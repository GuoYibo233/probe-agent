# T08 report — add generative evaluation back into the new trainer: `--gen-eval N` (default 200) and `--gen-bs`

Ticket: `.scratch/kvshare-train/issues/08-gen-eval.md`
Spec: `.scratch/kvshare-train/spec.md` 16.3 (approach), 16.9 (tests), 16.10 #29 #30 (silent failure points)
Branch: `ticket/2026-08-28-wave5/T08` (worktree `new1-wt/2026-08-28-wave5-T08`, deleted, branch kept)
base: `07907db08b50d66c1c193588f22b5cc97b24b4b3`
head: `b8a31f2` (`375acf5` → `05ca1b3` → `b8a31f2`)

## 1. What was done (checked against the ticket, item by item)

### 1. `share_data.load_events` row tuple gets a 6th slot

- cgen branch: `tgt_str = r["label_call"]`, `tool = None` (the cgen branch did not
  have a `tgt_str` variable before; it tokenized `r["label_call"]` directly and added
  eos, now it just stores that string into a variable name first before passing it to
  `tok(...)`, the tokenization logic itself is unchanged).
- cparam branch: `tool = r["label"]` (`tgt_str` is already an existing variable; rows
  where `param_target` returns None are still dropped entirely and counted into
  `assembly_mismatch`; this check happens before the `tool` assignment, the order is
  unchanged).
- `rows.append(...)` gets `gen = dict(tgt=tgt_str, tool=tool)` appended as the 6th
  slot; slots 0 through 5 (`sent_idx, text, p, seg_ids, seg_lab, w`) are untouched.
- The six-name unpacking in `pack_event`, `_sent_idx, _text, p, seg_ids, seg_lab, _w =
  row`, is changed to `= row[:6]`, so a 7-slot tuple no longer raises `ValueError`.
- Lines 214/215 of `share_data.py` (`prefix_len`/`packed_len` read `row[2]`/`row[3]` by
  index) and lines 179/470/789 of `train_causal_share.py` (read `row[5]`/`row[1]` by
  index) access by index; behavior is unchanged under a 7-slot tuple, so they are left
  untouched.
- The docstring's description of the `rows` tuple shape is updated to match.

### 2. Places in the tests that hand-build row tuples get the 6th slot added

- `tests/test_share_data.py`: the 3 rows in `_toy_event()` and the single hand-built
  `ev_b` row in `test_batch_mask` each get a `dict(tgt="", tool=None)` placeholder
  added (neither of these two spots tests generative evaluation, the placeholder value
  does not affect the existing assertions).
- In `tests/test_share_data.py`, `TestPrefixRule._check_mode`'s six-name unpacking of
  the real `share_data.load_events` return value,
  `for sent_idx, text, p, seg_ids, seg_lab, w in ev["rows"]:`, is changed to seven
  names (adding `_gen`) — the ticket did not name this line, but it unpacks the real
  `load_events` output, and once the row tuple becomes 7 slots it would raise
  `ValueError` if left unchanged, so it was fixed along the way.
- `tests/test_share_trainer.py`: the lines around 374/437/495 named by the ticket are
  actually `W = sum(row[5] for ev in events for row in ev["rows"])` — read by index,
  not a hand-built tuple; behavior is unchanged under a 7-slot tuple, so after
  checking, this file was not changed (details in the section 4 self-check).

### 3. Three parameters added to `train_causal_share.py`

`--gen-eval` (int, default 200, 0 disables it), `--gen-bs` (int, default 8),
`--gen-eval-at` (`choices=["all","last"]`, default `last`), all three placed right
after `--log-every`.

### 4. Sampling: `sample_gen_eval_rows(events, mode, seed, n)`

Called right after `ev_events` finishes loading (before the `readonly_env` audit
block), flattened into a single list in event-load order with rows in each event's
`sent_idx` order (no filtering), then `random.Random(seed).shuffle` and take the first
`n` rows (if `n` is larger than the row count, take all of them, handled naturally by
Python slicing), then packed by `mode`: cgen `(text, None, None, tgt)`, cparam
`(text, None, None, tool, tgt)` (`tgt`/`tool` come from the `gen` dict at slot 6 of the
row tuple). `seed` uses `SEED = train_causal_callgen.SEED` (=42, same as the old
trainer). A pure function kept independent of main(), for ease of unit testing.

### 5. Generation: calls the old script's `eval_gen`, no new function written

