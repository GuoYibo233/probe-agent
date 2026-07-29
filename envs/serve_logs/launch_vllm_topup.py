"""full_v2_topup 补采批次的服务发射器:两模型各双副本,q3.5 不参与。

  qwen3.6-27b   -> H200 GPU 3, port 8104   (主副本,沿用老端口)
  qwen3.6-27b   -> H100 GPU 0, port 8105   (副本 B)
  gpt-oss-120b  -> H200 GPU 4, port 8103   (主副本,沿用老端口)
  gpt-oss-120b  -> H200 GPU 5, port 8106   (副本 B)

tokyo108 GPU1/2 被他人占用,不碰。
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
    (3, "new1_srv_q36_t108g3",
     f"{VLLM} serve {ZMODELS}/Qwen3.6-27B --served-model-name qwen3.6-27b "
     f"--port 8104 --host 0.0.0.0 {QWEN_FLAGS}"),
    # H100 95G: Qwen3.6 的 Mamba cache 只够 612 块,默认 max_num_seqs=1024 会崩
    (0, "new1_srv_q36b_t108g0",
     f"{VLLM} serve {ZMODELS}/Qwen3.6-27B --served-model-name qwen3.6-27b "
     f"--port 8105 --host 0.0.0.0 {QWEN_FLAGS} --max-num-seqs 512"),
    (4, "new1_srv_gptoss_t108g4",
     f"{VLLM} serve {YMODELS}/gpt-oss-120b --served-model-name gpt-oss-120b "
     f"--port 8103 --host 0.0.0.0 --gpu-memory-utilization 0.92"),
    (5, "new1_srv_gptossb_t108g5",
     f"{VLLM} serve {YMODELS}/gpt-oss-120b --served-model-name gpt-oss-120b "
     f"--port 8106 --host 0.0.0.0 --gpu-memory-utilization 0.92"),
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
