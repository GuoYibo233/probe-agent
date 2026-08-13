#!/usr/bin/env python3
"""Oversight-face lint: banned conclusion words + "number with no repro
command" (R3, plan.md §C6).

Usage:
    evidence_lint.py FILE [FILE ...]

Pure text lint -- no project config, no ledger reads. Two independent
violation classes, one finding per offending line:

1. banned-word -- plan.md §C6's bilingual list of prose conclusion words
   (通过/没问题/符合预期/passed/looks good/no problems/as expected/
   all good/everything is fine) is disallowed on any line, including
   frontmatter lines -- EXCEPT a frontmatter line whose `key:` is verdict,
   rejections or withdrawals (rows.json evidence_lint_exempt._field_level:
   those three carry an enum value or user-quoted prose, not an agent's own
   conclusion). This is a field-level exemption, not a block-level one --
   spec.md R3: "结构化枚举字段...evidence_lint 按字段豁免"; rows.json:
   "字段级豁免登记在各自行条目" -- so a frontmatter line for any other key
   (batch_id, date, ...) is still scanned.

2. no-repro-command -- a line that asserts a number must be followed, within
   the next 3 lines, by a line starting with "$ " (a pasteable repro
   command). Before judging "does this line contain a number", the ticket's
   closed exemption list is stripped out of the line first (ISO timestamp,
   YYYY-MM-DD, a hex run of >=7 chars [git HEAD/commit], a `path:line`
   token, an `[A-Z]\\d{3,}` id or a `chk-...`/batch-id shape) -- only a
   digit surviving that strip counts as an empirical claim (rows.json
   evidence_lint_exempt; plan.md §C6). Unlike rule 1, this exemption is
   block-level: every frontmatter line is skipped outright (metadata belongs
   to the header, not a claim in prose). A `$ ` line itself, and the `= `
   echo line immediately under it, are also exempt -- they are the
   declaration this rule is checking FOR, not a claim needing one of their
   own.

Output: one line per violation, `<file>:<line>: <rule>: <detail>` (1-indexed
line numbers). Exit 1 if any file has any violation, else 0.

Spec: .scratch/research-loop/issues/13-oversight.md; spec.md R3 (§3);
plan.md §C6; tables/rows.json evidence_lint_exempt.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Rule 1: banned conclusion words (plan.md §C6, bilingual)
# ---------------------------------------------------------------------------

_BANNED_WORDS_CN = ["通过", "没问题", "符合预期"]
_BANNED_WORDS_EN = [
    "passed", "looks good", "no problems", "as expected", "all good",
    "everything is fine",
]
# English phrases are matched on word boundaries (case-insensitive) so
# "passed" doesn't false-positive inside "surpassed"/"bypassed"; Chinese has
# no clean word-boundary concept in \b, so those stay plain substring checks.
_BANNED_WORDS_EN_RE = [
    (word, re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE))
    for word in _BANNED_WORDS_EN
]

_FRONTMATTER_EXEMPT_FIELDS = {"verdict", "rejections", "withdrawals"}

# ---------------------------------------------------------------------------
# Rule 2: "number with no repro command" -- exemption strip patterns, applied
# in this order (rows.json evidence_lint_exempt.metadata_kinds).
# ---------------------------------------------------------------------------

_ISO_TS_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
)
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
# chk-<principle_id>-<YYYYMMDD>-<序> and batch id <name>-<YYYYMMDD>-<序>
# (spec_header/batch_report_header batch_id_pattern) share the same
# "...-YYYYMMDD-N" tail shape; one regex covers both.
_ID_DATE_SEQ_RE = re.compile(r"\b[\w.]+-\d{8}-\d+\b")
_LETTER_ID_RE = re.compile(r"\b[A-Z]\d{3,}\b")
_PATH_LINE_RE = re.compile(r"\b[\w~-]+(?:[./][\w~-]+)+:\d+\b")
_HEX_RE = re.compile(r"\b[0-9a-fA-F]{7,}\b")

_STRIP_PATTERNS = (
    _ISO_TS_RE, _DATE_RE, _ID_DATE_SEQ_RE, _LETTER_ID_RE, _PATH_LINE_RE, _HEX_RE,
)


def _strip_exempt(line: str) -> str:
    """Remove every exempt-category substring from `line`, in the fixed
    order above (later patterns run against what earlier ones left behind,
    so overlapping shapes like a hex run inside a chk-id are consumed by
    whichever pattern matches first and cannot double-count)."""
    for pattern in _STRIP_PATTERNS:
        line = pattern.sub("", line)
    return line


def _asserts_number(line: str) -> bool:
    return bool(re.search(r"\d", _strip_exempt(line)))


def _is_dollar_line(line: str) -> bool:
    return line.lstrip().startswith("$ ")


def _is_echo_line(line: str) -> bool:
    return line.lstrip().startswith("= ")


# ---------------------------------------------------------------------------
# Frontmatter detection (shared by both rules)
# ---------------------------------------------------------------------------


def _frontmatter_end(lines: list) -> int | None:
    """0-based index of the closing '---' line, if `lines` opens with a
    '---' frontmatter delimiter as its very first line. None otherwise."""
    if not lines or lines[0].rstrip("\r\n") != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == "---":
            return i
    return None


def _frontmatter_field(line: str) -> str | None:
    """'key: value' -> 'key'; None if the line doesn't look like a
    frontmatter field line at all."""
    stripped = line.rstrip("\r\n")
    if not stripped.strip() or ":" not in stripped:
        return None
    key, _, _ = stripped.partition(":")
    return key.strip()


# ---------------------------------------------------------------------------
# Per-file lint
# ---------------------------------------------------------------------------


def lint_file(path: Path) -> list:
    """Findings for one file: [{"file", "line", "rule", "detail"}, ...],
    line numbers 1-indexed. Never raises on lint content -- an unreadable
    file is the caller's problem (main() reports it separately)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    fm_end = _frontmatter_end(lines)  # inclusive 0-based index, or None

    findings = []

    # Rule 1: every line except a frontmatter line whose field is exempt.
    for i, line in enumerate(lines):
        if fm_end is not None and i <= fm_end:
            field = _frontmatter_field(line)
            if field in _FRONTMATTER_EXEMPT_FIELDS:
                continue
        hit = None
        for word in _BANNED_WORDS_CN:
            if word in line:
                hit = word
                break
        if hit is None:
            for word, pattern in _BANNED_WORDS_EN_RE:
                if pattern.search(line):
                    hit = word
                    break
        if hit is not None:
            findings.append({
                "file": path, "line": i + 1, "rule": "banned-word",
                "detail": f"banned conclusion phrase {hit!r}",
            })

    # Rule 2: block-level frontmatter exemption; skip $/= declaration lines.
    protected = set()
    for i, line in enumerate(lines):
        if _is_dollar_line(line):
            protected.add(i)
            if i + 1 < len(lines) and _is_echo_line(lines[i + 1]):
                protected.add(i + 1)

    for i, line in enumerate(lines):
        if fm_end is not None and i <= fm_end:
            continue
        if i in protected:
            continue
        if not _asserts_number(line):
            continue
        window = lines[i + 1:i + 4]
        if any(_is_dollar_line(w) for w in window):
            continue
        findings.append({
            "file": path, "line": i + 1, "rule": "no-repro-command",
            "detail": "asserts a number with no `$ ` reproduction command within 3 lines below",
        })

    return findings


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Lint report files for banned conclusion words and unsupported numeric claims (R3).",
    )
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args(argv)

    all_findings = []
    for path in args.files:
        try:
            all_findings.extend(lint_file(path))
        except OSError as exc:
            print(f"evidence_lint: could not read {path}: {exc}", file=sys.stderr)
            return 2

    all_findings.sort(key=lambda f: (str(f["file"]), f["line"]))
    for f in all_findings:
        print(f"{f['file']}:{f['line']}: {f['rule']}: {f['detail']}")
    return 1 if all_findings else 0


if __name__ == "__main__":
    sys.exit(main())
