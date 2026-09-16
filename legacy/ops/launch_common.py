#!/usr/bin/env python3
"""Launch shared components: card probing (fail-closed) + the tmux launch template +
all three registrations in one go.

Three capabilities shared by `run.py launch` (ticket 09) and the two card-scheduling
launchers (ticket 11):
  - `probe_free(host, gpus)`: probes the target card live before launch; a compute
    process present, or the probe itself failing, both count as non-FREE -- fail-closed,
    better to block a good card than let a task collide with one already in use.
  - `local_host()` / `has_session()` / `tmux_launch()`: the same ssh/tmux logic that used
    to be `ops/launch_probe.py`'s own `has_session`/`launch`, moved here to be shared
    across multiple call sites; `LOCAL` changed from a "module-level constant" to a
    "computed-on-demand function", to make it easier to monkeypatch in tests.
  - `register_all(...)`: the three places a launch must register -- the output dir's
    `RUNMETA.json`, the GPU ledger `ops/jobs.json`, and the experiment record
    `ops/runs.jsonl` (via an `ops/record.py start` subprocess) -- folded into one call,
    in a fixed order: RUNMETA→ledger→record. RUNMETA comes first: the launch has
    already really happened, so pinning the outputs to the code must be written to disk
    first, and a later rejection by the ledger/record (e.g. a duplicate run_id) must not
    be able to drop it. A RUNMETA write failure only logs a WARN; any failure in the
    ledger/record steps is not swallowed and is raised as-is. RUNMETA is written only
    once, here (the sole writer) -- callers no longer each write one first, otherwise a
    single launch would end up with two records in one output dir (2026-08-26 np821
    batch, observed in practice).

This file by itself does not change the behavior of any existing launcher (wiring
`launch_probe.py`/`launch_eval.py` into it is ticket 11's job).
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
    """The current machine's normalized host name (converted through ALIAS into the name
    the cluster recognizes). Computed on demand rather than as a module-level constant,
    to make it easier to monkeypatch in tests, and so every `import launch_common`
    no longer wastes a `hostname` subprocess call."""
    h = subprocess.run(["hostname"], capture_output=True, text=True).stdout.strip()
    return ALIAS.get(h, h)


def has_session(host, s):
    """Whether the target host has a tmux session named s (local goes through bash -c, remote goes through ssh)."""
    cmd = f"tmux has-session -t {shlex.quote(s)}"
    argv = ["bash", "-c", cmd] if host == local_host() else ["ssh", "-n", host, cmd]
    return subprocess.run(argv, capture_output=True, text=True).returncode == 0


def tmux_launch(host, sess, inner_cmd):
    """Starts a tmux session on host to run inner_cmd. Does not check "skip if it already
    exists" -- whether to launch or skip is the caller's business (launch_cmd /
    launch_probe / launch_eval); this function's only job is to actually send out the
    command."""
    tmux = f"tmux new-session -d -s {shlex.quote(sess)} {shlex.quote(inner_cmd)}"
    argv = ["bash", "-c", tmux] if host == local_host() else ["ssh", "-n", host, tmux]
    subprocess.run(argv, check=True)


def probe_free(host, gpus):
    """fail-closed card probe: `ssh <host> nvidia-smi --query-compute-apps=... -i <gpus>`.
    stdout has content (a compute process is present) -> non-FREE; ssh itself
    fails/times out/exits nonzero -> also non-FREE (an unclear probe can't be treated
    as a free card); stdout is empty -> FREE.
    Returns (ok: bool, why: str)."""
    cmd = ["ssh", host, "nvidia-smi", "--query-compute-apps=pid,used_memory",
           "--format=csv,noheader", "-i", str(gpus)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except (subprocess.TimeoutExpired, OSError) as e:
        return False, f"probe failed: {e}"
    if r.returncode != 0:
        err = (r.stderr or "").strip() or f"rc={r.returncode}"
        return False, f"probe failed: {err}"
    out = r.stdout.strip()
    if out:
        return False, f"busy: {out.splitlines()[0]}"
    return True, ""


def register_all(run_id, workdir, pieces, track, cmd_display, note=None,
                  outdir=None, monitor=None, runmeta_kind="launch",
                  runmeta_extra=None):
    """All three registrations in one go, in a fixed order: (1) RUNMETA (2) ledger
    (3) experiment record. A RUNMETA write failure only WARNs; a failure at any step
    of the ledger/record aborts on the spot (the exception is not swallowed).

    (1) RUNMETA: if outdir is given, appends one entry to `outdir/RUNMETA.json` (kind
    uses `runmeta_kind`; the fields in `runmeta_extra` -- session/gpu/log/the card
    schedule table, etc. -- are merged into this entry as-is); it comes first because
    the launch has already really happened, and pinning the outputs to the code must
    not be dropped along with a later rejection by the ledger/record (e.g. a duplicate
    run_id). If outdir is not given, a WARN line is printed, not treated as an error --
    this is the case for tasks where `run.py launch` decides the output dir only after
    the fact. This is RUNMETA's sole writer: the card-scheduling launchers
    (launch_probe/launch_eval) pass in their own outdir/kind/extra rather than each
    writing one first themselves.

    (2) Ledger: pieces (each already a rich piece -- host/gpus/session/log/cmd/
    launched_at/kind/stall_line/escalate_line/task) are appended directly as one job;
    job-level fields `monitor` (written only if given, the sampler otherwise falls back
    to verdicts.DEFAULTS) and `note`. A piece stores only `task` (the task name, used to
    look up `TASKS[task]["env"]` on refire), not env's actual key-value pairs -- env may
    carry secrets, so the original value lives only in the process-local variables of
    that launch and never lands in this git-tracked ledger file (finding N1, 2026-08-08).
    A duplicate run_id (a job of the same name already in the ledger) is rejected --
    a guardrail, not an obstacle.

    (3) Experiment record: starts `ops/record.py start` as a subprocess (isolating its
    own sys.exit); for multiple pieces, host/gpus/log are joined with commas into one
    display string; rc != 0 is passed through as-is and aborts (stdout/stderr are not
    captured, record.py's own error goes straight to the terminal).

    Returns the registration receipt text (three lines, one per step)."""
    lines = []
    if outdir:
        try:
            p = runmeta.append_runmeta(outdir, cmd_display, kind=runmeta_kind,
                                       extra=runmeta_extra)
            lines.append(f"RUNMETA: {p}")
        except Exception as e:
            warn = f"WARN RUNMETA not written ({outdir}): {e}"
            print(warn, file=sys.stderr)
            lines.append(warn)
    else:
        warn = "WARN no --outdir given, RUNMETA not written"
        print(warn)
        lines.append(warn)

    def _add(reg):
        if any(j["name"] == run_id for j in reg["active"]):
            sys.exit(f"run_id {run_id} already in the job ledger, use a different one or finish it first")
        job = {"name": run_id, "workdir": workdir, "note": note,
               "started_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
               "pieces": pieces}
        if monitor is not None:
            job["monitor"] = monitor
        reg["active"].append(job)
    gpu_jobs.mutate_reg(_add)
    lines.append(f"job ledger: registered {run_id} ({len(pieces)} pieces)")

    hosts = ",".join(p["host"] for p in pieces)
    gpus = ",".join(p["gpus"] for p in pieces)
    logs = ",".join(p["log"] for p in pieces)
    r = subprocess.run(
        [sys.executable, str(OPS_DIR / "record.py"), "start",
         "--run-id", run_id, "--track", track, "--cmd", cmd_display,
         "--host", hosts, "--gpu", gpus, "--log", logs])
    if r.returncode != 0:
        sys.exit(r.returncode)
    lines.append(f"record: run_id={run_id} track={track}")

    return "\n".join(lines)
