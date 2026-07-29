"""HotpotQA oracle injection (第1步): does the dead zone survive on real multi-hop?

Protocol ported from oracle_inject/oracle_v1.py. Tool = search("<query>");
we serve GOLD paragraphs (from supporting_facts) to remove retrieval quality
as a confound. comparison (independent hops) and bridge (hop-2 args depend on
hop-1 result) are reported separately; hop-1 and hop-2 injections separately.

Conditions per question:
  baseline                 normal run, serve gold docs on CALL
  hop1 d in {-1,100,50,25,0}   inject doc1 note at call1_tok - d (-1 = thinking start)
  hop2 d in {50,25,0}          inject doc2 note at call2 - d (within hop-2 segment)
  hop2_start               inject doc2 note at thinking start (before hop-1 resolved)

Output: one JSON line per (question, condition).
"""

import argparse
import json
import re
import string
import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

SYSTEM = (
    "You are a precise assistant with access to a search tool over Wikipedia. "
    "To use it, output a line in exactly this format:\n"
    'CALL: search("<query>")\n'
    "and stop there. The result will be given to you as a RESULT line. "
    "Facts must come from search results - do not rely on memory alone. "
    "You may search multiple times (one CALL at a time). "
    "When you know the answer, finish with exactly one line:\n"
    "ANSWER: <short answer>"
)

PERMIT = (
    " Sometimes the system prefetches a search for you: a line of the form\n"
    '[SYSTEM NOTE: prefetched search("<query>") = <result>]\n'
    "may appear during your reasoning. Such a note is a valid RESULT: when it "
    "covers what you need, use it and do NOT emit that CALL."
)

CALL_RE = re.compile(r'(?m)^\s*CALL:\s*search\(\s*"([^"\n]+)"\s*\)')
ANS_RE = re.compile(r"(?m)^\s*ANSWER:\s*(.+?)\s*$")


def norm(s):
    s = s.lower().strip()
    s = "".join(c for c in s if c not in string.punctuation)
    s = " ".join(w for w in s.split() if w not in ("a", "an", "the"))
    return s


def grade(pred, gold):
    if pred is None:
        return False, False
    p, g = norm(pred), norm(gold)
    if g in ("yes", "no"):
        w = p.split()
        ok = bool(w) and w[0] == g
        return ok, ok
    em = p == g
    soft = em or (g in p and len(g) > 0) or (p in g and len(p) > 0)
    return em, soft


def load_questions(n_per_type, seed_offset=0, dataset="hotpot"):
    from datasets import load_dataset
    if dataset == "hotpot":
        ds = load_dataset("hotpot_qa", "fullwiki", split="validation")
    else:  # 2wiki: comparison + compositional(=bridge-like 2-hop chain)
        ds = load_dataset("voidful/2WikiMultihopQA", split="validation")
    out = {"comparison": [], "bridge": []}
    for ex in ds:
        if dataset == "hotpot":
            t = ex["type"]
            sf_titles = ex["supporting_facts"]["title"]
            ctx_pairs = zip(ex["context"]["title"],
                            ["".join(s) for s in ex["context"]["sentences"]])
        else:
            t = {"comparison": "comparison", "compositional": "bridge"}.get(ex["type"])
            if t is None:
                continue
            sf_titles = [x[0] for x in ex["supporting_facts"]]
            ctx_pairs = ((title, "".join(sents)) for title, sents in ex["context"])
        if len(out[t]) >= n_per_type + seed_offset:
            continue
        golds = list(dict.fromkeys(sf_titles))
        if len(golds) != 2:
            continue
        ctx = dict(ctx_pairs)
        if not all(g in ctx for g in golds):
            continue  # fullwiki retrieval may miss gold docs
        distract = next(((ti, tx) for ti, tx in ctx.items() if ti not in golds),
                        None)
        out[t].append({
            "qid": ex.get("id") or ex["_id"], "question": ex["question"], "answer": ex["answer"],
            "type": t, "docs": [(g, ctx[g]) for g in golds],
            "distractor": distract})
        if all(len(v) >= n_per_type + seed_offset for v in out.values()):
            break
    return {k: v[seed_offset:seed_offset + n_per_type] for k, v in out.items()}


