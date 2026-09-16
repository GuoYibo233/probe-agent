"""tests/test_eval_overlong.py -- spec `.scratch/kvshare-train/spec.md` 16.9
item 1, corresponding to ticket `.scratch/kvshare-train/issues/07-eval-overlong.md`.

How to run (share_data.py/eval_tool.py both need torch at the top level,
`train_causal_tool` has a transformers>=5.14 version gate at the top level, so
the whole file needs cprobe-env):
  cprobe-env/bin/python -m unittest tests.test_eval_overlong -v
When system python3 runs the full discover, this module is skipped entirely (no
torch), which doesn't count as a failure; under mbert-env (transformers 4.57.6)
importing train_causal_tool/eval_tool raises SystemExit (the top-level
transformers>=5.14 version gate), which is also caught and skipped the same way
(following the pattern in tests/test_ctool_readpos.py).

When the real Qwen3-0.6B-Base tokenizer path doesn't exist, the test cases that
touch it call skipTest. All test cases hand-build small events/small models and
don't read the live data directory under pipeline/data/.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline/train"))
sys.path.insert(0, str(ROOT / "pipeline/eval"))

try:
    import torch
    import transformers
    import share_data
    from transformers import AutoModel, AutoModelForCausalLM, AutoTokenizer
except ImportError as e:                       # system python3 doesn't have torch
    raise unittest.SkipTest(f"needs the cprobe-env interpreter: {e}")

try:
    import train_causal_tool                    # noqa: E402
except ImportError as e:                        # system python3 doesn't have transformers
    raise unittest.SkipTest(f"needs the cprobe-env interpreter: {e}")
except SystemExit as e:                         # mbert-env's transformers<5.14
    raise unittest.SkipTest(f"needs the cprobe-env interpreter: {e}")

try:
    import eval_tool                            # noqa: E402
except ImportError as e:
    raise unittest.SkipTest(f"needs the cprobe-env interpreter: {e}")
except SystemExit as e:
    raise unittest.SkipTest(f"needs the cprobe-env interpreter: {e}")

try:
    import eval_causal_call                     # noqa: E402
    import eval_causal_param                    # noqa: E402
except ImportError as e:
    raise unittest.SkipTest(f"needs the cprobe-env interpreter: {e}")

QWEN_PATH = train_causal_tool.MODELS["qwen"]


def _row(event, sent_idx, n_sents, text, label, label_call, w=1.0):
    return dict(event=event, sent_idx=sent_idx, n_sents=n_sents, text=text,
               label=label, label_call=label_call, w=w)


def _write_jsonl(rows, path):
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _grow_until(tok, base, min_tokens):
    """Repeatedly concatenate `base` until the token count > `min_tokens` (following test_share_data.py)."""
    s = base
    while len(tok(s, add_special_tokens=False)["input_ids"]) <= min_tokens:
        s = s + " " + base
    return s


def _tiny_causal_config(vocab_size):
    """A two-layer Qwen3, scaled down to CPU-second speed (following
    `_tiny_config` from tests/test_share_trainer.py)."""
    return transformers.Qwen3Config(
        hidden_size=64, intermediate_size=128, num_hidden_layers=2,
        num_attention_heads=4, num_key_value_heads=2, head_dim=16,
        vocab_size=vocab_size, max_position_embeddings=8192,
        tie_word_embeddings=False)


class TestNFullTokensMatchesLoadEvents(unittest.TestCase):
    """(a) `n_full_tokens`/`full_token_ids` use the same number as `load_events`'s
    `dropped_events` criterion, consistent."""

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"tokenizer path does not exist: {QWEN_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)

    def test_matches_load_events_drop(self):
        short_text = "Please handle this request right now quickly."
        max_len = len(self.tok(short_text,
                              add_special_tokens=False)["input_ids"]) + 5
        long_full_text = _grow_until(self.tok, "word", max_len + 20)

        rows = [
            _row("ev_normal", 0, 1, short_text,
                "apis.a.call", "apis.a.call(x=1)"),
            _row("ev_long", 0, 1, long_full_text,
                "apis.a.call", "apis.a.call(x=1)"),
        ]
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "data.jsonl")
            _write_jsonl(rows, path)
            events, counts = share_data.load_events(
                path, self.tok, mode="cgen", max_len=max_len, limit=0)

        self.assertEqual(counts["dropped_events"], 1)
        kept = {e["event"] for e in events}
        self.assertIn("ev_normal", kept)
        self.assertNotIn("ev_long", kept)

        # On the same span of text, n_full_tokens's drop criterion is consistent with load_events's
        self.assertGreater(share_data.n_full_tokens(self.tok, long_full_text),
                           max_len)
        self.assertLessEqual(
            share_data.n_full_tokens(self.tok, short_text), max_len)
        # full_token_ids and n_full_tokens are two outputs of the same tokenization pass
        self.assertEqual(
            len(share_data.full_token_ids(self.tok, long_full_text)),
            share_data.n_full_tokens(self.tok, long_full_text))


class TestSelectKeys(unittest.TestCase):
    """(b) The counts and the set of keys kept for `share_data.select_keys`'s
    three modes, plus the exclusion behavior when `excluded_rows` is given (an
    event with some rows excluded is kept, an event with all candidate rows
    excluded is dropped and counted into `n_excluded_by_ctool`). Doesn't need a
    real tokenizer/model -- purely hand-built dict input.
    """

    def setUp(self):
        # e1/e2/e4's prompt length doesn't exceed the threshold; e3 exceeds it (counted
        # as left-truncated in left/drop-event, excluded entirely in skip); e2's event
        # full text exceeds max_len (drop-event only); e4 has only some candidate rows
        # excluded by ctool (kept); e5's only candidate row is entirely excluded by
        # ctool (the whole key is dropped, counted into n_excluded_by_ctool).
        self.keys = {"e1": [0, 1], "e2": [2, 3], "e3": [4],
                    "e4": [5, 6], "e5": [7]}
        self.n_full = {"e1": 100, "e2": 5000, "e3": 50, "e4": 10, "e5": 10}
        self.prompt_len = {"e1": 30, "e2": 30, "e3": 90, "e4": 10, "e5": 10}
        self.excluded_rows = {5, 7}     # e4 excludes one row and keeps one; e5's only candidate row is excluded
        self.max_len = 100
        self.max_new = 20               # thresh = 80

    def _call(self, mode):
        return share_data.select_keys(
            mode, self.keys, self.n_full, self.prompt_len,
            self.excluded_rows, self.max_len, self.max_new)

    def test_left(self):
        kept, counts = self._call("left")
        self.assertEqual(kept, ["e1", "e2", "e3", "e4"])
        self.assertEqual(counts, dict(n_left_truncated=1, n_skipped_rows=0,
                                      n_dropped_events=0,
                                      n_excluded_by_ctool=1))

    def test_skip(self):
        kept, counts = self._call("skip")
        self.assertEqual(kept, ["e1", "e2", "e4"])
        self.assertEqual(counts, dict(n_left_truncated=0, n_skipped_rows=1,
                                      n_dropped_events=0,
                                      n_excluded_by_ctool=1))

    def test_drop_event(self):
        kept, counts = self._call("drop-event")
        self.assertEqual(kept, ["e1", "e3", "e4"])
        self.assertEqual(counts, dict(n_left_truncated=1, n_skipped_rows=0,
                                      n_dropped_events=1,
                                      n_excluded_by_ctool=1))

    def test_bad_mode(self):
        with self.assertRaises(ValueError):
            share_data.select_keys("bogus", self.keys, self.n_full,
                                   self.prompt_len, self.excluded_rows,
                                   self.max_len, self.max_new)


class TestCparamPromptLenMaxRule(unittest.TestCase):
    """(b addendum) cparam test case: a key's true-label/predicted-tool prompt
    token counts differ, only the pred_tool one exceeds `max_len - max_new`.
    `L(k)` takes the max of the two (the same inline algorithm from
    `eval_causal_param.py`'s main(); here it's copied verbatim to verify that
    algorithm, without running the whole main() that needs a model run
    directory).
    """

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"tokenizer path does not exist: {QWEN_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)

    def test_max_of_two_tags(self):
        gt_text = "short prompt with the true tool name"
        len_gt = len(self.tok(gt_text, add_special_tokens=False,
                             truncation=False)["input_ids"])
        max_len = len_gt + 5
        max_new = 0                      # thresh = max_len, simplifies the arithmetic
        pred_text = _grow_until(self.tok, "word", max_len)
        len_pred = len(self.tok(pred_text, add_special_tokens=False,
                               truncation=False)["input_ids"])
        self.assertLessEqual(len_gt, max_len)
        self.assertGreater(len_pred, max_len)

        keys = {"k1": [0]}
        prompt_len = {"k1": max(len_gt, len_pred)}
        excluded_rows = set()

        # skip: the max of the two prompts exceeds the threshold, the whole key is excluded (max-value rule)
        kept, counts = share_data.select_keys(
            "skip", keys, {}, prompt_len, excluded_rows, max_len, max_new)
        self.assertEqual(kept, [])
        self.assertEqual(counts["n_skipped_rows"], 1)

        # left: the key is kept, and n_left_truncated_by_tag is counted per tag
        # following the algorithm inlined in eval_causal_param.py
        kept, counts = share_data.select_keys(
            "left", keys, {}, prompt_len, excluded_rows, max_len, max_new)
        self.assertEqual(kept, ["k1"])
        self.assertEqual(counts["n_left_truncated"], 1)
        thresh = max_len - max_new
        tag_len = {"k1": {"gt_tool": len_gt, "pred_tool": len_pred}}
        n_left_truncated_by_tag = {"gt_tool": 0, "pred_tool": 0}
        for k in kept:
            for tag in ("gt_tool", "pred_tool"):
                if tag_len[k][tag] > thresh:
                    n_left_truncated_by_tag[tag] += 1
        self.assertEqual(n_left_truncated_by_tag,
                         {"gt_tool": 0, "pred_tool": 1})


class _IdentityGenerate:
    """Swap `eval_causal_call.generate` / `eval_causal_param.generate` for an
    echo: return the prompt fed in, as-is, as the "generation result". What's
    tested is the wiring for how the trigger point/candidate row gets picked,
    not whether the model actually writes the call -- a real model's output is
    uncontrollable, and the echo makes the `gen` field in the report directly
    expose "exactly which line of text the prompt fed to the model contains",
    so it becomes possible to assert that the row picked is the one re-selected,
    not the original trigger row that ctool excluded.
    """

    def __call__(self, model, tok, prompts, dev, bs, max_len, max_new,
                tag=None):
        return list(prompts)


class TestCgenCtoolExclusionWiring(unittest.TestCase):
    """(b addendum 2) End-to-end wiring test for `eval_causal_call.py` (F1's
    regression test): a row excluded by ctool must not be a trigger-point
    candidate, an event whose candidate rows are all excluded is counted into
    `n_excluded_by_ctool` and not scored, and an event with only some
    candidate rows excluded must re-pick the trigger point among the remaining
    rows -- not by relying on the coincidence that "zero logits naturally fail
    to clear θ". Only hand-builds one real tokenizer plus a randomly
    initialized two-layer model, `generate` is swapped for an echo, no
    dependency on any live run directory.
    """

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"tokenizer path does not exist: {QWEN_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)

    def test_reselect_and_count_excluded(self):
        torch.manual_seed(20260828)
        model = AutoModelForCausalLM.from_config(
            _tiny_causal_config(len(self.tok)))
        model.eval()

        rows = [
            _row("ev_reselect", 0, 2, "ROW0 EXCLUDED CONFIDENT TEXT",
                "apis.a", "apis.a(x=1)"),
            _row("ev_reselect", 1, 2, "ROW1 SURVIVING TEXT",
                "apis.a", "apis.a(x=1)"),
            _row("ev_full_excl", 0, 2, "ROW2 FULL EXCL A",
                "apis.a", "apis.a(x=2)"),
            _row("ev_full_excl", 1, 2, "ROW3 FULL EXCL B",
                "apis.a", "apis.a(x=2)"),
            _row("ev_normal", 0, 1, "ROW4 NORMAL TEXT",
                "apis.a", "apis.a(x=3)"),
        ]
        for r in rows:
            r["args_named"] = []
        # row0 (excluded, logits deliberately set much higher than θ -- the rule "an
        # excluded row must not be a candidate" can't rely on θ naturally blocking it,
        # the wiring itself must block it); row1 (survives, conf just clears θ, the
        # event should re-pick this row); row2/row3 (the whole event is excluded,
        # logits are the real zero logits ctool produces, conf=0.5<θ, under the old
        # wiring events like this would never "fire" anyway, counted into neither
        # already-triggered nor n_excluded_by_ctool, vanishing silently -- this is
        # exactly the gap F1 points out); row4 (normal trigger, baseline control).
        logits = torch.tensor([
            [10.0, -10.0],
            [3.0, -3.0],
            [0.0, 0.0],
            [0.0, 0.0],
            [5.0, -5.0],
        ])
        excluded_idx = [0, 2, 3]
        theta = 0.9

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            ctool_dir, cgen_dir, data_dir = (root / "ctool", root / "cgen",
                                             root / "data")
            (ctool_dir / "best").mkdir(parents=True)
            (cgen_dir / "best").mkdir(parents=True)
            data_dir.mkdir()

            _write_jsonl(rows, data_dir / "test.jsonl")
            (ctool_dir / "best" / "label_map.json").write_text(
                json.dumps({"apis.a": 0, "apis.b": 1}))
            (ctool_dir / "best" / "meta.json").write_text(
                json.dumps({"data": str(data_dir)}))
            (ctool_dir / "REPLAY_REPORT.json").write_text(json.dumps(
                {"temperature": 1.0, "chosen_theta": {"0.05": theta}}))
            torch.save(logits, ctool_dir / "logits_test.pt")
            (ctool_dir / "logits_test.meta.json").write_text(
                json.dumps({"excluded_idx": excluded_idx}))

            self.tok.save_pretrained(cgen_dir / "best")
            model.save_pretrained(cgen_dir / "best")
            (cgen_dir / "best" / "meta.json").write_text(json.dumps(
                {"call_sep": "\n[CALL] ", "max_len": 4096,
                 "data": str(data_dir)}))

            argv = ["eval_causal_call.py", "--env", "appworld",
                   "--ctool-run", str(ctool_dir), "--cgen-run", str(cgen_dir),
                   "--data", str(data_dir), "--risk", "0.05",
                   "--device", "cpu", "--bs", "2", "--overlong", "left"]
            old_argv = sys.argv
            old_generate = eval_causal_call.generate
            try:
                sys.argv = argv
                eval_causal_call.generate = _IdentityGenerate()
                eval_causal_call.main()
            finally:
                sys.argv = old_argv
                eval_causal_call.generate = old_generate

            out = json.loads((cgen_dir / "CALLGEN_REPORT.json").read_text())

        self.assertEqual(out["n_events_test"], 3)
        self.assertEqual(out["n_events_fired"], 2,
                         "both rows of ev_full_excl are zero logits, should not count as fired")
        self.assertEqual(out["n_excluded_by_ctool"], 1)
        self.assertEqual(out["n_events_scored"], 2)

        by_event = {s["event"]: s for s in out["samples"]}
        self.assertIn("ev_reselect", by_event)
        self.assertNotIn("ev_full_excl", by_event)
        gen = by_event["ev_reselect"]["gen"]
        self.assertIn("ROW1 SURVIVING TEXT", gen,
                     "the fire point should be re-picked to the remaining row")
        self.assertNotIn("ROW0 EXCLUDED CONFIDENT TEXT", gen,
                         "rows dropped by ctool must not be fire-point candidates, no matter how confident "
                         "their logits are")


class TestCparamCtoolExclusionWiring(unittest.TestCase):
    """(b addendum 3) End-to-end wiring test for `eval_causal_param.py` (F2's
    regression test), isomorphic to `TestCgenCtoolExclusionWiring`."""

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"tokenizer path does not exist: {QWEN_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)

    def test_reselect_and_count_excluded(self):
        torch.manual_seed(20260828)
        model = AutoModelForCausalLM.from_config(
            _tiny_causal_config(len(self.tok)))
        model.eval()

        rows = [
            _row("ev_reselect", 0, 2, "ROW0 EXCLUDED CONFIDENT TEXT",
                "apis.a", "apis.a(x=1)"),
            _row("ev_reselect", 1, 2, "ROW1 SURVIVING TEXT",
                "apis.a", "apis.a(x=1)"),
            _row("ev_full_excl", 0, 2, "ROW2 FULL EXCL A",
                "apis.a", "apis.a(x=2)"),
            _row("ev_full_excl", 1, 2, "ROW3 FULL EXCL B",
                "apis.a", "apis.a(x=2)"),
            _row("ev_normal", 0, 1, "ROW4 NORMAL TEXT",
                "apis.a", "apis.a(x=3)"),
        ]
        for r in rows:
            r["args_named"] = []
        logits = torch.tensor([
            [10.0, -10.0],
            [3.0, -3.0],
            [0.0, 0.0],
            [0.0, 0.0],
            [5.0, -5.0],
        ])
        excluded_idx = [0, 2, 3]
        theta = 0.9

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            ctool_dir, cparam_dir, data_dir = (root / "ctool",
                                               root / "cparam", root / "data")
            (ctool_dir / "best").mkdir(parents=True)
            (cparam_dir / "best").mkdir(parents=True)
            data_dir.mkdir()

            _write_jsonl(rows, data_dir / "test.jsonl")
            (ctool_dir / "best" / "label_map.json").write_text(
                json.dumps({"apis.a": 0, "apis.b": 1}))
            (ctool_dir / "best" / "meta.json").write_text(
                json.dumps({"data": str(data_dir)}))
            (ctool_dir / "REPLAY_REPORT.json").write_text(json.dumps(
                {"temperature": 1.0, "chosen_theta": {"0.05": theta}}))
            torch.save(logits, ctool_dir / "logits_test.pt")
            (ctool_dir / "logits_test.meta.json").write_text(
                json.dumps({"excluded_idx": excluded_idx}))

            self.tok.save_pretrained(cparam_dir / "best")
            model.save_pretrained(cparam_dir / "best")
            (cparam_dir / "best" / "meta.json").write_text(json.dumps(
                {"call_sep": "\n[CALL] ", "max_len": 4096,
                 "data": str(data_dir), "param_only": True}))

            argv = ["eval_causal_param.py", "--env", "appworld",
                   "--ctool-run", str(ctool_dir),
                   "--cparam-run", str(cparam_dir),
                   "--data", str(data_dir), "--risk", "0.05",
                   "--device", "cpu", "--bs", "2", "--overlong", "left"]
            old_argv = sys.argv
            old_generate = eval_causal_param.generate
            try:
                sys.argv = argv
                eval_causal_param.generate = _IdentityGenerate()
                eval_causal_param.main()
            finally:
                sys.argv = old_argv
                eval_causal_param.generate = old_generate

            out = json.loads((cparam_dir / "PARAM_REPORT.json").read_text())

        self.assertEqual(out["n_events_test"], 3)
        self.assertEqual(out["n_events_fired"], 2,
                         "both rows of ev_full_excl are zero logits, should not count as fired")
        self.assertEqual(out["n_excluded_by_ctool"], 1)
        self.assertEqual(out["n_events_scored"], 2)

        by_event = {s["event"]: s for s in out["gt_tool"]["samples"]}
        self.assertIn("ev_reselect", by_event)
        self.assertNotIn("ev_full_excl", by_event)
        gen = by_event["ev_reselect"]["gen"]
        self.assertIn("ROW1 SURVIVING TEXT", gen,
                     "the fire point should be re-picked to the remaining row")
        self.assertNotIn("ROW0 EXCLUDED CONFIDENT TEXT", gen,
                         "rows dropped by ctool must not be fire-point candidates, no matter how confident "
                         "their logits are")


class TestCgenDropEventFullTextUsesRawRows(unittest.TestCase):
    """Final-review F1 regression test: when `--overlong drop-event` takes the
    event's full text, it must use share_data's rule (don't filter rows by the
    ctool vocabulary, take the `text` of the row with the largest `sent_idx`),
    not the ctool-filtered `rows`. Hand-builds one event: the row with the
    largest `sent_idx` has a label not in the ctool vocabulary (it would get
    filtered out by `label in label2id`), and only counting this row's full
    text pushes it over `max_len` -- using the wrong convention (the filtered
    `rows`) misses this row and wrongly judges it as not overlong; fixed
    correctly (using `raw_rows`) it correctly drops the whole event.
    """

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"tokenizer path does not exist: {QWEN_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)

    def test_event_with_out_of_vocab_last_row_gets_dropped(self):
        torch.manual_seed(20260829)
        model = AutoModelForCausalLM.from_config(
            _tiny_causal_config(len(self.tok)))
        model.eval()

        short_text_a = "Please handle this quick request now."
        short_text_b = "This is a different short event text."
        max_len = len(self.tok(short_text_a,
                              add_special_tokens=False)["input_ids"]) + 20
        # Only by counting in the full text of the sent_idx=1 row (label not in the
        # vocabulary) does the event's full text exceed max_len; after vocabulary
        # filtering, the remaining sent_idx=0 full text is far below max_len.
        long_full_text = _grow_until(self.tok, "word", max_len + 20)

        rows = [
            # ev_drop's trigger point (sent_idx=0, label in the vocabulary, will be
            # judged fired): the full text itself isn't long, and with the wrong
            # convention the event's full text equals just this row, so overlong can't be
            # detected.
            _row("ev_drop", 0, 2, short_text_a, "apis.a", "apis.a(x=1)"),
            # The row with the largest sent_idx has a label not in the ctool vocabulary,
            # so `label in label2id` filters the whole row out -- but share_data's rule
            # requires the full-text convention to see this row.
            _row("ev_drop", 1, 2, long_full_text, "apis.zzz", "apis.zzz(x=1)"),
            # baseline control: a normal short event, shouldn't be dropped under drop-event.
            _row("ev_keep", 0, 1, short_text_b, "apis.a", "apis.a(x=2)"),
        ]
        for r in rows:
            r["args_named"] = []
        # After filtering only two rows remain, ev_drop's sent_idx=0 and ev_keep's
        # sent_idx=0, in the same order as in raw_rows; both rows are given high
        # confidence so both can fire.
        logits = torch.tensor([
            [10.0, -10.0],
            [10.0, -10.0],
        ])
        theta = 0.9

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            ctool_dir, cgen_dir, data_dir = (root / "ctool", root / "cgen",
                                             root / "data")
            (ctool_dir / "best").mkdir(parents=True)
            (cgen_dir / "best").mkdir(parents=True)
            data_dir.mkdir()

            _write_jsonl(rows, data_dir / "test.jsonl")
            (ctool_dir / "best" / "label_map.json").write_text(
                json.dumps({"apis.a": 0, "apis.b": 1}))
            (ctool_dir / "best" / "meta.json").write_text(
                json.dumps({"data": str(data_dir)}))
            (ctool_dir / "REPLAY_REPORT.json").write_text(json.dumps(
                {"temperature": 1.0, "chosen_theta": {"0.05": theta}}))
            torch.save(logits, ctool_dir / "logits_test.pt")

            self.tok.save_pretrained(cgen_dir / "best")
            model.save_pretrained(cgen_dir / "best")
            (cgen_dir / "best" / "meta.json").write_text(json.dumps(
                {"call_sep": "\n[CALL] ", "max_len": max_len,
                 "data": str(data_dir)}))

            argv = ["eval_causal_call.py", "--env", "appworld",
                   "--ctool-run", str(ctool_dir), "--cgen-run", str(cgen_dir),
                   "--data", str(data_dir), "--risk", "0.05",
                   "--device", "cpu", "--bs", "2", "--overlong", "drop-event",
                   "--max-new-tokens", "0"]
            old_argv = sys.argv
            old_generate = eval_causal_call.generate
            try:
                sys.argv = argv
                eval_causal_call.generate = _IdentityGenerate()
                eval_causal_call.main()
            finally:
                sys.argv = old_argv
                eval_causal_call.generate = old_generate

            out = json.loads((cgen_dir / "CALLGEN_REPORT.json").read_text())

        self.assertEqual(out["n_dropped_events"], 1)
        self.assertEqual(out["n_events_fired"], 2,
                         "both events' fire rows got high confidence, both should fire")
        self.assertEqual(out["n_events_scored"], 1,
                         "ev_drop should be dropped by drop-event, leaving only ev_keep to be scored")
        by_event = {s["event"]: s for s in out["samples"]}
        self.assertNotIn("ev_drop", by_event,
                         "the row with the largest sent_idx (label not in vocab) has overlong full text, "
                         "the event should be dropped -- using the wrong settings (filtered rows) would miss this row")
        self.assertIn("ev_keep", by_event)


class TestScoreCausalOverlong(unittest.TestCase):
    """(c) Under all three modes of `eval_tool.score_causal`, `out` has the same row count
    as the input, `excluded_idx` and the counts match, and excluded rows have all-zero
    logits. Small model: a two-layer backbone from a randomly initialized `Qwen3Config`
    + one linear head (following `tests/test_share_trainer.py`'s approach).
    """

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"tokenizer path does not exist: {QWEN_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)
        if cls.tok.pad_token_id is None:
            cls.tok.pad_token = cls.tok.eos_token
        cls.tok.truncation_side = "left"
        cls.tok.padding_side = "right"

        torch.manual_seed(20260828)
        cls.backbone = AutoModel.from_config(
            _tiny_causal_config(len(cls.tok))).eval()
        cls.head = torch.nn.Linear(64, 3)
        cls.head.weight.data.zero_()
        cls.head.bias.data = torch.tensor([1.0, 2.0, 3.0])

        # ev1: after the early segment is left-truncated it falls outside the window (row0's
        # boundary is inside early), the tail segment (row1 = the full text) stays inside the
        # window; full's token count exceeds max_len, so under drop-event the whole event gets
        # dropped. ev2: a short event, always inside the window.
        # The early/late/max_len/early_cut construction is copied from
        # tests/test_ctool_readpos.py's TestScoreCausalOutOfWindow, already verified to
        # reliably trigger left-truncation-out-of-window.
        early = "zero one two three four five six seven eight nine ten. "
        late = ("eleven twelve thirteen fourteen fifteen sixteen seventeen "
               "eighteen nineteen twenty twenty-one twenty-two twenty-three "
               "twenty-four twenty-five twenty-six twenty-seven twenty-eight.")
        cls.full = early + late
        n_late = len(cls.tok(late, add_special_tokens=False)["input_ids"])
        n_full_total = len(
            cls.tok(cls.full, add_special_tokens=False)["input_ids"])
        cls.max_len = n_late
        assert cls.max_len < n_full_total, "construction does not meet the precondition for left truncation"
        cls.early_cut = 3                       # Falls inside early; after left-truncation it is definitely outside the window

        cls.short_text = "a short normal event that fits easily"
        assert share_data.n_full_tokens(cls.tok, cls.short_text) < cls.max_len

        cls.rows = [
            dict(event="ev1", sent_idx=0, text=cls.full[:cls.early_cut]),
            dict(event="ev1", sent_idx=1, text=cls.full),
            dict(event="ev2", sent_idx=0, text=cls.short_text),
        ]

    def test_left(self):
        out, excluded_idx, counts = eval_tool.score_causal(
            self.backbone, self.head, self.tok, self.rows, "cpu",
            self.max_len, bs=2, overlong="left")
        self.assertEqual(out.shape[0], len(self.rows))
        self.assertEqual(excluded_idx, [])
        self.assertGreaterEqual(counts["n_oow"], 1)
        self.assertEqual(counts["n_skipped_bounds"], 0)
        self.assertEqual(counts["n_dropped_events"], 0)
        self.assertEqual(counts["n_dropped_bounds"], 0)
        self.assertEqual(out[0].abs().sum().item(), 0.0)   # Outside the window: zero logits
        self.assertTrue(torch.equal(out[1], self.head.bias.detach()))
        self.assertTrue(torch.equal(out[2], self.head.bias.detach()))

    def test_skip(self):
        out, excluded_idx, counts = eval_tool.score_causal(
            self.backbone, self.head, self.tok, self.rows, "cpu",
            self.max_len, bs=2, overlong="skip")
        self.assertEqual(out.shape[0], len(self.rows))
        self.assertEqual(excluded_idx, [0])
        self.assertEqual(counts["n_skipped_bounds"], 1)
        self.assertGreaterEqual(counts["n_oow"], 1)
        self.assertEqual(counts["n_dropped_events"], 0)
        self.assertEqual(out[0].abs().sum().item(), 0.0)   # Excluded: zero logits
        self.assertTrue(torch.equal(out[2], self.head.bias.detach()))

    def test_drop_event(self):
        out, excluded_idx, counts = eval_tool.score_causal(
            self.backbone, self.head, self.tok, self.rows, "cpu",
            self.max_len, bs=2, overlong="drop-event")
        self.assertEqual(out.shape[0], len(self.rows))
        self.assertEqual(excluded_idx, [0, 1])
        self.assertEqual(counts["n_dropped_events"], 1)
        self.assertEqual(counts["n_dropped_bounds"], 2)
        self.assertEqual(counts["n_oow"], 0)
        self.assertEqual(counts["n_skipped_bounds"], 0)
        self.assertEqual(out[0].abs().sum().item(), 0.0)
        self.assertEqual(out[1].abs().sum().item(), 0.0)
        self.assertTrue(torch.equal(out[2], self.head.bias.detach()))

    def test_bad_overlong(self):
        with self.assertRaises(ValueError):
            eval_tool.score_causal(self.backbone, self.head, self.tok,
                                   self.rows, "cpu", self.max_len, bs=2,
                                   overlong="bogus")


class TestCachedLogitsOverlongModeGuard(unittest.TestCase):
    """(d) `--cached-logits` path: if the cached `overlong_mode` differs from this run's
    `--overlong`, raise `SystemExit`. Under the causal head, `--cached-logits` does not
    load model weights; it only needs the tokenizer (real Qwen), `label_map.json`,
    `meta.json`, two sets of hand-built jsonl, and hand-built `logits_*.pt`/`.meta.json`.
    """

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"tokenizer path does not exist: {QWEN_PATH}")

    def test_mode_mismatch_hard_stops(self):
        tok = AutoTokenizer.from_pretrained(QWEN_PATH)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            run = root / "run"
            data = root / "data"
            (run / "best").mkdir(parents=True)
            data.mkdir()
            tok.save_pretrained(run / "best")
            (run / "best" / "label_map.json").write_text(
                json.dumps({"apis.a": 0, "apis.b": 1}))
            (run / "best" / "meta.json").write_text(
                json.dumps({"max_len": 64, "base": "qwen-tiny"}))

            def _rows(n, prefix):
                return [dict(event=f"{prefix}{i}", sent_idx=0,
                           text=f"event {prefix}{i} text", label="apis.a")
                       for i in range(n)]

            val_rows, test_rows = _rows(2, "v"), _rows(2, "t")
            _write_jsonl(val_rows, data / "val.jsonl")
            _write_jsonl(test_rows, data / "test.jsonl")

            torch.save(torch.zeros(2, 2), run / "logits_val.pt")
            (run / "logits_val.meta.json").write_text(json.dumps(
                {"weights": {}, "rows": 2, "overlong_mode": "left",
                 "excluded_idx": []}))
            torch.save(torch.zeros(2, 2), run / "logits_test.pt")
            (run / "logits_test.meta.json").write_text(json.dumps(
                {"weights": {}, "rows": 2, "overlong_mode": "skip",
                 "excluded_idx": []}))

            argv = ["eval_tool.py", "--env", "appworld", "--run", str(run),
                   "--data", str(data), "--head", "causal",
                   "--cached-logits", "--overlong", "left", "--device", "cpu"]
            old_argv = sys.argv
            try:
                sys.argv = argv
                with self.assertRaises(SystemExit):
                    eval_tool.main()
            finally:
                sys.argv = old_argv


class TestMbertOverlongGuard(unittest.TestCase):
    """(e) Passing `--head mbert` with a `--overlong` value other than `left` must raise
    `SystemExit` -- this check happens after argument parsing but before any file access,
    so it can be tested even with `--run`/`--data` pointing at paths that don't exist."""

    def test_mbert_rejects_non_left(self):
        argv = ["eval_tool.py", "--env", "appworld", "--run", "/no/such/run",
               "--data", "/no/such/data", "--head", "mbert",
               "--overlong", "skip"]
        old_argv = sys.argv
        try:
            sys.argv = argv
            with self.assertRaises(SystemExit):
                eval_tool.main()
        finally:
            sys.argv = old_argv


if __name__ == "__main__":
    unittest.main()
