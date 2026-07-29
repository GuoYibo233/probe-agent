#!/bin/bash
# Fig 1 pilot: 4 arms in parallel, one dedicated GPU each.
#   L0 pair on H200 (gpu3,4 -> ports 8715,8716)
#   L1 pair on H100 (gpu0,1 -> ports 8712,8713)
set -u
cd /home/y-guo/reproduce/new1/fig1_pilot
PY=./fig1-env/bin/python
K=10
COMMON="--k $K --think --max-tokens 2048 --seed 0"

wait_ready() {
  for i in $(seq 1 90); do
    curl -s -m 3 "http://tokyo108:$1/v1/models" | grep -q Qwen && return 0
    sleep 5
  done
  echo "port $1 not ready" >&2; return 1
}

for p in 8712 8713 8715 8716; do wait_ready $p || exit 1; done
echo ALL_SERVERS_READY

$PY fig1_run.py --setting nomem --level L0 $COMMON --url http://tokyo108:8715/v1 --out results/pilot_L0_nomem.jsonl > results/pilot_L0_nomem.log 2>&1 &
$PY fig1_run.py --setting mem   --level L0 $COMMON --url http://tokyo108:8716/v1 --out results/pilot_L0_mem.jsonl   > results/pilot_L0_mem.log 2>&1 &
$PY fig1_run.py --setting nomem --level L1 $COMMON --url http://tokyo108:8712/v1 --out results/pilot_L1_nomem.jsonl > results/pilot_L1_nomem.log 2>&1 &
$PY fig1_run.py --setting mem   --level L1 $COMMON --url http://tokyo108:8713/v1 --out results/pilot_L1_mem.jsonl   > results/pilot_L1_mem.log 2>&1 &
wait
echo PILOT_DONE
for f in results/pilot_*.jsonl; do echo "--- $f"; tail -1 "$f" | head -c 200; echo; done
