---
name: gpu-run
description: >-
  The sole entry point for running any GPU program inside the new1 project — a
  full-lifecycle pipeline: read the slow-variable log → probe the cards for free ones →
  commit → smoke with `--debug` on the same setting → launch with one `run.py <workflow>
  <setting>` call, which walks that setting's stage list and stops after the launch,
  printing the monitoring command → read progress with `run.py ls` whenever a person
  wants to look → wrap up by re-running the same command, then `run.py table` and a
  commit, or interrupt with `kill` / `refire` / `retry`. Invoke whenever Dungeon♂Master
  says "run", "train", "inference", or any GPU work needs starting in new1. Chinese
  triggers: "跑程序" / "跑实验" / "跑一下" / "发射" / "用显卡跑" / "起个任务".
version: 1.1.0
---

# gpu-run — new1 GPU job full lifecycle

A mandatory pipeline for a job from birth to death: every stage of the walk below
leaves an artifact on disk, and skipping a step is a violation.

Fixed paths:
- Slow-variable log: `.claude/skills/gpu-run/references/gpu_state.md`.
- Measured task x card table: `.claude/skills/gpu-run/references/card_performance.md`.
- The one command: `run.py`, at the repo root, typed with the `probe` interpreter of
  `constants/path_datasets.yaml`'s `venvs:` map,
  `/home/y-guo/reproduce/new1/external/probe-env/bin/python` — that is the interpreter
  `README.md` gives `run.py` (`venv: probe`), and the system `python3` cannot import its
  dependencies. `run.py --help` lists every subcommand this file names.
- Cluster inventory: `constants/cards.yaml` (every host, and every card's model and
  memory). The login machine: `constants/path_outputs.yaml`'s `login_host:` key.

## Phase 0 — Read the log

Read three files, none of which says whether a card is busy right now:
- `constants/cards.yaml`: the card types and sizes, per host and per card index (the card's
  model and its `memory_gib`; tokyo108 mixes types, idx 0-2 H100 NVL and idx 3-5 H200 NVL).
- `.claude/skills/gpu-run/references/card_performance.md`: how each task performed on each
  card type (peak memory, wall-clock, throughput, outcome), and what has never been measured.
- `.claude/skills/gpu-run/references/gpu_state.md`: the other slow variables, driver and
  CUDA version per host and the alias dedupe (shiga=tokyo105, saitama=tokyo108, four
  physical machines).

A card's live occupancy is never read from these files.

## Phase 1 — Probe the cards for real

```bash
/home/y-guo/reproduce/new1/external/probe-env/bin/python run.py free
```

Free cards per host, over `constants/cards.yaml`'s hosts, probed now and
never cached. A card is busy when `nvidia-smi` shows a compute process on it, or when it
belongs to a piece of a run that has a start row with no finish row and either a live
session or a start row younger than the launch timeout (contracts 2.5). Every probe is
fail-closed: a failed or timed-out ssh counts as busy, so an unclear probe never frees a
card (contracts 3.4, 6.3).

### Pick the cards from the performance table, then name them with `--cards`

The probe says which cards are free; which of them fit the job is decided here, before
the launch, and handed to Phase 3 and Phase 4 as `--cards <host>:<id>,<id>,...` (once per
host). Count the cards the stage's pieces need:

| stage | pieces that hold a card | cards |
|---|---|---|
| `sample` | agent service x `sample.replicas` | `tensor_parallel_size` each |
| `inject` | agent service x `inject.replicas`, plus one probe service | `tensor_parallel_size` each, plus 1 |
| `train` | one train piece | 1 |

Then pick each piece's card type from `references/card_performance.md`: the smallest card
type whose measured peak memory for that task (stage, model, tuning, sizes) fits on the card
with margin. Card sizes are the `memory_gib` of each card in `constants/cards.yaml` (47 GiB on
tokyo105/106/107; on tokyo108 cards 0-2 are H100 NVL at 93 GiB and 3-5 are H200 NVL at
140 GiB). A task with no row in the table is smoked with `--debug` (Phase 3) on the card type
the nearest row suggests, and the smoke's result is appended to the table (Phase 6a). The
trainer on this tree prints no peak memory, so the table's training rows on this tree carry
only outcomes, among them the out-of-memory messages on 47 GiB cards, and its peak figures
for training come from the previous pipeline; the `--debug` smoke of Phase 3 is therefore
the check that the chosen card holds the job, and a smoke that runs out of memory moves the
job to the next card size up.

