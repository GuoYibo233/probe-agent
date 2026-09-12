# T10 implementation report: Refire mode `launch --refire`

Ticket: `.scratch/gpu-monitor-launch/issues/10-refire.md`
Plan section: `docs/plans/2026-08-08-gpu-monitor-launch.md` Task 12
Branch: `ticket/20260808-par/T10` (worktree `/home/y-guo/reproduce/new1-wt/20260808-par-T10`, removed per protocol)

## What was done

The ticket's acceptance line is one item: "tests pass: a live session is rejected, non-FREE is rejected, on the success path the ledger piece's log and launched_at are updated with the command unchanged, and no second job appears." Point by point:

1. **Live session rejected**: `ops/launch_cmd.py` got a new `cmd_refire(argv)`; after finding the `idx`-th piece of `run_id` in the ledger, it first checks `LC.has_session(piece.host, piece.session)`, and if true, `SystemExit`, with an error message naming "refire only applies to dead pieces."
2. **Non-FREE rejected**: the target card takes the value given by `--piece`, defaulting to the ledger's original host/gpus if not given; if `LC.probe_free(host, gpus)` is non-FREE, `SystemExit`, with the error carrying the reason text returned by `probe_free`, so an incident agent can use it to switch cards and retry (per spec user story 31).
3. **Success path**: once probed FREE, the log switches to a new filename `<sess>.r<refires+1>.log`
   (`refires` read from the sampler's on-disk cumulative state `monitor/state.json`, keyed by `job#idx`, treated as 0 if never sampled); `build_inner()` wraps the ledger's stored `piece["cmd"]` as-is inside `cd/CUDA_VISIBLE_DEVICES/tee` (not querying the task registry, not appending shard flags) and sends it into `LC.tmux_launch(host, sess, inner)`, keeping the session name unchanged; then `gpu_jobs.mutate_reg()` only changes this one piece's `host/gpus/log/launched_at` fields in place, leaving the job itself and other pieces untouched, and **does not call `LC.register_all()`**. No new `record.py start`, no repeated ledger append, refire does not produce a second job.

Entry point: `run.py launch` remains the single command-line entry point; `cmd_launch(argv)` forwards the whole
`argv` to `cmd_refire(argv)` as soon as it sees `--refire` in it, without reusing the original
`parse_launch_argv` (that one is for "launching a new task," with different field semantics). Added
`parse_refire_argv(argv)`, which only recognizes four flags: `--refire <run_id>` / `--idx <int>` / `--piece <host:gpus>` / `--allow-dirty`,
rejecting any other flag directly (refire is not a new task, so it shouldn't pass through task parameters).
Still goes through `gate_dirty` before refiring (`--allow-dirty` lets it through), consistent with the interface signature given
in the plan document.

Two documentation spots were also changed:
- `ops/launch_cmd.py`'s top docstring got a line pointing to `cmd_refire`.
- `run.py`'s top usage docstring got a line added for `launch --refire`'s invocation form and a one-sentence behavior note (neither the ticket nor the plan required this, but this is documentation for the same command's usage. Without it, someone reading `run.py`'s top comment later would not find this mode).

`launch_cmd.py` itself had no MAP.md line since ticket 09 landed it (checked `MAP.md`'s full text: `launch_common.py`/`launch_probe.py` both have lines, `launch_cmd.py` doesn't). This is a pre-existing gap left over from T09, not within this ticket's scope. No fix was made opportunistically; refire still lives in the same `launch_cmd.py` file, so if a MAP.md line is ever added for this file, `--refire` should be mentioned in it too.

## How it was verified

TDD order: first added `TestCmdRefire` to `tests/test_launch_cmd.py` (6 cases: live session rejected, non-FREE rejected, success path updates the ledger without adding a new job, `--piece` overrides the target card, nonexistent run_id rejected, out-of-range idx rejected), ran once to confirm it failed (`SystemExit: launch needs a task name...`, because `--refire` was not yet wired into `cmd_launch`), then wrote the implementation, then ran green.

```
python3 -m unittest tests.test_launch_cmd.TestCmdRefire -v
```
Output: all 6 cases `ok`.

```
python3 -m unittest discover -s tests -v
```
Tail output: `Ran 68 tests in 3.579s` / `OK` (including this ticket's 6 new cases, the other 62 being the repo's existing tests, all green, no regression from this change).

```
python3 run.py selfcheck
```
Run in the worktree: `selfcheck: 63 tasks / 4 recipes, 16 missing`, all missing items being venv interpreter paths (like `mbert-env/bin/python`, `envs/appworld/venv/bin/python`). Confirmed: these `*-env/`, `.venv/` directories are in `.gitignore`, existing physically only in the main repo `/home/y-guo/reproduce/new1/`, and `git worktree add` does not carry them; running the same command in the main repo (unchanged HEAD) gives `selfcheck: 63 tasks / 4 recipes, all present`. The task count and recipe count (63/4) match between the worktree and the main repo. This change did not touch any `TASKS`/`RECIPES` entries; the `16 missing` is environment noise caused by the worktree itself missing venvs, not a registry problem introduced by this ticket.

## Commit list

- `5dd8462` (branch `ticket/20260808-par/T10`): `T10: launch --refire dead-piece refire (live session rejected, non-FREE rejected, only changes the ledger without a new record)`. Changed `ops/launch_cmd.py` (`cmd_refire`/`parse_refire_argv`/`cmd_launch` dispatch), `run.py` (top usage docstring got one line added), `tests/test_launch_cmd.py` (`TestCmdRefire` six cases).

## Self-check findings and open questions

- The `refires` count is read from the sampler's on-disk `monitor/state.json` (`ops/sampler.py`'s `load_state()`/`piece_key()`), not a field on the ledger. The ledger piece itself does not store `refires`. This source is spelled out in one sentence in plan Task 12 ("the sampler will see launched_at changed and automatically reopen this piece's heartbeat time axis," already implemented by Task 6, with `refires` incrementing); read `ops/sampler.py`'s `update_piece_state()` and confirmed this chain is already in place, no separate counting system was started. If a refire happens within a window before the sampler has ever sampled this piece position (just launched and immediately died, not yet sampled), `refires` reads 0, and the log suffix will be `.r1.log`; if two consecutive refires both happen before the sampler catches up, both will read `.r1.log` (the old log file is not overwritten, just written into the same colliding filename with append). Neither the ticket nor the plan covers this consecutive-refire window's acceptance requirement, and no extra handling was added (YAGNI), noted here for reference by later tickets (e.g. ticket 12, incident triggering).
- Refire launching does **not** call `verify_alive()` (the 30-second aliveness check). Plan Task 12's interface description lists steps up through "mutate_reg updates... doesn't open a new record, doesn't re-register," without mentioning this verify-alive step, and the ticket's acceptance line doesn't mention it either; the normal `launch` mode's verify-alive is an independent design decision (spec user story 14), refire goes through the same `tmux_launch`, but doesn't copy this step. Implemented per the ticket's literal wording, no verify-alive added proactively.
- A theoretical race window exists between probing the card and `mutate_reg` (`has_session`/`probe_free` happen outside the lock, while the final ledger update happens inside `gpu_jobs.mutate_reg`'s file lock): this is consistent with the existing `LC.register_all()` pattern (also probing outside the lock, writing inside the lock), not a new pattern introduced by this ticket. Followed the repo's existing convention, no separate locking scheme invented.

## Fix round 1 (F1)

Worktree `/home/y-guo/reproduce/new1-wt/20260808-par-T10-fix1` (checked out the existing branch `ticket/20260808-par/T10`, removed per protocol).

### F1: Refire silently drops the original command's env variable prefix

**Problem pointed out by review**: `cmd_refire()` calls `build_inner(piece["cmd"], job["workdir"], gpus, new_log)` without passing an `env` argument, and `build_inner` defaults to `env=None`. The ledger piece at the time only stored `host/gpus/session/log/cmd/launched_at/kind/stall_line/escalate_line`, storing neither `env` nor the task name, so refire has no way to recover the original task's env prefix. If some `TASKS` task defines a non-empty `env`, refiring one of its pieces would silently drop these environment variables, with no error at all.

**Root cause**: on the normal launch path in `cmd_launch()`, `env = t.get("env", {}) if t is not None else {}` is only used in a local variable to assemble `build_inner`, and was never written into the ledger's rich piece, so by refire time this information is already gone; it's not that the parameter was forgotten when passing it, it's that the ledger schema never had a place for this field from the start.

**How it was fixed**:
1. `ops/launch_cmd.py` `cmd_launch()`: `rich_pieces`'s dict construction gets an `env=env` field added, storing the already-computed `env` dict as-is into the ledger piece.
2. `ops/launch_cmd.py` `cmd_refire()`: reads `env = piece.get("env") or {}`, passing it to `build_inner(piece["cmd"], job["workdir"], gpus, new_log, env)` (previously not passed at all). When `piece.get("env")` comes up empty for an old ledger job registered before this fix (which has no `env` field), it's treated as an empty dict, no error, behaving equivalently to before the fix (currently no `TASKS` entry in the repo uses a non-empty `env`, so backward compatibility doesn't lose any real behavior that has ever actually happened).
3. Synced two docstrings: `launch_common.py`'s `register_all()` description got `env` added to the piece field list; `launch_cmd.py`'s `cmd_refire()` docstring got a paragraph added explaining where the env prefix is recovered from and the old-ledger compatibility behavior.

The scope of the change only touched these two points, without opportunistically adding a `task` name field to the piece (the review's detail also mentioned that the ledger doesn't store the task name either; but the ticket needs to fix env-prefix loss, this one specific silent failure. The task name currently has no read path using it, adding it would be a field with no corresponding acceptance requirement, YAGNI, not added).

### How it was verified

Added two regression tests to `tests/test_launch_cmd.py`'s `TestCmdRefire`:
- `test_env_prefix_restored`: ledger job `erun`'s piece carries `"env": {"FOO": "bar", "BAZ": "qux"}`, and after refiring, asserts the inner command received by `tmux_launch` contains both `FOO=bar`, `BAZ=qux`, and the original cmd.
- `test_missing_env_field_defaults_empty`: reuses the `rrun` job from `setUp` which has no `env` field, refire goes through the success path without erroring, with the inner command containing cmd as-is.

```
python3 -m unittest tests.test_launch_cmd.TestCmdRefire -v
```
Output: all 8 cases `ok` (the original 6 plus 2 new this round).

```
python3 -m unittest discover -s tests
```
Tail output: `Ran 70 tests in 3.576s` / `OK` (68 → 70, the 2 new regression tests, everything else green, no regression).

```
python3 run.py selfcheck
```
Run in the worktree: `selfcheck: 63 tasks / 4 recipes, 16 missing`, missing items consistent with what the previous round's report recorded (all environment noise from the worktree itself missing venv interpreter paths, like `mbert-env/bin/python`), task/recipe counts (63/4) unchanged, this change did not touch any `TASKS`/`RECIPES` registry entry.

### Commit list

- `6595d1a` (branch `ticket/20260808-par/T10`): `T10: refire restores the original task's env prefix (F1)`. Changed `ops/launch_cmd.py` (`cmd_launch`'s rich piece gets an `env` field, `cmd_refire` reads it back and passes it to `build_inner`, two docstrings updated), `ops/launch_common.py` (`register_all` docstring supplemented with the `env` field), `tests/test_launch_cmd.py` (two regression tests).

### Self-check findings and open questions

- Grepping the whole repo's `TASKS` registry currently shows no entry using a non-empty `env`, so this fix currently has no real task that can trigger a differentiated-behavior verification (the assertion "would drop it before the fix, doesn't drop it after" only holds in the test's synthetic scenario). The review finding itself also points this out ("the interface itself is meant for exactly this scenario"), and the fix's approach is to have the ledger schema add this field, and refire symmetrically read it back, not wait for a real non-empty-env task to appear before adding it.
- No `task`-name field was opportunistically added to piece: F1's detail mentions that the ledger doesn't store the task name either; but there's currently no read path that needs "refire time reverse-lookup task name" (cmd is already stored as-is, probe_free/has_session don't need the task name), so adding this field has no corresponding acceptance requirement, and per YAGNI it wasn't added. If a follow-up ticket (like ticket 12, incident triggering) needs to do extra validation by task name at refire time, that should be evaluated separately.

## Fix round 2 (N1)

Worktree `/home/y-guo/reproduce/new1-wt/20260808-par-T10-fix2` (checked out the existing branch `ticket/20260808-par/T10`, removed per protocol).

### N1: The refire fix writes the task's env value verbatim into `ops/jobs.json`, a git-tracked ledger

**Problem pointed out by review**: F1, in order to have refire restore the env prefix, added a line `env=env` to `cmd_launch()`'s `rich_pieces`, storing the already-computed env dict as-is into the ledger. `ops/jobs.json` is a git-tracked file (confirmed with `git ls-files ops/jobs.json`), and per the repo's existing workflow, ledger changes are routinely committed. If some `TASKS` task down the line defines a non-empty env (especially a token freshly pulled from a local environment variable/secrets manager), this value would ride the normal launch flow straight into the git repository, with no scrubbing or exclusion mechanism intercepting it at all.

**Root cause**: F1 mapped the requirement "refire needs to restore env" directly into "store the env's value in the ledger piece." This conflates two things. What refire needs is the *ability* to find the env again, not the env's raw value itself. Before F1, the env dict at launch time was only ever meant to be a local variable for assembling `build_inner` (that's how it was before this fix); F1 gave it an extra persistence path into a git-tracked file, which is a newly introduced risk surface, not one that was already there.

