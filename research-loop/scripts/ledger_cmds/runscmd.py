"""`ledger.py runs-append --layer deploy --principle PID` (issues/07-runs-
principles.md; spec §5 "判据 run 执行契约").

The only script path that appends a runs.jsonl *criterion* (reduced) row.
Execution and intake are the same action: this module looks up PID's
criterion_cmd on the principles ledger, runs it itself (no shell, timed),
and -- only on exit code 0 with a structured JSON tail line -- appends the
row. A criterion that didn't run cleanly is not a measurement: nothing is
written, and the caller is pointed at R8 escalation instead.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import _lib
from ledger_cmds.principlescmd import parse_principles

_STDERR_TAIL_LINES = 20


def _principle_row(cfg, pid: str) -> dict:
    principles_path = Path(cfg.ledger_path("principles"))
    for row in parse_principles(principles_path):
        if row.get("principle_id") == pid:
            return row
    _lib.fail("principles", "principle_id", "not found", pid)


def _next_run_id(pid: str, existing: list) -> str:
    date = _lib.today().replace("-", "")
    prefix = f"chk-{pid}-{date}-"
    seq = sum(
        1 for row in existing
        if isinstance(row.get("run_id"), str) and row["run_id"].startswith(prefix)
    )
    return f"{prefix}{seq + 1}"


def run(args) -> int:
    if args.layer != "deploy":
        _lib.fail("runs", "layer", "runs-append only accepts --layer deploy")

    root = _lib.find_project_root()
    cfg = _lib.load_config(root)

    if cfg.null_locked("registry_cmd"):
        _lib.fail("config", "registry_cmd", "not wired (null); cannot run criterion")

    prow = _principle_row(cfg, args.principle)
    criterion_cmd = (prow.get("criterion_cmd") or "").strip()
    if not criterion_cmd:
        _lib.fail(
            "principles", "criterion_cmd",
            "not wired (【想法待定】); cannot run criterion",
        )

    argv = _lib.split_cmd(criterion_cmd, "principles", "criterion_cmd")
    _lib.check_in_registry(argv, cfg, ledger="principles", field="criterion_cmd")

    exit_code, stdout, stderr, elapsed = _lib.run_argv(argv, cwd=root)
    parsed = _lib.last_json_line(stdout)
    ok = (
        exit_code == 0
        and isinstance(parsed, dict)
        and "value" in parsed
        and "evidence_path" in parsed
    )
    if not ok:
        tail = "\n".join(stderr.splitlines()[-_STDERR_TAIL_LINES:])
        print(
            f"runs-append: criterion for {args.principle} did not produce a "
            f"valid result (exit_code={exit_code}); no row recorded.\n"
            f"--- stderr (last {_STDERR_TAIL_LINES} lines) ---\n{tail}\n"
            "escalate per R8: open a blocked entry (kind=failure) with the "
            "command, this output, and the log path.",
            file=sys.stderr,
        )
        return 2

    runs_path = cfg.ledger_path("runs")
    schema = _lib.load_schema("runs.criterion")

    with _lib.locked(runs_path):
        existing = _lib.jsonl_rows(runs_path, include_archive=True)
        run_id = _next_run_id(args.principle, existing)
        if any(row.get("run_id") == run_id for row in existing):
            _lib.fail("runs", "run_id", "criterion run already recorded", run_id)

        row = {
            "run_id": run_id,
            "status": "ok",
            "principle_id": args.principle,
            "value": parsed["value"],
            "output_dir": parsed["evidence_path"],
            "runmeta_path": None,
            "metric_name": None,
            "n": None,
            "filter": None,
            "seed": None,
            "dataset_version": None,
            "batch_id": None,
            "arm": None,
            "quick": None,
            "commit": _lib.git_head(root),
            "elapsed_s": int(round(elapsed)),
            "gpu_count": None,
            "recorded_at": _lib.now_iso(),
            "schema_version": 1,
        }
        _lib.validate(row, schema, schema.get("ledger", "runs"))
        _lib.jsonl_append(runs_path, row)

    print(json.dumps(row, ensure_ascii=False))
    return 0


def register(subparsers):
    parser = subparsers.add_parser(
        "runs-append",
        help="Run a principle's criterion_cmd and append its runs.jsonl reduced row.",
    )
    layer_values = _lib.load_tables()["writes"]["layer_param"]["values"]
    parser.add_argument("--layer", required=True, choices=layer_values)
    parser.add_argument("--principle", required=True)
