"""Shared by the three probe methods: read a train run's prediction rows and targets, bootstrap the confidence interval, and write and read the probe report."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable

import numpy as np
import polars as pl

from data import probe_output
from experimental_settings import schema
from jobs import registry

VERSION = 1

FIRES_SCHEMA: dict[str, pl.DataType] = {
    "risk": pl.Float32,
    "theta": pl.Float32,
    "split": pl.Utf8,
    "event_id": pl.Utf8,
    "example_id": pl.Utf8,
    "score": pl.Float32,
    "depth": pl.Float32,
    "label_pred": pl.Utf8,
}

IDENTITY_FIELDS: frozenset[str] = frozenset({
    "version", "method", "probe_kind", "stage_key", "train_key",
    "theta_from", "commit", "labels",
})


def _sha1(path: Path) -> str:
    """The sha1 of a file's bytes, for a consumed.json entry."""
    digest = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write_json(path: Path, obj: Any, *, indent: int = 2) -> None:
    path = Path(path)
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    tmp.write_text(json.dumps(obj, indent=indent, ensure_ascii=False))
    os.replace(tmp, path)


def write_report(run_dir: Path, fields: dict, fires: pl.DataFrame | None) -> None:
    """Write probe_report.json (json.dumps(..., indent=1)) and, when given, fires.parquet, each through a temporary name in the same directory and a rename."""
    run_dir = Path(run_dir)
    _atomic_write_json(run_dir / "probe_report.json", fields, indent=1)
    if fires is not None:
        fires_path = run_dir / "fires.parquet"
        tmp = fires_path.with_name(f"{fires_path.name}.tmp-{os.getpid()}")
        fires.write_parquet(tmp)
        os.replace(tmp, fires_path)


def read_report(run_dir: Path) -> tuple[dict, pl.DataFrame | None]:
    """Read probe_report.json and fires.parquet back together; raises when the json is missing or its recorded version is newer than this module's."""
    run_dir = Path(run_dir)
    report_path = run_dir / "probe_report.json"
    if not report_path.exists():
        raise ValueError(f"{report_path}: no probe report in this run directory")
    fields = json.loads(report_path.read_text())
    recorded = fields.get("version")
    if recorded is not None and recorded > VERSION:
        raise ValueError(
            f"{report_path}: recorded version {recorded} is newer than this module's VERSION {VERSION}")
    fires_path = run_dir / "fires.parquet"
    fires = pl.read_parquet(fires_path) if fires_path.exists() else None
    return fields, fires


def softmax(logits: "np.ndarray", temperature: float) -> "np.ndarray":
    """Softmax over the last axis of logits / temperature, numerically stabilised by subtracting the row max."""
    scaled = np.asarray(logits, dtype=np.float64) / temperature
    scaled = scaled - scaled.max(axis=-1, keepdims=True)
    exp = np.exp(scaled)
    return exp / exp.sum(axis=-1, keepdims=True)


def _mean_nll(logits: "np.ndarray", y: "np.ndarray", log_t: float) -> float:
    probs = softmax(logits, float(np.exp(log_t)))
    p_true = probs[np.arange(len(y)), y]
    return float(-np.log(np.clip(p_true, 1e-12, None)).mean())


def fit_temperature(logits: "np.ndarray", y: "np.ndarray") -> float:
    """Minimise the mean NLL over log T: an 81-point grid over [-4, 4], then a golden-section refinement inside the winning cell to a tolerance of 1e-6.

    Deterministic; a NumPy replacement for today's torch LBFGS fit, which `venv: any` forbids.
    """
    logits = np.asarray(logits, dtype=np.float64)
    y = np.asarray(y, dtype=np.int64)
    grid = np.linspace(-4.0, 4.0, 81)
    losses = [_mean_nll(logits, y, g) for g in grid]
    best_i = int(np.argmin(losses))
    lo = float(grid[max(best_i - 1, 0)])
    hi = float(grid[min(best_i + 1, len(grid) - 1)])

    gr = (5.0 ** 0.5 - 1.0) / 2.0
    c = hi - gr * (hi - lo)
    d = lo + gr * (hi - lo)
    fc = _mean_nll(logits, y, c)
    fd = _mean_nll(logits, y, d)
    while (hi - lo) > 1e-6:
        if fc < fd:
            hi, d, fd = d, c, fc
            c = hi - gr * (hi - lo)
            fc = _mean_nll(logits, y, c)
        else:
            lo, c, fc = c, d, fd
            d = lo + gr * (hi - lo)
            fd = _mean_nll(logits, y, d)
    log_t = (lo + hi) / 2.0
    return float(np.exp(log_t))


