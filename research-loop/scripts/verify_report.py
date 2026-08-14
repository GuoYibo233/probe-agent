#!/usr/bin/env python3
"""Oversight-face mechanical verifier: checks a report's own claims against
reality (R3, plan.md §C6).

Usage:
    verify_report.py FILE [--project-root PATH]

Three independent checks, each scanning FILE's lines for the shape it cares
about:

1. path:line references -- a `<path>:<line>` token (path resolved relative
   to the project root): the path must `stat()` (exist), and the referenced
   file must have at least `line` lines.
2. Excerpt back-check -- a `> ` blockquote line within 2 lines after a line
   carrying a path:line reference: its text (after the `> ` marker) must
   appear verbatim (substring) somewhere in the referenced file's content.
3. Repro-command back-check -- a `$ cmd` line immediately followed by a
   `= value` line (plan.md §C6's declared-output convention): `cmd` is
   re-run via `_lib.split_cmd` + `_lib.run_argv(cwd=project_root)`; its
   stdout's last non-empty line must equal the declared value -- numeric
   values (int/float) compare numerically (float tolerance 1e-9), anything
   else compares as an exact string. A non-zero exit code is always a
   failure, independent of what stdout says.

Output: one line per failure, `<file>:<line>: <check>: <detail>`, followed
by a summary line `verify_report: <N> failures`. Exit 1 if any failure was
found, else 0.

Spec: .scratch/research-loop/issues/13-oversight.md; spec.md R3 (§3);
plan.md §C6.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _lib  # noqa: E402

# Same shape as evidence_lint's path:line detector: a path token (>=2
# segments joined by '.' or '/', so a bare "10:30"-style pair never matches)
# followed by ":<digits>".
_PATH_LINE_RE = re.compile(r"\b([\w~-]+(?:[./][\w~-]+)+):(\d+)\b")


def _find_path_line_refs(line: str) -> list:
    return [(m.group(1), int(m.group(2))) for m in _PATH_LINE_RE.finditer(line)]


def _is_dollar_line(line: str) -> bool:
    return line.lstrip().startswith("$ ")


def _is_quote_line(line: str) -> bool:
    return line.lstrip().startswith("> ")


def _quote_text(line: str) -> str:
    return line.lstrip()[2:]


def _fail(file, line_no, check, detail) -> dict:
    return {"file": file, "line": line_no, "check": check, "detail": detail}


# ---------------------------------------------------------------------------
# Check 1 + 2: path:line references and their excerpt back-check
# ---------------------------------------------------------------------------


def check_path_line_refs(report_path: Path, lines: list, root: Path) -> list:
    findings = []
    for i, line in enumerate(lines):
        refs = _find_path_line_refs(line)
        if not refs:
            continue

        quote_lines = [j for j in (i + 1, i + 2) if j < len(lines) and _is_quote_line(lines[j])]

        for rel_path, ref_line in refs:
            target = (root / rel_path)
            if not target.exists():
                findings.append(_fail(
                    report_path, i + 1, "path:line",
                    f"referenced path {rel_path!r} does not exist under {root}",
                ))
                continue
            try:
                target_text = target.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                findings.append(_fail(
                    report_path, i + 1, "path:line",
                    f"referenced path {rel_path!r} could not be read: {exc}",
                ))
                continue
            target_lines = target_text.splitlines()
            if ref_line < 1 or ref_line > len(target_lines):
                findings.append(_fail(
                    report_path, i + 1, "path:line",
                    f"referenced path {rel_path!r} has {len(target_lines)} lines, "
                    f"reference asks for line {ref_line}",
                ))
                continue

            for j in quote_lines:
                excerpt = _quote_text(lines[j])
                if excerpt not in target_text:
                    findings.append(_fail(
                        report_path, j + 1, "excerpt",
                        f"quoted text does not appear verbatim in {rel_path!r}: {excerpt!r}",
                    ))
    return findings


# ---------------------------------------------------------------------------
# Check 3: repro command back-check
# ---------------------------------------------------------------------------


def _parse_declared(value: str):
    """(kind, parsed) -- kind is 'int'|'float'|'str'. A value with a decimal
    point never parses as int even if the fractional part is all zeros
    (declared "1.0" must not silently match an actual "1")."""
    try:
        return "int", int(value)
    except ValueError:
        pass
    try:
        return "float", float(value)
    except ValueError:
        pass
    return "str", value


def _last_nonempty_line(text: str) -> str:
    for candidate in reversed(text.splitlines()):
        if candidate.strip():
            return candidate.strip()
    return ""


def check_repro_commands(report_path: Path, lines: list, root: Path) -> list:
    findings = []
    for i, line in enumerate(lines):
        if not _is_dollar_line(line):
            continue
        if i + 1 >= len(lines) or not lines[i + 1].lstrip().startswith("= "):
            continue  # no declared value paired with this command -- not this check's concern

        cmd_text = line.lstrip()[2:]
        declared_text = lines[i + 1].lstrip()[2:].strip()
        declared_kind, declared_value = _parse_declared(declared_text)

        try:
            argv = _lib.split_cmd(cmd_text, "verify_report", "cmd")
        except _lib.RLError as exc:
            findings.append(_fail(
                report_path, i + 1, "repro-command", f"could not parse command: {exc.message}",
            ))
            continue

        exit_code, stdout, stderr, _elapsed = _lib.run_argv(argv, cwd=root)
        if exit_code != 0:
            tail = (stderr or stdout or "").strip().splitlines()[-5:]
            findings.append(_fail(
                report_path, i + 1, "repro-command",
                f"`{cmd_text}` exited {exit_code} (expected 0); tail: {tail}",
            ))
            continue

        actual_text = _last_nonempty_line(stdout)
        actual_kind, actual_value = _parse_declared(actual_text)

        if declared_kind in ("int", "float"):
            if actual_kind not in ("int", "float"):
                findings.append(_fail(
                    report_path, i + 1, "repro-command",
                    f"`{cmd_text}` declared numeric value {declared_text!r} but produced "
                    f"non-numeric output {actual_text!r}",
                ))
                continue
            if abs(float(declared_value) - float(actual_value)) > 1e-9:
                findings.append(_fail(
                    report_path, i + 1, "repro-command",
                    f"`{cmd_text}` declared {declared_text!r}, actual output was {actual_text!r}",
                ))
        else:
            if actual_text != declared_text:
                findings.append(_fail(
                    report_path, i + 1, "repro-command",
                    f"`{cmd_text}` declared {declared_text!r}, actual output was {actual_text!r}",
                ))
    return findings


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def run(report_path: Path, root: Path) -> list:
    text = report_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    findings = []
    findings.extend(check_path_line_refs(report_path, lines, root))
    findings.extend(check_repro_commands(report_path, lines, root))
    findings.sort(key=lambda f: f["line"])
    return findings


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Mechanically verify a report's path:line refs, quoted excerpts and repro commands.",
    )
    parser.add_argument("file", type=Path)
    parser.add_argument("--project-root", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        root = _lib.resolve_project_root(args.project_root)
    except _lib.RLError as exc:
        print(f"verify_report: {exc.message}", file=sys.stderr)
        return 2
    if root is None:
        print(
            "verify_report: project not wired: research-loop.json not found "
            "(pass --project-root)",
            file=sys.stderr,
        )
        return 2

    try:
        findings = run(args.file, root)
    except OSError as exc:
        print(f"verify_report: could not read {args.file}: {exc}", file=sys.stderr)
        return 2

    for f in findings:
        print(f"{f['file']}:{f['line']}: {f['check']}: {f['detail']}")
    print(f"verify_report: {len(findings)} failures")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
