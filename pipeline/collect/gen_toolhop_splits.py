#!/usr/bin/env python3
"""生成 ToolHop 的三份题单(train/val/test),供 pipeline/annotate/build.py 切堆用。

要回答什么问题:ToolHop 的 995 道多跳工具调用题,哪些进 train、哪些进 val、
哪些进 test?

**ToolHop 没有任何官方切分**——实测 envs/toolhop/data/ToolHop.json(NFS 本体,
软链穿透)是 995 条的平铺列表,字段 ['id','question','answer','sub_task','tools',
'functions','domain','answer_type','previous_answer_type'],id 为 0..994 的整数、
无重复,无 split 字段;上游 README 也只把它当整卷评测集用。所以照
gen_bfcl_splits.py 的先例:切分在这里定一次并入库,之后一律以入库的 txt 为准。

自切口径(全部是本脚本定的,2026-08-02,冻结进 DATA.md §9):
  1. 比例 train/val/test = 695/200/100(≈70/20/10,对齐 bfcl_mtb_v1 的
     140/40/20 比例)。
  2. **按 answer_type 分层**(number 602 / date 165 / string 164 / letter 41 /
     datetime 20 / character 3——六类干净无歧义)。不用 domain 字段分层:
     它是自由文本,大小写混乱('Film' 与 'film' 并存,共 80+ 个取值),
     当分层键就是自欺。
  3. 每层配额用最大余数法凑齐全局 100/200,层内独立种子
     random.Random(f"{SEED}:{answer_type}") 洗牌后按 test→val→train 顺序切。
     不共用 rng(bfcl 线实测过共用随机数流的死法,见 gen_bfcl_splits.py 文件头)。

unit id 形态:官方整数 id 的十进制字符串("0".."994")。ToolHop 的 annotate
分支还没写,题单先定下这个约定;将来采集器写 meta.task_id 时必须用同一形态。

已知偏差(随数字一起报):
  1. 这是**纯自切**,不存在官方对照,official_split_exists 记 false,
     config 必须写 split_desc(check_callstr.py 门禁 E 会拦撒谎文案)。
  2. 分层键只保 answer_type 分布,不保 domain / 跳数分布。
  3. 推导源 ToolHop.json 在 NFS 上、不进 git,入库的 txt 是唯一真源,
     md5 只是审计线索。

用法:
    python3 run.py gen-toolhop-splits --dry-run
    python3 run.py gen-toolhop-splits
"""
import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

SEED = 20260729                       # 已入库题单的档案种子;np821 起 rules.py/build.py 缺省已换 42,本文件不跟随
DATA = ROOT / "envs/toolhop/data/ToolHop.json"
OUT_DIR = ROOT / "pipeline/splits/toolhop_v1"

# 硬核对的行数(门禁 G9)。995 = 695 + 200 + 100。
EXPECT_N = {"train": 695, "val": 200, "test": 100}


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


def lr_alloc(sizes, target, total):
    """最大余数法:每层按 n*target/total 取整,余数大者先补,直到凑齐 target。
    平局按层名排序,保证可复现。"""
    ideal = {s: n * target / total for s, n in sizes.items()}
    base = {s: int(ideal[s]) for s in sizes}
    left = target - sum(base.values())
    order = sorted(sizes, key=lambda s: (-(ideal[s] - base[s]), s))
    for s in order[:left]:
        base[s] += 1
    return base


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(DATA), help="ToolHop.json(官方全集锚)")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--dry-run", action="store_true", help="只统计不写文件")
    ap.add_argument("--force", action="store_true",
                    help="允许覆盖已入库且内容不同的题单(冻结的切分,平时别开)")
    args = ap.parse_args()
    datapath = Path(args.data).resolve()
    out = Path(args.out_dir)
    if not datapath.is_file():
        sys.exit(f"官方全集文件不存在: {datapath}")

    items = json.loads(datapath.read_text())
    ids = [str(x["id"]) for x in items]
    if len(ids) != len(set(ids)):
        sys.exit(f"全集里有重复 id: {datapath}")
    total = len(ids)

    # 分层:answer_type -> sorted id 列表
    strata = {}
    for x in items:
        strata.setdefault(x["answer_type"], []).append(str(x["id"]))
    strata = {k: sorted(v, key=int) for k, v in strata.items()}
    sizes = {k: len(v) for k, v in strata.items()}
    q_test = lr_alloc(sizes, EXPECT_N["test"], total)
    q_val = lr_alloc(sizes, EXPECT_N["val"], total)
    for s in sizes:
        if q_test[s] + q_val[s] > sizes[s]:
            sys.exit(f"层 {s} 配额溢出: test {q_test[s]} + val {q_val[s]} "
                     f"> 层大小 {sizes[s]}")

    lists = {"train": [], "val": [], "test": []}
    per_stratum = {}
    for s in sorted(sizes):
        pool = list(strata[s])
        random.Random(f"{args.seed}:{s}").shuffle(pool)   # 层内独立种子
        te = pool[:q_test[s]]
        va = pool[q_test[s]:q_test[s] + q_val[s]]
        tr = pool[q_test[s] + q_val[s]:]
        lists["test"] += te
        lists["val"] += va
        lists["train"] += tr
        per_stratum[s] = {"层大小": sizes[s], "train": len(tr),
                          "val": len(va), "test": len(te)}
        print(f"[{s:9s}] {sizes[s]:4d} -> train {len(tr):3d} / "
              f"val {len(va):3d} / test {len(te):3d}")
    lists = {k: sorted(v, key=int) for k, v in lists.items()}

    # ---------- 门禁 1:三堆两两无交集 ----------
    names = list(lists)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            dup = set(lists[a]) & set(lists[b])
            if dup:
                sys.exit(f"题单交叠 {a} ∩ {b} = {len(dup)} 条,例: {sorted(dup)[:3]}")
    print("[门禁 1] 三堆两两无交集 ✓")

    # ---------- 门禁 2:并集 == 官方全集(唯一的官方锚) ----------
    allu = set().union(*(set(v) for v in lists.values()))
    uni = set(ids)
    if allu != uni:
        sys.exit(f"三堆并集({len(allu)})≠ 官方全集({len(uni)}):"
                 f"多出 {sorted(allu - uni)[:5]};漏 {sorted(uni - allu)[:5]}")
    print(f"[门禁 2] 三堆并集 == 官方全集 {len(uni)} 题 ✓")

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
        "batch": "toolhop_v1",
        "env": "toolhop",
        "seed": args.seed,
        "seed_used_for": "纯自切;每个 answer_type 层独立 "
                         "random.Random(f'{seed}:{answer_type}') 洗牌,"
                         "不共用随机数流",
        "split_origin": "纯自切 695/200/100(≈70/20/10,对齐 bfcl_mtb_v1 比例),"
                        "按 answer_type 六类分层,每层配额最大余数法",
        "official_split_exists": False,
        "official_split_note":
            "ToolHop.json 是 995 条平铺列表,无 split 字段,上游只当整卷评测集用",
        "unit_form": "官方整数 id 的十进制字符串('0'..'994');"
                     "将来采集器 meta.task_id 必须用同一形态",
        "universe_file": str(datapath),
        "universe_n": total,
        "md5": {"ToolHop.json": md5(datapath)},
        "truth_source": "入库的 {train,val,test}.txt 是唯一真源;"
                        "推导源在 NFS 上、不进 git,md5 只是审计线索",
        "strata": per_stratum,
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
