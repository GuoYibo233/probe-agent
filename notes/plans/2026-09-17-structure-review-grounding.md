# Fable review of the fourth draft: Grounding against today's code

Reviewer: Claude Fable 5.1 at effort xhigh, read-only, dispatched 2026-09-17 against `plans/2026-09-14-structure-from-zero.md` at commit 96fe9d2. The four reviews of this round are dependencies / structure / grounding / lifecycle; the synthesis is `plans/2026-09-17-structure-review-synthesis.md`.

---

# Grounding review of plans/2026-09-14-structure-from-zero.md (fourth draft) against today's code

Scope read: the plan, CONTEXT.md, MAP.md, METHOD.md sections 3-4, run.py in full, every Python file's header and import block under pipeline/, ops/, the root, configs/, demo/, learn/vllm/ (61 files in pipeline+ops+root: 47+9+5), plus bodies where the header did not decide a claim (eval_tool.py, share_data.py, train_causal_share.py, live_appworld.py, probe_server.py, envs/collect/common.py, run_appworld.py). Venv checks were import attempts only; nothing was installed or written. plans/archive/ and ACL2026 were not read.

## 1. Verdict

The plan is grounded in the live-run half of the repo: the loop / probe-service / inject-format / launch / registry splits match how `pipeline/inject/live_appworld.py`, `probe_server.py`, `inject_format.py` and `ops/` already divide the work. It is not grounded at the train/eval boundary: the rule "train writes one prediction row per example, eval reads disk with no torch" breaks on three facts in today's code — temperature fitting is torch LBFGS on the full logits matrix (`pipeline/eval/eval_tool.py:213-224`), cgen/cparam predictions today exist only at the trigger rows a ctool run's frozen θ selects (`eval_causal_call.py:11-13,536-549`), which per-example writing would turn into about 507k greedy generations per run instead of at most 8,533, and cparam's `pred_tool` arm reads the ctool run's argmax per row (`eval_causal_param.py:16,93-112,435`). The three-on-disk-formats claim holds for the probe chain only if the prediction row carries the full logits vector and the example row carries per-event token counts, and the registry claim leaves `ops/jobs.json` pieces and the sampler's monitor files without a home. Polars and OmegaConf are installed in none of the four venvs (import fails in cprobe-env, mbert-env, envs/appworld/venv, envs/vllm-env; `/usr/bin/python3` 3.10 has neither polars nor numpy), and the "three venvs" count silently drops mbert-env and five benchmark venvs whose collectors, split generators and cells are still registered in `run.py:63-75`. About a third of today's 61 files have no home and the plan does not state the drop: the offline replay line (replay_inject, sweep_theta, splice_replay, extract/acceptance/form-table, the exec cache), the sampler and verdict engine, the readonly axis, the ident3 gate, the demo fixtures, and every non-AppWorld environment.

## 2. Findings, ranked by severity

### F1 (split contradicted by code). Eval without torch: temperature fitting and the prediction-row shape
- `pipeline/eval/eval_tool.py:213-224` `fit_temperature` runs `torch.optim.LBFGS` over the full val logits matrix (rows × n_labels; label_map has 150 entries in np821 runs, 83 in p1). `eval_tool.py:500-506,522` then does `softmax(logits/T)` on val and test; confidence is the max probability (`replay`, line 243).
- The plan's `data/prediction.py` row holds "the score (ctool)". One score per row cannot be re-tempered; the row must carry the full logits vector (150 floats × 391,893 test rows + 115,211 val rows for nyapass_aw_v1) or T fitting must move into train's last step — which puts a calibration change back on the GPU, against principle 7.
- No venv other than mbert-env has scipy; system python3 has no numpy. LBFGS must be replaced by a 1-D minimizer in numpy or pure Python; a different optimizer gives a different T at its tolerance and can move `chosen_theta` across the 0.025 grid (`THETAS`, line 51). The plan should say the reimplementation is deliberate and that existing numbers are re-derived under it.
- Two more tokenizer uses in eval must become example-row columns: `--overlong drop-event` needs `share_data.n_full_tokens` per event (`eval_tool.py:447-454` meta check; `share_data.py:76-92`), and `token_cost` (`eval_tool.py:200-208`) tokenizes every row for the report. The bootstrap (`eval_tool.py:279-296`) is pure Python and needs nothing.

