"""rl scratch: the middle versions of a quick lane (03 L194-213; 05 L87; 07 L39, L77).

`scratch add` appends one middle version (numbers and notes, status stays open); `scratch
list` and `scratch show` are the two query commands 07 L77 names. The quick lane's own
open and close versions are written by `rl ql` (rl_cmds/ql.py).
"""

from __future__ import annotations

import rl_lib

SCRATCH_STATUSES = ("open", "merged", "dropped")  # 03 L196: three, no fourth state

# A version that copies an older row goes through rl_lib.copy_content: it drops the
# skeleton fields and the version-only ones (04 L29), so every module copies the same way.


def opts_of(args, ctx, *, flags=(), multi=()):
    """rl_lib.parse_args with the sub-command's option list from tables/commands.json: an
    option the signature does not carry is a usage error, exit 5 (03 L224)."""
    return rl_lib.parse_args(args, multi=multi, flags=flags,
                             allowed=rl_lib.allowed_options(ctx["command"]))


def one_tag(positional, ctx) -> str:
    if len(positional) != 1:
        raise rl_lib.RLError("usage", f"`rl {ctx['command']}` takes exactly one ql_tag",
                             f"usage: rl {ctx['command']} QL ...")
    return positional[0]


def rows_of(repo, ql_tag: str) -> list[dict]:
    return [r for r in rl_lib.read_rows(repo, "scratch") if r.get("ql_tag") == ql_tag]


def latest_row(repo, ql_tag: str) -> dict:
    """The latest version of one quick lane; an unknown tag is a usage error (03 L224: an id that does not exist)."""
    rows = rows_of(repo, ql_tag)
    if not rows:
        raise rl_lib.RLError("usage", f"no quick lane {ql_tag}")
    return max(rows, key=lambda r: r["version"])


def require_open(row: dict) -> None:
    """03 L196, L211: a quick lane is written while it is open -- the middle versions are
    "what happened while it was open" and the merged and dropped versions close it. Writing
    another version onto a closed lane would take it back out of its end state, which
    03 L196 does not allow (no fourth state, and the two end states are the way out).
    PENDING(part 03 L196): the parts do not spell out the refusal, only the shape."""
    if row["status"] != "open":
        raise rl_lib.RLError("validation",
                             f"quick lane {row['ql_tag']} is {row['status']}, not open",
                             "a closed quick lane takes no further version; open a new one "
                             "with `rl ql open` (03 L196, L211)")


def metrics_of(items) -> dict:
    """--metric k=v with number values (03 L207: metrics is a key-value map)."""
    out = {}
    for item in items:
        if "=" not in item:
            raise rl_lib.RLError("usage", f"--metric {item!r} is not k=v")
        key, raw = item.split("=", 1)
        try:
            out[key] = float(raw)
        except ValueError:
            raise rl_lib.RLError("usage", f"--metric {item!r}: the value must be a number")
    return out


def cmd_add(args, ctx):
    """rl scratch add QL [--note ...] [--metric k=v ...] (05 L87; 07 L39; 03 L206-207).

    who: deploy or analysis (05 L87; 03 L196), enforced by rl_lib.check_who_can_call
    inside write_row, where gyb is exempt (01 L65). A middle version keeps status open
    (03 L211); role is copied from the open version because the schema requires it on
    every row (schemas/scratch.schema.json required).
    """
    repo, actor, force, force_reason = rl_lib.context(ctx)
    positional, opts = opts_of(args, ctx, multi=("metric",))
    ql_tag = one_tag(positional, ctx)
    metrics = metrics_of(opts.get("metric", []))
    with rl_lib.Lock(repo):  # 03 L19
        latest = latest_row(repo, ql_tag)
        require_open(latest)
        fields = {"ql_tag": ql_tag, "role": latest["role"]}
        if opts.get("note"):
            fields["note"] = opts["note"]
        if metrics:
            fields["metrics"] = metrics
        row = rl_lib.write_row(repo, "scratch", fields, actor, ctx["command"], status="open",
                               version=latest["version"] + 1, force=force, force_reason=force_reason)
    if ctx["opts"]["json"]:
        return rl_lib.result(row, "scratch")
    return f"{ql_tag} version {row['version']} added"


def cmd_list(args, ctx):
    """rl scratch list [--status S] (05 L87; 07 L77): the latest version of every quick
    lane, filtered by status."""
    repo = rl_lib.find_repo_root()
    _, opts = opts_of(args, ctx)
    wanted = opts.get("status")
    if wanted is not None and wanted not in SCRATCH_STATUSES:
        raise rl_lib.RLError("usage", f"--status takes {', '.join(SCRATCH_STATUSES)}, not {wanted!r}")
    rows = list(rl_lib.latest(rl_lib.read_rows(repo, "scratch"), "scratch").values())
    if wanted:
        rows = [r for r in rows if r["status"] == wanted]
    rows.sort(key=lambda r: r["ql_tag"])
    if ctx["opts"]["json"]:
        return rows
    if not rows:
        return "no quick lanes"
    return "\n".join(f"{r['ql_tag']}  {r['status']}  {r['role']}  {r.get('worktree') or r.get('dir') or '-'}"
                     for r in rows)


def cmd_show(args, ctx):
    """rl scratch show QL (05 L87; 07 L77): the latest version of one quick lane; the text
    form lists every version so the numbers appended in between are visible."""
    repo = rl_lib.find_repo_root()
    positional, _ = opts_of(args, ctx)
    ql_tag = one_tag(positional, ctx)
    rows = rows_of(repo, ql_tag)
    if not rows:
        raise rl_lib.RLError("usage", f"no quick lane {ql_tag}")
    rows.sort(key=lambda r: r["version"])
    if ctx["opts"]["json"]:
        return rows[-1]
    lines = [f"{ql_tag} ({rows[-1]['role']}, {len(rows)} version(s))"]
    for r in rows:
        detail = r.get("note") or r.get("reason") or r.get("handoff_id") or r.get("worktree") or r.get("dir") or ""
        metrics = " ".join(f"{k}={v:g}" for k, v in sorted((r.get("metrics") or {}).items()))
        lines.append(f"  v{r['version']} {r['status']} {r['ts']} {detail} {metrics}".rstrip())
    return "\n".join(lines)
