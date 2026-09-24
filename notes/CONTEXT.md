# CONTEXT — Repository-wide glossary

This file is only a glossary: one definition per term, used with the same name
and meaning across project-wide discussion and code comments. It does not
record implementation details; implementation decisions go into `docs/adr/`.

## Settled terms

- **Job (长程任务)**: a GPU task that enters the ledger. The criterion is
  "holds a GPU and runs long"; long-running CPU work and recipe steps are
  outside this scope (decided 2026-08-08; reasoning: in practice only GPU
  work actually runs long).
- **Ledger (台账)**: `ops/jobs.json`. The registry of jobs, with two lists,
  `{active, history}`.
- **Piece (分片)**: the portion of a job split onto one GPU / one machine;
  a job name in the ledger can carry multiple pieces. A four-tuple of
  host:gpus:session:log.
- **Window (窗口)**: the entry point for viewing job status, three outlets
  onto the same sampling history: a terminal table (for a person to check
  ad hoc in the terminal), json (for an agent to read), and a web page (for
  the user to check remotely, via ssh port forwarding) (decided 2026-08-08;
  the outlets went from two to three: json was split out as a dedicated
  outlet for agents).
- **Verdict (判定)**: the health conclusion a program gives for a piece,
  taking one of the values healthy / warming up / slowed / suspected
  stall / dead / done. Computed by the program, never guessed by an agent.
- **Launch (发射)**: the action of starting a job inside tmux and filling in
  all three registrations (ledger register, experiment record start,
  RUNMETA.json in the output directory). This project turns launch into one
  subcommand of run.py, so the registration is guaranteed by the program
  instead of relying on a person to remember; launch requires explicitly
  specifying machine:GPU, it actually probes that GPU before acting, and
  refuses if it is not FREE (which GPU to pick is left to the agent/person's
  judgment; the program only holds the line of "never launch onto a GPU
  someone else is using") (decided 2026-08-08). The two queueing launchers,
  launch-probe / launch-eval, are not merged into this subcommand, but
  internally call the same registration code and the same FREE probe check,
  so "the program guarantees registration" holds across every launch path
  (decided 2026-08-08).
- **Heartbeat (心跳)**: a structured line with a fixed prefix (progress +
  token count) that a script writes to its own log every time it finishes
  one progress unit. The monitoring side only recognizes heartbeat lines;
  it never guesses at log formats. Every script we write emits heartbeats;
  third-party programs (the vLLM service) do not, so the monitoring side
  parses their own built-in throughput log lines instead (decided
  2026-08-08).
- **Sampler (采样器)**: a monitoring process that stays resident in a tmux
  session on the login machine, periodically sampling every active job
  (reading heartbeats, probing whether it is alive), writing the results
  into the sampling history, and the same process opens an HTTP port to
  serve the web page (decided 2026-08-08). The former standing system of
  scheduled agent inspections is retired and replaced by the sampler: when
  a verdict turns dead (on the spot) or suspected stall past the escalation
  line, the sampler automatically spins up an incident agent (decided
  2026-08-08; the boundaries are covered in the four entries incident
  agent / autopsy / refire / incident record).
- **Escalation line (升级线)**: the threshold for how long a suspected stall
  must persist before an incident agent is spun up. Like the threshold for
  the suspected-stall verdict itself, it is not a fixed number per job; it
  adapts to that job's own typical heartbeat interval (the denser the
  heartbeats, the shorter the line), and can be manually overridden at
  launch time. The only floor comes from the sampling interval: if the
  downtime is shorter than a few sampling rounds, the sampler cannot tell
  "stopped" from "not yet seen" (decided 2026-08-08).
- **Incident agent (事故 agent)**: a headless claude instance (model pinned
  to opus) that the sampler automatically spins up when a verdict turns
  bad. Its only job is to get the experiment back in working order; it does
  not write a report for a person to read. It is a separate role from the
  read-only job-monitor in an interactive session: job-monitor is an
  inspector a person dispatches, the incident agent is the middle-of-the-
  night responder (decided 2026-08-08).
- **Autopsy (验尸)**: the action of reading the logs to locate the cause
  after a verdict turns bad. This is the incident agent's authority
  boundary: a dead piece gets an autopsy and is then automatically refired;
  a suspected-stall piece only gets an autopsy, never a kill, because a
  long heartbeat gap has false positives (checkpoint saving, a long
  evaluation segment), and wrongly killing a live job costs more than
  refiring a few hours late (decided 2026-08-08).
- **Refire (补射)**: relaunching a dead piece with its original command. An
  automatic refire still probes the target GPU first, same as any launch;
  the same piece is allowed only one automatic refire, if it dies again
  after that the process stops, leaves a record, and waits for a person
  (decided 2026-08-08).
- **Incident record (事故记录)**: the on-disk record of the event chain
  verdict turns bad → agent spun up → refire outcome, shown in its own
  section on the web page. Written by the program, not by an agent writing
  a report for a person to read; details get looked up live in a fresh
  session the next morning (decided 2026-08-08).
