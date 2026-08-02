#!/usr/bin/env python3
"""生成 tau2-bench 的三份题单(train/val/test),供 pipeline/annotate/build.py 切堆用。

要回答什么问题:tau2 三个 domain(airline/retail/telecom)的官方任务实例,
哪些进 train、哪些进 val、哪些进 test?

官方给了什么(实测 envs/tau2-bench/data/tau2/domains/*/split_tasks.json,
2026-08-02,三个 domain 都验过 train∩test=0 且 train∪test==base):

    domain    train  test  base   备注
    airline      30    20    50   base == tasks.json 全集
    retail       74    40   114   base == tasks.json 全集
    telecom      74    40   114   base ⊂ tasks.json(2285=full 扩展集);另有 small 20

**官方只有 train/test 两堆,没有 val**——而 build.py:33 的 SPLITS 写死三堆,
eval_tool.py 的温度与 θ 都必须在 val 上定。处理办法(数据设定级决定,
2026-08-02 定,记录在 DATA.md §9):

    test  <- 官方 test 原封冻结(一题不动,保住与官方榜的同场地)
    val   <- 从官方 train 里抽 test 数量的一半:airline 10 / retail 20 / telecom 20
    train <- 官方 train 抽剩的部分

抽样口径(本脚本自己定的,不是官方口径):
  1. **每个 domain 独立种子** `random.Random(f"{SEED}:{domain}")`——
     不共用一个 rng。bfcl 那条线实测过共用 rng 的死法:三环境消耗同一个
     随机数流,任何一个环境的题数变了,后面全部对不上(gen_bfcl_splits.py 文件头)。
  2. domain 内 sorted 后 rng.sample,结果再 sorted——排序是可复现的前提。
  3. val 占比不分层(airline/retail 的任务没有类型字段;telecom 的 issue 前缀
     只有 74 题摊 8 类,分层配额四舍五入的噪声比均匀抽还大)。

unit id 形态:`<domain>/<task_id>`,与 envs/collect/run_tau2.py 写进 meta 的
task_id 逐字一致(run_tau2.py:419 `unit = f"{domain}/{task.id}"`)。telecom 的
task_id 自带 [ ] | 字符,在题单 txt 里一行一个没问题(read_unit_list 只 strip 空白);
落盘文件名的转义是采集器自己的事(`/`->`__`),与题单无关。

范围:三个 domain 全收,telecom 取 base 粒度(114)。telecom 采集器还没接
(run_tau2.py --domain 目前只有 airline/retail),但题单是数据侧的事,官方
split 已冻结在上游 repo 里,先落地不吃亏;full 2285 那一档要用的话开新版本目录。

已知偏差(随数字一起报):
  1. val 不是官方堆,是从官方 train 自切的——所以 SPLIT_REPORT 里
     official_split_exists 记 false,逼 config 必须写 split_desc
     (check_callstr.py 门禁 E 会拦"报告里印官方题单"的撒谎文案)。
  2. telecom 的官方 test 里含 PERSONA 变体,与 train 的任务底座有同源关系
     (同一个 issue 组合配不同 persona),"train/test 无泄漏"只在任务实例级成立。
  3. 推导源 split_tasks.json 在 NFS 克隆里、不进 git,入库的 txt 是唯一真源,
     md5 只是审计线索。

用法:
    python3 run.py gen-tau2-splits --dry-run
    python3 run.py gen-tau2-splits
"""
import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

SEED = 20260729                       # 全线固定,与 rules.py / build.py 同值
DOMAINS_DIR = ROOT / "envs/tau2-bench/data/tau2/domains"
OUT_DIR = ROOT / "pipeline/splits/tau2_official_v1"

DOMAINS = ("airline", "retail", "telecom")
VAL_N = {"airline": 10, "retail": 20, "telecom": 20}   # = 官方 test 的一半
# 硬核对的行数(门禁 G9)。train = 官方 train - val。
EXPECT_N = {"train": 128, "val": 50, "test": 100}


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_txt(path):
    """已入库的题单 txt -> unit 列表(【照抄 annotate/build.py:read_unit_list】)。"""
    txt = Path(path).read_text()
    return [ln.strip() for ln in txt.split("\n") if ln.strip()]


