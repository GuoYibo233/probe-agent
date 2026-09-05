"""rl_cmds/handoff.py: the `rl handoff` command group (04 L7-115; 05 L60-70).

Every rule below is transcribed from a design part or a proxy decision and carries the
citation next to it (`04 L63`, `proxy decision D-22`). Behaviour the parts have not ruled
is marked `PENDING(part NN LNN)` or `PENDING(issue NN)` and is written the narrowest way a
test needs.

Shape of every handler (03 L19 puts scan/assign/append in one lock):

    context()  ->  reject unknown options (exit 5)  ->  inside rl_lib.Lock:
        load the order (unknown id -> exit 5)
        rl_lib.check_who_can_call  (exit 3)
        rl_lib.find_transition     (a transition outside the table -> exit 2, gyb too, 04 L55)
        rl_lib.check_who_can_write (exit 3, gyb exempt, 04 L57)
        the row's preconditions by id (exit 2; gyb --force --reason skips the failed ones)
        the ledger writes

`start` is the one place where the role check runs before the transition lookup: 04 L63
states it in the *preconditions* column, and 30 L39 rules that a wrong role hitting the
preconditions column is exit 2 while a wrong role hitting the who_can_write column is
exit 3.
"""

from __future__ import annotations

import os

import rl_lib

LEDGER = "handoffs"

_WORK_TYPES = ("work_order", "analysis_order", "launch_order")
_CONFIG_KEYS = ("model", "params", "dataset", "split")  # 04 L43


# ---------------------------------------------------------------- small helpers

def _parse(args, command, multi=(), flags=()):
    """rl_lib.parse_args with the option names this sub-command takes, read off its
    signature in tables/commands.json (03 L224: an option the command does not have is a
    usage error). This is what refuses `rl handoff done --actual-seconds` (04 L43; 30 L62).
    The `handoff open` signature in commands.json carries --code-path because a quick-lane
    supplement must list its code paths (07 L101; sync-inbox Q41(b)).
    """
    allowed = rl_lib.allowed_options(command)
    return rl_lib.parse_args(args, multi=tuple(multi), flags=tuple(flags), allowed=allowed)


def _one_id(positional, what="ID"):
    if len(positional) != 1:
        raise rl_lib.RLError("usage", f"expected exactly one {what}, got {len(positional)}",
                             "usage: rl handoff <sub> ID [options]")
    return positional[0]


def _order(repo, ho_id):
    """The latest version of one order; an id nobody has is a usage error (03 L221)."""
    row = rl_lib.latest(rl_lib.read_rows(repo, LEDGER), LEDGER).get(ho_id)
    if row is None:
        raise rl_lib.RLError("usage", f"no such handoff: {ho_id}",
                             "run `rl handoff list` to see the open orders")
    return row


def _carry(order):
    """The content fields of the latest version, ready for the next one (03 L11).
    One copy rule for every module: rl_lib.copy_content drops the skeleton keys and the
    version-only keys (adopted, 04 L29; quote, 04 L40)."""
    return rl_lib.copy_content(order)


def _refs(values, kind):
    """`ID@V` on the command line becomes {"id": ID, "version": V} (04 L32-33)."""
    out = []
    for value in values or []:
        if "@" not in value:
            raise rl_lib.RLError("usage", f"--{kind} takes ID@V, got {value!r}",
                                 f"write it as --{kind} dec-idea-0007@2")
        ident, _, version = value.partition("@")
        if not version.isdigit():
            raise rl_lib.RLError("usage", f"--{kind} version must be a number, got {value!r}")
        out.append({"id": ident, "version": int(version)})
    return out


def _number(value, flag):
    try:
        return float(value)
    except (TypeError, ValueError):
        raise rl_lib.RLError("usage", f"{flag} takes a number, got {value!r}")


def _exists(repo, path):
    """Deliverable paths are repo-relative and must exist (04 L35, L37, L62; 07 L107:
    checked against the main tree)."""
    return bool(path) and (repo / path).exists()


def _append(repo, ledger, fields, actor, command, *, status, version, force=False,
            force_reason=None, via=None, skip_conditions=False, internal=False):
    """One ledger row.

    Without `skip_conditions` this is exactly rl_lib.write_row. With it the row is built the
    same way and put through the same three gates (03 L15, L27; 05 L21: writer alive, who
    can call, shape) but the required-by-status step is left out, which is what a quick-lane
    supplement needs: it is a `work_order` with no decision_refs (04 L62 and 07 L98-107 list
    its four requirements and decision_refs is not one of them), so the schema's
    `work_type == work_order -> decision_refs, explanation, track` x-condition would refuse
    it. The supplement's own precondition list is checked in cmd_open instead. This is not
    force: nothing is written to force_reason and gyb's --force stays a separate flag.

    `internal=True` marks a row rl writes on its own behalf (the notices of 04 L188-200, the
    adopted runs version of 03 L100, the release rows the session-end hook writes) and skips
    who-can-call, because the ledger_writes table describes what a role may type, not what rl
    does for it (05 L40; 06 L156).
    """
    if not skip_conditions:
        return rl_lib.write_row(repo, ledger, fields, actor, command, status=status,
                                version=version, force=force, force_reason=force_reason, via=via,
                                internal=internal)
    row = rl_lib.skeleton(actor, status, version, force_reason=force_reason, via=via)
    row.update(fields)
    if actor.quote and "quote" not in row and actor.is_gyb and not actor.bare_terminal:
        row["quote"] = actor.quote  # 01 L70: --as-gyb rows carry gyb's words
    rl_lib.check_writer_alive(repo, actor)                        # 03 L15
    if not internal:
        rl_lib.check_who_can_call(actor, command)                 # 06 L156
    rl_lib.validate_shape(ledger, row, skip_required=force)       # 03 L27: force skips required
    rl_lib.append_row(repo, ledger, row)
    return row


def _is_supplement(order):
    """A quick-lane supplement (04 L31: quick_lane plus ql_tag). An order transferred in by
    `ql open --from` is marked quick_lane but carries no ql_tag (schemas x-conditions,
    PENDING(issue 41f)), so it stays an ordinary work_order for validation."""
    return bool(order.get("quick_lane")) and bool(order.get("ql_tag"))


class _Preconditions:
    """The preconditions column of one transition row (04 L55, L57): every failure is exit 2
    unless the writer is gyb with --force --reason, who skips the failed ones and has the
    reason recorded as force_reason."""

    def __init__(self, trow, force):
        self.trow = trow
        self.force = force
        self.failed = []

    def check(self, ident, ok, message, next_step=""):
        if not ok:
            self.failed.append((ident, message, next_step))
        return ok

    def raise_if_failed(self):
        if self.failed and not self.force:
            ident, message, next_step = self.failed[0]
            raise rl_lib.RLError("validation", f"{message} (precondition {ident}, {self.trow['_source']})",
                                 next_step or "fix it and retry, or ask gyb to force-write "
                                              "(03 L27: gyb writes with --force --reason)")


# ---------------------------------------------------------------- ledger lookups

def _decision_index(repo):
    return rl_lib.latest(rl_lib.read_decisions(repo), "decisions")


def _line_of(repo, decision_refs):
    """04 L27 / 02 L66: rl computes `line` from the root_id of the first decision ref.
    PENDING(part 04 L27): whether line is one value or a list when the refs span several
    root decisions; one value is the narrowest reading and the one the schema takes."""
    if not decision_refs:
        return None
    first = _decision_index(repo).get(decision_refs[0]["id"])
    return first.get("root_id") if first else None


