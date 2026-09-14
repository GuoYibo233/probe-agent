# new1 from zero: the file structure and the modules

Written 2026-09-14 from gyb's principles in `plans/2026-09-13-tree-review-fable.md`.
This plan holds two things only: the file structure and the modules. Migration
steps, the README text and the root documents come later.

The principles the tree follows, in the order gyb gave them:

1. One experiment is one settings file. The file holds every hyperparameter and
   the workflow (which stages run). The whole repo exists to run such a file.
2. Every run is reproducible. Same settings, same output directory: a finished
   output is reused, a partial one is continued, a changed one gets a new
   directory. Outputs stay retrievable after the code changes, through version
   numbers.
3. Short, standard layers: `data`, `models`, `agent`, `train`, `eval`, `scripts`.
   Settings control their arguments.
4. `--debug` runs any experiment tiny: the smallest model, a few tasks, a few
   steps.
5. No copies of almost the same file and no framework: a piece of code becomes
   shared on its third repetition, and only when it has stopped changing.
6. Each file does one thing that its name says, so the file to edit is found
   by name. The README lists every file with that one line.

---

## Part 1. The file structure

```
new1/
  README.md               for the future reader: the tree below, one line per file, and how to run
  CLAUDE.md  TRAPS.md  METHOD.md  DATA.md  WORKPLAN.md  TIMELINE.md  RESULTS.md
                          root documents, reviewed by gyb by hand later; untouched by this plan
  run.py                  the one command: run an experiment file, or ask where/find/ls/watch/selfcheck

  settings/               everything written by hand
    config.py               the shape of an experiment (every field with its default) and how a file becomes one
    paths.yaml              where things are on this cluster: the outputs root on NFS, the weights root, AppWorld
    a path_datasets yaml for datasets 
    a path_outputs yaml for output

    models.yaml             the model table: each agent model and probe backbone, its weights, template, how it is served
    path_models
    
    debug.yaml              the tiny overlay that --debug merges on top of any experiment
    is this necessary? what is in this. i mean debug is just a subset of normal settings, which containse super small models and number of data


    experiments/            one YAML per experiment; the file name is the experiment name
      baseline_gptoss.yaml
      probe_ctool_qwen06.yaml

      it is weird. what does this define? and if i update the baseline, what will it be?
      and ctool qwen 06 is the exact settings. use baseline and train probe as two files, do not include exact setting in file name.
      save settings in the file.
      for example
      in baseline.yaml, there are multi settings:
      - gpt-oss-120b appworld
      - qwen3.8 alfworld
      when running a program, i can set which baseline i want


    presets/                YAML blocks an experiment may `include`; created on the third repetition, not before
    what is this? i mean every experiment is a preset


  data/                   the environment, the record of a run, and the dataset built from records
    appworld.py             the AppWorld environment: tasks per split, reset, step, save, restore, judge, its system prompt
    trajectory.py           the record of one task run: what the model saw, wrote and got back, step by step; read and write
    rules.py                how the text of a record is read: cut points, the call syntax, argument splitting; pure, one copy
    build.py                records -> examples for the three probe methods, the split, the report, the gates
file names here is not clear, hard to read. rules.py trajectory.py they are unclear, what are these?



  models/                 the two models: how each is loaded, prompted and served
    template_gptoss.py      the gpt-oss conversation format (its name is "harmony"): render, parse the stream, end of turn
    agent_model.py          the client to the served agent model: a chat request, or a raw token stream
    probe.py                the probe model: backbone plus head; load, score a prefix, generate a call
    serve_agent.py          start the vLLM server for a model table row and run its checks, including render-equals-server
    serve_probe.py          the probe as a local HTTP service for the agent loop, with --check




  agent/                  the loop that runs the agent on tasks; the probe is a switch inside its generation step
    loop.py                 run each task and seed: reset, generate, parse, step, until done; write the record
    generate.py             one generation step: stream tokens; stop at end of turn, or when the probe fires (switch on)
    speculate.py            after the probe fires: get the call, run it early, splice the result in, resume; roll back on mismatch
    inject_format.py        the injection-format table: the five ways an early result is written into the stream

  train/                  train a probe
    train.py                one trainer for ctool, cgen and cparam: the method is a settings value; checkpoints; --check alignment
    
    batches.py              examples -> packed batches; the instance strings and their constants
    reference.py            the row-by-row loss for cgen and cparam that the alignment check compares the packed loss against
    batches and references unclear, and this is not for everyexperiment, and this is run before actually training, so like pro-process. if this is related to exp setting, it can change the result, put it into train.py if not, use a new file to save all those not important things. if something only need to be checked once, put it in to tests

    lora.py                 the tuning axis: full or LoRA; merge for evaluation
    what is this? lora is the same as train, right? what's its difference from train?

  eval/                   score a probe or a run
    eval_probe.py           a trained probe offline: fit theta on val at the risk targets, freeze it, report on test
    score_run.py            a sample or inject run: task success, speculation outcomes, tokens and time; by seed; against a baseline
    matrix.py               the backbone x method table from the ledger

  scripts/                the programs that are not a stage: put a run on cards, watch it, record it
  there are nvitop right? is it necessary to use extra method
    launch.py               free cards, one tmux session per piece, the registrations, the alive check, refire
    monitor.py              read-only: heartbeats -> verdicts, the terminal table, the web page
    heartbeat.py            the progress protocol every stage writes; standard library only
    ledger.py               the record: runs.jsonl, meta.json, jobs.json, find/ls/where, the RESULTS.md render

  ledger/                 the records kept in git
    runs.jsonl              one row per stage run, appended at start and at finish; never edited
    RESULTS.md              rendered from runs.jsonl; never edited by hand
    jobs.json               the live GPU jobs; written by launch.py, read by monitor.py; ignored by gitra
    gpu_state.md            cluster notes written by hand: drivers, CUDA, pitfalls

  tests/                  one test per contract
    test_config.py          defaults fill in, diff and key are stable when a defaulted field is added
    test_rules.py           cut points and call parsing on recorded text
    test_template.py        template render equals the server's tokens (vllm environment)
    test_inject_format.py   the five formats on one fixed example
    test_alignment.py       packed loss equals the reference loss on CPU with the debug model
    test_ledger.py          a row survives a start, a finish and a relaunch

  notebooks/              no, it should not refer to the code above

  figures/                one script per figure; empty until the first figure exists

  envs/                   the three uv environments (agent, probe, vllm) and their lock files; the AppWorld clone stays here
  plans/  docs/  .claude/ as today
```

