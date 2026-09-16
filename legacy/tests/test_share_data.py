"""tests/test_share_data.py -- spec `.scratch/kvshare-train/spec.md` section 12
(a) through (e), corresponding to ticket `.scratch/kvshare-train/issues/01-share-data.md`.

How to run (share_data.py imports torch at the top level, so it needs cprobe-env):
  cprobe-env/bin/python -m unittest tests.test_share_data -v
When system python3 runs the full discover, this module is skipped entirely (no
torch), which does not count as a failure; under mbert-env (transformers 4.57.6),
the two legacy training scripts that `load_events` uses raise `SystemExit` (the
top-level transformers>=5.14 version gate), and this is caught the same way and
skipped -- the `read_position` standalone hard-gate check belongs to the ticket
acceptance check, not to this unittest.

When the real Qwen3-0.6B-Base tokenizer path does not exist, or the val set does
not exist, the test cases that touch them call `skipTest` (this does not affect
the rest of the cases).
"""
import json
import random as _random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline/train"))

try:
    import torch
    import share_data
except ImportError as e:                       # System python3 has no torch
    raise unittest.SkipTest(f"needs the cprobe-env interpreter: {e}")

try:
    from train_causal_callgen import (CALL_SEP, MAX_TGT_TOK, MODELS,  # noqa: E402
                                      SEED)
    from train_causal_param import (ASSEMBLY_MISMATCH_LIMIT,          # noqa: E402
                                    param_prompt_tail, param_target)
    from transformers import AutoTokenizer                            # noqa: E402
except ImportError as e:                       # System python3 has no transformers
    raise unittest.SkipTest(f"needs the cprobe-env interpreter: {e}")
except SystemExit as e:                        # mbert-env's transformers<5.14
    raise unittest.SkipTest(f"needs the cprobe-env interpreter: {e}")

QWEN_PATH = MODELS["qwen"]
VAL_PATH = ROOT / "pipeline/data/nyapass_aw_v1/gptoss/val.jsonl"


def _write_jsonl(rows, path):
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _row(event, sent_idx, n_sents, text, label, label_call, w=1.0):
    return dict(event=event, sent_idx=sent_idx, n_sents=n_sents, text=text,
               label=label, label_call=label_call, w=w)


def _grow_until(tok, base, min_tokens):
    """Repeatedly concatenate `base` until the token count from `tok(...)` exceeds `min_tokens`.

    Driven by the tokenizer's actual measured results, not a guess at BPE merge
    behavior (the test fixture must follow the tokenizer, not our guess about it).
    """
    s = base
    while len(tok(s, add_special_tokens=False)["input_ids"]) <= min_tokens:
        s = s + " " + base
    return s


