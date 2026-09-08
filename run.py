#!/usr/bin/env python3
"""new1 unified entry point for the whole pipeline: one registry covers all seven stages
(collect / annotate / train / eval / replay injection / exec / live run).

Usage (any python3 can run this file; the underlying scripts each use their own venv):
  python3 run.py list [stage]          # list tasks (grouped by stage)
  python3 run.py show <task>           # print the full command that would run, plus notes, without running it
  python3 run.py <task> [args...]      # run; args pass through as-is to the underlying script
  python3 run.py recipes               # list recipes (named chains that run several steps in one command)
  python3 run.py recipe <name> [--set k=v ...] [--id X] [--resume] [--dry-run]
  python3 run.py status [dir]          # recipe progress (reads the state file + log tail)
  python3 run.py selfcheck             # registry checkup: are interpreters/scripts/recipe references all consistent
  python3 run.py launch <task>|--cmd '<cmd>' --run-id ID --track T --piece host:gpus [...]
                                        # launch in one command: probe cards -> tmux -> verify alive -> the three registrations (ticket 09)
  python3 run.py launch --refire RUN_ID --idx N [--piece host:gpus] [--allow-dirty]
                                        # refire: resend a dead piece from the job ledger with its
                                        # original command, only that piece's four-tuple in the
                                        # ledger changes, no new record is opened (ticket 10)

Three dispatch rules:
- CPU tasks run directly: subprocess, cwd=ROOT, interpreter from the registry (absolute venv path).
- GPU/launch tasks (handoff=True) only assemble the command, they do not launch it: print
  `<interpreter> <script> <args>` as one block (no cd/CUDA_VISIBLE_DEVICES/tee -- that is the
  gpu-run launch template's job, printing them would get quoted a second time); the launch
  itself goes through the gpu-run skill's full lifecycle. What `show` prints is also the launch
  command, so show goes through the same dirty-tree gate for handoff/gate tasks too
  (--allow-dirty lets it through).
- Before a handoff task prints its command, it checks the working tree: dirty (git status
  --porcelain non-empty) gets refused, only an explicit --allow-dirty lets it through -- commit
  before launching an experiment is a hard rule, the history of 79/79 dirty launches proved that
  soft reminders do not work. --dry-run does not block it when present.

Extension rule (on the same line as the memory notes and probe-pipeline skill Phase E):
  Any future extension -- new model / new environment / new cell / new script / new parameter --
  must be wired into this file the moment the code lands: a new script gets a TASKS entry, a new
  multi-step flow gets a RECIPES entry, a new parameter on an underlying script needs no change
  here (it passes through). The single source of truth for the training cell table is this
  file's CELLS, ops/launch_probe.py imports from here -- do not write a second cell table
  anywhere else. Same for the eval cell table: the single source of truth is this file's
  EVAL_CELLS, ops/launch_eval.py imports from here.

Recipe state and logs: under logs/recipe/<name>__<id>/, one file per step, NN_<step>.log, plus
state.json (written atomically via tmp+replace). The resume key is (step name, command
fingerprint); changing a parameter is automatically treated as not done. rc=0 does not count as
done -- a step that declares itself done still has its outputs checked for existence.
"""

import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOGD = ROOT / "logs" / "recipe"

# Interpreter map (the two-environment hard rule: the mbert line is pinned to transformers
# 4.57.6, the cprobe line is >=5.14, neither ever upgrades; appworld/alfworld/tales/bfcl/tau2
# each have their own simulation environment managing one line)
PY = {
    "sys":      "python3",
    "cprobe":   str(ROOT / "cprobe-env/bin/python"),
    "mbert":    str(ROOT / "mbert-env/bin/python"),
    "appworld": str(ROOT / "envs/appworld/venv/bin/python"),
    "alfworld": str(ROOT / "envs/alfworld/venv/bin/python"),
    "tales":    str(ROOT / "envs/tales/venv/bin/python"),
    "tau2":     str(ROOT / "envs/tau2-bench/.venv/bin/python"),
    "toolhop":  str(ROOT / "envs/toolhop-env/bin/python"),
    "stbserver": str(ROOT / "envs/stb-server-env/bin/python"),
    "vllm":     str(ROOT / "envs/vllm-env/bin/python"),
    "bash":     "bash",
}

# The single source of truth for training cells: cell -> (interpreter, training script, the
# fixed args that cell always carries). ops/launch_probe.py imports from here, nowhere else may
# copy this table again.
CELLS = {
    "mtool": (PY["mbert"], str(ROOT / "pipeline/train/train_mbert_tool.py"), []),
    "mext":  (PY["mbert"], str(ROOT / "pipeline/train/train_mbert_extract.py"), []),
    "ctool": (PY["cprobe"], str(ROOT / "pipeline/train/train_causal_tool.py"),
              ["--base", "qwen"]),
    "cgen":  (PY["cprobe"], str(ROOT / "pipeline/train/train_causal_share.py"),
              ["--mode", "cgen"]),
    "cparam": (PY["cprobe"], str(ROOT / "pipeline/train/train_causal_share.py"),
              ["--mode", "cparam"]),
}
# The default smoke order may be a subset of CELLS: the ModernBERT line (mtool/mext) stopped
# running as of 2026-08-21 (the first overall decision in
# plans/archive/2026-08-21-new-probe-training.md); both cells still stay in CELLS and can be
# fired individually, they just are not in the default smoke order. ops/launch_probe.py's smoke
# tier assigns one card per cell from this table; the number of --gpus given must equal the
# length of this tuple.
CELL_ORDER = ("ctool", "cgen", "cparam")

# The single source of truth for eval cells: cell -> (run.py task name, dependency tool cell |
# None). ops/launch_eval.py imports from here and takes the task's interpreter/script/fixed args
# from it -- nowhere else may copy this table again (an isomorphic table always drifts, and that
# drift is silent).
# Dependency semantics: mext consumes the REPLAY_REPORT of the same model's mtool, cgen and
# cparam consume ctool's.
EVAL_CELLS = {
    "mtool": ("eval-tool-mbert", None),
    "ctool": ("eval-tool-causal", None),
    "mext":  ("eval-mcall", "mtool"),
    "cgen":  ("eval-ccall", "ctool"),
    "cparam": ("eval-cparam", "ctool"),
}

# ---------------------------------------------------------------- task registry
# Fields: stage = stage name / desc = one-line description / py = interpreter key /
#         script = script path relative to ROOT / args = fixed leading args / gpu = needs a
#         card or not / handoff = only assemble the command, do not run it (default = gpu) /
#         env = extra environment variables / cwd = override working directory (default ROOT) /
#         notes = known-pitfall notes
# One-off launchers (the thsweep series, launch_vllm_{w0,topup,trio,pair,gptoss,bfcl_gptoss},
# and the per-batch generated launch_servers.py/launch_clients.sh) do not go into the registry,
# per the user's ruling.

