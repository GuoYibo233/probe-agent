"""`rl feedback ...`: the feedback ledger (03 L139-152; 09 L69-93; 05 L80).

Anyone proposes, only gyb rules, everyone reads (03 L141). Five sub-commands (09 L81-85):
add, accept, reject, show, list. Every rule carries the part and line it transcribes.

`accept` does four things (09 L87): check every applied_to path exists, add one to the
`rules_version` line of common/GLOBAL-RULES.md and write it back, list the still-live
sessions with their rules_version, print a to-do. The rules line is the single source of
truth (09 L59); `rl_lib.rules_version()` reads it and honours RL_COMMON_DIR, so the
write-back goes to the same file.
"""

from __future__ import annotations

import os
from pathlib import Path

import rl_lib

TERMINAL = ("accepted", "rejected")  # 09 L73: both are terminal, propose again as a new row


def _common_dir() -> Path:
    """The master rules directory: the sandbox copy when RL_COMMON_DIR is set (tests
    seam, tables/README.md 7), else the plugin's common/ (09 L59)."""
    return Path(os.environ.get(rl_lib.ENV_COMMON_DIR) or rl_lib.COMMON_DIR)


def _bump_rules_version(after: int) -> None:
    """09 L59: `rl feedback accept` adds one to the first line of common/GLOBAL-RULES.md
    and writes it back; this is the only place rl writes into the master file."""
    path = _common_dir() / "GLOBAL-RULES.md"
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    first = lines[0]
    ending = first[len(first.rstrip("\r\n")):]
    lines[0] = f"rules_version: {after}{ending}"
    path.write_text("".join(lines), encoding="utf-8")


def _live_sessions(repo: Path) -> list[dict]:
    """09 L65: accept lists the sessions that are still alive with their rules_version, so
    gyb can pick which to close. Alive = the latest version of the chain is open (03 L176)."""
    rows = [r for r in rl_lib.latest(rl_lib.read_rows(repo, "sessions"), "sessions").values()
            if r["status"] == "open"]
    rows.sort(key=lambda r: (r.get("ts", ""), r["session_id"]))
    return rows


def _todo(fb_id: str, after: int) -> list[str]:
    """09 L87: the to-do says which places still need editing, whether to close sessions,
    and that the master change is its own commit plus a test run (09 L89: the commit
    prefix is `research-loop rules:`)."""
    return [
        f"to-do 1: edit the places {fb_id} names that are not edited yet (the master text is changed by hand, rl only moved the rules_version line to {after}).",
        "to-do 2: decide which of the live sessions above to close; closing one is `rl session end --session ID` (09 L65).",
        "to-do 3: commit the master change on its own with the prefix `research-loop rules:` and run tests/run_all.py (09 L89).",
    ]


def _latest(repo: Path, fb_id: str) -> tuple[dict | None, int]:
    return rl_lib.next_version_of(repo, "feedback", fb_id)


def _line(row: dict) -> str:
    bits = [row["id"], row["status"], f"v{row['version']}", f"actor={row['actor']}",
            f"target={row['target']}", row["text"]]
    if row.get("verdict_text"):
        bits.append(f"verdict={row['verdict_text']}")
    if row.get("applied_to"):
        bits.append("applied_to=" + ",".join(row["applied_to"]))
    return "  ".join(str(b) for b in bits)


# ---------------------------------------------------------------- add

