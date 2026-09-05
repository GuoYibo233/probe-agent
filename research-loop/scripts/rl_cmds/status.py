"""rl status: gyb's inbox (05 L149-170; 01 L116-135).

`rl status [--line L] [--group-by line|batch] [--json]`, open to everyone
(commands.json who: anyone). The first line prints how many days have passed since the
last reclaim (05 L166; 01 L120). Then the ten sections of tables/gyb-usecases.json
`status_sections`, transcribed from 05 L153-164 and 01 L122-133 word for word.

`--json` (05 L121; exit_codes.json json_shapes.status_row_min_keys): every order row
carries at least the twelve keys `id`, `work_type`, `owner`, `holder`, `holder_alive`,
`status`, `age_hours`, `line`, `decision_refs`, `batch`, `log_path`, `watch_cmd`. The
top-level container is not pinned by the parts; it is an object whose `rows` key holds
those order rows, with one further key per section that lists something other than an
order (issues, evaluations, feedback, review checklists, sessions, quick lanes, doctor
findings), because 05 L123 lets later fields be added and section 9's quick lanes have to
be readable from `--json` too. Construction convention, PENDING(part 05 L121).

Two extra keys ride on each order row (tables/README.md convention 14; 05 L123 "later
fields are only added"): `stale_holder`, true when section 7 lists the order, and
`sections`, the section numbers the order appears in.
"""

from __future__ import annotations

import time
from pathlib import Path

import rl_lib
from rl_cmds import doctor

_TERMINAL = tuple(rl_lib.TRANSITIONS["terminal_states"])  # accepted, withdrawn (04 L47)

# 05 L153-164 / 01 L122-133, transcribed through tables/gyb-usecases.json so the two
# copies stay one text.
SECTION_TITLES = {row["n"]: row["text"] for row in rl_lib.GYB_USECASES["status_sections"]}

# 01 L108: each section-5 row carries the "which role to load" command. A role is loaded by
# typing `/research-loop:` and the role name (skills/research-loop/SKILL.md L36).
LOAD_CMD = "/research-loop:{role}"

# 05 L121: the twelve keys every --json row carries.
MIN_KEYS = tuple(rl_lib.GYB_USECASES["status_json_keys"])


# ---------------------------------------------------------------- order projection

def _current_status_ts(led: doctor.Ledgers, ho_id: str, order: dict) -> str:
    """05 L168 (2026-08-17 issue 29): age_hours counts from the ts of the version that put
    the order into the status it is in now, not from when it was opened. An amend keeps the
    status, so the run of tail versions sharing the current status starts the clock."""
    versions = led.versions("handoffs", ho_id)
    start = versions[-1]
    for row in reversed(versions):
        if row["status"] != order["status"]:
            break
        start = row
    return start.get("ts")


def _run_fields(led: doctor.Ledgers, order: dict) -> tuple:
    """05 L155 / 01 L124: a launch order carries log_path and watch_cmd; both come from its
    run rows (03 L111, L113), newest version first, since a finished version does not repeat
    them."""
    if order.get("work_type") != "launch_order":
        return None, None
    attempts = order.get("attempts") or []
    run_ids = [attempts[-1]["run_id"]] if attempts and attempts[-1].get("run_id") else []
    run_ids += [r for r in led.run_ids_of_order(order["id"]) if r not in run_ids]
    for run_id in run_ids:
        for row in reversed(led.versions("runs", run_id)):
            if row.get("log_path") or row.get("watch_cmd"):
                return row.get("log_path"), row.get("watch_cmd")
    return None, None


def _root_ids(led: doctor.Ledgers, order: dict) -> list:
    """The root decision ids the order hangs under. 05 L166: `line` is the root decision id;
    sync-inbox Q43(b)(d) L313: decision_refs may span several root decisions and the order
    then shows up under every related line."""
    decisions = led.latest["decisions"]
    roots = []
    for ref in order.get("decision_refs") or []:
        row = decisions.get(ref["id"])
        root = row.get("root_id") if row else ref["id"]
        if root and root not in roots:
            roots.append(root)
    return roots


def _project(led: doctor.Ledgers, ho_id: str, order: dict, reference) -> dict:
    """One --json row: the twelve keys of 05 L121 plus the two extra ones."""
    holder = order.get("holder")
    log_path, watch_cmd = _run_fields(led, order)
    return {
        "id": ho_id,
        "work_type": order.get("work_type"),
        "owner": rl_lib.owner_of(order),                       # 04 L19: owner is from_role
        "holder": holder,
        # 05 L168: holder_alive is whether the holder session's latest sessions row is open.
        "holder_alive": bool(holder) and led.sessions_open_for(holder),
        "status": order.get("status"),
        "age_hours": doctor.hours_since(_current_status_ts(led, ho_id, order), reference),
        "line": order.get("line"),
        "decision_refs": order.get("decision_refs") or [],
        "batch": order.get("batch"),
        "log_path": log_path,
        "watch_cmd": watch_cmd,
        "stale_holder": False,                                 # filled by section 7
        "sections": [],
        "dispatch": order.get("dispatch"),
    }


