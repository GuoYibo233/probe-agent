# new1 renewal: design

Date: 2026-09-13, fourth draft. Status: for gyb's review. Nothing in the tree
changes until this document is approved.

Sections 1 to 5 are the design and are written for a reader who has never
opened the repo. Sections 6 to 9 are the engineering detail for the person
doing the migration. Section 10 lists the open decisions.

## 1. Purpose

Make the repo fast to extend and easy to read. The things gyb wants to do
without reading code:

- add a model, change generation settings, add a method, add an evaluation
  method, add a dataset, draw figures;
- try several similar variants of one step side by side;
- archive a method that did not work, so the attempt and its result stay
  findable;
- find the settings that produced any output file, find settings by
  condition, write notes next to the settings, and refer to a run by name
  when talking to an agent.

Each of those is a settings file, or one new file plus one table row.

Decisions gyb has taken (2026-09-12 and 2026-09-13):

- Dead code is deleted on a branch. Old files come back from git history.
  No archive directory for code.
- One settings file per run of a step, holding every parameter of that
  step, so a run needs no long command line. Every ledger entry links the
  output directory and the settings file.
- Outputs live only on NFS. The ledger is the index that finds them.
- The hand-written code map is abandoned. A README explains the repo. The
  rules for running code stay.
- Every place where a choice is made inside a step is a named axis with a
  table of variants; a settings file lists which variants it runs as arms.
- Folder and settings names say what the thing is. Codes like np821 are not
  used for new work.
- The root documents (METHOD, DATA, WORKPLAN, TIMELINE, RESULTS) keep their
  content; gyb re-roles them by hand after the renewal.
- CUDA is the default device.
- Model weights live on NFS in the existing models directory; the repo
  holds only the table that names them, and that table is a settings file.
- Steps 1 and 5 share one driver: the live run is the sampler with a probe
  attached (2026-09-13).
- Sample counts and repeats are settings values, never copies of a file:
  sample and inject give one seed per trajectory inside one run; dataset
  and train give one seed per run, and a list of seeds makes one run per
  value. A run that failed is relaunched under its own id.

Not in scope: changing any research method or any output file format on
NFS. The ledger stays append-only; it gains new event kinds and fields, and
no existing line is rewritten.

## 2. What the repo does, in five steps

The research question: a small probe model reads the agent model's thinking
while it is being written and predicts the tool call the agent is about to
make. The system then makes that call early and injects its result back into
the thinking, so the agent does not wait for it. Everything in the repo
serves five steps, and the target tree has one directory per step.

| Step | What happens | Input | Output on NFS | GPU |
|---|---|---|---|---|
| 1 sample | the agent model runs an environment's tasks; every step of thinking, tool call, and result is saved as a trajectory | a model, an environment, generation settings | trajectories | yes |
| 2 dataset | trajectories are cut into training examples: a prefix of the thinking paired with the call that followed; split into train, val, test piles | a sample run | a dataset | no |
| 3 train | a probe of one method is trained on a dataset | a dataset, a method, a backbone | a trained probe | yes |
| 4 eval | a trained probe is scored offline: does it predict the right tool and call, and at which confidence threshold does it fire with an acceptable false-fire rate | a trained probe | reports inside the probe's directory | yes |
| 5 inject | the driver of step 1 runs tasks live with a probe attached: the probe fires, the call runs early, its result is injected; task success is scored against a no-probe baseline | trained probes, a model, an environment | live runs and scores | yes |

Three shared resources serve every step: **models** (which weights exist and
how to serve one on a card), **environments** (the benchmark clones, each with
an adapter that speaks its API), and the **cluster** tools (launch a step on a
GPU, watch it, record it in the ledger).

### 2.1 Words used in this document

| Word | Meaning here |
|---|---|
| agent model | the large model that runs tasks (gpt-oss-120b today) |
| backbone | the small pretrained model a probe is fine-tuned from; keys `qwen06`, `qwen17`, `qwen4` for Qwen3 0.6B, 1.7B, 4B |
| method | one kind of probe: **ctool** predicts the tool name; **cgen** writes the whole call; **cparam** writes only the arguments given the tool name |
| tuning | how much of the backbone is updated: `full` updates every weight, `lora` trains small adapter matrices and merges them at the end |
| trajectory | one task run of the agent model: thinking, calls, results, step by step |
| split | a named task list of the environment; AppWorld has `train`, `dev`, `test_normal`, `test_challenge`. The dataset step maps them to its three piles train, val, test |
| cut point | a sentence boundary inside the thinking where a training example is sliced; **max cuts** caps how many per step (64 today) |
| example, event | one cut point with the call that followed; the unit the trainer counts |
| threshold, theta | the probe fires when its confidence exceeds a threshold, called theta in the code; eval fits the value at which the false-fire rate stays under a **risk target** (5 and 10 percent today); the live run takes theta as a number written by hand (METHOD.md axis 4) |
| injection format | where the fetched result is written back: **p1** inside the thinking, **p2** after the thinking closes; **e1** explains the mechanism inline, **e2** explains it once in the system prompt; **note** is the old inline form |
| harmony | gpt-oss's prompt format with channels; the repo renders it token for token like the server does. The `api` of a generation file is `harmony`, `chat`, or `raw` |
| generation settings | temperature, top_p, max tokens, reasoning effort, the pinned date; today called a preset |
| arm | one complete run inside a settings file that lists several variants |
| piece | one process of a run that handles a slice of a task list; pieces have their own logs and, for GPU processes, their own cards |
| role | what a process is for: `server` (vLLM), `probe` (the probe service), `client` (a task runner), `train`, `eval` |
| heartbeat, verdict, refire | a progress line a script writes to its log; the monitor's judgment of a piece (alive, stalled, dead, done); relaunching a dead piece with its recorded command |
| gpu-run | the reviewed launch procedure every GPU job goes through: check free cards, smoke, commit, `run.py launch`, monitor, wrap up. A skill in .claude/skills |
| smoke | a small run of the same settings that proves the wiring before the real run |
| dirty tree | uncommitted changes in git; launches from a dirty tree are refused so a recorded commit matches the code that ran |
| read-only tool | a tool call that is safe to execute early because it changes nothing; a feature that lets the probe fire only on those, built but never launched |
| alignment gate | a check run before training that the fast packed trainer computes the same loss as the slow row-by-row reference |
| selfcheck | `run.py selfcheck`: verifies every registry row, settings file, model key, and script path resolves |
| track | one phrase naming the research thread a run serves; the ledger requires it |
| interpreter | which venv runs a script; `cprobe` is `cprobe-env`, the venv of the probe steps |
| acceptance check | after a server starts, a request that proves it answers correctly (reasoning and content present, a tools request accepted) |
| the debugger | stepping through the trainer line by line in VS Code; `demo/` holds fixtures small enough for that |
| ledger | `runs.jsonl`: one event per run start and finish; RESULTS.md is rendered from it |
| gyb | the repo owner |

## 3. Target tree

Everything under `pipeline/` moves up one level. File names stay where they
already say what the file does; cryptic names change. Every module name is
unique across the tree, because scripts put several sibling directories on
one import path. The two ledger files keep their home in `ops/` until the
last commit of the migration (section 9), because other sessions write them.

