"""The registry: runs.jsonl rows under a lock, meta.json, the heartbeat, the verdicts, ls/where/find/kill/free, RESULTS.md.

Standard library and PyYAML only, imported by every stage to write its start and
finish rows and by run.py for the subcommands. Imports nothing from this repo.
`constants/path_outputs.yaml` and `constants/cards.yaml` are read lazily, inside
the functions that need them, and cached in module globals, so `import jobs.registry`, `lock()`,
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
_HOSTS: list[dict] | None = None


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


def hosts() -> list[dict]:
    """The cluster's hosts from `constants/cards.yaml`, the one file for card facts, read once
    and cached in this module global. Each entry carries the host's `name`, its `alias` where
    it has one, `cards` (how many cards it has: the length of its per-card list) and
    `memory_gib` (each card's memory in GiB, by card index)."""
    global _HOSTS
    if _HOSTS is None:
        with open(_repo_root() / "constants" / "cards.yaml") as f:
            entries = yaml.safe_load(f)["hosts"]
        _HOSTS = []
        for entry in entries:
            host = {"name": entry["name"], "cards": len(entry["cards"]),
                    "memory_gib": [int(card["memory_gib"]) for card in entry["cards"]]}
            if "alias" in entry:
                host["alias"] = entry["alias"]
            _HOSTS.append(host)
    return _HOSTS


def card_memory_gib() -> dict[str, list[int]]:
    """Host name -> each card's memory in GiB, by card index (`constants/cards.yaml`)."""
    return {host["name"]: host["memory_gib"] for host in hosts()}


def canonical_host(raw: str) -> str:
    """Normalise a host name or alias to its `constants/cards.yaml` entry's `name`, so this
    machine's own `hostname` and its cluster alias compare equal (errata, 3.4: this machine
    answers `shiga` to `hostname` while the host list calls it `tokyo105`)."""
    for host in hosts():
        if raw == host["name"] or raw == host.get("alias"):
            return host["name"]
    return raw


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


def launch_ordinal(run_dir) -> int:
    """How many launches this run directory has recorded: the length of
    `meta.json`'s append-only `launches` list (8.3), which every launch extends
    by one entry in the same lock hold that appends its start row."""
    meta = _read_json(Path(run_dir) / "meta.json") or {}
    return len(meta.get("launches") or [])


def write_done(run_dir, *, stage, key, commit, counts, versions, metrics,
                report, pairs=None, stage_extra=None) -> None:
    """Write `done.json` (1.5, 8.0) through a temporary name and a rename.

    `launch` names the launch that wrote this file, so a reader can tell the
    computation the open launch ran from the one before it (8.2, read by
    `sync` and by `run.py`'s walk, which close a run by this one rule). It is
    an ordinal and not a time because both stamps a reader could
    compare instead -- this file's `finished_at` and the start row's `t` -- come
    from `_now()` at minute resolution, and a stage that always recomputes (2.4)
    costs seconds, so its relaunch's start row lands in the minute the previous
    computation's `done.json` carries.
    """
    doc = {
        "stage": stage,
        "key": key,
        "commit": commit,
        "finished_at": _now(),
        "launch": launch_ordinal(run_dir),
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


def _beat_files(run_dir: Path, piece) -> dict[int, Path]:
    """`{<launch>: path}` over this piece's `heartbeat/<piece>-<launch>.jsonl` files."""
    hb_dir = Path(run_dir) / "heartbeat"
    files: dict[int, Path] = {}
    if not hb_dir.is_dir():
        return files
    prefix = f"{piece}-"
    for p in hb_dir.iterdir():
        name = p.name
        if name.startswith(prefix) and name.endswith(".jsonl"):
            n_str = name[len(prefix):-len(".jsonl")]
            if n_str.isdigit():
                files[int(n_str)] = p
    return files


def next_beat_launch(run_dir, piece) -> int:
    """The `<launch>` the next incarnation of this piece opens its heartbeat file under (8.4):
    1 + the largest existing `n` for `heartbeat/<piece>-<n>.jsonl`, 0 when none exists.
    `beat()` opens that file, and the launcher records the same number as the piece entry's
    `beat_launch` in `meta.json` before it starts the piece (`jobs/launch.py`, and `run.py`
    for a `cpu` piece), which is how a reader tells this incarnation's file from an earlier
    incarnation's."""
    return max(_beat_files(run_dir, piece), default=-1) + 1


def beat(run_dir: Path, piece: int) -> Heartbeat:
    """Open this piece's heartbeat file for append under `next_beat_launch` (8.4)."""
    run_dir = Path(run_dir)
    hb_dir = run_dir / "heartbeat"
    hb_dir.mkdir(parents=True, exist_ok=True)
    launch = next_beat_launch(run_dir, piece)
    return Heartbeat(hb_dir / f"{piece}-{launch}.jsonl")


def current_beats(run_dir, piece: dict) -> list[dict]:
    """The beat rows of the incarnation of a `loop`, `train` or `cpu` piece that its
    `meta.json` entry records: the newest heartbeat file whose `<launch>` is at or above the
    entry's `beat_launch`, and no rows while that incarnation has opened none yet.

    A relaunch, a `refire` or a `retry` starts a piece in a run directory that still holds
    the files of the piece's earlier incarnations, and the new process opens its own file
    only once it runs; until then the newest file on disk is an earlier incarnation's, which
    can end with the `status: "done"` row. Every verdict reads this incarnation's rows alone.
    An entry written before `beat_launch` existed (a launch before 2026-09-23) reads from
    `<launch>` 0, every file of the piece."""
    files = _beat_files(run_dir, piece.get("index"))
    first = piece.get("beat_launch", 0)
    current = [n for n in files if n >= first]
    if not current:
        return []
    out = []
    with open(files[max(current)]) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return out


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


# TODO(owner, 2026-09-21): `jobs/runs.jsonl` carries rows no experiment produced, and
# `render()` folds them into `jobs/RESULTS.md` like any other run. The registry is
# append-only and never hand-edited, so the rows stand until the owner rules on them:
#   - 42 fixture rows with run ids `sample-<n>-<m>` and run directories under
#     `/tmp/tmp*/out/sample/shared`, written into the real file by
#     `tests/test_registry_concurrent_append.py` before defect 9 of wave 7 was fixed
#     (74cfc76); committed in b59bdf2.
#   - the rows of `train-f895049ab1dc`, ten of them `launch_failed`, written by the
#     wave 7 session's relaunch loop during its first M-T3 attempt.
# Choices: leave them, or a one-off rewrite of the file by the owner with a commit that
# says so (an agent never does that), or a `fixture` filter in `fold()` keyed on the
# `/tmp/` run directory. Wave 7's record: .scratch/from-zero/sdd/2026-09-20-wave7/wave-result.md.
# Added 2026-09-22: the debug run `inject-4d9c736d3834` has a start row and no finish row. Its
# three records are finished and its sessions are gone, but agent/step_with_probe.py went to
# VERSION 3 before its wrap-up walk, so no walk computes its key any more and the row stays
# `launching`. It holds no card once the launch timeout has passed.
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


def _is_local_host(host_name: str) -> bool:
    this_machine = socket.gethostname()
    return canonical_host(host_name) == canonical_host(this_machine)


def _remote_shell(host: str, script: str, timeout: float = 20.0) -> tuple[bool, str]:
    """Run `script` on `host`: locally through `bash -c` when `host` normalises
    to this machine, over `ssh -o BatchMode=yes` to the host's
    `constants/cards.yaml` name otherwise (errata; an alias such as `shiga`
    resolves only inside the cluster network, the entry's name from outside it
    too). Returns `(ok, stdout)`; `ok` is False on any failure or timeout."""
    if _is_local_host(host):
        argv = ["bash", "-c", script]
    else:
        argv = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", canonical_host(host), script]
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
    """One `tmux ls` per host of `constants/cards.yaml`, fail-closed. Returns
    bare session names."""
    names: set[str] = set()
    failed: set[str] = set()
    host_of: dict[str, str] = {}
    for host in hosts():
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
        if canonical_host(host) in sessions.failed_hosts:
            return True
    return session in sessions


def pid_alive(host: str | None, pid) -> bool:
    """Whether a `cpu` piece's process is running on the host its piece entry names.

    A pid means something only on the machine that gave it, and `run.py` runs on any machine
    of the cluster, so the test goes to the piece's own host: in place when that host is this
    machine, over ssh otherwise. Fail-closed like every other probe here (3.4): a host that
    does not answer counts as alive. An entry with no host predates the host column and was
    written on the machine that ran it, which the login-host rule of that time made this one."""
    if not pid:
        return False
    if host is None or _is_local_host(host):
        try:
            os.kill(int(pid), 0)
        except ProcessLookupError:
            return False
        except Exception:
            return True
        return True
    ok, out = _remote_shell(host, f"test -d /proc/{int(pid)} && echo alive || echo dead")
    return out.strip() != "dead" if ok else True


def end_pid(host: str | None, pid) -> bool:
    """Send SIGTERM to a `cpu` piece's process on the host its piece entry names; True when a process was there to signal.

    A piece's process runs as the user who launched it, so a pid this user may not signal
    belongs to some other user's process that took the number over: it is not this run's
    process, and it counts like a pid with no process behind it. The remote branch reads the
    same way, because `kill` exits nonzero on a refused signal as well."""
    if not pid:
        return False
    if host is None or _is_local_host(host):
        try:
            os.kill(int(pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            return False
        return True
    ok, out = _remote_shell(host, f"kill -TERM {int(pid)} 2>/dev/null && echo ended || echo gone")
    return ok and out.strip() == "ended"


def _probe_port(piece: dict) -> bool | None:
    """Whether a service piece's port answers, tested on the piece's own host the way its
    session is tested with `tmux ls` there: a TCP connection to 127.0.0.1:<port> opened in
    place when the host is this machine, over ssh otherwise, so the verdict does not depend on
    whether this machine can route to the cluster's service ports. Fail-closed (3.4, 6.3): a
    failed or timed-out ssh reads as not answering. `None` for a piece with no host or port."""
    port = piece.get("port")
    host = piece.get("host")
    if not port or not host:
        return None
    script = f"timeout 3 bash -c {shlex.quote(f'exec 3<>/dev/tcp/127.0.0.1/{int(port)}')}"
    ok, _out = _remote_shell(host, script)
    return ok


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
    row and either a live session, or a start row younger than
    `DEFAULTS["launch_timeout_s"]` while the piece's work is still owed (2.5,
    8.6). A piece owes work until `_judge_pieces`, the verdict `ls` prints,
    calls it `done`: a work piece that wrote its finish row, and a service whose
    session ended once its run's work was done. The last loop piece of a
    finished `sample` or `inject` run ends the run's services before the
    wrap-up walk writes the finish row, so without that test their cards stayed
    reserved until the start row aged past the timeout. Probed now, never
    cached; fail-closed."""
    busy: dict[str, set[int]] = {}
    for host in hosts():
        busy[host["name"]] = _probe_host_busy_cards(host["name"], host["cards"])
    folded = fold(_read_rows())
    if not folded:
        return busy
    sessions = live_sessions()
    for entry in folded.values():
        start, finish = entry["start"], entry["finish"]
        if start is None or finish is not None:
            continue
        run_dir = Path(start["dir"])
        pieces = _pieces_of(run_dir, start)
        holds_cards = any(p.get("host") and p.get("gpus") for p in pieces)
        if not holds_cards:
            continue
        young = _age_s(start["t"]) < DEFAULTS["launch_timeout_s"]
        judged = _judge_pieces(pieces, run_dir, sessions, start["t"])
        for piece, (pv, verdict, _escalated) in zip(pieces, judged):
            host_name = piece.get("host")
            gpus = piece.get("gpus")
            if not host_name or not gpus:
                continue
            owes_work = verdict != "done"
            if pv["alive"] or (young and owes_work):
                ids = set()
                for token in str(gpus).split(","):
                    token = token.strip()
                    if token.isdigit():
                        ids.add(int(token))
                # Keyed by the `constants/cards.yaml` entry's own name, the key the
                # probe above and `free()` use, so a piece recorded under a host's
                # alias reserves that host's cards.
                busy.setdefault(canonical_host(host_name), set()).update(ids)
    return busy


def free() -> dict[str, list[int]]:
    """Free cards per host, under `cards_busy()`'s test."""
    busy = cards_busy()
    out: dict[str, list[int]] = {}
    for host in hosts():
        name = host["name"]
        out[name] = sorted(set(range(host["cards"])) - busy.get(name, set()))
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


# TODO(gyb, 2026-09-23): the contracts still state the old verdict rules in two rows of 8.5, both
# the owner's to update: the `judge` row calls a piece `done` on `status == done` or
# `done >= total`, where `judge` below reads only the `status: "done"` finish row; and the
# `judge_service` row calls a service `dead` whenever its session is gone, where `judge_service`
# below calls it `done` when its session is gone and every work piece of its run is `done`, and
# judges an attached agent service (`attached_to` in its endpoint file) by its port and its run's
# work instead of by its session, which ends once the endpoint file is written (7.4).
def judge(piece: dict) -> tuple[str, bool]:
    """`done, dead, suspected stall, warming up, slowed, healthy`, in that
    priority order, for a `loop`, `train` or `cpu` piece.

    A piece is `done` when the heartbeat file of its own incarnation, the one
    the entry's `beat_launch` names (an entry written before that field existed
    reads its newest file), ends with the `status: "done"` row
    `Heartbeat.finish` writes after the piece's last step (8.4),
    and by nothing else. A beat's `done` reaching its `total` is not that
    signal: a train piece's step beats reach the step total before its last
    validation and its prediction pass, and a claiming piece's total is the
    whole request (8.4), so a piece that dies after that beat and before its
    own finish row is `dead`, and `sync` and `launch_failed` can close it."""
    if piece.get("status") == "done":
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
    """`done, dead, healthy, warming up, suspected stall` for a `service`
    piece, over its start-row time, its session liveness, its port probe
    (`port_ok`, made only where this function reads it) and `work_done`, which
    `_judge_pieces` sets when the run has work pieces and `judge` calls every
    one of them `done`.

    A service exists to serve its run's work pieces, and the last loop piece
    ends its run's services once every requested record is finished
    (`agent/run_tasks.py`, 2.3), before the wrap-up walk closes the run. So a
    service whose session is gone is `done` when its run's work is done, and
    `dead` while that work is still owed: the fail-closed liveness rule for a
    service that dies during a run is unchanged.

    An attached agent service (`attached`, its endpoint file names another run
    in `attached_to`, 7.1) starts no server: its session writes the endpoint
    file and ends (7.4), and its run's loop pieces are served by the owning
    run's server on the port the piece records. So its session says nothing,
    and the port does: `done` once its run's work is done, `healthy` while the
    port answers, `dead` when the server it attached to stopped answering while
    that work is still owed."""
    if piece.get("attached"):
        if piece.get("work_done"):
            return "done", False
        if piece.get("port_ok"):
            return "healthy", False
        return "dead", True
    if piece.get("alive") is False:
        if piece.get("work_done"):
            return "done", False
        return "dead", True
    if piece.get("port_ok"):
        return "healthy", False
    since = piece["since_launch_s"]
    line = float(DEFAULTS["warmup_s"])
    if since > line:
        esc_line = line * DEFAULTS["escalate_line"]
        return "suspected stall", since > esc_line
    return "warming up", False


def launch_failed(started_at: str, verdicts: list[str]) -> bool:
    """Whether an open launch never came up (8.1): its start row is older than
    `DEFAULTS["launch_timeout_s"]` (8.5), it has pieces, and `judge` calls
    every one of them `dead`, so no process of this launch is left to write
    its own finish row.

    One rule, one word, every reader. `run.py ls` writes the `launch_failed`
    finish row for each run this selects (8.1, 8.2) and `sync` writes it for a
    run it reaches first, so the ledger, `RESULTS.md` and the `ls` line carry
    the same word for the same state instead of each naming it their own way."""
    return (bool(verdicts) and all(v == "dead" for v in verdicts)
            and _age_s(started_at) > DEFAULTS["launch_timeout_s"])


def _attached_to(run_dir: Path, piece: dict) -> str | None:
    """The `run_id` a service piece's endpoint file names in `attached_to` (7.1, 1.5): the run
    whose server this piece attached to instead of starting one, `None` for a piece that
    started its own server or has written no endpoint file yet."""
    endpoint_file = piece.get("endpoint_file")
    if endpoint_file is None:
        return None
    doc = _read_json(run_dir / endpoint_file) or {}
    return doc.get("attached_to")


def _service_verdict_dict(piece: dict, run_dir: Path, sessions: set, launch_t: str,
                          work_done: bool) -> dict:
    """The facts `judge_service` reads for one service piece, given whether its run's work
    pieces are all `done`. The port is probed only when `judge_service` reads it: for an
    attached service while its run's work is owed, and for a service of its own while its
    session is alive (or its host did not answer, which reads as alive, 3.4). Every other
    service is decided by its session and its run's work, and a probe is an ssh round trip
    to its host, so `port_ok` is `None` there. `since_launch_s` is measured against the
    clock read after the probe."""
    alive = _alive_on(piece.get("host"), piece.get("session"), sessions)
    attached = _attached_to(run_dir, piece) is not None
    if attached:
        reads_port = not work_done
    else:
        reads_port = alive
    port_ok = _probe_port(piece) if reads_port else None
    now_ts = time.time()
    return {
        "kind": "service",
        "alive": alive,
        "attached": attached,
        "port_ok": port_ok,
        "work_done": work_done,
        "since_launch_s": now_ts - _parse_t(launch_t),
    }


def _piece_verdict_dict(piece: dict, run_dir: Path, sessions: set, launch_t: str) -> dict:
    """The facts `judge` reads for one work piece (`loop`, `train` or `cpu`). Every age is
    measured against the clock read right after the piece's heartbeat file is read, so an age
    is never measured against an instant earlier than the file it ages."""
    kind = piece.get("kind")
    host = piece.get("host")
    session = piece.get("session")
    if kind == "cpu":
        alive = pid_alive(host, piece.get("pid"))
    else:
        alive = _alive_on(host, session, sessions)
    beats = current_beats(run_dir, piece)
    now_ts = time.time()
    since_launch_s = now_ts - _parse_t(launch_t)
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


def _judge_pieces(pieces: list[dict], run_dir: Path, sessions: set,
                  launch_t: str) -> list[tuple[dict, str, bool]]:
    """`(verdict dict, verdict, escalated)` per piece of one run, in the
    pieces' own order: the one derivation `ls()`, `sync()` and `cards_busy()`
    read. The
    work pieces (`loop`, `train`, `cpu`) are judged first, because a service
    piece's verdict depends on whether all of them are `done`
    (`judge_service`), and whether its port is probed at all depends on that
    too (`_service_verdict_dict`)."""
    judged: dict[int, tuple[dict, str, bool]] = {}
    for i, piece in enumerate(pieces):
        if piece.get("kind") == "service":
            continue
        pv = _piece_verdict_dict(piece, run_dir, sessions, launch_t)
        judged[i] = (pv, *judge(pv))
    work_done = bool(judged) and all(v == "done" for _pv, v, _esc in judged.values())
    for i, piece in enumerate(pieces):
        if piece.get("kind") == "service":
            pv = _service_verdict_dict(piece, run_dir, sessions, launch_t, work_done)
            judged[i] = (pv, *judge_service(pv))
    return [judged[i] for i in range(len(pieces))]


_SESSION_NAME_RE = re.compile(r"^.+-[0-9a-f]{12}-\d+$")


def _is_repo_session_name(name: str) -> bool:
    """Whether `name` has the shape this repo's own launcher names a tmux
    session with, `<stage>-<key>-<piece>` (contracts 2699): a 12-lowercase-
    hex `key` (the format `key()` returns) followed by a bare piece index.
    The hosts of `constants/cards.yaml` are shared cluster machines (3.4), so `live_sessions()`
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


def _ls_row(entry: dict, sessions: set, edited: dict, progress: dict,
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
    service_alive = False
    judged = _judge_pieces(pieces, run_dir, sessions, start["t"])
    for piece, (pv, verdict, escalated) in zip(pieces, judged):
        if pv["kind"] == "service":
            service_alive = service_alive or pv["alive"]
        else:
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
        # owner run finished, read from the session's liveness (fail-closed,
        # 3.4), since a service that ended with its run's work reads `done`.
        # The first case (a live session matching no row at all) has no owner
        # run to attach to and is flagged instead by ls()'s own synthetic
        # rows, built from _known_sessions().
        orphan = service_alive
    else:
        # The stored word, whatever it is: a launch that never came up is closed by the
        # `launch_failed` finish row `run.py ls` writes from `launch_failed()` before it
        # prints these rows, so this row and `render()`'s table read the same ledger.
        status = start.get("status", "launching")
        orphan = False
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
    of this repo matching no row"). The hosts of `constants/cards.yaml` are shared
    cluster machines (3.4), so `live_sessions()` returns every session anyone is
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
    rows = [_ls_row(e, sessions, edited, progress, behind, consumed, split, pinned)
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
    return the sessions it actually ended: a `cpu` piece is signalled only
    while the run is open and counts only when its `pid` was still alive to
    signal, and a tmux piece counts only when the kill
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
    # A `cpu` piece is signalled only while its run is open (no finish row after the newest
    # start row, the `open_runs()` scope that `run.py`'s `_live_pieces` judges a pid in): a CPU
    # stage's walk appends its finish row once the process exits, so a closed run's recorded pid
    # names a process that ended, and the number may since belong to an unrelated one.
    run_open = entry["finish"] is None
    ended = []
    for piece in _pieces_of(run_dir, entry["start"]):
        if piece.get("kind") == "cpu":
            pid = piece.get("pid")
            if run_open and end_pid(piece.get("host"), pid):
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
    missing finish rows; write the `launch_failed` row for a run whose open
    launch wrote no `done.json` of its own and that `launch_failed()` selects;
    re-render `RESULTS.md`. Appends those rows itself, through
    `append_finish`."""
    synced = []
    for run_id, entry in fold(_read_rows()).items():
        start = entry["start"]
        if start is None or entry["finish"] is not None:
            continue
        run_dir = Path(start["dir"])
        done = _read_json(run_dir / "done.json") or {}
        # 8.2: the finish row is owed to the computation the open launch ran,
        # and `write_done` stamps `done.json` with the launch that wrote it, so
        # this file closes the run when that ordinal is the directory's newest.
        # A relaunch into a directory that already served a request (2.3) or
        # already computed (2.4) starts with the previous computation's
        # `done.json` on disk, carrying the launch before this one; it leaves
        # the launch in flight open for its own finish row or for the dead-piece
        # test below, and so does a `done.json` from before this field existed.
        # This also satisfies the stamp 8.2 names: `fold` left this entry's
        # finish row empty, so every finish row of the `run_id` precedes the
        # open start row.
        if done.get("launch") == launch_ordinal(run_dir):
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
        verdicts = [verdict for _pv, verdict, _esc
                    in _judge_pieces(pieces, run_dir, sessions, start["t"])]
        # The same rule `run.py ls` closes such a run by, so whichever command reaches it
        # first writes the same word.
        if launch_failed(start["t"], verdicts):
            row = {
                "ev": "finish", "t": _now(), "run_id": run_id, "status": "launch_failed",
                "counts": {}, "metrics": {}, "report": None,
                "elapsed_s": _age_s(start["t"]),
            }
            append_finish(run_id, row)
            synced.append(run_id)
    return synced
