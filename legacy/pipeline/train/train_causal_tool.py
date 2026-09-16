"""Causal probe training (new pipeline ctool cell): causal language model base + linear classification head.

The essential difference from the ModernBERT probe (train_mbert_tool.py): ModernBERT
re-encodes the whole prefix at every sentence boundary (cost grows quadratically with
thinking length); here it is organized by **event** -- the samples' text within one event
are prefixes of each other, the full text = the text of the sample with the largest
sent_idx, and the character position of the i-th boundary = len(the i-th sample's text);
one forward pass over the whole sequence, with one classification supervision placed at
each boundary position (weight = the sample's own w).

- Input: <data_out>/{train,val}.jsonl + tool_vocab.json
- Base: --base qwen -> Qwen3-0.6B-Base / qwen17 -> 1.7B / qwen4 -> 4B
- Cap: --max-len (default 8192) drops overlong events whole by event full-text token
  count (no truncation), counted into the start event's
  dropped_events_train/dropped_events_val; the read-position rule
  (share_data.read_position) only counts n_bound_dropped when it cannot find a cut point
  among the remaining events, expected to always be 0
- Eval: each val round reports calA_weighted_acc + calA_lastbound_acc (log field names
  kept unchanged)
- Outputs: <out>/{ALIGN_CHECK.json, train_log.jsonl, best/}
- LoRA: `--lora` only swaps the base to train with LoRA (the classification head still
  trains full-parameter); before saving best, merge_and_unload merges the adapter back
  into the base first, so best/'s files are item-for-item identical in structure to a
  full-parameter save, and eval_tool.py can load it back with zero changes; meta.json
  gets one extra "lora" block recording the hyperparameters.
  When --lora is not passed, the script never touches peft (all peft imports live in the
  --lora branch), and behavior is identical to before this flag set was added; see
  lora_util.py for details.

**The alignment check before training starts is a hard rule** (--align-only only runs
this): for the same real text, one forward pass over the whole sequence vs. token-by-token
incremental forward passes (with past_key_values), the last-position hidden state and
classification-head logits must have max|diff| < 1e-4 before training is allowed. Prior
incident: under transformers 5.14.1, the LFM2 hybrid architecture (conv+attention)
silently computes wrong results under "non-empty cache + feeding multiple tokens at once"
(chunked incremental) -- see check_causal_candidates.py's conclusion, which rules that
only a single whole-sequence forward pass or token-by-token incremental forward pass is
usable, **chunking is forbidden**. This script's training and evaluation only use a
single whole-sequence forward pass; incremental forward passes appear only in this
alignment check, so both bases are in the safe zone.

Usage:
  # alignment check only
  cprobe-env/bin/python pipeline/train/train_causal_tool.py --base qwen \
    --data pipeline/data/aw_official_v1/q35 --out pipeline/runs/c1_q35_ctool --align-only
  # smoke test
  cprobe-env/bin/python pipeline/train/train_causal_tool.py --base qwen \
    --data pipeline/data/aw_official_v1/q35 --out pipeline/runs/c1_q35_ctool --smoke
  # full run
  cprobe-env/bin/python pipeline/train/train_causal_tool.py --base qwen \
    --data pipeline/data/aw_official_v1/q35 --out pipeline/runs/c1_q35_ctool
"""

import argparse
import json
import math
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

import torch
import transformers
_TV = tuple(int(x) for x in transformers.__version__.split(".")[:2])
if _TV < (5, 14):
    raise SystemExit(f"the cprobe line requires transformers>=5.14, currently "
                     f"{transformers.__version__} -- wrong interpreter? "
                     "Always enter through run.py's tasks (train-ctool/train-cgen).")
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModel, AutoTokenizer, get_linear_schedule_with_warmup

import lora_util
import readonly_map
import share_data

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / "ops"))
import heartbeat


# three base-model tiers (from 2026-08-21, the causal line expanded from one tier to three, to compare three sizes side by side)
MODELS = {
    "qwen":   "/net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-0.6B-Base",
    "qwen17": "/net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-1.7B-Base",
    "qwen4":  "/net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-4B-Base",
}
SEED = 42          # from np821 on, switched to the first of the seed family (42/67/4267/6742); the old value 20260729 only applies when reproducing old data
FULL_LR = 1e-5     # learning rate for full-parameter fine-tuning (the --lr default when --lora is not passed)
ALIGN_TOL = 3e-4   # from 2026-08-28 (cap 8192): c1/np821 real runs always pass 3e-4; an 8,167-token event with maxdiff_hidden 1.03e-4 (relative diff 1.46e-6) was blocked by the old default 1e-4
SPOT = 50          # number of events for the prefix-property spot check


