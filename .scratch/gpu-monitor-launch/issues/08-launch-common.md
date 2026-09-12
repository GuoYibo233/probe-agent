# 08 — Common launch pieces

**What to build:** The three common launch capabilities are collected into
one module: card probing (ssh checks the target card's compute processes;
either a process present or a probe failure counts as non-FREE,
fail-closed), the tmux launch template (carried over as-is from
launch-probe, the expand step of expand-then-consolidate), and the three
registrations in one go (the ledger's rich piece, the experiment record's
record start, and the product directory's RUNMETA, with rejecting a
duplicate run_id as the guardrail). This ticket does not change the
behavior of any existing launcher. Steps follow Task 10 of the
implementation plan.

**Blocked by:** None — can start immediately

**Status:** resolved

- [ ] Card-probing tests pass: three inputs, free card, occupied, probe
  timeout, map to three distinct returns
- [ ] Registration tests pass: the ledger gets a rich piece with all
  fields present, and a second call with a duplicate run_id is rejected
- [ ] commit

## Comments

- 2026-08-08 ticket-run: DONE. Branch ticket/20260808-par/T08 (base
  5be5d08, head c55e47a, added ops/launch_common.py +126,
  tests/test_launch_common.py +184, MAP.md +1), 29 tests all green and
  selfcheck passed after merging into main. 0 fix rounds. One leftover
  minor: launch_common.py's ROOT variable is defined but unused (dead
  code, does not block merging). Four cannotVerify items: the first was
  re-run and verified by the reviewer themselves across 14 test cases;
  the other three (whether the convention of not writing the key when
  monitor=None matches T09's caller, the display effect of comma-joined
  values in a multi-piece record start, and behavior consistency after
  T13's reverse import) are cross-ticket matters, already transcribed
  into ticket 09's Comments, with the last one to be checked when T13
  wraps up. Report: sdd/2026-08-08-wave1/T08-report.md.
