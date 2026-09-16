"""Trigger-time extraction eval (new pipeline mext cell): replay determines the threshold, extract parameters on that prefix,
and report full-call accuracy.

Source = envs/bert/eval_extract.py (copied verbatim) plus the parse/tier_of/THRESH from envs/bert/param_tiers.py
(moved into this file together, no separate module anymore). The only changes are the ones listed in spec §6.2:
`--data`/`--params` point to the new directory (<data_out> directly contains test.jsonl, and params defaults to
<data_out>/params), the split name calA → val (this script only uses the test split, so this only shows up in the params-directory convention),
and the extraction-head function is now imported from pipeline/train/train_mbert_extract.py. Everything else is copied verbatim:
the threshold comes from --run (mtool)'s REPLAY_REPORT temperature + chosen_theta, the extraction head runs on the prefix up to the trigger,
the loose/strict/full-call three tiers, and the three-tier breakdown (reads <data_out>/router_stats.md).

The ro1 batch adds `--readonly-env {appworld,bfcl}` (off by default; off = behavior byte-for-byte unchanged). When on,
ground-truth labels pass through readonly_map.collapse() at load time, and the trigger condition adds "argmax is not the abstain class";
parameter metrics are computed only on events where "it triggered and the ground truth is a read-only tool" -- events that triggered but whose
ground truth is non-read-only do not go into the params_all_ok / full_call_ok denominators, and are counted separately into the new key readonly_excluded.
Existing field names and the three-tier scoring are unchanged. The abstain sentinel in label_map.json and this flag each require the other.

Self-fire eval `--self-fire` (off by default; does not touch any old fields, only adds a self_fire block):
for mext runs trained with a fire head -- the fire moment no longer comes from mtool's report's θ, but is decided by the extraction
head's own fire head.
- Fire score: at each boundary, feed **plain text** (without the [FIND] suffix) into the encoder, take the [CLS] position
  through the fire head, sigmoid into a fire probability (same position convention as the training side)
- Fire condition = fire probability ≥ θ_fire **and** the mtool argmax at the same boundary is not the abstain sentinel
  (if argmax is abstain, treat it as not fired, and keep scanning forward)
- θ_fire is swept on **val** (using eval_tool's THETAS grid and RISK_TARGETS mechanism),
  risk is computed from labels: a wrong fire = fired but the ground truth is not-ready
  (ready = ground-truth tool is read-only and all parameters at that boundary are found)
- test is frozen once: at the fire point, extract parameters using the original three-tier scoring; tool identity is taken from the mtool
  argmax at the same boundary, so a fully correct call = all parameters correct (loose) and argmax == the collapsed ground truth
- requires --readonly-env, an mext run with fire_head=true, and the logits_val.pt / logits_test.pt already saved
  in the mtool run directory (present if eval_tool has been run)

Usage:
  mbert-env/bin/python pipeline/eval/eval_mbert_call.py --env appworld \\
    --run pipeline/runs/c1_q35_mtool --extractor pipeline/runs/c1_q35_mext \\
    --data pipeline/data/aw_official_v1/q35
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "train"))
import readonly_map                                      # noqa: E402
from train_mbert_extract import (FIND, collate, decode,  # noqa: E402
                                 load_extractor, span_ok)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_tool import RISK_TARGETS, THETAS               # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ops"))
import heartbeat                                          # noqa: E402

TIERS = ("no-arg", "choice", "free")
SPORK_ANCHOR = 0.076        # competitor SPORK's baseline parameter accuracy
PILOT_ANCHOR = 0.338        # pilot check: fraction of cases where the literal string already appears 25 tokens early
THRESH = 0.90               # [copied verbatim from param_tiers.py] exact-match hit-rate cutoff between the choice/free tiers


# ---------- three-tier table ([copied verbatim from param_tiers.py]) ----------

def parse(md_text):
    rows = []
    for line in md_text.splitlines():
        m = re.match(r"\|\s*(.+?)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*([\d.]+|-)\s*\|", line)
        if m:
            hit = None if m.group(4) == "-" else float(m.group(4))
            rows.append((m.group(1), int(m.group(2)), int(m.group(3)), hit))
    return rows


def tier_of(hit):
    if hit is None:
        return "no-arg"
    return "choice" if hit >= THRESH else "free"


def load_rows(path):
    return [json.loads(l) for l in open(path)]


def replay_fire(rows, probs, theta, nro_id=None):
    """Same logic as eval_tool.replay, additionally returns the sent_idx and line where it triggered.

    nro_id=None is the legacy convention; when given an abstain-class id (readonly mode), the trigger condition narrows to
    "conf>=θ and argmax != nro_id", exactly the same as eval_tool.replay.
    """
    ev = defaultdict(list)
    for r, p in zip(rows, probs):
        ev[r["event"]].append((r["sent_idx"], r, p))
    out = {}
    for k, items in ev.items():
        items.sort(key=lambda x: x[0])
        rec = dict(fired=False, ok=False, sent_idx=None, row=None,
                   label=items[0][1]["label"])
        for _, r, p in items:
            conf, pred = float(p.max()), int(p.argmax())
            if conf >= theta and (nro_id is None or pred != nro_id):
                rec.update(fired=True, ok=(pred == r["y"]),
                           sent_idx=r["sent_idx"], row=r)
                break
        out[k] = rec
    return out


@torch.no_grad()
def run_extractor(model, tok, meta, items, dev, bs):
    """items=[(str,value,gs,ge,found)] -> [(loose_ok, strict_ok, pred_ans)]."""
    out = []
    heartbeat.emit(0, len(items), "item")
    for i in range(0, len(items), bs):
        chunk = [(s, v, gs, ge, f, 1.0) for s, v, gs, ge, f in items[i:i + bs]]
        b = collate(chunk, tok, meta["max_len"])
        enc = {k: v.to(dev) for k, v in b["enc"].items()}
        s_lg, e_lg, a_lg = model(enc, b["last"].to(dev))
        s_lg, e_lg = s_lg.float().cpu(), e_lg.float().cpu()
        ansp = (a_lg.float().cpu() > 0)
        spans = decode(s_lg, e_lg, b["valid"], b["offs"])
        for j in range(len(chunk)):
            pa = bool(ansp[j])
            c0, c1 = spans[j]
            out.append((pa and span_ok(b["strs"][j], c0, c1,
                                       b["gs"][j], b["ge"][j]),
                        pa and b["strs"][j][c0:c1] == b["vals"][j], pa))
        if (i // bs) % 20 == 0:
            print(f"extracted {i}/{len(items)}", flush=True)
            heartbeat.emit(i, len(items), "item")
    return out


def rate(num, den):
    return round(num / den, 4) if den else None


# ---------- extraction scoring (moved verbatim out of main, logic unchanged) ----------

def extract_points(keys, fired, pmap, model, tok, meta, dev, bs):
    """Extract parameters at the given trigger/fire point and aggregate per event.

    Parameter correct = when ground truth is found, the span matches / when ground truth cannot be extracted, the answer says it cannot be extracted -- [logic unchanged, verbatim].
    Returns (per_ev, a counts dict).
    """
    items, index = [], []
    for k in keys:
        rec = fired[k]
        text = rec["row"]["text"]
        for q in pmap.get((k, rec["sent_idx"]), []):
            index.append((k, q["found"]))
            items.append((text + FIND + q["key"], q["value"],
                          q["start"], q["end"], q["found"]))
    res = run_extractor(model, tok, meta, items, dev, bs) if items else []
    per_ev = {k: dict(loose=True, strict=True, present=True, n=0) for k in keys}
    c = dict(n_par=0, n_loose=0, n_strict=0, n_present=0)
    for (k, fnd), (lo, st, pa) in zip(index, res):
        cl, cs = (lo, st) if fnd else (not pa, not pa)
        e = per_ev[k]
        e["n"] += 1
        e["loose"] &= cl
        e["strict"] &= cs
        e["present"] &= fnd
        c["n_par"] += 1
        c["n_loose"] += cl
        c["n_strict"] += cs
        c["n_present"] += fnd
    return per_ev, c


# ------------------------------------------------------------ self-fire

def load_ready(data, params, split, ro_set, label2id):
    """Read a batch of samples, collapse labels, compute the fire ground truth ready, and filter by label2id to keep
    the same order as logits_<split>.pt (filtering logic matches eval_tool line for line).

    ready = ground-truth tool is in the read-only set and all parameters of the sample have found=true (vacuously true with zero parameters);
    samples that fail to join in params are treated as not-ready and counted.
    """
    pmap = {}
    for p in load_rows(params / f"{split}.jsonl"):
        pmap[(p["event"], p["sent_idx"])] = p["params"]
    raw = load_rows(data / f"{split}.jsonl")
    st = dict(n=len(raw), n_ready=0, n_readonly=0,
              n_join_miss=0, n_join_miss_with_args=0)
    for r in raw:
        is_ro = r["label"] in ro_set
        st["n_readonly"] += is_ro
        ps = pmap.get((r["event"], r["sent_idx"]))
        if ps is None:
            st["n_join_miss"] += 1
            if r.get("args_named"):
                st["n_join_miss_with_args"] += 1
            r["ready"] = False
        else:
            r["ready"] = bool(is_ro and all(q["found"] for q in ps))
        st["n_ready"] += r["ready"]
        r["label"] = readonly_map.collapse(r["label"], ro_set)
    n = max(st["n"], 1)
    st["frac_ready"] = round(st["n_ready"] / n, 6)
    st["frac_readonly"] = round(st["n_readonly"] / n, 6)
    st["frac_join_miss"] = round(st["n_join_miss"] / n, 6)
    if st["frac_join_miss"] > 0.01:
        print(f"[self-fire] warning: {split} has {st['n_join_miss']}/{st['n']} "
              f"({st['frac_join_miss']:.1%}) samples that can't be joined against params,"
              f"already treated as not-ready", flush=True)
    rows = [r for r in raw if r["label"] in label2id]
    for r in rows:
        r["y"] = label2id[r["label"]]
    st["n_in_label_space"] = len(rows)
    return rows, pmap, st


@torch.no_grad()
def score_fire(model, tok, rows, dev, bs, max_len):
    """Fire probability at each boundary: plain text goes into the encoder, the [CLS] position goes through the fire head."""
    out = torch.zeros(len(rows))
    for i in range(0, len(rows), bs):
        chunk = [r["text"] for r in rows[i:i + bs]]
        enc = tok(chunk, truncation=True, max_length=max_len, padding=True,
                  return_tensors="pt")
        enc = {k: v.to(dev) for k, v in enc.items()}
        lg = model.fire_logit(enc)
        out[i:i + len(chunk)] = torch.sigmoid(lg.float()).cpu()
        if (i // bs) % 100 == 0:
            print(f"fire-scored {i}/{len(rows)}", flush=True)
    return out


def replay_fire_head(rows, probs, theta, gate):
    """Fire-head version of replay: for each event, take the first boundary where "fire probability ≥ θ and gate is true".

    gate[i] = the mtool argmax at that boundary is not the abstain sentinel; if argmax is abstain, treat it as not fired,
    and keep scanning forward (the same rule as "argmax != nro_id" in replay_fire).
    """
    ev = defaultdict(list)
    for i, (r, p) in enumerate(zip(rows, probs)):
        ev[r["event"]].append((r["sent_idx"], i, r, float(p)))
    out = {}
    for k, items in ev.items():
        items.sort(key=lambda x: x[0])
        rec = dict(fired=False, ready=False, ok=False, sent_idx=None,
                   row=None, conf=None)
        for _, i, r, p in items:
            if p >= theta and gate[i]:
                rec.update(fired=True, ready=bool(r["ready"]),
                           ok=bool(gate.pred[i] == r["y"]),
                           sent_idx=r["sent_idx"], row=r, conf=round(p, 4))
                break
        out[k] = rec
    return out


class Gate:
    """mtool argmax gate: gate[i] = argmax is not the abstain sentinel; gate.pred[i] = argmax."""

    def __init__(self, logits, nro_id):
        self.pred = logits.argmax(-1).tolist()
        self.ok = [p != nro_id for p in self.pred]

    def __getitem__(self, i):
        return self.ok[i]


def agg_fire(recs):
    """Fire head's coverage / accuracy / wrong-fire rate, formulas isomorphic to eval_tool.agg."""
    n = len(recs)
    fired = [r for r in recs if r["fired"]]
    return dict(n=n, n_fired=len(fired),
                coverage=round(len(fired) / max(n, 1), 4),
                fire_acc=round(sum(r["ready"] for r in fired)
                               / max(len(fired), 1), 4),
                wrong_fire_rate=round(sum(1 for r in fired if not r["ready"])
                                      / max(n, 1), 4))


