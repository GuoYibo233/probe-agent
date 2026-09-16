# Review of the "tree from zero" proposal (new1, HEAD 145992b)

Written by a read-only Fable 5.1 evaluator at gyb's request on 2026-09-13.
Input: the proposed tree saved with the renewal job
(`~/.claude/jobs/e41690a9/tmp/tree-from-zero.md`; the same tree as in the
chat of 2026-09-13) and the fifth-draft spec
`plans/2026-09-13-renewal-design.md`. The principle under test: each file
does one clear thing, each folder answers one question of the pipeline.
The report is reproduced verbatim below; the three insisted changes were
spot-checked by the main session against the cited lines and hold.

---

Read-only review. Every claim below cites a file I read; the uncommitted edit in `pipeline/train/train_causal_share.py` (a CUDA-only device check at lines 1010-1011 plus whitespace, per `git diff`) is ignored. I did not read `plans/archive/`.

## 1. Verdict

The folder cut (root registry, `agent/`, `dataset/`, `train/`, `eval/`, `jobs/`) is right and each folder answers one question. Three merges break the principle or a venv boundary and I would insist on changing them:

1. `harmony.py` must not absorb `rebuild.py` and `ident3_gate.py`: `harmony_render.py` imports `openai_harmony` at module top (`pipeline/inject/harmony_render.py:34-37`), the AppWorld venv cannot install it (`envs/collect/common.py:15-20`, `ops/env_locks/appworld.txt:52` pins pydantic 1.10.26), and the live driver imports `rebuild` inside that venv (`pipeline/inject/live_appworld.py:76`, uses `R.SYSTEM` 393, `R.check_system_verbatim` 691, `R.NO_CODE_MSG` 808). The AppWorld message convention belongs in a stdlib module in `agent/`; the render-equals-server check belongs in `serve.py`'s check table.
2. The train/ dependency must be reversed: the "reference only" row-wise modules are today the production source of the model builder, the generative eval, and eight constants (`pipeline/train/train_causal_share.py:1009,1012,1029-1032,1092-1093,1243-1244,1267`; `share_data.py:221-222,286,293-294,340`; `demo/prepare.py:247,266,307`). Move those into `share_data.py`/`trainer_base.py` and make `rowwise_*.py` import them, or "kept as proof" is not true.
3. `rules.py` must not absorb `param_label.py` (a 345-line program with its own `main`, file outputs and two reports, `pipeline/annotate/param_label.py:171-341`, while `rules.py:10-11` declares "reads and writes no files"). Separately, the call parser has four copies and should have one home in `dataset/rules.py` so `check_callstr.py` stops importing torch through `eval_causal_call` (`pipeline/annotate/check_callstr.py:313`, `run.py:234-239`).

## 2. Facts that constrain the layout (read from the code)

**Venvs and what each may import at module top.**
- AppWorld venv: appworld 0.1.3, openai 2.49.0, pydantic 1.10.26; no torch, transformers or openai_harmony (`ops/env_locks/appworld.txt:3,38,52`). Runs `run_appworld.py`, `live_appworld.py`, `exec_calls.py` (`run.py:67,124-126,457-461,519-521`).
- cprobe-env: torch 2.11, transformers 5.14.1, openai-harmony 0.0.8, pydantic 2.13.4; no `openai` package (`ops/env_locks/cprobe-env.txt:52,58,72,74`; no `openai==` line). Runs the trainers, evals, `probe_server.py`, `score_live.py`, `check_callstr.py` (`run.py:234-239,530-544`).
- vllm-env: vllm 0.26.0 plus openai-harmony (`ops/env_locks/vllm.txt:111,188`); only `tests/test_harmony_render.py` needs it (`tests/test_harmony_render.py:7-8,25-29`).
- system python3: `ident3_gate.py` (`run.py:562-563`; called as `python3` in `envs/serve_logs/ident3_job.sh:21`), the ops scripts, `build.py`, `param_label.py`, `summarize_matrix.py` (`run.py:222-229,425-426,641-693`).

**Modules that are stdlib-only today because two venvs import them:** `ops/heartbeat.py:9`; `pipeline/inject/inject_format.py:1-3`; `pipeline/inject/parse_call.py:11-12`; `pipeline/inject/rebuild.py:47-49` (imported by the live driver in the AppWorld venv and by `probe_server.py:78` in cprobe-env); `pipeline/annotate/rules.py:15` (imported by `live_appworld.py:77` and `exec_calls.py:128` in the AppWorld venv, by `build.py:44`, `param_label.py:33`, `check_callstr.py:89`, `eval_causal_call.py:80`, `eval_causal_param.py:74`, `share_data.py:51`, `demo/prepare.py:47`, `pipeline/driver.py:176`); `pipeline/train/readonly_map.py:9-10`; `preset_loader.py:1-2`.

