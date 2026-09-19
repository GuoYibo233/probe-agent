"""The one command: walk a named setting's stages (sample through score), or run one of the ten reserved subcommands (ls, where, find, kill, refire, retry, table, free, sync, selfcheck)."""
# venv: probe
from __future__ import annotations

import ast
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
# selfcheck's three parsers (ticket 15; contracts 0.1, 3.3): imports_of reads
# the real import graph with ast, and literal_of / literal_keys_of read a
# module-level literal the same way schema.py's loader does, but as a
# standalone reader that never raises past run.py's own message. A caller
# that wants a reader failure to stop only its own check, not the whole run,
# catches the SystemExit these readers raise around each call, and prefixes
# the message with its own check number -- the readers name the file and the
# name, and leave the prefix to the caller.
#
# Every path these readers take is relative to ROOT, so selfcheck reads the
# same tree whatever the shell's working directory is; an absolute path
# passes through ROOT / path unchanged, which is what ticket 15's D2 fixtures
# in a temp directory rely on.
# ---------------------------------------------------------------------------


def _parse(path) -> ast.Module:
    """The module at path, parsed with ast -- the one reader every selfcheck ast pass goes through.

    A file that does not parse is a selfcheck problem like any other: this refuses with the same
    SystemExit shape literal_of raises, naming the file and the syntax error's line, so the
    caller's own `except SystemExit` turns it into one problem line instead of a traceback.
    """
    source_path = ROOT / path
    try:
        return ast.parse(source_path.read_text(), filename=str(source_path))
    except SyntaxError as ex:
        raise SystemExit(f"{path}: does not parse ({ex.msg}, line {ex.lineno})") from ex


def _dotted_to_relpath(name: str) -> str | None:
    """The repo file a dotted module name names, as a path relative to ROOT, or None when it names no repo file (imports_of's rule 1)."""
    candidate = name.replace(".", "/") + ".py"
    if (ROOT / candidate).is_file():
        return candidate
    candidate = name.replace(".", "/") + "/__init__.py"
    if (ROOT / candidate).is_file():
        return candidate
    return None


def imports_of(path) -> set[str]:
    """The dotted module names this file imports, parsed with ast -- every Import and ImportFrom, including the ones inside a function body, never an import of the module itself.

    An ImportFrom's `module.name` is joined into one dotted name only when that join is a repo
    file (rule 1 of check 2's normalisation): `from data import training_data` yields
    `data.training_data` because `data/training_data.py` exists, but `from dataclasses import
    dataclass` yields the bare `dataclasses`, because neither `dataclasses/dataclass.py` nor
    `dataclasses/dataclass/__init__.py` is in this repo. Without the rule a `from <package>
    import <module>` import of a repo file would be invisible to the graph.
    """
    tree = _parse(path)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                for alias in node.names:
                    names.add(alias.name)
                continue
            for alias in node.names:
                joined = f"{node.module}.{alias.name}"
                names.add(joined if _dotted_to_relpath(joined) else node.module)
    return names


def _repo_imports(path) -> set[str]:
    """`imports_of(path)` restricted to repo files, as relative path strings (check 2's 'imports_of restricted to repo files')."""
    out: set[str] = set()
    for name in imports_of(path):
        rel = _dotted_to_relpath(name)
        if rel:
            out.add(rel)
    return out


def _column_zero_assign_values(path, name: str) -> list:
    """Every column-zero ast.Assign of `name` in the module at path, as its value node -- literal_of and literal_keys_of match ast.Assign only, never ast.AnnAssign (3.3's literal rule; check 5's SCHEMA/DEFAULTS/REQUIRED are the annotated exception, read separately)."""
    tree = _parse(path)
    matches = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and node.col_offset == 0:
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    matches.append(node.value)
    return matches


def literal_of(path, name: str):
    """The one column-zero ast.Assign of `name` in the module at path, ast.literal_eval'd -- never an import.

    Refuses, naming the file and the name, on zero matches, more than one match, and a value
    ast.literal_eval refuses (contracts 3.3): each of the three is a failure, reported the same
    way every other selfcheck problem is. `FORMATS` in agent/injected_text_formats.py is a dict
    of Format(...) calls, which is exactly the value this function must refuse rather than
    fall back on -- literal_keys_of is its reader.
    """
    matches = _column_zero_assign_values(path, name)
    if not matches:
        raise SystemExit(f"{path}: no column-zero assignment to {name!r}")
    if len(matches) > 1:
        raise SystemExit(
            f"{path}: {len(matches)} column-zero assignments to {name!r}, expected exactly one")
    try:
        return ast.literal_eval(matches[0])
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError) as ex:
        raise SystemExit(f"{path}: {name!r} has a value that is not a literal ({ex})") from ex


def literal_keys_of(path, name: str) -> list:
    """The keys of the one column-zero ast.Dict display assigned to `name` in the module at path, ast.literal_eval'd one at a time, in source order.

    For a name whose value ast.literal_eval refuses whole -- FORMATS' Format(...) calls -- but
    whose keys are themselves literals. Refuses, naming the file and the name, on zero matches,
    more than one match, a value that is not a dict display, and a key ast.literal_eval refuses.
    """
    matches = _column_zero_assign_values(path, name)
    if not matches:
        raise SystemExit(f"{path}: no column-zero assignment to {name!r}")
    if len(matches) > 1:
        raise SystemExit(
            f"{path}: {len(matches)} column-zero assignments to {name!r}, expected exactly one")
    value = matches[0]
    if not isinstance(value, ast.Dict):
        raise SystemExit(f"{path}: {name!r} is not a dict display, cannot read its keys")
    keys = []
    for key_node in value.keys:
        try:
            keys.append(ast.literal_eval(key_node))
        except (ValueError, TypeError, SyntaxError) as ex:
            raise SystemExit(f"{path}: {name!r} has a non-literal key ({ex})") from ex
    return keys


# ---------------------------------------------------------------------------
# ls (8.0, 8.6): edited and progress are run.py's own to compute, because
# jobs/registry.py imports nothing from this repo and cannot call schema.key
# or trajectory_record.done_pairs itself.
# ---------------------------------------------------------------------------


def _current_setting(workflow_name: str, setting_name: str, debug: bool):
    """The named setting as it loads today, or None when its file, its name or its load is gone (8.6's edited and behind flags compare a row against it)."""
    workflow_file = ROOT / "experimental_settings" / f"{workflow_name}.yaml"
    if not workflow_file.exists():
        return None
    try:
        cfgs = schema.load(workflow_file, setting_name, debug=debug, overrides={})
    except schema.SchemaError:
        return None
    if len(cfgs) == 1:
        return cfgs[0]
    return None


def _current_key_and_versions(stage: str, cfg) -> tuple[str | None, dict]:
    """Today's key for this stage of this setting, and the `versions` block that keys it.

    Both readers parse every module the stage's row lists, so this is what one ledger row
    costs to judge and it is read once per (setting, stage, debug) rather than once per row
    (8.6's `ls` runs over the whole ledger). An unreadable setting gives `None` and an empty
    block, which is the blank `edited` column of 8.6.
    """
    if cfg is None:
        return None, {}
    try:
        current_key = schema.key(stage, cfg)
    except Exception:
        current_key = None
    try:
        current_versions = schema.versions_of(stage, cfg)
    except Exception:
        current_versions = {}
    return current_key, current_versions


def _behind_versions(recorded: dict, current: dict) -> bool:
    """Whether any module the `recorded` block names now carries a higher VERSION than the block records (8.6's behind: 'a folded module's VERSION is ahead of the directory's').

    `current` comes from `schema.versions_of`, the same reader that wrote the row's own
    `versions` block, so a table entry (`<path>#<TABLE>.<method>`) and a stand-in
    (`<path>@<stage>`) are compared the way the stage table spells them, and this file parses
    no module itself (ticket 14's comment of 2026-09-18).
    """
    return any(name in current and recorded[name] < current[name] for name in recorded)


