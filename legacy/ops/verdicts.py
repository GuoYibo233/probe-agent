#!/usr/bin/env python3
"""Verdict engine: pure functions, zero IO (design doc §4). The sampler feeds in
state, gets a verdict out.
The six-way verdict is judged in a fixed priority order, stop at first hit: done ->
dead -> suspected stall -> warming up -> slowed -> healthy.
Clock discipline: never compare clocks across machines -- beat_age_s/since_launch_s
are computed by the sampler with its own clock and fed in; heartbeat ts is only
diffed on the same machine, inside rates(). All constants live in DEFAULTS, no
hardcoding anywhere else.
"""
from statistics import median

V_DONE, V_DEAD, V_STALL = "done", "dead", "suspected stall"
V_WARMUP, V_SLOW, V_OK = "warming up", "slowed", "healthy"

DEFAULTS = dict(
    sample_interval_s=60.0,   # interval of one sampler round
    stall_mult=5.0,           # verdict line = 5 x typical heartbeat interval
    stall_floor_samples=3,    # verdict line floor = 3 sampling rounds (below this granularity, stopped vs not is indistinguishable)
    escalate_mult=3.0,        # escalation line = verdict line x 3
    warmup_line_s=1800.0,     # warm-up cap, 30 minutes by default
    recent_beats=10,          # recent-rate view: last <=10 heartbeats
    typical_beats=20,         # typical heartbeat interval: median of the last <=20 intervals
    min_intervals=3,          # use the adaptive verdict line only once 3 intervals have accumulated
    slow_ratio=0.5,           # slowed = recent rate < average x 0.5
    port_fail_rounds=3,       # service: 3 consecutive rounds of no port response = suspected stall
)


def typical_gap_s(beat_ts, cfg=DEFAULTS):
    """Median of the last <=typical_beats heartbeat intervals; returns None if fewer than min_intervals intervals."""
    ts = list(beat_ts)[-(cfg["typical_beats"] + 1):]
    gaps = [b - a for a, b in zip(ts, ts[1:]) if b >= a]
    if len(gaps) < cfg["min_intervals"]:
        return None
    return median(gaps)


def stall_line_s(beat_ts, cfg=DEFAULTS, override=None):
    """Verdict line (seconds). override=the --stall-line given at launch; returns None
    when there aren't enough samples (the caller falls back to the warm-up cap, so
    a long task/long step at the start doesn't get falsely flagged)."""
    if override is not None:
        return float(override)
    gap = typical_gap_s(beat_ts, cfg)
    if gap is None:
        return None
    return max(cfg["stall_mult"] * gap,
               cfg["stall_floor_samples"] * cfg["sample_interval_s"])


def rates(first_beat, recent_beats, cfg=DEFAULTS):
    """(average rate, recent rate), in done/second; None where it can't be computed.
    first_beat: the first heartbeat {'ts','done'} (stored in the sampler's
    accumulated state, not dependent on the log tail).
    recent_beats: the last <=typical_beats heartbeats (ascending). All denominators
    are on the heartbeat timeline."""
    if not first_beat or not recent_beats:
        return None, None
    last = recent_beats[-1]
    avg = None
    dt = last["ts"] - first_beat["ts"]
    if dt > 0 and last["done"] >= first_beat["done"]:
        avg = (last["done"] - first_beat["done"]) / dt
    w = recent_beats[-cfg["recent_beats"]:]
    recent = None
    if len(w) >= 2:
        dtw = w[-1]["ts"] - w[0]["ts"]
        if dtw > 0 and w[-1]["done"] >= w[0]["done"]:
            recent = (w[-1]["done"] - w[0]["done"]) / dtw
    return avg, recent


def _judge_service(p, cfg):
    if p["alive"] is False:
        return V_DEAD, True
    if p.get("port_ok"):
        return V_OK, False
    if not p.get("port_ever_ok"):
        if p["since_launch_s"] > p["warmup_s"]:
            esc = p["since_launch_s"] > p["warmup_s"] * cfg["escalate_mult"]
            return V_STALL, esc
        return V_WARMUP, False
    n = p.get("port_fail_rounds", 0)
    if n >= cfg["port_fail_rounds"]:
        esc = n >= cfg["port_fail_rounds"] * cfg["escalate_mult"]
        return V_STALL, esc
    return V_OK, False


def judge(p, cfg=DEFAULTS):
    """Exactly one cell per piece per round. Returns (verdict, whether the escalation
    line is reached).
    done and slowed do not apply to the service type (design §4, end of section),
    services go through _judge_service."""
    if p["kind"] == "service":
        return _judge_service(p, cfg)
    done, total = p.get("done"), p.get("total")
    if p.get("status") == "done" or (done is not None and total
                                     and done >= total):
        return V_DONE, False
    if p["alive"] is False:
        return V_DEAD, True
    warm = not p["has_beat"]
    age = p["since_launch_s"] if warm else p["beat_age_s"]
    line = p["warmup_s"] if (warm or p.get("stall_s") is None) else p["stall_s"]
    if age > line:
        esc_line = (p["escalate_s"] if p.get("escalate_s") is not None
                    else line * cfg["escalate_mult"])
        return V_STALL, age > esc_line
    if warm:
        return V_WARMUP, False
    if (p.get("recent_rate") is not None and p.get("avg_rate")
            and p["recent_rate"] < cfg["slow_ratio"] * p["avg_rate"]):
        return V_SLOW, False
    return V_OK, False