**The live driver never renders harmony itself.** It asks the probe service for the prefix ids (`live_appworld.py:787-789`), decode (491, 562), encode (508), score and gen (482, 500). `harmony_render.py` has exactly one production importer, `probe_server.py:77`; the proposal's importer list ("by rebuild.py, live_appworld.py") is wrong: `rebuild.py:47-49` and `live_appworld.py:76-81` import neither `harmony_render` nor `openai_harmony`.

**Copies of one fact that the proposal inherits unchanged:**
- The AppWorld system prompt: `envs/collect/run_appworld.py:24-43` and `pipeline/inject/rebuild.py:52-71`, kept equal by a regex over the source file at runtime (`rebuild.py:92-93,109-119`).
- The call-start regex: `rules.py:67`, `parse_call.py:22` (comment says "must stay in sync"), `score_live.py:54`.
- The argument splitter: `rules.split_args_named` (118-149) and `eval_causal_call.split_named_raw` (134-169) plus a verbatim copy in `eval_causal_param.py:128-165`; `parse_call` asserts equality on every call (`eval_causal_call.py:200-201`).
- The ctool bundle loader (backbone from `best/`, head.pt, tokenizer): `eval_tool.load_causal` (81-91), `probe_server.load_ctool` (98-119), `check_bundle.CausalBundle` (128-171); the class itself is `train_causal_tool.CausalProbe` (191-208), which `check_bundle.py` loads by file path with importlib (43, 80-94).
- The greedy call generation contract (prompt + sep, greedy, cut at first newline, strip): `probe_server.gen` (180-193), `eval_causal_call.generate` (231-253), `eval_causal_param.generate` (225), `train_causal_callgen.eval_gen` (339) which the fast trainer calls (`train_causal_share.py:1243-1244`).
- `APPWORLD_HOME`: `run_appworld.py:149`, `live_appworld.py:83`, `exec_calls.py:131`.
- The backbone path table: `train_causal_tool.py:84-88`, `train_causal_callgen.py:95-99`, `train_causal_param.py:83-87`, plus `configs/models.json`, `gen_launch.py:60-67`, `rules.MODEL_OF` (23).
- `LEDGER_PATHS` and git probing: `run.py:795-805`, `ops/record.py:54-81`, `ops/runmeta.py:28-52` (the comment at `run.py:790-794` says "syncing all three places"); `record.py` stores a short HEAD, `runmeta.py` the full one.
- The monitor directory and the job-ledger reader: `ops/gpu_jobs.py:39-41,50-54` and `ops/sampler.py:33-46,49-51`.
- The date pinned into the gpt-oss prompt: the live line uses `COLLECT_DATE = "2026-07-31"` (`rebuild.py:90`, read by `probe_server.py:204,225`, `ident3_gate.py:81,91`, and pinned server-side by `envs/serve_logs/launch_vllm_splice.py:32,60`; the `fmt_smoke_srv` command in `ops/runs.jsonl:204` carries `VLLM_SYSTEM_START_DATE=2026-07-31`); the sampler uses `start_date` 2026-08-06 (`common.py:60,297`, `configs/presets/default.json:23`). `serve_preset.py:32-56` sets no date at all. Two constants for the same field, in two files, with different values. I report this as a fact only.

**Reference modules are production dependencies.** `train_causal_share.py` takes `FULL_LR` (1009), `SEED` (336, 1012), `MODELS` and `build` (1029-1032), `MAX_TGT_TOK` (1092-1093), `eval_gen` (1243-1244), `CALL_SEP` (1267) from `train_causal_callgen`/`train_causal_param`; the alignment check legitimately uses their `collate`, `inst_ce`, `CallDS`, `ParamDS` (691-694, 780-781). `share_data.py` takes `SEED`, `MAX_TGT_TOK`, `CALL_SEP`, `param_prompt_tail`, `param_target`, `ASSEMBLY_MISMATCH_LIMIT` (221-222, 286, 293-294, 340). `demo/prepare.py` takes `build`, `SEED`, `MODELS` (247, 266, 307). The fourteen shared names are `MODELS SEED FULL_LR CALL_SEP MAX_TGT_TOK MAX_GEN_TOK GEN_N _TV collate build inst_ce eval_ce eval_gen main` (def lists of `train_causal_callgen.py:73-367` and `train_causal_param.py:63-282`); `build` has different signatures (`callgen.py:240` vs `param.py:198`).