`jobs/launch.py` holds one size rule itself. An agent service that starts its own server
lands only on cards at least as large as the smallest card of its `models/table.yaml` row's
serving host; a train piece and a checkpoint-loading probe service have no size floor.
Without `--cards`, each piece goes to the first host that has enough free cards meeting its
floor — the agent service and the train piece try the agent model's serving host first, the
probe service tries the host the agent service landed on first, and the rest follow in
`constants/cards.yaml`'s host order — and claims that host's first such cards in the free
list's order. A train piece or a probe service launched without `--cards` therefore takes the
first free card whatever its size, so every launch this skill makes names its cards. With
`--cards`, the pieces claim from that pool only, in the order given, under the same floor: a
named card that is not free refuses the launch (`--cards names card(s) that are not free:
...`), and a pool with too few cards meeting a piece's floor refuses it, naming each pool card
smaller than the requirement with its size (`--cards names card(s) smaller than the <n> GiB
this piece needs: <host>:<id> (<m> GiB)`).

An agent service that an open run already serves on a pool host is attached to rather than
started again (contracts 7.4), and then takes no card from the pool. When the free list
holds no card of the size a piece needs, report the free list and stop; never launch on a
smaller card and never launch without `--cards` to get past it.

## Phase 2 — Commit before launching

The dirty-tree gate is one function, `jobs/launch.git_state(run_dir, allow_dirty)`: it
refuses a dirty tree without `--allow-dirty`, and with the flag writes `dirty.patch`
into the run directory and returns the git fields of the start row (contracts 2.5, 1.5).
`jobs/runs.jsonl`, `jobs/RESULTS.md` and any `*.lock` never count as dirty. The gate
guards every launch: Phase 4's walk, and the `refire` and `retry` of Phase 6b, which
`run.py --help` also lists with `--allow-dirty`. The flag covers the smoke of Phase 3;
every launch that produces a real result is committed first, Phase 6b's two included,
because a refire re-freezes `_commit` to the commit it cleared (contracts 2.3) and the
recorded HEAD has to lead back to the code that ran (the branch `CLAUDE.md`).

## Phase 3 — Smoke on the same setting

The smoke is `--debug` on the **same** setting, not a hand-shrunk copy:
`experimental_settings/debug.yaml` lays sizes only over whatever setting is named — a few
tasks, a few examples, a few steps — while the model, the tuning and the code path stay
the same (contracts 5.6). `--debug` is applied before keying and adds `debug: true` to
the key (contracts 3.4), so a debug run can never be mistaken for, or reused by, a real
one:

```bash
/home/y-guo/reproduce/new1/external/probe-env/bin/python run.py <workflow> <setting> --debug [--allow-dirty] --cards <host>:<ids>
```

The tree is often still dirty at this point, so `--allow-dirty` covers the smoke; the
commit of Phase 2 still has to happen before the real launch that follows.

## Phase 4 — Launch: one command walks the stage list

```bash
/home/y-guo/reproduce/new1/external/probe-env/bin/python run.py <workflow> <setting> [<setting> ...] [--debug] [--allow-dirty] [--cards <host>:<ids> ...] [section.field=value ...]
```

This is the whole entry point; `run.py --help` prints this argument shape. `--cards` is
the pool Phase 1 picked; it is where the launch runs and never part of the setting, so it
moves no key and no run directory. A call that names several settings, or a sweep parent,
shares the one pool: each launch takes its cards out of the pool and the next launch
claims from what is left, so the pool holds the cards of every child, and a child the
remainder cannot hold is refused with the free-card message. `<workflow>` is
the stem of a file under `experimental_settings/` (`baseline`, `train_probe`, `inject`);
`<setting>` is a name inside it, or a sweep child's own name
(`<setting>/<field>=<value>,...`); several settings may be walked in one call.

It walks the stage list of each named setting, and of each child a `sweep:` expands to,
one after another, each child with its own key, its own run directory and its own
registry row. For each: it freezes `settings.yaml` / `settings_diff.yaml`, takes
`jobs/runs.jsonl.lock` across the git gate, the launch gate, the attach test, the card
reservation, the port assignment and the start-row append (contracts 8.1, 8.6), starts
the service pieces, runs the probe service's `check` client for an `inject` run once its
port answers (contracts 2.3, 7.2), then starts the loop pieces — and **stops that
setting's walk there**, printing the monitoring command. One call over several settings,
or over a sweep parent, therefore leaves exactly one launched run per child.

