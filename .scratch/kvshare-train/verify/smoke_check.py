#!/usr/bin/env python3
"""Readout table for kvshare's second round of smoke tests and sweep runs (read-only,
not in the registry; pure stdlib, runs under the system python3).

Usage:
  python3 .scratch/kvshare-train/verify/smoke_check.py <run_dir> [<run_dir> ...] \
      [--dev-threshold 15] [--json <out.json>]

For each run_dir, reads train_log.jsonl (start / mem_probe / mem_probe_summary / eval /
step / done events, field names per spec 16.3 to 16.5) and ALIGN_CHECK.json, and outputs:
  1. A summary table: run_id, config (b06/b17/l17/l4, inferred from start's base and
     lora), checkpoint (grad_ckpt from best/meta.json, or, if absent, assumed from the
     card-scheduling plan and marked "assumed"), align PASS and max_abs_diff, probe
     pick/scope, worst_gb (worst_kind), the expected value and deviation for the worst
     block, the max step peak, wall_s.
  2. Per-run detail: each mem_probe event's kind, B, L_pad, n_tokens, n_loss_pos, peak,
     expected, deviation; each eval event's frac, val_ce, val_exact_call (val_exact_params
     for cparam), gen_n, gen_s.

Algorithm for the expected value (design-attention.md 9.1, unit GB):
  expected = fixed term + per-token coefficient × n_tokens / 1000 + 1.8 × n_loss_pos / 1000
The fixed term and coefficient are taken by config and checkpoint (table 9.1); n_tokens /
n_loss_pos are taken from the values recorded on the probe event, and old-format events
(only B, L_pad) are filled in using B × L_pad and the default loss-position counts
(fullest_block 1,984, longest_event 1,344). Plugging in the tokens probe's default block
(16,384 tokens, 1,984 loss positions): b17 without checkpointing 98.1, l17 without
checkpointing 77.7, l4 with checkpointing 28.8, b06 with checkpointing 15.8 (all four
configs are calibrated from the 2026-08-28 to 29 smoke tests, design 9.8 and 9.9).
Deviation = (measured - expected) / expected; rows whose absolute value exceeds
--dev-threshold (default 15%) get an "!!" marker.
"""
import argparse
import json
import sys
from pathlib import Path

# The 9.1 GPU-memory model (GB), giving two values per config: (without checkpointing,
# with checkpointing). Fixed term: without checkpointing it holds fp32 weights, the bf16
# copy, gradients, and either AdamW state or the four LoRA pieces; with checkpointing,
# LoRA's bf16 copy is not resident (design 9.9: l4's two-point fit gives 16.25, and the
# 8.04 missing from 24.66 is exactly that copy), full-parameter is about 0.6 less.
# Measured and calibrated: b06 both tiers, b17/l17 without checkpointing (design 9.8),
# l4 with checkpointing (9.9); the rest are estimated: b17 with checkpointing 30.4, l17
# with checkpointing 7.16 (10.60 minus the 3.44 copy), l4 without checkpointing 24.66.
FIXED_GB = {"b06": (10.86, 10.27), "b17": (30.97, 30.4), "l17": (10.60, 7.16), "l4": (24.66, 16.25)}
MB_PER_TOKEN = {  # (without checkpointing, with checkpointing)
    # Measured and calibrated: b06 without checkpointing 2.44 (8.6/9.1), with checkpointing
    # 0.12 (9.9); 1.7B without checkpointing 3.88 (9.8); l4 with checkpointing 0.55 (9.9).
    # Estimated: 1.7B with checkpointing 0.38, 4B without checkpointing 7.32 (the two base
    # models peak at different moments, so a ratio cannot convert one to the other).
    "b06": (2.44, 0.12), "b17": (3.88, 0.38), "l17": (3.88, 0.38), "l4": (7.32, 0.55)}
MB_PER_LOSS_POS = 1.8
# whether each config has checkpointing on, from the card-scheduling plan (decision 30);
# used as the assumption when meta.json has no grad_ckpt
PLANNED_GC = {"b06": True, "b17": False, "l17": False, "l4": True}
# default loss-position counts for old-format probe events (no n_loss_pos): the fullest
# block and the longest event over the full set (9.2, 8.6)
DEFAULT_LOSS_POS = {"fullest_block": 1984, "longest_event": 1344}
TAG_BY_BASE = {"qwen": "b06", "qwen17": "b17", "qwen4": "b4"}


