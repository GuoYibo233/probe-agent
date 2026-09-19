"""The probe class every backbone shares: load, save, score a prefix, generate a call."""
# venv: probe
from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
from transformers import AutoModel, AutoModelForCausalLM, AutoTokenizer

import models

# VERSION rule: read this before you edit this file (errata "3.3 / 8.6", gyb 2026-09-18).
# Bump VERSION only when some existing setting would now produce a different output of a stage
# that lists this file in the stage table of experimental_settings/schema.py. A new feature
# behind a new setting field whose default reproduces the old behaviour, a message, a comment
# or a report layout does not bump.
# Every bump adds one VERSION_HISTORY entry: {<new version>: {"why": "<one sentence>",
# "stale": (<stage names>)}}. "stale" names the stages (sample, build, train, eval, inject,
# score) whose existing outputs can no longer be used; leave "stale" out and every stage is
# stale. The key folds the highest version that made a stage stale, so a bump that leaves a
# stage usable keeps that stage's run directory. When unsure, list the stage.
VERSION = 2
VERSION_HISTORY = {
    2: {"why": "A restore that is handed the model row and the frozen setting keeps the row's "
               "dtype and rebuilds the adapter its tuning names, so a resumed run and the "
               "reload of best/ before the prediction step carry the form the fresh load built.",
        "stale": ("train",)},
}

Batch = dict[str, Any]      # keys forward consumes: input_ids, attention_mask,
                            # event_end, position_ids (optional); every other key
                            # is the method's own and base.py never reads it

GENERATE_BATCH = 8          # prompts per backbone.generate call inside Probe.generate

_PROBE_KINDS = ("classifier", "generator")
_TUNINGS = ("full", "lora")


@dataclass
class Outputs:
    logits: torch.Tensor          # classifier: [n_positions, n_labels]; generator: the LM head at event_end
    hidden: torch.Tensor | None   # classifier: [B, T, dim] at HEAD_LAYER; generator: None


def _read_attr_path(obj: Any, path: str) -> Any:
    for part in path.split("."):
        obj = getattr(obj, part)
    return obj


def _base_and_lm_head(model):
    """The inner transformer and the LM head, compatible with a peft-wrapped model (get_base_model() reaches down to the original)."""
    base = model.get_base_model() if hasattr(model, "get_base_model") else model
    return base.model, base.lm_head


