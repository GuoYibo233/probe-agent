#!/usr/bin/env python3
"""One queue of the 2026-09-29 inject sweep: launch sweep children one after another on one agent server.

Runs on tokyo108 (every run.py command runs there). Each queue owns one big
card (the agent server) and a list of small cards for the probe services, and
holds up to `--slots` runs in flight on that server (the later ones attach to
the server the first one started). For each child it types the same commands a
person would:

    run.py inject <child> --cards <server card> --cards <probe card>   (launch)
    ... wait until every loop piece's heartbeat says done ...
    run.py inject <child> --cards <server card> --cards <probe card>   (wrap-up: done.json, teardown, score)

It computes no verdicts and kills nothing: a launch that fails is logged and
the queue goes on to the next child; a run that stalls past --stall-min
minutes is logged as stalled and left to the person (the queue skips to the
next child and frees the slot only when the run's pieces are done or dead).

Usage:
    python3 .scratch/inject-sweep/queue.py --server tokyo108:5 --probe tokyo106:0,1 --slots 2 \
        --children .scratch/inject-sweep/children/queue-5.txt

The children file holds one child name per line (a sweep child's own name, or
a plain setting name); lines starting with # are skipped.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/home/y-guo/reproduce/new1")
PY = ROOT / "external/probe-env/bin/python"
LOGDIR = ROOT / ".scratch/inject-sweep/queue-logs"


def now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(fh, msg: str) -> None:
    line = f"[{now()}] {msg}"
    print(line, flush=True)
    fh.write(line + "\n")
    fh.flush()


def run_py(args: list[str]) -> tuple[int, str]:
    p = subprocess.run([str(PY), "run.py", *args], cwd=ROOT, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr)


def where(child: str) -> Path | None:
    rc, out = run_py(["where", "inject", child, "inject"])
    if rc != 0:
        return None
    return Path(out.strip().splitlines()[-1])


def loop_pieces_done(run_dir: Path) -> tuple[bool, str]:
    """Whether every loop piece of the run has a heartbeat row with status done; the second value is a short state line."""
    meta_path = run_dir / "meta.json"
    if not meta_path.exists():
        return False, "no meta.json"
    meta = json.loads(meta_path.read_text())
    states = []
    all_done = True
    for piece in meta.get("pieces", []):
        if piece.get("kind") != "loop":
            continue
        idx = piece["index"]
        launch = piece.get("beat_launch", 0)
        hb = run_dir / "heartbeat" / f"{idx}-{launch}.jsonl"
        status = "no heartbeat"
        if hb.exists():
            rows = [r for r in hb.read_text().splitlines() if r.strip()]
            if rows:
                last = json.loads(rows[-1])
                status = last.get("status") or f"{last.get('done')}/{last.get('total')}"
        states.append(f"{idx}:{status}")
        if status != "done":
            all_done = False
    return all_done, " ".join(states)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", required=True, help="<host>:<id>, the agent server's card")
    ap.add_argument("--probe", required=True, help="<host>:<id>,<id>,..., the probe-service cards this queue may use")
    ap.add_argument("--slots", type=int, default=1, help="runs in flight on this server")
    ap.add_argument("--children", required=True, help="file with one child name per line")
    ap.add_argument("--poll", type=int, default=60, help="seconds between checks")
    ap.add_argument("--stall-min", type=int, default=90, help="minutes without a heartbeat change before a run is logged as stalled")
    a = ap.parse_args()

    probe_host, probe_ids = a.probe.split(":")
    probe_cards = [f"{probe_host}:{i}" for i in probe_ids.split(",")]
    if len(probe_cards) < a.slots:
        sys.exit("queue.py: fewer probe cards than slots")
    children = [l.strip() for l in Path(a.children).read_text().splitlines()
                if l.strip() and not l.startswith("#")]
    LOGDIR.mkdir(parents=True, exist_ok=True)
    tag = a.server.replace(":", "-")
    fh = open(LOGDIR / f"queue-{tag}.log", "a")
    log(fh, f"queue start: server {a.server}, probe cards {probe_cards}, slots {a.slots}, {len(children)} children")

    in_flight: dict[str, dict] = {}   # child -> {probe, run_dir, last_state, last_change}
    free_probe = list(probe_cards)
    pending = list(children)
    outcomes: dict[str, str] = {}

    while pending or in_flight:
        # fill free slots
        while pending and len(in_flight) < a.slots:
            child = pending.pop(0)
            probe = free_probe.pop(0)
            log(fh, f"launch {child} on {a.server} + {probe}")
            rc, out = run_py(["inject", child, "--cards", a.server, "--cards", probe])
            tail = "\n".join(out.strip().splitlines()[-3:])
            if rc != 0 or "launched inject-" not in out:
                if " ok; report " in out or "reused inject-" in out:
                    log(fh, f"{child}: already finished ({tail.splitlines()[-1] if tail else ''})")
                    outcomes[child] = "already done"
                else:
                    log(fh, f"{child}: launch did not come up (rc {rc}):\n{tail}")
                    outcomes[child] = "launch failed"
                free_probe.append(probe)
                continue
            run_dir = where(child)
            log(fh, f"{child}: {tail.splitlines()[0]} -> {run_dir}")
            in_flight[child] = {"probe": probe, "run_dir": run_dir, "last_state": "", "last_change": time.time()}

        time.sleep(a.poll)

        # check runs in flight
        for child in list(in_flight):
            st = in_flight[child]
            done, state = loop_pieces_done(st["run_dir"])
            if state != st["last_state"]:
                st["last_state"], st["last_change"] = state, time.time()
            if done:
                log(fh, f"{child}: loop pieces done ({state}); wrap-up")
                rc, out = run_py(["inject", child, "--cards", a.server, "--cards", st["probe"]])
                lines = [l for l in out.strip().splitlines() if l.startswith("run.py:")]
                log(fh, f"{child}: wrap-up rc {rc}: " + " | ".join(lines[-3:]))
                outcomes[child] = "ok" if rc == 0 else f"wrap-up rc {rc}"
                free_probe.append(st["probe"])
                del in_flight[child]
                continue
            idle_min = (time.time() - st["last_change"]) / 60
            if idle_min > a.stall_min:
                log(fh, f"{child}: no heartbeat change for {idle_min:.0f} min ({state}); left to the person, slot freed")
                outcomes[child] = f"stalled ({state})"
                free_probe.append(st["probe"])
                del in_flight[child]

    log(fh, "queue end: " + json.dumps(outcomes, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