def _issue_rows(repo, ho_id=None):
    rows = rl_lib.latest(rl_lib.read_rows(repo, "issues"), "issues").values()
    if ho_id is None:
        return list(rows)
    return [r for r in rows if r.get("handoff_id") == ho_id]


def _run_versions(repo, run_id):
    return [r for r in rl_lib.read_rows(repo, "runs") if r.get("run_id") == run_id]


def _latest_attempt(order):
    attempts = order.get("attempts") or []
    return attempts[-1] if attempts else None


def _adoptable_run(repo, order):
    """04 L63 / 03 L100: a launch_order whose latest attempt has a launched run row with no
    finished version is adopted, not restarted."""
    if order.get("work_type") != "launch_order":
        return None
    attempt = _latest_attempt(order)
    if attempt is None:
        return None
    versions = _run_versions(repo, attempt.get("run_id"))
    if not versions:
        return None
    if any(v["status"] == "finished" for v in versions):
        return None
    if not any(v["status"] == "launched" for v in versions):
        return None
    return max(versions, key=lambda v: v["version"])


def _holder_key(order):
    """The holder of an order as the pair rl_lib.check_who_can_write compares (proxy
    decision D-15 addendum): a subagent shares its parent's session_id, so a session and its
    subagent are told apart by agent_id, never by session_id alone."""
    if not order.get("holder"):
        return None
    return rl_lib.session_key(order["holder"], order.get("agent_id") or None)


def _actor_key(actor):
    return rl_lib.session_key(actor.session_id, actor.agent_id or None)


def _role_of_session(repo, session_id, agent_id=None):
    """The role of the session that holds an order (04 L74: the withdrawn notice goes to the
    holder's role). The sessions ledger is chained on (session_id, agent_id or empty), so a
    subagent's own row is found only with its agent_id (proxy decision D-15 addendum)."""
    rows = rl_lib.latest(rl_lib.read_rows(repo, "sessions"), "sessions")
    row = rows.get(rl_lib.session_key(session_id, agent_id or None))
    return row.get("role") if row else None


def _notice(repo, actor, command, kind, assignee, text, ho_id):
    """rl's own notification issues: fyi, orphaned, withdrawn (04 L188-200; 03 L75 makes
    handoff_id required on withdrawn and orphaned). Numbering is next_number over the
    existing issue ids inside the caller's lock (03 L19, L21). These are rl's rows, not the
    writing role's, so they go in with internal=True (04 L190: rl opens them)."""
    iss_id = rl_lib.next_number([r["id"] for r in rl_lib.read_rows(repo, "issues")], "iss")
    fields = {"id": iss_id, "assignee": assignee, "kind": kind, "text": text, "handoff_id": ho_id}
    return rl_lib.write_row(repo, "issues", fields, actor, command, status="open", version=1,
                            internal=True)


def _close_answered_issues(repo, actor, command, ho_id):
    """04 L70 / 03 L92: accepting an order closes the answered issues linked to it."""
    closed = []
    for iss in _issue_rows(repo, ho_id):
        if iss.get("status") != "answered":
            continue
        fields = rl_lib.copy_content(iss)
        # 04 L70: rl closes them as a side effect of accept, so the row is rl's own.
        rl_lib.write_row(repo, "issues", fields, actor, command, status="closed",
                         version=iss["version"] + 1, internal=True)
        closed.append(iss["id"])
    return closed


def _fyi_when_gyb_overrides(repo, actor, command, order, what):
    """04 L70, L71, L114: when gyb accepts or rejects over the owner, rl opens an fyi to the
    owner. An order whose owner is gyb has nobody to tell."""
    owner = rl_lib.owner_of(order)
    if not actor.is_gyb or owner not in rl_lib.ROLES:
        return None
    return _notice(repo, actor, command, "fyi", owner,
                   f"gyb {what} {order['id']} over the owner ({owner})", order["id"])


# ---------------------------------------------------------------- open

def cmd_open(args, ctx):
    """(new) -> todo, or (new) -> done_pending_review for the quick-lane supplement
    (04 L61, L62; 05 L64; 07 L109)."""
    repo, actor, force, force_reason = rl_lib.context(ctx)
    positional, opts = _parse(
        args, ctx["command"],
        multi=("decision", "eval", "config", "code-path"),
        flags=("manual", "no-dispatch", "quick-lane"))
    if positional:
        raise rl_lib.RLError("usage", f"rl handoff open takes no positional argument, got {positional[0]!r}")

    work_type = opts.get("type")
    if work_type not in _WORK_TYPES:
        raise rl_lib.RLError("usage", f"--type takes one of {', '.join(_WORK_TYPES)}, got {work_type!r}")
    # 04 L84-88: auto is the default, --manual writes manual, --no-dispatch writes none.
    if opts.get("manual") and opts.get("no-dispatch"):
        raise rl_lib.RLError("usage", "--manual and --no-dispatch are exclusive (04 L84-88)")
    dispatch = "manual" if opts.get("manual") else ("none" if opts.get("no-dispatch") else "auto")

    decision_refs = _refs(opts.get("decision"), "decision")
    evaluation_refs = _refs(opts.get("eval"), "eval")
    code_paths = list(opts.get("code-path") or [])

    with rl_lib.Lock(repo):
        rl_lib.check_who_can_call(actor, ctx["command"])
        ho_id = rl_lib.next_number([r["id"] for r in rl_lib.read_rows(repo, LEDGER)], "ho")

        if opts.get("quick-lane"):
            return _open_quick_lane(repo, actor, ctx, ho_id, opts, code_paths, decision_refs,
                                    force, force_reason)

        to_role = opts.get("to")
        if to_role not in rl_lib.ROLES:
            raise rl_lib.RLError("usage", f"--to takes one of {', '.join(rl_lib.ROLES)}, got {to_role!r}")
        trow = rl_lib.find_transition("handoff open", None)
        rl_lib.check_who_can_write(trow, actor, None)

        # 04 L19: from_role is the owner; a role session opens as its role, everyone else as
        # gyb. PENDING(part 04 L49): a role session writing --as-gyb records from_role = the
        # role and actor = gyb, so the owner stays the role that typed it; 04 L49 names gyb
        # as the owner of "orders gyb opened" without saying which of the two decides.
        fields = {
            "id": ho_id,
            "work_type": work_type,
            "from_role": actor.role_session if actor.role_session else "gyb",
            "to_role": to_role,
            "holder": None,      # 04 L51: holder is empty outside in_progress
            "last_holder": None,
            "dispatch": dispatch,
            # 04 L24, L26: parent_id and batch are on every order's field table and are
            # empty rather than absent when nothing fills them (both are nullable in the
            # schema), so a reader never has to ask whether the key exists.
            "parent_id": opts.get("parent"),
            "batch": opts.get("batch"),
        }
        if code_paths:
            fields["code_paths"] = code_paths

        pre = _Preconditions(trow, force)
        index = _decision_index(repo)
        for ref in decision_refs:
            pre.check("open.work_order_has_refs_and_explanation", ref["id"] in index,
                      f"decision {ref['id']} does not exist")

        if work_type == "work_order":
            # 04 L61 with 04 L32, L34; track is proxy decision D-10 (sync-inbox Q45(a)(f)).
            fields["decision_refs"] = decision_refs
            # 04 L32: a work_order carries at least one decision reference. An empty list is
            # a present value for check_conditions, so the count is checked here.
            pre.check("open.work_order_has_refs_and_explanation", len(decision_refs) >= 1,
                      "a work_order needs at least one --decision ID@V")
            if opts.get("explain"):
                fields["explanation"] = opts["explain"]
            if opts.get("track"):
                fields["track"] = opts["track"]
            # PENDING(part 20 L128): whether a plain work_order fills parent_id; --parent is
            # accepted and stored, nothing requires it.
        elif work_type == "analysis_order":
            # 04 L61 / 04 L33: evaluation_refs, each item may still be proposed.
            fields["evaluation_refs"] = evaluation_refs
            pre.check("open.analysis_order_has_eval_refs", bool(evaluation_refs),
                      "an analysis_order needs at least one --eval ID@V")
            # PENDING(part 22 L113) decision_refs and PENDING(part 22 L114) explanation are
            # not ruled for an analysis_order: both are stored when given, neither is required.
            if decision_refs:
                fields["decision_refs"] = decision_refs
            if opts.get("explain"):
                fields["explanation"] = opts["explain"]
            if opts.get("track"):
                fields["track"] = opts["track"]
        else:
            _launch_order_fields(repo, ho_id, opts, fields, pre, decision_refs)

        pre.raise_if_failed()
        refs_for_line = fields.get("decision_refs") or []
        fields["line"] = _line_of(repo, refs_for_line)  # 04 L27
        row = _append(repo, LEDGER, fields, actor, ctx["command"], status="todo", version=1,
                      force=force, force_reason=force_reason)
    return rl_lib.result(row, LEDGER)


