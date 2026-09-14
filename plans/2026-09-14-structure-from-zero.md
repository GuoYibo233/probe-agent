# new1 from zero: the file structure and the modules

Third draft, 2026-09-14. The second draft is commit `07adb8f`; three reviews of
it are in `plans/2026-09-14-structure-review-{newcomer,builder,skeptic}.md`
with a synthesis in `plans/2026-09-14-structure-review-synthesis.md`. This
draft folds in the fourteen confirmed fixes of the synthesis and gyb's three
answers: shared code in a `utils` with one file per probe method; output
directories named by the key; a `sweep:` keyword, with the settings files
written by gyb only. This plan holds two things only: the file structure and
the modules. Migration steps, the README text and the root documents come
later.

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
4. `--debug` runs any setting tiny: a few tasks, a few examples, a few steps.
5. No copies of almost the same file and no framework: a piece of code becomes
   shared on its third repetition, and only when it has stopped changing.
   When several files of one layer share code, the shared code is a `utils`
   in that layer and each method keeps its own file.
6. Each file does one thing that its name says, so the file to edit is found
   by name. The README lists every file with that one line.

---

## Part 1. The file structure

```
new1/
  README.md               for the future reader: this tree, one line per file, how to run, the extension recipes
  CLAUDE.md  TRAPS.md  METHOD.md  DATA.md  WORKPLAN.md  TIMELINE.md
                          root documents, reviewed by gyb by hand later; untouched by this plan
  RESULTS.md              rendered from the ledger by scripts/ledger.py; never edited by hand
  run.py                  the one command: run one setting of one workflow file; ls, where, find, free, kill, sync, selfcheck
  outputs -> NFS          the one link to the outputs root on NFS; every run directory is under it

  constants/              written by hand; nothing in here changes a result or enters a key
    path_datasets.yaml      where each environment, its task splits and each dataset live on this cluster
    path_outputs.yaml       where outputs go on NFS
    path_models.yaml        where each model's weights live
    models.yaml             the model table: for each model, its family (which template) and how it is served
    gpu_state.md            cluster notes written by hand: drivers, CUDA, pitfalls

  settings/               everything in here changes a result; the YAML files are written by gyb only: agents read
                          them and never edit them (a hook refuses), and propose a setting as a task instead
    shape.py                the shape of a setting: every hyperparameter with its default and a one-line comment, the
                            allowed values of each axis, the stage table, and the loader (file -> setting, diff, key)
    debug.yaml              only sizes: 3 tasks, 1 seed, 64 examples, 20 steps, 100 eval examples; never a model or a
                            tuning; --debug lays it over any setting
    baseline.yaml           workflow sample, score; named settings inside
    train_probe.yaml        workflow sample, build, train, eval; named settings inside
    inject.yaml             workflow inject, score; named settings inside
                            a new workflow is a new file; a new experiment is a new named setting in a file

  data/                   the environments, the record a run leaves, what the probe is shown, the dataset built from records
    appworld.py             the AppWorld environment behind six methods: tasks, open, step, speculate, judge, close; its
                            task instructions (the developer message), its no-code message, its call regex
    task_record.py          the record one task run leaves: each step's prompt, reasoning, answer and observation, the
                            speculation events, the outcome, the seed, the commit; write, read, rebuild the conversation
    probe_input.py          what the probe is asked and shown: the cut positions in the reasoning, and the text assembled
                            for the probe (the task, the clipped tool history, the thinking so far); one rule offline and live
    call_syntax.py          the shared part of call handling: argument splitting, building a call, completing a cut-off call
    build_dataset.py        records -> examples for the three probe methods; the train/val/test split; the report; the gates
                            a second environment (ALFWorld) is a second file with the same six methods

  models/                 the two models: how each is loaded, prompted, served and reached
    template_gptoss.py      gpt-oss's conversation format (its name is "harmony"): messages -> tokens, parse a reply, end of
                            turn; the model's own system message (date, effort)
    agent_client.py         the loop's client to the served agent model: a raw token stream with a seed; standard library
    probe_client.py         the loop's client to the probe service: score, generate, encode, decode; standard library
    probe.py                the probe model: backbone plus head; load, score a prefix, generate a call
    serve_agent.py          start, or attach to, the vLLM server for a model with the generation settings; its checks
    serve_probe.py          the probe as a local HTTP service for the agent loop; --check
                            a second model family (Qwen) is template_qwen.py with the same functions

  agent/                  the loop that runs the agent on tasks; the probe is a switch inside its generation step
    loop.py                 run each task and seed: open, generate, parse, step, until done; claim tasks across pieces;
                            write the record
    generate.py             one generation step: stream tokens; stop at end of turn, or when the probe fires (switch on)
    speculate.py            after the probe fires: get the call, run it early, splice the result in, resume; roll back on mismatch
    inject_format.py        the injection-format table: the five ways an early result is written into the stream

  train/                  train a probe: shared code in utils, one file per probe method
    utils/
      trainer.py            the shared training loop: settings -> arguments, seed, backbone, tuning (full or LoRA),
                            checkpoints, metrics, heartbeat, resume, the alignment gate
      packing.py            examples -> packed batches for the generating probes; the instance strings and their constants
      reference.py          the row-by-row loss the alignment gate and the test compare the packed loss against
    ctool.py                the classification probe: its batches, its head, its loss, its validation accuracy
    cgen.py                 the call-generating probe: its instance strings and target, its loss positions, its exact-match eval
    cparam.py               the argument-generating probe: the same shape as cgen with its own strings

  eval/                   score a probe or a run: shared code in utils, one file per probe method
    utils.py                shared: load a probe run and its split, walk the examples, bootstrap, write the report
    ctool.py                fit theta on val at the risk targets, freeze it, report on test
    cgen.py                 exact match of the generated call at the frozen theta
    cparam.py               exact match of the generated arguments at the frozen theta
    score_run.py            a sample or inject run: task success, speculation outcomes, tokens and time; by seed; against a baseline
    method_table.py         the backbone x method table from the ledger; groups sweep children, reports mean and spread

  scripts/                the programs around a run: start it on cards, keep the record; ledger.py is a library every stage imports
    launch.py               pick free cards, one tmux session per piece, the record's start, the alive check, refire
    ledger.py               the record: runs.jsonl rows under a lock, meta.json, the heartbeat, ls/where/find/kill, RESULTS.md

  ledger/                 the records kept in git
    runs.jsonl              one row per stage run, appended at start and at finish; never edited
    runs.jsonl.lock         the lock every append takes; ignored by git

  tests/                  one test per contract; a check needed once per code change lives here, not in a stage
    fixtures.py             a tiny random-init model and a few records, for tests that need a model on CPU
    test_shape.py           defaults fill in; the key is unchanged when a defaulted field is added; a changed default
                            without a VERSION bump fails (golden defaults)
    test_probe_input.py     the cut rule and the assembled text on recorded reasoning
    test_call_syntax.py     argument splitting and call completion on recorded text
    test_template.py        template render equals the server's tokens (vllm environment)
    test_inject_format.py   the five formats on one fixed example
    test_rollback.py        a speculated call leaves the world as it was (today's shadow self-test)
    test_generate.py        the stop condition and the head boundary on a recorded stream
    test_loop.py            claiming, done means a final record without abort, resume
    test_build_dataset.py   the split and the gates on a few records
    test_train.py           the packed loss equals the row-by-row loss, gradient equality across block splits, a LoRA
                            merge equals full weights; tiny model, CPU
    test_score_run.py       the report on a few records, pairing by task and seed
    test_ledger.py          a row survives a start, a finish, a relaunch and two concurrent appends

  notebooks/              a notebook imports any module; no module imports a notebook; a notebook never writes an output
                          directory or a ledger row; one that produces a figure becomes a script under figures/
  figures/                one script per figure; empty until the first figure exists
  envs/                   virtual environments and benchmark clones, no code of this repo: the AppWorld clone and its
                          venv, the probe venv, the vLLM venv, the lock files
  .claude/skills/repo-review/SKILL.md
                          the two-day review: an agent reads the tree against the six principles and writes tasks
  .scratch/review/issues/ the tasks the review writes, in the issue-tracker format already in use
  .claude/hooks/settings_readonly.sh
                          the hook that refuses any agent edit to settings/*.yaml
  plans/  docs/  .claude/ as today
```

