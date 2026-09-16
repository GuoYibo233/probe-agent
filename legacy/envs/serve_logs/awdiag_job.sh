#!/bin/bash
# w0 recheck diagnostic, two arms (2026-08-02, tracking down the systematic source of live-run noprobe 17.3% vs w0 28.6%):
#   chat    = today's unmodified rerun of w0's original collection script (run_appworld.py --api chat) on 168 tasks.
#             reproducing ~28.6% => the live-run driver has a real settings gap; only ~17% => w0 doesn't reproduce.
#   np1shot = live-run driver's noprobe single-shot version (--tail-tokens 8192, one shot per step, no segment seam).
#             matching chat => the v2 gap comes from segmented continuation / 65k context; still ~17% => something else in the driver is broken.
# Usage: awdiag_job.sh chat|np1shot   (run the whole thing in tmux)
# Serving prerequisite: tokyo108 8103/8106/8107, three gpt-oss instances **native 131k (no --max-model-len,
#          same as launch_vllm_w0.py used for the w0 collection)**; tokyo105:8790 probe (used by /render).
set -u
ARM="$1"
ROOT=/home/y-guo/reproduce/new1
NFS=/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1
LOG=/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/logs
PORTS=(8103 8106 8107)
cd "$ROOT"
case "$ARM" in
  chat)
    OUT=$NFS/envs/runs/aw_pathdiag/w0_repro_chat
    mkdir -p "$OUT"
    for s in $(seq 0 5); do
      port=${PORTS[$((s % 3))]}
      envs/appworld/venv/bin/python envs/collect/run_appworld.py \
        --base-url http://tokyo108:$port/v1 --model gpt-oss-120b \
        --api chat --reasoning-effort high \
        --split test_normal --n 0 --max-steps 30 \
        --outdir "$OUT" --exp awdiag_chat \
        --num-shards 6 --shard-id $s --resume \
        > "$LOG/new1_awdiag_chat_s${s}.log" 2>&1 &
    done ;;
  np1shot)
    OUT=$NFS/pipeline/inject/runs/aw_pathdiag/np1shot
    mkdir -p "$OUT"
    # Dynamic task claiming: clear the claim root, all tasks without a final get re-claimed (the claim() convention)
    rm -rf "$OUT/.claims"
    for s in $(seq 0 5); do
      port=${PORTS[$((s % 3))]}
      envs/appworld/venv/bin/python pipeline/inject/live_appworld.py \
        --base-url http://tokyo108:$port/v1 --probe-url http://tokyo105:8790 \
        --split test_normal --max-steps 30 --no-probe --tail-tokens 8192 \
        --pool --outdir "$OUT" --exp awdiag_np1shot \
        --num-shards 6 --shard-id $s --resume \
        > "$LOG/new1_awdiag_np1shot_s${s}.log" 2>&1 &
    done ;;
  np1shot_fp)
    # After the parse fix, one shot per step (no segment seam): differs from v3 noprobe only by tail 8192,
    # isolating the contribution of the "1024 segment seam" to junk stuffed into the residual answer (22 tasks wrongly killed in v3np).
    OUT=$NFS/pipeline/inject/runs/aw_pathdiag/np1shot_fixedparser
    mkdir -p "$OUT"
    rm -rf "$OUT/.claims"
    for s in $(seq 0 5); do
      port=${PORTS[$((s % 3))]}
      envs/appworld/venv/bin/python pipeline/inject/live_appworld.py \
        --base-url http://tokyo108:$port/v1 --probe-url http://tokyo105:8790 \
        --split test_normal --max-steps 30 --no-probe --tail-tokens 8192 \
        --pool --outdir "$OUT" --exp awdiag_np1shot_fp \
        --num-shards 6 --shard-id $s --resume \
        > "$LOG/new1_awdiag_np1shot_fp_s${s}.log" 2>&1 &
    done ;;
  *) echo "unknown arm: $ARM"; exit 1 ;;
esac
wait
echo "DIAG_${ARM}_DONE"
