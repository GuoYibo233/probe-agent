# Review of the from-zero structure plan, perspective 3: the experiment-management skeptic

Written by a read-only Fable 5.1 reviewer (effort max) at gyb's request on
2026-09-14. Input: `plans/2026-09-14-structure-from-zero.md` at commit 07adb8f.
Role given: a researcher burned by config systems; break the key, the
workflow files, the versions, the ledger, the monitor removal, the
abstraction level, debug and the tracker, each as a concrete case.
Reproduced verbatim below, with the HTML entities of the transport decoded.

---

Read-only. Every code claim cites `file:line` at HEAD 07adb8f; the uncommitted edit in `pipeline/train/train_causal_share.py` (a CUDA-only device check at 1010-1011) is ignored except where noted. Nothing under `plans/archive/` was read.

## Verdict

The key design ("Identity, reuse, versions") is right in shape but wrong in two details that make it silently reuse stale outputs: the sample subset (seeds, tasks) and cross-workflow references are left out of the key, so the two most common experiment shapes here (more data per task; a re-run baseline) never re-run downstream. The monitor removal is defensible except for one protection that nothing replaces: a dead agent server under a live loop produces aborted records at full speed, the run "completes", and the aborted files are then treated as done forever. The abstraction level is well judged (every shared module has three or more verified copies), the debug overlay picks the wrong lever (backbone instead of sizes), and the wandb recommendation cannot be implemented in the agent environment.

## Findings

**1. Extending the sample never re-runs anything downstream (breaks reproducibility).** Do: sample with `seeds: [42, 67, 4267]`, build, train, eval. Then edit to six seeds and run again. The plan yields: sample extends in place (intended, "Identity, reuse, versions": "the task list and the seed list are left out of the key on purpose"), but build's key is `build section + sample key`, unchanged, and `meta.json` says done, so build is skipped, so train and eval are skipped. The researcher believes they trained on 2x data. Same for `score` after adding inject seeds. Evidence: today's builder globs every file in the run directory (`pipeline/annotate/build.py:61-62`, `335`), so whatever is keyed, the consumed set is "everything present". Fix: the sample *directory* is keyed without seeds/tasks (extends in place), but every consumer's key includes the subset it consumes (`sample.split`, `sample.seeds`, `sample.n`) and the consumer reads exactly that file list, never a glob. Drop `traj_per_task` (redundant with `len(seeds)`; today both are demanded and cross-checked, `envs/collect/run_appworld.py:48-68`). State that `split` is keyed; only the task subset within a split is not.

**2. A dead server yields a "finished" run of aborted records, and re-running skips them (breaks reproducibility; not covered by the monitor replacement).** Do: start a sample stage; the vLLM server dies at task 40 of 315. Today's loop catches per-task exceptions, records `abort`, evaluates, writes the final record and moves on (`run_appworld.py:221-241`; stream retries are three then raise, `pipeline/inject/live_appworld.py:241-248`). The heartbeat keeps advancing, so the plan's `run.py ls` (status from the row plus heartbeat age) shows healthy. The run finishes with 275 aborted files. Then: fix the server, re-run; the plan's loop "skips a task-and-seed whose file exists" (`agent/loop.py`), and today's `is_done` is "has a final record" (`run_appworld.py:79-82`), which an aborted file has. Today the sampler's `/health` probe on the service piece would have shown `dead`/`suspected stall` (`ops/sampler.py:323-332`, `ops/verdicts.py:74-88`; `--service` requires `--port`, `ops/launch_cmd.py:271-276`). Fix: (a) a task file is done only when its final record has `abort == null`; aborted files are partial and get redone; (b) the loop stops after N consecutive connection-class aborts instead of continuing; (c) `ls` probes each server piece's `/health` (the launcher knows the port) and shows per-piece alive.

