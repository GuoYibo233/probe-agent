#!/usr/bin/env bash
# PreToolUse hook: refuses any agent edit to experimental_settings/*.yaml and
# to models/table.yaml, the owner's files (contracts 5.1, 6.1).
#
# The Bash branch leans toward catching writes (gyb, 2026-09-24, ruling 16): a
# command whose text mentions a protected path together with a write word or
# with any of the interpreters python, perl, yq, ed is refused, whatever the
# command does. Read-only commands of that shape are refused too
# (`grep x experimental_settings/a.yaml > /tmp/out`,
# `python -c "yaml.safe_load(open('experimental_settings/x.yaml'))"`), and that
# is accepted.
set -uo pipefail

payload="$(cat)"

exec python3 - "$payload" << 'PYEOF'
import json
import re
import sys

payload = sys.argv[1]

REFUSAL = (
    "experimental_settings/*.yaml and models/table.yaml are the owner's files: "
    "an agent never edits them (contracts 5.1, 6.1). Propose the change as a "
    "task instead."
)

PROTECTED_TAIL_RE = re.compile(
    r"(^|/)experimental_settings/[^/]+\.ya?ml$|(^|/)models/table\.yaml$"
)

PROTECTED_MENTION_RE = re.compile(
    r"experimental_settings/[^\s\"']*\.ya?ml|models/table\.yaml"
)

# Plain substrings, matched anywhere in the command text.
BASH_WRITE_SUBSTRINGS = (
    ">", ">>", "tee", "sed -i", "cp ", "mv ", "rm ", "truncate", "dd ",
    "patch", "chmod", "install",
)

# Interpreters that can edit a file without spelling a substring above: any
# mention of one is a write marker, whatever its flags or its program.
BASH_WRITE_PATTERNS = (
    # python, python3, python3.12, a venv's .../bin/python.
    r"\bpython[0-9.]*\b",
    # perl, perl5.38.2, perl5.38-x86_64-linux-gnu; yq, yq_linux_amd64.
    r"\bperl",
    r"\byq",
    # ed as a word: the two letters with no word character, dot or hyphen on
    # either side and no slash after (a slash may precede, as in /bin/ed), so
    # "sed", "edit", "ed/" and a file named ed.yaml do not match.
    r"(?<![\w.-])ed(?![\w./-])",
)

BASH_WRITE_MARKERS = tuple(
    re.compile(re.escape(s)) for s in BASH_WRITE_SUBSTRINGS
) + tuple(re.compile(p) for p in BASH_WRITE_PATTERNS)


def is_protected(path):
    if not path:
        return False
    return PROTECTED_TAIL_RE.search(path) is not None


def block():
    sys.stderr.write(REFUSAL + "\n")
    sys.exit(2)


def allow():
    sys.exit(0)


try:
    data = json.loads(payload)
except (json.JSONDecodeError, TypeError):
    allow()

tool_name = data.get("tool_name", "")
tool_input = data.get("tool_input", {}) or {}

if tool_name in ("Write", "Edit", "MultiEdit"):
    if is_protected(tool_input.get("file_path")):
        block()
    for edit in tool_input.get("edits", []) or []:
        if is_protected(edit.get("file_path")):
            block()
    allow()

if tool_name == "NotebookEdit":
    if is_protected(tool_input.get("notebook_path")):
        block()
    allow()

if tool_name == "Bash":
    command = tool_input.get("command", "") or ""
    mentions_protected = PROTECTED_MENTION_RE.search(command) is not None
    has_write_marker = any(
        marker.search(command) is not None for marker in BASH_WRITE_MARKERS
    )
    if mentions_protected and has_write_marker:
        block()
    allow()

allow()
PYEOF
