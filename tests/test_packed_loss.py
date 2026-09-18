"""The packed loss equals a row-by-row loss kept in its plainest form, on a tiny CPU model, once per probe method."""
# venv: probe
from __future__ import annotations

import importlib
import pathlib
import tempfile
import unittest

import polars as pl
import torch
from transformers import AutoConfig, AutoModel, AutoTokenizer

from data import training_data

TOKDIR = "/net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-0.6B-Base"
TOL = 1e-4   # 2.5's alignment-gate tolerance, applied here to the per-example-row difference


def _tiny_backbone_and_tokenizer():
    """A two-layer, 64-hidden Qwen3 model built from the fixture tokenizer's own config -- about 10M parameters, CPU only."""
    tok = AutoTokenizer.from_pretrained(TOKDIR)
    cfg = AutoConfig.from_pretrained(TOKDIR)
    cfg.hidden_size, cfg.intermediate_size = 64, 128
    cfg.num_hidden_layers, cfg.num_attention_heads, cfg.num_key_value_heads = 2, 4, 2
    cfg.head_dim = 16
    backbone = AutoModel.from_config(cfg, dtype=torch.float32).eval()
    return tok, backbone, cfg


def _fixture_frame() -> pl.DataFrame:
    """Two events, three cuts each -- the same shape data/training_data.py's writer stamps a version onto."""
    rows = []
    for ev in range(2):
        base = "The task is to pay a bill. I will look at the phone app. "
        for c in range(3):
            text = base + "Thinking step " * (c + 1)
            rows.append(dict(
                example_id=f"t{ev}__s42|s0|c{c}", event_id=f"t{ev}__s42|s0",
                record_id=f"t{ev}__s42", task_id=f"t{ev}", seed=42, step=0,
                cut=len(text), cut_index=c, n_cuts=3, depth=0.3 * (c + 1),
                text=text, tool="phone.pay" if ev else "phone.login",
                call=("phone.pay(id=1)" if ev else "phone.login(user='a')"),
                args=[{"key": "id", "value": "1"}] if ev else [{"key": "user", "value": "a"}],
                weight=1.0, split="train", env="appworld", agent_model="gpt_oss_120b"))
    return pl.DataFrame(rows, strict=False)


class _StubOutputs:
    def __init__(self, logits, hidden):
        self.logits = logits
        self.hidden = hidden


class _StubProbe:
    """The one Probe.forward models/probe_models/base.py has, over a tiny backbone."""

    def __init__(self, tok, backbone, head, lm_head, probe_kind, labels):
        self.tokenizer = tok
        self.max_len = 512
        self.probe_kind = probe_kind
        self.labels = labels
        self._backbone = backbone
        self._head = head
        self._lm_head = lm_head

    def forward(self, batch):
        out = self._backbone(input_ids=batch["input_ids"], attention_mask=batch["attention_mask"],
                             position_ids=batch.get("position_ids"), use_cache=False)
        h = out.last_hidden_state
        ee = batch["event_end"]
        hp = h[ee[:, 0], ee[:, 1]].float()
        head = self._head if self.probe_kind == "classifier" else self._lm_head
        return _StubOutputs(head(hp), h)

    def set_training(self, flag):
        pass


class TestPackedLoss(unittest.TestCase):
    def _check(self, method_name: str) -> None:
        tok, backbone, cfg_model = _tiny_backbone_and_tokenizer()
        head = torch.nn.Linear(64, 3)
        lm_head = torch.nn.Linear(64, cfg_model.vocab_size, bias=False)

        d = pathlib.Path(tempfile.mkdtemp())
        training_data.write(d / "examples.parquet", _fixture_frame())
        df = training_data.read(d / "examples.parquet")

        probe_kind = "classifier" if method_name == "ctool" else "generator"
        probe = _StubProbe(tok, backbone, head, lm_head, probe_kind, ["phone.login", "phone.pay"])

        import types

        cfg = types.SimpleNamespace(
            train=types.SimpleNamespace(seed=42, max_len=512, events_per_mb=2, accum=1,
                                        predict=types.SimpleNamespace(splits=["train"], cap=None, max_new=8)),
            probe=types.SimpleNamespace(method=method_name), data=types.SimpleNamespace(env="appworld"))

        method = importlib.import_module(f"train.methods.{method_name}")
        if method_name == "ctool":
            labels = method.head_labels(df, cfg)
            self.assertEqual(labels, sorted(df["tool"].unique().to_list()))

        with torch.no_grad():
            packed = sum(float(method.loss(probe, b)) for b in method.batches(df, tok, cfg))
            plain = float(method.reference_loss(probe, df))

        n = len(df)
        diff = abs(packed - plain) / n
        self.assertLess(diff, TOL, f"{method_name}: packed={packed / n} plain={plain / n} diff={diff}")

    def test_ctool(self) -> None:
        self._check("ctool")

    def test_cgen(self) -> None:
        self._check("cgen")

    def test_cparam(self) -> None:
        self._check("cparam")


if __name__ == "__main__":
    unittest.main()
