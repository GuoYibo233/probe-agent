"""Extraction-head labels: for every event and every parameter, locate the parameter
value substring within each sample's text (pure CPU).

Source = envs/bert/param_label.py, logic unchanged word for word, only the input/
output paths and pile names changed:
- Input: --config points at the experiment config json, reads
  <data_out>/{train,val,test}.jsonl
- Output: <data_out>/params/{train,val,test}.jsonl + PARAM_LABEL_REPORT.md
  + CHECK_50.md

Convention (unchanged):
- Event re-extraction: reuses the split rules' regex/filtering/event key, but
  **keeps the parameter names** (a kwarg takes its own name; a positional argument
  takes pos0/pos1/...; tales' parameter name is fixed as arg); value normalization
  is exactly the same as build (strip, then strip("\\"'")); empty values are skipped
- Parameter key = f"{tool}.{parameter name}"
- Locating: take the **last** occurrence in the sample's own text (str.rfind),
  record [start,end); when not found, record found=false (= cannot locate it, the
  extraction head has to learn to output this)

Usage: python3 param_label.py --config pipeline/configs/aw_q35.json
"""

import argparse
import glob
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rules import (AW_CALL, BFCL_CALL, MIN_THINK, MODEL_OF,  # noqa: E402
                   SEED, alf_split, first_call_named, mkparams)

SPLITS = ("train", "val", "test")

# alfworld: count of actions the templates cannot parse. The split itself shares
# the same rules.alf_split implementation with build.py, so the two sides'
# conventions cannot drift apart (which is what makes the assert tool ==
# r["label"] at :202 meaningful).
ALF_DROP = Counter()
CTX = 80          # CHECK_50 context character count
KEEP_OK = 60      # reservoir: located examples
KEEP_NG = 20      # reservoir: examples that could not be located


# ---------- trajectory -> (event key, tool, parameter table) ----------

def jsonl_events(runs, pattern, env):
    for f in sorted(glob.glob(str(runs / pattern))):
        batch = Path(f).parent.name
        if MODEL_OF.get(batch.rsplit("_", 1)[1]) is None:
            continue
        recs = [json.loads(l) for l in open(f)]
        gens = {r["step"]: r for r in recs if r["type"] == "gen"}
        envs = {r["step"]: r for r in recs if r["type"] == "env"}
        traj = f"{batch}/{Path(f).stem}"
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
                    tool = f"apis.{m.group(1)}.{m.group(2)}"
                    yield (f"{traj}|s{st}", tool,
                           mkparams(tool,
                                    first_call_named(action, AW_CALL) or []))
            elif env == "alfworld":
                # same alf_split call as build.jsonl_events' alfworld branch
                tool, named, why = alf_split(action)
                if why:
                    ALF_DROP[why] += 1
                elif len(think) >= MIN_THINK:
                    yield (f"{traj}|s{st}", tool, mkparams(tool, named))
            else:
                parts = action.split()
                verb = parts[0].lower() if parts else ""
                if verb and len(think) >= MIN_THINK:
                    rest = " ".join(parts[1:])
                    yield (f"{traj}|s{st}", verb,
                           mkparams(verb, [("arg", rest)] if rest else []))


def bfcl_events(runs):
    for d in sorted(runs.glob("bfcl_*")):
        if MODEL_OF.get(d.name.rsplit("_", 1)[1]) is None:
            continue
        seen = set()
        # sorted: recursive glob is unordered, and dedup-by-id would make the event count drift across reruns
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
                k = 0
                for role, c, rc in msgs:
                    if role == "assistant" and rc.strip() and c.strip():
                        k += 1
                        m = BFCL_CALL.search(c)
                        if m and len(rc.strip()) >= MIN_THINK:
                            tool = m.group(1)
                            yield (f"{d.name}/{entry['id']}|s{k}", tool,
                                   mkparams(tool,
                                            first_call_named(c, BFCL_CALL)
                                            or []))


def collect_events(runs_dirs, env):
    evmap, dup = {}, 0
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
            raise SystemExit(f"unknown env: {env}")
        for key, tool, params in it:
            if key in evmap:
                dup += 1
                continue
            evmap[key] = (tool, params)
    return evmap, dup


# ---------- reservoir sampling (fixed length, fixed seed) ----------

