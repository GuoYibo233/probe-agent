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

import verdicts

ROOT = os.path.dirname(os.path.abspath(__file__))
REG_PATH = os.path.join(ROOT, "jobs.json")
GPU_STATUS_SH = os.path.join(
    os.path.dirname(ROOT), ".claude", "skills", "gpu-run", "scripts", "gpu_status.sh"
)

# 采样历史(latest.json,采样器 ops/sampler.py 落盘)——终端出口(status/
# watch/json)新鲜时直接读它渲染，过期退回下面的现场实探老路(collect())。
# free/register/finish 永远现场实探，不读这份文件(spec §终端出口读采样历史)。
MONITOR_DIR = os.environ.get(
    "NEW1_MONITOR_DIR",
    "/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/monitor")
FRESH_S = 300.0  # 新鲜度门槛:最后采样时刻 5 分钟内才信(工单 07)

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


def read_latest():
    """采样历史出口:读 MONITOR_DIR/latest.json。返回 (latest_dict|None,
    age_s|None)——文件不在/读不了/JSON 语法坏了/顶层不是 dict/sampled_at
    字段类型不对，都返回 (None, None)，退回现场实探老路，不让 status/
    watch/json 三个出口在畸形但语法合法的 latest.json 上崩溃。latest
    没有 sampled_at 字段（不该发生，但别炸）返回 age_s=None、latest 原样
    透传。age_s 用调用时的挂钟算，与 latest["sampled_at"]（采样器落盘时
    的挂钟）同机比较，不跨机比钟。"""
    p = os.path.join(MONITOR_DIR, "latest.json")
    try:
        with open(p) as f:
            latest = json.load(f)
    except (OSError, ValueError):
        return None, None
    if not isinstance(latest, dict):
        return None, None
    sampled_at = latest.get("sampled_at")
    if sampled_at is None:
        return latest, None
    if isinstance(sampled_at, bool) or not isinstance(sampled_at, (int, float)):
        return None, None
    try:
        age_s = time.time() - sampled_at
    except (TypeError, OverflowError, OSError):
        return None, None
    return latest, age_s


def _stale_warning(latest):
    """终端出口过期时打的警告行，措辞是工单 07 给定的原文。"""
    if latest and latest.get("sampled_at"):
        stamp = datetime.fromtimestamp(latest["sampled_at"]).strftime("%H:%M:%S")
    else:
        stamp = "无"
    return f"采样器不在跑(最后采样 {stamp}),现场实探一次"


def _fmt_progress_v2(r):
    done, total, unit = r.get("done"), r.get("total"), r.get("unit")
    if done is None or total is None:
        return "-"
    pct = r.get("progress_pct")
    pct_s = "-" if pct is None else f"{pct}%"
    tail = f" {unit}" if unit else ""
    return f"{done}/{total} ({pct_s}){tail}"


def _fmt_rate_v2(r):
    """recent_rate 没值 -> "-"；有值时按数量级挑单位：>=1/s 本身就够读，
    保留 /s；小于 1/s（批任务常见，比如几十秒一个 task）乘 3600 换算成
    /h 更好读。"""
    rate = r.get("recent_rate")
    if rate is None:
        return "-"
    if rate >= 1:
        return f"{rate:.3g}/s"
    return f"{rate * 3600:.3g}/h"


def _fmt_tok_short(v):
    if v is None:
        return "-"
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"{v / 1_000:.0f}k"
    return str(v)


def _fmt_tok_v2(r):
    tok_in, tok_out = r.get("tok_in"), r.get("tok_out")
    if tok_in is None and tok_out is None:
        return "-"
    return f"{_fmt_tok_short(tok_in)}/{_fmt_tok_short(tok_out)}"


def _fmt_eta_v2(r):
    eta_s = r.get("eta_s")
    if eta_s is None:
        return "-"
    m, s = divmod(max(0, int(eta_s)), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}"


