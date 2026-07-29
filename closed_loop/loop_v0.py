"""第8+9步 v0: 最小流式闭环——探针置信度开火 vs 固定时机开火.

设置:
  任务: oracle_v1 合成 lookup, n=40, seed=13, Qwen3-8B 贪心.
  探针: 在 pilot8b synthetic_*.pt 上现训逻辑回归 (layer=layers[0]=11,
        标签=未来 32 token 内有 CALL, 照 train_probe_v1 做法).
  流式: 每 16 token 一块, 块末尾额外前向 output_hidden_states 读末 token
        探针概率 p. 开火=追加 [SYSTEM NOTE: prefetched ...] (正确值).
  五策略: baseline(不注入) / t0(0 时刻开火) / p>0.5 / p>0.9 / p>0.99.

产出: results_v0.jsonl (每题每策略一行), readings_v0.jsonl (每题的 p 轨迹),
      summary_v0.json (五策略聚合 + 流式 AUROC).
"""

import glob
import json
import sys
import time
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

NEW1 = Path("/home/y-guo/reproduce/new1")
sys.path.insert(0, str(NEW1 / "oracle_inject"))
import oracle_v1  # noqa: E402

MODEL = "Qwen/Qwen3-8B"
N_Q, SEED = 40, 13
CHUNK = 16
MAX_NEW = 1200
H_AHEAD = 32
THRESHOLDS = [0.5, 0.9, 0.99]
OUTDIR = NEW1 / "closed_loop"
DEV = "cuda"

CALL_RE, ANS_RE = oracle_v1.CALL_RE, oracle_v1.ANS_RE


# ---------------- probe training (照 train_probe_v1) ----------------

def load_probe_data(files, layer):
    X, y, tid = [], [], []
    for ti, f in enumerate(files):
        d = torch.load(f, weights_only=False)
        T, plen = d["tokens"].shape[0], d["plen"]
        calls = [c["tok_pos"] for c in d["calls"]]
        ins = d["inserted"]
        h = d["hidden"][layer]
        for t in range(plen, T - 1):
            if any(s <= t < s + l for s, l in ins):
                continue
            lab = 1.0 if any(t < c <= t + H_AHEAD for c in calls) else 0.0
            X.append(h[t])
            y.append(lab)
            tid.append(ti)
    return torch.stack(X).float(), torch.tensor(y), torch.tensor(tid)


def train_lr(Xtr, ytr, dim, epochs=300):
    w = torch.zeros(dim, device=DEV, requires_grad=True)
    b = torch.zeros(1, device=DEV, requires_grad=True)
    opt = torch.optim.Adam([w, b], lr=1e-3)
    Xtr_, ytr_ = Xtr.to(DEV), ytr.to(DEV)
    pw = ((ytr == 0).sum() / max(1, (ytr == 1).sum())).to(DEV)
    for _ in range(epochs):
        opt.zero_grad()
        logit = Xtr_ @ w + b
        loss = torch.nn.functional.binary_cross_entropy_with_logits(
            logit, ytr_, pos_weight=pw)
        loss.backward()
        opt.step()
    return w.detach(), b.detach()


def auroc(scores, labels):
    scores, labels = torch.as_tensor(scores), torch.as_tensor(labels)
    order = scores.argsort()
    ranks = torch.empty_like(order, dtype=torch.float)
    ranks[order] = torch.arange(len(scores), dtype=torch.float)
    pos = labels == 1
    n1, n0 = pos.sum().item(), (~pos).sum().item()
    if n1 == 0 or n0 == 0:
        return float("nan")
    return (ranks[pos].sum().item() - n1 * (n1 - 1) / 2) / (n1 * n0)