def _launch_order_fields(repo, ho_id, opts, fields, pre, decision_refs):
    """04 L61 / 04 L43: a launch_order needs --parent and a first attempt with command,
    workdir, track and config; run_id is `<ho-id>-a<attempt>`; decision_refs, batch and
    track come from the parent (04 L26, L32; sync-inbox Q45(f))."""
    parent_id = opts.get("parent")
    pre.check("open.launch_order_first_attempt", bool(parent_id),
              "a launch_order needs --parent ID pointing at its work order")
    parent = None
    if parent_id:
        parent = rl_lib.latest(rl_lib.read_rows(repo, LEDGER), LEDGER).get(parent_id)
        pre.check("open.launch_order_first_attempt", parent is not None,
                  f"parent {parent_id} does not exist")
        if parent is not None:
            pre.check("open.launch_order_first_attempt", parent.get("work_type") == "work_order",
                      f"parent {parent_id} is a {parent.get('work_type')}, not a work_order")
    command = opts.get("command")
    workdir = opts.get("workdir")
    pre.check("open.launch_order_first_attempt", bool(command), "a launch_order needs --command")
    pre.check("open.launch_order_first_attempt", bool(workdir), "a launch_order needs --workdir")

    config = {}
    for item in opts.get("config") or []:
        key, sep, value = item.partition("=")
        if not sep:
            raise rl_lib.RLError("usage", f"--config takes k=v, got {item!r}")
        config[key] = value
    missing = [k for k in _CONFIG_KEYS if k not in config]
    pre.check("open.launch_order_first_attempt", not missing,
              "a launch_order's config needs " + ", ".join(_CONFIG_KEYS) +
              (f" (missing {', '.join(missing)})" if missing else ""))

    # sync-inbox Q45(c)(f): --track may be omitted on a launch_order and is then copied from
    # the parent's top-level track; a launch_order carries no top-level track of its own.
    track = opts.get("track") or (parent.get("track") if parent else None)
    pre.check("open.launch_order_first_attempt", bool(track),
              "a launch_order needs --track or a parent work_order that carries one")

    if parent is not None:
        fields["decision_refs"] = list(parent.get("decision_refs") or [])  # 04 L32
        fields["batch"] = opts.get("batch") or parent.get("batch")         # 04 L26
    elif decision_refs:
        fields["decision_refs"] = decision_refs
    fields["parent_id"] = parent_id
    fields["attempts"] = [{
        "attempt": 1,
        "command": command,
        "args": None,  # PENDING(part 21 L180): splitting args out of command is not ruled
        "workdir": workdir,
        "track": track,
        "config": config,
        "run_id": f"{ho_id}-a1",  # 04 L43
    }]


def _open_quick_lane(repo, actor, ctx, ho_id, opts, code_paths, decision_refs, force, force_reason):
    """(new) -> done_pending_review, written by deploy (04 L62; 07 L94-116).

    proxy decision D-24: the row records actor = the writer (deploy), from_role = gyb (the
    owner, so only gyb can accept it, 04 L70) and to_role = deploy (who did the work,
    07 L94 rule 1)."""
    trow = rl_lib.find_transition("handoff open --quick-lane", None)
    rl_lib.check_who_can_write(trow, actor, None)
    ql_tag = opts.get("ql")
    method = opts.get("report-method")
    explanation = opts.get("explain")

    scratch = rl_lib.latest(rl_lib.read_rows(repo, "scratch"), "scratch").get(ql_tag) if ql_tag else None
    pre = _Preconditions(trow, force)
    pre.check("ql.report_method_exists", _exists(repo, method),
              f"report_paths.method {method!r} does not exist under the repo root")
    pre.check("ql.explanation_nonempty", bool(explanation),
              "a quick-lane supplement needs --explain quoting gyb's words (04 L34)")
    pre.check("ql.code_paths_nonempty", bool(code_paths),
              "a quick-lane supplement needs at least one --code-path (sync-inbox Q41(b); 07 L101)")
    # proxy decision D-10 addendum: a supplement is a work order and needs --track like any
    # other; the value is the direction of the experiment being tuned (11 L122). Only
    # decision_refs is exempt for a supplement (04 L62 and 07 L98-107 list four requirements).
    pre.check("open.work_order_has_track", bool(opts.get("track")),
              "a quick-lane supplement needs --track T, the direction it belongs to")
    pre.check("ql.scratch_row_open", scratch is not None and scratch.get("status") == "open",
              f"the scratch row {ql_tag!r} is not open "
              "(open the supplement first, then `rl ql close --merged --handoff ID`, 07 L88)")
    pre.raise_if_failed()

    fields = {
        "id": ho_id,
        "work_type": "work_order",
        "from_role": "gyb",    # proxy decision D-24: the owner
        "to_role": "deploy",   # proxy decision D-24; 07 L94 rule 1
        "holder": None,        # 04 L51
        "last_holder": None,
        "parent_id": None,     # 07 L122: a quick-lane supplement's parent_id is empty
        "batch": None,
        # PENDING(part 04 L62): the supplement's dispatch value is not ruled. That row's
        # "who pulls next" column is empty (nobody is dispatched, it waits for gyb), so
        # dispatch is written as none; the schema requires the field to be there.
        "dispatch": "none",
        "quick_lane": True,    # 04 L30, L62
        "ql_tag": ql_tag,      # 04 L31
        "report_paths": {"method": method},  # 07 L98: only the method report, no detail
        "code_paths": code_paths,
        "explanation": explanation,
        "line": _line_of(repo, decision_refs),
    }
    if opts.get("track"):
        fields["track"] = opts["track"]
    if decision_refs:
        fields["decision_refs"] = decision_refs
    row = _append(repo, LEDGER, fields, actor, ctx["command"], status="done_pending_review",
                  version=1, force=force, force_reason=force_reason, skip_conditions=True)
    return rl_lib.result(row, LEDGER)


# ---------------------------------------------------------------- start

