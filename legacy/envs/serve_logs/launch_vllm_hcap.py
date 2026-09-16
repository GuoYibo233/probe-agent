"""Service launcher for hcap (per-token harmony capture): one gpt-oss-120b on one H100 on tokyo108.

Configuration copied from the launch_vllm_awdiag.py version (the convention that worked on
2026-08-02): do not pass --max-model-len, let vLLM use the model's native 131072; only add
--gpu-memory-utilization 0.92. Environment variables copied the same way, not a single
character changed -- what this run needs to verify is whether the client's own harmony
assembly works end to end, so the service side must not introduce new variables.

  gpt-oss-120b -> H100 GPU 2, port 8113

GPU 2 was the only H100 found free in the 2026-08-06 live check (0/1/3/4 belong to zhou-y).
The port avoids the three historically reserved 8103/8106/8107, to avoid colliding with
anyone else's leftovers.

Usage: python3 launch_vllm_hcap.py
"""
import shlex
import subprocess

HOST = "tokyo108"
GPU = 2
PORT = 8113
SESSION = f"new1_hcap_srv_t108g{GPU}"
WORKDIR = "/home/y-guo/reproduce/new1/envs/serve_logs"
VLLM = "/home/y-guo/reproduce/new1/envs/vllm-env/bin/vllm"
YMODELS = "/net/tokyo100-10g/data/str01_01/y-guo/models"

CACHE_ROOT = "/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache"
LOGDIR = f"{CACHE_ROOT}/logs"
LOG = f"{LOGDIR}/new1_hcap_srv.log"


def main() -> None:
    subprocess.run(["ssh", "-n", HOST, f"mkdir -p {LOGDIR}"], check=True)
    probe = subprocess.run(
        ["ssh", "-n", HOST, f"tmux has-session -t {SESSION} 2>/dev/null"])
    if probe.returncode == 0:
        print("SKIP (session exists):", SESSION)
        return
    cmd = (
        f"{VLLM} serve {YMODELS}/gpt-oss-120b "
        f"--served-model-name gpt-oss-120b "
        f"--port {PORT} --host 0.0.0.0 --gpu-memory-utilization 0.92"
    )
    inner = (
        f"cd {WORKDIR} && "
        "LD_LIBRARY_PATH=/home/y-guo/reproduce/new1/envs/cuda-compat-13.0 "
        "VLLM_USE_FLASHINFER_SAMPLER=0 CUDA_DEVICE_ORDER=PCI_BUS_ID "
        f"VLLM_CACHE_ROOT={CACHE_ROOT} TRITON_CACHE_DIR={CACHE_ROOT}/triton "
        f"CUDA_VISIBLE_DEVICES={GPU} {cmd} > {LOG} 2>&1"
    )
    tmux = f"tmux new-session -d -s {SESSION} {shlex.quote(inner)}"
    subprocess.run(["ssh", "-n", HOST, tmux], check=True)
    print(f"launched {SESSION} gpu {GPU} port {PORT} -> log: {LOG}")


if __name__ == "__main__":
    main()