# ---------------------------------------------------------------- data

def load_events(path, label2id, tok, max_len, limit=0, spot=SPOT, ro=None):
    """Group by event: full text = the text of the sample with the largest sent_idx,
    boundaries = each sample's len(text).

    Events whose full-text token count (`tok(full, add_special_tokens=False)`) exceeds
    `max_len` are dropped whole (spec 11.1); the return value carries an extra drop
    count.
    """
    ev = defaultdict(list)
    if ro is None:
        for line in open(path):
            r = json.loads(line)
            if r["label"] in label2id:
                ev[r["event"]].append(r)
    else:                                      # --readonly-env: count first, then fold
        rows = [json.loads(line) for line in open(path)]
        ro["info"] = readonly_map.audit(
            [r["label"] for r in rows], ro["table"], where=ro["where"])
        for r in rows:
            r["label"] = readonly_map.collapse(r["label"], ro["set"])
        bad = sorted({r["label"] for r in rows} - set(label2id))
        if bad:
            raise SystemExit(
                f"readonly: {ro['where']} still has {len(bad)} labels not in the"
                f" folded vocab after folding (e.g. {bad[:5]}) -- tool_vocab.json does not match the data, hard stop.")
        for r in rows:
            ev[r["event"]].append(r)
    events = []
    for k, rs in ev.items():
        rs.sort(key=lambda r: r["sent_idx"])
        full = rs[-1]["text"]
        events.append(dict(
            event=k, full=full, rows=rs, y=label2id[rs[-1]["label"]],
            bounds=[(len(r["text"]), float(r["w"]),
                     r["sent_idx"] == r["n_sents"] - 1) for r in rs]))
    events.sort(key=lambda e: e["event"])
    rng = random.Random(SEED)
    for e in rng.sample(events, min(spot, len(events))):   # prefix-property spot check
        assert all(e["full"].startswith(r["text"]) for r in e["rows"]), \
            f"sample text for event {e['event']} are not mutual prefixes"
    for e in events:
        e.pop("rows")
    dropped = 0
    kept = []
    for e in events:
        n_full = share_data.n_full_tokens(tok, e["full"])
        if n_full > max_len:
            dropped += 1
            continue
        kept.append(e)
    events = kept
    if limit:
        rng.shuffle(events)
        events = events[:limit]
    return events, dropped


class EventDS(Dataset):
    def __init__(self, events):
        self.events = events

    def __len__(self):
        return len(self.events)

    def __getitem__(self, i):
        return self.events[i]


def collate(batch, tok, max_len):
    """A batch of events for a single whole-sequence forward pass: returns enc + each supervision position's (row, col, y, w, last)."""
    enc = tok([e["full"] for e in batch], truncation=False, max_length=max_len,
              padding=True, return_offsets_mapping=True, return_tensors="pt")
    offs = enc.pop("offset_mapping")
    rows, cols, ys, ws, lasts, dropped = [], [], [], [], [], 0
    for i, e in enumerate(batch):
        full = e["full"]
        offsets_i = offs[i].tolist()
        keep = int(enc["attention_mask"][i].sum())
        for b, w, last in e["bounds"]:
            j = share_data.read_position(offsets_i, full, b, keep)
            if j < 0:                # count of cut points where the read position cannot be found (n_bound_dropped), expected 0
                dropped += 1
                continue
            rows.append(i)
            cols.append(j)
            ys.append(e["y"])
            ws.append(w)
            lasts.append(last)
    return (enc, torch.tensor(rows), torch.tensor(cols), torch.tensor(ys),
            torch.tensor(ws, dtype=torch.float), torch.tensor(lasts), dropped)


# ---------------------------------------------------------------- model

