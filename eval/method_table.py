"""Render the backbone x method x risk table from the registry's eval rows, one group per setting, mean and spread over each group's runs.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

from eval.utils import probe_eval
from experimental_settings import schema
from jobs import registry

_COLUMNS = (
    "backbone", "method", "risk", "n", "coverage", "trig_acc", "earliness", "wrong_spec",
    "tool_ok", "params_all_ok", "full_call_ok", "runs", "status",
)


def _method_of(row: dict) -> str:
    diff = row.get("diff") or {}
    return diff.get("probe.method", schema.SECTION_CLASSES["probe"]().method)


def _backbone_of(row: dict) -> str:
    """An eval row's diff never carries models.probe (STAGES["eval"]'s projection is probe.method plus eval),
    so the backbone is read off the train run directory the eval run's own meta.json names, located with
    schema.run_dir_of rather than through the registry listing (an eval's train reference may point at a
    directory the registry never recorded)."""
    meta_path = Path(row["dir"]) / "meta.json"
    if not meta_path.exists():
        return "?"
    meta = json.loads(meta_path.read_text())
    train_key = (meta.get("upstream") or {}).get("train")
    if train_key is None:
        return "?"
    debug = row.get("flags", {}).get("debug", False)
    train_dir = schema.run_dir_of("train", train_key, debug=debug)
    train_meta_path = train_dir / "meta.json"
    if not train_meta_path.exists():
        return "?"
    train_meta = json.loads(train_meta_path.read_text())
    diff = train_meta.get("diff") or {}
    return diff.get("models.probe", schema.SECTION_CLASSES["models"]().probe)


def _fmt(values: list[float | None], decimals: int = 4) -> str:
    values = [v for v in values if v is not None]
    if not values:
        return "-"
    if len(values) == 1:
        return f"{values[0]:.{decimals}f}"
    mean = statistics.fmean(values)
    spread = statistics.stdev(values)
    return f"{mean:.{decimals}f} ± {spread:.{decimals}f}"


def _fmt_n(values: list[int | None]) -> str:
    values = [v for v in values if v is not None]
    if not values:
        return "-"
    if len(values) == 1:
        return str(values[0])
    mean = statistics.fmean(values)
    spread = statistics.stdev(values)
    return f"{mean:.1f} ± {spread:.1f}"


def _render_md(rows: list[dict]) -> str:
    header = "| " + " | ".join(_COLUMNS) + " |"
    sep = "|" + "---|" * len(_COLUMNS)
    lines = ["# eval matrix: backbone x method x risk", "", header, sep]
    for row in rows:
        lines.append("| " + " | ".join(str(row[name]) for name in _COLUMNS) + " |")
    return "\n".join(lines) + "\n"


def table(workflow: str | None = None, out: Path | None = None, *, debug: bool = False) -> str:
    """The backbone x method x risk table over the registry's eval rows, one group per (setting name,
    debug flag) pair (a sweep child's own full name, never its parent), with debug rows included when
    debug is True. registry.ls(workflow, debug=True) drops the debug filter rather than selecting debug
    rows, so it returns both a --debug walk's rows and any non-debug run of the same setting; keying each
    group on the row's own debug flag as well as its setting name keeps those two runs in separate groups
    instead of averaging one real run and one debug run of the same setting into a single cell."""
    all_rows = registry.ls(workflow, debug=debug)
    eval_rows = [row for row in all_rows if row["stage"] == "eval"]

    groups: dict[tuple[str, bool], list[dict]] = {}
    for row in eval_rows:
        groups.setdefault((row["setting"], row["flags"]["debug"]), []).append(row)

    table_rows = []
    for members in groups.values():
        backbone = _backbone_of(members[0])
        method = _method_of(members[0])

        reports = []
        for row in members:
            report_path = Path(row["dir"]) / "probe_report.json"
            reports.append(probe_eval.read_report(Path(row["dir"]))[0] if report_path.exists() else None)

        n_ready = sum(1 for r in reports if r is not None)
        m = len(members)
        status = "OK" if n_ready == m else f"PENDING {n_ready}/{m}"

        risks: list[float] = []
        for fields in reports:
            if fields is not None:
                for risk in fields["risk_targets"]:
                    if risk not in risks:
                        risks.append(risk)

        for risk in risks:
            risk_str = str(risk)
            n_vals: list[int | None] = []
            cov_vals: list[float | None] = []
            trig_vals: list[float | None] = []
            early_vals: list[float | None] = []
            wrong_vals: list[float | None] = []
            tool_vals: list[float | None] = []
            params_vals: list[float | None] = []
            full_vals: list[float | None] = []
            for fields in reports:
                if fields is None:
                    continue
                if fields["probe_kind"] == "classifier":
                    block = fields.get("frozen", {}).get(risk_str)
                    if block is not None:
                        n_vals.append(block["n"])
                        cov_vals.append(block["coverage"])
                        trig_vals.append(block["trig_acc"])
                        early_vals.append(block["earliness"])
                        wrong_vals.append(block["wrong_spec"])
                else:
                    block = fields.get("exact", {}).get(risk_str)
                    if block is not None:
                        n_vals.append(block["n"])
                        tool_vals.append(block["tool_ok"])
                        params_vals.append(block["params_all_ok"])
                        full_vals.append(block["full_call_ok"])

            table_rows.append({
                "backbone": backbone,
                "method": method,
                "risk": risk_str,
                "n": _fmt_n(n_vals),
                "coverage": _fmt(cov_vals),
                "trig_acc": _fmt(trig_vals),
                "earliness": _fmt(early_vals),
                "wrong_spec": _fmt(wrong_vals),
                "tool_ok": _fmt(tool_vals),
                "params_all_ok": _fmt(params_vals),
                "full_call_ok": _fmt(full_vals),
                "runs": str(m),
                "status": status,
            })

    md = _render_md(table_rows)
    if out is not None:
        Path(out).write_text(md)
    return md
