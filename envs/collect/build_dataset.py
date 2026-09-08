"""Trajectories -> BERT-classification-head datasets for each of the three environments (v2
final, superseding the old four-cut version).

Final rules (settled point by point with the user and the advisor on 2026-07-29, WORKPLAN
C2-2t):
- One question = one prefix: always starts at the first character of the thinking, and the
  tail stops at a sentence boundary (code stops only at full lines)
- **All boundaries**: every event is cut at all its sentence boundaries (capped at 64, sampled
  evenly, always keeping the last one); training loss uses w=1/m_i, equal weight within an
  event -- matching the deployed distribution where "every sentence boundary gets called"
- Label = the tool actually called at that step, fully automatic with zero manual work; **one
  dataset per environment** (not trained jointly)
- Split unit = **task instance** (AppWorld task_id / TALES seed / BFCL entry id): the same
  instance's trajectories across different generating models move in and out together, to
  prevent sibling leakage
- Four-way split train/calA/calB/test = 70/10/10/10 (calA fits the temperature, calB sweeps
  the threshold in replay, test is frozen and run only once); calB/test naturally include all
  boundaries and can be replayed directly
- Seed is fixed, reruns are sample-for-sample identical; it produces a routing statistics
  table plus a frequency-prior baseline as a byproduct

Usage: python3 build_dataset.py [--runs DIR ...] [--out DIR]
Default runs=full_v1; you can append --runs .../full_v2_topup and rerun (deterministic
rebuild).
"""

import argparse
import json
import glob
import random
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

SEED = 20260729
BASE = Path("/home/y-guo/reproduce/new1/envs")
MAX_BOUNDS = 64       # per-event boundary cap (guards against gpt-oss's overlong thinking blowing up)
MIN_THINK = 40        # characters; shorter thinking has nothing left to cut
HIST_ROUNDS = 3       # number of recent tool-history turns kept in the prompt
RESULT_CAP = 400      # character cap per environment return inside the prompt
MODEL_OF = {"q35": "qwen3.5-27b", "q36": "qwen3.6-27b", "gptoss": "gpt-oss-120b"}

# sentence boundary: a newline, or .!? followed by whitespace (a decimal point or the dot in
# apis.x.y has no following whitespace, so it's naturally excluded)
SENT_RE = re.compile(r"(?<=[.!?])\s+|\n")


