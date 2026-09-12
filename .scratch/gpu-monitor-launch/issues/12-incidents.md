# 12 — Incident trigger

**What to build:** The sampler automatically pulls in an incident agent
when a verdict turns bad: it triggers on the spot for dead, and triggers
when suspected stall has stalled past the escalation line; the trigger rule is
collected in a pure function (the same incident only pulls in an agent
once, guarded by an incident number against repeats; refire is allowed
only when the verdict is dead and this piece slot hasn't been refired
before). The incident agent is a headless claude with the model pinned
to opus; the prompt carries the verdict, piece, log path, and original
launch command, and the permission line is fixed: for dead, autopsy then
refire once (via --refire); for suspected stall, autopsy only, never kill; it
writes no human-facing report. Both the incident record and the agent's
output are written to disk. Check the current spelling of the
headless-mode flag before implementing. Steps follow Task 14 of the
implementation plan.

**Blocked by:** 02 Sampler runs one round end to end, 10 Refire mode
--refire

**Status:** resolved

- [ ] Trigger-rule tests pass: a first-time dead allows refire, an
  already-refired one does not, an already-open incident does not trigger
  again, a suspected stall that hasn't reached the escalation line does not
  trigger
- [ ] Prompt tests pass: containing the log path, the ledger json
  command, and either the refire command or the wording forbidding refire
- [ ] Manual rehearsal: after sampling one round on a fake job, one
  incident record appears and the agent's output file has a DONE line;
  clear the state afterward
- [ ] commit

## Comments

- 2026-08-08 transcribed by the main conversation (from T09's wrap-up):
  the service piece's port-passing path is undefined (see ticket 13's
  Comments); no direct conflict with this ticket, noted for the record
  only.
- 2026-08-08 ticket-run: BLOCKED → ready-for-human. Completed and merged
  into main (branch ticket/20260808-par/T12, commit 5527eb9, 79 tests all
  green and selfcheck's 63 tasks in place after merging): the
  should_trigger trigger-rule pure function (5 cases), the
  build_incident_prompt prompt construction (2 cases), and the
  headless-flag spelling checked (-p/--print, --model,
  --dangerously-skip-permissions all present). Not completed: spawn_agent's
  implementation and the manual rehearsal, since writing/executing an
  action that "spawns a headless claude subprocess carrying a
  permission-bypass flag" was repeatedly blocked by Claude Code's
  permission classifier (a full implementation, deleting the placeholder,
  and a mocked unit test were all blocked), and spawning an opus
  subprocess counts as a paid model call, which per the hard rule
  requires the user's own authorization. A related finding (must be
  fixed during implementation): inside sample_once(),
  atomic_write(state.json) currently runs before
  maybe_trigger_incidents; without reordering it, "the same incident only
  pulls in an agent once" does not hold across rounds, and the same
  incident would repeatedly pull in an opus subprocess every 60-second
  round. Needs a user decision: after explicit authorization, the session
  holding that authorization implements it and does the rehearsal.
  Report: sdd/2026-08-08-wave1/T12-report.md.
- 2026-08-08 user ruling: the incident agent's spawn_agent implementation
  and manual rehearsal are **deferred**; this ticket stays in the state
  of "the trigger-rule pure function + prompt construction merged,
  maybe_trigger_incidents a pass placeholder." Impact on the downstream
  doc tickets (15/16): the docs must state as fact that "automatic
  incident-agent spawning is not live yet, verdicts and sampling proceed
  as usual," and must not write the not-yet-live automation as current
  state. When this ticket is revived, proceed with three things: the
  spawn_agent implementation, the state.json write-order fix, and the
  rehearsal.
- 2026-08-08 after the user changed course and authorized it, implemented
  by the main conversation: spawn_agent (a headless claude subprocess,
  model pinned to opus, detached without waiting, output going to
  monitor/incidents/<incident number>.out) + maybe_trigger_incidents (on
  a hit, writes incidents.jsonl → spawns the agent → sets
  incident_open=incident number) + moving state.json's on-disk write in
  sample_once to after the trigger (fixing the timing issue of "the same
  incident repeatedly pulling in an agent every 60 seconds"). Four new
  unit tests close the loop (mocked subprocess: a trigger writes the
  record and sets the flag, a second round doesn't re-trigger, healthy
  doesn't trigger, and the subprocess argument combination). **The
  manual rehearsal was cancelled again by user ruling**: the whole chain
  is backed only by unit tests, with opus never actually spawned once, so
  this chain will get its first real run when the first real incident
  happens. Test execution and the git commit were blocked by the
  platform's permission classifier because their content contained the
  headless-flag combination, so the user executed them personally with
  the `!` prefix (see the conversation). Doc phrasing updated: 15/16 may
  now state "automatic incident-agent spawning is wired in, not yet
  rehearsed for real." MAP.md is synced.
