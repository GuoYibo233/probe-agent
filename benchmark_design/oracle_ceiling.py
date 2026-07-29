"""完美复用天花板(T12d 的 CPU 件):在已有记录上算 oracle replay 上界。

定义:oracle 站在 nomem 流上,逐集看——若当前任务实例(game 字段)在
同一条流的**更早集位**出现过且成功过,则本集按"纯动作回放"记账:
成本 0(逐字重放已知成功动作序列,零 LLM 调用)、成绩 1(确定性引擎);
否则本集保持 nomem 原值。ep0 永不可替换。成本 0 是上界的正确取法:
任何真实系统还要付检索/核验的钱,但没有系统能比免费回放更省。

推论:天花板只在实例真重复的档位有内容(正典 L2 完全重复);
L1/L2- 每集实例不同,逐字回放无定义,天花板=nomem 本身——
这不是缺陷,是"逐字复用救不了非重复负载"的量化表达,进协议节。

用法: python3 oracle_ceiling.py [--dir ../fig1_pilot/results]
      [--glob '8bfull_*.jsonl'] [--legacy-levels] [--k 10] [--md out.md]
"""

import argparse
from collections import defaultdict
from pathlib import Path

from metrics import LEGACY_MAP, cost, load_runs  # noqa: F401  (同目录复用)


def oracle_stream(rows):
    """nomem 流 → (天花板成本序列, 成绩序列, 替换标记序列)。"""
    solved = set()     # 有成功先例的实例
    ceil_c, ceil_u, replaced = [], [], []
    for r in rows:
        inst = r.get("game", r.get("task"))
        if inst in solved:
            ceil_c.append(0.0)
            ceil_u.append(1)
            replaced.append(True)
        else:
            ceil_c.append(cost(r))
            ceil_u.append(r["success"])
            replaced.append(False)
            if r["success"]:
                solved.add(inst)
    return ceil_c, ceil_u, replaced


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="../fig1_pilot/results")
    ap.add_argument("--glob", default="8bfull_*.jsonl")
    ap.add_argument("--name-re", default=r".*_(L\d-?)_(nomem|mem)_s(\d+)")
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--legacy-levels", action="store_true")
    ap.add_argument("--md")
    args = ap.parse_args()

    runs, dropped = load_runs(str(Path(args.dir) / args.glob), args.k,
                              args.legacy_levels, args.name_re)
    lines = ["# 完美复用天花板(oracle replay,nomem 流上算)\n"]
    lines.append(f"完整 run:{len(runs)};R1 丢弃:{len(dropped)};"
                 "成本货币=tok_in+tok_out")

    levels = sorted({lv for (lv, st, s) in runs})
    for level in levels:
        keys = sorted(k for k in runs if k[0] == level and k[1] == "nomem")
        if not keys:
            continue
        per_k = defaultdict(lambda: [0.0, 0.0, 0, 0, 0])  # nomem, ceil, ok_n, ok_c, repl
        for key in keys:
            rows = runs[key]
            cc, cu, rep = oracle_stream(rows)
            for i, r in enumerate(rows):
                a = per_k[i]
                a[0] += cost(r)
                a[1] += cc[i]
                a[2] += r["success"]
                a[3] += cu[i]
                a[4] += rep[i]
        n = len(keys)
        lines.append(f"\n## 档位 {level}(n={n} 条 nomem 流)\n")
        lines.append("| k | 天花板省token | 成功率 nomem→oracle | 可替换集占比 |")
        lines.append("|---|---|---|---|")
        tot_n = tot_c = 0.0
        for i in sorted(per_k):
            a = per_k[i]
            tot_n += a[0]
            tot_c += a[1]
            sp = 1 - a[1] / a[0]
            lines.append(f"| {i + 1} | {100 * sp:+.1f}% | "
                         f"{a[2] / n:.2f}→{a[3] / n:.2f} | {a[4]}/{n} |")
        lines.append(f"\n全流合计:天花板省 token {100 * (1 - tot_c / tot_n):+.1f}%")
        if not any(per_k[i][4] for i in per_k):
            lines.append("(本档实例零重复:逐字回放无定义,天花板=nomem 本身。)")
    text = "\n".join(lines)
    if args.md:
        Path(args.md).write_text(text + "\n")
        print(f"报告已写 {args.md}")
    else:
        print(text)


if __name__ == "__main__":
    main()
