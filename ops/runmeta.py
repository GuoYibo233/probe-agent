#!/usr/bin/env python3
"""RUNMETA.json 落盘器:把产物目录钉回代码版本(审计 B6)。

每次发射往 <outdir>/RUNMETA.json 的 launches 列表 append 一条:
时间 / 机器 / kind / 实际命令 / commit / branch / dirty + 脏文件清单。
append 不覆盖——同一目录被二次发射会留下两条记录,产物归属不再靠猜。

调用方:
  ops/launch_probe.py、ops/launch_eval.py 发射成功后自动写;
  gpu-run skill 手搓发射时补一条: python3 run.py runmeta <outdir> --cmd '<命令>'
"""
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 台账与锁不算脏(与 run.py 的 LEDGER_PATHS、ops/record.py 三处同步维护):
# 它们是发射的副产品,不影响任何产物
LEDGER_PATHS = ("ops/jobs.json", "ops/runs.jsonl", "RESULTS.md",
                "ops/jobs.json.lock")


def git_info():
    """fail-closed:git 探不到就明说 probe_failed 并按脏处理,不许装干净。
    porcelain 输出不整体 strip——首行前导空格是状态码的一部分。"""
    def g(*a, raw=False):
        r = subprocess.run(["git", "-C", str(ROOT)] + list(a),
                           capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            raise RuntimeError((r.stderr or "").strip() or f"git rc={r.returncode}")
        return r.stdout if raw else r.stdout.strip()
    try:
        dirty = [l for l in g("status", "--porcelain", raw=True).splitlines()
                 if l.strip() and l[3:] not in LEDGER_PATHS]
        return {"commit": g("rev-parse", "HEAD"),
                "branch": g("rev-parse", "--abbrev-ref", "HEAD"),
                "dirty": bool(dirty), "dirty_count": len(dirty),
                "dirty_files": dirty[:50]}
    except Exception as e:
        return {"commit": "", "branch": "", "dirty": True, "dirty_files": [],
                "git_probe_failed": True, "git_probe_error": str(e)[:200]}


def append_runmeta(outdir, cmd, kind="launch", extra=None):
    """往 outdir/RUNMETA.json 追加一条发射记录,返回文件路径。
    旧文件坏了(不是 {"launches": [...]} 形状)就改名留档,绝不让记账炸掉发射。"""
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    p = out / "RUNMETA.json"
    doc = None
    if p.exists():
        try:
            doc = json.loads(p.read_text())
        except Exception:
            doc = None
        if not (isinstance(doc, dict) and isinstance(doc.get("launches"), list)):
            corrupt = p.with_name("RUNMETA.json.corrupt."
                                  + time.strftime("%Y%m%d_%H%M%S"))
            os.replace(p, corrupt)
            doc = {"launches": [], "corrupt_previous": str(corrupt)}
    if doc is None:
        doc = {"launches": []}
    ent = {"written_at": time.strftime("%F %T"),
           "host": socket.gethostname(), "kind": kind, "cmd": cmd}
    ent.update(git_info())
    if extra:
        ent.update(extra)
    doc["launches"].append(ent)
    tmp = p.with_name("RUNMETA.json.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1))
    os.replace(tmp, p)
    return p


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("outdir", help="产物目录(不存在会建)")
    ap.add_argument("--cmd", required=True, help="实际执行的完整命令")
    ap.add_argument("--kind", default="launch",
                    help="记录类别(发射器用 train/eval_tool/eval_call)")
    ap.add_argument("--note", default=None, help="一句话备注")
    a = ap.parse_args()
    extra = {"note": a.note} if a.note else None
    p = append_runmeta(a.outdir, a.cmd, kind=a.kind, extra=extra)
    doc = json.loads(p.read_text())
    last = doc["launches"][-1]
    warn = ""
    if last.get("git_probe_failed"):
        warn = "  ⚠️ git 探测失败,代码版本未知"
    elif last.get("dirty"):
        warn = (f"  ⚠️ 工作树脏({last.get('dirty_count', '?')} 文件,台账不计),"
                "commit 追不回真实代码")
    print(f"RUNMETA 已追加: {p}  (第 {len(doc['launches'])} 条,"
          f"commit {last['commit'][:9] or '?'}){warn}")


if __name__ == "__main__":
    main()
