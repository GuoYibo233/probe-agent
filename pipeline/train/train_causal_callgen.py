"""因果调用生成训练(新流水线 cgen 格):Qwen3-0.6B-Base 微调成"看题干写整条调用"。

与 ctool(train_causal_tool.py)的分工:ctool 只出工具种类,cgen 直接把
工具名 + 全部参数一次写出来(`apis.spotify.login(username=x, password=y)`)。

- 输入: <data_out>/{train,val}.jsonl,每行取 text / label_call / w 三个字段;
  一条样本 = 一条训练实例
- 拼串: 输入串 = text + CALL_SEP("\\n[CALL] "),目标串 = label_call + eos
- 防左截吃目标: 先 tokenize 目标得 tgt_ids(不截断),超 MAX_TGT_TOK 的实例整条
  丢弃并计数;再按 max_length = --max-len - len(tgt_ids) 左截输入串,拼接后
  labels 把 prompt 段掩成 -100(批内右 padding,pad 位同样 -100)
- 损失: 逐实例目标段 mean CE(ce_i),批损失 = Σ(w_i·ce_i)/Σw_i
- 评估: 每轮 val 全量加权 masked-CE(val_ce,选 best 的唯一依据,越低越好)+
  定种子抽 GEN_N 条 greedy 生成报 val_exact_call(只进日志,不选 best)
- 产物: <out>/best/(HF 权重 + tokenizer + meta.json)+ train_log.jsonl

用法:
  # 冒烟(500 训练实例/200 评估实例/1 epoch)
  cprobe-env/bin/python pipeline/train/train_causal_callgen.py \
    --data pipeline/data/aw_official_v1/q35 --out pipeline/runs/c1_q35_cgen --smoke
  # 全量
  cprobe-env/bin/python pipeline/train/train_causal_callgen.py \
    --data pipeline/data/aw_official_v1/q35 --out pipeline/runs/c1_q35_cgen
"""

import argparse
import json
import math
import random
import time
from pathlib import Path

import torch
import torch.nn.functional as F
import transformers
from torch.utils.data import DataLoader, Dataset
from transformers import (AutoModelForCausalLM, AutoTokenizer,
                          get_linear_schedule_with_warmup)

QWEN = "/net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-0.6B-Base"
SEED = 20260729
CALL_SEP = "\n[CALL] "
MAX_TGT_TOK = 160          # 目标串 token 上限,超了整条实例丢弃
MAX_GEN_TOK = 96           # 评估生成的 max_new_tokens
GEN_N = 200                # 每轮抽多少条做 greedy 生成


# ---------------------------------------------------------------- 数据

class CallDS(Dataset):
    """一条样本一条实例;构造时先 tokenize 目标串,过长的整条丢弃并计数。"""

    def __init__(self, path, tok, limit=0, max_tgt=MAX_TGT_TOK):
        self.rows, self.dropped = [], 0
        eos = tok.eos_token_id
        for line in open(path):
            r = json.loads(line)
            tgt = tok(r["label_call"], add_special_tokens=False)["input_ids"]
            tgt = tgt + [eos]
            if len(tgt) > max_tgt:
                self.dropped += 1
                continue
            self.rows.append((r["text"], tgt, float(r["w"]), r["label_call"]))
        if limit:
            rng = random.Random(SEED)
            rng.shuffle(self.rows)
            self.rows = self.rows[:limit]

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        return self.rows[i]


def collate(batch, tok, max_len):
    """左截输入 + 右 padding;labels 掩掉 prompt 段与 pad 位。"""
    ids, labs, ws = [], [], []
    for text, tgt, w, _call in batch:
        keep = max(max_len - len(tgt), 1)
        prompt = tok(text + CALL_SEP, truncation=True, max_length=keep,
                     add_special_tokens=False)["input_ids"]
        ids.append(prompt + tgt)
        labs.append([-100] * len(prompt) + tgt)
        ws.append(w)
    n, L = len(ids), max(len(x) for x in ids)
    pad = tok.pad_token_id
    input_ids = torch.full((n, L), pad, dtype=torch.long)
    attn = torch.zeros((n, L), dtype=torch.long)
    labels = torch.full((n, L), -100, dtype=torch.long)
    for i, (x, y) in enumerate(zip(ids, labs)):
        input_ids[i, :len(x)] = torch.tensor(x, dtype=torch.long)
        attn[i, :len(x)] = 1
        labels[i, :len(y)] = torch.tensor(y, dtype=torch.long)
    return (dict(input_ids=input_ids, attention_mask=attn), labels,
            torch.tensor(ws, dtype=torch.float))