TASKS = {
    # ---- collect collection ----
    "collect-aw": dict(
        stage="collect", py="appworld", script="envs/collect/run_appworld.py",
        desc="AppWorld collector (needs vLLM /v1 online)", shardable=True,
        notes=["must pass --base-url --model --outdir; the outdir name must be appworld_<q35|q36|gptoss>,"
               "any other suffix and downstream silently skips the whole dir",
               "--preset <name> selects a generation-settings set from configs/presets/; explicit command-line"
               "args override the preset; when the preset has a server section, --base-url/--model can be omitted",
               "a rerun must pass --resume, otherwise a same-named trajectory gets truncated and overwritten",
               "the script chdirs to envs/appworld itself; a relative --outdir is resolved against ROOT",
               "--api harmony: hand-assembled harmony goes through /v1/completions, raw output and generated "
               "token ids are all recorded (the server-side HarmonyParser is not involved); gpt-oss only,"
               "--start-date pins the Current date in the prompt",
               "do not install openai-harmony in envs/appworld/venv: it pulls in pydantic 2,"
               "which displaces the 1.10.26 that appworld needs (measured 2026-08-06: import breaks immediately)",
               "long-lived client: run at scale inside tmux (via gpu-run); only a small smoke test may run in the foreground"]),
    "collect-alf": dict(
        stage="collect", py="alfworld", script="envs/collect/run_alfworld.py",
        desc="ALFWorld collector (needs vLLM /v1 online)",
        notes=["must pass --base-url --model --outdir; --split val = the official valid_seen",
               "--preset <name> selects a generation-settings set (same as collect-aw)",
               "an externally exported ALFWORLD_DATA overrides --data-root (the script uses setdefault)",
               "a rerun must pass --resume",
               "long-lived client: run at scale inside tmux (via gpu-run); only a small smoke test may run in the foreground"]),
    "collect-tales": dict(
        stage="collect", py="tales", script="envs/collect/run_tales.py",
        desc="TALES/TWX collector (needs vLLM /v1 online)",
        notes=["no --split/--exp/sharding; sharding is done by splitting --seeds; a wrong --game raises KeyError directly",
               "smoke test: giving --seeds a single seed = run only one episode (there's no --n)",
               "--preset <name> selects a generation-settings set (same as collect-aw)",
               "a rerun must pass --resume",
               "long-lived client: run at scale inside tmux (via gpu-run); only a small smoke test may run in the foreground"]),
    "collect-tau2": dict(
        stage="collect", py="tau2", script="envs/collect/run_tau2.py",
        desc="tau2-bench collector (needs two /v1 endpoints: agent + user simulator)",
        notes=["endpoint smoke test passed (2026-08-02, airline 2 tasks, gptoss served both endpoints on the same server;"
               " zero parse failures/missing args); a real run at scale hasn't happened yet -- at scale, agent and user simulator need separate servers and models",
               "--user-base-url/--user-model are given separately; default = same endpoint as the agent",
               "--preset <name> selects a generation-settings set (default is 'default'); the user simulator's endpoint, model, api"
               " are given by the three --user-* flags, and its temperature uses the same preset as the agent side",
               "the server needs --max-model-len around 65536 (the system prompt is ~6k tokens)",
               "--domain only wires up airline/retail; telecom (2285 tasks, solo collection needs"
               " llm_agent_solo) is not in DOMAINS yet -- extending it is integration-phase work"]),
    "toolhop-official": dict(
        stage="collect", py="toolhop", script="envs/toolhop/code/evaluation_closed.py",
        cwd=str(ROOT / "envs/toolhop/code"),
        desc="ToolHop's official closed-source-path evaluator (needs vLLM /v1 online; the body lives on NFS, reached via a symlink)",
        notes=["the server must carry --enable-auto-tool-choice --tool-call-parser openai"
               "(in vLLM 0.26's registry, openai=GptOssToolParser); without these flags, the model tries to call a tool"
               " but tool_calls stays empty every time (measured 2026-08-02)",
               "must pass --base_url (ending in /v1) --output_file; all args use underscore style",
               "smoke test: --input_file ../data/smoke_2.json (relative to code/); output appends and skips ids"
               " that already exist -- delete the output file first before rerunning",
               "the printed Result percentage is hardcoded to divide by 995, meaningless when running a subset -- check Valid Items and per-item"
               " answer_correct instead",
               "--scenario Direct sends tools:null, vLLM may 400; use Mandatory/Free",
               "toolhop-env pins python 3.12; after upgrading to 3.13, every tool call silently turns into an error (PEP 667,"
               " measured); see patches/toolhop_req_closed.diff for all changes against upstream"]),
    "collect-bfcl": dict(
        stage="collect", prog=str(ROOT / "envs/bfcl/venv/bin/bfcl"),
        cwd=str(ROOT / "envs/bfcl"),
        env={"BFCL_PROJECT_ROOT": str(ROOT / "envs/bfcl")},
        desc="BFCL collection (console script, cwd=envs/bfcl)",
        notes=["See envs/collect/bfcl_gptoss/RUNBOOK.md for the full flow: first install_patch.py,"
               "then printf the task list json, then bfcl generate",
               "also needs the two env vars LOCAL_SERVER_ENDPOINT/LOCAL_SERVER_PORT to point at the service"]),
    "gen-launch": dict(
        stage="collect", py="sys", script="pipeline/collect/gen_launch.py",
        desc="service + client launcher that generates a collection batch from the manifest",
        notes=["--config is required; what it generates still needs to occupy a card to run (that step goes through gpu-run)",
               "ENV_TABLE only has appworld/alfworld; extend it first when adding an environment"]),
    "gen-alf-splits": dict(
        stage="collect", py="sys", script="pipeline/collect/gen_alfworld_splits.py",
        desc="draw the three task-list piles from the official ALFWorld directory",
        notes=["no overwrite-guard gate; rerunning directly rewrites the committed txt"]),
    "gen-bfcl-splits": dict(
        stage="collect", py="sys", script="pipeline/collect/gen_bfcl_splits.py",
        desc="split the 200 BFCL multi_turn_base tasks into three piles (four gates)",
        notes=["refuses to overwrite when the committed task list differs; needs --force"]),
    "gen-tau2-splits": dict(
        stage="collect", py="sys", script="pipeline/collect/gen_tau2_splits.py",
        desc="three piles for the tau2 three-domain task list: the official test is frozen, val is self-split from the official train (four gates)",
        notes=["the official data has only train/test, no val; val = half of each domain's test, with a seed independent per domain",
               "refuses to overwrite when the committed task list differs; needs --force"]),
    "gen-toolhop-splits": dict(
        stage="collect", py="sys", script="pipeline/collect/gen_toolhop_splits.py",
        desc="split all 995 ToolHop tasks into three piles of 695/200/100, stratified by answer_type (four gates)",
        notes=["no official split; the committed txt is the sole source of truth; unit = the official integer id string",
               "refuses to overwrite when the committed task list differs; needs --force"]),
    "build-dataset-legacy": dict(
        stage="collect", py="cprobe", script="envs/collect/build_dataset.py",
        desc="old-line dataset construction (superseded by ann-build, kept for the record)",
        notes=["recognizes only appworld/tales/bfcl; an unrecognized directory suffix is skipped silently"]),
    "summarize-full": dict(
        stage="collect", py="sys", script="envs/collect/summarize_full.py",
        desc="summarize scores across the full set of collection batches (batches/models are hardcoded)",
        notes=["changing batches requires editing the source; a missing directory silently drops a row"]),

    # ---- annotate annotation ----
    "ann-build": dict(
        stage="annotate", py="sys", script="pipeline/annotate/build.py",
        desc="trajectories -> three-pile dataset (--config is required)",
        notes=["a collection directory whose suffix is not in q35/q36/gptoss is skipped entirely and silently"]),
    "ann-params": dict(
        stage="annotate", py="sys", script="pipeline/annotate/param_label.py",
        desc="parameter-extraction annotation (--config is required; must run after ann-build)",
        notes=["raises FileNotFoundError if any of the three-pile jsonl files is missing"]),
    "ann-accept-v3diff": dict(
        stage="annotate", py="sys", script="pipeline/annotate/accept_v3diff.py",
        desc="v3 dataset rebuild consistency acceptance check (no arguments, paths are hardcoded)",
        notes=["the exit code has special meaning: 0 if everything matches, 1 if anything doesn't"]),
    "ann-check-callstr": dict(
        stage="annotate", py="cprobe", script="pipeline/annotate/check_callstr.py",
        env={"CUDA_VISIBLE_DEVICES": ""},
        desc="ground-truth call-string read-back gates G19-G22 (--config is required)",
        notes=["the docs saying python3 are wrong: it imports eval_causal_call -> torch, so it must use cprobe-env",
               "the entry point clears CUDA_VISIBLE_DEVICES on its behalf (the script's setdefault can't block an external export)"]),
    "readonly-gen-tables": dict(
        stage="annotate", py="sys", script="pipeline/annotate/readonly/gen_tables.py",
        desc="generator for the read-only / non-read-only tool ground-truth table",
        notes=["no __main__ guard; importing it executes it; the output is readonly/{appworld,bfcl}.json"]),

    # ---- train training (all cells full GPU, launch goes through gpu-run; the card-scheduling launcher is launch-probe) ----
    "train-mtool": dict(
        stage="train", py="mbert", script="pipeline/train/train_mbert_tool.py",
        gpu=True, desc="ModernBERT tool-name probe (--data --out are required)",
        notes=["--smoke must come with a different --out too, otherwise the smoke-test weights occupy best/",
               "train_log.jsonl is appended to, never cleared",
               "training again in the same --out is refused by default (blocked as soon as train_log.jsonl exists); --force escapes it"]),
    "train-mext": dict(
        stage="train", py="mbert", script="pipeline/train/train_mbert_extract.py",
        gpu=True, desc="ModernBERT parameter-extraction head (--data --out are required)",
        notes=["the output is a bare state_dict at best/model.pt; reuse it through load_extractor()",
               "training again in the same --out is refused by default; --force escapes it"]),
    "train-ctool": dict(
        stage="train", py="cprobe", script="pipeline/train/train_causal_tool.py",
        gpu=True, args=["--base", "qwen"],
        desc="causal tool-name probe (--data --out are required; --base defaults to qwen, three tiers available)",
        notes=["--base has three tiers: qwen=Qwen3-0.6B-Base / qwen17=1.7B / qwen4=4B;"
               "the registry always passes --base qwen; override it again via the card-scheduling table's extra at launch time",
               "the pre-training alignment gate exits 2 on FAIL (reldiff at the 1e-6 scale = noise, above 1e-3 = a real error)",
               "since 2026-08-28, --align-rule {abs,rel,both} defaults to abs; rel checks that "
               "reldiff_hidden/reldiff_logits are both <= --align-rel-tol (default 1e-5)",
               "--lora trains only the base adapter (the classification head still trains in full), and before saving best "
               "it runs merge_and_unload back into the base -- best/ is item-for-item isomorphic with a full-parameter save,"
               "so eval-tool-causal loads it back with zero changes;"
               "--lora-rank 16 / --lora-alpha 32 / --lora-dropout 0.05 / "
               "--lora-lr 2e-4 (an explicit --lr takes precedence)",
               "--grad-ckpt saves GPU memory; works with both full-parameter and --lora training (needed on a 48G card for the 4B model)",
               "training again in the same --out is refused by default; --force escapes it"]),
    "train-cgen": dict(
        stage="train", py="cprobe", script="pipeline/train/train_causal_share.py",
        gpu=True, args=["--mode", "cgen"],
        desc="causal head that generates the full call, with cache-reuse packed forward passes (--data --out are required)",
        notes=["kvshare-train swaps in a new implementation (.scratch/kvshare-train/spec.md): one event's"
               "full text goes through the forward pass once, so rows no longer each repeat tokenization/forward passes; the cell name, data,"
               "and the four eval scripts stay unchanged",
               "--base has three tiers, qwen/qwen17/qwen4, defaulting to qwen (=0.6B, consistent with the old settings);"
               "it also accepts a model directory path, going through build(path=...)",
               "--max-len defaults to 8192 (the token cap for an event's full text; an event over the cap is dropped whole,"
               "not truncated row by row); --tok-budget defaults to 16384 to control physical-block GPU memory",
               "the update unit = --events-per-mb (default 4) x --accum (default 2) = 8 events"
               "per opt.step(), no longer --bs rows per step",
               "a built-in pre-training alignment check (--align-only runs only this): under fp32, it compares row-by-row loss"
               "against the old row-by-row trainer train_causal_callgen.py; on failure it calls sys.exit(2)",
               "since 2026-08-28, --gen-eval N (default 200, 0 disables it) paired with --gen-eval-at "
               "{all,last} (default last) runs an extra generative eval at evaluation time; it only goes into the log and never picks best",
               "since 2026-08-28, --align-rule {abs,rel,both} defaults to abs; rel/both check "
               "rel_max_abs_diff <= --align-rel-tol (default 1e-5); the four coarse-screen thresholds"
               "(--align-tok-tol and the others) have also all become parameters, with defaults equal to the first round's constants",
               "since 2026-08-28, --mem-probe-pick {tokens,cost,loop} defaults to cost,"
               "used together with --mem-probe; at wrap-up it writes one mem_probe_summary entry (worst_gb and others)",
               "--lora trains only the base adapter, and before saving best "
               "it runs merge_and_unload back into the base -- best/ is item-for-item isomorphic with a full-parameter save,"
               "so eval-ccall loads it back with zero changes;"
               "--lora-rank 16 / --lora-alpha 32 / --lora-dropout 0.05 / "
               "--lora-lr 2e-4 (an explicit --lr takes precedence)",
               "--grad-ckpt saves GPU memory; works with both full-parameter and --lora training (needed on a 48G card for the 4B model)",
               "training again in the same --out is refused by default; --force escapes it"]),
    "train-cparam": dict(
        stage="train", py="cprobe", script="pipeline/train/train_causal_share.py",
        gpu=True, args=["--mode", "cparam"],
        desc="causal parameter-generation head, with cache-reuse packed forward passes (given the tool name, writes only the parameters; --data --out are required)",
        notes=["input string = text + \\n[CALL] + tool name + open paren, target = the part inside the parens + close paren",
               "kvshare-train swaps in a new implementation, sharing the same script and the same packed"
               "forward pass as train-cgen; only --mode differs (see the train-cgen entry for the spec)",
               "--base has three tiers, qwen/qwen17/qwen4, defaulting to qwen; also accepts a model directory path",
               "no --fire-head: the trigger is always done by ctool",
               "since 2026-08-28, --gen-eval N (default 200, 0 disables it) paired with --gen-eval-at "
               "{all,last} (default last) runs an extra generative eval at evaluation time; it only goes into the log and never picks best",
               "since 2026-08-28, --align-rule {abs,rel,both} defaults to abs; rel/both check "
               "rel_max_abs_diff <= --align-rel-tol (default 1e-5); the four coarse-screen thresholds"
               "(--align-tok-tol and the others) have also all become parameters, with defaults equal to the first round's constants",
               "since 2026-08-28, --mem-probe-pick {tokens,cost,loop} defaults to cost,"
               "used together with --mem-probe; at wrap-up it writes one mem_probe_summary entry (worst_gb and others)",
               "--lora trains only the base adapter; before saving best it runs merge_and_unload back into the base"
               "-- best/ is item-for-item isomorphic with a full-parameter save, eval-cparam loads it back with zero changes;"
               "--lora-rank 16 / --lora-alpha 32 / --lora-dropout 0.05 / "
               "--lora-lr 2e-4 (an explicit --lr takes precedence)",
               "--grad-ckpt saves GPU memory; works with both full-parameter and --lora training (needed on a 48G card for the 4B model)",
               "training again in the same --out is refused by default; --force escapes it"]),
    "train-cgen-rows": dict(
        stage="train", py="cprobe", script="pipeline/train/train_causal_callgen.py",
        gpu=True, desc="causal head that generates the full call, old row-by-row trainer (for reference/comparison)",
        notes=["the row-by-row reference implementation, used only for alignment checks and comparison; its output does not enter the matrix, and the run_id "
               "must not use an active batch prefix (kvshare-train decision 3 freezes it as the alignment reference)",
               "--base has three tiers, qwen/qwen17/qwen4, defaulting to qwen (=0.6B, consistent with the old settings)",
               "--lora trains only the base adapter (the fire head still trains in full), and before saving best "
               "it runs merge_and_unload back into the base -- best/ is item-for-item isomorphic with a full-parameter save,"
               "so eval-ccall loads it back with zero changes;"
               "--lora-rank 16 / --lora-alpha 32 / --lora-dropout 0.05 / "
               "--lora-lr 2e-4 (an explicit --lr takes precedence)",
               "--grad-ckpt saves GPU memory; works with both full-parameter and --lora training (needed on a 48G card for the 4B model)",
               "training again in the same --out is refused by default; --force escapes it"]),
    "train-cparam-rows": dict(
        stage="train", py="cprobe", script="pipeline/train/train_causal_param.py",
        gpu=True, desc="causal parameter-generation head, old row-by-row trainer (for reference/comparison)",
        notes=["the row-by-row reference implementation, used only for alignment checks and comparison; its output does not enter the matrix, and the run_id "
               "must not use an active batch prefix (kvshare-train decision 3 freezes it as the alignment reference)",
               "input string = text + \\n[CALL] + tool name + open paren, target = the part inside the parens + close paren",
               "--base has three tiers, qwen/qwen17/qwen4, defaulting to qwen",
               "no --fire-head: the trigger is always done by ctool",
               "--lora trains only the base adapter; before saving best it runs merge_and_unload back into the base"
               "-- best/ is item-for-item isomorphic with a full-parameter save, eval-cparam loads it back with zero changes;"
               "--lora-rank 16 / --lora-alpha 32 / --lora-dropout 0.05 / "
               "--lora-lr 2e-4 (an explicit --lr takes precedence)",
               "--grad-ckpt saves GPU memory; works with both full-parameter and --lora training (needed on a 48G card for the 4B model)",
               "training again in the same --out is refused by default; --force escapes it"]),
    "sweep-lr": dict(
        stage="train", py="cprobe", script="pipeline/train/sweep_lr.py",
        desc="lr-sweep list (plan) and collected report (report); launch still goes through gpu-run",
        notes=["two subcommands: `sweep-lr plan [--grid ...] [--write plan.json]`"
               "generates 12 train-cgen commands and launch lines from the `GRID` constant;"
               "`sweep-lr report --runs <path/glob...> --out <dir>` collects the train_log.jsonl"
               "from a batch of run directories into SWEEP_REPORT.json/.md",
               "the `GRID` constant sits at the top of pipeline/train/sweep_lr.py; the four base configs"
               "(b06/b17/l17/l4) each have three lr anchor points, which may change again after the smoke test",
               "this task only produces the list/collects the report (pure CPU); it does not launch; the actual launch of the 12 runs"
               "goes through gpu-run, and the output dir pipeline/runs/sweep/ does not enter the matrix"]),
    "demo-prep": dict(
        stage="train", py="cprobe", script="demo/prepare.py",
        env={"CUDA_VISIBLE_DEVICES": ""},
        desc="debugger demo fixtures: synthetic small data demo/data + a small two-layer Qwen3 "
             "demo/tiny_qwen3 (pure CPU, ten seconds)",
        notes=["the tokenizer is copied from the real Qwen3-0.6B-Base; demo/tiny_qwen3 and demo/runs are turned by this"
               "task into symlinks pointing at a mirrored dir on the net drive (hard rule: big outputs go to net, same as pipeline/runs)",
               "the data is determined by the seed; demo/data/*.jsonl goes into the repo, the two symlinks do not",
               "see demo/README.md for where to set breakpoints; enter the debugger via .vscode/launch.json,"
               "neither of the two training configs nor demo-train touches a GPU"]),
    "demo-train": dict(
        stage="train", py="cprobe", script="pipeline/train/train_causal_share.py",
        env={"CUDA_VISIBLE_DEVICES": ""},
        args=["--base", "demo/tiny_qwen3", "--data", "demo/data",
              "--device", "cpu", "--epochs", "2", "--eval-per-epoch", "2",
              "--log-every", "1", "--tok-budget", "768", "--gen-eval", "4",
              "--gen-bs", "2", "--align-events", "3"],
        desc="run the demo training end to end on CPU when not stepping through the debugger"
             "(--mode cgen|cparam and --out are required)",
        notes=["the same set of arguments as .vscode/launch.json; running the same --out a second time needs --force",
               "what actually runs is the real trainer train_causal_share.py, just with the model and data swapped for fixtures",
               "the output demo/runs/<mode>/ does not enter the repo, the matrix, or the record (it is not an experiment)"]),

    # ---- eval evaluation ----
    "eval-tool-mbert": dict(
        stage="eval", py="mbert", script="pipeline/eval/eval_tool.py",
        gpu=True, args=["--head", "mbert"],
        desc="tool-name eval, mbert head (--env --run --data are required)",
        notes=["logits are always written to --run, the report follows --report-dir; this is a prerequisite for the two call evals",
               "smoke test: --limit N truncates each pile to the first N rows; only allowed on a --run whose name includes smoke"
               "(the truncated logits/REPLAY_REPORT get written into --run; a real run must not touch this)",
               "the mbert head supports only --overlong left; passing skip/drop-event raises SystemExit directly"
               "(since 2026-08-28; --overlong only takes effect for --head causal)"]),
    "eval-tool-causal": dict(
        stage="eval", py="cprobe", script="pipeline/eval/eval_tool.py",
        gpu=True, args=["--head", "causal"],
        desc="tool-name eval, causal head (same as above, different interpreter)",
        notes=["one script forks into two interpreters by --head; the registry splits it into two tasks",
               "smoke test: --limit N (same as eval-tool-mbert, only allowed for a smoke directory)",
               "since 2026-08-28, --overlong {left,skip,drop-event} defaults to left,"
               "in all three modes logits_*.pt is written with the full row count, and excluded rows' indices go into .meta.json's "
               "excluded_idx; --cached-logits hits a hard stop if it meets a different overlong_mode"]),
    "eval-mcall": dict(
        stage="eval", py="mbert", script="pipeline/eval/eval_mbert_call.py",
        gpu=True, desc="eval of the full mbert call (--env --run --data --extractor are required)",
        notes=["must wait for the same model's eval-tool-mbert to finish (needs REPLAY_REPORT+logits)",
               "a null θ is a hard failure that exits 1: the standard remedy is to lower --risk to 0.1 and rerun; only N/A when both tiers are null"]),
    "eval-ccall": dict(
        stage="eval", py="cprobe", script="pipeline/eval/eval_causal_call.py",
        gpu=True, desc="eval of the full causal call (--env --ctool-run --cgen-run --data are required)",
        notes=["must wait for eval-tool-causal to finish; passing the wrong --env silently corrupts the numbers",
               "since 2026-08-28, --overlong {left,skip,drop-event} defaults to left,"
               "the set of rows entering the denominator differs across the three modes; the matrix accepts only the left eval results"]),
    "eval-cparam": dict(
        stage="eval", py="cprobe", script="pipeline/eval/eval_causal_param.py",
        gpu=True,
        desc="causal parameter-generation eval (--env --ctool-run --cparam-run --data are required)",
        notes=["must wait for eval-tool-causal to finish; passing the wrong --env silently corrupts the numbers",
               "the report PARAM_REPORT.{json,md} is written into --cparam-run, in two blocks:"
               "gt_tool (fed the ground-truth tool name) and pred_tool (fed the classification head's argmax)",
               "the matrix takes only the pred_tool block -- that is system B's real settings",
               "since 2026-08-28, --overlong {left,skip,drop-event} defaults to left,"
               "the set of rows entering the denominator differs across the three modes; the matrix accepts only the left eval results"]),
    "matrix": dict(
        stage="eval", py="sys", script="pipeline/eval/summarize_matrix.py",
        desc="matrix rollup (--runs-dir --out are required)",
        notes=["--risk is a string key; it only recognizes \"0.05\" or \"0.1\", passing 0.10 turns the whole row into - but the status is still OK",
               "--models is nargs=+; a bare argument gets swallowed by it"]),

    # ---- inject replay injection + exec execution ----
    "inject-plan": dict(
        stage="inject", py="cprobe", script="pipeline/inject/replay_inject.py",
        gpu=True, args=["plan"],
        desc="fire plan: run the probe+cgen over the full set of events (--ctool-run --cgen-run --data --traj-root --out are required)",
        notes=["--theta overrides --risk, and --decision-file overrides θ in turn"]),
    "inject-run": dict(
        stage="inject", py="cprobe", script="pipeline/inject/replay_inject.py",
        handoff=True, args=["run"],
        desc="send continuation requests per the plan (needs vLLM; long-lived, run it in tmux)",
        notes=["--base-url must end in /v1; the output is written into the same directory as --plan",
               "--preset <name> selects a set of generation settings (temperature/max_tokens/stop)",
               "--tag is just the raw file suffix; splitting by piece relies on an external split by arm (see splice_client.py)",
               "a single failed request only gets counted; the process still exits 0 overall -- completion is judged by the raw row count, not by rc"]),
    "inject-merge-exec": dict(
        stage="inject", py="cprobe", script="pipeline/inject/replay_inject.py",
        args=["merge-exec"], desc="execute mode: execute the results and write them back to the plan (--plan --exec are required)"),
    "inject-score": dict(
        stage="inject", py="cprobe", script="pipeline/inject/replay_inject.py",
        args=["score"], desc="score and produce INJECT_REPORT (--run-dir is required)",
        notes=["piece-sharded raw files must first be cat-merged into a single raw<tag>.jsonl",
               "changing saved_baseline's settings needs --rebaseline, and the whole θ curve must be rerun"]),
    "extract-completed": dict(
        stage="inject", py="cprobe", script="pipeline/inject/extract_completed.py",
        desc="sample completed calls per arm -> exec_in_<arm>.jsonl (--run-dir --arms are required)",
        notes=["the skeleton always uses pred_label; label is forbidden (the god's-eye-view red line)"]),
    "exec-calls": dict(
        stage="inject", py="appworld", script="pipeline/inject/exec_calls.py",
        desc="execute the call in the live world (--plan --out --cache --exp are required)",
        notes=["concurrency only works via multiple processes each with its own --exp; when sharded by piece, out/cache automatically get a .sN suffix",
               "a single unit blowing up only gets logged into unit_errors and continues; rc is still 0 -- check meta.json, not rc"]),
    "acceptance": dict(
        stage="inject", py="cprobe", script="pipeline/inject/acceptance.py",
        desc="compute-cost accounting for A (tool-name acceptance rate) / C (draft acceptance length) (--run-dir is required)",
        notes=["only with --base-url does it run the exact echo path; it must end in /v1,"
               "and the service must be a dedicated replica at util 0.80 + --max-num-batched-tokens 2048"]),
    "sweep-run": dict(
        stage="inject", py="cprobe", script="pipeline/inject/sweep_theta.py",
        handoff=True, args=["run"],
        desc="θ-sweep orchestration: run+score directory by directory (--runs --services are required; long-lived)",
        notes=["the subprocess interpreter is hardcoded to cprobe-env; the registry has no control over the replay_inject it spawns",
               "a leftover .run_lock needs manual confirmation before deleting"]),
    "sweep-curve": dict(
        stage="inject", py="cprobe", script="pipeline/inject/sweep_theta.py",
        args=["curve"], desc="roll up the θ curve (--runs is required)",
        notes=["rerunning just a single point's score leaves the curve with two different settings -- check_saved_baseline exists to block exactly this"]),
    "build-form-table": dict(
        stage="inject", py="cprobe", script="pipeline/inject/build_form_table.py",
        desc="skeleton shape table (runs with default arguments)",
        notes=["hard-blocks the w0 test set; rebuilding and swapping the table would make a finished skel arm's score not match"]),
    "check-bundle-mbert": dict(
        stage="inject", py="mbert", script="pipeline/inject/check_bundle.py",
        args=["--head", "mbert", "--device", "cpu"],
        desc="mbert weights cross-process load check (requires --run --data; CPU)"),
    "check-bundle-causal": dict(
        stage="inject", py="cprobe", script="pipeline/inject/check_bundle.py",
        gpu=True, args=["--head", "causal"],
        desc="causal weights load check (requires --run --data; default cuda)"),
    "parse-call-selftest": dict(
        stage="inject", py="cprobe", script="pipeline/inject/parse_call.py",
        desc="bracket-balance extractor self-test (no arguments; also run.py's smoke test)"),
    # ---- splice splice-style replay (god's-eye view, no probe; plan plans/archive/2026-08-18-splice-replay.md) ----
    "splice-replay-events": dict(
        stage="inject", py="cprobe", script="pipeline/inject/splice_replay.py",
        args=["events"],
        desc="extract events + four cuts from chat trajectories -> events.jsonl (requires --traj-root --out; CPU)",
        notes=["take single-call blocks only, dedupe repeated steps within the same task (D1/D2); mark cases capped to 8192 for baseline as baseline_capped"]),
    "splice-replay-run": dict(
        stage="inject", py="cprobe", script="pipeline/inject/splice_replay.py",
        handoff=True, args=["run"],
        desc="event x cut x arm sends completions continuations (requires vLLM; requires --run-dir --base-url; long-running)",
        notes=["prompt is token ids (prefix rendered the same way as chat; p3k/p4 rendered by openai_harmony)",
               "--preset <name> selects a set of generation settings (default: default),"
               "the continuation's temperature is read from its client section",
               "--dry-run prints only the prompt tail, writes nothing; resuming skips by (event, cut, arm)",
               "p4 has one extra stop token <|call|> (D11)"]),
    "splice-replay-score": dict(
        stage="inject", py="cprobe", script="pipeline/inject/splice_replay.py",
        args=["score"], desc="score into SPLICE_REPORT (requires --run-dir; CPU)"),
    "launch-plan-sweep": dict(
        stage="inject", py="sys", script="pipeline/inject/launch_plan_sweep.py",
        handoff=True, gpu=True,
        desc="θ-sweep plan-segment launcher (ssh+tmux to tokyo106 itself)",
        notes=["refiring a single point requires --only (SKIP blocks only sessions still alive)",
               "shell inside a shell: it ssh+tmux's 6 sessions itself -- different category from launch-probe/"
               "launch-eval (gate-type real execution); this is historical, use it per the handoff"]),

    # ---- live live run + serve service ----
    "live-appworld": dict(
        stage="live", py="appworld", script="pipeline/inject/live_appworld.py",
        handoff=True,
        desc="live-run driver (requires vLLM + probe service; requires --base-url --probe-url --outdir --exp)",
        notes=["the no-probe arm (--no-probe) also needs --probe-url (/render lives on the service side)",
               "--preset <name> selects a set of generation settings (effort/temperature/step budget/stop),"
               "explicit command-line arguments override the preset",
               "a transient failure writes task_error final; --resume does not retry: to retry, delete that task's live_*.jsonl first",
               "scale up via live-arm-job's 12 pieces"]),
    "probe-serve": dict(
        stage="live", py="cprobe", script="pipeline/inject/probe_server.py",
        gpu=True, args=["serve"],
        desc="probe long-running service (ctool+cgen, ~3GB; default port 8790; --theta required)",
        notes=["serve_forever never returns; temperature is read from <ctool-run>/REPLAY_REPORT.json",
               "--theta has no default; refuses to run without it (METHOD.md axis 4: θ is always manual)"]),
    "probe-selftest": dict(
        stage="live", py="cprobe", script="pipeline/inject/probe_server.py",
        args=["selftest", "--device", "cpu"],
        desc="probe-trigger consistency self-check (pure CPU; --theta required)",
        notes=["--theta has no default; to cross-check the replay run at θ=0.925, pass 0.925 for its logits"]),
    "score-live": dict(
        stage="live", py="cprobe", script="pipeline/inject/score_live.py",
        desc="score a live run -> LIVE_REPORT (requires --live-dir --base-root)",
        notes=["must wait for live_appworld to finish; task_error is listed separately and excluded from the success/failure denominator"]),
    "live-arm-job": dict(
        stage="live", py="bash", script="envs/serve_logs/live_arm_job.sh",
        handoff=True,
        desc="one live-run arm, 12 pieces (positional args probe|noprobe run_name; runs the whole thing inside tmux)",
        notes=["ports 8114-8116 and probe tokyo105:8790 are hardcoded; edit the file to change machines",
               "run_name is required (e.g. live_aw_gptoss_v2) = the output dir under runs/,"
               "a fail-safe: forgetting it once ran silently against the empty v1 dir and falsely reported DONE"]),
    # ---- ident3 three arms identical token by token (plan plans/archive/2026-08-18-ident3.md) ----
    "ident3-job": dict(
        stage="live", py="bash", script="envs/serve_logs/ident3_job.sh",
        handoff=True,
        desc="ident3, one arm, 10 repeats in series (positional args chat|noprobe|nofill <root> "
             "[reps n_tasks vllm_port probe_url]; runs the whole thing inside tmux)",
        notes=["start one copy of each of the three arms in parallel; requires vLLM (tokyo108:8114) + render-only probe_server"
               "(--render-only --device cpu, with /decode) online",
               "the fake-trigger cut index is set by the environment variable IDENT3_FIRE_NTH, default 5 (plan E1)",
               "the chat arm's outdir name ends with appworld_gptoss (collector convention)"]),
    "ident3-gate": dict(
        stage="live", py="sys", script="pipeline/inject/ident3_gate.py",
        desc="ident3 pre-launch gate: chat prompt_token_ids == /render prefix_ids"
             "(requires --base-url --probe-url; CPU)",
        notes=["ident3_job.sh calls it automatically before running; a failure means vLLM did not pin VLLM_SYSTEM_START_DATE"
               " or return_token_ids did not take effect",
               "--preset <name> defaults to default; the gate request's temperature is read from its "
               "client section"]),
    "ident3-score": dict(
        stage="live", py="sys", script="pipeline/inject/ident3_score.py",
        desc="ident3 scoring -> IDENT3_REPORT (requires --root; CPU, stdlib)",
        notes=["three arms x 5 tasks x 10 repeats, pairwise token-by-token comparison; same-arm pairs vs cross-arm pairs reported separately"]),
    "serve-splice": dict(
        stage="live", py="sys", script="envs/serve_logs/launch_vllm_splice.py",
        handoff=True, gpu=True,
        desc="gpt-oss three-replica vLLM launcher (tokyo108:8114-8116; ssh+tmux itself, idempotent)",
        notes=["environment variables (cuda-compat/FLASHINFER/cache into /net) are already embedded in the script",
               "VLLM_SYSTEM_START_DATE is pinned to 2026-07-31 (=COLLECT_DATE, METHOD §6-④)"]),
    "serve-awdiag": dict(
        stage="live", py="sys", script="envs/serve_logs/launch_vllm_awdiag.py",
        handoff=True, gpu=True,
        desc="gpt-oss three replicas for the w0 reproduction diagnosis (tokyo108:8103/8106/8107; ssh+tmux itself, idempotent)",
        notes=["**do not pass --max-model-len**: native 131072, replicating the config used at w0 collection time;"
               "65536 means it was launched wrong -- one suspect in the diagnosis chain is exactly the 65k context",
               "companion client awdiag_job.sh (PORTS hardcoded to 8103/8106/8107)"]),
    "serve-preset": dict(
        stage="live", py="sys", script="serve_preset.py",
        handoff=True, gpu=True,
        desc="generic vLLM launcher: reads the server section of configs/presets/<name>.json"
             "(requires --preset --gpu; --host/--port/--session can override)",
        notes=["the model path goes through model_registry.resolve(); it does not accept hardcoding",
               "at launch, copies the preset to envs/serve_logs/<session>.preset.json",
               "only presets with a server section can be launched: default and gptoss_default, two of them",
               "--dry-run only prints the ssh+tmux command; the old launch_vllm_*.py scripts are left untouched,"
               "new services start from here"]),
    "serve-mirrorapi": dict(
        stage="live", prog=str(ROOT / "envs/vllm-env/bin/vllm"),
        handoff=True, gpu=True,
        args=["serve",
              "/net/tokyo100-10g/data/str01_01/y-guo/models/MirrorAPI-Cache",
              "--served-model-name", "mirrorapi-cache"],
        desc="StableToolBench simulator MirrorAPI-Cache (Qwen2.5-7B fine-tuned, bf16 ~15G)",
        notes=["typical extra args: --port 8125 --gpu-memory-utilization 0.5",
               "tokyo108 needs LD_LIBRARY_PATH=envs/cuda-compat-13.0 (following"
               " the same setup as envs/serve_logs/run_gptoss.sh); on 106/107 with CUDA 12.2, do a 10-second live check first",
               "served-model-name must = mirrorapi-cache; the server config hardcodes the same name"]),
    "stb-virtual-server": dict(
        stage="live", py="stbserver",
        script="envs/stabletoolbench/server/main_mirrorapi_cache.py",
        cwd=str(ROOT / "envs/stabletoolbench/server"),
        handoff=True,
        desc="StableToolBench virtual API service (CPU, reads config_mirrorapi_cache.yml from cwd)",
        notes=["smoke-tested (2026-08-02, simulator started on a single H200 card): a fake Finance/Currency/Convert call"
               "returns structured exchange-rate JSON, error is empty, the whole offline chain works",
               "start serve-mirrorapi first, then point api_base in the config to it; FastAPI listens on 8126",
               "smoke-test criterion: POST /virtual (category/tool_name/api_name/tool_input/"
               "strip/toolbench_key, six fields) returns 200 and a non-empty response; key is not checked",
               "long-running service, run it inside tmux; the tool-doc tree is toolenv2404_filtered/ cloned on NFS"]),
    "splice-plan-job": dict(
        stage="live", py="bash", script="envs/serve_logs/splice_plan_job.sh",
        handoff=True, gpu=True,
        desc="eight-arm plan rerun job (positional arg gpu_idx; smoke-test gate + hard field check)",
        notes=["does not touch PLAN_OK -- the go-ahead marker is set by hand"]),
    "launch-splice-clients": dict(
        stage="live", py="sys", script="envs/serve_logs/launch_splice_clients.py",
        handoff=True,
        desc="eight-arm three-client launcher (each client waits for PLAN_OK + service health itself)"),
    "accept-vllm-qwen": dict(
        stage="live", py="sys", script="envs/serve_logs/accept_test.py",
        desc="Qwen dual-service acceptance gate (8101/8102; reasoning+content non-empty)"),
    "accept-vllm-tools": dict(
        stage="live", py="sys", script="envs/serve_logs/accept_tools_test.py",
        desc="tools-request acceptance gate (a request with tool_choice must not 400)"),
    "accept-vllm-gptoss": dict(
        stage="live", py="sys", script="envs/serve_logs/gptoss_accept_test.py",
        desc="gpt-oss service acceptance check (8103)",
        notes=["prints only, never exits non-zero -- judging success by rc would always pass; check the output"]),

    # ---- ops job ledger / record / launch ----
    "gpu-jobs": dict(
        stage="ops", py="sys", script="ops/gpu_jobs.py",
        desc="GPU job ledger (register/finish/watch/free/status passed through as-is)",
        notes=["register silently ignores a misspelled flag; free will exec bash to replace the process"]),
    "pipeline": dict(
        stage="ops", py="sys", script="pipeline/driver.py",
        desc="pipeline driver (resumable; requires --config, advances at most one step per invocation)",
        notes=["usage: python3 run.py pipeline --config pipeline/configs/np821_gptoss.json;"
               "--status only reads and prints status, does not advance",
               "it is an orchestrator, not a launcher: launch-type actions are handed off to launch-probe/launch-eval"
               "(which carry their own dirty-tree gate) or the batch's own launch_servers.py/launch_clients.sh,"
               "before acting the driver runs git_dirty() again itself; a dirty tree is blocked on the spot",
               "exit codes: 0 advanced one step / done / still running, 3 launched a GPU job this time, "
               "4 awaiting_decision (write the ruling into the batch config and invoke again), 1 gate failed",
               "status and per-step logs live in logs/pipeline/<run_family>/ (logs/ does not go into git,"
               "status changes do not dirty the working tree)",
               "if the status file is corrupt or the batch identity does not match, refuse to overwrite; delete by hand after a manual look"]),
    "sampler": dict(
        stage="ops", py="sys", script="ops/sampler.py",
        desc="long-running-job sampler (resident; samples heartbeat/probes liveness/computes verdict every 60s, serves a web page)",
        notes=["a resident process, run inside tmux on the login machine: tmux new-session -d -s new1_sampler "
               "'python3 run.py sampler'",
               "written to NFS under monitor/ (latest.json/state.json/history/incidents), not checked into git",
               "smoke test: python3 run.py sampler --once samples one round and exits"]),
    "record": dict(
        stage="ops", py="sys", script="ops/record.py",
        desc="experiment record (start/finish/render/list/show passed through as-is)",
        notes=["to keep run_id consistent everywhere, use only --run-id; --name adds a timestamp prefix",
               "a second start with the same run_id exits immediately; finish is idempotent and repeatable"]),
    "runmeta": dict(
        stage="ops", py="sys", script="ops/runmeta.py",
        desc="RUNMETA.json writer (pins the output dir back to commit+argv; written automatically by the launcher)",
        notes=["usage: run.py runmeta <outdir> --cmd '<actual command>' [--kind K --note N]",
               "appends to the launches list, does not overwrite -- a second launch into the same dir leaves two records",
               "launch_probe/launch_eval already call it automatically; a hand-rolled launch via gpu-run must add one entry manually"]),
    "preset-sweep": dict(
        stage="ops", py="sys", script="sweep_preset.py",
        desc="generate a batch of presets from a parameter grid (--base <preset> --grid key=value,value,...; pure CPU)",
        notes=["grid-key whitelist: temperature/top_p/max_tokens/seed/reasoning_effort;"
               "to sweep api/start_date/stop, open the preset by hand",
               "multiple --grid entries take the Cartesian product; refuses to overwrite an existing same-name preset, --force allows it; --dry-run only prints",
               "commit after generating, before launching (dirty-tree gate); each grid point's run_id carries the preset name",
               "the θ sweep is sweep-run/sweep-curve (sweep_theta.py); this sweeps sampling settings, do not confuse the two"]),
    "launch-probe": dict(
        stage="ops", py="sys", script="ops/launch_probe.py",
        gate=True, desc="training-cell card-scheduling launcher (smoke/full; the cell table is read from CELLS in this file)",
        notes=["it ssh+tmux's the launch itself, so it passes the dirty-tree gate before acting; --dry-run is not blocked"]),
    "launch-eval": dict(
        stage="ops", py="sys", script="ops/launch_eval.py",
        gate=True, desc="eval card-scheduling launcher (the tool tier runs first, the call tier consumes its trigger point)",
        notes=["it ssh+tmux's the launch itself, so it passes the dirty-tree gate before acting; --dry-run is not blocked",
               "before launching, the call tier hard-checks whether its dependent tool cell has REPLAY_REPORT.json,"
               "exits if not -- the dependency order in SKILL.md Phase C4 must not be reversed"]),
    "build-lesson-artifact": dict(
        stage="ops", py="sys", script="learn/vllm/build_artifact.py",
        desc="deterministic converter from lesson page to a single-file artifact (pure CPU; inlines styles and scripts, strips the document shell)",
        notes=["requires --lesson; the output defaults to <name>.artifact.html, in the same dir as the lesson page",
               "the output is rendered, **do not edit it by hand** -- the next rerun overwrites it directly; edit the lesson page or assets/ instead",
               "--check only verifies the output is in sync with the source (exits 3 if out of sync); run it before publishing",
               "the exit self-check blocks doctype/body/relative paths/external-linked resources; exits 2 if any is present"]),
    "build-token-walk": dict(
        stage="ops", py="vllm", script="learn/vllm/build_token_walk.py",
        desc="deterministic converter from raw token stream to a token-by-token step-through lesson page (pure CPU; requires openai_harmony decoding)",
        notes=["requires --traj --toolcall --out; --traj must be recorded with --api harmony"
               "(exits 2 immediately without out_token_ids)",
               "runs in vllm-env: it is the only one with openai_harmony installed",
               "the channel -> destination rule is rewritten here; after changing the vllm version, come back and check"
               "whether it still matches vllm/parser/harmony.py:46-56",
               "the output is rendered, **do not edit it by hand**; run build-lesson-artifact again before publishing"]),
}