**`params/` has one consumer family.** `param_label.py` writes `params/{train,val,test}.jsonl` (7-9, 212). Readers: `train_causal_callgen.fire_pmap` under `--fire-head` (110-116, 418, 442-444) and `eval_causal_call.load_ready` under `--self-fire` (262-297, 528). The fast trainer reads `label_call` only (`share_data.py:285-300`) and has no fire head (`train_causal_param.py:41-42`, `run.py:310`). No module imports `param_label`; it is a registry task (`run.py:226-229`), a recipe step (751-759) and a chain artifact (`driver.py:80-81,1244`). The proposal's importer list for `param_label.py` and `check_callstr.py` ("by build.py, rules.py, driver.py") is wrong: those are mentions in comments (`build.py:53-54,458`) and subprocess calls (`driver.py:1195,1245`), not imports.

**The chain driver is a subprocess orchestrator with per-step artifact knowledge.** `pipeline/driver.py` calls `run.py` tasks (70, 892, 1195, 1245), imports `run.git_dirty` (65) and `launch_common.probe_free/local_host` (68), keeps its own ssh `has_session` deliberately different from `launch_common`'s (100-116, docstring 47-49), and holds the artifact lists of every step (76-83) with 15 steps (1506-1537). Its test is 1337 lines (`tests/test_driver.py`).

**`probe_server.py` carries a second, dead check path.** `selftest` (280-343) reads `pipeline/data/aw_official_v1/gptoss` (299) and the deleted replay line's `plan.jsonl` (308); the default run paths point at probes deleted on 08-02 (83-84, 146-147).

**verify/ is seven files, not five**, 1537 lines (`wc`); `packed_common.py` is shared by three of them, `sweep_watch.py` imports `smoke_check.py` (37), `enum_blocks.py` uses a cwd-relative `sys.path.insert(0, "pipeline/train")` (13). One ledger row cites a verify script (`ops/runs.jsonl:116-117`, rendered at `RESULTS.md:53,554-562`); `cpu_equiv_check`/`mem_probe` have no ledger row (their numbers sit in `equiv_result.json`/`mem_probe.json` inside the folder).

## 3. Per-folder assessment (interpretation)

**Root: `run.py` + `registry.py`.** Tables plus settings loader in one stdlib file is acceptable because the loader validates settings against the tables (spec 4.2) and both are read by every venv. Two conditions. First, git probing and `gate_dirty` must leave `run.py`: today `ops/launch_cmd.py:49`, `launch_probe.py:42`, `launch_eval.py:49` and `driver.py:65` all import from `run`, which only works because `run.py:1289-1292` imports `launch_cmd` lazily. In the new tree `jobs/launch.py` should import `registry` and `ledger`, never `run`. Second, `model_registry.resolve` checks NFS existence at call time and reads the JSON at import (`model_registry.py:15-18,27`); in `registry.py` that check belongs to `selfcheck`, not to import.

**`settings/`.** Fine. `settings/inject/` should stay its own kind even though the code folder is shared: a settings kind is a step, i.e. a STEPS row, a run-id namespace and an output root, and the inject step has fields no sample setting has (`probe`, `theta`, `format`, `pieces`; spec 4.5) and a different root (`pipeline/inject/runs`, spec 4.3). Folders follow programs; kinds follow steps. One driver serving two kinds is exactly the owner's decision.

**`agent/`.** One question ("what runs while the agent model runs a task") and both servers belong: `serve.py` starts the agent model, `probe_server.py` is the process the probe attaches through. Three corrections. (a) `harmony.py` = renderer only (see verdict 1); the AppWorld message convention (SYSTEM, `NO_CODE_MSG`, turn templates, `load_traj`/`build_messages`, `load_steps`) becomes a stdlib module, and `run_appworld.py` imports SYSTEM from it instead of owning a copy, which deletes `check_system_verbatim` and the `_SRC` path literal. (b) The proposal puts "the stream half of live_appworld" into `chat.py`; that half is `gen_step` (`live_appworld.py:411-569`), which does cut detection, `/score` and `/gen` calls, token-boundary search (`find_head` 340-376), the speculate call (502), splice (503-511) and the spec/resume records (515-533). That is the probe hook, not a request row; in `chat.py` the file does two things. Give it its own file. (c) `agent/` will hold two cprobe-env files (`harmony.py`, `probe_server.py`) among AppWorld-venv files; that is already the case in `pipeline/inject/` and is fine if the README says so. Keeping a separate `inject/` folder for the probe side (fifth draft) is not needed.