- **Sampling history (采样历史)**: the state record the sampler writes to
  disk on every sampling round. All three outlets, the terminal table, the
  web page, and the agent's json, read from it.
- **Piece split (分片)**: a `sample` or `inject` stage runs as several loop
  processes, their count the setting's `sample.pieces` / `inject.pieces`
  field; the launcher starts each one with `--piece i/n` and the program
  takes its share of the task list from that. `train`, `build`, `eval` and
  `score` are one piece each. Splitting is never left to a person to do by
  hand (brought into the glossary 2026-08-09 as "shardable"; the flag and the
  `--shard-id`/`--num-shards` injection went with the old registry).
- **Monitoring parameters (监控参数)**: three fields that can be overridden
  at launch time to control the verdict computation, at the piece level
  `stall_line` (the suspected-stall threshold, in seconds) and
  `escalate_line` (the escalation line, in seconds), and at the task level
  `monitor.warmup_s` (the warm-up cap, in seconds). If not given, the
  DEFAULTS in `ops/verdicts.py` apply, adapted to that task's own typical
  heartbeat interval (brought into the glossary 2026-08-09; the term comes
  from the implementation of tickets 02/09).

- **Unit (进度单位)**: the unit in the progress denominator, one task during
  collection, one step during training. The name is not forced to be
  uniform: a heartbeat must carry four fields, done / total / unit / ts
  (ts is that machine's own clock at the moment the heartbeat is written,
  used only to diff between heartbeats on the same machine), unit is
  reported by the script itself ("task" or "step"), token count and loss
  are optional, and the window displays whatever unit the script reports
  (decided 2026-08-08).

- **Probe (探针)**: a side-channel predictive model that reads the agent
  model's current thinking prefix and gives a prediction of the next tool
  call along with a confidence score. The old name "observer" is retired;
  the whole project calls it only the probe (decided 2026-08-08).
- **Cut (切口)**: a sentence boundary inside the thinking text. Both
  prediction and injection only happen at cuts (decided 2026-08-08).
- **Fire (出手)**: the moment the trigger rule evaluates true at a cut;
  speculation begins from this moment (decided 2026-08-08).
- **Inject (注入)**: putting the predicted call and its result back into the
  cut as text, so the model continues writing from there (decided
  2026-08-08).
- **Trigger point (θ)**: the confidence threshold used to decide firing. θ
  is always given manually by a person; if it is not given, startup is
  refused (decided 2026-08-08).
- **No-injection control / no probe (空注入对照)**: a control arm that wires
  up the method's whole machinery but never fires, used to verify that the
  machinery itself does not change model behavior (decided 2026-08-08).
  Operational name no probe: `live_appworld.py` with `--no-probe` added,
  trajectory meta records `arm="no_probe"` (decided 2026-08-18).
- **chat baseline**: the original chat-endpoint path, `run_appworld.py --api
  chat`, where the harmony template is applied server-side by vLLM, one
  whole request per step, with no cuts along the way. The "baseline" in the
  same-setup rule refers to this (decided 2026-08-18).
- **with probe**: the arm in a live run that wires up the probe and
  fires/injects at cuts, the default path of `live_appworld.py`, trajectory
  meta records `arm="probe"`. It differs from no probe only in whether it
  fires; its comparison against chat baseline is routed through no probe
  (decided 2026-08-18).
- **Same-setup rule (同设铁律)**: the baseline and the method must use the
  same experimental setup, the method side must not introduce any decoding
  technique the baseline does not have (decided 2026-08-08).
- **Backbone / axis (主干 / 轴)**: the backbone is the fixed, settled loop;
  an axis is a swappable component queued up to try. The division is laid
  out in `METHOD.md` (decided 2026-08-08).
- **Three-color tagging (三色标注)**: every item in a document is tagged
  [Current state]/[Settled, to change]/[Idea, undecided], and the
  three statuses are never mixed together in writing (decided 2026-08-08).
- **Skeleton arm (骨架臂, skel)**: a class of offline-injection arm where the
  tool name is pinned by the probe and the arguments are left for the agent
  model to write itself (decided 2026-08-08).
- **The genuine world (正身世界)**: the real environment instance replayed
  forward to the target step. Speculation executes on the genuine world,
  then rolls back once execution finishes; no trace of world state is left
  behind (decided 2026-08-08).

- **Injection format (format)**: the named way a fired probe's call and result are put back into
  the token stream — where (placement `p1` inside the open thinking, `p2` after closing the
  thinking as a message from the sender `prefetch`) and how the mechanism is explained
  (`e1` inline every time, `e2` once in the system prompt with a `[Prefetch]` marker).
  Table in `pipeline/inject/inject_format.py`, selected by `--format`; `note` is the
  pre-2026-09-12 text and the default (decided 2026-09-12).
- **prefetch sender**: the author name of the message a `p2` format appends after the thinking
  closes; named `prefetch` and not `python` so the model does not switch into calling the python
  tool, which the AppWorld harness has no server for (decided 2026-09-12).

## Undecided terms (under discussion, move up once settled)

(none yet)
