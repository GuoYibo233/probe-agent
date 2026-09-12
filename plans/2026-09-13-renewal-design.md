# new1 renewal: design

Date: 2026-09-13. Status: draft for gyb's review. Nothing in the tree changes
until this document is approved.

## 1. Purpose

Make the repo fast to extend and easy to read. The test cases gyb named:
add a model, change generation settings, add a method, add an evaluation
method, add a dataset, draw figures, and try several similar variants of one
step side by side. Every one of those must be a config edit or one new file
plus one table row.

Decisions gyb has taken (2026-09-12 and 2026-09-13):

- Dead code is deleted on a branch. Old files come back from git history when
  needed. No archive directory.
- One settings JSON per batch holds every parameter, so a run needs no long
  command line. Every ledger entry links the output directory and that JSON.
- Outputs of finished work live only on NFS, and the ledger is the index that
  finds them.
- No hand-written code map. A README explains the repo. The rules for running
  code stay.
- Every place where a choice is made inside the pipeline becomes a named axis
  with a table of variants, and an experiment lists which variants it runs as
  arms.

Not in scope: changing any research method, any output format on NFS, or the
ledger file formats.

## 2. Evidence base

A 16-agent review on 2026-09-12 (eight subsystem readers, three architects,
two judges, three critics) produced the facts below. Line counts are from
`git ls-files` on commit 6bde35b.

| Fact | Value |
|---|---|
| Tracked files | 456 |
| Python lines outside tests | 32.7k |
| Registry tasks | 83; about 20 belong to the two lines that ran in September |
| Places that declare which models exist | 7 |
| Places that declare which cells exist | 7 |
| Files that define one batch | 5, across three directories, plus 22 card tables |
| Files touched to add an agent model today | 6 or 7; three fail silently |
| Files touched to add a cell today | about 10; four are registry tables |

The two live lines are the AppWorld probe chain (collect, annotate, train,
eval, matrix, driven by `pipeline/driver.py`) and the live injection run
(`pipeline/inject/live_appworld.py` with the injection-format axis committed
on 2026-09-12 as abccabd).

## 3. Target tree

```
new1/
  README.md            the repo on one page: what it measures, the two live
                       lines, how to run each stage, this tree, the glossary
  CLAUDE.md            the rules for running code (section 9) and the ledger
                       roles; about 60 lines
  TRAPS.md             measured silent-failure rows for code that still exists
  METHOD.md  DATA.md  WORKPLAN.md  TIMELINE.md  RESULTS.md   unchanged roles

  run.py               front door: dispatch, dirty-tree gate, selfcheck, launch
  tasks.py             registry data only: interpreters, CELLS, TASKS
  models.json          agents (weights, served name, serve flags) and probe
                       backbones (weights, aliases)
  presets/             generation settings, one json per setting

  exp/                 one directory per batch
    np821/exp.json       the finished AppWorld probe batch
    fmt/exp.json         the live injection-format experiment

  core/                imported by every stage
    rules.py             cut constants, sentence boundaries, call parsing,
                         one block per environment
    preset.py            load a preset, merge cli > preset > default, resolve
                         a model key to a path (preset_loader + model_registry)
    heartbeat.py         the progress protocol, stdlib only

  collect/             run_appworld.py  common.py  gen_launch.py
  annotate/            build.py  param_label.py  check_callstr.py  readonly/
  train/               common.py  share_data.py  train_causal_tool.py
                       train_causal_share.py  rowwise_ref.py  lora_util.py
                       readonly_map.py  verify/
  eval/                eval_tool.py  eval_call.py  matrix.py
  live/                probe_server.py  live_appworld.py  inject_format.py
                       world.py  harmony_render.py  rebuild.py  parse_call.py
                       score_live.py  ident3_gate.py  check_bundle.py  jobs/
  figures/             common.py plus one script per figure
  serve.py             the one vLLM launcher: preset server block -> ssh + tmux
  driver.py            the resumable state machine over the whole chain

  ops/                 launch.py  monitor.py  record.py  runmeta.py
                       gpu_status.sh  jobs.json  runs.jsonl  gpu_state.md
                       env_locks/
  demo/                the CPU debugger walkthrough of the live trainer
  tests/               one test file per module it pins
  plans/               live plan and status documents, plus archive/
  docs/agents/         ticket conventions used by ticket-run
  .claude/skills/      gpu-run (shortened), exp-status, ticket-run
  .claude/agents/      gpu-runner, env-runner, job-monitor
  envs/                third-party clones and venvs; zero tracked files
```

