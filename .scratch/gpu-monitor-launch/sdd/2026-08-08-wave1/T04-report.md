# T04 report: Four training scripts wired to heartbeats

Ticket: `.scratch/gpu-monitor-launch/issues/04-train-heartbeat.md`
Branch: `ticket/20260808-par/T04`, base `5be5d0827fe959cc1c016c8f99221c4d6a4218c8`

## What was done

Implemented against the ticket's four acceptance requirements one by one. Steps followed `docs/plans/2026-08-08-gpu-monitor-launch.md` Task 4 (lines 449-491); anchors were first located on the spot with `grep -n "event=\"start\"\|event=\"step\"\|event=\"done\"\|steps ="`, since the four files' line numbers differ slightly from what the plan document gave (the plan document only gave anchors for mtool among the last three, with the rest marked "repeat the same pattern"). Actual anchors:

| File | start | step | done | steps variable |
|---|---|---|---|---|
| `pipeline/train/train_mbert_tool.py` | 185 | 207-210 | 222 | 172 |
| `pipeline/train/train_mbert_extract.py` | 467-474 | 516-519 | 545-546 | 453 |
| `pipeline/train/train_causal_tool.py` | 366-371 | 392-396 | 417 | 353 |
| `pipeline/train/train_causal_callgen.py` | 426-434 | 466-469 | 496 | 413 |

All four files follow the same pattern, each with four insertions:

1. In the import section (right after `import readonly_map`/the last module-internal import):
   ```python
   import sys as _sys
   from pathlib import Path as _Path
   _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / "ops"))
   import heartbeat
   ```
   All four files already had a bare `from pathlib import Path` (some also had a bare `import sys`); using the `_sys`/`_Path` aliases avoids shadowing, matching the insertion snippet given in the plan document.

2. Right after the `log(event="start", ...)` call, added `heartbeat.emit(0, steps, "step")`, a heartbeat with done=0, marking "model finished loading."

3. In the `gstep % 50 == 0` branch, right after the `log(event="step", ...)` call and **before** `run = 0.0` resets, added:
   ```python
   heartbeat.emit(gstep, steps, "step",
                  loss=round(run / (50 * args.accum), 4))
   ```
   The loss expression was copied per-file from that file's own already-existing moving-average formula in its `log(event="step")` call (all four files happen to use the same formula: `run / (50 * args.accum)`), not a separately invented one.

4. After the `log(event="done", ...)` call, added `heartbeat.emit(gstep, steps, "step", status="done")`.

- [x] Syntax check passes for all four files
- [x] The heartbeat module can be imported under both the mbert-env and cprobe-env training venvs
- [x] loss is taken from the moving average already present in each file's step log, inserted before the reset
- [x] commit

## How it was verified

**Syntax check** (ticket requirement + plan doc Step 3):

```
$ for f in pipeline/train/train_*.py; do python3 -c "import ast; ast.parse(open('$f').read())" && echo "$f ok"; done
pipeline/train/train_causal_callgen.py ok
pipeline/train/train_causal_tool.py ok
pipeline/train/train_mbert_extract.py ok
pipeline/train/train_mbert_tool.py ok
```

**Both training venvs import the heartbeat module**: the worktree does not have `mbert-env/`, `cprobe-env/` (these two directories are excluded by `.gitignore`, and `git worktree add` does not bring in untracked files); tested instead by using the main-repo's venv interpreters and pointing `sys.path` at the worktree's `ops/` directory. `heartbeat.py` itself was not changed this time, and what is being tested is "can this venv import the heartbeat module," which does not depend on which directory it physically lives in:

```
$ mbert-env/bin/python -c "import sys; sys.path.insert(0,'/home/y-guo/reproduce/new1-wt/20260808-par-T04/ops'); import heartbeat; print('mbert-env import ok', heartbeat.__file__)"
mbert-env import ok /home/y-guo/reproduce/new1-wt/20260808-par-T04/ops/heartbeat.py

$ cprobe-env/bin/python -c "import sys; sys.path.insert(0,'/home/y-guo/reproduce/new1-wt/20260808-par-T04/ops'); import heartbeat; print('cprobe-env import ok', heartbeat.__file__)"
cprobe-env import ok /home/y-guo/reproduce/new1-wt/20260808-par-T04/ops/heartbeat.py
```

**diff self-check**: `git diff --stat` shows each of the four files changed by 9 lines (4 insertions, 1-2 lines each), no change to any existing logic, existing `log()` calls, or existing variables. Each file was individually checked to confirm the line order of `heartbeat.emit(gstep, ...)` before `run = 0.0`.

Did not touch the `run.py` registry, did not run `selfcheck` (neither the ticket nor the plan requires it, and nothing new was added to or changed in the scope of the change).

## Commit list

- `f4b9f67`: `T04: wire four training scripts to heartbeats(unit=step, report moving-average loss)`: each of the four training scripts got 4 `heartbeat.emit` calls added, 36 lines total inserted, nothing deleted or changed.

## Self-check findings and open questions

- The plan document's Task 4 gave line numbers only for `train_mbert_tool.py`, and wrote for the rest "the other three cells repeat the same anchor," "variable names follow each file's actual state." This time anchors were located on the spot per the ticket's requirement via `grep`; all four files' `log(event="step")` loss formulas happened to be `run / (50 * args.accum)`, and no inconsistency in the value convention was found.
- `train_causal_tool.py` and `train_causal_callgen.py` already had a bare `import sys` at the top; the inserted `import sys as _sys` matches the snippet given in the plan document verbatim, using an alias to avoid conflicting with the existing `sys` usage, without touching any existing `sys` usage.
- No other open questions.
