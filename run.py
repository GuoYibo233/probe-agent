"""The one command: walk a named setting's stages (sample through score), or run one of the ten reserved subcommands (ls, where, find, kill, refire, retry, table, free, sync, selfcheck)."""
# venv: probe
from __future__ import annotations

import hashlib
import json
import re
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

from data import trajectory_record
from data.environments import open_env, requested_pairs
from eval import method_table
from eval.utils import probe_eval
from experimental_settings import schema
from jobs import launch, registry

ROOT = Path(__file__).resolve().parent

RESERVED_SUBCOMMANDS = (
    "ls", "where", "find", "kill", "refire", "retry", "table", "free", "sync", "selfcheck",
)

_SUBCOMMAND_ONE_LINE = {
    "ls": "[workflow] [--debug] -- one folded line per run",
    "where": "<workflow> <setting> <stage> [--debug] -- the absolute run directory for one stage",
    "find": "section.field=value ... -- the runs whose settings_diff matches every given field",
    "kill": "<workflow> <setting> <stage> -- end one run's pieces, write the killed finish row",
    "refire": "<workflow> <setting> <stage> [--piece i] [--allow-dirty] -- restart one dead piece",
    "retry": "<workflow> <setting> <stage> [--allow-dirty] -- clear markers, then launch it fresh",
    "table": "[workflow] [--out FILE] [--debug] -- the backbone x method x risk table",
    "free": "-- the free cards per host",
    "sync": "-- fold done.json and heartbeats into missing finish rows",
    "selfcheck": "-- the tree's self-consistency checks",
}


# ---------------------------------------------------------------------------
# The login-host refusal (8.6): pinned as module-level functions, so later
# tickets' acceptance can address them without running the whole program.
# ---------------------------------------------------------------------------


def normalize_host(name: str, hosts: list[dict]) -> str:
    """A host name or alias normalised to the hosts: entry's own name column (errata, 3.4)."""
    for host in hosts:
        if name == host.get("name") or name == host.get("alias"):
            return host["name"]
    return name


def require_login_host(current: str, hosts: list[dict], login_host: str) -> None:
    """Refuse, naming both sides normalised, unless the current machine is login_host (8.6)."""
    norm_current = normalize_host(current, hosts)
    norm_login = normalize_host(login_host, hosts)
    if norm_current != norm_login:
        raise SystemExit(
            f"run.py: refuses to run on {current!r} (normalises to {norm_current!r}); "
            f"only {login_host!r} (normalises to {norm_login!r}) may run this")


# ---------------------------------------------------------------------------
# Config readers: lazy and cached, exactly like jobs/registry.py's and
# jobs/launch.py's own, so importing this module needs neither constants/
# nor models/table.yaml to exist yet.
# ---------------------------------------------------------------------------

_OUTPUTS_CFG: dict | None = None
_DATASETS_CFG: dict | None = None


def _outputs_config() -> dict:
    global _OUTPUTS_CFG
    if _OUTPUTS_CFG is None:
        with open(ROOT / "constants" / "path_outputs.yaml") as f:
            _OUTPUTS_CFG = yaml.safe_load(f)
    return _OUTPUTS_CFG


def _datasets_config() -> dict:
    global _DATASETS_CFG
    if _DATASETS_CFG is None:
        with open(ROOT / "constants" / "path_datasets.yaml") as f:
            _DATASETS_CFG = yaml.safe_load(f)
    return _DATASETS_CFG


def _hosts_config() -> list[dict]:
    return _outputs_config().get("hosts", [])


def _login_host() -> str:
    return _outputs_config()["login_host"]


def _venvs_config() -> dict:
    return _datasets_config().get("venvs", {})


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _parse_t(t: str) -> float:
    return datetime.strptime(t, "%Y-%m-%d %H:%M").timestamp()


