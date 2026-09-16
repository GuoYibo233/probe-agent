"""ident3 scoring (pure CPU, stdlib): three arms (chat / noprobe / nofill) x
5 questions x 10 reps, compared token by token, produces
IDENT3_REPORT.{json,md}. Plan: plans/archive/2026-08-18-ident3.md §4.

Input directory structure (laid down by ident3_job.sh):
  <root>/chat/rep<r>/appworld_gptoss/appworld_<tid>.jsonl   (run_appworld --api chat)
  <root>/noprobe/rep<r>/live_<tid>.jsonl                    (live_appworld --no-probe)
  <root>/nofill/rep<r>/live_<tid>.jsonl                     (live_appworld --fire-nth-cut N --nofill)

Each run is extracted into the same shape: the per-step generated token id
list (out_token_ids for chat, gen_ids for live), per-step prompt token
count, success/failure, step count, total generated tokens. Comparison
convention:
- Two runs are "token-for-token identical" = the per-step id sequences are
  all equal and the step counts match; first divergence = the first step
  with an unequal id + the first unequal position within that step;
  cumulative matching token count before the divergence = shared_tok.
- The trailing <|return|> (200002) is stripped before comparison: chat and
  completions may differ in whether the stop token counts into token_ids,
  and this layer of difference does not count as divergence (the report
  lists the end-id distribution of each arm separately).
- Pairs are split into same-arm pairs (chat-chat / noprobe-noprobe /
  nofill-nofill) and cross-arm pairs (chat-noprobe / chat-nofill /
  noprobe-nofill); if the divergence distribution of same-arm pairs and
  cross-arm pairs is the same, there is no meaningful difference between
  arms.
- Report facts only, no interpretation.

Usage:
  python3 pipeline/inject/ident3_score.py --root /net/.../pipeline/inject/runs/ident3_v1
"""

import argparse
import glob
import hashlib
import itertools
import json
import re
import statistics as S
from collections import Counter, defaultdict
from pathlib import Path

ARMS = ("chat", "noprobe", "nofill")
RETURN_ID = 200002          # <|return|>
SUCCESS_RE = re.compile(r"'success': (True|False)")


def _success(ev):
    if isinstance(ev, dict):
        v = ev.get("success")
        return None if v is None else bool(v)
    if isinstance(ev, str):
        m = SUCCESS_RE.search(ev)
        return None if not m else (m.group(1) == "True")
    return None


def ids_sha(ids):
    """Same algorithm as live_appworld.ids_sha (sha1 of the comma-joined string);
    chat stores the whole prompt id sequence, live run stores the sha, and
    computing the same sha on both sides is the id-for-id comparison."""
    return hashlib.sha1(",".join(map(str, ids)).encode()).hexdigest()


def load_run(path, arm):
    recs, bad_lines = [], 0
    with open(path) as f:
        for line in f:
            try:
                recs.append(json.loads(line))
            except json.JSONDecodeError:
                bad_lines += 1            # A half-line left behind by a killed process, count it, don't crash
    gens = [r for r in recs if r.get("type") == "gen"]
    fin = next((r for r in recs if r.get("type") == "final"), None)
    specs = [r for r in recs if r.get("type") == "spec"]
    resumes = [r for r in recs if r.get("type") == "resume"]
    steps_ids, prompt_tok, prompt_sha, gen_tok = [], [], [], []
    for g in gens:
        if arm == "chat":
            ids = g.get("out_token_ids")
            pids = g.get("prompt_token_ids")
            prompt_tok.append(len(pids) if pids is not None else g["usage"]["in"])
            prompt_sha.append(ids_sha(pids) if pids is not None else None)
            gen_tok.append(g["usage"]["out"])
        else:
            ids = g.get("gen_ids")
            prompt_tok.append(g.get("prefix_tok"))
            prompt_sha.append(g.get("prefix_sha"))
            gen_tok.append(g["usage"]["gen_tok"])
        steps_ids.append(list(ids) if ids is not None else None)
    abort = (fin.get("abort") if fin else "NO_FINAL")
    return dict(
        path=str(path), arm=arm, bad_lines=bad_lines,
        steps=fin["steps"] if fin else None,
        completed=fin.get("completed") if fin else None,
        abort=abort,
        success=_success(fin.get("eval")) if fin else None,
        # If any arm has a non-empty abort (live's task_error:*, chat's stepN:Err:*,
        # context hitting the ceiling, no final) it does not enter success/failure
        # or pairing -- keeping the two arms' conventions aligned, so a single
        # server-side fault doesn't sneak into pairing disguised as a "short
        # trajectory"
        excluded=bool(abort),
        n_gen=len(gens), ids=steps_ids, prompt_tok=prompt_tok,
        prompt_sha=prompt_sha,
        gen_tok=gen_tok, gen_tok_total=sum(gen_tok),
        n_inject=sum(g.get("n_inject", 0) for g in gens),
        discard_tok=sum((g.get("discard") or {}).get("tokens", 0) for g in gens),
        inconsistent=sum(1 for g in gens if g.get("text_ids_consistent") is False),
        specs=specs, resumes=resumes,
        last_ids=[s[-1] for s in steps_ids if s])


