# Contracts index: every named thing, its defining section, and where else it is mentioned

Built 2026-09-17 from `notes/plans/2026-09-17-contracts.md` and updated after
Round 7 (rows carrying a **Round 6** or **Round 7** note are the ones that moved
in that round), by scanning
the document for every function signature, column,
field, default, constant, marker file, directory-name shape, axis value and
module-level literal, and mapping each hit to the section it falls in.

**How to read it.** "Owner" is the section that states the thing itself: the
format's own section for a column, 2.1/2.2 for a stage's inputs and key, 3.3 for
the key formula, 4.1/4.2 for the environment, 5.x for a setting field, 5.3 for an
axis value, 6.2 for a module or probe-object name, 8.1/8.2/8.3/8.4 for a registry
file's fields, 8.5 for a registry constant. "Also in" lists every other section
that names it; after consolidation those are references, not restatements.
"Note" marks what was collapsed and what disagreed. Part 9(a) entries are
decision records and repeat a fact on purpose; they are not counted as
restatements.

---

## 1. Shared readers, ids and format conventions (Part 1)

| name | owner | also in | note |
|---|---|---|---|
| `read_frame(path, *, schema, defaults, required, version)` | Part 1 | 0.2 | |
| `write_frame(path, df, *, schema)` | Part 1 | 0.2 | |
| `record_id`, `event_id`, `example_id` (the id chain) | Part 1 | 1.1, 1.2, 1.3, 1.4, 2.5, 2.6 | **Round 6**: the three signatures are now beside the id table; each takes the id of the level above |
| `VERSION` (per format file) | Part 1 | everywhere a module version is folded (2.2, 3.3, 4.1, 4.4, 6.2) | the *line shape* is 3.3's |
| `DEFAULTS` (per format file) | Part 1 | 0.4, 1.1 | distinct from `registry.DEFAULTS` (8.5) |
| `REQUIRED` (per format file) | Part 1 | 0.4, 8.6 | |
| the two-rule table for a new column | Part 1 | 0.4 (two task-record rows), 9(a)#29 | |

## 2. Task record — `data/task_record.py` (1.1)

| name | owner | also in | note |
|---|---|---|---|
| record path `<run_dir>/records/<task_id>__s<seed>.jsonl` | 1.1 | 1.5 (by implication) | |
| the `O_EXCL` claim, and release only on the login machine | 1.1 | 2.3 (table cell), 9(a)#30 | **collapsed**: 2.3's cell now references 1.1 |
| six row kinds (`meta`, `gen`, `spec`, `resume`, `env`, `final`) | 1.1 | 4.2, 7.3 | |
| every record column (`task_text`, `judge`, `success`, `generation`, `inject`, `commit`, …) | 1.1 | 1.7, 4.2, 7.3, 9(a)#43, 9(a)#48 | |
| `RESULT_CAP` as the record's observation clip | 4.1 | 1.1, 1.7, 4.2, 4.3, 4.4, 5.2 | **collapsed**: the value 4,000 now only in 4.1 |
| `open_record`, `Writer.row`, `Writer.frame`, `Writer.close`, `is_done`, `owner`, `done_pairs`, `release`, `read`, `read_dir`, `to_messages` | 1.1 | 0.2, 2.3, 2.5, 8.0, 8.4, 8.6 | **Round 6**: `to_messages` gained `extra_developer`, the sixth parameter, applied inside it (7.3); `release`'s live-session set now has a producer, `registry.live_sessions()` (8.0). **Round 7**: `open_record(dir, task_id, seed)` no longer takes `meta` — the claim is the empty create and the `meta` row is the caller's first `row` call; `release(dir, live_sessions, unowned_age_s)` takes the margin as a third argument, so `data/task_record.py` still imports only `data/__init__.py` |
| the relaunch condition ("no piece of `kind` `loop` or `train` has a live session") | 1.1 | 2.3, 2.5 | **added Round 7**: a service piece never exits on its own, so the old "no session of the run" reading was never true and the launch gate's live-session clause now skips `kind: service` |
| `extra_developer` (the appended developer text) | 1.1 | 0.2, 7.3 | **added Round 6** |
| `meta.split`'s producer (the triple `agent/loop.py` walks) | 1.1 | 2.3, 2.5, 4.1 | **added Round 6** |
| `registry.DEFAULTS["launch_timeout_s"]` as the unowned-file margin | 8.5 | 1.1, 2.5, 7.4, 8.1, 8.2, 9(c) | |

