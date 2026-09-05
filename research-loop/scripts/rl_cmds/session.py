"""`rl session ...`: the sessions ledger (03 L174-192; 04 L116-160; 05 L40).

Six sub-commands (04 L149-156): start, end, amend, focus, show, list. Every rule below
carries the part and line it transcribes (`03 L15`) or the proxy decision it follows
(`proxy decision D-15`). Nothing here is invented; what the parts have not ruled is
marked `PENDING(...)` and listed in the build report.

Every row goes through `rl_lib.write_row`. Two of its switches carry rules of this group:

- `internal=True` for the rows rl writes on its own behalf: `session end`'s release rows
  and orphaned notices (04 L120: the deregistration hook does four things per held order),
  and `session amend`, whose who rule is "gyb or that role's own session" (03 L176; 04
  L153) instead of the role's `ledger_writes`. The who-can-call gate of `rl session end`
  itself is taken once at the top of the command (05 L40, "hook, gyb").
- `session start` is exempt from the closed-session refusal and writes the next open
  version of the same chain (proxy decision D-28; 03 L15: reloading the role is the way
  back), which `rl_lib.validate_row` carries.

Deleting `loop/.sessions/<session_id>.json` is the hook's last step (06 L120;
sync-inbox Q35(c)), not rl's; `hooks/rl_hook.py` does it after calling this command.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import rl_lib

# The nine skeleton fields (03 L31-43); a new version rebuilds them from the actor
# instead of copying them off the previous row.
SKELETON_KEYS = ("version", "status", "ts", "actor", "session_id", "schema_version",
                 "force_reason", "via", "agent_id")

LAUNCHED_BY = ("manual", "subagent", "workflow")  # 03 L183
END_REASONS = ("hook", "manual", "reclaim")  # 03 L189


# ---------------------------------------------------------------- small shared pieces

def _carry(row: dict) -> dict:
    """The content fields of a row, without the skeleton (03 L31-43)."""
    return {k: v for k, v in row.items() if k not in SKELETON_KEYS}


def _chains(repo: Path) -> dict:
    """Latest version per chain; a chain is (session_id, agent_id or empty)
    (03 L11; proxy decision D-15)."""
    return rl_lib.latest(rl_lib.read_rows(repo, "sessions"), "sessions")


def _chain(repo: Path, session_id: str, agent_id: str | None) -> dict | None:
    return _chains(repo).get(rl_lib.session_key(session_id, agent_id))


def _open_chains_of(repo: Path, session_id: str) -> list[dict]:
    """Every open chain under one session_id, the parent's chain first (proxy decision
    D-15: a subagent shares the session_id and gets its own chain by agent_id)."""
    rows = [r for r in _chains(repo).values()
            if r["session_id"] == session_id and r["status"] == "open"]
    rows.sort(key=lambda r: (bool(r.get("agent_id")), r.get("agent_id") or ""))
    return rows


def _last_activity(repo: Path, session_id: str) -> str | None:
    """03 L186; 04 L153: `last_activity` is not stored; queries compute it as the biggest
    `ts` over the nine ledgers for rows with this session_id, the sessions ledger
    included."""
    best = None
    for ledger in rl_lib.LEDGER_NAMES:
        rows = rl_lib.read_decisions(repo) if ledger == "decisions" else rl_lib.read_rows(repo, ledger)
        for row in rows:
            if row.get("session_id") == session_id and (best is None or row.get("ts", "") > best):
                best = row.get("ts")
    return best


def _line(row: dict) -> str:
    """One line per row for the text output (03 L25: every ledger has a query side)."""
    bits = [row["session_id"]]
    if row.get("agent_id"):
        bits.append(f"agent={row['agent_id']}")
    bits += [row["role"], row["status"], f"v{row['version']}", f"model={row.get('model')}",
             f"launched_by={row.get('launched_by')}", f"rules_version={row.get('rules_version')}"]
    if row.get("focus"):
        bits.append(f"focus={row['focus']}")
    if row.get("end_reason"):
        bits.append(f"end_reason={row['end_reason']}")
    return "  ".join(str(b) for b in bits)


# ---------------------------------------------------------------- start

def cmd_start(args: list[str], ctx: dict):
    """`rl session start --role R [--model M] [--launched-by manual|subagent|workflow]`
    (05 L40; 04 L151). Called by the plugin hook or by gyb; the hook writes on the role's
    behalf and the row's actor is the role (04 L118)."""
    positional, opts = rl_lib.parse_args(args)
    if positional:
        raise rl_lib.RLError("usage", f"rl session start takes no positional argument: {positional[0]!r}",
                             "usage: rl session start --role R [--model M] [--launched-by manual|subagent|workflow]")
    unknown = set(opts) - {"role", "model", "launched-by"}
    if unknown:
        raise rl_lib.RLError("usage", f"unknown flag(s) for rl session start: {', '.join(sorted(unknown))}",
                             "usage: rl session start --role R [--model M] [--launched-by manual|subagent|workflow]")
    role = opts.get("role")
    if role not in rl_lib.ROLES:
        raise rl_lib.RLError("usage", f"--role must be one of {', '.join(rl_lib.ROLES)}, not {role!r}",
                             "usage: rl session start --role R (03 L181)")
    repo, actor, force, force_reason = rl_lib.context(ctx)
    # model: the hook takes it from the hook input, `unknown` when it cannot (03 L182).
    model = opts.get("model") or "unknown"
    if actor.agent_id:
        # proxy decision D-15 (3): a subagent's row carries agent_id and launched_by subagent.
        launched_by = "subagent"
    else:
        # PENDING(part 03 L183): no default is ruled for launched_by; `manual` is the value
        # the registration hook uses for a role skill loaded by hand (06 L112).
        launched_by = opts.get("launched-by") or "manual"
    if launched_by not in LAUNCHED_BY:
        raise rl_lib.RLError("usage", f"--launched-by must be one of {', '.join(LAUNCHED_BY)}, not {launched_by!r}",
                             "usage: rl session start --launched-by manual|subagent|workflow (03 L183)")
    # rules_version comes from the first line of common/GLOBAL-RULES.md (03 L184; 09 L59).
    rules_version = rl_lib.rules_version()
    with rl_lib.Lock(repo):  # 03 L19
        previous = _chain(repo, actor.session_id, actor.agent_id)
        # Opening version is version 1 (tables/README.md construction 8). A chain that
        # already has versions continues its numbering: after a close that is the reload
        # (proxy decision D-28, the one command exempt from the closed-session refusal);
        # PENDING(part 06 L106): a second role load in a still-open session is not defined
        # by the machine, so this appends another open version of the same chain.
        version = previous["version"] + 1 if previous else 1
        fields = {"role": role, "model": model, "launched_by": launched_by,
                  "rules_version": rules_version, "started_at": rl_lib.now_iso()}  # 03 L185
        row = rl_lib.write_row(repo, "sessions", fields, actor, ctx["command"],
                               status="open", version=version, force=force, force_reason=force_reason)
    if ctx["opts"]["json"]:
        return rl_lib.result(row, "sessions", {"role": role, "rules_version": rules_version})
    return _line(row)


