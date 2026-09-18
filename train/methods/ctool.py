"""The classification probe: pack an event's rows by shared token prefix, decide at each row's own last token, weighted cross-entropy against the tool head."""
# venv: probe
from __future__ import annotations

import random
import sys
from pathlib import Path

import torch
import torch.nn.functional as F

from train.utils import trainer

VERSION = 1
PROBE_KIND = "classifier"
CHECKPOINT_META = {"call_sep": None, "param_only": False}

# No setting field gives a physical block's token budget (construction-plan errata): a training
# block holds as many events as fit under _TRAIN_BLOCK_MULT * cfg.train.max_len tokens, and
# validate/predict use twice that.
_TRAIN_BLOCK_MULT = 2
_VAL_BLOCK_MULT = 2 * _TRAIN_BLOCK_MULT


def head_labels(df, cfg) -> list[str] | None:
    """The unique tool values of the whole frame, sorted ascending -- never computed over the training split alone (1.3)."""
    return sorted(df["tool"].unique().to_list())


def _lcp(a: list[int], b: list[int]) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def _pad16(n: int) -> int:
    return ((n + 15) // 16) * 16


def _build_events(df, tok, max_len: int) -> tuple[list[dict], int]:
    """Group df's rows by event, tokenize the longest text as the event's full_ids and every row's own text, and drop an event whole when its longest text tokenizes past max_len. Returns (events, dropped_count)."""
    dropped = 0
    events = []
    for _event_id, group in df.group_by("event_id", maintain_order=True):
        rows = group.sort("cut_index").to_dicts()
        full_row = max(rows, key=lambda r: len(r["text"]))
        full_ids = tok(full_row["text"], add_special_tokens=False, truncation=False)["input_ids"]
        if len(full_ids) > max_len:
            dropped += 1
            continue
        packed_rows = []
        for r in rows:
            row_ids = tok(r["text"], add_special_tokens=False, truncation=False)["input_ids"]
            p = _lcp(row_ids, full_ids)
            packed_rows.append({"row": r, "p": p, "tail_ids": row_ids[p:]})
        prefix_len = max(pr["p"] for pr in packed_rows)
        packed_len = prefix_len + sum(len(pr["tail_ids"]) for pr in packed_rows)
        events.append({"full_ids": full_ids, "prefix_len": prefix_len,
                       "packed_len": packed_len, "rows": packed_rows})
    return events, dropped


def _chunk_by_budget(events: list[dict], budget: int) -> list[list[dict]]:
    """Greedy block packing: sort events by descending packed_len, pack while count * pad16(block's longest) <= budget; an over-budget single event becomes its own block."""
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
    """One physical block's Batch: input_ids, the 4-D block-diagonal additive mask, position_ids, event_end, and this method's own target/weight/example_id, one entry per decision row, packing order; `_rows` carries the source row dicts in the same order for validate's own bookkeeping."""
    packed = []
    for ev in block_events:
        P = ev["prefix_len"]
        tokens = list(ev["full_ids"][:P])
        positions = list(range(P))
        row_index = [-1] * P
        row_ranges = []
        own_p = []
        for k, pr in enumerate(ev["rows"]):
            start = len(tokens)
            tokens.extend(pr["tail_ids"])
            positions.extend(range(pr["p"], pr["p"] + len(pr["tail_ids"])))
            row_index.extend([k] * len(pr["tail_ids"]))
            row_ranges.append((start, len(tokens)))
            own_p.append(pr["p"])
        packed.append({"tokens": tokens, "positions": positions, "row_index": row_index,
                       "row_ranges": row_ranges, "own_p": own_p, "rows": ev["rows"]})

    L_pad = _pad16(max(len(p["tokens"]) for p in packed))
    B = len(packed)
    input_ids = torch.zeros((B, L_pad), dtype=torch.long)
    position_ids = torch.zeros((B, L_pad), dtype=torch.long)
    attn = torch.full((B, 1, L_pad, L_pad), float("-inf"), dtype=torch.float32)

    event_end: list[tuple[int, int]] = []
    target: list[str] = []
    weight: list[float] = []
    example_id: list[str] = []
    src_rows: list[dict] = []

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
            block[i, i] = 0.0   # a pad row as query only attends to itself
        attn[b, 0] = block

        for k, (start, end) in enumerate(p["row_ranges"]):
            pos = end - 1 if end > start else p["own_p"][k] - 1
            event_end.append((b, pos))
            row = p["rows"][k]["row"]
            target.append(row["tool"])
            weight.append(float(row["weight"]))
            example_id.append(row["example_id"])
            src_rows.append(row)

    return {
        "input_ids": input_ids,
        "attention_mask": attn,
        "position_ids": position_ids,
        "event_end": torch.tensor(event_end, dtype=torch.long),
        "target": target,
        "weight": torch.tensor(weight, dtype=torch.float32),
        "example_id": example_id,
        "_rows": src_rows,
    }


def batches(df, tok, cfg):
    """Group by event_id, pack each event to its shared-prefix sequence, split into logical minibatches of cfg.train.events_per_mb after a shuffle, then into physical blocks by 2 * cfg.train.max_len tokens.

    One call is one pass over df ('mb' starts at 0 every call); trainer.run calls this fresh once
    per epoch, so the epoch-to-epoch variation the construction plan describes as
    `random.Random(cfg.train.seed + epoch)` lives in which epoch calls this, not in a parameter
    this function takes -- 2.6 pins `batches(df, tok, cfg)` with no epoch argument, and this
    module's own acceptance fixture (A3.3) hands a `cfg.train` with no `epochs` field at all.
    """
    events, _dropped = _build_events(df, tok, cfg.train.max_len)
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


def loss(probe, batch):
    """Weighted cross-entropy sum over this batch's decision rows -- the unnormalised weighted sum, since a per-batch mean is not additive across the alignment gate's sum (2.6)."""
    out = probe.forward(batch)
    y = torch.tensor([probe.labels.index(t) for t in batch["target"]], dtype=torch.long)
    ce = F.cross_entropy(out.logits.float(), y, reduction="none")
    return (ce * batch["weight"]).sum()


def reference_loss(probe, df):
    """The same weighted cross-entropy sum, one example row per sequence, in its plainest form: tokenize each row's text alone, right-pad, a plain 2-D mask, no position_ids."""
    tok = probe.tokenizer
    rows = df.to_dicts()
    ids_list = [tok(r["text"], add_special_tokens=False, truncation=False)["input_ids"] for r in rows]
    length = max((len(x) for x in ids_list), default=1)
    input_ids = torch.zeros((len(rows), length), dtype=torch.long)
    attention_mask = torch.zeros((len(rows), length), dtype=torch.long)
    event_end = torch.zeros((len(rows), 2), dtype=torch.long)
    for i, ids in enumerate(ids_list):
        input_ids[i, :len(ids)] = torch.tensor(ids, dtype=torch.long)
        attention_mask[i, :len(ids)] = 1
        event_end[i] = torch.tensor([i, max(len(ids) - 1, 0)])
    batch = {"input_ids": input_ids, "attention_mask": attention_mask, "event_end": event_end}
    out = probe.forward(batch)
    y = torch.tensor([probe.labels.index(r["tool"]) for r in rows], dtype=torch.long)
    w = torch.tensor([float(r["weight"]) for r in rows], dtype=torch.float32)
    ce = F.cross_entropy(out.logits.float(), y, reduction="none")
    return (ce * w).sum()


def _score_frame(probe, df, tok, cfg, block_mult: int) -> list[dict]:
    """Every row of df through the packed path: one dict per row with target, weight, cut_index/n_cuts (for the last-cut accuracy), score, label_pred and logits, all read through probe.labels order."""
    events, _dropped = _build_events(df, tok, cfg.train.max_len)
    budget = block_mult * cfg.train.max_len
    out = []
    with torch.no_grad():
        for block in _chunk_by_budget(events, budget):
            batch = _make_batch(block)
            logits = probe.forward(batch).logits.float()
            probs = torch.softmax(logits, dim=-1)
            top_score, top_idx = probs.max(dim=-1)
            for i, row in enumerate(batch["_rows"]):
                out.append({
                    "example_id": batch["example_id"][i], "target": batch["target"][i],
                    "weight": float(batch["weight"][i]), "cut_index": row["cut_index"],
                    "n_cuts": row["n_cuts"], "score": float(top_score[i]),
                    "label_pred": probe.labels[int(top_idx[i])],
                    "logits": [float(x) for x in logits[i].tolist()],
                })
    return out


def validate(probe, df, tok, cfg):
    """Score the frame through the packed path, compare with probe_eval.match_ctool, and return weighted accuracy plus the last-cut accuracy (an extra number, not the objective)."""
    from eval.utils import probe_eval

    scored = _score_frame(probe, df, tok, cfg, _VAL_BLOCK_MULT)
    total_w = sum(r["weight"] for r in scored)
    correct_w = sum(r["weight"] for r in scored
                    if probe_eval.match_ctool(r["label_pred"], r["target"], None))
    wacc = correct_w / total_w if total_w > 0 else 0.0
    last_rows = [r for r in scored if r["cut_index"] == r["n_cuts"] - 1]
    lastcut_acc = (sum(1 for r in last_rows if probe_eval.match_ctool(r["label_pred"], r["target"], None))
                  / len(last_rows)) if last_rows else 0.0
    return {"objective": 1.0 - wacc, "val_wacc": wacc, "val_lastcut_acc": lastcut_acc}


def predict(probe, df, tok, cfg):
    """One row per example row, through the same packed path (not Probe.score, which would cost build.max_cuts times the packed pass)."""
    scored = _score_frame(probe, df, tok, cfg, _VAL_BLOCK_MULT)
    for r in scored:
        yield {"example_id": r["example_id"], "method": "ctool", "target": r["target"],
               "score": r["score"], "label_pred": r["label_pred"], "logits": r["logits"]}


def main(run_dir: Path) -> None:
    trainer.run(run_dir, sys.modules[__name__])


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()
    main(Path(args.run_dir))
