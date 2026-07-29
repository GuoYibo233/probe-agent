"""第17+18步 v0: 旗舰曲线小样——记忆越攒越厚, 投机器出手越来越早; 外加无关流负迁移.

流 A (相似流, 20 集): oracle_v1 的 5 个模板各 4 题交错, 首次出现分散在前 10 集
  (偶数位 0/2/4/6/8). 记忆=极简 dict, 键=模板签名 (题面去实体名/数字后的骨架),
  值=出现次数/历史成功数/学到的实体模板. 策略 (单一, 含记忆分档):
    命中且历史成功>=1 -> t=0 开火, 实体=记忆实体模板 x 题面第一个专名 (正则抽取);
    未命中 -> 退回流式探针 p>0.5 开火 (同 loop_v0).
  注入值: 抽取实体==真实体时为正确值 (流 A 恒成立); 抽错实体时为 q["wrong"]
  (模拟预取了错误实体, 数据库返回无关值).

流 B (无关流, 10 集): 5 个变体模板各 2 题, 骨架表面像流 A 但实体角色换了——
  题面第一个专名是干扰实体 (foundry/Bank/lab/institute/observatory),
  真查询实体在句子后半. 记忆从流 A 直接带入不重置 (键匹配含 Jaccard>=0.6 模糊档).
  对照 = 同一流关记忆重跑 (纯 p>0.5, 贪心+前缀复用故完全可复现).

产出: flagship_a.jsonl / flagship_b.jsonl / flagship_readings.jsonl /
      flagship_summary.json. 日志 ../logs/flagship_v0.log.
"""

import json
import random
import re
import sys
import time
from pathlib import Path

import torch

NEW1 = Path("/home/y-guo/reproduce/new1")
sys.path.insert(0, str(NEW1 / "oracle_inject"))
sys.path.insert(0, str(NEW1 / "closed_loop"))
import oracle_v1  # noqa: E402
import loop_v0 as L  # noqa: E402

MODEL = "Qwen/Qwen3-8B"
SEED = 17
CHUNK = 16
MAX_NEW = 1200
TAU = 0.5
JACCARD_THR = 0.6
OUT = NEW1 / "closed_loop"

NAME_RE = re.compile(r"\b[A-Z][a-z]+-\d+\b")

B_TEMPLATES = [
    ("the melting point in Celsius that the {d} foundry certified for {e} alloy",
     "{e} alloy", 400, 1900),
    ("the share price in dollars that {d} Bank quoted for {e} Corp",
     "{e} Corp", 4, 900),
    ("the battery capacity in mAh that the {d} lab measured for the {e} drone",
     "{e} drone", 1000, 9000),
    ("the maximum depth in meters that the {d} institute charted for Lake {e}",
     "Lake {e}", 15, 700),
    ("the atomic emission peak in nanometers that the {d} observatory logged for {e} crystal",
     "{e} crystal", 200, 1100),
]


# ---------------- signatures & memory ----------------

def signature(question):
    s = NAME_RE.sub(" <E> ", question)
    s = re.sub(r"\d+(?:\.\d+)?", " <N> ", s)
    s = s.lower()
    s = re.sub(r"[^a-z<>\s]", " ", s)
    return " ".join(s.split())


def jaccard(a, b):
    A, B = set(a.split()), set(b.split())
    return len(A & B) / max(1, len(A | B))


def match_memory(mem, sig):
    if sig in mem:
        return sig, 1.0
    best, bs = None, 0.0
    for k in mem:
        j = jaccard(sig, k)
        if j > bs:
            best, bs = k, j
    if bs >= JACCARD_THR:
        return best, bs
    return None, bs


def mem_update(mem, sig, q, correct):
    e = mem.setdefault(sig, {"count": 0, "success": 0, "ent_tpl": None})
    e["count"] += 1
    if correct:
        e["success"] += 1
        if e["ent_tpl"] is None:
            m = NAME_RE.search(q["question"])
            nm = m.group(0) if m else None
            ent = q["entity"]
            e["ent_tpl"] = ent.replace(nm, "{e}") if nm and nm in ent else ent


# ---------------- streams ----------------

