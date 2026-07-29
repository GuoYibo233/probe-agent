"""Oracle injection variance check (第2步): same protocol as oracle_v1 but
temperature sampling with a per-run seed, to put error bars on the dead zone.

Question: if the CORRECT tool result is spliced into the model's thinking
stream d tokens BEFORE the point where it would emit the call, how much
generated-token budget is saved, does the model skip the call, and does
answer accuracy survive? Plus a wrong-injection control to measure poisoning.

Design:
  Phase A (baseline): synthetic fact questions the model cannot know
    (invented entities). Model thinks, emits `CALL: lookup("entity")`,
    we return RESULT, it answers `ANSWER: value`.
  Phase B (inject): reuse baseline token stream, truncate at
    call_pos - d, splice "[Prefetched observation ...]" with the correct
    (or deliberately wrong) value, continue generation.

Output: one JSON line per (question, condition).
"""

import argparse
import json
import random
import re
import time
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

DO_SAMPLE = False
TEMPERATURE = 1.0
TOP_P = 1.0

SYSTEM = (
    "You are a precise assistant with access to an internal database that "
    "contains facts not available anywhere else. To query it, output a line "
    'in exactly this format:\nCALL: lookup("<entity name>")\n'
    "and stop there. The result will be given to you as a RESULT line. "
    "You cannot know these facts without the database - guessing is useless. "
    "When you have the fact, finish with exactly one line:\nANSWER: <number>"
)

PERMIT = (
    " Sometimes the system prefetches the lookup for you: a line of the form\n"
    '[SYSTEM NOTE: prefetched lookup("<entity>") = <value>]\n'
    "may appear during your reasoning. Such a note is a valid RESULT: when it "
    "covers what you need, use it and answer directly - do NOT emit a CALL."
)

TEMPLATES = [
    ("the melting point of {e} alloy in Celsius", "{e} alloy", 400, 1900),
    ("the share price of {e} Corp in dollars", "{e} Corp", 4, 900),
    ("the battery capacity of the {e} drone in mAh", "{e} drone", 1000, 9000),
    ("the maximum depth of Lake {e} in meters", "Lake {e}", 15, 700),
    ("the atomic emission peak of {e} crystal in nanometers", "{e} crystal", 200, 1100),
]

NAME_A = ["Vor", "Zel", "Kar", "Bren", "Thal", "Mor", "Quin", "Dax", "Fen", "Gral",
          "Hex", "Jor", "Lum", "Nev", "Oss", "Pyr", "Rul", "Syl", "Tor", "Vex"]
NAME_B = ["nite", "mora", "vex", "dahl", "quist", "born", "tesk", "mund", "lior", "gath"]


def build_questions(n, seed):
    rng = random.Random(seed)
    qs, used = [], set()
    while len(qs) < n:
        name = rng.choice(NAME_A) + rng.choice(NAME_B) + "-" + str(rng.randint(10, 99))
        if name in used:
            continue
        used.add(name)
        tpl, ent_tpl, lo, hi = rng.choice(TEMPLATES)
        value = str(round(rng.uniform(lo, hi), 1))
        wrong = str(round(rng.uniform(lo, hi), 1))
        while wrong == value:
            wrong = str(round(rng.uniform(lo, hi), 1))
        qs.append({
            "qid": len(qs),
            "question": "What is " + tpl.format(e=name) + "?",
            "entity": ent_tpl.format(e=name),
            "value": value,
            "wrong": wrong,
        })
    return qs


CALL_RE = re.compile(r'(?m)^\s*CALL:\s*lookup\(\s*"?([^"<>)\n]+?)"?\s*\)')
ANS_RE = re.compile(r"ANSWER:\s*\$?([\-0-9.,]+)")


def gen_until(model, tok, ids, stop_pred, max_new, chunk=48):
    """Greedy-generate in chunks until stop_pred(new_text) or budget out.
    Returns (new_ids_tensor, new_text)."""
    start = ids.shape[1]
    while ids.shape[1] - start < max_new:
        with torch.no_grad():
            out = model.generate(
                ids, max_new_tokens=min(chunk, max_new - (ids.shape[1] - start)),
                do_sample=DO_SAMPLE, temperature=TEMPERATURE, top_p=TOP_P, pad_token_id=tok.eos_token_id)
        ids = out
        new_text = tok.decode(ids[0, start:], skip_special_tokens=False)
        if stop_pred(new_text) or ids[0, -1].item() == tok.eos_token_id:
            break
    return ids, tok.decode(ids[0, start:], skip_special_tokens=False)


def first_call(text):
    m = CALL_RE.search(text)
    return (m.group(1).strip(), m.end()) if m else (None, None)


def answer_of(text):
    m = ANS_RE.search(text)
    return m.group(1).replace(",", "") if m else None