def _stale_sentence(stage: str, recorded: dict) -> str:
    """Which file's `VERSION` bump made this run stale, and that bump's own `why` (ticket 14's comment of 2026-09-18, errata '3.3 / 8.6').

    A stage's key folds each listed file's effective version for that stage — the highest
    version whose `VERSION_HISTORY` entry calls that stage stale — so a file whose effective
    version now stands above the version this run recorded is a file whose bump moved this
    run's key. A `<path>@<other>` stand-in is stale when either stage's entries say so, the
    way `key` folds it; a `<path>#<TABLE>.<method>` entry carries no version history and is
    left out.
    """
    parts = []
    for name, version in recorded.items():
        if "#" in name:
            continue
        path, _, stands_for = name.partition("@")
        try:
            effective = schema.effective_version(path, stage)
            if stands_for:
                effective = max(effective, schema.effective_version(path, stands_for))
            history = schema.version_history(path)
        except Exception:
            continue
        if effective > version:
            why = (history.get(effective) or {}).get("why", "")
            parts.append(f'{path} VERSION {effective}: "{why}"')
    return "; ".join(parts)


def _inputs_changed(entries) -> bool:
    """Whether any recorded `{path, sha1}` entry no longer matches the file it names — the comparison behind 8.6's consumed and split flags, and the one the walk's skip gate makes (2.3)."""
    for entry in entries or []:
        path, recorded = entry.get("path"), entry.get("sha1")
        if path is None or recorded is None:
            continue
        p = Path(path)
        actual = _sha1_of(p) if p.exists() else "<missing>"
        if actual != recorded:
            return True
    return False


def _has_pinned_reference(run_dir: Path) -> bool:
    """Whether the run's frozen setting gives one of the four reference fields in the pinned `key:`/`dir:` form, which skipped the inheritance check and the shared-build-key gate (5.4, 8.6's pinned flag)."""
    if not (run_dir / "settings.yaml").exists():
        return False
    try:
        frozen = schema.load_frozen(run_dir)
    except (schema.SchemaError, OSError, yaml.YAMLError):
        return False
    for dotted in schema.REF_FIELDS:
        section_name, _, field_name = dotted.partition(".")
        section = getattr(frozen, section_name, None)
        value = getattr(section, field_name, None) if section is not None else None
        if isinstance(value, dict):
            return True
    return False


def _compute_row_flags(rows: list[dict]) -> dict[str, dict]:
    """Per run_id, the five flags of 8.6 that `run.py` owns because `jobs/registry.py` imports nothing from this repo — `edited`, `behind`, `consumed`, `split`, `pinned` — plus the sentence naming the bump that made a stale run stale.

    `edited` is the named setting's current key against this directory's; `behind` is a
    recorded `VERSION` below the file's current one while that key still matches, which is
    the run that stayed usable across the bumps between (ticket 14's comment of 2026-09-18);
    a run whose key moved is stale instead, and `stale` carries which file's bump did it.

    A ledger holds many rows per setting, and every reading of a setting or of a module's
    `VERSION` re-reads and re-parses source text, so each of the three source readings is
    done once and reused: the setting per (workflow, setting, debug), the key and the
    versions block per stage of it, and the stale sentence per (stage, recorded versions),
    which is all it is a function of.
    """
    out: dict[str, dict] = {}
    settings: dict[tuple, object] = {}
    readings: dict[tuple, tuple[str | None, dict]] = {}
    sentences: dict[tuple, str] = {}
    for row in rows:
        run_id = row.get("run_id")
        workflow_name, setting_name, stage = row.get("workflow"), row.get("setting"), row.get("stage")
        debug = bool(row.get("debug"))
        if not (run_id and workflow_name and setting_name and stage):
            continue
        setting_id = (workflow_name, setting_name, debug)
        if setting_id not in settings:
            settings[setting_id] = _current_setting(workflow_name, setting_name, debug)
        stage_id = setting_id + (stage,)
        if stage_id not in readings:
            readings[stage_id] = _current_key_and_versions(stage, settings[setting_id])
        current, current_versions = readings[stage_id]
        recorded = row.get("versions") or {}
        if current is None:
            edited, behind, stale = None, None, ""
        else:
            key_matches = current == row.get("key")
            edited = not key_matches
            behind = key_matches and _behind_versions(recorded, current_versions)
            if key_matches:
                stale = ""
            else:
                sentence_id = (stage, tuple(sorted(recorded.items())))
                if sentence_id not in sentences:
                    sentences[sentence_id] = _stale_sentence(stage, recorded)
                stale = sentences[sentence_id]
        run_dir = Path(row["dir"]) if row.get("dir") else None
        consumed = split = pinned = False
        if run_dir is not None:
            consumed = _inputs_changed(_read_json(run_dir / "consumed.json"))
            split = _inputs_changed((_read_json(run_dir / "meta.json") or {}).get("split_files"))
            pinned = _has_pinned_reference(run_dir)
        out[run_id] = {"edited": edited, "behind": behind, "consumed": consumed,
                       "split": split, "pinned": pinned, "stale": stale}
    return out


def _requested_pairs_of(workflow_name: str, setting_name: str, stage: str, debug: bool) -> list | None:
    """The (task, seed) pairs this stage of this setting asks for, or None when the setting or its environment cannot be read.

    Reading them loads the setting and opens the environment, which is why the caller reads
    them once per (setting, stage) and counts every row of that setting against the one list.
    """
    try:
        cfg = _current_setting(workflow_name, setting_name, debug)
        if cfg is None:
            return None
        section = cfg.inject if stage == "inject" else cfg.sample
        env = open_env(cfg.data.env)
        triples = requested_pairs(env, section.split, section.tasks, section.n_tasks, section.seeds)
    except Exception:
        return None
    return [(task_id, seed) for _split, task_id, seed in triples]


def _compute_progress(rows: list[dict]) -> dict[str, tuple[int, int]]:
    """{run_id: (done, total)} for every sample/inject row, through trajectory_record.done_pairs against the row's own requested (task, seed) list (8.0's progress argument).

    The request is a function of the setting and the stage, so it is read once per
    (setting, stage, debug) over the whole ledger; `done_pairs` reads the row's own directory
    and stays per row.
    """
    progress: dict[str, tuple[int, int]] = {}
    requested: dict[tuple, list | None] = {}
    for row in rows:
        stage = row.get("stage")
        if stage not in ("sample", "inject"):
            continue
        run_id = row.get("run_id")
        workflow_name, setting_name, run_dir = row.get("workflow"), row.get("setting"), row.get("dir")
        debug = bool(row.get("debug"))
        if not (run_id and workflow_name and setting_name and run_dir):
            continue
        request_id = (workflow_name, setting_name, debug, stage)
        if request_id not in requested:
            requested[request_id] = _requested_pairs_of(workflow_name, setting_name, stage, debug)
        pairs = requested[request_id]
        if pairs is None:
            continue
        try:
            done = trajectory_record.done_pairs(Path(run_dir), pairs)
        except Exception:
            continue
        progress[run_id] = (len(done), len(pairs))
    return progress


def _format_piece(piece: dict) -> str:
    """One piece on the ls line: its index and verdict, the session it runs in and the host it runs on, and the cards it holds (8.6)."""
    text = f"{piece.get('index')}:{piece.get('verdict')}"
    host, session = piece.get("host"), piece.get("session")
    if session:
        text += f"@{host}:{session}"
    elif host:
        text += f"@{host}"
    gpus = piece.get("gpus")
    if gpus:
        text += f" cards={gpus}"
    return text


def _format_ls_row(row: dict, stale: str = "") -> str:
    """8.6's folded line: run_id, stage, the names that own it, status, progress as done/total unit with a rate, the heartbeat's age, the eight flags, and per piece its verdict, session, host and cards."""
    run_id = row.get("run_id") or "-"
    stage = row.get("stage") or "-"
    workflow_name = row.get("workflow") or "-"
    setting_name = row.get("setting") or "-"
    status = row.get("status") or "-"
    done, total = row.get("progress", (0, 0))
    # The unit comes from the beats (8.4), so a run that has not beaten yet has none to print.
    unit = f" {row['unit']}" if row.get("unit") else ""
    rate = row.get("recent_rate")
    rate_str = f"{rate:.3g}/s" if rate is not None else "-"
    beat_age = row.get("beat_age_s")
    beat_str = f"{beat_age:.0f}s" if beat_age is not None else "-"
    flags = row.get("flags") or {}
    flag_str = ",".join(k for k, v in flags.items() if v) or "-"
    pieces = row.get("pieces") or []
    piece_str = "; ".join(_format_piece(p) for p in pieces) or "-"
    line = (f"{run_id}  stage={stage}  {workflow_name}/{setting_name}  status={status}  "
            f"progress={done}/{total}{unit}  rate={rate_str}  beat={beat_str}  "
            f"flags={flag_str}  pieces={piece_str}")
    if stale:
        line += f"  stale={stale}"
    return line