**3. A changed default is invisible to the key (breaks reproducibility).** Do: change the `train.lr` default in `settings/config.py`; run a setting that never listed `lr`. The key hashes "only the values that differ from the defaults", the diff is still empty, the old directory is reused, and its saved `config.yaml` says one value while the code now says another. Conversely a setting that explicitly wrote the old default now has an empty diff, gets a new key and re-runs needlessly. The plan's guard is a human rule ("What keeps the tree this shape", rule 3). Fix: `tests/test_config.py` keeps a golden file of every field's default; an existing field whose default changed without a bump of the reading stage's `VERSION` fails the test; a new field is allowed (that keeps the plan's "adding a hyperparameter changes no key"). Thirty lines, machine-checked.

**4. References by `<workflow>/<setting>` are not keyed and resolve through the ledger (breaks reproducibility).** Do: edit the baseline setting (temperature), re-run baseline, re-run the inject workflow. `score`'s key is its section plus the inject key ("A workflow file" table: upstream "inject or sample"); the baseline is a name, not an upstream key, so score is skipped and the old comparison stands. Do: rename `ctool_on_qwen06`; `inject.yaml` still says `train_probe/ctool_on_qwen06`; "the ledger resolves the name to the directory", the old rows are never edited, so the reference resolves to a run that the current files cannot regenerate. Fix: resolve references by loading the named setting from its file and computing its key (a missing setting is a load error); the resolved key enters the referencing stage's key and is written to `meta.json` as `upstream`; the ledger maps key to directory only. Allow an explicit key in place of a name for pinning.

**5. No "running" state: two walks on one key collide (breaks outputs).** Do: launch `train_probe ctool_on_qwen06` (sample goes to tmux; the walk stops), then launch `cgen_on_qwen17_lora` a minute later. Its sample key is identical, the directory is "partial", the plan continues it, and a second loop starts on the same files; today's `TrajLog` opens with `"w"` (`envs/collect/common.py:337`), so half-written files are truncated. Today this is blocked by the unique run_id in `jobs.json` (`ops/launch_common.py:140-142`) and `record.py:243-244`. Fix: `meta.json.status` gets four values: running (heartbeat fresh), stalled, failed, done; the walk starts only missing/stalled/failed (failed needs `--retry`, or an OOM loops forever), and for running it prints the session and exits. The tmux session name must carry the key so `ls` can match session to directory.

**6. Ledger appends from several hosts without a lock (breaks the ledger).** The plan writes rows "at start and at finish" from a stage; `/home` is NFS across the cluster (`ops/gpu_state.md:83-84`) and `O_APPEND` is not atomic across NFS clients. Today `record.py` appends with no lock (`ops/record.py:84-86`) but is only ever invoked on the launching host by `register_all` (`launch_common.py:155-158`) and by hand at wrap-up; `jobs.json` uses `flock` (`ops/gpu_jobs.py:64-73`). Also unspecified: the fold semantics (today a later finish row overrides, `record.py:113-119`, and this was used to correct a wrong `ok`, `ops/runs.jsonl:154`), an attempt id (the same key can start twice after a failure), and the dirty-gate exemption for ledger files and the lock (`run.py:790-796`, copied at `record.py:54`, `runmeta.py:28`). Fix: one `ledger/runs.jsonl.lock` under `fcntl.flock` for every append, rows keyed by (stage, key, start time), last finish wins, exemption list in one place, and keep the fail-closed git probe (`record.py:58-81`) and the dirty patch saved into the run directory (`record.py:257-263`), which the plan's `meta.json` drops.

**7. `--debug` swaps the backbone, so a smoke does not smoke the real configuration (wastes compute, hides failures).** "Debug" overlays "the smallest probe backbone". Do: `--debug` a qwen17 LoRA grad-checkpoint setting; it runs qwen06. Today grad-ckpt is per cell (`ops/jobs.json:438` vs `458`), peak memory differs by 2x between those paths (`references/launch-methodology.md:44-45`), and two different settings collapse to one debug key, so the second is "skipped". Fix: `debug.yaml` overrides sizes only (tasks, seeds, examples, steps, eval examples), never `models.probe` or `probe.tuning`. For `tests/test_train_alignment.py` "on CPU with the debug model": use a tiny random-init Qwen3 config as the old demo did (`.gitignore:45-48` names `demo/tiny_qwen3`); packing alignment does not depend on weights. Note the working-tree edit makes the trainer CUDA-only; the plan and that edit disagree.

