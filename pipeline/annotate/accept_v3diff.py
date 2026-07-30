"""annotate 段验收:新代码的事件抽取+造样本与 v3 旧数据逐字节对比。

做什么:用 build.py 的抽取函数(jsonl_events/bfcl_events)与造样本函数
(make_samples)跑 v3 当年的输入(full_v1 + full_v2_topup,**不过滤模型**、
不用官方题单切分),与 envs/bert_data/v3/<env>/{train,calA,calB,test}.jsonl
四堆合并后按主键 (event, sent_idx) 对比。切分法不同,所以不比堆归属;
新字段 label_call/args_named 不比。

输入(只读): envs/runs/full_v1、envs/runs/full_v2_topup、envs/bert_data/v3
输出: pipeline/annotate/ACCEPT_V3DIFF.md(两边条数 + 逐字段不一致计数,须全 0)
退出码: 全 0 -> 0;有任何不一致 -> 1

用法: python3 accept_v3diff.py
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import bfcl_events, jsonl_events, make_samples  # noqa: E402

BASE = Path("/home/y-guo/reproduce/new1/envs")
RUNS = [BASE / "runs" / "full_v1", BASE / "runs" / "full_v2_topup"]
V3 = BASE / "bert_data" / "v3"
OLD_SPLITS = ("train", "calA", "calB", "test")
FIELDS = ("text", "label", "w", "depth", "n_sents",
          "traj", "unit", "model", "step")
OUT = Path(__file__).resolve().parent / "ACCEPT_V3DIFF.md"


def new_samples(env):
    events = []
    for runs in RUNS:
        if env == "appworld":
            events.extend(jsonl_events(
                runs, "appworld_*/appworld_*.jsonl", "appworld"))
        elif env == "bfcl":
            events.extend(bfcl_events(runs))
        else:
            raise SystemExit(f"未知环境: {env}")
    return events, make_samples(events)


def old_samples(env):
    rows = []
    for sp in OLD_SPLITS:
        with open(V3 / env / f"{sp}.jsonl") as f:
            for line in f:
                rows.append(json.loads(line))
    return rows


def index(rows):
    d = defaultdict(list)
    for r in rows:
        d[(r["event"], r["sent_idx"])].append(r)
    return d


def compare(env):
    events, new = new_samples(env)
    old = old_samples(env)

    # 输入漂移:v3 建库之后才落地的采集目录(实测 bfcl_gptoss 是 v3 建完
    # 3 小时后才采完的),旧数据里根本没有,不该算成抄写走样。
    # 判据不写死目录名:旧数据里没出现过的采集目录整批剔除,并在报告里点名。
    old_batches = {r["traj"].split("/")[0] for r in old}
    drift = defaultdict(int)
    kept = []
    for s in new:
        b = s["traj"].split("/")[0]
        if b in old_batches:
            kept.append(s)
        else:
            drift[b] += 1
    new = kept

    inew, iold = index(new), index(old)

    only_new = sorted(set(inew) - set(iold))
    only_old = sorted(set(iold) - set(inew))
    dup_new = sum(len(v) - 1 for v in inew.values() if len(v) > 1)
    dup_old = sum(len(v) - 1 for v in iold.values() if len(v) > 1)
    mult_mismatch = sum(1 for k in set(inew) & set(iold)
                        if len(inew[k]) != len(iold[k]))

    bad = {f: 0 for f in FIELDS}
    examples = {}
    n_cmp = 0
    for k in set(inew) & set(iold):
        for a, b in zip(inew[k], iold[k]):
            n_cmp += 1
            for f in FIELDS:
                if a[f] != b[f]:
                    bad[f] += 1
                    examples.setdefault(f, (k, repr(a[f])[:200],
                                            repr(b[f])[:200]))
    return dict(env=env, n_events=len(events), n_new=len(new), n_old=len(old),
                n_cmp=n_cmp, only_new=len(only_new), only_old=len(only_old),
                dup_new=dup_new, dup_old=dup_old, drift=dict(drift),
                mult_mismatch=mult_mismatch, bad=bad, examples=examples,
                only_new_ex=only_new[:5], only_old_ex=only_old[:5])


def main():
    results = [compare(env) for env in ("bfcl", "appworld")]
    md = ["# ACCEPT_V3DIFF — annotate 段与 v3 旧数据一致性验收\n",
          "口径:新代码(rules.py + build.py 的 jsonl_events/bfcl_events/"
          "make_samples)跑 v3 当年输入(full_v1 + full_v2_topup,不过滤模型、"
          "不切分),与 envs/bert_data/v3/<env> 四堆合并按 (event, sent_idx) "
          "对比;比 " + "/".join(FIELDS) + " 九字段,新字段不比。\n",
          "一处口径补丁:v3 建库(2026-07-30 00:38)之后才采完的采集目录"
          "(bfcl_gptoss,03:48 落地)旧数据里根本没有,整批剔除后再比,"
          "剔除清单逐环境列在下表。判据不写死目录名,取自旧数据自己的"
          "采集目录集合。\n"]
    ok = True
    for r in results:
        n_bad = sum(r["bad"].values())
        struct_bad = (r["n_new"] != r["n_old"] or r["only_new"]
                      or r["only_old"] or r["mult_mismatch"])
        passed = (n_bad == 0 and not struct_bad)
        ok = ok and passed
        md += [
            f"\n## {r['env']} — {'PASS' if passed else 'FAIL'}",
            "",
            "| 项 | 值 |",
            "|---|---|",
            f"| 新代码事件数(含漂移目录) | {r['n_events']} |",
            f"| 新代码样本数(剔除漂移目录后) | {r['n_new']} |",
            f"| 剔除的漂移采集目录 | {r['drift'] or '无'} |",
            f"| v3 旧样本数(四堆合并) | {r['n_old']} |",
            f"| 逐条比对数 | {r['n_cmp']} |",
            f"| 主键只在新侧 | {r['only_new']} |",
            f"| 主键只在旧侧 | {r['only_old']} |",
            f"| 新侧重复主键(超出首条) | {r['dup_new']} |",
            f"| 旧侧重复主键(超出首条) | {r['dup_old']} |",
            f"| 同主键条数不等 | {r['mult_mismatch']} |",
            "",
            "逐字段不一致计数:",
            "",
            "| 字段 | " + " | ".join(FIELDS) + " |",
            "|---|" + "---|" * len(FIELDS),
            "| 不一致 | " + " | ".join(str(r["bad"][f]) for f in FIELDS)
            + " |",
        ]
        if r["examples"]:
            md += ["", "首个不一致样例:"]
            for f, (k, a, b) in sorted(r["examples"].items()):
                md += [f"- `{f}` @ {k}: 新={a} 旧={b}"]
        if r["only_new_ex"] or r["only_old_ex"]:
            md += ["", f"- 只在新侧样例: {r['only_new_ex']}",
                   f"- 只在旧侧样例: {r['only_old_ex']}"]
        print(f"{r['env']}: new={r['n_new']} old={r['n_old']} "
              f"cmp={r['n_cmp']} field_mismatch={n_bad} "
              f"only_new={r['only_new']} only_old={r['only_old']} "
              f"-> {'PASS' if passed else 'FAIL'}", flush=True)

    md += ["", f"\n## 总判定: {'PASS(全 0)' if ok else 'FAIL'}"]
    OUT.write_text("\n".join(md) + "\n")
    print("done ->", OUT)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
