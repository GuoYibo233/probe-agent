"""Extract truncated probe cases from trajectories across the three domains.

Each case = context (task + most recent environment return) + a thinking prefix (truncated at
25%/50%/75%). The blind files (cases_*.json) carry no answers; gold is stored separately in
gold_*.json, for the main conversation to score only.
"""

import json
import glob
import re
from pathlib import Path

RUNS = Path("/home/y-guo/reproduce/new1/envs/runs")
OUT = RUNS / "probe_v0"
FRACS = [0.25, 0.5, 0.75]


def truncate(text, frac):
    return text[: max(1, int(len(text) * frac))]


def add(cases, gold, cid, context, thinking, answer):
    for fr in FRACS:
        cases.append({"case_id": f"{cid}@{int(fr*100)}", "context": context,
                      "thinking_prefix": truncate(thinking, fr)})
    gold[cid] = answer


def tales_cases():
    cases, gold = [], {}
    for f in sorted(glob.glob(str(RUNS / "smoke_q3*/tales_*.jsonl"))):
        recs = [json.loads(l) for l in open(f)]
        meta = recs[0]
        gens = {r["step"]: r for r in recs if r["type"] == "gen"}
        envs = {r["step"]: r for r in recs if r["type"] == "env"}
        for st, g in gens.items():
            if len(g["reasoning"]) < 200 or st not in envs:
                continue
            prev = envs.get(st - 1)
            ctx = (f"[game task] {meta.get('task','')}\n"
                   f"[latest observation] "
                   f"{prev['result'][:600] if prev else '(episode start)'}")
            add(cases, gold, f"tales|{Path(f).parent.name}.{Path(f).stem}|s{st}", ctx,
                g["reasoning"], envs[st]["action"])
    return cases, gold


def appworld_cases():
    cases, gold = [], {}
    call_re = re.compile(r"apis\.\w+\.\w+\([^)]*\)")
    for f in sorted(glob.glob(str(RUNS / "smoke_q3*/appworld_*.jsonl"))):
        recs = [json.loads(l) for l in open(f)]
        meta = recs[0]
        gens = {r["step"]: r for r in recs if r["type"] == "gen"}
        envs = {r["step"]: r for r in recs if r["type"] == "env"}
        for st, g in gens.items():
            e = envs.get(st)
            if not e or not e.get("action") or len(g["reasoning"]) < 150:
                continue
            calls = call_re.findall(e["action"])
            if not calls:
                continue
            prev = envs.get(st - 1)
            ctx = (f"[task] {meta.get('instruction','')}\n"
                   f"[latest execution output] "
                   f"{(prev['result'][:600] if prev else '(start)')}")
            add(cases, gold, f"appworld|{Path(f).parent.name}.{Path(f).stem}|s{st}", ctx,
                g["reasoning"], calls[0])
    return cases, gold


def bfcl_cases():
    cases, gold = [], {}
    f = (RUNS / "bfcl_q35/Qwen_Qwen3-32B/multi_turn/"
         "BFCL_v4_multi_turn_base_result.json")
    for line in open(f):
        e = json.loads(line)
        # inference_log: within a turn is a list of message dicts (role/content), interspersed with
        # status entries
        last_user = ""
        k = 0
        def visit(o):
            nonlocal last_user, k
            if isinstance(o, dict):
                role, c = o.get("role"), o.get("content")
                if role == "user" and isinstance(c, str):
                    last_user = c
                elif role == "assistant" and o.get("reasoning_content") \
                        and isinstance(c, str) and c.strip():
                    k += 1
                    ctx = f"[user request] {last_user[:600]}"
                    add(cases, gold, f"bfcl|{e['id']}|a{k}", ctx,
                        o["reasoning_content"], c.strip()[:300])
                else:
                    for v in o.values():
                        visit(v)
            elif isinstance(o, list):
                for v in o:
                    visit(v)
        visit(e["inference_log"])
    return cases, gold


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in [("tales", tales_cases), ("appworld", appworld_cases),
                     ("bfcl", bfcl_cases)]:
        cases, gold = fn()
        (OUT / f"cases_{name}.json").write_text(
            json.dumps(cases, ensure_ascii=False, indent=1))
        (OUT / f"gold_{name}.json").write_text(
            json.dumps(gold, ensure_ascii=False, indent=1))
        print(f"{name}: {len(gold)} calls -> {len(cases)} truncated cases")


if __name__ == "__main__":
    main()
