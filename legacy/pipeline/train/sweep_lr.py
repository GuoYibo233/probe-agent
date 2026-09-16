#!/usr/bin/env python3
"""Driver and report for the learning-rate sweep (`.scratch/kvshare-train/spec.md` 16.6, ticket 11).

What question this answers: among the three learning-rate anchors for each of
the four backbone configs (full-parameter 0.6B/1.7B, LoRA 1.7B/4B), which one
gets the lowest `val_ce`? This file only does two things; GPU launches go
through the main session's gpu-run:

  plan   -- generate 12 `train_causal_share.py` commands per `GRID`, print them as
             a list and as `python3 run.py launch` lines; `--write` dumps JSON.
  report -- scan `train_log.jsonl` from a batch of run directories, roll it up
             into `SWEEP_REPORT.json` and `SWEEP_REPORT.md`.

Usage:
    python3 run.py sweep-lr plan
    python3 run.py sweep-lr plan --write pipeline/runs/sweep/plan.json
    python3 run.py sweep-lr report --runs pipeline/runs/sweep/ks828* \\
        --out pipeline/runs/sweep
"""
import argparse
import datetime
import glob
import json
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Grid constants (spec 16.6 decision 29, 16.8 decision 30) -- may change again
# after smoke testing, written so a change is obvious at a glance: each item is
# tag/base/lora/lrs (full-parameter three anchors 1e-5, 5e-5, 2e-4; LoRA
# multiplies each point by 10 to get 1e-4, 5e-4, 2e-3)/tok_budget/card (card
# type, for the launcher to see)/extra (extra flags).
GRID = [
    dict(tag="b06", base="qwen", lora=False,
         lrs=[1e-5, 5e-5, 2e-4], tok_budget=16384, card="Ada",
         extra=["--grad-ckpt"]),
    dict(tag="b17", base="qwen17", lora=False,
         lrs=[1e-5, 5e-5, 2e-4], tok_budget=16384, card="H200",
         extra=[]),
    dict(tag="l17", base="qwen17", lora=True,
         lrs=[1e-4, 5e-4, 2e-3], tok_budget=16384, card="H200",
         extra=[]),
    dict(tag="l4", base="qwen4", lora=True,
         lrs=[1e-4, 5e-4, 2e-3], tok_budget=16384, card="H100",
         # --align-tol 3e-5: 4B's fp32 row-by-row alignment error of 1.54e-5 leaves only
         # 23% margin against the default 2e-5; it is bit-for-bit reproducible on the
         # same card type, so the tolerance is widened to leave margin for switching
         # card type or torch version (decision 36)
         extra=["--grad-ckpt", "--align-tol", "3e-5"]),
]

DEFAULT_DATA = "pipeline/data/nyapass_aw_v1/gptoss"
DEFAULT_OUT_ROOT = "pipeline/runs/sweep"
DEFAULT_TRACK = "kvshare-lr-sweep"


def fmt_lr(lr):
    """`1e-05` -> `1e-5`, `2e-04` -> `2e-4`: `f"{lr:.0e}"` keeps one significant
    digit, then strips the leading zero in the exponent. If two learning rates
    collide after formatting, the grid has a value with a non-unit significant
    digit (like 1.2e-5); `plan`'s self-check catches this through that
    collision."""
    s = f"{lr:.0e}"
    mantissa, exp = s.split("e")
    sign = exp[0]
    digits = exp[1:].lstrip("0") or "0"
    return f"{mantissa}e{sign}{digits}"


def build_plan(grid, data_dir, out_root, py):
    """Pure function: grid -> 12 run records. `data_dir`/`out_root` are already resolved to absolute paths."""
    rows = []
    for cfg in grid:
        for lr in cfg["lrs"]:
            lr_s = fmt_lr(lr)
            run_id = f"ks828{cfg['tag']}_gptoss_cgen_lr{lr_s}"
            outdir = out_root / run_id
            cmd = [py, str(ROOT / "pipeline/train/train_causal_share.py"),
                   "--mode", "cgen",
                   "--base", cfg["base"],
                   "--env", "appworld",
                   "--data", str(data_dir),
                   "--out", str(outdir),
                   "--lr", lr_s,
                   "--tok-budget", str(cfg["tok_budget"]),
                   "--epochs", "1",
                   "--eval-per-epoch", "4",
                   "--log-every", "10",
                   "--mem-probe"]
            if cfg["lora"]:
                cmd.append("--lora")
            cmd += list(cfg["extra"])
            rows.append(dict(run_id=run_id, tag=cfg["tag"], base=cfg["base"],
                              lora=cfg["lora"], lr=lr, lr_s=lr_s,
                              tok_budget=cfg["tok_budget"], card=cfg["card"],
                              extra=list(cfg["extra"]),
                              cmd=" ".join(cmd), outdir=str(outdir)))

    # Self-check: run_id must be pairwise distinct; on a duplicate, SystemExit and print the two colliding records (with their original lr values).
    seen = {}
    for r in rows:
        prior = seen.get(r["run_id"])
        if prior is not None:
            raise SystemExit(
                f"run_id collision: {r['run_id']}\n"
                f"  first: tag={prior['tag']} lr={prior['lr']}\n"
                f"  second: tag={r['tag']} lr={r['lr']}\n"
                f"(fmt_lr keeps only one significant digit, two lr values in the grid collided after formatting)")
        seen[r["run_id"]] = r
    return rows


