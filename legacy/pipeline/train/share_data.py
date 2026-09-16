"""share_data.py -- the pure-CPU data and tokenization module shared by cgen / cparam.

Used by:
- `train_causal_share.py` (ticket 03, the new trainer, shared by the cgen/cparam cells)
- `train_causal_tool.py` / `pipeline/eval/eval_tool.py` (ticket 02, uses only the
  `read_position` function; `eval_tool.py` must import this module under mbert-env)

The module top level allows only stdlib and torch: the two old trainers
(`train_causal_callgen.py`, `train_causal_param.py`) have a transformers >= 5.14 version
gate at module level, and a top-level import under mbert-env (transformers 4.57.6) would
`raise SystemExit`, while `eval_tool.py` also needs to import this module under mbert-env
to get `read_position`. So imports of the two old scripts (and of `pipeline/annotate/rules.py`,
under the same rule) are always deferred to inside the `load_events` function body;
`read_position` never touches any training script.

Rule source: `.scratch/kvshare-train/spec.md` sections 2, 3, 4, 5, 11.3.
"""
import json
import random
import sys
from pathlib import Path

import torch

_HERE = Path(__file__).resolve().parent

# The placeholder token id used for right padding. A pad row only sees itself as a query
# in batch_mask (spec section 4: a row that can see nothing at all makes softmax produce
# NaN); it never takes part in the loss and is never seen by any real token, so the exact
# value of this id doesn't affect any real output -- 0 is valid for any vocabulary.
PAD_TOKEN_ID = 0


def _lazy_imports():
    """Deferred import of the two old training scripts' constants/functions, plus
    `rules.MAX_BOUNDS`.

    The two old scripts have a transformers >= 5.14 version gate at module level, and a
    top-level import under mbert-env would `SystemExit`; this function is called only where
    they're actually needed (`load_events`), never touching them at `share_data.py`'s module
    top level (spec 3.3).
    """
    train_dir = str(_HERE)
    if train_dir not in sys.path:
        sys.path.insert(0, train_dir)
    annotate_dir = str(_HERE.parent / "annotate")
    if annotate_dir not in sys.path:
        sys.path.insert(0, annotate_dir)
    import train_causal_callgen as cgen_mod
    import train_causal_param as cparam_mod
    from rules import MAX_BOUNDS
    return cgen_mod, cparam_mod, MAX_BOUNDS


