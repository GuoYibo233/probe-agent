#!/usr/bin/env python3
"""`ledger.py launch-order|approve-spec` -- writing a launch order and
recording a spec file's approval (issues/08-launch-order.md).

`approve-spec` is the mechanical transcription of a user's approval
(spec.md §2.5: "spec 批准的转录是机械动作：你拍板当场跑 ledger.py
approve-spec"). It takes no --layer -- like decision-withdraw, it is a
direct user act, not a layer-owned write. It rewrites exactly three header
fields (approved_by/approved_date/approved_digest), defaults spec_version
to 1 when absent, and leaves every other header field (withdrawals etc.)
and every body byte untouched.

`launch-order` is deploy-only. It runs a fixed validation order -- schema,
the registry three-check (shared with principlescmd via
_lib.check_in_registry, tables/rows.json launch_order's own registry_task
note), the pre-launch approval gate (spec.md §5 "发射前批准门禁", waived
for quick orders per §2.6), decision_refs existence/status, and
promoted_from -- and only writes once every check has passed. The write
itself is two steps in a fixed order (spec.md §5 "发射单与台账的顺序"):
the launch order file first, then (if decision_refs is non-empty) the
affects backfill on each referenced decisions row -- decision_refs is
authoritative, affects is a rebuildable index, so a crash between the two
steps only ever leaves an index gap that a rerun of this same command
closes (dedup on run_id already present in affects, tables/writes.json
form2_inplace_whitelist.decisions).
"""
from __future__ import annotations

import json
from pathlib import Path

import _lib


def _context():
    root = _lib.find_project_root()
    return _lib.load_config(root)


def _decisions_whitelist():
    return set(
        _lib.load_tables()["writes"]["write_forms"]["form2_inplace_whitelist"]["decisions"]
    )


def register(subparsers):
    layer_choices = _lib.load_tables()["writes"]["layer_param"]["values"]

    lo_p = subparsers.add_parser(
        "launch-order",
        help="Write (or idempotently rewrite) a launch order; deploy-layer only.",
    )
    lo_p.add_argument("--layer", required=True, choices=layer_choices)
    lo_p.add_argument("--file", required=True, dest="draft_file")

    approve_p = subparsers.add_parser(
        "approve-spec",
        help="Record a spec file's approval (direct user act -- no --layer).",
    )
    approve_p.add_argument("spec_file")
    approve_p.add_argument("--by", required=True)


def run(args) -> int:
    if args.command == "launch-order":
        return _run_launch_order(args)
    if args.command == "approve-spec":
        return _run_approve_spec(args)
    raise AssertionError(f"unreachable launchcmd command: {args.command!r}")


# ---------------------------------------------------------------------------
# approve-spec
# ---------------------------------------------------------------------------


