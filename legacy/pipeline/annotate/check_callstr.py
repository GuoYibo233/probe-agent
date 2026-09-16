#!/usr/bin/env python3
"""annotate post-hoc gate: can the ground-truth call string be parsed back exactly by the
eval side, plus five structural hard checks (pure CPU).

What question this answers: build.py writes each sample's ground truth `label_call`
(hand-assembled `tool(k=v, k=v)`); can the eval side's `eval_causal_call.parse_call` parse
it back to `args_named` exactly? Whatever part cannot be parsed back is score that the
`params_all_ok` metric **can never get** -- the generation side is judged wrong no matter
how correct it is, because the ground truth itself is not self-consistent under eval's
parsing.

Why this step is necessary: `build.make_call` hand-assembles with
`", ".join(f"{k}={v}")`, unquoted, while the eval side's `split_named_raw` splits
arguments on **top-level commas**. A comma inside an argument value gets split apart.
Measured example:
    echo(content=Finally, in that file, Write my last question in it., file_name=79.pdf)
gets split into content=Finally / pos0=in that file / pos1=Write my last question in
it. / file_name=79.pdf. In rules.py, ALFWorld has an ALF_BAD_CHARS comma gate built
specifically to block this; neither appworld nor bfcl has one. This script **only
measures, does not fix**: appworld's twelve c1_* cells are already booked under the
"no gate" convention, so adding a gate for bfcl alone would no longer be one consistent
ruler.

While at it, this also runs five structural gates together (all hard-stop via
sys.exit; they live here because they can only be verified after build.py +
param_label.py have finished and the finished dataset is in hand):
  Gate A every row's model field == cfg.model_full. Guards against cross-model
         contamination (extending.md §5 #13: the eval side's shape assert
         len(rows)==logits.shape[0] is the only line of defense, and it cannot be
         relied on as a guarantee).
  Gate B (event, sent_idx) is globally unique, and a unit maps to exactly one traj
         under a given model. This exposes a mis-written traj_runs: when traj_runs
         is written as the parent directory envs/runs, build.py:101's
         runs.glob("bfcl_*") hits the 21-task smoke batch envs/runs/bfcl_q35/,
         whose traj name is character-identical to full_v1/bfcl_q35, so the same
         batch of event keys enters the store twice, silently, with no warning --
         only the sample count quietly grows.
  Gate C every entry of traj_runs must be the run directory itself, not its parent
         directory. Test: the entry has a bfcl_<model> subdirectory **directly**
         under it, and `*/bfcl_<model>` no longer matches any directory (a match
         means it is a parent directory). This is the upstream interception for
         gate B.
  Gate D every row's unit must fall within the task-list file of the pile it
         belongs to (full check of task-list membership, no sampling).
  Gate E ANNOTATE_REPORT.md's wording must not lie: when SPLIT_REPORT.json says
         official_split_exists=false, the report must not say "official task list".

The report separately lists four kinds of **known deviations** (not hard-blocked,
but must be visible, otherwise no one knows why the numbers look bad):
  Deviation 1 loss from parsing the ground-truth call string back (the thing above),
              given at both the event and parameter level.
  Deviation 2 the task list is consistent but the realized instances have gaps:
              three models share one task list, and some units' trajectories
              produce not a single usable event (thinking <40 characters, or the
              call cannot be parsed), listed one by one. The current gate G10
              ("the three models' unit sets are exactly the same") necessarily
              fails to hold on bfcl.
  Deviation 3 tools that appear in the test pile but never in the train pile: these
              are in label2id (the vocabulary is counted over the whole pile), so
              eval_tool.py does not drop them -- they are necessarily judged wrong,
              an unreachable ceiling on accuracy.
  Deviation 4 a warning for a thin test pile (too few events): when there are too
              few events, the risk tier's θ can end up all null, and
              eval_causal_call exits directly via SystemExit 1 (precedent:
              c1_q35_mext).

Known deviation (of this script itself): the read-back check compares "eval's
parsing vs. annotate's assembled string", it does not check the generation side;
`parse_call` looks only at the **first** matched call, the same source as
build/param_label's first_call_*.

Usage: python3 pipeline/annotate/check_callstr.py --config pipeline/configs/bfcl_q35.json
"""
import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

