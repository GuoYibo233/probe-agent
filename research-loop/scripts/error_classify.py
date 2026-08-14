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

A missing or unparseable error-classes table (#155) is treated as zero
rules, not a crash: R8's mandatory first step must never itself be the
thing that traceback-dies on a bare project -- it falls straight through to
the same "unknown" outcome nothing-matched would produce, with one extra
line on stderr naming the table path so the caller knows why.

stdout's last (and only) line is a single JSON object:
    {"rule": <name>|null, "action": "retry"|"swap-card"|"escalate"|"unknown"}
Exit code is always 0 -- "unknown" is a valid classification, not a script
failure (that includes the missing/unreadable-table case above).

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
            if log_text is None:
                return False
            try:
                if re.search(expected, log_text) is None:
                    return False
            except re.error as exc:
                raise ValueError(f"error-classes: invalid log_regex {expected!r}: {exc}") from exc
        elif key == "output_check":
            if output_check is None or output_check != expected:
                return False
    return True


def classify(classes: dict, exit_code, log_text, output_check) -> dict:
    for name, rule in classes.items():
        if _rule_matches(rule.get("match", {}), exit_code, log_text, output_check):
            if "action" not in rule:
                raise ValueError(f"error-classes: rule {name!r} is missing required key 'action'")
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
    except (OSError, json.JSONDecodeError):
        # #155: the error-classes table is deploy-owned and may simply not
        # exist yet on a bare project -- R8's mandatory first step must not
        # itself traceback-die for that. Zero rules classifies exactly like
        # nothing-matched: same stdout shape, same exit code (0), one extra
        # stderr line naming the path so the caller can tell "unclassified
        # because no table" from "unclassified because no rule fit".
        print(
            f"error_classify: error classes table not found/unreadable at "
            f"{args.error_classes}; treating as unclassified",
            file=sys.stderr,
        )
        classes = {}

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
