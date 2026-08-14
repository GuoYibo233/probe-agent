#!/usr/bin/env python3
"""`ledger.py grant|decision|decision-withdraw` -- the decisions ledger's
directly-driven write paths (issues/05-blocked-decisions.md).

kind=r5-choice's machine-assembled `decision` rows are NOT written from
here -- that assembly only ever fires from inside `blocked answer`, so it
lives in ledger_cmds/blockedcmd.py (tables/writes.json r5_choice_assembly).
This module owns:

- `grant`: kind=grant, always decided_by=user, always at least one layer's
  own session recording it, never oversight (tables/writes.json
  owner_values.per-kind: "kind=grant 三层会话当场代笔（均不含 oversight）").
- `decision`: kind=decision written directly by a session. decided_by
  defaults to agent; an agent-authored decision must point authorized_by
  at either an active grant (`grant:D0xx`) or the literal standing
  authorization `spec-standing-gpu-1h` (spec.md R5/R6) -- decided_by=user
  is only accepted from --layer deploy (spec approval is a deploy-layer
  act, §2.5).
- `decision-withdraw`: withdrawal-proxy special case (no --layer) --
  writes.json withdrawal_proxy applies to decisions generically, not just
  to r5-choice-assembled rows.

active_grants() is this module's export, consumed both by blockedcmd's R6
grant-validity check and (T09) by status/query's active-grants view: the
`decisions_row._grant_view` definition (rows.json) -- kind=grant,
status=decided, not superseded, and not expired.
"""
from __future__ import annotations

import json

import _lib


def active_grants(rows: list, now: str) -> list:
    """kind=grant rows that are status=decided, carry no superseded_by, and
    whose scope.expires_at is null or still later than `now` (an ISO-8601
    timestamp string -- comparable lexically, same format as _lib.now_iso()).
    See tables/ledgers.json decisions.active / rows.json
    decisions_row._grant_view for the definition this mirrors."""
    out = []
    for row in rows:
        if row.get("kind") != "grant":
            continue
        if row.get("status") != "decided":
            continue
        if row.get("superseded_by") is not None:
            continue
        scope = row.get("scope") or {}
        expires_at = scope.get("expires_at")
        if expires_at is not None and expires_at <= now:
            continue
        out.append(row)
    return out


def _find_row(rows, key_field, key_value):
    for row in rows:
        if row.get(key_field) == key_value:
            return row
    return None


def _whitelist(ledger_name):
    return set(
        _lib.load_tables()["writes"]["write_forms"]["form2_inplace_whitelist"][ledger_name]
    )


def _context():
    root = _lib.find_project_root()
    return _lib.load_config(root)


def register(subparsers):
    # kind=grant/decision are owned by idea|deploy|run sessions only --
    # oversight has zero write rights into this ledger either way
    # (writes.json owner_values.per-kind).
    non_oversight_layers = [
        layer for layer in _lib.load_tables()["writes"]["layer_param"]["values"]
        if layer != "oversight"
    ]

    grant_p = subparsers.add_parser(
        "grant", help="Record a standing authorization (kind=grant); never oversight."
    )
    grant_p.add_argument("--layer", required=True, choices=non_oversight_layers)
    grant_p.add_argument("--question", required=True)
    grant_p.add_argument("--reason", required=True)
    grant_p.add_argument("--scope-desc")
    grant_p.add_argument("--scope-globs", nargs="+")
    grant_p.add_argument("--expires")

    decision_p = subparsers.add_parser(
        "decision", help="Write a decisions-ledger decision row directly."
    )
    decision_p.add_argument("--layer", required=True, choices=non_oversight_layers)
    decision_p.add_argument("--question", required=True)
    decision_p.add_argument("--options", required=True, nargs="+")
    decision_p.add_argument("--chosen", required=True)
    decision_p.add_argument("--reason", required=True)
    decision_p.add_argument("--where", required=True)
    decision_p.add_argument("--authorized-by", required=True)
    decision_p.add_argument("--decided-by", choices=["user", "agent"])
    decision_p.add_argument("--principle-ref")
    decision_p.add_argument("--affects", nargs="+")

    withdraw_p = subparsers.add_parser(
        "decision-withdraw",
        help="Withdraw a decisions-ledger row (no --layer -- withdrawal proxy).",
    )
    withdraw_p.add_argument("decision_id", metavar="DID")
    withdraw_p.add_argument("--reason", required=True)
    withdraw_p.add_argument("--superseded-by")


def run(args) -> int:
    if args.command == "grant":
        return _run_grant(args)
    if args.command == "decision":
        return _run_decision(args)
    if args.command == "decision-withdraw":
        return _run_decision_withdraw(args)
    raise AssertionError(f"unreachable decisions command: {args.command!r}")


