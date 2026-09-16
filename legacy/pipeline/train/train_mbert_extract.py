"""Extraction-head training (new pipeline mext cell): ModernBERT base + start/end pointer head + answerable head.

- Input: <data_out>/{train,val}.jsonl (text) and <data_out>/params/ files of the same name
  (parameter span labels), joined by event+sent_idx
- Instance = (sample x parameter); the query is appended at the **end**: text + "\\n[FIND] " + tool_name.param_name
  (tokenizer left-truncates to 4096, keeping the tail of the thinking text and the query;
  the character span is not affected by the suffix)
- Character span -> token span takes the **minimum covering token span** (offset_mapping);
  a span cut off by left truncation is counted as training "not extractable"
- Loss = answerable BCE + found instances' start/end CE, both weighted by the sample weight w
- Two sets of correctness criteria (BPE merges leading spaces/quotes into tokens, so
  strict character-by-character comparison underestimates):
    loose (primary)   the predicted character span covers ground truth, and any extra characters are only whitespace/punctuation
    strict (control)  the predicted span's decoded text matches ground truth character-for-character
- Each val round reports: answerable accuracy / span hit (loose x strict) / parameter-level
  overall accuracy, weighted by w; log and meta field names keep the old calA_* names
  (downstream scripts read by name)
- Outputs: <out>/best/(model.pt + tokenizer + meta.json) + train_log.jsonl

Fire head (`--fire-head`, must be passed together with --readonly-env; default not
passed = same behavior as the old version):
- Attach one more sample-level binary classification head on the same encoder ([CLS]
  position hidden state -> Linear -> 1), learning "should this fire speculation right
  now". Fire label
  ready = the label is in that environment's read-only set AND all of the sample's
  parameters have found=true
  (a zero-parameter event's found condition is vacuously true; samples that cannot be
  joined in the params file are recorded as not-ready and counted)
- The fire head runs on an **independent sample-level data flow**: the input is plain
  text (without the [FIND] suffix, matching what live firing actually sees as input), one
  sample = one instance, so there is no "the same sample re-weighted by its parameter
  count"; non-read-only samples are no longer dropped whole, instead they go back into
  this flow as negative examples (they produce no span instances, so they contribute zero
  gradient to the original task)
- Loss = original span/answerable loss + λ * fire BCE (λ=1), the two flows each form
  their own batches and are each weighted by w
- The metric for picking best is unchanged (val parameter accuracy, computed on read-only
  samples); the fire head's weights are saved along with model.pt (the bare state_dict
  plus two extra keys), meta.json gets an added "fire_head": true; val's fire acc@0.5 and
  the positive/negative counts go into train_log's eval event

Usage (smoke):
  mbert-env/bin/python pipeline/train/train_mbert_extract.py \
    --data pipeline/data/aw_official_v1/q35 --out pipeline/runs/c1_q35_mext --smoke
"""

import argparse
import contextlib
import json
import math
import random
import time
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset
import transformers
# dual-environment hard rule (run.py's PY table): the mbert line is pinned to
# transformers==4.57.6; behavior drift from running the wrong interpreter is silent, so
# reject it outright here
if transformers.__version__ != "4.57.6":
    raise SystemExit(f"the mbert line pins transformers==4.57.6, currently "
                     f"{transformers.__version__} -- wrong interpreter? "
                     "Always enter through run.py's tasks (train-mtool/train-mext).")
from transformers import (AutoTokenizer, ModernBertModel,
                          get_linear_schedule_with_warmup)

import readonly_map

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / "ops"))
import heartbeat


MODEL = "/net/tokyo100-10g/data/str01_01/y-guo/models/ModernBERT-base"
SEED = 20260729
FIND = "\n[FIND] "
MAX_SPAN_TOK = 64          # max start/end span at decode time


