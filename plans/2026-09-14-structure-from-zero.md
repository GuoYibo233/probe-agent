# new1 from zero: the file structure and the modules

Second draft, 2026-09-14. The first draft with gyb's comments is commit
`c859aaa`; every comment is answered in the text below. This plan holds two
things only: the file structure and the modules. Migration steps, the README
text and the root documents come later.

The principles the tree follows, in the order gyb gave them:

1. One experiment is one setting. A setting holds every hyperparameter, and
   the file it lives in says which stages run. The whole repo exists to run a
   setting.
2. Every run is reproducible. Same setting, same output directory: a finished
   output is reused, a partial one is continued, an edited setting gets a new
   directory. Outputs stay retrievable after the code changes, through version
   numbers.
3. Short, standard layers: `data`, `models`, `agent`, `train`, `eval`,
   `scripts`. Settings control their arguments.
4. `--debug` runs any setting tiny: the smallest model, a few tasks, a few
   steps.
5. No copies of almost the same file and no framework: a piece of code becomes
   shared on its third repetition, and only when it has stopped changing.
6. Each file does one thing that its name says, so the file to edit is found
   by name. The README lists every file with that one line.

---

## Part 1. The file structure

```
new1/
  README.md               for the future reader: this tree, one line per file, and how to run
  CLAUDE.md  TRAPS.md  METHOD.md  DATA.md  WORKPLAN.md  TIMELINE.md  RESULTS.md
                          root documents, reviewed by gyb by hand later; untouched by this plan
  run.py                  the one command: run one setting of one workflow file; also ls, where, find, free, selfcheck

  constants/              written by hand; nothing in here changes a result
    path_datasets.yaml      where each environment and dataset lives on this cluster
    path_outputs.yaml       where outputs go on NFS
    path_models.yaml        where each model's weights live
    models.yaml             the model table: for each model, its family (which template) and how it is served

  settings/               written by hand; everything in here changes a result
    config.py               the shape of a setting: every hyperparameter with its default and a one-line comment; the loader
    debug.yaml              only the small values: the smallest models, 3 tasks, 1 seed, 64 examples, 20 steps;
                            --debug lays them over any setting, so no setting needs a small copy of itself
    baseline.yaml           workflow sample, score; named settings inside, for example gptoss120b_appworld, qwen3_8b_alfworld
    train_probe.yaml        workflow sample, build, train, eval; named settings inside, for example ctool_on_qwen06
    inject.yaml             workflow inject, score; named settings inside, for example ctool_qwen06_p1e1
                            a new workflow is a new file; a new experiment is a new named setting in a file

  data/                   the environments, the record a run leaves, and the dataset built from records
    appworld.py             the AppWorld environment behind five methods: tasks, reset, step, save and restore, judge;
                            also its system prompt
    task_record.py          the record one task run leaves: each step's prompt, reasoning, answer and observation, the
                            speculation events, the outcome, the seed; write it, read it, rebuild the conversation from it
    cut_points.py           where in the reasoning the probe is asked; the same rule offline (building examples) and live
    call_syntax.py          what a tool call looks like in text: the one regex, argument splitting, completing a cut-off call
    build.py                records -> examples for the three probe methods; the train/val/test split; the report; the gates
                            a second environment (alfworld) is a second file with the same five methods as appworld.py

  models/                 the two models: how each is loaded, prompted and served
    template_gptoss.py      gpt-oss's conversation format (its name is "harmony"): messages -> tokens, parse a reply, end of turn
    agent_model.py          the client to the served agent model: one chat request, or a raw token stream
    probe.py                the probe model: backbone plus head; load, score a prefix, generate a call
    serve_agent.py          start the vLLM server for a model with the generation settings; its checks (health, render-equals-server)
    serve_probe.py          the probe as a local HTTP service for the agent loop; --check
                            a second model family (Qwen) is template_qwen.py with the same three functions

  agent/                  the loop that runs the agent on tasks; the probe is a switch inside its generation step
    loop.py                 run each task and seed: reset, generate, parse, step, until done; write the record
    generate.py             one generation step: stream tokens; stop at end of turn, or when the probe fires (switch on)
    speculate.py            after the probe fires: get the call, run it early, splice the result in, resume; roll back on mismatch
    inject_format.py        the injection-format table: the five ways an early result is written into the stream

  train/                  train a probe
    train.py                the one trainer: the method (ctool, cgen, cparam) and the tuning (full, lora) are settings values;
                            packing examples into batches; checkpoints; continue from the last one

  eval/                   score a probe or a run
    eval_probe.py           a trained probe offline: fit theta on val at the risk targets, freeze it, report on test
    score_run.py            a sample or inject run: task success, speculation outcomes, tokens and time; by seed; against a baseline
    matrix.py               the backbone x method table from the ledger

  scripts/                start a run on cards and keep the record; card usage itself is watched with nvitop
    launch.py               pick free cards, one tmux session per piece, write the record's start, check alive, refire
    ledger.py               the record: runs.jsonl rows, meta.json, the heartbeat, ls/where/find, the RESULTS.md render

  ledger/                 the records kept in git
    runs.jsonl              one row per stage run, appended at start and at finish; never edited
    RESULTS.md              rendered from runs.jsonl; never edited by hand
    gpu_state.md            cluster notes written by hand: drivers, CUDA, pitfalls

  tests/                  one test per contract; a check that is needed once per code change lives here, not in a stage
    test_config.py          defaults fill in; the key is unchanged when a defaulted field is added
    test_cut_points.py      the cut rule on recorded reasoning
    test_call_syntax.py     the call regex, argument splitting and call completion on recorded text
    test_template.py        template render equals the server's tokens (vllm environment)
    test_inject_format.py   the five formats on one fixed example
    test_train_alignment.py the slow row-by-row loss against train.py's packed loss, on CPU with the debug model
    test_ledger.py          a row survives a start, a finish and a relaunch

  notebooks/              throwaway work; nothing in the tree depends on a notebook
  figures/                one script per figure; empty until the first figure exists
  envs/                   the three uv environments (agent, probe, vllm), their lock files, and the environment clones
  .claude/skills/repo-review/SKILL.md
                          the two-day review: an agent reads the tree against the six principles and writes tasks
  .scratch/review/issues/ the tasks the review writes, in the issue-tracker format already in use
  plans/  docs/  .claude/ as today
```

