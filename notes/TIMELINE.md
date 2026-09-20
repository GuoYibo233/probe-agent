# TIMELINE: direction decision log

> **This file only grows, never gets edited in place**, new entries go on top. It is not a
> plan document, it is "when and why we changed our mind."
>
> Three files divide the work, do not mix them up:
> - `WORKPLAN.md` = current plan, gets overwritten and rewritten → answers "what to do now"
> - `TIMELINE.md` = decision history, never overwritten → answers "why we decided this at the time"
> - `RESULTS.md` = the experiment number summary table (auto-generated) → answers "what the data looks like"
>
> The full history of the old phase (2026-07 ~ 2026-08-02, the hidden-state probe speculative
> execution tool-call line) lives in git snapshot commit `b1f5b9c` and earlier commits; this
> file does not trace back further than that.
>
> The 7 entries from 2026-08-02 to 2026-08-18 were archived as ancient memory on 2026-09-12 and
> moved to `plans/archive/TIMELINE-2026-08-02-to-2026-08-18.md`; read them only when gyb
> explicitly says "check ancient memory" or names that file.

## 2026-09-20 The from-zero rewrite replaces the old tree; `legacy/` deleted

- Trigger: gyb's seven principles (Part 1 of `notes/plans/2026-09-14-structure-from-zero.md`)
  and the 2026-09-13 to 2026-09-17 renewal discussion.
- Decision: the old tree is replaced by the 31-file tree of
  `notes/plans/2026-09-14-structure-from-zero.md`, whose interfaces are
  `notes/plans/2026-09-17-contracts.md` and whose build order was
  `notes/plans/2026-09-17-construction-plan.md`; six stages, one command
  (`run.py`), one experiment is one setting, a run directory is named by its key,
  `--debug` runs any setting tiny, `eval/` reads only disk.
- Counts: about 60 Python files under the old code directories become 31; the old
  four-ledger layout becomes five record layers, with `jobs/runs.jsonl` and
  `jobs/RESULTS.md` beside the registry.
- What is retired, by name: the resident sampler, its web page
  (`localhost:8377`), the sampling history, the incident agent, the autopsy, the
  escalation line's automatic consequence, the one-refire-per-piece quota, the
  `run.py` task registry (`TASKS`/`RECIPES`/`list`/`show`/`recipe`/`status`),
  `MAP.md`, `ops/jobs.json`, `RUNMETA.json`, the presets, the offline replay
  line, the chat-endpoint collection path, and the five non-AppWorld
  environments.
- What this invalidates: every command in the pre-rewrite gpu-run and
  probe-pipeline skills; the `notes/CONTEXT.md` entries listed below; every
  experiment number produced before the rewrite keeps its old provenance and is
  not re-derived (the old `RESULTS.md` goes with `legacy/`, and the tag is
  where it is read).
- The glossary debt, listed for gyb: `notes/CONTEXT.md`'s entries *Sampler*,
  *Window*, *Escalation line*, *Incident agent*, *Autopsy*, *Incident record*,
  *Sampling history*, the sampler's half of *Verdict*, *Ledger* (now the
  registry, `jobs/runs.jsonl`), *Refire*'s quota sentence, *shardable*,
  *Monitoring parameters* (now `registry.DEFAULTS`, 8.5) and *chat baseline*
  describe machinery that no longer exists. This entry names them; the rewrite
  of `CONTEXT.md` is gyb's.
- Where the old tree is: tag `checkpoint-2026-09-17-before-from-zero` on `main`,
  and commit `647dc45` on this branch.
- Acceptance that was actually run: three end-to-end `--debug` walks, each with
  its printed run-directory key, and `run.py selfcheck` exit 0.
  - `baseline gpt_oss_120b_appworld --debug`: sample=`96de225de2b4`,
    score=`20eaad1deae5`
  - `train_probe ctool_qwen3_0pt6b --debug`: sample=`96de225de2b4`,
    build=`b565f5ab1b94`, train=`0f3e343f0eca`, eval=`b5999ae061f9`
  - `train_probe cgen_qwen3_0pt6b --debug`: train=`b45633250e8b`,
    eval=`e5d6ba9d8c7b`
  - `train_probe cparam_qwen3_0pt6b --debug`: train=`5b398c217e13`,
    eval=`ef9644a7e92f`
  - `inject probe_p1_e1_theta_0pt80 --debug`: inject=`c96e48a8be3d`,
    score=`d49397cf4dd9`; rerun with `inject.fire_nth_cut=1`:
    inject=`27d4bad1b70a`, score=`a4e05cb2fbe3`
  - `run.py selfcheck`: `selfcheck: 31 python files, 0 problems`

## 2026-09-12 The whole repository is translated to English in one pass, ledgers and archive included

- Trigger: gyb ordered "make the whole repo English" and confirmed the same day that Chinese in
  chat never changes the language of a file. Before the pass, 192 of 456 tracked files carried
  Chinese, about 10,500 lines; Python code was already English apart from three pattern strings.
