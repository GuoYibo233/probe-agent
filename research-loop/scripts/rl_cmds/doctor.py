"""rl doctor: the ledger scan, its acks, and the shared scan other commands reuse.

Sources transcribed here: 05 L189-221 (the scan table, the ack rules, "roles look only"),
sync-inbox Q35(a) L194 (item 20, stale session state files) and Q43(a) L313 with Q35(g)
L195 (item 16 deleted, its number left as a gap and never reused), 08 L68-77 (the
thresholds), ledgers.json plain_files (`loop/.doctor-acks.jsonl` is a plain file, created
by the first `--ack`).

`scan(repo, cfg)` is the whole nineteen-plus-one-item pass; `rl status` section 10
(05 L164) and `rl reclaim --apply` (04 L184) call it in-process, so the finding shape is
one thing, defined once.

Finding shape (exit_codes.json json_shapes.doctor, 05 L123): `{item, ids, fix_cmd,
push_to}`. One finding per (item, id) pair, because an ack is per item and id (05 L217)
and a finding that mixed several ids could not be acked away one at a time; `note` is an
extra key, and 05 L123 lets later fields be added.
"""

from __future__ import annotations

import datetime as _dt
import json
import time
from pathlib import Path

import rl_lib

# ledgers.json plain_files: not one of the nine ledgers; created by the first `--ack`
# (05 L217; 08 L18).
ACKS_NAME = ".doctor-acks.jsonl"

# 03 L92 / 04 L190: the three notification kinds are notices, not problems.
NOTIFICATION_KINDS = ("withdrawn", "orphaned", "fyi")

# 05 L198: item 4 scans these three issue kinds.
BLOCKED_ISSUE_KINDS = ("cannot", "failed", "denied")

_TERMINAL = tuple(rl_lib.TRANSITIONS["terminal_states"])  # accepted, withdrawn (04 L47)

# sync-inbox Q35(a) L194: "超过一天没动" - a state file untouched for more than one day.
# PENDING(part 08 L57): the threshold table has no key for it, so it is not configurable.
STATE_FILE_STALE_HOURS = 24.0

# hooks/rl_hook.py L318, L347, L402-408: besides `<sid>.json` the hook leaves `<sid>.model`
# (the model cache) and `<sid>.end.log` (the background delete's log) behind.
# PENDING(sync-inbox Q35(a) L194): the ruling names only the state file; the two side files
# are read as part of the same leftover.
STATE_SIDE_SUFFIXES = (".model", ".end.log")


# ---------------------------------------------------------------- time

def parse_ts(text: str) -> _dt.datetime | None:
    """Read a row timestamp. rl writes %Y-%m-%dT%H:%M:%S%z (rl_lib.now_iso); rows seeded by
    hand may spell the offset +00:00 instead."""
    if not text:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
        try:
            return _dt.datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return _dt.datetime.fromisoformat(text)
    except ValueError:
        return None


def now() -> _dt.datetime:
    return parse_ts(rl_lib.now_iso())


def hours_since(ts: str | None, reference: _dt.datetime | None = None) -> float | None:
    """Hours between a row's ts and now. None when the timestamp cannot be read."""
    moment = parse_ts(ts) if isinstance(ts, str) else ts
    if moment is None:
        return None
    ref = reference or now()
    if (moment.tzinfo is None) != (ref.tzinfo is None):
        moment, ref = moment.replace(tzinfo=None), ref.replace(tzinfo=None)
    return (ref - moment).total_seconds() / 3600.0


# ---------------------------------------------------------------- acks

def acks_path(repo: Path) -> Path:
    return rl_lib.loop_dir(repo) / ACKS_NAME


def read_acks(repo: Path) -> list[dict]:
    """Every ack and unack line in file order (05 L217: `--unack` appends one more line)."""
    path = acks_path(repo)
    if not path.is_file():
        return []
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def acked_pairs(repo: Path) -> set:
    """05 L217: an acked (item, id) is never reported again, until `--unack` takes it back.
    The last line for a pair wins, so ack, unack, ack again all behave."""
    state: dict = {}
    for row in read_acks(repo):
        state[(row.get("item"), row.get("id"))] = row.get("op", "ack")
    return {pair for pair, op in state.items() if op == "ack"}


