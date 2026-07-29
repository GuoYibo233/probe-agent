"""Synthetic 2-hop bridge injection (任务扩展, 2026-07-27).

Chain: lookup("<X> alloy") -> "refines into <Y> crystal";
       lookup("<Y> crystal") -> <number>  (the asked property).
Hop-2 argument (Y) is provably unknowable before hop-1 returns — the fully
controlled version of HotpotQA bridge. Mirrors hop2_start: inject the hop-2
result at thinking start, before the model can know Y.

Conditions: baseline / hop1@{start,100,50,25,0} / hop2@{50,25,0} /
hop2_start / wrong hop-2 value @50.
"""

import argparse
import importlib.util
import json
import random
import re
import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

spec = importlib.util.spec_from_file_location(
    "hotpot_v1", "/home/y-guo/reproduce/new1/hotpot_inject/hotpot_v1.py")
H = importlib.util.module_from_spec(spec)
spec.loader.exec_module(H)  # gen_until / tok_pos_of_match / append_text / force_answer

SYSTEM = (
    "You are a precise assistant with access to an internal database that "
    "contains facts not available anywhere else. To query it, output a line "
    'in exactly this format:\nCALL: lookup("<entity name>")\n'
    "and stop there. The result will be given to you as a RESULT line. "
    "Some questions need a chain of two lookups. You cannot know these facts "
    "without the database - guessing is useless. When you have the final "
    "fact, finish with exactly one line:\nANSWER: <number>"
)
PERMIT = (
    " Sometimes the system prefetches a lookup for you: a line of the form\n"
    '[SYSTEM NOTE: prefetched lookup("<entity>") = <value>]\n'
    "may appear during your reasoning. Such a note is a valid RESULT: when it "
    "covers what you need, use it and do NOT emit that CALL."
)

CALL_RE = re.compile(r'(?m)^\s*CALL:\s*lookup\(\s*"?([^"<>)\n]+?)"?\s*\)')
ANS_RE = re.compile(r"ANSWER:\s*\$?([\-0-9.,]+)")
FAKE_RES_RE = re.compile(r"(?m)^\s*RESULT:")

NAME_A = ["Vor", "Zel", "Kar", "Bren", "Thal", "Mor", "Quin", "Dax", "Fen",
          "Gral", "Hex", "Jor", "Lum", "Nev", "Oss", "Pyr", "Rul", "Syl",
          "Tor", "Vex"]
NAME_B = ["nite", "mora", "vex", "dahl", "quist", "born", "tesk", "mund",
          "lior", "gath"]


def build_questions(n, seed):
    rng = random.Random(seed)
    qs, used = [], set()
    while len(qs) < n:
        x = rng.choice(NAME_A) + rng.choice(NAME_B) + "-" + str(rng.randint(10, 99))
        y = rng.choice(NAME_A) + rng.choice(NAME_B) + "-" + str(rng.randint(10, 99))
        if x in used or y in used or x == y:
            continue
        used.update((x, y))
        value = str(round(rng.uniform(200, 1100), 1))
        wrong = str(round(rng.uniform(200, 1100), 1))
        qs.append({
            "qid": len(qs),
            "question": ("What is the atomic emission peak, in nanometers, of "
                         f"the crystal produced by refining {x} alloy?"),
            "x": f"{x} alloy", "y": f"{y} crystal",
            "hop1": f"refines into {y} crystal",
            "value": value, "wrong": wrong})
    return qs


def serve(q, query):
    ql = query.lower()
    if q["y"].split()[0].lower() in ql:
        return f'\nRESULT: lookup("{query}") = {q["value"]}\n'
    return f'\nRESULT: lookup("{query}") = {q["hop1"]}\n'


