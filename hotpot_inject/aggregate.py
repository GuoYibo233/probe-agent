"""Aggregate hotpot_v1 results across shards/models into a markdown table."""
import glob
import json
import sys
from collections import defaultdict


def agg(files):
    rows = defaultdict(list)
    base = {}
    for fn in files:
        for line in open(fn):
            r = json.loads(line)
            key = (r["model"], r["type"], r["cond"], r.get("offset"))
            rows[key].append(r)
            if r["cond"] == "baseline":
                base[(r["model"], r["type"], r["qid"])] = r
    out = []
    for key in sorted(rows, key=str):
        rs = rows[key]
        model, typ, cond, off = key
        n = len(rs)
        if cond == "baseline":
            called = [r for r in rs if r["n_calls"] > 0]
            out.append({
                "model": model.split("/")[-1], "type": typ, "cond": cond,
                "offset": "", "n": n,
                "call_rate": round(len(called) / n, 2),
                "mean2calls": round(sum(r["n_calls"] for r in rs) / n, 2),
                "gen_tok": round(sum(r["gen_tokens"] for r in rs) / n),
                "d_tok": "", "em": round(sum(r["em"] for r in rs) / n, 2),
                "soft": round(sum(r["soft"] for r in rs) / n, 2)})
        else:
            # savings vs same-question baseline
            deltas, ems, softs = [], [], []
            for r in rs:
                b = base.get((r["model"], r["type"], r["qid"]))
                if b is None:
                    continue
                deltas.append(b["gen_tokens"] - r["gen_tokens"])
                ems.append(r["em"]); softs.append(r["soft"])
            if not deltas:
                continue
            m = len(deltas)
            out.append({
                "model": model.split("/")[-1], "type": typ, "cond": cond,
                "offset": off, "n": m, "call_rate": "", "mean2calls": "",
                "gen_tok": round(sum(r["gen_tokens"] for r in rs) / n),
                "d_tok": round(sum(deltas) / m),
                "em": round(sum(ems) / m, 2),
                "soft": round(sum(softs) / m, 2)})
    cols = ["model", "type", "cond", "offset", "n", "call_rate", "mean2calls",
            "gen_tok", "d_tok", "em", "soft"]
    print("| " + " | ".join(cols) + " |")
    print("|" + "---|" * len(cols))
    for o in out:
        print("| " + " | ".join(str(o[c]) for c in cols) + " |")


if __name__ == "__main__":
    files = []
    for pat in sys.argv[1:]:
        files += glob.glob(pat)
    agg(sorted(files))
