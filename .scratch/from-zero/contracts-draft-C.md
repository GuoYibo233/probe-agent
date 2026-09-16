# new1 from zero: the contracts (draft C)

Draft C, 2026-09-17. Written against the fixed tree in
`notes/plans/2026-09-14-structure-from-zero.md` Part 1 (fourth draft), the
thirteen fixes in `notes/plans/2026-09-17-structure-review-synthesis.md`, the
third draft's deleted Part 2 (commit `771a6e5`), and the legacy code under
`legacy/`.

The tree is fixed. No entry below is added, removed, moved, split or renamed.
Every mechanism this document defines lands in a file the tree already names.
Where a reviewer's fix needed a new file, a split or a move, it is not applied;
it is listed in Part 9(b) with one line of reasoning.

The standpoint of this draft is reproducibility. Each interface below is shaped
so that the nine lifecycle scenarios (first run, rerun unchanged, partial train,
dead piece, edit one value, sweep, inject referencing a probe, debug, two
sessions at once) have exactly one mechanism, inside these files. Part 9(c)
walks all nine.

Vocabulary follows `notes/CONTEXT.md`: probe, cut, fire, inject, launch,
heartbeat, piece, refire, verdict. Two words are pinned here because the
reviews found them overloaded: **row** means a line in `jobs/runs.jsonl`
(never a task record), and **verdict** means the health conclusion for a piece
(never an environment's judgement of a task, which this document calls the
**outcome**).

---

## Part 0. The tree, annotated

Each code file carries five annotations. `imports:` the repo files it imports.
`used by:` the repo files that import it. `reads:` / `writes:` the disk formats
or files. `venv:` one of `any` (importable and runnable in all three venvs),
`appworld` (the benchmark environment's venv, Python 3.12), `probe` (torch,
transformers, peft, openai_harmony, Python 3.11), `vllm` (Python 3.12).

These five lines are the contract. They are also the README's per-file block,
and `run.py selfcheck` checks them against the real import graph, so they
cannot rot.

`venv: any` on a file that has a heavy half means: the module imports under all
three venvs, and the heavy import sits inside the function that needs it. The
function's own venv is stated in the annotation.

