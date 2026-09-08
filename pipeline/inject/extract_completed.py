"""Extract the call completed by splicing back into an arm's continuation in
the experiment, and feed it to exec_calls.py. Spec:
plans/2026-08-01-splice-impl-spec.md §D3

The skeleton arm only pins the tool name; the arguments are written by the
model itself -- so "what this call actually looks like" isn't known until the
continuation comes back. This script uses the same convention as the score
cell's C2: extract the bare call from the continuation in raw<tag>.jsonl by
balancing parentheses, swap it in for gen_call in the plan record, and write
`exec_in_<arm>.jsonl`. exec_calls.py --plan consumes this file; it actually
executes the call in appworld, and only then can it tell whether the call is
correct.

Fields exec_calls.py reads from the plan record (checked field by field in
replay_unit + main): event / unit / step / traj_path / gen_call, plus
full_call_ok and n_calls_in_block via .get. So the plan record is copied in
full here, with not a single field dropped; but full_call_ok describes
whether the cgen draft that got replaced was correct, which is no longer
accurate for the new call -- and it is exactly what exec_calls.py's
--selfcheck and the merge-exec acceptance line use to pick events, so it is
recomputed against the new call (= the new call matches label_call character
for character), and the old value is moved to orig_full_call_ok for the
record. n_calls_in_block and traj_bare_print count the code block recorded in
the trajectory, unrelated to whether the call was swapped, and are kept
as-is.

Where the extraction happens splits into two cases by arm:
- skel_bare / skel_a / skel_b: the skeleton is embedded in analysis, and the
  call starts from the skeleton, so the skeleton must be spliced back onto
  the front of the continuation before searching.
- inject_stop / skel_switch / switch_only: the continuation starts **inside**
  the final channel, so running split_channels directly on text yields an
  empty final, so final = the arm's splice-in string + text.
- nofill / inject: the old convention, search within final after
  split_channels.

Usage:
  python pipeline/inject/extract_completed.py \\
      --run-dir pipeline/inject/runs/aw_gptoss_splice --arms skel_a,switch_only
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import parse_call                                            # noqa: E402
from build_form_table import load_table, skeleton            # noqa: E402

# The spec § pins this name; replay_inject.py has a constant with the same
# name, and the two must match character for character
SWITCH = "<|end|><|start|>assistant<|channel|>final<|message|>"
FENCE_OPEN = "```python\n"
FINAL_OPEN = "<|channel|>final<|message|>"
# [Copied from envs/collect/run_appworld.py:38] uses the same regex to pull
# out the code block
CODE_RE = re.compile(r"```python\s*(.*?)```", re.S)

# Arms whose continuation starts inside the final channel: their text has no
# FINAL_OPEN
ARMS_FINAL = {"inject_stop", "skel_switch", "switch_only"}
# Arms whose skeleton lands in analysis
ARMS_SKEL_ANALYSIS = {"skel_bare", "skel_a", "skel_b"}
# All arms that need a skeleton: without pred_label there's nothing to
# splice, skip directly
ARMS_SKEL = ARMS_SKEL_ANALYSIS | {"skel_switch"}
# Arms whose skeleton is preceded by an opening fence (skel_b is introduced
# in plain text, no fence)
ARMS_FENCED = {"skel_bare", "skel_a", "skel_switch"}


def split_channels(text):
    """Split the continuation into (analysis remainder, final content). [Same as replay_inject.py:632]"""
    if FINAL_OPEN in text:
        head, tail = text.split(FINAL_OPEN, 1)
        return head, tail
    return text, ""


def rebuild_sides(arm, text, skel):
    """Reconstruct the two searchable text segments (analysis side, final side).

    The part spliced into the prompt (skeleton, fence opening) is not in
    text, but the call starts from it, so it must be spliced back in to find
    where the call starts.
    """
    if arm in ARMS_FINAL:
        pre = FENCE_OPEN + skel if arm == "skel_switch" else ""
        return "", pre + text
    if arm in ARMS_SKEL_ANALYSIS:
        analysis, final = split_channels(text)
        pre = FENCE_OPEN if arm in ARMS_FENCED else ""
        return pre + skel + analysis, final
    return split_channels(text)


def call_of(arm, text, skel, pred_label):
    """Extract this arm's complete bare call using the C2 convention. Returns
    (call_out|None, which segment it was found in).

    For skeleton arms, first check whether **that position** in the skeleton
    was completed: the skeleton has no trailing open parenthesis, and
    without anchoring the position, a call the model writes on its own on a
    new line would be mistaken for the skeleton's completion (same
    anchoring as the score cell -- the two conventions must match character
    for character, or per_event's call_out won't match what gets sent to
    execution). When the model itself overrides the skeleton, fall back to
    the body segment and extract the call it actually wrote.
    """
    analysis, final = rebuild_sides(arm, text, skel)
    if arm in ARMS_SKEL and skel and pred_label:
        where = "final" if arm in ARMS_FINAL else "analysis"
        seg = final if arm in ARMS_FINAL else analysis
        pre = FENCE_OPEN if arm in ARMS_FENCED else ""
        call, _ = parse_call.call_at(seg, len(pre + skel) - len(pred_label))
        if call is not None:
            return call, where
    call, _ = parse_call.complete_call(final)
    return (call, "final") if call is not None else (None, None)


def rewritten_in_final(arm, text, skel, pred_label):
    """The skeleton was completed, but did the model switch to a different tool in
    the body segment?

    Same convention as tool_rewritten in the score cell: the tool name of
    the first call in the body segment's code block. For these events, what
    gets sent for real execution is the call at the skeleton, i.e. the call
    the model itself has already abandoned.
    """
    _, final = rebuild_sides(arm, text, skel)
    b = CODE_RE.search(final)
    m = parse_call.CALL_START.search(b.group(1)) if b else None
    return bool(m) and m.group(0)[:-1] != pred_label


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--plan-file", default="plan.jsonl",
                    help="plan file name inside run-dir (the execute version is plan_exec.jsonl)")
    ap.add_argument("--tag", default="", help="suffix for raw<tag>.jsonl")
    ap.add_argument("--arms", required=True,
                    help="comma-separated arm names, one exec_in_<arm>.jsonl per arm")
    ap.add_argument("--form-table", default=None,
                    help="skeleton form table (default pipeline/inject/form_table.json)")
    a = ap.parse_args()

    d = Path(a.run_dir)
    arms = [x.strip() for x in a.arms.split(",") if x.strip()]
    table = load_table(a.form_table)
    plan = {}
    for line in open(d / a.plan_file):
        p = json.loads(line)
        plan[p["event"]] = p
    raw = defaultdict(dict)
    for line in open(d / f"raw{a.tag}.jsonl"):
        o = json.loads(line)
        raw[o["event"]][o["arm"]] = o        # Later writes override earlier ones, same as the score cell

    summary = {}
    for arm in arms:
        rows, stat = [], Counter()
        for ev, byarm in raw.items():
            o = byarm.get(arm)
            p = plan.get(ev)
            if o is None or p is None:
                continue
            if o.get("dry"):                 # dry-run records have no continuation
                stat["dry"] += 1
                continue
            stat["n"] += 1
            # The skeleton uses pred_label, never label (the god's-eye-view red line)
            pred_label = p.get("pred_label")
            if arm in ARMS_SKEL and not pred_label:
                stat["no_pred_label"] += 1
                continue
            skel = skeleton(pred_label, table) if pred_label else ""
            text = o.get("text") or ""
            call, where = call_of(arm, text, skel, pred_label)
            if call is None:
                stat["no_call"] += 1
                continue
            stat[f"found_in_{where}"] += 1
            if where == "analysis" and rewritten_in_final(arm, text, skel,
                                                          pred_label):
                # What gets extracted is the call at the skeleton, but the model switched to
                # a different tool in the body segment: what's sent for execution is the
                # call the model itself has already abandoned. Count these, don't let them
                # mix into the score
                stat["rewritten_in_final"] += 1
            rec = dict(p)
            rec["gen_call"] = call
            rec["source_arm"] = arm
            # full_call_ok in the plan describes whether the cgen draft that got
            # replaced was correct, which is no longer accurate for the new call; and
            # exec_calls.py's --selfcheck and merge-exec's acceptance line both use it
            # to pick events, so carrying it over as-is would let a call that's
            # completely different from the ground truth enter the MATCH/DIFF
            # comparison with full_call_ok=True, causing DIFF to report a false alarm
            # and selfcheck to exit non-zero. Recompute it against the new call (record
            # None when the ground truth is missing, which fails the acceptance line's
            # filter), and move the old value to orig_full_call_ok for the record.
            # n_calls_in_block is left alone: it counts how many calls are in **the code
            # block recorded in the trajectory** (the plan cell counts it from
            # baseline_action), and like traj_bare_print it is the threshold for "can
            # executing one call alone be compared against the recorded stdout" -- not a
            # property of the draft
            truth = p.get("label_call")
            rec["orig_full_call_ok"] = p.get("full_call_ok")
            rec["full_call_ok"] = (call == truth) if truth else None
            rows.append(rec)
        out = d / f"exec_in_{arm}.jsonl"
        with open(out, "w") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        summary[arm] = dict(out=str(out), n_written=len(rows), **dict(stat))
        print(f"{arm}: {len(rows)} rows -> {out}  ({dict(stat)})", flush=True)

    print(json.dumps(dict(run_dir=str(d), plan_file=a.plan_file, tag=a.tag,
                          form_table=str(a.form_table or "default"),
                          arms=summary), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