# ---------------------------------------------------------------- end

def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def _wip_branch(repo: Path, ho_id: str) -> tuple[str | None, str | None]:
    """04 L127: dirty changes under experiments/ go onto a branch `wip/<ho-id>` and the
    branch name goes into the progress note. Returns (branch, note-about-failure).

    Done without `git stash`: branch off the current HEAD, commit experiments/, go back.
    Any git step that fails leaves the working tree alone and is reported.

    PENDING(part 04 L127): 04 names one branch per released order, but a session has one
    working tree, so the dirty changes go onto the branch named after the first order this
    session end releases and every other released order's progress note points at that same
    branch; `_release_chain` does that bookkeeping."""
    status = _git(repo, "status", "--porcelain", "--", "experiments")
    if status.returncode != 0 or not status.stdout.strip():
        return None, None
    head = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    previous = head.stdout.strip()
    if head.returncode != 0 or not previous or previous == "HEAD":
        return None, "experiments/ left dirty: git has no current branch to come back to"
    branch = f"wip/{ho_id}"
    made = _git(repo, "checkout", "-b", branch)
    if made.returncode != 0:
        return None, f"experiments/ left dirty: git checkout -b {branch} failed"
    _git(repo, "add", "--", "experiments")
    commit = _git(repo, "commit", "-q", "-m", f"wip: experiments/ at session end for {ho_id}")
    back = _git(repo, "checkout", previous)
    if commit.returncode != 0:
        return None, f"experiments/ left dirty: git commit on {branch} failed"
    if back.returncode != 0:
        return branch, f"still on {branch}: git checkout {previous} failed"
    return branch, None


