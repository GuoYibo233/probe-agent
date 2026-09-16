#!/bin/bash
# Diagnostic smoke test on 14 tasks for the stop-token fix (noprobe; handoff doc §3.2). Run the whole thing in tmux.
# The 14 tasks = tasks w0 got fully right, v1 live run got fully wrong, and per-task autopsy confirmed died from the stop-token bug.
# Acceptance line: (a) zero fabricated "Execution output:" in content, zero <|start|>;
#         (b) success >= 7/14, otherwise stop and re-diagnose the cause.
set -u
ROOT=/home/y-guo/reproduce/new1
LOG=/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/logs
TASKS="024c982_2,0a9d82a_2,0d01c76_1,13547f5_3,31dc501_1,3b8fb7a_3,522e5e5_2,59fae45_1,634f342_2,8749218_1,9dabbc9_1,c77c005_2,f3f60f0_1,ff58e36_2"
OUT="pipeline/inject/runs/live_smoke_stopfix"
PORTS=(8114 8115 8116)
cd "$ROOT"
# Dynamic task claiming: clear the claim root, all tasks without a final get re-claimed (the claim() convention)
rm -rf "$OUT/.claims"
for s in $(seq 0 5); do
  port=${PORTS[$((s % 3))]}
  envs/appworld/venv/bin/python pipeline/inject/live_appworld.py \
    --base-url http://tokyo108:$port/v1 --probe-url http://tokyo105:8790 \
    --split test_normal --max-steps 30 --no-probe --pool \
    --task-ids "$TASKS" \
    --outdir "$OUT" --exp live_smoke_stopfix \
    --num-shards 6 --shard-id $s --resume \
    > "$LOG/new1_live_smoke_stopfix_s${s}.log" 2>&1 &
done
wait
echo "SMOKE_DONE"
