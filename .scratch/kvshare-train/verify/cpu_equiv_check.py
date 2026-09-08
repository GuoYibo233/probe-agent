#!/usr/bin/env python
"""Cache-reuse trainer's attention forms: CPU equivalence verification (Qwen3-0.6B-Base,
one pass each with float32 and bf16 autocast).

Compares the loss on the same row between "form A packed into one forward pass" and
"the old trainer's per-row forward pass":
    per-row loss (mean of the target tokens' CE) vs per-token CE, reports the max
    absolute difference and max relative difference.
Three more optional checks (done only on the first event):
    --form-b    form B (prefix with use_cache=True, each segment passed separately with
                past_key_values): whether loss matches, whether gradients flow back to
                the prefix
    --grad-ckpt form A with gradient checkpointing on: whether loss matches, whether the
                backward pass runs
    --lora      form A with peft LoRA attached (lora_util's seven-piece set, r=16):
                whether loss matches (B starts at zero), whether only the adapter gets
                gradients

Usage (repo root, cprobe-env):
  cprobe-env/bin/python /home/y-guo/.claude/jobs/b39c625e/tmp/a2/cpu_equiv_check.py \
      --n-events 5 --form-b --grad-ckpt --lora --out /home/y-guo/.claude/jobs/b39c625e/tmp/a2/equiv_result.json
"""
import argparse
import json
import os
import sys
import time

