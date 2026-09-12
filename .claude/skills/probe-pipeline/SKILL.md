---
name: probe-pipeline
description: >-
  The execution entry point for new1's probe pipeline: an end-to-end run from trajectory
  collection to the matrix report. Pin the batch, then collect (GPU), write/edit code
  (CPU, in parallel with collect), two acceptance lines, build the dataset, smoke each
  cell, batch train, eval in dependency order, summarize the matrix, record and wrap up,
  write back to this skill. It is also **the only entry point for extending this
  pipeline**: adding a new model, a new environment, a new training method (a new cell),
  or a new split method all go through here, and the new method must be written back into
  the skill at wrap-up per Phase E. Invoke whenever Dungeon♂Master says "run the
  pipeline", or any task that needs collect/annotate/train/eval chained together or
  extended. A single GPU task uses gpu-run alone; this skill manages the whole chain.
  Chinese triggers: "跑流水线" / "跑一批探针" / "新数据集跑一遍" / "出矩阵" / "换个环境跑" / "加个新模型/新格" / "换个切分方式"
  / "加一种训练方法".
version: 1.0.0
---

# probe-pipeline: full-chain execution of the probe pipeline

A five-stage pipeline (collect → annotate → train → eval → inject),
wrapped inside a four-phase execution shell (A collect / B write code / C train and eval / D wrap-up).
A gate sits between every stage. **Skipping a gate is a violation.**