def run_continue_to_answer(model, tok, ids, q, max_new, serve_result=True):
    """Continue until ANSWER, serving RESULT if a CALL appears. Returns record."""
    called = False
    total_new = 0
    for _hop in range(3):
        ids, text = gen_until(
            model, tok, ids,
            lambda t: ANS_RE.search(t) or CALL_RE.search(t), max_new)
        total_new += 0  # counted at the end via shape bookkeeping by caller
        ent, _ = first_call(text)
        if ANS_RE.search(text):
            return ids, answer_of(text), called
        if ent is not None and serve_result:
            called = True
            res = f'\nRESULT: lookup("{q["entity"]}") = {q["value"]}\n'
            rid = tok(res, return_tensors="pt", add_special_tokens=False).input_ids.to(ids.device)
            ids = torch.cat([ids, rid], dim=1)
        else:
            break
    return ids, answer_of(tok.decode(ids[0], skip_special_tokens=False)), called


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--offsets", default="0,25,50,100,200,-1",
                    help="-1 = inject at thinking start")
    ap.add_argument("--wrong-offset", type=int, default=50)
    ap.add_argument("--max-new", type=int, default=1200)
    ap.add_argument("--out", required=True)
    ap.add_argument("--temperature", type=float, default=0.6)
    ap.add_argument("--top-p", type=float, default=0.95)
    ap.add_argument("--sample-seed", type=int, default=1,
                    help="torch sampling seed; question set stays fixed via --seed")
    ap.add_argument("--no-permit", action="store_true",
                    help="omit the injection-permission sentence from SYSTEM")
    args = ap.parse_args()

    global DO_SAMPLE, TEMPERATURE, TOP_P
    DO_SAMPLE = True
    TEMPERATURE = args.temperature
    TOP_P = args.top_p
    torch.manual_seed(args.sample_seed)

    tok = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForCausalLM.from_pretrained(
        args.model, torch_dtype=torch.bfloat16, device_map="cuda",
        attn_implementation="sdpa")
    model.eval()

    questions = build_questions(args.n, args.seed)
    offsets = [int(x) for x in args.offsets.split(",")]
    out = open(args.out, "w")

    def emit(rec):
        out.write(json.dumps(rec) + "\n")
        out.flush()

    for q in questions:
        sys_prompt = SYSTEM if args.no_permit else SYSTEM + PERMIT
        msgs = [{"role": "system", "content": sys_prompt},
                {"role": "user", "content": q["question"]}]
        prompt_text = tok.apply_chat_template(
            msgs, add_generation_prompt=True, enable_thinking=True,
            tokenize=False)
        prompt_ids = tok(prompt_text, return_tensors="pt",
                         add_special_tokens=False).input_ids.to(model.device)
        plen = prompt_ids.shape[1]

        # ---- Phase A: baseline ----
        t0 = time.time()
        ids, pre_text = gen_until(
            model, tok, prompt_ids.clone(),
            lambda t: CALL_RE.search(t) or ANS_RE.search(t), args.max_new)
        ent, _ = first_call(pre_text)
        base = {"qid": q["qid"], "cond": "baseline", "model": args.model, "sample_seed": args.sample_seed}
        if ent is None:
            ans = answer_of(pre_text)
            base.update(call_emitted=False, tokens_to_call=None,
                        gen_tokens=ids.shape[1] - plen,
                        answer=ans, correct=(ans == q["value"]),
                        wall_s=round(time.time() - t0, 1),
                        text_head=pre_text[:300], text_tail=pre_text[-300:])
            emit(base)
            print(f"[q{q['qid']:02d}] baseline NO-CALL correct={base['correct']}")
            continue  # no call point -> injection undefined for this q
        # token index (within generated stream) where the CALL line starts
        # find smallest k with CALL_RE fullmatch present in decode of first k tokens
        gen_ids = ids[0, plen:]
        lo, hi = 1, gen_ids.shape[0]
        while lo < hi:
            mid = (lo + hi) // 2
            if CALL_RE.search(tok.decode(gen_ids[:mid], skip_special_tokens=False)):
                hi = mid
            else:
                lo = mid + 1
        call_tok = lo  # tokens generated up to end of CALL match
        res = f'\nRESULT: lookup("{q["entity"]}") = {q["value"]}\n'
        rid = tok(res, return_tensors="pt", add_special_tokens=False).input_ids.to(ids.device)
        ids2 = torch.cat([ids[:, :plen + call_tok], rid], dim=1)
        ids2, ans, _ = run_continue_to_answer(model, tok, ids2, q, args.max_new,
                                              serve_result=True)
        base.update(call_emitted=True, tokens_to_call=call_tok,
                    gen_tokens=(ids2.shape[1] - plen - rid.shape[1]),
                    answer=ans, correct=(ans == q["value"]),
                    wall_s=round(time.time() - t0, 1))
        emit(base)
        print(f"[q{q['qid']:02d}] baseline call@{call_tok} "
              f"total={base['gen_tokens']} correct={base['correct']}")

        # ---- Phase B: injections ----
        conds = [("inject", d, q["value"]) for d in offsets]
        conds.append(("inject_wrong", args.wrong_offset, q["wrong"]))
        for cond, d, val in conds:
            t0 = time.time()
            point = 0 if d < 0 else max(0, call_tok - d)
            inj = (f'\n[SYSTEM NOTE: prefetched lookup("{q["entity"]}") '
                   f'= {val}]\n')
            iid = tok(inj, return_tensors="pt",
                      add_special_tokens=False).input_ids.to(model.device)
            ids3 = torch.cat([prompt_ids, ids[:, plen:plen + point], iid], dim=1)
            pre_len = ids3.shape[1]
            ids3, ans, called = run_continue_to_answer(
                model, tok, ids3, q, args.max_new, serve_result=True)
            cont_text = tok.decode(ids3[0, pre_len:], skip_special_tokens=False)
            rec = {"qid": q["qid"], "cond": cond, "model": args.model,
                   "sample_seed": args.sample_seed,
                   "offset": d, "inject_point": point,
                   "call_tok_baseline": call_tok,
                   "baseline_gen_tokens": base["gen_tokens"],
                   "gen_tokens": point + (ids3.shape[1] - pre_len),
                   "called_anyway": called,
                   "answer": ans,
                   "correct": (ans == q["value"]),
                   "wall_s": round(time.time() - t0, 1),
                   "text_head": cont_text[:400], "text_tail": cont_text[-400:]}
            emit(rec)
            print(f"[q{q['qid']:02d}] {cond} d={d} pt={point} "
                  f"gen={rec['gen_tokens']} called={called} correct={rec['correct']}")
    out.close()


if __name__ == "__main__":
    main()
