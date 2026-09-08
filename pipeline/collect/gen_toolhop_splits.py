#!/usr/bin/env python3
"""Generate ToolHop's three problem sets (train/val/test), for pipeline/annotate/build.py to split batches with.

Question to answer: of ToolHop's 995 multi-hop tool-call questions, which go
into train, which into val, which into test?

**ToolHop has no official split at all** -- measured, envs/toolhop/data/ToolHop.json
(the NFS original, reached through a symlink) is a flat list of 995 entries,
with fields ['id','question','answer','sub_task','tools','functions','domain',
'answer_type','previous_answer_type']; id is an integer 0..994 with no
duplicates and no split field; the upstream README also treats it only as one
whole eval set. So, following the gen_bfcl_splits.py precedent: the split is
fixed here once and checked into the repo, and afterward always use the
checked-in txt.

Self-split rule (all set by this script, 2026-08-02, frozen into DATA.md §9):
  1. Ratio train/val/test = 695/200/100 (approximately 70/20/10, matching
     bfcl_mtb_v1's 140/40/20 ratio).
  2. **Stratify by answer_type** (number 602 / date 165 / string 164 /
     letter 41 / datetime 20 / character 3 -- six clean, unambiguous
     classes). Do not stratify by the domain field: it is free text with
     inconsistent casing ('Film' and 'film' both occur, 80+ values in
     total), so using it as a stratification key would be self-deception.
  3. Each class's quota is filled to the global 100/200 total using the
     largest-remainder method; within each class, shuffle with an
     independent seed random.Random(f"{SEED}:{answer_type}") and then cut
     in test -> val -> train order. Do not share an rng (the bfcl line
     demonstrated the failure mode of sharing a random-number stream, see
     gen_bfcl_splits.py's file header).

unit id shape: the decimal string of the official integer id ("0".."994").
ToolHop's annotate branch is not written yet; the problem set fixes this
convention first, and the collector must use the same shape when it later
writes meta.task_id.

Known deviations (must be reported alongside the numbers):
  1. This is a **pure self-split**, with no official counterpart;
     official_split_exists is recorded as false, forcing the config to
     write split_desc (check_callstr.py's gate E blocks the lie).
  2. The stratification key preserves only the answer_type distribution,
     not the domain / hop-count distribution.
  3. The derivation source ToolHop.json lives on NFS and is not in git;
     the checked-in txt is the sole source of truth, and the md5 is only
     an audit trail.

Usage:
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

SEED = 20260729                       # Archived seed for the checked-in problem sets; since np821 rules.py/build.py default switched to 42, this file does not follow
DATA = ROOT / "envs/toolhop/data/ToolHop.json"
OUT_DIR = ROOT / "pipeline/splits/toolhop_v1"

# Hard-checked line counts (gate G9). 995 = 695 + 200 + 100.
EXPECT_N = {"train": 695, "val": 200, "test": 100}


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_txt(path):
    """Checked-in problem-set txt -> unit list ([copied from annotate/build.py:read_unit_list])."""
    txt = Path(path).read_text()
    return [ln.strip() for ln in txt.split("\n") if ln.strip()]


def lr_alloc(sizes, target, total):
    """Largest remainder method: each stratum takes floor(n*target/total), rounded down; the largest remainders get filled in first until target is reached.
    Ties break by stratum name, for reproducibility."""
    ideal = {s: n * target / total for s, n in sizes.items()}
    base = {s: int(ideal[s]) for s in sizes}
    left = target - sum(base.values())
    order = sorted(sizes, key=lambda s: (-(ideal[s] - base[s]), s))
    for s in order[:left]:
        base[s] += 1
    return base


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(DATA), help="ToolHop.json (official full-set anchor)")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--dry-run", action="store_true", help="count only, write no files")
    ap.add_argument("--force", action="store_true",
                    help="allow overwriting a committed task list whose content differs (frozen split, don't enable this normally)")
    args = ap.parse_args()
    datapath = Path(args.data).resolve()
    out = Path(args.out_dir)
    if not datapath.is_file():
        sys.exit(f"official full-set file does not exist: {datapath}")

    items = json.loads(datapath.read_text())
    ids = [str(x["id"]) for x in items]
    if len(ids) != len(set(ids)):
        sys.exit(f"duplicate ids in the full set: {datapath}")
    total = len(ids)

    # Stratify: answer_type -> sorted id list
    strata = {}
    for x in items:
        strata.setdefault(x["answer_type"], []).append(str(x["id"]))
    strata = {k: sorted(v, key=int) for k, v in strata.items()}
    sizes = {k: len(v) for k, v in strata.items()}
    q_test = lr_alloc(sizes, EXPECT_N["test"], total)
    q_val = lr_alloc(sizes, EXPECT_N["val"], total)
    for s in sizes:
        if q_test[s] + q_val[s] > sizes[s]:
            sys.exit(f"layer {s} quota overflow: test {q_test[s]} + val {q_val[s]} "
                     f"> layer size {sizes[s]}")

    lists = {"train": [], "val": [], "test": []}
    per_stratum = {}
    for s in sorted(sizes):
        pool = list(strata[s])
        random.Random(f"{args.seed}:{s}").shuffle(pool)   # Independent seed per stratum
        te = pool[:q_test[s]]
        va = pool[q_test[s]:q_test[s] + q_val[s]]
        tr = pool[q_test[s] + q_val[s]:]
        lists["test"] += te
        lists["val"] += va
        lists["train"] += tr
        per_stratum[s] = {"layer size": sizes[s], "train": len(tr),
                          "val": len(va), "test": len(te)}
        print(f"[{s:9s}] {sizes[s]:4d} -> train {len(tr):3d} / "
              f"val {len(va):3d} / test {len(te):3d}")
    lists = {k: sorted(v, key=int) for k, v in lists.items()}

    # ---------- Gate 1: the three piles are pairwise disjoint ----------
    names = list(lists)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            dup = set(lists[a]) & set(lists[b])
            if dup:
                sys.exit(f"task list overlap {a} ∩ {b} = {len(dup)} entries, example: {sorted(dup)[:3]}")
    print("[gate 1] the three piles are pairwise disjoint ✓")

    # ---------- Gate 2: union == official full set (the one official anchor) ----------
    allu = set().union(*(set(v) for v in lists.values()))
    uni = set(ids)
    if allu != uni:
        sys.exit(f"union of the three piles ({len(allu)}) ≠ official full set ({len(uni)}):"
                 f"extra {sorted(allu - uni)[:5]}; missing {sorted(uni - allu)[:5]}")
    print(f"[gate 2] union of the three piles == official full set {len(uni)} tasks ✓")

    # ---------- Gate 3: hard line-count check (G9) ----------
    bad = {n: len(lists[n]) for n in EXPECT_N if len(lists[n]) != EXPECT_N[n]}
    if bad:
        sys.exit(f"task count does not match expected {bad}, expected {EXPECT_N}")
    print(f"[gate 3] task count {EXPECT_N} matches per pile ✓")

    # ---------- Gate 4: never silently overwrite a frozen task list ----------
    changed = []
    for name in EXPECT_N:
        p = out / f"{name}.txt"
        if p.is_file() and read_txt(p) != lists[name]:
            changed.append(name)
    if changed and not args.force:
        sys.exit(f"committed task list differs from this run's result: {changed};"
                 f"a frozen split may not be silently rewritten, add --force after confirming you want to change the split")
    if changed:
        print(f"[gate 4] --force: will rewrite {changed} ⚠")
    else:
        print("[gate 4] no committed task list was rewritten ✓")

    report = {
        "batch": "toolhop_v1",
        "env": "toolhop",
        "seed": args.seed,
        "seed_used_for": "pure self-split; each answer_type layer independently "
                         "shuffles with random.Random(f'{seed}:{answer_type}'),"
                         "no shared random stream",
        "split_origin": "pure self-split 695/200/100 (≈70/20/10, matching the bfcl_mtb_v1 ratio),"
                        "stratified into 6 answer_type layers, each layer's quota via largest-remainder method",
        "official_split_exists": False,
        "official_split_note":
            "ToolHop.json is a flat list of 995 entries, no split field, upstream treats it only as one whole eval set",
        "unit_form": "decimal string form of the official integer id ('0'..'994');"
                     "future collectors' meta.task_id must use the same form",
        "universe_file": str(datapath),
        "universe_n": total,
        "md5": {"ToolHop.json": md5(datapath)},
        "truth_source": "the committed {train,val,test}.txt is the sole source of truth;"
                        "the derivation source lives on NFS, not in git, md5 is only an audit trail",
        "strata": per_stratum,
        "splits": {n: {"number of tasks in this pile": len(lists[n])} for n in EXPECT_N},
    }

    if args.dry_run:
        print("\n--dry-run: write no files")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    out.mkdir(parents=True, exist_ok=True)
    for name in EXPECT_N:
        p = out / f"{name}.txt"
        p.write_text("\n".join(lists[name]) + "\n", encoding="utf-8")
        print(f"wrote {p}  ({len(lists[name])} lines)")
    rp = out / "SPLIT_REPORT.json"
    rp.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                  encoding="utf-8")
    print(f"wrote {rp}")


if __name__ == "__main__":
    main()
