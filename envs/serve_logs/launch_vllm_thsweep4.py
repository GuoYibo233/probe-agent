"""θ 扫描 run 段服务补位发射器：重启 8112 / 8113 两个副本。

与 launch_vllm_thsweep.py 逐字同参（同模型、同 --served-model-name、
--max-model-len 65536、--gpu-memory-utilization 0.92、同三个环境变量），
只改两件让上一轮死掉的事：

1. **编译缓存挪出 /home**。/home/y-guo 有 NFS 服务端配额（df 看不出来），
   上一轮 8112/8113 就是死在往 ~/.cache/vllm 写 torch 编译缓存时写满。
   VLLM_CACHE_ROOT 指到 /net（44T 空闲），TRITON_CACHE_DIR 一并挪走
   （triton 自己的 JIT 缓存默认在 ~/.triton，同样吃 /home 配额）。
   H200 那份旧缓存已被写坏，本轮必然触发一次完整重编译，5-10 分钟。
2. **日志不走 `| tee`**。tee 写不进 /home 就退出，vllm 随即死于 EPIPE ——
   上一轮的连带死因。改成 shell 重定向，日志也放 /net。

  gpt-oss-120b -> H200 GPU 4, port 8112   (副本 B2)
  gpt-oss-120b -> H200 GPU 5, port 8113   (副本 C2)
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
