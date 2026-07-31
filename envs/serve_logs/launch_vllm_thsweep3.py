"""θ 扫描 run 段的第三批 gpt-oss-120b 服务：补两张 H200 上死掉的副本。

为什么要这一批：2026-08-01 04:41-05:15 之间，/home/y-guo 的写入连续抛
`OSError: [Errno 122] Disk quota exceeded`，把第一批的两个服务打死了——
副本 B(GPU 4, 8112) 的日志停在半句上没有任何报错（`vllm ... | tee log` 的
tee 写不进 NFS 就退出，vllm 随后死于 EPIPE），副本 C(GPU 5, 8113) 留下了
完整证据：EngineCore 在 `os.makedirs('/home/y-guo/.cache/vllm/torch_compile_cache/
.../inductor_cache')` 上拿到 Errno 122，引擎 fatal，之后所有请求 500，进程退出。
两张 H200 因此空转。

这一批用**新的会话名与端口**（不复用 8112/8113），免得日志和台账里新旧混淆：

  gpt-oss-120b -> H200 GPU 4, port 8117   (副本 G)
  gpt-oss-120b -> H200 GPU 5, port 8118   (副本 H)

参数与第一批、第二批**逐字一致**（模型路径 / served-model-name /
max-model-len 65536 / gpu-memory-utilization 0.92 / 三个环境变量），
六个 θ 点的服务侧口径才齐。
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
