"""Score a sample or inject run from its task records: success rates and probe agreement rates, paired against a baseline.

TODO(gyb, 2026-09-18): owner ruling — nothing in this report beyond accuracy
was ever asked for, so everything else is removed until the owner decides
what a score report should hold. Removed, with all the code that computed
them: the run and baseline blocks' steps_mean, completed, tokens_in,
tokens_out, n_inject_per_task, discard_chars, discard_tokens, wall_s_mean;
the paired block's tokens_out and base_tokens_out; the spec block's exec_ok,
conf_mean, discarded_chars, error_kinds; the whole resume block; the whole
by_seed block. score.by_seed is now a setting that nothing reads.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import polars as pl

from data import trajectory_record
from data.environments import open_env, requested_pairs
from experimental_settings import schema
from jobs import registry

# VERSION rule: read this before you edit this file (errata "3.3 / 8.6", gyb 2026-09-18).
# Bump VERSION only when some existing setting would now produce a different output of a stage
# that lists this file in the stage table of experimental_settings/schema.py. A new feature
# behind a new setting field whose default reproduces the old behaviour, a message, a comment
# or a report layout does not bump.
# Every bump adds one VERSION_HISTORY entry: {<new version>: {"why": "<one sentence>",
# "stale": (<stage names>)}}. "stale" names the stages (sample, build, train, eval, inject,
# score) whose existing outputs can no longer be used; leave "stale" out and every stage is
# stale. The key folds the highest version that made a stage stale, so a bump that leaves a
# stage usable keeps that stage's run directory. When unsure, list the stage.
VERSION = 1
VERSION_HISTORY = {}

_GENERATION_FIELDS = ("temperature", "top_p", "max_step_tokens", "stop", "effort", "date")
_DATA_FIELDS = ("env", "instructions")


def _atomic_write_json(path: Path, obj) -> None:
    path = Path(path)
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False))
    os.replace(tmp, path)


def _rate(numer: float, denom: int) -> float | None:
    return round(numer / denom, 4) if denom else None


def _first_diff_field(a, b) -> str | None:
    """The first field (dotted, section first) where a and b's data, models.agent or generation sections differ."""
    for name in _DATA_FIELDS:
        if getattr(a.data, name) != getattr(b.data, name):
            return f"data.{name}"
    if a.models.agent != b.models.agent:
        return "models.agent"
    for name in _GENERATION_FIELDS:
        if getattr(a.generation, name) != getattr(b.generation, name):
            return f"generation.{name}"
    return None


def _finals(df: pl.DataFrame) -> pl.DataFrame:
    """One row per record: its meta identity and its final success/abort outcome."""
    meta = df.filter(pl.col("type") == "meta").select(["record_id", "task_id", "seed"])
    final = df.filter(pl.col("type") == "final").select(["record_id", "success", "abort"])
    return meta.join(final, on="record_id", how="left")


def _run_block(rec: pl.DataFrame) -> dict:
    n = rec.height
    if n == 0:
        return {"n_records": 0, "n_abort": 0, "success": None, "success_no_abort": None}
    n_abort = rec.filter(pl.col("abort").is_not_null()).height
    no_abort = rec.filter(pl.col("abort").is_null())
    return {
        "n_records": n,
        "n_abort": n_abort,
        "success": _rate(float(rec["success"].sum()), n),
        "success_no_abort": _rate(float(no_abort["success"].sum()), no_abort.height),
    }


def _paired_block(rec: pl.DataFrame, brec: pl.DataFrame | None) -> dict:
    empty = {"n": 0, "success": None, "base_success": None, "delta_success": None}
    if brec is None:
        return empty
    joined = rec.join(brec, on=["task_id", "seed"], how="inner", suffix="_base")
    n = joined.height
    if n == 0:
        return empty
    success = float(joined["success"].sum()) / n
    base_success = float(joined["success_base"].sum()) / n
    return {
        "n": n,
        "success": round(success, 4),
        "base_success": round(base_success, 4),
        "delta_success": round(success - base_success, 4),
    }


def _spec_block(df: pl.DataFrame, env) -> dict:
    """tool_agree, call_agree and recalled recomputed against that step's env.action; a gen_call or env.action that does not parse counts as not agreeing."""
    spec = df.filter(pl.col("type") == "spec")
    n = spec.height
    if n == 0:
        return {"n": 0, "tool_agree": None, "call_agree": None, "recalled": None}

    env_rows = df.filter(pl.col("type") == "env").select(
        ["record_id", "step", pl.col("action").alias("env_action")])
    joined = spec.join(env_rows, on=["record_id", "step"], how="left")

    tool_agree_vals, call_agree_vals, recalled_vals = [], [], []
    for row in joined.iter_rows(named=True):
        action = row["env_action"]
        gen_call = row["gen_call"]
        gp = env.split_args(gen_call) if gen_call is not None else None
        ap = env.split_args(action) if action is not None else None
        if gp is not None and ap is not None:
            g_tool, g_args, _ = gp
            a_tool, a_args, _ = ap
            tool_agree_vals.append(g_tool == a_tool)
            call_agree_vals.append(env.build_call(g_tool, g_args) == env.build_call(a_tool, a_args))
        else:
            tool_agree_vals.append(False)
            call_agree_vals.append(False)
        recalled_vals.append(bool(gp is not None and action is not None and gp[0] in action))

    return {
        "n": n,
        "tool_agree": _rate(float(sum(tool_agree_vals)), n),
        "call_agree": _rate(float(sum(call_agree_vals)), n),
        "recalled": _rate(float(sum(recalled_vals)), n),
    }