def _append_ack(repo: Path, item: int, ident: str, actor: rl_lib.Actor, op: str) -> dict:
    """05 L217: one line with item, id, ts, actor, session_id; `op` tells an unack line from
    an ack line (the parts do not name that field, so it is a construction convention,
    tables/README.md; PENDING(part 05 L217))."""
    row = {"item": item, "id": ident, "ts": rl_lib.now_iso(), "actor": actor.actor,
           "session_id": actor.session_id, "op": op}
    path = acks_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return row


# ---------------------------------------------------------------- ledger snapshot

class Ledgers:
    """One read of every ledger, so a scan touches each file once (03 L11: a query takes
    the latest version per key; the history stays available for the items that need it)."""

    def __init__(self, repo: Path):
        self.repo = repo
        self.all: dict = {}
        self.latest: dict = {}
        for name in rl_lib.LEDGER_NAMES:
            if name == "decisions":
                rows = rl_lib.read_decisions(repo)
            elif rl_lib.LEDGERS[name].get("schema") is None:
                rows = []  # grants has no schema and no commands (proxy decision D-01)
            else:
                rows = rl_lib.read_rows(repo, name)
            self.all[name] = rows
            self.latest[name] = rl_lib.latest(rows, name)

    def versions(self, ledger: str, key_value: str) -> list[dict]:
        return sorted([r for r in self.all[ledger] if rl_lib.row_key(ledger, r) == key_value],
                      key=lambda r: r["version"])

    def version_where(self, ledger: str, key_value: str, status: str) -> dict | None:
        """The newest version of one key that carries this status (05 L197, L199, L202: the
        pusher is the actor of the version that set the status)."""
        rows = [r for r in self.versions(ledger, key_value) if r.get("status") == status]
        return rows[-1] if rows else None

    def opener(self, ledger: str, key_value: str) -> str | None:
        """The actor of version 1 (05 L196, L198, L205, L206: "the role that opened it")."""
        rows = self.versions(ledger, key_value)
        return rows[0]["actor"] if rows else None

    def open_session_roles(self) -> set:
        return {r.get("role") for r in self.latest["sessions"].values() if r["status"] == "open"}

    def sessions_open_for(self, session_id: str) -> bool:
        return any(r["session_id"] == session_id and r["status"] == "open"
                   for r in self.latest["sessions"].values())

    def last_activity(self, session_id: str) -> str | None:
        """03 L186; 05 L168: not stored; the biggest ts over the nine ledgers for this
        session_id, the sessions ledger included."""
        best = None
        for rows in self.all.values():
            for row in rows:
                if row.get("session_id") == session_id and (best is None or row.get("ts", "") > best):
                    best = row.get("ts")
        return best

    def run_ids_of_order(self, ho_id: str) -> list[str]:
        return sorted({r["run_id"] for r in self.all["runs"] if r.get("handoff_id") == ho_id})


def role_or_gyb(role: str | None, ledgers: Ledgers) -> str:
    """The "…；无活会话则 gyb" half of the push-to column (05 L197, L200, L201, L207)."""
    if role in rl_lib.ROLES and role in ledgers.open_session_roles():
        return role
    return "gyb"


# ---------------------------------------------------------------- the scan

