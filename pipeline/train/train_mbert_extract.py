"""抽取头训练(新流水线 mext 格):ModernBERT 底座 + 起止指针头 + 可答头。

- 输入: <data_out>/{train,val}.jsonl(文本) 与 <data_out>/params/同名文件
  (参数区间标签),按 event+sent_idx 连接
- 实例 = (样本 × 参数);查询拼在**末尾**:text + "\\n[FIND] " + 工具名.参数名
  (tokenizer 左截 4096,保思考尾巴与查询;字符区间不受后缀影响)
- 字符区间 -> token 区间取**最小覆盖 token 跨度**(offset_mapping);
  被左截切掉的 span 训练时按"抽不到"计并计数
- 损失 = 可答 BCE + found 实例的 start/end CE,均按样本权重 w 加权
- 判对口径两套(BPE 会把前导空格/引号并进 token,严格逐字会低估):
    宽松(主口径) 预测字符区间覆盖真值且多出来的字符只有空白/标点
    严格(对照)   预测区间解码文本逐字 == 真值
- 每轮 val 报: 可答准确率 / span 命中(宽松·严格) / 参数级总正确率,按 w 加权;
  日志与 meta 字段名沿用 calA_* 旧名(下游脚本按名读)
- 产物: <out>/best/(model.pt + tokenizer + meta.json)+ train_log.jsonl

用法(smoke):
  mbert-env/bin/python pipeline/train/train_mbert_extract.py \
    --data pipeline/data/aw_official_v1/q35 --out pipeline/runs/c1_q35_mext --smoke
"""

import argparse
import contextlib
import json
import math
import random
import time
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset
from transformers import (AutoTokenizer, ModernBertModel,
                          get_linear_schedule_with_warmup)

MODEL = "/net/tokyo100-10g/data/str01_01/y-guo/models/ModernBERT-base"
SEED = 20260729
FIND = "\n[FIND] "
MAX_SPAN_TOK = 64          # 解码时起止最大跨度


class Extractor(nn.Module):
    def __init__(self, base_path=MODEL):
        super().__init__()
        self.base = ModernBertModel.from_pretrained(
            base_path, attn_implementation="sdpa")
        self.base.config.reference_compile = False
        h = self.base.config.hidden_size
        self.span = nn.Linear(h, 2)
        self.ans = nn.Linear(h, 1)

    def forward(self, enc, last_idx):
        hs = self.base(**enc).last_hidden_state
        s, e = self.span(hs).unbind(-1)
        a = self.ans(hs[torch.arange(hs.size(0), device=hs.device),
                        last_idx]).squeeze(-1)
        return s, e, a


# ---------- 数据:样本文本 × params 区间 ----------

def join_rows(data, params, split, limit=0):
    """流式并归(两文件同序,params 是样本堆的子序列)-> (texts, instances)。"""
    texts, inst = [], []
    fp = open(params / f"{split}.jsonl")
    pr = fp.readline()
    for line in open(data / f"{split}.jsonl"):
        if not pr:
            break
        r = json.loads(line)
        p = json.loads(pr)
        if p["event"] != r["event"] or p["sent_idx"] != r["sent_idx"]:
            continue
        pr = fp.readline()
        if not p["params"]:
            continue
        ti = len(texts)
        texts.append(r["text"])
        for q in p["params"]:
            inst.append((ti, q["key"], q["value"], q["start"], q["end"],
                         q["found"], p["w"]))
    fp.close()
    if limit:
        rng = random.Random(SEED)
        rng.shuffle(inst)
        inst = inst[:limit]
    return texts, inst


class InstDS(Dataset):
    def __init__(self, texts, inst):
        self.texts, self.inst = texts, inst

    def __len__(self):
        return len(self.inst)

    def __getitem__(self, i):
        ti, key, val, s, e, found, w = self.inst[i]
        return self.texts[ti] + FIND + key, val, s, e, found, w


def char2tok(offs, start, end):
    """字符区间 -> 最小覆盖 token 跨度;越界/被截返回 (-1,-1)。"""
    st = en = -1
    for i, (a, b) in enumerate(offs):
        if b <= a:                       # 特殊 token / padding
            continue
        if a <= start < b:
            st = i
        if a < end <= b:
            en = i
    return st, en


def span_ok(full, c0, c1, gs, ge):
    """宽松判对:预测字符区间覆盖真值,且多出的字符只有空白/标点。"""
    if c0 < 0 or c0 > gs or c1 < ge:
        return False
    pad = full[c0:gs] + full[ge:c1]
    return not any(ch.isalnum() or ch == "_" for ch in pad)


