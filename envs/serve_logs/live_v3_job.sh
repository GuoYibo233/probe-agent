#!/bin/bash
# live v3 双臂发射(2026-08-02):commentary 修复(937b3a2)后的正式重跑。
# 与 v2 的三处不同:parse_step 对齐 vLLM HarmonyParser(commentary 进 content);
# vLLM 无 --max-model-len(native 131k,与 w0 采集同款,端口 8103/8106/8107);
# 其余口径(chunk 64/tail 1024/θ=0.925/effort high/max-steps 30)与 v2 逐字同。
# 用法: live_v3_job.sh probe|noprobe run_name   (run_name=live_aw_gptoss_v3)
set -u
ARM="$1"
RUN="${2:?run_name 必填,如 live_aw_gptoss_v3 (v1/v2 目录不许再指)}"
ROOT=/home/y-guo/reproduce/new1
LOG=/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/logs
cd "$ROOT"
case "$ARM" in
  probe)   EXTRA="" ;;
  noprobe) EXTRA="--no-probe" ;;
  *) echo "unknown arm: $ARM"; exit 1 ;;
esac
PORTS=(8103 8106 8107)
OUT="pipeline/inject/runs/$RUN/$ARM"
# 动态领题:清票根,没写 final 的题全部重新开抢(claim() 的约定)
rm -rf "$OUT/.claims"
for s in $(seq 0 11); do
  port=${PORTS[$((s % 3))]}
  envs/appworld/venv/bin/python pipeline/inject/live_appworld.py \
    --base-url http://tokyo108:$port/v1 --probe-url http://tokyo105:8790 \
    --split test_normal --max-steps 30 $EXTRA --pool \
    --outdir "$OUT" \
    --exp "${RUN}_${ARM}" --num-shards 12 --shard-id $s --resume \
    > "$LOG/new1_${RUN}_${ARM}_s${s}.log" 2>&1 &
done
wait
echo "ARM_${ARM}_DONE"
