#!/bin/bash
# ident3(2026-08-18):三臂逐 token 同、5 题 x 每题 10 遍。一臂一进程,遍内 5 题
# 串行、遍间串行(计划 plans/archive/2026-08-18-ident3.md §3)。三臂各起一份并行跑。
# 用法: ident3_job.sh chat|noprobe|nofill <root> [reps=10] [n_tasks=5] [vllm_port=8114] [probe_url=http://localhost:8795]
#   root = 产物根目录(NFS),每臂每遍一个子目录 <root>/<arm>/rep<r>/
#   chat 臂的 outdir 名必须以 appworld_gptoss 收尾(采集器约定)
# 开跑前先过 ident3_gate.py:chat 端点的 prompt_token_ids 必须与 /render 逐 id 相等
# (vLLM 日期钉、return_token_ids 生效),不过就整臂拒跑。
set -u -o pipefail
ARM="${1:?arm 必填: chat|noprobe|nofill}"
ROOTDIR="${2:?root 必填(NFS 产物根目录)}"
REPS="${3:-10}"
NTASK="${4:-5}"
PORT="${5:-8114}"
PROBE="${6:-http://localhost:8795}"
FIRE_NTH="${IDENT3_FIRE_NTH:-5}"      # 伪触发:第几个句尾切口开火(计划 E1)
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
