#!/bin/bash
# 1) wait for cu128 torch to land in fig1-env (max ~15 min)
for i in $(seq 1 180); do
  v=$(/home/y-guo/reproduce/new1/fig1_pilot/fig1-env/bin/python -c "import torch; print(torch.__version__)" 2>/dev/null)
  case "$v" in *cu128*) echo "TORCH_OK $v"; break;; esac
  sleep 5
done
case "$v" in *cu128*) ;; *) echo "TORCH_TIMEOUT last=$v"; exit 1;; esac
# 2) relaunch vLLM on tokyo108 H200 (physical card 3)
ssh -o BatchMode=yes tokyo108 "tmux kill-session -t fig1_vllm 2>/dev/null; tmux new-session -d -s fig1_vllm 'CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=3 /home/y-guo/reproduce/new1/fig1_pilot/fig1-env/bin/vllm serve Qwen/Qwen3.5-4B --port 8712 --max-model-len 16384 > /home/y-guo/reproduce/new1/fig1_pilot/vllm_serve.log 2>&1'" || { echo SSH_FAIL; exit 1; }
echo "VLLM_LAUNCHED"
# 3) wait for server ready (max ~10 min), fail fast on engine crash
for i in $(seq 1 120); do
  if curl -s -m 3 http://tokyo108:8712/v1/models | grep -q Qwen; then echo "SERVER_READY"; ok=1; break; fi
  if ssh -o BatchMode=yes tokyo108 "grep -q 'Engine core initialization failed' /home/y-guo/reproduce/new1/fig1_pilot/vllm_serve.log" 2>/dev/null; then echo "ENGINE_CRASH"; exit 1; fi
  sleep 5
done
[ "$ok" = 1 ] || { echo "SERVER_TIMEOUT"; exit 1; }
# 4) run the one-episode agent smoke
./fig1-env/bin/python agent_smoke.py 2>&1 | tail -15
