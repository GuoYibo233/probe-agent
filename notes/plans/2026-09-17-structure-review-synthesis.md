# Synthesis of the four Fable reviews of the fourth draft (2026-09-17)

Four read-only reviewers (Claude Fable 5.1, effort xhigh) read
`plans/2026-09-14-structure-from-zero.md` at commit 96fe9d2, each from one
standpoint. Their full reports are in this directory:

- `2026-09-17-structure-review-dependencies.md`: the import graph implied by
  the tree, eleven change scenarios with the files each one touches, and
  "if this file changes, who breaks" per file.
- `2026-09-17-structure-review-structure.md`: layer cuts, god files, naming,
  the principle-5 versus principle-6 trade, what today's pain points the plan
  fixes and what it carries over.
- `2026-09-17-structure-review-grounding.md`: every one of today's 61 code
  files mapped to its planned home, and the plan's technical claims checked
  against the code with file:line evidence.
- `2026-09-17-structure-review-lifecycle.md`: one experiment walked through
  first run, rerun, edit, sweep, inject, debug and two sessions at once.

The two questions gyb asked were: when one thing is added or changed, is the
set of files to touch small and known in advance; and when one file is
edited, can the tree alone say who uses it. This synthesis keeps only the
findings that answer those two questions or that two or more reviewers
raised independently. Numbers below are the reviewers' counts from the
plan's tree and today's code, cited to the report that made them.

## 1. Verdict

The layer cut is right and every reviewer lists the same things to keep
(section 4). The plan fails the two questions in four places.

First, the two extensions the tree was drawn to invite are not small. A
fourth probe method touches five to eight files across `data/`, `models/`,
`train/`, `eval/` and `agent/` where the plan says two (dependencies P2). A
second agent-model family touches `agent/inject_format.py`,
`models/probe_models/service.py` and `agent/inject.py` besides the family
file, because the probe service renders and encodes with the agent's
tokenizer today (dependencies P4, grounding F4).

Second, four files have a fan-in of five to ten importers and their tree
line names none of them: `experimental_settings/schema.py` (about ten
importers, edited by every extension, and it imports `agent/inject_format.py`
upward), `jobs/registry.py` (about ten importers, in the top layer by
placement), `models/probe_models/base.py` (six) and
`models/agent_models/gptoss.py` (five, including the probe service). For
these four the answer to "who breaks" is "read the code" (dependencies
section 5; structure items 4 and 5).

Third, principle 7 (eval reads disk only, no torch) contradicts today's code
in three places: the temperature fit is torch LBFGS over the full logits
matrix (`pipeline/eval/eval_tool.py:213-224`); cgen and cparam generate only
at the rows a ctool run's frozen theta selects, at most 8,533 rows per np821
run against 507,104 rows if every example is predicted
(`eval_causal_call.py:11-13,536-549`); cparam's `pred_tool` arm reads the
ctool run's argmax per row (`eval_causal_param.py:93-112,435`). The eval
report that carries theta and the temperature is read by three files in two
layers and defined nowhere (grounding F1, F2; dependencies P3; structure 3;
lifecycle B3).

Fourth, the mechanism that makes principle 2 true (what enters a key, one
key per setting or per stage, the output directory name, the "finished"
check per stage, what a piece is told on its command line, where debug and
sweep expand) was deleted with Part 2 and the tree lines do not restate it.
Under the fourth draft's own wording, editing a learning rate re-keys the
sample stage too (lifecycle A1, A2, B4, B5; dependencies P6).

## 2. Fixes that two or more reviewers converged on

Each item names the tree entry, what breaks, and the change. Items are in
the order of how much they cost gyb over the next six months, by the
reviewers' rankings.

