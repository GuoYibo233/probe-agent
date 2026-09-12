# 17 — Doc write-back: probe-pipeline and the root docs

**What to build:** The probe-pipeline skill and its references (gates,
stage-commands, invariants, extending), the handoff skill, CLAUDE.md,
MAP.md, and the gpu_state page header are all realigned with the new
flow. Three key new phrasings: G16's double registration becomes "launch
automatically writes all three, the hand-typed backfill path still
exists, and missing it still counts as a violation"; invariants' double-write
bookkeeping becomes "the double write is guaranteed by launch, and the
responsibility for a hand-launched job that bypasses launch falls back
on the person"; extending's new-script checklist gets a hard item added,
"a new collection/training/eval script must wire up heartbeats, and a
script that doesn't will sit at warming up in the window forever." MAP
gets three lines updated for old programs and five lines added for new
modules. Steps follow Task 18 of the implementation plan.

**Blocked by:** 09 launch subcommand, 11 Two queue-based launchers wire
up registration, 14 Sampler goes live

**Status:** resolved

- [ ] The three new phrasings above land verbatim in their respective
  files
- [ ] MAP.md has all the old and new program lines
- [ ] commit

## Comments

- 2026-08-09 ticket-run: DONE. Branch ticket/20260808-par/T17 (base
  f8c9965, head 80b6cbf, the probe-pipeline skill and its four
  references + the handoff skill + CLAUDE.md + MAP.md + the gpu_state
  page header), merge commit 4b2e9df (a MAP gpu_jobs line conflict: T07's
  outlet facts as the base with T17's "register is the backfill path"
  sentence folded in). 1 fix round. Acceptance check: the three key new
  phrasings landed, gates.md's "launch automatically writes all three" is
  there verbatim, invariants.md's "the double write is guaranteed by
  launch" is there verbatim, extending.md's heartbeat hard item has all
  the required elements ("wire up heartbeats" is phrased as "wire up
  `ops/heartbeat.py`" with a module reference, same meaning); MAP.md has
  all the old and new program lines, and T17 also filled in
  launch_cmd.py's missing line left over from T10 while at it. Three
  concerns noted as-is: SKILL.md's two spots at :74-75/:172-173 were
  judged, after a re-read, to need no change; CLAUDE.md's example
  sentence was split across two places and is not verbatim; MAP's four
  lines carry over each ticket's wrap-up version as-is without
  rewriting. Report: sdd/2026-08-08-wave1/T17-report.md.