class Pool:
    def __init__(self, cap, rng):
        self.cap, self.rng, self.n, self.buf = cap, rng, 0, []

    def offer(self, item):
        self.n += 1
        if len(self.buf) < self.cap:
            self.buf.append(item)
        else:
            j = self.rng.randrange(self.n)
            if j < self.cap:
                self.buf[j] = item


# ---------- main flow ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="experiment config json (§2.3)")
    args = ap.parse_args()
    cfg = json.loads(Path(args.config).read_text())
    env = cfg["env"]
    runs_dirs = [Path(r) for r in cfg["traj_runs"]]
    data_root = Path(cfg["data_out"])
    out = data_root / "params"
    out.mkdir(parents=True, exist_ok=True)
    seed = cfg.get("seed", SEED)
    rng = random.Random(seed)

    evmap, dup = collect_events(runs_dirs, env)
    print(f"re-extracted {env}: {len(evmap)} events (dup skipped {dup})",
          flush=True)

    report = [f"# {cfg['run_family']}/{cfg['model_short']} parameter localization report"
              "(param_label.py)\n",
              f"- SEED={seed} runs={[str(r) for r in runs_dirs]}",
              f"- data={data_root} out={out}",
              "- localization basis: str.rfind within the sample's own text (the occurrence closest to the end); "
              "not found = extraction failed (found=false)",
              "- param key = tool_name.param_name (kwarg uses its name, positional args pos0/1/...,"
              "tales fixed arg); empty values are skipped\n"]

    pool_ok, pool_ng = Pool(KEEP_OK, rng), Pool(KEEP_NG, rng)
    v3_events = set()
    miss_ev = Counter()          # present in the data, absent from the re-extraction
    n_rows = Counter()
    n_par = Counter()
    n_found = Counter()
    dep_tot = [0] * 10
    dep_hit = [0] * 10
    last_tot = last_hit = 0
    n_assert = 0
    n_short = 0      # located, and the value is <=3 characters (rfind easily hits a coincidental substring)
    n_inthink = 0    # located, and falls within the [THINKING] segment (not copied from the prompt/history)
    noparam_ev = set()

    for sp in SPLITS:
        with open(out / f"{sp}.jsonl", "w") as fo:
            for line in open(data_root / f"{sp}.jsonl"):
                r = json.loads(line)
                ev = r["event"]
                v3_events.add(ev)
                hit = evmap.get(ev)
                if hit is None:
                    miss_ev[sp] += 1
                    continue
                tool, params = hit
                assert tool == r["label"], (ev, tool, r["label"])
                if not params:
                    noparam_ev.add(ev)
                text = r["text"]
                th0 = text.rfind("\n[THINKING]\n") + 12
                b = min(9, int(r["depth"] * 10))
                last = r["sent_idx"] == r["n_sents"] - 1
                plist = []
                for k, v in params:
                    s = text.rfind(v)
                    if s < 0:
                        plist.append(dict(key=k, value=v, start=-1,
                                          end=-1, found=False))
                        pool_ng.offer((env, k, v, text[-120:]))
                    else:
                        e = s + len(v)
                        assert text[s:e] == v, (ev, k)
                        n_assert += 1
                        plist.append(dict(key=k, value=v, start=s,
                                          end=e, found=True))
                        n_found[sp] += 1
                        dep_hit[b] += 1
                        last_hit += last
                        n_short += len(v) <= 3
                        n_inthink += s >= th0
                        pool_ok.offer((env, k, v, s, e, text))
                    n_par[sp] += 1
                    dep_tot[b] += 1
                    last_tot += last
                n_rows[sp] += 1
                fo.write(json.dumps(
                    dict(event=ev, sent_idx=r["sent_idx"],
                         label=r["label"], w=r["w"], model=r["model"],
                         unit=r["unit"], params=plist),
                    ensure_ascii=False) + "\n")

    extra = len(set(evmap) - v3_events)
    tot_par = sum(n_par.values())
    tot_found = sum(n_found.values())
    report += [
        f"\n## {env} — {cfg['model_short']}",
        f"- re-drawn events {len(evmap)} / dataset events {len(v3_events)};"
        f"in dataset but missing from re-draw {sum(miss_ev.values())} samples"
        f"(by split {dict(miss_ev)}); in re-draw but missing from dataset {extra} events",
        f"- param-less events {len(noparam_ev)}"
        f"({len(noparam_ev)/max(len(v3_events),1):.1%})",
        f"- sample rows {sum(n_rows.values())} / param instances {tot_par} / "
        f"localized {tot_found}(**overall localization rate {tot_found/max(tot_par,1):.3f}**)",
        f"- span assertion text[start:end]==value: {n_assert}/{n_assert} ✓",
        "",
        "| split | sample rows | param instances | localization rate |",
        "|---|---|---|---|",
    ]
    for sp in SPLITS:
        report.append(f"| {sp} | {n_rows[sp]} | {n_par[sp]} | "
                      f"{n_found[sp]/max(n_par[sp],1):.3f} |")
    report += [
        "",
        "localization rate across ten depth buckets (0.0 = start of thinking, 0.9 = end of thinking):",
        "",
        "| bucket | " + " | ".join(f"{i/10:.1f}" for i in range(10)) + " |",
        "|---|" + "---|" * 10,
        "| localization rate | " + " | ".join(
            f"{dep_hit[i]/dep_tot[i]:.3f}" if dep_tot[i] else "-"
            for i in range(10)) + " |",
        "| param instances | " + " | ".join(str(dep_tot[i])
                                     for i in range(10)) + " |",
        "",
        f"- end-boundary (whole thinking text read through) localization rate {last_hit/max(last_tot,1):.3f}"
        f"({last_hit}/{last_tot})",
        f"- share of localized ones that fall within the [THINKING] segment "
        f"{n_inthink/max(tot_found,1):.3f}(the rest is copied from the prompt/history)",
        f"- share of localized ones with a value ≤3 characters long {n_short/max(tot_found,1):.3f}"
        "(a short-value rfind may hit a coincidental substring; upper bound on label noise)",
    ]
    if env == "alfworld":
        # must equal the same-named line in ANNOTATE_REPORT byte for byte -- a mismatch means the two sides' splits have drifted apart
        report.append(
            f"- steps dropped because the template could not be cut: {sum(ALF_DROP.values())} "
            f"({dict(sorted(ALF_DROP.items()))})")
        print(f"alfworld dropped for uncuttable: {sum(ALF_DROP.values())} "
              f"{dict(sorted(ALF_DROP.items()))}", flush=True)
    print(f"{env}: params={tot_par} found_rate="
          f"{tot_found/max(tot_par,1):.3f}", flush=True)

    report += [
        "\n## Reference anchors and known noise",
        "- Preliminary pilot: at 25 tokens ahead, only 33.8% of param literal strings had already appeared;"
        "this table's depth buckets give the full-picture version (the further left the bucket, the earlier the fire, the lower the localization rate),"
        "the difference in basis is that this table searches the whole text (prompt + history + thinking prefix),"
        "while the pilot looked only at thinking, so this table's leftmost bucket is well above 33.8%.",
        "- Competing method SPORK's starting param accuracy is 7.6% (the lower-bound anchor for extraction-head accuracy).",
        "- Noise: rfind on a short value (like `20`/`token`) may hit a coincidental substring,"
        "CHECK_50 has already seen instances of this; the share is in the ≤3-character line above,"
        "the extraction-head eval scores by the same basis, so this noise is consistent between train and eval and creates no bias.",
    ]
    (out / "PARAM_LABEL_REPORT.md").write_text("\n".join(report) + "\n")

    # ---------- CHECK_50 ----------
    md = [f"# CHECK_50 — param localization manual-check file (SEED={seed})\n",
          "the localized span is marked with [], with 80 characters of context on each side; check line by line"
          "whether the value inside [] is what this param should have.\n"]
    i = 0
    for (e, k, v, s, en, text) in pool_ok.buf[:50]:
        i += 1
        head = text[max(0, s - CTX):s].replace("\n", "⏎")
        body = text[s:en].replace("\n", "⏎")
        tail = text[en:en + CTX].replace("\n", "⏎")
        md += [f"### [{i}] {e} — `{k}`",
               f"- value: `{v}`  span [{s},{en})",
               f"```\n...{head}[{body}]{tail}...\n```"]
    md += ["\n## Extraction-failed (found=false) cases — check whether it truly did not appear\n"]
    j = 0
    for (e, k, v, tail) in pool_ng.buf[:10]:
        j += 1
        md += [f"### [NG{j}] {e} — `{k}`",
               f"- value: `{v}`",
               f"- last 120 characters of text:\n```\n{tail}\n```"]
    (out / "CHECK_50.md").write_text("\n".join(md) + "\n")
    print(f"done -> {out}(CHECK_50: {i} localized / {j} extraction failed)")


if __name__ == "__main__":
    main()
