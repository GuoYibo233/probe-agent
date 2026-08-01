#!/bin/bash
cd /home/y-guo/reproduce/new1
export CUDA_VISIBLE_DEVICES=8
/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_causal_callgen.py --data /home/y-guo/reproduce/new1/pipeline/data/aw_official_v1/q35 --out /home/y-guo/reproduce/new1/pipeline/runs/smoke/ro1aw_q35_cgen_smoke --smoke --readonly-env appworld --fire-head --env appworld 2>&1 | tee /home/y-guo/reproduce/new1/logs/ro1aw_q35_cgen_smoke.log
