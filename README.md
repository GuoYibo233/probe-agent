# new1

This file is assembled whole from `notes/plans/2026-09-17-contracts.md` (0.2, 0.4)
by ticket 14. Until then each ticket's own files are listed here, one section
per ticket, kept verbatim at every wave merge (`.scratch/from-zero/spec.md` section 3).

## Ticket 01 — constants, the setting files, the read-only hook

```
  constants/              where things are on this cluster: datasets, outputs, weights. Read by code;
                          nothing here changes a result or enters a key. Edited when something arrives or
                          moves on disk; a path may change only for the same bytes at a new place, and a
                          new set of weights is a new alias in models/table.yaml
    path_datasets.yaml      per environment: the clone's home, the interpreter that runs its loop, its data
                            root, and split name -> task-id file; plus the top-level venvs: map, which is
                            where every interpreter path in this repo is written down (Part 6.3)
      read by: data/environments/__init__.py (the splits block, to resolve a split name),
               data/environments/appworld.py (home, data root, split files),
               experimental_settings/schema.py (the splits block, to validate a split value at load),
               jobs/launch.py (the venv column and the venvs map), run.py (the venvs map, for selfcheck's
               per-interpreter import test)
    path_outputs.yaml       the outputs root on NFS, the debug subdirectory under it, the login_host and the
                            hosts: list, the cluster inventory (Part 6.3 holds the keys and their shape)
      read by: experimental_settings/schema.py (run_dir), jobs/registry.py (ls walks the root, and the
               hosts list for tmux and card probes), jobs/launch.py (the login_host and the hosts list),
               run.py (the login_host)
    path_models.yaml        weights alias -> the directory the weights live in
      read by: models/__init__.py, models/agent_models/service.py (the weights path of the row it serves)

  experimental_settings/  everything in here changes a result. The YAML files are gyb's: a new kind of
                          experiment is a new file, a new experiment is a new named setting in a file, a
                          tuning is an edited value. Agents read them and never edit them (a hook refuses).
                          schema.py is code and is edited for a new hyperparameter (with a default that
                          reproduces the old behavior) or a new value on an axis
    debug.yaml              only sizes, and Part 5.6 holds them; never a model and never a tuning;
                            --debug lays it over any setting
      read by: experimental_settings/schema.py only
    baseline.yaml           workflow sample, score; named settings inside
      read by: experimental_settings/schema.py only
    train_probe.yaml        workflow sample, build, train, eval; named settings inside
      read by: experimental_settings/schema.py only
    inject.yaml             workflow inject, score; named settings inside
      read by: experimental_settings/schema.py only

  .claude/hooks/settings_readonly.sh       the hook that refuses any agent edit to
                          experimental_settings/*.yaml, and (Part 6.1) to models/table.yaml
```

## Ticket 02 — the on-disk formats and the probe's input

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
    imports: data/__init__.py
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

## Ticket 03 — the registry and the ledger

```
jobs/registry.py — the registry: runs.jsonl rows under a lock, meta.json, the
heartbeat, the verdicts, ls/where/find/kill/free, RESULTS.md.
  imports: none (repo); [PyYAML]
  used by: run.py, jobs/launch.py, agent/loop.py, data/build_dataset.py,
           train/utils/trainer.py, eval/utils/probe_eval.py,
           eval/score_run.py, eval/method_table.py
  reads:   constants/path_outputs.yaml, jobs/runs.jsonl, run directories'
           meta.json and heartbeat, ssh, tmux, nvidia-smi
  writes:  jobs/runs.jsonl, jobs/RESULTS.md, meta.json,
           meta.json.corrupt.<timestamp> (a corrupt meta.json renamed aside),
           heartbeat/<piece>-<launch>.jsonl, done.json
  venv:    any

jobs/runs.jsonl — one registry row per stage run, appended at start and at
finish by registry.py; never edited by hand; in git.

jobs/RESULTS.md — rendered from runs.jsonl by registry.py; never edited by
hand.

tests/test_registry_concurrent_append.py — two pieces appending to
runs.jsonl at once both land: eight forked processes append 20 start rows
each into a throw-away copy of the tree; asserts 160 lines land and every
line parses as JSON.
  venv:    probe
```

## How to run (ticket 03's own piece)

`jobs/registry.py` is a library with no `__main__`; nothing here is run
directly. Every stage program calls `append_start`/`append_finish`,
`write_meta`, `write_done` and `beat` to record itself; `run.py` (ticket 14)
calls `ls`, `where`, `find`, `kill`, `free`, `sync` for its subcommands.

Run the concurrent-append check with the probe interpreter:

```
external/probe-env/bin/python tests/test_registry_concurrent_append.py
```

## Ticket 05 — the environment contract and AppWorld

```
    environments/           one file per benchmark environment; the only place a new environment adds a file
      __init__.py           the contract and the entrance: class Environment declares the nine methods
                            (tasks, open, step, speculate, judge, close, split_args, build_call,
                            complete_call) with one line each and no logic, and the StepObservation
                            dataclass that step returns (4.2); open_env(name) imports
                            environments/<name>.py inside the function, checks the methods are there, and
                            returns the instance; requested_pairs(env, splits, tasks, n_tasks, seeds) is the
                            one definition of what a run asks for, as (split, task_id, seed) triples
                            (2.3); carries VERSION
        imports: none (repo); [importlib, PyYAML]
        used by: data/environments/appworld.py (subclass), agent/loop.py (open_env, StepObservation,
                 requested_pairs), agent/inject.py, data/build_dataset.py (open_env, requested_pairs),
                 train/methods/cgen.py, train/methods/cparam.py (open_env, for the environment their
                 validation metric's match takes, 2.6), eval/methods/cgen.py, eval/methods/cparam.py,
                 eval/score_run.py,
                 jobs/launch.py (tasks and requested_pairs, to resolve the split files before the pieces
                 start), run.py (open_env and requested_pairs, for the subset skip test and done.json's
                 pairs, 2.3)
        reads:   constants/path_datasets.yaml   writes: -   venv: any
      appworld.py           class AppWorld(Environment): the nine methods on the AppWorld package, its task
                            instruction variants, its no-code message, its call regex and Python call
                            syntax; carries VERSION
        imports: data/environments/__init__.py; [the appworld package, inside open() alone]
        used by: data/environments/__init__.py (by name)
        reads:   constants/path_datasets.yaml, the split task-id files
        writes:  the AppWorld per-task output directory, deleted by close()
        venv:    any at import and for the call-syntax methods; appworld to hold a world
```

The `imports:` line for `appworld.py` reads "inside open() alone", not contracts
0.2's "inside open()/step()/speculate()": the ticket text and errata E11 both
state the `from appworld import AppWorld` statement sits in `open` alone, with
the other four world methods using the handle `open` already stored. See the
report for T05.