def build_streams(seed):
    rng = random.Random(seed)
    used = set()

    def new_name():
        while True:
            nm = (rng.choice(oracle_v1.NAME_A) + rng.choice(oracle_v1.NAME_B)
                  + "-" + str(rng.randint(10, 99)))
            if nm not in used:
                used.add(nm)
                return nm

    def make_q(tpl, ent_tpl, lo, hi, ti, distract=False):
        nm = new_name()
        v = str(round(rng.uniform(lo, hi), 1))
        w = str(round(rng.uniform(lo, hi), 1))
        while w == v:
            w = str(round(rng.uniform(lo, hi), 1))
        kw = {"e": nm}
        if distract:
            kw["d"] = new_name()
        return {"template": ti, "question": "What is " + tpl.format(**kw) + "?",
                "entity": ent_tpl.format(e=nm), "value": v, "wrong": w}

    # stream A: 5 templates x 4, firsts at episodes 0/2/4/6/8
    per_tpl = [[make_q(*oracle_v1.TEMPLATES[ti], ti) for _ in range(4)]
               for ti in range(5)]
    first_order = list(range(5))
    rng.shuffle(first_order)
    slots = [None] * 20
    for i, ti in enumerate(first_order):
        slots[2 * i] = ti
    rest = [ti for ti in range(5) for _ in range(3)]
    other = [1, 3, 5, 7, 9] + list(range(10, 20))
    while True:
        rng.shuffle(rest)
        cand = list(slots)
        for s, ti in zip(other, rest):
            cand[s] = ti
        if all(min(i for i, t in enumerate(cand) if t == ti)
               == 2 * first_order.index(ti) for ti in range(5)):
            seq = cand
            break
    idx = [0] * 5
    stream_a = []
    for ti in seq:
        stream_a.append(per_tpl[ti][idx[ti]])
        idx[ti] += 1

    # stream B: 5 variant templates x 2, shuffled
    stream_b = [make_q(*B_TEMPLATES[ti], ti, distract=True)
                for ti in range(5) for _ in range(2)]
    rng.shuffle(stream_b)
    return stream_a, stream_b


# ---------------- episode runners ----------------

def run_baseline(model, tok, pr, q):
    """流式 baseline + 块末探针读数 (同 loop_v0). 返回 (pids, plen, ids, readings, base)."""
    sys_prompt = oracle_v1.SYSTEM + oracle_v1.PERMIT
    msgs = [{"role": "system", "content": sys_prompt},
            {"role": "user", "content": q["question"]}]
    ptext = tok.apply_chat_template(msgs, add_generation_prompt=True,
                                    enable_thinking=True, tokenize=False)
    pids = tok(ptext, return_tensors="pt",
               add_special_tokens=False).input_ids.to(model.device)
    plen = pids.shape[1]
    ids = pids.clone()
    readings = []
    while ids.shape[1] - plen < MAX_NEW:
        ids = L.gen_chunk(model, tok, ids, CHUNK)
        g = ids.shape[1] - plen
        text = tok.decode(ids[0, plen:], skip_special_tokens=False)
        if (L.CALL_RE.search(text) or L.ANS_RE.search(text)
                or ids[0, -1].item() == tok.eos_token_id):
            break
        readings.append((g, L.probe_p(model, ids, pr)))
    text = tok.decode(ids[0, plen:], skip_special_tokens=False)
    m_ans, m_call = L.ANS_RE.search(text), L.CALL_RE.search(text)
    if m_call and (not m_ans or m_call.start() < m_ans.start()):
        k = L.tok_pos_monotone(tok, ids[0, plen:],
                               lambda t: L.CALL_RE.search(t) is not None)
        ids2 = ids[:, :plen + k]
        res = f'\nRESULT: lookup("{q["entity"]}") = {q["value"]}\n'
        rid = tok(res, return_tensors="pt",
                  add_special_tokens=False).input_ids.to(ids.device)
        ids2 = torch.cat([ids2, rid], dim=1)
        ans, extra, _ = L.continue_to_answer(model, tok, ids2, q, MAX_NEW - k)
        base = dict(call_tok=k, gen_tokens=k + extra, answer=ans,
                    correct=(ans == q["value"]), called=True)
    else:
        ans = m_ans.group(1).replace(",", "") if m_ans else None
        base = dict(call_tok=None, gen_tokens=ids.shape[1] - plen, answer=ans,
                    correct=(ans == q["value"]), called=False)
    return pids, plen, ids, readings, base


def inj_ids(tok, dev, entity, value):
    inj = f'\n[SYSTEM NOTE: prefetched lookup("{entity}") = {value}]\n'
    return tok(inj, return_tensors="pt",
               add_special_tokens=False).input_ids.to(dev)


