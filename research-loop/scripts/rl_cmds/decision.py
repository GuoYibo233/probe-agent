"""rl decision: the six decision books (02-decisions.md).

Sub-commands (02 L107-116; 05 L45-51): add, update, confirm, retire, merge (writes) and
show, list, stale (queries, open to everyone, 02 L118). Every rule below carries the part
and line it transcribes.
"""

from __future__ import annotations

import re

import rl_lib

# 02 L21: `dec-idea-0007`; the prefix says which book the row lands in, the sequence runs
# per prefix. Same pattern as schemas/decisions.schema.json.
_ID_RE = re.compile(r"^dec-(idea|deploy|run|analysis|reviewer|gyb)-[0-9]{4,}$")

# 04 L47 through tables/transitions.json: accepted and withdrawn are the terminal states,
# so an order in either of them is not one of the "没到终态的单子" of 02 L87.
_TERMINAL = tuple(rl_lib.TRANSITIONS["terminal_states"])


# ---------------------------------------------------------------- small shared pieces

def _out(ctx, payload, text):
    """--json returns the structure, a bare terminal reads the text form (05 L121-123)."""
    return payload if ctx["opts"]["json"] else text


def _book_of(decision_id: str) -> str:
    """02 L11, L13: the file a decision row lands in is read off the id prefix, never off
    the actor; every version of one decision stays in the same file."""
    m = _ID_RE.match(decision_id or "")
    if not m:
        raise rl_lib.RLError("usage", f"{decision_id!r} is not a decision id",
                             "ids look like dec-idea-0007 (02 L21)")
    return m.group(1)


def _write_row(repo, ledger, fields, actor, command, *, status, version, book=None, force=False, force_reason=None):
    """Thin wrapper over rl_lib.write_row; --force handling lives in rl_lib.validate_row
    (03 L27; 01 L90: required lists dropped, shape kept; reviewer fix on 529b8ef)."""
    return rl_lib.write_row(repo, ledger, fields, actor, command, status=status, version=version,
                            book=book, force=force, force_reason=force_reason)


def _parse_source(repo, spec: str, force: bool = False) -> dict:
    """One `--source K:V` argument into one sources item (02 L36-42).

    `file:PATH[#anchor]` - the path must exist under the repo, the anchor is deliberately
    not checked (02 L42); `run:RUN_ID` - the run_id must be in the runs ledger (02 L42);
    `decision:ID@V` - an older decision's id and version, which must exist (01 L88 lists
    reference existence among the integrity checks; 05 L196 doctor item 2 scans decisions'
    sources for dangling references). With force=True (gyb --force --reason, 03 L27;
    01 L90) the existence checks are skipped and only the K:V shape is checked.
    """
    kind, sep, rest = (spec or "").partition(":")
    if not sep or not rest:
        raise rl_lib.RLError("usage", f"--source {spec!r} is not K:V",
                             "write file:PATH[#anchor], run:RUN_ID or decision:ID@V (02 L36-40)")
    if kind == "file":
        path, _, anchor = rest.partition("#")
        if not path or (not force and not (repo / path).exists()):
            raise rl_lib.RLError("validation", f"source file {path!r} does not exist in the repo",
                                 "a file source is any path inside the repo and must exist (02 L42)")
        item = {"kind": "file", "path": path}
        if anchor:
            item["anchor"] = anchor  # 02 L42: the anchor is a hint, rl does not validate it
        return item
    if kind == "run":
        known = {r["run_id"] for r in rl_lib.read_rows(repo, "runs")}
        if not force and rest not in known:
            raise rl_lib.RLError("validation", f"run {rest} is not in the runs ledger",
                                 "a run source must point at a run_id that exists (02 L42)")
        return {"kind": "run", "run_id": rest}
    if kind == "decision":
        dec_id, at, raw = rest.rpartition("@")
        if not at or not raw.isdigit():
            raise rl_lib.RLError("usage", f"--source decision:{rest} needs a version",
                                 "write decision:dec-idea-0007@2 (02 L38)")
        version = int(raw)
        _book_of(dec_id)
        rows = rl_lib.read_rows(repo, "decisions", _book_of(dec_id))
        if not force and not any(r["id"] == dec_id and r["version"] == version for r in rows):
            raise rl_lib.RLError("validation", f"decision {dec_id} has no version {version}",
                                 "a decision source names an existing id and version (01 L88)")
        return {"kind": "decision", "id": dec_id, "version": version}
    raise rl_lib.RLError("usage", f"unknown source kind {kind!r}",
                         "the three kinds are decision, file and run (02 L36-40)")


