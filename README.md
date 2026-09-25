# new1

## 1. What this repo is and how to run it

Seven principles hold the tree together (`notes/plans/2026-09-14-structure-from-zero.md`):
one experiment is one setting, in one `experimental_settings/*.yaml` file; every run is
reproducible, so a finished output directory is reused, a partial one is continued, and an
edited setting gets a new directory; the layers are short and standard (`data`, `models`,
`agent`, `train`, `eval`, `jobs`), with settings controlling their arguments; `--debug` runs
any setting tiny (a few tasks, a few examples, a few steps); there are no near-duplicate files
and no framework, only per-layer `utils/` once code is shared on its third repetition; every
file does one thing its name says, and this file lists every one of them with that one line;
`eval/` only reads what is already on disk, no GPU and no torch, because the GPU half of an
evaluation is the last step of `train`.

`run.py` is the one command. It walks a named setting's stages:

```
external/probe-env/bin/python run.py <workflow> <setting> [<setting> ...] [--debug] [--allow-dirty] [--cards <host>:<id>,<id>,... ...] [section.field=value ...]
```

`<workflow>` is the stem of a file under `experimental_settings/` (`baseline`, `train_probe`,
`inject`); `<setting>` is a name inside that file, or a sweep child's own name
(`<name>/<field>=<value>,...`); several settings may be walked in one call. `--debug` lays
`experimental_settings/debug.yaml` over the named setting before it is keyed, so the run gets
its own directory and can never be mistaken for a real one. `--allow-dirty` lets a stage launch
over an uncommitted tree, writing `dirty.patch` into the run directory; without it a dirty tree
is refused. `--cards tokyo108:3,4` (given once per host) names the only cards a launch may
claim: the pieces take their cards from that pool in the order given, the agent service goes
to the pool's host instead of its `models/table.yaml` row's, and a named card that is not free
refuses the launch. The pool is where a launch runs and never part of the setting, so it moves
no key and no run directory; `refire` and `retry` take the same flag. Without it a launch takes
the first free cards. Either way a piece takes only cards at least as large as the cards it was
declared for: an agent service that starts its own server needs cards no smaller than the
smallest card of its table row's serving host, a train piece and a probe service need any card,
and card sizes are `constants/cards.yaml`'s; a pool whose cards are too small for a piece
refuses the launch, naming them. `section.field=value` overrides one field from the command line, its right-hand
side parsed as YAML, so a reference can be pinned without editing the setting file.

Ten further words are reserved (`run.py --help` lists them, one per line): `ls`, `where`,
`find`, `kill`, `refire`, `retry`, `table`, `free`, `sync`, `selfcheck`. Any other first word
is a workflow file's stem; a workflow file may not use one of the ten as its own stem.

Every output lives under `constants/path_outputs.yaml`'s `root`, keyed by stage and a 12-hex
hash of the setting (never by name, since several settings can share one directory); `run.py
where <workflow> <setting> <stage>` prints the path, whether or not it exists yet, and never
touches disk to compute it. A `--debug` run lives under that root's `debug_subdir` instead, so
it never collides with, or is mistaken for, a real run; `ls`, `where`, `table`, `kill`,
`refire` and `retry` take `--debug` to address the runs under it, and a `--debug` walk prints
its monitoring line with the flag.

`retry` means "start fresh": it refuses while any piece of the run is alive (end it with `kill`
first), and only then clears the continue markers and launches the stage normally.

`run.py` runs on any machine of the cluster. `constants/path_outputs.yaml`'s `login_host` is
where the loop pieces and every other piece that needs no card are placed; a piece on a host
other than the one `run.py` runs on is started over `ssh`.

## 2. The tree, one entry per file

