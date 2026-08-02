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

开火头(`--fire-head`,必须与 --readonly-env 同传;默认不传 = 行为与旧版一致):
- 同一个 encoder 上再挂一个样本级二分类头([CLS] 位隐状态 -> Linear -> 1),
  学"此刻该不该发射投机"。开火标签
  ready = 标签在该环境只读集合里 且 该样本所有参数 found=true
  (零参数事件 found 条件空真;params 文件里 join 不到的样本记 not-ready 并计数)
- 开火头走**独立的样本级数据流**:输入是纯 text(不带 [FIND] 后缀,与线上开火时
  能拿到的输入一致),一条样本一条实例,所以不存在"同一样本按参数数重复计权";
  非只读样本不再整条丢弃,而是回到这条流里当负例(它们不产 span 实例,
  因而对原任务零梯度)
- 损失 = 原 span/可答损失 + λ·开火 BCE(λ=1),两条流各自成批、各自按 w 加权
- best 的选择指标不变(val 参数正确率,只读样本上算);开火头权重随 model.pt
  一起存(裸 state_dict 加两个键),meta.json 加 "fire_head": true;
  val 的开火 acc@0.5 与正负例数进 train_log 的 eval 事件

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
import transformers
# 双环境铁律(run.py PY 表):mbert 线钉 transformers==4.57.6,跑错解释器
# 的行为漂移是静默的,这里直接拒绝
if transformers.__version__ != "4.57.6":
    raise SystemExit(f"mbert 线钉 transformers==4.57.6,当前 "
                     f"{transformers.__version__}——解释器用错了?"
                     "一律从 run.py 的任务进(train-mtool/train-mext)。")
from transformers import (AutoTokenizer, ModernBertModel,
                          get_linear_schedule_with_warmup)

import readonly_map


MODEL = "/net/tokyo100-10g/data/str01_01/y-guo/models/ModernBERT-base"
SEED = 20260729
FIND = "\n[FIND] "
MAX_SPAN_TOK = 64          # 解码时起止最大跨度


class Extractor(nn.Module):
    def __init__(self, base_path=MODEL, fire=False):
        super().__init__()
        self.base = ModernBertModel.from_pretrained(
            base_path, attn_implementation="sdpa")
        self.base.config.reference_compile = False
        h = self.base.config.hidden_size
        self.span = nn.Linear(h, 2)
        self.ans = nn.Linear(h, 1)
        # 开火头只在 --fire-head 下建,且**建在 span/ans 之后**:
        # 这样默认关时随机数流与旧版逐位一致(span/ans 的初始化不受影响)。
        self.fire = nn.Linear(h, 1) if fire else None

    def forward(self, enc, last_idx):
        hs = self.base(**enc).last_hidden_state
        s, e = self.span(hs).unbind(-1)
        a = self.ans(hs[torch.arange(hs.size(0), device=hs.device),
                        last_idx]).squeeze(-1)
        return s, e, a

    def fire_logit(self, enc):
        """开火头:纯样本文本的 [CLS] 位(左截后 CLS 仍在 0 号位)-> 标量 logit。"""
        hs = self.base(**enc).last_hidden_state
        return self.fire(hs[:, 0]).squeeze(-1)


# ---------- 数据:样本文本 × params 区间 ----------

def join_rows(data, params, split, limit=0, ro=None):
    """流式并归(两文件同序,params 是样本堆的子序列)-> (texts, instances)。

    ro 非 None 时(--readonly-env):只留真值为只读工具的样本,其余(含表外)丢弃并计数;
    清点用的标签在丢弃前收齐,audit 由调用方在返回后跑。
    """
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
        if ro is not None:                     # 非只读样本整条丢掉(计数在 ro 里)
            ro["labels"].append(r["label"])
            if r["label"] not in ro["set"]:
                ro["dropped"] += 1
                continue
            ro["kept"] += 1
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


def fire_rows(data, params, split, ro_set, limit=0):
    """开火头的样本级数据流(--fire-head 专用):主数据每行一条,不做只读过滤。

    ready = 标签在只读集合里 且 该样本所有参数 found=true;
    零参数事件 found 条件空真;params 里 join 不到的样本按 not-ready 处理并计数
    (其中 args_named 非空的另计——那才是真正可疑的那一类)。
    返回 (rows=[(text, ready, w)], stats)。
    """
    pmap = {}
    for line in open(params / f"{split}.jsonl"):
        p = json.loads(line)
        pmap[(p["event"], p["sent_idx"])] = p["params"]
    rows = []
    st = dict(n=0, n_ready=0, n_readonly=0, n_noparam=0,
              n_join_miss=0, n_join_miss_with_args=0)
    for line in open(data / f"{split}.jsonl"):
        r = json.loads(line)
        st["n"] += 1
        is_ro = r["label"] in ro_set
        st["n_readonly"] += is_ro
        ps = pmap.get((r["event"], r["sent_idx"]))
        if ps is None:
            st["n_join_miss"] += 1
            if r.get("args_named"):
                st["n_join_miss_with_args"] += 1
            ready = False
        else:
            st["n_noparam"] += not ps
            ready = is_ro and all(q["found"] for q in ps)
        st["n_ready"] += ready
        rows.append((r["text"], float(ready), float(r["w"])))
    n = max(st["n"], 1)
    st["frac_ready"] = round(st["n_ready"] / n, 6)
    st["frac_readonly"] = round(st["n_readonly"] / n, 6)
    st["frac_join_miss"] = round(st["n_join_miss"] / n, 6)
    if st["frac_join_miss"] > 0.01:
        print(f"[fire-head] 警告:{split} 有 {st['n_join_miss']}/{st['n']} "
              f"({st['frac_join_miss']:.1%}) 个样本在 params 文件里 join 不到,"
              f"已全部按 not-ready 处理(其中 args_named 非空 "
              f"{st['n_join_miss_with_args']} 条)", flush=True)
    if limit:
        rng = random.Random(SEED)          # 独立 RNG,不动全局随机流
        rng.shuffle(rows)
        rows = rows[:limit]
    return rows, st


