#!/usr/bin/env python3
"""`ledger.py blocked open|answer|close|withdraw` -- the blocked ledger's
four transitions (issues/05-blocked-decisions.md).

kind=r5-choice answers additionally machine-assemble a decisions.jsonl
"decision" row (spec.md §5 R5/R6, tables/writes.json r5_choice_assembly) --
that assembly lives in this module (not decisionscmd.py) because it only
ever fires from inside `blocked answer`, never as a standalone write path.
`withdraw` runs the three-step withdrawal-proxy write order (tables/
writes.json blocked_transitions.withdrawn._write_order): sync the answer's
decision to withdrawn first, then append the mechanically-reopened row,
and only last flip the old row -- a crash can only ever be caught holding
"old state" or "old state + one orphan decision row", never "new state
with a derived row missing" (spec.md §5 "复合动作的中断一致性").

Write rights, transitions and the r5-choice assembly rules are the ones in
tables/writes.json; row shape is tables/rows.json blocked_row/decisions_row.
Every write here goes through _lib.validate() (against the schemas T03
generated from those tables) and _lib.locked() (one flock per jsonl file
touched, held for the whole subcommand -- decisions.jsonl's lock, when
needed, nests inside blocked.jsonl's).
"""
from __future__ import annotations

import json

import _lib
from ledger_cmds import decisionscmd

_BLOCKED_ROW_DEFAULTS = {
    "answer": None,
    "answered_at": None,
    "answered_by": None,
    "grant_ref": None,
    "decision_ref": None,
    "schema_version": 1,
}


def _enum(name):
    return _lib.load_tables()["rows"]["enums"][name]


def _layer_values():
    return _lib.load_tables()["writes"]["layer_param"]["values"]


def _whitelist(ledger_name):
    return set(
        _lib.load_tables()["writes"]["write_forms"]["form2_inplace_whitelist"][ledger_name]
    )


def _find_row(rows, key_field, key_value):
    for row in rows:
        if row.get(key_field) == key_value:
            return row
    return None


def _context():
    root = _lib.find_project_root()
    return _lib.load_config(root)


def register(subparsers):
    parser = subparsers.add_parser(
        "blocked", help="Open, answer, close or withdraw a blocked-ledger row."
    )
    actions = parser.add_subparsers(dest="action", required=True)
    layer_choices = _layer_values()

    open_p = actions.add_parser("open", help="Open a new row (from_layer = --layer).")
    open_p.add_argument("--layer", required=True, choices=layer_choices)
    open_p.add_argument("--to-layer", required=True, choices=_enum("blocked.to_layer"))
    open_p.add_argument("--kind", required=True, choices=_enum("blocked.kind"))
    open_p.add_argument("--ref", required=True)
    open_p.add_argument("--question", required=True)
    open_p.add_argument("--evidence", required=True, nargs="+")
    open_p.add_argument("--where")
    open_p.add_argument("--options", nargs="+")

    answer_p = actions.add_parser(
        "answer",
        help="Answer an open row (writable by to_layer; any layer when to_layer=user).",
    )
    answer_p.add_argument("--layer", required=True, choices=layer_choices)
    answer_p.add_argument("blocked_id", metavar="BID")
    answer_p.add_argument("--answer", required=True, dest="answer_text")
    answer_p.add_argument("--answered-by", choices=["user"])
    answer_p.add_argument("--chosen")
    answer_p.add_argument("--grant", dest="grant_ref")
    answer_p.add_argument("--decision-ref", dest="decision_ref")

    close_p = actions.add_parser(
        "close", help="Close an open or answered row (writable by from_layer)."
    )
    close_p.add_argument("--layer", required=True, choices=layer_choices)
    close_p.add_argument("blocked_id", metavar="BID")

    withdraw_p = actions.add_parser(
        "withdraw",
        help="Withdraw an answered row (withdrawal-proxy special case -- no --layer).",
    )
    withdraw_p.add_argument("blocked_id", metavar="BID")
    withdraw_p.add_argument("--reason", required=True)


def run(args) -> int:
    if args.action == "open":
        return _run_open(args)
    if args.action == "answer":
        return _run_answer(args)
    if args.action == "close":
        return _run_close(args)
    if args.action == "withdraw":
        return _run_withdraw(args)
    raise AssertionError(f"unreachable blocked action: {args.action!r}")