1. Split `experimental_settings/schema.py` into three files with one import
   direction: `schema.py` (fields, defaults, axis literals, the stage
   table; imports nothing from the repo), `loader.py` (YAML to setting,
   debug overlay, overrides, sweep expansion, references, diff), `key.py`
   (`key(setting, stage, versions)` where the calling stage passes its own
   VERSION tuple, so no import cycle). `run.py selfcheck` cross-checks the
   axis literals against `agent/inject_format.py`, `data/environments/*.py`
   and the method files. Then "who breaks when I edit the axes" is
   `loader.py` plus the selfcheck. (dependencies P1, structure 4, lifecycle A1)

2. Split `jobs/registry.py` on day one: `jobs/ledger.py` (append a row
   under the lock, meta.json, heartbeat; standard library; imported by every
   stage) and `jobs/status.py` (ls, where, find, kill, RESULTS.md render;
   imported by `run.py` only). Only the login-machine launcher and `run.py`
   append to `runs.jsonl`; a stage process writes its state into its own run
   directory's meta.json, which `ls` folds in, so no fcntl lock on NFS from
   compute nodes. (dependencies P8, structure 5, lifecycle A3, A4, B11)

3. Keep the shared packing and the row-by-row reference. Today
   `pipeline/train/share_data.py` (611 lines) is shared by cgen and cparam
   with about 20 method-specific lines, and `train_causal_share.py` branches
   on mode in about 15 lines out of 1,000; the plan copies both into two
   files and guards the copies with an alignment test that is deferred.
   Bring back `train/packing.py` and `train/reference.py`; `train/cgen.py`
   and `train/cparam.py` then hold only the instance strings, the target, the
   loss positions and the validation. On the eval side one
   `eval/exact_match.py` with the target column chosen by the method.
   (structure 1 and 2, grounding F5)

4. Split `train/utils/trainer.py` at the seams today's code already has:
   `train/trainer.py` (loop, schedule, metrics, heartbeat, best/ and last/,
   resume at the same commit), `train/tuning.py` (full versus LoRA, merge on
   save; today's `lora_util.py`), `train/predict.py` (the last step: load
   the probe still on the card, write prediction rows). The continue rule
   becomes decidable: `train_done` marker present, predictions only; `last/`
   present, resume; neither, fresh. Each method file supplies a
   `predict(probe, rows)` hook so `trainer.py` never branches on method.
   (structure 1, lifecycle A6, dependencies P2)

5. Make the ctool-to-cgen dependency explicit and give the eval report a
   format. A cgen or cparam setting carries a reference field such as
   `probe.trigger_run: train_probe/<ctool setting>`; the stage table gives
   train(cgen) that upstream and folds its key in; `predict.py` generates
   at the rows that ctool run's frozen theta selects and writes the ctool
   score beside the generated text. The theta-and-temperature file becomes
   `data/probe_report.py` (write, read), read by the probe service and the
   two generating evals. The temperature fit is reimplemented as a 1-D
   minimiser in numpy, and the plan states that existing numbers are
   re-derived under it. If instead gyb wants generation at every cut so any
   theta can be scored later, the plan states the 60x cost. (structure 3,
   dependencies P3, grounding F1 F2, lifecycle B3)

6. Move rendering and encoding off the probe service. The loop runs in the
   AppWorld venv, which cannot host openai_harmony (pydantic 1 versus 2,
   `envs/collect/common.py:14-19`), so today `/render`, `/encode`, `/decode`
   sit on the probe server. The plan puts messages-to-tokens in
   `agent_models/gptoss.py` without saying which process serves it. Fix: the
   agent service's client gains `encode` and `decode` (vLLM's server exposes
   `/tokenize` and `/detokenize`), `probe_models/service.py` keeps score and
   generate only, and the harmony control-token wrapping of a p2 message
   moves into `gptoss.py`, leaving `inject_format.py` with placement, body
   and system text. Then a second agent family is one file plus a row. Also
   split each `service.py` into `server.py` and `client.py` so the venv
   boundary is a file boundary that selfcheck can import-test.
   (dependencies P4, grounding F4, structure 9)

