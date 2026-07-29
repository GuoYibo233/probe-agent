"""C3 指标脚本(T12b):Speedup@k / cost-to-competence / 负迁移指数。

从 fig1_pilot/analyze_full.py 长出;公式与边界规则以
benchmark_design/L3L4_and_metrics_draft.md §3 为准。
五条防幸存者偏差聚合规则(§3.5)全部做成代码内硬检查,不靠自觉:

  R1 完整格   — 逐集统计只用跑满 K 集的 run;被丢弃的 run 必须显式列出。
  R2 配对差分 — mem−nomem 比较只在 (seed, 集位, 任务实例) 三对齐的格上做;
               任一臂缺格或任务实例不一致 → 整格弃用并计数上报。
  R3 三态审计 — 主指标 ok-only;各条件 ok 率必报(无 status 字段视为全 ok)。
  R4 显式截尾 — CTC 未达标 run 记全流预算、带 censored 标记与达标率;
               代码不提供 reachers-only 均值的任何出口。
  R5 硬件分层 — 跨 run 汇总成本一律用 token(tok_in+tok_out);
               wall_s 仅在 --wall-uniform 显式声明同硬件时才进报告。

正典档位重映射(--legacy-levels,适用于 fig1/8bfull 旧标签文件):
  旧 L0(完全重复)→ L2 / 旧 L1(近重复)→ L2- / 旧 L2(部分相似)→ L1

用法:
  python3 metrics.py --dir ../fig1_pilot/results --glob '8bfull_*.jsonl' \
      --legacy-levels --k 10 [--wall-uniform] [--md out.md]
  python3 metrics.py --selftest        # 合成数据自检(含幸存者偏差场景)

种子:bootstrap 固定 20260729,重跑逐位一致。
"""

import argparse
import glob
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

SEED = 20260729
LEGACY_MAP = {"L0": "L2", "L1": "L2-", "L2": "L1"}
COST_KEYS = ("tokens_in", "tokens_out")
MIN_PAIRED = 4      # |P_k| 门槛,低于则该点不报告(留缺口)
CTC_WINDOW = 3
CTC_THETAS = (0.5, 0.7)
BOOTSTRAP_B = 2000


def cost(row):
    return sum(row[k] for k in COST_KEYS)


def ok(row):
    return row.get("status", "ok") == "ok"


# ---------------------------------------------------------------- 载入(R1)

def load_runs(pattern, k_expected, legacy, name_re):
    """runs[(level, setting, seed)] = rows(按 episode_idx 排序,恰好 K 条)。"""
    runs, dropped = {}, []
    for f in sorted(glob.glob(pattern)):
        name = Path(f).stem
        m = re.match(name_re, name)
        if not m:
            dropped.append((name, "文件名不匹配"))
            continue
        level, setting, seed = m.group(1), m.group(2), int(m.group(3))
        if legacy:
            level = LEGACY_MAP[level]
        rows = [json.loads(l) for l in open(f) if l.strip()]
        rows.sort(key=lambda r: r["episode_idx"])
        if len(rows) != k_expected:                      # R1
            dropped.append((name, f"{len(rows)}/{k_expected} 集,不完整"))
            continue
        runs[(level, setting, seed)] = rows
    return runs, dropped


# ---------------------------------------------------------- 配对格(R2/R3)

def paired_grid(runs, level):
    """P[k] = [(seed, mem_row, nomem_row)],三对齐 + 双臂 ok;弃格计数上报。"""
    seeds = sorted({s for (lv, st, s) in runs if lv == level})
    P = defaultdict(list)
    drops = {"missing_arm": 0, "instance_mismatch": 0, "not_ok": 0}
    for s in seeds:
        mem = runs.get((level, "mem", s))
        nom = runs.get((level, "nomem", s))
        if mem is None or nom is None:
            drops["missing_arm"] += 1
            continue
        for mr, nr in zip(mem, nom):
            inst_m = mr.get("game", mr.get("task"))
            inst_n = nr.get("game", nr.get("task"))
            if inst_m != inst_n:                          # R2
                drops["instance_mismatch"] += 1
                continue
            if not (ok(mr) and ok(nr)):                   # R3 主指标 ok-only
                drops["not_ok"] += 1
                continue
            P[mr["episode_idx"]].append((s, mr, nr))
    return P, drops


