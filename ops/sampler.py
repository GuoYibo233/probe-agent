#!/usr/bin/env python3
"""Sampler: the long-running monitoring process for long jobs (design doc §3-§5).
Each round: read the job ledger -> tail logs for heartbeats (local NFS read) -> ssh
to probe liveness -> verdicts.judge -> append to sample history + atomically write
latest.json/state.json.
This file only does IO and accumulates state; the verdict logic all lives in
ops/verdicts.py. stdlib only.
Usage: sampler.py [--once] [--interval 60] [--port 8377] (the web page, added in Task 7)
"""
import argparse
import html
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

OPS = Path(__file__).resolve().parent
sys.path.insert(0, str(OPS))
import heartbeat  # noqa: E402
import verdicts  # noqa: E402
from gpu_jobs import live_sessions, DEFAULT_HOSTS  # noqa: E402
import gpu_jobs  # noqa: E402

# A local copy, not reusing gpu_jobs.load_reg directly -- that function reads
# gpu_jobs module's own global REG_PATH, and unit tests monkeypatch
# `sampler.REG_PATH` to point the job ledger at a tmp dir; that only takes effect
# if this file reads that name itself.
REG_PATH = gpu_jobs.REG_PATH


def load_reg():
    """Job ledger read entry point -- reads this module's own REG_PATH (by default the
    same file as gpu_jobs.REG_PATH); unit tests point it at a tmp dir."""
    if not os.path.exists(REG_PATH):
        return {"active": [], "history": []}
    with open(REG_PATH) as f:
        return json.load(f)


MONITOR_DIR = Path(os.environ.get(
    "NEW1_MONITOR_DIR",
    "/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/monitor"))

# Truncation length for recent_beats in state.json -- aligned with the view
# (typical_beats) the verdict engine uses for "typical heartbeat interval";
# heartbeats beyond this view no longer matter for the verdict
_BEATS_CAP = verdicts.DEFAULTS["typical_beats"]

# This many consecutive probe failures (design doc §4) only turns the row red, it
# does not trigger an incident -- when you can't tell alive from dead, don't act;
# fail-closed throughout
_PROBE_FAIL_ROUNDS_RED = 10


