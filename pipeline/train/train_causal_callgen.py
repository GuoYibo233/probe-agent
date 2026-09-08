"""Causal call-generation training (new pipeline, cgen cell): fine-tunes Qwen3-0.6B-Base to "read the prompt and write out the whole call".

Division of labor with ctool (train_causal_tool.py): ctool only outputs the tool
kind, cgen writes the tool name plus all parameters in one shot
(`apis.spotify.login(username=x, password=y)`).

- Input: <data_out>/{train,val}.jsonl, each line takes the three fields text /
  label_call / w; one sample = one training instance
- Backbone: --base qwen -> Qwen3-0.6B-Base (default) / qwen17 -> 1.7B / qwen4 -> 4B
- Concatenation: input string = text + CALL_SEP("\\n[CALL] "), target string = label_call + eos
- Guard against left truncation eating the target: tokenize the target first to
  get tgt_ids (no truncation); instances over MAX_TGT_TOK are dropped whole and
  counted; then left-truncate the input string to max_length = --max-len -
  len(tgt_ids), and after concatenation labels mask the prompt segment to -100
  (right padding within the batch, pad positions also -100)
- Loss: per-instance target-segment mean CE (ce_i), batch loss = Σ(w_i·ce_i)/Σw_i
- Evaluation: every epoch, val's full weighted masked-CE (val_ce, the sole
  criterion for picking best, lower is better) + a fixed-seed draw of GEN_N
  greedy generations reported as val_exact_call (logged only, not used to pick best)
- Outputs: <out>/best/ (HF weights + tokenizer + meta.json) + train_log.jsonl
- LoRA: `--lora` swaps the backbone for LoRA training (the fire head, if present,
  still trains full-parameter as usual); before saving best it first runs
  merge_and_unload to fold the adapter back into the backbone, so best/'s files
  are structurally identical item by item to a full-parameter save, and it
  loads back into eval_causal_call.py with zero changes; meta.json gets one
  extra "lora" block recording the hyperparameters. When --lora is not passed,
  the script never touches peft (all peft imports live in the --lora branch),
  and behavior matches before this set of flags was added; see lora_util.py for
  details.

Fire head (`--fire-head`, must be passed together with --readonly-env; the
default, not passing it, matches the old version's behavior):
- A sample-level binary classification head, backbone's last-layer hidden state
  -> Linear(h,1), that learns "should this fire speculation right now". The
  position it reads is **the prompt's last position** (the last -100 position
  in labels, i.e. the last token of CALL_SEP): the hidden state at this
  position can only see text+CALL_SEP, matching what is available when firing
  live; reading the last position of the whole string would feed the target
  call string itself into the fire head, leaking the answer directly.
- Fire label ready = the label is in the read-only set AND every parameter of
  this sample has found=true
  (a zero-parameter event has an empty-true found condition; a param that
  cannot be joined in params counts as not-ready and is counted)
- Non-read-only samples are no longer dropped whole; instead they go back into
  the data stream as fire-head negatives: their LM labels are all -100,
  they produce no LM gradient, and do not enter val_ce's numerator or denominator
- Loss = the original masked-CE + lambda * fire BCE (lambda=1); when a batch is
  entirely non-read-only samples, the LM term's denominator is zero,
  and that whole term is skipped (no NaN)
- The criterion for picking best is unchanged (val masked-CE, computed only on
  read-only samples); the fire head is saved to
  best/fire_head.pt, and meta.json gets "fire_head": true added

Usage:
  # smoke (500 training instances / 200 eval instances / 1 epoch)
  cprobe-env/bin/python pipeline/train/train_causal_callgen.py \
    --data pipeline/data/aw_official_v1/q35 --out pipeline/runs/c1_q35_cgen --smoke
  # full run
  cprobe-env/bin/python pipeline/train/train_causal_callgen.py \
    --data pipeline/data/aw_official_v1/q35 --out pipeline/runs/c1_q35_cgen
"""

import argparse
import json
import math
import random
import time
from pathlib import Path

