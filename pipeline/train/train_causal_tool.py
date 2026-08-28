"""因果探针训练(新流水线 ctool 格):因果语言模型底座 + 线性分类头。

与 ModernBERT 探针(train_mbert_tool.py)的本质区别:ModernBERT 每个句子边界重编码
整段前缀(成本随思考长度平方涨),这里按**事件**组织——一个事件的各样本 text
互为前缀,全文 = 最大 sent_idx 样本的 text,第 i 个边界的字符位置 = len(第 i 个
样本的 text);整段一次前向,每个边界位置放一份分类监督(权重 = 样本自带 w)。

- 输入: <data_out>/{train,val}.jsonl + tool_vocab.json
- 底座: --base qwen -> Qwen3-0.6B-Base / qwen17 -> 1.7B / qwen4 -> 4B
- 上限: --max-len(默认 8192)按事件全文 token 数整条丢弃超长事件(不截断),
  计数进 start 事件的 dropped_events_train/dropped_events_val;读取位置规则
  (share_data.read_position)在留下的事件里找不到切点时才计 n_bound_dropped,
  预期恒为 0
- 评估: 每轮 val 报 calA_weighted_acc + calA_lastbound_acc(日志字段名照旧不改)
- 产物: <out>/{ALIGN_CHECK.json, train_log.jsonl, best/}
- LoRA: `--lora` 只把底座换成 LoRA 训(分类头照常全参),存 best 之前先
  merge_and_unload 把适配器并回底座,所以 best/ 的文件与全参存的逐项同构、
  eval_tool.py 零改动就装得回来;meta.json 多一个 "lora" 块记超参。
  不传 --lora 时脚本自己不碰 peft(peft 的 import 全在 --lora 分支里),
  行为与加这套旗标之前一致;详见 lora_util.py 的说明。

**开训前对齐检查是铁律**(--align-only 只跑它):同一段真实文本,整段一次前向 vs
逐 token 增量前向(带 past_key_values),末位置隐状态与分类头 logits 必须
max|diff| < 1e-4 才许训。前科:LFM2 混合架构(conv+attention)在 transformers
5.14.1 下"缓存非空 + 一次喂多 token"(分块增量)会静默算错——见
check_causal_candidates.py 的结论,判定为整段一次前向或逐 token 增量可用、
**禁分块**。本脚本训练与评估只用整段一次前向,增量前向仅出现在这份对齐检查里,
所以两个底座都在安全区内。

用法:
  # 只过对齐检查
  cprobe-env/bin/python pipeline/train/train_causal_tool.py --base qwen \
    --data pipeline/data/aw_official_v1/q35 --out pipeline/runs/c1_q35_ctool --align-only
  # 冒烟
  cprobe-env/bin/python pipeline/train/train_causal_tool.py --base qwen \
    --data pipeline/data/aw_official_v1/q35 --out pipeline/runs/c1_q35_ctool --smoke
  # 全量
  cprobe-env/bin/python pipeline/train/train_causal_tool.py --base qwen \
    --data pipeline/data/aw_official_v1/q35 --out pipeline/runs/c1_q35_ctool
"""

import argparse
import json
import math
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

import torch
import transformers
_TV = tuple(int(x) for x in transformers.__version__.split(".")[:2])
if _TV < (5, 14):
    raise SystemExit(f"cprobe 线要 transformers>=5.14,当前 "
                     f"{transformers.__version__}——解释器用错了?"
                     "一律从 run.py 的任务进(train-ctool/train-cgen)。")
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModel, AutoTokenizer, get_linear_schedule_with_warmup

import lora_util
import readonly_map
import share_data

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / "ops"))
import heartbeat


# 底座三档(2026-08-21 起因果线从单档扩成三档,目的是横向比三个规模)
MODELS = {
    "qwen":   "/net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-0.6B-Base",
    "qwen17": "/net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-1.7B-Base",
    "qwen4":  "/net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-4B-Base",
}
SEED = 42          # np821 起换种子家族(42/67/4267/6742)首位;旧值 20260729 只在旧数据复现里生效
FULL_LR = 1e-5     # 全参微调的学习率(不传 --lora 时的 --lr 默认值)
ALIGN_TOL = 3e-4   # 2026-08-28 起(上限 8192):c1/np821 实跑一直传 3e-4;8,167 token 的事件 maxdiff_hidden 1.03e-4 相对差 1.46e-6 被旧默认 1e-4 拦下
SPOT = 50          # 前缀性质抽查的事件数


# ---------------------------------------------------------------- 数据

