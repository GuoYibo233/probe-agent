# T04 report: the "Runs by card type" table in jobs/RESULTS.md

Branch `ticket/2026-10-02-wave2/T04`, base `f37f0980fc62abfaa2d93cd90f7caf03cb4ddd9b`,
head `eb7244791659dda1d489cbce5957c59b562a9425`. Worktree removed, branch kept.

## 1. What was done, against each requirement

- **A second table after the existing one, headed `## Runs by card type`, from the finish rows
  that carry a `card_record`.** `render()` (`jobs/registry.py`) now reads the ledger once and
  appends the lines `_card_type_lines(rows)` returns. That function walks every row of
  `runs.jsonl` (not the fold, so every incarnation of a relaunched run counts with its own
  record) and keeps the finish rows whose `card_record` is a non-null record. Under the heading
  sits one blockquote line saying what the table is; with no card record in the ledger the table
  is replaced by `No card records yet.` (what the real ledger renders today: it holds no card
  record yet).
- **One row per (task identity, card model); debug and full-size runs are separate rows.** The
  identity is the record's `task` dict (serialised with sorted keys as the group key), which
  holds `debug`, so a debug run lands in its own row. A record's pieces are split by
  `card_model`; the run counts in the row of each card model its card-holding pieces ran on
  (an inject run with its agent service on H200 and its probe service on H100 counts in both
  rows, and a memory failure counts only in the row of the card model whose piece failed).
- **Columns.** `stage | task | card | ok | failed for memory | memory | median speed | newest
  run | newest memory failure`:
  - stage: the task's `stage`;
  - task: the identity fields as `k=v`, space-separated, `stage` left out because it has its own
    column;
  - card: the card model and its memory (`NVIDIA H200 NVL 140 GiB`);
  - ok: finish rows of that group with status `ok`;
  - failed for memory: finish rows in which a piece on that card model has `failure: memory`;
  - memory: `peak <x> GiB` (largest train-piece `peak_gib`), `probe service peak <x> GiB`
    (largest probe-service `peak_gib`), and for the agent service the load with the largest
    weights + KV cache, `weights <w> + KV cache <k> GiB, concurrency <c>x`; joined by `; ` when a
    row has more than one kind (both services of an inject run on one card model); `-` when no
    piece measured any;
  - median speed: the median of the records' `speed.per_hour`, with the unit, `147.0 step/h`;
  - newest run: the run key of the group's newest finish row.
- **A row with a memory failure adds the run key and the quoted `failure_line` of its newest
  memory failure.** Last column: `` `train-<key>` "<failure_line>" ``, with `|` escaped as `\|`
  so the line cannot break the table; `-` for a row with no memory failure.
- **Newest row first.** Rows sort by the ledger position of each group's newest finish row
  (the append-only file's order, which is exact where the minute-resolution `t` is not).
- **The README section 2 line of `jobs/RESULTS.md` names the second table.** Done; the
  `jobs/registry.py` line now says "RESULTS.md (the runs table and the "Runs by card type"
  table)", and the `tests/` line names the new test cases.

Choices made inside the ticket's wording (each is a small judgment call, listed so a reviewer
can overrule it):

1. A record whose `task` is null (settings.yaml unreadable at finish time, ticket 01's
   `_guarded`) is grouped by its run id's stage alone, its task cell reads `-`. It is not
   dropped, because the ticket says the table is built from every finish row carrying a card
   record.
2. A finish row whose `card_record` is null (no open start row) adds nothing.
3. For the agent service "weights + KV cache and the maximum concurrency" is read as: the load
   with the largest weights + KV cache, and that same load's maximum concurrency.
4. The speed of a run is the run's (ticket 01 sums it over work pieces), so it counts in every
   card-model row the run touched; speeds of failed incarnations are included in the median.
5. The card memory cell shows the distinct `card_gib` values joined by `/` if a model ever had
   two sizes; in `constants/cards.yaml` today each model has one size.

`jobs/RESULTS.md` itself is not re-rendered on this branch: it is rendered on the next append
to the ledger, and rendering it here would put a generated file into a parallel branch.

## 2. How it was verified

All commands were run in the worktree with the main repo's interpreter
(`/home/y-guo/reproduce/new1/external/probe-env/bin/python`, because `external/` is not in git
and so is absent from a worktree).

Acceptance 1: a CPU-only unit test renders from fixture rows (two card models, one memory
failure, one debug run) and checks the grouping and the failure quote. Added as the class
`RunsByCardTypeTest` in `tests/test_registry_concurrent_append.py` (the registry's test module;
no new file). It copies `jobs/registry.py` into a temporary tree with its own `runs.jsonl`, so
it never touches the real ledger. The main case's fixture: a full-size train run that dies of
memory on an H100 card and is relaunched under the same run id on an H200 card where it
finishes; a second run of the same task on H200; a debug run of the same task on H200; a sample
run's agent service on H200; a build finish row and a finish row whose record is null. The
asserted table, verbatim:

