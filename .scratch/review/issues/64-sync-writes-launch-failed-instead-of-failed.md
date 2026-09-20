# 64 sync writes `launch_failed` for a run that died after running, and writes nothing at all inside the first launch_timeout_s

Status: needs-triage
Severity: minor
File: jobs/registry.py:1137
Contract: 8.2 (the five writers of the finish row; "when `run.py sync` finds a run with no `done.json` **whose pieces `judge` calls `dead`** (`failed`)")
Errata: not recorded

## Finding

8.2 gives `sync` its own word. The code writes the other one, and gates it on an age the
contract's sync rule does not have:

```python
        if launch_failed(start["t"], verdicts):
            row = {
                "ev": "finish", "t": _now(), "run_id": run_id, "status": "launch_failed",
                ...
```

with

```python
def launch_failed(started_at: str, verdicts: list[str]) -> bool:
    return (bool(verdicts) and all(v == "dead" for v in verdicts)
            and _age_s(started_at) > DEFAULTS["launch_timeout_s"])
```

Two deviations follow from reusing one predicate for both writers:

1. The status word. 8.2's `failed` now has one writer left, `run.py`'s non-zero exit of a CPU
   stage (run.py:2106-2111); every run that came up, ran and then died is recorded
   `launch_failed`, the word 8.1 defines as "a piece that dies before it starts" / "a launch
   that never came up".
2. The age clause. 8.2's sync rule is "no `done.json` and every piece `dead`"; the code adds
   "and the start row is older than `launch_timeout_s`".

## Failure scenario

A `train` run launches, trains for six hours and its piece is killed by the node. `run.py
sync` appends `{"status": "launch_failed"}` for it. `jobs/RESULTS.md`'s status column — the
only record of what became of the run, since the start row is never rewritten (8.1) — then
says the launch never came up, and `run.py find` shows the same word for it as for a run whose
`tmux new-session` failed on an unreachable host. A reader cannot tell the two apart without
opening the run directory.

Second case: a `sample` run whose six loop pieces all die three minutes in (a bad interpreter
path, an import error after the first beat). `run.py sync` folds it, `judge` calls every piece
`dead`, but `_age_s(start["t"])` is 180 s, so `launch_failed()` is false and sync writes
nothing and reports "0 run(s)". The row stays `launching` in `RESULTS.md` until someone runs
`sync` or `ls` again after the half hour is up.

## Proposed fix

Keep one predicate per rule, as 8.2 has them. `launch_failed()` stays what 8.1 defines — all
pieces dead and the start row past `launch_timeout_s` — and is what `run.py ls` writes its row
from. `sync()` closes a run whose open launch wrote no `done.json` and whose pieces `judge`
calls `dead` with `status: "failed"`, with no age condition, and writes `launch_failed`
instead when `launch_failed()` also holds, so the earlier of the two states keeps the word 8.1
gives it.