# ---------------------------------------------------------------- the ten sections

def build(repo: Path, cfg: dict | None = None, line: str | None = None) -> dict:
    """Every section of `rl status`, filtered by `--line` where a line applies."""
    cfg = cfg or rl_lib.load_config(repo)
    led = doctor.Ledgers(repo)
    reference = doctor.now()
    orders = led.latest["handoffs"]

    rows: dict = {}
    for ho_id, order in sorted(orders.items()):
        if order["status"] in _TERMINAL:
            continue  # 05 L155 section 1: orders that have not reached a terminal state
        if line is not None and line not in _root_ids(led, order):
            continue  # 05 L166: --line keeps the orders of that root decision
        rows[ho_id] = _project(led, ho_id, order, reference)

    def mark(ho_id: str, section: int) -> None:
        if ho_id in rows and section not in rows[ho_id]["sections"]:
            rows[ho_id]["sections"].append(section)

    for ho_id in rows:
        mark(ho_id, 1)

    # Section 2 (05 L156; 01 L125): open issues assigned to gyb, those idle beyond
    # issues.gyb_stale_hours marked (08 L68, default 24).
    gyb_stale = float(cfg["issues.gyb_stale_hours"])
    section2 = []
    for iss_id, issue in sorted(led.latest["issues"].items()):
        if issue["status"] != "open" or issue.get("assignee") != "gyb":
            continue
        idle = doctor.hours_since(issue.get("ts"), reference)
        section2.append({"id": iss_id, "kind": issue.get("kind"), "text": issue.get("text"),
                         "idle_hours": idle,
                         "stale": idle is not None and idle >= gyb_stale})

    # Section 3 (05 L157): evaluations waiting for approval.
    section3 = [{"id": e, "kind": row.get("kind"), "name": row.get("name"),
                 "definition": row.get("definition"), "applies_to": row.get("applies_to")}
                for e, row in sorted(led.latest["evaluations"].items())
                if row["status"] == "proposed"]

    # Section 4 (05 L158): orders waiting for acceptance.
    for ho_id, row in rows.items():
        if row["status"] == "done_pending_review":
            mark(ho_id, 4)

    # Section 5 (05 L159; 01 L108): todo orders whose owner role has no open session, and
    # orders gyb takes by hand. "dispatch=manual" is read together with the todo half: the
    # section is the "waiting for gyb to start" list, so an order already in progress is not
    # waiting for anybody. Listed as undecided in the build report.
    open_roles = led.open_session_roles()
    section5 = []
    for ho_id, row in rows.items():
        if row["status"] != "todo":
            continue
        owner = row["owner"]
        no_live_owner = owner not in open_roles
        manual = row.get("dispatch") == "manual"
        if not (no_live_owner or manual):
            continue
        mark(ho_id, 5)
        section5.append({"id": ho_id, "owner": owner, "dispatch": row.get("dispatch"),
                         "reason": "owner has no live session" if no_live_owner else "dispatch=manual",
                         "load_cmd": LOAD_CMD.format(role=owner) if owner in rl_lib.ROLES else None})

    # Section 6 (05 L160; 02 L85, L93): stale orders and live orders under retired decisions.
    latest_revision: dict = {}
    for row in rl_lib.read_decisions(repo):
        if row["op"] == "confirm":
            continue  # 02 L85: staleness skips confirm versions
        if row["version"] > latest_revision.get(row["id"], 0):
            latest_revision[row["id"]] = row["version"]
    retired = {d for d, row in led.latest["decisions"].items() if row["status"] == "retired"}
    section6 = []
    for ho_id, row in rows.items():
        stale_refs, retired_refs = [], []
        for ref in row["decision_refs"]:
            newest = latest_revision.get(ref["id"])
            if newest is not None and ref["version"] < newest:
                stale_refs.append({"decision": ref["id"], "cited": ref["version"], "latest": newest})
            if ref["id"] in retired:
                retired_refs.append(ref["id"])
        if not stale_refs and not retired_refs:
            continue
        mark(ho_id, 6)
        section6.append({"id": ho_id, "holder": row["holder"], "stale_refs": stale_refs,
                         "retired_decisions": retired_refs})

    # Section 7 (05 L161, L168): in_progress orders whose holder session has written nothing
    # for longer than status.stale_holder_minutes (08 L70, default 30). last_activity is not
    # stored: it is the biggest ts over the nine ledgers for that session_id.
    stale_minutes = float(cfg["status.stale_holder_minutes"])
    section7 = []
    for ho_id, row in rows.items():
        if row["status"] != "in_progress" or not row["holder"]:
            continue
        idle = doctor.hours_since(led.last_activity(row["holder"]), reference)
        silent_minutes = None if idle is None else idle * 60.0
        if silent_minutes is not None and silent_minutes < stale_minutes:
            continue
        row["stale_holder"] = True
        mark(ho_id, 7)
        section7.append({"id": ho_id, "holder": row["holder"], "silent_minutes": silent_minutes})

    # Section 8 (05 L162): feedback waiting for a verdict.
    section8 = [{"id": f, "target": row.get("target"), "text": row.get("text")}
                for f, row in sorted(led.latest["feedback"].items())
                if row["status"] == "proposed"]

    # Section 9 (05 L163; 07 L126): review/ checklists of the last status.review_recent_days
    # (08 L76, default 7), live sessions with their focus, and quick lanes that are not
    # closed. A quick lane belongs to no line and is listed as its own heap under
    # --group-by line.
    recent_days = float(cfg["status.review_recent_days"])
    review = []
    review_dir = repo / "review"
    if review_dir.is_dir():
        for path in sorted(p for p in review_dir.rglob("*") if p.is_file()):
            age_days = (time.time() - path.stat().st_mtime) / 86400.0
            if age_days <= recent_days:
                review.append({"path": str(path.relative_to(repo)), "age_days": age_days})
    sessions = [{"session_id": row["session_id"], "agent_id": row.get("agent_id"),
                 "role": row.get("role"), "model": row.get("model"), "focus": row.get("focus")}
                for row in sorted(led.latest["sessions"].values(),
                                  key=lambda r: (r["session_id"], r.get("agent_id") or ""))
                if row["status"] == "open"]
    quick_lanes = [{"ql_tag": tag, "role": row.get("role"), "status": row["status"],
                    "note": row.get("note")}
                   for tag, row in sorted(led.latest["scratch"].items())
                   if row["status"] == "open"]

    # Section 10 (05 L164, L219): what the doctor scan found and nobody fixed. The scan runs
    # in this process, over the same ledger snapshot.
    findings = doctor.scan(repo, cfg, ledgers=led)

    return {
        "days_since_last_reclaim": _days_since_last_reclaim(led, reference),
        "rows": list(rows.values()),
        "issues_to_gyb": section2,
        "evaluations_proposed": section3,
        "orders_waiting_to_start": section5,
        "stale_or_retired": section6,
        "silent_holders": section7,
        "feedback_proposed": section8,
        "review_checklists": review,
        "open_sessions": sessions,
        "quick_lanes": quick_lanes,
        "doctor": findings,
    }


