#!/usr/bin/env python3
"""Deploy-layer traceability check + batch closeout gate.

Usage:
    trace_check.py [--project-root PATH] [--closeout BATCH_ID]

Reads the project's ledgers, launch orders and (in --closeout mode) one
batch report, and reports every broken cross-reference it finds. Every
account is read across main + archive (`_lib.jsonl_rows(..., include_archive=
True)`) -- spec §2.1: "校验/追溯脚本一律跨档读". This script never writes
anything.

Checks (spec §4 trace_check comment block, spec §9, this ticket's own
numbered list -- one function per item):

1. check_forward_chain   -- every non-quick launch order's spec_ref resolves
   under the specs ledger via `_lib.find_spec_files` (a file must both parse
   as frontmatter'd and carry the item_id in its body to count -- F1, sdd/
   final-review.md), issue_ref names an existing issue file, and each
   decision_refs entry exists in the decisions ledger with status=decided.
   Zero matching spec files -> "not found"; two or more -> "ambiguous"
   (every candidate path is named, never silently narrowed to the first).
   quick=true launch orders are exempt from all three (spec §2.6).
2. check_approval         -- for every launch order with a non-empty
   spec_ref whose resolution above found exactly one file: empty
   approved_by -> "not-approved"; recomputed approved_digest mismatch ->
   "approval_stale" (spec_header._digest_rule/_stale_rule). Zero or
   ambiguous resolutions are already reported by check_forward_chain and
   are not re-reported here.
3. check_affects          -- the launch order is authoritative (spec §5):
   forward, each decision_refs entry's own `affects` must name the launch
   order's run_id ("affects-missing", detail carries the re-run fix);
   reverse, each decisions.affects entry that names an existing launch
   order must be named back in that order's decision_refs
   ("affects-extra").
4. check_runs_backlink    -- normal runs.jsonl rows: runmeta_path exists,
   its launch_order_ref resolves, and that launch order's own run_id field
   equals the row's run_id. A RUNMETA file that exists but fails to parse
   as JSON is "runs_backlink.runmeta_unreadable" (not a crash). Criterion
   (judged) rows: principle_id exists in the principles ledger and its
   criterion_cmd passes check_in_registry (registry_query null -> "unwired",
   never silently passed).
5. check_jobs_backlink    -- every jobs-ledger entry's launch_order_ref
   resolves to an existing launch order.
6. check_story_refs       -- every active story claim's evidence_runs /
   baseline_runs / candidate_runs entries exist in the runs ledger and are
   not quick runs.
7. check_promotion        -- launch orders with a non-null promoted_from:
   seed/dataset_version/argv/env_name/filter must equal the source quick
   order's, byte for byte; a mismatch reports "promotion-field-drift" and
   names the drifted field(s).
8. check_closeout         -- only with --closeout BATCH_ID: the batch's
   report exists, its frontmatter inspection_report is non-empty (empty is
   only reported here -- normal runs never flag it, per
   rows.json batch_report_header.inspection_report), and every run_id it
   lists is recorded in the runs ledger.

Loading is itself read-only and fallible the same way: a launch order file
or ops/jobs.json that exists but fails to parse as JSON is reported as
"load.launch_order_unreadable" / "load.jobs_unreadable" and the rest of the
run proceeds on whatever did parse -- one bad file must not crash the whole
check (an uncaught exception) or silently pass as "0 errors" (this script's
entire job is catching exactly this kind of ledger corruption).

Output: one line per finding, `<check>: <detail>`; a final summary line
`trace_check: <N> errors, <M> warnings`. Exit 1 if any error was found
(warnings alone do not fail the run), else 0. --closeout gates on the full
check set (1-7) plus check 8 -- exit 0 only when everything is clean.

Spec: .scratch/research-loop/issues/11-trace-check.md; spec.md §2 ("可追溯链
双向"), §2.6 (quick lane exemptions), §5 ("发射单与台账的顺序", the affects/
approval-gate rules); shape references: research-loop/tables/rows.json
(launch_order, spec_header, batch_report_header, decisions_row, story_row,
runs_row_normal, runs_row_criterion).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _lib  # noqa: E402

try:
    from ledger_cmds.principlescmd import parse_principles as _parse_principles
except ImportError:
    # Only reached in a stripped deployment where ledger_cmds isn't on
    # sys.path; ledger_cmds.principlescmd is always importable in this
    # repo's normal test environment, so the primary branch above always
    # wins here. Exercised (not just hand-verified) by
    # test_trace_check.py::test_import_error_fallback_parses_principles_same_as_primary,
    # which forces this branch via a builtins.__import__ patch + module
    # reload and diffs its output against the real parser's, on the same
    # fixture file, byte for byte.
    import re as _re

    _CELL_SPLIT_RE = _re.compile(r"(?<!\\)\|")

    def _split_row(line: str) -> list:
        stripped = line.strip()
        if stripped.startswith("|"):
            stripped = stripped[1:]
        if stripped.endswith("|"):
            stripped = stripped[:-1]
        return [cell.strip().replace("\\|", "|") for cell in _CELL_SPLIT_RE.split(stripped)]

    def _find_header(lines: list):
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped.startswith("|"):
                continue
            cells = _split_row(stripped)
            if "principle_id" in cells:
                return i, cells
        return None, None

    def _parse_principles(path) -> list:
        """Same-shape fallback for ledger_cmds.principlescmd.parse_principles
        (used only if ledger_cmds isn't importable): parses the first
        markdown table whose header row has a principle_id cell, one dict
        per body row, header cells as keys. Caller pre-checks existence."""
        path = Path(path)
        lines = path.read_text(encoding="utf-8").splitlines()
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


_PROMOTION_FIELDS = ("seed", "dataset_version", "argv", "env_name", "filter")


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------


def _err(check: str, detail: str) -> dict:
    return {"check": check, "severity": "error", "detail": detail}


# ---------------------------------------------------------------------------
# Loading (one pass per ledger, shared by every check function below)
# ---------------------------------------------------------------------------


class _Context:
    """Everything the eight check functions read, loaded once. Nothing in
    here is written back -- trace_check only ever reads."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.root = cfg.root
        # Findings raised while loading the ledgers themselves (malformed
        # JSON) -- collected here rather than raised, so one corrupted file
        # is reported instead of killing the whole run (F2); folded into the
        # regular findings list by run() below.
        self.load_findings = []
        self.launch_orders, launch_order_findings = _load_launch_orders(cfg)
        self.load_findings.extend(launch_order_findings)
        self.decisions_rows = _lib.jsonl_rows(cfg.ledger_path("decisions"), include_archive=True)
        self.decisions_by_id = {row.get("decision_id"): row for row in self.decisions_rows}
        self.runs_rows = _lib.jsonl_rows(cfg.ledger_path("runs"), include_archive=True)
        self.jobs, jobs_findings = _load_jobs(cfg)
        self.load_findings.extend(jobs_findings)
        self.story_rows = _lib.jsonl_rows(cfg.ledger_path("story"), include_archive=True)
        self.principles_rows = _load_principles(cfg)
        self.principles_by_id = {row.get("principle_id"): row for row in self.principles_rows}


def _load_launch_orders(cfg) -> tuple:
    """(orders, findings). orders is {filename stem: parsed launch order
    dict}. The filename stem is the canonical run_id (spec §5: "发射单按
    run_id 命名") -- it is the key used everywhere else in this script
    (RUNMETA/jobs launch_order_ref, decisions.affects, promoted_from). A
    launch order file whose own "run_id" field disagrees with its filename
    is exactly what check_runs_backlink's run_id-mismatch finding is for;
    this loader does not paper over that by keying off the field instead.

    findings carries one "load.launch_order_unreadable" entry per file that
    is not valid JSON (corrupted outside the normal write path, e.g. by a
    non-atomic write racing a reader -- issues/08-launch-order.md notes
    launchcmd.py writes via a plain Path.write_text) -- that file is skipped
    (absent from orders, so it cannot silently satisfy any check that looks
    it up) rather than raising and killing the whole run."""
    directory = Path(cfg.ledger_path("launch_orders"))
    orders = {}
    findings = []
    if not directory.exists():
        return orders, findings
    for path in sorted(directory.glob("*.json")):
        try:
            orders[path.stem] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            findings.append(_err(
                "load.launch_order_unreadable",
                f"launch order file {path} could not be read as JSON: {exc}",
            ))
    return orders, findings


def _load_jobs(cfg) -> tuple:
    """(entries, findings). entries is job-ledger rows as a flat list of
    dicts, each carrying at least a run_id key. plan.md §C5: jobs.json may
    be `{run_id: {...}}` or a list of dicts with a run_id/name key -- read
    both shapes leniently the same way statuscmd is specified to (this
    script never writes jobs.json). findings carries one
    "load.jobs_unreadable" entry (entries then empty) if the file exists but
    is not valid JSON -- reported, not a crash and not a silent 0-jobs read."""
    path = Path(cfg.ledger_path("jobs"))
    if not path.exists():
        return [], []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [], [_err(
            "load.jobs_unreadable",
            f"jobs ledger {path} could not be read as JSON: {exc}",
        )]
    entries = []
    if isinstance(data, dict):
        for run_id, entry in data.items():
            merged = dict(entry) if isinstance(entry, dict) else {}
            merged.setdefault("run_id", merged.get("run_id") or merged.get("name") or run_id)
            entries.append(merged)
    elif isinstance(data, list):
        for entry in data:
            if isinstance(entry, dict):
                merged = dict(entry)
                merged.setdefault("run_id", merged.get("run_id") or merged.get("name"))
                entries.append(merged)
    return entries, []


def _load_principles(cfg) -> list:
    path = Path(cfg.ledger_path("principles"))
    if not path.exists():
        return []
    return _parse_principles(path)


def _issues_glob_pattern(cfg) -> str:
    """Raw ledgers.issues path (default ".scratch/*/issues/", a glob
    pattern per tables/ledgers.json) with a trailing "*.md" -- Config.
    ledger_path() would join it as a literal "*" path component instead of
    resolving it, so this script resolves the glob itself."""
    entry = _lib.load_tables()["ledgers"]["ledgers"]["issues"]
    override = (cfg.data.get("ledgers") or {}).get("issues")
    raw = override if override is not None else entry["default_path"]
    return raw.rstrip("/") + "/*.md"


def _find_issue_file(cfg, issue_ref: str):
    for path in sorted(cfg.root.glob(_issues_glob_pattern(cfg))):
        if path.stem == issue_ref:
            return path
    return None


def _find_batch_report(cfg, batch_id: str):
    """<batch_reports>/<batch_id>.md first (rows.json batch_id_pattern names
    the file this way); falls back to scanning every *.md for a frontmatter
    batch_id field equal to `batch_id`, for reports filed under a different
    name."""
    reports_root = Path(cfg.ledger_path("batch_reports"))
    if not reports_root.exists():
        return None
    candidate = reports_root / f"{batch_id}.md"
    if candidate.exists():
        return candidate
    for path in sorted(reports_root.glob("*.md")):
        try:
            fields, _ = _lib.parse_frontmatter(path.read_text(encoding="utf-8"))
        except _lib.RLError:
            continue
        if fields.get("batch_id") == batch_id:
            return path
    return None


# ---------------------------------------------------------------------------
# 1. Launch-order forward chain
# ---------------------------------------------------------------------------


def check_forward_chain(ctx: _Context) -> list:
    findings = []
    for run_id, order in ctx.launch_orders.items():
        if order.get("quick"):
            continue  # §2.6: quick launch orders are exempt from all three

        spec_ref = order.get("spec_ref")
        if spec_ref:
            matches = _lib.find_spec_files(ctx.cfg, spec_ref)
            if not matches:
                findings.append(_err(
                    "forward_chain.spec_ref",
                    f"launch order {run_id}: spec_ref {spec_ref!r} not found under the specs ledger",
                ))
            elif len(matches) > 1:
                findings.append(_err(
                    "forward_chain.spec_ref",
                    f"launch order {run_id}: spec_ref {spec_ref!r} is ambiguous across "
                    f"{len(matches)} files: {[str(p) for p in matches]}",
                ))

        issue_ref = order.get("issue_ref")
        if issue_ref:
            if _find_issue_file(ctx.cfg, issue_ref) is None:
                findings.append(_err(
                    "forward_chain.issue_ref",
                    f"launch order {run_id}: issue_ref {issue_ref!r} has no matching issue file",
                ))

        for decision_id in order.get("decision_refs") or []:
            drow = ctx.decisions_by_id.get(decision_id)
            if drow is None:
                findings.append(_err(
                    "forward_chain.decision_ref",
                    f"launch order {run_id}: decision_refs entry {decision_id} not found in the decisions ledger",
                ))
            elif drow.get("status") != "decided":
                findings.append(_err(
                    "forward_chain.decision_ref",
                    f"launch order {run_id}: decision_refs entry {decision_id} has status "
                    f"{drow.get('status')!r}, expected 'decided'",
                ))
    return findings


# ---------------------------------------------------------------------------
# 2. Approval face
# ---------------------------------------------------------------------------


def check_approval(ctx: _Context) -> list:
    findings = []
    for run_id, order in ctx.launch_orders.items():
        if order.get("quick"):
            continue  # ticket: "quick 单不受影响"

        spec_ref = order.get("spec_ref")
        if not spec_ref:
            continue

        matches = _lib.find_spec_files(ctx.cfg, spec_ref)
        if len(matches) != 1:
            continue  # not-found / ambiguous already reported by check_forward_chain

        spec_path = matches[0]
        # find_spec_files already required this exact file to parse as
        # frontmatter'd -- re-parsing it here can only fail if the file was
        # rewritten (outside the normal write path) in the instant between
        # that scan and this read, which check_forward_chain's own
        # not-found/ambiguous findings do not cover either; this read is not
        # wrapped in a second try/except (there is nothing left for this
        # function to distinguish that check_forward_chain hasn't already).
        fields, _ = _lib.parse_frontmatter(spec_path.read_text(encoding="utf-8"))

        approved_by = fields.get("approved_by")
        if not approved_by:
            findings.append(_err(
                "not-approved",
                f"launch order {run_id}: spec {spec_path} approved_by is empty",
            ))
            continue

        approved_digest = fields.get("approved_digest")
        actual_digest = _lib.spec_digest(spec_path)
        if approved_digest != actual_digest:
            findings.append(_err(
                "approval_stale",
                f"launch order {run_id}: spec {spec_path} approved_digest {approved_digest!r} "
                f"does not match the recomputed digest {actual_digest!r}",
            ))
    return findings


# ---------------------------------------------------------------------------
# 3. affects consistency (the launch order is authoritative)
# ---------------------------------------------------------------------------


def check_affects(ctx: _Context) -> list:
    findings = []

    for run_id, order in ctx.launch_orders.items():
        for decision_id in order.get("decision_refs") or []:
            drow = ctx.decisions_by_id.get(decision_id)
            if drow is None:
                continue  # already reported by check_forward_chain
            affects = drow.get("affects") or []
            if run_id not in affects:
                findings.append(_err(
                    "affects-missing",
                    f"decision {decision_id} affects does not include run_id {run_id}, which "
                    f"names {decision_id} in its decision_refs; fix: re-run the same "
                    f"`ledger.py launch-order --layer deploy --file <draft>` write for {run_id} "
                    "to backfill affects (spec §5: affects is a physicalized index of "
                    "decision_refs, the launch order is authoritative)",
                ))

    for drow in ctx.decisions_rows:
        decision_id = drow.get("decision_id")
        for ref in drow.get("affects") or []:
            order = ctx.launch_orders.get(ref)
            if order is None:
                continue  # not a run_id (could be a spec item_id / issue_id) -- not this check's concern
            if decision_id not in (order.get("decision_refs") or []):
                findings.append(_err(
                    "affects-extra",
                    f"decision {decision_id} affects run_id {ref}, but launch order {ref}'s "
                    f"decision_refs does not include {decision_id}",
                ))
    return findings


# ---------------------------------------------------------------------------
# 4. runs backlink
# ---------------------------------------------------------------------------


def _check_criterion_registry(ctx: _Context, run_id: str, principle_id: str, cmd: str):
    try:
        argv = _lib.split_cmd(cmd or "", "principles", "criterion_cmd")
        _lib.check_in_registry(argv, ctx.cfg, ledger="principles", field="criterion_cmd")
    except _lib.RLError as exc:
        code = "unwired" if "not wired" in exc.message else "runs_backlink.criterion_cmd"
        return _err(
            code,
            f"runs row {run_id}: principle {principle_id} criterion_cmd check failed: {exc.message}",
        )
    return None


def check_runs_backlink(ctx: _Context) -> list:
    findings = []
    seen_normal_run_ids = set()

    for row in ctx.runs_rows:
        run_id = row.get("run_id")
        principle_id = row.get("principle_id")

        if principle_id is not None:
            # Criterion (judged) row -- rows.json runs_row_criterion: principle_id
            # non-null is the row-type discriminator; each row is its own run_id
            # (primary key = run_id alone), so no per-run_id dedup is needed here.
            if principle_id not in ctx.principles_by_id:
                findings.append(_err(
                    "runs_backlink.principle_missing",
                    f"runs row {run_id}: principle_id {principle_id} not found in the principles ledger",
                ))
                continue
            cmd = ctx.principles_by_id[principle_id].get("criterion_cmd")
            finding = _check_criterion_registry(ctx, run_id, principle_id, cmd)
            if finding is not None:
                findings.append(finding)
            continue

        # Normal row -- rows.json _run_level_fields: runmeta_path is a run-level
        # fact, identical across every metric row sharing this run_id, so one
        # representative row per run_id is enough (avoids N duplicate findings
        # for an N-metric run).
        if run_id in seen_normal_run_ids:
            continue
        seen_normal_run_ids.add(run_id)

        runmeta_path_str = row.get("runmeta_path")
        runmeta_path = (ctx.root / runmeta_path_str) if runmeta_path_str else None
        if not runmeta_path_str or not runmeta_path.exists():
            findings.append(_err(
                "runs_backlink.runmeta_missing",
                f"runs row {run_id}: runmeta_path {runmeta_path_str!r} does not exist",
            ))
            continue

        try:
            runmeta = json.loads(runmeta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            findings.append(_err(
                "runs_backlink.runmeta_unreadable",
                f"runs row {run_id}: runmeta_path {runmeta_path_str!r} could not be read as JSON: {exc}",
            ))
            continue

        launch_order_ref = runmeta.get("launch_order_ref")
        order = ctx.launch_orders.get(launch_order_ref) if launch_order_ref else None
        if not launch_order_ref or order is None:
            findings.append(_err(
                "runs_backlink.launch_order_ref_missing",
                f"runs row {run_id}: RUNMETA.launch_order_ref {launch_order_ref!r} does not "
                "point to an existing launch order",
            ))
            continue

        if order.get("run_id") != run_id:
            findings.append(_err(
                "runs_backlink.run_id_mismatch",
                f"runs row {run_id}: launch order {launch_order_ref} declares run_id "
                f"{order.get('run_id')!r}, expected {run_id!r}",
            ))
    return findings


# ---------------------------------------------------------------------------
# 5. jobs backlink
# ---------------------------------------------------------------------------


def check_jobs_backlink(ctx: _Context) -> list:
    findings = []
    for entry in ctx.jobs:
        run_id = entry.get("run_id")
        launch_order_ref = entry.get("launch_order_ref")
        if not launch_order_ref or launch_order_ref not in ctx.launch_orders:
            findings.append(_err(
                "jobs_backlink",
                f"jobs entry {run_id!r}: launch_order_ref {launch_order_ref!r} does not point "
                "to an existing launch order",
            ))
    return findings


# ---------------------------------------------------------------------------
# 6. story references
# ---------------------------------------------------------------------------


def check_story_refs(ctx: _Context) -> list:
    findings = []
    runs_by_id = {}
    for row in ctx.runs_rows:
        runs_by_id.setdefault(row.get("run_id"), row)

    for story_row in ctx.story_rows:
        if story_row.get("status") != "active":
            continue
        claim_id = story_row.get("claim_id")
        for field in ("evidence_runs", "baseline_runs", "candidate_runs"):
            for run_id in story_row.get(field) or []:
                row = runs_by_id.get(run_id)
                if row is None:
                    findings.append(_err(
                        "story_refs",
                        f"story {claim_id} {field} references run_id {run_id}, which was not "
                        "found in the runs ledger",
                    ))
                elif row.get("quick"):
                    findings.append(_err(
                        "story_refs",
                        f"story {claim_id} {field} references run_id {run_id}, which is a "
                        "quick run (§2.6: quick rows must not be referenced by the story ledger)",
                    ))
    return findings


# ---------------------------------------------------------------------------
# 7. promoted_from field drift
# ---------------------------------------------------------------------------


def check_promotion(ctx: _Context) -> list:
    findings = []
    for run_id, order in ctx.launch_orders.items():
        promoted_from = order.get("promoted_from")
        if not promoted_from:
            continue
        source = ctx.launch_orders.get(promoted_from)
        if source is None:
            continue  # existence is launch-order write time's job (T08), not this check's
        drifted = [field for field in _PROMOTION_FIELDS if order.get(field) != source.get(field)]
        if drifted:
            findings.append(_err(
                "promotion-field-drift",
                f"launch order {run_id}: promoted_from {promoted_from} field drift on {drifted}",
            ))
    return findings


# ---------------------------------------------------------------------------
# 8. --closeout batch gate
# ---------------------------------------------------------------------------


def check_closeout(ctx: _Context, batch_id: str) -> list:
    findings = []
    report_path = _find_batch_report(ctx.cfg, batch_id)
    if report_path is None:
        findings.append(_err(
            "closeout.report_missing",
            f"batch {batch_id}: no batch report found under {ctx.cfg.ledger_path('batch_reports')}",
        ))
        return findings

    try:
        fields, _ = _lib.parse_frontmatter(report_path.read_text(encoding="utf-8"))
    except _lib.RLError as exc:
        findings.append(_err(
            "closeout.report_unreadable",
            f"batch {batch_id}: {report_path}: {exc.message}",
        ))
        return findings

    if not (fields.get("inspection_report") or "").strip():
        findings.append(_err(
            "closeout.inspection_report_empty",
            f"batch {batch_id}: report {report_path} inspection_report is empty (--closeout "
            "requires it filled in; rows.json batch_report_header.inspection_report)",
        ))

    known_run_ids = {row.get("run_id") for row in ctx.runs_rows}
    missing = [rid for rid in (fields.get("run_ids") or []) if rid not in known_run_ids]
    if missing:
        findings.append(_err(
            "closeout.run_id_unrecorded",
            f"batch {batch_id}: report {report_path} run_ids not recorded in the runs ledger: {missing}",
        ))
    return findings


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

_REGULAR_CHECKS = (
    check_forward_chain,
    check_approval,
    check_affects,
    check_runs_backlink,
    check_jobs_backlink,
    check_story_refs,
    check_promotion,
)


def run(root: Path, closeout_batch_id) -> list:
    cfg = _lib.load_config(root)
    ctx = _Context(cfg)
    findings = list(ctx.load_findings)
    for check in _REGULAR_CHECKS:
        findings.extend(check(ctx))
    if closeout_batch_id is not None:
        findings.extend(check_closeout(ctx, closeout_batch_id))
    return findings


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Traceability check: forward/backward reference integrity across every "
                     "research-loop ledger, plus an optional batch closeout gate.",
    )
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--closeout", metavar="BATCH_ID", default=None)
    args = parser.parse_args(argv)

    try:
        root = _lib.resolve_project_root(args.project_root)
    except _lib.RLError as exc:
        print(f"trace_check: {exc.message}", file=sys.stderr)
        return 2
    if root is None:
        print(
            "trace_check: project not wired: research-loop.json not found (run: ledger.py init)",
            file=sys.stderr,
        )
        return 2

    try:
        findings = run(root, args.closeout)
    except _lib.RLError as exc:
        print(f"trace_check: {exc.message}", file=sys.stderr)
        return 2

    errors = [f for f in findings if f["severity"] == "error"]
    warnings = [f for f in findings if f["severity"] == "warning"]
    for finding in findings:
        print(f"{finding['check']}: {finding['detail']}")
    print(f"trace_check: {len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