def load_log(path):
    ev = {"start": None, "done": None, "summary": None, "mem_probe": [], "eval": [], "step": []}
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        k = r.get("event")
        if k == "start":
            ev["start"] = r
        elif k == "done":
            ev["done"] = r
        elif k == "mem_probe_summary":
            ev["summary"] = r
        elif k in ("mem_probe", "eval", "step"):
            ev[k].append(r)
    return ev


def config_tag(start):
    """Infer the config name from the start event: base decides the base model, and whether the lora key is present decides the training method."""
    if not start:
        return "?"
    base = start.get("base", "?")
    tag = TAG_BY_BASE.get(base)
    if tag is None:
        tag = Path(str(base)).name or "?"        # --base was passed a directory (a small test model)
    if "lora" in start:
        tag = "l" + tag[1:] if tag.startswith("b") else "l:" + tag
    return tag


def grad_ckpt_of(run_dir, tag):
    """best/meta.json's grad_ckpt is the only place the checkpoint switch is recorded; if absent, assume it from the card-scheduling plan."""
    meta = run_dir / "best" / "meta.json"
    if meta.exists():
        try:
            m = json.loads(meta.read_text())
            return bool(m.get("grad_ckpt", False)), "meta"
        except (OSError, ValueError):
            pass
    if tag in PLANNED_GC:
        return PLANNED_GC[tag], "assumed"
    return None, "missing"


def expected_gb(tag, gc, n_tokens, n_loss_pos):
    if tag not in FIXED_GB or gc is None or n_tokens is None or n_loss_pos is None:
        return None
    coef = MB_PER_TOKEN[tag][1 if gc else 0]
    fixed = FIXED_GB[tag][1 if gc else 0]
    return fixed + coef * n_tokens / 1e3 + MB_PER_LOSS_POS * n_loss_pos / 1e3


def probe_numbers(m):
    """(n_tokens, n_loss_pos) for one mem_probe event; old-format events are filled in using B × L_pad and the default loss-position count."""
    b = m.get("B", m.get("n_events"))
    l_pad = m.get("L_pad", m.get("packed_len_max"))
    n_tokens = m.get("n_tokens")
    if n_tokens is None and b is not None and l_pad is not None:
        n_tokens = b * l_pad
    n_loss = m.get("n_loss_pos")
    if n_loss is None:
        n_loss = DEFAULT_LOSS_POS.get(m.get("kind"))
    return n_tokens, n_loss


def fmt(v, nd=2):
    if v is None:
        return "missing"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def fmt_sci(v):
    return "missing" if v is None else f"{v:.2e}"


def dev_str(measured, expected, threshold):
    if measured is None or expected is None or expected <= 0:
        return "missing", False
    d = (measured - expected) / expected * 100
    flag = abs(d) > threshold
    return f"{d:+.1f}%" + (" !!" if flag else ""), flag