def _parse_sources(repo, specs, force: bool = False) -> list:
    return [_parse_source(repo, s, force) for s in specs]


def _require_sources(sources, force):
    """02 L26, L42: every version carries at least one source; an empty list is refused.
    gyb writes past it with --force --reason (03 L27)."""
    if not sources and not force:
        raise rl_lib.RLError("validation", "a decision version needs at least one --source",
                             "add --source file:PATH[#anchor], --source run:RUN_ID or "
                             "--source decision:ID@V (02 L42)")


def _add_sources(previous: list, extra: list) -> list:
    """02 L75: confirm 「正文不变，只加来源」 - narrowest reading, the previous sources
    plus the new ones, each item kept once."""
    out = list(previous)
    for item in extra:
        if item not in out:
            out.append(item)
    return out


# ---------------------------------------------------------------- who may append a version

def _check_same_actor(actor, book: str, command: str) -> None:
    """02 L81: 「谁能调」 for update, confirm, retire and merge is the same actor; a
    cross-role change to somebody else's decision is a new decision in the caller's own
    book instead (02 L58). gyb is exempt from this class of check (02 L81; 01 L65)."""
    if actor.is_gyb or actor.role_session == book:
        return
    who = actor.role_session or "gyb"
    raise rl_lib.RLError(
        "forbidden", f"{who} may not append a version to a {book} decision (02 L81)",
        "open a new decision in your own book with --source decision:ID@V (02 L58), or ask gyb: "
        + rl_lib.issue_command_for_gyb(f"{who} needs to change a {book} decision"))


# ---------------------------------------------------------------- staleness (02 L85)

def _latest_revisions(repo) -> dict:
    """Per decision id, the highest version whose `op` is not confirm. 02 L85: a citation
    is stale when its version is lower than the latest non-confirm version, so a confirm
    version never makes anything stale."""
    out: dict = {}
    for row in rl_lib.read_decisions(repo):
        if row["op"] == "confirm":
            continue
        if row["version"] > out.get(row["id"], 0):
            out[row["id"]] = row["version"]
    return out


def _affected(repo, cited: dict) -> list:
    """02 L87: the moment update, retire or merge lands, rl lists the orders that cite an
    older version and have not reached a terminal status, together with their holder.
    `cited` maps a decision id to the version just written. The shape is the one
    tables/README.md fixes for this command: a list of {"id", "holder"}."""
    orders = rl_lib.latest(rl_lib.read_rows(repo, "handoffs"), "handoffs")
    out = []
    for ho_id in sorted(orders):
        row = orders[ho_id]
        if row["status"] in _TERMINAL:
            continue
        for ref in row.get("decision_refs") or []:
            if ref["id"] in cited and ref["version"] < cited[ref["id"]]:
                out.append({"id": ho_id, "holder": row.get("holder")})
                break
    return out


def _affected_text(affected: list) -> str:
    return "\n".join(f"{item['id']} holder {item['holder'] or '-'}" for item in affected)


# ---------------------------------------------------------------- write sub-commands

def cmd_add(args, ctx):
    """02 L109: a new decision; the prefix comes from the session (a role session uses the
    role's prefix, --as-gyb included; a bare terminal uses gyb), the sequence number is
    assigned inside that book, and the row lands in that book's file."""
    _pos, opts = rl_lib.parse_args(args, multi=("source",), allowed=rl_lib.allowed_options(ctx["command"]))
    repo, actor, force, reason = rl_lib.context(ctx)
    sources = _parse_sources(repo, opts.get("source") or [], force=bool(ctx["opts"].get("force")))
    _require_sources(sources, force)
    book = rl_lib.role_book(actor)  # 02 L11: the session decides the book, not the actor
    with rl_lib.Lock(repo):  # 03 L19: scan, assign and append under one lock
        ids = [r["id"] for r in rl_lib.read_rows(repo, "decisions", book)]
        new_id = rl_lib.next_number(ids, f"dec-{book}")  # 02 L52: numbering is per prefix
        fields = {"id": new_id, "op": "add", "root_id": new_id}  # 02 L23: root is itself on add
        if opts.get("text") is not None:
            fields["text"] = opts["text"]
        if sources:
            fields["sources"] = sources
        # 02 L11 and schemas/decisions.schema.json x-conditions (book gyb, op add): the gyb
        # book only holds decisions opened from a bare terminal, and a bare terminal is the
        # only session whose role_book is gyb, so session_id is cli here by construction.
        row = _write_row(repo, "decisions", fields, actor, "decision add", status="active",
                         version=1, book=book, force=force, force_reason=reason)
    return _out(ctx, rl_lib.result(row, "decisions"), f"{row['id']} v1 active")


