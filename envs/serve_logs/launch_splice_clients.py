"""Client launcher for the run segment of the eight-arm splice-back: starts three
self-sequencing clients on tokyo108 (no GPU).

The clients wait for PLAN_OK + service health themselves (see splice_client.py), so they
can be launched at the same time as the service and the plan rerun, with no manual
sequencing needed. Logs go to /net along with the service (to avoid the /home quota).
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
