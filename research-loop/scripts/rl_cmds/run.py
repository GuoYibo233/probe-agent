"""rl run: the runs ledger (03 L98-124; 05 L73; 12 L66-122).

Five sub-commands: `add` writes the launched version, `finish` the finished version
(and its three side effects), `relink` the doctor fix, `show` and `list` are queries.
Every rule below carries the part and line it was copied from.
"""

from __future__ import annotations

import datetime as _dt
import subprocess

import rl_lib

EXIT_VALUES = ("ok", "failed", "killed")  # 03 L117

# Which host command template each exit status calls (08 L50-51; 12 L125, L127, L129):
# ok and failed both call the host finish command; killed calls the abort template on the
# "deregister on the host" step of the interruption sequence.
HOST_TEMPLATE_BY_EXIT = {"ok": "launcher.finish_cmd", "failed": "launcher.finish_cmd",
                         "killed": "launcher.abort_cmd"}


def _opts(args, ctx, *, flags=(), multi=()):
    """rl_lib.parse_args with the sub-command's option list from tables/commands.json: an
    option the signature does not carry is a usage error, exit 5 (03 L224). `started_at`
    and `finished_at` are filled by rl and are not in the `rl run add` / `rl run finish`
    signatures (05 L73), so `--started-at` / `--finished-at` are refused here (30 L117)."""
    return rl_lib.parse_args(args, multi=multi, flags=flags,
                             allowed=rl_lib.allowed_options(ctx["command"]))


def _one_id(positional, ctx, what: str) -> str:
    if len(positional) != 1:
        raise rl_lib.RLError("usage", f"`rl {ctx['command']}` takes exactly one {what}",
                             f"usage: rl {ctx['command']} {what.upper()} ...")
    return positional[0]


def _metrics(items) -> dict:
    """--metric k=v, values are numbers (03 L119: keys are metric names, values numbers)."""
    out = {}
    for item in items:
        if "=" not in item:
            raise rl_lib.RLError("usage", f"--metric {item!r} is not k=v")
        key, raw = item.split("=", 1)
        try:
            out[key] = float(raw)
        except ValueError:
            raise rl_lib.RLError("usage", f"--metric {item!r}: the value must be a number (03 L119)")
    return out


def _parse_ts(text: str) -> _dt.datetime:
    """Read a row timestamp. rl writes %Y-%m-%dT%H:%M:%S%z (rl_lib.now_iso); rows seeded by
    hand may spell the offset +00:00 instead."""
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
        try:
            return _dt.datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return _dt.datetime.fromisoformat(text)
    except ValueError:
        raise rl_lib.RLError("internal", f"cannot read the timestamp {text!r}")


def _seconds_between(started: str, finished: str) -> float:
    """actual_seconds = finished_at - started_at in seconds (03 L118)."""
    a, b = _parse_ts(started), _parse_ts(finished)
    if (a.tzinfo is None) != (b.tzinfo is None):  # one side has no offset: read both as local
        a, b = a.replace(tzinfo=None), b.replace(tzinfo=None)
    return (b - a).total_seconds()


def _runs_by_id(repo, run_id: str) -> list[dict]:
    return [r for r in rl_lib.read_rows(repo, "runs") if r.get("run_id") == run_id]


def _latest_order(repo, ho_id: str) -> dict | None:
    return rl_lib.latest(rl_lib.read_rows(repo, "handoffs"), "handoffs").get(ho_id)


# ---------------------------------------------------------------- write commands

