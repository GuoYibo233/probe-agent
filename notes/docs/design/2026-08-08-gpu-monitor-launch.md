# Long-running task monitoring and launch — final design (2026-08-08)

One sentence: scripts emit heartbeats, the sampler computes verdicts, three exits read the same
sampling history, an incident automatically pulls up an incident agent to refire, and launching
collapses into one run.py subcommand.

The glossary is in `CONTEXT.md` (long-running task / ledger / piece / window / verdict / launch /
heartbeat / sampler / sampling history / escalation line / autopsy / refire / incident record /
incident agent / progress unit); this document follows it and does not redefine these terms. This
document records design decisions; the implementation order is a separate plan, to be agreed on
again before work starts.

The problem to solve (state of things as of 2026-08-08): checking task status requires an agent to
read files everywhere and reason about them — the verdict relies on the job-monitor agent
measuring speed at two points, launch registration relies on a person typing three commands,
periodic check-ins cost both context and tokens, and most of the time an agent wakes up every half
hour just to see "everything is healthy."

## 1 Scope

Only GPU tasks are in scope (the ones that go into the ledger). CPU long-running processes and
recipe steps are out.

Three deliverables:
1. Programs: the heartbeat module + the sampler + the `run.py launch` subcommand + the
   registration rework of the two queueing launchers.
2. Script changes: wiring our own collection / training / evaluation scripts to emit heartbeats.
3. Documentation write-back: the skill / agent / root documents listed in §8.

## 2 Heartbeat (script side)

- New file `ops/heartbeat.py`, standard library only — any venv can import it, no new dependency.
- Every time a script finishes one progress unit it writes one line to stdout: a fixed prefix
  `@hb ` plus a JSON object. Heartbeat lines are mixed in with ordinary log lines inside the tmux
  tee log; the monitoring side tails the log's end and only recognizes lines with the prefix.
- Fields: required `done` / `total` / `unit` ("task" or "step", reported by the script itself) /
  `ts` (the clock of the machine the script is running on, at the moment this line is written);
  optional `tok_in` / `tok_out` (**cumulative** values: the sum of prompt / completion tokens over
  all requests up to this moment), `loss`, `status` ("done" means a normal finish).
- Before entering the main loop, emit one done=0 line first — this is the marker for "model
  loading finished," so loading time always falls outside the heartbeat timeline from here on.
- List of scripts to change:
  - `envs/collect/run_appworld.py` (unit=task; token data is already available —
    `envs/collect/common.py` gets usage on every request, accumulate it and put it into the
    heartbeat)
  - Training scripts such as `pipeline/train/train_mbert_tool.py` (unit=step, reports loss)
  - Evaluation scripts (go through the list one by one during implementation)