def cmd_start(args, ctx):
    """todo -> in_progress (04 L63) and rejected -> in_progress (04 L73); with --batch, every
    todo launch_order of that batch at once (proxy decision D-22)."""
    repo, actor, force, force_reason = rl_lib.context(ctx)
    positional, opts = _parse(args, ctx["command"])
    ho_id = _one_id(positional)
    batch = opts.get("batch")

    with rl_lib.Lock(repo):
        rl_lib.check_who_can_call(actor, ctx["command"])
        order = _order(repo, ho_id)
        targets = [order]
        if batch is not None:
            # proxy decision D-22 (commands.json handoff start): the ID only locates the
            # batch and must belong to it, otherwise exit 5.
            if order.get("batch") != batch:
                raise rl_lib.RLError("usage", f"{ho_id} is not in batch {batch!r} (its batch is "
                                              f"{order.get('batch')!r})",
                                     "name an order of that batch, or drop --batch")
            rows = rl_lib.latest(rl_lib.read_rows(repo, LEDGER), LEDGER)
            targets = [r for r in rows.values()
                       if r.get("work_type") == "launch_order" and r.get("batch") == batch
                       and r["status"] == "todo"]
            targets.sort(key=lambda r: r["id"])
        # proxy decision D-22 (addendum of 2026-09-05): a batch start is all-or-nothing;
        # every target is checked before any row is written, so one refused order leaves
        # the whole batch untouched (03 L19 puts the whole command in one lock, and a
        # refused write leaves no row, 30 L39-41).
        plans = [_start_checks(repo, actor, order) for order in targets]
        started = [_start_write(repo, actor, ctx, plan, force, force_reason) for plan in plans]
        named = _order(repo, ho_id)  # the named order's own latest version, batch form included
    return rl_lib.result(named, LEDGER, {"started": [r["id"] for r in started]})


def _start_checks(repo, actor, order):
    """Everything `start` refuses on, with nothing written yet. Returns the plan
    (order, transition row, run row to adopt or None)."""
    # 04 L63 preconditions column, read with 30 L39: a wrong role hits the preconditions
    # column here, so it is exit 2, not exit 3. gyb is exempt from the who column (04 L57)
    # and this precondition is that column written twice.
    if not actor.is_gyb and actor.role_session != order.get("to_role"):
        raise rl_lib.RLError("validation",
                             f"{order['id']} is addressed to {order.get('to_role')}, not to "
                             f"{actor.role_session} (precondition start.session_role_is_to_role, 04 L63)",
                             "let the addressed role start it, or ask gyb")
    # 04 L51 and 04 L57 rule 3 (proxy decision D-29): a non-empty holder is the header
    # invariant, not a precondition, so this refusal binds everyone and --force cannot pass
    # it; exit 2, listing the current holder (05 L119).
    if order.get("holder"):
        raise rl_lib.RLError("validation",
                             f"{order['id']} is already held by session {order['holder']} "
                             "(holder invariant, 04 L51; proxy decision D-29)",
                             f"ask that session to finish or release it: rl handoff release {order['id']} --note \"...\"")
    trow = rl_lib.find_transition("handoff start", order["status"])
    rl_lib.check_who_can_write(trow, actor, order)
    # Adoption belongs to the todo -> in_progress row alone (04 L63). The rejected ->
    # in_progress row (04 L73) is the original session carrying on, so it never adopts.
    adopt_run = _adoptable_run(repo, order) if trow["id"] == "start" else None
    return order, trow, adopt_run


def _start_write(repo, actor, ctx, plan, force, force_reason):
    order, _trow, adopt_run = plan
    fields = _carry(order)
    fields["holder"] = actor.session_id      # 04 L51: entering in_progress writes holder
    if adopt_run is not None:
        fields["adopted"] = True             # 04 L63
    row = _append(repo, LEDGER, fields, actor, ctx["command"], status="in_progress",
                  version=order["version"] + 1, force=force, force_reason=force_reason)
    if adopt_run is not None:
        # 03 L100: rl appends an adopted version to that runs row, recording the new
        # holder's session_id and ts in the skeleton fields, no extra field. rl writes it,
        # not the role, so it goes in with internal=True.
        rl_lib.write_row(repo, "runs", rl_lib.copy_content(adopt_run), actor, ctx["command"],
                         status="adopted", version=adopt_run["version"] + 1, internal=True)
    return row


# ---------------------------------------------------------------- amend

def cmd_amend(args, ctx):
    """todo/stuck -> same (04 L64) and done_pending_review -> same (04 L69): content only,
    status unchanged, holder unchanged."""
    repo, actor, force, force_reason = rl_lib.context(ctx)
    positional, opts = _parse(
        args, ctx["command"],
        multi=("config", "code-path", "figure", "decision", "eval"))
    ho_id = _one_id(positional)

    with rl_lib.Lock(repo):
        rl_lib.check_who_can_call(actor, ctx["command"])
        order = _order(repo, ho_id)
        trow = rl_lib.find_transition("handoff amend", order["status"])
        rl_lib.check_who_can_write(trow, actor, order)
        fields = _carry(order)

        if opts.get("report-method") or opts.get("report-detail"):
            report = dict(fields.get("report_paths") or {})
            if opts.get("report-method"):
                report["method"] = opts["report-method"]
            if opts.get("report-detail"):
                report["detail"] = opts["report-detail"]
            fields["report_paths"] = report
        if opts.get("code-path"):
            paths = list(fields.get("code_paths") or [])
            for p in opts["code-path"]:
                if p not in paths:
                    paths.append(p)
            fields["code_paths"] = paths
        if opts.get("notebook") or opts.get("figure"):
            outputs = dict(fields.get("output_paths") or {})
            if opts.get("notebook"):
                outputs["notebook"] = opts["notebook"]
            if opts.get("figure"):
                outputs["figures"] = list(opts["figure"])
            fields["output_paths"] = outputs
        if opts.get("decision"):
            # 05 L65: --decision swaps the decision_refs (the doctor fix for a dangling ref).
            refs = _refs(opts["decision"], "decision")
            index = _decision_index(repo)
            missing = [r["id"] for r in refs if r["id"] not in index]
            if missing:
                raise rl_lib.RLError("validation", f"decision {', '.join(missing)} does not exist")
            fields["decision_refs"] = refs
            fields["line"] = _line_of(repo, refs)  # 04 L27
        if opts.get("eval"):
            # 04 L64 swaps evaluation_refs the same way --decision swaps decision_refs, and
            # 01 L88 keeps every reference pointing at a row that exists.
            refs = _refs(opts["eval"], "eval")
            evaluations = rl_lib.latest(rl_lib.read_rows(repo, "evaluations"), "evaluations")
            missing = [r["id"] for r in refs if r["id"] not in evaluations]
            if missing:
                raise rl_lib.RLError("validation", f"evaluation {', '.join(missing)} does not exist")
            fields["evaluation_refs"] = refs
        attempt_flags = any(opts.get(k) for k in ("command", "workdir", "track", "config"))
        if order.get("work_type") == "launch_order" and trow["id"] == "amend_todo_stuck":
            # 04 L64: an amend of a launch_order appends one attempt. proxy decision D-31:
            # it does so with or without --command, because one run is one attempt
            # (principle 10); without --command the previous attempt's command, workdir,
            # track and config are copied and only the run_id is new.
            _append_attempt(order, fields, opts)
        elif attempt_flags:
            # 04 L69: the done_pending_review amend row changes paths and references only, and
            # no other work type has attempts, so the four attempt flags have nothing to act on.
            raise rl_lib.RLError("usage",
                                 "--command/--workdir/--track/--config describe an attempt, "
                                 "which only a launch_order at todo or stuck has (04 L64, L69)",
                                 "amend the paths or the references instead")

        row = _append(repo, LEDGER, fields, actor, ctx["command"], status=order["status"],
                      version=order["version"] + 1, force=force, force_reason=force_reason,
                      skip_conditions=_is_supplement(order))
    return rl_lib.result(row, LEDGER)