def bootstrap_ci(df: pl.DataFrame, group: str, stat: Callable[[pl.DataFrame], dict],
                  *, n: int, seed: int) -> dict[str, list[float]]:
    """Resample the distinct values of `group` with replacement `n` times and take today's sorted-index 2.5/97.5 bounds, rounded to 4."""
    rng = np.random.default_rng(seed)
    ids = sorted(df[group].unique().to_list())
    by_id = {value: df.filter(pl.col(group) == value) for value in ids}
    stats: dict[str, list[float]] = {}
    for _ in range(n):
        draws = rng.choice(np.array(ids, dtype=object), size=len(ids), replace=True)
        sample_df = pl.concat([by_id[d] for d in draws]) if len(draws) else df.clear()
        result = stat(sample_df)
        for name, value in result.items():
            stats.setdefault(name, []).append(value)
    ci: dict[str, list[float]] = {}
    for name, values in stats.items():
        values = sorted(values)
        lo = values[int(n * 0.025)]
        hi = values[int(n * 0.975)]
        ci[name] = [round(float(lo), 4), round(float(hi), 4)]
    return ci


def _render_report_md(fields: dict) -> str:
    """Render probe_report.json as report.md; computes nothing itself."""
    lines = [
        f"# eval {fields['stage_key']} — {fields['method']} ({fields['probe_kind']}) at {fields['commit']}",
        "",
    ]
    if fields["probe_kind"] == "classifier":
        lines.append(f"temperature: {fields['temperature']}")
        lines.append("")
        for risk in fields["risk_targets"]:
            risk_str = str(risk)
            theta = fields.get("chosen", {}).get(risk_str)
            block = fields.get("frozen", {}).get(risk_str)
            if theta is None or block is None:
                lines.append(f"- risk {risk_str}: no theta on the grid met the constraint")
                continue
            ci = block.get("ci", {})
            lines.append(
                f"- risk {risk_str}: theta={theta} "
                f"coverage={block['coverage']} (CI {ci.get('coverage')}) "
                f"trig_acc={block['trig_acc']} (CI {ci.get('trig_acc')}) "
                f"earliness={block['earliness']} (CI {ci.get('earliness')}) "
                f"wrong_spec={block['wrong_spec']} n={block['n']}"
            )
    else:
        for risk in fields["risk_targets"]:
            risk_str = str(risk)
            theta_used = fields.get("theta_used", {}).get(risk_str)
            block = fields.get("exact", {}).get(risk_str, {})
            lines.append(
                f"- risk {risk_str}: theta_used={theta_used} "
                f"tool_ok={block.get('tool_ok')} params_all_ok={block.get('params_all_ok')} "
                f"full_call_ok={block.get('full_call_ok')} n={block.get('n')}"
            )
    lines.append("")
    lines.append("## events per split")
    for split, count in fields.get("n_events", {}).items():
        lines.append(f"- {split}: {count}")
    return "\n".join(lines) + "\n"


def _classifier_metrics(fields: dict) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for risk_str, block in fields.get("frozen", {}).items():
        for name in ("coverage", "trig_acc", "earliness", "wrong_spec"):
            value = block.get(name)
            if value is not None:
                metrics[f"{name}@{risk_str}"] = value
    return metrics


def _generator_metrics(fields: dict) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for risk_str, block in fields.get("exact", {}).items():
        for name in ("tool_ok", "params_all_ok", "full_call_ok"):
            value = block.get(name)
            if value is not None:
                metrics[f"{name}@{risk_str}"] = value
    return metrics