def _read_json(path: Path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _sha1_of(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _elapsed(run_id: str) -> float:
    """Seconds since the newest open start row for run_id, 0.0 when there is none (8.2's elapsed_s)."""
    for row in registry.open_runs():
        if row.get("run_id") == run_id:
            return time.time() - _parse_t(row["t"])
    return 0.0


# ---------------------------------------------------------------------------
# --help (8.6, ticket 16/17's C8): the walk forms, then one subcommand per
# line, indented by exactly two spaces, the name first -- pinned because
# tickets 16 and 17 recover the set with ^\s{2,}([a-z][a-z0-9_-]*).
# ---------------------------------------------------------------------------


def _usage_text() -> str:
    lines = [
        "usage: run.py <workflow> <setting> [<setting> ...] [--debug] [--allow-dirty] "
        "[section.field=value ...]",
        "",
        "The first word is one of the ten reserved subcommands below, or else the stem of a",
        "workflow file under experimental_settings/.",
        "",
        "subcommands:",
    ]
    for name in RESERVED_SUBCOMMANDS:
        pad = " " * (12 - len(name))
        lines.append(f"  {name}{pad}{_SUBCOMMAND_ONE_LINE[name]}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Small shared helpers: loading one setting, checking a stage name.
# ---------------------------------------------------------------------------


def _check_stage_name(stage: str) -> None:
    if stage not in schema.STAGES:
        sys.exit(f"run.py: {stage!r} is not a stage; one of {sorted(schema.STAGES)}")


def _load_one(workflow_name: str, setting_name: str, *, debug: bool, overrides: dict | None = None):
    """schema.load, refused when the workflow file is missing, the setting fails to load, or the name is an un-suffixed sweep parent (ambiguous for a single-setting subcommand)."""
    workflow_file = ROOT / "experimental_settings" / f"{workflow_name}.yaml"
    if not workflow_file.exists():
        sys.exit(f"run.py: {workflow_file} does not exist")
    try:
        cfgs = schema.load(workflow_file, setting_name, debug=debug, overrides=overrides or {})
    except schema.SchemaError as ex:
        sys.exit(f"run.py: {ex}")
    if len(cfgs) != 1:
        sys.exit(
            f"run.py: {setting_name!r} under {workflow_name!r} names {len(cfgs)} settings; "
            "name a sweep child directly")
    return cfgs[0]


# ---------------------------------------------------------------------------
# The README parser (D1; also what ticket 15's selfcheck uses).
# ---------------------------------------------------------------------------

_README_ENTRY_RE = re.compile(r"^(\S+) — (.+)$")
_README_LABEL_RE = re.compile(r"^  (imports|used by|reads|writes|read by|offers|venv):\s*(.*)$")


def readme_entries(path) -> dict[str, dict[str, str]]:
    """Parse README.md's 'path — sentence' entries and their indented label lines (contracts 0.1's five-line format): path -> {label: value}."""
    text = Path(path).read_text()
    entries: dict[str, dict[str, str]] = {}
    current = None
    for line in text.splitlines():
        m = _README_ENTRY_RE.match(line)
        if m:
            current = m.group(1)
            entries.setdefault(current, {})
            continue
        m = _README_LABEL_RE.match(line)
        if m and current is not None:
            entries[current][m.group(1)] = m.group(2)
    return entries


# ---------------------------------------------------------------------------
# ls (8.0, 8.6): edited and progress are run.py's own to compute, because
# jobs/registry.py imports nothing from this repo and cannot call schema.key
# or trajectory_record.done_pairs itself.
# ---------------------------------------------------------------------------


def _current_key(workflow_name: str, setting_name: str, stage: str, debug: bool) -> str | None:
    workflow_file = ROOT / "experimental_settings" / f"{workflow_name}.yaml"
    if not workflow_file.exists():
        return None
    try:
        cfgs = schema.load(workflow_file, setting_name, debug=debug, overrides={})
    except schema.SchemaError:
        return None
    if len(cfgs) != 1:
        return None
    try:
        return schema.key(stage, cfgs[0])
    except Exception:
        return None


def _compute_edited(rows: list[dict]) -> dict[str, bool | None]:
    """{run_id: the named setting's current key != this row's key}, None when the setting can't be reloaded (8.6's edited flag)."""
    edited: dict[str, bool | None] = {}
    cache: dict[tuple, str | None] = {}
    for row in rows:
        run_id = row.get("run_id")
        workflow_name, setting_name, stage = row.get("workflow"), row.get("setting"), row.get("stage")
        debug = bool(row.get("debug"))
        if not (run_id and workflow_name and setting_name and stage):
            continue
        cache_key = (workflow_name, setting_name, stage, debug)
        if cache_key not in cache:
            cache[cache_key] = _current_key(workflow_name, setting_name, stage, debug)
        current = cache[cache_key]
        edited[run_id] = None if current is None else (current != row.get("key"))
    return edited


def _compute_progress(rows: list[dict]) -> dict[str, tuple[int, int]]:
    """{run_id: (done, total)} for every sample/inject row, through trajectory_record.done_pairs against the row's own requested (task, seed) list (8.0's progress argument)."""
    progress: dict[str, tuple[int, int]] = {}
    for row in rows:
        stage = row.get("stage")
        if stage not in ("sample", "inject"):
            continue
        run_id = row.get("run_id")
        workflow_name, setting_name, run_dir = row.get("workflow"), row.get("setting"), row.get("dir")
        debug = bool(row.get("debug"))
        if not (run_id and workflow_name and setting_name and run_dir):
            continue
        workflow_file = ROOT / "experimental_settings" / f"{workflow_name}.yaml"
        if not workflow_file.exists():
            continue
        try:
            cfgs = schema.load(workflow_file, setting_name, debug=debug, overrides={})
            if len(cfgs) != 1:
                continue
            cfg = cfgs[0]
            section = cfg.inject if stage == "inject" else cfg.sample
            env = open_env(cfg.data.env)
            triples = requested_pairs(env, section.split, section.tasks, section.n_tasks, section.seeds)
            pairs = [(task_id, seed) for _split, task_id, seed in triples]
            done = trajectory_record.done_pairs(Path(run_dir), pairs)
            progress[run_id] = (len(done), len(pairs))
        except Exception:
            continue
    return progress


def _format_ls_row(row: dict) -> str:
    run_id = row.get("run_id") or "-"
    stage = row.get("stage") or "-"
    workflow_name = row.get("workflow") or "-"
    setting_name = row.get("setting") or "-"
    status = row.get("status") or "-"
    done, total = row.get("progress", (0, 0))
    flags = row.get("flags") or {}
    flag_str = ",".join(k for k, v in flags.items() if v) or "-"
    pieces = row.get("pieces") or []
    verdicts = ",".join(f"{p.get('index')}:{p.get('verdict')}" for p in pieces) or "-"
    return (f"{run_id}  stage={stage}  {workflow_name}/{setting_name}  status={status}  "
            f"progress={done}/{total}  flags={flag_str}  pieces={verdicts}")


def cmd_ls(rest: list[str]) -> int:
    debug = "--debug" in rest
    workflow_name = next((t for t in rest if t != "--debug"), None)
    rows = registry.find({})
    edited = _compute_edited(rows)
    progress = _compute_progress(rows)
    result = registry.ls(workflow_name, debug=debug, edited=edited, progress=progress)
    if not result:
        print("run.py ls: no runs")
        return 0
    print("run_id | stage | workflow/setting | status | progress | flags | pieces")
    for row in result:
        print(_format_ls_row(row))
    return 0


def cmd_where(rest: list[str]) -> int:
    debug = "--debug" in rest
    positional = [t for t in rest if t != "--debug"]
    if len(positional) != 3:
        sys.exit("run.py where: usage: run.py where <workflow> <setting> <stage> [--debug]")
    workflow_name, setting_name, stage = positional
    _check_stage_name(stage)
    cfg = _load_one(workflow_name, setting_name, debug=debug)
    print(schema.run_dir(stage, cfg))
    return 0


def cmd_find(rest: list[str]) -> int:
    if not rest:
        sys.exit("run.py find: usage: run.py find section.field=value ...")
    fields: dict = {}
    for tok in rest:
        if "=" not in tok:
            sys.exit(f"run.py find: {tok!r} is not section.field=value")
        key, _, value = tok.partition("=")
        fields[key] = yaml.safe_load(value)
    rows = registry.find(fields)
    if not rows:
        print("run.py find: no runs match")
        return 0
    print("run_id | stage | workflow/setting | status | commit")
    for row in rows:
        print(f"{row.get('run_id')} | {row.get('stage')} | {row.get('workflow')}/{row.get('setting')} | "
              f"{row.get('status')} | {row.get('commit')}")
    return 0


def cmd_kill(rest: list[str]) -> int:
    if len(rest) != 3:
        sys.exit("run.py kill: usage: run.py kill <workflow> <setting> <stage>")
    workflow_name, setting_name, stage = rest
    _check_stage_name(stage)
    cfg = _load_one(workflow_name, setting_name, debug=False)
    key = schema.key(stage, cfg)
    run_id = f"{stage}-{key}"
    ended = registry.kill(run_id)
    open_ids = {r["run_id"] for r in registry.open_runs()}
    if run_id in open_ids:
        with registry.lock():
            registry.append_finish(run_id, {
                "ev": "finish", "t": _now(), "run_id": run_id, "status": "killed",
                "counts": {}, "metrics": {}, "report": None, "elapsed_s": _elapsed(run_id)})
    print(f"run.py kill: ended {ended}")
    return 0


def cmd_refire(rest: list[str]) -> int:
    piece = None
    allow_dirty = False
    positional: list[str] = []
    it = iter(rest)
    for tok in it:
        if tok == "--piece":
            piece = int(next(it))
        elif tok == "--allow-dirty":
            allow_dirty = True
        else:
            positional.append(tok)
    if len(positional) != 3:
        sys.exit(
            "run.py refire: usage: run.py refire <workflow> <setting> <stage> [--piece i] [--allow-dirty]")
    workflow_name, setting_name, stage = positional
    _check_stage_name(stage)
    cfg = _load_one(workflow_name, setting_name, debug=False)
    run_dir = schema.run_dir(stage, cfg)
    if not (run_dir / "settings.yaml").exists():
        sys.exit(f"run.py refire: {run_dir} has no settings.yaml; nothing to refire")
    existing = schema.load_frozen(run_dir)
    with registry.lock():
        git = launch.git_state(run_dir, allow_dirty)
        # 3.4/2.3: a refire takes the same two launch steps a first launch takes -- git_state and
        # freeze -- and re-freezes _commit to the commit this launch cleared; it reuses whatever
        # was already resolved (an inject run's probe_temperature) rather than erasing it.
        schema.freeze(cfg, stage, run_dir, existing._resolved, git["commit"])
        pieces = launch.refire(run_dir, git, piece)
    print(f"run.py refire: restarted {pieces}")
    return 0


def _clear_continue_markers(stage: str, run_dir: Path) -> None:
    """'start fresh' (2.4): clear this stage's own completion/continue markers before a normal launch. --retry never rides on the piece command; the piece command's shape is untouched."""
    for name in ("done.json", "consumed.json"):
        p = run_dir / name
        if p.exists():
            p.unlink()
    if stage == "train":
        for name in ("train_log.jsonl", "train_done.json", "align_check.json"):
            p = run_dir / name
            if p.exists():
                p.unlink()
        last_dir = run_dir / "last"
        if last_dir.is_dir():
            shutil.rmtree(last_dir)


def cmd_retry(rest: list[str]) -> int:
    allow_dirty = "--allow-dirty" in rest
    positional = [t for t in rest if t != "--allow-dirty"]
    if len(positional) != 3:
        sys.exit("run.py retry: usage: run.py retry <workflow> <setting> <stage> [--allow-dirty]")
    workflow_name, setting_name, stage = positional
    _check_stage_name(stage)
    cfg = _load_one(workflow_name, setting_name, debug=False)
    run_dir = schema.run_dir(stage, cfg)
    _clear_continue_markers(stage, run_dir)
    _stage_step(cfg, stage, allow_dirty)
    return 0


def cmd_table(rest: list[str]) -> int:
    workflow_name = None
    out = None
    debug = False
    it = iter(rest)
    for tok in it:
        if tok == "--out":
            out = Path(next(it))
        elif tok == "--debug":
            debug = True
        else:
            workflow_name = tok
    md = method_table.table(workflow_name, out, debug=debug)
    sys.stdout.write(md)
    return 0


def cmd_free(rest: list[str]) -> int:
    for host, cards in registry.free().items():
        print(f"{host}: {cards}")
    return 0


def cmd_sync(rest: list[str]) -> int:
    synced = registry.sync()
    print(f"run.py sync: {len(synced)} run(s): {synced}")
    return 0


def cmd_selfcheck(rest: list[str]) -> int:
    raise SystemExit("selfcheck arrives in ticket 15")


# ---------------------------------------------------------------------------
# The walk (2.3, 2.4, 2.5, 3.4, 8.1, 8.2).
# ---------------------------------------------------------------------------


def _is_override_token(tok: str) -> bool:
    if "=" not in tok:
        return False
    key = tok.split("=", 1)[0]
    # A sweep child's own name also carries "=" (e.g. "name/train.lr=0.0003"), but always after a
    # "/"; an override's left-hand side is a dotted section.field with no "/" in it (5.7 step 5).
    return "/" not in key and "." in key


def _parse_walk_rest(rest: list[str]) -> tuple[list[str], bool, bool, dict[str, str]]:
    settings: list[str] = []
    debug = False
    allow_dirty = False
    overrides: dict[str, str] = {}
    for tok in rest:
        if tok == "--debug":
            debug = True
        elif tok == "--allow-dirty":
            allow_dirty = True
        elif tok.startswith("--"):
            sys.exit(f"run.py: unrecognized flag {tok!r}")
        elif _is_override_token(tok):
            key, _, value = tok.partition("=")
            overrides[key] = value  # raw text; schema.load parses it with yaml.safe_load itself
        else:
            settings.append(tok)
    return settings, debug, allow_dirty, overrides


def cmd_walk(workflow_name: str, rest: list[str]) -> int:
    workflow_file = ROOT / "experimental_settings" / f"{workflow_name}.yaml"
    if not workflow_file.exists():
        sys.exit(f"run.py: {workflow_file} does not exist")
    setting_names, debug, allow_dirty, overrides = _parse_walk_rest(rest)
    if not setting_names:
        sys.exit("run.py: at least one <setting> is required")
    for setting_name in setting_names:
        try:
            cfgs = schema.load(workflow_file, setting_name, debug=debug, overrides=overrides)
        except schema.SchemaError as ex:
            sys.exit(f"run.py: {ex}")
        for cfg in cfgs:
            _walk_one(cfg, allow_dirty)
    return 0


def _walk_one(cfg, allow_dirty: bool) -> None:
    for stage in cfg._workflow:
        outcome = _stage_step(cfg, stage, allow_dirty)
        if outcome == "stop":
            return


def _refuse_on_stale_inputs(stage: str, run_dir: Path) -> None:
    """Before a skip (2.3): refuse, naming the file and both hashes, when a consumed.json entry -- or, for sample/inject, a meta.json split_files entry -- no longer matches the file it names."""
    entries: list[dict] = []
    consumed_path = run_dir / "consumed.json"
    if consumed_path.exists():
        entries.extend(json.loads(consumed_path.read_text()))
    if stage in ("sample", "inject"):
        meta = _read_json(run_dir / "meta.json") or {}
        entries.extend(meta.get("split_files") or [])
    for entry in entries:
        path, recorded = entry.get("path"), entry.get("sha1")
        if path is None or recorded is None:
            continue
        p = Path(path)
        actual = _sha1_of(p) if p.exists() else "<missing>"
        if actual != recorded:
            sys.exit(
                f"run.py: {run_dir} is stale: {path} sha1 is now {actual}, recorded {recorded}; "
                "run `run.py retry` to rebuild")


def _record_owner(run_dir: Path, cfg) -> None:
    """A skip is an ownership event (2.3): add {workflow, setting} to meta.json's owners, under the lock."""
    entry = {"workflow": cfg._file, "setting": cfg._name}
    with registry.lock():
        meta = _read_json(run_dir / "meta.json") or {}
        owners = list(meta.get("owners") or [])
        if entry not in owners:
            owners.append(entry)
            registry.write_meta(run_dir, owners=owners)


def _backfill_finish_row(run_id: str, run_dir: Path) -> None:
    """A directory whose done.json exists with no finish row gets one, on the walk that first sees it (8.2)."""
    open_ids = {r["run_id"] for r in registry.open_runs()}
    if run_id not in open_ids:
        return
    done = _read_json(run_dir / "done.json") or {}
    with registry.lock():
        registry.append_finish(run_id, {
            "ev": "finish", "t": _now(), "run_id": run_id, "status": "ok",
            "counts": done.get("counts", {}), "metrics": done.get("metrics", {}),
            "report": done.get("report"), "elapsed_s": _elapsed(run_id)})


def _finalize_pair_stage(stage: str, run_dir: Path, key: str, pairs: list[tuple[str, int]]) -> None:
    """Completeness reached (2.3): write done.json, tear the services down, append the ok finish row."""
    frozen = schema.load_frozen(run_dir)
    tasks = len({task_id for task_id, _seed in pairs})
    seeds = len({seed for _task_id, seed in pairs})
    counts = {"records": len(pairs), "tasks": tasks, "seeds": seeds}
    registry.write_done(run_dir, stage=stage, key=key, commit=frozen._commit,
                         counts=counts, versions=frozen._versions, metrics={}, report=None,
                         pairs=pairs)
    launch.teardown_services(run_dir)
    run_id = f"{stage}-{key}"
    registry.append_finish(run_id, {
        "ev": "finish", "t": _now(), "run_id": run_id, "status": "ok",
        "counts": counts, "metrics": {}, "report": None, "elapsed_s": _elapsed(run_id)})


def _refuse_missing_upstream(stage: str, cfg, upstream_map: dict) -> None:
    """5.4: refuse to start a stage whose referenced run has no done.json."""
    by_name = {e["name"]: e for e in schema.STAGES[stage]["upstream"]}
    for name, key_val in upstream_map.items():
        e = by_name[name]
        debug = cfg._debug if e["source"] == "same" else False
        target_dir = schema.run_dir_of(e["stage"], key_val, debug=debug)
        if not (target_dir / "done.json").exists():
            sys.exit(f"run.py: {stage}: upstream {name!r} at {target_dir} has no done.json; run it first")


def _check_inject_probe_methods(cfg, upstream_map: dict) -> None:
    """Errata '5.4 / 2.1': a key:/dir: reference's stated method must match the referenced train run's frozen probe.method."""
    for field_name, ref_value, train_key_name in (
        ("inject.probe_score", cfg.inject.probe_score, "probe_score.train"),
        ("inject.probe_gen", cfg.inject.probe_gen, "probe_gen.train"),
    ):
        if not (isinstance(ref_value, dict) and "method" in ref_value):
            continue
        stated = ref_value["method"]
        train_dir = schema.run_dir_of("train", upstream_map[train_key_name], debug=False)
        frozen = schema.load_frozen(train_dir)
        actual = frozen.probe.method if frozen.probe is not None else None
        if actual != stated:
            sys.exit(
                f"run.py: {field_name}: stated method {stated!r}, the referenced train run's "
                f"frozen probe.method is {actual!r}")


def _check_inject_shared_build_key(upstream_map: dict) -> None:
    """2.5: inject.probe_score and inject.probe_gen are refused unless their two train runs share a build key."""
    score_dir = schema.run_dir_of("train", upstream_map["probe_score.train"], debug=False)
    gen_dir = schema.run_dir_of("train", upstream_map["probe_gen.train"], debug=False)
    score_build = schema.load_frozen(score_dir)._upstream.get("build")
    gen_build = schema.load_frozen(gen_dir)._upstream.get("build")
    if score_build != gen_build:
        sys.exit(
            f"run.py: inject refuses: probe_score's train run build key {score_build!r} != "
            f"probe_gen's train run build key {gen_build!r}")


def _check_inject_code_currency(upstream_map: dict) -> None:
    """2.5: inject refuses when the live code differs from the code its two probes were trained under: data/probe_input.py (off the build run), models/probe_models/base.py and each train run's own backbone module (off the train run), each against schema.module_version's current source reading."""
    for label in ("probe_score.train", "probe_gen.train"):
        train_dir = schema.run_dir_of("train", upstream_map[label], debug=False)
        train_frozen = schema.load_frozen(train_dir)
        build_key = train_frozen._upstream.get("build")
        build_dir = schema.run_dir_of("build", build_key, debug=False)
        build_frozen = schema.load_frozen(build_dir)
        family = train_frozen.models.probe_row["family"]
        backbone_mod = f"models/probe_models/{family}.py"
        checks = (
            (build_dir, "data/probe_input.py", build_frozen._versions.get("data/probe_input.py")),
            (train_dir, "models/probe_models/base.py",
             train_frozen._versions.get("models/probe_models/base.py")),
            (train_dir, backbone_mod, train_frozen._versions.get(backbone_mod)),
        )
        for src_dir, mod, recorded in checks:
            current = schema.module_version(mod)
            if recorded != current:
                sys.exit(
                    f"run.py: inject refuses: {label} ({src_dir}) recorded {mod} VERSION "
                    f"{recorded}, current source VERSION is {current}")


def _resolve_inject_temperature(upstream_map: dict) -> dict:
    """5.4: the softmax temperature is read from the referenced classifier eval's report and frozen under _resolved.probe_temperature."""
    eval_dir = schema.run_dir_of("eval", upstream_map["probe_score.eval"], debug=False)
    fields, _fires = probe_eval.read_report(eval_dir)
    return {"probe_temperature": fields["temperature"]}


def _start_cpu_stage(stage, entry, run_dir, cfg, key, run_id, git, versions, upstream_map, diff):
    """Spawn a build/eval/score process in place, inside the caller's lock hold: registry.open_runs()'s refusal first (2.5's launch gate, applied the same way jobs.launch.launch applies it for a card stage), then the process, its pid captured before the start row is appended (errata: 8.1 appends the start row inside the lock while its cpu piece entry carries a pid that exists only after the process starts)."""
    open_rows = [r for r in registry.open_runs() if r.get("run_id") == run_id]
    if open_rows:
        meta_by_run = {run_id: _read_json(run_dir / "meta.json") or {}}
        beats = {run_id: launch.read_beats_for_run(run_dir)}
        sessions = registry.live_sessions()
        refusal = launch.gate_open_row(open_rows, meta_by_run, sessions, time.time(), beats)
        if refusal is not None:
            sys.exit(f"run.py: {refusal}")

    python = _venvs_config()["probe"]
    module = entry["program"]
    argv_cmd = [python, "-m", module, "--run-dir", str(run_dir)]
    proc = subprocess.Popen(argv_cmd, cwd=str(ROOT))
    piece_entry = {
        "index": 0, "kind": "cpu", "host": _login_host(), "gpus": "",
        "session": None, "pid": proc.pid, "log": None, "port": None,
        "endpoint_file": None, "agent_replica": None, "venv": "probe",
        "cmd": " ".join(argv_cmd),
    }
    start_row = {
        "ev": "start", "t": _now(), "run_id": run_id, "stage": stage, "key": key,
        "dir": str(run_dir), "workflow": cfg._file, "setting": cfg._name,
        "parent": None, "swept": None, "debug": cfg._debug,
        "upstream": upstream_map, "versions": versions, "diff": diff,
        "commit": git["commit"], "branch": git["branch"], "dirty": git["dirty"],
        "dirty_count": git["dirty_count"], "dirty_files": git["dirty_files"],
        "host": _login_host(), "pieces": [piece_entry], "status": "launching",
    }
    registry.append_start(start_row)
    launches_entry = {
        "t": _now(), "host": _login_host(), "commit": git["commit"], "branch": git["branch"],
        "dirty_count": git["dirty_count"], "dirty_files": git["dirty_files"],
        "cards": {}, "pieces": [0], "cmd": {"0": piece_entry["cmd"]},
    }
    registry.write_meta(run_dir, pieces=[piece_entry], launches=[launches_entry])
    return proc


def _stage_step(cfg, stage: str, allow_dirty: bool) -> str:
    """One stage of the walk (2.3-2.5, 8.1-8.2): the skip test, the partial-piece check, the launch. Returns 'continue' or 'stop'."""
    key = schema.key(stage, cfg)
    run_dir = schema.run_dir(stage, cfg)
    run_id = f"{stage}-{key}"
    entry = schema.STAGES[stage]
    done_path = run_dir / "done.json"

    pairs: list[tuple[str, int]] | None = None
    if stage in ("sample", "inject"):
        section = cfg.inject if stage == "inject" else cfg.sample
        env = open_env(cfg.data.env)
        triples = requested_pairs(env, section.split, section.tasks, section.n_tasks, section.seeds)
        pairs = [(task_id, seed) for _split, task_id, seed in triples]
        done = trajectory_record.done_pairs(run_dir, pairs)
        fully_done = len(done) == len(pairs)
    else:
        fully_done = done_path.exists()

    if fully_done:
        _refuse_on_stale_inputs(stage, run_dir)
        _record_owner(run_dir, cfg)
        if stage in ("sample", "inject") and not done_path.exists():
            _finalize_pair_stage(stage, run_dir, key, pairs)
        else:
            _backfill_finish_row(run_id, run_dir)
        return "continue"

    if stage in ("sample", "inject"):
        meta = _read_json(run_dir / "meta.json") or {}
        work_pieces = [p for p in (meta.get("pieces") or []) if p.get("kind") in ("loop", "train")]
        if work_pieces:
            sessions = registry.live_sessions()
            # release() only deletes a claim whose owner session is not in `sessions`
            # (data/trajectory_record.py), so this always runs, whether or not any of
            # this run's own pieces are still alive: a live piece's own claims are
            # untouched, and a fully-dead run's stale claims are freed so the relaunch
            # below can re-claim them instead of skipping them forever.
            released = trajectory_record.release(
                run_dir, sessions, registry.DEFAULTS["launch_timeout_s"])
            if released:
                print(f"run.py: released {len(released)} dead claim(s) under {run_dir}")
            if any(launch.piece_alive(p, sessions) for p in work_pieces):
                print(f"run.py: {run_dir} has a live piece; launching nothing")
                return "stop"

    upstream_map = schema.upstream(stage, cfg)
    _refuse_missing_upstream(stage, cfg, upstream_map)
    resolved: dict = {}
    if stage == "inject":
        _check_inject_probe_methods(cfg, upstream_map)
        _check_inject_shared_build_key(upstream_map)
        _check_inject_code_currency(upstream_map)
        resolved = _resolve_inject_temperature(upstream_map)

    proc = None
    with registry.lock():
        git = launch.git_state(run_dir, allow_dirty)
        schema.freeze(cfg, stage, run_dir, resolved, git["commit"])
        versions = schema.versions_of(stage, cfg)
        diff = schema.fields_of(stage, cfg)
        registry.write_meta(run_dir, stage=stage, key=key, dir=str(run_dir), versions=versions,
                             upstream=upstream_map, diff=diff, debug=cfg._debug)

        if entry["cards"]:
            outcome, _pieces = launch.launch(stage, cfg, run_dir, resolved, git)
        else:
            outcome = None
            proc = _start_cpu_stage(stage, entry, run_dir, cfg, key, run_id, git, versions,
                                     upstream_map, diff)

    if entry["cards"]:
        if outcome != "up":
            with registry.lock():
                registry.append_finish(run_id, {
                    "ev": "finish", "t": _now(), "run_id": run_id, "status": "launch_failed",
                    "counts": {}, "metrics": {}, "report": None, "elapsed_s": _elapsed(run_id)})
            return "stop"
        print(f"run.py: launched {run_id}; monitor with `run.py ls {cfg._file}`")
        return "stop"

    rc = proc.wait()
    if rc != 0:
        with registry.lock():
            registry.append_finish(run_id, {
                "ev": "finish", "t": _now(), "run_id": run_id, "status": "failed",
                "counts": {}, "metrics": {}, "report": None, "elapsed_s": _elapsed(run_id)})
        return "stop"
    done = _read_json(done_path) or {}
    registry.append_finish(run_id, {
        "ev": "finish", "t": _now(), "run_id": run_id, "status": "ok",
        "counts": done.get("counts", {}), "metrics": done.get("metrics", {}),
        "report": done.get("report"), "elapsed_s": _elapsed(run_id)})
    return "continue"


# ---------------------------------------------------------------------------
# main.
# ---------------------------------------------------------------------------

_SUBCOMMANDS = {
    "ls": cmd_ls,
    "where": cmd_where,
    "find": cmd_find,
    "kill": cmd_kill,
    "refire": cmd_refire,
    "retry": cmd_retry,
    "table": cmd_table,
    "free": cmd_free,
    "sync": cmd_sync,
    "selfcheck": cmd_selfcheck,
}


def main(argv: list[str] | None = None) -> int:
    require_login_host(socket.gethostname(), _hosts_config(), _login_host())

    argv = list(sys.argv[1:]) if argv is None else list(argv)
    if not argv or argv[0] in ("-h", "--help"):
        sys.stdout.write(_usage_text())
        return 0

    cmd, rest = argv[0], argv[1:]
    if cmd in _SUBCOMMANDS:
        return _SUBCOMMANDS[cmd](rest)
    return cmd_walk(cmd, rest)


if __name__ == "__main__":
    sys.exit(main())
