# How each task performed on each card

This file is for an agent or a person who has to pick the card for a GPU task. It is read
together with `constants/cards.yaml`, which says which cards exist: per host, per card index,
the card's model and its memory in GiB. This file says how a task performed on a card type
when it ran there.

**Picking a card.** Take the smallest card type whose measured peak memory for that task fits
on the card with margin. A task with no row here is smoked with `--debug` on the card type the
nearest row suggests (same stage, the closest model, tuning and sizes), and the result of that
smoke is appended here as a new row.

**Maintaining the table.** After every GPU run that finished, or that failed for memory,
append the row for that task x card, or update the existing row: the date, the run key
(`<stage>-<key>`), the sizes (`debug` or the full sizes), the peak memory if one was recorded,
the wall-clock and the throughput, the outcome, and the source file of every number. Gpu-run
Phase 6a says where each number comes from.

**Caveat on training rows.** The trainer on this tree prints no peak-memory figure, so a
training row on this tree has no peak until the trainer records one. The only memory numbers
for training on this tree are the out-of-memory messages in the A6000 rows below.

Conventions (from the 2026-09-23 fact report these rows were first copied from):
- Times in `meta.json`, `done.json` and `jobs/runs.jsonl` are UTC+9.
- "Heartbeat span" is the first to the last heartbeat row of the working piece.
- "registry elapsed_s" is the start row to the finish row in `jobs/runs.jsonl`.
- "tasks/h" is derived arithmetic (tasks x 3600 / heartbeat span) and is marked "derived".
- `<D>` is `/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/debug/`.
- Card memory: the `memory_gib` of `constants/cards.yaml`, the nvidia-smi MiB total divided by
  1024 and rounded down (RTX A6000 and RTX 6000 Ada 47 GiB, H100 NVL 93 GiB, H200 NVL 140 GiB). The logs print the capacity the process saw: 47.40 GiB
  on an RTX A6000 (the OOM messages), 93.1 GiB on an H100 NVL and 139.81 GiB on an H200 NVL
  (the vLLM logs).

Every run on this tree so far is a `--debug` run; there is no full-scale run of any stage.

## This tree

### Agent service and `sample`

The agent service is `gpt_oss_120b` on vLLM 0.26.0, tensor parallel 1,
`gpu_memory_utilization` 0.92. The probe service of a `sample` run is render-only and runs on
the CPU of shiga, so a `sample` run holds one card. Across the three `sample` runs the largest
number of requests running at once was 2 and the largest KV cache usage was 1.7%.

