#!/usr/bin/env python
"""GPU 上验证形态 A 的内核选择、显存峰值与对齐差值(给主会话跑;本脚本只读模型与 val 集,不写仓库)。

七步,每一步做完立刻把 --out 的 JSON 整个重写一次(崩了也留下前面的数);每一步包在 try 里,
出错就把错误原文记进 JSON、清显存、接着跑下一步,不许整个脚本崩掉。
  1 kernel_eligibility  torch.backends.cuda.can_use_{flash,efficient,cudnn}_attention(SDPAParams, debug=True)
                        对形态 A 真实形状的 q/k/v(bf16,[1,16,L,128])+ bool 掩码 / bf16 加性掩码各问一遍
  2 forced_efficient    sdpa_kernel([EFFICIENT_ATTENTION]) 下整模型前向+反向(autocast bf16):峰值显存、耗时、profiler 里的内核名
  3 default_selection   不套上下文的同一前向:profiler 内核名和第 2 步比(第一次发射实测 H100 默认落到 cuDNN)
  4 math_at_short_L     sdpa_kernel([MATH]) 在短序列上跑:只取 prompt ≤ --math-L 的行,前缀截到 --math-L,
                        逐行装到拼接长度 L ≤ 1.25 × --math-L 为止;装不进两行就跳过并记原因。峰值对照解析式 28×16×L²×4 字节
  5 mask_variants       bool 掩码 / bf16 加性掩码 × L 补到 16 的倍数 / 不补:各自的峰值显存(mem-efficient 的掩码预处理会不会复制)
  6 alignment           随机 5 个短事件:旧训练器逐行前向 vs 形态 A,每行 loss 与逐 token 差值,bf16 autocast 与 fp32(autocast 关、
                        highest 精度、fp32 掩码)各一遍,同一次运行里带「旧训练器单行 vs 整批补齐」的基线差
  7 optional            --grad-ckpt / --lora:形态 A 在这两个开关下的峰值显存

用法(仓库根,cprobe-env,单卡):
  CUDA_VISIBLE_DEVICES=0 cprobe-env/bin/python .scratch/kvshare-train/verify/gpu_kernel_check.py \
      --max-len 8192 --math-L 2048 --grad-ckpt --lora --out <产物目录>/gpu_result.json
"""
import argparse
import json
import os
import sys
import time
import traceback
import warnings

import torch
import torch.nn.functional as F
from torch.nn.attention import sdpa_kernel, SDPBackend
from torch.profiler import ProfilerActivity, profile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import packed_common as pc  # noqa: E402

N_LAYERS, N_HEADS, HEAD_DIM = 28, 16, 128


class _null:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def kernel_names(prof):
    keys = ("efficient", "fmha", "cutlass", "flash", "math", "cudnn", "scaled_dot_product")
    return sorted({e.name for e in prof.events() if any(k in e.name.lower() for k in keys)})


def run_model(model, pk, dev, mask_kind, mask_dtype=torch.bfloat16, backends=None, do_profile=False):
    """整模型前向加反向(autocast bf16),返回峰值显存、耗时、内核名。"""
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    base = torch.cuda.memory_allocated()
    model.zero_grad(set_to_none=True)
    ctx = sdpa_kernel(backends) if backends else _null()
    t0 = time.time()
    names = None
    with ctx, torch.autocast("cuda", dtype=torch.bfloat16):
        if do_profile:
            with profile(activities=[ProfilerActivity.CPU, ProfilerActivity.CUDA]) as prof:
                ce, rm = pc.forward_packed(model, pk, dev, mask_kind, mask_dtype)
                rm.mean().backward()
            names = kernel_names(prof)
        else:
            ce, rm = pc.forward_packed(model, pk, dev, mask_kind, mask_dtype)
            rm.mean().backward()
    torch.cuda.synchronize()
    peak = torch.cuda.max_memory_allocated()
    row_loss_mean = float(rm.detach().mean())
    del ce, rm
    model.zero_grad(set_to_none=True)
    return dict(L=pk["L"], mask=mask_kind, backends=[b.name for b in backends] if backends else "default",
                peak_alloc_GiB=round(peak / 2**30, 2), delta_GiB=round((peak - base) / 2**30, 2),
                seconds=round(time.time() - t0, 2), kernels=names, row_loss_mean=row_loss_mean)


