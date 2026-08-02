#!/bin/bash
# w0 复现诊断双臂(2026-08-02,排查活跑 noprobe 17.3% vs w0 28.6% 的系统性来源):
#   chat    = w0 原采集脚本(run_appworld.py --api chat)今天原样重跑 168 题。
#             复现 ~28.6% => 活跑驱动有真实口径差;也只有 ~17% => w0 不可复现。
#   np1shot = 活跑驱动 noprobe 单发版(--tail-tokens 8192,每步一枪,无分段缝)。
#             对齐 chat => v2 的缺口来自分段续写/65k 上下文;仍 ~17% => 驱动别处有毒。
# 用法: awdiag_job.sh chat|np1shot   (tmux 里整段跑)
# 服务前提:tokyo108 8103/8106/8107 三个 gpt-oss **native 131k(无 --max-model-len,
#          与 w0 采集时 launch_vllm_w0.py 同款)**;tokyo105:8790 探针(/render 用)。
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
    # 动态领题:清票根,没写 final 的题全部重新开抢(claim() 的约定)
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
    # 修复后解析 + 每步一枪(无分段缝):与 v3 noprobe 只差 tail 8192,
    # 隔离"1024 分段缝"对残余 answer 乱塞(v3np 22 题纯冤死)的贡献。
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
