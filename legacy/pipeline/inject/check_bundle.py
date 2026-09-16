"""Output-loading checker (build spec section 8): can training outputs be loaded as-is
by the "injection side" and scored.

What it does: load `<run>/best/` the same way the Probe class in
`envs/loop/probe_server.py` does, run one forward pass on the first sample from
`<data>/test.jsonl`, print the predicted tool / confidence / whether it passes
chosen_theta["0.05"] / ground truth, and write the same content into
`<run>/BUNDLE_CHECK.txt`.
**Running through is the proof** -- this is not an accuracy eval, it only proves these
weights load and score in a different process too.

Two heads:
  --head mbert   AutoModelForSequenceClassification(`best/`) + `best/label_map.json`
                 + the temperature from `REPLAY_REPORT.json`   [mbert-env]
  --head causal  CausalProbe = AutoModel backbone(`best/`) + `best/head.pt` linear head
                 (class structure sourced from: CausalProbe/build in
                  envs/bert/train_causal_probe.py; if pipeline/train/train_causal_tool.py
                  is in place, import it directly)
                                                          [cprobe-env]

When REPLAY_REPORT.json does not exist (e.g. right after a smoke test, before eval),
fall back to temperature=1.0, and the θ column reads N/A -- this path is for
"check_bundle.py runs on smoke outputs" per section 9.

Usage:
  mbert-env/bin/python pipeline/inject/check_bundle.py \
      --run pipeline/runs/c1_q35_mtool --data pipeline/data/aw_official_v1/q35 \
      --head mbert --device cpu
  cprobe-env/bin/python pipeline/inject/check_bundle.py \
      --run pipeline/runs/c1_q35_ctool --data pipeline/data/aw_official_v1/q35 \
      --head causal
"""

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

import torch

TRAIN_CAUSAL_TOOL = Path(__file__).resolve().parents[1] / "train" / "train_causal_tool.py"


# ---------------------------------------------------------------- causal structure

def _inline_causal_probe():
    """Inline copy of CausalProbe. Source: envs/bert/train_causal_probe.py (unchanged,
    word for word).

    Use only while pipeline/train/train_causal_tool.py is not yet in place; once that
    file lands, load_causal() will import it preferentially, so the training side and
    the injection side are always the same class.
    """
    from transformers import AutoModel

    class CausalProbe(torch.nn.Module):
        """Causal language model backbone + nn.Linear classification head (takes the last-layer hidden state at each supervised token position)."""

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

    return CausalProbe


def _causal_probe_cls():
    if TRAIN_CAUSAL_TOOL.exists():
        # The training script writes same-directory imports (readonly_map, etc.) on the
        # assumption that the script's directory is on sys.path; importlib loading by file path
        # has no such assumption, so add it here
        train_dir = str(TRAIN_CAUSAL_TOOL.parent)
        if train_dir not in sys.path:
            sys.path.insert(0, train_dir)
        spec = importlib.util.spec_from_file_location(
            "pipeline_train_causal_tool", TRAIN_CAUSAL_TOOL)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, "CausalProbe"):
            return mod.CausalProbe, f"import {TRAIN_CAUSAL_TOOL}"
    return _inline_causal_probe(), "inline (source: envs/bert/train_causal_probe.py)"


# ---------------------------------------------------------------- loading

class MBertBundle:
    """Loading works the same way as the Probe class in envs/loop/probe_server.py."""
    kind = "mbert"

    def __init__(self, run, temperature, device, dtype, max_len=4096):
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        run = Path(run)
        label2id = json.loads((run / "best" / "label_map.json").read_text())
        self.id2label = {v: k for k, v in label2id.items()}
        self.tok = AutoTokenizer.from_pretrained(run / "best")
        self.tok.truncation_side = "left"
        self.model = AutoModelForSequenceClassification.from_pretrained(
            run / "best", torch_dtype=dtype,
            attn_implementation="sdpa",
            reference_compile=False).to(device).eval()
        self.T = float(temperature)
        self.device = device
        self.max_len = max_len
        self.detail = f"dtype={dtype} attn=sdpa n_labels={len(self.id2label)}"

    @torch.no_grad()
    def probs(self, text):
        enc = self.tok([text], truncation=True, max_length=self.max_len,
                       return_tensors="pt")
        enc = {k: v.to(self.device) for k, v in enc.items()}
        logits = self.model(**enc).logits.float().cpu()[0]
        return torch.softmax(logits / self.T, -1)