def scan(repo: Path, cfg: dict | None = None, ledgers: Ledgers | None = None) -> list[dict]:
    """The twenty scan items of 05 L193-213 plus sync-inbox Q35(a); acked pairs are
    dropped (05 L217). Returns the finding list, sorted by item then id."""
    cfg = cfg or rl_lib.load_config(repo)
    led = ledgers or Ledgers(repo)
    reference = now()
    out: list[dict] = []

    def add(item: int, ident: str, fix_cmd: str, push_to: str, note: str = "") -> None:
        out.append({"item": item, "ids": [ident], "fix_cmd": fix_cmd, "push_to": push_to,
                    "note": note})

    _item1_duplicate_ids(led, add)
    _item2_dangling_refs(repo, led, add)
    _item3_stuck_without_issue(led, add)
    _item4_blocked_issue_without_order(led, add)
    _item5_missing_deliverables(repo, led, add)
    _item6_runs_handoff_id(led, add)
    _item7_launched_never_finished(led, cfg, reference, add)
    _item8_runs_on_withdrawn_orders(led, add)
    _item9_accepted_quick_lane_without_launch(led, add)
    _item10_approved_metric_key_missing(led, add)
    _item11_answered_not_closed(led, cfg, reference, add)
    _item12_todo_with_open_issue(led, add)
    _item13_holder_not_in_open_session(led, add)
    _item14_open_session_gone_quiet(led, cfg, reference, add)
    _item15_retired_decision_live_orders(led, add)
    # item 16 is a gap on purpose: "decision sources point at notes/ but grants has no
    # read:notes" was deleted with the permission mechanism (sync-inbox Q43(a) L313), and
    # Q35(g) L195 rules that a deleted item's number is left empty and never reused.
    _item17_accepted_feedback_without_applied_to(led, add)
    _item18_host_runs_ledger(repo, cfg, led, add)
    _item19_session_model_unknown(led, add)
    _item20_stale_state_files(repo, led, reference, add)

    acked = acked_pairs(repo)
    out = [f for f in out if (f["item"], f["ids"][0]) not in acked]
    out.sort(key=lambda f: (f["item"], f["ids"][0]))
    return out


def _item1_duplicate_ids(led: Ledgers, add) -> None:
    """05 L195 item 1: clashing numbers, report only; list each clashing row's ts, actor and
    session_id. Two rows of one key with the same version are the clash 03 L21 warns about
    (an ordinary new version is a bigger number, not a repeat)."""
    for ledger, rows in led.all.items():
        seen: dict = {}
        for row in rows:
            seen.setdefault((rl_lib.row_key(ledger, row), row["version"]), []).append(row)
        reported = set()
        for (key, version), group in sorted(seen.items()):
            if len(group) > 1 and key not in reported:
                reported.add(key)
                where = "; ".join(f"{r.get('ts')} {r.get('actor')} {r.get('session_id')}"
                                  for r in group)
                add(1, key, "", "gyb",
                    f"{ledger}: {len(group)} rows share version {version} - {where}")


def _item2_dangling_refs(repo: Path, led: Ledgers, add) -> None:
    """05 L196 item 2: dangling references in handoffs (parent_id, decision_refs,
    evaluation_refs, issue_id), issues (handoff_id), evaluations (uses) and decisions
    (sources, merged_from). runs' handoff_id belongs to item 6 and is not repeated here."""
    handoffs, issues = led.latest["handoffs"], led.latest["issues"]
    decisions, evaluations = led.latest["decisions"], led.latest["evaluations"]
    runs = led.latest["runs"]

    for ho_id, order in sorted(handoffs.items()):
        bad = []
        if order.get("parent_id") and order["parent_id"] not in handoffs:
            bad.append(f"parent_id -> {order['parent_id']}")
        for ref in order.get("decision_refs") or []:
            if ref["id"] not in decisions:
                bad.append(f"decision_refs -> {ref['id']}")
        for ref in order.get("evaluation_refs") or []:
            if ref["id"] not in evaluations:
                bad.append(f"evaluation_refs -> {ref['id']}")
        if order.get("issue_id") and order["issue_id"] not in issues:
            bad.append(f"issue_id -> {order['issue_id']}")
        if bad:
            # 05 L196: a handoffs row is repointed with `rl handoff amend`; the pusher is the
            # order's owner.
            add(2, ho_id, f"rl handoff amend {ho_id} --decision ID@V (or --eval ID@V)",
                role_or_gyb(rl_lib.owner_of(order), led), "; ".join(bad))

    for iss_id, issue in sorted(issues.items()):
        if issue.get("handoff_id") and issue["handoff_id"] not in handoffs:
            # 05 L196: other ledgers are report-only; the pusher is the role that opened it.
            add(2, iss_id, "", role_or_gyb(led.opener("issues", iss_id), led),
                f"issues handoff_id -> {issue['handoff_id']}")

    for eval_id, row in sorted(evaluations.items()):
        missing = [u for u in row.get("uses") or [] if u not in evaluations]
        if missing:
            add(2, eval_id, "", role_or_gyb(row.get("actor"), led),
                "evaluations uses -> " + ", ".join(missing))

    for dec_id, row in sorted(decisions.items()):
        bad = []
        for src in row.get("sources") or []:
            kind = src.get("kind")
            if kind == "decision" and src.get("id") not in decisions:
                bad.append(f"sources -> {src.get('id')}")
            elif kind == "run" and src.get("run_id") not in runs:
                bad.append(f"sources -> {src.get('run_id')}")
            elif kind == "file" and not (repo / str(src.get("path"))).exists():
                bad.append(f"sources -> {src.get('path')}")
        for other in row.get("merged_from") or []:
            if other not in decisions:
                bad.append(f"merged_from -> {other}")
        if bad:
            add(2, dec_id, "", role_or_gyb(row.get("actor"), led), "; ".join(bad))