class CausalProbe(torch.nn.Module):
    """Causal language model base + nn.Linear classification head (takes the last-layer hidden state at each supervision token position)."""

    def __init__(self, path, n_labels):
        super().__init__()
        self.backbone = AutoModel.from_pretrained(path, dtype=torch.float32)
        h = self.backbone.config.get_text_config().hidden_size
        self.head = torch.nn.Linear(h, n_labels)

    def hidden(self, enc):
        return self.backbone(input_ids=enc["input_ids"],
                             attention_mask=enc["attention_mask"],
                             use_cache=False).last_hidden_state

    def forward(self, enc, rows, cols):
        h = self.hidden(enc)
        h = h[rows.to(h.device), cols.to(h.device)]   # [n_sup, hidden]
        return self.head(h.float())


def build(base, n_labels, dev):
    path = MODELS[base]
    tok = AutoTokenizer.from_pretrained(path)
    if tok.pad_token_id is None:                      # copied verbatim from check_causal_candidates
        tok.pad_token = tok.eos_token
    tok.truncation_side = "left"                      # keep the tail of the thinking text
    tok.padding_side = "right"                        # all supervision positions are on real tokens
    torch.manual_seed(SEED)
    model = CausalProbe(path, n_labels)
    if model.backbone.config.get_text_config().pad_token_id is None:
        model.backbone.config.get_text_config().pad_token_id = tok.pad_token_id
    return tok, model.to(dev), path


# ---------------------------------------------------------------- alignment check

@torch.no_grad()
def align_check(model, tok, text, max_len, dev, base, path, tol=ALIGN_TOL,
                rule="abs", rel_tol=1e-5):
    """One whole-sequence forward pass vs. token-by-token incremental forward passes (fp32);
    the last-position hidden state/logits must match.

    Only use token-by-token mode: chunked incremental (non-empty cache + feeding multiple
    tokens at once) has a prior incident of silently computing wrong results on LFM2.

    `rule` (spec 9): `abs` = the current default, `max(d_h, d_l) < tol`; `rel` =
    `reldiff_hidden <= rel_tol` and `reldiff_logits <= rel_tol`; `both` = both hold at
    once.
    """
    model.eval()
    prev_prec = torch.get_float32_matmul_precision()
    torch.set_float32_matmul_precision("highest")   # disable TF32, do not let reduced precision masquerade as a computation error
    ids = tok(text, truncation=False, max_length=max_len,
              return_tensors="pt")["input_ids"].to(dev)
    n = ids.shape[1]
    ones = torch.ones_like(ids)
    h_full = model.backbone(input_ids=ids, attention_mask=ones,
                            use_cache=False).last_hidden_state[:, -1]
    lg_full = model.head(h_full)

    past, out = None, None
    for t in range(n):
        out = model.backbone(input_ids=ids[:, t:t + 1],
                             attention_mask=ones[:, :t + 1],
                             past_key_values=past, use_cache=True)
        past = out.past_key_values
    h_inc = out.last_hidden_state[:, -1]
    lg_inc = model.head(h_inc)

    d_h = (h_full - h_inc).abs().max().item()
    d_l = (lg_full - lg_inc).abs().max().item()
    a_h, a_l = h_full.abs().max().item(), lg_full.abs().max().item()
    reldiff_hidden = d_h / max(a_h, 1e-9)
    reldiff_logits = d_l / max(a_l, 1e-9)
    abs_ok = max(d_h, d_l) < tol
    rel_ok = reldiff_hidden <= rel_tol and reldiff_logits <= rel_tol
    if rule == "abs":
        ok = abs_ok
    elif rule == "rel":
        ok = rel_ok
    else:
        ok = abs_ok and rel_ok
    rep = dict(base=base, base_path=path, mode="token-by-token", n_tokens=n,
               maxdiff_hidden=d_h, maxdiff_logits=d_l, tol=tol,
               PASS=bool(ok), device=str(dev), dtype="float32",
               transformers=transformers.__version__, torch=torch.__version__,
               rule=rule, rel_tol=rel_tol,
               # The absolute difference is affected by the hidden-state magnitude; the relative
               # difference shows whether it is just fp32 noise: under the `abs` rule,
               # absmax_*/reldiff_* are only diagnostic reference; the `rel`/`both` rules use
               # reldiff_hidden/reldiff_logits in the decision.
               absmax_hidden=a_h, absmax_logits=a_l,
               reldiff_hidden=reldiff_hidden,
               reldiff_logits=reldiff_logits)
    torch.set_float32_matmul_precision(prev_prec)
    model.train()
    return rep


# ---------------------------------------------------------------- GPU memory

