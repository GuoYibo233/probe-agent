# Speed and ETA methodology (gpu-run reference)

Read the sampler's verdict, decide next step. Never guess from memory, and
don't re-derive it by hand from raw logs either — that's the sampler's job.

Referenced by `.claude/agents/job-monitor.md` and gpu-run Phase 5. Originally a global
skill, moved into the project on 2026-07-30 with the global copy retired; the example paths
below are from the old project — **inside new1, always go by the ledger output of
`python3 run.py gpu-jobs json` and `<workdir>/logs/`**.

## When to invoke

- After a wakeup fires checking on a daemonized job
- User asks "how's it going", "ETA?", "is it stuck"
- About to quote an ETA or wall-time estimate to the user

## What the program is responsible for: where the verdict comes from

This document used to teach the whole manual workflow of "read tqdm at two points in time to
compute the real rate, correct the per-piece ETA, hand-parse progress lines" — that work is now
the standing responsibility of `ops/heartbeat.py` + `ops/sampler.py` + `ops/verdicts.py`: every
collection/training/eval script wired to heartbeats calls `emit(done, total, ...)` in its main
loop, and the background sampler reads a round of all heartbeats every `sample_interval_s`
(default 60 seconds), computes the verdict/rate/ETA using the six-cell judgment plus the
two-line formula below, and writes them into its own state file (`MONITOR_DIR/latest.json`).
**Prefer `python3 run.py gpu-jobs json` to read the verdict** — the terminal outlet already
reads from this sampling history (with a freshness threshold: within 5 minutes of `sampled_at`
it directly outputs the sampler's verdict, and past that it falls back to the old path of
probing on the spot, ticket 07 is done), this command directly outputs the verdict; the web
outlet `http://localhost:8377/json` is another route to the same data (a web page the sampler
runs itself, ticket 06 is done), either one is enough to read. **Do not go back to manually
paging through logs or hand-computing tqdm lines** — the manual workflow is only a fallback for
when the sampler can't find anything (e.g. the task was never wired to heartbeats, or the
sampler isn't running).

Six-cell verdict (`ops/verdicts.py`'s `V_DONE`/`V_DEAD`/`V_STALL`/`V_WARMUP`/`V_SLOW`/`V_OK`,
`judge()` checks them in a fixed priority order and stops at the first match):

| Verdict constant | Label | Match condition (excerpted from `judge()`) |
|---|---|---|
| `V_DONE` | done | `status=="done"` or `done >= total` |
| `V_DEAD` | dead | tmux session can't be probed (`alive is False`) |
| `V_STALL` | suspected stall | time since the last heartbeat (or since launch if no heartbeat has been seen yet) exceeds the stall line |
| `V_WARMUP` | warming up | no first heartbeat seen yet, and the warm-up cap hasn't been exceeded |
| `V_SLOW` | slow | recent rate < average rate × `slow_ratio` |
| `V_OK` | healthy | none of the above match |

Two-line formula (constants live in `ops/verdicts.py`'s `DEFAULTS`; never hardcode them
elsewhere):

- **Stall line** (how long without a heartbeat counts as a stall):
  `max(stall_mult × typical heartbeat interval, stall_floor_samples × sample_interval_s)`,
  defaults `stall_mult=5.0`, `stall_floor_samples=3`, `sample_interval_s=60.0`; the typical
  heartbeat interval is the median of the most recent ≤`typical_beats` (20) heartbeat
  intervals, and when there are fewer than `min_intervals` (3) samples it falls back to
  `warmup_line_s` (default 1800 seconds / 30 minutes) as a floor, to avoid a long task/long
  step being misjudged as stalled right at the start; if `--stall-line` was given at launch
  time, that number is used directly instead of computing the adaptive value.
- **Escalation line** (how long without a heartbeat before someone should step in):
  `stall line × escalate_mult` (default 3.0), or the `--escalate-line` given at launch time.
  Once past the escalation line, the sampler marks this round's `escalated` as true — this is
  the input to Phase 5's "only dispatch job-monitor once the incident record has content."
- Service-class pieces (launched with `--service`, e.g. vLLM) go through `_judge_service`:
  port-probe (`/health`) failing `port_fail_rounds` (default 3) rounds in a row records
  `V_STALL`, and it escalates once it reaches `port_fail_rounds × escalate_mult` rounds; before
  a single 200 has ever been probed, it is capped at the warm-up limit.

To change the verdict rules, change `ops/verdicts.py`'s `DEFAULTS` — this document is only
responsible for explaining what the rules are, not for teaching how to manually reproduce them.

## Decision tree

The input to judge on is the verdict value the sampler gives (the `verdict`/`escalated`
fields — `gpu-jobs json` has them directly when fresh, and falls back to probing on the spot
past that per the hint; the web page `http://localhost:8377/json` reads the same data), not
raw logs:

| Verdict | Action |
|---|---|
| `V_OK` healthy | No special handling needed, follow the pace in the Wakeup scheduling guidance below |
| `V_SLOW` slow | Check whether the tail data itself is just slower (e.g. samples with long output), report + extrapolate from the average |
| `V_WARMUP` warming up | No heartbeat yet, normal; exceeding the warm-up cap automatically turns into `V_STALL`, no need to manually chase it |
| `V_STALL` suspected stall, `escalated=false` | Note it down, check again next time on the regular cadence |
| `V_STALL` suspected stall, `escalated=true` | Read the logs to pin down the cause of death — the sampler has already recorded this into the incident record and automatically spawned a headless incident agent to handle it (**wired up, never rehearsed for real**); a human or Claude actively patrolling can also step in on finding this |
| `V_DEAD` dead | Read the logs to pin down the cause of death, refire if it can be fixed: `python3 run.py launch --refire <run_id> --idx <N>` |
| `V_DONE` done | Go through the Phase 6a wrap-up five-step, no need to keep monitoring |

## Wakeup scheduling guidance

Use `ScheduleWakeup` after monitoring:

| Phase | Suggested wakeup |
|---|---|
| First 5 min after launch (model loading) | +30-60 min (don't burn cache) |
| Mid-job, healthy progress | +1h |
| Final 30% of progress | +30 min |
| Job nearly done | +15 min |
| Idle GPU phase (waiting for one slow job) | +1h |

Use the `prompt: <<autonomous-loop-dynamic>>` sentinel for autonomous chains.

**Before a job has produced its first heartbeat there is no verdict to read, so a
first-cut estimate has to come from somewhere else — use the measured wall times
per stage, not a guess.** For the probe pipeline those live in
`.claude/skills/probe-pipeline/references/stage-commands.md §4.5` (eval: what each
script counts and minutes per cell) and `§3.1` (training: measured VRAM peaks).
Read the counting unit before multiplying — np821's eval scripts count *events*
(8533 in the test split) while the dataset holds *cut-point rows* (391893 in the
same split), and extrapolating from rows turned a 40-minute job into a 2–3 hour
estimate.

## Gotchas

- `tail -c 1000 | tr '\r' '\n'` — the `\r` translation is essential because tqdm uses `\r` to overwrite the same line; without it you'll see one giant line.
- Filter out `Loading weights` and `examples/s` progress bars (model loading or dataset saving), not the actual generation tqdm.
- `process count = 9` is normal for 4-active-job scheduler (4 sh wrappers + 4 python children + 1 scheduler).
- A scheduler exiting normally is silent — the only signal is `Done N Failed 0` line in scheduler.log.
