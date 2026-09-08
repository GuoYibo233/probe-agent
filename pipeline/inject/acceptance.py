"""Compute-savings accounting for questions A and C: how much of the small model's draft the large model accepts. Spec:
plans/2026-08-01-splice-impl-spec.md §D4

This script does not change the experiment; it just uses the already-finished switch_only arm as the reference for
"the large model writing the whole call itself," and answers two questions:

- A (tool-name acceptance rate): is the probe's predicted tool name pred_label the same as the tool name in the call the
  large model wrote itself? Only if they match does "guess the tool name first to prefetch" hold up.
- C (how far the parameter pipeline's draft gets accepted): encode both the whole gen_call written by cgen and the
  call_out written by the large model with the gpt-oss tokenizer, and take the longest common prefix. However long that
  prefix is, that's how many steps this draft can save in speculative decoding -- this is the only hard convention for the
  compute-savings account, a character-level "looks similar" does not count.

C's default path goes through tokenizer comparison and needs no service; only with --base-url does it run the fallback
exact path: feed the whole "prompt + draft" string to vLLM's completions, with echo=True + logprobs + max_tokens=0, and
check token by token whether it is top-1; the first one that is not is the rejection point. If both paths are run, report
the disagreement rate.

Usage (default path, pure CPU):
  cprobe-env/bin/python pipeline/inject/acceptance.py \\
      --run-dir pipeline/inject/runs/aw_gptoss_splice
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import parse_call                                            # noqa: E402
from build_form_table import load_table, skeleton            # noqa: E402
from extract_completed import rebuild_sides                  # noqa: E402

DEFAULT_TOKENIZER = ("/net/tokyo100-10g/data/str01_01/y-guo/models/"
                     "gpt-oss-120b")
# spec §pins down the naming; the fallback exact path has to re-assemble the prompt the same way as the run segment for it to line up
SWITCH = "<|end|><|start|>assistant<|channel|>final<|message|>"


def pct(xs, q):
    """Quantile, nearest-rank method (no interpolation when the sample size is small, to avoid reporting a number that never occurred)."""
    if not xs:
        return None
    s = sorted(xs)
    i = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[i]


def lcp(a, b):
    """Longest common prefix length."""
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def load_switch_only(d, tag):
    """The switch_only arm's records in per_event<tag>.jsonl, indexed by event."""
    p = d / f"per_event{tag}.jsonl"
    if not p.exists():
        raise SystemExit(f"missing {p}; both part A and part C need the switch_only arm's scoring records")
    out = {}
    for line in open(p):
        r = json.loads(line)
        if r.get("arm") == "switch_only":
            out[r["event"]] = r
    if not out:
        raise SystemExit(f"{p} has no switch_only arm -- run this arm first, then do the acceptance check")
    return out


def part_a(plan, sw):
    """A: pred_label == switch_only's tool_out.

    The denominator is events where "the probe gave a tool name". Events where the large model wrote no call at all at this
    step (tool_out is empty) count as not-accepted, not as abstained -- in a real run the prefetch is wasted anyway either
    way, so n_no_tool is listed separately to make it visible, plus a separate accept_rate_of_called computed only on
    events that "wrote a call", for comparison.
    """
    n = hit = no_tool = 0
    miss = Counter()
    for ev, r in sw.items():
        pred = (plan.get(ev) or {}).get("pred_label")
        if pred is None:
            continue
        n += 1
        tool = r.get("tool_out")
        if tool is None:
            no_tool += 1
        elif pred == tool:
            hit += 1
        else:
            miss[f"{pred} -> {tool}"] += 1
    called = n - no_tool
    return dict(n=n, n_hit=hit, n_no_tool=no_tool,
                accept_rate=round(hit / n, 4) if n else None,
                accept_rate_of_called=(round(hit / called, 4)
                                       if called else None),
                top_miss=miss.most_common(10))