Python files: 30 (root 1, settings 1, data 5, models 6, agent 4, train 6,
eval 6, scripts 2), plus tests. Today: about 60 under the code directories.

Outputs live on NFS only, under `outputs/<stage>/<key>/`: the key alone,
because a directory that nine settings share cannot carry one setting's
name, and an edited shared block would leave directories whose names match
no setting; the ledger and `run.py ls` show the names. Debug runs go under
`outputs/debug/`.

### How a run is named and started

`python run.py baseline gptoss120b_appworld`: the first word is the workflow
file, the second the named setting inside it. The command loads the setting,
walks the file's stage list, and for each stage computes the key, looks for
the output directory, and then skips it (done), continues it (partial), runs
it (missing), or reports it (running, failed). A CPU stage runs at once. A GPU
stage is handed to `scripts/launch.py`, which starts its pieces on cards and
writes the record; the walk stops there and the same command continues it
later. Every stage run leaves one directory with its resolved settings, its
metadata and its outputs, and one row in the ledger.

### If you edit a setting

The key is computed from the setting's content, so editing a value gives the
next run a new directory; the old directory stays, with the settings it ran
under saved inside it, and `run.py ls baseline` shows both with what differs.
Editing the notes changes nothing. Adding a hyperparameter to the shape with
a default that reproduces the old behavior changes no key. Changing an
existing default is a version change of the stage that reads it, and a test
refuses it without the bump.

### What keeps the tree this shape

1. The two-day review. Every two days an agent runs the repo-review skill:
   it reads the tree against the six principles (one thing per file, no
   near-copies, one home per fact, imports only downward between layers,
   every file listed in the README with a true line) and writes one task per
   finding into `.scratch/review/issues/`. gyb triages the tasks.
