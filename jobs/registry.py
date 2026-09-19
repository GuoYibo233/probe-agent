"""The registry: runs.jsonl rows under a lock, meta.json, the heartbeat, the verdicts, ls/where/find/kill/free, RESULTS.md.

Standard library and PyYAML only, imported by every stage to write its start and
finish rows and by run.py for the subcommands. Imports nothing from this repo.
`constants/path_outputs.yaml` is read lazily, inside the functions that need it,
and cached in a module global, so `import jobs.registry`, `lock()`,
`append_start`, `append_finish`, `write_meta`, `write_done` and `beat` all work
before `constants/` exists.

The file is written in two halves: the writer half (called by stage programs, on
compute nodes and on the login machine) and the reader half (called by run.py's
subcommands and by the launch gate). `render()`, `cards_busy()` and `fold()` are
internal names used by both halves.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import shlex
import signal
import socket
import subprocess
import time
from datetime import datetime
from pathlib import Path
from statistics import median

import yaml

# ---------------------------------------------------------------------------
# Shared constants and path helpers
# ---------------------------------------------------------------------------

DEFAULTS: dict = {
    # Launcher / stall constants named directly in the verdict rules (8.5).
    "stall_line": 180,
    "escalate_line": 3,
    "warmup_s": 1800,
    "launch_timeout_s": 1800,
    # The five shape constants named directly in the verdict rules (8.5), under
    # their original names.
    "stall_mult": 5.0,
    "typical_beats": 20,
    "min_intervals": 3,
    "recent_beats": 10,
    "slow_ratio": 0.5,
}

_OUTPUTS_CONFIG: dict | None = None


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _runs_path() -> Path:
    return _repo_root() / "jobs" / "runs.jsonl"


def _lock_path() -> Path:
    return _repo_root() / "jobs" / "runs.jsonl.lock"


def _results_path() -> Path:
    return _repo_root() / "jobs" / "RESULTS.md"


def _outputs_config() -> dict:
    """`constants/path_outputs.yaml`, read once and cached in this module global."""
    global _OUTPUTS_CONFIG
    if _OUTPUTS_CONFIG is None:
        path = _repo_root() / "constants" / "path_outputs.yaml"
        with open(path) as f:
            _OUTPUTS_CONFIG = yaml.safe_load(f)
    return _OUTPUTS_CONFIG


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _parse_t(t: str) -> float:
    return datetime.strptime(t, "%Y-%m-%d %H:%M").timestamp()


def _age_s(t: str) -> float:
    return time.time() - _parse_t(t)


def _read_json(path: Path):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _write_json_atomic(path: Path, obj) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (path.name + ".tmp")
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def _write_text_atomic(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (path.name + ".tmp")
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# The writer half (8.0): called by stages, on compute nodes and on the login
# machine.
# ---------------------------------------------------------------------------

_lock_fd = None
_lock_depth = 0


class _Lock:
    """The re-entrant context manager `lock()` returns: one module-level file
    descriptor per process plus a depth counter, so a nested acquisition is a
    counter increment and never a second `fcntl` call."""

    def __enter__(self):
        global _lock_fd, _lock_depth
        if _lock_depth == 0:
            path = _lock_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            _lock_fd = open(path, "w")
            fcntl.flock(_lock_fd, fcntl.LOCK_EX)
        _lock_depth += 1
        return None

    def __exit__(self, exc_type, exc, tb):
        global _lock_fd, _lock_depth
        _lock_depth -= 1
        if _lock_depth == 0:
            fcntl.flock(_lock_fd, fcntl.LOCK_UN)
            _lock_fd.close()
            _lock_fd = None
        return False


def lock():
    """`fcntl.flock(LOCK_EX)` on `jobs/runs.jsonl.lock`, taken at depth 0 only
    and released when the outermost hold exits."""
    return _Lock()


def _append_row(row: dict) -> None:
    path = _runs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def append_start(row: dict) -> None:
    """Append one start row (8.1) and re-render `RESULTS.md`."""
    with lock():
        _append_row(row)
        render()


def append_finish(run_id: str, row: dict) -> None:
    """Append one finish row (8.2) for `run_id` and re-render `RESULTS.md`."""
    with lock():
        _append_row(row)
        render()


def _default_meta() -> dict:
    return {
        "meta_version": 1,
        "stage": None,
        "key": None,
        "dir": None,
        "versions": {},
        "upstream": {},
        "diff": {},
        "debug": False,
        "owners": [],
        "launches": [],
        "pieces": [],
        "split_files": [],
        "stage_extra": {},
    }


def _read_meta_or_recover(meta_path: Path) -> dict:
    """`meta.json`'s own read for `write_meta`: a missing file is a run's first
    call and gets a fresh default; a file that exists but does not parse as
    JSON is renamed aside as `meta.json.corrupt.<timestamp>` before a fresh
    default takes its place, so a scrambled write is archived for forensics
    rather than silently discarded (8.3)."""
    if not meta_path.exists():
        return _default_meta()
    try:
        with open(meta_path) as f:
            return json.load(f)
    except json.JSONDecodeError:
        corrupt = meta_path.with_name(
            meta_path.name + ".corrupt." + datetime.now().strftime("%Y%m%d_%H%M%S"))
        os.replace(meta_path, corrupt)
        return _default_meta()


def _merge_pieces(existing: list, new_entries: list) -> list:
    """`pieces is replaced entry by entry` (8.3): match on `index`, replace
    the matched entry whole, append an entry whose index is new."""
    by_index = {p.get("index"): p for p in existing}
    order = [p.get("index") for p in existing]
    for entry in new_entries:
        idx = entry.get("index")
        if idx not in by_index:
            order.append(idx)
        by_index[idx] = entry
    return [by_index[i] for i in order]


def write_meta(run_dir, **fields) -> None:
    """Rewrite the whole `meta.json` through a temporary name and `os.replace`,
    under `lock()`. `launches` is append-only, `pieces` is merged entry by
    entry, and a field the caller does not pass keeps its stored value (8.3)."""
    run_dir = Path(run_dir)
    meta_path = run_dir / "meta.json"
    with lock():
        meta = _read_meta_or_recover(meta_path)
        for name, value in fields.items():
            if name == "launches":
                meta.setdefault("launches", [])
                meta["launches"].extend(value)
            elif name == "pieces":
                meta["pieces"] = _merge_pieces(meta.get("pieces", []), value)
            else:
                meta[name] = value
        _write_json_atomic(meta_path, meta)


def write_done(run_dir, *, stage, key, commit, counts, versions, metrics,
                report, pairs=None, stage_extra=None) -> None:
    """Write `done.json` (1.5, 8.0) through a temporary name and a rename."""
    doc = {
        "stage": stage,
        "key": key,
        "commit": commit,
        "finished_at": _now(),
        "counts": counts,
        "versions": versions,
        "metrics": metrics,
        "report": report,
    }
    if pairs is not None:
        doc["pairs"] = pairs
    if stage_extra is not None:
        doc["stage_extra"] = stage_extra
    _write_json_atomic(Path(run_dir) / "done.json", doc)


class Heartbeat:
    """One piece incarnation's `heartbeat/<piece>-<launch>.jsonl` writer. Opens
    no `meta.json`; the caller opens it once, before its main loop, with
    `beat()`."""

    def __init__(self, path: Path):
        self._path = path
        self._file = open(path, "a")
        self._last = {"done": 0, "total": 0, "unit": ""}

    def _write(self, *, status=None, **extra) -> None:
        rec = dict(self._last)
        # A loop piece writes beats with a world open, which freezes
        # time.time(); every beat timestamp is the wall clock instead
        # (errata, measured 2026-09-17).
        rec["ts"] = time.clock_gettime(time.CLOCK_REALTIME)
        for key in ("tok_in", "tok_out", "loss"):
            if extra.get(key) is not None:
                rec[key] = extra[key]
        if status is not None:
            rec["status"] = status
        line = json.dumps(rec, ensure_ascii=False)
        self._file.write(line + "\n")
        self._file.flush()
        print("@hb " + line, flush=True)

    def emit(self, done: int, total: int, unit: str, **extra) -> None:
        self._last = {"done": int(done), "total": int(total), "unit": str(unit)}
        self._write(status=extra.pop("status", None), **extra)

    def finish(self) -> None:
        self._write(status="done")
        self._file.close()


def beat(run_dir: Path, piece: int) -> Heartbeat:
    """Resolve `<launch>` from this run directory's own `heartbeat/` listing
    (1 + the largest existing `n` for `heartbeat/<piece>-<n>.jsonl`, 0 when
    none exists) and open that file for append (8.4)."""
    run_dir = Path(run_dir)
    hb_dir = run_dir / "heartbeat"
    hb_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{piece}-"
    best = -1
    for p in hb_dir.iterdir():
        name = p.name
        if name.startswith(prefix) and name.endswith(".jsonl"):
            n_str = name[len(prefix):-len(".jsonl")]
            if n_str.isdigit():
                best = max(best, int(n_str))
    launch = best + 1
    return Heartbeat(hb_dir / f"{piece}-{launch}.jsonl")


# ---------------------------------------------------------------------------
# The reader half (8.0, 8.5): called by run.py's subcommands and by the
# launch gate.
# ---------------------------------------------------------------------------


def _read_rows() -> list[dict]:
    path = _runs_path()
    if not path.exists():
        return []
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def fold(rows: list[dict]) -> dict[str, dict]:
    """`run_id -> {"start": newest start row, "finish": the newest finish row
    that follows it, or None}` (8.2). The file is append-only in chronological
    order, so the last occurrence of each event kind for a `run_id` is already
    the newest. One `run_id` collects several start rows, and a relaunch after
    a `failed` or `launch_failed` finish appends its start row below that
    finish row: that finish row closed the earlier launch, so a start row
    clears it and the relaunch stays open until a finish row of its own lands
    (errata, wave 7)."""
    folded: dict[str, dict] = {}
    for row in rows:
        rid = row["run_id"]
        entry = folded.setdefault(rid, {"start": None, "finish": None})
        if row.get("ev") == "start":
            entry["start"] = row
            entry["finish"] = None
        elif row.get("ev") == "finish":
            entry["finish"] = row
    return folded


def _fmt_metrics(m) -> str:
    if not m:
        return "-"
    return " ".join(f"{k}={v}" for k, v in m.items())


def render() -> None:
    """Rewrite `jobs/RESULTS.md` from `jobs/runs.jsonl`: one markdown table,
    newest run first, one row per `run_id` folded from its newest start and
    newest finish row (8.2, 8.6). No per-run detail blocks."""
    folded = fold(_read_rows())
    entries = [(rid, e["start"], e["finish"]) for rid, e in folded.items()
               if e["start"] is not None]
    lines = [
        "# Registry results",
        "> Generated by `jobs/registry.py`'s `render()` from `jobs/runs.jsonl` — do not edit by hand.",
    ]
    if not entries:
        lines.append("No runs yet.")
    else:
        entries.sort(key=lambda e: e[1].get("t", ""), reverse=True)
        lines.append("")
        lines.append("| run_id | started | stage | workflow/setting | commit | status | numbers | report |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for run_id, start, finish in entries:
            status = finish.get("status") if finish else start.get("status", "launching")
            numbers = _fmt_metrics(finish.get("metrics")) if finish else "-"
            report = (finish.get("report") if finish else None) or "-"
            lines.append("| `{}` | {} | {} | {}/{} | `{}` | {} | {} | {} |".format(
                run_id, start.get("t", "-"), start.get("stage", "-"),
                start.get("workflow", "-"), start.get("setting", "-"),
                start.get("commit", "-"), status, numbers, report))
    _write_text_atomic(_results_path(), "\n".join(lines) + "\n")


def open_runs() -> list[dict]:
    """The newest start row of every run whose newest launch has no finish row yet."""
    return [e["start"] for e in fold(_read_rows()).values()
            if e["start"] is not None and e["finish"] is None]


def _folded_rows() -> list[dict]:
    out = []
    for e in fold(_read_rows()).values():
        start = e["start"]
        if start is None:
            continue
        row = dict(start)
        finish = e["finish"]
        if finish is not None:
            row["status"] = finish.get("status")
            row["counts"] = finish.get("counts")
            row["metrics"] = finish.get("metrics")
            row["report"] = finish.get("report")
            row["elapsed_s"] = finish.get("elapsed_s")
        out.append(row)
    return out


def find(fields: dict) -> list[dict]:
    """The folded rows whose `diff` matches every given field, newest first."""
    rows = _folded_rows()
    matched = [r for r in rows
               if all((r.get("diff") or {}).get(k) == v for k, v in fields.items())]
    matched.sort(key=lambda r: r.get("t", ""), reverse=True)
    return matched


def where(stage: str, key: str, *, debug: bool = False) -> Path:
    cfg = _outputs_config()
    root = Path(cfg["root"])
    if debug:
        root = root / cfg["debug_subdir"]
    return root / stage / key


def _pieces_of(run_dir: Path, start: dict) -> list[dict]:
    meta = _read_json(run_dir / "meta.json") or {}
    return meta.get("pieces") or start.get("pieces") or []


# -- Host probing: fail-closed, and never over ssh to this machine itself. --


def _canonical_host(raw: str, cfg: dict) -> str:
    """Normalise a host name or alias to the `hosts:` entry's `name`, so this
    machine's own `hostname` and its cluster alias compare equal (errata,
    3.4)."""
    for host in cfg.get("hosts", []):
        if raw == host.get("name") or raw == host.get("alias"):
            return host["name"]
    return raw


def _is_local_host(host_name: str, cfg: dict) -> bool:
    this_machine = socket.gethostname()
    return _canonical_host(host_name, cfg) == _canonical_host(this_machine, cfg)


def _remote_shell(host: str, script: str, timeout: float = 20.0) -> tuple[bool, str]:
    """Run `script` on `host`: locally through `bash -c` when `host` normalises
    to this machine, over `ssh -o BatchMode=yes` otherwise (errata). Returns
    `(ok, stdout)`; `ok` is False on any failure or timeout."""
    cfg = _outputs_config()
    if _is_local_host(host, cfg):
        argv = ["bash", "-c", script]
    else:
        argv = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", host, script]
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except Exception:
        return False, ""
    if r.returncode != 0:
        return False, ""
    return True, r.stdout


class _ProbedSessions(set):
    """The set `live_sessions()` returns: the real session names it collected,
    plus `failed_hosts`, the hosts whose probe did not answer, and `host_of`,
    the host each collected name came from — internal bookkeeping this
    module's own alive tests and `ls()`'s orphan-session check consult, so a
    piece on an unreachable host is still reported alive (fail-closed, 3.4)
    and an orphan session can still name its host."""

    def __init__(self, names=(), failed_hosts=(), host_of=None):
        super().__init__(names)
        self.failed_hosts = set(failed_hosts)
        self.host_of = dict(host_of) if host_of else {}


def live_sessions() -> set[str]:
    """One `tmux ls` per host of `constants/path_outputs.yaml`'s `hosts:`
    list, fail-closed. Returns bare session names."""
    cfg = _outputs_config()
    names: set[str] = set()
    failed: set[str] = set()
    host_of: dict[str, str] = {}
    for host in cfg.get("hosts", []):
        host_name = host["name"]
        ok, out = _remote_shell(host_name, "tmux ls -F '#S' 2>/dev/null; true")
        if ok:
            for name in out.split():
                names.add(name)
                host_of[name] = host_name
        else:
            failed.add(host_name)
    return _ProbedSessions(names, failed, host_of)


def session_alive(host: str, session: str) -> bool:
    """The single-piece, fail-closed form `jobs/launch.refire` probes before it
    deletes a piece's claims."""
    ok, out = _remote_shell(host, "tmux ls -F '#S' 2>/dev/null; true")
    if not ok:
        return True
    return session in out.split()


