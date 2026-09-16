"""tests/test_ctool_readpos.py -- items (a) through (d) of point 5 in ticket
`.scratch/kvshare-train/issues/02-ctool-drop-readpos.md`, corresponding to
sections 11 and 12 of the spec.

How to run (both train_causal_tool.py and eval_tool.py need transformers>=5.14
at the top level; only train_causal_tool.py does an explicit version gate at
the top level, eval_tool.py itself can be imported under both environments, but
this file needs train_causal_tool.collate, so the whole file needs cprobe-env):
  cprobe-env/bin/python -m unittest tests.test_ctool_readpos -v
When system python3 runs the full discover, this module is skipped entirely (no
torch), which doesn't count as a failure; under mbert-env (transformers 4.57.6)
importing train_causal_tool raises SystemExit (the top-level transformers>=5.14
version gate), which is also caught and skipped the same way, following the
pattern in tests/test_cparam_assembly.py lines 21 to 29.

When the real Qwen3-0.6B-Base tokenizer path doesn't exist, the test cases that
touch it call skipTest.
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
    import share_data
    from transformers import AutoTokenizer
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

QWEN_PATH = train_causal_tool.MODELS["qwen"]


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


class TestReadPositionManual(unittest.TestCase):
    """(a) Hand-build offsets to verify the read-position rule (directly tests share_data.read_position)."""

    def test_read_across_cut(self):
        # full[0:2]='Sp' offset(0,2); [2:7]='otify' offset(2,7);
        # [7:11]='."\n\n' offset(7,11); [11:13]='We' offset(11,13).
        # Cut point 10 falls inside the third token (covers after '\n' up to before
        # the next token), end_j=11>10 and full_text[10:11]='\n' is whitespace -> read j.
        offsets = [(0, 2), (2, 7), (7, 11), (11, 13)]
        full_text = 'Spotify."\n\nWe'
        j = share_data.read_position(offsets, full_text, 10, 4)
        self.assertEqual(j, 2)
        self.assertEqual(offsets[j], (7, 11))

    def test_backoff_to_prior_token(self):
        offsets = [(0, 4), (4, 5), (5, 10)]
        full_text = "done. Next"
        j = share_data.read_position(offsets, full_text, 6, 3)
        self.assertEqual(j, 1)
        self.assertEqual(offsets[j], (4, 5))


class TestCollateReadPosition(unittest.TestCase):
    """(a) continued: the column index that collate reads on one event with a real
    tokenizer via the new rule (share_data.read_position) matches the result of
    calling read_position directly."""

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"tokenizer path does not exist: {QWEN_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)
        if cls.tok.pad_token_id is None:
            cls.tok.pad_token = cls.tok.eos_token
        cls.tok.truncation_side = "left"
        cls.tok.padding_side = "right"

    def test_collate_matches_read_position(self):
        full = 'Spotify."\n\nWe are done here now.'
        enc = self.tok(full, add_special_tokens=False,
                       return_offsets_mapping=True)
        offsets = enc["offset_mapping"]
        cut = 10
        expected_j = share_data.read_position(offsets, full, cut, len(offsets))
        self.assertGreaterEqual(expected_j, 0)
        self.assertEqual(offsets[expected_j], (7, 11))   # the token covering '."\n\n'

        event = dict(event="ev_a", full=full, y=0, bounds=[(cut, 1.0, True)])
        enc2, rows, cols, ys, ws, lasts, dropped = train_causal_tool.collate(
            [event], self.tok, max_len=4096)
        self.assertEqual(dropped, 0)
        self.assertEqual(cols.tolist(), [expected_j])


class TestLoadEventsDropCount(unittest.TestCase):
    """(b) Event-level drop count for train_causal_tool.load_events."""

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"tokenizer path does not exist: {QWEN_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)

    def test_event_over_max_len_dropped_and_counted(self):
        short_text = "Please handle this short request right now."
        max_len = len(self.tok(short_text,
                               add_special_tokens=False)["input_ids"]) + 3
        long_text = _grow_until(self.tok, "word", max_len + 20)
        rows = [
            dict(event="ev_short", sent_idx=0, n_sents=1, text=short_text,
                label="apis.a", label_call="apis.a(x=1)", w=1.0),
            dict(event="ev_long", sent_idx=0, n_sents=1, text=long_text,
                label="apis.a", label_call="apis.a(x=1)", w=1.0),
        ]
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "data.jsonl")
            _write_jsonl(rows, path)
            label2id = {"apis.a": 0}
            events, dropped = train_causal_tool.load_events(
                path, label2id, self.tok, max_len)
            self.assertEqual(dropped, 1)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event"], "ev_short")


class _StubBackbone:
    """Only provides a correctly shaped last_hidden_state for score_causal, the
    values themselves don't factor into the check -- (c)/(d) only care about the
    column index the read position selects, not the gathered values themselves."""

    def __init__(self, hidden=4):
        self.hidden = hidden

    def __call__(self, input_ids, attention_mask, use_cache=False):
        class _Out:
            pass
        o = _Out()
        b, l = input_ids.shape
        o.last_hidden_state = torch.zeros(b, l, self.hidden)
        return o


class TestTrainEvalReadPositionAgree(unittest.TestCase):
    """(c) collate and score_causal read out the same index for the same full text
    and the same batch of cut points (events within the cap; events over the cap
    are dropped on the training side and left-truncated on the eval side, not
    covered here)."""

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"tokenizer path does not exist: {QWEN_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)
        if cls.tok.pad_token_id is None:
            cls.tok.pad_token = cls.tok.eos_token
        cls.tok.truncation_side = "left"
        cls.tok.padding_side = "right"

    def _spy(self, target_list):
        orig = share_data.read_position

        def _f(offsets, full_text, cut, keep):
            r = orig(offsets, full_text, cut, keep)
            target_list.append((cut, r))
            return r
        return _f

    def test_agree_within_max_len(self):
        full = ("Alpha beta gamma delta epsilon. " * 4
                + "Zeta eta theta iota kappa, done here now.")
        max_len = 4096
        self.assertLess(
            len(self.tok(full, add_special_tokens=False)["input_ids"]),
            max_len)                            # sanity check: confirm it's within the cap
        cut_points = [20, 45, 90, len(full)]

        train_event = dict(event="ev1", full=full, y=0,
                           bounds=[(c, 1.0, i == len(cut_points) - 1)
                                   for i, c in enumerate(cut_points)])
        eval_rows = [dict(event="ev1", sent_idx=i, text=full[:c])
                    for i, c in enumerate(cut_points)]

        orig = share_data.read_position
        calls_train, calls_eval = [], []
        try:
            share_data.read_position = self._spy(calls_train)
            train_causal_tool.collate([train_event], self.tok, max_len)
        finally:
            share_data.read_position = orig

        head = torch.nn.Linear(4, 1)
        try:
            share_data.read_position = self._spy(calls_eval)
            eval_tool.score_causal(_StubBackbone(), head, self.tok,
                                   eval_rows, "cpu", max_len, bs=1)
        finally:
            share_data.read_position = orig

        self.assertEqual(len(calls_train), len(cut_points))
        self.assertEqual(calls_train, calls_eval)
        self.assertTrue(all(j >= 0 for _c, j in calls_train))  # all within the cap


class TestScoreCausalOutOfWindow(unittest.TestCase):
    """(d) On a left-truncated event, score_causal counts out-of-window cut points into n_oow instead of putting them into cols."""

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"tokenizer path does not exist: {QWEN_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)
        if cls.tok.pad_token_id is None:
            cls.tok.pad_token = cls.tok.eos_token
        cls.tok.truncation_side = "left"
        cls.tok.padding_side = "right"

    def test_out_of_window_cut_not_in_cols(self):
        early = "zero one two three four five six seven eight nine ten. "
        late = ("eleven twelve thirteen fourteen fifteen sixteen seventeen "
               "eighteen nineteen twenty twenty-one twenty-two twenty-three "
               "twenty-four twenty-five twenty-six twenty-seven twenty-eight.")
        full = early + late
        n_full = len(self.tok(full, add_special_tokens=False)["input_ids"])
        n_late = len(self.tok(late, add_special_tokens=False)["input_ids"])
        max_len = n_late                        # guarantee left truncation, dropping the early part
        self.assertLess(max_len, n_full)

        # Zero the weights, fix the bias: any row that got gathered = bias, rows that
        # weren't gathered stay at the initialized 0 (consistent with out =
        # torch.zeros(...)), use the output itself to tell whether that cut point
        # landed in cols.
        head = torch.nn.Linear(4, 1)
        head.weight.data.zero_()
        head.bias.data.fill_(1.0)

        early_cut = 3                          # falls within early, guaranteed out of window after left truncation
        eval_rows = [
            dict(event="ev1", sent_idx=0, text=full[:early_cut]),
            dict(event="ev1", sent_idx=1, text=full),   # last row = full text, kept because it's near the tail
        ]
        out, excluded_idx, counts = eval_tool.score_causal(
            _StubBackbone(), head, self.tok, eval_rows, "cpu", max_len, bs=1)
        self.assertEqual(excluded_idx, [])               # left: doesn't exclude any row
        self.assertEqual(counts["n_oow"], 1)
        self.assertEqual(out[0, 0].item(), 0.0)          # out of window: not gathered
        self.assertEqual(out[1, 0].item(), 1.0)          # within window: gathered to bias


class TestPeakMemGb(unittest.TestCase):
    """Ticket 06 item 3: add `peak_mem_gb` to `step`/`eval` events, matching the
    convention of the new trainer `train_causal_share.py` (reads
    `max_memory_allocated` on cuda and resets the peak stats, always 0.0 on
    CPU). This file has no CPU test case that reaches a `step` event
    (`main()` needs a real tokenizer and dataset via `--base`/`--data`; the rest
    of this file's test cases call directly into the `collate`/`score_causal`
    layer), so per the fallback in ticket item 3, this only tests the function
    that writes this field, `_peak_mem_gb`, on its own."""

    def test_cpu_returns_zero(self):
        self.assertEqual(train_causal_tool._peak_mem_gb("cpu"), 0.0)

    def test_cpu_repeated_calls_stay_zero(self):
        # The CPU branch doesn't touch torch.cuda; repeated calls shouldn't accumulate or error out from "no reset".
        for _ in range(3):
            self.assertEqual(train_causal_tool._peak_mem_gb("cpu"), 0.0)


if __name__ == "__main__":
    unittest.main()
