"""Trigger-time call generation eval (new pipeline, cgen cell): at ctool's threshold
point, have the callgen model greedily write out the whole call, and score three levels
of accuracy: tool name / parameters / whole call.

Implementation of spec section 6.3. Read alongside eval_mbert_call.py (the
extraction-head route): the threshold point definition on both sides comes from exactly
the same source (copied verbatim from eval_extract.py's replay_fire()); the only
difference is "where the parameters come from" -- that side extracts a span from the
trigger prefix, this side generates the whole call directly.

- Threshold point: get temperature T and chosen_theta[--risk] from --ctool-run's
  REPLAY_REPORT.json, replay on the test stack with logits_test.pt, and for each event
  take the first sample row that crosses θ
- Generation: prompt = trigger-sample text + CALL_SEP, CALL_SEP is read from the
  `call_sep` field of --cgen-run/best/meta.json (shares the same convention as the
  training-side string concatenation, not hardcoded); greedy, max_new_tokens=96, stop on
  eos, then cut at the first \\n, then .strip() (matches the training-side
  val_exact_call convention). Temporarily switch padding_side to left during generation
- Parsing: tool name copied verbatim from AW_CALL (appworld) / ALF_CALL (alfworld) /
  BFCL_CALL (bfcl and tales); parameters copied verbatim from split_args_named's split
  logic plus the same normalization (strip, then strip quotes). Regex mismatch =
  parse_fail
- Scoring (ground truth = the trigger sample's label and args_named):
    tool_ok           parsed tool name == label
    per parameter     loose = equal after normalization; strict = equal on the raw,
                      unnormalized string; a key mismatch (extra param, missing param,
                      wrong name) = that parameter is wrong
    params_all_ok     all parameters match loosely (events with no ground-truth params
                      are always true, and also form their own column)
    full_call_ok      tool_ok and params_all_ok
- Outputs: <cgen-run>/CALLGEN_REPORT.{json,md}

The ro1 batch adds `--readonly-env {appworld,bfcl}` (off by default; off = behavior
unchanged byte for byte): when on, ground-truth labels pass through
readonly_map.collapse() at load time, and the trigger condition gains "argmax is not an
abstention class"; only events where "it fired and the ground truth is a read-only tool"
get scored -- events that fired but whose ground truth is not read-only do not enter the
params_all_ok / full_call_ok denominators, and are counted separately in the new
readonly_excluded key. Existing field names and the three scoring tiers stay unchanged.
A two-way safety check covers both spots: whether ctool run's label_map.json has an
abstention sentinel, and whether cgen run's meta.json has a readonly_env key (missing =
old mode).

Self-fire eval `--self-fire` (off by default; turning it on does not touch any existing
field, it only adds a self_fire block): for use with a cgen run trained with a fire head
-- the threshold point no longer comes from ctool's report; instead cgen's own fire head
decides when to fire.
- Fire score: at each boundary, run prompt=text+call_sep forward once, take the hidden
  state at the prompt's last position and pass it through best/fire_head.pt, sigmoid it
  into a fire probability (takes the same position as the training side, does not look
  at the target string)
- θ_fire is swept on **val** (reusing eval_tool's THETAS grid and RISK_TARGETS
  mechanism), risk is computed from the labels: a wrong fire = it fired but the ground
  truth is not-ready (ready = the ground-truth tool is read-only and all parameters at
  that boundary are found)
- Freeze once on test: replay the fire points using the chosen θ_fire, generate at the
  fire points and score them with the original three tiers, computing parameter /
  whole-call metrics. Ground truth uses the **uncollapsed** original labels, so a wrong
  fire is naturally scored wrong, with no exclusion applied
- Requires --readonly-env (the definition of ready depends on the read-only ground-truth
  table) and a cgen run with fire_head=true

Usage:
  cprobe-env/bin/python pipeline/eval/eval_causal_call.py --env appworld \\
    --ctool-run pipeline/runs/c1_q35_ctool --cgen-run pipeline/runs/c1_q35_cgen \\
    --data pipeline/data/aw_official_v1/q35
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "annotate"))
from rules import (ALF_CALL, AW_CALL, BFCL_CALL,        # noqa: E402
                   split_args_named)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "train"))
import readonly_map                                     # noqa: E402
import share_data                                        # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_tool import RISK_TARGETS, THETAS              # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ops"))
import heartbeat                                         # noqa: E402

MAX_GEN_TOK = 96            # [copied verbatim from train_causal_callgen.py's MAX_GEN_TOK]
FALLBACK_SEP = "\n[CALL] "  # Fallback for when meta.json doesn't have call_sep written (it should have)
TOPK_TOOLS = 10             # Per-tool breakdown table row count


def load_rows(path):
    return [json.loads(l) for l in open(path)]


def replay_fire(rows, probs, theta, nro_id=None):
    """[copied verbatim from eval_extract.py's replay_fire()] the first sample row to cross θ.

    nro_id=None is the old convention; when given an abstention-class id (readonly mode),
    the trigger condition narrows to "conf>=θ and argmax != nro_id", which comes from
    exactly the same source as eval_tool.replay.
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


# ---------------------------------------------------------------- Parsing

def norm(v):
    """[copied verbatim] the annotate side's value normalization: strip(), then strip("\\"'")."""
    return v.strip().strip("\"'")


def split_named_raw(argstr):
    """Copies split_args_named's splitting logic verbatim; only the trailing normalization is
    left to the caller: returns [(key, raw unnormalized string)]. Consistency with
    rules.split_args_named is asserted every time inside parse_call(), to keep the two
    copies of the split logic from drifting apart."""
    vals, buf, depth, q = [], "", 0, None
    for ch in argstr:
        if q:
            buf += ch
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch
            buf += ch
        elif ch in "([{":
            depth += 1
            buf += ch
        elif ch in ")]}":
            depth -= 1
            buf += ch
        elif ch == "," and depth == 0:
            vals.append(buf.strip())
            buf = ""
        else:
            buf += ch
    if buf.strip():
        vals.append(buf.strip())
    out, pos = [], 0
    for v in vals:
        m = re.match(r"(\w+)\s*=\s*(.+)", v, re.S)
        if m:
            out.append((m.group(1), m.group(2).strip()))
        else:
            out.append((f"pos{pos}", v.strip()))
            pos += 1
    return out


def parse_call(code, env):
    """-> (tool_name, [(key, raw_value)]) or (None, []) meaning parse_fail."""
    # alfworld needs an explicit branch: falling back to BFCL_CALL's `(\w+)\(` regex would
    # treat the first "word(" in the generated string as the tool name (for example, taking
    # a `note(` left over from a stray bit of thinking as a tool), silently collapsing
    # tool_ok.
    # ALF_CALL recognizes only the 13 official action names in rules.ALF_TEMPLATES, matching
    # the annotate side.
    name_re = (AW_CALL if env == "appworld"
               else ALF_CALL if env == "alfworld" else BFCL_CALL)
    m = name_re.search(code)
    if not m:
        return None, []
    tool = (f"apis.{m.group(1)}.{m.group(2)}" if env == "appworld"
            else m.group(1))
    i, depth = m.end() - 1, 0
    inner = None
    for j in range(i, len(code)):
        if code[j] == "(":
            depth += 1
        elif code[j] == ")":
            depth -= 1
            if depth == 0:
                inner = code[i + 1: j]
                break
    if inner is None:                      # Parenthesis not closed (generation got truncated)
        return tool, []
    raw = split_named_raw(inner)
    assert [(k, norm(v)) for k, v in raw] == split_args_named(inner), \
        f"split method does not match rules.split_args_named: {inner!r}"
    return tool, raw


def match_params(truth, gen_raw):
    """truth=[{"key","value"}] (values already normalized), gen_raw=[(key, raw unnormalized
    string)].

    Group by key, then compare position by position: a union convention -- extra
    params, missing params, and wrong names are each counted as one wrong instance.
    Returns (n_inst, n_loose_ok, n_strict_ok).
    """
    tmap, gmap = defaultdict(list), defaultdict(list)
    for a in truth:
        tmap[a["key"]].append(a["value"])
    for k, v in gen_raw:
        gmap[k].append(v)
    n = lo = st = 0
    for k in list(tmap) + [k for k in gmap if k not in tmap]:
        tv, gv = tmap.get(k, []), gmap.get(k, [])
        n += max(len(tv), len(gv))
        for i in range(min(len(tv), len(gv))):
            lo += norm(gv[i]) == tv[i]
            st += gv[i] == tv[i]
    return n, lo, st


# ---------------------------------------------------------------- Generation

@torch.no_grad()
def generate(model, tok, prompts, dev, bs, max_len, max_new):
    """Greedy generation: stop at \\n or eos, return the whole call string after .strip()."""
    prev_side, prev_cache = tok.padding_side, model.config.use_cache
    tok.padding_side = "left"                       # Generation must use left padding
    model.config.use_cache = True
    out = []
    heartbeat.emit(0, len(prompts), "item")
    for i in range(0, len(prompts), bs):
        chunk = prompts[i:i + bs]
        enc = tok(chunk, truncation=True,
                  max_length=max(max_len - max_new, 1), padding=True,
                  add_special_tokens=False, return_tensors="pt").to(dev)
        gen = model.generate(**enc, do_sample=False, max_new_tokens=max_new,
                             eos_token_id=tok.eos_token_id,
                             pad_token_id=tok.pad_token_id)
        txt = tok.batch_decode(gen[:, enc["input_ids"].shape[1]:],
                               skip_special_tokens=True)
        out += [t.split("\n")[0].strip() for t in txt]
        print(f"generated {min(i + bs, len(prompts))}/{len(prompts)}",
              flush=True)
        heartbeat.emit(min(i + bs, len(prompts)), len(prompts), "item")
    tok.padding_side, model.config.use_cache = prev_side, prev_cache
    return out


def rate(num, den):
    return round(num / den, 4) if den else None


# ------------------------------------------------------------ Self-fire

def load_ready(data, params, split, ro_set):
    """Read a batch of samples and compute the fire ground truth, ready. Returns (rows,
    stats).

    ready = the ground-truth tool is in the read-only set and all of the sample's
    parameters have found=true (vacuously true when there are zero parameters); params
    that can't be joined are treated as not-ready and counted. Labels are **not
    collapsed** -- the self-fire path never passes through ctool's label space.
    """
    pmap = {}
    for p in load_rows(params / f"{split}.jsonl"):
        pmap[(p["event"], p["sent_idx"])] = p["params"]
    rows = load_rows(data / f"{split}.jsonl")
    st = dict(n=len(rows), n_ready=0, n_readonly=0,
              n_join_miss=0, n_join_miss_with_args=0)
    for r in rows:
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
    n = max(st["n"], 1)
    st["frac_ready"] = round(st["n_ready"] / n, 6)
    st["frac_readonly"] = round(st["n_readonly"] / n, 6)
    st["frac_join_miss"] = round(st["n_join_miss"] / n, 6)
    if st["frac_join_miss"] > 0.01:
        print(f"[self-fire] warning: {split} has {st['n_join_miss']}/{st['n']} "
              f"({st['frac_join_miss']:.1%}) samples that cannot be joined in params,"
              f"treated as not-ready", flush=True)
    return rows, st


@torch.no_grad()
def score_fire(model, fire, tok, rows, sep, dev, bs, max_len, max_new):
    """Fire probability at each boundary. prompt=text+sep, right padding, take the hidden
    state at the prompt's last position.

    The truncation convention is identical to the generate() path (max_length = max_len
    - max_new), so "which prefix decides whether to fire" and "which prefix generation
    starts from" are the same thing.
    """
    prev_side, prev_cache = tok.padding_side, model.config.use_cache
    tok.padding_side = "right"                      # Locate the last position using attention_mask
    model.config.use_cache = False
    out = torch.zeros(len(rows))
    for i in range(0, len(rows), bs):
        chunk = [r["text"] + sep for r in rows[i:i + bs]]
        enc = tok(chunk, truncation=True,
                  max_length=max(max_len - max_new, 1), padding=True,
                  add_special_tokens=False, return_tensors="pt").to(dev)
        h = model(input_ids=enc["input_ids"],
                  attention_mask=enc["attention_mask"], use_cache=False,
                  output_hidden_states=True).hidden_states[-1]
        last = enc["attention_mask"].sum(1) - 1
        lg = fire(h[torch.arange(h.size(0), device=h.device), last].float())
        out[i:i + len(chunk)] = torch.sigmoid(lg.squeeze(-1).float()).cpu()
        if (i // bs) % 50 == 0:
            print(f"fire-scored {i}/{len(rows)}", flush=True)
    tok.padding_side, model.config.use_cache = prev_side, prev_cache
    return out


def replay_fire_head(rows, probs, theta, gate=None):
    """Fire-head replay: for each event, take the first boundary where fire_prob>=θ (and
    gate is true).

    Structurally identical to replay_fire, only the criterion is swapped for the fire
    probability; gate[i] is used on the mext side for "argmax is not an abstention
    class", here it is always None.
    """
    ev = defaultdict(list)
    for i, (r, p) in enumerate(zip(rows, probs)):
        ev[r["event"]].append((r["sent_idx"], i, r, float(p)))
    out = {}
    for k, items in ev.items():
        items.sort(key=lambda x: x[0])
        rec = dict(fired=False, ready=False, sent_idx=None, row=None, conf=None)
        for _, i, r, p in items:
            if p >= theta and (gate is None or gate[i]):
                rec.update(fired=True, ready=bool(r["ready"]),
                           sent_idx=r["sent_idx"], row=r, conf=round(p, 4))
                break
        out[k] = rec
    return out


def agg_fire(recs):
    """Fire head's coverage / accuracy / wrong-fire rate; formulas are structurally identical to eval_tool.agg."""
    n = len(recs)
    fired = [r for r in recs if r["fired"]]
    return dict(n=n, n_fired=len(fired),
                coverage=round(len(fired) / max(n, 1), 4),
                fire_acc=round(sum(r["ready"] for r in fired)
                               / max(len(fired), 1), 4),
                wrong_fire_rate=round(sum(1 for r in fired if not r["ready"])
                                      / max(n, 1), 4))


def pick_theta(sweep):
    """[Same mechanism as eval_tool's θ selection] under the risk constraint, take the tier with maximum coverage."""
    chosen = {}
    for risk in RISK_TARGETS:
        ok = [(th, a) for th, a in sweep
              if a["fire_acc"] >= 1 - risk and a["coverage"] > 0]
        chosen[risk] = (max(ok, key=lambda x: x[1]["coverage"])[0]
                        if ok else None)
    return chosen


# ------------------------------------------------------------ Scoring

def score_points(keys, rowof, gens, env, n_samples=20):
    """Score at the given threshold/fire point. keys and gens are in the same order,
    rowof[k] gives the ground-truth row for that point.

    [Scoring convention preserved verbatim] tool name / loose-strict parameters /
    whole-call three tiers, none of them change.
    """
    per_ev, samples = {}, []
    n_par = n_lo = n_st = 0
    for k, g in zip(keys, gens):
        row = rowof[k]
        truth = row.get("args_named") or []
        tool, raw = parse_call(g, env)
        n, lo, st = match_params(truth, raw)
        n_par += n
        n_lo += lo
        n_st += st
        noparam = not truth
        rec = dict(
            event=k, label=row["label"], label_call=row.get("label_call"),
            gen_call=g, parse_fail=tool is None,
            tool_ok=(tool == row["label"]),
            params_all_ok=(True if noparam else (n > 0 and lo == n)),
            params_all_ok_strict=(True if noparam else (n > 0 and st == n)),
            noparam=noparam,
            exact_call_ok=(g == row.get("label_call")))
        rec["full_call_ok"] = rec["tool_ok"] and rec["params_all_ok"]
        per_ev[k] = rec
        if len(samples) < n_samples:
            samples.append(dict(event=k, truth=row.get("label_call"),
                                gen=g, full_call_ok=rec["full_call_ok"]))
    return per_ev, samples, n_par, n_lo, n_st


def self_fire_block(args, cgen, data, params, meta, model, tok, sep,
                    max_len, dev, ro_set):
    """Self-fire: sweep θ_fire on val -> freeze once on test -> generate and score at the fire points."""
    if not meta.get("fire_head"):
        raise SystemExit(
            f"--self-fire requires the cgen run to be trained with a fire head: {cgen/'best'/'meta.json'} "
            "does not have \"fire_head\": true. Train it with train_causal_callgen.py --fire-head.")
    fp = cgen / "best" / "fire_head.pt"
    if not fp.exists():
        raise SystemExit(f"--self-fire cannot find fire-head weights at {fp}")
    sd = torch.load(fp, map_location="cpu")
    fire = torch.nn.Linear(sd["weight"].shape[1], 1)
    fire.load_state_dict(sd)
    fire = fire.float().to(dev).eval()
    bs = args.fire_bs or args.bs

    val_rows, val_st = load_ready(data, params, "val", ro_set)
    test_rows, test_st = load_ready(data, params, "test", ro_set)

    # Sweep θ_fire on val (grid and risk targets reuse eval_tool's THETAS/RISK_TARGETS)
    pv = score_fire(model, fire, tok, val_rows, sep, dev, bs, max_len,
                    args.max_new_tokens)
    sweep = [(th, agg_fire(list(replay_fire_head(val_rows, pv, th).values())))
             for th in THETAS]
    chosen = pick_theta(sweep)
    th_fire = chosen.get(args.risk)
    if th_fire is None:
        print(f"[self-fire] none of the 20 θ brackets on val push risk down to ≤{args.risk};"
              f"chosen={chosen}, this section only outputs the sweep table.", flush=True)
        return dict(theta_fire=None, risk=args.risk,
                    chosen_theta_fire={str(k): v for k, v in chosen.items()},
                    theta_sweep_val=[dict(theta=th, **a) for th, a in sweep],
                    ready_stats=dict(val=val_st, test=test_st),
                    val=None, test=None, scored=None, on_ready=None)

    # Freeze once on test
    pt = score_fire(model, fire, tok, test_rows, sep, dev, bs, max_len,
                    args.max_new_tokens)
    rec = replay_fire_head(test_rows, pt, th_fire)
    keys = [k for k in dict.fromkeys(r["event"] for r in test_rows)
            if rec[k]["fired"]]
    if args.limit:
        keys = keys[:args.limit]
    # Scoring uses the **uncollapsed** original labels (the load_ready path never collapses
    # at all): a wrong fire is naturally scored wrong, with no exclusion applied
    rowof = {k: rec[k]["row"] for k in keys}
    gens = generate(model, tok, [rowof[k]["text"] + sep for k in keys], dev,
                    args.bs, max_len, args.max_new_tokens) if keys else []
    per_ev, samples, n_par, n_lo, n_st = score_points(keys, rowof, gens,
                                                      args.env)

    def block(ks):
        n = len(ks)
        c = lambda f: sum(1 for k in ks if per_ev[k][f])   # noqa: E731
        return dict(n=n, parse_fail_rate=rate(c("parse_fail"), n),
                    tool_ok=rate(c("tool_ok"), n),
                    params_all_ok=rate(c("params_all_ok"), n),
                    params_all_ok_strict=rate(c("params_all_ok_strict"), n),
                    full_call_ok=rate(c("full_call_ok"), n),
                    exact_call_ok=rate(c("exact_call_ok"), n),
                    noparam_events=c("noparam"))
    ready_keys = [k for k in keys if rec[k]["ready"]]
    return dict(
        theta_fire=th_fire, risk=args.risk,
        chosen_theta_fire={str(k): v for k, v in chosen.items()},
        theta_sweep_val=[dict(theta=th, **a) for th, a in sweep],
        ready_stats=dict(val=val_st, test=test_st),
        val=dict(theta=th_fire,
                 **agg_fire(list(replay_fire_head(val_rows, pv,
                                                  th_fire).values()))),
        test=agg_fire(list(rec.values())),
        scored=dict(n_param_instances=n_par,
                    param_acc_loose=rate(n_lo, n_par),
                    param_acc_strict=rate(n_st, n_par), **block(keys)),
        on_ready=block(ready_keys),
        samples=samples)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", required=True,
                    choices=["tales", "appworld", "bfcl", "alfworld"])
    ap.add_argument("--ctool-run", required=True,
                    help="causal classification-head run dir (provides the threshold: temperature/θ/logits_test.pt)")
    ap.add_argument("--cgen-run", required=True, help="call-generation run dir")
    ap.add_argument("--data", required=True,
                    help="data dir <data_out> (directly contains test.jsonl)")
    ap.add_argument("--risk", type=float, default=0.05)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--bs", type=int, default=8, help="generation batch size")
    ap.add_argument("--max-new-tokens", type=int, default=MAX_GEN_TOK)
    ap.add_argument("--limit", type=int, default=0, help="truncate to the first N trigger events (smoke test)")
    ap.add_argument("--readonly-env", default=None,
                    choices=list(readonly_map.READONLY_ENVS),
                    help="read-only-tools + abstain-class mode (off by default); when on, the ground truth is "
                         "collapsed, the trigger condition adds \"argmax is not the abstain class\", and "
                         "only trigger events whose ground truth is a read-only "
                         "tool are scored")
    ap.add_argument("--params", default=None,
                    help="parameter interval-label dir (default <data>/params); --self-fire uses it to compute ready")
    ap.add_argument("--self-fire", action="store_true",
                    help="self-fire eval: θ_fire is swept on val and frozen once on test,"
                         "the threshold is set by cgen's own fire head, not ctool's θ."
                         "only adds the self_fire block, none of the old fields are touched")
    ap.add_argument("--fire-bs", type=int, default=0,
                    help="batch size for fire scoring (0 = reuse --bs)")
    ap.add_argument("--overlong", default="left",
                    choices=["left", "skip", "drop-event"],
                    help="three ways to handle an overlong trigger-event full text/prompt (spec 16.2);"
                         "default left (behavior is byte-for-byte unchanged from before this flag was added)."
                         "describes only the main path, --self-fire is not affected")
    args = ap.parse_args()

    ctool, cgen = Path(args.ctool_run), Path(args.cgen_run)
    data = Path(args.data)
    params = Path(args.params) if args.params else data / "params"
    dev = args.device

    if args.self_fire and not args.readonly_env:
        raise SystemExit(
            "--self-fire must be passed together with --readonly-env: the definition of fire "
            "ground truth ready depends on that environment's read-only ground-truth table.")

    rep_cls = json.loads((ctool / "REPLAY_REPORT.json").read_text())
    T = rep_cls["temperature"]
    theta = rep_cls["chosen_theta"].get(str(args.risk))
    if theta is None:
        if not args.self_fire:
            raise SystemExit(f"the classification-head report has no θ for risk={args.risk}:"
                             f"{rep_cls['chosen_theta']}")
        print(f"[self-fire] the classification-head report has no θ for risk={args.risk}"
              f"({rep_cls['chosen_theta']}), the whole legacy-mode block is skipped, only self_fire is output.",
              flush=True)
    old_mode = theta is not None

    # 1) Threshold point: the filtering logic matches eval_tool line for line, keeping the
    # order in sync with logits_test.pt
    label2id = json.loads((ctool / "best" / "label_map.json").read_text())
    meta = json.loads((cgen / "best" / "meta.json").read_text())

    # Cell safety check: this script only consumes outputs from the cgen cell. A cparam run
    # was only trained to "write the parameter segment"; feeding it in would generate a
    # string with no tool name, and scoring would collapse completely while running through
    # without ever raising an error.
    if meta.get("param_only"):
        raise SystemExit(
            f"{cgen / 'best' / 'meta.json'} carries \"param_only\": true -- "
            "this is output from the cparam cell. Evaluate parameter-generation runs with eval_causal_param.py.")

    # Three-way data cross-check: the data used to train cgen, the --data argument, and the
    # data used to train ctool must be the same directory. When two base-model tracks run in
    # parallel, cross-feeding like pairing p1b06's ctool with p1b17's cgen will silently pass
    # every other safety check.
    ctool_meta = json.loads((ctool / "best" / "meta.json").read_text())
    trio = {"--data value": str(data),
            "cgen meta.data": meta.get("data"),
            "ctool meta.data": ctool_meta.get("data")}
    canon = {k: (str(Path(v).resolve()) if v else None) for k, v in trio.items()}
    if len(set(canon.values())) != 1:
        raise SystemExit("three-way data cross-check mismatch, hard stop:\n" + "\n".join(
            f"  {k} = {trio[k]!r} -> {canon[k]!r}" for k in trio))

    # Two-way safety check against cross-contamination: ctool's label_map has an abstention
    # sentinel, cgen's meta has a readonly_env key (missing = old mode); both must hold
    # together with --readonly-env
    has_sentinel = readonly_map.NON_READONLY in label2id
    meta_ro = meta.get("readonly_env")
    if has_sentinel != bool(args.readonly_env) or \
            (meta_ro is not None) != bool(args.readonly_env):
        raise SystemExit(
            f"readonly fuse mismatch: {ctool / 'best' / 'label_map.json'} "
            f"{'has' if has_sentinel else 'lacks'} the abstain sentinel "
            f"{readonly_map.NON_READONLY!r};"
            f"{cgen / 'best' / 'meta.json'}'s readonly_env key "
            f"{'= ' + repr(meta_ro) if meta_ro is not None else 'missing (= legacy mode)'};"
            f"while --readonly-env "
            f"{'was passed ' + str(args.readonly_env) if args.readonly_env else 'was not passed'}."
            "all three must hold together or fail together -- a run trained in readonly mode can only "
            "be evaluated with --readonly-env, a legacy-settings run can only be evaluated without it.")
    if args.readonly_env and isinstance(meta_ro, str) \
            and meta_ro != args.readonly_env:
        raise SystemExit(
            f"readonly fuse: the cgen run was trained with {meta_ro!r},"
            f"but is being evaluated with {args.readonly_env!r}'s ground-truth table -- environment mismatch, hard stop.")
    ro_set = nro_id = None
    if args.readonly_env:
        ro_set = readonly_map.load_readonly_set(args.readonly_env)
        nro_id = label2id[readonly_map.NON_READONLY]

    raw_rows = load_rows(data / "test.jsonl")
    if ro_set is not None:
        readonly_map.audit([r["label"] for r in raw_rows],
                           readonly_map.load_table(args.readonly_env),
                           "eval_causal_call test")
        for r in raw_rows:
            r["label"] = readonly_map.collapse(r["label"], ro_set)
    rows = [r for r in raw_rows if r["label"] in label2id]
    for r in rows:
        r["y"] = label2id[r["label"]]
    fired, keys, n_fired, n_ro_excluded = {}, [], 0, 0
    overlong_counts = dict(n_left_truncated=0, n_skipped_rows=0,
                          n_dropped_events=0, n_excluded_by_ctool=0)
    ev_row_idx = defaultdict(list)
    for i, r in enumerate(rows):
        ev_row_idx[r["event"]].append(i)
    if old_mode:
        logits = torch.load(ctool / "logits_test.pt", map_location="cpu")
        assert len(rows) == logits.shape[0], (len(rows), logits.shape)

        # Rows excluded by ctool are not allowed as threshold-point candidates (spec 16.2's
        # connecting section): read excluded_idx up front, and pick the threshold point only
        # from the remaining rows -- zero logits through softmax give a uniform distribution,
        # which θ only blocks naturally when θ<=1/n_labels, so this cannot be relied on as a
        # safeguard.
        # When all of an event's candidate rows are excluded, it has no threshold point, is not
        # scored, and is counted in n_excluded_by_ctool.
        ctool_lmeta = ctool / "logits_test.meta.json"
        excluded_rows = set()
        if ctool_lmeta.exists():
            excluded_rows = set(
                json.loads(ctool_lmeta.read_text()).get("excluded_idx", []))
        overlong_counts["n_excluded_by_ctool"] = sum(
            1 for idxs in ev_row_idx.values()
            if all(i in excluded_rows for i in idxs))
        cand_idx = [i for i in range(len(rows)) if i not in excluded_rows]
        cand_rows = [rows[i] for i in cand_idx]
        cand_probs = torch.softmax(logits[cand_idx] / T, -1)
        fired = replay_fire(cand_rows, cand_probs, theta, nro_id)

        keys = [k for k in dict.fromkeys(r["event"] for r in cand_rows)
                if fired[k]["fired"]]
        n_fired = len(keys)
        # Readonly mode: events that fired but whose ground truth is not read-only are not
        # scored (they do not enter any denominator), and are counted separately
        if ro_set is not None:
            keep = [k for k in keys
                    if fired[k]["label"] != readonly_map.NON_READONLY]
            n_ro_excluded = len(keys) - len(keep)
            keys = keep

    # 2) Generation: CALL_SEP is read from the training-side meta.json (not hardcoded)
    sep = meta.get("call_sep", FALLBACK_SEP)
    max_len = meta.get("max_len", 4096)
    tok = AutoTokenizer.from_pretrained(cgen / "best")
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    tok.truncation_side = "left"                    # Keep the tail of the thinking text
    tok.padding_side = "right"
    model = AutoModelForCausalLM.from_pretrained(
        cgen / "best",
        dtype=torch.bfloat16 if str(dev).startswith("cuda") else torch.float32
    ).to(dev).eval()

    if old_mode:
        # --overlong filtering (after the tokenizer loads; after the readonly exclusion, before
        # --limit -- spec 16.2 fixes this three-step order). ctool exclusion was already handled
        # at the threshold-point-picking step (overlong_counts["n_excluded_by_ctool"] above), so
        # an empty set is passed here, doing only prompt-length filtering -- every event in keys
        # is already guaranteed to have at least one candidate row not excluded by ctool, so
        # select_keys' exclusion branch can never fire here.
        keys_rowmap = {k: ev_row_idx[k] for k in keys}
        prompt_len = {k: len(tok(fired[k]["row"]["text"] + sep,
                                add_special_tokens=False,
                                truncation=False)["input_ids"])
                     for k in keys}
        n_full = {}
        if args.overlong == "drop-event":
            key_set = set(keys)
            # spec 16.2: for the full text, use share_data's rule (don't filter rows by ctool's
            # vocabulary, take the text of the row with the largest sent_idx) -- pass raw_rows, not
            # the filtered rows, otherwise this amounts to applying ctool's filtering convention.
            full_texts = share_data.event_full_texts(
                [r for r in raw_rows if r["event"] in key_set])
            n_full = {k: share_data.n_full_tokens(tok, full_texts[k])
                     for k in keys}
        keys, length_counts = share_data.select_keys(
            args.overlong, keys_rowmap, n_full, prompt_len, set(),
            max_len, args.max_new_tokens)
        assert length_counts["n_excluded_by_ctool"] == 0, (
            "every event in keys should have at least one candidate row that ctool did not exclude")
        overlong_counts.update(n_left_truncated=length_counts["n_left_truncated"],
                              n_skipped_rows=length_counts["n_skipped_rows"],
                              n_dropped_events=length_counts["n_dropped_events"])
        if args.limit:
            keys = keys[:args.limit]

    prompts = [fired[k]["row"]["text"] + sep for k in keys]
    gens = generate(model, tok, prompts, dev, args.bs, max_len,
                    args.max_new_tokens) if prompts else []

    # 3) Scoring
    per_ev, samples, n_par, n_lo, n_st = score_points(
        keys, {k: fired[k]["row"] for k in keys}, gens, args.env)

    n = len(per_ev)
    cnt = lambda f: sum(1 for r in per_ev.values() if r[f])   # noqa: E731

    by_tool = defaultdict(lambda: dict(n=0, tool_ok=0, params_all_ok=0,
                                       full_call_ok=0))
    for r in per_ev.values():
        b = by_tool[r["label"]]
        b["n"] += 1
        b["tool_ok"] += r["tool_ok"]
        b["params_all_ok"] += r["params_all_ok"]
        b["full_call_ok"] += r["full_call_ok"]
    top = sorted(by_tool.items(), key=lambda kv: -kv[1]["n"])[:TOPK_TOOLS]

    n_ev = len({r["event"] for r in rows})
    out = dict(
        env=args.env, ctool_run=str(ctool), cgen_run=str(cgen),
        risk=args.risk, theta=theta, temperature=T, call_sep=sep,
        max_new_tokens=args.max_new_tokens, limit=args.limit,
        n_events_test=n_ev, overlong_mode=args.overlong,
        n_left_truncated=overlong_counts["n_left_truncated"],
        n_skipped_rows=overlong_counts["n_skipped_rows"],
        n_dropped_events=overlong_counts["n_dropped_events"],
        n_excluded_by_ctool=overlong_counts["n_excluded_by_ctool"])
    if old_mode:
        out.update(
            n_events_fired=n_fired, n_events_scored=n,
            parse_fail=cnt("parse_fail"),
            parse_fail_rate=rate(cnt("parse_fail"), n),
            tool_ok=rate(cnt("tool_ok"), n),
            params_all_ok=rate(cnt("params_all_ok"), n),
            params_all_ok_strict=rate(cnt("params_all_ok_strict"), n),
            full_call_ok=rate(cnt("full_call_ok"), n),
            exact_call_ok=rate(cnt("exact_call_ok"), n),
            noparam_events=cnt("noparam"), noparam_rate=rate(cnt("noparam"), n),
            n_param_instances=n_par,
            param_acc_loose=rate(n_lo, n_par),
            param_acc_strict=rate(n_st, n_par),
            by_tool={k: dict(n=v["n"], tool_ok=rate(v["tool_ok"], v["n"]),
                             params_all_ok=rate(v["params_all_ok"], v["n"]),
                             full_call_ok=rate(v["full_call_ok"], v["n"]))
                     for k, v in top},
            samples=samples)
    if ro_set is not None:
        out["readonly_env"] = args.readonly_env
        out["readonly_excluded"] = n_ro_excluded

    # ---------------- Self-fire (--self-fire): sweep θ_fire on val, freeze once on test
    sf = None
    if args.self_fire:
        sf = self_fire_block(args, cgen, data, params, meta, model, tok, sep,
                             max_len, dev, ro_set)
        out["self_fire"] = sf
    (cgen / "CALLGEN_REPORT.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1))

    md = [f"# trigger-time call-generation eval -- {args.env}",
          f"- overlong_mode={out['overlong_mode']}"
          f"(n_left_truncated={out['n_left_truncated']}, "
          f"n_skipped_rows={out['n_skipped_rows']}, "
          f"n_dropped_events={out['n_dropped_events']}, "
          f"n_excluded_by_ctool={out['n_excluded_by_ctool']})"]
    if not old_mode:
        md += [f"- classification head {ctool.name} has no solvable θ at risk={args.risk},"
               "the whole legacy-mode block is skipped; this file has only the self-fire section."]
    md += ([
          f"- classification head {ctool.name} / generation head {cgen.name}; risk≤{args.risk} → "
          f"θ={theta} (temperature T={T})",
          f"- test events {n_ev}, triggered {n_fired}, counted this time {n}"
          + (f"(--limit {args.limit})" if args.limit else ""),
          f"- join separator call_sep={sep!r} (read from the generation head's meta.json);"
          f"greedy max_new_tokens={args.max_new_tokens}, stop on newline or eos",
          "",
          "| metric | value |", "|---|---|",
          f"| parse failure rate | {out['parse_fail_rate']} |",
          f"| tool-name accuracy | {out['tool_ok']} |",
          f"| all-params-correct rate (loose) | {out['params_all_ok']} |",
          f"| all-params-correct rate (strict) | {out['params_all_ok_strict']} |",
          f"| full-call accuracy | {out['full_call_ok']} |",
          f"| exact whole-string hit (compare to the training-side val_exact_call) | {out['exact_call_ok']} |",
          f"| share of no-param events | {out['noparam_rate']}({out['noparam_events']}/{n}) |",
          f"| parameter instance count | {n_par} |",
          f"| parameter-level accuracy (loose/strict) | {out['param_acc_loose']} / "
          f"{out['param_acc_strict']} |",
          "",
          f"## per-tool breakdown (top {TOPK_TOOLS} by event count)",
          "| tool | event count | tool name correct | all params correct | full call correct |",
          "|---|---|---|---|---|"] if old_mode else [])
    if old_mode:
        for k, v in top:
            md.append(f"| {k} | {v['n']} | {rate(v['tool_ok'], v['n'])} | "
                      f"{rate(v['params_all_ok'], v['n'])} | "
                      f"{rate(v['full_call_ok'], v['n'])} |")
    md += ["", "## scoring settings",
           "- parameters are compared one by one: loose = values equal after normalization (strip then strip quotes);"
           "strict = the raw strings equal character for character;"
           "keys are compared by union, extra param / missing param / wrong name each count as one wrong instance.",
           "- in the all-params-correct rate, events whose ground truth has no params are always counted correct"
           "(their share is listed separately);"
           "full call correct = tool name correct and all params correct (loose).",
           "- the threshold comes from exactly the same replay as ctool, so this table can be read side by side with"
           "the same model's mext-cell EXTRACT_REPORT: both ask whether the whole call can be assembled"
           "at the moment of triggering."]
    if ro_set is not None and old_mode:
        md += ["", f"## read-only mode (--readonly-env {args.readonly_env})",
               f"- abstain class {readonly_map.NON_READONLY} (label id {nro_id});"
               "the trigger condition adds \"argmax is not the abstain class\", ground-truth labels are collapsed",
               f"- events that triggered but whose ground truth is not read-only, and so are not scored: {n_ro_excluded}"
               f"(readonly_excluded); every column in this table has the remaining {n} "
               "ground-truth-read-only trigger events as its denominator"]
    if sf is not None and sf["test"] is None:
        md += ["", f"## self-fire (--self-fire, risk≤{args.risk})",
               f"- none of the 20 θ brackets on val push risk down to ≤{args.risk}"
               f"(chosen={sf['chosen_theta_fire']}), test was not evaluated,"
               "only the self_fire.theta_sweep_val sweep table is kept."]
    elif sf is not None:
        a = sf["test"]
        md += ["", f"## self-fire (--self-fire, risk≤{args.risk})",
               f"- θ_fire swept on val to {sf['theta_fire']}"
               f"(val coverage {sf['val']['coverage']} / "
               f"fire accuracy {sf['val']['fire_acc']}); frozen once for test",
               "- fire ground truth ready = tool is read-only and every parameter at that boundary is found;"
               "wrong fire = fired but ground truth is not-ready",
               f"- test events {a['n']}, fired {a['n_fired']},"
               f"coverage {a['coverage']}, fire accuracy {a['fire_acc']},"
               f"wrong-fire rate {a['wrong_fire_rate']}",
               "",
               "| metric (denominator = fire points) | all fire points | those with ground truth ready |",
               "|---|---|---|",
               f"| event count | {sf['scored']['n']} | {sf['on_ready']['n']} |",
               f"| parse failure rate | {sf['scored']['parse_fail_rate']} | "
               f"{sf['on_ready']['parse_fail_rate']} |",
               f"| tool-name accuracy | {sf['scored']['tool_ok']} | "
               f"{sf['on_ready']['tool_ok']} |",
               f"| all-params-correct rate (loose) | {sf['scored']['params_all_ok']} | "
               f"{sf['on_ready']['params_all_ok']} |",
               f"| full-call accuracy | {sf['scored']['full_call_ok']} | "
               f"{sf['on_ready']['full_call_ok']} |",
               "",
               "- the left column excludes no fire points: a wrong fire is scored against the real (uncollapsed) label,"
               "so it is naturally counted wrong -- this is the true score for \"letting the probe decide"
               "for itself when to fire.\"",
               "- the right column looks only at fire points whose ground truth is ready, for reading side by side with the legacy-mode table."]
    (cgen / "CALLGEN_REPORT.md").write_text("\n".join(md) + "\n")
    heartbeat.emit(n, n, "item", status="done")
    if old_mode:
        print(json.dumps({k: out[k] for k in
                          ("n_events_scored", "parse_fail_rate", "tool_ok",
                           "params_all_ok", "full_call_ok")},
                         ensure_ascii=False, indent=1))
    if sf is not None and sf["test"] is not None:
        print(json.dumps(dict(theta_fire=sf["theta_fire"], **sf["test"],
                              full_call_ok=sf["scored"]["full_call_ok"]),
                         ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
