#!/usr/bin/env python3
"""new1 GPU job ledger + monitoring CLI (zero dependencies, standard library only).

Usage:
  gpu_jobs.py                    # snapshot table of my jobs (progress/rate/ETA/alive)
  gpu_jobs.py watch [SEC]        # auto-refresh, every 30 seconds by default
  gpu_jobs.py free               # cluster-wide free-card table (delegates to gpu_status.sh)
  gpu_jobs.py register --name N --workdir W [--note TEXT] \
              --piece host:gpus:session:logpath [--piece ...] \
              [--kind batch|service] [--port PORT]  # for manually backfilling service pieces
  gpu_jobs.py finish NAME        # finish and deregister (refuses if the session is still alive; --force to force it)
  gpu_jobs.py json               # machine-readable output (for agents)

Ledger: ops/jobs.json  {"active":[...], "history":[...]}
Logs live on NFS and are read directly; only the tmux liveness check goes over ssh (once per host).
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

# Sample history (latest.json, written to disk by the sampler ops/sampler.py) -- the
# terminal exits (status/watch/json) read and render it directly when fresh, and fall
# back to the old live-probe path below (collect()) when it is stale.
# free/register/finish always live-probe and never read this file (spec section
# "terminal exits read sample history").
MONITOR_DIR = os.environ.get(
    "NEW1_MONITOR_DIR",
    "/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/monitor")
FRESH_S = 300.0  # Freshness threshold: trust it only within 5 minutes of the last sample time (ticket 07)

# tqdm line (after \r has been replaced with \n): " 42%|####  | 42/100 [00:31<00:43,  1.35it/s]"
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
    """register/finish's read-modify-write must happen inside one lock -- two concurrent
    load→save cycles clobber each other and lose updates (audit E23). fn(reg) mutates
    the registry in place; the return value passes through unchanged."""
    with open(REG_PATH + ".lock", "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        reg = load_reg()
        out = fn(reg)
        save_reg(reg)
    return out


def live_sessions(hosts):
    """One ssh call per host, returns {host: set(names of live tmux sessions)}.
    A nonzero ssh exit (parse failure/connection refused/host key changed) also counts
    as a probe failure and is recorded as None -- empty stdout and "genuinely no session"
    must be distinguishable, otherwise the deregistration gate would let it through.
    When tmux is not running, `tmux ls` also exits nonzero, so the command has a
    fallback `true` built in."""
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
            out[h] = None  # Probe failure, distinct from "no session"
    return out


def parse_log(path):
    """Read the tail of the log and take the last tqdm line. Returns a dict or None."""
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
        # No tqdm: return the last non-empty line of text, to help tell where it is stuck
        last = [l for l in lines.splitlines() if l.strip()]
        return {"raw": last[-1][:80]} if last else None
    n, total, elapsed, remain, rate, unit = matches[-1]
    return {
        "n": int(n), "total": int(total),
        "elapsed": elapsed, "remain": remain,
        "rate": f"{rate}{unit}",
    }


# Reverse-check against the fixed list of machines to scan (aligned with ops/gpu_state.md)
# -- an empty ledger is exactly when registration is most likely to be missed, so we
# can't only probe the hosts already in the ledger
DEFAULT_HOSTS = ("tokyo105", "tokyo106", "tokyo107", "tokyo108")


def collect(with_extras=False):
    """Aggregate the status of all active jobs. When with_extras=True, also include a
    reverse check: sessions that are actually running but missing from the ledger
    (a full scan of the fixed machine list)."""
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
        return "The job ledger is empty -- no jobs currently registered. Launching via the gpu-run skill registers automatically."
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
        out.append("EXIT = the session has exited but progress has not reached 100%%, check the log: %s" % dead[0]["log"])
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
        out.append(f"DONE = all pieces at 100% progress and the session has exited -- time to finish: "
                   f"python3 run.py gpu-jobs finish {j}")
    for j in part_done:
        out.append(f"{j}: some pieces are done, the rest are still running -- do not finish yet")
    return "\n".join(out)


def read_latest():
    """Sample-history exit: reads MONITOR_DIR/latest.json. Returns (latest_dict|None,
    age_s|None) -- if the file is missing/unreadable/has bad JSON syntax/the top level
    isn't a dict/the sampled_at field has the wrong type, all return (None, None) and
    fall back to the old live-probe path, so the three terminal exits status/watch/json
    don't crash on a malformed but syntactically valid latest.json. If latest has no
    sampled_at field (shouldn't happen, but don't blow up), returns age_s=None with
    latest passed through unchanged. age_s is computed against the wall clock at call
    time, compared with latest["sampled_at"] (the wall clock when the sampler wrote it)
    on the same machine -- never compare clocks across machines."""
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
    """The warning line printed when a terminal exit is stale; the wording is the exact text given by ticket 07."""
    if latest and latest.get("sampled_at"):
        stamp = datetime.fromtimestamp(latest["sampled_at"]).strftime("%H:%M:%S")
    else:
        stamp = "none"
    return f"sampler is not running (last sample {stamp}), probing live once"


def _fmt_progress_v2(r):
    done, total, unit = r.get("done"), r.get("total"), r.get("unit")
    if done is None or total is None:
        return "-"
    pct = r.get("progress_pct")
    pct_s = "-" if pct is None else f"{pct}%"
    tail = f" {unit}" if unit else ""
    return f"{done}/{total} ({pct_s}){tail}"


def _fmt_rate_v2(r):
    """recent_rate with no value -> "-"; when it has a value, pick the unit by order of
    magnitude: >=1/s is already readable as is, keep /s; below 1/s (common for batch
    jobs, e.g. one task every few tens of seconds), multiply by 3600 to convert to
    /h, which reads better."""
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
    """Render path used when the sample history is fresh (ticket 07). Columns: JOB/HOST/GPU/
    VERDICT/PROGRESS/RATE/TOK/ETA/SESSION. If sampled_at is given, add a header line
    `Last sampled HH:MM:SS`. The done/dead verdicts still keep the wrap-up/check-the-log
    hint lines, with wording carried over from fmt_table()."""
    out = []
    if sampled_at is not None:
        stamp = datetime.fromtimestamp(sampled_at).strftime("%H:%M:%S")
        out.append(f"last sample {stamp}")
    if not rows:
        out.append("The job ledger is empty -- no jobs currently registered. Launching via the gpu-run skill registers automatically.")
        return "\n".join(out)
    cols = ["job", "host", "gpus", "verdict", "progress", "rate", "tok", "eta", "session"]
    head = {"job": "JOB", "host": "HOST", "gpus": "GPU", "verdict": "verdict",
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
        out.append(f"{verdicts.V_DONE} = every piece's verdict is done -- time to finish: "
                   f"python3 run.py gpu-jobs finish {j}")
    if dead:
        out.append(f"{verdicts.V_DEAD} = the session is gone, progress has not reached 100%, check the log: "
                   f"{dead[0].get('log')}")
    return "\n".join(out)


def _print_table_from_latest_or_fallback():
    """Freshness check shared by the two terminal exits status/watch: render the snapshot
    (fmt_table_v2) if latest.json is fresh; print a warning and fall back to the old
    live-probe path (collect + fmt_table) if it is stale/unreadable/malformed. Pulled
    out into its own function because this check used to be written once, identically,
    in each of the two terminal exits -- easy to miss updating one place when the
    freshness threshold or the render-selection logic changes (ticket 07 review F2).
    Returns extras (tmux sessions outside the ledger) for the caller to print next."""
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
        print("\ntmux sessions outside the job ledger (actually running but not registered -- missed register? another conversation using it?):")
        for h, ss in sorted(extras.items()):
            print(f"  {h}: {', '.join(ss)}")


def cmd_watch(sec):
    while True:
        sys.stdout.write("\x1b[2J\x1b[H")
        print(f"new1 GPU jobs  @ {datetime.now().strftime('%H:%M:%S')}  (refreshes every {sec}s, Ctrl-C to exit)\n")
        extras = _print_table_from_latest_or_fallback()
        if extras:
            print("\ntmux sessions outside the job ledger:")
            for h, ss in sorted(extras.items()):
                print(f"  {h}: {', '.join(ss)}")
        time.sleep(sec)


def cmd_free():
    os.execvp("bash", ["bash", GPU_STATUS_SH])


def cmd_register(argv):
    """`--kind`/`--port` (C2, final-review 2026-08-09): the manual-registration path used to
    only write the host/gpus/session/log quadruple; without kind/port it always
    registered as batch -- for a service piece (e.g. a manually started vLLM that
    didn't go through `run.py launch --service`), registering it into the ledger this
    way still leaves the sampler's `probe_port` verdict chain broken. `--kind` defaults
    to `batch` (unchanged behavior if not given); `--port` is written into the piece
    only if given. Both flags apply to every `--piece` in this call (manual
    registration is usually one piece at a time, so this legacy path doesn't get the
    fine-grained treatment of "kind/port per piece")."""
    name = workdir = note = None
    kind = "batch"
    port = None
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
        elif a == "--kind":
            kind = next(it)
        elif a == "--port":
            port = int(next(it))
    if not name or not pieces:
        sys.exit("register needs --name and at least one --piece host:gpus:session:log")
    for piece in pieces:
        piece["kind"] = kind
        if port is not None:
            piece["port"] = port

    def _add(reg):
        if any(j["name"] == name for j in reg["active"]):
            sys.exit(f"job name {name} already in the job ledger, use a different name or finish it first")
        reg["active"].append({
            "name": name, "workdir": workdir, "note": note,
            "started_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "pieces": pieces,
        })
    mutate_reg(_add)
    print(f"registered {name}: {len(pieces)} pieces")


def cmd_finish(name):
    # Guards against premature deregistration (audit case: eval_c2_q36_mtool was
    # deregistered at 16:52, but actually ran until 18:17): the probe runs outside the
    # lock (ssh takes up to 12s/host, shouldn't hold the ledger lock); fail-closed --
    # a probe failure (None) is treated as "may still be alive" and rejected; confirm
    # a deregistration with --force
    reg0 = load_reg()
    hit0 = [j for j in reg0["active"] if j["name"] == name]
    if not hit0:
        sys.exit(f"{name} is not in the job ledger")
    hosts = {p["host"] for p in hit0[0]["pieces"]}
    live = live_sessions(hosts)
    dead_probe = sorted(h for h in hosts if live.get(h) is None)
    if dead_probe:
        sys.exit(f"{name}'s host probe failed: {', '.join(dead_probe)} -- "
                 f"cannot tell whether the session is alive or dead, treating it as alive and refusing to deregister; "
                 f"to force deregistration: finish {name} --force")
    alive = [p["session"] for p in hit0[0]["pieces"]
             if p["session"] in live[p["host"]]]
    if alive:
        sys.exit(f"{name} still has {len(alive)} sessions alive: "
                 f"{', '.join(alive)} -- finish once they are done; "
                 f"to force deregistration: finish {name} --force")

    def _move(reg):
        hit = [j for j in reg["active"] if j["name"] == name]
        if not hit:
            sys.exit(f"{name} is not in the job ledger (just deregistered concurrently?)")
        job = hit[0]
        job["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        reg["active"] = [j for j in reg["active"] if j["name"] != name]
        reg["history"].append(job)
    mutate_reg(_move)
    print(f"{name} deregistered (moved to history)")


def cmd_finish_force(name):
    def _move(reg):
        hit = [j for j in reg["active"] if j["name"] == name]
        if not hit:
            sys.exit(f"{name} is not in the job ledger")
        job = hit[0]
        job["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        job["force_finished"] = True
        reg["active"] = [j for j in reg["active"] if j["name"] != name]
        reg["history"].append(job)
    mutate_reg(_move)
    print(f"{name} force-deregistered (moved to history, marked force_finished)")


def cmd_json():
    """json exit (ticket 07): dumps latest.json as-is when fresh; falls back to the old
    collect() path when stale, with a sampler_stale=true flag added for agents to
    detect. The old path's rows get wrapped in a "rows" key -- a bare list can't
    carry extra fields, latest.json already used this key name, so callers on both
    paths see a matching structure."""
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
            sys.exit("finish needs a job name: finish NAME [--force]")
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
