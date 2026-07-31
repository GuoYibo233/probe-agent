#!/usr/bin/env python3
"""生成 ALFWorld 的三份题单(train/val/test),供 pipeline/annotate/build.py 切堆用。

ALFWorld 官方**不提供** id 清单文件,官方的枚举方式是遍历目录,而遍历顺序是
os.walk 的文件系统序、跨机不保证一致。所以题单必须在这里生成一次并入库,
之后一律以入库的 txt 为准,不再依赖运行时的目录遍历顺序。

三堆的来源(官方分区,已实测 trial 级两两无交集):
    train <- json_2.1.1/train         分层抽样 N 条
    val   <- json_2.1.1/valid_seen    全量
    test  <- json_2.1.1/valid_unseen  全量

unit id 形态(与社区事实标准一致,取 gamefile 路径的后两级):
    pick_cool_then_place_in_recep-Lettuce-None-CounterTop-10/trial_T20190909_174840_771703

train 抽样口径(两条,都是本脚本自己定的,不是官方口径):
  1. 六类任务**等比例**分层——原始 train 分布严重倾斜(pick_two 813 vs look_at 308),
     而 test 侧接近均匀(17-31)。不分层会让探针偏向 pick_two。
  2. 每个任务配置(L1 目录)**最多取一条 trial**——train 的 1465 个配置摊着 3553 条
     trial,每配置一条能让 N 条覆盖 N 个不同配置,多样性最大。

用法:
    python3 pipeline/collect/gen_alfworld_splits.py \
        --data-root envs/alfworld/data/json_2.1.1 \
        --out-dir   envs/alfworld/splits \
        --n-train   200
"""
import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

SEED = 20260729                       # 全线固定,与 rules.py / build.py 同值
SPLIT_SRC = {                         # 我们的堆名 -> ALFWorld 官方分区目录名
    "train": "train",
    "val": "valid_seen",
    "test": "valid_unseen",
}
# ALFWorld 自己排除的两类变体(alfred_tw_env.collect_game_files 的同款条件)
EXCLUDE = ("movable", "Sliced")


def scan(split_dir):
    """返回该分区下全部 unit id(排序后),形如 '<task_config>/<trial>'。"""
    units = []
    for gf in split_dir.rglob("game.tw-pddl"):
        rel = gf.relative_to(split_dir)
        if len(rel.parts) != 3:       # 期望 <task_config>/<trial>/game.tw-pddl
            sys.exit(f"意外的目录层级: {gf}")
        if any(x in rel.parts[0] for x in EXCLUDE):
            continue
        units.append(f"{rel.parts[0]}/{rel.parts[1]}")
    return sorted(units)              # 排序是可复现的前提,别删


def task_type(unit):
    """从 unit id 取六类任务名,例 'pick_cool_then_place_in_recep-Lettuce-...' -> 前缀。"""
    return unit.split("/")[0].split("-")[0]


def stratified_sample(units, n, seed):
    """六类等比例 + 每个任务配置最多一条。返回 (抽样结果, 统计字典)。"""
    rng = random.Random(seed)

    # 每个任务配置只留一条 trial(配置内先排序再随机挑,保证可复现)
    by_cfg = defaultdict(list)
    for u in units:
        by_cfg[u.split("/")[0]].append(u)
    one_per_cfg = sorted(rng.choice(sorted(v)) for v in by_cfg.values())

    by_type = defaultdict(list)
    for u in one_per_cfg:
        by_type[task_type(u)].append(u)

    types = sorted(by_type)
    base, extra = divmod(n, len(types))
    quota = {t: base + (1 if i < extra else 0) for i, t in enumerate(types)}

    picked, shortfall = [], {}
    for t in types:
        pool = sorted(by_type[t])
        want = quota[t]
        if len(pool) < want:          # 某类配置数不够,记下来后面补
            shortfall[t] = want - len(pool)
            picked.extend(pool)
        else:
            picked.extend(rng.sample(pool, want))

    # 有缺口就从其余类的剩余池里补齐,保证总数正好是 n
    if shortfall:
        rest = sorted(set(one_per_cfg) - set(picked))
        need = sum(shortfall.values())
        picked.extend(rng.sample(rest, min(need, len(rest))))

    stats = {
        "配置总数": len(by_cfg),
        "每配置取一条后": len(one_per_cfg),
        "每类配额": quota,
        "配额缺口": shortfall,
        "实际抽出": len(picked),
    }
    return sorted(picked), stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", required=True, help="json_2.1.1 目录")
    ap.add_argument("--out-dir", required=True, help="三份 txt 的落盘目录")
    ap.add_argument("--n-train", type=int, default=200)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--dry-run", action="store_true", help="只统计不写文件")
    args = ap.parse_args()

    root = Path(args.data_root).resolve()
    out = Path(args.out_dir)
    if not root.is_dir():
        sys.exit(f"数据目录不存在: {root}")

    lists, report = {}, {"data_root": str(root), "seed": args.seed, "splits": {}}

    for name, srcname in SPLIT_SRC.items():
        src = root / srcname
        if not src.is_dir():
            sys.exit(f"官方分区目录不存在: {src}")
        allu = scan(src)
        if not allu:
            sys.exit(f"分区 {srcname} 扫不到任何 game.tw-pddl")

        if name == "train":
            units, stats = stratified_sample(allu, args.n_train, args.seed)
        else:
            units, stats = allu, {"取法": "全量"}

        lists[name] = units
        by_type = defaultdict(int)
        for u in units:
            by_type[task_type(u)] += 1
        report["splits"][name] = {
            "官方分区": srcname,
            "分区全量": len(allu),
            "本堆题数": len(units),
            "任务配置数": len({u.split("/")[0] for u in units}),
            "六类分布": dict(sorted(by_type.items())),
            "抽样统计": stats,
        }
        print(f"[{name:5s}] <- {srcname:13s} 全量 {len(allu):5d} -> 取 {len(units):4d} "
              f"(配置 {len({u.split('/')[0] for u in units})})")
        for t, c in sorted(by_type.items()):
            print(f"          {t:32s} {c:4d}")

    # 门禁:三堆两两无交集。build.py 对"同一 unit 落进两份题单"一声不吭,
    # 会按 train->val->test 顺序后写覆盖,静默让 train/test 边界失守。
    names = list(lists)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            dup = set(lists[a]) & set(lists[b])
            if dup:
                sys.exit(f"题单交叠 {a} ∩ {b} = {len(dup)} 条,例: {sorted(dup)[:3]}")
    print("\n[门禁] 三堆两两无交集 ✓")

    # 门禁:每条 unit 的 game.tw-pddl 必须真实存在
    missing = [u for name, us in lists.items() for u in us
               if not (root / SPLIT_SRC[name] / u / "game.tw-pddl").is_file()]
    if missing:
        sys.exit(f"有 {len(missing)} 条 unit 的 game.tw-pddl 不存在,例: {missing[:3]}")
    print("[门禁] 全部 unit 的 game.tw-pddl 存在 ✓")

    if args.dry_run:
        print("\n--dry-run:不写文件")
        return

    out.mkdir(parents=True, exist_ok=True)
    for name, units in lists.items():
        p = out / f"{name}.txt"
        p.write_text("\n".join(units) + "\n", encoding="utf-8")
        print(f"写出 {p}  ({len(units)} 行)")
    rp = out / "SPLIT_REPORT.json"
    rp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写出 {rp}")


if __name__ == "__main__":
    main()