def fmt_table_v2(rows, sampled_at=None):
    """采样历史新鲜时的渲染路径(工单 07)。列: JOB/HOST/GPU/判定/
    PROGRESS/RATE/TOK/ETA/SESSION。sampled_at 给了就加一行表头
    `最后采样 HH:MM:SS`。已完成/已挂两种判定仍保留收尾/看日志提示行，
    措辞沿用 fmt_table()。"""
    out = []
    if sampled_at is not None:
        stamp = datetime.fromtimestamp(sampled_at).strftime("%H:%M:%S")
        out.append(f"最后采样 {stamp}")
    if not rows:
        out.append("台账为空——当前没有登记中的任务。发射走 gpu-run skill 会自动登记。")
        return "\n".join(out)
    cols = ["job", "host", "gpus", "verdict", "progress", "rate", "tok", "eta", "session"]
    head = {"job": "JOB", "host": "HOST", "gpus": "GPU", "verdict": "判定",
            "progress": "PROGRESS", "rate": "RATE", "tok": "TOK",
            "eta": "ETA", "session": "SESSION"}
    disp = []
    for r in rows:
        disp.append({
            "job": r.get("job"), "host": r.get("host"), "gpus": r.get("gpus"),
            "verdict": r.get("verdict"), "progress": _fmt_progress_v2(r),
            "rate": _fmt_rate_v2(r), "tok": _fmt_tok_v2(r),
            "eta": _fmt_eta_v2(r), "session": r.get("session"),
        })
    widths = {c: max(len(head[c]), *(len(str(d[c])) for d in disp)) for c in cols}
    out.append("  ".join(head[c].ljust(widths[c]) for c in cols))
    out.append("  ".join("-" * widths[c] for c in cols))
    for d in disp:
        out.append("  ".join(str(d[c]).ljust(widths[c]) for c in cols))

    by_job = {}
    for r in rows:
        by_job.setdefault(r.get("job"), []).append(r.get("verdict"))
    all_done = sorted(j for j, vs in by_job.items()
                      if vs and all(v == verdicts.V_DONE for v in vs))
    dead = [r for r in rows if r.get("verdict") == verdicts.V_DEAD]
    if all_done or dead:
        out.append("")
    for j in all_done:
        out.append(f"{verdicts.V_DONE} = 全部分片判定已完成——该收尾了: "
                   f"python3 run.py gpu-jobs finish {j}")
    if dead:
        out.append(f"{verdicts.V_DEAD} = session 没了，进度未到 100%，看日志: "
                   f"{dead[0].get('log')}")
    return "\n".join(out)


def _print_table_from_latest_or_fallback():
    """status/watch 两个终端出口共用的新鲜度判断:latest.json 新鲜就渲染
    快照(fmt_table_v2)，过期/读不到/畸形就打警告退回现场实探老路
    (collect + fmt_table)。抽出来是因为这段判断两处出口原样各写一遍，
    新鲜度门槛或渲染选择逻辑改动容易漏改一处(工单 07 复核 F2)。返回
    extras(台账外 tmux session)供调用方接着打印。"""
    latest, age_s = read_latest()
    if latest is not None and age_s is not None and age_s <= FRESH_S:
        print(fmt_table_v2(latest.get("rows", []), latest.get("sampled_at")))
        return latest.get("extras") or {}
    print(_stale_warning(latest))
    rows, extras = collect(with_extras=True)
    print(fmt_table(rows))
    return extras


def cmd_status():
    extras = _print_table_from_latest_or_fallback()
    if extras:
        print("\n台账外 tmux session(实际在跑但没登记——漏 register?别的对话在用?):")
        for h, ss in sorted(extras.items()):
            print(f"  {h}: {', '.join(ss)}")


def cmd_watch(sec):
    while True:
        sys.stdout.write("\x1b[2J\x1b[H")
        print(f"new1 GPU jobs  @ {datetime.now().strftime('%H:%M:%S')}  (每 {sec}s 刷新, Ctrl-C 退出)\n")
        extras = _print_table_from_latest_or_fallback()
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


def cmd_json():
    """json 出口(工单 07):新鲜时原样吐 latest.json；过期退回 collect()
    老路，外加 sampler_stale=true 标记给 agent 识别。老路的 rows 换个
    外壳装进 "rows" 键——裸列表加不了字段，latest.json 本来就是这个
    键名，两条路径的调用方看到的结构对得上。"""
    latest, age_s = read_latest()
    if latest is not None and age_s is not None and age_s <= FRESH_S:
        print(json.dumps(latest, indent=2, ensure_ascii=False))
    else:
        out = {"rows": collect(), "sampler_stale": True}
        print(json.dumps(out, indent=2, ensure_ascii=False))


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
        cmd_json()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
