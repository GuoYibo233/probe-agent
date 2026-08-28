"""因果缓存复用训练器(新流水线 cgen / cparam 共用格,`--mode` 选一个):
一个事件的全文只过一遍底座,每个切点的目标段接在共享的前缀后面算损失。

与旧的逐行训练器(`train_causal_callgen.py` / `train_causal_param.py`)的关系:
旧脚本每一行各自成一次前向(prompt 从头分词、右 padding);本脚本把同一个
事件的全部行打包成一条序列一次前向(形态 A,`design-attention.md` 已验证),
理论上逐行 loss 与旧训练器逐 token 相同(第 9 节的对齐检查就是验这件事),
只是省掉了同一段前缀在多行之间的重复计算。

- 数据与分词:`pipeline/train/share_data.py`(纯 CPU,cgen/cparam 共用一套
  `load_events`/`pack_event`/`batch_mask`/`chunk_by_budget`/`worst_blocks`)。
- tokenizer 与模型:直接调用旧脚本 `train_causal_callgen.build(dev, base,
  attn_impl=, path=)`(spec 3.4,决定 6;`--base` 是 qwen/qwen17/qwen4 或者
  一个模型目录路径,后者走 `build(path=...)`,给小模型测试用)。
- 前向形态:`design-attention.md` 的形态 A——多事件沿批维摆,每个物理块一张
  bf16(或 fp32,对齐检查用)加性掩码,`attn_implementation="sdpa"` 且训练/
  评估/对齐检查三处前向在 cuda 上都套 `sdpa_kernel([SDPBackend.
  EFFICIENT_ATTENTION])`(CPU 上这个上下文对 CPU 内核不起作用,跳过)。
  只在损失位取隐状态过 `lm_head`,不算全位置 logits。
- 损失与更新单位:逻辑小批 = `--events-per-mb`(默认 4)个事件的全部行,按
  token 预算拆物理块,一次更新 = `--accum`(默认 2)个逻辑小批 = 8 个事件。
- 对齐检查(第 9 节):开训前(以及 `--align-only`)、`lora_util.wrap` 之前、
  `model.eval()` 下,fp32 关 TF32,抽 `--align-events` 个 val 短事件,同一份
  临时 jsonl 喂新路径(`share_data.load_events`)与参照路径(旧 `collate` +
  真正调用的 `inst_ce` 得到逐行 ce;逐 token 门槛需要的中间量另用同一套
  公式本地算,fp32 门禁那两遍每批都断言与 `inst_ce` 的返回值一致,bf16
  粗筛那一遍关掉这道自检,工单 05 S2),按位置配对逐行/逐
  token 比较。参照路径不套 EFFICIENT_ATTENTION(它的『单行不补齐』批没有
  掩码,HF 会走 `enable_gqa`,mem-efficient 不支持 GQA,强制内核会报错——
  只有永远带掩码的新路径套这个上下文)。

用法:
  # 只过对齐检查
  cprobe-env/bin/python pipeline/train/train_causal_share.py --mode cgen \
    --data pipeline/data/nyapass_aw_v1/gptoss --out pipeline/runs/x --align-only
  # 冒烟
  cprobe-env/bin/python pipeline/train/train_causal_share.py --mode cparam \
    --data pipeline/data/nyapass_aw_v1/gptoss --out pipeline/runs/smoke/x_smoke --smoke
"""

import argparse
import contextlib
import json
import math
import random
import sys
import tempfile
import time
from pathlib import Path

import torch
import torch.nn.functional as F
import transformers
_TV = tuple(int(x) for x in transformers.__version__.split(".")[:2])
if _TV < (5, 14):
    raise SystemExit(f"cprobe 线要 transformers>=5.14,当前 "
                     f"{transformers.__version__}——解释器用错了?"
                     "一律从 run.py 的任务进(train-cgen/train-cparam)。")
from torch.nn.attention import sdpa_kernel, SDPBackend
from transformers import get_linear_schedule_with_warmup

import lora_util
import readonly_map
import share_data
import train_causal_callgen
import train_causal_param

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / "ops"))
import heartbeat


# spec 第 9 节:只抽全文 token 数不超过这个上限的事件做对齐检查(控制耗时)。
ALIGN_LEN_FILTER = 2048
# 参照路径『整批』的行数,照旧训练器的 --bs 4(spec 第 9 节)。
REF_BATCH = 4
# `_ref_forward` 本地逐 token 公式聚合出的逐行结果,与真正调用 `inst_ce`
# 的返回值之间允许的最大差(同一批数据同一次 no_grad 前向调两遍,理论上
# bit 级相同;留这道容差只是防浮点求和顺序在不同内核调度下的极小抖动,
# 比 --align-tol 的 2e-5 低一个量级,离真正的公式错位(1e-2 量级)还差
# 1000 倍,不会把结构性错位放过)。
REF_INST_CE_DRIFT_TOL = 1e-6


class RefBaselineDriftError(RuntimeError):
    """`_ref_forward` 的自检失败:本地逐 token 公式聚合出的逐行结果与真正
    调用 `inst_ce` 的返回值超出 `REF_INST_CE_DRIFT_TOL`,说明参照基线本身
    不可信。用真异常而不是裸 `assert`,是因为裸 `assert` 在 `-O`/
    `PYTHONOPTIMIZE` 下会被整体剥除、静默放行——这道检查是本文件里唯一
    判定『参照基线是否可信』的运行时校验,不能有静默失效的路径。
    `run_align_check` 捕获这个异常后按文件里其余所有失败分支同样的模式
    处理:写 `ALIGN_CHECK.json`、打印诊断、`sys.exit(2)`。"""


# ---------------------------------------------------------------- 前向形态

def _attn_ctx(dev):
    """cuda 上钉死 mem-efficient(design-attention.md 第三节的裁决);CPU 上这个
    上下文会抛 `No viable backend`,跳过,走默认内核(spec 第 4 节)。"""
    if str(dev).startswith("cuda"):
        return sdpa_kernel([SDPBackend.EFFICIENT_ATTENTION])
    return contextlib.nullcontext()


