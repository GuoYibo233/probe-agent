"""tests/test_mem_probe_pick.py -- spec `.scratch/kvshare-train/spec.md` 16.5, 16.9,
corresponding to ticket `.scratch/kvshare-train/issues/10-mem-probe-pick.md`.

How to run it (needs cprobe-env; `import train_causal_share`'s top level has a
transformers>=5.14 version gate):
  cprobe-env/bin/python -m unittest tests.test_mem_probe_pick -v
When the system python3 runs the full discover, this module skips entirely (no torch);
that does not count as a failure; under mbert-env (transformers 4.57.6) it likewise
skips (following `tests/test_share_trainer.py`'s approach).

The small model and event construction reuse `tests/test_share_trainer.py`'s helper
functions (`_tiny_config`, `_load_five_short_events`, `QWEN_PATH`, etc.); they are not
copied again here; cases involving them call `skipTest` when the real Qwen3-0.6B-Base
tokenizer path or the live data does not exist.
"""
import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline/train"))
sys.path.insert(0, str(ROOT / "tests"))

try:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
except ImportError as e:                       # The system python3 lacks torch
    raise unittest.SkipTest(f"needs the cprobe-env interpreter: {e}")

try:
    import train_causal_share as tcs           # noqa: E402
    import share_data                          # noqa: E402
    import readonly_map                        # noqa: E402
except ImportError as e:                       # The system python3 lacks transformers
    raise unittest.SkipTest(f"needs the cprobe-env interpreter: {e}")
except SystemExit as e:                        # mbert-env's transformers<5.14
    raise unittest.SkipTest(f"needs the cprobe-env interpreter: {e}")

import test_share_trainer as tst               # noqa: E402: reuses the small-model/event helper functions

QWEN_PATH = tst.QWEN_PATH
DATA_DIR = tst.DATA_DIR
VAL_PATH = tst.VAL_PATH
TRAIN_PATH = tst.TRAIN_PATH
SEED = tst.SEED
_tiny_config = tst._tiny_config
_load_five_short_events = tst._load_five_short_events


def _mk_block(packed_len, loss_counts):
    """A single-event physical block (for pure block-picking logic tests): `_pick_cost_blocks`
    only reads a block's `packed_len` (padded via `_l_pad`) and, for each row, the count
    of entries in `row[4]` (`seg_lab`) that are not -100; it doesn't need real
    `full_ids`/`seg_ids`, so `packed_len` is given directly and `seg_lab` is written as
    all 1s (all loss positions). `loss_counts` is this event's loss-position count per
    row, row count = len(loss_counts). Returns a single-event physical block (an event
    list of length 1).
    """
    rows = [(i, f"r{i}", 0, [], [1] * n, 1.0) for i, n in enumerate(loss_counts)]
    return [dict(event=f"ev_{packed_len}_{sum(loss_counts)}",
                packed_len=packed_len, rows=rows)]


class TestPickCostBlocks(unittest.TestCase):
    """(a) Ticket 10 spec 16.5/16.9: hand-build 6 small events (blocks), `cost`'s three
    block-picking rules -- most tokens (ties broken by more loss positions), most loss
    positions (different block from the former), and the third block computed from
    `n_tok/max_n_tok + n_loss_pos/max_n_loss_pos`."""

    def test_tiebreak_and_third_block(self):
        blk_losspos_max = _mk_block(64, [60])          # One row, long target: most loss positions
        blk_tokens_tie_low = _mk_block(320, [2] * 8)    # Many rows, long prefix: tied on tokens (fewer loss positions)
        blk_tokens_tie_high = _mk_block(320, [5] * 8)   # Same token count, more loss positions
        blk_cost_max = _mk_block(288, [11] * 5)         # Highest combined score
        blk_filler1 = _mk_block(48, [5])
        blk_filler2 = _mk_block(32, [3])

        blocks = [blk_losspos_max, blk_tokens_tie_low, blk_tokens_tie_high,
                 blk_cost_max, blk_filler1, blk_filler2]
        picks = dict(tcs._pick_cost_blocks(blocks))

        self.assertEqual(set(picks),
                         {"max_tokens_block", "max_losspos_block", "max_cost_block"})
        self.assertIs(picks["max_tokens_block"], blk_tokens_tie_high,
                      "when token counts tie, should take the block with more loss positions")
        self.assertIs(picks["max_losspos_block"], blk_losspos_max)
        self.assertIsNot(picks["max_tokens_block"], picks["max_losspos_block"])
        self.assertIs(picks["max_cost_block"], blk_cost_max)
        self.assertNotIn(picks["max_cost_block"],
                         (picks["max_tokens_block"], picks["max_losspos_block"]))


