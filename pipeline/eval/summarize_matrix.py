#!/usr/bin/env python3
"""四格矩阵汇总(规格 §6.4,纯标准库):把 12 个 run 的报告收成一张表。

读每个 run 目录:
- mtool / ctool: `REPLAY_REPORT.json` → 风险 0.05 档的 theta / coverage /
  trig_acc / earliness / wrong_spec,外加 n_events_test 与 prior_baseline_event_acc
- mext: `EXTRACT_REPORT.json` → overall 的 params_all_ok / full_call_ok
- cgen: `CALLGEN_REPORT.json` → params_all_ok / full_call_ok

报告文件缺席的格标 `PENDING`(不报错,方便边跑边看)。

用法:
  python3 pipeline/eval/summarize_matrix.py \\
    --runs-dir pipeline/runs --out pipeline/runs/MATRIX_REPORT.md
"""

import argparse
import json
from pathlib import Path

CELLS = ("mtool", "mext", "ctool", "cgen")
REPORT_OF = {"mtool": "REPLAY_REPORT.json", "ctool": "REPLAY_REPORT.json",
             "mext": "EXTRACT_REPORT.json", "cgen": "CALLGEN_REPORT.json"}
RISK = "0.05"


def fmt(v):
    return "-" if v is None else str(v)


def read_cell(run_dir, cell, risk):
    """-> (status, row_dict)。status ∈ {"OK","PENDING"}。"""
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
    return "OK", dict(theta=rep.get("theta"),
                      params_all_ok=rep.get("params_all_ok"),
                      full_call_ok=rep.get("full_call_ok"),
                      n_events_scored=rep.get("n_events_scored"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs-dir", required=True,
                    help="12 个 run 目录的父目录(pipeline/runs)")
    ap.add_argument("--out", required=True, help="输出 MATRIX_REPORT.md 路径")
    ap.add_argument("--prefix", default="c1", help="run_id 前缀(c1_<model>_<cell>)")
    ap.add_argument("--models", nargs="+", default=["q35", "q36", "gptoss"])
    ap.add_argument("--risk", default=RISK, help="读哪一档风险(默认 0.05)")
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

    md = ["# 四格矩阵汇总",
          f"- run 目录 {root};风险档 {args.risk};缺报告的格标 PENDING",
          f"- 模型 {' / '.join(args.models)};格 {' / '.join(CELLS)}",
          "",
          "| 模型 | 格 | run_id | 状态 | θ | coverage | trig_acc | earliness |"
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

    md += ["", "## 每模型的 test 规模与先验基线(取 tool 格报告)",
           "| 模型 | test 事件数 | 频率先验基线 |", "|---|---|---|"]
    for m in args.models:
        n, pr = per_model.get(m, (None, None))
        md.append(f"| {m} | {fmt(n)} | {fmt(pr)} |")
    md += ["", "口径:tool 格(mtool/ctool)四列来自 REPLAY_REPORT 的 "
           f"test_frozen[\"{args.risk}\"];参数格(mext/cgen)两列来自 "
           "EXTRACT_REPORT.overall / CALLGEN_REPORT,都是同一风险档触发点上的数。"]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(md) + "\n")
    n_ok = sum(1 for *_x, st, _d in rows if st == "OK")
    print(f"{out}: {n_ok}/{len(rows)} 格有报告")
    print("\n".join(md))


if __name__ == "__main__":
    main()
