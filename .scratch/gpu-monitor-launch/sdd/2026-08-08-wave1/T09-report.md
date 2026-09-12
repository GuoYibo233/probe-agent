# T09: `run.py launch` subcommand

Ticket: `.scratch/gpu-monitor-launch/issues/09-launch-cmd.md`
Reference: `docs/plans/2026-08-08-gpu-monitor-launch.md` Task 11 (implementation-step source named by the ticket)

## What was done

New `ops/launch_cmd.py`, implementing `cmd_launch(argv)` and three separately unit-testable pure-logic functions
`parse_launch_argv`/`build_pieces`/`verify_alive`. `run.py` got the `launch` dispatch,
a usage line at the file header, and `TASKS["collect-aw"]` got `shardable=True`.

Against the ticket's acceptance requirements one by one:

1. **Shard-injection tests pass: two pieces get shard numbers 0 and 1, multi-piece rejected when not shardable, two pieces on the same host and card rejected**
   `build_pieces(p, t)`:
   - When `t.get("shardable")` is true and `--piece` is given >=2 times → each piece's command gets
     `--shard-id <i> --num-shards <N>` appended (i starting at 0, order following the order
     `--piece` appeared).
   - Giving >=2 `--piece` for a task not marked `shardable` → `SystemExit`.
   - Two `--piece` with identical `host:gpus` → `SystemExit` (same host and card stepping on each other).
   - `--cmd` mode: `t=None`, the command is used as-is (`p["cmd"]` is the `cmd_str` directly, not looking up
     `TASKS`, no shard injection. The ticket doesn't require sharding in `--cmd` mode either, implemented per the
     literal wording "command as-is").
   - session name = `new1_<run_id>_t<host with tokyo stripped>g<gpus comma-to-hyphen>`
     (e.g. `tokyo108:0,1` → `new1_<rid>_t108g0-1`).

2. **Dry-run smoke test: a two-piece collection task prints two full commands carrying shard numbers, the registration function isn't called**
   `--dry-run` prints each piece's `inner` command (the full in-tmux command including `cd`/`CUDA_VISIBLE_DEVICES`/`tee`,
   not just the bare script invocation), then directly `return 0`. `probe_free`/
   `tmux_launch`/`register_all` are all left untouched. Tested:

   ```
   python3 run.py launch collect-aw --run-id smoke_x --track smoke \
     --piece tokyo106:0 --piece tokyo106:1 --dry-run --allow-dirty \
     -- --base-url http://x/v1 --model m --outdir /tmp/x
   ```

   Prints two lines, respectively containing `--shard-id 0 --num-shards 2` and `--shard-id 1 --num-shards 2`
   (verbatim below in "How it was verified").

3. **`python3 run.py selfcheck` passes (launch is wired into run.py), commit**
   See the verification record below.