class TestRunMemProbeThreeModes(unittest.TestCase):
    """(b) Run `run_mem_probe` once for each of the three modes: `opt.state` is empty, lr
    is restored, `.grad` is all None, parameters are unchanged item-for-item (`loop`
    mode too), and `mem_probe_summary` is always written. `worst_gb`/`worst_kind` are
    verified for having discrimination using a monkeypatched `_peak_gb` (returns an
    increasing fake value on each call; the real value on CPU is always 0)."""

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

    def _run_mode(self, pick):
        events, _counts = share_data.load_events(
            self.data_path, self.tok, mode="cgen", max_len=8192, limit=0)
        self.assertGreaterEqual(len(events), 2,
                                "need at least 2 events to make up multiple physical blocks")

        torch.manual_seed(SEED)
        model = AutoModelForCausalLM.from_config(_tiny_config(len(self.tok)))
        model.train()
        orig_lr = 1e-3
        opt = torch.optim.AdamW(model.parameters(), lr=orig_lr,
                                weight_decay=0.01)
        params_before = [p.detach().clone() for p in model.parameters()]

        args = argparse.Namespace(tok_budget=100000, events_per_mb=2,
                                  accum=2, mem_probe_pick=pick)
        logged = []

        def log(**kw):
            logged.append(kw)

        counter = {"n": 0}

        def fake_peak(_dev):
            counter["n"] += 1
            return float(counter["n"])

        with patch.object(tcs, "_peak_gb", side_effect=fake_peak):
            tcs.run_mem_probe(model, opt, events, args, "cpu", log, amp=False)

        self.assertEqual(len(opt.state), 0,
                         f"{pick}: opt.state should be empty after the probe finishes")
        self.assertTrue(
            all(g["lr"] == orig_lr for g in opt.param_groups),
            f"{pick}: each param_group's lr should be restored to its original value after the probe finishes")
        self.assertTrue(
            all(p.grad is None for p in model.parameters()),
            f"{pick}: every parameter's .grad should be None after the probe finishes")
        for p0, p1 in zip(params_before, model.parameters()):
            self.assertTrue(torch.equal(p0, p1),
                            f"{pick}: parameters are bit-for-bit unchanged before and after the probe")

        mem_events = [e for e in logged if e.get("event") == "mem_probe"]
        summaries = [e for e in logged if e.get("event") == "mem_probe_summary"]
        self.assertTrue(mem_events, f"{pick}: should write at least one mem_probe event")
        self.assertEqual(len(summaries), 1,
                         f"{pick}: should write exactly one mem_probe_summary")
        summary = summaries[0]
        self.assertEqual(summary["pick"], pick)

        max_peak = max(e["peak_mem_gb"] for e in mem_events)
        max_kind = next(e["kind"] for e in mem_events
                        if e["peak_mem_gb"] == max_peak)
        self.assertEqual(summary["worst_gb"], max_peak,
                         f"{pick}: worst_gb should equal the max of each block's peak_mem_gb")
        self.assertEqual(summary["worst_kind"], max_kind,
                         f"{pick}: worst_kind should match the kind with the largest peak")

    def test_tokens(self):
        self._run_mode("tokens")

    def test_cost(self):
        self._run_mode("cost")

    def test_loop(self):
        self._run_mode("loop")


