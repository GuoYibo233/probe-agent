"""Tally each tool's call form in real trajectories, for use by the splice-back skeleton. Spec:
plans/2026-08-01-splice-impl-spec.md §D2

The skeleton arm (skel_*) needs to plant a half-finished call like `print(apis.venmo.login` in the thinking, letting the
large model continue writing the parameters. What shell to plant cannot be guessed by feel: gpt-oss customarily wraps a
documentation-lookup call like `show_app_descriptions` in `print(...)`, while a call like `login` that needs the return
value is customarily assigned with `token = apis...`. Pick the wrong shell and the model's first step has to undo the line
we planted.

So first pull out the first call of each step's final code block from the two already-collected trajectory batches
(full_v1 + full_v2_topup's appworld_gptoss), aggregate them by tool into {tool: {n, print_share, assign_share, top_var}},
and look up the table at run time to decide the shell: assign_share >= 0.5 uses the assign form (variable name taken from
top_var), otherwise use the print form; tools not seen in the table fall back to print.

**Read only full_v1 / full_v2_topup, never touch w0_aw_official** -- that is the test set reserved for the live run,
tallying its call forms would mean peeking at the answer beforehand.

Usage: python pipeline/inject/build_form_table.py
"""

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

PROJ_ROOT = Path(__file__).resolve().parents[2]

# [copied verbatim from envs/collect/run_appworld.py:38] use the same regex to pull out code blocks
CODE_RE = re.compile(r"```python\s*(.*?)```", re.S)
# [copied verbatim from pipeline/annotate/rules.py:55] there is only one convention for tool names
AW_CALL = re.compile(r"apis\.(\w+)\.(\w+)\(")
# assign form: the left side of the line has exactly one variable name and one equals sign (a comparison like `x ==` does not count)
ASSIGN_RE = re.compile(r"^\s*(\w+)\s*=$")

# the two trajectory batches used for training/tallying, relative to the project root. The w0 test set is not here, and must not be added
DEFAULT_ROOTS = ("envs/runs/full_v1/appworld_gptoss",
                 "envs/runs/full_v2_topup/appworld_gptoss")
DEFAULT_OUT = "pipeline/inject/form_table.json"


def call_form(code):
    """The form of the first apis call in a piece of code. Returns (tool, form, var) or None.

    form is one of five:
      assign      `x = apis...`            -- take the return value and use it later
      print       `print(apis...`          -- look at the output directly
      print_multi `print("x:", apis...`    -- also wrapped in print, but the shell carries other arguments
      bare        the line starts directly with apis...    -- bare call
      other       everything else (nested inside if / for / another call)
    Only assign carries var.
    """
    m = AW_CALL.search(code or "")
    if m is None:
        return None
    tool = f"apis.{m.group(1)}.{m.group(2)}"
    ls = code.rfind("\n", 0, m.start()) + 1
    pre = code[ls:m.start()].rstrip()
    am = ASSIGN_RE.match(pre)
    if am:
        return tool, "assign", am.group(1)
    if pre.endswith("print("):
        return tool, "print", None
    if "print(" in pre:
        return tool, "print_multi", None
    if pre == "":
        return tool, "bare", None
    return tool, "other", None


def scan(roots):
    """Scan the trajectory directory, return (per-tool form counts, per-tool variable-name counts, file/record stats)."""
    forms = defaultdict(Counter)
    vars_ = defaultdict(Counter)
    stat = Counter()
    for root in roots:
        files = sorted(Path(root).glob("*.jsonl"))
        stat["files"] += len(files)
        for fp in files:
            for line in open(fp):
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    stat["bad_line"] += 1
                    continue
                if r.get("type") != "gen":
                    continue
                stat["gen"] += 1
                m = CODE_RE.search(r.get("content") or "")
                if m is None:
                    stat["no_code_block"] += 1
                    continue
                got = call_form(m.group(1))
                if got is None:
                    stat["no_api_call"] += 1
                    continue
                tool, form, var = got
                forms[tool][form] += 1
                stat[f"form_{form}"] += 1
                if var:
                    vars_[tool][var] += 1
    return forms, vars_, stat


def build(forms, vars_):
    """Form counts -> the content of form_table.json."""
    table = {}
    for tool, c in sorted(forms.items()):
        n = sum(c.values())
        top_var = vars_[tool].most_common(1)[0][0] if vars_[tool] else None
        table[tool] = dict(
            n=n,
            print_share=round(c["print"] / n, 4),
            assign_share=round(c["assign"] / n, 4),
            top_var=top_var)
    return table


def load_table(path=None):
    """Read form_table.json; if the file is missing, return an empty table (skeleton falls back to print for everything)."""
    p = Path(path or (PROJ_ROOT / DEFAULT_OUT))
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def skeleton(pred_label, table):
    """Skeleton string: table lookup decides whether it's a print shell or an assign shell.

    **Never include a trailing open-parenthesis** -- tokenizer test (spec section
    "prerequisite facts"): the trailing open-parenthesis of `print(apis.venmo.login(`
    fuses with the argument name into a single token `(username` in real continuations,
    so the prefix necessarily diverges; cut to `print(apis.venmo.login` and you get a
    strict 6/6 prefix match.
    The input here must be pred_label (probe prediction), never label (ground truth).
    """
    e = table.get(pred_label) or {}
    if e.get("assign_share", 0.0) >= 0.5 and e.get("top_var"):
        return f"{e['top_var']} = {pred_label}"
    return "print(" + pred_label


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--roots", nargs="+", default=None,
                    help=f"trajectory dir (default {' '.join(DEFAULT_ROOTS)}, "
                         "relative to the project root). The w0 test set must not be included")
    ap.add_argument("--out", default=None,
                    help=f"output json (default {DEFAULT_OUT})")
    ap.add_argument("--top", type=int, default=15,
                    help="how many high-frequency tools to print in the summary")
    a = ap.parse_args()

    roots = [Path(r) if Path(r).is_absolute() else PROJ_ROOT / r
             for r in (a.roots or DEFAULT_ROOTS)]
    for r in roots:
        if "w0_" in str(r):
            raise SystemExit(f"{r} is a test set, the form table must not be built from it")
        if not r.is_dir():
            raise SystemExit(f"trajectory dir does not exist: {r}")

    forms, vars_, stat = scan(roots)
    table = build(forms, vars_)
    out = Path(a.out) if a.out else PROJ_ROOT / DEFAULT_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(table, ensure_ascii=False, indent=1))

    n_assign = [t for t, e in table.items() if e["assign_share"] >= 0.5]
    print(json.dumps(dict(roots=[str(r) for r in roots], out=str(out),
                          n_tools=len(table),
                          n_calls=sum(e["n"] for e in table.values()),
                          n_assign_form=len(n_assign),
                          scan=dict(stat)), ensure_ascii=False, indent=1))
    print("\nassign-form tools (skeleton writes `var = apis...`):")
    for t in sorted(n_assign, key=lambda x: -table[x]["n"]):
        e = table[t]
        print(f"  {t:52s} n={e['n']:5d} assign={e['assign_share']:.2f} "
              f"var={e['top_var']}")
    print(f"\ntop{a.top} high-frequency tools (skeleton samples):")
    for t, e in sorted(table.items(), key=lambda kv: -kv[1]["n"])[:a.top]:
        print(f"  {t:52s} n={e['n']:5d} print={e['print_share']:.2f} "
              f"assign={e['assign_share']:.2f} -> {skeleton(t, table)!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
