#!/usr/bin/env python
"""GPU 上验证形态 A 的内核选择、显存峰值与 bf16 对齐差值(给主会话跑;本脚本只读模型与 val 集,不写仓库)。

七步,每步结果写进 --out 的 JSON:
  1 kernel_eligibility  torch.backends.cuda.can_use_{flash,efficient,cudnn}_attention(SDPAParams, debug=True)
                        对形态 A 真实形状的 q/k/v(bf16,[1,16,L,128])+ bool 掩码 / bf16 加性掩码各问一遍
  2 forced_efficient    sdpa_kernel([EFFICIENT_ATTENTION]) 下整模型前向+反向(autocast bf16):峰值显存、耗时、profiler 里的内核名
  3 default_selection   不套上下文的同一前向:profiler 内核名要和第 2 步一样(默认优先级 flash→efficient→math→cudnn)
  4 math_at_short_L     sdpa_kernel([MATH]) 在 --math-L 上跑:峰值显存对照解析式 28×16×L²×4 字节
  5 mask_variants       bool 掩码 / bf16 加性掩码 × L 对齐到 16 / 不对齐:各自的峰值显存(mem-efficient 的掩码预处理会不会复制)
  6 bf16_alignment      随机 5 个短事件:旧训练器逐行前向 vs 形态 A,每行 loss 差值分布(bf16 autocast,GPU 真实内核)
  7 optional            --grad-ckpt / --lora:形态 A 在这两个开关下的峰值显存

用法(仓库根,cprobe-env,单卡):
  CUDA_VISIBLE_DEVICES=0 cprobe-env/bin/python /home/y-guo/.claude/jobs/b39c625e/tmp/a2/gpu_kernel_check.py \
      --max-len 8192 --math-L 2048 --out /home/y-guo/.claude/jobs/b39c625e/tmp/a2/gpu_result.json
"""
import argparse
import json
import os
import sys
import time
import warnings

import torch
import torch.nn.functional as F
from torch.nn.attention import sdpa_kernel, SDPBackend
from torch.profiler import ProfilerActivity, profile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import packed_common as pc  # noqa: E402

N_LAYERS, N_HEADS, HEAD_DIM = 28, 16, 128


def kernel_names(prof):
    keys = ("efficient", "fmha", "cutlass", "flash", "math", "cudnn", "scaled_dot_product")
    return sorted({e.name for e in prof.events() if any(k in e.name.lower() for k in keys)})


def run_model(model, pk, dev, mask_kind, mask_dtype=torch.bfloat16, backends=None, do_profile=False):
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
    model.zero_grad(set_to_none=True)
    return dict(L=pk["L"], mask=mask_kind, backends=[b.name for b in backends] if backends else "default",
                peak_alloc_GiB=round(peak / 2**30, 2), delta_GiB=round((peak - base) / 2**30, 2),
                seconds=round(time.time() - t0, 2), kernels=names, row_loss_mean=float(rm.mean()))


