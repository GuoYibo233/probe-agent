"""θ sweep driver shell: runs run+score across a list of θ values automatically, and
assembles a six-point curve into the main report.

The question this answers: the eval main report needs to switch from "pin down a risk
cell and report two points" to "sweep a curve against the trigger threshold," with θ
(or coverage, converted) on the x-axis and two y-axis lines -- how many tokens were
saved, and how much the accuracy dropped.
(Decided by the user 2026-08-01; see the WORKPLAN "2026-08-01 schedule" for the plan;
six grid points: 0.50/0.70/0.80/0.875/0.925/0.95)

Why this shell is needed: changing θ used to mean manually re-running plan/run/score
each time, and doing that five times makes it easy to miss a parameter or miss
recording something; and the run stage has to queue across multiple gpt-oss services,
so manual scheduling inevitably leaves some services idle.

Two subcommands:
  run    Given a list of run directories + a pool of service addresses, run the run
         stage concurrently and score each one. One θ occupies one service; when a
         service frees up it picks up the next θ. Idempotent: a θ that already has
         INJECT_REPORT.json is skipped outright, so resuming after a break doesn't
         recompute it.
  curve  Assembles the already-completed θ directories into a curve (markdown table +
         json).

Hard rules for the convention (the precondition for the curve to be valid):
- Each point may differ only in the θ variable. The plan stage's
  ctool/cgen/data/traj_root/miss_policy must be completely identical, and the run
  stage's arms/max_tokens/concurrency must also match -- changing concurrency changes
  the server-side batch composition, which causes numeric jitter in the continuation
  token counts (this known discrepancy is already listed at the top of
  replay_inject.py). This shell uses the same --concurrency for every θ.
- Token savings use the **full deployment account**, not "the average over events
  where injection succeeded":
      token-savings ratio = Sum(tokens saved by the inject segment) / Sum(tokens the nofill segment used across all fired events)
  The denominator is **all fired events**. Events that fired but weren't injected
  because the prediction was wrong (the skip convention) save 0 but still count in
  the denominator -- otherwise the cost of "the probe guessed wrong" would be erased
  from the token-savings axis, reporting an overly optimistic number.
- The accuracy axis measures **call-consistency rate** (whether the predicted whole
  call matches the real one), **not task-level performance**. The two conventions
  differ like this:
    skip cell    a wrong guess is not injected, so the cost of the wrong guess never
                 enters the injected-content account (optimistic)
    execute cell a wrong guess is injected too (injecting a real error), so the cost
                 is accounted for -- but what it measures is still **single-step**
                 call-consistency. execute **cannot produce appworld's Test score**:
                 an event only continues writing for one step, doesn't run to
                 completion, and doesn't call world.evaluate(). A true task-level axis
                 needs a separate in-loop rollout (attach the probe inside the
                 collection loop, inject when it fires, run the whole task through to
                 evaluation) -- that's a new batch of collection, out of scope for
                 this shell.
  Writing the execute cell into the report as "task-level accuracy" would be
  misreporting.
- The execute cell adds two preprocessing stages (both pure CPU, no GPU used, **and
  can run in parallel with other θ points' run stages**): exec_calls.py does the real
  execution -> merge-exec assembles plan_exec.jsonl. The dependency order is
  plan -> exec -> merge-exec -> run -> score; this shell's run stage points
  --plan-file at plan_exec.jsonl, and checks before launching whether the exec stage
  was missed.
- **Every point's plan stage must use the same parameters and the same machine**,
  especially `--bs`, which must match. Observed (2026-08-01, θ=0.925 run twice: r10
  used `--bs 32` on tokyo105, th0925 used the default `--bs 8` on tokyo106): the
  probe-firing layer is fully reproducible -- the set of fired events, trigger
  sentence positions, depth, and tool-level predictions all show zero difference;
  the divergence shows up in generation on the args pipeline, where 14/1061 entries
  (1.3%) produced different calls (example: on the same event r10 wrote
  show_api_doc(...show_album), th0925 wrote ...show_liked_songs), with full_call_ok
  differing by 7 and injectable counts 689 vs 686.
  The identified cause is **batch size changing**: left-padding length changes with
  it, floating-point rounding in the batched forward pass differs, and argmax flips
  at near-ties. (Separately, 446/1061 conf values differ at the 7th decimal place,
  which is CPU softmax reduction order varying with thread count -- it doesn't change
  any firing decision, provable by zero difference in sent_idx.)
  The impact is only 0.4%, far smaller than the gap between θ points, but mixing
  parameters would introduce a heterogeneous point into the curve.
  Hence the hard rule: all six points of one curve use the same --bs and the same
  machine, and this must be stated in the report.

Usage:
  # run stage: spread six θ values across three dedicated services
  cprobe-env/bin/python pipeline/inject/sweep_theta.py run \\
      --runs pipeline/inject/runs/aw_gptoss_th050,...,aw_gptoss_th095 \\
      --services http://tokyo108:8111/v1,http://tokyo108:8112/v1,http://tokyo108:8113/v1

  # curve assembly
  cprobe-env/bin/python pipeline/inject/sweep_theta.py curve \\
      --runs pipeline/inject/runs/aw_gptoss_th050,... \\
      --out pipeline/inject/THETA_CURVE
"""

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PY = str(ROOT / "cprobe-env" / "bin" / "python")
REPLAY = str(HERE / "replay_inject.py")

