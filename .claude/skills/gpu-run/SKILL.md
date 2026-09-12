---
name: gpu-run
description: >-
  The sole entry point for running any GPU program inside the new1 project — a
  full-lifecycle pipeline: read the slow-variable log → probe the cards for free ones →
  pick cards and shard → smoke → launch with a single `launch` command (auto-registers in
  three ledgers) → tell the user the self-service monitoring command → hand off to the
  sampler for verdict and escalation → wrap up (report + free VRAM + deregister) or
  interrupt midway. Invoke whenever Dungeon♂Master says "run", "train", "inference", or
  any GPU work needs starting in new1. Chinese triggers: "跑程序" / "跑实验" / "跑一下" / "发射" /
  "用显卡跑" / "起个任务".
version: 1.0.0
---

# gpu-run — new1 GPU job full lifecycle

A mandatory pipeline for a job from birth to death. Every step has an artifact; skipping a step is a violation.

Fixed paths (NFS, consistent everywhere):
- Slow-variable log: `/home/y-guo/reproduce/new1/ops/gpu_state.md`
- Ledger CLI: `python3 run.py gpu-jobs` (registers jobs; underlying implementation is `ops/gpu_jobs.py`;
  recording numbers goes the same way through `python3 run.py record`. This machine has no `python`, only `python3`)
- Launch methodology (card-picking rules / sharding / what `launch` does for you): `.claude/skills/gpu-run/references/launch-methodology.md`
- Speed and ETA methodology (`ops/verdicts.py` verdict rules / decision tree): `.claude/skills/gpu-run/references/monitor-methodology.md`
- Card-probing script: `.claude/skills/gpu-run/scripts/gpu_status.sh`

## Phase 0 — Read the log

Read `ops/gpu_state.md`. Focus on: alias deduplication (shiga=105, saitama=108),
tokyo106/107 only having CUDA 12.2, and tokyo108's H100/H200 index layout.

## Phase 1 — Probe the cards for real (never trust the cache)

```bash
python3 run.py gpu-jobs free   # ≈6 seconds (run from repo root)
```

Only use cards where OWNERS=FREE. Another user's process (even at 0% util) is off-limits.
Your own leftover process: first decide whether it's a warm service; ask if it isn't clear.

## Phase 2 — Pick cards + shard

