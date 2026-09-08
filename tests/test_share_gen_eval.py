"""tests/test_share_gen_eval.py -- (a)(b)(c)(d)(e) of ticket 08 in spec
`.scratch/kvshare-train/spec.md` section 16.9, corresponding to ticket
`.scratch/kvshare-train/issues/08-gen-eval.md`.

Not appended to the end of `tests/test_share_trainer.py` (tickets 09 and 10 run in
parallel, and three tickets appending cases to the same file's end would collide);
the small-model construction is imported from that file's existing `_tiny_config`
helper function. Preface to spec 16.9: new test cases always use hand-built small
events and a randomly initialized small model, never read a live large directory
like `pipeline/data/nyapass_aw_v1/gptoss` (one case reading through val once takes
over ten minutes) -- this file uses hand-built jsonl throughout, the real tokenizer
is used only for tokenizing.

How to run (needs cprobe-env, `import train_causal_share` has a top-level
transformers>=5.14 version gate):
  cprobe-env/bin/python -m unittest tests.test_share_gen_eval -v
When system python3 runs the full discover, this module is skipped entirely (no
torch), which does not count as a failure; under mbert-env (transformers 4.57.6),
it is caught and skipped the same way (following `tests/test_cparam_assembly.py`
lines 21 to 29 and `tests/test_share_trainer.py`'s approach).

When the real Qwen3-0.6B-Base tokenizer path does not exist, the test cases that
touch it call `skipTest`.
"""
import ast
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

from tests.test_share_trainer import _tiny_config  # noqa: E402

QWEN_PATH = train_causal_callgen.MODELS["qwen"]
SEED = 20260729          # The test fixture's own fixed seed, same as tests/test_share_trainer.py


def _mk_row(event, i, n_sents=1, sent_idx=0):
    """A single row of one independent small event: label/label_call match each other,
    and it loads cleanly under both cgen/cparam modes (cparam's `param_target` does
    not fail to strip). Built the same way as `tests/test_share_data.py`'s
    `_row`/`_clean_rows`."""
    label = f"apis.pad{i}.call"
    text = f"Please handle synthetic request number {i} right now completely."
    return dict(event=event, sent_idx=sent_idx, n_sents=n_sents, text=text,
               label=label, label_call=f"{label}(x=1)", w=1.0)


def _write_jsonl(rows, path):
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _make_data_dir(n_train, n_eval):
    """Hand-build a data directory of `n_train` training events + `n_eval` val events
    (each event independent, one row each), written into train.jsonl / val.jsonl
    in a temporary directory."""
    tmpdir = tempfile.TemporaryDirectory()
    data_dir = Path(tmpdir.name)
    train_rows = [_mk_row(f"tr{i}", i) for i in range(n_train)]
    eval_rows = [_mk_row(f"ev{i}", 1000 + i) for i in range(n_eval)]
    _write_jsonl(train_rows, data_dir / "train.jsonl")
    _write_jsonl(eval_rows, data_dir / "val.jsonl")
    return tmpdir, data_dir


def _make_model_dir(tok):
    tmpdir = tempfile.TemporaryDirectory()
    model_dir = Path(tmpdir.name)
    torch.manual_seed(SEED)
    model = AutoModelForCausalLM.from_config(_tiny_config(len(tok)))
    model.save_pretrained(model_dir)
    tok.save_pretrained(model_dir)
    return tmpdir, model_dir