Python files: 26 (root 1, settings 1, data 4, models 5, agent 4, train 4,
eval 3, scripts 4). Today: about 60 under the code directories.

Outputs live on NFS only, under `<outputs root>/<stage>/<experiment>__<key>/`
(key explained in Part 2). Debug runs go under `<outputs root>/debug/`.

### How an experiment runs

`python run.py settings/experiments/probe_ctool_qwen06.yaml` loads the file,
walks its `pipeline` list stage by stage, and for each stage computes the key,
looks for the output directory, and then skips it (finished), continues it
(partial), or runs it (missing). A CPU stage runs at once. A GPU stage is handed
to `scripts/launch.py`, which starts its pieces on cards and registers them;
the walk stops there and the same command continues it later. Every stage run
leaves one directory with its resolved settings, its metadata and its outputs,
and one row in the ledger.

### What keeps the tree this shape
Better to write a way to review and set a task, review the code base with an agent every 2 days.

Checked by `python run.py selfcheck`:

1. Every Python file starts with `# env: agent | probe | vllm | any`. Selfcheck
   imports each file under its environment, and a file marked `any` under all
   three.
2. A file marked `any` imports only the standard library at module top. Heavy
   packages are imported inside the function that needs them.
3. One home per fact. The call syntax lives in `data/rules.py`, the system
   prompt in `data/appworld.py`, model addresses in `settings/models.yaml`,
   cluster paths in `settings/paths.yaml`. Selfcheck fails when a listed name
   is assigned in a second file.
