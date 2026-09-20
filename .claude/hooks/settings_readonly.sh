#!/usr/bin/env bash
# PreToolUse hook: refuses any agent edit to experimental_settings/*.yaml and
# to models/table.yaml, the owner's files (contracts 5.1, 6.1).
#
# TODO(owner, 2026-09-21): the Bash branch is a substring match, and both of its
# errors are known (wave 7 final review, critic F2; agents do not change this
# file's logic):
#   - it refuses a read-only command that names a setting file beside a write word
#     (`grep x experimental_settings/a.yaml > /tmp/out`, `cat CLAUDE.md | tee ...`,
#     any command whose text carries "install" or "patch" as an ordinary word);
#   - it passes an edit made through an interpreter that never spells a write word
#     (`python3 -c "open('experimental_settings/a.yaml','w')..."`, `perl -pi`,
#     `yq -i`, `ed`).
# The owner decides which way the match leans: keep over-refusing (the gate is
# fail-closed today), or narrow it to redirects and in-place editors whose target
# token is a protected path, and add the interpreters to BASH_WRITE_MARKERS.
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

BASH_WRITE_MARKERS = (
    ">", ">>", "tee", "sed -i", "cp ", "mv ", "rm ", "truncate", "dd ",
    "patch", "chmod", "install",
)


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
    has_write_marker = any(marker in command for marker in BASH_WRITE_MARKERS)
    if mentions_protected and has_write_marker:
        block()
    allow()

allow()
PYEOF
