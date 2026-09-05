"""`rl eval ...`: the evaluations ledger (03 L154-172; 05 L81).

One criterion per row, metric or figure. analysis proposes and updates, gyb approves,
rejects and retires; an approved criterion that is updated goes back to proposed
(03 L156). Seven sub-commands (05 L81): propose, update, approve, reject, retire, show,
list. Every rule carries the part and line it transcribes.

Who-can-call is the role table's job (06 L156, `rl_lib.check_who_can_call`):
tables/roles/analysis.json lists `eval propose` and `eval update` only, so approve,
reject and retire are refused for every role and pass for gyb (01 L65).
"""

from __future__ import annotations

from pathlib import Path

import rl_lib

SKELETON_KEYS = ("version", "status", "ts", "actor", "session_id", "schema_version",
                 "force_reason", "via", "agent_id")

# The flags propose and update share; the option name is the flag without `--`.
CONTENT_FLAGS = ("kind", "name", "definition", "metrics-key", "code-path",
                 "group-by", "x", "y", "uses", "applies-to")
FIELD_OF = {"kind": "kind", "name": "name", "definition": "definition",
            "metrics-key": "metrics_key", "code-path": "code_path",
            "group-by": "group_by", "x": "x", "y": "y", "uses": "uses",
            "applies-to": "applies_to"}


def _carry(row: dict) -> dict:
    """The content fields of a row, without the skeleton (03 L31-43). `quote` and `reason`
    belong to the gyb versions that set them (03 L171-172), so a new content version drops
    them."""
    return {k: v for k, v in row.items() if k not in SKELETON_KEYS and k not in ("quote", "reason")}


def _runs_fields() -> set:
    """The runs top-level field names, one of the three value domains of group_by / x / y
    (03 L167-169)."""
    return set((rl_lib.load_schema("runs") or {}).get("properties", {}))


def _approved_metric_ids(repo: Path) -> set:
    latest = rl_lib.latest(rl_lib.read_rows(repo, "evaluations"), "evaluations")
    return {r["id"] for r in latest.values() if r["status"] == "approved" and r["kind"] == "metric"}


def _check_uses_exist(repo: Path, row: dict) -> None:
    """03 L170: `uses` names which metric criteria the figure uses, so each entry must be an
    evaluation id that exists; 01 L88: reference existence binds gyb too."""
    known = {r["id"] for r in rl_lib.read_rows(repo, "evaluations")}
    missing = [u for u in (row.get("uses") or []) if u not in known]
    if missing:
        raise rl_lib.RLError("validation", f"--uses names criteria that do not exist: {', '.join(missing)}",
                             "propose the metric criterion first, or fix the id (03 L170)")


def _check_domain(repo: Path, row: dict) -> None:
    """03 L167-169: group_by, x and y take a runs top-level field name, `config.<key>`, or
    the id of an approved metric criterion; anything else is refused."""
    allowed_fields = _runs_fields()
    approved = _approved_metric_ids(repo)
    for key in ("group_by", "x", "y"):
        value = row.get(key)
        if value is None:
            continue
        if value in allowed_fields:
            continue
        if value.startswith("config.") and len(value) > len("config."):
            continue
        if value in approved:
            continue
        raise rl_lib.RLError("validation",
                             f"{key}={value!r} is outside the allowed domain",
                             "use a runs top-level field name, config.<key>, or the id of an "
                             "approved metric criterion (03 L167-169)")


def _check_kind_shape(repo: Path, row: dict) -> None:
    """The kind-bound rules rl checks itself (the schema's x-conditions carry the rest): a
    metric row has exactly one of metrics_key / code_path (03 L165-166); a figure row's
    `uses` entries exist (03 L170) and its group_by / x / y stay inside their domain
    (03 L167-169)."""
    if row.get("kind") == "metric":
        given = [k for k in ("metrics_key", "code_path") if row.get(k)]
        if len(given) != 1:
            raise rl_lib.RLError("validation",
                                 f"a metric criterion takes exactly one of --metrics-key / --code-path, got {len(given)}",
                                 "give one of them (03 L165-166)")
    if row.get("kind") == "figure":
        _check_uses_exist(repo, row)
        _check_domain(repo, row)


def _check_code_path(repo: Path, row: dict) -> None:
    """03 L166: code_path may be missing while proposed and must exist when approved. The
    value is written as `analysis/common/metrics.py:accuracy`, so the file is the part in
    front of the last colon."""
    value = row.get("code_path")
    if not value:
        return
    path = value.rsplit(":", 1)[0] if ":" in value else value
    if not (repo / path).exists():
        raise rl_lib.RLError("validation", f"code_path {value!r} does not exist ({path})",
                             "write the file first, or approve after it exists (03 L166)")


def _latest(repo: Path, eval_id: str) -> tuple[dict | None, int]:
    return rl_lib.next_version_of(repo, "evaluations", eval_id)


def _fields_from_opts(opts: dict) -> dict:
    out = {}
    for flag in CONTENT_FLAGS:
        if flag in opts:
            out[FIELD_OF[flag]] = opts[flag]
    return out