class Extractor(nn.Module):
    def __init__(self, base_path=MODEL, fire=False):
        super().__init__()
        self.base = ModernBertModel.from_pretrained(
            base_path, attn_implementation="sdpa")
        self.base.config.reference_compile = False
        h = self.base.config.hidden_size
        self.span = nn.Linear(h, 2)
        self.ans = nn.Linear(h, 1)
        # The fire head is only built under --fire-head, and it is **built after span/ans**:
        # this way, when it is off by default, the random-number stream matches the old version
        # bit-for-bit (span/ans's initialization is unaffected).
        self.fire = nn.Linear(h, 1) if fire else None

    def forward(self, enc, last_idx):
        hs = self.base(**enc).last_hidden_state
        s, e = self.span(hs).unbind(-1)
        a = self.ans(hs[torch.arange(hs.size(0), device=hs.device),
                        last_idx]).squeeze(-1)
        return s, e, a

    def fire_logit(self, enc):
        """Fire head: plain sample text's [CLS] position (still at index 0 after left truncation) -> a scalar logit."""
        hs = self.base(**enc).last_hidden_state
        return self.fire(hs[:, 0]).squeeze(-1)


# ---------- data: sample text x params span ----------

def join_rows(data, params, split, limit=0, ro=None):
    """Streaming merge (the two files share the same order, params is a subsequence of the
    sample stack) -> (texts, instances).

    When ro is not None (--readonly-env): keep only samples whose ground truth is a
    read-only tool; the rest (including out-of-vocabulary ones) are dropped and counted;
    the labels used for the tally are collected before dropping, and the audit is run by
    the caller after the return.
    """
    texts, inst = [], []
    fp = open(params / f"{split}.jsonl")
    pr = fp.readline()
    for line in open(data / f"{split}.jsonl"):
        if not pr:
            break
        r = json.loads(line)
        p = json.loads(pr)
        if p["event"] != r["event"] or p["sent_idx"] != r["sent_idx"]:
            continue
        pr = fp.readline()
        if not p["params"]:
            continue
        if ro is not None:                     # non-read-only samples are dropped whole (counted in ro)
            ro["labels"].append(r["label"])
            if r["label"] not in ro["set"]:
                ro["dropped"] += 1
                continue
            ro["kept"] += 1
        ti = len(texts)
        texts.append(r["text"])
        for q in p["params"]:
            inst.append((ti, q["key"], q["value"], q["start"], q["end"],
                         q["found"], p["w"]))
    fp.close()
    if limit:
        rng = random.Random(SEED)
        rng.shuffle(inst)
        inst = inst[:limit]
    return texts, inst


def fire_rows(data, params, split, ro_set, limit=0):
    """Sample-level data stream for the fire head (--fire-head only): one line per sample
    in the main data, no read-only filtering.

    ready = the label is in the read-only set and every arg of the sample has found=true;
    for zero-arg events the found condition is vacuously true; samples that fail to join
    in params are treated as not-ready and counted
    (samples with non-empty args_named are counted separately -- those are the truly
    suspicious ones).
    Returns (rows=[(text, ready, w)], stats).
    """
    pmap = {}
    for line in open(params / f"{split}.jsonl"):
        p = json.loads(line)
        pmap[(p["event"], p["sent_idx"])] = p["params"]
    rows = []
    st = dict(n=0, n_ready=0, n_readonly=0, n_noparam=0,
              n_join_miss=0, n_join_miss_with_args=0)
    for line in open(data / f"{split}.jsonl"):
        r = json.loads(line)
        st["n"] += 1
        is_ro = r["label"] in ro_set
        st["n_readonly"] += is_ro
        ps = pmap.get((r["event"], r["sent_idx"]))
        if ps is None:
            st["n_join_miss"] += 1
            if r.get("args_named"):
                st["n_join_miss_with_args"] += 1
            ready = False
        else:
            st["n_noparam"] += not ps
            ready = is_ro and all(q["found"] for q in ps)
        st["n_ready"] += ready
        rows.append((r["text"], float(ready), float(r["w"])))
    n = max(st["n"], 1)
    st["frac_ready"] = round(st["n_ready"] / n, 6)
    st["frac_readonly"] = round(st["n_readonly"] / n, 6)
    st["frac_join_miss"] = round(st["n_join_miss"] / n, 6)
    if st["frac_join_miss"] > 0.01:
        print(f"[fire-head] warning: {split} has {st['n_join_miss']}/{st['n']} "
              f"({st['frac_join_miss']:.1%}) samples that don't join in the params file,"
              f" all treated as not-ready (of which args_named is non-empty for "
              f"{st['n_join_miss_with_args']})", flush=True)
    if limit:
        rng = random.Random(SEED)          # Independent RNG, does not touch the global random stream
        rng.shuffle(rows)
        rows = rows[:limit]
    return rows, st


