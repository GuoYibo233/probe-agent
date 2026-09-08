#!/usr/bin/env python3
"""Watch table for learning-rate sweep runs (read-only, pure stdlib): GPU-memory
deviations and curve facts, draws no conclusions.

Usage:
  python3 .scratch/kvshare-train/verify/sweep_watch.py [<run_dir> ...] [--glob 'pipeline/runs/sweep/*']
      [--dev-threshold 15] [--grad-factor 5] [--json <out.json>]

For each run directory, reads train_log.jsonl (fields per spec 16.3 to 16.6: step has
loss/lr/grad_norm/peak_mem_gb/ips, eval has val_ce/val_exact_call/gen_s, mem_probe and
mem_probe_summary per 16.5). Outputs two tables:

  1. GPU memory: mem_probe_summary.worst_gb against the expected value computed for the
     same block from the 9.1/9.9 coefficients, and the max step peak against that
     config's estimated true epoch-0 peak (design 9.9: b06 with checkpointing 22.1, b17
     without 102.2, l17 without 81.9, l4 with 33.7 GB); "!!" is marked when either
     deviation's absolute value exceeds --dev-threshold (default 15%).
  2. Curve: step's loss (first, last, max, min, nan/inf count), grad_norm (median, max,
     last value, count of rows exceeding --grad-factor times the median), eval's val_ce
     sequence (each point that rises above the previous one is marked "↑"), minutes
     since the last step and the interval between the two most recent steps (these two
     numbers show stalling), done and best.

The coefficient table is imported directly from the same directory's smoke_check.py:
FIXED_GB / MB_PER_TOKEN / MB_PER_LOSS_POS (one source of truth).
"""
import argparse
import glob
import json
import math
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import smoke_check as sc  # noqa: E402

# design 9.9 / 9.4: the sweep run's most expensive epoch-0 block and the estimated true
# peak (GB), by config and checkpoint setting.
# update is the index of the update group the true-peak block falls in (0-based, the
# group field in enum_blocks.json; group N happens during update N+1); before training
# reaches that group, a step peak below the estimated true peak is expected, marked
# "not yet reached" in the table
TRUE_PEAK = {
    ("b06", True): dict(block=(12736, 5696), gb=22.1, update=475),
    ("b06", False): dict(block=(16384, 4271), gb=58.5, update=490),
    ("b17", False): dict(block=(16384, 4271), gb=102.2, update=490),
    ("b17", True): dict(block=(12736, 5696), gb=46.1, update=475),
    ("l17", False): dict(block=(16384, 4271), gb=81.9, update=490),
    ("l17", True): dict(block=(12736, 5696), gb=22.3, update=475),
    ("l4", True): dict(block=(15360, 4992), gb=33.7, update=110),
    ("l4", False): dict(block=(16384, 4271), gb=152.3, update=490),
}


def fmt(v, nd=2):
    if v is None:
        return "missing"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def dev(measured, expected, threshold):
    if measured is None or expected is None or expected <= 0:
        return "missing", False
    d = (measured - expected) / expected * 100
    return f"{d:+.1f}%" + (" !!" if abs(d) > threshold else ""), abs(d) > threshold


