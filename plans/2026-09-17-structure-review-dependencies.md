# Fable review of the fourth draft: Dependency graph and change impact

Reviewer: Claude Fable 5.1 at effort xhigh, read-only, dispatched 2026-09-17 against `plans/2026-09-14-structure-from-zero.md` at commit 96fe9d2. The four reviews of this round are dependencies / structure / grounding / lifecycle; the synthesis is `plans/2026-09-17-structure-review-synthesis.md`.

---

# Dependency and change-impact review of `/home/y-guo/reproduce/new1/plans/2026-09-14-structure-from-zero.md` (fourth draft, 96fe9d2)

Read-only. Sources: the plan; the third draft's Part 2 at commit 771a6e5 (module reads, venvs, which files fold in); `/home/y-guo/reproduce/new1/CONTEXT.md`; today's code under `pipeline/`, `ops/`, `run.py`, `model_registry.py`, `preset_loader.py`, `configs/` (imports listed per file, nothing grepped from the root); the three 09-14 reviews and their synthesis. Where the fourth draft is silent I take the third draft's text (the stage table, what each module reads) as the intent, and say so.

## 1. Verdict

Want (a) holds for the in-family changes the tree was designed around (a hyperparameter, a model alias of a known backbone, a metric on existing record fields, the cut rule, an injection format that reuses a placement): the set is one to three files and it is named on the line, with one systematic undercount, that `experimental_settings/schema.py` and the module that reads the new value are left off every count. Want (a) fails for the two extensions the tree exists to invite: a fourth probe method touches five to eight files across `data/`, `models/`, `train/`, `eval/` and `agent/` where the plan says two, and a second agent-model family touches `agent/inject_format.py` and `models/probe_models/service.py` where the plan says one. Want (b) fails at the centre: `schema.py` is imported by about ten files and edited by every extension, `jobs/registry.py` is imported by about ten and sits in the top layer, and neither line says who; the eval `report.json` (theta per risk target, fitted temperature) is read by three files in two layers and is defined nowhere. There are three wrong-direction edges (`schema.py` importing `agent/inject_format.py`; `train/methods/*` importing `eval/methods/*`; `models/probe_models/service.py` depending on the agent family's tokenizer and on an eval output) and one probable import cycle (the key folds every stage's `VERSION`, every stage imports the loader) that the plan does not resolve. The two recurring rules narrow the search (a misspelling fails at load; a column is declared once) but concentrate the edits: `schema.py` becomes the file everyone edits and everyone imports, so the plan's small-change claims become true only after it is split into the part that is edited (fields, axes, stage table) and the part that is imported (the loader and the key).

## 2. Top problems, ranked by how much they hurt change impact

**P1. `experimental_settings/schema.py` holds five responsibilities, has fan-in ~10, is edited by every extension, imports the agent layer, and probably cycles with every stage.**
The line gives it: field defaults and comments, the axes, the stage table, the loader (merge, debug overlay, overrides, sweep expansion, references), and the key (hash, versions, manifests). The third draft's stage table says the key folds in the `VERSION` of `loop`, `task_record`, `build_dataset`, `probe_input`, `trainer`, the method files, `inject_format`, `score_run`; if `key()` reads those constants it imports the modules, and those modules import `schema.py` to read the setting: a cycle at import time. The plan also has the `inject.format` axis read `agent/inject_format.py`'s keys, which is the settings layer importing `agent/`.
Scenario that exposes it: add a probe method. The edit lands in `schema.py` (axis value, a new `inject.probe_*` reference field, and the stage table if it names programs); a mistake there fails every stage of every workflow at import, and the reader of the tree cannot narrow "who breaks" below "everything".
Fix: split into three files with one direction of import. `experimental_settings/schema.py`: the dataclasses, defaults, axis lists as literals, the stage table; imports nothing from the repo. `experimental_settings/loader.py`: file to setting, diff, debug overlay, overrides, sweep, references, `save`; imports `schema.py`. `experimental_settings/key.py`: `key(cfg, stage, versions)` where the calling stage passes its own `VERSION` tuple; imports nothing from the layers. Axis lists stay literal; `run.py selfcheck` cross-checks them against the files (`inject_format.FORMATS.keys()`, `data/environments/*.py`, `train/methods/*.py` intersected with `eval/methods/*.py`). Cost: the sixth-format claim becomes "one entry, one axis line, one YAML line". Gain: no settings file imports a layer, no cycle, and "who breaks when I edit the axes" is `loader.py` plus the selfcheck.

