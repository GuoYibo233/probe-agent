#!/usr/bin/env python3
"""发射公共件：探卡（fail-closed）+ tmux 发射模板 + 三处登记一口气。

三样能力供 `run.py launch`（工单 09）与两个排卡发射器（工单 11）共用：
  - `probe_free(host, gpus)`：发射前实探目标卡，有计算进程或探测本身失败都算
    非 FREE——fail-closed，宁可挡好卡也不许把任务撞进已占用的卡。
  - `local_host()` / `has_session()` / `tmux_launch()`：与 `ops/launch_probe.py`
    原来的 `has_session`/`launch` 同一套 ssh/tmux 逻辑，搬来给多处共用；
    `LOCAL` 从「模块级常量」改成「按需算的函数」，方便测试里 monkeypatch。
  - `register_all(...)`：一次发射要登记的三个地方——GPU 台账 `ops/jobs.json`、
    实验记录 `ops/runs.jsonl`（经 `ops/record.py start` 子进程）、产物目录的
    `RUNMETA.json`——收进一次调用，顺序固定为台账→记录→RUNMETA，任何一步失败
    都不吞掉，原样往外抛。

这一文件本身不改变任何现有发射器的行为（`launch_probe.py`/`launch_eval.py`
接进来是工单 11 的事）。
"""
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path

OPS_DIR = Path(__file__).resolve().parent
ROOT = OPS_DIR.parent

import gpu_jobs  # noqa: E402
import runmeta  # noqa: E402

ALIAS = {"shiga": "tokyo105", "saitama": "tokyo108"}


def local_host():
    """当前机器的规范化 host 名（经 ALIAS 折算成集群里认得的名字）。
    按需现算而不是模块级常量，方便测试 monkeypatch，也不再让每次
    `import launch_common` 都白跑一次 `hostname` 子进程。"""
    h = subprocess.run(["hostname"], capture_output=True, text=True).stdout.strip()
    return ALIAS.get(h, h)


def has_session(host, s):
    """目标 host 上是否有名为 s 的 tmux session（本机走 bash -c，远程走 ssh）。"""
    cmd = f"tmux has-session -t {shlex.quote(s)}"
    argv = ["bash", "-c", cmd] if host == local_host() else ["ssh", "-n", host, cmd]
    return subprocess.run(argv, capture_output=True, text=True).returncode == 0


def tmux_launch(host, sess, inner_cmd):
    """在 host 上起一个 tmux session 跑 inner_cmd。不做「已存在就跳过」的判断——
    发不发、跳不跳是调用方（launch_cmd / launch_probe / launch_eval）的业务，
    这里只管把命令真正发出去。"""
    tmux = f"tmux new-session -d -s {shlex.quote(sess)} {shlex.quote(inner_cmd)}"
    argv = ["bash", "-c", tmux] if host == local_host() else ["ssh", "-n", host, tmux]
    subprocess.run(argv, check=True)


def probe_free(host, gpus):
    """fail-closed 探卡：`ssh <host> nvidia-smi --query-compute-apps=... -i <gpus>`。
    stdout 有内容（有计算进程）→ 非 FREE；ssh 本身失败/超时/非零退出 → 也算非
    FREE（探不清楚不能当空卡用）；stdout 为空 → FREE。
    返回 (ok: bool, why: str)。"""
    cmd = ["ssh", host, "nvidia-smi", "--query-compute-apps=pid,used_memory",
           "--format=csv,noheader", "-i", str(gpus)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except (subprocess.TimeoutExpired, OSError) as e:
        return False, f"探测失败: {e}"
    if r.returncode != 0:
        err = (r.stderr or "").strip() or f"rc={r.returncode}"
        return False, f"探测失败: {err}"
    out = r.stdout.strip()
    if out:
        return False, f"占用中: {out.splitlines()[0]}"
    return True, ""


def register_all(run_id, workdir, pieces, track, cmd_display, note=None,
                  outdir=None, monitor=None):
    """三处登记一口气,顺序固定:①台账 ②实验记录 ③RUNMETA,任何一步失败就地
    中止(不吞异常)。

    ①台账:直接把 pieces(每个已经是 rich piece——host/gpus/session/log/cmd/
    launched_at/kind/stall_line/escalate_line/task)append 成一个 job；job 级字段
    `monitor`(给了才写,采样器缺省会退到 verdicts.DEFAULTS)与 `note`。piece 只存
    `task`(任务名,补射时反查 `TASKS[task]["env"]` 用),不存 env 实际键值——
    env 可能带密钥,原值只活在发射当次的进程局部变量里,不落进这份 git 追踪
    的台账文件(finding N1,2026-08-08)。
    重复 run_id(台账里已有同名 job)拒绝——护栏,不是障碍。

    ②实验记录:`ops/record.py start` 起子进程(隔离它自己的 sys.exit);多分片
    的 host/gpus/log 逗号拼成一个展示串;rc != 0 原样透出并中止(不捕获
    stdout/stderr,record.py 自己的报错直接打到终端)。

    ③RUNMETA:给了 outdir 才写(`outdir` 已经知道要落在哪,不必调用方另算);
    没给就打一行 WARN,不当错误。

    返回登记回执文本(三行,每步一行)。"""
    def _add(reg):
        if any(j["name"] == run_id for j in reg["active"]):
            sys.exit(f"run_id {run_id} 已在台账里，换一个或先 finish 它")
        job = {"name": run_id, "workdir": workdir, "note": note,
               "started_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
               "pieces": pieces}
        if monitor is not None:
            job["monitor"] = monitor
        reg["active"].append(job)
    gpu_jobs.mutate_reg(_add)
    lines = [f"台账: 已登记 {run_id}（{len(pieces)} 个分片）"]

    hosts = ",".join(p["host"] for p in pieces)
    gpus = ",".join(p["gpus"] for p in pieces)
    logs = ",".join(p["log"] for p in pieces)
    r = subprocess.run(
        [sys.executable, str(OPS_DIR / "record.py"), "start",
         "--run-id", run_id, "--track", track, "--cmd", cmd_display,
         "--host", hosts, "--gpu", gpus, "--log", logs])
    if r.returncode != 0:
        sys.exit(r.returncode)
    lines.append(f"记录: run_id={run_id} track={track}")

    if outdir:
        p = runmeta.append_runmeta(outdir, cmd_display, kind="launch")
        lines.append(f"RUNMETA: {p}")
    else:
        warn = "WARN 没给 --outdir，RUNMETA 没写"
        print(warn)
        lines.append(warn)

    return "\n".join(lines)
