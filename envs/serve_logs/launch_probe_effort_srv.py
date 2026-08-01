"""probe×effort 两臂(probe_low/probe_med)的专属服务发射器。

与 launch_vllm_splice.py 逐字同参,只换卡与端口;探针三号照抄探针二号的
绝对路径发射法(相对路径已经栽过三次)。两臂共用这一对服务:

  gpt-oss-120b -> tokyo108 H200 GPU 4, port 8119  (副本 f)
  probe_server -> tokyo105 A6000 GPU 2, port 8792 (探针三号,新 /render 认 effort)

老 8790 会静默丢 effort 字段按 high 渲染——effort 臂绝不能指过去。
"""
import shlex
import subprocess

VLLM = "/home/y-guo/reproduce/new1/envs/vllm-env/bin/vllm"
YMODELS = "/net/tokyo100-10g/data/str01_01/y-guo/models"
CACHE_ROOT = "/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache"
LOGDIR = f"{CACHE_ROOT}/logs"
CPROBE = "/home/y-guo/reproduce/new1/cprobe-env/bin/python"
PROBE_SRV = "/home/y-guo/reproduce/new1/pipeline/inject/probe_server.py"

JOBS = [
    ("tokyo108",
     "new1_effort_srv_f_t108g4",
     "LD_LIBRARY_PATH=/home/y-guo/reproduce/new1/envs/cuda-compat-13.0 "
     "VLLM_USE_FLASHINFER_SAMPLER=0 CUDA_DEVICE_ORDER=PCI_BUS_ID "
     f"VLLM_CACHE_ROOT={CACHE_ROOT} TRITON_CACHE_DIR={CACHE_ROOT}/triton "
     f"CUDA_VISIBLE_DEVICES=4 {VLLM} serve {YMODELS}/gpt-oss-120b "
     "--served-model-name gpt-oss-120b --port 8119 --host 0.0.0.0 "
     "--max-model-len 65536 --gpu-memory-utilization 0.92"),
    ("tokyo105",
     "new1_live_probe3_t105g2",
     f"CUDA_VISIBLE_DEVICES=2 {CPROBE} {PROBE_SRV} serve "
     "--port 8792 --device cuda:0"),
]


def main() -> None:
    for host, session, cmd in JOBS:
        probe = subprocess.run(
            ["ssh", "-n", host, f"tmux has-session -t {session} 2>/dev/null"])
        if probe.returncode == 0:
            print("SKIP (session exists):", session)
            continue
        log = f"{LOGDIR}/{session}.log"
        inner = f"{cmd} > {log} 2>&1"
        tmux = f"tmux new-session -d -s {session} {shlex.quote(inner)}"
        subprocess.run(["ssh", "-n", host, tmux], check=True)
        print(f"launched {session} on {host} -> log: {log}")


if __name__ == "__main__":
    main()