def _run_approve_spec(args) -> int:
    path = Path(args.spec_file)
    text = path.read_text(encoding="utf-8")
    fields, body = _lib.parse_frontmatter(text)

    fields["approved_by"] = args.by
    fields["approved_date"] = _lib.today()
    if fields.get("spec_version") is None:
        fields["spec_version"] = 1
    # Digest is read off the file as it stands before this write -- approving
    # never touches the body, so the pre-write and post-write digest are the
    # same value either way (rows.json spec_header._digest_rule).
    fields["approved_digest"] = _lib.spec_digest(path)

    header_lines = ["---\n"]
    for key, value in fields.items():
        header_lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}\n")
    header_lines.append("---\n")
    new_text = "".join(header_lines) + body

    with _lib.locked(path):
        path.write_text(new_text, encoding="utf-8")

    print(json.dumps(fields, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------------------
# launch-order
# ---------------------------------------------------------------------------


def _check_spec_approval(cfg, item_id: str) -> None:
    """spec.md §5 pre-launch approval gate. Recursively searches the
    configured specs directory (default .scratch/) for a *.md file that both
    contains `item_id` and parses as frontmatter'd -- the first such match
    (sorted path order, for determinism) is the spec item's home file."""
    specs_root = cfg.ledger_path("specs")
    match = None
    if specs_root.exists():
        for md_path in sorted(specs_root.rglob("*.md")):
            text = md_path.read_text(encoding="utf-8")
            if item_id not in text:
                continue
            try:
                fields, _body = _lib.parse_frontmatter(text)
            except _lib.RLError:
                continue
            match = (md_path, fields)
            break

    if match is None:
        _lib.fail("launch_order", "spec_ref", "spec item not found", item_id)

    spec_path, fields = match
    if not fields.get("approved_by"):
        _lib.fail("launch_order", "spec_ref", "spec not approved", item_id)
    if _lib.spec_digest(spec_path) != fields.get("approved_digest"):
        _lib.fail("launch_order", "spec_ref", "approval_stale", item_id)


def _check_decision_refs(cfg, decision_refs: list) -> None:
    if not decision_refs:
        return
    decision_rows = _lib.jsonl_rows(cfg.ledger_path("decisions"))
    by_id = {row["decision_id"]: row for row in decision_rows}
    for ref in decision_refs:
        row = by_id.get(ref)
        if row is None:
            _lib.fail("launch_order", "decision_refs", "decision not found", ref)
        if row.get("status") != "decided":
            _lib.fail("launch_order", "decision_refs", "decision is not status=decided", ref)


def _check_promoted_from(cfg, promoted_from) -> None:
    if promoted_from is None:
        return
    launch_orders_dir = cfg.ledger_path("launch_orders")
    pf_path = launch_orders_dir / f"{promoted_from}.json"
    if not pf_path.exists():
        _lib.fail("launch_order", "promoted_from", "promoted launch order not found", promoted_from)
    pf_draft = json.loads(pf_path.read_text(encoding="utf-8"))
    if not pf_draft.get("quick"):
        _lib.fail("launch_order", "promoted_from", "promoted_from must point to a quick launch order")


def _backfill_affects(cfg, decisions_schema: dict, decision_refs: list, run_id: str) -> None:
    if not decision_refs:
        return
    decisions_path = cfg.ledger_path("decisions")
    whitelist = _decisions_whitelist()
    with _lib.locked(decisions_path):
        rows = _lib.jsonl_rows(decisions_path)
        by_id = {row["decision_id"]: row for row in rows}
        for ref in decision_refs:
            row = by_id.get(ref)
            if row is None:
                continue  # existence already enforced by _check_decision_refs above
            affects = row.get("affects") or []
            if run_id in affects:
                continue  # already backfilled -- rerun-safe (spec.md §5)
            new_affects = affects + [run_id]
            merged = {**row, "affects": new_affects}
            _lib.validate(merged, decisions_schema, "decisions")
            _lib.inplace_update(
                decisions_path, "decision_id", ref, {"affects": new_affects}, whitelist
            )


def _run_launch_order(args) -> int:
    if args.layer != "deploy":
        _lib.fail("launch_order", "layer", "launch-order is a deploy-layer action", args.layer)

    draft_path = Path(args.draft_file)
    draft = json.loads(draft_path.read_text(encoding="utf-8"))

    schema = _lib.load_schema("launch_order")
    _lib.validate(draft, schema, "launch_order")

    cfg = _context()

    # Registry three-check (tables/rows.json launch_order.registry_task):
    # registry_cmd is argv's prefix, the token right after it names a task
    # present in registry_query's listing (check_in_registry, shared with
    # principlescmd) -- and that token must equal the draft's own
    # registry_task claim (checked here, not inside check_in_registry, since
    # check_in_registry has no notion of a second name to compare against).
    task = _lib.check_in_registry(draft["argv"], cfg, ledger="launch_order", field="registry_task")
    if task != draft["registry_task"]:
        _lib.fail("launch_order", "registry_task", "token after registry prefix does not match")

    # Pre-launch approval gate -- waived whole-cloth for quick orders
    # (spec.md §2.6), not just when spec_ref happens to be null.
    if not draft.get("quick") and draft.get("spec_ref") is not None:
        _check_spec_approval(cfg, draft["spec_ref"])

    decision_refs = draft.get("decision_refs") or []
    _check_decision_refs(cfg, decision_refs)

    _check_promoted_from(cfg, draft.get("promoted_from"))

    # Every check passed -- write. Launch order first, affects backfill
    # second (spec.md §5's fixed write order); same-path rewrite is
    # idempotent (tables/rows.json launch_order._note).
    run_id = draft["run_id"]
    launch_orders_dir = cfg.ledger_path("launch_orders")
    launch_orders_dir.mkdir(parents=True, exist_ok=True)
    lo_path = launch_orders_dir / f"{run_id}.json"
    with _lib.locked(lo_path):
        lo_path.write_text(json.dumps(draft, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    decisions_schema = _lib.load_schema("decisions")
    _backfill_affects(cfg, decisions_schema, decision_refs, run_id)

    print(json.dumps(draft, ensure_ascii=False))
    return 0
