#!/bin/bash
# 停止符修复的 14 题确诊冒烟(noprobe;交接书 §3.2)。tmux 里整段跑。
# 14 题 = w0 全对、v1 活跑全错、逐题验尸确诊死于停止符漏洞的题。
# 验收线: (a) content 零伪造 "Execution output:" 零 <|start|>;
#         (b) 成功 >= 7/14,否则停下重新归因。
set -u
ROOT=/home/y-guo/reproduce/new1
LOG=/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/logs
TASKS="024c982_2,0a9d82a_2,0d01c76_1,13547f5_3,31dc501_1,3b8fb7a_3,522e5e5_2,59fae45_1,634f342_2,8749218_1,9dabbc9_1,c77c005_2,f3f60f0_1,ff58e36_2"
OUT="pipeline/inject/runs/live_smoke_stopfix"
PORTS=(8114 8115 8116)
cd "$ROOT"
# 动态领题:清票根,没写 final 的题全部重新开抢(claim() 的约定)
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
