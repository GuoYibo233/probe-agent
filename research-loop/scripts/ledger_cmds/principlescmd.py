"""`ledger.py principles-lint [--file PATH]` and `ledger.py render principles`
(issues/07-runs-principles.md).

Both operate on the project's principles ledger -- an md-table file (default
`METHOD.md`, format=md-table per tables/ledgers.json) whose fixed eight
columns (tables/rows.json principles_columns) carry each R1 principle. This
module owns two things:

- `parse_principles()`: the shared md-table reader. runscmd.py (T07) and
  later tickets (T09/T11) import it to look up a principle's criterion_cmd
  or check its status/rationale/applies_when.
- `principles-lint`: mechanical R1 contract checks (spec R1, R7) -- every
  violation is collected and reported, not just the first.
- `render principles`: the maintenance action (writes.json
  maintenance_exempt) that back-fills the last_tested column from
  runs.jsonl's criterion rows. It rewrites only that one column's text on
  each data row; every other byte in the file (including other cells'
  original spacing) is left untouched.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import _lib

# Statuses whose row must carry a working criterion_cmd (spec R1: "未接线态
# 允许 criterion_cmd 暂空落档，但必须标【想法待定】；补上判据才可转
# 【现状】/【已定要改】").
_TESTABLE_STATUSES = {"【现状】", "【已定要改】"}
_IDEA_PENDING_STATUS = "【想法待定】"

# A '|' inside a cell must be escaped as '\|' to survive naive md-table
# splitting (the closing-'|'-delimited-columns convention every table in
# this plugin already follows). Splitting on unescaped '|' only, then
# unescaping '\|' back to a literal '|', is what lets a criterion_cmd cell
# legitimately (if wrongly) contain a shell pipe character for
# principles-lint's pipe check to catch, instead of the row silently
# failing to parse (wrong cell count) and vanishing from the table.
_CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")

_RUN_ID_DATE_RE = re.compile(r"^chk-.+-(\d{8})-\d+$")


# ---------------------------------------------------------------------------
# Shared md-table parsing
# ---------------------------------------------------------------------------


def _split_row(line: str) -> list:
    """One markdown table row -> its cell texts, split on unescaped '|'."""
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip().replace("\\|", "|") for cell in _CELL_SPLIT_RE.split(stripped)]


def _find_header(lines: list):
    """First line (0-indexed) whose cells include a `principle_id` cell.
    Returns (index, header_cells) or (None, None) if no such line exists."""
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = _split_row(stripped)
        if "principle_id" in cells:
            return i, cells
    return None, None


def parse_principles(path) -> list:
    """Parse the first markdown table in `path` whose header row contains a
    `principle_id` cell. Column names are exactly that header row's cells
    (helpers.py's eight-column METHOD.md layout: principle_id/status/scope/
    applies_when/principle/rationale/criterion_cmd/last_tested). Returns one
    dict per body row (header cell -> stripped cell text); the row
    immediately after the header (the `|---|---|...` separator) is skipped.
    A malformed body row (wrong cell count) is skipped, not raised on."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    header_idx, header = _find_header(lines)
    if header_idx is None:
        return []

    rows = []
    for line in lines[header_idx + 2:]:
        stripped = line.strip()
        if not stripped.startswith("|"):
            break
        cells = _split_row(stripped)
        if len(cells) != len(header):
            continue
        rows.append(dict(zip(header, cells)))
    return rows


# ---------------------------------------------------------------------------
# principles-lint
# ---------------------------------------------------------------------------


def _registry_error(cmd: str, cfg, pid: str):
    """Run cmd through check_in_registry (shared with launch_order.
    registry_task per principles_columns._exec_rule). Returns None if it
    passes, else a "principles.<pid>.criterion_cmd: <detail>" line -- the
    detail is check_in_registry's own message with its generic
    "principles.criterion_cmd: " prefix swapped for the PID-qualified one
    principles-lint's own error format uses."""
    argv = _lib.split_cmd(cmd, "principles", "criterion_cmd")
    try:
        _lib.check_in_registry(argv, cfg, ledger="principles", field="criterion_cmd")
    except _lib.RLError as exc:
        prefix = "principles.criterion_cmd: "
        detail = exc.message[len(prefix):] if exc.message.startswith(prefix) else exc.message
        return f"principles.{pid}.criterion_cmd: {detail}"
    return None


