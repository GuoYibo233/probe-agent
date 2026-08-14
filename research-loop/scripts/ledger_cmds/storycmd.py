"""`ledger.py story add|retire` -- the story ledger's two write entries
(issues/06-story-feedback.md).

`story add` is idea-layer exclusive: it appends a new claim after checking
every referenced run (evidence_runs/baseline_runs/candidate_runs, read
cross-archive per spec.md §2.1) exists, is status=ok, and is not a quick run
(spec.md §2.6) -- and, when metric_names is given, that every metric name is
present on every referenced run. `story retire` is the withdrawal-proxy
special case (tables/writes.json withdrawal_proxy.story): any session may
retire a claim without a --layer, but the user's own words are mandatory and
land verbatim in retired_reason.

`--baseline-runs` is optional (#157, rows.json story_row.baseline_runs):
omitted entirely, the claim lands with baseline_runs=null -- a single-arm
absolute statement, not a comparison with the baseline left unspecified.
Given, its run set must not equal candidate_runs' set exactly -- a claim
"compared" against itself is empty and the write is refused.
"""
from __future__ import annotations

import json

import _lib


def _split_csv(value) -> list:
    """'a, b,c' -> ['a', 'b', 'c']; None or '' -> []."""
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _check_referenced_runs(run_ids, runs_rows) -> None:
    """rows.json story_row._write_check: every referenced run_id must exist
    in the runs ledger, have status=ok, and not be a quick run. All three
    violations are reported under the evidence_runs field path (issues/
    06-story-feedback.md's literal error-format list), regardless of which
    of the three run-list arguments the offending run_id came from."""
    for run_id in run_ids:
        matches = [row for row in runs_rows if row.get("run_id") == run_id]
        if not matches:
            _lib.fail("story", "evidence_runs", "run not found", run_id)
        if matches[0].get("status") != "ok":
            _lib.fail("story", "evidence_runs", "run status is not ok", run_id)
        if matches[0].get("quick") is True:
            _lib.fail(
                "story", "evidence_runs",
                "quick runs cannot enter the story ledger", run_id,
            )


def _check_metric_names(metric_names, referenced_run_ids, runs_rows) -> None:
    """Each metric in metric_names must appear (as a metric_name column
    value) on every one of the referenced runs -- spec §9 'metric_names
    指向不存在的指标则 story 写入拒'."""
    if not metric_names:
        return
    seen_runs = []
    for run_id in referenced_run_ids:
        if run_id not in seen_runs:
            seen_runs.append(run_id)
    for metric in metric_names:
        for run_id in seen_runs:
            run_metrics = {
                row.get("metric_name") for row in runs_rows if row.get("run_id") == run_id
            }
            if metric not in run_metrics:
                _lib.fail(
                    "story", "metric_names",
                    "metric not found in referenced run", metric,
                )


def _cmd_add(args, cfg) -> int:
    if args.layer != "idea":
        _lib.fail("story", "layer", "story add is idea-layer only", args.layer)

    evidence_runs = _split_csv(args.evidence_runs)
    # #157: --baseline-runs is optional now -- not given at all means
    # baseline_runs=null (a single-arm claim, no comparison), distinct from
    # "given but empty" (which _split_csv would also turn into [] -- that
    # still counts as "given" for the equality check below, same as any
    # other explicit baseline set).
    baseline_runs = _split_csv(args.baseline_runs) if args.baseline_runs is not None else None
    candidate_runs = _split_csv(args.candidate_runs)
    metric_names = _split_csv(args.metric_names) if args.metric_names is not None else None

    if baseline_runs is not None and set(baseline_runs) == set(candidate_runs):
        _lib.fail(
            "story", "baseline_runs",
            "baseline set equals candidate set; a comparison against itself is empty",
            baseline_runs,
        )

    referenced_runs = evidence_runs + (baseline_runs or []) + candidate_runs
    runs_rows = _lib.jsonl_rows(cfg.ledger_path("runs"), include_archive=True)
    _check_referenced_runs(referenced_runs, runs_rows)
    _check_metric_names(metric_names, referenced_runs, runs_rows)

    story_path = cfg.ledger_path("story")
    schema = _lib.load_schema("story")

    with _lib.locked(story_path):
        existing = _lib.jsonl_rows(story_path, include_archive=True)
        row = {
            "claim_id": _lib.alloc_id(existing, "claim_id", "S"),
            "claim": args.claim,
            "evidence_runs": evidence_runs,
            "baseline_runs": baseline_runs,
            "candidate_runs": candidate_runs,
            "metric_names": metric_names,
            "selection_rule": args.selection_rule,
            "derivation_command": args.derivation_command,
            "principle_id": args.principle_id,
            "role": args.role,
            "decided_by": "user",
            "date": _lib.today(),
            "status": "active",
            "retired_reason": None,
            "retired_date": None,
            "retired_by": None,
            "superseded_by": None,
            "note": None,
            "schema_version": 1,
        }
        _lib.validate(row, schema, "story")
        _lib.jsonl_append(story_path, row)

    print(json.dumps(row, ensure_ascii=False))
    return 0


def _cmd_retire(args, cfg) -> int:
    # withdrawal_proxy: "无用户原话拒" -- --reason must carry the user's own
    # words, not just be present.
    if not args.reason or not args.reason.strip():
        _lib.fail(
            "story", "retired_reason",
            "withdrawal requires the user's own words",
        )

    story_path = cfg.ledger_path("story")
    updates = {
        "status": "retired",
        "retired_reason": args.reason,
        "retired_date": _lib.today(),
        "retired_by": "user",
    }
    if args.superseded_by is not None:
        existing = _lib.jsonl_rows(story_path, include_archive=True)
        if not any(row.get("claim_id") == args.superseded_by for row in existing):
            _lib.fail("story", "superseded_by", "claim not found", args.superseded_by)
        updates["superseded_by"] = args.superseded_by

    whitelist = {"status", "retired_reason", "retired_date", "retired_by", "superseded_by"}
    with _lib.locked(story_path):
        row = _lib.inplace_update(story_path, "claim_id", args.claim_id, updates, whitelist)

    print(json.dumps(row, ensure_ascii=False))
    return 0


def register(subparsers) -> None:
    parser = subparsers.add_parser("story", help="Story ledger: story add / story retire.")
    sub = parser.add_subparsers(dest="story_command", required=True)

    add_p = sub.add_parser("add", help="Append a new story claim (idea layer only).")
    add_p.add_argument("--layer", required=True)
    add_p.add_argument("--claim", required=True)
    add_p.add_argument("--evidence-runs", required=True)
    add_p.add_argument("--baseline-runs", default=None)
    add_p.add_argument("--candidate-runs", required=True)
    add_p.add_argument("--metric-names", default=None)
    add_p.add_argument("--selection-rule", required=True)
    add_p.add_argument("--derivation-command", required=True)
    add_p.add_argument("--principle-id", required=True)
    add_p.add_argument("--role", required=True)

    retire_p = sub.add_parser("retire", help="Retire a story claim (withdrawal proxy; no --layer).")
    retire_p.add_argument("claim_id", metavar="SID")
    retire_p.add_argument("--reason", required=True)
    retire_p.add_argument("--superseded-by", default=None)


def run(args) -> int:
    root = _lib.find_project_root()
    cfg = _lib.load_config(root)
    if args.story_command == "add":
        return _cmd_add(args, cfg)
    if args.story_command == "retire":
        return _cmd_retire(args, cfg)
    raise AssertionError(f"unhandled story_command: {args.story_command}")