def _item3_stuck_without_issue(led: Ledgers, add) -> None:
    """05 L197 item 3: a stuck order with no issue linking back (the stuck precondition of
    04 L66: issue_id names an issue whose handoff_id points back at this order). Fix
    `rl issue link ID --handoff ID`; pushed to the role that wrote the stuck version, or the
    owner when that role has no live session."""
    issues = led.latest["issues"]
    for ho_id, order in sorted(led.latest["handoffs"].items()):
        if order["status"] != "stuck":
            continue
        issue = issues.get(order.get("issue_id") or "")
        if issue is not None and issue.get("handoff_id") == ho_id:
            continue
        stuck_version = led.version_where("handoffs", ho_id, "stuck")
        setter = stuck_version["actor"] if stuck_version else None
        # PENDING(issue 50): 05 L197 pushes to "the role that turned the order stuck"; for a
        # launch order that role is run, which has no way to link an issue it did not open,
        # and the parts do not say who takes it instead. The column is transcribed as
        # written and the owner fallback below is the only escape.
        push_to = setter if setter in rl_lib.ROLES and setter in led.open_session_roles() \
            else role_or_gyb(rl_lib.owner_of(order), led)
        named = order.get("issue_id") or "ISS_ID"
        add(3, ho_id, f"rl issue link {named} --handoff {ho_id}", push_to,
            f"stuck since v{stuck_version['version'] if stuck_version else '?'}; no issue links "
            f"back (open one first with `rl issue open --handoff {ho_id}`)")


def _item4_blocked_issue_without_order(led: Ledgers, add) -> None:
    """05 L198 item 4: an open cannot/failed/denied issue that no order points at."""
    pointed = {o.get("issue_id") for o in led.latest["handoffs"].values() if o.get("issue_id")}
    for iss_id, issue in sorted(led.latest["issues"].items()):
        if issue["status"] != "open" or issue.get("kind") not in BLOCKED_ISSUE_KINDS:
            continue
        if iss_id in pointed:
            continue
        add(4, iss_id,
            f"rl handoff stuck ID --issue {iss_id} (the order really is stuck) "
            f"or rl issue close {iss_id} (the order has moved on)",
            role_or_gyb(led.opener("issues", iss_id), led),
            f"kind {issue.get('kind')}, no order points back")


def _item5_missing_deliverables(repo: Path, led: Ledgers, add) -> None:
    """05 L199 item 5: a done_pending_review order whose deliverable paths do not exist
    (04 L35-37: report_paths, code_paths, output_paths). Pushed to the role that delivered,
    i.e. the actor of the done version."""
    flag = {"method": "--report-method", "detail": "--report-detail", "code": "--code-path",
            "notebook": "--notebook", "figure": "--figure"}
    for ho_id, order in sorted(led.latest["handoffs"].items()):
        if order["status"] != "done_pending_review":
            continue
        wanted = []
        reports = order.get("report_paths") or {}
        wanted.append((flag["method"], reports.get("method")))
        wanted.append((flag["detail"], reports.get("detail")))
        for path in order.get("code_paths") or []:
            wanted.append((flag["code"], path))
        outputs = order.get("output_paths") or {}
        wanted.append((flag["notebook"], outputs.get("notebook")))
        for path in outputs.get("figures") or []:
            wanted.append((flag["figure"], path))
        missing = [(f, p) for f, p in wanted if p and not (repo / str(p)).exists()]
        if not missing:
            continue
        done_version = led.version_where("handoffs", ho_id, "done_pending_review")
        deliverer = done_version["actor"] if done_version else None
        add(5, ho_id,
            "rl handoff amend " + ho_id + " " + " ".join(f"{f} P" for f, _ in missing),
            role_or_gyb(deliverer, led),
            "missing: " + ", ".join(p for _, p in missing))