4. No absolute path in code. `/home/` and `/net/` appear only in
   `settings/paths.yaml` and `settings/models.yaml`.
5. Layers import downward only: `agent`, `train`, `eval` import from `data`
   and `models`; `models` imports from `data`; `scripts` imports from
   `settings`; `data` imports nothing from the repo. Selfcheck builds the
   import graph and fails on any other edge.
6. Every tracked Python file appears in the README tree with its one line.
   Selfcheck fails on a file that is missing there.

Two rules for people, not for selfcheck: code is shared on its third
repetition, and only when it has stopped changing; a stage's `VERSION` is
bumped when its output changes meaning for the same settings, and only then.

---

## Part 2. The modules

Each module below: what it does, what it offers, which settings it reads,
which environment imports it, and which of today's files fold into it. Files
not named anywhere in this part are deleted; git keeps them.

### `run.py` (any)

The one command. `run.py <experiment.yaml> [key=value ...] [--debug]
[--stage <name>] [--launch]` loads the experiment and walks its pipeline as
described above; without `--launch` a GPU stage's command is printed instead
of started. `run.py where <experiment> <stage>` prints the output directory.
`run.py find key=value ...` prints ledger rows whose settings match.
`run.py ls [stage]` prints the table of runs. `run.py watch`, `run.py free`
and `run.py jobs` are the monitor. `run.py selfcheck` runs the six checks.

`run.py` holds one table, `STAGES`: for each of the six stages, the pieces to
start (a stage is one or more processes), the environment of each piece, and
whether it needs cards. Sample and inject start the agent server, the probe
service (inject only) and the loop; train and eval start one process; build
and score run in place. About 200 lines.

Replaces `run.py` (1300 lines: the task registry, the recipe engine, the
dirty gate, which stays as one function), `pipeline/driver.py` (the fifteen-step
chain), `sweep_preset.py`.

### `settings/config.py` (any)

The shape of an experiment and how a file becomes one.

**Format.** YAML files, read with OmegaConf (version 2.3: one small package
with PyYAML underneath, no Hydra). The shape is a set of dataclasses in this
file, one per section, every field with a default and a one-line comment. An
experiment file lists only the fields that differ from the defaults. Loading
merges, in order: the dataclass defaults, the files named in `include`, the
experiment file, the command-line overrides `section.field=value`, and, with
`--debug`, `settings/debug.yaml`. A key that is not in the shape fails
loading, so a typo cannot pass as a new hyperparameter. `${probe.backbone}`
style references work inside a file.

Why OmegaConf alone: it gives the four things that matter (merge, typed
defaults, overrides, references) in one package that installs in seconds into
all three environments. Hydra is a framework on top of it (its own working
directory, output layout, config groups, launchers) and would fight the
identity rule below; it can be added later on the same objects if sweeps ever
need it. JSON was rejected for lacking comments; YAML is what a future reader
expects here.

**Adding a hyperparameter.** Add one field with a default that reproduces
the old behavior. No experiment file changes, and the resolved settings saved
in every run directory show the effective value. When the old behavior cannot
be the default, bump the `VERSION` of the stage that reads the field.

**The experiment file.** Six stages exist: `sample`, `build`, `train`,
`eval`, `inject`, `score`. Each appears at most once in a pipeline and has a
section of its own name. Three sections are shared: `models`, `generation`,
`probe`.

```yaml
name: probe_ctool_qwen06          # same as the file name
notes: first ctool probe on the 0.6B backbone, temperature 1.0 data
pipeline: [sample, build, train, eval, inject, score]

models:
  agent: gptoss20b                # a row of settings/models.yaml
  probe: qwen06                   # a row of settings/models.yaml
generation:                       # how the agent model generates, server and client side
  temperature: 1.0
  date: 2026-08-06                # the date written into the prompt
probe:                            # what the probe is
  method: ctool                   # ctool | cgen | cparam
  tuning: full                    # full | lora
sample:                           # run the agent with the probe off and record
  split: train
  traj_per_task: 3
  seeds: [42, 67, 4267]
build:
  traj_per_task: 3
train:
  lr: 1.0e-5
  epochs: 1
  seed: 42
eval:
  risk: [0.10, 0.05]
inject:                           # run the agent with the probe on
  split: test
  theta: 0.9
  format: p1_e1
  seeds: [42]
score:
  baseline: baseline_gptoss       # the experiment whose sample run is the comparison
```