def cmd_add(args: list[str], ctx: dict):
    """`rl feedback add --target ... --text ...` (05 L80; 09 L81): anyone proposes."""
    positional, opts = rl_lib.parse_args(args)
    if positional:
        raise rl_lib.RLError("usage", f"rl feedback add takes no positional argument: {positional[0]!r}",
                             "usage: rl feedback add --target T --text X")
    unknown = set(opts) - {"target", "text"}
    if unknown:
        raise rl_lib.RLError("usage", f"unknown flag(s) for rl feedback add: {', '.join(sorted(unknown))}",
                             "usage: rl feedback add --target T --text X")
    target, text = opts.get("target"), opts.get("text")
    if not target or not text:
        raise rl_lib.RLError("usage", "rl feedback add needs --target and --text",
                             "usage: rl feedback add --target T --text X")
    repo, actor, force, force_reason = rl_lib.context(ctx)
    # 03 L146; 09 L73 fix the two shapes a target may take and nothing else: a file path,
    # or a prefixed number like rule-06. A table row is given as the table's file path with
    # the row named in the text. rl checks that a path exists only for applied_to on the
    # accepted version (03 L149), so nothing is checked here.
    with rl_lib.Lock(repo):  # 03 L19: scan, number, append inside one lock
        ids = [r["id"] for r in rl_lib.read_rows(repo, "feedback")]
        fb_id = rl_lib.next_number(ids, "fb")  # fb-NNNN, proxy decision D-11
        row = rl_lib.write_row(repo, "feedback", {"id": fb_id, "target": target, "text": text},
                               actor, ctx["command"], status="proposed", version=1,
                               force=force, force_reason=force_reason)
    if ctx["opts"]["json"]:
        return rl_lib.result(row, "feedback")
    return _line(row)


# ---------------------------------------------------------------- accept

def cmd_accept(args: list[str], ctx: dict):
    """`rl feedback accept ID --applied-to FILE ... --text V` (05 L80; 09 L82, L87): gyb
    rules; verdict_text and at least one existing applied_to path are required
    (03 L148-149, L152)."""
    positional, opts = rl_lib.parse_args(args, multi=("applied-to",))
    if len(positional) != 1:
        raise rl_lib.RLError("usage", "rl feedback accept takes exactly one feedback id",
                             "usage: rl feedback accept ID --applied-to FILE ... --text V")
    unknown = set(opts) - {"applied-to", "text"}
    if unknown:
        raise rl_lib.RLError("usage", f"unknown flag(s) for rl feedback accept: {', '.join(sorted(unknown))}",
                             "usage: rl feedback accept ID --applied-to FILE ... --text V")
    fb_id = positional[0]
    applied_to = opts.get("applied-to") or []
    repo, actor, force, force_reason = rl_lib.context(ctx)
    with rl_lib.Lock(repo):  # 03 L19
        latest, version = _latest(repo, fb_id)
        if latest is None:
            raise rl_lib.RLError("usage", f"no feedback {fb_id}", "check `rl feedback list`")
        if latest["status"] in TERMINAL:
            raise rl_lib.RLError("validation",
                                 f"{fb_id} is {latest['status']}, which is terminal; it takes no further version",
                                 "propose again with `rl feedback add`, saying in the text which row it follows (09 L73)")
        # 03 L149, L152: rl checks every applied_to path exists. Integrity checks bind gyb
        # too (01 L88), so this runs before the row is written.
        missing = [p for p in applied_to if not (repo / p).exists()]
        if missing and not force:
            raise rl_lib.RLError("validation", f"applied_to path(s) do not exist: {', '.join(missing)}",
                                 "write the paths you actually changed; gyb may bypass with --force --reason (03 L27)")
        after = rl_lib.rules_version() + 1  # 09 L59: accept adds one to the master's line
        fields = {"id": fb_id, "target": latest["target"], "text": latest["text"],
                  "verdict_text": opts.get("text"),  # 03 L148
                  "applied_to": applied_to, "rules_version_after": after}  # 03 L149-150
        fields = {k: v for k, v in fields.items() if v not in (None, [])}
        row = rl_lib.write_row(repo, "feedback", fields, actor, ctx["command"],
                               status="accepted", version=version, force=force, force_reason=force_reason)
        # Written back only after the row is in: a refused row must not leave the master
        # file bumped (09 L59).
        _bump_rules_version(after)
        live = _live_sessions(repo)
    todo = _todo(fb_id, after)
    if ctx["opts"]["json"]:
        return rl_lib.result(row, "feedback",
                             {"rules_version_after": after,
                              "live_sessions": [{"session_id": s["session_id"], "role": s["role"],
                                                 "rules_version": s.get("rules_version"),
                                                 "agent_id": s.get("agent_id")} for s in live],
                              "todo": todo})
    lines = [f"{fb_id} accepted, rules_version {after - 1} -> {after}", "live sessions:"]
    if live:
        lines += [f"  {s['session_id']}  {s['role']}  rules_version={s.get('rules_version')}" for s in live]
    else:
        lines.append("  (none live; rules_version is now " + str(after) + ")")
    lines += todo
    return "\n".join(lines)


