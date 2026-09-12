# Long-running job monitoring and launch — spec

Status: ready-for-agent

This spec is distilled from two 2026-08-08 documents: the design decisions are
in `docs/design/2026-08-08-gpu-monitor-launch.md`, and the task breakdown is
in `docs/plans/2026-08-08-gpu-monitor-launch.md`. Throughout, the words job,
ledger, piece, window, verdict, launch, heartbeat, sampler, sampling history,
escalation line, autopsy, refire, incident record, incident agent, and unit
are all used per the definitions in the repo-root `CONTEXT.md` glossary; no
new names are invented here.

## Problem Statement

I run long jobs on four GPU machines: collection, training, evaluation, and
vLLM serving. Right now, finding out where a job stands means dispatching a
read-only agent to read logs machine by machine and do its own two-point rate
measurement; launching a job means typing three registration commands by hand,
and missing one breaks the ledger; the scheduled-checkin regime wakes an agent
every half hour, and most of the time what it sees on waking is "everything's
healthy," while context and tokens have already been spent; when a job dies in
the middle of the night nobody is watching, it's only discovered the next
morning, and a whole night of GPU time has been wasted for nothing.

## Solution

One sentence: scripts emit heartbeats, the sampler computes verdicts, three
outlets read the same sampling history, an incident automatically pulls in an
incident agent to refire, and launching is collapsed into a single subcommand.

Broken apart, that's five pieces, each solving one of the pains above:

1. Every script we write emits one heartbeat line to its own log each time it
   finishes one unit of progress; the monitoring side never has to guess the
   log format again.
2. A sampler stays resident on the login machine; each round it reads
   heartbeats, probes liveness, and computes a verdict, landing it in the
   sampling history; the verdict is computed by the program, and the agent
   only reads the conclusion.
3. Three outlets, the terminal table, json, and the web page, read the same
   sampling history: the terminal table is for a quick look in the terminal,
   json is for the agent to read a ready-made conclusion, and the web page,
   via ssh port forwarding, is for me to watch remotely.
4. When a verdict turns into dead on the spot, or stalled for longer than the
   escalation line, the sampler automatically pulls in an incident agent to
   run an autopsy; a dead piece is automatically refired once, and the
   incident record is written to disk by the program.
5. Launching collapses into one subcommand, `run.py launch`: probing cards,
   starting tmux, the three registrations, and verifying liveness all happen
   in one go; the two queue-based launchers are not merged into it, but they
   call into the same registration internally, so "the program guarantees
   registration" holds across every launch path.

## User Stories

1. As the experimenter, I want to see the verdict, progress, rate, and ETA
   for every long-running job in one terminal command, so I don't have to
   dispatch an agent to read logs and reason it out.
2. As the experimenter, I want to see the same job table in my local browser
   (via ssh port forwarding), so I can watch jobs remotely without being at
   the terminal.
3. As the experimenter, I want the window to show the last sample time and
   turn red when it's stale, so I notice for myself when the monitoring
   system has stopped.
4. As the experimenter, I want a piece that dies in the middle of the night
   to be automatically autopsied and refired once, so I don't have to wait
   until morning to find out a whole night of GPU time was wasted.
5. As the experimenter, I want a piece that suspected stall to only be autopsied,
   never killed, so a long heartbeat gap caused by checkpoint saving or a
   long eval segment doesn't get an active job killed by mistake.
6. As the experimenter, I want automatic refire for the same piece slot to be
   allowed only once in a job's whole lifetime, so a job that keeps dying
   isn't relaunched forever.
7. As the experimenter, I want incident records written to disk by the
   program and shown in their own block on the web page, so I can check in
   the morning what happened overnight.
8. As the experimenter, I want launching a long-running job to take one
   command, so the ledger, the experiment record, and RUNMETA don't rely on
   me remembering three registrations.
9. As the experimenter, I want the program to probe every target card before
   launch and reject the whole launch if even one card isn't FREE, so I
   never launch onto a card someone else is using.
10. As the experimenter, I want a job marked shardable (the registry flag
    meaning "this job can be split into pieces") to automatically get shard
    indices injected when given multiple pieces, so shard numbering never
    passes through human hands and two cards don't each run a full copy that
    overwrites the other's output.
11. As the experimenter, I want a job not marked shardable to be flatly
    rejected when given multiple pieces, so a mistaken multi-piece launch is
    caught at launch time.
12. As the experimenter, I want the run_id to be generated by the program
    from one single value across the tmux session name, the ledger name, the
    experiment record, and the log name, so the four stay consistent without
    a human cross-checking them.