def cmd_plan(args):
    grid = GRID
    if args.grid:
        grid = json.loads(Path(args.grid).read_text())

    data_dir = Path(args.data)
    if not data_dir.is_absolute():
        data_dir = ROOT / data_dir
    data_dir = data_dir.resolve()

    out_root = Path(args.out_root)
    if not out_root.is_absolute():
        out_root = ROOT / out_root
    out_root = out_root.resolve()

    rows = build_plan(grid, data_dir, out_root, args.py)

    print("| run_id | tag | base | lora | lr | tok_budget | card | extra |")
    print("|---|---|---|---|---|---|---|---|")
    for r in rows:
        extra_s = " ".join(r["extra"]) if r["extra"] else "-"
        print(f"| {r['run_id']} | {r['tag']} | {r['base']} | {r['lora']} | "
              f"{r['lr_s']} | {r['tok_budget']} | {r['card']} | {extra_s} |")

    print()
    print("replace the --piece placeholder in each line below with the actual card from the card-scheduling table:")
    for r in rows:
        quoted = shlex.quote(r["cmd"])
        print(f"python3 run.py launch --cmd {quoted} --run-id {r['run_id']} "
              f"--track {args.track} --outdir {r['outdir']} "
              f"--piece <host>:<gpus>")

    if args.write:
        out = [dict(run_id=r["run_id"], tag=r["tag"], base=r["base"],
                     lora=r["lora"], lr=r["lr"], tok_budget=r["tok_budget"],
                     card=r["card"], cmd=r["cmd"], outdir=r["outdir"])
               for r in rows]
        Path(args.write).write_text(
            json.dumps(out, ensure_ascii=False, indent=1))
    return 0


def _read_events(run_dir):
    log_path = run_dir / "train_log.jsonl"
    events = []
    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def summarize_run(run_dir):
    """One run directory -> one report record (dict), fields extracted per spec 16.6."""
    events = _read_events(run_dir)
    start = next((e for e in events if e["event"] == "start"), None)
    evals = [e for e in events if e["event"] == "eval"]
    done = next((e for e in events if e["event"] == "done"), None)
    steps = [e for e in events if e["event"] == "step"]
    mem_summary = next(
        (e for e in events if e["event"] == "mem_probe_summary"), None)
    mem_probes = [e for e in events if e["event"] == "mem_probe"]

    eval_rows = []
    for e in evals:
        val_exact = e.get("val_exact_call", e.get("val_exact_params"))
        eval_rows.append(dict(ep=e.get("ep"), frac=e.get("frac"),
                               val_ce=e.get("val_ce"), val_exact=val_exact))

    # Not every evaluation point has val_exact (with --gen-eval-at last, only the
    # epoch-end point has one); spec 16.6 takes the value from whichever point has
    # one and tags it with its (ep, frac); when several points have a value, take
    # the last one -- iterate over eval_rows in order, overwrite whenever a point
    # has a value, and whatever remains after the loop is the last point with a
    # value.
    val_exact_best = val_exact_frac = None
    for r in eval_rows:
        if r["val_exact"] is not None:
            val_exact_best = r["val_exact"]
            val_exact_frac = f"{r['ep']}.{r['frac']}"

    peak_mem_gb = (max(s.get("peak_mem_gb") for s in steps)
                   if steps else None)
    if mem_summary is not None:
        worst_gb = mem_summary.get("worst_gb")
    elif mem_probes:
        worst_gb = max(m.get("peak_mem_gb") for m in mem_probes)
    else:
        worst_gb = None

    if done is not None:
        status = "done"
        best_val_ce = done.get("best_val_ce")
        best_frac = done.get("best_frac")
        best_ep = done.get("best_ep")
        wall_s = done.get("wall_s")
    else:
        status = "running"
        wall_s = None
        if eval_rows:
            best = min(eval_rows, key=lambda r: r["val_ce"])
            best_val_ce, best_frac, best_ep = (
                best["val_ce"], best["frac"], best["ep"])
        else:
            best_val_ce = best_frac = best_ep = None

    return dict(
        run_id=run_dir.name, status=status,
        base=start.get("base") if start else None,
        lora=bool(start and "lora" in start),
        lr=start.get("lr") if start else None,
        tok_budget=start.get("tok_budget") if start else None,
        n_train_events=start.get("n_train_events") if start else None,
        dropped_events_train=(
            start.get("dropped_events_train") if start else None),
        evals=eval_rows, best_val_ce=best_val_ce, best_frac=best_frac,
        _best_ep=best_ep, wall_s=wall_s, peak_mem_gb=peak_mem_gb,
        worst_gb=worst_gb, val_exact=val_exact_best,
        val_exact_frac=val_exact_frac)


