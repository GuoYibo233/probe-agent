"""Offline replay experiment for text-layer injection (appworld / gpt-oss).

Question to answer: at the moment the probe decides mid-thinking, "the next call
is this tool," splice that tool's result directly into the thinking stream --
can the model write much less and still emit the correct call?

Four stages, run separately, each writing its own output (exec and merge-exec
are needed only when miss_policy=execute):
  plan   compute the trigger point + generate the predicted call + decide the
         injection content -> plan.jsonl
         (needs GPU, but only the 0.6B parameter pipeline; the probe's trigger
          point reads logits already written to disk)
  exec   replay the appworld environment to that step, actually execute the
         predicted call -> exec_calls.jsonl
         (pure CPU, no GPU used; **inside exec_calls.py, run it only with
          envs/appworld/venv/bin/python** -- in cprobe-env, `import appworld`
          raises ModuleNotFoundError, verified)
  merge-exec  left join plan.jsonl + exec_calls.jsonl -> plan_exec.jsonl
         (pure CPU; the run/score stages after this consume plan_exec.jsonl)
  run    rebuild the prompt, send vLLM completions to continue writing ->
         raw.jsonl
         (needs the gpt-oss-120b service, a single H200 card)
  score  parse, compute the token accounting and call agreement rate ->
         INJECT_REPORT.{json,md}
         (pure CPU)

Eight arms (select with --arms at the run stage, can run just a subset; the
default is still nofill,inject):
  baseline     not run. Uses the original trajectory's numbers directly (the
               model wrote out the whole step itself at the time); it is the
               **main control** for token savings
  nofill       continue writing from the cut point without injecting anything.
               Pipeline health check: it should be ~= baseline; if it does not
               match, the rebuild or sampling convention has a problem and this
               whole batch of numbers is untrustworthy
  inject       continue writing from the cut point and inject the tool result
               ([SYSTEM NOTE] template)
  inject_stop  right after the injection, append the channel-switch bytes,
               cutting off "re-mulling the result after receiving it"
  skel_bare    splice a fence + skeleton into the thinking segment (the tool
               name is fixed by the probe, the model writes only the arguments)
  skel_a       add the line "Thus code:" before the skeleton, then open the fence
  skel_b       prose-style skeleton ("So we will do: "), no fence opened
  skel_switch  channel switch + fence + skeleton, with the skeleton placed
               directly in the final segment
  switch_only  switch the channel only, no skeleton given, the model writes the
               whole call itself -- the accuracy anchor

"What to do when the predicted call does not match the actual one" is
--miss-policy, with three values:
  skip       do not inject; just record the event in the accounting (zero
             environment dependency, fastest way to get the first curve)
  oracle     regardless of whether the prediction is right or wrong, always
             inject the real result of the real call (god's-eye view; measures
             the upper bound of the injection mechanism itself, with the effect
             of prediction accuracy stripped out)
  execute    start appworld, replay the environment to that step (checking the
             recorded result step by step), add the quotes back to the
             unquoted predicted call, and execute it in the real environment;
             **inject it as-is whether it succeeds or errors**
             (true no-holds-barred inject-everything). This is where the cost
             of a wrong guess finally gets counted -- the 372 wrong guesses
             that the skip setting just skips, and the accuracy axis being
             over-optimistic, is no longer a problem.
             `--exec-scope all` (default) also executes hit events, keeping
             the accounting consistent; `--exec-scope miss` executes only the
             wrong guesses, hit events still go through traj_hit.

**What the execute setting measures is "single-step call agreement rate +
injecting the real error when the guess is wrong," not appworld's task-level
score (the Test score).** This file continues writing only one step per event;
it does not run to completion and does not call `world.evaluate()`. The
task-level axis needs a separate in-loop rollout (hook the probe into
run_appworld.py's loop, inject when it fires, run the whole task to completion
and evaluate) -- that is out of scope for this file. Writing the execute
setting's numbers up as "task-level accuracy" in a report is misreporting.

Conventions and known biases (all must be carried in the report, do not omit
them silently):
- The main control for token savings is the **original trajectory's** out
  tokens for that step (already on disk: how many tokens the model actually
  spent writing from the cut point to the call at the time); nofill is only a
  pipeline health check -- re-tokenizing from the cut point and continuing
  cannot reproduce the original token stream verbatim, so the two lines must be
  read together.
  This convention is stamped on the INJECT_REPORT's `saved_baseline` key; any
  downstream code that sums per_event (sweep_theta curve) must check this
  stamp first. Re-running score on an old report (where saved_tok was relative
  to nofill) is blocked; changing the convention requires re-running the whole
  θ curve together with `--rebaseline` explicitly added.
- The injected result is the stdout of the entire code block for that step,
  while the probe predicts the first api call in the code block (the label
  convention at build.py:70-72). When a code block contains multiple calls,
  the injected content is more than "that one call's return value." The first
  version accepts this bias and lists the proportion separately in the report.
  The execute setting **fixes** this (the injected content becomes "that one
  call's return value"), at the cost that hit events are no longer verbatim
  comparable with the already-completed skip/oracle six-point curve -- so the
  score stage buckets by inject_source, and traj_hit must not be mixed with
  exec_pred into a single average.
- The execute setting's injected content depends on the **heuristic** requote
  (gen_call's argument values have their quotes stripped by annotate,
  rules.py:133); adding them back wrong means crediting the probe with a false
  account. The per-argument branches land in arg_modes, and the branch counts
  go into the report; see exec_calls.py --selfcheck for the acceptance check.
- The execute setting **checks step by step** the prefix-replay fidelity
  against the result recorded in the trajectory; events that drift are marked
  prefix_verbatim=False and listed separately in the report -- skipping this
  check would mean executing the predicted call against a wrong state and then
  reporting the result as if it were real.
- The sampling keys for continuation come from the same preset as collection
  (--preset, default is default); but numerical jitter under server-side
  batching can still keep nofill and baseline from matching verbatim.
- A few steps have literal harmony markers mixed into their history, so
  re-tokenizing differs from collection by a few tokens (see the comment at
  the top of rebuild.py); the plan stage tags these as literal_harmony.

Usage:
  cprobe-env/bin/python pipeline/inject/replay_inject.py plan \\
      --ctool-run pipeline/runs/c1_gptoss_ctool \\
      --cgen-run  pipeline/runs/c1_gptoss_cgen \\
      --data      pipeline/data/aw_official_v1/gptoss \\
      --traj-root envs/runs/w0_aw_official/appworld_gptoss \\
      --out       pipeline/inject/runs/aw_gptoss_r10 \\
      --risk 0.1 --miss-policy skip

  For the θ sweep curve (the six-point grid the user approved on 2026-08-01),
  pin the threshold directly with --theta, overriding the --risk lookup:
      ... plan --theta 0.80 --out pipeline/inject/runs/aw_gptoss_th080 ...
  One θ, one run directory; plan/run/score each write their own output
  independently; see sweep_theta.py for the driver shell.

  cprobe-env/bin/python pipeline/inject/replay_inject.py run \\
      --plan pipeline/inject/runs/aw_gptoss_r10/plan.jsonl \\
      --base-url http://tokyo108:8103/v1 --model gpt-oss-120b \\
      --arms nofill,inject

  The skeleton/transition arms need pred_label (the probe's predicted tool
  name) already stored in plan; the form table is produced by
  build_form_table.py, and if it is missing everything defaults to print form:
      ... run --arms skel_bare,skel_a,skel_b,skel_switch,switch_only \\
          --form-table pipeline/inject/form_table.json

  cprobe-env/bin/python pipeline/inject/replay_inject.py score \\
      --run-dir pipeline/inject/runs/aw_gptoss_r10

  # execute setting: after plan, first run the exec stage (pure CPU, a
  # different interpreter), then merge, then run
  envs/appworld/venv/bin/python pipeline/inject/exec_calls.py \\
      --plan  pipeline/inject/runs/aw_gptoss_exec/plan.jsonl \\
      --out   pipeline/inject/runs/aw_gptoss_exec/exec_calls.jsonl \\
      --cache pipeline/inject/exec_cache/aw_gptoss.jsonl \\
      --exp   aw_exec --num-shards 4 --shard-id 0
  cprobe-env/bin/python pipeline/inject/replay_inject.py merge-exec \\
      --plan pipeline/inject/runs/aw_gptoss_exec/plan.jsonl \\
      --exec pipeline/inject/runs/aw_gptoss_exec/exec_calls.jsonl
  cprobe-env/bin/python pipeline/inject/replay_inject.py run \\
      --plan pipeline/inject/runs/aw_gptoss_exec/plan_exec.jsonl --tag _exec ...
  cprobe-env/bin/python pipeline/inject/replay_inject.py score \\
      --run-dir pipeline/inject/runs/aw_gptoss_exec \\
      --plan-file plan_exec.jsonl --tag _exec
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "annotate"))

import rebuild as R                                          # noqa: E402
from rules import AW_CALL, boundaries                        # noqa: E402
# exec_calls.py's module level uses only the standard library + rules, so it can
# be imported in cprobe-env (appworld is imported only after chdir inside its
# main()). Here we only borrow error_kind: the single source of truth for error
# classification lives over there; merge-exec recomputes it from exec_out and
# does not trust the old label in the cache
from exec_calls import err_tail, error_kind, is_bare_print    # noqa: E402
# There is only one implementation of extracting a complete call (balanced
# parentheses + closed fence), shared with extract_completed.py
from parse_call import call_at, complete_call, find_fence_close  # noqa: E402
# There is also only one set of form rules for the skeleton string: the one run
# splices into the prompt, the one score splices back to extract the call, and
# the one extract_completed sends off for real execution -- all three must be
# byte-identical, one character off and the call cannot be extracted
from build_form_table import skeleton as form_skeleton        # noqa: E402

# [Copied verbatim from envs/collect/run_appworld.py:38] uses the same regex to
# extract the code block
CODE_RE = re.compile(r"```python\s*(.*?)```", re.S)

# The injection line template. Reuses the wording already validated in
# oracle_inject/oracle_v1.py:218 and hotpot_inject/hotpot_v1.py:162 (the model
# accepted this format in those two rounds of experiments)
NOTE_TMPL = "\n[SYSTEM NOTE: prefetched {call} = {result}]\n"

# The permission sentence. In the oracle experiments on synthetic tasks it is a
# load-bearing wall (without it, opening injection gets acc 0.00), but the
# 07-27 second wave measured it as unnecessary on real 8B tasks. Off by
# default, turn it on with --permit.
PERMIT = ("\n- A line marked [SYSTEM NOTE: prefetched ...] may appear inside "
          "your reasoning. It is a real result the system fetched ahead of "
          "time; treat it exactly as if you had called that API yourself.")

FINAL_OPEN = "<|channel|>final<|message|>"
DEFAULT_STOP = ["<|return|>"]

# The fallback defaults for --preset merging. merge_client handles only keys
# that appear in cli union fallbacks; a sampling key not in this table = it
# silently has no effect even if the preset sets it (before 2026-08-21 that is
# exactly how top_p/seed got lost); coverage is pinned down by
# tests/test_preset.py.
PRESET_FB = {"max_tokens": 8192, "stop": DEFAULT_STOP,
             "top_p": None, "seed": None}

# These inject_source values have no content to inject, so the inject arm
# sends no request (but still counts toward the token-savings denominator).
# "none" = a wrong guess under the skip setting; "exec_pending" = the execute
# setting has not run the exec stage yet;
# "exec_missing" = the exec stage gave no record for it (the unit crashed
# midway, or that step was never executed in the trajectory).
# **exec_missing must never silently fall back to "none"** -- falling back
# would erase the cost of the wrong guess all over again.
NO_INJECT = {"none", "exec_pending", "exec_missing"}

# The bytes the skeleton/transition arms splice in. SWITCH is the model's
# native thinking->final channel-switch string, FENCE_OPEN is the start of a
# code block in the final segment; both strings are copied verbatim from a
# collected trajectory
SWITCH = "<|end|><|start|>assistant<|channel|>final<|message|>"
FENCE_OPEN = "```python\n"

# Arms whose continuation starts **inside** the final channel: the prompt
# already switched the channel at its end, so FINAL_OPEN will not appear
# again in text; running split_channels directly at the score stage would get
# final="" for everything
ARMS_FINAL = {"inject_stop", "skel_switch", "switch_only"}
# Skeleton arms: the tool name is fixed by the probe's prediction, the model
# writes only the arguments
ARMS_SKEL = {"skel_bare", "skel_a", "skel_b", "skel_switch"}
ARMS_ALL = ["nofill", "inject", "inject_stop", "skel_bare", "skel_a",
            "skel_b", "skel_switch", "switch_only"]

# The main control for token savings, stamped as a convention marker on
# INJECT_REPORT. Old reports don't have this key; back then saved_tok was
# "nofill minus this arm," this version is "original trajectory minus this
# arm." The column name is unchanged but the meaning has changed, so any
# downstream code reading per_event must check this stamp before summing (see
# check_saved_baseline)
SAVED_BASELINE = "traj"


def config_path_for(plan_path):
    """plan filename -> the corresponding config name in the same directory.

    plan.jsonl -> plan_config.json; plan_exec.jsonl -> plan_exec_config.json.
    If the execute setting switches the plan file but still reads
    plan_config.json, the permit convention and the statistics are both wrong.
    """
    p = Path(plan_path)
    return p.parent / (p.stem + "_config.json")


# ---------------------------------------------------------------- plan

def replay_fire(rows, probs, theta):
    """[Copied verbatim from pipeline/eval/eval_causal_call.py:54-71] the sample row for each event's first time crossing θ."""
    ev = defaultdict(list)
    for r, p in zip(rows, probs):
        ev[r["event"]].append((r["sent_idx"], r, p))
    out = {}
    for k, items in ev.items():
        items.sort(key=lambda x: x[0])
        rec = dict(fired=False, ok=False, sent_idx=None, row=None, pred=None,
                   label=items[0][1]["label"])
        for _, r, p in items:
            conf, pred = float(p.max()), int(p.argmax())
            if conf >= theta:
                # pred must be stored: the skeleton arms splice in the probe's predicted tool
                # name, only recording right/wrong is not enough --
                # without the name, downstream code can only splice using the true label,
                # turning the whole curve into a god's-eye view
                rec.update(fired=True, ok=(pred == r["y"]), conf=conf,
                           pred=pred, sent_idx=r["sent_idx"], row=r)
                break
        out[k] = rec
    return out


