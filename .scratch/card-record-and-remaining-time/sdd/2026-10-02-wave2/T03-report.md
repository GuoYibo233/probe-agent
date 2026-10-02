# T03 report: close a dead incarnation before a relaunch

Branch `ticket/2026-10-02-wave2/T03`, base `f37f0980fc62abfaa2d93cd90f7caf03cb4ddd9b`, head
`29c8de4`. Worktree `/home/y-guo/reproduce/new1-wt/2026-10-02-wave2-T03` (removed after the
commit; the branch is kept).

## 1. What was done

Requirement: before `launch()` or `refire()` appends a start row to a run that is still open and
whose pieces all read `dead` or `not started` (the `registry.launch_failed()` rule without its age
condition), append that incarnation's `launch_failed` finish row through `append_finish`, in the
same lock hold as the new start row; `retry` reaches it through the walk.

- `jobs/registry.py`
  - `incarnation_dead(verdicts)`: new. True when the launch has pieces and every one of them reads
    `dead` or `not started`. This is the verdict half of `launch_failed()`.
  - `launch_failed(started_at, verdicts)`: now `incarnation_dead(verdicts)` plus the age test. Its
    behaviour is unchanged. The old docstring said "`judge` calls every one of them `dead`"; it now
    states the rule as the code applies it (`dead` or `not started`).
  - `close_dead_incarnation(run_id, sessions) -> bool`: new. It takes `lock()`, which is
    re-entrant, so inside the caller's hold it only increments a counter. It folds the ledger and
    returns False when the run has no open start row. Otherwise it judges the open start row's
    pieces with `_judge_pieces` over the caller's `sessions`, which is the same derivation `ls`,
    `sync` and `cards_busy` read. When `incarnation_dead` holds, it appends the `launch_failed`
    finish row through `append_finish`, so the row carries the `card_record` ticket 01 builds
    there. The other fields are `counts {}`, `metrics {}`, `report null`, and `elapsed_s` measured
    from the open start row, the same shape `sync` writes.
- `jobs/launch.py`
  - `launch()`: calls `registry.close_dead_incarnation(run_id, sessions)` immediately before
    `registry.append_start(start_row)`, inside the existing hold. It passes the `sessions` the
    launch gate already probed. The walk and `retry` (through `_stage_step`, which calls the walk)
    both reach this point.
  - `refire()`: the `registry.live_sessions()` probe that `trajectory_record.release` used is now
    kept in `sessions`. `registry.close_dead_incarnation(run_id, sessions)` runs immediately before
    `registry.append_start`, inside the existing hold. A refire beside a live sibling piece (a
    healthy loop piece, a serving agent service) leaves the incarnation open, as before.
  - The docstrings of both functions list the new step in their hold.