def _revise(args, ctx, op: str, command: str):
    """The body shared by update, confirm and retire: one new version of one decision
    (02 L52: the id does not change, the version goes up by one)."""
    pos, opts = rl_lib.parse_args(args, multi=("source",), allowed=rl_lib.allowed_options(ctx["command"]))
    if not pos:
        raise rl_lib.RLError("usage", f"rl {command} needs a decision id")
    dec_id = pos[0]
    book = _book_of(dec_id)  # 02 L13: the book is the id's prefix, not the caller's role
    repo, actor, force, reason = rl_lib.context(ctx)
    _check_same_actor(actor, book, command)
    given = _parse_sources(repo, opts.get("source") or [], force=bool(ctx["opts"].get("force")))
    with rl_lib.Lock(repo):  # 03 L19
        prev, version = rl_lib.next_version_of(repo, "decisions", dec_id, book)
        if prev is None:
            raise rl_lib.RLError("usage", f"unknown decision {dec_id}")
        previous_sources = list(prev.get("sources") or [])
        if op == "confirm":
            sources = _add_sources(previous_sources, given)  # 02 L75: only adds sources
        else:
            # 02 L48: update, confirm, retire and merge inherit the previous version's
            # sources when no --source is given.
            sources = given or previous_sources
        _require_sources(sources, force)
        fields = {"id": dec_id, "op": op, "root_id": prev["root_id"]}  # 02 L23: root is inherited
        if sources:
            fields["sources"] = sources
        if op == "retire":
            status = "retired"  # 02 L76: retiring is one more version marked retired
            # proxy decision D-27 (02 L79 is more specific than 03 L27 and later): the
            # reason is owed by everyone, gyb too, and --force does not get past it;
            # a missing reason is a usage error (03 L224)
            if not opts.get("text"):
                raise rl_lib.RLError("usage", "decision retire needs --text <reason>",
                                     "the reason is the retire version's text (02 L79; D-27)")
            # 02 L79: the reason is the text of this version; a version without it is
            # refused by the schema's required `text` (same class as the empty-source
            # refusal). PENDING(issue 37a): the flag name --text is the one on record in
            # tables/commands.json and gyb reviews it at the final merge.
            if opts.get("text") is not None:
                fields["text"] = opts["text"]
        elif op == "confirm":
            status = prev["status"]
            fields["text"] = prev["text"]  # 02 L75: the text does not change
        else:
            status = prev["status"]
            if opts.get("text") is not None:
                fields["text"] = opts["text"]  # 02 L74: update swaps the text
        row = _write_row(repo, "decisions", fields, actor, command, status=status,
                         version=version, book=book, force=force, force_reason=reason)
        # 02 L87: update, retire and merge list the affected orders; confirm does not,
        # because confirming that nothing changed leaves nothing to re-check.
        affected = [] if op == "confirm" else _affected(repo, {dec_id: version})
    payload = rl_lib.result(row, "decisions")
    text = f"{dec_id} v{version} {status}"
    if op == "confirm":
        return _out(ctx, payload, text)
    payload["affected"] = affected
    return _out(ctx, payload, "\n".join([text, _affected_text(affected)]).rstrip())


def cmd_update(args, ctx):
    """02 L110: one more version with new text; sources inherit; the affected orders are
    listed the moment it lands."""
    return _revise(args, ctx, "update", "decision update")


def cmd_confirm(args, ctx):
    """02 L111: one more version, same text, sources only added, op confirm; it is not a
    revision, so it prints no affected orders and staleness skips it."""
    return _revise(args, ctx, "confirm", "decision confirm")


def cmd_retire(args, ctx):
    """02 L112: retire with a reason (everyone owes one, gyb too); the reason is this
    version's text; the affected orders are listed the same way update lists them."""
    return _revise(args, ctx, "retire", "decision retire")


