#!/usr/bin/env python3
"""Fallback rails.gpu executor (tables/config.json `_fallback_rule`,
issues/10-fallback-freeze.md).

    launch.py LAUNCH_ORDER.json [--project-root P]

Runs a launch order's `argv` exactly once, sequentially:

1. Dirty-tree gate on the launch order's `workdir` (`git status
   --porcelain`, filtered through `dirty_exempt_globs`) -- any non-exempt
   change refuses the launch outright, no override flag (spec §5, tables/
   config.json dirty_exempt_globs). Not a git repo at all (self-test
   sandboxes with no git) -> no gate.
2. `expected_commit` check against `git_head(project_root)` with any
   `-dirty` suffix stripped before comparing (the tree may still carry
   exempt-only dirt at this point).
3. Minimal `ops/jobs.json` bookkeeping (plan.md §C5 shape): register
   state=running before running, finalize state=done/failed/timeout +
   finished_at after.
4. `argv` run via `_lib.run_argv` with a timeout of `expected_runtime_s *
   runtime_factor`; stdout+stderr land in `<artifact_dir>/attempt<N>.log`.
5. `<artifact_dir>/RUNMETA.json` is written fresh on the first attempt and
   only ever appended to after that -- attempt_no increments, and every
   earlier attempt's argv/log_path/resources are left untouched byte for
   byte (rows.json runmeta.attempts).

`argv` is the sole authoritative execution body (spec §5): this script
never re-derives it from `registry_task`, and never retries, swaps cards,
or probes resources on its own -- that is a real rails.gpu adapter's job,
not this bare-minimum stand-in's (tables/config.json _fallback_rule:
"除此之外不复刻任何高级功能").
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import _lib  # noqa: E402

_EXIT_REFUSE = 3
_EXIT_TIMEOUT = 1


def _project_root(args) -> Path:
    if args.project_root:
        return Path(args.project_root)
    found = _lib.find_project_root()
    return found if found is not None else Path.cwd()


def _porcelain_paths(output: str) -> list:
    """Paths out of `git status --porcelain` output (relative to the repo
    root, regardless of the cwd git was run from). Renames ("R  old ->
    new") are reported by their new path."""
    paths = []
    for line in output.splitlines():
        if not line:
            continue
        rest = line[3:]
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1]
        paths.append(rest.strip().strip('"'))
    return paths


def _dirty_files(workdir: Path, exempt_globs) -> list:
    code, out, _err, _elapsed = _lib.run_argv(["git", "status", "--porcelain"], cwd=str(workdir))
    if code != 0:
        return []  # not a git repo at all -- no gate (self-test sandbox)
    paths = _porcelain_paths(out)
    if not exempt_globs:
        return paths
    return [p for p in paths if not any(fnmatch.fnmatch(p, glob) for glob in exempt_globs)]


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    os.replace(tmp, path)


def run(args) -> int:
    order_path = Path(args.launch_order)
    try:
        order = json.loads(order_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"launch: failed to read launch order {order_path}: {exc}", file=sys.stderr)
        return 2

    root = _project_root(args)
    cfg = _lib.load_config(root)

    workdir = root / order["workdir"]
    dirty = _dirty_files(workdir, cfg.get("dirty_exempt_globs"))
    if dirty:
        print("refuse to launch: dirty tree; escalate to deploy layer", file=sys.stderr)
        return _EXIT_REFUSE

    head = _lib.git_head(root)
    base = head[: -len("-dirty")] if head.endswith("-dirty") else head
    expected_commit = order["expected_commit"]
    if base != expected_commit:
        print(
            f"refuse to launch: expected_commit mismatch (expected {expected_commit!r}, "
            f"got {base!r}); escalate to deploy layer",
            file=sys.stderr,
        )
        return _EXIT_REFUSE

    artifact_dir = root / order["artifact_dir"]
    artifact_dir.mkdir(parents=True, exist_ok=True)
    runmeta_file = artifact_dir / "RUNMETA.json"

    existing_runmeta = _load_json(runmeta_file) or None
    attempt_no = len(existing_runmeta["attempts"]) + 1 if existing_runmeta else 1

    log_rel = str(Path(order["artifact_dir"]) / f"attempt{attempt_no}.log")
    log_path = artifact_dir / f"attempt{attempt_no}.log"

    jobs_path = Path(cfg.ledger_path("jobs"))
    launch_order_ref = str(args.launch_order)

    with _lib.locked(jobs_path):
        jobs = _load_json(jobs_path)
        jobs[order["run_id"]] = {
            "launch_order_ref": launch_order_ref,
            "state": "running",
            "started_at": _lib.now_iso(),
            "finished_at": None,
            "log_path": log_rel,
        }
        _save_json(jobs_path, jobs)

    started_at = _lib.now_iso()
    runtime_factor = cfg.get("runtime_factor")
    timeout = order["expected_runtime_s"] * runtime_factor
    exit_code, stdout, stderr, _elapsed = _lib.run_argv(
        order["argv"], cwd=str(workdir), timeout=timeout,
    )
    finished_at = _lib.now_iso()

    log_text = stdout
    if stderr:
        log_text += "\n--- stderr ---\n" + stderr
    log_path.write_text(log_text, encoding="utf-8")

    if exit_code is None:
        state = "timeout"
        process_exit = _EXIT_TIMEOUT
    elif exit_code == 0:
        state = "done"
        process_exit = 0
    else:
        state = "failed"
        process_exit = exit_code

    attempt = {
        "attempt_no": attempt_no,
        "argv": order["argv"],
        "exit_code": exit_code,
        "log_path": log_rel,
        "resources": order.get("resources", {}),
        "started_at": started_at,
        "finished_at": finished_at,
    }

    if existing_runmeta is None:
        runmeta = {
            "commit": head,
            "argv": order["argv"],
            "dirty_files": [],
            "launch_order_ref": launch_order_ref,
            "attempts": [attempt],
            "env_name": order.get("env_name"),
            "outputs": [],
        }
    else:
        runmeta = existing_runmeta
        runmeta["attempts"].append(attempt)
    _save_json(runmeta_file, runmeta)

    with _lib.locked(jobs_path):
        jobs = _load_json(jobs_path)
        entry = jobs.get(order["run_id"], {})
        entry["state"] = state
        entry["finished_at"] = finished_at
        jobs[order["run_id"]] = entry
        _save_json(jobs_path, jobs)

    return process_exit


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Fallback rails.gpu launch executor.")
    parser.add_argument("launch_order")
    parser.add_argument("--project-root", dest="project_root", default=None)
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
