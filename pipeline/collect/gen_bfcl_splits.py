#!/usr/bin/env python3
"""Generate BFCL multi_turn_base's three problem sets (train/val/test), for pipeline/annotate/build.py to split batches with.

Question to answer: of BFCL's 200 multi_turn_base task instances, which 140 are
train, which 40 are val, and which 20 are test?

**BFCL has no official train/val/test partition** -- it is a pure eval leaderboard.
On this machine, bfcl_eval==2026.3.23's data/ directory only has eval files split
by test category; `BFCL_v4_multi_turn_base.json` measured has 200 entries, with
fields only ['excluded_function','id','initial_config','involved_classes',
'path','question'], **no split field at all**; constants/category_mapping.py's
TEST_COLLECTION_MAPPING is entirely test sets. (Based on testing the local
install, not verified against upstream docs.)

So, following the ALFWorld precedent's **approach** (see gen_alfworld_splits.py's
file header): when the official release provides no id list, the problem sets
are fixed once in the script and checked into the repo; afterward always use the
checked-in txt. But ALFWorld's sampling rule (equal-proportion stratification
across six classes) is ALFWorld-specific; copying it onto bfcl would be inventing
a new split scheme, so we don't.

Sources of the three sets (freeze the one already used by the old v3_1 line, do
not reshuffle):
    train <- the unit set of envs/bert_data/v3_1/bfcl/train.jsonl   140
    val   <- the unit set of calA.jsonl ∪ calB.jsonl                 40
    test  <- the unit set of test.jsonl                              20

Why freeze instead of re-splitting:
  ① this is not a new split scheme, it is the one the project already has on
     hand;
  ② those 20 test items stay untouched, so the new causal-head numbers and the
     old classification-head bfcl numbers in RESULTS.md land on the same
     ground -- that is exactly the point of this relabeling;
  ③ calA∪calB -> val matches the deviation rule of the appworld line
     (temperature and theta are both set on val).
**Testing ruled out "rerunning the old rule" as an option**:
`random.Random(20260729).shuffle(sorted(units))` cannot reproduce the old three
sets (test overlaps only 1/20) -- the old script envs/collect/build_dataset.py:224's
rng is shared across the three environments, and bfcl comes after
appworld/tales, so the random state is already consumed. Re-running the old
rule would just switch to a different split, throwing away comparability with
the old numbers for nothing.

Known deviations (four, must be reported alongside the numbers):
  1. The problem sets' **derivation source**
     envs/bert_data/v3_1/bfcl/*.jsonl is not in git (.gitignore only lets
     envs/bert_data/**/*.md into the repo). If those four jsonl files are
     deleted, they can never be derived again. So **the checked-in txt is the
     sole source of truth**; the md5 in SPLIT_REPORT.json is only an audit
     trail, not a promise that it can be "regenerated with one command". For
     this reason the script by default **refuses to overwrite** an existing
     problem set whose content differs (overwriting needs an explicit
     --force).
  2. unit granularity = BFCL task instance id (multi_turn_base_N), not a
     trajectory.
  3. The three models share this one problem set, but the number of instances
     actually realized differs (q36 is missing 4 items, gptoss is missing 1
     item -- those trajectories produced not a single usable event), so it is
     not strictly the same set of items across models. The gaps are listed
     item by item by pipeline/annotate/check_callstr.py.
  4. This script **does no random sampling at all** (it freezes the old
     split); SEED is written into the report only as a project-wide rule
     marker.

Usage:
    python3 pipeline/collect/gen_bfcl_splits.py --dry-run
    python3 pipeline/collect/gen_bfcl_splits.py --out-dir pipeline/splits/bfcl_mtb_v1
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

SEED = 20260729                       # Archived seed for the checked-in problem sets; since np821 rules.py/build.py default switched to 42, this file does not follow
V31_DIR = ROOT / "envs/bert_data/v3_1/bfcl"
UNIVERSE = (ROOT / "envs/bfcl/venv/lib/python3.11/site-packages/bfcl_eval"
            / "data/BFCL_v4_multi_turn_base.json")
OUT_DIR = ROOT / "pipeline/splits/bfcl_mtb_v1"

# our set name -> which sets of the old v3_1 line (calA/calB merge into val: temperature and theta are both set on val)
SPLIT_SRC = {
    "train": ("train",),
    "val": ("calA", "calB"),
    "test": ("test",),
}
# Hard-checked line counts (gate G9). The old line's four sets measured 140/20/20/20, which together are exactly 200 = the full set.
EXPECT_N = {"train": 140, "val": 40, "test": 20}


def md5(path):
    """File md5 (read in chunks; some old jsonl files are 120MB)."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_units(path):
    """Old-line jsonl -> that set's unit set (json.loads line by line, taking the unit field)."""
    units = set()
    with open(path) as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                units.add(json.loads(ln)["unit"])
    if not units:
        sys.exit(f"this pile read not a single unit: {path}")
    return units