# ---------------------------------------------------------------- 模型

def build(dev):
    """tokenizer 构造照抄 train_causal_probe.build():pad=eos / 左截 / 右 pad。"""
    path = QWEN
    tok = AutoTokenizer.from_pretrained(path)
    if tok.pad_token_id is None:                      # 照抄 check_causal_candidates
        tok.pad_token = tok.eos_token
    tok.truncation_side = "left"                      # 保思考尾巴
    tok.padding_side = "right"                        # 目标段都在真实 token 上
    torch.manual_seed(SEED)
    model = AutoModelForCausalLM.from_pretrained(path, dtype=torch.float32)
    if model.config.get_text_config().pad_token_id is None:
        model.config.get_text_config().pad_token_id = tok.pad_token_id
    return tok, model.to(dev), path


def inst_ce(model, enc, labels, dev):
    """逐实例目标段 mean CE。返回 [B] 的 float32 张量。"""
    out = model(input_ids=enc["input_ids"], attention_mask=enc["attention_mask"],
                use_cache=False)
    lg = out.logits[:, :-1]                           # 预测下一 token
    tg = labels[:, 1:].to(dev)
    m = tg != -100
    ce = F.cross_entropy(lg[m].float(), tg[m], reduction="none")  # 只取目标位
    b = tg.size(0)
    inst = torch.arange(b, device=dev).unsqueeze(1).expand_as(tg)[m]
    ssum = torch.zeros(b, device=dev, dtype=torch.float32)
    ssum = ssum.index_add(0, inst, ce)
    return ssum / m.sum(1).clamp(min=1).float()


# ---------------------------------------------------------------- 评估

@torch.no_grad()
def eval_ce(model, loader, dev, amp):
    """val 全量加权 masked-CE(与训练损失同口径)。"""
    model.eval()
    s = w_tot = 0.0
    for enc, labels, w in loader:
        enc = {k: v.to(dev) for k, v in enc.items()}
        with torch.autocast("cuda", dtype=torch.bfloat16, enabled=amp):
            ce = inst_ce(model, enc, labels, dev)
        wd = w.to(dev)
        s += (ce.float() * wd).sum().item()
        w_tot += wd.sum().item()
    model.train()
    return s / max(w_tot, 1e-9)


@torch.no_grad()
def eval_gen(model, tok, rows, dev, amp, max_len, bs):
    """定种子抽样的 greedy 生成:整串命中率(遇 \\n 或 eos 停)。"""
    model.eval()
    prev_side, prev_cache = tok.padding_side, model.config.use_cache
    tok.padding_side = "left"                         # 生成必须左 padding
    model.config.use_cache = True
    hit = 0
    for i in range(0, len(rows), bs):
        chunk = rows[i:i + bs]
        enc = tok([r[0] + CALL_SEP for r in chunk], truncation=True,
                  max_length=max(max_len - MAX_GEN_TOK, 1), padding=True,
                  add_special_tokens=False, return_tensors="pt").to(dev)
        with torch.autocast("cuda", dtype=torch.bfloat16, enabled=amp):
            out = model.generate(**enc, do_sample=False,
                                 max_new_tokens=MAX_GEN_TOK,
                                 eos_token_id=tok.eos_token_id,
                                 pad_token_id=tok.pad_token_id)
        gen = tok.batch_decode(out[:, enc["input_ids"].shape[1]:],
                               skip_special_tokens=True)
        for g, r in zip(gen, chunk):
            hit += (g.split("\n")[0].strip() == r[3])
    tok.padding_side, model.config.use_cache = prev_side, prev_cache
    model.train()
    return hit / max(len(rows), 1)


# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default="appworld",
                    choices=["tales", "appworld", "bfcl"],
                    help="仅作日志标签(数据路径已由 --data 直接给定)")
    ap.add_argument("--data", required=True,
                    help="数据目录 <data_out>(含 train/val.jsonl)")
    ap.add_argument("--out", required=True, help="产物目录(必填,防覆盖旧件)")
    ap.add_argument("--max-len", type=int, default=4096)
    ap.add_argument("--bs", type=int, default=4)
    ap.add_argument("--accum", type=int, default=8)
    ap.add_argument("--lr", type=float, default=1e-5)
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--smoke", action="store_true",
                    help="500 训练实例/200 评估实例/1 epoch,验证管线")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--grad-ckpt", action="store_true")
    ap.add_argument("--gen-bs", type=int, default=8, help="生成评估的批大小")
    ap.add_argument("--max-inst", type=int, default=0,
                    help="调试用:再限实例数(0=不限)")
    args = ap.parse_args()

    torch.manual_seed(SEED)
    random.seed(SEED)
    data = Path(args.data)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    dev = args.device
    amp = dev.startswith("cuda")

    tok, model, path = build(dev)

    lim_tr, lim_ev = (500, 200) if args.smoke else (0, 0)
    if args.max_inst:
        lim_tr = min(lim_tr or args.max_inst, args.max_inst)
        lim_ev = min(lim_ev or args.max_inst, args.max_inst)
    epochs = 1 if args.smoke else args.epochs
    tr = CallDS(data / "train.jsonl", tok, lim_tr)
    ev = CallDS(data / "val.jsonl", tok, lim_ev)
    mk = lambda ds, sh: DataLoader(
        ds, batch_size=args.bs, shuffle=sh, num_workers=2,
        collate_fn=lambda b: collate(b, tok, args.max_len))
    tr_dl, ev_dl = mk(tr, True), mk(ev, False)
    gen_rows = list(ev.rows)
    random.Random(SEED).shuffle(gen_rows)
    gen_rows = gen_rows[:GEN_N]

    if args.grad_ckpt:
        model.gradient_checkpointing_enable()
        model.config.use_cache = False
    model.train()

    steps = math.ceil(len(tr_dl) / args.accum) * epochs
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    sch = get_linear_schedule_with_warmup(opt, int(steps * 0.05), steps)

    logf = open(out / "train_log.jsonl", "a")

    def log(**kw):
        kw["t"] = round(time.time(), 1)
        logf.write(json.dumps(kw) + "\n")
        logf.flush()
        print(kw, flush=True)

    log(event="start", base_path=path, env=args.env, n_train=len(tr),
        n_eval=len(ev), n_gen=len(gen_rows), steps=steps, smoke=args.smoke,
        max_len=args.max_len, max_tgt_tok=MAX_TGT_TOK, seed=SEED,
        dropped_train=tr.dropped, dropped_eval=ev.dropped, device=dev)

    best = float("inf")
    gstep = 0
    for ep in range(epochs):
        t0, run = time.time(), 0.0
        for i, (enc, labels, w) in enumerate(tr_dl):
            enc = {k: v.to(dev) for k, v in enc.items()}
            with torch.autocast("cuda", dtype=torch.bfloat16, enabled=amp):
                ce = inst_ce(model, enc, labels, dev)
            wd = w.to(dev)
            loss = (ce.float() * wd).sum() / wd.sum()
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
                        ips=round((i + 1) * args.bs / (time.time() - t0), 2))
                    run = 0.0
        vce = eval_ce(model, ev_dl, dev, amp)
        vex = eval_gen(model, tok, gen_rows, dev, amp, args.max_len,
                       args.gen_bs)
        log(event="eval", ep=ep, val_ce=round(vce, 4),
            val_exact_call=round(vex, 4))
        if vce < best:
            best = vce
            (out / "best").mkdir(parents=True, exist_ok=True)
            model.save_pretrained(out / "best")
            tok.save_pretrained(out / "best")
            (out / "best" / "meta.json").write_text(json.dumps(dict(
                base_path=path, data=str(data), max_len=args.max_len,
                seed=SEED, epoch=ep, call_sep=CALL_SEP,
                transformers=transformers.__version__), indent=1))
            log(event="save_best", ep=ep, val_ce=round(best, 4))
    log(event="done", best_val_ce=round(best, 4))


if __name__ == "__main__":
    main()
