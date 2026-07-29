#!/usr/bin/env python3
"""fig1 8B 全矩阵聚合(30 run × 10 集)。

第一行规矩:旧代码 L 编号 → 正典编号重映射(benchmark_design/L3L4_and_metrics_draft.md §0)。
旧 L0=完全重复 → 正典 L2;旧 L1=近重复 → 正典 L2-;旧 L2=部分相似 → 正典 L1。
"""
import json, glob, os, statistics as st

REMAP = {"L0": "L2(完全重复)", "L1": "L2-(近重复)", "L2": "L1(部分相似)"}
CANON_ORDER = ["L1(部分相似)", "L2-(近重复)", "L2(完全重复)"]
RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")

runs = {}  # (canon, setting, seed) -> [episode dicts sorted by idx]
for f in glob.glob(os.path.join(RES, "8bfull_*.jsonl")):
    base = os.path.basename(f)[len("8bfull_"):-len(".jsonl")]
    old_l, setting, seed = base.split("_")
    eps = [json.loads(l) for l in open(f)]
    eps.sort(key=lambda e: e["episode_idx"])
    runs[(REMAP[old_l], setting, seed)] = eps

def agg(canon, setting):
    vals = {"succ": [], "wall": [], "tout": [], "tin": [], "steps": []}
    for (c, s, seed), eps in runs.items():
        if c == canon and s == setting:
            vals["succ"] += [e["success"] for e in eps]
            vals["wall"] += [e["wall_s"] for e in eps]
            vals["tout"] += [e["tokens_out"] for e in eps]
            vals["tin"] += [e["tokens_in"] for e in eps]
            vals["steps"] += [e["steps"] for e in eps]
    n = len(vals["succ"])
    return {"n": n, "succ": sum(vals["succ"]) / n,
            "wall": st.mean(vals["wall"]), "tout": st.mean(vals["tout"]),
            "tin": st.mean(vals["tin"]), "steps": st.mean(vals["steps"])}

def curve(canon, setting, key):
    """逐集均值(5 种子平均)——成本随集数曲线。"""
    out = []
    for idx in range(10):
        pts = [eps[idx][key] for (c, s, _), eps in runs.items()
               if c == canon and s == setting and len(eps) > idx]
        out.append(st.mean(pts))
    return out

lines = ["# fig1 8B 全矩阵聚合(正典编号,ALFWorld,5 种子×10 集)\n",
         "旧→正典重映射已执行:旧L0→L2完全重复 / 旧L1→L2-近重复 / 旧L2→L1部分相似\n"]

lines.append("## 档位汇总(mem vs nomem,均值)\n")
lines.append("| 正典档 | 成功率 mem/nomem | 墙钟s mem/nomem | tok_out mem/nomem | tok_in mem/nomem | 步数 mem/nomem |")
lines.append("|---|---|---|---|---|---|")
ladder = []
for canon in CANON_ORDER:
    m, nm = agg(canon, "mem"), agg(canon, "nomem")
    dw = (m["wall"] - nm["wall"]) / nm["wall"] * 100
    ds = (m["succ"] - nm["succ"]) * 100
    ladder.append((canon, dw, ds))
    lines.append(f"| {canon} | {m['succ']:.2f}/{nm['succ']:.2f} | {m['wall']:.0f}/{nm['wall']:.0f} | "
                 f"{m['tout']:.0f}/{nm['tout']:.0f} | {m['tin']:.0f}/{nm['tin']:.0f} | "
                 f"{m['steps']:.1f}/{nm['steps']:.1f} |")

lines.append("\n## Δ(ℓ) 阶梯(记忆相对裸跑)\n")
lines.append("| 正典档 | 墙钟变化 | 成功率变化 |")
lines.append("|---|---|---|")
for canon, dw, ds in ladder:
    lines.append(f"| {canon} | {dw:+.0f}% | {ds:+.0f}pp |")

lines.append("\n## 逐集成本曲线(tok_out,5 种子均值)——主轴一号图的数据\n")
lines.append("| 集 | " + " | ".join(f"{c} mem/nomem" for c in CANON_ORDER) + " |")
lines.append("|---|" + "---|" * len(CANON_ORDER))
curves = {c: (curve(c, "mem", "tokens_out"), curve(c, "nomem", "tokens_out")) for c in CANON_ORDER}
for i in range(10):
    row = " | ".join(f"{curves[c][0][i]:.0f}/{curves[c][1][i]:.0f}" for c in CANON_ORDER)
    lines.append(f"| {i} | {row} |")

lines.append("\n## 逐集成功率曲线(5 种子均值)\n")
lines.append("| 集 | " + " | ".join(f"{c} mem/nomem" for c in CANON_ORDER) + " |")
lines.append("|---|" + "---|" * len(CANON_ORDER))
scurves = {c: (curve(c, "mem", "success"), curve(c, "nomem", "success")) for c in CANON_ORDER}
for i in range(10):
    row = " | ".join(f"{scurves[c][0][i]:.1f}/{scurves[c][1][i]:.1f}" for c in CANON_ORDER)
    lines.append(f"| {i} | {row} |")

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ANALYSIS_8bfull.md")
open(out, "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
