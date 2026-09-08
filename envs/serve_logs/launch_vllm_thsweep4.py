"""Replacement launcher for the run-segment θ-sweep services: restarts the two replicas on
8112 / 8113.

Same parameters verbatim as launch_vllm_thsweep.py (same model, same --served-model-name,
--max-model-len 65536, --gpu-memory-utilization 0.92, the same three environment variables),
changing only the two things that killed the previous round:

1. **Compile cache moved out of /home**. /home/y-guo has an NFS server-side quota (df does
   not show it), and in the previous round 8112/8113 died exactly from filling it up while
   writing the torch compile cache to ~/.cache/vllm. VLLM_CACHE_ROOT now points to /net
   (44T free), and TRITON_CACHE_DIR moves along with it (triton's own JIT cache defaults to
   ~/.triton, which eats the /home quota the same way). The old cache on the H200s has
   already been corrupted, so this round is bound to trigger one full recompile, 5-10 minutes.
2. **Logs no longer go through `| tee`**. tee exits once it cannot write to /home, and vllm
   then dies with EPIPE right after -- the associated cause of death in the previous round.
   Changed to shell redirection instead, with logs also going to /net.

  gpt-oss-120b -> H200 GPU 4, port 8112   (replica B2)
  gpt-oss-120b -> H200 GPU 5, port 8113   (replica C2)
"""
import shlex
import subprocess

HOST = "tokyo108"
WORKDIR = "/home/y-guo/reproduce/new1/envs/serve_logs"
VLLM = "/home/y-guo/reproduce/new1/envs/vllm-env/bin/vllm"
YMODELS = "/net/tokyo100-10g/data/str01_01/y-guo/models"

CACHE_ROOT = "/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache"
LOGDIR = f"{CACHE_ROOT}/logs"

GPTOSS_FLAGS = "--max-model-len 65536 --gpu-memory-utilization 0.92"

JOBS = [
    (4, 8112, "new1_thsw_srv_b2_t108g4"),
    (5, 8113, "new1_thsw_srv_c2_t108g5"),
]


def main() -> None:
    subprocess.run(["ssh", "-n", HOST, f"mkdir -p {LOGDIR}"], check=True)
    for gpu, port, session in JOBS:
        probe = subprocess.run(
            ["ssh", "-n", HOST, f"tmux has-session -t {session} 2>/dev/null"])
        if probe.returncode == 0:
            print("SKIP (session exists):", session)
            continue
        log = f"{LOGDIR}/{session}.log"
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
