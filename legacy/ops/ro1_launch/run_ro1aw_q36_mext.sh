#!/bin/bash
cd /home/y-guo/reproduce/new1
export CUDA_VISIBLE_DEVICES=0
/home/y-guo/reproduce/new1/mbert-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_mbert_extract.py --data /home/y-guo/reproduce/new1/pipeline/data/aw_official_v1/q36 --out /home/y-guo/reproduce/new1/pipeline/runs/ro1aw_q36_mext --grad-ckpt --readonly-env appworld --fire-head --env appworld 2>&1 | tee /home/y-guo/reproduce/new1/logs/ro1aw_q36_mext.log