class TestPrefixRule(unittest.TestCase):
    """(a) Common-prefix rule: the real tokenizer, 20 events sampled from the val set, both cgen and cparam modes."""

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"tokenizer path does not exist: {QWEN_PATH}")
        if not VAL_PATH.exists():
            raise unittest.SkipTest(f"val set does not exist: {VAL_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)

        # Sample 20 events and write them into a temporary jsonl (following spec section 9's
        # alignment-check feed method, to avoid tokenizing the entire val set -- that is
        # something only --mem-probe does).
        raw_by_event = {}
        order = []
        with open(VAL_PATH) as f:
            for line in f:
                r = json.loads(line)
                ev = r["event"]
                if ev not in raw_by_event:
                    raw_by_event[ev] = []
                    order.append(ev)
                raw_by_event[ev].append(r)
        import random as _random
        picked = _random.Random(42).sample(order, min(20, len(order)))
        cls.raw_by_event = {ev: raw_by_event[ev] for ev in picked}
        rows = []
        for ev in picked:
            rows.extend(sorted(cls.raw_by_event[ev], key=lambda r: r["sent_idx"]))
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.tmp_path = str(Path(cls.tmpdir.name) / "twenty.jsonl")
        _write_jsonl(rows, cls.tmp_path)

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def _check_mode(self, mode):
        events, counts = share_data.load_events(
            self.tmp_path, self.tok, mode=mode, max_len=8192, limit=0)
        self.assertGreater(len(events), 0)
        n_checked = 0
        for ev in events:
            raw_rows = {r["sent_idx"]: r for r in self.raw_by_event[ev["event"]]}
            full_text = raw_rows[max(raw_rows)]["text"]
            full_ids_ground = self.tok(full_text, add_special_tokens=False,
                                       truncation=False)["input_ids"]
            for sent_idx, text, p, seg_ids, seg_lab, w, _gen in ev["rows"]:
                r = raw_rows[sent_idx]
                self.assertEqual(text, r["text"])
                if mode == "cgen":
                    tail = CALL_SEP
                    tgt_ground = self.tok(
                        r["label_call"], add_special_tokens=False
                    )["input_ids"] + [self.tok.eos_token_id]
                else:
                    tail = param_prompt_tail(r["label"])
                    tgt_str = param_target(r["label"], r["label_call"])
                    self.assertIsNotNone(tgt_str)
                    tgt_ground = self.tok(
                        tgt_str, add_special_tokens=False
                    )["input_ids"] + [self.tok.eos_token_id]
                old_ids_ground = self.tok(text + tail, add_special_tokens=False,
                                          truncation=False)["input_ids"]
                self.assertEqual(full_ids_ground[:p] + seg_ids,
                                 old_ids_ground + tgt_ground)
                n_checked += 1
        self.assertGreater(n_checked, 0)

    def test_cgen(self):
        self._check_mode("cgen")

    def test_cparam(self):
        self._check_mode("cparam")


class TestDropCounts(unittest.TestCase):
    """(b) Drop-rule counts: event-level max_len, row-level tgt length, cparam strip failure."""

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"tokenizer path does not exist: {QWEN_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)

    def _clean_rows(self, n, prefix):
        """`n` mutually unrelated short events, one row each, label/label_call matching each other."""
        rows = []
        for i in range(n):
            label = f"apis.pad{prefix}{i}.call"
            rows.append(_row(f"ev_pad_{prefix}_{i}", 0, 1,
                             f"Please do padding task number {i} now.",
                             label, f"{label}(x=1)"))
        return rows

    def test_cgen_and_cparam_drop_counts(self):
        short_text = "Please handle this request right now quickly."
        max_len = len(self.tok(short_text, add_special_tokens=False)["input_ids"]) + 5

        long_full_text = _grow_until(self.tok, "word", max_len + 20)
        long_label_call = _grow_until(
            self.tok, "apis.echo(text='abcdefgh12345678')", MAX_TGT_TOK)

        rows = self._clean_rows(30, "a")           # Dilute cparam's strip-failure rate
        rows += [
            _row("ev_small", 0, 1, short_text,
                "apis.spotify.login", "apis.spotify.login(username=x, password=y)"),
            _row("ev_long_full", 0, 1, long_full_text,
                "apis.spotify.login", "apis.spotify.login(username=x, password=y)"),
            _row("ev_long_tgt", 0, 1, short_text,
                "apis.echo", long_label_call),
            _row("ev_mismatch", 0, 1, short_text,
                "apis.echo", "apis.other_tool(a=1)"),
        ]
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "data.jsonl")
            _write_jsonl(rows, path)

            events, counts = share_data.load_events(
                path, self.tok, mode="cgen", max_len=max_len, limit=0)
            self.assertEqual(counts["dropped_events"], 1)
            self.assertEqual(counts["dropped_rows_tgt"], 1)
            self.assertEqual(counts["assembly_mismatch"], 0)
            # ev_small + ev_mismatch (cgen does not check prefix match) + 30 dilution events
            self.assertEqual(counts["n_rows"], 32)
            kept_events = {e["event"] for e in events}
            self.assertNotIn("ev_long_full", kept_events)
            self.assertNotIn("ev_long_tgt", kept_events)

            events, counts = share_data.load_events(
                path, self.tok, mode="cparam", max_len=max_len, limit=0)
            self.assertEqual(counts["dropped_events"], 1)
            self.assertEqual(counts["dropped_rows_tgt"], 1)
            self.assertEqual(counts["assembly_mismatch"], 1)
            # ev_small + 30 dilution events (ev_mismatch is dropped by the strip failure)
            self.assertEqual(counts["n_rows"], 31)

    def test_hard_stop_zero_rows(self):
        rows = [_row("ev1", 0, 1, "short text here", "apis.a", "apis.a(x=1)")]
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "data.jsonl")
            _write_jsonl(rows, path)
            with self.assertRaises(SystemExit):
                share_data.load_events(path, self.tok, mode="cgen", max_len=1)

    def test_hard_stop_assembly_mismatch_rate(self):
        rows = [_row("ev1", 0, 1, "short text here", "apis.a", "wrong_prefix(x=1)")]
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "data.jsonl")
            _write_jsonl(rows, path)
            with self.assertRaises(SystemExit):
                share_data.load_events(path, self.tok, mode="cparam", max_len=8192)


