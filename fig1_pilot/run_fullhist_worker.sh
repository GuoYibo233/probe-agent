#!/bin/bash
# T12d full-history baseline worker: runs (level,seed) pairs sequentially on ONE
# server. Within a pair: nomem then fullhist on the SAME card, so the wall-clock
# comparison is same-hardware by construction (the 8bfull mem/nomem numbers came
# off shiga/tokyo107 — their wall is NOT comparable to a new card, only tokens
# are, so the paired nomem re-run is what makes the fullhist wall claim legal).
#
# Usage: run_fullhist_worker.sh <URL> "<L> <S>" ["<L> <S>" ...]
#   e.g. run_fullhist_worker.sh http://localhost:8791/v1 "L0 0" "L0 1" "L0 2"
# Env: SETTINGS="nomem fullhist" (default, paired wall control)
#      SETTINGS="fullhist"       (token-only comparison against 8bfull, half the wall)
#
# Same stream as 8bfull: --k 10, seeds 0-4, levels L0/L1/L2 (code names; canonical
# L0->L2 exact-repeat, L1->L2- near-dup, L2->L1 partial-similar).
set -u
cd /home/y-guo/reproduce/new1/fig1_pilot
PY=./fig1-env/bin/python
URL=$1; shift
SETTINGS=${SETTINGS:-"nomem fullhist"}
COMMON="--k 10 --think --max-tokens 2048 --model Qwen/Qwen3-8B --fullhist-budget-tokens 24576"

for i in $(seq 1 360); do
  curl -s -m 3 "$URL/models" | grep -q Qwen && break
  sleep 5
done
curl -s -m 3 "$URL/models" | grep -q Qwen || { echo "SERVER_NOT_READY $URL"; exit 1; }
echo "SERVER_READY $URL"

for pair in "$@"; do
  set -- $pair; L=$1; S=$2
  for SETTING in $SETTINGS; do
    tag="fullhist_${L}_${SETTING}_s${S}"
    echo "start $tag $(date +%F_%H:%M)"
    $PY fig1_run.py --setting $SETTING --level $L --seed $S $COMMON --url "$URL" \
      --out "results/$tag.jsonl" > "results/$tag.log" 2>&1
    echo "done $tag ($(wc -l < "results/$tag.jsonl" 2>/dev/null || echo 0) eps) $(date +%F_%H:%M)"
  done
  # truncation audit for the run note
  grep -h "fullhist eps_available" "results/fullhist_${L}_fullhist_s${S}.log" 2>/dev/null \
    | sed "s/^/[${L} s${S}] /"
done
echo WORKER_DONE
