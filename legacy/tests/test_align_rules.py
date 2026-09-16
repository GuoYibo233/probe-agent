"""tests/test_align_rules.py -- alignment tolerance parameterization + relative criteria,
corresponds to ticket `.scratch/kvshare-train/issues/09-align-tolerance-params.md`,
spec `.scratch/kvshare-train/spec.md` 16.4 (criteria and key names), 16.9 item 3 (tests).

How to run (needs cprobe-env; both training scripts have a transformers>=5.14 version gate at
the top level):
  cprobe-env/bin/python -m unittest tests.test_align_rules -v
When the system python3 runs a full discover, this module is skipped entirely (no torch); this
does not count as a failure. Under mbert-env (transformers 4.57.6) the top-level import raises
`SystemExit`, which is likewise caught and skipped (following the approach in
`tests/test_cparam_assembly.py`).

The new-trainer section uses 3 hand-built short cgen events (does not read a live large
directory such as `pipeline/data/nyapass_aw_v1/gptoss`); the ctool section builds a temporary
`Qwen3Config` model directory following the approach at lines 59 and 625-632 of
`tests/test_share_trainer.py`, constructs `CausalProbe` directly and calls `align_check`,
without going through `main()`, likewise not reading a live data directory. The small-model
construction reuses `tests/test_share_trainer.py`'s `_tiny_config`/`QWEN_PATH`/`SEED` rather than
defining a duplicate copy.
"""
import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline/train"))

try:
    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer
except ImportError as e:                       # the system python3 does not have torch
    raise unittest.SkipTest(f"needs the cprobe-env interpreter: {e}")

try:
    import train_causal_share as tcs           # noqa: E402
    import train_causal_tool as tct            # noqa: E402
except ImportError as e:                       # the system python3 does not have transformers
    raise unittest.SkipTest(f"needs the cprobe-env interpreter: {e}")
except SystemExit as e:                        # mbert-env's transformers<5.14
    raise unittest.SkipTest(f"needs the cprobe-env interpreter: {e}")

from tests.test_share_trainer import _tiny_config, QWEN_PATH, SEED  # noqa: E402

ALIGN_RULES = ("abs", "rel", "both")


def _write_jsonl(rows, path):
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _write_tiny_cgen_val(path):
    """3 hand-built short events (cgen cell), 2 lines each. The lines' `text` must be mutual
    prefixes (required by `share_data.load_events`'s prefix-property spot check) -- built by
    string concatenation, the short line's `text` is exactly a prefix substring of the long
    line's (the event's full text) `text`. Returns the event count."""
    bodies = [
        "Alice opens the fridge and takes out milk",
        "Bob walks to the store and buys bread",
        "Carol reads a book and writes a note",
    ]
    tails = [
        " for breakfast today.",
        " for the weekend trip.",
        " before going to sleep.",
    ]
    rows = []
    for ei, (short, tail) in enumerate(zip(bodies, tails)):
        ev = f"ev{ei}"
        full = short + tail
        rows.append(dict(event=ev, sent_idx=0, n_sents=2, text=short,
                         label="l0", label_call=f"call_{ei}_a()", w=1.0))
        rows.append(dict(event=ev, sent_idx=1, n_sents=2, text=full,
                         label="l1", label_call=f"call_{ei}_b(1)", w=1.0))
    _write_jsonl(rows, path)
    return len(bodies)


