"""Render the backbone x method x risk table from the registry's eval rows, grouped by sweep parent, mean and spread over each group's runs.
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


def _backbone_of(all_rows: list[dict], row: dict) -> str:
    """An eval row's diff never carries models.probe (STAGES["eval"]'s projection is probe.method plus eval),
    so the backbone is read off the train row the eval run's own meta.json names."""
    meta_path = Path(row["dir"]) / "meta.json"
    if not meta_path.exists():
        return "?"
    meta = json.loads(meta_path.read_text())
    train_key = (meta.get("upstream") or {}).get("train")
    if train_key is None:
        return "?"
    for other in all_rows:
        if other["stage"] == "train" and other.get("key") == train_key:
            diff = other.get("diff") or {}
            return diff.get("models.probe", schema.SECTION_CLASSES["models"]().probe)
    return "?"


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


def table(workflow: str | None = None, out: Path | None = None) -> str:
    """The backbone x method x risk table over every eval row of the (non-debug) registry, grouped by sweep parent."""
    all_rows = registry.ls(workflow, debug=False)
    eval_rows = [row for row in all_rows if row["stage"] == "eval"]

    groups: dict[str, list[dict]] = {}
    for row in eval_rows:
        group_key = row.get("parent") or row.get("setting")
        groups.setdefault(group_key, []).append(row)

    table_rows = []
    for members in groups.values():
        backbone = _backbone_of(all_rows, members[0])
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