def analyze(run_dir, args, now):
    run_dir = Path(run_dir)
    r = dict(run_id=run_dir.name)
    log_p = run_dir / "train_log.jsonl"
    if not log_p.exists():
        r["error"] = "train_log.jsonl missing"
        return r
    ev = sc.load_log(log_p)
    st = ev["start"] or {}
    tag = sc.config_tag(st)
    gc, gc_src = sc.grad_ckpt_of(run_dir, tag)
    r.update(tag=tag, grad_ckpt=gc, grad_ckpt_source=gc_src, lr=st.get("lr"),
             tok_budget=st.get("tok_budget"), steps_total=st.get("steps"),
             mem_probe_pick=st.get("mem_probe_pick"), align_pass=st.get("align_pass"),
             align_maxdiff=st.get("align_maxdiff"))

    # ---- GPU memory ----
    probes = []
    for m in ev["mem_probe"]:
        n_tokens, n_loss = sc.probe_numbers(m)
        exp = sc.expected_gb(tag, gc, n_tokens, n_loss)
        d, flag = dev(m.get("peak_mem_gb"), exp, args.dev_threshold)
        probes.append(dict(kind=m.get("kind"), n_tokens=n_tokens, n_loss_pos=n_loss,
                           peak_gb=m.get("peak_mem_gb"), expected_gb=exp, dev=d, flag=flag))
    r["probes"] = probes
    summ = ev["summary"]
    if summ:
        wp = next((p for p in probes if p["kind"] == summ.get("worst_kind")), None)
        d, flag = dev(summ.get("worst_gb"), wp["expected_gb"] if wp else None, args.dev_threshold)
        r["summary"] = dict(pick=summ.get("pick"), scope=summ.get("scope"), worst_gb=summ.get("worst_gb"),
                            worst_kind=summ.get("worst_kind"),
                            expected_gb=wp["expected_gb"] if wp else None, dev=d, flag=flag)
    else:
        r["summary"] = None
    steps = ev["step"]
    peaks = [s.get("peak_mem_gb") for s in steps if s.get("peak_mem_gb") is not None]
    r["step_peak_gb"] = max(peaks) if peaks else None
    tp = TRUE_PEAK.get((tag, gc))
    r["true_peak_est"] = tp["gb"] if tp else None
    r["true_peak_block"] = tp["block"] if tp else None
    r["true_peak_update"] = tp["update"] + 1 if tp else None
    r["step_peak_dev"], r["step_peak_flag"] = dev(r["step_peak_gb"], r["true_peak_est"], args.dev_threshold)
    gstep_last = steps[-1].get("gstep") if steps else None
    # training has not yet reached the update containing the true-peak block, and the step
    # peak is below the estimate: this is expected, no marker
    steps_total = st.get("steps") or 0
    if (tp and gstep_last is not None and gstep_last < tp["update"] + 1 <= steps_total
            and not st.get("smoke") and r["step_peak_gb"] is not None and r["step_peak_gb"] < tp["gb"]):
        r["step_peak_dev"] = f"{r['step_peak_dev'].replace(' !!', '')} not reached (the true peak block is at update {tp['update'] + 1})"
        r["step_peak_flag"] = False
    if st.get("smoke") and r["step_peak_gb"] is not None and r["true_peak_est"] is not None:
        r["step_peak_dev"] = r["step_peak_dev"].replace(" !!", "") + " (smoke block is small, not compared)"
        r["step_peak_flag"] = False

    # ---- curve ----
    losses = [s.get("loss") for s in steps if s.get("loss") is not None]
    finite = [x for x in losses if isinstance(x, (int, float)) and math.isfinite(x)]
    r["loss"] = dict(n=len(losses), first=finite[0] if finite else None, last=finite[-1] if finite else None,
                     max=max(finite) if finite else None, min=min(finite) if finite else None,
                     n_nonfinite=len(losses) - len(finite))
    gns = [s.get("grad_norm") for s in steps if s.get("grad_norm") is not None]
    gfin = [x for x in gns if isinstance(x, (int, float)) and math.isfinite(x)]
    med = statistics.median(gfin) if gfin else None
    r["grad_norm"] = dict(n=len(gns), median=med, max=max(gfin) if gfin else None,
                          last=gfin[-1] if gfin else None,
                          n_over=sum(1 for x in gfin if med and x > args.grad_factor * med) if gfin else 0,
                          n_nonfinite=len(gns) - len(gfin),
                          argmax_gstep=(steps[[s.get("grad_norm") for s in steps].index(max(gfin))].get("gstep")
                                        if gfin else None))
    vals = [(e.get("frac"), e.get("gstep"), e.get("val_ce"), e.get("val_exact_call", e.get("val_exact_params")),
             e.get("gen_s")) for e in ev["eval"]]
    marks = []
    for i, (frac, gstep, vce, vex, gs) in enumerate(vals):
        up = i > 0 and vals[i - 1][2] is not None and vce is not None and vce > vals[i - 1][2]
        marks.append(dict(frac=frac, gstep=gstep, val_ce=vce, val_exact=vex, gen_s=gs, up=up))
    r["evals"] = marks
    r["n_val_up"] = sum(1 for m in marks if m["up"])
    r["lr_last"] = steps[-1].get("lr") if steps else None
    r["gstep_last"] = steps[-1].get("gstep") if steps else None
    r["ips_last"] = steps[-1].get("ips") if steps else None
    r["last_step_age_min"] = (now - steps[-1]["t"]) / 60 if steps and "t" in steps[-1] else None
    r["step_interval_min"] = ((steps[-1]["t"] - steps[-2]["t"]) / 60
                              if len(steps) >= 2 and "t" in steps[-1] and "t" in steps[-2] else None)
    dn = ev["done"] or {}
    r["done"] = bool(ev["done"])
    r["best_val_ce"] = dn.get("best_val_ce")
    r["best_frac"] = dn.get("best_frac")
    r["wall_s"] = dn.get("wall_s")
    return r


