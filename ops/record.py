#!/usr/bin/env python3
"""new1 experiment record CLI (zero dependencies, standard library only).

The middle layer of the three-layer record system: the numbers.
  direction   TIMELINE.md   human-written, append-only (one line = one direction decision)
  numbers     ops/runs.jsonl -> RESULTS.md   maintained by this script
  data        raw trajectories/weights on NFS, not in git, traced via run_id dir name + report.md

Usage:
  record.py start --name NAME --track TRACK [options]   # record right after launch
  record.py start --run-id ID --track TRACK [options]
      --cmd "..."          the actual command line executed
      --host h --gpu 0,1   where it runs
      --model M --seed N   model and random seed
      --param k=v          repeatable, experiment parameters
      --data PATH          where the raw data lands
      --log PATH           log path (record and log can jump to each other)
      --note TEXT          one sentence on what this run is meant to verify
  record.py finish RUN_ID [options]                     # fill in the numbers at wrap-up
      --status ok|fail|killed
      --metric k=v         repeatable, key numbers
      --data PATH          final data location (overrides the one from start)
      --conclusion TEXT    one-sentence conclusion
  record.py render      # re-render RESULTS.md (start/finish call this automatically)
  record.py list        # one line per run
  record.py show RUN_ID # all fields of a single run

runs.jsonl is an append-only event stream, existing lines are never rewritten -- so
git diff is always pure addition, and history can never be silently tampered with.
RESULTS.md is its rendered output, rebuildable at any time.
run_id is the primary key running through everything: it is used in the raw data
dir name / tmux session name / job ledger name / commit message, and the four
places can jump to each other through it.
"""
import json
import os
import subprocess
import sys
from datetime import datetime

OPS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(OPS)
RUNS_PATH = os.path.join(OPS, "runs.jsonl")
RESULTS_PATH = os.path.join(ROOT, "RESULTS.md")


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# The job ledger and lock files do not count as dirty (kept in sync across three
# spots with run.py's LEDGER_PATHS and ops/runmeta.py): they are a byproduct of the
# recording itself and do not affect any outputs
LEDGER_PATHS = ("ops/jobs.json", "ops/runs.jsonl", "RESULTS.md",
                "ops/jobs.json.lock")