# ---------------------------------------------------------------- recipe registry
# Named multi-step chains. Values in params that are None must be given via --set; {placeholder}
# in args/done are filled from params, a foreach step expands a comma-separated list ({item}),
# shards=N starts N piece processes.

RECIPES = {
    "splice-wrapup": dict(
        desc="splice back the eight-arm wrap-up chain: extract -> per-arm exec (4 pieces) -> score -> acceptance",
        params=dict(run_dir=None,
                    arms="nofill,skel_a,skel_bare,skel_b,skel_switch,switch_only",
                    cache="pipeline/inject/exec_cache/aw_gptoss.jsonl",
                    tag=""),
        steps=[
            dict(name="extract", task="extract-completed",
                 args=["--run-dir", "{run_dir}", "--arms", "{arms}",
                       "--tag", "{tag}"]),
            dict(name="exec_{item}", task="exec-calls", foreach="arms", shards=4,
                 args=["--plan", "{run_dir}/exec_in_{item}.jsonl",
                       "--out", "{run_dir}/exec_calls_{item}.jsonl",
                       "--cache", "{cache}", "--exp", "splice_{item}"],
                 done=dict(exists="{run_dir}/exec_calls_{item}.s0.jsonl")),
            dict(name="score", task="inject-score",
                 args=["--run-dir", "{run_dir}", "--tag", "{tag}"],
                 done=dict(exists="{run_dir}/INJECT_REPORT{tag}.json")),
            dict(name="acceptance", task="acceptance",
                 args=["--run-dir", "{run_dir}", "--tag", "{tag}"],
                 done=dict(exists="{run_dir}/ACCEPT_REPORT.json")),
        ]),
    "splice-score": dict(
        desc="rescore only: score -> acceptance (use when exec output already exists)",
        params=dict(run_dir=None, tag=""),
        steps=[
            dict(name="score", task="inject-score",
                 args=["--run-dir", "{run_dir}", "--tag", "{tag}"],
                 done=dict(exists="{run_dir}/INJECT_REPORT{tag}.json")),
            dict(name="acceptance", task="acceptance",
                 args=["--run-dir", "{run_dir}", "--tag", "{tag}"],
                 done=dict(exists="{run_dir}/ACCEPT_REPORT.json")),
        ]),
    "annotate-chain": dict(
        desc="annotation chain: build -> param_label -> check_callstr (same --config)",
        params=dict(config=None),
        steps=[
            dict(name="build", task="ann-build", args=["--config", "{config}"]),
            dict(name="params", task="ann-params", args=["--config", "{config}"]),
            dict(name="check", task="ann-check-callstr",
                 args=["--config", "{config}"]),
        ]),
    "engine-smoke": dict(
        desc="recipe-engine smoke test: a two-step pure-CPU self-test that verifies state.json/logs/the resume path itself",
        params=dict(),
        steps=[
            dict(name="selftest_a", task="parse-call-selftest", args=[]),
            dict(name="selftest_b", task="parse-call-selftest", args=[]),
        ]),
}

