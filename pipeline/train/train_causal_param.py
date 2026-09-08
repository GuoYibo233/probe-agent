"""Causal parameter-generation training (the new pipeline's cparam cell): fine-tunes
Qwen3-Base into "write parameters given a tool name".

Division of labor with cgen (train_causal_callgen.py): cgen writes the tool name and the
parameters in one shot; cparam **feeds** the tool name in as part of the input, and the model
only writes the part after the opening parenthesis. See the third variant in
`plans/archive/2026-08-21-new-probe-training.md`.

- Input: <data_out>/{train,val}.jsonl, taking four fields per line: text / label / label_call / w;
  one sample = one training instance
- Concatenation: input string = text + CALL_SEP("\\n[CALL] ") + label + "(" ,
  target string = the remainder of label_call after stripping the prefix `label + "("`
  + eos
  (the remainder includes the closing parenthesis: `apis.spotify.login(username=x, password=y)` ->
  input tail `…[CALL] apis.spotify.login(`, target `username=x, password=y)`;
  for a call with no parameters the target is just `)`)
- Source of truth for the target: the single source of truth for the concatenation is build.py's
  make_call, so the target is always derived from label_call by stripping the prefix, **never
  reassembled from args_named** (reassembling would create a second concatenation rule, which
  will always drift). Rows where `label_call.startswith(label + "(")` does not hold are dropped
  entirely and counted
  (field assembly_mismatch, goes into the start log)
- Guarding against left-truncation eating the target: same as cgen -- tokenize the target first
  (no truncation); instances exceeding MAX_TGT_TOK are dropped entirely and counted; then
  left-truncate the input string to max_length = --max-len - len(tgt_ids), and after
  concatenation, labels mask the prompt segment to -100 (right padding within the batch, pad
  positions are also -100)
- Loss: per-instance mean CE over the target segment (ce_i), batch loss = Σ(w_i·ce_i)/Σw_i
- Eval: full-val weighted masked-CE every epoch (val_ce, the sole criterion for choosing best,
  lower is better) + fixed-seed sample of GEN_N greedy generations reporting val_exact_params
  (whole-target-segment hit, logged only, not used for best; matches cgen's val_exact_call
  accounting)
- Outputs: <out>/best/ (HF weights + tokenizer + meta.json) + train_log.jsonl
- LoRA: `--lora` swaps the backbone for LoRA training; before saving best, merge_and_unload runs
  first to merge the adapter back into the backbone, so the files in best/ are item-for-item
  isomorphic with a full-parameter save and eval_causal_param.py can load it back with zero
  changes; meta.json gets an extra "lora" block recording the hyperparameters. When --lora is
  not passed, the script never touches peft (all peft imports are inside the --lora branch), and
  behavior matches before this flag set was added; see lora_util.py for details.

No fire head: in the two-system comparison, firing is always decided by ctool (spec section
"at use time"), so cgen's `--fire-head` mechanism does not exist at all in this cell.

Usage:
  # smoke test (500 training instances / 200 eval instances / 1 epoch)
  cprobe-env/bin/python pipeline/train/train_causal_param.py \
    --data pipeline/data/aw_official_v1/q35 --out pipeline/runs/c2_q35_cparam --smoke
  # full run, swap to the 1.7B backbone
  cprobe-env/bin/python pipeline/train/train_causal_param.py --base qwen17 \
    --data pipeline/data/aw_official_v1/q35 --out pipeline/runs/c2_q35_cparam
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
                     "always go through run.py's tasks (train-ctool/train-cgen/train-cparam).")
from torch.utils.data import DataLoader, Dataset
from transformers import (AutoModelForCausalLM, AutoTokenizer,
                          get_linear_schedule_with_warmup)

import lora_util
import readonly_map

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / "ops"))
import heartbeat


# Three backbone tiers (since 2026-08-21 the causal line expanded from one tier to three tiers,
# styled the same as train_causal_tool.MODELS)
MODELS = {
    "qwen":   "/net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-0.6B-Base",
    "qwen17": "/net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-1.7B-Base",
    "qwen4":  "/net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-4B-Base",
}
SEED = 42                  # since np821, switched to the first of the seed family (42/67/4267/6742); the old value 20260729 only applies when reproducing old data
FULL_LR = 1e-5             # learning rate for full fine-tuning (the --lr default when --lora is not passed)
ASSEMBLY_MISMATCH_LIMIT = 0.05   # hard-stop threshold for the strip-failure rate, matching readonly_map.UNKNOWN_HARD_LIMIT
CALL_SEP = "\n[CALL] "
MAX_TGT_TOK = 160          # token cap for the target string; instances over this are dropped entirely
MAX_GEN_TOK = 96           # max_new_tokens for eval generation
GEN_N = 200                # how many rows to sample per epoch for greedy generation


# ---------------------------------------------------------------- concatenation

def param_prompt_tail(label):
    """The part of the input string appended after text: separator string + tool name + opening
    parenthesis."""
    return CALL_SEP + label + "("


def param_target(label, label_call):
    """(label, label_call) -> target string (without eos); returns None when the prefix doesn't
    match.

    The single source of truth for the concatenation is `pipeline/annotate/build.py`'s
    make_call: label_call = f"{tool}({inner})". So target = the whole span of label_call after
    stripping `label + "("`, with the closing parenthesis kept in the target (for a
    no-argument event the target is just `)`).
    Rows that return None are dropped entirely by the caller and counted under
    assembly_mismatch -- silently reassembling under a different rule would create a second
    source of truth for the concatenation, and that kind of drift raises no error.
    """
    pre = label + "("
    if not label_call.startswith(pre):
        return None
    return label_call[len(pre):]


# ---------------------------------------------------------------- data

class ParamDS(Dataset):
    """One sample = one instance; the target string is tokenized first during construction, and
    anything too long is dropped entirely and counted.

    Each row is a fixed 6-tuple (text, tgt_ids, w, label, tgt_str, label_call).
    When ro is not None (--readonly-env), non-read-only samples are dropped entirely, counted
    in ro.
    """

    def __init__(self, path, tok, limit=0, max_tgt=MAX_TGT_TOK, ro=None):
        self.rows, self.dropped, self.mismatch = [], 0, 0
        eos = tok.eos_token_id
        for line in open(path):
            r = json.loads(line)
            if ro is not None:                 # non-read-only samples are dropped entirely (counted in ro)
                ro["labels"].append(r["label"])
                if r["label"] not in ro["set"]:
                    ro["dropped"] += 1
                    continue
                ro["kept"] += 1
            tgt_str = param_target(r["label"], r["label_call"])
            if tgt_str is None:
                self.mismatch += 1
                continue
            tgt = tok(tgt_str, add_special_tokens=False)["input_ids"] + [eos]
            if len(tgt) > max_tgt:
                self.dropped += 1
                continue
            self.rows.append((r["text"], tgt, float(r["w"]), r["label"],
                              tgt_str, r["label_call"]))
        self.kept = len(self.rows)     # count kept before applying limit (used to compute the strip-failure rate)
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

    prompt = text + CALL_SEP + label + "(" -- the tool name and the opening parenthesis belong
    to the **input**; left truncation only ever eats into the head of text (the tokenizer's
    truncation_side is left), so the tool name and opening parenthesis are always preserved.
    """
    ids, labs, ws = [], [], []
    for text, tgt, w, label, _tgt_str, _call in batch:
        keep = max(max_len - len(tgt), 1)
        prompt = tok(text + param_prompt_tail(label), truncation=True,
                     max_length=keep, add_special_tokens=False)["input_ids"]
        ids.append(prompt + tgt)
        labs.append([-100] * len(prompt) + tgt)
        ws.append(w)
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
            torch.tensor(ws, dtype=torch.float))


