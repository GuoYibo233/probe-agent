"""Launch the three-model serving trio for the full-scale collection run.

Independent from the pair/gptoss scripts: this brings up a *private* set of
servers on tokyo108 so the full-scale run does not contend with whatever the
other session is driving on port 8102.

  qwen3.5-27b   -> H200 GPU 3, port 8101
  gpt-oss-120b  -> H200 GPU 5, port 8103
  qwen3.6-27b   -> H100 GPU 0, port 8104   (private copy)

max-model-len raised to 65536 (calib used 32768) because full AppWorld dev
tasks and 40-step multi-room TALES episodes run longer than the 5-task calib.
"""
import shlex
import subprocess

HOST = "tokyo108"
WORKDIR = "/home/y-guo/reproduce/new1/envs/serve_logs"
VLLM = "/home/y-guo/reproduce/new1/envs/vllm-env/bin/vllm"
ZMODELS = "/net/tokyo100-10g/data/str01_01/zhou-y/models"
YMODELS = "/net/tokyo100-10g/data/str01_01/y-guo/models"

QWEN_FLAGS = (
    "--reasoning-parser deepseek_r1 --max-model-len 65536 "
    "--gpu-memory-utilization 0.92 "
    "--enable-auto-tool-choice --tool-call-parser qwen3_coder"
)

JOBS = [
    (3, "new1_srv_q35_t108g3",
     f"{VLLM} serve {ZMODELS}/Qwen3.5-27B --served-model-name qwen3.5-27b "
     f"--port 8101 --host 0.0.0.0 {QWEN_FLAGS}"),
    (5, "new1_srv_gptoss_t108g5",
     f"{VLLM} serve {YMODELS}/gpt-oss-120b --served-model-name gpt-oss-120b "
     f"--port 8103 --host 0.0.0.0 --gpu-memory-utilization 0.92"),
    (0, "new1_srv_q36_t108g0",
     f"{VLLM} serve {ZMODELS}/Qwen3.6-27B --served-model-name qwen3.6-27b "
     f"--port 8104 --host 0.0.0.0 {QWEN_FLAGS}"),
]


def main() -> None:
    for gpu, session, cmd in JOBS:
        probe = subprocess.run(
            ["ssh", "-n", HOST, f"tmux has-session -t {session} 2>/dev/null"])
        if probe.returncode == 0:
            print("SKIP (session exists):", session)
            continue
        log = f"{WORKDIR}/{session}.log"
        inner = (
            f"cd {WORKDIR} && "
            "LD_LIBRARY_PATH=/home/y-guo/reproduce/new1/envs/cuda-compat-13.0 "
            "VLLM_USE_FLASHINFER_SAMPLER=0 CUDA_DEVICE_ORDER=PCI_BUS_ID "
            f"CUDA_VISIBLE_DEVICES={gpu} {cmd} 2>&1 | tee {log}"
        )
        tmux = f"tmux new-session -d -s {session} {shlex.quote(inner)}"
        subprocess.run(["ssh", "-n", HOST, tmux], check=True)
        print("launched", session, "gpu", gpu, "-> log:", log)


if __name__ == "__main__":
    main()