def _alive_on(host: str | None, session: str | None, sessions: set) -> bool:
    if not host or not session:
        return False
    if isinstance(sessions, _ProbedSessions):
        cfg = _outputs_config()
        if _canonical_host(host, cfg) in sessions.failed_hosts:
            return True
    return session in sessions


def _pid_alive(pid) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except Exception:
        return True
    return True


def _probe_port(piece: dict) -> bool | None:
    port = piece.get("port")
    host = piece.get("host")
    if not port or not host:
        return None
    cfg = _outputs_config()
    target = "127.0.0.1" if _is_local_host(host, cfg) else host
    try:
        with socket.create_connection((target, int(port)), timeout=3):
            return True
    except OSError:
        return False


def _probe_host_busy_cards(host_name: str, n_cards: int) -> set[int]:
    """The fail-closed `nvidia-smi` compute-process probe, one shell round
    trip per host covering every card index (2.5)."""
    if n_cards <= 0:
        return set()
    script = (
        "for i in $(seq 0 {}); do "
        "out=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader -i \"$i\" 2>/dev/null); "
        "if [ -n \"$out\" ]; then echo \"$i\"; fi; "
        "done; true"
    ).format(n_cards - 1)
    ok, out = _remote_shell(host_name, script)
    if not ok:
        return set(range(n_cards))
    busy = set()
    for token in out.split():
        try:
            busy.add(int(token))
        except ValueError:
            return set(range(n_cards))
    return busy