def run(run_dir: Path, method) -> None:
    """Drive one eval run: load the frozen setting, read the predictions, call the method's report hook, write the report, and mark done."""
    run_dir = Path(run_dir)
    cfg = schema.load_frozen(run_dir)
    hb = registry.beat(run_dir, 0)

    train_dir = schema.run_dir_of("train", cfg._upstream["train"], debug=cfg._debug)
    pred_df = probe_output.read(train_dir / "predictions.parquet")
    methods_found = sorted(pred_df["method"].unique().to_list())
    if methods_found != [cfg.probe.method]:
        raise ValueError(
            f"{train_dir / 'predictions.parquet'}: method column holds {methods_found}, "
            f"expected only [{cfg.probe.method!r}]")

    total_events = pred_df["event_id"].n_unique()
    hb.emit(0, total_events, "item")

    train_meta = json.loads((train_dir / "meta.json").read_text())
    labels = train_meta["stage_extra"]["labels"]

    kind = method.PROBE_KIND
    ref = None
    ref_eval_dir: Path | None = None
    if kind == "generator":
        ref_key = cfg._upstream["theta_from.eval"]
        ref_eval_dir = schema.run_dir_of("eval", ref_key, debug=False)
        if not (ref_eval_dir / "done.json").exists():
            raise ValueError(
                f"{ref_eval_dir}: the referenced classifier eval (theta_from) has no done.json")
        ref = read_report(ref_eval_dir)
        if ref[0]["risk_targets"] != cfg.eval.risk:
            raise ValueError(
                f"eval.risk {cfg.eval.risk} differs from the referenced report's "
                f"risk_targets {ref[0]['risk_targets']}")

        ref_meta = json.loads((ref_eval_dir / "meta.json").read_text())
        ref_train_key = ref_meta["upstream"]["train"]
        ref_train_dir = schema.run_dir_of("train", ref_train_key, debug=False)
        ref_train_meta = json.loads((ref_train_dir / "meta.json").read_text())
        ref_build_key = ref_train_meta["upstream"]["build"]
        own_build_key = train_meta["upstream"]["build"]
        if ref_build_key != own_build_key:
            raise ValueError(
                f"the referenced classifier eval's train run has build key {ref_build_key!r}, "
                f"this eval's own train run has build key {own_build_key!r}")

    fields, fires = method.report(pred_df, cfg, ref, labels)

    clash = sorted(set(fields) & IDENTITY_FIELDS)
    if clash:
        raise ValueError(
            f"method.report() returned identity field(s) {clash}, which probe_eval.run assembles itself")

    identity = {
        "version": VERSION,
        "method": cfg.probe.method,
        "probe_kind": kind,
        "stage_key": cfg._key,
        "train_key": cfg._upstream["train"],
        "theta_from": cfg._upstream.get("theta_from.eval"),
        "commit": cfg._commit,
        "labels": labels,
    }
    full_fields = {**identity, **fields}

    write_report(run_dir, full_fields, fires)
    (run_dir / "report.md").write_text(_render_report_md(full_fields))

    consumed = [{
        "path": str(train_dir / "predictions.parquet"),
        "sha1": _sha1(train_dir / "predictions.parquet"),
        "n_rows": pred_df.height,
    }]
    if kind == "generator":
        consumed.append({
            "path": str(ref_eval_dir / "probe_report.json"),
            "sha1": _sha1(ref_eval_dir / "probe_report.json"),
            "n_rows": None,
        })
        ref_fires_height = ref[1].height if ref[1] is not None else 0
        consumed.append({
            "path": str(ref_eval_dir / "fires.parquet"),
            "sha1": _sha1(ref_eval_dir / "fires.parquet"),
            "n_rows": ref_fires_height,
        })
    _atomic_write_json(run_dir / "consumed.json", consumed)

    metrics = _classifier_metrics(full_fields) if kind == "classifier" else _generator_metrics(full_fields)
    registry.write_done(
        run_dir, stage="eval", key=cfg._key, commit=cfg._commit,
        counts={
            "rows": pred_df.height,
            "events": total_events,
            "fires": fires.height if fires is not None else 0,
        },
        versions=cfg._versions, metrics=metrics, report="report.md",
    )
    hb.finish()