**How it was fixed** (scope limited to this one risk point, no opportunistic broader refactor):

1. `ops/launch_cmd.py` `cmd_launch()`: swapped the `rich_pieces`'s `env=env` field for `task=p["task"]`, storing only the task name (a string, containing no secrets), not the env's actual key-values. Under `--cmd` mode, `p["task"]` is already `None`, matching the previous `env` falling back to `{}`, without introducing an extra `--cmd`-mode difference.
2. `ops/launch_cmd.py` `cmd_refire()`: no longer reads `piece.get("env")` from the ledger; instead does `task_name = piece.get("task")` → `t = TASKS.get(task_name) if task_name else None` → `env = t.get("env", {}) if t is not None else {}`, computed fresh at call time, exactly symmetric with how `cmd_launch()` derives env (`t.get("env", {}) if t is not None else {}`), just with the data source switched from "an old snapshot in the ledger" to "the current definition in the TASKS registry." The env's actual key-values now live only in this one refire call's local variable, never persisted into any file.
3. Synced both docstrings' wording: `launch_common.py`'s `register_all()` piece field list swaps `env` for `task`, adding a sentence pointing to finding N1; `launch_cmd.py`'s `cmd_refire()` docstring says env is now "computed fresh by reverse-looking-up the current TASKS definition" rather than "a ledger snapshot," and points out the tradeoff this brings. If the task registry's env definition was changed by someone between the original launch and the refire, refire gets the value after the change, not the one from the original launch; this tradeoff is traded for the harder guarantee that "the raw env value never gets written into a git-tracked file."

