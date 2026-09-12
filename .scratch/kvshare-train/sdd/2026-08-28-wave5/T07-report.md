# T07 Report: Three Ways of Handling Overlong Events on the Eval Side

Ticket: `.scratch/kvshare-train/issues/07-eval-overlong.md`
spec paragraphs: 16.2 (criteria), 16.9 item 1 (tests), 16.10 #28/#33/#34/#35 (silent failure points)
Branch: `ticket/2026-08-28-wave5/T07`, base `07907db08b50d66c1c193588f22b5cc97b24b4b3`, head `19f2c703062ea43ad17cd192f17790571d9300b6`

## I. What was done (checked against the ticket item by item)

### 1. Extracting functions in `share_data.py` (ticket item 1)

- `full_token_ids(tok, full_text)`: extracted as-is from the full-text tokenization at lines 145-147 of `load_events` (`add_special_tokens=False, truncation=False`).
- `n_full_tokens(tok, full_text)`: `return len(full_token_ids(tok, full_text))`.
- `load_events` now calls `full_token_ids` instead; behavior is byte-for-byte unchanged (same number of tokenizations, same results).
- Line 128 of `train_causal_tool.load_events` now calls `share_data.n_full_tokens(tok, e["full"])` instead, the original call did not write `truncation=False`, but the tokenizer does not truncate by default when `max_length` is not passed, so the value is unchanged.
- `event_full_texts(rows) -> dict[event] -> full_text`: groups by event, takes the `text` of the row with the largest `sent_idx`, without filtering rows, without touching the grouping in the `events_all.append(dict(...))` part of `load_events`.
- `select_keys(mode, keys, n_full, prompt_len, excluded_rows, max_len, max_new) -> (kept_keys, counts)`: see the design notes below.

The four new functions are placed after `_pad16` (line 60) and before `load_events` (originally line 73), without touching the area the ticket named as "do not touch".

### 2. Adding `--overlong` to `eval_causal_call.py` / `eval_causal_param.py` (ticket item 2)

Both scripts add `--overlong {left,skip,drop-event}`, default `left`. The three-step order is fixed: readonly exclusion (unchanged) → `--overlong` filtering (after the tokenizer loads, calling `share_data.select_keys`) → `--limit` (moved from before filtering to after filtering). `n_events_fired` is still computed before filtering, its meaning unchanged.

- The tokenization convention for `L(k)` matches `generate()` (`add_special_tokens=False, truncation=False`); cparam computes it once for each of the `gt_tool`/`pred_tool` prompt sets and takes the max.
- `drop-event` only calls `event_full_texts`/`n_full_tokens` on the events in `keys`, without tokenizing the whole set.
- Both reports (JSON+MD) add `overlong_mode` and the four counts `n_left_truncated/n_skipped_rows/n_dropped_events/n_excluded_by_ctool`; cparam additionally adds the diagnostic key `n_left_truncated_by_tag = {"gt_tool": n, "pred_tool": n}`.
- The `--self-fire` path is unchanged.

**Interface with ctool**: reads `excluded_idx` from `ctool_run/logits_test.meta.json` (an empty list if the key does not exist), groups it by event into `dict[event] -> [row_idx,...]` and passes it to `select_keys`; internally, `select_keys` checks for each key "whether all of its candidate rows were excluded by ctool"; a key with all its rows excluded is not scored and is counted into `n_excluded_by_ctool`.

### 3. Adding `--overlong` to `score_causal` and the main flow of `eval_tool.py` (ticket item 3)

`score_causal(..., overlong="left")` now returns `(out, excluded_idx, counts)` (`counts` = `n_oow/n_skipped_bounds/n_dropped_events/n_dropped_bounds`; the ticket text only wrote the two-tuple "(out, excluded_idx)"; I added `counts` as the third return value. `n_oow` and the other three mode counts all need to be written into REPLAY_REPORT, and `score_causal` is the only place that computes these numbers, so without adding this third return value there would be no way to carry these numbers out; this is a design decision I made, listed below under "self-check findings and open questions").

