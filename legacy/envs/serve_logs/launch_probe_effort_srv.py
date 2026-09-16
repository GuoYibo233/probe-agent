"""Dedicated service launcher for the two probe x effort arms (probe_low/probe_med).

Same parameters verbatim as launch_vllm_splice.py, only the card and port change; probe
three copies probe two's absolute-path launch method (the relative-path version has already
failed three times). The two arms share this pair of services:

  gpt-oss-120b -> tokyo108 H200 GPU 4, port 8119  (replica f)
  probe_server -> tokyo105 A6000 GPU 2, port 8792 (probe three, the new /render recognizes effort)

The old 8790 silently drops the effort field and renders as high -- the effort arm must
never point there.
"""
import shlex
import subprocess

VLLM = "/home/y-guo/reproduce/new1/envs/vllm-env/bin/vllm"
YMODELS = "/net/tokyo100-10g/data/str01_01/y-guo/models"
CACHE_ROOT = "/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache"
LOGDIR = f"{CACHE_ROOT}/logs"
CPROBE = "/home/y-guo/reproduce/new1/cprobe-env/bin/python"
PROBE_SRV = "/home/y-guo/reproduce/new1/pipeline/inject/probe_server.py"

JOBS = [
    ("tokyo108",
     "new1_effort_srv_f_t108g4",
     "LD_LIBRARY_PATH=/home/y-guo/reproduce/new1/envs/cuda-compat-13.0 "
     "VLLM_USE_FLASHINFER_SAMPLER=0 CUDA_DEVICE_ORDER=PCI_BUS_ID "
     f"VLLM_CACHE_ROOT={CACHE_ROOT} TRITON_CACHE_DIR={CACHE_ROOT}/triton "
     f"CUDA_VISIBLE_DEVICES=4 {VLLM} serve {YMODELS}/gpt-oss-120b "
     "--served-model-name gpt-oss-120b --port 8119 --host 0.0.0.0 "
     "--max-model-len 65536 --gpu-memory-utilization 0.92"),
    ("tokyo105",
     "new1_live_probe3_t105g2",
     f"CUDA_VISIBLE_DEVICES=2 {CPROBE} {PROBE_SRV} serve "
     "--port 8792 --device cuda:0"),
]


def main() -> None:
    for host, session, cmd in JOBS:
        probe = subprocess.run(
            ["ssh", "-n", host, f"tmux has-session -t {session} 2>/dev/null"])
        if probe.returncode == 0:
            print("SKIP (session exists):", session)
            continue
        log = f"{LOGDIR}/{session}.log"
        inner = f"{cmd} > {log} 2>&1"
        tmux = f"tmux new-session -d -s {session} {shlex.quote(inner)}"
        subprocess.run(["ssh", "-n", host, tmux], check=True)
        print(f"launched {session} on {host} -> log: {log}")


if __name__ == "__main__":
    main()