- Decision: translate everything in place, including the three files that rules otherwise protect
  (`TIMELINE.md` append-only, `ops/runs.jsonl` append-only, `RESULTS.md` rendered, plus the
  `ops/jobs.json` body), the ancient-memory archive, `talks/`, `learn/`, and `.scratch/`. This
  entry is the record of that one-time exception; from here on the append-only and
  never-hand-edit rules hold again. `RESULTS.md` and `plans/STATUS_kvshare-train.html` were
  re-rendered from their translated sources, not edited by hand. The status renderer's fold
  labels became English ("How it was done" / "Why this design counts" / "One real sample";
  stop prefixes "Experiment results" / "Worth noting" / "Index"). Verdict names in documents
  were aligned to the strings in `ops/verdicts.py` (healthy / warming up / slowed /
  suspected stall / dead / done).
- Two Chinese remnants are kept on purpose: the trigger-phrase clause at the end of each skill
  and agent `description` (it routes Chinese requests to the right skill), and the original
  Chinese term in parentheses after each `CONTEXT.md` glossary head term (the map from chat
  vocabulary to canonical English). Binary talk assets (`talks/20260809/*.png`, `slides.pptx`)
  were not touched.
- Method: fifteen sonnet subagents, one per directory batch, each verifying a zero count of
  Chinese characters on its files; the two live ledgers were rewritten through a script that
  re-reads the file at apply time and writes atomically under the ledger lock, because the
  sampler and another session's launch were writing them at the same time.

## 2026-09-12 research-loop split out into its own repository

- Decision (user): research-loop leaves new1 entirely and becomes the standalone
  project `/home/y-guo/research-loop` (git-initialized, first commit `b9bb7d3`).
  Moved: the plugin tree `research-loop/`, the design source
  `plans/research-loop-parts/` (frozen-part checks re-pinned to the new repo's
  initial commit), the seven live plan documents
  `plans/2026-09-04/05-research-loop-*.md`, the ten research-loop items in
  `plans/archive/`, `.scratch/research-loop/`, and `review/` (spec review and
  advisor notes). The project memory moved to the new working directory's key. Test suite green in the new location
  (unittest, exit 0) and the parts checks pass there (0 errors).
- History stays here: everything up to new1 commit `c030702` is the pre-split
  record; the new repository starts fresh and names this repository as its
  ancestor in the initial commit message.
- new1 keeps zero research-loop content. MAP.md section 3.5 and the CLAUDE.md
  mention of research-loop's Chinese-parsing scripts went with the move;
  construction step 7 of the old plan (`rl init` hooking research-loop into
  new1) is obsolete in its old form and gets re-scoped on the research-loop side.

## 2026-09-12 Ancient memory rule established: everything before 2026-08-20 is archived, not read by default

- Decision (gyb): everything before 2026-08-20 is archived; the archive area `plans/archive/`
  is named "ancient memory." The 7 entries from 2026-08-02 to 2026-08-18 in this file were
  moved into `plans/archive/TIMELINE-2026-08-02-to-2026-08-18.md`, unchanged character for
  character (verified with a diff, byte-identical); the plan files from before 2026-08-20 were
  already moved into `plans/archive/` in the 2026-09-08 archiving pass (commit 1398466).
- Reading rule (written into CLAUDE.md): read `plans/archive/` only when gyb explicitly says
  "check ancient memory" or names an archived file; otherwise do not read it, cite it, or use
  it to answer questions. When an answer would need that batch of records, say plainly "the
  basis is in ancient memory" and stop, waiting for gyb to speak.
- What stays untouched: `ops/runs.jsonl` only grows and is never edited; `RESULTS.md` is a
  rendered artifact and is not hand-edited, and the pre-2026-08-20 number rows stay where they
  are; entries in `METHOD.md` and `CONTEXT.md` carrying a date stamp like "decided 2026-08-08"
  are active rules, not ancient memory.

## 2026-09-12 Injection format becomes an experiment axis: four arms, whole-task scoring only, p2 relaxes the no-special-token rule

- Trigger: gyb wants to test how a prefetched result is put back into the agent's token stream. The
  2026-08-18 single-step comparison (ten arms, correct result known in advance) is set aside: "i dont
  want these old results, abandon these result". Scoring is whole-task success and the token account
  only: "in test, we never see if a single tool call is right, we only care about the final result".
- Decisions (gyb, this day): the model always gets an explanation; two placements stay in play,
  inside the thinking (P1) and after an end-of-thinking token as a message from a sender named
  prefetch (P2); explanation is crossed with placement (inline every time, E1, or once in the system
  prompt with a marker inline, E2), giving four arms p1_e1 / p1_e2 / p2_e1 / p2_e2. Execution status is
  S1-rollback only: the call runs in a saved-then-restored world and the text says it already ran.
  Commit-and-keep and preview-not-executed are dropped (real side effects on wrong predictions; no
  round trip saved). P2 writes control markers, so R1 and R2 of `METHOD.md` are relaxed for this
  experiment only.