import torch
import torch.nn.functional as F
import transformers
_TV = tuple(int(x) for x in transformers.__version__.split(".")[:2])
if _TV < (5, 14):
    raise SystemExit(f"cprobe line requires transformers>=5.14, current "
                     f"{transformers.__version__} -- wrong interpreter?"
                     "always go through run.py's tasks (train-ctool/train-cgen).")
from torch.utils.data import DataLoader, Dataset
from transformers import (AutoModelForCausalLM, AutoTokenizer,
                          get_linear_schedule_with_warmup)

import lora_util
import readonly_map

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / "ops"))
import heartbeat


# Three backbone tiers (since 2026-08-21 the causal line expanded from one tier to
# three, same style as train_causal_tool.MODELS).
# --base defaults to qwen; behavior when not passed is byte-identical to before
# this table was added.
MODELS = {
    "qwen":   "/net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-0.6B-Base",
    "qwen17": "/net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-1.7B-Base",
    "qwen4":  "/net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-4B-Base",
}
SEED = 42                  # since np821, switched to the seed family (42/67/4267/6742)'s first value; old value 20260729 only applies when reproducing old data
FULL_LR = 1e-5             # learning rate for full-parameter fine-tuning (the --lr default when --lora is not passed)
CALL_SEP = "\n[CALL] "
MAX_TGT_TOK = 160          # target-string token cap; instances over this are dropped whole
MAX_GEN_TOK = 96           # max_new_tokens for eval generation
GEN_N = 200                # how many to draw each epoch for greedy generation


# ---------------------------------------------------------------- data

def fire_pmap(params, split):
    """{(event, sent_idx): params} -- the found information the fire label needs."""
    pmap = {}
    for line in open(params / f"{split}.jsonl"):
        p = json.loads(line)
        pmap[(p["event"], p["sent_idx"])] = p["params"]
    return pmap


def fire_stats():
    return dict(n=0, n_ready=0, n_readonly=0, n_noparam=0,
                n_join_miss=0, n_join_miss_with_args=0)


def fire_finish(st, where):
    n = max(st["n"], 1)
    st["frac_ready"] = round(st["n_ready"] / n, 6)
    st["frac_readonly"] = round(st["n_readonly"] / n, 6)
    st["frac_join_miss"] = round(st["n_join_miss"] / n, 6)
    if st["frac_join_miss"] > 0.01:
        print(f"[fire-head] warning: {where} has {st['n_join_miss']}/{st['n']} "
              f"({st['frac_join_miss']:.1%}) samples that can't be joined in the params file, "
              f"all treated as not-ready (of which args_named is non-empty for "
              f"{st['n_join_miss_with_args']} of them)", flush=True)
    return st


class CallDS(Dataset):
    """One sample is one instance; construction tokenizes the target string first,
overlong ones are dropped whole and counted.

    When fire is not None (--fire-head), rows split into two kinds: read-only
    samples stay as before (they have an LM target); non-read-only samples only
    serve as fire-head negatives (tgt empty, has_lm=False, LM labels all -100).
    Row structure is a fixed six-tuple (text, tgt, w, label_call, ready, has_lm);
    with the default off, ready is always 0.0 and has_lm is always True,
    matching the old version's values bit for bit.
    """

    def __init__(self, path, tok, limit=0, max_tgt=MAX_TGT_TOK, ro=None,
                 fire=None):
        self.rows, self.dropped = [], 0
        eos = tok.eos_token_id
        for line in open(path):
            r = json.loads(line)
            is_ro = True
            if ro is not None:                 # non-read-only samples are dropped whole (counted in ro)
                ro["labels"].append(r["label"])
                is_ro = r["label"] in ro["set"]
                if not is_ro:
                    ro["dropped"] += 1
                    if fire is None:
                        continue
                else:
                    ro["kept"] += 1
            ready = 0.0
            if fire is not None:
                st = fire["stats"]
                st["n"] += 1
                st["n_readonly"] += is_ro
                ps = fire["pmap"].get((r["event"], r["sent_idx"]))
                if ps is None:
                    st["n_join_miss"] += 1
                    if r.get("args_named"):
                        st["n_join_miss_with_args"] += 1
                else:
                    st["n_noparam"] += not ps
                    ready = float(is_ro and all(q["found"] for q in ps))
                st["n_ready"] += int(ready)
                if not is_ro:
                    # only serves as a fire-head negative: no LM target given, and not subject to the max_tgt drop
                    self.rows.append((r["text"], [], float(r["w"]),
                                      r["label_call"], ready, False))
                    continue
            tgt = tok(r["label_call"], add_special_tokens=False)["input_ids"]
            tgt = tgt + [eos]
            if len(tgt) > max_tgt:
                self.dropped += 1
                continue
            self.rows.append((r["text"], tgt, float(r["w"]), r["label_call"],
                              ready, True))
        if limit:
            rng = random.Random(SEED)
            rng.shuffle(self.rows)
            self.rows = self.rows[:limit]

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        return self.rows[i]