```
new1/
  README.md         one page: the five steps, this tree with one line per
                    file, how to run a step, the glossary of 2.1
  CLAUDE.md         the rules for running code (section 8), about 60 lines
  TRAPS.md          measured silent failures in code that still exists
  METHOD.md  DATA.md  WORKPLAN.md  TIMELINE.md  RESULTS.md
                    kept as they are; gyb re-roles them afterward

  run.py            front door. `run.py <step> <setting>` runs a CPU step
                    here; `run.py launch <step> <setting>` fires a GPU
                    step; `run.py chain <setting>` runs the upstream steps
                    a setting needs; `run.py find`, `run.py where`,
                    `run.py note`, `run.py selfcheck`
  registry.py       the tables: STEPS, METHODS, interpreters (today the
                    tables inside run.py)
  settings_loader.py  reads and validates a settings file; stdlib only,
                    because four venvs import it (today preset_loader.py
                    plus model_registry.py)

  settings/         every hand-written input: the model table, the named
                    generation settings, and one file per run of a step
    models.json       per agent model: weights on NFS, served name, serve
                      flags, env, max model length, tokenizer, acceptance
                      checks; per backbone: weights (4.9)
    generation/       temp1_high.json      named generation settings (4.6)
    sample/           appworld_gptoss_temp1_4traj.json
    dataset/          appworld_gptoss_temp1_maxcut64.json
    train/            probes_on_maxcut64.json
    eval/             eval_probes_on_maxcut64.json
    inject/           format_where_result_goes.json

  sample/           steps 1 and 5 run the agent here (today pipeline/collect,
                    envs/collect, and the live driver under pipeline/inject)
    run_appworld.py   the AppWorld driver: runs tasks, writes trajectories;
                      with a probe attached it is the live run of step 5
                      (today run_appworld.py plus live_appworld.py)
    chat.py           the request rows of the api axis (4.7): chat, harmony,
                      raw; the harmony row streams in chunks and is where a
                      probe attaches (today common.py plus the stream half
                      of live_appworld.py)
    harmony_render.py message list -> gpt-oss prompt tokens, identical to
                      the server's own rendering; the one renderer (today
                      this file under inject plus a second template in
                      common.py)
    serve.py          start a vLLM server for a model on a card and run its
                      acceptance checks (today serve_preset.py plus three
                      scripts under envs/serve_logs)
    gen_launch.py     a sample setting -> server and client launch scripts
    runs -> NFS       symlink to the trajectory root (today envs/runs)

  dataset/          step 2 (today pipeline/annotate)
    build.py          trajectories -> train/val/test examples and reports
    param_label.py    argument-span labels for the cparam method
    check_callstr.py  gates on the built dataset: call strings read back,
                      model purity, no unit in two piles
    rules.py          cut points, sentence boundaries, call parsing, one
                      block per environment
    readonly/         the read-only tool labels (which calls are safe)
    data -> NFS       symlink to the dataset root (today pipeline/data)

  train/            step 3
    trainer_base.py   shared trainer spine: version gate, the argument
                      block, seed, logging, backbone lookup (new; today
                      copied into each trainer)
    share_data.py     builds the packed batches: which examples share a
                      prefix, the masks, the token budget, where the probe
                      reads
    train_causal_tool.py    trains ctool
    train_causal_share.py   trains cgen and cparam with the packed forward
                            pass (the cache-reuse trainer)
    rowwise_cgen.py   the slow row-by-row reference for cgen that the
                      alignment gate compares against (today
                      train_causal_callgen.py)
    rowwise_cparam.py the same for cparam (today train_causal_param.py)
    lora_util.py      LoRA: flags, target modules, merge and save
    readonly_map.py   loads dataset/readonly for the read-only feature
    verify/           the two kernel and memory checks that produced
                      RESULTS rows (today .scratch/kvshare-train/verify)
    runs -> NFS       symlink to the probe run root (today pipeline/runs)

  eval/             step 4; reports land inside the probe's run directory
    eval_tool.py      ctool: fits the threshold on val, freezes it on test
    eval_call.py      cgen and cparam (today eval_causal_call.py plus
                      eval_causal_param.py; --mode picks)
    matrix.py         backbone x method table (today summarize_matrix.py)

  inject/           step 5, the probe side (today pipeline/inject; the
                    offline replay line is deleted, so "inject" now means
                    the live run; the driver is sample/run_appworld.py)
    probe_server.py   the GPU service that scores prefixes and generates
                      calls for the probe
    inject_format.py  the injection-format table (five rows today)
    world.py          AppWorld save, execute, rollback primitives (new;
                      harvested from exec_calls.py)
    rebuild.py        rebuilds the exact prompt of a recorded trajectory
                      and checks the system prompt is verbatim
    parse_call.py     extracts a call from generated text, stdlib only
    score_live.py     a live run -> LIVE_REPORT
    ident3_gate.py    pre-launch check that the server's prompt tokens equal
                      the repo's rendering (catches an unpinned date)
    check_bundle.py   loads a trained probe in a fresh process to prove the
                      saved weights are complete
    runs -> NFS       symlink to the live run root (today no link in the
                      tree; the NFS directory pipeline/inject/runs exists)

  figures/          one plain script per figure, run by hand; each names
                    the run ids it reads (new)
    figlib.py         style, one color per backbone and per method, and a
                      loader from run ids to a table

  chain.py          runs the upstream steps a setting needs, in order,
                    resumable (today pipeline/driver.py)

  cluster/          launch a step on a GPU, watch it (today ops/)
    launch.py         probe free cards, start tmux sessions, register in
                      three places, refire a dead piece (today launch_cmd,
                      launch_common, launch_probe, launch_eval)
    monitor.py        tails heartbeats, judges each piece, serves the
                      terminal table and the web page (today sampler,
                      verdicts, gpu_jobs)
    heartbeat.py      the progress protocol, stdlib only (unchanged)
    gpu_state.md      cluster facts: hosts, aliases, drivers, card quirks
    env_locks/        what is installed in each venv, one lock per venv

  ops/              the ledger home (unchanged until the final commit,
                    then it moves into cluster/)
    record.py         writes the ledger and renders RESULTS.md
    runmeta.py        writes commit and command into an output directory
    runs.jsonl        the run ledger
    jobs.json         the job ledger: what is on which card right now

  logs/             untracked; one log per tmux session, the chain's state
  cprobe-env/       the venv the probe steps run in (unchanged position)
  envs/             third-party benchmark clones and venvs, nothing tracked;
                    envs/runs stays as the trajectory root the generated
                    launchers write to
  demo/             fixtures and a walkthrough for stepping through the
                    cache-reuse trainer on CPU in the debugger
  tests/            automated checks; each file pins one module's behavior
                    with small fixtures and fails when an edit changes it
  plans/            plan and status documents, plus archive/ (ancient memory)
  docs/agents/      ticket conventions used by ticket-run
  .claude/skills/   gpu-run (shortened; its card probe script stays here),
                    exp-status, ticket-run
  .claude/agents/   gpu-runner, env-runner, job-monitor
```

Answers to the comments on the first draft:

- There is no `models/` directory in the repo: weights live on NFS under
  `/net/.../y-guo/models`, the table that names them is a settings file,
  and `serve.py` sits in `sample/` because starting the agent model's
  server is the first thing steps 1 and 5 do. Environment adapters live in
  `sample/`, one per environment, because sampling is where an
  environment's API is spoken. An adapter is never named after the package
  it imports, because Python would then import the script instead of the
  package.
- The live run is not a second program. Both drivers already write the
  same four record kinds per task (meta, gen, env, final); the live one
  adds the injection fields to gen. So `sample/run_appworld.py` is the one
  task loop, the probe is an attachment to its streaming request row, and
  `inject/` holds the probe side only.
- `driver.py` becomes `chain.py`: it runs the steps a setting depends on,
  in order, and resumes after a stop. It is orchestration, not an
  environment.
- `ops/` becomes `cluster/`: the tools that put a step on a GPU and watch
  it. Nothing research-specific lives there. The ledger files stay under
  `ops/` until the end of the migration and then move too.
- `tests/` are automated checks. Each file exercises one module with small
  fixtures and fails when the module's behavior changes. They run before
  every commit of the migration.
## 4. Settings files

This is the center of the design. Every run of every step starts from one
JSON file under `settings/<step>/<name>.json`.

### 4.1 The identity rule

- The settings name is the run id, the output directory name, and the
  ledger key. Names are unique across all steps and against the run
  directories already present under each output root; selfcheck enforces
  both. This binds every run launched after the migration.
- A settings file written for a run that already exists (the np821 and p1
  batches, section 9 phase 1) carries a `legacy` block mapping each of its
  runs to the existing run id and output directory, for example
  `{"qwen06_full_ctool": {"run_id": "np821b06_gptoss_ctool", "outdir": "pipeline/runs/np821b06_gptoss_ctool"}}`.
  Such a file is a provenance record: it is never launched, and `where`,
  `find`, and `chain` read the legacy block instead of deriving the run id
  from the name. selfcheck requires the block on any file whose name is not
  a directory under its root while its runs are in the ledger.
- A settings file that lists arms produces one run per arm. That run's id is
  `<name>__<arm>` and its output directory is `<root>/<name>__<arm>/`. An
  arm name contains no `__`.
- A run with several processes has one piece per process. tmux session
  names are `<run id>_<role><index>`, for example
  `appworld_gptoss_temp1_4traj_server2` and `..._client7`. The run ledger
  has one row per run; the job ledger has one entry per piece with its host
  and card.
- The launcher creates the output directory exclusively and refuses to
  launch when it already exists, so a new name can never write into an old
  run. The one exception is a relaunch: when the ledger says the run at
  that id failed, the launcher moves the old directory to
  `<run id>.failed<N>`, appends an `outdir` event to the failed row, and
  starts the same id again. Both rows stay in the ledger.
- A settings file is frozen when its run starts: the runner copies it into
  the output directory as `settings.json` with every value resolved, the
  generation file inlined under `generation`, and the derived fields filled
  in. Only `notes` and `archived` in the source file change afterward; the
  frozen copy is never edited.
- The runner is `run.py launch` for a GPU step and `run.py <step>` for the
  CPU step. Both do the same work: validate, create the output directory
  exclusively, freeze the settings, translate fields to flags, write the
  ledger start row, run, write the finish row. `launch` adds the card
  probe and the tmux sessions.
