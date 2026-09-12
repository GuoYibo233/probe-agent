# 07 — Terminal outlet switches to reading the sampling history

**What to build:** gpu-jobs's three outlets, the status table, watch, and
json, switch to reading the sampling history first: when the last sample
time is within 5 minutes, the table is produced instantly from the
sampling history (the header carries the last sample time); when it's
stale, a warning line is printed and it falls back to the existing
on-the-spot probing path. The json outlet attaches a sampler_stale flag
when stale. free, register, and finish stay untouched; card picking and
deregistration always probe on the spot. Steps follow Task 8 of the
implementation plan.

**Blocked by:** 02 Sampler runs one round end to end

**Status:** resolved

- [ ] When no sampler is running: the old table still comes out with a
  warning line added, and the json outlet emits valid JSON
- [ ] Pointing at a fake latest-sampling file: the new table is produced,
  with all columns, verdict, progress, rate, ETA, rendered
- [ ] The done and dead verdicts still have their finish and
  check-the-log hint lines
- [ ] commit

## Comments

- 2026-08-09 ticket-run: DONE. Branch ticket/20260808-par/T07 (base
  2ce9834, head f5a864a, gpu_jobs.py +177, tests/test_gpu_jobs.py added
  with 16 new cases), merge commit 0d2c1ac. 1 fix round, no minors, no
  cannotVerify. Main-conversation real smoke test: with a live sampler
  running, `gpu-jobs status` produced the table instantly with the last
  sample time in the header, and `gpu-jobs json` emitted the sampling
  result verbatim (rows/extras/incidents_tail); 16 tests all green. Two
  concerns noted as-is: the RATE unit-switch threshold (>=1 uses /s,
  otherwise /h) is a boundary the implementer set on their own,
  inconsistent with the web outlet's fixed /s, left for the wrap-up to
  check whether to unify; the done/dead hint lines keep the old key
  phrases but are not copied verbatim. The first workflow died silently
  yesterday; resumed and re-run to completion. Report:
  sdd/2026-08-08-wave1/T07-report.md.
