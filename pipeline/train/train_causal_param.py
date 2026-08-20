"""因果参数生成训练(新流水线 cparam 格):Qwen3-Base 微调成"给定工具名写参数"。

与 cgen(train_causal_callgen.py)的分工:cgen 把工具名和参数一次写完,cparam
把工具名当输入的一部分**喂进去**,模型只写左括号后面那一截。规格见
`plans/2026-08-21-new-probe-training.md` 的第三种。

- 输入: <data_out>/{train,val}.jsonl,每行取 text / label / label_call / w 四个字段;
  一条样本 = 一条训练实例
- 拼串: 输入串 = text + CALL_SEP("\\n[CALL] ") + label + "(" ,
  目标串 = label_call 剥掉前缀 `label + "("` 之后的剩余部分 + eos
  (剩余部分含收尾右括号:`apis.spotify.login(username=x, password=y)` ->
  输入尾巴 `…[CALL] apis.spotify.login(`、目标 `username=x, password=y)`;
  无参调用的目标就是 `)`)
- 目标真源: 拼串的唯一真源是 build.py 的 make_call,所以目标一律从 label_call
  按前缀剥离得到,**不从 args_named 重拼**(重拼 = 第二份拼串规则,必漂移)。
  `label_call.startswith(label + "(")` 不成立的行整条丢弃并计数
  (字段 assembly_mismatch,进 start 日志)
- 防左截吃目标: 与 cgen 同款——先 tokenize 目标(不截断),超 MAX_TGT_TOK 的实例
  整条丢弃并计数;再按 max_length = --max-len - len(tgt_ids) 左截输入串,
  拼接后 labels 把 prompt 段掩成 -100(批内右 padding,pad 位同样 -100)
- 损失: 逐实例目标段 mean CE(ce_i),批损失 = Σ(w_i·ce_i)/Σw_i
- 评估: 每轮 val 全量加权 masked-CE(val_ce,选 best 的唯一依据,越低越好)+
  定种子抽 GEN_N 条 greedy 生成报 val_exact_params(目标段整串命中,只进日志、
  不选 best;对齐 cgen 的 val_exact_call 口径)
- 产物: <out>/best/(HF 权重 + tokenizer + meta.json)+ train_log.jsonl
- LoRA: `--lora` 把底座换成 LoRA 训,存 best 之前先 merge_and_unload 把适配器
  并回底座,所以 best/ 的文件与全参存的逐项同构、eval_causal_param.py 零改动
  就装得回来;meta.json 多一个 "lora" 块记超参。不传 --lora 时脚本自己不碰
  peft(peft 的 import 全在 --lora 分支里),行为与加这套旗标之前一致;
  详见 lora_util.py 的说明。

没有开火头:两套系统对比里触发永远由 ctool 做(规格「使用的时候」节),所以
cgen 那套 `--fire-head` 机制在本格里整套不存在。

用法:
  # 冒烟(500 训练实例/200 评估实例/1 epoch)
  cprobe-env/bin/python pipeline/train/train_causal_param.py \
    --data pipeline/data/aw_official_v1/q35 --out pipeline/runs/c2_q35_cparam --smoke
  # 全量,换 1.7B 底座
  cprobe-env/bin/python pipeline/train/train_causal_param.py --base qwen17 \
    --data pipeline/data/aw_official_v1/q35 --out pipeline/runs/c2_q35_cparam
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
                     "一律从 run.py 的任务进(train-ctool/train-cgen/train-cparam)。")
from torch.utils.data import DataLoader, Dataset
from transformers import (AutoModelForCausalLM, AutoTokenizer,
                          get_linear_schedule_with_warmup)

import lora_util
import readonly_map

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / "ops"))
import heartbeat


# 底座三档(2026-08-21 起因果线从单档扩成三档,样式与 train_causal_tool.MODELS 同)
MODELS = {
    "qwen":   "/net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-0.6B-Base",
    "qwen17": "/net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-1.7B-Base",
    "qwen4":  "/net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-4B-Base",
}
SEED = 20260729
FULL_LR = 1e-5             # 全参微调的学习率(不传 --lora 时的 --lr 默认值)
ASSEMBLY_MISMATCH_LIMIT = 0.05   # 剥离失败率硬停线,对齐 readonly_map.UNKNOWN_HARD_LIMIT
CALL_SEP = "\n[CALL] "
MAX_TGT_TOK = 160          # 目标串 token 上限,超了整条实例丢弃
MAX_GEN_TOK = 96           # 评估生成的 max_new_tokens
GEN_N = 200                # 每轮抽多少条做 greedy 生成


# ---------------------------------------------------------------- 拼串

def param_prompt_tail(label):
    """输入串接在 text 后面的那一截:分隔串 + 工具名 + 左括号。"""
    return CALL_SEP + label + "("


def param_target(label, label_call):
    """(label, label_call) -> 目标串(不含 eos);前缀对不上返回 None。

    唯一拼串真源是 `pipeline/annotate/build.py` 的 make_call:
    label_call = f"{tool}({inner})"。所以目标 = label_call 剥掉 `label + "("`
    之后的整段,收尾右括号留在目标里(无参事件的目标就是 `)`)。
    返回 None 的行由调用方整条丢弃并计入 assembly_mismatch——静默按别的规则
    重拼会造出第二份拼串真源,而那种漂移不报错。
    """
    pre = label + "("
    if not label_call.startswith(pre):
        return None
    return label_call[len(pre):]


# ---------------------------------------------------------------- 数据

class ParamDS(Dataset):
    """一条样本一条实例;构造时先 tokenize 目标串,过长的整条丢弃并计数。

    行结构固定六元组 (text, tgt_ids, w, label, tgt_str, label_call)。
    ro 非 None(--readonly-env)时非只读样本整条丢掉,计数记在 ro 里。
    """

    def __init__(self, path, tok, limit=0, max_tgt=MAX_TGT_TOK, ro=None):
        self.rows, self.dropped, self.mismatch = [], 0, 0
        eos = tok.eos_token_id
        for line in open(path):
            r = json.loads(line)
            if ro is not None:                 # 非只读样本整条丢掉(计数在 ro 里)
                ro["labels"].append(r["label"])
                if r["label"] not in ro["set"]:
                    ro["dropped"] += 1
                    continue
                ro["kept"] += 1
            tgt_str = param_target(r["label"], r["label_call"])
            if tgt_str is None:
                self.mismatch += 1
                continue
            tgt = tok(tgt_str, add_special_tokens=False)["input_ids"] + [eos]
            if len(tgt) > max_tgt:
                self.dropped += 1
                continue
            self.rows.append((r["text"], tgt, float(r["w"]), r["label"],
                              tgt_str, r["label_call"]))
        self.kept = len(self.rows)     # 截 limit 之前的保留数(算剥离失败率用)
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

    prompt = text + CALL_SEP + label + "(" —— 工具名与左括号属于**输入**,
    左截只会吃掉 text 的头部(tokenizer 的 truncation_side 是 left),
    工具名与左括号永远保得住。
    """
    ids, labs, ws = [], [], []
    for text, tgt, w, label, _tgt_str, _call in batch:
        keep = max(max_len - len(tgt), 1)
        prompt = tok(text + param_prompt_tail(label), truncation=True,
                     max_length=keep, add_special_tokens=False)["input_ids"]
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

