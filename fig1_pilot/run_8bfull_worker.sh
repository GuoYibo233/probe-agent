#!/bin/bash
# Step-16 full-matrix worker: runs (level,seed) pairs sequentially on ONE server.
# Within a pair: nomem then mem on the same card (same-hardware wall comparison).
# Usage: run_8bfull_worker.sh <URL> "<L> <S>" ["<L> <S>" ...]
set -u
cd /home/y-guo/reproduce/new1/fig1_pilot
PY=./fig1-env/bin/python
URL=$1; shift
COMMON="--k 10 --think --max-tokens 2048 --model Qwen/Qwen3-8B"

for i in $(seq 1 360); do
  curl -s -m 3 "$URL/models" | grep -q Qwen && break
  sleep 5
done
curl -s -m 3 "$URL/models" | grep -q Qwen || { echo "SERVER_NOT_READY $URL"; exit 1; }
echo "SERVER_READY $URL"

for pair in "$@"; do
  set -- $pair; L=$1; S=$2
  for SETTING in nomem mem; do
    tag="8bfull_${L}_${SETTING}_s${S}"
    echo "start $tag $(date +%F_%H:%M)"
    $PY fig1_run.py --setting $SETTING --level $L --seed $S $COMMON --url "$URL" \
      --out "results/$tag.jsonl" > "results/$tag.log" 2>&1
    echo "done $tag ($(wc -l < "results/$tag.jsonl" 2>/dev/null || echo 0) eps) $(date +%F_%H:%M)"
  done
done
echo WORKER_DONE