def _reject_unknown(opts: dict, allowed: tuple, command: str, usage: str) -> None:
    unknown = set(opts) - set(allowed)
    if unknown:
        raise rl_lib.RLError("usage", f"unknown flag(s) for rl {command}: {', '.join(sorted(unknown))}", usage)


def _line(row: dict) -> str:
    bits = [row["id"], row["status"], f"v{row['version']}", row["kind"], row["name"]]
    for key in ("metrics_key", "code_path", "group_by", "x", "y"):
        if row.get(key):
            bits.append(f"{key}={row[key]}")
    if row.get("uses"):
        bits.append("uses=" + ",".join(row["uses"]))
    bits.append(f"applies_to={row.get('applies_to')}")
    return "  ".join(str(b) for b in bits)


# ---------------------------------------------------------------- propose

PROPOSE_USAGE = ("usage: rl eval propose --kind metric|figure --name N --definition D "
                 "[--metrics-key K | --code-path P] [--group-by G --x X --y Y --uses ID ...] --applies-to A")


def cmd_propose(args: list[str], ctx: dict):
    """`rl eval propose ...` (05 L81; 03 L156): analysis writes the proposed version."""
    positional, opts = rl_lib.parse_args(args, multi=("uses",))
    if positional:
        raise rl_lib.RLError("usage", f"rl eval propose takes no positional argument: {positional[0]!r}",
                             PROPOSE_USAGE)
    _reject_unknown(opts, CONTENT_FLAGS, "eval propose", PROPOSE_USAGE)
    kind = opts.get("kind")
    if kind not in ("metric", "figure"):
        raise rl_lib.RLError("usage", f"--kind must be metric or figure, not {kind!r}", PROPOSE_USAGE)
    repo, actor, force, force_reason = rl_lib.context(ctx)
    fields = _fields_from_opts(opts)
    with rl_lib.Lock(repo):  # 03 L19: scan, number, append inside one lock
        if not force:
            _check_kind_shape(repo, fields)
        ids = [r["id"] for r in rl_lib.read_rows(repo, "evaluations")]
        fields["id"] = rl_lib.next_number(ids, "eval")  # eval-NNNN (03 L160)
        row = rl_lib.write_row(repo, "evaluations", fields, actor, ctx["command"],
                               status="proposed", version=1, force=force, force_reason=force_reason)
    if ctx["opts"]["json"]:
        return rl_lib.result(row, "evaluations")
    return _line(row)


# ---------------------------------------------------------------- update

def cmd_update(args: list[str], ctx: dict):
    """`rl eval update ID ...` (05 L81; 03 L156): analysis appends a new version; an
    approved criterion goes back to proposed and waits for gyb again."""
    positional, opts = rl_lib.parse_args(args, multi=("uses",))
    if len(positional) != 1:
        raise rl_lib.RLError("usage", "rl eval update takes exactly one evaluation id",
                             "usage: rl eval update ID [--name ...] [--definition ...] ...")
    _reject_unknown(opts, CONTENT_FLAGS, "eval update",
                    "usage: rl eval update ID [--name ...] [--definition ...] ...")
    eval_id = positional[0]
    repo, actor, force, force_reason = rl_lib.context(ctx)
    with rl_lib.Lock(repo):  # 03 L19
        latest, version = _latest(repo, eval_id)
        if latest is None:
            raise rl_lib.RLError("usage", f"no evaluation {eval_id}", "check `rl eval list`")
        fields = _carry(latest)
        fields.update(_fields_from_opts(opts))
        fields["id"] = eval_id
        if not force:
            _check_kind_shape(repo, fields)
        # 03 L156: the version analysis writes is proposed, whatever the row was before.
        row = rl_lib.write_row(repo, "evaluations", fields, actor, ctx["command"],
                               status="proposed", version=version, force=force, force_reason=force_reason)
    if ctx["opts"]["json"]:
        return rl_lib.result(row, "evaluations")
    return _line(row)


# ---------------------------------------------------------------- approve

def cmd_approve(args: list[str], ctx: dict):
    """`rl eval approve ID [ID ...] --quote Q` (05 L81; 03 L172): gyb approves; one quote
    may approve several criteria. code_path must exist by now (03 L166)."""
    positional, opts = rl_lib.parse_args(args)
    if not positional:
        raise rl_lib.RLError("usage", "rl eval approve takes one or more evaluation ids",
                             "usage: rl eval approve ID [ID ...] --quote Q")
    _reject_unknown(opts, (), "eval approve", "usage: rl eval approve ID [ID ...] --quote Q")
    quote = ctx["opts"]["quote"]  # --quote is a global flag (05 L7-25)
    repo, actor, force, force_reason = rl_lib.context(ctx)
    if not quote and not force:
        raise rl_lib.RLError("validation", "rl eval approve needs --quote \"<gyb's words>\"",
                             "the approve version records gyb's words (03 L172)")
    with rl_lib.Lock(repo):  # 03 L19
        planned = []
        for eval_id in positional:
            latest, version = _latest(repo, eval_id)
            if latest is None:
                raise rl_lib.RLError("usage", f"no evaluation {eval_id}", "check `rl eval list`")
            fields = _carry(latest)
            fields["id"] = eval_id
            fields["quote"] = quote
            if not force:
                _check_code_path(repo, fields)
            planned.append((fields, version))
        # Every id is checked before the first row is written, so a refusal in a multi-id
        # approve leaves the ledger as it was (03 L19: one lock around the whole write).
        rows = [rl_lib.write_row(repo, "evaluations", fields, actor, ctx["command"],
                                 status="approved", version=version, force=force, force_reason=force_reason)
                for fields, version in planned]
    if ctx["opts"]["json"]:
        return {"evaluations": [rl_lib.result(r, "evaluations") for r in rows]}
    return "\n".join(_line(r) for r in rows)


