"""Launch and refire the tmux pieces of a sample, inject or train run: the dirty-tree gate, the launch gate, card placement, port assignment, the piece and service commands, and teardown.

# venv: probe

A library with no entry-point guard: `run.py` is the one command that calls
it (contracts 0.2, 8.6). Ported against contracts Part 2.3, 2.5, 3.4, 7.4 and
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


def _is_local_host(host: str) -> bool:
    return _canonical_host(host) == _canonical_host(socket.gethostname())


def _on_login_host() -> bool:
    return _is_local_host(_login_host())


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


def _piece_alive(piece: dict, live_sessions) -> bool:
    """A piece is alive when its session is a live one, or — fail-closed,
    3.4/8.0, `jobs/registry._alive_on`'s own rule — when its host's probe
    never answered at all: `registry.live_sessions()` then names that host
    in the returned set's `failed_hosts`, the canonical `hosts:` name (the
    same normalisation `_canonical_host` gives every other host comparison
    in this file). A plain set (no `failed_hosts` attribute) has no failed
    hosts, so a bare-membership caller sees no change."""
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
            if _piece_alive(piece, live_sessions):
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
                alive = _piece_alive(piece, live_sessions)
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


def place(kind, cards_needed, free_by_host, *, serving_host, prefer_host, attached) -> str | None:
    """Which host a piece lands on (3.4). `loop` and a `service_probe` with
    no card go to `login_host`; an agent service always goes to
    `serving_host` (its table row's), taking no card and no card search when
    `attached`; everything else (a checkpoint-loading `service_probe`,
    `train`) takes the first host with `cards_needed` free, preferring
    `prefer_host`. `None` when no host qualifies."""
    if kind == "loop":
        return _login_host()
    if kind == "service_probe" and cards_needed == 0:
        return _login_host()
    if kind == "service_agent":
        if attached:
            return serving_host
        if serving_host is None:
            return None
        if len(free_by_host.get(serving_host, [])) >= cards_needed:
            return serving_host
        return None
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


def _agent_service_cmd(python, run_dir, model_alias, port, gpus, replica, *,
                        attach_only, attached_to, log) -> str:
    """7.1's serve line, plus the `--replica` and `--attached-to` flags of
    errata 7.1/1.5. `--gpus` is unbracketed on every serve line (7.1), so it
    is always present; its value is shell-quoted (`shlex.quote`) so a
    card-less, attached replica's empty value survives tmux's shell as a
    real, empty token — `--gpus ''` — instead of vanishing under ordinary
    word-splitting and shifting every flag after it onto the previous
    flag's place."""
    parts = [python, "-m", "models.agent_models.service", "serve",
              "--run-dir", str(run_dir), "--model", model_alias,
              "--port", str(port), "--gpus", shlex.quote(gpus)]
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


def alive_check(pieces, window_s=30, poll_s=5) -> tuple[bool, list]:
    """`(all_up, failed_pieces)` over `window_s`, polled every `poll_s`
    (errata; 8.1 names the alive check and never defines it). A `loop`,
    `train` or `cpu` piece passes when its log file has grown and its
    session is alive with no `Traceback` in the log's last 4 KB; a
    `service` piece passes when its endpoint file has appeared and its
    port answers. Returns as soon as every piece passes."""
    pieces = list(pieces)
    if not pieces:
        return True, []
    initial_size = {}
    for p in pieces:
        if p.get("kind") != "service":
            log = Path(p.get("log", ""))
            initial_size[p["index"]] = log.stat().st_size if log.exists() else 0

    deadline = time.time() + window_s
    failed: list = []
    while True:
        sessions = registry.live_sessions()
        failed = []
        for p in pieces:
            if p.get("kind") == "service":
                run_dir = p.get("run_dir")
                endpoint_ok = bool(run_dir) and (Path(run_dir) / p["endpoint_file"]).exists()
                ok = endpoint_ok and _port_answers(p.get("host"), p.get("port"))
            else:
                log = Path(p.get("log", ""))
                grew = log.exists() and log.stat().st_size > initial_size.get(p["index"], 0)
                session_ok = _piece_alive(p, sessions)
                tb_free = True
                if log.exists():
                    try:
                        size = log.stat().st_size
                        with open(log, "rb") as f:
                            f.seek(max(0, size - 4096))
                            tb_free = b"Traceback" not in f.read()
                    except OSError:
                        tb_free = True
                ok = grew and session_ok and tb_free
            if not ok:
                failed.append(p)
        if not failed or time.time() >= deadline:
            break
        time.sleep(poll_s)
    return (not failed), failed


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


def _no_cards_message(free_by_host: dict, needed: int, host: str | None = None) -> str:
    if host is not None:
        return (f"jobs/launch.py: host {host!r} does not have {needed} free card(s); "
                f"free there: {free_by_host.get(host, [])}")
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


def _find_attach_target(agent_row: dict, serving_host):
    """7.4's attach search: a live registry row with a `service_agent_*.json`
    on `serving_host` whose `claims` match this run's frozen `result:` block
    (plus `role`/`family`) value for value."""
    if not agent_row or serving_host is None:
        return None
    for row in registry.open_runs():
        run_dir = Path(row.get("dir", ""))
        if not run_dir.is_dir():
            continue
        for path in sorted(run_dir.glob("service_agent_*.json")):
            doc = _read_json(path)
            if not doc or doc.get("host") != serving_host:
                continue
            claims = doc.get("claims") or {}
            if all(claims.get(k) == v for k, v in agent_row.items()):
                return {"run_id": row.get("run_id"), "host": doc.get("host"), "port": doc.get("port")}
    return None


def _read_beats_for_run(run_dir: Path) -> dict[int, list[float]]:
    """`{piece index: [beat ts, ...]}` over every incarnation of every piece
    of this run directory (errata: `gate_open_row`'s `beats` argument)."""
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


def launch(stage, setting, run_dir, resolved, git) -> tuple[str, list[dict]]:
    """Launch one stage run's tmux pieces (8.1). Inside one `registry.lock()`
    hold: the launch gate (2.5), the attach test (7.4), the card reservation,
    the port assignment, and the start-row append with `status: "launching"`.
    Then the lock is released and the pieces start in two waves — service
    pieces and their alive check first (an `inject` run's `service_check`
    gate in between), loop pieces last — or, for `train`, its one piece.
    Returns `(outcome, pieces)` with `outcome` `up`, `alive_check` or
    `service_check`; before any outcome but `up`, `teardown_services` is
    called and the sessions it ended are marked in the returned pieces."""
    if not _on_login_host():
        sys.exit(f"jobs/launch.py: refuses to run on any host but {_login_host()!r}")

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
            beats[r["run_id"]] = _read_beats_for_run(Path(r["dir"]))
        sessions = registry.live_sessions()
        refusal = gate_open_row(open_rows, meta_by_run, sessions, time.time(), beats)
        if refusal is not None:
            sys.exit(f"jobs/launch.py: {refusal}")

        attach = None
        if stage in ("sample", "inject"):
            attach = _find_attach_target(agent_row, serving_host)

        free_by_host = registry.free()
        piece_plan = _build_piece_plan(stage, setting)
        n_loop = sum(1 for p in piece_plan if p["kind"] == "loop")
        replicas = getattr(setting, stage).replicas if stage in ("sample", "inject") else 0

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
                             serving_host=serving_host, prefer_host=None, attached=attached)
                if host is None:
                    sys.exit(_no_cards_message(free_by_host, tp_size, host=serving_host))
                if attached:
                    gpus, port = "", attach["port"]
                else:
                    gpu_ids = _claim_cards(free_by_host, host, tp_size)
                    gpus = ",".join(str(g) for g in gpu_ids)
                    port = _next_free_port("service_agent", local_i, serving_port, host)
                endpoint_file = f"service_agent_{local_i}.json"
                cmd = _agent_service_cmd(python, run_dir_str, agent_alias, port, gpus, local_i,
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
                             serving_host=None, prefer_host=serving_host, attached=False)
                if host is None:
                    sys.exit(_no_cards_message(free_by_host, cards_needed))
                if render_only:
                    gpus, device, score_ckpt, gen_ckpt, temperature = "", None, None, None, None
                else:
                    gpu_id = _claim_cards(free_by_host, host, 1)[0]
                    gpus, device = str(gpu_id), f"cuda:{gpu_id}"
                    upstream_map = schema.upstream(stage, setting)
                    score_ckpt = schema.run_dir_of("train", upstream_map["probe_score.train"], debug=False)
                    gen_ckpt = schema.run_dir_of("train", upstream_map["probe_gen.train"], debug=False)
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
            "host": _login_host(),
            "pieces": persisted_pieces,
            "status": "launching",
        }
        registry.append_start(start_row)
        launch_entry = _launch_entry(
            git, host=_login_host(),
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

    if stage == "train":
        for p in placed:
            _start_tmux(p["host"], p["session"], p["cmd"])
        up, _failed = alive_check(placed)
        if not up:
            ended = teardown_services(run_dir)
            return "alive_check", _with_ended(placed, ended)
        return "up", [_strip_runtime(p) for p in placed]

    service_pieces = [p for p in placed if p["kind"] == "service"]
    loop_pieces = [p for p in placed if p["kind"] == "loop"]

    for p in service_pieces:
        _start_tmux(p["host"], p["session"], p["cmd"])
    up, _failed = alive_check(service_pieces, window_s=registry.DEFAULTS["launch_timeout_s"], poll_s=5)
    if not up:
        ended = teardown_services(run_dir)
        return "alive_check", _with_ended(placed, ended)

    if stage == "inject":
        probe_piece = next(p for p in service_pieces if p["endpoint_file"] == "service_probe_0.json")
        base_url = _wait_for_endpoint(run_dir, probe_piece)
        rc = subprocess.run(
            [_interpreter_for("probe"), "-m", "models.probe_models.service", "check",
             "--base-url", base_url, "--run-dir", run_dir_str],
            cwd=str(_repo_root())).returncode
        if rc != 0:
            ended = teardown_services(run_dir)
            return "service_check", _with_ended(placed, ended)

    for p in loop_pieces:
        _start_tmux(p["host"], p["session"], p["cmd"])
    up, _failed = alive_check(loop_pieces)
    if not up:
        ended = teardown_services(run_dir)
        return "alive_check", _with_ended(placed, ended)

    return "up", [_strip_runtime(p) for p in placed]


# ---------------------------------------------------------------------------
# 2.3: refire().
# ---------------------------------------------------------------------------

_PIECE_CMD_RE = re.compile(
    r"-m (?P<module>\S+) --run-dir (?P<run_dir>\S+)(?: --piece (?P<i>\d+)/(?P<n>\d+))? "
    r"2>&1 \| tee -a (?P<log>\S+)$"
)


def _parse_piece_cmd(cmd: str):
    m = _PIECE_CMD_RE.search(cmd)
    if not m:
        sys.exit(f"jobs/launch.py refire: could not parse the frozen command: {cmd!r}")
    return m.group("module"), m.group("run_dir"), m.group("i"), m.group("n"), m.group("log")


def refire(run_dir, git, piece=None) -> list[dict]:
    """Restart one dead piece beside its live siblings (2.3). Refuses, fail-
    closed, while `registry.session_alive` reports the piece's tmux session
    alive; otherwise warns (never refuses) when the piece already has more
    than one `launches` entry, releases its unfinished claims through
    `data/trajectory_record.release`, re-probes the cards, restarts it in a
    new tmux session under the *same* session name, and rewrites its
    `meta.json` entry and appends a `launches` entry through one
    `registry.write_meta` call."""
    if not _on_login_host():
        sys.exit(f"jobs/launch.py: refuses to run on any host but {_login_host()!r}")

    run_dir = Path(run_dir)
    meta = _read_json(run_dir / "meta.json") or {}
    pieces = meta.get("pieces") or []
    target = next((p for p in pieces if p.get("index") == piece), None)
    if target is None:
        sys.exit(f"jobs/launch.py refire: no piece {piece} recorded in {run_dir}/meta.json")

    host, session = target.get("host"), target.get("session")
    if host and session and registry.session_alive(host, session):
        sys.exit(f"jobs/launch.py refire: piece {piece} is alive: session {session!r} on host {host!r}")

    prior = [l for l in (meta.get("launches") or []) if piece in (l.get("pieces") or [])]
    if len(prior) > 1:
        print(f"jobs/launch.py refire: piece {piece} already has {len(prior)} launch entries: "
              f"{prior}", file=sys.stderr)

    trajectory_record.release(run_dir, registry.live_sessions(), registry.DEFAULTS["launch_timeout_s"])

    free_by_host = registry.free()
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

    if not _start_tmux(new_host, session, new_cmd):
        sys.exit(f"jobs/launch.py refire: failed to start piece {piece} on {new_host!r}")

    updated_piece = dict(target, host=new_host, gpus=new_gpus, session=session, pid=None, cmd=new_cmd)
    launch_entry = _launch_entry(git, host=new_host, cards=new_gpus, pieces=[piece], cmd=new_cmd)
    registry.write_meta(run_dir, pieces=[updated_piece], launches=[launch_entry])
    return [updated_piece]
