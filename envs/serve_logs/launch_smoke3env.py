#!/usr/bin/env python3
"""Launch the short-lived gpt-oss-120b smoke server on tokyo108 H200 idx 3.

Env vars follow the working recipe in run_gptoss.sh:
  - LD_LIBRARY_PATH -> CUDA 13.0 forward-compat libs (vllm-env torch needs a
    newer driver than tokyo108's 570.195.03)
  - CUDA_DEVICE_ORDER=PCI_BUS_ID so CUDA_VISIBLE_DEVICES matches nvidia-smi idx
  - VLLM_USE_FLASHINFER_SAMPLER=0
"""
import shlex
import subprocess
import sys

HOST = "tokyo108"
GPU = "3"
SESSION = "new1_smoke3env_t108g3"
LOG = "/home/y-guo/reproduce/new1/envs/serve_logs/new1_smoke3env_t108g3.log"
WORKDIR = "/home/y-guo/reproduce/new1"
VLLM = "/home/y-guo/reproduce/new1/envs/vllm-env/bin/vllm"
MODEL = "/net/tokyo100-10g/data/str01_01/y-guo/models/gpt-oss-120b"
COMPAT = "/home/y-guo/reproduce/new1/envs/cuda-compat-13.0"

extra = sys.argv[1:]  # optional extra vllm flags

cmd = [
    VLLM, "serve", MODEL,
    "--served-model-name", "gpt-oss-120b",
    "--host", "0.0.0.0",
    "--port", "8127",
    "--gpu-memory-utilization", "0.92",
] + extra

inner = (
    f"cd {WORKDIR} && "
    f"export LD_LIBRARY_PATH={COMPAT} && "
    f"export VLLM_USE_FLASHINFER_SAMPLER=0 && "
    f"export CUDA_DEVICE_ORDER=PCI_BUS_ID && "
    f"CUDA_VISIBLE_DEVICES={GPU} " + " ".join(shlex.quote(c) for c in cmd) +
    f" 2>&1 | tee {LOG}"
)

tmux = f"tmux new-session -d -s {SESSION} {shlex.quote(inner)}"
print("INNER:", inner)
subprocess.run(["ssh", "-n", HOST, tmux], check=True)
print("launched", SESSION, "on", HOST)