class TestChunkByBudget(unittest.TestCase):
    """(c) The budget for greedy physical-block packing and "an over-budget event becomes its own block"."""

    @staticmethod
    def _ev(name, packed_len):
        return dict(event=name, packed_len=packed_len)

    def test_greedy_budget(self):
        events = [self._ev("a", 90), self._ev("b", 40), self._ev("c", 40),
                 self._ev("d", 40), self._ev("e", 5)]
        blocks = share_data.chunk_by_budget(events, tok_budget=100)
        for blk in blocks:
            n = len(blk)
            worst = max(e["packed_len"] for e in blk)
            if n > 1:
                self.assertLessEqual(n * worst, 100)
        self.assertEqual(sum(len(b) for b in blocks), len(events))
        names = {e["event"] for blk in blocks for e in blk}
        self.assertEqual(names, {"a", "b", "c", "d", "e"})

    def test_single_event_over_budget_alone(self):
        events = [self._ev("giant", 150), self._ev("small", 50)]
        blocks = share_data.chunk_by_budget(events, tok_budget=100)
        giant_block = [b for b in blocks if any(e["event"] == "giant" for e in b)]
        self.assertEqual(len(giant_block), 1)
        self.assertEqual(len(giant_block[0]), 1)      # Becomes its own block

    def test_budget_uses_padded_length(self):
        # Two events with packed_len=161: before padding, 2*161=322<=322 (would pass); after
        # padding, L_pad=_pad16(161)=176, 2*176=352>322 (fails) -- the budget criterion must
        # use L_pad, otherwise these two events would be wrongly packed into the same block,
        # and real GPU memory/compute would exceed budget.
        events = [self._ev("x", 161), self._ev("y", 161)]
        blocks = share_data.chunk_by_budget(events, tok_budget=322)
        self.assertEqual(sorted(len(b) for b in blocks), [1, 1])   # Each becomes its own block

    def test_worst_blocks(self):
        # Hand-computed (events_per_mb=3, tok_budget=200): _pad16(100)=112,
        # _pad16(90)=96, _pad16(30)=_pad16(25)=_pad16(20)=32.
        # B=2: for descending [100,90,30,25,20], window [100,90] has L_pad=112, 2*112=224>200,
        #   not satisfied; window [90,30] has L_pad=96, 2*96=192<=200, satisfied -- B=2's best
        #   group has product=192.
        # B=3: window [100,90,30] has L_pad=112, 336>200; [90,30,25] has L_pad=96,
        #   288>200; [30,25,20] has L_pad=32, 3*32=96<=200, satisfied -- B=3's best
        #   group has product=96.
        # 192 > 96, so the fullest block is B=2's [90,30], not the one with the largest
        # packed_len, 100 (pairing with 90 would exceed budget).
        events = [self._ev("a", 100), self._ev("b", 90), self._ev("c", 30),
                 self._ev("d", 25), self._ev("e", 20)]
        longest, fullest = share_data.worst_blocks(
            events, tok_budget=200, events_per_mb=3)
        self.assertEqual(len(longest), 1)
        self.assertEqual(longest[0]["event"], "a")     # The single event with the largest packed_len
        fullest_names = {e["event"] for e in fullest}
        self.assertEqual(fullest_names, {"b", "c"})    # B=2's best group, not including a

        # For comparison: if you run chunk_by_budget directly on the full set of events (it
        # is greedy packing that "splits all events into disjoint blocks", not "search for
        # the worst combination of any B events"), and then take the block that is
        # "longest within the block", a already occupies its own block (pairing with b
        # would exceed the 200 budget), so the longest block you get is actually just the
        # single-event block {a} -- this is not the worst combination that can occur when
        # events_per_mb events are truly batched together, worst_blocks must not degenerate
        # to this result, it must be the independently searched {b, c}.
        naive_blocks = share_data.chunk_by_budget(events, tok_budget=200)
        naive_fullest = max(naive_blocks,
                            key=lambda blk: max(e["packed_len"] for e in blk))
        naive_fullest_names = {e["event"] for e in naive_fullest}
        self.assertEqual(naive_fullest_names, {"a"})
        self.assertNotEqual(fullest_names, naive_fullest_names)

    def test_worst_blocks_no_valid_group_when_budget_too_small(self):
        # When the budget cannot even fit the 2 smallest events, the fullest block returns an empty list.
        events = [self._ev("a", 100), self._ev("b", 90)]
        longest, fullest = share_data.worst_blocks(
            events, tok_budget=64, events_per_mb=4)
        self.assertEqual(longest[0]["event"], "a")
        self.assertEqual(fullest, [])

    def test_worst_blocks_empty_events(self):
        longest, fullest = share_data.worst_blocks([], tok_budget=100, events_per_mb=4)
        self.assertEqual(longest, [])
        self.assertEqual(fullest, [])