class CausalBundle:
    """backbone (best/) + head.pt, tokenizer -- all three set up per train_causal_probe.build()."""
    kind = "causal"

    def __init__(self, run, temperature, device, dtype, max_len=None):
        from transformers import AutoTokenizer
        run = Path(run)
        best = run / "best"
        label2id = json.loads((best / "label_map.json").read_text())
        self.id2label = {v: k for k, v in label2id.items()}
        meta = {}
        if (best / "meta.json").exists():
            meta = json.loads((best / "meta.json").read_text())
        self.max_len = max_len or int(meta.get("max_len", 4096))

        self.tok = AutoTokenizer.from_pretrained(best)
        if self.tok.pad_token_id is None:              # copied verbatim from build()
            self.tok.pad_token = self.tok.eos_token
        self.tok.truncation_side = "left"              # keep the thinking tail
        self.tok.padding_side = "right"                # supervised positions are all on real tokens

        cls, src = _causal_probe_cls()
        self.model = cls(str(best), len(label2id))
        self.model.head.load_state_dict(
            torch.load(best / "head.pt", map_location="cpu"))
        cfg = self.model.backbone.config.get_text_config()
        if cfg.pad_token_id is None:
            cfg.pad_token_id = self.tok.pad_token_id
        self.model = self.model.to(device=device, dtype=dtype).eval()
        self.T = float(temperature)
        self.device = device
        self.detail = (f"dtype={dtype} n_labels={len(self.id2label)} "
                       f"max_len={self.max_len} CausalProbe={src}")

    @torch.no_grad()
    def probs(self, text):
        enc = self.tok([text], truncation=True, max_length=self.max_len,
                       return_tensors="pt")
        enc = {k: v.to(self.device) for k, v in enc.items()}
        # single sample, no padding: supervised position = the last real token
        col = int(enc["attention_mask"][0].sum()) - 1
        logits = self.model(enc, torch.tensor([0]), torch.tensor([col]))
        logits = logits.float().cpu()[0]
        return torch.softmax(logits / self.T, -1)


# ---------------------------------------------------------------- main flow

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="training output dir (contains best/)")
    ap.add_argument("--data", required=True, help="data dir (contains test.jsonl)")
    ap.add_argument("--head", required=True, choices=["mbert", "causal"])
    ap.add_argument("--device", default="cuda", help="cuda / cpu")
    ap.add_argument("--dtype", default="auto",
                    help="auto = bfloat16 on cuda (matches probe_server), float32 on cpu; "
                         "can also be written explicitly as bfloat16/float32")
    ap.add_argument("--temperature", type=float, default=None,
                    help="override the temperature from REPLAY_REPORT.json")
    ap.add_argument("--index", type=int, default=0,
                    help="which row of test.jsonl to take (default the first row)")
    ap.add_argument("--max-len", type=int, default=None)
    args = ap.parse_args()

    run, data = Path(args.run), Path(args.data)
    if args.dtype == "auto":
        dtype = torch.bfloat16 if str(args.device).startswith("cuda") else torch.float32
    else:
        dtype = getattr(torch, args.dtype)

    # ---- temperature and θ: fall back to the default if not evaluated yet, don't block the smoke check ----
    rep_path = run / "REPLAY_REPORT.json"
    theta, temperature, rep_note = None, 1.0, "REPLAY_REPORT.json missing -> T=1.0, θ=N/A"
    if rep_path.exists():
        rep = json.loads(rep_path.read_text())
        temperature = float(rep.get("temperature", 1.0))
        theta = (rep.get("chosen_theta") or {}).get("0.05")
        theta = float(theta) if theta is not None else None
        rep_note = f"read temperature={temperature} theta0.05={theta} from {rep_path.name}"
    if args.temperature is not None:
        temperature = args.temperature
        rep_note += f"; --temperature overridden to {temperature}"

    # ---- sample ----
    with open(data / "test.jsonl") as f:
        row = None
        for i, line in enumerate(f):
            if i == args.index:
                row = json.loads(line)
                break
    if row is None:
        raise SystemExit(f"test.jsonl has no row {args.index}")

    t0 = time.time()
    cls = MBertBundle if args.head == "mbert" else CausalBundle
    bundle = cls(run, temperature, args.device, dtype, args.max_len)
    t_load = time.time() - t0

    t0 = time.time()
    probs = bundle.probs(row["text"])
    t_fwd = time.time() - t0

    k = min(5, probs.numel())
    top = torch.topk(probs, k=k)
    pred = bundle.id2label[int(probs.argmax())]
    conf = float(probs.max())
    gold = row.get("label")
    fired = None if theta is None else conf >= theta

    lines = [
        "BUNDLE_CHECK — output-loading check (pipeline/inject/check_bundle.py)",
        f"time            : {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"run             : {run}",
        f"data            : {data}",
        f"head            : {args.head}   device={args.device}   {bundle.detail}",
        f"temperature     : {bundle.T}   ({rep_note})",
        f"sample          : idx={args.index} event={row.get('event')} "
        f"unit={row.get('unit')} step={row.get('step')} "
        f"sent_idx={row.get('sent_idx')}/{row.get('n_sents')} "
        f"n_chars={len(row['text'])}",
        f"predicted tool  : {pred}",
        f"confidence      : {conf:.6f}",
        f"chosen_theta0.05: {'N/A' if theta is None else theta}",
        f"over threshold  : {'N/A' if fired is None else ('YES' if fired else 'NO')}",
        f"ground truth    : {gold}",
        f"pred == truth   : {pred == gold}",
        "top5            : " + ", ".join(
            f"{bundle.id2label[int(i)]}={float(p):.4f}"
            for p, i in zip(top.values, top.indices)),
        f"elapsed         : load {t_load:.1f}s / forward {t_fwd * 1000:.0f}ms",
        "conclusion      : LOAD_OK (passes if it loads and can score; numeric precision is out of scope for this check)",
    ]
    text = "\n".join(lines) + "\n"
    (run / "BUNDLE_CHECK.txt").write_text(text)
    print(text, end="")
    print("wrote", run / "BUNDLE_CHECK.txt")


if __name__ == "__main__":
    main()