def _expand_runs(patterns):
    dirs = set()
    for pat in patterns:
        for hit in glob.glob(pat):
            dirs.add(Path(hit))
    return sorted(dirs)


def cmd_report(args):
    dirs = _expand_runs(args.runs)
    records = []
    for d in dirs:
        if not (d / "train_log.jsonl").exists():
            print(f"[skip] no train_log.jsonl: {d}", file=sys.stderr)
            continue
        records.append(summarize_run(d))

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    json_records = [{k: v for k, v in r.items() if k != "_best_ep"}
                     for r in records]
    (out_dir / "SWEEP_REPORT.json").write_text(
        json.dumps(json_records, ensure_ascii=False, indent=1))

    # Group = (base, lora), ascending lr within a group; groups sorted by (base, lora).
    groups = {}
    for r in records:
        groups.setdefault((r["base"], r["lora"]), []).append(r)
    for key in groups:
        # (x is None, x) compares (True, None) against (True, None) when both records
        # lack lr, and the second element None < None raises TypeError -- when it is
        # None, swap in a comparable stand-in (0.0); the sort result does not depend
        # on this stand-in's value (the first element already sorts None to the end).
        groups[key].sort(
            key=lambda r: (r["lr"] is None, r["lr"] if r["lr"] is not None else 0.0))

    # Dynamic columns: every (ep, frac) combination that appears across all runs, ascending.
    combos = sorted({(e["ep"], e["frac"])
                      for r in records for e in r["evals"]
                      if e["ep"] is not None and e["frac"] is not None})

    lines = []
    lines.append(f"generated: {datetime.datetime.now().isoformat(timespec='seconds')}"
                  f"  directories read: {len(records)}")
    lines.append("")
    combo_cols = [f"val_ce@{ep}.{frac}" for ep, frac in combos]
    header = (["run_id", "lr"] + combo_cols +
              ["best_val_ce", "best_frac", "val_exact(@ep.frac)",
               "peak_mem_gb", "worst_gb", "wall_s", "status"])
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join(["---"] * len(header)) + "|")

    def _fmt(v):
        return "-" if v is None else str(v)

    for key in sorted(groups, key=lambda k: (k[0] or "", k[1])):
        rows = groups[key]
        # Same as above: when both records lack best_val_ce, swap None for the
        # comparable stand-in 0.0; this does not affect the sort (the first element
        # already sorts None to the end).
        best_i = min(range(len(rows)), key=lambda i: (
            rows[i]["best_val_ce"] is None,
            rows[i]["best_val_ce"] if rows[i]["best_val_ce"] is not None else 0.0))
        for i, r in enumerate(rows):
            by_combo = {(e["ep"], e["frac"]): e["val_ce"] for e in r["evals"]}
            # val_exact takes "whichever evaluation point has a value" (spec 16.6), which
            # is not necessarily the evaluation point where best_val_ce sits --
            # summarize_run has already picked it per this rule and stored it into
            # r["val_exact"]/r["val_exact_frac"]; this reads it directly rather than
            # re-pairing it against best_ep/best_frac.
            val_exact_cell = ("-" if r["val_exact"] is None else
                              f"{r['val_exact']}@{r['val_exact_frac']}")
            run_id_cell = ("*" + r["run_id"]) if i == best_i else r["run_id"]
            lr_cell = fmt_lr(r["lr"]) if r["lr"] is not None else "-"
            row = [run_id_cell, lr_cell]
            row += [_fmt(by_combo.get(c)) for c in combos]
            row += [_fmt(r["best_val_ce"]), _fmt(r["best_frac"]),
                    val_exact_cell, _fmt(r["peak_mem_gb"]),
                    _fmt(r["worst_gb"]), _fmt(r["wall_s"]), r["status"]]
            lines.append("| " + " | ".join(row) + " |")

    (out_dir / "SWEEP_REPORT.md").write_text("\n".join(lines) + "\n")
    return 0


def build_argparser():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    pp = sub.add_parser("plan", help="generate the run list from the grid")
    pp.add_argument("--grid", default=None, help="JSON file, replaces GRID wholesale")
    pp.add_argument("--data", default=DEFAULT_DATA)
    pp.add_argument("--out-root", default=DEFAULT_OUT_ROOT)
    pp.add_argument("--py", default=str(ROOT / "cprobe-env/bin/python"))
    pp.add_argument("--track", default=DEFAULT_TRACK)
    pp.add_argument("--write", default=None, help="write out a plan.json")
    pp.set_defaults(func=cmd_plan)

    rp = sub.add_parser("report", help="collect a batch of run directories into a report")
    rp.add_argument("--runs", nargs="+", required=True,
                     help="run directory path or glob, multiple allowed")
    rp.add_argument("--out", required=True, help="report output directory")
    rp.set_defaults(func=cmd_report)

    return p


def main(argv=None):
    args = build_argparser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
