#!/bin/bash
# ro1 batch: bf ctool smoke — tokyo107 GPU1
cd /home/y-guo/reproduce/new1
CUDA_VISIBLE_DEVICES=1 /home/y-guo/reproduce/new1/cprobe-env/bin/python \
  pipeline/train/train_causal_tool.py \
  --base qwen \
  --data pipeline/data/bfcl_mtb_v1/q35 \
  --out pipeline/runs/smoke/ro1bf_q35_ctool_smoke \
  --smoke --readonly-env bfcl --align-tol 3e-4 --env bfcl \
  2>&1 | tee logs/ro1bf_q35_ctool_smoke.log