| task | card type | peak memory | wall-clock | throughput | outcome | date | source |
|---|---|---|---|---|---|---|---|
| agent service startup, `gpt_oss_120b`, debug (9 launches: sample 96de225de2b4 x2, dbfc360385f6; inject c96e48a8be3d, 27d4bad1b70a, ecf0f0957791, 2045e001d683, 4d9c736d3834, 453a69cafd89) | NVIDIA H200 NVL, 140 GiB, tokyo108 c4 / c5 | free on startup 139.3 / 139.81 GiB; budget at 0.92 128.63 GiB = weights 61.43 GiB (checkpoint 60.77 GiB) + peak activation 2.87 GiB + non-torch 0.24 GiB + CUDA graphs 1.22 GiB (dbfc360385f6 log) + KV cache 63.43 GiB (1,640,595 tokens) | model loading 14.5 s to 237.0 s; init engine 35.6 s to 92.8 s | max concurrency 12.52x at 131,072 tokens per request | loaded in all 9 | 2026-09-20, 2026-09-22 | `<D>/{sample,inject}/<key>/log/<service piece>.txt`; also `<D>/_mm2_no_date/serve.log`, `serve2.log` |
| agent service startup, `gpt_oss_120b`, debug (sample 22be0dad52f2) | NVIDIA H100 NVL, 93 GiB, tokyo108 c0 | free on startup 92.58 / 93.1 GiB; budget at 0.92 85.65 GiB; weights 61.43 GiB; peak activation 2.87 GiB; KV cache 20.45 GiB (528,934 tokens) | model loading 18.9 s; init engine 39.21 s | max concurrency 4.04x at 131,072 tokens per request | loaded | 2026-09-20 | `<D>/sample/22be0dad52f2/log/1.txt` |
| `sample-96de225de2b4`, `gpt_oss_120b`, debug: 9 tasks, max_steps 6, 1 loop piece | NVIDIA H200 NVL, 140 GiB, tokyo108 c4 | agent service as in row 1 | heartbeat span 558.9 s; registry: 1st launch `launch_failed` after 1854.9 s, 2nd launch ok 0.0 s | 58.0 tasks/h (derived); tok_out 89,608; vLLM generation 175.0 / 204.8 tok/s (median / max) | 1st launch launch_failed, 2nd ok | 2026-09-20 | `<D>/sample/96de225de2b4/{meta.json,done.json,heartbeat/}`, `jobs/runs.jsonl`, vLLM log "Avg generation throughput" |
| `sample-22be0dad52f2`, `gpt_oss_120b`, debug: 9 tasks, max_steps 5, 1 loop piece | NVIDIA H100 NVL, 93 GiB, tokyo108 c0 | agent service as in row 2 | heartbeat span 350.8 s; registry elapsed_s 550.2 | 92.4 tasks/h (derived); tok_out 56,403; vLLM generation 185.1 / 200.5 tok/s | ok | 2026-09-20 | `<D>/sample/22be0dad52f2/`, `jobs/runs.jsonl`, vLLM log |
| `sample-dbfc360385f6`, `gpt_oss_120b`, debug: 6 tasks, max_steps 4, 2 loop pieces | NVIDIA H200 NVL, 140 GiB, tokyo108 c4 | agent service as in row 1 | heartbeat span 162.7 s (pieces 85.3 s and 162.7 s); registry elapsed_s 404.6 | 132.8 tasks/h (derived); tok_out 37,080; vLLM generation 205.3 / 339.7 tok/s | ok | 2026-09-22 | `<D>/sample/dbfc360385f6/`, `jobs/runs.jsonl`, vLLM log |

### `inject`, with its probe service

Every row: agent `gpt_oss_120b` on its own card, a probe service holding two Qwen3-0.6B
checkpoints (ctool score + cgen gen), debug sizes: 3 test tasks, max_steps 6. The probe
service log (`log/<n>.txt`, 2 lines) and `service_probe_0.json` carry no memory figure (the
json records only `device: cuda:N`), so the probe service's peak memory is unknown on every
card; it has run on a 47 GiB card in 6 runs. The agent service's memory is the startup row of
the table above.