**P2. A probe method is one thing in the plan's words and five to eight files in its tree; the train-to-eval import is part of the same spread.**
The plan says "a new probe method is a file under `methods/` plus a `schema.py` value" (train) and "a file under `methods/`" (eval). But the method's example construction is in `data/build_dataset.py` ("records -> example rows for the three probe methods"), its target type is in `data/example.py` ("a label for ctool, a call for cgen, arguments for cparam"), its output type is in `data/prediction.py` ("the score (ctool) or the generated text (cgen, cparam)"), its probe action is in `models/probe_models/base.py` ("score a prefix, generate a call"), its live use is in `models/probe_models/service.py` and `agent/inject.py`, and its prediction step is in `train/utils/trainer.py` ("the probe run over val and test") unless the method file supplies a `predict` hook, which the plan does not say. And `train/methods/<m>.py` imports `eval/methods/<m>.py` for its validation match: a fix to the match function changes which checkpoint becomes `best/`, so the train key must fold `eval/methods/<m>.py`'s `VERSION`, and an evaluation fix reruns days of training. (Today's train validation is cross-entropy, `pipeline/train/train_causal_share.py:243`; the exact-match validation and the import are new in the plan.)
Fix: one per-method module in the bottom layer, `data/methods/<m>.py`, holding the three method-specific pieces that today leak upward: the example row from a record, its cuts and the environment object (called by `build_dataset.py`), the target type, and `match(prediction_row)` (called by both `train/methods/<m>.py` for validation and `eval/methods/<m>.py` for the report). `example.py` and `prediction.py` keep a method-agnostic `target` / `output` column (text) plus a `method` column. `train/methods/<m>.py` keeps batches, loss, checkpoint layout and a `predict(probe, rows)` hook so `trainer.py` never branches on method. Then a fourth method is exactly `data/methods/x.py`, `train/methods/x.py`, `eval/methods/x.py`, one axis line, one README block, and no import points upward.

**P3. The eval report is an undefined cross-layer format, and the cgen/cparam evals have a hidden second upstream.**
`eval/methods/ctool.py` writes theta per risk target and the fitted temperature. Readers: `models/probe_models/service.py` (temperature; the plan's line says only "loads the probe"), `eval/methods/cgen.py` and `cparam.py` ("at the frozen theta", which is ctool's theta: today `--ctool-run`, `eval_causal_call.py:536-538`, `eval_causal_param.py:363-365`, and `run.py:104-110` records "cgen and cparam consume ctool's"), and `method_table.py` through the registry row. The plan's rule "every on-disk format between two stages is defined in `data/`" is broken by this file, and the eval key ("the train key" plus the eval section) does not contain the ctool eval it reads.
Scenario: change the theta fit in `eval/methods/ctool.py`. Its own key changes; the cgen and cparam eval keys do not, so their directories are reused with the old theta; the live probe service silently loads whichever temperature is in the referenced directory.
Fix: `data/probe_report.py` (theta per risk target, temperature, the metric block; write, read); an `eval.theta_from: <workflow>/<setting>` reference field in `schema.py` that cgen and cparam evals require and that enters their key, mirroring today's `EVAL_CELLS` dependency table.

**P4. `models/probe_models/service.py` depends on the agent family.**
Its encode/decode/render half uses the agent model's tokenizer and template (today `probe_server.py:77,143,207-215`: `oss_tok`, `harmony_render`), because the loop's venv cannot import the tokenizer. The plan's line hides this; `agent/inject_format.py`'s `TAIL` and `PREFETCH_SENDER` are harmony control tokens, so the "five ways" are five gpt-oss ways.
Scenario: add Qwen as an agent family. The plan says one file (`agent_models/qwen.py`) and a table row; in fact `inject_format.py` (the p2 tail), `probe_models/service.py` (whose tokenizer it loads) and `agent/inject.py` (control tokens for the after placement) change too.
Fix: the agent's own server answers encode and decode (vLLM's OpenAI-compatible server exposes `/tokenize` and `/detokenize`), so `models/agent_models/service.py`'s client gains `encode`/`decode` and `probe_models/service.py` keeps only score and generate; the control-marker wrapping of a p2 message moves into the family file (`gptoss.py: wrap_prefetch(body)`), leaving `inject_format.py` with placement, body and system text only. Then a second agent family is one file plus a row, as claimed.

