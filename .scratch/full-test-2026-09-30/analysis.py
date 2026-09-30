#!/usr/bin/env python3
"""The result file of the 2026-09-30 full-test run: one table per question, facts only.

Reads, for each of the 16 runs, the inject or sample directory (`run.py where`), its
score report (the task-level success rows), its records (steps, fires, tokens) and its
heartbeat span, and writes `.scratch/full-test-2026-09-30/report.md`.

    external/probe-env/bin/python .scratch/full-test-2026-09-30/analysis.py
"""
from __future__ import annotations

import glob
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path("/home/y-guo/reproduce/new1")
PY = ROOT / "external/probe-env/bin/python"
OUT = ROOT / ".scratch/full-test-2026-09-30/report.md"
P = "run_2026_09_30_test_split_168_tasks"

PAIRS = {"0.6B full": "qwen3_0pt6b_full_tuning", "4B LoRA": "qwen3_4b_lora_tuning"}
FORMATS = ["p1_e1", "p2_e1", "p2_e2"]
THETAS = ["0.6", "0.9"]


def runs() -> list[dict]:
    """The 16 runs: label, workflow, setting name, and the grouping fields."""
    out = [
        {"label": "baseline", "workflow": "baseline", "setting": f"{P}_baseline", "stage": "sample",
         "arm": "baseline", "pair": "-", "format": "-", "theta": "-"},
        {"label": "no-probe", "workflow": "inject", "setting": f"{P}_arm_no_probe", "stage": "inject",
         "arm": "no_probe", "pair": "-", "format": "-", "theta": "-"},
    ]
    for pair, suffix in PAIRS.items():
        for fmt in FORMATS:
            for theta in THETAS:
                out.append({
                    "label": f"probe {pair} {fmt} theta {theta}", "workflow": "inject",
                    "setting": f"{P}_arm_probe_{suffix}/inject.format='{fmt}',inject.theta={theta}",
                    "stage": "inject", "arm": "probe", "pair": pair, "format": fmt, "theta": theta})
        out.append({
            "label": f"no-fill {pair} theta 0.6", "workflow": "inject",
            "setting": f"{P}_arm_probe_nofill_theta_0pt6_{suffix}", "stage": "inject",
            "arm": "probe_nofill", "pair": pair, "format": "-", "theta": "0.6"})
    return out


def where(workflow: str, setting: str, stage: str) -> Path | None:
    p = subprocess.run([str(PY), "run.py", "where", workflow, setting, stage], cwd=ROOT,
                       capture_output=True, text=True)
    if p.returncode != 0:
        return None
    return Path(p.stdout.strip().splitlines()[-1])


def read_score(path: Path) -> dict | None:
    """success per task from the score report, plus its header numbers."""
    if not path.exists():
        return None
    text = path.read_text()
    head = {}
    m = re.search(r"n_records=(\d+) n_abort=(\d+) success=([\d.]+)", text)
    if m:
        head = {"n": int(m[1]), "n_abort": int(m[2]), "success": float(m[3])}
    per_task = {}
    for line in text.splitlines():
        m = re.match(r"^([0-9a-f]{7}_\d) \| (\d+) \| (True|False) \|", line)
        if m:
            per_task[m[1]] = m[3] == "True"
    return {**head, "per_task": per_task}


def read_records(run_dir: Path) -> dict:
    """steps, fires, fire hits, splices, tokens and the tasks that fired, over the run's records."""
    steps = fires = hits = splices = tok_in = tok_out = 0
    fired_tasks: set[str] = set()
    steps_per_task: list[int] = []
    for path in sorted((run_dir / "records").glob("*.jsonl")):
        rows = [json.loads(line) for line in path.open()]
        task_id = rows[0].get("task_id") if rows else None
        action = {r["step"]: r.get("action") or "" for r in rows if r.get("type") == "env"}
        n_steps = 0
        for r in rows:
            t = r.get("type")
            if t == "env":
                n_steps += 1
            elif t == "gen":
                u = r.get("usage") or {}
                tok_in += u.get("in", 0)
                tok_out += u.get("out", 0)
            elif t == "spec":
                fires += 1
                if task_id:
                    fired_tasks.add(task_id)
                if r.get("exec_code"):
                    splices += 1
                if r["step"] in action and r.get("pred_label") and r["pred_label"] in action[r["step"]]:
                    hits += 1
        steps += n_steps
        steps_per_task.append(n_steps)
    return {"steps": steps, "fires": fires, "hits": hits, "splices": splices, "tok_in": tok_in,
            "tok_out": tok_out, "fired_tasks": fired_tasks,
            "steps_mean": (sum(steps_per_task) / len(steps_per_task)) if steps_per_task else 0.0}


