"""拼回八臂 run 段客户端发射器:tokyo108 上起三个自排序客户端(无 GPU)。

客户端自己等 PLAN_OK + 服务健康(见 splice_client.py),所以可以和服务、
plan 重跑同时发射,不用人肉排序。日志与服务同放 /net(避 /home 配额)。
"""
import shlex
import subprocess

HOST = "tokyo108"
ROOT = "/home/y-guo/reproduce/new1"
PY = f"{ROOT}/cprobe-env/bin/python"
CLIENT = f"{ROOT}/envs/serve_logs/splice_client.py"
LOGDIR = "/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/logs"

JOBS = [(s, f"new1_splice_cli_s{s}_t108") for s in (0, 1, 2)]


def main() -> None:
    subprocess.run(["ssh", "-n", HOST, f"mkdir -p {LOGDIR}"], check=True)
    for shard, session in JOBS:
        probe = subprocess.run(
            ["ssh", "-n", HOST, f"tmux has-session -t {session} 2>/dev/null"])
        if probe.returncode == 0:
            print("SKIP (session exists):", session)
            continue
        log = f"{LOGDIR}/{session}.log"
        inner = (f"cd {ROOT} && {PY} {CLIENT} --shard {shard} "
                 f"> {log} 2>&1")
        tmux = f"tmux new-session -d -s {session} {shlex.quote(inner)}"
        subprocess.run(["ssh", "-n", HOST, tmux], check=True)
        print(f"launched {session} shard {shard} -> log: {log}")


if __name__ == "__main__":
    main()