- Running the same settings again for another result is another seed, not
  another file (`seed` in 4.2; `traj_per_task` and `seeds` in 4.5). A
  dataset or train setting whose `seed` is a list produces one run per
  value: the loader expands the list into arms named `<arm>_s<seed>`, or
  `s<seed>` for a file without arms, before anything else reads the file,
  so every later rule sees ordinary arms. The frozen copy of each run
  holds its one seed and the name of the arm it repeats. A dead piece of a
  running job is refired by the monitor's existing mechanism; a run that
  stopped as a whole is relaunched under its own id as above.

### 4.2 Two kinds of fields

A settings file has launcher fields and script parameters.

**Launcher fields** are defined by the per-step tables in 4.5. The common
ones:

| Field | Meaning and shape |
|---|---|
| `step` | one of sample, dataset, train, eval, inject |
| `name` | equals the file name without extension |
| `track` | one phrase: which research thread this run serves |
| `source` | the upstream runs this one consumes, by name; the per-step table says whether it is one name, a list, or a map from role to name |
| `cards` | a list of records `{"role": ..., "host": ..., "gpu": ...}`, plus `"arm"` when the record belongs to one arm; one record per process that needs a card; the launcher refuses a process with no matching record |
| `arms` | a map from arm name to overrides of any field; each arm is one complete run |
| `smoke` | true makes every script run on its small subset; the name must end in `_smoke` |
| `seed` | dataset and train: an integer, or a list that makes one run per value (4.1); sample and inject take one seed per trajectory under `params` instead |
| `archived` | true when the human has given up on the attempt (4.10); default false. Per-run progress (planned, running, done, failed) lives in the ledger |
| `notes` | free text: why this exists, what happened, remarks on the numbers |
| `legacy` | only on a file written for runs that already exist (4.1) |

**Derived fields** are filled in by the loader and appear only in the frozen
copy: `env` and `model` come from the sample setting at the top of the
`source` chain, so a train, eval, or inject setting never restates them.

**Script parameters** sit under `params`. A key is a flag of the script
without the leading dashes (`--events-per-mb` becomes `events_per_mb`); a
list value is joined with commas for a flag that takes one string. A key not
written takes the script's default, and the frozen copy records the
resolved value. When a step runs more than one program, `params` is keyed
by role: `client` and `probe` for inject, `client` for sample, one key per
method for eval; a train arm carries its own `params`. Each block is checked
against the script that role or method runs.

The check works without importing the scripts: each STEPS and METHODS row
in `registry.py` lists the flags its script accepts, and one test per script
runs inside that script's own venv and diffs the list against the live
argument parser. The loader rejects a key the list does not contain and a
missing required key, so a typo fails at load time and not thirty hours
later.

Launcher fields that the runner translates into flags, so the settings
file can use plain words: `backbone` becomes `--base`, `tuning: lora`
becomes `--lora`, `pieces` becomes `--num-shards` plus one `--shard-id` per
piece, `probe_on: false` becomes `--no-probe`. The dataset builder is driven
by a config file rather than flags, so for step 2 the runner writes that
config from the settings fields (the mapping is under step 2 in 4.5).

Numbers live in the ledger only. `run.py record finish` writes them there,
and `run.py find` shows them next to the settings. `notes` is free text
where gyb may write anything, including numbers as remarks; the ledger stays
the authoritative copy.

### 4.3 Where outputs go

Each step has one output root on NFS, reached through one symlink in the
step's directory. NFS is `/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1`.
The roots are today's roots; nothing on NFS moves, and old and new runs
share the same directories.

| Step | Output directory | Symlink |
|---|---|---|
| sample | `<nfs>/envs/runs/<run id>/<env>_<model>/` | `sample/runs` |
| dataset | `<nfs>/pipeline/data/<run id>/<model>/` | `dataset/data` |
| train | `<nfs>/pipeline/runs/<run id>/` | `train/runs` |
| eval | reports into the train run directory it scores; its own frozen settings and RUNMETA under `<train run dir>/eval/<eval run id>/` | (same root) |
| inject | `<nfs>/pipeline/inject/runs/<run id>/` | `inject/runs` |
| matrix | `<nfs>/pipeline/runs/MATRIX_<eval name>_r<risk>.md`, owned by the eval settings file that produced it | `train/runs` |

The inner level of sample and dataset directories is fixed by today's
readers: the dataset builder recognizes the model from the `<env>_<model>`
suffix, and every dataset consumer joins `<model>` onto the dataset root.
Both facts get a row in TRAPS.md.

Eval reports keep today's file names in the train run directory, because
the call evals, the probe service, and the matrix read them there. A later
eval of the same arm overwrites the reports; both eval rows stay in the
ledger, and `run.py where` on a report path answers with the latest one.

Every run directory made after the migration holds `settings.json` (the
frozen copy) and `RUNMETA.json` (commit, command, dirty list). Runs made
before the migration keep their directories; phase 3 appends one `outdir`
event per old run id to the ledger, so `run.py where` and `run.py find`
cover them without rewriting a line. The source differs per step: RUNMETA
files on NFS for train, eval, and inject runs; the generated launcher
directory for sample runs; the batch config plus the build report for the
two datasets, which have no RUNMETA.

### 4.4 The ledger and the three commands

A run's ledger rows carry: run id, step, track, settings path, output
directory, commit, host, card, start, finish, status (planned, running,
done, failed), and the numbers. Rows written before the migration say `ok`
or `fail`; the readers map those to done and failed. The job ledger carries one entry per piece
with its host, card, tmux session, and log.

`run.py where <path>` prints the settings file and the ledger row that
produced a path, for any path under a run directory:

```
$ run.py where train/runs/probes_on_maxcut64__qwen06_full_cgen/best
settings/train/probes_on_maxcut64.json   arm qwen06_full_cgen
run id  probes_on_maxcut64__qwen06_full_cgen   status done
start   2026-09-20 14:02   finish 2026-09-21 08:10   commit 3f1c2a9
source  dataset appworld_gptoss_temp1_maxcut64
numbers best_val 0.71
```

`run.py find` lists runs by condition, across steps and arms, with status,
numbers, and output directory. Nested fields use dots. For a run that has
not started, `find` reads the source file and follows the generation
reference; for a started run it reads the frozen copy.

```
$ run.py find --step train --where method=cgen --where backbone=qwen06
$ run.py find --where archived=true
$ run.py find --step sample --where generation.temperature=1.0
```

Runs that repeat one arm with several seeds are one group to `find` and to
`run.py matrix`: both print, per arm, the number of seeds and the mean and
spread of each number, with the single runs listed below the group.

`run.py note <run id or settings name> "<text>"` appends a dated line to
`notes` in the source settings file. The frozen copy is never edited;
`find` shows notes from the source file.

Referring to a run when talking to an agent is saying its run id.

### 4.5 Each step's settings

The examples describe today's real batch. Values not shown take the script
defaults.

**Step 1, sample.**

| Field | Required | Shape |
|---|---|---|
| `env`, `model` | yes | keys into the environment adapters and the models table |
| `generation` | yes | the name of a file under `settings/generation/` |
| `servers` | yes | list of `{host, gpu, card, port, flags?}`; one vLLM instance each; `flags` is appended to the model's serve flags |
| `clients` | yes | list of `{split, pieces, ports, exp}`; one task runner per split; `pieces` splits its task list into that many processes, each bound to one port in `ports`; every port must name a declared server; `exp` is the experiment name the environment itself requires |
| `params` | no | keyed by role; `client` holds flags of `sample/run_appworld.py`: `traj_per_task`, `seeds`, `max_steps`, ... |

`cards` is derived from `servers`; clients need no card.

`traj_per_task` with `seeds` says how many trajectories each task gets and
the seed of each one, so a bigger sample or a repeated one is a longer seed
list in the same run. Trajectories sampled later go into a second sample
setting, and the dataset setting lists both as `source`.

```json
{"step": "sample", "name": "appworld_gptoss_temp1_4traj",
 "track": "probe training data at temperature 1",
 "env": "appworld", "model": "gptoss", "generation": "temp1_high",
 "servers": [{"host": "tokyo108", "gpu": 2, "card": "H100", "port": 8103},
             {"host": "tokyo108", "gpu": 3, "card": "H100", "port": 8106},
             {"host": "tokyo108", "gpu": 4, "card": "H200", "port": 8107},
             {"host": "tokyo108", "gpu": 5, "card": "H200", "port": 8108}],
 "clients": [{"split": "train",       "pieces": 4, "ports": [8103, 8106, 8107, 8108], "exp": "gptr"},
             {"split": "dev",         "pieces": 2, "ports": [8103, 8106], "exp": "gpdv"},
             {"split": "test_normal", "pieces": 6, "ports": [8103, 8106, 8107, 8108, 8103, 8106], "exp": "gptn"}],
 "params": {"client": {"traj_per_task": 4, "seeds": [42, 67, 4267, 6742]}},
 "notes": "first temperature-1 batch: 4 trajectories per task, equal weight per step (2026-08-21 ruling); 315 tasks, 1260 trajectories",
 "legacy": {"": {"run_id": "nyapass", "outdir": "envs/runs/nyapass/appworld_gptoss"}}}
```