def run_threshold(model, tok, q, plen, ids, readings, base):
    """p>TAU 开火, 复用 baseline 前缀 (贪心等价). 注入正确实体+正确值."""
    fire = next((g for g, p in readings if p > TAU), None)
    if fire is None:
        return dict(fire_tok=None, gen_tokens=base["gen_tokens"],
                    answer=base["answer"], correct=base["correct"],
                    called=base["called"], fired=False)
    iid = inj_ids(tok, ids.device, q["entity"], q["value"])
    ids4 = torch.cat([ids[:, :plen + fire], iid], dim=1)
    ans, extra, called = L.continue_to_answer(model, tok, ids4, q,
                                              MAX_NEW - fire)
    return dict(fire_tok=fire, gen_tokens=fire + extra, answer=ans,
                correct=(ans == q["value"]), called=called, fired=True)


def run_t0(model, tok, q, pids, entity, value):
    iid = inj_ids(tok, pids.device, entity, value)
    ids3 = torch.cat([pids, iid], dim=1)
    ans, extra, called = L.continue_to_answer(model, tok, ids3, q, MAX_NEW)
    return dict(fire_tok=0, gen_tokens=extra, answer=ans,
                correct=(ans == q["value"]), called=called, fired=True)


# ---------------- main ----------------

def main():
    torch.manual_seed(0)
    pr = L.build_probe()
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL, dtype=torch.bfloat16, device_map="cuda",
        attn_implementation="sdpa")
    model.eval()

    stream_a, stream_b = build_streams(SEED)
    mem = {}
    fa = open(OUT / "flagship_a.jsonl", "w")
    fb = open(OUT / "flagship_b.jsonl", "w")
    fr = open(OUT / "flagship_readings.jsonl", "w")

    def emit(f, rec, keys):
        f.write(json.dumps(rec) + "\n")
        f.flush()
        print(json.dumps({k: rec.get(k) for k in keys}), flush=True)

    # ---------- stream A ----------
    for ep, q in enumerate(stream_a):
        t0 = time.time()
        pids, plen, ids, readings, base = run_baseline(model, tok, pr, q)
        fr.write(json.dumps({"stream": "A", "ep": ep,
                             "call_tok": base["call_tok"],
                             "readings": [[g, round(p, 5)] for g, p in readings]
                             }) + "\n")
        fr.flush()
        sig = signature(q["question"])
        key, jac = match_memory(mem, sig)
        hit = (key is not None and mem[key]["success"] >= 1
               and mem[key]["ent_tpl"] is not None)
        entity_ok = None
        if hit:
            extracted = NAME_RE.search(q["question"]).group(0)
            tpl = mem[key]["ent_tpl"]
            entity = tpl.format(e=extracted) if "{e}" in tpl else tpl
            entity_ok = (entity == q["entity"])
            val = q["value"] if entity_ok else q["wrong"]
            pol = run_t0(model, tok, q, pids, entity, val)
            pol["lead"] = base["call_tok"]
        else:
            pol = run_threshold(model, tok, q, plen, ids, readings, base)
            pol["lead"] = (base["call_tok"] - pol["fire_tok"]
                           if pol["fire_tok"] is not None
                           and base["call_tok"] is not None else None)
        mem_update(mem, sig, q, pol["correct"])
        rec = {"stream": "A", "ep": ep, "template": q["template"],
               "mem_hit": hit, "match_jaccard": round(jac, 3),
               "entity_ok": entity_ok,
               "fire_tok": pol["fire_tok"], "lead": pol["lead"],
               "gen_tokens": pol["gen_tokens"], "correct": pol["correct"],
               "called": pol["called"], "answer": pol["answer"],
               "base_call_tok": base["call_tok"],
               "base_gen_tokens": base["gen_tokens"],
               "base_correct": base["correct"],
               "wall_s": round(time.time() - t0, 1)}
        emit(fa, rec, ("ep", "template", "mem_hit", "fire_tok", "lead",
                       "gen_tokens", "correct", "wall_s"))
    fa.close()

    # ---------- stream B (记忆带入不重置) + 关记忆对照 ----------
    for ep, q in enumerate(stream_b):
        t0 = time.time()
        pids, plen, ids, readings, base = run_baseline(model, tok, pr, q)
        fr.write(json.dumps({"stream": "B", "ep": ep,
                             "call_tok": base["call_tok"],
                             "readings": [[g, round(p, 5)] for g, p in readings]
                             }) + "\n")
        fr.flush()
        ctrl = run_threshold(model, tok, q, plen, ids, readings, base)

        sig = signature(q["question"])
        key, jac = match_memory(mem, sig)
        hit = (key is not None and mem[key]["success"] >= 1
               and mem[key]["ent_tpl"] is not None)
        entity_ok = None
        entity = None
        if hit:
            extracted = NAME_RE.search(q["question"]).group(0)
            tpl = mem[key]["ent_tpl"]
            entity = tpl.format(e=extracted) if "{e}" in tpl else tpl
            entity_ok = (entity == q["entity"])
            val = q["value"] if entity_ok else q["wrong"]
            pol = run_t0(model, tok, q, pids, entity, val)
        else:
            pol = dict(ctrl)  # 未命中 => 与关记忆对照逐 token 相同 (贪心)
        mem_update(mem, sig, q, pol["correct"])
        rec = {"stream": "B", "ep": ep, "template": q["template"],
               "question": q["question"], "true_entity": q["entity"],
               "mem_hit": hit, "match_jaccard": round(jac, 3),
               "matched_key": key, "used_entity": entity,
               "entity_ok": entity_ok,
               "wrong_fire": bool(hit and not entity_ok),
               "fire_tok": pol["fire_tok"], "gen_tokens": pol["gen_tokens"],
               "correct": pol["correct"], "called": pol["called"],
               "answer": pol["answer"],
               "ctrl_fire_tok": ctrl["fire_tok"],
               "ctrl_gen_tokens": ctrl["gen_tokens"],
               "ctrl_correct": ctrl["correct"], "ctrl_called": ctrl["called"],
               "base_call_tok": base["call_tok"],
               "base_gen_tokens": base["gen_tokens"],
               "wall_s": round(time.time() - t0, 1)}
        emit(fb, rec, ("ep", "template", "mem_hit", "wrong_fire", "fire_tok",
                       "gen_tokens", "correct", "ctrl_gen_tokens",
                       "ctrl_correct", "wall_s"))
    fb.close()
    fr.close()

    # ---------- aggregate ----------
    ra = [json.loads(l) for l in open(OUT / "flagship_a.jsonl")]
    rb = [json.loads(l) for l in open(OUT / "flagship_b.jsonl")]
    firsts = [r for r in ra if not r["mem_hit"]]
    hits = [r for r in ra if r["mem_hit"]]

    def mean(xs):
        xs = [x for x in xs if x is not None]
        return round(sum(xs) / len(xs), 1) if xs else None

    summary = {
        "model": MODEL, "seed": SEED, "chunk": CHUNK, "tau": TAU,
        "jaccard_thr": JACCARD_THR,
        "probe_heldout_auroc": round(pr["heldout_auroc"], 4),
        "stream_a": {
            "n": len(ra),
            "fire_curve": [[r["ep"], r["fire_tok"], int(r["mem_hit"])]
                           for r in ra],
            "n_mem_hit": len(hits),
            "acc": round(sum(r["correct"] for r in ra) / len(ra), 3),
            "acc_hit": round(sum(r["correct"] for r in hits)
                             / max(1, len(hits)), 3),
            "mean_fire_miss": mean([r["fire_tok"] for r in firsts]),
            "mean_fire_hit": mean([r["fire_tok"] for r in hits]),
            "mean_gen_miss": mean([r["gen_tokens"] for r in firsts]),
            "mean_gen_hit": mean([r["gen_tokens"] for r in hits]),
            "mean_gen_base": mean([r["base_gen_tokens"] for r in ra]),
            "mean_fire_first10": mean([r["fire_tok"] for r in ra[:10]]),
            "mean_fire_last10": mean([r["fire_tok"] for r in ra[10:]]),
        },
        "stream_b": {
            "n": len(rb),
            "hit_rate": round(sum(r["mem_hit"] for r in rb) / len(rb), 3),
            "wrong_fire_rate": round(sum(r["wrong_fire"] for r in rb)
                                     / len(rb), 3),
            "acc_mem": round(sum(r["correct"] for r in rb) / len(rb), 3),
            "acc_ctrl": round(sum(r["ctrl_correct"] for r in rb) / len(rb), 3),
            "mean_gen_mem": mean([r["gen_tokens"] for r in rb]),
            "mean_gen_ctrl": mean([r["ctrl_gen_tokens"] for r in rb]),
        },
    }
    summary["stream_b"]["acc_delta"] = round(
        summary["stream_b"]["acc_mem"] - summary["stream_b"]["acc_ctrl"], 3)
    summary["stream_b"]["gen_delta"] = round(
        summary["stream_b"]["mean_gen_mem"]
        - summary["stream_b"]["mean_gen_ctrl"], 1)
    with open(OUT / "flagship_summary.json", "w") as f:
        json.dump(summary, f, indent=1)
    print(json.dumps(summary, indent=1), flush=True)


if __name__ == "__main__":
    main()