def render(rows, args):
    print("GPU memory (GB): worst_gb against the same block's expected value; step peak against this config's epoch 0 true-peak estimate (design 9.9)")
    print("| run_id | config | checkpoint | lr | align | pick/scope | worst_gb (kind) | expected | dev | step peak | true peak est | dev | progress |")
    print("|" + "---|" * 13)
    for r in rows:
        if r.get("error"):
            print(f"| {r['run_id']} | | | | | | | | | | | | {r['error']} |")
            continue
        s = r.get("summary")
        gc = r.get("grad_ckpt")
        gc_s = ("missing" if gc is None else ("on" if gc else "off")) + ("(assumed)" if r.get("grad_ckpt_source") == "assumed" else "")
        prog = f"{r.get('gstep_last')}/{r.get('steps_total')}" + ("(done)" if r.get("done") else "")
        al = f"{r.get('align_pass')} {r.get('align_maxdiff'):.2e}" if r.get("align_maxdiff") is not None else "missing"
        print(f"| {r['run_id']} | {r['tag']} | {gc_s} | {r.get('lr')} | {al} | "
              f"{(s['pick'] + '/' + str(s['scope'])) if s else 'missing'} | "
              f"{(fmt(s['worst_gb']) + ' (' + str(s['worst_kind']) + ')') if s else 'missing'} | "
              f"{fmt(s['expected_gb'], 1) if s else 'missing'} | {s['dev'] if s else 'missing'} | "
              f"{fmt(r.get('step_peak_gb'))} | {fmt(r.get('true_peak_est'), 1)} | {r.get('step_peak_dev')} | {prog} |")
    print()
    print("curves: loss and grad_norm come from step events, val_ce comes from eval events (↑ = up from the previous point)")
    print("| run_id | lr | loss first→last (max/min, non-finite) | grad_norm median/max@gstep/last (count exceeding median×{:g}) | val_ce sequence | last lr | last step minutes since now / interval min | done best |".format(args.grad_factor))
    print("|" + "---|" * 8)
    for r in rows:
        if r.get("error"):
            continue
        L, G = r["loss"], r["grad_norm"]
        vseq = " → ".join(f"{fmt(m['val_ce'], 4)}{'↑' if m['up'] else ''}" for m in r["evals"]) or "none"
        print(f"| {r['run_id']} | {r.get('lr')} | {fmt(L['first'], 4)}→{fmt(L['last'], 4)} ({fmt(L['max'], 4)}/{fmt(L['min'], 4)}, {L['n_nonfinite']}) | "
              f"{fmt(G['median'], 3)}/{fmt(G['max'], 3)}@{G['argmax_gstep']}/{fmt(G['last'], 3)} ({G['n_over']}) | {vseq} | "
              f"{r.get('lr_last')} | {fmt(r.get('last_step_age_min'), 1)} / {fmt(r.get('step_interval_min'), 1)} | "
              f"{r.get('done')} {fmt(r.get('best_val_ce'), 4)}@{r.get('best_frac')} |")
    flagged = [r["run_id"] for r in rows if not r.get("error") and (
        (r.get("summary") and r["summary"].get("flag")) or r.get("step_peak_flag"))]
    diverge = [r["run_id"] for r in rows if not r.get("error") and (
        r["loss"]["n_nonfinite"] or r["grad_norm"]["n_nonfinite"] or r["grad_norm"]["n_over"] or r["n_val_up"])]
    print()
    print(f"Runs with GPU memory deviation exceeding ±{args.dev_threshold:g}%: {', '.join(flagged) if flagged else 'none'}")
    print(f"Runs with curve anomaly flags (non-finite loss/grad_norm, grad_norm exceeding median ×{args.grad_factor:g}, val_ce rising): "
          f"{', '.join(diverge) if diverge else 'none'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dirs", nargs="*")
    ap.add_argument("--glob", default=None, help="glob for run dirs, e.g. 'pipeline/runs/sweep/*'")
    ap.add_argument("--dev-threshold", type=float, default=15.0)
    ap.add_argument("--grad-factor", type=float, default=5.0, help="how many times over the median grad_norm counts as anomalous")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    dirs = list(args.run_dirs)
    if args.glob:
        dirs += sorted(d for d in glob.glob(args.glob) if Path(d).is_dir())
    if not dirs:
        print("no run dir (the dir doesn't exist or the glob matched nothing)")
        return 0
    now = time.time()
    rows = [analyze(d, args, now) for d in dirs]
    render(rows, args)
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=1, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