7. Put every result-changing value inside `experimental_settings/` and out
   of code. Today's plan leaves outside the key: vLLM serving flags
   (`max_model_len`, dtype, quantisation) on `agent_models/service.py`'s
   line, the serving section of `models/table.yaml` (host, port, memory
   fraction, which do not change a result but are keyed), the benchmark
   task-split lists in `constants/`, and `reasoning_effort` and
   `start_date` which are client keys today and a server pin. Fix: the
   model table moves to `experimental_settings/models.yaml` (role, family
   or backbone, weights alias, context length, dtype; hook-protected,
   keyed) and serving location moves to `constants/models.yaml` (never
   keyed); date and effort are setting fields passed into `gptoss.py`;
   split lists are owned by the environment file. The open hook question
   closes itself. (dependencies P5, structure 7, grounding F8)

8. Restate the lifecycle mechanism on the tree lines. The stage table in
   `schema.py` names, per stage: the sections it reads, its upstream stage,
   the modules whose VERSION folds into its key, its venv, its piece rule.
   The key is per stage. `jobs/launch.py` freezes the resolved setting as
   `settings.yaml` in the run directory and every piece command names the
   run directory, never the setting name, so a YAML edit after launch or
   before a refire cannot move the process. The output directory is
   `<root>/<stage>/<key>` from one function. Debug is applied before keying
   and adds `debug: true` to the key, with rows flagged, under
   `<root>/debug/`. Sweep expands at load into children named
   `<setting>/<field>=<value>`, accepted by `run.py`. VERSION constants live
   on `data/probe_input.py`, `data/build_dataset.py`, `data/task_record.py`,
   `agent/inject.py`, `train/trainer.py`, the method files and
   `eval/score_run.py`, not only on `appworld.py` and schema defaults; CPU
   evals always recompute and write the commit into the report. Axis values
   are never renamed, only added and retired (or a `RENAMED` map in
   `key.py`). (lifecycle A1 A2 A6 A7 B1 B4 B5, dependencies P6 P9)

9. Decide the task record's layout and the claim mechanism. Today records
   are one file per (task, seed) with resume by "final row exists"
   (`envs/collect/run_appworld.py:74-82`); the plan's "one jsonl appended by
   many pieces" has no lock and a killed piece leaves a partial line that
   breaks every Polars read. Fix: `data/task_record.py` writes one file per
   (task, seed); claim is an O_EXCL create with the piece's session name as
   the first line; refire in `launch.py` releases files whose owner session
   is gone. (lifecycle A5, grounding F6)

10. State each drop and give the survivors a home. About a third of today's
    61 files have no planned home and the plan does not say they are
    dropped: the sampler and verdict engine (`ops/sampler.py`,
    `ops/verdicts.py`; CONTEXT.md still defines sampler, verdict,
    escalation line, incident agent, refire quota on them), the offline
    replay line (`replay_inject.py` and six siblings), the readonly axis,
    `ident3_gate.py`, `pipeline/driver.py`'s `awaiting_decision` stop,
    `demo/prepare.py`, the mbert line, the five non-AppWorld environments,
    and the 34 existing test files. Also dropped without a sentence: the
    dirty-tree gate, commit capture and dirty patch, RUNMETA.json, the
    LEDGER_PATHS exemption, service pieces with port checks, the
    deregistration gate. Each gets one line: retired (and which CONTEXT.md
    and CLAUDE.md text goes with it), or its file. The dirty-tree gate goes
    on `jobs/launch.py`'s line as one function. (all four reviews; grounding
    F7, structure 6 10 13, lifecycle B6 B7 B8 C3)

11. Environments are their own layer. `data/`'s own line says a new
    environment goes elsewhere; the folder's callers are `agent/loop.py`,
    `agent/inject.py` and `data/build_dataset.py`, and it holds prompt text,
    not a disk format. Move to top-level `environments/`, and make the
    instruction text a named axis value (`data.instructions: v1`) so a
    prompt variant is a YAML line that enters the key, with VERSION guarding
    only the AppWorld package interface. A `venv:` field on the
    environment's row tells `launch.py` which interpreter starts the loop
    (today `run.py:63-75`, no planned home). (structure 8, dependencies P7)

