"""Live-run injection line scorer (cprobe-env, CPU only). Design doc: plans/2026-08-01-live-inject-design.md

Input:
  --live-dir   live_appworld.py's output directory (live_*.jsonl)
  --base-root  comparison = the already-collected trajectory directory
               (envs/runs/w0_aw_official/appworld_gptoss), take only the task_ids
               that appear on the live-run side, paired by task
Output: LIVE_REPORT.{json,md} written into --live-dir

Conventions (design doc §1; flag two points of incomparability: the comparison batch's
service conditions and date both differ from the live run):
- Task success/failure: on the live run, final.eval is a structured dict; on the
  comparison, final.eval is a str, parsed with ast.literal_eval. Both sides go by the
  success field; anything that fails to parse is counted separately as unknown.
- Two token accounts: billed = all completion tokens generated across segments
  (including overflow discarded after a trigger); kept = billed - estimated overflow
  tokens. Overflow is only recorded as a character count -- estimating tokens with the
  gpt-oss tokenizer on the text discarded before injection isn't feasible (the
  original text isn't stored), so kept is reported only on a character basis; billed
  is the sole true account on a token basis. For the comparison side, each step's out
  token count is taken from usage.out (the completion_tokens the server recorded).
- After-the-fact firing account (unknowable at eval time, computed only at scoring
  time): consistency between the predicted call and the first complete call in the
  code block actually emitted at that step (tool-level / whole-call level; whole-call
  level extracts with parse_call's paren balancing, don't compare the whole "apis. to
  end of block" span -- print wrappers and multi-statement blocks would mark even a
  fully correct prediction as inconsistent), and whether that step called the same
  tool again after injection (re-call).
- task_error listed separately: the final that live_appworld backfills for a
  per-task transient failure (service restart / network jitter)
  (abort=task_error:*, steps=-1) is not a real success/failure outcome; it's only
  counted in n_task_error and does not enter live_success's denominator.

Usage:
  cprobe-env/bin/python pipeline/inject/score_live.py \\
      --live-dir pipeline/inject/runs/live_smoke \\
      --base-root envs/runs/w0_aw_official/appworld_gptoss
"""

import argparse
import ast
import glob
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from parse_call import complete_call                         # noqa: E402

AW_CALL = re.compile(r"apis\.(\w+)\.(\w+)\(")


def first_call(code):
    m = AW_CALL.search(code or "")
    return f"apis.{m.group(1)}.{m.group(2)}" if m else None


def norm_call(s):
    """Used for whole-call comparison: strips whitespace differences (gen_call is a
    quote-stripped canonical string, real code has quotes; whole-call consistency is
    judged true only when 'byte-identical after stripping quotes' -- same convention
    as full_call_ok in replay)."""
    return re.sub(r"\s+", "", (s or "").replace('"', "").replace("'", ""))


def success_of(ev):
    if isinstance(ev, dict):
        if "success" in ev:
            return bool(ev["success"])
        return None
    if isinstance(ev, str):
        try:
            d = ast.literal_eval(ev)
            if isinstance(d, dict) and "success" in d:
                return bool(d["success"])
        except Exception:
            pass
        # The comparison trajectory's eval is a truncated str (observed: 135 of 168 w0
        # entries fail literal_eval); the success key is at the start of the string, regex
        # is the fallback (same convention as summarize_full).
        m = re.search(r"'success': (True|False)", ev)
        if m:
            return m.group(1) == "True"
    return None


def read_live(path):
    recs = [json.loads(l) for l in open(path)]
    # When a single task crashes during world setup, the file only has the fallback
    # task_error final, with no meta line -- meta is held up with None, and the caller
    # recovers task_id from the filename.
    meta = recs[0] if recs and recs[0].get("type") == "meta" else None
    gens = [r for r in recs if r.get("type") == "gen"]
    envs = {r["step"]: r for r in recs if r.get("type") == "env"}
    specs = [r for r in recs if r.get("type") == "spec"]
    final = next((r for r in recs if r.get("type") == "final"), None)
    return meta, gens, envs, specs, final


