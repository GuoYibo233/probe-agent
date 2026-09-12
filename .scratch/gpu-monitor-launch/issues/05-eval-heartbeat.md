# 05 — Three eval scripts wire up heartbeats

**What to build:** The three eval scripts (tool eval, mbert-call eval,
causal-call eval) wire up heartbeats, with item (sample count) as the
progress unit: emit done=0 before the batch loop, emit a heartbeat
alongside each existing progress print (for scripts without a progress
print, add one every 50 batches to set the pace), and emit status=done
after the report is written. For a script with multiple loop segments, the
longest segment is the progress denominator; each script emits only one
progress axis. Steps follow Task 5 of the implementation plan.

**Blocked by:** 01 Heartbeat module and verdict engine

**Status:** resolved

- [ ] Syntax check passes on all three files
- [ ] Each script has only one progress axis, and status=done is emitted
  at the normal end point
- [ ] commit

## Comments

- 2026-08-08 ticket-run: DONE. Branch ticket/20260808-par/T05 (base
  5be5d08, head b8cda45, +20 lines total across three eval scripts), 29
  tests all green and py_compile passing on all three files after merging
  into main. 0 fix rounds, no minors. One cannotVerify item (whether the
  "longest segment" axis choice holds for eval_mbert_call/eval_causal_call
  depends on runtime data) ruled on by the main conversation: the progress
  axis must be statically determinable; the implementer's chosen
  main-convention path is the must-run segment, and --self-fire is an
  optional branch off by default, so it's accepted as "must-run segment is
  the axis," unchanged. Three concerns noted as-is: --self-fire's
  score_fire() does not wire up heartbeats; eval_tool's done restarts from
  0 across a split (verdicts.rates() is guarded against done going
  backward, recording the rate as None without erroring); status=done's
  done/total counts only the main convention and does not include
  self-fire's data volume. Report: sdd/2026-08-08-wave1/T05-report.md.