def collate(batch, tok, max_len):
    """Left-truncate the input + right-pad; labels mask out the prompt segment and pad positions.

    Also returns ready (the fire label), lm (whether this row enters the LM
    loss), and plast (the prompt's last-position index, where the fire head
    reads its hidden state). With the default off, ready is all 0 and lm is
    all 1, and no numeric value is affected.
    """
    ids, labs, ws, ready, lm, plast = [], [], [], [], [], []
    for text, tgt, w, _call, rdy, has_lm in batch:
        keep = max(max_len - len(tgt), 1)
        prompt = tok(text + CALL_SEP, truncation=True, max_length=keep,
                     add_special_tokens=False)["input_ids"]
        ids.append(prompt + tgt)
        labs.append([-100] * len(prompt) + tgt)
        ws.append(w)
        ready.append(rdy)
        lm.append(float(has_lm))
        plast.append(max(len(prompt) - 1, 0))
    n, L = len(ids), max(len(x) for x in ids)
    pad = tok.pad_token_id
    input_ids = torch.full((n, L), pad, dtype=torch.long)
    attn = torch.zeros((n, L), dtype=torch.long)
    labels = torch.full((n, L), -100, dtype=torch.long)
    for i, (x, y) in enumerate(zip(ids, labs)):
        input_ids[i, :len(x)] = torch.tensor(x, dtype=torch.long)
        attn[i, :len(x)] = 1
        labels[i, :len(y)] = torch.tensor(y, dtype=torch.long)
    return (dict(input_ids=input_ids, attention_mask=attn), labels,
            torch.tensor(ws, dtype=torch.float),
            torch.tensor(ready, dtype=torch.float),
            torch.tensor(lm, dtype=torch.float),
            torch.tensor(plast, dtype=torch.long))


# ---------------------------------------------------------------- model

def build(dev, base="qwen", attn_impl=None, path=None):
    """Tokenizer construction copies train_causal_probe.build() verbatim: pad=eos / left-truncate / right-pad.

    Two keyword arguments added by ticket
    `.scratch/kvshare-train/issues/03-share-trainer.md` (spec 3.4, decision 6);
    when both are None, behavior is byte-identical to before this change:
    - `attn_impl`: when not None, passed to `from_pretrained` as
      `attn_implementation` (the new trainer `train_causal_share.py` uses this
      to pin `sdpa`).
    - `path`: when not None, load the model and tokenizer directly from this
      directory, skipping the `MODELS[base]` lookup (used by the new trainer's
      section 12 small-model tests).
    """
    model_path = MODELS[base] if path is None else path
    tok = AutoTokenizer.from_pretrained(model_path)
    if tok.pad_token_id is None:                      # copied verbatim from check_causal_candidates
        tok.pad_token = tok.eos_token
    tok.truncation_side = "left"                      # keep the thinking tail
    tok.padding_side = "right"                        # the target segment sits entirely on real tokens
    torch.manual_seed(SEED)
    extra = {} if attn_impl is None else dict(attn_implementation=attn_impl)
    model = AutoModelForCausalLM.from_pretrained(model_path, dtype=torch.float32,
                                                 **extra)
    if model.config.get_text_config().pad_token_id is None:
        model.config.get_text_config().pad_token_id = tok.pad_token_id
    return tok, model.to(dev), model_path