def _item6_runs_handoff_id(led: Ledgers, add) -> None:
    """05 L200 item 6: a runs row whose handoff_id is empty, dangling or not a launch_order.
    Fix `rl run relink RUN_ID --handoff ID`; a run that never belonged to an order (gyb ran
    it by hand) is acked away with `rl doctor --ack 6 RUN_ID`."""
    handoffs = led.latest["handoffs"]
    for run_id, row in sorted(led.latest["runs"].items()):
        ho_id = row.get("handoff_id")
        order = handoffs.get(ho_id or "")
        if order is not None and order.get("work_type") == "launch_order":
            continue
        if not ho_id:
            why = "handoff_id is empty"
        elif order is None:
            why = f"handoff_id -> {ho_id} is not in the handoffs ledger"
        else:
            why = f"handoff_id -> {ho_id} is a {order.get('work_type')}, not a launch_order"
        add(6, run_id,
            f"rl run relink {run_id} --handoff ID (or rl doctor --ack 6 {run_id} when this run "
            f"belongs to no order)",
            role_or_gyb("run", led), why)


def _item7_launched_never_finished(led: Ledgers, cfg: dict, reference, add) -> None:
    """05 L201, L215 item 7: a run with a launched version and no finished version, older
    than reclaim.handoff_idle_hours (08 L72; the item takes that key rather than adding one
    of its own)."""
    threshold = float(cfg["reclaim.handoff_idle_hours"])
    for run_id in sorted(led.latest["runs"]):
        versions = led.versions("runs", run_id)
        if any(v["status"] == "finished" for v in versions):
            continue
        launched = [v for v in versions if v["status"] == "launched"]
        if not launched:
            continue
        idle = hours_since(launched[-1].get("ts"), reference)
        if idle is None or idle < threshold:
            continue
        add(7, run_id,
            f"rl handoff show {launched[-1].get('handoff_id')} for its watch_cmd and take over, "
            f"or rl run finish {run_id} --exit failed|killed",
            role_or_gyb("run", led),
            f"launched {idle:.1f}h ago, no finished version (threshold {threshold:g}h)")


def _item8_runs_on_withdrawn_orders(led: Ledgers, add) -> None:
    """05 L202 item 8: a run on a withdrawn order with no finished version. Pushed to the
    role that withdrew the order (the actor of the withdrawn version)."""
    handoffs = led.latest["handoffs"]
    for run_id in sorted(led.latest["runs"]):
        versions = led.versions("runs", run_id)
        if any(v["status"] == "finished" for v in versions):
            continue
        ho_id = versions[-1].get("handoff_id")
        order = handoffs.get(ho_id or "")
        if order is None or order["status"] != "withdrawn":
            continue
        withdrawn = led.version_where("handoffs", ho_id, "withdrawn")
        add(8, run_id,
            f"kill the process with the order's watch_cmd, then rl run finish {run_id} --exit killed",
            role_or_gyb(withdrawn["actor"] if withdrawn else None, led),
            f"order {ho_id} was withdrawn while this run was still open")