- Implementation (same day): `pipeline/inject/inject_format.py` holds the five formats (`note` keeps
  the pre-existing text as default) as plain strings; `live_appworld.py --format` selects one; the
  probe server's `/encode` gains `special` (control markers stay text unless asked for) and echoes
  `encode_special` in `/health`; `score_live.py` carries `format` into rows and the table. Judge
  test: the literal P2 tail encodes to exactly the harmony library's rendering of a tool-authored
  analysis message from sender `prefetch`. `--no-probe --format <e2 arm>` is the control for an e2 arm.
- Not yet run: the probe server has never been launched with np821 weights; the live arms need a
  served ctool + cgen pair and a hand-given θ.

## 2026-09-05 research-loop v2 skeleton version built in one day: five parallel sessions, a proxy-decision record, open questions 5 and 9 got answers

The three things gyb decided on 2026-09-04 set the direction for this round: deliver a "skeleton version" today (every component file exists, the parts already decided pass tests green, undecided parts are marked `PENDING(...)` in the code, the master document and the manual are drafts); write the code to the new sync-inbox decision and keep a separate comparison list for the final check; open question 5 (who a sub-session's ledger writes count as) and open question 9 (a background sub-session's lifetime) were named for testing; ground truth is layered (what a machine can check belongs to code and tables, discipline belongs to the master document and the manual, and a volume falls back to being a source of history only after its final acceptance check). gyb's own words were "go with all the recommended options, and this time open a separate record for decisions made without me knowing; when something needs me to resolve it, go with your own recommendation and I'll review it when I'm back," and the proxy-decision record was set up from that (`plans/2026-09-04-research-loop-proxy-decisions.md`, D-01 through D-38).

