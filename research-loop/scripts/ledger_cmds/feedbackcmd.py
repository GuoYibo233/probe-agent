"""`ledger.py feedback add|review` -- the feedback ledger's two write entries
(issues/06-story-feedback.md).

The feedback ledger is shared-append (tables/writes.json owner_values.
shared-append): any of the four working layers can append a suggestion row,
and only a --layer user session can append a review row that judges one.
Neither subcommand ever calls `_lib.inplace_update` -- writes.json's form2
whitelist has no entry for the feedback ledger, so once a row lands it is
final (R9: rejected suggestions are recorded, not erased).
"""
from __future__ import annotations

import json

import _lib

_SUGGESTION_LAYERS = {"idea", "deploy", "run", "oversight"}


def _cmd_add(args, cfg) -> int:
    if args.layer not in _SUGGESTION_LAYERS:
        _lib.fail(
            "feedback", "layer",
            "add rows only accept layer values idea|deploy|run|oversight", args.layer,
        )

    feedback_path = cfg.ledger_path("feedback")
    schema = _lib.load_schema("feedback.suggestion")

    with _lib.locked(feedback_path):
        existing = _lib.jsonl_rows(feedback_path, include_archive=True)
        row = {
            "fb_id": _lib.alloc_id(existing, "fb_id", "F"),
            "kind": "suggestion",
            "date": _lib.today(),
            "layer": args.layer,
            "context": args.context,
            "problem": args.problem,
            "suggestion": args.suggestion,
            "schema_version": 1,
        }
        _lib.validate(row, schema, "feedback")
        _lib.jsonl_append(feedback_path, row)

    print(json.dumps(row, ensure_ascii=False))
    return 0


def _cmd_review(args, cfg) -> int:
    if args.layer != "user":
        _lib.fail("feedback", "layer", "review rows only accept --layer user")

    feedback_path = cfg.ledger_path("feedback")
    schema = _lib.load_schema("feedback.review")

    with _lib.locked(feedback_path):
        existing = _lib.jsonl_rows(feedback_path, include_archive=True)
        ref_row = next((row for row in existing if row.get("fb_id") == args.ref), None)
        if ref_row is None:
            _lib.fail("feedback", "ref", "row not found", args.ref)
        if ref_row.get("kind") != "suggestion":
            _lib.fail("feedback", "ref", "ref must point to a suggestion row", args.ref)

        row = {
            "fb_id": _lib.alloc_id(existing, "fb_id", "F"),
            "kind": "review",
            "ref": args.ref,
            "layer": "user",
            "verdict": args.verdict,
            "note": args.note,
            "date": _lib.today(),
            "schema_version": 1,
        }
        _lib.validate(row, schema, "feedback")
        _lib.jsonl_append(feedback_path, row)

    print(json.dumps(row, ensure_ascii=False))
    return 0


def register(subparsers) -> None:
    parser = subparsers.add_parser("feedback", help="Feedback ledger: feedback add / feedback review.")
    sub = parser.add_subparsers(dest="feedback_command", required=True)

    add_p = sub.add_parser("add", help="Append a suggestion row (idea|deploy|run|oversight).")
    add_p.add_argument("--layer", required=True)
    add_p.add_argument("--context", required=True)
    add_p.add_argument("--problem", required=True)
    add_p.add_argument("--suggestion", required=True)

    review_p = sub.add_parser("review", help="Append a review row for a suggestion (--layer user only).")
    review_p.add_argument("--layer", required=True)
    review_p.add_argument("--ref", required=True)
    review_p.add_argument("--verdict", required=True)
    review_p.add_argument("--note", default=None)


def run(args) -> int:
    root = _lib.find_project_root()
    cfg = _lib.load_config(root)
    if args.feedback_command == "add":
        return _cmd_add(args, cfg)
    if args.feedback_command == "review":
        return _cmd_review(args, cfg)
    raise AssertionError(f"unhandled feedback_command: {args.feedback_command}")
