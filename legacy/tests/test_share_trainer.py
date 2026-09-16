"""tests/test_share_trainer.py -- (a)(b)(c) of spec `.scratch/kvshare-train/spec.md`
section 12, corresponding to ticket `.scratch/kvshare-train/issues/03-share-trainer.md`.

All models are small models randomly initialized with `transformers.Qwen3Config`
(full-parameter, no LoRA attached -- LoRA dropout 0.05 resamples on every forward
pass, and the gradient equality does not hold for LoRA); `vocab_size` takes the real
tokenizer's vocabulary size (`len(tok)`, including added tokens, otherwise high token
ids in real data would go out of range), CPU fp32.

How to run (needs cprobe-env, `import train_causal_share` has a top-level
transformers>=5.14 version gate):
  cprobe-env/bin/python -m unittest tests.test_share_trainer -v
When system python3 runs the full discover, this module is skipped entirely (no
torch), which does not count as a failure; under mbert-env (transformers 4.57.6),
`import train_causal_share` raises `SystemExit`, and this is caught the same way
and skipped (following `tests/test_cparam_assembly.py` lines 21 to 29).

When the real Qwen3-0.6B-Base tokenizer path or the live data
`pipeline/data/nyapass_aw_v1/gptoss` does not exist, the test cases that touch them
call `skipTest`.
"""
import json
import random as _random
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline/train"))

try:
    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer
except ImportError as e:                       # System python3 has no torch
    raise unittest.SkipTest(f"needs the cprobe-env interpreter: {e}")

try:
    import train_causal_share as tcs           # noqa: E402
    import train_causal_callgen                # noqa: E402
    import train_causal_param                  # noqa: E402
    import share_data                          # noqa: E402
except ImportError as e:                       # System python3 has no transformers
    raise unittest.SkipTest(f"needs the cprobe-env interpreter: {e}")
except SystemExit as e:                        # mbert-env's transformers<5.14
    raise unittest.SkipTest(f"needs the cprobe-env interpreter: {e}")

QWEN_PATH = train_causal_callgen.MODELS["qwen"]
DATA_DIR = ROOT / "pipeline/data/nyapass_aw_v1/gptoss"
VAL_PATH = DATA_DIR / "val.jsonl"
TRAIN_PATH = DATA_DIR / "train.jsonl"

SEED = 20260729          # The test fixture's own fixed seed, same as tests/test_lora_merge.py


def _tiny_config(vocab_size):
    """A randomly initialized two-layer Qwen3, same family structure as the three base
    models, small enough for CPU-second-level runs (following tests/test_lora_merge.py's
    tiny_config, with vocab_size swapped for the real vocabulary)."""
    return transformers.Qwen3Config(
        hidden_size=64, intermediate_size=128, num_hidden_layers=2,
        num_attention_heads=4, num_key_value_heads=2, head_dim=16,
        vocab_size=vocab_size, max_position_embeddings=8192,
        tie_word_embeddings=False)


def _load_five_short_events():
    """Pick 5 short events from the live val set (2 to 6 rows, full text under 800
    characters), seed 42 (following tests/test_share_data.py's sampling method),
    written into a temporary jsonl."""
    raw_by_event, order = {}, []
    with open(VAL_PATH) as f:
        for line in f:
            r = json.loads(line)
            ev = r["event"]
            if ev not in raw_by_event:
                raw_by_event[ev] = []
                order.append(ev)
            raw_by_event[ev].append(r)
    cands = []
    for ev in order:
        rs = sorted(raw_by_event[ev], key=lambda r: r["sent_idx"])
        if 2 <= len(rs) <= 6 and len(rs[-1]["text"]) <= 800:
            cands.append(ev)
    picked = _random.Random(42).sample(cands, min(5, len(cands)))
    rows = []
    for ev in picked:
        rows.extend(sorted(raw_by_event[ev], key=lambda r: r["sent_idx"]))
    tmpdir = tempfile.TemporaryDirectory()
    path = str(Path(tmpdir.name) / "five.jsonl")
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return tmpdir, path