def ok_rates(runs, level):
    out = {}
    for setting in ("mem", "nomem"):
        rows = [r for (lv, st, s), rs in runs.items()
                if lv == level and st == setting for r in rs]
        out[setting] = (sum(ok(r) for r in rows) / len(rows)) if rows else None
    return out


# ------------------------------------------------------------- Speedup@k

def speedup_at_k(P, rng):
    """逐集 {k: (Sp@k, Acc@k, |P_k|, CI95)};|P_k|<MIN_PAIRED → 该点 None。

    Sp@k 用和的比(= token 加权),不用逐 run 比值均值(重尾小分母会炸)。
    Acc@k 与 Sp@k 永远同一 P_k,拆开引用无效。CI 对 run 做 bootstrap。
    """
    out = {}
    for k in sorted(P):
        cells = P[k]
        if len(cells) < MIN_PAIRED:
            out[k] = None
            continue
        sp = 1 - sum(cost(m) for _, m, _ in cells) / sum(cost(n) for _, _, n in cells)
        acc = sum(m["success"] for _, m, _ in cells) / len(cells)
        boots = []
        for _ in range(BOOTSTRAP_B):
            bs = [cells[rng.randrange(len(cells))] for _ in cells]
            denom = sum(cost(n) for _, _, n in bs)
            if denom > 0:
                boots.append(1 - sum(cost(m) for _, m, _ in bs) / denom)
        boots.sort()
        ci = (boots[int(0.025 * len(boots))], boots[int(0.975 * len(boots))])
        out[k] = (sp, acc, len(cells), ci)
    return out


# ------------------------------------------------------- cost-to-competence

def ctc_one_run(rows, theta, k_total):
    """(ctc, censored, k*)。达标集位按滑窗能力 ≥θ;未达标记全流预算(R4)。"""
    u = [r["success"] for r in rows]
    k_star = None
    for k in range(CTC_WINDOW, k_total + 1):
        if sum(u[k - CTC_WINDOW:k]) / CTC_WINDOW >= theta:
            k_star = k
            break
    if k_star is None:
        return sum(cost(r) for r in rows), True, None
    return sum(cost(r) for r in rows[:k_star]), False, k_star


def ctc_summary(runs, level, setting, thetas, k_total):
    """各 θ:中位数 CTC(censored 计全预算)+ 达标率 ρ。永不提供 reachers-only。"""
    keys = sorted(k for k in runs if k[0] == level and k[1] == setting)
    out = {}
    for theta in thetas:
        vals, cens = [], 0
        for key in keys:
            c, censored, _ = ctc_one_run(runs[key], theta, k_total)
            vals.append(c)
            cens += censored
        if not vals:
            out[theta] = None
            continue
        vals.sort()
        n = len(vals)
        med = (vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2)
        out[theta] = {"median": med, "n": n, "censored": cens,
                      "reach_rate": (n - cens) / n, "geq": cens > 0}
    return out


def relative_theta(runs, level, k_total):
    """相对档 θ = nomem 全流成功率均值 + 10pp(封顶 1.0)。"""
    rows = [r for (lv, st, s), rs in runs.items()
            if lv == level and st == "nomem" for r in rs]
    if not rows:
        return None
    return min(1.0, sum(r["success"] for r in rows) / len(rows) + 0.10)


# --------------------------------------------------------------- 负迁移指数

def nti(P, probe_eps, tier_of=None):
    """L4 探针段读数:(NTI_acc, NTI_cost),正值=负迁移;可按 T1/T2/T3 分层。

    P 来自 paired_grid(已 ok-only 配对);probe_eps = 探针段集位集合
    (seeding 段一律剔除);tier_of(ep)→'T1'/'T2'/'T3' 可选。
    每层 n<10 不单独报(记 None),但计入 all。
    """
    layers = defaultdict(list)
    for k in sorted(P):
        if k not in probe_eps:
            continue
        for cell in P[k]:
            layers["all"].append(cell)
            if tier_of:
                layers[tier_of(k)].append(cell)
    out = {}
    for tier, cells in layers.items():
        if tier != "all" and len(cells) < 10:
            out[tier] = None
            continue
        um = sum(m["success"] for _, m, _ in cells) / len(cells)
        un = sum(n["success"] for _, _, n in cells) / len(cells)
        cm = sum(cost(m) for _, m, _ in cells) / len(cells)
        cn = sum(cost(n) for _, _, n in cells) / len(cells)
        out[tier] = {"NTI_acc": un - um, "NTI_cost": (cm - cn) / cn, "n": len(cells)}
    return out