def cmd_ls(rest: list[str]) -> int:
    debug = "--debug" in rest
    workflow_name = next((t for t in rest if t != "--debug"), None)
    rows = registry.find({})
    row_flags = _compute_row_flags(rows)
    progress = _compute_progress(rows)
    result = registry.ls(
        workflow_name, debug=debug, progress=progress,
        edited={rid: f["edited"] for rid, f in row_flags.items()},
        behind={rid: f["behind"] for rid, f in row_flags.items()},
        consumed={rid: f["consumed"] for rid, f in row_flags.items()},
        split={rid: f["split"] for rid, f in row_flags.items()},
        pinned={rid: f["pinned"] for rid, f in row_flags.items()})
    if not result:
        print("run.py ls: no runs")
        return 0
    print("run_id | stage | workflow/setting | status | progress | rate | heartbeat | flags | pieces")
    for row in result:
        print(_format_ls_row(row, (row_flags.get(row.get("run_id")) or {}).get("stale", "")))
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


# ---------------------------------------------------------------------------
# selfcheck (8.6, ticket 15): the tree's self-consistency checks, in the
# contract's order. Every _check_N function returns a list of problem lines;
# cmd_selfcheck prints them all and exits 1 on any, so one file's failure
# never hides another's.
# ---------------------------------------------------------------------------

PY_ROOTS = ("constants", "experimental_settings", "data", "models", "agent", "train", "eval", "jobs")


def _tree_python_files() -> list[str]:
    """Every .py file under run.py and the tree's code roots, as paths relative to ROOT (check 1)."""
    files = ["run.py"]
    for root_name in PY_ROOTS:
        for p in sorted((ROOT / root_name).rglob("*.py")):
            files.append(str(p.relative_to(ROOT)))
    return sorted(files)


def _stems_of(dirname: str) -> set[str]:
    """The .py file stems directly under dirname, __init__ excluded (check 3's set comparisons)."""
    return {p.stem for p in (ROOT / dirname).glob("*.py") if p.stem != "__init__"}


def _table_rows() -> dict:
    with open(ROOT / "models" / "table.yaml") as f:
        return yaml.safe_load(f)


def _families(role: str) -> list[str]:
    """The distinct `family` values of models/table.yaml's rows of this role, sorted (checks 3, 4, 7, 10)."""
    return sorted({row["family"] for row in _table_rows().values() if row.get("role") == role})


def _safe_literal(problems: list[str], check: str, path, name: str):
    """literal_of(path, name), appending its SystemExit message to problems and returning None on a refusal, so one bad file never stops the rest of a check's loop."""
    try:
        return literal_of(path, name)
    except SystemExit as ex:
        problems.append(f"{check}: {ex}")
        return None


def _safe_parse(problems: list[str], check: str, path):
    """_parse(path), appending its SystemExit message to problems and returning None on a file that does not parse, so one unparsable file never stops the rest of a check's loop (the shape _safe_literal uses for a literal)."""
    try:
        return _parse(path)
    except SystemExit as ex:
        problems.append(f"{check}: {ex}")
        return None


# --- check 1: the README's file list against the tree -----------------------


# Contracts 0.1's five-line format: every .py entry of README section 2 carries these five
# labels, in this order. Check 1 requires each of them to be there and to carry a value, for
# three reasons: check 10 reads venv: and drops the file from its import proof in silence when
# that line is gone, so check 1 is the only place that line is required; check 2 reads imports:
# and used by: and reports a missing one by name itself, so check 1 repeats that report for a
# .py entry rather than being its only source; and reads: and writes:, which no check reads,
# are required here because a line nobody requires rots.
README_PY_LABELS = ("imports", "used by", "reads", "writes", "venv")


def _check_1(entries: dict, tree_files: list[str]) -> list[str]:
    problems = []
    for f in tree_files:
        if f not in entries:
            problems.append(f"check 1: {f} is a .py file in the tree with no README entry")
    for name, entry in entries.items():
        if not (ROOT / name).exists():
            problems.append(f"check 1: README entry {name!r} names a path that does not exist")
        if name.endswith(".py"):
            for label in README_PY_LABELS:
                if (entry.get(label) or "").strip() == "":
                    problems.append(
                        f"check 1: README entry {name!r} carries no {label}: line "
                        "(contracts 0.1's five-line format)")
    return problems


# --- check 2: every annotation line against the real import graph -----------


_BRACKET_RE = re.compile(r"\[[^\[\]]*\]")
_BRACE_RE = re.compile(r"\{([^{}]*)\}")


def _drop_bracket_groups(text: str) -> str:
    """Drop every bracketed third-party list, whole (rule 1: '[polars, numpy]' and the like)."""
    return _BRACKET_RE.sub("", text)


def _split_top_level(text: str) -> list[str]:
    """Split text on every ',' and ';' that sits outside every (), [] and {} (rule 2 step 2)."""
    fragments = []
    depth = 0
    current: list[str] = []
    for ch in text:
        if ch in "([{":
            depth += 1
            current.append(ch)
        elif ch in ")]}":
            depth -= 1
            current.append(ch)
        elif ch in ",;" and depth == 0:
            fragments.append("".join(current))
            current = []
        else:
            current.append(ch)
    fragments.append("".join(current))
    return fragments


def _drop_parenthetical(fragment: str) -> tuple[str, str | None]:
    """Drop a fragment's parenthetical, from its first '(' to its last ')' (rule 2 step 3): (path text, parenthetical text or None)."""
    start = fragment.find("(")
    if start == -1:
        return fragment.strip(), None
    end = fragment.rfind(")")
    if end == -1 or end < start:
        return fragment.strip(), None
    return fragment[:start].strip(), fragment[start + 1:end].strip()


def _expand_braces(path_text: str) -> list[str]:
    """Expand one brace alternation into one path per alternative (rule 2 step 4); a fragment with none is itself the only entry."""
    m = _BRACE_RE.search(path_text)
    if not m:
        return [path_text]
    return [path_text[:m.start()] + alt.strip() + path_text[m.end():] for alt in m.group(1).split(",")]


def _is_path_token(fragment: str) -> bool:
    """Whether a fragment is a bare path token -- one whitespace-free word ending in .py or .yaml -- and so names a repo file rather than prose (rule 2 step 5's prose rule, the other way round)."""
    return len(fragment.split()) == 1 and fragment.endswith((".py", ".yaml"))


def _parse_annotation(raw: str) -> tuple[set[str], list[tuple[str, str]], list[str]]:
    """One README imports:/used by: value, parsed into (plain entries, by-name fragments, dead path tokens) per check 2's five-step rule (rule 2); the caller has already handled the 'none (program)' and '(as their package)' whole-line spellings of rule 3.

    A plain entry survives steps 1-5 as exactly a repo file path. A by-name fragment's
    parenthetical starts 'by name' (rule 3) and is returned separately, dropped from the plain
    equality either way. A fragment that is a bare path token yet names no repo file is a dead
    name -- what a rename leaves behind -- and is returned as the third value for the caller to
    report; prose fragments, which are several words, stay out of all three.
    """
    normal: set[str] = set()
    by_name: list[tuple[str, str]] = []
    dead: list[str] = []
    for fragment in _split_top_level(_drop_bracket_groups(raw)):
        path_text, paren_text = _drop_parenthetical(fragment)
        if not path_text:
            continue
        if paren_text is not None and paren_text.startswith("by name"):
            by_name.append((path_text, paren_text))
            continue
        for candidate in (c.strip() for c in _expand_braces(path_text)):
            if candidate == "":
                continue
            if (ROOT / candidate).exists():
                normal.add(candidate)
            elif _is_path_token(candidate):
                dead.append(candidate)
    return normal, by_name, dead


