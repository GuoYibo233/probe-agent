"""第5步 v0: linear probe for head-1 (will a CALL occur within next H tokens?).

Data: pilot .pt trajectories (hidden states at layers 10/14, call positions).
Split by trajectory. Logistic regression in torch. Reports AUROC per layer
vs a position-fraction-only baseline.
"""

import glob
import json

import torch

H_AHEAD = 32
DEV = "cuda" if torch.cuda.is_available() else "cpu"


def auroc(scores, labels):
    order = scores.argsort()
    ranks = torch.empty_like(order, dtype=torch.float)
    ranks[order] = torch.arange(len(scores), dtype=torch.float)
    pos = labels == 1
    n1, n0 = pos.sum().item(), (~pos).sum().item()
    if n1 == 0 or n0 == 0:
        return float("nan")
    return (ranks[pos].sum().item() - n1 * (n1 - 1) / 2) / (n1 * n0)


def load(files, layer):
    X, y, pos_frac, tid = [], [], [], []
    for ti, f in enumerate(files):
        d = torch.load(f, weights_only=False)
        T, plen = d["tokens"].shape[0], d["plen"]
        calls = [c["tok_pos"] for c in d["calls"]]
        ins = d["inserted"]
        h = d["hidden"][layer]
        for t in range(plen, T - 1):
            if any(s <= t < s + l for s, l in ins):
                continue  # inside inserted RESULT text
            lab = 1.0 if any(t < c <= t + H_AHEAD for c in calls) else 0.0
            X.append(h[t])
            y.append(lab)
            pos_frac.append((t - plen) / max(1, T - plen))
            tid.append(ti)
    return (torch.stack(X).float(), torch.tensor(y), torch.tensor(pos_frac),
            torch.tensor(tid))


def train_lr(Xtr, ytr, Xte, dim):
    w = torch.zeros(dim, device=DEV, requires_grad=True)
    b = torch.zeros(1, device=DEV, requires_grad=True)
    opt = torch.optim.Adam([w, b], lr=1e-3)
    Xtr_, ytr_ = Xtr.to(DEV), ytr.to(DEV)
    pw = ((ytr == 0).sum() / max(1, (ytr == 1).sum())).to(DEV)
    for ep in range(300):
        opt.zero_grad()
        logit = Xtr_ @ w + b
        loss = torch.nn.functional.binary_cross_entropy_with_logits(
            logit, ytr_, pos_weight=pw)
        loss.backward()
        opt.step()
    with torch.no_grad():
        return (Xte.to(DEV) @ w + b).cpu()


def main():
    files = sorted(glob.glob(
        "/home/y-guo/reproduce/new1/traj_pipeline/data/pilot/*.pt"))
    d0 = torch.load(files[0], weights_only=False)
    layers = d0["layers"]
    n_tr = int(len(files) * 0.8)
    out = {}
    for layer in layers:
        Xtr, ytr, ptr, _ = load(files[:n_tr], layer)
        Xte, yte, pte, _ = load(files[n_tr:], layer)
        mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-5
        s = train_lr((Xtr - mu) / sd, ytr, (Xte - mu) / sd, Xtr.shape[1])
        out[f"layer{layer}"] = {
            "auroc": round(auroc(s, yte), 4),
            "n_train": len(ytr), "n_test": len(yte),
            "pos_rate_test": round(yte.mean().item(), 3)}
        # baseline: position fraction only
        sb = train_lr(ptr.unsqueeze(1), ytr, pte.unsqueeze(1), 1)
        out[f"layer{layer}"]["posfrac_baseline_auroc"] = round(auroc(sb, yte), 4)
    print(json.dumps({"H_ahead": H_AHEAD, "n_traj": len(files),
                      "split": f"{n_tr}/{len(files)-n_tr}", **out}, indent=1))


if __name__ == "__main__":
    main()
