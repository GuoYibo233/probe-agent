#!/bin/bash
# live 活跑一臂的 12 分片发射(tmux 里整段跑;每分片一个进程一个世界)。
# 用法: live_arm_job.sh probe|noprobe
# 教训:上一版把 `cd && p0 & p1 &` 直接拼串,&& 只绑到第一个后台任务,
# 其余 11 片在错误 cwd 下秒死——所以固化成脚本,cd 在所有分片之前。
set -u
ARM="$1"
ROOT=/home/y-guo/reproduce/new1
LOG=/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/logs
cd "$ROOT"
case "$ARM" in
  probe)       EXTRA="" ;;
  noprobe)     EXTRA="--no-probe" ;;
  noprobe_low) EXTRA="--no-probe --effort low" ;;
  noprobe_med) EXTRA="--no-probe --effort medium" ;;
  *) echo "unknown arm: $ARM"; exit 1 ;;
esac
for s in $(seq 0 11); do
  port=$((8114 + s % 3))
  envs/appworld/venv/bin/python pipeline/inject/live_appworld.py \
    --base-url http://tokyo108:$port/v1 --probe-url http://tokyo105:8790 \
    --split test_normal --max-steps 30 $EXTRA \
    --outdir pipeline/inject/runs/live_aw_gptoss/$ARM \
    --exp live_aw_$ARM --num-shards 12 --shard-id $s --resume \
    > "$LOG/new1_live_${ARM}_s${s}.log" 2>&1 &
done
wait
echo "ARM_${ARM}_DONE"
