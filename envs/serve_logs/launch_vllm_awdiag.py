"""w0 复现诊断批(aw_pathdiag)的服务发射器:tokyo108 三张 H100 各一个 gpt-oss-120b。

**关键口径:不给 --max-model-len**,让 vLLM 用模型 native 131072——
这是复刻 w0 采集时 launch_vllm_w0.py 里 gpt-oss 两条 JOBS 的原样配置
(那两条只有 --gpu-memory-utilization 0.92)。65536 就是发错了,本批诊断
要查的正是"分段续写/65k 上下文"这条嫌疑链,服务侧不能先把它焊死。

  gpt-oss-120b -> H100 GPU 0, port 8103   (副本 A)
  gpt-oss-120b -> H100 GPU 1, port 8106   (副本 B)
  gpt-oss-120b -> H100 GPU 2, port 8107   (副本 C)

环境变量照抄 launch_vllm_w0.py(cuda-compat/FLASHINFER/PCI_BUS_ID),另加
launch_vllm_splice.py 的缓存重定向(VLLM_CACHE_ROOT/TRITON_CACHE_DIR 进 /net
——/home 有 NFS 服务端配额,写满会连死 vllm)。缓存路径不改模型行为。

客户端两臂见 awdiag_job.sh(PORTS=8103/8106/8107)。
用法: python3 launch_vllm_awdiag.py
"""
import shlex
import subprocess

HOST = "tokyo108"
WORKDIR = "/home/y-guo/reproduce/new1/envs/serve_logs"
VLLM = "/home/y-guo/reproduce/new1/envs/vllm-env/bin/vllm"
YMODELS = "/net/tokyo100-10g/data/str01_01/y-guo/models"

CACHE_ROOT = "/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache"
LOGDIR = f"{CACHE_ROOT}/logs"

# 无 --max-model-len:native 131072
GPTOSS_FLAGS = "--gpu-memory-utilization 0.92"

JOBS = [
    (0, 8103, "new1_diag_srv_a_t108g0", f"{LOGDIR}/new1_diag_srv_a.log"),
    (1, 8106, "new1_diag_srv_b_t108g1", f"{LOGDIR}/new1_diag_srv_b.log"),
    (2, 8107, "new1_diag_srv_c_t108g2", f"{LOGDIR}/new1_diag_srv_c.log"),
]


def main() -> None:
    subprocess.run(["ssh", "-n", HOST, f"mkdir -p {LOGDIR}"], check=True)
    for gpu, port, session, log in JOBS:
        probe = subprocess.run(
            ["ssh", "-n", HOST, f"tmux has-session -t {session} 2>/dev/null"])
        if probe.returncode == 0:
            print("SKIP (session exists):", session)
            continue
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