def cards_busy() -> dict[str, set[int]]:
    """A card is busy when `nvidia-smi` shows a compute process on it, or when
    it appears in the `pieces` list of a run with a start row and no finish
    row and either a live session or a start row younger than
    `DEFAULTS["launch_timeout_s"]` (2.5, 8.6). Probed now, never cached;
    fail-closed."""
    cfg = _outputs_config()
    busy: dict[str, set[int]] = {}
    for host in cfg.get("hosts", []):
        busy[host["name"]] = _probe_host_busy_cards(host["name"], host.get("cards", 0))
    folded = fold(_read_rows())
    if not folded:
        return busy
    sessions = live_sessions()
    for entry in folded.values():
        start, finish = entry["start"], entry["finish"]
        if start is None or finish is not None:
            continue
        run_dir = Path(start["dir"])
        young = _age_s(start["t"]) < DEFAULTS["launch_timeout_s"]
        for piece in _pieces_of(run_dir, start):
            host_name = piece.get("host")
            gpus = piece.get("gpus")
            if not host_name or not gpus:
                continue
            live = _alive_on(host_name, piece.get("session"), sessions)
            if live or young:
                ids = set()
                for token in str(gpus).split(","):
                    token = token.strip()
                    if token.isdigit():
                        ids.add(int(token))
                busy.setdefault(host_name, set()).update(ids)
    return busy


