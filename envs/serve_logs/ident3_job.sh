#!/bin/bash
# ident3 (2026-08-18): three arms match token-for-token, 5 tasks x 10 reps each. One process per arm, the 5 tasks within a rep
# run serially, and reps run serially too (plan plans/archive/2026-08-18-ident3.md §3). The three arms each launch one copy and run in parallel.
# Usage: ident3_job.sh chat|noprobe|nofill <root> [reps=10] [n_tasks=5] [vllm_port=8114] [probe_url=http://localhost:8795]
#   root = output root directory (NFS); one subdirectory per arm per rep, <root>/<arm>/rep<r>/
#   the chat arm's outdir name must end in appworld_gptoss (collector convention)
# Before running, pass ident3_gate.py: the chat endpoint's prompt_token_ids must equal /render's, id for id
# (vLLM date pin, return_token_ids in effect); if it doesn't pass, the whole arm is refused.
set -u -o pipefail
ARM="${1:?arm is required: chat|noprobe|nofill}"
ROOTDIR="${2:?root is required (NFS output root dir)}"
REPS="${3:-10}"
NTASK="${4:-5}"
PORT="${5:-8114}"
PROBE="${6:-http://localhost:8795}"
FIRE_NTH="${IDENT3_FIRE_NTH:-5}"      # pseudo-trigger: which sentence-ending cut number to fire at (plan E1)
NEW1=/home/y-guo/reproduce/new1
cd "$NEW1"
BASE="http://tokyo108:$PORT/v1"
mkdir -p "$ROOTDIR/logs"
if ! python3 pipeline/inject/ident3_gate.py --base-url "$BASE" --probe-url "$PROBE" \
     2>&1 | tee "$ROOTDIR/logs/gate_${ARM}.log"; then
  echo "ARM_${ARM}_GATE_FAIL"; exit 3
fi
FAILS=0
for r in $(seq 0 $((REPS - 1))); do
  case "$ARM" in
    chat)
      OUT="$ROOTDIR/chat/rep$r/appworld_gptoss"
      CMD=(envs/appworld/venv/bin/python envs/collect/run_appworld.py
           --base-url "$BASE" --model gpt-oss-120b --split test_normal
           --n "$NTASK" --max-steps 20 --api chat --outdir "$OUT"
           --exp "ident3_chat_r$r" --resume) ;;
    noprobe)
      OUT="$ROOTDIR/noprobe/rep$r"
      CMD=(envs/appworld/venv/bin/python pipeline/inject/live_appworld.py
           --base-url "$BASE" --probe-url "$PROBE" --split test_normal
           --n "$NTASK" --max-steps 20 --no-probe --outdir "$OUT"
           --exp "ident3_noprobe_r$r" --resume) ;;
    nofill)
      OUT="$ROOTDIR/nofill/rep$r"
      CMD=(envs/appworld/venv/bin/python pipeline/inject/live_appworld.py
           --base-url "$BASE" --probe-url "$PROBE" --split test_normal
           --n "$NTASK" --max-steps 20 --fire-nth-cut "$FIRE_NTH" --nofill
           --outdir "$OUT" --exp "ident3_nofill_r$r" --resume) ;;
    *) echo "unknown arm: $ARM"; exit 1 ;;
  esac
  echo "=== $(date '+%F %T') $ARM rep$r ==="
  echo "${CMD[*]}"
  "${CMD[@]}" 2>&1 | tee "$ROOTDIR/logs/${ARM}_rep$r.log"
  rc=$?
  echo "=== $(date '+%F %T') $ARM rep$r exit=$rc ==="
  [ "$rc" -ne 0 ] && FAILS=$((FAILS + 1))
done
echo "ARM_${ARM}_DONE fails=$FAILS"
