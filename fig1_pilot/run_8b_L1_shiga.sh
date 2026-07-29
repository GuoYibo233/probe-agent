#!/bin/bash
# Step-14 small matrix: Qwen3-8B on shiga, L1 x {nomem,mem} x seed0 x k=5.
# One cell per GPU (nomem -> gpu1/port 8721, mem -> gpu2/port 8722), servers are
# hf_server.py instances (Plan B backend, same as redo106; vLLM wheels don't run
# on shiga's driver). Wall times are shiga-hardware, NOT comparable to tokyo108.
set -u
cd /home/y-guo/reproduce/new1/fig1_pilot
PY=./fig1-env/bin/python
MODEL=Qwen/Qwen3-8B
COMMON="--k 5 --think --max-tokens 2048 --seed 0 --model $MODEL"

wait_ready() {
  for i in $(seq 1 180); do
    curl -s -m 3 "http://localhost:$1/v1/models" | grep -q Qwen && return 0
    sleep 5
  done
  echo "port $1 not ready" >&2; return 1
}

for p in 8721 8722; do wait_ready "$p" || exit 1; done
echo ALL_SERVERS_READY

$PY fig1_run.py --setting nomem --level L1 $COMMON --url http://localhost:8721/v1 \
  --out results/8b_L1_nomem_s0.jsonl > results/8b_L1_nomem_s0.log 2>&1 &
$PY fig1_run.py --setting mem   --level L1 $COMMON --url http://localhost:8722/v1 \
  --out results/8b_L1_mem_s0.jsonl   > results/8b_L1_mem_s0.log 2>&1 &
wait
echo SMALL_MATRIX_DONE
for f in results/8b_L1_*.jsonl; do echo "--- $f ($(wc -l < "$f") eps)"; done