def build_probe():
    files = sorted(glob.glob(
        str(NEW1 / "traj_pipeline/data/pilot8b/synthetic_*.pt")))
    layer = torch.load(files[0], weights_only=False)["layers"][0]
    # held-out check: 16/4 by trajectory
    Xa, ya, _ = load_probe_data(files[:16], layer)
    Xb, yb, _ = load_probe_data(files[16:], layer)
    mu, sd = Xa.mean(0), Xa.std(0) + 1e-5
    w, b = train_lr((Xa - mu) / sd, ya, Xa.shape[1])
    with torch.no_grad():
        s = (((Xb - mu) / sd).to(DEV) @ w + b).cpu()
    held_auroc = auroc(s, yb)
    print(f"[probe] layer={layer} heldout(4traj) AUROC={held_auroc:.4f} "
          f"n_tr={len(ya)} n_te={len(yb)} pos_te={yb.mean():.3f}", flush=True)
    # deploy probe: retrain on all 20 trajectories
    X, y, _ = load_probe_data(files, layer)
    mu, sd = X.mean(0), X.std(0) + 1e-5
    w, b = train_lr((X - mu) / sd, y, X.shape[1])
    return {"layer": layer, "w": w.float(), "b": b.float(),
            "mu": mu.to(DEV), "sd": sd.to(DEV),
            "heldout_auroc": held_auroc}


# ---------------- generation utilities ----------------

def gen_chunk(model, tok, ids, n):
    with torch.no_grad():
        out = model.generate(ids, max_new_tokens=n, do_sample=False,
                             pad_token_id=tok.eos_token_id)
    return out


def probe_p(model, ids, pr):
    with torch.no_grad():
        out = model(ids, output_hidden_states=True, use_cache=False)
        h = out.hidden_states[pr["layer"]][0, -1].float()
    z = (h - pr["mu"]) / pr["sd"]
    return torch.sigmoid(z @ pr["w"] + pr["b"]).item()


def tok_pos_monotone(tok, seg_ids, pred):
    """smallest k with pred(decode(seg_ids[:k])) true; pred monotone."""
    lo, hi = 1, seg_ids.shape[0]
    while lo < hi:
        mid = (lo + hi) // 2
        if pred(tok.decode(seg_ids[:mid], skip_special_tokens=False)):
            hi = mid
        else:
            lo = mid + 1
    return lo


def gen_until(model, tok, ids, stop_pred, budget, chunk=48):
    start = ids.shape[1]
    while ids.shape[1] - start < budget:
        ids = gen_chunk(model, tok, ids,
                        min(chunk, budget - (ids.shape[1] - start)))
        text = tok.decode(ids[0, start:], skip_special_tokens=False)
        if stop_pred(text) or ids[0, -1].item() == tok.eos_token_id:
            break
    return ids, tok.decode(ids[0, start:], skip_special_tokens=False)


def continue_to_answer(model, tok, ids, q, budget):
    """续跑到 ANSWER; 出现 CALL 则截到调用末尾并喂 RESULT (照 oracle_v1 逻辑,
    token 计数用二分截断保证精确). 返回 (answer, gen_count, called)."""
    gen_count, called = 0, False
    for _hop in range(3):
        seg_start = ids.shape[1]
        ids, text = gen_until(model, tok, ids,
                              lambda t: ANS_RE.search(t) or CALL_RE.search(t),
                              budget - gen_count)
        m_ans, m_call = ANS_RE.search(text), CALL_RE.search(text)
        seg = ids[0, seg_start:]
        if m_ans and (not m_call or m_ans.start() < m_call.start()):
            final = m_ans.group(1).replace(",", "")
            k = tok_pos_monotone(tok, seg, lambda t: (
                ANS_RE.search(t) is not None
                and ANS_RE.search(t).group(1).replace(",", "") == final))
            gen_count += k
            return final, gen_count, called
        if m_call:
            called = True
            k = tok_pos_monotone(tok, seg,
                                 lambda t: CALL_RE.search(t) is not None)
            gen_count += k
            ids = ids[:, :seg_start + k]
            res = f'\nRESULT: lookup("{q["entity"]}") = {q["value"]}\n'
            rid = tok(res, return_tensors="pt",
                      add_special_tokens=False).input_ids.to(ids.device)
            ids = torch.cat([ids, rid], dim=1)
            continue
        # eos / budget out without ANS or CALL
        gen_count += seg.shape[0]
        return None, gen_count, called
    return None, gen_count, called


