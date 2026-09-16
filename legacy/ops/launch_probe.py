#!/usr/bin/env python3
"""tmux launcher for Phase C probe training -- a batch-agnostic generalized version.

Replaces `ops/launch_c1.py` (it hardcodes the batch prefix `c1_`, the dataset
`aw_official_v1`, and the smoke model `q35` in three places; every new batch meant
copying the whole file).

Usage:
  # default sequential smoke (one model, one card per cell; cells and count follow
  # run.py's CELL_ORDER, three cells ctool/cgen/cparam as of 2026-08-21)
  launch_probe.py smoke --batch c2 --data-root pipeline/data/alf_official_v1 \
      --env alfworld --model q36 --host tokyo107 --gpus 0,1,2

  # full run (driven by the card-scheduling table)
  launch_probe.py full --batch c2 --data-root pipeline/data/alf_official_v1 \
      --env alfworld --placement ops/c2_placement.json

The card-scheduling table is a json array, one entry per cell:
  [{"model": "q36", "cell": "mtool", "host": "tokyo107", "gpu": 0,
    "extra": ["--align-tol", "3e-4"]}, ...]

run_id = <batch>_<model>_<cell>, consistent across the four spots (data dir name /
tmux session / job ledger name / commit message), see the "Recording" section of
CLAUDE.md.
"""
import argparse
import json
import shlex
import sys
import time
from pathlib import Path

WD = Path(__file__).resolve().parent.parent
LOGD = WD / "logs"

# cell -> (interpreter, training script, fixed args for that cell).
# The single source of truth is CELLS in the repo root's run.py (since 2026-08-02);
# this file only imports it, no longer keeps its own copy -- two isomorphic tables
# always drift, and that drift is silent. The dual-environment hard rule is also
# recorded in run.py.
sys.path.insert(0, str(WD))
from run import CELLS, CELL_ORDER  # noqa: E402
sys.path.insert(0, str(WD / "ops"))
# has_session/tmux_launch used to be local functions, now imported from the shared
# module (ticket 11, the consolidation step after the earlier expansion -- probing
# the card / registering are also wired in from here now).
from launch_common import has_session, tmux_launch, probe_free, register_all  # noqa: E402


def launch_and_register(host, gpu, sess, cmd, log, out, rid, batch, placement=""):
    """Full launch for one cell: probe the card (fail-closed) -> session existence check
    -> tmux launch -> RUNMETA -> job ledger / record registration. Skip (no launch,
    no registration) if the session already exists or the target card is not FREE.
    A registration failure (job ledger / record.py) only WARNs, it does not abort --
    the launch has already really happened, and this registration step (e.g. a
    duplicate run_id) must not hide an already-running job from the alive check.
    Returns True to mean it was actually launched (used by main()'s alive check)."""
    if has_session(host, sess):
        print(f"SKIP (exists): {sess}")
        return False
    ok, why = probe_free(host, str(gpu))
    if not ok:
        print(f"SKIP (not FREE): {sess}  {host} gpu{gpu}  {why}")
        return False
    inner = f"cd {WD} && CUDA_VISIBLE_DEVICES={gpu} {cmd} 2>&1 | tee {log}"
    tmux_launch(host, sess, inner)
    print(f"LAUNCHED {sess}  ({host} gpu{gpu})  log={log}")
    piece = {"host": host, "gpus": str(gpu), "session": sess, "log": str(log),
              "cmd": cmd, "launched_at": time.time(), "kind": "train",
              "stall_line": None, "escalate_line": None}
    # Pinning outputs to the code (audit B6) is written into out/RUNMETA.json by the
    # first step of register_all -- it is the sole writer; this only passes along the
    # kind and the fields to merge into the record.
    try:
        receipt = register_all(rid, str(WD), [piece], f"probe_{batch}", cmd,
                               outdir=out, runmeta_kind="train",
                               runmeta_extra={"run_id": rid, "session": sess,
                                              "launch_host": host, "gpu": gpu,
                                              "log": log,
                                              "placement": placement or ""})
        print(receipt)
    except SystemExit as e:
        print(f"WARN registration failed ({rid}): {e}")
    return True


