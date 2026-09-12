# stage-commands: the copy-paste command table for the five-stage pipeline

This file is the command template for the five stages collect / annotate / train / eval / inject, with the parameter interfaces copied word-for-word from the `pipeline/` source code (the code state as of the 2026-07-31 c1 batch); copy it verbatim, substitute the placeholders, and it runs.
**Every command always goes in through the repo root `run.py`** (a CLAUDE.md hard rule since 2026-08-02), don't call the underlying scripts directly: the interpreter is chosen by the registry, the fixed parameters are carried by the registry, and a GPU task only assembles the command and hands it to gpu-run. What this file gives is which parameters to pass for each task; the source of truth for task names and interpreters is `run.py` (checked with `python3 run.py list` / `show <task>`).
The companion process description is one level up in `SKILL.md`; the scoring convention and data settings are not in this file, they're in `invariants.md` in the same directory.
Placeholder convention: `<MODEL>` = a model short name like q35/q36/gptoss, `<BATCH>` = the batch prefix (e.g. c1), `<ENV>` = appworld/bfcl/tales, `<DATA_ROOT>` = the dataset directory (e.g. `pipeline/data/aw_official_v1/<MODEL>`).

## 0. Environment and path constants

| Environment | Absolute path | transformers | Which line it manages |
|---|---|---|---|
| mbert-env | `/home/y-guo/reproduce/new1/mbert-env/bin/python` | 4.57.6 | ModernBERT: mtool / mext, and the eval that evaluates them |
| cprobe-env | `/home/y-guo/reproduce/new1/cprobe-env/bin/python` | 5.14.1 | causal models: ctool / cgen / cparam, and the eval that evaluates them |

Neither environment upgrades to match the other (a mixed architecture on the old version silently computes wrong under chunked incremental feeding, this is the reason the version is pinned). **Going through run.py means you don't have to pick the interpreter yourself**; the table above is only there so you can tell which line an error is coming from.

Each environment's version-lock snapshot is in `ops/env_locks/` (one `uv pip freeze` txt per venv, covering both environments in the table above plus the collect/serve environments under `envs/`); the explanation and the generation command are in that directory's `README.md`. **Before a major upgrade, first regenerate the corresponding snapshot and commit it**, then install the packages; this way, when "some environment suddenly behaves differently," `git log -p` can pin down directly which package changed, without redoing the whole package-installation process.