# ---------------------------------------------------------------- engine

def build_cmd(t, extra):
    prog = t.get("prog") or PY[t["py"]]
    cmd = [prog]
    if "script" in t:
        cmd.append(str(ROOT / t["script"]))
    return cmd + list(t.get("args", [])) + list(extra)


def task_env(t):
    env = os.environ.copy()
    env.update(t.get("env", {}))
    return env


def gate_of(t):
    """Whether a task goes through the dirty-tree gate, the one decision chain: gate > handoff > gpu."""
    return t.get("gate", t.get("handoff", t.get("gpu", False)))


# The job ledger and lock files do not count as dirty: they are launch by-products (append-only
# records) and do not affect any output; without this exemption, the second shot in one session
# would always be blocked by its own previous shot's registration.
# record.py / ops/runmeta.py each keep a copy of this same list; changing it here means syncing
# all three places.
LEDGER_PATHS = ("ops/jobs.json", "ops/runs.jsonl", "RESULTS.md",
                "ops/jobs.json.lock")


def git_dirty():
    r = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return [l for l in r.stdout.splitlines()
            if l.strip() and l[3:] not in LEDGER_PATHS]


def gate_dirty(extra, honor_dry=True):
    """The dirty-tree gate. Returns the args with --allow-dirty filtered out; calls SystemExit
    directly when it blocks. honor_dry=False is for the command-only paths (show/print_handoff):
    they do not execute anything, so --dry-run means nothing to them and must not become a
    backdoor around the gate."""
    allow = "--allow-dirty" in extra
    extra = [a for a in extra if a != "--allow-dirty"]
    if (honor_dry and "--dry-run" in extra) or allow:
        return extra
    lines = git_dirty()
    if lines is None:                       # git itself will not run -> treat as dirty, do not allow
        raise SystemExit("git status failed; treated as a dirty tree and refuses to emit the launch command;"
                         "check the git environment, or force it with --allow-dirty.")
    if lines:
        head = "\n".join("  " + l for l in lines[:8])
        more = f"\n  ...{len(lines)} lines total" if len(lines) > 8 else ""
        raise SystemExit(
            f"working tree is dirty, refusing to emit the launch command (commit before launching, CLAUDE.md hard rule):\n"
            f"{head}{more}\nforce it with --allow-dirty.")
    return extra