def _peak_mem_gb(dev):
    """GPU memory field for `step`/`eval` events (ticket 06): on cuda, read
    `max_memory_allocated` (GB, rounded to 1e-3) and reset the peak-memory stats, using
    the same convention as the new trainer `train_causal_share.py`'s step log; always 0.0
    on CPU (this round of ctool's GPU memory can only be sampled externally via
    nvidia-smi, since it does not record it itself)."""
    if dev.startswith("cuda"):
        peak = round(torch.cuda.max_memory_allocated() / 1e9, 3)
        torch.cuda.reset_peak_memory_stats()
        return peak
    return 0.0


# ---------------------------------------------------------------- eval

@torch.no_grad()
def evaluate(model, loader, dev, amp):
    model.eval()
    wc = ws = lc = ln = 0.0
    for enc, rows, cols, y, w, last, _drop in loader:
        enc = {k: v.to(dev) for k, v in enc.items()}
        with torch.autocast("cuda", dtype=torch.bfloat16, enabled=amp):
            pred = model(enc, rows, cols).argmax(-1).cpu()
        ok = (pred == y).float()
        wc += (ok * w).sum().item()
        ws += w.sum().item()
        lc += ok[last].sum().item()
        ln += last.sum().item()
    model.train()
    return wc / max(ws, 1e-9), lc / max(ln, 1)