def cmd_add(args, ctx):
    """rl run add --handoff ID --attempt N --commit ... --host ... --gpus ... --log ...
    --tmux ... --watch-cmd ... (05 L73; 03 L100-115; 12 L70).

    who: run or gyb (03 L100), enforced by rl_lib.check_who_can_call inside write_row.
    run_id, command and config are copied from the named attempt; started_at is filled by
    rl (05 L73; 12 L70). The version is launched (03 L107-115).
    """
    repo, actor, force, force_reason = rl_lib.context(ctx)
    _, opts = _opts(args, ctx)
    # --handoff and --attempt are what rl needs to find the attempt it copies from, so a
    # missing one is a usage error (03 L224: a wrong argument); the ledger fields
    # (commit, host, ...) go into the row and are refused by the required-by-status check
    # instead, exit 2 (03 L13; test 10 test_launched_missing_commit_refused).
    ho_id = opts.get("handoff")
    if not ho_id:
        raise rl_lib.RLError("usage", "rl run add needs --handoff ID")
    if not opts.get("attempt"):
        raise rl_lib.RLError("usage", "rl run add needs --attempt N")
    try:
        attempt = int(opts["attempt"])
    except ValueError:
        raise rl_lib.RLError("usage", f"--attempt {opts['attempt']!r} is not a number (03 L106)")

    with rl_lib.Lock(repo):  # 03 L19: scan, assign and append inside one lock
        order = _latest_order(repo, ho_id)
        if order is None:
            raise rl_lib.RLError("usage", f"no handoff {ho_id}")
        att = next((a for a in order.get("attempts") or [] if a.get("attempt") == attempt), None)
        if att is None:
            raise rl_lib.RLError("usage", f"launch order {ho_id} has no attempt {attempt}",
                                 "the attempt is opened by `rl handoff open`/`amend` (04 L38, L43)")
        fields = {
            "run_id": att.get("run_id"),  # 04 L43: rl assigned it as <ho-id>-a<attempt>
            "handoff_id": ho_id,          # 03 L105
            "attempt": attempt,           # 03 L106
            "command": att.get("command"),  # 03 L108: copied from the launch order
            "config": att.get("config"),    # 03 L115: copied from the launch order
            "started_at": rl_lib.now_iso(),  # 03 L114; 05 L73: filled by rl
        }
        for flag, field in (("commit", "commit"), ("host", "host"), ("gpus", "gpus"),
                            ("log", "log_path"), ("tmux", "tmux_session"), ("watch-cmd", "watch_cmd")):
            if opts.get(flag) is not None:
                fields[field] = opts[flag]
        fields = {k: v for k, v in fields.items() if v is not None}
        if "run_id" not in fields:
            raise rl_lib.RLError("validation", f"attempt {attempt} of {ho_id} has no run_id (04 L43)")
        _, version = rl_lib.next_version_of(repo, "runs", fields["run_id"])
        row = rl_lib.write_row(repo, "runs", fields, actor, ctx["command"], status="launched",
                               version=version, force=force, force_reason=force_reason)
    if ctx["opts"]["json"]:
        return rl_lib.result(row, "runs")
    return f"{row['run_id']} launched (version {row['version']}) on {row.get('host')}"


