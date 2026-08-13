#!/usr/bin/env python3
"""Run-layer output check: verify a launch order's expected_outputs.

Usage:
    output_check.py --launch-order PATH

Reads the launch order JSON at PATH, resolves each expected_outputs entry's
path_glob relative to the launch order's artifact_dir (which is itself
resolved relative to the current working directory), and checks:

- glob has no match -> that entry is missing-output.
- for every matched file: size < min_bytes -> empty-output; line count <
  min_lines -> empty-output; required_keys non-empty and the file's first
  non-empty line does not parse as a JSON object containing every key (a
  parse failure counts as missing) -> empty-output.
- overall verdict: any entry missing-output -> missing-output; else any
  entry empty-output -> empty-output; else ok.

An experiment process exiting 0 with an empty product is not "ok" here --
this script never looks at the experiment's own exit code, only at what
landed on disk (spec R8/R3: run layer machine-checks, does not guess).

stdout's last (and only) line is a single JSON object:
    {"verdict": "ok"|"missing-output"|"empty-output", "failures": [...]}
Each failure is {"glob": str, "file": str|None, "why": str}.
Exit code: 0 when verdict is ok, 4 otherwise.

Spec: .scratch/research-loop/issues/12-output-error.md; shape reference:
research-loop/tables/rows.json launch_order.expected_outputs.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _read_first_nonempty_line(path: Path) -> str | None:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                return stripped
    return None


def _count_lines(path: Path) -> int:
    count = 0
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for _ in f:
            count += 1
    return count


def check_file(path: Path, glob: str, entry: dict) -> list:
    """Check one matched file against one expected_outputs entry. Returns a
    list of {glob, file, why} failure dicts (empty if the file clears every
    gate the entry specifies)."""
    failures = []
    file_str = str(path)

    min_bytes = entry.get("min_bytes")
    if min_bytes is not None:
        size = path.stat().st_size
        if size < min_bytes:
            failures.append({
                "glob": glob, "file": file_str,
                "why": f"size {size} bytes < min_bytes {min_bytes}",
            })

    min_lines = entry.get("min_lines")
    if min_lines is not None:
        n_lines = _count_lines(path)
        if n_lines < min_lines:
            failures.append({
                "glob": glob, "file": file_str,
                "why": f"{n_lines} lines < min_lines {min_lines}",
            })

    required_keys = entry.get("required_keys")
    if required_keys:
        first_line = _read_first_nonempty_line(path)
        parsed = None
        if first_line is not None:
            try:
                candidate = json.loads(first_line)
            except (json.JSONDecodeError, ValueError):
                candidate = None
            if isinstance(candidate, dict):
                parsed = candidate
        if parsed is None:
            failures.append({
                "glob": glob, "file": file_str,
                "why": "first non-empty line is not a JSON object",
            })
        else:
            missing = [k for k in required_keys if k not in parsed]
            if missing:
                failures.append({
                    "glob": glob, "file": file_str,
                    "why": f"missing required_keys: {missing}",
                })

    return failures


def check_entry(artifact_dir: Path, entry: dict):
    """Check one expected_outputs entry. Returns (verdict, failures) for
    this entry alone -- verdict is one of ok / missing-output / empty-output."""
    glob = entry["path_glob"]
    matches = sorted(p for p in artifact_dir.glob(glob) if p.is_file())
    if not matches:
        return "missing-output", [{
            "glob": glob, "file": None, "why": "no file matched the glob",
        }]

    failures = []
    for path in matches:
        failures.extend(check_file(path, glob, entry))
    if failures:
        return "empty-output", failures
    return "ok", []


def run(launch_order_path: Path) -> dict:
    order = json.loads(launch_order_path.read_text(encoding="utf-8"))
    artifact_dir = Path(order["artifact_dir"])

    all_failures = []
    entry_verdicts = []
    for entry in order.get("expected_outputs", []):
        verdict, failures = check_entry(artifact_dir, entry)
        entry_verdicts.append(verdict)
        all_failures.extend(failures)

    if "missing-output" in entry_verdicts:
        overall = "missing-output"
    elif "empty-output" in entry_verdicts:
        overall = "empty-output"
    else:
        overall = "ok"
    return {"verdict": overall, "failures": all_failures}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Check a launch order's expected_outputs against what landed on disk.",
    )
    parser.add_argument("--launch-order", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        result = run(args.launch_order)
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"output_check: failed to read launch order {args.launch_order}: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result))
    return 0 if result["verdict"] == "ok" else 4


if __name__ == "__main__":
    sys.exit(main())