**P5. Result-changing values sit outside `experimental_settings/` and enter no key.**
Two cases. vLLM serving flags: the line for `agent_models/service.py` says "edited when the serving flags change", but `max_model_len`, dtype, quantization and seed handling change outputs, and code does not enter the key; the plan's own `table.yaml` column "how it is served" is keyed. The benchmark's task-split lists: `constants/path_datasets.yaml` names "its task splits", `constants/` never enters a key, and the build key folds the sample manifest, not the split files.
Scenario: change a serving flag, rerun a sample setting: the old directory is reused. Edit a split list: the build key is unchanged, `train/val/test` membership changes silently.
Fix: result-affecting serving flags live in the `table.yaml` row (already keyed); `service.py` keeps ports, health waits and attach logic and its line drops "serving flags". Split lists are owned by the environment file (`tasks(split)` reads them; the environment `VERSION` covers a change) or their hashes join the build manifest.

**P6. Renaming an axis value orphans every directory and makes saved runs unloadable.**
The value enters the hash, so every old directory gets a stale key; `run.py <dir>/settings.yaml` ("repeat an old run exactly", third draft) fails on the retired value because the axis is strict; `find` by the new name misses old rows. The skeptic's alias table was not adopted.
Scenario: rename tuning `lora` to `lora_r16` after nine trainings exist. Touches `schema.py`, every YAML with the value (gyb, hook), `trainer.py` if it branches on the string, `method_table.py` labels; and no old run is reachable by the new name.
Fix: a `RENAMED = {("probe.tuning", "lora"): "lora_r16"}` dict in `key.py` applied before hashing and in `loader.py` before axis validation; or the rule "an axis value is never renamed, only added and retired".

**P7. The environment-to-venv mapping has no file.**
The loop piece runs "in the environment's venv"; nothing in the tree says where `jobs/launch.py` learns the interpreter path (today `run.py:63-75`, `PY`). Scenario: add an environment; the plan's list (sibling file, clone, path, axis value, README) omits the one edit that makes the launcher start the loop. Fix: a `venv:` field on the environment's row in `constants/path_datasets.yaml` (it is a location), read by `launch.py`.

**P8. `jobs/registry.py` is in the top layer by placement and the bottom layer by use, and its line mixes two edit reasons.**
"Every stage imports it" and "edited when ... a subcommand's output changes": a change to `ls` formatting is an edit to a file ten stage modules import. The plan defers the split "the day ls or kill needs more". Fix: split now, at zero cost: `jobs/registry.py` (append row under lock, heartbeat, `meta.json`, git probe; imported by stages; standard library) and `jobs/registry_cli.py` (ls, where, find, kill, `RESULTS.md` render; imported by `run.py` only).

**P9. Adding a column to a format is either a full rerun of the writer stage or an unreadable old file.**
`data/__init__.py` promises "every read returns a Polars DataFrame with the format's declared columns and types"; a record column added with a `VERSION` bump re-keys sample and inject (days of GPU); added without one, old files fail the strict read. Fix: the format file declares a default per column added after the first version; `VERSION` bumps only when an existing column changes meaning; the key folds only that.

**P10. The ctool head has two owners on the tree.**
`train/methods/ctool.py` says "its head"; `models/probe_models/base.py` says "score a prefix" and `load, save`, and `probe_models/service.py` and the trainer's prediction step must load that head. Fix: the head class and its save layout live in `probe_models/base.py` (attach point from the backbone file); `train/methods/ctool.py` only trains it.