def pad_to_16(pk):
    """把打包序列补到 16 的倍数:pad 位不进 loss 位表,掩码行只让 pad 自己看自己(避免全 False 行)。"""
    L = pk["L"]
    Lp = (L + 15) // 16 * 16
    if Lp == L:
        return pk
    allow = torch.zeros(Lp, Lp, dtype=torch.bool)
    allow[:L, :L] = pk["allow"]
    for j in range(L, Lp):
        allow[j, j] = True
    return dict(pk, L=Lp, seq=pk["seq"] + [pk["seq"][-1]] * (Lp - L),
                pos=pk["pos"] + list(range(pk["pos"][-1] + 1, pk["pos"][-1] + 1 + Lp - L)), allow=allow)


def short_pack(events, tok, math_L):
    """第 4 步的短序列:另挑「全文 token ≤ math_L 的最长事件」(前缀本身装得进,每行尾巴正常),
    按 sent_idx 顺序逐行装到拼接长度 L 超过 1.25 × math_L 为止;装不进两行就返回原因。
    (最长事件本身不能用:它的 64 行 prompt 全都超过 2048,截前缀会把整段 prompt 塞进尾巴,第一次发射就是这样崩的。)"""
    ek, n_full = pc.longest_event_within(events, tok, math_L)
    if ek is None:
        return None, f"没有全文 token ≤ {math_L} 的事件", None
    rs = events[ek]
    rows = pc.build_rows(tok, rs)
    full_ids = tok(rs[-1]["text"], add_special_tokens=False)["input_ids"]
    keep = []
    for r in rows:
        trial = pc.build_packed(keep + [r], full_ids)
        if trial["L"] > 1.25 * math_L:
            break
        keep.append(r)
    if len(keep) < 2:
        return None, f"事件 {ek}(全文 {n_full} 个 token)装不进两行就超过 1.25 × {math_L}", None
    pk = pc.build_packed(keep, full_ids)
    return pk, None, dict(event=ek, n_full=n_full, n_rows=len(keep), n_rows_total=len(rows))