def _held_orders(repo: Path, session_id: str, agent_id: str | None, any_agent: bool) -> list[dict]:
    """The orders to hand back: latest version in_progress and holder is this session
    (04 L51: session end only looks at in_progress orders).

    `any_agent` is the top-level case (proxy decision D-15 (4)): a SessionEnd hands back
    everything held under its session_id, the orders of subagents killed with it included,
    because those subagents get no SubagentStop. A SubagentStop takes only its own chain,
    paired by (session_id, agent_id or empty) (D-15 addendum)."""
    latest = rl_lib.latest(rl_lib.read_rows(repo, "handoffs"), "handoffs")
    out = []
    for row in latest.values():
        if row["status"] != "in_progress" or row.get("holder") != session_id:
            continue
        if not any_agent and (row.get("agent_id") or "") != (agent_id or ""):
            continue
        out.append(row)
    out.sort(key=lambda r: r["id"])
    return out


def _release_chain(repo: Path, chain: dict, actor: rl_lib.Actor, via: str, any_agent: bool,
                   issue_ids: list[str], wip: dict) -> tuple[list[str], list[str]]:
    """The four things 04 L120-127 does for every order the chain holds: hand it back to
    todo, write the progress note, open an orphaned issue to the owner, branch the dirty
    experiments/ tree. Returns (released ids, notes about git failures)."""
    session_id = chain["session_id"]
    agent_id = chain.get("agent_id")
    released: list[str] = []
    notes: list[str] = []
    for order in _held_orders(repo, session_id, agent_id, any_agent):
        # 04 L75 release.no_kill_if_launched: a launch_order whose latest attempt has a
        # launched run row without a finished version is handed back untouched, no process
        # is killed; the next run adopts it. So there is nothing to do here but release.
        if not wip["tried"]:
            wip["tried"] = True  # one working tree, one branch: see _wip_branch
            wip["branch"], note = _wip_branch(repo, order["id"])
            if note:
                notes.append(f"{order['id']}: {note}")
                wip["note"] = note
        progress_note = f"session ended, holder was {session_id}"  # 04 L125
        if wip["branch"]:
            progress_note += f"; dirty experiments/ changes are on branch {wip['branch']}"  # 04 L127
        elif wip["note"]:
            progress_note += f"; {wip['note']}"
        fields = _carry(order)
        fields.update({"holder": None, "last_holder": session_id, "progress_note": progress_note})
        # 04 L51 holder invariant: leaving in_progress clears holder into last_holder.
        # internal=True: rl writes this row for the session, not the role calling
        # `rl handoff release` (04 L120; transitions.json release_in_progress lists
        # session_end_hook under who_can_write).
        rl_lib.write_row(repo, "handoffs", fields, actor, "handoff release",
                         status="todo", version=order["version"] + 1, via=via, internal=True)
        # 04 L75 release.orphaned_notice; 04 L195: the notice goes to the owner, and
        # handoff_id is required on an orphaned issue (03 L75).
        issue_id = rl_lib.next_number(issue_ids, "iss")
        issue_ids.append(issue_id)
        rl_lib.write_row(repo, "issues",
                         {"id": issue_id, "assignee": rl_lib.owner_of(order), "kind": "orphaned",
                          "handoff_id": order["id"],
                          "text": f"holder session {session_id} ended; {order['id']} went back to todo"},
                         actor, "issue open", status="open", version=1, via=via, internal=True)
        released.append(order["id"])
    return released, notes


