#!/bin/bash
cd /home/y-guo/reproduce/new1
export CUDA_VISIBLE_DEVICES=2
/home/y-guo/reproduce/new1/mbert-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_mbert_tool.py --data /home/y-guo/reproduce/new1/pipeline/data/bfcl_mtb_v1/q36 --out /home/y-guo/reproduce/new1/pipeline/runs/ro1bf_q36_mtool --readonly-env bfcl --env bfcl 2>&1 | tee /home/y-guo/reproduce/new1/logs/ro1bf_q36_mtool.log