def alignment(model, tok, events, chosen, dev, fp32):
    """旧训练器逐行前向 vs 形态 A:每行 loss 与逐 token 的差,带补齐基线。fp32=True 时 autocast 关、fp32 掩码。

    参照路径不套 EFFICIENT 上下文:单行不补齐的批没有掩码,HF 走 enable_gqa=True(K/V 保持 8 头不复制),
    mem-efficient 不支持 GQA,强制 EFFICIENT 会抛 `No available kernel`(补射第一次就是这样错的,日志第 15 行:
    `both fused kernels require query, key and value to have the same num_heads`)。新路径永远带掩码
    (repeat_kv 到 16 头),套 EFFICIENT,这正是训练器对齐检查里新路径要走的内核。"""
    olds, singles, news = [], [], []
    olds_t, singles_t, news_t = [], [], []
    ctx = torch.autocast("cuda", dtype=torch.bfloat16, enabled=not fp32)
    mask_dtype = torch.float32 if fp32 else torch.bfloat16
    with torch.no_grad(), ctx:
        for e in chosen:
            rr = pc.build_rows(tok, events[e])
            fi = tok(events[e][-1]["text"], add_special_tokens=False)["input_ids"]
            pk_e = pc.build_packed(rr, fi)
            ce_b, rm_b = pc.forward_old(model, tok, rr, dev, batched=True)      # 默认内核选择
            ce_s, rm_s = pc.forward_old(model, tok, rr, dev, batched=False)     # 默认内核选择
            with sdpa_kernel([SDPBackend.EFFICIENT_ATTENTION]):
                ce_n, rm_n = pc.forward_packed(model, pk_e, dev, "float", mask_dtype)
            olds.append(rm_b); singles.append(rm_s); news.append(rm_n)
            olds_t.append(ce_b); singles_t.append(ce_s); news_t.append(ce_n)
    cat = torch.cat
    return dict(events=chosen, dtype="fp32" if fp32 else "bf16_autocast",
                n_rows=int(cat(olds).numel()), n_tokens=int(cat(olds_t).numel()),
                row_new_vs_old_batched=pc.diff_stats(cat(olds), cat(news)),
                row_old_single_vs_old_batched=pc.diff_stats(cat(olds), cat(singles)),
                tok_new_vs_old_batched=pc.diff_stats(cat(olds_t), cat(news_t)),
                tok_old_single_vs_old_batched=pc.diff_stats(cat(olds_t), cat(singles_t)),
                row_loss_mean=float(cat(olds).mean()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-len", type=int, default=8192)
    ap.add_argument("--math-L", type=int, default=2048)
    ap.add_argument("--n-events", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--grad-ckpt", action="store_true")
    ap.add_argument("--lora", action="store_true")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    dev = "cuda"
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(pc.MODEL)
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    tok.truncation_side, tok.padding_side = "left", "right"
    model = AutoModelForCausalLM.from_pretrained(pc.MODEL, dtype=torch.float32).to(dev)
    model.train()
    events = pc.load_events()
    R = dict(torch=torch.__version__, gpu=torch.cuda.get_device_name(0),
             priority_order=torch._C._get_sdp_priority_order(),
             float32_matmul_precision=torch.get_float32_matmul_precision(),
             allow_tf32_matmul=torch.backends.cuda.matmul.allow_tf32, steps_done=[], errors={})

    def dump():
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        json.dump(R, open(args.out, "w"), indent=1, ensure_ascii=False)

    def step(name, fn):
        """跑一步:成功就记结果,失败就记错误原文,两种情况都立刻落盘。"""
        try:
            R[name] = fn()
            print(name, json.dumps(R[name], ensure_ascii=False)[:2000], flush=True)
        except Exception as e:  # noqa: BLE001
            R["errors"][name] = f"{type(e).__name__}: {str(e)[:800]}"
            print(name, "ERROR", R["errors"][name], flush=True)
            traceback.print_exc()
            torch.cuda.empty_cache()
        R["steps_done"].append(name)
        dump()

    # 最长事件(全文 token ≤ max_len)的打包序列
    ek, n_full = pc.longest_event_within(events, tok, args.max_len)
    rs = events[ek]
    rows = pc.build_rows(tok, rs)
    full_ids = tok(rs[-1]["text"], add_special_tokens=False)["input_ids"]
    pk = pc.build_packed(rows, full_ids)
    R["longest_event"] = dict(event=ek, n_rows=len(rows), P=pk["P"], L=pk["L"])
    print("longest event", R["longest_event"], flush=True)
    dump()

    # 1 内核资格
    def s1():
        L = pk["L"]
        q = torch.randn(1, N_HEADS, L, HEAD_DIM, device=dev, dtype=torch.bfloat16)
        k = torch.randn_like(q)
        v = torch.randn_like(q)
        mask_bool = pk["allow"][None, None].to(dev)
        mask_bf16 = pc.float_mask(pk["allow"], torch.bfloat16)[None, None].to(dev)
        mask_f32 = pc.float_mask(pk["allow"], torch.float32)[None, None].to(dev)
        elig = {}
        for mname, (qq, kk, vv, m) in (("bool", (q, k, v, mask_bool)),
                                       ("bf16_additive", (q, k, v, mask_bf16)),
                                       ("fp32_query_fp32_additive", (q.float(), k.float(), v.float(), mask_f32)),
                                       ("bf16_gqa_no_mask_kv8heads", (q, k[:, :8], v[:, :8], None))):
            params = torch.backends.cuda.SDPAParams(qq, kk, vv, m, 0.0, m is None, m is None)
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                elig[mname] = dict(
                    flash=torch.backends.cuda.can_use_flash_attention(params, True),
                    efficient=torch.backends.cuda.can_use_efficient_attention(params, True),
                    cudnn=torch.backends.cuda.can_use_cudnn_attention(params, True),
                    warnings=[str(x.message)[:300] for x in w])
        del q, k, v, mask_bool, mask_bf16, mask_f32
        torch.cuda.empty_cache()
        return elig
    step("kernel_eligibility", s1)

    # 2, 3 强制 efficient / 默认
    step("forced_efficient", lambda: run_model(model, pk, dev, "bool",
                                               backends=[SDPBackend.EFFICIENT_ATTENTION], do_profile=True))
    step("default_selection", lambda: run_model(model, pk, dev, "bool", backends=None, do_profile=True))

    # 4 math 在短 L(只取 prompt 装得进 math_L 的行,L ≤ 1.25 × math_L,否则跳过)
    def s4():
        pk_short, why, picked = short_pack(events, tok, args.math_L)
        if pk_short is None:
            return dict(skipped=True, reason=why)
        info = dict(picked, P=pk_short["P"], L=pk_short["L"], bound=1.25 * args.math_L,
                    analytic_GiB_28x16xL2x4B=round(N_LAYERS * N_HEADS * pk_short["L"] ** 2 * 4 / 2**30, 2))
        print("math short pack", info, flush=True)
        assert pk_short["L"] <= 1.25 * args.math_L, info
        info["math"] = run_model(model, pk_short, dev, "bool", backends=[SDPBackend.MATH], do_profile=True)
        info["efficient"] = run_model(model, pk_short, dev, "bool", backends=[SDPBackend.EFFICIENT_ATTENTION])
        return info
    step("math_at_short_L", s4)

    # 5 掩码变体(全长,强制 efficient)
    def s5():
        pk16 = pad_to_16(pk)
        return dict(
            bool_unaligned=run_model(model, pk, dev, "bool", backends=[SDPBackend.EFFICIENT_ATTENTION]),
            bf16_unaligned=run_model(model, pk, dev, "float", torch.bfloat16, backends=[SDPBackend.EFFICIENT_ATTENTION]),
            bool_aligned16=run_model(model, pk16, dev, "bool", backends=[SDPBackend.EFFICIENT_ATTENTION]),
            bf16_aligned16=run_model(model, pk16, dev, "float", torch.bfloat16, backends=[SDPBackend.EFFICIENT_ATTENTION]),
            L_padded=pk16["L"])
    step("mask_variants", s5)

    # 6 对齐差值(短事件):bf16 autocast 一遍,fp32 一遍
    chosen, _ = pc.pick_events(events, args.n_events, 8, 4000, args.seed)
    step("bf16_alignment", lambda: alignment(model, tok, events, chosen, dev, fp32=False))

    def s6b():
        prev = torch.get_float32_matmul_precision()
        prev_tf32 = torch.backends.cuda.matmul.allow_tf32
        torch.set_float32_matmul_precision("highest")
        torch.backends.cuda.matmul.allow_tf32 = False
        try:
            return alignment(model, tok, events, chosen, dev, fp32=True)
        finally:
            torch.set_float32_matmul_precision(prev)
            torch.backends.cuda.matmul.allow_tf32 = prev_tf32
    step("fp32_alignment", s6b)

    # 7 可选
    if args.grad_ckpt:
        def s7a():
            model.gradient_checkpointing_enable()
            model.config.use_cache = False
            try:
                return run_model(model, pk, dev, "bool", backends=[SDPBackend.EFFICIENT_ATTENTION])
            finally:
                model.gradient_checkpointing_disable()
        step("grad_ckpt", s7a)
    if args.lora:
        def s7b():
            from peft import LoraConfig, get_peft_model
            get_peft_model(model, LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
                                             target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                                                             "gate_proj", "up_proj", "down_proj"]))
            return run_model(model, pk, dev, "bool", backends=[SDPBackend.EFFICIENT_ATTENTION])
        step("lora", s7b)
    dump()
    print("written", args.out, "errors:", R["errors"])


if __name__ == "__main__":
    main()
