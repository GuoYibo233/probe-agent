"""`ledger.py query LEDGER [filters...]` and `ledger.py render blocked`
(issues/09-query-status.md).

query is the plugin's only sanctioned way for a session to read a jsonl
ledger (spec §2.1 "查询口（主）"): default view = active rows only (per-ledger
definition below, mirroring tables/ledgers.json's `active` column since that
column is prose, not code); `--all-rows` returns literally everything;
`--include-archive` transparently passes through to `_lib.jsonl_rows` for the
ledger being queried. Only jsonl ledgers (`tables/ledgers.json` read class
"query-only") are servable here -- md/json ledgers are rejected and pointed
at their own read class (spec: "读法豁免" is for oversight only; every other
account's read law is enforced right here).

`_iter_launch_orders()` is this module's export: a plain (path, parsed-dict)
listing of every `ops/launch_orders/*.json` file. It backs this module's own
decisions default view (launch_orders.decision_refs is one of the three
reference sources that keep an otherwise-expired grant/decision in view) and
is reused as-is by statuscmd.py for pending_launch_orders / launch-overdue
(same directory scan, no reason to write it twice).

`render blocked` is the one maintenance/render action this module owns
(ledger.py's own `_RENDER_TARGET_MODULES` maps target "blocked" here); its
argparse surface (just the `target` choice) is registered by ledger.py
itself, not here -- this module only branches on `args.command == "render"`
in `run()` (2026-08-14 dispatcher note in the ticket).
"""
from __future__ import annotations

import json
from pathlib import Path

import _lib
from ledger_cmds import decisionscmd

# tables/ledgers.json read classes that `query` refuses, each with the
# rejection detail this module reports (query.<ledger>: <detail>). Only
# "query-only" ledgers are servable by query -- this dict is deliberately
# missing that key.
_REJECT_DETAIL = {
    "md-full": "md ledger, read the file directly (md-full)",
    "direct": "json ledger, read the file directly (direct)",
    "sliced": "large ledger, use a reader subagent (sliced)",
}

# tables/rows.json runs_row_normal/_criterion: which column --since compares
# against, one per queryable jsonl ledger (rows.json field _note: "query
# --since 按它过滤"; blocked/story/feedback/decisions equivalents are the
# ticket's own "--since 按 recorded_at（runs）/raised_at（blocked）/date
# （story、feedback）/decided_at（decisions）").
_SINCE_FIELD = {
    "runs": "recorded_at",
    "blocked": "raised_at",
    "story": "date",
    "feedback": "date",
    "decisions": "decided_at",
}

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _context():
    root = _lib.find_project_root()
    return _lib.load_config(root)


def _ledger_entry(name):
    doc = _lib.load_tables()["ledgers"]
    entry = doc["ledgers"].get(name)
    if entry is None:
        entry = doc.get("optional_ledgers", {}).get(name)
    return entry


def _iter_launch_orders(cfg):
    """[(path, parsed_dict), ...] for every *.json file directly under the
    launch_orders ledger's directory, sorted by path for deterministic
    iteration. A file that doesn't parse as a JSON object is skipped, not
    raised on -- launch orders are deploy-owned and schema-checked at write
    time; a query-time read has no write right to reject on their behalf."""
    path = Path(cfg.ledger_path("launch_orders"))
    if not path.exists():
        return []
    out = []
    for f in sorted(path.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict):
            out.append((f, data))
    return out


# ---------------------------------------------------------------------------
# Default (active) views -- one function per queryable ledger. Each mirrors
# tables/ledgers.json's `active` column for that ledger; the column itself is
# prose (not machine-readable) so the definition has to live in code exactly
# once, here (spec §0.5 "封闭清单只成文一次" -- this is that one place for
# the *executable* form of the active-row predicate).
# ---------------------------------------------------------------------------


def _story_default_view(rows):
    return [r for r in rows if r.get("status") == "active"]


def _blocked_default_view(rows):
    return [r for r in rows if r.get("status") in ("open", "answered")]


def _decisions_referenced_ids(rows, cfg):
    """decision_id values kept in view regardless of grant expiry, per the
    ticket's three reference sources: blocked.grant_ref/decision_ref,
    decisions' own superseded_by (scanned over the same `rows` this call
    already loaded -- respects the caller's --include-archive), and every
    launch order's decision_refs (always read at the launch_orders ledger's
    own default -- --include-archive only ever applies to the ledger being
    queried, not to the ledgers this cross-reference scan reaches into)."""
    referenced = set()
    for row in rows:
        superseded = row.get("superseded_by")
        if superseded:
            referenced.add(superseded)
    for row in _lib.jsonl_rows(cfg.ledger_path("blocked")):
        for field in ("grant_ref", "decision_ref"):
            value = row.get(field)
            if value:
                referenced.add(value)
    for _path, order in _iter_launch_orders(cfg):
        for value in order.get("decision_refs") or []:
            if value:
                referenced.add(value)
    return referenced


