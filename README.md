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
    used by: data/trajectory_record.py, data/training_data.py, data/probe_output.py, data/build_training_dataset.py (the id
             functions, which the builder calls rather than formatting a string)
    reads:   -   writes: -   venv: any
  trajectory_record.py    the record one task run leaves: six row kinds, one file per (task, seed); write,
                          read, is_done, owner, to_messages; carries VERSION
    imports: data/__init__.py
    used by: agent/loop.py (meta, gen, env, final), agent/inject.py (spec, resume),
             data/build_training_dataset.py, eval/score_run.py,
             jobs/launch.py (done_pairs, is_done, owner, release),
             run.py (done_pairs, is_done, owner, release: the completeness check, the progress count
             of 8.4 and the claim release, all of which happen on the login machine, 1.1)
    reads/writes: task record (jsonl)
    venv:    any
  training_data.py        the row build writes per cut: the record and cut it came from, the text the probe
                          sees, and all three targets; write, read; carries VERSION
    imports: data/__init__.py; [polars]
    used by: data/build_training_dataset.py (write), train/utils/trainer.py (read),
             train/methods/{ctool,cgen,cparam}.py (their target column)
    reads/writes: example (parquet)
    venv:    any
  probe_output.py         the row train writes per example after training: the example id, its target, the
                          true tool, the score and class logits (ctool) or the generated text (cgen,
                          cparam); write, read; carries VERSION
    imports: data/__init__.py; [polars]
    used by: train/utils/trainer.py (write), eval/utils/probe_eval.py (read)
    reads/writes: prediction (parquet)
    venv:    any
  probe_input.py          what the probe is asked and shown: the cut positions in the reasoning (the
                          offline enumeration and the streaming one, which differ in their offset
                          convention and are therefore not comparable, contracts 1.7; the event-level
                          min_think gate lives in data/build_training_dataset.py offline and in agent/inject.py
                          live, which scores no cut until the thinking reaches min_think), and the text
                          assembled for the probe (the task, the clipped tool history, the thinking so
                          far). example.cut and spec.cut are not the same coordinate (contracts 1.7).
                          Pure functions whose every parameter is passed in, never a module constant and
                          never read from a file, so the offline and the live caller cannot drift;
                          carries VERSION
    imports: none (repo); [re]
    used by: data/build_training_dataset.py, agent/inject.py
    reads:   -   writes: -   venv: any
```

## Ticket 03 — the registry and the ledger

```
jobs/registry.py — the registry: runs.jsonl rows under a lock, meta.json, the
heartbeat, the verdicts, ls/where/find/kill/free, RESULTS.md.
  imports: none (repo); [PyYAML]
  used by: run.py, jobs/launch.py, agent/loop.py, data/build_training_dataset.py,
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

## Ticket 04 — the setting schema and its loader

```
experimental_settings/schema.py — the setting schema: the dataclasses, the
stage table, and the loader that reads a YAML file against them (file ->
setting, diff, key).
  imports: none (repo); [PyYAML, ast, dataclasses, hashlib, itertools, json, pathlib, typing]
  used by: run.py, jobs/launch.py, agent/loop.py, data/build_training_dataset.py,
           train/utils/trainer.py, eval/utils/probe_eval.py, eval/score_run.py,
           eval/method_table.py, models/agent_models/service.py,
           models/probe_models/service.py  (ten; both services take
           load_frozen only)
  reads:   experimental_settings/*.yaml, models/table.yaml,
           constants/path_outputs.yaml, constants/path_datasets.yaml (the
           splits block of the chosen environment), a run directory's
           settings.yaml, and the VERSION / PROBE_KIND lines and
           module-level literals of contracts 3.3's literal rule -- all as
           source text, never by importing
  writes:  settings.yaml and settings_diff.yaml in a run directory
  venv:    any
```

`load`, `load_frozen`, `freeze`, `key`, `run_dir`, `run_dir_of`, `upstream`,
`module_version`, `module_literal`, `fields_of`, `models_of`, `upstream_of`
and `versions_of` are the names the file offers (contracts 5.1, 3.1, 3.3).
`fields_of`, `models_of`, `upstream_of`, `versions_of`, `module_version` and
`module_literal` are called only by this file and by `run.py`.

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
                 requested_pairs), agent/inject.py, data/build_training_dataset.py (open_env, requested_pairs),
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

## Ticket 06 — the model table, the entrance, the gpt-oss family and the probe object