**Step 2, dataset.** Runs on CPU; no `cards`. The builder reads a config
file, so the runner writes that config from the settings: `env` and
`model` from the source chain, the source runs' trajectory directories,
the output directory of 4.3, `split_files`, `max_cuts`, `seed`, the
trajectories per task (the sample's `traj_per_task`, or the smaller value
below), and the run name as the builder's family key.

| Field | Required | Shape |
|---|---|---|
| `source` | yes | one sample run id or a list of them |
| `split_files` | yes | `{train, val, test}` to the task-list files of the piles |
| `max_cuts` | yes | integer; today 64 |
| `seed` | yes | integer, or a list for one run per value (4.1) |
| `traj_per_task` | no | use only the first k trajectories of each task, in seed order; default: every trajectory the source holds. New: one builder flag (section 10 item 8) |
| `params` | no | flags of `dataset/build.py`: `weight_mode` (uniform or per_event) |

```json
{"step": "dataset", "name": "appworld_gptoss_temp1_maxcut64",
 "track": "probe training data at temperature 1",
 "source": "appworld_gptoss_temp1_4traj",
 "split_files": {"train": "envs/appworld/data/datasets/train.txt",
                 "val":   "envs/appworld/data/datasets/dev.txt",
                 "test":  "envs/appworld/data/datasets/test_normal.txt"},
 "max_cuts": 64, "seed": 42,
 "params": {"weight_mode": "uniform"},
 "notes": "max_cuts 64: the untruncated distribution is p50 60 / p90 246 / max 842; 64 keeps 186479 examples (2026-08-22 ruling)",
 "legacy": {"": {"run_id": "nyapass_aw_v1", "outdir": "pipeline/data/nyapass_aw_v1/gptoss"}}}
```

**Step 3, train.**

| Field | Required | Shape |
|---|---|---|
| `source` | yes | one dataset run id |
| `method` | yes, top level or per arm | a METHODS key |
| `backbone` | yes, top level or per arm | a backbones key of the models table |
| `tuning` | yes, top level or per arm | `full` or `lora` |
| `seed` | yes, top level or per arm | integer, or a list for one run per value (4.1); becomes the trainers' `--seed` (today a constant 42 in each trainer; the flag moves into trainer_base.py) |
| `cards` | yes | one record per arm (or one record for a file without arms); the runs of a seed list share their arm's card and run in sequence, unless a record names the seed too |
| `params` | no | flags of the arm's trainer: for ctool `bs`, `accum`, `lr`, `epochs`, `max_len`, `grad_ckpt`, `align_tol`, ...; for cgen and cparam `events_per_mb`, `accum`, `lr`, `epochs`, `max_len`, `tok_budget`, `grad_ckpt`, ... |

"Required" means present after the arm's overrides are applied; a field may
sit at the top level, in the arm, or be split between them. Every arm is
listed explicitly; there is no cross-product shorthand. The example shows
six of the twelve arms today's batch ran (three methods on four
backbone-and-tuning pairs: qwen06 full, qwen17 full, qwen17 lora, qwen4
lora); the legacy block maps each arm to its existing run.

```json
{"step": "train", "name": "probes_on_maxcut64",
 "track": "first probes on the temperature-1 data",
 "source": "appworld_gptoss_temp1_maxcut64",
 "seed": 42,
 "params": {"max_len": 8192, "accum": 1, "epochs": 1},
 "arms": {
   "qwen06_full_ctool":  {"method": "ctool", "backbone": "qwen06", "tuning": "full",
                          "params": {"bs": 8, "lr": 1e-5, "align_tol": 3e-4}},
   "qwen06_full_cgen":   {"method": "cgen",  "backbone": "qwen06", "tuning": "full",
                          "params": {"events_per_mb": 8, "lr": 1e-5}},
   "qwen17_full_ctool":  {"method": "ctool", "backbone": "qwen17", "tuning": "full",
                          "params": {"bs": 8, "lr": 1e-5, "grad_ckpt": true}},
   "qwen17_full_cgen":   {"method": "cgen",  "backbone": "qwen17", "tuning": "full",
                          "params": {"events_per_mb": 8, "lr": 1e-5, "grad_ckpt": true}},
   "qwen17_lora_ctool":  {"method": "ctool", "backbone": "qwen17", "tuning": "lora",
                          "params": {"bs": 8, "lr": 5e-4}},
   "qwen17_lora_cgen":   {"method": "cgen",  "backbone": "qwen17", "tuning": "lora",
                          "params": {"events_per_mb": 8, "lr": 5e-4}}
 },
 "cards": [{"arm": "qwen06_full_ctool", "role": "train", "host": "tokyo108", "gpu": 0},
           {"arm": "qwen06_full_cgen",  "role": "train", "host": "tokyo108", "gpu": 1},
           {"arm": "qwen17_full_ctool", "role": "train", "host": "tokyo108", "gpu": 2},
           {"arm": "qwen17_full_cgen",  "role": "train", "host": "tokyo108", "gpu": 3},
           {"arm": "qwen17_lora_ctool", "role": "train", "host": "tokyo106", "gpu": 0},
           {"arm": "qwen17_lora_cgen",  "role": "train", "host": "tokyo106", "gpu": 1}],
 "notes": "",
 "legacy": {"qwen06_full_ctool": {"run_id": "np821b06_gptoss_ctool", "outdir": "pipeline/runs/np821b06_gptoss_ctool"},
            "qwen06_full_cgen":  {"run_id": "np821b06_gptoss_cgen",  "outdir": "pipeline/runs/np821b06_gptoss_cgen"}}}
```

Run ids: `probes_on_maxcut64__qwen06_full_cgen` and so on for a file
launched after the migration. The top-level `params` are defaults; an arm
overrides any field. To repeat one arm three times, give that arm
`"seed": [42, 67, 4267]`: the runs are
`probes_on_maxcut64__qwen06_full_cgen_s42` and so on, the other arms keep
the top-level seed, and the matrix shows the arm once with its mean and
spread.

**Step 4, eval.**

| Field | Required | Shape |
|---|---|---|
| `source` | yes | one train settings name; every arm of it is evaluated |
| `risk_targets` | yes | list of allowed false-fire rates; eval_tool fits one threshold per entry, largest first; the call evals use the first entry |
| `cards` | yes | one record per arm |
| `params` | no | keyed by method; each block holds flags of that method's eval script: `ctool` takes `overlong`, ...; `cgen` and `cparam` take `bs`, `max_new_tokens`, ... |

For each arm, the METHODS row of its method says which eval script runs and
which other arm it needs: cgen and cparam need the ctool arm whose
`backbone` and `tuning` fields equal their own; the runner finds it by
those two fields, not by name, and refuses an arm without a partner.

```json
{"step": "eval", "name": "eval_probes_on_maxcut64",
 "track": "first probes on the temperature-1 data",
 "source": "probes_on_maxcut64",
 "risk_targets": [0.10, 0.05],
 "cards": [{"arm": "qwen06_full_ctool", "role": "eval", "host": "tokyo108", "gpu": 0},
           {"arm": "qwen06_full_cgen",  "role": "eval", "host": "tokyo108", "gpu": 0},
           {"arm": "qwen17_full_ctool", "role": "eval", "host": "tokyo108", "gpu": 1},
           {"arm": "qwen17_full_cgen",  "role": "eval", "host": "tokyo108", "gpu": 1},
           {"arm": "qwen17_lora_ctool", "role": "eval", "host": "tokyo106", "gpu": 0},
           {"arm": "qwen17_lora_cgen",  "role": "eval", "host": "tokyo106", "gpu": 0}],
 "notes": ""}
```

Run ids: `eval_probes_on_maxcut64__qwen06_full_cgen` and so on. Two arms on
one card run in sequence. When every arm is done, `run.py matrix <eval
setting>` writes the matrix of 4.3.

**Step 5, inject.**

