#!/bin/bash
# ro1 batch: aw ctool smoke — tokyo105 GPU1
cd /home/y-guo/reproduce/new1
CUDA_VISIBLE_DEVICES=1 /home/y-guo/reproduce/new1/cprobe-env/bin/python \
  pipeline/train/train_causal_tool.py \
  --base qwen \
  --data pipeline/data/aw_official_v1/q35 \
  --out pipeline/runs/smoke/ro1aw_q35_ctool_smoke \
  --smoke --readonly-env appworld --align-tol 3e-4 --env appworld \
  2>&1 | tee logs/ro1aw_q35_ctool_smoke.log