def _lcp(a, b):
    """The longest common prefix length of `a` and `b` (compared token by token up to the first difference)."""
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def _pad16(n):
    """Round `n` up to a multiple of 16, matching the same convention as `batch_mask`'s `L_pad`
    padding.

    The budget criteria for `chunk_by_budget`/`worst_blocks` must both use this padded
    length (spec section 5; ticket item 1: "chunk_by_budget's budget criterion also uses
    L_pad"), not the pre-padding `packed_len` -- real GPU memory/compute is determined by
    the physical block length after `batch_mask`'s padding.
    """
    return ((n + 15) // 16) * 16


def full_token_ids(tok, full_text):
    """Tokenize the event's full text, the single algorithm source (spec 16.2): `load_events`
    fills `e["full_ids"]`, and the `drop-event` criterion in all three eval scripts calls
    this function or `n_full_tokens` below -- tokenization has exactly one source of truth.
    `add_special_tokens=False, truncation=False` -- no truncation, what's wanted is the
    real full-text token count.
    """
    return tok(full_text, add_special_tokens=False,
              truncation=False)["input_ids"]


def n_full_tokens(tok, full_text):
    """A thin wrapper around `full_token_ids` for when only the length is needed (the eval
    side's `drop-event` criterion only needs the count, not `full_ids` itself)."""
    return len(full_token_ids(tok, full_text))


def event_full_texts(rows):
    """Group by event, take the `text` of the row with the largest `sent_idx` in each group
    (spec 16.2).

    Used only by the eval side's `--overlong drop-event`: it does not filter rows, and does
    not touch the grouping in `events_all.append(dict(...))` inside `load_events` -- that
    grouping is pinned to the random-number consumption order in section 3.2. This function
    is a separate one written for the eval side, unrelated to the training side's sampling
    order.

    `rows`: a batch of raw row dicts (containing at least `event`, `sent_idx`, `text`).
    -> dict[event] -> full_text
    """
    groups = {}
    for r in rows:
        groups.setdefault(r["event"], []).append(r)
    return {ev: max(rs, key=lambda r: r["sent_idx"])["text"]
           for ev, rs in groups.items()}


def select_keys(mode, keys, n_full, prompt_len, excluded_rows, max_len, max_new):
    """Filter a batch of keys (events) by `--overlong` and ctool's row exclusions (spec 16.2).

    `mode`: "left" / "skip" / "drop-event".
    `keys`: `dict[key] -> list[int]`, the list of candidate row indices for each key --
        all the row indices that event corresponds to in ctool's `rows`/`logits_test.pt`.
        This list is used only to decide "does this key still have any candidate rows
        after ctool's exclusion," independent of `mode`'s filtering logic (which uses
        `n_full`/`prompt_len` below).
    `n_full`: `dict[key] -> int`, the event's full-text token count (only needed when
        `mode="drop-event"`; other modes can pass an empty dict).
    `prompt_len`: `dict[key] -> int`, `L(k)` -- the prompt token count (cparam passes the
        max of its two prompt lengths; all three modes `left`/`skip`/`drop-event` use only
        this one number to decide "is the prompt too long").
    `excluded_rows`: `set[int]`, the set of excluded row indices from ctool (`rows`/`logits`
        positions, `logits_test.meta.json`'s `excluded_idx`).
    `max_len`, `max_new`: int.

    -> (kept_keys: list[key], counts: dict(n_left_truncated, n_skipped_rows,
        n_dropped_events, n_excluded_by_ctool))

    The order of the four criteria is fixed for every key: first check ctool's exclusion
    (if all candidate rows are excluded, the whole key gets no score, counted as
    `n_excluded_by_ctool`, and the mode criteria below are not checked); then follow `mode`
    into `drop-event` (the whole event is dropped if its full text is too long, counted as
    `n_dropped_events`) or `skip` (the whole row is skipped if the prompt is too long,
    counted as `n_skipped_rows`) or, when neither drops it, "the prompt is still too long"
    (both `left` and `drop-event` count this as `n_left_truncated`; `skip` never reaches
    this case, because rows with an overlong prompt were already excluded in the step
    above).
    """
    if mode not in ("left", "skip", "drop-event"):
        raise ValueError(
            f"select_keys: mode only supports left/skip/drop-event, got {mode!r}")
    thresh = max_len - max_new
    kept = []
    counts = dict(n_left_truncated=0, n_skipped_rows=0,
                 n_dropped_events=0, n_excluded_by_ctool=0)
    for k in keys:
        if all(i in excluded_rows for i in keys[k]):
            counts["n_excluded_by_ctool"] += 1
            continue
        if mode == "drop-event" and n_full[k] > max_len:
            counts["n_dropped_events"] += 1
            continue
        if prompt_len[k] > thresh:
            if mode == "skip":
                counts["n_skipped_rows"] += 1
                continue
            counts["n_left_truncated"] += 1
        kept.append(k)
    return kept, counts


# ---------------------------------------------------------------- data and tokenization

def load_events(path, tok, mode, max_len, ro=None, limit=0, order="random"):
    """Load one split (`train.jsonl` or `val.jsonl`), per spec 3.2-3.5.

    The step order is fixed (the RNG's consumption order determines the sampling
    result, spec 3.2): group -> spot-check prefix properties (over all events
    before dropping) -> tokenize each event's full text to get `n_full`, drop
    event-level overlong events per the drop rule -> take a subset by
    `limit`/`order` -> tokenize line by line and apply row-level drops only on
    the events that remain.

    `mode` = "cgen": target string = `tok(label_call) + [eos]`, tail = `CALL_SEP`.
    `mode` = "cparam": target string = `param_target(label, label_call) + [eos]`,
    tail = `param_prompt_tail(label)`; rows where `param_target` returns None are
    dropped whole and counted as `assembly_mismatch`.

    When `ro` is not None (`--readonly-env`), rows that are not read-only are
    dropped whole, counted in `ro` (`ro` = dict(set=.., labels=[], kept=0,
    dropped=0), same accounting as the readonly branch of `CallDS`/`ParamDS`).

    When `limit > 0`, take the first `limit` events by `order` from the events
    left after dropping overlong events: "random" shuffles with a freshly
    constructed `random.Random(SEED)` and takes the first limit; "shortest" takes
    the first limit by ascending `n_full`. After taking the subset, restore the
    order to each event's first appearance in the file (the order-preservation
    contract on the return value does not change with how the subset is taken).

    Returns `(events, counts)`:
    - `events`: a list, each event is `dict(event, n_full, packed_len,
      prefix_len, full_ids, rows)`, `rows` = `[(sent_idx, text, p, seg_ids,
      seg_lab, w, gen), ...]` (position 6 `gen` = `dict(tgt=<target string>,
      tool=<tool name or None>)`, for `train_causal_share.py`'s `--gen-eval`
      generative evaluation, spec 16.3, ticket 08). Event order = first
      appearance in the file; row order = ascending `sent_idx` -- these two
      order-preservation guarantees are a contract; the alignment check relies
      on them to pair by position.
      `full_ids` (the event's full-text tokenization) and
      `packed_len`/`prefix_len` (packed sequence length, common-prefix upper
      bound P = max_k p_k) are for `pack_event` to use.
    - `counts`: `dict(dropped_events, dropped_rows_tgt, assembly_mismatch,
      n_rows)`.

    Two hard stops (ported from `train_causal_param.py` lines 337-353): exit if
    this split loads 0 rows; when `mode="cparam"`, also exit if the stripping
    failure rate (`assembly_mismatch` share) exceeds
    `train_causal_param.ASSEMBLY_MISMATCH_LIMIT`.
    """
    if mode not in ("cgen", "cparam"):
        raise ValueError(f"load_events: mode only supports cgen/cparam, got {mode!r}")
    if order not in ("random", "shortest"):
        raise ValueError(f"load_events: order only supports random/shortest, got {order!r}")

    cgen_mod, cparam_mod, MAX_BOUNDS = _lazy_imports()
    SEED = cgen_mod.SEED               # cgen/cparam use the same SEED value (42)
    MAX_TGT_TOK = cgen_mod.MAX_TGT_TOK if mode == "cgen" else cparam_mod.MAX_TGT_TOK

    # ---- group: event order = first appearance in the file, within a group ascending sent_idx ----
    groups = {}
    order_list = []
    for line in open(path):
        r = json.loads(line)
        ev_id = r["event"]
        if ev_id not in groups:
            groups[ev_id] = []
            order_list.append(ev_id)
        groups[ev_id].append(r)
    events_all = []
    for idx, ev_id in enumerate(order_list):
        rs = sorted(groups[ev_id], key=lambda r: r["sent_idx"])
        events_all.append(dict(event=ev_id, orig_idx=idx,
                               full_text=rs[-1]["text"], rows_raw=rs))

    # ---- spot-check prefix properties (over all events before dropping, SEED fixed) ----
    rng_spot = random.Random(SEED)
    for e in rng_spot.sample(events_all, min(50, len(events_all))):
        assert all(e["full_text"].startswith(r["text"]) for r in e["rows_raw"]), \
            f"event {e['event']}'s sample texts are not mutual prefixes"

    # ---- tokenize each event's full text to get n_full, drop event-level overlong events per the drop rule ----
    # The criterion only looks at the token count of the event's full text, not the
    # packed sequence length (the packed sequence is bounded by the token budget as
    # a fallback).
    dropped_events = 0
    events_kept = []
    for e in events_all:
        full_ids = full_token_ids(tok, e["full_text"])
        if len(full_ids) > max_len:
            dropped_events += 1
            continue
        e["full_ids"] = full_ids
        e["n_full"] = len(full_ids)
        events_kept.append(e)

    # ---- take a subset by limit/order, then restore file order ----
    if limit and limit > 0:
        if order == "random":
            rng = random.Random(SEED)
            rng.shuffle(events_kept)
            events_kept = events_kept[:limit]
        else:                                          # "shortest"
            events_kept = sorted(events_kept, key=lambda e: e["n_full"])[:limit]
        events_kept.sort(key=lambda e: e["orig_idx"])

    # ---- tokenize line by line and apply row-level drops only on the events that remain ----
    dropped_rows_tgt = 0
    assembly_mismatch = 0
    n_rows = 0
    events = []
    for e in events_kept:
        rows = []
        for r in e["rows_raw"]:
            if ro is not None:
                ro["labels"].append(r["label"])
                if r["label"] not in ro["set"]:
                    ro["dropped"] += 1
                    continue
                ro["kept"] += 1
            if mode == "cgen":
                tail = cgen_mod.CALL_SEP
                tgt_str = r["label_call"]
                tool = None
                tgt_ids = tok(tgt_str,
                             add_special_tokens=False)["input_ids"]
                tgt_ids = tgt_ids + [tok.eos_token_id]
            else:
                tail = cparam_mod.param_prompt_tail(r["label"])
                tgt_str = cparam_mod.param_target(r["label"], r["label_call"])
                if tgt_str is None:
                    assembly_mismatch += 1
                    continue
                tool = r["label"]
                tgt_ids = tok(tgt_str, add_special_tokens=False)["input_ids"]
                tgt_ids = tgt_ids + [tok.eos_token_id]
            if len(tgt_ids) > MAX_TGT_TOK:
                dropped_rows_tgt += 1
                continue
            old_ids = tok(r["text"] + tail, add_special_tokens=False,
                          truncation=False)["input_ids"]
            p = _lcp(old_ids, e["full_ids"])
            tail_ids = old_ids[p:]
            assert len(tail_ids) >= 1, (
                f"event {e['event']} sent_idx={r['sent_idx']}: common prefix p={p} "
                f"consumed the entire tail (len(old_ids)={len(old_ids)}) -- the separator string collided "
                "with the full-text continuation, check the tokenizer version.")
            seg_ids = tail_ids + tgt_ids
            seg_lab = [-100] * len(tail_ids) + tgt_ids
            gen = dict(tgt=tgt_str, tool=tool)
            rows.append((r["sent_idx"], r["text"], p, seg_ids, seg_lab,
                        float(r["w"]), gen))
            n_rows += 1
        if not rows:
            # All rows of this event were dropped by the row-level drops (readonly/tgt too
            # long/mismatch); the event itself carries no training signal, so it does not go
            # into the return list -- its rows are already counted separately in
            # dropped_rows_tgt/assembly_mismatch/ro, so there is no need to count it again
            # here (dropped_events is reserved for the "event full text too long" criterion).
            continue
        prefix_len = max(row[2] for row in rows)
        packed_len = prefix_len + sum(len(row[3]) for row in rows)
        events.append(dict(event=e["event"], n_full=e["n_full"],
                           packed_len=packed_len, prefix_len=prefix_len,
                           full_ids=e["full_ids"], rows=rows))

    # ---- two hard stops (ported from train_causal_param.py lines 337-353) ----
    if n_rows == 0:
        raise SystemExit(
            f"{path} loaded to 0 rows (dropped_events={dropped_events}, "
            f"dropped_rows_tgt={dropped_rows_tgt}, "
            f"assembly_mismatch={assembly_mismatch}) -- "
            "the metric for picking best has no denominator, hard stop.")
    if mode == "cparam":
        tot = n_rows + assembly_mismatch
        limit_frac = cparam_mod.ASSEMBLY_MISMATCH_LIMIT
        if tot and assembly_mismatch / tot > limit_frac:
            raise SystemExit(
                f"{path}'s strip failure rate {assembly_mismatch}/{tot} = "
                f"{assembly_mismatch / tot:.3f} exceeds {limit_frac} -- "
                "upstream string-assembly settings drifted, hard stop.")

    # ---- packed-length upper-bound assertion (guards against tokenizer version drift stretching the tail) ----
    worst = max((e["packed_len"] for e in events), default=0)
    bound = max_len + MAX_BOUNDS * (MAX_TGT_TOK + 8)
    assert worst <= bound, (
        f"longest concatenated sequence {worst} exceeds the upper bound {bound}"
        f"(max_len={max_len}, MAX_BOUNDS={MAX_BOUNDS}, MAX_TGT_TOK={MAX_TGT_TOK})"
        " -- tokenizer version drift stretched the tail longer, hard stop.")

    counts = dict(dropped_events=dropped_events, dropped_rows_tgt=dropped_rows_tgt,
                 assembly_mismatch=assembly_mismatch, n_rows=n_rows)
    return events, counts


# ---------------------------------------------------------------- forward shape

def pack_event(ev):
    """The packed sequence for one event (spec section 4):

    ```
    tokens    = full_ids[:P] + seg_1 + seg_2 + ... + seg_K   # P = max_k p_k
    positions = [0..P-1] + [p_1, p_1+1, ...] + [p_2, p_2+1, ...] + ...
    labels    = [-100]*P + seg_lab_1 + ... + seg_lab_K
    ```

    Returns `(tokens, positions, labels, row_index, seg_bounds)`, all as plain
    python lists (torch conversion is left to `batch_mask`, since that is where
    the batch dimension and pad length get fixed):
    - `row_index[i]`: which row (index into `ev["rows"]`, 0-based) token i
      belongs to; the prefix is -1.
    - `seg_bounds[k]`: the `[start, end)` half-open range of row k's segment in
      `tokens`.
    """
    P = ev["prefix_len"]
    tokens = list(ev["full_ids"][:P])
    positions = list(range(P))
    labels = [-100] * P
    row_index = [-1] * P
    seg_bounds = []
    for k, row in enumerate(ev["rows"]):
        _sent_idx, _text, p, seg_ids, seg_lab, _w = row[:6]
        start = len(tokens)
        tokens.extend(seg_ids)
        positions.extend(range(p, p + len(seg_ids)))
        labels.extend(seg_lab)
        row_index.extend([k] * len(seg_ids))
        seg_bounds.append((start, len(tokens)))
    return tokens, positions, labels, row_index, seg_bounds


def _allowed_from_packed(positions, row_index, seg_bounds, L):
    """The core shared by `allowed_mask`/`batch_mask`: a [L, L] bool tensor (True = can attend).

    Attention allowance rule (spec section 4): causal within the prefix; the i-th
    token of segment k can attend to the first p_k positions of the prefix and
    the first i+1 tokens of its own segment; segments cannot attend to each
    other; the prefix cannot attend to any target segment.
    """
    row_t = torch.tensor(row_index, dtype=torch.long)
    idx = torch.arange(L)
    is_prefix = row_t < 0
    causal = idx.unsqueeze(0) <= idx.unsqueeze(1)          # [i, j] = (j <= i)

    qp = torch.zeros(L, dtype=torch.long)                  # p_k for each target segment position
    for start, end in seg_bounds:
        qp[start:end] = positions[start]

    prefix_prefix = is_prefix.unsqueeze(1) & is_prefix.unsqueeze(0) & causal
    same_row = row_t.unsqueeze(1) == row_t.unsqueeze(0)
    seg_self = same_row & (~is_prefix).unsqueeze(1) & causal
    seg_sees_prefix = ((~is_prefix).unsqueeze(1) & is_prefix.unsqueeze(0)
                       & (idx.unsqueeze(0) < qp.unsqueeze(1)))
    return prefix_prefix | seg_self | seg_sees_prefix


def allowed_mask(ev):
    """A `[L, L]` bool tensor for one event (True = can attend), per spec section 4."""
    tokens, positions, labels, row_index, seg_bounds = pack_event(ev)
    return _allowed_from_packed(positions, row_index, seg_bounds, len(tokens))


def batch_mask(packed_list, L_pad):
    """Right-pad several `pack_event` results from one physical block to `L_pad` (a multiple of 16).

    `packed_list`: `[pack_event(ev), ...]`, the caller has already run
    `pack_event` on every event in the block.

    Returns `(input_ids, position_ids, mask, loss_idx)`:
    - `input_ids`: `[B, L_pad]` long; pad positions hold `PAD_TOKEN_ID` (a pad row
      only attends to itself, so this value does not affect the output of any
      real token).
    - `position_ids`: `[B, L_pad]` long; pad positions continue counting from
      this event's last real position (spec section 4: "the pad positions
      padded up to 16 must also get position_ids [that keep counting]"), not a
      hardcoded 0.
    - `mask`: `[B, 1, L_pad, L_pad]` bf16 additive mask (0 = can attend, -inf =
      cannot); a pad row as query only lets the pad attend to itself (a row
      that cannot attend to anything makes softmax produce NaN; real tokens
      cannot attend to pad).
    - `loss_idx`: `[(batch_idx, qpos, target_id, row_idx), ...]`. Values are
      read from the `labels` array itself (labels are not shifted): the target
      token where `labels[t] != -100` is produced by the logits at position
      `t-1`, so the query position is `t-1`, the target id is `labels[t]`, and
      the row number is `row_index[t]`. Pad positions produce no `loss_idx`
      entries at all (pad never appears in `labels`).
    """
    assert L_pad % 16 == 0, f"L_pad must be a multiple of 16, got {L_pad}"
    B = len(packed_list)
    input_ids = torch.full((B, L_pad), PAD_TOKEN_ID, dtype=torch.long)
    position_ids = torch.zeros((B, L_pad), dtype=torch.long)
    mask = torch.empty((B, 1, L_pad, L_pad), dtype=torch.bfloat16)
    loss_idx = []
    for b, packed in enumerate(packed_list):
        tokens, positions, labels, row_index, seg_bounds = packed
        L = len(tokens)
        assert L <= L_pad, f"event length {L} exceeds the physical block pad length {L_pad}"
        input_ids[b, :L] = torch.tensor(tokens, dtype=torch.long)
        position_ids[b, :L] = torch.tensor(positions, dtype=torch.long)
        if L < L_pad:
            last_pos = positions[-1] if positions else -1
            position_ids[b, L:] = torch.arange(
                last_pos + 1, last_pos + 1 + (L_pad - L), dtype=torch.long)
        allowed = _allowed_from_packed(positions, row_index, seg_bounds, L)
        block = torch.full((L_pad, L_pad), float("-inf"), dtype=torch.bfloat16)
        real = torch.zeros((L, L), dtype=torch.bfloat16)
        real.masked_fill_(~allowed, float("-inf"))
        block[:L, :L] = real
        for i in range(L, L_pad):                          # a pad row as query only attends to itself
            block[i, i] = 0.0
        mask[b, 0] = block
        for t in range(1, L):
            if labels[t] != -100:
                loss_idx.append((b, t - 1, labels[t], row_index[t]))
    return input_ids, position_ids, mask, loss_idx


def epoch_minibatches(events, seed, ep, events_per_mb):
    """Event order and logical-microbatch splitting for one epoch (spec 16.5, ticket
    10): the single source shared by the training loop and the `cost`/`loop` GPU
    memory probes -- the blocks the probe hits must be blocks the training loop
    will actually encounter. `events` itself is not mutated (a `list(events)`
    copy is made first, then shuffled).

    Shuffle with `random.Random(seed + ep).shuffle`, then split into logical
    microbatches of `events_per_mb` each, identical step by step to the old code
    (these two steps used to be done by the training loop itself).
    """
    epoch_events = list(events)
    random.Random(seed + ep).shuffle(epoch_events)
    return [epoch_events[i:i + events_per_mb]
           for i in range(0, len(epoch_events), events_per_mb)]


def chunk_by_budget(events, tok_budget):
    """Greedy block packing per spec section 5, item 2.

    Sort events by descending `packed_len`, then pack greedily: a block's "event
    count x L_pad" <= `tok_budget` (`L_pad` = the block's longest `packed_len`
    padded up to a multiple of 16, `_pad16` -- the budget criterion uses the
    same accounting as `batch_mask`'s padding, not the raw `packed_len` before
    padding, spec section 5); when a single event exceeds the budget it becomes
    its own block (over-budget is allowed).

    Returns a list of blocks, each block a list of events (order within a block
    = insertion order, i.e. the order within the descending-`packed_len` sort; a
    block only fixes "which events go through one forward pass together" -- it
    makes no promise about the file-order contract, that contract belongs only
    to `load_events`'s return value).
    """
    ordered = sorted(events, key=lambda e: e["packed_len"], reverse=True)
    blocks = []
    current = []
    current_max = 0
    for e in ordered:
        n = len(current) + 1
        cand_max = current_max if current else e["packed_len"]
        if n * _pad16(cand_max) <= tok_budget:
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


def worst_blocks(events, tok_budget, events_per_mb):
    """For `--mem-probe` to use (spec section 10): returns two event lists.

    The first holds only the single event with the largest `packed_len` (length 1).

    The second (the "fullest block") does not borrow `chunk_by_budget`: in real
    training a logical microbatch has only `events_per_mb` events (spec section
    5), and `chunk_by_budget` only packs blocks over those `events_per_mb`
    events, so a block's event count is naturally <= `events_per_mb`; but
    `worst_blocks` looks for the worst block over the whole training set, and
    running `chunk_by_budget` directly over all events and then picking the
    block with the "largest longest-event" would let a block's event count
    exceed `events_per_mb`, so the block found might never occur in real
    training. So the fullest block is searched separately with the algorithm
    defined in the ticket: for `B` from 2 to `events_per_mb`, sort events by
    descending `packed_len`, and for each B slide a window of size B down from
    the longest end, taking the first window that satisfies `B * L_pad <=
    tok_budget` (`L_pad` = the window's longest `packed_len` padded up to a
    multiple of 16, `_pad16`; under descending order the window's longest is
    exactly its first element, and this value can only shrink or stay the same
    as the window moves down, so the first window that satisfies the condition
    is the largest `B * L_pad` this B can reach); among the optimal windows for
    each B, take the group with the largest `B * L_pad`. When no window
    satisfies the condition (not enough events, or the budget too small to fit
    even 2 events), the second list comes back empty.
    """
    if not events:
        return [], []
    longest = max(events, key=lambda e: e["packed_len"])
    ordered = sorted(events, key=lambda e: e["packed_len"], reverse=True)
    n_events = len(ordered)
    best_group = []
    best_product = -1
    for b in range(2, events_per_mb + 1):
        for i in range(n_events - b + 1):
            window = ordered[i:i + b]
            l_pad = _pad16(window[0]["packed_len"])
            product = b * l_pad
            if product <= tok_budget:
                if product > best_product:
                    best_product = product
                    best_group = window
                break                       # under descending order, the first window that satisfies it is the optimal window for this B
    return [longest], best_group


# ---------------------------------------------------------------- read position

def read_position(offsets, full_text, cut, keep):
    """The read-position rule from spec 11.3.

    `offsets`: the tokenizer's `offset_mapping` (each item a `(start, end)`
    half-open character-offset range); `full_text`: the full text; `cut`: the
    character position of the cut point; `keep`: the sum of this row's
    `attention_mask` (the real token count, look only within `offsets[:keep]`).

    `j` = the last real token whose start position < `cut` (the token that
    covers character `cut-1`). Read `j` when `end_j <= cut`; also read `j` when
    `end_j > cut` and `full_text[cut:end_j]` is all whitespace; otherwise read
    `j-1`. Two cases return -1 (not found): no real token has a start position <
    `cut`; or falling back to `j-1` while `j = 0`.
    """
    j = -1
    for t in range(keep - 1, -1, -1):
        if offsets[t][0] < cut:
            j = t
            break
    if j < 0:
        return -1
    end_j = offsets[j][1]
    if end_j <= cut:
        return j
    if full_text[cut:end_j].isspace():
        return j
    if j == 0:
        return -1
    return j - 1