Everything under `pipeline/` moves up one level, and `pipeline/inject` becomes
`live/`. NFS paths do not move: the symlinks `pipeline/data`, `pipeline/runs`
and `envs/runs` become `data`, `runs` and `envs/runs`, pointing at the same
NFS directories.

## 4. The mechanism

### 4.1 models.json

```json
{
  "agents": {
    "gptoss": {"full": "gpt-oss-120b",
               "weights": "/net/.../models/gpt-oss-120b",
               "served": "gpt-oss-120b",
               "serve_flags": "--gpu-memory-utilization 0.92",
               "note": "own replica, accepted 2026-07-28"}
  },
  "backbones": {
    "qwen":   {"weights": "/net/.../models/Qwen3-0.6B-Base", "note": "..."},
    "qwen17": {"weights": "/net/.../models/Qwen3-1.7B-Base", "note": "..."},
    "qwen4":  {"weights": "/net/.../models/Qwen3-4B-Base",   "note": "..."}
  }
}
```

The agent key is the collection directory suffix and the matrix column name.
`serve_flags` is a string per model, not a family enum, so a model whose flags
match nothing existing needs no new branch. The backbone keys keep today's
`--base` values, so no existing run command changes meaning. Today the two
backbones in use, Qwen3-1.7B-Base and Qwen3-4B-Base, are in no table at all;
they live in three identical dicts inside the trainers.

Readers: `annotate/build.py` (directory suffix to full name),
`collect/gen_launch.py` (weights and serve flags), `train/common.py`
(backbone lookup), `eval/matrix.py` (the model list comes from exp.json).

### 4.2 presets/

Unchanged in role. One JSON per generation setting with a `client` block and
a `server` block. `--preset` defaults to `default` everywhere. Two changes:

- `collect/gen_launch.py` reads the server block instead of its own constants,
  so a collection batch's memory fraction and max model length are a preset
  edit. Per-server facts (host, card, port, card type, extra flags) stay in
  exp.json because they differ per instance.
- `CUDA_DEVICE_ORDER=PCI_BUS_ID` moves into every preset's `server.env` and
  the injection in `serve_preset.py:50` goes, so the variable that decides
  which physical card an index means on tokyo108 has one source.

The merge order cli > preset > default and the deliberate filter in
`merge_client` stay as they are. A preset key that no consumer reads is
reported by selfcheck as a warning instead of being silently dropped.

### 4.3 exp/<batch>/exp.json

One file per batch. Every stage takes `--exp <batch>` and reads the rest.

```json
{
  "batch": "np821",
  "env": "appworld",
  "model": "gptoss",
  "preset": "default",
  "data": {
    "max_bounds": 64,
    "split_mode": "official",
    "official_split_files": {"train": "...", "val": "...", "test": "..."},
    "seed": 42, "weight_mode": "uniform", "trajs_per_unit": 4,
    "note": "max_bounds=64 is the 2026-08-22 ruling; see TIMELINE"
  },
  "collect": {
    "run_id": "nyapass",
    "seeds": [42, 67, 4267, 6742],
    "traj_per_task": 4,
    "servers": [{"host": "tokyo108", "gpu": 2, "card": "H100", "port": 8103,
                 "extra_flags": ""}],
    "clients": [{"tag": "gptr", "split": "train", "num_shards": 4,
                 "shard_ports": [8103, 8106, 8107, 8108], "exp": "np821gptr"}]
  },
  "arms": {
    "np821b06": {"cells": ["ctool", "cgen", "cparam"],
                 "base": "qwen", "mode": "full",
                 "extra": {"ctool": ["--align-tol", "3e-4"]},
                 "cards": {"train":     {"ctool": ["tokyo108", 0], "cgen": ["tokyo108", 1], "cparam": ["tokyo108", 2]},
                           "eval_tool": {"ctool": ["tokyo108", 0]},
                           "eval_call": {"cgen": ["tokyo108", 1], "cparam": ["tokyo108", 2]}}}
  }
}
```

Derived, never written: the data output directory
(`<nfs>/data/<batch>/<model>`), the run directory of each arm and cell
(`<nfs>/runs/<arm>_<model>_<cell>`), tmux session names, the collector's
output directory (`<env>_<model>`). Written, never derived: the client
experiment names and the card types, because the review showed they cannot be
rebuilt from the run id.

The 22 card tables under `ops/` fold into the `cards` field. The per-arm flags
that today live only in the card tables (`--align-tol 3e-4`) move into
`extra`, so the first merged launch does not drop them.

