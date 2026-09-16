#!/usr/bin/env python3
"""tmux launcher for Phase C4 eval -- batch-agnostic.

The pipeline has always been missing this piece: training has `ops/launch_probe.py`,
but eval has always relied on hand-rolled ssh+tmux. This script hardcodes the
dependency order from SKILL.md Phase C4:

    tool cells (mtool/ctool) ── produce REPLAY_REPORT.json + logits_test.pt
                 ↓ supply the temperature and the firing threshold theta
    call cells (mext eats the same model's mtool, cgen eats the same model's ctool)

Usage:
  # Launch the tool cells first (independent of each other, all in parallel)
  launch_eval.py tool --batch c2 --data-root pipeline/data/alf_official_v1 \
      --env alfworld --placement ops/c2_eval_tool_placement.json

  # Launch the call cells after the tool cells produce their reports
  launch_eval.py call --batch c2 --data-root pipeline/data/alf_official_v1 \
      --env alfworld --placement ops/c2_eval_call_placement.json

The card schedule table has one entry per cell:
  [{"model": "q36", "cell": "mtool", "host": "tokyo106", "gpu": 0,
    "extra": ["--risk", "0.1"]}, ...]

`cell` takes mtool/ctool in the tool phase, and mext/cgen/cparam in the call phase
(named for the head that produced it; the script itself resolves this to the
tool-cell path it depends on). Which cells belong to which phase is defined by
run.py's EVAL_CELLS (dep=None goes into the tool phase, having a dep goes into the
call phase); which cells actually get launched depends only on the --placement card
schedule table -- any cell not listed in the table is never launched. Session name
= eval_<batch>_<model>_<cell>.
"""
import argparse
import json
import shlex
import sys
import time
from pathlib import Path

WD = Path(__file__).resolve().parent.parent
LOGD = WD / "logs"

# The single source of truth for eval cells is EVAL_CELLS in the repo root's run.py
# (since audit C14, 2026-08-02); this file only imports it -- the interpreter/script/
# fixed args are all taken from the corresponding TASKS entry, not copied again here.
# The two-environment hard rule (the mbert head runs in mbert-env, the causal head
# runs in cprobe-env) is also recorded in run.py.
sys.path.insert(0, str(WD))
from run import EVAL_CELLS, PY, TASKS  # noqa: E402
sys.path.insert(0, str(WD / "ops"))
# has_session/tmux_launch used to be local functions; now they import the shared
# component instead (ticket 11, the consolidation step of "expand first, then
# consolidate" -- card probing/registration are wired in from here too).
from launch_common import has_session, tmux_launch, probe_free, register_all  # noqa: E402

TOOL_KEYS = [c for c, (_, dep) in EVAL_CELLS.items() if dep is None]
CALL_KEYS = [c for c, (_, dep) in EVAL_CELLS.items() if dep is not None]


def cell_cmd_parts(cell):
    """cell -> (interpreter, absolute script path, fixed args, dependency cell|None), all taken from run.py."""
    task_name, dep = EVAL_CELLS[cell]
    t = TASKS[task_name]
    return (t.get("prog") or PY[t["py"]], str(WD / t["script"]),
            list(t.get("args", [])), dep)


def launch_and_register(host, gpu, sess, cmd, log, meta_dir, stage, batch,
                        placement=""):
    """Complete launch of one cell: card probe (fail-closed)→session-existence check→
    tmux launch→RUNMETA→ledger/record registration. Both an already-existing
    session and a target card that is not FREE count as a skip, with neither launch
    nor registration happening. A registration (ledger/record.py) failure only WARNs
    and does not abort -- the launch has already really happened, and this step (e.g.
    a duplicate run_id) must not hide an already-running task from the alive check.
    Returns True to mean it was really sent out (used by main()'s alive check)."""
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
    # Pinning outputs to code (audit B6) is written into meta_dir/RUNMETA.json by
    # register_all's first step -- it's the sole writer; this only passes through kind
    # and the fields to merge into the record.
    # rid uses the full sess (including the eval_ prefix); the prefix can't be dropped --
    # dropping it would make it equal to the rid launch_probe.build() uses for the
    # training job of the same cell (`{batch}_{model}_{cell}`), and the training job's
    # deregistration (gpu_jobs finish) comes after eval (Phase C4) per SKILL.md Phase D,
    # so under the standard workflow the training job is still active in the ledger at
    # this point and would collide with register_all's duplicate run_id check (F1 review).
    # A prefixed rid can never structurally equal any training rid (`"eval_" + x == x` has
    # no solution), and the historical ledger does have a precedent for exactly this kind
    # of prefixed job name, `eval_c2_q36_mtool` (see the audit comment in
    # ops/gpu_jobs.py cmd_finish).
    rid = sess
    piece = {"host": host, "gpus": str(gpu), "session": sess, "log": str(log),
              "cmd": cmd, "launched_at": time.time(), "kind": f"eval_{stage}",
              "stall_line": None, "escalate_line": None}
    try:
        receipt = register_all(rid, str(WD), [piece], f"eval_{batch}", cmd,
                               outdir=meta_dir, runmeta_kind=f"eval_{stage}",
                               runmeta_extra={"session": sess,
                                              "launch_host": host, "gpu": gpu,
                                              "log": log,
                                              "placement": placement or ""})
        print(receipt)
    except SystemExit as e:
        print(f"WARN registration failed ({rid}): {e}")
    return True


