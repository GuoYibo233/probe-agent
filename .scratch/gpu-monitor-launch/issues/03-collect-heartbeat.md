# 03 — Collection script wires up heartbeats

**What to build:** The collection script run_appworld emits a done=0
heartbeat right as it enters its main loop (marking that model loading is
finished), emits one heartbeat with cumulative token counts each time it
finishes a task (the token count comes ready-made from each request's
usage), advances done the same way for tasks skipped by resume, and emits
status=done on a normal finish. Once running, a collection job has
progress, token rate, and ETA in the window. Steps follow Task 3 of the
implementation plan.

**Blocked by:** 01 Heartbeat module and verdict engine

**Status:** resolved

- [ ] Syntax check passes, `--help` prints normally under the appworld
  venv (proving the heartbeat module can be imported in that venv)
- [ ] Both the per-task finish path and the SKIP branch advance done, and
  status=done is emitted when the loop ends
- [ ] commit

## Comments

- 2026-08-08 ticket-run: DONE. Branch ticket/20260808-par/T03 (base
  5be5d08, head 9838281, changed envs/collect/run_appworld.py +17 lines),
  merge commit 251919f. 0 fix rounds, no minors. Two cannotVerify items
  already handled by the main conversation: --help under the appworld venv
  was re-run by the main conversation itself on the post-merge main and
  passed (exit 0); "progress/rate/ETA shown in the window" is an
  end-to-end effect spanning T02/06/07, left to be checked once the
  sampler and outlets are in place. One implementer concern: tok_in/tok_out
  are cumulative values, consistent with the protocol, recorded for
  confirmation. Report: sdd/2026-08-08-wave1/T03-report.md.