def _dynamic_import_prefix(annotated_file: str) -> str:
    """The dotted package a by-name importer must name to reach the annotated file: `models/agent_models/gptoss.py` -> `models.agent_models.`, and a repo-root file -> `` (rule 3).

    A root-level module's dotted name is the stem alone, so its package part is empty and the
    prefix is the empty string; every other file's prefix is its directory, dotted, with the
    separating dot on the end.
    """
    parts = Path(annotated_file).parent.parts
    return ".".join(parts) + "." if parts else ""


def _has_dynamic_import_of(path, prefix: str, exact: str = "") -> bool:
    """Whether the module at path holds an importlib.import_module(...) call that names the target: an f-string whose leading constant starts with the required leading text, or the plain string `exact` (rule 3's by-name test).

    The required leading text is what makes the test bite: a call that imports something else
    entirely is the breakage this rule exists to catch, and ast cannot see the edge any other
    way. It is the target's package prefix wherever the target sits inside a package. A
    repo-root target has an empty package prefix, which every string starts with, so there the
    required leading text is the module's own dotted name, `exact`. A placeholder fragment
    (models/probe_models/<backbone>.py) names no one module, so it passes no `exact` and its
    non-empty package prefix answers for it alone.
    """
    lead = prefix or exact
    tree = _parse(path)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_import_module = ((isinstance(func, ast.Attribute) and func.attr == "import_module")
                             or (isinstance(func, ast.Name) and func.id == "import_module"))
        if not (is_import_module and node.args):
            continue
        arg = node.args[0]
        if isinstance(arg, ast.JoinedStr) and arg.values:
            first = arg.values[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str) and first.value.startswith(lead):
                return True
        if exact and isinstance(arg, ast.Constant) and arg.value == exact:
            return True
    return False


def _has_main_block(path) -> bool:
    """Whether the module at path holds an `if __name__ == ...:` block at any depth (rule 3's 'none (program)' test)."""
    tree = _parse(path)
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
            left = node.test.left
            if isinstance(left, ast.Name) and left.id == "__name__":
                return True
    return False


def _check_by_name_fragments(current_file: str, label: str, fragments: list[tuple[str, str]],
                             unreadable: set[str]) -> list[str]:
    """Rule 3's by-name spelling: a fragment naming a real file is checked for existence and a dynamic-import call; the one placeholder spelling (models/probe_models/base.py's own <backbone>.py) is checked by its own f-string rule instead.

    The label says which of the two files holds the importlib call: on an `imports:` line the
    annotated file is the importer and the fragment is the module it names, on a `used by:` line
    the fragment is the importer and the annotated file is the module it names. `unreadable` is
    check 2's set of files that do not parse; a fragment whose importer sits in it is passed over,
    because that file's own parse-failure line is already among the problems.
    """
    problems = []
    for path_text, _paren in fragments:
        if "<" in path_text:
            if label == "imports":
                prefix = _dynamic_import_prefix(path_text)
                if not _has_dynamic_import_of(current_file, prefix):
                    problems.append(
                        f"check 2: {current_file}: no importlib.import_module f-string call beginning "
                        f"{prefix!r} for its by-name import of {path_text}")
            else:
                problems.append(f"check 2: {current_file} {label}: unrecognised by-name placeholder {path_text!r}")
            continue
        if not (ROOT / path_text).is_file():
            problems.append(f"check 2: {current_file} {label}: by-name entry {path_text} does not exist")
            continue
        if label == "imports":
            importer, imported = current_file, path_text
            subject = f"{current_file} holds no"
            tail = f" for by-name entry {path_text}"
        else:
            importer, imported = path_text, current_file
            subject = f"by-name entry {path_text} holds no"
            tail = ""
        if importer in unreadable:
            continue
        prefix = _dynamic_import_prefix(imported)
        module = _module_name(imported)
        if not _has_dynamic_import_of(importer, prefix, module):
            # a module inside a package is named by its package prefix, a repo-root module by its own name
            required = f"{prefix}<module>" if prefix else module
            problems.append(
                f"check 2: {current_file} {label}: {subject} "
                f"importlib.import_module call naming {required}{tail}")
    return problems


def _check_package_marker(current_file: str, label: str, raw: str) -> list[str]:
    """Rule 3's '(as their package)' spelling: the whole used by: line's named set must equal the .py files of the marker's own directory, __init__.py excluded."""
    if label != "used by":
        return [f"check 2: {current_file}: '(as their package)' on an {label}: line"]
    text = raw[:raw.rfind("(as their package)")]
    named = {t.strip() for t in text.split(",") if t.strip()}
    directory = Path(current_file).parent
    real = {str(p.relative_to(ROOT)) for p in sorted((ROOT / directory).glob("*.py")) if p.name != "__init__.py"}
    if named != real:
        return [f"check 2: {current_file} used by: package marker names {sorted(named)}, "
                f"directory {directory} holds {sorted(real)}"]
    return []


def _check_2(tree_files: list[str], entries: dict) -> list[str]:
    problems: list[str] = []
    imports_map: dict[str, set[str]] = {}
    unreadable: set[str] = set()
    for f in tree_files:
        try:
            imports_map[f] = _repo_imports(f)
        except SystemExit as ex:
            problems.append(f"check 2: {ex}")
            imports_map[f] = set()
            unreadable.add(f)
    used_by_map: dict[str, set[str]] = {f: set() for f in tree_files}
    for f, imps in imports_map.items():
        for target in imps:
            used_by_map.setdefault(target, set()).add(f)
    graphs = {"imports": imports_map, "used by": used_by_map}

    for f in tree_files:
        if f in unreadable:
            continue       # its own line is already above; its annotation lines say nothing more
        entry = entries.get(f, {})
        for label, graph in graphs.items():
            raw = entry.get(label)
            if raw is None:
                problems.append(f"check 2: {f} has no {label}: line")
                continue
            raw = raw.strip()
            try:
                if raw == "none (program)":
                    if label != "used by":
                        problems.append(f"check 2: {f}: 'none (program)' on an {label}: line")
                        continue
                    if graph.get(f):
                        problems.append(
                            f"check 2: {f}: used by: none (program), but imported by {sorted(graph[f])}")
                    if not _has_main_block(f):
                        problems.append(f"check 2: {f}: used by: none (program), but has no __main__ block")
                    continue
                if raw.endswith("(as their package)"):
                    problems.extend(_check_package_marker(f, label, raw))
                    continue
                normal, by_name, dead = _parse_annotation(raw)
                actual = graph.get(f, set())
                if normal != actual:
                    problems.append(
                        f"check 2: {f} {label}: README names {sorted(normal)}, the graph gives {sorted(actual)}")
                for candidate in dead:
                    problems.append(f"check 2: {f} {label}: names {candidate}, which is not a repo file")
                problems.extend(_check_by_name_fragments(f, label, by_name, unreadable))
            except SystemExit as ex:
                problems.append(f"check 2: {ex}")
    return problems


# --- check 3: every axis literal against the files behind it ----------------


