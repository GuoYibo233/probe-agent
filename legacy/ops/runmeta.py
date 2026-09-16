#!/usr/bin/env python3
"""RUNMETA.json writer: pins the output dir back to the code version (audit B6).

Every launch appends one entry to the launches list in <outdir>/RUNMETA.json:
timestamp / host / kind / actual command / commit / branch / dirty + list of dirty files.
Append, never overwrite -- launching into the same dir twice leaves two records, so
output ownership no longer has to be guessed.

Callers:
  ops/launch_probe.py and ops/launch_eval.py write automatically after a successful
  launch;
  gpu-run skill's hand-rolled launches add one manually:
  python3 run.py runmeta <outdir> --cmd '<command>'
"""
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The job ledger and lock files do not count as dirty (kept in sync across three
# spots with run.py's LEDGER_PATHS and ops/record.py): they are a byproduct of the
# launch itself and do not affect any outputs
LEDGER_PATHS = ("ops/jobs.json", "ops/runs.jsonl", "RESULTS.md",
                "ops/jobs.json.lock")


def git_info():
    """fail-closed: if git probing fails, say probe_failed explicitly and treat it as
    dirty, no pretending it's clean.
    Do not strip porcelain output as a whole -- the leading whitespace on the first
    line is part of the status code."""
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
    """Append one launch record to outdir/RUNMETA.json, return the file path.
    If the old file is broken (not shaped like {"launches": [...]}), rename it to
    keep an archive -- never let record-keeping blow up the launch."""
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
    ap.add_argument("outdir", help="output dir (created if missing)")
    ap.add_argument("--cmd", required=True, help="the full command actually executed")
    ap.add_argument("--kind", default="launch",
                    help="record category (launchers use train/eval_tool/eval_call)")
    ap.add_argument("--note", default=None, help="one-line note")
    a = ap.parse_args()
    extra = {"note": a.note} if a.note else None
    p = append_runmeta(a.outdir, a.cmd, kind=a.kind, extra=extra)
    doc = json.loads(p.read_text())
    last = doc["launches"][-1]
    warn = ""
    if last.get("git_probe_failed"):
        warn = "  ⚠️ git probe failed, code version unknown"
    elif last.get("dirty"):
        warn = (f"  ⚠️ working tree dirty ({last.get('dirty_count', '?')} files, not counted in the ledger), "
                "the commit can't recover the real code")
    print(f"RUNMETA appended: {p}  (entry {len(doc['launches'])}, "
          f"commit {last['commit'][:9] or '?'}){warn}")


if __name__ == "__main__":
    main()