class TestMemProbeRngRestorationViaMain(unittest.TestCase):
    """(c) Run the small model's `main()` once with `--mem-probe --mem-probe-pick cost
    --device cpu --lora` and once without `--mem-probe` (still `--lora`) (both with
    `--smoke --max-events 6 --log-every 1`); the `loss` values of the `step` events in
    the two `train_log.jsonl` files match entry for entry -- the random-number state is
    restored around the probe (spec 16.5, silent-failure point #31), and LoRA dropout's
    random stream is unaffected (dropout is 0 when the small model doesn't carry LoRA,
    so there's no discrimination there)."""

    def test_loss_identical_with_and_without_mem_probe(self):
        try:
            import peft  # noqa: F401
        except ImportError as e:
            self.skipTest(f"peft not installed: {e}")
        if not Path(QWEN_PATH).exists():
            self.skipTest(f"tokenizer path does not exist: {QWEN_PATH}")
        if not TRAIN_PATH.exists() or not VAL_PATH.exists():
            self.skipTest(f"live data does not exist: {DATA_DIR}")

        tok = AutoTokenizer.from_pretrained(QWEN_PATH)
        vocab_size = len(tok)
        with tempfile.TemporaryDirectory() as model_dir, \
                tempfile.TemporaryDirectory() as out_root:
            torch.manual_seed(SEED)
            model = AutoModelForCausalLM.from_config(_tiny_config(vocab_size))
            model.save_pretrained(model_dir)
            tok.save_pretrained(model_dir)

            def _run(name, extra_args):
                out = Path(out_root) / name
                argv = ["train_causal_share.py", "--mode", "cgen",
                       "--base", model_dir, "--data", str(DATA_DIR),
                       "--out", str(out), "--smoke", "--max-events", "6",
                       "--log-every", "1", "--device", "cpu",
                       "--align-events", "2", "--lora"] + extra_args
                old_argv = sys.argv
                sys.argv = argv
                try:
                    tcs.main()
                finally:
                    sys.argv = old_argv
                losses = []
                for line in open(out / "train_log.jsonl"):
                    r = json.loads(line)
                    if r["event"] == "step":
                        losses.append(r["loss"])
                return losses

            loss_with_probe = _run(
                "with_probe", ["--mem-probe", "--mem-probe-pick", "cost"])
            loss_without_probe = _run("without_probe", [])

            self.assertTrue(loss_with_probe, "no step events at all")
            self.assertEqual(loss_with_probe, loss_without_probe,
                             "the training part of a run with and without the probe should be bit-for-bit identical "
                             "(the random-number state is restored before and after the probe)")


def _row(event, sent_idx, n_sents, text, label, label_call, w=1.0):
    """Hand-build one training-sample row (following the same-named helper function in `tests/test_eval_overlong.py`)."""
    return dict(event=event, sent_idx=sent_idx, n_sents=n_sents, text=text,
               label=label, label_call=label_call, w=w)