def external_fire(rows, probs, path):
    """An external verdict file replaces the θ verdict, returning a table shaped
    the same as replay_fire.

    JSONL, one event per line: {"event":..., "fire": bool, "sent_idx": int|null},
    sent_idx given as null takes that event's first sentence. Once this file
    is given, θ plays no part in the verdict at all; conf is still computed as
    usual (the max of ctool softmax on that sentence), kept only as a number
    for reconciliation.
    Once the threshold-producing model the user is currently training
    finishes training, it produces this file directly and this plugs straight
    in, no pipeline change needed.
    """
    dec = {}
    for l in open(path):
        l = l.strip()
        if l:
            o = json.loads(l)
            dec[o["event"]] = o
    ev = defaultdict(list)
    for r, p in zip(rows, probs):
        ev[r["event"]].append((r["sent_idx"], r, p))
    out, n_oob, n_unknown = {}, 0, 0
    for k, items in ev.items():
        items.sort(key=lambda x: x[0])
        rec = dict(fired=False, ok=False, sent_idx=None, row=None, pred=None,
                   label=items[0][1]["label"])
        d = dec.get(k)
        if d is None:
            n_unknown += 1
        elif d.get("fire"):
            want = d.get("sent_idx")
            pick = (items[0] if want is None
                    else next((it for it in items if it[0] == want), None))
            if pick is None:
                # The verdict file points at a sentence that is not in the dataset: count it
                # as not firing, and count it separately -- silently dropping it would
                # quietly change the size of the trigger set
                n_oob += 1
            else:
                _, r, p = pick
                conf, pred = float(p.max()), int(p.argmax())
                rec.update(fired=True, ok=(pred == r["y"]), conf=conf,
                           pred=pred, sent_idx=r["sent_idx"], row=r)
        out[k] = rec
    print(f"external verdict {path}: {len(dec)} entries, events not verdicted {n_unknown},"
          f"pointing to nonexistent sentences {n_oob}", flush=True)
    return out