def collate(batch, tok, max_len):
    strs, vals, gs, ge, founds, ws = zip(*batch)
    enc = tok(list(strs), truncation=True, max_length=max_len, padding=True,
              return_offsets_mapping=True, return_tensors="pt")
    offs = enc.pop("offset_mapping")
    valid = (offs[:, :, 1] > offs[:, :, 0]) & (enc["attention_mask"] > 0)
    last = valid.float().cumsum(1).argmax(1)          # 末个真 token
    n = len(batch)
    st = torch.zeros(n, dtype=torch.long)
    en = torch.zeros(n, dtype=torch.long)
    ok = torch.zeros(n, dtype=torch.bool)             # 可答(且未被左截切掉)
    cut = 0
    for i in range(n):
        if not founds[i]:
            continue
        a, b = char2tok(offs[i].tolist(), gs[i], ge[i])
        if a < 0 or b < 0 or b < a:
            cut += 1
            continue
        st[i], en[i], ok[i] = a, b, True
    return dict(enc=enc, valid=valid, last=last, st=st, en=en, ok=ok,
                w=torch.tensor(ws, dtype=torch.float), strs=list(strs),
                vals=list(vals), gs=list(gs), ge=list(ge),
                found=list(founds), offs=offs, cut=cut)


def decode(s_lg, e_lg, valid, offs):
    """向量化解码:返回每条的预测字符区间 (c0, c1)。"""
    neg = torch.finfo(s_lg.dtype).min
    s_lg = s_lg.masked_fill(~valid, neg)
    e_lg = e_lg.masked_fill(~valid, neg)
    w = min(MAX_SPAN_TOK, e_lg.size(1))
    pad = F.pad(e_lg, (0, w - 1), value=neg)
    win = pad.unfold(1, w, 1)                          # (B, L, w)
    wmax, warg = win.max(-1)
    bi = (s_lg + wmax).argmax(1)
    r = torch.arange(s_lg.size(0))
    bj = bi + warg[r, bi]
    return [(int(offs[i, bi[i], 0]), int(offs[i, bj[i], 1]))
            for i in range(s_lg.size(0))]


@torch.no_grad()
def evaluate(model, loader, dev, amp):
    model.eval()
    a_hit = sp_l = sp_s = tot_ok = w_tot = w_ft = 0.0
    for b in loader:
        enc = {k: v.to(dev) for k, v in b["enc"].items()}
        with amp():
            s_lg, e_lg, a_lg = model(enc, b["last"].to(dev))
        s_lg, e_lg = s_lg.float().cpu(), e_lg.float().cpu()
        ansp = (a_lg.float().cpu() > 0)
        spans = decode(s_lg, e_lg, b["valid"], b["offs"])
        for i in range(len(b["strs"])):
            wi = float(b["w"][i])
            pa = bool(ansp[i])
            a_hit += wi * (pa == bool(b["found"][i]))
            w_tot += wi
            if b["found"][i]:
                c0, c1 = spans[i]
                loose = pa and span_ok(b["strs"][i], c0, c1,
                                       b["gs"][i], b["ge"][i])
                strict = pa and b["strs"][i][c0:c1] == b["vals"][i]
                sp_l += wi * loose
                sp_s += wi * strict
                w_ft += wi
                tot_ok += wi * loose
            else:
                tot_ok += wi * (not pa)
    model.train()
    return (a_hit / max(w_tot, 1e-9), sp_l / max(w_ft, 1e-9),
            sp_s / max(w_ft, 1e-9), tot_ok / max(w_tot, 1e-9))


