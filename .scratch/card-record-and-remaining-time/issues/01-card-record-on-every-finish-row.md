# 01 the card record on every finish row

Status: ready-for-agent
Blocked by: -
Spec: .scratch/card-record-and-remaining-time/spec.md (sections "The record", decisions 4, 5)

## What to do

Every finish row that `registry.append_finish` (`jobs/registry.py:208`) appends for a `sample`,
`inject` or `train` run carries a `card_record` field built in one helper inside
`jobs/registry.py`, in the shape the spec gives. No finish-row writer outside
`append_finish` changes.

1. `registry.hosts()` (`:81-97`) keeps each card's `model` from `constants/cards.yaml`; add a
   `card_model(host, index)` beside `card_memory_gib()` (`:100`).
2. The helper reads the run's open start row (its pieces, hosts, gpus, `beat_launch`), the
   run directory's `meta.json` (the launch ordinal), the frozen `settings.yaml` (the task
   identity fields, one constant per stage, the spec's list), the incarnation's heartbeat
   files, and each card-holding piece's log tail.
3. Memory figures: a train piece's `peak_gib` is the largest `mem_gib` in its incarnation's
   beats (absent until ticket 02 lands: then `null`); an agent service's `weights_gib`,
   `kv_cache_gib` and `max_concurrency` are parsed from its log with the three vLLM lines the
   spec quotes; a probe service's memory from the line ticket 02 adds (`null` when absent).
4. Failure: the memory patterns in one module constant; `memory`, `error` or `null`, and
   `failure_line` cut to 300 characters. Read only the last 16 KB of a log.
5. Speed over the incarnation's work-piece beats, the spec's formula; `null` with fewer than
   two counting beats.
6. A helper failure (an unreadable log, a missing settings file) never blocks the finish row:
   the affected field is `null` and the row is appended.
7. README section 2: the `jobs/registry.py` entry's `reads:` gains `settings.yaml` and the
   piece logs; the `jobs/runs.jsonl` line says a finish row of a card stage carries the card
   record.

## Acceptance

- A unit test (new cases in an existing `tests/` module that fits, CPU-only, temporary
  directory) builds a fake run directory with a train piece whose log ends in a CUDA
  out-of-memory traceback and beats carrying `mem_gib`, and one with an agent service log
  holding the three vLLM lines, and checks every field of both records.
- `run.py selfcheck` green; all seven test modules pass.
- `run.py version <stage> --same` rows for every stage whose code set holds a changed file.

## Comments