class TestGenEvalEndToEnd(unittest.TestCase):
    """(a) `--gen-eval 3 --gen-bs 2 --gen-eval-at all --eval-per-epoch 2` runs through,
    every `eval` event has the three generative-evaluation keys, `gen_n == 3`; with
    `--gen-eval-at last`, only the entry with `frac == 2` has them. (b) With
    `--gen-eval 0`, `eval` events do not have these three keys.

    12 training events (`--events-per-mb` default 4, `--accum` default 2) give
    M=ceil(12/4)=3, U=ceil(3/2)=2, and under `--eval-per-epoch 2`, eval_points is
    `{1: 1, 2: 2}` -- two evaluation points with two different fracs, which is what
    separates the all/last difference. 6 val events (one row each) are enough for
    `--gen-eval 3` to sample from.
    """

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"tokenizer path does not exist: {QWEN_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)

    def _run(self, mode, extra_argv, out_name):
        data_tmp, data_dir = _make_data_dir(n_train=12, n_eval=6)
        model_tmp, model_dir = _make_model_dir(self.tok)
        try:
            with tempfile.TemporaryDirectory() as out_root:
                out = Path(out_root) / out_name
                argv = ["train_causal_share.py", "--mode", mode,
                       "--base", str(model_dir), "--data", str(data_dir),
                       "--out", str(out), "--max-events", "12",
                       "--eval-per-epoch", "2", "--log-every", "1",
                       "--device", "cpu", "--align-events", "2"] + extra_argv
                old_argv = sys.argv
                sys.argv = argv
                try:
                    tcs.main()
                finally:
                    sys.argv = old_argv
                events = []
                for line in open(out / "train_log.jsonl"):
                    events.append(json.loads(line))
                return events
        finally:
            data_tmp.cleanup()
            model_tmp.cleanup()

    def _eval_events(self, events):
        return [e for e in events if e["event"] == "eval"]

    def _check_mode_all(self, mode):
        exact_key = "val_exact_call" if mode == "cgen" else "val_exact_params"
        events = self._run(mode, ["--gen-eval", "3", "--gen-bs", "2",
                                  "--gen-eval-at", "all"], "run_all")
        evals = self._eval_events(events)
        self.assertEqual({e["frac"] for e in evals}, {1, 2},
                         f"should have two eval points, frac=1 and frac=2: {evals}")
        for e in evals:
            self.assertIn(exact_key, e, f"missing {exact_key}: {e}")
            self.assertEqual(e["gen_n"], 3, f"gen_n should be 3: {e}")
            self.assertIn("gen_s", e, f"missing gen_s: {e}")

    def _check_mode_last(self, mode):
        exact_key = "val_exact_call" if mode == "cgen" else "val_exact_params"
        events = self._run(mode, ["--gen-eval", "3", "--gen-bs", "2",
                                  "--gen-eval-at", "last"], "run_last")
        evals = self._eval_events(events)
        self.assertEqual({e["frac"] for e in evals}, {1, 2})
        by_frac = {e["frac"]: e for e in evals}
        self.assertNotIn(exact_key, by_frac[1],
                         f"under gen-eval-at last, frac=1 (not epoch end) should not have "
                         f"{exact_key}: {by_frac[1]}")
        self.assertNotIn("gen_n", by_frac[1])
        self.assertNotIn("gen_s", by_frac[1])
        self.assertIn(exact_key, by_frac[2],
                      f"under gen-eval-at last, frac=2 (epoch end) should have "
                      f"{exact_key}: {by_frac[2]}")
        self.assertEqual(by_frac[2]["gen_n"], 3)
        self.assertIn("gen_s", by_frac[2])

    def _check_mode_off(self, mode):
        exact_key = "val_exact_call" if mode == "cgen" else "val_exact_params"
        events = self._run(mode, ["--gen-eval", "0"], "run_off")
        evals = self._eval_events(events)
        self.assertTrue(evals)
        for e in evals:
            self.assertNotIn(exact_key, e, f"--gen-eval 0 should not have {exact_key}: {e}")
            self.assertNotIn("gen_n", e)
            self.assertNotIn("gen_s", e)

    def test_cgen_all(self):
        self._check_mode_all("cgen")

    def test_cgen_last(self):
        self._check_mode_last("cgen")

    def test_cgen_off(self):
        self._check_mode_off("cgen")

    def test_cparam_all(self):
        self._check_mode_all("cparam")

    def test_cparam_last(self):
        self._check_mode_last("cparam")

    def test_cparam_off(self):
        self._check_mode_off("cparam")


class TestSampleGenEvalRowsDeterministic(unittest.TestCase):
    """(c) The sampling function tested on its own: two samples on the same batch of events give the same result."""

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"tokenizer path does not exist: {QWEN_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)

    def _events(self, mode):
        data_tmp, data_dir = _make_data_dir(n_train=1, n_eval=10)
        try:
            events, _counts = share_data.load_events(
                data_dir / "val.jsonl", self.tok, mode=mode, max_len=8192,
                limit=0)
            return events
        finally:
            data_tmp.cleanup()

    def _check_mode(self, mode):
        events = self._events(mode)
        self.assertGreaterEqual(len(events), 5)
        a = tcs.sample_gen_eval_rows(events, mode, SEED, 5)
        b = tcs.sample_gen_eval_rows(events, mode, SEED, 5)
        self.assertEqual(a, b)
        self.assertEqual(len(a), 5)

    def test_cgen(self):
        self._check_mode("cgen")

    def test_cparam(self):
        self._check_mode("cparam")

    def test_n_greater_than_rows_takes_all(self):
        events = self._events("cgen")
        n_rows = sum(len(ev["rows"]) for ev in events)
        picked = tcs.sample_gen_eval_rows(events, "cgen", SEED, n_rows + 100)
        self.assertEqual(len(picked), n_rows)


