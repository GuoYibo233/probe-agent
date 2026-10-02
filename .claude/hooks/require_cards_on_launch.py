#!/usr/bin/env python3
"""PreToolUse(Bash) hook: refuse a `run.py` launch that names no cards.

A workflow walk (`run.py <workflow> <setting> ...`), `run.py refire` and `run.py retry` can
start GPU pieces; without `--cards` the launcher takes the first free card whatever its size
(gpu-run skill, step 1). Every other subcommand, `--help`, and any text that only mentions
run.py (git add, grep, sed) passes.
"""
import json
import os
import shlex
import sys

READ_ONLY_SUBCOMMANDS = {"ls", "where", "find", "kill", "table", "free", "sync", "version",
                         "selfcheck"}
SEPARATORS = {"&&", "||", ";", "|", "&"}
REASON = ("run.py walks, refire and retry must name their cards: add --cards <host>:<ids> "
          "chosen from the Runs by card type table and `run.py free` (gpu-run skill, step 1). "
          "Without it the launcher takes the first free card whatever its size.")


def launches_without_cards(command: str) -> bool:
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return False
    tokens = [t.rstrip(";") for t in tokens]
    for i, token in enumerate(tokens):
        invoked = (token.endswith("run.py") and i > 0
                   and os.path.basename(tokens[i - 1]).startswith("python"))
        if not invoked:
            continue
        segment = []
        for t in tokens[i + 1:]:
            if t in SEPARATORS:
                break
            segment.append(t)
        first = segment[0] if segment else None
        if first is None or first.startswith("-") or first in READ_ONLY_SUBCOMMANDS:
            continue
        has_cards = any(t == "--cards" or t.startswith("--cards=") for t in segment)
        if not has_cards:
            return True
    return False


def main() -> int:
    payload = json.load(sys.stdin)
    command = (payload.get("tool_input") or {}).get("command") or ""
    if launches_without_cards(command):
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                 "permissionDecision": "deny",
                                                 "permissionDecisionReason": REASON}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