A live experiment uses the same file with a `live` block instead of `arms`:

```json
{"batch": "fmt", "env": "appworld", "model": "gptoss", "preset": "default",
 "probe": {"ctool_run": "np821b06_gptoss_ctool", "cgen_run": "np821b06_gptoss_cgen", "theta": 0.9},
 "live": {"arms": {"note": {"format": "note"}, "p1e1": {"format": "p1_e1"},
                   "noprobe": {"format": "note", "no_probe": true}},
          "tasks": "dev", "pieces": 12}}
```

### 4.4 The CELLS table

One row per cell in `tasks.py`, carrying everything about it:

```python
CELLS = {
  "ctool":  dict(py="cprobe", train="train/train_causal_tool.py", train_args=[],
                 evals=[dict(script="eval/eval_tool.py", args=["--head", "causal"], dep=None,
                             report="REPLAY_REPORT.json", cols=["theta", "acc_test"])],
                 smoke=True),
  "cgen":   dict(py="cprobe", train="train/train_causal_share.py", train_args=["--mode", "cgen"],
                 evals=[dict(script="eval/eval_call.py", args=["--mode", "cgen"], dep="ctool",
                             report="CALLGEN_REPORT.json", cols=["full_call_ok"])],
                 smoke=True),
  "cparam": dict(py="cprobe", train="train/train_causal_share.py", train_args=["--mode", "cparam"],
                 evals=[dict(script="eval/eval_call.py", args=["--mode", "cparam"], dep="ctool",
                             report="PARAM_REPORT.json", cols=["params_all_ok"])],
                 smoke=True),
}
```

This one table replaces `CELLS`, `CELL_ORDER`, `EVAL_CELLS`, the per-cell
`train-` and `eval-` task entries, the argument-shape branch in
`ops/launch_eval.py:151-162`, and the three private copies inside
`summarize_matrix.py`. `evals` is a list so a cell can carry several
evaluation methods. The launcher, the driver, the matrix, and
`check_bundle.py` all read this table. Task entries for training and eval are
generated from it at import time; hand-written prose notes stay on the row.

### 4.5 Axis tables

Every place where one step can be done in more than one way is an axis: a
name, one table in one module, and a value in exp.json that picks rows.

| Axis | Table | Picked by |
|---|---|---|
| injection format | `live/inject_format.py` FORMATS (exists today) | `live.arms[*].format` |
| trigger threshold | a number | `probe.theta` |
| training axis (LoRA) | `train/lora_util.py` | `arms[*].mode` |
| cell | `tasks.py` CELLS | `arms[*].cells` |
| model | `models.json` | `model`, `arms[*].base` |
| generation setting | `presets/` | `preset` |

Rule: a variant is a table row or a config value, never an `if` on a name
spread across scripts. A script that offers a choice builds its argparse
choices from the table.

### 4.6 The ledger links every run to its output and its settings

`ops/launch.py` registers a run in three places, as today, and the start
record in `ops/runs.jsonl` gains four fields: `out` (the output directory on
NFS), `exp` (the path of the exp.json used), `arm`, and `model`. The launcher
copies the exp.json into the output directory next to `RUNMETA.json`. Finding
a result is one grep of the run id in the ledger; the record names the
directory and the settings. Today launcher-driven runs never pass the output
directory to the record, so no dirty launch has ever saved its patch. This
fix lands in the first commit.

### 4.7 figures/

New. `figures/common.py` holds the style, one color per model and per cell,
and a loader that turns report JSONs in run directories into one table.
Each figure is one script that reads only the ledger and report JSONs, never
raw trajectories, and writes a PDF into `<nfs>/figures/`. Each figure has one
row in `tasks.py`. Whether any venv has matplotlib is unverified; if none
does, one entry in `ops/env_locks`.

## 5. The scenarios in the target tree

| Scenario | Steps | Files |
|---|---|---|
| Add an agent model | one entry in models.json; copy an exp directory and edit model key and server rows | 2 |
| Add a probe backbone | one entry in models.json | 1 |
| Change generation settings | copy a preset, edit values, pass its name, put it in the run id | 1 |
| Add a training method | one trainer importing train/common.py; one CELLS row; one card row in exp.json | 3 |
| Add an evaluation method | one script under eval/ writing a report JSON; one entry in the cell's `evals` list | 2 |
| New dataset, same environment | one exp directory; one DATA.md version entry | 1 + 1 |
| New environment | one collector; one block in core/rules.py; one exp directory; the clone under envs/ | 3 |
| New figure | one script under figures/; one tasks.py row | 1 + 1 |
| Try several variants of one step | rows in the axis table; arms in exp.json | 1 + 1 |

