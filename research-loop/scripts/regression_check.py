#!/usr/bin/env python3
"""Oversight-face regression check: new batch vs. the story ledger's active
claims, same-filter comparison only -- reports facts, renders no judgment
(R2, R3; issues/13-oversight.md).

Usage:
    regression_check.py --batch BATCH_ID [--dry-run] [--project-root PATH]

For every active story claim:

- metric_names empty/null -> the claim_id is listed under "Skipped" --
  explicitly, not silently dropped and not treated as a comparison (§9:
  "metric_names 为空的 claim 列入跳过清单，不报冲突也不静默漏掉").
- metric_names non-empty -> for each metric name, the claim's
  evidence_runs rows sharing that metric_name are the old values, grouped
  by their own `filter`; for each distinct filter value seen among them,
  the new batch's rows (runs ledger rows with batch_id=BATCH_ID) sharing
  that same metric_name and filter are the new values. A comparison entry
  is emitted only when at least one new-value row exists for that
  (metric_name, filter) pair -- rows.json story_row.metric_names: "regres-
  sion_check 按它加各 run 行的 filter 同口径重比".

Every comparison entry carries only data fields (claim_id, metric_name,
filter, old, new) -- no adjudicating language anywhere in the rendered
report (R2: "只报事实不判"; this script never decides whether old and new
agree).

Output is one markdown report: a Comparisons table, a Skipped table, and an
R3 provenance block (generated_at, git HEAD, ledger row counts read) in the
file's frontmatter. `--dry-run` prints the report to stdout and writes
nothing (doctor's own call path -- writing under reports/ is the oversight
face's exclusive territory, and doctor must not encroach on it, tables/
writes.json owner_values.oversight); without it, the same text is both
printed and written to `reports/regression-<BATCH_ID>.md`.

Spec: .scratch/research-loop/issues/13-oversight.md; spec.md R2/R3 (§3);
tables/rows.json story_row.metric_names.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _lib  # noqa: E402


def _old_new_item(row: dict) -> dict:
    return {"run_id": row.get("run_id"), "value": row.get("value"), "filter": row.get("filter")}


def build_comparisons(claim: dict, runs_rows: list) -> list:
    """Comparison entries for one active claim -- rows.json story_row.
    metric_names semantics, one entry per (metric_name, filter) pair that
    has at least one matching new-batch row. Caller has already checked
    metric_names is non-empty."""
    evidence_run_ids = set(claim.get("evidence_runs") or [])
    entries = []

    for metric_name in claim["metric_names"]:
        old_rows = [
            r for r in runs_rows
            if r.get("run_id") in evidence_run_ids and r.get("metric_name") == metric_name
        ]
        by_filter: dict = {}
        for row in old_rows:
            by_filter.setdefault(row.get("filter"), []).append(row)

        for filter_value, group in by_filter.items():
            entries.append((metric_name, filter_value, group))

    return entries


def run(cfg, batch_id: str) -> dict:
    story_rows = _lib.jsonl_rows(cfg.ledger_path("story"), include_archive=True)
    runs_rows = _lib.jsonl_rows(cfg.ledger_path("runs"), include_archive=True)

    comparisons = []
    skipped = []

    for claim in story_rows:
        if claim.get("status") != "active":
            continue
        claim_id = claim.get("claim_id")
        metric_names = claim.get("metric_names")
        if not metric_names:
            skipped.append({"claim_id": claim_id})
            continue

        for metric_name, filter_value, old_group in build_comparisons(claim, runs_rows):
            new_group = [
                r for r in runs_rows
                if r.get("batch_id") == batch_id
                and r.get("metric_name") == metric_name
                and r.get("filter") == filter_value
            ]
            if not new_group:
                continue
            comparisons.append({
                "claim_id": claim_id,
                "metric_name": metric_name,
                "filter": filter_value,
                "old": [_old_new_item(r) for r in old_group],
                "new": [_old_new_item(r) for r in new_group],
            })

    return {
        "comparisons": comparisons,
        "skipped": skipped,
        "provenance": {
            "batch_id": batch_id,
            "generated_at": _lib.now_iso(),
            "git_head": _lib.git_head(cfg.root),
            "story_rows_read": len(story_rows),
            "runs_rows_read": len(runs_rows),
        },
    }


# ---------------------------------------------------------------------------
# Rendering -- data fields only, no judgment words (R2)
# ---------------------------------------------------------------------------


def render_report(result: dict) -> str:
    provenance = result["provenance"]
    header_lines = ["---\n"]
    for key in ("batch_id", "generated_at", "git_head", "story_rows_read", "runs_rows_read"):
        header_lines.append(f"{key}: {json.dumps(provenance[key], ensure_ascii=False)}\n")
    header_lines.append("---\n")

    body_lines = [f"\n# Regression check: {provenance['batch_id']}\n\n"]

    body_lines.append("## Comparisons\n\n")
    body_lines.append("| claim_id | metric_name | filter | old | new |\n")
    body_lines.append("|---|---|---|---|---|\n")
    for entry in result["comparisons"]:
        body_lines.append(
            f"| {entry['claim_id']} | {entry['metric_name']} | "
            f"{json.dumps(entry['filter'], ensure_ascii=False)} | "
            f"{json.dumps(entry['old'], ensure_ascii=False)} | "
            f"{json.dumps(entry['new'], ensure_ascii=False)} |\n"
        )

    body_lines.append("\n## Skipped (metric_names empty or null)\n\n")
    body_lines.append("| claim_id |\n")
    body_lines.append("|---|\n")
    for entry in result["skipped"]:
        body_lines.append(f"| {entry['claim_id']} |\n")

    return "".join(header_lines) + "".join(body_lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare a batch's runs against the story ledger's active claims, same filter, facts only.",
    )
    parser.add_argument("--batch", required=True, dest="batch_id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--project-root", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.project_root is not None:
        root = Path(args.project_root).resolve()
    else:
        root = _lib.find_project_root()
        if root is None:
            print(
                "regression_check: project not wired: research-loop.json not found "
                "(pass --project-root)",
                file=sys.stderr,
            )
            return 2

    cfg = _lib.load_config(root)

    try:
        result = run(cfg, args.batch_id)
    except _lib.RLError as exc:
        print(f"regression_check: {exc.message}", file=sys.stderr)
        return 2

    text = render_report(result)
    print(text)

    if not args.dry_run:
        report_path = Path(cfg.ledger_path("reports")) / f"regression-{args.batch_id}.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(text, encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())
