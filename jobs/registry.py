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
    it has one, `cards` (how many cards it has: the length of its per-card list),
    `memory_gib` (each card's memory in GiB, by card index) and `model` (each card's model, by
    card index)."""
    global _HOSTS
    if _HOSTS is None:
        with open(_repo_root() / "constants" / "cards.yaml") as f:
            entries = yaml.safe_load(f)["hosts"]
        _HOSTS = []
        for entry in entries:
            host = {"name": entry["name"], "cards": len(entry["cards"]),
                    "memory_gib": [int(card["memory_gib"]) for card in entry["cards"]],
                    "model": [str(card["model"]) for card in entry["cards"]]}
            if "alias" in entry:
                host["alias"] = entry["alias"]
            _HOSTS.append(host)
    return _HOSTS


def card_memory_gib() -> dict[str, list[int]]:
    """Host name -> each card's memory in GiB, by card index (`constants/cards.yaml`)."""
    return {host["name"]: host["memory_gib"] for host in hosts()}


def card_model(host: str, index: int) -> str | None:
    """The model of card `index` on `host`, a host's name or its alias (`constants/cards.yaml`);
    None for a host or a card index the file does not list."""
    name = canonical_host(host)
    for entry in hosts():
        if entry["name"] == name and 0 <= index < entry["cards"]:
            return entry["model"][index]
    return None


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
    """Append one finish row (8.2) for `run_id` and re-render `RESULTS.md`.

    The row of a card stage's run (`CARD_STAGES`, named by the run id's `<stage>-` prefix)
    gains the `card_record` of the incarnation it closes, built here and nowhere else, so every
    finish-row writer records it without carrying the field itself. A record that cannot be
    built is null, and the row is appended all the same."""
    with lock():
        if run_id.rpartition("-")[0] in CARD_STAGES:
            row = dict(row, card_record=_guarded(_card_record, run_id, row.get("status")))
        _append_row(row)
        render()


# -- The card record: what one incarnation of a card stage's run did on its cards, the field
# `append_finish` adds to that run's finish row. It reads the run's open start row, its
# meta.json, settings.yaml, heartbeat files and piece logs, and probes no host. --

# The stages whose finish rows carry a `card_record`: the three that hold cards.
CARD_STAGES = ("sample", "inject", "train")

# The record's task identity, the fields that decide a run's memory and speed: dotted fields of
# the run's frozen settings.yaml, by stage, beside `stage` and `debug`. A sample record adds the
# number of cards per agent server (from its agent service pieces), an inject record each probe
# service checkpoint's backbone and tuning (`_INJECT_CHECKPOINTS`).
CARD_TASK_FIELDS = {
    "sample": ("models.agent",),
    "inject": ("models.agent",),
    "train": ("models.probe", "probe.method", "probe.tuning", "probe.lora_r",
              "train.max_len", "train.events_per_mb", "train.grad_ckpt", "train.import_from"),
}
# An inject run's two probe-service checkpoints: the name the record gives each, and the entry of
# the run's settings.yaml `_upstream` that keys the train run it comes from.
_INJECT_CHECKPOINTS = (("probe_score", "probe_score.train"), ("probe_gen", "probe_gen.train"))
# The fields of that train run's settings.yaml a checkpoint is named by in the record.
_CHECKPOINT_FIELDS = (("backbone", "models.probe"), ("tuning", "probe.tuning"))

# The beat unit a stage's speed is counted in: a loop piece's tasks, and a train piece's
# training steps (its prediction pass beats in a unit of its own and is not counted).
SPEED_UNIT = {"sample": "task", "inject": "task", "train": "step"}

# A log line that names a memory failure: torch's CUDA allocator, and vLLM's two refusals to
# start when the card has no room left for its cache.
MEMORY_FAILURE_PATTERNS = ("CUDA out of memory", "OutOfMemoryError",
                           "exceeds available Mamba cache blocks",
                           "No available memory for the cache blocks")