class FireDS(Dataset):
    """开火头数据集:一条样本一条实例(不按参数展开,天然不重复计权)。"""

    def __init__(self, rows):
        self.rows = rows

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        return self.rows[i]


def fire_collate(batch, tok, max_len):
    texts, ready, ws = zip(*batch)
    enc = tok(list(texts), truncation=True, max_length=max_len, padding=True,
              return_tensors="pt")
    return dict(enc=enc, ready=torch.tensor(ready, dtype=torch.float),
                w=torch.tensor(ws, dtype=torch.float))


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


@torch.no_grad()
def evaluate_fire(model, loader, dev, amp):
    """val 开火头:acc@0.5(按 w 加权,阈值 0.5 <=> logit>0)与正负例数(未加权)。"""
    model.eval()
    hit = w_tot = 0.0
    n_pos = n_neg = 0
    for b in loader:
        enc = {k: v.to(dev) for k, v in b["enc"].items()}
        with amp():
            lg = model.fire_logit(enc)
        pred = lg.float().cpu() > 0
        y = b["ready"] > 0.5
        hit += float(((pred == y).float() * b["w"]).sum())
        w_tot += float(b["w"].sum())
        n_pos += int(y.sum())
        n_neg += int((~y).sum())
    model.train()
    return hit / max(w_tot, 1e-9), n_pos, n_neg