def _run_grant(args) -> int:
    if not args.scope_desc or not args.scope_globs:
        _lib.fail("decisions", "scope", "grant requires structured scope")

    cfg = _context()
    path = cfg.ledger_path("decisions")
    schema = _lib.load_schema("decisions")
    now = _lib.now_iso()

    with _lib.locked(path):
        rows = _lib.jsonl_rows(path)
        row = {
            "decision_id": _lib.alloc_id(rows, "decision_id", "D"),
            "kind": "grant",
            "where": None,
            "question": args.question,
            "options": None,
            "chosen": None,
            "reason": args.reason,
            "authorized_by": args.reason,
            "scope": {
                "desc": args.scope_desc,
                "path_globs": args.scope_globs,
                "expires_at": args.expires,
            },
            "principle_ref": None,
            "affects": [],
            "blocked_ref": None,
            "decided_by": "user",
            "raised_at": now,
            "decided_at": now,
            "status": "decided",
            "superseded_by": None,
            "withdrawn_by": None,
            "withdrawn_reason": None,
            "schema_version": 1,
        }
        _lib.validate(row, schema, "decisions")
        _lib.jsonl_append(path, row)

    print(json.dumps(row, ensure_ascii=False))
    return 0


def _run_decision(args) -> int:
    decided_by = args.decided_by or "agent"

    if decided_by == "user":
        if args.layer != "deploy":
            _lib.fail(
                "decisions", "decided_by",
                "decided_by=user is only accepted from --layer deploy", args.layer,
            )
    else:
        if args.authorized_by != "spec-standing-gpu-1h" and not args.authorized_by.startswith("grant:"):
            _lib.fail(
                "decisions", "authorized_by",
                "decided_by=agent requires authorized_by=grant:D0xx or spec-standing-gpu-1h",
                args.authorized_by,
            )

    cfg = _context()
    path = cfg.ledger_path("decisions")
    schema = _lib.load_schema("decisions")
    now = _lib.now_iso()

    with _lib.locked(path):
        rows = _lib.jsonl_rows(path)

        if decided_by == "agent" and args.authorized_by.startswith("grant:"):
            grant_id = args.authorized_by[len("grant:"):]
            if not any(g["decision_id"] == grant_id for g in active_grants(rows, now)):
                _lib.fail(
                    "decisions", "authorized_by", "authorized_by grant is not active",
                    args.authorized_by,
                )

        row = {
            "decision_id": _lib.alloc_id(rows, "decision_id", "D"),
            "kind": "decision",
            "where": args.where,
            "question": args.question,
            "options": args.options,
            "chosen": args.chosen,
            "reason": args.reason,
            "authorized_by": args.authorized_by,
            "scope": None,
            "principle_ref": args.principle_ref,
            "affects": args.affects or [],
            "blocked_ref": None,
            "decided_by": decided_by,
            "raised_at": now,
            "decided_at": now,
            "status": "decided",
            "superseded_by": None,
            "withdrawn_by": None,
            "withdrawn_reason": None,
            "schema_version": 1,
        }
        _lib.validate(row, schema, "decisions")
        _lib.jsonl_append(path, row)

    print(json.dumps(row, ensure_ascii=False))
    return 0


def _run_decision_withdraw(args) -> int:
    # withdrawal_proxy: "无用户原话拒" -- same rule and phrasing storycmd's
    # own retire path enforces (F5, sdd/final-review.md).
    if not args.reason or not args.reason.strip():
        _lib.fail(
            "decisions", "withdrawn_reason",
            "withdrawal requires the user's own words",
        )

    cfg = _context()
    path = cfg.ledger_path("decisions")
    schema = _lib.load_schema("decisions")

    with _lib.locked(path):
        rows = _lib.jsonl_rows(path)
        row = _find_row(rows, "decision_id", args.decision_id)
        if row is None:
            _lib.fail("decisions", "decision_id", "row not found", args.decision_id)

        updates = {"status": "withdrawn", "withdrawn_by": "user", "withdrawn_reason": args.reason}
        if args.superseded_by is not None:
            if _find_row(rows, "decision_id", args.superseded_by) is None:
                _lib.fail("decisions", "superseded_by", "row not found", args.superseded_by)
            updates["superseded_by"] = args.superseded_by

        merged = {**row, **updates}
        _lib.validate(merged, schema, "decisions")
        _lib.inplace_update(path, "decision_id", args.decision_id, updates, _whitelist("decisions"))

    print(json.dumps(merged, ensure_ascii=False))
    return 0