The line `run.py: launched <run_id>; monitor with ...` is the only success signal, and a
failed launch takes one of four shapes. `jobs/launch.py` refuses before the start row is
written — the Phase 2 dirty-tree gate, the launch gate, a host with too few free cards —
and each of those refusals prints its own `jobs/launch.py: ...` line and exits 1, leaving
no registry row, nothing in Phase 5's `ls` and no piece log; that printed line is the
diagnosis. Every launch that started its pieces and did not come up exits 0 after printing
one line, `run.py: <run_id>: launch returned <outcome>; ended [<sessions>]`, appending a
`launch_failed` finish row and ending every session this launch started — service, loop and
train pieces alike. The `<outcome>` word names which shape it was. The second
shape is `alive_check`, a piece that started and then failed its alive check; a probe
service that never writes its endpoint file fails that same check, because a `service`
piece passes its alive check only when its endpoint file exists **and** its port answers.
The third shape is `service_check`, an `inject` run whose probe-service `check` client
fails its gate, and its `check: ...` lines stand above that one line. Read Phase 5's `ls`
line for the `launch_failed` row, and `<run_dir>/log/<piece index>.txt` for why the piece
died — on both paths the piece logs are the whole diagnosis. The fourth shape is an `inject` launch whose
probe-service endpoint file exists and whose port answers while the file never carries a
`base_url`: the start row is already written and the service pieces are already up, so
`jobs/launch.py: <path> did not appear within launch_timeout_s` exits 1 and leaves an
open `launching` row in Phase 5's `ls`, the piece logs under `<run_dir>/log/`, and the
service pieces alive on their cards — end them with Phase 6b's `kill`.

A GPU stage (`sample`, `train`, `inject`) is never waited on. A CPU stage (`build`,
`eval`, `score`) runs inline, in place, with no tmux and no ssh, and the walk goes
straight on to the next stage without stopping there.

Three `run.py`-held gates guard an `inject` launch specifically: the shared-build-key
gate and the code-currency gate of contracts 2.5, plus a third — `run.py` compares a
`key:` or `dir:` probe reference's stated `method:` against the referenced train run's
frozen `probe.method` before the stage starts (the `5.4 / 2.1` ruling of
`.scratch/from-zero/contract-errata.md`).

## Phase 5 — Monitoring is self-service

```bash
/home/y-guo/reproduce/new1/external/probe-env/bin/python run.py ls [workflow] [--debug]
```

One folded line per run, with each piece's verdict in priority order — `done`, `dead`,
`suspected stall`, `warming up`, `slowed`, `healthy` (contracts 8.5) — the mark
`(escalated)` after a verdict that has crossed the escalation line (a `suspected stall`
whose age is past three times the line that called it a stall, and every `dead`, so a
dead piece reads `0:dead(escalated)`), progress as
`done/total <unit>` and the recent rate, the heartbeat age, sessions and cards, and a
flag column: `edited`, `behind`, `consumed`, `split`, `pinned`, `dirty`, `debug`,
`orphan` (contracts 8.6). That priority order is the rule for a loop, train or cpu
piece; a `service` piece is judged by its port instead of by its beats, so it reads
`dead`, `healthy`, `suspected stall` or `warming up` and never `done` or `slowed`. A
live tmux session of this repo that matches no row gets a line of its own, with no
`run_id` and the verdict `orphan`.

An `edited` run is one whose named setting's current key no longer matches this
directory — an edited setting field, or a `VERSION` bump. When the key moved because a
file the run recorded had its effective `VERSION` raised, the line also carries a
trailing `stale=<path> VERSION <n>: "<why>"` naming that file and quoting the bump's own
`why`; an `edited` run whose key moved for any other reason carries no `stale=` text. A
`behind` run's recorded `VERSION` is below the current one but its key still matches, so
it stays usable and carries no `stale=` text.

`--debug` runs show only when `--debug` is given, because `ls` drops debug rows by
default, so the Phase 3 smoke is monitored with
`/home/y-guo/reproduce/new1/external/probe-env/bin/python run.py ls <workflow> --debug`.

A person looks when they want to; nothing patrols. There is no background process
computing verdicts: `ls` computes them on demand from the run directory's heartbeat
files and one `tmux ls` per host.

## Phase 6a — Wrap-up is re-running the same command