def inst_ce(model, enc, labels, dev, fire=None, plast=None):
    """Per-instance mean CE over the target segment. Returns a [B] float32 tensor.

    When fire is not None, also take an extra copy of the last-layer hidden state and run it
    through the fire head at plast (the last position of the prompt), returning
    (ce, fire_logit). The fire=None path is identical, byte for byte, to the old version.
    """
    kw = {} if fire is None else dict(output_hidden_states=True)
    out = model(input_ids=enc["input_ids"], attention_mask=enc["attention_mask"],
                use_cache=False, **kw)
    lg = out.logits[:, :-1]                           # predict the next token
    tg = labels[:, 1:].to(dev)
    m = tg != -100
    ce = F.cross_entropy(lg[m].float(), tg[m], reduction="none")  # take only the target positions
    b = tg.size(0)
    inst = torch.arange(b, device=dev).unsqueeze(1).expand_as(tg)[m]
    ssum = torch.zeros(b, device=dev, dtype=torch.float32)
    ssum = ssum.index_add(0, inst, ce)
    ice = ssum / m.sum(1).clamp(min=1).float()
    if fire is None:
        return ice
    h = out.hidden_states[-1]                         # [B, L, hidden]
    hp = h[torch.arange(b, device=h.device), plast.to(h.device)]
    return ice, fire(hp.float()).squeeze(-1)


# ---------------------------------------------------------------- eval

@torch.no_grad()
def eval_ce(model, loader, dev, amp, fire=None):
    """Full-val weighted masked-CE (same accounting as the training loss).

    When fire is not None: both the numerator and denominator of the CE only count rows with
    an LM target (= read-only samples), matching the accounting when --readonly-env is on by
    itself; also returns fire-head acc@0.5 (weighted by w) and the positive/negative example
    counts.
    """
    model.eval()
    s = w_tot = 0.0
    hit = fw_tot = 0.0
    n_pos = n_neg = 0
    for enc, labels, w, ready, lm, plast in loader:
        enc = {k: v.to(dev) for k, v in enc.items()}
        with torch.autocast("cuda", dtype=torch.bfloat16, enabled=amp):
            if fire is None:
                ce = inst_ce(model, enc, labels, dev)
            else:
                ce, flg = inst_ce(model, enc, labels, dev, fire, plast)
        wd = (w * lm if fire is not None else w).to(dev)
        s += (ce.float() * wd).sum().item()
        w_tot += wd.sum().item()
        if fire is not None:
            pred = flg.float().cpu() > 0
            y = ready > 0.5
            hit += float(((pred == y).float() * w).sum())
            fw_tot += float(w.sum())
            n_pos += int(y.sum())
            n_neg += int((~y).sum())
    model.train()
    if w_tot <= 0:
        raise SystemExit(
            "val has not a single LM target position (weighted denominator w_tot=0) -- continuing would give val_ce=0.0, "
            "saved as best every epoch, making the run look perfect. Something is wrong with the data or filter settings, hard stop.")
    vce = s / w_tot
    if fire is None:
        return vce
    return vce, dict(fire_acc=round(hit / max(fw_tot, 1e-9), 4),
                     fire_n_pos=n_pos, fire_n_neg=n_neg)