# ---------------------------------------------------------------- model

def build(base, dev):
    """tokenizer construction is copied from train_causal_callgen.build(): pad=eos / left
    truncation / right padding."""
    path = MODELS[base]
    tok = AutoTokenizer.from_pretrained(path)
    if tok.pad_token_id is None:                      # copied from check_causal_candidates
        tok.pad_token = tok.eos_token
    tok.truncation_side = "left"                      # preserve the thinking tail
    tok.padding_side = "right"                        # the target segment is always on real tokens
    torch.manual_seed(SEED)
    model = AutoModelForCausalLM.from_pretrained(path, dtype=torch.float32)
    if model.config.get_text_config().pad_token_id is None:
        model.config.get_text_config().pad_token_id = tok.pad_token_id
    return tok, model.to(dev), path


def inst_ce(model, enc, labels, dev):
    """Per-instance mean CE over the target segment. Returns a [B] float32 tensor."""
    out = model(input_ids=enc["input_ids"], attention_mask=enc["attention_mask"],
                use_cache=False)
    lg = out.logits[:, :-1]                           # predict the next token
    tg = labels[:, 1:].to(dev)
    m = tg != -100
    ce = F.cross_entropy(lg[m].float(), tg[m], reduction="none")  # take only the target positions
    b = tg.size(0)
    inst = torch.arange(b, device=dev).unsqueeze(1).expand_as(tg)[m]
    ssum = torch.zeros(b, device=dev, dtype=torch.float32)
    ssum = ssum.index_add(0, inst, ce)
    return ssum / m.sum(1).clamp(min=1).float()