def overlap(query, title, text):
    qw = set(norm(query).split())
    tw = set(norm(title).split()) | set(norm(text[:300]).split())
    return len(qw & tw) / max(1, len(qw))


def pick_doc(query, docs, served):
    """Prefer unserved gold doc with best query overlap."""
    order = sorted(range(len(docs)),
                   key=lambda i: (i in served, -overlap(query, *docs[i])))
    return order[0]


GEN_KW = {"do_sample": False}  # T11: main() may switch to sampling via --temperature


def gen_until(model, tok, ids, stop_pred, budget, chunk=64):
    start = ids.shape[1]
    while ids.shape[1] - start < budget:
        with torch.no_grad():
            out = model.generate(
                ids, max_new_tokens=min(chunk, budget - (ids.shape[1] - start)),
                pad_token_id=tok.eos_token_id, **GEN_KW)
        ids = out
        new_text = tok.decode(ids[0, start:], skip_special_tokens=False)
        if stop_pred(new_text) or ids[0, -1].item() == tok.eos_token_id:
            break
    return ids, tok.decode(ids[0, start:], skip_special_tokens=False)


def tok_pos_of_match(tok, gen_ids, regex):
    """Smallest k such that regex matches decode(gen_ids[:k])."""
    lo, hi = 1, gen_ids.shape[0]
    if not regex.search(tok.decode(gen_ids, skip_special_tokens=False)):
        return None
    while lo < hi:
        mid = (lo + hi) // 2
        if regex.search(tok.decode(gen_ids[:mid], skip_special_tokens=False)):
            hi = mid
        else:
            lo = mid + 1
    return lo


def append_text(tok, ids, text):
    tid = tok(text, return_tensors="pt", add_special_tokens=False).input_ids.to(ids.device)
    return torch.cat([ids, tid], dim=1), tid.shape[1]


FAKE_RES_RE = re.compile(r"(?m)^\s*RESULT:")


def result_line(query, title, text):
    return f'\nRESULT: search("{query}") = {title}: {text}\n'


def note_line(title, text):
    return f'\n[SYSTEM NOTE: prefetched search("{title}") = {title}: {text}]\n'


def force_answer(model, tok, ids):
    """Budget exhausted without ANSWER: append 'ANSWER:' and let it finish."""
    ids, _ = append_text(tok, ids, "\nANSWER:")
    with torch.no_grad():
        out = model.generate(ids, max_new_tokens=24,
                             pad_token_id=tok.eos_token_id, **GEN_KW)
    text = tok.decode(out[0, ids.shape[1]:], skip_special_tokens=True)
    return out, text.strip().split("\n")[0].strip() or None