**Scope boundary**: did not touch `probe_free`/`has_session`/other ledger fields/`--piece`-override logic, none of which are within N1's problem scope. Also did not add encryption/scrubbing for "the env value itself". Not persisting it at all removes the need for scrubbing, which is simpler and more thorough.

### How it was verified

TDD order: first changed the tests in `tests/test_launch_cmd.py` that depended on the old `env` field, ran once to see the expected failure (refire can no longer pass out the original env, because the ledger no longer stores `env` and `TASKS` has no corresponding task registered either), then changed the implementation, then ran green.

Tests changed:
- `test_env_prefix_restored` (`TestCmdRefire`): the ledger piece changed from storing `"env": {...}` to storing `"task": "envtask"`; the test uses `patch.dict(LCC.TASKS, {"envtask": fake_task(env=...)})` to register a task with a non-empty env on the spot, asserting that after refire the inner command still contains both `FOO=bar`/`BAZ=qux`/the original cmd. F1's acceptance assertion kept as-is, only the source of env changed.
- `test_missing_env_field_defaults_empty` renamed `test_missing_task_field_defaults_empty_env`: same meaning (an old ledger with no task field, refire doesn't error, cmd re-sent as-is), renamed because now the missing field is `task` not `env`.
- Added `test_unknown_task_field_defaults_empty_env`: the ledger's stored `task` name isn't in the current `TASKS` (the scenario where the task was later decommissioned), refire must not error because of this, reverse-lookup coming up empty treated as `{}`.
- `TestCmdLaunchFullFlow`'s `test_success_registers_rich_pieces`: the field-list check swapped `env` for `task`, with a line added asserting `pieces[0]["task"] == "faketask"`.
- Added `test_success_does_not_persist_raw_env_values` (`TestCmdLaunchFullFlow`): task defines `env={"HF_TOKEN": "shh-do-not-commit-me"}`, and after launching, asserts the tmux inner command normally carries this env (the launch itself isn't weakened), but the rich piece passed to `register_all()` has `assertNotIn("env", pieces[0])`, and `repr(pieces[0])` does not contain this secret string. This is N1's direct regression test, asserting "the secret value does not flow into the ledger."

```
python3 -m unittest tests.test_launch_cmd -v
```
Tail output: `Ran 31 tests in 0.328s` / `OK` (`TestCmdLaunchFullFlow`'s 5 + `TestCmdRefire`'s 8 + the other 18, all green, including this round's 4 changed/renamed cases).

```
python3 -m unittest discover -s tests
```
Tail output: `Ran 72 tests in 3.479s` / `OK` (70 → 72, net +2: 1 renamed with no net change, 2 new, all green, no regression).

```
python3 run.py selfcheck
```
Run in the worktree: `selfcheck: 63 tasks / 4 recipes, 16 missing`, missing items consistent with the previous two rounds' reports (all environment noise from the worktree itself missing venv interpreter paths). Running the same command in the main repo (unchanged HEAD) gives `selfcheck: 63 tasks / 4 recipes, all present`, task/recipe counts matching between the two. This change did not touch any `TASKS`/`RECIPES` registry entry.

Also grepped to confirm the change did not miss any read path: `grep -rn '"env"\|piece.get("env")' ops/*.py` (excluding tests) leaves only the two lines in `ops/launch_cmd.py` where `cmd_launch()`/`cmd_refire()` compute env fresh from `TASKS[task]["env"]`, and one line of documentation comment in `launch_common.py`. `ops/sampler.py`/`ops/gpu_jobs.py`/the web and json outlets have never read the ledger piece's `env` field (no other consumer since F1 landed), so removing this field now doesn't affect any other module.

### Commit list

- `55a0d0e` (branch `ticket/20260808-par/T10`): `T10: refire env no longer persisted into the ledger verbatim, switched to storing the task name and computing/passing it fresh (N1)`. Changed `ops/launch_cmd.py` (`cmd_launch`'s rich piece swaps `env` for `task`, `cmd_refire` reverse-looks-up `TASKS[task]["env"]` and computes/passes it fresh, docstrings updated), `ops/launch_common.py` (`register_all` docstring field list synced), `tests/test_launch_cmd.py` (2 cases reworked + 2 new).

### Self-check findings and open questions

- **The semantic difference between an env snapshot and a fresh lookup**: the env refire now restores is "the current definition in the TASKS registry," not "a snapshot from the moment of the original launch." If someone changed `TASKS[task]["env"]` between the two moments (e.g. swapped in a new token), refire will use the new value, not the one the original task actually ran with. Neither the ticket nor the review required the stronger property of "reproduce the original launch environment byte-for-byte," and this difference is itself the tradeoff for the harder guarantee that "the env value never gets written to git," noted here for follow-up tickets, no extra handling added.
- **The variable name `t` in `cmd_refire()` shares a name with, but doesn't scope-collide with, `cmd_launch()`'s existing `t = TASKS.get(p["task"])`**: `cmd_refire()`'s newly introduced local variable `t = TASKS.get(task_name)` is a local variable of a different function from `cmd_launch()`'s function body's `t`, with no shadowing or cross-talk; reusing the same variable name is to stay consistent with `cmd_launch()`'s existing naming convention of "using `t` for the task definition dict," not creating a cognitive burden with a different name.
- Still no secret-scrubbing mechanism added for piece, because it's simply not persisted, no scrubbing layer is needed. If a future need arises for "deliberately keeping some non-secret env values on record in the ledger for audit purposes," that's a different, opposite-direction need from N1, and would need a new ticket to evaluate separately, not opportunistically done within this round's scope.
