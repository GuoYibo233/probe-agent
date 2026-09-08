"""Trajectory -> single-model single-environment sample dataset (the new
pipeline's main annotate-stage builder).

Source = envs/collect/build_dataset.py, the rules are unchanged word for word
(full-sentence-boundary prefix / equal weight within an event / label = the tool
name actually called at that step); only five things change:
(1) filter events by config.model_full (one model, one set of data);
(2) split without shuffling, read the official task-list file to decide
train/val/test (a unit not in the task list -> error out);
(3)(4) output pile names train/val/test, output dir = config.data_out;
(5) report name ANNOTATE_REPORT.md.
The sample dict also gets two extra fields: label_call (the normalized full call
string), args_named (the named-args table).

Two knobs (2026-08-21, the np821 batch):
- weight_mode: uniform (default) = equal weight w=1 per step; per_event = the old
  convention w=1/m_i, kept only for the G8 reproduction acceptance line.
- max_bounds: the cap on cut points per event, default 64, passed through to
  rules.boundaries' thinning.
Both follow CLI > config field > default; when an old config doesn't set these two
fields and no flag is given, everything stays as before except the weighting
convention itself.

Input: the experiment config json pointed to by --config (schema in
plans/2026-07-31-pipeline-engineering.md §2.3)
Output: <data_out>/{train,val,test}.jsonl tool_vocab.json router_stats.md
      qa_sample.txt ANNOTATE_REPORT.md

Usage: python3 build.py --config pipeline/configs/aw_q35.json
      python3 build.py --config pipeline/configs/p1_gptoss.json \\
              --weight-mode per_event --max-bounds 64      # G8 reproduction
"""

import argparse
import glob
import json
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rules import (ALF_TEMPLATES, AW_CALL, BFCL_CALL,  # noqa: E402
                   HIST_ROUNDS, MAX_BOUNDS, MIN_THINK, MODEL_OF, SEED,
                   alf_split, assemble, boundaries, first_call_args,
                   first_call_named)

SPLITS = ("train", "val", "test")

# alfworld: counts of actions the template can't cut (not silently dropped, printed
# item by item in the report).
# key = the reason rules.alf_split came up empty; param_label.py has a copy using
# the same convention.
ALF_DROP = Counter()


# ---------- trajectory -> event (copied verbatim from build_dataset.py, only adds one named-args table) ----------
# event = dict(env, model, unit, traj, step, task, hist, think, tool, args, named)

def jsonl_events(runs, pattern, env):
    for f in sorted(glob.glob(str(runs / pattern))):
        batch = Path(f).parent.name           # e.g. appworld_q36
        model = MODEL_OF.get(batch.rsplit("_", 1)[1])
        if model is None:                     # non-model dirs like scoring/logs
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
                               args=first_call_args(action, AW_CALL) or [],
                               named=first_call_named(action, AW_CALL) or [])
            elif env == "alfworld":
                # Template fine-grained convention: longest-prefix match against the 13 official
                # action templates, cut named args at the preposition position.
                # If it can't be cut -> drop the whole step + count it (never fall back to the
                # verb-based cut in the else branch below).
                tool, named, why = alf_split(action)
                if why:
                    ALF_DROP[why] += 1
                elif len(think) >= MIN_THINK:
                    yield dict(env=env, model=model, unit=unit, traj=traj,
                               step=st, task=task, hist=list(hist),
                               think=think, tool=tool,
                               args=[v for _k, v in named],
                               named=list(named))
            else:  # tales: label = the first word of the command (the verb)
                verb = action.split()[0].lower() if action.split() else ""
                if verb and len(think) >= MIN_THINK:
                    rest = action.split()[1:]
                    yield dict(env=env, model=model, unit=unit, traj=traj,
                               step=st, task=task, hist=list(hist),
                               think=think, tool=verb,
                               args=[" ".join(rest)] if rest else [],
                               named=([("arg", " ".join(rest))] if rest
                                      else []))
            hist.append((action, e.get("result", "")))


