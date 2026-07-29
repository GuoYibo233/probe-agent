"""第6步 v0: 参数头原型 —— 从候选串里挑出即将发生的工具调用的参数。

Data: data/pilot8b/*.pt (tokens, plen, layers, hidden{layer:[T,d] fp16},
inserted[(start,len)], calls[{tok_pos, query,...}]).

Design (fixed):
  1. One sample per call. Anchor feature = hidden state h_t at the position of
     the 25th generated token BEFORE the call (layer = layers[0]; positions
     inside inserted spans and inside the prompt are skipped when counting).
  2. Candidate pool from the decoded text of tokens[:anchor]:
       - quoted fragments;
       - capitalized-word runs, all sub-spans of 1-6 words;
       - 2-6 word sliding windows that contain a capitalized word.
     The true query is force-added if extraction missed it (coverage reported).
     At most 32 sampled negatives per call.
  3. Candidate repr = mean hidden state over the candidate's token span in
     context (last occurrence before the anchor). Unresolvable spans dropped.
  4. Scorer: h and c each linearly projected to 256-d, dot product + bias.
     Loss = softmax CE (positive vs negatives).
  5. 80/20 split by trajectory (per task prefix). Report held-out top-1/top-5
     and candidate-pool coverage of the true query.
"""

import argparse
import glob
import os
import random
import re

import torch

ANCHOR_BACK = 25   # anchor = 25th generated token before the call
MAX_NEG = 32
PROJ_DIM = 256
SEED = 0
DEV = "cuda" if torch.cuda.is_available() else "cpu"

# ---------------------------------------------------------------- extraction

QUOTE_RE = re.compile(r'"([^"\n]{2,80})"|“([^”\n]{2,80})”')
WORD_RE = re.compile(r"[A-Za-z0-9][\w'’\-\.]*")


def extract_candidates(text):
    """Return dict {cand_string: last_char_start} extracted from text."""
    cands = {}

    def add(s, pos):
        s = s.strip()
        if 2 <= len(s) <= 80:
            cands[s] = max(pos, cands.get(s, -1))  # keep last occurrence

    # 1) quoted fragments
    for m in QUOTE_RE.finditer(text):
        g = m.group(1) or m.group(2)
        add(g, m.start() + 1)

    words = [(m.group(0), m.start(), m.end()) for m in WORD_RE.finditer(text)]
    is_cap = [w[0][0].isupper() for w in words]

    # 2) capitalized runs, all sub-spans of 1-6 words
    i = 0
    while i < len(words):
        if is_cap[i]:
            j = i
            while j + 1 < len(words) and is_cap[j + 1] \
                    and words[j + 1][1] - words[j][2] <= 2:
                j += 1
            for a in range(i, j + 1):
                for b in range(a, min(j, a + 5) + 1):
                    add(text[words[a][1]:words[b][2]], words[a][1])
            i = j + 1
        else:
            i += 1

    # 3) 2-6 word sliding windows containing >=1 capitalized word
    for n in (2, 3, 4, 5, 6):
        for a in range(len(words) - n + 1):
            b = a + n - 1
            if words[b][2] - words[a][1] > 80:
                continue
            if "\n" in text[words[a][1]:words[b][2]]:
                continue
            if any(is_cap[k] for k in range(a, b + 1)):
                add(text[words[a][1]:words[b][2]], words[a][1])
    return cands


# ---------------------------------------------------------------- span utils

def token_offsets(tok, ids):
    """Per-token decoded pieces concatenated = canonical text; char offsets."""
    pieces = [tok.decode([t]) for t in ids]
    offs, pos = [], 0
    for p in pieces:
        offs.append((pos, pos + len(p)))
        pos += len(p)
    return "".join(pieces), offs


def char_span_to_tok(offs, cs, ce, limit):
    """Token indices in [0, limit) overlapping char range [cs, ce)."""
    idx = [i for i in range(limit)
           if offs[i][1] > cs and offs[i][0] < ce and offs[i][1] > offs[i][0]]
    return idx


def anchor_position(tok_pos, plen, inserted, back=ANCHOR_BACK):
    """Position of the `back`-th generated token before tok_pos."""
    t, cnt = tok_pos - 1, 0
    while t >= plen:
        if not any(s <= t < s + l for s, l in inserted):
            cnt += 1
            if cnt >= back:
                return t
        t -= 1
    return plen  # clamp: fewer than `back` generated tokens before the call


# ---------------------------------------------------------------- data build

