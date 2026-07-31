#!/usr/bin/env python3
"""tmux launcher for new1 Phase C (c1) probe training. Usage: launch_c1.py smoke|full"""
import subprocess, shlex, sys, time

WD = "/home/y-guo/reproduce/new1"
LOGD = f"{WD}/logs"
LOCAL = subprocess.run(["hostname"], capture_output=True, text=True).stdout.strip()
ALIAS = {"shiga": "tokyo105", "saitama": "tokyo108"}
LOCAL = ALIAS.get(LOCAL, LOCAL)

MBERT = f"{WD}/mbert-env/bin/python"
CPROBE = f"{WD}/cprobe-env/bin/python"

CELLS = {
    "mtool": (MBERT, f"{WD}/pipeline/train/train_mbert_tool.py", []),
    "mext":  (MBERT, f"{WD}/pipeline/train/train_mbert_extract.py", []),
    "ctool": (CPROBE, f"{WD}/pipeline/train/train_causal_tool.py", ["--base", "qwen"]),
    "cgen":  (CPROBE, f"{WD}/pipeline/train/train_causal_callgen.py", []),
}


def run(host, argv, check=True):
    if host == LOCAL:
        return subprocess.run(argv, capture_output=True, text=True, check=check)
    return subprocess.run(["ssh", "-n", host] + argv, capture_output=True, text=True, check=check)


def has_session(host, s):
    cmd = f"tmux has-session -t {shlex.quote(s)}"
    if host == LOCAL:
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
    else:
        r = subprocess.run(["ssh", "-n", host, cmd], capture_output=True, text=True)
    return r.returncode == 0


def launch(host, gpu, session, cmd, log):
    if has_session(host, session):
        print(f"SKIP (exists): {session}")
        return False
    inner = f"cd {WD} && CUDA_VISIBLE_DEVICES={gpu} {cmd} 2>&1 | tee {log}"
    tmux = f"tmux new-session -d -s {shlex.quote(session)} {shlex.quote(inner)}"
    if host == LOCAL:
        subprocess.run(["bash", "-c", tmux], check=True)
    else:
        subprocess.run(["ssh", "-n", host, tmux], check=True)
    print(f"LAUNCHED {session}  ({host} gpu{gpu})  log={log}")
    return True


def build(model, cell, smoke, extra=None):
    py, script, base_args = CELLS[cell]
    rid = f"c1_{model}_{cell}"
    data = f"{WD}/pipeline/data/aw_official_v1/{model}"
    if smoke:
        out = f"{WD}/pipeline/runs/smoke/{rid}_smoke"
    else:
        out = f"{WD}/pipeline/runs/{rid}"
    args = [py, script, "--data", data, "--out", out] + base_args
    if smoke:
        args.append("--smoke")
    if extra:
        args += extra
    return rid, " ".join(shlex.quote(a) for a in args)


if __name__ == "__main__":
    mode = sys.argv[1]
    plan = []
    if mode == "smoke":
        for i, cell in enumerate(["mtool", "mext", "ctool", "cgen"]):
            rid, cmd = build("q35", cell, True)
            host, gpu = "tokyo105", i
            sess = f"new1_{rid}_smoke_t105g{gpu}"
            plan.append((host, gpu, sess, cmd, f"{LOGD}/{sess}.log"))
    else:
        # full: 12 runs. placement passed as arg file
        import json
        plan_spec = json.load(open(sys.argv[2]))
        for p in plan_spec:
            rid, cmd = build(p["model"], p["cell"], False, p.get("extra"))
            host, gpu = p["host"], p["gpu"]
            hs = host.replace("tokyo", "")
            sess = f"new1_{rid}_t{hs}g{gpu}"
            plan.append((host, gpu, sess, cmd, f"{LOGD}/{sess}.log"))

    for host, gpu, sess, cmd, log in plan:
        launch(host, gpu, sess, cmd, log)
    time.sleep(6)
    print("\n--- alive check ---")
    for host, gpu, sess, cmd, log in plan:
        print(f"{sess}: {'ALIVE' if has_session(host, sess) else 'DEAD'}")