class Probe(torch.nn.Module):
    def __init__(self, *, backbone, head, tokenizer, max_len: int,
                 labels: list[str] | None, probe_kind: str, lora, head_layer: str):
        super().__init__()
        self.backbone = backbone
        self.head = head
        self.tokenizer = tokenizer
        self.max_len = max_len
        self.labels = labels
        self.probe_kind = probe_kind
        self.lora = lora
        self._head_layer = head_layer

    def save(self, dir, *, labels=None, extra=None, meta=None) -> None:
        """Write the checkpoint layout (contracts 1.6): weights or merged adapter, tokenizer, head.pt for a classifier, meta.json."""
        import copy

        dir = Path(dir)
        dir.mkdir(parents=True, exist_ok=True)
        if self.lora is not None:
            merged = copy.deepcopy(self.lora).merge_and_unload()
            merged.save_pretrained(dir)
            was_cuda = next(merged.parameters()).is_cuda
            del merged
            if was_cuda:
                torch.cuda.empty_cache()
        else:
            self.backbone.save_pretrained(dir)
        self.tokenizer.save_pretrained(dir)
        if self.probe_kind == "classifier":
            torch.save(self.head.state_dict(), dir / "head.pt")
        meta_out = {"labels": labels, **(meta or {}), **(extra or {})}
        (dir / "meta.json").write_text(json.dumps(meta_out))

    def forward(self, batch: Batch) -> Outputs:
        device = next(self.backbone.parameters()).device
        input_ids = batch["input_ids"].to(device)
        attention_mask = batch["attention_mask"].to(device)
        event_end = batch["event_end"].to(device)
        kwargs = dict(input_ids=input_ids, attention_mask=attention_mask, use_cache=False)
        position_ids = batch.get("position_ids")
        if position_ids is not None:
            kwargs["position_ids"] = position_ids.to(device)
        seq_idx, tok_idx = event_end[:, 0], event_end[:, 1]

        if self.probe_kind == "classifier":
            out = self.backbone(**kwargs)
            hidden_states = _read_attr_path(out, self._head_layer)
            picked = hidden_states[seq_idx, tok_idx]
            logits = self.head(picked.float())
            return Outputs(logits=logits, hidden=hidden_states)

        inner, lm_head = _base_and_lm_head(self.backbone)
        out = inner(**kwargs)
        picked = out.last_hidden_state[seq_idx, tok_idx].float()
        logits = lm_head(picked)
        return Outputs(logits=logits, hidden=None)

    def score(self, texts: list[str]) -> tuple[list[list[float]], list[str]]:
        """The class logits in labels order and the argmax class name, one event per text at its last token."""
        device = next(self.backbone.parameters()).device
        enc = self.tokenizer(texts, truncation=True, max_length=self.max_len, padding=True,
                             return_tensors="pt")
        enc = {k: v.to(device) for k, v in enc.items()}
        with torch.no_grad():
            out = self.backbone(input_ids=enc["input_ids"], attention_mask=enc["attention_mask"],
                                use_cache=False)
            hidden_states = _read_attr_path(out, self._head_layer)
            last = enc["attention_mask"].sum(dim=1) - 1
            rows = torch.arange(hidden_states.shape[0], device=device)
            picked = hidden_states[rows, last]
            logits = self.head(picked.float())
        names = [self.labels[i] for i in logits.argmax(dim=-1).tolist()]
        return logits.tolist(), names

    def generate(self, texts: list[str], max_new: int, call_sep: str) -> list[str]:
        """The greedy continuation after call_sep, cut at the first newline and stripped."""
        device = next(self.backbone.parameters()).device
        prompts = [t + call_sep for t in texts]
        # batched autoregressive generation reads the next-token logits from the
        # physically last column of the sequence, so the batch must be left-padded
        # regardless of the tokenizer's stored padding_side (score()'s right-padding,
        # which its attention_mask.sum(dim=1)-1 rule depends on)
        # GENERATE_BATCH prompts per backbone.generate call: a validation or prediction frame
        # holds hundreds of prompts of several thousand tokens each, and one call over all of
        # them does not fit a 48 GB card
        decoded: list[str] = []
        for i in range(0, len(prompts), GENERATE_BATCH):
            enc = self.tokenizer(prompts[i:i + GENERATE_BATCH], add_special_tokens=False,
                                 truncation=True, max_length=max(self.max_len - max_new, 1),
                                 padding=True, padding_side="left", return_tensors="pt").to(device)
            with torch.no_grad():
                out = self.backbone.generate(
                    **enc, do_sample=False, max_new_tokens=max_new,
                    eos_token_id=self.tokenizer.eos_token_id,
                    pad_token_id=self.tokenizer.pad_token_id)
            continuations = out[:, enc["input_ids"].shape[1]:]
            decoded.extend(self.tokenizer.batch_decode(continuations, skip_special_tokens=True))
        return [d.split("\n")[0].strip() for d in decoded]

    def trainable_parameters(self) -> list:
        """The optimizer's parameter list: every backbone and head parameter, filtered to requires_grad under LoRA."""
        params = list(self.backbone.parameters())
        if self.head is not None:
            params += list(self.head.parameters())
        if self.lora is None:
            return params
        return [p for p in params if p.requires_grad]

    def set_training(self, flag: bool) -> None:
        self.train(mode=flag)

    def grad_checkpointing(self, enabled: bool) -> None:
        if enabled:
            self.backbone.gradient_checkpointing_enable()
            self.backbone.config.use_cache = False
            if self.lora is not None and getattr(self.backbone, "_require_grads_hook", None) is None:
                if hasattr(self.backbone, "enable_input_require_grads"):
                    self.backbone.enable_input_require_grads()
        else:
            self.backbone.gradient_checkpointing_disable()
            self.backbone.config.use_cache = True