def analyze(run_dir, threshold):
    run_dir = Path(run_dir)
    out = dict(run_id=run_dir.name, dir=str(run_dir))
    log_p, align_p = run_dir / "train_log.jsonl", run_dir / "ALIGN_CHECK.json"
    if align_p.exists():
        a = json.loads(align_p.read_text())
        out["align"] = dict(PASS=a.get("PASS"), max_abs_diff=a.get("max_abs_diff"),
                            max_tok_diff=a.get("max_tok_diff"), rule=a.get("rule"),
                            bf16_mean=a.get("bf16_mean_abs_diff"), baseline_warn=a.get("baseline_warn"))
    else:
        out["align"] = None
    if not log_p.exists():
        out["error"] = "train_log.jsonl missing"
        return out
    ev = load_log(log_p)
    st = ev["start"] or {}
    tag = config_tag(st)
    gc, gc_src = grad_ckpt_of(run_dir, tag)
    out.update(tag=tag, grad_ckpt=gc, grad_ckpt_source=gc_src, mode=st.get("mode"),
               tok_budget=st.get("tok_budget"), mem_probe_pick=st.get("mem_probe_pick"),
               gen_eval=st.get("gen_eval"), n_train_events=st.get("n_train_events"),
               smoke=st.get("smoke"), lr=st.get("lr"),
               align_pass_start=st.get("align_pass"), align_bf16_warn=st.get("align_bf16_warn"))

    probes = []
    for m in ev["mem_probe"]:
        n_tokens, n_loss = probe_numbers(m)
        exp = expected_gb(tag, gc, n_tokens, n_loss)
        peak = m.get("peak_mem_gb")
        d, flag = dev_str(peak, exp, threshold)
        probes.append(dict(kind=m.get("kind"), pick=m.get("pick"), B=m.get("B", m.get("n_events")),
                           L_pad=m.get("L_pad", m.get("packed_len_max")), n_tokens=n_tokens,
                           n_rows=m.get("n_rows"), n_loss_pos=n_loss, n_backward=m.get("n_backward"),
                           peak_gb=peak, expected_gb=exp, dev=d, flag=flag))
    out["probes"] = probes

    summ = ev["summary"]
    if summ:
        out["summary"] = dict(pick=summ.get("pick"), worst_gb=summ.get("worst_gb"),
                              worst_kind=summ.get("worst_kind"), scope=summ.get("scope"),
                              n_events_considered=summ.get("n_events_considered"), source="summary")
    elif probes:
        w = max((p for p in probes if p["peak_gb"] is not None), key=lambda p: p["peak_gb"], default=None)
        out["summary"] = (dict(pick=st.get("mem_probe_pick", "tokens (old format)"), worst_gb=w["peak_gb"],
                               worst_kind=w["kind"], scope="full?", n_events_considered=None,
                               source="max(mem_probe)") if w else None)
    else:
        out["summary"] = None
    if out["summary"]:
        wk = out["summary"]["worst_kind"]
        wp = next((p for p in probes if p["kind"] == wk), None)
        out["summary"]["expected_gb"] = wp["expected_gb"] if wp else None
        out["summary"]["dev"], out["summary"]["flag"] = dev_str(
            out["summary"]["worst_gb"], out["summary"]["expected_gb"], threshold)
        out["summary"]["x1_1"] = (None if out["summary"]["worst_gb"] is None
                                  else out["summary"]["worst_gb"] * 1.1)

    evals = []
    for e in ev["eval"]:
        exact = e.get("val_exact_call", e.get("val_exact_params"))
        evals.append(dict(ep=e.get("ep"), frac=e.get("frac"), gstep=e.get("gstep"),
                          val_ce=e.get("val_ce"), val_exact=exact, gen_n=e.get("gen_n"),
                          gen_s=e.get("gen_s"), n_eval_rows=e.get("n_eval_rows")))
    out["evals"] = evals
    steps = ev["step"]
    out["step_peak_gb"] = max((s.get("peak_mem_gb") or 0.0) for s in steps) if steps else None
    out["n_steps_logged"] = len(steps)
    out["last_ips"] = steps[-1].get("ips") if steps else None
    dn = ev["done"] or {}
    out["done"] = bool(ev["done"])
    out["wall_s"] = dn.get("wall_s")
    out["best_val_ce"] = dn.get("best_val_ce")
    out["best_frac"] = dn.get("best_frac")
    return out