# ---------------------------------------------------------------- reject

def cmd_reject(args: list[str], ctx: dict):
    """`rl feedback reject ID --text V` (05 L80; 09 L83): gyb rules; verdict_text says why
    it was not adopted (03 L148)."""
    positional, opts = rl_lib.parse_args(args)
    if len(positional) != 1:
        raise rl_lib.RLError("usage", "rl feedback reject takes exactly one feedback id",
                             "usage: rl feedback reject ID --text V")
    unknown = set(opts) - {"text"}
    if unknown:
        raise rl_lib.RLError("usage", f"unknown flag(s) for rl feedback reject: {', '.join(sorted(unknown))}",
                             "usage: rl feedback reject ID --text V")
    fb_id = positional[0]
    repo, actor, force, force_reason = rl_lib.context(ctx)
    with rl_lib.Lock(repo):  # 03 L19
        latest, version = _latest(repo, fb_id)
        if latest is None:
            raise rl_lib.RLError("usage", f"no feedback {fb_id}", "check `rl feedback list`")
        if latest["status"] in TERMINAL:
            raise rl_lib.RLError("validation",
                                 f"{fb_id} is {latest['status']}, which is terminal; it takes no further version",
                                 "propose again with `rl feedback add`, saying in the text which row it follows (09 L73)")
        fields = {"id": fb_id, "target": latest["target"], "text": latest["text"]}
        if opts.get("text"):
            fields["verdict_text"] = opts["text"]  # 03 L148: required on the rejected version
        row = rl_lib.write_row(repo, "feedback", fields, actor, ctx["command"],
                               status="rejected", version=version, force=force, force_reason=force_reason)
    if ctx["opts"]["json"]:
        return rl_lib.result(row, "feedback")
    return _line(row)


# ---------------------------------------------------------------- queries

def cmd_show(args: list[str], ctx: dict):
    """`rl feedback show ID` (05 L80). Queries are open to everyone (03 L25)."""
    positional, opts = rl_lib.parse_args(args)
    if len(positional) != 1:
        raise rl_lib.RLError("usage", "rl feedback show takes exactly one feedback id",
                             "usage: rl feedback show ID")
    repo = rl_lib.find_repo_root()
    latest, _ = _latest(repo, positional[0])
    if latest is None:
        raise rl_lib.RLError("usage", f"no feedback {positional[0]}", "check `rl feedback list`")
    if ctx["opts"]["json"]:
        return latest
    return _line(latest)


def cmd_list(args: list[str], ctx: dict):
    """`rl feedback list` (05 L80; 09 L85): the latest version of every row (03 L11)."""
    positional, opts = rl_lib.parse_args(args)
    if positional:
        raise rl_lib.RLError("usage", f"rl feedback list takes no positional argument: {positional[0]!r}",
                             "usage: rl feedback list")
    if opts:
        # 05 L80; 09 L85: `rl feedback list` takes no flag.
        raise rl_lib.RLError("usage", f"rl feedback list takes no flag: {', '.join(sorted(opts))}",
                             "usage: rl feedback list")
    repo = rl_lib.find_repo_root()
    rows = list(rl_lib.latest(rl_lib.read_rows(repo, "feedback"), "feedback").values())
    rows.sort(key=lambda r: r["id"])
    if ctx["opts"]["json"]:
        return {"feedback": rows}
    return "\n".join(_line(r) for r in rows)