A baseline is the short form of the same file:

```yaml
name: baseline_gptoss
pipeline: [sample, score]
models: {agent: gptoss20b}
sample: {split: test, seeds: [42]}
```

When a stage's upstream is not in the pipeline, the section names the
experiment that has it: `inject.probe: probe_ctool_qwen06` uses that
experiment's trained probe, `score.baseline` as above. The ledger resolves the
name to the directory.

| stage | code | environment | cards | reads | upstream |
|---|---|---|---|---|---|
| sample | agent/loop.py, models/serve_agent.py | agent, vllm | yes (server) | models.agent, generation, sample | none |
| build | data/build.py | any | no | build | sample |
| train | train/train.py | probe | yes | models.probe, probe, train | build |
| eval | eval/eval_probe.py | probe | yes | probe, eval | train |
| inject | agent/loop.py, models/serve_agent.py, models/serve_probe.py | agent, vllm, probe | yes | models, generation, probe, inject | train |
| score | eval/score_run.py | any | no | score | inject or sample |

**Identity, reuse, versions.** Each stage run has a key: twelve characters of
a hash over the stage's own section and the shared sections it reads (only
the values that differ from the defaults), the keys of its upstream stages,
and the stage's `VERSION`. The output directory is
`<outputs>/<stage>/<experiment>__<key>`, named by the experiment that created
it; a later experiment with the same key finds it through the ledger and uses
it without a copy. A directory whose `meta.json` says done is skipped. A
partial one is continued: sample and inject are collections of task files, one
per task and seed, so only the missing files run, and asking for more tasks or
seeds adds files to the same directory (the task list and the seed list are
left out of the key on purpose); train continues from its last checkpoint;
build, eval and score are quick and start over. `VERSION` is an integer at the
top of each stage's file; because it is part of the key, old outputs stay
valid under their version and a changed stage never reuses them by accident.
Eval's key holds its own `VERSION` and the key of the probe it scores. The
git commit is recorded in `meta.json`, not keyed, so a refactor that changes
no output keeps every output valid.

Every run directory holds `config.yaml` (resolved, everything), `diff.yaml`
(what differs from the defaults: the identity, and the human summary),
`meta.json` (key, version, commit, dirty files, host, cards, command, start,
end, status), `log.txt`, `heartbeat.json`, `metrics.jsonl`, and the stage's
outputs.

**Debug.** `settings/debug.yaml` sets the smallest probe backbone, three
tasks, one seed, 64 examples, 20 steps, 100 evaluation examples. Every stage
reads these limits from its section, so a debug run and a real run take the
same code path. Debug outputs go under `<outputs>/debug/` and are not written
to the ledger. This replaces `pipeline/train/demo/` and its CPU fixtures.

**Logs and tracking.** `log.txt` and `metrics.jsonl` in the run directory are
the record, and `run.py ls`, `find` and `where` read the ledger; nothing else
is needed to retrieve a run. Recommended viewer, switched on by
`logging.tracker: wandb` (default `none`): Weights & Biases, with the run
named `<experiment>/<stage>`, `diff.yaml` as its config and `metrics.jsonl`
mirrored. It has a free academic plan, works in a phone browser, and compares
runs by any settings field; offline mode plus a later sync covers nodes
without network. MLflow with a file store on NFS is the self-hosted
alternative behind the same switch. The tracker is a mirror; losing it loses
nothing.

