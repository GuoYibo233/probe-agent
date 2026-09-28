# new1 from zero: the contracts (draft A)

Draft A, 2026-09-17. The interfaces between the files of the fourth draft's tree
(`notes/plans/2026-09-14-structure-from-zero.md`, Part 1), written before any
code. The tree is fixed: no file is added, removed, moved, split or renamed.
Every mechanism below lands in a file that tree already names.

Angle of this draft: the simplest thing that works. Every mechanism kept is
followed by the failure it prevents, in one clause. Where a reviewer's fix needs
a file the tree does not have, the fix is not applied; it is listed in Part 9(b)
as a proposal for gyb.

Sources read: the fourth draft; the synthesis
(`notes/plans/2026-09-17-structure-review-synthesis.md`) and the four reviews
beside it; the third draft's deleted Part 2 (`git show
771a6e5:plans/2026-09-14-structure-from-zero.md`); `notes/CONTEXT.md`; the old
code under `legacy/` (`pipeline/inject/live_appworld.py`, `exec_calls.py`,
`inject_format.py`, `probe_server.py`, `parse_call.py`,
`pipeline/annotate/rules.py`, `build.py`, `pipeline/eval/eval_tool.py`,
`eval_causal_call.py`, `pipeline/train/train_causal_tool.py`,
`train_causal_share.py`, `share_data.py`, `envs/collect/run_appworld.py`,
`common.py`, `ops/record.py`, `heartbeat.py`, `verdicts.py`, `gpu_jobs.py`,
`launch_common.py`, `run.py`, `configs/`).

Terms follow `notes/CONTEXT.md`: probe, cut, fire, inject, launch, heartbeat,
piece, refire, verdict. Two terms are used in one meaning only, against today's
usage: **record** always means the task record on disk, never a ledger line (a
ledger line is a **row**); **environment** always means a benchmark, never a
venv (a venv is named by its directory under `external/`).

---

## Part 0. The tree, annotated

The entries below are the fourth draft's Part 1 tree, in its order, file for
file. Each code file carries five annotation lines:

- **imports** — the repo files it imports (third-party packages in brackets).
- **used by** — the repo files that import it.
- **reads** / **writes** — the disk formats or files it touches.
- **venv** — `any`, `appworld`, `probe` or `vllm`. `any` means: importable in
  all three venvs, because the heavy package import sits inside the function
  that needs it.

These annotations are the contract; `run.py selfcheck` verifies the imports and
used-by lines against the real import statements, so they cannot rot.

### Root

```
README.md      for the future reader: the tree, one line per file, how to run, the extension recipes
               written by: a person and by agents when the tree changes
               read by: run.py selfcheck (it compares the file list and the "used by" lines against the code)
