"""The eval program of every probe method: the PROBE_KIND and MATCH_VERSION tables, the three match functions, the classifier and the generator report, and the driver that reads a train run's prediction rows and writes the probe report."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable

import numpy as np
import polars as pl

from data import probe_output
from data.environments import open_env
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

# The report shape each probe method is scored under. experimental_settings/schema.py reads
# this table as source text (3.3) for the stage table's upstream rule and the loader's
# required-field rule, and run() reads it to pick the report below.
PROBE_KIND = {"ctool": "classifier", "cgen": "generator", "cparam": "generator"}

# The version of each method's match function. A train run folds the match version of the one
# method it trains and an inject run that of its scoring probe, so a change to a report, to the
# driver or to any other method's match leaves those runs' keys where they are, while a change
# to one method's match re-keys exactly the runs whose validation metric it decides.
MATCH_VERSION = {"ctool": 1, "cgen": 1, "cparam": 1}

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


# ---------------------------------------------------------------------------
# The match functions, offered to train/methods/<m>.py for its validation metric (2.6).
# ---------------------------------------------------------------------------


def match_ctool(pred: str, target: str, env) -> bool:
    """Class-name equality; `env` is ignored."""
    return pred == target


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


def _match_call(method: str, pred: str, target: str, env) -> dict[str, bool]:
    """tool_ok, params_all_ok and full_call_ok of two whole calls, both sides normalised through env.split_args — the one comparison both generator methods are scored by.

    TODO(gyb, 2026-09-18): owner ruling — the matching rule behind tool_ok,
    params_all_ok and full_call_ok, as this function computes them today, is
    open. The owner decides it later; no logic here changes for this ruling.

    Today's build drops the `noparam` short-circuit: params_all_ok is the union count over
    both sides' arguments, so a spurious argument on a no-argument target counts wrong
    instead of being automatically true.
    """
    t = env.split_args(target)
    if t is None:
        raise ValueError(f"match_{method}: target {target!r} does not parse via env.split_args")
    t_tool, t_args, _ = t

    p = env.split_args(pred)
    if p is None:
        return {"tool_ok": False, "params_all_ok": False, "full_call_ok": False}
    p_tool, p_args, _ = p

    tool_ok = p_tool == t_tool
    params_all_ok = _params_all_ok(t_args, p_args)
    return {"tool_ok": tool_ok, "params_all_ok": params_all_ok,
            "full_call_ok": tool_ok and params_all_ok}


def match_cgen(pred: str, target: str, env) -> dict[str, bool]:
    """tool_ok, params_all_ok and full_call_ok of the generated call against the target, both sides normalised through env.split_args."""
    return _match_call("cgen", pred, target, env)


def match_cparam(pred: str, target: str, env) -> dict[str, bool]:
    """The same three keys over two whole calls; callers hand this two whole calls, prepending the true tool themselves, because an argument string alone cannot be parsed by env.split_args."""
    return _match_call("cparam", pred, target, env)


# ---------------------------------------------------------------------------
# The two report shapes (1.4), one per PROBE_KIND.
# ---------------------------------------------------------------------------


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


def _classifier_ci_stat(recs: pl.DataFrame) -> dict:
    a = _agg(recs)
    return {"coverage": a["coverage"], "trig_acc": a["trig_acc"], "earliness": a["earliness"]}


def _n_events(pred_df: pl.DataFrame) -> dict:
    """Distinct event_id per split of the prediction frame the report was handed."""
    counted = pred_df.group_by("split").agg(pl.col("event_id").n_unique().alias("n"))
    return dict(zip(counted["split"].to_list(), counted["n"].to_list()))


def report_classifier(method: str, pred_df: pl.DataFrame, cfg, ref,
                      labels: list[str]) -> tuple[dict, pl.DataFrame]:
    """Fit temperature and theta on val, freeze on test, write the fired rows — the classifier shape of the probe report, which holds for any classifier probe."""
    if ref is not None:
        raise ValueError(f"{method}: ref must be None for a classifier method")
    if not isinstance(labels, list):
        raise ValueError(f"{method}: labels must be a list, got {type(labels).__name__}")

    logits = np.asarray(pred_df["logits"].to_list(), dtype=np.float64)
    label_index = {name: i for i, name in enumerate(labels)}
    targets = pred_df["target"].to_list()
    missing = sorted({t for t in targets if t not in label_index})
    if missing:
        raise ValueError(f"{method}: target value(s) {missing} not in labels {labels}")
    y = np.array([label_index[t] for t in targets], dtype=np.int64)

    val_mask = (pred_df["split"] == "val").to_numpy()
    if not val_mask.any():
        raise ValueError(f"{method}: no rows with split == 'val' to fit the temperature on")
    T = fit_temperature(logits[val_mask], y[val_mask])

    probs = softmax(logits, T)
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
        ci = bootstrap_ci(recs, "task_id", _classifier_ci_stat,
                          n=cfg.eval.bootstrap, seed=cfg.eval.bootstrap_seed)
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
        fires = pl.concat(fires_frames).select(list(FIRES_SCHEMA)).cast(FIRES_SCHEMA)
    else:
        fires = pl.DataFrame(schema=FIRES_SCHEMA)

    fields = {
        "temperature": round(float(T), 4),
        "risk_targets": cfg.eval.risk,
        "grid": grid,
        "chosen": chosen,
        "frozen": frozen,
        "n_events": _n_events(pred_df),
    }
    return fields, fires


def _generator_stat(df: pl.DataFrame) -> dict:
    n = df.height
    if n == 0:
        return {"tool_ok": 0.0, "params_all_ok": 0.0, "full_call_ok": 0.0}
    return {
        "tool_ok": float(np.mean(df["tool_ok"].to_list())),
        "params_all_ok": float(np.mean(df["params_all_ok"].to_list())),
        "full_call_ok": float(np.mean(df["full_call_ok"].to_list())),
    }


def _generator_scores(method: str, test: pl.DataFrame, fires_risk: pl.DataFrame,
                      env) -> tuple[pl.DataFrame, list[bool], list[bool], list[bool]]:
    """The one step of the generator report the method owns: join the test rows to the fired rows and score each joined row.

    cgen parses the whole generated call, so all three numbers come out of one match call.
    cparam generates the arguments alone, so its tool_ok is the fired label against the
    prediction row's own tool column and its params_all_ok comes from a match call over the
    two calls rebuilt as tool + "(" + the argument string.
    """
    if method == "cgen":
        joined = test.join(fires_risk.select("example_id"), on="example_id", how="inner")
        results = [match_cgen(row["text_pred"], row["target"], env)
                   for row in joined.iter_rows(named=True)]
        return (joined,
                [r["tool_ok"] for r in results],
                [r["params_all_ok"] for r in results],
                [r["full_call_ok"] for r in results])
    if method == "cparam":
        # test's own prediction rows already carry a (null) label_pred column, so the
        # fired label is renamed on the way in rather than joined under the same name.
        fired = fires_risk.select(["example_id", pl.col("label_pred").alias("fired_label")])
        joined = test.join(fired, on="example_id", how="inner")
        tool_ok_vals, params_vals, full_vals = [], [], []
        for row in joined.iter_rows(named=True):
            tool = row["tool"]
            tool_ok = row["fired_label"] == tool
            params_all_ok = match_cparam(
                tool + "(" + row["text_pred"], tool + "(" + row["target"], env)["params_all_ok"]
            tool_ok_vals.append(tool_ok)
            params_vals.append(params_all_ok)
            full_vals.append(tool_ok and params_all_ok)
        return joined, tool_ok_vals, params_vals, full_vals
    raise ValueError(
        f"{method}: no generator scoring step; the generator methods are 'cgen' and 'cparam'")


def report_generator(method: str, pred_df: pl.DataFrame, cfg, ref,
                     labels: list[str] | None) -> tuple[dict, None]:
    """Join the test predictions to the referenced classifier's fired rows per risk target, and report exact match at the frozen theta over the joined rows."""
    if not (isinstance(ref, tuple) and len(ref) == 2):
        raise ValueError(f"{method}: ref must be a (fields, fires) tuple, got {type(ref).__name__}")
    ref_fields, ref_fires = ref
    if labels is not None:
        raise ValueError(f"{method}: labels must be None for a generator method, got {labels!r}")

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
        joined, tool_ok_vals, params_vals, full_vals = _generator_scores(
            method, test, fires_risk, env)
        n = joined.height
        joined = joined.with_columns([
            pl.Series("tool_ok", tool_ok_vals),
            pl.Series("params_all_ok", params_vals),
            pl.Series("full_call_ok", full_vals),
        ])
        ci = bootstrap_ci(joined, "task_id", _generator_stat,
                          n=cfg.eval.bootstrap, seed=cfg.eval.bootstrap_seed) if n else None
        exact[risk_str] = {
            "tool_ok": round(float(np.mean(tool_ok_vals)), 4) if n else None,
            "params_all_ok": round(float(np.mean(params_vals)), 4) if n else None,
            "full_call_ok": round(float(np.mean(full_vals)), 4) if n else None,
            "n": n,
            "ci": ci,
        }

    fields = {
        "risk_targets": cfg.eval.risk,
        "theta_used": theta_used,
        "exact": exact,
        "n_events": _n_events(pred_df),
    }
    return fields, None


