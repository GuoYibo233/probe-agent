"""Aggregate oracle_v1 results across models into the decision table.

Per (model, cond, offset): n, mean saved generated tokens vs baseline,
call-skip rate, accuracy. Baselines reported per model. Markdown to stdout.
"""

import glob
import json
import sys
from collections import defaultdict


def main(pattern):
    rows = []
    for f in glob.glob(pattern):
        for line in open(f):
            rows.append(json.loads(line))

    models = sorted({r["model"] for r in rows})
    for m in models:
        mrows = [r for r in rows if r["model"] == m]
        base = [r for r in mrows if r["cond"] == "baseline"]
        called = [r for r in base if r.get("call_emitted")]
        nocall = [r for r in base if not r.get("call_emitted")]
        print(f"\n## {m}")
        print(f"- baseline: n={len(base)}, 发起调用 {len(called)}, "
              f"未调用(幻觉/直答) {len(nocall)}")
        if called:
            acc = sum(r["correct"] for r in called) / len(called)
            gt = sum(r["gen_tokens"] for r in called) / len(called)
            tc = sum(r["tokens_to_call"] for r in called) / len(called)
            print(f"- baseline(有调用): acc={acc:.2f}, "
                  f"mean gen_tokens={gt:.0f}, mean tokens_to_call={tc:.0f}")
        by = defaultdict(list)
        for r in mrows:
            if r["cond"] in ("inject", "inject_wrong"):
                by[(r["cond"], r["offset"])].append(r)
        if not by:
            continue
        print("\n| cond | offset | n | mean saved tok | call-skip | acc |")
        print("|---|---|---|---|---|---|")
        for (cond, off) in sorted(by, key=lambda k: (k[0], k[1])):
            rs = by[(cond, off)]
            saved = [r["baseline_gen_tokens"] - r["gen_tokens"] for r in rs]
            skip = sum(not r["called_anyway"] for r in rs) / len(rs)
            acc = sum(r["correct"] for r in rs) / len(rs)
            off_s = "start" if off < 0 else str(off)
            print(f"| {cond} | {off_s} | {len(rs)} | "
                  f"{sum(saved)/len(saved):+.0f} | {skip:.2f} | {acc:.2f} |")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "results/full_*.jsonl")