def _render_report_md(fields: dict, rec: pl.DataFrame, brec: pl.DataFrame | None) -> str:
    run = fields["run"]
    lines = [
        f"# score {fields['stage_key']} — {fields['scored_stage']} at {fields['commit']}",
        "",
        f"n_records={run['n_records']} n_abort={run['n_abort']} success={run['success']}",
    ]
    if fields["baseline"] is not None:
        base = fields["baseline"]
        paired = fields["paired"]
        lines.append(f"baseline: success={base['success']}")
        lines.append(f"paired: n={paired['n']} delta_success={paired['delta_success']}")
    lines.append("")
    lines.append("## per task")
    lines.append("task_id | seed | success | base_success")
    lines.append("---|---|---|---")

    base_success_by_pair: dict[tuple, bool | None] = {}
    if brec is not None:
        for row in brec.iter_rows(named=True):
            base_success_by_pair[(row["task_id"], row["seed"])] = row["success"]

    for row in rec.sort(["task_id", "seed"]).iter_rows(named=True):
        base_success = base_success_by_pair.get((row["task_id"], row["seed"]))
        lines.append(f"{row['task_id']} | {row['seed']} | {row['success']} | {base_success}")
    return "\n".join(lines) + "\n"


def main(run_dir: Path) -> None:
    run_dir = Path(run_dir)
    cfg = schema.load_frozen(run_dir)
    env = open_env(cfg.data.env)

    scored = "inject" if "inject" in cfg._upstream else "sample"
    sec = cfg.inject if scored == "inject" else cfg.sample
    triples = requested_pairs(env, sec.split, sec.tasks, sec.n_tasks, sec.seeds)
    pairs = [(task_id, seed) for _, task_id, seed in triples]

    scored_dir = schema.run_dir_of(scored, cfg._upstream[scored], debug=cfg._debug)

    base_dir: Path | None = None
    if cfg.score.baseline is not None:
        base_key = cfg._upstream["baseline.sample"]
        base_dir = schema.referenced_run_dir("sample", base_key)
        scored_cfg = schema.load_frozen(scored_dir)
        if base_dir is not None and (base_dir / "settings.yaml").exists():
            base_cfg = schema.load_frozen(base_dir)
        else:
            raise ValueError(
                f"score_run: sample key {base_key} named by score.baseline: "
                "no run directory holding settings.yaml under either root")
        diff_field = _first_diff_field(scored_cfg, base_cfg)
        if diff_field is not None:
            raise ValueError(
                f"score_run: same-setup gate failed between {scored_dir} and {base_dir}: {diff_field} differs")
        done = trajectory_record.done_pairs(base_dir, pairs)
        missing = [pair for pair in pairs if pair not in done]
        if missing:
            raise ValueError(
                f"score_run: baseline {base_dir} is missing a done record for pair(s) {missing}")

    hb = registry.beat(run_dir, 0)
    hb.emit(0, len(pairs), "task")
    scored_frames: list[pl.DataFrame] = []
    base_frames: list[pl.DataFrame] = []
    for i, pair in enumerate(pairs, start=1):
        scored_frames.append(trajectory_record.read_dir(scored_dir, [pair]))
        if base_dir is not None:
            base_frames.append(trajectory_record.read_dir(base_dir, [pair]))
        hb.emit(i, len(pairs), "task")

    df = pl.concat(scored_frames) if scored_frames else pl.DataFrame(schema=trajectory_record.SCHEMA)
    bdf = None
    if base_dir is not None:
        bdf = pl.concat(base_frames) if base_frames else pl.DataFrame(schema=trajectory_record.SCHEMA)

    rec = _finals(df)
    brec = _finals(bdf) if bdf is not None else None

    run_block = _run_block(rec)
    baseline_block = _run_block(brec) if brec is not None else None
    paired_block = _paired_block(rec, brec)
    spec_block = _spec_block(df, env)

    n_tasks = len({task_id for task_id, _ in pairs})
    n_seeds = len({seed for _, seed in pairs})

    fields = {
        "version": VERSION,
        "stage_key": cfg._key,
        "scored_stage": scored,
        "scored_key": cfg._upstream[scored],
        "baseline_key": cfg._upstream.get("baseline.sample"),
        "commit": cfg._commit,
        "n_pairs": len(pairs),
        "n_tasks": n_tasks,
        "n_seeds": n_seeds,
        "run": run_block,
        "baseline": baseline_block,
        "paired": paired_block,
        "spec": spec_block,
    }

    _atomic_write_json(run_dir / "run_report.json", fields)
    (run_dir / "report.md").write_text(_render_report_md(fields, rec, brec))

    metrics = {
        "success": run_block["success"],
        "base_success": baseline_block["success"] if baseline_block is not None else None,
        "delta_success": paired_block["delta_success"],
        "spec_tool_agree": spec_block["tool_agree"],
        "spec_call_agree": spec_block["call_agree"],
        "n_records": run_block["n_records"],
    }
    metrics = {name: value for name, value in metrics.items() if value is not None}

    registry.write_done(
        run_dir, stage="score", key=cfg._key, commit=cfg._commit,
        counts={"records": run_block["n_records"], "tasks": n_tasks, "seeds": n_seeds, "specs": spec_block["n"]},
        versions=cfg._versions, metrics=metrics, report="report.md",
    )
    hb.finish()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()
    main(Path(args.run_dir))