**8. Shared pure modules have no `VERSION` (breaks reproducibility).** `data/cut_points.py` and `data/call_syntax.py` determine build's examples and the live fire positions, but `VERSION` lives "at the top of each stage's file". Do: change the cut rule; build's key is unchanged; the dataset is reused; the live loop fires at new positions against a probe trained at old ones. Fix: a `VERSION` in each pure module and each stage declares `DEPENDS = (cut_points.VERSION, ...)` folded into its key. Also note the two cut rules differ today on purpose (live has no `MAX_BOUNDS` thinning, `live_appworld.py:181-184`); unifying them is a behaviour change on one side and needs a build `VERSION` bump.

**9. A `VERSION` bump invalidates every downstream run even when the output is byte-identical (wastes days).** A sample record-format change re-keys sample, build, train (18-30 h each per the GPU time memory), eval, inject, score. The driver already has a byte-for-byte rebuild check for build artifacts (`pipeline/driver.py:77-79`). Fix: for deterministic stages key the consumer on a content hash of the upstream output manifest (build writes `manifest.json` with file hashes; train keys on it). Sampling at temperature 1.0 is not byte-stable across re-runs (the `cmp_chat_noprobe_5` server series, `jobs.json:226-268`), so sample stays key-chained.

**10. Directory ownership and orphans (confuses the reader).** Named `<setting>__<key>` by the creating setting: nine trainings and the baseline share a sample directory named after whoever ran first, in another workflow's folder; a `common` edit gives every setting new keys and leaves old directories matching no setting; a directory without a ledger row (debug, a crashed start) is invisible and the key re-runs into a second directory. Fix: `<outputs>/<stage>/<key>/` is the directory, existence on disk is the truth, the ledger is the index; `owners` in `meta.json` lists every (workflow, setting) that used it; `ls` flags "orphaned (setting edited)" with the diff.

**11. Continuing a partial directory across commits (confuses; for train, breaks).** `meta.json` holds one `commit`; a sample half done at commit A and finished at B records one. Today RUNMETA appends one entry per launch (`ops/runmeta.py:4-7`, `80`). Train "continues from `last/`": no such checkpoint exists today (`best/` only on validation improvement, `train_causal_share.py:1254-1263`), and the trainer refuses to write into a trained directory without `--force` precisely to avoid mixing (`1017-1020`). Fix: `meta.json.launches[]` one entry per start; each task record carries its commit; train resumes only at the same commit, else starts over; checkpoint `last/` by wall time, not every eval.

**12. wandb cannot be imported where the plan mirrors from.** `wandb 0.28.1` declares `pydantic<3,>=2.6` (`envs/tales/venv/lib/python3.12/site-packages/wandb-0.28.1.dist-info/METADATA:54`); the agent env pins `pydantic==1.10.26` (`ops/env_locks/appworld.txt:52`). No code uses any tracker; the only install is in the tales env the plan deletes; all caches are on NFS (`jobs.json:73`, `gpu_state.md:85-87`), consistent with nodes without internet. Fix: the tracker is never imported by a stage; it is a separate login-machine process that tails `metrics.jsonl` (`run.py sync`). Then MLflow file store on NFS (no network, no account, `mlflow ui` plus port forward gives the phone view the old page gave) beats wandb; default `none` is right.