def build_samples(files, tok):
    samples, n_calls = [], 0
    cov_extract = 0     # extractor found the query without force-adding
    cov_in_ctx = 0      # query occurs verbatim in decoded context[:anchor]
    rng = random.Random(SEED)
    for ti, f in enumerate(files):
        d = torch.load(f, weights_only=False)
        layer = d["layers"][0]
        h = d["hidden"][layer].float()
        ids = d["tokens"].tolist()
        plen, inserted = d["plen"], d["inserted"]
        text_full, offs = token_offsets(tok, ids)
        for call in d["calls"]:
            n_calls += 1
            q = call["query"].strip()
            anc = anchor_position(call["tok_pos"], plen, inserted)
            ctx_end = offs[anc - 1][1] if anc > 0 else 0
            text = text_full[:ctx_end]

            cands = extract_candidates(text)
            hit = q in cands
            cov_extract += hit
            qpos = text.rfind(q)
            if qpos < 0:
                continue  # positive unrecoverable from context: skip sample
            cov_in_ctx += 1
            cands[q] = max(qpos, cands.get(q, -1))

            def repr_of(s, cs):
                tix = char_span_to_tok(offs, cs, cs + len(s), anc)
                return h[tix].mean(0) if tix else None

            pos_vec = repr_of(q, cands[q])
            if pos_vec is None:
                continue
            negs = [(s, p) for s, p in cands.items() if s != q]
            rng.shuffle(negs)
            neg_vecs = []
            for s, p in negs:
                v = repr_of(s, p)
                if v is not None:
                    neg_vecs.append(v)
                if len(neg_vecs) >= MAX_NEG:
                    break
            if not neg_vecs:
                continue
            samples.append({
                "traj": ti,
                "anchor": h[anc],
                "cands": torch.stack([pos_vec] + neg_vecs),  # pos at index 0
            })
    return samples, n_calls, cov_extract, cov_in_ctx


# ---------------------------------------------------------------- model

class BilinearHead(torch.nn.Module):
    def __init__(self, d, k=PROJ_DIM):
        super().__init__()
        self.ph = torch.nn.Linear(d, k)
        self.pc = torch.nn.Linear(d, k)
        self.b = torch.nn.Parameter(torch.zeros(1))

    def forward(self, hvec, cmat):  # h:[d], c:[N,d] -> scores [N]
        return self.pc(cmat) @ self.ph(hvec) / PROJ_DIM ** 0.5 + self.b


def evaluate(model, samples):
    t1 = t5 = 0
    with torch.no_grad():
        for s in samples:
            sc = model(s["anchor"].to(DEV), s["cands"].to(DEV))
            rank = (sc > sc[0]).sum().item()  # ties favor positive
            t1 += rank < 1
            t5 += rank < 5
    n = max(1, len(samples))
    return t1 / n, t5 / n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data", "pilot8b"))
    ap.add_argument("--tokenizer", default="Qwen/Qwen3-8B")
    ap.add_argument("--epochs", type=int, default=150)
    ap.add_argument("--seed", type=int, default=SEED,
                    help="trajectory-split / training seed")
    args = ap.parse_args()
    torch.manual_seed(args.seed)

    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(args.tokenizer)

    files = sorted(glob.glob(os.path.join(args.data, "*.pt")))
    # 80/20 split by trajectory, per task prefix
    rng = random.Random(args.seed)
    tr_files, te_files = [], []
    for pref in sorted({os.path.basename(f).split("_s")[0] for f in files}):
        grp = [f for f in files if os.path.basename(f).startswith(pref)]
        rng.shuffle(grp)
        k = max(1, int(round(0.2 * len(grp))))
        te_files += grp[:k]
        tr_files += grp[k:]

    tr, n_tr, cov_e_tr, cov_c_tr = build_samples(tr_files, tok)
    te, n_te, cov_e_te, cov_c_te = build_samples(te_files, tok)
    n_all = n_tr + n_te
    cov_extract = (cov_e_tr + cov_e_te) / max(1, n_all)
    cov_in_ctx = (cov_c_tr + cov_c_te) / max(1, n_all)
    print(f"trajs train/test: {len(tr_files)}/{len(te_files)}   "
          f"calls: {n_all} (train {n_tr}, test {n_te})")
    print(f"samples usable: train {len(tr)}, test {len(te)}")
    print(f"coverage: extractor {cov_extract:.3f}  "
          f"query-in-context {cov_in_ctx:.3f}")
    if not tr or not te:
        print("not enough samples; abort")
        return

    d = tr[0]["anchor"].shape[0]
    model = BilinearHead(d).to(DEV)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-4)
    order = list(range(len(tr)))
    for ep in range(args.epochs):
        rng.shuffle(order)
        tot = 0.0
        for i in order:
            s = tr[i]
            sc = model(s["anchor"].to(DEV), s["cands"].to(DEV))
            loss = torch.nn.functional.cross_entropy(
                sc.unsqueeze(0), torch.zeros(1, dtype=torch.long, device=DEV))
            opt.zero_grad()
            loss.backward()
            opt.step()
            tot += loss.item()
        if (ep + 1) % 25 == 0:
            tr1, tr5 = evaluate(model, tr)
            e1, e5 = evaluate(model, te)
            print(f"ep {ep+1:3d}  loss {tot/len(tr):.4f}  "
                  f"train t1/t5 {tr1:.3f}/{tr5:.3f}  "
                  f"test t1/t5 {e1:.3f}/{e5:.3f}")

    t1, t5 = evaluate(model, te)
    print(f"\nFINAL held-out: top-1 {t1:.3f}  top-5 {t5:.3f}  "
          f"(n={len(te)})  cand-pool coverage {cov_extract:.3f}  "
          f"query-in-context {cov_in_ctx:.3f}")


if __name__ == "__main__":
    main()