def load_events(path, label2id, tok, max_len, limit=0, spot=SPOT, ro=None):
    """按 event 分组:全文 = 最大 sent_idx 样本的 text,边界 = 各样本 len(text)。

    全文 token 数(`tok(full, add_special_tokens=False)`)超过 `max_len` 的
    事件整条丢弃(spec 11.1),返回值多带一个丢弃计数。
    """
    ev = defaultdict(list)
    if ro is None:
        for line in open(path):
            r = json.loads(line)
            if r["label"] in label2id:
                ev[r["event"]].append(r)
    else:                                      # --readonly-env:先清点后折叠
        rows = [json.loads(line) for line in open(path)]
        ro["info"] = readonly_map.audit(
            [r["label"] for r in rows], ro["table"], where=ro["where"])
        for r in rows:
            r["label"] = readonly_map.collapse(r["label"], ro["set"])
        bad = sorted({r["label"] for r in rows} - set(label2id))
        if bad:
            raise SystemExit(
                f"readonly: {ro['where']} 折叠后仍有 {len(bad)} 个标签不在"
                f"折叠词表里(如 {bad[:5]})——tool_vocab.json 与数据对不上,硬停。")
        for r in rows:
            ev[r["event"]].append(r)
    events = []
    for k, rs in ev.items():
        rs.sort(key=lambda r: r["sent_idx"])
        full = rs[-1]["text"]
        events.append(dict(
            event=k, full=full, rows=rs, y=label2id[rs[-1]["label"]],
            bounds=[(len(r["text"]), float(r["w"]),
                     r["sent_idx"] == r["n_sents"] - 1) for r in rs]))
    events.sort(key=lambda e: e["event"])
    rng = random.Random(SEED)
    for e in rng.sample(events, min(spot, len(events))):   # 前缀性质抽查
        assert all(e["full"].startswith(r["text"]) for r in e["rows"]), \
            f"事件 {e['event']} 的样本 text 不互为前缀"
    for e in events:
        e.pop("rows")
    dropped = 0
    kept = []
    for e in events:
        n_full = len(tok(e["full"], add_special_tokens=False)["input_ids"])
        if n_full > max_len:
            dropped += 1
            continue
        kept.append(e)
    events = kept
    if limit:
        rng.shuffle(events)
        events = events[:limit]
    return events, dropped


class EventDS(Dataset):
    def __init__(self, events):
        self.events = events

    def __len__(self):
        return len(self.events)

    def __getitem__(self, i):
        return self.events[i]


def collate(batch, tok, max_len):
    """整段一次前向所需的一批事件:返回 enc + 每个监督位置的 (行, 列, y, w, last)。"""
    enc = tok([e["full"] for e in batch], truncation=False, max_length=max_len,
              padding=True, return_offsets_mapping=True, return_tensors="pt")
    offs = enc.pop("offset_mapping")
    rows, cols, ys, ws, lasts, dropped = [], [], [], [], [], 0
    for i, e in enumerate(batch):
        full = e["full"]
        offsets_i = offs[i].tolist()
        keep = int(enc["attention_mask"][i].sum())
        for b, w, last in e["bounds"]:
            j = share_data.read_position(offsets_i, full, b, keep)
            if j < 0:                # 找不到读取位置的切点数(n_bound_dropped),预期 0
                dropped += 1
                continue
            rows.append(i)
            cols.append(j)
            ys.append(e["y"])
            ws.append(w)
            lasts.append(last)
    return (enc, torch.tensor(rows), torch.tensor(cols), torch.tensor(ys),
            torch.tensor(ws, dtype=torch.float), torch.tensor(lasts), dropped)


# ---------------------------------------------------------------- 模型

class CausalProbe(torch.nn.Module):
    """因果语言模型底座 + nn.Linear 分类头(取各监督 token 位的末层隐状态)。"""

    def __init__(self, path, n_labels):
        super().__init__()
        self.backbone = AutoModel.from_pretrained(path, dtype=torch.float32)
        h = self.backbone.config.get_text_config().hidden_size
        self.head = torch.nn.Linear(h, n_labels)

    def hidden(self, enc):
        return self.backbone(input_ids=enc["input_ids"],
                             attention_mask=enc["attention_mask"],
                             use_cache=False).last_hidden_state

    def forward(self, enc, rows, cols):
        h = self.hidden(enc)
        h = h[rows.to(h.device), cols.to(h.device)]   # [n_sup, hidden]
        return self.head(h.float())


