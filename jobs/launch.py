"""Launch and refire the tmux pieces of a sample, inject or train run: the dirty-tree gate, the launch gate, card placement, port assignment, the piece and service commands, and teardown.

# venv: probe

A library with no entry-point guard: `run.py` is the one command that calls
it (contracts 0.2, 8.6), and a loop piece (`agent/run_tasks.py`) calls
`teardown_services` alone, to free its run's cards once every requested record
is finished. Ported against contracts Part 2.3, 2.5, 3.4, 7.4 and
Part 8, with the wave-4 precheck's two corrections (B3/B7 use their own
temporary directory; `teardown_services` reaches a host that normalises to
`login_host` locally, with no `ssh`).
"""
from __future__ import annotations

import hashlib
import json
import re
import shlex
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

from data import trajectory_record
from data.environments import open_env, requested_pairs
from experimental_settings import schema
from jobs import registry

PROBE_PORT_BASE = 8500

# ---------------------------------------------------------------------------
# Config readers: lazy and cached, like jobs/registry.py's own, so importing
# this module needs neither constants/ nor models/table.yaml to exist yet.
# ---------------------------------------------------------------------------

_DATASETS_CFG: dict | None = None
_OUTPUTS_CFG: dict | None = None
_TABLE_CFG: dict | None = None


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _read_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def _datasets_config() -> dict:
    global _DATASETS_CFG
    if _DATASETS_CFG is None:
        _DATASETS_CFG = _read_yaml(_repo_root() / "constants" / "path_datasets.yaml")
    return _DATASETS_CFG


def _outputs_config() -> dict:
    global _OUTPUTS_CFG
    if _OUTPUTS_CFG is None:
        _OUTPUTS_CFG = _read_yaml(_repo_root() / "constants" / "path_outputs.yaml")
    return _OUTPUTS_CFG


def _table_config() -> dict:
    global _TABLE_CFG
    if _TABLE_CFG is None:
        _TABLE_CFG = _read_yaml(_repo_root() / "models" / "table.yaml")
    return _TABLE_CFG


def _login_host() -> str:
    return _outputs_config()["login_host"]


def _canonical_host(raw: str) -> str:
    """Normalise a host name or alias to the `hosts:` entry's `name`, so this
    machine's own `hostname` and its cluster alias compare equal (errata,
    3.4: this machine answers `shiga` to `hostname` while `hosts:` calls it
    `tokyo105`)."""
    for host in _outputs_config().get("hosts", []):
        if raw == host.get("name") or raw == host.get("alias"):
            return host["name"]
    return raw


def _this_host() -> str:
    """The machine this launch runs on, under the `hosts:` entry's own name."""
    return _canonical_host(socket.gethostname())


def _is_local_host(host: str) -> bool:
    return _canonical_host(host) == _this_host()


def _interpreter_for(venv_name: str) -> str:
    """The absolute interpreter path for a key of `constants/path_datasets.yaml`'s `venvs:` map."""
    venvs = _datasets_config().get("venvs", {})
    if venv_name not in venvs:
        sys.exit(f"jobs/launch.py: no interpreter for venv {venv_name!r} in constants/path_datasets.yaml")
    return venvs[venv_name]


def _resolve_venv(v, env_name: str | None) -> str:
    """`"env"` -> this setting's `data.env` row's `venv:` column; `"any"` -> `venvs.probe`; anything else, itself (2.1, 6.3)."""
    if v == "env":
        return _datasets_config()[env_name]["venv"]
    if v == "any":
        return "probe"
    return v


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _parse_row_t(t: str) -> float:
    return datetime.strptime(t, "%Y-%m-%d %H:%M").timestamp()