### F2 (split contradicted by code). "Train's last step writes one prediction row per example; eval only reads"
- Today cgen/cparam generate only at the trigger rows: `eval_causal_call.py:11-13,536-549` reads `chosen_theta[risk]` and `logits_test.pt` from the ctool run, replays to the first crossing per event, and generates at those rows (≤ `n_events_test` = 8,533 in every np821 REPLAY_REPORT.json; 2,275 in p1). Per-example generation over val+test is 507,104 rows at `max_new_tokens=96` (`eval_causal_call.py:243`), roughly 60× today's cost, and cparam does it twice (`gt_tool` and `pred_tool`, `eval_causal_param.py:14-20`).
- The alternative — train's last step reads a ctool run's frozen θ — is a cross-run dependency at train time. Today that dependency is `EVAL_CELLS` (`run.py:104-110`) plus the hard check in `ops/launch_eval.py:6-10,25-31`; the plan's `train_probe.yaml` has no field naming the ctool run a cgen/cparam setting keys on.
- `pred_tool` (`eval_causal_param.py:93-112`, argmax taken from `logits_test.pt` at line 435) needs the ctool prediction rows as an input to cparam's prediction step; the matrix takes only this block (`summarize_matrix.py:10-12`).
- Also lost unless named: the `--self-fire` block (`eval_causal_call.py:413-489`, uses `best/fire_head.pt`), the `--limit` smoke stamp (`eval_tool.py:323-341`), and `--report-dir`.
- What the plan should say: the cgen/cparam prediction row is written at the cut rows a named ctool run's frozen θ selects (a setting field such as `probe.trigger_run`, and the ctool run's eval must finish before), or generation at every cut is accepted and priced; `pred_tool` is either dropped or fed the ctool prediction file.

### F3 (claim does not hold). Polars/OmegaConf are installed nowhere; the venv set is not three
- Import checks: `polars` fails in cprobe-env, mbert-env, envs/appworld/venv, envs/vllm-env and `/usr/bin/python3`; `omegaconf` absent from all; `yaml` present in all four venvs and system python (pyyaml 6.0.3). pyarrow only in cprobe-env and mbert-env. Polars wheels have no runtime dependencies so installation is plausible, but unverified; OmegaConf needs antlr4-python3-runtime, absent everywhere.
- `run.py:63-75` registers 10 interpreters (sys, cprobe, mbert, appworld, alfworld, tales, tau2, toolhop, stbserver, vllm). The plan's three (probe, vllm, AppWorld) drop mbert-env and five benchmark venvs. The plan should state the drop and that eval's interpreter is one of the three venvs (the `sys` interpreter `python3` has no polars and no numpy).