# ------------------------------------------------------------------- 报告

def fmt_pct(x):
    return f"{100 * x:+.1f}%"


def report(runs, dropped, k_total, wall_uniform):
    lines = ["# C3 指标报告(metrics.py)\n"]
    lines.append(f"完整 run:{len(runs)};K={k_total};成本货币=tok_in+tok_out;"
                 f"bootstrap 种子={SEED}")
    if dropped:
        lines.append("\nR1 丢弃的 run(不完整/不匹配,不入任何统计):")
        for name, why in dropped:
            lines.append(f"- {name}:{why}")
    if not wall_uniform:
        lines.append("\nR5:未声明 --wall-uniform,墙钟一律不进报告,只报 token。")

    rng = random.Random(SEED)
    levels = sorted({lv for (lv, st, s) in runs})
    for level in levels:
        P, drops = paired_grid(runs, level)
        okr = ok_rates(runs, level)
        lines.append(f"\n## 档位 {level}\n")
        lines.append(f"R2/R3 弃格:{drops};ok 率 mem/nomem:"
                     f"{okr['mem']:.2f}/{okr['nomem']:.2f}")
        lines.append("\n| k | Sp@k | 95%CI | Acc@k | \\|P_k\\| |")
        lines.append("|---|---|---|---|---|")
        for k, v in speedup_at_k(P, rng).items():
            if v is None:
                lines.append(f"| {k + 1} | (缺口:配对格<{MIN_PAIRED}) | | | |")
            else:
                sp, acc, n, ci = v
                lines.append(f"| {k + 1} | {fmt_pct(sp)} | "
                             f"[{fmt_pct(ci[0])}, {fmt_pct(ci[1])}] | "
                             f"{acc:.2f} | {n} |")
        rel = relative_theta(runs, level, k_total)
        thetas = list(CTC_THETAS) + ([rel] if rel is not None else [])
        lines.append("\n| 臂 | θ | CTC 中位数(tok) | 达标率 ρ | censored |")
        lines.append("|---|---|---|---|---|")
        for setting in ("mem", "nomem"):
            for theta, s in ctc_summary(runs, level, setting, thetas, k_total).items():
                if s is None:
                    continue
                tag = "≥" if s["geq"] else ""
                lines.append(f"| {setting} | {theta:.2f} | {tag}{s['median']:.0f} | "
                             f"{s['reach_rate']:.2f} | {s['censored']}/{s['n']} |")
    lines.append("\n(NTI 需 L4 探针流数据,函数已备,`--selftest` 含其自检。)")
    return "\n".join(lines)


# ------------------------------------------------------------------- 自检

def _mk(ep, succ, ci, co, inst, status="ok"):
    return {"episode_idx": ep, "success": succ, "tokens_in": ci,
            "tokens_out": co, "game": inst, "status": status}


