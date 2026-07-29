#!/usr/bin/env python3
"""new1 GPU 任务台账 + 监控 CLI（零依赖，标准库）。

用法:
  gpu_jobs.py                    # 我的任务快照表（进度/速率/ETA/存活）
  gpu_jobs.py watch [SEC]        # 自动刷新，默认每 30 秒
  gpu_jobs.py free               # 全集群空卡表（转调 gpu_status.sh）
  gpu_jobs.py register --name N --workdir W [--note TEXT] \
              --piece host:gpus:session:logpath [--piece ...]
  gpu_jobs.py finish NAME        # 任务收尾后销号（移入 history）
  gpu_jobs.py json               # 机器可读输出（给 agent 用）

台账: ops/jobs.json  {"active":[...], "history":[...]}
日志在 NFS 上，本地直接读；只有 tmux 存活检查走 ssh（每 host 一次）。
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
REG_PATH = os.path.join(ROOT, "jobs.json")
GPU_STATUS_SH = os.path.expanduser("~/.claude/skills/launch-gpu-job/scripts/gpu_status.sh")

# tqdm 行（\r 已换成 \n 后）: " 42%|####  | 42/100 [00:31<00:43,  1.35it/s]"
TQDM_RE = re.compile(
    r"(\d+)/(\d+)\s*\[([0-9:]+)<([0-9:?,]+),\s*([0-9.]+)\s*(it/s|s/it)"
)


def load_reg():
    if not os.path.exists(REG_PATH):
        return {"active": [], "history": []}
    with open(REG_PATH) as f:
        return json.load(f)


def save_reg(reg):
    tmp = REG_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(reg, f, indent=2, ensure_ascii=False)
    os.replace(tmp, REG_PATH)


def live_sessions(hosts):
    """每台 host 一次 ssh，返回 {host: set(存活的 tmux session 名)}。"""
    out = {}
    for h in sorted(hosts):
        try:
            r = subprocess.run(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", h,
                 "tmux ls -F '#S' 2>/dev/null"],
                capture_output=True, text=True, timeout=12,
            )
            out[h] = set(r.stdout.split())
        except Exception:
            out[h] = None  # 探测失败，区别于"无 session"
    return out


def parse_log(path):
    """读日志尾部，取最后一条 tqdm 行。返回 dict 或 None。"""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 8192))
            tail = f.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    lines = tail.replace("\r", "\n")
    matches = TQDM_RE.findall(lines)
    if not matches:
        # 没有 tqdm，返回最后一行非空文本方便判断卡在哪
        last = [l for l in lines.splitlines() if l.strip()]
        return {"raw": last[-1][:80]} if last else None
    n, total, elapsed, remain, rate, unit = matches[-1]
    return {
        "n": int(n), "total": int(total),
        "elapsed": elapsed, "remain": remain,
        "rate": f"{rate}{unit}",
    }


def collect():
    """汇总所有 active job 的状态。"""
    reg = load_reg()
    hosts = {p["host"] for j in reg["active"] for p in j["pieces"]}
    live = live_sessions(hosts)
    rows = []
    for job in reg["active"]:
        for p in job["pieces"]:
            sess_set = live.get(p["host"])
            if sess_set is None:
                state = "HOST?"
            elif p["session"] in sess_set:
                state = "RUN"
            else:
                state = "EXIT"
            prog = parse_log(p["log"])
            if prog and "n" in prog:
                pct = 100 * prog["n"] // max(prog["total"], 1)
                progress = f"{prog['n']}/{prog['total']} ({pct}%)"
                rate, remain = prog["rate"], prog["remain"]
                if state == "EXIT" and prog["n"] >= prog["total"]:
                    state = "DONE"
            elif prog:
                progress, rate, remain = prog["raw"], "-", "-"
            else:
                progress, rate, remain = "(no log yet)", "-", "-"
            rows.append({
                "job": job["name"], "started": job["started_at"],
                "host": p["host"], "gpus": p["gpus"],
                "session": p["session"], "state": state,
                "progress": progress, "rate": rate, "eta": remain,
                "log": p["log"],
            })
    return rows


def fmt_table(rows):
    if not rows:
        return "台账为空——当前没有登记中的任务。发射走 gpu-run skill 会自动登记。"
    cols = ["job", "host", "gpus", "state", "progress", "rate", "eta", "session"]
    head = {"job": "JOB", "host": "HOST", "gpus": "GPU", "state": "STATE",
            "progress": "PROGRESS", "rate": "RATE", "eta": "ETA",
            "session": "TMUX SESSION"}
    widths = {c: max(len(head[c]), *(len(str(r[c])) for r in rows)) for c in cols}
    out = ["  ".join(head[c].ljust(widths[c]) for c in cols)]
    out.append("  ".join("-" * widths[c] for c in cols))
    for r in rows:
        out.append("  ".join(str(r[c]).ljust(widths[c]) for c in cols))
    dead = [r for r in rows if r["state"] == "EXIT"]
    if dead:
        out.append("")
        out.append("EXIT = session 已退出但进度未到 100%%，看日志: %s" % dead[0]["log"])
    return "\n".join(out)


def cmd_status():
    print(fmt_table(collect()))


def cmd_watch(sec):
    while True:
        rows = collect()
        sys.stdout.write("\x1b[2J\x1b[H")
        print(f"new1 GPU jobs  @ {datetime.now().strftime('%H:%M:%S')}  (每 {sec}s 刷新, Ctrl-C 退出)\n")
        print(fmt_table(rows))
        time.sleep(sec)


def cmd_free():
    os.execvp("bash", ["bash", GPU_STATUS_SH])


def cmd_register(argv):
    name = workdir = note = None
    pieces = []
    it = iter(argv)
    for a in it:
        if a == "--name":
            name = next(it)
        elif a == "--workdir":
            workdir = next(it)
        elif a == "--note":
            note = next(it)
        elif a == "--piece":
            host, gpus, session, log = next(it).split(":", 3)
            pieces.append({"host": host, "gpus": gpus,
                           "session": session, "log": log})
    if not name or not pieces:
        sys.exit("register 需要 --name 和至少一个 --piece host:gpus:session:log")
    reg = load_reg()
    if any(j["name"] == name for j in reg["active"]):
        sys.exit(f"任务名 {name} 已在台账里，换个名字或先 finish 它")
    reg["active"].append({
        "name": name, "workdir": workdir, "note": note,
        "started_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "pieces": pieces,
    })
    save_reg(reg)
    print(f"已登记 {name}: {len(pieces)} 个分片")


def cmd_finish(name):
    reg = load_reg()
    hit = [j for j in reg["active"] if j["name"] == name]
    if not hit:
        sys.exit(f"台账里没有 {name}")
    job = hit[0]
    job["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    reg["active"] = [j for j in reg["active"] if j["name"] != name]
    reg["history"].append(job)
    save_reg(reg)
    print(f"{name} 已销号（移入 history）")


def main():
    args = sys.argv[1:]
    if not args or args[0] == "status":
        cmd_status()
    elif args[0] == "watch":
        cmd_watch(int(args[1]) if len(args) > 1 else 30)
    elif args[0] == "free":
        cmd_free()
    elif args[0] == "register":
        cmd_register(args[1:])
    elif args[0] == "finish":
        cmd_finish(args[1])
    elif args[0] == "json":
        print(json.dumps(collect(), indent=2, ensure_ascii=False))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
