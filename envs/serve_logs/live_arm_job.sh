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
# effort 臂打专属 H200 副本与探针二号(8791,新 /render 才认 effort 字段;
# 老 8790 会静默丢掉 effort 按 high 渲——绝不能把 effort 臂指过去)
case "$ARM" in
  probe)       EXTRA="";                        PORTS=(8114 8115 8116); PROBE=8790 ;;
  noprobe)     EXTRA="--no-probe";              PORTS=(8114 8115 8116); PROBE=8790 ;;
  noprobe_low) EXTRA="--no-probe --effort low"; PORTS=(8117);           PROBE=8791 ;;
  noprobe_med) EXTRA="--no-probe --effort medium"; PORTS=(8118);        PROBE=8791 ;;
  probe_low)   EXTRA="--effort low";            PORTS=(8117);           PROBE=8792 ;;
  # ^ noprobe_low 168/168 收官后其专属副本 8117 空出,probe_low 切过去,
  #   与 probe_med(8119)各占一张 H200(2026-08-02 03:3x 切换,--resume 续跑)
  probe_med)   EXTRA="--effort medium";         PORTS=(8118 8119);      PROBE=8792 ;;
  # ^ noprobe_med 收官后 8118 空出,拨给落后的 probe_med 双副本分流(03:5x)
  *) echo "unknown arm: $ARM"; exit 1 ;;
esac
# 动态领题:清票根,没写 final 的题全部重新开抢(claim() 的约定)
rm -rf "pipeline/inject/runs/live_aw_gptoss/$ARM/.claims"
for s in $(seq 0 11); do
  port=${PORTS[$((s % ${#PORTS[@]}))]}
  envs/appworld/venv/bin/python pipeline/inject/live_appworld.py \
    --base-url http://tokyo108:$port/v1 --probe-url http://tokyo105:$PROBE \
    --split test_normal --max-steps 30 $EXTRA --pool \
    --outdir pipeline/inject/runs/live_aw_gptoss/$ARM \
    --exp live_aw_$ARM --num-shards 12 --shard-id $s --resume \
    > "$LOG/new1_live_${ARM}_s${s}.log" 2>&1 &
done
wait
echo "ARM_${ARM}_DONE"