| Field | Required | Shape |
|---|---|---|
| `env`, `model`, `generation` | yes | as in step 1 |
| `servers` | yes | as in step 1: the vLLM instances, `{host, gpu, card, port, flags?}` |
| `probe` | yes | `{host, gpu, port, tool, call, theta}`: where the probe service runs, the two train run ids it loads, and the threshold as a number written by hand (the eval report shows the fitted value; copying it here is the human step METHOD.md axis 4 requires) |
| `split`, `exp` | yes | the environment's task list, and the experiment name the environment requires |
| `pieces` | yes | client processes per arm, spread over the servers' ports in turn |
| `arms` | usually | overrides; `format` and `probe_on` are the axes that vary today |
| `params` | no | keyed by role: `client` holds flags of `sample/run_appworld.py`, the same driver as step 1 (`traj_per_task`, `seeds`, `max_steps`, and the probe flags `max_inject_per_step`, `chunk_tokens`, ...); `probe` holds flags of `inject/probe_server.py` (`device`, `events`, ...) |

`cards` is derived from `servers` and `probe`; clients need no card. A
repeat of a live arm is the same thing as in step 1: several trajectories
per task, one seed each, inside one run; the scorer reports each seed and
the mean. An arm with `probe_on` false runs the same loop with no scoring
and no probe service.

```json
{"step": "inject", "name": "format_where_result_goes",
 "track": "injection format axis",
 "env": "appworld", "model": "gptoss", "generation": "temp1_high",
 "servers": [{"host": "tokyo108", "gpu": 0, "card": "H100", "port": 8114},
             {"host": "tokyo108", "gpu": 1, "card": "H100", "port": 8115}],
 "probe": {"host": "tokyo105", "gpu": 0, "port": 8790,
           "tool": "probes_on_maxcut64__qwen06_full_ctool",
           "call": "probes_on_maxcut64__qwen06_full_cgen",
           "theta": 0.9},
 "split": "dev", "exp": "fmt", "pieces": 12,
 "params": {"client": {"traj_per_task": 3, "seeds": [42, 67, 4267], "max_inject_per_step": 1}},
 "arms": {"inside_thinking": {"format": "p1_e1"},
          "after_thinking":  {"format": "p2_e1"},
          "old_note":        {"format": "note"},
          "no_probe":        {"format": "note", "probe_on": false}},
 "notes": "does the result help more inside the thinking or after it closes; no_probe is the baseline with the same machinery and no firing"}
```

Run ids: `format_where_result_goes__inside_thinking` and so on. The servers
and the probe service are shared by the arms and start once; the clients
are per arm.

### 4.6 Generation settings and the three-way split

`settings/generation/<name>.json` is not a run settings file. It holds what
the agent model generates with, and its required fields are `name`, `api`,
`temperature`, `top_p`, `max_tokens`, `reasoning_effort`, `start_date`.
Its names are their own namespace.

```json
{"name": "temp1_high",
 "api": "harmony", "reasoning_effort": "high", "temperature": 1.0, "top_p": 1.0,
 "max_tokens": 8192, "start_date": "2026-08-06",
 "notes": "the temperature-1 setting every batch since 2026-08-21 uses"}
```

A sample or inject setting names it, so two runs that share generation
settings share the file and its name. This is today's preset with a new
home. The trajectory metadata keeps its `preset` key, filled with this name.

The rule for where a server fact lives: if it changes when you swap the
model, it is in `settings/models.json` (weights, served name, serve flags,
environment variables, max model length, tokenizer); if it changes when you
swap the card, it is in the settings file (host, gpu, card type, port, and
extra flags for that instance); if it changes what the model generates, it
is in the generation file.

### 4.7 Arms and axes

An arm is one complete run. The file's top-level values are the defaults
and each arm overrides some of them, any field at all. An axis is a field
whose legal values come from one table in one module:

| Axis | Field | Values today | Where the table is |
|---|---|---|---|
| injection format | `format` | note, p1_e1, p1_e2, p2_e1, p2_e2 | `inject/inject_format.py` |
| probe on or off | `probe_on` | true, false | the live driver's `--no-probe` switch |
| method | `method` | ctool, cgen, cparam | `registry.py` METHODS |
| backbone | `backbone` | qwen06, qwen17, qwen4 | `settings/models.json` |
| tuning | `tuning` | full, lora | `train/lora_util.py`; a switch plus LoRA's own flags |
| example weighting | `params.weight_mode` | uniform, per_event | `dataset/build.py` |
| request row | `api` of a generation file | `chat` (the server renders, one request per step), `harmony` (the repo renders, streamed in chunks; the only row a probe attaches to), `raw` (a client-side Qwen template) | `sample/chat.py` |
| generation | `generation` | the files under `settings/generation/` | |

Adding a variant to a table axis is one row. The scripts build their
argparse choices from the table, so nothing else knows the row exists; the
backbone axis also accepts a weights path, for a one-off trial. A variant is
never an `if` on a name spread across scripts. Fields with a fixed value set
that are not axes: `env` (one adapter per value), `role`, the ledger's
progress status.

### 4.8 The METHODS table

A probe method is a row in `registry.py`:

```python
METHODS = {
  "ctool": dict(
      interp="cprobe", train="train/train_causal_tool.py", train_args=[],
      evals=[dict(script="eval/eval_tool.py", args=["--head", "causal"],
                  run_flag="--run", needs=None,
                  report="REPLAY_REPORT.json",
                  cols={"theta":    ["test_frozen", "$risk", "theta"],
                        "fire_acc": ["test_frozen", "$risk", "trig_acc"]})]),
  "cgen": dict(
      interp="cprobe", train="train/train_causal_share.py", train_args=["--mode", "cgen"],
      evals=[dict(script="eval/eval_call.py", args=["--mode", "cgen"],
                  run_flag="--cgen-run", needs=("ctool", "--ctool-run"),
                  report="CALLGEN_REPORT.json",
                  cols={"full_call_ok": ["full_call_ok"]})]),
  "cparam": dict(
      interp="cprobe", train="train/train_causal_share.py", train_args=["--mode", "cparam"],
      evals=[dict(script="eval/eval_call.py", args=["--mode", "cparam"],
                  run_flag="--cparam-run", needs=("ctool", "--ctool-run"),
                  report="PARAM_REPORT.json",
                  cols={"params_all_ok": ["pred_tool", "params_all_ok"]})]),
}
```

One row says which interpreter and script train the method, how to
evaluate it (several evaluations allowed), which other method's run it
needs and by which flag, which report file the numbers land in, and the
path to each number the matrix shows. `$risk` is replaced by each value of
the eval setting's `risk_targets`, giving one column per value, named
`theta@0.05`, `theta@0.1`. The launcher passes `backbone` as `--base` to
every trainer. The full column set of each row is copied from today's
reports during phase 3; the paths shown here were checked against them.
The report file names are historical and stay for compatibility. `run.py matrix <eval setting>` enumerates the arms of the train settings
file the eval names, reads each arm's reports, and writes the matrix file
of 4.3; the old mode that scans a directory by run-id prefix stays for
runs made before the migration. Today this fact is spread over four tables
in run.py, a branch in the eval launcher, and three places in the matrix
script.

### 4.9 The models table

```json
{"agents": {
   "gptoss": {"full": "gpt-oss-120b", "weights": "/net/.../models/gpt-oss-120b",
              "served": "gpt-oss-120b", "tokenizer": null,
              "serve": {"flags": "--gpu-memory-utilization 0.92", "max_model_len": null,
                        "env": {"LD_LIBRARY_PATH": "envs/cuda-compat-13.0",
                                "VLLM_USE_FLASHINFER_SAMPLER": "0",
                                "CUDA_DEVICE_ORDER": "PCI_BUS_ID"},
                        "checks": ["reasoning_and_content", "tools_request"]},
              "note": "own replica, accepted 2026-07-28"},
   "q35": {"full": "qwen3.5-27b", "weights": "/net/.../zhou-y/models/Qwen3.5-27B",
           "served": "qwen3.5-27b",
           "serve": {"flags": "--reasoning-parser deepseek_r1 --max-model-len 65536 --gpu-memory-utilization 0.92 --enable-auto-tool-choice --tool-call-parser qwen3_coder",
                     "env": {"CUDA_DEVICE_ORDER": "PCI_BUS_ID"},
                     "checks": ["reasoning_and_content", "tools_request"]},
           "note": "old line; datasets on NFS"}},
 "backbones": {
   "qwen06": {"weights": "/net/.../models/Qwen3-0.6B-Base"},
   "qwen17": {"weights": "/net/.../models/Qwen3-1.7B-Base"},
   "qwen4":  {"weights": "/net/.../models/Qwen3-4B-Base"}}}
```

One table, read by the sample launcher, the trainer spine, the matrix, the
probe service (tokenizer), and the server launcher. `checks` lists which
acceptance checks `serve.py` runs after start; the three scripts under
`envs/serve_logs` become entries of one check table. The old agent models
stay as rows so the datasets built from them on NFS can still be rebuilt.
Today the model list is written in seven places, and the 1.7B and 4B
backbones are in the trainers' own dicts but not in the model file.

### 4.10 Archiving a method that did not work