- `left`: unchanged, `n_oow` is only a diagnostic count.
- `skip`: out-of-window boundaries (`read_position` returns -1) go into `excluded_idx`, counted as `n_skipped_bounds`.
- `drop-event`: events where `n_full_tokens(tok, full text) > max_len` (using the ctool trainer's own rule, `rows` is already filtered by `label in label2id` in `main()`, and `items[-1][2]["text"]` is the same "filter first, then take the last row" rule) skip tokenization/forward pass entirely; all their boundaries are recorded as zero logits into `excluded_idx`. The surviving events' full text was never truncated, so `n_oow` is always 0.
- `main()` adds `--overlong`, effective only for `--head causal`; passing anything other than `left` with `--head mbert` triggers `SystemExit` directly (the check point is after argument parsing and before any file access).
- `logits_*.meta.json` gains `overlong_mode`, `excluded_idx`, and (under the causal head) the four counts `n_oow/n_skipped_bounds/n_dropped_events/n_dropped_bounds` (the latter were added by me so that `--cached-logits` can also write these numbers into REPLAY_REPORT; the ticket did not explicitly state whether these four keys should be persisted, see the open question below). The mbert head always writes `overlong_mode: "left"`, `excluded_idx: []`.
- `--cached-logits` path: reads back `overlong_mode`; if it differs from this run's `--overlong` (or the key is missing while this run is not `left`), it `SystemExit`s and states both modes; if the same, it proceeds as usual and reads back `excluded_idx`/the four counts.
- After each split (val/test) finishes loading `rows`/`logits`, rows are excluded per `excluded_idx` before being stored into `splits[sp]`. Temperature fitting, θ scanning, test freezing, stop-time calibration, depth-bucket acc, prior baseline, `token_cost`, `readonly_stats`, all downstream steps consume the data after row exclusion. `logits_*.pt` is still persisted with the full row count (excluded rows keep zero logits), so it does not affect the index-alignment assertions of cgen/cparam.
- `REPLAY_REPORT.json/.md` adds `overlong_mode` and the four counts, fixed to always take the numbers from the **test split** (the val split's `overlong_mode`/counts are also written into its own `logits_val.meta.json`, but do not go into REPLAY_REPORT. This is a choice I made; the ticket did not state which split REPLAY_REPORT's counts should come from, see the open question).

## II. How it was verified

```
$ /home/y-guo/reproduce/new1/cprobe-env/bin/python -m unittest tests.test_eval_overlong tests.test_share_data tests.test_ctool_readpos
...
Ran 39 tests in 6.410s
OK (skipped=1)
```

(The 1 skip is the test case in `tests/test_share_data.py` that needs the active `pipeline/data/nyapass_aw_v1/gptoss/val.jsonl`, that directory is gitignored, absent in the worktree, present in the main repo; this is not a regression.)

```
$ grep -n "full_token_ids\|n_full_tokens" pipeline/train/share_data.py pipeline/train/train_causal_tool.py \
    pipeline/eval/eval_tool.py pipeline/eval/eval_causal_call.py pipeline/eval/eval_causal_param.py
```
All five files match.

```
$ grep -n 'tok(e\["full_text"\]' pipeline/train/share_data.py   # zero matches
$ grep -rn "def select_keys" pipeline/                          # matches only in share_data.py, one location
```

The `--help` output of all three eval scripts lists `--overlong {left,skip,drop-event}`, default `left` (actual screenshots are in the conversation record; all three `--help` outputs carry this line).

```
$ /home/y-guo/reproduce/new1/cprobe-env/bin/python -m unittest discover -s tests
Ran 431 tests in 17.867s
FAILED (failures=1, skipped=24)
```
The only failure, `test_no_env_reads_default_preset`, is in `tests/test_preset.py`, which hardcodes the absolute path `/home/y-guo/reproduce/new1/configs/presets/default.json` for comparison; naturally it does not match under this worktree (`new1-wt/2026-08-28-wave5-T07`). Verified with `git stash`: this test case fails the same way in this worktree even with no code changes, unrelated to this ticket.

```
$ python3 run.py selfcheck
selfcheck: 76 tasks / 4 recipes / 3 presets, 16 missing
```
All 16 missing items are venv/env directories (`envs/*/venv`, `cprobe-env`, `mbert-env`, etc.); these directories are gitignored, exist only in the main repo, and are absent from the worktree. This ticket does not modify `run.py`; running the same command in the main repo gives `all present`, already verified in the main repo, not a regression.

## III. Commit list

- `74d38f6` T07: share_data extract full_token_ids/n_full_tokens/event_full_texts/select_keys
- `75e212c` T07: eval_tool.py score_causal add --overlong three states, cached-logits verification mode
- `7d2c961` T07: eval_causal_call/eval_causal_param add --overlong, wire up ctool exclusion
- `19f2c70` T07: new tests tests/test_eval_overlong.py

## IV. Self-check findings and open questions

1. **The shape of `select_keys`'s `keys` parameter is a decision I made, not copied verbatim from the ticket**. The ticket wrote `select_keys(mode, keys, n_full, prompt_len, excluded_rows, max_len, max_new)`, only saying that `n_full`/`prompt_len` are "dictionaries looked up by key" and `excluded_rows` is "the set of excluded rows passed from ctool". Item (b) in the ticket's acceptance criteria explicitly requires testing "exclusion given excluded_rows (an event with some rows excluded is kept, an event with all its candidate rows excluded is dropped and counted into n_excluded_by_ctool)." For an event to express both "some rows excluded" and "all candidate rows excluded", `keys` must carry each event's candidate row indices, it cannot be just a flat list of event ids. I defined `keys` as `dict[key] -> list[int]` (a list of candidate row indices), and inside `select_keys`, each key is checked with `all(i in excluded_rows for i in keys[k])`. At the call sites in the three eval scripts, the candidate rows in `keys_rowmap = {k: ev_row_idx[k] for k in keys}` are "all row indices of that event in `rows`", not "only up to the current firing row", that is, if an event's firing row happens to land on a row excluded by ctool, but the same event has other candidate rows that were not excluded, this implementation **still scores the event at its original firing point (`fired[k]["row"]`)**, and does not go pick a new firing point among the remaining rows. The ticket's original text, "an event picks its firing point among the remaining rows", literally requires re-picking, but re-picking needs `probs`/`theta` (neither parameter is in `select_keys`'s signature, so they are not available), and doing it properly would require changing `replay_fire` itself; given that the actual θ values used in this project are all above 0.9, far above the uniform distribution's `1/n_labels`, the scenario of "a zero-logits row happening to fire" has extremely low probability, so I chose to implement only the most concrete and testable criterion in the ticket (an event with its candidate rows entirely excluded is not scored at all), without additionally re-picking a new firing point. This is a decision I made, not a misreading of the ticket; I would like you to confirm whether this tradeoff is acceptable.
2. `score_causal` changed from a two-value return to the three-value `(out, excluded_idx, counts)`. The ticket text only wrote "(out, excluded_idx)". `counts` is the third return value I added, because the ticket requires the four numbers `n_oow`/`n_skipped_bounds`/`n_dropped_events`/`n_dropped_bounds` to be written into REPLAY_REPORT and `logits_*.meta.json`, and `score_causal` is the only place that computes them; without adding this return value there is no way to pass them out.
3. In `logits_*.meta.json`, besides `overlong_mode`/`excluded_idx`, I additionally wrote the four counts `n_oow`/`n_skipped_bounds`/`n_dropped_events`/`n_dropped_bounds` (the new keys listed in ticket item 3 were only `overlong_mode` and `excluded_idx`). This is so that the `--cached-logits` path can also carry these four numbers into REPLAY_REPORT (without doing this, a run going through the cache could not produce these counts, and would either have to leave them blank or recompute them by force, neither of which is correct). Old caches (without these four keys) are treated as 0.
4. For REPLAY_REPORT's `overlong_mode` and the four counts, I fixed them to always take the numbers from the **test split**; the val split's own numbers stay only in `logits_val.meta.json` and do not go into REPLAY_REPORT. The ticket did not state which split to take (the existing fields like `probe_cost_test`/`n_events_test` already follow a test-only naming convention, and I followed the same convention).
5. Under `--overlong skip/drop-event`, the `val` split (used for temperature fitting and θ scanning) also has rows excluded by the same rule (rather than this taking effect only on the test split). The ticket's description of the criteria is concentrated in the section about interfacing with ctool's test split, and does not explicitly say whether the val split should be handled the same way; I think that if it is not handled, the zero-logits rows remaining in the val split would contaminate temperature fitting and θ scanning, which contradicts the problem `--overlong` is meant to solve (zero logits should not be taken at face value), so I made both splits go through the same exclusion logic.
6. To keep the `score_causal` signature change from breaking existing tests, I changed two call sites in `tests/test_ctool_readpos.py` (this file was not listed in the ticket's file-scope list). This is the necessary consequence of adding together the ticket's own required acceptance command (`tests.test_ctool_readpos` must pass) and the `score_causal` signature change (explicitly required by ticket item 3); it is not scope expansion on my own part.
7. `n_dropped_events` (in both `select_keys`/`score_causal`) uses strict `>` to judge `n_full[k] > max_len` / `n_full_tokens(...) > max_len`, matching the convention of `load_events`/`train_causal_tool.load_events`'s criteria (also strict `>`), introducing no new boundary discrepancy.
8. No GPU was used: this ticket was pure CPU code changes plus CPU unit tests throughout, with no step requiring a GPU, so the gpu-run process was not triggered.

## V. Fix round 1 (2026-08-28, taken over from the previous round's implementer)

Worktree `new1-wt/2026-08-28-wave5-T07-fix1`, branch still `ticket/2026-08-28-wave5/T07`,
starting point (before the fix) `19f2c70`, head after the fix `eadb3f8`. Received three unresolved findings, fixed one by one:

### F1 (critical) eval_causal_call.py did not implement "re-picking the firing point after ctool exclusion" per spec 16.2

**Root cause** (corresponds to self-check open question 1; now giving a root-cause fix instead of keeping the original decision):
`fired = replay_fire(rows, probs, ...)` (originally line 578) is computed using **all** rows before any exclusion happens, and `keys_rowmap[k]` in turn passes **all row indices** of that event in `rows` (including `fired[k]["row"]` itself). A firing row's conf is by definition always `>= θ`, while rows excluded by ctool have a uniform-distribution softmax of `1/n_labels`, which can only collide with θ when `θ<=1/n_labels`. The θ values in this project are all above 0.9, so the check `all(i in excluded_rows for i in keys[k])` is always false for any event that has already entered `keys`, and `n_excluded_by_ctool` is always 0. More fundamentally: if an event's candidate rows are **all** excluded by ctool (for example both rows are genuinely zero logits), it would never have `fired` in the original, unexcluded `replay_fire` in the first place (a class-0.5 conf cannot pass a θ of 0.9), so it never even gets past the "already fired" step. `select_keys` never sees this key at all; it is not "checked but judged false", it never gets the chance to be checked. This event thus **simultaneously disappears** from the three counts `n_events_fired`, `n_excluded_by_ctool`, `n_events_scored`, appearing in no denominator, and without raising any error.

**Fix** (directly overwriting the faulty logic, not patching around it): move the ctool exclusion to **before** the call to `replay_fire`. After reading `excluded_idx`, first group by event and compute "whether all candidate rows are excluded" to get `n_excluded_by_ctool` (this step is after exclusion, and does not depend on any subsequent fired state), then filter `rows`/`probs` by "index not in excluded_rows" (`cand_idx`/`cand_rows`/`cand_probs`), and call `replay_fire` with the filtered candidate rows. This way the firing point is naturally picked only from candidate rows that were never excluded, regardless of the relative size of θ and `1/n_labels`. It is not "θ is usually high enough so it's fine", but rather that excluded rows are kept out of the candidate pool from the source. The `--overlong` step (the second call to `select_keys`) therefore now passes an empty `excluded_rows`: every event in `keys` is already guaranteed to have at least one candidate row that was not excluded, so `select_keys`'s own exclusion branch can never hit here again; an `assert length_counts["n_excluded_by_ctool"] == 0` was added to pin down this invariant (an assertion failure would mean the earlier assumption was broken, not a defensive fallback).

`eval_causal_call.py` lines 572-607 (picking the firing point), lines 622-650 (`--overlong` filtering).

### F2 (critical) eval_causal_param.py has the same gap

The problem in `eval_causal_param.py` is structurally identical, word for word, to F1 (the `replay_fire` call is at line 403, and `keys_rowmap` at the original line 447 likewise takes all row indices), handled with the same root-cause fix: lines 401-434 (picking the firing point, `ev_row_idx`/`excluded_rows`/`n_excluded_by_ctool` computed ahead of time, `cand_idx`/`cand_rows`/`cand_probs` filtered before calling `replay_fire`), lines 453-486 (`--overlong` filtering now passes an empty `excluded_rows`, likewise asserting that the remaining `n_excluded_by_ctool` is always 0). `select_keys` (`share_data.py`) itself, shared by both scripts, was not changed, as a pure function its behavior was always correct (given the correct `keys`/`excluded_rows` it excludes correctly); the problem was always only in the step of "what gets fed to it" before the two eval scripts call it.

Self-check open questions 4/5 (`REPLAY_REPORT` only taking the test split's numbers, the val split also going through the same exclusion logic) are unrelated to this fix and are left untouched; items 2/3/6/7 (`score_causal`'s three-value return, the four extra counts written into `logits_*.meta.json`, the two call sites in `test_ctool_readpos.py`, the `n_dropped_events` criterion) are likewise outside the scope of this finding and are kept as they are.

### F3 (important) the new tests do not cover the wiring code where F1/F2 actually live

The original `TestSelectKeys` directly hand-built a candidate-row-index dictionary like `keys = {"e1": [0, 1], ...}` to call `select_keys`, bypassing the real wiring in the two eval scripts of "building `keys_rowmap` from `rows`, taking `fired[k]['row']` as the firing point". The F1/F2 bugs live exactly in this wiring, and an isolated unit test cannot catch it.

`tests/test_eval_overlong.py` adds two new end-to-end test classes:

- `TestCgenCtoolExclusionWiring` (tests `eval_causal_call.py`)
- `TestCparamCtoolExclusionWiring` (tests `eval_causal_param.py`)

Method: hand-build a real Qwen tokenizer plus a randomly initialized two-layer `AutoModelForCausalLM` (saved into a `<run>/best` directory following the `tiny_config`/`save_pretrained` pattern of `tests/test_lora_merge.py`), pair it with a hand-built `ctool` run (`REPLAY_REPORT.json` + `logits_test.pt` + `logits_test.meta.json`) and a hand-built `test.jsonl`, replace the script's `generate()` with an "echo" function (returns the fed-in prompt as-is, without depending on the model actually being able to produce anything), run `eval_causal_call.main()` / `eval_causal_param.main()` end to end, then read the persisted `CALLGEN_REPORT.json` / `PARAM_REPORT.json`.

Three events constructed (2-class labels, `θ=0.9`):

- `ev_reselect`: two rows, sent_idx 0 excluded but deliberately given strongly confident logits (`[10,-10]`, conf≈1.0), used to verify that "excluded rows must not be candidates for the firing point" is not something θ naturally blocks by itself, the wiring itself must block it; sent_idx 1 is not excluded, logits `[3,-3]` (conf≈0.9975), survives.
- `ev_full_excl`: both rows excluded, logits are the genuine zero logits produced by ctool `[0,0]` (conf=0.5<0.9). This is exactly the scenario F1 pointed out, "in the old wiring this kind of event never even gets to fired, and silently disappears from all the counts".
- `ev_normal`: one row, not excluded, fires normally, used as the baseline control.

Asserts `n_events_test==3`, `n_events_fired==2`, `n_excluded_by_ctool==1`, `n_events_scored==2`, and reads the generated prompt for `ev_reselect` from the echo report's `samples[...]["gen"]` field, confirming it contains "ROW1 SURVIVING TEXT" (the row that was re-picked) and does not contain "ROW0 EXCLUDED CONFIDENT TEXT" (the row that was excluded).

**Verified that these two new tests actually catch F1/F2** (not tests that pass trivially by construction): temporarily swapped in the two scripts using `git show 19f2c70:pipeline/eval/eval_causal_call.py` (the pre-fix version), ran the two new test classes alone, and both failed on `n_excluded_by_ctool` (`0 != 1`); switched back to the fixed scripts and both tests turned green.

## VI. How it was verified (this round)

```
$ cprobe-env/bin/python -m unittest tests.test_eval_overlong tests.test_share_data tests.test_ctool_readpos
Ran 41 tests in 7.225s
OK (skipped=1)
```
(41 = the previous round's 39 + the 2 end-to-end tests added this round; the 1 skip is the same as the previous round, the test case in `tests/test_share_data.py` that needs the active data directory, absent from the worktree since that gitignored directory is not there; not a regression.)

```
$ cprobe-env/bin/python -m unittest discover -s tests
Ran 433 tests in 17.016s
FAILED (failures=1, skipped=24)
```
The only failure is still `tests.test_preset.TestBfclHandlerPreset.test_no_env_reads_default_preset`
(hardcodes the absolute path `/home/y-guo/reproduce/new1/...`, which naturally does not match under this worktree's path; already confirmed unrelated to this ticket in the previous round, and this round's verification confirms the same).

```
$ grep -n "full_token_ids\|n_full_tokens" pipeline/train/share_data.py pipeline/train/train_causal_tool.py \
    pipeline/eval/eval_tool.py pipeline/eval/eval_causal_call.py pipeline/eval/eval_causal_param.py | wc -l
11   # all five files match
$ grep -n 'tok(e\["full_text"\]' pipeline/train/share_data.py | wc -l
0
$ grep -rn "def select_keys" pipeline/
pipeline/train/share_data.py:104:def select_keys(...)   # only here
```

The `--help` of all three eval scripts still lists `--overlong {left,skip,drop-event}`, default `left`
(re-ran verbatim to confirm, output matches the previous round's report).

```
$ python3 run.py selfcheck
selfcheck: 76 tasks / 4 recipes / 3 presets, 16 missing
```
The 16 missing items are still the venv/env directories (gitignored, only in the main repo, not in this worktree), consistent with the previous round, not a regression.

## VII. Commit list (this round)

- `530c997` T07: fix F1/F2 ctool exclusion-row wiring, exclude candidate rows before picking the firing point, re-pick the firing point
- `eadb3f8` T07: add F3 regression tests, run the wiring of eval_causal_call/param end to end, no longer testing only isolated units

Head after the fix: `eadb3f8`.
