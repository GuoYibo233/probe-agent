# 04 — Four training scripts wire up heartbeats

**What to build:** All four training-cell scripts (mbert tool, mbert
extraction, causal tool, causal call-generation) wire up heartbeats: emit
done=0 after the start log, emit one heartbeat with a rolling loss after
each 50-step step log, and emit status=done after the done log. Once
running, a training job has step progress and a loss trend in the window.
All four files follow the same pattern; the anchor points are whatever
grep finds live. Steps follow Task 4 of the implementation plan.

**Blocked by:** 01 Heartbeat module and verdict engine

**Status:** resolved

- [ ] Syntax check passes on all four files
- [ ] Both training venvs, mbert-env and cprobe-env, can import the
  heartbeat module
- [ ] loss is taken from the rolling average already present in each
  file's step log, inserted before it's reset
- [ ] commit

## Comments

- 2026-08-08 ticket-run: DONE. Branch ticket/20260808-par/T04 (base
  5be5d08, head f4b9f67, +9 lines each across four training scripts),
  merge commit on main. 0 fix rounds, no minors. Two cannotVerify items
  already handled by the main conversation: importing the heartbeat
  module under mbert-env / cprobe-env was re-run by the main conversation
  itself on the post-merge main, both passed, and py_compile passed on
  all four files; "step progress and loss trend in the window" is an
  end-to-end effect spanning T02/06/07, left to be checked later. Two
  concerns (no venv in the worktree so verified with the main repo's
  interpreter instead; three files' anchor points found live via grep
  don't match the plan document's line numbers) read, both process notes
  rather than gaps. Report: sdd/2026-08-08-wave1/T04-report.md.