`grep -n "def eval_gen" pipeline/train/train_causal_share.py` has zero hits — it calls
`train_causal_callgen.eval_gen` or `train_causal_param.eval_gen` depending on
`args.mode`, and the two old functions handle
`padding_side`/`use_cache`/`model.eval()`/`model.train()` themselves. The call site
sits after `eval_ce` and before the `eval` event is written, not inside the
`_attn_ctx` context (the guard test in item 7 pins this down).

### 6. Logging

- `eval` event: `val_exact_call` (cgen) / `val_exact_params` (cparam), `gen_n`
  (`len(gen_rows)`), `gen_s` (`round(elapsed seconds, 2)`) are only added when
  `do_gen = args.gen_eval > 0 and (args.gen_eval_at == "all" or frac == E)` holds;
  when it does not hold (`--gen-eval 0`, or an evaluation point that is not the end of
  an epoch under `--gen-eval-at last`), none of the three keys are written.
- The `start` event gets three keys added, `gen_eval`, `gen_bs`, `gen_eval_at`, placed
  after the `log_every` key (see the section 4 note "the ticket's two requirements do
  not fully agree with each other").
- The `save_best` criterion is untouched, it still only looks at `val_ce`.
- The `train_s` timing code (`epoch_train_s += time.time() - t0`) is not touched,
  generation time is not counted into it.

### 7. Evaluation-segment heartbeat

`eval_ce` gets an optional parameter `beat=None`, called once inside the block loop
`for i, blk in enumerate(blocks):` when `(i + 1) % 25 == 0`; the call site in the main
flow passes `beat=lambda: heartbeat.emit(gstep, steps, "step")`; when `do_gen` is
true, the same heartbeat is emitted once more each, before and after calling
`eval_gen`. `heartbeat.emit` only takes the three positional arguments
`(gstep, steps, "step")`, no other keyword is passed.

### 8. Tests (new file `tests/test_share_gen_eval.py`)

Not appended to `test_share_trainer.py` (tickets 09/10 running in parallel and adding
cases to the end of the same file would collide). Everything uses hand-built small
events (one row per event, `label`/`label_call` matching each other so both cgen and
cparam load cleanly) and a randomly initialized small model (`_tiny_config`, imported
from `tests.test_share_trainer`); it does not read
`pipeline/data/nyapass_aw_v1/gptoss` (per the spec 16.9 preamble). The real tokenizer
is only used to tokenize / build the model vocabulary.

- `TestGenEvalEndToEnd` (corresponds to (a)(b)): 12 training events + 6 val events,
  `--events-per-mb 4 --accum 2 --eval-per-epoch 2` gives two different evaluation
  points (`frac=1` and `frac=2`). Three cases each for cgen/cparam: under
  `--gen-eval-at all` both `eval` entries have the three new keys and `gen_n==3`;
  under `--gen-eval-at last` only the `frac==2` entry has them; under `--gen-eval 0`
  neither entry has them.
- `TestSampleGenEvalRowsDeterministic` (corresponds to (c)): calling
  `sample_gen_eval_rows` twice on the same batch of `events` gives the same result
  (one case each for cgen/cparam); another case verifies that when `n` is larger than
  the row count, all rows are taken.
- `TestAttnCtxOnlyInForwardPacked` (corresponds to (d)): parses the
  `train_causal_share.py` source with `ast`, walks the `Call` nodes to find
  `_attn_ctx(...)`, records the name of the nearest enclosing `FunctionDef` for each
  call, and asserts they are all `_forward_packed` (the `def _attn_ctx` line itself is
  a `FunctionDef`, not a `Call`, so it is not counted).
- `TestEvalCeBeat` (corresponds to (e)): 30 val events, `tok_budget` takes "the
  smallest padded length among all events" — this way `cand_max` for any two events is
  always `>= tok_budget`, so `2 * pad16(cand_max) > tok_budget` always holds,
  guaranteeing that each event becomes its own physical block on its own (30 blocks
  >= 25); asserts that `beat` is called at least once. Another case verifies that
  `beat=None` (the default) does not raise an error.

## 2. How it was verified

```
cd new1-wt/2026-08-28-wave5-T08
/home/y-guo/reproduce/new1/cprobe-env/bin/python -m unittest \
  tests.test_share_gen_eval tests.test_share_trainer tests.test_share_data
```
Output: `Ran 33 tests in 20.219s` / `OK (skipped=9)` (the skips are branches that need
the real tokenizer path, which does not exist, or that need `peft`, which is not
installed; the same reason as before the change).

Running just the new file (`-v`) is also all green:
```
Ran 12 tests in 19.488s
OK
```

```
grep -n "gen_eval\|val_exact_" pipeline/train/train_causal_share.py
```
Hits the `sample_gen_eval_rows` definition, the `gen_rows` assignment,
`gen_eval`/`gen_bs`/`gen_eval_at` inside `start_kw`, the `do_gen` condition, and three
occurrences of `exact_key`.

```
grep -n "def eval_gen" pipeline/train/train_causal_share.py
```
Zero hits (exit code 1).

The exact command from the ticket's acceptance checklist, using the real `--base
qwen` 0.6B backbone and the real in-service dataset
`pipeline/data/nyapass_aw_v1/gptoss`, run on CPU:
```
cprobe-env/bin/python pipeline/train/train_causal_share.py --mode cgen \
  --base qwen --data pipeline/data/nyapass_aw_v1/gptoss \
  --out <out> --smoke --max-events 6 --gen-eval 3 --gen-bs 2 --device cpu
```
`ALIGN_CHECK.json`: `PASS: true` (`max_abs_diff` 2.38e-06, `tol` 2e-05).
The `eval` event in `train_log.jsonl`:
```
{'event': 'eval', 'ep': 0, 'frac': 4, 'gstep': 1, 'val_ce': 1.2026,
 'n_eval_rows': 18, 'val_exact_call': 0.0, 'gen_n': 3, 'gen_s': 3.38,
 't': 1787923369.9}
```
All three new keys (`val_exact_call`, `gen_n`, `gen_s`) are present, and
`gen_n == 3` matches the `--gen-eval 3` passed in. In the `start` event, all three
keys `gen_eval: 3, gen_bs: 2, gen_eval_at: 'last'` are present. The `done` event
shows `wall_s: 13.91` (training + evaluation itself is fast; most of the time goes
into the alignment check before training starts — doing an fp32 forward pass with
the real 0.6B model on CPU, code this ticket did not change, which took on the order
of ten-odd minutes in the process, unrelated to this ticket's changes).

`git status --porcelain` (inside the worktree) shows only:
```
 M pipeline/train/share_data.py
 M pipeline/train/train_causal_share.py
 M tests/test_share_data.py
?? tests/test_share_gen_eval.py
```
`run.py`, `train_causal_callgen.py`, `train_causal_param.py` are not touched.

## 3. Commit list

- `375acf5` T08: share_data row tuple gets a 6th-slot gen dict, pack_event unpacking adapted
- `05ca1b3` T08: train_causal_share adds --gen-eval/--gen-bs/--gen-eval-at
- `b8a31f2` T08: self-check fix — remove the unused random import in test_share_gen_eval.py

## 4. Self-check findings and open questions

1. **Two requirements inside the ticket do not fully agree with each other;
   implemented per the more complete one, noted here for the closeout review to
   decide**: ticket item 2 says "this ticket adds two keys, `gen_eval / gen_bs`, to
   the `start_kw` dict" (only mentions two), item 5 says "the `start` event adds
   `gen_eval`, `gen_bs`, `gen_eval_at`" (three). The spec 16.3 source text also only
   writes two keys. None of the three tests (item 7) check the exact field count of
   the `start` event, so neither implementation would turn the acceptance criteria
   red. I implemented per item 5 (the more complete one, which specifically covers
   the logging fields), adding all three keys `gen_eval`, `gen_bs`, `gen_eval_at`
   into `start_kw` — if gyb's intent was to add only two (for example leaving
   `gen_eval_at` for elsewhere, or not logging it), this one spot needs to be
   changed during the main session's closeout review (one line after the
   `log_every=args.log_every,` line in `train_causal_share.py`).
2. Ticket item 1 named the lines around 374/437/495 in `tests/test_share_trainer.py`
   as "hand-built row tuples" that need the 6th slot added; after checking, these
   three spots are `row[5]` (reading the real `load_events` output by index), not
   hand-built tuples, and behavior is unaffected under a 7-slot tuple, so this file
   was not changed. Confirmed by running `tests.test_share_trainer` all green.
3. Under `--smoke`, running the alignment check with the real 0.6B `--base qwen`
   model on CPU is slow (fp32, two passes of `REF_BATCH=4` and a `bs=1` single-row
   baseline, plus `_new_forward`; CPU has no GPU acceleration, and the `bs=1` pass
   runs a full model forward pass once per row) — measured, this segment took on
   the order of ten-odd minutes before printing the first line of
   `ALIGN_CHECK.json` — this is `run_align_check`'s existing logic (this ticket did
   not change this code), not new overhead introduced by this change. After it
   finished, `PASS: true`, and the three new keys are all present in
   `train_log.jsonl`; results are in section 2.