# Pure CPU script, but eval_causal_call imports torch internally. Explicitly hide all
# visible GPUs, so this script never touches a GPU under any circumstances.
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "eval"))
from rules import MODEL_OF, SEED                       # noqa: E402
# eval_causal_call's import is deferred to the place in main() where norm/parse_call
# are actually used (the deviation-1 read-back check): it imports torch at module
# level, so importing it earlier would make the whole file fail to import in an
# environment without torch installed, and pure-logic pieces like gate B's K-item
# test / the §8b reinforcing test could no longer be unit-tested outside cprobe-env
# (see tests/test_check_callstr.py). The delay changes no output bytes: when torch
# gets pulled in has no effect on stdout or the report file.

SPLITS = ("train", "val", "test")
THIN_TEST_EVENTS = 200      # below this many test events, report the risk that "θ may end up all null"
MAX_LIST = 12               # the cap for listing items one by one in the report (beyond this, just report the count)
EXAMPLES = 5                # number of read-back failure examples


def read_unit_list(path):
    """[COPIED from build.py:read_unit_list] task list has one unit per line, empty lines dropped."""
    return [ln.strip() for ln in Path(path).read_text().split("\n")
            if ln.strip()]


def gate_c(traj_runs, env):
    """Gate C: every entry of traj_runs must be the run directory itself, not its parent directory."""
    if env != "bfcl":
        # Other environments go through jsonl_events' glob("<env>_*/<env>_*.jsonl"), a
        # different directory depth, so this gate's test does not apply -- skip it outright
        # (do not pretend it was checked).
        return f"gate C skipped (env={env} doesn't use the runs.glob path)"
    for r in traj_runs:
        p = Path(r)
        if not p.is_dir():
            sys.exit(f"[gate C] traj_runs directory does not exist: {p}")
        direct = [d for d in p.glob("bfcl_*")
                  if d.is_dir() and MODEL_OF.get(d.name.rsplit("_", 1)[1])]
        nested = [d for d in p.glob("*/bfcl_*")
                  if d.is_dir() and MODEL_OF.get(d.name.rsplit("_", 1)[1])]
        if nested:
            sys.exit(
                f"[gate C] traj_runs entry {p} looks like the **parent directory** of the run directory: "
                f"underneath it there are {len(nested)} nested run directories "
                f"(e.g. {nested[0]}). Pointing at the parent directory will make build.py:101's"
                f" runs.glob('bfcl_*') only scan sibling smoke batches, "
                f"or pull the smoke batch and the full-run batch in as duplicates. Point it at the run-directory level instead.")
        if not direct:
            sys.exit(f"[gate C] traj_runs entry {p} has no bfcl_<model> subdirectory at all")
    return f"gate C: all {len(traj_runs)} traj_runs entries are run directories themselves ✓"


def parse_sample_idx(traj):
    """Parse the multi-sample-collection sample index `_r<k>` off the tail of the stem
    in a traj string (shaped like "<batch>/<stem>"). Returns None when it cannot be
    parsed (old-style filename with no suffix)."""
    stem = traj.rsplit("/", 1)[-1]
    m = re.search(r"_r(\d+)$", stem)
    return int(m.group(1)) if m else None