class TestPackedForwardMatchesOldPath(unittest.TestCase):
    """(a) The per-row ce from the packed forward pass differs from the old path (old collate + inst_ce) by <= 1e-5, row by row."""

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"tokenizer path does not exist: {QWEN_PATH}")
        if not VAL_PATH.exists():
            raise unittest.SkipTest(f"val set does not exist: {VAL_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)
        if cls.tok.pad_token_id is None:
            cls.tok.pad_token = cls.tok.eos_token
        cls.tok.truncation_side = "left"
        cls.tok.padding_side = "right"

        cls.tmpdir, cls.data_path = _load_five_short_events()

        torch.manual_seed(SEED)
        cls.model = AutoModelForCausalLM.from_config(_tiny_config(len(cls.tok)))
        cls.model.eval()

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def _check_mode(self, mode):
        events, _counts = share_data.load_events(
            self.data_path, self.tok, mode=mode, max_len=8192, limit=0)
        self.assertGreater(len(events), 0)

        OldDS = (train_causal_callgen.CallDS if mode == "cgen"
                else train_causal_param.ParamDS)
        old_collate = (train_causal_callgen.collate if mode == "cgen"
                      else train_causal_param.collate)
        old_inst_ce = (train_causal_callgen.inst_ce if mode == "cgen"
                      else train_causal_param.inst_ce)
        ds = OldDS(self.data_path, self.tok, limit=0)

        # Both paths keep row order as file order (load_events' order-preserving contract +
        # OldDS not shuffling with limit=0); check that text matches position by position
        # first, only then does comparing ce make sense.
        new_texts = [row[1] for ev in events for row in ev["rows"]]
        self.assertEqual(len(ds.rows), len(new_texts))
        for r, t in zip(ds.rows, new_texts):
            self.assertEqual(r[0], t)

        with torch.no_grad():
            enc, labels = old_collate(ds.rows, self.tok, 8192)[:2]
            old_ce = old_inst_ce(self.model, enc, labels, "cpu")

            new_row_ce = torch.cat([
                tcs.block_row_ce(self.model, [ev], "cpu", torch.float32)[0]
                for ev in events])

        diff = (new_row_ce - old_ce).abs()
        self.assertLessEqual(diff.max().item(), 1e-5,
                             f"max diff {diff.max().item()} (mode={mode})")

    def test_cgen(self):
        self._check_mode("cgen")

    def test_cparam(self):
        self._check_mode("cparam")


class TestRefForwardUsesInstCe(unittest.TestCase):
    """F1 (found in review): the row-by-row ce from `train_causal_share._ref_forward`
    (the alignment check's reference path) must really come from calling `inst_ce`,
    not a separately hand-written substitute using the same formula -- (a) only
    verifies the difference between the new path `block_row_ce` and `inst_ce`, it
    does not cover `_ref_forward` itself, so this asserts directly on `_ref_forward`."""

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"tokenizer path does not exist: {QWEN_PATH}")
        if not VAL_PATH.exists():
            raise unittest.SkipTest(f"val set does not exist: {VAL_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)
        if cls.tok.pad_token_id is None:
            cls.tok.pad_token = cls.tok.eos_token
        cls.tok.truncation_side = "left"
        cls.tok.padding_side = "right"

        cls.tmpdir, cls.data_path = _load_five_short_events()

        torch.manual_seed(SEED)
        cls.model = AutoModelForCausalLM.from_config(_tiny_config(len(cls.tok)))
        cls.model.eval()

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def _check_mode(self, mode):
        OldDS = (train_causal_callgen.CallDS if mode == "cgen"
                else train_causal_param.ParamDS)
        old_collate = (train_causal_callgen.collate if mode == "cgen"
                      else train_causal_param.collate)
        old_inst_ce = (train_causal_callgen.inst_ce if mode == "cgen"
                      else train_causal_param.inst_ce)
        ds = OldDS(self.data_path, self.tok, limit=0)

        with torch.no_grad():
            row_ref, _tok_ref = tcs._ref_forward(
                mode, self.model, self.tok, ds.rows, "cpu", 8192,
                tcs.REF_BATCH)

            # Without going through `_ref_forward`, independently run through the old collate
            # + a real call to inst_ce again the same batching way -- both sides must match row
            # by row (same model, same batch of inputs, the same single no_grad forward pass,
            # theoretically bit-level identical), which is the only way to prove that what
            # `_ref_forward` returns is `inst_ce`'s real output, not a separate implementation
            # using the same formula.
            direct = []
            for i in range(0, len(ds.rows), tcs.REF_BATCH):
                chunk = ds.rows[i:i + tcs.REF_BATCH]
                enc, labels = old_collate(chunk, self.tok, 8192)[:2]
                direct.extend(
                    old_inst_ce(self.model, enc, labels, "cpu").tolist())

        self.assertEqual(len(row_ref), len(direct))
        diff = max(abs(a - b) for a, b in zip(row_ref, direct))
        self.assertEqual(diff, 0.0,
                         f"_ref_forward's row-by-row result and calling inst_ce directly are not "
                         f"the same computation (max diff {diff}, mode={mode})")

    def test_cgen(self):
        self._check_mode("cgen")

    def test_cparam(self):
        self._check_mode("cparam")


class TestRunAlignCheckHandlesRefBaselineDriftError(unittest.TestCase):
    """N1 (found in review): when `_ref_forward`'s self-check fails (the reference
    baseline is untrustworthy), it must go through the same failure-reporting
    channel as every other check in `run_align_check` -- write ALIGN_CHECK.json,
    print diagnostics, `sys.exit(2)` -- it must not be a bare `assert` (which gets
    stripped out entirely and silently passed under `-O`/`PYTHONOPTIMIZE`), nor can
    it let the exception surface as-is into an unhandled traceback (which loses the
    structured output)."""

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"tokenizer path does not exist: {QWEN_PATH}")
        if not VAL_PATH.exists():
            raise unittest.SkipTest(f"val set does not exist: {VAL_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)
        if cls.tok.pad_token_id is None:
            cls.tok.pad_token = cls.tok.eos_token
        cls.tok.truncation_side = "left"
        cls.tok.padding_side = "right"

        cls.tmpdir, cls.data_path = _load_five_short_events()

        torch.manual_seed(SEED)
        cls.model = AutoModelForCausalLM.from_config(_tiny_config(len(cls.tok)))
        cls.model.eval()

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def test_ref_forward_raises_real_exception_not_assert(self):
        """When check_drift=True (the default), a drift beyond tolerance must raise
        `RefBaselineDriftError` -- a real exception class, not a bare `assert`
        (which is not stripped out under `-O`), with the drift value included in
        the error message, so you know how far off it is without reproducing it
        (ticket 05 item 7 N2). Use a monkeypatched `inst_ce`, offset by 1.0 on every
        row (far beyond the 1e-6 tolerance), to construct a scenario that is
        guaranteed to exceed tolerance."""
        ds = train_causal_callgen.CallDS(self.data_path, self.tok, limit=0)
        orig = train_causal_callgen.inst_ce

        def _perturbed(model, enc, labels, dev):
            return orig(model, enc, labels, dev) + 1.0

        train_causal_callgen.inst_ce = _perturbed
        try:
            with torch.no_grad():
                with self.assertRaises(tcs.RefBaselineDriftError) as cm:
                    tcs._ref_forward("cgen", self.model, self.tok, ds.rows,
                                     "cpu", 8192, tcs.REF_BATCH,
                                     check_drift=True)
            msg = str(cm.exception)
            m = re.search(r"max diff ([0-9.eE+-]+)", msg)
            self.assertIsNotNone(m, f"error message doesn't carry the drift value: {msg}")
            self.assertGreater(float(m.group(1)), tcs.REF_INST_CE_DRIFT_TOL)
        finally:
            train_causal_callgen.inst_ce = orig

    def test_ref_forward_check_drift_false_does_not_raise(self):
        """With the same guaranteed-to-exceed-tolerance monkeypatch, `check_drift=False`
        does not raise (ticket 05 S2: the bf16 coarse-filter pass turns this
        self-check off, it uses only `row_ce`). The return value is still `inst_ce`'s
        real output (the offset one), not a local-formula substitute."""
        ds = train_causal_callgen.CallDS(self.data_path, self.tok, limit=0)
        orig = train_causal_callgen.inst_ce

        def _perturbed(model, enc, labels, dev):
            return orig(model, enc, labels, dev) + 1.0

        train_causal_callgen.inst_ce = _perturbed
        try:
            with torch.no_grad():
                row_ce, tok_ce = tcs._ref_forward(
                    "cgen", self.model, self.tok, ds.rows, "cpu", 8192,
                    tcs.REF_BATCH, check_drift=False)
            self.assertTrue(row_ce)
            self.assertTrue(tok_ce)
        finally:
            train_causal_callgen.inst_ce = orig

    def test_run_align_check_reports_drift_error_instead_of_crashing(self):
        """After `run_align_check` catches `RefBaselineDriftError`, it handles it the same
        way as every other failure branch in the file: write ALIGN_CHECK.json
        (PASS=False, stage="ref_forward_drift"), then `sys.exit(2)` -- not letting
        the exception surface as-is.
        """
        import argparse
        orig = tcs._ref_forward

        def _boom(*_a, **_kw):
            raise tcs.RefBaselineDriftError("drift injected for testing")

        tcs._ref_forward = _boom
        try:
            with tempfile.TemporaryDirectory() as out_dir:
                args = argparse.Namespace(
                    data=str(DATA_DIR), out=out_dir, align_events=2,
                    max_len=8192, align_tol=2e-5, attn_impl="sdpa",
                    # Ticket 09: run_align_check reads the newly added threshold parameter from args;
                    # this Namespace is hand-built and does not go through argparse defaults, so fill
                    # in the new attribute (value equal to the CLI default) to prevent AttributeError.
                    align_tok_tol=3e-4, align_bf16_mean_tol=2e-2,
                    align_bf16_max_tol=1e-1, align_baseline_factor=3.0,
                    align_rule="abs", align_rel_tol=1e-5)
                with self.assertRaises(SystemExit) as cm:
                    tcs.run_align_check(self.model, self.tok, args, "cpu",
                                        "cgen", None)
                self.assertEqual(cm.exception.code, 2)

                report_path = Path(out_dir) / "ALIGN_CHECK.json"
                self.assertTrue(report_path.exists(),
                               "drift error did not write out ALIGN_CHECK.json")
                report = json.loads(report_path.read_text())
                self.assertFalse(report["PASS"])
                self.assertEqual(report["stage"], "ref_forward_drift")
                self.assertIn("drift injected for testing", report["error"])
        finally:
            tcs._ref_forward = orig


class TestBackwardBlockSplitInvariance(unittest.TestCase):
    """(b) The parameter gradients from splitting one logical minibatch into 1 block
    versus into 3 blocks differ element-wise by <= 1e-6

    (spec section 5: the sum of the gradients from m physical blocks equals the
    gradient from computing the whole logical minibatch in one go; this property
    only depends on W and n_g staying fixed, and is independent of how exactly the
    blocks are split).
    """

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"tokenizer path does not exist: {QWEN_PATH}")
        if not VAL_PATH.exists():
            raise unittest.SkipTest(f"val set does not exist: {VAL_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)
        if cls.tok.pad_token_id is None:
            cls.tok.pad_token = cls.tok.eos_token
        cls.tok.truncation_side = "left"
        cls.tok.padding_side = "right"
        cls.tmpdir, cls.data_path = _load_five_short_events()
        cls.vocab_size = len(cls.tok)

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def _run(self, blocks, W):
        torch.manual_seed(SEED)
        model = AutoModelForCausalLM.from_config(_tiny_config(self.vocab_size))
        model.train()
        tcs.backward_logical_minibatch(model, blocks, W, n_g=1, dev="cpu",
                                       mask_dtype=torch.float32)
        return {n: p.grad.clone() for n, p in model.named_parameters()
                if p.grad is not None}

    def test_split_into_1_vs_3_blocks(self):
        events, _counts = share_data.load_events(
            self.data_path, self.tok, mode="cgen", max_len=8192,
            limit=3, order="shortest")
        self.assertEqual(len(events), 3)
        W = sum(row[5] for ev in events for row in ev["rows"])

        grads_1block = self._run([events], W)
        grads_3block = self._run([[events[0]], [events[1]], [events[2]]], W)

        self.assertTrue(grads_1block, "not a single gradient after running 1 block")
        self.assertEqual(set(grads_1block), set(grads_3block))
        bad = []
        for k in grads_1block:
            diff = (grads_1block[k] - grads_3block[k]).abs().max().item()
            if diff > 1e-6:
                bad.append((k, diff))
        self.assertEqual(bad, [], f"these parameters' gradients don't match between 1 block and 3 blocks: {bad[:5]}")


class TestBlockRowCeUnderLoRA(unittest.TestCase):
    """Ticket 05 acceptance item 3: after `_forward_packed` switches to using
    `model.model(...)`'s backbone output and then `model.lm_head` (S1),
    a forward pass plus backward pass under the LoRA wrapper must still run,
    and only the adapter parameters should get gradients. The two test cases
    cover the two branches of `_base_model_and_head` separately:
    `test_lora_forward_backward` uses `lora_util.wrap`'s in-place injection,
    with the caller's original `model` variable continuing to use this actual
    path (falls into the `else` branch -- `model` itself is not a PeftModel);
    `test_get_base_model_branch_forward_backward` uses the more general path
    where "what you get is the PeftModel itself" (ticket 05 final-review F1:
    the `get_base_model()` branch had no test case actually executing it
    before this).

    Runs if peft is installed, skips if not."""

    @classmethod
    def setUpClass(cls):
        try:
            import peft  # noqa: F401
        except ImportError as e:
            raise unittest.SkipTest(f"peft not installed: {e}")
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"tokenizer path does not exist: {QWEN_PATH}")
        if not VAL_PATH.exists():
            raise unittest.SkipTest(f"val set does not exist: {VAL_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)
        if cls.tok.pad_token_id is None:
            cls.tok.pad_token = cls.tok.eos_token
        cls.tok.truncation_side = "left"
        cls.tok.padding_side = "right"
        cls.tmpdir, cls.data_path = _load_five_short_events()

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def test_lora_forward_backward(self):
        import argparse
        import lora_util

        torch.manual_seed(SEED)
        model = AutoModelForCausalLM.from_config(_tiny_config(len(self.tok)))
        model.train()
        lora_args = argparse.Namespace(
            lora_rank=4, lora_alpha=8, lora_dropout=0.0)
        lora_util.wrap(model, lora_args)  # in-place injection, original model variable keeps being used

        events, _counts = share_data.load_events(
            self.data_path, self.tok, mode="cgen", max_len=8192,
            limit=2, order="shortest")
        self.assertEqual(len(events), 2)
        W = sum(row[5] for ev in events for row in ev["rows"])

        tcs.backward_logical_minibatch(
            model, [events], W, n_g=1, dev="cpu", mask_dtype=torch.float32)

        trainable = [(n, p) for n, p in model.named_parameters()
                    if p.requires_grad]
        frozen = [(n, p) for n, p in model.named_parameters()
                 if not p.requires_grad]
        self.assertTrue(trainable, "no trainable parameters at all after LoRA wrapping")
        self.assertTrue(
            any(p.grad is not None for _n, p in trainable),
            "not a single LoRA adapter parameter got a gradient -- S1's model.model()/"
            "model.lm_head accessors don't build a graph under peft wrapping")
        self.assertTrue(
            all(p.grad is None for _n, p in frozen),
            "non-adapter parameters should not have a gradient (lora_util.wrap already set their requires_grad "
            "to False)")

    def test_get_base_model_branch_forward_backward(self):
        """Ticket 05 final-review F1: the `model` that `test_lora_forward_backward` passes to
        `backward_logical_minibatch` is the original variable after `lora_util.wrap`'s
        in-place injection, which itself is not a PeftModel, so in `_base_model_and_head`
        `hasattr(model, "get_base_model")` is always false, and the `get_base_model()`
        half of the code was never executed. This changes the call to pass
        `lora_util.wrap`'s **return value** (the actual `PeftModel` object) as `model`,
        forcing `_base_model_and_head` down the `get_base_model()` branch: first it
        directly checks that the backbone/lm_head obtained are the same two attributes
        on the object returned by `get_base_model()` (proving the branch fetches the
        right values), then it runs one real forward pass plus backward pass (proving
        the computation graph built under this branch can actually train -- not just
        that the objects are equal)."""
        import argparse
        import lora_util

        torch.manual_seed(SEED)
        model = AutoModelForCausalLM.from_config(_tiny_config(len(self.tok)))
        model.train()
        lora_args = argparse.Namespace(
            lora_rank=4, lora_alpha=8, lora_dropout=0.0)
        wrapped = lora_util.wrap(model, lora_args)  # the actual PeftModel, don't discard it

        self.assertTrue(
            hasattr(wrapped, "get_base_model"),
            "peft version changed, PeftModel no longer has get_base_model() -- "
            "_base_model_and_head's branch condition needs to change accordingly")
        backbone, lm_head = tcs._base_model_and_head(wrapped)
        base = wrapped.get_base_model()
        self.assertIs(
            backbone, base.model,
            "the backbone taken from the get_base_model() branch should be "
            "the .model on the object returned by get_base_model()")
        self.assertIs(
            lm_head, base.lm_head,
            "the lm_head taken from the get_base_model() branch should be "
            "the .lm_head on the object returned by get_base_model()")

        events, _counts = share_data.load_events(
            self.data_path, self.tok, mode="cgen", max_len=8192,
            limit=2, order="shortest")
        W = sum(row[5] for ev in events for row in ev["rows"])

        tcs.backward_logical_minibatch(
            wrapped, [events], W, n_g=1, dev="cpu", mask_dtype=torch.float32)

        trainable = [(n, p) for n, p in model.named_parameters()
                    if p.requires_grad]
        frozen = [(n, p) for n, p in model.named_parameters()
                 if not p.requires_grad]
        self.assertTrue(
            any(p.grad is not None for _n, p in trainable),
            "not a single LoRA adapter parameter got a gradient on the get_base_model() branch")
        self.assertTrue(
            all(p.grad is None for _n, p in frozen),
            "non-adapter parameters should not have a gradient on the get_base_model() branch")


class TestRunMemProbeCPU(unittest.TestCase):
    """Ticket 06: `run_mem_probe`'s CPU finish state and log fields -- the real
    acceptance criterion is an H100 measurement (whether, after the change,
    `fullest_block.peak_mem_gb` >= the peak `step` value over the whole training
    run; the ticket does not do this), here we only verify it runs on CPU,
    finishes cleanly, and all fields are present."""

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"tokenizer path does not exist: {QWEN_PATH}")
        if not VAL_PATH.exists():
            raise unittest.SkipTest(f"val set does not exist: {VAL_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)
        if cls.tok.pad_token_id is None:
            cls.tok.pad_token = cls.tok.eos_token
        cls.tok.truncation_side = "left"
        cls.tok.padding_side = "right"
        cls.tmpdir, cls.data_path = _load_five_short_events()

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def test_state_cleared_lr_restored_grad_none_after_probe(self):
        import argparse

        events, _counts = share_data.load_events(
            self.data_path, self.tok, mode="cgen", max_len=8192, limit=0)
        self.assertGreaterEqual(len(events), 2,
                                "need at least 2 events to make up the fullest block")

        torch.manual_seed(SEED)
        model = AutoModelForCausalLM.from_config(_tiny_config(len(self.tok)))
        model.train()
        orig_lr = 1e-3
        opt = torch.optim.AdamW(model.parameters(), lr=orig_lr,
                                weight_decay=0.01)
        args = argparse.Namespace(tok_budget=100000, events_per_mb=4,
                                  mem_probe_pick="tokens", accum=2)
        logged = []

        def log(**kw):
            logged.append(kw)

        tcs.run_mem_probe(model, opt, events, args, "cpu", log, amp=False)

        self.assertEqual(len(opt.state), 0, "opt.state should be empty after the probe finishes")
        self.assertTrue(
            all(g["lr"] == orig_lr for g in opt.param_groups),
            "each param_group's lr should be restored to its original value after the probe finishes")
        self.assertTrue(
            all(p.grad is None for p in model.parameters()),
            "every parameter's .grad should be None after the probe finishes")

        kinds = {e["kind"]: e for e in logged if e.get("event") == "mem_probe"}
        self.assertEqual(set(kinds), {"longest_event", "fullest_block"},
                         f"should write two mem_probe events, got: {logged}")
        for kind, n_backward in (("fullest_block", 2), ("longest_event", 1)):
            e = kinds[kind]
            self.assertEqual(e["n_backward"], n_backward,
                             f"{kind}'s n_backward should be {n_backward}")
            self.assertTrue(e["optimizer_state_prebuilt"])
            self.assertTrue(e["with_optimizer_state"])
            self.assertEqual(e["peak_mem_gb"], 0.0)   # allowed to be 0 on CPU
            for key in ("B", "L_pad", "n_events", "packed_len_max"):
                self.assertIn(key, e, f"{kind} missing field {key}")

    def test_state_built_before_any_forward_backward(self):
        """F1 (ticket 06 fix round 2): per the ticket's literal ordering, no forward
        or backward pass should happen before the state-building step (first
        `opt.zero_grad(set_to_none=False)` followed by an lr=0 `opt.step()`) --
        verify this with a `block_row_ce` stand-in that records whether
        `opt.state` is still an empty dict at the moment it is called: the
        first time a forward/backward pass happens, `opt.state` must already
        be non-empty (state already built), and no forward/backward pass may
        happen while `opt.state` is still an empty dict."""
        import argparse

        events, _counts = share_data.load_events(
            self.data_path, self.tok, mode="cgen", max_len=8192, limit=0)
        self.assertGreaterEqual(len(events), 2,
                                "need at least 2 events to make up the fullest block")

        torch.manual_seed(SEED)
        model = AutoModelForCausalLM.from_config(_tiny_config(len(self.tok)))
        model.train()
        opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=0.01)
        args = argparse.Namespace(tok_budget=100000, events_per_mb=4,
                                  mem_probe_pick="tokens", accum=2)
        logged = []

        def log(**kw):
            logged.append(kw)

        state_was_empty_at_call = []
        real_block_row_ce = tcs.block_row_ce

        def spy(*a, **kw):
            state_was_empty_at_call.append(len(opt.state) == 0)
            return real_block_row_ce(*a, **kw)

        with patch.object(tcs, "block_row_ce", side_effect=spy):
            tcs.run_mem_probe(model, opt, events, args, "cpu", log, amp=False)

        self.assertGreater(len(state_was_empty_at_call), 0,
                           "should have at least one forward-backward")
        self.assertFalse(any(state_was_empty_at_call),
                         "no forward or backward should happen before this state-building step, "
                         f"actual record: {state_was_empty_at_call}")