# print lock: serializes multiple threads writing to stdout at the same time
_PRINT = threading.Lock()


def say(msg):
    with _PRINT:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ------------------------------------------------------------------ run

def service_alive(url, timeout=10):
    """Probe /v1/models for whether gpt-oss-120b is there. Confirm the service is up before sending requests, otherwise a whole round runs for nothing."""
    probe = url.rstrip("/")
    if probe.endswith("/v1"):
        probe += "/models"
    else:
        probe += "/v1/models"
    try:
        with urllib.request.urlopen(probe, timeout=timeout) as r:
            return b"gpt-oss-120b" in r.read()
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def config_of(d, plan_file="plan.jsonl"):
    """The config corresponding to the plan file. Once the execute cell switches to
    plan_exec.jsonl, both the expected row count and the permit convention must be
    read from plan_exec_config.json -- hardcoding a read of plan_config.json would
    get the old statistics from before the exec stage (n_inject was 0 back then), and
    the idempotency check would say "not done" forever."""
    return json.loads((d / (Path(plan_file).stem + "_config.json")).read_text())


def stage_done(d, stage, tag="", plan_file="plan.jsonl"):
    """Idempotency check. run looks at whether raw.jsonl has enough rows, score looks at whether INJECT_REPORT.json exists."""
    if stage == "score":
        return (d / f"INJECT_REPORT{tag}.json").exists()
    raw = d / f"raw{tag}.jsonl"
    if not raw.exists():
        return False
    # expected row count = nofill (one per fired event) + inject (one per actual injection)
    cfg = config_of(d, plan_file)
    want = cfg["n_planned"] + cfg["n_inject"]
    got = sum(1 for _ in open(raw))
    # allow a handful of requests to fail (r10 had 1 failure), within 1% counts as done
    return got >= want * 0.99


def one_theta(d, svc, a):
    """run + score for one θ, with a directory lock. Returns (dir, ok, note).

    The same θ must not be run by two pools at once. The run stage has its own
    resume-from-break support (reads raw.jsonl to build the completed set and only
    fills in what's missing), so **killing and restarting a single process is safe
    and loses nothing**; but two processes running in parallel would each read the
    completed set once and then both append to the same raw.jsonl at the same time,
    duplicating work and writing duplicate rows.
    The lock file records the pid and start time, to help tell a stale lock from a
    process that's really still running.
    """
    d = Path(d)
    lk = d / ".run_lock"
    if lk.exists():
        try:
            info = json.loads(lk.read_text())
        except Exception:
            info = {}
        return (str(d), False,
                f"held by another process (lock {lk.name} pid={info.get('pid')} "
                f"started at {info.get('t')}); confirm no process is running before deleting this lock file")
    lk.write_text(json.dumps(dict(pid=os.getpid(),
                                  t=time.strftime("%F %T"), svc=svc)))
    try:
        return _one_theta(d, svc, a)
    finally:
        lk.unlink(missing_ok=True)