def free() -> dict[str, list[int]]:
    """Free cards per host, under `cards_busy()`'s test."""
    cfg = _outputs_config()
    busy = cards_busy()
    out: dict[str, list[int]] = {}
    for host in cfg.get("hosts", []):
        name = host["name"]
        n = host.get("cards", 0)
        out[name] = sorted(set(range(n)) - busy.get(name, set()))
    return out


# -- Verdicts (8.5): pure functions over a piece's beat history, liveness and
# kind. No IO, no per-piece override. --


def typical_gap_s(beat_ts: list[float]) -> float | None:
    ts = list(beat_ts)[-(DEFAULTS["typical_beats"] + 1):]
    gaps = [b - a for a, b in zip(ts, ts[1:]) if b >= a]
    if len(gaps) < DEFAULTS["min_intervals"]:
        return None
    return median(gaps)


def stall_line_s(beat_ts: list[float]) -> float:
    gap = typical_gap_s(beat_ts)
    if gap is None:
        return float(DEFAULTS["warmup_s"])
    return max(DEFAULTS["stall_mult"] * gap, float(DEFAULTS["stall_line"]))


def rates(first_beat: dict | None, recent_beats: list[dict]) -> tuple[float | None, float | None]:
    if not first_beat or not recent_beats:
        return None, None
    last = recent_beats[-1]
    avg = None
    dt = last["ts"] - first_beat["ts"]
    if dt > 0 and last["done"] >= first_beat["done"]:
        avg = (last["done"] - first_beat["done"]) / dt
    w = recent_beats[-DEFAULTS["recent_beats"]:]
    recent = None
    if len(w) >= 2:
        dtw = w[-1]["ts"] - w[0]["ts"]
        if dtw > 0 and w[-1]["done"] >= w[0]["done"]:
            recent = (w[-1]["done"] - w[0]["done"]) / dtw
    return avg, recent