@torch.no_grad()
def eval_gen(model, tok, rows, dev, amp, max_len, bs):
    """Fixed-seed sampled greedy generation: whole-string hit rate (stops at \\n or eos)."""
    model.eval()
    prev_side, prev_cache = tok.padding_side, model.config.use_cache
    tok.padding_side = "left"                         # generation requires left padding
    model.config.use_cache = True
    hit = 0
    for i in range(0, len(rows), bs):
        chunk = rows[i:i + bs]
        enc = tok([r[0] + CALL_SEP for r in chunk], truncation=True,
                  max_length=max(max_len - MAX_GEN_TOK, 1), padding=True,
                  add_special_tokens=False, return_tensors="pt").to(dev)
        with torch.autocast("cuda", dtype=torch.bfloat16, enabled=amp):
            out = model.generate(**enc, do_sample=False,
                                 max_new_tokens=MAX_GEN_TOK,
                                 eos_token_id=tok.eos_token_id,
                                 pad_token_id=tok.pad_token_id)
        gen = tok.batch_decode(out[:, enc["input_ids"].shape[1]:],
                               skip_special_tokens=True)
        for g, r in zip(gen, chunk):
            hit += (g.split("\n")[0].strip() == r[3])
    tok.padding_side, model.config.use_cache = prev_side, prev_cache
    model.train()
    return hit / max(len(rows), 1)