Offers: `load(path, overrides, debug)`, `diff(cfg)`, `key(cfg, stage,
upstream_keys)`, `save(cfg, run_dir)`. Reads `paths.yaml` and `models.yaml`
for the `paths` and `models` lookups. Replaces `preset_loader.py`,
`model_registry.py`, `configs/models.json`, `configs/presets/`,
`pipeline/configs/`, the manifests in `pipeline/collect/`, and the tables in
`run.py`.

### `data/appworld.py` (agent)

The AppWorld environment behind five methods: `tasks(split)`, and for one
task `reset()` (the instruction and the tool documentation the agent sees),
`step(call)` (run the call, return the observation), `save()` and
`restore()` (the snapshot the speculation rolls back to), `judge()` (did the
task succeed). Also the system prompt and the message the agent gets when it
writes no code, because those are the environment's words. The loop never
contains environment code; a second environment is a second file with the
same five methods, and a shared base class waits for the third.

Reads `paths.appworld`. Replaces the world half of `envs/collect/run_appworld.py`,
`pipeline/inject/exec_calls.py`, the system prompt copy in `rebuild.py`, and
the three copies of `APPWORLD_HOME`.

### `data/trajectory.py` (any, standard library)

The record of one task run, step by step: what the model saw, what it wrote
(reasoning and answer), what came back, the speculation events when the probe
was on, the final judgement, and the seed. Offers `write`, `read`, and
`to_messages()`, which rebuilds the conversation exactly as the model saw it;
the loop uses it live and the builder uses it offline, so there is one
convention. Replaces the trajectory log in `envs/collect/common.py`, the
record readers in `rebuild.py` and `exec_calls.py`, `extract_completed.py`.

### `data/rules.py` (any, standard library, pure)

How the text of a record is read: cut points in the reasoning (where the
probe is asked), the one regular expression for a tool call, argument
splitting, `make_call`, `complete_call`, and the prompt assembly of one
example. Reads and writes no files. Today the call regex has three copies and
the argument splitter three; this file is the one home. Replaces
`pipeline/annotate/rules.py`, `pipeline/inject/parse_call.py`, the parser copies
in `eval_causal_call.py` and `eval_causal_param.py`, the regex in
`score_live.py`.

### `data/build.py` (any)

Records to examples: for each cut point, the example each method learns from
(ctool: will a call come; cgen: the call; cparam: its arguments), the split by
task into train, val and test, the report, and the gates that today live in
`check_callstr.py`. Reads `build`. Has a `VERSION`. Replaces
`pipeline/annotate/build.py`, `check_callstr.py`, `envs/collect/build_dataset.py`;
`param_label.py` and `readonly/` are dropped with the read-only feature.

### `models/template_gptoss.py` (any at import; render needs the probe environment)

The gpt-oss conversation format, whose name is "harmony": `render(messages)`
gives the prompt tokens exactly as the server renders them, `parse(text)`
splits a streamed reply into reasoning, answer and call, and `end_of_turn`
says where a reply ends. `settings/models.yaml` names the template for each
model (`template: gptoss`); when Qwen becomes an agent model,
`template_qwen.py` is a second file with the same three functions and a
second table row. The rendering library is imported inside `render`, so the
agent environment can import the file for parsing. Replaces
`pipeline/inject/harmony_render.py` and the stream parsing in
`live_appworld.py` and `common.py`.

### `models/agent_model.py` (agent)

The client to the served agent model: `chat(messages, generation)` (the
server renders the prompt; used with the probe off) and `stream(prompt_ids,
generation)` (a raw completion returning tokens as they arrive; used with the
probe on, because the probe needs the exact prefix). One seed per request.
The OpenAI client is imported inside the functions. Reads `generation`.
Replaces the request rows of `envs/collect/common.py` and the request half of
`live_appworld.py`.

### `models/probe.py` (probe)

The probe model: a small backbone from the model table plus, for ctool, a
classification head, and for cgen and cparam, the backbone's own generation.
Offers `Probe.load(dir)`, `save(dir)`, `score(prefix_ids)` (the probability
that a call is coming), `generate_call(prefix_ids)` (greedy, cut at the first
newline). One class shared by the trainer, the evaluator and the probe
service; today the loader exists three times and the generation contract four
times. Reads `models.probe`, `probe`. Replaces `CausalProbe` in
`train_causal_tool.py`, the loaders in `eval_tool.py`, `probe_server.py` and
`check_bundle.py`, the generation copies.