def cmd_merge(args, ctx):
    """02 L113: a new decision with a new id; the merged ids go into sources and
    merged_from automatically; each merged decision gets one more version marked retired
    whose own root_id does not move (02 L23, L66, L77)."""
    pos, opts = rl_lib.parse_args(args, multi=("source",), allowed=rl_lib.allowed_options(ctx["command"]))
    if not pos:
        raise rl_lib.RLError("usage", "rl decision merge needs the decision ids to merge")
    merged = list(pos)
    repo, actor, force, reason = rl_lib.context(ctx)
    for mid in merged:
        _check_same_actor(actor, _book_of(mid), "decision merge")
    given = _parse_sources(repo, opts.get("source") or [], force=bool(ctx["opts"].get("force")))
    book = rl_lib.role_book(actor)  # 02 L11: the new decision opens in the caller's book
    with rl_lib.Lock(repo):  # 03 L19
        heads = {}
        for mid in merged:
            prev, next_version = rl_lib.next_version_of(repo, "decisions", mid, _book_of(mid))
            if prev is None:
                raise rl_lib.RLError("usage", f"unknown decision {mid}")
            heads[mid] = (prev, next_version)
        # 02 L77: sources automatically hold every merged decision, at its latest version.
        sources = _add_sources(given, [{"kind": "decision", "id": mid,
                                        "version": heads[mid][0]["version"]} for mid in merged])
        root_id = None
        root_flag = opts.get("root")
        if root_flag is not None:
            if root_flag in heads:
                root_id = heads[root_flag][0]["root_id"]
            else:
                root_row, _ = rl_lib.next_version_of(repo, "decisions", root_flag, _book_of(root_flag))
                if root_row is None:
                    raise rl_lib.RLError("usage", f"unknown decision {root_flag}")
                root_id = root_row["root_id"]
        ids = [r["id"] for r in rl_lib.read_rows(repo, "decisions", book)]
        new_id = rl_lib.next_number(ids, f"dec-{book}")
        fields = {"id": new_id, "op": "merge", "sources": sources, "merged_from": merged}
        if root_id is not None:
            fields["root_id"] = root_id  # 02 L23: the new decision inherits --root's root
        if opts.get("text") is not None:
            fields["text"] = opts["text"]
        row = _write_row(repo, "decisions", fields, actor, "decision merge", status="active",
                         version=1, book=book, force=force, force_reason=reason)
        cited = {}
        for mid in merged:
            prev, next_version = heads[mid]
            retired = {"id": mid, "op": "retire", "root_id": prev["root_id"]}
            if prev.get("sources"):
                retired["sources"] = list(prev["sources"])  # 02 L48: sources inherit
            # PENDING(part 02 L77): 02 L77 says only "旧的各追加一版标 retired、根不动"; it
            # rules neither the text nor the op of that version. Narrowest reading: the
            # reason for retiring is the merge, so the merge's own text is the reason
            # (02 L79: a retire version's text is its reason) and op is retire.
            if opts.get("text") is not None:
                retired["text"] = opts["text"]
            _write_row(repo, "decisions", retired, actor, "decision merge", status="retired",
                       version=next_version, book=_book_of(mid), force=force, force_reason=reason)
            cited[mid] = next_version
        affected = _affected(repo, cited)  # 02 L87: merge lists them too
    payload = rl_lib.result(row, "decisions", {"affected": affected})
    text = "\n".join([f"{new_id} v1 active merged_from {' '.join(merged)}",
                      _affected_text(affected)]).rstrip()
    return _out(ctx, payload, text)


# ---------------------------------------------------------------- query sub-commands

def _descendants(order_id: str, children: dict) -> list:
    """Every order below one order along parent_id, the order itself first (02 L114)."""
    out, stack = [], [order_id]
    while stack:
        cur = stack.pop(0)
        if cur in out:
            continue
        out.append(cur)
        stack.extend(sorted(children.get(cur, [])))
    return out


def _with_runs(repo, dec_id: str) -> list:
    """02 L114: `--with-runs` first finds the orders whose decision_refs cite this decision
    (any version) as starting points, then walks parent_id downwards collecting the
    descendant orders with their runs and metrics, one entry per order id, grouped by the
    version that was cited."""
    orders = rl_lib.latest(rl_lib.read_rows(repo, "handoffs"), "handoffs")
    children: dict = {}
    for oid, row in orders.items():
        parent = row.get("parent_id")
        if parent:
            children.setdefault(parent, []).append(oid)
    runs_by_order: dict = {}
    for run_id, row in rl_lib.latest(rl_lib.read_rows(repo, "runs"), "runs").items():
        runs_by_order.setdefault(row.get("handoff_id"), []).append(
            {"run_id": run_id, "status": row["status"], "metrics": row.get("metrics")})
    groups: dict = {}
    for oid in sorted(orders):
        for ref in orders[oid].get("decision_refs") or []:
            if ref["id"] != dec_id:
                continue
            bucket = groups.setdefault(ref["version"], {})
            for did in _descendants(oid, children):
                bucket[did] = {"id": did, "work_type": orders[did]["work_type"],
                               "status": orders[did]["status"],
                               "runs": runs_by_order.get(did, [])}
    return [{"version": v, "orders": list(groups[v].values())} for v in sorted(groups)]


