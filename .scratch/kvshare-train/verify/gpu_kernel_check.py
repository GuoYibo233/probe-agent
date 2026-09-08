#!/usr/bin/env python
"""Verify form A's kernel selection, peak GPU memory, and alignment difference on GPU
(run from the main session; this script only reads the model and val set, and writes
nothing to the repo).

Seven steps; after each step finishes, immediately rewrite the whole --out JSON (so a
crash still leaves the earlier numbers). Each step is wrapped in try: on error, record
the original error text into the JSON, clear GPU memory, and move on to the next step --
the whole script must never crash.
  1 kernel_eligibility  torch.backends.cuda.can_use_{flash,efficient,cudnn}_attention(SDPAParams, debug=True)
                        asks once each for form A's real-shape q/k/v (bf16, [1,16,L,128])
                        with a bool mask and with a bf16 additive mask
  2 forced_efficient    sdpa_kernel([EFFICIENT_ATTENTION]) forward+backward on the whole
                        model (autocast bf16): peak GPU memory, wall time, kernel name
                        from the profiler
  3 default_selection   the same forward pass with no context manager: compare the
                        profiler's kernel name against step 2 (first launch measured H100
                        defaulting to cuDNN)
  4 math_at_short_L     run sdpa_kernel([MATH]) on short sequences: take only rows whose
                        prompt ≤ --math-L, crop the prefix to --math-L, pack rows one by
                        one until the concatenated length L ≤ 1.25 × --math-L; skip and
                        record the reason if even two rows do not fit. Compare the peak
                        against the closed form 28×16×L²×4 bytes
  5 mask_variants       bool mask / bf16 additive mask × L padded to a multiple of 16 /
                        not padded: peak GPU memory for each combination (whether
                        mem-efficient's mask preprocessing makes a copy)
  6 alignment           5 random short events: old trainer's per-row forward pass vs
                        form A, per-row loss and per-token difference, one pass each with
                        bf16 autocast and fp32 (autocast off, highest precision, fp32
                        mask); the same run also carries the baseline difference between
                        "old trainer single row" and "packed whole batch"
  7 optional            --grad-ckpt / --lora: form A's peak GPU memory under these two
                        switches

Usage (repo root, cprobe-env, single card):
  CUDA_VISIBLE_DEVICES=0 cprobe-env/bin/python .scratch/kvshare-train/verify/gpu_kernel_check.py \
      --max-len 8192 --math-L 2048 --grad-ckpt --lora --out <output dir>/gpu_result.json
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
    """Forward plus backward pass on the whole model (autocast bf16); returns peak GPU memory, wall time, and kernel name."""
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
    """Pad the packed sequence to a multiple of 16: pad positions are excluded from the loss-position table, and a pad row's mask only lets it see itself (to avoid an all-False row)."""
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
    """Short sequence for step 4: pick instead "the longest event whose full-text token
    count is ≤ math_L" (the prefix itself fits, and every row's tail is normal), pack
    rows one by one in sent_idx order until the concatenated length L exceeds 1.25 ×
    math_L; return the reason if even two rows do not fit.
    (The single longest event cannot be used: all 64 of its prompt rows exceed 2048, so
    cropping the prefix stuffs the whole prompt into the tail -- that is exactly how the
    first launch crashed.)"""
    ek, n_full = pc.longest_event_within(events, tok, math_L)
    if ek is None:
        return None, f"no event with full-text tokens ≤ {math_L}", None
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
        return None, f"event {ek} (full text {n_full} tokens) does not fit into two rows: exceeds 1.25 × {math_L}", None
    pk = pc.build_packed(keep, full_ids)
    return pk, None, dict(event=ek, n_full=n_full, n_rows=len(keep), n_rows_total=len(rows))


def alignment(model, tok, events, chosen, dev, fp32):
    """Old trainer's per-row forward pass vs form A: per-row loss and per-token difference,
    with the padding baseline. When fp32=True, autocast is off and the mask is fp32.

    The reference path does not use the EFFICIENT context manager: a single-row,
    unpadded batch has no mask, so HF takes the enable_gqa=True path (K/V stay at 8
    heads, not repeated); mem-efficient does not support GQA, so forcing EFFICIENT
    raises `No available kernel` (this is exactly the error on the first refire, log
    line 15: `both fused kernels require query, key and value to have the same
    num_heads`). The new path always carries a mask (repeat_kv up to 16 heads) and uses
    EFFICIENT -- this is exactly the kernel the new path takes in the trainer's
    alignment check."""
    olds, singles, news = [], [], []
    olds_t, singles_t, news_t = [], [], []
    ctx = torch.autocast("cuda", dtype=torch.bfloat16, enabled=not fp32)
    mask_dtype = torch.float32 if fp32 else torch.bfloat16
    with torch.no_grad(), ctx:
        for e in chosen:
            rr = pc.build_rows(tok, events[e])
            fi = tok(events[e][-1]["text"], add_special_tokens=False)["input_ids"]
            pk_e = pc.build_packed(rr, fi)
            ce_b, rm_b = pc.forward_old(model, tok, rr, dev, batched=True)      # default kernel selection
            ce_s, rm_s = pc.forward_old(model, tok, rr, dev, batched=False)     # default kernel selection
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
        """Run one step: record the result on success, record the original error text on failure; write to disk immediately either way."""
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

    # the packed sequence of the longest event (full-text tokens ≤ max_len)
    ek, n_full = pc.longest_event_within(events, tok, args.max_len)
    rs = events[ek]
    rows = pc.build_rows(tok, rs)
    full_ids = tok(rs[-1]["text"], add_special_tokens=False)["input_ids"]
    pk = pc.build_packed(rows, full_ids)
    R["longest_event"] = dict(event=ek, n_rows=len(rows), P=pk["P"], L=pk["L"])
    print("longest event", R["longest_event"], flush=True)
    dump()

    # 1 kernel eligibility
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

    # 2, 3 forced efficient / default
    step("forced_efficient", lambda: run_model(model, pk, dev, "bool",
                                               backends=[SDPBackend.EFFICIENT_ATTENTION], do_profile=True))
    step("default_selection", lambda: run_model(model, pk, dev, "bool", backends=None, do_profile=True))

    # 4 math at short L (only rows whose prompt fits math_L, L ≤ 1.25 × math_L, else skip)
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

    # 5 mask variants (full length, forced efficient)
    def s5():
        pk16 = pad_to_16(pk)
        return dict(
            bool_unaligned=run_model(model, pk, dev, "bool", backends=[SDPBackend.EFFICIENT_ATTENTION]),
            bf16_unaligned=run_model(model, pk, dev, "float", torch.bfloat16, backends=[SDPBackend.EFFICIENT_ATTENTION]),
            bool_aligned16=run_model(model, pk16, dev, "bool", backends=[SDPBackend.EFFICIENT_ATTENTION]),
            bf16_aligned16=run_model(model, pk16, dev, "float", torch.bfloat16, backends=[SDPBackend.EFFICIENT_ATTENTION]),
            L_padded=pk16["L"])
    step("mask_variants", s5)

    # 6 alignment difference (short events): one pass bf16 autocast, one pass fp32
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

    # 7 optional
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
