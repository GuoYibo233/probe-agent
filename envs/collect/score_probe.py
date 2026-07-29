"""给截断探针的盲测预测评分。

用法: python score_probe.py <domain> <pred.json>
domain ∈ tales/appworld/bfcl。gold 从 runs/probe_v0/gold_<domain>.json 读。
按截断档位(25/50/75)分桶报: 名称命中率 / 完全命中率,再按置信度分桶。
"""

import json
import re
import sys
from pathlib import Path

GOLD_DIR = Path("/home/y-guo/reproduce/new1/envs/runs/probe_v0")


def norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def head_name(domain, s):
    s = (s or "").strip()
    if domain == "tales":
        return s.split()[0].lower() if s.split() else ""
    if domain == "appworld":
        m = re.search(r"apis\.(\w+)\.(\w+)", s)
        return f"{m.group(1)}.{m.group(2)}" if m else ""
    m = re.search(r"\[?\s*(\w+)\s*\(", s)
    return m.group(1).lower() if m else ""


def all_names(domain, s):
    if domain == "bfcl":
        return tuple(re.findall(r"(\w+)\s*\(", s or ""))
    return (head_name(domain, s),)


def main():
    domain, pred_file = sys.argv[1], sys.argv[2]
    gold = json.load(open(GOLD_DIR / f"gold_{domain}.json"))
    preds = json.load(open(pred_file))
    key = {"tales": "cmd", "appworld": "call", "bfcl": "calls"}[domain]

    buckets = {}
    for cid, p in preds.items():
        base, _, frac = cid.rpartition("@")
        if base not in gold:
            continue
        g, ps = gold[base], p.get(key, "")
        b = buckets.setdefault(frac, {"n": 0, "name": 0, "names_all": 0,
                                      "exact": 0, "conf": {}})
        b["n"] += 1
        name_hit = head_name(domain, ps) == head_name(domain, g)
        b["name"] += name_hit
        b["names_all"] += all_names(domain, ps) == all_names(domain, g)
        b["exact"] += norm(ps) == norm(g)
        c = b["conf"].setdefault(p.get("conf", "?"), [0, 0])
        c[0] += 1
        c[1] += name_hit

    print(f"== {domain} ==")
    for frac in sorted(buckets, key=int):
        b = buckets[frac]
        n = b["n"]
        print(f"@{frac}%: n={n}  首调用名命中 {b['name']/n:.2f}  "
              f"全序列名命中 {b['names_all']/n:.2f}  完全一致 {b['exact']/n:.2f}")
        for cv, (cn, ch) in sorted(b["conf"].items()):
            print(f"    conf={cv}: n={cn} 名命中 {ch/cn:.2f}")


if __name__ == "__main__":
    main()
