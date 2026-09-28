# new1 from zero: the file structure

Fourth draft, 2026-09-17. The third draft is commit `771a6e5`; on 2026-09-17
gyb and Claude walked its tree directory by directory with one question per
entry: what operation adds a file here, and what operation edits this file.
Every entry now answers both. gyb deleted the third draft's Part 2 (the
module descriptions) and the migration notes during the walk; they are
rewritten against this tree next, and until then commit `771a6e5` holds the
old text.

The principles the tree follows, in the order gyb gave them:

1. One experiment is one setting. A setting holds every hyperparameter, and
   the file it lives in says which stages run. The whole repo exists to run a
   setting.
2. Every run is reproducible. Same setting, same output directory: a finished
   output is reused, a partial one is continued, an edited setting gets a new
   directory. Outputs stay retrievable after the code changes, through version
   numbers.
3. Short, standard layers: `data`, `models`, `agent`, `train`, `eval`,
   `jobs`. Settings control their arguments.
4. `--debug` runs any setting tiny: a few tasks, a few examples, a few steps.
5. No copies of almost the same file and no framework: a piece of code becomes
   shared on its third repetition, and only when it has stopped changing.
   When several files of one layer share code, the shared code is a `utils`
   in that layer and each method keeps its own file.
6. Each file does one thing that its name says, so the file to edit is found
   by name. The README lists every file with that one line.
7. Every output goes to disk, and `eval/` only reads disk: no GPU, no torch.
   The GPU half of an evaluation (running a probe over its splits) is the last
   step of `train`, so a change to how numbers are computed reruns in seconds.

Two rules that follow from them and recur below: any new value (an
environment name, a probe method, a tuning, an injection format) is
registered in `experimental_settings/schema.py` before a YAML file may use it,
so a misspelled name fails at load; and every format that lives on disk
between two stages is defined once, in `data/`.

---

## Part 1. The file structure

