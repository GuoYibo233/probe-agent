---
name: handoff
description: >-
  Write a handoff document for the current work line, so any incoming session can take
  over seamlessly within five minutes. Full flow: probe the real state
  (ledger/logs/git/jobs/runs.jsonl) → converge half-finished work → rewrite the handoff in
  memory as a whole file following the six-section template → sync the index → hand over
  authority (either wind-down mode or stop immediately for the old session, pick exactly
  one). Invoke whenever a session is winding down with work still in flight. Chinese
  triggers: "写交接书" / "交接一下" / "换个 session" / "收尾交接".
version: 1.1.0
---

# handoff — work-line handoff document

The reader of the handoff document is a new session that knows nothing. There is exactly one acceptance
criterion: the new session, reading only this file plus the paths it points to, can take over every running
task within 5 minutes, without stepping on a known trap, and without starting work that hasn't been approved.

## Hard rules

- **Current state must be probed live, never copied from memory or from the old handoff.** For every running
  task, tail its log individually to get the current progress; every status written into the handoff carries an
  absolute time (JST). ETAs are absolute times, never "2 more hours."
- **One work line keeps exactly one handoff document**, filename `handoff-<line-name>.md`, placed in this
  project's memory directory (the one given in the system prompt). A new handoff means rewriting the whole
  file, not appending or patching — history lives in git/TIMELINE, the handoff document only describes the
  present. When a work line concludes, delete the file and remove its index line from MEMORY.md.
- **Unapproved items get their own section**, each one noting "asked, no answer yet" or "not asked yet" — the
  incoming session is forbidden from starting work on these on its own.
- **Handover of authority**: a work line has exactly one lead session at any given moment. After the outgoing
  session writes the handoff, it picks exactly one of two modes — **wind-down mode** (only watch running tasks
  through to completion + carry out already-approved wind-down duties, i.e. gpu-run Phase 6a's five-step) or
  **stop immediately** (touch nothing) — and writes which one was picked in plain black and white in the
  handoff, no hedging. Neither posture takes on new work; any new idea goes into the handoff's queue. Before
  the incoming session starts, it confirms no other session is still working this line (two sessions both
  assuming lead = duplicate launches + killing each other's tmux sessions).
- **Converge half-finished work first**: before handing off, wrap up and commit whatever can be wrapped up from
  work in progress; roll back to a clean state whatever can't be wrapped up, and record a four-line account
  under "unsettled business" — what the goal was / how far it got / what's left / the exact next command. Never
  leave a dirty working tree with no accounting for the incoming session.

## Phase 1 — Probe (four lines of evidence)

1. `external/probe-env/bin/python run.py ls`: the active ledger, with each piece's progress, verdict, rate and ETA
   computed fresh on the call from its own heartbeat files. Tailing each piece's log still gets
   you the rawest text, for a piece that never got wired to heartbeats.
2. `git log --oneline -5` + `git status --short`: where HEAD is, what's uncommitted.
3. `tail jobs/runs.jsonl`: which run_ids have a start but no finish (`registry.open_runs()`).
4. Read the current section of `notes/WORKPLAN.md` + the latest entry of `notes/TIMELINE.md`, confirm the direction hasn't
   changed; if it has, add a TIMELINE entry first.

## Phase 2 — Write the handoff (six-section template)

```markdown
# <line name> handoff (<YYYY-MM-DD HH:MM JST>, handed off from session <short id>)
> Outgoing session's exit posture: wind-down mode watching through to completion / stop immediately (pick exactly one, with the time)
## Running tasks        ledger name / host / tmux / current progress@time (source: `run.py ls`) / completion criterion / ETA absolute time / wind-down duties
## Next-step queue (already approved)  in order; each item with a directly copy-pasteable command + success criterion
## Unapproved items     starting work on these on your own is forbidden; note whether it was asked and unanswered, or never asked
## Asset map             real paths for data / scripts / environments / weights; note for each whether it's committed
## Known traps           so the incoming session doesn't step in them again
## Unsettled business    uncommitted files / run_ids without a finish / ledger entries not deregistered / services not killed
```

Frontmatter follows the memory convention (`type: project`), with the description stating
"the incoming session reads this first."

## Phase 3 — Land it

1. Write the whole file, overwriting `<memory directory>/handoff-<line-name>.md`.
2. Sync the `MEMORY.md` index line (add it if missing, update the wording if present).
3. Restate three things to the user: where the handoff document is, a one-line list of running tasks, and
   which actions this session will still take under wind-down mode (no new work taken on after this).