def tail_of(path, n=40):
    """Read the last n non-empty lines of the log. tqdm uses \\r to overwrite the same line; convert it to \\n first."""
    p = Path(path)
    if not p.exists():
        return "(log does not exist)"
    with open(p, "rb") as f:
        f.seek(0, 2)
        f.seek(max(0, f.tell() - 65536))
        txt = f.read().decode("utf-8", "replace")
    lines = [l for l in txt.replace("\r", "\n").split("\n") if l.strip()]
    return "\n".join(lines[-n:])


def run_direct(name, t, extra):
    cmd = build_cmd(t, extra)
    # The banner goes to stderr: stdout is reserved for the underlying script -- machine-readable
    # output such as gpu-jobs json is no longer valid JSON once the banner pollutes it (confirmed by
    # audit review testing)
    print(f"[{name}] cwd={t.get('cwd', ROOT)}", file=sys.stderr)
    print("  " + shlex.join(cmd), file=sys.stderr, flush=True)
    r = subprocess.run(cmd, cwd=t.get("cwd", str(ROOT)), env=task_env(t))
    return r.returncode


def print_handoff(name, t, extra):
    extra = gate_dirty(extra, honor_dry=False)
    cmd = build_cmd(t, extra)
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    print(f"# {name}: builds the command only, does not launch. Launching goes through the gpu-run skill's full lifecycle")
    print(f"# (probe the card -> pick a card -> smoke -> commit -> tmux -> double registration -> monitor -> finish). HEAD={head}")
    if t.get("cwd"):
        print(f"# needs cd: {t['cwd']} (the gpu-run template cd's to the repo root by default,"
              f"this task must use the cwd here instead)")
    for k, v in t.get("env", {}).items():
        print(f"# needs environment variable: {k}={v}")
    for n in t.get("notes", []):
        print(f"# {n}")
    print(shlex.join(cmd))
    return 0