```
new1/
  README.md               for the future reader: this tree, one line per file, how to run, the extension recipes.
                          Edited whenever the tree changes; selfcheck fails on a Python file missing from it
                          holds the five annotation lines of every code file; selfcheck's source of truth
  CLAUDE.md               the rules an agent reads on its own; the only other file at the root that is not code
  run.py                  the one command: run one or several named settings of one workflow file; ls, where, find, free,
                          kill, sync, selfcheck. Edited when a subcommand is added or the stage walk changes. Nothing
                          else is added at the root; the outputs root is named in constants/path_outputs.yaml only and
                          printed by run.py where
                          imports: experimental_settings/schema.py, jobs/registry.py, jobs/launch.py
                          used by: nothing (entry point)
                          reads: experimental_settings/*.yaml (through schema.py), constants/path_outputs.yaml,
                                 every run directory's meta.json / done.json / heartbeat.*.jsonl, jobs/runs.jsonl
                          writes: jobs/runs.jsonl (start and finish rows), jobs/RESULTS.md, a run directory's
                                 settings.yaml and meta.json at launch, done.json for piece stages
                          venv: any; started as external/probe-env/bin/python run.py ...

  constants/              where things are on this cluster: datasets, outputs, weights. Set once, correct; read by
                          code, nothing here changes a result or enters a key. Edited when something arrives or
                          moves on disk; a path may change only for the same bytes at a new place, a new set of
                          weights is a new alias in models/table.yaml
    path_datasets.yaml      where each environment, its task splits and each dataset live on this cluster
                            read by: data/environments/<name>.py (home, split files), jobs/launch.py (the venv column)
                            never keyed
    path_outputs.yaml       where outputs go on NFS
                            read by: experimental_settings/schema.py (run_dir), run.py, jobs/launch.py, jobs/registry.py
                            never keyed
    path_models.yaml        where each model's weights live
                            read by: models/__init__.py, models/agent_models/service.py, models/probe_models/base.py
                            never keyed

  experimental_settings/  everything in here changes a result. The YAML files are gyb's: a new kind of experiment
                          (a new stage combination) is a new file; a new experiment is a new named setting in a
                          file; a tuning is an edited value (the name then points at a new key, the old directory
                          stays). Agents read the YAML files and never edit them (a hook refuses); an agent proposes
                          a setting as a task instead. schema.py is code and is edited for a new hyperparameter
                          (with a default that reproduces the old behavior) or a new value on an axis
    schema.py               the schema of a setting: every field with its default and a one-line comment, the allowed
                            values of each axis, the stage table; and the loader that reads a YAML file against it
                            (file -> setting, diff, key). Edited before the YAML that needs the new field or value
                            also holds: STAGES (the stage table), key(), run_dir(), reference resolution, sweep
                            expansion, the debug overlay, freeze()/load_frozen() for a run directory's settings.yaml
                            imports: nothing from the repo at module level; key() reads each versioned module's
                                     VERSION line from its source text (Part 3), never by importing it
                            used by: run.py, jobs/launch.py, jobs/registry.py, agent/loop.py, agent/inject.py,
                                     data/build_dataset.py, train/utils/trainer.py, train/methods/*.py,
                                     eval/utils/probe_eval.py, eval/methods/*.py, eval/score_run.py,
                                     eval/method_table.py, models/agent_models/service.py, models/probe_models/service.py
                            reads: experimental_settings/*.yaml, models/table.yaml, constants/path_outputs.yaml
                                   (after keying), the VERSION line of every module STAGES names
                            writes: <run dir>/settings.yaml, <run dir>/settings_diff.yaml
                            venv: any (PyYAML and dataclasses only)
    debug.yaml              only sizes: 3 tasks, 1 seed, 64 examples, 20 steps, 100 eval examples; never a model or a
                            tuning; --debug lays it over any setting
                            read by: experimental_settings/schema.py only
    baseline.yaml           workflow sample, score; named settings inside
                            read by: experimental_settings/schema.py only
    train_probe.yaml        workflow sample, build, train, eval; named settings inside
                            read by: experimental_settings/schema.py only
    inject.yaml             workflow inject, score; named settings inside
                            read by: experimental_settings/schema.py only
                            a new workflow is a new file; a new experiment is a new named setting in a file

  data/                   the benchmark environments, and every format that lives on disk between two stages: the record
                          (agent -> build), the example (build -> train), the prediction (train -> eval). One format per
                          interface, defined here and nowhere else; a fourth kind of file on disk reuses one of the
                          three unless it is a different thing. Nothing else is added here; a new environment goes
                          under environments/
    __init__.py             the conventions the three formats share: every read returns a Polars DataFrame with the
                            format's declared columns and types; the id rule; write. Records are jsonl, appended one
                            task at a time by many pieces; examples and predictions are parquet, written once in bulk.
                            Polars is a self-contained wheel and is installed in all three venvs (any). Edited never
                            imports: nothing from the repo
                            used by: data/task_record.py, data/example.py, data/prediction.py
                            reads: - | writes: -
                            venv: any (polars 1.44.2)
    environments/           one file per benchmark environment; this is the only place a new environment adds a file
      __init__.py           the contract and the entrance: class Environment declares the eight methods (tasks, open,
                            step, speculate, judge, close, plus the call syntax: split_args, build_call, complete_call)
                            with one line each and no logic; open_env(name) imports environments/<name>.py inside the
                            function, checks the eight methods are there, and returns the instance. The contract assumes
                            an environment that hands out tasks, steps, can try a call early and undo it, and judges
                            imports: nothing from the repo (importlib inside open_env)
                            used by: data/environments/appworld.py (subclass), agent/loop.py, agent/inject.py,
                                     data/build_dataset.py, eval/score_run.py (call parsing for the fire account)
                            reads: - | writes: -
                            venv: any
      appworld.py           class AppWorld(Environment): the eight methods on the AppWorld package, its task
                            instructions (the developer message), its no-code message, its call regex and Python call
                            syntax. Edited when AppWorld's interface or the instructions change; a changed instruction
                            changes results, so the file carries a VERSION that is bumped with it
                            imports: data/environments/__init__.py
                            used by: data/environments/__init__.py (through open_env, by name)
                            reads: constants/path_datasets.yaml (home, venv, split files, task lists)
                            writes: the AppWorld package's own per-task scratch under the environment home, deleted
                                    by close()
                            venv: any at import and for split_args / build_call / complete_call / tasks;
                                  appworld inside open(), step(), speculate(), judge(), close()
                            adding an environment: this file's sibling, its clone and venv under external/, its path in
                            constants/path_datasets.yaml, its name on the data.env axis in schema.py, its README line;
                            then --debug on one setting with data.env set to it
    task_record.py          the record one task run leaves: each step's prompt, reasoning, answer and observation, the
                            speculation events, the outcome, the seed, the commit; write, read, rebuild the conversation.
                            Edited when a field is added to the record
                            imports: data/__init__.py
                            used by: agent/loop.py (write), agent/inject.py (speculation and resume rows),
                                     data/build_dataset.py (read), eval/score_run.py (read)
                            reads / writes: <sample or inject run dir>/records/<task>__s<seed>.jsonl (Part 1.1)
                            venv: any
    example.py              the row build writes per probe example: the record and cut it came from, the text the probe
                            sees, the target (a label for ctool, a call for cgen, arguments for cparam); write, read. The
                            interface between build and train. Edited when a field is added to the row
                            imports: data/__init__.py
                            used by: data/build_dataset.py (write), train/utils/trainer.py (read),
                                     train/methods/*.py (read)
                            reads / writes: <build run dir>/examples.parquet (Part 1.2)
                            venv: any
    prediction.py           the row train writes per example after training: the example id, its label, the score
                            (ctool) or the generated text (cgen, cparam); write, read. The interface between train and
                            eval. Edited when a field is added to the row
                            imports: data/__init__.py
                            used by: train/utils/trainer.py (write), eval/utils/probe_eval.py (read),
                                     eval/methods/*.py (read)
                            reads / writes: <train run dir>/predictions.parquet (Part 1.3)
                            venv: any
    probe_input.py          what the probe is asked and shown: the cut positions in the reasoning, and the text assembled
                            for the probe (the task, the clipped tool history, the thinking so far); one rule offline and
                            live. Edited when the cut rule or what the probe sees changes; environment text comes through
                            the environment object
                            imports: nothing from the repo
                            used by: data/build_dataset.py (offline), agent/inject.py (live)
                            reads: - | writes: -
                            venv: any (standard library, pure functions)
    build_dataset.py        the program: records -> example rows for the three probe methods; the train/val/test split;
                            the report; the gates. Edited when how examples are made, the split or a gate changes; calls
                            are parsed through the environment object
                            imports: experimental_settings/schema.py, data/task_record.py, data/example.py,
                                     data/probe_input.py, data/environments/__init__.py
                            used by: nothing (a stage program, started by run.py)
                            reads: <sample run dir>/records/*.jsonl, the environment's task lists via
                                   constants/path_datasets.yaml
                            writes: <build run dir>/examples.parquet, consumed.json, BUILD_REPORT.md,
                                   tool_vocab.json, qa_sample.txt, done.json, heartbeat.build.jsonl
                            venv: any (entry: python -m data.build_dataset --run-dir DIR)

  
  
  models/                 the models: the table, the agent-model side, the probe-model side. A model's own settings
                          (format, serving, tokenizer quirks) live here; a run's settings live in experimental_settings/
    __init__.py             the entrance: agent(name) and probe(name) read table.yaml and import the family's or backbone's
                            file inside the function. Edited never; a new model is a row, a new family or backbone a file
                            imports: nothing at module level (importlib inside agent() and probe())
                            used by: models/agent_models/service.py, models/probe_models/base.py,
                                     models/probe_models/service.py, agent/loop.py, agent/generate.py,
                                     agent/inject.py, train/utils/trainer.py
                            reads: models/table.yaml, constants/path_models.yaml
                            writes: - | venv: any
    table.yaml              the model table, one row per alias: role (agent or probe), family or backbone, where its
                            weights are named in constants/path_models.yaml, how it is served. A row's fields are
                            expanded into the setting before keying, so an edited row is a new key. Edited when a new
                            model alias is wanted; a model of an existing family or backbone needs only this row
                            read by: models/__init__.py, experimental_settings/schema.py (expansion before keying),
                                     models/agent_models/service.py, models/probe_models/service.py
                            columns split into keyed and serving-only: Part 6
    agent_models/           the agent model: one file per family (a family shares one conversation format), its service.
                            A new family (Qwen as the agent) adds a file here
      __init__.py           empty, so the client half of service.py imports without the family's libraries
                            imports: - | used by: - | reads: - | writes: - | venv: any
      gptoss.py             gpt-oss's format ("harmony"): messages -> tokens, parse a reply, end of turn, the model's own
                            system message (date, effort). Edited when the format or that system message changes
                            imports: nothing from the repo
                            used by: agent/generate.py (parse, end of turn), agent/inject.py (think span, control
                                     tokens, head text), agent/loop.py (parse a step into reasoning and content),
                                     models/agent_models/service.py (the render-equals-server check),
                                     models/probe_models/service.py (render_ids on /render)
                            reads: - | writes: -
                            venv: any at import, and for render_text / parse_step / think_span / end_of_turn;
                                  probe or vllm inside render_ids (openai_harmony imported in the function)
      service.py            both ends of the served agent model: start or attach to the vLLM server for a table row and
                            check it (main, vllm venv); the loop's client, a raw token stream with a seed (standard
                            library). Edited when the serving flags or the client protocol change
                            imports: models/__init__.py, models/agent_models/gptoss.py,
                                     experimental_settings/schema.py, jobs/registry.py
                            used by: agent/generate.py (client), agent/loop.py (client), jobs/launch.py (starts main)
                            reads: models/table.yaml, constants/path_models.yaml
                            writes: <run dir>/service_agent.json (endpoint, pid, flags), heartbeat.agent.jsonl
                            venv: any for the client half; vllm for main (serve / attach / check)
    probe_models/           the probe model: the shared class, one file per backbone, its service. A new backbone
                            (Llama) adds a file here
      __init__.py           empty, so the client half of service.py imports without torch
                            imports: - | used by: - | reads: - | writes: - | venv: any
      base.py               the probe class every backbone shares: load, save, score a prefix, generate a call; shared
                            before its third repetition because the folder exists for the backbones to come. Edited when
                            a shared action changes
                            also owns: the checkpoint layout (best/, last/, head.pt, label_map.json, meta.json)
                            imports: models/__init__.py, models/probe_models/qwen.py (by name, through models.probe)
                            used by: train/utils/trainer.py, train/methods/ctool.py, train/methods/cgen.py,
                                     train/methods/cparam.py, models/probe_models/service.py
                            reads / writes: <train run dir>/best/, <train run dir>/last/ (Part 1.5)
                            venv: probe (torch, transformers, peft at module level)
      qwen.py               Qwen's tokenizer quirks, pad token, head attach point, LoRA target modules, dtype. Edited
                            when a Qwen-specific detail changes
                            imports: nothing from the repo
                            used by: models/probe_models/base.py (through models.probe(name))
                            reads: - | writes: - | venv: probe
      service.py            both ends of the probe service: the local HTTP server that loads the probe and answers score,
                            generate, encode, decode, with --check (main, probe venv); the loop's client (standard
                            library). Edited when the serving flags or the client protocol change
                            also answers /render (Part 7 and Part 9(a)#7): the loop's venv cannot import openai_harmony
                            imports: experimental_settings/schema.py, jobs/registry.py, models/__init__.py,
                                     models/probe_models/base.py (inside serve()),
                                     models/agent_models/gptoss.py (inside serve(), for render_ids)
                            used by: agent/inject.py (client), agent/loop.py (client, render only), jobs/launch.py
                            reads: the referenced train run's best/, the referenced eval run's PROBE_REPORT.json
                                   (theta, temperature)
                            writes: <run dir>/service_probe.json (endpoint, pid, loaded runs), heartbeat.probe.jsonl
                            venv: any for the client half; probe for main (serve / --check)
                            heavy imports in both service files sit inside the serving functions, so each file imports as any

  agent/                  the loop that runs the agent model on tasks. Nothing is added here; a new way to inject is an
                          entry in inject_format.py, a new injection mechanism is an edit to inject.py, and loop.py and
                          generate.py change for neither
    loop.py                 run each task and seed: open, step, parse, act, until done; claim tasks across pieces; write
                            the record. Picks the generation step by the setting: the inject section present ->
                            inject.step, absent -> generate.step; holds no probe code itself. Edited when task sharding,
                            claiming or what counts as done changes
                            imports: experimental_settings/schema.py, data/environments/__init__.py,
                                     data/task_record.py, models/__init__.py, models/agent_models/gptoss.py,
                                     models/agent_models/service.py (client), models/probe_models/service.py (client,
                                     for /render), agent/generate.py, agent/inject.py, jobs/registry.py
                            used by: nothing (a stage program, started by jobs/launch.py)
                            reads: <run dir>/settings.yaml, the environment's split files
                            writes: <run dir>/records/*.jsonl, heartbeat.loop<i>.jsonl, log.loop<i>.txt
                            venv: appworld (the environment's venv, from constants/path_datasets.yaml)
                            entry: <env venv>/bin/python -m agent.loop --run-dir DIR --piece i/n
    generate.py             the plain generation step: stream tokens from the agent model to end of turn; exposes the
                            token stream so inject.py iterates it instead of copying it. The baseline path. Edited when
                            the stop condition or the stream interface changes
                            imports: models/agent_models/service.py (client), models/agent_models/gptoss.py
                            used by: agent/loop.py, agent/inject.py
                            reads: - | writes: - (returns rows for loop.py to write)
                            venv: any at import; runs under the environment's venv
    inject.py               the generation step with the probe: iterate generate's token stream, score at each cut, on
                            fire get the call, run it early through the environment, write the result in
                            (inject_format), start a new request from the spliced prefix, roll back on mismatch. Replaces
                            generate.step when the setting has an inject section. Edited when the mechanism changes
                            imports: agent/generate.py, agent/inject_format.py, data/probe_input.py,
                                     models/probe_models/service.py (client), models/agent_models/gptoss.py,
                                     experimental_settings/schema.py
                            used by: agent/loop.py
                            reads: - | writes: - (returns spec and resume rows for loop.py to write)
                            venv: any at import; runs under the environment's venv
    inject_format.py        the table of the five ways an early result is written into the stream; schema's
                            inject.format axis reads its keys, so a sixth way is one entry here and a YAML line, nothing
                            else
                            imports: nothing from the repo
                            used by: agent/inject.py; experimental_settings/schema.py reads its FORMATS keys by
                                     source text, not by import (Part 3)
                            reads: - | writes: - | venv: any (standard library)

  train/                  train a probe. A training hyperparameter is a YAML line; a new training practice (a tuning, an
                          optimizer) is a schema.py value plus an edit to trainer.py; a new probe method is a file under
                          methods/ plus a schema.py value
    utils/
      trainer.py            the training loop every method shares: settings -> arguments, seed, backbone, tuning (full or
                            LoRA), checkpoints, metrics, heartbeat, resume, the alignment gate; and its last step, the
                            probe run over val and test with one prediction row per example written to disk (the probe is
                            still on the card). A directory with the checkpoint and no predictions is continued from
                            that step. Edited when a shared step changes
                            imports: experimental_settings/schema.py, models/__init__.py,
                                     models/probe_models/base.py, data/example.py, data/prediction.py,
                                     jobs/registry.py
                            used by: train/methods/ctool.py, train/methods/cgen.py, train/methods/cparam.py
                            reads: <build run dir>/examples.parquet, <own dir>/last/, <own dir>/train_done.json
                            writes: <own dir>/best/, last/, train_log.jsonl, ALIGN_CHECK.json, train_done.json,
                                    predictions.parquet, done.json, heartbeat.train.jsonl
                            venv: probe
    methods/                one file per probe method, each complete on its own: its batches or packing, its target, its
                            loss, its validation metric; the files do not import each other, so a fix in one is repeated
                            in the other and the alignment test, run per method, catches the one that was missed
      ctool.py              the classification probe: its batches, its head, its loss, its validation accuracy
                            imports: train/utils/trainer.py, models/probe_models/base.py,
                                     experimental_settings/schema.py, data/example.py, data/prediction.py,
                                     eval/methods/ctool.py (its match function only)
                            used by: nothing (a stage program, started by jobs/launch.py)
                            reads / writes: through trainer.py
                            venv: probe; entry: external/probe-env/bin/python -m train.methods.ctool --run-dir DIR
      cgen.py               the call-generating probe: its packing, its instance strings and target, its loss positions,
                            its exact-match validation
                            imports / used by / venv / entry: as ctool.py, with eval/methods/cgen.py
      cparam.py             the argument-generating probe: its own packing and strings, the arguments as the target
                            imports / used by / venv / entry: as ctool.py, with eval/methods/cparam.py

  eval/                   reads what is on disk and computes numbers; no GPU, no torch, every file imports as any. A new
                          probe method is a file under methods/; a new metric is an edit to the file that reports it
    utils/
      probe_eval.py         shared by the three methods: read a train run's prediction rows and labels, bootstrap the
                            confidence interval, write the report. Edited when the report or the interval method changes
                            also defines: the probe report format (write_report / read_report), and the numpy
                            temperature fit that replaces today's torch LBFGS
                            imports: experimental_settings/schema.py, data/prediction.py, jobs/registry.py
                            used by: eval/methods/ctool.py, eval/methods/cgen.py, eval/methods/cparam.py,
                                     eval/method_table.py (read_report), models/probe_models/service.py (read_report)
                            reads: <train run dir>/predictions.parquet
                            writes: <eval run dir>/PROBE_REPORT.json, PROBE_REPORT.md, done.json
                            venv: any (polars, numpy; no torch)
    methods/                one file per probe method, the metric computed from prediction rows; train/methods/<name>.py
                            calls this file's match function for its validation metric, never its own copy
      ctool.py              fit theta on the val rows at the risk targets, freeze it, report on the test rows
                            imports: eval/utils/probe_eval.py, experimental_settings/schema.py
                            used by: train/methods/ctool.py (match function), nothing else
                            reads: <train run dir>/predictions.parquet | writes: through probe_eval.py
                            venv: any; entry: python -m eval.methods.ctool --run-dir DIR
      cgen.py               exact match of the generated call at the frozen theta
                            imports: eval/utils/probe_eval.py, experimental_settings/schema.py,
                                     data/environments/__init__.py (call parsing)
                            used by: train/methods/cgen.py (match function)
                            reads: <own train run dir>/predictions.parquet, the referenced ctool setting's
                                   <train dir>/predictions.parquet and <eval dir>/PROBE_REPORT.json
                            writes: through probe_eval.py | venv: any
      cparam.py             exact match of the generated arguments at the frozen theta
                            imports / used by / reads / writes / venv: as cgen.py, with train/methods/cparam.py
    score_run.py            a sample or inject run from its records: task success, speculation outcomes, tokens and time;
                            by seed; against a baseline. Edited when a metric is added
                            imports: experimental_settings/schema.py, data/task_record.py,
                                     data/environments/__init__.py, jobs/registry.py
                            used by: nothing (a stage program, started by run.py)
                            reads: <inject or sample run dir>/records/*.jsonl, the baseline sample run's records
                            writes: <score run dir>/RUN_REPORT.json, RUN_REPORT.md, done.json
                            venv: any; entry: python -m eval.score_run --run-dir DIR
    method_table.py         the backbone x method table from the registry; groups sweep children, reports mean and spread.
                            Edited when the table's shape changes
                            imports: jobs/registry.py, experimental_settings/schema.py,
                                     eval/utils/probe_eval.py (read_report)
                            used by: nothing (started by run.py)
                            reads: jobs/runs.jsonl, each eval run's PROBE_REPORT.json
                            writes: a markdown table on stdout, or the path given
                            venv: any

  jobs/                   a job is one stage run on cards: the code that starts it and records it, and the record itself.
                          Nothing is added here; batch runs (a sweep, one method over several datasets, several seeds
                          over several models) are the sweep keyword in a setting, not a script
    launch.py               pick free cards, one tmux session per piece, the record's start, the alive check, refire.
                            Edited when card picking, the tmux start, the alive check or the refire rule changes
                            also owns: the dirty-tree gate (one function, --allow-dirty), the venv lookup per piece
                            imports: experimental_settings/schema.py, jobs/registry.py
                            used by: run.py
                            reads: constants/path_outputs.yaml, constants/path_datasets.yaml (the venv column),
                                   models/table.yaml (serving-only columns), a run directory's meta.json
                            writes: a run directory's meta.json (pieces, launches), dirty.patch, tmux sessions;
                                    the start row through registry.py
                            venv: any; runs on the login machine only
    registry.py               the registry: runs.jsonl rows under a lock, meta.json, the heartbeat, ls/where/find/kill,
                            RESULTS.md. Every stage imports it to write its start and finish rows; run.py imports it for
                            the subcommands. Both halves are standard library; the day ls or kill needs more, the
                            subcommand half becomes registry_cli.py. Edited when a row's fields, the heartbeat or a
                            subcommand's output changes
                            correction to the line: a stage process writes only its own run directory (heartbeat,
                            meta.json state, done.json); rows are appended by run.py and jobs/launch.py on the login
                            machine (Part 8, synthesis item 2 without the file split)
                            imports: nothing from the repo
                            used by: run.py, jobs/launch.py, agent/loop.py, data/build_dataset.py,
                                     train/utils/trainer.py, eval/utils/probe_eval.py, eval/score_run.py,
                                     eval/method_table.py, models/agent_models/service.py,
                                     models/probe_models/service.py
                            reads: jobs/runs.jsonl, a run directory's meta.json / done.json / heartbeat.*.jsonl;
                                   git, tmux, nvidia-smi
                            writes: jobs/runs.jsonl, jobs/RESULTS.md, meta.json, heartbeat.*.jsonl, done.json
                            venv: any (standard library only)
    runs.jsonl              one row per stage run, appended at start and at finish by registry.py; never edited by hand;
                            in git
    runs.jsonl.lock         the lock every append takes; ignored by git
    RESULTS.md              rendered from runs.jsonl by registry.py; never edited by hand
  tests/                  empty for now (gyb, 2026-09-17: tests come later). The four checks planned for it are the ones
                          where a bug gives a wrong number instead of a crash: a changed schema default without a
                          VERSION bump fails (this one enforces the version rule; until it exists the rule is kept by
                          hand); the packed loss equals a row-by-row loss kept in its plainest form, and a LoRA merge
                          equals full weights, on a tiny CPU model; a speculated call leaves the world unchanged, per
                          environment, in that environment's venv; two pieces appending to runs.jsonl at once both
                          land. Each file's header names its venv
  .claude/skills/repo-review/SKILL.md
                          the two-day review: an agent reads the tree against the six principles and writes tasks
  .claude/skills/gpu-run/references/gpu_state.md
                          cluster notes: drivers, CUDA, pitfalls; read by the gpu-run skill only, so it lives with
                          it; appended at a gpu-run wrap-up that hit a new pitfall
  .claude/hooks/settings_readonly.sh
                          the hook that refuses any agent edit to experimental_settings/*.yaml
  .scratch/review/issues/ the tasks the review writes, in the issue-tracker format already in use
  .claude/                as today

  notes/                  everything gyb writes by hand: TRAPS.md, METHOD.md, DATA.md, WORKPLAN.md, TIMELINE.md (moved
                          from the root), plans/ and docs/ (moved whole). Reviewed by gyb by hand later; untouched by
                          this plan beyond the move

  other directories, no rules beyond their one line:
  notebooks/              exploration; imports any module, is imported by none, writes no output directory and no
                          registry row
  figures/                one script per figure, moved here from a notebook when the figure is final
  external/               nothing written in this repo, nothing in git: the AppWorld clone and its venv, the probe venv,
                          the vLLM venv, the lock files; OmegaConf, PyYAML and Polars are in all three venvs.
                          "environment" in this tree means a benchmark, never a venv
```