def render(rows):
    head = ("| run_id | config | checkpoint | align PASS / max_abs_diff | pick / scope | worst_gb (kind) "
            "| expected GB | deviation | worst×1.1 | step peak GB | eval count / best val_ce | wall_s |")
    print(head)
    print("|" + "---|" * 12)
    for r in rows:
        if r.get("error"):
            print(f"| {r['run_id']} | | | | | | | | | | | {r['error']} |")
            continue
        al = r.get("align")
        al_s = "missing" if al is None else f"{al.get('PASS')} / {fmt_sci(al.get('max_abs_diff'))}"
        gc = r.get("grad_ckpt")
        gc_s = ("missing" if gc is None else ("on" if gc else "off")) + (
            f"({r['grad_ckpt_source']})" if r.get("grad_ckpt_source") == "assumed" else "")
        s = r.get("summary")
        if s:
            pick_s = f"{s.get('pick')} / {s.get('scope')}"
            worst_s = f"{fmt(s.get('worst_gb'))} ({s.get('worst_kind')})"
            exp_s, dev_s, x11 = fmt(s.get("expected_gb"), 1), s.get("dev"), fmt(s.get("x1_1"), 1)
        else:
            pick_s = worst_s = exp_s = dev_s = x11 = "missing"
        ev_s = f"{len(r['evals'])} / {fmt(r.get('best_val_ce'), 4)}"
        print(f"| {r['run_id']} | {r['tag']} | {gc_s} | {al_s} | {pick_s} | {worst_s} | {exp_s} | {dev_s} "
              f"| {x11} | {fmt(r.get('step_peak_gb'))} | {ev_s} | {fmt(r.get('wall_s'), 1)}"
              f"{'' if r.get('done') else '(not done)'} |")
    for r in rows:
        if r.get("error"):
            continue
        print()
        print(f"== {r['run_id']}  config {r['tag']}  mode {r.get('mode')}  lr {r.get('lr')}  "
              f"tok_budget {r.get('tok_budget')}  smoke {r.get('smoke')}  n_train_events {r.get('n_train_events')}  "
              f"gen_eval {r.get('gen_eval')}  mem_probe_pick {r.get('mem_probe_pick')}  "
              f"checkpoint source {r.get('grad_ckpt_source')}")
        al = r.get("align")
        if al:
            print(f"   align: PASS={al.get('PASS')} max_abs_diff={fmt_sci(al.get('max_abs_diff'))} "
                  f"max_tok_diff={fmt_sci(al.get('max_tok_diff'))} bf16_mean={fmt_sci(al.get('bf16_mean'))} "
                  f"rule={al.get('rule')} baseline_warn={al.get('baseline_warn')}")
        for p in r["probes"]:
            print(f"   mem_probe {p['kind']:>18s}: B={p['B']} L_pad={p['L_pad']} n_tokens={p['n_tokens']} "
                  f"n_rows={p['n_rows']} n_loss_pos={p['n_loss_pos']} n_backward={p['n_backward']} "
                  f"peak={fmt(p['peak_gb'])} expected={fmt(p['expected_gb'], 1)} dev={p['dev']}")
        s = r.get("summary")
        if s:
            print(f"   summary({s.get('source')}): pick={s.get('pick')} scope={s.get('scope')} "
                  f"worst={fmt(s.get('worst_gb'))} ({s.get('worst_kind')}) "
                  f"n_events_considered={s.get('n_events_considered')} expected={fmt(s.get('expected_gb'), 1)} "
                  f"dev={s.get('dev')} worst×1.1={fmt(s.get('x1_1'), 1)}")
        for e in r["evals"]:
            print(f"   eval ep={e['ep']} frac={e['frac']} gstep={e['gstep']}: val_ce={fmt(e['val_ce'], 4)} "
                  f"val_exact={fmt(e['val_exact'], 4)} gen_n={e['gen_n']} gen_s={fmt(e['gen_s'], 1)} "
                  f"n_eval_rows={e['n_eval_rows']}")
        print(f"   step: {r['n_steps_logged']} entries, peak max {fmt(r.get('step_peak_gb'))} GB, last entry ips {r.get('last_ips')}; "
              f"done={r.get('done')} best_val_ce={fmt(r.get('best_val_ce'), 4)} best_frac={r.get('best_frac')} "
              f"wall_s={fmt(r.get('wall_s'), 1)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dirs", nargs="+")
    ap.add_argument("--dev-threshold", type=float, default=15.0, help="flag with !! when the deviation percentage exceeds this")
    ap.add_argument("--json", default=None, help="save all fields separately as JSON")
    args = ap.parse_args()
    rows = [analyze(d, args.dev_threshold) for d in args.run_dirs]
    render(rows)
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=1, ensure_ascii=False))
        print(f"\nJSON written to {args.json}")
    flagged = [r["run_id"] for r in rows if r.get("summary") and r["summary"].get("flag")]
    if flagged:
        print(f"\nRuns with deviation exceeding ±{args.dev_threshold:g}%: {', '.join(flagged)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