def _one_theta(d, svc, a):
    cfg = config_of(d, a.plan_file)
    theta = cfg["theta"]
    log = HERE / "logs" / f"new1_thsw_run_{d.name}.log"
    log.parent.mkdir(parents=True, exist_ok=True)

    if stage_done(d, "run", a.tag, a.plan_file):
        say(f"θ={theta} run section already finished, skip")
    else:
        cmd = [PY, REPLAY, "run",
               "--plan", str(d / a.plan_file),
               "--base-url", svc,
               "--model", a.model,
               "--arms", a.arms,
               "--concurrency", str(a.concurrency),
               "--max-tokens", str(a.max_tokens),
               "--timeout", str(a.timeout)]
        if a.tag:
            cmd += ["--tag", a.tag]
        say(f"θ={theta} run section launched -> {svc} (expecting "
            f"{cfg['n_planned'] + cfg['n_inject']} entries, log {log.name})")
        # append, don't truncate: the run stage can resume from a break, and after a restart the previous round's log should stay around to check
        with open(log, "a") as f:
            f.write(f"\n# [{time.strftime('%F %T')}] {' '.join(cmd)}\n")
            f.flush()
            rc = subprocess.run(cmd, cwd=str(ROOT), stdout=f,
                                stderr=subprocess.STDOUT).returncode
        if rc != 0:
            return (str(d), False, f"run section exit code {rc}, check {log}")
        if not stage_done(d, "run", a.tag, a.plan_file):
            return (str(d), False, f"run section finished but outputs are insufficient, check {log}")
        say(f"θ={theta} run section finished")

    if stage_done(d, "score", a.tag, a.plan_file):
        say(f"θ={theta} score already finished, skip")
        return (str(d), True, "done (skip)")
    cmd = [PY, REPLAY, "score", "--run-dir", str(d),
           "--plan-file", a.plan_file]
    if a.tag:
        cmd += ["--tag", a.tag]
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    if r.returncode != 0:
        return (str(d), False, f"score exit code {r.returncode}: {r.stderr[-400:]}")
    say(f"θ={theta} score finished")
    return (str(d), True, "ok")


def cmd_run(a):
    dirs = [Path(x.strip()) for x in a.runs.split(",") if x.strip()]
    svcs = [x.strip() for x in a.services.split(",") if x.strip()]
    missing = [d for d in dirs if not (d / a.plan_file).exists()]
    if missing and not a.skip_missing:
        raise SystemExit(f"these θ do not have {a.plan_file} yet (plan section not finished? "
                         "execute mode also needs exec_calls.py + merge-exec finished):\n  "
                         + "\n  ".join(str(d) for d in missing))
    if missing:
        # for wave-based launching: whichever plan stage finishes first runs first, don't leave services waiting idle
        say(f"skipping θ not yet ready (missing {a.plan_file}):"
            + ", ".join(d.name for d in missing))
        dirs = [d for d in dirs if d not in missing]
        if not dirs:
            raise SystemExit("no θ is ready, not launching")
    # dependency order check for the execute cell: plan -> exec -> merge-exec -> run.
    # missing the exec stage means running a whole round on a service with a pile of
    # empty injection content; block it before launching
    pend = []
    for d in dirs:
        n = sum(1 for l in open(d / a.plan_file)
                if json.loads(l)["inject_source"] == "exec_pending")
        if n:
            pend.append(f"{d.name}: {n} events are still exec_pending")
    if pend:
        raise SystemExit("these θ have unfinished exec segments (pure CPU, no card needed; backfill them first):\n  "
                         + "\n  ".join(pend))
    dead = [s for s in svcs if not service_alive(s)]
    if dead:
        raise SystemExit("these services failed the liveness probe; start the services first:\n  " + "\n  ".join(dead))
    say(f"{len(dirs)} θ values spread across {len(svcs)} services, "
        f"concurrency={a.concurrency} arms={a.arms}")

    # service pool: one θ occupies one service, returns it to the pool when done, picks up the next one when free
    pool = queue.Queue()
    for s in svcs:
        pool.put(s)

    def work(d):
        svc = pool.get()
        try:
            return one_theta(d, svc, a)
        finally:
            pool.put(svc)

    results = []
    # start the larger θ points first (the ones that fire more run first), so a big job doesn't get left dragging at the tail end
    order = sorted(dirs, key=lambda d: -config_of(d, a.plan_file)["n_planned"])
    with ThreadPoolExecutor(max_workers=len(svcs)) as ex:
        futs = {ex.submit(work, d): d for d in order}
        for fu in as_completed(futs):
            results.append(fu.result())

    print("\n=== θ sweep results ===")
    bad = 0
    for d, ok, note in sorted(results):
        print(f"{'OK ' if ok else 'FAIL'} {Path(d).name:28s} {note}")
        bad += (not ok)
    if bad:
        raise SystemExit(f"{bad} θ values failed to run, don't rush to assemble the curve")
    print("all done, you can run the curve subcommand to assemble the curve")