def build(base, dev):
    """tokenizer 构造照抄 train_causal_callgen.build():pad=eos / 左截 / 右 pad。"""
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
    if w_tot <= 0:
        raise SystemExit(
            "val 一个目标位都没有(加权分母 w_tot=0)——继续算会得到 val_ce=0.0,"
            "每个 epoch 都当 best 存,run 看起来完美。数据或过滤口径有问题,硬停。")
    return s / w_tot


@torch.no_grad()
def eval_gen(model, tok, rows, dev, amp, max_len, bs):
    """定种子抽样的 greedy 生成:目标段整串命中率(遇 \\n 或 eos 停)。"""
    model.eval()
    prev_side, prev_cache = tok.padding_side, model.config.use_cache
    tok.padding_side = "left"                         # 生成必须左 padding
    model.config.use_cache = True
    hit = 0
    for i in range(0, len(rows), bs):
        chunk = rows[i:i + bs]
        enc = tok([r[0] + param_prompt_tail(r[3]) for r in chunk],
                  truncation=True,
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
            hit += (g.split("\n")[0].strip() == r[4])
    tok.padding_side, model.config.use_cache = prev_side, prev_cache
    model.train()
    return hit / max(len(rows), 1)


# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="qwen", choices=sorted(MODELS),
                    help="底座三档:qwen=0.6B(默认)/qwen17=1.7B/qwen4=4B")
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

    tok, model, path = build(args.base, dev)

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
    tr = ParamDS(data / "train.jsonl", tok, lim_tr, ro=ro_tr)
    ev = ParamDS(data / "val.jsonl", tok, lim_ev, ro=ro_ev)
    if args.readonly_env:
        au_tr = readonly_map.audit(ro_tr["labels"], ro_table, where="cparam/train")
        au_ev = readonly_map.audit(ro_ev["labels"], ro_table, where="cparam/val")
        ro_out = dict(
            readonly_env=args.readonly_env,
            table=str(readonly_map.table_path(args.readonly_env)),
            train=au_tr, val=au_ev,
            kept=dict(train=ro_tr["kept"], val=ro_ev["kept"]),
            dropped=dict(train=ro_tr["dropped"], val=ro_ev["dropped"]))
        (out / "READONLY.json").write_text(json.dumps(
            ro_out, ensure_ascii=False, indent=1))
    # 保险丝:val 装载后 0 行硬停。空 val 不会在训练里崩(SequentialSampler 不拦空),
    # 只会让 val_ce 恒 0、每个 epoch 都存 best,run 看起来完美。
    if not len(ev):
        raise SystemExit(
            f"{data / 'val.jsonl'} 装载后 val 是 0 行"
            f"(dropped={ev.dropped}, assembly_mismatch={ev.mismatch}"
            + (f", readonly_dropped={ro_ev['dropped']}" if ro_ev else "")
            + ")——选 best 的指标没有分母,硬停。")
    # 保险丝:剥离失败率超限硬停。label 与 label_call 前缀对不上通常是上游拼串
    # 口径变了,继续训会静默吞样本;5% 对齐 readonly_map.UNKNOWN_HARD_LIMIT 先例。
    for split, ds in (("train", tr), ("val", ev)):
        tot = ds.kept + ds.mismatch
        if tot and ds.mismatch / tot > ASSEMBLY_MISMATCH_LIMIT:
            raise SystemExit(
                f"{split} 的剥离失败率 {ds.mismatch}/{tot} = "
                f"{ds.mismatch / tot:.3f} 超过 {ASSEMBLY_MISMATCH_LIMIT}——"
                "上游拼串口径漂移,硬停。")
    mk = lambda ds, sh: DataLoader(
        ds, batch_size=args.bs, shuffle=sh, num_workers=2,
        collate_fn=lambda b: collate(b, tok, args.max_len))
    tr_dl, ev_dl = mk(tr, True), mk(ev, False)
    gen_rows = list(ev.rows)
    random.Random(SEED).shuffle(gen_rows)
    gen_rows = gen_rows[:GEN_N]

    # LoRA:就地把底座换成 LoRA 训。本格没有额外的头,进优化器的就只有适配器。
    lora_wrap = lora_util.wrap(model, args) if args.lora else None
    if args.grad_ckpt:
        model.gradient_checkpointing_enable()
        model.config.use_cache = False
        if args.lora:
            lora_util.prepare_grad_ckpt(model)
    model.train()

    steps = math.ceil(len(tr_dl) / args.accum) * epochs
    opt = torch.optim.AdamW(lora_util.opt_params(model.parameters(), args.lora),
                            lr=lr, weight_decay=0.01)
    sch = get_linear_schedule_with_warmup(opt, int(steps * 0.05), steps)

    logf = open(out / "train_log.jsonl", "a")

    def log(**kw):
        kw["t"] = round(time.time(), 1)
        logf.write(json.dumps(kw) + "\n")
        logf.flush()
        print(kw, flush=True)

    log(event="start", base=args.base, base_path=path, env=args.env,
        n_train=len(tr), n_eval=len(ev), n_gen=len(gen_rows), steps=steps,
        smoke=args.smoke, max_len=args.max_len, max_tgt_tok=MAX_TGT_TOK,
        seed=SEED, dropped_train=tr.dropped, dropped_eval=ev.dropped,
        assembly_mismatch=dict(train=tr.mismatch, val=ev.mismatch),
        device=dev, readonly_env=args.readonly_env, param_only=True,
        **(dict(lora=lora_util.meta_block(args, lr)) if args.lora else {}))
    heartbeat.emit(0, steps, "step")

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
                    heartbeat.emit(gstep, steps, "step",
                                   loss=round(run / (50 * args.accum), 4))
                    run = 0.0
        vce = eval_ce(model, ev_dl, dev, amp)
        vex = eval_gen(model, tok, gen_rows, dev, amp, args.max_len,
                       args.gen_bs)
        log(event="eval", ep=ep, val_ce=round(vce, 4),
            val_exact_params=round(vex, 4))
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
                base=args.base, base_path=path, data=str(data),
                max_len=args.max_len, seed=SEED, epoch=ep, call_sep=CALL_SEP,
                param_only=True, transformers=transformers.__version__,
                assembly_mismatch=dict(train=tr.mismatch, val=ev.mismatch))
            if args.readonly_env:
                meta["readonly_env"] = args.readonly_env
            if args.lora:
                meta["lora"] = lora_util.meta_block(args, lr)
            if args.grad_ckpt:
                meta["grad_ckpt"] = True
            (out / "best" / "meta.json").write_text(json.dumps(meta, indent=1))
            log(event="save_best", ep=ep, val_ce=round(best, 4))
    log(event="done", best_val_ce=round(best, 4))
    heartbeat.emit(gstep, steps, "step", status="done")


if __name__ == "__main__":
    main()
