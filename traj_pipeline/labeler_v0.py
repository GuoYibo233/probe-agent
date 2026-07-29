"""第4步先导: oracle replay labeler on stored pilot trajectories.

For each stored trajectory (clean, has calls): replay from sampled positions
with the known-correct result injected as a SYSTEM NOTE; measure benefit(t) =
baseline_gen_tokens - replay_gen_tokens, plus answer consistency with the
baseline answer (proxy for correctness on em/soft-true trajs).

Output: one json line per (traj, position) -> head-4 training labels.
"""

import argparse
import glob
import importlib.util
import json
import re

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

spec = importlib.util.spec_from_file_location(
    "hotpot_v1", "/home/y-guo/reproduce/new1/hotpot_inject/hotpot_v1.py")
H = importlib.util.module_from_spec(spec)
spec.loader.exec_module(H)

CALL_ANY_RE = re.compile(r'(?m)^\s*CALL:\s*(lookup|search)\(\s*"?([^"<>)\n]+?)"?\s*\)')
ANS_ANY_RE = re.compile(r"(?m)^\s*ANSWER:\s*(.+?)\s*$")
RES_RE = re.compile(r'RESULT:\s*(lookup|search)\("([^"]*)"\)\s*=\s*(.*)', re.S)


def stored_results(tok, d):
    """(query, full_result_payload) pairs from inserted RESULT spans."""
    out = []
    for s, l in d["inserted"]:
        txt = tok.decode(d["tokens"][s:s + l], skip_special_tokens=False)
        m = RES_RE.search(txt)
        if m:
            out.append({"tool": m.group(1), "query": m.group(2),
                        "payload": m.group(3).strip()})
    return out


def replay(model, tok, d, pos, results, budget=2000):
    """Truncate at generated-position pos (skipping inserted spans), inject
    the first not-yet-consumed result as a NOTE, continue with serving."""
    # map generated-token index -> stream index (skip inserted spans)
    stream_len = d["tokens"].shape[0]
    ins = sorted(d["inserted"])
    stream_pos, g = d["plen"], 0
    while g < pos and stream_pos < stream_len:
        if any(s == stream_pos for s, l in ins):
            stream_pos += next(l for s, l in ins if s == stream_pos)
            continue
        stream_pos += 1
        g += 1
    ids = d["tokens"][:stream_pos].unsqueeze(0).to(model.device)
    note = (f'\n[SYSTEM NOTE: prefetched {results[0]["tool"]}'
            f'("{results[0]["query"]}") = {results[0]["payload"]}]\n')
    ids, _ = H.append_text(tok, ids, note)
    served = 0
    gen = 0
    for _ in range(5):
        seg = ids.shape[1]
        ids, text = H.gen_until(
            model, tok, ids,
            lambda t: ANS_ANY_RE.search(t) or CALL_ANY_RE.search(t)
            or H.FAKE_RES_RE.search(t), budget - gen)
        m_ans, m_call, m_fake = (ANS_ANY_RE.search(text),
                                 CALL_ANY_RE.search(text),
                                 H.FAKE_RES_RE.search(text))
        ev = sorted((m.start(), k) for k, m in
                    (("ans", m_ans), ("call", m_call), ("fake", m_fake)) if m)
        kind = ev[0][1] if ev else None
        if kind == "ans":
            gen += ids.shape[1] - seg
            return pos + gen, m_ans.group(1), "ok"
        if kind == "call":
            k = H.tok_pos_of_match(tok, ids[0, seg:], CALL_ANY_RE)
            gen += k
            ids = ids[:, :seg + k]
            query = m_call.group(2).strip()
            # serve best-matching stored result
            best = max(results, key=lambda r: len(
                set(query.lower().split()) & set(r["query"].lower().split())))
            ids, _ = H.append_text(
                tok, ids,
                f'\nRESULT: {best["tool"]}("{query}") = {best["payload"]}\n')
            served += 1
            continue
        break
    _, ans = H.force_answer(model, tok, ids)
    return pos + gen, ans, "forced"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen3.5-4B")
    ap.add_argument("--shard", default="0/1")
    ap.add_argument("--out", required=True)
    ap.add_argument("--datadir", default="/home/y-guo/reproduce/new1/traj_pipeline/data/pilot")
    args = ap.parse_args()
    si, sn = (int(x) for x in args.shard.split("/"))

    tok = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForCausalLM.from_pretrained(
        args.model, dtype=torch.bfloat16, device_map="cuda",
        attn_implementation="sdpa")
    model.eval()
    out = open(args.out, "w")

    files = sorted(glob.glob(
        args.datadir + "/*.pt"))[si::sn]
    for f in files:
        d = torch.load(f, weights_only=False)
        if not d["calls"] or not d["soft"]:
            continue  # only clean trajs give trustworthy labels
        results = stored_results(tok, d)
        if not results:
            continue
        c1 = d["calls"][0]["tok_pos"] - d["plen"]  # generated idx of call1
        base_ans = d["answer"]
        base_gen = d["gen_tokens"]
        positions = sorted({0, max(0, c1 // 2), max(0, c1 - 100),
                            max(0, c1 - 50), max(0, c1 - 25),
                            max(0, c1 - 10), c1})
        for pos in positions:
            g, ans, stat = replay(model, tok, d, pos, results)
            _, soft_vs_base = H.grade(ans, base_ans or "")
            gold_num = None
            for r_ in results:
                try:
                    gold_num = str(float(r_["payload"].strip()))
                except ValueError:
                    pass
            num_ok = None
            if gold_num is not None and ans:
                m_ = re.search(r"[\-0-9.,]+", ans)
                try:
                    num_ok = m_ and str(float(m_.group().replace(",", ""))) == gold_num
                except ValueError:
                    num_ok = False
            rec = {"file": f.split("/")[-1], "pos": pos, "call1": c1,
                   "lead": c1 - pos, "gen_tokens": g,
                   "baseline_gen": base_gen, "benefit": base_gen - g,
                   "ans_match": bool(num_ok) if num_ok is not None else bool(soft_vs_base),
                   "match_kind": "gold_num" if num_ok is not None else "soft_vs_base",
                   "status": stat}
            out.write(json.dumps(rec) + "\n")
            out.flush()
            print(json.dumps(rec), flush=True)
    out.close()


if __name__ == "__main__":
    main()
