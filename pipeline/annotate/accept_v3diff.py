"""annotate-stage acceptance check: compares the new code's event extraction +
sample construction against the old v3 data byte for byte.

What it does: runs build.py's extraction functions (jsonl_events/bfcl_events) and
the sample-construction function (make_samples) on the same inputs v3 used at the
time (full_v1 + full_v2_topup, **without filtering by model**, without the
official task-list split), and compares against the four piles
envs/bert_data/v3/<env>/{train,calA,calB,test}.jsonl merged together, keyed on
(event, sent_idx). The split method differs, so pile membership is not compared;
the new fields label_call/args_named are not compared either.

Input (read-only): envs/runs/full_v1, envs/runs/full_v2_topup, envs/bert_data/v3
Output: pipeline/annotate/ACCEPT_V3DIFF.md (counts on both sides + per-field
mismatch counts, must all be 0)
Exit code: all 0 -> 0; any mismatch -> 1

Usage: python3 accept_v3diff.py
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
            raise SystemExit(f"unknown environment: {env}")
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

    # Input drift: collection dirs that landed only after v3's database was built
    # (measured: bfcl_gptoss finished collecting 3 hours after v3 was built), simply
    # don't exist in the old data, and should not count as a copy going wrong.
    # The criterion doesn't hardcode dir names: collection dirs that never appeared in
    # the old data are excluded as a whole batch, and named in the report.
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
    md = ["# ACCEPT_V3DIFF -- annotate segment vs v3 old-data consistency acceptance check\n",
          "settings: the new code (rules.py + build.py's jsonl_events/bfcl_events/"
          "make_samples) run on v3's original-year input (full_v1 + full_v2_topup, no model filtering, "
          "no splitting), merged with the four piles from envs/bert_data/v3/<env>, matched by (event, sent_idx) "
          "for comparison; compare " + "/".join(FIELDS) + " nine fields; new fields aren't compared.\n",
          "one settings patch: collection directories that only finished collecting after v3's database build (2026-07-30 00:38) "
          "(bfcl_gptoss, landed 03:48) don't exist in the old data at all; exclude the whole batch before comparing, "
          "the exclusion list is listed per environment in the table below. The criterion doesn't hardcode directory names; it's taken from the old data's own "
          "set of collection directories.\n"]
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
            "| item | value |",
            "|---|---|",
            f"| new-code event count (including drift dirs) | {r['n_events']} |",
            f"| new-code sample count (after excluding drift dirs) | {r['n_new']} |",
            f"| excluded drift collection dirs | {r['drift'] or 'none'} |",
            f"| v3 old sample count (four piles merged) | {r['n_old']} |",
            f"| row-by-row comparisons | {r['n_cmp']} |",
            f"| primary key only on the new side | {r['only_new']} |",
            f"| primary key only on the old side | {r['only_old']} |",
            f"| duplicate primary keys on the new side (beyond the first) | {r['dup_new']} |",
            f"| duplicate primary keys on the old side (beyond the first) | {r['dup_old']} |",
            f"| same primary key, mismatched row counts | {r['mult_mismatch']} |",
            "",
            "per-field mismatch counts:",
            "",
            "| field | " + " | ".join(FIELDS) + " |",
            "|---|" + "---|" * len(FIELDS),
            "| mismatched | " + " | ".join(str(r["bad"][f]) for f in FIELDS)
            + " |",
        ]
        if r["examples"]:
            md += ["", "first mismatch example:"]
            for f, (k, a, b) in sorted(r["examples"].items()):
                md += [f"- `{f}` @ {k}: new={a} old={b}"]
        if r["only_new_ex"] or r["only_old_ex"]:
            md += ["", f"- example present only on the new side: {r['only_new_ex']}",
                   f"- example present only on the old side: {r['only_old_ex']}"]
        print(f"{r['env']}: new={r['n_new']} old={r['n_old']} "
              f"cmp={r['n_cmp']} field_mismatch={n_bad} "
              f"only_new={r['only_new']} only_old={r['only_old']} "
              f"-> {'PASS' if passed else 'FAIL'}", flush=True)

    md += ["", f"\n## overall verdict: {'PASS (all zero)' if ok else 'FAIL'}"]
    OUT.write_text("\n".join(md) + "\n")
    print("done ->", OUT)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