def cmd_finish(args, ctx):
    """rl run finish RUN_ID --exit ok|failed|killed [--metric k=v ...] [--data-path P]
    (05 L73; 03 L116-120; 12 L72, L119).

    One command, four things: the finished version, actual_seconds copied onto the launch
    order's attempt (04 L43), the anomaly check (08 L74-75; 12 L94) and the host command
    template for this exit status (08 L50-51, L55; 12 L119, L125, L127, L129).
    """
    repo, actor, force, force_reason = rl_lib.context(ctx)
    positional, opts = _opts(args, ctx, multi=("metric",))
    run_id = _one_id(positional, ctx, "run_id")
    exit_status = opts.get("exit")
    if exit_status not in EXIT_VALUES:
        # 03 L117: exit_status takes ok, failed or killed; anything else is a wrong
        # argument, exit 5 (03 L224).
        raise rl_lib.RLError("usage", f"--exit takes {', '.join(EXIT_VALUES)}, not {exit_status!r}")
    metrics = _metrics(opts.get("metric", []))
    cfg = rl_lib.load_config(repo)
    notes: list[str] = []
    anomaly_id = None

    with rl_lib.Lock(repo):
        versions = _runs_by_id(repo, run_id)
        if not versions:
            raise rl_lib.RLError("usage", f"no run {run_id}")
        latest = max(versions, key=lambda r: r["version"])
        started = next((r["started_at"] for r in sorted(versions, key=lambda r: -r["version"])
                        if r.get("started_at")), None)
        if started is None:
            raise rl_lib.RLError("validation", f"run {run_id} has no launched version with started_at",
                                 "actual_seconds is computed from the two timestamps (03 L118)")
        finished_at = rl_lib.now_iso()  # 03 L116; 05 L73: filled by rl
        actual_seconds = _seconds_between(started, finished_at)
        fields = {
            "run_id": run_id,
            "handoff_id": latest.get("handoff_id"),
            "attempt": latest.get("attempt"),
            "finished_at": finished_at,
            "exit_status": exit_status,       # 03 L117
            "actual_seconds": actual_seconds,  # 03 L118: recorded whatever the exit status
        }
        if metrics:
            fields["metrics"] = metrics  # 03 L119: required when exit_status is ok
        if opts.get("data-path"):
            # 03 L120: the file or sub-directory in the artifact dir analysis computes
            # from, required when exit_status is ok. The part requires the field, not that
            # the path exists (contrast 04 L35, which spells out "and existing" for
            # report_paths), so rl records it as given.
            fields["data_path"] = opts["data-path"]
        fields = {k: v for k, v in fields.items() if v is not None}
        _, version = rl_lib.next_version_of(repo, "runs", run_id)
        row = rl_lib.write_row(repo, "runs", fields, actor, ctx["command"], status="finished",
                               version=version, force=force, force_reason=force_reason)

        # 04 L43: rl copies actual_seconds onto the launch order's attempt; a person never
        # types it. The version copies the latest handoffs row and keeps its status, so it
        # is not a transition (the transition table is untouched, 04 L53), and it goes in
        # with internal=True because rl writes it on its own behalf, not as a handoffs
        # command the run role calls.
        order = _latest_order(repo, row.get("handoff_id", ""))
        target = None  # the attempt this run belongs to, used again by the anomaly check
        if order is not None and order.get("attempts"):
            order_fields = rl_lib.copy_content(order)  # 04 L29: adopted stays on its own version
            attempts = [dict(a) for a in order_fields["attempts"]]
            # 03 L118: the number goes onto the attempt this run belongs to, found by the
            # run row's attempt number. `rl handoff amend` may have appended attempt 2
            # while attempt 1 was still running, so the last attempt is not always this one.
            target = next((a for a in attempts if a.get("attempt") == row.get("attempt")), None)
            if target is not None:
                target["actual_seconds"] = actual_seconds
                order_fields["attempts"] = attempts
                _, ho_version = rl_lib.next_version_of(repo, "handoffs", order["id"])
                rl_lib.write_row(repo, "handoffs", order_fields, actor, ctx["command"],
                                 status=order["status"], version=ho_version,
                                 force=force, force_reason=force_reason, internal=True)

        # 08 L74-75; 12 L94: the anomaly check runs in this same process at finish time.
        reasons = []
        extremes = cfg["anomaly.metric_extremes"]
        for key, value in sorted(metrics.items()):
            if any(value == extreme for extreme in extremes):
                reasons.append(f"metric {key}={value:g} landed on {value:g}, "
                               f"one of anomaly.metric_extremes {extremes}")
        # 08 L75 compares the real duration with the estimate of "the latest attempt";
        # 04 L43 says estimated_seconds sums the step table of one attempt. Read together
        # (reviewer ruling 2026-09-05), the estimate is the one on the attempt this run
        # belongs to -- the same item actual_seconds just landed on, not the last item in
        # the list, which an amend may have added while this run was still going. An
        # attempt nobody ran `rl handoff estimate` on has no estimated_seconds, and then
        # there is nothing to compare against, so the duration warning is skipped.
        estimated = (target or {}).get("estimated_seconds") or 0
        factor = cfg["anomaly.duration_factor"]
        if estimated > 0 and actual_seconds > factor * estimated:
            reasons.append(f"actual_seconds {actual_seconds:g} is more than {factor} times the "
                           f"estimated {estimated:g} seconds of attempt {row.get('attempt')}")
        if reasons:
            # 12 L94, L105: one issue on the spot, kind anomaly, to gyb; 12 L107: it carries
            # handoff_id and its actor is the writer (run).
            # PENDING(part 12 L186): whether an anomaly issue must carry handoff_id is not
            # pinned down; 12 L107 says run's issues carry it, so rl writes it.
            iss_id = rl_lib.next_number([r["id"] for r in rl_lib.read_rows(repo, "issues")], "iss")
            text = (f"run {run_id} finished {exit_status}: " + "; ".join(reasons))
            issue_fields = {"id": iss_id, "assignee": "gyb", "kind": "anomaly", "text": text}
            if row.get("handoff_id"):
                issue_fields["handoff_id"] = row["handoff_id"]
            rl_lib.write_row(repo, "issues", issue_fields, actor, "issue open", status="open",
                             version=1, force=force, force_reason=force_reason)
            anomaly_id = iss_id
            notes.append(f"anomaly issue {iss_id} opened to gyb: {text}")

    # The host command template for this exit status, skipped when empty (08 L55). ok and
    # failed call launcher.finish_cmd (12 L119, L125, L129: "ok and failed both call the
    # host finish command"); killed calls launcher.abort_cmd, the "deregister on the host"
    # step of the interruption sequence (08 L51; 12 L127). It runs after the lock is
    # released, so a slow host command cannot make every other session time out on
    # loop/.lock (03 L223).
    # PENDING(part 08 L50): the parts do not say what arguments the template receives, so
    # rl runs it exactly as written.
    host_note = _run_host_template(repo, cfg, HOST_TEMPLATE_BY_EXIT[exit_status])
    if host_note:
        notes.append(host_note)

    if ctx["opts"]["json"]:
        extra = {"actual_seconds": row["actual_seconds"]}
        if anomaly_id:
            extra["anomaly_issue"] = anomaly_id
        return rl_lib.result(row, "runs", extra)
    lines = [f"{run_id} finished {exit_status}, actual_seconds {row['actual_seconds']:g}"] + notes
    return "\n".join(lines)