# ---------------- main ----------------

def main():
    torch.manual_seed(0)
    OUTDIR.mkdir(exist_ok=True)
    pr = build_probe()

    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL, dtype=torch.bfloat16, device_map="cuda",
        attn_implementation="sdpa")
    model.eval()

    questions = oracle_v1.build_questions(N_Q, SEED)
    fout = open(OUTDIR / "results_v0.jsonl", "w")
    fread = open(OUTDIR / "readings_v0.jsonl", "w")

    def emit(rec):
        fout.write(json.dumps(rec) + "\n")
        fout.flush()
        print(json.dumps({k: rec[k] for k in
                          ("qid", "strategy", "fire_tok", "lead",
                           "gen_tokens", "correct", "called")}), flush=True)

    stream_scores, stream_labels = [], []

    for q in questions:
        sys_prompt = oracle_v1.SYSTEM + oracle_v1.PERMIT
        msgs = [{"role": "system", "content": sys_prompt},
                {"role": "user", "content": q["question"]}]
        ptext = tok.apply_chat_template(msgs, add_generation_prompt=True,
                                        enable_thinking=True, tokenize=False)
        pids = tok(ptext, return_tensors="pt",
                   add_special_tokens=False).input_ids.to(model.device)
        plen = pids.shape[1]
        inj = (f'\n[SYSTEM NOTE: prefetched lookup("{q["entity"]}") '
               f'= {q["value"]}]\n')
        iid = tok(inj, return_tensors="pt",
                  add_special_tokens=False).input_ids.to(model.device)

        # ---- baseline: 流式生成 + 每块末读探针 (贪心 => 前缀可复用) ----
        t0 = time.time()
        ids = pids.clone()
        readings = []  # (g, p) 全部在自然调用点之前
        while ids.shape[1] - plen < MAX_NEW:
            ids = gen_chunk(model, tok, ids, CHUNK)
            g = ids.shape[1] - plen
            text = tok.decode(ids[0, plen:], skip_special_tokens=False)
            if (CALL_RE.search(text) or ANS_RE.search(text)
                    or ids[0, -1].item() == tok.eos_token_id):
                break
            readings.append((g, probe_p(model, ids, pr)))
        text = tok.decode(ids[0, plen:], skip_special_tokens=False)
        m_ans, m_call = ANS_RE.search(text), CALL_RE.search(text)

        call_tok = None
        base = {"qid": q["qid"], "strategy": "baseline",
                "fire_tok": None, "lead": None}
        if m_call and (not m_ans or m_call.start() < m_ans.start()):
            k = tok_pos_monotone(tok, ids[0, plen:],
                                 lambda t: CALL_RE.search(t) is not None)
            call_tok = k
            ids2 = ids[:, :plen + k]
            res = f'\nRESULT: lookup("{q["entity"]}") = {q["value"]}\n'
            rid = tok(res, return_tensors="pt",
                      add_special_tokens=False).input_ids.to(ids.device)
            ids2 = torch.cat([ids2, rid], dim=1)
            ans, extra, _ = continue_to_answer(model, tok, ids2, q,
                                               MAX_NEW - k)
            base.update(call_tok=k, gen_tokens=k + extra, answer=ans,
                        correct=(ans == q["value"]), called=True)
        else:
            ans = m_ans.group(1).replace(",", "") if m_ans else None
            base.update(call_tok=None, gen_tokens=ids.shape[1] - plen,
                        answer=ans, correct=(ans == q["value"]), called=False)
        base["wall_s"] = round(time.time() - t0, 1)
        emit(base)

        for g, p in readings:
            stream_scores.append(p)
            stream_labels.append(
                1.0 if (call_tok is not None and g - 1 < call_tok <= g - 1
                        + H_AHEAD) else 0.0)
        fread.write(json.dumps({"qid": q["qid"], "call_tok": call_tok,
                                "readings": [[g, round(p, 5)]
                                             for g, p in readings]}) + "\n")
        fread.flush()

        # ---- t=0 开火 ----
        t0 = time.time()
        ids3 = torch.cat([pids, iid], dim=1)
        ans, extra, called = continue_to_answer(model, tok, ids3, q, MAX_NEW)
        emit({"qid": q["qid"], "strategy": "t0", "fire_tok": 0,
              "lead": call_tok, "call_tok": call_tok, "gen_tokens": extra,
              "answer": ans, "correct": (ans == q["value"]), "called": called,
              "wall_s": round(time.time() - t0, 1)})

        # ---- 阈值开火: 复用 baseline 前缀 (贪心等价) ----
        for tau in THRESHOLDS:
            name = f"p>{tau}"
            t0 = time.time()
            fire = next((g for g, p in readings if p > tau), None)
            if fire is None:
                # 调用点之前从未跨越阈值 => 行为与 baseline 逐 token 相同
                emit({"qid": q["qid"], "strategy": name, "fire_tok": None,
                      "lead": None, "call_tok": call_tok,
                      "gen_tokens": base["gen_tokens"],
                      "answer": base["answer"], "correct": base["correct"],
                      "called": base["called"], "fired": False,
                      "wall_s": 0.0})
                continue
            ids4 = torch.cat([ids[:, :plen + fire], iid], dim=1)
            ans, extra, called = continue_to_answer(model, tok, ids4, q,
                                                    MAX_NEW - fire)
            emit({"qid": q["qid"], "strategy": name, "fire_tok": fire,
                  "lead": (call_tok - fire) if call_tok is not None else None,
                  "call_tok": call_tok, "gen_tokens": fire + extra,
                  "answer": ans, "correct": (ans == q["value"]),
                  "called": called, "fired": True,
                  "wall_s": round(time.time() - t0, 1)})

    fout.close()
    fread.close()

    # ---- aggregate ----
    recs = [json.loads(l) for l in open(OUTDIR / "results_v0.jsonl")]
    summary = {"model": MODEL, "n": N_Q, "seed": SEED, "chunk": CHUNK,
               "probe_layer": pr["layer"],
               "probe_heldout_auroc": round(pr["heldout_auroc"], 4),
               "streaming_auroc": round(auroc(stream_scores, stream_labels), 4),
               "n_stream_readings": len(stream_scores),
               "stream_pos_rate": round(
                   sum(stream_labels) / max(1, len(stream_labels)), 3),
               "strategies": {}}
    for s in ["baseline", "t0"] + [f"p>{t}" for t in THRESHOLDS]:
        rs = [r for r in recs if r["strategy"] == s]
        fired = [r for r in rs if r.get("fire_tok") is not None]
        leads = [r["lead"] for r in fired if r.get("lead") is not None]
        summary["strategies"][s] = {
            "n": len(rs),
            "acc": round(sum(r["correct"] for r in rs) / len(rs), 3),
            "mean_gen_tokens": round(
                sum(r["gen_tokens"] for r in rs) / len(rs), 1),
            "fire_rate": round(len(fired) / len(rs), 3),
            "mean_fire_tok": round(sum(r["fire_tok"] for r in fired)
                                   / len(fired), 1) if fired else None,
            "mean_lead": round(sum(leads) / len(leads), 1) if leads else None,
            "call_saved_rate": round(
                sum(1 for r in rs if not r["called"]) / len(rs), 3),
        }
    with open(OUTDIR / "summary_v0.json", "w") as f:
        json.dump(summary, f, indent=1)
    print(json.dumps(summary, indent=1), flush=True)


if __name__ == "__main__":
    main()
