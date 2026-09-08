#!/usr/bin/env python3
"""Heartbeat: the sole channel long-running task scripts use to report progress to the
sampler (design doc §2).

One line = prefix "@hb " + one JSON object. done/total/unit/ts are required; optional:
tok_in/tok_out (cumulative values)/loss/status ("done" = normal finish).
Emit one emit(0, total, unit) before entering the main loop -- that's the signal that
"the model has finished loading".
Standard library only: any venv must be able to import this file.
"""
import json
import sys
import time

PREFIX = "@hb "
_REQUIRED = ("done", "total", "unit", "ts")


def emit(done, total, unit, *, tok_in=None, tok_out=None, loss=None,
         status=None, stream=None):
    rec = {"done": int(done), "total": int(total), "unit": str(unit),
           "ts": round(time.time(), 1)}
    if tok_in is not None:
        rec["tok_in"] = int(tok_in)
    if tok_out is not None:
        rec["tok_out"] = int(tok_out)
    if loss is not None:
        rec["loss"] = round(float(loss), 5)
    if status is not None:
        rec["status"] = str(status)
    out = stream or sys.stdout
    out.write(PREFIX + json.dumps(rec) + "\n")
    out.flush()


def parse(line):
    """Heartbeat line -> dict; returns None if not a valid heartbeat line (the monitoring side only recognizes this entry point)."""
    line = line.strip()
    if not line.startswith(PREFIX):
        return None
    try:
        rec = json.loads(line[len(PREFIX):])
    except ValueError:
        return None
    if not isinstance(rec, dict) or any(k not in rec for k in _REQUIRED):
        return None
    return rec