def boundaries(text):
    """All legal cut points (character offsets, prefix=text[:i]), including the end of the full text, capped at MAX_BOUNDS."""
    pts = sorted({m.end() for m in SENT_RE.finditer(text)} | {len(text)})
    pts = [p for p in pts if len(text[:p].strip()) >= MIN_THINK // 2]
    if not pts:
        pts = [len(text)]
    if len(pts) > MAX_BOUNDS:
        keep = {len(pts) - 1}
        step = (len(pts) - 1) / (MAX_BOUNDS - 1)
        keep.update(round(k * step) for k in range(MAX_BOUNDS - 1))
        pts = [pts[j] for j in sorted(keep)]
    return pts


def clip(s, cap=RESULT_CAP):
    s = str(s)
    return s if len(s) <= cap else s[: cap - 60] + " ...[cut]... " + s[-40:]


def assemble(task, history, think_prefix):
    lines = [f"Task: {task}", "[HISTORY]"]
    if history:
        lines += [f"{a} -> {clip(r)}" for a, r in history[-HIST_ROUNDS:]]
    else:
        lines.append("(start)")
    lines += ["[THINKING]", think_prefix]
    return "\n".join(lines)


# ---------- argument extraction (for routing statistics) ----------

AW_CALL = re.compile(r"apis\.(\w+)\.(\w+)\(")
BFCL_CALL = re.compile(r"(\w+)\(")


def split_args(argstr):
    vals, buf, depth, q = [], "", 0, None
    for ch in argstr:
        if q:
            buf += ch
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch
            buf += ch
        elif ch in "([{":
            depth += 1
            buf += ch
        elif ch in ")]}":
            depth -= 1
            buf += ch
        elif ch == "," and depth == 0:
            vals.append(buf.strip())
            buf = ""
        else:
            buf += ch
    if buf.strip():
        vals.append(buf.strip())
    out = []
    for v in vals:
        m = re.match(r"\w+\s*=\s*(.+)", v, re.S)
        out.append((m.group(1) if m else v).strip().strip("\"'"))
    return out


def first_call_args(code, name_re):
    m = name_re.search(code)
    if not m:
        return None
    i, depth = m.end() - 1, 0
    for j in range(i, len(code)):
        if code[j] == "(":
            depth += 1
        elif code[j] == ")":
            depth -= 1
            if depth == 0:
                return split_args(code[i + 1: j])
    return []


# ---------- three environments: trajectory -> event ----------
# event = dict(env, model, unit, traj, step, task, hist, think, tool, args)

def jsonl_events(runs, pattern, env):
    for f in sorted(glob.glob(str(runs / pattern))):
        batch = Path(f).parent.name           # e.g. appworld_q36
        model = MODEL_OF.get(batch.rsplit("_", 1)[1])
        if model is None:                     # non-model directories such as scoring/logs
            continue
        recs = [json.loads(l) for l in open(f)]
        meta = recs[0]
        gens = {r["step"]: r for r in recs if r["type"] == "gen"}
        envs = {r["step"]: r for r in recs if r["type"] == "env"}
        task = meta.get("instruction") or meta.get("task") or ""
        traj = f"{batch}/{Path(f).stem}"
        unit = (f"seed{meta.get('seed')}" if env == "tales"
                else str(meta.get("task_id") or Path(f).stem))
        hist = []
        for st in sorted(gens):
            g, e = gens[st], envs.get(st)
            if e is None:
                break
            think = (g.get("reasoning") or "").strip()
            action = (e.get("action") or "").strip()
            if not action:
                continue
            if env == "appworld":
                m = AW_CALL.search(action)
                if m and len(think) >= MIN_THINK:
                    yield dict(env=env, model=model, unit=unit, traj=traj,
                               step=st, task=task, hist=list(hist),
                               think=think,
                               tool=f"apis.{m.group(1)}.{m.group(2)}",
                               args=first_call_args(action, AW_CALL) or [])
            else:  # tales: label = first word of the command (the verb)
                verb = action.split()[0].lower() if action.split() else ""
                if verb and len(think) >= MIN_THINK:
                    rest = action.split()[1:]
                    yield dict(env=env, model=model, unit=unit, traj=traj,
                               step=st, task=task, hist=list(hist),
                               think=think, tool=verb,
                               args=[" ".join(rest)] if rest else [])
            hist.append((action, e.get("result", "")))


def bfcl_events(runs):
    for d in sorted(runs.glob("bfcl_*")):
        model = MODEL_OF.get(d.name.rsplit("_", 1)[1])
        if model is None:                     # non-model directories such as scoring/logs
            continue
        seen = set()
        for f in sorted(glob.glob(str(d / "**" / "*multi_turn*result.json"),
                                  recursive=True)):
            for line in open(f):
                entry = json.loads(line)
                if entry["id"] in seen:
                    continue
                seen.add(entry["id"])
                msgs = []

                def flat(o):
                    if isinstance(o, dict):
                        role, c = o.get("role"), o.get("content")
                        if role in ("user", "assistant", "tool") \
                                and isinstance(c, str):
                            msgs.append((role, c,
                                         o.get("reasoning_content") or ""))
                        else:
                            for v in o.values():
                                flat(v)
                    elif isinstance(o, list):
                        for v in o:
                            flat(v)
                flat(entry["inference_log"])
                task, hist, k = "", [], 0
                for role, c, rc in msgs:
                    if role == "user":
                        task = c
                    elif role == "assistant" and rc.strip() and c.strip():
                        k += 1
                        m = BFCL_CALL.search(c)
                        if m and len(rc.strip()) >= MIN_THINK:
                            yield dict(env="bfcl", model=model,
                                       unit=entry["id"],
                                       traj=f"{d.name}/{entry['id']}",
                                       step=k, task=task, hist=list(hist),
                                       think=rc.strip(), tool=m.group(1),
                                       args=first_call_args(c, BFCL_CALL) or [])
                        hist.append((c.strip()[:200], ""))
                        del hist[:-HIST_ROUNDS]
                    elif role == "tool" and hist:
                        a, _ = hist[-1]
                        hist[-1] = (a, c)


# ---------- main flow ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", action="append",
                    default=None, help="trajectory dir, repeatable; default full_v1")
    ap.add_argument("--out", default=str(BASE / "bert_data" / "v2"))
    args = ap.parse_args()
    runs_dirs = [Path(r) for r in (args.runs or [BASE / "runs" / "full_v1"])]
    out_root = Path(args.out)
    rng = random.Random(SEED)

    by_env = defaultdict(list)
    for runs in runs_dirs:
        for ev in jsonl_events(runs, "appworld_*/appworld_*.jsonl", "appworld"):
            by_env["appworld"].append(ev)
        for ev in jsonl_events(runs, "tales_*/tales_*.jsonl", "tales"):
            by_env["tales"].append(ev)
        for ev in bfcl_events(runs):
            by_env["bfcl"].append(ev)

    report = [f"# bert_data v2 release report\n\n- SEED={SEED} MAX_BOUNDS={MAX_BOUNDS}"
              f" runs={[str(r) for r in runs_dirs]}",
              "- rules: full-sentence boundary prefix / events equally weighted at w=1/m_i / four-way split at the task-instance level"
              " / one dataset per environment\n"]

    for env in ("appworld", "tales", "bfcl"):
        events = by_env[env]
        if not events:
            report.append(f"\n## {env}\n- no events, skip")
            continue
        out = out_root / env
        out.mkdir(parents=True, exist_ok=True)

        # task-instance-level split (same instance moves in and out together across models)
        units = sorted({ev["unit"] for ev in events})
        rng.shuffle(units)
        n = len(units)
        c1, c2, c3 = int(n * .7), int(n * .8), int(n * .9)
        part = {u: ("train" if i < c1 else "calA" if i < c2
                    else "calB" if i < c3 else "test")
                for i, u in enumerate(units)}

        # build questions (all boundaries + equal weight)
        samples = []
        for ev in events:
            pts = boundaries(ev["think"])
            m = len(pts)
            for si, cut in enumerate(pts):
                prefix = ev["think"][:cut]
                samples.append(dict(
                    text=assemble(ev["task"], ev["hist"], prefix),
                    label=ev["tool"], w=round(1.0 / m, 6),
                    depth=round(cut / len(ev["think"]), 4),
                    sent_idx=si, n_sents=m,
                    event=f"{ev['traj']}|s{ev['step']}",
                    traj=ev["traj"], unit=ev["unit"], model=ev["model"],
                    step=ev["step"]))

        # self-check 1: prefix = a slice of the original text (sample 200 and assert per question)
        ev_think = {f"{e['traj']}|s{e['step']}": e["think"] for e in events}
        for s in rng.sample(samples, min(200, len(samples))):
            think = s["text"].split("[THINKING]\n", 1)[1]
            assert ev_think[s["event"]].startswith(think), s["event"]
        # self-check 2: a unit never crosses splits (structurally guaranteed, verify explicitly again
        # anyway)
        seen_u = {}
        for s in samples:
            assert seen_u.setdefault(s["unit"], part[s["unit"]]) \
                == part[s["unit"]]

        splits = defaultdict(list)
        for s in samples:
            splits[part[s["unit"]]].append(s)
        for name in ("train", "calA", "calB", "test"):
            with open(out / f"{name}.jsonl", "w") as f:
                for s in splits[name]:
                    f.write(json.dumps(s, ensure_ascii=False) + "\n")

        vocab = Counter(e["tool"] for e in events)
        (out / "tool_vocab.json").write_text(json.dumps(
            dict(vocab.most_common()), ensure_ascii=False, indent=1))

        # routing statistics table
        rt = defaultdict(lambda: dict(n=0, nargs=[], alen=[], hit=0, argn=0))
        for ev in events:
            r = rt[ev["tool"]]
            r["n"] += 1
            r["nargs"].append(len(ev["args"]))
            ctx = ev["think"] + "\n" + ev["task"] + "\n" + \
                "\n".join(a + str(b) for a, b in ev["hist"])
            for a in ev["args"]:
                if not a:
                    continue
                r["argn"] += 1
                r["alen"].append(len(a))
                if a in ctx:
                    r["hit"] += 1
        with open(out / "router_stats.md", "w") as f:
            f.write(f"# routing statistics table — {env} (the args-head ruling)\n\n"
                    "| tool | event count | median arg count | exact-match hit rate | median arg length |\n"
                    "|---|---|---|---|---|\n")
            for k in sorted(rt, key=lambda k: -rt[k]["n"]):
                r = rt[k]
                hitrate = f"{r['hit']/r['argn']:.2f}" if r["argn"] else "-"
                alen = int(statistics.median(r["alen"])) if r["alen"] else "-"
                f.write(f"| {k} | {r['n']} | "
                        f"{int(statistics.median(r['nargs']))} "
                        f"| {hitrate} | {alen} |\n")

        # QA spot check
        with open(out / "qa_sample.txt", "w") as f:
            for i, s in enumerate(rng.sample(samples, min(20, len(samples)))):
                f.write(f"{'='*70}\n[QA {i}] label={s['label']} "
                        f"depth={s['depth']} sent {s['sent_idx']+1}/"
                        f"{s['n_sents']} traj={s['traj']}\n{s['text']}\n\n")

        # report
        bl = [e_m for e_m in (len(boundaries(e["think"])) for e in events)]
        dep = Counter(min(9, int(s["depth"] * 10)) for s in samples)
        lens = sorted(len(s["text"]) for s in samples)
        prior_tool = vocab.most_common(1)[0][0]
        test_events = {s["event"]: s["label"] for s in splits["test"]}
        prior_acc = (sum(1 for v in test_events.values() if v == prior_tool)
                     / max(1, len(test_events)))
        trajs = {e["traj"] for e in events}
        report += [
            f"\n## {env}",
            f"- trajectories {len(trajs)} / task instances {len(units)} / events {len(events)}"
            f" / samples {len(samples)}",
            f"- boundary count per event: min {min(bl)} med {sorted(bl)[len(bl)//2]}"
            f" max {max(bl)} (cap {MAX_BOUNDS})",
            "- split (task-instance level): " + " / ".join(
                f"{sp} {len({s['unit'] for s in splits[sp]})} instances·"
                f"{len({s['event'] for s in splits[sp]})} events·"
                f"{len(splits[sp])} samples"
                for sp in ("train", "calA", "calB", "test")),
            f"- tool vocab {len(vocab)} classes; top5 {vocab.most_common(5)}",
            f"- long tail (appears <5 times): {sum(1 for c in vocab.values() if c < 5)} classes",
            f"- sample counts across 10 depth buckets: {[dep.get(i, 0) for i in range(10)]}",
            f"- prompt length p50={lens[len(lens)//2]}"
            f" p90={lens[int(len(lens)*.9)]} max={lens[-1]} characters"
            " (over 4096 tokens gets left-truncated by the training script)",
            f"- frequency-prior baseline (test event level, guessing {prior_tool}): {prior_acc:.3f}",
            "- self-check: prefix assertion 200/200 ✓; instances don't cross splits ✓",
        ]
        print(f"{env}: events={len(events)} samples={len(samples)} "
              f"vocab={len(vocab)}")

    (out_root / "BUILD_REPORT.md").write_text("\n".join(report) + "\n")
    print("done ->", out_root)


if __name__ == "__main__":
    main()