def load_domain(domain):
    """-> (官方 train id 集, 官方 test id 集, base id 集, 来源文件路径 dict)。"""
    ddir = DOMAINS_DIR / domain
    sp_path = ddir / "split_tasks.json"
    tk_path = ddir / "tasks.json"
    for p in (sp_path, tk_path):
        if not p.is_file():
            sys.exit(f"官方文件不存在: {p}")
    sp = json.loads(sp_path.read_text())
    task_ids = {t["id"] for t in json.loads(tk_path.read_text())}
    tr, te, ba = set(sp["train"]), set(sp["test"]), set(sp["base"])
    # 官方 split 自洽性(三条,失手任何一条说明上游数据换了,必须停)
    if tr & te:
        sys.exit(f"{domain}: 官方 train∩test 竟有 {len(tr & te)} 条,上游数据异常")
    if tr | te != ba:
        sys.exit(f"{domain}: 官方 train∪test != base(差 "
                 f"{len((tr | te) ^ ba)} 条),上游数据异常")
    if not ba <= task_ids:
        sys.exit(f"{domain}: base 有 id 不在 tasks.json 里: "
                 f"{sorted(ba - task_ids)[:3]}")
    return tr, te, ba, {"split_tasks": str(sp_path), "tasks": str(tk_path)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--dry-run", action="store_true", help="只统计不写文件")
    ap.add_argument("--force", action="store_true",
                    help="允许覆盖已入库且内容不同的题单(冻结的切分,平时别开)")
    args = ap.parse_args()
    out = Path(args.out_dir)

    lists = {"train": [], "val": [], "test": []}
    per_domain = {}
    srcfiles, md5s = {}, {}
    universe = set()
    for d in DOMAINS:
        tr, te, ba, srcs = load_domain(d)
        rng = random.Random(f"{args.seed}:{d}")   # 每域独立种子,见文件头口径 1
        val = set(rng.sample(sorted(tr), VAL_N[d]))
        train = tr - val
        for name, ids in (("train", train), ("val", val), ("test", te)):
            lists[name] += [f"{d}/{i}" for i in sorted(ids)]
        universe |= {f"{d}/{i}" for i in ba}
        per_domain[d] = {"官方 train": len(tr), "官方 test": len(te),
                         "本堆 train": len(train), "本堆 val": len(val),
                         "本堆 test": len(te)}
        for k, v in srcs.items():
            srcfiles[f"{d}:{k}"] = v
            md5s[f"{d}:{k}"] = md5(v)
        print(f"[{d:8s}] 官方 {len(tr)}/{len(te)} -> "
              f"train {len(train)} / val {len(val)} / test {len(te)}")
    lists = {k: sorted(v) for k, v in lists.items()}

    # ---------- 门禁 1:三堆两两无交集 ----------
    names = list(lists)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            dup = set(lists[a]) & set(lists[b])
            if dup:
                sys.exit(f"题单交叠 {a} ∩ {b} = {len(dup)} 条,例: {sorted(dup)[:3]}")
    print("[门禁 1] 三堆两两无交集 ✓")

    # ---------- 门禁 2:并集 == 三 domain 官方 base 之并(官方锚) ----------
    allu = set().union(*(set(v) for v in lists.values()))
    if allu != universe:
        sys.exit(f"三堆并集({len(allu)})≠ 官方 base 并集({len(universe)}):"
                 f"多出 {sorted(allu - universe)[:3]};漏 {sorted(universe - allu)[:3]}")
    # 附加锚:本堆 test 必须逐字 == 官方 test(冻结承诺)
    for d in DOMAINS:
        te_official = {f"{d}/{i}" for i in load_domain(d)[1]}
        te_ours = {u for u in lists["test"] if u.startswith(f"{d}/")}
        if te_ours != te_official:
            sys.exit(f"{d}: 本堆 test 与官方 test 不逐字相等,冻结承诺被破")
    print(f"[门禁 2] 三堆并集 == 官方 base 并集 {len(universe)} 题,"
          f"且各域 test 逐字 == 官方 test ✓")

    # ---------- 门禁 3:行数硬核对(G9) ----------
    bad = {n: len(lists[n]) for n in EXPECT_N if len(lists[n]) != EXPECT_N[n]}
    if bad:
        sys.exit(f"题数与预期不符 {bad},预期 {EXPECT_N}")
    print(f"[门禁 3] 题数 {EXPECT_N} 逐堆对上 ✓")

    # ---------- 门禁 4:不静默覆盖已冻结的题单 ----------
    changed = []
    for name in EXPECT_N:
        p = out / f"{name}.txt"
        if p.is_file() and read_txt(p) != lists[name]:
            changed.append(name)
    if changed and not args.force:
        sys.exit(f"已入库题单与本次结果不同: {changed};"
                 f"冻结的切分不许静默改写,确认要换切分再加 --force")
    if changed:
        print(f"[门禁 4] --force:将改写 {changed} ⚠")
    else:
        print("[门禁 4] 未改写任何已入库题单 ✓")

    report = {
        "batch": "tau2_official_v1",
        "env": "tau2",
        "seed": args.seed,
        "seed_used_for": "从各域官方 train 抽 val;每域独立 "
                         "random.Random(f'{seed}:{domain}'),不共用随机数流",
        "split_origin": "test=官方 test 原封;val=官方 train 抽 test 半数;"
                        "train=官方 train 抽剩",
        "official_split_exists": False,
        "official_split_note":
            "官方 split_tasks.json 只有 train/test/base 两堆一底,没有 val;"
            "val 是从官方 train 自切的,所以此字段记 false,"
            "config 必须写 split_desc(check_callstr 门禁 E)",
        "unit_form": "<domain>/<task_id>,与 run_tau2.py meta.task_id 逐字一致",
        "domains": per_domain,
        "telecom_scope": "base 114(官方切分覆盖的粒度);full 2285 要用另开版本目录",
        "source_files": srcfiles,
        "md5": md5s,
        "truth_source": "入库的 {train,val,test}.txt 是唯一真源;"
                        "推导源在 NFS 克隆里、不进 git,md5 只是审计线索",
        "splits": {n: {"本堆题数": len(lists[n])} for n in EXPECT_N},
    }

    if args.dry_run:
        print("\n--dry-run:不写文件")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    out.mkdir(parents=True, exist_ok=True)
    for name in EXPECT_N:
        p = out / f"{name}.txt"
        p.write_text("\n".join(lists[name]) + "\n", encoding="utf-8")
        print(f"写出 {p}  ({len(lists[name])} 行)")
    rp = out / "SPLIT_REPORT.json"
    rp.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                  encoding="utf-8")
    print(f"写出 {rp}")


if __name__ == "__main__":
    main()