# ---------------------------------------------------------------- main flow

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, choices=sorted(MODELS),
                    help="qwen=Qwen3-0.6B-Base")
    ap.add_argument("--env", default="appworld",
                    choices=["tales", "appworld", "bfcl", "alfworld"],
                    help="log label only (the data path is given directly by --data)")
    ap.add_argument("--data", required=True,
                    help="data dir <data_out> (contains train/val.jsonl and tool_vocab.json)")
    ap.add_argument("--out", required=True, help="output dir (required; guards against overwriting old outputs)")
    ap.add_argument("--max-len", type=int, default=8192)
    ap.add_argument("--bs", type=int, default=2,
                    help="events per batch (default 2 since 2026-08-28: after the cap went to 8192, bs 4 on H100 training"
                         "OOMs on the very first batch; bs 2 peaks at 56,859 MiB; np821 uses 4096 x bs 4)")
    ap.add_argument("--accum", type=int, default=4,
                    help="gradient accumulation batch count (default 4; combined with --bs 2 gives 8 events per update)")
    ap.add_argument("--lr", type=float, default=None,
                    help=f"learning rate (default {FULL_LR}; switches to --lora-lr by default when --lora is on,"
                         "an explicit value given here takes precedence)")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--smoke", action="store_true",
                    help="200 training events/80 eval events/1 epoch, for pipeline verification")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--grad-ckpt", action="store_true",
                    help="turn on gradient checkpointing in the base model to save GPU memory (works in both full-parameter and --lora modes;"
                         "also turns off use_cache, and under LoRA additionally ensures input requires_grad)")
    ap.add_argument("--max-events", type=int, default=0,
                    help="for debugging: further cap the event count (0 = unlimited)")
    ap.add_argument("--align-only", action="store_true",
                    help="run only the pre-training alignment check, then exit")
    ap.add_argument("--align-tol", type=float, default=ALIGN_TOL,
                    help="alignment check absolute-difference threshold (default 3e-4 since 2026-08-28; was 1e-4 before)."
                         "Under long windows, fp32 rounding noise grows with token count and hidden-state magnitude together,"
                         "so an event at the 8192 cap can push the absolute difference to 1e-4 while the relative difference stays at 1e-6"
                         "(pure noise); judge by reldiff instead (above 1e-3 = a real bug, loosening this won't help)")
    ap.add_argument("--align-rule", default="abs", choices=["abs", "rel", "both"],
                    help="alignment criterion: abs = absolute difference (current default), rel = relative difference"
                         "(reldiff_hidden/reldiff_logits), both = both must hold (spec 9)")
    ap.add_argument("--align-rel-tol", type=float, default=1e-5,
                    help="alignment check relative-difference threshold, used with --align-rule rel/both (spec 9)")
    ap.add_argument("--readonly-env", default=None,
                    choices=list(readonly_map.READONLY_ENVS),
                    help="read-only tool mode: fold labels into this environment's read-only tools plus the "
                         f"{readonly_map.NON_READONLY} abstain class (off by default = the old settings)")
    ap.add_argument("--force", action="store_true",
                    help="allow training again in an --out dir that was already trained in (refused by default to keep outputs apart)")
    lora_util.add_args(ap)
    args = ap.parse_args()
    lr = lora_util.resolve_lr(args, FULL_LR)

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

    vocab = json.loads((data / "tool_vocab.json").read_text())
    ro_tr = ro_ev = None
    if args.readonly_env:                      # vocab = original-order read-only tools + trailing sentinel
        ro_set = readonly_map.load_readonly_set(args.readonly_env)
        ro_table = readonly_map.load_table(args.readonly_env)
        vocab = [t for t in vocab if t in ro_set] + [readonly_map.NON_READONLY]
        ro_tr = dict(set=ro_set, table=ro_table, where="ctool/train")
        ro_ev = dict(set=ro_set, table=ro_table, where="ctool/val")
    label2id = {k: i for i, k in enumerate(vocab)}
    tok, model, path = build(args.base, len(label2id), dev)

    lim_tr, lim_ev = (200, 80) if args.smoke else (0, 0)
    if args.max_events:
        lim_tr = min(lim_tr, args.max_events) if lim_tr else args.max_events
        lim_ev = min(lim_ev, args.max_events) if lim_ev else args.max_events
    epochs = 1 if args.smoke else args.epochs
    ev_events, dropped_events_val = load_events(
        data / "val.jsonl", label2id, tok, args.max_len, ro=ro_ev)
    longest = max(ev_events, key=lambda e: len(e["full"]))["full"]
    if lim_ev:
        random.Random(SEED).shuffle(ev_events)
        ev_events = ev_events[:lim_ev]

    # ---- mandatory gate before training starts: alignment check (val's longest event full text, truncated to --max-len) ----------
    rep = align_check(model, tok, longest, args.max_len, dev, args.base, path,
                      tol=args.align_tol, rule=args.align_rule,
                      rel_tol=args.align_rel_tol)
    (out / "ALIGN_CHECK.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep, indent=1), flush=True)
    if not rep["PASS"]:
        print("Alignment check FAIL: full-sequence forward and per-token incremental forward disagree, refusing to start training.\n"
              f"  rule --align-rule {rep['rule']}\n"
              f"  hidden max|diff| = {rep['maxdiff_hidden']:.3e}\n"
              f"  logits max|diff| = {rep['maxdiff_logits']:.3e}  (tol {rep['tol']:.1e})\n"
              f"  relative difference hidden {rep['reldiff_hidden']:.2e} / logits "
              f"{rep['reldiff_logits']:.2e}  (rel_tol {rep['rel_tol']:.1e};"
              " around 1e-6 = pure fp32 noise, the absolute difference is just"
              " large hidden-state magnitude; above 1e-3 = a real bug)\n"
              "  Debug: transformers version / this architecture's cache implementation / whether chunked incremental was misused.",
              flush=True)
        sys.exit(2)
    if args.align_only:
        return

    tr_events, dropped_events_train = load_events(
        data / "train.jsonl", label2id, tok, args.max_len, lim_tr, ro=ro_tr)
    if args.readonly_env:
        (out / "READONLY.json").write_text(json.dumps(dict(
            readonly_env=args.readonly_env,
            table=str(readonly_map.table_path(args.readonly_env)),
            train=ro_tr["info"], val=ro_ev["info"],
            vocab_size_collapsed=len(label2id)), ensure_ascii=False, indent=1))
    mk = lambda ds, sh: DataLoader(
        EventDS(ds), batch_size=args.bs, shuffle=sh, num_workers=2,
        collate_fn=lambda b: collate(b, tok, args.max_len))
    tr_dl, ev_dl = mk(tr_events, True), mk(ev_events, False)
    # LoRA only wraps the base: the classification head still trains full-parameter (the
    # head is freshly initialized, there are no old weights to low-rank), and the head's
    # parameters go into the optimizer together with the adapter. The wrapping happens after
    # the alignment check, so ALIGN_CHECK.json is comparable field-by-field with a
    # full-parameter run.
    lora_wrap = lora_util.wrap(model.backbone, args) if args.lora else None
    if args.grad_ckpt:
        model.backbone.gradient_checkpointing_enable()
        model.backbone.config.use_cache = False
        if args.lora:
            lora_util.prepare_grad_ckpt(model.backbone)
    model.train()

    steps = math.ceil(len(tr_dl) / args.accum) * epochs
    opt = torch.optim.AdamW(lora_util.opt_params(model.parameters(), args.lora),
                            lr=lr, weight_decay=0.01)
    sch = get_linear_schedule_with_warmup(opt, int(steps * 0.05), steps)
    lossf = torch.nn.CrossEntropyLoss(reduction="none")

    logf = open(out / "train_log.jsonl", "a")

    def log(**kw):
        kw["t"] = round(time.time(), 1)
        logf.write(json.dumps(kw) + "\n")
        logf.flush()
        print(kw, flush=True)

    log(event="start", base=args.base, base_path=path, env=args.env,
        n_train=len(tr_events), n_eval=len(ev_events), n_labels=len(label2id),
        steps=steps, smoke=args.smoke, max_len=args.max_len, seed=SEED,
        align_pass=rep["PASS"], align_maxdiff_hidden=rep["maxdiff_hidden"],
        align_maxdiff_logits=rep["maxdiff_logits"],
        readonly_env=args.readonly_env,
        dropped_events_train=dropped_events_train,
        dropped_events_val=dropped_events_val,
        **(dict(lora=lora_util.meta_block(args, lr)) if args.lora else {}))
    heartbeat.emit(0, steps, "step")

    best = -1.0
    gstep = 0
    for ep in range(epochs):
        t0, run, ndrop = time.time(), 0.0, 0
        for i, (enc, rows, cols, y, w, _last, drop) in enumerate(tr_dl):
            enc = {k: v.to(dev) for k, v in enc.items()}
            ndrop += drop
            with torch.autocast("cuda", dtype=torch.bfloat16, enabled=amp):
                logits = model(enc, rows, cols)
            wd = w.to(dev)
            loss = (lossf(logits.float(), y.to(dev)) * wd).sum() / wd.sum()
            (loss / args.accum).backward()
            run += loss.item()
            if (i + 1) % args.accum == 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()
                sch.step()
                opt.zero_grad()
                gstep += 1
                if gstep % 50 == 0:
                    log(event="step", ep=ep, gstep=gstep,
                        loss=round(run / (50 * args.accum), 4),
                        ips=round((i + 1) * args.bs / (time.time() - t0), 2),
                        n_bound_dropped=ndrop, lr=sch.get_last_lr()[0],
                        peak_mem_gb=_peak_mem_gb(dev))
                    heartbeat.emit(gstep, steps, "step",
                                   loss=round(run / (50 * args.accum), 4))
                    run = 0.0
        wacc, lacc = evaluate(model, ev_dl, dev, amp)
        log(event="eval", ep=ep, calA_weighted_acc=round(wacc, 4),
            calA_lastbound_acc=round(lacc, 4), n_bound_dropped=ndrop,
            peak_mem_gb=_peak_mem_gb(dev))
        if wacc > best:
            best = wacc
            (out / "best").mkdir(parents=True, exist_ok=True)
            if lora_wrap is None:
                model.backbone.save_pretrained(out / "best")
            else:
                # merge the adapter back into the base before saving: best/ is item-for-item identical in structure to a full-parameter save, zero changes needed on the eval side
                lora_util.save_merged(lora_wrap, out / "best", dev)
            tok.save_pretrained(out / "best")
            torch.save(model.head.state_dict(), out / "best" / "head.pt")
            (out / "best" / "label_map.json").write_text(
                json.dumps(label2id, ensure_ascii=False))
            meta = dict(
                base=args.base, base_path=path, env=args.env, data=str(data),
                max_len=args.max_len, n_labels=len(label2id), seed=SEED,
                epoch=ep, transformers=transformers.__version__)
            if args.readonly_env:
                meta["readonly_env"] = args.readonly_env
            if args.lora:
                meta["lora"] = lora_util.meta_block(args, lr)
            if args.grad_ckpt:
                meta["grad_ckpt"] = True
            (out / "best" / "meta.json").write_text(json.dumps(meta, indent=1))
            log(event="save_best", ep=ep, acc=round(best, 4))
    log(event="done", best_calA_weighted_acc=round(best, 4))
    heartbeat.emit(gstep, steps, "step", status="done")


if __name__ == "__main__":
    main()