def read_beats(log_path, max_bytes=262144):
    """All heartbeat lines (ascending order) within the last max_bytes bytes of the log
    tail. tqdm's \\r is converted to \\n first.
    Returns an empty list if the file doesn't exist / can't be read -- sampling is
    a long-running loop, and one piece's log trouble must not blow up the whole
    round of sampling."""
    try:
        with open(log_path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            tail = f.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    lines = tail.replace("\r", "\n").splitlines()
    beats = []
    for line in lines:
        rec = heartbeat.parse(line)
        if rec is not None:
            beats.append(rec)
    return beats


# vLLM throughput line (ticket 13 / implementation plan Task 15): format verified
# against a real log on 2026-08-08, sourced from vllm 0.26.0
# `vllm/v1/metrics/loggers.py:263-313`. One line every 10 seconds by default,
# downgraded to debug and not printed when the engine is idle -- a gap in the
# stream doesn't mean it stalled; the verdict doesn't look at this line, it's only
# used to show the token rate. Sample of the original text (checked byte for byte):
#   Engine 000: Avg prompt throughput: 785.1 tokens/s, Avg generation
#   throughput: 671.8 tokens/s, Running: 4 reqs, Waiting: 0 reqs, ...
VLLM_STATS_RE = re.compile(
    r"Avg prompt throughput:\s*([\d.]+)\s*tokens/s,\s*"
    r"Avg generation throughput:\s*([\d.]+)\s*tokens/s,\s*"
    r"Running:\s*(\d+)\s*reqs")


def parse_vllm_stats(text):
    """vLLM throughput line -> {"prompt_tok_s","gen_tok_s","running"}; None if no match.
    `text` can be multiple lines; if several lines match, take the last one (the
    most recent sample). Used only to display the rate, it does not feed into the
    verdict (the verdict is probe_port, see verdicts._judge_service)."""
    matches = list(VLLM_STATS_RE.finditer(text))
    if not matches:
        return None
    m = matches[-1]
    return {"prompt_tok_s": float(m.group(1)), "gen_tok_s": float(m.group(2)),
            "running": int(m.group(3))}


def read_vllm_stats(log_path, max_bytes=8192):
    """The latest throughput line within the last max_bytes bytes of a service piece's
    log tail (ticket 13). Returns None if the log can't be read or this round has
    no throughput line (engine idle, downgraded to debug) -- the caller decides
    whether to keep last round's displayed value; this function doesn't guess."""
    try:
        with open(log_path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            tail = f.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    return parse_vllm_stats(tail)


def atomic_write(path, obj):
    """tmp + os.replace, same pattern as run.py save_state -- a half-written file is
    never read by the exit point."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1))
    os.replace(tmp, path)


def append_jsonl(path, lines):
    """Sample history is one file per job, appended round by round (one sample point per line)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        for line in lines:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")


def load_state():
    """state.json missing/broken -> {} (the sampler restores from here after a
    stateless restart; if it can't be read, treat it as starting from scratch --
    must not let the long-running process die)."""
    p = MONITOR_DIR / "state.json"
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return {}


def read_incidents_tail(n=20):
    """The last n lines of incidents.jsonl (this file is only actually written starting
    at Task 14; returns an empty list if it doesn't exist yet -- not an error)."""
    p = MONITOR_DIR / "incidents.jsonl"
    try:
        lines = p.read_text().splitlines()
    except OSError:
        return []
    out = []
    for line in lines[-n:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


INCIDENT_PROMPT = """You are the incident agent for the new1 project. You do exactly one thing -- "get the experiment sorted" -- and you do not write reports for humans to read.
Incident: job {job} piece {idx} (session {session}, host {host}, GPU {gpus}) verdict {verdict}.
Log: {log}
First look at the scene: tail -c 8192 '{log}' | tr '\\r' '\\n' | tail -40
Job ledger json: cd /home/y-guo/reproduce/new1 && python3 run.py gpu-jobs json
Rules (do not cross the line):
- {refire_clause}
- If the verdict is suspected stall: only read the log to locate the cause; do not kill any session, do not modify any file.
- Touch only this one piece; leave every other job alone.
- When done, print one line: DONE <what you did, within 15 characters>.
"""

_REFIRE_ALLOWED_CLAUSE = (
    "If the verdict is dead: read the log to locate the cause of death, then refire once: "
    "`python3 run.py launch --refire {job} --idx {idx}`; "
    "if the original card is occupied (the command will error), pick a free card with `python3 run.py gpu-jobs free`, then add "
    "`--piece <host>:<gpus>` and retry once")
_REFIRE_DENIED_CLAUSE = "This piece has used up its refire quota: autopsy only, do not launch anything else"


def should_trigger(row, ps):
    """Pure-function rule for incident triggering (design §5, ticket 12): triggers only
    when `row["escalated"]` is true and `ps["incident_open"]` is empty -- the same
    incident spawns an agent only once.
    `allow_refire` = the verdict is dead and this piece slot has not been refired
    yet (`ps["refires"] == 0`). Returns (whether it triggers, whether refire is
    allowed)."""
    if not row.get("escalated"):
        return False, False
    if ps.get("incident_open"):
        return False, False
    allow_refire = (row["verdict"] == verdicts.V_DEAD
                     and ps.get("refires", 0) == 0)
    return True, allow_refire


def build_incident_prompt(row, allow_refire):
    """row + refire permission -> the incident agent's prompt (pure function, ticket 12)."""
    if allow_refire:
        refire_clause = _REFIRE_ALLOWED_CLAUSE.format(
            job=row["job"], idx=row["idx"])
    else:
        refire_clause = _REFIRE_DENIED_CLAUSE
    return INCIDENT_PROMPT.format(
        job=row["job"], idx=row["idx"], session=row.get("session"),
        host=row.get("host"), gpus=row.get("gpus"), verdict=row["verdict"],
        log=row.get("log"), refire_clause=refire_clause)


def spawn_agent(prompt, out_path):
    """Spawn a headless incident agent (design §5, ticket 12, authorized by the user on
    2026-08-08): a detached claude subprocess, model pinned to opus, stdout/stderr
    all go to out_path. Popen does not wait -- the sampling loop must not be
    blocked by an autopsy. Returns the Popen object (for tests).

    Environment switch `NEW1_NO_SPAWN` (final-review C1, 2026-08-09): when
    non-empty, does not create a subprocess, only writes one placeholder line to
    out_path and returns None -- a structural fallback for unit tests; mocking this
    function is the first line of defense, and this switch is the second, to keep a
    real process from running in case a mock is missed.

    Only launches once `claude` resolves to an absolute path (`shutil.which`)
    (final-review C3): the long-running sampler started by crontab often doesn't
    inherit the login shell's config, its PATH, so if resolution fails there's no
    way to confirm the launched binary is the right one -- raise directly when it's
    not found, and let the caller (`maybe_trigger_incidents`) catch it and record it
    into the incident record, instead of silently betting a bare "claude" string
    happens to be on PATH."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if os.environ.get("NEW1_NO_SPAWN"):
        with open(out_path, "ab") as f:
            f.write(b"[NEW1_NO_SPAWN] would spawn incident agent\n")
        return None
    claude_bin = shutil.which("claude")
    if claude_bin is None:
        raise RuntimeError(
            "claude cannot be resolved in PATH (spawn_agent needs an absolute path; "
            "a common crontab-environment pitfall: PATH doesn't inherit the login shell config)")
    with open(out_path, "ab") as f:
        return subprocess.Popen(
            [claude_bin, "-p", prompt, "--model", "opus",
             "--dangerously-skip-permissions"],
            cwd=str(OPS.parent), stdin=subprocess.DEVNULL,
            stdout=f, stderr=subprocess.STDOUT, start_new_session=True)


def maybe_trigger_incidents(rows, st):
    """Check should_trigger piece by piece; on a hit: append the incident record to
    incidents.jsonl -> spawn_agent -> ps["incident_open"] = the incident number (the
    key field that prevents duplicates).
    The caller must persist state.json only after this function runs, otherwise
    incident_open only lives in memory, and the next round of the long-running loop
    will spawn another agent for the same incident."""
    for row in rows:
        ps = st.get(piece_key(row["job"], row["idx"]))
        if not ps:
            continue
        trigger, allow_refire = should_trigger(row, ps)
        if not trigger:
            continue
        inc_id = "{}_{}#{}".format(
            datetime.now().strftime("%Y%m%d-%H%M%S"), row["job"], row["idx"])
        out_path = MONITOR_DIR / "incidents" / f"{inc_id}.out"
        inc = {
            "id": inc_id, "t": time.time(), "job": row["job"],
            "idx": row["idx"], "host": row.get("host"),
            "gpus": row.get("gpus"), "session": row.get("session"),
            "verdict": row["verdict"], "log": row.get("log"),
            "allow_refire": allow_refire, "out": str(out_path),
        }
        # A spawn failure (usually: no claude on PATH) must not let the exception escape
        # sample_once -- the long-running loop does have main()'s try/except as a
        # fallback, but one spawn failure should not drag down this round's sampling and
        # persistence for the other pieces. Record the failure as-is into the incident
        # record, and set incident_open all the same -- the same incident won't retry
        # every round just because spawn failed.
        try:
            spawn_agent(build_incident_prompt(row, allow_refire), out_path)
        except Exception as e:
            inc["spawn_error"] = str(e)
        append_jsonl(MONITOR_DIR / "incidents.jsonl", [inc])
        ps["incident_open"] = inc_id


def piece_key(job_name, idx):
    return f"{job_name}#{idx}"


def _piece_launched_at(piece, job):
    """If the piece has no launched_at (old format from manual register), fall back to
    the job's started_at; if that's missing too, use now -- a lenient handling,
    since both the login machine and the launch machine are NTP-synced, minute-
    level error is acceptable."""
    la = piece.get("launched_at")
    if la is not None:
        return float(la)
    started = job.get("started_at")
    if started:
        try:
            return datetime.strptime(started, "%Y-%m-%d %H:%M").timestamp()
        except ValueError:
            pass
    return time.time()


def probe_port(host, port, timeout=3):
    """Port probe for a service-type piece: HTTP GET http://host:port/health,
    connection refused / timeout / any exception -> False. vLLM's /health returns
    200 (ticket 13 checked this; update here if it turns out different)."""
    try:
        with urllib.request.urlopen(
                f"http://{host}:{port}/health", timeout=timeout) as r:
            return 200 <= r.status < 300
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _new_piece_state(launched_at, refires=0):
    return {
        "first_beat": None,
        "recent_beats": [],
        "last_new_beat_mono": None,
        "last_done": None,
        "last_total": None,
        "last_unit": None,
        "last_status": None,
        "launched_at": launched_at,
        "alive_last": None,
        "probe_fail_rounds": 0,
        "port_ok": None,
        "port_ever_ok": False,
        "port_fail_rounds": 0,
        "vllm_stats": None,
        "verdict": None,
        "escalated_since_mono": None,
        "incident_open": False,
        "refires": refires,
    }


def update_piece_state(st, job, idx, piece, beats, alive, now_mono,
                        vllm_stats=None):
    """Accumulate one piece's running state (design §3):
    - if launched_at changed (a refire) -> the whole state segment restarts,
      refires += 1
    - entries in beats newer than last_done/last_ts get appended into recent_beats
      (capped at <= typical_beats entries), and last_new_beat_mono = now_mono is
      refreshed
    - first_beat is recorded only the first time a heartbeat is seen
    - alive: None (probe failed) -> keep alive_last, probe_fail_rounds += 1;
      True/False -> take it directly, probe_fail_rounds = 0
    - service type: port_ok comes from probe_port(); port_ever_ok/port_fail_rounds
      accumulate the same way; `vllm_stats` is this round's parsed throughput-line
      result passed in by the caller (sample_once) (ticket 13), used only to
      display the rate, not fed into the verdict -- when this round has no
      throughput line (engine idle, downgraded to debug, log unreadable),
      vllm_stats=None, and last round's displayed value is kept instead of
      flashing the rate display blank just because the stream paused (spec: "no
      throughput line while idle does not count as a stall")
    Return value is this piece's state dict (already attached in place on st; st is
    persisted by the caller).
    """
    key = piece_key(job["name"], idx)
    launched_at = _piece_launched_at(piece, job)
    prev = st.get(key)
    if prev is None:
        ps = _new_piece_state(launched_at, refires=0)
        st[key] = ps
    elif prev.get("launched_at") != launched_at:
        ps = _new_piece_state(launched_at, refires=prev.get("refires", 0) + 1)
        st[key] = ps
    else:
        ps = prev

    # alive
    if alive is None:
        ps["probe_fail_rounds"] = ps.get("probe_fail_rounds", 0) + 1
    else:
        ps["alive_last"] = alive
        ps["probe_fail_rounds"] = 0

    # heartbeat dedup and accumulation
    last_key = None
    if ps["recent_beats"]:
        lb = ps["recent_beats"][-1]
        last_key = (lb["ts"], lb["done"])
    added_new = False
    for b in beats:
        cur = (b["ts"], b["done"])
        if last_key is None or cur > last_key:
            if ps["first_beat"] is None:
                ps["first_beat"] = {"ts": b["ts"], "done": b["done"]}
            ps["recent_beats"].append({
                "ts": b["ts"], "done": b["done"],
                "tok_in": b.get("tok_in"), "tok_out": b.get("tok_out"),
                "loss": b.get("loss"), "status": b.get("status"),
            })
            last_key = cur
            added_new = True
        ps["last_total"] = b.get("total")
        ps["last_unit"] = b.get("unit")
        ps["last_status"] = b.get("status")
    if added_new:
        ps["last_new_beat_mono"] = now_mono
        ps["last_done"] = last_key[1]
    if len(ps["recent_beats"]) > _BEATS_CAP:
        ps["recent_beats"] = ps["recent_beats"][-_BEATS_CAP:]

    # service type: port probe + throughput-line display (ticket 13, the verdict uses
    # only port_ok, not vllm_stats)
    if piece.get("kind") == "service":
        port = piece.get("port")
        port_ok = probe_port(piece["host"], port) if port else False
        ps["port_ok"] = port_ok
        if port_ok:
            ps["port_ever_ok"] = True
            ps["port_fail_rounds"] = 0
        else:
            ps["port_fail_rounds"] = ps.get("port_fail_rounds", 0) + 1
        if vllm_stats is not None:
            ps["vllm_stats"] = vllm_stats

    return ps


def build_row(job, idx, piece, ps, now_mono, now_wall):
    """State -> exit-point row: calls verdicts.stall_line_s (override=the stall_line in
    the piece) / rates / judge, computes progress_pct and eta_s (falls back to the
    average when the recent rate has no value; None if neither has a value)."""
    kind = piece.get("kind", "batch")
    beat_ts = [b["ts"] for b in ps.get("recent_beats", [])]
    stall_s = verdicts.stall_line_s(beat_ts, override=piece.get("stall_line"))
    escalate_s = piece.get("escalate_line")
    warmup_s = job.get("monitor", {}).get(
        "warmup_s", verdicts.DEFAULTS["warmup_line_s"])
    avg_rate, recent_rate = verdicts.rates(
        ps.get("first_beat"), ps.get("recent_beats", []))

    beat_age_s = None
    if ps.get("last_new_beat_mono") is not None:
        beat_age_s = now_mono - ps["last_new_beat_mono"]
    since_launch_s = now_wall - ps.get("launched_at", now_wall)

    p = {
        "kind": kind,
        "alive": ps.get("alive_last"),
        "done": ps.get("last_done"),
        "total": ps.get("last_total"),
        "status": ps.get("last_status"),
        "has_beat": ps.get("first_beat") is not None,
        "since_launch_s": since_launch_s,
        "beat_age_s": beat_age_s,
        "warmup_s": warmup_s,
        "stall_s": stall_s,
        "escalate_s": escalate_s,
        "avg_rate": avg_rate,
        "recent_rate": recent_rate,
        "port_ok": ps.get("port_ok"),
        "port_ever_ok": ps.get("port_ever_ok", False),
        "port_fail_rounds": ps.get("port_fail_rounds", 0),
    }
    verdict, escalated = verdicts.judge(p)
    ps["verdict"] = verdict

    done, total = ps.get("last_done"), ps.get("last_total")
    progress_pct = None
    if done is not None and total:
        progress_pct = round(100 * done / total, 1)
    eta_s = None
    if done is not None and total is not None:
        remaining = total - done
        # Only fall back to the average when the recent rate has no value (None); a recent
        # rate of exactly 0 (genuinely stopped) must not be quietly swapped for the average
        # rate by a truthy check that mistakes it for "no value"
        rate_for_eta = recent_rate if recent_rate is not None else avg_rate
        if remaining >= 0 and rate_for_eta:
            eta_s = remaining / rate_for_eta

    last_beat = ps["recent_beats"][-1] if ps.get("recent_beats") else {}
    probe_fail_rounds = ps.get("probe_fail_rounds", 0)

    # For service type, the tok_in/tok_out display fields reuse the same field
    # positions as the heartbeat protocol, but the meaning changes to throughput rate
    # (tokens/s) instead of a cumulative count -- service pieces produce no heartbeats,
    # last_beat is always an empty dict, so this takes the value from vllm_stats
    # instead (ticket 13: the throughput line is only for display, it does not feed
    # into the verdict)
    if kind == "service":
        vs = ps.get("vllm_stats") or {}
        tok_in, tok_out = vs.get("prompt_tok_s"), vs.get("gen_tok_s")
    else:
        tok_in, tok_out = last_beat.get("tok_in"), last_beat.get("tok_out")

    return {
        "job": job["name"], "idx": idx, "host": piece["host"],
        "gpus": piece.get("gpus"), "session": piece.get("session"),
        "kind": kind, "verdict": verdict, "escalated": escalated,
        "done": done, "total": total, "unit": ps.get("last_unit"),
        "progress_pct": progress_pct,
        "avg_rate": avg_rate, "recent_rate": recent_rate,
        "tok_in": tok_in, "tok_out": tok_out,
        "loss": last_beat.get("loss"), "eta_s": eta_s,
        "log": piece.get("log"),
        "probe_failed": probe_fail_rounds >= _PROBE_FAIL_ROUNDS_RED,
        "probe_fail_rounds": probe_fail_rounds,
        "refires": ps.get("refires", 0),
    }


def sample_once():
    reg = load_reg()
    hosts = {p["host"] for j in reg["active"] for p in j["pieces"]} | set(DEFAULT_HOSTS)
    live = live_sessions(hosts)
    st = load_state()
    rows, per_job_lines = [], {}
    now_mono, now_wall = time.monotonic(), time.time()
    for job in reg["active"]:
        for idx, piece in enumerate(job["pieces"]):
            sess_set = live.get(piece["host"])
            alive = None if sess_set is None else (piece["session"] in sess_set)
            # service piece (ticket 13): skips heartbeat parsing, the log goes through
            # read_vllm_stats which only takes the throughput line for display; the verdict is
            # decided separately by probe_port inside update_piece_state.
            if piece.get("kind") == "service":
                beats, vllm_stats = [], read_vllm_stats(piece["log"])
            else:
                beats, vllm_stats = read_beats(piece["log"]), None
            ps = update_piece_state(st, job, idx, piece, beats, alive,
                                    now_mono, vllm_stats=vllm_stats)
            row = build_row(job, idx, piece, ps, now_mono, now_wall)
            rows.append(row)
            per_job_lines.setdefault(job["name"], []).append(dict(row, t=now_wall))

    registered = {}
    for j in reg["active"]:
        for p in j["pieces"]:
            registered.setdefault(p["host"], set()).add(p["session"])
    extras = {}
    for h, sess_set in live.items():
        if sess_set is None:
            continue
        unreg = sorted(sess_set - registered.get(h, set()))
        if unreg:
            extras[h] = unreg

    # Persist state.json immediately after an incident triggers (final-review C3,
    # 2026-08-09): incident_open must be persisted together with this round's state,
    # otherwise the next round of the long-running loop's load_state() reads the old
    # state and spawns another agent for the same incident. Persisting history/latest
    # is moved to after state.json -- a history write failure (e.g. NFS jitter) must
    # not drag incident_open down with it: state.json has already landed.
    maybe_trigger_incidents(rows, st)
    atomic_write(MONITOR_DIR / "state.json", st)
    latest = {"sampled_at": now_wall, "rows": rows, "extras": extras,
              "incidents_tail": read_incidents_tail()}
    for jname, lines in per_job_lines.items():
        append_jsonl(MONITOR_DIR / "history" / f"{jname}.jsonl", lines)
    atomic_write(MONITOR_DIR / "latest.json", latest)
    return latest


def _load_latest_from(monitor_dir):
    """The web exit point reads the file on disk, it does not touch the sampling
    thread's memory (design §3) -- returns None if latest.json is missing/broken,
    the caller renders a "no sample" placeholder, must not error."""
    p = Path(monitor_dir) / "latest.json"
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def render_html(latest):
    """Sample result (the content of latest.json, or None) -> the job table web page,
    a pure function that does no IO. Table columns: JOB/PIECE/HOST/GPU/VERDICT/
    PROGRESS/RATE/token/ETA/SESSION.
    30-second <meta refresh>; the threshold for turning stale rows red =
    sample_interval_s * 3, generated into the page from verdicts.DEFAULTS, no
    separate copy of the number (ticket 06 acceptance requirement)."""
    stale_after_s = verdicts.DEFAULTS["sample_interval_s"] * 3

    def esc(x):
        return html.escape("" if x is None else str(x))

    def fmt_rate(r):
        return "-" if r is None else f"{r:.4g}/s"

    def fmt_tok(v):
        return "-" if v is None else str(v)

    def fmt_eta(v):
        if v is None:
            return "-"
        m, s = divmod(max(0, int(v)), 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}"

    if latest is None:
        body = "<p>No samples: latest.json is missing or unreadable, the sampler may not be running.</p>"
        sampled_at_js = "null"
        stamp = "-"
    else:
        sampled_at = latest.get("sampled_at")
        stamp = (time.strftime("%H:%M:%S", time.localtime(sampled_at))
                 if sampled_at else "-")
        sampled_at_js = "null" if sampled_at is None else repr(sampled_at)

        row_lines = []
        for r in latest.get("rows", []):
            pct = ("-" if r.get("progress_pct") is None
                   else f"{r['progress_pct']}%")
            tok = f"{fmt_tok(r.get('tok_in'))}/{fmt_tok(r.get('tok_out'))}"
            row_lines.append(
                "<tr><td>{job}</td><td>{idx}</td><td>{host}</td>"
                "<td>{gpus}</td><td>{verdict}</td><td>{pct}</td>"
                "<td>{rate}</td><td>{tok}</td><td>{eta}</td>"
                "<td>{sess}</td></tr>".format(
                    job=esc(r.get("job")), idx=esc(r.get("idx")),
                    host=esc(r.get("host")), gpus=esc(r.get("gpus")),
                    verdict=esc(r.get("verdict")), pct=esc(pct),
                    rate=fmt_rate(r.get("recent_rate")), tok=esc(tok),
                    eta=fmt_eta(r.get("eta_s")),
                    sess=esc(r.get("session"))))
        rows_body = ("\n".join(row_lines) if row_lines else
                     "<tr><td colspan=10>No jobs currently registered as running</td></tr>")

        incident_lines = []
        for inc in latest.get("incidents_tail", []):
            t = inc.get("t")
            t_str = (time.strftime("%H:%M:%S", time.localtime(t))
                     if t else "-")
            incident_lines.append(
                "<li>[{t}] {job}#{idx} {verdict}: {note}</li>".format(
                    t=esc(t_str), job=esc(inc.get("job")),
                    idx=esc(inc.get("idx")), verdict=esc(inc.get("verdict")),
                    note=esc(inc.get("note"))))
        incidents_body = ("\n".join(incident_lines) if incident_lines else
                          "<li>No incident records</li>")

        extras_lines = []
        for h_name, sessions in latest.get("extras", {}).items():
            extras_lines.append(
                "<li>{h}: {s}</li>".format(
                    h=esc(h_name), s=esc(", ".join(sessions))))
        extras_body = ("\n".join(extras_lines) if extras_lines else
                        "<li>No sessions outside the job ledger</li>")

        body = f"""
<h2>Job table</h2>
<table border="1" cellspacing="0" cellpadding="4">
<tr><th>JOB</th><th>PIECE</th><th>HOST</th><th>GPU</th><th>VERDICT</th>
<th>PROGRESS</th><th>RATE</th><th>token</th><th>ETA</th><th>SESSION</th></tr>
{rows_body}
</table>
<h2>Incident records</h2>
<ul>{incidents_body}</ul>
<h2>Sessions outside the job ledger</h2>
<ul>{extras_body}</ul>
"""

    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<meta http-equiv="refresh" content="30">
<title>new1 job monitor</title>
<style>
    body {{ font-family: sans-serif; }}
    #banner {{ padding: 6px 10px; margin-bottom: 10px; background: #eee; }}
    #banner.stale {{ background: #f88; color: #300; font-weight: bold; }}
    table {{ border-collapse: collapse; }}
    th, td {{ padding: 4px 8px; }}
</style>
</head>
<body>
<div id="banner">last sampled {esc(stamp)}</div>
{body}
<script>
(function () {{
    var sampledAt = {sampled_at_js};
    var staleAfterS = {stale_after_s};
    function tick() {{
        var banner = document.getElementById("banner");
        if (sampledAt === null) {{
            banner.classList.add("stale");
            return;
        }}
        var ageS = (Date.now() / 1000) - sampledAt;
        if (ageS > staleAfterS) {{
            banner.classList.add("stale");
        }} else {{
            banner.classList.remove("stale");
        }}
    }}
    tick();
    setInterval(tick, 5000);
}})();
</script>
</body></html>
"""


class _WebHandler(http.server.BaseHTTPRequestHandler):
    """monitor_dir is attached dynamically by WebServer via a subclass (a class
    attribute, since the handler is a new instance on every request, so it can't
    take a param through __init__)."""
    monitor_dir = None

    def log_message(self, fmt, *args):
        pass  # no need to pollute the sampler's stderr with access logs

    def do_GET(self):
        latest = _load_latest_from(self.monitor_dir)
        if self.path == "/json":
            if latest is None:
                self._send(503, b'{"error": "not sampled yet"}',
                            "application/json")
            else:
                body = json.dumps(latest, ensure_ascii=False).encode("utf-8")
                self._send(200, body, "application/json")
            return
        body = render_html(latest).encode("utf-8")
        self._send(200, body, "text/html; charset=utf-8")

    def _send(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class WebServer:
    """Sampler's web exit point (ticket 06): a separate thread, do_GET reads
    monitor_dir/latest.json fresh every time, it does not touch the sampling
    thread's memory -- an ssh hang on the sampling side does not affect serving
    the page (design §3). / serves the job table page, /json serves the raw
    latest.json content."""

    def __init__(self, port, monitor_dir):
        handler = type("_BoundHandler", (_WebHandler,),
                        {"monitor_dir": Path(monitor_dir)})
        self.httpd = http.server.ThreadingHTTPServer(("", port), handler)
        self._thread = None

    @property
    def server_address(self):
        return self.httpd.server_address

    def start(self):
        self._thread = threading.Thread(
            target=self.httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true",
                    help="sample one round then exit (for smoke tests)")
    ap.add_argument("--interval", type=float,
                    default=verdicts.DEFAULTS["sample_interval_s"])
    ap.add_argument("--port", type=int, default=8377,
                    help="web/json export port (ticket 06)")
    a = ap.parse_args()
    web = None
    if not a.once:
        web = WebServer(port=a.port, monitor_dir=MONITOR_DIR)
        web.start()
        print(f"[sampler] web on :{a.port}", file=sys.stderr, flush=True)
    while True:
        t0 = time.monotonic()
        try:
            sample_once()
        except Exception as e:  # a single round's failure must not kill the long-running process
            print(f"[sampler] round failed: {e}", file=sys.stderr, flush=True)
        if a.once:
            break
        time.sleep(max(1.0, a.interval - (time.monotonic() - t0)))
    if web is not None:
        web.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