class TestAttnCtxOnlyInForwardPacked(unittest.TestCase):
    """(d) Guard test (spec 16.10 #29): call sites for `_attn_ctx(...)` are only allowed
    to fall in three places -- the forward `_forward_packed`, and the backward
    `backward_logical_minibatch` / `_fwd_bwd_block` -- never in the generation path:
    unmasked `generate` goes through GQA, and the mem-efficient kernel reports
    `No available kernel`; if someone later wraps generation into `_attn_ctx` too,
    this test catches it. Use `ast` to find `_attn_ctx`'s `Call` nodes and assert
    the enclosing function is only one of these three (the line `def _attn_ctx`
    itself is a `FunctionDef`, not a `Call`, and does not count as a call)."""

    def test_attn_ctx_called_only_inside_forward_packed(self):
        # Allowed call sites: one in the forward, two in the backward (--grad-ckpt's
        # recomputation happens inside .backward(), and must use the same kernel as the
        # forward, spec 16.10 #37); the generation path (main's evaluation section,
        # eval_gen) must never appear in this set.
        ALLOWED_ATTN_CTX_CALLERS = {"_forward_packed",
                                    "backward_logical_minibatch",
                                    "_fwd_bwd_block"}
        src_path = ROOT / "pipeline/train/train_causal_share.py"
        tree = ast.parse(src_path.read_text())

        class _Visitor(ast.NodeVisitor):
            def __init__(self):
                self.stack = []
                self.offenders = []

            def visit_FunctionDef(self, node):
                self.stack.append(node.name)
                self.generic_visit(node)
                self.stack.pop()

            def visit_Call(self, node):
                func = node.func
                name = func.id if isinstance(func, ast.Name) else None
                if name == "_attn_ctx":
                    caller = self.stack[-1] if self.stack else None
                    if caller not in ALLOWED_ATTN_CTX_CALLERS:
                        self.offenders.append((caller, node.lineno))
                self.generic_visit(node)

        v = _Visitor()
        v.visit(tree)
        self.assertEqual(
            v.offenders, [],
            "spec 16.10 #29: _attn_ctx(...) can only be called in the forward (_forward_packed) and backward "
            "(backward_logical_minibatch / _fwd_bwd_block, #37: checkpoint recompute must use the same "
            "kernel) -- unmasked model.generate goes through enable_gqa, the mem-efficient "
            f"kernel reports No available kernel. Found a call site outside those functions: {v.offenders}")


class TestEvalCeBeat(unittest.TestCase):
    """(e) `eval_ce`'s `beat` callback is called at least once when the block count >= 25.

    30 independent single-row small events, with `tok_budget` set exactly tight
    enough to fit only one event (one event's padded length is a multiple of 16, and
    the sum of two events' padded lengths necessarily exceeds this budget), so each
    event becomes its own physical block, giving 30 physical blocks.
    """

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"tokenizer path does not exist: {QWEN_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)

    def test_beat_called_when_at_least_25_blocks(self):
        data_tmp, data_dir = _make_data_dir(n_train=1, n_eval=30)
        model_tmp, model_dir = _make_model_dir(self.tok)
        try:
            events, _counts = share_data.load_events(
                data_dir / "val.jsonl", self.tok, mode="cgen", max_len=8192,
                limit=0)
            self.assertGreaterEqual(len(events), 25)
            torch.manual_seed(SEED)
            model = AutoModelForCausalLM.from_config(_tiny_config(len(self.tok)))
            model.eval()
            # tok_budget = the smallest padded length among all events: no pair of events'
            # cand_max can be smaller than this value, so 2 * pad16(cand_max) necessarily
            # exceeds tok_budget -- no matter how these 30 events' packed_len is distributed,
            # no two of them fit into the same block, guaranteeing each event becomes its own
            # physical block (30 blocks).
            pads = [((ev["packed_len"] + 15) // 16) * 16 for ev in events]
            tok_budget = min(pads)

            calls = []
            with torch.no_grad():
                tcs.eval_ce(model, events, tok_budget, "cpu", amp=False,
                           beat=lambda: calls.append(1))
            self.assertGreaterEqual(len(calls), 1,
                                    "when block count >= 25, beat should be called at least once")
        finally:
            data_tmp.cleanup()
            model_tmp.cleanup()

    def test_beat_none_does_not_crash(self):
        """`beat=None` (the default) does not affect existing call sites -- no error when it is not passed."""
        data_tmp, data_dir = _make_data_dir(n_train=1, n_eval=3)
        try:
            events, _counts = share_data.load_events(
                data_dir / "val.jsonl", self.tok, mode="cgen", max_len=8192,
                limit=0)
            torch.manual_seed(SEED)
            model = AutoModelForCausalLM.from_config(_tiny_config(len(self.tok)))
            model.eval()
            with torch.no_grad():
                vce = tcs.eval_ce(model, events, 100000, "cpu", amp=False)
            self.assertIsInstance(vce, float)
        finally:
            data_tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