def _item9_accepted_quick_lane_without_launch(led: Ledgers, add) -> None:
    """05 L203 item 9 (07 L120, L130): an accepted quick-lane work order with no launch
    order under it. A quick lane that really needs no formal rerun is acked away."""
    handoffs = led.latest["handoffs"]
    parents = {o.get("parent_id") for o in handoffs.values()
               if o.get("work_type") == "launch_order" and o.get("parent_id")}
    for ho_id, order in sorted(handoffs.items()):
        if not order.get("quick_lane") or order["status"] != "accepted":
            continue
        if order.get("work_type") == "launch_order" or ho_id in parents:
            continue
        add(9, ho_id,
            f"rl handoff open --type launch_order --parent {ho_id} ... (or rl doctor --ack 9 {ho_id} "
            f"when no formal rerun is needed)",
            role_or_gyb(rl_lib.owner_of(order), led), "accepted quick-lane order, no launch order")


def _item10_approved_metric_key_missing(led: Ledgers, add) -> None:
    """05 L204 item 10: an approved evaluation whose metrics_key appears in no runs row.
    Report only: the evaluation id, the key, and the closest existing key name."""
    known: set = set()
    for row in led.all["runs"]:
        known.update((row.get("metrics") or {}).keys())
    for eval_id, row in sorted(led.latest["evaluations"].items()):
        key = row.get("metrics_key")
        if row["status"] != "approved" or not key or key in known:
            continue
        closest = min(known, key=lambda k: (abs(len(k) - len(key)), k), default=None)
        tail = f"closest existing key: {closest!r}" if closest else "the runs ledger holds no metrics"
        add(10, eval_id, "", "analysis", f"metrics_key {key!r} is in no runs row; {tail}")


def _item11_answered_not_closed(led: Ledgers, cfg: dict, reference, add) -> None:
    """05 L205, L215 item 11: an answered issue not closed for issues.answered_stale_days
    (08 L69, default 3)."""
    threshold = float(cfg["issues.answered_stale_days"]) * 24.0
    for iss_id, issue in sorted(led.latest["issues"].items()):
        if issue["status"] != "answered":
            continue
        idle = hours_since(issue.get("ts"), reference)
        if idle is None or idle < threshold:
            continue
        add(11, iss_id,
            f"rl issue close {iss_id} (if the answer did not help, close it and open a new issue "
            f"quoting {iss_id})",
            role_or_gyb(led.opener("issues", iss_id), led),
            f"answered {idle / 24.0:.1f} days ago and still open")


def _item12_todo_with_open_issue(led: Ledgers, add) -> None:
    """05 L206 item 12: an order back at todo whose linked issue is still open.

    The three notification kinds are left out: 04 L190 says withdrawn, orphaned and fyi are
    notices, "not problems", and every release writes one, so counting them would report
    every order the session-end hook or reclaim ever handed back. Listed as undecided in
    the build report."""
    for ho_id, order in sorted(led.latest["handoffs"].items()):
        if order["status"] != "todo":
            continue
        linked = [i for i in led.latest["issues"].values()
                  if i.get("handoff_id") == ho_id and i["status"] == "open"
                  and i.get("kind") not in NOTIFICATION_KINDS]
        if not linked:
            continue
        add(12, ho_id, "rl issue close " + " ".join(sorted(i["id"] for i in linked)),
            role_or_gyb(led.opener("issues", sorted(i["id"] for i in linked)[0]), led),
            "back at todo with " + ", ".join(sorted(i["id"] for i in linked)) + " still open")


def _item13_holder_not_in_open_session(led: Ledgers, add) -> None:
    """05 L207 item 13: an in_progress order whose holder is in no open session."""
    for ho_id, order in sorted(led.latest["handoffs"].items()):
        if order["status"] != "in_progress":
            continue
        holder = order.get("holder")
        if holder and led.sessions_open_for(holder):
            continue
        add(13, ho_id,
            f"rl handoff release {ho_id} --note ... or rl reclaim --only {ho_id} --apply",
            role_or_gyb(rl_lib.owner_of(order), led),
            f"holder {holder} has no open session")