def selftest():
    K = 6
    # R1:不完整 run 必须被丢弃 —— 幸存者偏差场景:快 run 先完赛且数字漂亮
    runs, dropped = {}, [("fast_partial", "3/6 集,不完整")]
    for s in range(4):
        runs[("L2", "mem", s)] = [_mk(e, 1, 100, 100 - 10 * e, f"g{e}") for e in range(K)]
        runs[("L2", "nomem", s)] = [_mk(e, 1, 100, 100, f"g{e}") for e in range(K)]
    P, drops = paired_grid(runs, "L2")
    assert all(len(P[k]) == 4 for k in range(K)) and not any(drops.values())
    sp = speedup_at_k(P, random.Random(SEED))
    assert abs(sp[5][0] - (1 - 150 / 200)) < 1e-9, "Sp@k 和的比算错"
    assert sp[5][1] == 1.0, "Acc@k 必须与 Sp@k 同格"

    # R2:任务实例不一致的格必须整格弃用
    runs2 = dict(runs)
    runs2[("L2", "nomem", 0)] = [_mk(e, 1, 100, 100, f"DIFF{e}") for e in range(K)]
    P2, d2 = paired_grid(runs2, "L2")
    assert d2["instance_mismatch"] == K and all(len(P2[k]) == 3 for k in range(K))

    # R2 |P_k| 门槛:3 < MIN_PAIRED → 全部缺口
    assert all(v is None for v in speedup_at_k(P2, random.Random(SEED)).values())

    # R3:非 ok 格剔除但 ok 率必报
    runs3 = dict(runs)
    runs3[("L2", "mem", 1)] = [_mk(e, 1, 100, 100, f"g{e}",
                               "degen" if e == 2 else "ok") for e in range(K)]
    P3, d3 = paired_grid(runs3, "L2")
    assert d3["not_ok"] == 1 and len(P3[2]) == 3
    assert ok_rates(runs3, "L2")["mem"] == (24 - 1) / 24

    # R4:永不达标 run 记全预算 + censored,且达标率如实
    never = [_mk(e, 0, 50, 50, f"g{e}") for e in range(K)]
    c, cen, ks = ctc_one_run(never, 0.5, K)
    assert cen and c == 600 and ks is None
    learner = [_mk(e, int(e >= 2), 50, 50, f"g{e}") for e in range(K)]
    c2, cen2, ks2 = ctc_one_run(learner, 0.5, K)   # 滑窗 [2,3] 首过在 k=4
    assert not cen2 and ks2 == 4 and c2 == 400
    runs4 = {("L4", "mem", 0): never, ("L4", "mem", 1): learner}
    s4 = ctc_summary(runs4, "L4", "mem", [0.5], K)[0.5]
    assert s4["censored"] == 1 and s4["reach_rate"] == 0.5 and s4["geq"]

    # NTI:构造 T3 特征(更快但错)与 T2 特征(又慢又错)
    P5 = defaultdict(list)
    for s in range(12):
        P5[0].append((s, _mk(0, 0, 40, 40, "g0"), _mk(0, 1, 50, 50, "g0")))   # T3
        P5[1].append((s, _mk(1, 0, 80, 80, "g1"), _mk(1, 1, 50, 50, "g1")))   # T2
    r = nti(P5, {0, 1}, tier_of=lambda k: "T3" if k == 0 else "T2")
    assert r["T3"]["NTI_acc"] == 1.0 and r["T3"]["NTI_cost"] < 0
    assert r["T2"]["NTI_acc"] == 1.0 and r["T2"]["NTI_cost"] > 0
    # 分层 n<10 不单独报
    r2 = nti(P5, {0, 1}, tier_of=lambda k: "T1" if k == 0 else "T2")
    assert r2["T1"] is None or r2["T1"]["n"] >= 10

    print("selftest: 全部通过(R1-R5 + Sp@k/CTC/NTI)")
    print(report(runs, dropped, K, wall_uniform=False)[:400] + "\n...")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="../fig1_pilot/results")
    ap.add_argument("--glob", default="8bfull_*.jsonl")
    ap.add_argument("--name-re", default=r".*_(L\d-?)_(nomem|mem)_s(\d+)")
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--legacy-levels", action="store_true",
                    help="文件名用 fig1 旧编号,载入时映射到正典档位")
    ap.add_argument("--wall-uniform", action="store_true",
                    help="显式声明本批 run 同硬件(R5);当前版本仍只报 token")
    ap.add_argument("--md", help="报告写到文件(默认 stdout)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        selftest()
        return

    runs, dropped = load_runs(str(Path(args.dir) / args.glob), args.k,
                              args.legacy_levels, args.name_re)
    if not runs:
        sys.exit("没有完整 run 可用")
    text = report(runs, dropped, args.k, args.wall_uniform)
    if args.md:
        Path(args.md).write_text(text + "\n")
        print(f"报告已写 {args.md}")
    else:
        print(text)


if __name__ == "__main__":
    main()