Set `archived` to true in its settings files and write the reason in
`notes`. Delete its METHODS row and scripts; git history keeps them. Add one
TIMELINE entry. The settings files stay: selfcheck checks an archived file
for shape only and does not resolve its method or scripts, so
`run.py find --where archived=true` lists every attempt that failed, with
why, and the ledger still holds its numbers. The settings directory is the
archive of what was tried.

### 4.11 Running a chain, and smoke runs

`run.py chain eval_probes_on_maxcut64` follows `source` upward (eval to
train to dataset to sample) and works through the steps whose runs are not
done. It runs the CPU step itself, stops after the cut statistics so gyb can
rule on `max_cuts`, and at each GPU step prints the launch command and stops;
the launch goes through gpu-run, and the chain resumes afterward. A full
chain from sample to eval has three GPU stops. An inject setting is chained
through the train runs named in `probe`.

A smoke run is a settings file whose name ends in `_smoke` and has
`"smoke": true`. The STEPS table in `registry.py` maps that flag to each
script's own switch (`--smoke` on the trainers, `--limit` on the evals,
`--n` on the task runners). The smoke file for a real setting is a copy with
the suffix, so the wiring proof and the real run are findable side by side.

## 5. The scenarios in the target tree

| Scenario | What you do | Files |
|---|---|---|
| Add an agent model of a known family | one entry in settings/models.json; one sample setting | 2 |
| Add an agent model of a new family | the two above, plus its acceptance checks in sample/serve.py and, when its prompt format is not harmony, a renderer next to harmony_render.py | 2 + code |
| Add a probe backbone | one entry in settings/models.json | 1 |
| Change generation settings | one file under settings/generation; name it in a sample or inject setting | 1 |
| Add a training method | one trainer importing trainer_base.py; one METHODS row; an arm or a train setting | 3 |
| Add an evaluation method | one script under eval/ writing a report; one entry in the method's evals list | 2 |
| New dataset, same environment | one dataset setting, plus a sample setting if new trajectories | 1 or 2 |
| Sample a new environment | one adapter under sample/; one block in dataset/rules.py; one sample setting; the clone under envs/ (untracked) | 3 |
| Run a new environment live | the above plus its save, execute, and rollback primitives next to inject/world.py; the driver is shared | code |
| New figure | one script under figures/ | 1 |
| Try variants side by side | rows in the axis table if new; arms in one setting | 1 |
| Same settings, more or fewer samples | sample and inject: `traj_per_task` and `seeds` in the setting; a smaller dataset from an existing sample: `traj_per_task` in the dataset setting | 1 |
| Repeat a run for the spread | sample and inject: more seeds in the one run; dataset and train: a seed list, one run per value; `find` and `matrix` print mean and spread | 1 |
| Relaunch a failed run | `run.py launch` the same setting again; the failed directory is moved aside and both rows stay in the ledger | 0 |
| Run the steps up to the next GPU launch, resume after it | `run.py chain <setting>` | 0 |
| Archive a failed method | `archived` and notes in its settings; delete its row and scripts; one TIMELINE entry | 0 new |
| Find what produced an output | `run.py where <path>` | 0 |

## 6. What is deleted and what is merged

Deleted, all to git history. Each group is one commit whose message names
it. The rename table is appendix A.

- The ModernBERT probe line: `train_mbert_tool.py`, `train_mbert_extract.py`,
  `input_modes.py`, `eval_mbert_call.py`, the mbert branch of `eval_tool.py`,
  `mbert-env`, its five task entries, its test cases.
- The offline injection line: `replay_inject.py`, `splice_replay.py`,
  `sweep_theta.py`, `launch_plan_sweep.py`, `extract_completed.py`,
  `build_form_table.py`, `form_table.json`, `acceptance.py`,
  `ident3_score.py`, `test_stopfix.py`, `THETA_CURVE.*`, `exec_cache/`, the
  offline half of `exec_calls.py`, the splice and ident3 task entries and
  recipes, `tests/test_splice_replay.py`, the `splice_plan_job.sh`,
  `ident3_job.sh`, `awdiag_job.sh`, `live_smoke_job.sh`, `live_v3_job.sh` and
  `run_gptoss.sh` shells.
- Environments that never ran a batch: the tau2, tales, alfworld adapters,
  `build_dataset.py`, `extract_probe_cases.py`, `score_probe.py`,
  `summarize_full.py`, the four split generators, `envs/alfworld/splits/`,
  `envs/collect/bfcl_gptoss/`, the eight dead configs under
  `pipeline/configs/` (every one except np821 and p1), the manifests w0 and
  c2, the tau2, tales, bfcl, toolhop, StableToolBench task entries, the
  ALFWorld block of `rules.py` once `eval_call.py` no longer imports it.
- One-off server launchers: every `envs/serve_logs/launch_*.py`; the three
  acceptance scripts there (the check table in `sample/serve.py` replaces
  them); `live_arm_job.sh` (its case table of arms, ports, and probe ports
  is what arms and cards in a settings file replace).
- Registry ceremony: the recipe engine and `RECIPES`, the `status` and
  `recipes` subcommands, the legacy live-probe renderer in `gpu_jobs.py`, the
  incident auto-spawn half of `sampler.py` and `tests/test_incidents.py`.
- Documents: `MAP.md`, `CONTEXT.md` (its live terms are section 2.1 and go
  into README), `.scratch/` except `kvshare-train/verify/`, `talks/`,
  `learn/`, `docs/plans/`, `docs/design/`, the probe-pipeline, handoff and
  paper-write skills (the extension checklists of probe-pipeline become the
  one-line scenarios of section 5 in README; its split-name dependency
  notes go to TRAPS.md), the deploy-scout and paper-verifier agents,
  `accept_v3diff.py` and its report, `readonly/gen_tables.py`,
  `ACCEPT_EVAL.md`, the two `accept_bfcl_v3*` directories, `sweep_lr.py`,
  `sweep_preset.py`.
- In phase 3, after their settings files exist: the 22 card tables under
  `ops/`, `pipeline/configs/np821_gptoss.json`, `p1_gptoss.json`,
  `manifest_np821.json`, `manifest_p1.json`, `configs/presets/`,
  `configs/models.json`.

The p1 batch is a real AppWorld batch (a dataset, twelve probe runs, two
matrices on NFS); its settings files are written in phase 1 next to np821's
so its provenance survives.

Merged:

| Today | Target |
|---|---|
| configs/models.json, gen_launch MODEL_TABLE and its family flag strings, rules MODEL_OF, matrix --models default, three trainer MODELS dicts | settings/models.json |
| CELLS, CELL_ORDER, EVAL_CELLS, per-cell task entries, launch_eval's branch, the matrix's three copies | registry.py METHODS |
| pipeline/configs/<batch>.json, manifest_<batch>.json, ops/<batch>*_placement.json | settings/<step>/<name>.json |
| configs/presets/*.json | settings/generation/<name>.json (client block) and settings/models.json (server block) |
| eval_causal_call.py, eval_causal_param.py | eval/eval_call.py, same report names |
| the blocks copied into each trainer (version gate, heartbeat shim, args, force guard, seed, backbone lookup) | train/trainer_base.py |
| ops/launch_cmd.py, launch_common.py, launch_probe.py, launch_eval.py | cluster/launch.py |
| ops/sampler.py, verdicts.py, gpu_jobs.py | cluster/monitor.py |
| model_registry.py, preset_loader.py (its merge order and the temperature-required check, whose two callers are repointed) | settings_loader.py at the root, stdlib only |
| serve_preset.py, three acceptance scripts | sample/serve.py with a check table |
| pipeline/collect, envs/collect | sample/ |
| envs/collect/run_appworld.py, pipeline/inject/live_appworld.py | sample/run_appworld.py: one task loop; the probe hook on the streaming request row is the only addition |
| common.py's hand-assembled harmony template, pipeline/inject/harmony_render.py | sample/harmony_render.py, the one renderer, checked against the server by ident3_gate |
| exec_calls.py's world primitives (including the deferred `load_steps`), replay_inject's harmony constants | inject/world.py |
| extending.md section 5, MAP.md section 5, run.py pitfall notes | TRAPS.md |
| CLAUDE.md's how-to-run half, MAP.md overview, CONTEXT.md glossary, extending.md's checklists | README.md |

Not merged: `train_causal_callgen.py` and `train_causal_param.py` define the
same fourteen names with different bodies and every caller picks one by
module; they are renamed to `rowwise_cgen.py` and `rowwise_cparam.py` and
kept as two modules.

## 7. What stays, and what breaks if it goes

The review flagged these as things that look removable and are not. Each is
written as "X stays because removing it breaks Y". Finer implementation
details of the same kind go into TRAPS.md during phase 5.

- The dirty-tree gate stays because a recorded commit is worth nothing when
  the tree that ran was different. Its exemption for the ledger files stays
  because the launcher writes the ledger, and without the exemption the
  second launch of a session is blocked by the first.
- The launcher's three registrations happen in a fixed order, and a failed
  ledger write aborts the launch, because a run that is on a card but not in
  the ledger is invisible to the monitor and to `run.py where`.
- The finish command checks that the job is really gone before it
  deregisters, because a job was once deregistered while still running for
  another hour and a half.
- `heartbeat.py` and `settings_loader.py` use only the standard library,
  because four different venvs import them and none has the same packages.
- The training log's event names and the `best/` layout stay, because the
  chain, the monitor, the sweep reader, and the eval scripts parse them.
- The alignment gate and the two row-wise reference modules stay, because
  they are the only proof that the fast packed trainer computes the same
  loss as the plain one.
- The eval scripts fingerprint the probe weights into their cached logits,
  because re-scoring old logits against retrained weights would give wrong
  numbers with no error.
- `harmony_render.py`, the verbatim system prompt check, and `ident3_gate.py`
  stay, because the whole comparison between a probe arm and its baseline
  rests on the repo rendering the prompt token for token as the server does.
- The `note` row of the format table stays byte for byte, because every
  live run before 2026-09-12 used it and scoring old runs reads it.
- `max_cuts` at 64 is a ruling recorded in TIMELINE, not a constant to tune.
- The sample launcher forces the inner output directory name to
  `<env>_<model>`, because the dataset builder recognizes the model from
  that suffix and skips a directory it cannot recognize without an error.
- The chain refuses `--allow-dirty`, stops after the cut statistics for a
  human ruling, and hashes its source setting, because an edited setting
  with a stale generated launcher once pointed at the wrong card.

## 8. Rules

These go into CLAUDE.md, together with the running-code rules that stay:
GPU work through gpu-run, every task through run.py, commit before launch,
big outputs on NFS, no guessing about results, English on disk.

1. Every run of a step starts from one settings file, and the file's name is
   the run id, the output directory, and the ledger key.
2. A settings file is frozen when its run starts; only the archive mark and
   the notes change afterward. Running it again for another result is
   another seed; running it again after a failure is a relaunch of the
   same run.
3. Each fact is written in one place, and every other place imports it.
4. A variant is a table row or a settings value, never a branch on a name.
5. A new method is one METHODS row plus the scripts the row names, in the
   same commit.
6. A file that no step imports is deleted; git history keeps it.
7. Every tracked file is reachable from registry.py, from a settings file,
   or from a test, and selfcheck enforces it.
8. A measured trap gets one row in TRAPS.md. A decision that changes the
   plan gets one entry in TIMELINE.md.

## 9. Migration

Branch `renew` in a separate worktree, since other sessions share the main
tree. One commit per phase, each ending with `python3 run.py selfcheck` and
the full unittest run green. Three things keep working throughout and the
heading of each phase says which of them its gate exercises: the AppWorld
chain (C), the cache-reuse trainer (T), and the injection-format live run
(L). No NFS path moves. The ledger code and files (`ops/record.py`,
`ops/runmeta.py`, `runs.jsonl`, `jobs.json`, the locks, and the three
literal copies of the ledger path prefix) stay under `ops/` until the last
commit of phase 6, after the final merge from main, because other sessions
keep writing them.

Appendix A is the rename table; every phase greps against it.

### Phase 0: clear the desk (on main, before the branch)

- gyb's trainer edit lands with the device rule of section 10 item 1.
- The two fmt_smoke jobs finish and are deregistered. The nine ledger rows
  with a start and no finish (fmt_smoke_probe, fmt_smoke_srv, ident3_v1_srv,
  and the six p1 LoRA cgen and cparam runs) are closed once by hand.
- The two recipe state files under `logs/recipe/` are the only record of
  which commit built each live dataset; copy each into its dataset directory
  on NFS as `BUILD_PROVENANCE.json`.
- The launcher passes the output directory to the ledger at start, so a
  dirty launch saves its patch. Two lines; before anything else.
- Create the missing symlink to the live run root on NFS
  (`pipeline/inject/runs`) after checking nothing under that path sits in
  home.

### Phase 1: settings files first, then deletions (gate: C)

- Write `settings/generation/temp1_high.json` and `temp0_high.json`, the
  five settings files of section 4.5, and the sample, dataset, train and
  eval settings of the p1 batch, by hand from today's configs, manifests,
  card tables, and presets, while those inputs still exist. Write
  `settings_loader.py`.
- Harvest before deleting: `APPWORLD_SEED`, `TRUNC`, `CKPT`, `requote`,
  `error_kind`, and the deferred `load_steps` from `exec_calls.py`;
  `DEFAULT_STOP` and the harmony markers from `replay_inject.py`; into
  `inject/world.py`. Repoint `live_appworld.py`. Find deferred imports by
  grepping every `import` line, not only the module top.
- Delete the groups of section 6 except the last one. In the same commit:
  inline the three annotate-chain steps into the chain's build step (the
  chain calls the recipe engine today); prune the entry-point list in
  `tests/test_preset.py` to the survivors; delete the tests of deleted
  modules; flip `eval_tool.py`'s `--head` default to causal; shrink the
  `--env` choices to the environments that exist; remove `recipe` and
  `status` from CLAUDE.md; rewrite the DATA.md sentences that name the
  recipe.
- Gate: selfcheck, unittest with zero errors, `run.py show pipeline` prints,
  and the chain's dataset build on the existing sample run into a scratch
  directory byte-compared against the dataset on NFS.

### Phase 2: reshape directories, no logic (gate: C, T, L)

- `git mv` into the tree of section 3 using appendix A, except the ledger
  code and files. Files that appendix A merges many-to-one move under their
  own names into the target directory here (`cluster/launch_cmd.py`,
  `eval/eval_causal_call.py`, `sample/live_appworld.py`, and so on) and
  collapse in phase 4. In the
  same commit: rewrite the 52 script paths in run.py's tables; every
  `parents[N]` count and every literal directory name in a moved file,
  including `gpu_jobs.py`'s path to the card probe script and the two
  cwd-relative literals in `train/verify/`; the 26 test files that carry
  `pipeline/` or `ops/` path literals or import the renamed row-wise
  modules; `demo/prepare.py`'s imports of the row-wise module; the three
  program paths in `.vscode/launch.json` and the path in `demo/README.md`;
  the eleven `.gitignore` rules keyed to old paths; recreate the symlinks
  with `ln -s` at their new positions (`sample/runs`, `dataset/data`,
  `train/runs`, `inject/runs`; `envs/runs` stays for the generated
  launchers) and add their bare names to `.gitignore`; regenerate the
  client launcher on NFS for the existing sample run because it hardcodes
  the adapter's path.
- Gate: selfcheck, unittest, the demo on CPU, the dataset build
  byte-compared again, `rebuild.check_system_verbatim()` on a recorded
  trajectory, and one `live_appworld --selftest-shadow`.

### Phase 3: tables and the ledger (gate: C, L)

- `settings/models.json` with agents and backbones, and the backbone key
  rename (`qwen` to `qwen06`) applied to its consumers listed in appendix
  A; `registry.py` METHODS and STEPS with the report key paths copied from
  today's reports; the matrix reading the table; the sample launcher
  reading server facts from the model table and generation from the
  settings; `eval_tool.py` gains a `--risk-targets` flag replacing its
  constant and sorts the values largest first, so the report key order
  stays as today; the loader derives `env` and `model` from the source
  chain and expands a seed list into arms (4.1); `dataset/build.py`'s
  config reader takes the config the runner writes and gains the
  `traj_per_task` subset (section 10 item 8); the launcher's relaunch of a
  failed run (4.1); the STEPS and METHODS rows gain their accepted-flag
  lists with one per-venv test each; the ledger fields of 4.4 and the
  `outdir` events for old runs, appended from the per-step sources of 4.3;
  `run.py find`, `run.py where`, `run.py note`, with the seed grouping of
  4.4 in `find` and `matrix`; selfcheck rewritten to validate settings
  files instead of presets; `tests/test_preset.py` rewritten against
  `settings_loader.py`.
- Then delete the last group of section 6.
- Gate: the chain's own byte-for-byte rebuild check on the existing dataset;
  regenerate the matrix files that exist on NFS through the old
  directory-scan mode and diff the value columns only (the header is
  already English since 6bde35b, the two ModernBERT rows are gone, and the
  run ids are the old ones); regenerate all three sample artifacts (`launch_servers.py`, `launch_clients.sh`,
  `MANIFEST.md`) and diff, with the expected line changes listed up front;
  dry-run the launcher for the four job-ledger pieces that carry a task name
  and compare argument shapes; `run.py where` on one old and one new output
  directory; `ident3_gate` against a running server.

Refire of a job launched before the migration is not supported; relaunch it
from its settings file. The old ledger command strings are an archive.

### Phase 4: the file merges (gate: T, C, L)

- `train/trainer_base.py` (every trainer gains `--seed`, default 42,
  replacing its constant), then `eval_call.py`, `cluster/launch.py`,
  `cluster/monitor.py`, `sample/serve.py`. The row-wise modules are renamed
  only. Last, the driver merge: `sample/run_appworld.py` absorbs
  `live_appworld.py`, `sample/chat.py` absorbs its streaming client as the
  harmony row with the probe hook, `sample/harmony_render.py` replaces the
  template in `chat.py`, and `score_live.py` groups by seed.
- Gate per merge: its tests; `--align-only` for cgen and cparam on the
  existing dataset; re-score the existing ctool run with cached logits and
  diff its report byte for byte; re-score the existing cgen and cparam runs
  on a fixed 50-event subset through gpu-run and diff; one smoke launch
  from a `_smoke` settings file that lands three ledger entries; the demo
  walkthrough's fifteen stops repointed at the lines they moved to.
- Gate for the driver merge: five tasks at temperature 0 through the chat
  row and through the harmony row give the same reasoning and content per
  step, or the first divergence is explained in TRAPS.md; a no-probe run
  of the merged driver builds a dataset that passes the dataset gates;
  `--selftest-shadow` passes; `ident3_gate` against a running server.

### Phase 5: inject, documents, skills (gate: L)

- `probe_server.py`'s default run paths become required arguments.
  `README.md`, `CLAUDE.md`, `TRAPS.md` written; `MAP.md` and `CONTEXT.md`
  deleted; the gpu-run skill cut to the steps a command cannot do.
- One TIMELINE entry carrying appendix A and the list of deleted lines.
  Entries before the renewal keep naming the old tree.
- Gate: `git grep` for every old path and every old module name in appendix
  A returns nothing in tracked `*.py`, `*.sh`, `.vscode/*.json`,
  `demo/*.md`, `.claude/`, `CLAUDE.md`, `README.md`, `registry.py`, except
  the ledger rows of appendix A, which move in phase 6; one live arm
  launched from the inject settings file and scored.

### Phase 6: prove the chain (gate: C, T, L)

- One 20-task sample through `run.py chain` on the new tree, sample through
  matrix, from `_smoke` settings files, plus one inject arm. Check that the
  run id is one path segment of the NFS output directory, the leading
  segment of every tmux session name, and the ledger key, and that the
  commit message carries the settings name. Merge main into `renew`, move
  the ledger code and files into `cluster/` with their path literals, run
  the phase 5 grep without its exemption, merge `renew` into main.

## 10. Open items for gyb

Each has a default. Silence means the default.

1. The device rule. Your uncommitted trainer edit rejects every device that
   is not CUDA, and the CPU demo and the debugger walkthrough pass cpu.
   Default: the flag defaults to cuda, accepts cpu only when written
   explicitly, and rejects anything else. This changes your edit, so it is
   your call.
2. Auto-finishing a run on the monitor's done verdict. Default: not
   adopted; finish stays a manual command.
3. The read-only feature: should the probe be allowed to fire only on calls
   that are safe to run early? The feature exists, ten modules import it,
   and it was never launched. Default: kept this round, listed in WORKPLAN.
4. `talks/` and `learn/`. Default: deleted from the repo; git history keeps
   them.
5. The names of the settings files for today's lines. Default: the names in
   section 4.5 for np821 and fmt; `appworld_gptoss_temp0` and
   `appworld_gptoss_temp0_dataset` for the p1 batch (temperature 0, one
   trajectory per task). These files carry legacy blocks pointing at the
   existing run ids (nyapass, nyapass_aw_v1, np821b06_gptoss_ctool, p1,
   aw_p1_v1, and so on), so the old directories and ledger rows stay as
   they are.
6. The old agent models q35 and q36. Default: they stay as rows in the
   models table so their datasets on NFS can be rebuilt.
7. The firing threshold in an inject setting. METHOD.md axis 4 says theta
   is always written by hand. Default: kept; the eval report shows the
   fitted value and you copy it. The alternative is a reference to the eval
   run and a risk target, which would be a TIMELINE entry changing the
   method rule.
8. A smaller dataset from an existing sample. Today the builder takes every
   trajectory the source holds, so two sample counts mean two sampling
   runs. Default: the dataset setting gains `traj_per_task` (the first k
   trajectories of each task in seed order), about twenty lines in the
   builder, added in phase 3.

## 11. Expected result

| Item | Today | Target |
|---|---|---|
| Tracked files | 456 | about 130 |
| Python outside tests | 32.7k lines | about 19k |
| Tests | 9.5k lines | about 8.5k |
| Markdown | 24.5k lines | about 5k |
| Registry rows | 83 tasks | five steps, three methods, about 12 tools |
| run.py | 1,309 lines | about 350, tables in registry.py |
| Places declaring models | 7 | 1 |
| Places declaring methods | 7 | 1 |
| Agent drivers | 2 (sampler, live) | 1 |
| Harmony renderers | 2 | 1 |
| Files per family of runs | 5 plus card tables | 1 per step |

## Appendix A: rename table

Paths:

| Old path | New path |
|---|---|
| pipeline/collect/gen_launch.py | sample/gen_launch.py |
| envs/collect/run_appworld.py | sample/run_appworld.py |
| pipeline/inject/live_appworld.py | sample/live_appworld.py in phase 2, merged into sample/run_appworld.py and sample/chat.py in phase 4 |
| pipeline/inject/harmony_render.py | sample/harmony_render.py |
| envs/collect/common.py | sample/chat.py |
| pipeline/annotate/build.py, param_label.py, check_callstr.py, rules.py, readonly/ | dataset/ (same names) |
| pipeline/train/* | train/* (same names, except the two below) |
| pipeline/train/train_causal_callgen.py | train/rowwise_cgen.py |
| pipeline/train/train_causal_param.py | train/rowwise_cparam.py |
| .scratch/kvshare-train/verify/ | train/verify/ |
| pipeline/eval/eval_tool.py | eval/eval_tool.py |
| pipeline/eval/eval_causal_call.py + eval_causal_param.py | eval/eval_call.py |
| pipeline/eval/summarize_matrix.py | eval/matrix.py |
| pipeline/inject/* (surviving files) | inject/* (same names), except the two rows above |
| envs/serve_logs/live_arm_job.sh | deleted (section 6) |
| pipeline/driver.py | chain.py |
| serve_preset.py | sample/serve.py |
| configs/models.json | settings/models.json |
| configs/presets/<name>.json | settings/generation/<name>.json |
| pipeline/configs/{np821,p1}_gptoss.json + pipeline/collect/manifest_{np821,p1}.json + ops/{np821,p1}*_placement.json | settings/{sample,dataset,train,eval}/... |
| preset_loader.py + model_registry.py | settings_loader.py |
| ops/launch_cmd.py + launch_common.py + launch_probe.py + launch_eval.py | cluster/launch.py |
| ops/sampler.py + verdicts.py + gpu_jobs.py | cluster/monitor.py |
| ops/heartbeat.py, gpu_state.md, env_locks/ | cluster/ (same names) |
| ops/record.py, runmeta.py, runs.jsonl, jobs.json, *.lock | cluster/ (same names; last commit of phase 6) |
| pipeline/data (symlink, untracked) | dataset/data |
| pipeline/runs (symlink, untracked) | train/runs |
| (none today) | inject/runs -> NFS pipeline/inject/runs |
| envs/runs (symlink, untracked) | sample/runs, and envs/runs kept |

Module and key names:

| Old name | New name | Consumers to rewrite |
|---|---|---|
| `train_causal_callgen` (module) | `rowwise_cgen` | train_causal_share.py (five call sites), tests/test_share_trainer.py, tests/test_cparam_assembly.py, tests/test_share_gen_eval.py, demo/prepare.py, demo/WALKTHROUGH.md |
| `train_causal_param` (module) | `rowwise_cparam` | same files |
| `pipeline/train/train_causal_share.py` (path) | `train/train_causal_share.py` | `.vscode/launch.json` (three program paths), `demo/README.md`, `demo/WALKTHROUGH.md` |
| the batch config keys `official_split_files`, `max_bounds`, `run_family`, `model_short`, `trajs_per_unit` | written by the runner from the dataset settings (4.5 step 2) | `dataset/build.py`'s config reader, `chain.py` |
| backbone key `qwen` | `qwen06` | the three trainer dicts (deleted), train_causal_share.py:1029, tests/test_share_trainer.py:51, tests/test_share_gen_eval.py:54, demo/prepare.py, the card tables (deleted) |
| `--max-bounds` (config key `max_bounds`) | settings field `max_cuts`, written into the builder's config by the runner | chain.py, dataset/build.py's config reader |
