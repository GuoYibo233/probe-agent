"""rl issue: the issues ledger (03 L63-92; 05 L54-58).

Sub-commands: open, reassign, reply, close, link (writes, per the role's ledger_writes)
and show, list (queries, open to everyone, 05 L100). Every rule below carries the part and
line it transcribes.
"""

from __future__ import annotations

import sys

import rl_lib

# 03 L76: log_tail is the last 40 lines of the log, kept as text, never as a path.
LOG_TAIL_LINES = 40

# 03 L92: the three notification kinds, which the addressee may close as well.
NOTIFICATION_KINDS = ("withdrawn", "orphaned", "fyi")

# The row's own content fields (03 L67-76); the skeleton's seven fields are written fresh
# for every version by rl_lib.skeleton, so a new version copies these and nothing else.
CONTENT_FIELDS = ("assignee", "kind", "text", "stage", "handoff_id", "log_tail", "reply")


def _out(ctx, payload, text):
    """--json returns the structure, a bare terminal reads the text form (05 L121)."""
    return payload if ctx["opts"]["json"] else text


def _write_row(repo, fields, actor, command, *, status, version, force=False, force_reason=None):
    """Thin wrapper over rl_lib.write_row; --force handling lives in rl_lib.validate_row
    (03 L27; 01 L90: required lists dropped, shape kept; reviewer fix on 529b8ef)."""
    return rl_lib.write_row(repo, "issues", fields, actor, command, status=status, version=version,
                            force=force, force_reason=force_reason)


def _carry(previous: dict) -> dict:
    """The content fields of the previous version, for the next one (03 L11: a change is
    one more version, and the row that goes down is complete on its own)."""
    return {key: previous[key] for key in CONTENT_FIELDS if key in previous}


def _head(repo, issue_id: str):
    """(latest version, next version number) of one issue; an unknown id is exit 5
    (05 L115)."""
    previous, version = rl_lib.next_version_of(repo, "issues", issue_id)
    if previous is None:
        raise rl_lib.RLError("usage", f"unknown issue {issue_id}")
    return previous, version


def _check_handoff_exists(repo, handoff_id: str) -> None:
    """01 L88: reference existence is an integrity check and binds gyb too; 05 L196 doctor
    item 2 scans issues' handoff_id for dangling references."""
    if handoff_id not in rl_lib.latest(rl_lib.read_rows(repo, "handoffs"), "handoffs"):
        raise rl_lib.RLError("validation", f"handoff {handoff_id} is not in the handoffs ledger",
                             "point --handoff at an order that exists (01 L88)")


