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
version: 1.0.0
---

# gpu-run — new1 GPU job full lifecycle

A mandatory pipeline for a job from birth to death: every stage of the walk below
leaves an artifact on disk, and skipping a step is a violation.

Fixed paths:
- Slow-variable log: `.claude/skills/gpu-run/references/gpu_state.md`.
- The one command: `run.py`, at the repo root; `run.py --help` lists every subcommand
  this file names. This machine has no `python`, only `python3`.
- Cluster inventory and the login machine: `constants/path_outputs.yaml`'s `hosts:` and
  `login_host:` keys.

## Phase 0 — Read the log

Read `.claude/skills/gpu-run/references/gpu_state.md` for the slow variables only:
driver and CUDA version per host, the alias dedupe (shiga=tokyo105, saitama=tokyo108,
four physical machines), and tokyo108's mixed card types (idx 0-2 are H100, idx 3-5 are
H200). A card's live occupancy is never read from this file.

## Phase 1 — Probe the cards for real

```bash
python3 run.py free
```

Free cards per host, over `constants/path_outputs.yaml`'s `hosts:` list, probed now and
never cached. A card is busy when `nvidia-smi` shows a compute process on it, or when it
belongs to a piece of a run that has a start row with no finish row and either a live
session or a start row younger than the launch timeout (contracts 2.5). Every probe is
fail-closed: a failed or timed-out ssh counts as busy, so an unclear probe never frees a
card (contracts 3.4, 6.3).

## Phase 2 — Commit before launching

The dirty-tree gate is one function, `jobs/launch.git_state(run_dir, allow_dirty)`: it
refuses a dirty tree without `--allow-dirty`, and with the flag writes `dirty.patch`
into the run directory and returns the git fields of the start row (contracts 2.5, 1.5).
`jobs/runs.jsonl`, `jobs/RESULTS.md` and any `*.lock` never count as dirty. Commit before
every real launch; `--allow-dirty` is for the smoke of Phase 3 only, never for Phase 4.

## Phase 3 — Smoke on the same setting

The smoke is `--debug` on the **same** setting, not a hand-shrunk copy:
`experimental_settings/debug.yaml` lays sizes only over whatever setting is named — a few
tasks, a few examples, a few steps — while the model, the tuning and the code path stay
the same (contracts 5.6). `--debug` is applied before keying and adds `debug: true` to
the key (contracts 3.4), so a debug run can never be mistaken for, or reused by, a real
one:

```bash
python3 run.py <workflow> <setting> --debug [--allow-dirty]
```

The tree is often still dirty at this point, so `--allow-dirty` covers the smoke; the
commit of Phase 2 still has to happen before the real launch that follows.

## Phase 4 — Launch: one command walks the stage list

```bash
python3 run.py <workflow> <setting> [<setting> ...] [--debug] [--allow-dirty] [section.field=value ...]
```

This is the whole entry point; `run.py --help` prints this usage line. `<workflow>` is
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
python3 run.py ls [workflow] [--debug]
```

One folded line per run, with each piece's verdict in priority order — `done`, `dead`,
`suspected stall`, `warming up`, `slowed`, `healthy` (contracts 8.5) — progress as
`done/total <unit>` and the recent rate, the heartbeat age, sessions and cards, and a
flag column: `edited`, `behind`, `consumed`, `split`, `pinned`, `dirty`, `debug`,
`orphan` (contracts 8.6). An `edited` run's key has moved because a file's effective
`VERSION` rose, and its line carries a trailing `stale=<path> VERSION <n>: "<why>"`
naming that file and quoting the bump's own `why`. A `behind` run's recorded `VERSION`
is below the current one but its key still matches, so it stays usable and carries no
`stale=` text.

`--debug` runs show only when `--debug` is given, because `ls` drops debug rows by
default, so the Phase 3 smoke is monitored with `python3 run.py ls <workflow> --debug`.

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

```bash
python3 run.py table [workflow] [--debug]
```

Prints the backbone x method table, grouped by parent, mean and spread over the group's
runs (contracts 8.6). Commit `jobs/runs.jsonl` and `jobs/RESULTS.md` together, with the
key in the commit message.

## Phase 6b — Interruption

- `python3 run.py kill <workflow> <setting> <stage>` writes the `killed` finish row and
  refuses while another live run is attached to this run's service (contracts 8.6).
- A dead piece: `python3 run.py refire <workflow> <setting> <stage> --piece i` — a
  liveness refusal first, then claims released, cards re-probed, a launch entry
  appended. It **warns**, and never refuses, when this piece already has more than one
  entry in `meta.json`'s `launches` (counted as the entries whose `pieces` list contains
  this piece index) — **there is no quota** (contracts 2.3).
- "Start fresh": `python3 run.py retry <workflow> <setting> <stage>` clears what the
  continue rule would resume from, then launches normally (contracts 2.4).

## Hard rules

- `jobs/runs.jsonl` is append-only and `jobs/RESULTS.md` is rendered — never hand-edited.
- `run.py` and `jobs/launch.py` refuse to run on any host but `login_host`; a piece on
  another machine is always started over ssh from there (contracts 8.6, 3.4).
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