def _toy_event():
    """A hand-built 3-row small event (spec 12 (d)): P=3, full_ids uses only the first 3."""
    full_ids = [10, 11, 12, 13, 14]
    gen = dict(tgt="", tool=None)
    rows = [
        (0, "a",   1, [20, 21, 22], [-100, -100, 22], 1.0, gen),
        (1, "ab",  3, [30, 31, 32], [-100, 31, 32],   1.0, gen),
        (2, "abc", 2, [40, 41, 42], [-100, -100, 42], 1.0, gen),
    ]
    prefix_len = max(row[2] for row in rows)
    packed_len = prefix_len + sum(len(row[3]) for row in rows)
    return dict(event="toy", n_full=5, packed_len=packed_len,
               prefix_len=prefix_len, full_ids=full_ids, rows=rows)


class TestPackAndMask(unittest.TestCase):
    """(d) Mask and position_ids construction, asserted position by position on the hand-built 3-row small event."""

    def test_pack_event(self):
        ev = _toy_event()
        tokens, positions, labels, row_index, seg_bounds = share_data.pack_event(ev)
        self.assertEqual(tokens, [10, 11, 12, 20, 21, 22, 30, 31, 32, 40, 41, 42])
        self.assertEqual(positions, [0, 1, 2, 1, 2, 3, 3, 4, 5, 2, 3, 4])
        self.assertEqual(labels, [-100, -100, -100, -100, -100, 22,
                                  -100, 31, 32, -100, -100, 42])
        self.assertEqual(row_index, [-1, -1, -1, 0, 0, 0, 1, 1, 1, 2, 2, 2])
        self.assertEqual(seg_bounds, [(3, 6), (6, 9), (9, 12)])

    def test_allowed_mask(self):
        ev = _toy_event()
        allowed = share_data.allowed_mask(ev)
        self.assertEqual(tuple(allowed.shape), (12, 12))
        expect = {
            0: {0}, 1: {0, 1}, 2: {0, 1, 2},           # Causal within the prefix
            3: {0, 3}, 4: {0, 3, 4}, 5: {0, 3, 4, 5},  # Row 0: p=1
            6: {0, 1, 2, 6}, 7: {0, 1, 2, 6, 7}, 8: {0, 1, 2, 6, 7, 8},  # Row 1: p=3
            9: {0, 1, 9}, 10: {0, 1, 9, 10}, 11: {0, 1, 9, 10, 11},      # Row 2: p=2
        }
        for i in range(12):
            got = {j for j in range(12) if bool(allowed[i, j])}
            self.assertEqual(got, expect[i], f"query position {i}")

    def test_batch_mask(self):
        ev_a = _toy_event()
        # Event B: single row, P=0 (no prefix), seg_ids=[50,51], labels=[-100,51].
        ev_b = dict(event="tiny", n_full=1, packed_len=2, prefix_len=0,
                   full_ids=[], rows=[(0, "x", 0, [50, 51], [-100, 51], 1.0,
                                       dict(tgt="", tool=None))])
        packed = [share_data.pack_event(ev_a), share_data.pack_event(ev_b)]
        L_pad = 16
        input_ids, position_ids, mask, loss_idx = share_data.batch_mask(packed, L_pad)

        self.assertEqual(tuple(input_ids.shape), (2, 16))
        self.assertEqual(tuple(mask.shape), (2, 1, 16, 16))
        self.assertEqual(mask.dtype, torch.bfloat16)

        self.assertEqual(input_ids[0, :12].tolist(),
                         [10, 11, 12, 20, 21, 22, 30, 31, 32, 40, 41, 42])
        self.assertTrue((input_ids[0, 12:] == share_data.PAD_TOKEN_ID).all())
        self.assertEqual(input_ids[1, :2].tolist(), [50, 51])
        self.assertTrue((input_ids[1, 2:] == share_data.PAD_TOKEN_ID).all())

        # position_ids at pad positions keep counting up (spec section 4), not hardcoded to 0.
        # Event A's last real position is 4 (positions[-1], see test_pack_event), and the
        # 4 pad positions 12..15 keep counting: 5, 6, 7, 8.
        self.assertEqual(position_ids[0, :12].tolist(),
                         [0, 1, 2, 1, 2, 3, 3, 4, 5, 2, 3, 4])
        self.assertEqual(position_ids[0, 12:].tolist(), [5, 6, 7, 8])
        # Event B's real positions are [0, 1], and the 14 pad positions 2..15 keep counting: 2..15.
        self.assertEqual(position_ids[1, :2].tolist(), [0, 1])
        self.assertEqual(position_ids[1, 2:].tolist(), list(range(2, 16)))

        # Real tokens cannot see pad (event A's 12 real queries, columns 12..15 are all -inf).
        self.assertTrue(torch.isneginf(mask[0, 0, :12, 12:]).all())
        # A pad token, as a query, sees only itself.
        for i in range(12, 16):
            row = mask[0, 0, i]
            self.assertEqual(float(row[i]), 0.0)
            others = torch.cat([row[:i], row[i + 1:]])
            self.assertTrue(torch.isneginf(others).all())
        for i in range(2, 16):
            row = mask[1, 0, i]
            self.assertEqual(float(row[i]), 0.0)
            others = torch.cat([row[:i], row[i + 1:]])
            self.assertTrue(torch.isneginf(others).all())

        # Event B's real region ([0:2,0:2]) is purely causal (P=0, no prefix to see).
        self.assertEqual(float(mask[1, 0, 0, 0]), 0.0)
        self.assertTrue(torch.isneginf(mask[1, 0, 0, 1:2]))
        self.assertEqual(float(mask[1, 0, 1, 0]), 0.0)
        self.assertEqual(float(mask[1, 0, 1, 1]), 0.0)

        expect_loss = {
            (0, 4, 22, 0), (0, 6, 31, 1), (0, 7, 32, 1), (0, 10, 42, 2),
            (1, 0, 51, 0),
        }
        self.assertEqual(set(loss_idx), expect_loss)


