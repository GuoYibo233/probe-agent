#!/usr/bin/env python3
"""SessionStart hook (asyncRewake): report open GPU runs that have a dead or stalled piece.

It runs `run.py ls` (about a minute: the command re-runs itself on tokyo108 and probes every
host's tmux) in the background. When an open run (status=launching) has a piece whose verdict
is dead or suspected stall, it writes those lines to stderr and exits 2, which wakes the model
with them; otherwise it exits 0 and says nothing.
"""
import os
import subprocess
import sys

ROOT = os.environ.get("CLAUDE_PROJECT_DIR", "/home/y-guo/reproduce/new1")
PYTHON = os.path.join(ROOT, "external/probe-env/bin/python")
STUCK_VERDICTS = ("dead", "suspected stall")


def main() -> int:
    try:
        out = subprocess.run([PYTHON, "run.py", "ls"], cwd=ROOT, capture_output=True,
                             text=True, timeout=240).stdout
    except (OSError, subprocess.TimeoutExpired):
        return 0
    stuck = []
    for line in out.splitlines():
        if "status=launching" not in line or "  pieces=" not in line:
            continue
        head, pieces = line.split("  pieces=", 1)
        stuck_pieces = [p for p in pieces.split("; ")
                        if any(f":{v}" in p for v in STUCK_VERDICTS)]
        if stuck_pieces:
            fields = dict(f.split("=", 1) for f in head.split()[1:] if "=" in f)
            stuck.append(f"{head.split()[0]} ({fields.get('stage')}, progress "
                         f"{fields.get('progress')}, left {fields.get('left')}): "
                         + "; ".join(stuck_pieces))
    if not stuck:
        return 0
    sys.stderr.write(
        "Session-start check (`run.py ls`): these open GPU runs have a dead or stalled piece. "
        "Tell the user in one sentence, then check them through the gpu-run skill:\n"
        + "\n".join(stuck) + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