def _run_host_template(repo, cfg, key: str) -> str:
    """Run one launcher.* template, report the outcome in text mode, never fail on it
    (08 L55: an empty template means the host has no such step, so rl skips it without an
    error and never substitutes a command of its own; 12 L127 says the same for abort)."""
    template = (cfg.get(key) or "").strip()
    if not template:
        return ""
    try:
        proc = subprocess.run(template, shell=True, cwd=str(repo), capture_output=True, text=True)
    except OSError as err:  # pragma: no cover - the host command is not rl's to fix
        return f"{key} {template!r} could not run: {err}"
    if proc.returncode != 0:
        return (f"{key} {template!r} exited {proc.returncode}: "
                f"{(proc.stderr or proc.stdout).strip().splitlines()[-1] if (proc.stderr or proc.stdout).strip() else ''}")
    return f"{key} {template!r} ran"


def cmd_relink(args, ctx):
    """rl run relink RUN_ID --handoff ID (05 L73; 03 L100; sync-inbox Q31).

    The doctor item 6 fix: a new version copies status and every other field from the
    latest version and changes only handoff_id.
    """
    repo, actor, force, force_reason = rl_lib.context(ctx)
    positional, opts = _opts(args, ctx)
    run_id = _one_id(positional, ctx, "run_id")
    new_handoff = opts.get("handoff")
    if not new_handoff:
        raise rl_lib.RLError("usage", "rl run relink needs --handoff ID")
    with rl_lib.Lock(repo):
        versions = _runs_by_id(repo, run_id)
        if not versions:
            raise rl_lib.RLError("usage", f"no run {run_id}")
        if _latest_order(repo, new_handoff) is None:
            raise rl_lib.RLError("usage", f"no handoff {new_handoff}")  # 03 L224: unknown id
        latest = max(versions, key=lambda r: r["version"])
        fields = rl_lib.copy_content(latest)
        fields["handoff_id"] = new_handoff
        row = rl_lib.write_row(repo, "runs", fields, actor, ctx["command"],
                               status=latest["status"], version=latest["version"] + 1,
                               force=force, force_reason=force_reason)
    if ctx["opts"]["json"]:
        return rl_lib.result(row, "runs")
    return f"{run_id} version {row['version']} now points at {new_handoff}"