def part_c_tok(plan, sw, tok):
    """C: cgen's gen_call vs. switch_only's call_out, longest common prefix at the tokenizer level."""
    rows = []
    skipped = Counter()
    for ev, r in sw.items():
        p = plan.get(ev)
        draft = (p or {}).get("gen_call")
        ref = r.get("call_out")
        if not draft:
            skipped["no_gen_call"] += 1
            continue
        if not ref:
            skipped["no_call_out"] += 1
            continue
        di = tok.encode(draft, add_special_tokens=False)
        ri = tok.encode(ref, add_special_tokens=False)
        if not di:
            skipped["empty_draft"] += 1
            continue
        k = lcp(di, ri)
        rows.append(dict(event=ev, draft=draft, ref=ref,
                         draft_tok=len(di), ref_tok=len(ri),
                         accept_len=k, accept_frac=round(k / len(di), 4),
                         exact=(di == ri)))
    return rows, dict(skipped)


def summarize_c(rows):
    lens = [r["accept_len"] for r in rows]
    fracs = [r["accept_frac"] for r in rows]
    n_exact = sum(1 for r in rows if r["exact"])
    return dict(
        n=len(rows),
        n_exact=n_exact,
        exact_rate=round(n_exact / len(rows), 4) if rows else None,
        accept_len=dict(median=pct(lens, 0.5), p10=pct(lens, 0.10),
                        p90=pct(lens, 0.90),
                        mean=(round(sum(lens) / len(lens), 3)
                              if lens else None)),
        accept_frac=dict(median=pct(fracs, 0.5), p10=pct(fracs, 0.10),
                         p90=pct(fracs, 0.90),
                         mean=(round(sum(fracs) / len(fracs), 4)
                               if fracs else None)),
        draft_tok=dict(median=pct([r["draft_tok"] for r in rows], 0.5)),
        hist_accept_len=dict(sorted(Counter(lens).items())))


# ------------------------------------------------------- fallback exact path (needs a service)