class FireDS(Dataset):
    """Fire-head dataset: one instance per sample (not expanded per arg, so no duplicate weighting by nature)."""

    def __init__(self, rows):
        self.rows = rows

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        return self.rows[i]


def fire_collate(batch, tok, max_len):
    texts, ready, ws = zip(*batch)
    enc = tok(list(texts), truncation=True, max_length=max_len, padding=True,
              return_tensors="pt")
    return dict(enc=enc, ready=torch.tensor(ready, dtype=torch.float),
                w=torch.tensor(ws, dtype=torch.float))


class InstDS(Dataset):
    def __init__(self, texts, inst):
        self.texts, self.inst = texts, inst

    def __len__(self):
        return len(self.inst)

    def __getitem__(self, i):
        ti, key, val, s, e, found, w = self.inst[i]
        return self.texts[ti] + FIND + key, val, s, e, found, w


def char2tok(offs, start, end):
    """Character span -> minimal covering token span; returns (-1, -1) if out of range or truncated."""
    st = en = -1
    for i, (a, b) in enumerate(offs):
        if b <= a:                       # special tokens / padding
            continue
        if a <= start < b:
            st = i
        if a < end <= b:
            en = i
    return st, en


def span_ok(full, c0, c1, gs, ge):
    """Lenient correctness check: the predicted character span covers the ground truth, and any extra characters are only whitespace/punctuation."""
    if c0 < 0 or c0 > gs or c1 < ge:
        return False
    pad = full[c0:gs] + full[ge:c1]
    return not any(ch.isalnum() or ch == "_" for ch in pad)


def collate(batch, tok, max_len):
    strs, vals, gs, ge, founds, ws = zip(*batch)
    enc = tok(list(strs), truncation=True, max_length=max_len, padding=True,
              return_offsets_mapping=True, return_tensors="pt")
    offs = enc.pop("offset_mapping")
    valid = (offs[:, :, 1] > offs[:, :, 0]) & (enc["attention_mask"] > 0)
    last = valid.float().cumsum(1).argmax(1)          # last real token
    n = len(batch)
    st = torch.zeros(n, dtype=torch.long)
    en = torch.zeros(n, dtype=torch.long)
    ok = torch.zeros(n, dtype=torch.bool)             # answerable (and not cut off by left truncation)
    cut = 0
    for i in range(n):
        if not founds[i]:
            continue
        a, b = char2tok(offs[i].tolist(), gs[i], ge[i])
        if a < 0 or b < 0 or b < a:
            cut += 1
            continue
        st[i], en[i], ok[i] = a, b, True
    return dict(enc=enc, valid=valid, last=last, st=st, en=en, ok=ok,
                w=torch.tensor(ws, dtype=torch.float), strs=list(strs),
                vals=list(vals), gs=list(gs), ge=list(ge),
                found=list(founds), offs=offs, cut=cut)


def decode(s_lg, e_lg, valid, offs):
    """Vectorized decoding: returns the predicted character span (c0, c1) for each item."""
    neg = torch.finfo(s_lg.dtype).min
    s_lg = s_lg.masked_fill(~valid, neg)
    e_lg = e_lg.masked_fill(~valid, neg)
    w = min(MAX_SPAN_TOK, e_lg.size(1))
    pad = F.pad(e_lg, (0, w - 1), value=neg)
    win = pad.unfold(1, w, 1)                          # (B, L, w)
    wmax, warg = win.max(-1)
    bi = (s_lg + wmax).argmax(1)
    r = torch.arange(s_lg.size(0))
    bj = bi + warg[r, bi]
    return [(int(offs[i, bi[i], 0]), int(offs[i, bj[i], 1]))
            for i in range(s_lg.size(0))]


