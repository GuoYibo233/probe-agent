"""Exact match of the generated arguments against the target at the frozen classifier theta.

Today's build drops the `noparam` short-circuit: params_all_ok is the union count over
both sides' arguments, so a spurious argument on a no-argument target counts wrong
instead of being automatically true.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import polars as pl

from data.environments import open_env
from eval.utils import probe_eval

VERSION = 1
PROBE_KIND = "generator"


def _params_all_ok(t_args: list[tuple[str, str]], p_args: list[tuple[str, str]]) -> bool:
    """The union-by-key comparison: group each side's pairs by key in call order, walk the truth keys then the extra generated keys, and count position-by-position equality over max(len(tv), len(gv)) instances per key."""
    truth_by_key: dict[str, list[str]] = {}
    for key, value in t_args:
        truth_by_key.setdefault(key, []).append(value)
    gen_by_key: dict[str, list[str]] = {}
    for key, value in p_args:
        gen_by_key.setdefault(key, []).append(value)

    keys = list(truth_by_key) + [k for k in gen_by_key if k not in truth_by_key]
    n_instances = 0
    n_ok = 0
    for key in keys:
        tv = truth_by_key.get(key, [])
        gv = gen_by_key.get(key, [])
        n_instances += max(len(tv), len(gv))
        n_ok += sum(1 for i in range(min(len(tv), len(gv))) if tv[i] == gv[i])
    return n_instances == 0 or n_ok == n_instances


def match(pred: str, target: str, env) -> dict[str, bool]:
    """tool_ok, params_all_ok and full_call_ok of two whole calls, both sides normalised through env.split_args; callers hand this two whole calls, prepending the true tool themselves, because an argument string alone cannot be parsed by env.split_args."""
    t = env.split_args(target)
    if t is None:
        raise ValueError(f"cparam.match: target {target!r} does not parse via env.split_args")
    t_tool, t_args, _ = t

    p = env.split_args(pred)
    if p is None:
        return {"tool_ok": False, "params_all_ok": False, "full_call_ok": False}
    p_tool, p_args, _ = p

    tool_ok = p_tool == t_tool
    params_all_ok = _params_all_ok(t_args, p_args)
    return {"tool_ok": tool_ok, "params_all_ok": params_all_ok, "full_call_ok": tool_ok and params_all_ok}


def _stat(df: pl.DataFrame) -> dict:
    n = df.height
    if n == 0:
        return {"tool_ok": 0.0, "params_all_ok": 0.0, "full_call_ok": 0.0}
    return {
        "tool_ok": float(np.mean(df["tool_ok"].to_list())),
        "params_all_ok": float(np.mean(df["params_all_ok"].to_list())),
        "full_call_ok": float(np.mean(df["full_call_ok"].to_list())),
    }


def report(pred_df: pl.DataFrame, cfg, ref, labels: list[str] | None) -> tuple[dict, None]:
    """Join the test predictions to the referenced classifier's fired rows per risk target; tool_ok is the fired label against the prediction row's own tool, params_all_ok is match() over the two rebuilt whole calls."""
    if not (isinstance(ref, tuple) and len(ref) == 2):
        raise ValueError(f"cparam.report: ref must be a (fields, fires) tuple, got {type(ref).__name__}")
    ref_fields, ref_fires = ref
    if labels is not None:
        raise ValueError(f"cparam.report: labels must be None for a generator method, got {labels!r}")

    env = open_env(cfg.data.env)
    test = pred_df.filter(pl.col("split") == "test")

    theta_used: dict[str, float | None] = {}
    exact: dict[str, dict] = {}
    for risk in cfg.eval.risk:
        risk_str = str(risk)
        theta = ref_fields["chosen"][risk_str]
        theta_used[risk_str] = theta
        if theta is None:
            exact[risk_str] = {
                "tool_ok": None, "params_all_ok": None, "full_call_ok": None, "n": 0, "ci": None,
            }
            continue

        fires_risk = ref_fires.filter((pl.col("risk") == risk) & (pl.col("split") == "test"))
        # test's own prediction rows already carry a (null) label_pred column, so the
        # fired label is renamed on the way in rather than joined under the same name.
        fired = fires_risk.select(["example_id", pl.col("label_pred").alias("fired_label")])
        joined = test.join(fired, on="example_id", how="inner")
        n = joined.height
        tool_ok_vals, params_vals, full_vals = [], [], []
        for row in joined.iter_rows(named=True):
            tool = row["tool"]
            tool_ok = row["fired_label"] == tool
            params_all_ok = match(tool + "(" + row["text_pred"], tool + "(" + row["target"], env)["params_all_ok"]
            tool_ok_vals.append(tool_ok)
            params_vals.append(params_all_ok)
            full_vals.append(tool_ok and params_all_ok)
        joined = joined.with_columns([
            pl.Series("tool_ok", tool_ok_vals),
            pl.Series("params_all_ok", params_vals),
            pl.Series("full_call_ok", full_vals),
        ])
        ci = probe_eval.bootstrap_ci(joined, "task_id", _stat, n=cfg.eval.bootstrap, seed=cfg.eval.bootstrap_seed) if n else None
        exact[risk_str] = {
            "tool_ok": round(float(np.mean(tool_ok_vals)), 4) if n else None,
            "params_all_ok": round(float(np.mean(params_vals)), 4) if n else None,
            "full_call_ok": round(float(np.mean(full_vals)), 4) if n else None,
            "n": n,
            "ci": ci,
        }

    n_events_df = pred_df.group_by("split").agg(pl.col("event_id").n_unique().alias("n"))
    n_events = dict(zip(n_events_df["split"].to_list(), n_events_df["n"].to_list()))

    fields = {
        "risk_targets": cfg.eval.risk,
        "theta_used": theta_used,
        "exact": exact,
        "n_events": n_events,
    }
    return fields, None


def main(run_dir: Path) -> None:
    probe_eval.run(run_dir, sys.modules[__name__])


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()
    main(Path(args.run_dir))
