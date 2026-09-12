# 01 — Heartbeat module and verdict engine, unit tests all green

**What to build:** The script side now has a single entry point for emitting
heartbeats (emit prints one prefixed JSON line, parse only recognizes valid
heartbeat lines); the monitoring side now has a single convention for
computing verdicts (six verdict cells in fixed priority order, the verdict
line and escalation line adapting automatically, two rate flavors, average
and recent, all pure functions with zero IO). Steps follow Task 1 and Task 2
of the implementation plan (`docs/plans/2026-08-08-gpu-monitor-launch.md`);
the test code is ready-made in the plan.

**Blocked by:** None — can start immediately

**Status:** resolved

- [ ] Heartbeat tests pass: required fields all present, optional fields
  absent when not given, parse round-trips consistently, garbage lines
  return None
- [ ] Verdict tests pass: at least one test case per verdict cell (six
  total), the verdict-line floor, the warm-up cap, a probe failure not
  being judged as dead, and edge cases for all four service-type cells
- [ ] Both modules use only the standard library, with all constants
  collected in the verdict engine's DEFAULTS config
- [ ] `python3 run.py selfcheck` passes, each task committed separately

## Comments

- 2026-08-08 ticket-run: DONE. Commit range ae41f27..ba3cdbb (c890cec
  heartbeat module ops/heartbeat.py, ba3cdbb verdict engine ops/verdicts.py,
  landed directly on main, back when it was still serial-wave mode). Tests
  15/15 green (test_heartbeat 4 + test_verdicts 11), selfcheck passed.
  Review: zero findings, zero cannotVerify, 0 fix rounds, no leftover
  minors, no implementer concerns. Report: sdd/2026-08-08-wave1/T01-report.md.