**P11. Two smaller inconsistencies.** The base class line says "eight methods" and lists nine (`tasks, open, step, speculate, judge, close, split_args, build_call, complete_call`). `data/build_dataset.py` (venv "any") calls the environment object for call parsing; if `environments/appworld.py` imports the AppWorld package at module top, build runs only in the appworld venv; the line should say the package import sits inside `open()`, as the service files do for torch. And `debug.yaml`'s "100 eval examples" is now read by train's last step, so the stage table must list that field under train's reads or the field moves to `train.predict_n`; otherwise an `eval.*` edit re-keys training.

## 3. Adjacency list (planned file -> what it depends on)

Layer order as the plan gives it, bottom to top: `constants` < `experimental_settings` < `data` < `models` < `agent` < `train` < `eval` < `jobs` < `run.py`. Marks: [FAN-IN n] for n > 4; [CYCLE]; [WRONG-DIRECTION] when a lower layer depends on a higher one. "reads"/"writes" are disk formats.

```
constants/path_datasets.yaml   leaf. read by data/environments/appworld.py (home, split lists); should be read by jobs/launch.py for the venv (P7)
constants/path_outputs.yaml    leaf. read by run.py, jobs/launch.py, jobs/registry.py
constants/path_models.yaml     leaf. read by models/__init__.py, models/agent_models/service.py, models/probe_models/base.py
models/table.yaml              names constants/path_models.yaml aliases. read by experimental_settings/schema.py (rows expanded before keying), models/__init__.py, models/agent_models/service.py, models/probe_models/service.py  [FAN-IN 4, borderline]
experimental_settings/*.yaml   read by schema.py only (hook-protected)

experimental_settings/schema.py
  imports: agent/inject_format.py (axis keys)                                   [WRONG-DIRECTION settings->agent]
  needs VERSION of: data/task_record.py, data/example.py, data/prediction.py, data/probe_input.py,
     data/build_dataset.py, data/environments/<env>.py, agent/loop.py, agent/generate.py, agent/inject.py,
     agent/inject_format.py, train/utils/trainer.py, train/methods/*, eval/methods/*, eval/score_run.py
     (third-draft stage table; the fourth draft is silent on how key() gets them)   [CYCLE with each, unless passed in]
  reads: experimental_settings/*.yaml, models/table.yaml, constants/*.yaml (after keying)
  writes: settings.yaml, settings_diff.yaml in the run directory
  imported by: run.py, jobs/launch.py, agent/loop.py, data/build_dataset.py, train/utils/trainer.py,
     eval/utils/probe_eval.py, eval/score_run.py, eval/method_table.py,
     models/agent_models/service.py, models/probe_models/service.py          [FAN-IN 10]

data/__init__.py               polars. imported by task_record.py, example.py, prediction.py
data/environments/__init__.py  importlib environments/<name>.py. imported by appworld.py (subclass), agent/loop.py,
                               agent/inject.py (env object), data/build_dataset.py (call parsing)   [FAN-IN 4, borderline]
data/environments/appworld.py  environments/__init__.py; external/appworld package; reads constants/path_datasets.yaml
data/task_record.py            data/__init__.py. written by agent/loop.py (+ agent/inject.py events);
                               read by data/build_dataset.py, eval/score_run.py                    [FAN-IN 4, borderline]
data/example.py                data/__init__.py. written by build_dataset.py; read by train/utils/trainer.py, train/methods/*
data/prediction.py             data/__init__.py. written by trainer.py (last step); read by eval/utils/probe_eval.py, eval/methods/*
data/probe_input.py            leaf. imported by data/build_dataset.py, agent/inject.py
data/build_dataset.py          schema.py, task_record.py, example.py, probe_input.py, environments/__init__.py,
                               jobs/registry.py [WRONG-DIRECTION by the plan's order]; reads records, split lists;
                               writes examples, manifest.json, report

models/__init__.py             table.yaml, constants/path_models.yaml; importlib agent_models/<family>.py, probe_models/<backbone>.py.
                               imported by trainer.py, probe_models/service.py, agent_models/service.py,
                               agent/generate.py or loop.py (the family file), schema.py (rows)      [FAN-IN 5]
models/agent_models/__init__.py  empty
models/agent_models/gptoss.py  openai_harmony inside render(). imported by agent/generate.py (end of turn, parse),
                               agent/inject.py (control tokens, head boundary), agent/loop.py (parse),
                               agent_models/service.py (render-equals-server check),
                               probe_models/service.py (encode/decode with the agent tokenizer, today probe_server.py:77,143)
                                                                                    [FAN-IN 5; WRONG-DIRECTION probe->agent]
models/agent_models/service.py models/__init__.py, table.yaml, constants/path_models.yaml, gptoss.py, schema.py (generation),
                               jobs/registry.py; vllm inside. client half imported by agent/generate.py, agent/loop.py;
                               server started by jobs/launch.py
models/probe_models/__init__.py  empty
models/probe_models/base.py    torch/transformers/peft; probe_models/<backbone>.py (quirks); constants/path_models.yaml;
                               reads/writes the checkpoint layout (best/, last/, head, label map: a format defined only here).
                               imported by trainer.py, train/methods/ctool.py, cgen.py, cparam.py,
                               probe_models/service.py, qwen.py                                    [FAN-IN 6]
models/probe_models/qwen.py    base.py (subclass) or imported by base.py; the plan does not say which
models/probe_models/service.py base.py (inside), schema.py (inject.probe_score/probe_gen/theta -> references),
                               jobs/registry.py (reference -> directory), gptoss.py + agent tokenizer [WRONG-DIRECTION],
                               reads eval report.json of the ctool run (temperature; undefined format) [WRONG-DIRECTION models<-eval output].
                               client half imported by agent/inject.py; server started by launch.py

agent/loop.py                  schema.py, environments/__init__.py, task_record.py, agent_models/service.py (client),
                               gptoss.py, generate.py, inject.py, jobs/registry.py; writes records, heartbeat.jsonl
agent/generate.py              agent_models/service.py (client), gptoss.py. imported by loop.py, inject.py
agent/inject.py                generate.py, probe_input.py, probe_models/service.py (client), inject_format.py,
                               the env object (speculate, complete_call, build_call), gptoss.py, task_record.py (events)
agent/inject_format.py         leaf; harmony-specific text. imported by inject.py, schema.py

train/utils/trainer.py         schema.py, models/__init__.py, base.py, example.py (read), prediction.py (write),
                               jobs/registry.py; torch/peft. imported by train/methods/* (3)
train/methods/ctool.py         trainer.py, base.py, eval/methods/ctool.py (match)                  [WRONG-DIRECTION train->eval]
train/methods/cgen.py          trainer.py, base.py, eval/methods/cgen.py (match)                   [WRONG-DIRECTION]
train/methods/cparam.py        trainer.py, base.py, eval/methods/cparam.py (match)                 [WRONG-DIRECTION]

eval/utils/probe_eval.py       prediction.py, schema.py (eval section), jobs/registry.py; polars. imported by eval/methods/* (3)
eval/methods/ctool.py          probe_eval.py; writes report.json (theta per risk, temperature: undefined format).
                               read by probe_models/service.py, eval/methods/cgen.py, eval/methods/cparam.py, method_table.py (via the row)
eval/methods/cgen.py           probe_eval.py; reads the ctool eval's report.json (theta: a second upstream absent from the setting and the key).
                               imported by train/methods/cgen.py
eval/methods/cparam.py         same shape as cgen.py
eval/score_run.py              task_record.py, schema.py (score, baseline reference), jobs/registry.py; reads two runs' records; writes report.json
eval/method_table.py           jobs/registry.py (rows), schema.py (sweep grouping)

jobs/launch.py                 schema.py (stage table), jobs/registry.py, constants/path_outputs.yaml, the env->venv mapping (no file, P7); tmux, nvidia-smi
jobs/registry.py               standard library; git; writes runs.jsonl, RESULTS.md, meta.json, heartbeat.jsonl.
                               imported by run.py, launch.py, loop.py, build_dataset.py, trainer.py, probe_eval.py,
                               score_run.py, method_table.py, agent_models/service.py, probe_models/service.py
                                                                     [FAN-IN 10; top layer imported by every lower layer]
run.py                         schema.py, jobs/registry.py, jobs/launch.py, constants/path_outputs.yaml; starts stage programs as subprocesses. imported by nobody
```