2. `run.py selfcheck`, the three checks a machine does better than a reader:
   every Python file starts with `# env: appworld | probe | vllm | any` and
   imports under that environment (a file marked `any` under all three,
   importing only what all three hold); no `/home/` or `/net/` in code
   outside `constants/`; every tracked Python file appears in the README
   tree.
3. The settings files are gyb's. `settings/*.yaml` are written by gyb only;
   a hook refuses Write and Edit on them from any agent, and an agent that
   wants a new setting writes a task with the proposed block. `shape.py` is
   code and follows the normal rules.
4. Two rules for people: code is shared on its third repetition, and only
   when it has stopped changing; a `VERSION` is bumped when a file's output
   changes meaning for the same settings, and only then.

---

## Part 2. The modules

Each module below: what it does, what it offers, which settings it reads,
which environment imports it, and which of today's files fold into it. Files
not named anywhere in this part are deleted; git keeps them.

Environments: `appworld` is the AppWorld venv (its pins, no torch); `probe` is
the torch venv (torch, transformers, peft, openai-harmony); `vllm` serves the
agent model. A second benchmark environment brings its own venv and names it
in its header. `any` means importable in all three; OmegaConf and PyYAML are
installed in all three and count as `any`. `run.py` runs under the probe
environment; the system python stops being an interpreter of this repo.

### `run.py` (any)