Re-run the identical `run.py <workflow> <setting> ...` call. What that re-run does
depends on the stage it lands on:

- `sample` and `inject`: the walk finds every requested pair done, writes `done.json`
  with the certified `pairs`, **tears the run's service pieces down**, and appends the
  `ok` finish row, in that order (contracts 2.3).
- `build` and `train`: the stage program already wrote its own `done.json`, so the walk
  only appends the finish row when the run still has none; there are no service pieces
  to tear down for either.
- `eval` and `score` **never skip** (contracts 2.4): the re-run recomputes the whole
  stage in place and appends that run's own finish row every time.

Then the walk goes on to the next stage, the same way Phase 4 does. Numbers reach
`jobs/RESULTS.md` through `done.json` -> the finish row -> the render; nothing is typed
in by hand (contracts 8.2).

The wrap-up call is the launch command, so it starts cards for any stage the walk lands
on that is not done: an incomplete `sample` or `inject` stage with no live work piece
releases its dead claims and relaunches on cards, and a completed stage lets the walk go
on into the next stage, which may itself be a GPU launch. The hard rule below holds here
too — an agent returns the command as `BLOCKED` and a person types it.

```bash
/home/y-guo/reproduce/new1/external/probe-env/bin/python run.py table [workflow] [--debug]
```

Prints the backbone x method x risk table, one group per (setting, debug flag) pair — a
sweep child's own name, never its parent — each cell the mean and spread over the
group's runs (the `5.5 / 8.6` ruling of `.scratch/from-zero/contract-errata.md`). Commit
`jobs/runs.jsonl` and `jobs/RESULTS.md` together, with the key in the commit message.

Append the run's row to `references/card_performance.md`, or update the row for the same
task x card, for every GPU run that finished and for every run that failed for memory, and
commit it with the two files above. The row carries the date, the run key, the sizes
(`debug` or the full sizes), the card type, the peak memory if one was recorded, the
wall-clock, the throughput, the outcome and the source file of each number:
- The card: the `host` and `gpus` of the pieces in the run's start row in `jobs/runs.jsonl`,
  with the model and `memory_gib` of that card in `constants/cards.yaml`.
- Wall-clock: the heartbeat span, the first to the last row of the working piece's
  `<run_dir>/heartbeat/<piece>-<launch>.jsonl`, and `elapsed_s` of the run's finish row in
  `jobs/runs.jsonl`; for `train`, the step, eval and save offsets in
  `<run_dir>/train_log.jsonl`; for an agent service, the vLLM log's "Model loading took"
  and "init engine ... took" seconds.
- Throughput: tasks per hour from the heartbeat span, written as derived; for an agent
  service, the vLLM log's "Avg generation throughput" lines.
- Peak memory of an agent service: the vLLM log's memory lines in
  `<run_dir>/log/<service piece>.txt` ("Model loading took", "Available KV cache memory",
  "GPU KV cache size", "Maximum concurrency", "Free memory on device ... on startup").
- A run that failed for memory: the `torch.OutOfMemoryError: CUDA out of memory. Tried to
  allocate ...` line in `<run_dir>/log/<piece>.txt`, quoted.

## Phase 6b — Interruption

- `/home/y-guo/reproduce/new1/external/probe-env/bin/python run.py kill <workflow>
  <setting> <stage>` writes the `killed` finish row and refuses while another live run
  is attached to this run's service (contracts 8.6).
- A dead piece: `/home/y-guo/reproduce/new1/external/probe-env/bin/python run.py refire
  <workflow> <setting> <stage> --piece i` — a liveness refusal first, then claims
  released, cards re-probed, the start row of the incarnation it is about to start
  appended, and a `launches` entry written beside it. It **warns**, and never refuses,
  when this piece already has more than one entry in `meta.json`'s `launches` (counted
  as the entries whose `pieces` list contains this piece index) — **there is no quota**
  (contracts 2.3). A refire is a launch and takes the Phase 2 dirty-tree gate, so commit
  the tree before it.