def heartbeat_span_h(run_dir: Path) -> float | None:
    ts = []
    for f in glob.glob(str(run_dir / "heartbeat" / "[0-5]-*.jsonl")):
        for line in open(f):
            try:
                ts.append(json.loads(line)["ts"])
            except (KeyError, ValueError):
                pass
    return (max(ts) - min(ts)) / 3600 if ts else None


def paired(a: dict, b: dict) -> tuple[int, int, int]:
    """Over the tasks both scored: solved by a only, by b only, by both."""
    common = set(a) & set(b)
    a_only = sum(1 for t in common if a[t] and not b[t])
    b_only = sum(1 for t in common if b[t] and not a[t])
    both = sum(1 for t in common if a[t] and b[t])
    return a_only, b_only, both


def pct(x: float | None) -> str:
    return "-" if x is None else f"{100 * x:.1f}%"


def main() -> int:
    rows = []
    for r in runs():
        d = where(r["workflow"], r["setting"], r["stage"])
        s = where(r["workflow"], r["setting"], "score")
        score = read_score(s / "report.md") if s else None
        done = d is not None and (d / "done.json").exists()
        finished = done and score is not None and score.get("n") == 168
        rec = read_records(d) if d and (d / "records").is_dir() else None
        rows.append({**r, "dir": d, "score_dir": s, "score": score, "finished": finished,
                     "rec": rec, "span_h": heartbeat_span_h(d) if d else None,
                     "n_records": len(list((d / "records").glob("*.jsonl"))) if d and (d / "records").is_dir() else 0})

    by_label = {r["label"]: r for r in rows}
    base = by_label["baseline"]["score"]["per_task"] if by_label["baseline"]["score"] else {}
    nop = by_label["no-probe"]["score"]["per_task"] if by_label["no-probe"]["score"] else {}

    lines = ["# Full-test run of 2026-09-30: results", ""]
    lines += ["168 test tasks, seed 42, one run per setting, gpt-oss-120b with instructions v2, history 3 rounds.",
              "The probes are the August imports (0.6B full: ctool `train-f80df32ec8e4`, cgen `train-c01a3052dca5`; "
              "4B LoRA: ctool `train-4bd4a2483c43`, cgen `train-9fc3053bacbb`).",
              "Every number below is read from the run's score report, records or heartbeats; "
              "`solved` is the score report's success count over 168 tasks.", ""]

    unfinished = [r for r in rows if not r["finished"]]
    if unfinished:
        lines += ["**Unfinished runs (numbers below are partial for them):** " +
                  ", ".join(f"{r['label']} ({r['n_records']}/168 records)" for r in unfinished), ""]

    # 1. every run
    lines += ["## 1. Every run", "",
              "| run | key | solved | aborts | vs baseline: +/- | vs no-probe: +/- | tasks fired | fires | fire hit rate | steps/task | out tokens/task | hours |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        sc, rec = r["score"], r["rec"]
        solved = f"{sum(sc['per_task'].values())}/{sc['n']}" if sc else "-"
        aborts = sc["n_abort"] if sc else "-"
        vb = vn = "-"
        if sc and base and r["label"] != "baseline":
            a, b, _ = paired(sc["per_task"], base)
            vb = f"+{a} / -{b}"
        if sc and nop and r["label"] not in ("baseline", "no-probe"):
            a, b, _ = paired(sc["per_task"], nop)
            vn = f"+{a} / -{b}"
        key = d.name if (d := r["dir"]) else "-"
        n = r["n_records"] or 1
        fired = f"{len(rec['fired_tasks'])}/{r['n_records']}" if rec else "-"
        fires = rec["fires"] if rec else "-"
        hit = pct(rec["hits"] / rec["fires"]) if rec and rec["fires"] else "-"
        spt = f"{rec['steps_mean']:.1f}" if rec else "-"
        tok = f"{rec['tok_out'] / n:.0f}" if rec else "-"
        hours = f"{r['span_h']:.1f}" if r["span_h"] else "-"
        lines.append(f"| {r['label']} | {r['stage']}-{key} | {solved} | {aborts} | {vb} | {vn} | {fired} | {fires} | {hit} | {spt} | {tok} | {hours} |")
    lines += ["", "`vs baseline: +a / -b`: a tasks this run solved that the baseline did not, b the reverse; the same against the no-probe run. "
              "`fire hit rate`: share of fires whose predicted API name is in the code the agent executed at that step.", ""]

    # 2. means by group
    probe_rows = [r for r in rows if r["arm"] == "probe" and r["score"]]
    def mean_solved(sel):
        vals = [sum(r["score"]["per_task"].values()) for r in sel]
        return f"{sum(vals) / len(vals):.1f} (n={len(vals)}, {min(vals)}-{max(vals)})" if vals else "-"
    lines += ["## 2. Solved tasks, mean over runs of a group (probe arm only)", "",
              "| group | mean solved of 168 (n runs, min-max) |", "|---|---|"]
    for pair in PAIRS:
        lines.append(f"| pair {pair} | {mean_solved([r for r in probe_rows if r['pair'] == pair])} |")
    for fmt in FORMATS:
        lines.append(f"| format {fmt} | {mean_solved([r for r in probe_rows if r['format'] == fmt])} |")
    for theta in THETAS:
        lines.append(f"| theta {theta} | {mean_solved([r for r in probe_rows if r['theta'] == theta])} |")
    lines.append(f"| all probe-arm runs | {mean_solved(probe_rows)} |")
    for lab in ("baseline", "no-probe", "no-fill 0.6B full theta 0.6", "no-fill 4B LoRA theta 0.6"):
        sc = by_label[lab]["score"]
        lines.append(f"| {lab} | {sum(sc['per_task'].values()) if sc else '-'} |")
    lines.append("")

    # 3. fired vs not fired tasks
    lines += ["## 3. Success on tasks where the probe fired at least once, against the same tasks in the no-probe run", "",
              "| run | tasks fired | solved among them | no-probe solved the same tasks | tasks never fired | solved among them | no-probe solved the same tasks |",
              "|---|---|---|---|---|---|---|"]
    for r in rows:
        if r["arm"] not in ("probe", "probe_nofill") or not r["score"] or not r["rec"] or not nop:
            continue
        pt = r["score"]["per_task"]
        fired = [t for t in pt if t in r["rec"]["fired_tasks"]]
        quiet = [t for t in pt if t not in r["rec"]["fired_tasks"]]
        lines.append(f"| {r['label']} | {len(fired)} | {sum(pt[t] for t in fired)} | {sum(nop.get(t, False) for t in fired)} "
                     f"| {len(quiet)} | {sum(pt[t] for t in quiet)} | {sum(nop.get(t, False) for t in quiet)} |")
    lines.append("")

    # 4. task-level agreement
    lines += ["## 4. Tasks by how many of the 14 probe-pair runs solved them", ""]
    counts = defaultdict(int)
    pair_runs = [r for r in rows if r["arm"] in ("probe", "probe_nofill") and r["score"]]
    if pair_runs:
        tasks = set(base) or set(pair_runs[0]["score"]["per_task"])
        for t in tasks:
            counts[sum(r["score"]["per_task"].get(t, False) for r in pair_runs)] += 1
        lines += [f"Over {len(pair_runs)} probe-pair runs with a score.", "",
                  "| solved by k runs | tasks | of which baseline solved | of which no-probe solved |", "|---|---|---|---|"]
        for k in sorted(counts):
            ts = [t for t in tasks if sum(r["score"]["per_task"].get(t, False) for r in pair_runs) == k]
            lines.append(f"| {k} | {len(ts)} | {sum(base.get(t, False) for t in ts)} | {sum(nop.get(t, False) for t in ts)} |")
    lines.append("")

    # 5. where the files are
    lines += ["## 5. Files", "", "| run | run directory | score report |", "|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['label']} | {r['dir'] or '-'} | {(r['score_dir'] / 'report.md') if r['score_dir'] else '-'} |")
    lines += ["", "Registry: `jobs/runs.jsonl` and `jobs/RESULTS.md`; queue logs: `.scratch/full-test-2026-09-30/queue-logs/`.", ""]

    OUT.write_text("\n".join(lines))
    print(f"wrote {OUT} ({len(rows)} runs, {len(unfinished)} unfinished)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
