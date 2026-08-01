"""拼回八臂 run 段服务发射器:tokyo108 三张空 H100 各起一个 gpt-oss-120b。

与 launch_vllm_thsweep4.py 逐字同参(同模型、同 --served-model-name、
--max-model-len 65536、--gpu-memory-utilization 0.92、同三个环境变量、
编译缓存与日志都走 /net —— /home 有 NFS 服务端配额,写满会连死 vllm),
只换卡与端口:

  gpt-oss-120b -> H100 GPU 0, port 8114   (shard s0: nofill,skel_switch)
  gpt-oss-120b -> H100 GPU 1, port 8115   (shard s1: inject,inject_stop,
                                           switch_only,skel_b)
  gpt-oss-120b -> H100 GPU 2, port 8116   (shard s2: skel_bare,skel_a)
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
    (0, 8114, "new1_splice_srv_a_t108g0"),
    (1, 8115, "new1_splice_srv_b_t108g1"),
    (2, 8116, "new1_splice_srv_c_t108g2"),
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