def _append_attempt(order, fields, opts):
    """04 L64: a launch_order amend appends one attempt, run_id `<ho-id>-a<n>` (04 L43).

    With --command the new attempt runs the fixed command (21 L179). Without it, proxy
    decision D-31: the previous attempt's command, workdir, track and config are copied, so
    a re-run of the same command is its own attempt (principle 10, one run is one attempt).
    """
    attempts = list(fields.get("attempts") or [])
    previous = attempts[-1] if attempts else {}
    command = opts.get("command") or previous.get("command")
    if not command:
        raise rl_lib.RLError("validation", f"{order['id']} has no attempt to copy: "
                                           "give --command for the first one (04 L43)")
    config = dict(previous.get("config") or {})
    for item in opts.get("config") or []:
        key, sep, value = item.partition("=")
        if not sep:
            raise rl_lib.RLError("usage", f"--config takes k=v, got {item!r}")
        config[key] = value
    number = len(attempts) + 1
    attempts.append({
        "attempt": number,
        "command": command,
        "args": None,  # PENDING(part 21 L180)
        "workdir": opts.get("workdir") or previous.get("workdir"),
        "track": opts.get("track") or previous.get("track"),
        "config": config,
        "run_id": f"{order['id']}-a{number}",  # 04 L43
    })
    fields["attempts"] = attempts


# ---------------------------------------------------------------- estimate

def cmd_estimate(args, ctx):
    """in_progress -> same, holder writes: append one step_table row to the latest attempt
    and re-total that attempt's estimated_seconds (04 L43, L65; 12 L52)."""
    repo, actor, force, force_reason = rl_lib.context(ctx)
    positional, opts = _parse(args, ctx["command"])
    ho_id = _one_id(positional)

    with rl_lib.Lock(repo):
        rl_lib.check_who_can_call(actor, ctx["command"])
        order = _order(repo, ho_id)
        trow = rl_lib.find_transition("handoff estimate", order["status"])
        rl_lib.check_who_can_write(trow, actor, order)
        fields = _carry(order)
        attempts = list(fields.get("attempts") or [])
        if not attempts:
            raise rl_lib.RLError("validation", f"{ho_id} has no attempt to estimate (04 L65)")
        attempt = dict(attempts[-1])
        steps = list(attempt.get("step_table") or [])

        if opts.get("copy-from"):
            # 05 L66 / 12 L27: only one order of a batch is smoke-timed; the others copy that
            # step table with --copy-from and rescale it. Reading of 12 L50 (the step table's
            # shape and the estimated_seconds formula): copy the source's latest attempt step
            # by step, keep step, kind and smoke_seconds, and replace scale_factor with
            # --scale when given, so estimated_seconds stays smoke_seconds * scale_factor.
            source = _order(repo, opts["copy-from"])
            source_attempt = _latest_attempt(source)
            source_steps = list((source_attempt or {}).get("step_table") or [])
            if not source_steps:
                raise rl_lib.RLError("validation", f"{opts['copy-from']} has no step_table to copy (05 L66)")
            scale = _number(opts["scale"], "--scale") if opts.get("scale") else None
            for src in source_steps:
                factor = scale if scale is not None else src["scale_factor"]
                steps.append(_step(src["step"], src["kind"], src["smoke_seconds"], factor))
        else:
            name = opts.get("step")
            kind = opts.get("kind")
            if not name:
                raise rl_lib.RLError("usage", "rl handoff estimate needs --step NAME or --copy-from ID2")
            if kind not in ("gpu", "cpu"):
                raise rl_lib.RLError("usage", f"--kind takes gpu or cpu, got {kind!r}")
            if opts.get("smoke-seconds") is None or opts.get("scale") is None:
                raise rl_lib.RLError("usage", "--step needs --smoke-seconds S and --scale F (04 L43)")
            steps.append(_step(name, kind, _number(opts["smoke-seconds"], "--smoke-seconds"),
                               _number(opts["scale"], "--scale")))

        attempt["step_table"] = steps
        # 04 L43: estimated_seconds totals the latest attempt's rows only.
        attempt["estimated_seconds"] = sum(s["estimated_seconds"] for s in steps)
        attempts[-1] = attempt
        fields["attempts"] = attempts
        row = _append(repo, LEDGER, fields, actor, ctx["command"], status=order["status"],
                      version=order["version"] + 1, force=force, force_reason=force_reason)
    return rl_lib.result(row, LEDGER)


def _step(name, kind, smoke_seconds, scale_factor):
    """04 L43: {"step","kind","smoke_seconds","scale_factor","estimated_seconds"}."""
    return {"step": name, "kind": kind, "smoke_seconds": smoke_seconds,
            "scale_factor": scale_factor, "estimated_seconds": smoke_seconds * scale_factor}


# ---------------------------------------------------------------- stuck / resume

def cmd_stuck(args, ctx):
    """in_progress -> stuck, holder writes; the issue must exist and point back (04 L66)."""
    repo, actor, force, force_reason = rl_lib.context(ctx)
    positional, opts = _parse(args, ctx["command"])
    ho_id = _one_id(positional)
    iss_id = opts.get("issue")
    if not iss_id:
        raise rl_lib.RLError("usage", "rl handoff stuck ID --issue ISS needs --issue")

    with rl_lib.Lock(repo):
        rl_lib.check_who_can_call(actor, ctx["command"])
        order = _order(repo, ho_id)
        trow = rl_lib.find_transition("handoff stuck", order["status"])
        rl_lib.check_who_can_write(trow, actor, order)
        issue = rl_lib.latest(rl_lib.read_rows(repo, "issues"), "issues").get(iss_id)
        if issue is None:
            # 03 L224: an id nobody has is a usage error (exit 5). An issue that does exist
            # but does not point back is the precondition below, exit 2, which gyb can force.
            raise rl_lib.RLError("usage", f"no such issue: {iss_id}",
                                 "open one first: rl issue open --to R --kind cannot --text \"...\" "
                                 f"--handoff {ho_id}")
        pre = _Preconditions(trow, force)
        # 04 L66; 03 L23 fixes the write order: the issue first, then the row that cites it.
        pre.check("stuck.issue_links_back", issue.get("handoff_id") == ho_id,
                  f"issue {iss_id} does not point back at {ho_id} "
                  f"(its handoff_id is {issue.get('handoff_id')!r})",
                  f"link it first: rl issue link {iss_id} --handoff {ho_id}")
        pre.raise_if_failed()

        fields = _carry(order)
        fields["issue_id"] = iss_id                    # 04 L41
        fields["last_holder"] = order.get("holder")    # 04 L51
        fields["holder"] = None
        row = _append(repo, LEDGER, fields, actor, ctx["command"], status="stuck",
                      version=order["version"] + 1, force=force, force_reason=force_reason)
    return rl_lib.result(row, LEDGER)


def cmd_resume(args, ctx):
    """stuck -> todo, written by the role that answered the issue or by the owner; the
    linked issue must be answered (04 L67)."""
    repo, actor, force, force_reason = rl_lib.context(ctx)
    positional, _opts = _parse(args, ctx["command"])
    ho_id = _one_id(positional)

    with rl_lib.Lock(repo):
        rl_lib.check_who_can_call(actor, ctx["command"])
        order = _order(repo, ho_id)
        trow = rl_lib.find_transition("handoff resume", order["status"])
        iss_id = order.get("issue_id")
        versions = [r for r in rl_lib.read_rows(repo, "issues") if r.get("id") == iss_id]
        answered = [r for r in versions if r["status"] == "answered"]
        # 04 L67 who column: "the role that answered the issue" is the actor of the
        # issue version whose status is answered.
        answerer = max(answered, key=lambda r: r["version"])["actor"] if answered else None
        rl_lib.check_who_can_write(trow, actor, order,
                                   issue_answerer_role=answerer if answerer in rl_lib.ROLES else None)
        latest_issue = max(versions, key=lambda r: r["version"]) if versions else None
        pre = _Preconditions(trow, force)
        pre.check("resume.issue_answered",
                  latest_issue is not None and latest_issue["status"] == "answered",
                  f"issue {iss_id} is not answered yet "
                  f"(status {latest_issue['status'] if latest_issue else 'missing'})",
                  f"wait for the reply: rl issue reply {iss_id} --text \"...\"")
        pre.raise_if_failed()

        fields = _carry(order)
        fields["holder"] = None  # 04 L51: resume lands on todo, holder stays empty
        row = _append(repo, LEDGER, fields, actor, ctx["command"], status="todo",
                      version=order["version"] + 1, force=force, force_reason=force_reason)
    return rl_lib.result(row, LEDGER)


