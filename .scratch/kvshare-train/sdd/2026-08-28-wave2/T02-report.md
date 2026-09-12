# T02 Report — ctool's drop rules, defaults, read-position rule, logging

Ticket: `.scratch/kvshare-train/issues/02-ctool-drop-readpos.md`
Branch: `ticket/2026-08-28-wave2/T02` (worktree `new1-wt/2026-08-28-wave2-T02`, base `2216c44`)

## I. What was done (against each ticket item)

### 1. Drop rule (spec 11.1)

- `pipeline/train/train_causal_tool.py`'s `load_events` gained two parameters,
  `tok` and `max_len`: after grouping, the prefix-property spot check, and
  cleaning up the `rows` field, computes
  `len(tok(e["full"], add_special_tokens=False)["input_ids"])` for each event,
  drops it and counts it if it exceeds `max_len`; only then does it proceed to
  the `limit`/`spot` subset-taking logic. The return value changed from
  `events` to `(events, dropped)`.
- Both calls to `main()`, for val and train, now pass `tok, args.max_len`;
  the `start` event gained
  `dropped_events_train=dropped_events_train, dropped_events_val=dropped_events_val`.
- `truncation=True` in `collate` (originally lines 137~138) and `align_check`
  (originally lines 209~210) was changed to `truncation=False`.
- The `n_bound_dropped` field is kept, `step`/`eval` events still write it as
  before; the corresponding comment in `collate` was changed to "the count of
  cut points where a read position could not be found (n_bound_dropped),
  expected to be 0".

### 2. Defaults (spec 11.2)

- `--max-len` 4096 → 8192.
- `--accum` 8 → 2 (`--bs` stays 4, one update covers 8 events).
- `--epochs` default of 3 was left unchanged (the ticket required "unchanged").
- The top-of-module docstring's "truncation" section was rewritten as a
  "cap" section, reflecting the new behavior (no truncation, whole overlong
  events dropped, `n_bound_dropped` is now always 0 under the read-position
  convention); the argparse help for these two parameters never carried
  the numbers as literal text to begin with, so there is nothing else to
  keep in sync.

### 3. Read-position rule (spec 11.3)

- `train_causal_tool.py` gained `import share_data` at the top level
  (in the same place and the same style as `lora_util`, `readonly_map`, no
  extra `sys.path.insert` is needed because `share_data.py` is already in the
  same directory).
- In `collate`, the whole loop body that used to read
  `for t in range(keep-1, -1, -1): if 0 < ends[t] <= b: ...` was deleted and
  replaced with `j = share_data.read_position(offsets_i, full, b, keep)`;
  `keep = int(enc["attention_mask"][i].sum())` was kept and passed in as the
  fourth argument; the `if j < 0` guard (`dropped += 1`) is unchanged.
- `eval_tool.py` gained a line `import share_data` right after
  `import readonly_map` at the top level (reusing the same `sys.path.insert`).
  In `score_causal`, the same loop body was deleted and replaced with a call
  to `share_data.read_position(offsets_i, full, b, keep)`; `if j < 0: n_oow
  += 1; continue` is unchanged. `_full` was renamed to `full` (needs to be
  passed to `read_position` as `full_text`).
- `align_check` has no cut-point loop, only line 209 (at its corresponding
  position in the current file) for `truncation` was changed, sharing the
  same edit as item 1.
- `eval_tool.py`'s left truncation (`truncation=True, max_length=max_len` in
  `score_causal`) was left untouched (spec 11.5).

### 4. Logging (spec 11.4)

- The `step` event gained `lr=sch.get_last_lr()[0]`.
- The `loss` field: checked the existing implementation — `run` is cleared
  to zero after every log write (`gstep % 50 == 0`), every mini-batch's loss
  is accumulated into `run`, and it is divided by `50 * args.accum` when the
  log is written; this already is "the average of every mini-batch loss
  since the last step log, the accumulator is cleared after writing", no
  need to change the computation logic, only the new `lr` field was added.

### 5. Tests `tests/test_ctool_readpos.py`

Four classes, corresponding to ticket (a)~(d):

- `TestReadPositionManual` + `TestCollateReadPosition`: (a) hand-built
  offsets directly verify `share_data.read_position`; on the real Qwen
  tokenizer, one event verifies that the column index read out by
  `train_causal_tool.collate` agrees with the result of directly calling
  `share_data.read_position` (`'Spotify."\n\nWe are done here now.'`, cut
  point 10, expected to cover the tokens of `'."\n\n'`).
