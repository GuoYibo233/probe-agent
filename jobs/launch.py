"""Launch the tmux pieces of a sample, inject or train run and refire a dead loop or train piece of an unfinished run (an omitted --piece names the run's one loop or train piece; a dead service piece is handled by re-running the walk, a finished run by run.py retry): the dirty-tree gate, the launch gate, card placement, port assignment, the piece and service commands, and teardown.

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


def _this_host() -> str:
    """The machine this launch runs on, under its `constants/cards.yaml` entry's own name."""
    return registry.canonical_host(socket.gethostname())


def _is_local_host(host: str) -> bool:
    return registry.canonical_host(host) == _this_host()


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


def code_blobs(files) -> dict[str, str]:
    """path -> git blob id of each of `files` as the working tree holds it (`git hash-object`, the id `ls-tree` gives a committed copy of the same bytes): the copy of a stage's code a launch records in its launches entry, which run.py's code gate (3.3) reads back. Refuses, naming them, files the tree does not hold."""
    files = tuple(files)
    repo_root = _repo_root()
    missing = [f for f in files if not (repo_root / f).is_file()]
    if missing:
        sys.exit(f"jobs/launch.py: the stage table's code tuple names {missing}, which the tree "
                 "does not hold; run.py selfcheck names the tuple")
    if not files:
        return {}
    r = subprocess.run(["git", "-C", str(repo_root), "hash-object", "--", *files],
                        capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        sys.exit(f"jobs/launch.py: git hash-object failed: {(r.stderr or r.stdout).strip()}")
    return dict(zip(files, r.stdout.split()))


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
    in the returned set's `failed_hosts`, the host's `constants/cards.yaml`
    name (the same normalisation `registry.canonical_host` gives every other
    host comparison in this file). A plain set (no `failed_hosts` attribute) has no failed
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
    if failed_hosts and registry.canonical_host(host) in failed_hosts:
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
    a host is stored under its `constants/cards.yaml` entry's own name, and a host named twice keeps both lists."""
    pool: dict[str, list[int]] = {}
    for tok in tokens:
        host, sep, ids = tok.partition(":")
        if not (host and sep and ids and all(i.strip().isdigit() for i in ids.split(","))):
            sys.exit(f"jobs/launch.py: --cards {tok!r} is not <host>:<id>,<id>,...")
        cards = pool.setdefault(registry.canonical_host(host), [])
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


def fitting_cards(free_by_host: dict, host: str, min_card_gib: int) -> list[int]:
    """The free cards of `host` whose memory (`constants/cards.yaml`) is at least `min_card_gib`
    GiB, in the order the free list gives them."""
    memory = registry.card_memory_gib()[host]
    return [i for i in free_by_host.get(host) or [] if memory[i] >= min_card_gib]


def _declared_card_gib(agent_alias: str) -> int:
    """The card size an agent service was declared for: the smallest card of its model table
    row's serving host. The owner chose that host because its cards hold the model, so a server
    that starts anywhere else needs cards at least that large."""
    serving_host = _table_config()[agent_alias]["serving"]["host"]
    return min(registry.card_memory_gib()[registry.canonical_host(serving_host)])


def place(kind, cards_needed, free_by_host, *, min_card_gib, serving_host, prefer_host,
          attached) -> str | None:
    """Which host a piece lands on (3.4). `loop` and a `service_probe` with
    no card go to `login_host`; an `attached` agent service goes to
    `serving_host`, the host of the live server it attaches to, taking no card
    and no card search; everything else (an agent service that starts its own
    server, a checkpoint-loading `service_probe`, `train`) takes the first host
    with `cards_needed` free cards of at least `min_card_gib` GiB each,
    preferring `prefer_host`. `None` when no host qualifies."""
    if kind == "loop":
        return _login_host()
    if kind == "service_probe" and cards_needed == 0:
        return _login_host()
    if kind == "service_agent" and attached:
        return serving_host
    # A piece lands only on cards at least as large as the cards it was declared for. An agent
    # service that starts its own server was declared for its table row's serving host, so
    # `min_card_gib` is that host's smallest card (`_declared_card_gib`) and the serving host is
    # `prefer_host`; a train piece and a checkpoint-loading probe service name no host, so their
    # `min_card_gib` is 0 and the card count alone decides.
    candidates = []
    if prefer_host is not None and prefer_host in free_by_host:
        candidates.append(prefer_host)
    for host in free_by_host:
        if host not in candidates:
            candidates.append(host)
    for host in candidates:
        if len(fitting_cards(free_by_host, host, min_card_gib)) >= cards_needed:
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
# Host execution: local when a host normalises to this machine, ssh otherwise
# (errata, 3.4/8.0). jobs/launch.py's own copy, used to start and end tmux
# sessions, to probe a service's port and to run the probe service's check
# client; registry.py's copy (private) serves its own callers. The ssh target
# is the host's `constants/cards.yaml` name, the name `registry.live_sessions`
# reaches every host by: a host's alias resolves only inside the cluster
# network (`ssh shiga` has no route from a machine outside it, `ssh tokyo105`
# does).
# ---------------------------------------------------------------------------


def _remote_run(host: str, script: str, timeout: float | None = 20.0) -> tuple[bool, str]:
    """Run `script` on `host`: `(ok, stdout)`, `ok` False on a nonzero exit, a
    failed ssh or a timeout. `timeout=None` waits for the script to end."""
    if _is_local_host(host):
        argv = ["bash", "-c", script]
    else:
        argv = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
                registry.canonical_host(host), script]
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except Exception:
        return False, ""
    return r.returncode == 0, r.stdout