class TestMainSmokeCPU(unittest.TestCase):
    """(c) main() runs --smoke --max-events 6 --log-every 1 --align-events 2
    --device cpu (--base a temp directory, using build(path=...)); this
    produces best/meta.json, ALIGN_CHECK.json (PASS true), and the five
    kinds of events in train_log.jsonl.
    """

    def _run_smoke(self, mode):
        tok = AutoTokenizer.from_pretrained(QWEN_PATH)
        vocab_size = len(tok)
        with tempfile.TemporaryDirectory() as model_dir, \
                tempfile.TemporaryDirectory() as out_root:
            torch.manual_seed(SEED)
            model = AutoModelForCausalLM.from_config(_tiny_config(vocab_size))
            model.save_pretrained(model_dir)
            tok.save_pretrained(model_dir)

            out = Path(out_root) / "run"
            argv = ["train_causal_share.py", "--mode", mode,
                   "--base", model_dir, "--data", str(DATA_DIR),
                   "--out", str(out), "--smoke", "--max-events", "6",
                   "--log-every", "1", "--device", "cpu",
                   "--align-events", "2"]
            old_argv = sys.argv
            sys.argv = argv
            try:
                tcs.main()
            finally:
                sys.argv = old_argv

            self.assertTrue((out / "ALIGN_CHECK.json").exists())
            align = json.loads((out / "ALIGN_CHECK.json").read_text())
            self.assertTrue(align["PASS"], align)

            self.assertTrue((out / "best" / "meta.json").exists())
            meta = json.loads((out / "best" / "meta.json").read_text())
            self.assertEqual(meta["trainer"], "share")
            self.assertIn("call_sep", meta)
            self.assertIn("max_len", meta)
            self.assertIn("data", meta)
            if mode == "cparam":
                self.assertTrue(meta["param_only"])

            events_seen = []
            for line in open(out / "train_log.jsonl"):
                events_seen.append(json.loads(line)["event"])
            # 6 events but only 1 update (only --log-every 1 writes out step; ticket item 5).
            self.assertEqual(set(events_seen),
                             {"start", "step", "eval", "save_best", "done"})

    def test_cgen_smoke(self):
        if not Path(QWEN_PATH).exists():
            self.skipTest(f"tokenizer path does not exist: {QWEN_PATH}")
        if not TRAIN_PATH.exists() or not VAL_PATH.exists():
            self.skipTest(f"active data does not exist: {DATA_DIR}")
        self._run_smoke("cgen")

    def test_cparam_smoke(self):
        if not Path(QWEN_PATH).exists():
            self.skipTest(f"tokenizer path does not exist: {QWEN_PATH}")
        if not TRAIN_PATH.exists() or not VAL_PATH.exists():
            self.skipTest(f"active data does not exist: {DATA_DIR}")
        self._run_smoke("cparam")


if __name__ == "__main__":
    unittest.main()