def build(stage, batch, data_root, env, model, cell, extra=None):
    runs = WD / "pipeline/runs"
    data = WD / data_root / model
    if not data.is_dir():
        sys.exit(f"data dir does not exist: {data}")

    if stage == "tool":
        if cell not in TOOL_KEYS:
            sys.exit(f"a tool-profile cell can only be {TOOL_KEYS}, got {cell}")
        py, script, fixed, _ = cell_cmd_parts(cell)
        run = runs / f"{batch}_{model}_{cell}"
        # Check best/, not the directory itself: writing RUNMETA creates the directory as a
        # side effect, so a directory existing no longer implies training actually produced
        # anything (audit review)
        if not (run / "best").is_dir():
            sys.exit(f"training output does not exist: {run}/best")
        args = [py, script, "--env", env,
                "--run", str(run), "--data", str(data)] + fixed
        meta_dir = run
    else:
        if cell not in CALL_KEYS:
            sys.exit(f"a call-profile cell can only be {CALL_KEYS}, got {cell}")
        py, script, fixed, dep = cell_cmd_parts(cell)
        head_run = runs / f"{batch}_{model}_{cell}"
        dep_run = runs / f"{batch}_{model}_{dep}"
        # Hard check on dependency order: refuse to launch if the tool cell hasn't produced
        # its report yet (SKILL.md Phase C4 hard rule)
        rep = dep_run / "REPLAY_REPORT.json"
        if not rep.is_file():
            sys.exit(f"dependency not ready: {rep} does not exist -- finish evaluating {batch}_{model}_{dep} first")
        if not (head_run / "best").is_dir():
            sys.exit(f"training output does not exist: {head_run}/best")
        # The three call scripts each take a different argument shape; this is the launcher's
        # own knowledge (fixed by each script's argparse). Adding a new call cell must add an
        # explicit line here: falling through to else would pass the head run as --cgen-run,
        # but eval_causal_param.py has no such argument at all, so argparse rejects it
        # immediately (loud, but the fault is the launcher's).
        if cell == "mext":
            args = [py, script, "--env", env, "--run", str(dep_run),
                    "--extractor", str(head_run), "--data", str(data)] + fixed
        elif cell == "cparam":
            args = [py, script, "--env", env, "--ctool-run", str(dep_run),
                    "--cparam-run", str(head_run), "--data", str(data)] + fixed
        else:
            args = [py, script, "--env", env, "--ctool-run", str(dep_run),
                    "--cgen-run", str(head_run), "--data", str(data)] + fixed
        meta_dir = head_run

    if extra:
        args += list(extra)
    sess = f"eval_{batch}_{model}_{cell}"
    return sess, " ".join(shlex.quote(str(a)) for a in args), meta_dir


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["tool", "call"],
                    help="tool=tool cell (run first) / call=parameter cell (consumes the tool cell's threshold)")
    ap.add_argument("--batch", required=True, help="run_id prefix, e.g. c2")
    ap.add_argument("--data-root", required=True, help="dataset version dir")
    ap.add_argument("--env", required=True,
                    choices=["appworld", "alfworld", "bfcl", "tales"])
    ap.add_argument("--placement", required=True, help="card-scheduling table json")
    ap.add_argument("--dry-run", action="store_true", help="print only, do not launch")
    args = ap.parse_args()

    LOGD.mkdir(exist_ok=True)
    plan = []
    for p in json.load(open(args.placement)):
        sess, cmd, meta_dir = build(args.stage, args.batch, args.data_root,
                                    args.env, p["model"], p["cell"],
                                    p.get("extra"))
        plan.append((p["host"], p["gpu"], sess, cmd,
                     f"{LOGD}/{sess}.log", meta_dir))

    if args.dry_run:
        for host, gpu, sess, cmd, log, meta_dir in plan:
            print(f"[dry-run] {host} gpu{gpu} {sess}\n    {cmd}")
        print(f"\n{len(plan)} cells total (dry-run, not launched)")
        return

    for host, gpu, sess, cmd, log, meta_dir in plan:
        launch_and_register(host, gpu, sess, cmd, log, meta_dir, args.stage,
                            args.batch, args.placement)
    time.sleep(6)
    print("\n--- alive check ---")
    for host, gpu, sess, cmd, log, meta_dir in plan:
        print(f"{sess}: {'ALIVE' if has_session(host, sess) else 'DEAD'}")


if __name__ == "__main__":
    main()