### `models/serve_agent.py` (vllm)

Start the vLLM server for a model table row with the generation settings
(the prompt date, the reasoning effort), wait for health, then run the check
table: health, and render-equals-server (the template's tokens for one
conversation equal the server's). `stop` ends it. The date is a settings value,
so the two arms of a comparison always share it; the old constant goes.
Reads `models.agent`, `generation`. Replaces `serve_preset.py`, the seventeen
`launch_vllm_*.py` under `envs/serve_logs/`, `ident3_gate.py`, `ident3_score.py`,
`run_gptoss.sh`.

### `models/serve_probe.py` (probe)

The probe as a local HTTP service: score, generate, render, encode, decode,
health; `--check` proves a trained probe loads and answers before a launch.
Why a service: the loop runs in the agent environment (AppWorld's pins) and
the probe in the probe environment (torch, transformers, the renderer); the
two cannot share a process, so the loop reaches the probe and the tokenizer
through this one door. Reads `models.probe`, `probe`. Replaces
`pipeline/inject/probe_server.py` (its dead self-test deleted) and
`check_bundle.py`.

### `agent/loop.py` (agent)

Run each requested task and seed: `reset`, then repeat generate, parse,
`step`, append, until the turn ends or the step limit is reached; write the
record; skip a task-and-seed whose file exists; write heartbeats. It runs a
sample (probe off) and an inject (probe on) alike; the difference is the
switch that `generate.py` reads. It calls the environment's five methods and
nothing else of it. Reads `sample` or `inject`, `generation`. Has a
`VERSION` (the record format). Replaces the loop half of `run_appworld.py`,
`run_task` and `main` of `live_appworld.py`, `live_arm_job.sh`,
`live_smoke_job.sh`, `live_v3_job.sh`, `splice_client.py`,
`launch_splice_clients.py`.

### `agent/generate.py` (agent)

One generation step. Probe off: one chat request. Probe on: a token stream,
and at each cut point of the reasoning (from `rules.cut_points`) a score from
the probe service; the stop condition of the stream is "end of turn, or the
probe fired" (score at or above `theta`). Returns the text and, when it
fired, the cut position and the score. The link to the probe service (score,
generate, render, encode, decode over HTTP, standard library only) is a small
class at the top of this file. Reads `probe`, `inject.theta`, `generation`.
Replaces `gen_step`, `find_head` and the service calls of `live_appworld.py`.

### `agent/speculate.py` (agent)

What happens after the probe fires: ask the service for the call, `save` the
environment, `step` the call early, write its result into the stream in the
chosen format, splice it at the cut, resume generation; when the model's own
call turns out different, `restore` and run the real call. Records every
speculation event (fired, matched, rolled back) into the trajectory. Reads
`inject.format`. Replaces the speculate, splice and resume parts of
`live_appworld.py`, `replay_inject.py`, `splice_replay.py`.

### `agent/inject_format.py` (any, standard library)

The injection-format table: `note`, `p1_e1`, `p1_e2`, `p2_e1`, `p2_e2`; each
row says how an early result is written into the stream. Unchanged from
`pipeline/inject/inject_format.py`.

### `train/train.py` (probe)

One trainer for the three methods. The method is a settings value and picks
one row of a small table (which batches, which loss); everything else is the
same code: arguments from settings, seed, backbone from the model table,
tuning through `lora.py`, packed batches from `batches.py`, checkpoints
`best/` and `last/`, `metrics.jsonl`, heartbeats, continue from `last/` when
the directory is partial. `--check alignment` compares the packed loss with
the reference loss on a few batches. Has a `VERSION`. Reads `models.probe`,
`probe`, `train`. Replaces `train_causal_tool.py`, `train_causal_share.py`,
`sweep_lr.py`, and the mbert trainers.

### `train/batches.py` (probe)

Examples to packed batches: the instance strings of cgen and cparam (the
prompt tail, the target, the separator, the length caps live here, in one
place), the ctool examples as tensors, the cache-reuse packing. Reads
`train`. Replaces `share_data.py` and the constants the row-wise trainers
own today.

### `train/reference.py` (probe)

The row-by-row loss for cgen and cparam, computed the slow way, that
`train.py --check alignment` compares the packed loss against. No training
loop, no fire head. Imports its constants from `batches.py`. Replaces
`train_causal_callgen.py` and `train_causal_param.py`.

### `train/lora.py` (probe)

The tuning axis: `full` trains every weight, `lora` trains adapters; peft is
imported inside; `merge` for evaluation. Reads `probe.tuning`. Replaces
`lora_util.py`.

### `eval/eval_probe.py` (probe)

Score a trained probe offline. ctool: fit `theta` on val at each risk target,
freeze it, report precision, recall and lead time on test. cgen and cparam:
exact match of the generated call at the ctool threshold. Writes
`report.json`. Has a `VERSION`. Reads `probe`, `eval`. Replaces `eval_tool.py`,
`eval_causal_call.py`, `eval_causal_param.py`, `eval_mbert_call.py`, the
self-fire block.

### `eval/score_run.py` (any)

Score a sample or inject run from its records: task success, calls speculated,
matched and rolled back, tokens and wall time; grouped by seed with mean and
spread; an inject run paired with its baseline run task by task and seed by
seed. Writes `report.json`. Has a `VERSION`. Reads `score`. Replaces
`score_live.py`, `envs/collect/score_probe.py`, `summarize_full.py`,
`acceptance.py`, `sweep_theta.py`.

### `eval/matrix.py` (any)

The backbone times method table from the eval reports in the ledger, as
markdown. Reads nothing but the ledger. Replaces `summarize_matrix.py` and the
`MATRIX_*.md` files under `pipeline/runs/`.

### `scripts/launch.py` (any)

Put a stage's pieces on cards: probe the free cards, one tmux session per
piece, the registrations through `ledger.py`, the alive check, refire of a
dead piece. Which pieces a stage has comes from `run.py`'s `STAGES` table.
Also `free`. Replaces `launch_cmd.py`, `launch_common.py`, `launch_probe.py`,
`launch_eval.py`, `pipeline/collect/gen_launch.py`, the placement JSON files
under `ops/`, the launch scripts under `envs/serve_logs/`.

### `scripts/monitor.py` (any)

Read-only: read heartbeats, judge each piece (alive, stalled, dead, done),
print the terminal table, serve the web page. Replaces `sampler.py` (its
incident half deleted), `verdicts.py`, the read side of `gpu_jobs.py`.

### `scripts/heartbeat.py` (any, standard library)

The progress protocol every stage writes. Unchanged from `ops/heartbeat.py`.

### `scripts/ledger.py` (any, standard library)

The record: append a row to `ledger/runs.jsonl` at start and at finish (key,
stage, experiment, directory, status, commit, dirty files, version,
`diff.yaml`, the summary numbers), write `meta.json`, register and release in
`jobs.json`, resolve an experiment name to a directory, `find`, `ls`,
`where`, render `RESULTS.md`. One git probe, one set of ledger paths.
Replaces `record.py`, `runmeta.py`, the write side of `gpu_jobs.py`, the
three copies of the ledger paths.

### Not carried over

The read-only feature and the fire head (`readonly/`, `readonly_map.py`,
`param_label.py`, the fire head in `train_causal_callgen.py`, `--self-fire`),
per gyb's answer of 2026-09-13. The other-environment runners under
`envs/collect/` and their split generators. The mbert line. The theta and
plan sweeps, the acceptance scripts and the one-off checks under
`pipeline/inject/`, `.scratch/kvshare-train/verify/`. The fifteen-step chain
and its test. The dead self-test of the probe service. Each comes back from
git if a result needs it.
