#!/usr/bin/env python
"""How many activations form A's backward pass needs to save: on CPU, use
saved_tensors_hooks to record every tensor autograd saves, one by one (deduplicated by
storage). Split into "L×L class" (last two dims both equal the sequence length) and
"other class", give the bytes-per-L² coefficient per layer and the bytes-per-token for
each, then extrapolate to an 8192 prefix + 45 target segments (L≈9,100) and L=10,000.

Kernels: MATH (= the case where GPU falls back to math) and FLASH_ATTENTION (CPU-side
flash, does not materialize L×L×heads, stands in for GPU mem-efficient to measure the
"non-attention" share of activations). Precision: fp32 and bf16 autocast (the trainer's
convention).

Usage: cprobe-env/bin/python mem_probe.py --L 1024 2048 --out mem_probe.json
"""
import argparse
import json
import os
import sys
import time

import torch
from torch.nn.attention import sdpa_kernel, SDPBackend

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import packed_common as pc  # noqa: E402

N_LAYERS, N_HEADS, HEAD_DIM = 28, 16, 128
VOCAB = 151936


def synth_packed(L, n_seg=8, seg_len=20, seed=0):
    """Packed sequence of random tokens: prefix P = L - n_seg*seg_len, the segments' p values spread evenly across the prefix."""
    g = torch.Generator().manual_seed(seed)
    P = L - n_seg * seg_len
    full = torch.randint(100, 150000, (P,), generator=g).tolist()
    rows = []
    for k in range(n_seg):
        p = int(P * (k + 1) / (n_seg + 1))
        tail = [int(x) for x in torch.randint(100, 150000, (5,), generator=g)]
        tgt = [int(x) for x in torch.randint(100, 150000, (seg_len - 5,), generator=g)]
        rows.append(dict(prompt=full[:p] + tail, tgt=tgt))
    return pc.build_packed(rows, full)


def measure(model, pk, dev, backend, bf16, run_backward=False):
    saved = {}
    L = pk["L"]

    def pack(t):
        key = (t.untyped_storage().data_ptr(), t.untyped_storage().nbytes())
        saved.setdefault(key, (tuple(t.shape), str(t.dtype), t.numel() * t.element_size()))
        return t

    model.zero_grad(set_to_none=True)
    ctx = torch.autocast("cpu", dtype=torch.bfloat16, enabled=bf16)
    t0 = time.time()
    with torch.autograd.graph.saved_tensors_hooks(pack, lambda t: t), sdpa_kernel([backend]), ctx:
        ce, rm = pc.forward_packed(model, pk, dev, "float", torch.bfloat16 if bf16 else torch.float32)
        loss = rm.mean()
    t_fwd = time.time() - t0
    lxl = [(k, v) for k, v in saved.items() if len(v[0]) >= 2 and v[0][-1] == L and v[0][-2] == L]
    other = [(k, v) for k, v in saved.items() if (k, v) not in lxl]
    lxl_storage = sum(k[1] for k, _ in lxl)
    other_storage = sum(k[1] for k, _ in other)
    # no need to run the backward pass: the tensor-saving hooks already fire during the
    # forward pass; on CPU, bf16 backward GEMM is a single-threaded slow path that takes
    # ten-plus minutes per run
    t_bwd = 0.0
    if run_backward:
        t0 = time.time()
        loss.backward()
        t_bwd = time.time() - t0
    del loss, ce, rm
    model.zero_grad(set_to_none=True)
    return dict(L=L, backend=backend.name, bf16=bf16, n_saved=len(saved),
                lxl_bytes=lxl_storage, lxl_count=len(lxl),
                lxl_examples=sorted({(v[0], v[1]) for _, v in lxl}, key=str)[:4],
                lxl_bytes_per_layer_per_L2=lxl_storage / (N_LAYERS * L * L),
                other_bytes=other_storage, other_bytes_per_token=other_storage / L,
                fwd_s=round(t_fwd, 1), bwd_s=round(t_bwd, 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--L", type=int, nargs="+", default=[1024, 2048])
    ap.add_argument("--threads", type=int, default=32)
    ap.add_argument("--backward", action="store_true", help="also run backward (CPU bf16 backward is very slow, off by default)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    torch.set_num_threads(args.threads)
    from transformers import AutoModelForCausalLM
    model = AutoModelForCausalLM.from_pretrained(pc.MODEL, dtype=torch.float32)
    model.train()
    dev = "cpu"
    res = []
    for L in args.L:
        pk = synth_packed(L)
        for bf16 in (True, False):
            for backend in (SDPBackend.FLASH_ATTENTION, SDPBackend.MATH):
                r = measure(model, pk, dev, backend, bf16, args.backward)
                print(json.dumps(r), flush=True)
                res.append(r)
    # extrapolation: L×L class = coefficient × 28 × L²; other class = bytes per token × L
    # (using the coefficient measured at the largest L)
    ext = {}
    for bf16 in (True, False):
        for backend in ("FLASH_ATTENTION", "MATH"):
            rr = [r for r in res if r["bf16"] == bf16 and r["backend"] == backend]
            r = max(rr, key=lambda x: x["L"])
            for L in (8192, 9100, 10000):
                ext[f"{backend}_{'bf16' if bf16 else 'fp32'}_L{L}"] = dict(
                    lxl_GB=round(r["lxl_bytes_per_layer_per_L2"] * N_LAYERS * L * L / 1e9, 2),
                    other_GB=round(r["other_bytes_per_token"] * L / 1e9, 2),
                    math_analytic_GB=round(N_LAYERS * N_HEADS * L * L * 4 / 1e9, 2),
                    logits_all_positions_bf16_GB=round(L * VOCAB * 2 / 1e9, 2))
    out = dict(measurements=res, extrapolation=ext)
    json.dump(out, open(args.out, "w"), indent=1)
    print("EXTRAPOLATION", json.dumps(ext, indent=1))


if __name__ == "__main__":
    main()
