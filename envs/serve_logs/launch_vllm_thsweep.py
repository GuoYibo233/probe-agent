"""Service launcher for gpt-oss-120b dedicated to the run segment of the θ-sweep injection
experiment: three replicas.

Independent from the three services used for c2_alfworld collection (which occupy tokyo108
GPU 0/1/2, ports 8101/8102/8103), so the ports move to 8111/8112/8113 and the cards move to
three H200s; the two batches of jobs do not preempt each other.

  gpt-oss-120b -> H200 GPU 3, port 8111   (replica A)
  gpt-oss-120b -> H200 GPU 4, port 8112   (replica B)
  gpt-oss-120b -> H200 GPU 5, port 8113   (replica C)

max-model-len is pinned to 65536: the injection-replay continuation has --max-tokens 8192,
and the prompt also carries the whole trajectory history, so the default short context would
truncate and error out. The model config's max_position_embeddings is 131072, and 65536 is
within range.
"""
import shlex
import subprocess

HOST = "tokyo108"
WORKDIR = "/home/y-guo/reproduce/new1/envs/serve_logs"
VLLM = "/home/y-guo/reproduce/new1/envs/vllm-env/bin/vllm"
YMODELS = "/net/tokyo100-10g/data/str01_01/y-guo/models"

GPTOSS_FLAGS = "--max-model-len 65536 --gpu-memory-utilization 0.92"

JOBS = [
    (3, 8111, "new1_thsw_srv_a_t108g3"),
    (4, 8112, "new1_thsw_srv_b_t108g4"),
    (5, 8113, "new1_thsw_srv_c_t108g5"),
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