class TestAlignRulesShare(unittest.TestCase):
    """The new trainer (`train_causal_share.py`)'s alignment tolerance parameterization + relative
    criteria, spec 16.4 item 1."""

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"tokenizer path does not exist: {QWEN_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)
        vocab_size = len(cls.tok)
        cls.model_dir_ctx = tempfile.TemporaryDirectory()
        cls.model_dir = cls.model_dir_ctx.name
        torch.manual_seed(SEED)
        model = AutoModelForCausalLM.from_config(_tiny_config(vocab_size))
        model.save_pretrained(cls.model_dir)
        cls.tok.save_pretrained(cls.model_dir)

    @classmethod
    def tearDownClass(cls):
        cls.model_dir_ctx.cleanup()

    def setUp(self):
        self.data_dir_ctx = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.data_dir_ctx.name)
        self.n_events = _write_tiny_cgen_val(self.data_dir / "val.jsonl")
        self.out_root_ctx = tempfile.TemporaryDirectory()
        self.out_root = Path(self.out_root_ctx.name)

    def tearDown(self):
        self.data_dir_ctx.cleanup()
        self.out_root_ctx.cleanup()

    def _run_align_only(self, extra_argv, out_name):
        """Goes through the real CLI entry point `tcs.main()` (with `sys.argv` patched), following the
        same approach as `tests/test_share_trainer.py`'s `TestMainSmokeCPU._run_smoke`, except
        here `--data` points at the hand-built small data directory and `--align-only` is
        added."""
        out = self.out_root / out_name
        argv = ["train_causal_share.py", "--mode", "cgen",
               "--base", self.model_dir, "--data", str(self.data_dir),
               "--out", str(out), "--align-only", "--device", "cpu",
               "--align-events", str(self.n_events)] + extra_argv
        old_argv = sys.argv
        sys.argv = argv
        try:
            tcs.main()
        finally:
            sys.argv = old_argv
        return out

    def test_three_rules_pass_with_all_new_keys(self):
        """All three rules' `ALIGN_CHECK.json` have every new key, and PASS is true for all of them --
        on fp32 CPU the small model's difference is on the order of 1e-6, and all three rules'
        default thresholds pass."""
        for rule in ALIGN_RULES:
            with self.subTest(rule=rule):
                out = self._run_align_only(
                    ["--align-rule", rule], f"run_{rule}")
                report = json.loads((out / "ALIGN_CHECK.json").read_text())
                for key in ("rule", "tol", "tok_tol", "rel_tol", "ref_scale",
                           "rel_max_abs_diff", "bf16_mean_tol",
                           "bf16_max_tol", "baseline_factor"):
                    self.assertIn(key, report, f"{rule} rule missing key {key}")
                self.assertEqual(report["rule"], rule)
                self.assertTrue(
                    report["PASS"],
                    f"{rule} rule should PASS (fp32 CPU diff is on the 1e-6 order): {report}")

    def test_align_rel_tol_negative_fails(self):
        """`--align-rule rel --align-rel-tol -1` must be judged failed, exit code 2 -- use a negative
        number, not 0: when the difference is exactly 0.0, `<= 0` would occasionally pass."""
        with self.assertRaises(SystemExit) as cm:
            self._run_align_only(
                ["--align-rule", "rel", "--align-rel-tol", "-1"], "run_neg")
        self.assertEqual(cm.exception.code, 2)

    def test_baseline_factor_zero(self):
        """When `--align-baseline-factor 0`, `max(0 x baseline, 1e-6)` is still 1e-6; it only warns when
        the difference is greater than 1e-6. If this difference on the small model is smaller
        than 1e-6, fall back to asserting that the `baseline_factor` key faithfully records the
        value passed in (ticket 09 item 1, last sentence)."""
        out = self._run_align_only(
            ["--align-baseline-factor", "0"], "run_bf0")
        report = json.loads((out / "ALIGN_CHECK.json").read_text())
        self.assertEqual(report["baseline_factor"], 0.0)
        if report["max_abs_diff"] > 1e-6:
            self.assertTrue(
                report["baseline_warn"],
                f"baseline_factor=0 diff {report['max_abs_diff']} exceeds "
                "the 1e-6 floor, baseline_warn should be true")

    def test_run_align_check_drift_exit_has_rule_and_rel_tol(self):
        """`run_align_check`'s second failure exit (the minimal report written when `_ref_forward`'s
        reference-baseline self-check fails) must also carry the `rule`/`rel_tol` keys -- follow
        the approach in `tests/test_share_trainer.py`'s
        `TestRunAlignCheckHandlesRefBaselineDriftError`: monkeypatch `_ref_forward` to raise
        `RefBaselineDriftError` directly."""
        torch.manual_seed(SEED)
        model = AutoModelForCausalLM.from_config(
            _tiny_config(len(self.tok)))
        model.eval()
        orig = tcs._ref_forward

        def _boom(*_a, **_kw):
            raise tcs.RefBaselineDriftError("drift injected for testing")

        tcs._ref_forward = _boom
        try:
            with tempfile.TemporaryDirectory() as out_dir:
                args = argparse.Namespace(
                    data=str(self.data_dir), out=out_dir,
                    align_events=self.n_events, max_len=8192,
                    align_tol=2e-5, attn_impl="sdpa",
                    align_rule="rel", align_rel_tol=1e-5)
                with self.assertRaises(SystemExit) as cm:
                    tcs.run_align_check(model, self.tok, args, "cpu",
                                        "cgen", None)
                self.assertEqual(cm.exception.code, 2)
                report = json.loads(
                    (Path(out_dir) / "ALIGN_CHECK.json").read_text())
                self.assertEqual(report["stage"], "ref_forward_drift")
                self.assertEqual(report["rule"], "rel")
                self.assertEqual(report["rel_tol"], 1e-5)
        finally:
            tcs._ref_forward = orig


