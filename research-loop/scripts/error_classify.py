#!/usr/bin/env python3
"""Run-layer error classification: match a failure against the project's
error-classes table and report the first fully-matching rule's action.

Usage:
    error_classify.py --error-classes PATH [--exit-code N] [--log PATH]
                       [--output-check V]

The error-classes table is {rule_name: {"match": {...}, "action": "retry"|
"swap-card"|"escalate"}}, tried in the file's key order. A rule's match
dict may give exit_code, log_regex, output_check -- however many it gives
are AND-ed together:

- exit_code: numeric equality against --exit-code.
- log_regex: re.search against the full text of --log.
- output_check: string equality against --output-check.

Any match key whose corresponding CLI input was not supplied makes that
key (and so the whole rule) fail to match -- it is never treated as a
free pass. The first rule where every given key matches wins.

If nothing matches, this script does not guess (spec R8: the run layer
classifies mechanically or not at all; escalating an unknown failure is the
caller's job, not this script's).

stdout's last (and only) line is a single JSON object:
    {"rule": <name>|null, "action": "retry"|"swap-card"|"escalate"|"unknown"}
Exit code is always 0 -- "unknown" is a valid classification, not a script
failure.

Spec: .scratch/research-loop/issues/12-output-error.md; shape reference:
research-loop/tables/rows.json error_classes.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_MATCH_KEYS = {"exit_code", "log_regex", "output_check"}


def _rule_matches(match: dict, exit_code, log_text, output_check) -> bool:
    for key in match:
        if key not in _MATCH_KEYS:
            raise ValueError(f"error-classes: unknown match key {key!r}")
    for key, expected in match.items():
        if key == "exit_code":
            if exit_code is None or exit_code != expected:
                return False
        elif key == "log_regex":
            if log_text is None or re.search(expected, log_text) is None:
                return False
        elif key == "output_check":
            if output_check is None or output_check != expected:
                return False
    return True


def classify(classes: dict, exit_code, log_text, output_check) -> dict:
    for name, rule in classes.items():
        if _rule_matches(rule.get("match", {}), exit_code, log_text, output_check):
            return {"rule": name, "action": rule["action"]}
    return {"rule": None, "action": "unknown"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Classify a run failure against the project's error-classes table.",
    )
    parser.add_argument("--error-classes", required=True, type=Path)
    parser.add_argument("--exit-code", type=int, default=None)
    parser.add_argument("--log", type=Path, default=None)
    parser.add_argument("--output-check", type=str, default=None)
    args = parser.parse_args(argv)

    try:
        classes = json.loads(args.error_classes.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error_classify: failed to read error classes {args.error_classes}: {exc}", file=sys.stderr)
        return 2

    log_text = None
    if args.log is not None:
        try:
            log_text = args.log.read_text(encoding="utf-8", errors="replace")
        except OSError:
            log_text = None

    try:
        result = classify(classes, args.exit_code, log_text, args.output_check)
    except ValueError as exc:
        print(f"error_classify: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