## 6. What is deleted

All to git history. The commit that deletes each group names it in the
message, and one TIMELINE entry (section 10, phase 5) carries the rename
table.

- The ModernBERT line: `pipeline/train/train_mbert_tool.py`,
  `train_mbert_extract.py`, `input_modes.py`, `pipeline/eval/eval_mbert_call.py`,
  the mbert branch of `eval_tool.py`, `mbert-env`'s registry interpreter, the
  five m-line task entries, `tests/test_lora_merge.py`'s mbert cases.
- The offline injection line: `pipeline/inject/replay_inject.py`,
  `splice_replay.py`, `sweep_theta.py`, `launch_plan_sweep.py`,
  `extract_completed.py`, `build_form_table.py`, `form_table.json`,
  `acceptance.py`, `ident3_score.py`, `test_stopfix.py`, `THETA_CURVE.*`,
  `exec_cache/`, the offline half of `exec_calls.py`, the splice and ident3
  task entries and the two splice recipes, `tests/test_splice_replay.py`.
- Environments that never ran a batch: `envs/collect/run_tau2.py`,
  `run_tales.py`, `run_alfworld.py`, `build_dataset.py`,
  `extract_probe_cases.py`, `score_probe.py`, `summarize_full.py`, the four
  split generators under `pipeline/collect/`, `envs/alfworld/splits/`,
  `envs/collect/bfcl_gptoss/`, the nine dead configs under
  `pipeline/configs/`, the manifests w0, c2 and p1, the tau2, tales, bfcl,
  toolhop and StableToolBench task entries, the ALFWorld block of `rules.py`
  once `eval_call.py` no longer imports it.
- One-off launchers: the 16 `envs/serve_logs/launch_*.py`, the three job
  shells there, `ops/ro1_launch/`, `envs/serve_logs`' three acceptance scripts
  (one parameterized check replaces them).
- Registry ceremony: the recipe engine and `RECIPES` (about 294 lines), the
  `status` and `recipes` subcommands, the legacy live-probe renderer in
  `gpu_jobs.py`, the incident auto-spawn half of `sampler.py` and
  `tests/test_incidents.py` (no agent has been spawned since 2026-08-10 while
  the record kept logging escalations).
- Documents: `MAP.md`, `CONTEXT.md` (live terms move into README),
  `.scratch/` except `kvshare-train/verify/` (two of its scripts produced
  RESULTS rows and move to `train/verify/` with registry rows), `talks/`,
  `learn/`, `docs/plans/`, `docs/design/`, the `probe-pipeline`, `handoff` and
  `paper-write` skills, the `deploy-scout` and `paper-verifier` agents,
  `pipeline/annotate/accept_v3diff.py` and its report, `readonly/gen_tables.py`,
  `pipeline/eval/ACCEPT_EVAL.md` and the two `accept_bfcl_v3*` directories.
- The 22 card tables under `ops/` (folded into exp.json), `sweep_lr.py`
  (its report lives in RESULTS), `demo/` stays.

## 7. What is merged

| Today | Target |
|---|---|
| configs/models.json, gen_launch MODEL_TABLE, rules MODEL_OF, matrix --models default, three trainer MODELS dicts | models.json |
| CELLS, CELL_ORDER, EVAL_CELLS, per-cell task entries, launch_eval's branch, matrix's three copies | one CELLS row per cell |
| pipeline/configs/<batch>.json, manifest_<batch>.json, ops/<batch>*_placement.json | exp/<batch>/exp.json |
| train_causal_callgen.py, train_causal_param.py | train/rowwise_ref.py --mode (kept because train_causal_share.py imports both and the alignment gate compares against them) |
| eval_causal_call.py, eval_causal_param.py | eval/eval_call.py --mode, same report names |
| version gate, heartbeat shim, --env block, --force guard, SEED, backbone lookup (copied into each trainer) | train/common.py |
| ops/launch_cmd.py, launch_common.py, launch_probe.py, launch_eval.py | ops/launch.py |
| ops/sampler.py, verdicts.py, gpu_jobs.py | ops/monitor.py |
| model_registry.py, preset_loader.py, sweep_preset.py | core/preset.py, with the grid generator as its `sweep` subcommand |
| serve_preset.py, three acceptance scripts | serve.py plus one acceptance check that exits non-zero |
| pipeline/collect, envs/collect | collect/ |
| exec_calls.py's world primitives, replay_inject's harmony constants | live/world.py |
| extending.md section 5, MAP.md section 5, run.py pitfall notes | TRAPS.md, rows about code that still exists |
| CLAUDE.md's how-to-run half, MAP.md overview and smoke table, CONTEXT.md glossary | README.md |