def report(method: str, pred_df: pl.DataFrame, cfg, ref,
           labels: list[str] | None) -> tuple[dict, pl.DataFrame | None]:
    """The report of the method's PROBE_KIND: the classifier shape for a classifier, the generator shape for a generator."""
    kind = PROBE_KIND[method]
    if kind == "classifier":
        return report_classifier(method, pred_df, cfg, ref, labels)
    if kind == "generator":
        return report_generator(method, pred_df, cfg, ref, labels)
    raise ValueError(
        f"{method}: PROBE_KIND {kind!r} has no report shape; the shapes are "
        f"'classifier' and 'generator'")


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


def run(run_dir: Path) -> None:
    """Drive one eval run: load the frozen setting, read the predictions, call the report of the setting's probe method, write the report, and mark done."""
    run_dir = Path(run_dir)
    cfg = schema.load_frozen(run_dir)
    method = cfg.probe.method
    if method not in PROBE_KIND:
        raise ValueError(
            f"probe.method {method!r} is not a key of PROBE_KIND; it holds {sorted(PROBE_KIND)}")
    hb = registry.beat(run_dir, 0)

    train_dir = schema.run_dir_of("train", cfg._upstream["train"], debug=cfg._debug)
    pred_df = probe_output.read(train_dir / "predictions.parquet")
    methods_found = sorted(pred_df["method"].unique().to_list())
    if methods_found != [method]:
        raise ValueError(
            f"{train_dir / 'predictions.parquet'}: method column holds {methods_found}, "
            f"expected only [{method!r}]")

    total_events = pred_df["event_id"].n_unique()
    hb.emit(0, total_events, "item")

    train_meta = json.loads((train_dir / "meta.json").read_text())
    labels = train_meta["stage_extra"]["labels"]

    kind = PROBE_KIND[method]
    ref = None
    ref_eval_dir: Path | None = None
    if kind == "generator":
        ref_key = cfg._upstream["theta_from.eval"]
        ref_eval_dir = schema.referenced_run_dir("eval", ref_key)
        if ref_eval_dir is None or not (ref_eval_dir / "done.json").exists():
            raise ValueError(
                f"eval key {ref_key} at {ref_eval_dir}: the referenced classifier eval "
                "(theta_from) has no done.json")
        ref = read_report(ref_eval_dir)
        if ref[0]["risk_targets"] != cfg.eval.risk:
            raise ValueError(
                f"eval.risk {cfg.eval.risk} differs from the referenced report's "
                f"risk_targets {ref[0]['risk_targets']}")

        ref_meta = json.loads((ref_eval_dir / "meta.json").read_text())
        ref_train_key = ref_meta["upstream"]["train"]
        ref_train_dir = schema.referenced_run_dir("train", ref_train_key)
        ref_train_meta = json.loads((ref_train_dir / "meta.json").read_text())
        ref_build_key = ref_train_meta["upstream"]["build"]
        own_build_key = train_meta["upstream"]["build"]
        if ref_build_key != own_build_key:
            raise ValueError(
                f"the referenced classifier eval's train run has build key {ref_build_key!r}, "
                f"this eval's own train run has build key {own_build_key!r}")

    fields, fires = report(method, pred_df, cfg, ref, labels)

    clash = sorted(set(fields) & IDENTITY_FIELDS)
    if clash:
        raise ValueError(
            f"the {method} report returned identity field(s) {clash}, which probe_eval.run assembles itself")

    identity = {
        "version": VERSION,
        "method": method,
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


def main(run_dir: Path) -> None:
    run(run_dir)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()
    main(Path(args.run_dir))
