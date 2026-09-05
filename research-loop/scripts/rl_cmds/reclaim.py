"""rl reclaim: gyb's catch-all tidy-up (04 L162-186; 05 L172-187; 07 L128).

`rl reclaim [--session-older-than H] [--handoff-older-than H] [--only ID ...]
[--skip ID ...] [--kill] [--apply]`. Who may call it: gyb (05 L94, commands.json
who=gyb); a role session is exit 3, which rl_lib.check_who_can_call gives because the
command writes and has no ledger of its own.

Without `--apply` it only lists the sessions, orders and quick lanes that are past their
threshold (04 L176). With `--apply` it acts, one rule per kind (04 L178-182):

  session                  close it with end_reason reclaim and release the in_progress
                           orders it holds (actor gyb, via=reclaim)
  in_progress launch_order release it; the process is left running for the next run to
                           adopt, and only `--kill` goes through the abort sequence
  stuck                    reassign the linked issue to the owner, status untouched
  rejected                 push it back to todo through the rejected -> todo row
  done_pending_review/todo list only, with a ready-made command

Then two more things (04 L184): print the orders waiting to be started, grouped by owner
with the command that loads that role, and run the doctor scan.

`--json` (exit_codes.json json_shapes.reclaim, 05 L123): an array of `{kind, id,
idle_hours, action}`; `kind` is session, handoff or ql.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import rl_lib
from rl_cmds import doctor
from rl_cmds.handoff import release_order

# 05 L163 / skills/research-loop/SKILL.md L36: a role is loaded by typing this.
LOAD_CMD = "/research-loop:{role}"

_TERMINAL = tuple(rl_lib.TRANSITIONS["terminal_states"])  # accepted, withdrawn (04 L47)

_SKELETON_KEYS = ("version", "status", "ts", "actor", "session_id", "schema_version",
                  "force_reason", "via")


# ---------------------------------------------------------------- private writers

def _carry(row: dict) -> dict:
    """The content fields of a row, without the skeleton (03 L11, L31-43)."""
    return {k: v for k, v in row.items() if k not in _SKELETON_KEYS}


_SHAPE_CACHE: dict = {}


def _validate_shape(ledger: str, row: dict) -> None:
    """`rl_lib.validate_shape` with the schema's `$id` dropped before the validator is
    built. jsonschema 3.2.0 joins a `#/definitions/...` fragment onto the repo-relative
    `$id` and then tries to fetch it as a URL. scripts/rl_cmds/handoff.py and
    scripts/rl_cmds/session.py carry the same private helper for the same reason; the fix
    belongs in `rl_lib.merged_schema` (see "rl_lib changes wanted")."""
    if ledger not in _SHAPE_CACHE:
        schema = dict(rl_lib.merged_schema(ledger))
        schema.pop("$id", None)
        _SHAPE_CACHE[ledger] = schema
    try:
        import jsonschema
    except ImportError:  # pragma: no cover - rl_lib's own fallback covers this case
        rl_lib.validate_shape(ledger, row)
        return
    validator = jsonschema.Draft7Validator(_SHAPE_CACHE[ledger])
    errors = sorted(validator.iter_errors(row), key=lambda e: list(e.path))
    if errors:
        err = errors[0]
        where = "/".join(str(p) for p in err.path) or "(row)"
        raise rl_lib.RLError("validation", f"{ledger} row rejected at {where}: {err.message}",
                             f"fix the field and retry (schemas/{ledger}.schema.json)")


def _check_required_by_status(ledger: str, row: dict) -> None:
    """03 L13 with one difference from `rl_lib.check_conditions`: a present empty list counts
    as present, so the closed version of a session that held no order carries
    `released_handoffs: []` (03 L190). Same private helper as scripts/rl_cmds/session.py."""
    schema = rl_lib.load_schema(ledger) or {}
    for cond in schema.get("x-conditions", []):
        if "if" not in cond or "then_required" not in cond:
            continue
        if not rl_lib._condition_holds(cond["if"], row, None):
            continue
        missing = [k for k in cond["then_required"] if row.get(k) is None or row.get(k) == ""]
        if missing:
            raise rl_lib.RLError("validation",
                                 f"{ledger} row with {cond['if']} needs {', '.join(missing)} "
                                 f"({cond.get('source', '')})", "add the missing field(s) (03 L13)")


def _append(repo: Path, ledger: str, fields: dict, actor: rl_lib.Actor, command: str, *,
            status: str, version: int, via: str | None = None) -> dict:
    """One ledger row through rl_lib's pipeline (03 L15, L27; 05 L21): writer alive, who can
    call, shape, required-by-status, append. The caller holds rl_lib.Lock (03 L19)."""
    row = rl_lib.skeleton(actor, status, version, via=via)
    row.update(fields)
    rl_lib.check_writer_alive(repo, actor)
    rl_lib.check_who_can_call(actor, command)
    _validate_shape(ledger, row)
    _check_required_by_status(ledger, row)
    rl_lib.append_row(repo, ledger, row)
    return row


# ---------------------------------------------------------------- candidate scan

def _order_status_group(order: dict) -> str:
    status = order["status"]
    if status == "in_progress":
        return "in_progress_launch" if order.get("work_type") == "launch_order" else "in_progress"
    return status


def _action_for(order: dict, kill: bool) -> str:
    """The action column of the --json rows, one sentence per 04 L178-182 rule."""
    group = _order_status_group(order)
    ho_id = order["id"]
    if group == "in_progress_launch":
        if kill:
            return ("abort the run (kill, free the GPU, host deregister, runs falls to killed) "
                    "and release it to todo")
        return "release it to todo; the launched run keeps going for the next run to adopt"
    if group == "in_progress":
        # 04 L176-182 names five dispositions and an in_progress order that is not a
        # launch_order is in none of them. Narrowest reading: list it, write nothing.
        # PENDING(part 04 L176-182).
        return f"listed only; release it by hand with `rl handoff release {ho_id} --note ...`"
    if group == "stuck":
        return "reassign the linked issue to the owner; the order stays stuck"
    if group == "rejected":
        return "push it back to todo (rejected -> todo, actor gyb, via=reclaim)"
    if group == "done_pending_review":
        return f"listed only; `rl handoff accept {ho_id}` or `rl handoff reject {ho_id} --reason ...`"
    return f"listed only; the owner starts it again, `rl handoff start {ho_id}`"


def _candidates(repo: Path, led: doctor.Ledgers, cfg: dict, session_hours: float,
                handoff_hours: float, ql_days: float, kill: bool, reference) -> list[dict]:
    """Everything past its threshold: sessions, orders and quick lanes (04 L176; 07 L128).

    A threshold is met at `>=`, so a threshold of 0 in a test sandbox catches a thing that
    was written this second (08 L71-73 give the working defaults 48 h / 72 h / 7 days)."""
    out: list[dict] = []

    for row in sorted(led.latest["sessions"].values(),
                      key=lambda r: (r["session_id"], r.get("agent_id") or "")):
        if row["status"] != "open":
            continue
        idle = doctor.hours_since(led.last_activity(row["session_id"]), reference)
        if idle is None or idle < session_hours:
            continue
        held = sorted(o["id"] for o in led.latest["handoffs"].values()
                      if o["status"] == "in_progress" and o.get("holder") == row["session_id"])
        out.append({"kind": "session", "id": row["session_id"], "idle_hours": idle,
                    "action": "close it with end_reason reclaim and release "
                              + (", ".join(held) if held else "nothing"),
                    "_agent_id": row.get("agent_id"), "_held": held})

    for ho_id, order in sorted(led.latest["handoffs"].items()):
        if order["status"] in _TERMINAL:
            continue
        idle = doctor.hours_since(order.get("ts"), reference)
        if idle is None or idle < handoff_hours:
            continue
        out.append({"kind": "handoff", "id": ho_id, "idle_hours": idle,
                    "action": _action_for(order, kill), "_group": _order_status_group(order)})

    for tag, row in sorted(led.latest["scratch"].items()):
        if row["status"] != "open":
            continue
        idle = doctor.hours_since(row.get("ts"), reference)
        if idle is None or idle < ql_days * 24.0:
            continue
        out.append({"kind": "ql", "id": tag, "idle_hours": idle,
                    "action": f"listed only; `rl ql close {tag} --merged --handoff ID` or "
                              f"`rl ql close {tag} --dropped --reason ...`"})
    return out


# ---------------------------------------------------------------- the apply rules

def _fresh_order(repo: Path, ho_id: str) -> dict | None:
    return rl_lib.latest(rl_lib.read_rows(repo, "handoffs"), "handoffs").get(ho_id)


def _adoptable_run(repo: Path, order: dict) -> dict | None:
    """04 L75 / 03 L100: the latest attempt's run row when it is launched and has no
    finished version - the run that `--kill` aborts and that a plain release leaves alone."""
    attempts = order.get("attempts") or []
    if order.get("work_type") != "launch_order" or not attempts:
        return None
    run_id = attempts[-1].get("run_id")
    versions = [r for r in rl_lib.read_rows(repo, "runs") if r.get("run_id") == run_id]
    if not versions or any(v["status"] == "finished" for v in versions):
        return None
    if not any(v["status"] == "launched" for v in versions):
        return None
    return max(versions, key=lambda v: v["version"])


def _abort(repo: Path, cfg: dict, actor: rl_lib.Actor, order: dict, notes: list) -> str | None:
    """04 L179; 12 L136: `--kill` goes through the interrupt sequence - kill the process,
    free the GPU, deregister on the host, land a killed version in runs. rl owns the last
    two: the host step is the `launcher.abort_cmd` template (08 L51; an empty template means
    the host has no such step and rl skips it, 08 L55), and the runs version is written
    here. Killing the process and freeing the card are the host command's business; rl has
    no handle on a remote process (03 L9: rl only writes ledgers)."""
    run = _adoptable_run(repo, order)
    if run is None:
        return None
    template = (cfg.get("launcher.abort_cmd") or "").strip()
    if template:
        try:
            proc = subprocess.run(template, shell=True, cwd=str(repo), capture_output=True, text=True)
            if proc.returncode != 0:
                notes.append(f"launcher.abort_cmd {template!r} exited {proc.returncode}")
            else:
                notes.append(f"launcher.abort_cmd {template!r} ran")
        except OSError as err:  # pragma: no cover - the host command is not rl's to fix
            notes.append(f"launcher.abort_cmd {template!r} could not run: {err}")
    finished_at = rl_lib.now_iso()
    started = run.get("started_at")
    actual = 0.0
    if started:
        seconds = doctor.hours_since(started, doctor.parse_ts(finished_at))
        actual = max(0.0, (seconds or 0.0) * 3600.0)
    fields = {"run_id": run["run_id"], "handoff_id": run.get("handoff_id"),
              "attempt": run.get("attempt"), "finished_at": finished_at,
              "exit_status": "killed",           # 03 L117
              "actual_seconds": actual}          # 03 L118
    _, version = rl_lib.next_version_of(repo, "runs", run["run_id"])
    rl_lib.write_row(repo, "runs", fields, actor, "reclaim", status="finished", version=version,
                     via="reclaim")
    return run["run_id"]


def _release(repo: Path, actor: rl_lib.Actor, ho_id: str, note: str, cfg: dict, kill: bool,
             notes: list) -> str | None:
    """One release version through the transition table's own writer (04 L75 / 04 L72), with
    actor gyb and via=reclaim (04 L178, L181; transitions.json release_in_progress
    side_effect release.actor_via). `handoff.release_order` also opens the orphaned notice
    to the owner (04 L195)."""
    order = _fresh_order(repo, ho_id)
    if order is None or order["status"] not in ("in_progress", "rejected"):
        return None
    if kill and order["status"] == "in_progress":
        killed = _abort(repo, cfg, actor, order, notes)
        if killed:
            notes.append(f"{ho_id}: run {killed} finished with exit_status killed")
        order = _fresh_order(repo, ho_id)
    # 04 L39: progress_note is required on in_progress -> todo and not on rejected -> todo.
    release_note = note if order["status"] == "in_progress" else None
    release_order(repo, actor, "reclaim", order, note=release_note, via="reclaim",
                  validate_who=False)
    return ho_id


def _close_session(repo: Path, actor: rl_lib.Actor, session_id: str, agent_id: str | None,
                   released: list) -> None:
    """04 L178: the session is marked reclaim and struck off. 03 L188-190: the closed version
    carries ended_at, end_reason and released_handoffs."""
    chain = rl_lib.latest(rl_lib.read_rows(repo, "sessions"), "sessions").get(
        rl_lib.session_key(session_id, agent_id))
    if chain is None or chain["status"] == "closed":
        return
    fields = _carry(chain)
    fields.update({"session_id": session_id, "ended_at": rl_lib.now_iso(),
                   "end_reason": "reclaim", "released_handoffs": released})
    if agent_id:
        fields["agent_id"] = agent_id
    _append(repo, "sessions", fields, actor, "reclaim", status="closed",
            version=chain["version"] + 1, via="reclaim")


def _reassign_issue(repo: Path, actor: rl_lib.Actor, order: dict) -> str | None:
    """04 L180: a stuck order gets its linked issue reassigned to the owner and nothing else;
    the order's own status stays stuck (transitions.json header rule stuck_untouched). 03 L92:
    reassigning is one more version with a new assignee."""
    iss_id = order.get("issue_id")
    issue = rl_lib.latest(rl_lib.read_rows(repo, "issues"), "issues").get(iss_id or "")
    if issue is None:
        return None
    owner = rl_lib.owner_of(order)
    if issue.get("assignee") == owner:
        return None
    fields = _carry(issue)
    fields["assignee"] = owner
    _append(repo, "issues", fields, actor, "reclaim", status=issue["status"],
            version=issue["version"] + 1, via="reclaim")
    return iss_id


def _apply(repo: Path, cfg: dict, actor: rl_lib.Actor, candidates: list, kill: bool,
           notes: list) -> None:
    """The five dispositions of 04 L178-182, sessions first: releasing an idle session's
    orders writes a fresh todo version whose ts is now, and that version must not then be
    read as an idle order."""
    handled: set = set()
    # 04 L178 releases an idle session's orders through the in_progress -> todo row, and
    # that row's precondition (04 L75; transitions.json release.no_kill_if_launched) says
    # it in one sentence: a launch order with a launched, unfinished run keeps its process
    # unless reclaim carries --kill, in which case the abort sequence runs first. No extra
    # "the order itself is idle" condition (reviewer ruling on 635499d, 2026-09-05).
    for cand in [c for c in candidates if c["kind"] == "session"]:
        released = []
        for ho_id in cand["_held"]:
            # 04 L178 with 04 L39: the note reclaim fills in automatically.
            done = _release(repo, actor, ho_id, f"reclaimed: holder {cand['id']} idle", cfg,
                            kill, notes)
            if done:
                released.append(done)
                handled.add(done)
        _close_session(repo, actor, cand["id"], cand.get("_agent_id"), released)
        notes.append(f"session {cand['id']} closed with end_reason reclaim; released "
                     + (", ".join(released) if released else "nothing"))

    for cand in [c for c in candidates if c["kind"] == "handoff"]:
        ho_id = cand["id"]
        if ho_id in handled:
            continue
        group = cand["_group"]
        if group == "in_progress_launch":
            if _release(repo, actor, ho_id, "reclaimed: order idle past the threshold", cfg,
                        kill, notes):
                notes.append(f"{ho_id} released to todo")
        elif group == "rejected":
            # 04 L181: a rejected order idle past the threshold goes back to todo.
            if _release(repo, actor, ho_id, None, cfg, False, notes):
                notes.append(f"{ho_id} pushed back to todo")
        elif group == "stuck":
            order = _fresh_order(repo, ho_id)
            iss_id = _reassign_issue(repo, actor, order) if order else None
            if iss_id:
                notes.append(f"{ho_id} stays stuck; {iss_id} reassigned to "
                             f"{rl_lib.owner_of(order)}")
        # in_progress work/analysis orders, done_pending_review and todo: listed only
        # (04 L182 and the PENDING above in _action_for).


# ---------------------------------------------------------------- output

def _waiting_by_owner(repo: Path) -> dict:
    """04 L184: the orders waiting to be started, grouped by owner, each with the command
    that loads that role (01 L108; skills/research-loop/SKILL.md L36)."""
    buckets: dict = {}
    for ho_id, order in sorted(rl_lib.latest(rl_lib.read_rows(repo, "handoffs"), "handoffs").items()):
        if order["status"] != "todo":
            continue
        buckets.setdefault(rl_lib.owner_of(order), []).append(ho_id)
    return buckets


def _render(candidates: list, applied: bool, notes: list, waiting: dict,
            findings: list) -> str:
    lines = []
    for kind, title in (("session", "sessions idle past the threshold"),
                        ("handoff", "orders idle past the threshold"),
                        ("ql", "quick lanes open past the threshold")):
        rows = [c for c in candidates if c["kind"] == kind]
        lines.append(f"{title} ({len(rows)})")
        for c in rows:
            lines.append(f"  {c['id']}  idle={c['idle_hours']:.1f}h  {c['action']}")
    if not applied:
        lines.append("")
        lines.append("nothing was written: add --apply to act on the list above (04 L176)")
        return "\n".join(lines)
    lines.append("")
    lines.append("applied:")
    for note in notes:
        lines.append("  " + note)
    lines.append("")
    lines.append("waiting to be started, by owner (04 L184):")
    for owner in sorted(waiting):
        load = LOAD_CMD.format(role=owner) if owner in rl_lib.ROLES else "gyb takes it in person"
        lines.append(f"  {owner}  {', '.join(waiting[owner])}  load: {load}")
    lines.append("")
    lines.append(f"doctor scan (04 L184; 05 L219): {len(findings)} finding(s)")
    lines.append(doctor.render(findings))
    return "\n".join(lines)


# ---------------------------------------------------------------- command

def cmd_main(args, ctx):
    """`rl reclaim [...]` (05 L94, L172-187; 04 L162-186)."""
    positional, opts = rl_lib.parse_args(args, multi=("only", "skip"),
                                         flags=("kill", "apply"))
    if positional:
        raise rl_lib.RLError("usage", f"rl reclaim takes no positional argument: {positional[0]!r}",
                             "usage: rl reclaim [--session-older-than H] [--handoff-older-than H] "
                             "[--only ID ...] [--skip ID ...] [--kill] [--apply]")
    known = {"session-older-than", "handoff-older-than", "only", "skip", "kill", "apply"}
    unknown = set(opts) - known
    if unknown:
        raise rl_lib.RLError("usage", f"unknown option(s): {', '.join(sorted(unknown))}",
                             "known options: " + ", ".join("--" + n for n in sorted(known)))
    repo, actor, _force, _reason = rl_lib.context(ctx)
    # 05 L94: gyb's command. A role session is exit 3 with or without --apply, so the gate
    # comes before anything is read or written.
    rl_lib.check_who_can_call(actor, ctx["command"])

    cfg = rl_lib.load_config(repo)
    session_hours = _hours(opts.get("session-older-than"), cfg["reclaim.session_idle_hours"],
                           "--session-older-than")
    handoff_hours = _hours(opts.get("handoff-older-than"), cfg["reclaim.handoff_idle_hours"],
                           "--handoff-older-than")
    ql_days = float(cfg["reclaim.ql_idle_days"])  # 08 L73; 07 L128, L137
    only = set(opts.get("only") or [])
    skip = set(opts.get("skip") or [])
    apply_it = bool(opts.get("apply"))
    kill = bool(opts.get("kill"))

    notes: list = []
    with rl_lib.Lock(repo):  # 03 L19: scan and append under one lock
        led = doctor.Ledgers(repo)
        candidates = _candidates(repo, led, cfg, session_hours, handoff_hours, ql_days, kill,
                                 doctor.now())
        # 04 L166: --only and --skip pick which of the listed things this run touches.
        if only:
            candidates = [c for c in candidates if c["id"] in only]
        if skip:
            candidates = [c for c in candidates if c["id"] not in skip]
        if apply_it:
            _apply(repo, cfg, actor, candidates, kill, notes)
        waiting = _waiting_by_owner(repo) if apply_it else {}
        findings = doctor.scan(repo, cfg) if apply_it else []

    public = [{k: c[k] for k in ("kind", "id", "idle_hours", "action")} for c in candidates]
    if ctx["opts"]["json"]:
        return public
    return _render(public, apply_it, notes, waiting, findings)


def _hours(value, default, flag: str) -> float:
    if value is None:
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        raise rl_lib.RLError("usage", f"{flag} takes a number of hours, got {value!r}")