def _check_3() -> list[str]:
    problems: list[str] = []
    axes = schema.AXES

    try:
        fmt_keys = tuple(literal_keys_of("agent/injected_text_formats.py", "FORMATS"))
    except SystemExit as ex:
        problems.append(f"check 3: {ex}")
        fmt_keys = None
    if fmt_keys is not None and tuple(axes["inject.format"]) != fmt_keys:
        problems.append(
            f"check 3: schema.AXES['inject.format'] {tuple(axes['inject.format'])} != "
            f"agent/injected_text_formats.py FORMATS keys {fmt_keys}")

    arms = _safe_literal(problems, "check 3", "agent/step_with_probe.py", "ARMS")
    if arms is not None and tuple(axes["inject.arm"]) != tuple(arms):
        problems.append(
            f"check 3: schema.AXES['inject.arm'] {tuple(axes['inject.arm'])} != "
            f"agent/step_with_probe.py ARMS {tuple(arms)}")

    probe_kind = _safe_literal(problems, "check 3", "eval/utils/probe_eval.py", "PROBE_KIND")
    match_version = _safe_literal(problems, "check 3", "eval/utils/probe_eval.py", "MATCH_VERSION")
    for m in axes["probe.method"]:
        if probe_kind is not None and m not in probe_kind:
            problems.append(f"check 3: schema.AXES['probe.method'] value {m!r} is not a key of PROBE_KIND")
        if match_version is not None and m not in match_version:
            problems.append(f"check 3: schema.AXES['probe.method'] value {m!r} is not a key of MATCH_VERSION")
    method_stems = _stems_of("train/methods")
    if set(axes["probe.method"]) != method_stems:
        problems.append(
            f"check 3: schema.AXES['probe.method'] {set(axes['probe.method'])} != "
            f"train/methods/ stems {method_stems}")

    env_stems = _stems_of("data/environments")
    if set(axes["data.env"]) != env_stems:
        problems.append(
            f"check 3: schema.AXES['data.env'] {set(axes['data.env'])} != data/environments/ stems {env_stems}")

    instructions_union: set = set()
    split_role_union: set = set()
    for env in sorted(env_stems):
        path = f"data/environments/{env}.py"
        instr = _safe_literal(problems, "check 3", path, "INSTRUCTIONS")
        if instr is not None:
            instructions_union |= set(instr)
        split_role = _safe_literal(problems, "check 3", path, "SPLIT_ROLE")
        if split_role is not None:
            split_role_union |= set(split_role)
    if not set(axes["data.instructions"]) <= instructions_union:
        problems.append(
            f"check 3: schema.AXES['data.instructions'] {set(axes['data.instructions'])} is not within "
            f"the environments' INSTRUCTIONS keys {instructions_union}")
    for axis_name in ("sample.split", "inject.split"):
        if not set(axes[axis_name]) <= split_role_union:
            problems.append(
                f"check 3: schema.AXES[{axis_name!r}] {set(axes[axis_name])} is not within "
                f"the environments' SPLIT_ROLE keys {split_role_union}")

    effort_union: set = set()
    for fam in _families("agent"):
        efforts = _safe_literal(problems, "check 3", f"models/agent_models/{fam}.py", "EFFORTS")
        if efforts is not None:
            effort_union |= set(efforts)
    if not set(axes["generation.effort"]) <= effort_union:
        problems.append(
            f"check 3: schema.AXES['generation.effort'] {set(axes['generation.effort'])} is not within "
            f"the family modules' EFFORTS {effort_union}")
    return problems


# --- check 4: one VERSION per stage-table module, one literal apiece --------


def _resolve_versions_entry(entry: str) -> list[str]:
    """One `versions` tuple entry of schema.STAGES, resolved to the concrete file(s) it names: drop the @stage/#table.name tail, then expand whichever of the four templates the remaining path holds (5.2's resolution, check 4)."""
    path = entry.split("@")[0].split("#")[0]
    rows = _table_rows()
    agent_fams = sorted({r["family"] for r in rows.values() if r.get("role") == "agent"})
    probe_fams = sorted({r["family"] for r in rows.values() if r.get("role") == "probe"})
    outs = [path]
    for token, values in (
        ("{env}", schema.AXES["data.env"]),
        ("{method}", schema.AXES["probe.method"]),
        ("{probe_score_method}", schema.AXES["probe.method"]),
        ("{family}", agent_fams),
        ("{backbone}", probe_fams),
    ):
        if token in path:
            outs = [out.replace(token, v) for out in outs for v in values]
    return outs


def _stage_table_files() -> set[str]:
    named: set[str] = set()
    for row in schema.STAGES.values():
        for entry in row["versions"]:
            named |= set(_resolve_versions_entry(entry))
    return named


# The VERSION rule comment block pinned directly above every column-zero VERSION
# assignment in the 22 stage-table files (errata "3.3 / 8.6", gyb 2026-09-18):
# word-for-word identical in all of them, checked by _check_version_comment below.
_VERSION_RULE_COMMENT = (
    '# VERSION rule: read this before you edit this file (errata "3.3 / 8.6", gyb 2026-09-18).',
    "# Bump VERSION only when some existing setting would now produce a different output of a stage",
    "# that lists this file in the stage table of experimental_settings/schema.py. A new feature",
    "# behind a new setting field whose default reproduces the old behaviour, a message, a comment",
    "# or a report layout does not bump.",
    '# Every bump adds one VERSION_HISTORY entry: {<new version>: {"why": "<one sentence>",',
    '# "stale": (<stage names>)}}. "stale" names the stages (sample, build, train, eval, inject,',
    '# score) whose existing outputs can no longer be used; leave "stale" out and every stage is',
    "# stale. The key folds the highest version that made a stage stale, so a bump that leaves a",
    "# stage usable keeps that stage's run directory. When unsure, list the stage.",
)


def _version_assigns(path) -> list[ast.Assign]:
    """Every column-zero ast.Assign to VERSION in the module at path, in source order (check 4 reads their count and the one's line number)."""
    return [
        node for node in ast.walk(_parse(path))
        if isinstance(node, ast.Assign) and node.col_offset == 0
        and any(isinstance(target, ast.Name) and target.id == "VERSION" for target in node.targets)
    ]


def _version_assign_lineno(path) -> int | None:
    """The line number (1-indexed) of the one column-zero ast.Assign to VERSION in the module at path, or None when there is not exactly one -- that mismatch is already check 4's own problem, reported by _safe_literal's caller."""
    matches = _version_assigns(path)
    if len(matches) != 1:
        return None
    return matches[0].lineno


def _check_version_comment(path) -> list[str]:
    """The VERSION rule comment block sits directly above the file's VERSION assignment, word for word (errata '3.3 / 8.6', gyb 2026-09-18)."""
    problems: list[str] = []
    try:
        lineno = _version_assign_lineno(path)
    except SystemExit as ex:
        problems.append(f"check 4: {ex}")
        return problems
    if lineno is None:
        return problems
    lines = (ROOT / path).read_text().splitlines()
    start = lineno - 1 - len(_VERSION_RULE_COMMENT)
    if start < 0:
        problems.append(
            f"check 4: {path}: the VERSION rule comment block is missing directly above VERSION (line {lineno})")
        return problems
    above = tuple(lines[start:lineno - 1])
    if above != _VERSION_RULE_COMMENT:
        problems.append(
            f"check 4: {path}: the lines directly above VERSION (line {lineno}) do not match the pinned VERSION rule comment block")
    return problems


def _check_version_and_history(path: str) -> list[str]:
    """One file's VERSION rule comment (pinned text, directly above), VERSION (an int) and VERSION_HISTORY (errata '3.3 / 8.6'): keys exactly 2..VERSION, every entry's why non-empty, every stale a tuple of schema.STAGES names."""
    problems: list[str] = []
    problems.extend(_check_version_comment(path))
    version = _safe_literal(problems, "check 4", path, "VERSION")
    if version is None:
        return problems
    if isinstance(version, bool) or not isinstance(version, int):
        problems.append(f"check 4: {path}: VERSION is a {type(version).__name__}, expected an int")
        return problems
    history = _safe_literal(problems, "check 4", path, "VERSION_HISTORY")
    if history is None:
        return problems
    if not isinstance(history, dict):
        problems.append(f"check 4: {path}: VERSION_HISTORY is a {type(history).__name__}, expected a mapping")
        return problems
    expected_keys = set(range(2, version + 1))
    if set(history) != expected_keys:
        problems.append(f"check 4: {path}: VERSION_HISTORY keys {sorted(history)} != expected {sorted(expected_keys)}")
    stage_names = set(schema.STAGES)
    for entry_version, entry in history.items():
        if not isinstance(entry, dict):
            problems.append(f"check 4: {path}: VERSION_HISTORY[{entry_version}] is not a mapping")
            continue
        if not entry.get("why"):
            problems.append(f"check 4: {path}: VERSION_HISTORY[{entry_version}] has no non-empty 'why'")
        stale = entry.get("stale")
        if stale is None:
            continue
        if not isinstance(stale, tuple):
            problems.append(f"check 4: {path}: VERSION_HISTORY[{entry_version}]['stale'] is a "
                             f"{type(stale).__name__}, expected a tuple")
        elif not set(stale) <= stage_names:
            problems.append(f"check 4: {path}: VERSION_HISTORY[{entry_version}]['stale'] names "
                             f"{sorted(set(stale) - stage_names)}, not one of {sorted(stage_names)}")
    return problems


