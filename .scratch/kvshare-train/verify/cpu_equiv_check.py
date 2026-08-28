#!/usr/bin/env python
"""缓存复用训练器的注意力形态:CPU 等价验证(Qwen3-0.6B-Base,float32 与 bf16 autocast 各一遍)。

比的是「形态 A 打包一次前向」和「旧训练器逐行前向」在同一行上的 loss:
    每行 loss(目标 token CE 的平均)与逐 token CE,报最大绝对差、最大相对差。
另外三项可选检查(只在第一个事件上做):
    --form-b    形态 B(前缀 use_cache=True,每段带 past_key_values 单独过):loss 是否相同、梯度能否回流前缀
    --grad-ckpt 形态 A 开梯度检查点:loss 是否相同、反向是否能跑
    --lora      形态 A 套 peft LoRA(lora_util 的七件套、r=16):loss 是否相同(B 初始为零)、只有适配器有梯度

用法(仓库根,cprobe-env):
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
    model.train()                       # 训练器是 train 模式;Qwen3 没有 dropout,数值与 eval 相同
    print(f"torch {torch.__version__} transformers {transformers.__version__} "
          f"attn_impl={model.config._attn_implementation}", flush=True)

    events = pc.load_events()
    chosen, n_cand = pc.pick_events(events, args.n_events, args.max_rows, args.max_chars, args.seed)
    print(f"候选事件 {n_cand} 个(行数≤{args.max_rows},全文≤{args.max_chars} 字符),抽 {len(chosen)} 个:{chosen}", flush=True)

    report = dict(torch=torch.__version__, transformers=transformers.__version__,
                  attn_impl=model.config._attn_implementation, seed=args.seed,
                  n_candidates=n_cand, events=[], summary={})
    all_rows = {"fp32": {}, "bf16": {}}   # dtype -> name -> list of tensors(每行 loss)
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
                  f"padding 基线 row max|single-batched|={d['row_diff_old_single_vs_old_batched']['max_abs']:.3e} "
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
    # bf16 对 fp32 自己的偏差(同一形态两种精度):容差的另一把尺子
    for name in ("old_batched", "new_bool"):
        report["summary"][f"row_{name}_bf16_vs_fp32"] = pc.diff_stats(
            torch.cat(all_rows["fp32"][name]), torch.cat(all_rows["bf16"][name]))
        report["summary"][f"tok_{name}_bf16_vs_fp32"] = pc.diff_stats(
            torch.cat(all_tok["fp32"][name]), torch.cat(all_tok["bf16"][name]))
    print("SUMMARY", json.dumps(report["summary"], indent=1), flush=True)

    # ------------------------------------------------------------ 可选检查(第一个事件)
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
    """形态 B:前缀 use_cache=True 过一遍,各段按 p 从大到小 crop 缓存后单独过。

    验两件事:(1) 每行 loss 与旧训练器逐行前向相同(fp32);(2) loss 反向后梯度回流到前缀的输入嵌入。
    """
    from transformers import DynamicCache
    with torch.no_grad():
        _, old_rows = pc.forward_old(model, tok, rows, dev, batched=True)
    model.zero_grad(set_to_none=True)
    emb = model.get_input_embeddings()(torch.tensor(pk["seq"][:pk["P"]], device=dev)[None]).detach().requires_grad_(True)
    cache = DynamicCache(config=model.config)
    # 尾巴为空的行,首个目标 token 由前缀第 p-1 位预测,前缀前向顺便把这些位的 logits 取出来
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
        note="use_cache=True 与 gradient checkpointing 互斥:modeling_layers.py 第 82-84 行在训练态开检查点时把 use_cache 强制改 False",
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
    """套 peft LoRA 后 loss 应与底座相同(B 初始为零),反向只有适配器拿到梯度。放最后跑:就地改模型。"""
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
