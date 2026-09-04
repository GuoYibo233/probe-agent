"""rl trace: the whole chain behind one id (05 L145-147).

05 L147: `rl trace <编号>` takes five kinds of id - `dec-`, `ho-`, a run_id, `iss-` and
`eval-` - and one command prints the chain from the run through the launch order and the
work order to the decision versions. It walks the two handoffs fields that carry the
chain, `parent_id` and `decision_refs`. It is a query command, so anyone may call it
(05 L100).
"""

from __future__ import annotations

import re

import rl_lib

_RUN_RE = re.compile(r"^ho-[0-9]{4,}-a[0-9]+$")        # 04 L43: <ho-id>-a<attempt>
_HANDOFF_RE = re.compile(r"^ho-[0-9]{4,}$")            # 04 L17
_ISSUE_RE = re.compile(r"^iss-[0-9]{4,}$")             # 03 L69
_EVAL_RE = re.compile(r"^eval-[0-9]{4,}$")             # evaluations schema id
_DECISION_RE = re.compile(r"^dec-(idea|deploy|run|analysis|reviewer|gyb)-[0-9]{4,}$")  # 02 L21


def _node(ledger: str, row: dict, version: int | None = None) -> dict:
    """One link of the chain. The shape is fixed by the task's --json convention:
    {"ledger", "id", "version"}."""
    return {"ledger": ledger, "id": rl_lib.row_key(ledger, row),
            "version": row["version"] if version is None else version}


def _extend(chain: list, node: dict) -> None:
    """Append unless the same ledger, id and version is already in the chain."""
    if node not in chain:
        chain.append(node)


def _order_chain(order_id: str, orders: dict) -> list:
    """One order and its ancestors along parent_id, child first (05 L147: launch order
    then work order). A parent_id that points nowhere ends the walk; 05 L196 doctor item 2
    is what reports such a dangling reference."""
    out, seen, cur = [], set(), order_id
    while cur and cur in orders and cur not in seen:
        seen.add(cur)
        out.append(cur)
        cur = orders[cur].get("parent_id")
    return out


def _runs_of(order_ids: list, runs_by_order: dict) -> list:
    out = []
    for order_id in order_ids:
        out.extend(runs_by_order.get(order_id, []))
    return out


def _decisions_of(order_ids: list, orders: dict, decisions: list) -> list:
    """The decision versions the orders in the chain cite, in chain order (05 L147: the
    chain runs on decision_refs)."""
    out = []
    for order_id in order_ids:
        for ref in orders[order_id].get("decision_refs") or []:
            rows = [r for r in decisions if r["id"] == ref["id"] and r["version"] == ref["version"]]
            node = {"ledger": "decisions", "id": ref["id"], "version": ref["version"]}
            if rows and node not in out:
                out.append(node)
            elif not rows and node not in out:
                out.append(node)  # a dangling ref is still part of the chain, doctor item 2 reports it
    return out


def _from_order(order_id: str, orders: dict, runs_by_order: dict, decisions: list,
                include_runs: bool = True) -> list:
    """The run-to-decision chain that passes through one order (05 L147)."""
    chain_ids = _order_chain(order_id, orders)
    chain = []
    if include_runs:
        for run in _runs_of(chain_ids, runs_by_order):
            _extend(chain, _node("runs", run))
    for oid in chain_ids:
        _extend(chain, _node("handoffs", orders[oid]))
    for node in _decisions_of(chain_ids, orders, decisions):
        _extend(chain, node)
    return chain


def cmd_main(args, ctx):
    """05 L52, L145-147: `rl trace <dec-|ho-|run_id|iss-|eval->`."""
    pos, _opts = rl_lib.parse_args(args)
    if not pos:
        raise rl_lib.RLError("usage", "rl trace needs an id",
                             "ids it takes: dec-, ho-, a run_id, iss-, eval- (05 L147)")
    ident = pos[0]
    repo, _actor, _force, _reason = rl_lib.context(ctx)
    orders = rl_lib.latest(rl_lib.read_rows(repo, "handoffs"), "handoffs")
    runs = rl_lib.latest(rl_lib.read_rows(repo, "runs"), "runs")
    runs_by_order: dict = {}
    for run_id in sorted(runs):
        runs_by_order.setdefault(runs[run_id].get("handoff_id"), []).append(runs[run_id])
    decisions = rl_lib.read_decisions(repo)
    chain: list = []

    if _RUN_RE.match(ident):
        if ident not in runs:
            raise rl_lib.RLError("usage", f"unknown run {ident}")
        _extend(chain, _node("runs", runs[ident]))
        # 05 L147: the chain starts at the run and climbs its launch order's parent_id.
        for node in _from_order(runs[ident].get("handoff_id"), orders, runs_by_order, decisions,
                                include_runs=False):
            _extend(chain, node)
    elif _HANDOFF_RE.match(ident):
        if ident not in orders:
            raise rl_lib.RLError("usage", f"unknown handoff {ident}")
        for node in _from_order(ident, orders, runs_by_order, decisions):
            _extend(chain, node)
    elif _ISSUE_RE.match(ident):
        issues = rl_lib.latest(rl_lib.read_rows(repo, "issues"), "issues")
        if ident not in issues:
            raise rl_lib.RLError("usage", f"unknown issue {ident}")
        _extend(chain, _node("issues", issues[ident]))
        # 03 L75: an issue reaches the chain through its handoff_id.
        linked = issues[ident].get("handoff_id")
        if linked:
            for node in _from_order(linked, orders, runs_by_order, decisions):
                _extend(chain, node)
    elif _EVAL_RE.match(ident):
        evaluations = rl_lib.latest(rl_lib.read_rows(repo, "evaluations"), "evaluations")
        if ident not in evaluations:
            raise rl_lib.RLError("usage", f"unknown evaluation {ident}")
        _extend(chain, _node("evaluations", evaluations[ident]))
        # 04 L33: an analysis order cites its evaluations in evaluation_refs.
        for order_id in sorted(orders):
            if any(ref["id"] == ident for ref in orders[order_id].get("evaluation_refs") or []):
                for node in _from_order(order_id, orders, runs_by_order, decisions):
                    _extend(chain, node)
    elif _DECISION_RE.match(ident):
        versions = [r for r in decisions if r["id"] == ident]
        if not versions:
            raise rl_lib.RLError("usage", f"unknown decision {ident}")
        for order_id in sorted(orders):
            if any(ref["id"] == ident for ref in orders[order_id].get("decision_refs") or []):
                for node in _from_order(order_id, orders, runs_by_order, decisions):
                    _extend(chain, node)
        if not chain:
            # PENDING(part 05 L147): the part names the chain from the run end and does not
            # say what a `dec-` id with no order citing it prints. Narrowest reading: the
            # decision's own versions, which is the far end of the chain either way.
            for row in sorted(versions, key=lambda r: r["version"]):
                _extend(chain, _node("decisions", row))
    else:
        raise rl_lib.RLError("usage", f"{ident!r} is not an id rl trace takes",
                             "it takes dec-, ho-, a run_id, iss- and eval- (05 L147)")

    text = "\n".join(f"{node['ledger']} {node['id']} v{node['version']}" for node in chain)
    return chain if ctx["opts"]["json"] else text