On the mechanics, gyb `/fork`ed the coordinating session directly into four helpers on 2026-09-05, base, text, verification, and review, and all five sessions edited the same tree (new1's worktree isolation for background sessions is turned off); the protocol is in `plans/2026-09-05-research-loop-fork-protocol.md`: split people by directory, each only adds their own paths, messages carry signals only, anything needing a ruling goes to the coordinator. The result was 109 files in the plugin tree, 20 test files with 250 cases all green (HEAD ba55ccc), 62 distinct `PENDING(` markers, reported in `plans/2026-09-05-research-loop-build-report.md`.

Where the plan changed: a sub-session's identity no longer relies on a state file (the gap found in testing at line 118 of doc 06 held up); it changed to a write-permission hook that injects `RL_AGENT_TYPE` and `RL_AGENT_ID` in front of Bash commands, `rl` checks the injection first and the state file second, and a sub-session logs a separate row with `agent_id` in the sessions ledger (D-15, verified in `plans/2026-09-05-research-loop-verify.md`); the plugin body is English only, and the pending marker has two forms (D-09); a dispatching session in print mode waits at most 600 seconds for a background sub-session by default, written into the discipline rather than built as a mechanism (D-23). Not done: step 7, step 8, the watchdog, and the six stress-test scenarios. Waiting on gyb: the review of D-01 through D-38, whether grants stay or go, write permission for issues in `run`, which session's commit gets logged in the ledger, and the permission rules after injection.

## 2026-08-29 Second round after gyb's ruling: the four open items become switchable parameters (the default is the recommended value), cgen's learning rate got a 12-run sweep, the code default learning rate is unchanged

gyb's own verdict on the night of 2026-08-28, on the nine open items in the first-round report: "The learning rate needs sweeping. Skip flex_attention. For the rest, give me several options each; I don't have time to review by hand right now, so implement the option code first, switchable by parameter, and I'll compare later. Verify it once it's implemented, then gpu-run a learning-rate sweep on the recommended configuration"; "leave the other one for later, keep it as is" refers to the packing optimization that cuts padding waste.

What changed (spec `.scratch/kvshare-train/spec.md` section 16, tickets 07 through 12, code endpoint b3875a7):
- The three eval scripts gained `--overlong {left,skip,drop-event}`, defaulting to `left`, the current behavior; all three `logits_*.pt` modes now write the full row count, with excluded rows marked in `.meta.json`, and cgen / cparam read that to drop candidate rows.
- The new trainer got generative evaluation back, `--gen-eval 200 --gen-eval-at last` (done only at epoch end, matching the old trainer's once-per-epoch cadence); the `eval` event carries `val_exact_call / val_exact_params`; the evaluation segment now emits heartbeats.
- All five alignment-check thresholds became parameters (defaults unchanged), adding `--align-rule {abs,rel,both}` and `--align-rel-tol 1e-5`; `ALIGN_CHECK.json` now writes the full relative quantities regardless of rule; ctool got the same `--align-rule` addition.
- The memory probe gained `--mem-probe-pick {tokens,cost,loop}`, defaulting to `cost` (it enumerates the physical blocks in epoch 0 of this run and picks three: most tokens, most loss positions, largest normalized sum); the peak counter resets after the probe returns; `.backward()` is wrapped inside the kernel context (grad-checkpoint recomputation happens during the backward pass; wrapping only the forward pass crashes with `CheckpointError`).
- `run.py` gained `sweep-lr` (`plan` produces the list, `report` collects the table); output goes to `pipeline/runs/sweep/`, run_id has four segments `ks828<tag>_gptoss_cgen_lr<lr>`, and it does not enter the matrix.
- flex_attention and the packing optimization are not done; np821 retraining, correcting the TIMELINE convention, and reclassifying the implementation are not code changes, and the options are listed in the report.

Learning-rate sweep (decisions 27, 29, 30: cgen cell, four base-model configurations x three rates, 1 epoch, 4 evaluation points per epoch, full-parameter grid {1e-5, 5e-5, 2e-4}, LoRA grid {1e-4, 5e-4, 2e-3}; card assignment: l4 with checkpointing on H100, b17 without checkpointing on H200 then handed to l17 once done, b06 with checkpointing on Ada, all with a 16384 token budget; all 12 runs done, numbers in `pipeline/runs/sweep/SWEEP_REPORT.md` and `ops/runs.jsonl`). Epoch-end val_ce: b06 0.1730 / 0.1857 / 0.2470, b17 0.1636 / 0.1750 / 0.2269, l17 0.1826 / 0.1647 / 0.2138, l4 0.1671 / 0.1547 / 0.6510 (each ordered from low to high learning rate). The lowest-loss rate for each of the four configurations: full-parameter 1e-5 (the lowest rate on the grid for both full-parameter configurations, with the endpoint still falling), LoRA 5e-4. The ranking of epoch-end 200-line greedy generation val_exact_call matches the val_ce ranking. Whole-run step peak against the `cost` probe: b17 102.336 vs 102.29 GB, b06 22.427 vs 22.005, l17 81.655 vs 81.654, l4 33.088 vs 32.964.

Why the default did not change (decision 31): the learning-rate default is a convention locked by `invariants.md`; changing it would make old and new numbers incomparable and would require touching invariants and changing the batch prefix; gyb said he would compare later, so the sweep results go only into the report table and the write-up, and whether to change it is gyb's call. The best rate for the full-parameter runs fell at the edge of the grid, and helper 2's rule is to sweep one more rate further in that direction: decision 40, b06 and b17 each got one extra lr2e-6 run (`ks828b06_gptoss_cgen_lr2e-6` on Ada, `ks828b17_gptoss_cgen_lr2e-6` on H200), launched between 02:49 and 02:50 on the 29th, LoRA not extended; result: b06 lr2e-6 epoch-end val_ce 0.2157 (1e-5 is 0.1730), b17 lr2e-6 0.2046 (1e-5 is 0.1636); the lowest point for both full-parameter configurations is still 1e-5, with both neighbors higher; the table of 14 runs is in `SWEEP_REPORT`.

Other facts settled this round: the fp32 row-by-row alignment gap rises monotonically with base model size (0.6B 5.48e-6, 1.7B 9.06e-6, 4B 1.54e-5), reproducible bit-for-bit on the same card type and shifting across card types (0.6B on Ada is 5.007e-6); 4B carries an explicit `--align-tol 3e-5` in the grid (decision 36). The three `--overlong` modes on np821b06's 4096 output (`--limit 200`) respectively left-truncate 56 rows, drop 56 rows, and drop 133 events; under the smoke output's 8192 cap, none of the 200 rows are overlong, all counts are 0. Decisions 26 through 40 and their rationale are in `.scratch/kvshare-train/decisions.md`, second-round section; the report is in `plans/2026-08-28-kvshare-report.html`, second-round part.

## 2026-08-28 Training convention switches to the cache-reuse trainer: 8192 cap with whole-event drop on overlong, 8 events per update, cgen/cparam 1 epoch, batch prefix ks828

- Trigger: the np821 twelve-cell review (`plans/2026-08-28-plan.md` sections 12 through 14). The
  row-by-row trainer for cgen / cparam treats every cut point of an event as an independent sample
  and recomputes the prefix each time; one 1.7B LoRA cell takes 98 hours on Ada. The val_ce of all 8
  cgen / cparam runs is lowest at epoch 0, while all 4 ctool runs keep rising over three epochs; the
  4096 left-truncation cut 4,956 rows on train (2.66%), and 259 events (6.28%) exceed 4096 in full
  length (`plans/2026-08-28-plan.md` section 4).
- Decision (confirmed by gyb; two of the items, the per-cell epoch counts and the ctool read
  position, were locked on Claude's recommendation with gyb's authorization; from the fifth round of
  step-by-step discussion on 2026-08-28, the original ruling is in
  `plans/2026-08-28-kvshare-draft.md` section 2): an event's full text passes through the base model
  only once, and each cut point's target segment is appended after the shared prefix to compute the
  loss (`plans/2026-08-28-plan.md` section 10.2, idea one); no sample is truncated any more, an event
  whose full text exceeds the cap is dropped whole and counted, and the cap candidate 8192 is fixed
  by smoke testing; 8 events per update (4 events per logical mini-batch x 2 accumulation steps), the
  same convention across all three cells; cgen / cparam run 1 epoch with a full val_ce evaluation
  every quarter epoch, ctool keeps its 3 epochs; tokenization follows the common-prefix rule (each
  row is tokenized the old way, sharing the longest common prefix with the full-text tokens, with a
  separator string plus the target string appended as the target segment); the new and old trainers
  produce identical per-row token sequences position for position; ctool's cut-point read position
  changes to "when a cut point is crossed by a single token and everything after the cut point is
  whitespace, read that crossing token (for example `."\n\n`), otherwise read the token before it";
  the learning-rate default stays unchanged, with sweeping left until after the smoke test.
- Implementation (same day; the plan-8-28 session implemented it autonomously under gyb's
  authorization, 22 autonomous decisions numbered in `.scratch/kvshare-train/decisions.md`, spec and
  six tickets in the same directory): a new trainer `pipeline/train/train_causal_share.py`
  (`--mode cgen|cparam`) and a data module `pipeline/train/share_data.py`; the cgen and cparam cells
  in `run.py`'s `CELLS` / `TASKS` now point to the new script, the old row-by-row trainer is frozen
  as an alignment reference and kept available as `train-cgen-rows` / `train-cparam-rows` (its
  output does not enter the matrix); attention uses sdpa's mem-efficient kernel, pinned explicitly
  (flash refuses input with a mask, the math kernel needs 148 GB at L 9,100, and H100 falls back to
  cuDNN by default); ctool drops truncation, with the read-position rule collected in
  `share_data.read_position`. Defaults: all three cells `--max-len 8192`; the new trainer
  `--tok-budget 16384`; ctool `--bs 2 --accum 4`, `--align-tol 3e-4` (previously 1e-4; np821 runs
  had always passed 3e-4 in practice). Runs under the new convention use the batch prefix `ks828`
  (shaped like `ks828b06`).
- Evidence (numbers in `ops/runs.jsonl`, output in `pipeline/runs/smoke/ks828b06_*`): the alignment
  check's fp32 row-by-row loss max difference is 5.48e-6 (6 events, 154 rows, 2,877 target tokens,
  tolerance 2e-5; on H200 the cgen / cparam smoke tests are 5.48e-6 / 9.30e-6 respectively); the
  speed cell `ks828b06_gptoss_cgen_speed_b16k` (H100, 450 events, 20,641 rows) has a cumulative
  rows-per-second of 185.6 / 189.5 / 184.1 at 1,600 / 9,600 / 19,200 rows, versus the old trainer's
  2.76 / 3.26 / 3.97 on the same machine and same row counts (`np821b06_gptoss_cgen`), a 16x speedup
  over the old steady-state 10.6 to 11.6; training memory peak is 60.59 GB (torch's allocated peak
  `max_memory_allocated`, equal to 56.4 GiB, 39% headroom on H100's 93.10 GiB; the reserved peak was
  not recorded, one nvidia-smi sample during training reads 54.4 GiB), the longest-event probe reads
  31.4 GB (same convention); a 24576 budget is 15% slower (end-of-run cumulative rows-per-second 157
  vs 184; the six comparison points are respectively 17.8 / 18.1 / 15.4 / 17.8 / 17.3 / 7.0% slower,
  averaging 16%) with an allocated peak of 80.9 GB, and expandable_segments is 3% slower with no
  gain. ctool: 8192 x bs 4 OOMs on the first training batch on H100 (process memory.used 92.94 GiB);
  bs 2's nvidia-smi memory.used peak is 56,859 MiB (2-second sampling, including allocator cache); the
  8192 cap drops 1 event on train and 3 on val, matching the statistics table in plan section 4
  exactly.
- Relationship to old records: the np821 twelve cells used the 4096-left-truncation /
  32-events-per-update / 3-epoch convention, and those numbers are only comparable within that batch;
  models under the new convention get a separate batch prefix. The change to ctool's read-position
  rule brings the training and offline-evaluation position in line with "tokenize the full text
  once"; the token boundary produced by a live run may still differ from offline tokenization, and
  that is a separate open problem, not solved here.
- Pending (no ruling yet): how the eval side handles overlong events (the eval scripts currently
  read 8192 from `meta.json` as the left-truncation length); the learning-rate sweep; flex_attention;
  the packing optimization for padding waste (28% recomputed on the speed cell's 450-event sample
  under a 16384 budget, not a full-dataset number); the fix for the `--mem-probe` probe
  underestimating the true peak by 6 to 10 GB (ticket 06).
- Added the same day (after final verification): after ticket 06 changed the probe to "build the
  optimizer state first, then run the fullest block through the backward pass twice," the probe's
  underestimate of the whole-run step peak shrank from 9.5 / 5.9 GB to 4.1 / 4.4 GB (16384: 54.38 vs
  58.47 GB; 24576: 76.47 vs the earlier 80.91 GB, from the `mem_probe` event of
  `ks828b06_gptoss_cgen_final_*`), still not matching exactly; this round settles on "assign cards
  using the probe's fullest block x 1.1, then discount further for reserved-memory fragmentation,"
  with whether to change the probe further left for gyb to decide (decision 25). Final verification
  used the final code: the cgen speed cell's six comparison figures are 187.2 / 191.9 / 187.6 and
  187.2 / 206.2 / 156.2, whole-run peak 58.47 GB; the cparam and ctool smoke alignment checks both
  pass.

## 2026-08-28 One single generation convention across the whole line: preset default (temperature 1.0), live runs and controls share the same convention

- Trigger: after the np821 12-cell evaluation wrapped up (`plans/2026-08-26-np821-results.md`), gyb
  wanted to wire the probe into the live-run injection line and look at whole-task performance. The
  live-run line's original default generation settings (`live_appworld.py`'s fallback table and five
  temperature-0.0 presets) and the probe's training data (the nyapass batch, preset `default`,
  temperature 1.0) belonged to two different conventions.