def run_episode(model, tok, prompt_ids, q, budget, max_hops=4):
    """Serve gold docs on CALL until ANSWER. Returns record with per-hop info.

    gen_tokens counts only model-generated tokens (inserted RESULT lines
    excluded). call_positions are cumulative generated-token counts at which
    each CALL completed. Segment boundaries let us replay/truncate exactly.
    """
    ids = prompt_ids.clone()
    served = set()
    gen_tokens = 0
    hops = []          # per hop: dict(call_tok_global, doc_idx, seg_start_len)
    segments = []      # (ids_len_before_gen,) for replay bookkeeping
    for _hop in range(max_hops + 1):
        seg_start = ids.shape[1]
        ids, text = gen_until(model, tok, ids,
                              lambda t: ANS_RE.search(t) or CALL_RE.search(t)
                              or FAKE_RES_RE.search(t),
                              budget - gen_tokens)
        seg_ids = ids[0, seg_start:]
        m_ans, m_call, m_fake = (ANS_RE.search(text), CALL_RE.search(text),
                                 FAKE_RES_RE.search(text))
        first = min((m.start(), k) for k, m in
                    (("ans", m_ans), ("call", m_call), ("fake", m_fake))
                    if m) if (m_ans or m_call or m_fake) else (None, None)
        if first[1] == "fake":
            # model started writing its own RESULT lines -> degeneration
            k = tok_pos_of_match(tok, seg_ids, FAKE_RES_RE)
            gen_tokens += k
            ids = ids[:, :seg_start + max(1, k - 1)]
            ids, ans = force_answer(model, tok, ids)
            return ids, gen_tokens, hops, ans, "degen"
        if first[1] == "ans":
            gen_tokens += seg_ids.shape[0]
            return ids, gen_tokens, hops, ANS_RE.search(text).group(1), "ok"
        if m_call:
            k = tok_pos_of_match(tok, seg_ids, CALL_RE)
            gen_tokens += k
            query = m_call.group(1)
            di = pick_doc(query, q["docs"], served)
            served.add(di)
            # truncate any overshoot past the CALL line, then append RESULT
            ids = ids[:, :seg_start + k]
            ids, _ = append_text(tok, ids,
                                 result_line(query, *q["docs"][di]))
            hops.append({"call_tok": gen_tokens, "doc_idx": di,
                         "stream_len_after_result": ids.shape[1]})
            continue
        gen_tokens += seg_ids.shape[0]
        ids, ans = force_answer(model, tok, ids)
        return ids, gen_tokens, hops, ans, "forced"  # budget out / eos
    ids, ans = force_answer(model, tok, ids)
    return ids, gen_tokens, hops, ans, "forced"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--types", default="comparison,bridge")
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--hop1-offsets", default="-1,100,50,25,0")
    ap.add_argument("--hop2-offsets", default="50,25,0")
    ap.add_argument("--budget", type=int, default=2500)
    ap.add_argument("--shard", default="0/1", help="i/N: take questions i::N")
    ap.add_argument("--both-start", action="store_true",
                    help="add condition: inject BOTH gold docs at thinking start")
    ap.add_argument("--only-both", action="store_true",
                    help="run only baseline + both_start (for cheap reruns)")
    ap.add_argument("--no-permit", action="store_true",
                    help="omit the prefetch-authorization sentence from SYSTEM")
    ap.add_argument("--wrong", action="store_true",
                    help="add wrong-doc injection conds (distractor at start/50)")
    ap.add_argument("--dataset", default="hotpot", choices=["hotpot", "2wiki"])
    ap.add_argument("--temperature", type=float, default=0.0,
                    help="T11: >0 switches all generation to sampling (variance check)")
    ap.add_argument("--gen-seed", type=int, default=-1,
                    help="T11: torch.manual_seed for sampling runs; -1 = off")
    ap.add_argument("--tray", action="store_true",
                    help="add condition: both golds + 1 distractor at start")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    shard_i, shard_n = (int(x) for x in args.shard.split("/"))
    if args.temperature > 0:
        GEN_KW.update(do_sample=True, temperature=args.temperature)
    if args.gen_seed >= 0:
        torch.manual_seed(args.gen_seed)

    tok = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForCausalLM.from_pretrained(
        args.model, dtype=torch.bfloat16, device_map="cuda",
        attn_implementation="sdpa")
    model.eval()

    qs = load_questions(args.n, dataset=args.dataset)
    out = open(args.out, "w")

    def emit(rec):
        out.write(json.dumps(rec) + "\n")
        out.flush()

    for typ in args.types.split(","):
        for q in qs[typ][shard_i::shard_n]:
            sys_prompt = SYSTEM if args.no_permit else SYSTEM + PERMIT
            msgs = [{"role": "system", "content": sys_prompt},
                    {"role": "user", "content": q["question"]}]
            prompt_text = tok.apply_chat_template(
                msgs, add_generation_prompt=True, enable_thinking=True,
                tokenize=False)
            prompt_ids = tok(prompt_text, return_tensors="pt",
                             add_special_tokens=False).input_ids.to(model.device)
            plen = prompt_ids.shape[1]

            # ---- baseline ----
            t0 = time.time()
            ids_b, gen_b, hops, ans, status_b = run_episode(
                model, tok, prompt_ids, q, args.budget)
            em, soft = grade(ans, q["answer"])
            base = {"qid": q["qid"], "type": typ, "cond": "baseline",
                    "dataset": args.dataset,
                    "temperature": args.temperature, "gen_seed": args.gen_seed,
                    "model": args.model, "n_calls": len(hops),
                    "call_toks": [h["call_tok"] for h in hops],
                    "gen_tokens": gen_b, "answer": ans, "em": em, "soft": soft,
                    "status": status_b,
                    "wall_s": round(time.time() - t0, 1)}
            emit(base)
            print(f"[{typ} {q['qid'][:8]}] baseline calls={base['call_toks']} "
                  f"gen={gen_b} em={em} soft={soft}", flush=True)
            if not hops:
                continue  # no call point -> injection undefined

            def replay(cut_stream_len, inject_docs, cond, d):
                """Truncate full baseline stream at cut point, inject, rerun."""
                t1 = time.time()
                ids0 = ids_b[:, :cut_stream_len]
                docs = inject_docs if isinstance(inject_docs, list) else [inject_docs]
                for di_ in docs:
                    src_doc = q["distractor"] if di_ == -1 else q["docs"][di_]
                    ids0, _ = append_text(tok, ids0, note_line(*src_doc))
                # generated tokens kept from baseline = cut - plen - RESULT spans before cut
                acc, kept_inserted = 0, 0
                for h in hops:
                    call_end = plen + h["call_tok"] + acc
                    r_len = h["stream_len_after_result"] - call_end
                    if h["stream_len_after_result"] <= cut_stream_len:
                        kept_inserted += r_len
                    acc += r_len
                kept_gen = cut_stream_len - plen - kept_inserted
                ids1, gen1, hops1, ans1, status1 = run_episode(
                    model, tok, ids0, q, args.budget)
                em1, soft1 = grade(ans1, q["answer"])
                emit({"qid": q["qid"], "type": typ, "cond": cond, "offset": d,
                      "model": args.model, "dataset": args.dataset,
                      "temperature": args.temperature, "gen_seed": args.gen_seed,
                      "kept_gen_tokens": kept_gen, "cont_gen_tokens": gen1,
                      "gen_tokens": kept_gen + gen1,
                      "baseline_gen_tokens": gen_b,
                      "baseline_call_toks": base["call_toks"],
                      "n_calls_after": len(hops1), "status": status1,
                      "answer": ans1, "em": em1, "soft": soft1,
                      "wall_s": round(time.time() - t1, 1)})
                print(f"[{typ} {q['qid'][:8]}] {cond} d={d} "
                      f"gen={kept_gen + gen1} calls_after={len(hops1)} "
                      f"em={em1}", flush=True)

            if (args.both_start or args.only_both) and len(q["docs"]) == 2:
                replay(plen, [0, 1], "both_start", -1)
            if args.tray and q.get("distractor") and len(q["docs"]) == 2:
                replay(plen, [0, 1, -1], "tray_start", -1)
            if args.wrong and q.get("distractor"):
                replay(plen, -1, "wrong_start", -1)
                c1 = hops[0]["call_tok"]
                replay(plen + max(0, c1 - 50), -1, "wrong", 50)
            if args.only_both:
                continue

            # ---- hop-1 injections: cut within first thinking segment ----
            call1 = hops[0]["call_tok"]
            doc1 = hops[0]["doc_idx"]
            for d in [int(x) for x in args.hop1_offsets.split(",")]:
                point = 0 if d < 0 else max(0, call1 - d)
                replay(plen + point, doc1, "hop1", d)

            # ---- hop-2 injections: only if a second call happened ----
            if len(hops) >= 2:
                doc2 = hops[1]["doc_idx"]
                seg2_start_stream = hops[0]["stream_len_after_result"]
                call2_in_seg = hops[1]["call_tok"] - hops[0]["call_tok"]
                for d in [int(x) for x in args.hop2_offsets.split(",")]:
                    point = max(0, call2_in_seg - d)
                    replay(seg2_start_stream + point, doc2, "hop2", d)
                # doc2 injected at thinking start, before hop-1 resolved
                replay(plen, doc2, "hop2_start", -1)
    out.close()


if __name__ == "__main__":
    main()