def _lint_errors(rows: list, cfg) -> list:
    """Every R1 contract violation across `rows`, each formatted
    `principles.<PID>.<column>: <what's wrong>` (this section's own header).
    Collects everything instead of stopping at the first violation."""
    status_enum = _lib.load_tables()["rows"]["enums"]["principles.status"]
    errors = []

    counts = {}
    for row in rows:
        pid = row.get("principle_id", "")
        counts[pid] = counts.get(pid, 0) + 1
    for pid, n in counts.items():
        if n > 1:
            errors.append(f"principles.{pid}.principle_id: duplicate principle_id ({n} rows)")

    for row in rows:
        pid = row.get("principle_id", "")

        if not (row.get("applies_when") or "").strip():
            errors.append(f"principles.{pid}.applies_when: must not be empty")

        if not (row.get("rationale") or "").strip():
            errors.append(f"principles.{pid}.rationale: must not be empty")

        status = row.get("status", "")
        if status not in status_enum:
            errors.append(
                f"principles.{pid}.status: must be one of {status_enum} (got: {status!r})"
            )

        cmd = (row.get("criterion_cmd") or "").strip()

        if cmd and ("|" in cmd or "\n" in cmd):
            errors.append(f"principles.{pid}.criterion_cmd: must not contain pipes or newlines")
            continue  # unusable as a command -- the registry check below needs a clean argv

        if status == _IDEA_PENDING_STATUS:
            if cmd:  # empty cmd is the expected 未接线态 shape -- allowed
                err = _registry_error(cmd, cfg, pid)
                if err:
                    errors.append(err)
        elif status in _TESTABLE_STATUSES:
            if not cmd:
                errors.append(
                    f"principles.{pid}.criterion_cmd: not wired; required when status is {status}"
                )
            else:
                err = _registry_error(cmd, cfg, pid)
                if err:
                    errors.append(err)
        # else (withdrawn / an already-reported bad status): no criterion_cmd
        # requirement -- the status-enum error above already covers it.

    return errors


def _lint(args) -> int:
    root = _lib.find_project_root()
    cfg = _lib.load_config(root)
    path = Path(args.file) if args.file is not None else Path(cfg.ledger_path("principles"))

    rows = parse_principles(path)
    errors = _lint_errors(rows, cfg)
    if errors:
        for line in errors:
            print(line, file=sys.stderr)
        return 1
    return 0


# ---------------------------------------------------------------------------
# render principles
# ---------------------------------------------------------------------------


def _format_last_tested(run_row: dict) -> str:
    """`ok (<value>) <YYYY-MM-DD>` -- the date comes from run_id's own
    <YYYYMMDD> segment (spec §5: "日期取 run_id 的日期段，spec 成文的日期
    来源"), reformatted with dashes for display."""
    match = _RUN_ID_DATE_RE.match(run_row.get("run_id", ""))
    date = match.group(1) if match else ""
    date_display = f"{date[:4]}-{date[4:6]}-{date[6:]}" if len(date) == 8 else date
    return f"ok ({run_row.get('value')}) {date_display}"


def _latest_criterion_rows(runs_path) -> dict:
    """{principle_id: its latest (by recorded_at) runs.jsonl criterion row},
    read across main + archive (spec §5: "跨档")."""
    latest = {}
    for row in _lib.jsonl_rows(runs_path, include_archive=True):
        pid = row.get("principle_id")
        if pid is None:
            continue
        current = latest.get(pid)
        if current is None or (row.get("recorded_at") or "") > (current.get("recorded_at") or ""):
            latest[pid] = row
    return latest


def _rewrite_last_tested_cell(line: str, new_value: str) -> str:
    """Replace only the final ('last_tested') cell's content in one
    markdown table row -- every other byte (leading whitespace, earlier
    cells, line ending) is copied through unchanged."""
    newline = ""
    body = line
    for ending in ("\r\n", "\n"):
        if body.endswith(ending):
            newline = ending
            body = body[: -len(ending)]
            break
    stripped = body.rstrip(" \t")
    trailing_ws = body[len(stripped):]

    last_pipe = stripped.rfind("|")
    second_last_pipe = stripped.rfind("|", 0, last_pipe)
    if last_pipe == -1 or second_last_pipe == -1:
        return line  # not a well-formed table row -- leave it alone

    new_body = f"{stripped[:second_last_pipe + 1]} {new_value} |"
    return new_body + trailing_ws + newline


def _render(args) -> int:
    root = _lib.find_project_root()
    cfg = _lib.load_config(root)
    principles_path = Path(cfg.ledger_path("principles"))

    lines = principles_path.read_text(encoding="utf-8").splitlines(keepends=True)
    header_idx, header = _find_header(lines)
    if header_idx is None:
        return 0  # no principles table -- nothing to render

    pid_col = header.index("principle_id")
    latest_by_pid = _latest_criterion_rows(cfg.ledger_path("runs"))

    out_lines = list(lines)
    idx = header_idx + 2
    while idx < len(out_lines):
        line = out_lines[idx]
        stripped = line.strip()
        if not stripped.startswith("|"):
            break
        cells = _split_row(stripped)
        if len(cells) == len(header):
            pid = cells[pid_col]
            run_row = latest_by_pid.get(pid)
            new_value = _format_last_tested(run_row) if run_row is not None else "—"
            out_lines[idx] = _rewrite_last_tested_cell(line, new_value)
        idx += 1

    principles_path.write_text("".join(out_lines), encoding="utf-8")
    return 0


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


def register(subparsers):
    parser = subparsers.add_parser(
        "principles-lint",
        help="Check METHOD.md's R1 principle table for contract violations.",
    )
    parser.add_argument(
        "--file", type=Path, default=None,
        help="Principles file to lint (default: the project's configured principles ledger).",
    )


def run(args) -> int:
    # ledger.py's own render_parser sets args.command == "render" (and
    # args.target == "principles", the only target this module owns per
    # ledger.py's _RENDER_TARGET_MODULES); principles-lint's own subparser
    # (registered above) sets args.command == "principles-lint".
    if args.command == "render":
        return _render(args)
    if args.command == "principles-lint":
        return _lint(args)
    raise AssertionError(f"principlescmd: unexpected command {args.command!r}")
