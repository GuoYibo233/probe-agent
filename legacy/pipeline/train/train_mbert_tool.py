"""ModernBERT tool-type head training (new pipeline mtool cell, one model per run).

- Input: <data_out>/{train,val}.jsonl + tool_vocab.json
- Loss: weighted cross-entropy, weight = the sample's own w (=1/m_i, equal weight within
  an event)
- Truncation: tokenizer left-truncates to 4096 (keeps the tail of the thinking)
- Eval: each epoch reports on val the weighted sample acc + the event-final-boundary acc
  (full-thinking); log field names keep the old calA_* names (downstream scripts read by
  name)
- Outputs: <out>/best/ (best weights + tokenizer + label_map.json) + train_log.jsonl

Usage (smoke):
  mbert-env/bin/python pipeline/train/train_mbert_tool.py \
    --data pipeline/data/aw_official_v1/q35 --out pipeline/runs/c1_q35_mtool --smoke
Full run:
  mbert-env/bin/python pipeline/train/train_mbert_tool.py \
    --data pipeline/data/aw_official_v1/q35 --out pipeline/runs/c1_q35_mtool
"""

import argparse
import json
import math
import random
import time
from pathlib import Path

import torch
from torch.utils.data import DataLoader, Dataset
import transformers
# Two-env hard rule (run.py PY table): the mbert line pins transformers==4.57.6; running
# under the wrong interpreter drifts silently, so this rejects it outright
if transformers.__version__ != "4.57.6":
    raise SystemExit(f"the mbert line pins transformers==4.57.6, currently "
                     f"{transformers.__version__} -- wrong interpreter? "
                     "Always enter through run.py's tasks (train-mtool/train-mext).")
from transformers import (AutoModelForSequenceClassification, AutoTokenizer,
                          get_linear_schedule_with_warmup)

import readonly_map
from input_modes import apply_mode

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / "ops"))
import heartbeat


MODEL = "/net/tokyo100-10g/data/str01_01/y-guo/models/ModernBERT-base"
SEED = 20260729


class JsonlDS(Dataset):
    def __init__(self, path, label2id, limit=0, mode="full", ro=None):
        if ro is None:
            rows = [r for r in map(json.loads, open(path))
                    if r["label"] in label2id]
        else:                                  # --readonly-env: inventory first, then collapse
            rows = list(map(json.loads, open(path)))
            ro["info"] = readonly_map.audit(
                [r["label"] for r in rows], ro["table"], where=ro["where"])
            for r in rows:
                r["label"] = readonly_map.collapse(r["label"], ro["set"])
            bad = sorted({r["label"] for r in rows} - set(label2id))
            if bad:
                raise SystemExit(
                    f"readonly: {ro['where']} still has {len(bad)} labels not in the"
                    f" folded vocab after folding (e.g. {bad[:5]}) -- tool_vocab.json does not match the data, hard stop.")
            rows = [r for r in rows if r["label"] in label2id]
        self.rows = apply_mode(rows, mode)
        if limit:
            rng = random.Random(SEED)
            rng.shuffle(self.rows)
            self.rows = self.rows[:limit]
        self.label2id = label2id

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        r = self.rows[i]
        return (r["text"], self.label2id[r["label"]], r["w"],
                r["sent_idx"] == r["n_sents"] - 1)


def collate(batch, tok, max_len):
    texts, labels, ws, lasts = zip(*batch)
    enc = tok(list(texts), truncation=True, max_length=max_len,
              padding=True, return_tensors="pt")
    return (enc, torch.tensor(labels), torch.tensor(ws, dtype=torch.float),
            torch.tensor(lasts))