- Decision (gyb): there is now exactly one active generation convention across the whole line, the
  preset `default` (harmony / effort high / temperature 1.0 / top_p 1.0 / max_tokens 8192 /
  start_date 2026-08-06; the seed is assigned per trajectory by the entry point, from the seed family
  42/67/4267/6742). Collection, all three live-run arms (with probe / no probe / probe-but-nofill),
  replay, and control trajectories all use this one convention; the difference between the two arms
  is smoothed against sampling noise by the volume of tasks.
- Implementation (same day, 35 files): `configs/presets/default.json` gained a server section
  (matching the nyapass batch's launcher `envs/runs/nyapass/launch_servers.py`: tokyo108:8103, GPU
  memory fraction 0.92, `VLLM_USE_FLASHINFER_SAMPLER=0`); the eight generation entry points (four
  collectors / live_appworld / replay run / splice run / ident3_gate) now default `--preset` to
  `default`; the temperature setting now comes only from the preset's client section, every literal
  temperature value in .py files and tests was removed, `Chat.__init__`'s `temperature` became a
  required argument, and when a preset's temperature is null, `preset_loader.require_temperature`
  stops immediately and names the preset; the five preset files `gptoss_chat_high` /
  `gptoss_harmony_high` / `gptoss_harmony_medium` / `gptoss_live_high` / `gptoss_replay` were removed
  from the repository (historical values remain in git and in `.scratch/gen-preset/spec.md`);
  `acceptance.py`'s echo-scoring request now carries only model / prompt / max_tokens / echo /
  logprobs. How the probe encodes its own generated call string (cgen / cparam's `do_sample=False`,
  the convention behind the np821 evaluation numbers) is outside the scope of this decision.
