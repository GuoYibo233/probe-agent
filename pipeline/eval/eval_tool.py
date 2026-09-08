"""Replay eval (new pipeline eval stage): fit temperature on val + sweep threshold on val → freeze once on test.

Source = envs/bert/eval_replay.py (copied verbatim), plus the causal scoring path from envs/bert/eval_replay_causal.py.
The only changes are the four listed in spec §6.1:

1. Split names ("calA","calB","test") → ("val","test"): temperature is fit on val, θ is also swept on val
   (§2.5), test freeze is unchanged; report field names such as theta_sweep_calB [keep the old names unchanged].
2. `--data` points directly to <data_out> (no longer appends an env subdirectory), `--run` is now required, neither has a default.
3. `--head causal`: model loading = CausalProbe's (pipeline/train/train_causal_tool.py) backbone + head.pt;
   scoring runs one forward pass over the whole event and takes logits at each boundary position
   ([copied verbatim from eval_replay_causal.py's score_causal]). The cached-logits path is unchanged.
4. `--legacy-splits`: reads the old calA/calB/test and runs entirely under the old logic (temperature on calA, θ on calB),
   `--data`'s meaning falls back to <data>/<env> -- for §6.5 acceptance only.

Two more switches that do not change the logic (see the deviation record in ACCEPT_EVAL.md):
`--report-dir` (write the report elsewhere, so acceptance runs do not touch the old files), `--device`.

The third switch added by the ro1 batch, `--readonly-env {appworld,bfcl}` (off by default, off = behavior byte-for-byte unchanged):
when on, ground-truth labels uniformly pass through readonly_map.collapse() at load time (non-read-only tools collapse into the abstain class
<NON_READONLY>), the trigger condition narrows to "conf>=θ and argmax is not the abstain class", and a new top-level
readonly_stats is added. Old field names and formulas are unchanged. Whether label_map.json has an abstain sentinel
and whether this switch is on must hold together; either one alone hard-stops (anti-crosstalk two-way fuse).

Usage:
  # new pipeline (mbert classification head)
  mbert-env/bin/python pipeline/eval/eval_tool.py --env appworld \\
    --run pipeline/runs/c1_q35_mtool --data pipeline/data/aw_official_v1/q35
  # new pipeline (causal probe)
  cprobe-env/bin/python pipeline/eval/eval_tool.py --env appworld --head causal \\
    --run pipeline/runs/c1_q35_ctool --data pipeline/data/aw_official_v1/q35
"""

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "train"))
import readonly_map                                    # noqa: E402
import share_data                                       # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ops"))
import heartbeat                                       # noqa: E402

SEED = 20260729
THETAS = [round(0.5 + 0.025 * i, 3) for i in range(20)]  # 0.5 .. 0.975
RISK_TARGETS = [0.10, 0.05]        # trigger error-rate constraint (= precision 0.90/0.95)
BOOT = 1000
EVAL_BS = 4                        # causal scoring: events per batch


def load_rows(path):
    return [json.loads(l) for l in open(path)]