## 3. Example, prediction, report (1.2, 1.3, 1.4)

| name | owner | also in | note |
|---|---|---|---|
| every `example` column (`cut`, `cut_index`, `depth`, `text`, `tool`, `call`, `args`, `weight`, `split`) | 1.2 | 1.3, 1.4, 2.5, 2.6 | **Round 7**: `args` has one reader, the build gate of 2.5, and is never read by `eval/`; `call` is `build_call`'s output and no longer "the same string today's `make_call` produces" |
| cparam's derived target string | 1.2 | 1.3, 2.6 | |
| every `prediction` column (`target`, `score`, `label_pred`, `logits`, `text_pred`, `gen_tokens`, `tool`) | 1.3 | 1.4, 2.6 | |
| the two prediction writers (`predict` hook / `trainer.run` copy) | 1.3 | 2.6 (`predict` row) | |
| the class order (`labels`) and its owner | 1.3 | 1.4, 1.6, 2.6, 6.2, 8.3 | |
| `head_labels(df, cfg)` | 2.6 | 1.3, 6.2 | **Round 7**: computed over the **whole** example frame, not the training split, since a val- or test-only tool is an expected condition (2.5 demoted that gate) |
| `write_report`, `read_report` | 1.4 | 0.2, 2.6, 5.4 | |
| every `probe_report.json` field, both shapes | 1.4 | 2.6 | **collapsed**: 2.6's closing field lists became a reference |
| the identity block `probe_eval.run` assembles | 1.4 | 2.6 | **collapsed**: named once, in 1.4 |
| every `fires.parquet` column | 1.4 | 2.6, 9(c) | |
| the three exact-match tiers, and cparam's `tool + "("` rebuild | 1.4 (tiers) / 2.6 (`match`'s callers) | 1.4, 2.6 | **collapsed**: the rebuild rule lives on `match`'s row |

## 4. Run-directory files (1.5), checkpoint (1.6), probe input (1.7)