import torch
import torch.nn.functional as F

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import packed_common as pc  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-events", type=int, default=5)
    ap.add_argument("--max-rows", type=int, default=8)
    ap.add_argument("--max-chars", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--threads", type=int, default=32)
    ap.add_argument("--form-b", action="store_true")
    ap.add_argument("--grad-ckpt", action="store_true")
    ap.add_argument("--lora", action="store_true")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    torch.set_num_threads(args.threads)
    torch.manual_seed(args.seed)
    torch.set_float32_matmul_precision("highest")
    dev = "cpu"

    from transformers import AutoModelForCausalLM, AutoTokenizer
    import transformers
    tok = AutoTokenizer.from_pretrained(pc.MODEL)
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    tok.truncation_side, tok.padding_side = "left", "right"
    model = AutoModelForCausalLM.from_pretrained(pc.MODEL, dtype=torch.float32).to(dev)
    model.train()                       # the trainer is in train mode; Qwen3 has no dropout, so the numbers match eval
    print(f"torch {torch.__version__} transformers {transformers.__version__} "
          f"attn_impl={model.config._attn_implementation}", flush=True)

    events = pc.load_events()
    chosen, n_cand = pc.pick_events(events, args.n_events, args.max_rows, args.max_chars, args.seed)
    print(f"{n_cand} candidate events (rows≤{args.max_rows}, full text≤{args.max_chars} chars), sampled {len(chosen)}: {chosen}", flush=True)

    report = dict(torch=torch.__version__, transformers=transformers.__version__,
                  attn_impl=model.config._attn_implementation, seed=args.seed,
                  n_candidates=n_cand, events=[], summary={})
    all_rows = {"fp32": {}, "bf16": {}}   # dtype -> name -> list of tensors (per-row loss)
    all_tok = {"fp32": {}, "bf16": {}}
    first_pack = None

    for ek in chosen:
        rs = events[ek]
        rows = pc.build_rows(tok, rs)
        full_ids = tok(rs[-1]["text"], add_special_tokens=False)["input_ids"]
        pk = pc.build_packed(rows, full_ids)
        if first_pack is None:
            first_pack = (rows, pk)
        info = dict(event=ek, n_rows=len(rows), P=pk["P"], L=pk["L"],
                    segs=[dict(p=s["p"], prompt_len=s["prompt_len"], n_tail=s["n_tail"], n_tgt=s["n_tgt"])
                          for s in pk["segs"]], runs={})
        for dtype in ("fp32", "bf16"):
            ctx = torch.autocast("cpu", dtype=torch.bfloat16, enabled=(dtype == "bf16"))
            res = {}
            with torch.no_grad(), ctx:
                t0 = time.time()
                res["old_batched"] = pc.forward_old(model, tok, rows, dev, batched=True)
                res["old_single"] = pc.forward_old(model, tok, rows, dev, batched=False)
                res["new_bool"] = pc.forward_packed(model, pk, dev, "bool")
                res["new_float"] = pc.forward_packed(model, pk, dev, "float",
                                                     torch.bfloat16 if dtype == "bf16" else torch.float32)
                dt = time.time() - t0
            for name, (ce, rm) in res.items():
                all_rows[dtype].setdefault(name, []).append(rm)
                all_tok[dtype].setdefault(name, []).append(ce)
            info["runs"][dtype] = dict(
                seconds=round(dt, 1),
                row_loss={k: [round(float(x), 6) for x in v[1]] for k, v in res.items()},
                row_diff_new_bool_vs_old_batched=pc.diff_stats(res["old_batched"][1], res["new_bool"][1]),
                tok_diff_new_bool_vs_old_batched=pc.diff_stats(res["old_batched"][0], res["new_bool"][0]),
                row_diff_new_float_vs_old_batched=pc.diff_stats(res["old_batched"][1], res["new_float"][1]),
                row_diff_old_single_vs_old_batched=pc.diff_stats(res["old_batched"][1], res["old_single"][1]),
                tok_diff_old_single_vs_old_batched=pc.diff_stats(res["old_batched"][0], res["old_single"][0]),
            )
            d = info["runs"][dtype]
            print(f"[{ek}] rows={len(rows)} P={pk['P']} L={pk['L']} {dtype}: "
                  f"row max|new-old|={d['row_diff_new_bool_vs_old_batched']['max_abs']:.3e} "
                  f"(rel {d['row_diff_new_bool_vs_old_batched']['max_rel']:.3e}) "
                  f"tok max|new-old|={d['tok_diff_new_bool_vs_old_batched']['max_abs']:.3e} | "
                  f"padding baseline row max|single-batched|={d['row_diff_old_single_vs_old_batched']['max_abs']:.3e} "
                  f"| {dt:.0f}s", flush=True)
        report["events"].append(info)

    for dtype in ("fp32", "bf16"):
        cat = lambda name, store: torch.cat(store[dtype][name])
        report["summary"][dtype] = dict(
            n_rows=int(cat("old_batched", all_rows).numel()),
            n_tokens=int(cat("old_batched", all_tok).numel()),
            row_new_bool_vs_old_batched=pc.diff_stats(cat("old_batched", all_rows), cat("new_bool", all_rows)),
            row_new_float_vs_old_batched=pc.diff_stats(cat("old_batched", all_rows), cat("new_float", all_rows)),
            row_new_bool_vs_new_float=pc.diff_stats(cat("new_bool", all_rows), cat("new_float", all_rows)),
            row_old_single_vs_old_batched=pc.diff_stats(cat("old_batched", all_rows), cat("old_single", all_rows)),
            tok_new_bool_vs_old_batched=pc.diff_stats(cat("old_batched", all_tok), cat("new_bool", all_tok)),
            tok_old_single_vs_old_batched=pc.diff_stats(cat("old_batched", all_tok), cat("old_single", all_tok)),
            row_loss_abs_max=float(cat("old_batched", all_rows).abs().max()),
            row_loss_mean=float(cat("old_batched", all_rows).mean()),
        )
    # bf16's deviation from fp32 itself (same form, two precisions): another yardstick for
    # tolerance
    for name in ("old_batched", "new_bool"):
        report["summary"][f"row_{name}_bf16_vs_fp32"] = pc.diff_stats(
            torch.cat(all_rows["fp32"][name]), torch.cat(all_rows["bf16"][name]))
        report["summary"][f"tok_{name}_bf16_vs_fp32"] = pc.diff_stats(
            torch.cat(all_tok["fp32"][name]), torch.cat(all_tok["bf16"][name]))
    print("SUMMARY", json.dumps(report["summary"], indent=1), flush=True)

    # ------------------------------------------------------------ optional checks (first event)
    rows, pk = first_pack
    extra = {}
    if args.form_b:
        extra["form_b"] = form_b_check(model, tok, rows, pk, dev)
        print("FORM_B", json.dumps(extra["form_b"], indent=1), flush=True)
    if args.grad_ckpt:
        extra["grad_ckpt"] = grad_ckpt_check(model, pk, dev)
        print("GRAD_CKPT", json.dumps(extra["grad_ckpt"], indent=1), flush=True)
    if args.lora:
        extra["lora"] = lora_check(model, pk, dev)
        print("LORA", json.dumps(extra["lora"], indent=1), flush=True)
    report["extra"] = extra
    json.dump(report, open(args.out, "w"), indent=1, ensure_ascii=False)
    print("written", args.out)


def form_b_check(model, tok, rows, pk, dev):
    """Form B: run the prefix once with use_cache=True, then crop the cache by p in
    descending order and run each segment separately.

    Verifies two things: (1) per-row loss matches the old trainer's per-row forward
    pass (fp32); (2) after loss.backward(), gradients flow back to the prefix's input
    embeddings.
    """
    from transformers import DynamicCache
    with torch.no_grad():
        _, old_rows = pc.forward_old(model, tok, rows, dev, batched=True)
    model.zero_grad(set_to_none=True)
    emb = model.get_input_embeddings()(torch.tensor(pk["seq"][:pk["P"]], device=dev)[None]).detach().requires_grad_(True)
    cache = DynamicCache(config=model.config)
    # for rows with an empty tail, the first target token is predicted by position p-1 of
    # the prefix; the prefix forward pass grabs the logits at these positions along the way
    need_prefix = sorted({s["p"] - 1 for s in pk["segs"] if s["n_tail"] == 0})
    out = model(inputs_embeds=emb, past_key_values=cache, use_cache=True,
                logits_to_keep=torch.tensor(need_prefix, device=dev) if need_prefix else 0)
    prefix_lg = {p: out.logits[0, c].float() for c, p in enumerate(need_prefix)}
    order = sorted(range(len(rows)), key=lambda i: -pk["segs"][i]["p"])
    row_loss = [None] * len(rows)
    total = 0.0
    for i in order:
        s, r = pk["segs"][i], rows[i]
        cache.crop(s["p"])
        seg = r["prompt"][s["p"]:] + r["tgt"]
        pos = torch.arange(s["p"], s["p"] + len(seg), device=dev)[None]
        o = model(input_ids=torch.tensor(seg, device=dev)[None], past_key_values=cache,
                  position_ids=pos, use_cache=True)
        lg = o.logits[0].float()                 # [len(seg), V]
        ces = []
        for t, y in enumerate(r["tgt"]):
            if t == 0 and s["n_tail"] == 0:
                v = prefix_lg[s["p"] - 1]
            else:
                v = lg[s["n_tail"] + t - 1]
            ces.append(F.cross_entropy(v[None], torch.tensor([y], device=dev)))
        row_loss[i] = torch.stack(ces).mean()
        total = total + row_loss[i]
    (total / len(rows)).backward()
    new_rows = torch.stack(row_loss).detach()
    g = emb.grad
    return dict(
        cache_seq_len_after=int(cache.get_seq_length()),
        row_diff_vs_old_batched=pc.diff_stats(old_rows, new_rows),
        prefix_embed_grad_is_none=g is None,
        prefix_embed_grad_absmax=float(g.abs().max()) if g is not None else None,
        prefix_embed_grad_nonzero_positions=int((g.abs().sum(-1) > 0).sum()) if g is not None else None,
        prefix_len=pk["P"],
        note="use_cache=True is mutually exclusive with gradient checkpointing: modeling_layers.py lines 82-84 force use_cache to False when checkpointing is turned on in training mode",
    )


def grad_ckpt_check(model, pk, dev):
    model.zero_grad(set_to_none=True)
    with torch.no_grad():
        _, ref = pc.forward_packed(model, pk, dev, "bool")
    model.gradient_checkpointing_enable()
    model.config.use_cache = False
    ce, rm = pc.forward_packed(model, pk, dev, "bool")
    rm.mean().backward()
    gn = float(model.get_input_embeddings().weight.grad.abs().max())
    model.gradient_checkpointing_disable()
    model.zero_grad(set_to_none=True)
    return dict(row_diff_vs_no_ckpt=pc.diff_stats(ref, rm.detach()), embed_grad_absmax=gn,
                gradient_checkpointing=bool(model.model.gradient_checkpointing))


def lora_check(model, pk, dev):
    """After attaching peft LoRA, loss should match the base model (B starts at zero), and the backward pass gives gradients only to the adapter. Run this last: it modifies the model in place."""
    from peft import LoraConfig, get_peft_model
    with torch.no_grad():
        _, ref = pc.forward_packed(model, pk, dev, "bool")
    cfg = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.0,
                     target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
                     bias="none")
    wrapped = get_peft_model(model, cfg)
    wrapped.train()
    ce, rm = pc.forward_packed(model, pk, dev, "bool")
    rm.mean().backward()
    n_lora_grad = sum(1 for n, p in model.named_parameters() if "lora_" in n and p.grad is not None)
    n_lora = sum(1 for n, p in model.named_parameters() if "lora_" in n)
    n_base_grad = sum(1 for n, p in model.named_parameters() if "lora_" not in n and p.grad is not None)
    return dict(row_diff_vs_base=pc.diff_stats(ref, rm.detach()), n_lora_params=n_lora,
                n_lora_with_grad=n_lora_grad, n_base_params_with_grad=n_base_grad)


if __name__ == "__main__":
    main()
