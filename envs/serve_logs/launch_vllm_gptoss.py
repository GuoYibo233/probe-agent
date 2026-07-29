"""Launch the gpt-oss-120b vLLM server in tmux on tokyo108 (H200 GPU 5)."""

import shlex
import subprocess

WORKDIR = "/home/y-guo/reproduce/new1/envs/serve_logs"
VLLM = "/home/y-guo/reproduce/new1/envs/vllm-env/bin/vllm"
MODEL = "/net/tokyo100-10g/data/str01_01/y-guo/models/gpt-oss-120b"

GPU = 5
SESSION = "new1_vllm_t108_gptoss"

# No --reasoning-parser: vLLM 0.26 auto-sets "openai_gptoss" for GptOssForCausalLM
# (vllm/model_executor/models/config.py: reasoning_parser == "" -> "openai_gptoss").
CMD = (
    f"{VLLM} serve {MODEL} "
    "--served-model-name gpt-oss-120b "
    "--port 8103 --host 0.0.0.0 "
    "--gpu-memory-utilization 0.92"
)


def main() -> None:
    log = f"{WORKDIR}/{SESSION}.log"
    inner = (
        f"cd {WORKDIR} && "
        "LD_LIBRARY_PATH=/home/y-guo/reproduce/new1/envs/cuda-compat-13.0 "
        "VLLM_USE_FLASHINFER_SAMPLER=0 "
        "CUDA_DEVICE_ORDER=PCI_BUS_ID "
        f"CUDA_VISIBLE_DEVICES={GPU} {CMD} 2>&1 | tee {log}"
    )
    tmux = f"tmux new-session -d -s {SESSION} {shlex.quote(inner)}"
    subprocess.run(["ssh", "-n", "tokyo108", tmux], check=True)
    print("launched", SESSION, "-> log:", log)


if __name__ == "__main__":
    main()