@torch.no_grad()
def evaluate(model, loader, dev, amp):
    model.eval()
    a_hit = sp_l = sp_s = tot_ok = w_tot = w_ft = 0.0
    for b in loader:
        enc = {k: v.to(dev) for k, v in b["enc"].items()}
        with amp():
            s_lg, e_lg, a_lg = model(enc, b["last"].to(dev))
        s_lg, e_lg = s_lg.float().cpu(), e_lg.float().cpu()
        ansp = (a_lg.float().cpu() > 0)
        spans = decode(s_lg, e_lg, b["valid"], b["offs"])
        for i in range(len(b["strs"])):
            wi = float(b["w"][i])
            pa = bool(ansp[i])
            a_hit += wi * (pa == bool(b["found"][i]))
            w_tot += wi
            if b["found"][i]:
                c0, c1 = spans[i]
                loose = pa and span_ok(b["strs"][i], c0, c1,
                                       b["gs"][i], b["ge"][i])
                strict = pa and b["strs"][i][c0:c1] == b["vals"][i]
                sp_l += wi * loose
                sp_s += wi * strict
                w_ft += wi
                tot_ok += wi * loose
            else:
                tot_ok += wi * (not pa)
    model.train()
    return (a_hit / max(w_tot, 1e-9), sp_l / max(w_ft, 1e-9),
            sp_s / max(w_ft, 1e-9), tot_ok / max(w_tot, 1e-9))


@torch.no_grad()
def evaluate_fire(model, loader, dev, amp):
    """val fire head: acc@0.5 (weighted by w, threshold 0.5 <=> logit>0) and positive/negative counts (unweighted)."""
    model.eval()
    hit = w_tot = 0.0
    n_pos = n_neg = 0
    for b in loader:
        enc = {k: v.to(dev) for k, v in b["enc"].items()}
        with amp():
            lg = model.fire_logit(enc)
        pred = lg.float().cpu() > 0
        y = b["ready"] > 0.5
        hit += float(((pred == y).float() * b["w"]).sum())
        w_tot += float(b["w"].sum())
        n_pos += int(y.sum())
        n_neg += int((~y).sum())
    model.train()
    return hit / max(w_tot, 1e-9), n_pos, n_neg


