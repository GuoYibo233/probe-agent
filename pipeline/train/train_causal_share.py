"""Causal cache-reuse trainer (the new pipeline's shared cgen / cparam cell, pick one with
`--mode`): the full text of one event passes through the backbone only once, and each cut's
target segment is appended after the shared prefix to compute loss.

Relationship to the old row-by-row trainers (`train_causal_callgen.py` /
`train_causal_param.py`): the old scripts run one forward pass per row (prompt tokenized from
scratch, right padding); this script packs all the rows of the same event into one sequence for
a single forward pass (form A, verified in `design-attention.md`); in theory the per-row loss is
identical to the old trainer token for token (that's exactly what the alignment check in
section 9 verifies), it just skips the repeated computation of the same shared prefix across
rows.

- Data and tokenization: `pipeline/train/share_data.py` (pure CPU, cgen/cparam share one set of
  `load_events`/`pack_event`/`batch_mask`/`chunk_by_budget`/`worst_blocks`).
- Tokenizer and model: calls the old script's `train_causal_callgen.build(dev, base,
  attn_impl=, path=)` directly (spec 3.4, decision 6; `--base` is qwen/qwen17/qwen4 or a model
  directory path, the latter goes through `build(path=...)`, for testing with small models).
- Forward form: form A from `design-attention.md` -- multiple events laid out along the batch
  dimension, one bf16 (or fp32, for the alignment check) additive mask per physical block,
  `attn_implementation="sdpa"`, and all three forward passes (training / eval / alignment check)
  wrap `sdpa_kernel([SDPBackend.EFFICIENT_ATTENTION])` on cuda (this context has no effect on
  CPU kernels, so it's skipped on CPU). Only the hidden states at loss positions are taken
  through `lm_head`; full-position logits are never computed.
- Loss and update units: a logical minibatch = all the rows of `--events-per-mb` (default 4)
  events, split into physical blocks by token budget; one update = `--accum` (default 2) logical
  minibatches = 8 events.
- Alignment check (section 9): before training starts (and with `--align-only`), before
  `lora_util.wrap`, under `model.eval()`, with TF32 off in fp32, sample `--align-events` short
  val events, feed the same temp jsonl into the new path (`share_data.load_events`) and the
  reference path (old `collate` + actually calling `inst_ce` to get per-row ce; the intermediate
  values needed for the per-token threshold are computed separately, locally, with the same set
  of formulas -- the two fp32-gate passes each assert, per batch, that they match `inst_ce`'s
  return value; the bf16 coarse-screening pass turns this self-check off, ticket 05 S2), then
  compare per-row/per-token by paired position. The reference path does not wrap
  EFFICIENT_ATTENTION (its "single row, unpadded" batches have no mask, so HF goes through
  `enable_gqa`, mem-efficient doesn't support GQA, and forcing the kernel would raise an error --
  only the new path, which always carries a mask, wraps this context).

Usage:
  # alignment check only
  cprobe-env/bin/python pipeline/train/train_causal_share.py --mode cgen \
    --data pipeline/data/nyapass_aw_v1/gptoss --out pipeline/runs/x --align-only
  # smoke test
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
    raise SystemExit(f"cprobe line requires transformers>=5.14, current "
                     f"{transformers.__version__} -- wrong interpreter?"
                     "always go through run.py's tasks (train-cgen/train-cparam).")
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


# spec section 9: only sample events whose full-text token count is under this cap for the
# alignment check (to control runtime).
ALIGN_LEN_FILTER = 2048
# row count for the reference path's "whole batch", matching the old trainer's --bs 4
# (spec section 9).
REF_BATCH = 4
# The maximum allowed difference between the per-row result that `_ref_forward` aggregates
# locally from the per-token formula and the return value of the actual `inst_ce` call (the same
# batch of data, one no_grad forward pass, called twice; in theory they should be bit-identical
# -- this tolerance only guards against tiny floating-point summation-order jitter under
# different kernel scheduling, one order of magnitude below --align-tol's 2e-5, 1000x away from
# a real formula misalignment (on the order of 1e-2), so it will not let a structural
# misalignment slip through).
REF_INST_CE_DRIFT_TOL = 1e-6


class RefBaselineDriftError(RuntimeError):
    """`_ref_forward`'s self-check failure: the per-row result aggregated locally from the
    per-token formula differs from the return value of the actual `inst_ce` call by more than
    `REF_INST_CE_DRIFT_TOL`, meaning the reference baseline itself is not trustworthy. This uses
    a real exception rather than a bare `assert`, because a bare `assert` is stripped entirely
    and silently allowed through under `-O`/`PYTHONOPTIMIZE` -- this check is the only runtime
    validation in this file that determines "whether the reference baseline is trustworthy",
    and it must not have a silent-failure path.
    `run_align_check` catches this exception and handles it the same way as every other failure
    branch in the file: write `ALIGN_CHECK.json`, print diagnostics, `sys.exit(2)`."""


# ---------------------------------------------------------------- forward form

def _attn_ctx(dev):
    """Pins mem-efficient on cuda (the ruling in design-attention.md section 3); on CPU this
    context raises `No viable backend`, so it's skipped, falling back to the default kernel
    (spec section 4)."""
    if str(dev).startswith("cuda"):
        return sdpa_kernel([SDPBackend.EFFICIENT_ATTENTION])
    return contextlib.nullcontext()


def _l_pad(events):
    """The padded length of a physical block for a group of events: the longest `packed_len` in
    the block, padded up to a multiple of 16, using the same accounting as the padding in
    `share_data.batch_mask`/`chunk_by_budget` (spec sections 4 and 5)."""
    longest = max(ev["packed_len"] for ev in events)
    return ((longest + 15) // 16) * 16


def _base_model_and_head(model):
    """How to get `model.model` and `model.lm_head`, compatible with peft's wrapped object
    (ticket 05 S1). `lora_util.wrap` injects in place -- after wrapping, the caller's original
    hf_model variable is still the original model, with `.model`/`.lm_head` directly available;
    this also additionally supports the calling style where "what's in hand is the PeftModel
    itself", using `get_base_model()` to reach down to the original backbone / lm_head on the
    backbone (peft only replaces the seven nn.Linear modules, it doesn't change this layer's
    structure)."""
    base = model.get_base_model() if hasattr(model, "get_base_model") else model
    return base.model, base.lm_head


def _forward_packed(model, events, dev, mask_dtype):
    """Forward pass for one physical block (`events`): calls `model.model(...)` to get the
    backbone's `last_hidden_state` directly (the old approach let the upper `ForCausalLM.forward`
    emit the hidden states of every layer and then took the last element of the tuple -- that
    path relies on HF's convention of appending the last layer to the end of the tuple, and
    under `--grad-ckpt` it records the hidden states of all 28 layers, about 1.9 GB for a
    16k-token block), gathers at the loss positions and then runs `model.lm_head`
    (spec section 4), never computing full-position logits (ticket 05 S1).

    Returns `(tok_ce [n_tgt] tensor (on dev), global_row [n_tgt] list, n_rows_total
    int)` -- `global_row[i]` is the global row number, within this physical block, of the
    target token that `tok_ce[i]` corresponds to (accumulated across events: event 0's rows
    come first, then event 1's rows continue counting, and so on).
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
    """Per-token CE -> per-row mean CE (the same accounting as `inst_ce`: average the
    cross-entropy over this row's target token positions, denominator is this row's target
    token count, spec section 4, final paragraph)."""
    rid = torch.tensor(global_row, device=dev)
    ssum = torch.zeros(n_rows, device=dev).index_add(0, rid, tok_ce)
    cnt = torch.zeros(n_rows, device=dev).index_add(0, rid, torch.ones_like(tok_ce))
    return ssum / cnt.clamp(min=1)


def block_row_ce(model, events, dev, mask_dtype):
    """The mean CE and the weight w of each row in a physical block (the basic unit for
    training/eval)."""
    tok_ce, global_row, n_rows = _forward_packed(model, events, dev, mask_dtype)
    ce_per_row = _aggregate_rows(tok_ce, global_row, n_rows, dev)
    w = torch.tensor([row[5] for ev in events for row in ev["rows"]],
                     dtype=torch.float32, device=dev)
    return ce_per_row, w


def backward_logical_minibatch(model, blocks, W, n_g, dev, mask_dtype, amp=False):
    """Backward pass for one logical minibatch (spec section 5): `blocks` is a list of physical
    blocks already split by token budget (each block is a list of events). `W` is the sum of
    row weights for the whole logical minibatch (not for a single physical block on its own),
    `n_g` is the actual number of logical minibatches in this group (the `--accum` logical
    minibatches).

    `torch.autocast` only wraps the forward pass (`block_row_ce`); `.backward()` is outside it
    (matching the shape of the old trainer `train_causal_callgen.py` lines 489 to 505, ticket
    05 S3) -- the backward pass follows the dtype left by the forward pass, unaffected by
    whether it's called inside an autocast context, so wrapping `.backward()` in autocast too
    would have no effect.

    The sum of the gradients from m physical blocks equals the gradient of computing the whole
    logical minibatch in one shot -- this property holds regardless of how `blocks` is split, as
    long as `W` and `n_g` stay the same (this is exactly what test 12(b) verifies).

    Returns `(logical_minibatch_loss, n_rows)`: the former is this logical minibatch's scalar
    loss (for accumulating the "loss" in the step log), the latter is its total row count.

    `.backward()` is wrapped in `_attn_ctx` (silent-failure point #37): when `--grad-ckpt` is
    on, each layer's forward pass is recomputed during the backward pass, and the recompute
    happens inside `.backward()`; the forward pass runs inside `_forward_packed`'s EFFICIENT
    context, so if the recompute falls outside that context it goes through the default kernel
    selection instead, the saved tensor metadata won't match, and torch raises
    `CheckpointError: Recomputed values ... have different metadata` (measured on the l4 smoke
    test `ks828l4_gptoss_cgen_smoke`, 2026-08-28: [2,32,8192,8192] vs [2,1,8192,8192], cpu vs
    cuda). The kernel context only affects kernel selection inside the forward pass; with
    checkpointing off, wrapping it or not gives the same result.
    """
    total = 0.0
    n_rows = 0
    for blk in blocks:
        with torch.autocast("cuda", dtype=torch.bfloat16, enabled=amp):
            ce_per_row, w = block_row_ce(model, blk, dev, mask_dtype)
        loss_c = (ce_per_row * w).sum() / W
        with _attn_ctx(dev):               # checkpoint recompute uses the same kernel as the forward pass (#37)
            (loss_c / n_g).backward()
        total += loss_c.item()
        n_rows += ce_per_row.numel()
    return total, n_rows


@torch.no_grad()
def eval_ce(model, events, tok_budget, dev, amp, beat=None):
    """Full-val weighted masked-CE (same accounting as the training loss, spec section 6).

    `beat` (ticket 08, spec 16.3, second-to-last item): an optional no-arg callback, called
    once every 25 physical blocks in the block loop -- during the window covering full val
    (115,211 rows) plus generative eval, there is currently no heartbeat at all, and the sampler
    judging a stall at 5x the typical heartbeat interval would false-positive; `beat` lets the
    caller (main's `heartbeat.emit`) refresh the timestamp during this window. When `beat=None`,
    it's skipped, with no effect on existing call sites.
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
            "val has not a single target position (weighted denominator w_tot=0) -- continuing would give val_ce=0.0, "
            "saved as best every epoch, making the run look perfect. Something is wrong with the data or filter settings, hard stop.")
    return s / w_tot


def sample_gen_eval_rows(events, mode, seed, n):
    """Sampling for `--gen-eval` (ticket 08, spec 16.3): `events` (the return value of
    `share_data.load_events`, usually the val set) is flattened into a row list in
    event-loading order, with rows within an event in `sent_idx` order (no filtering -- every
    row from share_data has a target), then `random.Random(seed).shuffle` and take the first
    `n` rows (`n` greater than the row count means take them all).

    A fixed-seed pure function: the same `events` gives the same result across two calls
    (spec 16.9 (b)).

    The return value is packed by `mode` into the tuple shape the two old scripts' `eval_gen`
    expect (`tgt`/`tool` come from the `gen` dict at position 6 of the row tuple,
    `share_data.load_events` line 205): cgen `(text, None, None, tgt)`,
    cparam `(text, None, None, tool, tgt)`.
    """
    flat = [row for ev in events for row in ev["rows"]]
    rng = random.Random(seed)
    rng.shuffle(flat)
    picked = flat[:n] if n > 0 else []
    if mode == "cgen":
        return [(row[1], None, None, row[6]["tgt"]) for row in picked]
    return [(row[1], None, None, row[6]["tool"], row[6]["tgt"]) for row in picked]


# ---------------------------------------------------------------- GPU-memory probe

def _peak_gb(dev):
    """Read the peak (spec 16.5, ticket 10): `max_memory_allocated() / 1e9` on cuda, 0.0 on other
    devices. Both the probe's per-block log and the step log call this one function (the single
    source of truth); tests monkeypatch it to supply a fake peak (the real value on CPU is
    always 0, with no discriminating power)."""
    if dev.startswith("cuda"):
        return torch.cuda.max_memory_allocated() / 1e9
    return 0.0


def _block_stats(events):
    """The total row count and total loss-position count of a physical block (a list of events)
    (the mem_probe field in spec 16.5: loss-position count = the sum, over all rows in the
    block, of the count of `!= -100` entries in `seg_lab` [position 4 of the row tuple])."""
    n_rows = sum(len(ev["rows"]) for ev in events)
    n_loss_pos = sum(1 for ev in events for row in ev["rows"]
                     for v in row[4] if v != -100)
    return n_rows, n_loss_pos


def _fwd_bwd_block(model, grp, dev, mask_dtype, amp):
    """One forward-plus-backward pass on a physical block (shared by the probe's three
    block-picking modes, gradients are not zeroed)."""
    with torch.autocast("cuda", dtype=torch.bfloat16, enabled=amp):
        ce_per_row, w = block_row_ce(model, grp, dev, mask_dtype)
        loss = (ce_per_row * w).sum() / w.sum().clamp(min=1e-9)
    with _attn_ctx(dev):                   # checkpoint recompute uses the same kernel as the forward pass (#37)
        loss.backward()


def _enum_run_blocks(tr_events, args):
    """The logical minibatches for epoch 0 of this run and the physical blocks of each logical
    minibatch (spec 16.5: the `cost`/`loop` probes share the same enumeration path -- after
    `share_data.epoch_minibatches`, each logical minibatch goes through `chunk_by_budget`, the
    same path the training loop takes, because the blocks the probe touches must be blocks
    training will actually encounter). Returns `(minibatches, mb_blocks)`: `mb_blocks[i]` is
    the list of physical blocks sliced from `minibatches[i]`."""
    minibatches = share_data.epoch_minibatches(
        tr_events, train_causal_callgen.SEED, 0, args.events_per_mb)
    mb_blocks = [share_data.chunk_by_budget(mb, args.tok_budget)
                for mb in minibatches]
    return minibatches, mb_blocks


def _pick_cost_blocks(blocks):
    """The three-block selection for the `cost` block-picking mode (spec 16.5;
    design-attention.md 9.2/9.5):
    (i) the block with the largest token count (`B x L_pad`), ties broken by more loss
    positions;
    (ii) the block with the largest loss-position count, ties broken by more tokens;
    (iii) the block with the largest `n_tokens / max n_tokens over all blocks + n_loss_pos /
    max n_loss_pos over all blocks`. No coefficients (design-attention.md 9.5: under five sets
    of coefficients, the maximum among the three blocks is exactly the same as the linear
    model's maximum). Returns `[(kind, block), ...]`, where `block` is the original object from
    `blocks` (used for object-identity comparison when deciding "duplicate blocks only run
    once").
    """
    stats = []
    for blk in blocks:
        n_tok = len(blk) * _l_pad(blk)
        _n_rows, n_loss_pos = _block_stats(blk)
        stats.append((n_tok, n_loss_pos))
    max_n_tok = max(s[0] for s in stats)
    max_n_loss_pos = max(s[1] for s in stats)

    def _cost(i):
        return stats[i][0] / max_n_tok + stats[i][1] / max_n_loss_pos

    i_tokens = max(range(len(blocks)), key=lambda i: (stats[i][0], stats[i][1]))
    i_losspos = max(range(len(blocks)), key=lambda i: (stats[i][1], stats[i][0]))
    i_cost = max(range(len(blocks)), key=_cost)
    return [("max_tokens_block", blocks[i_tokens]),
            ("max_losspos_block", blocks[i_losspos]),
            ("max_cost_block", blocks[i_cost])]


def _mem_probe_tokens(model, full_events, args, dev, log, amp, mask_dtype):
    """`tokens` block-picking method (spec 16.5, current): from the whole set, pick the fullest
    block by token count plus the longest event, build state first, then do two backward
    passes in a row. See `share_data.py` for how `worst_blocks` picks.
    """
    longest, fullest = share_data.worst_blocks(
        full_events, args.tok_budget, args.events_per_mb)
    n_considered = len(full_events)
    worst_gb, worst_kind = 0.0, None
    for kind, grp, n_backward in (("fullest_block", fullest, 2),
                                  ("longest_event", longest, 1)):
        if not grp:
            continue
        if dev.startswith("cuda"):
            # Reset the peak-memory counter separately for each block (reset to what is currently
            # allocated: weights + gradients + state, all three kept as-is);
            # otherwise the second block would record the max of the two blocks (raised by assistant-2's review of 907d143)
            torch.cuda.reset_peak_memory_stats()
        for _ in range(n_backward):
            _fwd_bwd_block(model, grp, dev, mask_dtype, amp)  # no zero_grad in between, gradient accumulation
        peak = round(_peak_gb(dev), 3)
        b = len(grp)
        l_pad = _l_pad(grp)
        n_rows, n_loss_pos = _block_stats(grp)
        log(event="mem_probe", pick="tokens", kind=kind, n_events=b,
            packed_len_max=l_pad, peak_mem_gb=peak, B=b, L_pad=l_pad,
            n_tokens=b * l_pad, n_rows=n_rows, n_loss_pos=n_loss_pos,
            with_optimizer_state=True, n_backward=n_backward,
            optimizer_state_prebuilt=True)
        if worst_kind is None or peak > worst_gb:   # on a peak tie (CPU is all 0) take the first block
            worst_gb, worst_kind = peak, kind
    log(event="mem_probe_summary", pick="tokens", worst_gb=worst_gb,
        worst_kind=worst_kind, scope="full", n_events_considered=n_considered)


def _mem_probe_cost(model, tr_events, args, dev, log, amp, mask_dtype):
    """`cost` block-picking method (spec 16.5, default): pick three blocks from all the
    physical blocks in epoch 0 of this run (`_pick_cost_blocks`), and measure peak
    memory for each under the condition "state already built, run two forward+backward
    passes in a row, no gradient clearing in between"; a repeated block only runs once,
    a repeated event is still written, with an added `same_as` pointing to the kind that
    actually ran."""
    _minibatches, mb_blocks = _enum_run_blocks(tr_events, args)
    blocks = [blk for blks in mb_blocks for blk in blks]
    n_considered = len(tr_events)
    picks = _pick_cost_blocks(blocks)

    seen = {}                          # id(block) -> (kind, peak)
    worst_gb, worst_kind = 0.0, None
    for kind, grp in picks:
        b = len(grp)
        l_pad = _l_pad(grp)
        n_rows, n_loss_pos = _block_stats(grp)
        key = id(grp)
        if key in seen:
            same_kind, peak = seen[key]
            log(event="mem_probe", pick="cost", kind=kind, B=b, L_pad=l_pad,
                n_tokens=b * l_pad, n_rows=n_rows, n_loss_pos=n_loss_pos,
                peak_mem_gb=peak, n_backward=2, with_optimizer_state=True,
                optimizer_state_prebuilt=True, n_events=b, packed_len_max=l_pad,
                same_as=same_kind)
        else:
            if dev.startswith("cuda"):
                torch.cuda.reset_peak_memory_stats()
            for _ in range(2):
                _fwd_bwd_block(model, grp, dev, mask_dtype, amp)
            peak = round(_peak_gb(dev), 3)
            seen[key] = (kind, peak)
            log(event="mem_probe", pick="cost", kind=kind, B=b, L_pad=l_pad,
                n_tokens=b * l_pad, n_rows=n_rows, n_loss_pos=n_loss_pos,
                peak_mem_gb=peak, n_backward=2, with_optimizer_state=True,
                optimizer_state_prebuilt=True, n_events=b, packed_len_max=l_pad)
        if worst_kind is None or peak > worst_gb:   # on a peak tie (CPU is all 0) take the first block
            worst_gb, worst_kind = peak, kind
    log(event="mem_probe_summary", pick="cost", worst_gb=worst_gb,
        worst_kind=worst_kind, scope="run", n_events_considered=n_considered)


def _mem_probe_loop(model, opt, tr_events, args, dev, log, amp, mask_dtype):
    """`loop` block-picking method (spec 16.5, decision 32): for each of the three blocks
    picked by `cost`, find the update group it belongs to (`accum` consecutive logical
    minibatches, `n_g` follows the same rule as the training loop: the last group uses
    the actual count when short of `accum`), run one update per group exactly as the
    training loop does (`backward_logical_minibatch` over each logical minibatch,
    `clip_grad_norm_`, `opt.step()` with lr set to 0), read the peak, and take the max
    of the three groups; the same group only runs once. The scheduler `sch` is not touched.

    Only running "the group containing the block with the most loss positions" is not
    enough (design-attention.md section 9, confirmed by 8-28-assistant-2): epoch 0's true
    peak block is in group 490, while the block with the most loss positions is in group
    475; on a configuration without checkpointing, running only the latter comes in about
    6% below the true peak."""
    minibatches, mb_blocks = _enum_run_blocks(tr_events, args)
    n_considered = len(tr_events)
    M_ep = len(minibatches)
    accum = args.accum

    # block -> logical minibatch index (by object identity; _pick_cost_blocks returns the original objects)
    mb_of_block = {}
    all_blocks = []
    for mb_idx, blocks in enumerate(mb_blocks):
        for blk in blocks:
            mb_of_block[id(blk)] = mb_idx
            all_blocks.append(blk)
    # group -> which blocks this group is run for (a list of kinds, in the order of the three cost blocks)
    groups = {}
    for kind, blk in _pick_cost_blocks(all_blocks):
        group_start = (mb_of_block[id(blk)] // accum) * accum
        groups.setdefault(group_start, []).append(kind)

    worst_gb, worst_kind, worst_group_of = 0.0, None, None
    for gi, (group_start, kinds) in enumerate(sorted(groups.items())):
        if dev.startswith("cuda"):
            torch.cuda.reset_peak_memory_stats()   # reset the peak-memory counter separately for each group
        group_end = min(group_start + accum, M_ep)
        group_mb_idx = list(range(group_start, group_end))
        n_g = len(group_mb_idx)

        n_backward_total = 0
        sum_rows = sum_loss_pos = total_events = 0
        max_n_tokens = max_b = max_l_pad = 0
        max_block_n_loss_pos = 0
        for mb_idx in group_mb_idx:
            mb_events = minibatches[mb_idx]
            total_events += len(mb_events)
            W = sum(row[5] for ev in mb_events for row in ev["rows"])
            blocks = mb_blocks[mb_idx]
            backward_logical_minibatch(model, blocks, W, n_g, dev, mask_dtype, amp)
            for blk in blocks:
                n_backward_total += 1
                n_rows, n_loss_pos = _block_stats(blk)
                sum_rows += n_rows
                sum_loss_pos += n_loss_pos
                max_block_n_loss_pos = max(max_block_n_loss_pos, n_loss_pos)
                b = len(blk)
                l_pad = _l_pad(blk)
                n_tok = b * l_pad
                if n_tok > max_n_tokens:
                    max_n_tokens, max_b, max_l_pad = n_tok, b, l_pad

        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()                     # lr is already 0 (set during the skeleton's state-building step)
        peak = round(_peak_gb(dev), 3)
        opt.zero_grad(set_to_none=True)  # the next group starts from "state already built, gradients not yet produced"
        group_of = "+".join(kinds)

        log(event="mem_probe", pick="loop", kind="loop_group", group_of=group_of,
            group_idx=group_start // accum, B=max_b,
            L_pad=max_l_pad, n_tokens=max_n_tokens, n_rows=sum_rows,
            n_loss_pos=sum_loss_pos, peak_mem_gb=peak, n_backward=n_backward_total,
            with_optimizer_state=True, optimizer_state_prebuilt=True,
            n_events=total_events, packed_len_max=max_l_pad,
            n_blocks=n_backward_total, max_block_n_loss_pos=max_block_n_loss_pos)
        if worst_kind is None or peak > worst_gb:
            worst_gb, worst_kind, worst_group_of = peak, "loop_group", group_of
    log(event="mem_probe_summary", pick="loop", worst_gb=worst_gb,
        worst_kind=worst_kind, worst_group_of=worst_group_of, scope="run",
        n_events_considered=n_considered)


def run_mem_probe(model, opt, tr_events, args, dev, log, amp, full_events=None):
    """spec section 10/16.5: probe the real worst-case GPU memory before training starts
    (tickets 06, 10).

    Skeleton (build optimizer state -> reset peak -> run per `--mem-probe-pick` -> clear
    state, restore lr, clear gradients) plus three block-picking methods. `full_events` is
    only used under `tokens`; if not given, fall back to `tr_events` (this is how main()
    reuses it when `--max-events 0` and `--smoke` is not passed, since tr_events is
    already the full set).

    Key point on building state (ticket 06): AdamW's `step()` only allocates state for
    parameters where `.grad is not None`; for a model that has never done a backward
    pass, every `.grad` is None, so a plain `zero_grad` followed by `step(lr=0)` builds
    no state at all (verified in this repo's `cprobe-env` on torch 2.11.0+cu128:
    `opt.state` ends up an empty dict `{}`, zero keys). The root cause is not "whether a
    forward+backward pass needs to be inserted before this state-building step", but that
    `.grad` needs a tensor of the real shape first -- AdamW's state allocation only looks
    at whether `.grad is not None` and the parameter's shape/dtype, not the gradient
    values, so assigning `torch.zeros_like(p)` directly to each trainable parameter's
    `.grad` is enough; there is no need to run an extra forward+backward pass for this.

    Random-number state (spec 16.5, silent-failure point #31): the probe's forward pass
    consumes the CUDA/CPU random-number streams (LoRA dropout); without restoring it, a
    run with the probe and a run without it would no longer match bit-for-bit in the
    training part -- save and restore all three of `random`/`torch`/`torch.cuda` random
    state around the whole block.
    """
    if full_events is None:
        full_events = tr_events
    mask_dtype = torch.bfloat16 if amp else torch.float32

    py_state = random.getstate()
    torch_state = torch.get_rng_state()
    cuda_state = torch.cuda.get_rng_state() if dev.startswith("cuda") else None
    try:
        orig_lrs = [g["lr"] for g in opt.param_groups]
        for g in opt.param_groups:
            for p in g["params"]:
                p.grad = torch.zeros_like(p)   # used to build state, not the product of any forward+backward pass
        opt.zero_grad(set_to_none=False)
        for g in opt.param_groups:
            g["lr"] = 0.0
        opt.step()                             # optimizer state gets allocated here; parameters are untouched
        if dev.startswith("cuda"):
            torch.cuda.reset_peak_memory_stats()

        if args.mem_probe_pick == "tokens":
            _mem_probe_tokens(model, full_events, args, dev, log, amp, mask_dtype)
        elif args.mem_probe_pick == "cost":
            _mem_probe_cost(model, tr_events, args, dev, log, amp, mask_dtype)
        else:
            _mem_probe_loop(model, opt, tr_events, args, dev, log, amp, mask_dtype)
    finally:
        # The three block-picking methods are themselves probing worst-case GPU memory, so if
        # the probe run crashes (OOM etc.) it must not leave opt.state/lr/.grad stuck in a dirty
        # mid-probe state -- move the three cleanup steps into finally together with the
        # random-number state restore, so they run whether the probe finishes normally or
        # raises. Order: clear state, restore lr, clear gradients, then restore the random
        # number state (spec 16.9 O4).
        opt.state.clear()                      # #32: a step with lr=0 still writes state, clear it
        for g, lr0 in zip(opt.param_groups, orig_lrs):
            g["lr"] = lr0
        opt.zero_grad(set_to_none=True)
        random.setstate(py_state)
        torch.set_rng_state(torch_state)
        if cuda_state is not None:
            torch.cuda.set_rng_state(cuda_state)


# ---------------------------------------------------------------- alignment check

def _align_candidates(path, tok, seed, n, max_len):
    """spec section 9: randomly sample `n` val events whose full-text token count is
    <= `min(ALIGN_LEN_FILTER, max_len)` -- the cap also has to respect `--max-len`,
    otherwise when `--max-len < 2048` the new path (`share_data.load_events` drops whole
    events by `--max-len`) drops a few more of the sampled events than the reference path
    (`CallDS`/`ParamDS` does not drop by this cap), so the two paths' total row counts
    would not match and section 9's pairing assertion would hit `exit(2)` directly
    (ticket 05 S5). Independent of `share_data.load_events`'s row-level pipeline (only
    does group-by-event plus full-text tokenization), to avoid running a full row-level
    tokenization pass just for sampling -- that cost would be out of proportion to the
    sampling purpose under `--smoke`."""
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
    """Write all raw rows of the sampled events into one temp jsonl, sorted ascending by
    `(event, sent_idx)` (spec section 9). The same file feeds both the new path and the
    reference path, so the row order the two paths see is naturally consistent, which is
    what makes position-based pairing comparison meaningful."""
    rows = [r for rs in picked for r in rs]
    rows.sort(key=lambda r: (r["event"], r["sent_idx"]))
    fd, path = tempfile.mkstemp(suffix=".jsonl", prefix="kvshare_align_")
    with open(fd, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return path


def _ref_forward(mode, model, tok, rows, dev, max_len, bs, check_drift=True):
    """Reference path: the old `collate`, batches of `bs` rows with right padding, run
    through the same model.

    Each row's ce comes directly from calling the old script's `inst_ce`
    (`train_causal_callgen.py`/`train_causal_param.py`, the literal requirement of spec
    section 9: "import collate, inst_ce... to get each row's ce") -- `row_ce` is exactly
    `inst_ce`'s return value, not a hand-written substitute using the same formula.
    `inst_ce` itself only returns each row's mean CE and does not expose per-token
    intermediates, while the same spec section also requires a per-token max-diff
    threshold, so this function separately computes a per-token CE locally with the
    exact same formula as `inst_ce` (shifted prediction, CE taken only at target
    positions) for `tok_ce` to use, and on every batch asserts that the per-row result
    aggregated from this local formula matches the value actually returned by calling
    `inst_ce` (`REF_INST_CE_DRIFT_TOL`) -- if they do not match it raises
    `RefBaselineDriftError` (a real exception, not a bare `assert`, so it is not stripped
    by `-O`/`PYTHONOPTIMIZE`), which `run_align_check` catches and handles the same way
    as every other failure branch in this file (write `ALIGN_CHECK.json`, print
    diagnostics, `sys.exit(2)`), so an unverified hand-written formula never quietly
    becomes the baseline for the alignment check.
    `bs=4` is the "full batch", `bs=1` is the "single row" that fills out the baseline
    (spec: both use the old trainer's convention, only the batch size differs). The
    reference path does not apply EFFICIENT_ATTENTION and uses the default kernel
    selection (design-attention.md section 7.1: a batch with "no padding for a single
    row" has no mask, HF skips building a mask and turns on enable_gqa, mem-efficient
    does not support GQA, and forcing the kernel would error).

    `check_drift` (ticket 05 S2): when True (the default), do the self-check above --
    both fp32 calls (REF_BATCH full batch, bs=1 single-row baseline) keep it on, with
    tolerance `REF_INST_CE_DRIFT_TOL`, since the same no_grad forward pass should in
    theory match; the bf16 coarse pass passes False to turn the self-check off -- under
    bf16 it is comparing two independent forward passes' bf16 results, and the GPU kernel
    only has to drift past the magnitude set for fp32 to falsely raise
    `RefBaselineDriftError` and block training from starting, while the bf16 coarse pass
    only ever uses `row_ce` (`inst_ce_fn`'s return value) and does not need this
    self-check.

    Returns `(row_ce list, tok_ce list)`; row order/token order = the input order of
    `rows`.
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
        # `out`/`lg` are this batch's [B, L, V] fp32 all-position logits (about 5.1 GB); later
        # code only needs the `ce`/`rid` already extracted from them, so release them before
        # calling `inst_ce_fn` (which recomputes a forward pass itself) -- otherwise having both
        # alive at once briefly costs about 10 GB (ticket 05 S6).
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
                    f"_ref_forward's per-row results aggregated locally by the per-token formula don't match "
                    f"the return value of actually calling inst_ce (max diff {drift} > "
                    f"{REF_INST_CE_DRIFT_TOL}, mode={mode}): the reference baseline for the alignment check "
                    "is not trustworthy, check the difference between the two formulas before continuing.")

        row_ce.extend(row_ce_inst.tolist())
        tok_ce.extend(ce.tolist())
    return row_ce, tok_ce


def _new_forward(events, model, dev, mask_dtype):
    """New path, fp32 (or for the bf16 coarse pass): one separate forward pass per event
    (align_events is a small count, no need to pack into blocks by token budget); row
    order/token order = the order `events` expands to, sharing the same temp file sorted
    by `(event, sent_idx)` with the reference path, so the row order is naturally
    consistent."""
    row_ce, tok_ce = [], []
    for ev in events:
        tok_c, global_row, n_rows = _forward_packed(model, [ev], dev, mask_dtype)
        ce_per_row = _aggregate_rows(tok_c, global_row, n_rows, dev)
        row_ce.extend(ce_per_row.tolist())
        tok_ce.extend(tok_c.tolist())
    return row_ce, tok_ce


def run_align_check(model, tok, args, dev, mode, ro_set):
    """spec section 9: the alignment check before training starts (and for
    `--align-only`). The caller must ensure this is called before `lora_util.wrap`; the
    function itself handles the `model.eval()`/`model.train()` switch and the
    save/restore of fp32 precision settings. On failure, write the report to
    ALIGN_CHECK.json then `sys.exit(2)` (following ctool's approach)."""
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
                mismatch_idx = [-1]        # total row counts differ, position-by-position comparison is meaningless
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
            # spec 9: the relative criterion uses one overall average of the reference path's
            # per-row ce absolute values as the denominator, not each row divided by its own ce --
            # rows where ce is near 0 would make the per-row relative difference blow up.
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

            # `bf16_warn` is not in spec section 9's list of fields to persist (`align_bf16_warn` has
            # already been reported once in the `start` event), so it is not written into
            # ALIGN_CHECK.json; it is only carried as an extra item in the function's return value
            # for main() to record in the `start` event
            # (ticket 05 F2/ticket 03 minor).
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
                    "alignment check FAIL: form A's per-row loss does not match the old trainer's, refusing to start training.",
                    f"  rule --align-rule {args.align_rule}",
                    f"  max per-row diff {row_diff:.3e} (tol {args.align_tol:.1e}), "
                    f"max per-token diff {tok_diff:.3e} (tol {args.align_tok_tol:.1e})",
                ]
                if args.align_rule in ("rel", "both"):
                    if ref_scale == 0:
                        msg_lines.append(
                            "  ref_scale is 0 (the mean absolute value of the reference path's per-row ce is 0), "
                            "rel_max_abs_diff is recorded as null, the rel rule judges it a failure.")
                    else:
                        msg_lines.append(
                            f"  relative diff {rel_max_abs_diff:.3e}"
                            f"(rel_tol {args.align_rel_tol:.1e}),"
                            f"ref_scale={ref_scale:.3e}")
                msg_lines.append(
                    f"  row count/drop count match: mismatch_idx={mismatch_idx[:5]}, "
                    f"dropped_rows_tgt_ok={drop_ok}, assembly_mismatch_ok="
                    f"{mismatch_ok}\n  Debug: check share_data's common prefix/mask/"
                    "position_ids construction, or tokenizer version drift.")
                print("\n".join(msg_lines), flush=True)
                sys.exit(2)
            return dict(report, bf16_warn=bf16_warn)
    except RefBaselineDriftError as e:
        # `_ref_forward`'s self-check failure (the reference baseline itself is untrustworthy):
        # handled the same way as every other failure branch in this file -- write
        # ALIGN_CHECK.json, print diagnostics, sys.exit(2). The two `_ref_forward` calls that
        # still pass `check_drift=True` (REF_BATCH full batch, bs=1 single-row baseline, both
        # fp32) share this one except -- the bf16 coarse-pass call on cuda passes
        # `check_drift=False` (ticket 05 S2) and does not trigger this exception.
        report = dict(PASS=False, stage="ref_forward_drift", error=str(e),
                      ref_inst_ce_drift_tol=REF_INST_CE_DRIFT_TOL,
                      rule=args.align_rule, rel_tol=args.align_rel_tol)
        (out / "ALIGN_CHECK.json").write_text(
            json.dumps(report, indent=1, ensure_ascii=False))
        print(json.dumps(report, indent=1), flush=True)
        print(
            "Alignment check FAIL: reference-path self-check failed, refusing to start training.\n"
            f"  {e}\n"
            "  Debug: check whether the local per-token formula in _ref_forward matches inst_ce's shift/mask/"
            "aggregation logic; if the two are indeed equivalent, this means this environment shows, within a "
            "single no_grad forward pass, more floating-point nondeterminism than expected, and needs a review "
            "of whether REF_INST_CE_DRIFT_TOL should be loosened, rather than passing by default.", flush=True)
        sys.exit(2)
    finally:
        if tmp_path is not None:
            Path(tmp_path).unlink(missing_ok=True)
        torch.set_float32_matmul_precision(prev_prec)
        if dev.startswith("cuda"):
            torch.backends.cuda.matmul.allow_tf32 = prev_tf32_mm
            torch.backends.cudnn.allow_tf32 = prev_tf32_cudnn
        model.train()


# ---------------------------------------------------------------- main flow

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=["cgen", "cparam"],
                    help="which construction path the target string and tail follow (spec 3.3)")
    ap.add_argument("--base", default="qwen",
                    help="qwen/qwen17/qwen4, or a model directory path"
                         "(a path goes through build(path=...), for admitting small test models)")
    ap.add_argument("--env", default="appworld",
                    choices=["tales", "appworld", "bfcl", "alfworld"],
                    help="log label only (the data path is given directly by --data)")
    ap.add_argument("--data", required=True,
                    help="data dir <data_out> (contains train/val.jsonl)")
    ap.add_argument("--out", required=True, help="output dir (required; guards against overwriting old outputs)")
    ap.add_argument("--max-len", type=int, default=8192,
                    help="token cap for full event text; drop the whole event if it's exceeded (spec 3.5)")
    ap.add_argument("--tok-budget", type=int, default=16384,
                    help="physical block budget: event count x longest padded concatenated sequence length (spec 5)")
    ap.add_argument("--eval-tok-budget", type=int, default=0,
                    help="eval physical block budget, 0 = 2 x --tok-budget")
    ap.add_argument("--events-per-mb", type=int, default=4,
                    help="event count per logical mini-batch (spec 5)")
    ap.add_argument("--accum", type=int, default=2,
                    help="number of logical mini-batches accumulated per update (spec 5)")
    ap.add_argument("--lr", type=float, default=None,
                    help="learning rate, same as before; goes through lora_util.resolve_lr")
    ap.add_argument("--epochs", type=int, default=1)
    ap.add_argument("--eval-per-epoch", type=int, default=4,
                    help="how many times to evaluate per epoch (spec 6)")
    ap.add_argument("--smoke", action="store_true",
                    help="40 training events/16 eval events/1 epoch, take the first N by full-text"
                         "token count ascending")
    ap.add_argument("--max-events", type=int, default=0,
                    help="for debugging: cap the event count (0 = unlimited); given alone, shuffle then take the first N,"
                         "given together with --smoke, N overrides 40/16 and the selection is still ascending")
    ap.add_argument("--log-every", type=int, default=50,
                    help="write one step log line every N updates")
    ap.add_argument("--gen-eval", type=int, default=200,
                    help="number of val rows sampled for generative eval, 0 disables it (spec 16.3, ticket 08)")
    ap.add_argument("--gen-bs", type=int, default=8,
                    help="batch size for generative eval")
    ap.add_argument("--gen-eval-at", default="last", choices=["all", "last"],
                    help="last (default) = only generate at the eval that falls at frac==E (epoch end),"
                         "all = generate at every eval point")
    ap.add_argument("--mem-probe", action="store_true",
                    help="probe worst-case block GPU memory before training (spec 10)")
    ap.add_argument("--mem-probe-pick", default="cost",
                    choices=["tokens", "cost", "loop"],
                    help="block-picking method for the GPU memory probe (spec 16.5, ticket 10)")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--grad-ckpt", action="store_true",
                    help="turn on gradient checkpointing in the base model to save GPU memory, same as before")
    ap.add_argument("--readonly-env", default=None,
                    choices=list(readonly_map.READONLY_ENVS),
                    help="read-only tool mode, same as before (off by default = the old settings)")
    ap.add_argument("--force", action="store_true",
                    help="allow training again in an --out dir that was already trained in (refused by default to keep outputs apart)")
    ap.add_argument("--attn-impl", default="sdpa", choices=["sdpa"],
                    help="attention implementation path; only sdpa this round (spec 4)")
    ap.add_argument("--align-only", action="store_true",
                    help="run only the pre-training alignment check, then exit")
    ap.add_argument("--align-tol", type=float, default=2e-5,
                    help="alignment check threshold for max per-row ce absolute difference (spec 9)")
    ap.add_argument("--align-events", type=int, default=6,
                    help="number of val events sampled for the alignment check (spec 9)")
    ap.add_argument("--align-tok-tol", type=float, default=3e-4,
                    help="alignment check threshold for max per-token ce absolute difference (spec 9)")
    ap.add_argument("--align-bf16-mean-tol", type=float, default=2e-2,
                    help="alignment check threshold for the bf16 coarse-filter mean absolute difference (spec 9)")
    ap.add_argument("--align-bf16-max-tol", type=float, default=1e-1,
                    help="alignment check threshold for the bf16 coarse-filter max absolute difference (spec 9)")
    ap.add_argument("--align-baseline-factor", type=float, default=3.0,
                    help="baseline alert multiplier: alert when the per-row max difference exceeds this multiple of the"
                         "baseline's own difference (the difference between a single-row-padded baseline and the full batch) (spec 9)")
    ap.add_argument("--align-rule", default="abs", choices=["abs", "rel", "both"],
                    help="alignment criterion: abs = per-row/per-token absolute difference (current default),"
                         "rel = relative difference, both = both must hold (spec 9)")
    ap.add_argument("--align-rel-tol", type=float, default=1e-5,
                    help="alignment check relative-difference threshold, used with --align-rule rel/both (spec 9)")
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
            f"{out} already has a train_log.jsonl -- this dir has already been trained once; training again would mix"
            " both runs' outputs into the same best/ with no way to tell them apart (audit B7). Use a different --out, or confirm the overwrite and pass --force.")
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

    # ---- mandatory gate before training starts: alignment check (before lora_util.wrap, under model.eval()) ------
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
        gen_eval_at=args.gen_eval_at, mem_probe=args.mem_probe,
        mem_probe_pick=args.mem_probe_pick, lr=lr,
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
        full_tr_events = None
        if args.mem_probe_pick == "tokens":
            # When readonly_env is on, tr_events is loaded with ro=ro_tr, and non-read-only rows
            # have already been dropped entirely -- it is not the full training set anymore. This
            # branch must count readonly_env being off into the criterion for "tr_events is already
            # the full set", otherwise the probe would be measuring a filtered subset while still
            # tagged scope="full".
            if args.readonly_env is None and (not args.smoke) \
                    and args.max_events == 0:
                full_tr_events = tr_events     # when limit=0, tr_events is already the full set
            else:
                full_tr_events, _full_counts = share_data.load_events(
                    data / "train.jsonl", tok, args.mode, args.max_len,
                    ro=None, limit=0)
        run_mem_probe(model, opt, tr_events, args, dev, log, amp,
                     full_events=full_tr_events)
        del full_tr_events
        if dev.startswith("cuda"):
            # The probe resets the counter separately before each block but not after it finishes,
            # so the first step reads the probe's last block's peak
            # (found by 8-28-assistant from five smoke tests' gstep 1)
            torch.cuda.reset_peak_memory_stats()

    best = float("inf")
    best_ep = best_frac = None
    gstep = 0
    total_rows = 0
    for ep in range(epochs):
        minibatches = share_data.epoch_minibatches(
            tr_events, SEED, ep, args.events_per_mb)
        M_ep = len(minibatches)
        E = args.eval_per_epoch
        # eval point -> frac: computed for k = 1 to E in order; when the same point is hit by
        # multiple k, the later k overwrites the earlier one (takes the max k), so the point at
        # k=E (= end of epoch, ceil(U*E/E)=U always holds) always reports frac=E and is never
        # taken over by an earlier duplicate point (spec 6: "the point at k=E is the end of the
        # epoch").
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
            total_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
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
                peak_mem_gb = round(_peak_gb(dev), 3)
                if dev.startswith("cuda"):
                    torch.cuda.reset_peak_memory_stats()
                log(event="step", ep=ep, gstep=gstep, rows=epoch_rows,
                    loss=loss_val, lr=sch.get_last_lr()[0], ips=ips,
                    ips_win=ips_win, eps=eps, train_s=round(epoch_train_s, 2),
                    peak_mem_gb=peak_mem_gb, grad_norm=round(float(total_norm), 4))
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
                        # merge the adapter back into the base before saving: best/ is item-for-item identical in structure to a full-parameter save
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
