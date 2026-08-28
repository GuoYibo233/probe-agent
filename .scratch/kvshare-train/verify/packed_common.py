"""三个验证脚本共用的构造代码:选事件、按旧训练器分词、造打包序列(形态 A)。

形态 A(打包一次前向):
    序列 = 事件全文 token(P 个) + 段1 + ... + 段K
    段k  = 旧训练器该行 prompt token 里公共前缀 p_k 之后的尾巴 + 目标串 token(含 eos)
    掩码 = 前缀内因果;段k 的 query 只看前缀前 p_k 位 + 自己段内因果(bool,True=可看)
    position_ids = 前缀 0..P-1;段k 从 p_k 接着数
    loss 位 = 预测每个目标 token 的 logits 位置(尾巴为空时首个目标 token 由前缀第 p_k-1 位预测)

旧训练器口径(train_causal_callgen.py collate + inst_ce):
    每行 = tok(text + SEP) + tok(label_call) + [eos],右 padding 成一批,labels 掩掉 prompt 与 pad,
    只在目标位取 CE,每行 loss = 目标 token 的 CE 平均。
"""
import json
import random
from collections import defaultdict

import torch
import torch.nn.functional as F

MODEL = "/net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-0.6B-Base"
VAL = "pipeline/data/nyapass_aw_v1/gptoss/val.jsonl"
SEP = "\n[CALL] "
MAX_TGT_TOK = 160


def load_events(path=VAL):
    ev = defaultdict(list)
    for line in open(path):
        r = json.loads(line)
        ev[r["event"]].append(r)
    out = {}
    for k, rs in ev.items():
        rs.sort(key=lambda r: r["sent_idx"])
        out[k] = rs
    return out


def pick_events(events, n, max_rows, max_chars, seed, min_rows=2):
    cands = []
    for k in sorted(events):
        rs = events[k]
        full = rs[-1]["text"]
        if min_rows <= len(rs) <= max_rows and len(full) <= max_chars \
                and all(full.startswith(r["text"]) for r in rs):
            cands.append(k)
    rng = random.Random(seed)
    chosen = rng.sample(cands, min(n, len(cands)))
    return chosen, len(cands)


def longest_event_within(events, tok, max_tokens):
    """全文 token 数 ≤ max_tokens 的事件里最长的一个(GPU 峰值用)。"""
    best, best_n = None, -1
    for k in sorted(events):
        rs = events[k]
        full = rs[-1]["text"]
        if len(full) > max_tokens * 6:          # 粗筛:一个 token 至少 1 字符,先按字符砍掉明显超长的
            continue
        n = len(tok(full, add_special_tokens=False)["input_ids"])
        if best_n < n <= max_tokens:
            best, best_n = k, n
    return best, best_n


def lcp(a, b):
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def build_rows(tok, rs):
    """旧训练器每行的 prompt/tgt token(不截断:验证只选短事件)。"""
    eos = tok.eos_token_id
    rows = []
    for r in rs:
        prompt = tok(r["text"] + SEP, add_special_tokens=False)["input_ids"]
        tgt = tok(r["label_call"], add_special_tokens=False)["input_ids"] + [eos]
        assert len(tgt) <= MAX_TGT_TOK, "目标串超 MAX_TGT_TOK,旧训练器会丢弃这一行"
        rows.append(dict(sent_idx=r["sent_idx"], prompt=prompt, tgt=tgt,
                         call=r["label_call"], w=float(r["w"])))
    return rows


def build_packed(rows, full_ids):
    """形态 A 的序列、position_ids、bool 掩码、loss 位(qpos -> 目标 token)。"""
    P = len(full_ids)
    seq = list(full_ids)
    pos = list(range(P))
    segs = []
    for r in rows:
        p = lcp(r["prompt"], full_ids)
        tail = r["prompt"][p:]
        start = len(seq)
        seg = tail + r["tgt"]
        seq += seg
        pos += list(range(p, p + len(seg)))
        segs.append(dict(p=p, start=start, end=start + len(seg),
                         n_tail=len(tail), n_tgt=len(r["tgt"]),
                         prompt_len=len(r["prompt"])))
    L = len(seq)
    allow = torch.zeros(L, L, dtype=torch.bool)
    allow[:P, :P] = torch.ones(P, P, dtype=torch.bool).tril()
    for s in segs:
        allow[s["start"]:s["end"], :s["p"]] = True
        n = s["end"] - s["start"]
        allow[s["start"]:s["end"], s["start"]:s["end"]] = torch.ones(n, n, dtype=torch.bool).tril()
    qpos, ys, row_id = [], [], []
    for i, (r, s) in enumerate(zip(rows, segs)):
        for t, y in enumerate(r["tgt"]):
            if t == 0 and s["n_tail"] == 0:
                j = s["p"] - 1                      # 尾巴为空:首个目标 token 由前缀第 p-1 位预测
            else:
                j = s["start"] + s["n_tail"] + t - 1
            qpos.append(j)
            ys.append(y)
            row_id.append(i)
    return dict(P=P, L=L, seq=seq, pos=pos, allow=allow, segs=segs,
                qpos=qpos, ys=ys, row_id=row_id)