**Python file count.** root 1 (`run.py`); `experimental_settings` 1
(`schema.py`); `data` 8 (`__init__.py`, `environments/__init__.py`,
`environments/appworld.py`, `task_record.py`, `example.py`, `prediction.py`,
`probe_input.py`, `build_dataset.py`); `models` 8 (`__init__.py`,
`agent_models/__init__.py`, `agent_models/gptoss.py`,
`agent_models/service.py`, `probe_models/__init__.py`, `probe_models/base.py`,
`probe_models/qwen.py`, `probe_models/service.py`); `agent` 4; `train` 4;
`eval` 6; `jobs` 2. Total **34**, matching the fourth draft's count. `agent/`,
`train/`, `train/utils/`, `train/methods/`, `eval/`, `eval/utils/`,
`eval/methods/`, `jobs/` and `constants/` hold no `__init__.py`; they are
namespace packages (PEP 420) and `python -m` finds them with the repo root on
`sys.path`, so the count stays 34 and no file is added.

**One correction to the tree's wording, not to its files.** `data/__init__.py`
says records are "appended one task at a time by many pieces". The record
layout in Part 1.1 is one file per (task, seed) with an exclusive-create claim
(synthesis item 9, lifecycle A5): many pieces still append one task at a time,
each to its own file. No file changes; the phrase means per-task files.

---

## Part 1. On-disk formats

Five things live on disk between stages: the task record, the example, the
prediction, the probe report, and the run directory's own files. Each has one
defining file, a version integer, an id rule, and a named writer and readers.

Common conventions, defined in `data/__init__.py` and obeyed by all three data
formats:

- Every read returns a Polars DataFrame with the format's declared columns and
  types, in the declared order. A column the file lacks is filled with the
  declared default (not with null, unless the default is null). A column the
  file has and the format does not is an error, not a silent drop.