# ---------------------------------------------------------------- eval

@torch.no_grad()
def eval_ce(model, loader, dev, amp):
    """Full-val weighted masked-CE (same accounting as the training loss)."""
    model.eval()
    s = w_tot = 0.0
    for enc, labels, w in loader:
        enc = {k: v.to(dev) for k, v in enc.items()}
        with torch.autocast("cuda", dtype=torch.bfloat16, enabled=amp):
            ce = inst_ce(model, enc, labels, dev)
        wd = w.to(dev)
        s += (ce.float() * wd).sum().item()
        w_tot += wd.sum().item()
    model.train()
    if w_tot <= 0:
        raise SystemExit(
            "val has not a single target position (weighted denominator w_tot=0) -- continuing would give val_ce=0.0, "
            "saved as best every epoch, making the run look perfect. Something is wrong with the data or filter settings, hard stop.")
    return s / w_tot


@torch.no_grad()
def eval_gen(model, tok, rows, dev, amp, max_len, bs):
    """Fixed-seed sampled greedy generation: whole-target-segment hit rate (stops at \\n or
    eos)."""
    model.eval()
    prev_side, prev_cache = tok.padding_side, model.config.use_cache
    tok.padding_side = "left"                         # generation requires left padding
    model.config.use_cache = True
    hit = 0
    for i in range(0, len(rows), bs):
        chunk = rows[i:i + bs]
        enc = tok([r[0] + param_prompt_tail(r[3]) for r in chunk],
                  truncation=True,
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
            hit += (g.split("\n")[0].strip() == r[4])
    tok.padding_side, model.config.use_cache = prev_side, prev_cache
    model.train()
    return hit / max(len(rows), 1)


# ---------------------------------------------------------------- main flow

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="qwen", choices=sorted(MODELS),
                    help="base model, three tiers: qwen=0.6B (default)/qwen17=1.7B/qwen4=4B")
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
            f"{out} already has a train_log.jsonl -- this directory has been trained once, training again would mix "
            "both runs' outputs into the same best/ with no way to attribute them (audit B7). Use a different --out, or confirm the overwrite and add --force.")
    out.mkdir(parents=True, exist_ok=True)
    dev = args.device
    amp = dev.startswith("cuda")

    tok, model, path = build(args.base, dev)

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
    tr = ParamDS(data / "train.jsonl", tok, lim_tr, ro=ro_tr)
    ev = ParamDS(data / "val.jsonl", tok, lim_ev, ro=ro_ev)
    if args.readonly_env:
        au_tr = readonly_map.audit(ro_tr["labels"], ro_table, where="cparam/train")
        au_ev = readonly_map.audit(ro_ev["labels"], ro_table, where="cparam/val")
        ro_out = dict(
            readonly_env=args.readonly_env,
            table=str(readonly_map.table_path(args.readonly_env)),
            train=au_tr, val=au_ev,
            kept=dict(train=ro_tr["kept"], val=ro_ev["kept"]),
            dropped=dict(train=ro_tr["dropped"], val=ro_ev["dropped"]))
        (out / "READONLY.json").write_text(json.dumps(
            ro_out, ensure_ascii=False, indent=1))
    # Fuse: hard-stop if val loads 0 rows. An empty val will not crash training (SequentialSampler
    # does not block on empty), it will just make val_ce always 0, save best every epoch, and make
    # the run look perfect.
    if not len(ev):
        raise SystemExit(
            f"{data / 'val.jsonl'} loaded to 0 val rows"
            f"(dropped={ev.dropped}, assembly_mismatch={ev.mismatch}"
            + (f", readonly_dropped={ro_ev['dropped']}" if ro_ev else "")
            + ") -- the metric for picking best has no denominator, hard stop.")
    # Fuse: hard-stop if the strip-failure rate exceeds the limit. A mismatch between label and
    # label_call's prefix usually means the upstream concatenation convention changed; continuing
    # to train would silently swallow samples; the 5% threshold matches the
    # readonly_map.UNKNOWN_HARD_LIMIT precedent.
    for split, ds in (("train", tr), ("val", ev)):
        tot = ds.kept + ds.mismatch
        if tot and ds.mismatch / tot > ASSEMBLY_MISMATCH_LIMIT:
            raise SystemExit(
                f"{split}'s strip failure rate {ds.mismatch}/{tot} = "
                f"{ds.mismatch / tot:.3f} exceeds {ASSEMBLY_MISMATCH_LIMIT} -- "
                "upstream string-assembly settings drifted, hard stop.")
    mk = lambda ds, sh: DataLoader(
        ds, batch_size=args.bs, shuffle=sh, num_workers=2,
        collate_fn=lambda b: collate(b, tok, args.max_len))
    tr_dl, ev_dl = mk(tr, True), mk(ev, False)
    gen_rows = list(ev.rows)
    random.Random(SEED).shuffle(gen_rows)
    gen_rows = gen_rows[:GEN_N]

    # LoRA: swap the backbone in place for LoRA training. This cell has no extra head; only the
    # adapter goes into the optimizer.
    lora_wrap = lora_util.wrap(model, args) if args.lora else None
    if args.grad_ckpt:
        model.gradient_checkpointing_enable()
        model.config.use_cache = False
        if args.lora:
            lora_util.prepare_grad_ckpt(model)
    model.train()

    steps = math.ceil(len(tr_dl) / args.accum) * epochs
    opt = torch.optim.AdamW(lora_util.opt_params(model.parameters(), args.lora),
                            lr=lr, weight_decay=0.01)
    sch = get_linear_schedule_with_warmup(opt, int(steps * 0.05), steps)

    logf = open(out / "train_log.jsonl", "a")

    def log(**kw):
        kw["t"] = round(time.time(), 1)
        logf.write(json.dumps(kw) + "\n")
        logf.flush()
        print(kw, flush=True)

    log(event="start", base=args.base, base_path=path, env=args.env,
        n_train=len(tr), n_eval=len(ev), n_gen=len(gen_rows), steps=steps,
        smoke=args.smoke, max_len=args.max_len, max_tgt_tok=MAX_TGT_TOK,
        seed=SEED, dropped_train=tr.dropped, dropped_eval=ev.dropped,
        assembly_mismatch=dict(train=tr.mismatch, val=ev.mismatch),
        device=dev, readonly_env=args.readonly_env, param_only=True,
        **(dict(lora=lora_util.meta_block(args, lr)) if args.lora else {}))
    heartbeat.emit(0, steps, "step")

    best = float("inf")
    gstep = 0
    for ep in range(epochs):
        t0, run = time.time(), 0.0
        for i, (enc, labels, w) in enumerate(tr_dl):
            enc = {k: v.to(dev) for k, v in enc.items()}
            with torch.autocast("cuda", dtype=torch.bfloat16, enabled=amp):
                ce = inst_ce(model, enc, labels, dev)
            wd = w.to(dev)
            loss = (ce.float() * wd).sum() / wd.sum()
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
        vce = eval_ce(model, ev_dl, dev, amp)
        vex = eval_gen(model, tok, gen_rows, dev, amp, args.max_len,
                       args.gen_bs)
        log(event="eval", ep=ep, val_ce=round(vce, 4),
            val_exact_params=round(vex, 4))
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
                param_only=True, transformers=transformers.__version__,
                assembly_mismatch=dict(train=tr.mismatch, val=ev.mismatch))
            if args.readonly_env:
                meta["readonly_env"] = args.readonly_env
            if args.lora:
                meta["lora"] = lora_util.meta_block(args, lr)
            if args.grad_ckpt:
                meta["grad_ckpt"] = True
            (out / "best" / "meta.json").write_text(json.dumps(meta, indent=1))
            log(event="save_best", ep=ep, val_ce=round(best, 4))
    log(event="done", best_val_ce=round(best, 4))
    heartbeat.emit(gstep, steps, "step", status="done")


if __name__ == "__main__":
    main()
