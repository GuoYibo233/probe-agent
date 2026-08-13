#!/usr/bin/env python3
"""Fallback plain-row entry point for runs.jsonl (tables/config.json
`_fallback_rule`, issues/10-fallback-freeze.md, spec §5 "普通实验经发射单
metrics_cmd").

    record.py --launch-order PATH [--status S]

Reads the launch order at PATH and its `<artifact_dir>/RUNMETA.json`
(missing -> exit 2). `status` is `--status` verbatim if given, else
ok/failed derived from the last attempt's exit code.

status=ok additionally runs the launch order's `metrics_cmd` (no shell);
its stdout's last line must be `{"metrics": [...]}` with a non-empty array
(tables/rows.json structured_output_contract) -- anything else (parse
failure, missing key, empty or non-array `metrics`) refuses with no row
recorded (spec §9, R8 escalation). One row per metric item; a non-ok status
writes a single row with metric_name/value/n null (schema conditional
allows this -- runs.normal.schema.json).

Every row for this run_id shares the run-level fields listed in
tables/rows.json runs_row_normal._run_level_fields. All rows this
invocation produces are schema-validated and appended inside one hold of
runs.jsonl's lock (same `<path>.lock` convention as `ledger.py
runs-append`) -- either every row lands, or none does.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import _lib  # noqa: E402

# rows.json runs_row_normal._run_level_fields, verbatim list.
_RUN_LEVEL_FIELDS = (
    "status", "output_dir", "runmeta_path", "seed", "dataset_version",
    "batch_id", "arm", "quick", "commit", "elapsed_s", "gpu_count",
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _elapsed_s(attempt: dict) -> int:
    started = datetime.fromisoformat(attempt["started_at"])
    finished = datetime.fromisoformat(attempt["finished_at"])
    return int(round((finished - started).total_seconds()))


def _run_level_row(order: dict, run_id: str, status: str, elapsed_s: int, gpu_count) -> dict:
    return {
        "run_id": run_id,
        "status": status,
        "output_dir": order["artifact_dir"],
        "runmeta_path": str(Path(order["artifact_dir"]) / "RUNMETA.json"),
        "seed": order["seed"],
        "dataset_version": order["dataset_version"],
        "batch_id": order["batch_id"],
        "arm": order["arm"],
        "quick": order["quick"],
        "principle_id": None,
        "commit": None,
        "elapsed_s": elapsed_s,
        "gpu_count": gpu_count,
        "recorded_at": _lib.now_iso(),
        "schema_version": 1,
    }


def run(args) -> int:
    order_path = Path(args.launch_order)
    try:
        order = _read_json(order_path)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"record: failed to read launch order {order_path}: {exc}", file=sys.stderr)
        return 2

    root = _lib.find_project_root() or Path.cwd()
    artifact_dir = root / order["artifact_dir"]
    runmeta_file = artifact_dir / "RUNMETA.json"
    if not runmeta_file.exists():
        print(f"record: RUNMETA not found: {runmeta_file}", file=sys.stderr)
        return 2
    try:
        runmeta = _read_json(runmeta_file)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"record: failed to read {runmeta_file}: {exc}", file=sys.stderr)
        return 2

    attempts = runmeta.get("attempts") or []
    if not attempts:
        print(f"record: RUNMETA has no attempts: {runmeta_file}", file=sys.stderr)
        return 2
    last_attempt = attempts[-1]

    if args.status:
        status = args.status
    else:
        status = "ok" if last_attempt.get("exit_code") == 0 else "failed"

    run_id = order["run_id"]
    elapsed_s = _elapsed_s(last_attempt)
    resources = order.get("resources") or {}
    gpu_count = resources.get("gpus")
    base = _run_level_row(order, run_id, status, elapsed_s, gpu_count)

    if status == "ok":
        argv = _lib.split_cmd(order["metrics_cmd"], "launch_order", "metrics_cmd")
        _exit_code, stdout, _stderr, _elapsed = _lib.run_argv(argv, cwd=root)
        parsed = _lib.last_json_line(stdout)
        metrics = parsed.get("metrics") if isinstance(parsed, dict) else None
        if not isinstance(metrics, list) or not metrics:
            print(
                "refuse: metrics output invalid; no row recorded; escalate per R8",
                file=sys.stderr,
            )
            return 2

        rows = []
        for item in metrics:
            row = dict(base)
            row["metric_name"] = item.get("metric_name")
            row["value"] = item.get("value")
            row["n"] = item.get("n")
            item_filter = item.get("filter")
            row["filter"] = item_filter if item_filter is not None else order.get("filter")
            rows.append(row)
    else:
        row = dict(base)
        row["metric_name"] = None
        row["value"] = None
        row["n"] = None
        row["filter"] = order.get("filter")
        rows = [row]

    cfg = _lib.load_config(root)
    runs_path = cfg.ledger_path("runs")
    schema = _lib.load_schema("runs.normal")

    with _lib.locked(runs_path):
        existing = _lib.jsonl_rows(runs_path, include_archive=True)

        same_run = [r for r in existing if r.get("run_id") == run_id]
        if same_run:
            ref = same_run[0]
            for field in _RUN_LEVEL_FIELDS:
                if ref.get(field) != rows[0].get(field):
                    _lib.fail(
                        "runs", field,
                        "run-level field does not match this run_id's existing rows",
                        rows[0].get(field),
                    )

        seen_keys = {(r.get("run_id"), r.get("metric_name"), r.get("filter")) for r in existing}
        for row in rows:
            key = (row["run_id"], row["metric_name"], row["filter"])
            if key in seen_keys:
                _lib.fail(
                    "runs", "run_id",
                    "duplicate primary key (run_id, metric_name, filter); repeat record refused",
                    key,
                )
            seen_keys.add(key)

        for row in rows:
            _lib.validate(row, schema, schema.get("ledger", "runs"))

        for row in rows:
            _lib.jsonl_append(runs_path, row)

    for row in rows:
        print(json.dumps(row, ensure_ascii=False))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Fallback plain-row entry point for runs.jsonl.")
    parser.add_argument("--launch-order", required=True, dest="launch_order")
    status_choices = _lib.load_tables()["rows"]["enums"]["runs.status"]
    parser.add_argument("--status", choices=status_choices, default=None)
    args = parser.parse_args(argv)
    try:
        return run(args)
    except _lib.RLError as exc:
        print(exc.message, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
