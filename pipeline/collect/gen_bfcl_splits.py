#!/usr/bin/env python3
"""生成 BFCL multi_turn_base 的三份题单(train/val/test),供 pipeline/annotate/build.py 切堆用。

要回答什么问题:BFCL 的 200 个 multi_turn_base 任务实例,哪 140 个是 train、
哪 40 个是 val、哪 20 个是 test?

**BFCL 没有官方 train/val/test 分区**——它是纯评测榜。本机 bfcl_eval==2026.3.23 的
data/ 目录下只有按 test category 分的评测文件,`BFCL_v4_multi_turn_base.json` 实测
200 条、字段只有 ['excluded_function','id','initial_config','involved_classes',
'path','question'],**无任何 split 字段**;constants/category_mapping.py 的
TEST_COLLECTION_MAPPING 全是 test 集合。(依据是本机安装包实测,未核上游文档。)

所以照 ALFWorld 那条先例的**做法**(见 gen_alfworld_splits.py 文件头):官方不提供
id 清单时,题单在脚本里定一次并入库,之后一律以入库的 txt 为准。但 ALFWorld 的
抽样口径(六类等比例分层)是 ALFWorld 专用的,照搬到 bfcl 上就是自创新切法,不做。

三堆的来源(冻结老线 v3_1 已经用过的那一份,不重新 shuffle):
    train <- envs/bert_data/v3_1/bfcl/train.jsonl 的 unit 集合   140
    val   <- calA.jsonl ∪ calB.jsonl 的 unit 集合                 40
    test  <- test.jsonl 的 unit 集合                              20

为什么冻结而不重切:
  ① 这不是新切法,是工程手里已有的那一份;
  ② test 那 20 题原封不动,新的因果头数字与 RESULTS.md 里老分类头的 bfcl 数字
     落在同一块地上——这正是这批重标的目的;
  ③ calA∪calB→val 与 appworld 那条线的偏离口径一致(温度与 θ 都在 val 上定)。
**实测排除了「重跑老规则」这条路**:`random.Random(20260729).shuffle(sorted(units))`
复现不出老三堆(test 只重合 1/20)——老脚本 envs/collect/build_dataset.py:224 的 rng
是三个环境共用、bfcl 排在 appworld/tales 之后,随机数状态已被消耗。重新执行老规则
等于换一个切分,白丢与老数字的可比性。

已知偏差(四条,必须随数字一起报):
  1. 题单的**推导源** envs/bert_data/v3_1/bfcl/*.jsonl 不在 git 里(.gitignore 只放
     envs/bert_data/**/*.md 进库)。那四个 jsonl 删了就再也推不出来。所以
     **入库的 txt 是唯一真源**,SPLIT_REPORT.json 里的 md5 只是审计线索,
     不是"能一键重生成"的承诺。为此本脚本默认**拒绝覆盖**已存在且内容不同的
     题单(要覆盖得显式 --force)。
  2. unit 粒度 = BFCL 任务实例 id(multi_turn_base_N),不是轨迹。
  3. 三个模型共用这一份题单,但实现出的实例数不一致(q36 缺 4 题、gptoss 缺 1 题,
     那些轨迹一个可用事件都没出),所以跨模型不是严格同题。缺口由
     pipeline/annotate/check_callstr.py 逐条列出。
  4. 本脚本**不做任何随机抽样**(冻结老切分),SEED 只作为全线口径标记写进报告。

用法:
    python3 pipeline/collect/gen_bfcl_splits.py --dry-run
    python3 pipeline/collect/gen_bfcl_splits.py --out-dir pipeline/splits/bfcl_mtb_v1
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

SEED = 20260729                       # 全线固定,与 rules.py / build.py 同值
V31_DIR = ROOT / "envs/bert_data/v3_1/bfcl"
UNIVERSE = (ROOT / "envs/bfcl/venv/lib/python3.11/site-packages/bfcl_eval"
            / "data/BFCL_v4_multi_turn_base.json")
OUT_DIR = ROOT / "pipeline/splits/bfcl_mtb_v1"

# 我们的堆名 -> 老线 v3_1 的哪几堆(calA/calB 合并成 val:温度与 θ 都在 val 上定)
SPLIT_SRC = {
    "train": ("train",),
    "val": ("calA", "calB"),
    "test": ("test",),
}
# 硬核对的行数(门禁 G9)。老线四堆实测 140/20/20/20,合起来正好 200 = 全集。
EXPECT_N = {"train": 140, "val": 40, "test": 20}


def md5(path):
    """文件 md5(分块读,老 jsonl 有 120MB 的)。"""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_units(path):
    """老线 jsonl -> 该堆的 unit 集合(逐行 json.loads 取 unit 字段)。"""
    units = set()
    with open(path) as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                units.add(json.loads(ln)["unit"])
    if not units:
        sys.exit(f"该堆一个 unit 都没读到: {path}")
    return units


def read_universe(path):
    """bfcl_eval 的 multi_turn_base 全集 -> sorted 的 id 列表(这是唯一的官方锚)。"""
    ids = []
    with open(path) as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                ids.append(json.loads(ln)["id"])
    if len(ids) != len(set(ids)):
        sys.exit(f"全集里有重复 id: {path}")
    return sorted(ids)                # 排序是可复现的前提,别删


def read_txt(path):
    """已入库的题单 txt -> unit 列表(【照抄 annotate/build.py:read_unit_list】)。"""
    txt = Path(path).read_text()
    return [ln.strip() for ln in txt.split("\n") if ln.strip()]


def build_lists(v31dir):
    """-> {'train': [...], 'val': [...], 'test': [...]},每堆内部 sorted。"""
    lists, srcfiles = {}, {}
    for name, srcs in SPLIT_SRC.items():
        units = set()
        for s in srcs:
            p = Path(v31dir) / f"{s}.jsonl"
            if not p.is_file():
                sys.exit(f"老线堆文件不存在: {p}(题单只能从这里推,见文件头偏差 1)")
            got = read_units(p)
            if units & got:            # 老线 calA/calB 本应互斥,先验一遍
                sys.exit(f"老线内部就有交叠: {s} 与前序堆重 {len(units & got)} 条")
            units |= got
            srcfiles[f"{name}:{s}"] = str(p)
        lists[name] = sorted(units)    # 排序是可复现的前提,别删
    return lists, srcfiles


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--v31-dir", default=str(V31_DIR), help="老线 v3_1/bfcl 目录")
    ap.add_argument("--universe", default=str(UNIVERSE),
                    help="bfcl_eval 的 BFCL_v4_multi_turn_base.json(官方锚)")
    ap.add_argument("--out-dir", default=str(OUT_DIR), help="三份 txt 的落盘目录")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--dry-run", action="store_true", help="只统计不写文件")
    ap.add_argument("--force", action="store_true",
                    help="允许覆盖已入库且内容不同的题单(冻结的切分,平时别开)")
    args = ap.parse_args()

    v31dir = Path(args.v31_dir).resolve()
    unipath = Path(args.universe).resolve()
    out = Path(args.out_dir)
    if not v31dir.is_dir():
        sys.exit(f"老线目录不存在: {v31dir}")
    if not unipath.is_file():
        sys.exit(f"官方全集文件不存在: {unipath}")

    lists, srcfiles = build_lists(v31dir)
    universe = read_universe(unipath)
    for name in ("train", "val", "test"):
        print(f"[{name:5s}] <- v3_1 {'+'.join(SPLIT_SRC[name]):11s} "
              f"-> {len(lists[name]):4d} 题")

    # ---------- 门禁 1:三堆两两无交集 ----------
    # 【照抄 gen_alfworld_splits.py 的同名门禁】build.py:196-205 的 official_split 是
    # part[u] = name 后写覆盖、零重叠检查,SPLITS=('train','val','test') 顺序下 test
    # 最后写赢,重叠会静默让 train/test 边界失守。
    names = list(lists)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            dup = set(lists[a]) & set(lists[b])
            if dup:
                sys.exit(f"题单交叠 {a} ∩ {b} = {len(dup)} 条,例: {sorted(dup)[:3]}")
    print("[门禁 1] 三堆两两无交集 ✓")

    # ---------- 门禁 2:并集 == 官方全集(本案唯一的官方锚) ----------
    allu = set().union(*(set(v) for v in lists.values()))
    uni = set(universe)
    if allu != uni:
        sys.exit(f"三堆并集({len(allu)})≠ 官方全集({len(uni)}):"
                 f"题单多出 {sorted(allu - uni)[:5]};"
                 f"全集里漏 {sorted(uni - allu)[:5]}")
    print(f"[门禁 2] 三堆并集 == 官方全集 {len(uni)} 题 ✓")

    # ---------- 门禁 3:行数硬核对(G9) ----------
    bad = {n: len(lists[n]) for n in EXPECT_N if len(lists[n]) != EXPECT_N[n]}
    if bad:
        sys.exit(f"题数与预期不符 {bad},预期 {EXPECT_N}")
    print(f"[门禁 3] 题数 {EXPECT_N} 逐堆对上 ✓")

    # ---------- 门禁 4:不静默覆盖已冻结的题单 ----------
    # 题单的推导源不在 git 里(文件头偏差 1),入库的 txt 是唯一真源。
    # 已存在且内容不同 = 有人在换切分,必须显式 --force。
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
        "batch": "bfcl_mtb_v1",
        "env": "bfcl",
        "seed": args.seed,
        "seed_used_for": "本脚本不做随机抽样(冻结老切分),seed 仅作全线口径标记",
        "split_origin": "冻结 envs/bert_data/v3_1/bfcl 的四堆:train/calA∪calB/test",
        "official_split_exists": False,
        "official_split_note":
            "BFCL 无官方 train/val/test 分区(纯评测榜);"
            "本机 bfcl_eval 的 multi_turn_base 全集 200 条无 split 字段",
        "universe_file": str(unipath),
        "universe_n": len(universe),
        "source_files": srcfiles,
        "md5": {k: md5(v) for k, v in srcfiles.items()} | {
            "universe": md5(unipath)},
        "truth_source": "入库的 {train,val,test}.txt 是唯一真源;"
                        "上面的 md5 只是审计线索,推导源不在版本控制里",
        "splits": {n: {"本堆题数": len(lists[n]),
                       "来自 v3_1": list(SPLIT_SRC[n])} for n in EXPECT_N},
    }

    if args.dry_run:
        print("\n--dry-run:不写文件")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    out.mkdir(parents=True, exist_ok=True)
    for name in EXPECT_N:
        p = out / f"{name}.txt"
        # 带末尾换行(与 alfworld 题单同款),wc -l 才是真数
        p.write_text("\n".join(lists[name]) + "\n", encoding="utf-8")
        print(f"写出 {p}  ({len(lists[name])} 行)")
    rp = out / "SPLIT_REPORT.json"
    rp.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                  encoding="utf-8")
    print(f"写出 {rp}")


if __name__ == "__main__":
    main()