def load_extractor(run, device="cuda"):
    """eval_mbert_call 复用:返回 (model, tok, meta)。

    meta 里有 "fire_head": true 的 run 才建开火头——裸 state_dict 是严格加载,
    建多了或建少了都会在这里报 missing/unexpected key,正好当保险丝。
    """
    run = Path(run)
    meta = json.loads((run / "best" / "meta.json").read_text())
    tok = AutoTokenizer.from_pretrained(run / "best")
    tok.truncation_side = "left"
    model = Extractor(meta["base"], fire=bool(meta.get("fire_head")))
    model.load_state_dict(torch.load(run / "best" / "model.pt",
                                     map_location="cpu"))
    return model.to(device).eval(), tok, meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default="appworld",
                    choices=["tales", "appworld", "bfcl", "alfworld"],
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
    ap.add_argument("--readonly-env", default=None,
                    choices=list(readonly_map.READONLY_ENVS),
                    help="只读工具模式:只用真值为只读工具的样本训练(默认关=旧口径)")
    ap.add_argument("--grad-ckpt", action="store_true",
                    help="梯度检查点:数学中性,只换显存(fire 双前向在长序列档会顶爆 48G 卡)")
    ap.add_argument("--fire-head", action="store_true",
                    help="再学一个样本级开火头(此刻该不该发射投机);"
                         "必须与 --readonly-env 同传,默认关=行为不变")
    ap.add_argument("--force", action="store_true",
                    help="允许在已训过的 --out 目录再次训练(默认拒绝防产物混淆)")
    args = ap.parse_args()

    if args.fire_head and not args.readonly_env:
        raise SystemExit(
            "--fire-head 必须与 --readonly-env 同时传:开火标签 ready 的定义"
            "依赖该环境的只读真值表(ready = 只读 且 参数全 found),"
            "没有环境就算不出标签。")

    torch.manual_seed(SEED)
    random.seed(SEED)
    data = Path(args.data)
    params = Path(args.params) if args.params else data / "params"
    out = Path(args.out)
    if (out / "train_log.jsonl").exists() and not args.force:
        raise SystemExit(
            f"{out} 已有 train_log.jsonl——这个目录训过一次,再训会把两次产物"
            "混进同一个 best/ 且无法归属(审计 B7)。换 --out,或确认覆盖后加 --force。")
    out.mkdir(parents=True, exist_ok=True)
    dev = args.device
    amp = ((lambda: torch.autocast("cuda", dtype=torch.bfloat16))
           if dev.startswith("cuda") else contextlib.nullcontext)

    tok = AutoTokenizer.from_pretrained(MODEL)
    tok.truncation_side = "left"
    model = Extractor(fire=args.fire_head).to(dev)
    if args.grad_ckpt:
        model.base.gradient_checkpointing_enable()
    model.train()

    lim_tr, lim_ev = (500, 200) if args.smoke else (0, 0)
    if args.max_inst:
        lim_tr = min(lim_tr or args.max_inst, args.max_inst)
        lim_ev = min(lim_ev or args.max_inst, args.max_inst)
    epochs = 1 if args.smoke else args.epochs
    ro_tr = ro_ev = None
    if args.readonly_env:
        ro_set = readonly_map.load_readonly_set(args.readonly_env)
        ro_table = readonly_map.load_table(args.readonly_env)
        ro_tr = dict(set=ro_set, labels=[], kept=0, dropped=0)
        ro_ev = dict(set=ro_set, labels=[], kept=0, dropped=0)
    tr = InstDS(*join_rows(data, params, "train", lim_tr, ro_tr))
    ev = InstDS(*join_rows(data, params, "val", lim_ev, ro_ev))
    fire_st = {}
    fire_tr = fire_ev = None
    if args.fire_head:
        # 开火头的样本级流:非只读样本在这里当负例回到数据流,不进 span 实例
        ftr, fire_st["train"] = fire_rows(data, params, "train", ro_set, lim_tr)
        fev, fire_st["val"] = fire_rows(data, params, "val", ro_set, lim_ev)
        fire_tr, fire_ev = FireDS(ftr), FireDS(fev)
    if args.readonly_env:
        au_tr = readonly_map.audit(ro_tr["labels"], ro_table, where="mext/train")
        au_ev = readonly_map.audit(ro_ev["labels"], ro_table, where="mext/val")
        ro_out = dict(
            readonly_env=args.readonly_env,
            table=str(readonly_map.table_path(args.readonly_env)),
            train=au_tr, val=au_ev,
            kept=dict(train=ro_tr["kept"], val=ro_ev["kept"]),
            dropped=dict(train=ro_tr["dropped"], val=ro_ev["dropped"]))
        if args.fire_head:
            ro_out["fire_head"] = fire_st
        (out / "READONLY.json").write_text(json.dumps(
            ro_out, ensure_ascii=False, indent=1))
    mk = lambda ds, sh: DataLoader(
        ds, batch_size=args.bs, shuffle=sh, num_workers=2,
        collate_fn=lambda b: collate(b, tok, args.max_len))
    tr_dl, ev_dl = mk(tr, True), mk(ev, False)
    fire_tr_dl = fire_ev_dl = fire_it = None
    if args.fire_head:
        mkf = lambda ds, sh: DataLoader(
            ds, batch_size=args.bs, shuffle=sh, num_workers=2,
            collate_fn=lambda b: fire_collate(b, tok, args.max_len))
        fire_tr_dl, fire_ev_dl = mkf(fire_tr, True), mkf(fire_ev, False)

        def cycle(dl):                     # 开火流与 span 流长度不同,循环取
            while True:
                for x in dl:
                    yield x
        fire_it = cycle(fire_tr_dl)

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
        steps=steps, smoke=args.smoke, max_len=args.max_len, device=dev,
        readonly_env=args.readonly_env,
        **(dict(fire_head=True, n_fire_train=len(fire_tr),
                n_fire_eval=len(fire_ev),
                fire_ready_train=fire_st["train"]["frac_ready"],
                fire_ready_val=fire_st["val"]["frac_ready"])
           if args.fire_head else {}))

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
            if args.fire_head:
                # 开火头独立成批:输入是纯 text,标签 ready,按 w 加权,λ=1
                fb = next(fire_it)
                fenc = {k: v.to(dev) for k, v in fb["enc"].items()}
                with amp():
                    flg = model.fire_logit(fenc)
                fwd = fb["w"].to(dev)
                lf = ((bce(flg.float(), fb["ready"].to(dev)) * fwd).sum()
                      / fwd.sum())
                loss = loss + lf
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
        fkw = {}
        if args.fire_head:
            facc, fpos, fneg = evaluate_fire(model, fire_ev_dl, dev, amp)
            fkw = dict(fire_acc=round(facc, 4), fire_n_pos=fpos,
                       fire_n_neg=fneg)
        log(event="eval", ep=ep, calA_ans_acc=round(aacc, 4),
            calA_span_loose=round(sl, 4), calA_span_strict=round(ss, 4),
            calA_param_acc=round(tacc, 4), truncated_spans=cutsum, **fkw)
        if tacc > best:
            best = tacc
            (out / "best").mkdir(exist_ok=True)
            torch.save(model.state_dict(), out / "best" / "model.pt")
            tok.save_pretrained(out / "best")
            meta = dict(env=args.env, base=MODEL, max_len=args.max_len,
                        find=FIND, max_span_tok=MAX_SPAN_TOK, seed=SEED,
                        calA_param_acc=round(best, 4))
            if args.readonly_env:
                meta["readonly_env"] = args.readonly_env
            if args.fire_head:
                meta["fire_head"] = True
            (out / "best" / "meta.json").write_text(json.dumps(
                meta, ensure_ascii=False))
            log(event="save_best", ep=ep, acc=round(best, 4))
    log(event="done", best_calA_param_acc=round(best, 4),
        truncated_spans=cutsum)


if __name__ == "__main__":
    main()
