# 61 sync() reads the ledger, done.json and the launch ordinal outside the lock, then appends a finish row from that stale read

Status: needs-triage
Severity: important
File: jobs/registry.py:1092
Contract: 8.6 (the lock: "`runs.jsonl` is appended only by `run.py` and `jobs/launch.py` ... both reach it through `registry.lock()`"), 8.2, 2.5
Errata: not recorded — the "1.5 / 8.2 (`done.json` and the finish row a reader owes it)" entry installs the launch-ordinal rule that this read is supposed to apply, and names `jobs/registry.sync` as the closer that applies it

## Finding

`sync()` holds no lock while it decides. Every input it judges on is read outside any hold,
and only the append takes one (through `append_finish`):

```python
def sync() -> list[str]:
    synced = []
    for run_id, entry in fold(_read_rows()).items():      # 1099: unlocked read of the ledger
        ...
        done = _read_json(run_dir / "done.json") or {}    # 1104
        if done.get("launch") == launch_ordinal(run_dir): # 1116: unlocked read of meta.json
            row = {... "status": "ok", ...}
            append_finish(run_id, row)                    # 1122: the only lock hold
```

and the same shape for the `launch_failed` row at :1137-1143. Between the read at :1099 and
the append at :1122 the run can be relaunched by another `run.py` on the same machine: a
relaunch appends a start row, which `fold` (:360-378) makes the newest, so the finish row
`sync` then appends closes **the new launch** and not the one it judged.

The sibling writer of the same row does hold the lock across the check. `run.py.
_close_failed_launches` (run.py:612-647) re-reads `registry.open_runs()` inside the hold and
appends "only while that row is still the judged one — same `run_id`, same `t`". `sync()` has
no such re-check.

## Failure scenario

Train run `train-<key>` is open; its piece died at step 40; nobody has closed the row.

1. Session A types `run.py sync`. It folds the ledger and reads `done.json` (the previous
   computation's, `launch: 1`) and `launch_ordinal` (1): they match, so it decides to append
   an `ok` finish row with that computation's counts, metrics and report.
2. Before A appends, session B types `run.py train_probe <setting>`. The gate passes (the
   piece is dead and has beats, so the young-row clause drops), B appends its start row,
   `registry.write_meta` grows `launches` to 2, and the trainer resumes on a card.
3. A appends `{"ev": "finish", "status": "ok", ...}` for that `run_id`. `fold` now returns
   `finish = A's row` for the live launch.

Result: the live run reads as finished everywhere. `open_runs` drops it, so `cards_busy`
(:611-644) stops counting its card and the next launch places another piece on it; the launch
gate (`jobs/launch.gate_open_row`) stops refusing the key, so a third `run.py` starts a second
trainer into the same directory; and `jobs/RESULTS.md` carries the previous computation's
counts and metrics as this launch's result — the exact mislabelling the launch-ordinal rule
was introduced to prevent.

The `launch_failed` branch has the same shape with a different payload: a run relaunched
between :1099 and :1143 is closed as a launch that never came up while its sessions are
running.

## Proposed fix

`sync()` takes `lock()` for the read and the appends, the way every other writer of
`runs.jsonl` does: probe `live_sessions()` once before the hold (it is a probe of the hosts,
not of the ledger, and 8.6 keeps ssh out of the hold), then inside one hold fold the rows,
read each run's `done.json` and `launch_ordinal`, and append. `lock()` is re-entrant, so the
`append_finish` calls inside nest as counter increments. The alternative that matches
`run.py._close_failed_launches` exactly — one hold per row that re-reads the fold and appends
only while the judged start row is still the open one — is equally correct and keeps the hold
short.
