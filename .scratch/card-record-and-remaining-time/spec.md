# Card record and remaining time: spec

Status: ready-for-agent (design decided by gyb on 2026-10-02; the points marked PROPOSED are
mine and stand unless he overrides them)

## Problem

An agent that picks a card for a GPU run should know how the same task went on each card
type before, above all where it ran out of memory, and how fast it ran. Today that knowledge
lives only in `.claude/skills/gpu-run/references/card_performance.md`, a 250-line table an
agent writes by hand after a run. A run is recorded only when the agent remembers, and the
facts are buried in prose. Three gaps in the code are why the hand table exists at all:

- A finish row in `jobs/runs.jsonl` carries `status`, `counts`, `metrics`, `report` and
  `elapsed_s` only: no card, no memory figure, no speed, and no failure reason. An
  out-of-memory death and any other death both read `launch_failed`.
- The trainer measures no GPU memory, and nothing reads the memory lines vLLM already prints
  into the agent service's piece log.
- A run whose pieces died and that is then relaunched by a walk or a `refire` gets a new start
  row with no finish row for the dead incarnation (`fold()`, `jobs/registry.py:463-465`,
  clears it), so that incarnation's outcome is lost.

Separately, `run.py ls` prints progress and a recent rate but no remaining time.

## Decisions

1. **DECIDED: every run records itself.** When any finish row is appended, the registry adds
   the card record of that incarnation: per card-holding piece, the host, the cards, the card
   model and memory, the memory figures measured, the failure reason read from the piece log,
   and the run's speed. No agent writes a row by hand any more.
2. **DECIDED: the record advises and never refuses.** The launcher does not block a card type
   because of a past failure; the gpu-run skill tells the agent to read the record and avoid
   repeating a failure.
3. **DECIDED: remaining time.** `run.py ls` prints the remaining time of each run, and the
   skill states an estimate before every launch from the recorded speed.
4. **PROPOSED: one place builds the record.** `registry.append_finish` (`jobs/registry.py:208`)
   builds it, so the four finish-row writers (`run.py:2162`, `:2194`, `:2444`, `:2466`,
   `jobs/registry.py:1350`, `:1367`, `run.py:862`, `:938`) get it without each copying a new
   field.
5. **PROPOSED: the status words stay.** `ok`, `launch_failed`, `killed`, `failed` keep their
   meaning; the new `failure` field says why (`memory`, `error`, or none).
6. **PROPOSED: the lookup view is a second table in `jobs/RESULTS.md`**, rendered from the
   finish rows by `registry.render()`, so no new file enters the tree.
7. **PROPOSED: past runs are not backfilled.** `jobs/runs.jsonl` is append-only; the records
   start with the first finish row after ticket 01 lands. The hand table stays as the frozen
   history of the runs before that.

## The record

A finish row gains one field, `card_record`:

```
"card_record": {
  "launch": 2,                      # the incarnation (meta.json launches ordinal)
  "task": {...},                    # the lookup identity, below
  "pieces": [
    {"index": 1, "kind": "service", "service": "agent", "host": "tokyo108", "gpus": "5",
     "card_model": "NVIDIA H200 NVL", "card_gib": 140,
     "weights_gib": 50.22, "kv_cache_gib": 73.63, "max_concurrency": 8.99,
     "failure": null, "failure_line": null},
    {"index": 0, "kind": "train", "host": "tokyo108", "gpus": "0",
     "card_model": "NVIDIA H100 NVL", "card_gib": 93,
     "peak_gib": 61.2, "failure": "memory",
     "failure_line": "torch.OutOfMemoryError: CUDA out of memory. Tried to allocate ..."}
  ],
  "speed": {"unit": "task", "done": 9, "span_s": 173.0, "per_hour": 187.3}
}
```

- **Card model and memory**: from `constants/cards.yaml`. `registry.hosts()` (`:81-97`) drops
  the per-card `model` today; it keeps it.
