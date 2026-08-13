"""`ledger.py status --layer L` (issues/09-query-status.md; spec §2/§2.1).

The single input/output contract is tables/rows.json `status_view`: every
field's derivation is spelled out there and this module only implements that
sentence -- it does not invent extra derivation rules. The whole command is
a pure read: no ledger is written, no cache file is created, nothing is
locked. Two breakpoints a session hits every time it opens a new context
window (§2 "会话开工必读") come from this same view: the working-face fields
below, and the pending/waiting fields that double as the open-decisions
queue.

jobs.json is read tolerantly (plan.md §C5): both the fallback shape (a dict
keyed by run_id) and a list-of-dicts shape are accepted, keyed off
run_id/name and state/status; an entry that parses as neither is skipped,
not raised on -- run-layer's own jobs ledger is read-only from here and this
module has no write right to reject on its behalf (writes.json owner_values:
jobs is owner=run).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import _lib
from ledger_cmds import decisionscmd, querycmd

_STATUS_SCHEMA_VERSION = 1

# rows.json issue_min / the ticket's own "Status: <value>" line convention
# (visible at the top of every issues/*.md file in this very repo).
_STATUS_LINE_RE = re.compile(r"^Status:\s*(.+?)\s*$", re.MULTILINE)

# Ticket's own wording for approved_specs_in_flight/open_issues: "终态=
# {resolved, wontfix}" -- deliberately not the five triage-label tags
# (docs/agents/triage-labels.md is a different, project-level vocabulary).
_TERMINAL_ISSUE_STATUSES = {"resolved", "wontfix"}

_TERMINAL_JOB_STATES = {"done", "failed", "timeout"}


def _context():
    root = _lib.find_project_root()
    return _lib.load_config(root)


def _rel(cfg, path) -> str:
    """Path -> string relative to the project root when possible (matches
    this plugin's existing convention of root-relative evidence paths, e.g.
    runs_row.output_dir); falls back to the absolute string for anything
    that isn't actually under root (shouldn't happen for our own ledgers)."""
    path = Path(path)
    try:
        return str(path.relative_to(cfg.root))
    except ValueError:
        return str(path)


# ---------------------------------------------------------------------------
# approved_specs_in_flight / open_issues -- both read the specs/issues
# ledgers' md files directly (read class md-full; status_view is exempt from
# the query-only rule, same as every other cross-ledger derivation here).
# ---------------------------------------------------------------------------


def _issue_status(path) -> str | None:
    text = Path(path).read_text(encoding="utf-8")
    match = _STATUS_LINE_RE.search(text)
    return match.group(1) if match else None


def _spec_files(cfg):
    specs_root = Path(cfg.ledger_path("specs"))
    if not specs_root.exists():
        return []
    return sorted(specs_root.rglob("*.md"))


def _issue_files(cfg):
    """ledgers.json's issues default_path is itself a glob pattern
    (".scratch/*/issues/") -- resolve it relative to root and glob for
    *.md, so a project's config override (also expected to be a glob
    pattern) is honored the same way."""
    issues_pattern = Path(cfg.ledger_path("issues"))
    rel = issues_pattern.relative_to(cfg.root)
    return sorted(cfg.root.glob(str(rel / "*.md")))


def _approved_specs_in_flight(cfg) -> list:
    out = []
    for spec_path in _spec_files(cfg):
        text = spec_path.read_text(encoding="utf-8")
        try:
            fields, _body = _lib.parse_frontmatter(text)
        except _lib.RLError:
            continue  # not a frontmatter'd spec file -- not a candidate
        if not fields.get("approved_by"):
            continue
        issues_dir = spec_path.parent / "issues"
        if not issues_dir.is_dir():
            continue
        has_open = False
        for issue_path in sorted(issues_dir.glob("*.md")):
            status = _issue_status(issue_path)
            if status is not None and status not in _TERMINAL_ISSUE_STATUSES:
                has_open = True
                break
        if has_open:
            out.append(_rel(cfg, spec_path))
    return sorted(out)


def _open_issues(cfg) -> list:
    out = []
    for issue_path in _issue_files(cfg):
        status = _issue_status(issue_path)
        if status is not None and status not in _TERMINAL_ISSUE_STATUSES:
            out.append({"issue_id": issue_path.stem, "path": _rel(cfg, issue_path)})
    return sorted(out, key=lambda x: x["issue_id"])


# ---------------------------------------------------------------------------
# jobs.json read (tolerant, plan.md §C5) + the fields derived from it
# ---------------------------------------------------------------------------


def _load_jobs(cfg) -> dict:
    """{run_id: state_string}, tolerant of both the fallback dict-keyed-by-
    run_id shape and a list-of-dicts shape."""
    jobs_path = Path(cfg.ledger_path("jobs"))
    if not jobs_path.exists():
        return {}
    try:
        data = json.loads(jobs_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

    jobs: dict = {}
    if isinstance(data, dict):
        for key, entry in data.items():
            if not isinstance(entry, dict):
                continue
            run_id = entry.get("run_id") or entry.get("name") or key
            state = entry.get("state", entry.get("status"))
            if state is None:
                continue
            jobs[run_id] = state
    elif isinstance(data, list):
        for entry in data:
            if not isinstance(entry, dict):
                continue
            run_id = entry.get("run_id") or entry.get("name")
            state = entry.get("state", entry.get("status"))
            if run_id is None or state is None:
                continue
            jobs[run_id] = state
    return jobs


def _running_runs(jobs: dict) -> list:
    return sorted(run_id for run_id, state in jobs.items() if state == "running")


def _unrecorded_runs(cfg, jobs: dict) -> list:
    runs_ids = {r.get("run_id") for r in _lib.jsonl_rows(cfg.ledger_path("runs"))}
    return sorted(
        run_id for run_id, state in jobs.items()
        if state in _TERMINAL_JOB_STATES and run_id not in runs_ids
    )


def _pending_launch_orders(cfg, jobs: dict) -> list:
    out = []
    for path, order in querycmd._iter_launch_orders(cfg):
        run_id = order.get("run_id")
        if run_id is None or run_id in jobs:
            continue
        out.append({"run_id": run_id, "path": _rel(cfg, path)})
    return sorted(out, key=lambda x: x["run_id"])


# ---------------------------------------------------------------------------
# batch_reports frontmatter (read once, shared by three derivations)
# ---------------------------------------------------------------------------


def _batch_report_headers(cfg) -> list:
    """[(path, frontmatter_fields), ...] for every plans/*.md whose header
    parses -- a file without frontmatter is skipped, not raised on."""
    reports_root = Path(cfg.ledger_path("batch_reports"))
    if not reports_root.exists():
        return []
    out = []
    for path in sorted(reports_root.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        try:
            fields, _body = _lib.parse_frontmatter(text)
        except _lib.RLError:
            continue
        out.append((path, fields))
    return out


def _batches_pending_report(cfg, batch_headers: list) -> list:
    runs_rows = _lib.jsonl_rows(cfg.ledger_path("runs"))
    batch_ids = sorted({r.get("batch_id") for r in runs_rows if r.get("batch_id")})
    reported = {fields.get("batch_id") for _path, fields in batch_headers}
    return [b for b in batch_ids if b not in reported]


def _batches_pending_inspection(cfg, batch_headers: list) -> list:
    out = [
        {"batch_id": fields.get("batch_id"), "path": _rel(cfg, path)}
        for path, fields in batch_headers
        if fields.get("inspection_report") == ""
    ]
    return sorted(out, key=lambda x: (x["batch_id"] or "", x["path"]))


# ---------------------------------------------------------------------------
# blocked / decisions derivations
# ---------------------------------------------------------------------------


def _open_blocked(blocked_rows: list) -> list:
    return sorted(r["blocked_id"] for r in blocked_rows if r.get("status") == "open")


def _pending_user_decisions(blocked_rows: list) -> list:
    return sorted(
        r["blocked_id"] for r in blocked_rows
        if r.get("status") == "open" and r.get("to_layer") == "user"
    )


def _active_grants(cfg, now: str) -> list:
    decisions_rows = _lib.jsonl_rows(cfg.ledger_path("decisions"))
    return sorted(g["decision_id"] for g in decisionscmd.active_grants(decisions_rows, now))


# ---------------------------------------------------------------------------
# waiting_on -- action text is routes.json's own "to" column, verbatim
# ---------------------------------------------------------------------------


def _route_to(tables: dict, say_prefix: str) -> str | None:
    for route in tables["routes"]["routes"]:
        if route["say"].startswith(say_prefix):
            return route["to"]
    return None


def _waiting_on(pending_user_decision_ids: list, batches_pending_inspection_list: list) -> list:
    tables = _lib.load_tables()
    decide_action = _route_to(tables, "有什么在等我")
    inspect_action = _route_to(tables, "深查这批")
    if decide_action is None or inspect_action is None:
        _lib.fail(
            "status", "waiting_on",
            "tables/routes.json is missing an expected route entry",
        )

    out = []
    for blocked_id in pending_user_decision_ids:
        out.append({"item": "blocked", "ref": blocked_id, "layer": "user", "action": decide_action})
    for entry in batches_pending_inspection_list:
        out.append(
            {"item": "batch", "ref": entry["batch_id"], "layer": "deploy", "action": inspect_action}
        )
    return out


# ---------------------------------------------------------------------------
# inconsistencies -- exactly the three cheap cross-checks the ticket names
# ---------------------------------------------------------------------------


def _inconsistencies(cfg, jobs: dict, batch_headers: list, runtime_factor: int, now: str) -> list:
    out = []
    runs_rows = _lib.jsonl_rows(cfg.ledger_path("runs"))
    runs_by_id: dict = {}
    for row in runs_rows:
        runs_by_id.setdefault(row.get("run_id"), row)

    # ① a batch report's run_ids[] pointing at a run the runs ledger has no
    # row for.
    for path, fields in batch_headers:
        for run_id in fields.get("run_ids") or []:
            if run_id not in runs_by_id:
                out.append(
                    {"code": "report-run-missing", "ref": run_id, "source": _rel(cfg, path)}
                )

    # ② jobs terminal state vs. the runs ledger's own status disagreeing.
    jobs_path_rel = _rel(cfg, cfg.ledger_path("jobs"))
    for run_id in sorted(jobs):
        state = jobs[run_id]
        row = runs_by_id.get(run_id)
        if row is None:
            continue
        status = row.get("status")
        mismatch = (state == "done" and status != "ok") or (
            state in ("failed", "timeout") and status == "ok"
        )
        if mismatch:
            out.append(
                {"code": "jobs-runs-status-mismatch", "ref": run_id, "source": jobs_path_rel}
            )

    # ③ a launch order old enough (created_at + expected_runtime_s ×
    # runtime_factor) to be overdue, with jobs still carrying no entry.
    try:
        now_dt = datetime.fromisoformat(now)
    except ValueError:
        now_dt = None
    if now_dt is not None:
        for path, order in querycmd._iter_launch_orders(cfg):
            run_id = order.get("run_id")
            created_at = order.get("created_at")
            expected_runtime_s = order.get("expected_runtime_s")
            if run_id is None or run_id in jobs or not created_at or expected_runtime_s is None:
                continue
            try:
                created_dt = datetime.fromisoformat(created_at)
            except ValueError:
                continue
            deadline = created_dt + timedelta(seconds=expected_runtime_s * runtime_factor)
            if now_dt > deadline:
                out.append({"code": "launch-overdue", "ref": run_id, "source": _rel(cfg, path)})

    return out


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "status", help="Cross-ledger working-face + pending-queue snapshot (read-only)."
    )
    layer_values = _lib.load_tables()["writes"]["layer_param"]["values"]
    parser.add_argument("--layer", required=True, choices=layer_values)


def run(args) -> int:
    cfg = _context()
    now = _lib.now_iso()

    jobs = _load_jobs(cfg)
    blocked_rows = _lib.jsonl_rows(cfg.ledger_path("blocked"))
    batch_headers = _batch_report_headers(cfg)
    runtime_factor = cfg.get("runtime_factor")

    pending_user_decisions = _pending_user_decisions(blocked_rows)
    batches_pending_inspection = _batches_pending_inspection(cfg, batch_headers)

    view = {
        "schema_version": _STATUS_SCHEMA_VERSION,
        "generated_at": now,
        "layer": args.layer,
        "approved_specs_in_flight": _approved_specs_in_flight(cfg),
        "open_issues": _open_issues(cfg),
        "pending_launch_orders": _pending_launch_orders(cfg, jobs),
        "running_runs": _running_runs(jobs),
        "unrecorded_runs": _unrecorded_runs(cfg, jobs),
        "batches_pending_report": _batches_pending_report(cfg, batch_headers),
        "batches_pending_inspection": batches_pending_inspection,
        "open_blocked": _open_blocked(blocked_rows),
        "pending_user_decisions": pending_user_decisions,
        "active_grants": _active_grants(cfg, now),
        "waiting_on": _waiting_on(pending_user_decisions, batches_pending_inspection),
        "inconsistencies": _inconsistencies(cfg, jobs, batch_headers, runtime_factor, now),
    }
    print(json.dumps(view, indent=2, ensure_ascii=False))
    return 0