def _days_since_last_reclaim(led: doctor.Ledgers, reference) -> float | None:
    """05 L166; 01 L120: the first line is how many days it has been since the last reclaim.
    A reclaim leaves rows marked `via=reclaim` (04 L178, L181; _skeleton.schema.json), so the
    last reclaim is the newest such ts; never run is None."""
    best = None
    for rows in led.all.values():
        for row in rows:
            if row.get("via") == "reclaim" and (best is None or row.get("ts", "") > best):
                best = row.get("ts")
    hours = doctor.hours_since(best, reference)
    return None if hours is None else hours / 24.0


# ---------------------------------------------------------------- text rendering

def _order_line(row: dict) -> str:
    bits = [row["id"], str(row["work_type"]), f"owner={row['owner']}",
            f"holder={row['holder'] or '-'}",
            f"holder_alive={'yes' if row['holder_alive'] else 'no'}", str(row["status"])]
    if row["age_hours"] is not None:
        bits.append(f"age={row['age_hours']:.1f}h")
    bits.append(f"line={row['line'] or '-'}")
    if row.get("batch"):
        bits.append(f"batch={row['batch']}")
    if row["log_path"]:
        bits.append(f"log_path={row['log_path']}")
    if row["watch_cmd"]:
        bits.append(f"watch_cmd={row['watch_cmd']}")
    return "  ".join(bits)


def _grouped(rows: list, group_by: str | None) -> list:
    """05 L166: the whole listing can be grouped by line or by batch."""
    if not group_by:
        return [(None, rows)]
    key = "line" if group_by == "line" else "batch"
    buckets: dict = {}
    for row in rows:
        buckets.setdefault(row.get(key) or "(none)", []).append(row)
    return [(f"{group_by} {name}", buckets[name]) for name in sorted(buckets)]