def read_universe(path):
    """bfcl_eval's full multi_turn_base set -> sorted id list (this is the only official anchor)."""
    ids = []
    with open(path) as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                ids.append(json.loads(ln)["id"])
    if len(ids) != len(set(ids)):
        sys.exit(f"the full set has a duplicate id: {path}")
    return sorted(ids)                # sorting is a precondition for reproducibility, do not remove


def read_txt(path):
    """Checked-in problem-set txt -> unit list ([copied from annotate/build.py:read_unit_list])."""
    txt = Path(path).read_text()
    return [ln.strip() for ln in txt.split("\n") if ln.strip()]


def build_lists(v31dir):
    """-> {'train': [...], 'val': [...], 'test': [...]}, sorted within each set."""
    lists, srcfiles = {}, {}
    for name, srcs in SPLIT_SRC.items():
        units = set()
        for s in srcs:
            p = Path(v31dir) / f"{s}.jsonl"
            if not p.is_file():
                sys.exit(f"old-line pile file does not exist: {p}(the task list can only be derived from here, see deviation 1 in the file header)")
            got = read_units(p)
            if units & got:            # old-line calA/calB should be mutually exclusive, verify it first
                sys.exit(f"old line already overlaps internally: {s} shares {len(units & got)} items with an earlier pile")
            units |= got
            srcfiles[f"{name}:{s}"] = str(p)
        lists[name] = sorted(units)    # sorting is a precondition for reproducibility, do not remove
    return lists, srcfiles


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--v31-dir", default=str(V31_DIR), help="old-line v3_1/bfcl dir")
    ap.add_argument("--universe", default=str(UNIVERSE),
                    help="bfcl_eval's BFCL_v4_multi_turn_base.json (official anchor)")
    ap.add_argument("--out-dir", default=str(OUT_DIR), help="output dir for the three txt files")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--dry-run", action="store_true", help="count only, write no files")
    ap.add_argument("--force", action="store_true",
                    help="allow overwriting a committed task list whose content differs (a frozen split; do not enable this normally)")
    args = ap.parse_args()

    v31dir = Path(args.v31_dir).resolve()
    unipath = Path(args.universe).resolve()
    out = Path(args.out_dir)
    if not v31dir.is_dir():
        sys.exit(f"old-line dir does not exist: {v31dir}")
    if not unipath.is_file():
        sys.exit(f"official full-set file does not exist: {unipath}")

    lists, srcfiles = build_lists(v31dir)
    universe = read_universe(unipath)
    for name in ("train", "val", "test"):
        print(f"[{name:5s}] <- v3_1 {'+'.join(SPLIT_SRC[name]):11s} "
              f"-> {len(lists[name]):4d} tasks")

    # ---------- gate 1: the three sets are pairwise disjoint ----------
    # [copied from the same-named gate in gen_alfworld_splits.py] build.py:196-205's
    # official_split does part[u] = name with last-write-wins and no overlap check;
    # under SPLITS=('train','val','test') order, test is written last and wins, so an
    # overlap would silently let the train/test boundary break down.
    names = list(lists)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            dup = set(lists[a]) & set(lists[b])
            if dup:
                sys.exit(f"task list overlap {a} ∩ {b} = {len(dup)} items, e.g.: {sorted(dup)[:3]}")
    print("[gate 1] the three piles are pairwise disjoint ✓")

    # ---------- gate 2: union == official full set (the only official anchor in this case) ----------
    allu = set().union(*(set(v) for v in lists.values()))
    uni = set(universe)
    if allu != uni:
        sys.exit(f"union of the three piles({len(allu)}) ≠ official full set({len(uni)}):"
                 f"task list has extra {sorted(allu - uni)[:5]};"
                 f"full set is missing {sorted(uni - allu)[:5]}")
    print(f"[gate 2] union of the three piles == official full set {len(uni)} tasks ✓")

    # ---------- gate 3: hard line-count check (G9) ----------
    bad = {n: len(lists[n]) for n in EXPECT_N if len(lists[n]) != EXPECT_N[n]}
    if bad:
        sys.exit(f"task count does not match expectation {bad}, expected {EXPECT_N}")
    print(f"[gate 3] task count {EXPECT_N} matches for every pile ✓")

    # ---------- gate 4: never silently overwrite a frozen problem set ----------
    # The problem set's derivation source is not in git (file-header deviation 1); the checked-in txt is the sole source of truth.
    # Existing and different content = someone is changing the split, must pass --force explicitly.
    changed = []
    for name in EXPECT_N:
        p = out / f"{name}.txt"
        if p.is_file() and read_txt(p) != lists[name]:
            changed.append(name)
    if changed and not args.force:
        sys.exit(f"the committed task list differs from this run's result: {changed};"
                 f"a frozen split may not be silently rewritten -- confirm you want to change the split, then add --force")
    if changed:
        print(f"[gate 4] --force: will rewrite {changed} ⚠")
    else:
        print("[gate 4] no committed task list was rewritten ✓")

    report = {
        "batch": "bfcl_mtb_v1",
        "env": "bfcl",
        "seed": args.seed,
        "seed_used_for": "this script does no random sampling (the old split is frozen); seed is only a pipeline-wide settings marker",
        "split_origin": "freezes the four piles of envs/bert_data/v3_1/bfcl: train/calA∪calB/test",
        "official_split_exists": False,
        "official_split_note":
            "BFCL has no official train/val/test partition (it is a pure eval leaderboard);"
            "the local bfcl_eval's multi_turn_base full set of 200 items has no split field",
        "universe_file": str(unipath),
        "universe_n": len(universe),
        "source_files": srcfiles,
        "md5": {k: md5(v) for k, v in srcfiles.items()} | {
            "universe": md5(unipath)},
        "truth_source": "the committed {train,val,test}.txt is the sole source of truth;"
                        "the md5 above is only an audit trail; the derivation source is not under version control",
        "splits": {n: {"number of tasks in this pile": len(lists[n]),
                       "from v3_1": list(SPLIT_SRC[n])} for n in EXPECT_N},
    }

    if args.dry_run:
        print("\n--dry-run: write no files")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    out.mkdir(parents=True, exist_ok=True)
    for name in EXPECT_N:
        p = out / f"{name}.txt"
        # with a trailing newline (same as the alfworld problem sets), so wc -l gives the true count
        p.write_text("\n".join(lists[name]) + "\n", encoding="utf-8")
        print(f"wrote {p}  ({len(lists[name])} lines)")
    rp = out / "SPLIT_REPORT.json"
    rp.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                  encoding="utf-8")
    print(f"wrote {rp}")


if __name__ == "__main__":
    main()
