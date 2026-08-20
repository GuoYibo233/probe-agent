"""因果调用生成训练(新流水线 cgen 格):Qwen3-0.6B-Base 微调成"看题干写整条调用"。

与 ctool(train_causal_tool.py)的分工:ctool 只出工具种类,cgen 直接把
工具名 + 全部参数一次写出来(`apis.spotify.login(username=x, password=y)`)。

- 输入: <data_out>/{train,val}.jsonl,每行取 text / label_call / w 三个字段;
  一条样本 = 一条训练实例
- 底座: --base qwen -> Qwen3-0.6B-Base(默认)/ qwen17 -> 1.7B / qwen4 -> 4B
- 拼串: 输入串 = text + CALL_SEP("\\n[CALL] "),目标串 = label_call + eos
- 防左截吃目标: 先 tokenize 目标得 tgt_ids(不截断),超 MAX_TGT_TOK 的实例整条
  丢弃并计数;再按 max_length = --max-len - len(tgt_ids) 左截输入串,拼接后
  labels 把 prompt 段掩成 -100(批内右 padding,pad 位同样 -100)
- 损失: 逐实例目标段 mean CE(ce_i),批损失 = Σ(w_i·ce_i)/Σw_i
- 评估: 每轮 val 全量加权 masked-CE(val_ce,选 best 的唯一依据,越低越好)+
  定种子抽 GEN_N 条 greedy 生成报 val_exact_call(只进日志,不选 best)
- 产物: <out>/best/(HF 权重 + tokenizer + meta.json)+ train_log.jsonl
- LoRA: `--lora` 把底座换成 LoRA 训(开火头如果有,照常全参),存 best 之前先
  merge_and_unload 把适配器并回底座,所以 best/ 的文件与全参存的逐项同构、
  eval_causal_call.py 零改动就装得回来;meta.json 多一个 "lora" 块记超参。
  不传 --lora 时脚本自己不碰 peft(peft 的 import 全在 --lora 分支里),
  行为与加这套旗标之前一致;详见 lora_util.py 的说明。

开火头(`--fire-head`,必须与 --readonly-env 同传;默认不传 = 行为与旧版一致):
- backbone 末层隐状态 -> Linear(h,1) 的样本级二分类头,学"此刻该不该发射投机"。
  取的位置是**prompt 末位**(labels 里最后一个 -100 的位置,即 CALL_SEP 的最后一个
  token):这一位的隐状态只看得见 text+CALL_SEP,与线上开火时能拿到的输入一致;
  取整串末位会把目标调用串本身喂进开火头,直接泄题。
- 开火标签 ready = 标签在只读集合里 且 该样本所有参数 found=true
  (零参数事件 found 条件空真;params 里 join 不到的按 not-ready 并计数)
- 非只读样本不再整条丢弃,而是当开火头负例回到数据流:它们的 LM labels 全 -100,
  不产生 LM 梯度,也不进 val_ce 的分子分母
- 损失 = 原 masked-CE + λ·开火 BCE(λ=1);批内全是非只读样本时 LM 项分母为零,
  整项跳过(不出 NaN)
- best 的选择指标不变(val masked-CE,只在只读样本上算);开火头存
  best/fire_head.pt,meta.json 加 "fire_head": true

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
_TV = tuple(int(x) for x in transformers.__version__.split(".")[:2])
if _TV < (5, 14):
    raise SystemExit(f"cprobe 线要 transformers>=5.14,当前 "
                     f"{transformers.__version__}——解释器用错了?"
                     "一律从 run.py 的任务进(train-ctool/train-cgen)。")
from torch.utils.data import DataLoader, Dataset
from transformers import (AutoModelForCausalLM, AutoTokenizer,
                          get_linear_schedule_with_warmup)

import lora_util
import readonly_map

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / "ops"))
import heartbeat


# 底座三档(2026-08-21 起因果线从单档扩成三档,样式与 train_causal_tool.MODELS 同)。
# --base 默认 qwen,不传时的行为与加这张表之前逐字节相同。
MODELS = {
    "qwen":   "/net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-0.6B-Base",
    "qwen17": "/net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-1.7B-Base",
    "qwen4":  "/net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-4B-Base",
}
SEED = 20260729
FULL_LR = 1e-5             # 全参微调的学习率(不传 --lora 时的 --lr 默认值)
CALL_SEP = "\n[CALL] "
MAX_TGT_TOK = 160          # 目标串 token 上限,超了整条实例丢弃
MAX_GEN_TOK = 96           # 评估生成的 max_new_tokens
GEN_N = 200                # 每轮抽多少条做 greedy 生成


# ---------------------------------------------------------------- 数据

def fire_pmap(params, split):
    """{(event, sent_idx): params} —— 开火标签要用的 found 信息。"""
    pmap = {}
    for line in open(params / f"{split}.jsonl"):
        p = json.loads(line)
        pmap[(p["event"], p["sent_idx"])] = p["params"]
    return pmap


def fire_stats():
    return dict(n=0, n_ready=0, n_readonly=0, n_noparam=0,
                n_join_miss=0, n_join_miss_with_args=0)


def fire_finish(st, where):
    n = max(st["n"], 1)
    st["frac_ready"] = round(st["n_ready"] / n, 6)
    st["frac_readonly"] = round(st["n_readonly"] / n, 6)
    st["frac_join_miss"] = round(st["n_join_miss"] / n, 6)
    if st["frac_join_miss"] > 0.01:
        print(f"[fire-head] 警告:{where} 有 {st['n_join_miss']}/{st['n']} "
              f"({st['frac_join_miss']:.1%}) 个样本在 params 文件里 join 不到,"
              f"已全部按 not-ready 处理(其中 args_named 非空 "
              f"{st['n_join_miss_with_args']} 条)", flush=True)
    return st


class CallDS(Dataset):
    """一条样本一条实例;构造时先 tokenize 目标串,过长的整条丢弃并计数。

    fire 非 None(--fire-head)时行数变两类:只读样本照旧(有 LM 目标),
    非只读样本只当开火头负例(tgt 空、has_lm=False,LM labels 全 -100)。
    行结构固定六元组 (text, tgt, w, label_call, ready, has_lm);
    默认关时 ready 恒 0.0、has_lm 恒 True,取值口径与旧版逐位相同。
    """

    def __init__(self, path, tok, limit=0, max_tgt=MAX_TGT_TOK, ro=None,
                 fire=None):
        self.rows, self.dropped = [], 0
        eos = tok.eos_token_id
        for line in open(path):
            r = json.loads(line)
            is_ro = True
            if ro is not None:                 # 非只读样本整条丢掉(计数在 ro 里)
                ro["labels"].append(r["label"])
                is_ro = r["label"] in ro["set"]
                if not is_ro:
                    ro["dropped"] += 1
                    if fire is None:
                        continue
                else:
                    ro["kept"] += 1
            ready = 0.0
            if fire is not None:
                st = fire["stats"]
                st["n"] += 1
                st["n_readonly"] += is_ro
                ps = fire["pmap"].get((r["event"], r["sent_idx"]))
                if ps is None:
                    st["n_join_miss"] += 1
                    if r.get("args_named"):
                        st["n_join_miss_with_args"] += 1
                else:
                    st["n_noparam"] += not ps
                    ready = float(is_ro and all(q["found"] for q in ps))
                st["n_ready"] += int(ready)
                if not is_ro:
                    # 只当开火头负例:不给 LM 目标,也不受 max_tgt 丢弃影响
                    self.rows.append((r["text"], [], float(r["w"]),
                                      r["label_call"], ready, False))
                    continue
            tgt = tok(r["label_call"], add_special_tokens=False)["input_ids"]
            tgt = tgt + [eos]
            if len(tgt) > max_tgt:
                self.dropped += 1
                continue
            self.rows.append((r["text"], tgt, float(r["w"]), r["label_call"],
                              ready, True))
        if limit:
            rng = random.Random(SEED)
            rng.shuffle(self.rows)
            self.rows = self.rows[:limit]

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        return self.rows[i]


def collate(batch, tok, max_len):
    """左截输入 + 右 padding;labels 掩掉 prompt 段与 pad 位。

    另返回 ready(开火标签)、lm(该行进不进 LM 损失)、plast(prompt 末位下标,
    开火头就在这一位取隐状态)。默认关时 ready 全 0、lm 全 1,不影响任何数值。
    """
    ids, labs, ws, ready, lm, plast = [], [], [], [], [], []
    for text, tgt, w, _call, rdy, has_lm in batch:
        keep = max(max_len - len(tgt), 1)
        prompt = tok(text + CALL_SEP, truncation=True, max_length=keep,
                     add_special_tokens=False)["input_ids"]
        ids.append(prompt + tgt)
        labs.append([-100] * len(prompt) + tgt)
        ws.append(w)
        ready.append(rdy)
        lm.append(float(has_lm))
        plast.append(max(len(prompt) - 1, 0))
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
            torch.tensor(ws, dtype=torch.float),
            torch.tensor(ready, dtype=torch.float),
            torch.tensor(lm, dtype=torch.float),
            torch.tensor(plast, dtype=torch.long))


# ---------------------------------------------------------------- 模型

def build(dev, base="qwen"):
    """tokenizer 构造照抄 train_causal_probe.build():pad=eos / 左截 / 右 pad。"""
    path = MODELS[base]
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


def inst_ce(model, enc, labels, dev, fire=None, plast=None):
    """逐实例目标段 mean CE。返回 [B] 的 float32 张量。

    fire 非 None 时多要一份末层隐状态,在 plast(prompt 末位)上过开火头,
    返回 (ce, fire_logit)。fire=None 的路径与旧版逐字节相同。
    """
    kw = {} if fire is None else dict(output_hidden_states=True)
    out = model(input_ids=enc["input_ids"], attention_mask=enc["attention_mask"],
                use_cache=False, **kw)
    lg = out.logits[:, :-1]                           # 预测下一 token
    tg = labels[:, 1:].to(dev)
    m = tg != -100
    ce = F.cross_entropy(lg[m].float(), tg[m], reduction="none")  # 只取目标位
    b = tg.size(0)
    inst = torch.arange(b, device=dev).unsqueeze(1).expand_as(tg)[m]
    ssum = torch.zeros(b, device=dev, dtype=torch.float32)
    ssum = ssum.index_add(0, inst, ce)
    ice = ssum / m.sum(1).clamp(min=1).float()
    if fire is None:
        return ice
    h = out.hidden_states[-1]                         # [B, L, hidden]
    hp = h[torch.arange(b, device=h.device), plast.to(h.device)]
    return ice, fire(hp.float()).squeeze(-1)


# ---------------------------------------------------------------- 评估

@torch.no_grad()
def eval_ce(model, loader, dev, amp, fire=None):
    """val 全量加权 masked-CE(与训练损失同口径)。

    fire 非 None 时:CE 的分子分母都只算有 LM 目标的行(=只读样本),口径与
    --readonly-env 单开时相同;顺带回一份开火头 acc@0.5(按 w 加权)与正负例数。
    """
    model.eval()
    s = w_tot = 0.0
    hit = fw_tot = 0.0
    n_pos = n_neg = 0
    for enc, labels, w, ready, lm, plast in loader:
        enc = {k: v.to(dev) for k, v in enc.items()}
        with torch.autocast("cuda", dtype=torch.bfloat16, enabled=amp):
            if fire is None:
                ce = inst_ce(model, enc, labels, dev)
            else:
                ce, flg = inst_ce(model, enc, labels, dev, fire, plast)
        wd = (w * lm if fire is not None else w).to(dev)
        s += (ce.float() * wd).sum().item()
        w_tot += wd.sum().item()
        if fire is not None:
            pred = flg.float().cpu() > 0
            y = ready > 0.5
            hit += float(((pred == y).float() * w).sum())
            fw_tot += float(w.sum())
            n_pos += int(y.sum())
            n_neg += int((~y).sum())
    model.train()
    vce = s / max(w_tot, 1e-9)
    if fire is None:
        return vce
    return vce, dict(fire_acc=round(hit / max(fw_tot, 1e-9), 4),
                     fire_n_pos=n_pos, fire_n_neg=n_neg)


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
    ap.add_argument("--base", default="qwen", choices=sorted(MODELS),
                    help="底座三档:qwen=0.6B(默认,与旧行为一致)/"
                         "qwen17=1.7B/qwen4=4B")
    ap.add_argument("--env", default="appworld",
                    choices=["tales", "appworld", "bfcl", "alfworld"],
                    help="仅作日志标签(数据路径已由 --data 直接给定)")
    ap.add_argument("--data", required=True,
                    help="数据目录 <data_out>(含 train/val.jsonl)")
    ap.add_argument("--out", required=True, help="产物目录(必填,防覆盖旧件)")
    ap.add_argument("--max-len", type=int, default=4096)
    ap.add_argument("--bs", type=int, default=4)
    ap.add_argument("--accum", type=int, default=8)
    ap.add_argument("--lr", type=float, default=None,
                    help=f"学习率(默认 {FULL_LR};开 --lora 时默认换成 --lora-lr,"
                         "这里显式给了就以显式值为准)")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--smoke", action="store_true",
                    help="500 训练实例/200 评估实例/1 epoch,验证管线")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--grad-ckpt", action="store_true",
                    help="底座开梯度检查点省显存(全参与 --lora 两种模式都能用;"
                         "同时关 use_cache,LoRA 下另保证输入 require_grad)")
    ap.add_argument("--gen-bs", type=int, default=8, help="生成评估的批大小")
    ap.add_argument("--max-inst", type=int, default=0,
                    help="调试用:再限实例数(0=不限)")
    ap.add_argument("--readonly-env", default=None,
                    choices=list(readonly_map.READONLY_ENVS),
                    help="只读工具模式:只用真值为只读工具的样本训练(默认关=旧口径)")
    ap.add_argument("--params", default=None,
                    help="参数区间标签目录(默认 <data>/params);只有 "
                         "--fire-head 用得上——开火标签要读 found")
    ap.add_argument("--fire-head", action="store_true",
                    help="再学一个样本级开火头(此刻该不该发射投机);"
                         "必须与 --readonly-env 同传,默认关=行为不变")
    ap.add_argument("--force", action="store_true",
                    help="允许在已训过的 --out 目录再次训练(默认拒绝防产物混淆)")
    lora_util.add_args(ap)
    args = ap.parse_args()
    lr = lora_util.resolve_lr(args, FULL_LR)

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
    amp = dev.startswith("cuda")

    tok, model, path = build(dev, args.base)

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
    fire_tr = fire_ev = None
    if args.fire_head:
        fire_tr = dict(pmap=fire_pmap(params, "train"), stats=fire_stats())
        fire_ev = dict(pmap=fire_pmap(params, "val"), stats=fire_stats())
    tr = CallDS(data / "train.jsonl", tok, lim_tr, ro=ro_tr, fire=fire_tr)
    ev = CallDS(data / "val.jsonl", tok, lim_ev, ro=ro_ev, fire=fire_ev)
    fire_st = {}
    if args.fire_head:
        fire_st = dict(train=fire_finish(fire_tr["stats"], "cgen/train"),
                       val=fire_finish(fire_ev["stats"], "cgen/val"))
    if args.readonly_env:
        au_tr = readonly_map.audit(ro_tr["labels"], ro_table, where="cgen/train")
        au_ev = readonly_map.audit(ro_ev["labels"], ro_table, where="cgen/val")
        ro_out = dict(
            readonly_env=args.readonly_env,
            table=str(readonly_map.table_path(args.readonly_env)),
            train=au_tr, val=au_ev,
            kept=dict(train=ro_tr["kept"], val=ro_ev["kept"]),
            dropped=dict(train=ro_tr["dropped"], val=ro_ev["dropped"]))
        if args.fire_head:
            # dropped 在开火模式下含义变了:不再是"丢出数据集",而是"不进 LM 损失"
            ro_out["dropped_semantics"] = "fire-head 模式下 = 只当开火头负例,不进 LM 损失"
            ro_out["fire_head"] = fire_st
        (out / "READONLY.json").write_text(json.dumps(
            ro_out, ensure_ascii=False, indent=1))
    mk = lambda ds, sh: DataLoader(
        ds, batch_size=args.bs, shuffle=sh, num_workers=2,
        collate_fn=lambda b: collate(b, tok, args.max_len))
    tr_dl, ev_dl = mk(tr, True), mk(ev, False)
    # 生成评估只在有 LM 目标的行上做(=只读样本),与 --readonly-env 单开时同源
    gen_rows = [r for r in ev.rows if r[5]]
    random.Random(SEED).shuffle(gen_rows)
    gen_rows = gen_rows[:GEN_N]

    # LoRA:就地把底座换成 LoRA 训。开火头(如果有)是新初始化的线性头,照常
    # 全参训练,与适配器一起进优化器。
    lora_wrap = lora_util.wrap(model, args) if args.lora else None
    if args.grad_ckpt:
        model.gradient_checkpointing_enable()
        model.config.use_cache = False
        if args.lora:
            lora_util.prepare_grad_ckpt(model)
    model.train()

    fire = None
    if args.fire_head:
        h = model.config.get_text_config().hidden_size
        fire = torch.nn.Linear(h, 1).to(dev)          # 建在 backbone 之后
    bcef = torch.nn.BCEWithLogitsLoss(reduction="none")
    steps = math.ceil(len(tr_dl) / args.accum) * epochs
    pars = (lora_util.opt_params(model.parameters(), args.lora)
            + (list(fire.parameters()) if fire else []))
    opt = torch.optim.AdamW(pars, lr=lr, weight_decay=0.01)
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
        dropped_train=tr.dropped, dropped_eval=ev.dropped, device=dev,
        readonly_env=args.readonly_env,
        **(dict(fire_head=True, n_gen_lm=len(gen_rows),
                fire_ready_train=fire_st["train"]["frac_ready"],
                fire_ready_val=fire_st["val"]["frac_ready"])
           if args.fire_head else {}),
        **(dict(lora=lora_util.meta_block(args, lr)) if args.lora else {}))
    heartbeat.emit(0, steps, "step")

    best = float("inf")
    gstep = 0
    for ep in range(epochs):
        t0, run = time.time(), 0.0
        for i, (enc, labels, w, ready, lm, plast) in enumerate(tr_dl):
            enc = {k: v.to(dev) for k, v in enc.items()}
            with torch.autocast("cuda", dtype=torch.bfloat16, enabled=amp):
                if fire is None:
                    ce = inst_ce(model, enc, labels, dev)
                else:
                    ce, flg = inst_ce(model, enc, labels, dev, fire, plast)
            wd = w.to(dev)
            if fire is None:
                loss = (ce.float() * wd).sum() / wd.sum()
            else:
                wl = wd * lm.to(dev)          # 只读样本才进 LM 项
                ws = wl.sum()
                # 批内全是非只读样本:LM 项分母为零,整项跳过(不是除零)
                loss = ((ce.float() * wl).sum() / ws if float(ws) > 0
                        else torch.zeros((), device=dev))
                loss = loss + ((bcef(flg.float(), ready.to(dev)) * wd).sum()
                               / wd.sum())
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
                    heartbeat.emit(gstep, steps, "step",
                                   loss=round(run / (50 * args.accum), 4))
                    run = 0.0
        fkw = {}
        if fire is None:
            vce = eval_ce(model, ev_dl, dev, amp)
        else:
            vce, fkw = eval_ce(model, ev_dl, dev, amp, fire)
        vex = eval_gen(model, tok, gen_rows, dev, amp, args.max_len,
                       args.gen_bs)
        log(event="eval", ep=ep, val_ce=round(vce, 4),
            val_exact_call=round(vex, 4), **fkw)
        if vce < best:
            best = vce
            (out / "best").mkdir(parents=True, exist_ok=True)
            if lora_wrap is None:
                model.save_pretrained(out / "best")
            else:
                # 适配器并回底座再落盘:best/ 与全参存的逐项同构,评测端零改动
                lora_util.save_merged(lora_wrap, out / "best", dev)
            tok.save_pretrained(out / "best")
            meta = dict(
                base_path=path, data=str(data), max_len=args.max_len,
                seed=SEED, epoch=ep, call_sep=CALL_SEP,
                transformers=transformers.__version__)
            if args.readonly_env:
                meta["readonly_env"] = args.readonly_env
            if args.lora:
                meta["lora"] = lora_util.meta_block(args, lr)
            if args.grad_ckpt:
                meta["grad_ckpt"] = True
            if fire is not None:
                meta["fire_head"] = True
                torch.save(fire.state_dict(), out / "best" / "fire_head.pt")
            (out / "best" / "meta.json").write_text(json.dumps(meta, indent=1))
            log(event="save_best", ep=ep, val_ce=round(best, 4))
    log(event="done", best_val_ce=round(best, 4))
    heartbeat.emit(gstep, steps, "step", status="done")


if __name__ == "__main__":
    main()