# How much of a piece log's end the failure is read from, and how long a quoted line may be.
LOG_TAIL_BYTES = 16 * 1024
FAILURE_LINE_CHARS = 300
_TRACEBACK_HEADER = "Traceback (most recent call last)"
# What vLLM writes before a line of its processes' output, `(EngineCore pid=N) ` and its
# logger's `ERROR 10-02 20:37:44 [core.py:1330] `: a traceback's frame lines are indented after it.
_LOG_LINE_PREFIX = re.compile(r"^(?:\([^()]*\) )?(?:[A-Z]+ \d\d-\d\d \d\d:\d\d:\d\d \[[^\]]*\] )?")
# The three lines vLLM prints into an agent service's log as it loads a model.
_VLLM_WEIGHTS = re.compile(r"Model loading took ([0-9.]+) GiB memory")
_VLLM_KV_CACHE = re.compile(r"Available KV cache memory: ([0-9.]+) GiB")
_VLLM_CONCURRENCY = re.compile(r"Maximum concurrency for [0-9,]+ tokens per request: ([0-9.]+)x")
# The line the probe service prints once its checkpoints are loaded.
_PROBE_SERVICE_MEMORY = re.compile(r"probe service memory: ([0-9.]+) GiB reserved after loading")
_SERVICE_ENDPOINT = re.compile(r"^service_([a-z]+)_\d+\.json$")


def _guarded(fn, *args):
    """`fn(*args)`, or None when it raises: a record field that cannot be read (a log that is
    gone, a settings file that does not parse) is null, and the finish row is appended."""
    try:
        return fn(*args)
    except Exception:
        return None


def _card_record(run_id: str, status: str | None) -> dict | None:
    """The `card_record` of the finish row `append_finish` appends for a card stage's run, with
    status `status`: the incarnation its open start row launched (`launch`, the meta.json
    launches ordinal), the task identity, one entry per piece that holds cards, and the speed of
    its work pieces. None when the run has no open start row, because no incarnation ran since
    its last finish row. The pieces are the run's meta.json entries (`_pieces_of`), the start
    row's pieces with the launcher's `started` stamp, which the verdicts read."""
    entry = fold(_read_rows()).get(run_id)
    if entry is None or entry["start"] is None or entry["finish"] is not None:
        return None
    start = entry["start"]
    run_dir = Path(start["dir"])
    stage = start.get("stage")
    pieces = _pieces_of(run_dir, start)
    verdicts = _guarded(_finish_verdicts, pieces, run_dir, start["t"]) or [None] * len(pieces)
    return {
        "launch": _guarded(launch_ordinal, run_dir),
        "task": _guarded(_card_task, run_dir, stage, pieces),
        "pieces": [_card_piece(piece, verdict, run_dir, status)
                   for piece, verdict in zip(pieces, verdicts)
                   if piece.get("host") and piece.get("gpus")],
        "speed": _guarded(_card_speed, run_dir, stage, pieces),
    }


def _finish_verdicts(pieces: list[dict], run_dir: Path, launch_t: str) -> list[str | None]:
    """Each piece's verdict as its run's finish row finds it, by `judge` and `judge_service`.

    A finish row is appended once the incarnation's processes have ended or while they end (a
    train piece after its last beat, services its walk has torn down, a run `kill` ended), so
    every session is read as gone and no host is probed while the lock is held: a work piece is
    `done` on its own finish beat and `dead` or `not started` otherwise, and a service is `done`
    once every work piece is done and `dead` while work was owed. None for a `cpu` piece."""
    verdicts: list[str | None] = [None] * len(pieces)
    for i, piece in enumerate(pieces):
        if piece.get("kind") in ("loop", "train"):
            verdicts[i] = judge(_piece_verdict_dict(piece, run_dir, set(), launch_t))[0]
    work = [v for v in verdicts if v is not None]
    work_done = bool(work) and all(v == "done" for v in work)
    for i, piece in enumerate(pieces):
        if piece.get("kind") == "service":
            verdicts[i] = judge_service({"kind": "service", "alive": False, "attached": False,
                                         "port_ok": None, "work_done": work_done,
                                         "since_launch_s": 0.0})[0]
    return verdicts