# ---------------------------------------------------------------- query commands

def cmd_show(args, ctx):
    """rl run show RUN_ID (05 L73): the latest version of one run."""
    repo = rl_lib.find_repo_root()
    positional, _ = _opts(args, ctx)
    run_id = _one_id(positional, ctx, "run_id")
    versions = _runs_by_id(repo, run_id)
    if not versions:
        raise rl_lib.RLError("usage", f"no run {run_id}")
    versions.sort(key=lambda r: r["version"])
    row = versions[-1]
    if ctx["opts"]["json"]:
        return row
    lines = [f"{run_id} ({len(versions)} version(s))"]
    for v in versions:
        lines.append(f"  v{v['version']} {v['status']} {v.get('exit_status', '')} {v['ts']} {v['actor']}")
    return "\n".join(lines)


def _matches_line(order: dict, wanted: str) -> bool:
    """PENDING(part 04 L27): line is stored as one value or as a list; match either."""
    line = order.get("line")
    if isinstance(line, list):
        return wanted in line
    return line == wanted


def cmd_list(args, ctx):
    """rl run list [--handoff ID] [--decision ID] [--batch B] [--line L] [--all]
    (05 L73; 03 L124).

    Default: for each launch order only its latest attempt, and only when that run's
    latest version is finished with exit_status ok (03 L124). --all shows everything.
    --decision, --batch and --line are resolved through the launch order the run points
    at, because the runs row carries none of them (05 L73).
    """
    repo = rl_lib.find_repo_root()
    _, opts = _opts(args, ctx, flags=("all",))
    runs = list(rl_lib.latest(rl_lib.read_rows(repo, "runs"), "runs").values())
    orders = rl_lib.latest(rl_lib.read_rows(repo, "handoffs"), "handoffs")

    if opts.get("handoff"):
        runs = [r for r in runs if r.get("handoff_id") == opts["handoff"]]
    if opts.get("batch"):
        runs = [r for r in runs if (orders.get(r.get("handoff_id", "")) or {}).get("batch") == opts["batch"]]
    if opts.get("decision"):
        wanted = opts["decision"]
        runs = [r for r in runs
                if any(ref.get("id") == wanted
                       for ref in (orders.get(r.get("handoff_id", "")) or {}).get("decision_refs") or [])]
    if opts.get("line"):
        runs = [r for r in runs if _matches_line(orders.get(r.get("handoff_id", "")) or {}, opts["line"])]

    if not opts.get("all"):
        newest: dict[str, dict] = {}
        for r in runs:
            key = r.get("handoff_id", "")
            if key not in newest or (r.get("attempt") or 0) > (newest[key].get("attempt") or 0):
                newest[key] = r
        runs = [r for r in newest.values()
                if r.get("status") == "finished" and r.get("exit_status") == "ok"]

    runs.sort(key=lambda r: r["run_id"])
    if ctx["opts"]["json"]:
        return runs
    if not runs:
        return "no runs"
    return "\n".join(f"{r['run_id']}  {r['status']}  {r.get('exit_status', '-')}  {r.get('handoff_id', '-')}"
                     for r in runs)
