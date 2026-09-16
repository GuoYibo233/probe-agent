"""Third batch of gpt-oss-120b services for the run segment of the θ sweep: replaces the two
replicas that died on the two H200s.

Why this batch is needed: between 2026-08-01 04:41-05:15, writes to /home/y-guo repeatedly
raised `OSError: [Errno 122] Disk quota exceeded`, which killed the two services in the first
batch -- replica B's (GPU 4, 8112) log stopped mid-sentence with no error at all (the tee in
`vllm ... | tee log` exits once it cannot write to NFS, and vllm then dies with EPIPE), while
replica C (GPU 5, 8113) left complete evidence: EngineCore hit Errno 122 on
`os.makedirs('/home/y-guo/.cache/vllm/torch_compile_cache/.../inductor_cache')`, the engine
went fatal, every subsequent request got 500, and the process exited. The two H200s sat idle
as a result.

This batch uses **a new session name and new ports** (not reusing 8112/8113), to avoid mixing
up old and new in the logs and the job ledger:

  gpt-oss-120b -> H200 GPU 4, port 8117   (replica G)
  gpt-oss-120b -> H200 GPU 5, port 8118   (replica H)

Parameters are **identical, verbatim, to the first and second batches** (model path /
served-model-name / max-model-len 65536 / gpu-memory-utilization 0.92 / the three environment
variables), so the service-side convention is consistent across all six θ points.
"""
import shlex
import subprocess

HOST = "tokyo108"
WORKDIR = "/home/y-guo/reproduce/new1/envs/serve_logs"
VLLM = "/home/y-guo/reproduce/new1/envs/vllm-env/bin/vllm"
YMODELS = "/net/tokyo100-10g/data/str01_01/y-guo/models"

GPTOSS_FLAGS = "--max-model-len 65536 --gpu-memory-utilization 0.92"

JOBS = [
    (4, 8117, "new1_thsw_srv_g_t108g4"),
    (5, 8118, "new1_thsw_srv_h_t108g5"),
]


def main() -> None:
    for gpu, port, session in JOBS:
        probe = subprocess.run(
            ["ssh", "-n", HOST, f"tmux has-session -t {session} 2>/dev/null"])
        if probe.returncode == 0:
            print("SKIP (session exists):", session)
            continue
        log = f"{WORKDIR}/{session}.log"
        cmd = (
            f"{VLLM} serve {YMODELS}/gpt-oss-120b "
            f"--served-model-name gpt-oss-120b "
            f"--port {port} --host 0.0.0.0 {GPTOSS_FLAGS}"
        )
        inner = (
            f"cd {WORKDIR} && "
            "LD_LIBRARY_PATH=/home/y-guo/reproduce/new1/envs/cuda-compat-13.0 "
            "VLLM_USE_FLASHINFER_SAMPLER=0 CUDA_DEVICE_ORDER=PCI_BUS_ID "
            f"CUDA_VISIBLE_DEVICES={gpu} {cmd} 2>&1 | tee {log}"
        )
        tmux = f"tmux new-session -d -s {session} {shlex.quote(inner)}"
        subprocess.run(["ssh", "-n", HOST, tmux], check=True)
        print(f"launched {session} gpu {gpu} port {port} -> log: {log}")


if __name__ == "__main__":
    main()