- Incidental convention changes (facts, not separately decided): the user-simulator temperature for
  tau2 collection now follows the agent side's preset (1.0); the BFCL handler reads `default`
  (max_tokens 8192 / top_p 1.0 / temperature 1.0) when `NEW1_PRESET_JSON` is not set, and needs to
  point at `gptoss_bfcl_high` for the 16384 tier; the command `gen_launch` builds for qwen-family
  clients carries no `--preset` and falls through to `default` (gpt-oss's harmony format); the qwen
  family needs its own preset opened (api raw, temperature 1.0) before it can be collected again.
- Relationship to old records: the 2026-08-18 numbers ident3_v1 / splice_replay_v1 /
  cmp_chat_noprobe_5 were measured under the temperature-0.0 convention and are only comparable
  within their own batches; the name `gptoss_harmony_high` (the p1 collection convention) from the
  2026-08-21 entry remains in `pipeline/collect/manifest_p1.json` and in the ledger, though the file
  itself has been removed.

## 2026-08-22 np821 cut-point cap ruling: max_bounds stays at 64 (Claude ruled autonomously under gyb's authorization)

- Trigger: the driver's a1_stats stop point (run_id nyapass, after all 1260 trajectories were
  collected). The untruncated cut-point distribution: 15216 events, p50 60 / p90 246 / p99 572 /
  max 842, with 7271 events exceeding 64 (47.8%) and 1408 exceeding 256 (9.3%).