def gen_calls(cgen_dir, texts, device, bs, max_new):
    """Run the argument-generation pipeline, greedy-writing the whole call on top
    of the trigger-point prefix.

    [Copied verbatim from generate() in eval_causal_call.py:171-192] -- same
    left padding, same truncation to the first line, same reading of call_sep
    from meta.json, keeping it reconcilable with CALLGEN_REPORT.

    Returns (calls, min_ps). min_ps is **the probability of the weakest
    token** in each call, used for cgen self-triggering (only dares to fire
    when the whole call's weakest probability clears the threshold).
    Generation does not keep the probabilities; getting them afterward would
    need a full batch rerun, so they are grabbed here in passing.
    """
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    meta = json.loads((cgen_dir / "best" / "meta.json").read_text())
    sep, max_len = meta.get("call_sep", "\n[CALL] "), meta.get("max_len", 4096)
    tok = AutoTokenizer.from_pretrained(cgen_dir / "best")
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    tok.truncation_side = "left"
    model = AutoModelForCausalLM.from_pretrained(
        cgen_dir / "best",
        dtype=torch.bfloat16 if str(device).startswith("cuda")
        else torch.float32).to(device).eval()
    prompts = [t + sep for t in texts]
    out, min_ps, prev = [], [], tok.padding_side
    tok.padding_side = "left"
    # Stop at these two ids: eos means it actually finished writing, pad is the
    # padding generate adds to sequences that have already ended
    stop_ids = {i for i in (tok.eos_token_id, tok.pad_token_id)
                if isinstance(i, int)}
    nl = {}                              # token id -> whether the decoded text has a newline

    def has_nl(tid):
        if tid not in nl:
            nl[tid] = "\n" in tok.decode([tid])
        return nl[tid]

    with torch.no_grad():
        for i in range(0, len(prompts), bs):
            enc = tok(prompts[i:i + bs], truncation=True,
                      max_length=max(max_len - max_new, 1), padding=True,
                      add_special_tokens=False, return_tensors="pt").to(device)
            g = model.generate(**enc, do_sample=False, max_new_tokens=max_new,
                               eos_token_id=tok.eos_token_id,
                               pad_token_id=tok.pad_token_id,
                               return_dict_in_generate=True,
                               output_scores=True)
            new = g.sequences[:, enc["input_ids"].shape[1]:]
            # Under left padding, every row's generated segment starts at the same
            # column, so scores[t] lines up with new[:, t] -- switch to right padding and
            # each row starts at a different column, this would definitely misalign
            cols = [torch.softmax(s.float(), -1).gather(
                        1, new[:, t:t + 1]).squeeze(1)
                    for t, s in enumerate(g.scores)]
            ps = torch.stack(cols, 1).cpu() if cols else None
            txt = tok.batch_decode(new, skip_special_tokens=True)
            out += [t.split("\n")[0].strip() for t in txt]
            for b in range(new.shape[0]):
                mp = None
                for t in range(0 if ps is None else ps.shape[1]):
                    tid = int(new[b, t])
                    if tid in stop_ids:      # eos and the padding after it don't count
                        break
                    p = float(ps[b, t])
                    mp = p if mp is None else min(mp, p)
                    # The first line stops here, aligned with split("\n")[0] above. The token
                    # that carries the newline counts in: it is often something like `)\n`, and
                    # missing it means missing the trailing parenthesis
                    if has_nl(tid):
                        break
                min_ps.append(mp)            # Record None if not a single token was generated
            print(f"  gen {min(i + bs, len(prompts))}/{len(prompts)}",
                  flush=True)
    tok.padding_side = prev
    del model
    torch.cuda.empty_cache()
    return out, min_ps


def first_api_call(code):
    """The tool name of the first apis.x.y call in the code block. Returns None if not found."""
    m = AW_CALL.search(code or "")
    return f"apis.{m.group(1)}.{m.group(2)}" if m else None


