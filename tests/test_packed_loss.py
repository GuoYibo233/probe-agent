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

# TODO(gyb, 2026-09-22): run as CLAUDE.md spells it (`external/probe-env/bin/python
# tests/test_packed_loss.py`) the import below fails with "No module named 'data'", at HEAD
# too; the three tests pass with PYTHONPATH set to the repo root. Either this file puts the
# repo root on sys.path, as tests/test_registry_concurrent_append.py does, or CLAUDE.md's
# command changes.
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


def _event(event_id, texts, tool, call):
    """One event's rows: nested prefixes in cut order, one tool and one call for the whole event."""
    return [dict(
        example_id=f"{event_id}|c{i}", event_id=event_id, record_id=event_id.split("|")[0],
        task_id=event_id.split("__")[0], seed=42, step=0, cut=len(text), cut_index=i,
        n_cuts=len(texts), depth=0.3 * (i + 1), text=text, tool=tool, call=call,
        args=[{"key": "id", "value": "1"}], weight=1.0, split="train", env="appworld",
        agent_model="gpt_oss_120b") for i, text in enumerate(texts)]


def _grow(base, n=3, step="Thinking step "):
    return [base + step * (i + 1) for i in range(n)]


def _fixture_frame() -> pl.DataFrame:
    """Two events, three cuts each -- the same shape data/training_data.py's writer stamps a version onto."""
    base = "The task is to pay a bill. I will look at the phone app. "
    rows = _event("t0__s42|s0", _grow(base), "phone.login", "phone.login(user='a')")
    rows += _event("t1__s42|s0", _grow(base), "phone.pay", "phone.pay(id=1)")
    return pl.DataFrame(rows, strict=False)


def _n_tok(tok, text) -> int:
    return len(tok(text, add_special_tokens=False, truncation=False)["input_ids"])


def _cases(tok):
    """(label, frame, max_len) triples: the plain fixture, and the three shapes where a method's
    batches() legitimately keeps fewer rows, or fewer tokens, than the whole frame carries. Each of
    the three fails whenever the two sides stop agreeing on which rows are scored and how they are
    cut, which is what the alignment gate would then report as a packing bug."""
    short = "The task is to pay a bill. I will look at the phone app. "
    long_text = "The agent looked at the phone application screen again and again. " * 8
    long_call = "phone.pay(id='" + "x " * 200 + "')"

    overlong = pl.DataFrame(
        _event("a0__s42|s0", _grow(short), "phone.pay", "phone.pay(id=1)")
        + _event("a1__s42|s0", _grow(long_text), "phone.login", "phone.login(user='a')"),
        strict=False)

    long_target = pl.DataFrame(
        _event("b0__s42|s0", _grow(short), "phone.pay", "phone.pay(id=1)")
        + _event("b1__s42|s0", _grow(short + "again "), "phone.pay", long_call), strict=False)

    band_texts = _grow("The agent read the bill and opened the phone application. " * 2)
    band = pl.DataFrame(_event("c0__s42|s0", band_texts, "phone.pay", "phone.pay(id=1)"),
                        strict=False)
    band_max_len = max(_n_tok(tok, t) for t in band_texts) + 2

    return [
        ("two events of nested prefixes", _fixture_frame(), 512),
        ("an event whose longest text is over max_len", overlong, 64),
        ("an event whose target is over MAX_TGT_TOK", long_target, 512),
        ("an event whose prompt sits just under max_len", band, band_max_len),
    ]


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

        probe_kind = "classifier" if method_name == "ctool" else "generator"
        probe = _StubProbe(tok, backbone, head, lm_head, probe_kind, ["phone.login", "phone.pay"])
        method = importlib.import_module(f"train.methods.{method_name}")
        d = pathlib.Path(tempfile.mkdtemp())

        import types

        for i, (label, frame, max_len) in enumerate(_cases(tok)):
            with self.subTest(case=label):
                path = d / f"examples{i}.parquet"
                training_data.write(path, frame)
                df = training_data.read(path)
                probe.max_len = max_len

                cfg = types.SimpleNamespace(
                    train=types.SimpleNamespace(
                        seed=42, max_len=max_len, events_per_mb=2, accum=1,
                        predict=types.SimpleNamespace(splits=["train"], cap=None, max_new=8)),
                    probe=types.SimpleNamespace(method=method_name),
                    data=types.SimpleNamespace(env="appworld"))

                if method_name == "ctool":
                    labels = method.head_labels(df, cfg)
                    self.assertEqual(labels, sorted(df["tool"].unique().to_list()))

                with torch.no_grad():
                    packed = sum(float(method.loss(probe, b))
                                 for b in method.batches(df, tok, cfg))
                    plain = float(method.reference_loss(probe, df))

                n = len(df)
                diff = abs(packed - plain) / n
                self.assertLess(diff, TOL, f"{method_name} [{label}]: packed={packed / n} "
                                           f"plain={plain / n} diff={diff}")

    def test_ctool(self) -> None:
        self._check("ctool")

    def test_cgen(self) -> None:
        self._check("cgen")

    def test_cparam(self) -> None:
        self._check("cparam")


if __name__ == "__main__":
    unittest.main()