Python files: 22 (root 1, settings 1, data 5, models 5, agent 4, train 1,
eval 3, scripts 2). Today: about 60 under the code directories.

Outputs live on NFS only, under
`<outputs>/<stage>/<workflow file>/<setting>__<key>/` (the key is explained in
Part 2). Debug runs go under `<outputs>/debug/`.

### How a run is named and started

`python run.py baseline gptoss120b_appworld`: the first word is the workflow
file, the second the named setting inside it. The command loads the setting,
walks the file's stage list, and for each stage computes the key, looks for
the output directory, and then skips it (finished), continues it (partial), or
runs it (missing). A CPU stage runs at once. A GPU stage is handed to
`scripts/launch.py`, which starts its pieces on cards and writes the record;
the walk stops there and the same command continues it later. Every stage run
leaves one directory with its resolved settings, its metadata and its
outputs, and one row in the ledger.

### If you edit a setting

The key is computed from the setting's content, so editing a value gives the
next run a new directory; the old directory stays, with the settings it ran
under saved inside it, and `run.py ls baseline` shows both with what differs.
Editing the notes changes nothing. Adding a hyperparameter to the shape with
a default that reproduces the old behavior changes no key.

### What keeps the tree this shape

1. The two-day review. Every two days an agent runs the repo-review skill:
   it reads the tree against the six principles (one thing per file, no
   near-copies, one home per fact, imports only downward between layers,
   every file listed in the README with a true line) and writes one task per
   finding into `.scratch/review/issues/`. gyb triages the tasks.
2. `run.py selfcheck`, the three checks a machine does better than a reader:
   every Python file starts with `# env: agent | probe | vllm | any` and
   imports under that environment (a file marked `any` under all three, with
   only the standard library at module top); no `/home/` or `/net/` in code
   outside `constants/`; every tracked Python file appears in the README tree.
3. Two rules for people: code is shared on its third repetition, and only
   when it has stopped changing; a stage's `VERSION` is bumped when its
   output changes meaning for the same settings, and only then.

---

## Part 2. The modules

Each module below: what it does, what it offers, which settings it reads,
which environment imports it, and which of today's files fold into it. Files
not named anywhere in this part are deleted; git keeps them.

### `run.py` (any)

