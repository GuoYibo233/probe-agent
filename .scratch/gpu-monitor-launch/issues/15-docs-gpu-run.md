# 15 — Doc write-back: the gpu-run skill and two methodology docs

**What to build:** The gpu-run skill is realigned with the new flow:
Phase 4's launch section collapses into a single launch (the command
steps for hand-typed double registration, RUNMETA, and record are all
deleted), and the monitoring commands handed to the user become
gpu-jobs, watch, and the web page; Phase 5's standing checkin regime
becomes a sampler clause (verdicts, escalation, and the incident agent
are the sampler's responsibility; Claude only dispatches job-monitor to
read the json when the user asks or when an incident record has
content); Phase 6a's five-step deregistration is kept. In the launch
methodology, the tmux-template section becomes "what launch does for
you," with the card-picking rules kept; in the monitoring methodology,
the three sections including two-point rate measurement become a
statement of the program's responsibility, and the decision tree's
inputs become verdict values. Steps follow Task 16 of the implementation
plan.

**Blocked by:** 09 launch subcommand, 12 Incident trigger, 14 Sampler
goes live

**Status:** resolved

- [ ] Phase 4 has only three steps left: commit, launch, hand over the
  monitoring entry point
- [ ] Phase 5 no longer has a scheduled-checkin clause
- [ ] commit

## Comments

- 2026-08-08 transcribed by the main conversation (current-state
  phrasing that must be read before writing docs): the incident agent's
  automatic spawning in ticket 12 was deferred by user ruling on
  2026-08-08, the trigger-rule pure function has been merged but
  maybe_trigger_incidents is a placeholder. In Phase 5's sampler clause,
  write "verdicts and escalation are the sampler's responsibility" as
  is, but "the incident agent automatically autopsies and refires" must
  be written as "not live yet (deferred)," never as current state.
- 2026-08-08 phrasing update (overrides the previous entry): the user
  subsequently authorized it, and the incident agent's automatic
  spawning has been wired in by the main conversation (including the
  refire-permission rule), but the manual rehearsal was cancelled; the
  docs should say "wired in, not yet rehearsed for real," not "not live
  yet." If you already wrote it under the old phrasing, the main
  conversation will check and correct it at wrap-up.
- 2026-08-08 ticket-run: DONE. Branch ticket/20260808-par/T15 (base
  86f2b8e, head b0cd20d, gpu-run SKILL.md + the launch/monitor
  methodology docs, +159/-130 total), merged. 1 fix round. Both
  acceptance items met: Phase 4 collapsed into the three steps commit →
  launch → hand over the monitoring entry point; Phase 5 has no
  scheduled-checkin clause, and the incident-agent phrasing matches the
  implementation state (wired in, not yet rehearsed for real). One
  leftover minor: the implementer's report's self-check item 4 doesn't
  match the diff (it said "the --kind three-word enum is kept as-is,"
  but that section was actually deleted and replaced with a generic
  placeholder); the doc itself is fine, the report's description is
  wrong, noted as-is. Five concerns noted as-is, of which two, "the
  --kind three-word enum vs. launch writing kind=launch, two different
  value sets" and "launch-methodology Step6's old ETA phrasing not quite
  matching the new monitor-methodology," are passed to ticket 18's final
  self-check for review. Three cannotVerify items: T07's transition
  wording, to be checked against T07's wrap-up; T12's wiring
  completeness, to be checked once T12's commit lands (currently going
  through the user's ! submission); web-page rendering consistency, T14
  already tested the web page working, to be swept again at final
  wrap-up on the wording level. Report: sdd/2026-08-08-wave1/T15-report.md.