# ---------------------------------------------------------------- done

def cmd_done(args, ctx):
    """in_progress -> done_pending_review, holder writes; the deliverables of the work type
    must be there (04 L68 with 04 L35-37).

    proxy decision D-32: the deliverable paths may come on this same call, a work_order's
    with --report-method / --report-detail / --code-path and an analysis_order's with
    --notebook / --figure. They are merged over whatever an earlier amend set and then
    checked for existence, so handing in the work is one command and no new transition row
    is needed; in_progress still takes no amend (04 L64, L69).

    `--actual-seconds` does not exist here: it only comes from `rl run finish` (04 L43;
    30 L62), so it is refused as a usage error.
    """
    repo, actor, force, force_reason = rl_lib.context(ctx)
    positional, opts = _parse(args, ctx["command"], multi=("figure", "code-path"))
    ho_id = _one_id(positional)

    with rl_lib.Lock(repo):
        rl_lib.check_who_can_call(actor, ctx["command"])
        order = _order(repo, ho_id)
        trow = rl_lib.find_transition("handoff done", order["status"])
        rl_lib.check_who_can_write(trow, actor, order)
        fields = _carry(order)
        # proxy decision D-32: the paths given here are merged over what amend already set,
        # then checked below by the same 04 L68 preconditions.
        if opts.get("notebook") or opts.get("figure"):
            outputs = dict(fields.get("output_paths") or {})
            if opts.get("notebook"):
                outputs["notebook"] = opts["notebook"]
            if opts.get("figure"):
                outputs["figures"] = list(opts["figure"])
            fields["output_paths"] = outputs
        if opts.get("report-method") or opts.get("report-detail"):
            report = dict(fields.get("report_paths") or {})
            if opts.get("report-method"):
                report["method"] = opts["report-method"]
            if opts.get("report-detail"):
                report["detail"] = opts["report-detail"]
            fields["report_paths"] = report
        if opts.get("code-path"):
            paths = list(fields.get("code_paths") or [])
            for p in opts["code-path"]:
                if p not in paths:
                    paths.append(p)
            fields["code_paths"] = paths

        pre = _Preconditions(trow, force)
        work_type = order.get("work_type")
        if work_type == "work_order":
            report = fields.get("report_paths") or {}
            # 04 L68 with 04 L35-36: method and detail exist, code_paths is non-empty. The
            # quick-lane supplement never passes here (it opens straight at
            # done_pending_review, 04 L62), which is why detail is unconditional.
            pre.check("done.work_order_deliverables", _exists(repo, report.get("method")),
                      f"report_paths.method {report.get('method')!r} is missing or does not exist")
            pre.check("done.work_order_deliverables", _exists(repo, report.get("detail")),
                      f"report_paths.detail {report.get('detail')!r} is missing or does not exist")
            pre.check("done.work_order_deliverables", bool(fields.get("code_paths")),
                      "code_paths is empty")
        elif work_type == "launch_order":
            attempt = _latest_attempt(order)
            versions = _run_versions(repo, (attempt or {}).get("run_id"))
            ok = any(v["status"] == "finished" and v.get("exit_status") == "ok" for v in versions)
            pre.check("done.launch_order_ok_finished", ok,
                      f"the latest attempt's run row has no finished version with exit_status ok "
                      f"(run_id {(attempt or {}).get('run_id')})",
                      "finish the run first: rl run finish RUN_ID --exit ok --metric k=v --data-path P")
        else:
            outputs = fields.get("output_paths") or {}
            # PENDING(part 22 L117): whether output_paths hold repo paths or
            # analysis_artifact_root paths, and how two notebooks are recorded. Repo-relative
            # is the narrow reading every other path field takes (04 L35-36).
            pre.check("done.analysis_order_outputs_and_approved", _exists(repo, outputs.get("notebook")),
                      f"output_paths.notebook {outputs.get('notebook')!r} is missing or does not exist")
            for figure in outputs.get("figures") or []:
                pre.check("done.analysis_order_outputs_and_approved", _exists(repo, figure),
                          f"output_paths figure {figure!r} does not exist")
            evaluations = rl_lib.latest(rl_lib.read_rows(repo, "evaluations"), "evaluations")
            for ref in fields.get("evaluation_refs") or []:
                row_e = evaluations.get(ref["id"])
                pre.check("done.analysis_order_outputs_and_approved",
                          row_e is not None and row_e["status"] == "approved",
                          f"evaluation {ref['id']} is {row_e['status'] if row_e else 'missing'}, not approved",
                          "ask gyb to approve it: rl eval approve ID --quote \"...\"")
        pre.raise_if_failed()

        fields["last_holder"] = order.get("holder")  # 04 L51; 30 L45
        fields["holder"] = None
        row = _append(repo, LEDGER, fields, actor, ctx["command"], status="done_pending_review",
                      version=order["version"] + 1, force=force, force_reason=force_reason)
    return rl_lib.result(row, LEDGER)


# ---------------------------------------------------------------- accept / reject

def cmd_accept(args, ctx):
    """done_pending_review -> accepted, the owner writes (04 L70).

    The quick-lane supplement's owner is gyb (proxy decision D-24; 07 L116), so the same
    who_can_write column already makes gyb the only acceptor. A dispatch=manual order is
    accepted by gyb himself by default (sync-inbox Q43(e)), which needs no code: gyb is
    exempt from the who column (04 L57)."""
    repo, actor, force, force_reason = rl_lib.context(ctx)
    positional, _opts = _parse(args, ctx["command"])
    ho_id = _one_id(positional)

    with rl_lib.Lock(repo):
        rl_lib.check_who_can_call(actor, ctx["command"])
        order = _order(repo, ho_id)
        trow = rl_lib.find_transition("handoff accept", order["status"])
        rl_lib.check_who_can_write(trow, actor, order)
        fields = _carry(order)
        fields["holder"] = None  # 04 L51: accepted is not in_progress
        row = _append(repo, LEDGER, fields, actor, ctx["command"], status="accepted",
                      version=order["version"] + 1, force=force, force_reason=force_reason,
                      skip_conditions=_is_supplement(order))
        closed = _close_answered_issues(repo, actor, ctx["command"], ho_id)  # 04 L70; 03 L92
        _fyi_when_gyb_overrides(repo, actor, ctx["command"], order, "accepted")  # 04 L70, L114
    return rl_lib.result(row, LEDGER, {"closed_issues": closed})