# ---------------------------------------------------------------- curve

def load_point(d, tag=""):
    """Read one θ directory and compute the honest numbers for this point on the curve."""
    d = Path(d)
    rep_p = d / f"INJECT_REPORT{tag}.json"
    per_p = d / f"per_event{tag}.jsonl"
    if not rep_p.exists():
        return None
    rep = json.loads(rep_p.read_text())
    cfg = rep["config"]
    per = [json.loads(l) for l in open(per_p)]
    nof = [r for r in per if r["arm"] == "nofill"]
    inj = [r for r in per if r["arm"] == "inject"]

    # Convention tag: the new score version replaced saved_tok with the original-trajectory
    # baseline comparison (saved_baseline="traj"); the old convention's numbers moved into the
    # nofill_delta column. Every number on the curve must use the same basis as the historical
    # points (nofill denominator), so traj reports now always read nofill_delta.
    sb = rep.get("saved_baseline", "nofill")
    if sb == "nofill":
        sv_of = lambda r: r["saved_tok"]
    elif sb == "traj":
        sv_of = lambda r: r.get("nofill_delta")
    else:
        raise SystemExit(f"{rep_p}: unrecognized saved_baseline={sb!r}")
    if sb == "traj" and inj and all(sv_of(r) is None for r in inj):
        raise SystemExit(f"{per_p}: traj settings but nofill_delta is entirely empty, cannot convert")

    # Deployment tally: the denominator is the nofill token count of **all fire events**
    # (including ones that fired but were not injected); the numerator is the tokens actually
    # saved. Under the skip convention, events that were not injected save 0 but still count
    # toward the denominator.
    denom = sum(r["out_tok"] for r in nof)
    saved = sum(sv_of(r) for r in inj if sv_of(r) is not None)
    n_fired = cfg["n_fired"]
    n_events = cfg["n_events_test"]
    n_inject = cfg["n_inject"]

    # The accuracy axis = call-consistency rate (whether the whole call matches the ground
    # truth), **not task-level score**
    tool_ok = sum(1 for r in nof if r["tool_ok"]) / len(nof) if nof else None
    is_exec = cfg.get("miss_policy") == "execute"
    if is_exec:
        # In execute mode, n_inject/n_fired cannot be used as the call-consistency rate: under
        # exec_scope=all every fire event gets injected, so this ratio is always 1 and would
        # report the accuracy axis as a perfect score. Count full_call_ok in per_event directly
        # instead (the two algorithms give the same value in skip mode, so the algorithm only
        # changes on the execute branch; not a single number on skip's historical curve moves)
        full_ok = (sum(1 for r in nof if r["full_call_ok"]) / len(nof)
                   if nof else None)
    else:
        full_ok = n_inject / n_fired if n_fired else None
    ex = rep.get("exec") or {}

    ia = rep["by_arm"].get("inject", {})
    # Dead-zone diagnostic: what fraction fires only in the last 40% (these lose tokens on average)
    late = sum(1 for r in inj if r["depth"] >= 0.6)

    # -- headroom for a timing head --
    # Same batch of fire events, same denominator; only change one decision -- "which events
    # are actually injected":
    #   current         = inject when the prediction is correct (saved_ratio_deployed above)
    #   depth threshold = inject only at certain proportions into the thinking segment (how
    #                      much an existing signal can capture)
    #   oracle timing   = inject only the events that, in hindsight, actually save tokens
    #                      (the ceiling of perfect timing)
    # The gap among the three is a direct measure of whether timing is worth learning.
    injd = {r["event"]: r for r in inj}
    nofd = {r["event"]: r for r in nof}

    def spend(fire):
        return sum((injd[e]["out_tok"] if (e in injd and fire(e))
                    else nofd[e]["out_tok"]) for e in nofd)

    def ratio(fire):
        return (denom - spend(fire)) / denom if denom else None

    oracle = ratio(lambda e: (sv_of(injd[e]) or 0) > 0)
    best_cut, best_r = None, -1e9
    for c in [i / 20 for i in range(1, 21)]:
        r = ratio(lambda e, c=c: injd[e]["depth"] < c)
        if r is not None and r > best_r:
            best_cut, best_r = c, r
    losing = [r for r in inj if (sv_of(r) or 0) <= 0]

    # The saved_* aggregates under by_arm are in the original-trajectory convention in the
    # traj report; the curve needs the nofill convention, so it must be computed fresh from
    # per_event (the algorithm matches replay_inject's agg exactly)
    if sb == "traj":
        sv = sorted(x for x in (sv_of(r) for r in inj) if x is not None)
        sv_mean = round(sum(sv) / len(sv), 1) if sv else None
        sv_median = sv[len(sv) // 2] if sv else None
        sv_pos = (round(sum(1 for x in sv if x > 0) / len(sv), 4)
                  if sv else None)
    else:
        sv_mean = ia.get("saved_tok_mean")
        sv_median = ia.get("saved_tok_median")
        sv_pos = ia.get("saved_positive")
    return dict(
        theta=cfg["theta"], miss_policy=cfg["miss_policy"],
        theta_source=cfg.get("theta_source", "risk-derived"),
        n_events=n_events, n_fired=n_fired, n_inject=n_inject,
        coverage=round(n_fired / n_events, 4) if n_events else None,
        # -- y-axis 1: tokens saved --
        saved_tok_total=saved,
        nofill_tok_total=denom,
        saved_ratio_deployed=round(saved / denom, 5) if denom else None,
        saved_tok_mean_injected=sv_mean,
        saved_tok_median_injected=sv_median,
        saved_positive=sv_pos,
        per_event_baseline=sb,
        # -- y-axis 2: call-consistency rate (**not task-level score**) --
        tool_ok=round(tool_ok, 4) if tool_ok is not None else None,
        full_call_ok=round(full_ok, 4) if full_ok is not None else None,
        # -- execute-mode only: the cost of a wrong guess --
        exec_error_rate=ex.get("exec_error_rate"),
        n_exec_error=ex.get("n_exec_error"),
        n_exec_missing=ex.get("n_exec_missing"),
        n_exec_drift=ex.get("n_drift"),
        exec_acceptance=(f"{ex['acceptance_matched']}/{ex['acceptance_n']}"
                         if ex.get("acceptance_n") else None),
        # -- mechanism diagnostics --
        adopted=ia.get("advanced"), repeated=ia.get("repeated_injected"),
        truncated=ia.get("truncated"),
        # Runaway rate: the continuation keeps writing until it hits the max_tokens cap before
        # stopping. This is itself an outcome -- injection pushes it down (measured at θ=0.95:
        # 8.0% without injection, 4.8% with injection); it is also the source of instability in
        # sum-type metrics: one runaway generation produces ~8192 tokens versus a few hundred for
        # a normal one, so flipping a single event swings the sum by eight thousand, and whether
        # it flips depends only on floating-point noise.
        trunc_nofill=(round(sum(r["finish_reason"] == "length" for r in nof)
                            / len(nof), 4) if nof else None),
        trunc_inject=(round(sum(r["finish_reason"] == "length" for r in inj)
                            / len(inj), 4) if inj else None),
        late_trigger_share=round(late / len(inj), 4) if inj else None,
        # -- headroom for a timing head --
        saved_ratio_oracle_timing=round(oracle, 5) if oracle is not None else None,
        saved_ratio_best_depth=round(best_r, 5) if best_r > -1e8 else None,
        best_depth_cut=best_cut,
        headroom_captured=(round((saved / denom) / oracle, 4)
                           if oracle and denom and oracle > 0 else None),
        n_losing_inject=len(losing),
        tok_lost_by_losing=-sum(sv_of(r) or 0 for r in losing),
        tok_gained_by_winning=sum(sv_of(r) for r in inj
                                  if (sv_of(r) or 0) > 0),
        run_dir=str(d))


def cmd_curve(a):
    dirs = [x.strip() for x in a.runs.split(",") if x.strip()]
    ctrl_dirs = [x.strip() for x in (a.control or "").split(",") if x.strip()]
    pts, skipped = [], []
    for d in dirs:
        p = load_point(d, a.tag)
        (pts if p else skipped).append(p or d)
    ctrls = [q for q in (load_point(d, a.tag) for d in ctrl_dirs) if q]
    if not pts:
        raise SystemExit("not a single point assembled (none scored yet?)")
    dup = {p["theta"] for p in pts}
    if len(dup) != len(pts):
        raise SystemExit(
            f"the main curve has duplicate θ values ({sorted(dup)}) -- two rows for the same θ make the report self-contradictory."
            "pass copies such as architecture controls / settings controls via --control, don't mix them into --runs.")
    pts.sort(key=lambda p: p["theta"])
    ctrls.sort(key=lambda p: p["theta"])

    pol = sorted({p["miss_policy"] for p in pts})
    L = ["# θ sweep curve: tokens saved vs accuracy", "",
         f"- points {len(pts)}  θ from {pts[0]['theta']} to {pts[-1]['theta']}",
         f"- miss_policy = {','.join(pol)}",
         f"- total events {pts[0]['n_events']} (all tool-call events in the test segment)", ""]
    if len(pol) > 1:
        L.append("> ⚠️ miss_policy is inconsistent across points, cannot be plotted on the same curve.")
        L.append("")
    L += [
        "> **token savings ratio = deployment total**: the numerator is the total tokens actually saved in the inject segment,",
        "> the denominator is the total tokens in the nofill segment over **all fire events**. Events that fired but predicted wrong,",
        "> and thus were not injected save 0 but still count toward the denominator -- the cost of the probe's wrong guesses must not be erased from this axis.",
        "> **the accuracy axis measures call consistency rate** (whether the whole predicted call matches the real one),",
        "> **not task-level score**.",
        "> adoption rate = the continuation went and did something else (meaning it accepted the injection); re-call rate = the injected tool was called again."]
    if "skip" in pol:
        L += ["> **skip settings**: if the prediction is wrong, don't inject, so the cost of a wrong guess doesn't enter "
              "the **injected content** ledger (it only enters the token-savings denominator)."]
    if "execute" in pol:
        L += ["> **execute settings**: inject even when the prediction is wrong -- put the predicted call back into the real "
              "appworld environment to execute, and inject whatever comes back (errors included); only then does the cost of a wrong guess fully enter the ledger.",
              "> but what it measures is still the **single-step call consistency rate**: one event continues only one step, doesn't run to completion,",
              "> and doesn't call world.evaluate(). **execute cannot give appworld's Test "
              "score**; writing it up as 'task-level accuracy' is misreporting."]
    L += ["", "## main table", "",
         "| θ | coverage | fire | inject | token savings ratio (deployed) | total tokens saved | "
         "mean saved per injection | median saved per injection | savings positive | tool correct | whole-call correct | adopted | re-called | late-fire share |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for p in pts:
        L.append(
            f"| {p['theta']} | {p['coverage']} | {p['n_fired']} | "
            f"{p['n_inject']} | {p['saved_ratio_deployed']} | "
            f"{p['saved_tok_total']} | {p['saved_tok_mean_injected']} | "
            f"{p['saved_tok_median_injected']} | {p['saved_positive']} | "
            f"{p['tool_ok']} | {p['full_call_ok']} | {p['adopted']} | "
            f"{p['repeated']} | {p['late_trigger_share']} |")

    # List the main figure's two lines in a separate narrow table, ready to copy straight into the paper
    L += ["", "## main chart, two lines (x-axis is coverage)", "",
          "| coverage | θ | token savings ratio | call consistency rate |", "|---|---|---|---|"]
    for p in pts:
        L.append(f"| {p['coverage']} | {p['theta']} | "
                 f"{p['saved_ratio_deployed']} | {p['full_call_ok']} |")

    if "execute" in pol:
        L += ["", "## execute tier: what the cost of a wrong guess looks like", "",
              "> the real execution's return is injected as-is, errors included. **error rate** = the share of the probe's "
              "predicted calls that simply don't run in the real environment;",
              "> **acceptance line** is, among events that hit and whose code block contains only one call, the count where the "
              "execution output is character-for-character identical to the result recorded in the trajectory (this column shows whether the quote-completion step got it wrong).",
              "> **prefix drift** is when the output at replay to that step doesn't match what was recorded -- these events "
              "were executed with the wrong state and can't be counted as real.",
              "",
              "| θ | inject | execution errors | error rate | no execution record | prefix drift | acceptance line |",
              "|---|---|---|---|---|---|---|"]
        for p in pts:
            if p["miss_policy"] != "execute":
                continue
            L.append(f"| {p['theta']} | {p['n_inject']} | "
                     f"{p['n_exec_error']} | {p['exec_error_rate']} | "
                     f"{p['n_exec_missing']} | {p['n_exec_drift']} | "
                     f"{p['exec_acceptance']} |")

    # Headroom for a timing head: same batch of fire events, same denominator, only change one decision -- "which ones are actually injected"
    L += ["", "## is timing worth learning (same batch of fire events, only the fire-moment decision changes)", "",
          "> all three columns use deployment-total settings with the same denominator. **current** = inject when the prediction is right;",
          "> **depth threshold** = inject only at a few fixed proportions into the thinking segment (an off-the-shelf signal, nothing to learn);",
          "> **god timing** = inject only, after the fact, on events that actually save (the upper bound of perfect timing).",
          "> the ratio reaching the upper bound = current / god timing. The lower this column, the more room a timing head has.",
          "",
          "| θ | current | depth threshold (best cut) | god timing | reaches upper bound | "
          "token-losing injections | saved | net loss |",
          "|---|---|---|---|---|---|---|---|"]
    for p in pts:
        L.append(
            f"| {p['theta']} | {p['saved_ratio_deployed']} | "
            f"{p['saved_ratio_best_depth']} (depth<{p['best_depth_cut']}) | "
            f"{p['saved_ratio_oracle_timing']} | {p['headroom_captured']} | "
            f"{p['n_losing_inject']}/{p['n_inject']} | "
            f"{p['tok_gained_by_winning']} | {p['tok_lost_by_losing']} |")
    if ctrls:
        # Control point: same θ, same plan, rerun with only the serving-side conditions changed
        # (card type / load / concurrency). The six points on the curve itself must share the
        # same setup; this table answers "how much does changing conditions actually change the
        # result," i.e. how much of the difference on the curve could just be serving noise.
        base = {p["theta"]: p for p in pts}
        L += ["", "## service-side control (same θ, same plan, rerun with only the service conditions changed)", "",
              "> continuation has numerical jitter under changes in server-side batch composition "
              "(replay_inject.py's file header already lists this known bias).",
              "> this table measures exactly that jitter: same θ, same plan, rerun with a different batch of services,",
              "> how much the token savings ratio differs. **this gap is the curve's noise floor** -- on the curve, anything smaller than",
              "> it, fluctuations cannot be read as a real trend.", "",
              "| θ | main curve token savings ratio | control token savings ratio | diff | "
              "main curve call consistency rate | control call consistency rate | control source |",
              "|---|---|---|---|---|---|---|"]
        gaps = []
        for q in ctrls:
            b = base.get(q["theta"])
            if b is None:
                L.append(f"| {q['theta']} | (no such point on the main curve) | "
                         f"{q['saved_ratio_deployed']} | — | — | "
                         f"{q['full_call_ok']} | {Path(q['run_dir']).name} |")
                continue
            g = (q["saved_ratio_deployed"] - b["saved_ratio_deployed"]
                 if None not in (q["saved_ratio_deployed"],
                                 b["saved_ratio_deployed"]) else None)
            if g is not None:
                gaps.append(abs(g))
            L.append(
                f"| {q['theta']} | {b['saved_ratio_deployed']} | "
                f"{q['saved_ratio_deployed']} | "
                f"{('%+.5f' % g) if g is not None else '—'} | "
                f"{b['full_call_ok']} | {q['full_call_ok']} | "
                f"{Path(q['run_dir']).name} |")
        if gaps:
            L += ["", f"**noise floor of sum-type metrics = {max(gaps):.5f}**"
                  f"(the largest absolute difference among control points, {len(gaps)} pairs in total)."]

        # Compute the noise floor per metric and compare it against that metric's span on the
        # main curve -- an axis where the noise exceeds the span cannot be plotted at all. The
        # sum-type "token-saved ratio" metric fails exactly this way in practice: one runaway
        # generation produces ~8192 tokens, and whether it flips depends only on floating-point
        # noise, so the total ends up dominated by that single coin flip.
        METRICS = [("token savings ratio (sum)", "saved_ratio_deployed"),
                   ("token savings median", "saved_tok_median_injected"),
                   ("savings positive", "saved_positive"),
                   ("call consistency rate", "full_call_ok"),
                   ("adoption rate", "adopted"),
                   ("runaway rate (no injection)", "trunc_nofill"),
                   ("runaway rate (injected)", "trunc_inject")]
        L += ["", "### per metric: noise floor vs main curve span", "",
              "> noise floor = the largest absolute difference between two runs at the same θ across the three control pairs (only the service conditions changed).",
              "> span = for this metric, the max minus the min across the six points on the main curve.",
              "> **a metric whose noise floor ≥ span cannot be plotted in the main chart** -- all it measures is jitter.", "",
              "| metric | noise floor | main curve span | span/noise | plottable |",
              "|---|---|---|---|---|"]
        for name, key in METRICS:
            ns = [abs(q[key] - base[q["theta"]][key])
                  for q in ctrls
                  if q["theta"] in base and q.get(key) is not None
                  and base[q["theta"]].get(key) is not None]
            vs = [p[key] for p in pts if p.get(key) is not None]
            if not ns or len(vs) < 2:
                continue
            nf, span = max(ns), max(vs) - min(vs)
            r = span / nf if nf else float("inf")
            L.append(f"| {name} | {nf:.4f} | {span:.4f} | {r:.1f}x | "
                     f"{'yes' if r >= 3 else ('borderline' if r >= 2 else '**no**')} |")
        L += ["", "> criterion: span must be at least 3x the noise to be readable, 2-3x is borderline, under 2x is unreadable."]

    if skipped:
        L += ["", "## points not yet assembled (no INJECT_REPORT.json)", ""]
        L += [f"- {s}" for s in skipped]

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".md").write_text("\n".join(L) + "\n")
    out.with_suffix(".json").write_text(
        json.dumps(dict(points=pts, controls=ctrls, skipped=skipped),
                   ensure_ascii=False,
                   indent=1))
    print("\n".join(L))
    print(f"\nwritten -> {out.with_suffix('.md')} / {out.with_suffix('.json')}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("run", help="run each θ's run+score concurrently to completion")
    p.add_argument("--runs", required=True, help="comma-separated run directories")
    p.add_argument("--services", required=True,
                   help="comma-separated service base-urls, one per θ")
    p.add_argument("--model", default="gpt-oss-120b")
    p.add_argument("--arms", default="nofill,inject")
    p.add_argument("--concurrency", type=int, default=16,
                   help="must use the same value across all θ; changing it changes the server-side batch composition")
    p.add_argument("--max-tokens", type=int, default=8192)
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--tag", default="")
    p.add_argument("--plan-file", default="plan.jsonl",
                   help="execute tier uses plan_exec.jsonl (config/idempotency criteria both follow it)")
    p.add_argument("--skip-missing", action="store_true",
                   help="skip, without erroring, θ values whose plan segment hasn't finished (for launching in waves)")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("curve", help="assemble the curve")
    p.add_argument("--runs", required=True)
    p.add_argument("--out", default="pipeline/inject/THETA_CURVE")
    p.add_argument("--control", default="",
                   help="service-side control points (copies with the same θ and plan, rerun with only the service conditions changed), "
                        "listed in a separate table to compute the noise floor, not mixed into the main curve")
    p.add_argument("--tag", default="")
    p.set_defaults(fn=cmd_curve)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
