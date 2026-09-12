# 10 — Refire mode --refire

**What to build:** `run.py launch --refire` relaunches a dead piece from
the ledger under its original command: it's rejected if the session is
still alive (refire is only for dead pieces); the target card is either
the one specified or the original, probed on the spot the same as any
launch, and rejected with a clear error if not FREE (the incident agent
uses the error to switch cards and retry). On success, this piece slot's
four-tuple in the ledger is updated and launched_at is refreshed; the
session name stays the same but the log switches to a new file; no new
record is opened and there's no repeat registration, since a refire is
not a new job. When the sampler sees launched_at change, it automatically
restarts that piece's heartbeat timeline. Steps follow Task 12 of the
implementation plan.

**Blocked by:** 09 launch subcommand

**Status:** resolved

- [ ] Tests pass: a live session is rejected, a non-FREE card is
  rejected, and the success path updates the ledger piece's log and
  launched_at with the command unchanged and no second job appearing
- [ ] commit

## Comments

- 2026-08-08 ticket-run: DONE. Branch ticket/20260808-par/T10 (base
  8dfdec0, head 55a0d0e, launch_cmd.py +115, launch_common.py minor
  tweak, run.py +3, tests +185), 72 tests all green and selfcheck's 63
  tasks in place after merging into main. 2 fix rounds, no leftover
  minors, no cannotVerify. Three concerns noted as-is: launch_cmd.py is
  missing a MAP.md line (a pre-existing gap from T09, left for T17's MAP
  update, to be checked at T17's wrap-up); firing refire twice in a row
  within a window the sampler hasn't caught up to collides on the same
  .r1.log suffix (append writes don't overwrite; the boundary is
  undefined); refire does not do a 30-second liveness check afterward
  (neither the ticket nor the plan required it). Report:
  sdd/2026-08-08-wave1/T10-report.md.
