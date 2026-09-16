#!/bin/bash
# vLLM server for gpt-oss-120b on tokyo108 H200 GPU 5.
# LD_LIBRARY_PATH points at the CUDA 13.0 forward-compat libs so vllm-env's
# torch runs on this host's older driver (data-center cards only).
# No --reasoning-parser: vLLM 0.26 auto-sets "openai_gptoss" for GptOssForCausalLM
# (see vllm/model_executor/models/config.py).
cd /home/y-guo/reproduce/new1/envs/serve_logs || exit 1

export LD_LIBRARY_PATH=/home/y-guo/reproduce/new1/envs/cuda-compat-13.0
export VLLM_USE_FLASHINFER_SAMPLER=0
export CUDA_DEVICE_ORDER=PCI_BUS_ID
export CUDA_VISIBLE_DEVICES=5

/home/y-guo/reproduce/new1/envs/vllm-env/bin/vllm serve \
  /net/tokyo100-10g/data/str01_01/y-guo/models/gpt-oss-120b \
  --served-model-name gpt-oss-120b \
  --port 8103 --host 0.0.0.0 \
  --gpu-memory-utilization 0.92 \
  2>&1 | tee /home/y-guo/reproduce/new1/envs/serve_logs/new1_vllm_t108_gptoss.log