def judge(piece: dict) -> tuple[str, bool]:
    """`done, dead, suspected stall, warming up, slowed, healthy`, in that
    priority order, for a `loop`, `train` or `cpu` piece."""
    done, total = piece.get("done"), piece.get("total")
    if piece.get("status") == "done" or (done is not None and total and done >= total):
        return "done", False
    if piece.get("alive") is False:
        return "dead", True
    warm = not piece.get("has_beat")
    age = piece["since_launch_s"] if warm else piece["beat_age_s"]
    line = float(DEFAULTS["warmup_s"]) if warm else stall_line_s(piece.get("beat_ts") or [])
    if age > line:
        esc_line = line * DEFAULTS["escalate_line"]
        return "suspected stall", age > esc_line
    if warm:
        return "warming up", False
    recent_rate, avg_rate = piece.get("recent_rate"), piece.get("avg_rate")
    if recent_rate is not None and avg_rate and recent_rate < DEFAULTS["slow_ratio"] * avg_rate:
        return "slowed", False
    return "healthy", False


def judge_service(piece: dict) -> tuple[str, bool]:
    """`dead, healthy, warming up, suspected stall` for a `service` piece,
    over its start-row time, its session liveness and one port probe."""
    if piece.get("alive") is False:
        return "dead", True
    if piece.get("port_ok"):
        return "healthy", False
    since = piece["since_launch_s"]
    line = float(DEFAULTS["warmup_s"])
    if since > line:
        esc_line = line * DEFAULTS["escalate_line"]
        return "suspected stall", since > esc_line
    return "warming up", False