def run_episode(model, tok, prompt_ids, q, budget=1600, max_hops=4):
    ids = prompt_ids.clone()
    gen_tokens, hops = 0, []
    for _hop in range(max_hops + 1):
        seg_start = ids.shape[1]
        ids, text = H.gen_until(
            model, tok, ids,
            lambda t: ANS_RE.search(t) or CALL_RE.search(t) or FAKE_RES_RE.search(t),
            budget - gen_tokens)
        seg_ids = ids[0, seg_start:]
        m = {k: r.search(text) for k, r in
             (("ans", ANS_RE), ("call", CALL_RE), ("fake", FAKE_RES_RE))}
        ev = sorted((x.start(), k) for k, x in m.items() if x)
        kind = ev[0][1] if ev else None
        if kind == "ans":
            gen_tokens += seg_ids.shape[0]
            return ids, gen_tokens, hops, m["ans"].group(1).replace(",", ""), "ok"
        if kind == "call":
            k = H.tok_pos_of_match(tok, seg_ids, CALL_RE)
            gen_tokens += k
            ids = ids[:, :seg_start + k]
            query = m["call"].group(1).strip()
            ids, _ = H.append_text(tok, ids, serve(q, query))
            hops.append({"call_tok": gen_tokens, "query": query,
                         "stream_len_after_result": ids.shape[1]})
            continue
        if kind == "fake":
            k = H.tok_pos_of_match(tok, seg_ids, FAKE_RES_RE)
            gen_tokens += k
            ids = ids[:, :seg_start + max(1, k - 1)]
            ids, ans = H.force_answer(model, tok, ids)
            a = ANS_RE.search("ANSWER: " + (ans or ""))
            return ids, gen_tokens, hops, (a.group(1).replace(",", "") if a else ans), "degen"
        gen_tokens += seg_ids.shape[0]
        ids, ans = H.force_answer(model, tok, ids)
        a = ANS_RE.search("ANSWER: " + (ans or ""))
        return ids, gen_tokens, hops, (a.group(1).replace(",", "") if a else ans), "forced"
    ids, ans = H.force_answer(model, tok, ids)
    return ids, gen_tokens, hops, ans, "forced"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--budget", type=int, default=1600)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    tok = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForCausalLM.from_pretrained(
        args.model, dtype=torch.bfloat16, device_map="cuda",
        attn_implementation="sdpa")
    model.eval()
    out = open(args.out, "w")

    def emit(r):
        out.write(json.dumps(r) + "\n")
        out.flush()

    for q in build_questions(args.n, args.seed):
        msgs = [{"role": "system", "content": SYSTEM + PERMIT},
                {"role": "user", "content": q["question"]}]
        ptext = tok.apply_chat_template(msgs, add_generation_prompt=True,
                                        enable_thinking=True, tokenize=False)
        pids = tok(ptext, return_tensors="pt",
                   add_special_tokens=False).input_ids.to(model.device)
        plen = pids.shape[1]
        t0 = time.time()
        ids_b, gen_b, hops, ans, stat = run_episode(model, tok, pids, q, args.budget)
        emit({"qid": q["qid"], "cond": "baseline", "model": args.model,
              "n_calls": len(hops), "call_toks": [h["call_tok"] for h in hops],
              "gen_tokens": gen_b, "answer": ans, "correct": ans == q["value"],
              "status": stat, "wall_s": round(time.time() - t0, 1)})
        print(f"[q{q['qid']:02d}] base calls={[h['call_tok'] for h in hops]} "
              f"gen={gen_b} ok={ans == q['value']} st={stat}", flush=True)
        if not hops:
            continue

        def note(entity, val):
            return f'\n[SYSTEM NOTE: prefetched lookup("{entity}") = {val}]\n'

        def replay(cut, note_txt, cond, d):
            t1 = time.time()
            ids0 = ids_b[:, :cut]
            ids0, _ = H.append_text(tok, ids0, note_txt)
            acc_ins, kept_ins = 0, 0
            for h in hops:
                ce = plen + h["call_tok"] + acc_ins
                rl = h["stream_len_after_result"] - ce
                if h["stream_len_after_result"] <= cut:
                    kept_ins += rl
                acc_ins += rl
            kept = cut - plen - kept_ins
            ids1, g1, h1, a1, s1 = run_episode(model, tok, ids0, q, args.budget)
            emit({"qid": q["qid"], "cond": cond, "offset": d,
                  "model": args.model, "gen_tokens": kept + g1,
                  "baseline_gen_tokens": gen_b, "n_calls_after": len(h1),
                  "answer": a1, "correct": a1 == q["value"], "status": s1,
                  "wall_s": round(time.time() - t1, 1)})
            print(f"[q{q['qid']:02d}] {cond} d={d} gen={kept + g1} "
                  f"ok={a1 == q['value']} st={s1}", flush=True)

        call1 = hops[0]["call_tok"]
        for d in (-1, 100, 50, 25, 0):
            cut = plen + (0 if d < 0 else max(0, call1 - d))
            replay(cut, note(q["x"], q["hop1"]), "hop1", d)
        replay(plen, note(q["y"], q["value"]), "hop2_start", -1)
        replay(plen, note(q["y"], q["wrong"]), "hop2_start_wrong", -1)
        if len(hops) >= 2:
            seg2 = hops[0]["stream_len_after_result"]
            c2 = hops[1]["call_tok"] - hops[0]["call_tok"]
            for d in (50, 25, 0):
                replay(seg2 + max(0, c2 - d), note(q["y"], q["value"]), "hop2", d)
    out.close()


if __name__ == "__main__":
    main()
