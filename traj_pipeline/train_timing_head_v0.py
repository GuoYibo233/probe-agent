"""第7步 v0:时机头——从隐藏态回归"此刻注入的收益"。

数据:
- 标签 data/labels8b_v0.shard*.jsonl(status=="ok"),y = benefit / baseline_gen
- 特征 data/pilot8b/<file>.pt,取 layers[0] 层、注入点(pos 映射回流内位置)的隐藏态

模型:两层 MLP(256 hidden),MSE;按轨迹(file)80/20 切。
基线:(a) lead/baseline_gen 标量线性回归 (b) 全局均值。
报告:held-out Spearman / MSE、lead 桶(预测均值 vs 真值均值)、
      测试轨迹上预测收益随 lead 缩小的走势。
"""
import os

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "5")

import glob
import json
import random
from collections import defaultdict

import torch
import torch.nn as nn

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
SEEDS = [0, 1, 2, 3, 4]
PRIMARY_SEED = 0
EPOCHS = 300
LR = 1e-3
WD = 1e-4

LEAD_BUCKETS = [
    (">100", lambda l: l > 100),
    ("51-100", lambda l: 51 <= l <= 100),
    ("26-50", lambda l: 26 <= l <= 50),
    ("11-25", lambda l: 11 <= l <= 25),
    ("1-10", lambda l: 1 <= l <= 10),
    ("0", lambda l: l == 0),
]


def map_pos_to_stream(pos, plen, inserted, total):
    """生成 token 序号 pos(不含 inserted 区间)→ 流内绝对位置。"""
    span = {int(s): int(n) for s, n in inserted}
    i = plen
    gen = 0
    while i < total:
        if i in span:
            i += span[i]
            continue
        if gen == pos:
            return i
        gen += 1
        i += 1
    raise ValueError(f"pos {pos} out of stream (plen={plen}, total={total})")


def load_dataset():
    rows = []
    for f in sorted(glob.glob(os.path.join(DATA, "labels8b_v0.shard*.jsonl"))):
        for line in open(f):
            r = json.loads(line)
            if r.get("status") == "ok":
                rows.append(r)

    cache = {}
    X, y, lead, base, files = [], [], [], [], []
    skipped = 0
    for r in rows:
        fn = r["file"]
        if fn not in cache:
            cache[fn] = torch.load(
                os.path.join(DATA, "pilot8b", fn), map_location="cpu", weights_only=False
            )
        d = cache[fn]
        layer = d["layers"][0]
        try:
            idx = map_pos_to_stream(r["pos"], d["plen"], d["inserted"], len(d["tokens"]))
        except ValueError:
            skipped += 1
            continue
        X.append(d["hidden"][layer][idx].float())
        y.append(r["benefit"] / r["baseline_gen"])
        lead.append(r["lead"])
        base.append(r["baseline_gen"])
        files.append(fn)
    print(f"loaded {len(y)} samples from {len(set(files))} trajectories, skipped {skipped}")
    return torch.stack(X), torch.tensor(y), torch.tensor(lead, dtype=torch.float32), \
        torch.tensor(base, dtype=torch.float32), files


def spearman(a, b):
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        rk = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0
            for k in range(i, j + 1):
                rk[order[k]] = avg
            i = j + 1
        return torch.tensor(rk)

    ra, rb = ranks(list(a)), ranks(list(b))
    ra, rb = ra - ra.mean(), rb - rb.mean()
    den = ra.norm() * rb.norm()
    return float((ra @ rb) / den) if den > 0 else float("nan")


def split_by_file(files, seed):
    uniq = sorted(set(files))
    rng = random.Random(seed)
    rng.shuffle(uniq)
    n_test = max(1, round(len(uniq) * 0.2))
    test_files = set(uniq[:n_test])
    tr = [i for i, f in enumerate(files) if f not in test_files]
    te = [i for i, f in enumerate(files) if f in test_files]
    return tr, te