- `TestLoadEventsDropCount`: (b) one short and one long event, the long
  event's full-text token count > max_len, asserting `dropped == 1`, the
  returned event count is 1, and the one kept is the short event.
- `TestTrainEvalReadPositionAgree`: (c) the same full text, four cut points
  within the cap, each run through `train_causal_tool.collate` and
  `eval_tool.score_causal`, using monkeypatch on `share_data.read_position`
  (verified that the two modules import the same module object, via
  `train_causal_tool.share_data is eval_tool.share_data`) to record the
  `(cut, j)` sequence, asserting the two sides agree completely.
- `TestScoreCausalOutOfWindow`: (d) constructs an event whose full-text
  token count exceeds `max_len` (triggering left truncation), with one cut
  point falling in the truncated-off beginning portion and one cut point at
  the very end of the full text; `head`'s weights are zeroed and its bias
  is set to a fixed 1.0, judging directly from the output tensor itself
  whether this row was ever gathered — the out-of-window row's output is
  0.0 (never gathered), the in-window row's output is 1.0 (gathered the
  bias), corresponding to the split between the `n_oow` count and what
  `cols` collects.

`score_causal` needs real `backbone`/`head` objects to run; to avoid loading
an entire Qwen model for a purely logical test, a `_StubBackbone` was
written (it only returns an all-zero `last_hidden_state` of the correct
shape), because these tests only care about the column index selected by
the read position, not the actual values of the gathered hidden state.

## II. How it was verified

```
cd new1-wt/2026-08-28-wave2-T02
/home/y-guo/reproduce/new1/cprobe-env/bin/python -m unittest tests.test_ctool_readpos -v
```
```
Ran 6 tests in 1.144s
OK
```
(There is one `UserWarning: max_length is ignored when padding=True and there
is no truncation strategy` and one `ResourceWarning: unclosed file`, both
recorded below under "self-check findings", neither counts as a test
failure.)

```
/home/y-guo/reproduce/new1/cprobe-env/bin/python -m py_compile \
  pipeline/train/train_causal_tool.py pipeline/eval/eval_tool.py
```
```
(no output, exit code 0)
```

Hard gate (mbert-env, a real import, no try/skip fallback allowed):
```
mbert-env/bin/python -c "import sys; sys.path.insert(0,'pipeline/eval'); import eval_tool; print('ok')"
mbert-env/bin/python -c "import sys; sys.path.insert(0,'pipeline/eval'); import eval_mbert_call; print('ok')"
```
Both print `ok`, exit code 0 (each has one `FutureWarning` from transformers
itself about `TRANSFORMERS_CACHE`, unrelated to this ticket).

`git diff` scope check (acceptance item 4):
```
git diff -- pipeline/eval/eval_tool.py
```
Only two spots: adding `import share_data` at the top level; the cut-point
locating loop in `score_causal` swapped out for a call to
`share_data.read_position`. The `score` function (the mbert classification
head path), the left-truncation setting in `main()`, and so on were not
touched at all.

Full regression (confirming no new failures were introduced):
```
python3 -m unittest discover -s tests -v          # system python3
```
```
Ran 357 tests in 8.678s
FAILED (failures=1, errors=1, skipped=19)
```
The single failure (`test_no_env_reads_default_preset`) and the single error
(`test_splice_replay`) are both existing failures unrelated to this ticket —
`test_splice_replay` is a case recorded in the repo's memory as "only passes
under cprobe-env", `test_no_env_reads_default_preset` is an existing failure
already recorded in ticket 01's wrap-up report (the presets batch, not
investigated further). The newly added `test_ctool_readpos` in this file is
`skipped` as a whole module under system python3, as expected.

```
cprobe-env/bin/python -m unittest discover -s tests -v
```
```
Ran 415 tests in 11.847s
FAILED (failures=1, skipped=16)
```
The same existing failure (`test_no_env_reads_default_preset`), all 6 cases
of `test_ctool_readpos` actually ran and passed.

