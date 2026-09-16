#!/bin/bash
# Launch 12 pieces for one live-run arm (run the whole thing in tmux; one process, one world, per piece).
# Usage: live_arm_job.sh probe|noprobe run_name
#   run_name is required (v2 rerun = live_aw_gptoss_v2). Foolproofing: the v1 directory live_aw_gptoss
#   is already wrapped up; falling back to it by default would silently run empty (--resume skips everything) and still print DONE, looking like it finished.
# Lesson: the previous version chained `cd && p0 & p1 &` directly; && only binds to the first background job,
# so the other 11 pieces died instantly in the wrong cwd -- so this was hardened into a script, with cd before all pieces.
set -u
ARM="$1"
RUN="${2:?run_name is required, e.g. live_aw_gptoss_v2 (must not point at the v1 dir)}"
ROOT=/home/y-guo/reproduce/new1
LOG=/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/logs
cd "$ROOT"
# effort arms use a dedicated H200 replica and probe #2 (8791; only the new /render recognizes the effort field;
# the old 8790 silently drops effort and renders at high -- effort arms must never point at it)
case "$ARM" in
  probe)       EXTRA="";                        PORTS=(8114 8115 8116); PROBE=8790 ;;
  noprobe)     EXTRA="--no-probe";              PORTS=(8114 8115 8116); PROBE=8790 ;;
  noprobe_low) EXTRA="--no-probe --effort low"; PORTS=(8117);           PROBE=8791 ;;
  noprobe_med) EXTRA="--no-probe --effort medium"; PORTS=(8118);        PROBE=8791 ;;
  probe_low)   EXTRA="--effort low";            PORTS=(8117);           PROBE=8792 ;;
  # ^ after noprobe_low wrapped up at 168/168, its dedicated replica 8117 freed up, so probe_low switched to it,
  #   each taking one H200 alongside probe_med (8119) (switched 2026-08-02 03:3x, continued via --resume)
  probe_med)   EXTRA="--effort medium";         PORTS=(8118 8119);      PROBE=8792 ;;
  # ^ after noprobe_med wrapped up, 8118 freed up and was given to the lagging probe_med as a second replica to split load (03:5x)
  *) echo "unknown arm: $ARM"; exit 1 ;;
esac
# Dynamic task claiming: clear the claim root, all tasks without a final get re-claimed (the claim() convention)
OUT="pipeline/inject/runs/$RUN/$ARM"
rm -rf "$OUT/.claims"
for s in $(seq 0 11); do
  port=${PORTS[$((s % ${#PORTS[@]}))]}
  envs/appworld/venv/bin/python pipeline/inject/live_appworld.py \
    --base-url http://tokyo108:$port/v1 --probe-url http://tokyo105:$PROBE \
    --split test_normal --max-steps 30 $EXTRA --pool \
    --outdir "$OUT" \
    --exp "${RUN}_${ARM}" --num-shards 12 --shard-id $s --resume \
    > "$LOG/new1_${RUN}_${ARM}_s${s}.log" 2>&1 &
done
wait
echo "ARM_${ARM}_DONE"
