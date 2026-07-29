#!/bin/bash
# Redo the (L2, seed 1) pair ON tokyo106 GPU 0 — both settings on the SAME card
# so the within-pair wall-clock comparison stays same-hardware by construction.
# NOTE: different hardware from the tokyo108 pairs -> results named redo106_* so
# analysis can keep hardware provenance separate.
set -u
cd /home/y-guo/reproduce/new1/fig1_pilot
PY=./fig1-env/bin/python
URL=http://tokyo106:8712/v1

for i in $(seq 1 120); do
  curl -s -m 3 "$URL/models" | grep -q Qwen && break
  sleep 5
done
curl -s -m 3 "$URL/models" | grep -q Qwen || { echo SERVER_NOT_READY; exit 1; }
echo SERVER_READY

for SETTING in nomem mem; do
  tag="redo106_L2_${SETTING}_s1"
  echo "start $tag"
  $PY fig1_run.py --setting $SETTING --level L2 --seed 1 --k 10 --think \
    --max-tokens 2048 --url "$URL" --out "results/$tag.jsonl" \
    > "results/$tag.log" 2>&1
  echo "done $tag ($(wc -l < results/$tag.jsonl) eps)"
done
echo PAIR_DONE