class TestReadPosition(unittest.TestCase):
    """(e) Read-position rule: once with hand-built offsets, once with the real tokenizer."""

    def test_manual_read_across_cut(self):
        # case1 of the hand-built version (see the comment on the real-tokenizer case below).
        offsets = [(0, 2), (2, 7), (7, 11), (11, 13)]
        full_text = 'Spotify."\n\nWe'
        self.assertEqual(share_data.read_position(offsets, full_text, 10, 4), 2)

    def test_manual_read_backoff(self):
        offsets = [(0, 4), (4, 5), (5, 10)]
        full_text = "done. Next"
        self.assertEqual(share_data.read_position(offsets, full_text, 6, 3), 1)

    def test_manual_first_start_after_cut(self):
        offsets = [(3, 5), (5, 8), (8, 10)]
        full_text = "0123456789"
        self.assertEqual(share_data.read_position(offsets, full_text, 2, 3), -1)

    def test_manual_j_zero_backoff(self):
        offsets = [(0, 5), (5, 8)]
        full_text = "hello world"
        # cut=3: the only real token with a start position < 3 is j=0; end_j=5>3, and
        # full_text[3:5]='lo' is non-whitespace -> must fall back to j-1, and j=0 -> -1.
        self.assertEqual(share_data.read_position(offsets, full_text, 3, 2), -1)

    def test_real_tokenizer_read_across_cut(self):
        if not Path(QWEN_PATH).exists():
            self.skipTest(f"tokenizer path does not exist: {QWEN_PATH}")
        tok = AutoTokenizer.from_pretrained(QWEN_PATH)
        full_text = 'Spotify."\n\nWe'
        enc = tok(full_text, add_special_tokens=False, return_offsets_mapping=True)
        offsets = enc["offset_mapping"]
        keep = len(offsets)
        # The cut point is after the first '\n': S0 p1 o2 t3 i4 f5 y6 .7 "8 \n9 \n10 W11 e12
        cut = 10
        j = share_data.read_position(offsets, full_text, cut, keep)
        self.assertEqual(offsets[j], (7, 11))          # Covers the token for '."\n\n'

    def test_real_tokenizer_read_backoff(self):
        if not Path(QWEN_PATH).exists():
            self.skipTest(f"tokenizer path does not exist: {QWEN_PATH}")
        tok = AutoTokenizer.from_pretrained(QWEN_PATH)
        full_text = "done. Next"
        enc = tok(full_text, add_special_tokens=False, return_offsets_mapping=True)
        offsets = enc["offset_mapping"]
        keep = len(offsets)
        cut = 6                                        # After "done. "
        j = share_data.read_position(offsets, full_text, cut, keep)
        self.assertEqual(offsets[j], (4, 5))            # The token containing '.', not ' Next'

    def test_real_tokenizer_batched_padding_matches_standalone(self):
        if not Path(QWEN_PATH).exists():
            self.skipTest(f"tokenizer path does not exist: {QWEN_PATH}")
        tok = AutoTokenizer.from_pretrained(QWEN_PATH)
        tok.padding_side = "right"
        if tok.pad_token_id is None:
            tok.pad_token = tok.eos_token
        long_text = 'Spotify."\n\nWe are done here now completely finished'
        short_text = "done. Next"

        enc_solo = tok(short_text, add_special_tokens=False,
                       return_offsets_mapping=True)
        keep_solo = len(enc_solo["offset_mapping"])

        enc_batch = tok([long_text, short_text], add_special_tokens=False,
                        padding=True, return_offsets_mapping=True)
        keep_batch = int(sum(enc_batch["attention_mask"][1]))
        offsets_batch = enc_batch["offset_mapping"][1]

        self.assertEqual(keep_batch, keep_solo)
        self.assertEqual(offsets_batch[:keep_batch],
                         enc_solo["offset_mapping"][:keep_solo])

        for cut in (4, 6):
            j_solo = share_data.read_position(
                enc_solo["offset_mapping"], short_text, cut, keep_solo)
            j_batch = share_data.read_position(
                offsets_batch, short_text, cut, keep_batch)
            self.assertEqual(j_batch, j_solo)
            self.assertLess(j_batch, keep_batch)


