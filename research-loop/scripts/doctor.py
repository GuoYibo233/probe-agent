#!/usr/bin/env python3
"""One-shot health check: config + trace + evidence + principles + regression
+ caps + archives + worktrees + half-state + workplan (issues/14-doctor.md).

Usage:
    doctor.py [--project-root PATH] [--out PATH]

Ten independent sections, each read-only, each run in isolation -- one
section's own crash (an uncaught Python exception raised while building it,
not a subprocess simply exiting non-zero with a normal finding) is caught,
recorded as `section failed: <last 3 lines of the traceback>`, and the run
moves on to the next section (spec.md §5 "半状态由 doctor 扫出", §9 "单项
检查件挂掉能正确汇总"):

1. config      -- subprocess `ledger.py config-check`, relayed verbatim.
2. trace       -- subprocess `trace_check.py`, relayed verbatim.
3. evidence    -- every reports/*.md file, `evidence_lint.py` run once per
                  file (spec: "逐个"), each file's output relayed.
4. principles  -- subprocess `ledger.py principles-lint`, relayed verbatim.
5. regression  -- the runs ledger's latest batch_id (max recorded_at among
                  rows carrying a non-null batch_id) fed to
                  `regression_check.py --batch <id> --dry-run` (--dry-run:
                  doctor must never write under reports/, the oversight
                  face's exclusive territory); no batch at all -> one
                  "skipped" line, not an error.
6. caps        -- each jsonl ledger's row count vs. its effective cap
                  (research-loop.json ledger_caps override, else the
                  ledgers.json table default; null = never capped). At or
                  over cap is a v1-only advisory finding -- archive
                  execution itself is v1.1 (spec.md §10).
7. archives    -- reports the row count of any `<name>.archive.jsonl`
                  sibling that already exists; never itself a finding (v1
                  ships no archive writer, so this is normally empty).
8. worktrees   -- `git worktree list --porcelain` entries beyond the main
                  worktree, plus any directory under the sibling
                  `<repo>-wt/` convention this codebase's own tooling uses.
9. half-state  -- direct jsonl reads (not delegated to any other script) for
                  the three interrupted-complex-write shapes spec.md §5
                  names: an orphan decision (blocked_ref set, but the
                  blocked row's own decision_ref doesn't point back), an
                  interrupted withdrawal (blocked row is withdrawn but its
                  synced decision is still status=decided, or the
                  mechanically-reopened row is missing), and an affects
                  mismatch (a launch order's decision_refs names a decision
                  whose own affects doesn't list that run_id back). Every
                  finding's fix is "the same command, re-run" (spec.md §5
                  "重跑即修复") -- doctor never fixes anything itself.
10. workplan   -- subprocess `ledger.py status --layer deploy`, relayed
                  verbatim (status_view already does the cross-ledger
                  derivation; this section does not reimplement it).

The report goes to stdout always; `--out PATH` additionally writes the exact
same text to that path. Nothing is ever written under reports/ or any
ledger directory, and no ledger is ever touched (only read) -- doctor is
purely advisory, so the exit code is unconditionally 0 (issues/14-doctor.md:
"exit 恒 0（体检是建议件）") for the "nothing found by walking up from cwd"
case: that prints a diagnostic to stderr, same as trace_check.py/
regression_check.py, but (unlike those two) still exits 0 rather than 2.
One case does exit non-zero: an explicit `--project-root` that has no
research-loop.json under it (F2, sdd/final-review.md) -- doctor cannot
advise its way past a caller mistake that would otherwise make every
section below silently read an empty, falsely-clean project, so this one
case exits 2 instead.

Spec: .scratch/research-loop/issues/14-doctor.md; spec.md §4 (doctor
comment block), §5 ("复合动作的中断一致性" ③), §10 (archive is v1-advisory
only).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _lib  # noqa: E402

_SECTION_NAMES = [
    "config", "trace", "evidence", "principles", "regression",
    "caps", "archives", "worktrees", "half-state", "workplan",
]

_TRACE_SUMMARY_RE = re.compile(r"^trace_check:\s*(\d+)\s*errors,\s*(\d+)\s*warnings\s*$")


# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------


def _nonblank_lines(text: str) -> list:
    return [line for line in text.splitlines() if line.strip()]


def _combine_output(out: str, err: str) -> list:
    """Everything a subprocess printed, stdout first then stderr, blank
    lines dropped -- the doctor report relays this verbatim under its own
    section header (spec: "转贴")."""
    return _nonblank_lines(out) + _nonblank_lines(err)


def _scripts_dir() -> Path:
    return _lib.plugin_root() / "scripts"


# ---------------------------------------------------------------------------
# 1. config
# ---------------------------------------------------------------------------


def _section_config(root: Path):
    # ledger.py's dispatcher has no --project-root flag at all (every
    # subcommand resolves its own root by walking up from cwd,
    # _lib.find_project_root() with no argument) -- cwd=root is the only
    # channel available to steer it at the same project doctor itself is
    # reading. Since root is guaranteed to carry research-loop.json (F2,
    # sdd/final-review.md), that walk-up finds it immediately at cwd.
    ledger_py = _scripts_dir() / "ledger.py"
    code, out, err, _elapsed = _lib.run_argv(
        [sys.executable, str(ledger_py), "config-check"], cwd=root,
    )
    return _combine_output(out, err), (0 if code == 0 else 1)


# ---------------------------------------------------------------------------
# 2. trace
# ---------------------------------------------------------------------------


def _section_trace(root: Path):
    trace_check_py = _scripts_dir() / "trace_check.py"
    # --project-root is passed explicitly, not left to trace_check.py's own
    # cwd-search fallback (which `cwd=root` alone would otherwise rely on)
    # -- root is doctor's own already-resolved root (F2, sdd/final-
    # review.md); every subprocess this module launches should read the
    # same project doctor itself is reading, not re-derive it.
    code, out, err, _elapsed = _lib.run_argv(
        [sys.executable, str(trace_check_py), "--project-root", str(root)], cwd=root,
    )
    lines = _combine_output(out, err)
    findings = None
    for line in _nonblank_lines(out):
        match = _TRACE_SUMMARY_RE.match(line.strip())
        if match:
            findings = int(match.group(1)) + int(match.group(2))
            break
    if findings is None:
        findings = 1 if code != 0 else 0
    return lines, findings


# ---------------------------------------------------------------------------
# 3. evidence
# ---------------------------------------------------------------------------


def _section_evidence(cfg: _lib.Config, root: Path):
    reports_dir = Path(cfg.ledger_path("reports"))
    if not reports_dir.exists():
        return ["no reports/ directory"], 0

    md_files = sorted(reports_dir.glob("*.md"))
    if not md_files:
        return ["no report files under reports/"], 0

    evidence_lint_py = _scripts_dir() / "evidence_lint.py"
    lines = []
    findings = 0
    for path in md_files:
        _code, out, err, _elapsed = _lib.run_argv(
            [sys.executable, str(evidence_lint_py), str(path)], cwd=root,
        )
        lines.extend(_combine_output(out, err))
        findings += len(_nonblank_lines(out))

    if not lines:
        lines = [f"{len(md_files)} report file(s) checked, clean"]
    return lines, findings


# ---------------------------------------------------------------------------
# 4. principles
# ---------------------------------------------------------------------------


def _section_principles(root: Path):
    ledger_py = _scripts_dir() / "ledger.py"
    code, out, err, _elapsed = _lib.run_argv(
        [sys.executable, str(ledger_py), "principles-lint"], cwd=root,
    )
    lines = _combine_output(out, err)
    findings = len(_nonblank_lines(err)) if code != 0 else 0
    return lines, findings


# ---------------------------------------------------------------------------
# 5. regression
# ---------------------------------------------------------------------------


def _latest_batch_id(cfg: _lib.Config):
    rows = _lib.jsonl_rows(cfg.ledger_path("runs"), include_archive=True)
    candidates = [
        (row.get("recorded_at") or "", row.get("batch_id"))
        for row in rows if row.get("batch_id")
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[-1][1]


def _section_regression(cfg: _lib.Config, root: Path):
    batch_id = _latest_batch_id(cfg)
    if batch_id is None:
        return ["skipped: no batch_id found in the runs ledger"], 0

    regression_check_py = _scripts_dir() / "regression_check.py"
    # --project-root passed explicitly, same reasoning as _section_trace above.
    code, out, err, _elapsed = _lib.run_argv(
        [
            sys.executable, str(regression_check_py),
            "--batch", batch_id, "--dry-run", "--project-root", str(root),
        ],
        cwd=root,
    )
    return _combine_output(out, err), (0 if code == 0 else 1)


# ---------------------------------------------------------------------------
# 6/7. caps + archives share the same "which jsonl ledgers exist" listing
# ---------------------------------------------------------------------------


def _jsonl_ledger_names(cfg: _lib.Config) -> list:
    """Every main-table jsonl ledger, plus any optional jsonl ledger
    (runs_legacy) that this project has actually hooked into
    research-loop.json's own `ledgers` key -- an optional ledger only
    exists once freeze-legacy has run (tables/ledgers.json runs_legacy
    _note), so an un-hooked one has no on-disk file to count."""
    tables = _lib.load_tables()
    ledgers_table = tables["ledgers"]["ledgers"]
    optional_table = tables["ledgers"].get("optional_ledgers", {})
    hooked = cfg.data.get("ledgers") or {}

    names = [name for name, entry in ledgers_table.items() if entry.get("format") == "jsonl"]
    names += [
        name for name, entry in optional_table.items()
        if entry.get("format") == "jsonl" and name in hooked
    ]
    return sorted(names)


def _section_caps(cfg: _lib.Config):
    tables = _lib.load_tables()
    ledgers_table = tables["ledgers"]["ledgers"]
    optional_table = tables["ledgers"].get("optional_ledgers", {})
    caps_override = cfg.data.get("ledger_caps") or {}

    lines = []
    findings = 0
    for name in _jsonl_ledger_names(cfg):
        entry = ledgers_table.get(name) or optional_table.get(name)
        cap = caps_override.get(name, entry.get("cap"))
        if cap is None:
            continue
        count = len(_lib.jsonl_rows(cfg.ledger_path(name)))
        if count >= cap:
            lines.append(
                f"caps.{name}: {count} rows >= cap {cap}; "
                "archive lands in v1.1; trim manually or raise the cap"
            )
            findings += 1
        else:
            lines.append(f"caps.{name}: {count}/{cap}")

    if not lines:
        lines = ["no capped jsonl ledgers"]
    return lines, findings


def _section_archives(cfg: _lib.Config):
    lines = []
    for name in _jsonl_ledger_names(cfg):
        path = Path(cfg.ledger_path(name))
        archive_path = path.with_name(f"{path.stem}.archive{path.suffix}")
        if archive_path.exists():
            count = len(_lib.jsonl_rows(archive_path))
            lines.append(f"archives.{name}: {count} rows in {archive_path.name}")

    if not lines:
        lines = ["no archive files present"]
    return lines, 0  # v1: archive existing is never itself a finding (spec.md §10)


# ---------------------------------------------------------------------------
# 8. worktrees
# ---------------------------------------------------------------------------


def _parse_worktree_paths(porcelain_out: str) -> list:
    return [
        line[len("worktree "):].strip()
        for line in porcelain_out.splitlines()
        if line.startswith("worktree ")
    ]


def _section_worktrees(root: Path):
    lines = []
    findings = 0

    code, out, _err, _elapsed = _lib.run_argv(
        ["git", "worktree", "list", "--porcelain"], cwd=root,
    )
    if code == 0:
        extra = _parse_worktree_paths(out)[1:]  # [0] is the main worktree itself
        for path in extra:
            lines.append(f"worktree: {path}")
        findings += len(extra)
    else:
        lines.append("not a git repository (or git unavailable): skipping worktree list")

    sibling_dir = root.parent / f"{root.name}-wt"
    if sibling_dir.is_dir():
        for child in sorted(sibling_dir.iterdir()):
            if child.is_dir():
                lines.append(f"stray worktree dir: {child}")
                findings += 1

    if not lines:
        lines = ["no extra worktrees"]
    return lines, findings


# ---------------------------------------------------------------------------
# 9. half-state (direct jsonl reads -- see module docstring)
# ---------------------------------------------------------------------------


def _load_launch_orders(cfg: _lib.Config) -> dict:
    directory = Path(cfg.ledger_path("launch_orders"))
    orders = {}
    if not directory.exists():
        return orders
    for path in sorted(directory.glob("*.json")):
        try:
            orders[path.stem] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue  # a corrupt launch order is trace_check's finding, not this scan's
    return orders


def _orphan_decision_findings(decisions_rows: list, blocked_by_id: dict) -> list:
    out = []
    for decision in decisions_rows:
        blocked_ref = decision.get("blocked_ref")
        if not blocked_ref:
            continue
        blocked_row = blocked_by_id.get(blocked_ref)
        if blocked_row is None:
            continue  # broken reference entirely -- trace_check's territory, not this scan's
        if blocked_row.get("decision_ref") != decision.get("decision_id"):
            out.append(
                f"orphan decision: decision {decision.get('decision_id')} blocked_ref="
                f"{blocked_ref} but blocked {blocked_ref} decision_ref="
                f"{blocked_row.get('decision_ref')!r} -> "
                f"re-run: ledger.py blocked answer {blocked_ref} ..."
            )
    return out


def _synced_decision(blocked_id: str, blocked_row: dict, decisions_rows: list, decisions_by_id: dict):
    decision_ref = blocked_row.get("decision_ref")
    if decision_ref:
        found = decisions_by_id.get(decision_ref)
        if found is not None:
            return found
    for decision in decisions_rows:
        if decision.get("blocked_ref") == blocked_id:
            return decision
    return None


def _withdrawal_interrupted_findings(blocked_rows: list, decisions_rows: list, decisions_by_id: dict) -> list:
    out = []
    for row in blocked_rows:
        if row.get("status") != "withdrawn":
            continue
        blocked_id = row["blocked_id"]

        synced = _synced_decision(blocked_id, row, decisions_rows, decisions_by_id)
        decision_still_decided = synced is not None and synced.get("status") == "decided"

        reopened = any(
            r.get("ref") == blocked_id and r.get("status") == "open" for r in blocked_rows
        )

        if decision_still_decided or not reopened:
            out.append(
                f"interrupted withdrawal: blocked {blocked_id} is withdrawn but not fully "
                f"converged -> re-run: ledger.py blocked withdraw {blocked_id} --reason ..."
            )
    return out


def _affects_mismatch_findings(launch_orders: dict, decisions_by_id: dict, cfg: _lib.Config) -> list:
    out = []
    launch_orders_dir = Path(cfg.ledger_path("launch_orders"))
    for run_id, order in launch_orders.items():
        for decision_id in order.get("decision_refs") or []:
            drow = decisions_by_id.get(decision_id)
            if drow is None:
                continue  # broken reference entirely -- trace_check's territory, not this scan's
            affects = drow.get("affects") or []
            if run_id not in affects:
                lo_path = launch_orders_dir / f"{run_id}.json"
                out.append(
                    f"affects mismatch: decision {decision_id} affects is missing run_id "
                    f"{run_id} -> re-run: ledger.py launch-order --layer deploy --file {lo_path}"
                )
    return out


def _section_half_state(cfg: _lib.Config):
    decisions_rows = _lib.jsonl_rows(cfg.ledger_path("decisions"), include_archive=True)
    blocked_rows = _lib.jsonl_rows(cfg.ledger_path("blocked"), include_archive=True)
    decisions_by_id = {d["decision_id"]: d for d in decisions_rows if d.get("decision_id")}
    blocked_by_id = {b["blocked_id"]: b for b in blocked_rows if b.get("blocked_id")}
    launch_orders = _load_launch_orders(cfg)

    findings = []
    findings.extend(_orphan_decision_findings(decisions_rows, blocked_by_id))
    findings.extend(_withdrawal_interrupted_findings(blocked_rows, decisions_rows, decisions_by_id))
    findings.extend(_affects_mismatch_findings(launch_orders, decisions_by_id, cfg))

    lines = findings or ["no half-state anomalies found"]
    return lines, len(findings)


# ---------------------------------------------------------------------------
# 10. workplan
# ---------------------------------------------------------------------------


def _section_workplan(root: Path):
    ledger_py = _scripts_dir() / "ledger.py"
    code, out, err, _elapsed = _lib.run_argv(
        [sys.executable, str(ledger_py), "status", "--layer", "deploy"], cwd=root,
    )
    lines = _combine_output(out, err)

    if code != 0:
        return lines, 1
    try:
        view = json.loads(out)
    except json.JSONDecodeError:
        return lines, 1
    return lines, len(view.get("inconsistencies") or [])


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

_SECTION_FUNCS = {
    "config": lambda cfg, root: _section_config(root),
    "trace": lambda cfg, root: _section_trace(root),
    "evidence": lambda cfg, root: _section_evidence(cfg, root),
    "principles": lambda cfg, root: _section_principles(root),
    "regression": lambda cfg, root: _section_regression(cfg, root),
    "caps": lambda cfg, root: _section_caps(cfg),
    "archives": lambda cfg, root: _section_archives(cfg),
    "worktrees": lambda cfg, root: _section_worktrees(root),
    "half-state": lambda cfg, root: _section_half_state(cfg),
    "workplan": lambda cfg, root: _section_workplan(root),
}


def _traceback_tail(n: int = 3) -> str:
    tb_lines = [line for line in traceback.format_exc().splitlines() if line.strip()]
    return " | ".join(tb_lines[-n:])


def build_report(root: Path) -> str:
    cfg = _lib.load_config(root)

    lines = []
    total_findings = 0
    for name in _SECTION_NAMES:
        lines.append(f"== {name} ==")
        try:
            section_lines, findings = _SECTION_FUNCS[name](cfg, root)
        except Exception:
            lines.append(f"section failed: {_traceback_tail(3)}")
            total_findings += 1
        else:
            lines.extend(section_lines)
            total_findings += findings
        lines.append("")

    lines.append(f"doctor: {total_findings} findings across {len(_SECTION_NAMES)} sections")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="One-shot read-only health check across every research-loop ledger "
                    "and check script; always exits 0 -- doctor is purely advisory.",
    )
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        root = _lib.resolve_project_root(args.project_root)
    except _lib.RLError as exc:
        # The one exception to "doctor always exits 0" (issues/14-doctor.md):
        # an explicit --project-root that doesn't actually point at a wired
        # project is a caller mistake doctor cannot advise its way past --
        # every section below would just read as an empty, falsely-clean
        # project (F2, sdd/final-review.md). The no-flag "nothing found by
        # walking up from cwd" branch below is unaffected and still exits 0.
        print(f"doctor: {exc.message}", file=sys.stderr)
        return 2
    if root is None:
        print(
            "doctor: project not wired: research-loop.json not found (run: ledger.py init)",
            file=sys.stderr,
        )
        return 0

    report = build_report(root)
    print(report, end="")
    if args.out is not None:
        args.out.write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