- "Start fresh": `/home/y-guo/reproduce/new1/external/probe-env/bin/python run.py retry
  <workflow> <setting> <stage>`, which also takes the Phase 2 dirty-tree gate. For
  `train` it deletes `last/`, `train_log.jsonl`, `train_done.json`, `align_check.json`,
  `consumed.json` and `done.json`, then launches normally (contracts 2.4). The resume
  checkpoint carries three names while the trainer swaps it — the new one is written into
  `last.tmp/`, and the one it replaces is held as `last.prev/` between the two renames —
  and `retry` deletes `last/` alone, so a kill inside a checkpoint write leaves
  `last.tmp/` or `last.prev/` on disk. The trainer settles those two at its next start,
  and a `last.prev/` with no `last/` beside it takes the name back: the run you meant to
  start fresh resumes from the pre-crash checkpoint, at its old step and with the
  alignment gate skipped. So after a kill inside a checkpoint write, remove `last.tmp/`
  and `last.prev/` from the run directory yourself before typing `retry`. For `sample`
  and `inject` it clears `done.json` and `consumed.json` only; those two stages resume
  from the per-pair files under the run directory's `records/` (contracts 2.3), which
  retry never deletes, so a partial directory continues exactly
  as a plain re-run would, and a directory whose per-pair files are already complete is
  re-certified — a rewritten `done.json`, a service teardown and a second `ok` finish
  row — rather than sampled again.
- All three key the real run and none of them parses `--debug`: typing the flag is a
  usage error, and leaving it off names the real run, so none of them can reach a Phase
  3 smoke. With that setting and stage carrying a real run, all three act on that real
  run: `kill` ends its pieces and writes its `killed` finish row; `refire` restarts one
  of its pieces, and refuses while that piece's session is alive, as the bullet above
  states; `retry` clears the markers first and unconditionally — `done.json` and
  `consumed.json`, and for `train` also `last/`, `train_log.jsonl`, `train_done.json` and
  `align_check.json` — and only then walks the stage. So `retry` against a live run
  deletes those files and launches nothing: a live `sample`, `inject` or `train` run stops
  at `run.py: <run_dir> has a live piece; launching nothing`, the refusal every card stage
  takes, `train` included — and for `train` its checkpoint directory and its training log
  are already gone by then. `kill` the run and let its pieces end before typing `retry`.
  With the smoke as the only run of
  that setting and stage, `kill` prints `ended []` and stops nothing
  while the smoke keeps its cards. End a smoke by hand instead:
  `ssh <host> tmux kill-session -t <session>` for every piece, service pieces included,
  taking each host and session from the smoke's Phase 5 `ls --debug` line, then
  `run.py sync` to write the missing finish row.

## Hard rules

- `jobs/runs.jsonl` is append-only and `jobs/RESULTS.md` is rendered — never hand-edited.
- `run.py` runs on any machine of the cluster; a piece placed on a machine other than the
  one `run.py` runs on is started over ssh.
- An agent never starts a GPU process; a step that needs a GPU is returned as `BLOCKED`
  with the ready-to-run command, and the main conversation launches it (the branch
  `CLAUDE.md`).
- One key is one directory, and `run.py where <workflow> <setting> <stage>` prints it,
  whether or not it exists yet.

## What is gone

- `run.py gpu-jobs free/register/finish/watch/json`, `run.py record start/finish`, and
  registering a launch by hand into several places -> one registry, `jobs/registry.py`,
  called through `run.py`'s ten reserved subcommands and through the walk itself.
- `run.py launch` with `--run-id`/`--track`/`--piece host:gpus`, and the queueing
  launchers `launch-probe` / `launch-eval` -> the single walk of Phase 4,
  `run.py <workflow> <setting> ...`; no command line here carries a `run_id`, a `--track`
  direction or a `host:gpus` pair, and there is no separate queue.
- `run.py runmeta` and `RUNMETA.json` -> `meta.json`'s `launches` list already carries
  what `RUNMETA.json` held.
- `ops/jobs.json`, `ops/runs.jsonl`, `ops/gpu_state.md` -> `jobs/runs.jsonl`,
  `jobs/RESULTS.md`, and this skill's own `references/gpu_state.md`.
- The resident sampler and `python3 run.py sampler`, the web page
  `http://localhost:8377`, and the sampling history it kept -> `run.py ls` computes
  every verdict on demand, from the run directory's own heartbeat files and one
  `tmux ls` per host; there is no background process, and nothing to restart after a
  merge.
- `incidents.jsonl` and the incident agent, and the escalation line's automatic
  consequence (spawning an agent on an escalation) -> `ls`'s `escalated` flag survives
  as something a person reads, not something that starts a process.
- The one-refire-per-piece quota -> `run.py refire` warns past one launch entry and
  proceeds; there is no quota, because the only refire left is a person's.