# ---------------------------------------------------------------- main flow

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="qwen", choices=sorted(MODELS),
                    help="base model, three tiers: qwen=0.6B (default, same as old behavior)/"
                         "qwen17=1.7B/qwen4=4B")
    ap.add_argument("--env", default="appworld",
                    choices=["tales", "appworld", "bfcl", "alfworld"],
                    help="log label only (the data path is given directly by --data)")
    ap.add_argument("--data", required=True,
                    help="data dir <data_out> (contains train/val.jsonl)")
    ap.add_argument("--out", required=True, help="output dir (required; guards against overwriting old outputs)")
    ap.add_argument("--max-len", type=int, default=4096)
    ap.add_argument("--bs", type=int, default=4)
    ap.add_argument("--accum", type=int, default=8)
    ap.add_argument("--lr", type=float, default=None,
                    help=f"learning rate (default {FULL_LR}; when --lora is on it defaults to --lora-lr instead, "
                         "if given explicitly here that value takes precedence)")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--smoke", action="store_true",
                    help="500 training instances/200 eval instances/1 epoch, for verifying the pipeline")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--grad-ckpt", action="store_true",
                    help="turn on gradient checkpointing on the base model to save GPU memory (works in both full-parameter and --lora modes; "
                         "also turns off use_cache, and under LoRA additionally ensures the input requires grad)")
    ap.add_argument("--gen-bs", type=int, default=8, help="batch size for generation eval")
    ap.add_argument("--max-inst", type=int, default=0,
                    help="for debugging: further cap the instance count (0 = no cap)")
    ap.add_argument("--readonly-env", default=None,
                    choices=list(readonly_map.READONLY_ENVS),
                    help="readonly-tool mode: train only on samples whose ground truth is a readonly tool (off by default = old settings)")
    ap.add_argument("--params", default=None,
                    help="directory for parameter-range labels (default <data>/params); only used "
                         "by --fire-head -- the fire label needs to read found")
    ap.add_argument("--fire-head", action="store_true",
                    help="also learn a sample-level fire head (should speculation fire right now); "
                         "must be passed together with --readonly-env, off by default = behavior unchanged")
    ap.add_argument("--force", action="store_true",
                    help="allow training again in an --out dir that was already trained in (refused by default to keep outputs apart)")
    lora_util.add_args(ap)
    args = ap.parse_args()
    lr = lora_util.resolve_lr(args, FULL_LR)

    if args.fire_head and not args.readonly_env:
        raise SystemExit(
            "--fire-head must be passed together with --readonly-env: the definition of a ready fire label "
            "depends on that environment's readonly ground-truth table (ready = readonly and all params found), "
            "without an environment the label can't be computed.")

    torch.manual_seed(SEED)
    random.seed(SEED)
    data = Path(args.data)
    params = Path(args.params) if args.params else data / "params"
    out = Path(args.out)
    if (out / "train_log.jsonl").exists() and not args.force:
        raise SystemExit(
            f"{out} already has a train_log.jsonl -- this directory has been trained once, training again would mix "
            "both runs' outputs into the same best/ with no way to attribute them (audit B7). Use a different --out, or confirm the overwrite and add --force.")
    out.mkdir(parents=True, exist_ok=True)
    dev = args.device
    amp = dev.startswith("cuda")

    tok, model, path = build(dev, args.base)

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
    fire_tr = fire_ev = None
    if args.fire_head:
        fire_tr = dict(pmap=fire_pmap(params, "train"), stats=fire_stats())
        fire_ev = dict(pmap=fire_pmap(params, "val"), stats=fire_stats())
    tr = CallDS(data / "train.jsonl", tok, lim_tr, ro=ro_tr, fire=fire_tr)
    ev = CallDS(data / "val.jsonl", tok, lim_ev, ro=ro_ev, fire=fire_ev)
    fire_st = {}
    if args.fire_head:
        fire_st = dict(train=fire_finish(fire_tr["stats"], "cgen/train"),
                       val=fire_finish(fire_ev["stats"], "cgen/val"))
    if args.readonly_env:
        au_tr = readonly_map.audit(ro_tr["labels"], ro_table, where="cgen/train")
        au_ev = readonly_map.audit(ro_ev["labels"], ro_table, where="cgen/val")
        ro_out = dict(
            readonly_env=args.readonly_env,
            table=str(readonly_map.table_path(args.readonly_env)),
            train=au_tr, val=au_ev,
            kept=dict(train=ro_tr["kept"], val=ro_ev["kept"]),
            dropped=dict(train=ro_tr["dropped"], val=ro_ev["dropped"]))
        if args.fire_head:
            # In fire mode, "dropped" changes meaning: it no longer means "dropped from the dataset", it
            # means "excluded from the LM loss"
            ro_out["dropped_semantics"] = "in fire-head mode = counts only as a negative for the fire head, not into the LM loss"
            ro_out["fire_head"] = fire_st
        (out / "READONLY.json").write_text(json.dumps(
            ro_out, ensure_ascii=False, indent=1))
    # Fuse: hard-stop if val loads 0 rows. An empty val will not crash training (SequentialSampler
    # does not block on empty), it will just make val_ce always 0, save best every epoch, and make
    # the run look perfect.
    if not len(ev):
        raise SystemExit(
            f"{data / 'val.jsonl'} loaded to 0 val rows (dropped={ev.dropped}"
            + (f", readonly_dropped={ro_ev['dropped']}" if ro_ev else "")
            + ") -- the metric for picking best has no denominator, hard stop.")
    mk = lambda ds, sh: DataLoader(
        ds, batch_size=args.bs, shuffle=sh, num_workers=2,
        collate_fn=lambda b: collate(b, tok, args.max_len))
    tr_dl, ev_dl = mk(tr, True), mk(ev, False)
    # Generation eval only runs on rows with an LM target (= read-only samples), the same source as
    # when --readonly-env is on by itself
    gen_rows = [r for r in ev.rows if r[5]]
    random.Random(SEED).shuffle(gen_rows)
    gen_rows = gen_rows[:GEN_N]

    # LoRA: swap the backbone in place for LoRA training. The fire head (if present) is a newly
    # initialized linear head, trained fully as usual, going into the optimizer along with the
    # adapter.
    lora_wrap = lora_util.wrap(model, args) if args.lora else None
    if args.grad_ckpt:
        model.gradient_checkpointing_enable()
        model.config.use_cache = False
        if args.lora:
            lora_util.prepare_grad_ckpt(model)
    model.train()

    fire = None
    if args.fire_head:
        h = model.config.get_text_config().hidden_size
        fire = torch.nn.Linear(h, 1).to(dev)          # built after the backbone
    bcef = torch.nn.BCEWithLogitsLoss(reduction="none")
    steps = math.ceil(len(tr_dl) / args.accum) * epochs
    pars = (lora_util.opt_params(model.parameters(), args.lora)
            + (list(fire.parameters()) if fire else []))
    opt = torch.optim.AdamW(pars, lr=lr, weight_decay=0.01)
    sch = get_linear_schedule_with_warmup(opt, int(steps * 0.05), steps)

    logf = open(out / "train_log.jsonl", "a")

    def log(**kw):
        kw["t"] = round(time.time(), 1)
        logf.write(json.dumps(kw) + "\n")
        logf.flush()
        print(kw, flush=True)

    log(event="start", base_path=path, env=args.env, n_train=len(tr),
        n_eval=len(ev), n_gen=len(gen_rows), steps=steps, smoke=args.smoke,
        max_len=args.max_len, max_tgt_tok=MAX_TGT_TOK, seed=SEED,
        dropped_train=tr.dropped, dropped_eval=ev.dropped, device=dev,
        readonly_env=args.readonly_env,
        **(dict(fire_head=True, n_gen_lm=len(gen_rows),
                fire_ready_train=fire_st["train"]["frac_ready"],
                fire_ready_val=fire_st["val"]["frac_ready"])
           if args.fire_head else {}),
        **(dict(lora=lora_util.meta_block(args, lr)) if args.lora else {}))
    heartbeat.emit(0, steps, "step")

    best = float("inf")
    gstep = 0
    for ep in range(epochs):
        t0, run = time.time(), 0.0
        for i, (enc, labels, w, ready, lm, plast) in enumerate(tr_dl):
            enc = {k: v.to(dev) for k, v in enc.items()}
            with torch.autocast("cuda", dtype=torch.bfloat16, enabled=amp):
                if fire is None:
                    ce = inst_ce(model, enc, labels, dev)
                else:
                    ce, flg = inst_ce(model, enc, labels, dev, fire, plast)
            wd = w.to(dev)
            if fire is None:
                loss = (ce.float() * wd).sum() / wd.sum()
            else:
                wl = wd * lm.to(dev)          # only read-only samples enter the LM term
                ws = wl.sum()
                # The whole batch is non-read-only samples: the LM term's denominator is zero, so skip the
                # whole term (not a divide-by-zero)
                loss = ((ce.float() * wl).sum() / ws if float(ws) > 0
                        else torch.zeros((), device=dev))
                loss = loss + ((bcef(flg.float(), ready.to(dev)) * wd).sum()
                               / wd.sum())
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
                        ips=round((i + 1) * args.bs / (time.time() - t0), 2))
                    heartbeat.emit(gstep, steps, "step",
                                   loss=round(run / (50 * args.accum), 4))
                    run = 0.0
        fkw = {}
        if fire is None:
            vce = eval_ce(model, ev_dl, dev, amp)
        else:
            vce, fkw = eval_ce(model, ev_dl, dev, amp, fire)
        vex = eval_gen(model, tok, gen_rows, dev, amp, args.max_len,
                       args.gen_bs)
        log(event="eval", ep=ep, val_ce=round(vce, 4),
            val_exact_call=round(vex, 4), **fkw)
        if vce < best:
            best = vce
            (out / "best").mkdir(parents=True, exist_ok=True)
            if lora_wrap is None:
                model.save_pretrained(out / "best")
            else:
                # Merge the adapter back into the backbone before saving: best/ is item-for-item isomorphic with
                # a full-parameter save, zero changes needed on the eval side
                lora_util.save_merged(lora_wrap, out / "best", dev)
            tok.save_pretrained(out / "best")
            meta = dict(
                base=args.base, base_path=path, data=str(data),
                max_len=args.max_len, seed=SEED, epoch=ep, call_sep=CALL_SEP,
                transformers=transformers.__version__)
            if args.readonly_env:
                meta["readonly_env"] = args.readonly_env
            if args.lora:
                meta["lora"] = lora_util.meta_block(args, lr)
            if args.grad_ckpt:
                meta["grad_ckpt"] = True
            if fire is not None:
                meta["fire_head"] = True
                torch.save(fire.state_dict(), out / "best" / "fire_head.pt")
            (out / "best" / "meta.json").write_text(json.dumps(meta, indent=1))
            log(event="save_best", ep=ep, val_ce=round(best, 4))
    log(event="done", best_val_ce=round(best, 4))
    heartbeat.emit(gstep, steps, "step", status="done")


if __name__ == "__main__":
    main()