def cmd_reject(args, ctx):
    """done_pending_review -> rejected, the owner writes, reason required (04 L71)."""
    repo, actor, force, force_reason = rl_lib.context(ctx)
    positional, _opts = _parse(args, ctx["command"])
    ho_id = _one_id(positional)
    reason = ctx["opts"].get("reason")  # --reason is a global flag (bin/rl)

    with rl_lib.Lock(repo):
        rl_lib.check_who_can_call(actor, ctx["command"])
        order = _order(repo, ho_id)
        trow = rl_lib.find_transition("handoff reject", order["status"])
        rl_lib.check_who_can_write(trow, actor, order)
        pre = _Preconditions(trow, force)
        pre.check("reject.reason_nonempty", bool(reason), "rl handoff reject needs --reason R")
        pre.raise_if_failed()

        fields = _carry(order)
        fields["reason"] = reason  # 04 L40
        fields["holder"] = None    # 04 L51
        row = _append(repo, LEDGER, fields, actor, ctx["command"], status="rejected",
                      version=order["version"] + 1, force=force, force_reason=force_reason,
                      skip_conditions=_is_supplement(order))
        _fyi_when_gyb_overrides(repo, actor, ctx["command"], order, "rejected")  # 04 L71, L114
    return rl_lib.result(row, LEDGER)


# ---------------------------------------------------------------- release

def _release_via(env=None):
    """04 L75 / proxy decision D-15: the hook's release rows carry via=session_end, or
    via=subagent_stop when the hook is releasing a subagent's orders."""
    env = env if env is not None else os.environ
    if env.get(rl_lib.ENV_CALLER) != "hook":
        return None
    return "subagent_stop" if env.get("RL_AGENT_ID") else "session_end"


def release_order(repo, actor, ctx_command, order, *, note=None, via=None, force=False,
                  force_reason=None, validate_who=True, internal=False):
    """One release version, `rejected -> todo` (04 L72) or `in_progress -> todo` (04 L75).

    Public so `rl session end` and `rl reclaim` write exactly this row instead of building
    their own. The caller holds rl_lib.Lock (03 L19). `internal=True` is the hook's and
    reclaim's case: rl writes the row for the session, so who-can-call does not apply and a
    role without `handoff release` in its ledger_writes (roles/run.json) still hands its
    orders back (05 L40; 06 L156).
    """
    trow = rl_lib.find_transition("handoff release", order["status"])
    if validate_who:
        rl_lib.check_who_can_write(trow, actor, order)
    was_in_progress = order["status"] == "in_progress"
    pre = _Preconditions(trow, force)
    if was_in_progress:
        # 04 L75 / 04 L39: progress_note is required here and not on rejected -> todo.
        pre.check("release.progress_note_nonempty", bool(note),
                  "in_progress -> todo needs --note \"<how far it got>\"")
    pre.raise_if_failed()

    fields = _carry(order)
    if note:
        fields["progress_note"] = note
    if was_in_progress:
        fields["last_holder"] = order.get("holder")  # 04 L51
    fields["holder"] = None
    row = _append(repo, LEDGER, fields, actor, ctx_command, status="todo",
                  version=order["version"] + 1, force=force, force_reason=force_reason, via=via,
                  skip_conditions=_is_supplement(order), internal=internal)
    if was_in_progress:
        # 04 L75, L195: rl opens an orphaned notice to the owner. Nothing is killed here: a
        # launch_order with a launched, unfinished run keeps running for the next run session
        # to adopt (04 L75 release.no_kill_if_launched; reclaim kills only with --kill).
        _notice(repo, actor, ctx_command, "orphaned", rl_lib.owner_of(order),
                f"the holder session of {order['id']} is gone; the order is back at todo",
                order["id"])
    return row


def release_held_orders(repo, actor, *, via, command, extra_note=None):
    """Every in_progress order this session holds, handed back to todo (04 L122: none left).

    Used by `rl session end` (the hook's four steps, 04 L124-127) and by `rl reclaim`. The
    caller holds rl_lib.Lock. `extra_note(ho_id) -> str` adds text to the progress note, for
    the `wip/<ho-id>` branch the hook makes (04 L127). Returns the released ids, which the
    caller records in the closed session row's released_handoffs (04 L122).
    """
    rows = rl_lib.latest(rl_lib.read_rows(repo, LEDGER), LEDGER)
    # The holder is the pair (session_id, agent_id or empty), proxy decision D-15 addendum:
    # a subagent shares its parent's session_id, so a parent's session end must not sweep a
    # subagent's orders and SubagentStop releases only its own chain's.
    mine = _actor_key(actor)
    held = sorted([r for r in rows.values()
                   if r["status"] == "in_progress" and _holder_key(r) == mine],
                  key=lambda r: r["id"])
    released = []
    for order in held:
        # 04 L125: the note says "session ended, holder was X".
        note = f"session ended, holder was {actor.session_id}"
        if extra_note:
            addition = extra_note(order["id"])
            if addition:
                note = f"{note}; {addition}"
        release_order(repo, actor, command, order, note=note, via=via, validate_who=False,
                      internal=True)
        released.append(order["id"])
    return released


def cmd_release(args, ctx):
    """rejected -> todo (04 L72) or in_progress -> todo (04 L75)."""
    repo, actor, force, force_reason = rl_lib.context(ctx)
    positional, opts = _parse(args, ctx["command"])
    ho_id = _one_id(positional)

    with rl_lib.Lock(repo):
        rl_lib.check_who_can_call(actor, ctx["command"])
        order = _order(repo, ho_id)
        row = release_order(repo, actor, ctx["command"], order, note=opts.get("note"),
                            via=_release_via(), force=force, force_reason=force_reason)
    return rl_lib.result(row, LEDGER)


# ---------------------------------------------------------------- withdraw

def _withdraw_one(repo, actor, ctx_command, order, reason, quote, force, force_reason,
                  validate_who=True):
    trow = rl_lib.find_transition("handoff withdraw", order["status"])
    if validate_who:
        rl_lib.check_who_can_write(trow, actor, order)
    was_in_progress = order["status"] == "in_progress"
    holder = order.get("holder")
    fields = _carry(order)
    fields["reason"] = reason  # 04 L40
    if quote:
        fields["quote"] = quote  # 04 L40, L74
    if was_in_progress:
        fields["last_holder"] = holder  # 04 L51
    fields["holder"] = None
    row = _append(repo, LEDGER, fields, actor, ctx_command, status="withdrawn",
                  version=order["version"] + 1, force=force, force_reason=force_reason,
                  skip_conditions=_is_supplement(order))
    if was_in_progress:
        # 04 L74, L194: a withdrawal from in_progress notifies the holder's role and the
        # owner; other statuses do not notify. A run still going on a withdrawn launch order
        # is doctor item 8's job, not this notice's: kill it by its watch_cmd, then
        # `rl run finish --exit killed` (05 L207).
        # sync-inbox Q45(b): the text tells the holder to report where the code and the
        # half-finished artifact directory are. PENDING(issue 50): what that report contains
        # when the holder is run rather than deploy (proxy decision D-14).
        text = (f"{order['id']} was withdrawn: {reason}. Report the code location and the "
                "half-finished artifact directory into this issue; nothing is moved, gyb decides.")
        recipients = []
        holder_role = _role_of_session(repo, holder, order.get("agent_id")) if holder else None
        if holder_role:
            recipients.append(holder_role)
        owner = rl_lib.owner_of(order)
        if owner not in recipients:
            recipients.append(owner)
        for who in recipients:
            _notice(repo, actor, ctx_command, "withdrawn", who, text, order["id"])
    return row


def _children_of(repo, ho_id):
    rows = rl_lib.latest(rl_lib.read_rows(repo, LEDGER), LEDGER)
    terminal = set(rl_lib.TRANSITIONS["terminal_states"])  # accepted, withdrawn (04 L47)
    return sorted([r for r in rows.values()
                   if r.get("parent_id") == ho_id and r["status"] not in terminal],
                  key=lambda r: r["id"])