def _card_piece(piece: dict, verdict: str | None, run_dir: Path, status: str | None) -> dict:
    """One card-holding piece's entry in the record: where it ran, the card model and memory,
    its memory figures, and the failure its log names. Every incarnation appends to the same
    log (`tee -a`), so the log is read from the entry's `log_offset`, the size the launcher
    recorded before this incarnation's session started (`jobs/launch.incarnation_origin`); an
    entry written before that field existed reads from byte 0. The failure is read only for a
    piece whose verdict is `dead` or in a run whose status is not `ok`, and never for a piece
    that was `not started`, which wrote nothing in this incarnation."""
    index = piece.get("index")
    kind = piece.get("kind")
    host = piece.get("host")
    gpus = str(piece.get("gpus"))
    log = run_dir / "log" / f"{index}.txt"
    offset = int(piece.get("log_offset") or 0)
    service = _service_of(piece)
    out: dict = {"index": index, "kind": kind}
    if kind == "service":
        out["service"] = service
    out["host"] = host
    out["gpus"] = gpus
    out["card_model"] = _guarded(_cards_model, host, gpus)
    out["card_gib"] = _guarded(_cards_gib, host, gpus)
    if kind == "train":
        out["peak_gib"] = _guarded(_peak_gib, run_dir, piece)
    elif service == "agent":
        out.update(_guarded(_agent_memory, log, offset)
                   or {"weights_gib": None, "kv_cache_gib": None, "max_concurrency": None})
    elif service == "probe":
        out["peak_gib"] = _guarded(_probe_memory, log, offset)
    failure = None
    if verdict != "not started" and (status != "ok" or verdict == "dead"):
        failure = _guarded(_log_failure, log, offset)
    out["failure"], out["failure_line"] = failure or (None, None)
    return out


def _service_of(piece: dict) -> str | None:
    """A service piece's kind, `agent` or `probe`, from its `service_<kind>_<replica>.json`
    endpoint file name; None for any other piece."""
    match = _SERVICE_ENDPOINT.match(piece.get("endpoint_file") or "")
    return match.group(1) if match else None


def _card_ids(gpus: str) -> list[int]:
    return [int(token) for token in str(gpus).split(",") if token.strip().isdigit()]


def _cards_model(host: str, gpus: str) -> str | None:
    """The model of a piece's cards: the one model, or the distinct models in card order joined
    by ` + ` when a piece spans cards of two models; None when a card is not in the file."""
    models = [card_model(host, i) for i in _card_ids(gpus)]
    if not models or None in models:
        return None
    return " + ".join(dict.fromkeys(models))


def _cards_gib(host: str, gpus: str) -> int:
    """The memory of a piece's card in GiB; on several cards, the smallest of them."""
    memory = card_memory_gib()[canonical_host(host)]
    return min(memory[i] for i in _card_ids(gpus))


def _peak_gib(run_dir: Path, piece: dict) -> float | None:
    """A train piece's peak memory: the largest `mem_gib` among its incarnation's beats."""
    values = [b["mem_gib"] for b in current_beats(run_dir, piece) if b.get("mem_gib") is not None]
    return max(values) if values else None


def _log_lines(log: Path, offset: int):
    """The lines of a log from byte `offset` on, decoded as UTF-8."""
    with open(log, "rb") as f:
        f.seek(offset)
        for raw in f:
            yield raw.decode("utf-8", errors="replace")


def _agent_memory(log: Path, offset: int) -> dict:
    """An agent service's memory figures from the three lines vLLM prints as it loads: the
    weights, the KV cache and the maximum concurrency of the newest load in the log from byte
    `offset` on, where this incarnation's output starts. A load line clears the other two and
    the cache lines after it fill them in, so a log read from byte 0 (an entry with no recorded
    offset) gives the newest incarnation's load. These lines come early, so everything after
    `offset` is read, not only the tail the failure is read from."""
    figures = {"weights_gib": None, "kv_cache_gib": None, "max_concurrency": None}
    for line in _log_lines(log, offset):
        if "Model loading took" in line:
            match = _VLLM_WEIGHTS.search(line)
            if match:
                figures = {"weights_gib": float(match.group(1)), "kv_cache_gib": None,
                           "max_concurrency": None}
        elif "Available KV cache memory" in line:
            match = _VLLM_KV_CACHE.search(line)
            if match:
                figures["kv_cache_gib"] = float(match.group(1))
        elif "Maximum concurrency" in line:
            match = _VLLM_CONCURRENCY.search(line)
            if match:
                figures["max_concurrency"] = float(match.group(1))
    return figures


