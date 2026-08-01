"""ModernBERT 工具种类头训练(新流水线 mtool 格,一模型一 run)。

- 输入: <data_out>/{train,val}.jsonl + tool_vocab.json
- 损失: 加权交叉熵,权重 = 样本自带 w(=1/m_i,事件内等权)
- 截断: tokenizer 左截 4096(保思考尾巴)
- 评估: 每轮在 val 上报 加权样本 acc + 事件末边界 acc(full-thinking);
  日志字段名沿用 calA_* 旧名(下游脚本按名读)
- 产物: <out>/best/(最优权重+tokenizer+label_map.json)+ train_log.jsonl

用法(smoke):
  mbert-env/bin/python pipeline/train/train_mbert_tool.py \
    --data pipeline/data/aw_official_v1/q35 --out pipeline/runs/c1_q35_mtool --smoke
全量:
  mbert-env/bin/python pipeline/train/train_mbert_tool.py \
    --data pipeline/data/aw_official_v1/q35 --out pipeline/runs/c1_q35_mtool
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

import readonly_map
from input_modes import apply_mode

MODEL = "/net/tokyo100-10g/data/str01_01/y-guo/models/ModernBERT-base"
SEED = 20260729


class JsonlDS(Dataset):
    def __init__(self, path, label2id, limit=0, mode="full", ro=None):
        if ro is None:
            rows = [r for r in map(json.loads, open(path))
                    if r["label"] in label2id]
        else:                                  # --readonly-env:先清点后折叠
            rows = list(map(json.loads, open(path)))
            ro["info"] = readonly_map.audit(
                [r["label"] for r in rows], ro["table"], where=ro["where"])
            for r in rows:
                r["label"] = readonly_map.collapse(r["label"], ro["set"])
            bad = sorted({r["label"] for r in rows} - set(label2id))
            if bad:
                raise SystemExit(
                    f"readonly: {ro['where']} 折叠后仍有 {len(bad)} 个标签不在"
                    f"折叠词表里(如 {bad[:5]})——tool_vocab.json 与数据对不上,硬停。")
            rows = [r for r in rows if r["label"] in label2id]
        self.rows = apply_mode(rows, mode)
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
        with torch.autocast("cuda", dtype=torch.bfloat16):
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
    ap.add_argument("--env", default="appworld",
                    choices=["tales", "appworld", "bfcl", "alfworld"],
                    help="仅作日志标签(数据路径已由 --data 直接给定)")
    ap.add_argument("--data", required=True,
                    help="数据目录 <data_out>(含 train/val.jsonl 与 tool_vocab.json)")
    ap.add_argument("--out", required=True, help="产物目录(必填,防覆盖旧件)")
    ap.add_argument("--max-len", type=int, default=4096)
    ap.add_argument("--bs", type=int, default=8)
    ap.add_argument("--accum", type=int, default=4)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--smoke", action="store_true",
                    help="500 训练样本/200 评估样本/1 epoch,验证管线")
    ap.add_argument("--input-mode", default="full",
                    choices=["full", "no-think", "no-hist"],
                    help="T5 消融:切 [THINKING] 或 [HISTORY] 段")
    ap.add_argument("--readonly-env", default=None,
                    choices=list(readonly_map.READONLY_ENVS),
                    help="只读工具模式:标签折叠成 该环境的只读工具 + "
                         f"{readonly_map.NON_READONLY} 弃权类(默认关=旧口径)")
    args = ap.parse_args()

    torch.manual_seed(SEED)
    random.seed(SEED)
    data = Path(args.data)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    dev = "cuda"

    vocab = json.loads((data / "tool_vocab.json").read_text())
    ro_tr = ro_ev = None
    if args.readonly_env:                      # 词表 = 原序只读工具 + 末尾哨兵
        ro_set = readonly_map.load_readonly_set(args.readonly_env)
        ro_table = readonly_map.load_table(args.readonly_env)
        vocab = [t for t in vocab if t in ro_set] + [readonly_map.NON_READONLY]
        ro_tr = dict(set=ro_set, table=ro_table, where="mtool/train")
        ro_ev = dict(set=ro_set, table=ro_table, where="mtool/val")
    label2id = {k: i for i, k in enumerate(vocab)}
    tok = AutoTokenizer.from_pretrained(MODEL)
    tok.truncation_side = "left"          # 保思考尾巴
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL, num_labels=len(label2id),
        attn_implementation="sdpa")
    model.config.reference_compile = False
    model.to(dev).train()

    lim_tr, lim_ev = (500, 200) if args.smoke else (0, 0)
    epochs = 1 if args.smoke else args.epochs
    tr = JsonlDS(data / "train.jsonl", label2id, lim_tr, args.input_mode, ro_tr)
    ev = JsonlDS(data / "val.jsonl", label2id, lim_ev, args.input_mode, ro_ev)
    if args.readonly_env:
        (out / "READONLY.json").write_text(json.dumps(dict(
            readonly_env=args.readonly_env,
            table=str(readonly_map.table_path(args.readonly_env)),
            train=ro_tr["info"], val=ro_ev["info"],
            vocab_size_collapsed=len(label2id)), ensure_ascii=False, indent=1))
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
        n_labels=len(label2id), steps=steps, smoke=args.smoke,
        input_mode=args.input_mode, readonly_env=args.readonly_env)

    best = -1.0
    gstep = 0
    for ep in range(epochs):
        t0, run = time.time(), 0.0
        for i, (enc, y, w, _last) in enumerate(tr_dl):
            enc = {k: v.to(dev) for k, v in enc.items()}
            with torch.autocast("cuda", dtype=torch.bfloat16):
                logits = model(**enc).logits
            loss = (lossf(logits.float(), y.to(dev))
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
