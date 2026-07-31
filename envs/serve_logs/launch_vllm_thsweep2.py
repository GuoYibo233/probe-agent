"""θ 扫描 run 段的第二批 gpt-oss-120b 服务：三副本，落在腾出来的三张 H100。

c2_alfworld 采集收工后（474+474 条轨迹全部以 "type": "final" 结束），它占的
tokyo108 GPU 0/1/2（H100 95G）三张卡空出来了。第一批服务（launch_vllm_thsweep.py）
在三张 H200 上跑 8111/8112/8113，六个 θ 点却只有三个服务，一半时间在排队；
这一批把剩下三个 θ 也接上，六点一对一全并发。

  gpt-oss-120b -> H100 GPU 0, port 8114   (副本 D)
  gpt-oss-120b -> H100 GPU 1, port 8115   (副本 E)
  gpt-oss-120b -> H100 GPU 2, port 8116   (副本 F)

参数与第一批**逐字一致**（模型路径 / served-model-name / max-model-len 65536 /
gpu-memory-utilization 0.92 / 三个环境变量），否则六个点的服务端口径不齐：
concurrency 与批组成会影响 greedy 续写的 token 数（replay_inject.py 文件头已列
这条已知偏差），服务侧参数更不能有差别。

H100 是 95G 而 H200 是 143G，0.92 × 95G ≈ 87G；采集期这三张卡上的同一个模型
实测占 89G，装得下。
"""
import shlex
import subprocess

HOST = "tokyo108"
WORKDIR = "/home/y-guo/reproduce/new1/envs/serve_logs"
VLLM = "/home/y-guo/reproduce/new1/envs/vllm-env/bin/vllm"
YMODELS = "/net/tokyo100-10g/data/str01_01/y-guo/models"

GPTOSS_FLAGS = "--max-model-len 65536 --gpu-memory-utilization 0.92"

JOBS = [
    (0, 8114, "new1_thsw_srv_d_t108g0"),
    (1, 8115, "new1_thsw_srv_e_t108g1"),
    (2, 8116, "new1_thsw_srv_f_t108g2"),
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