def build(base, n_labels, dev):
    path = MODELS[base]
    tok = AutoTokenizer.from_pretrained(path)
    if tok.pad_token_id is None:                      # 照抄 check_causal_candidates
        tok.pad_token = tok.eos_token
    tok.truncation_side = "left"                      # 保思考尾巴
    tok.padding_side = "right"                        # 监督位都在真实 token 上
    torch.manual_seed(SEED)
    model = CausalProbe(path, n_labels)
    if model.backbone.config.get_text_config().pad_token_id is None:
        model.backbone.config.get_text_config().pad_token_id = tok.pad_token_id
    return tok, model.to(dev), path


# ---------------------------------------------------------------- 对齐检查

@torch.no_grad()
def align_check(model, tok, text, max_len, dev, base, path, tol=ALIGN_TOL):
    """整段一次前向 vs 逐 token 增量前向(fp32),末位置隐状态/logits 必须一致。

    只用逐 token 模式:分块增量(缓存非空+一次喂多 token)在 LFM2 上有静默算错前科。
    """
    model.eval()
    prev_prec = torch.get_float32_matmul_precision()
    torch.set_float32_matmul_precision("highest")   # 禁 TF32,别让降精度冒充算错
    ids = tok(text, truncation=False, max_length=max_len,
              return_tensors="pt")["input_ids"].to(dev)
    n = ids.shape[1]
    ones = torch.ones_like(ids)
    h_full = model.backbone(input_ids=ids, attention_mask=ones,
                            use_cache=False).last_hidden_state[:, -1]
    lg_full = model.head(h_full)

    past, out = None, None
    for t in range(n):
        out = model.backbone(input_ids=ids[:, t:t + 1],
                             attention_mask=ones[:, :t + 1],
                             past_key_values=past, use_cache=True)
        past = out.past_key_values
    h_inc = out.last_hidden_state[:, -1]
    lg_inc = model.head(h_inc)

    d_h = (h_full - h_inc).abs().max().item()
    d_l = (lg_full - lg_inc).abs().max().item()
    ok = max(d_h, d_l) < tol
    a_h, a_l = h_full.abs().max().item(), lg_full.abs().max().item()
    rep = dict(base=base, base_path=path, mode="token-by-token", n_tokens=n,
               maxdiff_hidden=d_h, maxdiff_logits=d_l, tol=tol,
               PASS=bool(ok), device=str(dev), dtype="float32",
               transformers=transformers.__version__, torch=torch.__version__,
               # 诊断用(不参与判定):绝对差受隐状态量级影响,相对差看是否只是 fp32 噪声
               absmax_hidden=a_h, absmax_logits=a_l,
               reldiff_hidden=d_h / max(a_h, 1e-9),
               reldiff_logits=d_l / max(a_l, 1e-9))
    torch.set_float32_matmul_precision(prev_prec)
    model.train()
    return rep


# ---------------------------------------------------------------- 评估

@torch.no_grad()
def evaluate(model, loader, dev, amp):
    model.eval()
    wc = ws = lc = ln = 0.0
    for enc, rows, cols, y, w, last, _drop in loader:
        enc = {k: v.to(dev) for k, v in enc.items()}
        with torch.autocast("cuda", dtype=torch.bfloat16, enabled=amp):
            pred = model(enc, rows, cols).argmax(-1).cpu()
        ok = (pred == y).float()
        wc += (ok * w).sum().item()
        ws += w.sum().item()
        lc += ok[last].sum().item()
        ln += last.sum().item()
    model.train()
    return wc / max(ws, 1e-9), lc / max(ln, 1)


# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, choices=sorted(MODELS),
                    help="qwen=Qwen3-0.6B-Base")
    ap.add_argument("--env", default="appworld",
                    choices=["tales", "appworld", "bfcl", "alfworld"],
                    help="仅作日志标签(数据路径已由 --data 直接给定)")
    ap.add_argument("--data", required=True,
                    help="数据目录 <data_out>(含 train/val.jsonl 与 tool_vocab.json)")
    ap.add_argument("--out", required=True, help="产物目录(必填,防覆盖旧件)")
    ap.add_argument("--max-len", type=int, default=8192)
    ap.add_argument("--bs", type=int, default=4, help="事件数/批")
    ap.add_argument("--accum", type=int, default=2)
    ap.add_argument("--lr", type=float, default=None,
                    help=f"学习率(默认 {FULL_LR};开 --lora 时默认换成 --lora-lr,"
                         "这里显式给了就以显式值为准)")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--smoke", action="store_true",
                    help="200 训练事件/80 评估事件/1 epoch,验证管线")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--grad-ckpt", action="store_true",
                    help="底座开梯度检查点省显存(全参与 --lora 两种模式都能用;"
                         "同时关 use_cache,LoRA 下另保证输入 require_grad)")
    ap.add_argument("--max-events", type=int, default=0,
                    help="调试用:再限事件数(0=不限)")
    ap.add_argument("--align-only", action="store_true",
                    help="只跑开训前对齐检查即退")
    ap.add_argument("--align-tol", type=float, default=ALIGN_TOL,
                    help="对齐检查绝对差阈值(默认 3e-4,2026-08-28 起;之前 1e-4)。"
                         "长窗口下 fp32 舍入噪声随 token 数与隐状态量级一起涨,"
                         "8192 上限的事件绝对差会顶到 1e-4 而相对差仍是 1e-6"
                         "(纯噪声);判定依据看 reldiff(1e-3 以上=真算错,放宽也没用)")
    ap.add_argument("--readonly-env", default=None,
                    choices=list(readonly_map.READONLY_ENVS),
                    help="只读工具模式:标签折叠成 该环境的只读工具 + "
                         f"{readonly_map.NON_READONLY} 弃权类(默认关=旧口径)")
    ap.add_argument("--force", action="store_true",
                    help="允许在已训过的 --out 目录再次训练(默认拒绝防产物混淆)")
    lora_util.add_args(ap)
    args = ap.parse_args()
    lr = lora_util.resolve_lr(args, FULL_LR)

    torch.manual_seed(SEED)
    random.seed(SEED)
    data = Path(args.data)
    out = Path(args.out)
    if (out / "train_log.jsonl").exists() and not args.force:
        raise SystemExit(
            f"{out} 已有 train_log.jsonl——这个目录训过一次,再训会把两次产物"
            "混进同一个 best/ 且无法归属(审计 B7)。换 --out,或确认覆盖后加 --force。")
    out.mkdir(parents=True, exist_ok=True)
    dev = args.device
    amp = dev.startswith("cuda")

    vocab = json.loads((data / "tool_vocab.json").read_text())
    ro_tr = ro_ev = None
    if args.readonly_env:                      # 词表 = 原序只读工具 + 末尾哨兵
        ro_set = readonly_map.load_readonly_set(args.readonly_env)
        ro_table = readonly_map.load_table(args.readonly_env)
        vocab = [t for t in vocab if t in ro_set] + [readonly_map.NON_READONLY]
        ro_tr = dict(set=ro_set, table=ro_table, where="ctool/train")
        ro_ev = dict(set=ro_set, table=ro_table, where="ctool/val")
    label2id = {k: i for i, k in enumerate(vocab)}
    tok, model, path = build(args.base, len(label2id), dev)

    lim_tr, lim_ev = (200, 80) if args.smoke else (0, 0)
    if args.max_events:
        lim_tr = min(lim_tr, args.max_events) if lim_tr else args.max_events
        lim_ev = min(lim_ev, args.max_events) if lim_ev else args.max_events
    epochs = 1 if args.smoke else args.epochs
    ev_events, dropped_events_val = load_events(
        data / "val.jsonl", label2id, tok, args.max_len, ro=ro_ev)
    longest = max(ev_events, key=lambda e: len(e["full"]))["full"]
    if lim_ev:
        random.Random(SEED).shuffle(ev_events)
        ev_events = ev_events[:lim_ev]

    # ---- 开训必过的门:对齐检查(val 最长事件全文,截到 --max-len) ----------
    rep = align_check(model, tok, longest, args.max_len, dev, args.base, path,
                      tol=args.align_tol)
    (out / "ALIGN_CHECK.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep, indent=1), flush=True)
    if not rep["PASS"]:
        print("对齐检查 FAIL:整段前向与逐 token 增量前向不一致,拒绝开训。\n"
              f"  hidden max|diff| = {rep['maxdiff_hidden']:.3e}\n"
              f"  logits max|diff| = {rep['maxdiff_logits']:.3e}  (tol {rep['tol']:.1e})\n"
              f"  相对差 hidden {rep['reldiff_hidden']:.2e} / logits "
              f"{rep['reldiff_logits']:.2e}(1e-6 量级=纯 fp32 噪声、绝对差只是"
              "隐状态量级大;1e-3 以上=真算错)\n"
              "  排查:transformers 版本 / 该架构的缓存实现 / 是否误用分块增量。",
              flush=True)
        sys.exit(2)
    if args.align_only:
        return

    tr_events, dropped_events_train = load_events(
        data / "train.jsonl", label2id, tok, args.max_len, lim_tr, ro=ro_tr)
    if args.readonly_env:
        (out / "READONLY.json").write_text(json.dumps(dict(
            readonly_env=args.readonly_env,
            table=str(readonly_map.table_path(args.readonly_env)),
            train=ro_tr["info"], val=ro_ev["info"],
            vocab_size_collapsed=len(label2id)), ensure_ascii=False, indent=1))
    mk = lambda ds, sh: DataLoader(
        EventDS(ds), batch_size=args.bs, shuffle=sh, num_workers=2,
        collate_fn=lambda b: collate(b, tok, args.max_len))
    tr_dl, ev_dl = mk(tr_events, True), mk(ev_events, False)
    # LoRA 只包底座:分类头照常全参训练(头是新初始化的,没有可低秩化的旧权重),
    # 头的参数与适配器一起进优化器。包装动作放在对齐检查之后,ALIGN_CHECK.json
    # 与全参跑逐字段可比。
    lora_wrap = lora_util.wrap(model.backbone, args) if args.lora else None
    if args.grad_ckpt:
        model.backbone.gradient_checkpointing_enable()
        model.backbone.config.use_cache = False
        if args.lora:
            lora_util.prepare_grad_ckpt(model.backbone)
    model.train()

    steps = math.ceil(len(tr_dl) / args.accum) * epochs
    opt = torch.optim.AdamW(lora_util.opt_params(model.parameters(), args.lora),
                            lr=lr, weight_decay=0.01)
    sch = get_linear_schedule_with_warmup(opt, int(steps * 0.05), steps)
    lossf = torch.nn.CrossEntropyLoss(reduction="none")

    logf = open(out / "train_log.jsonl", "a")

    def log(**kw):
        kw["t"] = round(time.time(), 1)
        logf.write(json.dumps(kw) + "\n")
        logf.flush()
        print(kw, flush=True)

    log(event="start", base=args.base, base_path=path, env=args.env,
        n_train=len(tr_events), n_eval=len(ev_events), n_labels=len(label2id),
        steps=steps, smoke=args.smoke, max_len=args.max_len, seed=SEED,
        align_pass=rep["PASS"], align_maxdiff_hidden=rep["maxdiff_hidden"],
        align_maxdiff_logits=rep["maxdiff_logits"],
        readonly_env=args.readonly_env,
        dropped_events_train=dropped_events_train,
        dropped_events_val=dropped_events_val,
        **(dict(lora=lora_util.meta_block(args, lr)) if args.lora else {}))
    heartbeat.emit(0, steps, "step")

    best = -1.0
    gstep = 0
    for ep in range(epochs):
        t0, run, ndrop = time.time(), 0.0, 0
        for i, (enc, rows, cols, y, w, _last, drop) in enumerate(tr_dl):
            enc = {k: v.to(dev) for k, v in enc.items()}
            ndrop += drop
            with torch.autocast("cuda", dtype=torch.bfloat16, enabled=amp):
                logits = model(enc, rows, cols)
            wd = w.to(dev)
            loss = (lossf(logits.float(), y.to(dev)) * wd).sum() / wd.sum()
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
                        ips=round((i + 1) * args.bs / (time.time() - t0), 2),
                        n_bound_dropped=ndrop, lr=sch.get_last_lr()[0])
                    heartbeat.emit(gstep, steps, "step",
                                   loss=round(run / (50 * args.accum), 4))
                    run = 0.0
        wacc, lacc = evaluate(model, ev_dl, dev, amp)
        log(event="eval", ep=ep, calA_weighted_acc=round(wacc, 4),
            calA_lastbound_acc=round(lacc, 4), n_bound_dropped=ndrop)
        if wacc > best:
            best = wacc
            (out / "best").mkdir(parents=True, exist_ok=True)
            if lora_wrap is None:
                model.backbone.save_pretrained(out / "best")
            else:
                # 适配器并回底座再落盘:best/ 与全参存的逐项同构,评测端零改动
                lora_util.save_merged(lora_wrap, out / "best", dev)
            tok.save_pretrained(out / "best")
            torch.save(model.head.state_dict(), out / "best" / "head.pt")
            (out / "best" / "label_map.json").write_text(
                json.dumps(label2id, ensure_ascii=False))
            meta = dict(
                base=args.base, base_path=path, env=args.env, data=str(data),
                max_len=args.max_len, n_labels=len(label2id), seed=SEED,
                epoch=ep, transformers=transformers.__version__)
            if args.readonly_env:
                meta["readonly_env"] = args.readonly_env
            if args.lora:
                meta["lora"] = lora_util.meta_block(args, lr)
            if args.grad_ckpt:
                meta["grad_ckpt"] = True
            (out / "best" / "meta.json").write_text(json.dumps(meta, indent=1))
            log(event="save_best", ep=ep, acc=round(best, 4))
    log(event="done", best_calA_weighted_acc=round(best, 4))
    heartbeat.emit(gstep, steps, "step", status="done")


if __name__ == "__main__":
    main()