def git_state():
    """Current code version. dirty=True means this record's commit cannot be traced back
    to the real code.
    fail-closed: if git probing fails, mark git_probe_failed explicitly and treat it
    as dirty -- silently recording it as a clean tree would make a bad record look
    better than a dirty tree (audit A4).
    Do not strip porcelain output as a whole: the leading whitespace on the first
    line is part of the status code."""
    def g(*a, raw=False):
        r = subprocess.run(["git", "-C", ROOT] + list(a),
                           capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            raise RuntimeError((r.stderr or "").strip() or f"git rc={r.returncode}")
        return r.stdout if raw else r.stdout.strip()
    try:
        dirty = [l for l in g("status", "--porcelain", raw=True).splitlines()
                 if l.strip() and l[3:] not in LEDGER_PATHS]
        return {"commit": g("rev-parse", "--short", "HEAD"),
                "branch": g("rev-parse", "--abbrev-ref", "HEAD"),
                "dirty": bool(dirty), "dirty_count": len(dirty),
                "dirty_files": dirty[:50]}
    except Exception as e:
        return {"commit": "", "branch": "", "dirty": True, "dirty_files": [],
                "git_probe_failed": True, "git_probe_error": str(e)[:200]}


def append(ev):
    with open(RUNS_PATH, "a") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")


def load():
    """Fold the event stream into {run_id: merged record}, preserving first-occurrence order."""
    runs = {}
    if not os.path.exists(RUNS_PATH):
        return runs
    with open(RUNS_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            ev = json.loads(line)
            rid = ev["run_id"]
            r = runs.setdefault(rid, {"run_id": rid, "status": "running",
                                      "metrics": {}, "params": {}})
            kind = ev.pop("ev")
            if kind == "start":
                r["started_at"] = ev.get("t")
                for k in ("track", "commit", "branch", "dirty", "dirty_files",
                          "dirty_count", "git_probe_failed", "git_probe_error",
                          "cmd", "host",
                          "gpu", "model", "seed", "data", "note", "log"):
                    if ev.get(k) not in (None, ""):
                        r[k] = ev[k]
                r["params"].update(ev.get("params") or {})
            elif kind == "finish":
                r["finished_at"] = ev.get("t")
                r["status"] = ev.get("status", "ok")
                r["metrics"].update(ev.get("metrics") or {})
                for k in ("data", "conclusion"):
                    if ev.get(k):
                        r[k] = ev[k]
    return runs


def kv(pairs):
    out = {}
    for p in pairs:
        if "=" not in p:
            sys.exit(f"params must be written as k=v, got: {p}")
        k, v = p.split("=", 1)
        try:
            v = float(v) if ("." in v or "e" in v.lower()) else int(v)
        except ValueError:
            pass
        out[k] = v
    return out


def fmt_metrics(m):
    if not m:
        return "-"
    return " ".join(f"{k}={v}" for k, v in m.items())


def render():
    runs = load()
    lines = [
        "# RESULTS -- master table of experiment statistics",
        "",
        "> This file is auto-generated by `python3 run.py record render`, **do not edit by hand**.",
        "> The data source is the append-only `ops/runs.jsonl`; to change a number, add a finish event.",
        "> For the background behind direction decisions, see [TIMELINE.md](TIMELINE.md); raw data is not in git.",
        "",
    ]
    if not runs:
        lines += ["(No records yet. Launching experiments via the gpu-run skill writes them automatically.)", ""]
    else:
        lines += [
            "| run_id | Date | Direction | commit | Model | Status | Key numbers | Conclusion |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for r in reversed(list(runs.values())):
            if r.get("git_probe_failed"):
                c = "?"                # probe failure is not the same as a known dirty tree, don't render it as -+dirty
            else:
                c = r.get("commit", "-")
                if r.get("dirty"):
                    c += "+dirty"
            lines.append("| `{}` | {} | {} | `{}` | {} | {} | {} | {} |".format(
                r["run_id"], r.get("started_at", "-"), r.get("track", "-"), c,
                r.get("model", "-"), r.get("status", "-"),
                fmt_metrics(r.get("metrics")),
                (r.get("conclusion") or "-").replace("|", "/"),
            ))
        lines += ["", "## Per-run detail", ""]
        for r in reversed(list(runs.values())):
            lines.append(f"### `{r['run_id']}`")
            lines.append("")
            if r.get("note"):
                lines.append(f"- **What this tests**: {r['note']}")
            if r.get("conclusion"):
                lines.append(f"- **Conclusion**: {r['conclusion']}")
            lines.append("- **Direction**: {} | **Status**: {} | **Start/end**: {} → {}".format(
                r.get("track", "-"), r.get("status", "-"),
                r.get("started_at", "-"), r.get("finished_at", "not finished")))
            if r.get("git_probe_failed"):
                lines.append("- **Code**: ⚠️ git probe failed at record time, code version unknown"
                             + ("({})".format(r["git_probe_error"])
                                if r.get("git_probe_error") else ""))
            else:
                nd = r.get("dirty_count") or len(r.get("dirty_files") or [])
                lines.append("- **Code**: `{}`{} (branch {})".format(
                    r.get("commit", "-"),
                    ("  ⚠️ the working tree was dirty at launch time ({} files), this commit "
                     "cannot trace back to the real code".format(nd or "?"))
                    if r.get("dirty") else "",
                    r.get("branch", "-")))
            if r.get("host"):
                lines.append("- **Machine**: {} GPU {}".format(
                    r["host"], r.get("gpu", "-")))
            if r.get("model") or r.get("seed") is not None:
                lines.append("- **Model / seed**: {} / {}".format(
                    r.get("model", "-"), r.get("seed", "-")))
            if r.get("params"):
                lines.append("- **Params**: {}".format(fmt_metrics(r["params"])))
            if r.get("metrics"):
                lines.append("- **Numbers**: {}".format(fmt_metrics(r["metrics"])))
            if r.get("data"):
                lines.append(f"- **Raw data**: `{r['data']}` (not in git)")
            if r.get("log"):
                lines.append(f"- **Log**: `{r['log']}`")
            if r.get("cmd"):
                lines.append(f"- **Command**: `{r['cmd']}`")
            lines.append("")
    with open(RESULTS_PATH, "w") as f:
        f.write("\n".join(lines))
    return len(runs)


def cmd_start(argv):
    ev = {"ev": "start", "t": now(), "params": {}}
    name = None
    params = []
    it = iter(argv)
    for a in it:
        if a == "--run-id":
            ev["run_id"] = next(it)
        elif a == "--name":
            name = next(it)
        elif a in ("--track", "--cmd", "--host", "--gpu", "--model",
                   "--data", "--note", "--log"):
            ev[a[2:]] = next(it)
        elif a == "--seed":
            ev["seed"] = int(next(it))
        elif a == "--param":
            params.append(next(it))
        else:
            sys.exit(f"unknown argument {a}\n\n{__doc__}")
    if not ev.get("run_id"):
        if not name:
            sys.exit("start needs --run-id or --name")
        ev["run_id"] = datetime.now().strftime("%Y%m%d_%H%M_") + name
    if not ev.get("track"):
        sys.exit("start needs --track (which direction this experiment serves, align with TIMELINE.md)")
    if ev["run_id"] in load():
        sys.exit(f"run_id {ev['run_id']} already exists, use a different one")
    ev["params"] = kv(params)
    ev.update(git_state())
    # Capture the dirty-tree diff **before** append/render: otherwise the diff would
    # pick up the job-ledger change this very record just wrote, which would not be
    # the same moment as the dirty_files snapshot stored in the event (audit review)
    if ev.get("dirty") and not ev.get("git_probe_failed"):
        d = ev.get("data")
        if not d:
            print("⚠️ dirty tree with no --data given, nowhere to save the patch -- this record only has the dirty-file list")
        elif not os.path.isdir(d):
            print(f"⚠️ dirty-tree patch not saved: --data dir does not exist yet ({d})")
        else:
            try:
                r = subprocess.run(["git", "-C", ROOT, "diff", "HEAD"],
                                   capture_output=True, text=True, timeout=20)
                if r.returncode == 0 and r.stdout:
                    pf = os.path.join(d, f"dirty_{ev['run_id']}.patch")
                    with open(pf, "w") as f:
                        f.write(r.stdout)
                    print(f"saved dirty-tree patch: {pf} (untracked new files are not in the patch, "
                          "see this record's dirty_files for the list)")
            except Exception as e:
                print(f"⚠️ dirty-tree patch failed to save: {e}")
    append(ev)
    render()
    if ev.get("git_probe_failed"):
        print(f"recorded start: {ev['run_id']}  ⚠️ git probe failed, code version unknown")
    else:
        print(f"recorded start: {ev['run_id']}  (commit {ev['commit']}"
              f"{', ⚠️ the working tree is dirty: commit before launching, otherwise the trace chain breaks' if ev['dirty'] else ''})")
    print(f"at finish time: python3 run.py record finish {ev['run_id']} "
          f"--metric k=v --conclusion \"...\"")


def cmd_finish(argv):
    if not argv or argv[0].startswith("--"):
        sys.exit("finish needs RUN_ID")
    ev = {"ev": "finish", "t": now(), "run_id": argv[0], "status": "ok"}
    metrics = []
    it = iter(argv[1:])
    for a in it:
        if a in ("--status", "--data", "--conclusion"):
            ev[a[2:]] = next(it)
        elif a == "--metric":
            metrics.append(next(it))
        else:
            sys.exit(f"unknown argument {a}\n\n{__doc__}")
    runs = load()
    if ev["run_id"] not in runs:
        sys.exit(f"no run_id {ev['run_id']} -- run record.py start first, or check record.py list")
    ev["metrics"] = kv(metrics)
    append(ev)
    render()
    print(f"recorded finish: {ev['run_id']}  {fmt_metrics(ev['metrics'])}")
    print("Did the numbers change a judgment in WORKPLAN? Append an entry to TIMELINE.md and commit.")


def cmd_list():
    runs = load()
    if not runs:
        print("No records yet.")
        return
    for r in runs.values():
        print("{:<28} {:<12} {:<8} {}".format(
            r["run_id"], r.get("track", "-")[:12], r.get("status", "-"),
            fmt_metrics(r.get("metrics"))))


def cmd_show(rid):
    runs = load()
    if rid not in runs:
        sys.exit(f"no run_id {rid}")
    print(json.dumps(runs[rid], indent=2, ensure_ascii=False))


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    if args[0] == "start":
        cmd_start(args[1:])
    elif args[0] == "finish":
        cmd_finish(args[1:])
    elif args[0] == "render":
        print(f"RESULTS.md rebuilt ({render()} records)")
    elif args[0] == "list":
        cmd_list()
    elif args[0] == "show":
        cmd_show(args[1])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