- Decision: keep 64. Basis (the training-split sample count under each candidate cap was computed on
  the spot with the same `boundary_counts` code): keeping 64 gives a training split of 186479 rows,
  4.02x the p1 training split's 46438, landing right at the plan's 4x budget, so all wall-clock
  projections and card assignments still hold as they were; raising it to 128 gives a training split
  of 277594 (+49%), and the two LoRA batches were already at the edge of "won't run"; under the
  per-step equal-weight convention, without truncation the overlong thinking events, only 9.3% of all
  events, would take up about 36% of the samples, and the 64 cap caps any single event's
  contribution; the thinning is near-even sampling that always keeps the final cut point, so depth
  coverage is not lost; the raw trajectories are fully archived, so raising the cap only requires
  rerunning annotation (pure CPU), making the ruling reversible.
- Impact: no convention is invalidated. np821 and p1 share the same cut-point cap of 64; the
  cross-batch convention differences stay confined to temperature, trajectories per task, and
  weighting.

## 2026-08-21 np821's new convention finalized: temperature 1, 4 trajectories per task, per-step equal weighting set as the long-term convention, the whole chain made programmatic

- Decision (gyb ruled the same day, full plan in `plans/2026-08-21-np821-plan.md`): the new batch
  nyanpasu-probtest821's generation settings switch to temperature 1.0, top_p 1.0 (new preset
  `default`, the old `gptoss_default` file untouched); the task list stays AppWorld's official three
  splits, all 315 tasks, with 4 trajectories collected per task for 1260 total; sample weighting
  switches from equal weight within an event, w=1/m, to per-step equal weight, w=1, and this is set
  as the long-term convention: `weight_mode` now defaults to equal weight, and the old convention
  only applies when `per_event` is passed explicitly, with its only remaining use being to reproduce
  the acceptance line.
- The seed changes from a single value 20260729 to the seed family 42, 67, 4267, 6742, used in
  order: the four trajectories are each assigned one in sequence and it is logged into each
  trajectory's meta; single-seed spots inside the pipeline (dataset-split construction, training
  script constants) take 42. The old seed 20260729 still applies only to old configurations and
  reproducing old data; values written explicitly in old configuration files are unchanged.
- Training changes to a four-batch side-by-side comparison: np821b06 (0.6B full-parameter),
  np821b17 (1.7B full-parameter), np821l17 (1.7B LoRA), np821l4 (4B LoRA), with cells ctool/cgen/
  cparam; the machine pool is limited to tokyo107 and tokyo108.
- The whole pipeline is made programmatic as a resumable driver
  (`python3 run.py pipeline --config <batch config>`): each invocation advances one step, a failed
  gate stops it in place and writes the reason into a state file, and the cut-point cap ruling is
  made an explicit stop point.
- Impact: temperature-1 numbers are not comparable to any historical temperature-0 numbers; the
  cut-point cap stays at 64 for collection, with a distribution statistic produced at annotation time
  before ruling on whether to keep or raise it.

## 2026-08-21 The p1 batch's temperature-0 convention is closed out

- Decision: the p1 batch's collection and dataset-building convention (temperature 0.0, 1
  trajectory per task, equal weight within an event w=1/m, seed 20260729) is closed out here; every
  new collection and training batch from now on follows the np821 new convention.
- p1's raw trajectories and the `aw_p1_v1` dataset stay byte-for-byte unchanged; their only
  remaining use is reproducing the acceptance line (rerunning build with param_label and comparing
  byte-for-byte against the old output). Training and evaluation numbers already produced from the p1
  series stay in `RESULTS.md` as they are; no new batches are added on top of this dataset any more.

## 2026-08-21 First training round finalized: 0.6B and 1.7B full-parameter run in parallel on tokyo108, a separate LoRA experiment line opens on the small cards

- Decision (gyb ruled the same day, closing out the SFT discussion): the main line uses full-
  parameter fine-tuning, with the hyperparameters for the three-tier comparison locked to 0.6B's
  current values (lr 1e-5, 3 epochs, effective batch 32, loss computed on the target segment only,
  fp32 weights + bf16 compute); the data-feeding method and precision convention are unchanged, and
  base-model size is the only variable changed this round.
- The first round changes from running only 1.7B to running 0.6B and 1.7B together: two tiers x
  three cells = 6 single-card jobs, assigned to tokyo108's 6 large cards (3 H100 95G + 3 H200 143G,
  all probed free that day). p1 collection occupies two of the H200 cards first, then hands them over
  to training once collection is done, with no time conflict.
- A separate LoRA experiment line opens: tokyo106's 10 A6000 48G cards run the LoRA tier in
  parallel (gyb: try LoRA on the small cards, it can run in parallel anyway). z1's test found 0.6B
  full-parameter OOMs on 48G; what the small cards can run is LoRA. This experiment line does not
  enter the locked-hyperparameter comparison; its value is measuring how much the small-card training
  method differs from full-parameter.