def bfcl_events(runs):
    for d in sorted(runs.glob("bfcl_*")):
        model = MODEL_OF.get(d.name.rsplit("_", 1)[1])
        if model is None:                     # non-model dirs like scoring/logs
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
                                       args=first_call_args(c, BFCL_CALL) or [],
                                       named=first_call_named(c, BFCL_CALL)
                                       or [])
                        hist.append((c.strip()[:200], ""))
                        del hist[:-HIST_ROUNDS]
                    elif role == "tool" and hist:
                        a, _ = hist[-1]
                        hist[-1] = (a, c)


def collect_events(runs_dirs, env):
    """Concatenate events from multiple runs directories per environment (order = runs directory order)."""
    events = []
    for runs in runs_dirs:
        if env == "appworld":
            it = jsonl_events(runs, "appworld_*/appworld_*.jsonl", "appworld")
        elif env == "tales":
            it = jsonl_events(runs, "tales_*/tales_*.jsonl", "tales")
        elif env == "alfworld":
            it = jsonl_events(runs, "alfworld_*/alfworld_*.jsonl", "alfworld")
        elif env == "bfcl":
            it = bfcl_events(runs)
        else:
            raise SystemExit(f"unknown environment: {env}")
        events.extend(it)
    return events


# ---------- two new fields added (§3.3) ----------

def norm_named(named):
    """Named-parameter table -> [{"key","value"}], in call order, empty values skipped."""
    return [dict(key=k, value=v) for k, v in named if v]


def make_call(tool, args_named):
    """label_call = tool(k=v, k=v); tool() when there are no arguments."""
    inner = ", ".join(f"{a['key']}={a['value']}" for a in args_named)
    return f"{tool}({inner})"


# ---------- build samples (all boundaries + equal weight, [COPIED], dict gets two extra fields) ----------

def make_samples(events, weight_mode="per_event", max_bounds=MAX_BOUNDS):
    """Event -> sample. The two parameters' defaults = the pre-change semantics (w=1/m_i, cap 64),
    so old callers (accept_v3diff.py uses this to reproduce v3 data) need no change at all;
    main() always passes the effective values explicitly."""
    samples = []
    for ev in events:
        pts = boundaries(ev["think"], max_bounds)
        m = len(pts)
        w = 1.0 if weight_mode == "uniform" else round(1.0 / m, 6)
        args_named = norm_named(ev.get("named") or [])
        label_call = make_call(ev["tool"], args_named)
        for si, cut in enumerate(pts):
            prefix = ev["think"][:cut]
            samples.append(dict(
                text=assemble(ev["task"], ev["hist"], prefix),
                label=ev["tool"], w=w,
                depth=round(cut / len(ev["think"]), 4),
                sent_idx=si, n_sents=m,
                event=f"{ev['traj']}|s{ev['step']}",
                traj=ev["traj"], unit=ev["unit"], model=ev["model"],
                step=ev["step"],
                label_call=label_call,
                args_named=[dict(a) for a in args_named]))
    return samples


# ---------- independent scan for multi-sample batches (2026-08-21; does not touch the event stream) ----------
#
# These two stats ask what the raw trajectory itself looks like, which the event stream cannot
# answer: comparing identical trajectories needs the step-by-step original text (the event
# stream keeps only the filtered think), and the step cap needs the final record (the event
# stream does not carry it at all). So the files are read again, using the same reading rules
# (directory filtering, unit convention) as jsonl_events.

# The per-task step cap on the collection side, by environment (gen_launch.py ENV_TABLE's
# --max-steps: appworld 30, alfworld 50); environments not in the table are recorded as "n/a".
STEP_CAP = {"appworld": 30, "alfworld": 50}

TRAJ_PATTERNS = {"appworld": "appworld_*/appworld_*.jsonl",
                 "tales": "tales_*/tales_*.jsonl",
                 "alfworld": "alfworld_*/alfworld_*.jsonl"}


def traj_files(runs_dirs, env, model_full):
    """List of raw trajectory files to scan for this batch; bfcl has no step-by-step trajectory file -> None."""
    pattern = TRAJ_PATTERNS.get(env)
    if pattern is None:
        return None
    out = []
    for runs in runs_dirs:
        for f in sorted(glob.glob(str(runs / pattern))):
            batch = Path(f).parent.name       # e.g. appworld_gptoss
            if MODEL_OF.get(batch.rsplit("_", 1)[1]) != model_full:
                continue                      # other model / non-model directories
            out.append(f)
    return out