12. Flatten `train/` and `eval/` and name eval files by the metric.
    `train/methods/ctool.py` and `eval/methods/ctool.py` collide in any file
    switcher; `train/utils/` and `eval/utils/` hold one file each. Proposed:
    `train/`: `trainer.py`, `tuning.py`, `predict.py`, `packing.py`,
    `reference.py`, `ctool.py`, `cgen.py`, `cparam.py`; `eval/`:
    `probe_eval.py`, `fire_threshold.py`, `exact_match.py`, `score_run.py`,
    `method_table.py`. The per-method example construction and the match
    function that both train validation and eval need move to
    `data/methods/<m>.py`, so a fourth method is `data/methods/x.py`,
    `train/x.py`, one axis line and a README block, with no upward import.
    (structure 12, dependencies P2)

13. Fix the claim about Polars. Polars and OmegaConf are installed in none
    of the four venvs (import checks in cprobe-env, mbert-env,
    envs/appworld/venv, envs/vllm-env; `/usr/bin/python3` 3.10 has neither
    polars nor numpy). Polars wheels have no runtime dependencies, so
    installation is plausible but unverified; OmegaConf needs
    antlr4-python3-runtime. The plan says "three venvs" where `run.py`
    registers ten interpreters; the drop of mbert-env and the five benchmark
    venvs is stated, and eval's interpreter is named as one of the three.
    (grounding F3)

## 3. Smaller items, one line each

- The base class line says eight methods and lists nine. (dependencies P11)
- `environments/appworld.py` must import the AppWorld package inside
  `open()`, or `build_dataset.py` runs only in the AppWorld venv. (dependencies P11)
- The prediction run's sizing (`debug.yaml`'s 100 eval examples, the split
  choice) needs a `train.predict` section so an `eval.*` edit never re-keys
  training. (lifecycle B2, dependencies P11)
- A record column added with a VERSION bump re-keys sample and inject; added
  without one, old files fail the strict Polars read. Declare a default per
  column added after the first version. (dependencies P9)
- The ctool head has two owners on the tree (`train/methods/ctool.py` "its
  head" and `probe_models/base.py` "score a prefix"); the head class and its
  save layout live in `base.py`. (dependencies P10)
- `data/build_dataset.py` holds gates with a different edit trigger
  (a new silent failure) than example-making; `data/check_dataset.py` for
  the gates. (structure 11)
- "record" means both the task record and the registry row; call the row
  "row". (lifecycle C2)
- `CONTEXT.md` has no line in the tree; `RESULTS.md` is sent to `jobs/`
  while the other three ledgers go to `notes/`. (structure 13)
- The chat baseline uses the openai SDK today (`envs/collect/common.py`);
  either rewritten on urllib or dropped from `baseline.yaml`. (grounding F9)
- Build refuses unless every requested (task, seed) has a done record, and
  writes the consumed file list with hashes beside the parquet. (lifecycle B9)

## 4. What every reviewer says to keep

The environment object owning the call regex, the call syntax, `speculate`
and `judge`, with the loop calling eight methods and nothing else. One
generation path for sample and inject. `data/probe_input.py` as the one cut
rule offline and live. The three on-disk formats defined once with a VERSION
and read into Polars. `eval/` reading prediction rows only (the direction is
right once item 5 is settled). Output directories named by key. Settings
YAML written by gyb only and hook-enforced. Sweep as a keyword. `constants/`
holding nothing that enters a key. `inject.step` replacing `generate.step`.
`debug.yaml` as sizes only. Deleting the placement JSONs, the vLLM launcher
scripts, `pipeline/configs/`, the collection manifests and the presets.
`run.py` as the single entry with no task registry and no recipe engine.
