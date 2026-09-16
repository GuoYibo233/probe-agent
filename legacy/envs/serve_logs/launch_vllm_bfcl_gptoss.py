"""Service launcher for the bfcl_gptoss top-up collection batch: a single gpt-oss-120b replica.

  gpt-oss-120b -> tokyo108 H100 GPU 0, port 8103

Difference from launch_vllm_topup.py: --served-model-name is not set -- the BFCL client
sends requests using the --local-model-path path as the model name, and when no name is
set vLLM's model id is the path itself, so the two sides line up naturally.
"""
import shlex
import subprocess

HOST = "tokyo108"
GPU = 0
SESSION = "new1_srv_gptoss_bfcl_t108g0"
WORKDIR = "/home/y-guo/reproduce/new1/envs/serve_logs"
VLLM = "/home/y-guo/reproduce/new1/envs/vllm-env/bin/vllm"
MODEL = "/net/tokyo100-10g/data/str01_01/y-guo/models/gpt-oss-120b"

CMD = (f"{VLLM} serve {MODEL} --port 8103 --host 0.0.0.0 "
       "--gpu-memory-utilization 0.92")


def main() -> None:
    probe = subprocess.run(
        ["ssh", "-n", HOST, f"tmux has-session -t {SESSION} 2>/dev/null"])
    if probe.returncode == 0:
        print("SKIP (session exists):", SESSION)
        return
    log = f"{WORKDIR}/{SESSION}.log"
    inner = (
        f"cd {WORKDIR} && "
        "LD_LIBRARY_PATH=/home/y-guo/reproduce/new1/envs/cuda-compat-13.0 "
        "VLLM_USE_FLASHINFER_SAMPLER=0 CUDA_DEVICE_ORDER=PCI_BUS_ID "
        f"CUDA_VISIBLE_DEVICES={GPU} {CMD} 2>&1 | tee {log}"
    )
    tmux = f"tmux new-session -d -s {SESSION} {shlex.quote(inner)}"
    subprocess.run(["ssh", "-n", HOST, tmux], check=True)
    print("launched", SESSION, "gpu", GPU, "-> log:", log)


if __name__ == "__main__":
    main()