def _decisions_default_view(rows, cfg, now):
    grant_ids = {g["decision_id"] for g in decisionscmd.active_grants(rows, now)}
    keep = grant_ids | _decisions_referenced_ids(rows, cfg)
    return [r for r in rows if r.get("decision_id") in keep]


def _feedback_default_view(rows):
    reviewed_refs = {r.get("ref") for r in rows if r.get("kind") == "review"}
    return [
        r for r in rows
        if r.get("kind") == "suggestion" and r.get("fb_id") not in reviewed_refs
    ]


def _default_view(ledger_name, rows, cfg, now):
    if ledger_name == "story":
        return _story_default_view(rows)
    if ledger_name == "blocked":
        return _blocked_default_view(rows)
    if ledger_name == "decisions":
        return _decisions_default_view(rows, cfg, now)
    if ledger_name == "feedback":
        return _feedback_default_view(rows)
    # runs: "无活跃行概念" -- identity. Any other query-only ledger reaching
    # here (e.g. the optional runs_legacy) has no active/inactive concept
    # defined either, so identity is the correct fallback, not a gap.
    return rows


# ---------------------------------------------------------------------------
# `query`
# ---------------------------------------------------------------------------


def _run_query(args) -> int:
    cfg = _context()
    ledger_name = args.ledger
    entry = _ledger_entry(ledger_name)
    if entry is None:
        _lib.fail("query", ledger_name, "unknown ledger")

    read_class = entry["read"]
    if read_class != "query-only":
        detail = _REJECT_DETAIL.get(read_class, f"not queryable ({read_class})")
        _lib.fail("query", ledger_name, detail)

    if ledger_name == "runs" and not (args.batch or args.run or args.metric or args.since):
        _lib.fail(
            "query", "runs",
            "refuse to return the full table; add a filter "
            "(--batch/--run/--since/--metric) or read the rendered product",
        )

    rows = _lib.jsonl_rows(cfg.ledger_path(ledger_name), include_archive=args.include_archive)

    if not args.all_rows:
        rows = _default_view(ledger_name, rows, cfg, _lib.now_iso())

    if args.status is not None:
        rows = [r for r in rows if r.get("status") == args.status]
    if args.to_layer is not None:
        rows = [r for r in rows if r.get("to_layer") == args.to_layer]
    if args.kind is not None:
        rows = [r for r in rows if r.get("kind") == args.kind]
    if args.batch is not None:
        rows = [r for r in rows if r.get("batch_id") == args.batch]
    if args.run is not None:
        rows = [r for r in rows if r.get("run_id") == args.run]
    if args.metric is not None:
        rows = [r for r in rows if r.get("metric_name") == args.metric]
    if args.since is not None:
        since_field = _SINCE_FIELD.get(ledger_name)
        if since_field is not None:
            rows = [r for r in rows if (r.get(since_field) or "") >= args.since]

    print(json.dumps(rows, indent=2, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------------------
# `render blocked`
# ---------------------------------------------------------------------------


def _run_render_blocked(args) -> int:
    cfg = _context()
    rows = _lib.jsonl_rows(cfg.ledger_path("blocked"))
    relevant = _blocked_default_view(rows)

    groups: dict = {}
    for row in relevant:
        groups.setdefault(row.get("to_layer"), []).append(row)

    to_layer_order = _lib.load_tables()["rows"]["enums"]["blocked.to_layer"]
    for layer in to_layer_order:
        layer_rows = groups.get(layer)
        if not layer_rows:
            continue
        print(f"## {layer}")
        print("| blocked_id | kind | question | from_layer | raised_at |")
        print("|---|---|---|---|---|")
        for row in sorted(layer_rows, key=lambda r: r.get("blocked_id") or ""):
            print(
                f"| {row.get('blocked_id')} | {row.get('kind')} | {row.get('question')} | "
                f"{row.get('from_layer')} | {row.get('raised_at')} |"
            )
        print()
    return 0


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


def register(subparsers) -> None:
    # `render`'s own parser (just the target choice) is owned by ledger.py
    # itself (_RENDER_TARGET_MODULES) -- this module registers "query" only.
    parser = subparsers.add_parser(
        "query", help="Query a jsonl ledger's default (active) or filtered view."
    )
    parser.add_argument("ledger", metavar="LEDGER")
    parser.add_argument("--all-rows", action="store_true")
    parser.add_argument("--include-archive", action="store_true")
    parser.add_argument("--status")
    parser.add_argument("--to-layer")
    parser.add_argument("--kind")
    parser.add_argument("--batch")
    parser.add_argument("--run")
    parser.add_argument("--metric")
    parser.add_argument("--since")


def run(args) -> int:
    if args.command == "render":
        return _run_render_blocked(args)
    if args.command == "query":
        return _run_query(args)
    raise AssertionError(f"unreachable query command: {args.command!r}")
