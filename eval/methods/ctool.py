"""Fit the temperature and theta on the val rows at the risk targets, freeze theta, report on the test rows, and write the fired rows."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import polars as pl

from eval.utils import probe_eval

VERSION = 1
PROBE_KIND = "classifier"


def match(pred: str, target: str, env) -> bool:
    """Class-name equality; `env` is ignored."""
    return pred == target


def _first_crossing(df: pl.DataFrame, theta: float) -> pl.DataFrame:
    """One row per event: task_id, split, fired, ok, depth, conf, label_pred, example_id — the first cut (depth ascending, tie-broken by example_id ascending) whose conf >= theta."""
    ordered = df.sort(["event_id", "depth", "example_id"])
    events = ordered.group_by("event_id", maintain_order=True).agg([
        pl.col("task_id").first(),
        pl.col("split").first(),
    ])
    hits = (
        ordered.filter(pl.col("conf") >= theta)
        .group_by("event_id", maintain_order=True)
        .agg([
            pl.col("example_id").first(),
            pl.col("depth").first(),
            pl.col("conf").first(),
            pl.col("label_pred").first(),
            pl.col("target").first(),
        ])
    )
    hits = hits.with_columns(
        (pl.col("label_pred") == pl.col("target")).alias("ok")
    ).drop("target")
    out = events.join(hits, on="event_id", how="left")
    out = out.with_columns([
        pl.col("conf").is_not_null().alias("fired"),
        pl.col("ok").fill_null(False),
    ])
    return out


def _agg(recs: pl.DataFrame) -> dict:
    """n, coverage, trig_acc, earliness, wrong_spec, each rounded to 4."""
    n = recs.height
    fired = recs.filter(pl.col("fired"))
    n_fired = fired.height
    coverage = (n_fired / n) if n else 0.0
    trig_acc = (int(fired["ok"].sum()) / n_fired) if n_fired else 0.0
    earliness = float((1 - fired["depth"]).mean()) if n_fired else 0.0
    wrong = fired.filter(~pl.col("ok")).height
    wrong_spec = (wrong / n) if n else 0.0
    return {
        "n": n,
        "coverage": round(float(coverage), 4),
        "trig_acc": round(float(trig_acc), 4),
        "earliness": round(float(earliness), 4),
        "wrong_spec": round(float(wrong_spec), 4),
    }


def _ci_stat(recs: pl.DataFrame) -> dict:
    a = _agg(recs)
    return {"coverage": a["coverage"], "trig_acc": a["trig_acc"], "earliness": a["earliness"]}


def report(pred_df: pl.DataFrame, cfg, ref, labels: list[str]) -> tuple[dict, pl.DataFrame | None]:
    """Fit temperature and theta on val, freeze on test, write the fired rows — the classifier shape of the probe report."""
    if ref is not None:
        raise ValueError("ctool.report: ref must be None for a classifier method")
    if not isinstance(labels, list):
        raise ValueError(f"ctool.report: labels must be a list, got {type(labels).__name__}")

    logits = np.asarray(pred_df["logits"].to_list(), dtype=np.float64)
    label_index = {name: i for i, name in enumerate(labels)}
    targets = pred_df["target"].to_list()
    missing = sorted({t for t in targets if t not in label_index})
    if missing:
        raise ValueError(f"ctool.report: target value(s) {missing} not in labels {labels}")
    y = np.array([label_index[t] for t in targets], dtype=np.int64)

    val_mask = (pred_df["split"] == "val").to_numpy()
    if not val_mask.any():
        raise ValueError("ctool.report: no rows with split == 'val' to fit the temperature on")
    T = probe_eval.fit_temperature(logits[val_mask], y[val_mask])

    probs = probe_eval.softmax(logits, T)
    conf = probs.max(axis=1).astype(np.float32)
    pred_idx = probs.argmax(axis=1)
    label_pred = np.array(labels, dtype=object)[pred_idx].tolist()

    work = pred_df.select(["event_id", "task_id", "split", "example_id", "depth", "target"]).with_columns([
        pl.Series("conf", conf),
        pl.Series("label_pred", label_pred),
    ])
    val_work = work.filter(pl.col("split") == "val")
    test_work = work.filter(pl.col("split") == "test")

    grid = []
    for theta in cfg.eval.theta_grid:
        recs = _first_crossing(val_work, theta)
        grid.append({"theta": theta, **_agg(recs)})

    chosen: dict[str, float | None] = {}
    for risk in cfg.eval.risk:
        candidates = [e for e in grid if e["trig_acc"] >= 1 - risk and e["coverage"] > 0]
        chosen[str(risk)] = max(candidates, key=lambda e: e["coverage"])["theta"] if candidates else None

    frozen: dict[str, dict] = {}
    for risk_str, theta in chosen.items():
        if theta is None:
            continue
        recs = _first_crossing(test_work, theta)
        ci = probe_eval.bootstrap_ci(recs, "task_id", _ci_stat, n=cfg.eval.bootstrap, seed=cfg.eval.bootstrap_seed)
        frozen[risk_str] = {**_agg(recs), "ci": ci}

    fires_frames = []
    for risk_str, theta in chosen.items():
        if theta is None:
            continue
        recs = _first_crossing(work, theta)
        fired = recs.filter(pl.col("fired"))
        fires_frames.append(fired.select([
            pl.lit(float(risk_str), dtype=pl.Float32).alias("risk"),
            pl.lit(float(theta), dtype=pl.Float32).alias("theta"),
            pl.col("split"),
            pl.col("event_id"),
            pl.col("example_id"),
            pl.col("conf").alias("score"),
            pl.col("depth"),
            pl.col("label_pred"),
        ]))
    if fires_frames:
        fires = pl.concat(fires_frames).select(list(probe_eval.FIRES_SCHEMA)).cast(probe_eval.FIRES_SCHEMA)
    else:
        fires = pl.DataFrame(schema=probe_eval.FIRES_SCHEMA)

    n_events_df = pred_df.group_by("split").agg(pl.col("event_id").n_unique().alias("n"))
    n_events = dict(zip(n_events_df["split"].to_list(), n_events_df["n"].to_list()))

    fields = {
        "temperature": round(float(T), 4),
        "risk_targets": cfg.eval.risk,
        "grid": grid,
        "chosen": chosen,
        "frozen": frozen,
        "n_events": n_events,
    }
    return fields, fires


def main(run_dir: Path) -> None:
    probe_eval.run(run_dir, sys.modules[__name__])


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()
    main(Path(args.run_dir))
