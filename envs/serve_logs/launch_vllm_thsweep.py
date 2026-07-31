"""θ 扫描注入实验 run 段专用的 gpt-oss-120b 服务发射器：三副本。

独立于 c2_alfworld 采集用的那三个服务（占 tokyo108 GPU 0/1/2、端口
8101/8102/8103），所以端口挪到 8111/8112/8113、卡挪到三张 H200，两批任务
互不抢占。

  gpt-oss-120b -> H200 GPU 3, port 8111   (副本 A)
  gpt-oss-120b -> H200 GPU 4, port 8112   (副本 B)
  gpt-oss-120b -> H200 GPU 5, port 8113   (副本 C)

max-model-len 钉 65536：注入回放的续写 --max-tokens 8192，prompt 还带整段
历史轨迹，默认短上下文会截断报错。模型 config 的 max_position_embeddings
是 131072，65536 在范围内。
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