def pick_theta(sweep):
    """[same mechanism as eval_tool's θ selection] take the tier with maximum coverage under the risk constraint."""
    chosen = {}
    for risk in RISK_TARGETS:
        ok = [(th, a) for th, a in sweep
              if a["fire_acc"] >= 1 - risk and a["coverage"] > 0]
        chosen[risk] = (max(ok, key=lambda x: x[1]["coverage"])[0]
                        if ok else None)
    return chosen


def self_fire_block(args, run, ext, data, params, model, tok, meta,
                    label2id, ro_set, nro_id):
    """Sweep θ_fire on val → freeze once on test → extract and score parameters at the fire point."""
    if not meta.get("fire_head"):
        raise SystemExit(
            f"--self-fire requires the mext run to be trained with a fire head:{ext/'best'/'meta.json'} "
            "doesn't have \"fire_head\": true. Train with train_mbert_extract.py --fire-head.")
    bs = args.fire_bs or args.bs
    max_len = meta["max_len"]
    blocks = {}
    for sp in ("val", "test"):
        f = run / f"logits_{sp}.pt"
        if not f.exists():
            raise SystemExit(
                f"--self-fire needs the same-boundary mtool argmax to determine tool identity, missing {f}."
                "First run eval_tool.py on the same mtool run (it saves logits_*.pt).")
        rows, pmap, st = load_ready(data, params, sp, ro_set, label2id)
        lg = torch.load(f, map_location="cpu")
        if len(rows) != lg.shape[0]:
            raise SystemExit(f"{f} has {lg.shape[0]} rows, {sp} has {len(rows)} rows after filtering"
                             "-- data and cached logits don't come from the same source")
        blocks[sp] = (rows, pmap, st, Gate(lg, nro_id))

    val_rows, _vp, val_st, val_gate = blocks["val"]
    pv = score_fire(model, tok, val_rows, args.device, bs, max_len)
    sweep = [(th, agg_fire(list(replay_fire_head(val_rows, pv, th,
                                                 val_gate).values())))
             for th in THETAS]
    chosen = pick_theta(sweep)
    th_fire = chosen.get(args.risk)
    test_rows, test_pmap, test_st, test_gate = blocks["test"]
    base = dict(theta_fire=th_fire, risk=args.risk,
                chosen_theta_fire={str(k): v for k, v in chosen.items()},
                theta_sweep_val=[dict(theta=th, **a) for th, a in sweep],
                ready_stats=dict(val=val_st, test=test_st))
    if th_fire is None:
        print(f"[self-fire] none of the 20 θ tiers on val push risk down to ≤{args.risk};"
              f"chosen={chosen}, this block only outputs the sweep table.", flush=True)
        return dict(base, val=None, test=None, scored=None, on_ready=None)

    pt = score_fire(model, tok, test_rows, args.device, bs, max_len)
    rec = replay_fire_head(test_rows, pt, th_fire, test_gate)
    keys = [k for k in dict.fromkeys(r["event"] for r in test_rows)
            if rec[k]["fired"]]
    if args.limit:
        keys = keys[:args.limit]
    per_ev, c = extract_points(keys, rec, test_pmap, model, tok, meta,
                               args.device, args.bs)

    def block(ks):
        n = len(ks)
        return dict(
            n=n,
            noparam_events=sum(1 for k in ks if per_ev[k]["n"] == 0),
            params_all_present=rate(sum(per_ev[k]["present"] for k in ks), n),
            params_all_ok=rate(sum(per_ev[k]["loose"] for k in ks), n),
            params_all_ok_strict=rate(sum(per_ev[k]["strict"] for k in ks), n),
            full_call_ok=rate(sum(per_ev[k]["loose"] and rec[k]["ok"]
                                  for k in ks), n))
    return dict(
        base,
        val=dict(theta=th_fire,
                 **agg_fire(list(replay_fire_head(val_rows, pv, th_fire,
                                                  val_gate).values()))),
        test=agg_fire(list(rec.values())),
        scored=dict(n_param_instances=c["n_par"],
                    param_acc_loose=rate(c["n_loose"], c["n_par"]),
                    param_acc_strict=rate(c["n_strict"], c["n_par"]),
                    **block(keys)),
        on_ready=block([k for k in keys if rec[k]["ready"]]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", required=True,
                    choices=["tales", "appworld", "bfcl", "alfworld"])
    ap.add_argument("--run", required=True, help="classification head run directory (mtool)")
    ap.add_argument("--data", required=True,
                    help="data directory <data_out> (directly contains test.jsonl / router_stats.md)")
    ap.add_argument("--params", default=None,
                    help="parameter-span label directory (default <data>/params)")
    ap.add_argument("--extractor", required=True, help="extraction head run directory (mext)")
    ap.add_argument("--risk", type=float, default=0.05)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--bs", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0, help="truncate to the first N events (smoke test)")
    ap.add_argument("--readonly-env", default=None,
                    choices=list(readonly_map.READONLY_ENVS),
                    help="readonly-tool + abstention-class mode (off by default); once on, ground truth is folded,"
                         "the fire condition adds \"argmax is not the abstention class\", and parameter metrics are computed only for"
                         "fired events whose ground truth is a readonly tool")
    ap.add_argument("--self-fire", action="store_true",
                    help="autonomous-fire evaluation: θ_fire is swept on val and frozen once for test,"
                         "the fire moment is decided by the extraction head's own fire head, not by mtool's θ."
                         "only adds a self_fire block; none of the old fields are touched")
    ap.add_argument("--fire-bs", type=int, default=0,
                    help="batch size for fire scoring (0 = follow --bs)")
    args = ap.parse_args()

    run, ext = Path(args.run), Path(args.extractor)
    data = Path(args.data)
    params = Path(args.params) if args.params else data / "params"

    if args.self_fire and not args.readonly_env:
        raise SystemExit(
            "--self-fire must be passed together with --readonly-env: the definition of fire ground-truth ready"
            "depends on that environment's readonly ground-truth table.")

    rep_cls = json.loads((run / "REPLAY_REPORT.json").read_text())
    T = rep_cls["temperature"]
    theta = rep_cls["chosen_theta"].get(str(args.risk))
    if theta is None:
        if not args.self_fire:
            raise SystemExit(f"no θ for risk={args.risk} in the classification head's report:"
                             f"{rep_cls['chosen_theta']}")
        print(f"[self-fire] no θ for risk={args.risk} in the classification head's report"
              f"({rep_cls['chosen_theta']}); the whole old-mode block is skipped, only self_fire is output.",
              flush=True)
    old_mode = theta is not None

    # 1) threshold: filtering logic matches eval_tool line for line, guaranteeing the same order as logits_test.pt
    label2id = json.loads((run / "best" / "label_map.json").read_text())

    # anti-crosstalk two-way fuse: label_map has an abstain sentinel ⇔ --readonly-env must be passed
    has_sentinel = readonly_map.NON_READONLY in label2id
    if has_sentinel != bool(args.readonly_env):
        raise SystemExit(
            f"readonly fuse mismatch:{run / 'best' / 'label_map.json'} "
            f"{'has' if has_sentinel else 'lacks'} abstention sentinel "
            f"{readonly_map.NON_READONLY!r}; while --readonly-env "
            f"{'passed ' + str(args.readonly_env) if args.readonly_env else 'not passed'}."
            "Both must hold together or fail together -- a run trained in readonly mode can only be "
            "evaluated with --readonly-env; a run trained under the old settings can only be evaluated without it.")
    ro_set = nro_id = None
    if args.readonly_env:
        ro_set = readonly_map.load_readonly_set(args.readonly_env)
        nro_id = label2id[readonly_map.NON_READONLY]

    raw_rows = load_rows(data / "test.jsonl")
    if ro_set is not None:
        readonly_map.audit([r["label"] for r in raw_rows],
                           readonly_map.load_table(args.readonly_env),
                           "eval_mbert_call test")
        for r in raw_rows:
            r["label"] = readonly_map.collapse(r["label"], ro_set)
    rows = [r for r in raw_rows if r["label"] in label2id]
    for r in rows:
        r["y"] = label2id[r["label"]]
    fired, keys, n_ro_excluded = {}, [], 0
    if old_mode:
        logits = torch.load(run / "logits_test.pt", map_location="cpu")
        assert len(rows) == logits.shape[0], (len(rows), logits.shape)
        fired = replay_fire(rows, torch.softmax(logits / T, -1), theta, nro_id)

    # 2) parameter ground truth: the row in params with the same (event, sent_idx)
    pmap = {}
    for p in load_rows(params / "test.jsonl"):
        pmap[(p["event"], p["sent_idx"])] = p["params"]

    if old_mode:
        keys = [k for k in dict.fromkeys(r["event"] for r in rows)
                if fired[k]["fired"]]
        # readonly mode: events that triggered but whose ground truth is non-read-only are excluded from parameter metrics (not in any denominator), counted separately
        if ro_set is not None:
            keep = [k for k in keys
                    if fired[k]["label"] != readonly_map.NON_READONLY]
            n_ro_excluded = len(keys) - len(keep)
            keys = keep
        if args.limit:
            keys = keys[:args.limit]

    model, tok, meta = load_extractor(ext, args.device)

    # 3) aggregate per event. Parameter correct = when ground truth is found, the span matches / when ground truth cannot be extracted, the answer says it cannot be extracted
    per_ev, cnts = extract_points(keys, fired, pmap, model, tok, meta,
                                  args.device, args.bs)
    n_par, n_loose = cnts["n_par"], cnts["n_loose"]
    n_strict, n_present = cnts["n_strict"], cnts["n_present"]

    tiers = {name: tier_of(hit)
             for name, _n, _np, hit in parse((data / "router_stats.md")
                                             .read_text())}

    buck = defaultdict(lambda: dict(n=0, allok=0, allok_s=0, call=0,
                                    noparam=0, present=0))

    def add(b, k):
        rec, pe = fired[k], per_ev[k]
        b["n"] += 1
        b["allok"] += pe["loose"]
        b["allok_s"] += pe["strict"]
        b["call"] += pe["loose"] and rec["ok"]
        b["noparam"] += pe["n"] == 0
        b["present"] += pe["present"]

    for k in keys:
        add(buck["overall"], k)
        add(buck[tiers.get(fired[k]["label"], "free")], k)

    def fmt(b):
        return dict(n=b["n"], noparam_events=b["noparam"],
                    params_all_present=rate(b["present"], b["n"]),
                    params_all_ok=rate(b["allok"], b["n"]),
                    params_all_ok_strict=rate(b["allok_s"], b["n"]),
                    full_call_ok=rate(b["call"], b["n"]))

    n_ev = len(rows) and len({r["event"] for r in rows})
    out = dict(
        env=args.env, run=str(run), extractor=str(ext), risk=args.risk,
        theta=theta, temperature=T, n_events_test=n_ev)
    if old_mode:
        out.update(
            n_events_fired=len([k for k in fired if fired[k]["fired"]]),
            n_events_scored=len(keys), limit=args.limit,
            n_param_instances=n_par,
            param_present_rate=rate(n_present, n_par),
            param_acc_loose=rate(n_loose, n_par),
            param_acc_strict=rate(n_strict, n_par),
            by_tier={t: fmt(buck[t]) for t in TIERS if t in buck},
            overall=fmt(buck["overall"]),
            anchors=dict(spork_param_acc=SPORK_ANCHOR,
                         pilot_value_present_at_25tok=PILOT_ANCHOR))
    if ro_set is not None:
        out["readonly_env"] = args.readonly_env
        out["readonly_excluded"] = n_ro_excluded

    # ---------------- self-fire (--self-fire): sweep θ_fire on val, freeze once on test
    sf = None
    if args.self_fire:
        sf = self_fire_block(args, run, ext, data, params, model, tok, meta,
                             label2id, ro_set, nro_id)
        out["self_fire"] = sf
    (ext / "EXTRACT_REPORT.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1))

    md = [f"# Extraction evaluation at the fire moment -- {args.env}"]
    if not old_mode:
        md += [f"- classification head {run.name} has no θ solution at risk={args.risk},"
               "the whole old-mode block is skipped; this file has only the autonomous-fire section."]
    md += ([
          f"- classification head {run.name} / extraction head {ext.name}; risk≤{args.risk} → θ={theta}"
          f"(temperature T={T})",
          f"- test events {n_ev}, fired {out['n_events_fired']},"
          f"{len(keys)} counted this time" + (f"(--limit {args.limit})"
                                     if args.limit else ""),
          f"- parameter instances {n_par}; parameter-level accuracy loose {out['param_acc_loose']} / "
          f"strict {out['param_acc_strict']}; value already present at fire time "
          f"{out['param_present_rate']}",
          "",
          "| tier | events | of which no-arg | values already present | all-params-correct rate |"
          " all params correct (strict) | full-call accuracy |",
          "|---|---|---|---|---|---|---|"] if old_mode else [])
    for t in (list(TIERS) + ["overall"]) if old_mode else []:
        if t not in buck:
            continue
        f = fmt(buck[t])
        md.append(f"| {t} | {f['n']} | {f['noparam_events']} | "
                  f"{f['params_all_present']} | {f['params_all_ok']} | "
                  f"{f['params_all_ok_strict']} | {f['full_call_ok']} |")
    md += ["",
           "## Anchors and known risks",
           f"- the competing system SPORK's starting parameter accuracy is {SPORK_ANCHOR:.1%};"
           "the full-call accuracy in this table's last column is the same measure.",
           "- known risk: parameters at early fire points often haven't appeared yet -- in an earlier pilot, firing 25 tokens ahead,"
           f"the literal string had appeared only {PILOT_ANCHOR:.1%} of the time. This part of the ground truth is recorded as not extractable,"
           "the extraction head getting 'not extractable' right also counts as the parameter being correct, so the all-params-correct rate can be higher than"
           "the values-already-present rate; but the only thing that reflects what can truly be assembled into a full call to speculate on at fire time,"
           "is the values-already-present column -- that is the ceiling on speculation coverage.",
           "- correctness criterion: loose = the predicted character span covers the ground truth and the only extra characters are whitespace/punctuation."
           "BPE merges the leading space and the quote into one token, so strict exact match systematically underestimates --"
           "the gold-standard token span's own strict pass rate is only "
           "tales 0.066 / bfcl 0.642 / appworld 0.659,"
           "and under the loose settings it's 0.997/0.997/0.991. The strict column is for reference only."]
    if ro_set is not None and old_mode:
        md += ["", f"## Readonly mode (--readonly-env {args.readonly_env})",
               f"- abstention class {readonly_map.NON_READONLY} (label id {nro_id});"
               "the fire condition adds \"argmax is not the abstention class\"; ground-truth labels have been folded",
               f"- events that fire but whose ground truth isn't readonly, and therefore don't enter any parameter denominator:"
               f"{n_ro_excluded}(readonly_excluded);"
               f"the denominator for every column in this table is the remaining {len(keys)} ground-truth-readonly fired events"]
    if sf is not None and sf["test"] is None:
        md += ["", f"## Autonomous fire (--self-fire, risk≤{args.risk})",
               f"- none of the 20 θ tiers on val push risk down to ≤{args.risk}"
               f"(chosen={sf['chosen_theta_fire']}); test wasn't evaluated,"
               "only the self_fire.theta_sweep_val sweep table is kept."]
    elif sf is not None:
        a = sf["test"]
        md += ["", f"## Autonomous fire (--self-fire, risk≤{args.risk})",
               f"- θ_fire was swept to {sf['theta_fire']} on val"
               f"(val coverage {sf['val']['coverage']} / "
               f"fire accuracy {sf['val']['fire_acc']}); test frozen once",
               "- fire condition = fire head probability ≥ θ_fire AND the same-boundary mtool argmax is not the abstention class;"
               "fire ground-truth ready = the tool is readonly AND every parameter at that boundary is found",
               f"- test events {a['n']}, fired {a['n_fired']},"
               f"coverage {a['coverage']}, fire accuracy {a['fire_acc']},"
               f"wrong-fire rate {a['wrong_fire_rate']}",
               f"- parameter instances {sf['scored']['n_param_instances']}; parameter-level accuracy "
               f"loose {sf['scored']['param_acc_loose']} / "
               f"strict {sf['scored']['param_acc_strict']}",
               "",
               "| metric (denominator = fire points) | all fire points | of which ground-truth ready |",
               "|---|---|---|",
               f"| number of events | {sf['scored']['n']} | {sf['on_ready']['n']} |",
               f"| of which no-arg | {sf['scored']['noparam_events']} | "
               f"{sf['on_ready']['noparam_events']} |",
               f"| values already present | {sf['scored']['params_all_present']} | "
               f"{sf['on_ready']['params_all_present']} |",
               f"| all-params-correct rate | {sf['scored']['params_all_ok']} | "
               f"{sf['on_ready']['params_all_ok']} |",
               f"| all params correct (strict) | {sf['scored']['params_all_ok_strict']} | "
               f"{sf['on_ready']['params_all_ok_strict']} |",
               f"| full-call accuracy | {sf['scored']['full_call_ok']} | "
               f"{sf['on_ready']['full_call_ok']} |",
               "",
               "- the left column doesn't exclude any fire point: for the events with a wrong fire, the tool identity necessarily doesn't match"
               "(mtool argmax isn't the abstention class, but the ground truth is), so it's naturally scored wrong --"
               "this column is the real score for \"letting the probe decide for itself when to fire\".",
               "- the right column only looks at fire points where the ground truth is ready, for reading side by side with the old-mode table above."]
    (ext / "EXTRACT_REPORT.md").write_text("\n".join(md) + "\n")
    heartbeat.emit(cnts["n_par"], cnts["n_par"], "item", status="done")
    if old_mode:
        print(json.dumps(out["overall"], ensure_ascii=False, indent=1))
    if sf is not None and sf["test"] is not None:
        print(json.dumps(dict(theta_fire=sf["theta_fire"], **sf["test"],
                              full_call_ok=sf["scored"]["full_call_ok"]),
                         ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