## 8. What stays because it is load-bearing

The review flagged these as things that look removable and are not.

- The dirty-tree gate with its `LEDGER_PATHS` exemption and the
  `honor_dry=False` asymmetry on the two printing paths.
- `register_all`'s fixed order and its rule that a RUNMETA failure warns
  while a ledger failure aborts.
- `gpu_jobs.cmd_finish`'s fail-closed alive probe.
- `verdicts.DEFAULTS` as the only home for thresholds.
- `ops/heartbeat.py` stdlib-only, so every venv can import it.
- The `train_log.jsonl` event names and `best/` layout, including the old
  field names; the driver, the monitor, and the sweep reader parse them.
- The alignment gates in both trainers and `rowwise_ref.py` as their
  reference.
- `share_data.py`'s stdlib-plus-torch top level and lazy imports.
- `eval_tool.py`'s weight fingerprint in the logits meta, its `--limit`
  smoke gate, and the old report field names.
- The readonly fuse in eval and `readonly_map.py`; the feature is unused but
  ten modules import it, and removing it is a separate decision.
- `harmony_render.py`, `rebuild.py`'s SYSTEM and `check_system_verbatim`,
  `probe_server.py`'s render-only mode, `ident3_gate.py`, the `note` entry of
  `inject_format.py` byte for byte, `MAX_BOUNDS = 64`.
- `gen_launch.py`'s forced output directory name and the manifest preset
  check; `run_appworld.py`'s single-sample file naming and the experiment
  name suffix.
- The driver's launch markers, manifest hash gate, a1_stats stop, and its
  refusal of `--allow-dirty`.
- `build.py`'s three self-checks and hard exit on an unowned unit;
  `param_label.py`'s assert that the two extraction copies agree.
- `preset_loader.require_temperature` and the null-temperature preset.
- `ops/env_locks/`, `ops/gpu_state.md`, the banner-to-stderr rule.

## 9. Rules

These go into CLAUDE.md and are the whole of it, together with the ledger
table and the running-code rules that stay (GPU work through gpu-run, launch
through run.py, commit before launch, big outputs on NFS, no guessing about
results, English on disk).

1. Each fact is written in one place, and every other place imports it.
2. One batch keeps all of its settings in one exp.json, and every stage reads
   that file.
3. A new cell is one CELLS row plus the scripts the row names, in the same
   commit.
4. A variant is a table row or a config value, never a branch on a name.
5. Every ledger record names the run id, the output directory, and the
   exp.json, and the run id is identical in the output directory, the tmux
   session, the ledger, and the commit message.
6. A file that no live line imports is deleted; git history keeps it.
7. Every tracked file is reachable from tasks.py, from an exp.json, or from a
   test, and selfcheck enforces it.
8. A measured trap gets one row in TRAPS.md. A decision that changes the plan
   gets one entry in TIMELINE.md.

## 10. Migration

Branch `renew` off main after phase 0. One commit per phase, each ending with
`python3 run.py selfcheck` and the full unittest run green. Three things keep
working throughout: the np821 chain stays re-runnable through the driver, the
cache-reuse trainer keeps training cgen and cparam, and the injection-format
live run stays launchable and scorable. No NFS path moves.

### Phase 0: clear the desk (on main, before the branch)

- gyb commits the trainer edit in `train_causal_share.py`. It rejects any
  device that is not CUDA, while `demo-train` runs with `--device cpu`; gyb
  decides whether the demo keeps a CPU path.
- The two fmt_smoke jobs finish and are deregistered. The nine runs in the
  ledger with a start and no finish are closed once by hand.
- The two recipe state files under `logs/recipe/` are the only record of
  which commit built each live dataset. Copy each into its dataset directory
  on NFS as `BUILD_PROVENANCE.json` before the recipe engine goes.

### Phase 1: deletions, with the harvest first