def cmd_plan(a):
    import torch
    ctool, cgen = Path(a.ctool_run), Path(a.cgen_run)
    data, root = Path(a.data), Path(a.traj_root)
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    R.check_system_verbatim()

    rep = json.loads((ctool / "REPLAY_REPORT.json").read_text())
    T = rep["temperature"]
    # θ has three sources: an external verdict file (once given, it takes over
    # completely, θ plays no part), a lookup from the risk setting (the original
    # convention, consistent with eval's chosen_theta), or --theta given directly
    # (used for the θ sweep curve). Temperature calibration T is independent of
    # the risk setting; all sources use the same T, so the points on the curve
    # differ only in the verdict threshold and can be compared directly side by side.
    if a.decision_file:
        theta, theta_source = None, f"external:{a.decision_file}"
    elif a.theta is not None:
        theta, theta_source = a.theta, "explicit"
    else:
        theta = rep["chosen_theta"].get(str(a.risk))
        if theta is None:
            raise SystemExit(f"no risk={a.risk} in θ: {rep['chosen_theta']}")
        theta_source = f"risk={a.risk}"

    # The row filtering must match the eval side line for line, otherwise it is
    # out of order with logits_test.pt
    label2id = json.loads((ctool / "best" / "label_map.json").read_text())
    id2label = {v: k for k, v in label2id.items()}   # Reverse lookup: predicted id -> tool name
    rows = [r for r in (json.loads(l) for l in open(data / "test.jsonl"))
            if r["label"] in label2id]
    for r in rows:
        r["y"] = label2id[r["label"]]
    logits = torch.load(ctool / "logits_test.pt", map_location="cpu")
    assert len(rows) == logits.shape[0], (len(rows), logits.shape)
    probs = torch.softmax(logits / T, -1)
    fired = (external_fire(rows, probs, a.decision_file) if a.decision_file
             else replay_fire(rows, probs, theta))

    keys = [k for k in dict.fromkeys(r["event"] for r in rows)
            if fired[k]["fired"]]
    n_events = len({r["event"] for r in rows})
    print(f"events {n_events} fired {len(keys)} (θ={theta} source {theta_source} "
          f"T={T:.4f} risk={a.risk})", flush=True)
    if a.limit:
        keys = keys[:a.limit]

    print(f"the args pipeline generated {len(keys)} calls ...", flush=True)
    calls, min_ps = gen_calls(cgen, [fired[k]["row"]["text"] for k in keys],
                              a.device, a.bs, a.max_new_tokens)

    traj_cache, plan, drop = {}, [], defaultdict(int)
    for k, gen_call, gen_min_p in zip(keys, calls, min_ps):
        row = fired[k]["row"]
        tp = root / f"appworld_{row['unit']}.jsonl"
        if tp not in traj_cache:
            if not tp.exists():
                drop["traj_missing"] += 1
                continue
            traj_cache[tp] = R.load_traj(tp)
        meta, gens, envs, _ = traj_cache[tp]
        st = row["step"]
        if st not in gens or st not in envs:
            drop["step_missing"] += 1
            continue
        think = (gens[st].get("reasoning") or "").strip()
        b = boundaries(think)
        if row["sent_idx"] >= len(b):
            drop["sent_idx_oob"] += 1
            continue
        cut = b[row["sent_idx"]]
        # Self-check: the recomputed prefix must be byte-identical to the segment the
        # probe consumed in the dataset
        ds_think = row["text"].split("[THINKING]\n", 1)[-1]
        if think[:cut] != ds_think:
            drop["prefix_mismatch"] += 1
            continue
        try:
            msgs = R.build_messages(meta, gens, envs, st)
        except ValueError:
            drop["history_broken"] += 1
            continue

        truth_call = row.get("label_call")
        hit = (gen_call == truth_call)
        result = envs[st].get("result") or ""
        if a.miss_policy == "oracle":
            inj_call, inj_res, src = truth_call, result, "traj_oracle"
        elif a.miss_policy == "execute" and (not hit or a.exec_scope == "all"):
            # The injection content is not known yet -- it needs the exec stage to
            # actually execute it in the environment first.
            # The plan stage runs on the GPU (the cgen pipeline); import appworld must
            # never happen here
            inj_call, inj_res, src = gen_call, None, "exec_pending"
        elif hit:
            inj_call, inj_res, src = gen_call, result, "traj_hit"
        elif a.miss_policy == "skip":
            inj_call, inj_res, src = None, None, "none"
        else:                                    # Unreachable: the three cases above are exhaustive
            raise AssertionError(f"miss_policy={a.miss_policy} has no branch")

        action = envs[st].get("action") or ""
        rec = dict(
            event=k, unit=row["unit"], traj=row["traj"], step=st,
            sent_idx=row["sent_idx"], depth=row["depth"], cut=cut,
            think_len=len(think), conf=fired[k].get("conf"),
            label=row["label"], label_call=truth_call, gen_call=gen_call,
            # The tool name the probe predicted. The skeleton arms splice this in, **not
            # label** (the true label is kept only to compute name_hit); splicing in
            # label would turn the whole curve into a god's-eye view
            pred_id=fired[k].get("pred"),
            pred_label=id2label.get(fired[k].get("pred")),
            gen_min_p=gen_min_p,
            tool_ok=fired[k]["ok"], full_call_ok=hit,
            inject_call=inj_call, inject_result=inj_res, inject_source=src,
            baseline_out_tok=(gens[st].get("usage") or {}).get("out"),
            baseline_action=action,
            baseline_tool=first_api_call(action),
            n_calls_in_block=len(AW_CALL.findall(action)),
            literal_harmony=R.has_literal_harmony(msgs),
            traj_path=str(tp))
        if a.miss_policy == "execute":
            # Add these fields only under the execute setting: skip/oracle's plan.jsonl
            # must stay byte-for-byte unchanged (they already have real production
            # output; changing it would wreck the comparability of the six-point curve)
            rec.update(traj_result=result,      # The whole block of recorded stdout, for the acceptance line to use
                       exec_code=None, arg_modes=None, exec_ok=None)
        plan.append(rec)

    with open(out_dir / "plan.jsonl", "w") as f:
        for p in plan:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    cfg = dict(ctool_run=str(ctool), cgen_run=str(cgen), data=str(data),
               traj_root=str(root), risk=a.risk, theta=theta,
               theta_source=theta_source, temperature=T,
               decision_file=a.decision_file,
               miss_policy=a.miss_policy, permit=a.permit,
               n_events_test=n_events, n_fired=len(keys), n_planned=len(plan),
               drop=dict(drop),
               n_gen_min_p=sum(1 for p in plan
                               if p.get("gen_min_p") is not None),
               n_inject=sum(1 for p in plan
                            if p["inject_source"] not in NO_INJECT),
               n_hit=sum(1 for p in plan if p["full_call_ok"]),
               n_multicall=sum(1 for p in plan if p["n_calls_in_block"] > 1),
               n_literal=sum(1 for p in plan if p["literal_harmony"]))
    if a.miss_policy == "execute":
        # Same as above: add only under the execute setting, skip/oracle's
        # plan_config.json stays byte-for-byte unchanged
        cfg.update(exec_scope=a.exec_scope,
                   n_exec_pending=sum(1 for p in plan
                                      if p["inject_source"] == "exec_pending"))
    (out_dir / "plan_config.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=1))
    print(json.dumps(cfg, ensure_ascii=False, indent=1))


# ----------------------------------------------------------- merge-exec

def expand_exec(spec):
    """Expand the --exec spec into an actual file list.

    When exec_calls.py shards, it automatically writes `exec_calls.jsonl` as
    `exec_calls.s0.jsonl`, so this looks for the original name first, and if
    not found, collects pieces by `<stem>*<suffix>` -- missing even one piece
    means an extra batch of exec_missing for nothing.
    """
    import glob
    out = []
    for tok in (x.strip() for x in spec.split(",")):
        if not tok:
            continue
        hits = sorted(glob.glob(tok))
        if not hits:
            p = Path(tok)
            hits = sorted(glob.glob(str(p.parent / (p.stem + "*" + p.suffix))))
        if not hits:
            raise SystemExit(f"cannot find exec outputs: {tok}")
        out += hits
    return out


def cmd_merge_exec(a):
    """Left join plan.jsonl + exec_calls.jsonl -> plan_exec.jsonl.

    Events with missing exec records are tagged exec_missing and counted
    separately, **never silently falling back to "none"** -- falling back
    would erase the cost of the probe's wrong guess all over again, and that
    is exactly the problem the execute setting is meant to fix.
    """
    plan_p = Path(a.plan)
    out_dir = plan_p.parent
    cfg = json.loads(config_path_for(plan_p).read_text())
    if cfg.get("miss_policy") != "execute":
        raise SystemExit(f"{plan_p} has miss_policy={cfg.get('miss_policy')},"
                         "not execute mode, no exec section to merge")
    plan = [json.loads(l) for l in open(plan_p)]

    files = expand_exec(a.exec)
    ex = {}
    for fp in files:
        for l in open(fp):
            try:
                o = json.loads(l)
            except Exception:                # A half line (process was killed) is dropped outright
                continue
            ex[o["event"]] = o               # Whatever is written later overwrites whatever was written earlier
    print(f"exec outputs {len(files)} files {len(ex)} entries:"
          + ", ".join(Path(f).name for f in files), flush=True)

    n = defaultdict(int)
    modes, ekind, miss_why = Counter(), Counter(), Counter()
    rows = []
    for p in plan:
        r = dict(p)
        if p["inject_source"] != "exec_pending":
            # hit events under exec-scope=miss (traj_hit), oracle, and skip's none:
            # not a single byte is touched, they pass through as-is
            n[p["inject_source"]] += 1
            rows.append(r)
            continue
        e = ex.get(p["event"])
        # Error classification is computed fresh from exec_out; the field in the exec
        # record is not trusted -- the cache may have been written under old rules,
        # and copying it directly would silently carry the old label into the report
        ek = error_kind(e.get("exec_out")) if e else None
        if e is None or e.get("exec_out") is None:
            r["inject_result"], r["inject_source"] = None, "exec_missing"
            why = ("no_record" if e is None
                   else (e.get("error_kind") or "no_output"))
            r["exec_missing_reason"] = why
            miss_why[why] += 1
            n["exec_missing"] += 1
        else:
            r["inject_result"] = e["exec_out"]
            r["inject_source"] = "exec_pred" if ek is None else "exec_error"
            n[r["inject_source"]] += 1
        if e is not None:
            # The three comparisons are also computed fresh (using plan's own
            # traj_result / baseline_action); likewise not copied from the exec record --
            # the cache may have been written by a previous version's comparison method
            eo, tr = e.get("exec_out"), p.get("traj_result")
            r.update(exec_code=e.get("exec_code"),
                     arg_modes=e.get("arg_modes"), exec_ok=(ek is None),
                     error_kind=ek,
                     prefix_verbatim=e.get("prefix_verbatim"),
                     drift_step=e.get("drift_step"),
                     matched_traj_result=(eo == tr),
                     matched_traj_error=(
                         None if err_tail(eo) is None or err_tail(tr) is None
                         else err_tail(eo) == err_tail(tr)),
                     traj_bare_print=is_bare_print(p.get("baseline_action")),
                     exec_cache_hit=e.get("cache_hit"))
            modes.update(e.get("arg_modes") or [])
            if ek:
                ekind[ek] += 1
        rows.append(r)

    with open(out_dir / "plan_exec.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    inj = [r for r in rows if r["inject_source"] not in NO_INJECT]
    fired_exec = [r for r in rows if r["inject_source"] in
                  ("exec_pred", "exec_error")]
    verb = [r for r in fired_exec if r.get("matched_traj_result") is not None]
    # The acceptance line accepts only events where all three conditions hold:
    # the prediction matches the truth, the code block contains only one call,
    # and that code block is a single clean print(call). Missing any one
    # condition makes the two sides incomparable, and including it would only
    # raise a false alarm (see the BARE_PRINT / err_tail comments in
    # exec_calls.py for details)
    acc = [r for r in fired_exec
           if r.get("full_call_ok") and r.get("n_calls_in_block") == 1
           and r.get("traj_bare_print")]
    acc_ok = [r for r in acc if r.get("matched_traj_result")
              or r.get("matched_traj_error")]
    mixed = [r for r in fired_exec
             if r.get("full_call_ok") and r.get("n_calls_in_block") == 1
             and not r.get("traj_bare_print")]
    out = dict(cfg)
    out.update(
        exec_files=[str(f) for f in files], plan_file="plan_exec.jsonl",
        n_inject=len(inj), by_inject_source=dict(n),
        n_exec_pred=n["exec_pred"], n_exec_error=n["exec_error"],
        n_exec_missing=n["exec_missing"], exec_missing_reason=dict(miss_why),
        exec_error_rate=(round(n["exec_error"] / len(fired_exec), 4)
                         if fired_exec else None),
        arg_modes=dict(modes), error_kind=dict(ekind),
        n_drift=sum(1 for r in fired_exec
                    if r.get("prefix_verbatim") is False),
        # Acceptance line: hit + single call + the code block is a single clean
        # print(call), and the execution output matches the recorded result
        # (verbatim, or the error message matches when it errors)
        acceptance_matched=len(acc_ok), acceptance_n=len(acc),
        acceptance_exact=sum(1 for r in acc if r.get("matched_traj_result")),
        acceptance_excluded_mixed=len(mixed),
        matched_traj_result_all=(
            round(sum(1 for r in verb if r["matched_traj_result"]) / len(verb),
                  4) if verb else None))
    (out_dir / "plan_exec_config.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps(out, ensure_ascii=False, indent=1))
    if n["exec_missing"]:
        print(f"\nnote: {n['exec_missing']} events have no exec record, marked "
              f"exec_missing, the inject arm sends no request for them, but they still count in the"
              f"saved-token denominator. reason distribution {dict(miss_why)}")


# ---------------------------------------------------------------- run

def load_form_table(path):
    """Tool name -> skeleton form (tallied by build_form_table.py from native
    trajectories).

    If the file is missing, return an empty table, default every skeleton to
    print form, and warn only once -- missing one statistics table should not
    stop the skeleton experiment from running, but it also must not silently
    be treated as "every tool is print form."
    """
    p = Path(path)
    if not p.exists():
        print(f"note: form_table does not exist ({p}), the skeleton always uses print form;"
              "to use assignment form split by tool, run build_form_table.py first", flush=True)
        return {}
    return json.loads(p.read_text())


def skeleton(p, form_table):
    """The skeleton string for one plan record. Returns None if there is no
    predicted tool name.

    What gets spliced in is **the probe's predicted pred_label, never the
    true label** -- splicing in the true label would turn the whole curve
    into a god's-eye view.
    The form split (assignment form `var = apis.x.y` versus `print(apis.x.y`)
    and the tokenizer hard rule of "never a trailing opening parenthesis"
    both live in build_form_table.skeleton; here we only look up the value
    and fall back on empty.
    """
    name = p.get("pred_label")
    if not name:
        return None
    return form_skeleton(name, form_table)


def build_splice(arm, p, form_table):
    """Build, per arm, "the piece that follows the thinking segment's head."

    Returns None to mean this arm cannot be built for this event (a skeleton
    arm with no pred_label); under the normal path this has already been
    filtered out by todo.
    """
    if arm == "nofill":
        return ""
    if arm in ("inject", "inject_stop"):
        note = NOTE_TMPL.format(call=p["inject_call"],
                                result=p["inject_result"])
        # inject_stop adds an extra channel-switch string: cut off "re-mulling the
        # result after receiving it" outright
        return note + SWITCH if arm == "inject_stop" else note
    if arm == "switch_only":
        return SWITCH
    sk = skeleton(p, form_table)
    if sk is None:
        return None
    if arm == "skel_bare":
        return "\n" + FENCE_OPEN + sk
    if arm == "skel_a":
        return "\nThus code:\n" + FENCE_OPEN + sk
    if arm == "skel_b":
        return "\nSo we will do: " + sk
    if arm == "skel_switch":
        return SWITCH + FENCE_OPEN + sk
    raise SystemExit(f"unknown arm: {arm} (options: {','.join(ARMS_ALL)})")


def spliced_tail(arm, p, form_table):
    """The piece (fence + skeleton) that is fed in before continuation but does
    not land in raw's text.

    The score stage must splice it back in front of text to extract the call:
    `apis.`'s start is in the prompt, text has only the arguments left, and
    without splicing it back the parser cannot find the call's start at all.
    Among the skeleton arms, bare/a/b's skeleton lands in the analysis
    segment, switch's lands in the final segment.
    """
    if arm not in ARMS_SKEL:
        return ""
    sk = skeleton(p, form_table)
    if sk is None:
        return ""
    return sk if arm == "skel_b" else FENCE_OPEN + sk


def sample_extras(a):
    """top_p/seed enter the request body only when given explicitly (the same
    convention as Chat._sample_extras in envs/collect/common.py): when not
    given, the request body is byte-identical to before these two keys were
    added."""
    d = {}
    if getattr(a, "top_p", None) is not None:
        d["top_p"] = a.top_p
    if getattr(a, "seed", None) is not None:
        d["seed"] = a.seed
    return d


def gen_payload(a, prompt):
    """How the replay's main generation request body is packed. The sampling
    keys in the preset's client section (temperature/top_p/max_tokens/stop/
    seed) all land here, pinned down by tests/test_preset.py."""
    return dict(model=a.model, prompt=prompt, max_tokens=a.max_tokens,
                temperature=a.temperature, stop=a.stop,
                skip_special_tokens=False, **sample_extras(a))


def post_completions(base_url, payload, timeout, retries=4):
    url = base_url.rstrip("/") + "/completions"
    body = json.dumps(payload).encode()
    for att in range(retries):
        try:
            req = urllib.request.Request(
                url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if att == retries - 1:
                raise
            print(f"    retry {att + 1}: {e}", flush=True)
            time.sleep(2 ** att)


def cmd_run(a):
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from transformers import AutoTokenizer

    # --preset merge (explicit CLI value > preset client section > original
    # default), the expanded value is hung back onto a;
    # --preset defaults to default, the temperature key comes only from the
    # preset file
    root = str(HERE.parents[1])
    if root not in sys.path:
        sys.path.append(root)
    from preset_loader import load_preset, merge_client, require_temperature
    pre = load_preset(a.preset)
    eff = merge_client(
        {"max_tokens": a.max_tokens,
         "temperature": getattr(a, "temperature", None)},
        pre.get("client"),
        PRESET_FB)
    a.max_tokens = eff["max_tokens"]
    a.temperature = require_temperature(eff["temperature"], pre["_name"])
    a.stop = eff["stop"]
    a.top_p = eff["top_p"]
    a.seed = eff["seed"]

    plan_path = Path(a.plan)
    out_dir = plan_path.parent
    # The config follows the plan filename: plan_exec.jsonl pairs with
    # plan_exec_config.json.
    # Hard-reading plan_config.json would get the wrong permit convention and
    # statistics under the execute setting
    cfg = json.loads(config_path_for(plan_path).read_text())
    plan = [json.loads(l) for l in open(plan_path)]
    if a.limit:
        plan = plan[:a.limit]
    pend = sum(1 for p in plan if p["inject_source"] == "exec_pending")
    if pend:
        raise SystemExit(
            f"{plan_path} has {pend} events still exec_pending (injection content is empty)."
            "execute mode's dependency order is plan -> exec_calls.py -> merge-exec -> run,"
            "finish the exec section first")
    arms = [x.strip() for x in a.arms.split(",") if x.strip()]
    bad = [x for x in arms if x not in ARMS_ALL]
    if bad:
        raise SystemExit(f"unknown arm: {','.join(bad)}; options: {','.join(ARMS_ALL)}")
    form_table = load_form_table(a.form_table)
    tok = AutoTokenizer.from_pretrained(a.tokenizer)
    add_permit = bool(a.permit or cfg.get("permit"))

    rp = out_dir / f"raw{a.tag}.jsonl"
    done = set()
    if rp.exists():                              # Resume from a checkpoint
        for l in open(rp):
            try:
                o = json.loads(l)
                done.add((o["event"], o["arm"]))
            except Exception:
                pass

    def wanted(p, arm):
        """Whether this arm has material to splice for this event. If material is missing, no request is sent, but it still counts toward the denominator."""
        if arm in ("inject", "inject_stop"):
            return p["inject_source"] not in NO_INJECT   # No content to inject
        if arm in ARMS_SKEL:
            return bool(p.get("pred_label"))             # The skeleton cannot pin down a tool name
        return True

    todo = [(p, arm) for p in plan for arm in arms
            if (p["event"], arm) not in done and wanted(p, arm)]
    if (any(x in ARMS_SKEL for x in arms)
            and not any(p.get("pred_label") for p in plan)):
        print("note: this plan has not a single pred_label (an old-version plan section does not store the"
              "probe's predicted tool name), the skeleton arm will be filtered out entirely -- rerun plan first", flush=True)
    print(f"plan {len(plan)} entries x {arms}; already have {len(done)}, still to run "
          f"{len(todo)}, concurrency {a.concurrency}", flush=True)

    sink = open(rp, "a")
    lock, cache, clock = threading.Lock(), {}, threading.Lock()
    stat = dict(n=0, t0=time.time(), fail=0)

    def traj_of(path):
        with clock:
            if path not in cache:
                cache[path] = R.load_traj(Path(path))
            return cache[path]

    def one(p, arm):
        meta, gens, envs, _ = traj_of(p["traj_path"])
        msgs = R.build_messages(meta, gens, envs, p["step"])
        if add_permit:
            msgs = [dict(m) for m in msgs]
            msgs[0]["content"] = msgs[0]["content"] + PERMIT
        prefix = R.build_prefix(tok, msgs,
                                pin_date=None if a.no_pin_date
                                else R.COLLECT_DATE)
        if not a.assume_date:
            R.assert_date(prefix)
        think = (gens[p["step"]].get("reasoning") or "").strip()
        head = think[:p["cut"]]
        head_tok = len(tok.encode(head, add_special_tokens=False))
        splice = build_splice(arm, p, form_table)
        prompt = prefix + R.ANALYSIS_OPEN + head + splice
        if a.dry_run:
            return dict(event=p["event"], arm=arm, dry=True,
                        prompt_chars=len(prompt), head_tok=head_tok,
                        note_chars=len(splice),
                        prompt_tok=len(tok.encode(
                            prompt, add_special_tokens=False)),
                        baseline_out_tok=p["baseline_out_tok"],
                        tail=prompt[-160:])
        t0 = time.time()
        r = post_completions(a.base_url, gen_payload(a, prompt), a.timeout)
        ch = r["choices"][0]
        return dict(event=p["event"], arm=arm, text=ch["text"],
                    finish_reason=ch.get("finish_reason"),
                    prompt_tok=r["usage"]["prompt_tokens"],
                    gen_tok=r["usage"]["completion_tokens"],
                    head_tok=head_tok, note_chars=len(splice),
                    wall_s=round(time.time() - t0, 2))

    with ThreadPoolExecutor(max_workers=a.concurrency) as ex:
        futs = {ex.submit(one, p, arm): (p["event"], arm) for p, arm in todo}
        for fu in as_completed(futs):
            ev, arm = futs[fu]
            try:
                rec = fu.result()
            except Exception as e:
                stat["fail"] += 1
                print(f"  FAIL {ev} {arm}: {type(e).__name__}: {e}",
                      flush=True)
                continue
            with lock:
                sink.write(json.dumps(rec, ensure_ascii=False) + "\n")
                sink.flush()
                stat["n"] += 1
                if stat["n"] % 50 == 0:
                    el = time.time() - stat["t0"]
                    rate = stat["n"] / el
                    left = (len(todo) - stat["n"]) / rate if rate else 0
                    print(f"  {stat['n']}/{len(todo)} "
                          f"{rate:.2f} req/s ETA {left/60:.1f} min",
                          flush=True)
    sink.close()
    print(f"finished {stat['n']}/{len(todo)}; failed {stat['fail']} -> {rp}")


# ---------------------------------------------------------------- score

def split_channels(text):
    """Split the continuation into (analysis remainder, final content)."""
    if FINAL_OPEN in text:
        head, tail = text.split(FINAL_OPEN, 1)
        return head, tail
    return text, ""


def check_saved_baseline(d, tag, rebaseline):
    """Before overwriting an old report, compare the token-savings convention
    once; the two conventions must not swap within the same batch directory.

    After saved_tok changed from "relative to nofill" to "relative to the
    original trajectory," the per_event column name did not change at all,
    but its meaning did. Downstream, sweep_theta's curve subcommand sums
    per_event directly across each θ directory into one curve; rerunning
    score for just one θ turns the curve into half old convention and half
    new convention -- invisible on the surface, since the column name and the
    historical rows look exactly the same. So this blocks it here: if the
    report sitting in the directory uses a different convention from this
    version, stop; to actually switch conventions, every θ point on the same
    curve must be rerun together.
    """
    rep = d / f"INJECT_REPORT{tag}.json"
    if not rep.exists():
        return
    try:
        old = json.loads(rep.read_text()).get("saved_baseline")
    except (ValueError, OSError):
        return                      # The old report itself is broken, overwrite as usual
    if old == SAVED_BASELINE:
        return
    if rebaseline:
        print(f"[settings switch] {rep.name}: saved_baseline {old!r} -> "
              f"{SAVED_BASELINE!r}. the other points on the same θ curve must also rerun score,"
              "otherwise sweep_theta curve will sum saved_tok from two different settings together")
        return
    raise SystemExit(
        f"{rep} is an old report with saved_baseline={old!r} (saved_tok = nofill's out "
        f"token minus this arm), this version writes {SAVED_BASELINE!r} (saved_tok = the original trajectory's "
        "out token at that step minus this arm). the two columns share a name but differ in meaning: rerunning just "
        "this one dir would sum two settings into one θ curve, and the report cannot tell them apart. confirm "
        "you want to switch settings and will rerun the whole curve's θ points, then add --rebaseline.")


def cmd_score(a):
    d = Path(a.run_dir)
    # Check the convention first, then do the several minutes of parsing work: a
    # convention change must be caught before the overwrite happens
    check_saved_baseline(d, a.tag, a.rebaseline)
    plan_p = d / a.plan_file
    cfg = json.loads(config_path_for(plan_p).read_text())
    is_exec = cfg.get("miss_policy") == "execute"
    # The skeleton arm's skeleton string itself is not in raw; it must be
    # re-spliced using the same form table before a call can be extracted.
    # If form_table changed between run and score, the skeleton rebuilt here will
    # not match
    form_table = load_form_table(a.form_table)
    plan = {json.loads(l)["event"]: json.loads(l) for l in open(plan_p)}
    raw = defaultdict(dict)
    for l in open(d / f"raw{a.tag}.jsonl"):
        o = json.loads(l)
        raw[o["event"]][o["arm"]] = o          # Whatever is written later overwrites whatever was written earlier

    per, by_arm = [], defaultdict(list)
    for ev, arms in raw.items():
        p = plan.get(ev)
        if p is None:
            continue
        nof = arms.get("nofill")
        nof_out = (nof["head_tok"] + nof["gen_tok"]) if nof else None
        for arm, o in arms.items():
            tail = spliced_tail(arm, p, form_table)
            if arm in ARMS_SKEL and o.get("note_chars") is not None:
                # If the form table changed between run and score (build_form_table was
                # rerun, assign_share crossed 0.5, or the same table was not passed along),
                # the skeleton rebuilt here is no longer the string originally fed in, and
                # skeleton_done / call_out / post_think shift silently across the board.
                # raw stores the character count of the piece that was originally spliced
                # in; checking against it catches this on the spot
                sp = build_splice(arm, p, form_table)
                if sp is None or len(sp) != o["note_chars"]:
                    raise SystemExit(
                        f"form_table mismatch: {ev} {arm} spliced in "
                        f"{o['note_chars']} characters at run time, rebuilding from {a.form_table} gives "
                        f"{len(sp) if sp is not None else 0} characters -- "
                        "score must use the same table used at run time")
            if arm in ARMS_FINAL:
                # These arms' continuation starts **inside** the final channel: FINAL_OPEN
                # will never appear in text at all, running split_channels on it gets
                # final="" and wipes everything out.
                # Record the analysis remainder as empty, final = the spliced-in piece +
                # continuation
                rest, final = "", tail + o["text"]
            else:
                rest, final = split_channels(o["text"])
                rest = tail + rest      # The skeleton is in analysis, splice it back to find the start
            m = CODE_RE.search(final)
            code = m.group(1) if m else ""
            tool = first_api_call(code)
            sk_call, skel_done, tool_rw, post_think = None, None, None, None
            if arm in ARMS_FINAL:
                post_think = 0          # Already in the final segment: no "rethink after filling in" step
            if arm in ARMS_SKEL:
                # The segment where the skeleton lives: bare/a/b are in analysis, switch is in final.
                # Whether it completes, and how long it keeps thinking after completing, are both
                # measured from this segment.
                # The call's starting point is a **known position**: the end of tail is pred_label
                # itself. Per the hard rule, the skeleton carries no trailing open-parenthesis; without
                # anchoring this position, a line the model writes on its own on a new line gets
                # treated as "the skeleton completed" (observed: the model writes "Wait, that is
                # wrong." then switches to a different tool on its own, and skeleton_done still
                # reports True), which wrecks this setting's headline metric.
                seg = final if arm == "skel_switch" else rest
                pred = p.get("pred_label") or ""
                sk_call, sk_end = (call_at(seg, len(tail) - len(pred))
                                   if tail and pred else (None, None))
                fenced = tail.startswith(FENCE_OPEN)
                fin = (find_fence_close(seg, sk_end)
                       if sk_call is not None and fenced else None)
                skel_done = sk_call is not None and (fin is not None
                                                     or not fenced)
                # When it never enters the body segment (the skeleton arm often doesn't transition),
                # tool is None: that means "no body was written," not "no rewrite happened." Recording
                # None keeps it out of the denominator, otherwise the rewrite rate gets diluted low.
                tool_rw = (tool != p.get("pred_label")) if tool else None
                if arm not in ARMS_FINAL and sk_call is not None:
                    # How many characters it keeps thinking between the skeleton-completion point (counted
                    # to the fence close if there is a fence) and the transition; if there's no transition,
                    # rest is the whole continuation, measured all the way to the end.
                    end = fin if fin is not None else sk_end
                    post_think = len(rest) - end
            # Full call: for the skeleton arm, take the one completed at the skeleton (the args
            # the model writes itself once the tool name is pinned down -- also the one
            # extract_completed.py sends off for real execution); fall back to the body segment
            # if it can't be extracted. Other arms only look at the body segment. Both sides
            # must use the same accounting, or the numbers won't reconcile.
            # Note that on events with tool_rewritten=True, what gets extracted is still the one
            # at the skeleton, even though the model has switched tools in the body segment --
            # that subset is sent for real execution, measuring calls the model abandoned on its
            # own. Read the numbers split by tool_rewritten (the accounting notes are in the md
            # report).
            call_out = (sk_call if sk_call is not None
                        else complete_call(final)[0])
            out_tok = o["head_tok"] + o["gen_tok"]
            base = p.get("baseline_out_tok")
            # The primary comparison is baseline (the original trajectory): how many out tokens
            # the model actually spent writing this step through to the call, taken straight from
            # the record. nofill is downgraded to a pipeline sanity check -- it's built with
            # exactly the same prompt construction as this arm (same reconstruction, same
            # truncation at the cut, same re-tokenizing), differing only in the spliced-in
            # segment. So nofill approx baseline is what shows the reconstruction and sampling
            # accounting haven't drifted, which is what clears this batch of numbers to ship.
            rec = dict(
                event=ev, arm=arm, depth=p["depth"], conf=p["conf"],
                inject_source=p["inject_source"],
                full_call_ok=p["full_call_ok"], tool_ok=p["tool_ok"],
                pred_label=p.get("pred_label"), gen_min_p=p.get("gen_min_p"),
                name_hit=(p.get("pred_label") == p["label"]),
                out_tok=out_tok, nofill_out_tok=nof_out,
                baseline_out_tok=base,
                saved_tok=(base - out_tok) if base else None,
                saved_ratio=(round((base - out_tok) / base, 4)
                             if base else None),
                nofill_delta=((nof_out - out_tok)
                              if nof_out is not None else None),
                baseline_drift=(out_tok - base) if base else None,
                gen_tok=o["gen_tok"], head_tok=o["head_tok"],
                has_code=bool(m), tool_out=tool, call_out=call_out,
                skeleton_done=skel_done, tool_rewritten=tool_rw,
                post_think_chars=post_think,
                # A successful injection looks like "skip the injected call and move straight to the
                # next thing," so a high repeated rate is the bad outcome (the model ignored the
                # injection).
                # Note that appworld embeds calls inside python, and the result often has to be
                # assigned to a variable before use, so calling it again once doesn't necessarily
                # mean the injection was ignored -- look at both metrics together.
                repeated_injected=(tool == p["label"]),
                advanced=(tool is not None and tool != p["label"]),
                same_as_baseline_step=(tool == p["baseline_tool"]),
                finish_reason=o["finish_reason"])
            if is_exec:
                # Add only in the execute cell: per_event.jsonl for skip/oracle stays byte-for-byte unchanged
                rec.update(
                    exec_ok=p.get("exec_ok"),
                    matched_traj_result=p.get("matched_traj_result"),
                    prefix_verbatim=p.get("prefix_verbatim"),
                    error_kind=p.get("error_kind"),
                    arg_modes=p.get("arg_modes"))
            per.append(rec)
            by_arm[arm].append(rec)

    def agg(rs):
        n = len(rs)
        if not n:
            return {}
        sv = sorted(r["saved_tok"] for r in rs if r["saved_tok"] is not None)
        sr = [r["saved_ratio"] for r in rs if r["saved_ratio"] is not None]
        dr = sorted(abs(r["baseline_drift"]) for r in rs
                    if r["baseline_drift"] is not None)
        nd = sorted(r["nofill_delta"] for r in rs
                    if r["nofill_delta"] is not None)
        sd = [r["skeleton_done"] for r in rs if r["skeleton_done"] is not None]
        tw = [r["tool_rewritten"] for r in rs
              if r["tool_rewritten"] is not None]
        pt = sorted(r["post_think_chars"] for r in rs
                    if r["post_think_chars"] is not None)
        return dict(
            n=n,
            saved_tok_mean=round(sum(sv) / len(sv), 1) if sv else None,
            saved_tok_median=sv[len(sv) // 2] if sv else None,
            saved_ratio_mean=round(sum(sr) / len(sr), 4) if sr else None,
            saved_positive=(round(sum(1 for x in sv if x > 0) / len(sv), 4)
                            if sv else None),
            out_tok_mean=round(sum(r["out_tok"] for r in rs) / n, 1),
            has_code=round(sum(r["has_code"] for r in rs) / n, 4),
            repeated_injected=round(sum(r["repeated_injected"]
                                        for r in rs) / n, 4),
            advanced=round(sum(r["advanced"] for r in rs) / n, 4),
            baseline_drift_median=dr[len(dr) // 2] if dr else None,
            # Sanity check: the gap between nofill and this arm only shows whether the pipeline
            # has drifted, it is not counted as a gain
            nofill_delta_median=nd[len(nd) // 2] if nd else None,
            skeleton_done=round(sum(sd) / len(sd), 4) if sd else None,
            tool_rewritten=round(sum(tw) / len(tw), 4) if tw else None,
            post_think_median=pt[len(pt) // 2] if pt else None,
            truncated=round(sum(r["finish_reason"] == "length"
                                for r in rs) / n, 4))

    # Bucket by trigger depth: this gets an "injection position vs. gain" curve for free, to check whether there's a dead zone
    buckets = defaultdict(lambda: defaultdict(list))
    for r in per:
        buckets[min(int(r["depth"] * 5), 4)][r["arm"]].append(r)

    # Write saved_tok's primary comparison into the report: older reports don't have this
    # key, so readers (and sweep_theta downstream computing the curve) can tell whether
    # the per_event in hand is "relative to the original trajectory" or the old
    # "relative to nofill" -- mixing the two saved_tok conventions into the same ratio
    # is a miscalculation
    out = dict(run_dir=str(d), config=cfg, saved_baseline=SAVED_BASELINE,
               by_arm={k: agg(v) for k, v in by_arm.items()},
               by_depth={f"{b*0.2:.1f}-{(b+1)*0.2:.1f}":
                         {k: agg(v) for k, v in arms.items()}
                         for b, arms in sorted(buckets.items())},
               by_hit={
                   "hit": {k: agg([r for r in v if r["full_call_ok"]])
                           for k, v in by_arm.items()},
                   "miss": {k: agg([r for r in v if not r["full_call_ok"]])
                            for k, v in by_arm.items()}})
    # The skeleton arm's wrong-guess bucket is name_hit (whether the probe's predicted
    # tool name is correct), not full_call_ok: the skeleton only pins the tool name, the
    # args are written fresh by the large model, so bucketing by whether the whole call
    # is correct buckets the wrong thing
    skel = {k: v for k, v in by_arm.items() if k in ARMS_SKEL}
    if skel:
        out["by_name_hit"] = {
            "hit": {k: agg([r for r in v if r["name_hit"]])
                    for k, v in skel.items()},
            "miss": {k: agg([r for r in v if not r["name_hit"]])
                     for k, v in skel.items()}}
    if is_exec:
        # The execute cell must be bucketed by injection source: what exec_pred injects is
        # "that one call's return value," what traj_hit injects is "the whole stdout block" --
        # on the 99/1061 multi-call blocks these are not the same thing.
        # Averaging them into one number mixes the two conventions together, and the reported
        # token savings won't mean anything.
        src_of = {}
        for r in per:
            src_of.setdefault(r["inject_source"], []).append(r)
        out["by_inject_source"] = {
            s: {arm: agg([r for r in rs if r["arm"] == arm])
                for arm in sorted({r["arm"] for r in rs})}
            for s, rs in sorted(src_of.items())}
        pl = list(plan.values())
        fired_exec = [p for p in pl if p["inject_source"] in
                      ("exec_pred", "exec_error")]
        # See the comment in merge-exec for the acceptance line's three thresholds: missing any one makes the two sides incomparable
        acc = [p for p in fired_exec
               if p.get("full_call_ok") and p.get("n_calls_in_block") == 1
               and p.get("traj_bare_print")]
        vb = [p for p in fired_exec
              if p.get("matched_traj_result") is not None]
        out["exec"] = dict(
            note="the accuracy is the single-step call consistency rate, not appworld task-level score",
            exec_scope=cfg.get("exec_scope"),
            n_exec_pred=sum(1 for p in pl
                            if p["inject_source"] == "exec_pred"),
            n_exec_error=sum(1 for p in pl
                             if p["inject_source"] == "exec_error"),
            n_exec_missing=sum(1 for p in pl
                               if p["inject_source"] == "exec_missing"),
            exec_error_rate=(round(sum(1 for p in fired_exec
                                       if p["inject_source"] == "exec_error")
                                   / len(fired_exec), 4)
                             if fired_exec else None),
            # Acceptance line: hit + single call + the code block is one clean print(call)
            acceptance_matched=sum(1 for p in acc
                                   if p.get("matched_traj_result")
                                   or p.get("matched_traj_error")),
            acceptance_exact=sum(1 for p in acc
                                 if p.get("matched_traj_result")),
            acceptance_n=len(acc),
            acceptance_excluded_mixed=sum(
                1 for p in fired_exec
                if p.get("full_call_ok") and p.get("n_calls_in_block") == 1
                and not p.get("traj_bare_print")),
            matched_traj_result=(round(sum(1 for p in vb
                                           if p["matched_traj_result"])
                                       / len(vb), 4) if vb else None),
            n_drift=sum(1 for p in fired_exec
                        if p.get("prefix_verbatim") is False),
            arg_modes=dict(Counter(m for p in fired_exec
                                   for m in (p.get("arg_modes") or []))),
            error_kind=dict(Counter(p["error_kind"] for p in fired_exec
                                    if p.get("error_kind"))))
    (d / f"INJECT_REPORT{a.tag}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1))
    with open(d / f"per_event{a.tag}.jsonl", "w") as f:
        for r in per:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    L = [f"# Injection replay report {d.name}", "",
         f"- settings risk={cfg['risk']} θ={cfg['theta']} "
         f"miss_policy={cfg['miss_policy']} permit={cfg.get('permit')}",
         f"- events {cfg['n_events_test']} fired {cfg['n_fired']} "
         f"entered plan {cfg['n_planned']} injectable {cfg['n_inject']}", "",
         "> the **main comparison for saved tokens is the original trajectory**: saved_tok = the original trajectory's out token at that step",
         "> minus this arm's out token (the original trajectory's number is how many the model itself wrote from here to issuing the call at the time",
         "> actually spent, already available on disk).",
         "> **nofill is only a pipeline health-check line**: nofill health-check = nofill's out token minus this arm's,",
         "> used to check whether rebuild and sampling settings have drifted (only nofill ≈ original trajectory greenlights the whole batch of numbers), not counted as a gain.",
         "> repeated_injected = the continuation called the injected tool again (lower means the injection was adopted more),",
         "> but appworld embeds calls inside python, and the result often needs to be assigned to a variable, so calling again does not necessarily mean the injection was ignored.",
         "", "## By arm", "",
         "| arm | n | saved-token mean | saved-token median | save ratio | save positive | out-token mean "
         "| emits code block | recalls injected | advances | nofill health-check median | hits length cap |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, v in out["by_arm"].items():
        L.append(f"| {k} | {v['n']} | {v['saved_tok_mean']} | "
                 f"{v['saved_tok_median']} | {v['saved_ratio_mean']} | "
                 f"{v['saved_positive']} | {v['out_tok_mean']} | "
                 f"{v['has_code']} | {v['repeated_injected']} | "
                 f"{v['advanced']} | {v['nofill_delta_median']} | "
                 f"{v['truncated']} |")
    L += ["", "## Bucketed by fire depth (dead-zone diagnosis)", "",
          "| depth | arm | n | saved-token mean | recalls injected | advances |",
          "|---|---|---|---|---|---|"]
    for b, arms in out["by_depth"].items():
        for k, v in arms.items():
            L.append(f"| {b} | {k} | {v['n']} | {v['saved_tok_mean']} | "
                     f"{v['repeated_injected']} | {v['advanced']} |")
    if "by_name_hit" in out:
        L += ["", "## Skeleton arm (the tool name is pinned by the probe, the large model only writes the args)", "",
              "> skeleton completion = the model **continuing from the skeleton position** to finish writing the call (parentheses balanced, and if a fence"
              "was spliced in, the fence closed too); writing one on a new line on its own does not count as completion.",
              "> tool name rewritten = the model switched to a different tool in the body section, the denominator only counts events that wrote out a body"
              "call (ones with no transition are recorded as None, read together with the emits-code-block column).",
              "> reconsidered after completion = the number of characters between the skeleton completion point and the transition.",
              "> name_hit = the probe's predicted tool name matches the original trajectory; the wrong-guess bucket is the cost this setting pays.",
              "> **call_out (the one sent to real execution) always takes the one completed at the skeleton "
              "position**: for events whose tool name was rewritten, what gets executed is a call the model itself "
              "had already abandoned, so that subset's execution accuracy cannot be read as this setting's score.",
              "",
              "| arm | n | skeleton completion | tool name rewritten | reconsidered after completion (median chars) | "
              "correct-guess n | correct-guess saved-token median | wrong-guess n | wrong-guess saved-token median |",
              "|---|---|---|---|---|---|---|---|---|"]
        for k in out["by_name_hit"]["hit"]:
            v = out["by_arm"][k]
            h = out["by_name_hit"]["hit"][k]
            ms = out["by_name_hit"]["miss"][k]
            L.append(f"| {k} | {v['n']} | {v['skeleton_done']} | "
                     f"{v['tool_rewritten']} | {v['post_think_median']} | "
                     f"{h.get('n', 0)} | {h.get('saved_tok_median')} | "
                     f"{ms.get('n', 0)} | {ms.get('saved_tok_median')} |")
    if is_exec:
        e = out["exec"]
        L.insert(4, "> ⚠️ **execute mode: the accuracy here is the single-step call consistency rate, not "
                    "appworld task-level score.** an event only continues one step, does not run to completion,"
                    "and does not call world.evaluate(). the task-level axis needs a separate in-loop rollout.")
        L += ["", "## Execute mode settings", "",
              f"- exec_scope = {e['exec_scope']}; actually executed "
              f"{e['n_exec_pred'] + e['n_exec_error']} events, of which errored "
              f"{e['n_exec_error']} (error rate {e['exec_error_rate']}),"
              f"no execution record obtained for {e['n_exec_missing']}",
              f"- **acceptance line**: prediction matches ground truth, the code block contains only 1 call, and "
              f"that code block is a clean print(call) -- for these events, execution output matches the result "
              f"recorded in the trajectory {e['acceptance_matched']}/{e['acceptance_n']}"
              f"(of which character-for-character identical {e['acceptance_exact']}, the rest are cases where "
              f"the call itself errored, the error message matched but the traceback's echoed quote style differed). "
              f"another {e['acceptance_excluded_mixed']} hit+single-call events could not be compared because the "
              f"code block was not a clean print, and were not counted into the acceptance line",
              f"- proportion of all actually-executed events whose output is character-for-character identical to "
              f"the recorded result {e['matched_traj_result']} (multi-call blocks are not expected to match anyway, this is for reference only)",
              f"- events where prefix replay drifted {e['n_drift']} (executed against the wrong state, cannot be "
              f"taken at face value in the report)",
              f"- branch counts for quote-patching {e['arg_modes']}",
              f"- kinds of execution errors {e['error_kind']}", "",
              "> the cost of a wrong guess is only booked in this mode: when the predicted call errors, the "
              "error text is injected verbatim, using the same [SYSTEM NOTE: prefetched ...] template (comparable to hit events).",
              "", "### Bucketed by injection source (**must not be mixed into one mean**)", "",
              "| source | arm | n | saved-token mean | saved-token median | save ratio | "
              "out-token mean | emits code block | recalls injected | advances |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for s, arms in out["by_inject_source"].items():
            for k, v in arms.items():
                L.append(f"| {s} | {k} | {v['n']} | {v['saved_tok_mean']} | "
                         f"{v['saved_tok_median']} | {v['saved_ratio_mean']} | "
                         f"{v['out_tok_mean']} | {v['has_code']} | "
                         f"{v['repeated_injected']} | {v['advanced']} |")
    (d / f"INJECT_REPORT{a.tag}.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


# ---------------------------------------------------------------- cli

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("plan")
    p.add_argument("--ctool-run", required=True)
    p.add_argument("--cgen-run", required=True)
    p.add_argument("--data", required=True)
    p.add_argument("--traj-root", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--risk", type=float, default=0.1)
    p.add_argument("--theta", type=float, default=None,
                   help="pin θ directly, overriding --risk's reverse lookup (used for θ sweep curves)")
    p.add_argument("--decision-file", default=None,
                   help="external per-event verdict JSONL: {event, fire, sent_idx}; if given, it "
                        "fully replaces the θ verdict (the interface for threshold-model production), conf is still computed as usual")
    p.add_argument("--miss-policy", default="skip",
                   choices=["skip", "oracle", "execute"])
    p.add_argument("--exec-scope", default="all", choices=["all", "miss"],
                   help="only takes effect when miss_policy=execute. all = actually execute hit events too "
                        "(unifies settings, and fixes the multi-call-block bias along the way);"
                        "miss = only execute the wrong guesses, hit still goes through traj_hit (comparable to the old curve)")
    p.add_argument("--permit", action="store_true", help="add an authorization sentence to system")
    p.add_argument("--device", default="cuda")
    p.add_argument("--bs", type=int, default=8)
    p.add_argument("--max-new-tokens", type=int, default=96)
    p.add_argument("--limit", type=int, default=0)
    p.set_defaults(fn=cmd_plan)

    p = sub.add_parser("merge-exec",
                       help="plan.jsonl + exec_calls.jsonl -> plan_exec.jsonl")
    p.add_argument("--plan", required=True)
    p.add_argument("--exec", required=True,
                   help="exec_calls.py's outputs; pieces are automatically collected as <stem>*<suffix>,"
                        "comma-separated multiple files are also accepted")
    p.set_defaults(fn=cmd_merge_exec)

    p = sub.add_parser("run")
    p.add_argument("--plan", required=True)
    p.add_argument("--base-url", required=True)
    p.add_argument("--model", default="gpt-oss-120b")
    p.add_argument("--tokenizer", default="/net/tokyo100-10g/data/str01_01/"
                                          "y-guo/models/gpt-oss-120b")
    p.add_argument("--arms", default="nofill,inject",
                   help="optional " + ",".join(ARMS_ALL))
    p.add_argument("--form-table", default=str(HERE / "form_table.json"),
                   help="build_form_table.py's output, decides whether the skeleton is print form or"
                        "assignment form; if the file is absent, always use print form")
    p.add_argument("--preset", default="default",
                   help="a set of generation settings from configs/presets/<name>.json"
                        "(temperature/top_p/max_tokens/stop/seed);"
                        "default is default; explicit command-line values override the preset")
    # max_tokens=8192 at collection time (the Chat default in envs/collect/common.py). Set
    # it too low and nofill gets truncated, making it incomparable with baseline -- some
    # single steps have been observed with baseline_out_tok up to 5681
    p.add_argument("--max-tokens", type=int, default=None,
                   help="default 8192 (when the preset gives none either)")
    p.add_argument("--dry-run", action="store_true",
                   help="only splice the prompt and write it to disk, do not send requests (verifies splicing without occupying the service)")
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--tag", default="")
    p.add_argument("--permit", action="store_true")
    p.add_argument("--concurrency", type=int, default=16)
    p.add_argument("--no-pin-date", action="store_true",
                   help="do not pin Current date back to the collection day (pinned by default, to guarantee character-for-character rebuild)")
    p.add_argument("--assume-date", action="store_true",
                   help="accept that the rebuild date differs from the collection date, and keep running")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("score")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--plan-file", default="plan.jsonl",
                   help="execute mode uses plan_exec.jsonl (the config name is derived from it)")
    p.add_argument("--form-table", default=str(HERE / "form_table.json"),
                   help="must be the same table used at run time: the skeleton string is not stored in raw,"
                        "extracting the call has to splice it again from this table")
    p.add_argument("--tag", default="")
    p.add_argument("--rebaseline", action="store_true",
                   help="allow overwriting a report under the old settings (saved_tok relative to nofill) with the new"
                        "settings (relative to the original trajectory). rerunning just one θ point would make "
                        "sweep_theta curve sum the two settings together; adding this switch is a commitment to rerun the entire curve together")
    p.set_defaults(fn=cmd_score)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