def _run_open(args) -> int:
    if args.kind == "r5-choice" and (args.where is None or not args.options):
        _lib.fail("blocked", "where", "kind=r5-choice requires --where and --options")

    # #152: escalation must go one step, never skip a layer (failures.md
    # "升级走楼梯不跳层" / spec §2 通道表) -- writes.json blocked_transitions.
    # open.legal_to is the closed from_layer -> {legal to_layer} mapping this
    # checks against.
    legal_to = _lib.load_tables()["writes"]["blocked_transitions"]["open"]["legal_to"]
    allowed = legal_to.get(args.layer, [])
    if args.to_layer not in allowed:
        _lib.fail(
            "blocked", "to_layer",
            f"escalation must go one step (from_layer={args.layer!r}; "
            f"legal targets: {allowed})",
            args.to_layer,
        )

    cfg = _context()
    path = cfg.ledger_path("blocked")
    schema = _lib.load_schema("blocked")

    with _lib.locked(path):
        rows = _lib.jsonl_rows(path)
        row = {
            "blocked_id": _lib.alloc_id(rows, "blocked_id", "B"),
            "from_layer": args.layer,
            "to_layer": args.to_layer,
            "kind": args.kind,
            "ref": args.ref,
            "question": args.question,
            "where": args.where,
            "options": args.options,
            "evidence": args.evidence,
            "raised_at": _lib.now_iso(),
            "status": "open",
            **_BLOCKED_ROW_DEFAULTS,
        }
        _lib.validate(row, schema, "blocked")
        _lib.jsonl_append(path, row)

    print(json.dumps(row, ensure_ascii=False))
    return 0