def _start_tmux(host: str, session: str, inner_cmd: str) -> bool:
    script = f"tmux new-session -d -s {shlex.quote(session)} {shlex.quote(inner_cmd)}"
    ok, _out = _remote_run(host, script)
    return ok


def _start_wave(run_dir, pieces) -> bool:
    """Start one wave's tmux sessions; True when every session of the wave
    started. `tmux new-session` fails when the host is unreachable and when a
    session of that name is already there — the session name is a pure
    function of the run id and the piece index (8.1), so a relaunch into a
    directory whose earlier piece is still running hits its own name. Both
    mean this launch has no process of its own for that piece, so it says so
    and the caller ends the launch, rather than passing an alive check against
    somebody else's session.

    Each session that started is stamped on its piece's `meta.json` entry as
    `started`, the time of the start: a piece with no such stamp has no session
    because none was ever started for it (a later wave, or a launch that ended
    before its wave), and `registry.judge` reads it `not started` instead of
    `dead` (repo test 2026-09-25, D1)."""
    started = True
    for p in pieces:
        if not _start_tmux(p["host"], p["session"], p["cmd"]):
            print(f"jobs/launch.py: piece {p['index']}: tmux new-session failed for session "
                  f"{p['session']!r} on host {p['host']!r}", file=sys.stderr)
            started = False
            continue
        p["started"] = _now()
        registry.write_meta(run_dir, pieces=[_strip_runtime(p)])
    return started


def _kill_tmux(host: str, session: str) -> bool:
    script = f"tmux kill-session -t {shlex.quote(session)}"
    ok, _out = _remote_run(host, script)
    return ok


def _port_answers(host: str | None, port) -> bool:
    """Whether a TCP connection to `port` opens on `host`, tested on `host`
    itself the way a session is tested with `tmux ls` on its host: in place
    when `host` is this machine, over ssh otherwise, connecting to 127.0.0.1
    there (both services bind 0.0.0.0), so the answer does not depend on
    whether this machine can route to the cluster's service ports.
    Fail-closed (3.4, 6.3): a failed or timed-out ssh reads as not answering."""
    if not host or not port:
        return False
    script = f"timeout 3 bash -c {shlex.quote(f'exec 3<>/dev/tcp/127.0.0.1/{int(port)}')}"
    ok, _out = _remote_run(host, script)
    return ok


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