```
python3 run.py selfcheck
```
```
selfcheck: 74 tasks / 4 recipes / 3 presets, 16 gaps
```
All 16 gaps are gitignored interpreter/venv directories that this worktree
does not have (cprobe-env, mbert-env, envs/*, and so on), a normal
consequence of creating a new worktree, not a problem introduced by this
ticket's changes (this ticket did not touch `run.py` or the registry itself).
The task/recipe/preset counts agree with the numbers from the main repo's
most recent selfcheck record.

## III. Commit list

- `40cbd8d` T02: train_causal_tool.py gained an event-level drop rule, the
  read position now goes through share_data.read_position
- `b6a3a51` T02: eval_tool.py's score_causal read position now goes through
  share_data.read_position
- `479b887` T02: added tests tests/test_ctool_readpos.py (read position and
  drop counts)

Branch start point (base) `2216c44`, branch end (head) `479b887`.

## III-2. MAP.md text for ticket 04

Ticket acceptance item 4 requires that this ticket not touch MAP.md, and
that ticket 04 write it; given here is a suggested text based on the three
points given in the acceptance text itself (the cap 8192 drops overlong
events whole; one update covers 8 events; the read position reads across
the cut point's whitespace), for ticket 04 to adopt or rewrite:

> The cap `--max-len` defaults to 8192 (an event whose full-text token count
> exceeds the cap is dropped whole, no longer truncated, counted in
> `dropped_events_train`/`dropped_events_val`); the read-position rule uses
> `share_data.read_position`, when a cut point falls on a whitespace
> character between two tokens it reads across the cut, attributed to the
> earlier token; `--bs 4 --accum 2`, one update covers 8 events

## IV. Self-check findings and open questions

1. **The `max_length=max_len` parameter in `collate`/`align_check` no longer
   has any effect under `truncation=False`** — the HF tokenizer emits a
   one-time `UserWarning` ("max_length is ignored when padding=True and
   there is no truncation strategy"), and running the tests confirmed this
   warning does indeed appear. The ticket text only required changing
   `truncation=True` to `truncation=False`, it did not require also removing
   the now-decorative `max_length` parameter, so I only changed
   `truncation` as written literally, and recorded this observation here —
   whether to also remove these two now-decorative `max_length=max_len`
   spots in a follow-up ticket is left to the main session/a later ticket to
   decide.
2. **`tok.truncation_side = "left"` in `build()` is now also decorative** —
   because `collate`/`align_check` no longer truncate at all, this line no
   longer affects any behavior. The ticket did not name this line, it was
   not touched.
3. **`for line in open(path):` in `load_events` does not use a context
   manager** — this predates this change (not introduced by this ticket),
   and when the tests hit this path Python emits a
   `ResourceWarning: unclosed file`. Not required to be changed within this
   ticket's scope, not touched.
4. **`python3 -m unittest tests.test_ctool_readpos` (without `discover`)
   crashes with exit code 1 under mbert-env**, rather than cleanly skipping
   — this is not a problem with how this ticket's tests are written, it is
   `unittest` itself: `loadTestsFromName` (the loading path taken when a
   single module is named directly) does not treat a `SkipTest` raised
   during module import as a normal skip, only `unittest discover` correctly
   recognizes it as `ModuleSkipped` and reports `OK (skipped=N)`. Verified
   the same way one by one: `tests/test_cparam_assembly.py` and
   `tests/test_share_data.py` (the file already merged and closed out under
   ticket 01) likewise crash with exit code 1 under mbert-env when run
   directly by name with `-m unittest tests.<module>` — this is an existing
   behavior shared by these three files, not a regression introduced by this
   ticket. The ticket's acceptance text literally says "passes under both
   environments"; I verified the mbert-env side does not cause a real
   failure using discover mode (`OK (skipped=1)`) plus the two hard-gate
   import checks (`import eval_tool`/`import eval_mbert_call` printing
   `ok`); whether the test-running approach needs to change because of this
   behavior of unittest itself (for example, standardizing on discover) is
   left to the main session to decide.
5. **The `lr` in the `step` event is not `round()`-ed to four decimal
   places** — the expression the ticket text gave is exactly
   `sch.get_last_lr()[0]`, and in the same line `loss`/`ips` both have
   `round(..., 4)`; I did not add a round per the literal text, and wrote
   the raw float directly. `json.dumps` serializes it fine, this does not
   affect correctness, it is only that the displayed precision is
   inconsistent with the other fields in the same log line, recorded here
   for reference.
