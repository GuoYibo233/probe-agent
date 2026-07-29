"""第3步先导: trajectory + hidden-state collection pilot (50 traj scale).

Runs agent episodes (greedy, tools served), then ONE full-sequence forward
pass with output_hidden_states to recover per-token hidden states at selected
depths (greedy => recomputation is exact). Saves one .pt per trajectory:

  tokens        LongTensor [T]        full stream (prompt + gen + inserted)
  plen          int                   prompt length
  layers        [int, int]            selected layer indices (~30%, ~45% depth)
  hidden        {layer: fp16 [T, d]}
  inserted      [(start, len), ...]   RESULT/injection spans (not model-generated)
  calls         [{tok_pos, query, seg}, ...]   labels for heads 1-3
  answer/em/soft, wall_s, gen_tokens

Purpose: validate the storage + label route before scaling; measure bytes/traj.
"""

import argparse
import importlib.util
import json
import re
import string
import sys
import time
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

NEW1 = Path("/home/y-guo/reproduce/new1")
sys.path.insert(0, str(NEW1 / "oracle_inject"))
import oracle_v1  # noqa: E402  (SYSTEM/PERMIT/templates/regexes for synthetic)

spec = importlib.util.spec_from_file_location(
    "hotpot_v1", NEW1 / "hotpot_inject" / "hotpot_v1.py")
hotpot_v1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hotpot_v1)


def gen_until(model, tok, ids, stop_pred, budget, chunk=64):
    start = ids.shape[1]
    while ids.shape[1] - start < budget:
        with torch.no_grad():
            out = model.generate(
                ids, max_new_tokens=min(chunk, budget - (ids.shape[1] - start)),
                do_sample=False, pad_token_id=tok.eos_token_id)
        ids = out
        text = tok.decode(ids[0, start:], skip_special_tokens=False)
        if stop_pred(text) or ids[0, -1].item() == tok.eos_token_id:
            break
    return ids, tok.decode(ids[0, start:], skip_special_tokens=False)


def run_traj(model, tok, prompt_ids, call_re, ans_re, serve, budget=2500,
             max_hops=4):
    ids = prompt_ids.clone()
    plen = prompt_ids.shape[1]
    inserted, calls = [], []
    for hop in range(max_hops + 1):
        seg_start = ids.shape[1]
        ids, text = gen_until(model, tok, ids,
                              lambda t: ans_re.search(t) or call_re.search(t)
                              or hotpot_v1.FAKE_RES_RE.search(t),
                              budget)
        m_ans, m_call = ans_re.search(text), call_re.search(text)
        m_fake = hotpot_v1.FAKE_RES_RE.search(text)
        if m_fake and (not m_ans or m_fake.start() < m_ans.start()) and \
                (not m_call or m_fake.start() < m_call.start()):
            k = hotpot_v1.tok_pos_of_match(tok, ids[0, seg_start:],
                                           hotpot_v1.FAKE_RES_RE)
            return ids[:, :seg_start + max(1, k - 1)], inserted, calls, None
        if m_ans and (not m_call or m_ans.start() < m_call.start()):
            return ids, inserted, calls, m_ans.group(1)
        if not m_call:
            return ids, inserted, calls, None
        k = hotpot_v1.tok_pos_of_match(tok, ids[0, seg_start:], call_re)
        ids = ids[:, :seg_start + k]
        query = m_call.group(1)
        res = serve(query, hop)
        rid = tok(res, return_tensors="pt",
                  add_special_tokens=False).input_ids.to(ids.device)
        calls.append({"tok_pos": ids.shape[1], "query": query, "seg": hop})
        inserted.append((ids.shape[1], rid.shape[1]))
        ids = torch.cat([ids, rid], dim=1)
    return ids, inserted, calls, None