13. As the experimenter, I want a one-off command outside the registry to
    also go through the same launch command, so a one-off launch gets the
    full set of registrations too.
14. As the experimenter, I want liveness verified within 30 seconds of launch
    (session exists, the log has output, no traceback), so a launch failure
    is reported on the spot instead of leaving a false entry in the ledger.
15. As the experimenter, I want a script to emit one done=0 heartbeat right
    as it enters its main loop, so model-loading time always falls outside
    the heartbeat timeline and never pollutes the rate.
16. As the experimenter, I want a collection script's heartbeat to carry
    cumulative token counts, so the window can show token throughput.
17. As the experimenter, I want a training script's heartbeat to carry a
    rolling loss, so the window can show the training trend.
18. As the experimenter, I want warm-up to have a cap, past which it turns
    into suspected stall, so a job stuck in the loading stage doesn't stay silent
    forever.
19. As the experimenter, I want the verdict lines to adapt to each job's own
    typical heartbeat interval, so a job with sparse heartbeats isn't
    falsely flagged and a job with dense heartbeats gets reported quickly
    when something goes wrong.
20. As the experimenter, I want to be able to manually override the verdict
    line, the escalation line, and the warm-up cap at launch time, so a
    special job can be tuned as needed.
21. As the experimenter, I want a vLLM service to be judged alive or dead by
    port response, with the throughput line used only for rate display, so
    an idle service isn't mistaken for a stall.
22. As the experimenter, I want a round where the probe fails to carry over
    the previous round's conclusion and be flagged, and consecutive failures
    to only turn the display red without triggering an incident, so the
    program doesn't take action when it can't tell alive from dead.
23. As the experimenter, I want card picking and deregistration to always
    probe live and never trust the cache, so occupancy decisions are never
    misled by stale sampling history.
24. As the experimenter, I want a session missing from the ledger to show up
    on the table as a reminder, so a stray hand-launched session doesn't
    slip through unnoticed.
25. As the experimenter, I want the sampler to be stateless and recover from
    the sampling history after a restart, so a watchdog can pull it back up
    at any time and have it pick right back up.
26. As the experimenter, I want a watchdog on the login machine to check the
    sampler periodically and pull it back up when it's gone, so the monitor
    itself is also monitored.
27. As the experimenter, I want every constant used in a verdict to be
    collected in one configurable place, so a false alarm can be tuned in
    one spot instead of hunting the whole repo for hardcoded values.
28. As the main-conversation Claude, I want a json outlet that gives me a
    ready-made verdict, rate, and ETA, so I no longer do my own two-point
    rate measurement, saving context and tokens.
29. As the job-monitor reviewer, I want the verdict already computed by the
    sampler so I only read the conclusion and autopsy on demand, so my job
    narrows to read-only checking and doesn't compete with the incident
    agent.
30. As the incident agent, I want the prompt to carry the job's verdict,
    piece, log path, and original launch command, so an autopsy doesn't
    require finding the scene myself.
31. As the incident agent, I want refire to go through the same launch
    command, and to get a clear error when the original card is occupied,
    so there's a clear procedure for switching cards and retrying.
32. As whoever picks this up next, I want the skill, the agent definitions,
    and the root docs to be rewritten along with this overhaul, so what they
    get is a new map, not a narrative of the old flow.

## Implementation Decisions