class TestMemProbePickTokensReadonlyEnvReloadsFull(unittest.TestCase):
    """Final-review F2 regression test: when `--mem-probe-pick tokens` and
    `--readonly-env` are both on, `tr_events` is loaded with `ro=ro_tr` (non-read-only
    rows dropped whole-row), not the full training set -- the criterion
    `(not args.smoke) and args.max_events == 0` for "tr_events is already the full set"
    must also require `args.readonly_env is None`, otherwise the probe would treat the
    filtered subset as the full set while still tagging it `scope="full"`.

    Build a hand-made small dataset with only two events, each exactly one row (spec
    16.9's preamble: new cases always use hand-built small events, and do not read the
    live `pipeline/data/nyapass_aw_v1/gptoss` -- that val set is 810MB/115211 rows, and
    reading through the whole thing row by row takes 13 seconds; not passing `--smoke`
    and not giving `--max-events` is exactly what triggers the old code's condition for
    judging "tr_events is already the full set"): one event's label is the first label
    that `readonly_map.load_table("appworld")` judges read-only, the other is the first
    label it judges not read-only -- once `--readonly-env appworld` is on, the non-read-
    only event's only row is dropped whole-row, `tr_events` is left with only 1 event,
    no longer the full set. Verify this directly with `share_data.load_events`'s call
    record: whether the probe should load the full set separately is judged by whether
    this one `ro=None` call happened, not by the numbers in the training result.
    """

    def test_readonly_env_forces_reload_even_when_limit_zero(self):
        try:
            import peft  # noqa: F401
        except ImportError as e:
            self.skipTest(f"peft not installed: {e}")
        if not Path(QWEN_PATH).exists():
            self.skipTest(f"tokenizer path does not exist: {QWEN_PATH}")

        ro_table = readonly_map.load_table("appworld")
        ro_label = next(k for k, v in ro_table.items() if v["readonly"])
        nro_label = next(k for k, v in ro_table.items() if not v["readonly"])

        rows = [
            _row("ev_ro", 0, 1, "Please show the requested listing now.",
                ro_label, f"{ro_label}()"),
            _row("ev_nro", 0, 1, "Please submit the final answer now.",
                nro_label, f"{nro_label}()"),
        ]

        with tempfile.TemporaryDirectory() as data_dir_s, \
                tempfile.TemporaryDirectory() as model_dir, \
                tempfile.TemporaryDirectory() as out_root:
            data_dir = Path(data_dir_s)
            for split in ("train.jsonl", "val.jsonl"):
                with open(data_dir / split, "w") as f:
                    for r in rows:
                        f.write(json.dumps(r) + "\n")

            tok = AutoTokenizer.from_pretrained(QWEN_PATH)
            torch.manual_seed(SEED)
            model = AutoModelForCausalLM.from_config(_tiny_config(len(tok)))
            model.save_pretrained(model_dir)
            tok.save_pretrained(model_dir)

            ro_calls = []
            orig_load_events = share_data.load_events

            def _spy_load_events(*a, **kw):
                ro_calls.append(kw.get("ro"))
                return orig_load_events(*a, **kw)

            out = Path(out_root) / "run"
            # Deliberately not passing --smoke, not passing --max-events (default 0): this is
            # exactly the old code's condition `(not args.smoke) and args.max_events == 0` for
            # judging "tr_events is already the full set", and it only exposes F2 combined with
            # --readonly-env.
            argv = ["train_causal_share.py", "--mode", "cgen",
                   "--base", model_dir, "--data", str(data_dir),
                   "--out", str(out), "--align-events", "2",
                   "--device", "cpu", "--lora", "--mem-probe",
                   "--mem-probe-pick", "tokens",
                   "--readonly-env", "appworld"]
            old_argv = sys.argv
            with patch.object(share_data, "load_events",
                             side_effect=_spy_load_events):
                sys.argv = argv
                try:
                    tcs.main()
                finally:
                    sys.argv = old_argv

        # In main(), when --readonly-env is on, load_events is called 4 times: the alignment
        # check (run_align_check loads a separate small sample to cross-check internally,
        # ro=ro_new), tr_events (ro=ro_tr), ev_events (ro=ro_ev) -- these three all carry
        # a non-None ro; when `--mem-probe-pick tokens` and `--readonly-env` are both on,
        # it must load the full set once more, and this last call must pass ro=None --
        # falling back to the old logic (taking tr_events directly as the full set) means
        # load_events would only be called those first 3 times, never a 4th.
        self.assertEqual(len(ro_calls), 4,
                         "when readonly_env is on, mem-probe-pick=tokens must "
                         "reload the full set again (load_events should be called 4 times: "
                         "alignment check/train/val/mem-probe full set)")
        self.assertTrue(all(c is not None for c in ro_calls[:-1]),
                        f"the first 3 calls should all carry a non-None ro: {ro_calls[:-1]}")
        self.assertIsNone(ro_calls[-1],
                         "the last call (reloading the mem-probe full set) must pass ro=None, "
                         "must not reuse tr_events filtered by readonly")


if __name__ == "__main__":
    unittest.main()