class TestEpochMinibatches(unittest.TestCase):
    """Ticket 10 (spec 16.5, 16.9): the minibatches that `epoch_minibatches` cuts out
    match, one by one, the ones cut out by "the old hand-copied training loop"
    (train_causal_share.py lines 761 to 764 before the change) (equal event-name
    sequences) -- the blocks the probe steps on must be blocks training will
    actually encounter."""

    def test_matches_old_inline_shuffle(self):
        events = [dict(event=f"ev{i}") for i in range(23)]
        seed, ep, events_per_mb = 42, 1, 4

        old_events = list(events)                  # The old hand-copied version
        _random.Random(seed + ep).shuffle(old_events)
        old_minibatches = [old_events[i:i + events_per_mb]
                           for i in range(0, len(old_events), events_per_mb)]

        new_minibatches = share_data.epoch_minibatches(
            events, seed, ep, events_per_mb)

        self.assertEqual(
            [[e["event"] for e in mb] for mb in new_minibatches],
            [[e["event"] for e in mb] for mb in old_minibatches])

    def test_does_not_mutate_input(self):
        events = [dict(event=f"ev{i}") for i in range(9)]
        order_before = [e["event"] for e in events]
        share_data.epoch_minibatches(events, 42, 0, 4)
        self.assertEqual([e["event"] for e in events], order_before)


if __name__ == "__main__":
    unittest.main()