def _check_4() -> list[str]:
    problems: list[str] = []
    named = _stage_table_files()
    # The set difference runs in both directions (ticket 15 step 4): a stage-table file with no
    # VERSION is caught by the strict shape below, and a file that carries a VERSION the stage
    # table does not name is reported here, because that VERSION folds into no key -- a bump of
    # it would invalidate nothing while its pinned comment block says it invalidates runs. The
    # strict shape then holds for every versioned file (gyb's comment), named or not.
    carriers: set[str] = set()
    unreadable: set[str] = set()
    for path in _tree_python_files():
        try:
            assigns = _version_assigns(path)
        except SystemExit as ex:
            problems.append(f"check 4: {ex}")
            unreadable.add(path)
            continue
        if assigns:
            carriers.add(path)
    for path in sorted(carriers - named):
        problems.append(
            f"check 4: {path} carries a column-zero VERSION but the stage table's versions do not name it")
    for path in sorted((named | carriers) - unreadable):
        if not (ROOT / path).exists():
            problems.append(f"check 4: {path} is named by the stage table's versions but does not exist")
            continue
        problems.extend(_check_version_and_history(path))

    for method in sorted(_stems_of("train/methods")):
        path = f"train/methods/{method}.py"
        _safe_literal(problems, "check 4", path, "PROBE_KIND")
        _safe_literal(problems, "check 4", path, "CHECKPOINT_META")
    for fam in _families("agent"):
        path = f"models/agent_models/{fam}.py"
        for name in ("STOP", "EFFORTS", "DEFAULT_EFFORT", "DEFAULT_DATE"):
            _safe_literal(problems, "check 4", path, name)
    for fam in _families("probe"):
        path = f"models/probe_models/{fam}.py"
        _safe_literal(problems, "check 4", path, "LORA_TARGETS")
    for env in sorted(_stems_of("data/environments")):
        path = f"data/environments/{env}.py"
        for name in ("INSTRUCTIONS", "SPLIT_ROLE"):
            _safe_literal(problems, "check 4", path, name)
    return problems


# --- check 5: SCHEMA / DEFAULTS / REQUIRED in each format file --------------


FORMAT_FILES = ("data/trajectory_record.py", "data/training_data.py", "data/probe_output.py")


def _column_zero_ann_or_assign(tree, name: str) -> list:
    """Every column-zero ast.Assign or ast.AnnAssign whose target's bare id is `name` (check 5 matches the target's id, never ast.unparse(target), so a subscript target like DEFAULTS['n_inject'] = 0 is not a second match)."""
    matches = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and node.col_offset == 0:
            targets = node.targets
        elif isinstance(node, ast.AnnAssign) and node.col_offset == 0:
            targets = [node.target]
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and target.id == name:
                matches.append(node.value)
    return matches


def _check_5() -> list[str]:
    problems: list[str] = []
    for path in FORMAT_FILES:
        tree = _safe_parse(problems, "check 5", path)
        if tree is None:
            continue
        nodes: dict[str, object] = {}
        for name in ("SCHEMA", "DEFAULTS", "REQUIRED"):
            matches = _column_zero_ann_or_assign(tree, name)
            if len(matches) != 1:
                problems.append(
                    f"check 5: {path}: {len(matches)} column-zero bindings of {name!r}, expected exactly one")
                continue
            nodes[name] = matches[0]
        if "SCHEMA" not in nodes or "REQUIRED" not in nodes:
            continue
        schema_node = nodes["SCHEMA"]
        if not isinstance(schema_node, ast.Dict):
            problems.append(f"check 5: {path}: SCHEMA is not a dict display")
            continue
        try:
            schema_cols = {ast.literal_eval(k) for k in schema_node.keys}
        except (ValueError, TypeError, SyntaxError) as ex:
            problems.append(f"check 5: {path}: SCHEMA has a non-literal key ({ex})")
            continue
        required_node = nodes["REQUIRED"]
        if not (isinstance(required_node, ast.Call) and isinstance(required_node.func, ast.Name)
                and required_node.func.id == "frozenset" and required_node.args):
            problems.append(f"check 5: {path}: REQUIRED is not a frozenset(...) call")
            continue
        try:
            required_names = ast.literal_eval(required_node.args[0])
        except (ValueError, TypeError, SyntaxError) as ex:
            problems.append(f"check 5: {path}: REQUIRED's argument is not a literal ({ex})")
            continue
        missing = set(required_names) - schema_cols
        if missing:
            problems.append(f"check 5: {path}: REQUIRED names {sorted(missing)}, which SCHEMA does not declare")
    return problems


# --- check 6: the two PROBE_KIND declarations of a method -------------------


def _check_6() -> list[str]:
    problems: list[str] = []
    probe_kind = _safe_literal(problems, "check 6", "eval/utils/probe_eval.py", "PROBE_KIND")
    if probe_kind is None:
        return problems
    for method in sorted(_stems_of("train/methods")):
        path = f"train/methods/{method}.py"
        own = _safe_literal(problems, "check 6", path, "PROBE_KIND")
        if own is None:
            continue
        other = probe_kind.get(method)
        if own != other:
            problems.append(
                f"check 6: {path}'s PROBE_KIND {own!r} != eval/utils/probe_eval.py "
                f"PROBE_KIND[{method!r}] {other!r}")
    return problems


# --- check 7: DEFAULT_EFFORT a member of its own EFFORTS, or both empty -----


def _check_7() -> list[str]:
    problems: list[str] = []
    for fam in _families("agent"):
        path = f"models/agent_models/{fam}.py"
        # Read both literals directly, because None is a legal DEFAULT_EFFORT value and
        # _safe_literal returns None for a refusal too: routed through it, the family whose
        # EFFORTS are non-empty while DEFAULT_EFFORT is None -- the one spelling contracts 6.2
        # allows only with EFFORTS = () -- would be read as a refusal and skipped.
        try:
            efforts = literal_of(path, "EFFORTS")
            default_effort = literal_of(path, "DEFAULT_EFFORT")
        except SystemExit as ex:
            problems.append(f"check 7: {ex}")
            continue
        if not isinstance(efforts, tuple):
            problems.append(f"check 7: {path}: EFFORTS {efforts!r} is not a tuple (contracts 6.2)")
            continue
        if efforts == () and default_effort is None:
            continue
        if default_effort not in efforts:
            problems.append(f"check 7: {path}: DEFAULT_EFFORT {default_effort!r} is not in EFFORTS {efforts}")
    return problems


# --- check 8: models/table.yaml's family and weights alias ------------------


def _check_8() -> list[str]:
    problems: list[str] = []
    rows = _table_rows()
    with open(ROOT / "constants" / "path_models.yaml") as f:
        aliases = yaml.safe_load(f)
    subdir_of_role = {"agent": "agent_models", "probe": "probe_models"}
    for alias, row in rows.items():
        role = row.get("role")
        family = row.get("family")
        subdir = subdir_of_role.get(role)
        if subdir is None:
            problems.append(f"check 8: models/table.yaml[{alias!r}]: role {role!r} is not 'agent' or 'probe'")
            continue
        path = f"models/{subdir}/{family}.py"
        if not (ROOT / path).is_file():
            problems.append(
                f"check 8: models/table.yaml[{alias!r}]: family {family!r} names {path}, which does not exist")
        weights = (row.get("result") or {}).get("weights")
        if weights not in aliases:
            problems.append(
                f"check 8: models/table.yaml[{alias!r}]: result.weights {weights!r} is not an alias of "
                "constants/path_models.yaml")
    return problems


# --- check 9: no cluster-absolute path in code outside constants/ -----------