def read_base(path):
    recs = [json.loads(l) for l in open(path)]
    gens = [r for r in recs if r.get("type") == "gen"]
    final = next((r for r in recs if r.get("type") == "final"), None)
    return gens, final


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--live-dir", required=True)
    ap.add_argument("--base-root", required=True)
    a = ap.parse_args()
    live_dir = Path(a.live_dir)
    base_root = Path(a.base_root)

    rows, spec_rows = [], []
    for f in sorted(glob.glob(str(live_dir / "live_*.jsonl"))):
        meta, gens, envs, specs, final = read_live(f)
        tid = ((meta or {}).get("task_id")
               or Path(f).stem[len("live_"):])       # filename live_<task_id>.jsonl
        fmt = (meta or {}).get("format", "note")   # runs before 2026-09-12 carry no format field
        if final is None:
            rows.append(dict(task=tid, arm=(meta or {}).get("arm"), format=fmt,
                             unfinished=True))
            continue
        billed = sum(g["usage"]["gen_tok"] for g in gens)
        reqs = sum(g["usage"]["req"] for g in gens)
        disc_c = sum(g["discard"]["chars"] for g in gens)

        bp = base_root / f"appworld_{tid}.jsonl"
        base = dict(success=None, out_tok=None, steps=None)
        if bp.exists():
            bg, bf = read_base(bp)
            base = dict(
                success=success_of((bf or {}).get("eval")),
                out_tok=sum((g.get("usage") or {}).get("out") or 0
                            for g in bg),
                steps=(bf or {}).get("steps"))

        for s in specs:
            act = (envs.get(s["step"]) or {}).get("action") or ""
            tool_pred = first_call(s["gen_call"])
            tool_real = first_call(act)
            real_call, _ = complete_call(act)
            spec_rows.append(dict(
                task=tid, step=s["step"], conf=s["conf"],
                exec_ok=s["exec_ok"], error_kind=s["error_kind"],
                arg_modes=s["arg_modes"],
                tool_agree=(tool_pred == tool_real and tool_pred is not None),
                call_agree=(real_call is not None and
                            norm_call(s["gen_call"]) == norm_call(real_call)),
                recalled=(tool_pred is not None and tool_pred in act),
                discarded_chars=s["discarded_chars"]))

        rows.append(dict(
            task=tid, arm=(meta or {}).get("arm"), format=fmt,
            success=success_of(final.get("eval")),
            steps=final["steps"], completed=final["completed"],
            task_error=str(final.get("abort") or "").startswith("task_error"),
            n_inject=sum(g.get("n_inject", 0) for g in gens),
            billed_tok=billed, n_req=reqs, discarded_chars=disc_c,
            base_success=base["success"], base_out_tok=base["out_tok"],
            base_steps=base["steps"]))

    errs = [r for r in rows if r.get("task_error")]
    done = [r for r in rows
            if not r.get("unfinished") and not r.get("task_error")]
    paired = [r for r in done if r["base_success"] is not None]

    def rate(xs):
        xs = [x for x in xs if x is not None]
        return round(sum(xs) / len(xs), 4) if xs else None

    summary = dict(
        n_tasks=len(rows), n_done=len(done), n_paired=len(paired),
        n_task_error=len(errs),
        formats=sorted({r["format"] for r in rows}),
        live_success=rate([r["success"] for r in done]),
        base_success=rate([r["base_success"] for r in paired]),
        live_success_paired=rate([r["success"] for r in paired]),
        inject_per_task=rate([r["n_inject"] for r in done]),
        billed_tok_sum=sum(r["billed_tok"] for r in done),
        base_out_tok_sum=sum(r["base_out_tok"] or 0 for r in paired),
        n_spec=len(spec_rows),
        spec_exec_ok=rate([s["exec_ok"] for s in spec_rows]),
        spec_tool_agree=rate([s["tool_agree"] for s in spec_rows]),
        spec_call_agree=rate([s["call_agree"] for s in spec_rows]),
        spec_recalled=rate([s["recalled"] for s in spec_rows]),
        spec_error_kinds=dict(Counter(
            s["error_kind"] for s in spec_rows if s["error_kind"])))

    (live_dir / "LIVE_REPORT.json").write_text(json.dumps(
        dict(summary=summary, tasks=rows, specs=spec_rows),
        ensure_ascii=False, indent=1))

    md = ["# Live-run injection line report", "",
          "the control batch's service conditions and harmony date line both differ from the live run (design doc §1),",
          "the total-token comparison must carry this caveat; billed includes overflow discarded after firing.",
          "n_task_error is the number of tasks with a transient failure (abort=task_error); these tasks are not included in",
          "live_success's denominator; delete the corresponding live_*.jsonl before rerunning for it to be retried.", "",
          "| metric | value |", "|---|---|"]
    if errs:
        md.insert(6, "task_error tasks: " + ", ".join(r["task"] for r in errs))
    for k, v in summary.items():
        md.append(f"| {k} | {v} |")
    md += ["", "| task | arm | format | outcome | control outcome | steps | fired | billed tok |"
              " control out tok |", "|---|---|---|---|---|---|---|---|---|"]
    for r in done:
        md.append(f"| {r['task']} | {r['arm']} | {r['format']} | {r['success']} | "
                  f"{r['base_success']} | {r['steps']} | {r['n_inject']} | "
                  f"{r['billed_tok']} | {r['base_out_tok']} |")
    (live_dir / "LIVE_REPORT.md").write_text("\n".join(md) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