def _log_tail(opts) -> str | None:
    """03 L76: `--log-tail FILE` has rl cut the last 40 lines, `--log-text -` reads them
    from standard input; either way the ledger holds the text, never the path."""
    if opts.get("log-tail") and opts.get("log-text"):
        raise rl_lib.RLError("usage", "--log-tail and --log-text are the two ways to give one log tail",
                             "give one of them (03 L76)")
    if opts.get("log-tail"):
        try:
            with open(opts["log-tail"], encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as err:
            raise rl_lib.RLError("usage", f"cannot read --log-tail {opts['log-tail']}: {err}")
    elif opts.get("log-text"):
        if opts["log-text"] != "-":
            raise rl_lib.RLError("usage", f"--log-text takes only `-`, got {opts['log-text']!r}",
                                 "`--log-text -` reads the log tail from standard input (03 L76)")
        text = sys.stdin.read()
    else:
        return None
    lines = text.splitlines()
    return "\n".join(lines[-LOG_TAIL_LINES:])


# ---------------------------------------------------------------- write sub-commands

def cmd_open(args, ctx):
    """05 L58: open an issue. Who may call it follows the role's ledger_writes (checked by
    rl_lib.check_who_can_call); which fields the kind demands follows the schema's
    x-conditions (03 L72, L75), applied by rl_lib.check_conditions."""
    _pos, opts = rl_lib.parse_args(args, allowed=rl_lib.allowed_options(ctx["command"]))
    repo, actor, force, reason = rl_lib.context(ctx)
    log_tail = _log_tail(opts)
    fields = {}
    if opts.get("to") is not None:
        fields["assignee"] = opts["to"]  # 03 L70: the assignee is a role or gyb
    if opts.get("kind") is not None:
        fields["kind"] = opts["kind"]  # 03 L71, L78-90: one of nine kinds
        if opts["kind"] in NOTIFICATION_KINDS:
            # proxy decision D-38 (04 L188-200; 03 L90): the three notification kinds are
            # opened only by rl at their trigger points (handoff._notice); a hand-typed
            # `rl issue open --kind fyi|orphaned|withdrawn` is refused for everyone, gyb too.
            raise rl_lib.RLError(
                "validation",
                f"kind {opts['kind']} is a notification rl opens by itself (04 L188-200; "
                f"proxy decision D-38); pick one of the other kinds")
    if opts.get("stage") is not None:
        fields["stage"] = opts["stage"]  # 03 L72: required when kind is failed
    if opts.get("text") is not None:
        fields["text"] = opts["text"]
    if opts.get("handoff") is not None:
        _check_handoff_exists(repo, opts["handoff"])
        fields["handoff_id"] = opts["handoff"]
    if log_tail is not None:
        fields["log_tail"] = log_tail
    with rl_lib.Lock(repo):  # 03 L19: scan, assign and append under one lock
        ids = [r["id"] for r in rl_lib.read_rows(repo, "issues")]
        fields["id"] = rl_lib.next_number(ids, "iss")  # 03 L21, L69: iss-0001 upwards
        row = _write_row(repo, fields, actor, "issue open", status="open", version=1,
                         force=force, force_reason=reason)
    return _out(ctx, rl_lib.result(row, "issues"), f"{row['id']} open to {row.get('assignee')}")


def cmd_reassign(args, ctx):
    """03 L92: reassigning is one more version with a new assignee."""
    pos, opts = rl_lib.parse_args(args, allowed=rl_lib.allowed_options(ctx["command"]))
    if not pos:
        raise rl_lib.RLError("usage", "rl issue reassign needs an issue id")
    issue_id = pos[0]
    repo, actor, force, reason = rl_lib.context(ctx)
    with rl_lib.Lock(repo):  # 03 L19
        previous, version = _head(repo, issue_id)
        fields = _carry(previous)
        fields["id"] = issue_id
        if opts.get("to") is not None:
            fields["assignee"] = opts["to"]
        row = _write_row(repo, fields, actor, "issue reassign", status=previous["status"],
                         version=version, force=force, force_reason=reason)
    return _out(ctx, rl_lib.result(row, "issues"), f"{issue_id} v{version} to {row.get('assignee')}")


def cmd_reply(args, ctx):
    """03 L92: only the assignee or gyb writes the reply; 03 L74: a version whose status is
    answered carries the reply text."""
    pos, opts = rl_lib.parse_args(args, allowed=rl_lib.allowed_options(ctx["command"]))
    if not pos:
        raise rl_lib.RLError("usage", "rl issue reply needs an issue id")
    issue_id = pos[0]
    repo, actor, force, reason = rl_lib.context(ctx)
    with rl_lib.Lock(repo):  # 03 L19
        previous, version = _head(repo, issue_id)
        if not actor.is_gyb and actor.role_session != previous.get("assignee"):
            raise rl_lib.RLError(
                "forbidden", f"{actor.role_session} is not the assignee of {issue_id} "
                             f"({previous.get('assignee')}); only the assignee or gyb replies (03 L92)",
                "ask the assignee, or gyb: " + rl_lib.issue_command_for_gyb(f"please answer {issue_id}"))
        fields = _carry(previous)
        fields["id"] = issue_id
        if opts.get("text") is not None:
            fields["reply"] = opts["text"]
        row = _write_row(repo, fields, actor, "issue reply", status="answered", version=version,
                         force=force, force_reason=reason)
    return _out(ctx, rl_lib.result(row, "issues"), f"{issue_id} v{version} answered")


def cmd_close(args, ctx):
    """03 L92: only the actor who opened the issue or gyb closes it; for the three
    notification kinds (withdrawn, orphaned, fyi) the assignee closes it too, because the
    inbox only reads and the addressee closes the notice when done."""
    pos, _opts = rl_lib.parse_args(args, allowed=rl_lib.allowed_options(ctx["command"]))
    if not pos:
        raise rl_lib.RLError("usage", "rl issue close needs an issue id")
    issue_id = pos[0]
    repo, actor, force, reason = rl_lib.context(ctx)
    with rl_lib.Lock(repo):  # 03 L19
        previous, version = _head(repo, issue_id)
        versions = [r for r in rl_lib.read_rows(repo, "issues") if r["id"] == issue_id]
        opener = min(versions, key=lambda r: r["version"])["actor"]
        allowed = actor.is_gyb or actor.role_session == opener
        if previous.get("kind") in NOTIFICATION_KINDS and actor.role_session == previous.get("assignee"):
            allowed = True
        if not allowed:
            raise rl_lib.RLError(
                "forbidden", f"{actor.role_session} did not open {issue_id} ({opener} did); "
                             "only the opening actor or gyb closes it (03 L92)",
                "ask the opener, or gyb: " + rl_lib.issue_command_for_gyb(f"please close {issue_id}"))
        fields = _carry(previous)
        fields["id"] = issue_id
        row = _write_row(repo, fields, actor, "issue close", status="closed", version=version,
                         force=force, force_reason=reason)
    return _out(ctx, rl_lib.result(row, "issues"), f"{issue_id} v{version} closed")


def cmd_link(args, ctx):
    """05 L58, L197: `rl issue link ID --handoff ID` is doctor item 3's fix; it appends one
    more version that adds handoff_id and leaves everything else as it was."""
    pos, opts = rl_lib.parse_args(args, allowed=rl_lib.allowed_options(ctx["command"]))
    if not pos:
        raise rl_lib.RLError("usage", "rl issue link needs an issue id")
    issue_id = pos[0]
    repo, actor, force, reason = rl_lib.context(ctx)
    if opts.get("handoff") is None:
        raise rl_lib.RLError("usage", "rl issue link needs --handoff ID")
    _check_handoff_exists(repo, opts["handoff"])
    with rl_lib.Lock(repo):  # 03 L19
        previous, version = _head(repo, issue_id)
        fields = _carry(previous)
        fields["id"] = issue_id
        fields["handoff_id"] = opts["handoff"]
        row = _write_row(repo, fields, actor, "issue link", status=previous["status"],
                         version=version, force=force, force_reason=reason)
    return _out(ctx, rl_lib.result(row, "issues"), f"{issue_id} v{version} -> {opts['handoff']}")


# ---------------------------------------------------------------- query sub-commands

def cmd_show(args, ctx):
    """05 L58: show one issue. 03 L25: reading is open to everyone."""
    pos, _opts = rl_lib.parse_args(args, allowed=rl_lib.allowed_options(ctx["command"]))
    if not pos:
        raise rl_lib.RLError("usage", "rl issue show needs an issue id")
    issue_id = pos[0]
    repo, _actor, _force, _reason = rl_lib.context(ctx)
    versions = sorted([r for r in rl_lib.read_rows(repo, "issues") if r["id"] == issue_id],
                      key=lambda r: r["version"])
    if not versions:
        raise rl_lib.RLError("usage", f"unknown issue {issue_id}")  # 05 L115: exit 5
    latest = versions[-1]  # 03 L11: a read takes the latest version
    text = (f"{issue_id} v{latest['version']} {latest['status']} {latest['kind']} "
            f"to {latest['assignee']}: {latest.get('text', '')}")
    if latest.get("reply"):
        text += f"\nreply: {latest['reply']}"
    return _out(ctx, latest, text)


def cmd_list(args, ctx):
    """05 L58: `rl issue list [--open] [--to R] [--kind K]`."""
    _pos, opts = rl_lib.parse_args(args, flags=("open",), allowed=rl_lib.allowed_options(ctx["command"]))
    repo, _actor, _force, _reason = rl_lib.context(ctx)
    rows = rl_lib.latest(rl_lib.read_rows(repo, "issues"), "issues")
    out = []
    for issue_id in sorted(rows):
        row = rows[issue_id]
        if opts.get("open") and row["status"] != "open":
            continue
        if opts.get("to") and row.get("assignee") != opts["to"]:
            continue
        if opts.get("kind") and row.get("kind") != opts["kind"]:
            continue
        out.append(row)
    text = "\n".join(f"{r['id']} v{r['version']} {r['status']} {r['kind']} to {r['assignee']}: "
                     f"{r.get('text', '')}" for r in out)
    return _out(ctx, out, text)