_FORBIDDEN_ROOTS = ("/" + "home/", "/" + "net/")   # split so this check's own source never matches itself


def _check_9(tree_files: list[str]) -> list[str]:
    problems: list[str] = []
    for path in tree_files:
        if path.startswith("constants/"):
            continue
        tree = _safe_parse(problems, "check 9", path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if any(root in node.value for root in _FORBIDDEN_ROOTS):
                    problems.append(
                        f"check 9: {path}: a string literal names an absolute path outside constants/: "
                        f"{node.value!r}")
    return problems


# --- check 10: any files under every venv; family modules under probe+vllm --


def _module_name(rel_path: str) -> str:
    if rel_path.endswith("/__init__.py"):
        return rel_path[: -len("/__init__.py")].replace("/", ".")
    return rel_path[:-3].replace("/", ".")


def _import_under(interpreter: str, rel_path: str) -> str | None:
    """None on a clean `import <module>` under interpreter with ROOT as cwd, else a message naming the failure's last stderr line."""
    dotted = _module_name(rel_path)
    proc = subprocess.run(
        [interpreter, "-c", f"import {dotted}"], cwd=str(ROOT), capture_output=True, text=True)
    if proc.returncode == 0:
        return None
    tail = proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else f"exit {proc.returncode}"
    return f"{rel_path}: import under {interpreter} failed: {tail}"


# The one README venv: spelling that names an interpreter by the benchmark that brings it
# rather than by a venvs: key: "the environment's (appworld today)" and its bare form.
_VENV_ENVIRONMENT_SPELLING = "the environment's"


def _venv_names_an_interpreter(venv_value: str, venvs: dict) -> bool:
    """Whether a README venv: value opens with an interpreter check 10 knows: `any`, a key of constants/path_datasets.yaml's venvs: map, or the environment's own interpreter.

    Check 10 imports a file under every interpreter when its value opens with `any`, so a value
    it cannot read -- a typo, or a venvs: key that no longer exists -- drops the file out of the
    check in silence. Requiring the value to name something keeps that from happening.
    """
    if venv_value.startswith(_VENV_ENVIRONMENT_SPELLING):
        return True
    tokens = venv_value.split()
    return bool(tokens) and (tokens[0] == "any" or tokens[0] in venvs)


def _check_10(entries: dict) -> list[str]:
    problems: list[str] = []
    venvs = _venvs_config()
    for path, entry in entries.items():
        if not path.endswith(".py"):
            continue
        venv_value = (entry.get("venv") or "").strip()
        if venv_value == "":
            continue                     # check 1 reports the missing venv: line
        if not _venv_names_an_interpreter(venv_value, venvs):
            problems.append(
                f"check 10: {path}: venv: {venv_value!r} names no interpreter: expected 'any', "
                f"one of {sorted(venvs)}, or {_VENV_ENVIRONMENT_SPELLING!r}")
            continue
        if not venv_value.startswith("any"):
            continue
        for interp in venvs.values():
            msg = _import_under(interp, path)
            if msg:
                problems.append(f"check 10: {msg}")
    for fam in _families("agent"):
        path = f"models/agent_models/{fam}.py"
        for name in ("probe", "vllm"):
            interp = venvs.get(name)
            if interp is None:
                problems.append(f"check 10: constants/path_datasets.yaml's venvs: map has no {name!r} entry")
                continue
            msg = _import_under(interp, path)
            if msg:
                problems.append(f"check 10: {msg}")
    return problems


# --- check 11: no workflow file's stem is a reserved subcommand name --------


def _check_11() -> list[str]:
    problems: list[str] = []
    for path in sorted((ROOT / "experimental_settings").glob("*.yaml")):
        if path.stem in RESERVED_SUBCOMMANDS:
            problems.append(
                f"check 11: experimental_settings/{path.name}: stem {path.stem!r} is a reserved subcommand name")
    return problems


def cmd_selfcheck(rest: list[str]) -> int:
    entries = readme_entries(ROOT / "README.md")
    tree_files = _tree_python_files()
    problems: list[str] = []
    # A check that raises becomes a problem line of its own, so the other ten still run and the
    # count still prints: an edit that a check cannot read -- a renamed axis, a file that does
    # not parse -- is a problem to report, not a reason to stop reporting.
    checks = (
        (1, lambda: _check_1(entries, tree_files)),
        (2, lambda: _check_2(tree_files, entries)),
        (3, _check_3),
        (4, _check_4),
        (5, _check_5),
        (6, _check_6),
        (7, _check_7),
        (8, _check_8),
        (9, lambda: _check_9(tree_files)),
        (10, lambda: _check_10(entries)),
        (11, _check_11),
    )
    for number, check in checks:
        try:
            problems += check()
        except SystemExit as ex:
            problems.append(f"check {number}: {ex}")
        except Exception as ex:
            problems.append(f"check {number} raised: {type(ex).__name__}: {ex}")
    for line in problems:
        print(line)
    print(f"selfcheck: {len(tree_files)} python files, {len(problems)} problems")
    return 1 if problems else 0


# ---------------------------------------------------------------------------
# The walk (2.3, 2.4, 2.5, 3.4, 8.1, 8.2).
# ---------------------------------------------------------------------------

# 2.3's continue column and 2.4: `eval` and `score` always recompute inside their key -- a
# rerun overwrites its own directory, and each recomputation gets its own finish row (8.2).
# They cost seconds, and the failure this prevents is a metric fix that never runs because a
# finished directory was reused. Ticket 14's step 2 sentence "every other stage skips on the
# presence of done.json" is 2.3's general rule; the stage table's own row for these two names
# them and wins.
ALWAYS_RECOMPUTE = ("eval", "score")


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


def _owners_with(run_dir: Path, cfg) -> list[dict]:
    """This directory's owners list with {workflow, setting} in it: 8.3's owners holds every setting that has run into or reused the directory. Read under the caller's lock hold."""
    meta = _read_json(run_dir / "meta.json") or {}
    owners = list(meta.get("owners") or [])
    entry = {"workflow": cfg._file, "setting": cfg._name}
    if entry not in owners:
        owners.append(entry)
    return owners


def _record_owner(run_dir: Path, cfg) -> None:
    """A skip is an ownership event (2.3): add {workflow, setting} to meta.json's owners, under the lock, on the walk that first brings this setting to the directory."""
    with registry.lock():
        stored = list((_read_json(run_dir / "meta.json") or {}).get("owners") or [])
        owners = _owners_with(run_dir, cfg)
        if owners != stored:
            registry.write_meta(run_dir, owners=owners)


def _fold_stage_extra(run_dir: Path, done: dict) -> None:
    """8.3 and 1.3: a stage writes its own `stage_extra` — train puts the class order there — into its `done.json`, and `run.py` folds it into `meta.json` on the walk that sees that file, under the lock, so `meta.json` keeps exactly two writers and the eval stage reads the train run's labels from it."""
    extra = done.get("stage_extra")
    if extra:
        with registry.lock():
            registry.write_meta(run_dir, stage_extra=extra)


def _backfill_finish_row(run_id: str, run_dir: Path) -> None:
    """A directory whose done.json exists with no finish row gets one, on the walk that first sees it (8.2).

    8.2's other rule — a stage that always recomputes gets a new finish row per recomputation —
    is held by the walk itself: `eval` and `score` never skip (2.4), so `run.py` runs each
    recomputation in place and appends that run's own `ok` row when the process exits zero.
    """
    open_ids = {r["run_id"] for r in registry.open_runs()}
    if run_id not in open_ids:
        return
    done = _read_json(run_dir / "done.json") or {}
    with registry.lock():
        registry.append_finish(run_id, {
            "ev": "finish", "t": _now(), "run_id": run_id, "status": "ok",
            "counts": done.get("counts", {}), "metrics": done.get("metrics", {}),
            "report": done.get("report"), "elapsed_s": _elapsed(run_id)})


def _certifies_request(done: dict | None, pairs: list[tuple[str, int]]) -> bool:
    """Whether this directory's done.json already certifies every requested pair (2.3).

    One `sample` or `inject` directory serves several requests, and a request widened after an
    earlier one finished is completed again: `done.json` is rewritten with the wider `pairs`
    list, the run's service pieces are ended and a new finish row is appended. So the test that
    tells a completed request from one still to certify is the recorded `pairs` list, not the
    presence of the file.
    """
    if done is None:
        return False
    recorded = {(p[0], p[1]) for p in done.get("pairs") or [] if len(p) == 2}
    return set(pairs) <= recorded


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


def _reference_is_pinned(cfg, source: str) -> bool:
    """Whether the setting states this upstream's reference in the pinned key:/dir: form (5.4): a name is a string, a pinned reference is a mapping."""
    dotted = source[len("ref:"):]
    section_name, _, field_name = dotted.partition(".")
    section = getattr(cfg, section_name, None)
    value = getattr(section, field_name, None) if section is not None else None
    return isinstance(value, dict)


def _pinned_run_dir(stage: str, key_val: str) -> Path | None:
    """The run directory a pinned key names, or None when neither root holds it.

    A run's `--debug` flag is part of its own key payload (3.3), so a pinned `key:`/`dir:`
    reference — a key computed elsewhere, not from the setting being walked — names a
    directory under whichever of the two roots that run was written in. The one that answers
    is the directory whose frozen `settings.yaml` records this very key; a directory made
    before this scheme carries no `settings.yaml` (5.4's reason for the `dir:` form), so the
    one that exists stands in for it.
    """
    candidates = [schema.run_dir_of(stage, key_val, debug=flag) for flag in (False, True)]
    for candidate in candidates:
        if (candidate / "settings.yaml").exists() and schema.load_frozen(candidate)._key == key_val:
            return candidate
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def _upstream_dirs(stage: str, cfg, upstream_map: dict) -> dict[str, Path | None]:
    """Where each of this stage's upstream runs lives (3.4, 5.4).

    A `same`-source upstream is keyed from this very setting, so it lives under this walk's own
    root — under `<root>/debug/` for a `--debug` walk. A name-form reference is loaded by the
    schema with `debug=False`, so its key is the non-debug one and its run lives under the real
    root. A pinned reference carries a key whose payload holds its own debug flag, so the root
    it lives under is the key's, not the walk's: errata '3.4 / 9(c)#8' pins the debug keys the
    construction plan's `--debug` walk produced into `inject.yaml`'s three references, and that
    walk has to find them.
    """
    by_name = {e["name"]: e for e in schema.STAGES[stage]["upstream"]}
    dirs: dict[str, Path | None] = {}
    for name, key_val in upstream_map.items():
        entry = by_name[name]
        if entry["source"] == "same":
            dirs[name] = schema.run_dir_of(entry["stage"], key_val, debug=cfg._debug)
        elif _reference_is_pinned(cfg, entry["source"]):
            dirs[name] = _pinned_run_dir(entry["stage"], key_val)
        else:
            dirs[name] = schema.run_dir_of(entry["stage"], key_val, debug=False)
    return dirs


def _refuse_missing_upstream(stage: str, upstream_map: dict, upstream_dirs: dict) -> None:
    """5.4: refuse to start a stage whose referenced run has no done.json."""
    by_name = {e["name"]: e for e in schema.STAGES[stage]["upstream"]}
    for name, target_dir in upstream_dirs.items():
        if target_dir is None:
            key_val = upstream_map[name]
            candidates = " or ".join(
                str(schema.run_dir_of(by_name[name]["stage"], key_val, debug=flag))
                for flag in (False, True))
            sys.exit(f"run.py: {stage}: upstream {name!r} is pinned to key {key_val}, which is "
                     f"neither {candidates}; run it first")
        if not (target_dir / "done.json").exists():
            sys.exit(f"run.py: {stage}: upstream {name!r} at {target_dir} has no done.json; run it first")


def _check_inject_probe_methods(cfg, upstream_dirs: dict) -> None:
    """Errata '5.4 / 2.1': a key:/dir: reference's stated method must match the referenced train run's frozen probe.method."""
    for field_name, ref_value, train_key_name in (
        ("inject.probe_score", cfg.inject.probe_score, "probe_score.train"),
        ("inject.probe_gen", cfg.inject.probe_gen, "probe_gen.train"),
    ):
        if not (isinstance(ref_value, dict) and "method" in ref_value):
            continue
        stated = ref_value["method"]
        frozen = schema.load_frozen(upstream_dirs[train_key_name])
        actual = frozen.probe.method if frozen.probe is not None else None
        if actual != stated:
            sys.exit(
                f"run.py: {field_name}: stated method {stated!r}, the referenced train run's "
                f"frozen probe.method is {actual!r}")


def _check_inject_shared_build_key(upstream_dirs: dict) -> None:
    """2.5: inject.probe_score and inject.probe_gen are refused unless their two train runs share a build key."""
    score_build = schema.load_frozen(upstream_dirs["probe_score.train"])._upstream.get("build")
    gen_build = schema.load_frozen(upstream_dirs["probe_gen.train"])._upstream.get("build")
    if score_build != gen_build:
        sys.exit(
            f"run.py: inject refuses: probe_score's train run build key {score_build!r} != "
            f"probe_gen's train run build key {gen_build!r}")


def _check_inject_code_currency(upstream_dirs: dict) -> None:
    """2.5: inject refuses when the live code differs from the code its two probes were trained under: data/probe_input.py (off the build run), models/probe_models/base.py and each train run's own backbone module (off the train run), each against schema.module_version's current source reading."""
    for label in ("probe_score.train", "probe_gen.train"):
        train_dir = upstream_dirs[label]
        train_frozen = schema.load_frozen(train_dir)
        build_key = train_frozen._upstream.get("build")
        # The build run of a train run lives under the root that train run was written in: a
        # debug train run's `build` key is a debug key (3.3), and its own frozen settings say
        # which root it belongs to.
        build_dir = schema.run_dir_of("build", build_key, debug=train_frozen._debug)
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


def _resolve_inject_temperature(upstream_dirs: dict) -> dict:
    """5.4: the softmax temperature is read from the referenced classifier eval's report and frozen under _resolved.probe_temperature."""
    fields, _fires = probe_eval.read_report(upstream_dirs["probe_score.eval"])
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
    elif stage in ALWAYS_RECOMPUTE:
        fully_done = False
    else:
        fully_done = done_path.exists()

    if fully_done:
        _refuse_on_stale_inputs(stage, run_dir)
        _record_owner(run_dir, cfg)
        done_doc = _read_json(done_path)
        # A pair stage is certified by the request its done.json records, every other stage by
        # the presence of that file, which is what the skip test above already read (2.3).
        if stage in ("sample", "inject"):
            certified = _certifies_request(done_doc, pairs)
        else:
            certified = True
        if certified:
            _fold_stage_extra(run_dir, done_doc or {})
            _backfill_finish_row(run_id, run_dir)
        else:
            _finalize_pair_stage(stage, run_dir, key, pairs)
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
    upstream_dirs = _upstream_dirs(stage, cfg, upstream_map)
    _refuse_missing_upstream(stage, upstream_map, upstream_dirs)
    resolved: dict = {}
    if stage == "inject":
        _check_inject_probe_methods(cfg, upstream_dirs)
        _check_inject_shared_build_key(upstream_dirs)
        _check_inject_code_currency(upstream_dirs)
        resolved = _resolve_inject_temperature(upstream_dirs)

    proc = None
    with registry.lock():
        git = launch.git_state(run_dir, allow_dirty)
        schema.freeze(cfg, stage, run_dir, resolved, git["commit"])
        versions = schema.versions_of(stage, cfg)
        diff = schema.fields_of(stage, cfg)
        # `owners` holds every setting that has run into or reused this directory (8.3), and a
        # stage that always recomputes never takes the skip that records one, so a launch
        # records its own setting here.
        registry.write_meta(run_dir, stage=stage, key=key, dir=str(run_dir), versions=versions,
                             upstream=upstream_map, diff=diff, debug=cfg._debug,
                             owners=_owners_with(run_dir, cfg))

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
    _fold_stage_extra(run_dir, done)
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