- Every write takes a DataFrame or a list of dicts, validates against the
  declared columns, and writes the version into the file (records: in the
  `meta` row; parquet: in the file's key-value metadata under `format_version`).
- Records are jsonl, one file per task run, flushed per row. Examples and
  predictions are parquet, written once in bulk by one process.
- Text is UTF-8, `ensure_ascii=False`; floats are float64 in jsonl and float32
  in parquet unless the column says otherwise.

### 1.0 The id rule

| id | shape | example | made by |
|---|---|---|---|
| `record_id` | `<task_id>\|<seed>` | `82e2fac_1\|42` | `data/task_record.py` |
| `event_id` | `<record_id>\|s<step>` | `82e2fac_1\|42\|s3` | `data/task_record.py` |
| `example_id` | `<event_id>\|c<cut_index>` | `82e2fac_1\|42\|s3\|c7` | `data/example.py` |
| `prediction id` | the `example_id` it answers | same | `data/prediction.py` |
| `run_id` | `<stage>-<key>` | `train-9f31c0a41b2e` | `experimental_settings/schema.py` |

`cut_index` is the position of the cut in the list `probe_input.cut_points`
returns for that step's reasoning, after the `build.max_cuts` thinning, counted
from 0. The legacy field `sent_idx` is this value; `event` in legacy rows is
`event_id` with the trajectory path instead of task and seed.

An id is a string and is never parsed for meaning by a consumer; the parts are
also stored as their own columns, so a join never needs to split a string.

### 1.1 The task record — `data/task_record.py`

**Layout.** One file per task run:
`<sample or inject run dir>/records/<task_id>__s<seed>.jsonl`. The file is
created with `O_CREAT|O_EXCL` by the piece that claims the task; the create and
the first row (`kind="meta"`, carrying `session` and `host`) are the claim. One
task run is one file; one line is one row; rows are flushed as they are written,
so a killed piece leaves a file whose last line is complete and whose final row
is missing.

**Row kinds.** Six, the same six the live driver writes today
(`legacy/pipeline/inject/live_appworld.py:34-42`), with `sample` runs writing
four of them (`meta`, `gen`, `env`, `final`) and `inject` runs writing all six:

| kind | one per | written by | meaning |
|---|---|---|---|
| `meta` | file | `agent/loop.py` | the task, the arm and every setting the run was made under |
| `gen` | step | `agent/loop.py` | the whole step's generation: reasoning, answer, usage, the token ids |
| `spec` | fire | `agent/inject.py` | one fire: the cut, the score, the predicted call, its early execution, the injected text |
| `resume` | fire | `agent/inject.py` | the account of the resent continuation against the ids discarded at that fire |
| `env` | step | `agent/loop.py` | the code actually executed and what came back |
| `final` | file | `agent/loop.py` | the outcome: step count, completion, abort, the environment's evaluation |

**Columns.** The reader declares the union of all kinds; a column not belonging
to a row's kind is null. Types are Polars types.

| column | type | kinds | meaning |
|---|---|---|---|
| `kind` | Utf8 | all | one of the six above |
| `seq` | Int32 | all | 0-based write order inside the file |
| `step` | Int32 | gen, spec, resume, env | the agent turn; null on meta and final |
| `ts` | Float64 | all | the writing host's clock, seconds since epoch |
| `record_version` | Int32 | meta | `task_record.VERSION` at write time |
| `run_key` | Utf8 | meta | the key of the sample or inject run this file belongs to |
| `stage` | Utf8 | meta | `sample` or `inject` |
| `task_id` | Utf8 | meta | the environment's task id |
| `seed` | Int32 | meta | the generation seed for this run of the task |
| `env` | Utf8 | meta | `data.env` |
| `instructions` | Utf8 | meta | `data.instructions`, the instruction-variant name |
| `instruction_text` | Utf8 | meta | the task text the environment handed out |
| `agent_alias` | Utf8 | meta | `models.agent` |
| `arm` | Utf8 | meta | `sample`, `no_probe`, or `probe` |
| `format` | Utf8 | meta | the injection format name; null for a sample run |
| `theta` | Float64 | meta | the fire threshold; null for a sample run |
| `probe_score_key` | Utf8 | meta | the eval(ctool) key the probe service scored with |
| `probe_gen_key` | Utf8 | meta | the eval(cgen) key the probe service generated with |
| `gen_settings` | Struct | meta | temperature, top_p, seed, max_step_tokens, stop, effort, date |
| `env_seed` | Int32 | meta | the environment's own seed (AppWorld's `random_seed`, 100) |
| `commit` | Utf8 | meta | the git commit the piece ran at |
| `host` | Utf8 | meta | the machine |
| `session` | Utf8 | meta | the tmux session that owns this file (the claim's owner) |
| `piece` | Utf8 | meta | `i/n` |
| `reasoning` | Utf8 | gen | the analysis channel's text for the whole step |
| `content` | Utf8 | gen | the final and unaddressed-commentary channels' text |
| `gen_ids` | List[Int32] | gen | the token ids the step ended with (after any splice) |
| `prompt_tok` | Int32 | gen | prompt tokens billed across the step's requests |
| `gen_tok` | Int32 | gen | completion tokens billed, discarded overflow included |
| `n_requests` | Int32 | gen | requests this step took (1 plus one per fire) |
| `prefix_tok` | Int32 | gen | length of the rendered prefix |
| `prefix_sha` | Utf8 | gen | sha1 of the prefix id list, so two arms can be compared id for id |
| `discard_chars` | Int32 | gen | characters generated after a cut and thrown away |
| `discard_tokens` | Int32 | gen | token ids thrown away |
| `discard_events` | Int32 | gen | how many times this step discarded |
| `n_inject` | Int32 | gen | fires that injected in this step |
| `wall_s` | Float64 | gen | wall time of the step |
| `finish_reason` | Utf8 | gen, resume | the server's finish reason |
| `stop_reason` | Utf8 | gen, resume | the server's stop reason |
| `text_ids_consistent` | Boolean | gen | decode(gen_ids) still matches the text; null when nothing was injected |
| `cut` | Int32 | spec | character offset of the cut inside the step's thinking |
| `cut_index` | Int32 | spec | the cut's index among the cuts checked in this step |
| `n_checked` | Int32 | spec | cuts scored so far in this step |
| `conf` | Float64 | spec | the probe's calibrated confidence at the cut |
| `pred_label` | Utf8 | spec | the tool the score probe predicted |
| `gen_call` | Utf8 | spec | the call the generation probe wrote |
| `exec_code` | Utf8 | spec | the executable form of that call after requoting |
| `arg_modes` | List[Utf8] | spec | which requote branch each argument took |
| `exec_out` | Utf8 | spec | the early execution's output, clipped at `result_cap` |
| `exec_ok` | Boolean | spec | the early execution raised no error |
| `error_kind` | Utf8 | spec | the error class when it did |
| `note` | Utf8 | spec | the exact text spliced into the stream |
| `head_tok` | Int32 | spec | length of the model's own id prefix kept at the cut |
| `note_tok` | Int32 | spec | tokens the injected text encoded to |
| `head_chars` | Int32 | spec | characters of thinking kept |
| `head_ends_ws` | Boolean | spec | the head ended in whitespace (the seam rule) |
| `head_tail` | Utf8 | spec | the last 40 characters of the head, for eyeballing |
| `discarded_chars` | Int32 | spec | characters discarded at this fire |
| `overflow_ids` | List[Int32] | spec | the ids discarded at this fire |
| `overflow_tok` | Int32 | resume | how many ids were discarded at the fire this row settles |
| `new_tok` | Int32 | resume | how many ids the resent continuation produced |
| `match_len` | Int32 | resume | how many of them matched the discarded ids position by position |
| `identical` | Boolean | resume | the continuation reproduced the discarded ids exactly |
| `action` | Utf8 | env | the code executed; null when the model wrote no code block |
| `result` | Utf8 | env | what came back, clipped at `result_cap` |
| `steps` | Int32 | final | steps taken |
| `completed` | Boolean | final | the environment said the task was completed |
| `abort` | Utf8 | final | why the run stopped early; null on a clean end |
| `success` | Boolean | final | the environment's own success verdict, lifted out of `outcome` |
| `outcome` | Utf8 | final | the environment's evaluation, as a JSON string |

**Who writes, who reads.** `agent/loop.py` writes `meta`, `gen`, `env` and
`final`; `agent/inject.py` hands `spec` and `resume` rows back to `loop.py`,
which writes them, so there is one writer per file. `data/build_dataset.py` and
`eval/score_run.py` read.

**Done, claimed, orphaned.** `task_record.is_done(path)` is true when the file's
last row has `kind="final"` — including a final with a non-null `abort`, so a
poisonous task is not retried forever. `task_record.is_ok(path)` adds
`abort is null`. A file whose last row is not `final` is unfinished; its owner is
the `session` of its `meta` row, and `jobs/launch.py` releases (deletes) an
unfinished file whose owning session is gone before it refires that piece
(synthesis item 9).

**VERSION rule.** `task_record.VERSION` is bumped when an existing column's
meaning changes or a column is removed; then `sample` and `inject` keys change
and every existing record directory is left behind, intact, for the old key. A
column **added** with a declared default does not bump the version: the reader
fills the default, old files stay readable, and `settings.yaml` inside each
directory still says what the run was. A column added without a default is a
version bump by definition, because old files cannot be read strictly
(dependencies P9).

**Defined in:** `data/task_record.py`. **Offers:** `write_row`, `read(path)`,
`read_dir(dir)`, `is_done`, `is_ok`, `claim(dir, task_id, seed, meta)`,
`release(path)`, `to_messages(df)` (rebuild the conversation exactly as the
model saw it, used live by the loop and offline by the builder).

### 1.2 The example — `data/example.py`

**Layout.** One parquet file per build run: `<build run dir>/examples.parquet`,
written once in bulk by `data/build_dataset.py`. One row per (event, cut). The
three probe methods share one file: every row carries all three targets, so one
build serves ctool, cgen and cparam (as `legacy/pipeline/annotate/build.py`
already does with `label`, `label_call`, `args_named`).

| column | type | default | meaning |
|---|---|---|---|
| `example_id` | Utf8 | — | primary key, `<event_id>\|c<cut_index>` |
| `event_id` | Utf8 | — | the step this cut is in |
| `record_id` | Utf8 | — | the task run |
| `task_id` | Utf8 | — | the environment's task id |
| `seed` | Int32 | — | the generation seed |
| `step` | Int32 | — | the agent turn |
| `cut` | Int32 | — | character offset of the cut in the step's reasoning |
| `cut_index` | Int32 | — | the cut's index after thinning |
| `n_cuts` | Int32 | — | cuts kept for this event |
| `depth` | Float32 | — | `cut / len(reasoning)`, how far into the thinking |
| `split` | Utf8 | — | `train`, `val` or `test`, decided per task |
| `text` | Utf8 | — | what the probe sees, from `probe_input.assemble` |
| `w` | Float32 | 1.0 | the row's weight in the loss |
| `target_label` | Utf8 | — | the tool actually called at this step (ctool's target) |
| `target_call` | Utf8 | — | the canonical full call (cgen's target) |
| `target_args` | List[Struct{key:Utf8,value:Utf8}] | `[]` | the named arguments (cparam's target) |
| `env` | Utf8 | — | `data.env`, so a mixed read is impossible by accident |
| `agent_alias` | Utf8 | — | which agent model produced the record |
| `sample_key` | Utf8 | — | the sample run these rows came from |

**Who writes, who reads.** `data/build_dataset.py` writes. `train/utils/trainer.py`
reads (train and val), `train/methods/*.py` read through the trainer for their
own packing. `eval/` never reads this file; everything eval needs is copied onto
the prediction row (1.3).

**VERSION rule.** Same as 1.1: `example.VERSION` bumps on a changed or removed
column, changing the `build` key; a column added with a default does not.

**Defined in:** `data/example.py`. **Offers:** `write(df, dir)`, `read(dir)`,
`read_split(dir, split)`, `SCHEMA`, `VERSION`.

### 1.3 The prediction — `data/prediction.py`

**Layout.** One parquet file per train run:
`<train run dir>/predictions.parquet`, written once by `train/utils/trainer.py`
as the last step of training, with the probe still on the card. One row per
example in the splits `train.predict.splits` names (default `[val, test]`),
uniform across methods: **every method predicts at every cut row it is given**,
so no eval needs a cross-run reference at train time (the owner's ruling).

The row carries its own target, so `eval/` reads exactly one file and never
reaches back to the build directory.

| column | type | default | meaning |
|---|---|---|---|
| `example_id` | Utf8 | — | the example this answers |
| `event_id` | Utf8 | — | the step |
| `record_id` | Utf8 | — | the task run |
| `task_id` | Utf8 | — | for grouping the bootstrap by task |
| `seed` | Int32 | — | the generation seed |
| `step` | Int32 | — | the agent turn |
| `cut_index` | Int32 | — | position of the cut, so "the first crossing" is well defined |
| `n_cuts` | Int32 | — | cuts in the event |
| `depth` | Float32 | — | lead time is `1 - depth` |
| `w` | Float32 | 1.0 | the row's weight, carried through for weighted accuracy |
| `split` | Utf8 | — | `val` or `test` |
| `method` | Utf8 | — | `ctool`, `cgen` or `cparam` |
| `target_label` | Utf8 | — | the ground-truth tool |
| `target_call` | Utf8 | — | the ground-truth call |
| `target_args` | List[Struct{key,value}] | `[]` | the ground-truth arguments |
| `pred_label` | Utf8 | null | ctool: the argmax label |
| `logits` | List[Float32] | `[]` | ctool: the full logit vector, so a temperature fit at eval time is possible |
| `generated` | Utf8 | null | cgen, cparam: the greedy text, cut at the first newline and stripped |
| `truncated` | Boolean | false | the event's full text did not fit the window, so this row never fires |
| `prediction_version` | Int32 | — | `prediction.VERSION` at write time (also in the parquet metadata) |
| `train_key` | Utf8 | — | the train run that produced the row |
| `label_space` | List[Utf8] | — | the label order the `logits` vector is in (repeated per row; Polars dictionary-encodes it) |

The `logits` column is why ctool's eval can stay on the CPU: the softmax
temperature is fit at eval time and changes the confidence, so a scalar score
would not be enough (`legacy/pipeline/eval/eval_tool.py:213-224` fits T on the
logits matrix; today they are saved as `logits_{val,test}.pt`). Size at
today's scale: about 8,500 val plus test events by 64 cuts by 200 labels by
4 bytes, a few hundred megabytes of float32, on NFS, which is the same order as
today's `.pt` files.

**Who writes, who reads.** `train/utils/trainer.py` writes.
`eval/utils/probe_eval.py` reads; `eval/methods/*.py` read through it.
`eval/methods/cgen.py` and `cparam.py` additionally read the **referenced ctool
setting's** prediction file, for the ctool score per example that selects the
fire row (Part 2, stage `eval`).

**VERSION rule.** Same as 1.1, changing the `eval` key when bumped.

**Defined in:** `data/prediction.py`. **Offers:** `write(rows, dir)`,
`read(dir)`, `SCHEMA`, `VERSION`.

### 1.4 The probe report — `eval/utils/probe_eval.py`

**Layout.** One JSON file per eval run: `<eval run dir>/PROBE_REPORT.json`,
plus a rendered `PROBE_REPORT.md` beside it. It is the only file that crosses
from `eval/` back into a live run, so its shape is fixed here and read through
one function.

| field | type | meaning |
|---|---|---|
| `report_version` | int | `probe_eval.VERSION` |
| `stage` / `method` | str | always `eval`; `ctool`, `cgen` or `cparam` |
| `train_key` / `eval_key` | str | the runs this report is about |
| `trigger_key` | str | for cgen and cparam: the referenced ctool setting's eval key; null for ctool |
| `commit` | str | the git commit the eval ran at |
| `versions` | object | every module VERSION folded into the eval key |
| `label_space` | list[str] | the label order, copied from the prediction rows |
| `temperature` | float | the fitted softmax temperature (ctool only); the probe service reads this |
| `thetas` | list[float] | the swept grid, 0.500 to 0.975 by 0.025 |
| `val_sweep` | list[{theta, coverage, trig_acc, earliness, wrong_spec}] | the sweep on val |
| `chosen_theta` | object {risk: theta} | the frozen threshold per risk target; the probe service reads this |
| `test_frozen` | object {risk: {n, coverage, trig_acc, earliness, wrong_spec, ci}} | the frozen numbers on test with the bootstrap interval |
| `economics` | object {risk: {exp_token_saving_ratio, exp_overlap_ratio}} | the offline speculation account |
| `depth_buckets` | object | accuracy by depth decile on test |
| `prior_baseline` | float | event accuracy of always guessing the most frequent tool |
| `n_events` | object {val, test} | event counts |
| `counts` | object | truncated rows, dropped events, rows outside the window |
| `exact_match` | object | cgen and cparam only: tool_ok, params_all_ok, full_call_ok per risk |

Field names `chosen_theta`, `temperature`, `test_frozen`, `coverage`,
`trig_acc`, `earliness`, `wrong_spec`, `exp_token_saving_ratio`,
`exp_overlap_ratio` keep today's spelling
(`legacy/pipeline/eval/eval_tool.py:597-615`), so an old report can be read
with the new reader and the two can be compared without a translation table.

**Who writes, who reads.** `eval/methods/ctool.py` writes the file through
`probe_eval.write_report`; `eval/methods/cgen.py` and `cparam.py` write their
own report with `exact_match` filled and `temperature` copied from the
referenced ctool report. Readers: `eval/methods/cgen.py`, `eval/methods/cparam.py`
(theta and temperature), `models/probe_models/service.py` (theta and
temperature at serve time), `eval/method_table.py` (the table).

`models/probe_models/service.py` importing `eval/utils/probe_eval.read_report`
is an upward import, `models` reading from `eval`. It is deliberate: the tree
gives the report no home in `data/`, and one reader function beats three
hand-rolled `json.loads` with three chances to misspell a key. Part 9(b) lists
the reviewer's `data/probe_report.py` as the structural alternative, not
applied.

**VERSION rule.** `probe_eval.VERSION` bumps when a field's meaning changes or
the interval method changes; it folds into the `eval` key, so the old report
stays at the old key. Adding a field does not bump it; `read_report` fills a
missing field with its declared default and records that it did, in the
`report_version` it returns.

### 1.5 The run directory's own files

Every stage run is one directory, `run_dir(stage, setting)` (Part 3). It holds:

| file | written by | read by | meaning |
|---|---|---|---|
| `settings.yaml` | `jobs/launch.py` (piece stages) or the stage program (in-place stages), through `schema.freeze` | every piece, `run.py`, `jobs/registry.py` | the fully resolved setting, frozen at first launch. A piece is told this directory, never a setting name, so an edit to the YAML after launch cannot move a running or refired process (lifecycle A2) |
| `settings_diff.yaml` | same | `run.py ls`, `run.py find` | only what differs from the defaults: the run's human identity and the search index |
| `meta.json` | `jobs/launch.py`, then each piece for its own state block | `run.py`, `jobs/registry.py`, `jobs/launch.py` | Part 8 lists the fields |
| `heartbeat.<piece>.jsonl` | the piece | `jobs/registry.py` | one JSON object per line, Part 8 |
| `log.<piece>.txt` | tmux `tee` | a person | raw stdout and stderr |
| `dirty.patch` | `jobs/launch.py` | a person | the uncommitted diff at launch, written only when `--allow-dirty` was used |
| `done.json` | the stage program for single-process stages; `run.py` for piece stages | `run.py`, `jobs/registry.py` | the done marker, Part 2 |
| `train_done.json` | `train/utils/trainer.py` | itself, `run.py` | training finished, predictions may or may not be written (lifecycle A6) |
| `consumed.json` | `data/build_dataset.py`, `eval/score_run.py` | `run.py ls` | the exact input files consumed, with size and a short hash, so a later refire into the upstream directory is visible |
| the stage's outputs | the stage program | the next stage | `records/`, `examples.parquet`, `predictions.parquet`, `best/`, `last/`, `PROBE_REPORT.*`, `RUN_REPORT.*` |

`done.json`: `{stage, key, finished_at, by, counts, versions, commit}`. `by` is
`program` or `walk`. `counts` is per stage: sample and inject report tasks
done, ok and aborted; build reports events, examples and per-split counts;
train reports steps and prediction rows; eval and score report events scored.

`train_done.json`: `{finished_at, steps, best_step, best_metric, commit}`.

---

## Part 2. The stage table

`STAGES` lives in `experimental_settings/schema.py`, as its tree line says
("the stage table"). It is a plain dict of dataclasses, one entry per stage
name. Everything `run.py`, `jobs/launch.py` and `key()` need about a stage is
read from here and nowhere else (synthesis item 8, lifecycle A1).

Per stage the table holds: `reads` (setting sections), `upstream` (stage names
and reference fields), `program` (module and entry), `venv`, `gpu`,
`pieces` (the piece rule), `versions` (modules whose VERSION folds into the
key), `outputs`, `done` (the marker and who writes it), `continue_rule`,
`always_recompute`.

### 2.1 The table

| stage | sections read | upstream | program (entry) | venv | GPU |
|---|---|---|---|---|---|
| `sample` | `data`, `models.agent`, `generation`, `sample` | none | `agent.loop` (`main`) | the environment's, plus `vllm` and `probe` for its service pieces | yes |
| `build` | `data`, `build`, and `sample.{split, n_tasks, seeds}` | `sample` | `data.build_dataset` (`main`) | any | no |
| `train` | `models.probe`, `probe`, `train` | `build` | `train.methods.<probe.method>` (`main`) | probe | yes |
| `eval` | `probe.method`, `eval` | `train`; for cgen and cparam also the setting named by `eval.trigger_run` (its `train` and `eval` keys) | `eval.methods.<probe.method>` (`main`) | any | no |
| `inject` | `data`, `models`, `generation`, `probe`, `inject` | the settings named by `inject.probe_score` and `inject.probe_gen` (their `train` and `eval` keys) | `agent.loop` (`main`) | the environment's, plus `vllm` and `probe` | yes |
| `score` | `score`, and the `inject` or `sample` section's `{split, n_tasks, seeds}` | `inject` or `sample` in the same workflow, plus the setting named by `score.baseline` (its `sample` key) | `eval.score_run` (`main`) | any | no |

No stage is added. The agent service and the probe service are **pieces** of
`sample` and `inject`, not stages: they hold cards, they get a row's piece
entry with `kind: service` and a port, and they are torn down with the stage
(lifecycle B8).

### 2.2 Pieces, claiming and done

| stage | pieces | how a piece claims work | done |
|---|---|---|---|
| `sample` | `sample.pieces` loop pieces (the environment's venv), `sample.replicas` agent-service pieces (vllm), 1 probe-service piece in render-only mode (probe, no card) | a loop piece walks the requested (task, seed) list rotated by its own index and takes the first one whose record file it can create with `O_CREAT\|O_EXCL`; the create writes the `meta` row with the piece's session | every requested (task, seed) has a record file whose last row is `final`; `run.py` checks this on its walk and writes `done.json` |
| `build` | 1 in-place process | none | the program writes `done.json` as its last action |
| `train` | 1 piece on 1 card (no sharding: the trainer packs by event and its state is one optimizer) | none | the program writes `train_done.json` after the last step and `done.json` after the prediction rows |
| `eval` | 1 in-place process | none | the program writes `done.json`; `always_recompute` is true, so a present `done.json` never skips the run |
| `inject` | `inject.pieces` loop pieces, `inject.replicas` agent-service pieces, 1 probe-service piece with both probes loaded (probe, 1 card) | same exclusive-create claim as `sample` | same as `sample` |
| `score` | 1 in-place process | none | the program writes `done.json`; `always_recompute` is true |

Two rules make this work across hosts. First, the claim is an exclusive create
on NFS, which is atomic there (today's live driver already claims with an
atomic `mkdir`, `legacy/pipeline/inject/live_appworld.py:590-603`). Second, no
piece ever writes another piece's file, and no piece writes `jobs/runs.jsonl`
(Part 8), so nothing needs a cross-host lock.

**The finish row has one owner.** A piece cannot know it is the last, so it
does not try: `run.py` (and `run.py sync`, and `run.py ls`) on the login
machine folds a directory's state, writes `done.json` when the completeness
check passes, and appends the finish row. That answers "two writers of the
start row, no owner of the finish row" (lifecycle A3) without splitting
`registry.py`.

### 2.3 Versions folded into each key

`VERSION` is a module-level integer on every file whose output can change
meaning for the same setting. It is bumped only then (the third draft's rule
for people, kept).

| stage | modules whose VERSION folds in |
|---|---|
| `sample` | `data/environments/<env>.py`, `models/agent_models/<family>.py`, `agent/loop.py`, `agent/generate.py`, `data/task_record.py` |
| `build` | `data/task_record.py`, `data/probe_input.py`, `data/build_dataset.py`, `data/example.py`, `data/environments/<env>.py` |
| `train` | `data/example.py`, `data/prediction.py`, `train/utils/trainer.py`, `train/methods/<method>.py`, `models/probe_models/base.py` |
| `eval` | `data/prediction.py`, `eval/utils/probe_eval.py`, `eval/methods/<method>.py` |
| `inject` | `data/environments/<env>.py`, `models/agent_models/<family>.py`, `agent/loop.py`, `agent/generate.py`, `agent/inject.py`, `agent/inject_format.py`, `data/probe_input.py`, `data/task_record.py`, `models/probe_models/base.py` |
| `score` | `data/task_record.py`, `eval/score_run.py` |

This is the third draft's list plus the four the fourth draft dropped
(`probe_input`, `inject_format`, the eval modules, `score_run`), which the
lifecycle review found leave a stale directory looking finished (B1, A7).

### 2.4 The continue rule, per stage

| stage | finished | partial | how a dead piece shows | refire |
|---|---|---|---|---|
| `sample`, `inject` | `done.json` present -> skip | some record files missing or unfinished -> start the missing pieces again with the same run directory; finished files are never rewritten | the piece's tmux session is gone and its claimed files have no `final` row; `run.py ls` gives the verdict `dead` | `jobs/launch.py --refire <dir> --piece i` releases the unfinished files owned by that dead session, probes the card, restarts the piece with the command frozen in `meta.json`; one automatic refire per piece, then it stops and waits for a person (CONTEXT's refire quota) |
| `build` | `done.json` -> skip | no partial state; it starts over (minutes) | not applicable (one CPU process) | rerun the same command |
| `train` | `done.json` -> skip. `train_done.json` without `done.json` -> run the prediction step only | `last/` present and its recorded commit equals HEAD -> resume from its step; commit differs -> refuse without `--retry` | the session is gone and the heartbeat is stale | `--refire` restarts the same directory; the continue rule above decides where it picks up |
| `eval`, `score` | never skipped: `always_recompute` is true, the report is rewritten in place and carries the commit and the versions it was computed with | not applicable | not applicable | rerun |

The train rule is the lifecycle review's A6 fix, achieved with two markers
instead of a file split: `train_done.json` separates "training finished, the
prediction step died" from "training died at step 40", which the fourth draft's
one-marker wording cannot (`best/` exists in both).

`eval` and `score` always recompute **and** their module VERSIONs enter their
keys. The two together mean: a metric edit with a VERSION bump writes a new
directory and keeps the old numbers; a metric edit without one still reruns
rather than being silently reused. Principle 7 says these stages cost seconds,
so nothing is lost by recomputing.

### 2.5 What each stage writes into its run directory

| stage | outputs |
|---|---|
| `sample` | `records/*.jsonl`, `service_agent.json`, `service_probe.json`, heartbeats, logs, `done.json` |
| `build` | `examples.parquet`, `consumed.json`, `BUILD_REPORT.md`, `tool_vocab.json`, `qa_sample.txt`, `done.json` |
| `train` | `best/`, `last/`, `train_log.jsonl`, `ALIGN_CHECK.json`, `train_done.json`, `predictions.parquet`, `done.json` |
| `eval` | `PROBE_REPORT.json`, `PROBE_REPORT.md`, `done.json` |
| `inject` | `records/*.jsonl`, `service_agent.json`, `service_probe.json`, heartbeats, logs, `done.json` |
| `score` | `RUN_REPORT.json`, `RUN_REPORT.md`, `consumed.json`, `done.json` |

All six also hold `settings.yaml`, `settings_diff.yaml`, `meta.json` and, when
launched dirty, `dirty.patch`.

### 2.6 Gates the stages hold

- `build` refuses unless every requested (task, seed) has a record file with a
  `final` row, and refuses when the share with a non-null `abort` exceeds
  `build.max_abort_frac` (default 0.02). It writes `consumed.json` with the file
  list, sizes and a short hash (lifecycle B9). The gates that today live in
  `check_callstr.py` run here too: the assembled prefix must be a slice of the
  original thinking, a task must not cross splits, and every task must be in one
  of the environment's three official lists.
- `train` refuses to start into a directory that already has `train_log.jsonl`
  unless the continue rule in 2.4 applies or `--retry` is given (today's rule,
  `legacy/pipeline/train/train_causal_share.py:1017`).
- `train` runs the alignment gate before training (`train.align_check`, default
  on) and stops on a mismatch.
- `score` refuses a baseline whose `data`, `models.agent` or `generation`
  sections differ from the run's (the same-setup rule).
- `jobs/launch.py` refuses a dirty tree without `--allow-dirty`; `jobs/runs.jsonl`,
  `jobs/RESULTS.md` and `*.lock` are exempt (lifecycle B6).
- `jobs/launch.py` refuses to launch a key whose latest row is `running` with a
  fresh heartbeat and a live session, and prints the session instead
  (lifecycle A4).

---

## Part 3. `run_dir` and keys

### 3.1 Signature and home

```python
def run_dir(stage: str, setting: Setting) -> pathlib.Path
def key(stage: str, setting: Setting) -> str        # 12 lowercase hex characters
```

Both live in `experimental_settings/schema.py`, whose tree line says it holds
"the loader that reads a YAML file against it (file -> setting, diff, key)".
`run_dir` is the key plus the output root, and the root comes from
`constants/path_outputs.yaml`, which `schema.py` already reads after keying.

Why not `jobs/registry.py` (the lifecycle review's C1 proposal): every stage
program needs its own and its upstream's directory, and every stage program
already imports `schema.py` to read its setting. Putting `run_dir` in
`registry.py` would force `eval/`, `data/build_dataset.py` and the method files
to import the jobs layer to find a path. The alternative is named in Part 9(a).

### 3.2 Guarantees

1. **Deterministic.** Same `(stage, setting)` gives the same path, in any
   process, any venv, any host, any day. No clock, no hostname, no directory
   listing, no environment variable enters it.
2. **Complete.** Any change to a field the stage reads (2.1), to an upstream
   key it folds (2.1), or to a folded module VERSION (2.3) gives a different
   path.
3. **Narrow.** A change to a field the stage does not read gives the same path.
   Editing `train.lr` leaves `sample` and `build` at their keys; editing
   `eval.risk` leaves `train` at its key. The key is per stage, which is what
   makes "edit one value, reuse upstream" true (lifecycle A1).
4. **Debug is separate.** `--debug` is applied before keying and `debug: true`
   enters the key, and the path gains a `debug/` component. A debug run can
   never be reused for a real one and never collides with a real tmux session
   (lifecycle B4).
5. **Sweep children are ordinary settings.** Each child is a full setting with
   its own fields, so each gets its own path by rule 2, with no special case.
6. **Notes never enter.** `notes`, and any field marked `keyed: false` in the
   schema, are excluded.

### 3.3 What is hashed

`key(stage, setting)` hashes the canonical JSON of exactly this object:

```
{ "stage": <stage>,
  "fields": <the stage's read sections, resolved, with defaults filled in and
             model-table rows expanded, excluding fields marked keyed: false>,
  "debug": <bool>,
  "upstream": { <stage or reference name>: <its key> },
  "versions": { <module path>: <its VERSION int> } }
```

Canonical JSON means: keys sorted, no whitespace, floats formatted with
`repr`, lists kept in order (a list is a value, and reordering seeds is a
different experiment). The hash is `blake2b(digest_size=6)` rendered as 12
lowercase hex characters.

**The hash is implemented last.** Until it lands, `key()` raises
`NotImplementedError` and every caller reaches a directory only through
`run_dir`, so there is exactly one function to fill in and nothing to
retrofit. `run_dir` is written now, with the signature and the guarantees
above.

### 3.4 How `key()` reads a VERSION without an import cycle

`schema.py` must know `train/utils/trainer.py`'s VERSION to key a train run.
Importing it would be a cycle (the trainer imports `schema.py`) and would fail
outright in the appworld venv (the trainer imports torch).

So `key()` **reads the VERSION line from the module's source text**: every
versioned file declares, in its first 30 lines, exactly one line matching
`^VERSION = (\d+)$`. `key()` opens the file, finds that line, and parses the
integer. No import, no cycle, no venv problem, and `run.py selfcheck` asserts
every module `STAGES` names has exactly one such line and that the README lists
it. The same trick reads `agent/inject_format.py`'s `FORMATS` keys for the
`inject.format` axis, which is the one upward dependency the dependencies
review flagged in the settings layer (P1).

### 3.5 The directory

```
<root from constants/path_outputs.yaml>/
  <stage>/<key>/                      a real run
  debug/<stage>/<key>/                a --debug run
```

`root` is the only place the outputs location is written; nothing else in the
repo holds an NFS path, and `run.py selfcheck` fails on a `/home/` or `/net/`
string in code outside `constants/`.

There is no name in the path. A directory can be shared by several settings
(the same sample key under three probe settings), so a name in the path would
be a lie the moment a shared block is edited. `run.py where <workflow>
<setting> <stage>` prints the path, `run.py ls` prints the names, and
`meta.json`'s `owners` list holds every (workflow, setting) that landed on the
key.

### 3.6 `settings.yaml` is frozen into the directory

At the moment a stage first starts, `schema.freeze(setting, run_dir)` writes
the fully resolved setting as `settings.yaml` and the diff as
`settings_diff.yaml`. From then on:

- Every piece command names the **directory**, never the setting name:
  `<interpreter> -m <module> --run-dir <path> [--piece i/n]`.
- A piece loads `settings.yaml` with `schema.load_frozen(run_dir)`, which
  checks the file against the current schema and refuses when a field it holds
  no longer exists (an axis value was retired) rather than silently defaulting.
- `run.py <dir>/settings.yaml` reruns exactly that setting, which is how an old
  run is repeated after the YAML has moved on.
- A YAML edit after launch, or before a refire days later, cannot move a
  process to a different directory (lifecycle A2).

`schema.freeze` refuses to overwrite an existing `settings.yaml` whose content
differs; that mismatch means two settings collided on one key, which is a bug
in `key()`, and it fails loudly.

---

## Part 4. The environment base class

`data/environments/__init__.py`. Class name `Environment`. The class declares
the methods with one line each and no logic; `data/environments/appworld.py`
subclasses it as `class AppWorld(Environment)`.

The tree's line says "the eight methods" and then names nine
(`tasks, open, step, speculate, judge, close, split_args, build_call,
complete_call`). The names are the contract; the count is prose. Part 9(a)
records the discrepancy (dependencies P11).

### 4.1 Class attributes

| attribute | type | meaning |
|---|---|---|
| `NAME` | str | the value on the `data.env` axis, e.g. `appworld` |
| `VERSION` | int | bumped when the package interface or a text below changes |
| `INSTRUCTIONS` | dict[str, str] | variant name -> the developer message the agent reads; selected by `data.instructions` |
| `NO_CODE_MESSAGE` | str | what the agent is told when it wrote no code block |
| `RESULT_CAP` | int | characters kept of one observation (today 4000) |
| `SEED` | int | the environment's own seed (AppWorld's `random_seed`, today 100) |

`INSTRUCTIONS` is a dict, not a constant, so a prompt variant is a YAML line
that enters every key reading `data` (synthesis item 11, applied without the
move). Adding a variant is one dict entry plus one axis value in `schema.py`;
it never touches `VERSION`, because the old variant still exists and old
outputs are still reproducible.

### 4.2 Methods

| method | signature | returns | one line |
|---|---|---|---|
| `tasks` | `tasks(split: str) -> list[str]` | task ids | the split's task ids, read from the file `constants/path_datasets.yaml` names; no package import, so build and `run.py` can enumerate tasks in any venv |
| `open` | `open(task_id: str, seed: int) -> None` | — | a fresh world for this task and seed, named so two seeds never share the benchmark's scratch directory; the package is imported here |
| `step` | `step(code: str) -> Observation` | `Observation(text, error_kind)` | run the agent's code in the live world, clip the output at `RESULT_CAP`, classify the error |
| `speculate` | `speculate(call: str) -> Speculation` | `Speculation(code, arg_modes, text, ok, error_kind)` | make the predicted call executable, snapshot, run it, restore, refreeze the clock, assert no drift, return what came back |
| `judge` | `judge() -> Outcome` | `Outcome(success, detail)` | did the task succeed, plus the environment's own evaluation as a dict |
| `close` | `close() -> None` | — | end the world and delete the per-task outputs |
| `split_args` | `split_args(code: str) -> Call \| None` | `Call(tool, args)` where `args` is `list[(key, value)]` | find the first call in a block of the agent's own code and split it into a tool name and named arguments; `None` when there is none |
| `build_call` | `build_call(tool: str, args: list[tuple[str, str]]) -> str` | the canonical call string | the one spelling of a call, used as cgen's target and as the thing an eval compares against |
| `complete_call` | `complete_call(text: str) -> str \| None` | a finished call | finish a call the probe wrote that was cut off; `None` when it cannot be finished |

`Observation`, `Speculation`, `Call` and `Outcome` are small frozen dataclasses
declared in the same file, so a caller never indexes a tuple by position.

`judge` returns an `Outcome`, not a "verdict": in this repo a verdict is a
piece's health (CONTEXT).

### 4.3 Who calls what

| caller | methods |
|---|---|
| `agent/loop.py` | `tasks`, `open`, `step`, `judge`, `close`, `INSTRUCTIONS[...]`, `NO_CODE_MESSAGE`, `RESULT_CAP` |
| `agent/inject.py` | `speculate`, `complete_call`, `build_call` |
| `data/build_dataset.py` | `split_args`, `build_call`, `tasks` (the three official lists for the split) |
| `eval/score_run.py` | `split_args`, `build_call` (the after-the-fact fire account: did the model's own call match the predicted one) |

`data/environments/__init__.open_env(name) -> Environment` imports
`environments/<name>.py` inside the function, checks the nine methods are
present and callable, checks `INSTRUCTIONS` holds the requested variant, and
returns the instance. A missing method is an error at `open_env`, not at the
first call three hours into a run.

### 4.4 What `speculate` must guarantee

In order, and with the restore in a `finally`:

1. Snapshot the world under a fixed checkpoint name.
2. Make the call executable (the requote rules:
   `legacy/pipeline/inject/exec_calls.py:161-260`; an unparsable call is run
   as-is and allowed to fail, never skipped, so a wrong guess still costs what
   it costs).
3. Run it, clip the output at `RESULT_CAP`, classify the error kind.
4. Restore the snapshot, then refreeze the clock explicitly (restoring does not
   refreeze it), then assert the frozen time did not drift; a drift raises.
5. Return `Speculation`. The world is byte-identical to before the call, which
   the deferred `tests/` check verifies per environment in that environment's
   venv.

### 4.5 Venv rule

The file imports under `any`: the benchmark package import sits **inside**
`open()`, and the working-directory change the package needs happens there too,
after every path the process will use has been resolved (today's lesson,
`legacy/pipeline/inject/live_appworld.py:686-693`). `tasks`, `split_args`,
`build_call` and `complete_call` are pure and work everywhere, which is what
lets `data/build_dataset.py` and `eval/score_run.py` run in any venv
(dependencies P11).

The interpreter that runs a loop piece is the `venv` column of the
environment's row in `constants/path_datasets.yaml` (Part 6);
`jobs/launch.py` reads it. It is a location on this cluster, so it lives in
`constants/` and never enters a key.

### 4.6 VERSION rule

`appworld.VERSION` bumps when the benchmark package's interface changes in a
way that changes outputs, when `NO_CODE_MESSAGE` or `RESULT_CAP` changes, or
when an existing `INSTRUCTIONS` entry's text changes. Adding a new
`INSTRUCTIONS` entry does not bump it. The VERSION folds into the `sample`,
`build` and `inject` keys.

---

## Part 5. The setting schema

`experimental_settings/schema.py`. Sections are dataclasses, one per section,
every field with a default and a one-line comment. A setting lists only what
differs from the defaults.

### 5.1 Sections and fields

`meta`

| field | type | default | one line |
|---|---|---|---|
| `notes` | str | `""` | what this experiment is for; never enters a key |

`data`

| field | type | default | one line |
|---|---|---|---|
| `env` | axis | `appworld` | which benchmark environment |
| `instructions` | axis | `v1` | which instruction variant the agent reads |

`models`

| field | type | default | one line |
|---|---|---|---|
| `agent` | table alias | `gptoss120b` | the agent model's row in `models/table.yaml` |
| `probe` | table alias | `qwen06` | the probe backbone's row |

`generation`

| field | type | default | one line |
|---|---|---|---|
| `temperature` | float | `1.0` | sampling temperature |
| `top_p` | float or null | `null` | only sent when set, so the request body stays byte-identical when it is not |
| `max_step_tokens` | int | `8192` | the per-step generation budget |
| `stop` | list[str] | `["<|return|>"]` | stop strings |
| `effort` | axis | `high` | the harmony reasoning tier |
| `date` | str | `2026-08-06` | the date pinned into the prompt, so a rerun on another day renders the same prefix |

`sample`

| field | type | default | one line |
|---|---|---|---|
| `split` | str | `train` | which task split to run |
| `n_tasks` | int or null | `null` | cap on tasks; null is the whole split |
| `seeds` | list[int] | `[42, 67, 4267]` | one task run per seed; replaced, never appended |
| `max_steps` | int | `30` | the per-task step cap |
| `pieces` | int | `6` | loop pieces |
| `replicas` | int | `2` | agent-service replicas |

`build`

| field | type | default | one line |
|---|---|---|---|
| `max_cuts` | int | `64` | cuts kept per event, thinned evenly |
| `min_think` | int | `40` | characters of thinking below which a step has no cuts |
| `hist_rounds` | int | `3` | tool rounds of history the probe sees |
| `result_cap` | int | `400` | characters kept of one history result in the probe's text |
| `weight_mode` | axis | `uniform` | `uniform` gives every cut weight 1, `per_event` gives 1/m |
| `max_examples` | int or null | `null` | cap on examples, for `--debug` only |
| `max_abort_frac` | float | `0.02` | refuse to build when more than this share of records aborted |

`probe`

| field | type | default | one line |
|---|---|---|---|
| `method` | axis | `ctool` | `ctool`, `cgen` or `cparam` |
| `tuning` | axis | `full` | `full` or `lora` |

`train`

| field | type | default | one line |
|---|---|---|---|
| `lr` | float | `1.0e-5` | learning rate (LoRA's own default is `5.0e-4`, set in the YAML) |
| `epochs` | int | `1` | passes over the training rows |
| `seed` | int | `42` | weight init, shuffling and dropout |
| `max_len` | int | `8192` | tokens per event; an event longer than this is dropped whole |
| `events_per_mb` | int | `4` | events in one logical minibatch |
| `accum` | int | `2` | logical minibatches per update |
| `max_steps` | int or null | `null` | stop early, for `--debug` only |
| `checkpoint_hours` | float | `2.0` | how often `last/` is written |
| `align_check` | bool | `true` | run the alignment gate before training |
| `lora_r` / `lora_alpha` / `lora_dropout` / `lora_targets` | int / int / float / list[str] | `16` / `32` / `0.05` / backbone default | read only when `probe.tuning` is `lora` |

`train.predict` (a sub-section, so an `eval.*` edit never re-keys training —
lifecycle B2)

| field | type | default | one line |
|---|---|---|---|
| `splits` | list[str] | `["val", "test"]` | which splits get prediction rows |
| `cap` | int or null | `null` | rows per split, for `--debug` only |
| `max_new` | int | `96` | generation budget per row for cgen and cparam |

`eval`

| field | type | default | one line |
|---|---|---|---|
| `risk` | list[float] | `[0.10, 0.05]` | the wrong-fire rates theta is frozen at |
| `thetas` | list[float] | `0.500..0.975 step 0.025` | the sweep grid |
| `bootstrap` | int | `1000` | resamples for the interval, grouped by task |
| `trigger_run` | reference or null | `null` | cgen and cparam only: the ctool setting whose frozen theta selects the fire row |

`inject`

| field | type | default | one line |
|---|---|---|---|
| `split` | str | `test` | which task split to run |
| `n_tasks` | int or null | `null` | cap on tasks |
| `seeds` | list[int] | `[42]` | one task run per seed |
| `max_steps` | int | `30` | the per-task step cap |
| `pieces` | int | `6` | loop pieces |
| `replicas` | int | `2` | agent-service replicas |
| `probe_score` | reference | — | the setting whose ctool probe decides when to fire |
| `probe_gen` | reference | — | the setting whose cgen probe writes the call |
| `theta` | float | — | the fire threshold; no default, an unset theta refuses to start (CONTEXT) |
| `format` | axis | `note` | which of `inject_format.FORMATS` writes the result into the stream |
| `max_inject_per_step` | int | `1` | fires allowed per step |
| `arm` | axis | `probe` | `probe`, `no_probe` (the machinery wired, never fires), or `probe_nofill` (fires, injects nothing) |

`score`

| field | type | default | one line |
|---|---|---|---|
| `baseline` | reference | — | the sample setting this run is paired against, task by task and seed by seed |

There is no `logging` section: the tracker and the sampler are retired
(Part 9(a)#2).

### 5.2 The axes and where each value's code lives

| axis | allowed values | the code behind a value |
|---|---|---|
| `data.env` | `appworld` | `data/environments/<value>.py` |
| `data.instructions` | `v1` | `AppWorld.INSTRUCTIONS[<value>]` |
| `generation.effort` | `high`, `medium`, `low` | `models/agent_models/gptoss.py` |
| `probe.method` | `ctool`, `cgen`, `cparam` | `train/methods/<value>.py` and `eval/methods/<value>.py` |
| `probe.tuning` | `full`, `lora` | `train/utils/trainer.py` |
| `build.weight_mode` | `uniform`, `per_event` | `data/build_dataset.py` |
| `inject.format` | the keys of `agent/inject_format.FORMATS` | `agent/inject_format.py` |
| `inject.arm` | `probe`, `no_probe`, `probe_nofill` | `agent/inject.py` |
| `models.agent` / `models.probe` | the aliases in `models/table.yaml` with the matching `role` | the row plus `agent_models/<family>.py` or `probe_models/<backbone>.py` |

`run.py selfcheck` cross-checks each axis's literals against the files that
implement them: `data/environments/*.py`, the method files,
`inject_format.FORMATS`, `models/table.yaml`. A value with no code, or code
with no value, fails the check. That is synthesis item 1's benefit without the
file split.

**Axis values are never renamed**, only added and retired. A retired value stays
listed as retired, so an old `settings.yaml` still loads and an old directory
can still be rerun; `key()` treats a retired value exactly as it treated it
before.

### 5.3 References

A reference field holds `"<workflow>/<setting>"`, e.g.
`train_probe/ctool_on_qwen06`, or `"key:<12 hex>"` to pin a specific run
directly.

Resolution, at load:

1. Load the named setting from its own file, with the same defaults and the
   same `common` block that file gives it. A name that does not exist is a load
   error.
2. The referencing stage's `run_dir` for each stage it needs is computed from
   the resolved setting. `eval.trigger_run` gives eval(cgen) both
   `run_dir("train", ref)` (the ctool score per example) and
   `run_dir("eval", ref)` (theta and temperature); `inject.probe_score` gives
   `run_dir("train", ref)` (the weights) and `run_dir("eval", ref)` (theta and
   temperature); `score.baseline` gives `run_dir("sample", ref)`.
3. Every key so reached folds into the referencing stage's key (2.1), and is
   written into `meta.json` under `upstream`.
4. The referencing setting **inherits** `data`, `models.agent` and `generation`
   from the referenced setting. Stating a different value is a load error unless
   it sits under an explicit `override:` block, so an inject arm cannot silently
   differ from the data its probe was trained on, or from its baseline (the
   same-setup rule).
5. `run.py` refuses to run a stage whose referenced run has no `done.json`,
   and prints the command that would produce it.

### 5.4 The sweep keyword

A named setting may hold one `sweep:` block, a map from dotted field to list:

```yaml
sweep: {train.lr: [1.0e-4, 3.0e-4, 5.0e-4], train.seed: [42, 67]}
```

The loader expands it into the cross product, one child per combination, named
`<setting>/<field>=<value>,<field>=<value>` with the fields in the order the
block lists them. Each child is a full ordinary setting: it keys by rule 2 of
3.2, it launches, it refires, `run.py where` addresses it by that name.
`meta.json` and the start row carry `parent` (the setting name) and `swept`
(the field-value map), which is what `eval/method_table.py` groups by.

`--debug` is applied per child and **refused** when `debug.yaml` sets a field
the sweep also sets, because the child would collapse onto its sibling's key
(lifecycle B5).

### 5.5 `debug.yaml`

Sizes only, never a model and never a tuning, so a debug run walks the real
code path:

```yaml
sample: {n_tasks: 3, seeds: [42], max_steps: 5}
inject: {n_tasks: 3, seeds: [42], max_steps: 5}
build:  {max_examples: 64}
train:  {max_steps: 20, epochs: 1, predict: {cap: 100}}
eval:   {bootstrap: 50}
```

### 5.6 The loader

```python
def load(workflow: str, setting: str, overrides: list[str] = (), debug: bool = False) -> Setting | list[Setting]
def load_frozen(run_dir: Path) -> Setting
def freeze(setting: Setting, run_dir: Path) -> None
def diff(setting: Setting) -> dict
def resolve(reference: str) -> Setting
def key(stage: str, setting: Setting) -> str
def run_dir(stage: str, setting: Setting) -> Path
STAGES: dict[str, Stage]
```

Merge order, each step overwriting the last:

1. the dataclass defaults;
2. the workflow file's `common` block;
3. the named setting;
4. the `sweep:` child's own values (one child per call);
5. `experimental_settings/debug.yaml`, when `--debug`;
6. the command-line overrides `section.field=value`.

Debug before overrides, so an override beats debug. Model-table rows are
expanded into the setting **after** step 6 and **before** keying, so an edited
row is a new key. `constants/` is read after keying and never enters it.

A list field is replaced, never appended: `seeds: [42]` over
`seeds: [42, 67, 4267]` gives `[42]`.

The loader refuses, with the offending line named:

- a key that is not in the schema;
- a value outside an axis;
- a `pipeline:` list naming an unknown stage, or the same stage twice;
- a section for a stage the workflow does not run;
- a reference to a setting that does not exist, or whose inherited sections
  conflict without `override:`;
- a `sweep:` block that `debug.yaml` also touches, under `--debug`;
- `inject.theta` unset when the `inject` stage runs;
- a `settings.yaml` in `load_frozen` that holds a field the schema no longer has.

Format: YAML through PyYAML plus dataclasses. **Not OmegaConf**: the grounding
review found it installed in none of the venvs and it needs
`antlr4-python3-runtime`, and the only OmegaConf feature this schema uses is
interpolation, which a twenty-line resolver in `schema.py` covers.

---

## Part 6. The model table and constants

### 6.1 `models/table.yaml`

One row per alias. A row's keyed columns are expanded into the setting before
keying, so editing one is a new key; the serving-only columns are marked and
excluded, so moving a server to another card reuses the directory.

| column | keyed | meaning |
|---|---|---|
| `alias` | yes | the name a setting writes in `models.agent` or `models.probe` |
| `role` | yes | `agent` or `probe` |
| `family` | yes | agent rows: which `agent_models/<family>.py` renders and parses |
| `backbone` | yes | probe rows: which `probe_models/<backbone>.py` holds the quirks |
| `weights` | yes | the alias to look up in `constants/path_models.yaml` |
| `dtype` | yes | the serving or training dtype |
| `quantization` | yes | null, or the scheme; it changes the bytes the model emits |
| `max_model_len` | yes | the context window the server is started with; a shorter one changes what is dropped |
| `tokenizer` | yes | the weights alias whose tokenizer is used, when it differs from `weights` |
| `served_name` | no | the model name the client sends |
| `host` | no | where the server runs |
| `port` | no | which port |
| `gpus` | no | which cards |
| `memory_fraction` | no | vLLM's `--gpu-memory-utilization` |
| `extra_env` | no | environment variables the server needs (`LD_LIBRARY_PATH`, sampler flags) |

**The rule for a new column.** Ask: would two runs that differ only in this
column produce different bytes? Yes, it is keyed and it belongs in this file.
No, it only places a process, and it is serving-only. A value that changes a
result and is not a property of the model belongs in `experimental_settings/`,
not here (`generation.effort` and `generation.date` are settings fields for
exactly this reason; today they are client keys and a server pin, which is how
one run silently rendered at `high` when it was meant to be `medium`).

The read-only hook question the fourth draft left open closes this way: the
keyed columns of `table.yaml` change results, so the hook covers this file too,
and an agent proposes a row as a task.

### 6.2 `constants/path_datasets.yaml`

One block per environment.

| column | meaning |
|---|---|
| `home` | the clone's directory, the one the package is imported from |
| `venv` | the interpreter that runs a loop piece for this environment |
| `splits` | split name -> the file listing that split's task ids |
| `task_lists` | `train`, `val`, `test` -> the official task list used to split the dataset |
| `scratch` | where the benchmark writes its per-task outputs |

`venv` lives here because an interpreter path is a location on this cluster: it
does not change a result and must never enter a key (the fix dependencies P7
asked for, without a new file). `jobs/launch.py` reads it to build a piece's
command.

### 6.3 `constants/path_outputs.yaml`

| column | meaning |
|---|---|
| `root` | the outputs root on NFS; every run directory is under it |
| `logs` | where a tmux piece tees its log, when it is not the run directory |

### 6.4 `constants/path_models.yaml`

| column | meaning |
|---|---|
| `<alias>` | the directory holding those weights |

Nothing in `constants/` enters a key, ever. A path may change only when the
same bytes moved; a new set of weights is a new alias in `models/table.yaml`,
which is keyed.

**One recorded gap.** The environment's split files and official task lists are
named in `constants/` and their contents never enter a key (dependencies P5).
The sample stage therefore writes the resolved task id list and the split
file's short hash into `meta.json`, and `run.py ls` flags a directory whose
split file has changed since the run. That makes the gap visible rather than
closing it; closing it would mean hashing a dataset file at key time, which
breaks `run_dir`'s purity.

---

## Part 7. Service protocols

Two services, each one file with both ends, as the tree says. Both clients are
standard library only and import under `any`; both servers import their heavy
libraries inside the serving function.

### 7.1 The agent service — `models/agent_models/service.py`

**Server (`main`, vllm venv).** `serve(row, generation, run_dir)` starts vLLM
for a `models/table.yaml` row with the row's keyed flags (`--served-model-name`,
`--max-model-len`, `--dtype`, `--quantization`) and serving-only flags
(`--port`, `--host`, `--gpu-memory-utilization`, `extra_env`), waits for
`/health`, runs the check table, and writes `service_agent.json` into the run
directory with the endpoint, the pid, the resolved flags and the row's keyed
columns.

`attach(row, generation)` finds a live server and reuses it **only** when its
`service_agent.json` (or its `/v1/models` plus the row recorded beside it)
shows the same keyed columns; a difference is a refusal, not a warning. That is
today's lesson in one sentence: pointing at the wrong service does not error,
it produces wrong numbers.

The check table, run once at start:

| check | how |
|---|---|
| health | `GET /health` returns 200 |
| model | `GET /v1/models` lists `served_name` |
| render equals server | `gptoss.render_ids(fixed_conversation, effort, date)` equals the ids vLLM renders for the same conversation, token for token |

**Client (any venv, standard library).**

| call | request | response |
|---|---|---|
| `stream(prompt_ids, generation, seed)` | `POST /v1/completions` with `model`, `prompt` (token ids), `max_tokens`, `temperature`, `top_p` and `seed` only when set, `stop`, `add_special_tokens=false`, `skip_special_tokens=false`, `return_token_ids=true`, `stream=true`, `stream_options={"include_usage":true}` | an iterator of `(text_delta, token_id_delta)` pairs, plus `finish_reason`, `stop_reason` and `usage` when the stream ends cleanly; `close()` aborts server-side decoding |
| `health()` | `GET /health` | up or not |

The prompt is always token ids, for both `sample` and `inject`: one generation
path, so a probe run and its baseline are compared on the same path (every
reviewer says to keep this). Retries: three, exponential backoff, on connection
errors and 5xx; a 400 is passed to the caller, which records
`abort="context_overflow_400"` and evaluates the task honestly.

### 7.2 The probe service — `models/probe_models/service.py`

**Server (`main`, probe venv).** `serve(setting, run_dir, port, device)` loads
the score probe from `run_dir("train", probe_score_ref)/best/` with the
temperature and theta from `run_dir("eval", probe_score_ref)/PROBE_REPORT.json`,
and the generation probe from `run_dir("train", probe_gen_ref)/best/`. It
refuses to start when `inject.theta` is unset (CONTEXT: theta is always given by
a person). `--check` loads both, answers one request of each kind, and exits,
which is the gate a launch runs before the loop pieces start. `--render-only`
loads no probe and answers `/render`, `/encode`, `/decode` and `/health` only,
which is the mode a `sample` run uses; `/score` and `/gen` then return 503 and
never pretend a probe is there.

| route | request | response |
|---|---|---|
| `POST /score` | `{"text": <the probe's input text>}` | `{"conf": float, "label": str, "fired": bool}`; `conf` is `softmax(logits / T).max()` with `T` from the report, `fired` is `conf >= theta` |
| `POST /gen` | `{"text": <the probe's input text at the fire>}` | `{"call": str}`; greedy, `max_new` tokens, cut at the first newline, stripped |
| `POST /render` | `{"messages": [...], "effort": str, "date": str}` | `{"prefix_ids": [int], "n_tokens": int}` |
| `POST /encode` | `{"text": str, "special": bool}` | `{"ids": [int]}`; `special=false` keeps a control marker inside a result as plain text, `special=true` turns it into its control token |
| `POST /decode` | `{"ids": [int]}` | `{"text": str}`; special tokens are kept, because the model really wrote them |
| `GET /health` | — | the startup configuration echoed back: `theta`, `temperature`, the two run keys, `render`, `encode_special`, `decode`, `device`, `date` |

Every response also carries `wall_s`. The service is single-threaded, which is
enough: a loop piece is serial and one request is in flight at a time. One
service is shared by the stage's loop pieces.

**Client (any venv, standard library).** `score(text)`, `gen(text)`,
`render(messages, effort, date)`, `encode(text, special)`, `decode(ids)`,
`health()`. The loop refuses to start when `/health` does not echo
`render="harmony_ids"`, `decode=true`, and, for a `p2_*` format,
`encode_special=true` (today's refusal, kept:
`legacy/pipeline/inject/live_appworld.py:572-587`).

### 7.3 Which end renders

The loop runs in the environment's venv, which cannot hold `openai_harmony`
(pydantic 1 against pydantic 2). So:

- `models/agent_models/gptoss.py` holds both renderings. `render_text(messages,
  effort, date)` is pure string assembly (standard library) and works
  everywhere; `render_ids(messages, effort, date)` imports `openai_harmony`
  **inside the function** and produces token ids exactly as vLLM's chat
  endpoint does.
- `models/probe_models/service.py` answers `/render` by calling
  `gptoss.render_ids`. Its process is the only one in the loop's reach that runs
  in a venv with `openai_harmony`.
- `models/agent_models/service.py`'s check compares `gptoss.render_ids` against
  the server's own rendering, in the vllm venv, at start.

`/render` is not on the probe service's tree line, which lists score, generate,
encode and decode. It goes there under the rule "a mechanism with no obvious
file goes into the file whose line best covers it": the loop needs prompt ids,
the only server it can reach is this one, and this is where `/render` lives
today. Part 9(a)#7 states the choice and its alternative.

The cost this carries: a `sample` run starts one extra CPU process, the probe
service in render-only mode, purely to render. That is what today's no-probe
arm does (`--render-only`), and it is the price of keeping one generation path
for sample and inject.

### 7.4 Who starts a service and how attach is verified

`jobs/launch.py` starts every service piece, in its own tmux session, before the
loop pieces, and registers it in `meta.json` and the start row with
`kind: service` and its port. A loop piece never starts a service. Attach
reuses a live server only when its keyed columns and generation settings match
(7.1); the `--check` run is the gate for the probe service. `run.py ls` gives a
service piece a verdict from its port, not its heartbeat (Part 8).

---

## Part 8. The registry

`jobs/registry.py`, standard library only.

### 8.1 Who writes `jobs/runs.jsonl`

Only `run.py` and `jobs/launch.py`, both on the login machine, both under
`jobs/runs.jsonl.lock` (an `fcntl` exclusive lock on a local file). A stage
process on a compute node writes **only into its own run directory**: its
heartbeat file, its state block in `meta.json`, its `done.json`. `run.py ls`
and `run.py sync` fold those in and append any missing finish row.

This is synthesis item 2's substance without its file split: the NFS lock
problem disappears because nothing on a compute node takes a lock, and the
row-writing half stays in the same file as the reading half until `ls` or `kill`
needs more than the standard library, at which point the tree's own line says it
becomes `registry_cli.py`.

### 8.2 Row fields

Start row, appended by `jobs/launch.py` after the alive check (so a piece that
dies before it starts still leaves a row, because the alive check fails and the
row is written with `status: "launch_failed"`):

| field | meaning |
|---|---|
| `ev` | `"start"` |
| `t` | login-machine timestamp |
| `run_id` | `<stage>-<key>` |
| `stage`, `key`, `dir` | the stage, its key, its run directory |
| `workflow`, `setting` | which YAML file and which named setting launched it |
| `parent`, `swept` | the sweep parent and the swept field-value map, when it is a child |
| `debug` | true for a `--debug` run |
| `commit`, `branch`, `dirty`, `dirty_count`, `dirty_files` | the code the run started at; `dirty` true means the commit does not lead back to what ran |
| `host` | the login machine that launched |
| `venv` | the interpreter per piece kind |
| `pieces` | list of `{index, kind, host, gpus, session, log, port, cmd}`; `kind` is `loop`, `train`, `cpu` or `service` |
| `upstream` | `{stage or reference name: key}` |
| `versions` | `{module path: VERSION}` |
| `settings_diff` | what differs from the defaults, as JSON, which `run.py find` searches |
| `cmd` | the display command |

Finish row, appended by `run.py` when it first sees `done.json` without one, or
by `run.py kill`:

| field | meaning |
|---|---|
| `ev` | `"finish"` |
| `t`, `run_id` | when, and which run |
| `status` | `ok`, `failed`, `killed` |
| `counts` | the stage's `done.json` counts |
| `metrics` | the headline numbers, pulled from the stage's report |
| `note` | a person's one line, optional |

A later finish row for the same `run_id` wins. `runs.jsonl` is append-only and
in git; `jobs/RESULTS.md` is rendered from it on every append and never edited
by hand. A run's one-sentence conclusion does not live here: it goes into
`notes/TIMELINE.md`, which is a person's file (lifecycle C3).

### 8.3 `meta.json`

| field | meaning |
|---|---|
| `meta_version` | the file's own version |
| `stage`, `key`, `dir` | identity |
| `owners` | every `{workflow, setting}` that landed on this key |
| `debug` | true for a debug run |
| `upstream` | `{stage or reference: {key, dir}}` |
| `versions` | `{module path: VERSION}` at the time of the first launch |
| `pieces` | the piece list, with each piece's frozen command |
| `launches` | append-only: one entry per launch or refire, `{t, host, commit, branch, dirty_count, dirty_files, cards, cmd, piece}` — this absorbs today's `RUNMETA.json` (lifecycle B6) |
| `split_file` | sample and inject: the split file path, its short hash, and the resolved task ids |
| `state` | `{piece index: {done, total, unit, ts, status}}`, written by each piece for itself |

### 8.4 The heartbeat

One line per progress unit, one file per piece,
`<run dir>/heartbeat.<piece>.jsonl`, one JSON object per line:

```
{"done": int, "total": int, "unit": "task"|"step"|"item", "ts": float,
 "tok_in": int?, "tok_out": int?, "loss": float?, "status": "done"?}
```

`done`, `total`, `unit` and `ts` are required; `ts` is that machine's own clock
and is only ever diffed against another `ts` from the same machine. Every stage
program emits `emit(0, total, unit)` before its main loop, which is the signal
that the model has finished loading. Third-party servers do not emit
heartbeats; their pieces get a port probe instead.

### 8.5 Verdicts

Pure functions in `jobs/registry.py`, taking a state dict and returning
`(verdict, escalated)`. No process is resident; `run.py ls` computes a verdict
on demand from the heartbeat files and one `tmux ls` per host. The six values
and the priority order are CONTEXT's and today's
(`legacy/ops/verdicts.py`): `done` -> `dead` -> `suspected stall` ->
`warming up` -> `slowed` -> `healthy`.

| input | source |
|---|---|
| `alive` | `tmux has-session` on the piece's host; `None` when the probe itself failed, which is treated as not-free and not-alive |
| `has_beat`, `beat_age_s`, `done`, `total` | the piece's heartbeat file, read with the login machine's clock for the age |
| `since_launch_s` | the piece's `launches` entry |
| `stall_s`, `escalate_s`, `warmup_s` | `verdicts`-style defaults adapted to the piece's own typical heartbeat interval, overridable per piece at launch |
| `port_ok`, `port_ever_ok`, `port_fail_rounds` | service pieces only |

Defaults, carried over unchanged: stall line is five times the median of the
last twenty heartbeat intervals with a floor of three sampling rounds; the
escalation line is three times the stall line; the warm-up cap is 30 minutes;
`slowed` is a recent rate below half the average.

The escalation line survives as a printed flag on `run.py ls`, not as a trigger:
nothing spawns an incident agent any more (Part 9(a)#2).

### 8.6 The subcommands

| command | prints |
|---|---|
| `run.py ls [workflow]` | one line per stage run: workflow/setting (and sweep parent), stage, key, verdict, progress `done/total unit`, rate, ETA, heartbeat age, sessions, cards, and flags: `edited` (the setting's current key differs from this directory's), `behind` (a folded module's VERSION is ahead of the directory's), `dirty` (launched dirty), `debug`, `orphan` (a tmux session of this repo matching no row) |
| `run.py where <workflow> <setting> <stage>` | the run directory |
| `run.py find section.field=value ...` | the rows whose `settings_diff` matches, newest first |
| `run.py kill <workflow> <setting> <stage>` | ends every piece's session, appends the killed row; refuses when a piece is still alive after the kill |
| `run.py free` | the free cards, from a live `nvidia-smi` probe on each host, fail-closed: a card with any compute process, or a probe that failed, is busy |
| `run.py sync` | folds every run directory's `done.json` and state into `runs.jsonl`, writes missing finish rows, re-renders `RESULTS.md` |
| `run.py selfcheck` | the README's annotation lines against the real import graph; every axis literal against its implementing file; one `VERSION =` line per module `STAGES` names; every tracked Python file present in the README; no `/home/` or `/net/` in code outside `constants/`; each file imports under the venv its annotation claims |

---

## Part 9. Decisions, proposals and their alternatives

### (a) Choices the owner could reasonably veto

1. **`run_dir` and `key` live in `experimental_settings/schema.py`, not
   `jobs/registry.py`.** Alternative: `registry.py`, as the lifecycle review
   proposed. This one, because every stage program already imports `schema.py`
   for its setting, and the other way would force `eval/` and `data/` to import
   the jobs layer to learn a path.
2. **The sampler, its web page, the incident agent and the escalation trigger
   are retired.** `run.py ls` computes the six verdicts from heartbeat age and
   tmux liveness, on demand. Alternative: keep a resident sampler. This one, per
   the owner's decision; the cost is that nobody is watching at 03:00, and the
   CONTEXT entries for sampler, sampling history, window, incident agent,
   autopsy and incident record are retired in the same commit. The refire quota
   (one automatic refire per piece) survives in `jobs/launch.py`.
3. **`key()` reads a module's `VERSION` from its source text, not by importing
   it.** Alternative: pass the version tuple in from the calling stage
   (synthesis item 1). This one, because `schema.py` is one file in the fixed
   tree, an import would be a cycle, and the trainer's module-level torch import
   would make the read impossible in the appworld venv. Cost: the rule "exactly
   one `^VERSION = <int>$` line in the first 30 lines" is enforced by selfcheck
   rather than by the language.
4. **`eval` and `score` always recompute, and their module VERSIONs still enter
   their keys.** Alternative: one or the other. Both, because the VERSION keeps
   old numbers retrievable and the recompute stops a metric edit without a bump
   from being silently reused.
5. **Prediction rows carry the full ctool logit vector.** Alternative: a scalar
   confidence. The vector, because the temperature is fit at eval time and the
   calibrated confidence cannot be recovered from a scalar; the cost is a few
   hundred megabytes per train run, the same order as today's `logits_*.pt`.
6. **Prediction rows are denormalized: they carry the target.** Alternative:
   eval joins back to `examples.parquet`. Denormalized, so `eval/` reads exactly
   one file and has exactly one upstream directory per method.
7. **`/render` is served by the probe service.** Alternative: the agent
   service's client sends harmony text and lets vLLM tokenize it. The probe
   service, because vLLM's tokenize endpoint cannot be told to keep a literal
   `<|end|>` inside an execution result as plain text, and that divergence
   silently changes the prompt from that step on. Cost: a `sample` run starts a
   render-only probe process.
8. **The base class declares the nine method names the tree lists, although the
   line says eight.** Alternative: fold the three call-syntax methods into one.
   The nine names, because the names are the contract and the count is prose.
9. **`build`'s key folds the sample key plus `sample.{split, n_tasks, seeds}`;
   the consumed file list is written but not hashed into the key.** Alternative:
   the manifest in the key (third draft). This one, because hashing thousands of
   files would make `run_dir` impure and slow; the residual risk (a refire
   rewrites a record after build ran) is made visible by `consumed.json` and a
   flag on `run.py ls`.
10. **`done.json` for `sample` and `inject` is written by `run.py` on the login
    machine, not by a piece.** Alternative: a designated last piece. This one,
    because a piece cannot know it is last, and it gives the finish row one
    owner.
11. **The record is one file per (task, seed), claimed by exclusive create.**
    Alternative: one shared jsonl appended by many pieces. This one: a killed
    piece would leave a partial line that breaks every strict read of a shared
    file, and per-task files are what the collector does today.
12. **A final row with a non-null `abort` counts as done.** Alternative: retry
    aborted tasks. This one, so a poisonous task cannot loop; the cost is
    controlled by `build.max_abort_frac`, which stops a build over a batch that
    mostly failed.
13. **The `venv` that runs a loop piece is a column in
    `constants/path_datasets.yaml`.** Alternative: a column in `models/table.yaml`
    or a literal in `jobs/launch.py`. This one, because an interpreter path is a
    location and must never enter a key.
14. **`models/table.yaml` is covered by the read-only hook.** Alternative: leave
    it editable by agents. Covered, because its keyed columns change results
    exactly as a setting does; this closes the fourth draft's open question.
15. **There is no `logging` section and no tracker.** Alternative: keep the
    MLflow switch from the third draft. Dropped, because with the sampler
    retired nothing feeds it and `run.py ls` plus the run directory answer the
    same questions.
16. **The instruction text is an axis value (`data.instructions`), not a
    VERSION.** Alternative: bump `appworld.VERSION` on every prompt edit. The
    axis, so two prompt variants can be compared side by side and both stay
    reproducible.
17. **Run directories are named by key only, with no name and no symlink.**
    Alternative: a `by-name/` tree of symlinks beside the keyed tree. Key only,
    because a directory shared by several settings cannot carry one name;
    `run.py where` and `meta.json`'s `owners` cover the lookup.
18. **`run.py sync` means "fold run directories into the ledger", not "push
    metrics to a tracker".** The tree names the subcommand; this is what is left
    for it to do once the tracker is dropped.
19. **The chat-endpoint baseline is dropped from `baseline.yaml`.** Alternative:
    rewrite it on urllib. Dropped: `models/agent_models/service.py`'s client is
    the one generation path, and a chat-path baseline would compare two paths
    (grounding F9). The chat endpoint survives only inside the
    render-equals-server check.
20. **The read-only feature, the mbert line, the offline replay line,
    `ident3_gate.py`, `demo/`, the five non-AppWorld environment runners and the
    34 existing test files are retired, not homed.** Their code stays in git at
    the checkpoint tag. The `readonly` axis, `param_label.py`,
    `pipeline/driver.py`'s `awaiting_decision` stop and the recipe engine go with
    them (synthesis item 10).

### (b) Reviewer fixes that would need a structural change — not applied

1. **Split `schema.py` into `schema.py` + `loader.py` + `key.py`** (synthesis 1).
   Would add two files. It would buy a fan-in of one for the axis literals and
   an import-free `key()`. Not applied; 3.4's source-text read gets the second
   half of that benefit inside one file.
2. **Split `registry.py` into `ledger.py` + `status.py`** (synthesis 2). Would
   add one file. It would buy a compute-node half that cannot take a lock by
   construction. Not applied; 8.1 gets the same property by rule, and the tree's
   own line already names `registry_cli.py` as the future split.
3. **Bring back `train/packing.py` and `train/reference.py`** (synthesis 3).
   Would add two files. It would buy one copy of the 611-line packing that cgen
   and cparam share, instead of two guarded by a deferred test. Not applied; the
   tree says each method file is complete on its own with no shared packing.
4. **Split `trainer.py` into `trainer.py` + `tuning.py` + `predict.py`**
   (synthesis 4). Would add two files. It would buy a continue rule decidable
   from the file list alone. Not applied; 2.4 gets the decidability from two
   markers instead.
5. **`data/probe_report.py`** (synthesis 5). Would add one file. It would buy a
   probe report defined in `data/` with the other formats and read downward by
   `models/probe_models/service.py` instead of upward. Not applied; 1.4 puts the
   format in `eval/utils/probe_eval.py`, whose line says "write the report", and
   accepts the upward import.
6. **Split each `service.py` into `server.py` and `client.py`** (synthesis 6).
   Would add two files. It would buy a venv boundary that selfcheck can
   import-test directly. Not applied; the tree says each service is one file
   with both ends, and selfcheck import-tests the module under all three venvs
   instead.
7. **Move the model table to `experimental_settings/models.yaml` and serving
   location to `constants/models.yaml`** (synthesis 7). Would add one file and
   move another. It would buy a `constants/` that provably holds nothing keyed.
   Not applied; 6.1's keyed/serving-only column marking gets the same guarantee
   in one file, and the tree names `models/table.yaml`.
8. **`data/check_dataset.py` for the build gates** (smaller item). Would add one
   file. It would buy a separate edit trigger for a new silent-failure gate. Not
   applied; the gates stay in `build_dataset.py`, whose line names them.
9. **Move `environments/` to the top level** (synthesis 11). Would move a
   folder. It would buy a layer whose callers are `agent/` and `data/` and whose
   contents are prompt text, not a disk format. Not applied; the tree puts it
   under `data/`.
10. **Flatten `train/` and `eval/`, rename eval files by their metric, and add
    `data/methods/<m>.py`** (synthesis 12). Would move seven files and add
    three. It would buy no name collisions in a file switcher and a fourth
    method that touches three files instead of five. Not applied; the tree fixes
    `train/methods/` and `eval/methods/` with the same three names.

### (c) The nine lifecycle scenarios, walked

**1. First run of `train_probe.yaml:ctool_on_qwen06`.**
`run.py train_probe ctool_on_qwen06` loads the setting (5.6), expands the model
rows, and walks `pipeline: [sample, build, train, eval]`. For `sample`:
`run_dir("sample", s)` gives a path with no `done.json`, so `jobs/launch.py`
runs the dirty gate, probes cards, freezes `settings.yaml` and `meta.json`,
starts two vLLM pieces, one render-only probe piece and six loop pieces in tmux,
waits for the alive check, appends the start row, and the walk stops there,
printing the monitoring command. Each loop piece claims (task, seed) files by
exclusive create and writes records. On a later `run.py` call, the walk sees
every requested file finished, writes `done.json`, appends the finish row, and
moves to `build`: an in-place CPU process that reads the records, refuses if any
are missing, writes `examples.parquet` and `consumed.json`, and writes its own
`done.json`. `train` launches one piece on one card; the trainer reads the
example parquet, trains, writes `train_done.json`, then runs predictions on val
and test and writes `predictions.parquet` and `done.json`. `eval` runs in place
on the CPU, fits the temperature and theta on val, freezes on test, and writes
`PROBE_REPORT.json`. Four directories, four keys, four rows.

**2. Rerun unchanged.** The same command recomputes the same four keys (3.2
rule 1), finds `done.json` in `sample`, `build` and `train`, and skips them.
`eval` reruns because `always_recompute` is true and overwrites its report with
the same numbers and today's commit. Nothing on a card starts. Total cost:
seconds.

**3. Partial train.** The train piece died at step 40. `run.py ls` shows the
verdict `dead` (session gone, heartbeat stale). The rerun finds no
`done.json` and no `train_done.json` but a `last/` whose recorded commit equals
HEAD, so the trainer resumes from step 40 into the same directory. Had it died
after training but during prediction, `train_done.json` would be present and the
rerun would run the prediction step only. Had the commit moved, the trainer
refuses and says so; `--retry` starts fresh.

**4. Dead piece.** One of six sample loop pieces died with two tasks claimed and
unfinished. `run.py ls` shows five healthy pieces and one `dead`.
`jobs/launch.py --refire <dir> --piece 3` reads that piece's frozen command from
`meta.json`, deletes the unfinished record files whose `meta` row names the dead
session, probes the card, restarts the piece in a new tmux session, appends a
launch entry. The five live pieces are untouched; the service pieces are reused.
A second death of the same piece stops and waits for a person (the refire quota).

**5. Edit one value.** `train.lr` changes from 1e-5 to 3e-5.
`key("sample", s)` and `key("build", s)` are unchanged, because neither stage
reads `train` (3.2 rule 3), so both directories are reused with no GPU work.
`key("train", s)` and, through it, `key("eval", s)` change; two new directories
appear, the old ones stay with their own `settings.yaml` inside, and `run.py ls`
shows both with what differs. Editing `eval.risk` instead changes only the eval
key: no GPU work at all, because the prediction rows cover every example
(`train.predict` is its own sub-section, so an `eval.*` edit cannot reach the
train key). Editing the cut rule in `data/probe_input.py` and bumping its
VERSION changes the `build`, `eval` and `inject` keys; `sample` is untouched and
its records are reused.

**6. Sweep.** `sweep: {train.lr: [1e-4, 3e-4, 5e-4], train.seed: [42, 67]}`
expands at load into six children named `<setting>/train.lr=1e-4,train.seed=42`
and so on. All six share one sample key and one build key. `run.py` walks the
children in order; the first child launches `sample`, and the other five find a
row whose status is `running` with a fresh heartbeat and a live session, so they
refuse to launch it and wait (the rule in 2.6). When the shared stages are done,
the six train runs launch on six cards. `run.py where <setting>/train.lr=3e-4,train.seed=67 train`
addresses one child. `eval/method_table.py` groups them by `parent` and reports
mean and spread.

**7. Inject referencing a probe.** `inject.yaml:ctool_qwen06_p1e1` names
`probe_score: train_probe/ctool_on_qwen06`, `probe_gen:
train_probe/cgen_on_qwen06`, `theta: 0.9`, `format: p1_e1`, and
`score.baseline: baseline/gptoss120b_appworld`. The loader resolves all three
references, inherits `data`, `models.agent` and `generation` from them (a stated
difference is a load error), and folds four keys into the inject key: the two
train keys (the weights) and the two eval keys (theta and temperature).
`run.py` refuses if any referenced run lacks `done.json`. `jobs/launch.py`
starts the vLLM pieces, one probe service piece loading both probes from
`best/` and reading theta and the temperature from the ctool `PROBE_REPORT.json`,
runs `--check`, and then the loop pieces. After the run, `score` pairs the inject
records with the baseline sample records task by task and seed by seed and
refuses the pair if the generation settings differ.

**8. Debug.** `--debug` lays `debug.yaml` over the setting before keying, and
`debug: true` enters the key, so `run_dir` lands under `<root>/debug/<stage>/<key>`.
The tmux session name carries that key, so it cannot collide with a real run's.
The rows carry `debug: true` and `run.py ls` hides them unless `--debug` is
passed. A non-debug walk never considers a debug directory for reuse, because
the keys differ. The debug run uses the same model, the same tuning and the same
code path — only the sizes shrink.

**9. Two sessions at once.** Two people (or two agent sessions) run the same
setting from the same login machine. Both compute the same key. The first
launches and appends a start row. The second's launch gate finds the latest row
for that key is `running` with a fresh heartbeat and a live tmux session, and
refuses, printing the session name. If the first run had died, the second finds
`dead` and is told to use `--retry` or `--refire`, so an out-of-memory failure
cannot loop. Both sessions append to `runs.jsonl` under the same local lock, and
because the file is append-only their git commits merge. A stage process on a
compute node takes no lock at all, so two hosts cannot deadlock on NFS.

---

## Appendix: what a builder still has to decide

Three things this document deliberately leaves open, each with the place it is
settled:

- **The hash function's exact input serialization** beyond "canonical JSON":
  float formatting across Python versions is the one place a key could drift.
  Settled when `key()` is implemented, with a golden-key test in `tests/`.
- **The generation cost of predicting at every cut** for cgen and cparam. The
  construction plan measures it in the smoke run. The fallback, written down and
  not built: an `eval.trigger_run` field that selects the rows a ctool run's
  frozen theta fires on, moving the filter back before generation.
- **Whether `p2_*` formats survive** the move of `/encode` to the probe service
  with `split_special_tokens`: today they do, and `probe_cfg_problem`'s
  `encode_special` check is kept for exactly this.