def cmd_show(args, ctx):
    """02 L114: the latest version by default; --version picks one, --history gives them
    all, --with-runs adds the orders and runs hanging off this decision."""
    pos, opts = rl_lib.parse_args(args, flags=("history", "with-runs"), allowed=rl_lib.allowed_options(ctx["command"]))
    if not pos:
        raise rl_lib.RLError("usage", "rl decision show needs a decision id")
    dec_id = pos[0]
    book = _book_of(dec_id)
    repo, _actor, _force, _reason = rl_lib.context(ctx)
    versions = sorted([r for r in rl_lib.read_rows(repo, "decisions", book) if r["id"] == dec_id],
                      key=lambda r: r["version"])
    if not versions:
        raise rl_lib.RLError("usage", f"unknown decision {dec_id}")  # 05 L115: exit 5
    if opts.get("version") is not None:
        want = opts["version"]
        if not str(want).isdigit():
            raise rl_lib.RLError("usage", f"--version {want!r} is not a version number")
        chosen = [r for r in versions if r["version"] == int(want)]
        if not chosen:
            raise rl_lib.RLError("usage", f"decision {dec_id} has no version {want}")
    elif opts.get("history"):
        chosen = versions
    else:
        chosen = [versions[-1]]  # 02 L52: a read takes the latest version by default
    payload = {"id": dec_id, "book": book, "versions": chosen}
    lines = [f"v{r['version']} {r['op']} {r['status']} {r['actor']} {r.get('text', '')}" for r in chosen]
    if opts.get("with-runs"):
        payload["with_runs"] = _with_runs(repo, dec_id)
        for group in payload["with_runs"]:
            lines.append(f"cited at v{group['version']}:")
            for order in group["orders"]:
                runs = " ".join(run["run_id"] for run in order["runs"]) or "-"
                lines.append(f"  {order['id']} {order['work_type']} {order['status']} runs {runs}")
    return _out(ctx, payload, "\n".join(lines))


def cmd_list(args, ctx):
    """02 L115: list decisions; --actor filters by who wrote the latest version, --line by
    the research line, which is the root decision id (02 L66)."""
    _pos, opts = rl_lib.parse_args(args, allowed=rl_lib.allowed_options(ctx["command"]))
    repo, _actor, _force, _reason = rl_lib.context(ctx)
    rows = rl_lib.latest(rl_lib.read_decisions(repo), "decisions")
    out = []
    for dec_id in sorted(rows):
        row = rows[dec_id]
        if opts.get("actor") and row["actor"] != opts["actor"]:
            continue
        if opts.get("line") and row.get("root_id") != opts["line"]:
            continue
        out.append(row)
    text = "\n".join(f"{r['id']} v{r['version']} {r['status']} {r['actor']} {r.get('text', '')}"
                     for r in out)
    return _out(ctx, out, text)


def cmd_stale(args, ctx):
    """02 L89, L116: the staleness check. Default lists only what the current session's own
    orders cite, --handoff ID only that order's citations, --all the whole ledger. It is a
    query command, so anyone may call it (02 L118)."""
    _pos, opts = rl_lib.parse_args(args, flags=("all",), allowed=rl_lib.allowed_options(ctx["command"]))
    repo, actor, _force, _reason = rl_lib.context(ctx)
    latest_revision = _latest_revisions(repo)
    orders = rl_lib.latest(rl_lib.read_rows(repo, "handoffs"), "handoffs")
    if opts.get("handoff"):
        wanted = opts["handoff"]
        if wanted not in orders:
            raise rl_lib.RLError("usage", f"unknown handoff {wanted}")
        selected = [wanted]
    elif opts.get("all"):
        # PENDING(part 02 L89): "--all 全库" does not say whether finished orders count.
        # Narrowest reading: the same set 02 L87 prints, the orders that have not reached a
        # terminal status, which is also what rl status section 6 shows (05 L155, L160).
        selected = [o for o in sorted(orders) if orders[o]["status"] not in _TERMINAL]
    else:
        # 02 L89 with 05 L143: the default is the orders held by this session.
        selected = [o for o in sorted(orders) if orders[o].get("holder") == actor.session_id]
    out = []
    for ho_id in selected:
        row = orders[ho_id]
        for ref in row.get("decision_refs") or []:
            newest = latest_revision.get(ref["id"])
            if newest is not None and ref["version"] < newest:
                out.append({"handoff": ho_id, "holder": row.get("holder"), "decision": ref["id"],
                            "cited": ref["version"], "latest": newest})
    text = "\n".join(f"{item['handoff']} cites {item['decision']} v{item['cited']}, "
                     f"latest v{item['latest']}" for item in out)
    return _out(ctx, out, text)
