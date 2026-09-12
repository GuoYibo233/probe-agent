# T11 Report: Learning-Rate Sweep Driver and Report `pipeline/train/sweep_lr.py`

Ticket: `.scratch/kvshare-train/issues/11-sweep-lr.md`
Branch: `ticket/2026-08-28-wave5/T11`, commit `540d06b`, base `073382cbf2f636bf639ef9f2721d28cf1efa1ba2`.

## What was done

Checked against the ticket item by item:

1. **`pipeline/train/sweep_lr.py`, two subcommands.**
   - `plan [--grid <json>] [--data <dir>] [--out-root <dir>] [--py <python>] [--track kvshare-lr-sweep] [--write <plan.json>]`:
     the grid constant `GRID` (the ticket's initial values: `b06` qwen
     full-parameter `[1e-5,5e-5,2e-4]` 16384 Ada `["--grad-ckpt"]`; `b17` qwen17
     full-parameter same as above 16384 H200 `[]`; `l17` qwen17 LoRA
     `[1e-4,5e-4,2e-3]` 16384 H200 `[]`; `l4` qwen4 LoRA same as above 16384
     H100 `["--grad-ckpt"]`) generates 12 runs. run_id =
     `ks828<tag>_gptoss_cgen_lr<lr>`, `<lr>` is obtained from `fmt_lr()`
     (`f"{lr:.0e}"` with the leading zero of the exponent stripped). The
     command is assembled in the order given by the ticket: `--mode cgen
     --base <base> --env appworld --data <absolute data path> --out <absolute
     out path> --lr <lr> --tok-budget <tb> --epochs 1 --eval-per-epoch 4
     --log-every 10 --mem-probe` plus `--lora` (when true) plus `extra`.
     `--data` defaults to `pipeline/data/nyapass_aw_v1/gptoss`, `--out-root`
     defaults to `pipeline/runs/sweep`, both resolved to absolute paths and
     written into the command; `--py` defaults to `<repo
     root>/cprobe-env/bin/python` (repo root =
     `Path(__file__).resolve().parents[2]`). After generation, self-checks
     that the run_ids are pairwise distinct; a collision (e.g. if the grid has
     `1.2e-5` stuffed in, `fmt_lr` keeping only one significant digit would
     collide with `1e-5`) triggers `SystemExit` and prints the two colliding
     entries (with tag and original lr value). stdout first prints a Markdown
     table (`run_id | tag | base | lora | lr | tok_budget | card | extra`),
     then prints a reminder "replace the --piece placeholder with the actual
     card from the card-allocation table", then 12 lines of `python3 run.py
     launch --cmd '<cmd>' --run-id <run_id> --track <track> --outdir <out>
     --piece <host>:<gpu>` (`shlex.quote` on the whole training command
     string, the `--piece` placeholder printed as-is). When `--grid` is given
     a JSON file, it replaces `GRID` wholesale. When `--write` is given, a
     JSON array is written to disk (each entry `run_id, tag, base, lora, lr,
     tok_budget, card, cmd, outdir`).
   - `report --runs <path or glob, nargs="+"> --out <dir>`: reads
     `train_log.jsonl` for each run directory. The `start` event takes `base,
     lora` (whether the key exists), `lr, tok_budget, n_train_events,
     dropped_events_train`; every `eval` event takes `frac, val_ce`, and
     either `val_exact_call` or `val_exact_params` (writes `null` if neither
     key is present); `done` takes `best_val_ce, best_frac, wall_s`; the max
     of `peak_mem_gb` among `step` events; `worst_gb` preferentially takes the
     `mem_probe_summary` event, falling back to the max of `peak_mem_gb`
     across the individual `mem_probe` events if absent, and writes `null` if
     neither is present. Grouping key `(base, lora)`, sorted ascending by lr
     within each group. Writes `<out>/SWEEP_REPORT.json` (each of the above
     fields plus `run_id, status`) and `<out>/SWEEP_REPORT.md` (header row
     `run_id | lr | val_ce@<ep>.<frac>…(the union of every (ep,frac)
     combination that appeared across all runs, generated dynamically,
     ascending) | best_val_ce | best_frac | val_exact(best) | peak_mem_gb |
     worst_gb | wall_s | status`; `status` is `done` or `running`; for a
     `running` row the best column writes the lowest eval seen so far; the row
     with the lowest `best_val_ce` in each group gets a `*` prepended to its
     run_id). A line before the table gives the generation time and the
     number of directories read, no conclusion sentence is written after the
     table. If `train_log.jsonl` is not found under a directory, a warning
     line is printed to stderr and it is skipped, without raising an error.

2. **Added `"sweep-lr"` to `run.py`'s `TASKS`**: `stage="train", py="cprobe",
   script="pipeline/train/sweep_lr.py"`, `desc` and `notes` per the ticket's
   requirements (usage of the two subcommands, the location of the `GRID`
   constant, launching still goes through gpu-run); the field set follows the
   precedent of `gen-toolhop-splits` (stage/py/script/desc/notes), no `gpu`
   key is written.

3. **`tests/test_sweep_lr.py`** (pure CPU, does not import torch):
   - `TestFmtLr`: formatting for six learning-rate values (`1e-05→1e-5` and
     five other examples).
   - `TestPlan`: the default `GRID` produces 12 non-duplicate run_ids, each
     `cmd` contains the correct `--lr` and `--log-every 10`, `--lora` present
     or absent according to `lora` being true/false, `outdir` ends with
     run_id; at the CLI level, `main(["plan", "--write", ...])` prints 12
     lines of `python3 run.py launch`, each line containing the `--piece
     <host>:<gpu>` placeholder, the written JSON has all 9 fields complete;
     given a `--grid` containing both `1e-5` and `1.2e-5`, `SystemExit`
     occurs.
   - `TestReport`: hand-built two run directories (one with `start`+4 `eval`
     events+`done`+2 `step` events+`mem_probe_summary`, one with only
     `start`+1 `eval` event), `report` produces two JSON entries, `status` is
     `done`/`running` respectively, the `running` row's `best_val_ce` equals
     the value of its single eval, in the Markdown the `done` row (with the
     lower `best_val_ce`) is marked with `*` while the `running` row is not,
     the dynamic column count of `val_ce@` equals the size of the union of
     `(ep, frac)` pairs appearing across the two directories (4); another test
     case verifies that when a directory has no `train_log.jsonl`, `report`
     returns 0, skips it, and the JSON is an empty list.

**Not done / out of scope**: the trainer was not modified
(`train_causal_share.py` has zero changes), `MAP.md` was not modified (the
ticket names this as belonging to ticket 12).

## How it was verified

```
cd <worktree>
/home/y-guo/reproduce/new1/cprobe-env/bin/python -m unittest tests.test_sweep_lr -v
```
```
Ran 6 tests in 0.007s
OK
```
(Six test cases: `test_examples`
`test_default_grid_twelve_unique_rows`
`test_cli_plan_prints_twelve_launch_lines_and_writes_json`
`test_grid_with_colliding_lr_exits`
`test_report_two_runs_status_star_and_columns`
`test_missing_train_log_is_skipped_not_error`. `cprobe-env` is not present in
this worktree; ran using the main repo's interpreter binary, with cwd switched
to the worktree.)

```
python3 -m unittest tests.test_sweep_lr -v
```
```
Ran 6 tests in 0.006s
OK
```
(The system `python3` is likewise all green, the script does not import
torch.)

```
python3 run.py selfcheck
```
worktree has no venv at all (they are not tracked by git), running as-is
produces 15-16 "missing interpreter/missing script" entries, all of them
missing untracked directories like `cprobe-env`, `mbert-env`, `envs/*/venv`,
unrelated to this ticket's changes. `sweep-lr` itself is not in the missing
list. Temporarily symlinked these directories from the main repo
`/home/y-guo/reproduce/new1/` into the worktree (for diagnostic purposes only,
deleted right after verification, never committed) and re-checked once:
```
selfcheck: 77 tasks / 4 recipes / 3 presets, all present
```
After removing the symlinks, `git status --porcelain` is clean (only this
ticket's three changed files remain), confirming the diagnostic step did not
pollute the branch.

Regression test (the `run.py` registry was changed, so ran the few test cases
affected by it as a safety net, did not run the full `discover`, that would
need each environment's venv, which is out of this ticket's scope):
```
python3 -m unittest tests.test_sweep_lr tests.test_launch_cmd tests.test_gpu_jobs tests.test_driver -v
```
```
Ran 144 tests in 4.615s
OK
```

Manual CLI test:
```
python3 pipeline/train/sweep_lr.py plan
```
Printed the 12-row table and 12 lines of `python3 run.py launch
...--piece <host>:<gpu>`; manually checked that the three lr values for each
of the four configs, the run_id naming, the presence/absence of `--lora`, and
the `extra` concatenation all matched the ticket's convention
(`ks828b06_gptoss_cgen_lr1e-5` … `ks828l4_gptoss_cgen_lr2e-3`, 12 in total, all
pairwise distinct).

```
python3 pipeline/train/sweep_lr.py plan --write /tmp/t11_plan_check.json
```
12 entries persisted, each containing the nine fields `run_id, tag, base,
lora, lr, tok_budget, card, cmd, outdir`.

## Commit list

- `540d06b` T11: learning-rate sweep driver and report
  `pipeline/train/sweep_lr.py` (plan/report), register `sweep-lr` (a single
  logical unit: new script + new tests + `run.py` registry entry).

## Self-check findings and open questions

- During self-check, found an unused `track` parameter in `build_plan()` and
  an unused `import re` at the top of the file (originally intended to
  implement `fmt_lr` with regex, later switched to a string-slicing
  implementation); deleted both on the spot, and updated the call sites and
  tests accordingly.
- Ticket item 1's description of the `--write` JSON fields (the nine fields
  `run_id, tag, base, lora, lr, tok_budget, card, cmd, outdir`) does not match
  the spec 16.6 text (the six fields `run_id, cmd, outdir, card, tag, lr`);
  per the implementer's rule that "the ticket file is the sole source of
  requirements", implemented per the ticket's nine fields. This is not
  ambiguity or missing information, the ticket supplements the spec, there
  was no need to stop, but it is recorded here for cross-checking at merge
  time.
- The key names used for each eval record in `report`'s output JSON,
  `ep/frac/val_ce/val_exact`, are ones I chose myself (the ticket's original
  text says "take frac, val_ce, val_exact_call (or val_exact_params)", it does
  not mandate the field names at this layer of the output JSON, only which
  source keys to take). `val_exact` is a unified field taken from the source
  event's `val_exact_call` or `val_exact_params` (whichever key is present),
  without additionally outputting the two top-level keys
  `val_exact_call`/`val_exact_params`. This is an implementation choice I made
  in the absence of more explicit guidance, not a deviation from the ticket;
  but since it is not a name the ticket text gives directly, it is listed here
  to explain the rationale, for other tickets (especially downstream code
  reading this JSON) to reference when aligning naming.
- Each record in `SWEEP_REPORT.json` carries an extra underscore-prefixed
  internal field `_best_ep`. No, it does not: it is already filtered out
  before writing the JSON (`json_records` in `cmd_report` is the version with
  `_best_ep` excluded); it is only passed in memory to the Markdown-generation
  step to find `val_exact(best)`. The final JSON artifact is clean, with no
  extra field.
- No GPU was used, the trainer was not touched, the commands printed by
  `plan` were not actually launched and verified (this was never meant to be
  done within this ticket's scope; the main conversation handles the gpu-run
  smoke test).

## Fix round 1 (F1)

Worktree: `/home/y-guo/reproduce/new1-wt/2026-08-28-wave5-T11-fix1`, checked
out the existing branch `ticket/2026-08-28-wave5/T11` (HEAD before checkout
`540d06b`).

### Findings to fix

- **F1 (important)**: `summarize_run()`'s three value-taking paths for
  `worst_gb`, preferentially `mem_probe_summary.worst_gb`, falling back to
  the max `peak_mem_gb` across the `mem_probe` events (the
  backward-compatible old-probe branch explicitly required by ticket item 1),
  or `null` when neither is present. The tests covered only the first
  (`_make_done_run` with `mem_probe_summary`) and the third
  (`_make_running_run` with no memory events at all); the middle `elif
  mem_probes: ...` branch was never triggered by any test case. The review
  already confirmed the branch's own value-taking is correct (not a
  functional bug), it is purely a lack of test coverage.

### How it was fixed

Production code `pipeline/train/sweep_lr.py` was not changed. The logic of
the `elif mem_probes:` branch itself has no problem, it does not need a
root-cause fix, what needs to be added is a test.

Added to `TestReport` in `tests/test_sweep_lr.py`:

- `_make_run_with_mem_probe_events_only()`: hand-builds a run directory
  containing only `start` + one `eval` + two `mem_probe` events
  (`peak_mem_gb` 18.3 and 21.5 respectively, no `mem_probe_summary`).
- `test_worst_gb_falls_back_to_mem_probe_max_without_summary()`: calls
  `SL.summarize_run(d)` directly on this directory, asserts
  `rec["worst_gb"] == 21.5` (the max of the two `mem_probe` values), pinning
  down the previously zero-coverage `elif` branch.

Did not touch the `plan` subcommand, the `run.py` registry, or `MAP.md`, not
within the scope of this round's finding.

### How it was verified

```
cd /home/y-guo/reproduce/new1-wt/2026-08-28-wave5-T11-fix1
python3 -m unittest tests.test_sweep_lr -v
```
```
test_examples (tests.test_sweep_lr.TestFmtLr) ... ok
test_cli_plan_prints_twelve_launch_lines_and_writes_json (tests.test_sweep_lr.TestPlan) ... ok
test_default_grid_twelve_unique_rows (tests.test_sweep_lr.TestPlan) ... ok
test_grid_with_colliding_lr_exits (tests.test_sweep_lr.TestPlan) ... ok
test_missing_train_log_is_skipped_not_error (tests.test_sweep_lr.TestReport) ... ok
test_report_two_runs_status_star_and_columns (tests.test_sweep_lr.TestReport) ... ok
test_worst_gb_falls_back_to_mem_probe_max_without_summary (tests.test_sweep_lr.TestReport) ... ok

Ran 7 tests in 0.011s

OK
```
(System `python3`; the 6 old test cases are all green, the newly added 7th
covers F1.)

```
/home/y-guo/reproduce/new1/cprobe-env/bin/python -m unittest tests.test_sweep_lr -v
```
```
Ran 7 tests in 0.010s

OK
```
(worktree does not have `cprobe-env`; ran using the main repo's interpreter
binary, with cwd switched to the worktree; both interpreters named in the
acceptance criteria pass.)

Regression (the change is a test file, `run.py`'s registry itself was not
touched, still re-checked once more against the previous round's same set of
tests, as a safety net):
```
python3 -m unittest tests.test_sweep_lr tests.test_launch_cmd tests.test_gpu_jobs tests.test_driver -v
```
```
Ran 145 tests in 4.537s

OK
```
(the same set in the previous round was 144; the 1 extra this round is the
newly added F1 test case; the other 144 results are consistent with the
previous round, all unrelated log noise printed to stdout by tasks other than
`sweep-lr`, not failures.)

### Commit list

- `e0677fc` T11: add test coverage for the worst_gb backward-compatible
  old-probe branch (F1) (single change: `tests/test_sweep_lr.py` gains one
  run-directory constructor + one test, zero changes to production code).

### Self-check findings and open questions

- Went through this round's diff line by line: only added one helper method
  and one test method in `tests/test_sweep_lr.py`, all 27 lines are
  additions, no existing code was changed or deleted, `plan`, `run.py`,
  `MAP.md` were not touched, no change went beyond the scope of F1.
- The new test calls `SL.summarize_run()` directly (a module-level public
  function), instead of going through the full `report` CLI round trip.
  This precisely isolates the `elif` branch named by F1, without
  interference from other logic in `cmd_report` (grouping, dynamic columns,
  Markdown assembly); judged that testing this way better fits what the
  finding asked for (the finding's original wording is "hand-built, in an
  isolated environment, a run_log containing only mem_probe events, and
  verified it", which is the same kind of verification as calling
  `summarize_run` directly).
- No new findings were found.