# ---------------------------------------------------------------- recipe engine

def expand(s, params):
    try:
        return s.format(**params)
    except KeyError as e:
        raise SystemExit(f"recipe placeholder was not given a value: {e} (use --set k=v)")


def plan_steps(rc, params):
    """Expand a recipe into concrete steps: [{name, task, cmds:[argv...], logs:[...], done}]."""
    out = []
    for st in rc["steps"]:
        items = ([x.strip() for x in params[st["foreach"]].split(",") if x.strip()]
                 if "foreach" in st else [None])
        for it in items:
            p = dict(params, item=it) if it is not None else params
            t = TASKS[st["task"]]
            args = [expand(a, p) for a in st["args"]]
            base = build_cmd(t, args)
            n = st.get("shards", 0)
            if n:
                cmds = [base + ["--num-shards", str(n), "--shard-id", str(i)]
                        for i in range(n)]
            else:
                cmds = [base]
            done = None
            if st.get("done"):
                done = {k: expand(v, p) for k, v in st["done"].items()}
            if st.get("done"):
                unknown = set(st["done"]) - {"exists"}
                if unknown:
                    raise SystemExit(f"recipe step {st['name']} has an unrecognized done key: "
                                     f"{sorted(unknown)} (whitelist: exists)")
            out.append(dict(name=expand(st["name"], p), task=st["task"],
                            cmds=cmds, done=done,
                            env=t.get("env", {}), cwd=t.get("cwd", str(ROOT)),
                            handoff=t.get("handoff", t.get("gpu", False)),
                            gate=gate_of(t)))
    return out


