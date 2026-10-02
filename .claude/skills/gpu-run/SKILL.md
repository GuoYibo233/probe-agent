---
name: gpu-run
description: >-
  The sole entry point for running any GPU program inside the new1 project: pick the cards
  from the measured card table, estimate the time, commit, smoke with `--debug`, launch with
  one `run.py <workflow> <setting> --cards ...` call, read progress with `run.py ls`, wrap up
  by re-running the same command, and record how the run went on its card. Invoke whenever
  Dungeon♂Master says "run", "train", "inference", or any GPU work needs starting in new1.
  Chinese triggers: "跑程序" / "跑实验" / "跑一下" / "发射" / "用显卡跑" / "起个任务".
version: 2.0.0
---

# gpu-run

Only the main conversation and the `gpu-runner` agent start a GPU process, always through
this skill. Every other agent returns a step that needs a GPU as `BLOCKED` with the
ready-to-run command.

`run.py` is the only command. Type it as
`/home/y-guo/reproduce/new1/external/probe-env/bin/python run.py ...` (written `run.py`
below). It runs on tokyo108; typed elsewhere it re-runs itself there, so never wrap it in
`ssh`. `run.py --help` lists every subcommand and flag; read it when a detail below is not
enough. When the launcher refuses something, its printed line says why; read it before
guessing.

## 1. Pick the cards

Read three files first:

- `constants/cards.yaml`: every host and card, with its model and memory.
- `references/card_performance.md`: how each task ran on each card type (peak memory,
  speed, outcome). Its failure rows are the record of what not to repeat.
- `references/gpu_state.md`: drivers and cluster traps.

Then run `run.py free` for the cards that are free right now (never trust an older probe).

Choose the smallest card type on which the same task (stage, model, tuning, text length)
already ran with margin, and never a card type on which it failed for memory. A task with no
row is smoked on the card type its nearest row suggests; a smoke that runs out of memory
moves to the next size up. Cards per stage:

| stage | cards |
|---|---|
| `sample` | one agent server per replica |
| `inject` | one agent server per replica, plus one card for the probe service |
| `train` | one |

Known limits (the table holds the evidence):

- Agent servers (vLLM) run only on tokyo108; the vLLM venv hangs on tokyo105/106/107. A card
  pool for a walk that reaches `sample` or `inject` therefore names a tokyo108 card.
- Train pieces and probe services run on any host.
- A run attaches to a live agent server of the same model whose cards are in its pool,
  instead of starting a new one.

Always pass the chosen cards as `--cards <host>:<id>,<id>` (once per host). Without it the
launcher takes the first free card whatever its size. When no fitting card is free, wait
for one; never take a card that is not free and never launch on a smaller one.

## 2. Estimate the time

Before the launch, state an estimate: the work size (tasks x runs, or training events x
passes) divided by the same task's measured speed on that card type in the card table. Say
which row the speed comes from, or that no row exists.

## 3. Commit, then smoke

Commit before any real launch: the recorded HEAD must lead back to the code that ran. The
launcher refuses a dirty tree; `--allow-dirty` is for the smoke only.

The smoke is the same command with `--debug`: the same setting, the same code path, at the
small sizes of `experimental_settings/debug.yaml`, written under the debug directory. A
setting that names another setting (`eval.theta_from`, `inject.probe_score`,
`inject.probe_gen`, `score.baseline`) reads that setting's debug run, so smoke the named
settings first.

## 4. Launch

```bash
run.py <workflow> <setting> [<setting> ...] [--debug] [--allow-dirty] --cards <host>:<ids> [section.field=value ...]
```

The call walks the setting's stage list: a CPU stage (`build`, `eval`, `score`) runs in
place, a GPU stage (`sample`, `inject`, `train`) is launched in tmux and the walk stops
there. `run.py: launched <run_id>; monitor with ...` is the only success line. A launch that
fails prints `launch returned <outcome>`; the reason is in `<run_dir>/log/<piece>.txt`.

**Code gate.** When a stage's code has changed since a directory it reads was produced, the
walk refuses and prints the diff summary. Read the full diff, then:

- the output is unchanged (a rename, a log line, a path this stage never enters):
  `run.py version <stage> --same --from <commit> --why "<one sentence>"`;
- the output changes: `run.py version <stage> --why "<one sentence>"` (new directories from
  then on).

When unsure, write the second. Commit the row, then repeat the launch command.

## 5. Monitor

`run.py ls [workflow] [--debug]` prints one line per run: each piece's verdict, progress,
recent rate, heartbeat age and cards. Remaining time is (total - done) / rate; say it when
reporting. Nothing watches in the background; when you check a long run on a schedule,
check every 30 minutes.

## 6. Wrap up

1. Re-run the identical launch command. It certifies a finished `sample` or `inject` run,
   tears down its servers (freeing the cards), writes the finish row, and walks on to the
   next stage, which may launch the next GPU stage.
2. `run.py table`, then commit `jobs/runs.jsonl` and `jobs/RESULTS.md` with the run key in
   the message.
3. Add or update the row in `references/card_performance.md` for every GPU run that finished
   or failed for memory: date, run key, sizes, card type, peak memory, wall-clock, speed,
   outcome, and the file each number came from (the vLLM log's memory and throughput lines,
   the heartbeat span, the out-of-memory line quoted from the piece log). Commit it with the
   two files above.

## 7. Interrupt

- `run.py kill <workflow> <setting> <stage> [--debug]`: end every piece of a run.
- `run.py refire <workflow> <setting> <stage> [--piece i]`: restart one dead loop or train
  piece; it continues from its records or its last checkpoint.
- A dead agent or probe service: `kill` the run, then re-run the launch command; the loops
  resume from their records.
- `run.py retry <workflow> <setting> <stage>`: start a stage fresh. For `train` it deletes
  the checkpoints and the training log first, so commit before typing it.

## Rules

- `jobs/runs.jsonl` and `jobs/versions.yaml` are append-only; `jobs/RESULTS.md` is rendered.
  Never edit them by hand.
- Never start a GPU process outside `run.py`: no bare ssh, no nohup.
- A finished run's servers are torn down at wrap-up; holding a card "just in case" is not a
  reason.