def cmd_end(args: list[str], ctx: dict):
    """`rl session end [--session ID] [--end-reason hook|manual|reclaim]` (05 L40; 04 L152).

    05 L40 writes the flag as `--reason`, but `--reason` is one of bin/rl's global flags and
    carries gyb's `--force --reason` sentence, so the end reason has its own option
    `--end-reason`; `--reason` is still read as its alias while `--force` is absent, which
    is how the plugin hook calls it (`rl session end --reason hook`).

    Order of writes (03 L15; debt map 47(b)): first hand back every held order (those
    release rows carry this session's id and pass the writer-alive check because the
    sessions ledger still says open), then close the still-open subagent chains, and write
    the chain's closed version last."""
    positional, opts = rl_lib.parse_args(args)
    if positional:
        raise rl_lib.RLError("usage", f"rl session end takes no positional argument: {positional[0]!r}",
                             "usage: rl session end [--session ID] [--end-reason hook|manual|reclaim]")
    unknown = set(opts) - {"session", "end-reason"}
    if unknown:
        raise rl_lib.RLError("usage", f"unknown flag(s) for rl session end: {', '.join(sorted(unknown))}",
                             "usage: rl session end [--session ID] [--end-reason hook|manual|reclaim]")
    repo, actor, force, force_reason = rl_lib.context(ctx)
    # 05 L40: `session start` and `session end` are the hook's or gyb's. This is the one
    # who-can-call gate of the command; it is taken before anything is written, so a
    # refused caller never releases an order (03 L15 order of checks).
    rl_lib.check_who_can_call(actor, ctx["command"])
    target = opts.get("session") or actor.session_id
    other = target != actor.session_id
    if other and not actor.is_gyb:
        # 04 L152: closing another session is gyb's, and gyb alone may do it without
        # checking whether that session is alive.
        raise rl_lib.RLError("forbidden", "`rl session end --session ID` closes another session and is gyb's",
                             "ask gyb: " + rl_lib.issue_command_for_gyb(f"please close session {target}"))
    if other:
        # 04 L152: gyb closing another session is not stopped and the session is not checked
        # for being alive (rl sees ledgers, not processes); end_reason is manual.
        end_reason = "manual"
    else:
        end_reason = opts.get("end-reason")
        if end_reason is None and not force:
            end_reason = ctx["opts"]["reason"]  # 05 L40 spells the flag --reason
        if end_reason is None:
            # hook when the plugin hook is the caller (05 L40, RL_CALLER=hook), else manual.
            end_reason = "hook" if os.environ.get(rl_lib.ENV_CALLER) == "hook" else "manual"
    if end_reason not in END_REASONS:
        raise rl_lib.RLError("usage", f"--end-reason must be one of {', '.join(END_REASONS)}, not {end_reason!r}",
                             "usage: rl session end [--end-reason hook|manual|reclaim] (03 L189)")
    # via: the hook's release rows record via=session_end; a SubagentStop release records
    # via=subagent_stop (05 L27-29; proxy decision D-15 (4)).
    via = "subagent_stop" if actor.agent_id else "session_end"
    # proxy decision D-15 (4): a SessionEnd hands back everything under its session_id and
    # then closes the subagent chains still open; a SubagentStop takes its own chain only.
    any_agent = not actor.agent_id
    with rl_lib.Lock(repo):  # 03 L19
        issue_ids = [r["id"] for r in rl_lib.read_rows(repo, "issues")]
        own = _chain(repo, target, actor.agent_id if not other else None)
        if own is None:
            raise rl_lib.RLError("usage", f"no sessions row for {target}", "check `rl session list`")
        if own["status"] == "closed":
            # 03 L15: a closed session is closed; 03 L222: exit 3 says what to do next.
            raise rl_lib.RLError("forbidden", f"session {target} has been closed already",
                                 "reload the role to register a new session (03 L15); "
                                 "`rl session list` shows which chains are open")
        notes: list[str] = []
        wip = {"tried": False, "branch": None, "note": None}
        # 1. hand back the orders this session holds (04 L120-127). Every row this command
        # writes for a chain carries that chain's role as actor and that chain's session id
        # (04 L118: the hook writes on the role's behalf; 05 L27-29: a session-end release
        # records the session's role).
        # PENDING(part 04 L152): who the closed version's actor is when gyb closes another
        # session is not ruled; the chain's role is used, which keeps the open and closed
        # versions of one chain in one hand.
        own_actor = rl_lib.Actor(own["role"], own["role"], target, agent_id=own.get("agent_id"))
        released, git_notes = _release_chain(repo, own, own_actor, via, any_agent, issue_ids, wip)
        notes += git_notes
        # 2. proxy decision D-15 (4): a top-level session end also closes the subagent
        # chains that are still open (a subagent killed with its parent gets no
        # SubagentStop); their orders are already in step 1's list, so these rows record
        # an empty released_handoffs (03 L190).
        sub_closed = []
        if not actor.agent_id:
            for chain in _open_chains_of(repo, target):
                if not chain.get("agent_id"):
                    continue
                sub_actor = rl_lib.Actor(chain["role"], chain["role"], target, agent_id=chain["agent_id"])
                sub_fields = _carry(chain)
                sub_fields.update({"session_id": target, "agent_id": chain["agent_id"],
                                   "ended_at": rl_lib.now_iso(), "end_reason": end_reason,
                                   "released_handoffs": []})
                rl_lib.write_row(repo, "sessions", sub_fields, sub_actor, ctx["command"],
                                 status="closed", version=chain["version"] + 1, internal=True,
                                 force=force, force_reason=force_reason)
                sub_closed.append(chain["agent_id"])
        # 3. the closed version last (03 L15; 03 L188-190).
        fields = _carry(own)
        fields.update({"session_id": target, "ended_at": rl_lib.now_iso(), "end_reason": end_reason,
                       "released_handoffs": released})
        if own.get("agent_id"):
            fields["agent_id"] = own["agent_id"]
        row = rl_lib.write_row(repo, "sessions", fields, own_actor, ctx["command"],
                               status="closed", version=own["version"] + 1, internal=True,
                               force=force, force_reason=force_reason)
    if ctx["opts"]["json"]:
        return rl_lib.result(row, "sessions", {"released_handoffs": released,
                                               "closed_subagents": sub_closed, "notes": notes})
    lines = [_line(row), f"released_handoffs: {', '.join(released) if released else '(none)'}"]
    if sub_closed:
        lines.append(f"closed subagent rows: {', '.join(sub_closed)}")
    lines += notes
    return "\n".join(lines)