def fp_of(cmds):
    return hashlib.sha1(json.dumps(cmds).encode()).hexdigest()[:12]


def save_state(d, state):
    tmp = d / "state.json.tmp"
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1))
    os.replace(tmp, d / "state.json")


def check_done(done):
    if not done:
        return True
    unknown = set(done) - {"exists"}
    if unknown:
        # A mistyped key must not silently degrade to "only look at rc" -- that would judge a step with
        # no outputs as done
        raise SystemExit(f"done criterion has unrecognized keys: {sorted(unknown)} (whitelist: exists)")
    return (ROOT / done["exists"]).exists()


def run_recipe(name, argv):
    rc = RECIPES.get(name)
    if rc is None:
        raise SystemExit(f"no such recipe: {name} (see run.py recipes for the list)")
    params = dict(rc["params"])
    rid, resume, dry, allow_dirty = None, False, False, False
    it = iter(argv)
    for a in it:
        if a == "--set":
            kv = next(it, "")
            if "=" not in kv:
                raise SystemExit(f"--set wants k=v, got {kv!r}")
            k, v = kv.split("=", 1)
            if k not in params:
                raise SystemExit(f"recipe {name} has no parameter {k}; it has {list(params)}")
            params[k] = v
        elif a == "--id":
            rid = next(it, None)
        elif a == "--resume":
            resume = True
        elif a == "--dry-run":
            dry = True
        elif a == "--allow-dirty":
            allow_dirty = True         # the escape hatch for the dirty-tree gate on handoff steps
        else:
            raise SystemExit(f"recipe does not recognize the parameter: {a} (underlying parameters are written into the recipe definition, not passed through)")
    missing = [k for k, v in params.items() if v is None]
    if missing:
        raise SystemExit(f"recipe {name} is missing parameters: {missing} (use --set k=v)")

    steps = plan_steps(rc, params)
    if dry:
        for i, s in enumerate(steps):
            print(f"[{i + 1}/{len(steps)}] {s['name']}")
            for c in s["cmds"]:
                print("    " + shlex.join(c))
        return 0

    def params_of(p):
        try:
            return json.loads((p / "state.json").read_text()).get("params")
        except Exception:
            return None

    if resume and rid is None:
        # Only recognize a history directory whose params match verbatim -- picking by mtime at random
        # can attach to another run and overwrite its state.json (this has been confirmed by review).
        olds = sorted(LOGD.glob(f"{name}__*"), key=lambda p: p.stat().st_mtime)
        match = [p for p in olds if params_of(p) == params]
        if not match:
            names = [p.name for p in olds[-5:]]
            raise SystemExit(f"--resume could not find a history dir for {name} with matching parameters;"
                             f"specify one with --id. Recent ones: {names}")
        rid = match[-1].name.split("__", 1)[1]
    rid = rid or time.strftime("%Y%m%d_%H%M%S")
    d = LOGD / f"{name}__{rid}"
    if (d / "state.json").exists() and params_of(d) != params:
        raise SystemExit(f"{d.name} holds a run with a different set of parameters (params={params_of(d)}),"
                         f"refusing to overwrite; use a different --id or align the parameters.")
    d.mkdir(parents=True, exist_ok=True)

    old = {}
    sp = d / "state.json"
    if resume and sp.exists():
        for s in json.loads(sp.read_text()).get("steps", []):
            old[(s["name"], s["fp"])] = s

    dirty = git_dirty() or []
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    state = dict(recipe=name, id=rid, params=params, git_commit=head,
                 git_dirty=bool(dirty), started_at=time.strftime("%F %T"),
                 steps=[dict(name=s["name"], fp=fp_of(s["cmds"]), state="pending",
                             rc=None, cmds=s["cmds"], logs=[], wall_s=None)
                        for s in steps])
    save_state(d, state)

    for i, s in enumerate(steps):
        rec = state["steps"][i]
        prev = old.get((rec["name"], rec["fp"]))
        if prev and prev.get("state") == "ok":
            rec.update(prev)
            rec["state"] = "ok"
            print(f"[{i + 1}/{len(steps)}] {s['name']} SKIP (already done, fingerprint matches)")
            save_state(d, state)
            continue
        if s.get("gate") and not allow_dirty:
            # handoff steps and gate steps (self-launching tasks such as launch-probe/launch-eval) go
            # through the same gate: a recipe must not fire on a dirty tree either
            lines = git_dirty()        # None (git failed) is treated as dirty, not allowed
            if lines is None or lines:
                why = "git status failed" if lines is None else f"{len(lines)} lines dirty"
                raise SystemExit(
                    f"step {s['name']} is a launch-type task and the working tree is not clean ({why}),"
                    "refusing to emit the launch command (commit before launching, CLAUDE.md hard rule);"
                    "to force it: append --allow-dirty after recipe.")
        if s["handoff"]:
            rec["state"] = "handoff"
            save_state(d, state)
            print(f"[{i + 1}/{len(steps)}] {s['name']} is a launch-type task, the recipe stops here:")
            for c in s["cmds"]:
                print("    " + shlex.join(c))
            print("launch via gpu-run; after it finishes, run.py recipe "
                  f"{name} --id {rid} --resume to continue.")
            return 3
        rec["state"], t0 = "running", time.time()
        rec["started_at"] = time.strftime("%F %T")
        save_state(d, state)
        procs, logs = [], []
        env = os.environ.copy()
        env.update(s["env"])
        for j, c in enumerate(s["cmds"]):
            suffix = f".s{j}" if len(s["cmds"]) > 1 else ""
            log = d / f"{i:02d}_{s['name']}{suffix}.log"
            logs.append(str(log))
            fh = open(log, "a")
            fh.write(f"# [{time.strftime('%F %T')}] step={s['name']} "
                     f"cmd: {shlex.join(c)}\n")
            fh.flush()
            procs.append((subprocess.Popen(c, cwd=s["cwd"], env=env,
                                           stdout=fh, stderr=fh), fh))
            print(f"[{i + 1}/{len(steps)}] {s['name']}"
                  f"{suffix or ''} -> {log.name}", flush=True)
        rcs = []
        for p, fh in procs:                 # collect rc one by one, do not use a bare wait (it will not get the code)
            rcs.append(p.wait())
            fh.close()
        rec["rc"] = rcs if len(rcs) > 1 else rcs[0]
        rec["logs"] = logs
        rec["wall_s"] = round(time.time() - t0, 1)
        ok = all(r == 0 for r in rcs) and check_done(s["done"])
        rec["state"] = "ok" if ok else "failed"
        save_state(d, state)
        if not ok:
            why = (f"rc={rec['rc']}" if any(rcs) else
                   f"rc was all 0 but outputs are not in place: {s['done']}")
            print(f"\nFAILED step {i + 1}/{len(steps)} {s['name']} {why} "
                  f"wall={rec['wall_s']}s")
            for lg in logs:
                print(f"  log: {lg}")
            bad = next((logs[j] for j, r in enumerate(rcs) if r != 0), logs[-1])
            print(f"---- last 40 lines ({Path(bad).name}) ----")
            print(tail_of(bad))
            print(f"after fixing: python3 run.py recipe {name} --id {rid} --resume")
            return 1
    print(f"\nrecipe {name} all {len(steps)} steps complete. Status: {d / 'state.json'}")
    return 0


