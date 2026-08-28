#!/usr/bin/env python
"""在 CPU 上复现学习率扫描 run 的 epoch 0 全部物理块(全量 train, 种子 42, 预算 16384,
逻辑小批 4 个事件, accum 2), 以及 val 全集在评估预算 32768 下的块; 输出块的统计,
给 design-attention 第九节的显存/时间估算用. 只读数据, 不碰 GPU."""
import json
import math
import random
import sys
import time
from collections import Counter

sys.path.insert(0, "pipeline/train")
from transformers import AutoTokenizer  # noqa: E402
import share_data  # noqa: E402
import train_causal_callgen as cg  # noqa: E402

DATA = "pipeline/data/nyapass_aw_v1/gptoss"
OUT = sys.argv[1] if len(sys.argv) > 1 else "/home/y-guo/.claude/jobs/1c030365/tmp/enum_blocks.json"
TOK_BUDGET, EVAL_BUDGET, EPM, ACCUM, SEED = 16384, 32768, 4, 2, cg.SEED


def pad16(n):
    return ((n + 15) // 16) * 16


def block_stats(blk):
    B = len(blk)
    l_pad = pad16(max(e["packed_len"] for e in blk))
    rows = sum(len(e["rows"]) for e in blk)
    loss = sum(sum(1 for x in row[4] if x != -100) for e in blk for row in e["rows"])
    real = sum(e["packed_len"] for e in blk)
    return dict(B=B, L_pad=l_pad, tokens=B * l_pad, real=real, rows=rows, loss=loss,
                events=[e["event"] for e in blk])


def main():
    tok = AutoTokenizer.from_pretrained(cg.MODELS["qwen"])
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    tok.truncation_side = "left"
    tok.padding_side = "right"
    res = {}
    for split, budget, do_epoch in (("train", TOK_BUDGET, True), ("val", EVAL_BUDGET, False)):
        t0 = time.time()
        events, counts = share_data.load_events(f"{DATA}/{split}.jsonl", tok, "cgen", 8192,
                                                ro=None, limit=0)
        load_s = time.time() - t0
        print(split, "load_s", round(load_s, 1), counts, "n_events", len(events), flush=True)
        if do_epoch:
            ep = list(events)
            random.Random(SEED + 0).shuffle(ep)
            mbs = [ep[i:i + EPM] for i in range(0, len(ep), EPM)]
        else:
            mbs = [events]
        blocks = []
        for mi, mb in enumerate(mbs):
            for blk in share_data.chunk_by_budget(mb, budget):
                st = block_stats(blk)
                st["mb"] = mi
                st["group"] = mi // ACCUM if do_epoch else 0
                blocks.append(st)
        M = len(mbs)
        U = math.ceil(M / ACCUM) if do_epoch else None
        tot_tokens = sum(b["tokens"] for b in blocks)
        tot_real = sum(b["real"] for b in blocks)
        tot_loss = sum(b["loss"] for b in blocks)
        max_T = max(blocks, key=lambda b: b["tokens"])
        max_P = max(blocks, key=lambda b: b["loss"])
        tmax, pmax = max_T["tokens"], max_P["loss"]
        max_norm = max(blocks, key=lambda b: b["tokens"] / tmax + b["loss"] / pmax)
        coef = {"b06_nogc": (2.44, 1.8), "b17_nogc": (3.8, 1.8), "b06_gc": (0.19, 1.8),
                "b17_gc": (0.34, 1.8), "b4_gc": (0.55, 1.8)}
        by_cost = {}
        for name, (a, b) in coef.items():
            top = sorted(blocks, key=lambda x: a * x["tokens"] / 1e3 + b * x["loss"] / 1e3,
                         reverse=True)[:3]
            by_cost[name] = [dict(t, cost_gb=round(a * t["tokens"] / 1e3 + b * t["loss"] / 1e3, 2))
                             for t in top]
        hist_B = Counter(b["B"] for b in blocks)
        # 每个更新组里 token 最多的块与损失位最多的块(loop 模式挑组用)
        groups = {}
        for b in blocks:
            g = groups.setdefault(b["group"], dict(tokens=0, loss=0, blocks=0))
            g["tokens"] = max(g["tokens"], b["tokens"])
            g["loss"] = max(g["loss"], b["loss"])
            g["blocks"] += 1
        res[split] = dict(load_s=round(load_s, 1), counts=counts, n_events=len(events),
                          M=M, U=U, n_blocks=len(blocks), tot_tokens=tot_tokens,
                          tot_real=tot_real, tot_loss=tot_loss, pad_frac=round(1 - tot_real / tot_tokens, 4),
                          hist_B=dict(hist_B), max_T=max_T, max_P=max_P, max_norm=max_norm,
                          by_cost=by_cost,
                          loss_pos_quantiles=sorted(b["loss"] for b in blocks)[::max(1, len(blocks) // 10)],
                          tokens_quantiles=sorted(b["tokens"] for b in blocks)[::max(1, len(blocks) // 10)],
                          n_blocks_over_4000_loss=sum(1 for b in blocks if b["loss"] > 4000),
                          n_blocks_over_5000_loss=sum(1 for b in blocks if b["loss"] > 5000),
                          group_of_max_P=max_P["group"], group_of_max_T=max_T["group"],
                          groups_with_maxP=groups.get(max_P["group"]),
                          longest_event=max((dict(event=e["event"], packed_len=e["packed_len"],
                                                  rows=len(e["rows"]),
                                                  loss=sum(1 for row in e["rows"] for x in row[4] if x != -100))
                                             for e in events), key=lambda d: d["packed_len"]))
        json.dump(res, open(OUT, "w"), indent=1, ensure_ascii=False)
        print(json.dumps({k: v for k, v in res[split].items() if k != "by_cost"}, ensure_ascii=False), flush=True)
        print("by_cost:", json.dumps(res[split]["by_cost"], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