def extract_hidden(model, ids, layers):
    with torch.no_grad():
        out = model(ids, output_hidden_states=True, use_cache=False)
    return {l: out.hidden_states[l][0].to(torch.float16).cpu() for l in layers}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--task", choices=["synthetic", "hotpot", "2wiki"],
                    required=True)
    ap.add_argument("--shard", default="0/1")
    ap.add_argument("--n", type=int, default=25)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    tok = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForCausalLM.from_pretrained(
        args.model, dtype=torch.bfloat16, device_map="cuda",
        attn_implementation="sdpa")
    model.eval()
    L = model.config.num_hidden_layers
    layers = [max(1, round(0.30 * L)), max(2, round(0.45 * L))]
    meta_all = []

    if args.task == "synthetic":
        qs = oracle_v1.build_questions(args.n, args.seed)
        call_re, ans_re = oracle_v1.CALL_RE, oracle_v1.ANS_RE
        sys_prompt = oracle_v1.SYSTEM + oracle_v1.PERMIT
        tasks = [{"qid": f"syn{q['qid']:03d}", "question": q["question"],
                  "gold": q["value"],
                  "serve": (lambda q_: lambda query, hop:
                            f'\nRESULT: lookup("{q_["entity"]}") = {q_["value"]}\n')(q)}
                 for q in qs]
        grade = lambda a, g: (a == g, a == g)
    else:
        qs = hotpot_v1.load_questions(
            args.n, dataset="hotpot" if args.task == "hotpot" else "2wiki")
        pool = (qs["bridge"] + qs["comparison"])[:args.n]
        call_re, ans_re = hotpot_v1.CALL_RE, hotpot_v1.ANS_RE
        sys_prompt = hotpot_v1.SYSTEM + hotpot_v1.PERMIT

        def make_serve(q_):
            served = set()
            def serve(query, hop):
                di = hotpot_v1.pick_doc(query, q_["docs"], served)
                served.add(di)
                return hotpot_v1.result_line(query, *q_["docs"][di])
            return serve
        tasks = [{"qid": q["qid"], "question": q["question"],
                  "gold": q["answer"], "serve": make_serve(q)} for q in pool]
        grade = hotpot_v1.grade

    si, sn = (int(x) for x in args.shard.split("/"))
    tasks = tasks[si::sn]
    for i, t in enumerate(tasks):
        msgs = [{"role": "system", "content": sys_prompt},
                {"role": "user", "content": t["question"]}]
        ptext = tok.apply_chat_template(msgs, add_generation_prompt=True,
                                        enable_thinking=True, tokenize=False)
        pids = tok(ptext, return_tensors="pt",
                   add_special_tokens=False).input_ids.to(model.device)
        t0 = time.time()
        ids, inserted, calls, ans = run_traj(model, tok, pids, call_re, ans_re,
                                             t["serve"])
        wall = time.time() - t0
        em, soft = grade(ans, t["gold"])
        hid = extract_hidden(model, ids, layers)
        T = ids.shape[1]
        rec = {"tokens": ids[0].cpu(), "plen": pids.shape[1], "layers": layers,
               "hidden": hid, "inserted": inserted, "calls": calls,
               "answer": ans, "em": bool(em), "soft": bool(soft),
               "wall_s": round(wall, 1),
               "gen_tokens": T - pids.shape[1] - sum(l for _, l in inserted)}
        f = outdir / f"{args.task}_s{si}_{i:03d}.pt"
        torch.save(rec, f)
        meta = {"file": f.name, "qid": t["qid"], "T": T,
                "n_calls": len(calls), "em": bool(em), "soft": bool(soft),
                "bytes": f.stat().st_size, "wall_s": rec["wall_s"]}
        meta_all.append(meta)
        print(json.dumps(meta), flush=True)

    with open(outdir / f"{args.task}_s{si}_meta.jsonl", "w") as f:
        for m in meta_all:
            f.write(json.dumps(m) + "\n")
    tot = sum(m["bytes"] for m in meta_all)
    print(f"DONE {len(meta_all)} traj, total {tot/1e6:.1f} MB, "
          f"avg {tot/1e6/max(1,len(meta_all)):.1f} MB/traj", flush=True)


if __name__ == "__main__":
    main()