- `tests/test_registry_concurrent_append.py` (the test seam: ticket 01's `CardRecordTest`). There
  are two new cases plus one shared fixture, `_dead_train_run`. The fixture is an open train run
  whose one piece, on card 0 of tokyo108, trained 4 steps and died of memory: it has a started
  stamp and no session, its beats carry `mem_gib`, and its log ends in the OOM error. In the
  fixture, sessions read as gone and cards 3 and 4 as free, so no host is probed.
  - `test_walk_relaunch_closes_the_dead_incarnation_before_its_start_row`:
    - It first checks that `close_dead_incarnation` with the piece's session alive appends nothing.
    - It then runs the real `launch.launch("train", ...)` on a setting loaded with
      `schema.load_frozen`. Only `_start_tmux` and `alive_check` are patched.
  - `test_refire_closes_the_dead_incarnation_before_its_start_row`: the real `launch.refire(...)`,
    with only `_start_tmux` patched.
  - Both cases assert three rows in order: start, then a `launch_failed` finish, then start. They
    also check:
    - the finish row's whole `card_record`: `launch` 1, the train task identity, the piece on an
      H100 with `peak_gib` 91.5, `failure` `memory`, the OOM line cut to 300 characters, and speed
      4 steps over 200 s, which is 72.0 per hour;
    - that the new start row holds card 3;
    - that the run is open again under the new start row.
- `README.md`: the `jobs/registry.py` and `jobs/launch.py` lines (the launch `writes:` field now
  names the finish row), and the test-module sentence for the two new cases.
- No `jobs/versions.yaml` row. No stage's code set holds `jobs/` or `run.py` (checked below).

## 2. How it was verified

All commands ran from the worktree with the main repo's interpreter, because `external/` is not
in git and so is absent from a worktree.

The new cases fail on the unfixed launcher. With `jobs/launch.py` reverted to HEAD and the new
registry kept:

```
FAIL: test_walk_relaunch_closes_the_dead_incarnation_before_its_start_row
AssertionError: Lists differ: [('start', 'launching'), ('start', 'launching')] != [('start', 'launching'), ('finish', 'launch_failed'), ('start', 'launching')]
FAIL: test_refire_closes_the_dead_incarnation_before_its_start_row
AssertionError: Lists differ: [('start', 'launching'), ('start', 'launching')] != [('start', 'launching'), ('finish', 'launch_failed'), ('start', 'launching')]
Ran 2 tests in 0.244s
FAILED (failures=2)
```

With the fix:

```
$ /home/y-guo/reproduce/new1/external/probe-env/bin/python tests/test_registry_concurrent_append.py -v
...
test_refire_closes_the_dead_incarnation_before_its_start_row (__main__.CardRecordTest...) ... ok
test_walk_relaunch_closes_the_dead_incarnation_before_its_start_row (__main__.CardRecordTest...) ... ok
...
Ran 17 tests in 0.617s
OK
```

`run.py selfcheck` (run again after the last edit):

```
$ /home/y-guo/reproduce/new1/external/probe-env/bin/python run.py selfcheck
selfcheck: 32 python files, 0 problems
exit=0
```

Every test module, each in its own process:

```
== test_registry_concurrent_append   Ran 17 tests in 0.675s   OK
== test_settings_keys                Ran 25 tests in 24.409s  OK
== test_probe_input                  Ran 19 tests in 2.024s   OK
== test_record_formats               Ran 16 tests in 0.101s   OK
== test_probe_eval                   Ran 15 tests in 2.059s   OK
== test_environment_and_build        Ran 22 tests in 0.075s   OK
== test_qwen3_family                 Ran 13 tests in 24.199s  OK
== test_packed_loss                  Ran 3 tests in 2.600s    OK
```

No code-era row is owed:

```
sample [] / build [] / train [] / eval [] / inject [] / score []   (code entries under jobs/ or equal to run.py)
versions.yaml diff lines: 0
```

After the tests, `git status` shows only the four intended files. The tests write only to the
temporary tree's `jobs/runs.jsonl`, because `launch.registry` is pointed at the temporary copy for
each case.

## 3. Commits

- `29c8de4` T03: a relaunch closes the dead incarnation it replaces before its start row
  (`jobs/registry.py`, `jobs/launch.py`, `tests/test_registry_concurrent_append.py`,
  `README.md`).

## 4. Self-review and open questions

- Scope: only the two start-row appends the ticket names call the new function. The CPU stages'
  start row in `run.py` (`_start_cpu_stage`) is unchanged. A CPU stage carries no card record, and
  the ticket does not name that path.
- Where the close sits: right before the start-row append, as the ticket says, and after every
  refusal the hold can still raise (no cards, a missing checkpoint, the split files). A refused
  relaunch therefore appends nothing. One consequence: `registry.free()` runs earlier in the same
  hold, while the dead incarnation is still open. If its start row is younger than
  `launch_timeout_s`, its piece's card still counts as reserved (`cards_busy`: young and owing
  work), so the relaunch lands on another card. This matches the behaviour before this ticket and
  is not changed here. Moving the close before `free()` would release that card to the relaunch;
  that would change placement, which is a decision for the owner.
- `refire()` reuses the sessions probe it already made for the claim release instead of probing a
  second time. The probe happens inside the same hold, before the card re-probe.
- Source of the logic: the rule is `registry.launch_failed()` and `registry.sync()`'s
  `launch_failed` branch (the same verdict derivation and the same row shape), restated as
  `incarnation_dead` plus `close_dead_incarnation`. No source outside the tree was used.
- Open question: none blocking.
