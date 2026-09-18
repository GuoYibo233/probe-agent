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
    used by: agent/run_tasks.py (meta, gen, env, final), agent/step_with_probe.py (spec, resume),
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
                          min_think gate lives in data/build_training_dataset.py offline and in agent/step_with_probe.py
                          live, which scores no cut until the thinking reaches min_think), and the text
                          assembled for the probe (the task, the clipped tool history, the thinking so
                          far). example.cut and spec.cut are not the same coordinate (contracts 1.7).
                          Pure functions whose every parameter is passed in, never a module constant and
                          never read from a file, so the offline and the live caller cannot drift;
                          carries VERSION
    imports: none (repo); [re]
    used by: data/build_training_dataset.py, agent/step_with_probe.py
    reads:   -   writes: -   venv: any
```

## Ticket 03 — the registry and the ledger

```
jobs/registry.py — the registry: runs.jsonl rows under a lock, meta.json, the
heartbeat, the verdicts, ls/where/find/kill/free, RESULTS.md.
  imports: none (repo); [PyYAML]
  used by: run.py, jobs/launch.py, agent/run_tasks.py, data/build_training_dataset.py,
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
  used by: run.py, jobs/launch.py, agent/run_tasks.py, data/build_training_dataset.py,
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
`module_version`, `module_literal`, `version_history`, `effective_version`,
`fields_of`, `models_of`, `upstream_of` and `versions_of` are the names the
file offers (contracts 5.1, 3.1, 3.3; `version_history` and
`effective_version` come from the errata entry "3.3 / 8.6").
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
        used by: data/environments/appworld.py (subclass), agent/run_tasks.py (open_env, StepObservation,
                 requested_pairs), agent/step_with_probe.py, data/build_training_dataset.py (open_env, requested_pairs),
                 train/methods/cgen.py, train/methods/cparam.py (open_env, for the environment their
                 validation metric's match takes, 2.6), eval/utils/probe_eval.py,
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
      used by: agent/step_without_probe.py, agent/step_with_probe.py, models/agent_models/service.py,
               models/probe_models/base.py, models/probe_models/service.py, train/utils/trainer.py
               (six; agent/run_tasks.py is not among them, 7.2)
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
        used by: agent/step_without_probe.py (client), agent/run_tasks.py (health); jobs/launch.py starts it as a
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
        used by: agent/run_tasks.py (client: render), agent/step_with_probe.py (client: score, generate, encode,
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

## Ticket 08 — the eval library and the classifier metric

```
  eval/                   reads what is on disk and computes numbers; no GPU, no torch, every file imports
                          as any. A new probe method is a key in probe_eval.py's PROBE_KIND and
                          MATCH_VERSION tables plus a match_<m> function there; a new metric is an edit
                          to the file that reports it
    utils/
      probe_eval.py         the eval program of every probe method: the PROBE_KIND and MATCH_VERSION
                            tables, the three match functions, the classifier and the generator report,
                            and the driver that reads a train run's prediction rows and writes the probe
                            report; carries VERSION
        imports: experimental_settings/schema.py, data/probe_output.py,
                 data/environments/__init__.py (open_env, for the environment the generator report
                 normalises both sides through, 2.6), jobs/registry.py; [polars, numpy]
        used by: train/methods/{ctool,cgen,cparam}.py (match_<method>, for their validation metric),
                 run.py (read_report, to freeze a temperature), eval/method_table.py
        reads:   prediction (parquet), its own and the referenced eval run's train meta.json
                 (stage_extra.labels, upstream["build"] — the second is what the 2.5 gate compares), probe
                 report (json + parquet)
        writes:  probe report (probe_report.json + fires.parquet), report.md, consumed.json (the
                 prediction parquet and any referenced report it read), heartbeat, done.json
        venv:    any
```

Ticket 10's two generator metrics land in this same file.

## Ticket 09 — the dataset builder

```
data/build_training_dataset.py — the program: records -> example rows for the three probe methods; the
train/val/test split, by either rule of build.split_source (contracts 5.2 for the hash share, 2.5 for
the env mapping); the report; the gates; carries VERSION
  imports: experimental_settings/schema.py, data/__init__.py (the id functions), data/trajectory_record.py,
           data/training_data.py, data/probe_input.py, data/environments/__init__.py, jobs/registry.py;
           [polars, PyYAML]
  used by: none (program)
  reads:   the sample run's task records, constants/path_datasets.yaml (the splits block of cfg.data.env,
           for the split files' paths), the environment's split task-id files
  writes:  examples.parquet, consumed.json, report.md, heartbeat, done.json
  venv:    any
```

## How to run (ticket 09's own piece)

```
<the any interpreter of 6.3> -m data.build_training_dataset --run-dir <a build stage's own run directory>
```

No setting name on the command line; the program calls `experimental_settings.schema.load_frozen(run_dir)`
itself (contracts 2.6).

## Ticket 10 — the generator metrics, the run scorer and the matrix table

```
    score_run.py            a sample or inject run from its records: success rates and probe agreement
                            rates, paired against a baseline; carries VERSION
      imports: experimental_settings/schema.py, data/trajectory_record.py, data/environments/__init__.py
               (open_env for split_args and build_call, and requested_pairs, 2.3),
               jobs/registry.py; [polars]
      used by: none (program)
      reads:   the task records of this run and of its baseline; the environment's split task-id files
               (through data/environments/requested_pairs, for the pair list both record gates of 2.5
               are stated over); the scored run's and the baseline run's settings.yaml (the same-setup
               gate of 2.5)
      writes:  run_report.json, report.md, heartbeat, done.json
      venv:    any
    method_table.py         the backbone x method table from the registry; one group per (setting, debug
                            flag) pair (a sweep child's own name, never its parent, and a debug run never
                            grouped with a non-debug run of the same setting), reports mean and spread; an
                            optional debug switch shows debug rows
      offers:  table(workflow: str | None = None, out: Path | None = None, *, debug: bool = False) -> str (8.6)
      imports: experimental_settings/schema.py, jobs/registry.py, eval/utils/probe_eval.py (read_report)
      used by: run.py (the table subcommand, 8.6; this file is not a stage and has no __main__)
      reads:   jobs/runs.jsonl, the probe reports the rows point at, an eval run's own meta.json and its
               train run's meta.json (for backbone)
      writes:  a markdown table on stdout or into a named file
      venv:    any
```

Decisions made where the ticket did not fix a detail (see the T10 report for the
full account, and the owner rulings round 1 for the current state): `method_table.table`'s
`backbone` column is read off the train run directory the eval row's own `meta.json`
`upstream["train"]` names, located with `schema.run_dir_of("train", ..., debug=<the eval
row's own debug flag>)` rather than through the registry listing (an eval's train
reference may point at a directory the registry never recorded); it prints `?` when
either the eval row's `meta.json` or the train directory's `meta.json` is missing.
`table` groups by `(row["setting"], row["flags"]["debug"])`, never by `row["parent"]`:
a sweep's children are parallel settings and are never merged into one row. `table`'s
`debug` keyword switch (default `False`) is passed straight to `registry.ls`, which
drops its own debug filter rather than selecting debug rows, so a `debug=True` call
returns a debug walk's rows alongside any non-debug run of the same setting; keying
each group on the row's own debug flag as well as its setting name keeps those two
runs apart instead of averaging one real run and one debug run of the same setting
into a single cell. A group's `n` column and every rate column render `mean ± spread`
the same way, the bare value when the group holds one run, and `-` when the group
holds no report at all.

## Ticket 11 — the agent loop: formats, generation, injection, the task walk

```
  agent/                  the loop that runs the agent model on tasks. Nothing is added here; a new way to
                          inject is an entry in injected_text_formats.py, a new injection mechanism is an edit to
                          step_with_probe.py, and run_tasks.py and step_without_probe.py change for neither
    run_tasks.py                 run each task and seed: open, step, parse, act, until the environment reports the
                            task completed or max_steps is reached; claim tasks across pieces; write the
                            record. Picks the generation step by the setting: the inject section present ->
                            step_with_probe.step, absent -> step_without_probe.step; passes agent/step_with_probe.py's
                            system_text(cfg) into to_messages as extra_developer on every call (7.3, 1.1);
                            holds no probe code itself; carries VERSION
      imports: experimental_settings/schema.py (load_frozen), data/environments/__init__.py,
               data/trajectory_record.py, models/agent_models/service.py (client),
               models/probe_models/service.py (client, for render), agent/step_without_probe.py, agent/step_with_probe.py,
               jobs/registry.py. It names no family module and imports models/__init__.py nowhere: it
               renders through the probe service and compares the family the service echoes against
               cfg.models.agent_row["family"] (7.2)
      used by: none (program)
      reads:   its run directory's settings.yaml, the environment's split task-id files (through
               data/environments/requested_pairs, whose triples carry the split each task came from,
               2.3), and the
               service_agent_<replica>.json / service_probe_0.json endpoint files in its own run
               directory, whose names it computes from its own --piece index and settings.yaml's
               replicas (Part 7.4)
      writes:  task records (jsonl), heartbeat
      venv:    the environment's (appworld today)
    step_without_probe.py             the plain generation step: stream tokens from the agent model to end of turn;
                            exposes the token stream so inject.py iterates it instead of copying it. The
                            baseline path; carries VERSION
      imports: models/agent_models/service.py (client), models/__init__.py (the family module).
               The `probe` field of the `clients` dataclass this file declares is annotated `object`,
               not the probe client class, so this file imports models/probe_models/service.py
               nowhere (7.3)
      used by: agent/run_tasks.py, agent/step_with_probe.py
      reads:   -   writes: -   venv: the environment's
    step_with_probe.py               the generation step with the probe: iterate generate's token stream, score at
                            each cut, on fire get the call, run it early through the environment, write the
                            result in (injected_text_formats), start a new request from the spliced prefix, roll
                            back on mismatch. Replaces generate.step when the setting has an inject section;
                            offers system_text(cfg), the one place a format's system text reaches the
                            conversation (7.3);
                            declares the module-level literal ARMS, which is what schema's inject.arm
                            axis is checked against (5.3); carries VERSION
      imports: agent/step_without_probe.py, agent/injected_text_formats.py, data/probe_input.py, data/trajectory_record.py,
               data/environments/__init__.py (type only; the object is passed in),
               models/probe_models/service.py (client), models/__init__.py (the family module).
               The setting is passed in by loop.py, so this file does not import schema
      used by: agent/run_tasks.py
      reads:   -   writes: spec and resume rows, through data/trajectory_record.py
      venv:    the environment's
    injected_text_formats.py        the table of the five ways an early result is written into the stream, as the
                            module-level literal FORMATS whose entries have the four fields of Part 7.3;
                            schema's inject.format axis is checked against its keys, so a sixth way is one
                            entry here and one schema value; carries VERSION
      imports: none
      used by: agent/step_with_probe.py; its keys are cross-checked against schema.py's axis by run.py selfcheck
      reads:   -   writes: -   venv: any
```

## Ticket 12 — the launcher

```
jobs/launch.py — launches and refires the tmux pieces of a sample, inject or train run: the dirty-tree
gate, the launch gate, card placement, port assignment, the piece and service commands, and teardown.
  imports: experimental_settings/schema.py, jobs/registry.py, data/trajectory_record.py (release),
           data/environments/__init__.py (tasks and requested_pairs); [PyYAML]
  used by: run.py
  reads:   constants/path_datasets.yaml (the venv per environment and the venvs map),
           constants/path_outputs.yaml (the login_host and the hosts list), models/table.yaml (the
           serving block), the run directory's settings.yaml and meta.json, other live runs'
           service_<kind>_<replica>.json, nvidia-smi (through jobs/registry.py), tmux, git
  writes:  the start row in jobs/runs.jsonl, meta.json launch entries, meta.json's split_files,
           dirty.patch, the piece commands
  venv:    probe
```

A library with no entry-point guard: `run.py` is the one command that calls it.

## Ticket 13 — the training loop and the three probe methods

```
  train/                  train a probe. A training hyperparameter is a YAML line; a new training practice
                          is a schema.py value plus an edit to trainer.py; a new probe method is a file
                          under methods/ plus a schema.py value
    utils/
      trainer.py            the training loop every method shares: settings -> arguments, seed, backbone,
                            tuning (full or LoRA), checkpoints, metrics, heartbeat, resume, the alignment
                            gate; and its last step, the probe run over the prediction splits with one
                            prediction row per example written to disk (the probe is still on the card). A
                            directory with the checkpoint and no predictions is continued from that step;
                            carries VERSION
        imports: experimental_settings/schema.py, models/__init__.py, models/probe_models/base.py,
                 data/training_data.py, data/probe_output.py, jobs/registry.py; [torch]
        used by: train/methods/{ctool,cgen,cparam}.py
        reads:   example (parquet), the checkpoint layout
        writes:  best/, last/, train_log.jsonl, align_check.json, train_done.json, predictions.parquet,
                 consumed.json (the example parquet it read), heartbeat, done.json (whose stage_extra
                 carries the class order, copied out of best/meta.json)
        venv:    probe
    methods/                one file per probe method, each complete on its own: its batches or packing, its
                            target, its loss, its validation metric; the files do not import each other, so
                            a fix in one is repeated in the other and the alignment test, run per method,
                            catches the one that was missed
      ctool.py              the classification probe: its batches, its head use, its loss, its validation
                            accuracy; carries VERSION
        imports: train/utils/trainer.py, models/probe_models/base.py, data/training_data.py,
                 eval/utils/probe_eval.py (match_ctool, for its validation metric); [torch]
        used by: none (program)
        reads:   -   writes: - (everything goes through trainer.py)
        venv:    probe
      cgen.py               the call-generating probe: its packing, its instance strings and target, its loss
                            positions, its exact-match validation; carries VERSION
        imports: train/utils/trainer.py, models/probe_models/base.py, data/training_data.py,
                 eval/utils/probe_eval.py (match_cgen, for its validation metric),
                 data/environments/__init__.py (open_env, for the environment that match takes, 2.6); [torch]
        used by: none (program)
        reads:   -   writes: - (everything goes through trainer.py)
        venv:    probe
      cparam.py             the argument-generating probe: its own packing and strings, the arguments as the
                            target; carries VERSION
        imports: train/utils/trainer.py, models/probe_models/base.py, data/training_data.py,
                 eval/utils/probe_eval.py (match_cparam, for its validation metric),
                 data/environments/__init__.py (open_env, for the environment that match takes, 2.6); [torch]
        used by: none (program)
        reads:   -   writes: - (everything goes through trainer.py)
        venv:    probe
  tests/test_packed_loss.py    the packed loss equals a row-by-row loss kept in its plainest form, one test
                          per probe method, on a tiny CPU model built from the Qwen3-0.6B-Base config;
                          venv: probe
```

`eval/utils/probe_eval.py`'s own `PROBE_KIND` and `MATCH_VERSION` tables (Ticket 08's line, folded per
gyb's 2026-09-18 eval-fold ruling) are what the three method files' own `PROBE_KIND` literal is checked
against, and what a train run's key folds in place of a per-method eval file's `VERSION`.

`train.warmup_ratio` defaults to `0.0` in `experimental_settings/schema.py`, while the previous
pipeline hardcoded `int(steps * 0.05)`; a setting that wants that schedule writes `warmup_ratio: 0.05`.

`train/methods/<m>.py`'s `batches(df, tok, cfg)` takes no epoch: one call is one pass over `df`, and
`trainer.py`'s step loop calls it fresh once per epoch, so the per-epoch shuffle variation lives in which
epoch calls it rather than in an argument the hook reads.