def cmd_status(argv):
    if argv:
        d = Path(argv[0])
        if not d.is_absolute():
            d = LOGD / argv[0]
    else:
        dirs = sorted(LOGD.glob("*__*"), key=lambda p: p.stat().st_mtime)
        if not dirs:
            raise SystemExit(f"no recipe records under {LOGD} yet")
        d = dirs[-1]
    sp = d / "state.json"
    if not sp.exists():
        raise SystemExit(f"no status file: {sp}")
    st = json.loads(sp.read_text())
    print(f"recipe {st['recipe']}  id={st['id']}  HEAD={st['git_commit']}"
          f"{'+dirty' if st['git_dirty'] else ''}  started at {st['started_at']}")
    for i, s in enumerate(st["steps"]):
        wall = f" {s['wall_s']}s" if s.get("wall_s") else ""
        print(f"  [{i + 1}] {s['name']:<24} {s['state']:<8} rc={s['rc']}{wall}")
        if s["state"] == "failed" and s.get("logs"):
            print("  ---- last 20 lines of the failure log ----")
            print("  " + tail_of(s["logs"][-1], 20).replace("\n", "\n  "))
        if s["state"] == "handoff":
            for c in s["cmds"]:
                print("    awaiting launch: " + shlex.join(c))
    return 0


# ---------------------------------------------------------------- viewing commands

STAGE_ORDER = ("collect", "annotate", "train", "eval", "inject", "live", "ops")


def cmd_list(argv):
    want = argv[0] if argv else None
    for stg in STAGE_ORDER:
        if want and stg != want:
            continue
        rows = [(n, t) for n, t in TASKS.items() if t["stage"] == stg]
        if not rows:
            continue
        print(f"\n== {stg} ==")
        for n, t in rows:
            mark = ("[launch]" if t.get("handoff", t.get("gpu", False))
                    else "[GPU]" if t.get("gpu") else "")
            print(f"  {n:<22} {mark:<6} {t['desc']}")
    print("\nrecipes (see run.py recipes for details):", ", ".join(RECIPES))
    return 0


def cmd_show(argv):
    if not argv or argv[0] not in TASKS:
        raise SystemExit(f"need a task name; available: {', '.join(TASKS)}")
    n, t = argv[0], TASKS[argv[0]]
    if gate_of(t):
        # What show prints is the launch command you can copy directly -- it goes through the same
        # dirty-tree gate too; do not let the documented command-printing path become a backdoor around
        # the gate (audit A3); show <task> --allow-dirty lets it through.
        # honor_dry=False: show does not execute anything, --dry-run is not its escape hatch
        gate_dirty(argv[1:], honor_dry=False)
    print(f"{n}: {t['desc']}  (stage={t['stage']})")
    print(f"  command: {shlex.join(build_cmd(t, ['<args...>']))}")
    print(f"  cwd: {t.get('cwd', ROOT)}")
    if t.get("cwd"):
        print(f"  # needs cd: {t['cwd']} (the gpu-run template cd's to the repo root by default,"
              f"this task must use the cwd here instead)")
    if t.get("env"):
        print(f"  env: {t['env']}")
    print(f"  gpu={t.get('gpu', False)} handoff={t.get('handoff', t.get('gpu', False))}"
          f" dirty-tree gate={gate_of(t)}")
    for note in t.get("notes", []):
        print(f"  - {note}")
    return 0


def cmd_recipes():
    for n, rc in RECIPES.items():
        print(f"\n{n}: {rc['desc']}")
        print(f"  parameters: " + ", ".join(
            f"{k}(required)" if v is None else f"{k}={v!r}"
            for k, v in rc["params"].items()))
        for st in rc["steps"]:
            extra = " x" + str(st["shards"]) if st.get("shards") else ""
            fe = f" foreach={st['foreach']}" if "foreach" in st else ""
            print(f"    {st['name']} -> {st['task']}{extra}{fe}")
    return 0


def cmd_selfcheck():
    bad = 0
    seen_prog = set()
    for n, t in TASKS.items():
        if "py" not in t and "prog" not in t:
            print(f"entry missing py/prog: {n} (will raise a bare KeyError at runtime)")
            bad += 1
            continue
        if "prog" not in t and t["py"] not in PY:
            print(f"entry's py key is not in the interpreter map: {t['py']}  (task {n})")
            bad += 1
            continue
        prog = t.get("prog") or PY[t["py"]]
        if prog not in seen_prog and prog not in ("python3", "bash"):
            if not Path(prog).exists():
                print(f"missing interpreter/program: {prog}  (task {n})")
                bad += 1
            seen_prog.add(prog)
        if "script" in t and not (ROOT / t["script"]).exists():
            print(f"missing script: {t['script']}  (task {n})")
            bad += 1
        if "cwd" in t and not Path(t["cwd"]).is_dir():
            print(f"missing cwd directory: {t['cwd']}  (task {n})")
            bad += 1
    for rn, rc in RECIPES.items():
        # The placeholders must be fully expandable with params (item is only additionally available
        # when the step has a foreach) -- exploding at runtime means exploding in the middle of the
        # experiment; item must not be stuffed in unconditionally, otherwise you cannot catch the most
        # common copy-paste mistake, "using {item} but forgetting to write foreach"
        base_probe = {k: "X" for k in rc["params"]}
        for st in rc["steps"]:
            if st["task"] not in TASKS:
                print(f"recipe {rn} references a task that does not exist: {st['task']}")
                bad += 1
            if "foreach" in st and st["foreach"] not in rc["params"]:
                print(f"recipe {rn}'s foreach={st['foreach']} is not in params")
                bad += 1
            if "name" not in st:
                print(f"recipe {rn} has a step missing the name field")
                bad += 1
                continue
            probe = dict(base_probe)
            if "foreach" in st:
                probe["item"] = "X"
            fields = [st["name"], *st.get("args", [])]
            fields += list((st.get("done") or {}).values())
            for s in fields:
                try:
                    s.format(**probe)
                except (KeyError, IndexError, ValueError, TypeError,
                        AttributeError) as e:
                    print(f"recipe {rn} step {st['name']} has a broken placeholder: {s!r} ({e})")
                    bad += 1
            unknown = set(st.get("done") or {}) - {"exists"}
            if unknown:
                print(f"recipe {rn} step {st['name']} has a done key not in the whitelist: "
                      f"{sorted(unknown)} (only exists is recognized)")
                bad += 1
    for cell, (task, dep) in EVAL_CELLS.items():
        if task not in TASKS:
            print(f"EVAL_CELLS[{cell}] references a task that does not exist: {task}")
            bad += 1
        if dep is not None and dep not in EVAL_CELLS:
            print(f"EVAL_CELLS[{cell}] depends on a cell that does not exist: {dep}")
            bad += 1
    # configs/'s model table and generation presets (the gen-preset rework, 2026-08-20):
    # aliases must resolve, field types must match, block on any one being broken -- the preset is
    # the shared spec between launching and collection, if it breaks and is not reported here, it
    # explodes in the middle of the experiment instead
    n_presets = 0
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        import preset_loader as PL
        m = PL.load_models()
        for k, v in m["models"].items():
            if not v.get("path") or not v.get("note"):
                print(f"models.json entry {k} missing path/note")
                bad += 1
        for alias, tgt in m["aliases"].items():
            if tgt not in m["models"]:
                print(f"models.json alias {alias} points to an entry that does not exist: {tgt}")
                bad += 1
        names = PL.list_presets()
        n_presets = len(names)
        for name in names:
            p = json.loads((PL.PRESET_DIR / f"{name}.json").read_text())
            for e in PL.validate(p, m):
                print(f"preset {name}: {e}")
                bad += 1
    except Exception as e:
        print(f"configs/ read failed: {type(e).__name__}: {e}")
        bad += 1
    print(f"selfcheck: {len(TASKS)} tasks / {len(RECIPES)} recipes / "
          f"{n_presets} presets, {'all present' if not bad else f'{bad} missing'}")
    return 1 if bad else 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "list":
        return cmd_list(rest)
    if cmd == "show":
        return cmd_show(rest)
    if cmd == "recipes":
        return cmd_recipes()
    if cmd == "recipe":
        if not rest:
            raise SystemExit("recipe needs a recipe name (see run.py recipes for the list)")
        return run_recipe(rest[0], rest[1:])
    if cmd == "status":
        return cmd_status(rest)
    if cmd == "selfcheck":
        return cmd_selfcheck()
    if cmd == "launch":
        sys.path.insert(0, str(ROOT / "ops"))
        from launch_cmd import cmd_launch
        return cmd_launch(rest)
    t = TASKS.get(cmd)
    if t is None:
        raise SystemExit(f"unrecognized: {cmd} (see run.py list for tasks, run.py recipes for recipes)")
    if t.get("handoff", t.get("gpu", False)):
        return print_handoff(cmd, t, rest)
    if gate_of(t):
        # Letting --dry-run through and stripping --allow-dirty both happen inside gate_dirty; short-
        # circuiting at this layer would leak --allow-dirty as-is to the underlying script (which does
        # not recognize this flag).
        # This path really executes (launch-probe/launch-eval do their own ssh+tmux), so honor_dry
        # stays True: their --dry-run genuinely does not launch
        rest = gate_dirty(rest)
    return run_direct(cmd, t, rest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
