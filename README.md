# new1

This file is assembled from `notes/plans/2026-09-17-contracts.md` (0.2, 0.4).
Ticket 14 assembles the whole tree; until then, each ticket's own files are
listed here, per `.scratch/from-zero/spec.md` section 3. Merge conflicts on
this file across tickets of one wave are expected and are resolved at wave
merge by keeping every ticket's lines.

## Tree

```
data/                   the benchmark environments, and every format that lives on disk between two
                        stages: the record (agent -> build), the example (build -> train), the prediction
                        (train -> eval). One format per interface, defined here and nowhere else.
                        Nothing else is added here; a new environment goes under environments/
  __init__.py             the conventions the three formats share: read_frame and write_frame (Part 1),
                          so every read returns a Polars DataFrame with the format's declared columns
                          and types; the id rule; the VERSION / DEFAULTS / REQUIRED rule, including the
                          raise on a missing required column. Edited never
    imports: none (repo); [polars]
    used by: data/task_record.py, data/example.py, data/prediction.py, data/build_dataset.py (the id
             functions, which the builder calls rather than formatting a string)
    reads:   -   writes: -   venv: any
  task_record.py          the record one task run leaves: six row kinds, one file per (task, seed); write,
                          read, is_done, owner, to_messages; carries VERSION
    imports: data/__init__.py; [polars]
    used by: agent/loop.py (meta, gen, env, final), agent/inject.py (spec, resume),
             data/build_dataset.py, eval/score_run.py,
             jobs/launch.py (done_pairs, is_done, owner, release),
             run.py (done_pairs, is_done, owner, release: the completeness check, the progress count
             of 8.4 and the claim release, all of which happen on the login machine, 1.1)
    reads/writes: task record (jsonl)
    venv:    any
  example.py              the row build writes per cut: the record and cut it came from, the text the probe
                          sees, and all three targets; write, read; carries VERSION
    imports: data/__init__.py; [polars]
    used by: data/build_dataset.py (write), train/utils/trainer.py (read),
             train/methods/{ctool,cgen,cparam}.py (their target column)
    reads/writes: example (parquet)
    venv:    any
  prediction.py           the row train writes per example after training: the example id, its target, the
                          true tool, the score and class logits (ctool) or the generated text (cgen,
                          cparam); write, read; carries VERSION
    imports: data/__init__.py; [polars]
    used by: train/utils/trainer.py (write), eval/utils/probe_eval.py (read)
    reads/writes: prediction (parquet)
    venv:    any
  probe_input.py          what the probe is asked and shown: the cut positions in the reasoning (the
                          offline enumeration and the streaming one, which differ in their offset
                          convention and are therefore not comparable, contracts 1.7; the event-level
                          min_think gate lives in data/build_dataset.py offline and in agent/inject.py
                          live, which scores no cut until the thinking reaches min_think), and the text
                          assembled for the probe (the task, the clipped tool history, the thinking so
                          far). example.cut and spec.cut are not the same coordinate (contracts 1.7).
                          Pure functions whose every parameter is passed in, never a module constant and
                          never read from a file, so the offline and the live caller cannot drift;
                          carries VERSION
    imports: none (repo); [re]
    used by: data/build_dataset.py, agent/inject.py
    reads:   -   writes: -   venv: any
```
