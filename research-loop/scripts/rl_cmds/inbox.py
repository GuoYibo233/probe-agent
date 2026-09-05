"""rl inbox: the role's inbox (05 L41, L131-143; 04 L200).

Five items, read-only, open to anyone (commands.json who: "anyone; roles call it when they
need it, not on start; run does not use it"). Reading the inbox never writes anything:
05 L138 leaves a notification issue open until its recipient calls `rl issue close`.

`--json` is an object with five keys, each an array (exit_codes.json json_shapes.inbox,
05 L123). The key names are a construction convention - PENDING(part 05 L123): the parts
fix the shape (five keys matching the five items, each a list) and never name the keys.
"""

from __future__ import annotations

from pathlib import Path

import rl_lib

# 05 L138: the three notification kinds item 4 lists (03 L92 names the same three).
NOTIFICATION_KINDS = ("withdrawn", "orphaned", "fyi")

# proxy decision D-33: item 2 lists the owner's orders in these four states (non-terminal,
# 04 L47) and with no holder (04 L51).
INBOX_ITEM2_STATES = ("todo", "stuck", "rejected", "done_pending_review")

# 03 L141: a verdict on feedback is the accepted or the rejected version.
VERDICT_STATUSES = ("accepted", "rejected")

# Construction convention (PENDING(part 05 L123)): the five key names.
KEYS = ("issues", "orders_without_holder", "stale_refs", "notifications", "feedback_verdicts")


def _latest_revisions(repo: Path) -> dict:
    """Per decision id, the highest version whose op is not confirm. 02 L85: a citation is
    stale when its version is lower than the latest non-confirm version, so a confirm
    version never makes anything stale. Same rule as `rl decision stale`."""
    out: dict = {}
    for row in rl_lib.read_decisions(repo):
        if row["op"] == "confirm":
            continue
        if row["version"] > out.get(row["id"], 0):
            out[row["id"]] = row["version"]
    return out


def collect(repo: Path, role: str | None, session_id: str) -> dict:
    """The five items of 05 L133-139 for one role session.

    A bare terminal has no role, so items 1, 2, 4 and 5 (all keyed on the role) are empty
    and item 3 is empty too, since a bare terminal holds no order (04 L21: holder is a
    session id and gyb's terminal never takes one). Narrowest reading of 05 L131 "the
    role's inbox"; PENDING(part 05 L131).
    """
    issues = rl_lib.latest(rl_lib.read_rows(repo, "issues"), "issues")
    orders = rl_lib.latest(rl_lib.read_rows(repo, "handoffs"), "handoffs")
    feedback_rows = rl_lib.read_rows(repo, "feedback")
    feedback = rl_lib.latest(feedback_rows, "feedback")

    # 1. open issues assigned to this role (05 L135).
    item1 = [issues[i] for i in sorted(issues)
             if issues[i]["status"] == "open" and issues[i].get("assignee") == role]

    # 2. orders owned by this role with an empty holder (05 L136; 04 L200). The holder
    #    invariant (04 L51) makes "holder empty" the same set as "not in_progress"; proxy
    #    decision D-33 narrows it to the non-terminal states: todo, stuck, rejected and
    #    done_pending_review (accepted and withdrawn are terminal, 04 L47).
    item2 = [orders[o] for o in sorted(orders)
             if rl_lib.owner_of(orders[o]) == role and orders[o]["status"] in INBOX_ITEM2_STATES
             and not orders[o].get("holder")]

    # 3. past-version decisions cited by the orders THIS SESSION holds (05 L137 with the
    #    2026-08-17 ruling at 05 L143: only the holder's own orders; an order the role owns
    #    but another session holds belongs to rl status section 6). The element shape is the
    #    one `rl decision stale` prints (02 L89); PENDING(part 05 L123): the parts say
    #    "raw ledger rows" and item 3 has no single row of its own.
    latest_revision = _latest_revisions(repo)
    item3 = []
    for ho_id in sorted(orders):
        row = orders[ho_id]
        if row.get("holder") != session_id:
            continue
        for ref in row.get("decision_refs") or []:
            newest = latest_revision.get(ref["id"])
            if newest is not None and ref["version"] < newest:
                item3.append({"handoff": ho_id, "holder": row.get("holder"),
                              "decision": ref["id"], "cited": ref["version"], "latest": newest})

    # 4. notifications addressed to this role and still open (05 L138).
    item4 = [issues[i] for i in sorted(issues)
             if issues[i]["status"] == "open" and issues[i].get("assignee") == role
             and issues[i].get("kind") in NOTIFICATION_KINDS]

    # 5. verdicts on feedback this role proposed (05 L139). "Proposed by" is the actor of
    #    the row's first version; the feedback ledger has no proposer field (03 L143-150).
    openers = {}
    for row in feedback_rows:
        if row["version"] == 1:
            openers[row["id"]] = row["actor"]
    item5 = [feedback[f] for f in sorted(feedback)
             if feedback[f]["status"] in VERDICT_STATUSES and openers.get(f) == role]

    return dict(zip(KEYS, (item1, item2, item3, item4, item5)))


def _text(payload: dict, role: str | None) -> str:
    titles = ("1. open issues assigned to this role",
              "2. orders owned by this role with no holder",
              "3. past-version decisions cited by the orders this session holds",
              "4. notifications addressed to this role",
              "5. verdicts on feedback this role proposed")
    lines = [f"inbox for {role or '(no role loaded)'}"]
    for key, title in zip(KEYS, titles):
        rows = payload[key]
        lines.append(f"{title} ({len(rows)})")
        for row in rows:
            if key == "stale_refs":
                lines.append(f"  {row['handoff']} cites {row['decision']} v{row['cited']}, "
                             f"latest v{row['latest']}")
            elif key == "orders_without_holder":
                lines.append(f"  {row['id']}  {row['work_type']}  {row['status']}  "
                             f"to {row.get('to_role')}")
            elif key == "feedback_verdicts":
                lines.append(f"  {row['id']}  {row['status']}  {row.get('target')}: "
                             f"{row.get('verdict_text', '')}")
            else:
                lines.append(f"  {row['id']}  {row.get('kind')}  {row['status']}: "
                             f"{row.get('text', '')}")
    return "\n".join(lines)


def cmd_main(args, ctx):
    """`rl inbox [--json]` (05 L41): a query command, open to everyone, and read-only
    (05 L138: reading never closes a notification)."""
    positional, opts = rl_lib.parse_args(args)
    if positional or opts:
        raise rl_lib.RLError("usage", "rl inbox takes no argument", "usage: rl inbox [--json]")
    repo, actor, _force, _reason = rl_lib.context(ctx)
    payload = collect(repo, actor.role_session, actor.session_id)
    if ctx["opts"]["json"]:
        return payload
    return _text(payload, actor.role_session)