def discover(root):
    """-> {tid: {arm: {rep: run}}}"""
    runs = defaultdict(lambda: defaultdict(dict))
    for arm in ARMS:
        for rep_dir in sorted(glob.glob(str(root / arm / "rep*"))):
            rep = int(Path(rep_dir).name[3:])
            pat = (f"{rep_dir}/appworld_gptoss/appworld_*.jsonl" if arm == "chat"
                   else f"{rep_dir}/live_*.jsonl")
            for p in sorted(glob.glob(pat)):
                name = Path(p).stem
                tid = name[len("appworld_"):] if arm == "chat" else name[len("live_"):]
                runs[tid][arm][rep] = load_run(p, arm)
    return runs


def strip_tail(ids):
    ids = list(ids)
    while ids and ids[-1] == RETURN_ID:
        ids.pop()
    return ids


def compare(a, b):
    """Compare two runs token by token. Returns
    dict(identical, div_step, div_tok, shared_tok).
    div_step=None means fully identical (including matching step counts).
    If step counts differ but the shared steps are all identical:
    div_step=number of shared steps, div_tok=0. If a step's id is missing
    (old format), record it as not comparable, None."""
    shared = 0
    n = min(len(a["ids"]), len(b["ids"]))
    for s in range(n):
        x, y = a["ids"][s], b["ids"][s]
        if x is None or y is None:
            return dict(identical=None, div_step=None, div_tok=None, shared_tok=None,
                        comparable=False)
        x, y = strip_tail(x), strip_tail(y)
        m = 0
        while m < min(len(x), len(y)) and x[m] == y[m]:
            m += 1
        if m < len(x) or m < len(y):
            return dict(identical=False, div_step=s, div_tok=m,
                        shared_tok=shared + m, comparable=True)
        shared += len(x)
    if len(a["ids"]) != len(b["ids"]):
        return dict(identical=False, div_step=n, div_tok=0, shared_tok=shared,
                    comparable=True)
    return dict(identical=True, div_step=None, div_tok=None, shared_tok=shared,
                comparable=True)