```
| stage | task | card | ok | failed for memory | memory | median speed | newest run | newest memory failure |
|---|---|---|---|---|---|---|---|---|
| sample | debug=False models.agent=qwen3pt8_27b cards_per_agent_server=1 | NVIDIA H200 NVL 140 GiB | 1 | 0 | weights 50.22 + KV cache 73.63 GiB, concurrency 8.99x | 187.3 task/h | `sample-f6f6f6f6f6f6` | - |
| train | debug=True models.probe=qwen3_4b probe.method=ctool probe.tuning=lora probe.lora_r=16 train.max_len=8192 train.events_per_mb=4 train.grad_ckpt=True | NVIDIA H200 NVL 140 GiB | 1 | 0 | peak 20.0 GiB | 600.0 step/h | `train-e5e5e5e5e5e5` | - |
| train | debug=False models.probe=qwen3_4b ... | NVIDIA H200 NVL 140 GiB | 2 | 0 | peak 70.0 GiB | 147.0 step/h | `train-c3c3c3c3c3c3` | - |
| train | debug=False models.probe=qwen3_4b ... | NVIDIA H100 NVL 93 GiB | 0 | 1 | peak 92.04 GiB | - | `train-a1a1a1a1a1a1` | `train-a1a1a1a1a1a1` "torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 2.00 GiB. ..." |
```

(the `...` here shorten the report only; the test compares the full lines). Two further cases:
a failure line holding `|` is written as `\|` and the row stays one table row with `-` for
memory and speed; a ledger with no card record renders `No card records yet.`.

```
$ external/probe-env/bin/python tests/test_registry_concurrent_append.py -v
...
test_a_failure_line_with_a_pipe_keeps_the_table_whole (__main__.RunsByCardTypeTest...) ... ok
test_a_ledger_without_card_records (__main__.RunsByCardTypeTest...) ... ok
test_one_row_per_task_and_card_model_newest_first (__main__.RunsByCardTypeTest...) ... ok
----------------------------------------------------------------------
Ran 18 tests in 0.653s

OK
```

Acceptance 2: `run.py selfcheck` green; all CPU test modules pass.

```
$ external/probe-env/bin/python run.py selfcheck
selfcheck: 32 python files, 0 problems

$ external/probe-env/bin/python tests/test_registry_concurrent_append.py   -> Ran 18 tests in 0.629s  OK
$ external/probe-env/bin/python tests/test_settings_keys.py                -> Ran 25 tests in 24.464s OK
$ external/probe-env/bin/python tests/test_probe_input.py                  -> Ran 19 tests in 2.258s  OK
$ external/probe-env/bin/python tests/test_record_formats.py               -> Ran 16 tests in 0.194s  OK
$ external/probe-env/bin/python tests/test_probe_eval.py                   -> Ran 15 tests in 2.064s  OK
$ external/probe-env/bin/python tests/test_environment_and_build.py        -> Ran 22 tests in 0.074s  OK
$ external/probe-env/bin/python tests/test_qwen3_family.py                 -> Ran 13 tests in 24.883s OK
$ CUDA_VISIBLE_DEVICES= external/probe-env/bin/python tests/test_packed_loss.py -> Ran 3 tests in 2.676s OK
```

Extra check: a copy of `jobs/registry.py` rendered the real `jobs/runs.jsonl` in the scratchpad.
The runs table came out identical to the committed `jobs/RESULTS.md`, followed by the new
heading, the blockquote line and `No card records yet.`. `git status` in the worktree after the
test runs showed only the three edited files, so no test wrote the real ledger or RESULTS.md.

## 3. Commits

- `eb72447` T04: the "Runs by card type" table in jobs/RESULTS.md (`jobs/registry.py`
  `render()`, `_card_type_lines`, `_card_type_memory`; `RunsByCardTypeTest` in
  `tests/test_registry_concurrent_append.py`; README section 2 lines of `jobs/registry.py`,
  `jobs/RESULTS.md` and `tests/`).

## 4. Self-review findings and open questions

- Source of the logic: none ported; the ticket and the spec section "The lookup view" define
  it, and it reads the `card_record` shape ticket 01 writes (`_card_record` in the same file).
- The ticket cites `jobs/registry.py:493-519` for `render()`; after ticket 01 it sits at
  lines 838-866. No conflict, only moved lines.
- The ticket's column list names "card model and memory" as one column; the header calls it
  `card`. The ticket names no header words, so the headers are mine: `stage`, `task`, `card`,
  `ok`, `failed for memory`, `memory`, `median speed`, `newest run`, `newest memory failure`.