**`dataset/`.** One question, four files, but `rules.py` + `param_label.py` fails the principle (verdict 3). `readonly/` absorbing `readonly_map.py` is coherent ("the read-only labels and how they are read"), cheap (8 importers change one `sys.path` literal; `readonly_map.py:22` becomes `Path(__file__).parent`), and only worth doing if open item 3 keeps the feature; if the feature is dropped, delete `readonly/`, `readonly_map.py`, the fire head and `--self-fire`, and `param_label.py` with them, because nothing else reads `params/`. `build.make_call` (197-200) is a rule other code depends on (`train_causal_param.param_target` docstring 105-115; `demo/prepare.py:48`); it belongs in `rules.py`.

**`train/`.** One question. Insist on the dependency reversal (verdict 2). `trainer_base.py` is the right home for the copied blocks (version gate `train_causal_tool.py:65-69`, heartbeat shim 77-80, force guard 380-383, seed 376-377, backbone lookup 84-88,211-222). Merging `lora_util.py` into it is not worth it: `lora_util` is the tuning axis table (spec 4.7), has its own contract test (`tests/test_lora_merge.py:1-35`), keeps peft lazy on purpose (`lora_util.py:8-11,85,101`), and `trainer_base` already lists six responsibilities; a spine that also holds an axis table does two things. `demo/` under `train/` is fine (three program paths in `.vscode/launch.json`, `NET_DEMO` in `demo/prepare.py:53` stays because NFS does not move, two `.gitignore` bare names). One new file is warranted: the probe model and its loaders (`CausalProbe`, `load_ctool`, `load_cgen`, the greedy call generation) exist in three to four copies across train, eval and the probe service; one `train/probe_model.py` makes `train_tool.py`, `eval_tool.py`, `probe_server.py` and `--check` share it by construction.

**`eval/`.** `score_live.py` belongs here: eval/ then answers "how is anything scored", and the scorer's baseline pairing must be rewritten anyway (it pairs by `appworld_{tid}.jsonl`, `score_live.py:133`, while multi-seed sampling names files `appworld_{tid}_r{k}`, `run_appworld.py:75`). `figures/` can sit under `eval/`; I would put it at the root because a figure reads the ledger and reports of several steps, not eval code. `matrix.py` should read `registry.METHODS` and stop carrying its own cell table (`summarize_matrix.py:24-27`).