**Which tasks occupy a card and which don't: always check the full list live with `python3 run.py list`, only ones marked `[launch]` get handed to gpu-run** (run.py only assembles and prints the command for them), ones not marked run straight through to a result; this file no longer keeps a copy that would go stale. Two exceptions worth knowing: (1) `launch-probe` / `launch-eval` don't carry the `[launch]` mark in the list (they ssh+tmux and launch by themselves, they don't hand out a command), but they go through the same dirty-tree gate; (2) `ann-check-callstr` is a third kind: it doesn't occupy a card, but torch is on its import chain, and the registry has pinned it to cprobe-env and clears `CUDA_VISIBLE_DEVICES`; bypassing run.py and hand-typing `python3 pipeline/annotate/check_callstr.py` is guaranteed to die with a ModuleNotFoundError. For a single task's interpreter/fixed parameters/whether it goes through the gate, check `python3 run.py show <task>`.
A task marked `[launch]` no longer needs the manual "`show` the command → copy into tmux → hand-type three registrations":
`python3 run.py launch <task> [args...] --run-id ID --track direction --piece host:gpus`
does probe the card → tmux → 30-second liveness check → the three registrations, ledger/record/RUNMETA, in one command (see gates.md G16);
`launch-probe`/`launch-eval` are dedicated launch shells for the batch placement-table scenario, and they're wired into the same registration.

| Item | Path |
|---|---|
| Project root | `/home/y-guo/reproduce/new1` |
| Data root | `/home/y-guo/reproduce/new1/pipeline/data/<batch dataset name>/<MODEL>` |
| runs root | `/home/y-guo/reproduce/new1/pipeline/runs` (smoke artifacts are in `pipeline/runs/smoke/<rid>_smoke`) |
| Log directory | `/home/y-guo/reproduce/new1/logs` |
| Collect envs root | `/home/y-guo/reproduce/new1/envs` (trajectories land in `envs/runs/<run_id>/`) |
| vLLM service logs | `/home/y-guo/reproduce/new1/envs/serve_logs` |
| Model weights | `/net/tokyo100-10g/data/str01_01/y-guo/models` (other people's are under `.../zhou-y/models`) |

Base weights (hard-coded in the scripts, changing the base means changing the code; **remember only the constant name, not the line number**, they've drifted once this round; to locate one, `grep -n` the constant name):
- ModernBERT-base → `/net/tokyo100-10g/data/str01_01/y-guo/models/ModernBERT-base`
  (`train_mbert_tool.py` and `train_mbert_extract.py` each have a module-level constant `MODEL`)
- Qwen3-0.6B-Base → `/net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-0.6B-Base`
  (`train_causal_tool.py`'s `MODELS` table, `train_causal_callgen.py`'s `QWEN`)

---

## 1. collect

**What it does**: consumes a manifest json, generates the vLLM service launcher + the client-shard launcher + a human-readable manifest; **generates only, doesn't execute**, no ssh, doesn't touch a GPU.

```bash
cd /home/y-guo/reproduce/new1
# Trial generation (take a look first, never touch envs/)
python3 run.py gen-launch --config pipeline/collect/manifest_<BATCH>.json \
  --dry-run --out-override /tmp/genlaunch_<BATCH>/
# Generate for real -> envs/runs/<run_id>/
python3 run.py gen-launch --config pipeline/collect/manifest_<BATCH>.json
```

| flag | Required | Description |
|---|---|---|
| `--config` | yes | the manifest json, template at `pipeline/collect/manifest_w0.json` |
| `--dry-run` | no | must be given together with `--out-override`, otherwise exits with 2 |
| `--out-override` | no | write to a different location |
| `--force` | no | allow overwriting an existing same-named file in the target directory |

**Input**: the manifest requires `run_id` / `servers[]{host,gpu,model_key,port,session,extra_flags,card}` / `clients[]{tag,model_key,split,num_shards,shard_ports[],outdir,exp}`; optionally `envs_root` (default `envs`), `client_session_prefix` (defaults to the first two segments of run_id joined, `w0_aw_official` → `new1_w0aw`), `traj_per_task`+`seed_family` (since 2026-08-22, multiple trajectories per task: either both are given or neither is, `len(seed_family)==traj_per_task`, only recognized when env=appworld; when present, the client command appends `--traj-per-task N --seeds a,b,…`, and when absent the output is byte-for-byte identical to the old version).
**Output**: `envs/runs/<run_id>/launch_servers.py`, `launch_clients.sh` (0o775), `MANIFEST.md`.
**Exit code**: 0 normally; every validation failure is `sys.exit(2)`: the servers must be on the same machine, model_key must be in the table (only q35/q36/gptoss are recognized), ports/session/cards must not repeat, `len(shard_ports)==num_shards`, the shard ports must exist and match the model, the target already has a file of the same name with no `--force`. A non-standard `outdir` name only gets a WARN and is forced to `<env>_<model_key>` (`env` is taken from the manifest's top-level `env` field, defaulting to `appworld`; downstream recognizes the model by the directory-name tail, and a renamed one gets silently skipped).

The two generated launchers still need to occupy a card to run → **launch them through the gpu-run skill, don't hand-roll ssh/nohup**.

---

## 2. annotate

**What it does**: cuts the raw trajectories into a sample set of "thinking prefix → which tool this step calls" (build.py), then labels each sample with the character span of its parameter values (param_label.py). Both steps are pure CPU.

```bash
cd /home/y-guo/reproduce/new1
# Three steps as one chain (recommended): build -> param_label -> check_callstr, using the same config
python3 run.py recipe annotate-chain --set config=pipeline/configs/<BATCH>_<MODEL>.json
# Or run step by step
python3 run.py ann-build         --config pipeline/configs/<BATCH>_<MODEL>.json
python3 run.py ann-params        --config pipeline/configs/<BATCH>_<MODEL>.json
python3 run.py ann-check-callstr --config pipeline/configs/<BATCH>_<MODEL>.json
# Optional: consistency acceptance after changing rules.py/build.py (paths are all hard-coded, no parameters)
python3 run.py ann-accept-v3diff
```

After the recipe finishes, check `python3 run.py status`; if it blows up midway, fix it and continue with
`python3 run.py recipe annotate-chain --id <id> --resume`.
Warning: the recipe engine itself has a smoke test: `python3 run.py recipe engine-smoke`, a two-step pure-CPU self-test
(runs `parse-call-selftest` twice), which verifies that **the machinery** of `state.json` / logs / the resume path
isn't broken itself, it doesn't verify pipeline data. Run it first when the engine has been changed or `--resume` is suspected of being wrong, don't use the real annotate chain as a testing ground.

The third step, `ann-check-callstr`, is **the implementation of G19-G22** (doesn't occupy a card, but the registry has pinned it to
cprobe-env: `main()` imports eval_causal_call → torch, which the system python3 doesn't have;
since 2026-08-22 this import was moved out of the module level, so `import check_callstr` itself no longer needs torch,
but running main still needs cprobe-env; it must run after the first two steps), artifact
`<DATA_ROOT>/CALLSTR_CHECK.md`; it does five hard gates and four classes of "reported but not blocked" known deviations at the same time,
see the G19-G22 entries in `gates.md §1` for details.

**The bfcl batch (`bfcl_mtb_v1`)'s complete commands can be copied directly and adapted to a different environment**: note that bfcl has no official partition,
the task list has to be self-generated once first (method and gates in `extending.md §4.6`):

```bash
cd /home/y-guo/reproduce/new1
# ① Task list: --dry-run first to see the stats, then save (the second run gets blocked by the "don't silently overwrite" gate, unless --force)
python3 run.py gen-bfcl-splits --dry-run
python3 run.py gen-bfcl-splits --out-dir pipeline/splits/bfcl_mtb_v1
wc -l pipeline/splits/bfcl_mtb_v1/{train,val,test}.txt      # must be 140 / 40 / 20
# ② Three steps per model (an equivalent way to write it: three recipe annotate-chain runs, changing config each time)
for M in q35 q36 gptoss; do
  python3 run.py ann-build         --config pipeline/configs/bfcl_$M.json || break
  python3 run.py ann-params        --config pipeline/configs/bfcl_$M.json || break
  python3 run.py ann-check-callstr --config pipeline/configs/bfcl_$M.json || break
done
```

The task-list generators for the other environments are likewise in the registry, just change the task name:
`gen-alf-splits` (ALFWorld, warning: no anti-overwrite gate), `gen-tau2-splits` (tau2's three domains),
`gen-toolhop-splits` (ToolHop 695/200/100).

The two scripts share the same config, **one per model**. Config fields (copied verbatim from `pipeline/configs/aw_q35.json`):

| Field | Meaning |
|---|---|
| `run_family` / `model_short` | only go into the report title |
| `env` | appworld / tales / bfcl, decides the event extractor |
| `model_full` | events are filtered by this (e.g. `qwen3.5-27b`), one model, one set of data |
| `traj_runs[]` | list of trajectory directories, absolute paths |
| `traj_runs[]`'s hierarchy | Warning: must be written down to the **run directory itself** (`envs/runs/full_v1`), not its parent directory (`envs/runs`). Writing the parent directory silently merges in the smoke batch, exits 0 with no warning (`extending.md §5 #20`, gate G21) |
| `official_split_files.{train,val,test}` | task-list txt files, one task_id per line. **Also used when the environment has no official partition**, pointing at a self-generated task list under `pipeline/splits/<batch>/` (see `extending.md §4.6`) |
| `split_mode` | pure decoration, **no code reads it** (`extending.md §5 #12`) |
| `split_desc` | optional, **the report's wording is taken from it**. Default `"official task list, task-instance level"`; an environment with no official partition must write it (bfcl writes `"the frozen old three splits from v3_1, task-instance level; BFCL has no official partition"`), not writing it gets blocked by gate G22 |
| `data_out` | the dataset output directory = every subsequent `--data` |
| `seed` | defaults to 42 (since np821, `rules.py`'s constant has switched to the first entry of the seed family); an explicit 20260729 written in an old config still takes effect as-is, overriding the default |
| `weight_mode` | optional, since 2026-08-22. Defaults to `uniform` = equal weight per step, w=1 (the long-term convention); the old convention `per_event` = w=1/m is only obtained by writing it explicitly, its only remaining use is byte-for-byte reproduction acceptance |
| `max_bounds` | optional, since 2026-08-22. The cut-point ceiling per event, defaults to 64, passed through to `rules.boundaries` for thinning |
| `trajs_per_unit` | optional, since 2026-08-22. How many trajectories per task (np821 = 4): check_callstr's gate B uses it to judge "one unit has exactly K traj and the sampling index `_r0..r{K-1}` is all present"; **when this field is present**, ANNOTATE_REPORT appends four extra statistics (the untruncated cut-point distribution, the count of events hitting the ceiling, the count of exactly-identical trajectories, the count hitting the 30-step ceiling); when absent, the report's set of lines matches the old version |

`ann-build` also has two CLI flags that override config fields of the same name: `--weight-mode uniform|per_event`,
`--max-bounds N`. Byte-for-byte reproduction of an old artifact (the G8 acceptance line) means taking the old config as-is and adding
`--weight-mode per_event --max-bounds 64` and rerunning in place: the config file doesn't change, that's the only way the
`config=`/`out=` lines in the report can match word-for-word.

**Output**: `<DATA_ROOT>/{train,val,test}.jsonl`, `tool_vocab.json`, `router_stats.md`, `qa_sample.txt`, `ANNOTATE_REPORT.md`; param_label additionally writes `<DATA_ROOT>/params/{train,val,test}.jsonl` + `PARAM_LABEL_REPORT.md` + `CHECK_50.md`; check_callstr additionally writes `<DATA_ROOT>/CALLSTR_CHECK.md` (it **only reads, never writes** the data itself).
**Exit code**: 0; `raise SystemExit` (=1) in three cases: no events with `model_full` remain after filtering, **a unit is not in any official task list** (refuses to silently drop it; the pitfall most commonly hit when changing environments, a wrong task-list file path or a changed split naming will error out across the board), or an unknown env. A self-check assert failure is also 1 (prefix = a 200-entry spot check against the original-text slice, a unit doesn't cross splits, a 20-unit task-list-assignment spot check per split). accept_v3diff is special: **fully consistent = 0, any inconsistency = 1**, the report is written to `pipeline/annotate/ACCEPT_V3DIFF.md`.

---

## 3. train

**What it does**: trains each cell on the same data. Currently in service, three cells (the m-line retired since 2026-08-21): ctool (a causal model judges the tool kind), cgen (a causal model writes the whole call directly), cparam (a causal model, given the tool name, writes only the parameter segment; the data comes from the same source as cgen, zero new annotation); retired, kept for reference, two cells: mtool (ModernBERT judges the tool kind), mext (ModernBERT circles the parameter span), both can still be launched individually. The cells are independent of each other and can all run in parallel. Three base tiers: ctool/cgen/cparam all recognize `--base qwen (0.6B, default)/qwen17 (1.7B)/qwen4 (4B)`, **one batch runs only one base tier**, run_id has no tier segment, mixing tiers collides on rid (see extending §3.4). **Training all needs a GPU, so launch through the gpu-run skill, don't hand-roll ssh/nohup.**

Smoke first (add `--smoke` to each cell, artifact written to `pipeline/runs/smoke/`, doesn't pollute the real directory), then the full volume. Below are the shapes of the **12 commands actually run in the c1 batch** (one per cell, only the model segment differs):

Every training cell is a launch-type task: `run.py` only **assembles and prints** the full command (the interpreter and script path are filled in by the registry, without cd/CUDA_VISIBLE_DEVICES/tee, that's the job of the gpu-run launch template), and the launch itself goes through gpu-run. Warning: the dirty-tree gate is enforced before emitting the command: a non-empty `git status --porcelain` refuses it, commit first; to force it through, add `--allow-dirty`. **This gate is enforced even by `run.py show <task>`**
(hardened 2026-08-02, audit A3): the documented path "use show to emit the command" must not become a backdoor around the gate, only `show <task> --allow-dirty` lets it through.

```bash
cd /home/y-guo/reproduce/new1
R=pipeline/runs; D=pipeline/data/aw_official_v1
python3 run.py train-mtool --data $D/q35 --out $R/c1_q35_mtool
python3 run.py train-mext  --data $D/q35 --out $R/c1_q35_mext
# ctool's --base qwen is already fixed in the registry, no need to pass it again; --align-tol is the only hyperparameter ever touched
python3 run.py train-ctool --data $D/q35 --out $R/c1_q35_ctool --align-tol 3e-4
# cgen/cparam's --base defaults to qwen (0.6B), pass --base qwen17 / qwen4 to switch tiers
python3 run.py train-cgen  --data $D/q35 --out $R/c1_q35_cgen
# cparam (a new cell since 2026-08-21): given the tool name, only generates the parameters
python3 run.py train-cparam --data $D/<m> --out $R/<batch>_<m>_cparam
```

Launching the whole batch at once goes through the placement-table launcher `python3 run.py launch-probe` (the cell table's sole source of truth is `run.py`'s
`CELLS`, `ops/launch_probe.py` imports it); use `--dry-run` first to check the machine placement.
It has its own `--force`, **passed through as-is to the four training scripts**: `launch-probe smoke` must carry it when rerunning the same batch, since smoke's `--out` is deterministically derived from `<batch>_<model>_<cell>_smoke`,
and the second run gets blocked by the "an out with an existing `train_log.jsonl`" guard, turning into SKIP/exit. The full tier is the same way,
only add it once you've confirmed you want to overwrite that directory.
Once it **launches successfully it automatically appends one `RUNMETA.json` to every `--out` directory**
(time/machine/kind=`train`/the actual command/commit/branch/dirty + the list of dirty files, plus the session/launch_host/gpu/log/placement-table paths; appends without overwriting, launching twice into the same directory leaves two entries). This is written by the first step of
`launch_common.register_all` (it is the sole writer of RUNMETA, the three-registration order is RUNMETA→ledger→record), and a `RUNMETA: <path>` line in the receipt
means it was written; only if the receipt shows `WARN RUNMETA not written (<directory>): <error>`
does it need to be backfilled by hand with `python3 run.py runmeta <outdir> --cmd '<actual command>' --kind train`.
(Before 2026-08-26 the launcher wrote one entry itself and then called `register_all`, and the receipt's line
`WARN --outdir not given, RUNMETA not written` was a false alarm; backfilling it by hand based on that
would leave two duplicate entries in the same RUNMETA, which is exactly what happened to np821's 12 training run directories; fixed in commit 6047f83.)
A hand-rolled launch (not through launch-probe) needs to backfill one itself: `python3 run.py runmeta <outdir> --cmd '<actual command>'`.

Warning: **when relaunching a single cell, don't relaunch the whole placement table** (measured on np821): a cell that's already finished
gets instantly rejected by the training script's "an out with an existing `train_log.jsonl`" guard (the exit code stays the same, the whole batch isn't interrupted), but **the launcher already did the registration before the guard blocked it**: that
already-finished run gets a fake `RUNMETA` entry added, and its run_id gets stuffed back into the active ledger.
The ledger ends up with a zombie entry that never disappears on its own, and RUNMETA gets one extra command that never actually ran.
Handling: **write a temporary placement table containing only the cell being relaunched**, kept outside the repo (e.g.
`$CLAUDE_JOB_DIR/tmp/<batch>_<cell>_only_placement.json`) to avoid dirtying the working tree,
and update that row in the official table `ops/<batch>_placement.json` with the new machine placement for the record.

When changing batches, just swap `q35` for `<MODEL>`, `c1` for `<BATCH>`, and the dataset name. run_id is always `<BATCH>_<MODEL>_<cell name>`, consistent across all four places (data directory name / tmux session / ledger name / commit message).

| flag | who has it | Description |
|---|---|---|
| `--data` | every cell | required, `<DATA_ROOT>`; mext can additionally use `--params` (defaults to `<DATA_ROOT>/params`) |
| `--out` | every cell | required, to prevent overwriting an old artifact |
| `--force` | every cell | **since 2026-08-02 (audit B7)**: without it, if `--out` already has a `train_log.jsonl`, it **exits outright with SystemExit, refusing to start training**: that directory has already been trained once, and training again would mix two runs' artifacts into the same `best/` with no way to tell them apart. The normal remedy is to **use a different `--out`**; only add `--force` once you've confirmed you want to overwrite. → before relaunching a specific cell, check whether the target directory already has a `train_log.jsonl`, don't mistake this exit for the script being broken |
| `--base qwen` | ctool only | **required**, the only choice is `qwen` |
| `--align-tol` | both ctool and cgen/cparam have it, with different criteria | ctool: defaults to `3e-4` (since 2026-08-28, decision 20; the previous default was 1e-4: after the ceiling became 8192, long windows became the norm, and `ks828b06` smoke had maxdiff_hidden 1.03e-4 with a relative difference of 1.46e-6 on an event with 8,167 tokens, which got blocked by the old default of 1e-4; the c1/np821 batches always passed `3e-4` explicitly). Whether it's a real computation error is judged by the reldiff in the report: on the order of 1e-6 = pure noise, above 1e-3 = a real computation error, loosening it wouldn't help. cgen/cparam (the new trainer): defaults to `2e-5`, the maximum absolute-difference threshold on per-row ce under fp32 (the per-token maximum-difference threshold is hard-coded at `3e-4`, and doesn't accept a command-line override), which is not the same criterion as ctool's `--align-tol`, and the numbers aren't interchangeable (spec §9, last paragraph) |
| `--align-only` | both ctool and cgen/cparam have it | only runs the alignment check and then exits (0); use it to verify separately before starting training |
| `--align-events` | cgen/cparam only (`train_causal_share.py`, since 2026-08-28) | defaults to `6`; the alignment check only draws events from val where `len(full_ids) <= 2048` (to control time cost) |
| `--mode` | cgen/cparam only (`train_causal_share.py`, since 2026-08-28) | **required**, `cgen` / `cparam`, decides which set of target-string and concatenation-tail logic to use; `run.py`'s `train-cgen`/`train-cparam` already carries this flag in the registry, only a hand-rolled command needs to pass it |
| `--tok-budget` | cgen/cparam only | defaults to `16384` (2026-08-28 smoke ruling, doesn't adopt `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`); the ceiling on "event count x the length of the longest concatenated sequence in the block, padded up to a multiple of 16" allowed in one physical block; a single event that exceeds the budget still forms its own block by itself (over-budget is allowed). `--eval-tok-budget` defaults to `0` = 2 x this value, i.e. `32768`. Basis: `ks828b06_gptoss_cgen_speed_b16k` (H100, 450 events, 20,641 rows, 57 updates) had a training-step peak of 60.59 GB (39% of the 93.10 GiB headroom); `--tok-budget 24576` had a peak of 80.91 GB and was 15% slower (`pipeline/runs/smoke/ks828b06_gptoss_cgen_speed*`, `ops/runs.jsonl`) |
| `--events-per-mb` | cgen/cparam only | defaults to `4`, the event count of a logical minibatch, the normalization unit for the loss |
| `--eval-per-epoch` | cgen/cparam only | defaults to `4`, evaluate full-volume val this many times per epoch (the set of evaluation points is `{ceil(U·k/E): k=1..E}`, and the point at `k=E` is the end of the epoch) |
| `--accum` | both ctool and cgen/cparam have it, with different meanings and different values | cgen/cparam: the number of logical minibatches accumulated, defaults to `2` (paired with `--events-per-mb 4` = 8 events per update). ctool: the number of physical batches accumulated, defaults to `4` (paired with `--bs 2` = 8 events per update, since 2026-08-28; previously it was `--bs 4 --accum 2`, but `--bs 4`'s first training batch OOM'd on H100, the process at 92.94 GiB, and it was backed off to this tier, decision 15; `--bs 2 --accum 4` ran through, nvidia-smi's maximum sample was 56,859 MiB, recorded in `ops/runs.jsonl`'s `ks828b06_gptoss_ctool_h100mem_bs2`) |
| `--base` | ctool/cgen/cparam | three tiers, qwen=0.6B / qwen17=1.7B / qwen4=4B (the weights are all on the NFS models drive). Required for ctool (the registry already carries qwen); defaults to qwen for cgen/cparam. Switching tiers at launch time goes through the placement table's extra (`--base qwen17`, whichever argparse writes last wins) |
| `--smoke` | every cell | the retired mtool/mext and the old row-by-row scripts (`train-cgen-rows`/`train-cparam-rows`) = 500 training / 200 eval instances; ctool = 200 / 80 events; cgen/cparam's **current trainer** (`train_causal_share.py`, since 2026-08-28) = 40 training events / 16 eval events, taken by sorting **ascending** by the full event's token count and taking the top N (train and val follow the same rule, not a random draw; rerunning the same `--smoke` gets exactly the same event set, which is not the same yardstick as the old convention "randomly draw 500/200", the numbers are not comparable); all are 1 epoch. When given together with `--max-events`, N overrides 40/16, still taken ascending; only when `--max-events` is given alone does it go through `random.Random(SEED)` randomly (following ctool's convention) |
| `--env` | every cell | defaults to appworld, **is only a log label**, doesn't affect the data path |
| `--device` | all except mtool | defaults to cuda |
| `--readonly-env` | every cell | choices `appworld/bfcl`, not passed by default (**not passing it = byte-level old behavior**). When passed, it's the "read-only + abstain" convention (since the ro1 batch): mtool/ctool fold the ground truth, the vocabulary = read-only tools (original order) + a final sentinel `<NON_READONLY>`; mext/cgen only train the task on read-only events, non-read-only samples only serve as fire-head negatives; cparam drops non-read-only samples entirely (it has no fire head). The ground-truth table is at `pipeline/annotate/readonly/<env>.json`, more than 5% of labels falling outside the table hard-stops it (`readonly_map.audit`). The artifact gains one extra file, `<out>/READONLY.json` |
| `--fire-head` | mext/cgen (cparam doesn't have this flag) | trains a fire head alongside (binary: whether all parameters at that boundary are ready). The ready ground truth is joined by `(event, sent_idx)` against `params/<split>.jsonl`; mext goes through an independent sample stream for a second forward pass, cgen takes the logit at the prompt's final position (the last `-100` in labels) so as not to see the target string. Artifact `best/fire_head.pt`, `meta.json` records `fire_head: true` |
| `--lora` | ctool/cgen/cparam (since np821) | trains the base with LoRA, **the classification head/fire head are still full-parameter as usual**; before saving `best/`, `merge_and_unload` first and fold back into the base, then `save_pretrained`, so `best/` is item-for-item isomorphic with what full-parameter training saves, **the four eval scripts load it back with zero changes** (they all use `from_pretrained(best/)`). `meta.json` gains one extra `lora` block recording the hyperparameters. When this flag isn't passed, the script itself never touches peft (all of peft's imports are inside the `--lora` branch), and behavior is identical to before this flag existed. The sole source of truth for the flag/default values/target modules is `pipeline/train/lora_util.py` (shared by the three cells, no copy allowed anywhere else) |
| `--lora-rank` / `--lora-alpha` / `--lora-dropout` / `--lora-lr` | the same three cells above | defaults 16 / 32 / 0.05 / 2e-4 (convention in the LoRA row of invariants §3). **The learning-rate priority**: an explicit `--lr` > `--lora-lr` (when `--lora` is on) > the full-parameter default of 1e-5; the three scripts' `--lr` default is `None` precisely so it can tell apart "not passed" from "passed a value that happens to equal the default" |
| `--grad-ckpt` | **ctool/cgen/cparam/mext** (mtool doesn't have it) | the sole compliant remedy for OOM (invariants §6). Works in both full-parameter and `--lora` mode. Measured on ro1: the fire head's double forward pass guarantees an OOM on 48G cards for q36/gptoss's long-sequence tiers, and adding this flag and relaunching on the same card fixes it. **Measured on z1 (2026-08-10): gptoss trajectories' ctool/cgen, without fire-head, even with default hyperparameters, OOM directly on a 48G A6000**: at the time cgen didn't have this flag yet, and the only option was switching to a bigger H100/H200 card (`launch --refire` with a different `--piece` is enough); since np821 all three causal cells have this flag, and the remedy changed to adding the flag first |
| `--gen-eval` / `--gen-bs` / `--gen-eval-at` | cgen/cparam only (`train_causal_share.py`, since 2026-08-28, spec 16.3, ticket 08) | `--gen-eval N` is the number of rows of extra generative evaluation done during training evaluation, defaults to `200` (0 turns it off); `--gen-bs` is the generation batch size, defaults to `8`; `--gen-eval-at {all,last}` defaults to `last` (only generates at the evaluation where `frac==E`, i.e. the end of the epoch), `all` generates at every evaluation point. When it's on, the `eval` log gains the three keys `val_exact_call` (cgen)/`val_exact_params` (cparam), `gen_n`, `gen_s` (not written when `--gen-eval 0` or not at that evaluation point); best selection still only looks at `val_ce` (decision 28, unchanged) |
| `--align-tok-tol` / `--align-bf16-mean-tol` / `--align-bf16-max-tol` / `--align-baseline-factor` | cgen/cparam only (`train_causal_share.py`, since 2026-08-28) | the four alignment coarse-screening thresholds that used to be hard-coded module constants were all turned into parameters, and their default values are exactly the old constants: `3e-4` / `2e-2` / `1e-1` / `3.0` respectively; the same-named constants at the top of the module have been removed, the parameter defaults are the sole source of truth |
| `--align-rule` / `--align-rel-tol` | both ctool and cgen/cparam have them (ctool only has these two new flags, not the four coarse-screening thresholds above) | `--align-rule {abs,rel,both}` defaults to `abs` (the status quo, absolute per-row/per-token difference, ctool is `max(d_h, d_l) < tol`); `rel` judges the relative difference: for cgen/cparam it's `rel_max_abs_diff = max_abs_diff / mean(|ce_ref|) <= --align-rel-tol`, for ctool it's `reldiff_hidden <= tol and reldiff_logits <= tol` (ctool already computed these two quantities before, they were just "diagnostic, not part of the judgment", now they're wired into the criterion); `both` requires both to hold. `--align-rel-tol` defaults to `1e-5` (on both sides). `ALIGN_CHECK.json` always writes the full set of new keys like `rule`/`rel_tol`, existing keys are unchanged |
| `--mem-probe-pick` | cgen/cparam only, paired with `--mem-probe` (spec 16.5, ticket 10) | `{tokens,cost,loop}`, defaults to `cost`. `tokens` = the status quo, pick the fullest block plus the longest event by token count across the whole set, build the state first and then do two backward passes in a row; `cost` = enumerate all epoch-0 physical blocks only among the events sampled for this run, and pick three blocks by "largest token count" / "largest loss-position count" / "the largest sum after each is divided by its global maximum" (a repeated block only runs once), taking the largest of the three peaks; `loop` = for each of the three blocks `cost` picked, find the update group it belongs to (the same group only runs once), run one update per group as-is (`opt.step()` with lr set to 0, followed by `opt.state.clear()`), one `mem_probe` entry per group (`group_of` records which blocks this group was run for), and take the larger of the groups' peaks (decision 32: only running the group containing the block with the most loss positions comes in about 6% below the true peak on a configuration without checkpointing on). The three methods share the skeleton "build state → reset the peak → run → read the peak → clear the state, restore lr, clear the gradient", and each writes one `mem_probe_summary` entry at the end (fields `pick, worst_gb, worst_kind, scope, n_events_considered`, `loop` additionally has `worst_group_of`); `scope` = `full` (`tokens`, measuring the whole set) or `run` (`cost`/`loop`, only measuring the events sampled for this run; under `--smoke`/`--max-events` this is a small sample and can't be used to assign cards for the full volume, spec 16.10 #36) |
| `--overlong` | the three eval scripts (`eval_causal_call.py`/`eval_causal_param.py`/`eval_tool.py`, spec 16.2, ticket 07) | `{left,skip,drop-event}`, defaults to `left`. `left` = the status quo, the prompt/full text is still left-truncated when overlong: cgen/cparam record `n_left_truncated` (cparam computes it against the maximum length `L(k)` of the two prompts, gt_tool/pred_tool, and additionally records `n_left_truncated_by_tag`), ctool records zero logits for out-of-window boundaries and counts `n_oow`; `skip` = an overlong sample itself doesn't enter any denominator: cgen/cparam record `n_skipped_rows`, ctool records `n_skipped_bounds`; `drop-event` = if an event's full-text token count exceeds `max_len`, the whole event isn't scored: cgen/cparam record `n_dropped_events` (plus `n_excluded_by_ctool`, recording events with no trigger-point candidate left after ctool strips its candidate rows), ctool records `n_dropped_events` and `n_dropped_bounds`. Only takes effect for `eval_tool.py --head causal`; passing anything other than `left` to `--head mbert` is an outright `SystemExit` (the mbert report's `overlong_mode` always writes `left`). Every report writes `overlong_mode` and the corresponding counts (writes 0 for something that didn't happen, the key is never omitted); the two reports (ctool and cgen/cparam) each record their own `overlong_mode`, and whoever reads them needs to look at both together (extending §5 #28) |

Everything else uses the defaults (the two mbert cells are still `--max-len 4096 --bs 8 --accum 4 --lr 2e-5 --epochs 3`; the three causal cells switched to a new convention since 2026-08-28: the same ceiling `--max-len 8192` for all three cells (an overlong event is dropped whole, no longer truncated, so the three cells' training event sets don't fork): ctool `--bs 2 --accum 4 --lr 1e-5 --epochs 3`, cgen/cparam (the new trainer) `--events-per-mb 4 --accum 2 --lr 1e-5 --epochs 1 --tok-budget 16384`, with lr switched to 2e-4 when `--lora` is on. **The np821 batch used `--max-len 4096`, the three causal cells used `--bs 4 --accum 8`, `--epochs 3`**). None of c1's 12 training runs touched any hyperparameter except ctool's `--align-tol`; np821's four batches likewise only touched the three flags `--base` / `--lora` / `--grad-ckpt`; the new convention starting with `ks828` is in this section's newly added parameter rows and the real `train_causal_share.py` commands below.

**Output**:
- mtool → `<out>/best/` (HF weights + tokenizer + `label_map.json`) + `train_log.jsonl`
- mext → `<out>/best/{model.pt (a bare state_dict, not an HF directory), tokenizer, meta.json}` + `train_log.jsonl`
- ctool → `<out>/ALIGN_CHECK.json` + `<out>/best/{HF backbone, tokenizer, head.pt, label_map.json, meta.json}` + `train_log.jsonl`
- cgen → `<out>/ALIGN_CHECK.json` + `<out>/best/` (HF weights + tokenizer + `meta.json`, containing `call_sep`) + `train_log.jsonl`
- cparam → `<out>/ALIGN_CHECK.json` + `<out>/best/` (HF weights + tokenizer + `meta.json`, containing `call_sep` and `param_only: true`) + `train_log.jsonl`
- `sweep-lr plan --write` → `<the json written>` (9 fields per entry); `sweep-lr report --out` → `SWEEP_REPORT.json/.md` (since 2026-08-28, spec 16.6)
- when a cell has `--mem-probe` on, `train_log.jsonl` gains `mem_probe` entries (one per block/group) and one `mem_probe_summary` wrap-up event (since 2026-08-28, spec 16.5, fields in the `--mem-probe-pick` row of the §3 parameter table)
- the three eval scripts' reports (`REPLAY_REPORT.json`/`CALLGEN_REPORT.json`/`PARAM_REPORT.json` and the corresponding `.md`) all gain `overlong_mode` and the corresponding count keys (since 2026-08-28, spec 16.2, fields in the `--overlong` row of the §3 parameter table)

**Exit code**: ctool's and cgen/cparam's alignment checks both `sys.exit(2)` on FAIL, with different criteria for the two (ctool compares the whole-segment forward pass against the per-token incremental forward pass's hidden states and logits, tolerance 3e-4; cgen/cparam compare per-row ce against the old row-by-row trainer, per-row 2e-5, per-token 3e-4). `ALIGN_CHECK.json` is written to disk regardless of pass or fail; read its reldiff to decide whether to loosen the tolerance or check the version. `share_data.load_events`'s two hard stops (zero rows loaded, or cparam's stripping failure rate exceeding 5%) are non-zero `SystemExit`.

**`train_causal_share.py`'s real commands** (cgen/cparam's current trainer, since 2026-08-28; `run.py`'s `train-cgen`/`train-cparam` are exactly this command assembled, with `--mode` carried by the registry):

```bash
# CPU smoke (actually run in ticket 03's report, artifact 0.6B fp32 best/ about 2.4 GB, must not be written to /tmp or home)
cprobe-env/bin/python pipeline/train/train_causal_share.py --mode cgen \
  --data pipeline/data/nyapass_aw_v1/gptoss --out pipeline/runs/smoke/share_cpu_cgen_smoke \
  --device cpu --smoke --max-events 6 --log-every 1 --align-events 2 --base qwen --force
# cparam is the same command with --mode cparam --out .../share_cpu_cparam_smoke

# GPU smoke tier (launch_probe automatically appends --smoke; the shape run.py show train-cgen prints):
# /…/cprobe-env/bin/python /…/pipeline/train/train_causal_share.py --mode cgen '<args...>'
python3 run.py show train-cgen   # or train-cparam; --data/--out are assembled by launch_probe

# GPU speed/VRAM tier (spec section 10, tokyo108 H100, without --smoke)
cprobe-env/bin/python pipeline/train/train_causal_share.py --mode cgen \
  --data pipeline/data/nyapass_aw_v1/gptoss \
  --out pipeline/runs/smoke/ks828b06_gptoss_cgen_speed \
  --max-events 450 --log-every 3 --eval-per-epoch 1 --mem-probe \
  --tok-budget 16384 --base qwen --force
# also ran once more with --tok-budget 24576; the expandable_segments switch has been measured and is not adopted (see the --tok-budget row above)
```

**Learning-rate sweep** (`pipeline/train/sweep_lr.py`, spec 16.6, ticket 11; both subcommands are pure CPU, registered in `run.py` as `sweep-lr`, GPU launches still go through gpu-run):

```bash
# plan: produces 12 commands by the GRID constant (four configurations b06/b17/l17/l4 x three learning-rate anchors), writes a plan.json for the record
python3 run.py sweep-lr plan --write pipeline/runs/sweep/plan.json

# report: after the sweep finishes, collect a batch of run directories' train_log.jsonl into a table
python3 run.py sweep-lr report --runs pipeline/runs/sweep/ks828* \
  --out pipeline/runs/sweep
```

The 12 lines `plan` prints are commands of the form `python3 run.py launch --cmd ... --run-id ... --track kvshare-lr-sweep --outdir ...`, ending with a placeholder `--piece <host>:<gpus>`; the launcher swaps in the actual card from the placement table before launching; `report` produces `SWEEP_REPORT.json/.md`, grouped by configuration, sorted ascending by learning rate within each group, with the row of lowest `best_val_ce` in each group marked `*`. The artifact directory `pipeline/runs/sweep/` doesn't go into the matrix, doesn't go into `summarize_matrix.py` (run_id has four segments, `ks828<tag>_gptoss_cgen_lr<lr>`, one segment more than the three-segment `{batch}_{model}_{cell}` used by the cells currently in service, see §3.2).

### 3.1 Measured VRAM table (measured on np821: gpt-oss trajectories / `--max-len 4096` / `--bs 4 --accum 8`)

Check this table first when picking a card, don't guess from model size: **the watershed for whether it fits is whether `--grad-ckpt` is on, not how big the model is** (0.6B without gc has a higher peak than 1.7B with gc, by a factor of two).

| Batch configuration | ctool | cgen | cparam | Conclusion on a 48G card (47.51 GiB usable) |
|---|---|---|---|---|
| 0.6B full-parameter, **without** gc | 60.2 | 76.8 | 76.7 | **doesn't fit**, all three cells' smoke OOM (gates §3.10) |
| 1.7B full-parameter + gc | 35.4 | 44.1 | 44.1 | smoke gets through, **the full volume doesn't fit**: cgen's full volume OOMs on the very first backward pass (gates §3.9) |
| 1.7B LoRA + gc | 17.3 | 34.7 | 34.7 | fits, zero OOM, finishes |
| 4B LoRA + gc | 32.1 | 37.6 | 37.6 | fits, zero OOM, finishes |
| ctool 0.6B full-parameter, `--max-len 8192 × --bs 2` (ks828, the new default since 2026-08-28) | 56,859 MiB (H100, nvidia-smi sample) | N/A | N/A | the new convention, tokyo108's **H100**, not a 48G card. `--bs 4` under the same conditions OOM'd on the first training batch (the process at 92.94 GiB, decision 15, `ops/runs.jsonl`'s `ks828b06_gptoss_ctool_h100mem_bs2`) |
| cgen's new trainer (`train_causal_share.py`) `--tok-budget 16384` (ks828) | N/A | 60.59 GB allocated (H100, `torch.cuda.max_memory_allocated`) | N/A | the new convention, tokyo108's **H100**, not a 48G card. `--tok-budget 24576` had a peak of 80.91 GB and was 15% slower (`pipeline/runs/smoke/ks828b06_gptoss_cgen_speed*`) |

(Units are GiB, peak values, except the last two rows whose units are given in each cell.) Two ways to read this: (1) **if the smoke peak is within ~10% of the card's capacity, treat it as not fitting**: smoke only samples 500 instances, and doesn't hit the kind of long-sequence combination in the full volume's first batch, and the peak is set by the longest sequence in the batch; (2) the "reserved but unallocated" item in the error message is fragmentation (8.63 GiB in the np821 case), and the headroom needs a further discount on top of that. The last two rows are measurements of the new ks828 convention on H100, and are on a different axis from the four np821/48G rows above, they can't be compared side by side directly. (3) **cgen/cparam's new trainer's `--mem-probe` is a lower-bound estimate; assign cards using `mem_probe_summary.worst_gb × 1.1` with a further fragmentation discount on top** (since 2026-08-28, spec 16.5, ticket 10 wrap-up; `--mem-probe-pick` defaults to `cost`, the §3 parameter table has all three picking methods): in the 2026-08-28 final verification (the old convention, the `tokens` probe), the probe's fullest block came in 7.5% below the full run's step peak at the same budget (16384: 54.38 vs. 58.47 GB) and 5.8% below at another budget (24576: 76.47 vs. 80.91 GB), the `mem_probe` events of `ks828b06_gptoss_cgen_final_b16k` / `_final_b24k_probe`; this 1.1 only covers the gap between the already-allocated peaks, the discount from (2) for fragmentation is a separate layer, and both need to be applied. (4) **Check which commit a step peak was run under**: for a run with `--mem-probe` before commit 479aa4b, the first `step` entry's `peak_mem_gb` is the number from the probe's last block (the probe zeroes out before each block but not after it finishes, so in the second round of smoke the `gstep 1` of all five equals the probe's last block); from gstep 2 onward is training's own peak; from commit 479aa4b onward the probe zeroes out after returning, so the first entry is already training's own. (5) **For a LoRA configuration, additionally check that "the fixed items + the fp32 base's size" doesn't exceed the card's capacity**: every time the best version is saved, `save_merged`'s deepcopy temporarily puts one copy of the fp32 base onto the card (by that point the gradients and activations have already been released); l4 smoke's step 3 through 5, at 33.09 / 33.19 / 33.18 GB, are exactly this moment (16.25 fixed plus 16.09 for the 4B fp32), below the training peak of 33.7, so checking `worst_gb × 1.1` is enough here, but when placed on a 48G card, that moment's 49.8 against 51 leaves only 1.2 GB (design-attention 9.9); on the wall clock, one `save_merged` for 4B takes 126 to 149 seconds, and under a schedule where the learning rate decays to 0, each of the four evaluation points is very likely to set a new low, adding about 9 minutes to an l4 run.

### 3.2 The relationship between LoRA batches and full-parameter batches

`--lora` is not a new cell, it's a **training axis**: the same three cells (ctool/cgen/cparam), the same data, the same eval scripts, only how the base is trained changes. The run_id template has neither a base-tier segment nor a training-method segment, so **one batch runs only one `--base` tier + one training method**, with the tier and the method written into the batch prefix (np821's four batches `b06 / b17 / l17 / l4` = 0.6B full-parameter / 1.7B full-parameter / 1.7B LoRA / 4B LoRA). At launch time, `--base` / `--lora` / `--grad-ckpt` are always written **in the placement table's extra** (whichever argparse writes last wins); the driver **does not read** the `base`/`mode` fields in the batch config's `train.batches`, those two fields are just markers for humans to look at, the placement table is the source of truth.

**The new convention's batch prefix (since 2026-08-28) is `ks828` plus the tier-and-method segment**, shaped like np821's `b06/l17` segment, e.g. `ks828b06`, `ks828l17`, with a run_id example `ks828b06_gptoss_cgen`; smoke is written to `pipeline/runs/smoke/<run_id>_smoke`. **The `np821` prefix must not be used for a run under the new convention (after the implementation changed)**: the two conventions' dropping rule, ceiling, and update unit are all different, and mixing them into the same prefix would make people think the numbers are comparable when they aren't (extending §3.4).

**The learning-rate sweep's run_id has four segments** (`sweep_lr.py`, spec 16.6, ticket 11): `ks828<tag>_gptoss_cgen_lr<lr>` (`<tag>` is b06/b17/l17/l4, `<lr>` is shaped like `1e-5`), one segment more than the three-segment `{batch}_{model}_{cell}` used by cells currently in service; the artifacts land in `pipeline/runs/sweep/`, and **don't go into the matrix, don't go into `summarize_matrix.py`**: it's only used to choose each configuration's learning rate, it's not a cell meant to go into the MATRIX table.

---

## 4. eval

**What it does**: fits the temperature on val, sweeps the trigger threshold theta on val, then freezes it and runs once on test to produce the numbers; then evaluates the parameters/whole call at the trigger points.

### 4.1 Dependency order (must not be reversed)

1. **Evaluate the tool cell first** (currently ctool; also mtool before the m-line was retired): `eval_tool.py` produces `REPLAY_REPORT.json` and `logits_test.pt` / `logits_val.pt`. The tool cells are independent of each other and can run in parallel.
2. **Then evaluate the parameter/call cells**: `eval_mbert_call.py` consumes the **same model's mtool** report and logits; both `eval_causal_call.py` (cgen) and `eval_causal_param.py` (cparam) consume the **same model's ctool** report and logits. Crossing models will fail an assert.
3. **Finally, summarize**: `summarize_matrix.py` (pure CPU).

The first two steps occupy a card → **launch through the gpu-run skill, don't hand-roll ssh/nohup**.

### 4.2 Commands

```bash
cd /home/y-guo/reproduce/new1
R=pipeline/runs; D=pipeline/data/aw_official_v1

# Tool cells: the same eval_tool.py forks into two tasks by --head, the interpreter is chosen by the registry
# (the mbert head -> mbert-env; the causal head -> cprobe-env, since it has to import train_causal_tool.py)
python3 run.py eval-tool-mbert  --env <ENV> --run $R/<BATCH>_<MODEL>_mtool --data $D/<MODEL>
python3 run.py eval-tool-causal --env <ENV> --run $R/<BATCH>_<MODEL>_ctool --data $D/<MODEL>

# Parameter cells
python3 run.py eval-mcall --env <ENV> --run $R/<BATCH>_<MODEL>_mtool \
  --extractor $R/<BATCH>_<MODEL>_mext --data $D/<MODEL>
python3 run.py eval-ccall --env <ENV> --ctool-run $R/<BATCH>_<MODEL>_ctool \
  --cgen-run $R/<BATCH>_<MODEL>_cgen --data $D/<MODEL>
# cparam: runs both the gt_tool/pred_tool conventions on the same batch's ctool trigger points, the report is written into --cparam-run
python3 run.py eval-cparam --env <ENV> --ctool-run $R/<BATCH>_<MODEL>_ctool \
  --cparam-run $R/<BATCH>_<MODEL>_cparam --data $D/<MODEL>

# Summarize (pure CPU, run.py runs it directly; a cell missing a report is automatically marked PENDING, can be viewed while still running)
python3 run.py matrix --runs-dir $R --out $R/MATRIX_REPORT.md --prefix <BATCH>
python3 run.py matrix --runs-dir $R --out $R/MATRIX_REPORT_risk10.md --prefix <BATCH> --risk 0.1

# The "read-only + abstain" batch (since ro1): all four evals add --readonly-env <ENV> (must match the training side, the two-way fuse is in §4.4);
# the parameter cells can additionally add --self-fire to produce the self-fire block. ro1's actual run shape:
python3 run.py eval-tool-mbert --env bfcl --run $R/ro1bf_q35_mtool --data $D/q35 --readonly-env bfcl
python3 run.py eval-mcall --env bfcl --run $R/ro1bf_q35_mtool \
  --extractor $R/ro1bf_q35_mext --data $D/q35 --readonly-env bfcl --self-fire
python3 run.py eval-ccall --env bfcl --ctool-run $R/ro1bf_q35_ctool \
  --cgen-run $R/ro1bf_q35_cgen --data $D/q35 --readonly-env bfcl --self-fire
```

All five eval tasks are launch-type: `run.py` only prints the command, launching is handed to gpu-run, and the dirty-tree gate is enforced before the command is emitted
(even `run.py show <task>` goes through it; emitting the command is not a backdoor around the gate; to force it through on a dirty tree, add
`--allow-dirty`). `--head mbert` / `--head causal` are already fixed in the registry, **don't pass them by hand again**.
Launching the whole placement table at once goes through `python3 run.py launch-eval`: before launching the call tier it hard-checks whether the tool cell it depends on
has a `REPLAY_REPORT.json`, exiting if not, enforcing §4.1's dependency order; the eval-cell table's sole source of truth
is `run.py`'s `EVAL_CELLS` (cell → task name + the tool cell it depends on), and `ops/launch_eval.py`
only imports it. It likewise **automatically writes `RUNMETA.json` after a successful launch** (appends one commit + the actual command,
doesn't overwrite), but **the landing spot differs from §3, don't reuse that section's `--out` convention**: the tool tier writes into its `--run`
directory (= `<BATCH>_<MODEL>_<mtool|ctool>`), the call tier writes into **the head's own directory**
(the mext / cgen / cparam run, not the tool cell it depends on), with `kind` recording `eval_tool` / `eval_call` respectively.
The two tiers' RUNMETA landing spots are consistent with their own reports' landing spots (EXTRACT_REPORT is in the mext directory,
CALLGEN_REPORT is in the cgen directory, see the first item of §7). RUNMETA is written by the first step of `register_all`
(the sole writer, in the order RUNMETA→ledger→record); a `RUNMETA: <path>` line in the receipt means it was written;
if the ledger/record registration fails (e.g. a duplicate run_id), it only prints `WARN registration failed` without interrupting the launch, and RUNMETA
has already been saved to disk by that point. Only if the receipt shows `WARN RUNMETA not written (<directory>): <error>` does it need to be backfilled by hand with
`python3 run.py runmeta <directory> --cmd '<command>' --kind eval_tool|eval_call`.
(Before 2026-08-26 the receipt's line `WARN --outdir not given, RUNMETA not written` was a false alarm, already fixed, see the same explanation in §3.)

### 4.3 The `--risk` two-tier strategy

`eval_tool.py` fixedly sweeps 20 tiers of theta (0.5→0.975, step 0.025), and for each of `RISK_TARGETS = [0.10, 0.05]` picks the theta that "maximizes coverage subject to the trigger-accuracy constraint," writing it into `REPLAY_REPORT.json`'s `chosen_theta`. When the constraint is too tight, that tier is `null`. So the parameter cells follow this order:

1. Use the default `--risk 0.05` first;
2. if the report's `chosen_theta["0.05"]` is `null` → `eval_*_call.py` exits outright with `SystemExit` (exit 1), pass `--risk 0.1` instead and rerun;
3. if both tiers are `null` → this cell is judged **N/A**, and isn't retried again (the c1 batch's `q35_mtool` is exactly this case, both tiers null, which is why `c1_q35_mext` still has no EXTRACT_REPORT to this day).

### 4.4 Parameter table (only lists ones that change)

| flag | Script | Description |
|---|---|---|
| `--env` | all four evals | **required**, choices tales/appworld/bfcl; `eval_causal_call.py` and `eval_causal_param.py` use it to choose the call-parsing regex (appworld uses `apis.x.y(`, everything else uses `name(`) |
| `--head mbert\|causal` | eval_tool | defaults to mbert; causal goes through the backbone + head.pt path |
| `--cached-logits` | eval_tool | reads the already-saved `logits_*.pt`, skipping inference, pure CPU post-processing; use it when regenerating a report without occupying a card. **Since 2026-08-02 there is weight-fingerprint verification (audit B9)**: each `logits_<sp>.pt` is paired with a `logits_<sp>.meta.json`, recording the fingerprint of every weight file under `best/` (**size + a sha1 of the first and last 64KB, no mtime**, since a normal copy/restore shouldn't invalidate the cache) and the row count; running normally (without this flag) automatically writes/updates this fingerprint. With this flag on, two situations hard-exit: **missing `.meta.json`** (an old cache with no way to tell which weights it came from), **a fingerprint mismatch** (the weights have been retrained or overwritten, refusing to let old logits pass as the result of new weights). A fingerprint mismatch can only be resolved by dropping this flag and recomputing; **a missing fingerprint** (old logits produced before the fingerprint mechanism existed) has one more path, see the next row |
| `--adopt-logits-fingerprint` | eval_tool | **backfills logits produced before the fingerprint mechanism**, a separate one-off run: swap `--cached-logits` for this flag, keep the rest of the parameters as-is (`--env` / `--run` / `--data` are all still required); it writes a `.meta.json` for every existing `logits_<sp>.pt` under `--run` and then **returns and exits directly, without evaluating**. It's only allowed when the mtime of **every** weight file under `best/` is no newer than that logits, since that's the only way to prove "the current weights are the weights that produced these logits"; if the weights have been updated it SystemExits, suggesting dropping `--cached-logits` and recomputing. It also SystemExits if `best/` has not a single weight file (nothing to claim). Once backfilled, rerun the original command with `--cached-logits` |
| `--report-dir` | eval_tool | defaults to `--run`; point it elsewhere during acceptance/trial runs to avoid overwriting old artifacts |
| `--legacy-splits` | eval_tool | reads the old calA/calB/test three splits, only for historical acceptance, don't touch it for a new batch |
| `--risk` | the three calls | defaults to 0.05, see §4.3 |
| `--limit` | the three calls | truncates to the first N triggered events, used for smoke |
| `--device` | all four evals | defaults to cuda |
| `--bs` | **only the three call scripts have it** | defaults to 8. Warning: `eval_tool.py` **doesn't have this flag**: its batch size is a constant in the script: the mbert head goes through `score()`'s default `bs=16`, the causal head goes through `EVAL_BS = 4` (events per batch). Changing it can only be done by changing the code; passing `--bs` on the command line gets rejected by argparse |
| `--max-new-tokens` | **only eval_causal_param has it** | defaults to 96 (= `MAX_GEN_TOK`, copied from the ceiling used by the training-side generative evaluation); the token ceiling for greedy-generating the parameter segment |
| `--readonly-env` | all four evals | choices `appworld/bfcl`, not passed by default. When passed: the ground truth is folded, the trigger condition gains "argmax != the abstention sentinel", the parameter metric only counts triggered events whose ground truth is read-only; the eval_tool report gains a `readonly_stats` block, and `prior_baseline_event_acc` changes to taking the highest frequency **on the folded vocabulary** (a pitfall fixed by de1c781: taking it before folding would misprint bfcl's prior as 0.0). **Two-way fuse**: the run's `best/label_map.json` containing the sentinel <=> this flag must be passed; one without the other is a SystemExit |
| `--self-fire` | the two calls | self-fire evaluation: theta_fire is swept on val, frozen once on test, and the trigger point is set by the parameter cell's own fire head. **Must be passed together with `--readonly-env`** (the ready definition depends on the read-only ground-truth table), otherwise SystemExit. Requires the parameter cell to have been trained with `--fire-head`. Only adds the `self_fire` report block, not one old field is touched |
| `--fire-bs` | the two calls | the fire-scoring batch size, 0 = follow `--bs` |
| `--params` | the two calls | the parameter-label directory, defaults to `<data>/params`; self-fire uses it to compute the ready ground truth |

**Input / Output**:

| Script | Reads | Writes |
|---|---|---|
| eval_tool | `<DATA_ROOT>/{val,test}.jsonl` + `tool_vocab.json`; `<run>/best/label_map.json` (causal additionally reads `meta.json`, `head.pt`) | `<run>/logits_val.pt`, `<run>/logits_test.pt`, `<report-dir>/REPLAY_REPORT.{json,md}` |
| eval_mbert_call | `<run>/REPLAY_REPORT.json` + `logits_test.pt` + `best/label_map.json`; `<DATA_ROOT>/test.jsonl` + `router_stats.md`; `<DATA_ROOT>/params/test.jsonl`; `<extractor>/best/` | `<extractor>/EXTRACT_REPORT.{json,md}` |
| eval_causal_call | `<ctool-run>/REPLAY_REPORT.json` + `logits_test.pt` + `best/label_map.json` + `best/meta.json`; `<DATA_ROOT>/test.jsonl`; `<cgen-run>/best/` (`call_sep` is read from its meta.json, not hard-coded) | `<cgen-run>/CALLGEN_REPORT.{json,md}` |
| eval_causal_param | `<ctool-run>/REPLAY_REPORT.json` + `logits_test.pt` + `best/label_map.json` + `best/meta.json`; `<DATA_ROOT>/test.jsonl`; `<cparam-run>/best/` (`call_sep` likewise read from meta.json) | `<cparam-run>/PARAM_REPORT.{json,md}` (the matrix only reads its `pred_tool` block) |
| summarize_matrix | each run's `REPLAY_REPORT.json` (mtool/ctool), `EXTRACT_REPORT.json` (mext), `CALLGEN_REPORT.json` (cgen), `PARAM_REPORT.json` (cparam, taking the `pred_tool` block) | the .md pointed to by `--out`, also printed to stdout |

**Exit code**: eval_tool's normal path has no explicit non-zero exit; under `--cached-logits` there are three hard exits: missing `logits_<sp>.meta.json`, a weight-fingerprint mismatch (both are SystemExit, see this row of §4.4), and the logits row count not matching the data row count (an assert exits 1, meaning `--data` and this evaluation come from different sources). Additionally, if `best/` has not a single weight file, a fingerprint can't be built, also SystemExit. The three call scripts: theta being null at that risk tier → `SystemExit` exits 1. `eval_causal_call` and `eval_causal_param` each additionally have an assert guarding against the call-splitting convention drifting from `annotate/rules.py`, plus three cell fuses (all SystemExit, exit 1): `eval_causal_param` requires the head run's meta to carry `param_only: true`, `eval_causal_call` conversely refuses a run carrying `param_only` (a cparam run was only ever trained to write the parameter segment, and feeding it in would make scoring collapse entirely without an error); both scripts do a **three-way data cross-check**: the head run's meta.data, the `--data` argument, and `--ctool-run`'s meta.data, resolved and hard-stopped if inconsistent (guarding against cross-feeding when two base tiers run in parallel). summarize_matrix always returns 0.

### 4.5 Time-cost reference (measured on np821, use this to estimate when scheduling eval shifts)

**First look carefully at what each script counts by, then multiply**: the dataset's row count (cut-point samples) and the event count are two things whose magnitude differs by several dozen times; np821's test split has 8533 events, 391893 sample rows, and extrapolating from the row count would estimate a 40-minute job as two or three hours.

| Who | Counting unit (this is exactly the heartbeat's `total`) | Measured quantity on np821 | Wall-clock per cell |
|---|---|---|---|
| `eval_tool` (the ctool tier) | events: dev in full first, then test in full; within each event it scores **every cut point** (the heartbeat's `total` is the event count during the dev segment and switches to the cut-point row count during the test segment, don't treat "events/second" as a stable unit) | dev 2556 + test 8533 events (= dev 115211 + test 391893 cut points) | **36-38 minutes** on H100 for the 0.6B/1.7B base, **about 45 minutes** on H200 for the 4B base (first-to-last heartbeat span; np821's four batches actually measured 35.7 / 37.6 / 38.0 / 44.8; the ledger window, including weight loading and post-processing, is 39-48 minutes) |
| `eval_causal_call` / `eval_causal_param` (the call tier) | **test events triggered by theta**, generated greedily one by one | that batch's `REPLAY_REPORT.json`'s test trigger count (np821's four batches fall in the range 2192-2806) | **21-26 minutes** (heartbeat span; ledger window 23-28 minutes). cparam internally runs gt_tool / pred_tool twice, but the wall-clock is still on the same order as cgen |

Two conclusions: (1) **the call tier's cost only tracks the triggered-event count**, unrelated to how many sample rows the dataset has: the higher theta is, the fewer triggers and the faster it runs, so when estimating time for a different batch, first look at that batch's `REPLAY_REPORT.json`'s `chosen_theta` and trigger count, don't copy another batch's minute figures; (2) the ctool tier's cost tracks the **cut-point row count**, and multiplies right along with however many times the dataset's samples multiply (np821's data is about 4x p1's, and ctool's evaluation grew from 11-14 minutes to 39-48 minutes). See gpu-run's `references/launch-methodology.md` for how to estimate the hardware side.

---

## 5. inject

**What it does**: proves that this set of weights can still be loaded and scored in a different process. **Running through successfully is itself the credential**, this is not an accuracy evaluation. It should be run once at the smoke stage already.

```bash
cd /home/y-guo/reproduce/new1
# The mbert head (mtool/mext artifacts); the registry already carries --head mbert --device cpu, run.py runs it directly, no card occupied
python3 run.py check-bundle-mbert --run pipeline/runs/<BATCH>_<MODEL>_mtool --data <DATA_ROOT>
# The causal head (ctool artifact); the registry already carries --head causal, defaults to cuda
python3 run.py check-bundle-causal --run pipeline/runs/<BATCH>_<MODEL>_ctool --data <DATA_ROOT>
```

Warning: the two run differently: `check-bundle-mbert` is a CPU task, run.py runs it to completion on the spot and produces a result;
`check-bundle-causal` is marked `gpu=True` in the registry, and run.py **only prints the command** for gpu-run to handle:
the handoff is decided by the task, and adding `--device cpu` still only gets it printed, it won't execute on the spot.

| flag | Required | Description |
|---|---|---|
| `--run` / `--data` / `--head` | yes | head in mbert/causal |
| `--device` | no | defaults to cuda, give `cpu` for zero-card verification |
| `--dtype` | no | defaults to auto = bfloat16 on cuda / float32 on cpu |
| `--index` | no | defaults to 0, which row of test.jsonl to take |
| `--temperature` | no | overrides REPLAY_REPORT.json's temperature |

**Input**: `<run>/best/` (label_map.json + weights + tokenizer, causal additionally needs `head.pt`), `<DATA_ROOT>/test.jsonl`; `<run>/REPLAY_REPORT.json` **can be missing**: if missing, it goes with T=1.0 and theta recorded as N/A, this path is designed specifically for "smoke just finished, not evaluated yet."
**Output**: `<run>/BUNDLE_CHECK.txt` (content also printed to stdout): predicted tool / confidence / whether theta is exceeded / ground truth / top5 / loading and forward-pass time cost.
**Exit code**: 0; if `test.jsonl` has no entry at `--index` → SystemExit exits 1.

---

## 6. A batch's complete command sequence

From zero to the matrix table. `(CPU)` = runs directly without occupying a card, `(GPU)` = **launch through the gpu-run skill, don't hand-roll ssh/nohup**.

Since 2026-08-22, the np821-series batches have had a resumable driver that programmatizes this S1-S11 sequence:
`python3 run.py pipeline --config pipeline/configs/<batch>.json`; each invocation advances
one step, and if a gate fails it stops in place and writes the reason into `logs/pipeline/<run_family>/state.json`;
the table below is still the source of truth for each step, and if the driver breaks, run it by hand following the table.

**The driver's two kinds of completion criteria decide how far it can be mixed with hand-launching** (measured on np821):

- **The training stage `t2_full` recognizes launch markers**: each invocation **only launches one batch**, the four batches are **strictly serial**
  (taking the first unfinished one in the order of `train.batches` in the config); a launched batch keeps a
  `launched` marker in state.json, and invoking it again after that only waits, never relaunches. To parallelize across batches,
  **hand-launch the rest yourself with `run.py launch-probe full --batch <batch>`** (the same registration code path,
  the ledger/record/RUNMETA all just as complete); the driver doesn't recognize a hand-launched batch's launch marker, but its completion criterion is
  `best/` existing plus `train_log` having `event=done`, so once it finishes running, the driver lets it through all the same.
  Warning: invoking `t2_full` again on a **partially completed** batch (e.g. deleting the marker wanting to fill in one cell) relaunches the whole placement
  table: the already-finished cells get instantly rejected by the guard, but it has already backfilled a fake RUNMETA and stuffed the run_id back into the active ledger
  (`driver.py`'s `step_t2_full` docstring records this scenario). To fill in one cell, follow §3's
  "a temporary placement table containing only that cell."
- **The eval stage `e1_tool` / `e2_call` / `m1_matrix`'s completion criterion is only the artifact files**: each batch's
  ctool `REPLAY_REPORT.json`, cgen's `CALLGEN_REPORT.json`, cparam's
  `PARAM_REPORT.json`, `MATRIX_<batch>_r{0.05,0.1}.md`; the launch marker is only used to block **the batch it itself
  already launched**, it doesn't participate in judging completion, and it has no bearing on a hand-launched task either. The upside is that
  when training isn't all complete yet, `run.py launch-eval` can directly evaluate the batches that have finished training first, and once the report lands,
  when the driver invokes that step it will directly recognize it as complete (SKILL.md C4's "wrap up each cell and dispatch its eval as it finishes").
  The cost is two pitfalls, each paired with a gate: a hand-launched eval **must not have the driver invoked while it's still in flight** (the report hasn't landed yet,
  and there's no launch marker either → `e2_call` launches that batch again, **G23**); the matrix for a batch **must not be produced before that batch's call-tier
  reports are all in** (`m1_matrix` skips as soon as it sees the file already exists, and a prematurely produced PENDING table will
  stay around forever, **G24**).

```
S1 (CPU)  run.py gen-launch --config manifest_<BATCH>.json --dry-run --out-override /tmp/... -> look at the manifest
S2 (CPU)  run.py gen-launch --config manifest_<BATCH>.json                -> envs/runs/<BATCH>/
S3 (GPU)  launch_servers.py -> smoke 1 task per model -> launch_clients.sh       * collect, takes the longest
          (these two are gen-launch's generated artifacts, a one-off launcher doesn't go into the registry)
S4 (CPU)  run.py ann-build  --config configs/<BATCH>_<MODEL>.json         <- wait for S3's trajectories to all land
S5 (CPU)  run.py ann-params --config the same config                     <- wait for S4's jsonl
          (S4+S5+check can also be one command, run.py recipe annotate-chain --set config=...)
S6 (GPU)  run.py train-<cell> ... --smoke, artifact goes into pipeline/runs/smoke/       <- wait for S5
S7 (CPU)  run.py check-bundle-mbert run once against the smoke artifact    <- wait for S6
S8 (GPU)  run.py train-<cell> full volume for each cell (or run.py launch-probe for the whole placement table at once)     <- wait for S7 to pass
S9 (GPU)  run.py eval-tool-mbert / eval-tool-causal x 6                   <- wait for S8's corresponding cell to finish training
S10(GPU)  run.py eval-mcall (consumes same model's mtool) / eval-ccall (consumes same model's ctool) <- wait for S9
          (S9+S10 launched together via run.py launch-eval for the whole placement table, which enforces the dependency order)
S11(CPU)  run.py matrix produces the 0.05 and 0.1 tier tables             <- can run anytime, missing ones marked PENDING
```

Parallel/serial:
- **S4/S5 are independent per model**, the three models can run in parallel (pure CPU, not competing for resources); within the same model, S5 must wait for S4.
- **S8's four cells x three models = 12 runs, all in parallel**, limited only by card count (the c1 batch: tokyo105's eight cards + tokyo106's four cards).
- **S9's six run in parallel**; S10 must wait for the corresponding S9, since it needs to read the temperature/theta from `REPLAY_REPORT.json` and `logits_test.pt`.
- S11 can run at any time, and an incomplete run just produces a table carrying PENDING.
- Commit before every GPU launch (the HEAD stored in the record can only be traced back to the real code when the working tree is clean; run.py enforces this as a **hard gate** for launch-type tasks, a dirty tree refuses to emit the command outright, and `show` is blocked the same way, only `--allow-dirty` lets it through). **launch writes all three places automatically; the hand-rolled/register backfill path still exists, missing it still counts as a violation**: once `python3 run.py launch <task> ...` (a single task) or `launch-probe`/`launch-eval` (batch placement) launches successfully, it automatically completes all three, the ledger registration + `record.py start` + `<out>/RUNMETA.json`; a hand-rolled launch (an old script not wired into launch) needs to backfill `python3 run.py gpu-jobs register ...` + `python3 run.py record start ...` + `python3 run.py runmeta <outdir> --cmd '<command>'` itself, and run `finish` once for each at wrap-up.

---

## 7. Interface traps

- **The write direction of artifacts is asymmetric**: `eval_tool.py`'s `logits_*.pt` is always written into `--run` (`--report-dir` only changes the report); `eval_mbert_call.py`'s report is written into `--extractor` rather than `--run`; `eval_causal_call.py`'s report is written into `--cgen-run` rather than `--ctool-run`. → looking for EXTRACT_REPORT in the mtool directory finds nothing.
- **`train_log.jsonl` is in append mode** (consistent across every training script): rerunning into the same `--out` continues writing after the old log, it doesn't clear it. → before reading the log to compute epochs/time cost, first confirm there's only one `event=start` segment, otherwise the numbers are a mixture of two runs. **This pitfall was closed since 2026-08-02**: before starting training, each cell checks whether `--out` already has a `train_log.jsonl`, and if it does and `--force` wasn't passed, it SystemExits (see the `--force` row in §3); so now a mixed log can only appear with an explicit `--force`, and reading two `event=start` segments means someone added `--force`.
- **`--env` is only a log label in the training scripts**, the data path is entirely decided by `--data`; but in the three eval scripts `--env` is required and **affects scoring** (choosing the call-parsing regex). → getting it wrong at training time is harmless, getting it wrong at eval time makes the tool name judged wrong across the board.
- **Three base tiers (since 2026-08-21)**: ctool's `--base` is required (the registry carries `qwen`), cgen/cparam default to `qwen`; each of the three scripts has its own copy of an isomorphic `MODELS` table (qwen/qwen17/qwen4), **there is no single source of truth, adding a tier requires changing three places**. Switching tiers at launch time goes through the placement table's extra (whichever argparse writes last wins).
- **eval_causal_param.py's report is written into `--cparam-run`** (PARAM_REPORT.{json,md}); it carries a cell fuse: `best/meta.json` lacking `param_only: true` (e.g. accidentally feeding it a cgen run) is an outright SystemExit; cparam's prompt already carries the tool name, so feeding it a cgen run would write the tool name twice and silently deform the numbers, hence the hard stop. The matrix only reads its **pred_tool block** (system B's convention), the gt_tool block only goes into the report.
- **gen_launch's gpt-oss client preset has been configurable since 2026-08-21**: the manifest's optional top-level field `gptoss_client_preset`, defaulting to `default` (the convention currently in service across the whole line); if a name is given it validates that `configs/presets/<name>.json` exists, exiting with 2 if the file is missing.
- **launch_probe's smoke tier `--gpus` default has been `0,1,2` since 2026-08-21**: the count must equal `CELL_ORDER`'s length (currently three cells), giving four exits with 1.
- **mext's weights are a bare state_dict at `best/model.pt`**, not an HF directory, and can't be read directly with `from_pretrained`. → reusing it must go through `train_mbert_extract.load_extractor()`.
- **`eval_tool` with `--head causal` imports `pipeline/train/train_causal_tool.py`**, so it must be run with cprobe-env; running the causal head with mbert-env will crash at the import or the loading step.
- **For the two call scripts, theta being null is a hard failure** (exit 1), not a skip. → a batch eval script needs to catch this exit code and drop down to `--risk 0.1`, otherwise the whole batch gets interrupted. **Exception**: with `--self-fire` on, theta being null doesn't exit 1: the old-mode block gets skipped entirely, only the `self_fire` block comes out with one line printed as a notice; don't mistake "it finished running" for "the old convention has numbers too."
- **`--self-fire` is bound to `--readonly-env`** (missing either one is a SystemExit); `--readonly-env` is itself two-way bound to the sentinel in label_map (a run carrying the sentinel with the flag not passed, or a run not carrying the sentinel with the flag passed, both hard-stop). → when troubleshooting this kind of SystemExit, first check whether `best/label_map.json`'s last entry is `<NON_READONLY>`, then check the command line, don't go digging through the data.
- **`build.py` has zero tolerance for "a unit not in the official task list"** (exit 1). → when changing environments (appworld→bfcl→alfworld), the task-list file's naming and the task_id format must be aligned first, otherwise the very first step errors out across the board.
- **`gen_launch.py` forces `outdir = <env>_<model_key>`** (`env` is taken from the manifest's top-level `env` field, defaulting to `appworld`; so an appworld batch is `appworld_q35`, an alfworld batch is `alfworld_q36`), a custom name only gets WARNed and changed; downstream event extraction recognizes the model by the directory-name tail, and `MODEL_OF` only recognizes q35/q36/gptoss (`annotate/rules.py`'s `MODEL_OF` constant). → a new model must first have a line added to this table, otherwise the collected trajectories get silently skipped.
- **`--smoke` doesn't change `--out`**: passing the same `--out` for smoke and the full volume would let the smoke weights occupy `best/`. → follow `ops/launch_probe.py:71`'s approach, smoke always writes to `pipeline/runs/smoke/<rid>_smoke`. **This has been hard-blocked since 2026-08-02**: every cell now has `--force`, and without it, if `--out` already has a `train_log.jsonl`, it refuses to start training (see the `--force` row in §3), so "smoke occupying the real directory" now exits on the spot instead of silently mixing artifacts.
- **`ann-build`'s two knobs override the config via the CLI** (since 2026-08-22): `--weight-mode`/`--max-bounds`, when given explicitly, override the `weight_mode`/`max_bounds` fields in the config; `weight_mode` **defaults to the new convention, uniform**, so rerunning an old config without adding the flag gets equal-weight data, not the old w=1/m; reproducing an old artifact requires an explicit `--weight-mode per_event`. The report's four new statistics only appear when the config carries the `trajs_per_unit` key, don't use a config carrying this key to do a byte-for-byte reproduction.
- **Gate B's criterion follows `trajs_per_unit`** (since 2026-08-22): with the default K=1, the wording is byte-for-byte identical to the old version; with K>1, a unit must have exactly K traj **and** the filename's trailing sampling index `_r0..r{K-1}` must all be present, missing even one (some trajectory produced not a single usable event) also hard-stops it, which is not the same thing as deviation 2's "missing task." → an accidental K-fold re-scan hits the `(event, sent_idx)` uniqueness criterion first, the index criterion is the second line of defense.
- **A multi-sample trajectory filename carries the `_r<k>` suffix** (`appworld_<tid>_r0.jsonl`…, since 2026-08-22, with `--traj-per-task 1` there's no suffix = the old name): both `build.py`/`param_label.py`'s glob can handle it; but `pipeline/inject/replay_inject.py:399` and `pipeline/inject/score_live.py:119` still look things up by `appworld_<unit>.jsonl`, and need to be made compatible before ingesting a multi-sample batch (recorded in the WORKPLAN write-back checklist).
- **The presets `default` and `gptoss_default` are two different files**: `default` is the convention currently in service across the whole line (harmony/high/temperature 1/top_p 1/max_tokens 8192, with a server section tokyo108:8103, gpu-memory-utilization 0.92, launched directly by `serve_preset.py`), `gptoss_default` is OpenAI's official recommended convention (effort medium, server section max_model_len 131072). Getting one character of the manifest's `gptoss_client_preset` wrong changes the convention; check the preset name in `MANIFEST.md` before launching. When the four collectors omit `--base-url`/`--model`, the endpoint and model name are taken from the preset's server section (`default`'s is `gpt-oss-120b` at `http://tokyo108:8103/v1`), so leaving these two items out of the command still hits that service on tokyo108.
- **The driver `run.py pipeline` has no `--allow-dirty`**: a launch step hitting a dirty tree only gets blocked (the reason lands in `logs/pipeline/<run_family>/state.json`), commit clean and invoke it again; exit code 3 only means it genuinely launched this time, invoking it again on a batch that's already launched but not yet finished returns 0 (waiting, not relaunching), 0 also covers advancing one step and being fully complete, 4 = waiting for a ruling (the a1 cut-point stopping point, write `max_bounds` into the batch config and invoke it again), 1 = a gate failed. The state file has a `launched` launch marker (printed by `--status`; to confirm a batch is dead and needs relaunching, first delete that marker from the state file) and `manifest_sha1` (if the manifest was changed again after c1 generated it → c2/c5 are blocked, `gen-launch --force` regenerates and updates this field). The state file is in the git-ignored zone, `--status` only reads it, never changes it.
- **`--mode` is a required flag for `train_causal_share.py`** (since 2026-08-28, the cgen/cparam trainer currently in service): not passing it is an argparse error exit, not a guess at a default cell. `run.py`'s `train-cgen`/`train-cparam` already carry it in `CELLS`/`TASKS` (`["--mode", "cgen"]`/`["--mode", "cparam"]`), only a hand-rolled command needs to add it itself.
- **`train-cgen-rows`/`train-cparam-rows` are a reference, not what's currently in service**: these two tasks point at the old row-by-row scripts `train_causal_callgen.py`/`train_causal_param.py` (the old convention frozen unchanged: 4096, left truncation, 3 epochs), used only for alignment checks and comparison, their artifacts don't go into the matrix, and `best/meta.json` has no `trainer` field; the run_id shape is the same as the current `train-cgen`/`train-cparam`, and taking it to eval would mix it into the matrix with no way to tell it apart (extending §5 #26), the run_id must not use the current batch prefix.
- **A single event that exceeds the `--tok-budget` forms its own block**: when `chunk_by_budget` greedily packs blocks, if an event's own concatenated sequence length already exceeds `--tok-budget`, it is neither rejected nor truncated, it instead occupies one physical block by itself (this block is allowed to exceed the budget). → for a dataset with many long events, `peak_mem_gb` can't be estimated by `--tok-budget` alone, look at the `worst_gb` in the `mem_probe_summary` entry that `--mem-probe` writes at wrap-up (since 2026-08-28, spec 16.5; with `scope=full`, the probe finds the fullest block/longest event across the whole set, which can represent the full volume; with `scope=run`, it only finds one among the events sampled for this run, and under `--smoke`/`--max-events` this is a small sample and can't be used to assign cards for the full volume, spec 16.10 #36).