```
new1/
  README.md               for the future reader: this tree, one line per file, how to run, the extension recipes.
                          Edited whenever the tree changes; selfcheck fails on a Python file missing from it
  CLAUDE.md               the rules an agent reads on its own; the only other file at the root that is not code
  run.py                  the one command: run one or several named settings of one workflow file; ls, where, find, free,
                          kill, sync, selfcheck. Edited when a subcommand is added or the stage walk changes. Nothing
                          else is added at the root; the outputs root is named in constants/path_outputs.yaml only and
                          printed by run.py where

  constants/              where things are on this cluster: datasets, outputs, weights. Set once, correct; read by
                          code, nothing here changes a result or enters a key. Edited when something arrives or
                          moves on disk; a path may change only for the same bytes at a new place, a new set of
                          weights is a new alias in models/table.yaml
    path_datasets.yaml      where each environment, its task splits and each dataset live on this cluster
    path_outputs.yaml       where outputs go on NFS
    path_models.yaml        where each model's weights live

  experimental_settings/  everything in here changes a result. The YAML files are gyb's: a new kind of experiment
                          (a new stage combination) is a new file; a new experiment is a new named setting in a
                          file; a tuning is an edited value (the name then points at a new key, the old directory
                          stays). Agents read the YAML files and never edit them (a hook refuses); an agent proposes
                          a setting as a task instead. schema.py is code and is edited for a new hyperparameter
                          (with a default that reproduces the old behavior) or a new value on an axis
    schema.py               the schema of a setting: every field with its default and a one-line comment, the allowed
                            values of each axis, the stage table; and the loader that reads a YAML file against it
                            (file -> setting, diff, key). Edited before the YAML that needs the new field or value
    debug.yaml              only sizes: 3 tasks, 1 seed, 64 examples, 20 steps, 100 eval examples; never a model or a
                            tuning; --debug lays it over any setting
    baseline.yaml           workflow sample, score; named settings inside
    train_probe.yaml        workflow sample, build, train, eval; named settings inside
    inject.yaml             workflow inject, score; named settings inside
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
    environments/           one file per benchmark environment; this is the only place a new environment adds a file
      __init__.py           the contract and the entrance: class Environment declares the eight methods (tasks, open,
                            step, speculate, judge, close, plus the call syntax: split_args, build_call, complete_call)
                            with one line each and no logic; open_env(name) imports environments/<name>.py inside the
                            function, checks the eight methods are there, and returns the instance. The contract assumes
                            an environment that hands out tasks, steps, can try a call early and undo it, and judges
      appworld.py           class AppWorld(Environment): the eight methods on the AppWorld package, its task
                            instructions (the developer message), its no-code message, its call regex and Python call
                            syntax. Edited when AppWorld's interface or the instructions change; a changed instruction
                            changes results, so the file carries a VERSION that is bumped with it
                            adding an environment: this file's sibling, its clone and venv under external/, its path in
                            constants/path_datasets.yaml, its name on the data.env axis in schema.py, its README line;
                            then --debug on one setting with data.env set to it
    trajectory_record.py    the record one task run leaves: each step's prompt, reasoning, answer and observation, the
                            speculation events, the outcome, the seed, the commit; write, read, rebuild the conversation.
                            Edited when a field is added to the record
    training_data.py        the row build writes per probe example: the record and cut it came from, the text the probe
                            sees, the target (a label for ctool, a call for cgen, arguments for cparam); write, read. The
                            interface between build and train. Edited when a field is added to the row
    probe_output.py         the row train writes per example after training: the example id, its label, the score
                            (ctool) or the generated text (cgen, cparam); write, read. The interface between train and
                            eval. Edited when a field is added to the row
    probe_input.py          what the probe is asked and shown: the cut positions in the reasoning, and the text assembled
                            for the probe (the task, the clipped tool history, the thinking so far); one rule offline and
                            live. Edited when the cut rule or what the probe sees changes; environment text comes through
                            the environment object
    build_training_dataset.py  the program: records -> example rows for the three probe methods; the train/val/test split;
                            the report; the gates. Edited when how examples are made, the split or a gate changes; calls
                            are parsed through the environment object

  
  
  models/                 the models: the table, the agent-model side, the probe-model side. A model's own settings
                          (format, serving, tokenizer quirks) live here; a run's settings live in experimental_settings/
    __init__.py             the entrance: agent(name) and probe(name) read table.yaml and import the family's or backbone's
                            file inside the function. Edited never; a new model is a row, a new family or backbone a file
    table.yaml              the model table, one row per alias: role (agent or probe), family or backbone, where its
                            weights are named in constants/path_models.yaml, how it is served. A row's fields are
                            expanded into the setting before keying, so an edited row is a new key. Edited when a new
                            model alias is wanted; a model of an existing family or backbone needs only this row
    agent_models/           the agent model: one file per family (a family shares one conversation format), its service.
                            A new family (Qwen as the agent) adds a file here
      __init__.py           empty, so the client half of service.py imports without the family's libraries
      gptoss.py             gpt-oss's format ("harmony"): messages -> tokens, parse a reply, end of turn, the model's own
                            system message (date, effort). Edited when the format or that system message changes
      service.py            both ends of the served agent model: start or attach to the vLLM server for a table row and
                            check it (main, vllm venv); the loop's client, a raw token stream with a seed (standard
                            library). Edited when the serving flags or the client protocol change
    probe_models/           the probe model: the shared class, one file per backbone, its service. A new backbone
                            (Llama) adds a file here
      __init__.py           empty, so the client half of service.py imports without torch
      base.py               the probe class every backbone shares: load, save, score a prefix, generate a call; shared
                            before its third repetition because the folder exists for the backbones to come. Edited when
                            a shared action changes
      qwen.py               Qwen's tokenizer quirks, pad token, head attach point, LoRA target modules, dtype. Edited
                            when a Qwen-specific detail changes
      service.py            both ends of the probe service: the local HTTP server that loads the probe and answers score,
                            generate, encode, decode, with --check (main, probe venv); the loop's client (standard
                            library). Edited when the serving flags or the client protocol change
                            heavy imports in both service files sit inside the serving functions, so each file imports as any

  agent/                  the loop that runs the agent model on tasks. Nothing is added here; a new way to inject is an
                          entry in inject_format.py, a new injection mechanism is an edit to inject.py, and loop.py and
                          generate.py change for neither
    loop.py                 run each task and seed: open, step, parse, act, until done; claim tasks across pieces; write
                            the record. Picks the generation step by the setting: the inject section present ->
                            inject.step, absent -> generate.step; holds no probe code itself. Edited when task sharding,
                            claiming or what counts as done changes
    generate.py             the plain generation step: stream tokens from the agent model to end of turn; exposes the
                            token stream so inject.py iterates it instead of copying it. The baseline path. Edited when
                            the stop condition or the stream interface changes
    inject.py               the generation step with the probe: iterate generate's token stream, score at each cut, on
                            fire get the call, run it early through the environment, write the result in
                            (inject_format), start a new request from the spliced prefix, roll back on mismatch. Replaces
                            generate.step when the setting has an inject section. Edited when the mechanism changes
    inject_format.py        the table of the five ways an early result is written into the stream; schema's
                            inject.format axis reads its keys, so a sixth way is one entry here and a YAML line, nothing
                            else

  train/                  train a probe. A training hyperparameter is a YAML line; a new training practice (a tuning, an
                          optimizer) is a schema.py value plus an edit to trainer.py; a new probe method is a file under
                          methods/ plus a schema.py value
    utils/
      trainer.py            the training loop every method shares: settings -> arguments, seed, backbone, tuning (full or
                            LoRA), checkpoints, metrics, heartbeat, resume, the alignment gate; and its last step, the
                            probe run over val and test with one prediction row per example written to disk (the probe is
                            still on the card). A directory with the checkpoint and no predictions is continued from
                            that step. Edited when a shared step changes
    methods/                one file per probe method, each complete on its own: its batches or packing, its target, its
                            loss, its validation metric; the files do not import each other, so a fix in one is repeated
                            in the other and the alignment test, run per method, catches the one that was missed
      ctool.py              the classification probe: its batches, its head, its loss, its validation accuracy
      cgen.py               the call-generating probe: its packing, its instance strings and target, its loss positions,
                            its exact-match validation
      cparam.py             the argument-generating probe: its own packing and strings, the arguments as the target

  eval/                   reads what is on disk and computes numbers; no GPU, no torch, every file imports as any. A new
                          probe method is a file under methods/; a new metric is an edit to the file that reports it
    utils/
      probe_eval.py         shared by the three methods: read a train run's prediction rows and labels, bootstrap the
                            confidence interval, write the report. Edited when the report or the interval method changes
    methods/                one file per probe method, the metric computed from prediction rows; train/methods/<name>.py
                            calls this file's match function for its validation metric, never its own copy
      ctool.py              fit theta on the val rows at the risk targets, freeze it, report on the test rows
      cgen.py               exact match of the generated call at the frozen theta
      cparam.py             exact match of the generated arguments at the frozen theta
    score_run.py            a sample or inject run from its records: task success, speculation outcomes, tokens and time;
                            by seed; against a baseline. Edited when a metric is added
    method_table.py         the backbone x method table from the registry; groups sweep children, reports mean and spread.
                            Edited when the table's shape changes

  jobs/                   a job is one stage run on cards: the code that starts it and records it, and the record itself.
                          Nothing is added here; batch runs (a sweep, one method over several datasets, several seeds
                          over several models) are the sweep keyword in a setting, not a script
    launch.py               pick free cards, one tmux session per piece, the record's start, the alive check, refire.
                            Edited when card picking, the tmux start, the alive check or the refire rule changes
    registry.py               the registry: runs.jsonl rows under a lock, meta.json, the heartbeat, ls/where/find/kill,
                            RESULTS.md. Every stage imports it to write its start and finish rows; run.py imports it for
                            the subcommands. Both halves are standard library; the day ls or kill needs more, the
                            subcommand half becomes registry_cli.py. Edited when a row's fields, the heartbeat or a
                            subcommand's output changes
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


Python files: 34 (root 1, experimental_settings 1, data 8 counting the two
`__init__.py`, models 8 counting the three `__init__.py`, agent 4, train 4,
eval 6, jobs 2); tests 0 for now. Today: about 60 under the code directories.

## Decisions of the 2026-09-17 walk

Settled, in tree order: `constants/` holds locations only and `gpu_state.md`
moves to the gpu-run skill; `settings/` is `experimental_settings/` and
`shape.py` is `schema.py`; environments get their own folder with a base
class that declares eight methods, and call syntax is the environment's;
`envs/` is `external/`; `models/agents/` and `models/probes/` are
`agent_models/` and `probe_models/`; the inject step replaces the plain
generation step instead of switching inside it, and `speculate.py` folds
into `inject.py`; each probe method is one complete file in `train/methods/`
and `eval/methods/`, with no "generating probes" grouping and no shared
packing; the three on-disk formats (record, example, prediction) are defined
in `data/`, read into Polars, records as jsonl and the other two as parquet;
`scripts/` and `ledger/` merge into `jobs/` and the ledger is the registry;
tests are deferred; the root keeps README, CLAUDE.md and run.py, and gyb's
documents move to `notes/`.

Dropped: `train/utils/packing.py` and `reference.py` (per-method packing;
the row-by-row loss lives in the deferred test); `data/call_syntax.py` (the
environment's); `data/environment.py` (now `environments/__init__.py`); the
`outputs` symlink at the root (one home for the outputs root,
`constants/path_outputs.yaml`); batch-run scripts (the `sweep:` keyword and
several setting names on one `run.py` call cover them).

Open, for gyb: whether the read-only hook also covers `models/table.yaml`,
whose rows enter the key like a setting does.

Next: rewrite Part 2 (one section per module: what it does, what it reads,
which venv, which of today's files fold into it) against this tree, then the
migration steps and the README text.