class _null:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def pad_to_16(pk):
    """把打包序列补到 16 的倍数:pad 位 label 无、掩码只看自己(避免全 False 行)。"""
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
             priority_order=torch._C._get_sdp_priority_order())

    # 最长事件(全文 token ≤ max_len)的打包序列
    ek, n_full = pc.longest_event_within(events, tok, args.max_len)
    rs = events[ek]
    rows = pc.build_rows(tok, rs)
    full_ids = tok(rs[-1]["text"], add_special_tokens=False)["input_ids"]
    pk = pc.build_packed(rows, full_ids)
    R["longest_event"] = dict(event=ek, n_rows=len(rows), P=pk["P"], L=pk["L"])
    print("longest event", R["longest_event"], flush=True)

    # 1 内核资格
    L = pk["L"]
    q = torch.randn(1, N_HEADS, L, HEAD_DIM, device=dev, dtype=torch.bfloat16)
    k = torch.randn_like(q)
    v = torch.randn_like(q)
    mask_bool = pk["allow"][None, None].to(dev)
    mask_bf16 = pc.float_mask(pk["allow"], torch.bfloat16)[None, None].to(dev)
    elig = {}
    for mname, m in (("bool", mask_bool), ("bf16_additive", mask_bf16)):
        params = torch.backends.cuda.SDPAParams(q, k, v, m, 0.0, False, False)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            elig[mname] = dict(
                flash=torch.backends.cuda.can_use_flash_attention(params, True),
                efficient=torch.backends.cuda.can_use_efficient_attention(params, True),
                cudnn=torch.backends.cuda.can_use_cudnn_attention(params, True),
                warnings=[str(x.message) for x in w])
    R["kernel_eligibility"] = elig
    print("eligibility", json.dumps(elig, indent=1), flush=True)
    del q, k, v

    # 2, 3 强制 efficient / 默认
    R["forced_efficient"] = run_model(model, pk, dev, "bool", backends=[SDPBackend.EFFICIENT_ATTENTION], do_profile=True)
    print(json.dumps(R["forced_efficient"]), flush=True)
    R["default_selection"] = run_model(model, pk, dev, "bool", backends=None, do_profile=True)
    print(json.dumps(R["default_selection"]), flush=True)

    # 4 math 在短 L
    pk_short = pc.build_packed(rows[: max(2, len(rows) // 4)], full_ids[: args.math_L])
    R["math_at_short_L"] = run_model(model, pk_short, dev, "bool", backends=[SDPBackend.MATH], do_profile=True)
    R["math_at_short_L"]["analytic_GiB_28x16xL2x4B"] = round(N_LAYERS * N_HEADS * pk_short["L"] ** 2 * 4 / 2**30, 2)
    R["efficient_at_short_L"] = run_model(model, pk_short, dev, "bool", backends=[SDPBackend.EFFICIENT_ATTENTION])
    print(json.dumps(R["math_at_short_L"]), json.dumps(R["efficient_at_short_L"]), flush=True)

    # 5 掩码变体
    pk16 = pad_to_16(pk)
    R["mask_variants"] = dict(
        bool_unaligned=run_model(model, pk, dev, "bool", backends=[SDPBackend.EFFICIENT_ATTENTION]),
        bf16_unaligned=run_model(model, pk, dev, "float", torch.bfloat16, backends=[SDPBackend.EFFICIENT_ATTENTION]),
        bool_aligned16=run_model(model, pk16, dev, "bool", backends=[SDPBackend.EFFICIENT_ATTENTION]),
        bf16_aligned16=run_model(model, pk16, dev, "float", torch.bfloat16, backends=[SDPBackend.EFFICIENT_ATTENTION]),
    )
    print(json.dumps(R["mask_variants"], indent=1), flush=True)

    # 6 bf16 对齐差值(短事件)
    chosen, _ = pc.pick_events(events, args.n_events, 8, 4000, args.seed)
    olds, news = [], []
    with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):
        for e in chosen:
            rr = pc.build_rows(tok, events[e])
            fi = tok(events[e][-1]["text"], add_special_tokens=False)["input_ids"]
            pk_e = pc.build_packed(rr, fi)
            olds.append(pc.forward_old(model, tok, rr, dev, batched=True)[1])
            news.append(pc.forward_packed(model, pk_e, dev, "bool")[1])
    R["bf16_alignment"] = dict(events=chosen, row=pc.diff_stats(torch.cat(olds), torch.cat(news)))
    print("bf16_alignment", json.dumps(R["bf16_alignment"]), flush=True)

    # 7 可选
    if args.grad_ckpt:
        model.gradient_checkpointing_enable()
        model.config.use_cache = False
        R["grad_ckpt"] = run_model(model, pk, dev, "bool", backends=[SDPBackend.EFFICIENT_ATTENTION])
        model.gradient_checkpointing_disable()
        print(json.dumps(R["grad_ckpt"]), flush=True)
    if args.lora:
        from peft import LoraConfig, get_peft_model
        get_peft_model(model, LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
                                         target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                                                         "gate_proj", "up_proj", "down_proj"]))
        R["lora"] = run_model(model, pk, dev, "bool", backends=[SDPBackend.EFFICIENT_ATTENTION])
        print(json.dumps(R["lora"]), flush=True)
    json.dump(R, open(args.out, "w"), indent=1, ensure_ascii=False)
    print("written", args.out)


if __name__ == "__main__":
    main()