def _item14_open_session_gone_quiet(led: Ledgers, cfg: dict, reference, add) -> None:
    """05 L208 item 14: a session with no closed version that has written nothing past the
    threshold (reclaim.session_idle_hours, 08 L71)."""
    threshold = float(cfg["reclaim.session_idle_hours"])
    for row in sorted(led.latest["sessions"].values(), key=lambda r: r["session_id"]):
        if row["status"] != "open":
            continue
        idle = hours_since(led.last_activity(row["session_id"]), reference)
        if idle is None or idle < threshold:
            continue
        add(14, row["session_id"],
            f"rl session end --session {row['session_id']} --reason manual", "gyb",
            f"{row.get('role')} session, silent {idle:.1f}h (threshold {threshold:g}h)")


def _item15_retired_decision_live_orders(led: Ledgers, add) -> None:
    """05 L209 item 15 (02 L93): a retired decision with orders still live under it."""
    retired = {d for d, row in led.latest["decisions"].items() if row["status"] == "retired"}
    for ho_id, order in sorted(led.latest["handoffs"].items()):
        if order["status"] in _TERMINAL:
            continue
        cited = sorted({r["id"] for r in order.get("decision_refs") or []} & retired)
        if not cited:
            continue
        add(15, ho_id, f"rl handoff withdraw {ho_id} --reason ... --cascade",
            role_or_gyb(rl_lib.owner_of(order), led),
            "cites retired " + ", ".join(cited))


def _item17_accepted_feedback_without_applied_to(led: Ledgers, add) -> None:
    """05 L211 item 17: accepted feedback whose applied_to is empty."""
    for fb_id, row in sorted(led.latest["feedback"].items()):
        if row["status"] != "accepted" or row.get("applied_to"):
            continue
        add(17, fb_id, f"rl feedback accept {fb_id} --applied-to FILE ...", "gyb",
            "accepted with an empty applied_to")


def _item18_host_runs_ledger(repo: Path, cfg: dict, led: Ledgers, add) -> None:
    """05 L212 item 18: run ids that loop/runs.jsonl and the host runs ledger disagree on.
    The host ledger is the host_ledgers entry whose kind is runs (08 L53); with no such
    entry there is nothing to compare and the item is skipped. Report only."""
    entry = next((e for e in cfg.get("host_ledgers") or [] if e.get("kind") == "runs"), None)
    if entry is None:
        return
    path = Path(entry["path"])
    if not path.is_absolute():
        path = repo / path
    if not path.is_file():
        return
    host_ids: set = set()
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("run_id"):
                host_ids.add(row["run_id"])
    ours = set(led.latest["runs"])
    for run_id in sorted(ours - host_ids):
        add(18, run_id, "", "run", f"in loop/runs.jsonl, not in {entry['path']}")
    for run_id in sorted(host_ids - ours):
        add(18, run_id, "", "run", f"in {entry['path']}, not in loop/runs.jsonl")


def _item19_session_model_unknown(led: Ledgers, add) -> None:
    """05 L213 item 19: a sessions row whose model is unknown (03 L182: the hook records
    unknown when the hook input carries no model)."""
    seen: set = set()
    for row in sorted(led.latest["sessions"].values(), key=lambda r: r["session_id"]):
        if row.get("model") != "unknown" or row["session_id"] in seen:
            continue
        seen.add(row["session_id"])
        add(19, row["session_id"], f"rl session amend {row['session_id']} --model M",
            f"gyb or {row.get('role')}", "sessions row records model unknown")


def _item20_stale_state_files(repo: Path, led: Ledgers, reference, add) -> None:
    """Item 20 (sync-inbox Q35(a) L194): a session state file under loop/.sessions/ whose
    session is already closed, or which nothing has touched for more than a day. Fix: delete
    the file; pushed to gyb. Q35(g) L195 puts a new item at the end of the numbering."""
    directory = rl_lib.sessions_state_dir(repo)
    if not directory.is_dir():
        return
    sessions = led.latest["sessions"]
    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue
        name = path.name
        sid = name
        for suffix in (".json",) + STATE_SIDE_SUFFIXES:
            if name.endswith(suffix):
                sid = name[: -len(suffix)]
                break
        closed = any(r["session_id"] == sid and r["status"] == "closed" for r in sessions.values())
        open_now = any(r["session_id"] == sid and r["status"] == "open" for r in sessions.values())
        try:
            age = (time.time() - path.stat().st_mtime) / 3600.0
        except OSError:  # pragma: no cover - the file went away between listing and stat
            continue
        if not closed and age < STATE_FILE_STALE_HOURS:
            continue
        why = "its session is closed" if closed else f"untouched for {age:.1f}h"
        if not closed and not open_now:
            why += " and no sessions row carries that id"
        add(20, name, f"rm {rl_lib.LEDGERS_TABLE['dir']}/.sessions/{name}", "gyb", why)