def _beats_full(run_dir: Path, piece_index) -> list[dict]:
    hb_dir = run_dir / "heartbeat"
    if not hb_dir.is_dir():
        return []
    prefix = f"{piece_index}-"
    best_n, best_path = -1, None
    for p in hb_dir.iterdir():
        name = p.name
        if name.startswith(prefix) and name.endswith(".jsonl"):
            n_str = name[len(prefix):-len(".jsonl")]
            if n_str.isdigit() and int(n_str) > best_n:
                best_n, best_path = int(n_str), p
    if best_path is None:
        return []
    out = []
    with open(best_path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return out


def _piece_verdict_dict(piece: dict, run_dir: Path, sessions: set,
                         launch_t: str, now_ts: float) -> dict:
    kind = piece.get("kind")
    host = piece.get("host")
    session = piece.get("session")
    since_launch_s = now_ts - _parse_t(launch_t)
    if kind == "service":
        return {
            "kind": kind,
            "alive": _alive_on(host, session, sessions),
            "port_ok": _probe_port(piece),
            "since_launch_s": since_launch_s,
        }
    if kind == "cpu":
        alive = _pid_alive(piece.get("pid"))
    else:
        alive = _alive_on(host, session, sessions)
    beats = _beats_full(run_dir, piece.get("index"))
    has_beat = bool(beats)
    last = beats[-1] if beats else None
    beat_ts = [b.get("ts") for b in beats]
    recent_slice = beats[-DEFAULTS["typical_beats"]:] if beats else []
    avg_rate, recent_rate = rates(beats[0] if beats else None, recent_slice)
    return {
        "kind": kind,
        "alive": alive,
        "status": last.get("status") if last else None,
        "done": last.get("done") if last else None,
        "total": last.get("total") if last else None,
        # The beat's own unit, which 8.6's ls line prints beside done/total.
        "unit": last.get("unit") if last else None,
        "has_beat": has_beat,
        "beat_ts": beat_ts,
        "beat_age_s": (now_ts - beat_ts[-1]) if has_beat else None,
        "since_launch_s": since_launch_s,
        "port_ok": None,
        "avg_rate": avg_rate,
        "recent_rate": recent_rate,
    }


_SESSION_NAME_RE = re.compile(r"^.+-[0-9a-f]{12}-\d+$")


def _is_repo_session_name(name: str) -> bool:
    """Whether `name` has the shape this repo's own launcher names a tmux
    session with, `<stage>-<key>-<piece>` (contracts 2699): a 12-lowercase-
    hex `key` (the format `key()` returns) followed by a bare piece index.
    `hosts:` machines are shared cluster machines (3.4), so `live_sessions()`
    returns every session anyone is running there, under any name; a name
    with no such shape belongs to some other process on the host, not to
    this repo, and is never a candidate for 8.6's first orphan case."""
    return bool(_SESSION_NAME_RE.match(name))


def _known_sessions(all_entries) -> set[str]:
    """Every session name recorded in any run's current pieces (`meta.json`
    when it exists, else the start row), across the whole ledger — not just
    the rows `ls()` will display, so a session belonging to a filtered-out
    workflow or a filtered-out debug run is never mistaken for orphan."""
    known: set[str] = set()
    for entry in all_entries:
        start = entry["start"]
        if start is None:
            continue
        run_dir = Path(start["dir"])
        for piece in _pieces_of(run_dir, start):
            session = piece.get("session")
            if session:
                known.add(session)
    return known


def _orphan_session_row(name: str, host: str | None) -> dict:
    """A synthetic `ls()` row for a live tmux session matching no piece
    recorded anywhere in the ledger (8.6's first `orphan` case: "a tmux
    session of this repo matching no row"). There is no run behind it, so
    every run-identifying field is `None`; only the session's own name and,
    when known, its host are real."""
    return {
        "run_id": None,
        "t": "",
        "stage": None,
        "key": None,
        "dir": None,
        "workflow": None,
        "setting": None,
        "parent": None,
        "swept": None,
        "diff": None,
        "commit": None,
        "status": "orphan_session",
        "pieces": [{
            "index": None,
            "kind": None,
            "host": host,
            "session": name,
            "gpus": None,
            "verdict": "orphan",
            "escalated": False,
            "beat_age_s": None,
        }],
        "progress": (0, 0),
        "unit": None,
        "avg_rate": None,
        "recent_rate": None,
        "beat_age_s": None,
        "flags": {
            "edited": None,
            "behind": None,
            "consumed": False,
            "split": False,
            "pinned": False,
            "dirty": False,
            "debug": False,
            "orphan": True,
        },
    }


def _ls_row(entry: dict, sessions: set, now_ts: float, edited: dict, progress: dict,
            behind: dict, consumed: dict, split: dict, pinned: dict) -> dict:
    start, finish = entry["start"], entry["finish"]
    run_id = start["run_id"]
    run_dir = Path(start["dir"])
    pieces = _pieces_of(run_dir, start)
    piece_rows = []
    sum_done = sum_total = 0
    unit = None
    beat_ages: list[float] = []
    avg_rates: list[float] = []
    recent_rates: list[float] = []
    for piece in pieces:
        pv = _piece_verdict_dict(piece, run_dir, sessions, start["t"], now_ts)
        verdict, escalated = (judge_service(pv) if pv["kind"] == "service"
                              else judge(pv))
        if pv["kind"] != "service":
            sum_done += pv.get("done") or 0
            sum_total += pv.get("total") or 0
            unit = pv.get("unit") or unit
            if pv.get("beat_age_s") is not None:
                beat_ages.append(pv["beat_age_s"])
            if pv.get("avg_rate") is not None:
                avg_rates.append(pv["avg_rate"])
            if pv.get("recent_rate") is not None:
                recent_rates.append(pv["recent_rate"])
        piece_rows.append({
            "index": piece.get("index"),
            "kind": pv["kind"],
            "host": piece.get("host"),
            "session": piece.get("session"),
            # The cards this piece holds, as `jobs/launch.py` placed it (8.3); 8.6's ls line
            # prints them beside the session.
            "gpus": piece.get("gpus"),
            "verdict": verdict,
            "escalated": escalated,
            "beat_age_s": pv.get("beat_age_s"),
        })
    if run_id in progress:
        done, total = progress[run_id]
    else:
        done, total = sum_done, sum_total
    if finish is not None:
        status = finish.get("status")
        # 8.6's second orphan case: a service piece still running after its
        # owner run finished. The first case (a live session matching no row
        # at all) has no owner run to attach to and is flagged instead by
        # ls()'s own synthetic rows, built from _known_sessions().
        orphan = any(p["kind"] == "service" and p["verdict"] != "dead" for p in piece_rows)
    else:
        status = start.get("status", "launching")
        orphan = False
        if status == "launching" and _age_s(start["t"]) > DEFAULTS["launch_timeout_s"]:
            if not any(p["verdict"] != "dead" for p in piece_rows):
                status = "launch_failed"
    return {
        "run_id": run_id,
        "t": start.get("t"),
        "stage": start.get("stage"),
        "key": start.get("key"),
        "dir": start.get("dir"),
        "workflow": start.get("workflow"),
        "setting": start.get("setting"),
        "parent": start.get("parent"),
        "swept": start.get("swept"),
        "diff": start.get("diff"),
        "commit": start.get("commit"),
        "status": status,
        "pieces": piece_rows,
        "progress": (done, total),
        # The beat unit, the two rates and the newest heartbeat's age, folded over the run's
        # work pieces: 8.6's ls line prints progress as `done/total unit` with a rate, and the
        # heartbeat's age beside it.
        "unit": unit,
        "avg_rate": sum(avg_rates) if avg_rates else None,
        "recent_rate": sum(recent_rates) if recent_rates else None,
        "beat_age_s": min(beat_ages) if beat_ages else None,
        "flags": {
            "edited": edited.get(run_id),
            "behind": behind.get(run_id),
            "consumed": bool(consumed.get(run_id)),
            "split": bool(split.get(run_id)),
            "pinned": bool(pinned.get(run_id)),
            "dirty": bool(start.get("dirty")),
            "debug": bool(start.get("debug")),
            "orphan": orphan,
        },
    }


def ls(workflow: str | None = None, *, debug: bool = False,
       edited: dict[str, bool] | None = None,
       progress: dict[str, tuple[int, int]] | None = None,
       behind: dict[str, bool] | None = None,
       consumed: dict[str, bool] | None = None,
       split: dict[str, bool] | None = None,
       pinned: dict[str, bool] | None = None) -> list[dict]:
    """One folded row per run, verdicts included, plus one synthetic row per
    live tmux session that has this repo's own session-name shape and
    matches no piece anywhere in the ledger (8.6's `orphan`: "a tmux session
    of this repo matching no row"). `hosts:` machines are shared cluster
    machines (3.4), so `live_sessions()` returns every session anyone is
    running there; `_is_repo_session_name` is what narrows that raw set down
    to "of this repo" before the ledger is even consulted, so an unrelated
    session started by other work on the same host is never reported as this
    repo's own orphan. Calls `live_sessions()` whenever the ledger holds any
    run at all, regardless of the `workflow`/`debug` display filters: an
    orphan session belongs to no known run by construction, so it has no
    workflow to match a `workflow=` filter and no non-debug run to satisfy
    the default `debug=False` filter, and gating the probe on the filtered
    display set would hide a genuinely live orphaned session whenever that
    filter happens to pass nothing. Only a truly empty ledger (no run
    recorded at all) skips the probe, so `run.py ls` and
    `eval/method_table.table()` against an empty ledger issue no `ssh` at
    all (8.6, A10).

    `edited`, `behind`, `consumed`, `split` and `pinned` are the five flags of
    8.6 that `run.py` computes and passes in, for the reason `edited` names:
    this file imports nothing from the repo, so it can call neither `key` nor
    `version_history` nor a settings reader, and it hashes no upstream file.
    Given None, ls leaves that flag blank."""
    edited = edited or {}
    progress = progress or {}
    behind = behind or {}
    consumed = consumed or {}
    split = split or {}
    pinned = pinned or {}
    all_entries = [e for e in fold(_read_rows()).values() if e["start"] is not None]
    if not all_entries:
        return []
    entries = all_entries
    if workflow is not None:
        entries = [e for e in entries if e["start"].get("workflow") == workflow]
    if not debug:
        entries = [e for e in entries if not e["start"].get("debug")]
    sessions = live_sessions()
    now_ts = time.time()
    rows = [_ls_row(e, sessions, now_ts, edited, progress, behind, consumed, split, pinned)
            for e in entries]
    known = _known_sessions(all_entries)
    host_of = sessions.host_of if isinstance(sessions, _ProbedSessions) else {}
    repo_sessions = {n for n in sessions if _is_repo_session_name(n)}
    for name in sorted(repo_sessions - known):
        rows.append(_orphan_session_row(name, host_of.get(name)))
    rows.sort(key=lambda r: r.get("t", ""), reverse=True)
    return rows


def _attached_elsewhere(run_id: str) -> bool:
    for other_id, entry in fold(_read_rows()).items():
        if other_id == run_id or entry["start"] is None or entry["finish"] is not None:
            continue
        run_dir = Path(entry["start"]["dir"])
        if not run_dir.is_dir():
            continue
        for path in run_dir.glob("service_*.json"):
            doc = _read_json(path) or {}
            if doc.get("attached_to") == run_id:
                return True
    return False


def kill(run_id: str) -> list[str]:
    """End each piece of `run_id` — a tmux piece by its session, a `cpu`
    piece by its `pid`, both read from `meta.json`'s `pieces` list — and
    return the sessions it actually ended: a `cpu` piece counts only when its
    `pid` was still alive to signal, and a tmux piece only when the kill
    command actually reached its host (an unreachable host reports nothing
    ended for that piece, rather than a session that was never touched).
    Refuses while any live run's `service_<kind>_<replica>.json` names this
    `run_id` in `attached_to`."""
    entry = fold(_read_rows()).get(run_id)
    if entry is None or entry["start"] is None:
        return []
    if _attached_elsewhere(run_id):
        raise RuntimeError(
            f"run.py kill {run_id}: refused, a live run's service file names "
            f"it in attached_to")
    run_dir = Path(entry["start"]["dir"])
    ended = []
    for piece in _pieces_of(run_dir, entry["start"]):
        if piece.get("kind") == "cpu":
            pid = piece.get("pid")
            if not pid:
                continue
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                continue
            ended.append(f"pid:{pid}")
        else:
            session, host = piece.get("session"), piece.get("host")
            if session and host:
                ok, _out = _remote_shell(
                    host, f"tmux kill-session -t {shlex.quote(session)} 2>/dev/null; true")
                if ok:
                    ended.append(session)
    return ended


def sync() -> list[str]:
    """Fold every run directory's `done.json` and heartbeat files into the
    missing finish rows; write the `failed` row for a run with no `done.json`
    whose pieces `judge` calls `dead`; re-render `RESULTS.md`. Appends those
    rows itself, through `append_finish`."""
    synced = []
    for run_id, entry in fold(_read_rows()).items():
        start = entry["start"]
        if start is None or entry["finish"] is not None:
            continue
        run_dir = Path(start["dir"])
        done = _read_json(run_dir / "done.json")
        if done is not None:
            row = {
                "ev": "finish", "t": _now(), "run_id": run_id, "status": "ok",
                "counts": done.get("counts", {}), "metrics": done.get("metrics", {}),
                "report": done.get("report"), "elapsed_s": _age_s(start["t"]),
            }
            append_finish(run_id, row)
            synced.append(run_id)
            continue
        pieces = _pieces_of(run_dir, start)
        if not pieces:
            continue
        sessions = live_sessions()
        now_ts = time.time()
        verdicts = []
        for piece in pieces:
            pv = _piece_verdict_dict(piece, run_dir, sessions, start["t"], now_ts)
            v = judge_service(pv)[0] if pv["kind"] == "service" else judge(pv)[0]
            verdicts.append(v)
        if verdicts and all(v == "dead" for v in verdicts):
            row = {
                "ev": "finish", "t": _now(), "run_id": run_id, "status": "failed",
                "counts": {}, "metrics": {}, "report": None,
                "elapsed_s": _age_s(start["t"]),
            }
            append_finish(run_id, row)
            synced.append(run_id)
    return synced