| task | card type | peak memory | wall-clock | throughput | outcome | date | source |
|---|---|---|---|---|---|---|---|
| `inject-c96e48a8be3d`, debug | agent: H200 NVL 140 GiB, tokyo108 c5; probe service: RTX A6000 47 GiB, tokyo105 c1 | probe service not recorded | heartbeat span 140.5 s; registry elapsed_s 436.9 | 76.9 tasks/h (derived) | ok 3/3 | 2026-09-20 | `<D>/inject/c96e48a8be3d/{meta.json,done.json,service_*.json,heartbeat/}`, `jobs/runs.jsonl` |
| `inject-27d4bad1b70a`, debug | agent: H200 NVL, tokyo108 c5; probe service: RTX A6000, tokyo105 c1 | not recorded | heartbeat span 219.6 s; registry elapsed_s 458.1 | 49.2 tasks/h (derived) | ok | 2026-09-20 | `<D>/inject/27d4bad1b70a/`, `jobs/runs.jsonl` |
| `inject-ecf0f0957791` (no_probe arm), debug | agent: H200 NVL, tokyo108 c4; probe service: H200 NVL, tokyo108 c5 | not recorded | heartbeat span 149.8 s; registry elapsed_s 744.8 | 72.1 tasks/h (derived) | ok | 2026-09-20 | `<D>/inject/ecf0f0957791/`, `jobs/runs.jsonl` |
| `inject-7c45d0327b85` (probe_nofill), debug | agent: attached to ecf0f0957791's; probe service: RTX A6000, tokyo105 c2 | not recorded | heartbeat span 166.9 s; registry elapsed_s 253.4 | 64.7 tasks/h (derived) | ok | 2026-09-20 | `<D>/inject/7c45d0327b85/`, `jobs/runs.jsonl` |
| `inject-2045e001d683`, debug | agent: H200 NVL, tokyo108 c4; probe service: H200 NVL, tokyo108 c5 | not recorded | heartbeat span 592.2 s; registry elapsed_s 1003.6 | 18.2 tasks/h (derived) | ok | 2026-09-20 | `<D>/inject/2045e001d683/`, `jobs/runs.jsonl` |
| `inject-a36cf8d69e00` (probe_nofill), debug | agent: attached to 2045e001d683's; probe service: RTX A6000, tokyo105 c1 | not recorded | heartbeat span 109.3 s; registry elapsed_s 640.3 | 98.8 tasks/h (derived) | ok | 2026-09-20 | `<D>/inject/a36cf8d69e00/`, `jobs/runs.jsonl` |
| `inject-4d9c736d3834`, debug | agent: H200 NVL, tokyo108 c5; probe service: RTX A6000, tokyo105 c1 | not recorded | heartbeat span 168.6 s (2 pieces); no finish row | 64.1 tasks/h (derived) | no `done.json`; `run.py ls` shows launching; both heartbeats end with status done | 2026-09-22 | `<D>/inject/4d9c736d3834/`, `jobs/runs.jsonl` |
| `inject-453a69cafd89`, debug | agent: H200 NVL, tokyo108 c4; probe service: RTX A6000, tokyo105 c2 | not recorded | heartbeat span 173.6 s (2 pieces); registry elapsed_s 402.3 | 62.2 tasks/h (derived) | ok | 2026-09-22 | `<D>/inject/453a69cafd89/`, `jobs/runs.jsonl` |
| `inject-583c0e97913c` (probe arm), debug: 3 test tasks, max_steps 6 | agent: H200 NVL, 140 GiB, tokyo108 c5; probe service: RTX A6000, 47 GiB, tokyo105 c2 | agent service as in the startup row above (weights 61.43 GiB, KV cache 63.43 GiB, free on startup 139.3 / 139.81 GiB); probe service not recorded | heartbeat span 144.7 s; registry elapsed_s 458.9 | 74.6 tasks/h (derived) | launch 1 (typed on yebis) `launch_failed` after 1847.7 s: the alive check could not reach either port from outside the cluster network; launch 2 (typed on shiga) ok 3/3 | 2026-09-25 | `<D>/inject/583c0e97913c/`, `jobs/runs.jsonl`, `.scratch/repo-test-2026-09-25/report.md` |
| `inject-210ff860f998` (no_probe arm), debug | agent: H200 NVL, tokyo108 c4 (started fresh, the probe arm's server had already ended); probe service: RTX A6000, tokyo105 c3 | as above | heartbeat span 139.8 s; registry elapsed_s 429.2 | 77.3 tasks/h (derived) | ok 3/3 (typed on shiga) | 2026-09-25 | `<D>/inject/210ff860f998/`, `jobs/runs.jsonl` |
| `inject-dfd404c89e8e` (probe arm, `inject.max_steps=5`), debug | agent: H200 NVL, tokyo108 c5; probe service: RTX A6000, tokyo105 c2 | as above | heartbeat span 104.2 s; registry elapsed_s 438.7 | 103.6 tasks/h (derived) | ok 3/3, typed on yebis on the merged tree (commit 72aa81c: ports probed over ssh, check client on login_host) | 2026-09-25 | `<D>/inject/dfd404c89e8e/`, `jobs/runs.jsonl` |

### `train`, by method and tuning

Every row is debug-sized: Qwen3-0.6B-Base (probe dtype float32), 9 train events, 64 train
rows, 64 val rows, 2 optimizer steps, max_len 8192, events_per_mb 4, accum 2, grad_ckpt
false, predict cap 100, 128 predictions (`experimental_settings/debug.yaml` plus each run's
`settings.yaml`). Times like "+9.6 s" are offsets from the piece's start in
`train_log.jsonl` / the heartbeat. Sources for every row: `<D>/train/<key>/{train_log.jsonl,
heartbeat/,done.json}` and `jobs/runs.jsonl`; the OOM messages are in `<D>/train/<key>/log/0.txt`,
and the launch-to-card mapping is from the start rows of `jobs/runs.jsonl`.

| task | card type | peak memory | wall-clock | throughput | outcome | date | source |
|---|---|---|---|---|---|---|---|
| `train-bd4a5dcf5629`: ctool, full, 0.6B, debug | NVIDIA H100 NVL, 93 GiB, tokyo108 c0 | not printed by the trainer | gstep 2 at +9.6 s, eval +12.1 s, save_best +35.8 s; heartbeat span 45 s; registry elapsed_s -32296.5 (the finish row carries t "2026-09-21 18:07") | - | ok | 2026-09-22 | as above |
| `train-94cbec080c4b`: cgen, full, 0.6B, debug | NVIDIA H100 NVL, 93 GiB, tokyo108 c1 | not printed | gstep 2 +9.7 s, eval +314.8 s, save_best +335.6 s, predict phase (heartbeat 0/3 to 2/3) +342 s to +729 s; span 729 s; registry elapsed_s 884.3 | - | ok | 2026-09-22 | as above |
| `train-0f3e343f0eca`: ctool, full, 0.6B, debug | NVIDIA H200 NVL, 140 GiB, tokyo108 c5 | not printed | heartbeat span 41 s; registry finish row `launch_failed` (85.3 s) | - | `done.json` and `train_done.json` present; registry and `run.py ls` say launch_failed | 2026-09-20 | as above |
| `train-b45633250e8b` 3rd launch (commit 44a1eb8): cgen, full, 0.6B, debug | NVIDIA H200 NVL, 140 GiB, tokyo108 c5 | not printed | gstep 2 +7.9 s, eval +313.0 s; span 732 s | - | ok | 2026-09-20 | as above |
| `train-b6406c340879` 2nd launch (resume test): cgen, full, 0.6B, debug | NVIDIA H200 NVL, 140 GiB, tokyo108 c4 | not printed | span 725 s; registry elapsed_s 839.1 | - | ok | 2026-09-20 | as above |
| `train-a956d422f5a0`: cparam, full, 0.6B, debug | NVIDIA H200 NVL, 140 GiB, tokyo108 c4 | not printed | gstep 2 +8.9 s, eval +313.0 s; span 726 s; registry elapsed_s 867.2 | - | ok | 2026-09-22 | as above |
| `train-5b398c217e13` 4th launch: cparam, full, 0.6B, debug | NVIDIA H200 NVL, 140 GiB, tokyo108 c4 | not printed | predict phase only, 495 s | - | ok | 2026-09-20 | as above |
| `train-d2bdc6878a92` (lr 2e-5): ctool, full, 0.6B, debug | NVIDIA H200 NVL, 140 GiB, tokyo108 c5 | not printed | - | - | launch_failed: the packed-loss alignment check failed (`align_check`, difference 0.151); not a memory failure | 2026-09-20 | as above |
| `train-e643baeab23b`: ctool, LoRA, 0.6B, debug (the only LoRA run on this tree) | NVIDIA H200 NVL, 140 GiB, tokyo108 c5 | not printed | span 40 s | - | ok | 2026-09-20 | as above |
| `train-22a0980de899` (commit 30aae15): ctool, full, 0.6B, debug | NVIDIA RTX A6000, 47 GiB, tokyo105 c1 | not printed | span 53 s | - | ok | 2026-09-20 | as above |
| `train-feabb7b090f5` (lr 3e-5, commit 00b4b81): ctool, full, 0.6B, debug | NVIDIA RTX A6000, 47 GiB, tokyo105 c1 | not printed | span 41 s | - | ok | 2026-09-20 | as above |
| `train-f4b98907f380` (cgen, c2) and `train-4f98555bfe73` (cparam, c3), commit 30aae15: full, 0.6B, debug | NVIDIA RTX A6000, 47 GiB, tokyo105 c2 / c3 | OOM on the first training forward: "Tried to allocate 142.00 MiB. GPU 0 has a total capacity of 47.40 GiB of which 58.19 / 54.19 MiB is free ... this process has 47.34 GiB memory in use ... 45.65 GiB is allocated by PyTorch, 1.37 / 1.38 GiB reserved but unallocated" (the two runs' figures as the report gives them) | - | - | OOM | 2026-09-20 | `<D>/train/<key>/log/0.txt` |
| `train-b45633250e8b` 1st launch (commit 0793692): cgen, full, 0.6B, debug | NVIDIA RTX A6000, 47 GiB, tokyo105 c1 | OOM in validation generate (SDPA prefill) after 2 training steps finished: "Tried to allocate 2.40 GiB ... 348.19 MiB is free ... 47.05 GiB in use ... 44.47 GiB allocated, 2.25 GiB reserved" | - | - | OOM | 2026-09-20 | `<D>/train/b45633250e8b/log/0.txt` |
| `train-5b398c217e13` 1st launch (commit 0793692): cparam, full, 0.6B, debug | NVIDIA RTX A6000, 47 GiB, tokyo105 c2 | OOM at the same point: "Tried to allocate 2.40 GiB ... 1.52 GiB free ... 45.87 GiB in use ... 42.34 GiB allocated, 3.20 GiB reserved" | - | - | OOM | 2026-09-20 | `<D>/train/5b398c217e13/log/0.txt` |
| `train-5b398c217e13` 3rd launch (commit 44a1eb8): cparam, full, 0.6B, debug | NVIDIA RTX A6000, 47 GiB, tokyo105 c1 | not printed | gstep 2 +8.8 s, eval +87.9 s, predict phase +117 s to +206 s; span 206 s | - | completed, including validation and prediction | 2026-09-20 | as above |
| `train-f895049ab1dc` 1st launch (commit 8c72466): cgen, full, 0.6B, debug | NVIDIA RTX A6000, 47 GiB, tokyo105 c1 | not printed | step 1 at +8.6 s, then a checkpoint was written; the heartbeat stops at 1/2 | - | stopped at 1/2 with no error line in the log; launches 2 to 11 went to tokyo108 c4 and all failed with a commit-mismatch refusal | 2026-09-20 | as above |
| `train-d5600ac666ba` (commit 64ee040): cgen, full, 0.6B, debug | NVIDIA RTX A6000, 47 GiB, tokyo105 c1 | not printed | launch 1: step 1 at +8.7 s, checkpoint written; registry elapsed_s 6423.3 | - | failed: launch 2 hit "PytorchStreamReader failed reading zip archive" on the optimizer checkpoint; not a memory failure | 2026-09-20 | as above |
| `train-602051218152` (chain under `sample.max_steps=5`, build 55cd38c24455): ctool, full, 0.6B, debug | NVIDIA H200 NVL, 140 GiB, tokyo108 c4 | not printed | heartbeat span 42.2 s; registry elapsed_s 175.2 | - | ok (2/2 steps, 128 predictions) | 2026-09-25 | `<D>/train/602051218152/`, `jobs/runs.jsonl` |
| `train-b4a83a32b921` (same chain): cgen, full, 0.6B, debug | NVIDIA H100 NVL, 93 GiB, tokyo108 c0 | not printed | heartbeat span 665.7 s; registry elapsed_s 1270.6; read `suspected stall` at beat 207 s during validation | - | ok; its eval failed the shared-build-key gate (theta_from resolved to the un-overridden ctool) | 2026-09-25 | `<D>/train/b4a83a32b921/`, `jobs/runs.jsonl` |
| `train-f46997fdbf8d` (same chain, launched in the same call as the row above from one `--cards tokyo108:0,1` pool): cparam, full, 0.6B, debug | NVIDIA H100 NVL, 93 GiB, tokyo108 c1 | not printed | heartbeat span 659.6 s; registry elapsed_s 1213.5 | - | ok; eval failed the same gate | 2026-09-25 | `<D>/train/f46997fdbf8d/`, `jobs/runs.jsonl` |
| `train-a956d422f5a0` retry / kill / refire / retry: cparam, full, 0.6B, debug | NVIDIA H100 NVL, 93 GiB, tokyo108 c1 | not printed | retry 1 span 726.1 s (killed by hand at 2/2 steps); refire span 9.0 s (died: `train_log.jsonl` exists and no `last/`); retry 2 span 724.4 s; registry elapsed_s 2360.4 on the final row | - | ok after the second retry | 2026-09-25 | `<D>/train/a956d422f5a0/{heartbeat/0-0,0-1,0-3.jsonl,log/0.txt}`, `jobs/runs.jsonl` |

### CPU stages

`eval`, `score` and `build` run as CPU pieces (gpus `''`) on shiga/tokyo105; registry
elapsed_s 4.2 s to 60.3 s (`jobs/runs.jsonl`).

## Previous pipeline, previous trainer at 4096 tokens per event

Not measured on this tree. Source: the project memory file
`/home/y-guo/.claude/projects/-home-y-guo-reproduce-new1/memory/gpu-time-reference.md`. The
earlier version of the gpu-run skill repeated the np821 peaks and "LoRA 17 to 38 GiB" as
measured on the previous trainer at 4096 tokens per event; this trainer's default is 8192.

| task | card type | peak memory | wall-clock | throughput | outcome | date | source |
|---|---|---|---|---|---|---|---|
| p1 collection, gpt-oss-120b, full (315 questions) | 2 x H200 | - | 3.02 h | about 104 questions/h | - | 2026-08-21 | gpu-time-reference.md |
| p1 train, 0.6B full, no gradient checkpointing | H100 | - | whole run 5.6 h; ctool cell 17 min | ~11 ips | - | 2026-08-21 | gpu-time-reference.md |
| p1 train, 1.7B full + gradient checkpointing | H200 | - | whole run 8.6 h; ctool cell 26 min | ~6.7 ips | - | 2026-08-21 | gpu-time-reference.md |
| p1 train, 0.6B LoRA + gradient checkpointing | A6000 | - | whole run ~33 h | ~1.2 ips | - | 2026-08-21 | gpu-time-reference.md |
| p1 train, 1.7B LoRA + gradient checkpointing | A6000 | - | whole run ~42 h | ~0.92 ips | - | 2026-08-21 | gpu-time-reference.md |
| p1 train, 4B LoRA + gradient checkpointing | A6000 | - | whole run ~94 h (marked "extrapolated" in the source) | ~0.41 ips | - | 2026-08-21 | gpu-time-reference.md |
| p1 ctool cell training, 0.6B LoRA + gradient checkpointing | A6000 | - | 1.0 h | - | - | 2026-08-21 | gpu-time-reference.md |
| p1 ctool cell training, 1.7B LoRA + gradient checkpointing | A6000 | - | 1.4 h | - | - | 2026-08-21 | gpu-time-reference.md |
| p1 ctool cell training, 4B LoRA + gradient checkpointing | A6000 | - | 3.1 h | - | - | 2026-08-21 | gpu-time-reference.md |
| p1 evaluation | - | - | 7 to 14 min per cell | - | - | 2026-08-21 | gpu-time-reference.md |
| np821 collection | 1 x H100 + 3 x H200 | - | - | about 260 trajectories/h | - | 2026-08-26 | gpu-time-reference.md |
| np821 train, 0.6B full | H100 | - | whole run ~18 h; ctool ~1.0 h | - | - | 2026-08-26 | gpu-time-reference.md |
| np821 train, 1.7B full + gradient checkpointing | H100 | - | whole run ~30 h; ctool ~1.5 h | - | - | 2026-08-26 | gpu-time-reference.md |
| np821 train, 1.7B LoRA + gradient checkpointing | RTX 6000 Ada | - | whole run ~98.5 h; ctool ~3.2 h | 1.72-1.73 ips | - | 2026-08-26 | gpu-time-reference.md |
| np821 train, 4B LoRA + gradient checkpointing | H200 | - | whole run ~64.3 h; ctool ~3.0 h | 2.78-2.79 ips | - | 2026-08-26 | gpu-time-reference.md |
| np821 train, 0.6B full, ctool / cgen / cparam | "a large card" (the source names no model) | 60.2 / 76.8 / 76.7 GiB | - | - | - | 2026-08-26 | gpu-time-reference.md |
| np821 train, 1.7B full + gradient checkpointing, smoke | 48 GB card | 44.1 GB | - | - | smoke passed | 2026-08-26 | gpu-time-reference.md |
| np821 train, 1.7B full + gradient checkpointing, full cgen | 48 GB card | - | - | - | OOM on the first backward pass | 2026-08-26 | gpu-time-reference.md |
| np821 train, 1.7B LoRA / 4B LoRA | card not named in the source | 1.7B 17-35 G; 4B 32-38 G | - | - | - | 2026-08-26 | gpu-time-reference.md |
| np821 evaluation | - | - | ctool 36-45 min per batch; call tier 21-26 min per cell | - | - | 2026-08-26 | gpu-time-reference.md |

`notes/DATA.md` (lines 42, 102) states only which cards the collections used: nyapass on
tokyo108 "2 H100 + 3/4/5 H200", p1 on "two H200". `gpu_state.md`, surveyed 2026-07-29:
tokyo106/107 drivers go up to CUDA 12.2, and cu128 torch was measured to run on 106/107.

## Previous pipeline, other trainer settings (`notes/TIMELINE.md`)

Not measured on this tree. The 2026-08-28 rows are from the ks828 trainer at the token budgets
each row names; the 2026-08-29 sweep ran at a 16384 token budget (notes/TIMELINE.md, 2026-08-29
entry).

| task | card type | peak memory | wall-clock | throughput | outcome | date | source |
|---|---|---|---|---|---|---|---|
| 0.6B full test (z1) | 48G | - | - | - | "z1's test found 0.6B full-parameter OOMs on 48G" | 2026-08-21 | notes/TIMELINE.md |
| ks828 cgen speed cell, 8192 / 16384 token budget | H100 (93.10 GiB) | allocated peak 60.59 GB (56.4 GiB); one nvidia-smi sample 54.4 GiB; final whole-run peak 58.47 GB | - | - | - | 2026-08-28 | notes/TIMELINE.md |
| ks828 cgen, 24576 token budget | H100 | 80.9 GB | - | - | - | 2026-08-28 | notes/TIMELINE.md |
| ks828 ctool, 8192 x bs 4 | H100 (92.94 GiB) | - | - | - | OOM on the first batch | 2026-08-28 | notes/TIMELINE.md |
| ks828 ctool, 8192 x bs 2 | H100 | 56,859 MiB (nvidia-smi) | - | - | - | 2026-08-28 | notes/TIMELINE.md |
| LR sweep b17: 1.7B full, no gradient checkpointing, 16384 token budget | H200 | 102.336 GB (whole-run step peak) | - | - | - | 2026-08-29 | notes/TIMELINE.md |
| LR sweep b06: 0.6B full + gradient checkpointing, 16384 token budget | Ada | 22.427 GB | - | - | - | 2026-08-29 | notes/TIMELINE.md |
| LR sweep l17: 1.7B LoRA, 16384 token budget | H200 | 81.655 GB | - | - | - | 2026-08-29 | notes/TIMELINE.md |
| LR sweep l4: 4B LoRA + gradient checkpointing, 16384 token budget | H100 | 33.088 GB | - | - | - | 2026-08-29 | notes/TIMELINE.md |

## Not measured

What no run on this tree has measured (as of 2026-09-23):

- `sample`: no full-scale run (315 tasks, 6 pieces) on any card. `gpt_oss_120b` has never
  been started on a 47 GiB card, never with more than one replica or tensor parallelism above
  1, never with more than 2 requests at once, and its KV cache usage was never above 1.7%.
- `inject`: no full-scale run. The probe service's memory has never been recorded on any card;
  it has never run on tokyo106 or tokyo107 and has never held 1.7B or 4B checkpoints.
- `train`: no full-scale run of any method. Qwen3-1.7B and Qwen3-4B were never trained on this
  tree, and no setting names them. LoRA never ran on a 47 GiB card, never for cgen or cparam,
  never on an H100. `grad_ckpt=true` never ran. No run on tokyo106 (RTX A6000) or tokyo107
  (RTX 6000 Ada); all 47 GiB training was on tokyo105 (RTX A6000). No peak-memory figure
  exists for any successful training run, because the trainer prints none. ctool full on H100
  and H200 succeeded only at debug size.
- Card slots this tree has never used: tokyo108 card 2 (H100 NVL) and card 3 (H200 NVL).
