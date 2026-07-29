#!/usr/bin/env python3
"""参数头三档档位表:从路由统计表(router_stats.md)生成 无参/选择/自由 档位与占比。

三档口径(2026-07-30 用户定):
  无参   工具从不带参数,分类头出名字即完整调用
  选择   参数出自上文封闭候选集,抽取/打分即可
  自由   参数现场编写,需生成式产线兜底

初裁规则(逐字命中率是候选集封闭性的代理指标,阈值 0.90):
  无参   参数数中位=0 且无命中率数据
  选择   逐字命中率 >= 0.90
  自由   逐字命中率 <  0.90
"""
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "bert_data" / "v2"
ENVS = ["tales", "appworld", "bfcl"]
THRESH = 0.90


def parse(md_text):
    rows = []
    for line in md_text.splitlines():
        m = re.match(r"\|\s*(.+?)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*([\d.]+|-)\s*\|", line)
        if m:
            hit = None if m.group(4) == "-" else float(m.group(4))
            rows.append((m.group(1), int(m.group(2)), int(m.group(3)), hit))
    return rows


def tier_of(hit):
    if hit is None:
        return "无参"
    return "选择" if hit >= THRESH else "自由"


def main():
    out = ["# 参数头三档档位表(由 param_tiers.py 从 router_stats.md 生成)",
           "",
           f"档位规则:无参=从不带参;选择=逐字命中率≥{THRESH};自由=<{THRESH}。",
           "命中率是候选集封闭性的代理指标,终裁待抽取头实测。",
           ""]
    grand = {"无参": [0, 0], "选择": [0, 0], "自由": [0, 0]}
    for env in ENVS:
        rows = parse((BASE / env / "router_stats.md").read_text())
        total_ev = sum(r[1] for r in rows)
        stat = {"无参": [0, 0], "选择": [0, 0], "自由": [0, 0]}
        free_tools = []
        for name, ev, _np, hit in rows:
            t = tier_of(hit)
            stat[t][0] += 1
            stat[t][1] += ev
            grand[t][0] += 1
            grand[t][1] += ev
            if t == "自由":
                free_tools.append(f"{name}(命中率{hit:.2f},{ev}事件)")
        out.append(f"## {env}(共 {total_ev} 事件)")
        out.append("")
        out.append("| 档位 | 工具数 | 事件数 | 事件占比 |")
        out.append("|---|---|---|---|")
        for t in ("无参", "选择", "自由"):
            n, e = stat[t]
            out.append(f"| {t} | {n} | {e} | {e/total_ev:.1%} |")
        out.append("")
        out.append("自由档明细:" + ("、".join(free_tools) if free_tools else "无"))
        out.append("")
    total_all = sum(v[1] for v in grand.values())
    out.append(f"## 三环境合计(共 {total_all} 事件)")
    out.append("")
    out.append("| 档位 | 工具数 | 事件数 | 事件占比 |")
    out.append("|---|---|---|---|")
    for t in ("无参", "选择", "自由"):
        n, e = grand[t]
        out.append(f"| {t} | {n} | {e} | {e/total_all:.1%} |")
    out.append("")
    (BASE / "PARAM_TIERS.md").write_text("\n".join(out))
    print("\n".join(out))


if __name__ == "__main__":
    main()
