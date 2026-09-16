#!/usr/bin/env python3
"""Matrix summary (spec §6.4, pure standard library): collect a batch of run reports into one table (model × cell).

Reads each run directory:
- mtool / ctool: `REPLAY_REPORT.json` → theta / coverage / trig_acc / earliness / wrong_spec at the risk-0.05 tier,
  plus n_events_test and prior_baseline_event_acc
- mext: `EXTRACT_REPORT.json` → overall's params_all_ok / full_call_ok
- cgen: `CALLGEN_REPORT.json` → params_all_ok / full_call_ok
- cparam: the **pred_tool block** of `PARAM_REPORT.json` → theta / params_all_ok /
  full_call_ok / n_events_scored (pred_tool = tool name predicted by feeding the classification head, i.e. system B's
  real-world convention; the gt_tool block in the same report feeds the ground-truth tool name and does not go into the matrix)

Cells whose report file is missing are marked `PENDING` (not an error, so you can check while runs are still going).

Usage:
  python3 pipeline/eval/summarize_matrix.py \\
    --runs-dir pipeline/runs --out pipeline/runs/MATRIX_REPORT.md
"""

import argparse
import json
from pathlib import Path

CELLS = ("mtool", "mext", "ctool", "cgen", "cparam")
REPORT_OF = {"mtool": "REPLAY_REPORT.json", "ctool": "REPLAY_REPORT.json",
             "mext": "EXTRACT_REPORT.json", "cgen": "CALLGEN_REPORT.json",
             "cparam": "PARAM_REPORT.json"}
RISK = "0.05"


def fmt(v):
    return "-" if v is None else str(v)


def read_cell(run_dir, cell, risk):
    """-> (status, row_dict). status ∈ {"OK","PENDING"}."""
    p = run_dir / REPORT_OF[cell]
    if not p.exists():
        return "PENDING", {}
    rep = json.loads(p.read_text())
    if cell in ("mtool", "ctool"):
        fr = (rep.get("test_frozen") or {}).get(risk)
        row = dict(theta=None, coverage=None, trig_acc=None, earliness=None,
                   wrong_spec=None,
                   n_events_test=rep.get("n_events_test"),
                   prior=rep.get("prior_baseline_event_acc"))
        if fr:
            row.update(theta=fr.get("theta"), coverage=fr.get("coverage"),
                       trig_acc=fr.get("trig_acc"),
                       earliness=fr.get("earliness"),
                       wrong_spec=fr.get("wrong_spec"))
        return "OK", row
    if cell == "mext":
        ov = rep.get("overall") or {}
        return "OK", dict(theta=rep.get("theta"),
                          params_all_ok=ov.get("params_all_ok"),
                          full_call_ok=ov.get("full_call_ok"),
                          n_events_scored=rep.get("n_events_scored"))
    if cell == "cparam":
        # PARAM_REPORT has two blocks: gt_tool (fed the ground-truth tool name) and pred_tool (fed the classification head's
        # argmax). The matrix always takes pred_tool -- that is system B's (ctool + cparam) real-world
        # convention; gt_tool is only kept in the report for human comparison. This must branch explicitly: falling into the else
        # branch below would take params_all_ok/full_call_ok from the top-level keys, but the top level has neither key,
        # so rep.get() is all None → the whole row is "-" but the status column still says OK (extending §5 #15).
        pt = rep.get("pred_tool") or {}
        return "OK", dict(theta=pt.get("theta"),
                          params_all_ok=pt.get("params_all_ok"),
                          full_call_ok=pt.get("full_call_ok"),
                          n_events_scored=pt.get("n_events_scored"))
    return "OK", dict(theta=rep.get("theta"),
                      params_all_ok=rep.get("params_all_ok"),
                      full_call_ok=rep.get("full_call_ok"),
                      n_events_scored=rep.get("n_events_scored"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs-dir", required=True,
                    help="parent dir of the 12 run dirs (pipeline/runs)")
    ap.add_argument("--out", required=True, help="output path for MATRIX_REPORT.md")
    ap.add_argument("--prefix", default="c1", help="run_id prefix (c1_<model>_<cell>)")
    ap.add_argument("--models", nargs="+", default=["q35", "q36", "gptoss"])
    ap.add_argument("--risk", default=RISK, help="which risk tier to read (default 0.05)")
    args = ap.parse_args()

    root = Path(args.runs_dir)
    rows, per_model = [], {}
    for m in args.models:
        for c in CELLS:
            rid = f"{args.prefix}_{m}_{c}"
            st, d = read_cell(root / rid, c, args.risk)
            rows.append((m, c, rid, st, d))
            if c in ("mtool", "ctool") and st == "OK" and m not in per_model:
                per_model[m] = (d.get("n_events_test"), d.get("prior"))

    md = ["# matrix summary",
          f"- run dir {root}; run_id prefix {args.prefix}; risk tier {args.risk}; "
          "cells with no report are marked PENDING",
          f"- models {' / '.join(args.models)}; cells {' / '.join(CELLS)}",
          "",
          "| model | cell | run_id | status | θ | coverage | trig_acc | earliness |"
          " wrong_spec | params_all_ok | full_call_ok |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for m, c, rid, st, d in rows:
        if st != "OK":
            md.append(f"| {m} | {c} | {rid} | PENDING | - | - | - | - | - | - | - |")
            continue
        md.append(
            f"| {m} | {c} | {rid} | OK | {fmt(d.get('theta'))} | "
            f"{fmt(d.get('coverage'))} | {fmt(d.get('trig_acc'))} | "
            f"{fmt(d.get('earliness'))} | {fmt(d.get('wrong_spec'))} | "
            f"{fmt(d.get('params_all_ok'))} | {fmt(d.get('full_call_ok'))} |")

    md += ["", "## per-model test scale and prior baseline (from the tool-cell reports)",
           "| model | test event count | frequency prior baseline |", "|---|---|---|"]
    for m in args.models:
        n, pr = per_model.get(m, (None, None))
        md.append(f"| {m} | {fmt(n)} | {fmt(pr)} |")
    md += ["", "settings: the four columns for the tool cells (mtool/ctool) come from REPLAY_REPORT's "
           f"test_frozen[\"{args.risk}\"]; the two columns for the param cells (mext/cgen/cparam) come from "
           "EXTRACT_REPORT.overall / CALLGEN_REPORT / PARAM_REPORT.pred_tool, "
           "all numbers at the same risk tier's fire point. cparam takes the pred_tool block (tool name fed "
           "to the classification head for prediction); the gt_tool block in the same report, which feeds "
           "the ground-truth tool name, is not included in this table."]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(md) + "\n")
    n_ok = sum(1 for *_x, st, _d in rows if st == "OK")
    print(f"{out}: {n_ok}/{len(rows)} cells have a report")
    print("\n".join(md))


if __name__ == "__main__":
    main()
