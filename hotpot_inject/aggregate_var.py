"""T11 采样方差聚合:按 gen_seed 分组算每种子聚合值,再报跨种子 mean±std。

用法: python aggregate_var.py 'results_t11/*.jsonl'
配对口径与 aggregate.py 一致:注入条件的 d_tok/em/soft 都对同种子同题的 baseline 配对。
"""
import glob
import json
import statistics
import sys
from collections import defaultdict


def per_seed(files):
    rows = defaultdict(list)
    base = {}
    for fn in files:
        for line in open(fn):
            r = json.loads(line)
            seed = r.get("gen_seed", -1)
            key = (r["model"], r.get("dataset", "hotpot"), r["type"],
                   r["cond"], r.get("offset"), seed)
            rows[key].append(r)
            if r["cond"] == "baseline":
                base[(r["model"], r["type"], r["qid"], seed)] = r
    stats = defaultdict(dict)   # cond_key -> seed -> dict
    for key, rs in rows.items():
        model, ds, typ, cond, off, seed = key
        ckey = (model, ds, typ, cond, off)
        n = len(rs)
        if cond == "baseline":
            stats[ckey][seed] = dict(
                n=n, em=sum(r["em"] for r in rs) / n,
                soft=sum(r["soft"] for r in rs) / n,
                gen_tok=sum(r["gen_tokens"] for r in rs) / n, d_tok=None)
        else:
            deltas, ems, softs = [], [], []
            for r in rs:
                b = base.get((r["model"], r["type"], r["qid"], seed))
                if b is None:
                    continue
                deltas.append(b["gen_tokens"] - r["gen_tokens"])
                ems.append(r["em"])
                softs.append(r["soft"])
            if not deltas:
                continue
            m = len(deltas)
            stats[ckey][seed] = dict(
                n=m, em=sum(ems) / m, soft=sum(softs) / m,
                gen_tok=sum(r["gen_tokens"] for r in rs) / n,
                d_tok=sum(deltas) / m)
    return stats


def ms(vals):
    """mean±std 字符串;单种子只报值。"""
    if len(vals) == 1:
        return f"{vals[0]:.2f}"
    return f"{statistics.mean(vals):.2f}±{statistics.stdev(vals):.2f}"


def main():
    files = []
    for pat in sys.argv[1:]:
        files += glob.glob(pat)
    stats = per_seed(sorted(files))
    cols = ["model", "dataset", "type", "cond", "offset", "seeds", "n/seed",
            "em", "soft", "gen_tok", "d_tok"]
    print("| " + " | ".join(cols) + " |")
    print("|" + "---|" * len(cols))
    for ckey in sorted(stats, key=str):
        model, ds, typ, cond, off = ckey
        by_seed = stats[ckey]
        seeds = sorted(by_seed)
        em = ms([by_seed[s]["em"] for s in seeds])
        soft = ms([by_seed[s]["soft"] for s in seeds])
        gt = ms([by_seed[s]["gen_tok"] for s in seeds])
        dt = ("" if by_seed[seeds[0]]["d_tok"] is None
              else ms([by_seed[s]["d_tok"] for s in seeds]))
        ns = ",".join(str(by_seed[s]["n"]) for s in seeds)
        print(f"| {model.split('/')[-1]} | {ds} | {typ} | {cond} | "
              f"{'' if off is None else off} | {len(seeds)} | {ns} | "
              f"{em} | {soft} | {gt} | {dt} |")


if __name__ == "__main__":
    main()
