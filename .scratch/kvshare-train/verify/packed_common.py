"""Construction code shared by the three verification scripts: pick events, tokenize the
way the old trainer does, and build the packed sequence (form A).

Form A (packed into one forward pass):
    sequence = event's full-text tokens (P of them) + segment 1 + ... + segment K
    segment k = the tail of that row's prompt tokens after the common prefix p_k in the
                old trainer, plus the target-string tokens (including eos)
    mask = causal within the prefix; segment k's query sees only the first p_k prefix
           positions plus its own within-segment causal mask (bool, True = visible)
    position_ids = prefix 0..P-1; segment k continues counting from p_k
    loss positions = the logits position that predicts each target token (when the tail
                     is empty, the first target token is predicted by prefix position p_k-1)

Old trainer's convention (train_causal_callgen.py collate + inst_ce):
    each row = tok(text + SEP) + tok(label_call) + [eos], right-padded into a batch,
    labels mask out the prompt and pad, CE is taken only at target positions, and each
    row's loss = the mean CE over its target tokens.
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
    """The longest event among those whose full-text token count is ≤ max_tokens (used for the GPU peak)."""
    best, best_n = None, -1
    for k in sorted(events):
        rs = events[k]
        full = rs[-1]["text"]
        if len(full) > max_tokens * 6:          # coarse filter: a token is at least 1 character; first cut obviously overlong entries by character count
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
    """Each row's prompt/tgt tokens as the old trainer produces them (no truncation: verification only picks short events)."""
    eos = tok.eos_token_id
    rows = []
    for r in rs:
        prompt = tok(r["text"] + SEP, add_special_tokens=False)["input_ids"]
        tgt = tok(r["label_call"], add_special_tokens=False)["input_ids"] + [eos]
        assert len(tgt) <= MAX_TGT_TOK, "target string exceeds MAX_TGT_TOK, the old trainer drops this row"
        rows.append(dict(sent_idx=r["sent_idx"], prompt=prompt, tgt=tgt,
                         call=r["label_call"], w=float(r["w"])))
    return rows


def build_packed(rows, full_ids):
    """Form A's sequence, position_ids, bool mask, and loss positions (qpos -> target token)."""
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
                j = s["p"] - 1                      # empty tail: the first target token is predicted by prefix position p-1
            else:
                j = s["start"] + s["n_tail"] + t - 1
            qpos.append(j)
            ys.append(y)
            row_id.append(i)
    return dict(P=P, L=L, seq=seq, pos=pos, allow=allow, segs=segs,
                qpos=qpos, ys=ys, row_id=row_id)


def float_mask(allow, dtype):
    """bool mask -> additive mask (0 / -inf), for sdpa's floating-point mask path."""
    return torch.zeros(allow.shape, dtype=dtype).masked_fill(~allow, float("-inf"))


def per_row_mean(ce, row_id, n_rows):
    ce = ce.float()
    rid = torch.tensor(row_id, device=ce.device)
    ssum = torch.zeros(n_rows, device=ce.device).index_add(0, rid, ce)
    cnt = torch.zeros(n_rows, device=ce.device).index_add(0, rid, torch.ones_like(ce))
    return ssum / cnt


def forward_packed(model, pk, dev, mask_kind="bool", mask_dtype=torch.float32):
    """Form A's forward pass; returns (per-target-token CE [n_tgt], per-row mean CE [K])."""
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
    """Old trainer's convention: right-pad into one batch (batched=True) or one row per
    batch (batched=False).

    Same indexing as inst_ce: logits position j predicts token j+1; CE is computed only
    at target positions.
    Use logits_to_keep to compute only the needed positions (lm_head is a per-position
    linear layer, so taking a subset does not change the values).
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