def float_mask(allow, dtype):
    """bool 掩码 -> 加性掩码(0 / -inf),给 sdpa 的浮点掩码路径。"""
    return torch.zeros(allow.shape, dtype=dtype).masked_fill(~allow, float("-inf"))


def per_row_mean(ce, row_id, n_rows):
    ce = ce.float()
    rid = torch.tensor(row_id, device=ce.device)
    ssum = torch.zeros(n_rows, device=ce.device).index_add(0, rid, ce)
    cnt = torch.zeros(n_rows, device=ce.device).index_add(0, rid, torch.ones_like(ce))
    return ssum / cnt


def forward_packed(model, pk, dev, mask_kind="bool", mask_dtype=torch.float32):
    """形态 A 前向,返回 (每目标 token 的 CE [n_tgt], 每行 mean CE [K])。"""
    L = pk["L"]
    if mask_kind == "bool":
        mask = pk["allow"][None, None].to(dev)
    else:
        mask = float_mask(pk["allow"], mask_dtype)[None, None].to(dev)
    keep = sorted(set(pk["qpos"]))
    col = {p: c for c, p in enumerate(keep)}
    out = model(input_ids=torch.tensor(pk["seq"], device=dev)[None],
                attention_mask=mask,
                position_ids=torch.tensor(pk["pos"], device=dev)[None],
                use_cache=False,
                logits_to_keep=torch.tensor(keep, device=dev))
    lg = out.logits[0].float()
    idx = torch.tensor([col[j] for j in pk["qpos"]], device=dev)
    ce = F.cross_entropy(lg[idx], torch.tensor(pk["ys"], device=dev), reduction="none")
    return ce, per_row_mean(ce, pk["row_id"], len(pk["segs"]))


def forward_old(model, tok, rows, dev, batched=True):
    """旧训练器口径:右 padding 一批(batched=True)或每行单独一批(batched=False)。

    与 inst_ce 同一套下标:logits 第 j 位预测第 j+1 个 token;只在目标位算 CE。
    用 logits_to_keep 只算需要的位置(lm_head 是逐位置线性层,取子集不改数值)。
    """
    groups = [rows] if batched else [[r] for r in rows]
    ces, rows_mean = [], []
    for g in groups:
        ids = [r["prompt"] + r["tgt"] for r in g]
        n, L = len(ids), max(map(len, ids))
        pad = tok.pad_token_id
        input_ids = torch.full((n, L), pad, dtype=torch.long)
        attn = torch.zeros((n, L), dtype=torch.long)
        for i, x in enumerate(ids):
            input_ids[i, :len(x)] = torch.tensor(x)
            attn[i, :len(x)] = 1
        qpos, ys, rid = [], [], []
        for i, r in enumerate(g):
            P = len(r["prompt"])
            for t, y in enumerate(r["tgt"]):
                qpos.append(P + t - 1)
                ys.append(y)
                rid.append(i)
        keep = sorted(set(qpos))
        col = {p: c for c, p in enumerate(keep)}
        out = model(input_ids=input_ids.to(dev), attention_mask=attn.to(dev),
                    use_cache=False, logits_to_keep=torch.tensor(keep, device=dev))
        lg = out.logits.float()
        ii = torch.tensor(rid, device=dev)
        cc = torch.tensor([col[j] for j in qpos], device=dev)
        ce = F.cross_entropy(lg[ii, cc], torch.tensor(ys, device=dev), reduction="none")
        ces.append(ce)
        rows_mean.append(per_row_mean(ce, rid, n))
    return torch.cat(ces), torch.cat(rows_mean)


def diff_stats(a, b):
    a, b = a.float().cpu(), b.float().cpu()
    d = (a - b).abs()
    rel = d / a.abs().clamp(min=1e-12)
    return dict(n=int(d.numel()), max_abs=float(d.max()), mean_abs=float(d.mean()),
                p90_abs=float(d.quantile(0.9)) if d.numel() > 1 else float(d.max()),
                max_rel=float(rel.max()))