Cycles: C1 `schema.py` <-> every versioned stage module through `key()` (import-time, unless versions are passed in). C2 (layer level) `train/methods/*` -> `eval/methods/*` by import while `eval/*` <- `train/*` by disk. C3 (layer level) `models/probe_models/service.py` <- `eval/methods/ctool.py`'s report by disk while `eval` <- `train` <- `models` by import.

## 4. Scenario table

| Scenario | Plan's claim | Files that must change (named by the plan) | Hidden touches (not named) | Must NOT change | Claim |
|---|---|---|---|---|---|
| Add a benchmark environment | sibling under `data/environments/`, clone+venv under `external/`, path in `constants/path_datasets.yaml`, axis value in `schema.py`, README; `--debug` | those five | the env-to-venv mapping (no file, P7); OmegaConf/PyYAML/Polars installed into the new venv; `data/task_record.py` and `eval/score_run.py` if `judge()` returns something other than a boolean (the plan does not fix the return type); the new setting YAML (gyb) | `agent/loop.py`, `generate.py`, `inject.py`, `probe_input.py`, `train/*`, `eval/methods/*`, `models/*` | incomplete by one certain item (venv mapping) and one conditional |
| Add a fourth probe method | `train/methods/x.py` + `schema.py` value; `eval/methods/x.py` | those three, README | `data/build_dataset.py` (the per-method example rows, certain); `data/example.py` and `data/prediction.py` if the target/output type is new; `train/utils/trainer.py` if the prediction step branches on method (unspecified); `models/probe_models/base.py` if a new probe action; `probe_models/service.py`, `agent/inject.py`, and a new `inject.probe_*` field in `schema.py` if used live; `eval/method_table.py` if columns are enumerated | `agent/loop.py`, `generate.py`, `environments/*`, `jobs/*`, `run.py` | incomplete: 5 to 8 files, not 3 (P2) |
| Add a training hyperparameter (warmup ratio) | "a YAML line" | the YAML line (gyb) | `schema.py` (field + default + comment, the plan's own schema line says so), `train/utils/trainer.py` (use it in the schedule); if the old behaviour cannot be the default, a trainer `VERSION` bump re-keys every train, eval and inject run | `train/methods/*`, `eval/*`, `data/*`, `run.py`, `launch.py` | incomplete by two files; the set is small and known |
| Add a field to the task record | `task_record.py` "edited when a field is added" | `task_record.py` | the writer: `agent/loop.py` (a step field), `agent/inject.py` (a speculation-event field) or `environments/appworld.py` (an environment-derived field); consumers `build_dataset.py` / `score_run.py` if used; with a `VERSION` bump the sample and inject keys change, so every existing sample directory is orphaned and build/train/eval follow through the manifest; without a bump, old files fail the strict Polars read (P9) | `train/*`, `eval/methods/*`, `models/*` | incomplete: 2 to 4 files and a rerun-or-unreadable choice the plan does not name |
| Add a sixth injection format | "one entry here and a YAML line, nothing else" | `inject_format.py`, the YAML line (gyb) | none if the format reuses a placement (think/after) and the gpt-oss tail; `agent/inject.py` plus `agent_models/gptoss.py` plus `probe_models/service.py` (encode with special tokens) for a new placement; `schema.py` imports `inject_format.py` to make this work (P1); editing an existing entry's text changes no key, so `inject_format.py` needs the `VERSION` the third draft gave it and the fourth omits | `loop.py`, `generate.py`, `train/*`, `eval/*` | correct for the narrow case; the condition is not stated |
| Change the cut rule | `probe_input.py` "edited when the cut rule changes" | `probe_input.py` (+ `VERSION`) | none in code while the interface stays character positions; `agent/inject.py` if the rule becomes token-based (the head boundary); the cascade: build key changes, train follows through the manifest, eval through the train key, inject through the two eval keys and `probe_input`'s own `VERSION`; every downstream directory reruns | `build_dataset.py`, `task_record.py`, `models/*` | correct; the cost (a full rerun) is inherent and should be on the line |
| Add a metric to `score_run` | `score_run.py` "edited when a metric is added" | `score_run.py` (+ `VERSION`; re-keys score, CPU-cheap) | `task_record.py` + `loop.py`/`inject.py` if the metric needs an unrecorded field (then the record scenario applies); `jobs/registry.py` if the finish row's summary field list is fixed there; `method_table.py` if it shows run metrics | `train/*`, `eval/methods/*`, `data/*` other than the record | correct for a metric on existing fields |
| Add a probe backbone (Llama) | `probe_models/llama.py` + a `table.yaml` row; a known backbone needs only the row | `llama.py`, `table.yaml`, `constants/path_models.yaml`, README | `schema.py` if backbone names are an axis (the "register every value" rule says yes, the models line says no; the plan has two sources of allowed model names); `train/utils/trainer.py` or `base.py` if Llama's attention path needs a flag (GQA/SDPA quirks live in the trainer today) | `train/methods/*`, `eval/*`, `agent/*`, `data/*` | correct if the axis question is settled in `table.yaml`'s favour |
| Add an agent model family (Qwen) | `agent_models/qwen.py` + a row | `qwen.py`, `table.yaml`, `path_models.yaml`, README | `agent/inject_format.py` (the p2 tail is harmony tokens), `models/probe_models/service.py` (loads the agent tokenizer, P4), `agent/inject.py` (control tokens), `agent_models/service.py` if serving flags are per family and not in the row | `loop.py`, `generate.py` (through the family file), `train/*`, `eval/*`, `data/*` | incomplete by two to three files (P4) |
| Change the vLLM serving flags | `agent_models/service.py` "edited when the serving flags change" | `service.py` | nothing enters a key, so sample and inject directories are reused with different outputs (P5); the flag belongs in the `table.yaml` row instead | everything else | correct as written and wrong as a design: the edit should be a row, not code |
| Change how examples are split | `build_dataset.py` "edited when ... the split ... changes" | `build_dataset.py` (+ `VERSION`; re-keys build, then train through the manifest, eval, inject) | `schema.py` if the rule becomes a `build.*` field; `constants/path_datasets.yaml` if the split follows the benchmark's task lists, whose contents enter no key (P5); `data/example.py` if the split label is a column (the plan does not say whether it is a column or three files; eval reading "val rows" and "test rows" implies a column) | `train/*`, `eval/*`, `agent/*` | correct file; one unkeyed input |
| Rename an axis value (a tuning) after runs exist | not addressed (only "an edited value points at a new key, the old directory stays") | `schema.py`, every YAML using it (gyb), README | `trainer.py` if it branches on the string; `method_table.py` labels; every old directory gets a stale key and shows as "setting edited"; `find` by the new name misses old rows; `run.py <dir>/settings.yaml` fails on the retired value (P6) | `data/*`, `agent/*` | not covered; a rename today is a full rerun |

## 5. "If this file changes, who breaks": answerable from the tree and its line?

Visible (the line or the dependent's line names the readers): `experimental_settings/*.yaml` (schema only), `debug.yaml`, `data/__init__.py` (the three formats), `data/example.py` (build -> train), `data/prediction.py` (train -> eval), `data/build_dataset.py` (a program), `data/environments/appworld.py` (through the base class), `models/probe_models/qwen.py`, `agent/loop.py`, `agent/generate.py` (inject's line says it iterates the stream), `agent/inject.py`, `agent/inject_format.py` (inject and schema), `train/utils/trainer.py` (the three methods), `eval/utils/probe_eval.py` (the three methods), `eval/score_run.py`, `eval/method_table.py`, `jobs/launch.py` (run.py), `jobs/runs.jsonl`, `RESULTS.md`, `run.py` (nobody).

Partially visible (one reader named, others not): `data/task_record.py` (the header says "agent -> build"; `score_run.py`'s line is where the third reader and `inject.py`'s event writes are found), `data/probe_input.py` (the fourth draft says "one rule offline and live" without naming `build_dataset.py` and `inject.py`), `data/environments/__init__.py` (loop is obvious; `build_dataset.py`'s call parsing is on build's line), `models/table.yaml` (schema's expansion is stated; the two services are not), `models/agent_models/service.py` (client readers not named), `models/probe_models/service.py` (its reads of the eval report and the agent tokenizer are absent), `jobs/registry.py` ("every stage imports it" is stated; which subcommand outputs are read by `method_table.py` and `launch.py`'s refire is not), `constants/*.yaml` ("read by code", no names).

Not visible (needs reading code): `experimental_settings/schema.py` (ten importers, none listed; the cycle through `VERSION` is invisible), `models/__init__.py` (five importers, none listed), `models/agent_models/gptoss.py` (five importers including the probe service; the line names none), `models/probe_models/base.py` (six importers; "the probe class every backbone shares" hides the trainer, the three methods and the service), `eval/methods/ctool.py` (its report is read by the probe service and by the cgen/cparam evals; nothing on any line), `train/methods/*` (their import of `eval/methods/*` is stated on eval's line, not on train's), the checkpoint layout (written by `trainer.py` plus the method's save layout, read by `base.py`; no line names it as a format), and the env-to-venv mapping (no file).

## 6. The two recurring rules

Register every value in `schema.py` first. It makes a misspelled value fail at load, and it makes the touch set knowable in advance (want a). It does not make the impact smaller: every extension scenario in the table touches `schema.py`, and `schema.py` is imported by ten files, so the file with the highest edit frequency is the file with the highest blast radius, and want (b) is answered "everything" for it. The rule is also applied inconsistently: env, method and tuning values are literals in `schema.py`, while format values are read from `agent/inject_format.py`, which is the one layer inversion in the settings layer. The split in P1 keeps the rule's benefit (fail at load) and moves the edits into a file with fan-in 1 (`schema.py` imported by `loader.py` only), with `run.py selfcheck` as the cross-check.

Every on-disk format defined once in `data/`. For the three named formats it does shrink impact: a column is declared in one file, and readers of the format are two known files each. Three things limit it. The plan has more formats than three: the eval report (three readers in two layers, no owner, P3), the checkpoint layout (owned by `base.py`, unnamed as a format), and `meta.json`/`manifest.json`/`heartbeat.jsonl`/`settings.yaml` (owned by `registry.py` and `schema.py`, read by `run.py`, `launch.py`, `method_table.py`). The strict declared-columns read turns "add a column" into "rerun the writer or lose the old files" unless defaults are declared (P9). And method-dependence leaks into the formats (`example.py`'s target and `prediction.py`'s output are per method), which is why a fourth method touches `data/` at all; P2's per-method module in `data/methods/` is where that leak is meant to go.

## Files cited

- Plan: `/home/y-guo/reproduce/new1/plans/2026-09-14-structure-from-zero.md`; third-draft Part 2 via `git show 771a6e5:plans/2026-09-14-structure-from-zero.md`
- Prior reviews: `/home/y-guo/reproduce/new1/plans/2026-09-14-structure-review-synthesis.md`, `/home/y-guo/reproduce/new1/plans/2026-09-14-structure-review-skeptic.md`
- Today's couplings the plan folds: `/home/y-guo/reproduce/new1/pipeline/inject/probe_server.py` (agent tokenizer and harmony renderer inside the probe service, lines 77, 143, 207-215), `/home/y-guo/reproduce/new1/pipeline/eval/eval_causal_call.py:536-538` and `/home/y-guo/reproduce/new1/pipeline/eval/eval_causal_param.py:363-365` (theta and temperature from the ctool run), `/home/y-guo/reproduce/new1/run.py:63-110` (`PY` interpreter map, `CELLS`, `EVAL_CELLS` dependency table), `/home/y-guo/reproduce/new1/pipeline/train/train_causal_share.py:243` (validation is cross-entropy today), `/home/y-guo/reproduce/new1/pipeline/annotate/rules.py` (cut rule, assemble, call regexes and splitters that the plan spreads over `probe_input.py`, `environments/appworld.py`, `build_dataset.py`), `/home/y-guo/reproduce/new1/pipeline/inject/inject_format.py:36-38` (harmony control tokens in the format table), `/home/y-guo/reproduce/new1/ops/record.py:51-55` (the ledger-path exemption copied in three places today)