def _l_pad(events):
    """一组事件的物理块补齐长度:块内最长 `packed_len` 补到 16 的倍数,和
    `share_data.batch_mask`/`chunk_by_budget` 的补齐同口径(spec 第 4、5 节)。"""
    longest = max(ev["packed_len"] for ev in events)
    return ((longest + 15) // 16) * 16


def _base_model_and_head(model):
    """`model.model` 与 `model.lm_head` 的取法,兼容 peft 的包装对象(工单
    05 S1)。`lora_util.wrap` 是就地注入——调用方原来的 hf_model 变量本身
    在包装之后还是原始模型,直接有 `.model`/`.lm_head`;这里额外兼容『拿到
    手的就是 PeftModel 本身』的调用方式,`get_base_model()` 拆到底座上原始
    的 backbone / lm_head(peft 只替换了七件套 nn.Linear,不改这层结构)。"""
    base = model.get_base_model() if hasattr(model, "get_base_model") else model
    return base.model, base.lm_head


def _forward_packed(model, events, dev, mask_dtype):
    """一个物理块(`events`)的前向:调 `model.model(...)` 直接拿 backbone 的
    `last_hidden_state`(旧写法是让上层 `ForCausalLM.forward` 把每一层的
    隐状态都吐出来、再取元组最后一个——那条路靠 HF 往元组末尾追加末层的
    约定,并且 `--grad-ckpt` 下会把 28 层的隐状态全记下来,16k token 的块
    约 1.9 GB),按损失位 gather 出来再过 `model.lm_head`(spec 第 4 节),
    不算全位置 logits(工单 05 S1)。

    返回 `(tok_ce [n_tgt] 张量(on dev), global_row [n_tgt] list, n_rows_total
    int)`——`global_row[i]` 是 `tok_ce[i]` 对应的目标 token 在这个物理块里的
    全局行号(跨事件累加,事件 0 的行在前、事件 1 的行接着数,以此类推)。
    """
    packed = [share_data.pack_event(ev) for ev in events]
    l_pad = _l_pad(events)
    input_ids, position_ids, mask, loss_idx = share_data.batch_mask(packed, l_pad)
    input_ids = input_ids.to(dev)
    position_ids = position_ids.to(dev)
    mask = mask.to(dev).to(dtype=mask_dtype)
    backbone, lm_head = _base_model_and_head(model)
    with _attn_ctx(dev):
        out = backbone(input_ids=input_ids, attention_mask=mask,
                       position_ids=position_ids, use_cache=False)
    h = out.last_hidden_state
    bidx = torch.tensor([x[0] for x in loss_idx], device=dev)
    qidx = torch.tensor([x[1] for x in loss_idx], device=dev)
    ys = torch.tensor([x[2] for x in loss_idx], device=dev)
    offsets, acc = [], 0
    for ev in events:
        offsets.append(acc)
        acc += len(ev["rows"])
    global_row = [offsets[b] + x[3] for b, x in zip(bidx.tolist(), loss_idx)]
    hp = h[bidx, qidx].float()
    logits = lm_head(hp).float()
    ce = F.cross_entropy(logits, ys, reduction="none")
    return ce, global_row, acc


def _aggregate_rows(tok_ce, global_row, n_rows, dev):
    """逐 token CE -> 每行 mean CE(`inst_ce` 同一口径:本段目标 token 位置上
    的交叉熵求平均,分母是本行目标 token 数,spec 第 4 节末段)。"""
    rid = torch.tensor(global_row, device=dev)
    ssum = torch.zeros(n_rows, device=dev).index_add(0, rid, tok_ce)
    cnt = torch.zeros(n_rows, device=dev).index_add(0, rid, torch.ones_like(tok_ce))
    return ssum / cnt.clamp(min=1)


def block_row_ce(model, events, dev, mask_dtype):
    """一个物理块每行的 mean CE 与该行的权重 w(训练/评估的基本单位)。"""
    tok_ce, global_row, n_rows = _forward_packed(model, events, dev, mask_dtype)
    ce_per_row = _aggregate_rows(tok_ce, global_row, n_rows, dev)
    w = torch.tensor([row[5] for ev in events for row in ev["rows"]],
                     dtype=torch.float32, device=dev)
    return ce_per_row, w


def backward_logical_minibatch(model, blocks, W, n_g, dev, mask_dtype, amp=False):
    """一个逻辑小批的反向(spec 第 5 节):`blocks` 是已经按 token 预算切好的
    物理块列表(每块是事件列表)。`W` 是整个逻辑小批的行权重和(不是单个物理
    块自己的),`n_g` 是这一组(--accum 个逻辑小批)里实际的逻辑小批数。

    `torch.autocast` 只包前向(`block_row_ce`),`.backward()` 在外面(照旧
    训练器 `train_causal_callgen.py` 第 489 到 505 行的形状,工单 05 S3)——
    反向按前向留下的 dtype 走,不受调用时是否处在 autocast 上下文里影响,
    把 `.backward()` 也套进 autocast 没有意义。

    m 个物理块的梯度之和等于把整个逻辑小批一次算完的梯度——这条性质与
    `blocks` 具体怎么切无关,只要 `W` 与 `n_g` 不变(测试 12(b) 验的就是这条)。

    返回 `(logical_minibatch_loss, n_rows)`:前者是这个逻辑小批的标量 loss
    (供 step 日志的『loss』累加),后者是它的总行数。
    """
    total = 0.0
    n_rows = 0
    for blk in blocks:
        with torch.autocast("cuda", dtype=torch.bfloat16, enabled=amp):
            ce_per_row, w = block_row_ce(model, blk, dev, mask_dtype)
        loss_c = (ce_per_row * w).sum() / W
        (loss_c / n_g).backward()
        total += loss_c.item()
        n_rows += ce_per_row.numel()
    return total, n_rows


@torch.no_grad()
def eval_ce(model, events, tok_budget, dev, amp, beat=None):
    """val 全量加权 masked-CE(与训练损失同口径,spec 第 6 节)。

    `beat`(工单 08,spec 16.3 倒数第二条):可选的无参回调,块循环里每 25
    个物理块调一次——全量 val(115,211 行)加生成式评估的窗口里现在没有
    任何心跳,采样器按 5 x 典型心跳间隔判停滞会误报,`beat` 让调用方
    (main 的 `heartbeat.emit`)在这个窗口里刷新时间戳。`beat=None` 时
    跳过,不影响现有调用点。
    """
    model.eval()
    mask_dtype = torch.bfloat16 if amp else torch.float32
    blocks = share_data.chunk_by_budget(events, tok_budget)
    s = w_tot = 0.0
    with torch.autocast("cuda", dtype=torch.bfloat16, enabled=amp):
        for i, blk in enumerate(blocks):
            ce_per_row, w = block_row_ce(model, blk, dev, mask_dtype)
            s += (ce_per_row.float() * w).sum().item()
            w_tot += w.sum().item()
            if beat is not None and (i + 1) % 25 == 0:
                beat()
    model.train()
    if w_tot <= 0:
        raise SystemExit(
            "val 一个目标位都没有(加权分母 w_tot=0)——继续算会得到 val_ce=0.0,"
            "每个 epoch 都当 best 存,run 看起来完美。数据或过滤口径有问题,硬停。")
    return s / w_tot


def sample_gen_eval_rows(events, mode, seed, n):
    """`--gen-eval` 的抽样(工单 08,spec 16.3):`events`(`share_data.
    load_events` 的返回值,通常是 val 集)按事件加载顺序、行按事件内
    `sent_idx` 顺序摊平成行列表(不过滤——share_data 的行全部有目标),
    `random.Random(seed).shuffle` 后取前 `n` 行(`n` 大于行数就全取)。

    定种子的纯函数:同一份 `events` 两次调用结果相同(spec 16.9 (b))。

    返回值按 `mode` 打包成两个旧脚本 `eval_gen` 要的元组形状(`tgt`/`tool`
    来自行元组第 6 位的 `gen` 字典,`share_data.load_events` 第 205 行):
    cgen `(text, None, None, tgt)`,cparam `(text, None, None, tool, tgt)`。
    """
    flat = [row for ev in events for row in ev["rows"]]
    rng = random.Random(seed)
    rng.shuffle(flat)
    picked = flat[:n] if n > 0 else []
    if mode == "cgen":
        return [(row[1], None, None, row[6]["tgt"]) for row in picked]
    return [(row[1], None, None, row[6]["tool"], row[6]["tgt"]) for row in picked]


# ---------------------------------------------------------------- 显存探针

def run_mem_probe(model, opt, full_events, args, dev, log, amp):
    """spec 第 10 节:训练开始前踩真实最坏情况的显存(工单 06)。

    机理(8-28-assistant-2 判读):训练的真峰在 accum=2 的第二个逻辑小批
    反向期间——此时优化器状态(AdamW 的两份 fp32 状态,来自上一个 step)
    与第一个逻辑小批留下的梯度都还在。这里复现同样的条件:优化器状态
    先建好、最满块连做两次前向加反向(中间不清梯度,即梯度累积),第二次
    反向后读峰值;最长事件那一块紧接着做,状态已建、梯度未清的条件不变,
    再做一次前向加反向读峰值。最后清优化器状态、恢复 lr、清梯度。

    建状态要点:AdamW 的 `step()` 只给 `.grad is not None` 的参数分配状态,
    一个从没做过反向的模型全体 `.grad` 都是 None,直接 `zero_grad` 接
    `step(lr=0)` 建不出任何状态(本仓 `cprobe-env` 的 torch 2.11.0+cu128 上
    实测过:`opt.state` 事后是空字典 `{}`,零个 key)。根因不是"建状态这
    一步前面要不要插一次前向反向",而是 `.grad` 需要先有真实形状的张量——
    AdamW 分配状态只看 `.grad is not None` 与参数的形状/dtype,不看梯度
    数值,所以直接给每个可训练参数的 `.grad` 赋 `torch.zeros_like(p)` 就
    够,不必为此另跑一次前向反向。顺序严格按工单字面写:先把每个可训练
    参数的 `.grad` 置成零张量,`zero_grad(set_to_none=False)` 保留张量、
    清零数值(此时已经是零,等价于空操作,但按字面留着这一步调用);再用
    lr=0 的 `opt.step()`,AdamW 才会真正给每个参数分配
    exp_avg/exp_avg_sq(`optimizer_state_prebuilt`),参数值不动(lr=0);
    `reset_peak_memory_stats()` 在这之后;然后才对最满块连做两次前向加
    反向——建状态这一步之前不发生任何前向或反向。
    """
    mask_dtype = torch.bfloat16 if amp else torch.float32
    longest, fullest = share_data.worst_blocks(
        full_events, args.tok_budget, args.events_per_mb)

    def _fwd_bwd(grp):
        with torch.autocast("cuda", dtype=torch.bfloat16, enabled=amp):
            ce_per_row, w = block_row_ce(model, grp, dev, mask_dtype)
            loss = (ce_per_row * w).sum() / w.sum().clamp(min=1e-9)
        loss.backward()

    orig_lrs = [g["lr"] for g in opt.param_groups]
    for g in opt.param_groups:
        for p in g["params"]:
            p.grad = torch.zeros_like(p)       # 建状态用,不来自任何前向反向
    opt.zero_grad(set_to_none=False)
    for g in opt.param_groups:
        g["lr"] = 0.0
    opt.step()                                 # 优化器状态就此分配,参数不动
    if dev.startswith("cuda"):
        torch.cuda.reset_peak_memory_stats()

    for kind, grp, n_backward in (("fullest_block", fullest, 2),
                                  ("longest_event", longest, 1)):
        if not grp:
            continue
        if dev.startswith("cuda"):
            # 每块各自归零峰值计数器(归到当前已分配:权重 + 梯度 + 状态,三样照留),
            # 否则第二块记的是两块的最大值(assistant-2 复核 907d143 提出)
            torch.cuda.reset_peak_memory_stats()
        for _ in range(n_backward):
            _fwd_bwd(grp)                      # 中间不 zero_grad,梯度累积
        peak = (torch.cuda.max_memory_allocated() / 1e9
               if dev.startswith("cuda") else 0.0)
        b = len(grp)
        l_pad = _l_pad(grp)
        log(event="mem_probe", kind=kind, n_events=b, packed_len_max=l_pad,
            peak_mem_gb=round(peak, 3), B=b, L_pad=l_pad,
            with_optimizer_state=True, n_backward=n_backward,
            optimizer_state_prebuilt=True)

    opt.state.clear()
    for g, lr0 in zip(opt.param_groups, orig_lrs):
        g["lr"] = lr0
    opt.zero_grad(set_to_none=True)


# ---------------------------------------------------------------- 对齐检查

def _align_candidates(path, tok, seed, n, max_len):
    """spec 第 9 节:随机抽 `n` 个只有全文 token 数 <= `min(ALIGN_LEN_FILTER,
    max_len)` 的 val 事件——上限还要卡 `--max-len`,否则 `--max-len < 2048`
    时新路径(`share_data.load_events` 按 `--max-len` 丢整条事件)比参照路径
    (`CallDS`/`ParamDS` 不按这个上限丢)多丢几个抽中的事件,两条路径的总行
    数就对不上,第 9 节的配对断言直接 `exit(2)`(工单 05 S5)。独立于
    `share_data.load_events` 的行级流水线(只做按 event 分组 + 全文分词),
    避免为了抽样跑一遍全量行级分词——`--smoke` 时那笔开销与抽样目的不成
    比例。"""
    groups, order = {}, []
    for line in open(path):
        r = json.loads(line)
        ev = r["event"]
        if ev not in groups:
            groups[ev] = []
            order.append(ev)
        groups[ev].append(r)
    len_filter = min(ALIGN_LEN_FILTER, max_len)
    cands = []
    for ev in order:
        rs = sorted(groups[ev], key=lambda r: r["sent_idx"])
        full_text = rs[-1]["text"]
        n_full = len(tok(full_text, add_special_tokens=False,
                         truncation=False)["input_ids"])
        if n_full <= len_filter:
            cands.append(rs)
    rng = random.Random(seed)
    return rng.sample(cands, min(n, len(cands)))


def _write_align_tmpfile(picked):
    """把抽中事件的全部原始行按 `(event, sent_idx)` 升序写进一个临时 jsonl
    (spec 第 9 节)。同一份文件喂新路径与参照路径,两条路径看到的行序天然
    一致,配对按位置比较才有意义。"""
    rows = [r for rs in picked for r in rs]
    rows.sort(key=lambda r: (r["event"], r["sent_idx"]))
    fd, path = tempfile.mkstemp(suffix=".jsonl", prefix="kvshare_align_")
    with open(fd, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return path


def _ref_forward(mode, model, tok, rows, dev, max_len, bs, check_drift=True):
    """参照路径:旧 `collate`,`bs` 行一批右 padding,过同一个模型。

    每行 ce 直接来自调用旧脚本的 `inst_ce`(`train_causal_callgen.py`/
    `train_causal_param.py`,spec 第 9 节字面要求的『import collate、
    inst_ce...得到每行 ce』)——`row_ce` 就是 `inst_ce` 的返回值,不是另一套
    同公式的手写替代。`inst_ce` 本身只回每行 mean CE,不暴露逐 token 的
    中间量,而 spec 同一节还要求逐 token 最大差门槛,所以本函数另外用与
    `inst_ce` 完全相同的公式(移位预测、只在目标位取 CE)本地算一份逐
    token CE 供 `tok_ce` 用,并在每一批上把这份本地公式聚合出的逐行结果
    与真正调用 `inst_ce` 的返回值断言一致(`REF_INST_CE_DRIFT_TOL`)——
    不一致就抛 `RefBaselineDriftError`(真异常,不是裸 `assert`,不会被
    `-O`/`PYTHONOPTIMIZE` 剥除),由 `run_align_check` 捕获后按文件里其余
    所有失败分支同样的模式处理(写 `ALIGN_CHECK.json`、打印诊断、
    `sys.exit(2)`),不会把一个未经验证的手写公式悄悄当成对齐检查的基准。
    `bs=4` 是『整批』,`bs=1` 是补齐基线的『单行』(spec:
    两者都用旧训练器的口径,只是分批大小不同)。参照路径不套
    EFFICIENT_ATTENTION,用默认内核选择(design-attention.md 7.1 节:『单行
    不补齐』批没有掩码,HF 会跳过建掩码并开 enable_gqa,mem-efficient 不
    支持 GQA,强制内核会报错)。

    `check_drift`(工单 05 S2):True(默认)时做上面这道自检——fp32 的两遍
    调用(REF_BATCH 整批、bs=1 单行基线)都留着,容差 `REF_INST_CE_DRIFT_TOL`,
    同一次 no_grad 前向理论上该一致;bf16 粗筛那一遍传 False 关掉自检——
    bf16 下比的是两次独立前向的 bf16 结果,GPU 内核只要抖过这个为 fp32 定
    的量级就会误报 `RefBaselineDriftError` 挡住开训,而 bf16 粗筛本来就
    只用 `row_ce`(`inst_ce_fn` 的返回值),不需要这道自检。

    返回 `(row_ce list, tok_ce list)`,行序/token 序 = `rows` 的输入顺序。
    """
    collate_fn = (train_causal_callgen.collate if mode == "cgen"
                 else train_causal_param.collate)
    inst_ce_fn = (train_causal_callgen.inst_ce if mode == "cgen"
                 else train_causal_param.inst_ce)
    row_ce, tok_ce = [], []
    for i in range(0, len(rows), bs):
        chunk = rows[i:i + bs]
        enc, labels = collate_fn(chunk, tok, max_len)[:2]
        enc = {k: v.to(dev) for k, v in enc.items()}
        out = model(input_ids=enc["input_ids"], attention_mask=enc["attention_mask"],
                    use_cache=False)
        lg = out.logits[:, :-1].float()
        tg = labels[:, 1:].to(dev)
        m = tg != -100
        ce = F.cross_entropy(lg[m], tg[m], reduction="none")
        b = tg.size(0)
        rid = torch.arange(b, device=dev).unsqueeze(1).expand_as(tg)[m]
        # `out`/`lg` 是这一批 [B, L, V] fp32 全位置 logits(约 5.1 GB),后面
        # 只用得到已经从它们抽出来的 `ce`/`rid`;调 `inst_ce_fn`(它自己会
        # 再算一遍前向)之前先释放,不然两份都活着瞬时约 10 GB(工单 05 S6)。
        del out, lg
        if check_drift:
            ssum = torch.zeros(b, device=dev).index_add(0, rid, ce)
            cnt = torch.zeros(b, device=dev).index_add(0, rid, torch.ones_like(ce))
            row_ce_local = ssum / cnt.clamp(min=1)

        row_ce_inst = inst_ce_fn(model, enc, labels, dev).float()
        if check_drift:
            drift = (row_ce_local - row_ce_inst).abs().max().item()
            if drift > REF_INST_CE_DRIFT_TOL:
                raise RefBaselineDriftError(
                    f"_ref_forward 本地逐 token 公式聚合出的逐行结果与真正调用 "
                    f"inst_ce 的返回值不一致(max diff {drift} > "
                    f"{REF_INST_CE_DRIFT_TOL},mode={mode}):对齐检查的参照基线"
                    "不可信,先查两套公式的差异再继续。")

        row_ce.extend(row_ce_inst.tolist())
        tok_ce.extend(ce.tolist())
    return row_ce, tok_ce


def _new_forward(events, model, dev, mask_dtype):
    """新路径,fp32(或 bf16 粗筛用):逐事件单独一次前向(align_events 数量
    小,不必按 token 预算装块),行序/token 序 = `events` 展开顺序,与参照
    路径共用同一份按 `(event, sent_idx)` 排序的临时文件,行序天然一致。"""
    row_ce, tok_ce = [], []
    for ev in events:
        tok_c, global_row, n_rows = _forward_packed(model, [ev], dev, mask_dtype)
        ce_per_row = _aggregate_rows(tok_c, global_row, n_rows, dev)
        row_ce.extend(ce_per_row.tolist())
        tok_ce.extend(tok_c.tolist())
    return row_ce, tok_ce


def run_align_check(model, tok, args, dev, mode, ro_set):
    """spec 第 9 节:开训前(以及 `--align-only`)的对齐检查。调用方要保证
    在 `lora_util.wrap` 之前调用,函数内部自己做 `model.eval()`/`model.train()`
    切换与 fp32 精度设置的保存/恢复。不通过时把报告写进 ALIGN_CHECK.json
    再 `sys.exit(2)`(照 ctool 的做法)。"""
    data = Path(args.data)
    out = Path(args.out)
    model.eval()
    prev_prec = torch.get_float32_matmul_precision()
    prev_tf32_mm = torch.backends.cuda.matmul.allow_tf32
    prev_tf32_cudnn = torch.backends.cudnn.allow_tf32
    torch.set_float32_matmul_precision("highest")
    if dev.startswith("cuda"):
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
    tmp_path = None
    try:
        picked = _align_candidates(data / "val.jsonl", tok,
                                   train_causal_callgen.SEED, args.align_events,
                                   args.max_len)
        tmp_path = _write_align_tmpfile(picked)

        ro_new = (dict(set=ro_set, labels=[], kept=0, dropped=0)
                 if ro_set is not None else None)
        ro_ref = (dict(set=ro_set, labels=[], kept=0, dropped=0)
                 if ro_set is not None else None)

        with torch.no_grad():
            new_events, new_counts = share_data.load_events(
                tmp_path, tok, mode, args.max_len, ro=ro_new, limit=0)

            OldDS = (train_causal_callgen.CallDS if mode == "cgen"
                    else train_causal_param.ParamDS)
            ds = OldDS(tmp_path, tok, limit=0, ro=ro_ref)

            n_new_rows = sum(len(ev["rows"]) for ev in new_events)
            new_texts = [row[1] for ev in new_events for row in ev["rows"]]
            mismatch_idx = []
            if len(ds.rows) != n_new_rows:
                mismatch_idx = [-1]        # 总行数不等,逐位比较没有意义
            else:
                mismatch_idx = [i for i, (r, t) in
                                enumerate(zip(ds.rows, new_texts)) if r[0] != t]
            drop_ok = (ds.dropped == new_counts["dropped_rows_tgt"])
            mismatch_ok = (mode != "cparam"
                          or ds.mismatch == new_counts["assembly_mismatch"])

            row_ref, tok_ref = _ref_forward(mode, model, tok, ds.rows, dev,
                                            args.max_len, REF_BATCH)
            row_ref_solo, _tok_ref_solo = _ref_forward(
                mode, model, tok, ds.rows, dev, args.max_len, 1)
            row_new, tok_new = _new_forward(new_events, model, dev, torch.float32)

            n_rows = len(row_ref)
            n_tgt = len(tok_ref)
            row_diff = max((abs(a - b) for a, b in zip(row_new, row_ref)),
                          default=0.0)
            tok_diff = max((abs(a - b) for a, b in zip(tok_new, tok_ref)),
                          default=0.0)
            baseline_diff = max((abs(a - b) for a, b in
                                zip(row_ref_solo, row_ref)), default=0.0)
            hard_ok = (not mismatch_idx) and drop_ok and mismatch_ok
            abs_ok = (row_diff <= args.align_tol
                     and tok_diff <= args.align_tok_tol)
            # spec 9:相对判据用参照路径逐行 ce 绝对值的『整体一个平均数』当
            # 分母,不是逐行各除各的 ce——ce 接近 0 的行会让逐行相对差发散。
            ref_scale = (sum(abs(x) for x in row_ref) / len(row_ref)
                        if row_ref else 0.0)
            if ref_scale == 0:
                rel_max_abs_diff = None
                rel_ok = False
            else:
                rel_max_abs_diff = row_diff / ref_scale
                rel_ok = rel_max_abs_diff <= args.align_rel_tol
            if args.align_rule == "abs":
                rule_ok = abs_ok
            elif args.align_rule == "rel":
                rule_ok = rel_ok
            else:
                rule_ok = abs_ok and rel_ok
            pass_ok = hard_ok and rule_ok
            baseline_warn = row_diff > max(
                args.align_baseline_factor * baseline_diff, 1e-6)

            bf16_mean = bf16_max = None
            bf16_warn = False
            if dev.startswith("cuda"):
                with torch.autocast("cuda", dtype=torch.bfloat16):
                    row_new_bf16, _ = _new_forward(new_events, model, dev,
                                                   torch.bfloat16)
                    row_ref_bf16, _ = _ref_forward(mode, model, tok, ds.rows,
                                                   dev, args.max_len, REF_BATCH,
                                                   check_drift=False)
                diffs = [abs(a - b) for a, b in zip(row_new_bf16, row_ref_bf16)]
                bf16_mean = sum(diffs) / max(len(diffs), 1)
                bf16_max = max(diffs, default=0.0)
                bf16_warn = bool(bf16_mean > args.align_bf16_mean_tol
                                 or bf16_max > args.align_bf16_max_tol)

            # `bf16_warn` 不在 spec 第 9 节的落盘字段列表里(`align_bf16_warn`
            # 已经在 `start` 事件里报过一次),所以不写进 ALIGN_CHECK.json;
            # 只在函数返回值里额外带一份给 main() 记 `start` 事件用
            # (工单 05 F2/工单 03 minor)。
            report = dict(
                PASS=bool(pass_ok), n_events=len(new_events), n_rows=n_rows,
                n_tgt_tokens=n_tgt, max_abs_diff=row_diff, max_tok_diff=tok_diff,
                baseline_max_abs_diff=baseline_diff, tol=args.align_tol,
                bf16_mean_abs_diff=bf16_mean, bf16_max_abs_diff=bf16_max,
                attn_impl=args.attn_impl, mismatch_idx=mismatch_idx,
                baseline_warn=bool(baseline_warn),
                rule=args.align_rule, tok_tol=args.align_tok_tol,
                rel_tol=args.align_rel_tol, ref_scale=ref_scale,
                rel_max_abs_diff=rel_max_abs_diff,
                bf16_mean_tol=args.align_bf16_mean_tol,
                bf16_max_tol=args.align_bf16_max_tol,
                baseline_factor=args.align_baseline_factor)
            (out / "ALIGN_CHECK.json").write_text(
                json.dumps(report, indent=1, ensure_ascii=False))
            print(json.dumps(report, indent=1), flush=True)
            if not report["PASS"]:
                msg_lines = [
                    "对齐检查 FAIL:形态 A 与旧训练器逐行 loss 不一致,拒绝开训。",
                    f"  规则 --align-rule {args.align_rule}",
                    f"  逐行最大差 {row_diff:.3e}(tol {args.align_tol:.1e}),"
                    f"逐 token 最大差 {tok_diff:.3e}(tol {args.align_tok_tol:.1e})",
                ]
                if args.align_rule in ("rel", "both"):
                    if ref_scale == 0:
                        msg_lines.append(
                            "  ref_scale 为 0(参照路径逐行 ce 绝对值均值为 0),"
                            "rel_max_abs_diff 记为 null,rel 规则判失败。")
                    else:
                        msg_lines.append(
                            f"  相对差 {rel_max_abs_diff:.3e}"
                            f"(rel_tol {args.align_rel_tol:.1e}),"
                            f"ref_scale={ref_scale:.3e}")
                msg_lines.append(
                    f"  行数/丢弃计数是否一致: mismatch_idx={mismatch_idx[:5]}, "
                    f"dropped_rows_tgt_ok={drop_ok}, assembly_mismatch_ok="
                    f"{mismatch_ok}\n  排查:share_data 的公共前缀/掩码/"
                    "position_ids 构造,或 tokenizer 版本漂移。")
                print("\n".join(msg_lines), flush=True)
                sys.exit(2)
            return dict(report, bf16_warn=bf16_warn)
    except RefBaselineDriftError as e:
        # `_ref_forward` 的自检失败(参照基线本身不可信):按文件里其余所有
        # 失败分支同样的模式处理——写 ALIGN_CHECK.json、打印诊断、
        # sys.exit(2)。两处仍带 `check_drift=True` 的 `_ref_forward` 调用
        # (REF_BATCH 整批、bs=1 单行基线,都是 fp32)共用这一个 except——
        # cuda 上的 bf16 粗筛那一处传了 `check_drift=False`(工单 05 S2),
        # 不会触发这条异常。
        report = dict(PASS=False, stage="ref_forward_drift", error=str(e),
                      ref_inst_ce_drift_tol=REF_INST_CE_DRIFT_TOL,
                      rule=args.align_rule, rel_tol=args.align_rel_tol)
        (out / "ALIGN_CHECK.json").write_text(
            json.dumps(report, indent=1, ensure_ascii=False))
        print(json.dumps(report, indent=1), flush=True)
        print(
            "对齐检查 FAIL:参照路径自检失败,拒绝开训。\n"
            f"  {e}\n"
            "  排查:_ref_forward 里本地逐 token 公式与 inst_ce 的移位/掩码/"
            "聚合逻辑是否等价;如果两者逻辑本就等价,说明该环境下同一次 "
            "no_grad 前向存在超出预期的浮点不确定性,需要复核 "
            "REF_INST_CE_DRIFT_TOL 是否要放宽,而不是默认放行。", flush=True)
        sys.exit(2)
    finally:
        if tmp_path is not None:
            Path(tmp_path).unlink(missing_ok=True)
        torch.set_float32_matmul_precision(prev_prec)
        if dev.startswith("cuda"):
            torch.backends.cuda.matmul.allow_tf32 = prev_tf32_mm
            torch.backends.cudnn.allow_tf32 = prev_tf32_cudnn
        model.train()


# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=["cgen", "cparam"],
                    help="目标串与尾巴的构造走哪一套(spec 3.3)")
    ap.add_argument("--base", default="qwen",
                    help="qwen/qwen17/qwen4,或者一个模型目录路径"
                         "(路径走 build(path=...),给测试用的小模型进门)")
    ap.add_argument("--env", default="appworld",
                    choices=["tales", "appworld", "bfcl", "alfworld"],
                    help="仅作日志标签(数据路径已由 --data 直接给定)")
    ap.add_argument("--data", required=True,
                    help="数据目录 <data_out>(含 train/val.jsonl)")
    ap.add_argument("--out", required=True, help="产物目录(必填,防覆盖旧件)")
    ap.add_argument("--max-len", type=int, default=8192,
                    help="事件全文 token 上限,超过整条事件丢弃(spec 3.5)")
    ap.add_argument("--tok-budget", type=int, default=16384,
                    help="物理块预算:事件数 x 补齐后最长拼接序列长度(spec 5)")
    ap.add_argument("--eval-tok-budget", type=int, default=0,
                    help="评估物理块预算,0 = 2 x --tok-budget")
    ap.add_argument("--events-per-mb", type=int, default=4,
                    help="逻辑小批的事件数(spec 5)")
    ap.add_argument("--accum", type=int, default=2,
                    help="一次更新累积的逻辑小批数(spec 5)")
    ap.add_argument("--lr", type=float, default=None,
                    help="学习率,同旧;走 lora_util.resolve_lr")
    ap.add_argument("--epochs", type=int, default=1)
    ap.add_argument("--eval-per-epoch", type=int, default=4,
                    help="每 epoch 评估几次(spec 6)")
    ap.add_argument("--smoke", action="store_true",
                    help="40 训练事件/16 评估事件/1 epoch,按全文 token 数"
                         "升序取前 N 个")
    ap.add_argument("--max-events", type=int, default=0,
                    help="调试用:限事件数(0=不限);单独给时打乱后取前 N,"
                         "和 --smoke 同给时 N 覆盖 40/16、取法仍是升序")
    ap.add_argument("--log-every", type=int, default=50,
                    help="每几次更新写一条 step 日志")
    ap.add_argument("--gen-eval", type=int, default=200,
                    help="生成式评估抽的 val 行数,0 关闭(spec 16.3,工单 08)")
    ap.add_argument("--gen-bs", type=int, default=8,
                    help="生成式评估的批大小")
    ap.add_argument("--gen-eval-at", default="last", choices=["all", "last"],
                    help="last(默认)=只在 frac==E(epoch 末)那次评估做生成,"
                         "all=每个评估点都做")
    ap.add_argument("--mem-probe", action="store_true",
                    help="训练前踩最坏块量显存(spec 10)")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--grad-ckpt", action="store_true",
                    help="底座开梯度检查点省显存,同旧")
    ap.add_argument("--readonly-env", default=None,
                    choices=list(readonly_map.READONLY_ENVS),
                    help="只读工具模式,同旧(默认关=旧口径)")
    ap.add_argument("--force", action="store_true",
                    help="允许在已训过的 --out 目录再次训练")
    ap.add_argument("--attn-impl", default="sdpa", choices=["sdpa"],
                    help="注意力实现路径,这一轮只有 sdpa(spec 4)")
    ap.add_argument("--align-only", action="store_true",
                    help="只跑开训前对齐检查即退")
    ap.add_argument("--align-tol", type=float, default=2e-5,
                    help="对齐检查逐行 ce 最大绝对差门槛(spec 9)")
    ap.add_argument("--align-events", type=int, default=6,
                    help="对齐检查抽的 val 事件数(spec 9)")
    ap.add_argument("--align-tok-tol", type=float, default=3e-4,
                    help="对齐检查逐 token ce 最大绝对差门槛(spec 9)")
    ap.add_argument("--align-bf16-mean-tol", type=float, default=2e-2,
                    help="对齐检查 bf16 粗筛平均绝对差门槛(spec 9)")
    ap.add_argument("--align-bf16-max-tol", type=float, default=1e-1,
                    help="对齐检查 bf16 粗筛最大绝对差门槛(spec 9)")
    ap.add_argument("--align-baseline-factor", type=float, default=3.0,
                    help="基线告警倍数:逐行最大差超过基线自身差(单行补齐"
                         "基线与整批的差)的这个倍数就告警(spec 9)")
    ap.add_argument("--align-rule", default="abs", choices=["abs", "rel", "both"],
                    help="对齐判据:abs=逐行/逐token 绝对差(现状),"
                         "rel=相对差,both=两者同时成立(spec 9)")
    ap.add_argument("--align-rel-tol", type=float, default=1e-5,
                    help="对齐检查相对差门槛,配合 --align-rule rel/both(spec 9)")
    lora_util.add_args(ap)
    args = ap.parse_args()
    lr = lora_util.resolve_lr(args, train_causal_callgen.FULL_LR)

    SEED = train_causal_callgen.SEED
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
    mask_dtype = torch.bfloat16 if amp else torch.float32

    base_kw = (dict(base=args.base) if args.base in train_causal_callgen.MODELS
              else dict(path=args.base))
    tok, model, base_path = train_causal_callgen.build(
        dev, attn_impl=args.attn_impl, **base_kw)

    ro_set = (readonly_map.load_readonly_set(args.readonly_env)
             if args.readonly_env else None)

    # ---- 开训必过的门:对齐检查(lora_util.wrap 之前,model.eval() 下) ------
    align_rep = run_align_check(model, tok, args, dev, args.mode, ro_set)
    if args.align_only:
        return

    lora_wrap = lora_util.wrap(model, args) if args.lora else None
    if args.grad_ckpt:
        model.gradient_checkpointing_enable()
        model.config.use_cache = False
        if args.lora:
            lora_util.prepare_grad_ckpt(model)
    model.train()

    ro_tr = ro_ev = ro_table = None
    if args.readonly_env:
        ro_table = readonly_map.load_table(args.readonly_env)
        ro_tr = dict(set=ro_set, labels=[], kept=0, dropped=0)
        ro_ev = dict(set=ro_set, labels=[], kept=0, dropped=0)

    if args.smoke:
        order = "shortest"
        n_tr, n_ev = 40, 16
        if args.max_events:
            n_tr = n_ev = args.max_events
        epochs = 1
    else:
        order = "random"
        n_tr = n_ev = args.max_events
        epochs = args.epochs

    tr_events, tr_counts = share_data.load_events(
        data / "train.jsonl", tok, args.mode, args.max_len, ro=ro_tr,
        limit=n_tr, order=order)
    ev_events, ev_counts = share_data.load_events(
        data / "val.jsonl", tok, args.mode, args.max_len, ro=ro_ev,
        limit=n_ev, order=order)

    gen_rows = (sample_gen_eval_rows(ev_events, args.mode, SEED, args.gen_eval)
               if args.gen_eval > 0 else [])

    if args.readonly_env:
        au_tr = readonly_map.audit(ro_tr["labels"], ro_table,
                                   where=f"share/{args.mode}/train")
        au_ev = readonly_map.audit(ro_ev["labels"], ro_table,
                                   where=f"share/{args.mode}/val")
        (out / "READONLY.json").write_text(json.dumps(dict(
            readonly_env=args.readonly_env,
            table=str(readonly_map.table_path(args.readonly_env)),
            train=au_tr, val=au_ev,
            kept=dict(train=ro_tr["kept"], val=ro_ev["kept"]),
            dropped=dict(train=ro_tr["dropped"], val=ro_ev["dropped"])),
            ensure_ascii=False, indent=1))

    eval_tok_budget = (args.eval_tok_budget if args.eval_tok_budget > 0
                       else 2 * args.tok_budget)
    max_tgt_tok = (train_causal_callgen.MAX_TGT_TOK if args.mode == "cgen"
                  else train_causal_param.MAX_TGT_TOK)

    n_train_events = len(tr_events)
    M = math.ceil(n_train_events / args.events_per_mb)
    U = math.ceil(M / args.accum)
    steps = U * epochs

    pars = lora_util.opt_params(model.parameters(), args.lora)
    opt = torch.optim.AdamW(pars, lr=lr, weight_decay=0.01)
    sch = get_linear_schedule_with_warmup(opt, int(steps * 0.05), steps)

    logf = open(out / "train_log.jsonl", "a")

    def log(**kw):
        kw["t"] = round(time.time(), 1)
        logf.write(json.dumps(kw) + "\n")
        logf.flush()
        print(kw, flush=True)

    start_kw = dict(
        base=args.base, base_path=base_path, env=args.env, mode=args.mode,
        n_train_events=n_train_events, n_train_rows=tr_counts["n_rows"],
        n_eval_events=len(ev_events), n_eval_rows=ev_counts["n_rows"],
        dropped_events_train=tr_counts["dropped_events"],
        dropped_events_val=ev_counts["dropped_events"],
        dropped_rows_tgt_train=tr_counts["dropped_rows_tgt"],
        dropped_rows_tgt_val=ev_counts["dropped_rows_tgt"],
        steps=steps, epochs=epochs, smoke=args.smoke, max_len=args.max_len,
        max_tgt_tok=max_tgt_tok, tok_budget=args.tok_budget,
        eval_tok_budget=eval_tok_budget, events_per_mb=args.events_per_mb,
        accum=args.accum, eval_per_epoch=args.eval_per_epoch,
        log_every=args.log_every, gen_eval=args.gen_eval, gen_bs=args.gen_bs,
        gen_eval_at=args.gen_eval_at, mem_probe=args.mem_probe, lr=lr,
        attn_impl=args.attn_impl, seed=SEED, device=dev,
        readonly_env=args.readonly_env, align_pass=align_rep["PASS"],
        align_maxdiff=align_rep["max_abs_diff"],
        align_bf16_warn=bool(align_rep["bf16_warn"]),
        align_rule=args.align_rule)
    if args.mode == "cparam":
        start_kw["assembly_mismatch_train"] = tr_counts["assembly_mismatch"]
        start_kw["assembly_mismatch_val"] = ev_counts["assembly_mismatch"]
    if args.lora:
        start_kw["lora"] = lora_util.meta_block(args, lr)
    log(event="start", **start_kw)
    heartbeat.emit(0, steps, "step")

    training_t0 = time.time()
    if args.mem_probe:
        full_tr_events, _full_counts = share_data.load_events(
            data / "train.jsonl", tok, args.mode, args.max_len, ro=None, limit=0)
        run_mem_probe(model, opt, full_tr_events, args, dev, log, amp)
        del full_tr_events

    best = float("inf")
    best_ep = best_frac = None
    gstep = 0
    total_rows = 0
    for ep in range(epochs):
        epoch_events = list(tr_events)
        random.Random(SEED + ep).shuffle(epoch_events)
        minibatches = [epoch_events[i:i + args.events_per_mb]
                      for i in range(0, len(epoch_events), args.events_per_mb)]
        M_ep = len(minibatches)
        E = args.eval_per_epoch
        # 评估点 -> frac:k 从 1 到 E 顺序算,同一个点被多个 k 命中时后面的 k
        # 覆盖前面的(拿到 max k),这样 k=E 的点(=epoch 末,ceil(U*E/E)=U 恒成立)
        # 总是报 frac=E,不会被更早的重复点抢走(spec 6:『k=E 的那个点是 epoch
        # 末』)。
        eval_points = {}
        for k in range(1, E + 1):
            p = math.ceil(U * k / E)
            eval_points[p] = k

        run_loss_sum = run_mb_count = 0
        epoch_rows = epoch_events_n = 0
        epoch_train_s = 0.0
        last_log_rows = last_log_train_s = 0.0
        u = 0
        i = 0
        while i < M_ep:
            group_size = min(args.accum, M_ep - i)
            group = minibatches[i:i + group_size]
            i += group_size
            t0 = time.time()
            n_g = group_size
            for mb_events in group:
                W = sum(row[5] for ev in mb_events for row in ev["rows"])
                blocks = share_data.chunk_by_budget(mb_events, args.tok_budget)
                mb_loss, mb_rows = backward_logical_minibatch(
                    model, blocks, W, n_g, dev, mask_dtype, amp)
                run_loss_sum += mb_loss
                run_mb_count += 1
                epoch_rows += mb_rows
                epoch_events_n += len(mb_events)
                total_rows += mb_rows
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sch.step()
            opt.zero_grad()
            gstep += 1
            u += 1
            epoch_train_s += time.time() - t0

            if gstep % args.log_every == 0:
                loss_val = round(run_loss_sum / max(run_mb_count, 1), 4)
                ips = round(epoch_rows / max(epoch_train_s, 1e-9), 2)
                d_rows = epoch_rows - last_log_rows
                d_s = epoch_train_s - last_log_train_s
                ips_win = round(d_rows / max(d_s, 1e-9), 2)
                eps = round(epoch_events_n / max(epoch_train_s, 1e-9), 2)
                if dev.startswith("cuda"):
                    peak_mem_gb = round(torch.cuda.max_memory_allocated() / 1e9, 3)
                    torch.cuda.reset_peak_memory_stats()
                else:
                    peak_mem_gb = 0.0
                log(event="step", ep=ep, gstep=gstep, rows=epoch_rows,
                    loss=loss_val, lr=sch.get_last_lr()[0], ips=ips,
                    ips_win=ips_win, eps=eps, train_s=round(epoch_train_s, 2),
                    peak_mem_gb=peak_mem_gb)
                heartbeat.emit(gstep, steps, "step", loss=loss_val)
                run_loss_sum = run_mb_count = 0
                last_log_rows, last_log_train_s = epoch_rows, epoch_train_s

            if u in eval_points:
                frac = eval_points[u]
                vce = eval_ce(model, ev_events, eval_tok_budget, dev, amp,
                              beat=lambda: heartbeat.emit(gstep, steps, "step"))
                eval_kw = dict(event="eval", ep=ep, frac=frac, gstep=gstep,
                              val_ce=round(vce, 4), n_eval_rows=ev_counts["n_rows"])
                do_gen = (args.gen_eval > 0
                         and (args.gen_eval_at == "all" or frac == E))
                if do_gen:
                    heartbeat.emit(gstep, steps, "step")
                    gen_t0 = time.time()
                    gen_fn = (train_causal_callgen.eval_gen if args.mode == "cgen"
                             else train_causal_param.eval_gen)
                    vex = gen_fn(model, tok, gen_rows, dev, amp, args.max_len,
                                args.gen_bs)
                    heartbeat.emit(gstep, steps, "step")
                    exact_key = ("val_exact_call" if args.mode == "cgen"
                                else "val_exact_params")
                    eval_kw[exact_key] = round(vex, 4)
                    eval_kw["gen_n"] = len(gen_rows)
                    eval_kw["gen_s"] = round(time.time() - gen_t0, 2)
                log(**eval_kw)
                if vce < best:
                    best = vce
                    best_ep, best_frac = ep, frac
                    (out / "best").mkdir(parents=True, exist_ok=True)
                    if lora_wrap is None:
                        model.save_pretrained(out / "best")
                    else:
                        # 适配器并回底座再落盘:best/ 与全参存的逐项同构
                        lora_util.save_merged(lora_wrap, out / "best", dev)
                    tok.save_pretrained(out / "best")
                    meta = dict(
                        base=args.base, base_path=base_path, data=str(data),
                        max_len=args.max_len, seed=SEED, epoch=ep,
                        call_sep=train_causal_callgen.CALL_SEP,
                        transformers=transformers.__version__,
                        trainer="share", frac=frac, gstep=gstep,
                        tok_budget=args.tok_budget,
                        events_per_mb=args.events_per_mb, accum=args.accum,
                        attn_impl=args.attn_impl)
                    if args.readonly_env:
                        meta["readonly_env"] = args.readonly_env
                    if args.lora:
                        meta["lora"] = lora_util.meta_block(args, lr)
                    if args.grad_ckpt:
                        meta["grad_ckpt"] = True
                    if args.mode == "cparam":
                        meta["param_only"] = True
                    (out / "best" / "meta.json").write_text(
                        json.dumps(meta, indent=1))
                    log(event="save_best", ep=ep, frac=frac, gstep=gstep,
                        val_ce=round(best, 4))

    log(event="done", best_val_ce=round(best, 4), best_ep=best_ep,
        best_frac=best_frac, total_rows=total_rows,
        wall_s=round(time.time() - training_t0, 2))
    heartbeat.emit(gstep, steps, "step", status="done")


if __name__ == "__main__":
    main()