class TestAlignRulesTool(unittest.TestCase):
    """ctool (`train_causal_tool.py`)'s alignment tolerance parameterization + relative criteria,
    spec 16.4 item 2. `CausalProbe.build()` only recognizes `MODELS[base]` and has no `path=`
    opening (`train_causal_tool.py` lines 177-184), so following the approach at lines 59 and
    625-632 of `tests/test_share_trainer.py`, build a temporary `Qwen3Config` model directory,
    construct `CausalProbe(<directory>, n_labels)` directly and call `align_check`, without
    going through `main()`, and without reading a live data directory."""

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"tokenizer path does not exist: {QWEN_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)
        vocab_size = len(cls.tok)
        cls.model_dir_ctx = tempfile.TemporaryDirectory()
        cls.model_dir = cls.model_dir_ctx.name
        torch.manual_seed(SEED)
        backbone_model = AutoModelForCausalLM.from_config(
            _tiny_config(vocab_size))
        backbone_model.save_pretrained(cls.model_dir)
        cls.tok.save_pretrained(cls.model_dir)
        torch.manual_seed(SEED)
        cls.probe = tct.CausalProbe(cls.model_dir, n_labels=4)
        cls.probe.eval()
        cls.text = ("Alice opens the fridge and takes out milk for "
                   "breakfast today.")

    @classmethod
    def tearDownClass(cls):
        cls.model_dir_ctx.cleanup()

    def test_three_rules_pass_with_reldiff_and_new_keys(self):
        for rule in ALIGN_RULES:
            with self.subTest(rule=rule):
                rep = tct.align_check(
                    self.probe, self.tok, self.text, 64, "cpu", "qwen",
                    self.model_dir, tol=3e-4, rule=rule, rel_tol=1e-5)
                for key in ("rule", "rel_tol", "reldiff_hidden",
                           "reldiff_logits"):
                    self.assertIn(key, rep, f"{rule} rule missing key {key}")
                self.assertEqual(rep["rule"], rule)
                self.assertTrue(
                    rep["PASS"],
                    f"{rule} rule should PASS (fp32 CPU diff is on the 1e-6 order): {rep}")

    def test_align_rel_tol_negative_fails(self):
        """`rel_tol = -1` is judged failed (use a negative number, not 0, same reasoning as on the new
        trainer side)."""
        rep = tct.align_check(
            self.probe, self.tok, self.text, 64, "cpu", "qwen",
            self.model_dir, tol=3e-4, rule="rel", rel_tol=-1)
        self.assertFalse(rep["PASS"], f"rel_tol=-1 should be judged a failure, got: {rep}")


if __name__ == "__main__":
    unittest.main()