Companion documents (go to the first one to copy commands verbatim, the second one to judge whether something should change, the third one when you're stuck):
- Command table: `references/stage-commands.md`
- Invariants checklist: `references/invariants.md` (change any entry here → new and old numbers are no longer comparable)
- Gates and contingencies: `references/gates.md` (gate numbers G1-G24, referenced by number below)
- Extension checklist: `references/extending.md` (**enter here to add a new model / new environment / new training method / new split method**;
  §5 the silent-failure-point table; **§6 the checklist for writing back to this skill**)

The engineering rules' higher authority is still `CLAUDE.md`; the higher authority for GPU launches is still `.claude/skills/gpu-run/SKILL.md`.
**This skill does not launch GPU tasks itself**: any step that occupies a card is always handed off to gpu-run.

**Unified entry point (since 2026-08-02)**: the repo root `run.py` is the running registry for the whole chain
(interpreter dispatch / argument passthrough / GPU tasks only assemble the command and hand it to gpu-run / multi-step recipes).
Check the task list with `python3 run.py list` (do not keep a separate copy in the docs that will go stale);
`show <task>` / `selfcheck` also go through it. This skill's command table is still
the authority for parameter details; which interpreter is used is decided by the run.py registry. **Any extension must, in the same
commit that changes the code, hook the new script/new cell into the run.py registry**
(the sole source of truth for the training-cell table is its `CELLS`,
`ops/launch_probe.py` imports from it; **the sole source of truth for the eval-cell table is its `EVAL_CELLS`**,
`ops/launch_eval.py` only imports it and does not keep a second copy). Only when `selfcheck` passes does it count as complete.
This rule stands alongside the Phase E write-back, neither one can substitute for the other: the skill records the process and the pitfalls, run.py records how to run it.
Warning: `run.py show <task>` also enforces the dirty-tree gate for **launch-type tasks** (a non-empty
`git status --porcelain` refuses to emit the command; `--allow-dirty` lets it through). Emitting the command is not a backdoor around the gate.

---

## Phase 0: Pin the batch (nail down these five variables before touching anything)

| Variable | Example (this round, c1) | Basis for setting it |
|---|---|---|
| `<BATCH>` | `c1` | run_id prefix, one per batch, consistent across all four places in the chain |
| `<ENV>` | `appworld` | appworld / bfcl / tales, decides the event-extraction regex |
| `<MODELS>` | `q35 q36 gptoss` | the agent models being probed, **never merge same-family models** (q35 != q36) |
| `<CELLS>` | `ctool cgen cparam` | the three causal-line cells: judge the tool name / write the whole call / given the tool name, fill in only the parameters. The m-line (mtool/mext) has been retired since 2026-08-21, both cells remain in CELLS and can still be launched individually. Three base tiers `--base qwen/qwen17/qwen4`, two training methods (full-parameter / `--lora`, since np821), **one batch runs only one base tier plus one training method**, both are written into the batch prefix (extending §3.4, stage-commands §3.2) |
| `<DATA_ROOT>` | `pipeline/data/aw_official_v1/` | the dataset version directory, **change the convention and you change the version number** |

Four of these five variables can be extended; each one's change checklist is in `references/extending.md`:
new model §1, new environment §2, **new cell (new training method) §3**, **new split method §4**.
Extending any of these means the wrap-up must go through **Phase E, writing back to this skill**.

As soon as they're pinned, do three things immediately:
1. Go through the `DATA.md §7` checklist (eight items, each one corresponds to a pitfall already hit).
2. Write a batch plan to `plans/<date>-<batch>-plan.md`, stating clearly what question this batch is meant to answer.
3. Confirm `<DATA_ROOT>` is a **new directory**: not one byte of the old dataset gets touched (G hard rule).

Ready-made examples exist, just adapt them, don't write from scratch:
annotate config `pipeline/configs/aw_q35.json`, collect manifest `pipeline/collect/manifest_w0.json`,
placement table `ops/c1_placement.json`.

> Deciding whether to go through the whole chain: only changing model/dataset → whole chain; only filling in a few cells → go straight in at Phase C.

---

## Phase A: Collect (occupies big cards, wall-clock 3-5h)

**This whole stage is handed off to the gpu-run skill**; this skill is only responsible for giving it the correct input and acceptance criteria.

1. Generate the launch scripts: `python3 run.py gen-launch --config <manifest.json>`
   (pure CPU, only generates, does not execute; produces `launch_servers.py` / `launch_clients.sh` / `MANIFEST.md`)
2. **Dispatch gpu-runner** to bring up the services and send the clients. The ceiling on the service side is tokyo108's six big cards:
   27B weights are 54G, gpt-oss is 63G, and A6000's 48G can't hold them, so it's always one instance per card.
3. Gate **G3 service health** (all six green before ramping up volume) → **G4 one-task smoke per model** → ramp up volume.
4. For the model with the longest pole (the one with the most tasks), open the client concurrency one notch higher to even out the wall-clock across all three.
5. Wrap-up gate **G6 completeness** (file count matches **task count × trajectories per task**, every file's last line is `type:"final"`)
   → **G7 zero VRAM** → `python3 run.py gpu-jobs finish` → `python3 run.py record finish` → commit.

Warning: **multiple trajectories per task** (since np821): the manifest gives `traj_per_task` + `seed_family` (either both are given
or neither is, the lengths must be equal, only recognized when env=appworld). The collector assigns each trajectory a seed in order and
writes it into the trajectory meta one by one; the filename carries a sampling index `appworld_<tid>_r0.jsonl … _r{K-1}.jsonl`
(with `--traj-per-task 1` there is no suffix = the old name, and the output is byte-for-byte identical to the old version). The K trajectories of the same task share the same `unit`,
so they **naturally fall in the same split** and won't leak across splits; the sample count grows by a factor of K. Downstream side effects: the annotate-side config writes
`trajs_per_unit` (gate B uses it to judge "one unit has exactly K trajectories and the indices are all present"). **The inject line hasn't caught up yet**:
`replay_inject.py` / `score_live.py` still look things up by `appworld_<unit>.jsonl`; this needs to be changed first before ingesting a multi-sample batch (stage-commands §7).

Warning: **G5 outdir naming**: it must be the standard name `<env>_<model_key>` (e.g. `appworld_gptoss`);
a non-standard name gets **silently skipped** by the downstream event extraction. This pitfall doesn't raise an error, it just makes the sample count smaller.

---

## Phase B: Write code / edit code (pure CPU, **runs in parallel with Phase A**)

This is the biggest parallelism dividend in the whole chain: get all the code written during the hours collection has the GPUs fully occupied.

- Code-writing order: annotate → eval → each train cell → collect generator → inject checker.
- **Write it all in one pass and then run the acceptance checks, don't test-run against real data stage by stage.**
- Dispatch subagents to build in parallel (three concurrent this round; eval is dispatched later because of its import dependency).
  The standard structure for a task brief is under "How to dispatch work" below.

At the end of this stage there are two reproduction acceptance lines, **failing to pass either means Phase C is off-limits**:

| Gate | What it checks | Criterion |
|---|---|---|
| **G8 ACCEPT_V3DIFF** | feed the new annotate code the old trajectories | compare all nine fields entry-by-entry against the old dataset, the mismatch count is **all zero** (run once for each environment) |
| **G12 ACCEPT_EVAL** | feed the new eval code the old artifacts | the three blocks temperature / chosen_theta / test_frozen are exactly identical, the report is written to a temp directory and doesn't touch the old files |

These two gates are the bedrock of the whole pipeline's credibility: **new code fed old data must reproduce the old numbers**,
otherwise none of the new numbers that come after can be compared against history. See `references/gates.md §2` for details.

---

## Phase C: Build the dataset → smoke → train → eval

### C1 Build the dataset (CPU)
Run `build.py` + `param_label.py` once per model (commands in stage-commands §2).
Gates: **G9 task-list line count** (note the task-list files have no trailing newline, so `wc -l` will each read 1 short),
**G10 same tasks across three models** (the train split's unit set must be exactly identical across models, otherwise they can't be compared side by side), **G11 label_call spot check**.

Warning: **the three task lists must be pairwise disjoint, this must be verified by hand**: `build.py` has zero tolerance for "a unit is not in any task list"
(exits with 1), but stays **silent** about "a unit is in two task lists at once": it processes them in train→val→test order and
the later write overwrites the earlier one, so test wins. Overlap silently breaks the train/test boundary, while the report still comes out and the exit code is still 0.
When changing environments, run a `comm` comparison across the three task lists first.

### C2 Smoke each cell (occupies a card, hands off to gpu-run)
Gate **G14**: each cell in `CELL_ORDER` runs `--smoke` once (cgen/cparam's **current training script**
`train_causal_share.py`'s `--smoke` takes the top N events sorted ascending by the full event's token count: 40 training
events / 16 eval **events**, not dependent on `SEED`, not a random draw; the old row-by-row scripts, launched via
`train-cgen-rows`/`train-cparam-rows`, still randomly draw 500 training / 200 eval **instances** according to each script's own `SEED` constant
(the three causal cells use 42 since np821, the two mbert cells still use 20260729);
ctool draws 200 / 80 **events** randomly the same way; every cell is 1 epoch,
with no step ceiling. The retired mtool/mext quota is also 500/200 instances, for mext this is at the **parameter-instance level**
not the sample level, kept on file for reference), the criterion is that `train_log` has both start and done, and the checkpoint can be saved and read
(Warning: the item "is loss decreasing" cannot be judged at smoke scale: a step record is only written every 50 gsteps,
and smoke has only a dozen or so gsteps total, see the G14 row in gates §1).
ctool additionally has **G13 alignment check**: run `--align-only` alone first, FAIL means `exit 2`
(cgen/cparam's current training script `train_causal_share.py` has its own separate set of alignment checks, randomly draw
6 events, compare per-row loss against the old row-by-row trainer, fp32 per-row ≤ 2e-5, per-token ≤ 3e-4, it also has
`--align-only`, writes `<out>/ALIGN_CHECK.json`, FAIL likewise `sys.exit(2)`).
**If smoke fails, ramping up volume is not allowed**, not even once.

The small-scale entry points for every stage in the whole chain (collect's `--n`/train's `--smoke`/eval's `--limit`/inject's `--limit`/
live run's `--n`) are summarized in `MAP.md` §0.5's smoke summary table (surveyed 2026-08-21): after changing code, pick
the corresponding row and run it once before ramping up volume; on the eval side, `eval-tool-* --limit` may only be used against
`--run` directories whose name contains smoke (the truncated logits/REPLAY_REPORT get written into `--run`, a real run must never be touched by it).

Warning: **the tree during the smoke phase is often dirty** (the code was just changed and hasn't been finalized): to emit the command use
`python3 run.py show <task> --allow-dirty` or `python3 run.py launch-probe smoke … --allow-dirty`.
Smoke artifacts aren't kept on file, don't go into `runs.jsonl`, and aren't bound by the "HEAD must be able to trace back to the code" constraint.
Rerunning the same smoke also needs `--force` (the smoke directory name is deterministically derived from the batch/model/cell,
the second run gets blocked by the "an out with an existing `train_log.jsonl`" guard).
**Before the formal launch (C3) you must commit**, that gate must not be papered over with `--allow-dirty`.

Warning: **passing smoke doesn't mean this card can hold the full volume** (measured on np821): smoke only samples 500 instances,
and doesn't hit the kind of long-sequence combination that shows up in the full volume's first batch, while the VRAM peak is set by the
**longest sequence within the batch**. np821b17's cgen smoke finished on a 48G card at a peak of 44.1 GiB, but once the full volume was launched
it OOM'd on the very first backward pass six minutes in (gates §3.9). Rule of thumb: **if the smoke peak is within ~10% of the card's capacity, treat it as not fitting, and go straight to a bigger card**.
The measured peak table for the four configurations (base tier × training method × whether `--grad-ckpt` is on) is in stage-commands §3.1,
check it first when picking a card, don't guess from model size; the watershed for whether it fits is gc, not how big the model is.

### C3 Batch training (occupies cards, hands off to gpu-run)
`<MODELS>` × `<CELLS>` are all independent, **launch them all in parallel at once**, wall-clock is roughly the duration of a single run.
Before launching: **G1 clean working tree** (commit first; run.py treats this as a **hard gate** for launch-type tasks,
it refuses to emit the command even for `show`, only `--allow-dirty` lets it through) → **G2 actually probe for a free card** → launch →
**G16 dual registration**, launch writes all three places automatically; the hand-rolled/register backfill path still exists, missing it still counts as a violation
(one command `python3 run.py launch <task> ...` does all three registrations, the ledger + `record.py start` + RUNMETA;
a hand-rolled launch has to backfill `python3 run.py gpu-jobs register ...` + `python3 run.py record start ...` itself).

Two new behaviors (since 2026-08-02) relating to "training a second time into the same `--out`": every training cell now has `--force`,
**without it, if `--out` already has a `train_log.jsonl`, training is refused outright** (to prevent two runs' artifacts from getting mixed into the same
`best/`); once `run.py launch-probe` / `launch-eval` launches successfully, it automatically writes
`RUNMETA.json` into the artifact directory (written by the first step of `register_all`, the receipt has a line `RUNMETA: <path>`;
before 2026-08-26 the receipt's line `WARN no --outdir given, RUNMETA not written` was a false alarm, backfilling by hand based on it
would leave duplicate entries, this has been fixed), only a hand-rolled launch needs to backfill it itself with
`python3 run.py runmeta <outdir> --cmd '<command>'`.

Write down a placement table `ops/<batch>_placement.json`, with host/gpu/extra params pinned per cell
(`--base` / `--lora` / `--grad-ckpt` are all in extra, the placement table is the source of truth for these three);
this way, re-launching a single cell doesn't need re-deriving the card assignment.

Warning: **relaunching a single cell must not be done by relaunching the whole placement table** (measured on np821): a cell that has already finished
gets instantly rejected by the "out already has `train_log.jsonl`" guard, but **the registration was already done before the guard kicked in**:
that already-finished run gets a fake RUNMETA entry added, and its run_id gets stuffed back into the active ledger, requiring a manual cleanup. To relaunch a specific cell, write a temporary
placement table **containing only that cell** and keep it outside the repo, and update that row in the official table with the new machine placement for the record (stage-commands §3,
extending §5 #24).

**Each invocation of the driver `run.py pipeline`'s training stage only launches one batch, the four batches are strictly serial**; a launched batch keeps a marker
and doesn't get relaunched; to parallelize across batches, hand-launch the rest yourself with `run.py launch-probe full --batch <batch>`
(the same registration code path), once a hand-launched batch finishes, the driver still recognizes it (its criterion is `best/` existing plus
`train_log` having done). See stage-commands §6 for details and the two kinds of completion criteria.

### C4 Eval (**must be serial internally, this is the only stage with dependencies**)

```
Eval the tool cell first (ctool; also mtool before the m-line was retired) ── produces REPLAY_REPORT.json + logits_test.pt
                    ↓ provides the temperature and the trigger point θ
Then eval the parameter/call cells (both cgen and cparam consume the same model's ctool; mext consumes mtool's)
```

**Two-tier strategy**: take `--risk 0.05` first; if theta comes out null at that tier, fall back to `--risk 0.10` and mark it explicitly in the report;
if both tiers have no solution, **record N/A**: don't loosen the risk target, don't borrow another cell's trigger point (both break the convention, see gates §3.4).

No need to wait for the whole training batch to wrap up: **wrap up each cell and dispatch its eval as it finishes** (dispatch continuations to the same subagent with SendMessage).
This works the same way for batches run by the driver: **the completion criterion for the three eval steps only looks at artifact files, not launch markers**,
so when training isn't fully done, just use `run.py launch-eval` to evaluate the finished batches first; once the report lands, when the driver
reaches that step it will recognize it as complete. Two gates go with this: **G23**, a hand-launched eval **must not have the driver invoked while it's still in flight**
(the report hasn't landed yet, and it has no launch marker of its own, so `e2_call` will launch that batch again, since it doesn't check the ledger);
**G24** see C5. For how to estimate the time cost see stage-commands §4.5 (the ctool tier scales with the cut-point row count, the call tier
scales only with the number of events triggered by theta).

### C5 Matrix summary
`python3 run.py matrix --runs-dir ... --out ... --risk 0.05`
Produces one table for each of the two tiers. Warning: this script has three display limitations (N/A displays as PENDING,
the table fixedly reads a single risk tier, the parameter cell's two columns read unconditionally and may mix tiers),
**quoting the matrix table always requires a written explanation alongside it**, don't let the reader misread it.

**G24: the matrix for a batch must not be produced before that batch's call-tier reports are all in**: the driver's `m1_matrix`
skips as soon as it sees `MATRIX_<batch>_r{0.05,0.1}.md` already exists, so a prematurely produced table carrying PENDING will
stay around forever, and running it again later won't regenerate it (extending §5 #23). If one has already been left behind, delete those two md files and regenerate.

---

## Phase D: Wrap-up (six mandatory steps, none may be skipped)

1. **Record the numbers**: one `python3 run.py record finish --metric ... --conclusion ...` per run.
   (Warning: the three record.py syntax pitfalls are in gates §3.7)
2. **Record the direction**: if the conclusion changes any judgment in `WORKPLAN.md` → append an entry to `TIMELINE.md`.
3. **Record the convention**: write the dataset's construction method and settings into `DATA.md` (**settings only, no conclusions**).
4. **Release**: kill every tmux session, confirm zero occupancy for this project across all three machines with `nvidia-smi`.
5. **Retire the job**: `python3 run.py gpu-jobs finish` for every task, clearing the ledger. (If the session is still alive,
   or the ssh probe fails and can't tell whether it's dead or alive, it fails closed and refuses; add `--force` once you've confirmed it should be retired.)
6. **Commit**: code + `ops/runs.jsonl` + `RESULTS.md` + the report `.md`,
   with `<BATCH>` and the key numbers in the commit message.

---

## Phase E: Write back to this skill (**mandatory if the pipeline was extended, not doing it is the same as not doing the work**)

Phase D settles the numbers for this batch; Phase E is what saves **the next batch** from stepping on the same problem again.
The skill is a living document: use it once without writing back and it rots once. The next person to invoke it (quite possibly you)
will walk in carrying an old map that's missing the new cell, the new environment, the new pitfall.

### Trigger conditions (any one of these means writing back is mandatory)

1. Added a new model / new environment / new cell / new split method
2. Changed any hard-coded convention (even just loosening a threshold)
3. Added or changed a script interface (added a flag, changed a default, changed an artifact path)
4. **Hit a pitfall this skill hadn't recorded**, especially the kind that "doesn't error, the numbers are just wrong"
5. Established a new gate

### How to write back

Go line by line down the table in `references/extending.md §6` and check each off; it spells out
"what you did → which document's which section to update → what content to update". Three hard rules:

- **New gate numbers pick up from G25**, G1-G24 are already taken, do not reuse an old number (SKILL.md references them by number).
- **Distinguish "this belongs in the skill" from "this is a one-off thing for this batch"**: the criterion is **whether the next person will run into it again**.
  "gptoss doesn't fit on an A6000" goes into the skill (a hardware constraint that holds long-term);
  "in batch c1, q35's theta was 0.85" does not (that's this batch's result, it belongs in RESULTS.md).
- **Write back together with Phase D's commit, don't leave it for "later"**, leaving it for later means forever.
  Write the commit message as `skill: <what changed> -- triggered by <batch>`.

### Two self-checks after writing back

- For a newly added section, does SKILL.md have a path pointing to it? (An orphaned document is the same as not existing.)
- Do the referenced section numbers/gate numbers still line up? (`grep -n '^#' references/*.md` scans it in one glance.)

---

## How to dispatch work (the core methodology this round)

**The main conversation only does four things: dispatch work, judge acceptance, git commit, and keep the task ledger.**
All the actual doing (writing code, running commands, launching, evaluating, bookkeeping) is handed off to subagents.

| Work | Who to dispatch | Notes |
|---|---|---|
| Write code / bookkeeping / stocktaking | `general-purpose` (opus) | if the task is clear, use opus, don't put it on Fable |
| Launching and evaluating | `gpu-runner` | probe cards → smoke → `launch` (auto three-way registration + liveness check), start to finish |
| Long-task monitoring | `job-monitor` | read-only; kill recommendations go in the report and are decided by the main conversation |

**Continue dispatching to the same subagent with SendMessage**, so context doesn't get rebuilt (this round the launcher was re-dispatched 3 times, the evaluator 6 times).

Standard structure for a task brief (five sections; leave one out and someone will go off track):
1. **Which sections of which spec to read first** (and state that "when the spec and the brief conflict, the spec wins")
2. **Hard conventions**: tabulated, cell / script / interpreter / path, one row per cell
3. **Work discipline**: don't touch git, read old files only, don't modify other people's scripts,
   if it crashes read the traceback first, don't just retry blindly more than twice, run `py_compile` once in each of the two environments
4. **Acceptance criteria**: what counts as passing, what counts as failing
5. **Reporting format**: require it to list **its own autonomous decisions** (this is the main way to catch drift)

Warning: numbers reported by a subagent need to be spot-checked. This round there was a case where it wrote "difference < 2e-5" from memory,
while the downstream bookkeeper who actually read the file found it was 2.0027e-5. The rule that **numbers must be read from the file** needs to be written into the task brief.

---

## Hard rules

- **Stop the moment a gate fails**, no "let's just run it and see". If smoke fails, don't launch; if alignment FAILs, stop the whole line and wait for a ruling;
  if eval has no trigger point, SystemExit rather than forcing a theta.
- **Not one byte of old data or old numbers gets touched**; every new artifact goes into a new directory with a new version number.
- **Test is frozen once.** Once theta is chosen on val, the numbers on test get reported as-is no matter how bad they look,
  that ugly cell is exactly the thing the matrix is meant to measure.
- **run_id is consistent across all four places**: the data directory name / tmux session / ledger name / commit message.
- `RESULTS.md` is a rendered artifact, don't hand-edit it; `runs.jsonl` is append-only; the ledger is only touched via `python3 run.py gpu-jobs register/finish`.
- **Commit before launching**, with a dirty working tree the HEAD stored in the record can't be traced back to the real code.
- **The only situation where stopping to ask the user is allowed is "overturning a premise"**: the target split simply can't be run at all,
  the weight path is dead, the acceptance line keeps failing repeatedly. Everything else is handled automatically (see gates §4 for details).
  Before stopping, wrap up whatever has already been completed cleanly.