def _run_answer(args) -> int:
    cfg = _context()
    blocked_path = cfg.ledger_path("blocked")
    decisions_path = cfg.ledger_path("decisions")
    blocked_schema = _lib.load_schema("blocked")
    decisions_schema = _lib.load_schema("decisions")
    now = _lib.now_iso()

    with _lib.locked(blocked_path):
        rows = _lib.jsonl_rows(blocked_path)
        row = _find_row(rows, "blocked_id", args.blocked_id)
        if row is None:
            _lib.fail("blocked", "blocked_id", "row not found", args.blocked_id)
        if row["status"] != "open":
            _lib.fail("blocked", "status", "illegal transition to answered", row["status"])

        if row["to_layer"] == "user":
            # Withdrawal-proxy-style special case: any layer's session may
            # answer on the user's behalf, but the field is force-set --
            # argparse's choices=["user"] already rejects any other
            # explicit --answered-by value before we get here.
            #
            # --grant is rejected outright here (F10, sdd/final-review.md):
            # a to_layer=user row is a transcript of the user's own ruling,
            # never a self-decision -- answered_by is about to be forced to
            # "user" two lines down regardless of who actually typed the
            # answer, so a --grant here would get recorded as if the user
            # ruled on it when an agent actually self-decided under a
            # grant. A real self-decision opens its row --to-layer idea or
            # --to-layer deploy instead (r5-choices.md "Which mode
            # applies").
            if args.grant_ref is not None:
                _lib.fail(
                    "blocked", "grant_ref",
                    "to_layer=user answers are a transcript of the user's own ruling and "
                    "may not carry --grant (a self-decision must open its row --to-layer "
                    "idea or --to-layer deploy, not --to-layer user)",
                    args.grant_ref,
                )
            # Same reasoning as --grant just above (F10, sdd/final-review.md)
            # extended to #151's --decision-ref: a to_layer=user row is a
            # transcript of the user's own ruling, never a self-decision, so
            # it must not carry a decisions-ledger citation either.
            if args.decision_ref is not None:
                _lib.fail(
                    "blocked", "decision_ref",
                    "to_layer=user answers are a transcript of the user's own ruling and "
                    "may not carry --decision-ref (a self-decision must open its row "
                    "--to-layer idea or --to-layer deploy, not --to-layer user)",
                    args.decision_ref,
                )
            answered_by = "user"
        else:
            if args.layer != row["to_layer"]:
                _lib.fail("blocked", "to_layer", "only to_layer may write answered", args.layer)
            answered_by = "user" if args.answered_by == "user" else args.layer

            if row["kind"] == "r5-choice":
                # A provided --grant must name an active grant row -- grant_ref
                # is an audit-chain pointer, so a literal like
                # "spec-standing-gpu-1h" (valid only for `decision
                # --authorized-by`) must not land in it. r5-choice 分支一字
                # 不动 (#151): this is the same early fail-fast pre-check as
                # before, unchanged; the assembly block below re-checks under
                # the decisions lock at assembly time.
                if args.grant_ref is not None:
                    if not any(
                        g["decision_id"] == args.grant_ref
                        for g in decisionscmd.active_grants(_lib.jsonl_rows(decisions_path), now)
                    ):
                        _lib.fail("blocked", "grant_ref", "grant is not active", args.grant_ref)
            else:
                # #151 R6 two-step path (tables/writes.json
                # blocked_transitions.answered._non_r5_self_decision): a
                # non-r5-choice self-decision is never recorded by citing
                # --grant directly on the answer -- that used to produce an
                # "authorized" answer with zero decisions-ledger trace (the
                # R6 hole, v1-deploy-2 / v2-hop3-1). The only route is: record
                # the decision first (`ledger.py decision --blocked-ref ...
                # --authorized-by grant:D0xx|spec-standing-gpu-1h`), then
                # answer citing that decision via --decision-ref. This
                # replaces the "validate --grant is active regardless of
                # kind" gate the previous round put here as a stopgap against
                # the literal spec-standing-gpu-1h landing in grant_ref.
                if args.grant_ref is not None:
                    _lib.fail(
                        "blocked", "grant_ref",
                        f"kind={row['kind']!r} answers do not take --grant directly -- "
                        "record the self-decision first (ledger.py decision --blocked-ref "
                        f"{args.blocked_id} --authorized-by grant:D0xx|spec-standing-gpu-1h), "
                        "then answer with --decision-ref D0xx",
                        args.grant_ref,
                    )
                # An optional --decision-ref cites an already-recorded
                # self-decision (step 1 above). Not given at all is still a
                # legal plain answer -- R6 only governs self-decisions that
                # cite authorization, not every answer.
                if args.decision_ref is not None:
                    decision_rows = _lib.jsonl_rows(decisions_path)
                    decision_row = _find_row(decision_rows, "decision_id", args.decision_ref)
                    if decision_row is None:
                        _lib.fail("blocked", "decision_ref", "row not found", args.decision_ref)
                    if decision_row.get("kind") != "decision":
                        _lib.fail(
                            "blocked", "decision_ref",
                            "decision_ref must point at a kind=decision row",
                            args.decision_ref,
                        )
                    if decision_row.get("blocked_ref") != args.blocked_id:
                        _lib.fail(
                            "blocked", "decision_ref",
                            "decision.blocked_ref does not point back at this blocked row",
                            args.decision_ref,
                        )
                    if decision_row.get("decided_by") != "agent":
                        _lib.fail(
                            "blocked", "decision_ref",
                            "decision.decided_by must be agent", args.decision_ref,
                        )
                    authorized_by = decision_row.get("authorized_by") or ""
                    if authorized_by.startswith("grant:"):
                        grant_id = authorized_by[len("grant:"):]
                        if not any(
                            g["decision_id"] == grant_id
                            for g in decisionscmd.active_grants(decision_rows, now)
                        ):
                            _lib.fail(
                                "blocked", "decision_ref",
                                "decision.authorized_by grant is not active",
                                args.decision_ref,
                            )
                    elif authorized_by != "spec-standing-gpu-1h":
                        _lib.fail(
                            "blocked", "decision_ref",
                            "decision.authorized_by must be grant:D0xx or spec-standing-gpu-1h",
                            args.decision_ref,
                        )

        updates = {
            "status": "answered",
            "answer": args.answer_text,
            "answered_at": now,
            "answered_by": answered_by,
        }
        if args.grant_ref is not None:
            updates["grant_ref"] = args.grant_ref
        if row["kind"] != "r5-choice" and args.decision_ref is not None:
            updates["decision_ref"] = args.decision_ref

        if row["kind"] == "r5-choice":
            if args.chosen is None:
                _lib.fail("blocked", "chosen", "r5-choice answer requires --chosen")
            if answered_by != "user" and args.grant_ref is None:
                _lib.fail("blocked", "grant_ref", "answered_by != user requires --grant")

            with _lib.locked(decisions_path):
                decision_rows = _lib.jsonl_rows(decisions_path)

                if answered_by != "user":
                    if not any(
                        g["decision_id"] == args.grant_ref
                        for g in decisionscmd.active_grants(decision_rows, now)
                    ):
                        _lib.fail("blocked", "grant_ref", "grant is not active", args.grant_ref)

                # Idempotency (writes.json r5_choice_assembly._idempotency):
                # reuse an existing synced decision instead of appending a
                # second one -- this is also the "crash recovery" path
                # (step 1 succeeded, step 2 didn't) rerun converges here.
                decided_matches = [
                    d
                    for d in decision_rows
                    if d.get("blocked_ref") == args.blocked_id and d.get("status") == "decided"
                ]
                if len(decided_matches) > 1:
                    _lib.fail(
                        "decisions",
                        "blocked_ref",
                        "more than one decided decision synced to the same blocked row",
                        args.blocked_id,
                    )
                if decided_matches:
                    decision_id = decided_matches[0]["decision_id"]
                else:
                    decided_by = "user" if answered_by == "user" else "agent"
                    authorized_by = (
                        args.answer_text if answered_by == "user" else f"grant:{args.grant_ref}"
                    )
                    # blocked.ref carrying a B-prefix means this row is
                    # itself a withdrawal reopen (ref points at the old
                    # blocked_id, not a spec/issue/run) -- nothing to
                    # affect (tables/rows.json decisions_row.affects).
                    affects = [] if row["ref"].startswith("B") else [row["ref"]]
                    decision_row = {
                        "decision_id": _lib.alloc_id(decision_rows, "decision_id", "D"),
                        "kind": "decision",
                        "where": row["where"],
                        "question": row["question"],
                        "options": row["options"],
                        "chosen": args.chosen,
                        "reason": args.answer_text,
                        "authorized_by": authorized_by,
                        "scope": None,
                        "principle_ref": None,
                        "affects": affects,
                        "blocked_ref": args.blocked_id,
                        "decided_by": decided_by,
                        "raised_at": row["raised_at"],
                        "decided_at": now,
                        "status": "decided",
                        "superseded_by": None,
                        "withdrawn_by": None,
                        "withdrawn_reason": None,
                        "schema_version": 1,
                    }
                    _lib.validate(decision_row, decisions_schema, "decisions")
                    _lib.jsonl_append(decisions_path, decision_row)
                    decision_id = decision_row["decision_id"]

            updates["decision_ref"] = decision_id

        merged = {**row, **updates}
        _lib.validate(merged, blocked_schema, "blocked")
        _lib.inplace_update(blocked_path, "blocked_id", args.blocked_id, updates, _whitelist("blocked"))

    print(json.dumps(merged, ensure_ascii=False))
    return 0