The one command. `run.py <workflow> <setting> [section.field=value ...]
[--debug] [--stage <name>] [--launch]` loads the setting and walks the
workflow's stages as described above; without `--launch` a GPU stage's command
is printed instead of started. `run.py ls [workflow]` prints the table of runs
with status (done, failed, alive with the heartbeat's age, stalled). `run.py
where <workflow> <setting> <stage>` prints the output directory. `run.py find
section.field=value ...` prints the ledger rows whose settings match. `run.py
free` prints the free cards. `run.py selfcheck` runs the three checks.

`run.py` holds one table, `STAGES`: for each of the six stages, the pieces to
start (a stage is one or more processes), the environment of each piece, and
whether it needs cards. Sample and inject start the agent server, the probe
service (inject only) and the loop; train and eval start one process; build
and score run in place. About 200 lines.

Replaces `run.py` (1300 lines: the task registry, the recipe engine, the
dirty gate, which stays as one function), `pipeline/driver.py` (the
fifteen-step chain), `sweep_preset.py`.

### `settings/config.py` (any)

The shape of a setting and how a file becomes one.

**Format.** YAML files, read with OmegaConf (version 2.3: one small package
with PyYAML underneath, no Hydra). The shape is a set of dataclasses in this
file, one per section, every field with a default and a one-line comment. A
setting lists only the fields that differ from the defaults. Loading merges,
in order: the dataclass defaults, the file's `common` block, the named
setting, the command-line overrides `section.field=value`, and, with
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
the old behavior. No setting changes, and the resolved settings saved in
every run directory show the effective value. When the old behavior cannot be
the default, bump the `VERSION` of the stage that reads the field.

**A workflow file.** The file is the workflow: its `pipeline` line names
the stages, in order, from the six that exist (`sample`, `build`, `train`,
`eval`, `inject`, `score`), each at most once. Its `common` block holds what
every setting in the file shares. Every other top-level key is a named
setting. The sections of a setting are the six stage sections plus four
shared ones: `data` (which environment), `models` (which agent model, which
probe backbone), `generation` (how the agent model generates), `probe` (what
the probe is).

```yaml
# settings/train_probe.yaml: sample the agent, build the dataset, train a probe, score it
pipeline: [sample, build, train, eval]

common:
  data: {env: appworld}
  models: {agent: gptoss20b}
  generation: {temperature: 1.0, date: 2026-08-06}      # the date is written into the prompt
  sample: {split: train, traj_per_task: 3, seeds: [42, 67, 4267]}
  train: {epochs: 1, seed: 42}
  eval: {risk: [0.10, 0.05]}

ctool_on_qwen06:
  notes: first ctool probe on the 0.6B backbone
  models: {probe: qwen06}
  probe: {method: ctool, tuning: full}
  train: {lr: 1.0e-5}

cgen_on_qwen17_lora:
  models: {probe: qwen17}
  probe: {method: cgen, tuning: lora}
  train: {lr: 5.0e-4}
```

```yaml
# settings/baseline.yaml: run the agent alone and score it
pipeline: [sample, score]

common:
  sample: {split: test, seeds: [42]}

gptoss120b_appworld:
  data: {env: appworld}
  models: {agent: gptoss120b}

qwen3_8b_alfworld:
  data: {env: alfworld}
  models: {agent: qwen3_8b}
```

```yaml
# settings/inject.yaml: run the agent with a trained probe and score it against a baseline
pipeline: [inject, score]

common:
  inject: {split: test, seeds: [42], theta: 0.9}

ctool_qwen06_p1e1:
  inject: {probe: train_probe/ctool_on_qwen06, format: p1_e1}
  score: {baseline: baseline/gptoss20b_appworld}
```

When a stage's upstream is not in the file's pipeline, the section names the
run that has it, as `<workflow>/<setting>`: `inject.probe` names the training
run whose probe to use, `score.baseline` the baseline run to compare with. The
ledger resolves the name to the directory.

| stage | code | environment | cards | reads | upstream |
|---|---|---|---|---|---|
| sample | agent/loop.py, models/serve_agent.py | agent, vllm | yes (the server) | data, models.agent, generation, sample | none |
| build | data/build.py | any | no | build | sample |
| train | train/train.py | probe | yes | models.probe, probe, train | build |
| eval | eval/eval_probe.py | probe | yes | probe, eval | train |
| inject | agent/loop.py, models/serve_agent.py, models/serve_probe.py | agent, vllm, probe | yes | data, models, generation, probe, inject | train |
| score | eval/score_run.py | any | no | score | inject or sample |

**Identity, reuse, versions.** Each stage run has a key: twelve characters of
a hash over the stage's own section and the shared sections it reads (only
the values that differ from the defaults), the keys of its upstream stages,
and the stage's `VERSION`. The output directory is
`<outputs>/<stage>/<workflow>/<setting>__<key>`, named by the setting that
created it; a later setting with the same key (a probe setting whose sample
stage equals a baseline's, for instance) finds it through the ledger and uses
it without a copy. A directory whose `meta.json` says done is skipped. A
partial one is continued: sample and inject are collections of task files, one
per task and seed, so only the missing files run, and asking for more tasks
or seeds adds files to the same directory (the task list and the seed list
are left out of the key on purpose); train continues from its last
checkpoint; build, eval and score are quick and start over. `VERSION` is an
integer at the top of each stage's file; because it is part of the key, old
outputs stay valid under their version and a changed stage never reuses them
by accident. Eval's key holds its own `VERSION` and the key of the probe it
scores. The git commit is recorded in `meta.json`, not keyed, so a refactor
that changes no output keeps every output valid.

Every run directory holds `config.yaml` (resolved, everything), `diff.yaml`
(what differs from the defaults: the identity, and the human summary),
`meta.json` (key, version, commit, dirty files, host, cards, command, start,
end, status), `log.txt`, `heartbeat.json`, `metrics.jsonl`, and the stage's
outputs.

**Debug.** `settings/debug.yaml` is a setting with only the small values in
it: the smallest probe backbone, three tasks, one seed, 64 examples, 20
steps, 100 evaluation examples. `--debug` lays it over whichever setting is
run, so no setting needs a small copy of itself. Every stage reads these
limits from its section, so a debug run and a real run take the same code
path. Debug outputs go under `<outputs>/debug/` and are not written to the
ledger. This replaces `pipeline/train/demo/` and its CPU fixtures.

**Logs and tracking.** `log.txt` and `metrics.jsonl` in the run directory are
the record, and `run.py ls`, `find` and `where` read the ledger; nothing else
is needed to retrieve a run. Recommended viewer, switched on by
`logging.tracker: wandb` (default `none`): Weights & Biases, with the run
named `<workflow>/<setting>/<stage>`, `diff.yaml` as its config and
`metrics.jsonl` mirrored. It has a free academic plan, works in a phone
browser, and compares runs by any settings field; offline mode plus a later
sync covers nodes without network. MLflow with a file store on NFS is the
self-hosted alternative behind the same switch. The tracker is a mirror;
losing it loses nothing.

Offers: `load(workflow, setting, overrides, debug)`, `diff(cfg)`, `key(cfg,
stage, upstream_keys)`, `save(cfg, run_dir)`. Reads `constants/` for the
paths and the model table; nothing in `constants/` enters a key. Replaces
`preset_loader.py`, `model_registry.py`,
`configs/models.json`, `configs/presets/`, `pipeline/configs/`, the manifests
in `pipeline/collect/`, and the tables in `run.py`.

### `data/appworld.py` (agent)

The AppWorld environment behind five methods: `tasks(split)`, and for one
task `reset()` (the instruction and the tool documentation the agent sees),
`step(call)` (run the call, return the observation), `save()` and
`restore()` (the snapshot the speculation rolls back to), `judge()` (did the
task succeed). Also the system prompt and the message the agent gets when it
writes no code, because those are the environment's words. The loop never
contains environment code; a second environment is a second file with the
same five methods, chosen by `data.env`, and a shared base class waits for
the third.

Reads `constants/path_datasets.yaml`. Replaces the world half of
`envs/collect/run_appworld.py`, `pipeline/inject/exec_calls.py`, the system
prompt copy in `rebuild.py`, and the three copies of `APPWORLD_HOME`.

### `data/task_record.py` (any, standard library)

The record one task run leaves, step by step: what the model saw, what it
wrote (reasoning and answer), what came back, the speculation events when the
probe was on, the outcome, and the seed. Offers `write`, `read`, and
`to_messages()`, which rebuilds the conversation exactly as the model saw
it; the loop uses it live and the builder uses it offline, so there is one
convention. Replaces the trajectory log in `envs/collect/common.py`, the
record readers in `rebuild.py` and `exec_calls.py`, `extract_completed.py`.

### `data/cut_points.py` (any, standard library, pure)

Where in the reasoning the probe is asked: the rule that turns reasoning text
into the positions at which a probe may fire. `build.py` uses it offline to
make one example per position; `agent/generate.py` uses it live to ask the
probe at the same positions. One copy, so the probe is asked where it was
trained. Reads and writes no files. Replaces the cut rule in
`pipeline/annotate/rules.py` and its live copy in `live_appworld.py`.

### `data/call_syntax.py` (any, standard library, pure)

What a tool call looks like in text: the one regular expression that finds
a call, argument splitting, `make_call` (a call from its parts) and
`complete_call` (finishing a call that was cut off). Used by `build.py`,
`agent/speculate.py`, `eval/eval_probe.py` and `eval/score_run.py`. Today the
regex has three copies and the argument splitter three; this file is the one
home. Reads and writes no files. Replaces the call half of
`pipeline/annotate/rules.py`, `pipeline/inject/parse_call.py`, the parser copies
in `eval_causal_call.py` and `eval_causal_param.py`, the regex in
`score_live.py`.

### `data/build.py` (any)

Records to examples: for each cut point, the example each method learns from
(ctool: will a call come; cgen: the call; cparam: its arguments), the prompt
of the example, the split by task into train, val and test, the report, and
the gates that today live in `check_callstr.py`. Reads `build`. Has a
`VERSION`. Replaces `pipeline/annotate/build.py`, `check_callstr.py`,
`envs/collect/build_dataset.py`; `param_label.py` and `readonly/` are dropped
with the read-only feature.

### `models/template_gptoss.py` (any at import; render needs the probe environment)

The gpt-oss conversation format, whose name is "harmony": `render(messages)`
gives the prompt tokens exactly as the server renders them, `parse(text)`
splits a streamed reply into reasoning, answer and call, and `end_of_turn`
says where a reply ends. `constants/models.yaml` names the template for each
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
conversation equal the server's). `stop` ends it. The date is a settings
value, so the two arms of a comparison always share it; the old constant
goes. Reads `models.agent`, `generation`, `constants/path_models.yaml`. Replaces
`serve_preset.py`, the seventeen `launch_vllm_*.py` under `envs/serve_logs/`,
`ident3_gate.py`, `ident3_score.py`, `run_gptoss.sh`.

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
and at each cut point of the reasoning (from `data/cut_points.py`) a score
from the probe service; the stop condition of the stream is "end of turn, or
the probe fired" (score at or above `theta`). Returns the text and, when it
fired, the cut position and the score. The link to the probe service (score,
generate, render, encode, decode over HTTP, standard library only) is a small
class at the top of this file. Reads `probe`, `inject.theta`, `generation`.
Replaces `gen_step`, `find_head` and the service calls of `live_appworld.py`.

### `agent/speculate.py` (agent)

What happens after the probe fires: ask the service for the call, `save` the
environment, `step` the call early, write its result into the stream in the
chosen format, splice it at the cut, resume generation; when the model's own
call turns out different, `restore` and run the real call. Records every
speculation event (fired, matched, rolled back) into the record. Reads
`inject.format`. Replaces the speculate, splice and resume parts of
`live_appworld.py`, `replay_inject.py`, `splice_replay.py`.

### `agent/inject_format.py` (any, standard library)

The injection-format table: `note`, `p1_e1`, `p1_e2`, `p2_e1`, `p2_e2`; each
row says how an early result is written into the stream. Unchanged from
`pipeline/inject/inject_format.py`.

### `train/train.py` (probe)

The one trainer. Everything that changes a training result lives in this
file: the method row (ctool: the classification head and its loss on "will a
call come"; cgen: the call as the target; cparam: the arguments as the
target), the packing of examples into batches (examples that share a prompt
prefix share one forward pass; this packing is the method's speed and is
part of the result), the tuning (`full` trains every weight, `lora` trains
adapters through peft, merged when saved), the seed, the learning rate, the
epochs, checkpoints `best/` and `last/`, `metrics.jsonl`, heartbeats,
continue from `last/` when the directory is partial. Has a `VERSION`. Reads
`models.probe`, `probe`, `train`. The proof that the packed loss equals the
plain row-by-row loss is needed once per change of this file, so it is
`tests/test_train_alignment.py`, not a stage. Replaces `train_causal_tool.py`,
`train_causal_share.py`, `share_data.py`, `lora_util.py`, `sweep_lr.py`,
`input_modes.py`, the row-by-row trainers `train_causal_callgen.py` and
`train_causal_param.py` (their loss becomes the test), and the mbert trainers.

### `eval/eval_probe.py` (probe)

Score a trained probe offline. ctool: fit `theta` on val at each risk target,
freeze it, report precision, recall and lead time on test. cgen and cparam:
exact match of the generated call at the ctool threshold. Writes
`report.json`. Has a `VERSION`. Reads `probe`, `eval`. Replaces
`eval_tool.py`, `eval_causal_call.py`, `eval_causal_param.py`,
`eval_mbert_call.py`, the self-fire block.

### `eval/score_run.py` (any)

Score a sample or inject run from its records: task success, calls
speculated, matched and rolled back, tokens and wall time; grouped by seed
with mean and spread; an inject run paired with its baseline run task by task
and seed by seed. Writes `report.json`. Has a `VERSION`. Reads `score`.
Replaces `score_live.py`, `envs/collect/score_probe.py`, `summarize_full.py`,
`acceptance.py`, `sweep_theta.py`.

### `eval/matrix.py` (any)

The backbone times method table from the eval reports in the ledger, as
markdown. Reads nothing but the ledger. Replaces `summarize_matrix.py` and
the `MATRIX_*.md` files under `pipeline/runs/`.

### `scripts/launch.py` (any)

Put a stage's pieces on cards: ask `nvidia-smi` for the free cards, start
each piece in its own tmux session under its environment, write `meta.json`
and the ledger's start row through `ledger.py`, check after a minute that
every piece is alive, refire a dead piece. Which pieces a stage has comes
from `run.py`'s `STAGES` table. Card usage while a run is going is watched
with nvitop and the tmux sessions, so there is no monitor process, no web
page and no job file of held cards. Replaces `launch_cmd.py`,
`launch_common.py`, `launch_probe.py`, `launch_eval.py`,
`pipeline/collect/gen_launch.py`, `gpu_jobs.py`, the placement JSON files
under `ops/`, the launch scripts under `envs/serve_logs/`.

### `scripts/ledger.py` (any, standard library)

The record: append a row to `ledger/runs.jsonl` at start and at finish (key,
stage, workflow, setting, directory, status, commit, dirty files, version,
`diff.yaml`, the summary numbers), write `meta.json`, write the heartbeat a
stage calls every few minutes (`heartbeat.json`: step, total, time), resolve
`<workflow>/<setting>` to a directory, `ls` (status from the row and the
heartbeat's age), `where`, `find`, render `RESULTS.md`. One git probe, one
set of ledger paths. Replaces `record.py`, `runmeta.py`, `heartbeat.py`,
`sampler.py`, `verdicts.py`, the ledger side of `gpu_jobs.py`, the three
copies of the ledger paths.

### `.claude/skills/repo-review/SKILL.md`

Not a Python module: the procedure of the two-day review. The agent reads
the whole tree (naming the code directories, never searching from the root),
checks each file against the six principles and the README's line for it,
and writes one task per finding into `.scratch/review/issues/` with the
file, the principle broken and the smallest fix. It changes no code. gyb
triages the tasks; accepted ones run through the ticket-run skill.

### Not carried over

The read-only feature and the fire head (`readonly/`, `readonly_map.py`,
`param_label.py`, the fire head in `train_causal_callgen.py`, `--self-fire`),
per gyb's answer of 2026-09-13. The mbert line. The theta and plan sweeps,
the acceptance scripts and the one-off checks under `pipeline/inject/`,
`.scratch/kvshare-train/verify/`. The fifteen-step chain and its test. The
dead self-test of the probe service. The monitor process, its web page,
`jobs.json` and the placement files (nvitop, tmux and `run.py ls` cover
them). Presets and `include` (a workflow file's `common` block covers
sharing inside a file). The environment runners for alfworld, bfcl, tau2,
tales and toolhop under `envs/collect/` and their split generators, until one
of them is wanted again; each then becomes one file under `data/` with the
five methods. Everything comes back from git if a result needs it.
