"""hcap(harmony 逐 token 抓取)的服务发射器:tokyo108 一张 H100 一个 gpt-oss-120b。

配置照抄 launch_vllm_awdiag.py 那一版(2026-08-02 跑通过的口径):
不给 --max-model-len,让 vLLM 用模型 native 131072;只加
--gpu-memory-utilization 0.92。环境变量同样照抄,一个字不改——
这次要验的是客户端自拼 harmony 能不能走通,服务侧不引入新变量。

  gpt-oss-120b -> H100 GPU 2, port 8113

GPU 2 是 2026-08-06 实探唯一空着的 H100(0/1/3/4 是 zhou-y 的)。
端口避开 8103/8106/8107 那三个历史约定,免得跟别人的残留撞。

用法: python3 launch_vllm_hcap.py
"""
import shlex
import subprocess

HOST = "tokyo108"
GPU = 2
PORT = 8113
SESSION = f"new1_hcap_srv_t108g{GPU}"
WORKDIR = "/home/y-guo/reproduce/new1/envs/serve_logs"
VLLM = "/home/y-guo/reproduce/new1/envs/vllm-env/bin/vllm"
YMODELS = "/net/tokyo100-10g/data/str01_01/y-guo/models"

CACHE_ROOT = "/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache"
LOGDIR = f"{CACHE_ROOT}/logs"
LOG = f"{LOGDIR}/new1_hcap_srv.log"


def main() -> None:
    subprocess.run(["ssh", "-n", HOST, f"mkdir -p {LOGDIR}"], check=True)
    probe = subprocess.run(
        ["ssh", "-n", HOST, f"tmux has-session -t {SESSION} 2>/dev/null"])
    if probe.returncode == 0:
        print("SKIP (session exists):", SESSION)
        return
    cmd = (
        f"{VLLM} serve {YMODELS}/gpt-oss-120b "
        f"--served-model-name gpt-oss-120b "
        f"--port {PORT} --host 0.0.0.0 --gpu-memory-utilization 0.92"
    )
    inner = (
        f"cd {WORKDIR} && "
        "LD_LIBRARY_PATH=/home/y-guo/reproduce/new1/envs/cuda-compat-13.0 "
        "VLLM_USE_FLASHINFER_SAMPLER=0 CUDA_DEVICE_ORDER=PCI_BUS_ID "
        f"VLLM_CACHE_ROOT={CACHE_ROOT} TRITON_CACHE_DIR={CACHE_ROOT}/triton "
        f"CUDA_VISIBLE_DEVICES={GPU} {cmd} > {LOG} 2>&1"
    )
    tmux = f"tmux new-session -d -s {SESSION} {shlex.quote(inner)}"
    subprocess.run(["ssh", "-n", HOST, tmux], check=True)
    print(f"launched {SESSION} gpu {GPU} port {PORT} -> log: {LOG}")


if __name__ == "__main__":
    main()
