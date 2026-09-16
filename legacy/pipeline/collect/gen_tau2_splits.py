#!/usr/bin/env python3
"""Generate tau2-bench's three problem sets (train/val/test), for pipeline/annotate/build.py to split batches with.

Question to answer: of tau2's three domains' (airline/retail/telecom) official
task instances, which go into train, which into val, which into test?

What the official release provides (measured from
envs/tau2-bench/data/tau2/domains/*/split_tasks.json, 2026-08-02; all three
domains verified train∩test=0 and train∪test==base):

    domain    train  test  base   notes
    airline      30    20    50   base == full set in tasks.json
    retail       74    40   114   base == full set in tasks.json
    telecom      74    40   114   base ⊂ tasks.json (2285 = full expanded set); also a small set of 20

**The official release has only train/test, no val** -- while build.py:33's
SPLITS hard-codes three sets, and eval_tool.py's temperature and theta must
both be set on val. How this is handled (a data-setting-level decision, made
2026-08-02, recorded in DATA.md §9):

    test  <- the official test frozen as-is (not one item touched, to keep the
              same footing as the official leaderboard)
    val   <- drawn from official train, half the size of test: airline 10 /
              retail 20 / telecom 20
    train <- what remains of official train after drawing val

Sampling rule (set by this script itself, not an official rule):
  1. **Independent seed per domain** `random.Random(f"{SEED}:{domain}")` --
     do not share one rng. The bfcl line demonstrated the failure mode of
     sharing an rng: three environments consume the same random-number
     stream, and if any one environment's item count changes, everything
     after it stops matching (gen_bfcl_splits.py file header).
  2. sorted within the domain, then rng.sample, then sorted again --
     sorting is a precondition for reproducibility.
  3. val's share is not stratified (airline/retail's tasks have no type
     field; telecom's issue prefixes spread only 74 items across 8
     classes, so the rounding noise from a stratified quota would be
     worse than uniform sampling).

unit id shape: `<domain>/<task_id>`, matching character for character the
task_id that envs/collect/run_tau2.py writes into meta
(run_tau2.py:419 `unit = f"{domain}/{task.id}"`). telecom's task_id carries
[ ] | characters of its own; one per line in the problem-set txt is fine
(read_unit_list only strips whitespace); escaping for the on-disk filename
(`/`->`__`) is the collector's own business, unrelated to the problem set.

Scope: all three domains are taken in full, telecom at base granularity (114).
telecom's collector is not wired up yet (run_tau2.py --domain currently only
has airline/retail), but the problem set is a data-side matter, and the
official split is already frozen in the upstream repo, so landing it now
costs nothing; if the full 2285 tier is ever needed, open a new version
directory.

Known deviations (must be reported alongside the numbers):
  1. val is not an official set, it is self-split from official train --
     so SPLIT_REPORT records official_split_exists as false, forcing the
     config to write split_desc (check_callstr.py's gate E blocks the lie
     of "printing an official problem set in the report").
  2. telecom's official test contains PERSONA variants that share an
     origin with train's task base (the same issue combination paired
     with different personas), so "no train/test leakage" holds only at
     the task-instance level.
  3. The derivation source split_tasks.json lives in an NFS clone and is
     not in git; the checked-in txt is the sole source of truth, and the
     md5 is only an audit trail.

Usage:
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

SEED = 20260729                       # Archived seed for the checked-in problem sets; since np821 rules.py/build.py default switched to 42, this file does not follow
DOMAINS_DIR = ROOT / "envs/tau2-bench/data/tau2/domains"
OUT_DIR = ROOT / "pipeline/splits/tau2_official_v1"

DOMAINS = ("airline", "retail", "telecom")
VAL_N = {"airline": 10, "retail": 20, "telecom": 20}   # = half of official test
# Hard-checked line counts (gate G9). train = official train - val.
EXPECT_N = {"train": 128, "val": 50, "test": 100}


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


def load_domain(domain):
    """-> (official train id set, official test id set, base id set, dict of source file paths)."""
    ddir = DOMAINS_DIR / domain
    sp_path = ddir / "split_tasks.json"
    tk_path = ddir / "tasks.json"
    for p in (sp_path, tk_path):
        if not p.is_file():
            sys.exit(f"official file does not exist: {p}")
    sp = json.loads(sp_path.read_text())
    task_ids = {t["id"] for t in json.loads(tk_path.read_text())}
    tr, te, ba = set(sp["train"]), set(sp["test"]), set(sp["base"])
    # Official split self-consistency (three checks; failing any one means the upstream data changed, and we must stop)
    if tr & te:
        sys.exit(f"{domain}: official train∩test actually has {len(tr & te)} entries, upstream data anomaly")
    if tr | te != ba:
        sys.exit(f"{domain}: official train∪test != base (differs by "
                 f"{len((tr | te) ^ ba)} entries), upstream data anomaly")
    if not ba <= task_ids:
        sys.exit(f"{domain}: base has ids not in tasks.json: "
                 f"{sorted(ba - task_ids)[:3]}")
    return tr, te, ba, {"split_tasks": str(sp_path), "tasks": str(tk_path)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--dry-run", action="store_true", help="count only, write no files")
    ap.add_argument("--force", action="store_true",
                    help="allow overwriting a committed task list whose content differs (frozen split, don't enable this normally)")
    args = ap.parse_args()
    out = Path(args.out_dir)

    lists = {"train": [], "val": [], "test": []}
    per_domain = {}
    srcfiles, md5s = {}, {}
    universe = set()
    for d in DOMAINS:
        tr, te, ba, srcs = load_domain(d)
        rng = random.Random(f"{args.seed}:{d}")   # independent seed per domain, see rule 1 in the file header
        val = set(rng.sample(sorted(tr), VAL_N[d]))
        train = tr - val
        for name, ids in (("train", train), ("val", val), ("test", te)):
            lists[name] += [f"{d}/{i}" for i in sorted(ids)]
        universe |= {f"{d}/{i}" for i in ba}
        per_domain[d] = {"official train": len(tr), "official test": len(te),
                         "this pile's train": len(train), "this pile's val": len(val),
                         "this pile's test": len(te)}
        for k, v in srcs.items():
            srcfiles[f"{d}:{k}"] = v
            md5s[f"{d}:{k}"] = md5(v)
        print(f"[{d:8s}] official {len(tr)}/{len(te)} -> "
              f"train {len(train)} / val {len(val)} / test {len(te)}")
    lists = {k: sorted(v) for k, v in lists.items()}

    # ---------- gate 1: the three sets are pairwise disjoint ----------
    names = list(lists)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            dup = set(lists[a]) & set(lists[b])
            if dup:
                sys.exit(f"task list overlap {a} ∩ {b} = {len(dup)} entries, example: {sorted(dup)[:3]}")
    print("[gate 1] the three piles are pairwise disjoint ✓")

    # ---------- gate 2: union == the union of the three domains' official base (official anchor) ----------
    allu = set().union(*(set(v) for v in lists.values()))
    if allu != universe:
        sys.exit(f"union of the three piles ({len(allu)}) ≠ official base union ({len(universe)}):"
                 f"extra {sorted(allu - universe)[:3]}; missing {sorted(universe - allu)[:3]}")
    # Extra anchor: this set's test must be character-for-character == official test (the freeze promise)
    for d in DOMAINS:
        te_official = {f"{d}/{i}" for i in load_domain(d)[1]}
        te_ours = {u for u in lists["test"] if u.startswith(f"{d}/")}
        if te_ours != te_official:
            sys.exit(f"{d}: this pile's test does not match official test verbatim, the freeze commitment is broken")
    print(f"[gate 2] union of the three piles == official base union {len(universe)} tasks,"
          f"and each domain's test verbatim == official test ✓")

    # ---------- gate 3: hard line-count check (G9) ----------
    bad = {n: len(lists[n]) for n in EXPECT_N if len(lists[n]) != EXPECT_N[n]}
    if bad:
        sys.exit(f"task count does not match expected {bad}, expected {EXPECT_N}")
    print(f"[gate 3] task count {EXPECT_N} matches per pile ✓")

    # ---------- gate 4: never silently overwrite a frozen problem set ----------
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
        "batch": "tau2_official_v1",
        "env": "tau2",
        "seed": args.seed,
        "seed_used_for": "draw val from each domain's official train; each domain independently uses "
                         "random.Random(f'{seed}:{domain}'), no shared random stream",
        "split_origin": "test=official test unchanged; val=half of test drawn from official train;"
                        "train=the rest of official train",
        "official_split_exists": False,
        "official_split_note":
            "official split_tasks.json only has train/test/base -- two piles plus a base, no val;"
            "val is self-split from official train, so this field records false,"
            "config must write split_desc (check_callstr gate E)",
        "unit_form": "<domain>/<task_id>, matches run_tau2.py meta.task_id verbatim",
        "domains": per_domain,
        "telecom_scope": "base 114 (the granularity covered by the official split); full 2285 needs a separate versioned directory",
        "source_files": srcfiles,
        "md5": md5s,
        "truth_source": "the committed {train,val,test}.txt is the sole source of truth;"
                        "the derivation source lives in the NFS clone, not in git, md5 is only an audit trail",
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
