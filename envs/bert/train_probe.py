"""ModernBERT 工具种类头训练(一环境一模型,C2-2t v1)。

- 输入: bert_data/v2/<env>/{train,calA}.jsonl + tool_vocab.json
- 损失: 加权交叉熵,权重 = 样本自带 w(=1/m_i,事件内等权)
- 截断: tokenizer 左截 4096(保思考尾巴)
- 评估: 每轮在 calA 上报 加权样本 acc + 事件末边界 acc(full-thinking)
- 产物: <out>/best/(最优权重+label_map.json+train_log.jsonl)

用法(smoke):
  python train_probe.py --env tales --smoke
全量:
  python train_probe.py --env tales
"""

import argparse
import json
import math
import random
import time
from pathlib import Path

import torch
from torch.utils.data import DataLoader, Dataset
from transformers import (AutoModelForSequenceClassification, AutoTokenizer,
                          get_linear_schedule_with_warmup)

BASE = Path("/home/y-guo/reproduce/new1/envs")
MODEL = "/net/tokyo100-10g/data/str01_01/y-guo/models/ModernBERT-base"
SEED = 20260729


class JsonlDS(Dataset):
    def __init__(self, path, label2id, limit=0):
        self.rows = []
        for line in open(path):
            r = json.loads(line)
            if r["label"] in label2id:
                self.rows.append(r)
        if limit:
            rng = random.Random(SEED)
            rng.shuffle(self.rows)
            self.rows = self.rows[:limit]
        self.label2id = label2id

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        r = self.rows[i]
        return (r["text"], self.label2id[r["label"]], r["w"],
                r["sent_idx"] == r["n_sents"] - 1)


def collate(batch, tok, max_len):
    texts, labels, ws, lasts = zip(*batch)
    enc = tok(list(texts), truncation=True, max_length=max_len,
              padding=True, return_tensors="pt")
    return (enc, torch.tensor(labels), torch.tensor(ws, dtype=torch.float),
            torch.tensor(lasts))


@torch.no_grad()
def evaluate(model, loader, dev):
    model.eval()
    wc = ws = lc = ln = 0.0
    for enc, y, w, last in loader:
        enc = {k: v.to(dev) for k, v in enc.items()}
        pred = model(**enc).logits.argmax(-1).cpu()
        ok = (pred == y).float()
        wc += (ok * w).sum().item()
        ws += w.sum().item()
        lc += ok[last].sum().item()
        ln += last.sum().item()
    model.train()
    return wc / max(ws, 1e-9), lc / max(ln, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", required=True,
                    choices=["tales", "appworld", "bfcl"])
    ap.add_argument("--data", default=str(BASE / "bert_data" / "v2"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--max-len", type=int, default=4096)
    ap.add_argument("--bs", type=int, default=8)
    ap.add_argument("--accum", type=int, default=4)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--smoke", action="store_true",
                    help="500 训练样本/200 评估样本/1 epoch,验证管线")
    args = ap.parse_args()

    torch.manual_seed(SEED)
    random.seed(SEED)
    data = Path(args.data) / args.env
    out = Path(args.out or BASE / "bert_runs" / f"{args.env}_v2")
    out.mkdir(parents=True, exist_ok=True)
    dev = "cuda"

    vocab = json.loads((data / "tool_vocab.json").read_text())
    label2id = {k: i for i, k in enumerate(vocab)}
    tok = AutoTokenizer.from_pretrained(MODEL)
    tok.truncation_side = "left"          # 保思考尾巴
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL, num_labels=len(label2id), torch_dtype=torch.bfloat16,
        attn_implementation="sdpa")
    model.config.reference_compile = False
    model.to(dev).train()

    lim_tr, lim_ev = (500, 200) if args.smoke else (0, 0)
    epochs = 1 if args.smoke else args.epochs
    tr = JsonlDS(data / "train.jsonl", label2id, lim_tr)
    ev = JsonlDS(data / "calA.jsonl", label2id, lim_ev)
    mk = lambda ds, sh: DataLoader(
        ds, batch_size=args.bs, shuffle=sh, num_workers=2,
        collate_fn=lambda b: collate(b, tok, args.max_len))
    tr_dl, ev_dl = mk(tr, True), mk(ev, False)

    steps = math.ceil(len(tr_dl) / args.accum) * epochs
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    sch = get_linear_schedule_with_warmup(opt, int(steps * 0.05), steps)
    lossf = torch.nn.CrossEntropyLoss(reduction="none")

    logf = open(out / "train_log.jsonl", "a")

    def log(**kw):
        kw["t"] = round(time.time(), 1)
        logf.write(json.dumps(kw) + "\n")
        logf.flush()
        print(kw, flush=True)

    log(event="start", env=args.env, n_train=len(tr), n_eval=len(ev),
        n_labels=len(label2id), steps=steps, smoke=args.smoke)

    best = -1.0
    gstep = 0
    for ep in range(epochs):
        t0, run = time.time(), 0.0
        for i, (enc, y, w, _last) in enumerate(tr_dl):
            enc = {k: v.to(dev) for k, v in enc.items()}
            loss = (lossf(model(**enc).logits, y.to(dev))
                    * w.to(dev)).sum() / w.sum().to(dev)
            (loss / args.accum).backward()
            run += loss.item()
            if (i + 1) % args.accum == 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()
                sch.step()
                opt.zero_grad()
                gstep += 1
                if gstep % 50 == 0:
                    log(event="step", ep=ep, gstep=gstep,
                        loss=round(run / (50 * args.accum), 4),
                        ips=round((i + 1) * args.bs / (time.time() - t0), 1))
                    run = 0.0
        wacc, lacc = evaluate(model, ev_dl, dev)
        log(event="eval", ep=ep, calA_weighted_acc=round(wacc, 4),
            calA_lastbound_acc=round(lacc, 4))
        if wacc > best:
            best = wacc
            model.save_pretrained(out / "best")
            tok.save_pretrained(out / "best")
            (out / "best" / "label_map.json").write_text(
                json.dumps(label2id, ensure_ascii=False))
            log(event="save_best", ep=ep, acc=round(best, 4))
    log(event="done", best_calA_weighted_acc=round(best, 4))


if __name__ == "__main__":
    main()
