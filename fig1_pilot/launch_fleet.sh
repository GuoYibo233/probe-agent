#!/bin/bash
# Launch one hf_server per GPU on tokyo108 (run ON tokyo108 or via ssh).
# GPU 0-2 = H100 96G (ports 8712-8714), GPU 3-5 = H200 144G (ports 8715-8717).
# Usage: launch_fleet.sh [gpu ids...]   (default: 0 1 3 4)

set -u
PY=/home/y-guo/reproduce/new1/jlens-env/bin/python
SRV=/home/y-guo/reproduce/new1/fig1_pilot/hf_server.py
LOGDIR=/home/y-guo/reproduce/new1/fig1_pilot/fleet_logs
mkdir -p "$LOGDIR"

GPUS=("$@")
[ ${#GPUS[@]} -eq 0 ] && GPUS=(0 1 3 4)

for g in "${GPUS[@]}"; do
  port=$((8712 + g))
  sess="fig1_hf_$g"
  tmux kill-session -t "$sess" 2>/dev/null
  tmux new-session -d -s "$sess" \
    "CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=$g $PY $SRV --port $port > $LOGDIR/hf_$g.log 2>&1"
  echo "launched gpu=$g port=$port session=$sess"
done