The flow followed the ten steps from plan Task 11, in the same order: argument parsing (hand-written iteration,
everything after `--` is passed through to the task/`--cmd` as-is, no longer treated as a launch flag) →
task/`--cmd` mode decision → `gate_dirty`
(honor_dry=True, `--dry-run` allowed through) → `run_id`/`track` required-field check → `build_pieces`
(shard injection + session/log naming, `log = <workdir>/logs/<sess>.log`, workdir taken from
`t["cwd"]`/`--workdir`/ROOT) → dry-run branch returns early → per-piece `probe_free`
(any single piece non-FREE triggers a whole-batch `SystemExit`, listing all reasons) → per-piece make log dir +
`tmux_launch` → `verify_alive` (30-second window, one round every 5 seconds: passes early if every
piece's log byte count has grown; when the window ends, checks each piece's `has_session` + tails 4KB of the log for a
`Traceback` for a final pass/fail verdict. On failure, prints the piece info + the log's last 40 lines, already-launched
pieces are not rolled back, `return 1` and does not register) → `register_all(...)` assembles rich pieces
(host/gpus/session/log/cmd/launched_at/kind/stall_line/escalate_line) + job-level `monitor`
(only when `--warmup-line` is given does it carry `warmup_s`; if not given, `monitor` isn't passed at all,
matching T08's settlement convention that "when `monitor=None`, the job's `monitor` key isn't written") →
prints the monitoring entry points (`gpu-jobs` / `watch` / web `localhost:8377`).

## How it was verified

```
$ python3 -m unittest tests.test_launch_cmd -v
```
```
test_dry_run_does_not_probe_or_launch (tests.test_launch_cmd.TestCmdLaunchDryRun) ... ok
test_dry_run_prints_shard_commands_and_skips_register (tests.test_launch_cmd.TestCmdLaunchDryRun) ... ok
test_non_free_piece_rejects_all_and_no_register (tests.test_launch_cmd.TestCmdLaunchFullFlow) ... ok
test_success_registers_rich_pieces (tests.test_launch_cmd.TestCmdLaunchFullFlow) ... ok
test_verify_alive_failure_skips_register (tests.test_launch_cmd.TestCmdLaunchFullFlow) ... ok
test_missing_run_id_rejected (tests.test_launch_cmd.TestCmdLaunchValidation) ... ok
test_missing_track_rejected (tests.test_launch_cmd.TestCmdLaunchValidation) ... ok
test_unknown_task_rejected (tests.test_launch_cmd.TestCmdLaunchValidation) ... ok
test_cmd_mode_flags (tests.test_launch_cmd.TestParseLaunchArgv) ... ok
test_task_positional_and_flags (tests.test_launch_cmd.TestParseLaunchArgv) ... ok
test_fails_on_traceback_in_tail (tests.test_launch_cmd.TestVerifyAlive) ... ok
test_fails_when_session_gone (tests.test_launch_cmd.TestVerifyAlive) ... ok
test_ok_when_alive_and_no_traceback (tests.test_launch_cmd.TestVerifyAlive) ... ok
... (19 total, including the 6 in TestBuildPieces)
----------------------------------------------------------------------
Ran 19 tests in 0.311s

OK
```

```
$ python3 -m unittest discover -s tests -v   # whole-repo tests (coexisting with other merged tickets)
```
```
Ran 54 tests in 0.573s

OK
```

```
$ python3 run.py selfcheck
```
```
selfcheck: 63 tasks / 4 recipes, 16 missing
missing interpreter/program: .../envs/appworld/venv/bin/python  (task collect-aw)
... (16 lines, all envs/*/venv, cprobe-env, mbert-env and other third-party venvs missing)
```
These 16 lines are "all present" (confirmed) in the **main-repo worktree**
(`/home/y-guo/reproduce/new1`). venv directories are not in git (`.gitignore`), and
`git worktree add` only materializes git-tracked files, so the worktree naturally lacks these third-party venvs.
this is a product of the parallel worktree itself, not a problem introduced by this change; `shardable=True` and
similar new fields don't participate in `selfcheck`'s check items at all (it only checks
`py`/`prog`/`script`/`cwd` existence, and `RECIPES`/`EVAL_CELLS` references).

```
$ python3 run.py launch collect-aw --run-id smoke_x --track smoke \
    --piece tokyo106:0 --piece tokyo106:1 --dry-run --allow-dirty \
    -- --base-url http://x/v1 --model m --outdir /tmp/x
```
```
[dry-run] tokyo106 gpu0 new1_smoke_x_t106g0
    cd .../new1-wt/20260808-par-T09 && CUDA_VISIBLE_DEVICES=0 .../envs/appworld/venv/bin/python .../envs/collect/run_appworld.py --base-url http://x/v1 --model m --outdir /tmp/x --shard-id 0 --num-shards 2 2>&1 | tee .../logs/new1_smoke_x_t106g0.log
[dry-run] tokyo106 gpu1 new1_smoke_x_t106g1
    cd .../new1-wt/20260808-par-T09 && CUDA_VISIBLE_DEVICES=1 .../envs/appworld/venv/bin/python .../envs/collect/run_appworld.py --base-url http://x/v1 --model m --outdir /tmp/x --shard-id 1 --num-shards 2 2>&1 | tee .../logs/new1_smoke_x_t106g1.log

2 pieces total (dry-run, not launched, not registered)
```
Both commands carry `--shard-id`/`--num-shards`, matching acceptance item 2 verbatim.

## Commit list

- `0144ea0`: `T09: run.py launch subcommand (probe→tmux→verify alive→three registrations in one command; shardable injection)`
  Changes: `ops/launch_cmd.py` (new), `tests/test_launch_cmd.py` (new), `run.py`
  (launch dispatch + usage line + `collect-aw`'s `shardable=True`).

## Self-check findings and open questions

- **`--service`/`--port` have no dedicated logic**: plan Task 11's `Produces` command signature wrote
  `[--service --port N]`, but none of the ten numbered steps mentions how to handle them,
  and design doc §6's launch section doesn't mention them either. I implemented `--service` as a recognized
  boolean flag; when given, it sets every piece's `kind` for that launch to `"service"` (default `"batch"`),
  and that's all it does; `--port` isn't recognized specially, and falls into the "unrecognized flag passed through
  to the task" branch. For a vLLM-style service, `--port` genuinely needs to be passed to the real
  `vllm serve` command, so treating it as a task parameter is a reasonable landing point.
  But `verdicts.py`/plan Task 15 (the vLLM service ledger) says service pieces should be verdicted alive via
  `probe_port(host, port)`, yet the rich piece's field table (fixed by T08's docstring)
  has no `port` field at all. The whole plan document never accounts for the path this field would take
  from piece to sampler. This is not in this ticket's acceptance scope (ticket 13's vLLM service ledger changes
  `ops/sampler.py`, not `launch_cmd.py`), and I did not invent a field for it. Leaving it for whoever
  implements ticket 13, or a follow-up user confirmation of how to fill this plan gap.