# ---------------------------------------------------------------- amend

def cmd_amend(args: list[str], ctx: dict):
    """`rl session amend ID --model M` (05 L40; 03 L176; 04 L153).

    The amend version copies status and every other field from the latest version and
    changes only model; a closed session can be amended without tripping the closed-session
    refusal; the writer is gyb or that role's own session."""
    positional, opts = rl_lib.parse_args(args)
    if len(positional) != 1:
        raise rl_lib.RLError("usage", "rl session amend takes exactly one session id",
                             "usage: rl session amend ID --model M")
    unknown = set(opts) - {"model"}
    if unknown:
        # 05 L40: amend may change only model.
        raise rl_lib.RLError("usage", f"rl session amend changes only model, not {', '.join(sorted(unknown))}",
                             "usage: rl session amend ID --model M (05 L40)")
    if not opts.get("model"):
        raise rl_lib.RLError("usage", "rl session amend needs --model M", "usage: rl session amend ID --model M")
    target = positional[0]
    repo, actor, force, force_reason = rl_lib.context(ctx)
    with rl_lib.Lock(repo):  # 03 L19
        # PENDING(part 03 L176): amend names a session id, not a chain; a subagent amends
        # its own chain, everybody else the top-level one (proxy decision D-15 keys the
        # chains by (session_id, agent_id)).
        agent_id = actor.agent_id if actor.session_id == target else None
        latest = _chain(repo, target, agent_id)
        if latest is None:
            raise rl_lib.RLError("usage", f"no sessions row for {target}", "check `rl session list`")
        # 03 L176; 04 L153: gyb or that role's own session.
        own_session = actor.role_session == latest["role"] and actor.session_id == target
        if not (actor.is_gyb or own_session):
            raise rl_lib.RLError("forbidden",
                                 f"rl session amend is gyb's or {latest['role']}'s own session, "
                                 f"not a {actor.role_session} session",
                                 "ask gyb: " + rl_lib.issue_command_for_gyb(
                                     f"please run rl session amend {target} --model <model>"))
        fields = _carry(latest)
        fields.update({"session_id": target, "model": opts["model"]})
        if latest.get("agent_id"):
            fields["agent_id"] = latest["agent_id"]
        # internal=True: the who rule above replaces the ledger_writes table for this
        # command (03 L176), which no role file carries.
        row = rl_lib.write_row(repo, "sessions", fields, actor, ctx["command"], status=latest["status"],
                               version=latest["version"] + 1, internal=True,
                               force=force, force_reason=force_reason)
    if ctx["opts"]["json"]:
        return rl_lib.result(row, "sessions", {"model": row["model"]})
    return _line(row)


# ---------------------------------------------------------------- focus