- Open question for the owner, low stakes: whether a record with an unreadable `task` should be
  dropped instead of grouped under its stage with task `-` (choice 1 above).
- Merge note: ticket 03 (same wave) edits `jobs/registry.py` too, around `refire`/`retry` and
  the dead incarnation; this branch only touches `render()` and adds two functions after it, so
  a textual conflict is unlikely. Both branches may touch the README `jobs/registry.py` line
  and the `tests/` line; a conflict there is a two-sentence merge.

## Fix round 1

Branch `ticket/2026-10-02-wave2/T04`, head `781f2aec6385bb2a13aebc34c269fda439069541`
(one commit on top of `eb72447`). Worktree `new1-wt/2026-10-02-wave2-T04-fix1` removed, branch kept.

### F1 (critical): a record with a null task merged debug and full-size runs into one row

Fixed at the cause: the fallback identity no longer drops `debug`. `_card_type_lines`
(`jobs/registry.py`) now remembers each run's newest start row as it walks the ledger, and a
record whose `task` is null takes `{"stage": <start row's stage>, "debug": bool(<start row's
debug>)}` from the start row it closes. The record exists only for a run with an open start row
(`_card_record` returns None otherwise, and reads the ledger before its finish row is appended),
so that start row is always above the finish row; the lookup is `starts[run_id]` with no
fallback. Such a row's task cell now reads `debug=True` or `debug=False`, so the reader can tell
which kind it is. The function's docstring says this. Null-task records stay in the table
(answering open question 1 the way the finding's first fix names); they are not dropped.

Test: new case `test_records_without_a_task_keep_debug_and_full_size_apart` in
`RunsByCardTypeTest` (`tests/test_registry_concurrent_append.py`), the finding's own scenario: two
null-task train records on H200, one from a debug start row (600 step/h, peak 20), one from a
full-size start row (100 step/h, peak 80). Asserted rows, verbatim:

```
| train | debug=False | NVIDIA H200 NVL 140 GiB | 1 | 0 | peak 80.0 GiB | 100.0 step/h | `train-c3c3c3c3c3c3` | - |
| train | debug=True | NVIDIA H200 NVL 140 GiB | 1 | 0 | peak 20.0 GiB | 600.0 step/h | `train-a1a1a1a1a1a1` | - |
```

The same case run against `eb72447`'s `jobs/registry.py` (the fix stashed) fails with one merged
row (`FAILED (failures=1)`); with the fix it passes. The README `tests/` line now says "a debug
run in a row of its own (also when its record's task could not be read)".

### Verification

```
$ external/probe-env/bin/python run.py selfcheck
selfcheck: 32 python files, 0 problems

$ external/probe-env/bin/python tests/test_registry_concurrent_append.py -v
...
test_a_failure_line_with_a_pipe_keeps_the_table_whole (__main__.RunsByCardTypeTest...) ... ok
test_a_ledger_without_card_records (__main__.RunsByCardTypeTest...) ... ok
test_one_row_per_task_and_card_model_newest_first (__main__.RunsByCardTypeTest...) ... ok
test_records_without_a_task_keep_debug_and_full_size_apart (__main__.RunsByCardTypeTest...) ... ok
Ran 19 tests in 0.634s
OK

$ external/probe-env/bin/python tests/test_settings_keys.py                -> Ran 25 tests in 23.704s OK
$ external/probe-env/bin/python tests/test_probe_input.py                  -> Ran 19 tests in 2.059s  OK
$ external/probe-env/bin/python tests/test_record_formats.py               -> Ran 16 tests in 0.088s  OK
$ external/probe-env/bin/python tests/test_probe_eval.py                   -> Ran 15 tests in 2.245s  OK
$ external/probe-env/bin/python tests/test_environment_and_build.py        -> Ran 22 tests in 0.069s  OK
$ external/probe-env/bin/python tests/test_qwen3_family.py                 -> Ran 13 tests in 23.888s OK
$ CUDA_VISIBLE_DEVICES= external/probe-env/bin/python tests/test_packed_loss.py -> Ran 3 tests in 2.628s OK
```

Extra check: a copy of the fixed `jobs/registry.py` rendered a copy of the real `jobs/runs.jsonl`
in the scratchpad. The ledger now holds one card record (`train-3e562de5abb9`, a debug train run
on an RTX A6000); it rendered as one row with no error, so its start row was found.

### Commits

- `781f2ae` T04: a card record without a task is grouped by its start row's stage and debug
  (`jobs/registry.py` `_card_type_lines`; the new case in
  `tests/test_registry_concurrent_append.py`; the README `tests/` line).