def _section_block(number: int, rows: list, render_row, group_by: str | None = None) -> list:
    lines = [f"{number}. {SECTION_TITLES[number]} ({len(rows)})"]
    for header, bucket in _grouped(rows, group_by):
        indent = "  "
        if header is not None:
            lines.append(f"  [{header}]")
            indent = "    "
        for row in bucket:
            lines.append(indent + render_row(row))
    return lines


def _issue_line(r: dict) -> str:
    age = "?" if r["idle_hours"] is None else format(r["idle_hours"], ".1f")
    return f"{r['id']}  {r['kind']}  age={age}h{'  STALE' if r['stale'] else ''}: {r['text']}"


def _silent_line(r: dict) -> str:
    silent = "?" if r["silent_minutes"] is None else format(r["silent_minutes"], ".1f")
    return f"{r['id']}  holder={r['holder']}  silent {silent} min"


def _stale_line(r: dict) -> str:
    bits = [f"{r['id']}", f"holder={r['holder'] or '-'}"]
    for s in r["stale_refs"]:
        bits.append(f"cites {s['decision']} v{s['cited']}, latest v{s['latest']}")
    if r["retired_decisions"]:
        bits.append("under retired " + ", ".join(r["retired_decisions"]))
    return "  ".join(bits)


def _waiting_line(r: dict) -> str:
    load = r["load_cmd"] or "gyb takes it in person"
    return f"{r['id']}  owner={r['owner']}  {r['reason']}  load: {load}"


def render(payload: dict, group_by: str | None = None) -> str:
    days = payload["days_since_last_reclaim"]
    first = ("days since the last reclaim: never, 0 rows carry via=reclaim"
             if days is None else f"days since the last reclaim: {days:.1f}")
    lines = [first, ""]
    rows = payload["rows"]

    lines += _section_block(1, rows, _order_line, group_by)
    lines += _section_block(2, payload["issues_to_gyb"], _issue_line)
    lines += _section_block(3, payload["evaluations_proposed"],
                            lambda r: f"{r['id']}  {r['kind']}  {r['name']}: {r['definition']}")
    lines += _section_block(4, [r for r in rows if 4 in r["sections"]], _order_line, group_by)
    lines += _section_block(5, payload["orders_waiting_to_start"], _waiting_line)
    lines += _section_block(6, payload["stale_or_retired"], _stale_line)
    lines += _section_block(7, payload["silent_holders"], _silent_line)
    lines += _section_block(8, payload["feedback_proposed"],
                            lambda r: f"{r['id']}  {r['target']}: {r['text']}")
    lines.append(f"9. {SECTION_TITLES[9]}")
    for row in payload["review_checklists"]:
        lines.append(f"  review  {row['path']}  {row['age_days']:.1f} days old")
    for row in payload["open_sessions"]:
        bits = [row["session_id"]]
        if row["agent_id"]:
            bits.append(f"agent={row['agent_id']}")
        bits += [str(row["role"]), f"model={row['model']}"]
        if row["focus"]:
            bits.append(f"focus={row['focus']}")
        lines.append("  session  " + "  ".join(bits))
    # 07 L126: quick lanes belong to no line; under --group-by line they are a heap of
    # their own, so they are always printed under their own heading.
    lines.append("  quick lanes not closed (no line)")
    for row in payload["quick_lanes"]:
        lines.append(f"    {row['ql_tag']}  {row['role']}  {row['status']}")
    lines.append(f"10. {SECTION_TITLES[10]} ({len(payload['doctor'])})")
    for finding in payload["doctor"]:
        lines.append("  " + doctor.render([finding]))
    return "\n".join(lines)


def cmd_main(args, ctx):
    """`rl status [--line L] [--group-by line|batch] [--json]` (05 L93, L149-170)."""
    positional, opts = rl_lib.parse_args(args)
    if positional:
        raise rl_lib.RLError("usage", f"rl status takes no positional argument: {positional[0]!r}",
                             "usage: rl status [--line L] [--group-by line|batch] [--json]")
    unknown = set(opts) - {"line", "group-by"}
    if unknown:
        raise rl_lib.RLError("usage", f"unknown option(s): {', '.join(sorted(unknown))}",
                             "usage: rl status [--line L] [--group-by line|batch] [--json]")
    group_by = opts.get("group-by")
    if group_by is not None and group_by not in ("line", "batch"):
        raise rl_lib.RLError("usage", f"--group-by takes line or batch, not {group_by!r}")
    repo, _actor, _force, _reason = rl_lib.context(ctx)
    payload = build(repo, line=opts.get("line"))
    if ctx["opts"]["json"]:
        return payload
    return render(payload, group_by)
