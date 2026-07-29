"""Full-matrix analysis for Fig1: per (level, setting) learning curves.

Aggregates results/full_*.jsonl (complete 10-episode runs only, unless
--include-partial). Optionally folds in redo106_* replacements (flagged:
different hardware, wall_s excluded from cross-pair wall stats).
Outputs markdown to stdout.
"""

import argparse
import glob
import json
import re
from collections import defaultdict
from pathlib import Path

STATS = ["success", "steps", "wall_s", "tokens_in", "tokens_out"]


def load(pattern, min_eps=10):
    runs = {}
    for f in glob.glob(pattern):
        name = Path(f).stem
        rows = [json.loads(l) for l in open(f)]
        if len(rows) < min_eps:
            print(f"<!-- skipped {name}: {len(rows)} eps -->")
            continue
        runs[name] = rows
    return runs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="results")
    ap.add_argument("--redo", action="store_true", help="fold in redo106_* files")
    args = ap.parse_args()

    runs = load(f"{args.dir}/full_*.jsonl")
    redo = load(f"{args.dir}/redo106_*.jsonl") if args.redo else {}

    # index: (level, setting) -> ep -> list of rows
    agg = defaultdict(lambda: defaultdict(list))
    redo_agg = defaultdict(lambda: defaultdict(list))
    for name, rows in runs.items():
        m = re.match(r"full_(L\d)_(nomem|mem)_s(\d)", name)
        for r in rows:
            agg[(m.group(1), m.group(2))][r["episode_idx"]].append(r)
    for name, rows in redo.items():
        m = re.match(r"redo106_(L\d)_(nomem|mem)_s(\d)", name)
        for r in rows:
            redo_agg[(m.group(1), m.group(2))][r["episode_idx"]].append(r)

    print("# Fig1 全矩阵分析\n")
    print(f"完整 run 数: {len(runs)}" + (f" + redo106 替补 {len(redo)}" if redo else ""))

    for key in sorted(agg):
        level, setting = key
        eps = agg[key]
        n_runs = len(eps[0])
        print(f"\n## {level} / {setting}  (n={n_runs} seeds)\n")
        print("| ep | success | steps | wall_s | tok_in | tok_out |")
        print("|---|---|---|---|---|---|")
        for i in sorted(eps):
            rs = eps[i]
            def mean(k):
                return sum(r[k] for r in rs) / len(rs)
            print(f"| {i+1} | {mean('success'):.2f} | {mean('steps'):.1f} | "
                  f"{mean('wall_s'):.0f} | {mean('tokens_in'):.0f} | "
                  f"{mean('tokens_out'):.0f} |")
        # halves summary
        first = [r for i in range(5) for r in eps[i]]
        last = [r for i in range(5, 10) for r in eps[i]]
        for tag, part in (("前半(ep1-5)", first), ("后半(ep6-10)", last)):
            sr = sum(r["success"] for r in part) / len(part)
            wl = sum(r["wall_s"] for r in part) / len(part)
            st = sum(r["steps"] for r in part) / len(part)
            ti = sum(r["tokens_in"] for r in part) / len(part)
            print(f"\n**{tag}**: success {sr:.2f} · wall {wl:.0f}s · "
                  f"steps {st:.1f} · tok_in {ti:.0f}")

    if redo_agg:
        print("\n# redo106 替补对 (L2, s1) — A6000 硬件，wall 与 tokyo108 不可比\n")
        for key in sorted(redo_agg):
            eps = redo_agg[key]
            succ = [str(int(eps[i][0]["success"])) for i in sorted(eps)]
            walls = [str(round(eps[i][0]["wall_s"])) for i in sorted(eps)]
            print(f"- {key}: success {' '.join(succ)} | wall {' '.join(walls)}")


if __name__ == "__main__":
    main()