def _run_close(args) -> int:
    cfg = _context()
    path = cfg.ledger_path("blocked")
    schema = _lib.load_schema("blocked")

    with _lib.locked(path):
        rows = _lib.jsonl_rows(path)
        row = _find_row(rows, "blocked_id", args.blocked_id)
        if row is None:
            _lib.fail("blocked", "blocked_id", "row not found", args.blocked_id)
        if args.layer != row["from_layer"]:
            _lib.fail("blocked", "from_layer", "only from_layer may close", args.layer)
        if row["status"] not in ("open", "answered"):
            _lib.fail("blocked", "status", "illegal transition to closed", row["status"])

        updates = {"status": "closed"}
        merged = {**row, **updates}
        _lib.validate(merged, schema, "blocked")
        _lib.inplace_update(path, "blocked_id", args.blocked_id, updates, _whitelist("blocked"))

    print(json.dumps(merged, ensure_ascii=False))
    return 0


def _run_withdraw(args) -> int:
    # withdrawal_proxy: "无用户原话拒" -- same rule and phrasing storycmd's
    # own retire path enforces (F5, sdd/final-review.md: this was the one
    # of the three withdrawal-proxy write paths that didn't check it yet).
    if not args.reason or not args.reason.strip():
        _lib.fail(
            "blocked", "reason",
            "withdrawal requires the user's own words",
        )

    cfg = _context()
    blocked_path = cfg.ledger_path("blocked")
    decisions_path = cfg.ledger_path("decisions")
    blocked_schema = _lib.load_schema("blocked")
    decisions_schema = _lib.load_schema("decisions")

    with _lib.locked(blocked_path):
        rows = _lib.jsonl_rows(blocked_path)
        row = _find_row(rows, "blocked_id", args.blocked_id)
        if row is None:
            _lib.fail("blocked", "blocked_id", "row not found", args.blocked_id)

        status = row["status"]
        if status == "open":
            _lib.fail(
                "blocked",
                "status",
                "withdraw applies to answered rows; from_layer should close open rows",
            )
        if status not in ("answered", "withdrawn"):
            _lib.fail("blocked", "status", f"withdraw does not apply to status={status!r} rows")

        # Step 1 -- sync the answer's decision to withdrawn (writes.json
        # blocked_transitions.withdrawn._write_order): via decision_ref, or
        # (fixture-only orphan case / decision_ref cleared) a reverse
        # lookup on decisions.blocked_ref.
        with _lib.locked(decisions_path):
            decision_rows = _lib.jsonl_rows(decisions_path)
            target = None
            if row.get("decision_ref"):
                target = _find_row(decision_rows, "decision_id", row["decision_ref"])
            if target is None:
                for d in decision_rows:
                    if d.get("blocked_ref") == args.blocked_id and d.get("status") == "decided":
                        target = d
                        break
            if target is not None and target.get("status") != "withdrawn":
                d_updates = {
                    "status": "withdrawn",
                    "withdrawn_by": "user",
                    "withdrawn_reason": args.reason,
                }
                d_merged = {**target, **d_updates}
                _lib.validate(d_merged, decisions_schema, "decisions")
                _lib.inplace_update(
                    decisions_path, "decision_id", target["decision_id"], d_updates,
                    _whitelist("decisions"),
                )

        # Step 2 -- mechanical reopen, deduped on ref=BID alone (F3, sdd/
        # final-review.md) so a rerun (crash recovery, the idempotent-
        # withdrawn path below, or doctor's own "re-run the same withdraw"
        # fix suggestion) never opens a second one -- even after the
        # already-reopened row has itself moved past status=open (answered,
        # closed, ...), which is ordinary lifecycle, not a sign the reopen
        # needs doing again.
        already_reopened = any(r.get("ref") == args.blocked_id for r in rows)
        if not already_reopened:
            new_row = {
                "blocked_id": _lib.alloc_id(rows, "blocked_id", "B"),
                "from_layer": row["from_layer"],
                "to_layer": row["to_layer"],
                "kind": row["kind"],
                "ref": args.blocked_id,
                "question": row["question"],
                "where": row["where"],
                "options": row["options"],
                "evidence": row["evidence"],
                "raised_at": _lib.now_iso(),
                "status": "open",
                **_BLOCKED_ROW_DEFAULTS,
            }
            _lib.validate(new_row, blocked_schema, "blocked")
            _lib.jsonl_append(blocked_path, new_row)

        # Step 3 -- flip the old row last. Skipped when it's already
        # withdrawn (idempotent rerun: only steps 1/2's convergence applies).
        if status == "answered":
            old_answer = row.get("answer") or ""
            new_answer = f"{old_answer}\n[withdrawn by user: {args.reason}]"
            updates = {"status": "withdrawn", "answer": new_answer}
            merged = {**row, **updates}
            _lib.validate(merged, blocked_schema, "blocked")
            _lib.inplace_update(
                blocked_path, "blocked_id", args.blocked_id, updates, _whitelist("blocked")
            )

    print(json.dumps({
        "blocked_id": args.blocked_id,
        "status": "withdrawn",
        "reopened": not already_reopened,
    }, ensure_ascii=False))
    return 0
