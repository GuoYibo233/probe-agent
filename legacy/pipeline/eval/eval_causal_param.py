"""Trigger-time parameter generation eval (new pipeline, cparam cell): at ctool's
threshold point, feed the tool name together with the opening parenthesis into the
cparam model, have it write only the parameters, then reassemble the whole call and
score it.

Read alongside eval_causal_call.py (the cgen cell): the threshold point definition on
both sides comes from exactly the same source (copied verbatim from
eval_extract.py's replay_fire()), and the scoring convention is also copied verbatim --
the only difference is "where the tool name comes from": on that side the generating
model writes it itself, on this side it is given directly by the input.

This script runs **two conventions** in one pass, generating once for the same batch of
threshold points each time:
- gt_tool   the tool name in the prompt = the ground-truth label; this measures the
            model's pure ability to fill in parameters
- pred_tool the tool name in the prompt = ctool's argmax prediction on that threshold row
            (name looked up through label_map); this measures the real performance of
            system B (ctool + cparam)
The difference between the two blocks = the loss from ctool picking the wrong tool. The
matrix (summarize_matrix.py) takes only the pred_tool block -- that is the real number
for system B.

- Threshold point: get temperature T and chosen_theta[--risk] from --ctool-run's
  REPLAY_REPORT.json, replay on the test stack with logits_test.pt, and for each event
  take the first sample row that crosses θ
- Generation: prompt = trigger-sample text + CALL_SEP + <tool name> + "(", CALL_SEP is
  read from the `call_sep` field of --cparam-run/best/meta.json (shares the same
  convention as the training-side string concatenation, not hardcoded); greedy,
  max_new_tokens=96, stop on eos, then cut at the first \\n, then .strip() (matches the
  training-side val_exact_params convention). Temporarily switch padding_side to left
  during generation
- Scoring: first reassemble the full call string = <tool name> + "(" + the generated
  string, then run the exact same parse_call / match_params as cgen:
    tool_ok           parsed tool name == label (the gt_tool block records this as-is
                      and it is always true; the pred_tool block is equivalent to
                      "predicted name == ground-truth name")
    per parameter     loose = equal after normalization; strict = equal on the raw,
                      unnormalized string; a key mismatch (extra param, missing param,
                      wrong name) = that parameter is wrong
    params_all_ok     all parameters match loosely (events with no ground-truth params
                      are always true, and also form their own column)
    full_call_ok      tool_ok and params_all_ok
    exact_call_ok     the reassembled string == label_call
- Outputs: <cparam-run>/PARAM_REPORT.{json,md}

Readonly mode `--readonly-env {appworld,bfcl}` (off by default; off = old convention):
copies the semantics of the cgen eval verbatim -- ground-truth labels pass through
readonly_map.collapse() at load time, and the trigger condition gains "argmax is not an
abstention class"; only events where "it fired and the ground truth is a read-only tool"
get scored, events that fired but whose ground truth is not read-only do not enter any
denominator, and are counted separately in readonly_excluded. The two conventions share
the same batch of threshold points, so this applies to both blocks at once.
A two-way safety check covers both spots: whether ctool run's label_map.json has an
abstention sentinel, and whether cparam run's meta.json has a readonly_env key (missing =
old mode).

Usage:
  cprobe-env/bin/python pipeline/eval/eval_causal_param.py --env appworld \\
    --ctool-run pipeline/runs/c2_q35_ctool --cparam-run pipeline/runs/c2_q35_cparam \\
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

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ops"))
import heartbeat                                         # noqa: E402

MAX_GEN_TOK = 96            # [copied verbatim from train_causal_param.py's MAX_GEN_TOK]
FALLBACK_SEP = "\n[CALL] "  # Fallback for when meta.json doesn't have call_sep written (it should have)
TOPK_TOOLS = 10             # Per-tool breakdown table row count


def load_rows(path):
    return [json.loads(l) for l in open(path)]


def replay_fire(rows, probs, theta, nro_id=None):
    """[copied verbatim from eval_causal_call.py's replay_fire()] the first sample row to
    cross θ.

    Records one more field than the cgen version, `pred` (that row's argmax class id) --
    the pred_tool convention needs it to look up the tool name. nro_id=None is the old
    convention; when given an abstention-class id (readonly mode), the trigger condition
    narrows to "conf>=θ and argmax != nro_id", which comes from exactly the same source
    as eval_tool.replay.
    """
    ev = defaultdict(list)
    for r, p in zip(rows, probs):
        ev[r["event"]].append((r["sent_idx"], r, p))
    out = {}
    for k, items in ev.items():
        items.sort(key=lambda x: x[0])
        rec = dict(fired=False, ok=False, sent_idx=None, row=None, pred=None,
                   label=items[0][1]["label"])
        for _, r, p in items:
            conf, pred = float(p.max()), int(p.argmax())
            if conf >= theta and (nro_id is None or pred != nro_id):
                rec.update(fired=True, ok=(pred == r["y"]),
                           sent_idx=r["sent_idx"], row=r, pred=pred)
                break
        out[k] = rec
    return out


# ---------------------------------------------------------------- Parsing

def norm(v):
    """[copied verbatim] the annotate side's value normalization: strip(), then strip("\\"'")."""
    return v.strip().strip("\"'")


def split_named_raw(argstr):
    """[copied verbatim from eval_causal_call.split_named_raw] copies split_args_named's
    splitting logic verbatim, leaving only the trailing normalization to the caller:
    returns [(key, raw unnormalized string)]. Consistency with rules.split_args_named is
    asserted every time inside parse_call(), to keep the two copies of the split logic
    from drifting apart."""
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
    """[copied verbatim from eval_causal_call.parse_call] -> (tool_name, [(key, raw_value)])
    or (None, []) meaning parse_fail."""
    # alfworld needs an explicit branch: falling back to BFCL_CALL's `(\w+)\(` regex would
    # treat the first "word(" in the string as the tool name, silently collapsing tool_ok.
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
    """[copied verbatim from eval_causal_call.match_params] truth=[{"key","value"}] (values
    already normalized), gen_raw=[(key, raw unnormalized string)].

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
def generate(model, tok, prompts, dev, bs, max_len, max_new, tag=""):
    """Greedy generation: stop at \\n or eos, return the parameter string after .strip()
    (excluding the tool name and opening parenthesis)."""
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
        print(f"[{tag}] generated {min(i + bs, len(prompts))}/{len(prompts)}",
              flush=True)
        heartbeat.emit(min(i + bs, len(prompts)), len(prompts), "item")
    tok.padding_side, model.config.use_cache = prev_side, prev_cache
    return out


def rate(num, den):
    return round(num / den, 4) if den else None


# ------------------------------------------------------------ Scoring

def score_points(keys, rowof, given, gens, env, n_samples=20):
    """Score at the threshold point. keys and gens are in the same order, rowof[k] gives the
    ground-truth row for that point, given[k] gives the tool name fed into the prompt.

    [Scoring convention preserved verbatim from eval_causal_call.score_points] tool name
    / loose-strict parameters / whole-call three tiers, none of them change; the only
    difference is that the tool name and opening parenthesis are reassembled back on
    before scoring.
    """
    per_ev, samples = {}, []
    n_par = n_lo = n_st = 0
    for k, g in zip(keys, gens):
        row = rowof[k]
        truth = row.get("args_named") or []
        full = given[k] + "(" + g          # Reassemble the full call string
        tool, raw = parse_call(full, env)
        n, lo, st = match_params(truth, raw)
        n_par += n
        n_lo += lo
        n_st += st
        noparam = not truth
        rec = dict(
            event=k, label=row["label"], label_call=row.get("label_call"),
            given_tool=given[k], gen_params=g, gen_call=full,
            parse_fail=tool is None,
            tool_ok=(tool == row["label"]),
            given_tool_ok=(given[k] == row["label"]),
            params_all_ok=(True if noparam else (n > 0 and lo == n)),
            params_all_ok_strict=(True if noparam else (n > 0 and st == n)),
            noparam=noparam,
            exact_call_ok=(full == row.get("label_call")))
        rec["full_call_ok"] = rec["tool_ok"] and rec["params_all_ok"]
        per_ev[k] = rec
        if len(samples) < n_samples:
            samples.append(dict(event=k, truth=row.get("label_call"),
                                gen=full, full_call_ok=rec["full_call_ok"]))
    return per_ev, samples, n_par, n_lo, n_st


def block(per_ev, keys, theta, n_par, n_lo, n_st, samples):
    """All the numbers for one convention. theta / n_events_scored / params_all_ok /
    full_call_ok are the four fields summarize_matrix reads from the pred_tool block --
    do not rename them."""
    n = len(keys)
    c = lambda f: sum(1 for k in keys if per_ev[k][f])   # noqa: E731
    by_tool = defaultdict(lambda: dict(n=0, tool_ok=0, params_all_ok=0,
                                       full_call_ok=0))
    for k in keys:
        r = per_ev[k]
        b = by_tool[r["label"]]
        b["n"] += 1
        b["tool_ok"] += r["tool_ok"]
        b["params_all_ok"] += r["params_all_ok"]
        b["full_call_ok"] += r["full_call_ok"]
    top = sorted(by_tool.items(), key=lambda kv: -kv[1]["n"])[:TOPK_TOOLS]
    return dict(
        theta=theta, n_events_scored=n,
        parse_fail=c("parse_fail"), parse_fail_rate=rate(c("parse_fail"), n),
        tool_ok=rate(c("tool_ok"), n),
        given_tool_ok=rate(c("given_tool_ok"), n),
        params_all_ok=rate(c("params_all_ok"), n),
        params_all_ok_strict=rate(c("params_all_ok_strict"), n),
        full_call_ok=rate(c("full_call_ok"), n),
        exact_call_ok=rate(c("exact_call_ok"), n),
        noparam_events=c("noparam"), noparam_rate=rate(c("noparam"), n),
        n_param_instances=n_par,
        param_acc_loose=rate(n_lo, n_par),
        param_acc_strict=rate(n_st, n_par),
        by_tool={k: dict(n=v["n"], tool_ok=rate(v["tool_ok"], v["n"]),
                         params_all_ok=rate(v["params_all_ok"], v["n"]),
                         full_call_ok=rate(v["full_call_ok"], v["n"]))
                 for k, v in top},
        samples=samples)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", required=True,
                    choices=["tales", "appworld", "bfcl", "alfworld"])
    ap.add_argument("--ctool-run", required=True,
                    help="causal classification-head run dir (provides the threshold: temperature/θ/logits_test.pt/label_map)")
    ap.add_argument("--cparam-run", required=True,
                    help="parameter-generation run dir (the report is also written here)")
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
    ap.add_argument("--overlong", default="left",
                    choices=["left", "skip", "drop-event"],
                    help="three ways to handle an overlong trigger-event full text/prompt (spec 16.2);"
                         "default left (behavior is byte-for-byte unchanged from before this flag was added)")
    args = ap.parse_args()

    ctool, cparam = Path(args.ctool_run), Path(args.cparam_run)
    data = Path(args.data)
    dev = args.device

    rep_cls = json.loads((ctool / "REPLAY_REPORT.json").read_text())
    T = rep_cls["temperature"]
    theta = rep_cls["chosen_theta"].get(str(args.risk))
    if theta is None:
        raise SystemExit(f"the classification-head report has no θ for risk={args.risk}:"
                         f"{rep_cls['chosen_theta']}")

    # 1) Threshold point: the filtering logic matches eval_tool line for line, keeping the
    # order in sync with logits_test.pt
    label2id = json.loads((ctool / "best" / "label_map.json").read_text())
    id2label = {v: k for k, v in label2id.items()}
    meta = json.loads((cparam / "best" / "meta.json").read_text())

    # Cell safety check: this script only consumes outputs from the cparam cell. cgen's meta
    # has no param_only field; evaluating a cgen run here would silently feed the tool name
    # in twice (once in the prompt, once again in the generation).
    if not meta.get("param_only"):
        raise SystemExit(
            f"{cparam / 'best' / 'meta.json'} does not have \"param_only\": true -- "
            "this is not output from the cparam cell. Evaluate full call-generation runs with eval_causal_call.py.")

    # Three-way data cross-check: the data used to train cparam, the --data argument, and
    # the data used to train ctool must be the same directory. When two base-model tracks
    # run in parallel, cross-feeding like pairing p1b06's ctool with p1b17's cparam will
    # silently pass every other safety check.
    ctool_meta = json.loads((ctool / "best" / "meta.json").read_text())
    trio = {"--data value": str(data),
            "cparam meta.data": meta.get("data"),
            "ctool meta.data": ctool_meta.get("data")}
    canon = {k: (str(Path(v).resolve()) if v else None) for k, v in trio.items()}
    if len(set(canon.values())) != 1:
        raise SystemExit("three-way data cross-check mismatch, hard stop:\n" + "\n".join(
            f"  {k} = {trio[k]!r} -> {canon[k]!r}" for k in trio))

    # Two-way safety check against cross-contamination: ctool's label_map has an abstention
    # sentinel, cparam's meta has a readonly_env key (missing = old mode); both must hold
    # together with --readonly-env
    has_sentinel = readonly_map.NON_READONLY in label2id
    meta_ro = meta.get("readonly_env")
    if has_sentinel != bool(args.readonly_env) or \
            (meta_ro is not None) != bool(args.readonly_env):
        raise SystemExit(
            f"readonly fuse mismatch:{ctool / 'best' / 'label_map.json'} "
            f"{'has' if has_sentinel else 'lacks'} abstention sentinel "
            f"{readonly_map.NON_READONLY!r};"
            f"{cparam / 'best' / 'meta.json'}'s readonly_env key "
            f"{'= ' + repr(meta_ro) if meta_ro is not None else 'missing (=old mode)'};"
            f"while --readonly-env "
            f"{'passed ' + str(args.readonly_env) if args.readonly_env else 'not passed'}."
            "All three must hold together or fail together -- a run trained in readonly mode can only be "
            "evaluated with --readonly-env; a run trained under the old settings can only be evaluated without it.")
    if args.readonly_env and isinstance(meta_ro, str) \
            and meta_ro != args.readonly_env:
        raise SystemExit(
            f"readonly fuse: cparam run was trained on {meta_ro!r},"
            f"but it's being evaluated against {args.readonly_env!r}'s ground-truth table -- environments don't match, hard stop.")
    ro_set = nro_id = None
    if args.readonly_env:
        ro_set = readonly_map.load_readonly_set(args.readonly_env)
        nro_id = label2id[readonly_map.NON_READONLY]

    raw_rows = load_rows(data / "test.jsonl")
    if ro_set is not None:
        readonly_map.audit([r["label"] for r in raw_rows],
                           readonly_map.load_table(args.readonly_env),
                           "eval_causal_param test")
        for r in raw_rows:
            r["label"] = readonly_map.collapse(r["label"], ro_set)
    rows = [r for r in raw_rows if r["label"] in label2id]
    for r in rows:
        r["y"] = label2id[r["label"]]

    logits = torch.load(ctool / "logits_test.pt", map_location="cpu")
    assert len(rows) == logits.shape[0], (len(rows), logits.shape)

    # Rows excluded by ctool are not allowed as threshold-point candidates (spec 16.2's
    # connecting section): read excluded_idx up front, and pick the threshold point only
    # from the remaining rows -- zero logits through softmax give a uniform distribution,
    # which θ only blocks naturally when θ<=1/n_labels, so this cannot be relied on as a
    # safeguard. When all of an event's candidate rows are excluded, it has no threshold
    # point, is not scored, and is counted in n_excluded_by_ctool.
    ev_row_idx = defaultdict(list)
    for i, r in enumerate(rows):
        ev_row_idx[r["event"]].append(i)
    ctool_lmeta = ctool / "logits_test.meta.json"
    excluded_rows = set()
    if ctool_lmeta.exists():
        excluded_rows = set(
            json.loads(ctool_lmeta.read_text()).get("excluded_idx", []))
    n_excluded_by_ctool = sum(
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
    # scored (they do not enter any denominator), and are counted separately. The two
    # conventions share the same batch of keys, so this applies to gt_tool / pred_tool at
    # the same time.
    n_ro_excluded = 0
    if ro_set is not None:
        keep = [k for k in keys
                if fired[k]["label"] != readonly_map.NON_READONLY]
        n_ro_excluded = len(keys) - len(keep)
        keys = keep

    # 2) Generation: CALL_SEP is read from the training-side meta.json (not hardcoded);
    # generate once for each convention
    sep = meta.get("call_sep", FALLBACK_SEP)
    max_len = meta.get("max_len", 4096)
    tok = AutoTokenizer.from_pretrained(cparam / "best")
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    tok.truncation_side = "left"                    # Keep the tail of the thinking text
    tok.padding_side = "right"
    model = AutoModelForCausalLM.from_pretrained(
        cparam / "best",
        dtype=torch.bfloat16 if str(dev).startswith("cuda") else torch.float32
    ).to(dev).eval()

    rowof = {k: fired[k]["row"] for k in keys}
    gt_given = {k: rowof[k]["label"] for k in keys}
    pred_given = {k: id2label[fired[k]["pred"]] for k in keys}

    # --overlong filtering (after pred_given is built, before the generation loop for either
    # convention; spec 16.2 fixes the three-step order: readonly exclusion -> --overlong
    # filtering -> --limit). ctool exclusion was already handled at the threshold-point-
    # picking step (n_excluded_by_ctool above), so an empty set is passed here, doing only
    # prompt-length filtering -- every event in keys is already guaranteed to have at least
    # one candidate row not excluded by ctool, so select_keys' exclusion branch can never
    # fire here.
    overlong_counts = dict(n_left_truncated=0, n_skipped_rows=0,
                          n_dropped_events=0, n_excluded_by_ctool=n_excluded_by_ctool)
    n_left_truncated_by_tag = {"gt_tool": 0, "pred_tool": 0}
    keys_rowmap = {k: ev_row_idx[k] for k in keys}
    thresh = max_len - args.max_new_tokens
    tag_len = {}
    prompt_len = {}
    for k in keys:
        lens = {tag: len(tok(rowof[k]["text"] + sep + given[k] + "(",
                            add_special_tokens=False,
                            truncation=False)["input_ids"])
               for tag, given in (("gt_tool", gt_given), ("pred_tool", pred_given))}
        tag_len[k] = lens
        prompt_len[k] = max(lens.values())
    n_full = {}
    if args.overlong == "drop-event":
        key_set = set(keys)
        # spec 16.2: for the full text, use share_data's rule (don't filter rows by ctool's
        # vocabulary, take the text of the row with the largest sent_idx) -- pass raw_rows, not
        # the filtered rows, otherwise this amounts to applying ctool's filtering convention.
        full_texts = share_data.event_full_texts(
            [r for r in raw_rows if r["event"] in key_set])
        n_full = {k: share_data.n_full_tokens(tok, full_texts[k]) for k in keys}
    keys, length_counts = share_data.select_keys(
        args.overlong, keys_rowmap, n_full, prompt_len, set(),
        max_len, args.max_new_tokens)
    assert length_counts["n_excluded_by_ctool"] == 0, (
        "every event in keys should have at least one candidate row not excluded by ctool")
    overlong_counts.update(n_left_truncated=length_counts["n_left_truncated"],
                          n_skipped_rows=length_counts["n_skipped_rows"],
                          n_dropped_events=length_counts["n_dropped_events"])
    for k in keys:
        for tag in ("gt_tool", "pred_tool"):
            if tag_len[k][tag] > thresh:
                n_left_truncated_by_tag[tag] += 1
    if args.limit:
        keys = keys[:args.limit]

    res = {}
    for tag, given in (("gt_tool", gt_given), ("pred_tool", pred_given)):
        prompts = [rowof[k]["text"] + sep + given[k] + "(" for k in keys]
        gens = (generate(model, tok, prompts, dev, args.bs, max_len,
                         args.max_new_tokens, tag) if prompts else [])
        per_ev, samples, n_par, n_lo, n_st = score_points(
            keys, rowof, given, gens, args.env)
        res[tag] = block(per_ev, keys, theta, n_par, n_lo, n_st, samples)

    n = len(keys)
    n_ev = len({r["event"] for r in rows})
    out = dict(
        env=args.env, ctool_run=str(ctool), cparam_run=str(cparam),
        risk=args.risk, theta=theta, temperature=T, call_sep=sep,
        max_new_tokens=args.max_new_tokens, limit=args.limit,
        n_events_test=n_ev, n_events_fired=n_fired, n_events_scored=n,
        overlong_mode=args.overlong,
        n_left_truncated=overlong_counts["n_left_truncated"],
        n_skipped_rows=overlong_counts["n_skipped_rows"],
        n_dropped_events=overlong_counts["n_dropped_events"],
        n_excluded_by_ctool=overlong_counts["n_excluded_by_ctool"],
        n_left_truncated_by_tag=n_left_truncated_by_tag,
        gt_tool=res["gt_tool"], pred_tool=res["pred_tool"])
    if ro_set is not None:
        out["readonly_env"] = args.readonly_env
        out["readonly_excluded"] = n_ro_excluded
    (cparam / "PARAM_REPORT.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1))

    g, p = res["gt_tool"], res["pred_tool"]
    md = [f"# Parameter generation evaluation at the fire moment -- {args.env}",
          f"- overlong_mode={out['overlong_mode']}"
          f"(n_left_truncated={out['n_left_truncated']}, "
          f"n_skipped_rows={out['n_skipped_rows']}, "
          f"n_dropped_events={out['n_dropped_events']}, "
          f"n_excluded_by_ctool={out['n_excluded_by_ctool']}, "
          f"n_left_truncated_by_tag={out['n_left_truncated_by_tag']})",
          f"- classification head {ctool.name} / parameter head {cparam.name}; risk≤{args.risk} → "
          f"θ={theta}(temperature T={T})",
          f"- test events {n_ev}, fired {n_fired}, {n} counted this time"
          + (f"(--limit {args.limit})" if args.limit else ""),
          f"- concatenation separator call_sep={sep!r} (read from the parameter head's meta.json);"
          f"prompt = text + call_sep + tool name + \"(\";"
          f"greedy max_new_tokens={args.max_new_tokens}, stop on newline or eos",
          "",
          "| metric | gt_tool (fed the ground-truth tool name) | pred_tool (fed the classification head's prediction) |",
          "|---|---|---|",
          f"| number of scored events | {g['n_events_scored']} | {p['n_events_scored']} |",
          f"| parse-failure rate (structurally always 0 in this table, see scoring settings) | {g['parse_fail_rate']} | "
          f"{p['parse_fail_rate']} |",
          f"| tool-name accuracy | {g['tool_ok']} | {p['tool_ok']} |",
          f"| all-params-correct rate (loose) | {g['params_all_ok']} | {p['params_all_ok']} |",
          f"| all-params-correct rate (strict) | {g['params_all_ok_strict']} | "
          f"{p['params_all_ok_strict']} |",
          f"| full-call accuracy | {g['full_call_ok']} | {p['full_call_ok']} |",
          f"| exact whole-string match | {g['exact_call_ok']} | {p['exact_call_ok']} |",
          f"| share of no-arg events | {g['noparam_rate']}({g['noparam_events']}/{n}) | "
          f"same as left |",
          f"| number of parameter instances | {g['n_param_instances']} | {p['n_param_instances']} |",
          f"| parameter-level accuracy (loose/strict) | {g['param_acc_loose']} / "
          f"{g['param_acc_strict']} | {p['param_acc_loose']} / "
          f"{p['param_acc_strict']} |",
          "",
          f"## Per-tool breakdown (pred_tool settings, top {TOPK_TOOLS} by event count)",
          "| tool | events | tool name correct | all params correct | full call correct |",
          "|---|---|---|---|---|"]
    for k, v in p["by_tool"].items():
        md.append(f"| {k} | {v['n']} | {v['tool_ok']} | "
                  f"{v['params_all_ok']} | {v['full_call_ok']} |")
    md += ["", "## Scoring settings",
           "- Before scoring, reassemble the tool name and the opening parenthesis onto the front of the generated string, then run the "
           "exact same parse_call / match_params as the cgen evaluation.",
           "- Parameters are compared one by one: loose = values equal after normalization (strip, then drop quotes); strict = the raw strings are exactly equal;"
           "keys are compared by union; an extra param, a missing param, or a wrong name each counts as one wrong instance.",
           "- The parse-failure rate is structurally always 0 in this table: the tool name is spliced onto the front of the string by the script itself,"
           "so parse_call always hits. This row isn't comparable to the parse-failure rate in the cgen report,"
           "and it doesn't reflect generation quality.",
           "- In the all-params-correct rate, events whose ground truth has no args are always true (their share is listed separately);"
           "full call correct = tool name correct AND all params correct (loose). In the gt_tool block, no-arg events"
           "are always full-call correct too (the tool name is fed in), so this free credit is larger than in the cgen cell"
           "(there the tool name has to be generated on its own); for cross-comparisons the matrix only takes pred_tool's full_call_ok.",
           "- The tool name in the gt_tool block is given by the ground truth, so its tool-name accuracy is always 1 (recorded as-is);"
           "the tool name in the pred_tool block comes from the classification head's argmax, and the gap between the two blocks"
           "is exactly the loss left by the classification head picking the wrong tool. The matrix only takes pred_tool -- that's system B's real settings.",
           "- The fire points and ctool's replay come from exactly the same source, so this table can be read side by side with the same model's cgen cell's "
           "CALLGEN_REPORT: both are about whether a full call can be assembled at the very moment of firing."]
    if ro_set is not None:
        md += ["", f"## Readonly mode (--readonly-env {args.readonly_env})",
               f"- abstention class {readonly_map.NON_READONLY} (label id {nro_id});"
               "the fire condition adds \"argmax is not the abstention class\"; ground-truth labels have been folded",
               f"- events that fire but whose ground truth isn't readonly, and are therefore not scored: {n_ro_excluded}"
               f"(readonly_excluded); both blocks' denominator is the remaining {n}"
               "ground-truth-readonly fired events"]
    (cparam / "PARAM_REPORT.md").write_text("\n".join(md) + "\n")
    heartbeat.emit(n, n, "item", status="done")
    print(json.dumps(
        dict(n_events_scored=n,
             gt_tool={k: g[k] for k in ("tool_ok", "params_all_ok",
                                        "full_call_ok")},
             pred_tool={k: p[k] for k in ("tool_ok", "params_all_ok",
                                          "full_call_ok")}),
        ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
