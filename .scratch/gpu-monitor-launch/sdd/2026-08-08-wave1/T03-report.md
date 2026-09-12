# T03: Collection script wired to heartbeats (`run_appworld.py`) report

Ticket: `.scratch/gpu-monitor-launch/issues/03-collect-heartbeat.md`
Dependency: 01 (`ops/heartbeat.py`, already resolved on main, commit c890cec)
Step source: `docs/plans/2026-08-08-gpu-monitor-launch.md` Task 3 (lines 390-445)

## What was done

Implemented against the ticket's three acceptance requirements one by one, all landing in `envs/collect/run_appworld.py`:

1. **Heartbeat import**: after the `sys.path.insert` line, added
   `sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ops"))`
   and `import heartbeat  # noqa: E402`, placed before `from common import Chat, TrajLog`
   (lines 15-17).

2. **Emit done=0 right before the main loop**: after the print of the `shard ... exp=...` line and before
   `for tid in ids:`, added
   ```python
   tok_in = tok_out = 0
   n_done = 0
   heartbeat.emit(0, len(ids), "task", tok_in=0, tok_out=0)
   ```
   (lines 80-82). `heartbeat.emit` is the module already landed by T01, with signature
   `emit(done, total, unit, *, tok_in=None, tok_out=None, loss=None, status=None, stream=None)`.

3. **Advance done and accumulate tokens per question**:
   - After `g = chat(msgs)`, added
     `tok_in += g["usage"]["in"]; tok_out += g["usage"]["out"]`
     (lines 105-106). The field names `in`/`out` on `g["usage"]` come from the existing
     `envs/collect/common.py:161,182,220-221`; `common.py` was not modified.
   - The resume SKIP branch (before the `continue`) added `n_done += 1` and one
     `heartbeat.emit(n_done, len(ids), "task", tok_in=tok_in, tok_out=tok_out)`
     (lines 88-92). The ticket specifically calls out "resume-skipped questions still advance done", covered here.
   - Every question's normal wrap-up (after the `print(f"task={tid} steps=...")`) similarly added
     `n_done += 1` plus one heartbeat (lines 134-138).
   - At the end of `main()`, after the `for tid in ids:` loop finishes, added a normal-completion marker:
     `heartbeat.emit(n_done, len(ids), "task", tok_in=tok_in, tok_out=tok_out, status="done")`
     (lines 140-141).

All three acceptance items (syntax check + --help, done advances for both regular questions and SKIP + status=done at loop end, commit)
are complete.

## How it was verified

The ticket specifies verifying with a syntax check and `--help` under the appworld venv (proving the heartbeat module
can be imported inside that venv, which is the real test of the "stdlib-only" constraint).

The entire `envs/appworld` directory is gitignored (venv/data/runs are all excluded from git),
`git worktree add` will not carry it into a new worktree, so the venv physically exists only in the main repo,
`/home/y-guo/reproduce/new1/envs/appworld/venv/`. The script itself uses the absolute path
`os.chdir("/home/y-guo/reproduce/new1/envs/appworld")`, independent of the worktree location,
so pointing directly at the main-repo venv to run the worktree's script file is equivalent, and is
the only feasible way to verify this.

```
$ /home/y-guo/reproduce/new1/envs/appworld/venv/bin/python -c \
    "import ast,sys; ast.parse(open('envs/collect/run_appworld.py').read()); print('syntax ok')"
syntax ok

$ /home/y-guo/reproduce/new1/envs/appworld/venv/bin/python envs/collect/run_appworld.py --help
usage: run_appworld.py [-h] --base-url BASE_URL --model MODEL [--split SPLIT]
                       [--n N] [--max-steps MAX_STEPS] --outdir OUTDIR
                       [--exp EXP] [--api {raw,chat,harmony}]
                       [--reasoning-effort REASONING_EFFORT]
                       [--start-date START_DATE] [--shard-id SHARD_ID]
                       [--num-shards NUM_SHARDS] [--resume]
options:
  ...
```

The `--help` output printed all the way through (all args included), proving `import heartbeat` succeeds under the
appworld venv (stdlib-only constraint), without triggering any ImportError.

Also ran `python3 -c "import py_compile; py_compile.compile(...)"` (a second syntax pass):
`py_compile ok`.

The ticket did not name a unit-test seam for this (unit tests for heartbeat emit/parse are already covered by T01); this
change is instrumentation calls inserted into a script, with no new independently-unit-testable pure functions, so no separate test
file was written. Per the implementer's protocol of "add tests at the changed boundary if not otherwise specified," verification at that boundary is
exactly the `--help` run the ticket specified, which has already been run.

`run.py selfcheck` run in this worktree reports 16 "missing interpreter" items (appworld/alfworld/
tau2/toolhop/bfcl venvs etc. all missing), because these venv directories are themselves
gitignored and not part of the git worktree, not a problem introduced by this change. In the main repo
`/home/y-guo/reproduce/new1`, running the same `python3 run.py selfcheck` gives
"62 tasks / 4 recipes, all present". This ticket did not change the `run.py` registry, so this is
not a case of "changed something related to the registry" that would make this a hard gate, but the main-repo-side selfcheck was still confirmed clean.

## Commit list

- `9838281`: `T03: collect: wire run_appworld to heartbeats (per-question done/cumulative tokens, done=0 marks load complete)`
  (worktree `/home/y-guo/reproduce/new1-wt/20260808-par-T03`, branch
  `ticket/20260808-par/T03`, diff 1 file changed, 17 insertions)

## Self-check findings and open questions

- Self-checked the full diff: only `envs/collect/run_appworld.py`, 17 lines added,
  no deletions or changes to any existing logic lines, no changes beyond the ticket's scope.
- No new dependency introduced, `common.py` was not touched (the ticket explicitly said "no need to change common.py").
- The `run.py` registry was not touched. This ticket does not need it, and how
  `envs/collect/run_appworld.py` is invoked (`python3 run.py collect-aw ...`) has not changed.
- Open question: `heartbeat.emit`'s `tok_in`/`tok_out` are passed as "the cumulative value at this moment"
  rather than an increment, which is consistent with the heartbeat protocol's definition that "tok_in/tok_out are both cumulative values" (spec.md's
  "heartbeat protocol" section), with no ambiguity in the writing; noted here so the reviewer knows this was checked and
  not overlooked.
- No other open questions; no NEEDS_CONTEXT or BLOCKED conditions triggered.