The one command. `run.py <workflow> <setting> [section.field=value ...]
[--debug] [--stage <name>] [--launch] [--retry] [--force]` loads the setting
and walks the workflow's stages as described above; without `--launch` a GPU
stage's command is printed instead of started; `--retry` starts a failed
directory again; `--force` runs a stage into a fresh directory even when a
done one exists. `run.py <run directory>/settings.yaml` runs from a saved
settings file, which is how an old run is repeated exactly. `run.py ls
[workflow]` prints the table of runs with status (done, failed, running with
the heartbeat's age, stalled), the owners of shared directories, and
directories whose setting has since been edited. `run.py where <workflow>
<setting> <stage>` prints the output directory. `run.py find
section.field=value ...` prints the ledger rows whose settings match. `run.py
free` prints the free cards. `run.py kill <workflow> <setting> <stage>` ends
the pieces and writes the killed row. `run.py sync` mirrors metrics into the
tracker. `run.py selfcheck` runs the three checks. About 250 lines; the stage
table it walks lives in `settings/shape.py`.

Replaces `run.py` (1300 lines: the task registry, the recipe engine, the
dirty gate, which stays as one function), `pipeline/driver.py` (the
fifteen-step chain).

### `settings/shape.py` (any)

The shape of a setting, the stage table, and how a file becomes a setting.

**Format.** YAML files, read with OmegaConf (version 2.3: one small package
with PyYAML underneath, no Hydra). The shape is a set of dataclasses in this
file, one per section, every field with a default and a one-line comment;
each axis (`data.env`, `probe.method`, `probe.tuning`, `inject.format`, the
template names) declares its allowed values, so a retired value fails loudly.
A setting lists only the fields that differ from the defaults. Loading
merges, in order: the dataclass defaults, the file's `common` block, the
named setting, `settings/debug.yaml` when `--debug` is given, and last the
command-line overrides `section.field=value`, so an override beats debug. A
key that is not in the shape, or a value outside an axis, fails loading. A
list field is replaced, never appended: `seeds: [42]` in a setting over
`seeds: [42, 67, 4267]` in `common` gives `[42]`. `${probe.method}` style
references work after the merge.

Why OmegaConf alone: it gives the four things that matter (merge, typed
defaults, overrides, references) in one package that installs in seconds into
all three environments. Hydra is a framework on top of it (its own working
directory, output layout, config groups, launchers) and would fight the
identity rule below. JSON was rejected for lacking comments; YAML is what a
future reader expects here.

**Adding a hyperparameter.** Add one field with a default that reproduces
the old behavior. No setting changes, and the resolved settings saved in
every run directory show the effective value. When the old behavior cannot be
the default, bump the `VERSION` of the stage that reads the field;
`tests/test_shape.py` keeps a golden copy of every default and fails when an
existing default changes without that bump.

**A workflow file.** The file is the workflow: its `pipeline` line names
the stages, in order, from the six that exist (`sample`, `build`, `train`,
`eval`, `inject`, `score`), each at most once. Its `common` block holds what
every setting in the file shares. Every other top-level key is a named
setting. The sections of a setting are the six stage sections plus five
shared ones: `data` (which environment), `models` (which agent model, which
probe backbone), `generation` (how the agent model generates), `probe` (what
the probe is), `logging` (the tracker switch).

```yaml
# settings/train_probe.yaml: sample the agent, build the dataset, train a probe, score it
pipeline: [sample, build, train, eval]

common:
  data: {env: appworld}
  models: {agent: gptoss120b}
  generation: {temperature: 1.0, date: 2026-08-06}      # the date is written into the prompt
  sample: {split: train, seeds: [42, 67, 4267], pieces: 6, replicas: 2, max_steps: 30}
  train: {epochs: 1, seed: 42}
  eval: {risk: [0.10, 0.05]}

ctool_on_qwen06:
  notes: first ctool probe on the 0.6B backbone
  models: {probe: qwen06}
  probe: {method: ctool, tuning: full}
  train: {lr: 1.0e-5}

cgen_on_qwen06:
  models: {probe: qwen06}
  probe: {method: cgen, tuning: full}
  train: {lr: 1.0e-5}

ctool_on_qwen17_lora_lr:
  models: {probe: qwen17}
  probe: {method: ctool, tuning: lora}
  sweep: {train.lr: [1.0e-4, 3.0e-4, 5.0e-4]}            # see "Sweeps"
```

```yaml
# settings/baseline.yaml: run the agent alone and score it
pipeline: [sample, score]

common:
  sample: {split: test, seeds: [42], pieces: 6, replicas: 2, max_steps: 30}

gptoss120b_appworld:
  data: {env: appworld}
  models: {agent: gptoss120b}
  generation: {temperature: 1.0, date: 2026-08-06}
```

```yaml
# settings/inject.yaml: run the agent with a trained probe and score it against a baseline
pipeline: [inject, score]

common:
  inject: {split: test, seeds: [42], pieces: 6, replicas: 2, max_steps: 30}

ctool_qwen06_p1e1:
  inject:
    probe_score: train_probe/ctool_on_qwen06   # the ctool eval run: when to fire, with its fitted temperature
    probe_gen: train_probe/cgen_on_qwen06      # the cgen eval run: what call to write
    theta: 0.9
    format: p1_e1
  score: {baseline: baseline/gptoss120b_appworld}
```

A live run needs two probes: one that decides when to fire (a ctool run,
with the softmax temperature its eval fitted) and one that writes the call (a
cgen run). Both are named as eval runs, so inject's upstream stage is eval.

**References.** When a stage's upstream is not in the file's pipeline, the
section names the run that has it, as `<workflow>/<setting>`. A reference is
resolved by loading that setting from its file, as it is now, and computing
its key chain; a name that no longer exists is a load error; the resolved key
enters the referencing stage's key and is written into its `meta.json`. A
bare key may be written instead of a name to pin an old run. The referencing
setting inherits the shared sections of the referenced run (`data`,
`models.agent`, `generation`); a value it states differently is a load error,
except under an explicit `override:` block, so an inject arm cannot silently
differ from its probe's training data or from its baseline.

**The stage table.** One table, in this file, read by `run.py` and by the
key function:

| stage | pieces (environment) | cards | reads | upstream in the key | versions folded in |
|---|---|---|---|---|---|
| sample | serve_agent (vllm) x replicas; loop (the environment's venv) x pieces | yes | data, models.agent, generation, sample | none | loop, task_record |
| build | build_dataset, in place | no | build; the sample section (split, seeds) | the manifest of the consumed sample files | build_dataset, probe_input, call_syntax |
| train | train/<method> (probe) | yes | models.probe, probe, train | the build manifest | trainer, packing, the method file |
| eval | eval/<method> (probe) | yes | probe, eval | the train key | eval utils, the method file, probe_input |
| inject | serve_agent (vllm) x replicas; serve_probe (probe); loop (the environment's venv) x pieces | yes | data, models, generation, probe, inject | the two eval keys | loop, generate, speculate, inject_format, probe_input |
| score | score_run, in place | no | score; the inject or sample section (split, seeds) | the manifests of the run and of its baseline | score_run |

**Identity, reuse, versions.** Each stage run has a key: twelve characters
of a hash over the fields the table lists for the stage (only the values that
differ from the defaults; `notes` never enters), its upstream as the table
says, and the `VERSION` of its own file and of the pure modules it folds in.
Two kinds of upstream exist. A key-chained upstream (train from build, eval
from train, inject from the two evals) enters as the upstream key. A
consumer of task files (build from sample, score from inject or sample)
enters the subset it consumes (split, seeds) and the manifest of exactly
those files, so adding seeds to a sample changes the build key, and a
`VERSION` bump upstream that changes no bytes stops at the manifest instead
of cascading through days of training. The sample and inject directories
themselves are keyed without the task and seed lists, so a request for more
tasks or seeds adds files to the same directory. Every stage writes
`manifest.json` (file list with hashes) at finish; sample and inject update
it per task file.

The output directory is `outputs/<stage>/<key>/`. Its `meta.json` holds the key, the versions, the status, the owners (every
workflow and setting that used it), the upstream keys, and one launch entry
per start (commit, dirty files, host, cards, command, time). A directory
whose status is done is skipped. A partial one is continued: sample and
inject are collections of task files, one per task and seed, and a task file
is done only when its final record has no abort, so aborted files are redone;
train continues from `last/` when the commit is the same, otherwise it starts
over; build, eval and score are quick and start over. A running directory
(fresh heartbeat) is reported with its session and not touched; a failed one
is started again only with `--retry`, so an out-of-memory failure cannot loop.
The git commit is recorded in every launch entry and in every task record,
not keyed, so a refactor that changes no output keeps every output valid.

Every run directory holds `settings.yaml` (resolved, everything),
`settings_diff.yaml` (what differs from the defaults: the identity, and the
human summary), `meta.json`, `dirty.patch` (the uncommitted changes at
launch, if any), `log.txt`, `heartbeat.jsonl`, `metrics.jsonl`,
`manifest.json`, and the stage's outputs.

**Sweeps.** A named setting may hold one `sweep:` block: a map from field
to list. The loader expands it into child settings named
`<setting>/<field>=<value>,...`, each a full setting with its own keys;
`eval/method_table.py` groups children by everything but the swept fields
and reports mean and spread. Three sweep tools exist today (presets, learning
rate, theta), which is the third repetition; the block is about forty lines
in the loader. Like every other part of a settings file, a `sweep:` block is
written by gyb only.

**Debug.** `settings/debug.yaml` holds only sizes: three tasks, one seed, 64
examples, 20 steps, 100 evaluation examples. It never changes a model or a
tuning, so a debug run exercises the real configuration's code path, and it
is applied before the command-line overrides. `serve_agent.py` attaches to a
live server with the same model and generation settings, so a debug sample
does not wait for a server to start. Debug outputs go under `outputs/debug/`
and are not written to the ledger. This replaces `demo/` and its fixtures.

**Logs and tracking.** `log.txt` and `metrics.jsonl` in the run directory
are the record, and `run.py ls`, `find` and `where` read the ledger; nothing
else is needed to retrieve a run. Optional viewer, switched on by
`logging.tracker: mlflow` (default `none`): MLflow with a file store on NFS,
fed by `run.py sync` on the login machine, which reads the metrics files; no
stage imports the tracker. Its web page over an ssh port forward replaces
today's monitor page. Weights & Biases was considered and rejected: it needs
pydantic 2, which the AppWorld venv cannot hold, and the compute nodes have
no internet.

Offers: `load(workflow, setting, overrides, debug)`, `diff(cfg)`,
`key(cfg, stage)`, `resolve(reference)`, `save(cfg, run_dir)`, `STAGES`.
Reads `constants/` for the paths and the model table, after keying, so
nothing in `constants/` enters a key. About 400 lines with the dataclasses
and their comments. Replaces `preset_loader.py`, `model_registry.py`,
`configs/models.json`, `configs/presets/`, `pipeline/configs/`, the
manifests in `pipeline/collect/`, and the tables in `run.py`.

### `data/appworld.py` (appworld)

The AppWorld environment behind six methods: `tasks(split)`; `open(task,
seed)` (a fresh world for this task and seed, named so that two seeds never
share AppWorld's experiment directory); `step(code)` (run the agent's code,
return the observation cut at the length cap, with its error kind);
`speculate(call)` (make the predicted call executable, snapshot the world,
run it, restore the snapshot, keep the clock frozen, return the observation
and its error kind); `judge()` (did the task succeed); `close()` (delete the
per-task outputs). Also the task instructions the agent reads (the developer
message), the message the agent gets when it writes no code, the environment's
call regex, and the AppWorld seed, because those are the environment's. The
package is imported after changing into the AppWorld home, as today. The loop
never contains environment code; a second environment is a second file with
the same six methods, chosen by `data.env`, and a shared base class waits for
the third.

Reads `constants/path_datasets.yaml`. Replaces the world half of
`envs/collect/run_appworld.py`, `pipeline/inject/exec_calls.py` (requote, error
kinds, the snapshot, the clock guard, the length cap), the system prompt copy
in `rebuild.py`, and the three copies of `APPWORLD_HOME`.

### `data/task_record.py` (any, standard library)

The record one task run leaves, step by step: what the model saw, what it
wrote (reasoning and answer), what came back, the speculation events when the
probe was on (fired, matched, rolled back, with times), the outcome with its
abort field, the seed, and the commit. One record format for sample and
inject, with a `VERSION`. Offers `write`, `read`, `is_done` (a final record
with no abort), and `to_messages()`, which rebuilds the conversation exactly
as the model saw it; the loop uses it live and the builder offline, so there
is one convention. Replaces the trajectory log in `envs/collect/common.py`,
the record readers in `rebuild.py` and `exec_calls.py`.

### `data/probe_input.py` (any, standard library, pure)

What the probe is asked and shown. `cut_points(reasoning)` gives the
positions at which the probe may be asked: sentence starts, after a minimum
length, unthinned; this is today's live rule, and the builder applies its own
cap (`build.max_cuts`, keyed) after enumeration. `assemble(task, history,
thinking)` gives the text the probe scores: the task, the last three tool
rounds with results clipped, and the thinking so far. `build_dataset.py`
uses both offline, `agent/generate.py` uses both live, `eval/utils.py` uses
`assemble`; one copy, so the probe is asked where and on what it was trained.
Has a `VERSION`, folded into the keys of build, eval and inject. Replaces the
cut rule and `assemble` in `pipeline/annotate/rules.py` and the live cut rule
in `live_appworld.py`; unifying the two rules changes every existing dataset
and starts the build `VERSION` at 2.

### `data/call_syntax.py` (any, standard library, pure)

The shared part of call handling: argument splitting, `make_call` (a call
from its parts), `complete_call` (finishing a call that was cut off). The
regex that finds a call belongs to the environment (AppWorld, BFCL, ALFWorld
and tau2 each have their own today); these functions take it from the
environment file. Used by `build_dataset.py`, `agent/speculate.py`,
`eval/utils.py` and `eval/score_run.py`. Today the splitter has three copies;
this file is the one home. Has a `VERSION`. Replaces the call half of
`pipeline/annotate/rules.py`, `pipeline/inject/parse_call.py`, the parser
copies in `eval_causal_call.py` and `eval_causal_param.py`, the regex in
`score_live.py`.

### `data/build_dataset.py` (any)

Records to examples. Reads exactly the files its sample section names (split
and seeds), never a glob; for each cut point of each record, the example each
method learns from (ctool: will a call come; cgen: the call; cparam: its
arguments), with the probe's text from `probe_input.py`; the split by task
into train, val and test; the report; the gates that today live in
`check_callstr.py`; the manifest. Reads `build`, the sample section. Has a
`VERSION`. Replaces `pipeline/annotate/build.py`, `check_callstr.py`,
`envs/collect/build_dataset.py`; `param_label.py` and `readonly/` are dropped
with the read-only feature.

### `models/template_gptoss.py` (any at import; render needs the probe environment)

The gpt-oss conversation format, whose name is "harmony": `render(messages)`
gives the prompt tokens exactly as the server renders them, `parse(text)`
splits a streamed reply into reasoning, answer and call, `end_of_turn` says
where a reply ends, and `system_message(generation)` is the model's own
system message (date, reasoning effort), distinct from the environment's task
instructions. `constants/models.yaml` names the template for each model
(`template: gptoss`); when Qwen becomes an agent model, `template_qwen.py`
is a second file with the same functions and a second table row. The
rendering library is imported inside `render`, so the AppWorld environment
can import the file for parsing. Replaces `pipeline/inject/harmony_render.py`,
the hand-assembled template in `common.py`, and the stream parsing in
`live_appworld.py` and `common.py`.

### `models/agent_client.py` (any, standard library)

The loop's client to the served agent model: `stream(prompt_ids, generation,
seed)` returns tokens as they arrive from a raw completion request, with
retries. This is the one generation path, for sample, for the inject control
and for inject: today's default sampling path is already the hand-rendered
completion, and comparing a probe run with a chat-endpoint baseline would
compare two paths. The chat endpoint is used only by `serve_agent.py`'s
render-equals-server check. Reads `generation`. Replaces the request rows of
`envs/collect/common.py` and the request half of `live_appworld.py`; the
OpenAI package is no longer needed.

### `models/probe_client.py` (any, standard library)

The loop's client to the probe service: `score(text)`, `generate(text)`,
`encode(text)`, `decode(ids)`, `health()` over HTTP. Sits beside the agent
client so both clients and both servers are in one folder. Replaces the
service calls scattered through `live_appworld.py`.

### `models/probe.py` (probe)

The probe model: a small backbone from the model table plus, for ctool, a
classification head, and for cgen and cparam, the backbone's own generation.
Offers `Probe.load(dir)`, `save(dir)`, `score(text)` (the probability that a
call is coming, at the temperature its eval fitted), `generate_call(text)`
(greedy, cut at the first newline); the tokenizer is the probe's own. One
class shared by the trainers, the evaluators and the probe service; today the
loader exists three times and the generation contract four times. Reads
`models.probe`, `probe`. Replaces `CausalProbe` in `train_causal_tool.py`,
the loaders in `eval_tool.py`, `probe_server.py` and `check_bundle.py`, the
generation copies.

### `models/serve_agent.py` (vllm)

Start the vLLM server for a model table row with the generation settings
(the prompt date, the reasoning effort, the server environment variables), or
attach to a live server that already serves the same model with the same
generation settings; wait for health; run the check table: health, and
render-equals-server (the template's tokens for one conversation equal the
server's). `stop` ends a server this run started. Replicas come from the
stage's setting. The date is a settings value, so the two arms of a
comparison always share it; the old constants go. Reads `models.agent`,
`generation`, `constants/path_models.yaml`, `constants/models.yaml`. Replaces
`serve_preset.py`, the seventeen `launch_vllm_*.py` under `envs/serve_logs/`,
`ident3_gate.py`, `run_gptoss.sh`.

### `models/serve_probe.py` (probe)

The probe as a local HTTP service: it loads the score probe (a ctool eval run,
with its fitted temperature) and the generation probe (a cgen eval run), and
answers score, generate, encode, decode, health; `--check` proves both load
and answer before a launch. Why a service: the loop runs in the AppWorld
environment and the probe in the probe environment; the two cannot share a
process, so the loop reaches the probe and the tokenizer through this one
door. Reads `inject.probe_score`, `inject.probe_gen`, `inject.theta`.
Replaces `pipeline/inject/probe_server.py` (its dead self-test deleted) and
`check_bundle.py`.

### `agent/loop.py` (the environment's venv)

Run the requested tasks and seeds across the stage's pieces: each piece
claims a task-and-seed with an atomic ticket, `open`s the world, then repeats
generate, parse, `step`, append, until the turn ends or the step limit is
reached; writes the record with the commit; `close`s the world; writes the
heartbeat. A task file is redone unless it is done (a final record with no
abort); a piece never opens another piece's file. The loop stops after a run
of consecutive connection failures instead of recording aborts at full
speed. It runs a sample (probe off) and an inject (probe on) alike; the
difference is the switch that `generate.py` reads. It calls the environment's
six methods and nothing else of it. Reads `sample` or `inject`, `generation`.
Replaces the loop half of `run_appworld.py`, `run_task`, `main` and the
claim protocol of `live_appworld.py`, `live_arm_job.sh`, `live_smoke_job.sh`,
`live_v3_job.sh`, `splice_client.py`, `launch_splice_clients.py`.

### `agent/generate.py` (the environment's venv)

One generation step: a token stream from the agent client, parsed by the
template as it arrives. Probe off: the stop condition is the end of the
turn. Probe on: at each cut point of the reasoning (from `probe_input.py`)
the assembled text goes to the probe client for a score; the stop condition
becomes "end of turn, or the probe fired" (score at or above `theta`); on a
fire, the head boundary (the shortest token prefix covering the cut) is
found through decode. Returns the text and, when it fired, the cut, the
score and the head. Reads `probe`, `inject.theta`, `generation`. Replaces
`gen_step`, `find_head`, `token_boundary` of `live_appworld.py`.

### `agent/speculate.py` (the environment's venv)

What happens after the probe fires: ask the probe client for the call,
complete it if cut off, `speculate` it in the environment (which snapshots,
runs and restores), write its result into the stream in the chosen format,
splice it at the head, resume generation; when the model's own call turns
out different, the real call runs through `step` and the event is recorded
as rolled back. Records every speculation event with its times into the
record. Reads `inject.format`. Replaces the speculate, splice and resume
parts of `live_appworld.py`.

### `agent/inject_format.py` (any, standard library)

The injection-format table: `note`, `p1_e1`, `p1_e2`, `p2_e1`, `p2_e2`; each
row says how an early result is written into the stream. Unchanged from
`pipeline/inject/inject_format.py`.

### `train/utils/trainer.py` (probe)

The shared training loop, imported by the three method files: settings to
arguments; the seed (also the shuffle's); the backbone from the model table;
the tuning (`full` trains every weight, `lora` trains adapters through peft,
merged when saved); the optimizer and schedule; `metrics.jsonl`; heartbeats;
checkpoints `best/` on validation improvement and `last/` every
`train.checkpoint_hours`; resume from `last/` at the same commit, otherwise a
fresh start; the alignment gate (`train.align_check`, default on) that
compares the method's loss on a few real batches with `reference.py` before
training and stops on a mismatch, because a kernel path once computed wrong
results on the real model. Replaces the copied spines of
`train_causal_tool.py` and `train_causal_share.py`, `lora_util.py`,
`sweep_lr.py`.

### `train/utils/packing.py` (probe)

Examples to packed batches for the generating probes: the instance strings
of cgen and cparam (prompt tail, target, separator, length caps, in one
place), examples that share a prompt prefix packed into one sequence with
the mask and positions that keep them separate, batches by token budget.
Replaces `share_data.py` and the constants the row-wise trainers own today.

### `train/utils/reference.py` (probe)

The row-by-row loss for cgen and cparam computed the plain way, one example
per sequence; the alignment gate compares the packed loss against it on the
real model, and `tests/test_train.py` on the tiny model. No training loop.
Replaces the loss halves of `train_causal_callgen.py` and
`train_causal_param.py`.

### `train/ctool.py`, `train/cgen.py`, `train/cparam.py` (probe)

One file per probe method, each a program `run.py` starts for
`probe.method`, each using the shared loop. `ctool.py`: whole events as
batches, the boundary positions, the classification head, its loss,
validation accuracy at the boundaries, the save layout with the head and the
label map. `cgen.py`: the instance strings and the call as the target through
`packing.py`, the loss on the target positions, validation loss plus greedy
exact match, the save layout of a full language model. `cparam.py`: the same
shape as `cgen.py` with the arguments as the target and its own prompt tail.
Each has a `VERSION`. Reads `models.probe`, `probe`, `train`. Replaces the
method halves of `train_causal_tool.py` and `train_causal_share.py`.

### `eval/utils.py` (probe)

Shared by the three method files: load a probe run through `models/probe.py`
and the split it is scored on, assemble each example's text through
`probe_input.py`, walk the examples in batches, bootstrap the intervals,
write `report.json` and the manifest. Replaces the shared halves of
`eval_tool.py`, `eval_causal_call.py`, `eval_causal_param.py`.

### `eval/ctool.py`, `eval/cgen.py`, `eval/cparam.py` (probe)

One file per probe method, each a program `run.py` starts for
`probe.method`. `ctool.py`: fit the softmax temperature and `theta` on val at
each risk target, freeze them, report precision, recall and lead time on
test; the fitted temperature is what the probe service reads. `cgen.py`:
exact match of the generated call at the frozen theta. `cparam.py`: exact
match of the generated arguments at the frozen theta. Each has a `VERSION`.
Reads `probe`, `eval`. Replaces the method halves of `eval_tool.py`,
`eval_causal_call.py`, `eval_causal_param.py`; `eval_mbert_call.py` and the
self-fire block are dropped.

### `eval/score_run.py` (any)

Score a sample or inject run from exactly the files its section names: task
success, calls speculated, matched and rolled back, time saved per fired
call, tokens and wall time; grouped by seed with mean and spread; an inject
run paired with its baseline run task by task and seed by seed; refuses a
pair whose generation settings differ. Writes `report.json` and the manifest.
Has a `VERSION`. Reads `score`, the inject or sample section. Replaces
`score_live.py`, `envs/collect/score_probe.py`, `summarize_full.py`,
`acceptance.py`.

### `eval/method_table.py` (any)

The backbone times method table from the eval reports in the ledger, as
markdown; groups the children of a sweep by everything but the swept fields
and reports mean and spread. Reads nothing but the ledger. Replaces
`summarize_matrix.py` and the `MATRIX_*.md` files under `pipeline/runs/`.

### `scripts/launch.py` (any)

Put a stage's pieces on cards: ask `nvidia-smi` for the free cards and treat
a card with any compute process, or a failed probe, as busy; start each piece
in its own tmux session, named with the stage and key, under the piece's
environment; write the launch entry and the ledger's start row through
`ledger.py`; check after a minute that every piece is alive and that no
foreign process took the card; refire a dead piece, reusing a server piece
that is still alive. The pieces and their count come from the stage table
and the stage's setting. Also `free`. Card usage while a run is going is
watched with nvitop and the tmux sessions; there is no monitor process and
no web page. Replaces `launch_cmd.py`, `launch_common.py`, `launch_probe.py`,
`launch_eval.py`, `pipeline/collect/gen_launch.py`, `gpu_jobs.py`, the
placement JSON files under `ops/`, the launch scripts under
`envs/serve_logs/`.

### `scripts/ledger.py` (any, standard library)

The record, imported by every stage. Append a row to `ledger/runs.jsonl`
under `runs.jsonl.lock` at start and at finish (stage, key, workflow,
setting, directory, status, launch entry, versions, the settings diff as
JSON, the summary numbers); a later finish row for the same start wins.
Write `meta.json` and `dirty.patch`. Write the heartbeat a stage calls every
few minutes (`heartbeat.jsonl`: step, total, time, so a rate and an estimate
can be read). `ls`: status from the row, the heartbeat's age, the tmux
session's liveness and each server piece's health; owners; directories whose
setting has been edited since; tmux sessions of this repo that match no row.
`where`, `find`, `kill` (ends the pieces, writes the killed row),
`resolve` (a reference to a directory), the `RESULTS.md` render. One git
probe, fail-closed. Replaces `record.py`, `runmeta.py`, `heartbeat.py`,
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
`param_label.py`, the fire head in `train_causal_callgen.py`, `--self-fire`;
their branches thread through train and eval, so this is an edit, not a
deletion). The mbert line (`train_mbert_*.py`, `eval_mbert_call.py`,
`input_modes.py`). The offline replay line (`replay_inject.py`,
`splice_replay.py`, `extract_completed.py`, `build_form_table.py`,
`launch_plan_sweep.py`, `ident3_score.py`, `test_stopfix.py`). The sweep
tools (`sweep_preset.py`, `sweep_lr.py`, `sweep_theta.py`); a sweep is the
`sweep:` block or N named settings. The theta curve and the acceptance
scripts under `pipeline/inject/`, `.scratch/kvshare-train/verify/`. The
memory probe and its pickers in the trainer, the logits cache of the ctool
evaluator. The fifteen-step chain and its test. The dead self-test of the
probe service. The monitor process, its web page, its incident half,
`jobs.json` and the placement files (nvitop, tmux and `run.py ls` cover
them). Presets and `include`. The environment runners for alfworld, bfcl,
tau2, tales and toolhop under `envs/collect/` and their split generators,
until one of them is wanted again; each then becomes one file under `data/`
with the six methods, and the README's `data/` block names the old file and
the commit that holds it. `demo/` at the repository root; its tiny model
builder becomes `tests/fixtures.py`. Everything comes back from git if a
result needs it.
