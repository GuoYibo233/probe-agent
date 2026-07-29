#!/bin/bash
# Full overnight matrix: {L0,L1,L2} x {nomem,mem} x seeds 0-4 = 30 runs (15 pairs).
# Each (level,seed) pair runs nomem then mem SEQUENTIALLY on the SAME card, so the
# within-pair wall-clock comparison is same-hardware by construction.
# 15 pairs round-robin over 6 cards (ports 8712-8717).
set -u
cd /home/y-guo/reproduce/new1/fig1_pilot
PY=./fig1-env/bin/python
COMMON="--k 10 --think --max-tokens 2048"

wait_ready() {
  for i in $(seq 1 90); do
    curl -s -m 3 "http://tokyo108:$1/v1/models" | grep -q Qwen && return 0
    sleep 5
  done
  echo "port $1 not ready" >&2; return 1
}

PORTS=(8712 8713 8714 8715 8716 8717)
for p in "${PORTS[@]}"; do wait_ready "$p" || exit 1; done
echo ALL_SERVERS_READY

# enumerate 15 (level,seed) pairs
PAIRS=()
for L in L0 L1 L2; do for S in 0 1 2 3 4; do PAIRS+=("$L $S"); done; done

worker() {  # worker <card_idx>
  local ci=$1 port=${PORTS[$1]}
  for ((j=ci; j<15; j+=6)); do
    set -- ${PAIRS[$j]}
    local L=$1 S=$2
    for SETTING in nomem mem; do
      local tag="full_${L}_${SETTING}_s${S}"
      echo "[card $ci] start $tag"
      $PY fig1_run.py --setting $SETTING --level $L --seed $S $COMMON \
        --url "http://tokyo108:$port/v1" --out "results/$tag.jsonl" \
        > "results/$tag.log" 2>&1
      echo "[card $ci] done $tag ($(wc -l < results/$tag.jsonl) eps)"
    done
  done
}

for ci in 0 1 2 3 4 5; do worker $ci & done
wait
echo FULL_MATRIX_DONE
ls -la results/full_*.jsonl | wc -l