def incarnation_origin(run_dir, pieces) -> dict[int, dict]:
    """One rule over every kind of piece: what a piece inherits from an earlier
    incarnation is snapshotted or cleared here, before the first
    `tmux new-session`, because everything a piece writes after that is its
    own. That is what lets `alive_check` read this incarnation's output and no
    earlier one's (errata, section-4 walks: an old `Traceback` in the reused
    log closed every relaunch at its first poll).

    A `loop`, `train` or `cpu` piece appends to a log the run directory already
    holds (`tee -a`, 3.4), so its origin is a snapshot: the returned
    `{piece index: {"log_size"}}` is what its `log/<index>.txt` held before
    this launch started it. Its heartbeat file needs no snapshot here: the
    piece entry's own `beat_launch`, recorded before the session starts, names
    the file this incarnation opens (`registry.current_beats`). A
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


def _piece_finished(piece: dict) -> bool:
    """Whether this incarnation of a `loop`, `train` or `cpu` piece walked its
    whole share: its own heartbeat rows (`registry.current_beats`, the file
    the entry's `beat_launch` names) end with the `status: "done"` row
    `registry.Heartbeat.finish` writes. `agent/run_tasks.py` writes it when
    its rotation is walked out and `train/utils/trainer.py` after `done.json`,
    so a piece whose session has ended with that row on disk did its work; a
    piece killed mid-share leaves no such row."""
    beats = registry.current_beats(piece.get("run_dir", ""), piece)
    return bool(beats) and beats[-1].get("status") == "done"


def alive_check(pieces, origin, window_s=None, poll_s=5) -> tuple[bool, list]:
    """`(all_up, pending_pieces)`, polled every `poll_s` for at most `window_s`
    (default `registry.DEFAULTS["launch_timeout_s"]`; errata: 8.1 names the
    alive check and never defines it). `origin` is `incarnation_origin`'s map,
    taken before the sessions started; that call is what makes every test below
    read this incarnation's own output: the map holds a work piece's log size
    and the endpoint file it cleared for a service piece, and a work piece's
    heartbeat is read through its entry's `beat_launch` (`_piece_finished`).

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
                finished = _piece_finished(p)
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


def _claim_cards(free_by_host: dict, host: str, n: int, min_card_gib: int) -> list[int]:
    """Claim the first `n` free cards of `host` that are at least `min_card_gib` GiB, taking them
    out of `free_by_host` in place."""
    ids = fitting_cards(free_by_host, host, min_card_gib)
    if len(ids) < n:
        sys.exit(f"jobs/launch.py: host {host!r} has only {len(ids)} free card(s) of at least "
                 f"{min_card_gib} GiB, need {n}")
    claimed = ids[:n]
    free_by_host[host] = [i for i in free_by_host[host] if i not in claimed]
    return claimed


def _no_cards_message(free_by_host: dict, needed: int, min_card_gib: int, pool) -> str:
    """The refusal when `place` finds no host for a piece. With a named pool, each pool card
    smaller than the piece's `min_card_gib` is named with its size, as `restrict_to_pool` names
    a pool card that is not free."""
    memory = registry.card_memory_gib()
    if pool is not None:
        small = [f"{h}:{i} ({memory[h][i]} GiB)" for h, ids in free_by_host.items()
                 for i in ids if memory[h][i] < min_card_gib]
        if small:
            return (f"jobs/launch.py: --cards names card(s) smaller than the {min_card_gib} GiB "
                    f"this piece needs: {', '.join(small)}")
    probed = ", ".join(f"{h}:{len(fitting_cards(free_by_host, h, min_card_gib))} free"
                       for h in free_by_host)
    return (f"jobs/launch.py: no host has {needed} free card(s) of at least {min_card_gib} GiB; "
            f"probed {probed}")


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
                # An attached run's endpoint file carries the same claims, host and port as
                # the server it attached to, and names that server's run in `attached_to`.
                # The new run attaches to that owner, never to the attacher: teardown asks
                # `_attached_elsewhere` about the owner's run_id, so naming the attacher would
                # let the owner's server be ended while this run still uses it.
                owner = doc.get("attached_to") or row.get("run_id")
                return {"run_id": owner, "host": doc.get("host"), "port": doc.get("port")}
    return None


def _folded_row_of(run_id: str):
    """The registry's newest row for one run, folded (8.2): `registry.find({})`
    matches every row and the fold keeps each `run_id`'s newest start row.
    `refire` reads the request fields of the run it restarts a piece of from
    here -- `workflow`, `setting`, `parent`, `swept`, `upstream`, `era`,
    `diff` -- because those live in the row and not in `meta.json`."""
    return next((r for r in registry.find({}) if r.get("run_id") == run_id), None)


def read_beats_for_run(run_dir: Path, pieces: list[dict]) -> dict[int, list[float]]:
    """`{piece index: [beat ts, ...]}` over the incarnation each `loop`,
    `train` or `cpu` entry of `pieces` records (`registry.current_beats`;
    errata: `gate_open_row`'s `beats` argument). The gate's third test reads a
    piece with beats and no process as observed dead, and an earlier
    incarnation's beats would make a piece of this launch that has not started
    yet read that way. Public: `run.py`'s own CPU-stage gate call (2.3/2.5)
    reads the same heartbeat files through this function rather than keeping
    a second copy."""
    out: dict[int, list[float]] = {}
    for piece in pieces:
        if piece.get("kind") in ("loop", "train", "cpu"):
            out[piece["index"]] = [b["ts"] for b in registry.current_beats(run_dir, piece)
                                   if b.get("ts") is not None]
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


def _wait_for_endpoint(run_dir: Path, piece: dict) -> str | None:
    """The `base_url` of a service piece's endpoint file (7.4), polled for at
    most `launch_timeout_s`; `None` when no readable document carrying one
    appeared in that window. `launch()` treats `None` as a failed service
    check, so this exit ends the sessions the launch started like every other
    failure (8.1)."""
    path = run_dir / piece["endpoint_file"]
    deadline = time.time() + registry.DEFAULTS["launch_timeout_s"]
    while time.time() < deadline:
        doc = _read_json(path)
        if doc and doc.get("base_url"):
            return doc["base_url"]
        time.sleep(2)
    print(f"jobs/launch.py: {path} carried no base_url within launch_timeout_s", file=sys.stderr)
    return None


def _launch_entry(git, *, host, cards, pieces, cmd, code) -> dict:
    """One entry for `meta.json`'s `launches` list (8.3): `{t, host, commit,
    branch, dirty_count, dirty_files, cards, pieces, cmd, code}`, from the
    `git` dict the caller was handed; `code` is the working tree's copy of
    the stage's code files (`code_blobs`), so a `--allow-dirty` launch records
    the code that ran and not HEAD's. The one builder both `launch()` (many
    pieces, one login-machine event) and `refire()` (one restarted piece)
    go through, so the two write one shape."""
    return {
        "t": _now(), "host": host,
        "commit": git.get("commit"), "branch": git.get("branch"),
        "dirty_count": git.get("dirty_count"), "dirty_files": git.get("dirty_files"),
        "cards": cards, "pieces": pieces, "cmd": cmd, "code": code,
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
            beats[r["run_id"]] = read_beats_for_run(
                Path(r["dir"]), _pieces_of_row(r["run_id"], r, meta_by_run))
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

        # The interpreter the inject run's service check runs under, looked up here with every
        # piece's own, so a missing venvs entry refuses the launch before its start row is
        # appended and before any session starts.
        check_python = _interpreter_for("probe") if stage == "inject" else None

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
                                "beat_launch": registry.next_beat_launch(run_dir, idx),
                                "venv": venv, "cmd": cmd, "run_dir": run_dir_str})

            elif kind == "train":
                venv = _resolve_venv(entry["venv"], None)
                python = _interpreter_for(venv)
                host = place("train", 1, free_by_host, min_card_gib=0, serving_host=None,
                             prefer_host=serving_host, attached=False)
                if host is None:
                    sys.exit(_no_cards_message(free_by_host, 1, 0, cards))
                gpu_id = _claim_cards(free_by_host, host, 1, 0)[0]
                module = entry["program"].format(method=setting.probe.method)
                cmd = piece_command(python, module, run_dir_str, None, None, str(gpu_id), log)
                placed.append({"index": idx, "kind": "train", "host": host, "gpus": str(gpu_id),
                                "session": session, "pid": None, "log": log, "port": None,
                                "endpoint_file": None, "agent_replica": None,
                                "beat_launch": registry.next_beat_launch(run_dir, idx),
                                "venv": venv, "cmd": cmd, "run_dir": run_dir_str})

            elif kind == "service_agent":
                venv = _resolve_venv(entry["venv"]["service_agent"], None)
                python = _interpreter_for(venv)
                attached = attach is not None and local_i == 0
                agent_card_gib = _declared_card_gib(agent_alias)
                host = place("service_agent", tp_size, free_by_host, min_card_gib=agent_card_gib,
                             serving_host=serving_host, prefer_host=serving_host,
                             attached=attached)
                if host is None:
                    sys.exit(_no_cards_message(free_by_host, tp_size, agent_card_gib, cards))
                if local_i == 0:
                    agent_host = host
                if attached:
                    gpus, port = "", attach["port"]
                else:
                    gpu_ids = _claim_cards(free_by_host, host, tp_size, agent_card_gib)
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
                host = place("service_probe", cards_needed, free_by_host, min_card_gib=0,
                             serving_host=None, prefer_host=agent_host, attached=False)
                if host is None:
                    sys.exit(_no_cards_message(free_by_host, cards_needed, 0, cards))
                if render_only:
                    gpus, device, score_ckpt, gen_ckpt, temperature = "", None, None, None, None
                else:
                    gpu_id = _claim_cards(free_by_host, host, 1, 0)[0]
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
            "era": schema.era_of(stage),
            "diff": schema.fields_of(stage, setting),
            # The command-line overrides the setting was loaded under, so `run.py ls` reloads
            # it the same way when it asks whether the setting was edited since.
            "overrides": dict(setting._overrides),
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
            code=code_blobs(schema.code_files(stage, setting)),
        )
        registry.write_meta(run_dir, stage=stage, key=key, dir=run_dir_str,
                             era=start_row["era"], upstream=start_row["upstream"],
                             diff=start_row["diff"], debug=setting._debug,
                             overrides=start_row["overrides"],
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
        if not _start_wave(run_dir, placed):
            return failed("alive_check")
        up, _pending = alive_check(placed, origin)
        if not up:
            return failed("alive_check")
        return "up", [_strip_runtime(p) for p in placed]

    service_pieces = [p for p in placed if p["kind"] == "service"]
    loop_pieces = [p for p in placed if p["kind"] == "loop"]

    if not _start_wave(run_dir, service_pieces):
        return failed("alive_check")
    up, _pending = alive_check(service_pieces, origin)
    if not up:
        return failed("alive_check")

    if stage == "inject":
        probe_piece = next(p for p in service_pieces if p["endpoint_file"] == "service_probe_0.json")
        base_url = _wait_for_endpoint(run_dir, probe_piece)
        if base_url is None:
            return failed("service_check")
        # The check client runs on login_host, where the loop pieces it vouches for run and
        # which reaches the probe service's base_url, through the path a loop piece is started
        # with (in place when login_host is this machine, ssh otherwise).
        check_cmd = (f"cd {shlex.quote(str(_repo_root()))} && {shlex.quote(check_python)} -m "
                     f"models.probe_models.service check --base-url {shlex.quote(base_url)} "
                     f"--run-dir {shlex.quote(run_dir_str)} 2>&1")
        check_ok, check_out = _remote_run(_login_host(), check_cmd, timeout=None)
        sys.stdout.write(check_out)
        if not check_ok:
            return failed("service_check")

    if not _start_wave(run_dir, loop_pieces):
        return failed("alive_check")
    up, _pending = alive_check(loop_pieces, origin)
    if not up:
        return failed("alive_check")

    return "up", [_strip_runtime(p) for p in placed]


# ---------------------------------------------------------------------------
# 2.3: refire().
# ---------------------------------------------------------------------------

# Refire restarts a dead loop or train piece of an unfinished run only (owner ruling 2026-09-24;
# contracts 2.3: a piece is dead when its session is gone and its stage has no done.json). A dead
# service piece is handled by killing the run and re-running the walk, `run.py <workflow>
# <setting> [--debug]`, which relaunches the whole run; a CPU stage is re-run in place by the
# walk; a finished run is started fresh by `run.py retry`. refire_target() refuses a piece of
# any other kind, naming its index and kind, and a piece of a finished run; `run.py refire` calls
# it before the dirty-tree gate and the freeze, and refire() calls it before its liveness test,
# its claim release and its command parse.
REFIRE_KINDS = ("loop", "train")


def _train_can_continue(run_dir: Path) -> bool:
    """Whether a restarted train piece would get past the trainer's continue rule
    (`train/utils/trainer.run`, contracts 2.4), asked before refire writes a start row:
    the trainer continues from `last/` (or from a `last.prev/` its checkpoint settling
    restores), predicts from `best/` when `train_done.json` is there (whether or not a
    `predictions.parquet` is), starts fresh when no `train_log.jsonl` exists yet, and refuses
    a directory that holds `train_log.jsonl` and none of those, because a second training
    would mix two runs in one log. Refire used to
    start that refused incarnation, which died at once and left a `launching` row that
    blocked `run.py retry` for `launch_timeout_s` (repo test 2026-09-25, O10). This module
    imports no torch, so the rule is restated here and both places name each other."""
    run_dir = Path(run_dir)
    if (run_dir / "train_done.json").exists():
        return True
    if (run_dir / "last").exists() or (run_dir / "last.prev").exists():
        return True
    return not (run_dir / "train_log.jsonl").exists()


def refire_refusal(run_dir, target: dict) -> str | None:
    """The continue-rule refusal for a session-less train piece, or None when
    refire may go on: `run.py refire` asks it right after `refire_target`,
    before the dirty-tree gate and the freeze, so a refused refire rewrites
    nothing, and `refire()` asks it again after its own liveness test. A piece
    whose session is alive is not judged here (it is refused as alive)."""
    run_dir = Path(run_dir)
    if target.get("kind") != "train":
        return None
    host, session = target.get("host"), target.get("session")
    if host and session and registry.session_alive(host, session):
        return None
    if _train_can_continue(run_dir):
        return None
    return (f"jobs/launch.py refire: {run_dir} holds train_log.jsonl and neither a last/ checkpoint "
            f"nor a train_done.json, so the trainer would refuse to "
            f"continue it (contracts 2.4: a second training would mix two runs in one log); "
            f"run.py retry <workflow> <setting> train [--debug] starts it fresh")


def _run_finished(run_dir: Path) -> bool:
    """Whether the run's `done.json` was written by its newest launch: the rule `run.py`'s walk
    and `registry.sync` close a run by (8.2). A `done.json` stamped with an earlier launch is
    the previous request's, left in place while a widened request's launch is in flight (2.3)."""
    done = _read_json(run_dir / "done.json")
    return done is not None and done.get("launch") == registry.launch_ordinal(run_dir)


def refire_target(run_dir, piece) -> tuple[dict, dict]:
    """The run's `meta.json` and the entry of the piece `run.py refire` names,
    when that entry exists, its kind is in `REFIRE_KINDS` and the run is not
    finished; otherwise exits with the refusal. `piece` None (`--piece`
    omitted) names the run's one loop or train piece when it records exactly
    one (every train run); a run that records several is refused with its
    piece list. One function, so `run.py refire` and refire() refuse with the
    same text and resolve the same piece."""
    run_dir = Path(run_dir)
    meta = _read_json(run_dir / "meta.json") or {}
    recorded = meta.get("pieces") or []
    if piece is None:
        refireable = [p for p in recorded if p.get("kind") in REFIRE_KINDS]
        if len(refireable) == 1:
            target = refireable[0]
        else:
            listed = [(p.get("index"), p.get("kind")) for p in recorded]
            sys.exit(f"jobs/launch.py refire: --piece is required: this run records pieces "
                     f"{listed} in {run_dir}/meta.json")
    else:
        target = next((p for p in recorded if p.get("index") == piece), None)
        if target is None:
            sys.exit(f"jobs/launch.py refire: no piece {piece} recorded in {run_dir}/meta.json")
    piece = target.get("index")
    kind = target.get("kind")
    if kind in REFIRE_KINDS:
        if _run_finished(run_dir):
            sys.exit(f"jobs/launch.py refire: {run_dir} is finished (done.json present, written "
                     f"by its newest launch); piece {piece} is done, not dead; run.py retry "
                     f"<workflow> <setting> {meta.get('stage', '<stage>')} [--debug] starts it "
                     f"fresh")
        return meta, target
    if kind == "cpu":
        sys.exit(f"jobs/launch.py refire: piece {piece} is a cpu piece; refire restarts loop and "
                 f"train pieces only. Re-run the walk, run.py <workflow> <setting> [--debug], "
                 f"which re-runs the stage in place (owner ruling 2026-09-24)")
    sys.exit(f"jobs/launch.py refire: piece {piece} is a {kind} piece; refire restarts loop and "
             f"train pieces only. Kill the run, run.py kill <workflow> <setting> <stage> "
             f"[--debug], then re-run the walk, run.py <workflow> <setting> [--debug], which "
             f"relaunches the whole run (owner ruling 2026-09-24)")


# The piece command of a loop or train piece, in piece_command's shape; a command this pattern
# does not match is a malformed record.
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
    """Restart one dead loop or train piece beside its live siblings (2.3).
    `piece` None names the run's one loop or train piece (`refire_target`).
    Refuses a piece of any other kind and a piece of a finished run through
    `refire_target`, before the liveness test, the claim release and the
    command parse: a dead service piece is handled by killing the run and
    re-running the walk, which relaunches the whole run, a CPU stage is re-run
    in place by the walk (owner ruling 2026-09-24), and a finished run is
    started fresh by `run.py retry`. Refuses, fail-closed, while
    `registry.session_alive` reports the piece's tmux session alive;
    otherwise warns (never refuses) when the piece already has more than one
    `launches` entry, releases its unfinished claims through
    `data/trajectory_record.release`, re-probes the cards, appends the start
    row of the incarnation it is about to start, restarts the piece in a new
    tmux session under the *same* session name, and rewrites its `meta.json`
    entry and appends a `launches` entry through one `registry.write_meta`
    call.

    Everything from reading the piece's entry through `tmux new-session` runs
    inside one `registry.lock()` hold: the liveness test, the claim release,
    the card re-probe and claim, the start row, the `meta.json` rewrite and the
    session start. The liveness test is refire's only guard against a second
    refire of the same piece, and the session it tests for exists only once
    `tmux new-session` has returned, so the hold ends after that call; a hold
    that ended before it would let a second `run.py refire` pass the liveness
    test, append its own start row, rewrite `meta.json` and then either fail on
    the session name (same host) or start a second incarnation on another host
    into the same run directory. The hold is one bounded session
    start (no alive check follows it; `_remote_run` gives up after 20 s).
    launch() ends its hold before its tmux waves (8.1, 8.6; owner ruling 10 of
    2026-09-24) because a second launch into the same run is refused by the
    launch gate's young-`launching`-row clause (`gate_open_row`), which has no
    counterpart for a refire.

    The start row is 8.1's, appended after the cards are claimed and before the
    session starts, and it is what makes the refired incarnation a recorded
    one: a start row clears the run's finish row (8.2), so the card
    reservation of 2.5 counts the refired card again, the walk backfills the
    `ok` row when the piece reaches `done.json`, and `run.py kill` writes its
    `killed` row. A `tmux new-session` that fails exits inside the hold and
    leaves the `launching` row with no finish row; `run.py ls` and `sync`
    close it with a `launch_failed` row once it is older than
    `launch_timeout_s` and every piece it names reads `dead`
    (`registry.launch_failed`, 8.1), so the run stays open while a sibling
    piece lives."""
    run_dir = Path(run_dir)
    with registry.lock():
        meta, target = refire_target(run_dir, piece)
        # The recorded index of the piece refire_target resolved (`--piece` omitted names the
        # run's one loop or train piece); every step below addresses the piece by it.
        index = target["index"]
        pieces = meta.get("pieces") or []
        kind = target.get("kind")

        host, session = target.get("host"), target.get("session")
        if host and session and registry.session_alive(host, session):
            sys.exit(f"jobs/launch.py refire: piece {index} is alive: session {session!r} "
                     f"on host {host!r}")

        refusal = refire_refusal(run_dir, target)
        if refusal is not None:
            sys.exit(refusal)

        run_id = _run_id_of_meta(meta)
        run_row = _folded_row_of(run_id) if run_id else None
        if run_row is None:
            sys.exit(f"jobs/launch.py refire: {run_dir}/meta.json names no run this registry has a "
                     f"row for, so the restarted piece would go unrecorded (8.1)")

        prior = [l for l in (meta.get("launches") or []) if index in (l.get("pieces") or [])]
        if len(prior) > 1:
            print(f"jobs/launch.py refire: piece {index} already has {len(prior)} launch entries: "
                  f"{prior}", file=sys.stderr)

        trajectory_record.release(run_dir, registry.live_sessions(),
                                  registry.DEFAULTS["launch_timeout_s"])

        free_by_host = restrict_to_pool(registry.free(), cards)
        old_gpus = str(target.get("gpus") or "")
        cards_needed = len([g for g in old_gpus.split(",") if g.strip() != ""])

        # A loop piece holds no card and restarts on its host; a train piece is placed again.
        new_host, new_gpus = host, old_gpus
        if kind == "train" and cards_needed > 0:
            placed_host = place("train", cards_needed, free_by_host, min_card_gib=0,
                                 serving_host=host, prefer_host=host, attached=False)
            if placed_host is None:
                sys.exit(_no_cards_message(free_by_host, cards_needed, 0, cards))
            new_host = placed_host
            new_gpus = ",".join(
                str(g) for g in _claim_cards(free_by_host, new_host, cards_needed, 0))

        module, old_run_dir, piece_i, piece_n, log = _parse_piece_cmd(target.get("cmd") or "")
        python = _interpreter_for(target.get("venv"))
        new_cmd = piece_command(python, module, old_run_dir, piece_i, piece_n, new_gpus, log)
        updated_piece = dict(target, host=new_host, gpus=new_gpus, session=session, pid=None,
                             cmd=new_cmd)
        # The heartbeat file the restarted incarnation opens, recorded before its session starts
        # (registry.current_beats), so no verdict reads the dead incarnation's rows as this one's.
        updated_piece["beat_launch"] = registry.next_beat_launch(run_dir, index)

        # 8.1's fixed order: the row naming the cards is on disk before the session that uses them.
        # Its `pieces` is the run's whole current list with this piece's entry replaced, because the
        # card reservation of 2.5 reserves the cards of every piece in the newest start row.
        registry.append_start({
            "ev": "start", "t": _now(), "run_id": run_id,
            "stage": run_row.get("stage"), "key": run_row.get("key"), "dir": str(run_dir),
            "workflow": run_row.get("workflow"), "setting": run_row.get("setting"),
            "parent": run_row.get("parent"), "swept": run_row.get("swept"),
            "debug": run_row.get("debug"), "upstream": run_row.get("upstream"),
            "era": run_row.get("era"), "diff": run_row.get("diff"),
            "overrides": run_row.get("overrides") or {},
            "commit": git["commit"], "branch": git["branch"], "dirty": git["dirty"],
            "dirty_count": git["dirty_count"], "dirty_files": git["dirty_files"],
            "host": _this_host(),
            "pieces": [updated_piece if p.get("index") == index else p for p in pieces],
            "status": "launching",
        })

        # meta.json carries the new entry (its `beat_launch` included) before the
        # session starts, the order launch() uses, so no reader sees the earlier
        # incarnation's heartbeat file under the new session.
        launch_entry = _launch_entry(
            git, host=new_host, cards={index: new_gpus}, pieces=[index], cmd={index: new_cmd},
            code=code_blobs(schema.code_files(run_row.get("stage"), schema.load_frozen(run_dir))))
        registry.write_meta(run_dir, pieces=[updated_piece], launches=[launch_entry])

        # The session starts inside the hold: the liveness test above is the only guard against
        # a second refire of this piece, and the session it tests for exists only once
        # `tmux new-session` has returned. launch() releases before its tmux waves because the
        # launch gate refuses a young `launching` row; refire has no such clause.
        if not _start_tmux(new_host, session, new_cmd):
            sys.exit(f"jobs/launch.py refire: failed to start piece {index} on {new_host!r}")
        # The session exists: stamp the entry the way `_start_wave` stamps a launch's.
        updated_piece["started"] = _now()
        registry.write_meta(run_dir, pieces=[updated_piece])
    return [updated_piece]