- Harvest before deleting: `APPWORLD_SEED`, `TRUNC`, `CKPT`, `requote`,
  `error_kind`, and the deferred `load_steps` from `exec_calls.py`;
  `DEFAULT_STOP` and the harmony markers from `replay_inject.py`; into
  `live/world.py`. Repoint `live_appworld.py`. Find deferred imports by
  grepping every `import` line in the file, not only the module top.
- Delete the groups in section 6. In the same commit: prune
  `tests/test_preset.py`'s entry-point list to the survivors, delete the test
  classes of deleted modules, flip `eval_tool.py`'s `--head` default to
  causal, shrink the `--env` choices lists to the environments that exist,
  remove `recipe` and `status` from CLAUDE.md, rewrite the DATA.md
  provenance sentences that name the recipe.
- Gate: selfcheck, unittest with zero errors (the one known error was the
  splice test, now deleted), `run.py show pipeline` prints.

### Phase 2: reshape directories, no logic

- `git mv` `pipeline/{collect,annotate,train,eval}` up one level,
  `pipeline/inject` to `live/`, the surviving `envs/collect` files into
  `collect/`, the surviving skills' shell script into `ops/`.
- Fix the `sys.path.insert` lines that count parent directories, and the
  three symlinks.
- Gate: selfcheck, unittest, `demo-prep` and `demo-train` on CPU, and
  `ann-build` on np821 into a scratch directory byte-compared against the
  dataset on NFS.

### Phase 3: the tables

- `models.json` with agents and backbones; `exp/np821/exp.json` and
  `exp/fmt/exp.json` written by hand from today's files; the CELLS row;
  `matrix.py` reading the table and the exp; `gen_launch.py` reading the
  preset's server block; `CUDA_DEVICE_ORDER` into the presets; the ledger
  fields of section 4.6.
- Gate: the driver's own byte-for-byte rebuild check on np821
  (`driver.py:1237-1257` does this comparison); regenerate
  `MATRIX_np821b06_r*.md` and diff; regenerate the nyapass server launcher
  and diff against the one on NFS; dry-run the launcher for each of the 111
  finished jobs in `ops/jobs.json` history and diff the command strings.

### Phase 4: the file merges

- `train/common.py`, then `rowwise_ref.py`, `eval_call.py`, `ops/launch.py`,
  `ops/monitor.py`, `core/preset.py`, `serve.py`.
- Gate per merge: its tests; `--align-only` for cgen and cparam on np821
  data; re-score np821b06 cgen and cparam with `--cached-logits` and diff
  both reports byte for byte; one smoke launch that lands three ledger
  entries; `demo/README.md` and `WALKTHROUGH.md` repointed at the renamed
  module.

### Phase 5: live/, documents, skills

- `probe_server.py`'s default run paths become required arguments.
  `README.md`, `CLAUDE.md`, `TRAPS.md` written; `MAP.md` and `CONTEXT.md`
  deleted; the gpu-run skill cut to the steps a command cannot do.
- One TIMELINE entry with a rename table: old path, new path, first commit
  where the new path applies. It covers the 35 ledger commands and the 39
  RUNMETA files on NFS that name old paths. Entries before the renewal keep
  naming the old tree; TIMELINE is append-only.
- Gate: `git grep` for every deleted path and command name returns nothing
  outside TIMELINE and RESULTS.

### Phase 6: prove the chain

- One 20-task batch end to end through the driver on the new tree, collect
  through matrix, plus one live arm through `live_appworld.py`. Check that the
  run id appears identically in the NFS output directory, the tmux session,
  the ledger, and the commit message. Then merge `renew` into main.

## 11. Open items for gyb

Each has a default. Silence means the default.

1. The trainer edit's CUDA-only guard versus the CPU demo. Default: the
   guard allows `cpu` when the data directory is the demo fixture.
2. Auto-finishing a run on the monitor's done verdict. Default: not adopted;
   finish stays a manual command.
3. The readonly feature (303 branch lines, never launched). Default: kept
   this round, listed in WORKPLAN for a later decision.
4. `talks/` and `learn/`. Default: deleted from the repo per the trust-git
   decision; they are in history.

## 12. Expected result

| Item | Today | Target |
|---|---|---|
| Tracked files | 456 | about 130 |
| Python outside tests | 32.7k lines | about 19k |
| Tests | 9.5k lines | about 8.5k |
| Markdown | 24.5k lines | about 5k |
| Registry tasks | 83 | about 40 |
| run.py | 1,309 lines | about 350, tables in tasks.py |
| Places declaring models | 7 | 1 |
| Places declaring cells | 7 | 1 |
| Files per batch | 5 plus card tables | 1 |