- **Memory figures**:
  - train piece: `peak_gib`, the largest `mem_gib` in the incarnation's heartbeat rows
    (ticket 02 adds `mem_gib`, `torch.cuda.max_memory_reserved()` in GiB, to every beat).
    A piece that died of memory still has the last beat before its death.
  - agent service: parsed from its piece log, the lines vLLM prints, quoted from
    `outputs/debug/sample/c32dc16e29c0/log/1.txt`: `Model loading took 50.22 GiB memory and
    ...`, `Available KV cache memory: 73.63 GiB`, `Maximum concurrency for 131,072 tokens per
    request: 8.99x`.
  - probe service: the line ticket 02 makes it print after loading its checkpoints.
- **Failure**: from the tail of the piece's log (`<run_dir>/log/<index>.txt`), read only for a
  piece whose verdict is `dead` or for a run whose status is not `ok`. `memory` when the tail
  matches one of the memory patterns kept in one constant (`CUDA out of memory`,
  `OutOfMemoryError`, `exceeds available Mamba cache blocks`, `No available memory for the
  cache blocks`); `error` for any other `Traceback`, with the last exception line; otherwise
  none. `failure_line` quotes the matched line, cut to 300 characters.
- **Speed**: summed over the work pieces (loop or train) of this incarnation, from their
  heartbeat rows: `(last.done - first.done) / (last.ts - first.ts)`, per hour, over the
  training beats only for `train` (ticket 02 gives the prediction phase its own unit).
  `null` when fewer than two counting beats exist.
- **Task identity** (`task`), the fields that decide memory and speed, read from the run's
  frozen `settings.yaml` at finish time and kept in one constant per stage:
  - every stage: `stage`, `debug`;
  - `sample`: `models.agent`, the number of cards per agent server;
  - `inject`: `models.agent`, and for the probe service the score and gen checkpoints'
    backbone and tuning;
  - `train`: `models.probe`, `probe.method`, `probe.tuning`, `probe.lora_r`,
    `train.max_len`, `train.events_per_mb`, `train.grad_ckpt`, `train.import_from` (an
    imported checkpoint trains nothing, so its record must not join a training row; added by
    the final review).
  CPU stages (`build`, `eval`, `score`) hold no card and get no `card_record`.

## The lookup view

`registry.render()` adds a second table to `jobs/RESULTS.md`, "Runs by card type": one row
per (task identity, card model), newest first, with the number of runs that finished `ok`,
the number that failed for memory, the largest peak memory seen (or, for an agent service,
weights + KV cache and the maximum concurrency), the median speed, and the newest run key.
A row with a memory failure names that run key and quotes its `failure_line`.

## The dead incarnation

Before a walk, `refire` or `retry` appends a new start row to a run that is still open and
whose pieces all read `dead` or `not started`, it appends the finish row of the dead
incarnation (`launch_failed`, with its `card_record`). The same rule that `ls` and `sync`
already apply (`registry.launch_failed()`, `:921`) decides it, without the 1800-second age
condition, because a person is relaunching it now.

## Remaining time

`run.py ls` adds `left=<h>h<mm>` to each open run's line: `(total - done) / recent_rate`,
from the numbers the line already prints. For `train` it is the remaining time of the
current phase (training or prediction), and the line says which. A run with no rate prints
`left=-`.

## The skill

After tickets 01 to 05, the gpu-run skill's step 1 reads the "Runs by card type" table in
`jobs/RESULTS.md` before the hand table, its step 2 takes the speed from there, and its
step 6.3 (writing a row by hand) is removed. The hand table gets a first line saying it is
the frozen history before the automatic record began.

## Code-era rows

None of these changes alters what a stage produces. Of the files the tickets change, only
`train/utils/trainer.py` (the `train` stage) and `models/probe_models/service.py` (`sample`
and `inject`) are in a stage's code set (`experimental_settings/schema.py`, the stage
table's `code` tuple). No ticket branch writes a `jobs/versions.yaml` row, because parallel
branches appending to its end would conflict; the main conversation writes the `--same`
rows for those three stages after merging ticket 02.

## Tickets

| # | ticket | blocked by |
|---|---|---|
| 01 | the card record on every finish row | - |
| 02 | memory and phase in the trainer's beats; the probe service's memory line | - |
| 03 | close a dead incarnation before a relaunch | 01 |
| 04 | the "Runs by card type" table in `jobs/RESULTS.md` | 01 |
| 05 | remaining time in `run.py ls` | 02 |
| 06 | the gpu-run skill reads the record | 01, 02, 03, 04, 05 |