def load(row: dict | None, cfg: object, *, probe_kind: str, n_labels: int | None = None,
         labels: list[str] | None = None, ckpt_dir: str | Path | None = None,
         device: str = "cpu") -> Probe:
    if probe_kind not in _PROBE_KINDS:
        raise ValueError(f"probe_kind: {probe_kind!r} is not one of {_PROBE_KINDS}")

    if ckpt_dir is not None:
        ckpt_dir = Path(ckpt_dir)
        meta = json.loads((ckpt_dir / "meta.json").read_text())
        labels = meta.get("labels")
        tuning = meta["tuning"]
        max_len = meta["max_len"]
        family = models.probe(meta["backbone"]).family
        weights_path: str | Path = ckpt_dir
    else:
        family = row["family"]
        tuning = cfg.probe.tuning
        max_len = cfg.train.max_len
        weights_path = models.probe(cfg.models.probe).weights_path

    backbone_module = importlib.import_module(f"models.probe_models.{family}")
    # The dtype is the model row's whenever a row is given, restore or not: a resume from
    # last/ and the reload of best/ before the prediction step come back in the dtype the
    # fresh load picked, so one run's numerics are the same on both sides of a crash. The
    # served form is handed no row (models/probe_models/service.py) and takes the family's
    # serving dtype on a card and float32 on the cpu -- ticket 06's "a restore with no row",
    # and the sentence qwen.DTYPE carries: a row's result.dtype overrides at training.
    dtype_name = row["dtype"] if row is not None else (
        backbone_module.DTYPE if str(device).startswith("cuda") else "float32")
    dtype = getattr(torch, dtype_name)

    if probe_kind == "classifier":
        model = AutoModel.from_pretrained(weights_path, dtype=dtype)
    else:
        model = AutoModelForCausalLM.from_pretrained(weights_path, dtype=dtype)

    tokenizer = AutoTokenizer.from_pretrained(weights_path)
    backbone_module.prepare_tokenizer(tokenizer)
    if model.config.get_text_config().pad_token_id is None:
        model.config.get_text_config().pad_token_id = tokenizer.pad_token_id

    head = None
    if probe_kind == "classifier":
        head_n_labels = n_labels if ckpt_dir is None else len(labels)
        head = backbone_module.attach_head(model, head_n_labels)
        if ckpt_dir is not None:
            head.load_state_dict(torch.load(ckpt_dir / "head.pt", map_location="cpu"))

    # The tuning is built whenever the frozen setting is given, restore or not: the four
    # lora_* values live in cfg.probe alone, and the tuning itself comes from the checkpoint's
    # own meta.json on a restore. A restored LoRA probe therefore holds the adapter its
    # training held, so trainable_parameters() names the same tensors the crashed
    # incarnation's optimizer state holds and the run resumes as a LoRA run. save() merged
    # that adapter into the weights, so the rebuilt adapter starts from peft's
    # zero-initialised B over the merged weights and the probe scores what it scored before.
    # A load with no frozen setting is the served form (models/probe_models/service.py): it
    # serves those merged weights and trains nothing.
    lora = None
    if cfg is not None:
        if tuning == "full":
            pass
        elif tuning == "lora":
            import peft

            targets = cfg.probe.lora_targets or backbone_module.LORA_TARGETS
            peft_cfg = peft.LoraConfig(
                r=cfg.probe.lora_r, lora_alpha=cfg.probe.lora_alpha,
                lora_dropout=cfg.probe.lora_dropout, target_modules=list(targets), bias="none")
            lora = peft.get_peft_model(model, peft_cfg)
        else:
            raise ValueError(f"probe.tuning: {tuning!r} is not one of {_TUNINGS}")

    instance = Probe(backbone=model, head=head, tokenizer=tokenizer, max_len=max_len,
                     labels=labels, probe_kind=probe_kind, lora=lora,
                     head_layer=backbone_module.HEAD_LAYER)
    return instance.to(device)