Follow the rules in `references/launch-methodology.md`: estimate VRAM as bf16 ≈ 2×params GB;
fits in 48G → prefer 105/106/107, big model → 108; shard only when there are many
independent items and a single card would take >1h; sharded outputs must be written to distinct files.
**Additional project-specific constraint**: tasks that need to install a new CUDA wheel avoid 106/107 (the 12.2 trap);
an existing cu128 wheel (e.g. mbert-env's torch) must first be spot-checked for 10 seconds to confirm it runs before going on 106/107.

## Phase 3 — Smoke before scaling up

For any task not explicitly told to already be "validated at small scale," first fire a smoke run
of a few dozen items/steps; only launch the full run once the log shows real progress (model
finished loading, first batch, a tqdm line). If smoke fails, fix it; if it can't be fixed, report
it with the traceback — never force a full launch.

**The tree during the smoke phase is often dirty** (code was just changed and hasn't been
finalized), so use `python3 run.py show <task> --allow-dirty` / `python3 run.py launch-probe smoke … --allow-dirty`
to get the command for this stage: smoke artifacts are not recorded and don't go into `runs.jsonl`,
so they're not bound by the "HEAD must be able to trace back to the code" rule.
Rerunning `launch-probe smoke` on the same smoke directory needs `--force` too (the smoke directory
name is deterministically derived from batch/model/cell, so a second run is blocked by the "an out
with an existing train_log.jsonl" guard). Smoke can also be previewed with
`python3 run.py launch <task> ... --dry-run` to see the actual command each piece will run —
it only prints, it does not launch or register.
**A commit is required before the real launch (Phase 4)** — that step's dirty-tree gate must not
be papered over with `--allow-dirty`.

## Phase 4 — Commit before launch + launch + hand off the monitoring entry point

**How to execute**: dispatch the entire launch segment to a `gpu-runner` agent (card-probing/smoke/launch/liveness-check
all bundled to it, opus is sufficient) rather than hand-doing it in the main conversation —
the main conversation is responsible for planning and writing scripts.

1. **Commit the code**. The git HEAD stored in the experiment record can only trace back to
   the actual code that ran when the working tree is clean. `record.py` prints a ⚠️ on a dirty
   working tree but does not block you — a broken trace is your own loss.
   `run.py` at the repo root pushes one step further from here: for GPU/launch-class tasks in
   the registry, it checks `git status` before producing the command, and a dirty tree is
   refused outright (`--allow-dirty` is the escape hatch) — a hard gate in force since 2026-08-02.
2. **`python3 run.py launch`**:
   ```bash
   python3 run.py launch <task> [task args...] --run-id <run_id> --track <direction> \
     --piece <host>:<gpus> [--piece <host2>:<gpus2> ...] [--note "..."] \
     [--outdir <output dir>] [--stall-line seconds] [--escalate-line seconds] \
     [--warmup-line seconds] [--service]
   ```
   One command does all ten steps pinned into the launch pipeline (order is in the head
   comment of `ops/launch_cmd.py`): parse args → dirty-tree gate → piece parsing (multiple
   pieces require the task to be marked `shardable: True` in the registry; each piece
   automatically gets `--shard-id i --num-shards N` injected) + session/log naming
   (session name `new1_<run_id>_t<host with the tokyo prefix stripped>g<gpu>`, log
   `<workdir>/logs/<session>.log`) → probe each piece for real, and refuse the entire launch
   if any is non-FREE (not a single occupied card gets launched) → fire in tmux → a 30-second
   liveness window (every piece passes early as soon as its log byte count grows; a failure is
   only counted if the session is gone or a Traceback shows up in the tail by the time the
   window closes — already-launched pieces are neither rolled back nor registered on failure,
   and a failure prints the last 40 log lines of each failed piece) → the ledger
   `ops/jobs.json`, the experiment record `ops/runs.jsonl` (via a `record.py start` subprocess),
   and the output-directory `RUNMETA.json` — all three registrations done in one pass
   (`ops/launch_common.py`'s `register_all`, in a fixed order RUNMETA → ledger → record:
   RUNMETA goes first because the launch has already really happened, so the artifact-to-code
   pin lands first; if the ledger/record steps later refuse (duplicate run_id) that won't drag
   RUNMETA down with it; a RUNMETA write failure is only a WARN, while any failure in the
   ledger/record steps is thrown straight through, never swallowed). `register_all` is the sole
   writer of RUNMETA: the two queueing launchers `launch-probe` / `launch-eval` hand it the
   output directory, kind (`train` / `eval_tool` / `eval_call`), and the session/gpu/log/queue
   table to write, and the receipt carries a `RUNMETA: <path>` line; the
   `WARN --outdir not given, RUNMETA not written` line only shows up when `run.py launch`
   wasn't given `--outdir` — that's the only case where it's really not written. Before
   2026-08-26 the two queueing launchers each wrote one record themselves and then called
   `register_all`, so that WARN line in the receipt was a false alarm; hand-filling `runmeta`
   based on it leaves two duplicate records in the same RUNMETA (observed in the np821 batch).
   The workflow of manually typing three registration commands no longer exists.
   `--run-id`/`--track` are required (a hard requirement of `record start`; `--track` must
   match a direction in `TIMELINE.md`); RUNMETA is only written when `--outdir` is given,
   otherwise it just prints a `WARN` line (for tasks whose output directory can only be
   determined afterward, fill it in later yourself with
   `python3 run.py runmeta <output dir> --cmd '<full command>' --kind <kind>`;
   `kind` is a free-form string — auto-registration by launch writes `launch`, the two
   queueing launchers write `train` / `eval_<stage>`, and a manual backfill should pick
   whichever of these values fits).
   A one-off command outside the registry goes through the `--cmd '<full command>' --workdir <dir>`
   escape hatch: it skips the TASKS lookup, the command goes into tmux as-is, and registration
   still happens.
   When a piece dies and needs to be relaunched in the same session (refire):
   `python3 run.py launch --refire <run_id> --idx <N> [--piece host:gpus]` — this does not
   start a new record or register again, it only updates that piece's host/gpus/log/
   launched_at quadruple in the ledger.
3. **Hand off the monitoring entry point**: a successful `launch` prints these two lines
   itself; make sure they appear in the reply to the user (this is the entry point for the
   user's own monitoring):
   ```bash
   cd /home/y-guo/reproduce/new1 && python3 run.py gpu-jobs           # one look
   cd /home/y-guo/reproduce/new1 && python3 run.py gpu-jobs watch     # auto-refresh every 30s
   ```
   The table shows each piece's progress, measured rate, ETA, and tmux liveness.
   **Both commands also list "tmux sessions outside the ledger" at the end** (bare `gpu-jobs`
   and `watch` both go through the same `collect(with_extras=True)`), which scans the fixed
   four machines `tokyo105/106/107/108` — not just the hosts already in the ledger — so even
   when the ledger is empty you can still see a session that missed registration or something
   another conversation is running.
   Plus the browser at `http://localhost:8377` (via ssh port forwarding): a web page the
   background sampler (next section) runs itself, showing the six-cell verdict computed by
   `ops/verdicts.py` (healthy / slow / warming up / suspected stall / dead / done); the `/json`
   route serves the same data in a machine-readable form — the terminal outlets
   `gpu-jobs`/`watch`/`json` already read from this sampling history (ticket 07; see
   `references/monitor-methodology.md` for the exact rules): within a 5-minute freshness
   threshold `latest.json` is rendered directly as the verdict, and past that it falls back to
   the old path of probing on the spot (tailing logs / probing the session over ssh) — there's
   no need to separately open the web page to check.

## Phase 5 — The sampler takes over (Claude no longer does standing patrols)

Verdicts and escalation are the responsibility of the background sampler (`ops/sampler.py`
reads all heartbeats once every `sample_interval_s` (default 60 seconds), computes each
piece's verdict/rate/ETA using `ops/verdicts.py`, and writes them into its own state file
(`latest.json`, which the web outlet reads directly; see `references/monitor-methodology.md`
for the exact rules) — there's no more need to rely on Claude scheduling periodic patrols.

Claude only dispatches the read-only `job-monitor` agent to read the sampling results
(`python3 run.py gpu-jobs json` — within the 5-minute freshness threshold it directly outputs
the sampler's verdict, and past that it automatically falls back to probing on the spot; the
web page `http://localhost:8377/json` is another outlet for the same data, either one is
enough to read) at two moments:
1. the user asks about progress/ETA/whether something is stuck;
2. there is new content in the incident record (`incidents.jsonl`) (meaning the sampler has
   judged at least one escalation).

**Incident-agent auto-autopsy-and-refire: wired up, never rehearsed for real.**
`ops/sampler.py`'s `should_trigger` (a pure function for the trigger rule) and
`maybe_trigger_incidents` (which pulls in an agent once triggered) were implemented by the
main conversation on 2026-08-08 with the user's authorization: when an escalation happens, it
first writes an incident record into `incidents.jsonl`, then spawns a headless `claude`
subprocess (model pinned to opus, detached and not waited on, output written to
`monitor/incidents/<incident id>.out`), and simultaneously marks `incident_open` to keep the
same incident from pulling in an agent again on every subsequent round. A manual rehearsal was
called off by the user's own decision — the whole chain is backed only by unit tests, no agent
has ever really been pulled in, and this chain will be running for the first time whenever the
first real incident happens. An escalation can still be caught by a human or by Claude actively
patrolling, reading the logs to pin down the cause of death, and refiring with
`python3 run.py launch --refire <run_id> --idx <N>` if it can be fixed.

## Phase 6a — Normal wrap-up (mandatory five-step)

1. **Report**: where the result files are, whether the counts are right (count == total after
   merging pieces), and the key numbers in one line.
2. **Record the numbers**:
   ```bash
   python3 run.py record finish <run_id> --metric <k=v> [--metric ...] \
     --data <path to final data> --conclusion "one-line conclusion"
   ```
   The numbers go into `RESULTS.md` automatically. **If this conclusion changes any judgment in
   `WORKPLAN.md`, also append a direction decision to the top of `TIMELINE.md`** (write clearly
   what was decided, which run_id triggered it, and what it invalidates). Plain progress does
   not need a TIMELINE entry — that's the job of the `plans/` worklog.
3. **Release**: kill every leftover tmux session / vLLM service, and confirm with `nvidia-smi`
   that VRAM is back to zero. A batch job must not hold a card overnight after it finishes.
4. **Deregister**: `python3 run.py gpu-jobs finish <task>`. It **refuses to deregister** if a
   session is still alive and lists the alive session names — check first whether the job
   actually finished (a mistake hit before: deregistered at 16:52 while the job actually ran
   until 18:17).
   **A probe failure gets the same refusal** (fail-closed): when ssh can't reach a host, it
   can't tell whether the session is dead or alive, so it lists the hosts whose probe failed
   and exits, instead of treating them as "no session" and letting it through.
   Both kinds of refusal share the same escape hatch: `finish <task> --force` (which stamps a
   `force_finished` marker in the history).
5. **Commit**: `git add` the code changed this time plus the three ledger files
   `ops/runs.jsonl` + `RESULTS.md` + `ops/jobs.json` (+ `TIMELINE.md` if any), with the run_id
   in the commit message.
   **Committing the ledger is for historical preservation** — it pins this run's numbers and
   ledger changes into git history, so `git log` can later look up which version of the ledger
   corresponds to which experiment.
   It is **no longer** "needed for the next launch to work": since 2026-08-02 these three files
   plus `ops/*.lock` are on a whitelist exemption in the dirty-tree gate (`run.py`'s
   `LEDGER_PATHS`, with `ops/record.py` and `ops/runmeta.py` each keeping their own copy of the
   same list) — an uncommitted ledger will not block the next launch.

## Phase 6b — Interrupted midway (the user calls a stop, or a patrol judges it dead)

1. Per piece, `ssh <host> tmux kill-session -t <session>`.
2. Confirm with `nvidia-smi` that VRAM has been released.
3. Report how far it got, where the logs and partial output are, and whether it can be resumed
   from a checkpoint.
4. `finish <task>` to deregister, keeping a record in the ledger history.

## Hard rules

- The ledger is only read and written through `run.py gpu-jobs register/finish`; never
  hand-edit jobs.json.
- Occupancy state is always probed live in Phase 1; the log file only records slow variables.
- One name per job; if a name is reused, finish the old one first.
- Numbers are only ever written through `run.py record start/finish`; `RESULTS.md` is a
  rendered artifact, and a hand edit gets overwritten on the next render. `runs.jsonl` is
  append-only, never edited.
- run_id is the primary key running through everything: the raw data directory name / tmux
  session / ledger name / commit message must all match — missing one breaks a link in the trace.
