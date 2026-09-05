"""rl ql: the way into and out of a quick lane (07 L21-122; 03 L194-213; 05 L87).

`ql open` assigns the quick-lane tag inside the lock, makes the worktree (deploy) or the
scratch directory (analysis) and writes the open version; `ql close` writes the merged or
dropped version and deletes the worktree and the branch. The middle versions are
`rl scratch add` (rl_cmds/scratch.py).
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import rl_lib
from rl_cmds.scratch import latest_row, one_tag, opts_of, require_open, rows_of

QL_ROLES = ("deploy", "analysis")  # 05 L87; 03 L201


def _git(repo: Path, *args, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise rl_lib.RLError("internal", f"git {' '.join(args)} failed: {(proc.stderr or proc.stdout).strip()}")
    return proc


def _worktree_root(repo: Path, cfg: dict) -> Path:
    """quick_lane.worktree_root, where the worktree and its same-named branch go
    (07 L28, L136; 08 L78). The default in tables/config_defaults.json is written as
    `<repo>/../<repo-name>-ql/`; those two placeholders are filled in here so the default
    means what 08 L78 says it means."""
    raw = str(cfg["quick_lane.worktree_root"])
    raw = raw.replace("<repo-name>", repo.name).replace("<repo>", str(repo))
    return Path(raw)


def _guard_write(repo: Path, actor, command: str) -> None:
    """The two checks that must come before any side effect on disk: the writing session is
    still open (03 L15) and this actor may call the command (05 L100; 06 L156). rl_lib runs
    both again inside write_row; running them first keeps a refused `ql open` from leaving a
    worktree behind."""
    rl_lib.check_writer_alive(repo, actor)
    rl_lib.check_who_can_call(actor, command)


def cmd_open(args, ctx):
    """rl ql open [--role deploy|analysis] [--from ho-ID] (05 L87; 07 L23-31).

    Three things (07 L25-29): the tag is assigned inside the lock, the directory is made,
    and the open version goes into the scratch ledger. who: deploy or analysis (05 L87);
    gyb passes as the superuser and is recorded as the actor (01 L65; proxy decision D-16,
    scratch schema actor enum).
    """
    repo, actor, force, force_reason = rl_lib.context(ctx)
    _, opts = opts_of(args, ctx, value=("role", "from"))
    role = opts.get("role") or actor.role_session
    if role is None:
        raise rl_lib.RLError("usage", "rl ql open needs --role deploy|analysis from a bare terminal",
                             "inside a role session the role of the session is used (05 L87)")
    if role not in QL_ROLES:
        raise rl_lib.RLError("usage", f"--role takes {' or '.join(QL_ROLES)}, not {role!r}")
    _guard_write(repo, actor, ctx["command"])
    cfg = rl_lib.load_config(repo)
    from_id = opts.get("from")

    with rl_lib.Lock(repo):  # 03 L19; 07 L27: the tag is assigned inside the lock
        order = None
        if from_id:
            # Read and check the order to be transferred before anything is created, so a
            # refused transfer leaves neither a worktree nor an open quick lane behind
            # (the ledgers only ever grow, 03 L11).
            order = rl_lib.latest(rl_lib.read_rows(repo, "handoffs"), "handoffs").get(from_id)
            if order is None:
                raise rl_lib.RLError("usage", f"no handoff {from_id}")
            if order.get("work_type") != "work_order":
                # 07 L31: --from takes "a todo work order" into the quick lane; a
                # launch_order or an analysis_order is not one of them.
                raise rl_lib.RLError("validation",
                                     f"{from_id} is a {order.get('work_type')}, not a work_order",
                                     "`rl ql open --from` takes a todo work order (07 L31)")
            trow = rl_lib.find_transition("ql open --from", order["status"])
            rl_lib.check_who_can_write(trow, actor, order)
        tags = [r["ql_tag"] for r in rl_lib.read_rows(repo, "scratch")]
        # 07 L27; 03 L200: the tag is ql-YYYYMMDD-NN, so the running number is scoped to
        # today's date and two digits wide (rl_lib.next_number widens past 99 by itself).
        ql_tag = rl_lib.next_number(tags, "ql-" + time.strftime("%Y%m%d"), width=2)
        fields = {"ql_tag": ql_tag, "role": role}
        if role == "deploy":
            # 07 L28; 03 L202-205: a worktree at quick_lane.worktree_root/<ql_tag> on a
            # branch of the same name, cut from the repo's HEAD; base_commit is that HEAD.
            root = _worktree_root(repo, cfg)
            path = root / ql_tag
            root.mkdir(parents=True, exist_ok=True)
            head = _git(repo, "rev-parse", "HEAD").stdout.strip()
            _git(repo, "worktree", "add", "-b", ql_tag, str(path))
            fields.update({"worktree": str(path), "base_commit": head, "branch": ql_tag})
        else:
            # 07 L28; 03 L203: the analysis quick lane builds no worktree and no branch;
            # its output goes to analysis/scratch/<ql_tag>/.
            rel = f"analysis/scratch/{ql_tag}/"
            (repo / rel).mkdir(parents=True, exist_ok=True)
            fields["dir"] = rel
        row = rl_lib.write_row(repo, "scratch", fields, actor, ctx["command"], status="open",
                               version=1, force=force, force_reason=force_reason)

        transferred = None
        if order is not None:
            # 07 L31: --from takes a todo work order into the quick lane -- rl appends one
            # version marking it quick_lane, and from then on it is out of the todo queue:
            # nobody is dispatched to it and it takes no holder (transitions.json
            # ql_transfer_in, sync-inbox Q41(c)). The status does not change.
            order_fields = rl_lib.copy_content(order)  # 04 L29: adopted stays on its own version
            order_fields["quick_lane"] = True
            # PENDING(issue 41f): the sub-command that takes a transferred order back out
            # (straight to done_pending_review on merge-back, or back to todo with the
            # quick_lane mark cleared) has no name yet (07 L114; transitions.json
            # ql_transfer_exit), so until 41f is ruled a transferred order can neither
            # leave the quick lane nor be closed with `rl ql close --merged`: that path
            # needs a supplement whose ql_tag is this lane, and rl sets no ql_tag here
            # (whether a transferred order carries one is part of the same question).
            _, ho_version = rl_lib.next_version_of(repo, "handoffs", from_id)
            # The command stays `ql open`: the who-can-call check reads the scratch ledger
            # this command writes (05 L87), and who may mark this order is the transition
            # table's who_can_write, checked above.
            rl_lib.write_row(repo, "handoffs", order_fields, actor, ctx["command"],
                             status=order["status"], version=ho_version,
                             force=force, force_reason=force_reason)
            transferred = from_id

    if ctx["opts"]["json"]:
        extra = {"role": role, "worktree": fields.get("worktree"), "dir": fields.get("dir")}
        if transferred:
            extra["from"] = transferred
        return rl_lib.result(row, "scratch", {k: v for k, v in extra.items() if v is not None})
    where = fields.get("worktree") or fields.get("dir")
    line = f"{ql_tag} open ({role}) at {where}"
    if transferred:
        line += f"; {transferred} marked quick_lane"
    return line


def cmd_close(args, ctx):
    """rl ql close QL --merged --handoff ID | --dropped --reason R (05 L87; 07 L83-92).

    --merged is only for deploy: the analysis quick lane has no merge-back and only
    --dropped (07 L86; 03 L208). Both paths delete the worktree and the branch of the same
    name (07 L92).

    --reason is one of bin/rl's five global flags, so it arrives in ctx["opts"], not in
    args (bin/rl split_global_flags).
    """
    repo, actor, force, force_reason = rl_lib.context(ctx)
    positional, opts = opts_of(args, ctx, value=("handoff",), flags=("merged", "dropped"))
    ql_tag = one_tag(positional, ctx)
    merged = bool(opts.get("merged"))
    dropped = bool(opts.get("dropped"))
    if merged == dropped:
        raise rl_lib.RLError("usage", "rl ql close takes exactly one of --merged or --dropped",
                             "usage: rl ql close QL --merged --handoff ID | --dropped --reason R")
    if merged and not actor.is_gyb and actor.role_session != "deploy":
        # 07 L86; 05 L87: merging back is deploy's alone; gyb is exempt (01 L65).
        raise rl_lib.RLError("forbidden",
                             f"`rl ql close --merged` is deploy's, not {actor.role_session}'s",
                             "the analysis quick lane closes with --dropped (07 L86); or ask gyb: "
                             + rl_lib.issue_command_for_gyb(
                                 f"{actor.role_session} needs to merge quick lane {ql_tag} back"))
    _guard_write(repo, actor, ctx["command"])

    with rl_lib.Lock(repo):  # 03 L19
        latest = latest_row(repo, ql_tag)
        require_open(latest)
        fields = {"ql_tag": ql_tag, "role": latest["role"]}
        if merged:
            if latest["role"] != "deploy":
                # 03 L208; 07 L86: merged exists only for the deploy quick lane.
                raise rl_lib.RLError("validation",
                                     f"quick lane {ql_tag} belongs to {latest['role']}; merged is "
                                     "only for a deploy quick lane (03 L208; 07 L86)")
            handoff_id = opts.get("handoff")
            if not handoff_id:
                raise rl_lib.RLError("usage", "rl ql close --merged needs --handoff ID")
            order = rl_lib.latest(rl_lib.read_rows(repo, "handoffs"), "handoffs").get(handoff_id)
            if order is None:
                raise rl_lib.RLError("usage", f"no handoff {handoff_id}")
            if not order.get("quick_lane") or order.get("ql_tag") != ql_tag:
                # 05 L87; 03 L208; 07 L88: ID must be the quick-lane supplement whose
                # ql_tag is this lane -- the two point at each other.
                raise rl_lib.RLError("validation",
                                     f"{handoff_id} is not a quick_lane supplement whose ql_tag is {ql_tag}",
                                     "open the supplement first (`rl handoff open --quick-lane "
                                     "--ql QL ...`), then close the quick lane with its id (07 L88)")
            fields["handoff_id"] = handoff_id
            status = "merged"
        else:
            # 03 L209: the dropped version needs reason. A missing --reason leaves the
            # field out and the required-by-status check refuses it, exit 2 (03 L13).
            reason = ctx["opts"].get("reason")
            if reason:
                fields["reason"] = reason
            status = "dropped"
        row = rl_lib.write_row(repo, "scratch", fields, actor, ctx["command"], status=status,
                               version=latest["version"] + 1, force=force, force_reason=force_reason)
        # 07 L92: closing deletes the worktree and the branch of the same name, on both
        # paths; the analysis quick lane has neither, so nothing is removed there. This runs
        # after the row is written, so a refused close leaves the worktree in place.
        removed = _remove_worktree(repo, rows_of(repo, ql_tag))

    if ctx["opts"]["json"]:
        return rl_lib.result(row, "scratch", {"removed": removed})
    tail = f"; removed {', '.join(removed)}" if removed else ""
    return f"{ql_tag} {status}{tail}"


def _remove_worktree(repo: Path, versions: list[dict]) -> list[str]:
    """Delete the worktree and the branch recorded on the open version, each when it exists
    (07 L92). Failures of git are not the close's business: the row is already written."""
    worktree = branch = None
    for row in sorted(versions, key=lambda r: r["version"]):
        worktree = row.get("worktree") or worktree
        branch = row.get("branch") or branch
    removed = []
    if worktree and Path(worktree).exists():
        if _git(repo, "worktree", "remove", "--force", worktree, check=False).returncode == 0:
            removed.append(worktree)
    if branch:
        if _git(repo, "branch", "-D", branch, check=False).returncode == 0:
            removed.append(branch)
    return removed