- **`gate_of` is not imported/used**: plan Task 11's `Consumes` lists
  `run.TASKS/PY/build_cmd/gate_dirty/gate_of`, but none of the ten steps
  actually uses `gate_of` (launch uses its own `gate_dirty` for a unified gate, and doesn't go through the old
  `TASKS`/`gate_of`/`print_handoff`/`run_direct` route). I did not import
  `gate_of`, to avoid dead code; if this is a missing intended use (e.g. wanting launch to
  respect some task's `gate=False` by taking a different path), it needs clarification from the user or a follow-up ticket.
- **`--cmd` mode with multiple `--piece` does not do shard injection**: the ticket's acceptance items only test the shard
  injection for task mode; I interpreted `--cmd` mode's "command as-is" (Step 1 test's original wording) as
  meaning that even given multiple `--piece`, each piece still gets the exact same
  command, with nothing appended. This is asymmetric with task mode's shard-rejection rule
  (rejects when not shardable): `--cmd` mode given multiple `--piece` neither rejects nor shards at
  all, launching the exact same command as-is. Neither the ticket nor the plan says whether `--cmd`
  mode should reject multiple pieces; I implemented it following the reading closest to the literal "command as-is,"
  noted here for review.
- **`--workdir` only applies in `--cmd` mode**: the plan's original wording, "workdir defaults to ROOT, task mode
  uses cwd if given," only mentioned the task branch, and the command signature also only wrote
  `--workdir DIR` on the `--cmd`-mode line. Based on this, I implemented it so that: task mode ignores
  `--workdir` (even if given, it's not used, only `t.get("cwd", ROOT)`),
  `--cmd` mode is the only one that consumes `--workdir`. If the user wants task mode to also be able to override
  workdir, a separate interface needs to be defined.
- **The multi-piece `cmd_display` (the single-command display string for `record.py`/RUNMETA)**:
  the plan does not define what this field should look like for multiple pieces; I implemented it so that:
  single piece uses that piece's command directly; multiple pieces are joined with `"; "` between each
  piece's full command. This is the smallest reasonable choice I made in the absence of a clearer spec, not
  a copy of some existing pattern, and is worth eyeballing after the next real multi-piece launch, to check whether the rendering in
  `RESULTS.md` is readable (the ticket 09 comments also mention that this needs a main-session check).
- No real GPU process or tmux session was launched, `probe_free`/`tmux_launch`/
  `register_all`/network calls were all mocked in tests, no real ledger was touched
  (`ops/jobs.json`), nor `ops/runs.jsonl`, nor any GPU machine.

## Fix round 1 (2026-08-08)

Review turned up one important finding:

### F1: Same-host-same-card de-dup only checks exact string equality, doesn't catch overlapping GPU ranges

**Problem**: `build_pieces()`'s original de-dup logic put a `key = (host, gpus)` into a
`seen` set, with `gpus` being the raw string after the colon in `--piece`. Two
`--piece` are only blocked if the strings are **exactly identical** (`tokyo106:0` and `tokyo106:0`).
But a piece can be a multi-card string (like `tokyo108:0,1`, already used in this form in
`test_session_name_format`); `--piece tokyo106:0,1 --piece tokyo106:1,2`
are two unequal strings, so they aren't rejected, but they genuinely overlap on gpu1. This would send two processes
onto the same card at the same time, a silent miss beyond the probe-before-launch check
(`probe_free`).

**How it was fixed**: in `ops/launch_cmd.py`'s `build_pieces()`, swapped
`seen = set()` + exact-string-match key for accumulating, per host, a set of
"already claimed gpu ids" (`claimed_by_host: dict[host] -> set[gpu_id]`). Each new
`--piece` splits `gpus` on commas into a set of gpu ids first, and intersects it with
that host's already-accumulated set; a non-empty intersection triggers `SystemExit`
(reporting the specific conflicting gpu id), an empty intersection merges these ids into the accumulated
set and continues. This fix covers both the original exact-duplicate scenario (an exact
duplicate necessarily has a non-empty intersection) and the newly discovered partial-overlap scenario, without
falsely flagging non-overlapping cards on the same host (like `0,1` and `2,3`,
which should be allowed through). The error message keeps the original wording ("two pieces on the same host and
card will step on each other, split across different cards or launch separately"), only the
verdict condition changed from string equality to set intersection.

The scope of the change is only this piece of de-dup logic inside `build_pieces()`; the function signature, return
structure, and caller `cmd_launch()` were all untouched, no scope-widening refactor.

**Tests**: two cases added to `TestBuildPieces` in `tests/test_launch_cmd.py`:

- `test_overlapping_multi_gpu_pieces_rejected`: `tokyo106:0,1` +
  `tokyo106:1,2` (overlapping gpu1) should `SystemExit`.
- `test_disjoint_multi_gpu_pieces_same_host_allowed`: `tokyo106:0,1` +
  `tokyo106:2,3` (non-overlapping) should be allowed, producing 2 pieces.

The existing `test_duplicate_host_gpu_piece_rejected` (exact duplicate
`tokyo106:0` + `tokyo106:0`) was left unchanged, verifying the new logic doesn't regress the old scenario.

```
$ python3 -m unittest tests.test_launch_cmd -v
```
```
test_cmd_mode_command_verbatim_no_registry (tests.test_launch_cmd.TestBuildPieces) ... ok
test_disjoint_multi_gpu_pieces_same_host_allowed (tests.test_launch_cmd.TestBuildPieces) ... ok
test_duplicate_host_gpu_piece_rejected (tests.test_launch_cmd.TestBuildPieces) ... ok
test_no_piece_rejected (tests.test_launch_cmd.TestBuildPieces) ... ok
test_non_shardable_rejects_multi_piece (tests.test_launch_cmd.TestBuildPieces) ... ok
test_overlapping_multi_gpu_pieces_rejected (tests.test_launch_cmd.TestBuildPieces) ... ok
test_session_name_format (tests.test_launch_cmd.TestBuildPieces) ... ok
test_shardable_two_pieces_get_shard_flags (tests.test_launch_cmd.TestBuildPieces) ... ok
test_dry_run_does_not_probe_or_launch (tests.test_launch_cmd.TestCmdLaunchDryRun) ... ok
test_dry_run_prints_shard_commands_and_skips_register (tests.test_launch_cmd.TestCmdLaunchDryRun) ... ok
test_non_free_piece_rejects_all_and_no_register (tests.test_launch_cmd.TestCmdLaunchFullFlow) ... ok
test_success_registers_rich_pieces (tests.test_launch_cmd.TestCmdLaunchFullFlow) ... ok
test_verify_alive_failure_skips_register (tests.test_launch_cmd.TestCmdLaunchFullFlow) ... ok
test_missing_run_id_rejected (tests.test_launch_cmd.TestCmdLaunchValidation) ... ok
test_missing_track_rejected (tests.test_launch_cmd.TestCmdLaunchValidation) ... ok
test_unknown_task_rejected (tests.test_launch_cmd.TestCmdLaunchValidation) ... ok
test_cmd_mode_flags (tests.test_launch_cmd.TestParseLaunchArgv) ... ok
test_task_positional_and_flags (tests.test_launch_cmd.TestParseLaunchArgv) ... ok
test_fails_on_traceback_in_tail (tests.test_launch_cmd.TestVerifyAlive) ... ok
test_fails_when_session_gone (tests.test_launch_cmd.TestVerifyAlive) ... ok
test_ok_when_alive_and_no_traceback (tests.test_launch_cmd.TestVerifyAlive) ... ok

----------------------------------------------------------------------
Ran 21 tests in 0.314s

OK
```

```
$ python3 -m unittest discover -s tests -v   # whole-repo tests
```
```
Ran 56 tests in 0.551s

OK
```
(2 more than before the fix, i.e. the two newly added overlapping/non-overlapping tests; the rest of the cases' output lines are unchanged.)

```
$ python3 run.py selfcheck
```
Run in this fix round's worktree (`/home/y-guo/reproduce/new1-wt/20260808-par-T09-fix1`),
output `16 missing`, consistent with what the T09 first-round report recorded. All 16 lines are
`envs/*/venv`, `cprobe-env`, `mbert-env` and other third-party venv directories naturally not existing in this newly built
`git worktree` (not in git); confirmed to be "all present" running the same command in the main-repo
worktree (`/home/y-guo/reproduce/new1`).

### Commit list (fix round 1)

- `0160809`: `T09: fix F1, same-host-same-card de-dup switched to GPU-set overlap check, no longer just string equality`
  Changes: `ops/launch_cmd.py` (`build_pieces()`'s de-dup logic),
  `tests/test_launch_cmd.py` (two overlapping/non-overlapping tests added).

### Self-check findings and open questions (fix round 1)

- Only the de-dup part inside `build_pieces()` was changed; shard injection, session naming,
  `--cmd` mode, and other logic weren't touched, no opportunistic refactoring or change to something the ticket didn't name.
- gpu ids split on commas aren't checked for numeric validity (e.g. `"0,1,"` would split out an empty
  string), but the original code didn't do this check either, and this is out of this finding's fix scope,
  not added opportunistically.