def cmd_withdraw(args, ctx):
    """any non-terminal -> withdrawn, the owner writes (04 L74)."""
    repo, actor, force, force_reason = rl_lib.context(ctx)
    positional, opts = _parse(args, ctx["command"], flags=("cascade",))
    ho_id = _one_id(positional)
    reason = ctx["opts"].get("reason")   # global flag
    quote = ctx["opts"].get("quote")     # global flag

    with rl_lib.Lock(repo):
        rl_lib.check_who_can_call(actor, ctx["command"])
        order = _order(repo, ho_id)
        trow = rl_lib.find_transition("handoff withdraw", order["status"])
        rl_lib.check_who_can_write(trow, actor, order)
        pre = _Preconditions(trow, force)
        pre.check("withdraw.reason_nonempty", bool(reason), "rl handoff withdraw needs --reason R")
        # 04 L74 / 04 L40: a withdrawal issued from a role session also needs quote.
        pre.check("withdraw.quote_if_role_session", actor.bare_terminal or bool(quote),
                  "a withdrawal from a role session needs --quote \"<gyb's words>\"")
        pre.raise_if_failed()

        row = _withdraw_one(repo, actor, ctx["command"], order, reason, quote, force, force_reason)
        cascaded = []
        if opts.get("cascade"):
            # 04 L74: --cascade withdraws, on the owner's behalf, the orders whose parent_id
            # points at this one; the downstream rows record the initiator as actor, so the
            # who_can_write column of those rows is not applied to the initiator.
            for child in _children_of(repo, ho_id):
                _withdraw_one(repo, actor, ctx["command"], child, reason, quote, force,
                              force_reason, validate_who=False)
                cascaded.append(child["id"])
    return rl_lib.result(row, LEDGER, {"cascaded": cascaded})


# ---------------------------------------------------------------- reissue

def cmd_reissue(args, ctx):
    """any non-terminal -> the old order withdrawn (cascading) plus a new todo order that
    supersedes it (04 L76; 02 L91)."""
    repo, actor, force, force_reason = rl_lib.context(ctx)
    positional, opts = _parse(args, ctx["command"], multi=("decision",))
    ho_id = _one_id(positional)
    refs = _refs(opts.get("decision"), "decision")

    with rl_lib.Lock(repo):
        rl_lib.check_who_can_call(actor, ctx["command"])
        order = _order(repo, ho_id)
        trow = rl_lib.find_transition("handoff reissue", order["status"])
        rl_lib.check_who_can_write(trow, actor, order)
        pre = _Preconditions(trow, force)
        pre.check("reissue.decision_ref_given", bool(refs),
                  "rl handoff reissue needs --decision ID@V naming the new decision version")
        index = _decision_index(repo)
        for ref in refs:
            pre.check("reissue.decision_ref_given", ref["id"] in index,
                      f"decision {ref['id']} does not exist")
        pre.raise_if_failed()

        # 04 L76 side effect: rl withdraws the old order, cascading. The reason is written by
        # rl because the row needs one (04 L40) and reissue has no --reason; the withdraw
        # row's quote precondition is not applied either, because this withdrawal is rl's own
        # step inside reissue, not a withdrawal a role issued (04 L74 vs L76).
        new_id = rl_lib.next_number([r["id"] for r in rl_lib.read_rows(repo, LEDGER)], "ho")
        reason = f"reissued as {new_id} on {refs[0]['id']}@{refs[0]['version']}"
        _withdraw_one(repo, actor, ctx["command"], order, reason, None, force, force_reason,
                      validate_who=False)
        for child in _children_of(repo, ho_id):
            _withdraw_one(repo, actor, ctx["command"], child, reason, None, force, force_reason,
                          validate_who=False)

        # 04 L76 / 02 L91: the new order starts at todo, inherits explanation, parent_id and
        # batch, and sets supersedes. work_type, to_role, track and dispatch come along too
        # (the brief's list); PENDING(part 20 L130): whether report_paths and code_paths are
        # inherited - they are not, which is the narrow reading of 04 L76's list.
        fields = {
            "id": new_id,
            "work_type": order["work_type"],
            # PENDING(part 04 L76): the new order's from_role is not stated; it inherits the
            # old owner, who is the only actor allowed to reissue.
            "from_role": order["from_role"],
            "to_role": order["to_role"],
            "holder": None,
            "last_holder": None,
            "dispatch": order.get("dispatch", "auto"),
            "supersedes": ho_id,
            "decision_refs": refs,
            "line": _line_of(repo, refs),
            # 04 L76 / 02 L91: parent_id and batch are inherited as they stand, empty included.
            "parent_id": order.get("parent_id"),
            "batch": order.get("batch"),
        }
        for key in ("explanation", "track"):
            if order.get(key) is not None:
                fields[key] = order[key]
        if order.get("work_type") == "launch_order":
            # PENDING(part 04 L76): attempts are not in the inherited list, but the schema
            # requires them on a launch_order. Copied as the instructions of the attempt
            # (command, args, workdir, track, config) with the run_id renumbered onto the new
            # order (04 L43: run_id is <ho-id>-a<attempt>). The measurements are left behind:
            # step_table and estimated_seconds come from a smoke run of the old order, and
            # actual_seconds is rl's own value copied from the runs finish version (04 L43),
            # which the new order has not got.
            fields["attempts"] = [
                {k: v for k, v in dict(a, run_id=f"{new_id}-a{a['attempt']}").items()
                 if k not in ("step_table", "estimated_seconds", "actual_seconds")}
                for a in order.get("attempts") or []]
        new_row = _append(repo, LEDGER, fields, actor, ctx["command"], status="todo", version=1,
                          force=force, force_reason=force_reason)
    return rl_lib.result(new_row, LEDGER, {"supersedes": ho_id})


# ---------------------------------------------------------------- queries

def cmd_show(args, ctx):
    """05 L67: anyone may read (03 L25: reads are not permissioned)."""
    repo = rl_lib.find_repo_root()
    positional, _opts = _parse(args, ctx["command"])
    ho_id = _one_id(positional)
    row = _order(repo, ho_id)
    if ctx["opts"]["json"]:
        return row
    return _one_line(row)


def cmd_list(args, ctx):
    """05 L67: the latest version per id, filtered."""
    repo = rl_lib.find_repo_root()
    positional, opts = _parse(args, ctx["command"])
    if positional:
        raise rl_lib.RLError("usage", f"rl handoff list takes no positional argument, got {positional[0]!r}")
    rows = sorted(rl_lib.latest(rl_lib.read_rows(repo, LEDGER), LEDGER).values(),
                  key=lambda r: r["id"])
    out = []
    for row in rows:
        if opts.get("status") and row["status"] != opts["status"]:
            continue
        if opts.get("owner") and rl_lib.owner_of(row) != opts["owner"]:   # 04 L49
            continue
        if opts.get("holder") and row.get("holder") != opts["holder"]:
            continue
        if opts.get("to") and row.get("to_role") != opts["to"]:
            continue
        if opts.get("batch") and row.get("batch") != opts["batch"]:
            continue
        if opts.get("decision") and opts["decision"] not in [r["id"] for r in row.get("decision_refs") or []]:
            continue
        if opts.get("line") and row.get("line") != opts["line"]:
            continue
        out.append(row)
    if ctx["opts"]["json"]:
        return out
    return "\n".join(_one_line(r) for r in out)


def _one_line(row):
    return (f"{row['id']} {row['work_type']} {row['status']} "
            f"owner={rl_lib.owner_of(row)} to={row.get('to_role')} holder={row.get('holder')}")