| name | owner | also in | note |
|---|---|---|---|
| `settings.yaml` (content) | 3.4 (the stage projection) | 1.5, 2.1, 2.6, 5.4, 7.1, 7.2 | **disagreement settled**: 1.5 said "the fully resolved setting", 3.4 "a stage projection"; 3.4 wins (9(a)#32) |
| `settings_diff.yaml` | 1.5 | 3.3, 3.4, 8.1, 8.6 | |
| `_stage`, `_key`, `_upstream`, `_versions`, `_debug`, `_commit`, `_resolved` | 1.5 | 2.1, 2.5, 3.3, 3.4, 5.4, 7.2 | |
| `_upstream`'s naming rule and each stage's map | 1.5 | 2.1, 2.5, 5.4, 7.2, 9(c)#7 | |
| `done.json` (content, and who writes it) | 1.5 | 2.3, 8.0, 8.2 | **Round 7**: what `run.py` writes into it for `sample` and `inject` — `counts`, `metrics: {}`, `report: null`, `versions` — the two stages whose writer is not the stage itself |
| `consumed.json` (three writers) | 1.5 | 2.3, 2.5, 6.3, 8.3 | |
| `dirty.patch` | 1.5 | 2.3, 2.5 | |
| `heartbeat/<piece>-<launch>.jsonl`, and how `<launch>` is resolved | 8.4 | 1.5, 8.0 | **collapsed**: the index rule stated once, in 8.4 |
| `log/<piece>.txt` | 1.5 | — | |
| `service_<kind>_<replica>.json` (content, `attached_to`) | 1.5 | 2.3, 7.1, 7.2, 7.4, 8.1, 8.6 | **collapsed**: 7.1/7.2 field lists became references |
| the checkpoint layout, `best/`, `last/`, `best/meta.json` | 1.6 | 1.3, 2.4, 2.6, 6.2, 7.2 | |
| `call_sep`, `param_only` | 1.6 | 2.6, 5.7, 7.2 | |
| `cuts(thinking, min_think, max_cuts)`, `cuts_live(thinking_so_far, min_think)`, `assemble(...)` | 1.7 | 0.2, 7.3, 9(a)#31 | **fixed**: 1.7 said "Both are pure" for three functions |
| the event-level `min_think` gate, offline and live | 1.7 | 0.2, 2.5, 7.3 | **added Round 7**: `agent/inject.py` scores no cut until the thinking so far reaches `min_think`, the streaming form of the gate `data/build_dataset.py` applies per event |
| `probe_result_cap` vs `Environment.RESULT_CAP` | 1.7 (the distinction) | 4.1, 5.2 | **collapsed**: both values now stated once each (4.1, 5.2) |
| `PROBE_TEXT_FIELDS` | 1.7 | 0.4, 2.1, 2.2, 3.3, 3.4, 5.1, 5.4, 5.7, 9(c)#7 | **collapsed**: 9(c)#7 listed the three members |
| `history` as the earlier steps' pairs | 1.7 | 7.3 | |

## 5. The stage table (Part 2)

| name | owner | also in | note |
|---|---|---|---|
| `STAGES` | Part 2 | 5.1 | |
| the literal shape of the venv cell and the piece-rule cell | 2.1 | Part 2's opening, 2.3, 3.4, 6.3 | **added Round 6**: venv is a string or a `{piece kind: venv name}` mapping with `"env"` meaning the environment's column; the piece rule is `(kind, count_field_or_int, mode)` tuples |
| each stage's "sections read" | 2.1 | 2.2 ("minus" column), 3.3 | 2.2 already says 2.1 is authoritative |
| each stage's upstream, and reference resolution | 2.1 | 1.5, 2.2, 5.4 | |
| the `inject.probe_score` eval-key carve-out | 2.1 | 2.2, 3.3, 5.4, 9(a)#40, 9(c)#5 | **collapsed**: the failure paragraph now only in 2.1 |
| the inherited `build` fields of an inject setting | 2.1 | 1.7, 5.4, 5.7 | |
| what enters each key, and the folded module VERSIONs | 2.2 | 3.3 | |
| piece rules, claiming, done markers, continue | 2.3 | 1.1, 1.5, 8.0 | |
| `requested_pairs` semantics, its five callers, and the projection of its triples to pairs | 2.3 | 0.2, 4.1, 4.2, 5.2, 5.6, 9(c)#8 | **collapsed**: 5.2's `n_tasks` rows no longer restate the order. **Round 6**: it returns `(split, task_id, seed)` triples and the pair projection is stated once, here |
| the skip test for `sample` / `inject` (the pair check) | 2.3 | 1.5, 2.2, 9(c)#2 | |
| the consumed/split-hash gate before a skip | 2.3 | 2.5, 6.3, 8.6, 9(a)#36 | |
| service teardown | 2.3 | 1.5, 8.1, 8.6, 9(a)#37 | **Round 7**: two callers — the walk that writes `done.json`, and `jobs/launch.launch` before it returns any outcome but `up` |
| `run.py refire`, and the retired quota | 2.3 | 8.6, 9(a)#39, 9(c)#4 | **Round 7**: a refire takes `git_state` and re-freezes `_commit` before it restarts the piece, and `refire(run_dir, git, piece)` takes the git dict `run.py` obtained |
| `owners` is written on a skip too | 8.3 | 2.3, 3.4 | **added Round 7**: a reused directory's owner is otherwise never recorded, which is the shared-`sample` case `owners` exists for |
| the train continue rule (three markers) | 2.4 | 2.3, 9(c)#3 | |
| every gate (`build`, `train`, generator `eval`, `inject`, `score`) | 2.5 | 1.1, 1.4, 5.7, 6.3 | **Round 7**: the call-string round trip is a new hard stop (not "today's `check_callstr.py` gates"); a null `env.action` skips the event and an unparsable non-null one stops the build; the unseen-tool row is demoted to a report line; `build.max_examples` is capped per split; the `score` same-setup gate names its source (the two upstream `settings.yaml`) |
| `git_state(run_dir, allow_dirty)` and the ledger exemption | 2.5 | 0.2, 1.5, 2.3, 3.4, 5.1, 8.6 | **Round 7**: `run.py` is its one caller for all six stages and hands the dict to `launch(..., git)` and `refire(run_dir, git, piece)`, so git is probed once per launch |
| the launch gate (the three-clause disjunction) | 2.5 | 8.1, 8.6, 9(c)#6, 9(c)#9 | **Round 7**: the live-session clause counts only pieces whose `kind` is not `service` |
| the card-reservation busy test | 2.5 | 3.4, 8.1, 8.6 (`free`) | **collapsed**: 8.6's `free` row references 2.5 |
| the piece command shape | 2.6 | 2.4, 3.4, 8.4 | |
| `trainer.run(run_dir, method)`, `probe_eval.run(run_dir, method)` | 2.6 | 1.3, 1.4, 1.6, 6.2 | |
| the train hooks (`PROBE_KIND`, `CHECKPOINT_META`, `head_labels`, `batches`, `loss`, `validate`, `predict`, `reference_loss`) | 2.6 | 1.3, 1.6, 3.3, 5.7, 6.2 | **Round 6**: `reference_loss` takes `df`, a slice of the example frame, and the gate's slice and normalisation are pinned; `validate` and `predict` pass their own `CHECKPOINT_META["call_sep"]` into `Probe.generate` |
| the eval hooks (`match`, `report`) | 2.6 | 1.4, 2.1, 5.4 | |
| who owns what on both sides (library vs method) | 2.6 | 8.1, 8.2 | |

## 6. Keys and directories (Part 3)

| name | owner | also in | note |
|---|---|---|---|
| `key(stage, setting)`, `run_dir(stage, setting)`, `run_dir_of(stage, key, *, debug)` | 3.1 | 2.1, 2.5, 5.1, 8.0, 8.6 | |
| the seven guarantees | 3.2 | 9(a)#5 | |
| the key formula | 3.3 | 2.2 | |
| the `models` entry | 3.3 | 2.1, 5.2, 6.1 | |
| the four pre-diff resolutions | 3.3 | 5.2, 6.2 | |
| the `VERSION` / literal line shape | 3.3 | 0.2, 4.1, 5.3, 6.2, 8.6 | |
| `RETIRED` | 3.3 | 0.4 | |
| `<root>/<stage>/<key>/`, `<root>/<debug_subdir>/<stage>/<key>/` | 3.4 | 3.1, 6.3, 8.0, 9(c)#8 | |
| "no `outputs` symlink; `run.py where` prints the path" | 3.4 | 6.3 | **collapsed**: deleted from 6.3 |
| the sweep child name (`repr()` of the parsed value) | 5.5 | 3.4, 9(c)#6, 9(d) | **collapsed**: 3.4 states the name's use, 5.5 its spelling; 3.4's example setting was `ctool_q06`, which sweeps nothing, and is now `ctool_q17_lr` |
| `schema.freeze` and the projection | 3.4 | 1.5, 5.1 | |
| the collision check over `settings_diff.yaml` | 3.4 | 9(a)#32 | |
| `CUDA_VISIBLE_DEVICES` | 3.4 | 8.1 | |
| the ssh transport and the fail-closed rule | 3.4 | 0.2, 6.3, 8.5, 8.6 | **collapsed**: 0.2's `launch.py` description references 3.4 |
| the host-placement rule | 3.4 | 2.3, 7.2, 8.1 | **Round 6**: a fourth case — an agent-service piece the attach test matched takes no card and enters no card search |
| the per-field merge of the non-keyed request fields | 3.4 | 2.3 | **Round 6**: `tasks` null absorbs, `seeds` is the ordered union, `pieces` / `replicas` take the new launch's values |
| where `--piece <i>/<n>` appears | 3.4 | 2.1, 2.6, 8.4 | **Round 6**: only on a `sample` or `inject` loop piece; the other four stages are piece 0 |
| the tmux session name `<stage>-<key>-<piece>` | 3.4 | 8.1 (`run_id`), 8.6 | |

## 7. The environment (Part 4)

| name | owner | also in | note |
|---|---|---|---|
| `StepObservation` | 4.1 | 0.2, 4.2, 7.3, 9(a)#41 | |
| `NAME`, `VERSION`, `INSTRUCTIONS`, `NO_CODE_MESSAGE`, `RESULT_CAP`, `SEED`, `SPLIT_ROLE` | 4.1 | 1.1, 1.7, 3.3, 4.2, 4.4, 5.2, 5.3, 6.3, 8.6 | |
| AppWorld's `SPLIT_ROLE` map | 4.1 | 2.3, 2.5, 5.3, 6.3, 9(a)#44 | |
| `open_env(name)` | 4.1 | 0.2, 2.1, 2.6, 3.4 | |
| `requested_pairs(env, splits, tasks, n_tasks, seeds) -> list[tuple[str, str, int]]` (signature) | 4.1 | 2.3 (semantics), 4.2, 8.3 | **Round 6**: the return type is triples |
| the nine methods | 4.2 | 0.2, 4.1, 4.3, 7.3 | **Round 7**: `build_call` is round-trippable — AppWorld quotes a value with `repr()` when it holds a top-level `,`, `=`, quote or bracket — which is what makes 2.5's round-trip gate passable |
| who calls what | 4.2 | 0.2, 2.3, 2.6 | **disagreement settled**: `jobs/launch.py` calls `tasks` *and* `requested_pairs` |
| the `speculate` three-step guarantee | 4.3 | 4.2, 4.4 | |
| what an environment's `VERSION` guards | 4.4 | 4.1, 2.2 | |

## 8. The setting schema (Part 5)

| name | owner | also in | note |
|---|---|---|---|
| `load`, `load_frozen`, `freeze` | 5.1 | 0.2, 2.3, 2.6, 3.4, 5.7 | **Round 7**: `freeze(setting, stage, run_dir, resolved, commit)` takes the stage, since every section it writes is stage-dependent |
| `cfg._workflow`, and a section the setting does not hold being `None` | 5.1 | 0.2, 2.1, 7.3, 8.1 | **added Round 7**: the stage list had no home on the Setting and the presence tests of 0.2 and 7.3 had no spelling; the start row's `workflow` is the file's name |
| every setting field and its default | 5.2 | 1.3, 1.7, 2.1, 2.3, 2.5, 5.6, 5.7 | **collapsed**: the values of `max_abort_frac`, `align_check`, `predict.splits`, `sample.split`, `probe_result_cap` are now stated only here. **Round 7**: `build.max_examples` is per split, and `inject.max_new` (int, 96, keyed) is new — the probe's generation budget per fire, which 2.1 lists in the inject key and 7.2 carries on the `/gen` request |
| `models.agent_row` / `models.probe_row` | 5.2 | 1.5, 3.3, 6.1, 6.2, 7.1, 7.2, 9(a)#46 | |
| the family-resolved generation defaults (`STOP`, `DEFAULT_EFFORT`, `DEFAULT_DATE` values) | 5.2 | 3.3, 5.3, 6.2 | **collapsed**: 3.3 no longer restates `["<\|return\|>"]` |
| every axis and its values | 5.3 | 5.2, 7.3, 0.4 | **collapsed**: 5.2's `probe.method` / `probe.tuning` / `inject.arm` rows point at 5.3 |
| `ARMS`, `FORMATS` as the checked literals | 5.3 (the axis) / 7.3 (`FORMATS`' fields) | 0.2, 7.2, 8.6 | |
| the four reference fields and the three reference syntaxes | 5.4 | 2.1, 5.2, 5.7 | **Round 6**: 3.3 now excludes all four from `fields`, and 5.2's four `key` cells say "through 3.3's upstream entry and never as a field of the diff" |
| the per-group inheritance rule | 5.4 | 1.7, 2.1, 5.7, 9(c)#7 | |
| `_resolved.probe_temperature` | 5.4 | 1.4, 2.1, 3.3, 7.2, 9(a)#7 | |
| the `sweep:` keyword | 5.5 | 3.4, 5.7, 9(c)#6 | |
| `debug.yaml`'s sizes | 5.6 | 0.2, 2.3, 9(c)#8 | **Round 6**: the `inject:` block gained `max_steps: 6`, and the "default that means no cap" claim was corrected |
| the merge order and every refusal | 5.7 | 2.1, 2.5, 5.2, 5.3, 5.4 | |

## 9. Models and constants (Part 6)

| name | owner | also in | note |
|---|---|---|---|
| `models/table.yaml`'s two blocks and every column | 6.1 | 3.3, 5.2, 6.2, 7.1, 7.4 | |
| `role` and `family` keyed with `result:` | 6.1 | 3.3 | |
| `VLLM_SYSTEM_START_DATE` | 6.1 | 5.2, 7.1, 9(a)#25 | |
| `models.agent(alias) -> AgentModel` / `models.probe(alias) -> ProbeModel`, and the `weights` / `weights_path` naming rule | 6.2 | 0.2, 5.2, 6.1, 7.1, 7.2 | **Round 7**: both return types are named dataclasses with `module` (agent only), `alias`, `role`, `family`, `weights` (always the alias), `weights_path` (always the directory) and `serving`, so nothing is attached to a shared module object and `/health`'s weights alias has a source |
| the family module's names (`render_ids`, `parse`, `end_of_turn`, `wrap_prefetch`, `STOP`, `EFFORTS`, `DEFAULT_EFFORT`, `DEFAULT_DATE`, `NAME`, `VERSION`) | 6.2 | 0.2, 3.3, 5.2, 5.3, 7.1, 7.2, 7.3 | |
| the backbone module's names (`DTYPE`, `LORA_TARGETS`, `HEAD_LAYER`, `prepare_tokenizer`, `attach_head`) | 6.2 | 0.2, 3.3, 5.2 | |
| the probe object (`load`, `Probe.save`, `Batch`, `Outputs`, `Probe.forward`, `Probe.score`, `Probe.generate`, `Probe.tokenizer`, `Probe.max_len`) | 6.2 | 1.3, 1.6, 2.6, 7.2 | **Round 6**: `Probe.generate(texts, max_new, call_sep)` — the caller supplies the separator, which is what gives a generator one on the training path |
| the exceptions to "every keyed column is read from the frozen setting" | 6.2 | 0.2, 7.2, 7.3 | **added Round 6**: the probe service's `serve` resolves `family` and `weights` live, echoes both on `/health`, and `agent/loop.py` compares both. **Round 7**: a second exception — `agent/generate.py` and `agent/inject.py` reach the family through `models.agent(...)`, which resolves the keyed `family` live, so both compare `module.NAME` against `cfg.models.agent_row["family"]` before their first use |
| the classification position (`Batch["event_end"]`, `Probe.score` at a text's last token) | 6.2 | 2.6 | **added Round 7**: nothing pinned the token the decision is taken at, so `base.py` and each method file chose one independently |
| `path_datasets.yaml`'s columns and the `venvs:` map | 6.3 | 0.1, 0.2, 3.4, 4.4, 5.3 | |
| `any` resolves to `venvs.probe` | 6.3 | 2.3, 3.4 | |
| `path_outputs.yaml`'s keys (`root`, `debug_subdir`, `login_host`, `hosts`) | 6.3 | 0.2, 3.4, 8.5, 8.6 | **collapsed**: the `hosts:` columns (name, alias, cards) stated once |
| `path_models.yaml` | 6.3 | 0.2, 6.1, 6.2, 7.1 | |

## 10. Services and the step interface (Part 7)

| name | owner | also in | note |
|---|---|---|---|
| the agent service's command line and check table | 7.1 | 2.3, 6.1 | **fixed**: "within the wait" had no source; now the launch timeout of 8.5 |
| `--attach-only` and the attach verification | 7.1 | 7.4, 8.6 | |
| the agent client (`stream`, `health`) | 7.1 | 7.3, 7.4 | **Round 6**: `Client(base_url, served_model_name)`; `agent/loop.py` passes the frozen `models.agent_row["served_model_name"]` (7.4) |
| the probe service's command line and every route | 7.2 | 2.3, 5.2, 6.2, 7.3, 7.4 | **Round 6**: the three probe flags are bracketed and absent under `--render-only`; both checkpoint flags take the **train run directory** and the service opens `<dir>/best/`; `/health` echoes `weights` and nulls `max_len` in render-only mode. **Round 7**: `/gen`'s request body carries `max_new` (`cfg.inject.max_new`, 5.2) and the client half is `generate(text, max_new)`, so the one parameter of `Probe.generate` with no source has one; the render-only paragraph asks for the same three echo fields the loop's refusal does |
| `check --base-url <url> --run-dir <dir>` | 7.2 | 2.3, 5.1, 8.1, 9(a)#38, 9(c)#7, 9(d) | **Round 6**: it is the sole owner of the `<\|end\|>` encode fixture; 9(d)'s "the service refuses to start otherwise" is gone |
| the loop's and the injector's `/health` refusals | 7.2 | 5.2, 9(c)#7 | |
| `step(env, clients, cfg, writer, messages, prefix_ids, history, task_text, step_index, seed)` | 7.3 | 0.2, 4.2 | |
| `StepResult`, `clients`, `stream(...)` | 7.3 | 1.1, 7.1 | |
| a `FORMATS` entry's four fields | 7.3 | 5.3, 7.2, 0.4 | |
| `system_text(cfg)` | 7.3 | 0.2, 1.1 | **Round 6**: it reaches the conversation as `to_messages`'s `extra_developer`, on every call, not appended once |
| port assignment, `PROBE_PORT_BASE` | 7.4 | 7.1, 7.2, 8.1 | |
| the endpoint-file name rule, and which replica a loop piece talks to | 7.4 | 1.5, 2.3, 8.1 | |

## 11. The registry (Part 8)

| name | owner | also in | note |
|---|---|---|---|
| `beat`, `Heartbeat.emit`, `Heartbeat.finish`, `write_done`, `write_meta`, `append_start`, `append_finish` | 8.0 | 1.5, 2.3, 8.3, 8.4 | |
| `lock()` (the re-entrant context manager) | 8.0 | 2.3, 3.4, 8.1, 8.3, 8.6 | **added Round 6**: one descriptor per process plus a depth counter; `append_start`, `append_finish` and `write_meta` call it unconditionally |
| `live_sessions()`, `session_alive(host, session)` | 8.0 | 1.1, 2.3, 8.5 | **added Round 6**: the producer of the live-session set three mechanisms consume |
| `ls`, `where`, `find`, `kill`, `free`, `sync`, `open_runs` | 8.0 | 2.3, 2.5, 8.5, 8.6 | |
| `ls`'s `edited` and `progress` parameters | 8.0 | 8.4, 8.6 | **collapsed**: the reason stated once, in 8.0 |
| every start-row field, and the piece entry's keys | 8.1 | 2.3, 3.4, 7.4, 8.5, 8.6 | **Round 7**: the three optional per-piece monitoring keys are gone — nothing produced them — and `workflow` is stated as the file's name |
| the launch order inside one lock hold, and the two waves after the release | 8.1 | 2.5, 3.4, 7.2, 8.6, 9(c) | **Round 6**: the attach test runs inside the hold before the card reservation; services, then the `check` client, then the loop pieces |
| every finish-row field, the **five** writers, the `status` enum | 8.2 | 1.5, 2.3, 2.4, 8.5, 8.6 | **Round 6**: `sync`'s condition is `judge`'s `dead` verdict, and a CPU stage that exits non-zero closes its own row |
| every `meta.json` field | 8.3 | 1.3, 1.5, 2.3, 3.4, 6.3, 8.6 | **collapsed**: `owners` and the writer pair stated once |
| the heartbeat line format, `unit` per stage, `total` for a claiming piece | 8.4 | 2.3, 8.0, 8.5, 8.6 | |
| the six verdicts and the verdict functions | 8.5 | 2.3, 8.0, 8.6 | **Round 7**: `stall_line_s(beat_ts)` lost its unreachable `override` parameter, and `DEFAULTS` changes only by an edit to the dictionary |
| `orphan` | 2.3 (the teardown skip) | 8.6 | **Round 7**: 8.6 defined it as the opposite condition ("no live run is attached to"); its cell now covers both survivors |
| `registry.DEFAULTS` and its entries | 8.5 | 1.1, 2.5, 7.4, 8.1, 8.2, 9(c) | **defined here**: `stall_line`, `escalate_line`, `warmup_s` had no stated values |
| every subcommand's output | 8.6 | 2.3, 2.4, 8.0, 8.2, 8.5 | |
| the `login_host` refusal | 8.6 | 3.4, 6.3, 9(a)#34 | |
| the lock and who may append | 8.6 | 2.3, 3.4, 8.0, 8.1, 8.3 | **Round 6**: the span is 8.1's, released before any tmux session; the "`fcntl` allows it within one process" sentence is gone and `registry.lock()` carries the nesting |
| the launch gate's third clause | 2.5 | 8.1, 8.2, 8.5, 9(c)#3, 9(c)#9 | **Round 6**: it holds only while no piece of that row has been observed dead |

## 12. Part 0's annotations, checked against Parts 1-8

| annotation | checked against | outcome |
|---|---|---|
| `run.py` imports | 2.3, 5.4, 8.6 | agrees |
| `run.py` reads `constants/path_outputs.yaml` | 3.1, 3.2, 8.6 | **fixed**: "and the outputs root" dropped; `schema.run_dir` reads the root |
| `run.py` writes | 2.3, 8.1, 8.2 | **fixed**: the start rows of the three CPU stages were missing |
| `schema.py` used by (ten) | 2.6, 5.1 | agrees |
| `data/environments/__init__.py` used by | 2.3, 4.2, 2.6 | **fixed**: `jobs/launch.py (tasks and requested_pairs)` |
| `jobs/launch.py` imports | 2.3, 4.2, 8.3 | **fixed**: `requested_pairs` added |
| `agent/loop.py` imports `models/__init__.py` | 7.2, 7.3, 0.4 | **fixed**: no caller in Parts 1-8; removed from both lines |
| `data/build_dataset.py` description (the `hash` formula) | 5.2 | **collapsed** to a reference |
| `jobs/launch.py` description (ssh, fail-closed) | 3.4 | **collapsed** to a reference |
| `data/probe_input.py` description | 1.7 | agrees (three functions) |
| `tests/`'s cross-reference to 9(b) | 9(b) | **fixed**: it pointed at #16 (`RESULTS.md` into `notes/`); the deferred tests are #17 |
| `models/agent_models/service.py` and `models/probe_models/service.py` descriptions (why they carry `VERSION`) | 2.2 | **collapsed** to a reference |
| `4.2`'s "who calls what" for `eval/score_run.py` | 2.3, 0.2 | **fixed**: it said `split_args` and `build_call` "only" while that file also calls `requested_pairs` |
| `eval/methods/cgen.py`, `eval/methods/cparam.py` imports | 2.6 (`report` calls `open_env`) | **fixed Round 6**: they named `split_args, build_call` instead of the entrance `open_env`, the way the train-side lines are spelled |
| `eval/score_run.py` imports | 4.2 | **fixed Round 6**: `build_call` was missing beside `split_args`; now `open_env for split_args and build_call, and requested_pairs` |
| `run.py` reads | 1.1, 8.0 | **fixed Round 6**: `ssh` and `tmux` added, through `registry.live_sessions`, since `run.py` releases claims |
| `agent/loop.py` reads | 2.3 | **fixed Round 6**: "split task-id file" (singular, from the one-split era) became the files `requested_pairs` resolves |
| `models/probe_models/service.py` reads | 1.6, 7.2 | **fixed Round 6**: `call_sep` is passed into `Probe.generate`, `param_only` is a startup refusal |
| `eval/score_run.py` reads | 2.3, 2.5, 4.2 | **fixed Round 7**: the split task-id files (through `requested_pairs`) and the scored run's and baseline run's `settings.yaml` (the same-setup gate) were missing |
| `jobs/launch.py` offers | 2.3, 2.5, 8.1 | **fixed Round 7**: `launch(..., git)` and `refire(run_dir, git, piece)`, since `run.py` is git_state's one caller |
| `models/__init__.py` description | 6.2 | **fixed Round 7**: it named a "row" with no field names; it now names `AgentModel` / `ProbeModel` and their fields |
| `data/probe_input.py` description | 1.7 | **fixed Round 7**: the live `min_think` gate is named beside the two-coordinate note |
| three cross-references | 9(a), 9(b), 9(c) | **fixed Round 7**: `9(a)#14` -> `#15` (the NumPy alternative) in the facts section, `9(b)#13` -> `#15` (the replay stage) in 9(a)#26, and 2.3's `(9(c)#6)` dropped — no walked scenario is an eval rerun loop |
| every other `imports` / `used by` / `reads` / `writes` / `venv` line | Parts 1-8 | agrees |
| the count | 0.3 | 1 + 1 + 8 + 8 + 4 + 4 + 6 + 2 = **34**, and the annotated tree holds exactly 34 `.py` entries |