def _probe_memory(log: Path, offset: int) -> float | None:
    """A probe service's memory: the GiB its newest `probe service memory:` line from byte
    `offset` on reports reserved after loading its checkpoints; None when there is no such
    line."""
    value = None
    for line in _log_lines(log, offset):
        if "probe service memory" in line:
            match = _PROBE_SERVICE_MEMORY.search(line)
            if match:
                value = float(match.group(1))
    return value


def _log_tail(log: Path, offset: int) -> list[str]:
    """The lines this incarnation wrote at the end of a log: from byte `offset` on, where its
    output starts, and no more than the last `LOG_TAIL_BYTES`; the first line is dropped when
    that limit cut inside it."""
    with open(log, "rb") as f:
        f.seek(0, os.SEEK_END)
        start = max(offset, f.tell() - LOG_TAIL_BYTES)
        f.seek(start)
        data = f.read()
    lines = data.decode("utf-8", errors="replace").splitlines()
    return lines[1:] if start > offset else lines


def _log_failure(log: Path, offset: int) -> tuple[str | None, str | None]:
    """`(failure, failure_line)` from the tail of a piece's log that this incarnation wrote
    (`_log_tail`): `memory` with the newest line that matches one of
    `MEMORY_FAILURE_PATTERNS`; `error` for any other traceback, with the exception line of the
    newest one, the first line after its header that is not indented once vLLM's line prefix is
    set aside; `(None, None)` when the tail holds neither. A quoted line is cut to
    `FAILURE_LINE_CHARS`."""
    lines = _log_tail(log, offset)
    for line in reversed(lines):
        if any(pattern in line for pattern in MEMORY_FAILURE_PATTERNS):
            return "memory", line.strip()[:FAILURE_LINE_CHARS]
    headers = [i for i, line in enumerate(lines) if _TRACEBACK_HEADER in line]
    if not headers:
        return None, None
    for line in lines[headers[-1] + 1:]:
        body = line[_LOG_LINE_PREFIX.match(line).end():]
        if body.strip() and not body[0].isspace():
            return "error", line.strip()[:FAILURE_LINE_CHARS]
    return "error", None


def _dotted(doc: dict | None, dotted: str):
    """The value at a dotted field of a parsed settings.yaml; None where the path is absent."""
    value = doc
    for part in dotted.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _card_task(run_dir: Path, stage: str, pieces: list[dict]) -> dict:
    """The record's task identity, read from the run's frozen settings.yaml (`CARD_TASK_FIELDS`)."""
    with open(run_dir / "settings.yaml") as f:
        doc = yaml.safe_load(f)
    task = {"stage": stage, "debug": bool(doc.get("_debug"))}
    for dotted in CARD_TASK_FIELDS[stage]:
        task[dotted] = _dotted(doc, dotted)
    if stage == "sample":
        agent = next((p for p in pieces if _service_of(p) == "agent" and p.get("gpus")), None)
        task["cards_per_agent_server"] = len(_card_ids(agent["gpus"])) if agent else None
    if stage == "inject":
        upstream = doc.get("_upstream") or {}
        for name, upstream_name in _INJECT_CHECKPOINTS:
            source = _guarded(_train_settings, upstream.get(upstream_name))
            for field_name, dotted in _CHECKPOINT_FIELDS:
                task[f"{name}.{field_name}"] = _dotted(source, dotted)
    return task


def _train_settings(key: str | None) -> dict | None:
    """The frozen settings.yaml of the train run keyed `key`: the one of the two roots (the
    outputs root and its debug subdirectory) whose settings.yaml records this very key."""
    if key is None:
        return None
    for debug in (False, True):
        path = where("train", key, debug=debug) / "settings.yaml"
        if path.exists():
            with open(path) as f:
                doc = yaml.safe_load(f) or {}
            if doc.get("_key") == key:
                return doc
    return None


