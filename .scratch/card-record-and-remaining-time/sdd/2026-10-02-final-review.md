# Final review of card-record-and-remaining-time (757d006..abe9f97)

One opus reviewer over the files the feature touched (`jobs/`, `run.py`, `train/`, `models/`,
`tests/`, `README.md`, `.claude/skills/gpu-run/`).

## Findings, fixed at 496a996 (same row for `train` at c87bfc2)

- **B1 (important): an imported train run was recorded as a training run that used 0 GiB.**
  Under `train.import_from` the trainer trains nothing and initialises no card, so its record
  read `peak_gib` 0.0, and the train identity had no field that told it apart from a real
  training run with the same backbone and sizes. Fix: `train.import_from` is part of the
  train identity (`CARD_TASK_FIELDS["train"]`).
- **B2 (important): a resumed train incarnation recorded an inflated speed.** Its load beat
  said `done=0` while its next beat said the resume step plus 50, so the moved count included
  the previous incarnation's steps; `left=` read near zero for the first beats. Fix: the load
  beat counts from `resume_step`.
- The skill's step 2 now says a train speed counts the training steps with their validation,
  and the prediction pass comes on top.

## Minors and shelved items, adjudicated

| item | verdict |
|---|---|
| T01 F3, `launch: 0` when `meta.json` is missing | stays: `meta.json` is written in the launch hold before any finish row can close a card stage |
| T01 N1, no test for refire's `log_offset` | stays; a cheap later assertion in `test_refire_closes_the_dead_incarnation_before_its_start_row` |
| T01, a replica that died of memory in an `ok` two-replica run is not recorded | stays: vLLM memory failures happen at startup, which fails the alive check and is recorded |
| T03 F1, ragged `refire()` docstring line | stays (cosmetic) |
| T03, a CPU stage's dead incarnation gets no finish row on a re-walk | stays: no card record there; only the status is lost |
| T03, `registry.free()` runs before the dead incarnation is closed | stays (behaviour older than the feature); within `launch_timeout_s` a relaunch naming the same card in `--cards` is refused as not free |
| T04 F2, no test for the probe-service and cross-card-model table paths | stays |
| T04 N1, `starts[run_id]` lookup in `_card_type_lines` | stays: only a hand-edited ledger, which is forbidden, can put a card record above no start row |

## Observations, not acted on

- Sample and inject speed depends on `pieces` and `replicas`, which are not in the identity,
  so a row's median speed mixes runs with different piece counts.
- The probe service's figure is the memory reserved after loading, stored as `peak_gib`; it is
  not a peak during generation.
- Building the record of a 22-piece sample run holds the registry lock for about 3.75 s.

## For gyb: `notes/plans/2026-09-17-contracts.md` rows that now differ from the code

- 8.0, the `Heartbeat.emit` row: `extra` lists tok_in, tok_out and loss, not `mem_gib`.
- 8.4: the optional beat fields leave out `mem_gib`, and the train unit is `step` for training
  and `prediction split` for the prediction pass.
- 8.5, the `rates(first_beat, recent_beats)` row: the average is over the newest unit's beats,
  not the whole run.
- 8.2: the finish-row field table has no `card_record`; the registry reads `meta.json`,
  heartbeats, logs and `settings.yaml` for it, and launch and refire append a `launch_failed`
  row through `close_dead_incarnation`.
- 8.3: the piece entry fields do not list `log_offset`.
- 8.6: the `ls` row has no `left` column.

## Not verified on a card

- A sample or inject card record from a real run (the ledger held one record, a debug train
  run, at review time).
- The probe service's memory line (no inject walk has run since ticket 02).