# ---------------------------------------------------------------- text rendering

def render(findings: list[dict]) -> str:
    """One line per finding with the item number, the ids, the fix command and who pushes
    (05 L191-193; "report only" items carry no fix command)."""
    if not findings:
        return "doctor: nothing to report"
    lines = []
    for f in findings:
        bits = [f"item {f['item']}", ", ".join(f["ids"])]
        if f.get("note"):
            bits.append(f["note"])
        bits.append("fix: " + (f["fix_cmd"] or "(report only)"))
        bits.append("push to: " + f["push_to"])
        lines.append("  ".join(bits))
    return "\n".join(lines)


# ---------------------------------------------------------------- commands

def cmd_main(args, ctx):
    """`rl doctor [--json]` (05 L95, L189): a query, so anyone may run it; roles look only
    and hand the fix to the "push to" column (05 L219)."""
    positional, opts = rl_lib.parse_args(args)
    if positional or opts:
        raise rl_lib.RLError("usage", "rl doctor takes no argument",
                             "usage: rl doctor [--json] | --ack ITEM ID | --unack ITEM ID | --list-acks")
    repo, _actor, _force, _reason = rl_lib.context(ctx)
    findings = scan(repo)
    if ctx["opts"]["json"]:
        return findings
    return render(findings)


def _item_and_id(args, sub: str):
    positional, _opts = rl_lib.parse_args(args)
    if len(positional) != 2:
        raise rl_lib.RLError("usage", f"rl doctor {sub} takes ITEM and ID",
                             f"usage: rl doctor {sub} 6 ho-0001-a1")
    item, ident = positional
    if not item.isdigit():
        raise rl_lib.RLError("usage", f"the item number must be a number, got {item!r}")
    return int(item), ident


def _write_ack(args, ctx, sub: str, op: str):
    """05 L217: `--ack` and `--unack` are write commands only gyb may run; a role session is
    exit 3 (commands.json who=gyb, checked through rl_lib.check_who_can_call, which gives an
    empty allow-list to a command with no ledger). The gate comes before the file is
    touched, so a refused caller never creates loop/.doctor-acks.jsonl."""
    item, ident = _item_and_id(args, sub)
    repo, actor, _force, _reason = rl_lib.context(ctx)
    rl_lib.check_who_can_call(actor, ctx["command"])
    with rl_lib.Lock(repo):  # 03 L19: one lock in front of every append
        row = _append_ack(repo, item, ident, actor, op)
    if ctx["opts"]["json"]:
        return row
    return f"{op} item {item} {ident}"


def cmd_ack(args, ctx):
    """`rl doctor --ack ITEM ID` (05 L217): that item and that id are never reported again."""
    return _write_ack(args, ctx, "--ack", "ack")


def cmd_unack(args, ctx):
    """`rl doctor --unack ITEM ID` (05 L217): appends one more line taking the ack back."""
    return _write_ack(args, ctx, "--unack", "unack")


def cmd_list_acks(args, ctx):
    """`rl doctor --list-acks` (05 L217): list every ack recorded so far. A query, so anyone
    may run it (commands.json who=anyone)."""
    positional, opts = rl_lib.parse_args(args)
    if positional or opts:
        raise rl_lib.RLError("usage", "rl doctor --list-acks takes no argument")
    repo, _actor, _force, _reason = rl_lib.context(ctx)
    rows = read_acks(repo)
    if ctx["opts"]["json"]:
        return rows
    if not rows:
        return "no doctor acks recorded"
    return "\n".join(f"{r.get('op', 'ack')}  item {r.get('item')}  {r.get('id')}  {r.get('ts')}  "
                     f"{r.get('actor')}  {r.get('session_id')}" for r in rows)