def gate_b_unit_traj(rows_by_split, K):
    """Gate B, second half: the unit -> traj test (K-item test, plans §4 + the §8b
    reinforcing test).

    Deliberately written as a pure function that does not import eval_causal_call/
    torch, so it can be unit-tested on its own outside cprobe-env (see
    tests/test_check_callstr.py); the first half -- the sample-key uniqueness test
    ((event, sent_idx) globally unique, around lines 138-143 in main()) -- stays
    put and is not in this function.

    K = cfg.get("trajs_per_unit", 1). When K==1, the test and its wording are
    byte-identical to the old version (rerunning an old config's CALLSTR_CHECK.md
    must be byte-identical); when K>1:
      - each unit must map to exactly K mutually distinct traj;
      - §8b reinforcing test 1: explicitly re-verify once more that the K traj are
        mutually distinct (a repeated scan producing a same-named traj is already
        supposed to be caught by the sample-key uniqueness test, and the set
        aggregation here naturally deduplicates anyway, so this explicit assertion
        is a defensive test, with its error text kept separate from "wrong count"
        so the two symptoms can be told apart);
      - §8b reinforcing test 2: once the sampling index parsed off the tail of the
        K traj filenames is collected, it must be exactly {0..K-1}, one each;
        failure to parse it (filename lacks the _r<k> suffix) is reported as its
        own separate error.

    rows_by_split: {split: [row, ...]}, each row carries at least the "unit"/"traj"
    keys.
    Returns (ok, msg):
      when ok=True, msg is the success text (without the "gate B sample key..."
      prefix; the caller assembles that itself).
      when ok=False, msg is the failure text (without the "[gate B] " prefix; the
      caller assembles that itself, then calls sys.exit).
    """
    u2t = {}
    for sp in SPLITS:
        for r in rows_by_split[sp]:
            u2t.setdefault(r["unit"], set()).add(r["traj"])

    if K == 1:
        # Old convention kept as-is: len(t) > 1 is fatal, the test and its wording are byte-identical.
        multi = {u: sorted(t) for u, t in u2t.items() if len(t) > 1}
        if multi:
            return False, (f"{len(multi)} units map to multiple trajs, "
                           f"e.g. {list(multi.items())[:2]}; under the same model, one task instance should have only one trajectory")
        return True, f"{len(u2t)} units each map to one traj ✓"

    # K > 1: each unit must have exactly K traj. The example carries (actual count,
    # traj list) laid out alongside K, so no one has to count the traj list's length
    # themselves to see how far off it is.
    bad_count = {u: (len(t), sorted(t)) for u, t in u2t.items()
                if len(t) != K}
    if bad_count:
        ex = list(bad_count.items())[:2]
        return False, (f"{len(bad_count)} units have a traj count that isn't "
                       f"trajs_per_unit={K}, e.g. (unit, (actual count, traj)) {ex}")

    # §8b reinforcing test 1: explicitly assert once more that the K traj are mutually distinct.
    dup_units = [u for u, t in u2t.items() if len(t) != len(set(t))]
    if dup_units:
        return False, (f"{len(dup_units)} units have duplicate traj strings, "
                       f"e.g. {dup_units[:3]}; most likely traj_runs scanned the same batch of trajectories twice")

    # §8b reinforcing test 2: the sampling indices must be exactly {0..K-1}, one each.
    unparsed, idx_of = [], {}
    for u, t in u2t.items():
        idxs = []
        for traj in sorted(t):
            k = parse_sample_idx(traj)
            if k is None:
                unparsed.append((u, traj))
            else:
                idxs.append(k)
        idx_of[u] = idxs
    if unparsed:
        return False, (f"{len(unparsed)} traj filenames carry no sampling index (the stem's tail "
                       f"doesn't parse out _r<k>), e.g. {unparsed[:3]}; when trajs_per_unit="
                       f"{K} > 1, every traj filename must carry a _r0.._r{K - 1} "
                       f"sampling-index suffix")
    bad_idx = {u: sorted(idxs) for u, idxs in idx_of.items()
              if sorted(idxs) != list(range(K))}
    if bad_idx:
        ex = list(bad_idx.items())[:2]
        return False, (f"{len(bad_idx)} units' sampling indices are not "
                       f"exactly one each of {{0..{K - 1}}}, e.g. {ex}")

    return True, f"{len(u2t)} units each map to exactly {K} trajs ✓"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="experiment config json (§2.3)")
    args = ap.parse_args()
    cfg = json.loads(Path(args.config).read_text())
    env = cfg["env"]
    model_full = cfg["model_full"]
    data = Path(cfg["data_out"])
    seed = cfg.get("seed", SEED)
    gates = []

    # ---------- gate C (run first: it is the upstream interception for B) ----------
    gates.append(gate_c(cfg["traj_runs"], env))

    # ---------- read the task list ----------
    lists = {n: set(read_unit_list(cfg["official_split_files"][n]))
             for n in SPLITS}

    rows = {}
    for sp in SPLITS:
        p = data / f"{sp}.jsonl"
        if not p.is_file():
            sys.exit(f"dataset does not exist: {p} (run build.py first)")
        rows[sp] = [json.loads(l) for l in open(p)]

    # ---------- gate A: one model, one dataset ----------
    bad_model = Counter(r["model"] for sp in SPLITS for r in rows[sp]
                        if r["model"] != model_full)
    if bad_model:
        sys.exit(f"[gate A] another model got mixed into the dataset: {dict(bad_model)} "
                 f"(cfg.model_full={model_full})")
    gates.append(f"gate A: all {sum(len(rows[s]) for s in SPLITS)} rows have "
                 f"model=={model_full} ✓")

    # ---------- gate B: sample key unique + unit maps to only one traj ----------
    keyc = Counter((r["event"], r["sent_idx"]) for sp in SPLITS
                   for r in rows[sp])
    dupk = [k for k, c in keyc.items() if c > 1]
    if dupk:
        sys.exit(f"[gate B] (event, sent_idx) duplicated {len(dupk)} times, "
                 f"e.g. {dupk[:3]}; most likely traj_runs scanned the same batch of trajectories twice")
    K = cfg.get("trajs_per_unit", 1)
    gate_ok, gate_msg = gate_b_unit_traj(rows, K)
    if not gate_ok:
        sys.exit(f"[gate B] {gate_msg}")
    gates.append(f"gate B: all {len(keyc)} sample keys are unique; {gate_msg}")

    # ---------- gate D: full check of task-list membership ----------
    wrong = []
    for sp in SPLITS:
        for r in rows[sp]:
            if r["unit"] not in lists[sp]:
                wrong.append((sp, r["unit"]))
    if wrong:
        sys.exit(f"[gate D] {len(wrong)} rows have a unit not in this pile's task list, e.g. {wrong[:3]}")
    gates.append("gate D: task-list ownership checked in full (not sampled) ✓")

    # ---------- gate E: the report wording must not lie ----------
    sp_report = Path(cfg["official_split_files"]["train"]).parent \
        / "SPLIT_REPORT.json"
    if sp_report.is_file():
        meta = json.loads(sp_report.read_text())
        rp = data / "ANNOTATE_REPORT.md"
        txt = rp.read_text() if rp.is_file() else ""
        if meta.get("official_split_exists") is False and "official task list" in txt:
            sys.exit(
                f"[gate E] {sp_report} says this environment has no official partition, "
                f"but {rp}'s report text still prints 'official task list'. "
                f"Write split_desc in the config to state the real split method (build.py takes the text from that field).")
        gates.append(f"gate E: report text matches SPLIT_REPORT ✓"
                     f"(official_split_exists="
                     f"{meta.get('official_split_exists')})")
    else:
        gates.append(f"gate E skipped (couldn't find {sp_report})")

    # ---------- deviation 1: read back the ground-truth call string ----------
    # Import happens only here (see the file-header comment: eval_causal_call pulls in
    # torch, deferred to where it is actually used, so gates A-E and the structural
    # tests can run/be unit-tested in an environment without torch installed).
    from eval_causal_call import norm, parse_call
    # All samples within one event share the same label_call; deduplicate by event, then parse one by one.
    ev_call, ev_split = {}, {}
    for sp in SPLITS:
        for r in rows[sp]:
            ev_call.setdefault(r["event"], (r["label"], r["label_call"],
                                            r["args_named"]))
            ev_split.setdefault(r["event"], sp)
    n_ev = len(ev_call)
    bad_tool, bad_par, comma_val, ok = 0, [], 0, 0
    par_tot = par_ok = 0
    per_split_bad = Counter()
    for evk, (label, call, named) in sorted(ev_call.items()):
        for a in named:
            par_tot += 1
            if "," in a["value"]:
                comma_val += 1
        tool, raw = parse_call(call, env)
        got = [dict(key=k, value=norm(v)) for k, v in raw]
        if tool != label:
            bad_tool += 1
        if got == named:
            ok += 1
            par_ok += len(named)
        else:
            bad_par.append((evk, call, named, got))
            per_split_bad[ev_split[evk]] += 1
            # Score per parameter: read-back counts as successful only when both key and value match.
            gset = {(a["key"], a["value"]) for a in got}
            par_ok += sum(1 for a in named
                          if (a["key"], a["value"]) in gset)

    # ---------- deviation 2: task-list gaps ----------
    gap = {sp: sorted(lists[sp] - {r["unit"] for r in rows[sp]})
           for sp in SPLITS}

    # ---------- deviation 3: tools present in test / absent from train ----------
    tools = {sp: Counter(r["label"] for r in rows[sp]) for sp in SPLITS}
    unseen = sorted(set(tools["test"]) - set(tools["train"]))
    unseen_ev = {t: len({r["event"] for r in rows["test"] if r["label"] == t})
                 for t in unseen}

    # ---------- deviation 4: test pile thickness ----------
    test_ev = len({r["event"] for r in rows["test"]})

    md = [f"# {cfg['run_family']} / {cfg['model_short']} ground-truth call-string round-trip check "
          f"(check_callstr.py)\n",
          f"- SEED={seed} env={env} model={model_full}",
          f"- config={args.config} data={data}",
          "- settings: call `eval_causal_call.parse_call` on each event's label_call, "
          "then compare `(key, norm(value))` position by position against the event's "
          "`args_named`; the round trip succeeds only if every one matches.\n",
          "## structural gates"]
    md += [f"- {g}" for g in gates]
    md += [
        "\n## deviation 1: ground-truth call-string round trip",
        f"- events {n_ev}; round trip succeeded {ok} (**{ok/max(n_ev,1):.4f}**), "
        f"failed {len(bad_par)} (**{len(bad_par)/max(n_ev,1):.4f}**)",
        f"- failures by split: {dict(per_split_bad) or '{}'}",
        f"- events whose tool name can't be cut back out: {bad_tool}",
        f"- arg instances {par_tot}; round trip succeeded {par_ok} "
        f"(**{par_ok/max(par_tot,1):.4f}**)",
        f"- instances whose arg value contains a comma: {comma_val} "
        f"({comma_val/max(par_tot,1):.4f})← this is the main cause of failure",
        f"- **conclusion: the ceiling for params_all_ok / full_call_ok is "
        f"{ok/max(n_ev,1):.4f}**, no matter how correctly the generation side writes it, it still can't reach the rest. "
        f"The reason we don't fix the settings is in the file header.",
        "",
        f"### failure examples (first {EXAMPLES})",
    ]
    for evk, call, named, got in bad_par[:EXAMPLES]:
        md += [f"- `{evk}`",
               f"  - label_call: `{call}`",
               f"  - ground truth on the annotate side: `{named}`",
               f"  - cut back out on the eval side: `{got}`"]
    if not bad_par:
        md.append("(none)")

    md += ["\n## deviation 2: task lists match, but implemented instances have gaps",
           "The three models share the same task list; if a unit's trajectory doesn't produce a single usable event "
           "(thinking <40 characters, or the call regex can't parse it out), that unit doesn't enter this model's dataset. "
           "So the current gate G10 'unit sets are identical across the three models' doesn't hold on bfcl, "
           "across models it's only an **approximate** match on the same task."]
    for sp in SPLITS:
        g = gap[sp]
        shown = ", ".join(g[:MAX_LIST]) + (" ..." if len(g) > MAX_LIST else "")
        md.append(f"- {sp}: task list {len(lists[sp])} tasks -> realized "
                  f"{len({r['unit'] for r in rows[sp]})} tasks; missing {len(g)} tasks"
                  + (f": {shown}" if g else ""))

    md += ["\n## Deviation 3: tools that appear in test but not in train",
           "These tools are in label2id (tool_vocab.json is tallied over the whole pile), "
           "eval_tool.py will not drop them; it is **always scored wrong** = an unreachable accuracy ceiling.",
           f"- {len(unseen)} kinds: {unseen_ev if unseen else '(none)'}",
           f"- vocab size: train {len(tools['train'])} / val {len(tools['val'])}"
           f" / test {len(tools['test'])} kinds"]

    md += ["\n## Deviation 4: test pile thickness",
           f"- test events {test_ev} / instances "
           f"{len({r['unit'] for r in rows['test']})}"
           f" / samples {len(rows['test'])}"]
    if test_ev < THIN_TEST_EVENTS:
        md.append(f"- ⚠ test event count {test_ev} < {THIN_TEST_EVENTS}: "
                  f"the bootstrap confidence interval will be wide, and the low-risk tier (0.05) is quite likely to have no fire point, "
                  f"with θ all null causing eval_causal_call to SystemExit with code 1 directly "
                  f"(precedent: c1_q35_mext). Must be called out at handoff.")
    else:
        md.append(f"- test event count {test_ev} ≥ {THIN_TEST_EVENTS}, thickness normal")

    if sp_report.is_file():
        meta = json.loads(sp_report.read_text())
        md += ["\n## Task list source of truth",
               f"- sole source of truth = the committed txt: {sp_report.parent}",
               f"- {meta.get('truth_source', '')}",
               f"- derivation source md5: {meta.get('md5', {})}"]

    (data / "CALLSTR_CHECK.md").write_text("\n".join(md) + "\n")
    for g in gates:
        print(f"[gate] {g}")
    print(f"{env}/{cfg['model_short']}: read-back {ok}/{n_ev} "
          f"({ok/max(n_ev,1):.4f}) args {par_ok}/{par_tot} "
          f"contains comma {comma_val}; task list gap "
          f"{ {sp: len(gap[sp]) for sp in SPLITS} }")
    print(f"done -> {data / 'CALLSTR_CHECK.md'}")


if __name__ == "__main__":
    main()