- The vLLM service is third-party; it does not emit heartbeats, and there is no such thing as
  done/total for it. It goes through a separate verdict track for service-type pieces (see the end
  of §4); the throughput lines in its log are only used to show token rates and do not participate
  in the verdict. The throughput line has been verified against a real log
  (`/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/logs/new1_diag_srv_a.log`,
  vllm 0.26.0, original text: `Avg prompt throughput: 785.1 tokens/s, Avg generation
  throughput: 671.8 tokens/s, Running: 4 reqs, ...`, one line every 10 seconds by default,
  downgraded to debug and not printed when the engine is idle — which is exactly why "no
  throughput line while idle does not count as a stall").

## 3 Sampler (monitoring side)

- New file `ops/sampler.py`, resident in a tmux session on the login machine (session name
  `new1_sampler`), one round every 60 seconds.
- Each round does four things: read the task list from the ledger's active list → tail each
  piece's log to pick up heartbeats (the log is on NFS, read locally, no ssh needed) → ssh into the
  four machines and run `tmux ls` to probe liveness (keeping the existing fail-closed semantics: a
  failed probe ≠ no session) → compute the verdict, append it to the sampling history.
- The sampling history is one file per task; each round's line carries a piece slot (shard-id), and
  pieces with multiple shards are each computed on their own. Besides the round-by-round record,
  each piece slot stores one cumulative state: the ts of the first heartbeat, the latest done, the
  incident number, the refire count. The origin point for the average rate is taken from here, so
  it does not depend on whether the start of the log is still within the tail range; the sampler
  also recovers from here after a restart.
- The scan for sessions outside the ledger is kept (the current behavior of
  `collect(with_extras=True)`): it always scans tokyo105-108, and unregistered sessions show up on
  the table as a reminder — only host and session name are listed, no verdict is computed, no
  incident is triggered (without registration there is no log path or launch command; to manage
  it, register it first).
- The sampling thread and the web thread are separate: the HTTP port (configurable, default 8377)
  serves the web page, and the web thread only reads the latest sampling history; if ssh hangs on
  the sampling side, it does not affect serving the page — the timestamp on the page will just get
  stale. The ssh probe itself carries a timeout. With VS Code Remote-SSH's automatic port
  forwarding, you can view it directly in your local browser. Page contents: a task table (verdict
  / progress / rate / token metrics / ETA), the time of the last sample (turns red if it has not
  updated for more than 3 rounds), the incident record block, and sessions outside the ledger.
- The sampler's own liveness has two layers of backup: both the terminal table and the web page
  surface "the last sample time has gone stale" for a person to see; a crontab on the login machine
  checks the tmux session every 5 minutes and restarts the sampler if it is gone — the sampler is
  stateless, and after a restart it recovers from the sampling history and keeps computing.
- On disk: both the sampling history and the incident record are high-frequency increments, they do
  not go into git, they live in the NFS mirror directory
  `/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/monitor/`, and they are kept, not deleted,
  after finish (the footprint is small).

## 4 Verdict

All six values are computed by the sampler; the agent only reads the conclusion. Each piece gets
exactly one cell per round, judged in the order below, stopping at the first match:

| Order | Verdict | Condition |
|---|---|---|
| 1 | done | done == total, or a heartbeat with status=done was received |
| 2 | dead | the session is gone, and done is not satisfied (including dying before ever emitting a heartbeat) |
| 3 | suspected stall | the session is alive, and the stall duration > the stall line |
| 4 | warming up | the session is alive, and there is no heartbeat at all yet (still loading) |
| 5 | slowed | the recent rate has a value, and it is < the overall average rate × 0.5 |
| 6 | healthy | none of the above |

- **Clock discipline**: never compare clocks across machines. Stall duration = under the sampler's
  own clock, the time from "the sampling moment when a new heartbeat was last seen" to now; the
  heartbeat `ts` is only used to take differences between heartbeats on the same machine (the
  denominator of the average rate).
- **Warm-up has a ceiling**: counted from the launch moment, 30 minutes by default; once exceeded
  it turns into suspected stall — a task stuck in the loading stage no longer stays silent forever.
  Override with `--warmup-line`.
- **Stall line** = 5 × typical heartbeat interval, with a floor of 3 sampling rounds (at 60 seconds
  per round, that is 3 minutes). The floor comes from the sampling granularity: when the stall
  duration is under a few sampling rounds, the sampler cannot tell "it has stopped" from "it just
  hasn't been my turn to look yet," so it tracks the sampling interval rather than a number
  hardcoded on the task side. Typical heartbeat interval = the median of the most recent 20
  heartbeat intervals at most; when fewer than 3 intervals have accumulated, the stall line
  temporarily falls back to the warm-up ceiling (so a long task / long step does not false-positive
  at the start).
- **Escalation line** = stall line × 3, measured on the same stall duration: stalling past the stall
  line turns the verdict into suspected stall, stalling past the escalation line pulls up an incident
  agent.
- **Rate**: average rate = (latest done − 0) ÷ (the ts of the latest heartbeat − the ts of the
  done=0 line); recent rate = Δdone ÷ Δts over the most recent 10 heartbeats at most, and there is
  no value if fewer than 2 are available (shown as — in the table). The token rate works the same
  way, taking the difference of cumulative tok values. Loading time never touches any denominator.
  ETA = remaining units ÷ recent rate, falling back to the average rate when the recent rate has no
  value.
- **Probe failure**: for that round, liveness carries over the previous round's conclusion, and the
  table marks "probe failed"; 10 consecutive rounds of probe failure only turn the table red, they
  do not trigger an incident agent — when you cannot tell dead from alive you do not act;
  fail-closed is applied consistently.
- **Service-type pieces (vLLM)** only use four cells: warming up (session alive, the port has not
  answered yet, also subject to the warm-up ceiling), healthy (session alive, the port answers),
  suspected stall (session alive, the port has not answered for 3 consecutive rounds), dead (session is
  gone). Done and slowed do not apply to a resident service; not printing a throughput line
  while idle does not count as a stall.

## 5 After an incident

- Trigger: the verdict turning **dead** triggers on the spot; **suspected stall** triggers once the stall
  duration passes the escalation line.
- Action: the sampler starts an incident agent (headless `claude -p`, model pinned to opus), with a
  prompt carrying this task's json (verdict, piece, log path, original launch command). It is a
  different role from the read-only job-monitor in a session: job-monitor is the inspector you
  dispatch, read-only and hands-off; the incident agent is the one handling things in the middle of
  the night.
- The incident agent does exactly one thing, "get the experiment handled," within these permission
  lines:
  - Dead → autopsy (read the tail of the log to locate the cause of death), then refire once.
    Refiring also goes through launch: first probe with `gpu-jobs free` to pick a card live (the
    original card first, switching to a probed-free card if it is occupied), probe once more right
    before launch fires, and retry on a different card if it gets taken. Since the session is
    already gone, refiring cannot break anything that is still running.
  - Stalled → autopsy only, **killing is not allowed**. A long heartbeat pause has false positives
    (saving a checkpoint, a long evaluation segment); killing a live task by mistake costs more
    than refiring a few hours late.
  - No report written for a person to read. The incident record is written by the sampler; the
    agent's conversation record lands automatically in the claude session file, to be checked in a
    fresh session in the morning.
- How the books connect after a refire: the task name and shard-id stay the same, and the
  quadruple for that piece slot in the ledger (host / gpus / session / log) is updated to the new
  one; the incident number and the refire quota travel with the piece slot (task name + shard-id),
  not with the session name. That piece's heartbeat timeline reopens: the stall line, the average
  rate, and the recent rate all reaccumulate from the done=0 after the refire, not mixed in with
  the old trajectory.
- Quota and debounce: over a piece slot's whole task lifetime, **an automatic refire is allowed
  only once**, and it does not reset; if it dies again after a refire, stop and just record the
  incident and wait for a person. The same incident only pulls up one incident agent (each incident
  in the incident record has a number, and the sampler recognizes the number to prevent duplicate
  triggers).

## 6 Launch

```
python3 run.py launch <task> [task args] --piece <host>:<gpus> [--piece ...] \
  [--track <track>] [--note <what you want to verify>] \
  [--stall-line seconds] [--escalate-line seconds] [--warmup-line seconds] [--allow-dirty]
```

- The interpreter / script / cwd come from the registry; the dirty-tree gate carries over (the
  LEDGER_PATHS exemption is unchanged, `--allow-dirty` for smoke scenarios stays as before).
- `--piece <host>:<gpus>`, where gpus is a comma-separated list (one number per card, e.g.
  `tokyo108:0,1`). Before firing, each piece's card gets a live FREE probe; any card that is not
  FREE rejects the whole launch — the program only guards the line "never launch onto a card
  someone else is using"; which card to pick is still the agent's/person's judgment call.
- Sharding: a new key `shardable` is added to the TASKS registry (this key does not exist yet; the
  existing `shards=N` is a separate mechanism on RECIPES steps, don't mix them up). For a task
  marked shardable, when given multiple `--piece` entries, `--shard-id i --num-shards N` is
  auto-injected in piece order, with i starting at 0 — shard numbering no longer passes through
  human hands. A task not marked this way rejects multiple `--piece` entries outright (to prevent
  two cards each running a full copy and overwriting each other's output).
- Then, in one breath: start tmux (session name follows `new1_<task>_<host>g<gpus>`, with commas
  written as hyphens for multiple cards; log at `<workdir>/logs/<session>.log`) → register in three
  places (gpu-jobs register, record start, RUNMETA.json) → verify liveness → print the monitoring
  entry points. Liveness criterion: the session exists, the log has output within 30 seconds, and
  there is no traceback — that counts as a successful launch; whether loading has finished is left
  to the sampler's warm-up verdict, launch does not wait around for it.
- run_id consistency follows the original rule in CLAUDE.md (the raw data directory name / tmux
  session / ledger name / commit message stay consistent in all four places): the session name, the
  ledger name, the record run-id, and the log name are all generated by the program from the same
  run_id, not matched up by hand.
- A one-off launch outside the registry (the sole exception ruled on 2026-08-02) does not give
  `<task>`, instead using `run.py launch --name <run_id> --workdir <dir> --cmd '<full command>'
  --piece ...`: the command goes into tmux verbatim, the interpreter is written into the command
  itself, and registration still happens as usual.
- The two queueing launchers `launch-probe` / `launch-eval` are not merged; each keeps its own
  guard rails (launch-probe's queue table and smoke mode; launch-eval's hard dependency-order check
  and the check that the training artifact `best/` exists — it has no smoke mode); internally they
  are changed to call the same registration functions plus the same live FREE probe. Once changed,
  "the program guarantees registration" holds across every launch path, with no exception
  footnote.

## 7 Three exits

- **Terminal table**: `gpu-jobs` / `watch` switch to reading the sampling history, producing
  results instantly, with the table header carrying the last sample time, which lights up when
  stale. `free` and the card check before launch **always probe live, on the spot** — the iron rule
  of "never trust the cache" governs the decision to occupy a card, not viewing progress.
- **json**: the exit for agents; the verdict, rate, and ETA are all ready-made conclusions.
  job-monitor no longer measures speed at two points itself from here on — that action becomes an
  intrinsic capability of the sampler.
- **Web page**: an exit onto the same sampling history, for you to view remotely.
- The wrap-up process is unchanged: done is just a verdict, deregistering still goes through the
  fail-closed check of `gpu-jobs finish`, and the five steps of gpu-run skill's Phase 6a stay as
  they are.

## 8 Documentation write-back list

Reference points counted by grep (2026-08-08), to be changed one by one during implementation:

**Major changes**: `gpu-run/SKILL.md` (the Phase 4 launch section collapses into one launch
command, the Phase 5 monitoring regime changes to a sampler clause, the monitoring commands handed
to the user are replaced); `gpu-run/references/launch-methodology.md` (the tmux template section
moves under launch); `gpu-run/references/monitor-methodology.md` (two-point speed measurement
changes from an agent manual into a description of the program's responsibility);
`agents/job-monitor.md` (slimmed down to "read the json verdict + autopsy on demand," staying
read-only, with the division of labor against the incident agent written out clearly);
`agents/gpu-runner.md` (the launch section switches to launch, the double-registration section is
deleted); `probe-pipeline/SKILL.md` (the wrap-up chain at 74-75, G16 at 134, releasing/deregistering
at 172-173, the agent division-of-labor table at 221-222); `probe-pipeline/references/gates.md`
(the wording of G2/G16/G17); `references/stage-commands.md` (lines 19 and 352);
`references/invariants.md` (double-write bookkeeping: from "guaranteed by the person" to
"guaranteed by launch"); `references/extending.md` (add "wire up heartbeats" to the new-script
checklist, line 130 on job-monitor recognizing log events); `MAP.md` (the three lines for
gpu_jobs.py, launch_probe.py, launch_eval.py updated, one line each added for heartbeat.py /
sampler.py / launch); `CLAUDE.md` (the GPU section's monitoring commands and ledger entry point);
`ops/gpu_state.md` (the page-top pointer).

**Minor changes**: `handoff/SKILL.md` line 42, the "running tasks" table points to the sampling
history.

**Untouched**: `agents/env-runner.md` (CPU side, out of scope), exp-status / paper-write / the two
knowledge-map skills (no references).

## 9 Explicitly not doing (v1)

- CPU tasks do not enter the window.
- Mobile push notifications are not done; every incident in the incident record already carries
  the fields needed to locate it, so adding push later is purely additive.
- Automatically killing a live task is not done.
- The standing periodic check-in regime is retired, not improved — the sampler replaces it.
- The sampling history does not go into git.

## 10 Small things left to decide at implementation time

- The field table for the incident record and the json exit.
- The concrete file list of evaluation scripts to wire up with heartbeats (go through them one by
  one).
- How the piece output file name is generated from a template.
- The concrete web page layout.
- Turn every constant into configuration, to be tuned once it produces false positives: the stall
  line's 5x and the 3-round sampling floor, the escalation line's ×3, the 30-minute warm-up
  ceiling, the 10-heartbeat recent-rate window, the 10 rounds before probe failure turns red, the
  30-second liveness wait.
