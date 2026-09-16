#!/usr/bin/env python3
"""Generate ALFWorld's three problem sets (train/val/test), for pipeline/annotate/build.py to split batches with.

ALFWorld's official release does **not provide** an id list file; the official way to
enumerate is to walk the directory, and the walk order is os.walk's filesystem
order, which is not guaranteed consistent across machines. So the problem sets
must be generated here once and checked into the repo; afterward always use the
checked-in txt, never depend on the runtime directory walk order again.

Sources of the three sets (official partition, verified pairwise disjoint at
trial level):
    train <- json_2.1.1/train         stratified sample of N items
    val   <- json_2.1.1/valid_seen    full set
    test  <- json_2.1.1/valid_unseen  full set

unit id shape (matches the community de facto standard, the last two levels of
the gamefile path):
    pick_cool_then_place_in_recep-Lettuce-None-CounterTop-10/trial_T20190909_174840_771703

train sampling rules (two, both set by this script itself, not an official rule):
  1. Stratify the six task types in **equal proportion** -- the raw train
     distribution is heavily skewed (pick_two 813 vs look_at 308), while the
     test side is close to uniform (17-31). Without stratifying, the probe
     would skew toward pick_two.
  2. Take **at most one trial per task config** (L1 directory) -- train's 1465
     configs spread across 3553 trials; one per config lets N items cover N
     distinct configs, maximizing diversity.

Usage:
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

SEED = 20260729                       # Archived seed for the checked-in problem sets; since np821 rules.py/build.py default switched to 42, this file does not follow
SPLIT_SRC = {                         # our set name -> ALFWorld official partition directory name
    "train": "train",
    "val": "valid_seen",
    "test": "valid_unseen",
}
# Two variant types ALFWorld itself excludes (same condition as alfred_tw_env.collect_game_files)
EXCLUDE = ("movable", "Sliced")


def scan(split_dir):
    """Return all unit ids under this partition (sorted), shaped like '<task_config>/<trial>'."""
    units = []
    for gf in split_dir.rglob("game.tw-pddl"):
        rel = gf.relative_to(split_dir)
        if len(rel.parts) != 3:       # expects <task_config>/<trial>/game.tw-pddl
            sys.exit(f"unexpected directory level: {gf}")
        if any(x in rel.parts[0] for x in EXCLUDE):
            continue
        units.append(f"{rel.parts[0]}/{rel.parts[1]}")
    return sorted(units)              # sorting is a precondition for reproducibility, do not remove


def task_type(unit):
    """Extract the six-class task name from a unit id, e.g. 'pick_cool_then_place_in_recep-Lettuce-...' -> prefix."""
    return unit.split("/")[0].split("-")[0]


def stratified_sample(units, n, seed):
    """Six classes in equal proportion + at most one per task config. Returns (sampling result, stats dict)."""
    rng = random.Random(seed)

    # Keep only one trial per task config (sort within the config, then pick randomly, to keep it reproducible)
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
        if len(pool) < want:          # not enough configs for some class, note it down to fill in later
            shortfall[t] = want - len(pool)
            picked.extend(pool)
        else:
            picked.extend(rng.sample(pool, want))

    # if there is a shortfall, fill it from the remaining pool of other classes, to keep the total exactly n
    if shortfall:
        rest = sorted(set(one_per_cfg) - set(picked))
        need = sum(shortfall.values())
        picked.extend(rng.sample(rest, min(need, len(rest))))

    stats = {
        "total configs": len(by_cfg),
        "after taking one per config": len(one_per_cfg),
        "quota per category": quota,
        "quota gap": shortfall,
        "actually drawn": len(picked),
    }
    return sorted(picked), stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", required=True, help="json_2.1.1 dir")
    ap.add_argument("--out-dir", required=True, help="output dir for the three txt files")
    ap.add_argument("--n-train", type=int, default=200)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--dry-run", action="store_true", help="count only, write no files")
    args = ap.parse_args()

    root = Path(args.data_root).resolve()
    out = Path(args.out_dir)
    if not root.is_dir():
        sys.exit(f"data dir does not exist: {root}")

    lists, report = {}, {"data_root": str(root), "seed": args.seed, "splits": {}}

    for name, srcname in SPLIT_SRC.items():
        src = root / srcname
        if not src.is_dir():
            sys.exit(f"official partition dir does not exist: {src}")
        allu = scan(src)
        if not allu:
            sys.exit(f"partition {srcname} found no game.tw-pddl at all")

        if name == "train":
            units, stats = stratified_sample(allu, args.n_train, args.seed)
        else:
            units, stats = allu, {"sampling method": "full set"}

        lists[name] = units
        by_type = defaultdict(int)
        for u in units:
            by_type[task_type(u)] += 1
        report["splits"][name] = {
            "official partition": srcname,
            "partition full set": len(allu),
            "number of tasks in this pile": len(units),
            "number of task configs": len({u.split("/")[0] for u in units}),
            "distribution across six categories": dict(sorted(by_type.items())),
            "sampling stats": stats,
        }
        print(f"[{name:5s}] <- {srcname:13s} full set {len(allu):5d} -> drew {len(units):4d} "
              f"(configs {len({u.split('/')[0] for u in units})})")
        for t, c in sorted(by_type.items()):
            print(f"          {t:32s} {c:4d}")

    # Gate: the three sets are pairwise disjoint. build.py stays silent when "the same unit
    # lands in two problem sets" -- it writes last in train->val->test order and overwrites,
    # silently letting the train/test boundary break down.
    names = list(lists)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            dup = set(lists[a]) & set(lists[b])
            if dup:
                sys.exit(f"task list overlap {a} ∩ {b} = {len(dup)} items, e.g.: {sorted(dup)[:3]}")
    print("\n[gate] the three piles are pairwise disjoint ✓")

    # Gate: every unit's game.tw-pddl must actually exist
    missing = [u for name, us in lists.items() for u in us
               if not (root / SPLIT_SRC[name] / u / "game.tw-pddl").is_file()]
    if missing:
        sys.exit(f"{len(missing)} units have a game.tw-pddl that does not exist, e.g.: {missing[:3]}")
    print("[gate] every unit's game.tw-pddl exists ✓")

    if args.dry_run:
        print("\n--dry-run: write no files")
        return

    out.mkdir(parents=True, exist_ok=True)
    for name, units in lists.items():
        p = out / f"{name}.txt"
        p.write_text("\n".join(units) + "\n", encoding="utf-8")
        print(f"wrote {p}  ({len(units)} lines)")
    rp = out / "SPLIT_REPORT.json"
    rp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {rp}")


if __name__ == "__main__":
    main()
