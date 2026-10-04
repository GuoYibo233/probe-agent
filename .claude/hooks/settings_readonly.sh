#!/usr/bin/env bash
# PreToolUse hook: refuses any agent edit to a YAML file under
# experimental_settings/ outside its draft directory and to models/table.yaml,
# the owner's files (contracts 5.1, 6.1). The setting files under
# experimental_settings/draft/ are the agents' to write (gyb, 2026-10-02 and
# 2026-10-04).
#
# The Bash branch leans toward catching writes (gyb, 2026-09-24, ruling 16): a
# command whose text mentions a protected path together with a write word or
# with any of the interpreters python, perl, yq, ed is refused, whatever the
# command does. Read-only commands of that shape are refused too
# (`grep x experimental_settings/a.yaml > /tmp/out`,
# `python -c "yaml.safe_load(open('experimental_settings/x.yaml'))"`), and that
# is accepted. A mention counts as a draft file only when it is a plain path
# under experimental_settings/draft/ (word characters, dots and hyphens, no ".."
# segment), so a glob, a brace expansion or a climb out of the draft directory
# is still protected.
set -uo pipefail

payload="$(cat)"

exec python3 - "$payload" << 'PYEOF'
import json
import os
import re
import sys

payload = sys.argv[1]

REFUSAL = (
    "experimental_settings/*.yaml and models/table.yaml are the owner's files: "
    "an agent never edits them (contracts 5.1, 6.1). Propose the change as a "
    "task instead, or write the setting under experimental_settings/draft/, "
    "which agents may write."
)

MODEL_TABLE_TAIL_RE = re.compile(r"(^|/)models/table\.yaml$")
SETTINGS_TAIL_RE = re.compile(r"(^|/)(experimental_settings/.+\.ya?ml)$")

MODEL_TABLE_MENTION_RE = re.compile(r"models/table\.yaml")
SETTINGS_MENTION_RE = re.compile(r"experimental_settings/[^\s\"']*\.ya?ml")

DRAFT_SETTING_RE = re.compile(
    r"experimental_settings/draft/(?:[\w.-]+/)*[\w.-]+\.ya?ml"
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


def is_draft_setting(mention):
    """True when the mention is a plain path of a setting file in the draft directory."""
    return (
        DRAFT_SETTING_RE.fullmatch(mention) is not None
        and ".." not in mention.split("/")
    )


def is_protected(path):
    """True when the path names models/table.yaml or a setting file outside the draft directory."""
    if not path:
        return False
    normal = os.path.normpath(path)
    if MODEL_TABLE_TAIL_RE.search(normal) is not None:
        return True
    match = SETTINGS_TAIL_RE.search(normal)
    return match is not None and not is_draft_setting(match.group(2))


def mentions_protected(command):
    """True when the command text names models/table.yaml or a setting file outside the draft directory."""
    if MODEL_TABLE_MENTION_RE.search(command) is not None:
        return True
    return any(
        not is_draft_setting(mention)
        for mention in SETTINGS_MENTION_RE.findall(command)
    )


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
    has_write_marker = any(
        marker.search(command) is not None for marker in BASH_WRITE_MARKERS
    )
    if mentions_protected(command) and has_write_marker:
        block()
    allow()

allow()
PYEOF