def build(batch, data_root, env, model, cell, smoke, extra=None):
    py, script, base_args = CELLS[cell]
    rid = f"{batch}_{model}_{cell}"
    data = Path(data_root) / model
    if not data.is_dir():
        sys.exit(f"data dir does not exist: {data}")
    out = WD / ("pipeline/runs/smoke/" + rid + "_smoke" if smoke else "pipeline/runs/" + rid)
    args = [py, str(script), "--data", str(data), "--out", str(out), "--env", env]
    args += base_args
    if smoke:
        args.append("--smoke")
    if extra:
        args += list(extra)
    return rid, " ".join(shlex.quote(a) for a in args), out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["smoke", "full"])
    ap.add_argument("--batch", required=True, help="run_id prefix, e.g. c2")
    ap.add_argument("--data-root", required=True, help="dataset version dir (one subdirectory per model underneath)")
    ap.add_argument("--env", required=True,
                    choices=["appworld", "alfworld", "bfcl", "tales"])
    ap.add_argument("--model", help="smoke mode: which model's data to run the four cells with")
    ap.add_argument("--host", default="tokyo107", help="smoke mode: which host to run on")
    ap.add_argument("--gpus", default="0,1,2",
                    help="smoke mode: one card per cell, the count must equal run.py's "
                         "CELL_ORDER length (currently three: ctool/cgen/cparam)")
    ap.add_argument("--placement", help="full mode: card-scheduling table json")
    ap.add_argument("--force", action="store_true",
                    help="pass through to the training script's --force: retrain in the same out dir (B7 guard escape hatch, "
                         "mandatory for smoke reruns -- the smoke dir name is derived deterministically)")
    ap.add_argument("--dry-run", action="store_true", help="print only, do not launch")
    args = ap.parse_args()
    force = ["--force"] if args.force else []

    LOGD.mkdir(exist_ok=True)
    plan = []

    if args.mode == "smoke":
        if not args.model:
            sys.exit("smoke mode needs --model")
        gpus = [g.strip() for g in args.gpus.split(",")]
        if len(gpus) != len(CELL_ORDER):
            sys.exit(f"--gpus needs {len(CELL_ORDER)} cards, got {len(gpus)}")
        for cell, gpu in zip(CELL_ORDER, gpus):
            rid, cmd, out = build(args.batch, args.data_root, args.env,
                                  args.model, cell, True, force or None)
            hs = args.host.replace("tokyo", "")
            sess = f"new1_{rid}_smoke_t{hs}g{gpu}"
            plan.append((args.host, gpu, sess, cmd, f"{LOGD}/{sess}.log", out, rid))
    else:
        if not args.placement:
            sys.exit("full mode needs --placement")
        for p in json.load(open(args.placement)):
            rid, cmd, out = build(args.batch, args.data_root, args.env,
                                  p["model"], p["cell"], False,
                                  list(p.get("extra") or []) + force)
            host, gpu = p["host"], p["gpu"]
            hs = host.replace("tokyo", "")
            sess = f"new1_{rid}_t{hs}g{gpu}"
            plan.append((host, gpu, sess, cmd, f"{LOGD}/{sess}.log", out, rid))

    if args.dry_run:
        for host, gpu, sess, cmd, log, out, rid in plan:
            print(f"[dry-run] {host} gpu{gpu} {sess}\n    {cmd}")
        print(f"\n{len(plan)} cells total (dry-run, not launched)")
        return

    for host, gpu, sess, cmd, log, out, rid in plan:
        launch_and_register(host, gpu, sess, cmd, log, out, rid, args.batch,
                            args.placement or "")
    time.sleep(6)
    print("\n--- alive check ---")
    for host, gpu, sess, cmd, log, out, rid in plan:
        print(f"{sess}: {'ALIVE' if has_session(host, sess) else 'DEAD'}")


if __name__ == "__main__":
    main()
