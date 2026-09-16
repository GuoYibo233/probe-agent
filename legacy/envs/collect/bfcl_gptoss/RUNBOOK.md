# bfcl_gptoss top-up collection runbook (2026-07-30)

> 2026-08-20 gen-preset rework: the handler's max_tokens/effort/temperature all
> come from one preset's client block (taking whichever values in it are not
> null). The environment variable
> `NEW1_PRESET_JSON=<absolute path to some file in configs/presets/>` points at
> this preset; when the environment variable is absent, the handler reads the
> repo root's `configs/presets/default.json`, which is api chat (the handler
> fixes the endpoint itself), effort high, max_tokens 8192, top_p 1.0,
> temperature 1.0. To run the BFCL line's setting of 16384 plus BFCL's own
> built-in temperature, point `NEW1_PRESET_JSON` at
> `configs/presets/gptoss_bfcl_high.json`.

All code is ready (the handler is installed into the venv and registered,
commit 6fc03f3); this session is blocked by permissions from launching over
ssh, so execute the steps below via gpu-runner or by hand. Every step is
idempotent, and a break can be resumed from that step.

## 1. Launch the service (tokyo108 H100 g0, probe live at launch time to confirm it is still free)

```bash
python3 /home/y-guo/reproduce/new1/envs/serve_logs/launch_vllm_bfcl_gptoss.py
```

Readiness check (the 120B loads from NFS in roughly 5-10 minutes):

```bash
curl -s http://tokyo108:8103/v1/models | grep gpt-oss-120b
```

## 2. Smoke: a single task, end to end

The proper entry point is `python3 run.py collect-bfcl <bfcl's arguments...>`
-- `cwd=envs/bfcl` and `BFCL_PROJECT_ROOT` are carried by the registry, no need
to cd and export yourself; the two blocks below still write the raw
`venv/bin/bfcl` form, because `bfcl` is the console script in the venv, and
`collect-bfcl` is just its registered wrapper -- both run the same
executable (the two server-side environment variables
`LOCAL_SERVER_ENDPOINT` / `LOCAL_SERVER_PORT` still need to be given
yourself).

```bash
cd /home/y-guo/reproduce/new1/envs/bfcl
printf '{"multi_turn_base": ["multi_turn_base_0"]}\n' > test_case_ids_to_generate.json
BFCL_PROJECT_ROOT=$PWD LOCAL_SERVER_ENDPOINT=tokyo108 LOCAL_SERVER_PORT=8103 \
venv/bin/bfcl generate --model openai/gpt-oss-120b \
  --test-category multi_turn_base --run-ids --skip-server-setup \
  --local-model-path /net/tokyo100-10g/data/str01_01/y-guo/models/gpt-oss-120b \
  --num-threads 1 \
  --result-dir /home/y-guo/reproduce/new1/envs/runs/full_v2_topup/bfcl_gptoss
```

(--run-ids **replaces** the whole category with the ids file, confirmed by
reading the source, so this only runs this 1 task; the smoke run writes
straight to the final directory, and the full-scale continuation dedupes by
id and does not redo it. A single task at the high-thinking setting can take
on the order of 10 minutes.)

Acceptance (both must pass before continuing):

```bash
python3 - <<'EOF'
import json, glob
f = glob.glob("/home/y-guo/reproduce/new1/envs/runs/full_v2_topup/bfcl_gptoss/**/*multi_turn*result.json", recursive=True)[0]
e = json.loads(open(f).readline())
# The thinking is in the result entry's top-level reasoning_content field, shaped
# list[list[str]] (by turn, by step); the old script's approach of looking for
# role=assistant inside inference_log gets an empty list, a false negative
# (confirmed by measurement 2026-07-30)
rc = e.get("reasoning_content") or []
print("thinking char counts (by turn, by step):", [[len(s) for s in turn] for turn in rc][:10])
print("first-turn action:", str(e["result"][0])[:200])
EOF
```

- Thinking char counts are generally > 0 (the reasoning channel is working)
- The first-turn action is call text shaped like `[func(...)]` (the text
  protocol parses correctly)

If vLLM rejects the model name (404): when the server has no
served-model-name set, the model id is the weights path, which is the same as
--local-model-path, so it should in principle always match; if it really
errors, check the id returned by curl /v1/models, and either override with
REMOTE_OPENAI_BASE_URL or add --served-model-name to the launcher to align it.

## 3. Full-scale launch (200 tasks, tmux, this machine)

```bash
tmux new-session -d -s new1_topup_bfcl_gptoss bash -c '
cd /home/y-guo/reproduce/new1/envs/bfcl
LOCAL_SERVER_ENDPOINT=tokyo108 LOCAL_SERVER_PORT=8103 \
venv/bin/bfcl generate --model openai/gpt-oss-120b \
  --test-category multi_turn_base --skip-server-setup \
  --local-model-path /net/tokyo100-10g/data/str01_01/y-guo/models/gpt-oss-120b \
  --num-threads 4 \
  --result-dir /home/y-guo/reproduce/new1/envs/runs/full_v2_topup/bfcl_gptoss \
  2>&1 | tee /home/y-guo/reproduce/new1/envs/runs/full_v2_topup/logs/bfcl_gptoss.log'
```

## 4. Register in both ledgers

```bash
cd /home/y-guo/reproduce/new1
python3 run.py gpu-jobs register --name bfcl_gptoss_topup \
  --piece "tokyo108:0:new1_srv_gptoss_bfcl_t108g0:/home/y-guo/reproduce/new1/envs/serve_logs/new1_srv_gptoss_bfcl_t108g0.log" \
  --piece "$(hostname):-:new1_topup_bfcl_gptoss:/home/y-guo/reproduce/new1/envs/runs/full_v2_topup/logs/bfcl_gptoss.log"
python3 run.py record start --name bfcl_gptoss_topup --track collect \
  --cmd "bfcl generate --model openai/gpt-oss-120b --test-category multi_turn_base (via the chat endpoint, reasoning high)" \
  --host tokyo108 --gpu 0 --model gpt-oss-120b \
  --data envs/runs/full_v2_topup/bfcl_gptoss \
  --note "backfills the v1 gap: bfcl has no gpt-oss trajectories, and the cross-model bidirectional matrix needs it"
```

## 5. Wrap-up (once the batch has finished running)

- Completion criterion: result.json has all 200 ids (`python3 -c` counts the
  lines).
- Kill the service: ssh tokyo108 tmux kill-session
  new1_srv_gptoss_bfcl_t108g0, confirm g0 is back to zero with nvidia-smi.
- `python3 run.py gpu-jobs finish bfcl_gptoss_topup` +
  `python3 run.py record finish <run_id> --metric n_traj=200`.
- **The v3 dataset is missing this batch** (v3's database was built before
  this batch), so a v3.1 is needed:
  `python3 run.py build-dataset-legacy --runs envs/runs/full_v1 --runs envs/runs/full_v2_topup --out envs/bert_data/v3.1`
  (the cprobe interpreter is carried by the registry)
  Cross-model matrix experiments use v3.1 as the basis.