def _card_speed(run_dir: Path, stage: str, pieces: list[dict]) -> dict | None:
    """The run's speed over its work pieces (`loop`, `train`) in this incarnation: each piece's
    `(last.done - first.done) / (last.ts - first.ts)` over its counting beats in the stage's
    `SPEED_UNIT`, summed over the pieces and given per hour, with the beats moved (`done`) and
    the longest piece's span (`span_s`). None while no piece has two such beats."""
    unit = SPEED_UNIT[stage]
    done, span_s, per_s = 0, 0.0, 0.0
    counted = False
    for piece in pieces:
        if piece.get("kind") not in ("loop", "train"):
            continue
        beats = [b for b in current_beats(run_dir, piece)
                 if not b.get("phase") and b.get("unit") == unit]
        if len(beats) < 2:
            continue
        first, last = beats[0], beats[-1]
        dt = last["ts"] - first["ts"]
        if dt <= 0:
            continue
        moved = last["done"] - first["done"]
        done += moved
        span_s = max(span_s, dt)
        per_s += moved / dt
        counted = True
    if not counted:
        return None
    return {"unit": unit, "done": done, "span_s": round(span_s, 1),
            "per_hour": round(per_s * 3600, 1)}


def _default_meta() -> dict:
    return {
        "meta_version": 1,
        "stage": None,
        "key": None,
        "dir": None,
        "era": None,
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


def write_done(run_dir, *, stage, key, commit, counts, era, metrics,
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
        "era": era,
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

    def _write(self, *, status=None, phase=None, **extra) -> None:
        rec = dict(self._last)
        # A loop piece writes beats with a world open, which freezes
        # time.time(); every beat timestamp is the wall clock instead
        # (errata, measured 2026-09-17).
        rec["ts"] = time.clock_gettime(time.CLOCK_REALTIME)
        # `mem_gib` is the peak card memory a train piece's process has reserved so far, in
        # GiB (`train/utils/trainer.py` passes it on every beat it emits).
        for key in ("tok_in", "tok_out", "loss", "mem_gib"):
            if extra.get(key) is not None:
                rec[key] = extra[key]
        if status is not None:
            rec["status"] = status
        if phase is not None:
            rec["phase"] = phase
        line = json.dumps(rec, ensure_ascii=False)
        self._file.write(line + "\n")
        self._file.flush()
        print("@hb " + line, flush=True)

    def emit(self, done: int, total: int, unit: str, **extra) -> None:
        self._last = {"done": int(done), "total": int(total), "unit": str(unit)}
        self._write(status=extra.pop("status", None), **extra)

    def touch(self, phase: str) -> None:
        """A beat that moves no count: the last `done/total unit` again, a fresh
        timestamp and the name of the phase the piece is in (`validate`,
        `predict`). A train piece's validation and prediction passes advance no
        optimizer step, so without these a long pass read `suspected stall`
        (repo test 2026-09-25, D4); `judge` reads the phase and does not call a
        piece `slowed` on a count that a pass by design leaves where it was."""
        self._write(phase=phase)

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
    """Rewrite `jobs/RESULTS.md` from `jobs/runs.jsonl`: the runs table, newest
    run first, one row per `run_id` folded from its newest start and newest
    finish row (8.2, 8.6), with no per-run detail blocks; then the "Runs by card
    type" table (`_card_type_lines`)."""
    rows = _read_rows()
    folded = fold(rows)
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
    lines.extend(_card_type_lines(rows))
    _write_text_atomic(_results_path(), "\n".join(lines) + "\n")


# -- The lookup view: RESULTS.md's second table, "Runs by card type", where an agent picking
# cards reads how the same task went on each card model before. --


def _card_type_lines(rows: list[dict]) -> list[str]:
    """The "Runs by card type" table, from every finish row that carries a card record (each
    incarnation of a run has its own): one row per (task identity, card model). The identity is
    the record's `task`, `debug` included, so a debug run and a full-size run of the same task
    are separate rows; a record whose task could not be read is grouped by the `stage` and
    `debug` of the start row it closes, the run's newest start row above it in the ledger (a
    record is written only for a run with an open start row, so that row is always there). A
    run counts in the row of each card model its card-holding pieces ran on. A row
    gives the card's memory, the runs that finished `ok`, the runs a piece of which on that card
    model failed for memory, the memory those pieces used (`_card_type_memory`), the median of
    the runs' speeds, the newest run key, and, when it has a memory failure, the run key and the
    quoted `failure_line` of the newest one. Newest row first, by the ledger's order."""
    groups: dict[tuple[str, str], dict] = {}
    starts: dict[str, dict] = {}
    for order, row in enumerate(rows):
        if row.get("ev") == "start":
            starts[row["run_id"]] = row
        record = row.get("card_record") if row.get("ev") == "finish" else None
        if not record:
            continue
        run_id = row["run_id"]
        start = starts[run_id]
        task = record.get("task")
        if task:
            # The identity is read over today's `CARD_TASK_FIELDS`: a field added after a record
            # was written reads None, so the older record keeps its row.
            task = {**task, **{dotted: None for dotted in CARD_TASK_FIELDS.get(task.get("stage"), ())
                               if dotted not in task}}
        else:
            task = {"stage": start.get("stage"), "debug": bool(start.get("debug"))}
        identity = json.dumps(task, sort_keys=True, default=str)
        by_model: dict[str, list[dict]] = {}
        for piece in record.get("pieces") or []:
            by_model.setdefault(piece.get("card_model") or "-", []).append(piece)
        speed = record.get("speed") or {}
        for model, pieces in by_model.items():
            group = groups.setdefault((identity, model), {
                "task": task, "model": model, "card_gib": set(), "ok": 0, "memory": 0,
                "pieces": [], "per_hour": [], "unit": None, "newest": None,
                "newest_memory_failure": None})
            group["card_gib"].update(p["card_gib"] for p in pieces if p.get("card_gib") is not None)
            group["pieces"].extend(pieces)
            if row.get("status") == "ok":
                group["ok"] += 1
            failed = next((p for p in pieces if p.get("failure") == "memory"), None)
            if failed is not None:
                group["memory"] += 1
                group["newest_memory_failure"] = (run_id, failed.get("failure_line"))
            if speed.get("per_hour") is not None:
                group["per_hour"].append(speed["per_hour"])
                group["unit"] = speed.get("unit")
            group["newest"] = (order, run_id)
    lines = ["", "## Runs by card type", "",
             "> One row per task identity and card model, from the card record on every finish "
             "row of a sample, inject or train run; a run counts under each card model it held. "
             "Newest first.", ""]
    if not groups:
        lines.append("No card records yet.")
        return lines
    lines.append("| stage | task | card | ok | failed for memory | memory | median speed "
                 "| newest run | newest memory failure |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for group in sorted(groups.values(), key=lambda g: g["newest"][0], reverse=True):
        task = group["task"]
        fields = " ".join(f"{k}={v}" for k, v in task.items() if k != "stage") or "-"
        card_gib = "/".join(str(gib) for gib in sorted(group["card_gib"]))
        card = f"{group['model']} {card_gib} GiB" if card_gib else group["model"]
        speed = (f"{round(median(group['per_hour']), 1)} {group['unit']}/h"
                 if group["per_hour"] else "-")
        failure = "-"
        if group["newest_memory_failure"] is not None:
            failed_run, failure_line = group["newest_memory_failure"]
            failure = f"`{failed_run}`"
            if failure_line is not None:
                quoted = failure_line.replace("|", "\\|")
                failure += f' "{quoted}"'
        lines.append("| {} | {} | {} | {} | {} | {} | {} | `{}` | {} |".format(
            task.get("stage", "-"), fields, card, group["ok"], group["memory"],
            _card_type_memory(group["pieces"]), speed, group["newest"][1], failure))
    return lines


def _card_type_memory(pieces: list[dict]) -> str:
    """A "Runs by card type" row's memory, over the pieces of its runs on its card model: the
    largest `peak_gib` of the train pieces and of the probe-service pieces, and the agent-service
    load with the largest weights + KV cache, with that load's maximum concurrency; `-` when no
    piece measured any."""
    parts = []
    train = [p["peak_gib"] for p in pieces
             if p.get("kind") == "train" and p.get("peak_gib") is not None]
    if train:
        parts.append(f"peak {round(max(train), 2)} GiB")
    probe = [p["peak_gib"] for p in pieces
             if p.get("service") == "probe" and p.get("peak_gib") is not None]
    if probe:
        parts.append(f"probe service peak {round(max(probe), 2)} GiB")
    loads = [p for p in pieces if p.get("service") == "agent" and p.get("weights_gib") is not None]
    if loads:
        load = max(loads, key=lambda p: p["weights_gib"] + (p.get("kv_cache_gib") or 0))
        kv_cache = load.get("kv_cache_gib")
        concurrency = load.get("max_concurrency")
        parts.append("weights {} + KV cache {} GiB, concurrency {}x".format(
            load["weights_gib"], "-" if kv_cache is None else kv_cache,
            "-" if concurrency is None else concurrency))
    return "; ".join(parts) or "-"


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
    """`done, not started, dead, suspected stall, warming up, slowed, healthy`,
    in that priority order, for a `loop`, `train` or `cpu` piece.

    A piece is `done` when the heartbeat file of its own incarnation, the one
    the entry's `beat_launch` names (an entry written before that field existed
    reads its newest file), ends with the `status: "done"` row
    `Heartbeat.finish` writes after the piece's last step (8.4),
    and by nothing else. A beat's `done` reaching its `total` is not that
    signal: a train piece's step beats reach the step total before its last
    validation and its prediction pass, and a claiming piece's total is the
    whole request (8.4), so a piece that dies after that beat and before its
    own finish row is `dead`, and `sync` and `launch_failed` can close it.

    A `loop` or `train` piece with no session, no `started` time on its entry
    and no beat of its own incarnation was never started by the launcher (the
    loop wave of an inject launch waits for its services and the check client;
    a launch that ended before that wave never starts it), so it is
    `not started`: not escalated while the launch is younger than
    `launch_timeout_s`, the longest the launcher waits before its last wave,
    and escalated past that, when the launcher that would have started it is
    gone (a launch killed between its service wave and its loop wave leaves
    the services alive and holding cards, and only this mark says so).
    `launch_failed` closes a launch whose pieces all read `dead` or
    `not started` once the start row is that old. Either mark of a start, the
    launcher's stamp or a beat the piece wrote itself, makes a session-less
    piece `dead`. A `cpu` piece is started by the walk that records its pid, so
    it never reads `not started`.

    A newest beat that names a phase (`Heartbeat.touch`: a train piece's
    validation or prediction pass) moves no count by design, so the piece is
    not `slowed` on it; its age is still read against the stall line."""
    if piece.get("status") == "done":
        return "done", False
    if piece.get("alive") is False:
        if piece.get("kind") != "cpu" and not piece.get("started") and not piece.get("has_beat"):
            return "not started", piece["since_launch_s"] > DEFAULTS["launch_timeout_s"]
        return "dead", True
    warm = not piece.get("has_beat")
    age = piece["since_launch_s"] if warm else piece["beat_age_s"]
    line = float(DEFAULTS["warmup_s"]) if warm else stall_line_s(piece.get("beat_ts") or [])
    if age > line:
        esc_line = line * DEFAULTS["escalate_line"]
        return "suspected stall", age > esc_line
    if warm:
        return "warming up", False
    if piece.get("phase"):
        return "healthy", False
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


def incarnation_dead(verdicts: list[str]) -> bool:
    """Whether an open launch has pieces and every one of them reads `dead` or `not started`,
    so no process of this launch is left to write its own finish row. `launch_failed` adds the
    age condition for the readers that come upon such a launch; `close_dead_incarnation` applies
    this rule alone, because a relaunch is replacing the launch now."""
    return bool(verdicts) and all(v in ("dead", "not started") for v in verdicts)


def launch_failed(started_at: str, verdicts: list[str]) -> bool:
    """Whether an open launch never came up (8.1): every one of its pieces reads `dead` or
    `not started` (`incarnation_dead`), and its start row is older than
    `DEFAULTS["launch_timeout_s"]` (8.5).

    One rule, one word, every reader. `run.py ls` writes the `launch_failed`
    finish row for each run this selects (8.1, 8.2) and `sync` writes it for a
    run it reaches first, so the ledger, `RESULTS.md` and the `ls` line carry
    the same word for the same state instead of each naming it their own way."""
    return incarnation_dead(verdicts) and _age_s(started_at) > DEFAULTS["launch_timeout_s"]


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
    # A phase-named beat (`Heartbeat.touch`) refreshes the age only: the typical gap, the
    # stall line and the rates are read over the counting beats, so a pass that touches every
    # few seconds neither drops the stall line to its floor nor reads as a zero rate afterwards.
    counting = [b for b in beats if not b.get("phase")]
    beat_ts = [b.get("ts") for b in counting]
    # The rates are read over the counting beats in the newest counting beat's unit: a train
    # piece counts steps and then prediction splits from 0 (`train/utils/trainer.py`), so each
    # phase has a rate of its own, and the prediction phase has one from its second beat on.
    unit_now = counting[-1].get("unit") if counting else None
    phase_counting = [b for b in counting if b.get("unit") == unit_now]
    recent_slice = phase_counting[-DEFAULTS["typical_beats"]:]
    avg_rate, recent_rate = rates(phase_counting[0] if phase_counting else None, recent_slice)
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
        "beat_age_s": (now_ts - last["ts"]) if has_beat else None,
        "since_launch_s": since_launch_s,
        "port_ok": None,
        "avg_rate": avg_rate,
        "recent_rate": recent_rate,
        # The pass the newest beat names (`Heartbeat.touch`), None for a counting beat.
        "phase": last.get("phase") if last else None,
        # The time the launcher started this piece's session (`jobs/launch.py`), absent for
        # a piece whose session was never started: a later wave of its launch, or a launch
        # that ended before its wave.
        "started": piece.get("started"),
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
            "unjudged": None,
            "consumed": False,
            "split": False,
            "pinned": False,
            "dirty": False,
            "debug": False,
            "orphan": True,
        },
    }


def _ls_row(entry: dict, sessions: set, edited: dict, progress: dict,
            unjudged: dict, consumed: dict, split: dict, pinned: dict) -> dict:
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
            "unjudged": unjudged.get(run_id),
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
       unjudged: dict[str, bool] | None = None,
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

    `edited`, `unjudged`, `consumed`, `split` and `pinned` are the five flags of
    8.6 that `run.py` computes and passes in, for the reason `edited` names:
    this file imports nothing from the repo, so it can call neither `key` nor
    the code gate nor a settings reader, and it hashes no upstream file.
    Given None, ls leaves that flag blank."""
    edited = edited or {}
    progress = progress or {}
    unjudged = unjudged or {}
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
    rows = [_ls_row(e, sessions, edited, progress, unjudged, consumed, split, pinned)
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


def close_dead_incarnation(run_id: str, sessions: set) -> bool:
    """Append the `launch_failed` finish row of `run_id`'s open incarnation when every one of its
    pieces reads `dead` or `not started` under `sessions` (`incarnation_dead`); True when it
    appended the row.

    `jobs/launch.launch` (a walk or a `retry`) and `jobs/launch.refire` call this inside the lock
    hold that appends their start row, right before that append. A start row clears the run's
    finish (`fold`), so the incarnation it replaces is closed here first, with the row and the
    card record (`append_finish`) that incarnation owes. The rule is the one `ls` and `sync`
    close a run by (`launch_failed`) without the age condition, because a person is relaunching
    the run now. A run with no open start row has no incarnation to close, and a run with a
    piece of any other verdict (`done`, `healthy`, `warming up`, ...) keeps its incarnation
    open: a refire restarts one piece beside such siblings."""
    with lock():
        entry = fold(_read_rows()).get(run_id)
        if entry is None or entry["start"] is None or entry["finish"] is not None:
            return False
        start = entry["start"]
        run_dir = Path(start["dir"])
        verdicts = [verdict for _pv, verdict, _esc
                    in _judge_pieces(_pieces_of(run_dir, start), run_dir, sessions, start["t"])]
        if not incarnation_dead(verdicts):
            return False
        append_finish(run_id, {
            "ev": "finish", "t": _now(), "run_id": run_id, "status": "launch_failed",
            "counts": {}, "metrics": {}, "report": None, "elapsed_s": _age_s(start["t"]),
        })
        return True


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
