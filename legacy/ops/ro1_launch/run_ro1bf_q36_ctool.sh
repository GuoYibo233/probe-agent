#!/bin/bash
cd /home/y-guo/reproduce/new1
export CUDA_VISIBLE_DEVICES=3
/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_causal_tool.py --base qwen --data /home/y-guo/reproduce/new1/pipeline/data/bfcl_mtb_v1/q36 --out /home/y-guo/reproduce/new1/pipeline/runs/ro1bf_q36_ctool --align-tol 3e-4 --grad-ckpt --readonly-env bfcl --env bfcl 2>&1 | tee /home/y-guo/reproduce/new1/logs/ro1bf_q36_ctool.log