def run_seed(X, y, lead, base, files, seed, device, verbose=False):
    tr, te = split_by_file(files, seed)
    Xtr, Xte = X[tr], X[te]
    ytr, yte = y[tr], y[te]

    mu, sd = Xtr.mean(0), Xtr.std(0).clamp_min(1e-6)
    Xtr = ((Xtr - mu) / sd).to(device)
    Xte = ((Xte - mu) / sd).to(device)

    torch.manual_seed(seed)
    mlp = nn.Sequential(nn.Linear(X.shape[1], 256), nn.ReLU(), nn.Linear(256, 1)).to(device)
    opt = torch.optim.Adam(mlp.parameters(), lr=LR, weight_decay=WD)
    ytr_d = ytr.to(device)
    for _ in range(EPOCHS):
        opt.zero_grad()
        loss = nn.functional.mse_loss(mlp(Xtr).squeeze(-1), ytr_d)
        loss.backward()
        opt.step()
    with torch.no_grad():
        pred = mlp(Xte).squeeze(-1).cpu()

    # 基线 a:lead/baseline_gen 标量线性回归(闭式解)
    str_ = (lead / base)
    A = torch.stack([str_[tr], torch.ones(len(tr))], dim=1)
    w = torch.linalg.lstsq(A, ytr.unsqueeze(1)).solution.squeeze(1)
    pred_lin = str_[te] * w[0] + w[1]

    # 基线 b:全局均值
    pred_mean = torch.full((len(te),), float(ytr.mean()))

    res = {
        "mlp": (spearman(pred.tolist(), yte.tolist()), float(((pred - yte) ** 2).mean())),
        "lin": (spearman(pred_lin.tolist(), yte.tolist()), float(((pred_lin - yte) ** 2).mean())),
        "mean": (float("nan"), float(((pred_mean - yte) ** 2).mean())),
        "n_test": len(te),
        "n_test_files": len(set(files[i] for i in te)),
    }

    if verbose:
        print(f"\n=== primary seed {seed}: lead 桶(测试集,n={len(te)}) ===")
        print(f"{'bucket':>8} {'n':>4} {'pred_mean':>10} {'true_mean':>10}")
        for name, cond in LEAD_BUCKETS:
            sel = [k for k, i in enumerate(te) if cond(int(lead[i]))]
            if not sel:
                print(f"{name:>8} {0:>4} {'-':>10} {'-':>10}")
                continue
            pm = float(pred[sel].mean())
            tm = float(yte[sel].mean())
            print(f"{name:>8} {len(sel):>4} {pm:>10.3f} {tm:>10.3f}")

        print(f"\n=== 测试轨迹:预测收益随 lead 缩小的走势(lead: true/pred) ===")
        byfile = defaultdict(list)
        for k, i in enumerate(te):
            byfile[files[i]].append((int(lead[i]), float(yte[k]), float(pred[k])))
        for fn in sorted(byfile):
            pts = sorted(byfile[fn], reverse=True)
            trace = "  ".join(f"{l}: {t:.2f}/{p:.2f}" for l, t, p in pts)
            print(f"{fn}: {trace}")
    return res


def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("device:", device)
    X, y, lead, base, files = load_dataset()

    all_res = []
    for seed in SEEDS:
        r = run_seed(X, y, lead, base, files, seed, device, verbose=(seed == PRIMARY_SEED))
        all_res.append(r)
        print(f"seed {seed}: mlp sp={r['mlp'][0]:.3f} mse={r['mlp'][1]:.3f} | "
              f"lin(lead/base) sp={r['lin'][0]:.3f} mse={r['lin'][1]:.3f} | "
              f"mean mse={r['mean'][1]:.3f} | test n={r['n_test']} ({r['n_test_files']} traj)")

    def agg(key, j):
        v = [r[key][j] for r in all_res]
        t = torch.tensor(v)
        return float(t.mean()), float(t.min()), float(t.max())

    print("\n=== 5 个切分种子汇总(mean [min, max]) ===")
    for key, name in [("mlp", "MLP(hidden)"), ("lin", "Linear(lead/base)"), ("mean", "GlobalMean")]:
        sp = agg(key, 0)
        ms = agg(key, 1)
        sp_s = "-" if sp[0] != sp[0] else f"{sp[0]:.3f} [{sp[1]:.3f}, {sp[2]:.3f}]"
        print(f"{name:>18}: Spearman {sp_s} | MSE {ms[0]:.3f} [{ms[1]:.3f}, {ms[2]:.3f}]")


if __name__ == "__main__":
    main()