@torch.no_grad()
def evaluate(model, loader, dev):
    model.eval()
    wc = ws = lc = ln = 0.0
    for enc, y, w, last in loader:
        enc = {k: v.to(dev) for k, v in enc.items()}
        with torch.autocast("cuda", dtype=torch.bfloat16):
            pred = model(**enc).logits.argmax(-1).cpu()
        ok = (pred == y).float()
        wc += (ok * w).sum().item()
        ws += w.sum().item()
        lc += ok[last].sum().item()
        ln += last.sum().item()
    model.train()
    return wc / max(ws, 1e-9), lc / max(ln, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default="appworld",
                    choices=["tales", "appworld", "bfcl", "alfworld"],
                    help="log label only (the data path is given directly by --data)")
    ap.add_argument("--data", required=True,
                    help="data dir <data_out> (contains train/val.jsonl and tool_vocab.json)")
    ap.add_argument("--out", required=True, help="output dir (required; guards against overwriting old outputs)")
    ap.add_argument("--max-len", type=int, default=4096)
    ap.add_argument("--bs", type=int, default=8)
    ap.add_argument("--accum", type=int, default=4)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--smoke", action="store_true",
                    help="500 training samples/200 eval samples/1 epoch, for pipeline verification")
    ap.add_argument("--input-mode", default="full",
                    choices=["full", "no-think", "no-hist"],
                    help="T5 ablation: cut the [THINKING] or [HISTORY] segment")
    ap.add_argument("--readonly-env", default=None,
                    choices=list(readonly_map.READONLY_ENVS),
                    help="read-only tool mode: fold labels into this environment's read-only tools plus the "
                         f"{readonly_map.NON_READONLY} abstain class (off by default = the old settings)")
    ap.add_argument("--force", action="store_true",
                    help="allow training again in an --out dir that was already trained in (refused by default to keep outputs apart)")
    args = ap.parse_args()

    torch.manual_seed(SEED)
    random.seed(SEED)
    data = Path(args.data)
    out = Path(args.out)
    if (out / "train_log.jsonl").exists() and not args.force:
        raise SystemExit(
            f"{out} already has a train_log.jsonl -- this dir has already been trained once; training again would mix"
            " both runs' outputs into the same best/ with no way to tell them apart (audit B7). Use a different --out, or confirm the overwrite and pass --force.")
    out.mkdir(parents=True, exist_ok=True)
    dev = "cuda"

    vocab = json.loads((data / "tool_vocab.json").read_text())
    ro_tr = ro_ev = None
    if args.readonly_env:                      # vocab = read-only tools in original order + trailing sentinel
        ro_set = readonly_map.load_readonly_set(args.readonly_env)
        ro_table = readonly_map.load_table(args.readonly_env)
        vocab = [t for t in vocab if t in ro_set] + [readonly_map.NON_READONLY]
        ro_tr = dict(set=ro_set, table=ro_table, where="mtool/train")
        ro_ev = dict(set=ro_set, table=ro_table, where="mtool/val")
    label2id = {k: i for i, k in enumerate(vocab)}
    tok = AutoTokenizer.from_pretrained(MODEL)
    tok.truncation_side = "left"          # keep the tail of the thinking
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL, num_labels=len(label2id),
        attn_implementation="sdpa")
    model.config.reference_compile = False
    model.to(dev).train()

    lim_tr, lim_ev = (500, 200) if args.smoke else (0, 0)
    epochs = 1 if args.smoke else args.epochs
    tr = JsonlDS(data / "train.jsonl", label2id, lim_tr, args.input_mode, ro_tr)
    ev = JsonlDS(data / "val.jsonl", label2id, lim_ev, args.input_mode, ro_ev)
    if args.readonly_env:
        (out / "READONLY.json").write_text(json.dumps(dict(
            readonly_env=args.readonly_env,
            table=str(readonly_map.table_path(args.readonly_env)),
            train=ro_tr["info"], val=ro_ev["info"],
            vocab_size_collapsed=len(label2id)), ensure_ascii=False, indent=1))
    mk = lambda ds, sh: DataLoader(
        ds, batch_size=args.bs, shuffle=sh, num_workers=2,
        collate_fn=lambda b: collate(b, tok, args.max_len))
    tr_dl, ev_dl = mk(tr, True), mk(ev, False)

    steps = math.ceil(len(tr_dl) / args.accum) * epochs
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    sch = get_linear_schedule_with_warmup(opt, int(steps * 0.05), steps)
    lossf = torch.nn.CrossEntropyLoss(reduction="none")

    logf = open(out / "train_log.jsonl", "a")

    def log(**kw):
        kw["t"] = round(time.time(), 1)
        logf.write(json.dumps(kw) + "\n")
        logf.flush()
        print(kw, flush=True)

    log(event="start", env=args.env, n_train=len(tr), n_eval=len(ev),
        n_labels=len(label2id), steps=steps, smoke=args.smoke,
        input_mode=args.input_mode, readonly_env=args.readonly_env)
    heartbeat.emit(0, steps, "step")

    best = -1.0
    gstep = 0
    for ep in range(epochs):
        t0, run = time.time(), 0.0
        for i, (enc, y, w, _last) in enumerate(tr_dl):
            enc = {k: v.to(dev) for k, v in enc.items()}
            with torch.autocast("cuda", dtype=torch.bfloat16):
                logits = model(**enc).logits
            loss = (lossf(logits.float(), y.to(dev))
                    * w.to(dev)).sum() / w.sum().to(dev)
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
        wacc, lacc = evaluate(model, ev_dl, dev)
        log(event="eval", ep=ep, calA_weighted_acc=round(wacc, 4),
            calA_lastbound_acc=round(lacc, 4))
        if wacc > best:
            best = wacc
            model.save_pretrained(out / "best")
            tok.save_pretrained(out / "best")
            (out / "best" / "label_map.json").write_text(
                json.dumps(label2id, ensure_ascii=False))
            log(event="save_best", ep=ep, acc=round(best, 4))
    log(event="done", best_calA_weighted_acc=round(best, 4))
    heartbeat.emit(gstep, steps, "step", status="done")


if __name__ == "__main__":
    main()