@torch.no_grad()
def score(model, tok, rows, dev, bs=16, max_len=4096):
    """Returns logits for each row (np array order matches rows)."""
    out = []
    model.eval()
    heartbeat.emit(0, len(rows), "item")
    for i in range(0, len(rows), bs):
        texts = [r["text"] for r in rows[i:i + bs]]
        enc = tok(texts, truncation=True, max_length=max_len,
                  padding=True, return_tensors="pt")
        enc = {k: v.to(dev) for k, v in enc.items()}
        out.append(model(**enc).logits.float().cpu())
        if (i // bs) % 50 == 0:
            print(f"scored {i}/{len(rows)}", flush=True)
            heartbeat.emit(i, len(rows), "item")
    return torch.cat(out)


# ---------------------------------------------------------------- causal scoring

def load_causal(run, n_labels, dev):
    """[copied verbatim from train_causal_tool.CausalProbe's loading method] backbone is read from best/,
    head is read from best/head.pt; on cuda, cast the backbone to bf16 (same as the old eval)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "train"))
    from train_causal_tool import CausalProbe          # noqa: E402
    model = CausalProbe(run / "best", n_labels)
    model.head.load_state_dict(
        torch.load(run / "best" / "head.pt", map_location="cpu"))
    if str(dev).startswith("cuda"):
        model.backbone = model.backbone.to(torch.bfloat16)
    return model.to(dev).eval()


def weights_fingerprint(run):
    """Fingerprint of the weight files under best/: size + sha1 of the first and last 64KB. The logits cache must be pinned to
    the weights that produced it -- matching row counts do not mean matching weights, a second round of training in the same
    directory would let stale logits masquerade as the new weights' results (audit B9). Do not use mtime: a normal copy/restore
    should not invalidate the cache.
    Returns {} when there are no weight files (an old run whose weights were cleaned up -- left to the caller to decide)."""
    import hashlib
    fps = {}
    for name in ("model.safetensors", "pytorch_model.bin", "model.pt", "head.pt"):
        p = Path(run) / "best" / name
        if p.exists():
            size = p.stat().st_size
            h = hashlib.sha1()
            with open(p, "rb") as f:
                h.update(f.read(65536))
                if size > 131072:
                    f.seek(-65536, 2)
                    h.update(f.read(65536))
            fps[name] = [size, h.hexdigest()[:16]]
    return fps


@torch.no_grad()
def score_causal(backbone, head, tok, rows, dev, max_len, bs=EVAL_BS,
                 overlong="left"):
    """One forward pass per event, gather logits at each boundary position, and restore them into a tensor in the same order as rows.

    `overlong` (spec 16.2), pick one of three:
    - "left": current behavior -- left-truncate the whole text to `max_len`, boundaries outside the window (`read_position`
      returns -1) get zero logits, `n_oow` is only a diagnostic count and does not exclude any row.
    - "skip": boundaries outside the window do not go into `excluded_idx` (not in any denominator), counted as
      `n_skipped_bounds` (the same batch of boundaries as `n_oow`, just excluded this time).
    - "drop-event": events whose full-text token count (`share_data.n_full_tokens`, ctool's own rule of
      "filter by label first, take the last row" -- here `rows` has already been filtered by `main()` on
      `label in label2id`, so using "last row's text" directly is the same rule) exceeds `max_len` skip
      tokenization/forward pass entirely; all boundaries of that event get zero logits and go into `excluded_idx`,
      counted as `n_dropped_events`/`n_dropped_bounds`. The full text of these events was never truncated, so
      surviving events no longer trigger `read_position`'s out-of-window branch, and `n_oow` is always 0.

    -> (out, excluded_idx, counts): `out`'s shape is unchanged (`len(rows)` rows, excluded
    rows have zero logits); `excluded_idx` is the list of indices of excluded rows (empty list under `left`);
    `counts` = dict(n_oow, n_skipped_bounds, n_dropped_events,
    n_dropped_bounds).
    """
    if overlong not in ("left", "skip", "drop-event"):
        raise ValueError(
            f"score_causal: overlong only supports left/skip/drop-event,"
            f"got {overlong!r}")
    ev = defaultdict(list)
    for i, r in enumerate(rows):
        ev[r["event"]].append((r["sent_idx"], i, r))
    events = []
    excluded_idx = []
    n_dropped_events = n_dropped_bounds = 0
    for k, items in ev.items():
        items.sort(key=lambda x: x[0])
        full = items[-1][2]["text"]
        if overlong == "drop-event" and share_data.n_full_tokens(tok, full) > max_len:
            n_dropped_events += 1
            n_dropped_bounds += len(items)
            excluded_idx.extend(i for _, i, _ in items)
            continue
        events.append((full, [(len(r["text"]), i) for _, i, r in items]))

    n_lab = head.out_features
    out = torch.zeros(len(rows), n_lab)
    n_oow = n_skipped_bounds = 0                 # number of boundaries outside the left-truncation window
    heartbeat.emit(0, len(events), "item")
    for s in range(0, len(events), bs):
        chunk = events[s:s + bs]
        enc = tok([e[0] for e in chunk], truncation=True, max_length=max_len,
                  padding=True, return_offsets_mapping=True,
                  return_tensors="pt")
        offs = enc.pop("offset_mapping")
        enc = {k: v.to(dev) for k, v in enc.items()}
        h = backbone(input_ids=enc["input_ids"],
                     attention_mask=enc["attention_mask"],
                     use_cache=False).last_hidden_state
        for bi, (full, bounds) in enumerate(chunk):
            offsets_i = offs[bi].tolist()
            keep = int(enc["attention_mask"][bi].sum())
            cols, idxs = [], []
            for b, ri in bounds:
                j = share_data.read_position(offsets_i, full, b, keep)
                if j < 0:
                    n_oow += 1
                    if overlong == "skip":
                        n_skipped_bounds += 1
                        excluded_idx.append(ri)
                    continue
                cols.append(j)
                idxs.append(ri)
            if cols:
                lg = head(h[bi, torch.tensor(cols, device=dev)].float())
                out[torch.tensor(idxs)] = lg.cpu()
        if (s // bs) % 25 == 0:
            print(f"scored {s}/{len(events)} events", flush=True)
            heartbeat.emit(s, len(events), "item")
    print(f"total boundaries {len(rows)}, left-truncated outside the window (all-zero logits, never fires) {n_oow}",
          flush=True)
    counts = dict(n_oow=n_oow, n_skipped_bounds=n_skipped_bounds,
                 n_dropped_events=n_dropped_events,
                 n_dropped_bounds=n_dropped_bounds)
    return out, sorted(excluded_idx), counts


def token_cost(tok, rows):
    """(bert_tokens, causal_tokens): per-row prefix vs. per-event full text, not counting max_len truncation."""
    bert = sum(len(x) for x in tok([r["text"] for r in rows])["input_ids"])
    ev = {}
    for r in rows:
        if len(r["text"]) > len(ev.get(r["event"], "")):
            ev[r["event"]] = r["text"]
    causal = sum(len(x) for x in tok(list(ev.values()))["input_ids"])
    return bert, causal


# ---------------------------------------------------------------- post-processing

def fit_temperature(logits, labels):
    logT = torch.zeros(1, requires_grad=True)
    opt = torch.optim.LBFGS([logT], lr=0.1, max_iter=100)
    lossf = torch.nn.CrossEntropyLoss()

    def closure():
        opt.zero_grad()
        loss = lossf(logits / logT.exp(), labels)
        loss.backward()
        return loss
    opt.step(closure)
    return float(logT.exp())


def replay(rows, probs, theta, nro_id=None):
    """rows and probs are in the same order. Returns per-event dict(fired, ok, depth, conf).

    nro_id=None is the legacy convention: the first boundary with conf>=θ triggers.
    When nro_id is given an abstain-class id (readonly mode), the trigger condition narrows to
    "conf>=θ and argmax != nro_id" -- predicting the abstain class never triggers.
    """
    ev = defaultdict(list)
    for r, p in zip(rows, probs):
        ev[r["event"]].append((r["sent_idx"], r, p))
    out = {}
    for k, items in ev.items():
        items.sort(key=lambda x: x[0])
        rec = dict(fired=False, ok=False, depth=None, conf=None,
                   unit=items[0][1]["unit"], label=items[0][1]["label"])
        for _, r, p in items:
            conf, pred = float(p.max()), int(p.argmax())
            if conf >= theta and (nro_id is None or pred != nro_id):
                rec.update(fired=True, ok=(pred == r["y"]),
                           depth=r["depth"], conf=conf)
                break
        out[k] = rec
    return out


def agg(recs):
    n = len(recs)
    fired = [r for r in recs if r["fired"]]
    cov = len(fired) / max(n, 1)
    acc = sum(r["ok"] for r in fired) / max(len(fired), 1)
    early = (sum(1 - r["depth"] for r in fired) / max(len(fired), 1))
    wrong = sum(1 for r in fired if not r["ok"]) / max(n, 1)
    return dict(n=n, coverage=round(cov, 4), trig_acc=round(acc, 4),
                earliness=round(early, 4), wrong_spec=round(wrong, 4))


def economics(recs):
    """Speculation-economics conversion (T4, offline estimate; field convention aligned with the T10 fork-comparison online measurement,
    for side-by-side reconciliation later):
    - exp_token_saving_ratio: truncation convention, expected fraction of thinking tokens saved per event
      = Σ triggered-events(1-depth) / total events ≡ trigger rate × lead amount (saved whether right or wrong; the cost of being wrong is
      recorded in the wrong-speculation rate)
    - exp_overlap_ratio: prefetch convention, expected overlapping-latency fraction; only events that triggered and predicted correctly
      contribute an overlap window (a wrong prefetch does not save latency, but is also harmless)
    """
    n = max(len(recs), 1)
    save = sum(1 - r["depth"] for r in recs if r["fired"]) / n
    overlap = sum(1 - r["depth"] for r in recs if r["fired"] and r["ok"]) / n
    return dict(exp_token_saving_ratio=round(save, 4),
                exp_overlap_ratio=round(overlap, 4))


def bootstrap(recs, rng):
    by_unit = defaultdict(list)
    for r in recs:
        by_unit[r["unit"]].append(r)
    units = list(by_unit)
    stats = defaultdict(list)
    for _ in range(BOOT):
        samp = []
        for u in (rng.choice(units) for _ in units):
            samp.extend(by_unit[u])
        a = agg(samp)
        for k in ("coverage", "trig_acc", "earliness"):
            stats[k].append(a[k])
    ci = {}
    for k, v in stats.items():
        v.sort()
        ci[k] = (round(v[int(BOOT * .025)], 4), round(v[int(BOOT * .975)], 4))
    return ci


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", required=True,
                    choices=["tales", "appworld", "bfcl", "alfworld"])
    ap.add_argument("--run", required=True, help="training output directory (required)")
    ap.add_argument("--data", required=True,
                    help="data directory <data_out>; under --legacy-splits, semantics fall back to <data>/<env>")
    ap.add_argument("--head", default="mbert", choices=["mbert", "causal"],
                    help="mbert=sequence classification head; causal=causal probe (backbone+head.pt)")
    ap.add_argument("--legacy-splits", action="store_true",
                    help="read the old calA/calB/test and run with the old logic (temperature from calA, θ from calB); for acceptance checks only")
    ap.add_argument("--report-dir", default=None,
                    help="report output directory (default = --run; point it elsewhere during acceptance checks to avoid overwriting old outputs)")
    ap.add_argument("--cached-logits", action="store_true",
                    help="read the logits_*.pt already saved in the run directory, skip model inference (pure CPU post-processing)")
    ap.add_argument("--adopt-logits-fingerprint", action="store_true",
                    help="backfill logits produced before the fingerprint mechanism existed, then exit: only claim the current weights"
                         " as their source when the weight's mtime isn't newer than the logits' (audit B9)")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--readonly-env", default=None,
                    choices=list(readonly_map.READONLY_ENVS),
                    help="readonly-tool + abstention-class mode (off by default); once on, ground truth is folded,"
                         "the fire condition adds \"argmax is not the abstention class\", and readonly_stats is output")
    ap.add_argument("--limit", type=int, default=0,
                    help="truncate each pile to the first N rows (a minute-scale smoke-test hook); the truncated logits_*.pt and"
                         " REPLAY_REPORT are still written to disk as usual, so this may only be used on --run"
                         " directories whose name includes smoke")
    ap.add_argument("--overlong", default="left",
                    choices=["left", "skip", "drop-event"],
                    help="three ways to handle an overlong full event text / prompt (spec 16.2); only takes effect for"
                         " --head causal, default left (behavior is byte-for-byte unchanged from"
                         " before this flag was added)")
    args = ap.parse_args()
    run = Path(args.run)
    if args.head == "mbert" and args.overlong != "left":
        raise SystemExit(
            f"--overlong {args.overlong!r} only takes effect for --head causal --"
            "the mbert head (ModernBERT sequence classification) only takes a single-line prefix per forward pass; it has no concept of"
            "'overlong full event text' or 'boundary left-truncated outside the window', it only supports left.")
    if args.limit and "smoke" not in run.name:
        raise SystemExit(
            f"--limit may only be used on --run directories whose name includes smoke (currently {run.name}):"
            "the truncated logits_*.pt and REPLAY_REPORT.json get written into --run, and downstream call "
            "evaluation follows the θ/logits here, silently contaminating the real run. To do a small-sample eval of the real weights,"
            "first copy the run directory to a name that includes smoke, then run it.")
    data = Path(args.data) / args.env if args.legacy_splits else Path(args.data)
    rep_dir = Path(args.report_dir) if args.report_dir else run
    rep_dir.mkdir(parents=True, exist_ok=True)
    dev = args.device
    rng = random.Random(SEED)

    # split-name mapping (§2.5): new convention has two splits, both temperature and θ are set on val; old convention's three splits unchanged
    if args.legacy_splits:
        split_names = ("calA", "calB", "test")
        fit_sp, sweep_sp = "calA", "calB"
    else:
        split_names = ("val", "test")
        fit_sp, sweep_sp = "val", "val"

    if args.adopt_logits_fingerprint:
        # logits produced before the fingerprint mechanism existed, backfilled: only if none of the weight files are newer than the logits
        # can we prove "the current weights are the weights that produced these logits" (audit B9 backfill path)
        fp = weights_fingerprint(run)
        if not fp:
            raise SystemExit(f"{run}/best has no weight file, nothing to claim")
        wt_mtime = max((Path(run) / "best" / n).stat().st_mtime for n in fp)
        n_done = 0
        for sp in split_names:
            lp = run / f"logits_{sp}.pt"
            if not lp.exists():
                continue
            if wt_mtime > lp.stat().st_mtime:
                raise SystemExit(
                    f"weights are newer than {lp.name} -- can't prove the logits came from the current weights,"
                    "refusing to claim them; drop --cached-logits and recompute.")
            logits = torch.load(lp)
            (run / f"logits_{sp}.meta.json").write_text(json.dumps(
                {"weights": fp, "rows": len(logits), "adopted": True}))
            n_done += 1
        print(f"claimed {n_done} logits fingerprints ({run});"
              "--cached-logits can be used now")
        return

    label2id = json.loads((run / "best" / "label_map.json").read_text())

    # anti-crosstalk two-way fuse: label_map has an abstain sentinel ⇔ --readonly-env must be passed
    has_sentinel = readonly_map.NON_READONLY in label2id
    if has_sentinel != bool(args.readonly_env):
        raise SystemExit(
            f"readonly fuse mismatch: {run / 'best' / 'label_map.json'} "
            f"{'has' if has_sentinel else 'has no'} abstention sentinel "
            f"{readonly_map.NON_READONLY!r}; but --readonly-env "
            f"{'was given ' + str(args.readonly_env) if args.readonly_env else 'was not given'}."
            "Both conditions must hold together or fail together -- a run trained in readonly mode can only be "
            "evaluated with --readonly-env; a run under the old settings can only be evaluated without it.")
    ro_table = ro_set = nro_id = None
    if args.readonly_env:
        ro_table = readonly_map.load_table(args.readonly_env)
        ro_set = readonly_map.load_readonly_set(args.readonly_env)
        nro_id = label2id[readonly_map.NON_READONLY]

    meta = {}
    if args.head == "causal":
        # [copied verbatim from eval_replay_causal.py] the tokenizer is loaded unconditionally (it's needed to count probing cost),
        # --cached-logits only skips the model itself
        meta = json.loads((run / "best" / "meta.json").read_text())
        max_len = meta.get("max_len", 4096)
        tok = AutoTokenizer.from_pretrained(run / "best")
        if tok.pad_token_id is None:
            tok.pad_token = tok.eos_token
        tok.truncation_side = "left"
        tok.padding_side = "right"
        if not args.cached_logits:
            model = load_causal(run, len(label2id), dev)
    elif not args.cached_logits:
        tok = AutoTokenizer.from_pretrained(run / "best")
        tok.truncation_side = "left"
        model = AutoModelForSequenceClassification.from_pretrained(
            run / "best", torch_dtype=torch.bfloat16,
            attn_implementation="sdpa").to(dev)

    splits = {}
    overlong_counts_test = dict(n_oow=0, n_skipped_bounds=0,
                                n_dropped_events=0, n_dropped_bounds=0)
    for sp in split_names:
        raw_rows = load_rows(data / f"{sp}.jsonl")
        if ro_set is not None:
            # ground-truth collapsing happens at load time: temperature fitting/θ sweeping/replay/prior baseline all use the collapsed labels afterward
            readonly_map.audit([r["label"] for r in raw_rows], ro_table,
                               f"eval_tool {sp}")
            for r in raw_rows:
                r["label"] = readonly_map.collapse(r["label"], ro_set)
        rows = [r for r in raw_rows if r["label"] in label2id]
        if args.limit:
            rows = rows[: args.limit]
        for r in rows:
            r["y"] = label2id[r["label"]]
        lp = run / f"logits_{sp}.pt"
        lmeta = run / f"logits_{sp}.meta.json"
        if args.cached_logits:
            if not lmeta.exists():
                raise SystemExit(
                    f"{lp} has no matching fingerprint {lmeta.name} -- the old cache gives no way to tell which "
                    "weights it came from (audit B9). Two options: drop --cached-logits and "
                    "recompute once (this fills in the fingerprint automatically); or, if the "
                    "weights are confirmed unchanged, use --adopt-logits-fingerprint to claim/backfill "
                    "the record (requires the weights' mtime to be no newer than the logits).")
            m = json.loads(lmeta.read_text())
            cached_mode = m.get("overlong_mode", "left")
            if cached_mode != args.overlong:
                raise SystemExit(
                    f"{lmeta} recorded overlong_mode={cached_mode!r}, which differs from this run's "
                    f"--overlong={args.overlong!r} -- caches from the two modes can happen to have "
                    "the same row count but different content (silent-failure point #33); refusing "
                    "to let one pass for the other. Drop --cached-logits and recompute, or switch back to "
                    f"--overlong {cached_mode}.")
            now_fp = weights_fingerprint(run)
            if not now_fp:
                print(f"⚠️ {run}/best no longer has a weights file, logits fingerprint cannot be verified -- "
                      f"trusting the source recorded in {lmeta.name}", flush=True)
            elif m.get("weights") != now_fp:
                raise SystemExit(
                    f"{lp}'s weights fingerprint does not match: the cache came from {m.get('weights')}, "
                    f"now it is {now_fp} -- the weights have been retrained/overwritten; refusing to let old logits "
                    "pass for new-weights results. Drop --cached-logits and recompute.")
            logits = torch.load(lp)
            assert len(logits) == len(rows), \
                f"{sp}: cached logits has {len(logits)} rows != data has {len(rows)} rows, --data does not match this eval's source"
            excluded_idx = m.get("excluded_idx", [])
            sc_counts = dict(
                n_oow=m.get("n_oow", 0),
                n_skipped_bounds=m.get("n_skipped_bounds", 0),
                n_dropped_events=m.get("n_dropped_events", 0),
                n_dropped_bounds=m.get("n_dropped_bounds", 0))
        elif args.head == "causal":
            logits, excluded_idx, sc_counts = score_causal(
                model.backbone, model.head, tok, rows, dev, max_len,
                overlong=args.overlong)
            torch.save(logits, lp)
            lmeta.write_text(json.dumps(
                {"weights": weights_fingerprint(run), "rows": len(rows),
                 "overlong_mode": args.overlong, "excluded_idx": excluded_idx,
                 **sc_counts}))
        else:
            logits = score(model, tok, rows, dev)
            excluded_idx, sc_counts = [], dict(
                n_oow=0, n_skipped_bounds=0, n_dropped_events=0,
                n_dropped_bounds=0)
            torch.save(logits, lp)
            lmeta.write_text(json.dumps(
                {"weights": weights_fingerprint(run), "rows": len(rows),
                 "overlong_mode": "left", "excluded_idx": []}))
        if sp == "test":
            overlong_counts_test = sc_counts
        if excluded_idx:
            excl = set(excluded_idx)
            keep_pos = [i for i in range(len(rows)) if i not in excl]
            rows = [rows[i] for i in keep_pos]
            logits = logits[torch.tensor(keep_pos, dtype=torch.long)]
        splits[sp] = (rows, logits)

    # 1) fit temperature on val (old convention: calA)
    rows_a, lg_a = splits[fit_sp]
    T = fit_temperature(lg_a, torch.tensor([r["y"] for r in rows_a]))

    # 2) sweep θ by replay on val (old convention: calB)
    rows_b, lg_b = splits[sweep_sp]
    probs_b = torch.softmax(lg_b / T, -1)
    sweep = []
    econ_sweep = []
    for th in THETAS:
        recs = list(replay(rows_b, probs_b, th, nro_id).values())
        sweep.append((th, agg(recs)))
        econ_sweep.append((th, economics(recs)))
    chosen = {}
    for risk in RISK_TARGETS:
        ok = [(th, a) for th, a in sweep
              if a["trig_acc"] >= 1 - risk and a["coverage"] > 0]
        chosen[risk] = (max(ok, key=lambda x: x[1]["coverage"])[0]
                        if ok else None)

    # 3) freeze on test: only run the selected θ
    rows_t, lg_t = splits["test"]
    probs_t = torch.softmax(lg_t / T, -1)
    final = {}
    econ_test = {}
    for risk, th in chosen.items():
        if th is None:
            final[risk] = None
            econ_test[str(risk)] = None
            continue
        recs = list(replay(rows_t, probs_t, th, nro_id).values())
        final[risk] = dict(theta=th, **agg(recs), ci=bootstrap(recs, rng))
        econ_test[str(risk)] = dict(theta=th, **economics(recs))

    # stop-time calibration (test, take the θ at risk 0.05; 0.8 if none)
    th0 = chosen.get(0.05) or 0.8
    fired = [r for r in replay(rows_t, probs_t, th0, nro_id).values()
             if r["fired"]]
    bins = defaultdict(list)
    for r in fired:
        bins[min(int(r["conf"] * 10), 9)].append(r)
    stoptime = {f"{b/10:.1f}-{(b+1)/10:.1f}":
                dict(n=len(v),
                     mean_conf=round(sum(x["conf"] for x in v) / len(v), 3),
                     acc=round(sum(x["ok"] for x in v) / len(v), 3))
                for b, v in sorted(bins.items())}

    # depth-decile sample-level acc (diagnostic) + prior baseline
    pred_t = probs_t.argmax(-1)
    dep = defaultdict(lambda: [0, 0])
    for r, p in zip(rows_t, pred_t):
        b = min(9, int(r["depth"] * 10))
        dep[b][0] += int(p) == r["y"]
        dep[b][1] += 1
    depth_acc = {f"{b/10:.1f}": round(c / n, 3)
                 for b, (c, n) in sorted(dep.items())}
    vocab = json.loads((data / "tool_vocab.json").read_text())
    if ro_set is not None:
        # the vocabulary is also collapsed by the same ground-truth table before taking the most frequent one: labels were collapsed
        # at load time (see above), the prior must be compared in the same label space -- if uncollapsed and the most frequent tool
        # is non-read-only (bfcl's startEngine), the prior is always 0, and the baseline gets squeezed into a fake advantage
        cnt = defaultdict(int)
        for k, v in vocab.items():
            cnt[readonly_map.collapse(k, ro_set)] += v
        vocab = dict(cnt)
    prior_tool = max(vocab, key=vocab.get)
    ev_labels = {r["event"]: r["label"] for r in rows_t}
    prior_acc = (sum(1 for v in ev_labels.values() if v == prior_tool)
                 / max(len(ev_labels), 1))

    # stats specific to readonly mode (not a single old field changed; the prior baseline is recomputed in the collapsed
    # label space -- reusing the old numbers is not allowed -- DATA.md §7.2)
    ro_stats = None
    if args.readonly_env:
        ro_stats = {"readonly_env": args.readonly_env,
                    "table": str(readonly_map.table_path(args.readonly_env)),
                    "theta_used": th0}
        for name, rws, prs in ((sweep_sp, rows_b, probs_b),
                               ("test", rows_t, probs_t)):
            recs = list(replay(rws, prs, th0, nro_id).values())
            ro = [r for r in recs
                  if r["label"] != readonly_map.NON_READONLY]
            nro = [r for r in recs
                   if r["label"] == readonly_map.NON_READONLY]
            cnt = defaultdict(int)
            for r in recs:
                cnt[r["label"]] += 1
            ro_stats[name] = dict(
                n_events=len(recs),
                n_readonly_truth=len(ro),
                ro_coverage=round(sum(r["fired"] for r in ro)
                                  / max(len(ro), 1), 4),
                nro_trigger_rate=round(sum(r["fired"] for r in nro)
                                       / max(len(nro), 1), 4),
                prior_baseline_collapsed=round(
                    max(cnt.values(), default=0) / max(len(recs), 1), 4),
            )

    rep = {
        "env": args.env, "temperature": round(T, 4),
        "theta_sweep_calB": [(th, a) for th, a in sweep],
        "chosen_theta": {str(k): v for k, v in chosen.items()},
        "test_frozen": {str(k): v for k, v in final.items()},
        "stoptime_calibration_test": stoptime,
        "depth_bucket_acc_test": depth_acc,
        "prior_baseline_event_acc": round(prior_acc, 4),
        "n_events_test": len(ev_labels),
        "overlong_mode": args.overlong if args.head == "causal" else "left",
        "n_skipped_bounds": overlong_counts_test["n_skipped_bounds"],
        "n_dropped_events": overlong_counts_test["n_dropped_events"],
        "n_dropped_bounds": overlong_counts_test["n_dropped_bounds"],
        "n_oow": overlong_counts_test["n_oow"],
        "speculation_economics": {
            "note": ("T4 offline estimate; reconciles with the T10 fork control (live measurement) at the same scale. "
                     "save = truncation setting: trigger rate × lead time; overlap = prefetch setting: only fire-and-correct cases"),
            "calB_sweep": econ_sweep,
            "test_frozen": econ_test,
        },
    }
    if ro_stats is not None:
        rep["readonly_stats"] = ro_stats
    if args.limit:
        # smoke stamp: a report carrying this field is from a truncated run, the numbers do not count
        rep["limit"] = args.limit
    # two diagnostic fields specific to the causal probe ([copied verbatim from eval_replay_causal.py], not a single old field changed)
    if args.head == "causal":
        bert_tok, causal_tok = token_cost(tok, rows_t)
        rep["probe_backbone"] = meta.get("base")
        rep["probe_cost_test"] = {
            "bert_tokens": bert_tok, "causal_tokens": causal_tok,
            "ratio": round(bert_tok / max(causal_tok, 1), 3)}
    (rep_dir / "REPLAY_REPORT.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=1))

    title = (f"# replay eval — {args.env}(causal probe {meta.get('base')})"
             if args.head == "causal" else f"# replay eval — {args.env}")
    md = [title, f"- temperature T={T:.3f}",
          f"- test event count {len(ev_labels)}; frequency prior baseline {prior_acc:.3f}",
          f"- overlong_mode={rep['overlong_mode']}"
          f"(n_skipped_bounds={rep['n_skipped_bounds']}, "
          f"n_dropped_events={rep['n_dropped_events']}, "
          f"n_dropped_bounds={rep['n_dropped_bounds']}, "
          f"n_oow={rep['n_oow']})", ""]
    for risk, r in final.items():
        if r:
            md.append(
                f"- **risk≤{risk}** θ={r['theta']}: coverage "
                f"{r['coverage']} (CI {r['ci']['coverage']}), trigger accuracy "
                f"{r['trig_acc']} (CI {r['ci']['trig_acc']}), earliness "
                f"{r['earliness']} (CI {r['ci']['earliness']}), "
                f"wrong-speculation rate {r['wrong_spec']}")
        else:
            md.append(f"- risk≤{risk}: no θ on calB satisfies the constraint")
    md += ["", "## depth-bucket acc (sample-level, diagnostic)",
           json.dumps(depth_acc), "", "## stop-time calibration (first fire point)",
           json.dumps(stoptime, ensure_ascii=False)]
    md += ["", "## speculation economics conversion (T4 offline estimate, settings aligned with the T10 fork control)",
           "| setting | θ | expected token-saving ratio (truncation) | expected overlap-delay ratio (prefetch) |",
           "|---|---|---|---|"]
    for risk, e in econ_test.items():
        if e:
            md.append(f"| test risk≤{risk} | {e['theta']} | "
                      f"{e['exp_token_saving_ratio']} | {e['exp_overlap_ratio']} |")
        else:
            md.append(f"| test risk≤{risk} | - | - | - |")
    md += ["", "calB, all θ settings:", "| θ | token saved | overlap delay |", "|---|---|---|"]
    md += [f"| {th} | {e['exp_token_saving_ratio']} | {e['exp_overlap_ratio']} |"
           for th, e in econ_sweep]
    if ro_stats is not None:
        md += ["", f"## readonly mode (--readonly-env {args.readonly_env})",
               f"- ground-truth table {ro_stats['table']}; abstention class "
               f"{readonly_map.NON_READONLY} (label id {nro_id}); "
               f"trigger condition adds \"argmax is not the abstention class\"",
               f"- the table below uses θ={th0} (the θ for risk≤0.05, or 0.8 if there is no solution)",
               "| pile | event count | of which ground-truth readonly | readonly-event coverage |"
               " non-readonly-event false-trigger rate | collapsed prior baseline |",
               "|---|---|---|---|---|---|"]
        for name in (sweep_sp, "test"):
            s = ro_stats[name]
            md.append(f"| {name} | {s['n_events']} | {s['n_readonly_truth']} |"
                      f" {s['ro_coverage']} | {s['nro_trigger_rate']} |"
                      f" {s['prior_baseline_collapsed']} |")
    if "probe_cost_test" in rep:
        pc = rep["probe_cost_test"]
        md += ["", "## probing cost (test, token compute for probing the whole trajectory)",
               f"- ModernBERT setting bert_tokens={pc['bert_tokens']} "
               "(rereads the prefix once at every sentence boundary)",
               f"- causal setting causal_tokens={pc['causal_tokens']} "
               "(reads the whole segment once per event)",
               f"- ratio={pc['ratio']}x",
               f"- setting: both sides count with the tokenizer of the {rep.get('probe_backbone')} backbone, "
               "not counting max_len truncation; counts only the tokens the probe reads in, excludes tokens the agent itself generates."]
    (rep_dir / "REPLAY_REPORT.md").write_text("\n".join(md) + "\n")
    heartbeat.emit(len(rows_t), len(rows_t), "item", status="done")
    print(json.dumps(rep["test_frozen"], indent=1))


if __name__ == "__main__":
    main()