def post_completions(base_url, payload, timeout):
    import urllib.request
    # same convention as replay_inject.post_completions: --base-url ends with /v1
    req = urllib.request.Request(
        base_url.rstrip("/") + "/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def anchor_of(plan, raw, ev, tok, table):
    """Re-assemble the prompt at the switch_only step, all the way up to where the bare call starts.

    The draft and the reference need to start from the same position for the accepted length to mean anything: so the
    anchor = the run segment's prompt (prefix + analysis-channel opener + thinking head + SWITCH), followed by the shell
    the large model wrote itself before the bare call (fence opener plus print( and so on).
    """
    import rebuild as R
    p = plan[ev]
    o = raw.get(ev, {}).get("switch_only")
    if o is None or not o.get("text"):
        return None
    meta, gens, envs, _ = R.load_traj(Path(p["traj_path"]))
    msgs = R.build_messages(meta, gens, envs, p["step"])
    prefix = R.build_prefix(tok, msgs, pin_date=R.COLLECT_DATE)
    head = (gens[p["step"]].get("reasoning") or "").strip()[:p["cut"]]
    pred_label = p.get("pred_label")
    skel = skeleton(pred_label, table) if pred_label else ""
    _, final = rebuild_sides("switch_only", o["text"], skel)
    call, end = parse_call.complete_call(final)
    if call is None:
        return None
    return prefix + R.ANALYSIS_OPEN + head + SWITCH + final[:end - len(call)]


def part_c_echo(rows, plan, raw, tok, table, a):
    """Feed the draft back in after the anchor, and check token by token whether it is top-1."""
    out, fail = [], Counter()
    for r in rows:
        anc = anchor_of(plan, raw, r["event"], tok, table)
        if anc is None:
            fail["no_anchor"] += 1
            continue
        try:
            resp = post_completions(a.base_url, dict(
                # max_tokens=0 + echo: this is a scoring request, it only reads the logprob of the tokens already
                # in the draft; the request body carries model / prompt / max_tokens / echo /
                # logprobs / skip_special_tokens
                model=a.model, prompt=anc + r["draft"], max_tokens=0,
                echo=True, logprobs=1,
                skip_special_tokens=False), a.timeout)
        except Exception as e:
            fail[f"http_{type(e).__name__}"] += 1
            continue
        lp = resp["choices"][0].get("logprobs") or {}
        offs = lp.get("text_offset") or []
        toks = lp.get("tokens") or []
        tlp = lp.get("token_logprobs") or []
        tops = lp.get("top_logprobs") or []
        # the draft's first token = the first token whose start position falls after the anchor. Locate it with text_offset,
        # not "the length of the anchor encoded on its own" -- the two can differ by one token at the boundary
        idx = [i for i, o in enumerate(offs) if o >= len(anc)]
        if not idx:
            fail["no_draft_span"] += 1
            continue
        k = 0
        for i in idx:
            top = tops[i] if i < len(tops) else None
            if not top or tlp[i] is None:
                break
            if toks[i] != max(top, key=top.get):   # not top-1 = rejection point
                break
            k += 1
        out.append(dict(event=r["event"], accept_len_echo=k,
                        accept_len_lcp=r["accept_len"],
                        agree=(k == r["accept_len"])))
    n = len(out)
    n_dis = sum(1 for x in out if not x["agree"])
    ks = [x["accept_len_echo"] for x in out]
    return dict(n=n, n_fail=dict(fail), n_disagree=n_dis,
                disagree_rate=round(n_dis / n, 4) if n else None,
                accept_len_echo=dict(median=pct(ks, 0.5), p10=pct(ks, 0.10),
                                     p90=pct(ks, 0.90)),
                rows=out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--plan-file", default="plan.jsonl")
    ap.add_argument("--tag", default="", help="suffix for per_event<tag>/raw<tag>")
    ap.add_argument("--tokenizer", default=DEFAULT_TOKENIZER,
                    help="the large model's tokenizer (loaded on CPU, used only for encoding, does not build the model)")
    ap.add_argument("--form-table", default=None)
    ap.add_argument("--base-url", default=None,
                    help="runs the fallback exact path (echo+logprobs) only when given; marked skipped otherwise")
    ap.add_argument("--model", default="gpt-oss-120b")
    ap.add_argument("--timeout", type=float, default=600)
    ap.add_argument("--limit", type=int, default=0,
                    help="the fallback exact path only runs the first N rows (one request per row, very slow)")
    ap.add_argument("--out", default="ACCEPT_REPORT.json")
    a = ap.parse_args()

    from transformers import AutoTokenizer
    d = Path(a.run_dir)
    plan = {}
    for line in open(d / a.plan_file):
        p = json.loads(line)
        plan[p["event"]] = p
    sw = load_switch_only(d, a.tag)
    tok = AutoTokenizer.from_pretrained(a.tokenizer)
    table = load_table(a.form_table)

    rep = dict(run_dir=str(d), plan_file=a.plan_file, tag=a.tag,
               tokenizer=a.tokenizer, n_plan=len(plan), n_switch_only=len(sw))
    rep["jia_tool_accept"] = part_a(plan, sw)
    rows, skipped = part_c_tok(plan, sw, tok)
    rep["bing_draft_accept"] = dict(skipped=skipped, **summarize_c(rows))

    if a.base_url:
        use = rows[:a.limit] if a.limit else rows
        raw = {}
        for line in open(d / f"raw{a.tag}.jsonl"):
            o = json.loads(line)
            raw.setdefault(o["event"], {})[o["arm"]] = o
        rep["bing_echo"] = part_c_echo(use, plan, raw, tok, table, a)
    else:
        rep["bing_echo"] = dict(status="skipped",
                                reason="no --base-url given, the fallback exact path does not run")

    (d / a.out).write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    show = {k: v for k, v in rep.items() if k != "bing_echo"}
    show["bing_draft_accept"] = {
        k: v for k, v in show["bing_draft_accept"].items()
        if k != "hist_accept_len"}
    print(json.dumps(show, ensure_ascii=False, indent=1))
    print(f"-> {d / a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
