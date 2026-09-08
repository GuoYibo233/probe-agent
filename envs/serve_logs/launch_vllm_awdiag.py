"""Service launcher for the w0-reproduction diagnostic batch (aw_pathdiag): one gpt-oss-120b
on each of three H100s on tokyo108.

**Key convention: do not pass --max-model-len**, let vLLM use the model's native 131072 --
this reproduces the exact configuration of the two gpt-oss JOBS entries in launch_vllm_w0.py
from the w0 collection (those two entries only had --gpu-memory-utilization 0.92). 65536 was
simply a mistake; this diagnostic batch exists precisely to check the "chunked continuation /
65k context" suspect chain, so the service side must not weld that shut in advance.

  gpt-oss-120b -> H100 GPU 0, port 8103   (replica A)
  gpt-oss-120b -> H100 GPU 1, port 8106   (replica B)
  gpt-oss-120b -> H100 GPU 2, port 8107   (replica C)

Environment variables copied from launch_vllm_w0.py (cuda-compat/FLASHINFER/PCI_BUS_ID), plus
the cache redirection from launch_vllm_splice.py (VLLM_CACHE_ROOT/TRITON_CACHE_DIR into /net
-- /home has an NFS server-side quota, and filling it can kill vllm too). The cache path does
not change model behavior.

The two client arms are in awdiag_job.sh (PORTS=8103/8106/8107).
Usage: python3 launch_vllm_awdiag.py
"""
import shlex
import subprocess

HOST = "tokyo108"
WORKDIR = "/home/y-guo/reproduce/new1/envs/serve_logs"
VLLM = "/home/y-guo/reproduce/new1/envs/vllm-env/bin/vllm"
YMODELS = "/net/tokyo100-10g/data/str01_01/y-guo/models"

CACHE_ROOT = "/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache"
LOGDIR = f"{CACHE_ROOT}/logs"

# No --max-model-len: native 131072
GPTOSS_FLAGS = "--gpu-memory-utilization 0.92"

JOBS = [
    (0, 8103, "new1_diag_srv_a_t108g0", f"{LOGDIR}/new1_diag_srv_a.log"),
    (1, 8106, "new1_diag_srv_b_t108g1", f"{LOGDIR}/new1_diag_srv_b.log"),
    (2, 8107, "new1_diag_srv_c_t108g2", f"{LOGDIR}/new1_diag_srv_c.log"),
]


def main() -> None:
    subprocess.run(["ssh", "-n", HOST, f"mkdir -p {LOGDIR}"], check=True)
    for gpu, port, session, log in JOBS:
        probe = subprocess.run(
            ["ssh", "-n", HOST, f"tmux has-session -t {session} 2>/dev/null"])
        if probe.returncode == 0:
            print("SKIP (session exists):", session)
            continue
        cmd = (
            f"{VLLM} serve {YMODELS}/gpt-oss-120b "
            f"--served-model-name gpt-oss-120b "
            f"--port {port} --host 0.0.0.0 {GPTOSS_FLAGS}"
        )
        inner = (
            f"cd {WORKDIR} && "
            "LD_LIBRARY_PATH=/home/y-guo/reproduce/new1/envs/cuda-compat-13.0 "
            "VLLM_USE_FLASHINFER_SAMPLER=0 CUDA_DEVICE_ORDER=PCI_BUS_ID "
            f"VLLM_CACHE_ROOT={CACHE_ROOT} TRITON_CACHE_DIR={CACHE_ROOT}/triton "
            f"CUDA_VISIBLE_DEVICES={gpu} {cmd} > {log} 2>&1"
        )
        tmux = f"tmux new-session -d -s {session} {shlex.quote(inner)}"
        subprocess.run(["ssh", "-n", HOST, tmux], check=True)
        print(f"launched {session} gpu {gpu} port {port} -> log: {log}")


if __name__ == "__main__":
    main()