# ---------------------------------------------------------------- reject and retire

def cmd_reject(args: list[str], ctx: dict):
    """`rl eval reject ID --reason R` (05 L81; 03 L171): gyb rejects, reason required."""
    positional, opts = rl_lib.parse_args(args)
    if len(positional) != 1:
        raise rl_lib.RLError("usage", "rl eval reject takes exactly one evaluation id",
                             "usage: rl eval reject ID --reason R")
    _reject_unknown(opts, (), "eval reject", "usage: rl eval reject ID --reason R")
    eval_id = positional[0]
    reason = ctx["opts"]["reason"]  # --reason is a global flag (05 L7-25)
    repo, actor, force, force_reason = rl_lib.context(ctx)
    if not reason:
        raise rl_lib.RLError("validation", "rl eval reject needs --reason R",
                             "say why the criterion is sent back (03 L171)")
    with rl_lib.Lock(repo):  # 03 L19
        latest, version = _latest(repo, eval_id)
        if latest is None:
            raise rl_lib.RLError("usage", f"no evaluation {eval_id}", "check `rl eval list`")
        fields = _carry(latest)
        fields["id"] = eval_id
        fields["reason"] = reason
        row = rl_lib.write_row(repo, "evaluations", fields, actor, ctx["command"],
                               status="rejected", version=version, force=force, force_reason=force_reason)
    if ctx["opts"]["json"]:
        return rl_lib.result(row, "evaluations")
    return _line(row)


def cmd_retire(args: list[str], ctx: dict):
    """`rl eval retire ID` (05 L81; 03 L156): gyb only; a role is refused by its
    ledger_writes (tables/roles/analysis.json has propose and update only)."""
    positional, opts = rl_lib.parse_args(args)
    if len(positional) != 1:
        raise rl_lib.RLError("usage", "rl eval retire takes exactly one evaluation id",
                             "usage: rl eval retire ID")
    _reject_unknown(opts, (), "eval retire", "usage: rl eval retire ID")
    eval_id = positional[0]
    repo, actor, force, force_reason = rl_lib.context(ctx)
    with rl_lib.Lock(repo):  # 03 L19
        latest, version = _latest(repo, eval_id)
        if latest is None:
            raise rl_lib.RLError("usage", f"no evaluation {eval_id}", "check `rl eval list`")
        # PENDING(part 03 L156): which statuses a retire, approve or reject may start from
        # is not ruled; rl only checks who writes them and the field rules.
        fields = _carry(latest)
        fields["id"] = eval_id
        row = rl_lib.write_row(repo, "evaluations", fields, actor, ctx["command"],
                               status="retired", version=version, force=force, force_reason=force_reason)
    if ctx["opts"]["json"]:
        return rl_lib.result(row, "evaluations")
    return _line(row)


# ---------------------------------------------------------------- queries

def cmd_show(args: list[str], ctx: dict):
    """`rl eval show ID` (05 L81). Queries are open to everyone (03 L25)."""
    positional, opts = rl_lib.parse_args(args)
    if len(positional) != 1:
        raise rl_lib.RLError("usage", "rl eval show takes exactly one evaluation id",
                             "usage: rl eval show ID")
    repo = rl_lib.find_repo_root()
    latest, _ = _latest(repo, positional[0])
    if latest is None:
        raise rl_lib.RLError("usage", f"no evaluation {positional[0]}", "check `rl eval list`")
    if ctx["opts"]["json"]:
        return latest
    return _line(latest)


def cmd_list(args: list[str], ctx: dict):
    """`rl eval list [--status S]` (05 L81): the latest version of every row (03 L11)."""
    positional, opts = rl_lib.parse_args(args)
    if positional:
        raise rl_lib.RLError("usage", f"rl eval list takes no positional argument: {positional[0]!r}",
                             "usage: rl eval list [--status S]")
    _reject_unknown(opts, ("status",), "eval list", "usage: rl eval list [--status S]")
    repo = rl_lib.find_repo_root()
    rows = list(rl_lib.latest(rl_lib.read_rows(repo, "evaluations"), "evaluations").values())
    if opts.get("status"):
        rows = [r for r in rows if r["status"] == opts["status"]]
    rows.sort(key=lambda r: r["id"])
    if ctx["opts"]["json"]:
        return {"evaluations": rows}
    return "\n".join(_line(r) for r in rows)