def cmd_focus(args: list[str], ctx: dict):
    """`rl session focus --decision ID` (05 L40; 04 L154): reviewer notes which decision it
    is reviewing; `rl status` shows it under the live sessions."""
    positional, opts = rl_lib.parse_args(args)
    if positional:
        raise rl_lib.RLError("usage", f"rl session focus takes no positional argument: {positional[0]!r}",
                             "usage: rl session focus --decision ID")
    unknown = set(opts) - {"decision"}
    if unknown:
        raise rl_lib.RLError("usage", f"unknown flag(s) for rl session focus: {', '.join(sorted(unknown))}",
                             "usage: rl session focus --decision ID")
    decision_id = opts.get("decision")
    if not decision_id:
        raise rl_lib.RLError("usage", "rl session focus needs --decision ID", "usage: rl session focus --decision ID")
    repo, actor, force, force_reason = rl_lib.context(ctx)
    with rl_lib.Lock(repo):  # 03 L19
        # 01 L88: reference existence is an integrity check and binds gyb too.
        if not force and not any(r.get("id") == decision_id for r in rl_lib.read_decisions(repo)):
            raise rl_lib.RLError("validation", f"no decision {decision_id}",
                                 "check `rl decision list` (01 L88: references must exist)")
        latest = _chain(repo, actor.session_id, actor.agent_id)
        if latest is None:
            raise rl_lib.RLError("usage", f"no sessions row for {actor.session_id}",
                                 "load a role skill so the hook registers the session (06 L112)")
        fields = _carry(latest)
        fields.update({"session_id": actor.session_id, "focus": decision_id})  # 03 L187
        if latest.get("agent_id"):
            fields["agent_id"] = latest["agent_id"]
        row = rl_lib.write_row(repo, "sessions", fields, actor, ctx["command"],
                               status=latest["status"], version=latest["version"] + 1,
                               force=force, force_reason=force_reason)
    if ctx["opts"]["json"]:
        return rl_lib.result(row, "sessions", {"focus": decision_id})
    return _line(row)


# ---------------------------------------------------------------- queries

def cmd_show(args: list[str], ctx: dict):
    """`rl session show ID` (05 L40; 04 L155). Queries are open to everyone (03 L25)."""
    positional, opts = rl_lib.parse_args(args)
    if len(positional) != 1:
        raise rl_lib.RLError("usage", "rl session show takes exactly one session id",
                             "usage: rl session show ID")
    target = positional[0]
    repo = rl_lib.find_repo_root()
    rows = [r for r in _chains(repo).values() if r["session_id"] == target]
    if not rows:
        raise rl_lib.RLError("usage", f"no sessions row for {target}", "check `rl session list`")
    rows.sort(key=lambda r: (bool(r.get("agent_id")), r.get("agent_id") or ""))
    last_activity = _last_activity(repo, target)  # 03 L186: computed, never stored
    if ctx["opts"]["json"]:
        return {"sessions": rows, "last_activity": last_activity}
    return "\n".join([_line(r) for r in rows] + [f"last_activity: {last_activity}"])


def cmd_list(args: list[str], ctx: dict):
    """`rl session list [--alive] [--role R]` (05 L40; 04 L156). Alive means the latest
    version of the chain is open (03 L176)."""
    positional, opts = rl_lib.parse_args(args, flags=("alive",))
    if positional:
        raise rl_lib.RLError("usage", f"rl session list takes no positional argument: {positional[0]!r}",
                             "usage: rl session list [--alive] [--role R]")
    unknown = set(opts) - {"alive", "role"}
    if unknown:
        raise rl_lib.RLError("usage", f"unknown flag(s) for rl session list: {', '.join(sorted(unknown))}",
                             "usage: rl session list [--alive] [--role R]")
    role = opts.get("role")
    if role is not None and role not in rl_lib.ROLES:
        raise rl_lib.RLError("usage", f"--role must be one of {', '.join(rl_lib.ROLES)}, not {role!r}",
                             "usage: rl session list [--role R]")
    repo = rl_lib.find_repo_root()
    rows = list(_chains(repo).values())
    if opts.get("alive"):
        rows = [r for r in rows if r["status"] == "open"]
    if role:
        rows = [r for r in rows if r["role"] == role]
    rows.sort(key=lambda r: (r.get("ts", ""), r["session_id"], r.get("agent_id") or ""))
    if ctx["opts"]["json"]:
        return {"sessions": rows}
    return "\n".join(_line(r) for r in rows)