**13. A debug sample is not quick.** The agent model is gpt-oss-120b (the only gpt-oss row, `configs/models.json:24-27`; the plan's `gptoss20b` in "A workflow file" does not exist there); server ready takes about five minutes (`runs.jsonl:4`, `ready_s: 306`). Fix: `serve_agent` detects a live server with the same model and generation settings and attaches; debug reuses warm servers; `--debug --stage train` reuses real upstream outputs.

**14. Grids are hand-written and override runs are unnameable.** `sweep_preset.py` is dropped ("Not carried over"); a theta x format grid or a three-seed ablation is N near-identical blocks; a run started with `train.lr=3e-5` on the command line lives only in its `diff.yaml`. Fix: a `sweep:` key inside a named setting (`sweep: {inject.theta: [0.8, 0.9], inject.format: [p1_e1, p2_e2]}`) expanded at load into child settings named `<setting>/theta=0.8,format=p2_e2`; `matrix.py` groups children by everything but the swept fields and reports mean and spread.

**15. Two stage tables and a fixed piece count.** `run.py` holds `STAGES` (pieces, environments, cards) and `settings/config.py` holds the reads/upstream table; adding a stage touches five places. Today's collection ran two vLLM replicas and seven client shards (`jobs.json:336-426`); the plan's pieces are fixed per stage. Fix: one `STAGES` table in one file; replica and shard counts are settings values.

## Key failure table

| Case | Rating | Fix |
|---|---|---|
| Default changes, no VERSION bump | breaks reproducibility | golden defaults test (F3) |
| Field renamed or moved between sections | wastes compute, orphans directories | treat as VERSION-class; a one-dict alias table in `key()` keeps old keys valid |
| `common` value changes for a file | correct re-run; confuses | `ls` marks orphaned directories; rule: `common` is frozen once a setting has a finished run |
| Shared value a stage does not read changes | fine if reads are field-level; wastes 9x if section-level (`models` holds both agent and probe) | hash the listed fields, test that `models.probe` does not enter the sample key |
| `traj_per_task` or seeds change | breaks reproducibility | consumers key on the subset (F1) |
| Same key in two workflow files | confuses; can corrupt the owner's score if it globs | key-named directory, owners list, explicit file lists (F10) |
| Setting renamed/deleted while referenced | breaks reproducibility | resolve through files, not the ledger (F4) |
| `find` with several matches | fine | one line per (stage, key) with status, date, setting, diff columns |
| `--debug` sharing keys | confuses; hides failures | sizes-only overlay (F7) |
| VERSION bump cascade | wastes compute | content-hash keys for deterministic edges (F9) |
| Partial directory, code changed since | confuses; train breaks | launches list, same-commit resume (F11) |
| Failed directory treated as partial | wastes compute (OOM loop) | `failed` state needs `--retry` (F5) |

## Workflow shapes

| Shape | Files and settings | Awkwardness | Smallest fix |
|---|---|---|---|
| Nine trainings on one sample | 1 file, 9 settings, `common` holds sample | sample directory named after the first setting; nine walks race on one running sample; sample key breaks if `models` is hashed whole | F5 running state; field-level reads; key-named directories |
| Same probe, two thetas x two formats | 1 file, 4 settings, two cross-file references | four near-identical blocks; a 3x5 grid is fifteen; references unkeyed | `sweep:` (F14); keyed references (F4) |
| Temperature comparison | 3 files (baseline, train_probe, inject), 6 new settings | temperature restated six times; nothing checks the inject arm, its probe's data and its baseline share `generation` | `score` refuses when the two runs' `generation` sections differ; `sweep` over `generation.temperature` in each file |
| Training-data scale | 1 file, 2 settings | impossible: identical keys, second setting skipped | F1 |
| One training, three seeds, mean | 1 file, 3 settings | repetition; no aggregation over runs | `sweep: {train.seed: [...]}` and grouping in `matrix.py` |

The "each stage at most once" rule is fine; it forces cross-file references, which only work once references are keyed.

## Monitor protections

| Protection today | Where | Covered by the plan | Minimal thing to keep |
|---|---|---|---|
| Card double-booking between my sessions: fail-closed live probe, whole launch refused, overlap check | `launch_common.py:70-88`, `launch_cmd.py:151-163`, `291-299` | yes (`scripts/launch.py`) | keep fail-closed semantics; add the same-key running state (F5) |
| Launch on a card probed free a minute earlier | probe is seconds before tmux, `launch_cmd.py:291-303` | same as today (the CUDA-init window is unprotected today too) | re-probe after the alive window and report a foreign process |
| Stalled job overnight: adaptive stall line, escalation | `verdicts.py:39-49`, `91-116`; incident agent never spawned (`gpu_state.md:37-42`) | partly: `ls` shows stalled when someone looks; rate/ETA history lost (`heartbeat.json` is one state) | append `heartbeat.jsonl`; port `stall_line_s`/`rates` (40 pure lines) into `ledger.ls` |
| Dead server under a live client | `sampler.py:323-332`, `verdicts.py:74-88` | no | F2 |
| Sessions outside the ledger | `gpu_jobs.py:121-135`, `168-176` | no | `ls` lists `new1_*` tmux sessions per host that match no row |
| Premature deregistration refused | `gpu_jobs.py:439-461` | not needed (stage writes its finish row), but a human kill leaves no row | `run.py kill` writes the killed row; `ls` derives dead from session gone plus not done |
| Refire keeps session/log naming, resets the timeline | `launch_cmd.py:359-449`, `sampler.py:386-388` | only at launch time | re-running the walk is the refire; it must reuse an alive server piece instead of starting a second one |
| Phone view | web on :8377 | no; the plan's substitute is wandb (F12) | MLflow UI or nothing |

## Abstraction bar

| Module | Copies today (verified) | Judgement |
|---|---|---|
| `data/task_record.py` | writer `common.py:335-345`; readers `rebuild.py:122`, `exec_calls.py:308`, `build.py:61-75`, `extract_completed.py:162` | passes |
| `data/cut_points.py` | `rules.py:29`; `live_appworld.py:174-187` (two variants, documented divergence at 181-184) | passes on count; the merge changes one side's behaviour, needs a build VERSION bump and a `max_bounds=None` parameter |
| `data/call_syntax.py` | regex `rules.py:67`, `parse_call.py:22` ("must stay in sync", 21), `score_live.py:54`; splitter `rules.py:118`, `eval_causal_call.py:134`, `eval_causal_param.py:128` | passes clearly |
| `models/probe.py` | loaders `eval_tool.py:81`, `probe_server.py:98`,`122`, `check_bundle.py:128`; generation `probe_server.py:180`, `eval_causal_call.py:231`, `eval_causal_param.py:225`, `train_causal_callgen.py:339` | passes clearly |
| `models/template_gptoss.py` | `harmony_render.py`; hand-assembled template `common.py:21-37` (exists because the agent env cannot import openai_harmony, `common.py:15-20`); stream parse in `live_appworld.py` | passes; the venv wall must be a selfcheck rule; note `chat()` "the server renders" changes today's default client-rendered path (`test_preset.py:164`), a data-changing decision that needs a DATA.md line |
| `models/agent_model.py` | `common.Chat` (40+), `live_appworld.py:241`,`264`, `replay_inject.gen_payload` (`test_preset.py:363-372`) | passes |
| `scripts/ledger.py` | `LEDGER_PATHS` x3 (`run.py:795`, `record.py:54`, `runmeta.py:28`); git probe x3 (`run.py:799-805`, `record.py:58-81`, `runmeta.py:32-52`); monitor dir x2 | passes |

Opposite disease: `train/train.py` folds a separate ctool trainer into a 1293-line cgen/cparam trainer with a method switch in model build, collate, loss, eval and save; acceptable only if the method-specific parts are three small objects behind one loop. The two stage tables (F15) are the "one small change touches many files" case; merge them.

## What the plan gets right

- Key = settings content + upstream keys + VERSION, with `config.yaml`/`diff.yaml`/`meta.json` inside every run directory; "If you edit a setting" gives the correct behaviour for the common case.
- Sample and inject as per-task-and-seed file collections that extend in place; the loader failing on unknown keys; `constants/` never entering a key.
- Deleting the sampler, verdicts, web page and incident agent: the incident chain never worked (`gpu_state.md:37-42`) and the verdict logic worth keeping is forty pure lines.
- The dirty gate kept as one function; commit recorded but not keyed.
- Debug as an overlay rather than small copies of settings; debug outputs out of the ledger (smokes are unrecorded today too, `SKILL.md:56-59`).
- The shared modules all clear the third-repetition bar with verified copies; nothing in `data/` or `models/` is premature.