```
  models/                 the models: the table, the agent-model side, the probe-model side. A model's own
                          settings (format, serving, tokenizer quirks) live here; a run's settings live in
                          experimental_settings/
    __init__.py             the entrance: agent(alias) reads table.yaml and imports the family module inside
                            the function, returning it as AgentModel.module beside the row's alias, role,
                            family, weights (the alias) and weights_path (from constants/path_models.yaml)
                            and its serving block; probe(alias) returns the same shape as ProbeModel, minus
                            the module, without importing the backbone module —
                            models/probe_models/base.py imports that, by name, inside load(). The two return
                            types are in Part 6.2. Edited never; a new model is a row, a new family or
                            backbone a file
      imports: none (repo); [importlib, PyYAML]
      used by: agent/generate.py, agent/inject.py, models/agent_models/service.py,
               models/probe_models/base.py, models/probe_models/service.py, train/utils/trainer.py
               (six; agent/loop.py is not among them, 7.2)
      reads:   models/table.yaml, constants/path_models.yaml
      writes:  -   venv: any
    table.yaml              one row per alias, in two blocks: result (expanded into the setting before
                            keying) and serving (never keyed). Edited when a new model alias is wanted; a
                            model of an existing family or backbone needs only this row
      read by: models/__init__.py, experimental_settings/schema.py (the result block),
               models/agent_models/service.py (the serving block),
               jobs/launch.py (the serving block: host and port)
    agent_models/           one file per family (a family shares one conversation format), plus its service
      __init__.py           empty, so the client half of service.py imports without the family's libraries
        imports: none
        used by: models/agent_models/service.py, models/agent_models/gptoss.py (as their package)
        reads:   -   writes: -   venv: any
      gptoss.py             gpt-oss's format ("harmony"): messages -> token ids, parse a streamed reply, end
                            of turn, the model's own system message (date, effort), the control-token
                            wrapping of a prefetch message, and the family's own generation defaults; the
                            module interface is Part 6.2; carries VERSION
        imports: none (repo); [openai_harmony, inside render_ids()]
        used by: models/__init__.py (by name). Every other file reaches this module as the object
                 models/__init__.py's agent(alias) returns, and names no family file
        reads:   -   writes: -
        venv:    any at import and for parse/end_of_turn/wrap_prefetch; probe or vllm for render_ids()
    probe_models/           the probe model: the shared class, one file per backbone, plus its service
      __init__.py           empty, so the client half of service.py imports without torch
        imports: none
        used by: models/probe_models/base.py, models/probe_models/service.py,
                 models/probe_models/qwen.py (as their package)
        reads:   -   writes: -   venv: any
      base.py               the probe class every backbone shares: load, save, score a prefix, generate a
                            call; owns the classification head and the checkpoint layout; carries VERSION
        imports: models/__init__.py; models/probe_models/<backbone>.py (by name, inside load());
                 [torch, transformers, peft]
        used by: train/utils/trainer.py, train/methods/{ctool,cgen,cparam}.py,
                 models/probe_models/service.py (inside serve())
        reads/writes: the checkpoint layout (Part 1.6), including the class order in best/meta.json
                 (Part 1.3); it writes no run-level file and imports neither schema nor registry
        venv:    probe
      qwen.py                Qwen's tokenizer quirks, pad token, head attach point, LoRA target modules,
                            dtype; the module interface is Part 6.2; carries VERSION
        imports: none (repo); [transformers]
        used by: models/probe_models/base.py (by name)
        reads:   -   writes: -   venv: probe
```

`models/agent_models/service.py` and `models/probe_models/service.py` are ticket
07's, not this ticket's; the two group lines above (`agent_models/`,
`probe_models/`) already say "plus its service" because they describe the whole
group, but no `service.py` line is added here.

## How to run (ticket 06's own piece)

`models/__init__.py` is a library with no `__main__`. Run the acceptance
commands of `.scratch/from-zero/issues/06-model-table-entrance-and-probe-object.md`
(A1 through A12, A16) from the repo root, with the interpreter each one names.

## Ticket 07 — the two model services

The two `service.py` lines `agent_models/` and `probe_models/` (Ticket 06)
already point at, filled in:

```
    agent_models/
      service.py            both ends of the served agent model: start or attach to the vLLM server for a
                            table row and check it (main, vllm venv); the loop's client, a raw token
                            stream with a seed (standard library); carries VERSION, which is folded into
                            the sample and inject keys for the reason 2.2 gives
        imports: models/__init__.py (the family through agent(alias), inside the server main),
                 experimental_settings/schema.py (load_frozen)
        used by: agent/generate.py (client), agent/loop.py (health); jobs/launch.py starts it as a
                 piece, which is a tmux command and not an import
        reads:   models/table.yaml (the serving block only), constants/path_models.yaml, the run
                 directory's settings.yaml (models.agent_row — every keyed column — plus
                 generation.date and generation.effort)
        writes:  service_agent_<replica>.json and its piece log in the run directory
        venv:    any at import; vllm to serve
    probe_models/
      service.py            both ends of the probe service: the HTTP server that loads the probe and
                            answers score, generate, encode, decode and render, plus the check
                            subcommand, a client against a running service that loads no checkpoint
                            (main, probe venv); the loop's client (standard library); carries VERSION,
                            which is folded into the sample and inject keys for the reason 2.2 gives
        imports: models/__init__.py; experimental_settings/schema.py (load_frozen, for the check
                 client's expected values); models/probe_models/base.py inside serve();
                 [http.server, transformers and torch inside serve()]
        used by: agent/loop.py (client: render), agent/inject.py (client: score, generate, encode,
                 decode); jobs/launch.py starts it as a piece, which is a tmux command and not an import
        reads:   the checkpoint directories named on its command line, including each one's
                 best/meta.json; the run directory's settings.yaml, the check client only
        writes:  service_probe_0.json and its piece log in the run directory
        venv:    any at import; probe to serve
```

### How to run (ticket 07's own piece)

Neither file has a library-only entrance; both are run with
`python -m models.agent_models.service` / `python -m models.probe_models.service`.
Run the acceptance commands of
`.scratch/from-zero/issues/07-model-services.md` (A1, A13 through A16) from the
repo root, with the interpreter each one names.
