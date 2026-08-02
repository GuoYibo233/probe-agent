#!/usr/bin/env python3
"""new1 GPU 任务台账 + 监控 CLI（零依赖，标准库）。

用法:
  gpu_jobs.py                    # 我的任务快照表（进度/速率/ETA/存活）
  gpu_jobs.py watch [SEC]        # 自动刷新，默认每 30 秒
  gpu_jobs.py free               # 全集群空卡表（转调 gpu_status.sh）
  gpu_jobs.py register --name N --workdir W [--note TEXT] \
              --piece host:gpus:session:logpath [--piece ...]
  gpu_jobs.py finish NAME        # 收尾销号（session 还活着会拒绝;--force 强销）
  gpu_jobs.py json               # 机器可读输出（给 agent 用）

台账: ops/jobs.json  {"active":[...], "history":[...]}
日志在 NFS 上，本地直接读；只有 tmux 存活检查走 ssh（每 host 一次）。
"""
import fcntl
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
REG_PATH = os.path.join(ROOT, "jobs.json")
GPU_STATUS_SH = os.path.join(
    os.path.dirname(ROOT), ".claude", "skills", "gpu-run", "scripts", "gpu_status.sh"
)

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


def mutate_reg(fn):
    """register/finish 的读改写要在一把锁里做——并发的两次 load→save 会互相
    覆盖丢更新(审计 E23)。fn(reg) 就地改,返回值原样透传。"""
    with open(REG_PATH + ".lock", "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        reg = load_reg()
        out = fn(reg)
        save_reg(reg)
    return out


def live_sessions(hosts):
    """每台 host 一次 ssh，返回 {host: set(存活的 tmux session 名)}。
    ssh 非零退出（解析失败/拒连/host key 变更）也算探测失败记 None——
    空 stdout 与"真的没有 session"必须能区分，否则销号门禁会被放行。
    tmux 没在跑时 `tmux ls` 也退非零，所以命令里兜一个 true。"""
    out = {}
    for h in sorted(hosts):
        try:
            r = subprocess.run(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", h,
                 "tmux ls -F '#S' 2>/dev/null; true"],
                capture_output=True, text=True, timeout=12,
            )
            out[h] = set(r.stdout.split()) if r.returncode == 0 else None
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


# 反向核对要扫的固定机器清单(与 ops/gpu_state.md 对齐)——台账为空时
# 恰恰是最容易漏登记的时候,不能只探台账里已有的 host
DEFAULT_HOSTS = ("tokyo105", "tokyo106", "tokyo107", "tokyo108")


def collect(with_extras=False):
    """汇总所有 active job 的状态。with_extras=True 时附带反向核对:
    实际在跑但台账里没有的 session(固定机器清单全扫)。"""
    reg = load_reg()
    hosts = {p["host"] for j in reg["active"] for p in j["pieces"]}
    if with_extras:
        hosts = hosts | set(DEFAULT_HOSTS)
    live = live_sessions(hosts)
    registered = {}
    for j in reg["active"]:
        for p in j["pieces"]:
            registered.setdefault(p["host"], set()).add(p["session"])
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
    if with_extras:
        extras = {}
        for h, sess_set in live.items():
            if sess_set is None:
                continue
            unreg = sorted(sess_set - registered.get(h, set()))
            if unreg:
                extras[h] = unreg
        return rows, extras
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
    by_job = {}
    for r in rows:
        by_job.setdefault(r["job"], []).append(r["state"])
    all_done = sorted(j for j, sts in by_job.items()
                      if all(s == "DONE" for s in sts))
    part_done = sorted(j for j, sts in by_job.items()
                       if any(s == "DONE" for s in sts) and j not in all_done)
    if all_done or part_done:
        out.append("")
    for j in all_done:
        out.append(f"DONE = 全部分片进度 100% 且 session 已退——该收尾了: "
                   f"python3 run.py gpu-jobs finish {j}")
    for j in part_done:
        out.append(f"{j}: 部分分片已完成,其余还在跑——先别 finish")
    return "\n".join(out)


def cmd_status():
    rows, extras = collect(with_extras=True)
    print(fmt_table(rows))
    if extras:
        print("\n台账外 tmux session(实际在跑但没登记——漏 register?别的对话在用?):")
        for h, ss in sorted(extras.items()):
            print(f"  {h}: {', '.join(ss)}")


def cmd_watch(sec):
    while True:
        rows, extras = collect(with_extras=True)
        sys.stdout.write("\x1b[2J\x1b[H")
        print(f"new1 GPU jobs  @ {datetime.now().strftime('%H:%M:%S')}  (每 {sec}s 刷新, Ctrl-C 退出)\n")
        print(fmt_table(rows))
        if extras:
            print("\n台账外 tmux session:")
            for h, ss in sorted(extras.items()):
                print(f"  {h}: {', '.join(ss)}")
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

    def _add(reg):
        if any(j["name"] == name for j in reg["active"]):
            sys.exit(f"任务名 {name} 已在台账里，换个名字或先 finish 它")
        reg["active"].append({
            "name": name, "workdir": workdir, "note": note,
            "started_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "pieces": pieces,
        })
    mutate_reg(_add)
    print(f"已登记 {name}: {len(pieces)} 个分片")


def cmd_finish(name):
    # 防提前销号(审计实例 eval_c2_q36_mtool 16:52 被销号,实际跑到 18:17):
    # 探测在锁外做(ssh 最长 12s/host,不该把台账锁住);fail-closed——
    # 探测失败(None)按"可能还活着"拒绝,确认要销带 --force
    reg0 = load_reg()
    hit0 = [j for j in reg0["active"] if j["name"] == name]
    if not hit0:
        sys.exit(f"台账里没有 {name}")
    hosts = {p["host"] for p in hit0[0]["pieces"]}
    live = live_sessions(hosts)
    dead_probe = sorted(h for h in hosts if live.get(h) is None)
    if dead_probe:
        sys.exit(f"{name} 的 host 探测失败: {', '.join(dead_probe)}——"
                 f"分不清 session 死活,按活处理拒绝销号;"
                 f"确认要强行销号: finish {name} --force")
    alive = [p["session"] for p in hit0[0]["pieces"]
             if p["session"] in live[p["host"]]]
    if alive:
        sys.exit(f"{name} 还有 {len(alive)} 个 session 活着: "
                 f"{', '.join(alive)}——跑完再 finish;"
                 f"确认要强行销号: finish {name} --force")

    def _move(reg):
        hit = [j for j in reg["active"] if j["name"] == name]
        if not hit:
            sys.exit(f"台账里没有 {name}(刚被并发销号?)")
        job = hit[0]
        job["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        reg["active"] = [j for j in reg["active"] if j["name"] != name]
        reg["history"].append(job)
    mutate_reg(_move)
    print(f"{name} 已销号（移入 history）")


def cmd_finish_force(name):
    def _move(reg):
        hit = [j for j in reg["active"] if j["name"] == name]
        if not hit:
            sys.exit(f"台账里没有 {name}")
        job = hit[0]
        job["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        job["force_finished"] = True
        reg["active"] = [j for j in reg["active"] if j["name"] != name]
        reg["history"].append(job)
    mutate_reg(_move)
    print(f"{name} 已强行销号（移入 history,标记 force_finished）")


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
        rest = args[1:]
        names = [a for a in rest if not a.startswith("--")]
        if not names:
            sys.exit("finish 需要任务名: finish NAME [--force]")
        if "--force" in rest:
            cmd_finish_force(names[0])
        else:
            cmd_finish(names[0])
    elif args[0] == "json":
        print(json.dumps(collect(), indent=2, ensure_ascii=False))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