This section is the current statement of the tree: one entry per file, in contracts 0.1's
five-line annotation format, and the text `run.py selfcheck` checks — check 1 requires an
entry for every `.py` file on disk and a path that exists for every entry, and check 2 holds
the `imports:` and `used by:` lines equal to the real import graph. Its origin is
`notes/plans/2026-09-17-contracts.md` 0.2, reconciled against the lines each ticket landed
and against `.scratch/from-zero/contract-errata.md`. Contracts 0.2, 0.3 and 0.4 have been
stale since the two rulings of 2026-09-18 that folded `eval/methods/<m>.py` into
`eval/utils/probe_eval.py` and renamed the four `agent/` files (the errata entries
`0.2 / 2.1 / 2.6 (eval/methods/)` and `0.2 (the four agent/ file names)`): they still spell
34 files, `eval/methods/` and `agent/inject_format.py`. This file wins over them until the
owner rewrites them.

### The root

CLAUDE.md — the rules an agent reads on its own; the only other file at the root that is not code.

run.py — the one command: walk a named setting's stages (sample through score), or run one of the ten reserved subcommands (ls, where, find, kill, refire, retry, table, free, sync, selfcheck); a walk loads every named setting before it walks the first stage, so a name the file does not hold is refused before anything is frozen or launched; each stage prints one line naming its outcome (reused, ok with its report, failed with its exit code, or launched with the monitoring command), and a walk or a retry exits 1 when a CPU stage failed; where, kill, refire and retry load the named setting first and refuse a stage its own workflow does not walk.
  imports: experimental_settings/schema.py, jobs/launch.py, jobs/registry.py, data/trajectory_record.py (done_pairs, is_done, owner, release), data/environments/__init__.py (open_env, requested_pairs), eval/utils/probe_eval.py (read_report, to freeze a referenced temperature), eval/method_table.py (the table subcommand)
  used by: none (program)
  reads:   experimental_settings/*.yaml (through schema), every run directory's settings.yaml / meta.json / done.json / consumed.json and the upstream files it names, the VERSION and VERSION_HISTORY tables of the modules a stage lists (through schema.versions_of, schema.effective_version and schema.version_history, for ls's behind flag), the sample or inject run's task records (through data/trajectory_record.py), the environment's split task-id files (through data/environments.requested_pairs), the probe report of a referenced classifier eval run (through eval/utils/probe_eval.read_report), jobs/runs.jsonl, constants/cards.yaml (through jobs/registry.canonical_host, to name the machine a CPU stage runs on), constants/path_datasets.yaml (the venvs map)
  writes:  settings.yaml and settings_diff.yaml into a run directory (through schema.freeze), done.json for the piece stages, meta.json (its owners list, and the stage_extra it folds out of a finished stage's done.json), the start rows of the three CPU stages it starts in place, finish rows and RESULTS.md (through jobs/registry.py); on `retry`, once no piece of the run is alive, deletes the run's continue markers (done.json, consumed.json; for train also train_log.jsonl, train_done.json, align_check.json, last/, last.tmp/, last.prev/)
  venv:    probe (the interpreter this repo's commands are typed with)

### constants/ — where things are on this cluster

constants/path_datasets.yaml — per environment: the clone's home, the interpreter that runs its loop, its data root, and split name -> task-id file; plus the top-level venvs: map, which is where every interpreter path in this repo is written down.
  read by: data/environments/__init__.py (the splits block, to resolve a split name), data/environments/appworld.py (home, data root, split files), experimental_settings/schema.py (the splits block, to validate a split value at load), jobs/launch.py (the venv column and the venvs map), run.py (the venvs map)

constants/cards.yaml — the cluster inventory, the one file for card facts: every host's name and alias, and per card index its model and memory in GiB; the source for the code (how many cards a host has, how large each card is) and for people picking cards.
  read by: jobs/registry.py (the one loader, hosts(): the hosts for tmux and card probes, the card count, card_memory_gib() and canonical_host() for jobs/launch.py and run.py)

constants/path_outputs.yaml — the outputs root on NFS, the debug subdirectory under it, and the login_host.
  read by: experimental_settings/schema.py (run_dir), jobs/registry.py (ls walks the root), jobs/launch.py (the login_host)

constants/path_models.yaml — weights alias -> the directory the weights live in.
  read by: models/__init__.py, models/agent_models/service.py (the weights path of the row it serves)

### experimental_settings/ — everything in here changes a result; the owner's files, never edited by an agent

experimental_settings/schema.py — the setting schema: the dataclasses, the stage table, and the loader that reads a YAML file against them (file -> setting, diff, key).
  imports: none (repo); [PyYAML, ast, dataclasses, hashlib, itertools, json, pathlib, typing]
  used by: run.py, jobs/launch.py, agent/run_tasks.py, data/build_training_dataset.py, train/utils/trainer.py, eval/utils/probe_eval.py, eval/score_run.py, eval/method_table.py, models/agent_models/service.py, models/probe_models/service.py
  reads:   experimental_settings/*.yaml, models/table.yaml, constants/path_outputs.yaml, constants/path_datasets.yaml (the splits block of the chosen environment), a run directory's settings.yaml, the VERSION / VERSION_HISTORY / PROBE_KIND lines and module-level literals of contracts 3.3's literal rule, all as source text, never by importing
  writes:  settings.yaml and settings_diff.yaml in a run directory
  venv:    any

experimental_settings/debug.yaml — only sizes, never a model and never a tuning; --debug lays it over any setting.
  read by: experimental_settings/schema.py only

experimental_settings/baseline.yaml — workflow sample, score; named settings inside.
  read by: experimental_settings/schema.py only

experimental_settings/train_probe.yaml — workflow sample, build, train, eval; named settings inside.
  read by: experimental_settings/schema.py only

experimental_settings/inject.yaml — workflow inject, score; named settings inside.
  read by: experimental_settings/schema.py only

### data/ — the benchmark environments, and every format that lives on disk between two stages

data/__init__.py — the conventions the three on-disk formats share: read_frame and write_frame, the id chain, the VERSION / DEFAULTS / REQUIRED rule.
  imports: none (repo); [polars]
  used by: data/trajectory_record.py, data/training_data.py, data/probe_output.py, data/build_training_dataset.py (the id functions)
  reads:   -
  writes:  -
  venv:    any

data/environments/__init__.py — the environment contract every benchmark implements, the loader that finds and instantiates one by name, and the one rule for which (task, seed) pairs a run requests.
  imports: none (repo); [importlib, PyYAML]
  used by: data/environments/appworld.py (subclass), agent/run_tasks.py (open_env, StepObservation, requested_pairs), agent/step_with_probe.py, data/build_training_dataset.py, train/methods/cgen.py, train/methods/cparam.py, eval/utils/probe_eval.py, eval/score_run.py, jobs/launch.py, run.py
  reads:   constants/path_datasets.yaml
  writes:  -
  venv:    any

data/environments/appworld.py — the AppWorld benchmark: hands out its tasks, steps a model's call through a live world, speculates one call early, and judges task completion.
  imports: data/environments/__init__.py; [the appworld package, inside open() alone]
  used by: data/environments/__init__.py (by name)
  reads:   constants/path_datasets.yaml, the split task-id files
  writes:  the AppWorld per-task output directory, deleted by close()
  venv:    any at import and for the call-syntax methods; appworld to hold a world

data/trajectory_record.py — the record one task run leaves: six row kinds in one flush-per-row jsonl file, with the claim, release, read and message-rebuilding functions its callers share.
  imports: data/__init__.py
  used by: agent/run_tasks.py (meta, gen, env, final; done_pairs), agent/step_with_probe.py (spec, resume), data/build_training_dataset.py, eval/score_run.py, jobs/launch.py (done_pairs, is_done, owner, release), run.py (done_pairs, is_done, owner, release: the completeness check, the progress count and the claim release)
  reads:   task record (jsonl)
  writes:  task record (jsonl)
  venv:    any

data/training_data.py — the row build writes per cut: the record and cut it came from, the text the probe sees, and all three probe methods' targets.
  imports: data/__init__.py; [polars]
  used by: data/build_training_dataset.py (write), train/utils/trainer.py (read)
  reads:   example (parquet)
  writes:  example (parquet)
  venv:    any

data/probe_output.py — the row train writes per example after training: the example id, its target, the true tool, the score and class logits (ctool) or the generated text (cgen, cparam).
  imports: data/__init__.py; [polars]
  used by: train/utils/trainer.py (write), eval/utils/probe_eval.py (read)
  reads:   prediction (parquet)
  writes:  prediction (parquet)
  venv:    any

data/probe_input.py — the probe's cut enumeration and prompt assembly, shared by the offline builder and the live injector so neither builds its own probe text.
  imports: none (repo); [re]
  used by: data/build_training_dataset.py, agent/step_with_probe.py
  reads:   -
  writes:  -
  venv:    any

data/build_training_dataset.py — the program: records -> example rows for the three probe methods; the train/val/test split, by either rule of build.split_source; the report; the gates.
  imports: experimental_settings/schema.py, data/__init__.py (the id functions), data/trajectory_record.py, data/training_data.py, data/probe_input.py, data/environments/__init__.py, jobs/registry.py; [polars, PyYAML]
  used by: none (program)
  reads:   the sample run's task records, constants/path_datasets.yaml (the splits block of cfg.data.env, for the split files' paths), the environment's split task-id files
  writes:  examples.parquet, consumed.json, report.md, heartbeat, done.json
  venv:    any

### models/ — the models: the table, the agent-model side, the probe-model side

models/__init__.py — the entrance to models/table.yaml: agent(alias) and probe(alias) resolve a row into its family module (agent only), weights alias, weights path and serving block.
  imports: none (repo); [importlib, PyYAML]
  used by: agent/step_without_probe.py, agent/step_with_probe.py, models/agent_models/service.py, models/probe_models/base.py, models/probe_models/service.py, train/utils/trainer.py
  reads:   models/table.yaml, constants/path_models.yaml
  writes:  -
  venv:    any

models/table.yaml — one row per alias, in two blocks: result (expanded into the setting before keying) and serving (never keyed).
  read by: models/__init__.py, experimental_settings/schema.py (the result block), models/agent_models/service.py (the serving block), jobs/launch.py (the serving block: host and port)

models/agent_models/__init__.py — empty package marker, so the client half of service.py imports without the family's libraries.
  imports: none
  used by: models/agent_models/service.py, models/agent_models/gptoss.py (as their package)
  reads:   -
  writes:  -
  venv:    any

models/agent_models/gptoss.py — gpt-oss's harmony conversation format: render messages to token ids, parse a streamed reply, end of turn, and the control-token wrapping of a prefetch message.
  imports: none (repo); [openai_harmony, inside render_ids()]
  used by: models/__init__.py (by name); every other file reaches this module as the object models/__init__.py's agent(alias) returns
  reads:   -
  writes:  -
  venv:    any at import and for parse/end_of_turn/wrap_prefetch; probe or vllm for render_ids()

models/agent_models/service.py — both ends of the served agent model: start or attach to the vLLM server for a table row and check it, plus the loop's raw token-stream client.
  imports: models/__init__.py (the family through agent(alias), inside the server main), experimental_settings/schema.py (load_frozen)
  used by: agent/step_without_probe.py (client), agent/run_tasks.py (health); jobs/launch.py starts it as a piece, which is a tmux command and not an import
  reads:   models/table.yaml (the serving block only), constants/path_models.yaml, the run directory's settings.yaml (models.agent_row plus generation.date and generation.effort)
  writes:  service_agent_<replica>.json and its piece log in the run directory
  venv:    any at import; vllm to serve

models/probe_models/__init__.py — empty package marker, so the client half of service.py imports without torch.
  imports: none
  used by: models/probe_models/base.py, models/probe_models/service.py, models/probe_models/qwen.py (as their package)
  reads:   -
  writes:  -
  venv:    any

models/probe_models/base.py — the probe class every backbone shares: load, save, score a prefix, generate a call; owns the classification head and the checkpoint layout.
  imports: models/__init__.py; models/probe_models/<backbone>.py (by name, inside load()); [torch, transformers, peft]
  used by: train/utils/trainer.py, models/probe_models/service.py (inside serve())
  reads:   the checkpoint layout, including the class order in best/meta.json, and the backbone alias's own weights when the checkpoint holds the LoRA adapter alone
  writes:  the checkpoint layout
  venv:    probe

models/probe_models/qwen.py — Qwen's tokenizer quirks, pad token, head attach point, LoRA target modules and restore/serving dtype.
  imports: none (repo); [transformers]
  used by: models/probe_models/base.py (by name)
  reads:   -
  writes:  -
  venv:    probe

models/probe_models/service.py — both ends of the probe service: the HTTP server that scores, generates, encodes, decodes and renders, plus the check client and the loop's client.
  imports: models/__init__.py; experimental_settings/schema.py (load_frozen, for the check client's expected values); models/probe_models/base.py (inside serve()); [http.server, transformers and torch inside serve()]
  used by: agent/run_tasks.py (client: render), agent/step_with_probe.py (client: score, generate, encode, decode); jobs/launch.py starts it as a piece, which is a tmux command and not an import
  reads:   the checkpoint directories named on its command line, including each one's best/meta.json; the run directory's settings.yaml, the check client only
  writes:  service_probe_0.json and its piece log in the run directory
  venv:    any at import; probe to serve

### agent/ — the loop that runs the agent model on tasks

agent/run_tasks.py — run each task and seed of a piece's rotation to completion, claiming tasks across pieces and writing the record.
  imports: experimental_settings/schema.py (load_frozen), data/environments/__init__.py, data/trajectory_record.py, models/agent_models/service.py (client), models/probe_models/service.py (client, for render), agent/step_without_probe.py, agent/step_with_probe.py, jobs/registry.py, jobs/launch.py (teardown_services)
  used by: none (program)
  reads:   its run directory's settings.yaml, the environment's split task-id files (through data/environments.requested_pairs), the service_agent_<replica>.json / service_probe_0.json endpoint files in its own run directory; after its walk, the last line of every requested record (done_pairs) and, through jobs/launch.teardown_services, its run directory's meta.json and the open runs' service_<kind>_<replica>.json
  writes:  task records (jsonl), heartbeat; ends its run's service pieces (through jobs/launch.teardown_services) once every requested record is finished
  venv:    the environment's (appworld today)

agent/step_without_probe.py — the plain generation step: stream tokens from the agent model to end of turn, exposing the stream so step_with_probe.py can iterate it instead.
  imports: models/agent_models/service.py (client), models/__init__.py (the family module)
  used by: agent/run_tasks.py, agent/step_with_probe.py
  reads:   -
  writes:  -
  venv:    the environment's

agent/step_with_probe.py — the generation step with the probe attached: score the model's own reasoning as it streams, fire early, splice the result in and resume.
  imports: agent/step_without_probe.py, agent/injected_text_formats.py, data/probe_input.py, data/trajectory_record.py, data/environments/__init__.py (type only), models/probe_models/service.py (client), models/__init__.py (the family module)
  used by: agent/run_tasks.py
  reads:   -
  writes:  spec and resume rows, through data/trajectory_record.py
  venv:    the environment's

agent/injected_text_formats.py — the table of the five ways an early speculation result is written into the token stream.
  imports: none
  used by: agent/step_with_probe.py; its keys are cross-checked against schema.py's axis by run.py selfcheck
  reads:   -
  writes:  -
  venv:    any

### train/ — train a probe

train/utils/trainer.py — the training loop every method shares: settings -> arguments, seed, backbone, tuning (full or LoRA), checkpoints, metrics, heartbeat, resume, the alignment gate (it passes only when it compared at least one row the method kept and the two losses agree), and the probe run over the prediction splits.
  imports: experimental_settings/schema.py, models/__init__.py, models/probe_models/base.py, data/training_data.py, data/probe_output.py, jobs/registry.py; [torch]
  used by: train/methods/{ctool,cgen,cparam}.py
  reads:   example (parquet), the checkpoint layout
  writes:  best/, last/, last.tmp/ and last.prev/ (the two names the resume checkpoint's swap uses, left on disk by a kill inside it), train_log.jsonl, align_check.json, train_done.json, predictions.parquet, consumed.json, heartbeat, done.json
  venv:    probe

train/methods/ctool.py — the classification probe: its batches, its head use, its loss, its validation accuracy.
  imports: train/utils/trainer.py, eval/utils/probe_eval.py (match_ctool); [torch]
  used by: none (program)
  reads:   -
  writes:  - (everything goes through trainer.py)
  venv:    probe

train/methods/cgen.py — the call-generating probe: its packing, its instance strings and target, its loss positions, its exact-match validation.
  imports: train/utils/trainer.py, eval/utils/probe_eval.py (match_cgen), data/environments/__init__.py (open_env, for the environment its validation metric's match takes); [torch]
  used by: none (program)
  reads:   -
  writes:  - (everything goes through trainer.py)
  venv:    probe

train/methods/cparam.py — the argument-generating probe: its own packing and strings, the arguments as the target.
  imports: train/utils/trainer.py, eval/utils/probe_eval.py (match_cparam), data/environments/__init__.py (open_env, for the environment its validation metric's match takes); [torch]
  used by: none (program)
  reads:   -
  writes:  - (everything goes through trainer.py)
  venv:    probe

### eval/ — reads what is on disk and computes numbers; no GPU, no torch

eval/utils/probe_eval.py — the eval program of every probe method: the PROBE_KIND and MATCH_VERSION tables, the three match functions, the classifier and the generator report, and the driver that reads a train run's prediction rows and writes the probe report.
  imports: experimental_settings/schema.py, data/probe_output.py, data/environments/__init__.py (open_env, for the environment the generator report normalises both sides through), jobs/registry.py; [polars, numpy]
  used by: train/methods/{ctool,cgen,cparam}.py (match_<method>, for their validation metric), run.py (read_report, to freeze a temperature), eval/method_table.py
  reads:   prediction (parquet), its own and the referenced eval run's train meta.json (stage_extra.labels, upstream["build"]), its own train run's done.json (counts.dropped_overlong), probe report (json + parquet)
  writes:  probe report (probe_report.json + fires.parquet), report.md, consumed.json, heartbeat, done.json
  venv:    any

eval/score_run.py — score a sample or inject run from its task records: success rates and probe agreement rates, paired against a baseline.
  imports: experimental_settings/schema.py, data/trajectory_record.py, data/environments/__init__.py (open_env for split_args and build_call, and requested_pairs), jobs/registry.py; [polars]
  used by: none (program)
  reads:   the task records of this run and of its baseline; the environment's split task-id files (through data/environments.requested_pairs); the scored run's and the baseline run's settings.yaml (the same-setup gate)
  writes:  run_report.json, report.md, heartbeat, done.json
  venv:    any

eval/method_table.py — the backbone x method table from the registry; one group per (setting, debug flag) pair, reports mean and spread.
  offers:  table(workflow: str | None = None, out: Path | None = None, *, debug: bool = False) -> str
  imports: experimental_settings/schema.py, jobs/registry.py, eval/utils/probe_eval.py (read_report)
  used by: run.py (the table subcommand); this file is not a stage and has no __main__
  reads:   jobs/runs.jsonl, the probe reports the rows point at, an eval run's own meta.json and its train run's meta.json (for backbone)
  writes:  a markdown table on stdout or into a named file
  venv:    any

### jobs/ — a job is one stage run on cards: the code that starts it and records it, and the record itself

jobs/registry.py — the registry: runs.jsonl rows under a lock, meta.json, the heartbeat, the verdicts, ls/where/find/kill/free/sync, RESULTS.md.
  imports: none (repo); [PyYAML]
  used by: run.py, jobs/launch.py, agent/run_tasks.py, data/build_training_dataset.py, train/utils/trainer.py, eval/utils/probe_eval.py, eval/score_run.py, eval/method_table.py
  reads:   constants/path_outputs.yaml (the root), constants/cards.yaml (the hosts, their card counts and card memory; this file holds its one loader), jobs/runs.jsonl, run directories' meta.json, done.json, heartbeat and service_<kind>_<replica>.json, ssh, tmux, nvidia-smi
  writes:  jobs/runs.jsonl, jobs/RESULTS.md, meta.json, meta.json.corrupt.<timestamp>, heartbeat/<piece>-<launch>.jsonl, done.json
  venv:    any

jobs/launch.py — launch the tmux pieces of a sample, inject or train run and refire its loop and train pieces (a dead service piece is handled by re-running the walk): the dirty-tree gate, the launch gate, card placement, port assignment, the piece and service commands, and teardown.
  imports: experimental_settings/schema.py, jobs/registry.py, data/trajectory_record.py (release), data/environments/__init__.py (tasks and requested_pairs); [PyYAML]
  used by: run.py, agent/run_tasks.py (teardown_services)
  reads:   constants/path_datasets.yaml (the venv per environment and the venvs map), constants/path_outputs.yaml (the login_host), constants/cards.yaml (through jobs/registry.py: host names and each card's memory, which placement holds against the card size a piece was declared for), models/table.yaml (the serving block; an agent service's declared card size is the smallest card of its row's serving host), the run directory's settings.yaml and meta.json, its pieces' log/<piece>.txt and, through jobs/registry.current_beats, the heartbeat/<piece>-<launch>.jsonl file of the incarnation each piece entry's beat_launch names (the alive check and the launch gate's beats), its own and other live runs' service_<kind>_<replica>.json, the registry rows (through jobs/registry.py), nvidia-smi (through jobs/registry.py), tmux, git
  writes:  the start row in jobs/runs.jsonl (a launch's and a refire's), meta.json launch entries, meta.json's split_files, dirty.patch, the piece commands; deletes this launch's own service_<kind>_<replica>.json before its service pieces start
  venv:    probe

jobs/runs.jsonl — one registry row per stage run, appended at start and at finish by registry.py; never edited by hand; in git.

jobs/RESULTS.md — rendered from runs.jsonl by registry.py; never edited by hand.

### tests/

tests/ — empty by the owner's decision, except for the two of the four planned checks this build needs: `tests/test_registry_concurrent_append.py` (ticket 03: eight forked processes append 20 start rows each into a throw-away copy of the tree; asserts 160 lines land and every line parses as JSON; and 8.5's piece verdicts over heartbeat files in a temporary run directory: a train piece is `done` only on its finish row, a service gone once its run's work pieces are done is `done`, a service gone while a loop piece works is `dead`, a relaunched piece reads only the heartbeat file of the incarnation its entry's `beat_launch` names, and an attached agent service is judged by its port and its run's work, not by its ended session) and `tests/test_packed_loss.py` (ticket 13: the packed loss equals the plain loss on a tiny CPU model, once per probe method; it puts the repo root on `sys.path` itself). Run each in its own process, from the repo root: `external/probe-env/bin/python tests/test_registry_concurrent_append.py` and `external/probe-env/bin/python tests/test_packed_loss.py`.

## 3. The extension recipes

What you edit, in order, and what it costs, for each of the seven ways this tree grows and the
two changes that are not extensions but deserve the same treatment (contracts 0.4).

Every recipe that adds a file (1, 2, 6 and 7) also writes that file's own five annotation lines
into section 2 above, and adds the new file's name to the `used by:` line of every repo file it
imports. A new file that lands in a package directory whose `__init__.py` carries an
`(as their package)` `used by:` line (`models/agent_models/` and `models/probe_models/` today)
joins that list as well, because check 2 holds such a line equal to the `.py` files the
directory holds. `run.py selfcheck` compares those lines against the real import graph, so it is
the check that catches a recipe followed half way. A line written as a brace list,
`train/methods/{ctool,cgen,cparam}.py`, is widened rather than extended with a second fragment;
selfcheck reads both spellings the same, and this one keeps the line short.

1. **A new benchmark environment.** `data/environments/<env>.py` (new, carrying its own
   column-zero `INSTRUCTIONS` and `SPLIT_ROLE` maps, plus `VERSION` and `VERSION_HISTORY` under
   the pinned VERSION rule comment block, because the stage table names this file);
   `experimental_settings/schema.py` (one value on `data.env`, one on
   `data.instructions`, and one value on `sample.split` / `inject.split` for every split name the
   new environment has that no existing one has); `constants/path_datasets.yaml` (home, venv,
   data root, split files, and a `venvs:` entry when the benchmark brings its own interpreter,
   which must carry PyYAML, Polars and NumPy). Cost: nothing else, because the loop calls nine
   methods and nothing else, and `data/build_training_dataset.py` parses calls through the
   environment object.
2. **A fourth probe method.** `train/methods/<m>.py` (new, carrying four column-zero bindings:
   `VERSION` and `VERSION_HISTORY` under the pinned VERSION rule comment block, `PROBE_KIND`
   matching the entry you add to `eval/utils/probe_eval.py`, and `CHECKPOINT_META`);
   `experimental_settings/schema.py`
   (one value on `probe.method`); `eval/utils/probe_eval.py` (a `match_<m>` function plus one
   entry each in `PROBE_KIND` and `MATCH_VERSION`, both column-zero tables). Cost: the example
   row and the prediction row are method-independent, so `data/build_training_dataset.py`,
   `data/training_data.py` and `data/probe_output.py` are untouched, and the head lives in
   `models/probe_models/base.py` already. A method that is neither classifier nor generator needs
   a third `PROBE_KIND`, which costs a column on `data/probe_output.py`, a third report shape and
   a third head as well.
3. **A new training hyperparameter.** `experimental_settings/schema.py` (field, default,
   one-line comment); the one module that reads it (`train/utils/trainer.py` or one method
   file). Cost: free when the default reproduces the old behaviour, because the key is over the
   diff from the defaults.
4. **A new field on the task record.** `data/trajectory_record.py` (the column and its
   `DEFAULTS` entry); the one writer (`agent/run_tasks.py` or `agent/step_with_probe.py`). A
   field nobody downstream reads costs nothing more: no `VERSION` bump, no rerun. A field a
   downstream stage reads costs a `REQUIRED` entry and a `VERSION` bump as well, which re-keys
   `sample` and `inject` and costs the recollection.
5. **A sixth injection format that reuses a placement.** `agent/injected_text_formats.py` (one
   `FORMATS` entry); `experimental_settings/schema.py` (one value on `inject.format`). A new
   placement costs one more file, `models/agent_models/<family>.py` (one function per family,
   the control-token wrapping).
6. **A new probe backbone.** `models/probe_models/<backbone>.py` (new, carrying a column-zero
   `LORA_TARGETS`, plus `VERSION` and `VERSION_HISTORY` under the pinned VERSION rule comment
   block, because the stage table names this file); `models/table.yaml`
   (one row); `constants/path_models.yaml` (one row). Cost: `base.py` holds everything the
   backbones share.
7. **A new agent-model family.** `models/agent_models/<family>.py` (new, carrying column-zero
   `STOP`, `EFFORTS`, `DEFAULT_EFFORT` and `DEFAULT_DATE`, plus `VERSION` and `VERSION_HISTORY`
   under the pinned VERSION rule comment block, because the stage table names this file);
   `models/table.yaml`
   (one row); `constants/path_models.yaml` (one row); `experimental_settings/schema.py` (one
   value on `generation.effort` for each reasoning tier the new family has that no existing
   family has); plus the family's rendering library installed in the probe venv and the vllm
   venv, which `selfcheck` proves by importing the module under both interpreters.

Two changes that are not extensions but deserve the same treatment:

- **Change the cut rule.** `data/probe_input.py` (plus a `VERSION` bump); a cut rule that gains
  a parameter also adds the field to `schema.py`'s `build` section and to `PROBE_TEXT_FIELDS`.
  Cost: an inherent full rerun downstream — `build` re-keys, `train` follows through the build
  key, `eval` through the train key, `inject` through `probe_input`'s own version.
- **Rename an axis value.** Not allowed. A value is added and retired instead, never renamed;
  `schema.py`'s `RETIRED` set is what makes retiring safe, so every old run stays reachable.

## 4. The ledgers

`jobs/runs.jsonl` is append-only: one JSON line per stage run, a start row and (once the stage
closes) a finish row, written only by `jobs/registry.py` under its own lock. Nobody edits it by
hand. `jobs/RESULTS.md` is rendered whole from `runs.jsonl` on every append, and is likewise
never edited by hand; `run.py sync` folds any run directory's `done.json` and heartbeat files
into a finish row the ledger is missing. `notes/` — `TIMELINE.md`, `DATA.md`, `WORKPLAN.md`,
`METHOD.md`, `CONTEXT.md`, `plans/` — is the owner's; an agent appends to `TIMELINE.md` only
when a ticket says so, and never edits the rest.