def scan_raw_trajs(files, env):
    """-> dict(n_traj, dup_pairs, dup_units, cap_trajs, cap_units).

    dup: the number of trajectory **pairs** within the same unit whose step-by-step
        (reasoning, content) sequences are exactly equal (three identical trajectories
        count as 3 pairs), counted without deduplication; dup_units = the number of
        tasks that had any duplicate.
    cap: the number of trajectories, and the number of tasks involved, whose final
        record has steps >= that environment's step cap; when the environment is not
        in the STEP_CAP table, cap is recorded as None (the report prints "n/a").
    """
    cap = STEP_CAP.get(env)
    by_unit = defaultdict(list)
    cap_trajs, cap_units = 0, set()
    for f in files:
        recs = [json.loads(l) for l in open(f)]
        meta = recs[0]
        unit = (f"seed{meta.get('seed')}" if env == "tales"
                else str(meta.get("task_id") or Path(f).stem))
        gens = {r["step"]: r for r in recs if r["type"] == "gen"}
        by_unit[unit].append(tuple(
            (gens[st].get("reasoning") or "", gens[st].get("content") or "")
            for st in sorted(gens)))
        fin = [r for r in recs if r["type"] == "final"]
        if cap is not None and fin and (fin[-1].get("steps") or 0) >= cap:
            cap_trajs += 1
            cap_units.add(unit)
    dup_pairs, dup_units = 0, set()
    for unit, sigs in by_unit.items():
        pairs = sum(n * (n - 1) // 2 for n in Counter(sigs).values() if n > 1)
        if pairs:
            dup_pairs += pairs
            dup_units.add(unit)
    return dict(n_traj=len(files), dup_pairs=dup_pairs,
                dup_units=len(dup_units), cap=cap, cap_trajs=cap_trajs,
                cap_units=len(cap_units))


# ---------- official task-list split (change 2) ----------

def read_unit_list(path):
    """Official task list: one task_id per line (file has no trailing newline; split by line then drop empty lines)."""
    txt = Path(path).read_text()
    return [ln.strip() for ln in txt.split("\n") if ln.strip()]


def official_split(cfg):
    """-> (part: unit->pile name, lists: pile name->that task list's unit set)"""
    files = cfg["official_split_files"]
    lists, part = {}, {}
    for name in SPLITS:
        units = read_unit_list(files[name])
        lists[name] = set(units)
        for u in units:
            part[u] = name
    return part, lists


# ---------- main flow ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="experiment config json (§2.3)")
    ap.add_argument("--weight-mode", choices=("uniform", "per_event"),
                    default=None,
                    help="sample weighting settings; defaults to the config's weight_mode, then to uniform")
    ap.add_argument("--max-bounds", type=int, default=None,
                    help="per-event cut-point cap; defaults to the config's max_bounds, then to 64")
    args = ap.parse_args()
    cfg = json.loads(Path(args.config).read_text())
    env = cfg["env"]
    model_full = cfg["model_full"]
    runs_dirs = [Path(r) for r in cfg["traj_runs"]]
    out = Path(cfg["data_out"])
    seed = cfg.get("seed", SEED)
    rng = random.Random(seed)
    # Effective value: CLI > config field > default. The default is the new convention (equal
    # weight per step); the old convention must be named explicitly.
    # The config branch is decided by "is the key present", not by truthiness: writing an
    # invalid value like 0 must fall through to the hard stop below, and must not be silently
    # swapped for the default by `or` (a hole caught in the 2026-08-22 review).
    cfg_wm = cfg.get("weight_mode")
    weight_mode = (args.weight_mode if args.weight_mode is not None
                   else "uniform" if cfg_wm is None else cfg_wm)
    cfg_mb = cfg.get("max_bounds")
    max_bounds = (args.max_bounds if args.max_bounds is not None
                  else MAX_BOUNDS if cfg_mb is None else cfg_mb)
    if weight_mode not in ("uniform", "per_event"):
        raise SystemExit(f"unknown weight_mode: {weight_mode} "
                         "(only uniform/per_event are recognized)")
    if max_bounds < 2:
        # A cap of 1 would make rules.boundaries' thinning stride divide by zero; it must not blow up silently partway through.
        raise SystemExit(f"max_bounds must be at least 2 (got {max_bounds})")

    events = collect_events(runs_dirs, env)
    n_all = len(events)
    # Change 1: one model, one dataset
    events = [ev for ev in events if ev["model"] == model_full]
    if not events:
        raise SystemExit(f"no events for model={model_full} (scanned {n_all} events total)")
    out.mkdir(parents=True, exist_ok=True)

    # Change 2: official task-list split, no shuffle; a unit not in any task list -> error and exit
    part, lists = official_split(cfg)
    units = sorted({ev["unit"] for ev in events})
    missing = [u for u in units if u not in part]
    if missing:
        raise SystemExit(
            f"{len(missing)} units are not in any official task list; refusing to silently drop them: "
            f"{missing[:10]}{' ...' if len(missing) > 10 else ''}")

    samples = make_samples(events, weight_mode, max_bounds)

    # Self-check 1: prefix = original-text slice (sample 200, assert per task)
    ev_think = {f"{e['traj']}|s{e['step']}": e["think"] for e in events}
    for s in rng.sample(samples, min(200, len(samples))):
        think = s["text"].split("[THINKING]\n", 1)[1]
        assert ev_think[s["event"]].startswith(think), s["event"]
    # Self-check 2: a unit does not cross splits (structurally guaranteed, verified explicitly again)
    seen_u = {}
    for s in samples:
        assert seen_u.setdefault(s["unit"], part[s["unit"]]) \
            == part[s["unit"]]

    splits = defaultdict(list)
    for s in samples:
        splits[part[s["unit"]]].append(s)
    for name in SPLITS:
        with open(out / f"{name}.jsonl", "w") as f:
            for s in splits[name]:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")

    # Self-check 3 (new): draw 20 units per pile, assert they are actually in the corresponding official task-list file
    check3 = []
    for name in SPLITS:
        us = sorted({s["unit"] for s in splits[name]})
        pick = rng.sample(us, min(20, len(us))) if us else []
        for u in pick:
            assert u in lists[name], (name, u)
        check3.append(f"{name} {len(pick)}/{len(pick)}")

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
        f.write(f"# routing stats table -- {env} (arg-head ruling)\n\n"
                "| tool | events | median arg count | exact-match hit rate | median arg length |\n"
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
    bl = [e_m for e_m in (len(boundaries(e["think"], max_bounds))
                          for e in events)]
    dep = Counter(min(9, int(s["depth"] * 10)) for s in samples)
    lens = sorted(len(s["text"]) for s in samples)
    prior_tool = vocab.most_common(1)[0][0]
    test_events = {s["event"]: s["label"] for s in splits["test"]}
    prior_acc = (sum(1 for v in test_events.values() if v == prior_tool)
                 / max(1, len(test_events)))
    trajs = {e["traj"] for e in events}
    # Wording for the split convention. It only affects two lines of **text** in the report, it
    # does not go into any sample field, so the data bytes are byte-identical to before the change
    # (verified: aw_official_v1/q35, three piles, zero cmp diff).
    # The default keeps the pre-change wording; appworld/alfworld configs need not write it.
    # bfcl must write it: BFCL has no official partition, so stamping "official task list" anyway
    # would make the numbers right but the wording a lie (extending.md §5 silent-failure point #18);
    # check_callstr.py hard-blocks this kind of lying.
    split_desc = cfg.get("split_desc", "official task list, task-instance level")
    # Wording for the weighting convention: per_event stays word-for-word (G8 reproduction needs it byte-identical), uniform gets different wording.
    w_desc = "w=1/m_i, events equally weighted" if weight_mode == "per_event" else "w=1, each step equally weighted"
    report = [
        f"# {cfg['run_family']} / {cfg['model_short']} annotate release report\n",
        f"- SEED={seed} MAX_BOUNDS={max_bounds} env={env}"
        f" model={model_full}",
        f"- runs={[str(r) for r in runs_dirs]}",
        f"- config={args.config} out={out}",
        f"- rules: full-sentence-boundary prefix / {w_desc} / three-way split "
        f"({split_desc}) / one model, one dataset\n",
        f"## {env} — {cfg['model_short']}",
        f"- trajectories {len(trajs)} / task instances {len(units)} / events {len(events)}"
        f" / samples {len(samples)} (all-model events {n_all}, {len(events)} left after filtering)",
        f"- boundary count per event: min {min(bl)} med {sorted(bl)[len(bl)//2]}"
        f" max {max(bl)} (cap {max_bounds})",
        f"- split ({split_desc}): " + " / ".join(
            f"{sp} {len({s['unit'] for s in splits[sp]})} instances·"
            f"{len({s['event'] for s in splits[sp]})} events·"
            f"{len(splits[sp])} samples"
            for sp in SPLITS),
        f"- tool vocabulary {len(vocab)} classes; top5 {vocab.most_common(5)}",
        f"- long tail (appears <5 times): {sum(1 for c in vocab.values() if c < 5)} classes",
        f"- sample counts across 10 depth buckets: {[dep.get(i, 0) for i in range(10)]}",
        f"- task-text length p50={lens[len(lens)//2]}"
        f" p90={lens[int(len(lens)*.9)]} max={lens[-1]} characters "
        "(beyond 4096 tokens, left-truncated by the training script)",
        f"- frequency-prior baseline (test, event-level, guessing {prior_tool}): {prior_acc:.3f}",
        "- self-check: prefix assertion 200/200 ✓; instances don't cross splits ✓; "
        "task-list ownership spot check " + " ".join(check3) + " ✓",
    ]
    if "trajs_per_unit" in cfg:
        # These four lines appear only for multi-sample batches (multiple trajectories per task):
        # whether the cut-point cap should be raised depends on the untruncated cut-point
        # distribution; whether multiple trajectories for the same task collide into identical
        # ones, and how many hit the step cap, are problems specific to temperature-1
        # multi-sampling. Old configs lack this key -> the set of report lines matches before
        # the change. No sampling anywhere in this, and no rng used.
        ub = sorted(len(boundaries(e["think"], 10**9)) for e in events)

        def q(p):
            return ub[min(len(ub) - 1, int(len(ub) * p))]

        report.append(
            f"- cut-point count (untruncated) per event: min {ub[0]} p50 {q(.5)} p90 {q(.9)}"
            f" p99 {q(.99)} max {ub[-1]}; events exceeding 32/64/128/256 "
            + "/".join(str(sum(1 for n in ub if n > t))
                       for t in (32, 64, 128, 256)))
        report.append(f"- events hitting the cut-point cap ({max_bounds}): "
                      f"{sum(1 for n in ub if n > max_bounds)}")
        files = traj_files(runs_dirs, env, model_full)
        if files is None:
            report.append("- identical trajectories / step count at cap: "
                          f"not applicable ({env} has no step-by-step trajectory file)")
        else:
            raw = scan_raw_trajs(files, env)
            report.append(f"- identical trajectories: {raw['dup_pairs']} pairs "
                          f"(involving {raw['dup_units']} tasks); "
                          f"scanned {raw['n_traj']} trajectories, counted only, not deduplicated")
            if raw["cap"] is None:
                report.append(f"- trajectories at the step-count cap: not applicable "
                              f"({env} is not in the STEP_CAP table)")
            else:
                report.append(f"- trajectories at the step-count cap ({raw['cap']}): "
                              f"{raw['cap_trajs']} "
                              f"(involving {raw['cap_units']} tasks)")
    if env == "alfworld":
        # Actions the templates cannot parse: drop the whole step, but it must be observable.
        # A high no_template share means the prompt is sending the old syntax (put X in Y) or
        # extraneous natural language, not that the model is bad -- this line doubles as an
        # alarm for a syntax version mismatch.
        report.append(
            f"- steps dropped because no template could cut them: {sum(ALF_DROP.values())} "
            f"({dict(sorted(ALF_DROP.items()))}); "
            f"official templates {len(ALF_TEMPLATES)}, tool vocabulary should be ≤{len(ALF_TEMPLATES)} classes")
    (out / "ANNOTATE_REPORT.md").write_text("\n".join(report) + "\n")
    if env == "alfworld":
        print(f"alfworld dropped, uncuttable: {sum(ALF_DROP.values())} "
              f"{dict(sorted(ALF_DROP.items()))}")
    print(f"{env}/{cfg['model_short']}: events={len(events)} "
          f"samples={len(samples)} vocab={len(vocab)}")
    print("done ->", out)


if __name__ == "__main__":
    main()