**`jobs/`.** The name is fine (`jobs.json`, `run.py gpu-jobs` already use the word). `chain.py` does not belong here: it orchestrates steps (walks `source` upward, runs `run.py <step>`, prints launch commands, spec 4.11) and today knows every step's artifacts (`driver.py:76-83`). It is the front door's helper; put it at the root next to `run.py` as the fifth draft did, and move the per-step artifact knowledge into `registry.STEPS` so it shrinks. Inside `jobs/`, the cut between `launch.py`, `monitor.py` and `ledger.py` should follow write/read: `ledger.py` = the three registrations (RUNMETA, `jobs.json`, `runs.jsonl`) including the `jobs.json` CRUD now in `gpu_jobs.py:50-73,390-486` and `register_all` (`launch_common.py:91-163`); `monitor.py` = sampler + verdicts + terminal table + web page, read-only (`sampler.py:2-8`, `gpu_jobs.py:180-347`); `launch.py` = card probe, tmux, refire, and `free` (`gpu_jobs.py:386-387` execs the skill's `gpu_status.sh`, path at 30-32). The incident half of the sampler (`sampler.py:177-300`) is deleted per spec section 6.

## 4. Per-file table

| Proposed file | The one thing it does after the merges | Evidence read | Advice |
|---|---|---|---|
| `run.py` | front door: dispatch step/launch/chain/find/where/note/selfcheck | `run.py:1270-1306`; tables 63-110, 122-710 | keep; move tables to registry, git probing to ledger |
| `registry.py` | STEPS/METHODS/interpreter tables and the settings loader that validates against them | `preset_loader.py:78-132`, `model_registry.py:15-28`, `run.py:63-110` | keep; stdlib only; no NFS existence check at import |
| `agent/run_appworld.py` | the AppWorld adapter: task loop writing meta/gen/env/final, world primitives (save, execute, restore, requote, error_kind) | `run_appworld.py:176-241`; `live_appworld.py:305-321,759-838`; `exec_calls.py:137-303,308-324` | keep; import SYSTEM and turn templates from `messages.py`; one `APPWORLD_HOME` |
| `agent/chat.py` | the request rows chat / harmony(stream) / raw | `common.py:40-272`; `live_appworld.py:190-249` | split: the probe hook (`gen_step` 411-569) goes to `probe_hook.py`; make the `openai` import lazy (13) so cprobe-env processes can import the module |
| `agent/harmony.py` | gpt-oss messages -> prompt token ids as vLLM renders them | `harmony_render.py:34-140`; importer `probe_server.py:77` | rename only; do not absorb `rebuild.py`/`ident3_gate.py` (venv break, two things) |
| `agent/inject_format.py` | the injection-format axis table | `inject_format.py:40-78`; tests `test_inject_format.py:13`, `test_inject_tail_ids.py:20` | keep |
| `agent/serve.py` | start the agent model's vLLM server for a settings file and run its acceptance checks | `serve_preset.py:32-78`; `ident3_gate.py:44-92` | keep; add the render-equals-server check as one check-table entry; the date pin comes from the generation file, not a constant |
| `agent/probe_server.py` | the probe service over HTTP (score, gen, render, encode, decode, health) plus `--check` | `probe_server.py:136-277`; `check_bundle.py:128-171,176-263` | keep; delete `selftest` (280-343, dead paths); loaders come from `train/probe_model.py`; defaults become required (83-85) |
| `dataset/build.py` | trajectories -> train/val/test examples and reports | `build.py:323-540` | keep; move `make_call` (197-200) to rules |
| `dataset/rules.py` | how an AppWorld trajectory's text is read: cut points, prompt assembly, call syntax and argument splitting, call extraction | `rules.py:17-178`; `eval_causal_call.py:129-202`; `parse_call.py:27-100` | keep pure and stdlib; absorb the eval parser and `complete_call`, not `param_label.py` |
| `dataset/check_callstr.py` | the gates on a built dataset | `check_callstr.py:104-437` | keep; import the parser from rules so it runs without torch |
| `dataset/readonly/` (+ loader) | the read-only tool labels and their loader | `readonly_map.py:30-88`; tables listing | keep only if open item 3 keeps the feature |
| `train/trainer_base.py` | what every trainer does the same way: version gate, args, force guard, seed, logging, heartbeat, backbone lookup | copied blocks cited in section 3 | new; also the home of `MODELS`/`SEED`/`FULL_LR` |
| `train/share_data.py` | the packed batches and the instance strings of cgen/cparam | `share_data.py:169-579`; constants imported at 221-222,286,293-294,340 | keep; own `CALL_SEP`, `MAX_TGT_TOK`, `param_prompt_tail`, `param_target`, `ASSEMBLY_MISMATCH_LIMIT`; drop the mbert-env note (3-14) |
| `train/train_tool.py` | trains ctool | `train_causal_tool.py:326-539` | rename; `CausalProbe` moves to `probe_model.py` |
| `train/train_call.py` | trains cgen and cparam with the packed forward pass | `train_causal_share.py:928-1293` | rename; stop importing `build`, `eval_gen`, constants from the row-wise modules |
| `train/rowwise_cgen.py` | the slow row-by-row cgen reference the alignment gate compares against | `train_causal_callgen.py:137-365`; used at `train_causal_share.py:691-694,780-781` | keep as reference only; it must import constants from share_data; decide the fire head (110-134, 400-464) |
| `train/rowwise_cparam.py` | the same for cparam | `train_causal_param.py:125-280` | keep, same condition |
| `train/demo/prepare.py` | build the CPU fixtures for the debugger | `demo/prepare.py:47-73,214-307` | keep; repoint imports and the three program paths |
| `eval/eval_tool.py` | ctool: fit the threshold on val, freeze on test | `eval_tool.py:57-300`; importer `eval_causal_call.py:88` | keep; mbert branch (41) deleted; loader from `probe_model.py` |
| `eval/eval_call.py` | cgen and cparam at the ctool threshold | shared defs `eval_causal_call.py:98-258` vs `eval_causal_param.py:89-257`; call-only 262-490; param-only 296 | merge as spec says; parser from rules; the self-fire block (262-490) only evaluates a probe the production trainer cannot train, decide with the fire head |
| `eval/score_live.py` | a live run -> LIVE_REPORT | `score_live.py:111-216` | keep here; import the call regex and `complete_call` from rules (54, 52); group by seed |
| `eval/matrix.py` | backbone x method table from the reports | `summarize_matrix.py:35-131` | keep; read METHODS from registry (24-27, 81-82) |
| `eval/figures/figlib.py` | style and the ledger-to-table loader | none exists today | new; prefer root `figures/` |
| `jobs/launch.py` | put pieces on cards: probe, tmux, alive check, refire, free | `launch_cmd.py:74-334,359-449`; `launch_common.py:44-88`; `launch_probe.py`, `launch_eval.py` | keep; import registry/ledger, not run; the eval arg-shape branch (`launch_eval.py:154-162`) becomes a METHODS field |
| `jobs/monitor.py` | sample heartbeats, judge pieces, render table and web page | `sampler.py:2-8,527-776`; `verdicts.py`; `gpu_jobs.py:180-347` | keep; read-only; incident half (177-300) deleted |
| `jobs/heartbeat.py` | the progress protocol | `heartbeat.py:19-47` | keep, stdlib |
| `jobs/ledger.py` | the three registrations and their files: RUNMETA, jobs.json, runs.jsonl, RESULTS render; one git probe; one `LEDGER_PATHS` | `record.py:58-215`; `runmeta.py:32-84`; `gpu_jobs.py:50-73,390-486`; `launch_common.py:91-163` | keep; absorb jobs.json CRUD and `register_all` |
| `jobs/chain.py` | run the upstream steps a setting needs | `driver.py:1506-1615`; subprocess calls 892,1195,1245 | move to root; artifact knowledge into `registry.STEPS` |

Files the proposal does not list but that the merges leave with no home: `exec_calls.load_steps` and `rebuild.load_traj/build_messages` (trajectory reading), `run_appworld.SYSTEM`/`rebuild.SYSTEM` (one copy needed by the driver, the server check and, today, the probe server), and the probe hook. These are the two added files in section 6.

## 5. Merge and deletion risks

| Merge / deletion | What breaks | Cost | Worth it |
|---|---|---|---|
| world primitives into `run_appworld.py` | `requote` needs `rules.AW_CALL/first_call_named` (`exec_calls.py:128,195-199`): a cross-folder import agent -> dataset in the AppWorld venv; fine while rules stays stdlib. `selftest_shadow` (`live_appworld.py:841-872`) needs `load_steps` | move of whole functions (161-324 of exec_calls, 305-321 of live) | yes |
| `rebuild.py` + `ident3_gate.py` into `harmony.py` | venv break: the driver imports `rebuild` in the AppWorld venv (`live_appworld.py:76`) and `harmony_render.py:34` needs openai_harmony; interpreter break: `ident3-gate` runs under system python3 (`run.py:562-563`); two things (renderer vs AppWorld conversation vs server check); `rebuild.py:161-256` (jinja path) is dead after section 6 | rewrite: split, not merge | no; do the split of section 6 |
| `check_bundle.py` into `probe_server.py --check` | second consumer: the loader is copied in `eval_tool.load_causal` (81-91) and stays a copy; `check_bundle.py:43,80-94` importlib-by-path and the mbert branch (99-125) die; `probe_server.selftest` (280-343) remains a dead third check unless deleted; tests `test_inject_tail_ids.py:26-27` pin `PS.GPTOSS_TOK`/`encode_ids` | small once `probe_model.py` exists | yes, with the loader in train/ |
| `parse_call.py` into `score_live.py` | name clash of intent: `eval_causal_call.parse_call` is a different parser (172-202) from `parse_call.complete_call` (27-69); regex copy stays (`score_live.py:54`); `run.py:489-491,760-766` selftest task dies with the recipe engine | move of two functions | prefer rules.py as the home; merging into the scorer keeps two parsers alive |
| `lora_util.py` into `trainer_base.py` | `tests/test_lora_merge.py:49` and `test_share_trainer.py:451,497` import the module; peft must stay lazy (`lora_util.py:8-11`); axis table loses its own file | move | not worth it |
| `readonly_map.py` into `dataset/readonly/` | 8 importers change a `sys.path` literal; `_TABLE_DIR` (22) changes; `test_mem_probe_pick.py:37` | trivial | only if open item 3 keeps the feature |
| `param_label.py` into `rules.py` | rules gains a `main`, file IO and reports (`param_label.py:171-341`); rules is imported by the live driver and the probe side, which then carry a program; event extraction duplicated with `build.py:61-117` stays | rewrite | no; keep as `dataset/param_label.py`, or delete with the fire head |
| `record.py` + `runmeta.py` into `ledger.py` | `launch_common.py:155-158` calls `record.py start` as a subprocess to isolate `sys.exit`; other sessions write `ops/runs.jsonl` until phase 6; `run.py:665-675` tasks | move; dedups two git probes and three `LEDGER_PATHS` | yes; also absorb `jobs.json` CRUD |
| `preset_loader` + `model_registry` + run tables into `registry.py` | cycle if `jobs/launch.py` still imports `run` (`launch_cmd.py:49`); `tests/test_preset.py:26-27,63-71,262-271` pin today's names; `common.py:292`, `live_appworld.py:669`, `ident3_gate.py:59` import lazily | rewrite of the loader (already planned, spec phase 3) | yes |
| delete `verify/` | seven files, not five (`wc`); one RESULTS row's command names `gpu_kernel_check.py` (`RESULTS.md:562`); `enum_blocks.py:13` cwd-relative path would break on move anyway | delete | yes; the living proof is `run_align_check` (`train_causal_share.py:748-926`) |
| delete `gen_launch.py` | `driver.py:892` (subprocess), `tests/test_preset.py:187-193`, `tests/test_collect_multisample.py:56`, `build.py:239-241` copies its `STEP_CAP`; regenerating the NFS launcher of the existing sample run (spec phase 2) becomes impossible | delete | yes, once `launch.py` starts servers and clients from a sample setting |
| keep the two row-wise files | today they are production sources (section 2); `tests/test_share_data.py:34-36`, `test_cparam_assembly.py:28-30` import constants from them | move ~8 constants, `build`, `eval_gen`, `param_prompt_tail`, `param_target` into share_data/trainer_base; 12 call sites in `train_causal_share.py`, 6 in `share_data.py`, 4 in `demo/prepare.py` | yes, but only with the reversal |

## 6. Improved tree

Changed lines carry a reason; unchanged lines are as proposed.

```
new1/
  README.md  CLAUDE.md  TRAPS.md
  METHOD.md  DATA.md  WORKPLAN.md  TIMELINE.md  RESULTS.md
  i will manully reviwe these files later

  run.py
  registry.py       tables + settings loader; stdlib; no NFS check at import
  it contains path for datasets, models, and constants

  chain.py          moved from jobs/: it orchestrates steps, not cards; step
                    artifacts come from registry.STEPS
  it is about what a work flow is like, right?, if yes, it should be in settings

  figures/          moved from eval/: figures read the ledger of every step
    figlib.py

  settings/         (as proposed)

  agent/
      agent should only handle the agent structure, it can receive input from dataset, but never run the dataset( dataset here means appworld and things like this )


    run_appworld.py   the adapter: task loop, records, world primitives
    better to call env_appworld.py

    messages.py       NEW, stdlib: the AppWorld message convention (SYSTEM,
                      turn templates, trajectory -> messages, load_steps);
                      replaces rebuild.py's live half and the regex source check
    chat.py           request rows only; lazy openai import
    probe_hook.py     NEW: the probe attached to a streaming step (cuts, /score
                      /gen, head boundary, speculate, splice, spec/resume
                      records; today live_appworld.gen_step 411-569)
    harmony.py        renderer only (openai_harmony; cprobe-env)
    inject_format.py
    serve.py          start the server + check table, including
                      render-equals-server (today ident3_gate)
    probe_server.py   HTTP service + --check; selftest deleted
    files above is still not unclear, for examole, harmony is a specfic thing with gpt, but when we use qwen, there may not be harmony, so and no one knows what harmony is, it should be put into some where else, template setting or sth 


    runs -> NFS   live -> NFS
    why HTTP service here?
    
    how to add the probe is also a question, i think it should be like a switch, if it is on, when generating, the stop condition is related to probe instead of just related to the output token

    and agnet and appworld should be in different folders agnet should only run the agent
    and every file should do one function, that means when i want to edit one thing, i can easily reach it via its name. things now is not very clear


  dataset/
    dataset should deal with dataset and output of runs in dataset, appwolrds should be here



    build.py
    rules.py          + complete_call, the eval-side parse_call, make_call;
                      param_label stays out
    param_label.py    kept as its own program (or deleted with the fire head)
    check_callstr.py  imports the parser from rules; runs without torch
    readonly/         (only if open item 3 keeps the feature)
    data -> NFS

  train/
    trainer_base.py   + MODELS/SEED/FULL_LR (from the three trainer dicts)
    probe_model.py    NEW: CausalProbe, load_ctool, load_cgen, generate_call;
                      one loader for train_tool, eval_tool, probe_server, --check
    what dose this file do?
    share_data.py     + CALL_SEP, MAX_TGT_TOK, param_prompt_tail, param_target
    train_tool.py

    train_call.py
    these tool should be in one file
    rowwise_cgen.py   imports constants from share_data (dependency reversed)
    rowwise_cparam.py
    so as these files

    lora_util.py      kept: the tuning axis table with its own contract test
    demo/
    runs -> NFS

  eval/
    eval_tool.py
    eval_call.py
    score_live.py     imports rules for the call regex and complete_call
    matrix.py         reads registry.METHODS

  jobs/
    launch.py         + free (execs the skill's gpu_status.sh); imports
                      registry and ledger, never run
    monitor.py        sampler + verdicts + table + web; read-only
    heartbeat.py
    ledger.py         + jobs.json CRUD and register_all: the three registrations
    runs.jsonl  jobs.json  gpu_state.md  env_locks/

  envs/  cprobe-env/  logs/  tests/  plans/  docs/agents/  .claude/
```

Count: 31 Python files instead of 28 (three new: `messages.py`, `probe_hook.py`, `probe_model.py`; one moved back: `lora_util.py`; `chain.py` at root; `param_label.py` kept or deleted).
IMPORTANT:
let me give some instruction:
1. one experiment is one config, the center of the whole repo is about how to handle the setting.
- all hyperparameters should be included
- what the workflow is like. for example, use agent to run the experiment is baseline. use probe is probe way, sometimes we just do sample, sometimes we do both sample and training, design a proper way to handle this
- what file type to use depends on you. json? yaml? hydra?
- easy to edit, and its structure is easy to be updated, for example, when i add one more hyperparameter, all previous settings may cointain one more argument, not sure how to handle this
- every code file is responsibe for things in parameter.

2 everytime it runs, we can reproduce.
- if output file with same settings already exists and it is not 增量, skip generation
- easy to reterive the output file with certain settings
- easy to retrive logs, wandb / mlflow or anything you recommned
- still can retrive even code is edites, maybe we should use version number
- eval should use version number, too

i've heard that Hydra + OmegaConf is common, anyway you should find avaliable light and quick models to recommend

3.short and small layers
data
models
train
eval
scripts

they are standard layers, settings contorl the arguments of them

notebooks (for quick run)

other parts (demo, figure....)

4. debug or tiny mode. --debug avaliable: small model, small subset of data, super quick verify

5 NO exterme abstraction, do not use multi almost same files, 科研代码最常见的两种病：一是复制粘贴出五个几乎一样的训练脚本；二是过早抽象成一个万能框架，改一个小点要动六个文件。合理的度是：重复第三次再抽象，抽象只针对已经稳定的东西。

6 Read me is for the future: check whether pepole in the future can quick understand

## 7. Rules that keep files single-purpose, each testable by `run.py selfcheck`

1. Every tracked `.py` declares its interpreter in `registry.py` (a step script through its STEPS/METHODS row, a library through a `SHARED` list with the venvs that import it). Selfcheck runs `<interp> -c "import <module>"` for each file under each declared interpreter and fails on `ImportError`. This is the test that would have caught `harmony.py` absorbing `rebuild.py`.
2. A module on the `SHARED` list (today: heartbeat, registry, rules, inject_format, messages, the parse helpers) imports only the standard library at module top. Selfcheck parses top-level imports with `ast` and checks them against `sys.stdlib_module_names`.
3. One definition per fact: `registry.SINGLE_SOURCE` maps a name to its file (`AW_CALL -> dataset/rules.py`, `SYSTEM -> agent/messages.py`, `LEDGER_PATHS -> jobs/ledger.py`, `APPWORLD_HOME`, the backbone paths, `MONITOR_DIR`). Selfcheck fails when the name is defined by assignment in any other tracked `.py`.
4. No absolute repo or NFS path in code outside `registry.py` and `settings/`. Selfcheck greps tracked `.py` for `/home/y-guo` and `/net/` (today: `run_appworld.py:149`, `live_appworld.py:83`, `exec_calls.py:131`, `gen_launch.py:52-57`, `serve_preset.py:28-29`, `sampler.py:49-51`, `gpu_jobs.py:39-41`, `probe_server.py:85`, the three `MODELS` dicts, `demo/prepare.py:53`).
5. Cross-folder imports are explicit: a module may be imported from another folder only if it is on the `SHARED` list. Selfcheck builds the import graph by bare module name (names are unique across the tree) and fails on any other cross-folder edge. This is what keeps `chat.py` from growing a second consumer that drags `openai` into cprobe-env.

## 8. Questions only the owner can answer

1. Read-only feature (spec open item 3): keep or drop. Dropping removes `readonly/`, `readonly_map.py`, the fire head (`train_causal_callgen.py:110-134,400-464`), `--self-fire` (`eval_causal_call.py:262-490`), and `param_label.py` with its `params/` outputs, since nothing else reads them.
drop


2. Does the fire head survive at all when the production trainer is `train_call.py`, which has none? If not, `rowwise_cgen.py` shrinks and `eval_call.py` loses about 230 lines.

3. The date in the prompt: the live line pins 2026-07-31, the sampler 2026-08-06 (section 2). Which value goes into `settings/generation/temp1_high.json` for the live run, and is a second generation file needed to reproduce the old live runs? This decides whether `COLLECT_DATE` survives anywhere.
4. Is `probe_server.py selftest` (280-343) deleted with the replay line it reads from?
5. Should `chain.py` keep the 15-step gated state machine of `driver.py` (and its 1337-line test), or be rewritten to the "walk `source` upward" form of spec 4.11? The answer changes whether it is a root file of about 150 lines or a folder-sized program.
6. What is the first figure? No figure script exists today, so `figures/figlib.py` cannot be evaluated against code.
