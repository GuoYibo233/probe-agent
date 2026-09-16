#!/bin/bash
# live v3 two-arm launch (2026-08-02): the official rerun after the commentary fix (937b3a2).
# Three differences from v2: parse_step matches vLLM's HarmonyParser (commentary goes into content);
# vLLM has no --max-model-len (native 131k, same as the w0 collection, ports 8103/8106/8107);
# the remaining settings (chunk 64/tail 1024/θ=0.925/effort high/max-steps 30) are identical to v2.
# Usage: live_v3_job.sh probe|noprobe run_name   (run_name=live_aw_gptoss_v3)
set -u
ARM="$1"
RUN="${2:?run_name is required, e.g. live_aw_gptoss_v3 (must not point at the v1/v2 dirs)}"
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
# Dynamic task claiming: clear the claim root, all tasks without a final get re-claimed (the claim() convention)
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
