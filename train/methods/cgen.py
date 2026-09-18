"""The call-generating probe: pack an event's rows by shared token prefix, teacher-force the whole call after the separator, exact-match validation against the environment."""
# venv: probe
from __future__ import annotations

import random
import sys
from pathlib import Path

import torch
import torch.nn.functional as F

from train.utils import trainer

VERSION = 1
PROBE_KIND = "generator"
CHECKPOINT_META = {"call_sep": "\n[CALL] ", "param_only": False}
GEN_N = 200          # val rows generated per validation

_TRAIN_BLOCK_MULT = 2
_VAL_BLOCK_MULT = 2 * _TRAIN_BLOCK_MULT
MAX_TGT_TOK = 160    # target-string token cap; a row over this is dropped whole and counted


def head_labels(df, cfg) -> list[str] | None:
    return None


def _lcp(a: list[int], b: list[int]) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def _pad16(n: int) -> int:
    return ((n + 15) // 16) * 16


def _build_events(df, tok, max_len: int) -> tuple[list[dict], int, int]:
    """Group df's rows by event, per row build the CALL_SEP-tailed segment and the target tokens, drop an overlong event whole and a row whose target exceeds MAX_TGT_TOK. Returns (events, dropped_overlong, dropped_tgt)."""
    dropped_overlong = 0
    dropped_tgt = 0
    eos_id = tok.eos_token_id
    events = []
    for _event_id, group in df.group_by("event_id", maintain_order=True):
        rows = group.sort("cut_index").to_dicts()
        full_row = max(rows, key=lambda r: len(r["text"]))
        full_ids = tok(full_row["text"], add_special_tokens=False, truncation=False)["input_ids"]
        if len(full_ids) > max_len:
            dropped_overlong += 1
            continue
        packed_rows = []
        for r in rows:
            old_ids = tok(r["text"] + CHECKPOINT_META["call_sep"], add_special_tokens=False,
                         truncation=False)["input_ids"]
            p = _lcp(old_ids, full_ids)
            tail_ids = old_ids[p:]
            assert len(tail_ids) >= 1, (
                f"event {r['event_id']} cut_index={r['cut_index']}: the common prefix consumed "
                "the whole call-separator tail")
            tgt_ids = tok(r["call"], add_special_tokens=False)["input_ids"] + [eos_id]
            if len(tgt_ids) > MAX_TGT_TOK:
                dropped_tgt += 1
                continue
            seg_ids = tail_ids + tgt_ids
            seg_lab = [-100] * len(tail_ids) + tgt_ids
            packed_rows.append({"row": r, "p": p, "seg_ids": seg_ids, "seg_lab": seg_lab})
        if not packed_rows:
            continue
        prefix_len = max(pr["p"] for pr in packed_rows)
        packed_len = prefix_len + sum(len(pr["seg_ids"]) for pr in packed_rows)
        events.append({"full_ids": full_ids, "prefix_len": prefix_len,
                       "packed_len": packed_len, "rows": packed_rows})
    return events, dropped_overlong, dropped_tgt


def _chunk_by_budget(events: list[dict], budget: int) -> list[list[dict]]:
    ordered = sorted(events, key=lambda e: e["packed_len"], reverse=True)
    blocks: list[list[dict]] = []
    current: list[dict] = []
    current_max = 0
    for e in ordered:
        n = len(current) + 1
        cand_max = current_max if current else e["packed_len"]
        if n * _pad16(cand_max) <= budget:
            current.append(e)
            current_max = cand_max
        else:
            if current:
                blocks.append(current)
            current = [e]
            current_max = e["packed_len"]
    if current:
        blocks.append(current)
    return blocks


def _make_batch(block_events: list[dict]) -> dict:
    """One physical block's Batch: input_ids, the 4-D block-diagonal additive mask, position_ids, and this method's own event_end (one per target token, the query position t-1), target_ids, row_of, weight and example_id (the last two, one per decision row)."""
    packed = []
    for ev in block_events:
        P = ev["prefix_len"]
        tokens = list(ev["full_ids"][:P])
        positions = list(range(P))
        labels = [-100] * P
        row_index = [-1] * P
        row_ranges = []
        own_p = []
        for k, pr in enumerate(ev["rows"]):
            start = len(tokens)
            tokens.extend(pr["seg_ids"])
            positions.extend(range(pr["p"], pr["p"] + len(pr["seg_ids"])))
            labels.extend(pr["seg_lab"])
            row_index.extend([k] * len(pr["seg_ids"]))
            row_ranges.append((start, len(tokens)))
            own_p.append(pr["p"])
        packed.append({"tokens": tokens, "positions": positions, "labels": labels,
                       "row_index": row_index, "row_ranges": row_ranges, "own_p": own_p,
                       "rows": ev["rows"]})

    L_pad = _pad16(max(len(p["tokens"]) for p in packed))
    B = len(packed)
    input_ids = torch.zeros((B, L_pad), dtype=torch.long)
    position_ids = torch.zeros((B, L_pad), dtype=torch.long)
    attn = torch.full((B, 1, L_pad, L_pad), float("-inf"), dtype=torch.float32)

    event_end: list[tuple[int, int]] = []
    target_ids: list[int] = []
    row_of: list[int] = []
    weight: list[float] = []
    example_id: list[str] = []
    global_row = 0

    for b, p in enumerate(packed):
        L = len(p["tokens"])
        input_ids[b, :L] = torch.tensor(p["tokens"], dtype=torch.long)
        position_ids[b, :L] = torch.tensor(p["positions"], dtype=torch.long)
        if L < L_pad:
            last_pos = p["positions"][-1] if p["positions"] else -1
            position_ids[b, L:] = torch.arange(last_pos + 1, last_pos + 1 + (L_pad - L), dtype=torch.long)

        row_index = torch.tensor(p["row_index"], dtype=torch.long)
        idx = torch.arange(L)
        is_prefix = row_index < 0
        causal = idx.unsqueeze(0) <= idx.unsqueeze(1)
        prefix_prefix = is_prefix.unsqueeze(1) & is_prefix.unsqueeze(0) & causal
        same_row = row_index.unsqueeze(1) == row_index.unsqueeze(0)
        seg_self = same_row & (~is_prefix).unsqueeze(1) & causal
        qp = torch.zeros(L, dtype=torch.long)
        for k, (start, end) in enumerate(p["row_ranges"]):
            qp[start:end] = p["own_p"][k]
        seg_sees_prefix = (~is_prefix).unsqueeze(1) & is_prefix.unsqueeze(0) & (idx.unsqueeze(0) < qp.unsqueeze(1))
        allowed = prefix_prefix | seg_self | seg_sees_prefix

        block = torch.full((L_pad, L_pad), float("-inf"), dtype=torch.float32)
        real = torch.zeros((L, L), dtype=torch.float32)
        real.masked_fill_(~allowed, float("-inf"))
        block[:L, :L] = real
        for i in range(L, L_pad):
            block[i, i] = 0.0
        attn[b, 0] = block

        for k, pr in enumerate(p["rows"]):
            weight.append(float(pr["row"]["weight"]))
            example_id.append(pr["row"]["example_id"])
        for t in range(1, L):
            if p["labels"][t] != -100:
                event_end.append((b, t - 1))
                target_ids.append(p["labels"][t])
                row_of.append(global_row + p["row_index"][t])
        global_row += len(p["rows"])

    return {
        "input_ids": input_ids,
        "attention_mask": attn,
        "position_ids": position_ids,
        "event_end": torch.tensor(event_end, dtype=torch.long),
        "target_ids": torch.tensor(target_ids, dtype=torch.long),
        "row_of": torch.tensor(row_of, dtype=torch.long),
        "weight": torch.tensor(weight, dtype=torch.float32),
        "example_id": example_id,
    }


def batches(df, tok, cfg):
    """Group by event_id, pack each event to its shared-prefix sequence with every row's target appended after CALL_SEP, split into logical minibatches after a shuffle, then into physical blocks by 2 * cfg.train.max_len tokens.

    One call is one pass over df ('mb' starts at 0 every call); trainer.run calls this fresh once
    per epoch (see train/methods/ctool.py's batches for why this function reads no epoch).
    """
    events, _o, _t = _build_events(df, tok, cfg.train.max_len)
    budget = _TRAIN_BLOCK_MULT * cfg.train.max_len
    shuffled = list(events)
    random.Random(cfg.train.seed).shuffle(shuffled)
    mb = 0
    for i in range(0, len(shuffled), cfg.train.events_per_mb):
        group = shuffled[i:i + cfg.train.events_per_mb]
        if not group:
            continue
        w_total = sum(pr["row"]["weight"] for ev in group for pr in ev["rows"])
        for block in _chunk_by_budget(group, budget):
            batch = _make_batch(block)
            batch["mb"] = mb
            batch["mb_weight"] = w_total
            yield batch
        mb += 1


def _row_mean_ce(probe, batch):
    """Token CE aggregated to a per-row mean by index_add over row_of, divided by each row's target-token count."""
    out = probe.forward(batch)
    tok_ce = F.cross_entropy(out.logits.float(), batch["target_ids"], reduction="none")
    n_rows = batch["weight"].shape[0]
    row_of = batch["row_of"]
    ssum = torch.zeros(n_rows).index_add(0, row_of, tok_ce)
    cnt = torch.zeros(n_rows).index_add(0, row_of, torch.ones_like(tok_ce))
    return ssum / cnt.clamp(min=1)


def loss(probe, batch):
    """The unnormalised weighted sum of the per-row mean CE."""
    row_ce = _row_mean_ce(probe, batch)
    return (row_ce * batch["weight"]).sum()


def reference_loss(probe, df):
    """The same weighted sum, one row per sequence, in its plainest form: left-truncated prompt, right padding, labels masking the prompt, per-instance mean CE."""
    tok = probe.tokenizer
    max_len = probe.max_len
    eos_id = tok.eos_token_id
    rows = df.to_dicts()
    seqs = []
    for r in rows:
        tgt_ids = tok(r["call"], add_special_tokens=False)["input_ids"] + [eos_id]
        budget = max(max_len - len(tgt_ids), 1)
        prompt_full = tok(r["text"] + CHECKPOINT_META["call_sep"], add_special_tokens=False,
                          truncation=False)["input_ids"]
        prompt_ids = prompt_full[-budget:] if len(prompt_full) > budget else prompt_full
        seq_ids = prompt_ids + tgt_ids
        seg_lab = [-100] * len(prompt_ids) + tgt_ids
        seqs.append((seq_ids, seg_lab, float(r["weight"])))

    L = max((len(s) for s, _lab, _w in seqs), default=1)
    B = len(seqs)
    input_ids = torch.zeros((B, L), dtype=torch.long)
    attention_mask = torch.zeros((B, L), dtype=torch.long)
    event_end: list[tuple[int, int]] = []
    target_ids: list[int] = []
    row_of: list[int] = []
    for i, (seq_ids, seg_lab, _w) in enumerate(seqs):
        li = len(seq_ids)
        input_ids[i, :li] = torch.tensor(seq_ids, dtype=torch.long)
        attention_mask[i, :li] = 1
        for t in range(1, li):
            if seg_lab[t] != -100:
                event_end.append((i, t - 1))
                target_ids.append(seg_lab[t])
                row_of.append(i)

    batch = {"input_ids": input_ids, "attention_mask": attention_mask,
             "event_end": torch.tensor(event_end, dtype=torch.long),
             "target_ids": torch.tensor(target_ids, dtype=torch.long),
             "row_of": torch.tensor(row_of, dtype=torch.long),
             "weight": torch.tensor([w for _s, _l, w in seqs], dtype=torch.float32)}
    row_ce = _row_mean_ce(probe, batch)
    return (row_ce * batch["weight"]).sum()


def _weighted_val_ce(probe, df, tok, cfg) -> float:
    events, _o, _t = _build_events(df, tok, cfg.train.max_len)
    budget = _VAL_BLOCK_MULT * cfg.train.max_len
    total_loss = 0.0
    total_weight = 0.0
    with torch.no_grad():
        for block in _chunk_by_budget(events, budget):
            batch = _make_batch(block)
            total_loss += float(loss(probe, batch))
            total_weight += float(batch["weight"].sum())
    return total_loss / total_weight if total_weight > 0 else 0.0


def validate(probe, df, tok, cfg):
    """The weighted val CE over the whole frame through the packed path, plus greedy generation over a deterministic GEN_N-row subsample compared with probe_eval.match_cgen."""
    from data.environments import open_env
    from eval.utils import probe_eval

    val_ce = _weighted_val_ce(probe, df, tok, cfg)

    rows = df.sort("example_id").to_dicts()
    random.Random(cfg.train.seed).shuffle(rows)
    sample = rows[:GEN_N] if GEN_N > 0 else []
    env = open_env(cfg.data.env)
    texts = [r["text"] for r in sample]
    preds = probe.generate(texts, cfg.train.predict.max_new, CHECKPOINT_META["call_sep"]) if sample else []

    total_w = sum(r["weight"] for r in sample) or 1.0
    tool_ok_w = params_ok_w = full_ok_w = 0.0
    for r, pred in zip(sample, preds):
        m = probe_eval.match_cgen(pred, r["call"], env)
        w = r["weight"]
        tool_ok_w += w * float(m["tool_ok"])
        params_ok_w += w * float(m["params_all_ok"])
        full_ok_w += w * float(m["full_call_ok"])
    tool_ok = tool_ok_w / total_w
    params_ok = params_ok_w / total_w
    full_ok = full_ok_w / total_w
    return {"objective": 1.0 - full_ok, "val_ce": val_ce, "val_tool_ok": tool_ok,
           "val_params_all_ok": params_ok, "val_full_call_ok": full_ok, "gen_n": len(sample)}


def predict(probe, df, tok, cfg):
    """One row per example row: the probe's own greedy continuation after its own CALL_SEP."""
    rows = df.to_dicts()
    texts = [r["text"] for r in rows]
    outs = probe.generate(texts, cfg.train.predict.max_new, CHECKPOINT_META["call_sep"]) if rows else []
    for r, out in zip(rows, outs):
        gen_tokens = len(tok(out, add_special_tokens=False)["input_ids"])
        yield {"example_id": r["example_id"], "method": "cgen", "target": r["call"],
               "text_pred": out, "gen_tokens": gen_tokens}


def main(run_dir: Path) -> None:
    trainer.run(run_dir, sys.modules[__name__])


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()
    main(Path(args.run_dir))