def _read_json(path: Path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------------------
# 2.5: the dirty-tree gate and the ledger exemption.
# ---------------------------------------------------------------------------


def is_ledger_path(path) -> bool:
    """The ledger exemption of 2.5, as a pure test over one path string: true
    for `jobs/runs.jsonl`, `jobs/RESULTS.md` and anything ending `.lock`,
    false for everything else."""
    p = str(path)
    return p in ("jobs/runs.jsonl", "jobs/RESULTS.md") or p.endswith(".lock")


def git_state(run_dir, allow_dirty: bool) -> dict:
    """The dirty-tree gate and the git fields of a start row, in one function
    (2.5). Refuses a dirty tree without `allow_dirty`, naming the files;
    writes `<run_dir>/dirty.patch` (`git diff HEAD`) when the tree is dirty
    and the refusal did not fire; fail-closed: a failed git probe counts as
    dirty. `jobs/runs.jsonl`, `jobs/RESULTS.md` and `*.lock` never count as
    dirty."""
    run_dir = Path(run_dir)
    repo_root = _repo_root()

    def _git(*args: str) -> str:
        r = subprocess.run(["git", "-C", str(repo_root), *args],
                            capture_output=True, text=True, timeout=20)
        if r.returncode != 0:
            raise RuntimeError((r.stderr or r.stdout or f"git rc={r.returncode}").strip())
        return r.stdout

    probe_failed = False
    try:
        status = _git("status", "--porcelain")
        dirty_files = sorted({
            line[3:] for line in status.splitlines()
            if line.strip() and not is_ledger_path(line[3:])
        })
        commit = _git("rev-parse", "--short", "HEAD").strip()
        branch = _git("rev-parse", "--abbrev-ref", "HEAD").strip()
        dirty = bool(dirty_files)
    except Exception:
        commit, branch, dirty, dirty_files, probe_failed = "", "", True, [], True

    if dirty and not allow_dirty:
        detail = ", ".join(dirty_files) if dirty_files else "git probe failed"
        sys.exit(f"jobs/launch.py: refusing a dirty working tree without --allow-dirty: {detail}")

    if dirty:
        run_dir.mkdir(parents=True, exist_ok=True)
        try:
            patch = "" if probe_failed else _git("diff", "HEAD")
            (run_dir / "dirty.patch").write_text(patch)
        except Exception:
            pass

    return {
        "commit": commit,
        "branch": branch,
        "dirty": dirty,
        "dirty_count": len(dirty_files),
        "dirty_files": dirty_files,
    }


# ---------------------------------------------------------------------------
# 2.5 / 8.5: the launch gate, as a pure decision over registry rows.
# ---------------------------------------------------------------------------


def _pieces_of_row(run_id: str, row: dict, meta_by_run: dict) -> list[dict]:
    meta = meta_by_run.get(run_id) or {}
    return meta.get("pieces") or row.get("pieces") or []


def piece_alive(piece: dict, live_sessions) -> bool:
    """A piece is alive when its session is a live one, or — fail-closed,
    3.4/8.0, `jobs/registry._alive_on`'s own rule — when its host's probe
    never answered at all: `registry.live_sessions()` then names that host
    in the returned set's `failed_hosts`, the canonical `hosts:` name (the
    same normalisation `_canonical_host` gives every other host comparison
    in this file). A plain set (no `failed_hosts` attribute) has no failed
    hosts, so a bare-membership caller sees no change. Public: `run.py`'s
    own partial-piece check (2.3/2.4) calls this directly rather than
    keeping a second copy.

    A `cpu` piece runs in no session: it is alive when its recorded pid is
    running on the host its entry names (`registry.pid_alive`), which is the
    test `run.py ls` judges it by."""
    if piece.get("kind") == "cpu":
        return registry.pid_alive(piece.get("host"), piece.get("pid"))
    host, session = piece.get("host"), piece.get("session")
    if not host or not session:
        return False
    failed_hosts = getattr(live_sessions, "failed_hosts", None)
    if failed_hosts and _canonical_host(host) in failed_hosts:
        return True
    return session in live_sessions


def gate_open_row(open_rows, meta_by_run, live_sessions, now_ts, beats=None) -> str | None:
    """The launch gate of 2.5: refuse a key whose newest start row (`open_rows`,
    already scoped to that key) has no finish row and any of three things
    holds, counting only pieces whose `kind` is not `service`:
    (a) a live session; (b) a heartbeat younger than the stall line;
    (c) a start row younger than `registry.DEFAULTS["launch_timeout_s"]`,
    holding only while no piece of the row has been *observed dead* — not
    alive and has emitted at least one heartbeat beat (a `cpu` piece: has a
    recorded pid). Returns the refusal message, or `None`."""
    beats = beats or {}
    for row in open_rows:
        run_id = row["run_id"]
        pieces = [p for p in _pieces_of_row(run_id, row, meta_by_run) if p.get("kind") != "service"]
        row_beats = beats.get(run_id) or {}

        for piece in pieces:
            if piece_alive(piece, live_sessions):
                if piece.get("kind") == "cpu":
                    return (f"refusing to launch {row.get('key')!r}: live process "
                            f"{piece.get('pid')!r} on host {piece.get('host')!r}")
                return (f"refusing to launch {row.get('key')!r}: live session "
                        f"{piece.get('session')!r} on host {piece.get('host')!r}")

        for piece in pieces:
            ts_list = row_beats.get(piece.get("index")) or []
            if not ts_list:
                continue
            age = now_ts - max(ts_list)
            if age < registry.stall_line_s(ts_list):
                return (f"refusing to launch {row.get('key')!r}: piece {piece.get('index')} "
                        f"has a fresh heartbeat ({age:.0f}s old)")

        age_s = now_ts - _parse_row_t(row["t"])
        if age_s < registry.DEFAULTS["launch_timeout_s"]:
            observed_dead = False
            for piece in pieces:
                alive = piece_alive(piece, live_sessions)
                if piece.get("kind") == "cpu":
                    has_emitted = piece.get("pid") is not None
                else:
                    has_emitted = bool(row_beats.get(piece.get("index")))
                if not alive and has_emitted:
                    observed_dead = True
                    break
            if not observed_dead:
                return (f"refusing to launch: run_id {run_id!r} started {age_s:.0f}s ago, "
                        f"within launch_timeout_s")
    return None


# ---------------------------------------------------------------------------
# 3.4: placement, and the piece command.
# ---------------------------------------------------------------------------


def parse_cards(tokens: list[str]) -> dict[str, list[int]]:
    """`--cards`' values, `<host>:<id>,<id>,...` each, as host -> card ids in the order given;
    a host is stored under its `hosts:` entry's own name, and a host named twice keeps both lists."""
    pool: dict[str, list[int]] = {}
    for tok in tokens:
        host, sep, ids = tok.partition(":")
        if not (host and sep and ids and all(i.strip().isdigit() for i in ids.split(","))):
            sys.exit(f"jobs/launch.py: --cards {tok!r} is not <host>:<id>,<id>,...")
        cards = pool.setdefault(_canonical_host(host), [])
        for i in ids.split(","):
            if int(i) not in cards:
                cards.append(int(i))
    return pool


def restrict_to_pool(free_by_host: dict, pool: dict[str, list[int]] | None) -> dict:
    """The cards a launch may claim: every free card when no pool is named, the pool when one
    is. A pool is the caller's statement of where this launch runs, so a pool card that is not
    free refuses the launch, naming the card, rather than moving the launch to another card."""
    if pool is None:
        return free_by_host
    busy = [f"{host}:{i}" for host, ids in pool.items()
            for i in ids if i not in (free_by_host.get(host) or [])]
    if busy:
        sys.exit(f"jobs/launch.py: --cards names card(s) that are not free: {', '.join(busy)}")
    return {host: list(ids) for host, ids in pool.items()}


def remove_claimed(pool: dict[str, list[int]], pieces: list[dict]) -> None:
    """Take the cards these placed pieces hold out of the pool, in place."""
    for piece in pieces:
        held = [int(g) for g in str(piece.get("gpus") or "").split(",") if g.strip() != ""]
        host = piece.get("host")
        if host in pool:
            pool[host] = [i for i in pool[host] if i not in held]


def place(kind, cards_needed, free_by_host, *, serving_host, prefer_host, attached) -> str | None:
    """Which host a piece lands on (3.4). `loop` and a `service_probe` with
    no card go to `login_host`; an `attached` agent service goes to
    `serving_host`, the host of the live server it attaches to, taking no card
    and no card search; everything else (an agent service that starts its own
    server, a checkpoint-loading `service_probe`, `train`) takes the first host
    with `cards_needed` free, preferring `prefer_host`. `None` when no host
    qualifies."""
    if kind == "loop":
        return _login_host()
    if kind == "service_probe" and cards_needed == 0:
        return _login_host()
    # An attached agent service takes no card and no card search: it lands on the host of the
    # live server it attaches to. One that starts its own server falls through to the card
    # search below, where its table row's serving host reaches it as `prefer_host`, so a full
    # serving host moves that server to a free machine instead of ending the launch.
    # TODO(gyb, 2026-09-22): the fallback knows how many cards are free and nothing about their
    # size, so with tokyo108 full the gpt_oss_120b server lands on a 48 GB card, claims it, and
    # fails its alive check one launch timeout later, where the launch used to refuse at once.
    # Needs the owner's files: a minimum card memory in the row's `serving:` block of the model
    # table and a per-host card memory in constants/path_outputs.yaml (a comment there today);
    # place() then keeps the hosts whose cards are large enough. Contracts 3.4 (first bullet)
    # and 7.4 (first paragraph) still state "the serving host and nowhere else".
    if kind == "service_agent" and attached:
        return serving_host
    candidates = []
    if prefer_host is not None and prefer_host in free_by_host:
        candidates.append(prefer_host)
    for host in free_by_host:
        if host not in candidates:
            candidates.append(host)
    for host in candidates:
        if len(free_by_host.get(host, [])) >= cards_needed:
            return host
    return None


def assign_ports(kind, replica, serving_port, taken) -> int:
    """The port for one service piece (7.4): an agent replica starts at
    `serving_port + replica`; a probe service starts at `PROBE_PORT_BASE`.
    Either moves to the next free integer not in `taken`."""
    port = PROBE_PORT_BASE if kind == "service_probe" else serving_port + replica
    while port in taken:
        port += 1
    return port


def piece_command(python, module, run_dir, piece, n, gpus, log) -> str:
    """The tmux inner command for a `loop`, `train` or `cpu`-shaped piece
    (3.4, errata): `cd <repo root> && CUDA_VISIBLE_DEVICES=<ids> <python>
    -m <module> --run-dir <dir> [--piece <i>/<n>] 2>&1 | tee -a <log>`.
    `--piece` is present only when `piece` is not `None` (a `sample` or
    `inject` loop piece)."""
    cmd = f"cd {_repo_root()} && CUDA_VISIBLE_DEVICES={gpus} {python} -m {module} --run-dir {run_dir}"
    if piece is not None:
        cmd += f" --piece {piece}/{n}"
    cmd += f" 2>&1 | tee -a {log}"
    return cmd


def _agent_service_cmd(python, run_dir, model_alias, host, port, gpus, replica, *,
                        attach_only, attached_to, log) -> str:
    """7.1's serve line, plus the `--replica` and `--attached-to` flags of
    errata 7.1/1.5, plus `--host`: the launcher places the service, so the
    launcher tells it which host its endpoint file names. `--gpus` is unbracketed on every serve line (7.1), so it
    is always present; its value is shell-quoted (`shlex.quote`) so a
    card-less, attached replica's empty value survives tmux's shell as a
    real, empty token — `--gpus ''` — instead of vanishing under ordinary
    word-splitting and shifting every flag after it onto the previous
    flag's place."""
    parts = [python, "-m", "models.agent_models.service", "serve",
              "--run-dir", str(run_dir), "--model", model_alias,
              "--host", str(host), "--port", str(port), "--gpus", shlex.quote(gpus)]
    parts += ["--replica", str(replica)]
    if attach_only:
        parts += ["--attach-only", "--attached-to", attached_to]
    return f"cd {_repo_root()} && {' '.join(parts)} 2>&1 | tee -a {log}"


def _probe_service_cmd(python, run_dir, agent_alias, port, *, score_ckpt, gen_ckpt,
                        temperature, device, render_only, log) -> str:
    """7.2's serve line: the four checkpoint/device flags are absent under `--render-only`."""
    parts = [python, "-m", "models.probe_models.service", "serve",
              "--run-dir", str(run_dir), "--agent-model", agent_alias, "--port", str(port)]
    if render_only:
        parts += ["--render-only"]
    else:
        parts += ["--score-ckpt", str(score_ckpt), "--gen-ckpt", str(gen_ckpt),
                  "--temperature", str(temperature)]
        if device:
            parts += ["--device", device]
    return f"cd {_repo_root()} && {' '.join(parts)} 2>&1 | tee -a {log}"


# ---------------------------------------------------------------------------
# Host execution: local when a host normalises to login_host, ssh otherwise
# (errata, 3.4/8.0). jobs/launch.py's own copy, used to start and end tmux
# sessions; registry.py's copy (private) serves its own callers.
# ---------------------------------------------------------------------------


def _remote_run(host: str, script: str, timeout: float = 20.0) -> tuple[bool, str]:
    if _is_local_host(host):
        argv = ["bash", "-c", script]
    else:
        argv = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", host, script]
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except Exception:
        return False, ""
    return r.returncode == 0, r.stdout


def _start_tmux(host: str, session: str, inner_cmd: str) -> bool:
    script = f"tmux new-session -d -s {shlex.quote(session)} {shlex.quote(inner_cmd)}"
    ok, _out = _remote_run(host, script)
    return ok


def _start_wave(pieces) -> bool:
    """Start one wave's tmux sessions; True when every session of the wave
    started. `tmux new-session` fails when the host is unreachable and when a
    session of that name is already there — the session name is a pure
    function of the run id and the piece index (8.1), so a relaunch into a
    directory whose earlier piece is still running hits its own name. Both
    mean this launch has no process of its own for that piece, so it says so
    and the caller ends the launch, rather than passing an alive check against
    somebody else's session."""
    started = True
    for p in pieces:
        if not _start_tmux(p["host"], p["session"], p["cmd"]):
            print(f"jobs/launch.py: piece {p['index']}: tmux new-session failed for session "
                  f"{p['session']!r} on host {p['host']!r}", file=sys.stderr)
            started = False
    return started


def _kill_tmux(host: str, session: str) -> bool:
    script = f"tmux kill-session -t {shlex.quote(session)}"
    ok, _out = _remote_run(host, script)
    return ok


def _port_answers(host: str | None, port) -> bool:
    if not host or not port:
        return False
    target = "127.0.0.1" if _is_local_host(host) else host
    try:
        with socket.create_connection((target, int(port)), timeout=2):
            return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# 8.1: the alive check (errata; 8.1 names it and never defines it).
# ---------------------------------------------------------------------------

# How long a piece whose session has ended keeps its waiting state before the
# check calls it down. The evidence a piece leaves is a file in the run
# directory, which is on the NFS outputs mount with the default attribute
# cache, so this host can answer a lookup from cache for tens of seconds after
# the serving host wrote the file, while the session probe (`tmux ls` over ssh)
# is always live. The grace is the window in which the two facts disagree.
SESSION_END_GRACE_S = 60


def _newest_beat_launch(run_dir, index: int) -> int:
    """The largest `<launch>` among this piece's `heartbeat/<index>-<launch>.jsonl`
    files, -1 when it has none: the same numbering `registry.beat` hands the
    next incarnation (8.4)."""
    hb_dir = Path(run_dir) / "heartbeat"
    prefix = f"{index}-"
    best = -1
    if not hb_dir.is_dir():
        return best
    for path in hb_dir.iterdir():
        name = path.name
        if name.startswith(prefix) and name.endswith(".jsonl"):
            n_str = name[len(prefix):-len(".jsonl")]
            if n_str.isdigit():
                best = max(best, int(n_str))
    return best


def incarnation_origin(run_dir, pieces) -> dict[int, dict]:
    """One rule over every kind of piece: what a piece inherits from an earlier
    incarnation is snapshotted or cleared here, before the first
    `tmux new-session`, because everything a piece writes after that is its
    own. That is what lets `alive_check` read this incarnation's output and no
    earlier one's (errata, section-4 walks: an old `Traceback` in the reused
    log closed every relaunch at its first poll).

    A `loop`, `train` or `cpu` piece appends to a log the run directory already
    holds (`tee -a`, 3.4) and numbers its heartbeat files from the ones already
    there, so its origin is a snapshot: the returned
    `{piece index: {"log_size", "beat_launch"}}` is what its `log/<index>.txt`
    and its `heartbeat/` listing held before this launch started it. A
    `service` piece leaves one file instead of a growing log and nothing else
    deletes it, so its origin is made by clearing: the endpoint file this
    launch's server is about to write (7.4) is removed, and the existence test
    in `alive_check` and in `agent/run_tasks._wait_for_endpoints` then reads
    this incarnation's own server. Only the pieces this launch places are
    touched, so a piece of this run that this launch does not start keeps its
    file."""
    run_dir = Path(run_dir)
    origin: dict[int, dict] = {}
    for p in pieces:
        if p.get("kind") == "service":
            (run_dir / p["endpoint_file"]).unlink(missing_ok=True)
            continue
        log = Path(p.get("log", ""))
        origin[p["index"]] = {
            "log_size": log.stat().st_size if log.exists() else 0,
            "beat_launch": _newest_beat_launch(run_dir, p["index"]),
        }
    return origin


def _log_shows_traceback(log: Path, first_byte: int) -> bool:
    """Whether this incarnation's own output carries a `Traceback`: the last
    4 KB of `log`, reaching no further back than `first_byte`, where this
    launch's output starts."""
    try:
        size = log.stat().st_size
        with open(log, "rb") as f:
            f.seek(max(first_byte, size - 4096))
            return b"Traceback" in f.read()
    except OSError:
        return False


def _last_beat_status(path: Path) -> str | None:
    """The `status` of the last row of one heartbeat file (`None` when its last
    row carries none): `registry.Heartbeat.finish` writes `"done"` and an
    ordinary beat writes no status at all (8.4)."""
    status = None
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    status = json.loads(line).get("status")
                except json.JSONDecodeError:
                    continue
    except OSError:
        return None
    return status


def _piece_finished(run_dir, index: int, beat_launch: int) -> bool:
    """Whether this incarnation of a `loop`, `train` or `cpu` piece walked its
    whole share: the newest heartbeat file opened after `beat_launch` (the
    launch number `incarnation_origin` found) ends with the `status: "done"`
    row `registry.Heartbeat.finish` writes. `agent/run_tasks.py` writes it when
    its rotation is walked out and `train/utils/trainer.py` after `done.json`,
    so a piece whose session has ended with that row on disk did its work; a
    piece killed mid-share leaves no such row."""
    newest = _newest_beat_launch(run_dir, index)
    if newest <= beat_launch:
        return False
    return _last_beat_status(Path(run_dir) / "heartbeat" / f"{index}-{newest}.jsonl") == "done"


def alive_check(pieces, origin, window_s=None, poll_s=5) -> tuple[bool, list]:
    """`(all_up, pending_pieces)`, polled every `poll_s` for at most `window_s`
    (default `registry.DEFAULTS["launch_timeout_s"]`; errata: 8.1 names the
    alive check and never defines it). `origin` is `incarnation_origin`'s map,
    taken before the sessions started; that call is what makes every test below
    read this incarnation's own output — the map for a work piece's log and
    heartbeat, and the endpoint file it cleared for a service piece.

    One rule over every kind of piece. A piece is **up** while it shows the
    evidence of its kind: a `loop`, `train` or `cpu` piece that holds its
    session and has grown its log since this launch started it, or whose
    heartbeat says it walked its whole share; a `service` piece whose endpoint
    file is there and whose port answers. The session belongs in that first
    conjunct because a grown log is a fact about the past and stays true at
    every later poll, while the session says the process runs now: a piece
    killed without a traceback -- the OOM killer, `kill -9`, a CUDA abort --
    keeps its grown log, loses its session and writes no finish row, and the
    grace window below is what ends it. A piece is **down** the moment this
    incarnation's log carries a `Traceback`, and otherwise once its session
    has ended and it still owes that evidence `SESSION_END_GRACE_S` later.
    Every other piece is **waiting**: a live session that has written nothing
    yet, which is what a cold interpreter start over NFS looks like for the
    better part of a minute, and the grace window, in which this host's
    directory cache can still be hiding the file a piece wrote just before it
    exited.

    The grace window and the finish row are what keep the two pieces whose
    ended session is their success state out of the down state: an
    `--attach-only` agent service, which writes its endpoint file and returns
    (7.4), and a loop piece that finds every record of its rotation already
    claimed and exits seconds after its first beat (2.3). A piece that dies
    without ever producing its evidence is still down, one grace period into
    a `launch_timeout_s` window.

    Returns as soon as every piece is up (`True`), as soon as one is down, or
    at the deadline (`False`, with the pieces that are not up)."""
    pieces = list(pieces)
    if not pieces:
        return True, []
    if window_s is None:
        window_s = registry.DEFAULTS["launch_timeout_s"]

    session_ended_at: dict[int, float] = {}
    deadline = time.time() + window_s
    while True:
        sessions = registry.live_sessions()
        now = time.time()
        pending: list = []      # every piece that is waiting or down
        any_down = False
        for p in pieces:
            index = p["index"]
            session_ok = piece_alive(p, sessions)
            if p.get("kind") == "service":
                run_dir = p.get("run_dir")
                endpoint_ok = bool(run_dir) and (Path(run_dir) / p["endpoint_file"]).exists()
                working = endpoint_ok and _port_answers(p.get("host"), p.get("port"))
                finished = False
                crashed = False
            else:
                log = Path(p.get("log", ""))
                started_from = origin[index]
                log_grew = log.exists() and log.stat().st_size > started_from["log_size"]
                working = session_ok and log_grew
                finished = _piece_finished(p.get("run_dir", ""), index,
                                           started_from["beat_launch"])
                crashed = _log_shows_traceback(log, started_from["log_size"])
            up = (working or finished) and not crashed
            if crashed:
                down = True
            elif up or session_ok:
                session_ended_at.pop(index, None)
                down = False
            else:
                ended_at = session_ended_at.setdefault(index, now)
                down = now - ended_at >= SESSION_END_GRACE_S
            if not up:
                pending.append(p)
            any_down = any_down or down
        all_up = len(pending) == 0
        if all_up or any_down or time.time() >= deadline:
            return all_up, pending
        time.sleep(poll_s)


# ---------------------------------------------------------------------------
# 2.3: ending the service pieces.
# ---------------------------------------------------------------------------


def _run_id_of_meta(meta: dict) -> str | None:
    stage, key = meta.get("stage"), meta.get("key")
    return f"{stage}-{key}" if stage and key else None


def _attached_elsewhere(run_id: str) -> bool:
    """Whether another live run's `service_*.json` names `run_id` in its
    `attached_to` field (the test `run.py kill` also uses, 8.6)."""
    for row in registry.open_runs():
        if row.get("run_id") == run_id:
            continue
        run_dir = Path(row.get("dir", ""))
        if not run_dir.is_dir():
            continue
        for path in run_dir.glob("service_*.json"):
            doc = _read_json(path)
            if doc and doc.get("attached_to") == run_id:
                return True
    return False


def teardown_services(run_dir) -> list[str]:
    """End every `kind: service` piece of this run (`ssh <host> tmux
    kill-session -t <session>`, local with no `ssh` when the host
    normalises to `login_host`, errata wave-4 precheck), skipped whole when
    this run's own `run_id` appears in another live run's `attached_to`
    (2.3). Returns the sessions actually ended."""
    run_dir = Path(run_dir)
    meta = _read_json(run_dir / "meta.json") or {}
    run_id = _run_id_of_meta(meta)
    if run_id and _attached_elsewhere(run_id):
        return []
    ended = []
    for piece in meta.get("pieces") or []:
        if piece.get("kind") != "service":
            continue
        host, session = piece.get("host"), piece.get("session")
        if not host or not session:
            continue
        if _kill_tmux(host, session):
            ended.append(session)
    return ended


def teardown_launch(run_dir, pieces) -> list[str]:
    """End every session this launch started (8.1): the `service` pieces
    through `teardown_services`, which keeps its own `attached_to` skip rule
    (2.3), and this launch's `loop` and `train` pieces by `ssh <host> tmux
    kill-session`. This is what `launch()` calls before it returns any outcome
    but `up`, so a run that a `launch_failed` finish row closes (8.2) has
    nothing of its own left running: a work piece holds a card, writes into the
    run directory and claims records exactly as a service piece holds a card,
    and the closed row makes every gate stop refusing a second launch into the
    same directory. `teardown_services` keeps its own meaning for the finished
    pair stage of 2.3, where the loop pieces have already exited. Returns the
    sessions actually ended."""
    ended = teardown_services(run_dir)
    for piece in pieces:
        if piece.get("kind") == "service":
            continue
        host, session = piece.get("host"), piece.get("session")
        if not host or not session:
            continue
        if _kill_tmux(host, session):
            ended.append(session)
    return ended


# ---------------------------------------------------------------------------
# 8.3: meta.json.split_files.
# ---------------------------------------------------------------------------


def _resolve_split_files(stage: str, setting) -> list[dict]:
    """One entry per split file the stage's request touches: path, sha1 and
    the resolved (tasks-filtered, n_tasks-capped) task-id list, through
    `env.tasks(split)` and `requested_pairs` (2.3, 8.3). Refuses a `tasks`
    id that is in none of the splits, naming the id and the split files."""
    section = setting.inject if stage == "inject" else setting.sample
    env_name = setting.data.env
    env = open_env(env_name)
    splits_map = _datasets_config()[env_name]["splits"]

    triples = requested_pairs(env, section.split, section.tasks, section.n_tasks, section.seeds)
    by_split: dict[str, list[str]] = {}
    for split, task_id, _seed in triples:
        ids = by_split.setdefault(split, [])
        if task_id not in ids:
            ids.append(task_id)

    if section.tasks is not None:
        wanted = set(section.tasks)
        covered: set[str] = set()
        for split in section.split:
            covered.update(env.tasks(split))
        missing = sorted(wanted - covered)
        if missing:
            paths = [str(splits_map[s]) for s in section.split]
            sys.exit(f"jobs/launch.py: tasks id(s) {missing} are in none of the split files {paths}")

    out = []
    for split in section.split:
        path = Path(splits_map[split])
        sha1 = hashlib.sha1(path.read_bytes()).hexdigest()
        out.append({"path": str(path), "sha1": sha1, "task_ids": by_split.get(split, [])})
    return out


# ---------------------------------------------------------------------------
# Card and port bookkeeping shared by launch() and refire().
# ---------------------------------------------------------------------------


def _claim_cards(free_by_host: dict, host: str, n: int) -> list[int]:
    ids = free_by_host.get(host) or []
    if len(ids) < n:
        sys.exit(f"jobs/launch.py: host {host!r} has only {len(ids)} free card(s), need {n}")
    claimed, free_by_host[host] = ids[:n], ids[n:]
    return claimed


def _no_cards_message(free_by_host: dict, needed: int) -> str:
    probed = ", ".join(f"{h}:{len(ids)} free" for h, ids in free_by_host.items())
    return f"jobs/launch.py: no host has {needed} free card(s); probed {probed}"


def _taken_service_ports(host: str) -> set[int]:
    taken: set[int] = set()
    for row in registry.open_runs():
        meta = _read_json(Path(row.get("dir", "")) / "meta.json") or {}
        for piece in meta.get("pieces") or row.get("pieces") or []:
            if piece.get("kind") == "service" and piece.get("host") == host and piece.get("port"):
                taken.add(int(piece["port"]))
    return taken


def _next_free_port(kind: str, replica: int, serving_port, host: str) -> int:
    taken = _taken_service_ports(host)
    port = assign_ports(kind, replica, serving_port, taken)
    while _port_answers(host, port):
        taken.add(port)
        port = assign_ports(kind, replica, serving_port, taken)
    return port


def _find_attach_target(agent_row: dict, hosts=None):
    """7.4's attach search: a live registry row with a `service_agent_*.json`
    whose `claims` match this run's frozen `result:` block (plus `role`/`family`)
    value for value, and whose server is answering now. `hosts` is the set of hosts
    the server may be on: `None` for every host, and the pool's hosts when the launch
    names a pool, because a named pool is where that launch runs, its agent service
    included. Within that, the search reaches every host: the endpoint document carries the host its server was placed on (7.1
    writes the `--host` the launcher handed it), so the match itself names the
    host this run's attached piece goes to, and a server that `place` moved off
    its table row's serving host is found where it actually runs.

    Answering now is part of the test because an endpoint file outlives its
    server: nothing deletes it, and a run is open from its start row on (8.2)
    while its relaunched vLLM is still loading weights and the file on disk is
    the previous incarnation's. The two facts that make the document current
    are the ones `alive_check` already reads for a service piece: the run has a
    service piece with that endpoint file and that port -- from `meta.json`,
    the current truth a refire rewrites (8.3), and from the start row's list
    when the directory has no `meta.json` -- and the port answers."""
    if not agent_row:
        return None
    for row in registry.open_runs():
        run_dir = Path(row.get("dir", ""))
        if not run_dir.is_dir():
            continue
        meta = _read_json(run_dir / "meta.json") or {}
        row_pieces = meta.get("pieces") or row.get("pieces") or []
        for path in sorted(run_dir.glob("service_agent_*.json")):
            doc = _read_json(path)
            if not doc:
                continue
            claims = doc.get("claims") or {}
            if not all(claims.get(k) == v for k, v in agent_row.items()):
                continue
            if hosts is not None and doc.get("host") not in hosts:
                continue
            served = any(p.get("kind") == "service" and p.get("endpoint_file") == path.name
                         and p.get("port") == doc.get("port") for p in row_pieces)
            if served and _port_answers(doc.get("host"), doc.get("port")):
                return {"run_id": row.get("run_id"), "host": doc.get("host"), "port": doc.get("port")}
    return None


def _folded_row_of(run_id: str):
    """The registry's newest row for one run, folded (8.2): `registry.find({})`
    matches every row and the fold keeps each `run_id`'s newest start row.
    `refire` reads the request fields of the run it restarts a piece of from
    here -- `workflow`, `setting`, `parent`, `swept`, `upstream`, `versions`,
    `diff` -- because those live in the row and not in `meta.json`."""
    return next((r for r in registry.find({}) if r.get("run_id") == run_id), None)


def read_beats_for_run(run_dir: Path) -> dict[int, list[float]]:
    """`{piece index: [beat ts, ...]}` over every incarnation of every piece
    of this run directory (errata: `gate_open_row`'s `beats` argument).
    Public: `run.py`'s own CPU-stage gate call (2.3/2.5) reads the same
    heartbeat files through this function rather than keeping a second
    copy."""
    hb_dir = run_dir / "heartbeat"
    out: dict[int, list[float]] = {}
    if not hb_dir.is_dir():
        return out
    for path in hb_dir.glob("*-*.jsonl"):
        idx_str = path.name.split("-", 1)[0]
        if not idx_str.isdigit():
            continue
        idx = int(idx_str)
        ts_list = out.setdefault(idx, [])
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ts = json.loads(line).get("ts")
                    except json.JSONDecodeError:
                        continue
                    if ts is not None:
                        ts_list.append(ts)
        except OSError:
            continue
    return out


def _strip_runtime(piece: dict) -> dict:
    """Drop `run_dir`, the bookkeeping field `launch()` adds to its own
    in-memory piece dicts for `alive_check`'s use; not one of 8.1's fields."""
    return {k: v for k, v in piece.items() if k != "run_dir"}


def _build_piece_plan(stage: str, setting) -> list[dict]:
    """One entry per piece, in the fixed order of `STAGES[stage]["pieces"]`
    (2.1): a global `index`, its stage-table `kind`, its position within its
    own kind group (`local_index`), and its `mode` flag."""
    entry = schema.STAGES[stage]
    section = getattr(setting, stage)
    plan = []
    idx = 0
    for kind, count_field, mode in entry["pieces"]:
        count = count_field if isinstance(count_field, int) else getattr(section, count_field)
        for local_i in range(count):
            plan.append({"kind": kind, "index": idx, "local_index": local_i, "mode": mode})
            idx += 1
    return plan


def _ensure_log_dir(run_dir: Path) -> None:
    (run_dir / "log").mkdir(parents=True, exist_ok=True)


def _wait_for_endpoint(run_dir: Path, piece: dict) -> str:
    path = run_dir / piece["endpoint_file"]
    deadline = time.time() + registry.DEFAULTS["launch_timeout_s"]
    while time.time() < deadline:
        doc = _read_json(path)
        if doc and doc.get("base_url"):
            return doc["base_url"]
        time.sleep(2)
    sys.exit(f"jobs/launch.py: {path} did not appear within launch_timeout_s")


def _launch_entry(git, *, host, cards, pieces, cmd) -> dict:
    """One entry for `meta.json`'s `launches` list (8.3): `{t, host, commit,
    branch, dirty_count, dirty_files, cards, pieces, cmd}`, from the `git`
    dict the caller was handed. The one builder both `launch()` (many
    pieces, one login-machine event) and `refire()` (one restarted piece)
    go through, so the two write one shape."""
    return {
        "t": _now(), "host": host,
        "commit": git.get("commit"), "branch": git.get("branch"),
        "dirty_count": git.get("dirty_count"), "dirty_files": git.get("dirty_files"),
        "cards": cards, "pieces": pieces, "cmd": cmd,
    }


def _with_ended(placed: list[dict], ended_sessions: list[str]) -> list[dict]:
    out = []
    for p in placed:
        q = _strip_runtime(p)
        if p.get("session") in ended_sessions:
            q = dict(q, ended=True)
        out.append(q)
    return out


# ---------------------------------------------------------------------------
# 8.1: launch().
# ---------------------------------------------------------------------------


def launch(stage, setting, run_dir, resolved, git, cards=None) -> tuple[str, list[dict]]:
    """Launch one stage run's tmux pieces (8.1). Inside one `registry.lock()`
    hold: the launch gate (2.5), the attach test (7.4), the card reservation,
    the port assignment, and the start-row append with `status: "launching"`.
    Then the lock is released and the pieces start in two waves — service
    pieces and their alive check first (an `inject` run's `service_check`
    gate in between), loop pieces last — or, for `train`, its one piece.
    Returns `(outcome, pieces)` with `outcome` `up`, `alive_check` or
    `service_check`; before any outcome but `up`, `teardown_launch` ends every
    session this launch started and the sessions it ended are marked in the
    returned pieces."""
    run_dir = Path(run_dir)
    key = run_dir.name
    run_id = f"{stage}-{key}"
    entry = schema.STAGES[stage]
    env_name = setting.data.env if stage in ("sample", "inject") else None

    agent_alias = setting.models.agent
    agent_row = setting.models.agent_row or {}
    agent_serving = (_table_config().get(agent_alias) or {}).get("serving") or {}
    serving_host = agent_serving.get("host")
    serving_port = agent_serving.get("port")
    tp_size = int(agent_serving.get("tensor_parallel_size", 1) or 1)

    run_dir_str = str(run_dir)

    with registry.lock():
        open_rows = [r for r in registry.open_runs() if r.get("run_id") == run_id]
        meta_by_run: dict[str, dict] = {}
        beats: dict[str, dict] = {}
        for r in open_rows:
            m = _read_json(Path(r["dir"]) / "meta.json") or {}
            meta_by_run[r["run_id"]] = m
            beats[r["run_id"]] = read_beats_for_run(Path(r["dir"]))
        sessions = registry.live_sessions()
        refusal = gate_open_row(open_rows, meta_by_run, sessions, time.time(), beats)
        if refusal is not None:
            sys.exit(f"jobs/launch.py: {refusal}")

        free_by_host = restrict_to_pool(registry.free(), cards)

        # The agent service's host. A live server for this model takes it, on whatever host
        # that server's endpoint file names (the attach of 7.4); a named pool is where this
        # launch runs, so with a pool the server must be on one of the pool's hosts. Otherwise the table row's
        # serving host is the preference `place` searches from, and the cards this launch may
        # claim -- every free card, or the named pool -- decide where the server really lands.
        attach = None
        if stage in ("sample", "inject"):
            attach = _find_attach_target(agent_row, None if cards is None else set(free_by_host))
            if attach is not None:
                serving_host = attach["host"]

        piece_plan = _build_piece_plan(stage, setting)
        n_loop = sum(1 for p in piece_plan if p["kind"] == "loop")
        replicas = getattr(setting, stage).replicas if stage in ("sample", "inject") else 0

        # The host this run's agent service holds, which its probe service prefers (3.4). It
        # starts as the serving host and becomes the host replica 0 was placed on, which the
        # piece order of `STAGES[stage]["pieces"]` settles before the probe service is placed.
        agent_host = serving_host

        placed: list[dict] = []
        for p in piece_plan:
            kind, idx, local_i = p["kind"], p["index"], p["local_index"]
            session = f"{stage}-{key}-{idx}"
            log = f"{run_dir_str}/log/{idx}.txt"

            if kind == "loop":
                venv = _resolve_venv(entry["venv"]["loop"], env_name)
                python = _interpreter_for(venv)
                host = _login_host()
                gpus = ""
                module = entry["program"]
                cmd = piece_command(python, module, run_dir_str, str(local_i), str(n_loop), gpus, log)
                placed.append({"index": idx, "kind": "loop", "host": host, "gpus": gpus,
                                "session": session, "pid": None, "log": log, "port": None,
                                "endpoint_file": None,
                                "agent_replica": local_i % replicas if replicas else 0,
                                "venv": venv, "cmd": cmd, "run_dir": run_dir_str})

            elif kind == "train":
                venv = _resolve_venv(entry["venv"], None)
                python = _interpreter_for(venv)
                host = place("train", 1, free_by_host, serving_host=None,
                             prefer_host=serving_host, attached=False)
                if host is None:
                    sys.exit(_no_cards_message(free_by_host, 1))
                gpu_id = _claim_cards(free_by_host, host, 1)[0]
                module = entry["program"].format(method=setting.probe.method)
                cmd = piece_command(python, module, run_dir_str, None, None, str(gpu_id), log)
                placed.append({"index": idx, "kind": "train", "host": host, "gpus": str(gpu_id),
                                "session": session, "pid": None, "log": log, "port": None,
                                "endpoint_file": None, "agent_replica": None,
                                "venv": venv, "cmd": cmd, "run_dir": run_dir_str})

            elif kind == "service_agent":
                venv = _resolve_venv(entry["venv"]["service_agent"], None)
                python = _interpreter_for(venv)
                attached = attach is not None and local_i == 0
                host = place("service_agent", tp_size, free_by_host,
                             serving_host=serving_host, prefer_host=serving_host,
                             attached=attached)
                if host is None:
                    sys.exit(_no_cards_message(free_by_host, tp_size))
                if local_i == 0:
                    agent_host = host
                if attached:
                    gpus, port = "", attach["port"]
                else:
                    gpu_ids = _claim_cards(free_by_host, host, tp_size)
                    gpus = ",".join(str(g) for g in gpu_ids)
                    port = _next_free_port("service_agent", local_i, serving_port, host)
                endpoint_file = f"service_agent_{local_i}.json"
                cmd = _agent_service_cmd(python, run_dir_str, agent_alias, host, port, gpus, local_i,
                                          attach_only=attached,
                                          attached_to=(attach["run_id"] if attached else None),
                                          log=log)
                placed.append({"index": idx, "kind": "service", "host": host, "gpus": gpus,
                                "session": session, "pid": None, "log": log, "port": port,
                                "endpoint_file": endpoint_file, "agent_replica": None,
                                "venv": venv, "cmd": cmd, "run_dir": run_dir_str})

            elif kind == "service_probe":
                venv = _resolve_venv(entry["venv"]["service_probe"], None)
                python = _interpreter_for(venv)
                render_only = (p["mode"] == "render_only")
                cards_needed = 0 if render_only else 1
                host = place("service_probe", cards_needed, free_by_host,
                             serving_host=None, prefer_host=agent_host, attached=False)
                if host is None:
                    sys.exit(_no_cards_message(free_by_host, cards_needed))
                if render_only:
                    gpus, device, score_ckpt, gen_ckpt, temperature = "", None, None, None, None
                else:
                    gpu_id = _claim_cards(free_by_host, host, 1)[0]
                    gpus, device = str(gpu_id), f"cuda:{gpu_id}"
                    upstream_map = schema.upstream(stage, setting)
                    score_ckpt = schema.referenced_run_dir("train", upstream_map["probe_score.train"])
                    gen_ckpt = schema.referenced_run_dir("train", upstream_map["probe_gen.train"])
                    temperature = resolved.get("probe_temperature")
                port = _next_free_port("service_probe", 0, None, host)
                endpoint_file = "service_probe_0.json"
                cmd = _probe_service_cmd(python, run_dir_str, agent_alias, port,
                                          score_ckpt=score_ckpt, gen_ckpt=gen_ckpt,
                                          temperature=temperature, device=device,
                                          render_only=render_only, log=log)
                placed.append({"index": idx, "kind": "service", "host": host, "gpus": gpus,
                                "session": session, "pid": None, "log": log, "port": port,
                                "endpoint_file": endpoint_file, "agent_replica": None,
                                "venv": venv, "cmd": cmd, "run_dir": run_dir_str})

        split_files = _resolve_split_files(stage, setting) if stage in ("sample", "inject") else []
        persisted_pieces = [_strip_runtime(p) for p in placed]

        start_row = {
            "ev": "start", "t": _now(), "run_id": run_id, "stage": stage, "key": key,
            "dir": run_dir_str, "workflow": setting._file, "setting": setting._name,
            "parent": None, "swept": None, "debug": setting._debug,
            "upstream": schema.upstream(stage, setting),
            "versions": schema.versions_of(stage, setting),
            "diff": schema.fields_of(stage, setting),
            "commit": git["commit"], "branch": git["branch"], "dirty": git["dirty"],
            "dirty_count": git["dirty_count"], "dirty_files": git["dirty_files"],
            "host": _this_host(),
            "pieces": persisted_pieces,
            "status": "launching",
        }
        registry.append_start(start_row)
        launch_entry = _launch_entry(
            git, host=_this_host(),
            cards={p["index"]: p.get("gpus", "") for p in persisted_pieces},
            pieces=[p["index"] for p in persisted_pieces],
            cmd={p["index"]: p.get("cmd", "") for p in persisted_pieces},
        )
        registry.write_meta(run_dir, stage=stage, key=key, dir=run_dir_str,
                             versions=start_row["versions"], upstream=start_row["upstream"],
                             diff=start_row["diff"], debug=setting._debug,
                             pieces=persisted_pieces, split_files=split_files,
                             launches=[launch_entry])

    # -- lock released; start the tmux sessions. --
    _ensure_log_dir(run_dir)
    origin = incarnation_origin(run_dir, placed)

    def failed(outcome: str) -> tuple[str, list[dict]]:
        """Every way out of a launch that did not come up: end what this launch
        started (8.1) and name the sessions ended in the returned pieces."""
        return outcome, _with_ended(placed, teardown_launch(run_dir, placed))

    if stage == "train":
        if not _start_wave(placed):
            return failed("alive_check")
        up, _pending = alive_check(placed, origin)
        if not up:
            return failed("alive_check")
        return "up", [_strip_runtime(p) for p in placed]

    service_pieces = [p for p in placed if p["kind"] == "service"]
    loop_pieces = [p for p in placed if p["kind"] == "loop"]

    if not _start_wave(service_pieces):
        return failed("alive_check")
    up, _pending = alive_check(service_pieces, origin)
    if not up:
        return failed("alive_check")

    if stage == "inject":
        probe_piece = next(p for p in service_pieces if p["endpoint_file"] == "service_probe_0.json")
        base_url = _wait_for_endpoint(run_dir, probe_piece)
        rc = subprocess.run(
            [_interpreter_for("probe"), "-m", "models.probe_models.service", "check",
             "--base-url", base_url, "--run-dir", run_dir_str],
            cwd=str(_repo_root())).returncode
        if rc != 0:
            return failed("service_check")

    if not _start_wave(loop_pieces):
        return failed("alive_check")
    up, _pending = alive_check(loop_pieces, origin)
    if not up:
        return failed("alive_check")

    return "up", [_strip_runtime(p) for p in placed]


# ---------------------------------------------------------------------------
# 2.3: refire().
# ---------------------------------------------------------------------------

# TODO(gyb, 2026-09-22): `run.py refire` cannot restart a service piece. This pattern asks for
# ` 2>&1 | tee -a` right after `--run-dir <dir>`, which a serve line never matches, so refire
# exits with "could not parse the frozen command" (found by the 2026-09-22 launch review, not
# changed). Decide whether a dead service is refired or the whole run is relaunched.
_PIECE_CMD_RE = re.compile(
    r"-m (?P<module>\S+) --run-dir (?P<run_dir>\S+)(?: --piece (?P<i>\d+)/(?P<n>\d+))? "
    r"2>&1 \| tee -a (?P<log>\S+)$"
)


def _parse_piece_cmd(cmd: str):
    m = _PIECE_CMD_RE.search(cmd)
    if not m:
        sys.exit(f"jobs/launch.py refire: could not parse the frozen command: {cmd!r}")
    return m.group("module"), m.group("run_dir"), m.group("i"), m.group("n"), m.group("log")


def refire(run_dir, git, piece=None, cards=None) -> list[dict]:
    """Restart one dead piece beside its live siblings (2.3). Refuses, fail-
    closed, while `registry.session_alive` reports the piece's tmux session
    alive; otherwise warns (never refuses) when the piece already has more
    than one `launches` entry, releases its unfinished claims through
    `data/trajectory_record.release`, re-probes the cards, appends the start
    row of the incarnation it is about to start, restarts the piece in a new
    tmux session under the *same* session name, and rewrites its `meta.json`
    entry and appends a `launches` entry through one `registry.write_meta`
    call.

    The start row is 8.1's, appended after the cards are claimed and before the
    session starts, and it is what makes the refired incarnation a recorded
    one: a start row clears the run's finish row (8.2), so the card
    reservation of 2.5 counts the refired card again, the walk backfills the
    `ok` row when the piece reaches `done.json`, and `run.py kill` writes its
    `killed` row. A `tmux new-session` that fails then leaves a `launching`
    row, which is the same state a first launch leaves and which `ls` closes
    once it is older than `launch_timeout_s` (8.1)."""
    run_dir = Path(run_dir)
    meta = _read_json(run_dir / "meta.json") or {}
    pieces = meta.get("pieces") or []
    target = next((p for p in pieces if p.get("index") == piece), None)
    if target is None:
        sys.exit(f"jobs/launch.py refire: no piece {piece} recorded in {run_dir}/meta.json")

    host, session = target.get("host"), target.get("session")
    if host and session and registry.session_alive(host, session):
        sys.exit(f"jobs/launch.py refire: piece {piece} is alive: session {session!r} on host {host!r}")

    run_id = _run_id_of_meta(meta)
    run_row = _folded_row_of(run_id) if run_id else None
    if run_row is None:
        sys.exit(f"jobs/launch.py refire: {run_dir}/meta.json names no run this registry has a "
                 f"row for, so the restarted piece would go unrecorded (8.1)")

    prior = [l for l in (meta.get("launches") or []) if piece in (l.get("pieces") or [])]
    if len(prior) > 1:
        print(f"jobs/launch.py refire: piece {piece} already has {len(prior)} launch entries: "
              f"{prior}", file=sys.stderr)

    trajectory_record.release(run_dir, registry.live_sessions(), registry.DEFAULTS["launch_timeout_s"])

    free_by_host = restrict_to_pool(registry.free(), cards)
    kind = target.get("kind")
    old_gpus = str(target.get("gpus") or "")
    cards_needed = len([g for g in old_gpus.split(",") if g.strip() != ""])

    new_host, new_gpus = host, old_gpus
    if kind != "loop" and cards_needed > 0:
        placement_kind = ("service_agent" if (kind == "service" and str(target.get("endpoint_file") or "").startswith("service_agent"))
                            else "train" if kind == "train" else "service_probe")
        placed_host = place(placement_kind, cards_needed, free_by_host, serving_host=host,
                             prefer_host=host, attached=False)
        if placed_host is None:
            sys.exit(_no_cards_message(free_by_host, cards_needed))
        new_host = placed_host
        new_gpus = ",".join(str(g) for g in _claim_cards(free_by_host, new_host, cards_needed))

    module, old_run_dir, piece_i, piece_n, log = _parse_piece_cmd(target.get("cmd") or "")
    python = _interpreter_for(target.get("venv"))
    new_cmd = piece_command(python, module, old_run_dir, piece_i, piece_n, new_gpus, log)
    updated_piece = dict(target, host=new_host, gpus=new_gpus, session=session, pid=None, cmd=new_cmd)

    # 8.1's fixed order: the row naming the cards is on disk before the session that uses them.
    # Its `pieces` is the run's whole current list with this piece's entry replaced, because the
    # card reservation of 2.5 reserves the cards of every piece in the newest start row.
    registry.append_start({
        "ev": "start", "t": _now(), "run_id": run_id,
        "stage": run_row.get("stage"), "key": run_row.get("key"), "dir": str(run_dir),
        "workflow": run_row.get("workflow"), "setting": run_row.get("setting"),
        "parent": run_row.get("parent"), "swept": run_row.get("swept"),
        "debug": run_row.get("debug"), "upstream": run_row.get("upstream"),
        "versions": run_row.get("versions"), "diff": run_row.get("diff"),
        "commit": git["commit"], "branch": git["branch"], "dirty": git["dirty"],
        "dirty_count": git["dirty_count"], "dirty_files": git["dirty_files"],
        "host": _this_host(),
        "pieces": [updated_piece if p.get("index") == piece else p for p in pieces],
        "status": "launching",
    })

    if not _start_tmux(new_host, session, new_cmd):
        sys.exit(f"jobs/launch.py refire: failed to start piece {piece} on {new_host!r}")

    launch_entry = _launch_entry(git, host=new_host, cards=new_gpus, pieces=[piece], cmd=new_cmd)
    registry.write_meta(run_dir, pieces=[updated_piece], launches=[launch_entry])
    return [updated_piece]