### F4 (split contradicted by code). Harmony rendering has no venv where the loop runs
- The loop runs in the AppWorld venv (`live_appworld.py:57-58`, `exec_calls.py` header: the only two files importing appworld). That venv cannot host openai_harmony: `run.py:136-137` note and `envs/collect/common.py:14-19` (pydantic 2 displaces appworld's pydantic 1.10.26, measured 2026-08-06; site-packages confirms pydantic-1.10.26). That is why `/render`, `/encode`, `/decode` live on the probe server (`probe_server.py:3-6,77`; `live_appworld.py` header item 2).
- The plan puts "messages -> tokens" in `models/agent_models/gptoss.py` and says the empty `__init__` lets the client half import without the family's libraries — but the loop needs the rendering itself. The plan must say which process serves rendering (an endpoint on the agent service side in the vllm venv, or kept on the probe service) and that `gptoss.py` is imported only there. `ident3_gate.py:13-16` shows the vLLM chat endpoint's `prompt_token_ids` equals `/render`, so a vLLM-side path exists.

### F5 (split contradicted by code). One file per method duplicates the whole packed trainer
- Method-specific lines in `pipeline/train/share_data.py`: 215-222, 285-294, 338-340 (tail string, target, cparam assembly-mismatch stop) — about 20 lines; `pack_event`/`allowed_mask`/`batch_mask`/`chunk_by_budget`/`epoch_minibatches`/`worst_blocks` (362-582) are mode-agnostic. In `train_causal_share.py` the mode branches are lines 291, 691-694, 780-781, 793, 1092-1093, 1132, 1243-1249, 1267, 1279 — about 15 lines; forward/backward/eval_ce/mem-probe/align/LoRA/checkpoint (140-930) is one path. ctool packs nothing (`train_causal_tool.py:142-176` uses only `n_full_tokens` and `read_position`).
- So "no shared packing module" is mechanically possible but means two ~1,000-line copies differing in ~35 lines, of code that is today one file selected by `--mode` (`run.py:85-88`). Principle 5 (share on the third repetition) is being applied to code that has already been merged once. The plan should either keep `train/utils/packing.py` or state the copy size and the per-method alignment-test burden.
- The mandatory pre-training alignment gate (`train_causal_share.py:1037-1038`; `run.py:286-287`, exit 2) depends on the two row-by-row reference trainers (`train_causal_share.py:691-694,780-781`) the plan drops; until the deferred test exists, the gate leaves the run path. `train_causal_callgen.build()`, `CALL_SEP`, `MAX_TGT_TOK`, `param_prompt_tail`/`param_target`, `eval_gen` (`train_causal_share.py:1031,1092-1093,1243-1244,1267`) also live in the dropped files and need a named destination (`probe_models/qwen.py` and the method files).

### F6 (claim ambiguous against code). Records are per-task files today, not one appended jsonl
- `envs/collect/run_appworld.py:74-82`: one `appworld_<tid>[_r<k>].jsonl` per trajectory; resume = file exists and contains a `final` row. `live_appworld.py:34,731`: one `live_{tid}.jsonl` per task, six row types (meta/gen/spec/resume/env/final, lines 295-834). "Records are jsonl, appended one task at a time by many pieces" reads as one shared file with many writers; no lock is named for it (only `runs.jsonl.lock`), and the resume rule would change from "file exists" to "row exists". The plan should say which layout `task_record.py` writes.

### F7 (real needs with no home). Each is a forgotten need or an unstated drop
- `ops/sampler.py` (806 lines) + `ops/verdicts.py`: resident sampler, six-way verdicts, web page, incident-agent spawn, service-piece throughput parsing, `monitor/{latest,state}.json`, `history/<job>.jsonl`, `incidents.jsonl`. The plan's `jobs/registry.py` names only heartbeat and ls/where/find/kill. CONTEXT.md terms Sampler / Verdict / Escalation line / Incident agent / Refire all rest on these.
- Offline replay line: `replay_inject.py` (1,521 lines), `sweep_theta.py`, `launch_plan_sweep.py`, `splice_replay.py`, `extract_completed.py`, `acceptance.py`, `build_form_table.py`, the plan/cache half of `exec_calls.py`, recipes `splice-wrapup`/`splice-score`. METHOD.md:195 lists offline injection as a current implementation; the plan's `inject.yaml` is live only.
- Readonly axis: `readonly_map.py`, `annotate/readonly/gen_tables.py`, `--readonly-env` in every trainer and eval (`train_causal_tool.py:391-393`). METHOD.md:176-179 marks it [Idea, undecided]; no np821/p1 run wrote READONLY.json. A defensible drop; say it.
- `ident3_gate.py` / `ident3_score.py`: the pre-launch identity gate that protects the same-setup rule; candidate for `service.py --check`.
- `pipeline/driver.py` (1,615 lines): the resumable 15-step walk with gates G1-G22 and the `awaiting_decision` stop (exit 4). The reuse/continue rule folds into run.py; the decision stop has no expression.
- `demo/prepare.py` + `demo-train`: the CPU tiny-Qwen path. `--debug` "never a model", so no CPU trainer path until tests exist.
- Non-AppWorld environments (collect-alf/tales/tau2/toolhop/bfcl, four `gen_*_splits.py`, `build-dataset-legacy`, `serve-mirrorapi`, `stb-virtual-server`) and the mbert line (`train_mbert_tool/extract`, `eval_mbert_call`, `input_modes`, `param_label`, `ann-params`; paused since 2026-08-21 per `run.py:90-95`).
- `check_bundle.py`, `learn/vllm/build_artifact.py`, `learn/vllm/build_token_walk.py` (registered in run.py ops stage), and `tests/` (34 tracked files today, 0 in the plan).
- Cross-run inputs with no named place: `REPLAY_REPORT.json` (T + chosen_theta) is read by `probe_server.py:118-119`, `eval_causal_call.py:536`, `eval_causal_param.py:365`; the plan's `inject.yaml` has no field naming the ctool run whose T it uses (θ is manual per CONTEXT.md). `tool_vocab.json`/`label_map.json` (`build.py:405`, `train_causal_tool.py:524`) need a stated home (example format or train run meta).

### F8 (claim partly holds). Model-table row vs configs/presets
- `configs/presets/default.json` bundles model alias + server section + client section; `run_id` carries the preset name (configs/README rule 3). Splitting server into `table.yaml` and client into settings is consistent, with two exceptions: `reasoning_effort` and `start_date` are client keys today (sweepable: `sweep_preset.py:31`), while the plan puts "the model's own system message (date, effort)" in `gptoss.py`. `start_date` must also equal the server pin `VLLM_SYSTEM_START_DATE` (`ident3_gate.py:6-11`; `run.py:579`). The plan should say date and effort are setting fields passed into `gptoss.py`, and that the date pin appears in both the table row (server env) and the setting.

### F9 (claim partly holds). Standard-library clients
- Live client holds: `live_appworld.py:68-69,199-205` (urllib streaming with `return_token_ids`, seed at 259-260), probe client 276-283. The collector's chat/raw paths use the openai SDK (`envs/collect/common.py:13,62,189,213`); only its harmony path is urllib (250-254). The chat baseline (CONTEXT.md: server-side template, one request per step) therefore either gets rewritten on urllib against the chat endpoint or is dropped from `baseline.yaml`; the plan should say which.

## 3. Fold-in table

Legend: -> planned file; NO HOME; DROPPED (stated) / DROPPED (unstated).

Root
- `run.py` -> `run.py` (subcommands; TASKS/RECIPES/CELLS/EVAL_CELLS replaced by settings + schema stage table; the EVAL_CELLS dependency has no field, F2)
- `model_registry.py` -> `models/__init__.py` + `constants/path_models.yaml`
- `preset_loader.py` -> `experimental_settings/schema.py` loader (client keys) + `models/table.yaml` (server section)
- `serve_preset.py` -> `models/agent_models/service.py` (main half; already stdlib-only, lines 18-26)
- `sweep_preset.py` -> DROPPED (stated: sweep keyword)
- `configs/models.json` -> `constants/path_models.yaml` + `models/table.yaml`
- `configs/presets/*.json` -> server -> `table.yaml`; client -> named settings in `experimental_settings/*.yaml` (F8)

ops/
- `gpu_jobs.py` -> `jobs/registry.py` (ls/free/kill; `free` shells to `.claude/skills/gpu-run/scripts/gpu_status.sh`, line 31-33) + `jobs/launch.py`
- `heartbeat.py` -> `jobs/registry.py`
- `launch_cmd.py` -> `jobs/launch.py` + `run.py`
- `launch_common.py` -> `jobs/launch.py`
- `launch_probe.py` -> `jobs/launch.py` + several settings on one `run.py` call
- `launch_eval.py` -> `jobs/launch.py`; its tool-before-call dependency check: NO HOME (F2)
- `record.py` -> `jobs/registry.py` (runs.jsonl, RESULTS.md)
- `runmeta.py` -> `jobs/registry.py` (meta.json)
- `sampler.py` -> NO HOME (F7)
- `verdicts.py` -> NO HOME (F7)
- (`ops/jobs.json` -> runs.jsonl rows; `ops/gpu_state.md` -> skill reference, stated; `ops/env_locks/` -> `external/`)

pipeline/annotate/
- `rules.py` -> `data/probe_input.py` (SENT_RE, boundaries, clip, assemble, MIN_THINK, MAX_BOUNDS) + `data/environments/appworld.py` (AW_CALL, split_args, first_call_named); ALF/BFCL templates DROPPED (unstated)
- `build.py` -> `data/build_dataset.py`
- `param_label.py` -> DROPPED (unstated, mext)
- `check_callstr.py` -> `data/build_dataset.py` gates (parse through the environment object)
- `accept_v3diff.py` -> DROPPED (unstated; hard-coded paths to deleted data)
- `readonly/gen_tables.py` -> NO HOME (readonly axis, F7)

pipeline/collect/
- `gen_launch.py` -> `jobs/launch.py` pieces + agent service main
- `gen_alfworld_splits.py`, `gen_bfcl_splits.py`, `gen_tau2_splits.py`, `gen_toolhop_splits.py` -> DROPPED (unstated, with the environments)
- `pipeline/driver.py` -> `run.py` stage walk (reuse/continue); gates partly -> `build_dataset.py`; `awaiting_decision` stop: NO HOME

pipeline/train/
- `train_causal_tool.py` -> `train/methods/ctool.py` + `train/utils/trainer.py` (align gate, LoRA, checkpoints) + `probe_models/base.py` (`CausalProbe`, imported by `eval_tool.py:85`, `probe_server.py:100`)
- `train_causal_share.py` -> `train/methods/cgen.py` + `train/methods/cparam.py` (two copies, F5) + `trainer.py`
- `share_data.py` -> packing copied into `cgen.py`/`cparam.py`; `read_position` -> `data/probe_input.py`; `n_full_tokens`/`event_full_texts` -> columns in `data/example.py` (F1)
- `train_causal_callgen.py`, `train_causal_param.py` -> DROPPED (stated as reference.py) but `build()`, `CALL_SEP`, `MAX_TGT_TOK`, `param_prompt_tail`/`param_target`, `eval_gen`, `collate`/`inst_ce` need named destinations (F5)
- `lora_util.py` -> `train/utils/trainer.py` + `probe_models/qwen.py` (TARGET_MODULES)
- `input_modes.py` -> DROPPED (unstated; only `train_mbert_tool.py` imports it)
- `readonly_map.py` -> NO HOME (F7)
- `sweep_lr.py` -> sweep keyword + `eval/method_table.py`
- `train_mbert_tool.py`, `train_mbert_extract.py` -> DROPPED (unstated, mbert line)

pipeline/eval/
- `eval_tool.py` -> `score_causal` (116-198) -> `trainer.py` last step; `fit_temperature`/`replay`/`agg`/`economics`/`bootstrap` -> `eval/utils/probe_eval.py` + `eval/methods/ctool.py` (F1)
- `eval_causal_call.py` -> `eval/methods/cgen.py` (parse via environment) + trigger-row generation -> trainer last step (F2); `self_fire` block: NO HOME
- `eval_causal_param.py` -> `eval/methods/cparam.py` (pred_tool, F2)
- `eval_mbert_call.py` -> DROPPED (unstated, mext)
- `summarize_matrix.py` -> `eval/method_table.py`

pipeline/inject/
- `inject_format.py` -> `agent/inject_format.py`
- `live_appworld.py` -> `agent/loop.py` + `agent/generate.py` (`Stream`, 190-250) + `agent/inject.py` + probe client in `probe_models/service.py` + `data/task_record.py`
- `probe_server.py` -> `probe_models/service.py` (score/gen/encode/decode); `/render` -> F4
- `harmony_render.py` -> `agent_models/gptoss.py` (F4)
- `rebuild.py` -> `gptoss.py` (SYSTEM message, self-check) + `task_record.py` (rebuild conversation); `build_prefix` jinja path DROPPED with replay (unstated)
- `exec_calls.py` -> `environments/appworld.py` `speculate` (save_state/execute/load_state/refreeze, requote, `error_kind`); plan/cache half -> NO HOME (replay line)
- `parse_call.py` -> `environments/appworld.py` (`complete_call`)
- `score_live.py` -> `eval/score_run.py`
- `replay_inject.py`, `sweep_theta.py`, `launch_plan_sweep.py`, `splice_replay.py`, `extract_completed.py`, `acceptance.py`, `build_form_table.py` -> NO HOME (offline replay line, F7)
- `check_bundle.py` -> NO HOME (or a test)
- `ident3_gate.py` -> NO HOME (candidate: `service.py --check`); `ident3_score.py` -> NO HOME
- `test_stopfix.py` -> `tests/` (deferred)

Outside the three code dirs but registered in run.py
- `demo/prepare.py` -> NO HOME (F7); `learn/vllm/build_artifact.py`, `learn/vllm/build_token_walk.py` -> NO HOME
- `envs/collect/run_appworld.py` + `common.py` -> `agent/loop.py` + `generate.py` + agent client (F9); `run_alfworld/tales/tau2.py`, `bfcl_gptoss/`, `build_dataset.py`, `extract_probe_cases.py`, `score_probe.py`, `summarize_full.py` -> DROPPED (unstated) except `summarize_full` -> `eval/score_run.py`; `envs/serve_logs/*` (20 .py, 8 .sh) -> agent service main / DROPPED (unstated)

File count: "about 60" holds — 61 under pipeline+ops+root; plus demo/learn 3, tests 34, envs/collect 11, envs/serve_logs 28.

## 4. Claim table

| Claim | Status | Deciding evidence |
|---|---|---|
| eval/ runs with no torch and no GPU | does not hold today; feasible only with the logits vector in the prediction row and a numpy/pure-Python T fit | `eval_tool.py:40-41,76` torch+transformers at top; `213-224` torch LBFGS; `506,522` softmax; bootstrap `279-296` pure Python; scipy only in mbert-env; system python has no numpy |
| probe client and vLLM client standard library only | holds for the live path; does not hold for the collector's chat/raw paths | `live_appworld.py:68-69,199-205,276-283` urllib; `envs/collect/common.py:13,62,189,213` openai SDK, `250-254` urllib (harmony) |
| the two service.py files import as any with heavy imports inside functions | does not hold today for the probe side; feasible; the render endpoint's venv is undecided (F4) | `probe_server.py:68-69,77-78` torch/transformers/openai_harmony at module top; `serve_preset.py:18-26` stdlib-only already |
| packed loss per method in one file without shared packing | holds mechanically; duplicates ~1,000 lines for ~35 method-specific lines; ctool does not pack | `share_data.py:215-340` (specific) vs `362-582` (shared); `train_causal_share.py:140-930`; `train_causal_tool.py:142-176` |
| GPU prediction run is the last step of train, eval reads only prediction rows | does not hold: trigger-row generation, `pred_tool`, T fit, `self_fire`, `--overlong`, `token_cost` all act on the model or another run's outputs | `eval_causal_call.py:11-13,243,413-489,536-549`; `eval_causal_param.py:14-20,93-112,435`; `eval_tool.py:200-224,447-454`; n_events_test 8,533 vs 391,893 test rows |
| table-row fields expanded into the setting before keying, consistent with configs today | holds except `reasoning_effort` and `start_date`, which are client (run) keys today and a server pin | `configs/presets/default.json` client block; `sweep_preset.py:31`; `ident3_gate.py:6-11`; `run.py:579` |
| records jsonl appended by many pieces; examples and predictions parquet; three formats cover the disk | partly: records are per-task files today (F6); logits are torch tensors (`eval_tool.py:477-490`); fourth kinds exist: REPLAY_REPORT T/θ read cross-run, tool_vocab/label_map, params/, jobs.json pieces, monitor files, RUNMETA/ALIGN_CHECK/train_log, replay plan/raw/exec cache | `run_appworld.py:74-82`; `live_appworld.py:34,731`; `probe_server.py:118-119`; `build.py:405`; `sampler.py:4-6` |
| Polars installed / installable in the three venvs | does not hold (installed nowhere); installable unknown, not attempted; OmegaConf likewise; PyYAML present everywhere | import checks in cprobe-env, mbert-env, envs/appworld/venv, envs/vllm-env, /usr/bin/python3 |

## 5. run.py registry mapped to the three workflow files

- `baseline.yaml` (sample, score): `collect-aw` (harmony path only, F9), `score-live`, `summarize-full`.
- `train_probe.yaml` (sample, build, train, eval): `ann-build`, `ann-check-callstr`, recipe `annotate-chain` (build); `train-ctool`, `train-cgen`, `train-cparam` (train); `eval-tool-causal`, `eval-ccall`, `eval-cparam` (eval; the ctool->cgen/cparam dependency of EVAL_CELLS has no field, F2); `matrix` -> `method_table.py`; `sweep-lr`, `preset-sweep` -> sweep keyword.
- `inject.yaml` (inject, score): `live-appworld`, `probe-serve`, `live-arm-job` (pieces), `score-live`; `serve-preset`, `serve-splice`, `serve-awdiag` -> agent service main; `accept-vllm-qwen/tools/gptoss` -> service `--check`.
- run.py subcommands: `gpu-jobs` -> ls/free/kill; `record`, `runmeta` -> registry; `launch-probe`, `launch-eval` -> `jobs/launch.py` + several settings on one call; `pipeline` (driver) -> the stage walk.
- No expression in the three workflow files: `collect-alf`, `collect-tales`, `collect-tau2`, `toolhop-official`, `collect-bfcl`, `gen-launch` (only its pieces), `gen-alf-splits`, `gen-bfcl-splits`, `gen-tau2-splits`, `gen-toolhop-splits`, `build-dataset-legacy`, `ann-params`, `ann-accept-v3diff`, `readonly-gen-tables`, `train-mtool`, `train-mext`, `train-cgen-rows`, `train-cparam-rows`, `demo-prep`, `demo-train`, `eval-tool-mbert`, `eval-mcall`, `inject-plan`, `inject-run`, `inject-merge-exec`, `inject-score`, `extract-completed`, `exec-calls` (as a task; its mechanism folds into `speculate`), `acceptance`, `sweep-run`, `sweep-curve`, `build-form-table`, `check-bundle-mbert`, `check-bundle-causal`, `parse-call-selftest`, `splice-replay-events/run/score`, `launch-plan-sweep`, `probe-selftest`, `ident3-job`, `ident3-gate`, `ident3-score`, `serve-mirrorapi`, `stb-virtual-server`, `splice-plan-job`, `launch-splice-clients`, `sampler`, `build-lesson-artifact`, `build-token-walk`; recipes `splice-wrapup`, `splice-score`, `engine-smoke`; CELLS `mtool`, `mext`.

Files not readable in this pass: none refused; `pipeline/inject/test_stopfix.py` and `sweep_theta.py` were read by header only.