def load_extractor(run, device="cuda"):
    """eval_mbert_call 复用:返回 (model, tok, meta)。"""
    run = Path(run)
    meta = json.loads((run / "best" / "meta.json").read_text())
    tok = AutoTokenizer.from_pretrained(run / "best")
    tok.truncation_side = "left"
    model = Extractor(meta["base"])
    model.load_state_dict(torch.load(run / "best" / "model.pt",
                                     map_location="cpu"))
    return model.to(device).eval(), tok, meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default="appworld",
                    choices=["tales", "appworld", "bfcl"],
                    help="仅作日志标签(数据路径已由 --data 直接给定)")
    ap.add_argument("--data", required=True,
                    help="数据目录 <data_out>(含 train/val.jsonl)")
    ap.add_argument("--params", default=None,
                    help="参数区间标签目录(默认 <data>/params)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-len", type=int, default=4096)
    ap.add_argument("--bs", type=int, default=8)
    ap.add_argument("--accum", type=int, default=4)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--smoke", action="store_true",
                    help="500 训练实例/200 评估实例/1 epoch,验证管线")
    ap.add_argument("--max-inst", type=int, default=0,
                    help="再压实例数(CPU 调试用,0=不限)")
    ap.add_argument("--device", default="cuda")
    args = ap.parse_args()

    torch.manual_seed(SEED)
    random.seed(SEED)
    data = Path(args.data)
    params = Path(args.params) if args.params else data / "params"
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    dev = args.device
    amp = ((lambda: torch.autocast("cuda", dtype=torch.bfloat16))
           if dev.startswith("cuda") else contextlib.nullcontext)

    tok = AutoTokenizer.from_pretrained(MODEL)
    tok.truncation_side = "left"
    model = Extractor().to(dev)
    model.train()

    lim_tr, lim_ev = (500, 200) if args.smoke else (0, 0)
    if args.max_inst:
        lim_tr = min(lim_tr or args.max_inst, args.max_inst)
        lim_ev = min(lim_ev or args.max_inst, args.max_inst)
    epochs = 1 if args.smoke else args.epochs
    tr = InstDS(*join_rows(data, params, "train", lim_tr))
    ev = InstDS(*join_rows(data, params, "val", lim_ev))
    mk = lambda ds, sh: DataLoader(
        ds, batch_size=args.bs, shuffle=sh, num_workers=2,
        collate_fn=lambda b: collate(b, tok, args.max_len))
    tr_dl, ev_dl = mk(tr, True), mk(ev, False)

    steps = math.ceil(len(tr_dl) / args.accum) * epochs
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    sch = get_linear_schedule_with_warmup(opt, int(steps * 0.05), steps)
    ce = nn.CrossEntropyLoss(reduction="none")
    bce = nn.BCEWithLogitsLoss(reduction="none")

    logf = open(out / "train_log.jsonl", "a")

    def log(**kw):
        kw["t"] = round(time.time(), 1)
        logf.write(json.dumps(kw) + "\n")
        logf.flush()
        print(kw, flush=True)

    log(event="start", env=args.env, n_train=len(tr), n_eval=len(ev),
        steps=steps, smoke=args.smoke, max_len=args.max_len, device=dev)

    best, gstep, cutsum = -1.0, 0, 0
    neg = torch.finfo(torch.float32).min
    for ep in range(epochs):
        t0, run = time.time(), 0.0
        for i, b in enumerate(tr_dl):
            cutsum += b["cut"]
            enc = {k: v.to(dev) for k, v in b["enc"].items()}
            with amp():
                s_lg, e_lg, a_lg = model(enc, b["last"].to(dev))
            m = b["valid"].to(dev)
            s_lg = s_lg.float().masked_fill(~m, neg)
            e_lg = e_lg.float().masked_fill(~m, neg)
            wd, okd = b["w"].to(dev), b["ok"].to(dev)
            la = (bce(a_lg.float(), okd.float()) * wd).sum() / wd.sum()
            if okd.any():
                wf = wd[okd]
                ls = ((ce(s_lg[okd], b["st"].to(dev)[okd])
                       + ce(e_lg[okd], b["en"].to(dev)[okd]))
                      * wf).sum() / wf.sum()
            else:
                ls = torch.zeros((), device=dev)
            loss = la + ls
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
        aacc, sl, ss, tacc = evaluate(model, ev_dl, dev, amp)
        log(event="eval", ep=ep, calA_ans_acc=round(aacc, 4),
            calA_span_loose=round(sl, 4), calA_span_strict=round(ss, 4),
            calA_param_acc=round(tacc, 4), truncated_spans=cutsum)
        if tacc > best:
            best = tacc
            (out / "best").mkdir(exist_ok=True)
            torch.save(model.state_dict(), out / "best" / "model.pt")
            tok.save_pretrained(out / "best")
            (out / "best" / "meta.json").write_text(json.dumps(
                dict(env=args.env, base=MODEL, max_len=args.max_len,
                     find=FIND, max_span_tok=MAX_SPAN_TOK, seed=SEED,
                     calA_param_acc=round(best, 4)), ensure_ascii=False))
            log(event="save_best", ep=ep, acc=round(best, 4))
    log(event="done", best_calA_param_acc=round(best, 4),
        truncated_spans=cutsum)


if __name__ == "__main__":
    main()
