"""Launch two vLLM servers in tmux on tokyo108 (H200 GPUs 3 and 4)."""
import subprocess
import shlex

WORKDIR = "/home/y-guo/reproduce/new1/envs/serve_logs"
VLLM = "/home/y-guo/reproduce/new1/envs/vllm-env/bin/vllm"
MODELS = "/net/tokyo100-10g/data/str01_01/zhou-y/models"

JOBS = [
    (
        3,
        "new1_vllm_t108g3",
        f"{VLLM} serve {MODELS}/Qwen3.5-27B "
        f"--served-model-name qwen3.5-27b {MODELS}/Qwen3.5-27B "
        "--port 8101 --host 0.0.0.0 "
        "--reasoning-parser deepseek_r1 --max-model-len 32768 "
        "--gpu-memory-utilization 0.92 "
        "--enable-auto-tool-choice --tool-call-parser qwen3_coder",
    ),
    (
        4,
        "new1_vllm_t108g4",
        f"{VLLM} serve {MODELS}/Qwen3.6-27B "
        f"--served-model-name qwen3.6-27b {MODELS}/Qwen3.6-27B "
        "--port 8102 --host 0.0.0.0 "
        "--reasoning-parser deepseek_r1 --max-model-len 32768 "
        "--gpu-memory-utilization 0.92 "
        "--enable-auto-tool-choice --tool-call-parser qwen3_coder",
    ),
]


def main() -> None:
    for gpu, session, cmd in JOBS:
        log = f"{WORKDIR}/{session}.log"
        inner = (
            f"cd {WORKDIR} && "
            "LD_LIBRARY_PATH=/home/y-guo/reproduce/new1/envs/cuda-compat-13.0 "
            "VLLM_USE_FLASHINFER_SAMPLER=0 "
            "CUDA_DEVICE_ORDER=PCI_BUS_ID "
            f"CUDA_VISIBLE_DEVICES={gpu} {cmd} 2>&1 | tee {log}"
        )
        tmux = f"tmux new-session -d -s {session} {shlex.quote(inner)}"
        subprocess.run(["ssh", "-n", "tokyo108", tmux], check=True)
        print("launched", session, "-> log:", log)


if __name__ == "__main__":
    main()