CLAUDE.md      the rules an agent reads on its own
```

```
run.py
  purpose : the one command: run one or several named settings of one workflow file;
            ls, where, find, free, kill, sync, selfcheck
  imports : experimental_settings/schema.py, jobs/registry.py, jobs/launch.py [stdlib]
  used by : nobody
  reads   : experimental_settings/*.yaml (through schema), every run directory's
            done.json / meta.json / heartbeat/*.json, jobs/runs.jsonl
  writes  : jobs/runs.jsonl rows (start rows through launch.py, finish rows on a walk),
            jobs/RESULTS.md, the run directory's settings.yaml and meta.json at creation
  venv    : probe (the login-machine interpreter; it is the only venv with polars,
            numpy and torch, and key computation imports the versioned modules)
```

### constants/

Locations on this cluster. Nothing here enters a key. Edited when something
arrives or moves on disk.

```
constants/path_datasets.yaml
  purpose : where each environment, its task splits and each dataset live; and the
            interpreter that runs that environment's loop
  read by : data/environments/appworld.py (home, split lists), jobs/launch.py (the venv column)
  writes  : —
constants/path_outputs.yaml
  purpose : where outputs go on NFS (the output root, and the debug root under it)
  read by : experimental_settings/schema.py (run_dir), jobs/registry.py (ls scans the root)
constants/path_models.yaml
  purpose : where each model's weights live (weights alias -> absolute path)
  read by : models/__init__.py
```

### experimental_settings/

Everything in here changes a result. The YAML files are gyb's; agents never edit
them (`.claude/hooks/settings_readonly.sh` refuses).

```
experimental_settings/schema.py
  purpose : the schema of a setting (every field, default, one-line comment, the allowed
            values of each axis), the stage table, and the loader (file -> setting, diff,
            key, run_dir, load_frozen)
  imports : constants/path_outputs.yaml, models/table.yaml, experimental_settings/*.yaml
            [PyYAML, dataclasses]; at call time inside key(), by importlib, the modules
            the stage table names, to read their VERSION
  used by : run.py, jobs/launch.py, jobs/registry.py (run_dir for `where`),
            data/build_dataset.py, agent/loop.py, agent/inject.py,
            models/agent_models/service.py, models/probe_models/service.py,
            train/utils/trainer.py, eval/utils/probe_eval.py, eval/score_run.py
            (stage programs use load_frozen only)
  reads   : experimental_settings/*.yaml, models/table.yaml, constants/*.yaml,
            <run dir>/settings.yaml
  writes  : <run dir>/settings.yaml
  venv    : any
experimental_settings/debug.yaml      sizes only; --debug lays it over any setting
experimental_settings/baseline.yaml   stages [sample, score]; named settings inside
experimental_settings/train_probe.yaml  stages [sample, build, train, eval]
experimental_settings/inject.yaml     stages [inject, score]
  read by : experimental_settings/schema.py only
```

### data/

The benchmark environments, and every format that lives on disk between two
stages.

```
data/__init__.py
  purpose : the conventions the three formats share: read returns a Polars DataFrame with
            the declared columns and types; the id rule; write; the version check
  imports : [polars 1.44.2]
  used by : data/task_record.py, data/example.py, data/prediction.py
  reads   : —   writes : —
  venv    : any
data/environments/__init__.py
  purpose : class Environment (the eleven methods, one line each, no logic) and
            open_env(name), which imports environments/<name>.py inside the function
  imports : constants/path_datasets.yaml [PyYAML, importlib]
  used by : data/environments/appworld.py (subclass), agent/loop.py, agent/inject.py,
            data/build_dataset.py, eval/methods/cgen.py, eval/methods/cparam.py,
            eval/score_run.py
  reads   : constants/path_datasets.yaml   writes : —
  venv    : any
data/environments/appworld.py
  purpose : class AppWorld(Environment): the eleven methods on the AppWorld package, its
            task instructions, its no-code message, its call regex and Python call syntax
  imports : data/environments/__init__.py, constants/path_datasets.yaml
            [the appworld package, imported inside open()]
  used by : data/environments/__init__.py (by importlib, never by name)
  reads   : the AppWorld clone under external/appworld, its split task lists
  writes  : its own per-task output directory, deleted by close()
  venv    : any at import and for the call-syntax methods; appworld for open/step/
            speculate/judge/close
data/task_record.py
  purpose : the record one task run leaves; write, read, is_done, to_messages
  imports : data/__init__.py
  used by : agent/loop.py (write), agent/inject.py (fire and resume rows),
            data/build_dataset.py (read), eval/score_run.py (read)
  reads/writes : the task record (Part 1.1)
  venv    : any
data/example.py
  purpose : the row build writes per probe example; write, read
  imports : data/__init__.py
  used by : data/build_dataset.py (write), train/utils/trainer.py (read),
            train/methods/*.py (read), eval/utils/probe_eval.py (read)
  reads/writes : the example (Part 1.2)
  venv    : any
data/prediction.py
  purpose : the row train writes per example after training; write, read
  imports : data/__init__.py
  used by : train/utils/trainer.py (write), train/methods/*.py (the per-method output
            column), eval/utils/probe_eval.py (read)
  reads/writes : the prediction (Part 1.3)
  venv    : any
data/probe_input.py
  purpose : the cut positions in the reasoning, and the text assembled for the probe;
            one rule offline and live
  imports : [stdlib only]
  used by : data/build_dataset.py, agent/inject.py
  reads   : —   writes : —
  venv    : any
data/build_dataset.py
  purpose : the program: records -> example rows for the three probe methods; the
            train/val/test split; the report; the gates
  imports : experimental_settings/schema.py, data/task_record.py, data/example.py,
            data/probe_input.py, data/environments/__init__.py, jobs/registry.py
  used by : nobody (a program; run.py starts it as `python -m data.build_dataset <run dir>`)
  reads   : the sample run's records, the environment's split task lists
  writes  : examples.parquet, report.json, done.json, heartbeat/<piece>.json in its run dir
  venv    : any (run under probe)
```

### models/

```
models/__init__.py
  purpose : the entrance: agent(alias) and probe(alias) read table.yaml and import the
            family's or backbone's file inside the function
  imports : models/table.yaml, constants/path_models.yaml [PyYAML, importlib]
  used by : models/agent_models/service.py, models/probe_models/base.py,
            agent/loop.py, agent/generate.py, agent/inject.py,
            train/utils/trainer.py
  reads   : models/table.yaml, constants/path_models.yaml   writes : —
  venv    : any
models/table.yaml
  purpose : the model table, one row per alias; keyed columns are expanded into the setting
            before keying, serving-only columns never are
  read by : models/__init__.py, experimental_settings/schema.py (the keyed columns),
            models/agent_models/service.py (the serving columns)
models/agent_models/__init__.py
  purpose : empty, so the client half of service.py imports without the family's libraries
  venv    : any
models/agent_models/gptoss.py
  purpose : gpt-oss's conversation format ("harmony") as plain strings: messages -> prompt
            text, parse a reply, end of turn, the model's own system message, the prefetch
            wrapper for a p2 injection
  imports : [stdlib only]
  used by : models/agent_models/service.py (the render-equals-server check),
            agent/generate.py (parse, end of turn), agent/inject.py (the prefetch wrapper),
            agent/loop.py (messages -> prompt text)
  reads   : —   writes : —
  venv    : any (the official renderer, openai_harmony, is imported inside the check
            function of service.py, never here)
models/agent_models/service.py
  purpose : both ends of the served agent model: start or attach to the vLLM server for a
            table row and check it (main); the loop's client, a raw token stream with a seed
  imports : models/__init__.py, models/table.yaml, models/agent_models/gptoss.py,
            experimental_settings/schema.py (load_frozen), jobs/registry.py
            [stdlib for the client; vllm and openai_harmony inside the server functions]
  used by : agent/generate.py, agent/loop.py, agent/inject.py (the client)
  reads   : models/table.yaml, the weights path   writes : its piece log, heartbeat/<piece>.json
  venv    : any for the client; vllm for the main
models/probe_models/__init__.py
  purpose : empty, so the client half of service.py imports without torch
  venv    : any
models/probe_models/base.py
  purpose : the probe class every backbone shares: load, save, score a prefix, generate a
            call; and the classification head class with its save layout
  imports : models/__init__.py, models/probe_models/qwen.py (by importlib, inside load)
            [torch, transformers, peft]
  used by : train/utils/trainer.py, train/methods/ctool.py, train/methods/cgen.py,
            train/methods/cparam.py, models/probe_models/service.py
  reads/writes : the checkpoint layout (Part 1.6)
  venv    : probe
models/probe_models/qwen.py
  purpose : Qwen's tokenizer quirks, pad token, head attach point, LoRA target modules, dtype
  imports : [transformers]
  used by : models/probe_models/base.py (by importlib, never by name)
  venv    : probe
models/probe_models/service.py
  purpose : both ends of the probe service: the local HTTP server that loads the probes and
            answers score, generate, health (main); the loop's client
  imports : models/probe_models/base.py (inside the server functions),
            experimental_settings/schema.py (load_frozen), jobs/registry.py [stdlib client]
  used by : agent/inject.py (the client)
  reads   : the two referenced run directories (checkpoints, probe report)
  writes  : its piece log, heartbeat/<piece>.json
  venv    : any for the client; probe for the main
```

### agent/

```
agent/loop.py
  purpose : run each task and seed: open, step, parse, act, until done; claim tasks across
            pieces; write the record. Picks the generation step by the setting
  imports : experimental_settings/schema.py (load_frozen), data/environments/__init__.py,
            data/task_record.py, models/__init__.py, models/agent_models/gptoss.py,
            models/agent_models/service.py (client), agent/generate.py, agent/inject.py,
            jobs/registry.py
  used by : nobody (a program)
  reads   : its run dir's settings.yaml, the environment's task list
  writes  : one record per (task, seed), heartbeat/<piece>.json, done.json
  venv    : the environment's venv (appworld today)
agent/generate.py
  purpose : the plain generation step: stream tokens to end of turn; exposes the token
            stream so inject.py iterates it instead of copying it
  imports : models/agent_models/service.py (client), models/agent_models/gptoss.py,
            models/__init__.py
  used by : agent/loop.py, agent/inject.py
  venv    : the environment's venv
agent/inject.py
  purpose : the generation step with the probe: score at each cut, on fire get the call, run
            it early, write the result in, restart from the spliced prefix, roll back on
            mismatch
  imports : agent/generate.py, agent/inject_format.py, data/probe_input.py,
            data/task_record.py, data/environments/__init__.py,
            models/probe_models/service.py (client), models/agent_models/service.py (client),
            models/agent_models/gptoss.py, models/__init__.py,
            experimental_settings/schema.py (load_frozen)
  used by : agent/loop.py
  writes  : fire and resume rows into the record
  venv    : the environment's venv
agent/inject_format.py
  purpose : the table of the five ways an early result is written into the stream
  imports : [stdlib only]
  used by : agent/inject.py; its keys are cross-checked by run.py selfcheck against the
            inject.format axis in schema.py
  venv    : any
```

### train/

```
train/utils/trainer.py
  purpose : the training loop every method shares: settings -> arguments, seed, backbone,
            tuning, checkpoints, metrics, heartbeat, resume, the alignment gate; and its
            last step, the probe run over val and test with one prediction row per example
  imports : experimental_settings/schema.py (load_frozen), models/__init__.py,
            models/probe_models/base.py, data/example.py, data/prediction.py,
            jobs/registry.py [torch, peft]
  used by : train/methods/ctool.py, train/methods/cgen.py, train/methods/cparam.py
  reads   : the build run's examples.parquet
  writes  : best/, last/, train_done.json, predictions.parquet, metrics.jsonl,
            align_check.json, heartbeat/<piece>.json, done.json
  venv    : probe
train/methods/ctool.py
  purpose : the classification probe: its batches, its head, its loss, its validation accuracy
  imports : train/utils/trainer.py, models/probe_models/base.py, data/example.py,
            data/prediction.py, eval/methods/ctool.py (the match function)
  used by : nobody (a program)
  venv    : probe
train/methods/cgen.py
  purpose : the call-generating probe: its packing, its instance strings and target, its loss
            positions, its exact-match validation
  imports : as ctool.py, with eval/methods/cgen.py
  venv    : probe
train/methods/cparam.py
  purpose : the argument-generating probe: its own packing and strings, the arguments as the
            target
  imports : as ctool.py, with eval/methods/cparam.py
  venv    : probe
```

### eval/

Reads what is on disk and computes numbers; no torch, no GPU. numpy and polars
only.

```
eval/utils/probe_eval.py
  purpose : shared by the three methods: read a train run's prediction rows and the example
            rows behind them, bootstrap the confidence interval, write the report; and the
            definition of the probe report format
  imports : data/prediction.py, data/example.py, experimental_settings/schema.py
            (load_frozen), jobs/registry.py [polars, numpy]
  used by : eval/methods/ctool.py, eval/methods/cgen.py, eval/methods/cparam.py
  reads   : the train run's predictions.parquet, the build run's examples.parquet
  writes  : report.json, fires.parquet (the probe report, Part 1.4), done.json
  venv    : probe (numpy and polars; torch is never imported)
eval/methods/ctool.py
  purpose : fit theta on the val rows at the risk targets, freeze it, report on the test rows
  imports : eval/utils/probe_eval.py
  used by : train/methods/ctool.py (the match function)
  writes  : the probe report through probe_eval.py
  venv    : probe
eval/methods/cgen.py
  purpose : exact match of the generated call at the frozen theta
  imports : eval/utils/probe_eval.py, data/environments/__init__.py (parse_call)
  used by : train/methods/cgen.py (the match function)
  reads   : the referenced eval(ctool) run's probe report
  venv    : probe
eval/methods/cparam.py
  purpose : exact match of the generated arguments at the frozen theta
  imports : as cgen.py
  used by : train/methods/cparam.py (the match function)
  venv    : probe
eval/score_run.py
  purpose : a sample or inject run from its records: task success, speculation outcomes,
            tokens and time; by seed; against a baseline
  imports : data/task_record.py, data/environments/__init__.py (parse_call),
            experimental_settings/schema.py (load_frozen), jobs/registry.py [polars]
  used by : nobody (a program)
  reads   : the run's records and the baseline run's records
  writes  : report.json, done.json
  venv    : probe
eval/method_table.py
  purpose : the backbone x method table from the registry; groups sweep children, reports
            mean and spread
  imports : jobs/registry.py [stdlib]
  used by : nobody (a program)
  reads   : jobs/runs.jsonl, each named run's report.json
  writes  : a markdown table on stdout, or into the path given
  venv    : any
```

### jobs/

```
jobs/launch.py
  purpose : pick free cards, one tmux session per piece, the row's start, the alive check,
            refire; and the dirty-tree gate
  imports : experimental_settings/schema.py, jobs/registry.py,
            constants/path_datasets.yaml (the venv column)
            [stdlib; nvidia-smi, tmux, ssh, git as subprocesses]
  used by : run.py
  reads   : the run directory's settings.yaml and records (to release dead claims)
  writes  : the run directory's meta.json launch entries and dirty.patch,
            jobs/runs.jsonl start rows
  venv    : any (run under probe on the login machine)
jobs/registry.py
  purpose : the registry: runs.jsonl rows under a lock, meta.json, the heartbeat,
            ls/where/find/kill, RESULTS.md
  imports : experimental_settings/schema.py (run_dir, for `where`) [stdlib]
  used by : run.py, jobs/launch.py, and every stage program for the heartbeat, meta.json
            and done.json: data/build_dataset.py, agent/loop.py,
            models/agent_models/service.py, models/probe_models/service.py,
            train/utils/trainer.py, eval/utils/probe_eval.py, eval/score_run.py,
            eval/method_table.py
  reads   : jobs/runs.jsonl, every run directory's meta.json / done.json / heartbeat/*.json
  writes  : jobs/runs.jsonl (login machine only), jobs/RESULTS.md,
            <run dir>/meta.json, <run dir>/heartbeat/<piece>.json, <run dir>/done.json
  venv    : any
jobs/runs.jsonl        one row per stage run, appended at start and at finish; in git
jobs/runs.jsonl.lock   the lock every append takes; ignored by git
jobs/RESULTS.md        rendered from runs.jsonl by registry.py; never edited by hand
```

### Everything else in the tree

```
tests/                 empty for now (gyb, 2026-09-17); the four planned checks are in the
                       fourth draft's tree line and are not restated here
.claude/skills/repo-review/SKILL.md          the two-day review procedure
.claude/skills/gpu-run/references/gpu_state.md  cluster notes, read by the gpu-run skill only
.claude/hooks/settings_readonly.sh           refuses any agent edit to experimental_settings/*.yaml
.scratch/review/issues/                      the tasks the review writes
.claude/                                     as today
notes/                                       everything gyb writes by hand
notebooks/             exploration; imports any module, is imported by none, writes no output
                       directory and no row
figures/               one script per figure
external/              the AppWorld clone and its venv, the probe venv, the vLLM venv; nothing
                       in git; "environment" in this tree means a benchmark, never a venv
```

### Count

Python files: root 1 (`run.py`), experimental_settings 1, data 8
(`__init__.py`, `environments/__init__.py`, `environments/appworld.py`,
`task_record.py`, `example.py`, `prediction.py`, `probe_input.py`,
`build_dataset.py`), models 8 (`__init__.py`, `agent_models/__init__.py`,
`agent_models/gptoss.py`, `agent_models/service.py`,
`probe_models/__init__.py`, `probe_models/base.py`, `probe_models/qwen.py`,
`probe_models/service.py`), agent 4, train 4, eval 6, jobs 2. Total **34**,
equal to the fourth draft's count. tests 0.

---

## Part 1. On-disk formats

Four formats cross a stage boundary and are therefore defined once and read by
name: the task record, the example, the prediction, the probe report. Beside
them every run directory holds four fixed files (`settings.yaml`, `meta.json`,
`heartbeat/<piece>.json`, `done.json`) plus a `report.json` that only people and
`eval/method_table.py` read.

Shared conventions, defined in `data/__init__.py`:

- Records are jsonl, one file per task run, written line by line and flushed, so
  a killed piece loses at most its last line. Examples and predictions are
  parquet, written once in bulk.
- Every read returns a Polars DataFrame with the declared columns and types; the
  schema is passed to the reader, so a column missing from an old file reads as
  null instead of changing the frame's shape.
- Every format module holds `VERSION`, an integer, and every file it writes
  carries that number (the record in its `meta` row, parquet in a companion
  `<name>.version` one-line file). A read refuses a file whose version is higher
  than the reading code's. *Failure it prevents: a newer writer's file read
  silently by older code, with a new column dropped.*
- **VERSION rule.** Bump when the same input would now produce a different
  value in an existing column, or when a column is removed. Do **not** bump when
  a column is added: the new column is declared with a default, old files read
  that default, and the key is unchanged. *Failure it prevents: adding one field
  to the record re-keying every sample and inject run, which is days of GPU
  (dependencies P9).*
- **The id rule.** Ids are built by joining their parts with `:`; no part may
  contain a colon.
  - `record_id = "<task_id>:<seed>"`
  - `event_id = "<record_id>:<step>"` — one event is one step whose code block
    contained a call.
  - `example_id = "<event_id>:<cut_index>"` — `cut_index` counts cuts from 0 in
    character order.
  Ids are stable across runs: the same task, seed, step and cut index in another
  run gives the same id, which is what lets the score stage pair an inject run
  with its baseline task by task and seed by seed.

### 1.1 The task record — `data/task_record.py`

One file per task run: `records/<task_id>__s<seed>.jsonl` in the run directory.
One file per (task, seed) rather than one appended file per piece, because the
file is also the claim (Part 2) and because a killed piece must not leave a
half-line in a file other pieces are reading. *Failure it prevents: a partial
line breaking every Polars read of a shared file (lifecycle A5, grounding F6).*

Five row kinds, told apart by `kind`. Today's live record has six
(`legacy/pipeline/inject/live_appworld.py:34-41`): `meta`, `gen`, `spec`,
`resume`, `env`, `final`. `gen` and `env` merge into one `step` row, because
they are always the same step and today's builder joins them by step number and
silently drops the rest of a trajectory when the join fails
(`legacy/pipeline/annotate/build.py:75-80`, `if e is None: break`).

Columns, by row kind. Every column not belonging to a row's kind is null.

| column | type | rows | meaning |
|---|---|---|---|
| kind | str | all | meta / step / fire / resume / final |
| version | int | meta | the `VERSION` of `task_record.py` that wrote the file |
| env | str | meta | the environment name (`appworld`) |
| task_id | str | meta | the benchmark's task id |
| seed | int | meta | the generation seed for this run of the task |
| stage | str | meta | `sample` or `inject`; the only difference between the two records |
| owner | str | meta | the piece's tmux session name; the claim's owner (Part 2) |
| commit | str | meta | the git commit the piece ran at |
| instruction | str | meta | the task text the environment handed out |
| settings_key | str | meta | the run directory's key, so a stray file is traceable |
| started_at | float | meta | unix time at open |
| step | int | step, fire, resume | 0-based step number |
| reasoning | str | step | the model's thinking text for this step |
| content | str | step | the model's answer text for this step |
| action | str | step | the code block the step executed; null when there was none |
| result | str | step | the environment's return, cut at 4000 characters |
| error_kind | str | step | the error class of `result`, null when it was not an error |
| prompt_tok | int | step | prompt tokens billed for this step |
| gen_tok | int | step | generated tokens billed for this step, discards included |
| kept_tok | int | step | generated tokens kept after discards |
| wall_s | float | step | seconds spent in this step |
| n_fires | int | step | how many times the probe fired in this step |
| fire_index | int | fire, resume | 0-based fire number within the step |
| cut | int | fire | character offset of the cut in the reasoning |
| n_checked | int | fire | how many cuts had been scored when this one fired |
| score | float | fire | the probe's confidence at the cut |
| pred_label | str | fire | the tool name the score probe predicted |
| pred_call | str | fire | the call the generation probe wrote |
| exec_code | str | fire | the executable form of `pred_call` after requoting |
| arg_modes | list[str] | fire | which requote branch each argument took |
| exec_out | str | fire | the early call's output, cut at 4000 characters |
| exec_ok | bool | fire | whether the early call ran without an error |
| exec_error_kind | str | fire | the error class of `exec_out`, null when it was not an error |
| note | str | fire | the exact text spliced into the stream |
| format | str | fire | the injection format used |
| head_tok | int | fire | tokens kept from the model's own output at the splice |
| note_tok | int | fire | tokens the note added |
| dropped_tok | int | fire | tokens discarded from after the cut |
| dropped_chars | int | fire | characters discarded from after the cut |
| match_tok | int | resume | how many tokens of the resent continuation matched the discarded ones |
| identical | bool | resume | whether the resent continuation reproduced the discarded one entirely |
| steps | int | final | number of steps run |
| completed | bool | final | whether the environment said the task was done |
| abort | str | final | why the run stopped early; null when it did not |
| success | bool | final | the environment's verdict on the task |
| judge | str | final | the environment's full verdict, as json text |
| finished_at | float | final | unix time at close |

A record is **done** when its last row is a `final` row with `abort` null. That
is also the resume criterion and the claim release criterion.

Dropped from today's record, each with its reason: `gen_ids` and `overflow_ids`
(the whole step's token ids, about half the file's bytes; their only consumer was
the 2026-08-18 identity investigation, whose answer is now the `match_tok` and
`identical` columns, computed live in `agent/inject.py` where the ids are in
memory); `prefix_sha` (a hash of the prompt ids for arm-to-arm comparison, a
one-off); `n_chunks`, `head_tail`, `head_ends_ws` (stream-shape diagnostics);
`text_ids_consistent` (a warning the score stage never used).

Written by `agent/loop.py` (meta, step, final) and `agent/inject.py` (fire,
resume). Read by `data/build_dataset.py` and `eval/score_run.py`. Defined in
`data/task_record.py`, which also offers `to_messages(record)` — the
conversation as the model saw it, used live by the loop and offline by nothing
else, so the two can never drift.

### 1.2 The example — `data/example.py`

One parquet per build run: `examples.parquet`. One row per (event, cut).

| column | type | meaning |
|---|---|---|
| example_id | str | `<event_id>:<cut_index>` |
| event_id | str | `<record_id>:<step>` |
| record_id | str | `<task_id>:<seed>` |
| task_id | str | the benchmark task |
| seed | int | the seed of the record it came from |
| step | int | the step of the record it came from |
| split | str | `train`, `val` or `test` |
| cut | int | character offset of the cut in the reasoning |
| cut_index | int | 0-based index of the cut within the event |
| n_cuts | int | how many cuts the event has |
| depth | float | `cut / len(reasoning)`, rounded to 4 places |
| text | str | what the probe sees: the task, the clipped tool history, the thinking so far |
| label | str | the tool the step actually called (ctool's target) |
| call | str | the normalized full call, `tool(k=v, k=v)` (cgen's target) |
| args | list[struct{key: str, value: str}] | the named arguments in call order (cparam's target) |

No `method` column and no `target` column: the three methods read the same rows
and each takes its own target from `label`, `call` or `args`. *Failure it
prevents: three datasets per sample where one suffices, and a cgen run trained on
a ctool build.*

No weight column: every cut carries weight 1. Today's `per_event` weighting
(`w = 1/m_i`) survives only as the switch for one 2026-08 acceptance line and is
dropped.

No token-count columns. Today's `n_full_tokens` exists for the `--overlong
drop-event` and `skip` modes of the evaluator; this draft keeps only
left-truncation, so the count is not needed and the example row stays free of
the probe tokenizer.

Written by `data/build_dataset.py`. Read by `train/utils/trainer.py` (batching),
`train/methods/*.py` (targets) and `eval/utils/probe_eval.py` (labels and depth
for scoring). Defined in `data/example.py`.

### 1.3 The prediction — `data/prediction.py`

One parquet per train run: `predictions.parquet`. One row per example of the
splits named in `train.predict.splits`, uniform across methods.

| column | type | meaning |
|---|---|---|
| example_id | str | the example this prediction is for |
| split | str | `val` or `test` |
| method | str | `ctool`, `cgen` or `cparam` |
| output | str | ctool: the predicted label; cgen: the generated call; cparam: the generated arguments |
| score | float32 | ctool: the largest softmax probability at temperature 1; null for the generating methods |
| logits | list[float32] | ctool: the class logits in the label order of the train run's `meta.json`; null for the generating methods |

`logits` is the one heavy column (about 150 floats per row, roughly 150 MB per
run at today's label count). It is the price of principle 7: temperature is
fitted on the CPU in `eval/methods/ctool.py`, so a calibration change costs
seconds instead of a GPU rerun. *Failure it prevents: a calibration fix that can
only be applied by retraining (grounding F1).*

The label order lives in the train run's `meta.json` under `stage_extra.labels`,
not in a separate `label_map.json`. *Failure it prevents: a fifth undefined file
with no owner (grounding F7).*

Written by `train/utils/trainer.py`. Read by `eval/utils/probe_eval.py`. The
event id, label and depth a metric needs are not copied here; `probe_eval.py`
joins the prediction rows to the example rows on `example_id`, finding the build
run through the train run's `meta.json`. *Failure it prevents: two copies of the
label, which drift when the build is rebuilt.*

### 1.4 The probe report — defined in `eval/utils/probe_eval.py`

Written by `eval(ctool)` into its run directory, in two files:

`report.json` — the scalars, read by `eval/methods/cgen.py`,
`eval/methods/cparam.py` and `models/probe_models/service.py`:

| field | type | meaning |
|---|---|---|
| version | int | the `VERSION` of `probe_eval.py` |
| stage_key | str | the key of this eval run |
| train_key | str | the key of the train run it scored |
| temperature | float | the softmax temperature fitted on val |
| risks | list of objects | one per risk target, see below |
| grid | list of objects | every theta on the sweep grid with its val numbers, for a person |
| n_events | object | events in val and in test |
| commit | str | the commit the eval ran at |

Each entry of `risks`: `risk` (float), `theta` (float or null when no theta on
the grid meets the constraint), `coverage`, `trigger_accuracy`, `earliness`,
`wrong_fire_rate`, and `ci` (the 95% bootstrap interval of the first three,
resampled by task).

`fires.parquet` — one row per (risk, event) that fired, read by
`eval/methods/cgen.py` and `eval/methods/cparam.py`:

| column | type | meaning |
|---|---|---|
| risk | float | the risk target this selection belongs to |
| event_id | str | the event |
| example_id | str | the first cut of the event whose score reached theta |
| score | float32 | that cut's score |
| depth | float | that cut's depth |

The generating evals join their own prediction rows to this table on
`example_id`, so the fire rule is executed once, in one file. *Failure it
prevents: the replay-to-first-crossing rule existing in three files, as it does
today (`legacy/pipeline/eval/eval_tool.py:236`, `eval_causal_call.py:536-549`,
`eval_causal_param.py:363-365`, each marked "copied verbatim").*

The live probe service reads `report.json` for `temperature` only; theta is a
setting field, because the glossary makes theta a value a person gives.

### 1.5 The run directory's own files

Every stage run directory is `<output root>/<stage>/<key>/` (Part 3) and holds:

| file | written by | read by | contents |
|---|---|---|---|
| settings.yaml | run.py (through `schema.save`) at creation | every piece of that stage, through `schema.load_frozen` | the fully resolved setting, every section and field, plus `_key`, `_stage`, `_upstream` (stage -> key), `_versions` (module -> int), `_debug` |
| meta.json | jobs/registry.py | run.py, jobs/launch.py, jobs/registry.py, the next stage | see below |
| heartbeat/&lt;piece&gt;.json | each piece, through jobs/registry.py | jobs/registry.py (`ls`) | `{done, total, unit, ts, host, session, pid, status}`, rewritten in place each beat |
| done.json | the stage, through jobs/registry.py, created with O_EXCL | run.py, jobs/launch.py, the next stage | `{stage, key, finished_at, counts, status: "ok"}` |
| report.json | the stage (build, eval, score) | a person, eval/method_table.py | the stage's numbers |
| log/&lt;piece&gt;.log | tmux | a person | the piece's stdout |
| dirty.patch | jobs/launch.py, only when `--allow-dirty` was given | a person | `git diff HEAD` at launch |

`meta.json` fields: `key`, `stage`, `workflow` (the settings file stem),
`setting` (the named setting that created it), `owners` (every
`workflow/setting` that has used this directory, appended, deduplicated),
`created_at`, `upstream` (stage -> key), `versions` (module -> int), `debug`,
`launches` (one entry per start: commit, dirty file count, dirty file list
capped at 50, host, cards, session names, command, time), and `stage_extra` (a
free object; the train stage puts the label order there).

The heartbeat is a small file per piece, not a line in the log. *Failure it
prevents: `ls` tailing six logs over NFS and parsing three log formats, which is
what today's monitor does; and the `@hb` line disappearing when a library prints
over it.* The fields keep today's names (`legacy/ops/heartbeat.py`), so the unit
convention ("task" for the loop, "step" for training) carries over unchanged.

There is no `manifest.json`: what a stage consumed is determined by its key and
the completeness rule in Part 2. *Failure it prevents: a fifth file that has to
be kept in step with the key.*

---

## Part 2. The stage table

Six stages. No stage is added: serving the agent model and serving the probe are
pieces of `sample` and `inject`, not stages, because they produce no output
directory of their own; the prediction run is the last step of `train`, by
gyb's decision; the offline replay line is retired (Part 9).

The table below is the content of `STAGES` in
`experimental_settings/schema.py`. `run.py` walks it; `key()` reads it;
`jobs/launch.py` reads its piece and venv columns.

### 2.1 Sections read, upstream, program, venv

| stage | sections read | upstream | program (module: entry) | venv | cards |
|---|---|---|---|---|---|
| sample | data, models.agent, generation, loop | — | `agent.loop:main` (loop pieces); `models.agent_models.service:main` (service pieces) | environment's venv for the loop; vllm for the service | yes |
| build | data, build, loop.split/tasks/seeds | sample | `data.build_dataset:main` | probe | no |
| train | models.probe, probe, train | build | `train.methods.<probe.method>:main` | probe | yes |
| eval | probe.method, eval | train; and for cgen/cparam the eval run named by `eval.theta_from` | `eval.methods.<probe.method>:main` | probe | no |
| inject | data, models, generation, loop, inject | the train and eval runs named by `inject.score_probe` and `inject.gen_probe` | `agent.loop:main` (loop pieces); `models.agent_models.service:main`; `models.probe_models.service:main` | environment's venv; vllm; probe | yes |
| score | score, loop.split/tasks/seeds | the sample or inject run of the same setting; and the run named by `score.baseline` | `eval.score_run:main` | probe | no |

`sample` and `inject` run the same program: `agent/loop.py` picks
`inject.step` over `generate.step` when the setting has an `inject` section, per
the fourth draft. The two stages differ in their key, their directory and the
`stage` field of their records.

The upstream directory is found through `settings.yaml`'s `_upstream` map, which
`run.py` wrote at creation: a stage never recomputes an upstream key, it reads
the key it was given and calls `run_dir(upstream_stage, key)`. *Failure it
prevents: a YAML edit between launch and run sending a piece to a different
directory than the one registered (lifecycle A2).*

### 2.2 What enters the key

Read with Part 3. "Sections" means the fields of those sections that differ from
their schema defaults and are marked keyed.

| stage | sections hashed | minus | plus | module VERSIONs folded in |
|---|---|---|---|---|
| sample | data, models.agent (keyed table columns), generation, loop | loop.tasks, loop.seeds | — | loop, generate, task_record, environments/&lt;env&gt;, gptoss |
| build | build, data | — | the sample key; loop.split, loop.tasks, loop.seeds | build_dataset, probe_input, example, task_record |
| train | models.probe (keyed table columns), probe, train | — | the build key | trainer, methods/&lt;m&gt;, eval methods/&lt;m&gt;, probe_models/base, probe_models/&lt;backbone&gt;, prediction |
| eval | eval, probe.method | — | the train key; the resolved `eval.theta_from` eval key for cgen and cparam | probe_eval, eval methods/&lt;m&gt; |
| inject | data, models, generation, loop, inject | loop.tasks, loop.seeds | the resolved train and eval keys of both referenced probes | loop, generate, inject, inject_format, probe_input, task_record, environments/&lt;env&gt;, gptoss |
| score | score | — | the upstream run's key; the resolved baseline key; loop.split, loop.tasks, loop.seeds | score_run, task_record |

Two entries need their reason on the page.

- **sample and inject exclude the task and seed lists.** Their directories are
  collections of per-task files, so asking for three more seeds adds files to
  the same directory instead of recollecting the first three. The consumers
  (build, score) put the lists into their own keys and refuse to run until every
  requested (task, seed) has a done record, so what a consumer consumed is still
  fixed by its key. *Failure it prevents: adding a fourth seed throwing away
  three seeds of collected trajectories (GPU days).*
- **train folds `eval/methods/<m>.py`'s VERSION.** The method file calls the
  eval method's match function for its validation metric, as the tree says, so a
  change to the match changes which checkpoint becomes `best/`. *Failure it
  prevents: an eval fix silently leaving a differently-selected checkpoint in
  place (dependencies P2).*

### 2.3 Pieces, claiming, done, continue

| stage | piece rule | claim | done marker | continue |
|---|---|---|---|---|
| sample, inject | `loop.pieces` loop pieces plus `loop.replicas` agent-service pieces (inject adds one probe-service piece); every loop piece gets the whole (task, seed) list | a loop piece claims a (task, seed) by creating `records/<task_id>__s<seed>.jsonl` with `O_EXCL` and writing the `meta` row, whose `owner` is its tmux session; a piece never opens another piece's file | `done.json`, created with `O_EXCL` by the first piece that finds no unclaimed work left **and** every requested (task, seed) done | claimed-and-done files are skipped; a file whose last row is not a clean `final` and whose `owner` session is gone is deleted by `jobs/launch.py` before it starts the replacement piece, and is then re-claimed |
| build | one process | — | `done.json` | reuse when done; otherwise start over, writing into `tmp/` and renaming |
| train | one process on one card | — | `train_done.json` after the last optimizer step; `done.json` after `predictions.parquet` | `done.json` present: reuse. `train_done.json` present: run the prediction step only. `last/` present and its commit equals HEAD: resume from its step. Otherwise fresh. A commit mismatch refuses without `--retry` |
| eval, score | one process | — | `done.json`, rewritten every run | always recompute; the done marker never prevents a rerun |

Two markers in train, not one, because `best/` exists both after a training that
died in the prediction step and after a training that died at step 40. *Failure
it prevents: a finished training restarted from zero, or a half-trained probe
evaluated as final (lifecycle A6).*

CPU evaluation always recomputes, because its key does not change when the
number it computes changes unless someone remembers the VERSION, and it costs
seconds. *Failure it prevents: a metric fix that never runs because a finished
directory was reused (lifecycle A7).*

**Dead piece and refire.** A piece is dead when its tmux session is gone and its
stage has no `done.json`. `jobs/launch.py refire <run dir>` releases the dead
pieces' unfinished claims, probes the cards again and starts one replacement per
dead piece with the same command (which names the run directory, so it cannot
drift). One automatic refire per piece per launch; the second death stops and
waits for a person. There is no incident agent and no resident sampler; a person
or the session reads `run.py ls` (Part 9a).

**Completeness before build.** `data/build_dataset.py` refuses unless every
(task, seed) in `loop.tasks x loop.seeds` has a done record in the sample
directory, and names the missing ones. *Failure it prevents: a build over a
half-finished sample producing a smaller dataset that looks finished
(lifecycle B9).*

---

## Part 3. run_dir and keys

### 3.1 The signature

```
run_dir(stage: str, setting: Setting) -> Path
key(setting: Setting, stage: str) -> str          # 12 hex characters
```

Both live in `experimental_settings/schema.py`, beside the stage table they
read, which is what the tree's line for that file says ("the stage table; and
the loader ... file -> setting, diff, key"). `run_dir` is not in
`jobs/registry.py`: registry would then have to know the stage table and the
section list to compute a directory, which is the settings layer's knowledge;
registry imports `schema.run_dir` for `where` instead, and the import goes
downward.

Guarantees:

1. The same setting and stage give the same path, in any process, on any host.
2. A change to any keyed field the stage reads, to an upstream key, or to a
   folded module VERSION gives a different path.
3. `--debug` gives a separate root, and `debug` enters the key, so no debug
   output can be mistaken for a real one and no tmux session name can collide.
4. Each sweep child has its own path, because each child is a full setting with
   the swept field set.
5. A field set back to its default gives the same path as never setting it.

### 3.2 What is hashed

`key()` builds one canonical JSON object and takes the first 12 characters of
its sha256:

```
{ "stage": <stage>,
  "fields": <the keyed fields of the sections in the stage table's "sections
             hashed" column that differ from their schema default, nested, keys
             sorted, minus the "minus" column, plus the "plus" column>,
  "models": <the keyed columns of each table.yaml row the stage uses>,
  "upstream": {<stage>: <key>, ...},
  "versions": {<module>: <int>, ...},
  "debug": <bool> }
```

Only the difference from the defaults is hashed, so adding a field with a
default that reproduces the old behaviour leaves every existing key alone.
Defaults are therefore frozen: **changing a default, or removing a field,
requires bumping the VERSION of the module that reads it**. Until `tests/`
exists this rule is kept by hand; the fourth draft already names the test that
will enforce it.

`key()` collects the VERSIONs by importing, with importlib **inside the
function**, the modules the stage table names. The import happens at call time,
so there is no import cycle, and only `run.py` and `jobs/launch.py` ever call
`key()` — both on the login machine, under the probe venv. Stage processes never
compute a key; they are handed a run directory. *Failure it prevents: the
settings layer importing every stage at module load, which is a cycle and pulls
torch into the AppWorld venv (dependencies P1, C1).*

Axis values are never renamed, only added and retired. *Failure it prevents:
every old directory becoming unreachable and `run.py <dir>/settings.yaml`
failing on a value the axis no longer allows (dependencies P6).*

### 3.3 The directory

The output root is `constants/path_outputs.yaml`'s `root`. The shape is:

```
<root>/<stage>/<key>/              a real run
<root>/debug/<stage>/<key>/        a debug run
```

The name carries no setting name, because two different settings that agree on
everything a stage reads must share the directory; the human name lives in
`meta.json`'s `owners` and is printed by `run.py where` and `run.py ls`.

`run.py` creates the directory, writes `settings.yaml` (fully resolved, with
`_key`, `_stage`, `_upstream`, `_versions`, `_debug`) and calls
`registry.meta_init` before any piece starts. A piece command is then:

```
<venv python> -m <module> <run dir>
```

and nothing else. A piece therefore cannot be moved by a later YAML edit, and
`refire` re-runs the same string. *Failure it prevents: a refire days later
starting a fresh directory because the YAML changed (lifecycle A2).*

---

## Part 4. The environment base class — `data/environments/__init__.py`

```
class Environment
```

`open_env(name) -> Environment` imports `data/environments/<name>.py` inside the
function, checks every method below is defined, and returns the instance. The
benchmark package is imported inside `open()`, never at module level, so
`data/build_dataset.py`, `eval/methods/cgen.py` and `eval/score_run.py` can use
the call-syntax methods in any venv. *Failure it prevents: build running only in
the AppWorld venv (dependencies P11).*

Eleven methods. The fourth draft's line says eight and lists nine; the list
below adds the two prompt texts, which that line names as the environment's
belongings without making them methods, and folds `split_args` into
`parse_call`, whose return already carries the split arguments.

| method | signature | called by | what it does |
|---|---|---|---|
| tasks | `tasks(split: str) -> list[str]` | loop, build | the task ids of a benchmark split, in the benchmark's order |
| open | `open(task_id: str, seed: int) -> None` | loop | a fresh world for this task and seed, named so two seeds never share the benchmark's output directory |
| step | `step(code: str) -> Observation` | loop | run the agent's code, return the observation cut at the length cap, with its error kind |
| speculate | `speculate(call: str) -> Observation` | inject | make the predicted call executable, snapshot, run it, restore, refreeze the clock, check the clock, return the observation |
| judge | `judge() -> dict` | loop | the benchmark's verdict; must contain `success: bool` |
| close | `close() -> None` | loop | delete the per-task outputs, close the world |
| parse_call | `parse_call(text: str) -> Call \| None` | build, eval(cgen), eval(cparam), score | the first call in a piece of text: tool name, named arguments in call order, and the character span |
| build_call | `build_call(tool: str, args: list[tuple[str, str]]) -> str` | build | the normalized call string, `tool(k=v, k=v)`; `tool()` with no arguments |
| complete_call | `complete_call(text: str) -> str \| None` | inject | finish a call that generation cut off, by balancing parentheses and quotes; null when it cannot be balanced |
| instructions | `instructions(variant: str) -> str` | loop | the task instructions the agent reads, selected by the `data.instructions` axis |
| no_code_message | `no_code_message() -> str` | loop | what the agent is told when it wrote no code block |

`Observation` is a small record with `text: str` and `error_kind: str | None`.
`Call` is a small record with `tool: str`, `args: list[tuple[str, str]]` and
`span: tuple[int, int]`. Both are defined in `data/environments/__init__.py`;
they are plain data, not classes with behaviour.

**What `speculate` must guarantee**, in order, from
`legacy/pipeline/inject/exec_calls.py` and `live_appworld.py:305-322`:

1. snapshot the world under a fixed checkpoint name before anything runs;
2. requote the predicted call into executable form and record which branch each
   argument took (`arg_modes`), never skipping an unparsable call — it is run and
   allowed to fail, because skipping erases the cost of a wrong guess;
3. run it and cut the output at 4000 characters;
4. restore the snapshot and refreeze the clock, in a `finally`;
5. read the clock back and raise when it moved;
6. return the observation with its error kind.

The world after `speculate` is byte-identical to the world before it. The
deferred test named in the fourth draft's `tests/` line is this property, per
environment, in that environment's venv.

**Instruction text.** The variants live in `data/environments/appworld.py` as a
dict from variant name to text; the name is a value on the `data.instructions`
axis in `schema.py`, so a prompt variant is a YAML line that enters the key.
*Failure it prevents: the value gyb varies most often being a code edit guarded
by a hand-bumped VERSION, and two datasets built under different prompts sharing
a key (structure item 8).* VERSION on `appworld.py` then guards only the
benchmark package's interface and the call syntax.

---

## Part 5. The setting schema — `experimental_settings/schema.py`

### 5.1 The shape of a settings file

A workflow file has one `stages:` line naming its stages in order, one `common:`
block, and one block per named setting. A named setting may hold `notes:` (never
keyed) and one `sweep:` block.

```
stages: [sample, build, train, eval]
common:   { ... shared sections ... }
<name>:   { ... sections that differ ... , sweep: {train.lr: [1e-5, 3e-5]} }
```

### 5.2 Sections and fields

`keyed` marks whether the field enters a key at all. Unkeyed fields are
operational: two runs differing only in them produce the same output.

**data** — which benchmark and which prompt.

| field | type | default | keyed | meaning |
|---|---|---|---|---|
| env | axis: appworld | appworld | yes | the benchmark environment |
| instructions | axis: v1 | v1 | yes | which task-instruction text the agent is given |

**models** — which models.

| field | type | default | keyed | meaning |
|---|---|---|---|---|
| agent | table alias, role agent | gptoss120b | yes (its keyed columns) | the agent model |
| probe | table alias, role probe | qwen06 | yes (its keyed columns) | the probe backbone |

**generation** — how the agent model generates.

| field | type | default | keyed | meaning |
|---|---|---|---|---|
| temperature | float | 1.0 | yes | sampling temperature |
| top_p | float | 1.0 | yes | nucleus cut |
| max_step_tokens | int | 8192 | yes | generated-token budget per step |
| reasoning_effort | axis: low, medium, high | high | yes | the harmony reasoning tier |
| start_date | str | 2026-08-06 | yes | the date pinned into the model's system message |

**loop** — the fields both the sample stage and the inject stage read. The
section is named `loop` and not `sample` because the inject stage reads it too;
`sample` stays the name of a stage only.

| field | type | default | keyed | meaning |
|---|---|---|---|---|
| split | benchmark split name | test_normal | yes | which benchmark split to run |
| splits_sampled | list[str] | [] | yes | extra benchmark splits to run in the same directory; empty means `split` alone |
| tasks | int | 0 | key: no for sample/inject, yes for build/score | how many tasks of the split; 0 is all |
| seeds | list[int] | [42] | same as tasks | one trajectory per seed per task |
| max_steps | int | 30 | yes | step cap per task |
| pieces | int | 6 | no | loop pieces |
| replicas | int | 1 | no | agent-service pieces |

**build** — records to examples.

| field | type | default | keyed | meaning |
|---|---|---|---|---|
| max_cuts | int | 64 | yes | cut-point cap per event, applied after enumeration |
| max_examples | int | 0 | yes | cap on the rows written; 0 is all (debug uses it) |
| splits | map | {train: train, val: dev, test: test_normal} | yes | which benchmark split feeds each example split |

The cut rule's other constants (minimum thinking length 40 characters, three
history rounds, 400 characters per history result) are constants in
`data/probe_input.py` under its VERSION, not fields: they have not moved since
the pipeline began, and a field that never changes is a field that has to be
read anyway.

**probe** — what the probe is.

| field | type | default | keyed | meaning |
|---|---|---|---|---|
| method | axis: ctool, cgen, cparam | ctool | yes | which probe method |
| tuning | axis: full, lora | full | yes | train every weight, or adapters |
| lora_r | int | 16 | yes | LoRA rank; read only when tuning is lora |
| lora_alpha | int | 32 | yes | LoRA alpha; read only when tuning is lora |

**train** — how it is trained.

| field | type | default | keyed | meaning |
|---|---|---|---|---|
| lr | float | 1.0e-5 | yes | learning rate |
| epochs | int | 1 | yes | passes over the train split |
| seed | int | 42 | yes | weight init, shuffling and dropout |
| max_len | int | 4096 | yes | probe context in tokens, left-truncated |
| tok_budget | int | 8192 | yes | tokens per forward pass |
| events_per_update | int | 8 | yes | events folded into one optimizer step |
| grad_ckpt | bool | false | yes | gradient checkpointing |
| max_steps | int | 0 | yes | stop after this many steps; 0 is no cap (debug uses it) |
| align_check | bool | true | yes | run the alignment gate before training |
| checkpoint_hours | float | 2.0 | no | how often `last/` is written |

**train.predict** — the prediction run, train's last step. Its own subsection so
that an `eval.*` edit never re-keys training.

| field | type | default | keyed | meaning |
|---|---|---|---|---|
| splits | list[str] | [val, test] | yes | which example splits get prediction rows |
| examples | int | 0 | yes | cap per split; 0 is all (debug uses it) |
| max_new_tokens | int | 96 | yes | generation cap for cgen and cparam |

**eval** — how the numbers are computed.

| field | type | default | keyed | meaning |
|---|---|---|---|---|
| risk | list[float] | [0.10, 0.05] | yes | the trigger-error targets theta is fitted at |
| theta_from | reference or null | null | yes (the resolved key) | the eval(ctool) run whose theta selects rows; required for cgen and cparam, refused for ctool |

The theta grid (0.5 to 0.975 in steps of 0.025) and the bootstrap size (1000,
resampled by task, fixed seed) are constants in `eval/utils/probe_eval.py` under
its VERSION.

**inject** — what injection adds to the loop.

| field | type | default | keyed | meaning |
|---|---|---|---|---|
| score_probe | reference | — | yes (the resolved train and eval keys) | the train_probe setting whose ctool probe decides when to fire |
| gen_probe | reference | — | yes | the train_probe setting whose cgen probe writes the call |
| theta | float | — | yes | the firing threshold; no default, a run without it is refused |
| format | axis: the keys of `agent/inject_format.py` | p1_e1 | yes | how the early result is written into the stream |
| max_per_step | int | 1 | yes | fires allowed per step |
| max_cuts | int | 64 | yes | cuts scored per step before probing stops |
| fire | axis: probe, never, nth_cut | probe | yes | `never` is the no-probe control (the machinery on, never firing); `nth_cut` fires at a fixed cut with no probe, for the identity check |
| nth_cut | int | 0 | yes | which cut `fire: nth_cut` fires at |

**score** — what a run is compared against.

| field | type | default | keyed | meaning |
|---|---|---|---|---|
| baseline | reference or null | null | yes (the resolved key) | the run to pair with, task by task and seed by seed |

### 5.3 Axes and where each value is implemented

| axis | values | the code behind a value |
|---|---|---|
| data.env | appworld | `data/environments/appworld.py` |
| data.instructions | v1 | a key of the instruction dict in `data/environments/appworld.py` |
| generation.reasoning_effort | low, medium, high | a word in the system message in `models/agent_models/gptoss.py` |
| probe.method | ctool, cgen, cparam | `train/methods/<m>.py` and `eval/methods/<m>.py` |
| probe.tuning | full, lora | branches in `train/utils/trainer.py`; targets in `models/probe_models/<backbone>.py` |
| inject.format | note, p1_e1, p1_e2, p2_e1, p2_e2 | rows of `FORMATS` in `agent/inject_format.py` |
| inject.fire | probe, never, nth_cut | branches in `agent/inject.py` |
| models.agent / models.probe | the aliases in `models/table.yaml` | a row, plus `agent_models/<family>.py` or `probe_models/<backbone>.py` |

The axis lists are literals in `schema.py`; `run.py selfcheck` compares them
against `agent/inject_format.py`'s keys, the file names under
`data/environments/`, and the names under `train/methods/` intersected with
`eval/methods/`. *Failure it prevents: the settings layer importing the agent
layer to read an axis, which is the one upward import in the fourth draft
(dependencies P1).*

### 5.4 References

A reference names another setting: `<file stem>/<setting name>`, for example
`train_probe/ctool_on_qwen06`. A bare 12-character key may be written instead,
to pin one old run.

Resolution, in `schema.py`'s loader: load that file, resolve that named setting
in full, compute the stage keys the referring field needs (`eval.theta_from`
needs the eval key; `inject.score_probe` and `inject.gen_probe` need the train
key for the weights and the eval key for the probe report), and put the resolved
keys into the referring stage's key and into `meta.json`. A name that no longer
exists is a load error. A referenced run without a `done.json` is a launch
error, not a load error, so `run.py where` still answers.

The referring setting must agree with the referenced one on `data`,
`models.agent` and `generation`; a difference is a load error, with no flag to
get past it. *Failure it prevents: an inject arm compared against a baseline
collected under another prompt or another temperature, which the glossary's
same-setup rule forbids.*

### 5.5 Sweeps

One `sweep:` block per named setting, a map from a dotted field name to a list
of values. The loader expands it after every other merge into children named
`<setting>/<field>=<value>` (several fields give
`<setting>/<f1>=<v1>,<f2>=<v2>`), each a full setting with its own keys. A child
name is accepted by `run.py` wherever a setting name is. The parent name and the
swept fields are written into the row, so `eval/method_table.py` groups children
by everything else and reports mean and spread.

Refusals: a sweep over a field also given as a command-line override; a sweep
over a field `debug.yaml` sets; a sweep list with one entry.

### 5.6 debug.yaml

Sizes only, never a model and never a tuning, so a debug run exercises the real
code path:

| field | value |
|---|---|
| loop.tasks | 3 |
| loop.seeds | [42] |
| loop.max_steps | 20 |
| loop.pieces | 1 |
| loop.replicas | 1 |
| build.max_examples | 64 |
| train.max_steps | 20 |
| train.predict.examples | 100 |

### 5.7 The loader

`load(workflow, setting, overrides, debug) -> Setting | list[Setting]` merges in
this order:

1. the dataclass defaults;
2. the file's `common:` block;
3. the named setting;
4. `debug.yaml`, when `--debug` was given;
5. the command-line overrides `section.field=value`;
6. sweep expansion, into named children.

A list field is replaced, never appended. Debug is applied before keying and
before overrides, so an override beats debug and a debug run has its own key.

It refuses: a key that is not in the schema; a value outside an axis; a
reference that names no setting; a setting whose `stages:` names an unknown
stage or names one twice; a `stages:` list whose order is not a subsequence of
`sample, build, train, eval, inject, score`; a setting name containing `/`;
`inject.theta` missing; `eval.theta_from` missing for cgen or cparam, or present
for ctool; a reference whose shared sections differ (5.4).

`load_frozen(run_dir) -> Setting` reads the frozen `settings.yaml`, checks
nothing and merges nothing. It is what every stage process calls, so no stage
imports a YAML file of gyb's.

---

## Part 6. The model table and constants

### 6.1 models/table.yaml

One row per alias. Keyed columns are expanded into the setting before keying, so
an edited row is a new key; serving-only columns are not.

| column | keyed | meaning |
|---|---|---|
| role | yes | `agent` or `probe` |
| family | yes | the agent conversation format's file stem (`gptoss`); agent rows only |
| backbone | yes | the probe backbone's file stem (`qwen`); probe rows only |
| weights | yes | the alias to look up in `constants/path_models.yaml` |
| context_len | yes | the served context length (`max_model_len`); null means the engine's default |
| dtype | yes | the weights dtype the server loads |
| quantisation | yes | the quantisation the server applies; null means none |
| served_name | yes | the model name in requests, which the client checks against `/v1/models` |
| host | no | which machine serves it |
| port | no | which port |
| gpu_memory_utilization | no | the fraction of card memory the server takes |
| env | no | environment variables the server process needs |
| extra_flags | no | extra flags for the server command |

**The rule for a new column:** it is keyed when two runs that differ only in it
can produce different text. `context_len`, `dtype` and `quantisation` are keyed
by that test; `gpu_memory_utilization` and `port` are not. *Failure it prevents:
a serving flag changing the outputs while the finished directory is reused
(dependencies P5), and a server move throwing away every finished directory
(structure item 7).*

`table.yaml` holds result-changing values and is therefore covered by the
read-only hook, which answers the fourth draft's open question. Only gyb edits
it.

### 6.2 constants/

Nothing here enters a key. A path may change only for the same bytes at a new
place; a new set of weights is a new alias in `table.yaml`.

`constants/path_datasets.yaml` — one block per environment:

| column | meaning |
|---|---|
| home | the clone's directory (the benchmark's own working directory) |
| splits | split name -> the file or benchmark split name that lists its tasks |
| venv | **the interpreter that runs this environment's loop**, for example `external/appworld/venv/bin/python` |

`constants/path_outputs.yaml`: `root` (the NFS output root) and `debug_root`
(under it).

`constants/path_models.yaml`: one line per weights alias, alias -> absolute
path.

**How the venv that runs an environment's loop is found:** `jobs/launch.py`
reads `constants/path_datasets.yaml[<data.env>].venv`. It is a location, so it
belongs in `constants/`, and this is the one file in the fixed tree whose line
already says "where each environment ... lives". *Failure it prevents: the
launcher having no file to learn the interpreter from (dependencies P7).* The
other two venvs are named by the stage table directly (`probe`, `vllm`) and
resolved as `external/probe-env/bin/python` and
`external/vllm-env/bin/python`.

---

## Part 7. Service protocols

Two services, each one file with both ends, as the tree says. The server main
imports its heavy packages inside the serving functions, so the client half
imports in any venv.

### 7.1 Who renders the conversation

The loop runs in the AppWorld venv, which cannot hold `openai_harmony`
(pydantic 2 would displace the pydantic 1.10.26 AppWorld needs;
`legacy/envs/collect/common.py:14-19`). Today's answer is to put `/render`,
`/encode` and `/decode` on the probe service, which makes the probe service
depend on the agent model's family.

This draft moves it instead:

- `models/agent_models/gptoss.py` renders the conversation to a **string** with
  the standard library, as `legacy/envs/collect/common.py:104-129` already does
  (that hand-assembled string was verified byte-for-byte against the official
  renderer on 2026-08-06). No `openai_harmony` anywhere in the loop's path.
- The **agent service client** turns that string into token ids by calling the
  vLLM server's `/tokenize`, and ids back into text with `/detokenize`.
- The `render-equals-server` check, which needs the official renderer, runs in
  the **server main**, in the vLLM venv, where `openai_harmony` already lives
  because vLLM serves gpt-oss with it.
- `models/probe_models/service.py` keeps `score` and `generate` only.

*Failure it prevents: a second agent family (Qwen) requiring edits to the probe
service and the inject format (dependencies P4, grounding F4).*

### 7.2 The agent service — `models/agent_models/service.py`

Server main (vllm venv), started by `jobs/launch.py` as a service piece:

- `start` — assemble the `vllm serve` command from the table row's serving
  columns and the keyed columns, start it, wait for health.
- `attach` — when a server on the row's host and port answers `/v1/models` with
  the row's `served_name`, use it instead of starting one. Attach is verified by
  the check table below, not by the port answering.
- `--check` — the check table: `/health`; `/v1/models` names `served_name`; and
  **render-equals-server**: `gptoss.render(messages)` tokenized by `/tokenize`
  equals the chat endpoint's `prompt_token_ids` for the same messages, id for id.
  *Failure it prevents: pointing at a server that renders differently, which does
  not error, it just produces wrong numbers (the 2026-08-18 lesson in
  `legacy/pipeline/inject/probe_server.py:572-587`).*
- `stop` — end a server this run started.

Client (standard library, imported by `agent/generate.py` and `agent/loop.py`):

| call | request | response |
|---|---|---|
| stream | POST `/v1/completions` with `prompt` (token ids), `max_tokens`, `temperature`, `top_p`, `seed`, `stream: true`, `return_token_ids: true`, `skip_special_tokens: false`, `stream_options.include_usage` | an iterator of `(text_delta, token_ids_delta)`; after the iterator, `finish`, `stop_reason`, `usage`; `close()` aborts server-side decoding |
| encode | POST `/tokenize` with `prompt` and `add_special_tokens: false` | `ids: list[int]` |
| decode | POST `/detokenize` with `tokens` | `text: str` |
| health | GET `/health`, GET `/v1/models` | ok, and the served name |

The stream hands out text and ids per chunk together, because the text lags the
ids when vLLM withholds bytes for a stop string or an incomplete character;
every consumer records chunk boundaries as `(chars, ids)` pairs
(`legacy/pipeline/inject/live_appworld.py:190-238,340-376`).

### 7.3 The probe service — `models/probe_models/service.py`

Server main (probe venv), started by `jobs/launch.py` as a service piece of the
inject stage. It is given the inject run directory and reads the two referenced
run directories from `settings.yaml`'s `_upstream`: the score probe's
checkpoint, the generation probe's checkpoint, and the score probe's eval run for
`temperature`.

| call | request | response |
|---|---|---|
| score | POST `/score` `{text}` | `{score: float, label: str}` — the largest softmax probability at the fitted temperature, and its class |
| generate | POST `/generate` `{text}` | `{call: str}` — greedy continuation after the separator, cut at the first newline and stripped |
| health | GET `/health` | `{score_train_key, gen_train_key, report_key, temperature, max_len, device, version}` |

`score` returns the number; the comparison with theta happens in
`agent/inject.py`, which has theta from the setting. *Failure it prevents: theta
living both in a setting and in a service, and the two disagreeing.*

`--check` loads both probes, scores and generates once, and prints the health
echo, before any launch.

**How attach is verified.** Before its first request, `agent/inject.py` calls
`/health` and refuses to run unless `score_train_key`, `gen_train_key` and
`report_key` equal the keys resolved in its own `settings.yaml`. The agent
client does the same with `served_name` and the row's keyed columns. *Failure it
prevents: a stale service answering happily with the wrong weights, which is the
exact failure `probe_cfg_problem` was written for.*

---

## Part 8. The registry — `jobs/registry.py`

### 8.1 Rows in jobs/runs.jsonl

Append-only, one line per event, never rewritten. Two events.

**start row**

| field | meaning |
|---|---|
| ev | `start` |
| t | local time, `YYYY-MM-DD HH:MM` |
| key | the stage key |
| stage | the stage name |
| workflow | the settings file stem |
| setting | the named setting (a sweep child carries `parent/field=value`) |
| run_dir | the absolute run directory |
| host | the launching host |
| pieces | one entry per piece: `{kind: loop \| service \| single, host, gpus, session, log}` |
| commit | git HEAD at launch |
| dirty | whether the tree was dirty |
| dirty_files | up to 50 paths, empty when clean |
| debug | whether this is a debug run |
| upstream | stage -> key |
| versions | module -> int |

**finish row**

| field | meaning |
|---|---|
| ev | `finish` |
| t | local time |
| key, stage | as in the start row |
| status | `ok`, `failed` or `killed` |
| wall_s | seconds from the start row |
| counts | what the stage produced: records done, example rows, train steps, events evaluated |
| metrics | the stage's headline numbers, copied from its `report.json` |

A later finish row for the same key wins. `RESULTS.md` is rendered from the
folded stream by `registry.py` and never edited by hand.

### 8.2 Who writes what, and the lock

| writer | writes | where |
|---|---|---|
| jobs/launch.py (login machine) | the start row | jobs/runs.jsonl, under `runs.jsonl.lock` (`fcntl.flock`) |
| run.py (login machine) | the finish row, when a walk finds `done.json` and no finish row; and `RESULTS.md` | same lock |
| every stage piece (any host) | `heartbeat/<piece>.json`, `done.json`, `meta.json` launch entries | its own run directory, no lock |

**Only login-machine processes append to `runs.jsonl`.** A compute node writes
nothing outside its run directory, so no `fcntl` lock is ever taken over NFS
from several hosts. *Failure it prevents: two pieces on two nodes interleaving
half-lines into the ledger because NFS did not honour the lock (lifecycle B11).*

### 8.3 The heartbeat

`registry.beat(run_dir, done, total, unit, **extra)` rewrites
`heartbeat/<session>.json` atomically (write to a temporary name, rename), with
`{done, total, unit, ts, host, session, pid, status}` plus optional `tok_in`,
`tok_out`, `loss`. `unit` is the script's own word, `task` for the loop, `step`
for training, `item` for evaluation. Every piece emits one beat with `done=0`
before its main loop, which is the "model finished loading" signal, and one with
`status="done"` at the end.

### 8.4 Verdicts

Pure functions over four inputs, no IO: `(done_marker: bool, session_alive:
bool, beat_age_s: float | None, since_start_s: float)`. Four values, first hit
wins:

| verdict | rule |
|---|---|
| done | the run directory has `done.json` |
| dead | no tmux session alive |
| stalled | alive, and the newest beat is older than `STALL_S` (1800 s), or there is no beat and the piece started more than `STALL_S` ago |
| running | alive, and a beat within `STALL_S` |

One constant instead of today's adaptive stall line, because the adaptive line
needs a history of beats, and the history existed to feed a resident sampler
that no longer exists. 1800 s is today's warm-up cap, chosen for the same
reason: below it, a checkpoint save or a long validation pass is mistaken for a
stall (`legacy/ops/verdicts.py:21`). A stalled piece is never killed
automatically. *Failure it prevents: killing a live job, which costs more than
refiring a few hours late (the glossary's autopsy entry).*

### 8.5 Subcommands

| command | what it prints |
|---|---|
| `run.py ls [workflow]` | one line per run directory with a start row and no finish row, plus the runs finished today: stage, key, workflow/setting, verdict per piece, progress and rate from the newest beat, the session names, and a mark on directories whose folded VERSIONs are behind the code |
| `run.py where <workflow> <setting> <stage>` | the run directory, one line, nothing else |
| `run.py find <section.field=value ...>` | the rows whose frozen settings match every condition, newest first |
| `run.py kill <workflow> <setting> <stage>` | ends every piece's tmux session, writes the `killed` finish row |
| `run.py free` | the free cards per host, probed live, never cached: a card with any compute process, or a probe that fails, counts as busy |
| `run.py sync` | folds `done.json` files into finish rows and re-renders `RESULTS.md` |
| `run.py selfcheck` | the README's file list against the tree; every "used by" line against the real imports; the axis literals against the files behind them; every `any` file imported under the AppWorld venv |

`ls` reads the run directories, not a sampler's state file; there is no resident
process and no web page (Part 9a).

---

## Part 9. Decisions, proposals and alternatives

### (a) Choices gyb could reasonably veto

1. **The sampler, the incident agent, the escalation line and the refire quota
   are retired.** Alternative: keep a resident sampler. This one: `run.py ls`
   computes the verdict from four inputs with pure functions; the monitoring
   process, its web page and its incident half were 900 lines serving one reader.
   The glossary entries sampler / verdict / escalation line / incident agent /
   autopsy / incident record / sampling history / window are rewritten in the
   same commit; **verdict**, **refire** and **heartbeat** keep their meaning.
2. **Four verdicts, not six.** Alternative: keep `warming up` and `slowed`.
   This one: both were inputs to the automatic escalation that is gone; a person
   reading a rate does not need the program to call it slow.
3. **The heartbeat is a file per piece, not a line in a log.** Alternative:
   keep `@hb` on stdout. This one: `ls` then opens N small files instead of
   tailing N logs and parsing three log formats.
4. **Records are one file per (task, seed), with the file itself as the claim.**
   Alternative: a shared jsonl with a lock. This one: an O_EXCL create is the
   whole claim mechanism, and a killed piece can only damage its own file.
5. **The loop's fields live in a section named `loop`, read by both the sample
   and the inject stage.** Alternative: a `sample:` section and an `inject:`
   section that repeats its six fields. This one: one loop, one set of fields,
   and the same-setup comparison between a baseline and an inject arm is a
   comparison of the same section.
6. **The sample and inject keys exclude the task and seed lists.** Alternative:
   include them, so a directory is exactly its request. This one: adding a
   fourth seed then costs one seed of collection instead of four.
7. **No manifest file.** Alternative: the third draft's `manifest.json` of
   consumed files with hashes. This one: the consumer's key already carries the
   upstream key and the (tasks, seeds) request, and the completeness check makes
   the content deterministic; the manifest was a fifth file to keep in step.
8. **Diff-from-defaults hashing, with defaults frozen.** Alternative: hash the
   full resolved sections. This one: adding a field with a compatible default
   then leaves every existing directory valid; the cost is the rule that
   changing a default needs a VERSION bump, which the deferred test will enforce.
9. **CPU stages (eval, score) always recompute; GPU stages and build reuse.**
   Alternative: reuse everywhere by key. This one: an eval fix that forgets a
   VERSION bump then still runs, and the cost is seconds.
10. **The prediction row carries the full logits vector for ctool.**
    Alternative: fit the temperature on the GPU inside train. This one: eval
    stays CPU-only and a calibration change costs seconds; the cost is about
    150 MB per run and re-derived temperatures (the fit moves from torch LBFGS to
    a 1-D minimiser in numpy, so existing numbers must be re-derived).
11. **cgen and cparam generate at every cut row.** Alternative (the written
    fallback, not built): a `train.predict.trigger_run` field naming the ctool run
    whose theta selects the rows. This one is gyb's decision; the construction
    plan measures the cost in the smoke, and the fallback is one field away.
12. **eval runs in the probe venv and imports numpy.** Alternative: pure Python
    or Polars expressions. This one: the temperature fit and the bootstrap are
    array work; principle 7 forbids torch and the GPU, not numpy.
13. **Harmony rendering is string assembly in `gptoss.py`, with ids from the
    server's `/tokenize`.** Alternative: keep `/render` on the probe service.
    This one: the probe service stops depending on the agent family, and a second
    family is one file and a row.
14. **The probe service returns a score; `agent/inject.py` compares it with
    theta.** Alternative: the service owns theta and returns `fired`. This one:
    theta lives in the setting only.
15. **Instruction text is an axis value (`data.instructions`), not a VERSION
    bump.** Alternative: keep it a code edit guarded by a VERSION. This one: the
    value gyb varies most often becomes a keyed YAML line.
16. **The model table stays at `models/table.yaml` and is covered by the
    read-only hook.** Alternative: move it into `experimental_settings/`. That
    move is a structural change, so it is in (b); the hook answers the fourth
    draft's open question without moving a file.
17. **`run.py sync` is repurposed.** It no longer mirrors metrics into a
    tracker (there is no tracker); it folds `done.json` into finish rows and
    re-renders `RESULTS.md`.
18. **Dropped without a successor**, each because its only consumer is gone:
    the per-event weighting switch (`weight_mode`), the `--overlong skip` and
    `drop-event` modes, the probing-cost table, the read-only axis
    (`readonly_map`, `--readonly-env`), the self-fire head, the mbert line, the
    offline replay line, the five non-AppWorld environments, `RUNMETA.json` (its
    content is `meta.json`'s `launches`), and the chat-endpoint collection path
    (the baseline is the same streamed completion path as every other arm, so
    the same-setup rule holds by construction; the chat endpoint survives only
    inside the render-equals-server check).
19. **Kept although it costs a mechanism**: the dirty-tree gate in
    `jobs/launch.py` (refuses a dirty tree; `--allow-dirty` records
    `dirty.patch`), exempting `jobs/runs.jsonl`, `jobs/RESULTS.md` and
    `*.lock`; the alignment gate before training; the clock-guard assertion in
    `speculate`; the resume accounting (`match_tok`, `identical`). Each has an
    incident behind it in the old code.

### (b) Reviewer fixes that need a structural change — not applied

| fix | the file it would add or split | what it would buy |
|---|---|---|
| Split `schema.py` into schema / loader / key (synthesis 1) | `experimental_settings/loader.py`, `key.py` | the file everyone imports stops being the file everyone edits; here the cycle is instead broken by importing VERSIONs inside `key()` |
| Split `registry.py` into writer and reader (synthesis 2) | `jobs/ledger.py`, `jobs/status.py` | the file every stage imports would stop changing whenever `ls` gains a column |
| Keep shared packing and the row-by-row reference (synthesis 3) | `train/packing.py`, `train/reference.py` | cgen and cparam would stop being two near-copies of 600 lines, and the alignment gate would have something to compare against; as it stands the gate compares the packed loss against a plain loop written inside each method file |
| Split the trainer (synthesis 4) | `train/tuning.py`, `train/predict.py` | three duties with three edit triggers would stop sharing a file; the continue rule is made decidable here by two markers instead |
| Give the probe report a file in `data/` (synthesis 5) | `data/probe_report.py` | the rule "every format between two stages is defined in `data/`" would hold without exception; here the report is defined in `eval/utils/probe_eval.py`, per gyb's instruction |
| Split each service into server and client (synthesis 6) | `agent_models/server.py`, `client.py`, `probe_models/server.py`, `client.py` | the venv boundary would be a file boundary that `selfcheck` could import-test; here `selfcheck` imports the whole file under the AppWorld venv instead |
| Move the model table into `experimental_settings/` (synthesis 7) | `experimental_settings/models.yaml`, `constants/models.yaml` | result-changing values would all sit in one directory; here the keyed/serving-only column marks do the same work in one file |
| One per-method module in the bottom layer (synthesis 12, dependencies P2) | `data/methods/<m>.py` | a fourth probe method would touch three files instead of five; here it touches `data/build_dataset.py`, `train/methods/x.py`, `eval/methods/x.py`, one axis line and a README block |
| Gates in their own file (structure 11) | `data/check_dataset.py` | the gates have a different edit trigger (a new silent failure) than example-making |
| Environments as a top-level layer (synthesis 11) | `environments/` | `data/` would hold only on-disk formats; here the folder stays under `data/` and the call-syntax methods are what make it importable anywhere |
| Flatten `train/` and `eval/`, name eval files by the metric (synthesis 12) | `train/*.py` flat, `eval/fire_threshold.py`, `eval/exact_match.py` | `train/methods/ctool.py` and `eval/methods/ctool.py` would stop colliding in a file switcher |
| A seventh stage for offline replay (structure 13) | `agent/replay.py` or a stage file | the replay line would have a home; it is retired here |
| A resident watcher (structure 6) | `jobs/watch.py` | verdicts without a person; retired here |