- Four new modules: the heartbeat module (two entry points, emit and parse,
  standard library only, importable from every venv); the verdict engine
  (pure functions, zero IO, all verdict conventions collected in this layer);
  the sampler (a resident process, sampling thread and web thread kept
  separate, so a stuck sampling round doesn't affect serving the page); and
  the launch piece (a common registration function plus the `run.py launch`
  subcommand).
- Heartbeat protocol: one line equals a fixed prefix `@hb ` plus a JSON
  object. Required fields are done, total, unit, and ts; optional fields are
  tok_in, tok_out (both cumulative), loss, and status (a value of done marks
  a normal finish). One done=0 heartbeat is emitted right as it enters the
  main loop, marking "model loading is finished."
- Six verdict cells, checked in a fixed priority order, first hit wins. This
  table is the design's finalized text:

| Order | Verdict | Condition |
|---|---|---|
| 1 | done | done == total, or a heartbeat with status=done was received |
| 2 | dead | session is gone, and done is not satisfied |
| 3 | suspected stall | session is alive, stall duration > verdict line |
| 4 | warming up | session is alive, not a single heartbeat yet |
| 5 | slowed | recent rate has a value and is < 0.5 × the overall average rate |
| 6 | healthy | none of the above |

- Clock discipline: clocks are never compared across machines. Stall duration
  is computed with the sampler's own clock; the ts inside a heartbeat is only
  differenced between heartbeats on the same machine.
- Verdict line = 5 × typical heartbeat interval (the median of at most the
  most recent 20 intervals), with a floor of 3 sampling intervals; when not
  enough interval samples have accumulated yet, the verdict line temporarily
  uses the warm-up cap as a stand-in. Escalation line = verdict line × 3. The
  warm-up cap defaults to 30 minutes. All three lines can be manually
  overridden at launch time.
- Service-type pieces (vLLM) use only four verdict cells: warming up,
  healthy, suspected stall, dead; alive/dead is judged by port response, not by
  the throughput line; the throughput line is only used to display token
  rate.
- Sampling history is written under a monitor subdirectory of the NFS mirror
  directory, not tracked in git; the latest round's result and the
  accumulated state are each an atomically-written file, and per-round
  history is appended per job. The accumulated state stores each piece
  slot's first heartbeat, latest progress, incident number, and refire
  count, which is what the sampler recovers from after a restart.
- Incident-trigger rules are collected in pure functions: escalation only
  fires once the escalation line is reached, and the same incident only
  pulls in an agent once (guarded by the incident number); refire is
  allowed only when the verdict is dead and this piece slot has not been
  refired before. The incident agent is a headless claude with the model
  pinned to opus, and it writes no human-facing report.
- The account after a refire: the job name and piece index don't change,
  but this piece slot's four-tuple in the ledger is updated to the new
  values. The heartbeat timeline restarts, and the verdict line and rate
  accumulate again from done=0 after the refire.
- The launch flow is fixed in this order: dirty-tree gate, probe cards
  (reject the whole launch if even one card isn't FREE), start tmux, verify
  liveness for 30 seconds, the three registrations, print the monitoring
  entry point. A liveness-verification failure means no registration and
  no rollback; killing the process is a human decision.
- The two queue-based launchers are not merged into launch; each keeps its
  own guards, and internally switches to calling the same registration
  functions and the same FREE probe. In the queue scenario, a non-FREE slot
  is skipped rather than rejecting the whole table, because a queue table
  being half-empty is common, and rejecting the whole table would strand the
  good slots.
- The terminal outlet reading the sampling history has a freshness
  threshold: it's only used when the last sample time is within 5 minutes;
  otherwise it prints a warning and falls back to the on-the-spot probing
  path. The free command for card picking and the launch-time card probe
  always probe live.
- All the verdict engine's constants are collected in one config dict inside
  the verdict engine; hardcoding elsewhere is not allowed.

## Testing Decisions

- A good test only tests external behavior: the verdict engine takes state
  in and gives a verdict out; the sampler takes a fake ledger and fake logs
  in and gives files written to disk out; launch takes parameters in and
  gives a command list out. Internal function organization is not tested.
- Four test seams (confirmed with the experimenter on 2026-08-08): the
  verdict engine's pure functions are unit-tested to cover every verdict
  convention and edge case; the sampler is integration-smoke-tested in a
  single-round sampling mode, fed a fake ledger and fake logs in a temp
  directory, with the ssh probe function replaced by the test; the launch
  piece's pure logic, such as shard injection, is broken into functions and
  unit-tested, with card-probing and registration checked via a replaced
  subprocess, and the whole command smoke-tested via dry-run; the
  incident-trigger rules are collected in pure functions and unit-tested.
- The test framework is the standard library's unittest, and the test
  directory is first created by this pipeline. The repo had no unit tests
  before this; the existing verification habit is `run.py selfcheck`,
  which continues to serve as the gate at the end of each task.
- Testing precedent: there was no existing test precedent in the repo to
  follow; pointing the on-disk output directory at a temp directory via an
  environment variable is established as this repo's first precedent by the
  sampler's tests.

## Out of Scope

- CPU jobs do not enter the window.
- Phone push notifications are not built; each incident record already
  carries the fields needed to locate it, so adding push later is additive.
- Automatically killing a live job is not done.
- The standing scheduled-checkin regime is retired, not improved; the
  sampler replaces it.
- Sampling history is not tracked in git.

## Further Notes

- The first-version values for the constants, and the list of "small things
  left to decide during implementation" (the incident-record field table,
  the eval-script roster, per-piece output filenames, the web page layout),
  are in §10 of the design document.
- The vLLM throughput line's format has been verified against real logs: by
  default one line every 10 seconds, downgraded to a debug line that isn't
  printed when the engine is idle, so a gap in the throughput line does not
  count as a stall.
- Reason for marking Status ready-for-agent: the implementation plan has
  already broken the work into 19 tasks with steps and verification
  commands, and an agent can execute them one by one per the plan.