def q(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return None
    xs = sorted(xs)
    return dict(n=len(xs), min=xs[0], med=S.median(xs), max=xs[-1],
                mean=round(S.mean(xs), 2))


def cell(x):
    """markdown table cell: strip the pipes and newlines that would break the table, truncate if long."""
    return str(x).replace("|", "/").replace("\n", " ")[:80]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    root = Path(a.root)
    runs = discover(root)
    rep = dict(root=str(root), tasks={}, pairs={}, pair_list=[], nofill={},
               prompt_check={}, last_ids={}, excluded=[])
    md = [f"# IDENT3 report — {root.name}", ""]

    # ---- 1. Per question, per arm ----
    md += ["## 1. per task, per arm (10 runs)", "",
           "gen_tok has two columns: billed = the total generated tokens the server recorded (for nofill "
           "this includes the discarded overflow from the interruption plus the resumed continuation); "
           "kept = billed - discarded overflow (the same for chat/noprobe). excluded = abort is non-empty "
           "(task_error / a stepN error / hit the context limit / no final), not counted toward success or pairing.", "",
           "| task | arm | n | excluded | success | steps min/med/max | "
           "gen_tok billed med | gen_tok kept med | distinct traj | inconsistent |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for tid in sorted(runs):
        rep["tasks"][tid] = {}
        for arm in ARMS:
            rs = list(runs[tid].get(arm, {}).values())
            if not rs:
                continue
            ok = [r for r in rs if not r["excluded"]]
            for r in rs:
                if r["excluded"]:
                    rep["excluded"].append(dict(tid=tid, arm=arm, path=r["path"],
                                                abort=str(r["abort"])[:200]))
            succ = sum(1 for r in ok if r["success"])
            with_ids = [r for r in ok if all(s is not None for s in r["ids"])]
            distinct = len({json.dumps([strip_tail(s) for s in r["ids"]])
                            for r in with_ids})
            row = dict(n=len(rs), n_ok=len(ok), success=succ,
                       steps=q([r["steps"] for r in ok]),
                       gen_tok_billed=q([r["gen_tok_total"] for r in ok]),
                       gen_tok_kept=q([r["gen_tok_total"] - r["discard_tok"]
                                       for r in ok]),
                       distinct_traj=distinct, n_with_ids=len(with_ids),
                       excluded=len(rs) - len(ok),
                       inconsistent=sum(r["inconsistent"] for r in rs),
                       bad_lines=sum(r["bad_lines"] for r in rs),
                       abort=dict(Counter(str(r["abort"])[:60] for r in rs
                                          if r["abort"])))
            rep["tasks"][tid][arm] = row
            st = row["steps"] or {}
            md.append(f"| {tid} | {arm} | {len(rs)} | {row['excluded']} | "
                      f"{succ}/{len(ok)} | "
                      f"{st.get('min')}/{st.get('med')}/{st.get('max')} | "
                      f"{(row['gen_tok_billed'] or {}).get('med')} | "
                      f"{(row['gen_tok_kept'] or {}).get('med')} | "
                      f"{distinct}/{len(with_ids)} | {row['inconsistent']} |")
    md.append("")
    if rep["excluded"]:
        md += ["excluded runs:", ""] + [
            f"- {e['tid']} {e['arm']}: {cell(e['abort'])}" for e in rep["excluded"]
        ] + [""]

    # ---- 2. Pairwise token-by-token comparison ----
    pair_stats = defaultdict(list)
    for tid in sorted(runs):
        allr = [(arm, r, run) for arm in ARMS
                for r, run in sorted(runs[tid].get(arm, {}).items())
                if not run["excluded"]]
        for (a1, r1, x), (a2, r2, y) in itertools.combinations(allr, 2):
            kind = f"{a1}-{a2}" if ARMS.index(a1) <= ARMS.index(a2) else f"{a2}-{a1}"
            c = compare(x, y)
            c.update(tid=tid, a=f"{a1}:r{r1}", b=f"{a2}:r{r2}", kind=kind)
            pair_stats[kind].append(c)
            rep["pair_list"].append(c)
    md += ["## 2. pairwise token-by-token comparison (same task, excluded runs removed)", "",
           "| pair kind | n pairs | identical | comparable | div step 0 | "
           "div_step med | div_tok med | shared_tok med | shared_tok min |",
           "|---|---|---|---|---|---|---|---|---|"]
    for kind in sorted(pair_stats):
        cs = pair_stats[kind]
        comp = [c for c in cs if c["comparable"]]
        div = [c for c in comp if not c["identical"]]
        row = dict(n=len(cs), comparable=len(comp),
                   identical=sum(1 for c in comp if c["identical"]),
                   div_step0=sum(1 for c in div if c["div_step"] == 0),
                   div_step=q([c["div_step"] for c in div]),
                   div_tok=q([c["div_tok"] for c in div]),
                   shared_tok=q([c["shared_tok"] for c in comp]),
                   div_step_hist=dict(Counter(c["div_step"] for c in div)))
        rep["pairs"][kind] = row
        md.append(f"| {kind} | {row['n']} | {row['identical']} | {row['comparable']} | "
                  f"{row['div_step0']} | {(row['div_step'] or {}).get('med')} | "
                  f"{(row['div_tok'] or {}).get('med')} | "
                  f"{(row['shared_tok'] or {}).get('med')} | "
                  f"{(row['shared_tok'] or {}).get('min')} |")
    md.append("")
    md += ["same-arm pairs = chat-chat / noprobe-noprobe / nofill-nofill; the rest are cross-arm pairs. "
           "div_tok = the first mismatched token position within the diverging step.", ""]
    # Detailed pairing table by question
    md += ["### 2b. by task: identical / n for each pair kind", ""]
    kinds = sorted(pair_stats)
    md += ["| task | " + " | ".join(kinds) + " |", "|---|" + "---|" * len(kinds)]
    for tid in sorted(runs):
        cells = []
        for kind in kinds:
            cs = [c for c in pair_stats[kind] if c["tid"] == tid and c["comparable"]]
            cells.append(f"{sum(1 for c in cs if c['identical'])}/{len(cs)}")
        md.append(f"| {tid} | " + " | ".join(cells) + " |")
    md.append("")

    # ---- 3. Cross-arm prompt id check (steps before divergence + the divergence step): id-for-id compare by sha ----
    n_eq = n_tot = n_len_eq = 0
    mism = []
    for kind, cs in pair_stats.items():
        a1, a2 = kind.split("-")
        if a1 == a2:
            continue
        for c in cs:
            if not c["comparable"]:
                continue
            x = runs[c["tid"]][c["a"].split(":")[0]][int(c["a"].split(":r")[1])]
            y = runs[c["tid"]][c["b"].split(":")[0]][int(c["b"].split(":r")[1])]
            upto = c["div_step"] if c["div_step"] is not None else min(
                len(x["prompt_sha"]), len(y["prompt_sha"]))
            for s in range(min(upto + 1, len(x["prompt_sha"]), len(y["prompt_sha"]))):
                # The prompt at the divergence step itself should also match (the prompt is
                # the history before the divergence)
                if x["prompt_sha"][s] is None or y["prompt_sha"][s] is None:
                    continue
                n_tot += 1
                n_len_eq += (x["prompt_tok"][s] == y["prompt_tok"][s])
                if x["prompt_sha"][s] == y["prompt_sha"][s]:
                    n_eq += 1
                elif len(mism) < 20:
                    mism.append(dict(tid=c["tid"], a=c["a"], b=c["b"], step=s,
                                     len_a=x["prompt_tok"][s], len_b=y["prompt_tok"][s]))
    rep["prompt_check"] = dict(n=n_tot, sha_equal=n_eq, len_equal=n_len_eq,
                               mismatches=mism)
    md += ["## 3. cross-arm prompt id check (steps before the divergence plus the diverging step; sha1 id-by-id comparison)", "",
           f"- sha equal {n_eq} / {n_tot}; length equal {n_len_eq} / {n_tot}"
           f" (should all be equal; unequal means a pipeline problem, see the first 20 in JSON prompt_check.mismatches)", ""]

    # ---- 4. Each arm's end id per step ----
    for arm in ARMS:
        cnt = Counter()
        for tid in runs:
            for run in runs[tid].get(arm, {}).values():
                cnt.update(run["last_ids"])
        rep["last_ids"][arm] = {str(k): v for k, v in cnt.most_common(5)}
    md += ["## 4. last id of each arm's per-step generated id sequence (top-5)", "",
           json.dumps(rep["last_ids"]), ""]

    # ---- 5. nofill only ----
    specs, resumes, n_steps, n_fired = [], [], 0, 0
    for tid in runs:
        for run in runs[tid].get("nofill", {}).values():
            specs += run["specs"]
            resumes += run["resumes"]
            n_steps += run["n_gen"]
            n_fired += run["n_inject"]
    if specs or n_steps:
        idn = [r["identical"] for r in resumes]
        row = dict(n_steps=n_steps, n_fired=n_fired,
                   fire_rate=round(n_fired / n_steps, 3) if n_steps else None,
                   head_ends_ws=dict(Counter(str(s.get("head_ends_ws")) for s in specs)),
                   head_tok=q([s["head_tok"] for s in specs]),
                   head_chars=q([s.get("head_chars") for s in specs]),
                   overflow_tok=q([r["overflow_tok"] for r in resumes]),
                   n_resume=len(resumes),
                   identical=sum(idn),
                   identical_rate=round(sum(idn) / len(idn), 3) if idn else None,
                   match_len=q([r["match_len"] for r in resumes]),
                   match_len_zero=sum(1 for r in resumes if r["match_len"] == 0),
                   match_ratio=q([round(r["match_len"] / r["overflow_tok"], 3)
                                  for r in resumes if r["overflow_tok"]]),
                   finish=dict(Counter(str(r.get("finish")) for r in resumes)))
        rep["nofill"] = row
        md += ["## 5. nofill: interruption-resend ledger", "",
               f"- step count {n_steps}, fired {n_fired} (fire_rate {row['fire_rate']})",
               f"- head ends in whitespace {row['head_ends_ws']}; head_tok {row['head_tok']}; "
               f"head_chars {row['head_chars']}",
               f"- resumed continuation vs discarded overflow: n={len(resumes)}, identical at every position "
               f"{row['identical']} ({row['identical_rate']}), match_len {row['match_len']}, "
               f"count with match_len=0 {row['match_len_zero']}, overflow_tok {row['overflow_tok']}, "
               f"match_ratio {row['match_ratio']}; resumed continuation finish {row['finish']}", ""]

    (root / "IDENT3_REPORT.json").write_text(json.dumps(rep, ensure_ascii=False,
                                                        indent=1, default=str))
    (root / "IDENT3_REPORT.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    print(f"\n-> {root}/IDENT3_REPORT.{{md,json}}")


if __name__ == "__main__":
    main()