- Batch prefixes: full-parameter `p1b06` / `p1b17`, LoRA line `p1l06` / `p1l17`. run_id has no
  tier segment; the convention "one training batch runs one base-model tier only" continues, and
  different training methods each get their own batch prefix too.
- Rationale: LoRA saves memory but not compute (the forward and backward passes still go through
  the whole base model), so the main line uses full-parameter when large cards are available,
  keeping the same training method as the existing 0.6B results; the hyperparameters are locked first
  to get a baseline, with a comparison round to be added later if self-tuning is needed, so both
  numbers will exist.
- Engineering gap: the three training scripts currently support only full-parameter training; LoRA
  needs the peft dependency added and a `--lora` flag, and when saving, the adapter must be merged
  back into the base weights so the eval side needs zero changes; the implementation and the skill
  write-back are recorded separately.

## 2026-08-21 Probe training changes to three model types x three base-model tiers, the m line stops, a new cparam cell is established, the p1 collection batch is set up

- Decision (gyb ruled item by item the same day): (1) the ModernBERT line (mtool/mext) stops, and
  the probe focuses on the causal line; (2) the causal base model expands from the single Qwen3-0.6B
  tier to three tiers, 0.6B/1.7B/4B, to compare across the three sizes; (3) training splits into
  three model types: judging tool type only (ctool), generating the whole call (cgen), and
  generating only the parameters given the tool name (a new cell, named **cparam**); (4) the first
  round is done on 1.7B first (SFT details discussed separately). The full design is in
  `plans/2026-08-21-new-probe-training.md`.
- Usage convention: comparing two systems, system A = ctool triggers + cgen rewrites the whole
  call, system B = ctool triggers + cparam fills in only the parameters (the tool name comes from the
  classification head). cparam evaluation runs both the gt_tool and pred_tool conventions; the matrix
  takes pred_tool only (system B's real numbers), and the gap between the two conventions is the
  loss that leaks through when ctool picks the wrong tool.
- Matching collection batch p1: AppWorld's official three splits, all 315 tasks, gptoss single
  model (gyb's ruling); a new preset `gptoss_harmony_high` opens for generation settings (gyb ruled
  to use high, because the probe operates in effort-high live runs reading the thinking, so the
  training data takes the same tier; the old harmony_medium stays on file, untouched). The plan and
  preparation work are all recorded in `plans/2026-08-21-p1-collection-plan.md`; five preparation
  items were finished the same day, with only the launch left.
- Engineering convention: run_id has no base-model tier segment, **one training batch runs one
  base-model tier only** (p1b06/p1b17/p1b4); the 1.7B/4B weights are already downloaded to the NFS
  models drive and verified with a cold load.
- Basis: cparam and cgen use the same batch of samples and the same ground truth, differing only in
  string assembly, so any gap measured between them can only come from "whether the tool name is
  given in advance" (design document section 3); the constrained-decoding option was discussed the
  same day and dropped (the awkwardness of two sources of truth remains, see the design document).

## 2026-08-20 Generation settings move into config files (gen-preset): .py files keep only logic, models and settings are selected by name

- Trigger: gyb wanted to tune gpt-oss's generation settings, and a review found the settings
  scattered across five places with inconsistent values (the collector Chat default / gen_launch
  constants / the BFCL handler's hardcoded values / live-run constants / replay defaults), so
  changing one place would miss another; gyb ruled "there needs to be a way to pick from many sets of
  settings going forward," and model paths need to come out of .py files too.
- Decision: a new `configs/` directory at the repo root; `models.json` is the single model-address
  mapping (`model_registry.py` is downgraded to a reader, resolve() unchanged, and while at it, the
  three missing entries LFM2.5-350M-Base / Qwen3-0.6B-Base / MirrorAPI-Cache get registered);
  `presets/<name>.json` holds one set of generation settings each (model alias + server section +
  client section). Seven entry points now take `--preset` (the four collectors / live_appworld /
  replay run; the BFCL handler goes through the environment variable NEW1_PRESET_JSON), with a fixed
  priority order: an explicit command-line value beats the preset, which beats the original default.
  The general-purpose launcher `serve_preset.py` is registered (serve-preset, a launch-class task);
  it reads the server section, starts vLLM, and copies the preset into the log directory; the 13 old
  `launch_vllm_*.py` scripts are left untouched as history. From now on, trajectory meta records the
  preset name plus the expanded gen_settings (previously it did not even record effort).
- Equivalence is not checked by eye: the five gptoss presets match the pre-change hardcoded values
  item by item, `--preset gptoss_chat_high` matches explicit flags key by key inside the appworld
  venv, and the tmux command serve_preset builds for gptoss_chat_high matches the old
  `launch_vllm_gptoss.py` character by character; all of this is pinned in `tests/test_preset.py`
  (18 test cases). The spec is in `.scratch/gen-preset/spec.md`.