def load_extractor(run, device="cuda"):
    """Reused from eval_mbert_call: returns (model, tok, meta).

    Only builds the fire head for a run whose meta has "fire_head": true -- the bare
    state_dict is loaded strictly, so building too many or too few heads reports a
    missing/unexpected key right here, which works as a fuse.
    """
    run = Path(run)
    meta = json.loads((run / "best" / "meta.json").read_text())
    tok = AutoTokenizer.from_pretrained(run / "best")
    tok.truncation_side = "left"
    model = Extractor(meta["base"], fire=bool(meta.get("fire_head")))
    model.load_state_dict(torch.load(run / "best" / "model.pt",
                                     map_location="cpu"))
    return model.to(device).eval(), tok, meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default="appworld",
                    choices=["tales", "appworld", "bfcl", "alfworld"],
                    help="log label only (the data path is given directly by --data)")
    ap.add_argument("--data", required=True,
                    help="data dir <data_out> (contains train/val.jsonl)")
    ap.add_argument("--params", default=None,
                    help="arg-span label dir (default <data>/params)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-len", type=int, default=4096)
    ap.add_argument("--bs", type=int, default=8)
    ap.add_argument("--accum", type=int, default=4)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--smoke", action="store_true",
                    help="500 training instances/200 eval instances/1 epoch, for pipeline verification")
    ap.add_argument("--max-inst", type=int, default=0,
                    help="cap the instance count further (for CPU debugging, 0 = unlimited)")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--readonly-env", default=None,
                    choices=list(readonly_map.READONLY_ENVS),
                    help="read-only tool mode: train only on samples whose ground truth is a read-only tool (off by default = the old settings)")
    ap.add_argument("--grad-ckpt", action="store_true",
                    help="gradient checkpointing: mathematically neutral, only trades for GPU memory (fire's dual forward pass can blow past a 48G card at long-sequence settings)")
    ap.add_argument("--fire-head", action="store_true",
                    help="additionally train a sample-level fire head (should we speculate right now);"
                         "must be passed together with --readonly-env, off by default = behavior unchanged")
    ap.add_argument("--force", action="store_true",
                    help="allow training again in an --out dir that was already trained in (refused by default to keep outputs apart)")
    args = ap.parse_args()

    if args.fire_head and not args.readonly_env:
        raise SystemExit(
            "--fire-head must be passed together with --readonly-env: the definition of the fire"
            " label ready depends on that environment's read-only ground-truth table (ready = read-only and all args found),"
            " with no environment the label can't be computed.")

    torch.manual_seed(SEED)
    random.seed(SEED)
    data = Path(args.data)
    params = Path(args.params) if args.params else data / "params"
    out = Path(args.out)
    if (out / "train_log.jsonl").exists() and not args.force:
        raise SystemExit(
            f"{out} already has a train_log.jsonl -- this dir has already been trained once; training again would mix"
            " both runs' outputs into the same best/ with no way to tell them apart (audit B7). Use a different --out, or confirm the overwrite and pass --force.")
    out.mkdir(parents=True, exist_ok=True)
    dev = args.device
    amp = ((lambda: torch.autocast("cuda", dtype=torch.bfloat16))
           if dev.startswith("cuda") else contextlib.nullcontext)

    tok = AutoTokenizer.from_pretrained(MODEL)
    tok.truncation_side = "left"
    model = Extractor(fire=args.fire_head).to(dev)
    if args.grad_ckpt:
        model.base.gradient_checkpointing_enable()
    model.train()

    lim_tr, lim_ev = (500, 200) if args.smoke else (0, 0)
    if args.max_inst:
        lim_tr = min(lim_tr or args.max_inst, args.max_inst)
        lim_ev = min(lim_ev or args.max_inst, args.max_inst)
    epochs = 1 if args.smoke else args.epochs
    ro_tr = ro_ev = None
    if args.readonly_env:
        ro_set = readonly_map.load_readonly_set(args.readonly_env)
        ro_table = readonly_map.load_table(args.readonly_env)
        ro_tr = dict(set=ro_set, labels=[], kept=0, dropped=0)
        ro_ev = dict(set=ro_set, labels=[], kept=0, dropped=0)
    tr = InstDS(*join_rows(data, params, "train", lim_tr, ro_tr))
    ev = InstDS(*join_rows(data, params, "val", lim_ev, ro_ev))
    fire_st = {}
    fire_tr = fire_ev = None
    if args.fire_head:
        # Fire-head sample-level stream: non-read-only samples come back into the data stream as negatives here, and do not become span instances
        ftr, fire_st["train"] = fire_rows(data, params, "train", ro_set, lim_tr)
        fev, fire_st["val"] = fire_rows(data, params, "val", ro_set, lim_ev)
        fire_tr, fire_ev = FireDS(ftr), FireDS(fev)
    if args.readonly_env:
        au_tr = readonly_map.audit(ro_tr["labels"], ro_table, where="mext/train")
        au_ev = readonly_map.audit(ro_ev["labels"], ro_table, where="mext/val")
        ro_out = dict(
            readonly_env=args.readonly_env,
            table=str(readonly_map.table_path(args.readonly_env)),
            train=au_tr, val=au_ev,
            kept=dict(train=ro_tr["kept"], val=ro_ev["kept"]),
            dropped=dict(train=ro_tr["dropped"], val=ro_ev["dropped"]))
        if args.fire_head:
            ro_out["fire_head"] = fire_st
        (out / "READONLY.json").write_text(json.dumps(
            ro_out, ensure_ascii=False, indent=1))
    mk = lambda ds, sh: DataLoader(
        ds, batch_size=args.bs, shuffle=sh, num_workers=2,
        collate_fn=lambda b: collate(b, tok, args.max_len))
    tr_dl, ev_dl = mk(tr, True), mk(ev, False)
    fire_tr_dl = fire_ev_dl = fire_it = None
    if args.fire_head:
        mkf = lambda ds, sh: DataLoader(
            ds, batch_size=args.bs, shuffle=sh, num_workers=2,
            collate_fn=lambda b: fire_collate(b, tok, args.max_len))
        fire_tr_dl, fire_ev_dl = mkf(fire_tr, True), mkf(fire_ev, False)

        def cycle(dl):                     # fire stream and span stream differ in length, cycle through
            while True:
                for x in dl:
                    yield x
        fire_it = cycle(fire_tr_dl)

    steps = math.ceil(len(tr_dl) / args.accum) * epochs
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    sch = get_linear_schedule_with_warmup(opt, int(steps * 0.05), steps)
    ce = nn.CrossEntropyLoss(reduction="none")
    bce = nn.BCEWithLogitsLoss(reduction="none")

    logf = open(out / "train_log.jsonl", "a")

    def log(**kw):
        kw["t"] = round(time.time(), 1)
        logf.write(json.dumps(kw) + "\n")
        logf.flush()
        print(kw, flush=True)

    log(event="start", env=args.env, n_train=len(tr), n_eval=len(ev),
        steps=steps, smoke=args.smoke, max_len=args.max_len, device=dev,
        readonly_env=args.readonly_env,
        **(dict(fire_head=True, n_fire_train=len(fire_tr),
                n_fire_eval=len(fire_ev),
                fire_ready_train=fire_st["train"]["frac_ready"],
                fire_ready_val=fire_st["val"]["frac_ready"])
           if args.fire_head else {}))
    heartbeat.emit(0, steps, "step")

    best, gstep, cutsum = -1.0, 0, 0
    neg = torch.finfo(torch.float32).min
    for ep in range(epochs):
        t0, run = time.time(), 0.0
        for i, b in enumerate(tr_dl):
            cutsum += b["cut"]
            enc = {k: v.to(dev) for k, v in b["enc"].items()}
            with amp():
                s_lg, e_lg, a_lg = model(enc, b["last"].to(dev))
            m = b["valid"].to(dev)
            s_lg = s_lg.float().masked_fill(~m, neg)
            e_lg = e_lg.float().masked_fill(~m, neg)
            wd, okd = b["w"].to(dev), b["ok"].to(dev)
            la = (bce(a_lg.float(), okd.float()) * wd).sum() / wd.sum()
            if okd.any():
                wf = wd[okd]
                ls = ((ce(s_lg[okd], b["st"].to(dev)[okd])
                       + ce(e_lg[okd], b["en"].to(dev)[okd]))
                      * wf).sum() / wf.sum()
            else:
                ls = torch.zeros((), device=dev)
            loss = la + ls
            if args.fire_head:
                # Fire head forms its own batch: input is plain text, label is ready, weighted by w, lambda=1
                fb = next(fire_it)
                fenc = {k: v.to(dev) for k, v in fb["enc"].items()}
                with amp():
                    flg = model.fire_logit(fenc)
                fwd = fb["w"].to(dev)
                lf = ((bce(flg.float(), fb["ready"].to(dev)) * fwd).sum()
                      / fwd.sum())
                loss = loss + lf
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
                        ips=round((i + 1) * args.bs / (time.time() - t0), 1))
                    heartbeat.emit(gstep, steps, "step",
                                   loss=round(run / (50 * args.accum), 4))
                    run = 0.0
        aacc, sl, ss, tacc = evaluate(model, ev_dl, dev, amp)
        fkw = {}
        if args.fire_head:
            facc, fpos, fneg = evaluate_fire(model, fire_ev_dl, dev, amp)
            fkw = dict(fire_acc=round(facc, 4), fire_n_pos=fpos,
                       fire_n_neg=fneg)
        log(event="eval", ep=ep, calA_ans_acc=round(aacc, 4),
            calA_span_loose=round(sl, 4), calA_span_strict=round(ss, 4),
            calA_param_acc=round(tacc, 4), truncated_spans=cutsum, **fkw)
        if tacc > best:
            best = tacc
            (out / "best").mkdir(exist_ok=True)
            torch.save(model.state_dict(), out / "best" / "model.pt")
            tok.save_pretrained(out / "best")
            meta = dict(env=args.env, base=MODEL, max_len=args.max_len,
                        find=FIND, max_span_tok=MAX_SPAN_TOK, seed=SEED,
                        calA_param_acc=round(best, 4))
            if args.readonly_env:
                meta["readonly_env"] = args.readonly_env
            if args.fire_head:
                meta["fire_head"] = True
            (out / "best" / "meta.json").write_text(json.dumps(
                meta, ensure_ascii=False))
            log(event="save_best", ep=ep, acc=round(best, 4))
    log(event="done", best_calA_param_acc=round(best, 4),
        truncated_spans=cutsum)
    heartbeat.emit(gstep, steps, "step", status="done")


if __name__ == "__main__":
    main()
