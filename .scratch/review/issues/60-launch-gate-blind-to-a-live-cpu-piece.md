# 60 The launch gate calls every cpu piece dead, so two build/eval/score processes enter one run directory

Status: needs-triage
Severity: critical
File: jobs/launch.py:203
Contract: 2.5 (the launch gate's third clause), 8.5 (liveness is per kind), 2.3 (a CPU stage passes the same two gates), 9(c)#9
Errata: not recorded — the round-1 entry "2.5 / 8.5 (the launch gate's third clause)" defines *observed dead* as "not alive **and** has emitted at least one heartbeat beat (a `cpu` piece: has a recorded pid)", which presumes 8.5's per-kind `alive`; the code's `alive` has no cpu branch

## Finding

`piece_alive` tests one thing, the tmux session:

```python
def piece_alive(piece: dict, live_sessions) -> bool:
    host, session = piece.get("host"), piece.get("session")
    if not host or not session:
        return False
    failed_hosts = getattr(live_sessions, "failed_hosts", None)
    if failed_hosts and _canonical_host(host) in failed_hosts:
        return True
    return session in live_sessions
```

A `cpu` piece has no session — `run.py._start_cpu_stage` (run.py:1973-1974) writes
`"index": 0, "kind": "cpu", ... "session": None, "pid": proc.pid` — so `piece_alive` returns `False` for a CPU piece from
the instant its process starts. 8.5 states the opposite: "A `cpu` piece has no session ... so
it is alive while `os.kill(pid, 0)` on `login_host` succeeds, against the `pid` its start-row
entry carries". `jobs/registry._piece_verdict_dict` (jobs/registry.py:786-787) has that branch;
this copy of the rule does not.

The gate's third clause then collapses (jobs/launch.py:251-265):

```python
        age_s = now_ts - _parse_row_t(row["t"])
        if age_s < registry.DEFAULTS["launch_timeout_s"]:
            observed_dead = False
            for piece in pieces:
                alive = piece_alive(piece, live_sessions)
                if piece.get("kind") == "cpu":
                    has_emitted = piece.get("pid") is not None
                ...
                if not alive and has_emitted:
                    observed_dead = True
```

For a cpu piece `alive` is always False and `has_emitted` is always True (run.py records the
pid before it appends the start row), so `observed_dead` is True on the first pass and the
young-row clause never fires. Clause (a) is also always false (no session), so until the
process writes its first heartbeat beat the gate has nothing left to refuse on.

`build`, `eval` and `score` carry `"cards": False` (experimental_settings/schema.py:223, :256,
:314), so `run.py._stage_step`'s live-piece test at run.py:2036-2055 (`work_pieces` is filtered
to `loop` and `train`, and the test is guarded by `if entry["cards"] and work_pieces`) never
runs for them either, and `gate_open_row` is their only gate (run.py:1959-1966).

## Failure scenario

Session A: `external/probe-env/bin/python run.py train_probe ctool_qwen3_0pt6b`. The walk
reaches `build`, takes the lock, spawns the build process (run.py:2089), releases the
lock and blocks in `proc.wait()`.

Session B, two seconds later, runs the same command. `build`'s `done.json` does not exist yet,
so `fully_done` is False; `entry["cards"]` is False, so the live-piece test is skipped;
`gate_open_row` sees A's open start row, whose one cpu piece is "not alive" with a recorded
pid, and returns `None`. B spawns a second `data/build_training_dataset.py` into the same run
directory. Both write `examples.parquet`, `consumed.json` and `report.md` — the exact failure
2.3 names ("two sessions could start one `build` in the same second, both rewriting
`examples.parquet`, `consumed.json` and `report.md` in one directory") and 9(c)#9 says cannot
happen. The window is from the start row to the process's first beat (the interpreter start
plus, for `eval`, the read of the prediction frame); after the first beat the second clause
covers it.

`eval` and `score` are worse, not better: they are in `ALWAYS_RECOMPUTE`, so every `run.py
<workflow> <setting>` typed while an eval is running takes this path, and re-running the walk
command is the ordinary way to check on a run.

## Proposed fix

Give `piece_alive` 8.5's per-kind liveness, so the gate's `alive` means what the errata's
*observed dead* rule assumes: a `cpu` piece is alive while its recorded `pid` answers
`os.kill(pid, 0)` on the login machine; every other kind is alive while its session is live or
its host's probe failed. The pid test already exists once, as `jobs/registry._pid_alive`
(jobs/registry.py:562) — 8.5 puts the verdict rules in `jobs/registry.py`, so the single
source is that function made public and called from `piece_alive`, rather than a second
`os.kill` in `jobs/launch.py`.
