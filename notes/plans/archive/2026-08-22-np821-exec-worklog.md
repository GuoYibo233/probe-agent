# np821 execution block worklog (started 2026-08-22, run autonomously by Claude)

gyb's 2026-08-22 authorization: the execution block runs autonomously
throughout, every stop point is ruled on by Claude and filed, gyb checks
it upon return. This file is the record of process-level rulings and
progress; convention-level rulings are recorded separately in TIMELINE.
The plan itself is in `plans/2026-08-21-np821-plan.md`.

## Precheck before starting (execution block todo 1 plus three additional checks, morning of 2026-08-22)

- NFS space: /net/tokyo100-10g/data/str01_01 has 43T available. This
  batch's worst-case total demand is about 187G (new dataset ≈ p1's
  1.3G x 4 = 5.2G; new trajectories ≈ 479M x 4 ≈ 1.9G; the test split's
  logits cache ≈ 32M x 4 = 128M; the checkpoints for 12 training runs
  extrapolated from p1's three measured sizes, worst case all-4B at
  15G x 12 = 180G). Under 0.5% of what's available, cleared.
- Config check: np821_gptoss.json, manifest_np821.json,
  configs/presets/default.json match the plan's master convention table
  item for item; gpt-oss-120b's 15 weight shards are all present on NFS;
  task-set `wc -l` gives 89/56/167 (no trailing newline, actually
  90/57/168, 315 tasks in total).
- All nine items of DATA.md's start-of-work checklist done: the data
  version goes into run_family (nyapass_aw_v1), the seed is hardcoded
  into the manifest, generation settings go through the new preset
  default (the preset name and the expanded gen_settings land in
  trajectory meta automatically); the byte-for-byte reconstruction
  comparison and the TIMELINE entry are scheduled for the annotation
  stage.
- Working tree clean, HEAD a8566db.

## Ruling 1: collection card slots follow the manifest's placeholder values 2/3/4/5, unchanged

A real probe (gpu-jobs free) found all six big cards on tokyo108 FREE.
The placeholder values 2/3/4/5 are exactly 1 H100 95G plus 3 H200 143G,
taking all three H200s, which is the largest-VRAM four-card combination
obtainable from the six; the file is left unchanged, keeping the working
tree clean, and c2's G2 gate ran another real probe as a backstop at
launch time. This is a process-level ruling, not entered into TIMELINE.

## Collection launch record (2026-08-22 05:40-05:50)

All five driver invocations passed (executed by the gpu-runner agent):

- c1_gen: the three generated files land in envs/runs/nyapass/
  (launch_servers.py / launch_clients.sh / MANIFEST.md), card numbers and
  ports checked item by item.
- c2_servers: four vLLM instances launched, sessions
  `new1_nyapass_srv_gptoss{a,b,c,d}_t108g{2,3,4,5}`, ports
  8103/8106/8107/8108.
- c3_health: polling started at 05:40:42, all four ports reachable by
  05:44:42, took about 4 minutes, no session dropped.
- c4_smoke: 1 task x 4 trajectories finished in 264 seconds, G4's
  criteria all passed: the 4 files `_r0.._r3` are all present, last line
  is final, meta's seeds 42/67/4267/6742 match r0..r3 one by one,
  temperature 1.0 / effort high / preset default. Of the 4, 3 had eval
  success=True and 1 had False (trajectory quality isn't a gate item, let
  through as usual).
- c5_clients: 12 client shards launched (on the login machine, sessions
  `new1_nyapass_gptr_s0..s3` / `gpdv_s0..s1` / `gptn_s0..s5`), shard task
  counts 360+228+672 = 1260, matching the task set x 4. The driver
  auto-filled all three ledger entries: five gpu-jobs names (nyapass +
  nyapass_srv_a..d), record start (run_id nyapass, track
  collect_nyapass, commit a8566db, tree clean), RUNMETA.json's first
  entry.

After launch the pointer stops at c6_done (launched). The output
directory is `envs/runs/nyapass/appworld_gptoss/`, client logs are in
`envs/runs/nyapass/logs/`, server logs are in `envs/serve_logs/`.

## Monitoring arrangement

The resident sampler is running (web page at 8377). The main session
also set up a standing monitor (one round every 5 minutes): all 12
client sessions exiting -> wake up and advance c6 (killing the four vLLM
instances first, then running it, so G7 can pass); a change in the
server session count or 90 minutes with no new file -> wake up and
investigate. Wall-clock is projected at 6 hours and up (p1 measured out
to about 52 tasks/hour/instance x 4 instances, and temperature 1 can only
be slower).

## Waiting-period reconnaissance summary (morning of 2026-08-22, from two agents reading the code, line numbers in the agent reports)

Key points of the remaining nine-step route, both verification and
running follow this:

- The a1 stop point: the driver itself scans all trajectories with
  max_bounds=10^9 to produce the untruncated cut distribution (p50/p90/
  p99/max plus counts over 32/64/128/256), writing it into state.json's
  cutpoint_stats. The way to rule is to add `"max_bounds": <number>` at
  the top level of np821_gptoss.json; even keeping it at 64 must be
  written explicitly. max_bounds does not enter the state fingerprint, so
  changing the config won't collide on ident.
- The meaning of max_bounds: it caps the number of samples cut out of
  each event (one step's think text); beyond the cap, thinning is by
  approximately equal-spaced index, the final cut is always kept, and
  what gets thinned out are the samples at the gradual decision points in
  the middle-to-late part of the thinking. p1's baseline: 4048 events,
  boundaries per event min 1 / med 56 / max 64 (this statistic was itself
  already truncated at 64, p1's true truncation rate cannot be read from
  it).
- a2 reruns the whole annotate-chain each time it's invoked (build ->
  param_label -> check_callstr), with gates A/B/D hard-blocking inside
  check_callstr; a3 does G9/G11 plus a byte-for-byte cmp on a rebuild of
  the 12 output files (backup directory `<data_out>_rebuild_ref`, NFS
  needs one more dataset's worth of space reserved).
- After editing the config, a commit is required before entering the
  training stage (t1 checks for a dirty tree right at the start).
- t1_smoke only checks the criteria: the 12 cells' smoke tests must be
  fired manually, and the output directory must be named
  `pipeline/runs/smoke/<batch>_gptoss_<cell>_smoke`. b06 can go through
  `launch-probe smoke`; b17/l17/l4 fire
  train_causal_{tool,callgen,param}.py `--smoke` manually per cell, with
  flags in the same shape as the p1 ledger (b17: --base qwen17
  --grad-ckpt; l17: add --lora as well; l4: --base qwen4 --lora
  --grad-ckpt; ctool carries --align-tol 3e-4).
- Draft smoke layout (also answering the two card-placement questions):
  b06 and b17's six cells go on tokyo107 48G to actually measure whether
  they fit (if b17 OOMs, the answer is recorded as "doesn't fit on 48G,"
  and that cell's smoke test moves to 108 and reruns to pass the gate);
  l17 and l4's six cells go on tokyo108's big cards to actually measure
  LoRA speed.
- t2_full launches one batch per invocation, with the four batches
  strictly serial (pend[0]); cross-batch parallelism requires manual
  launching and has the pitfall of "the driver reissuing a fake
  RUNMETA," so whether to run batches in parallel is ruled on after the
  smoke test's measured speed.
- The driver doesn't read base/mode from batches; --base/--lora/
  --grad-ckpt are entirely decided by the placement table's extra; none
  of the 12 placement tables (4 training + 4 eval_tool + 4 eval_call)
  exist yet, they need to be handwritten before each launch, shaped after
  p1's tables of the same name.
- The evaluation risk level: ctool computes both the 0.05/0.10 levels
  in one pass into REPLAY_REPORT.json; before launching e2, read each
  batch's REPLAY_REPORT's chosen_theta first: if 0.05 has a solution,
  launch with the default, and if not, write `--risk 0.1` into that
  batch's eval_call table's extra (write 0.1, not 0.10, since the matrix
  looks up values by string key), noted in the report. This way, 0.05
  being unsolvable doesn't turn into a silent exit 1 in tmux.
- After launch-probe/launch-eval launches, the driver's exit code
  doesn't guarantee the process is alive (the §6.3 deviation): after
  launching, always read the alive check at the tail of stage logs such
  as `logs/pipeline/nyapass_aw_v1/t2_full.log`, then watch with
  gpu-jobs.

## Collection wrap-up record (2026-08-22 10:38-11:0x)

- All 12 clients exited naturally, all 1260/1260 files end in final
  (checked file by file by the main session, zero corrupt files); 41
  trajectories hit the 30-step cap.
- All four vLLM sessions killed clean, GPU 2/3/4/5 VRAM measured 0
  MiB; the driver's c6 passed on one invocation: all five names
  deregistered, record finish landed trajs=1260 / units=315 /
  steps30_hit=41 (41 matches the main session's independent count).
- Measured wall-clock: launched at 05:50, all collected by 10:5x,
  about 5 hours, a rate of about 260 per hour (four instances), slightly
  faster than the estimate projected from p1.

## Ruling 2: max_bounds stays at 64 (a convention-level ruling, already entered into TIMELINE's 2026-08-22 entry)

a1 stop-point statistics: 15216 events, untruncated cuts p50 60 / p90
246 / p99 572 / max 842, event counts over 32/64/128/256 are
10417/7271/4019/1408. Per-split sample counts under each candidate cap
(computed for real with the same boundary_counts code):

| Cap | train | dev | test_normal | Total | train vs p1 (46438) |
|---|---|---|---|---|---|
| 64 | 186479 | 115211 | 391893 | 693583 | x4.02 |
| 96 | 238893 | 148731 | 505964 | 893588 | x5.14 |
| 128 | 277594 | 174279 | 590482 | 1042355 | x5.98 |
| 256 | 358380 | 228864 | 768824 | 1356068 | x7.72 |
| uncapped | 402722 | 263063 | 881153 | 1546938 | x8.67 |

Event counts across the three splits: train 4127 / dev 2556 /
test_normal 8533. The four reasons for the ruling are in TIMELINE's entry
for that day (budget fit, the long tail dominating under equal weight,
thinning preserving depth coverage, reversibility).

## Smoke test record (midday 2026-08-22, all 12 cells passed)

The four criteria (start/done/best/, plus ALIGN PASS for ctool) all
passed across all 12 cells, and all four ctool alignment checks PASS
(b06_ctool's align_maxdiff_hidden is 4.53e-05, within tol 3e-4). Hard
answers to the two card-placement questions:

- **0.6B full-parameter (no checkpointing) does not fit on 48G**: all
  three cells OOM on tokyo107 (traceback archived at
  `logs/smoke_np821b06_cparam.oom_t107.log`); after moving to a big card,
  measured peaks are ctool 60.2 / cgen 76.8 / cparam 76.7 GiB, not a
  small gap. The watershed for whether it fits is `--grad-ckpt`, not
  model size.
- **1.7B full-parameter + checkpointing does fit on 48G**: peaks are
  ctool 35.4 / cgen 44.1 / cparam 44.1 GiB, leaving only 3.4 GiB of
  headroom against 47.5 GiB available.
- LoRA's VRAM is small: l17 peaks 17.3/34.7/34.7, l4 peaks
  32.1/37.6/37.6 GiB.
- The smoke test's ips is a contaminated lower bound (the interval
  includes the validation forward pass and 200 generations, and at smoke
  scale not a single step event is written); it's not used for ETA, the
  ETA baseline instead uses p1's real run wall-clock.

p1's real-run wall-clock (runs.jsonl, x1 data): b06 on H100, ctool
0.57h, cgen/cparam 6.07h each; b17 on H200, ctool 0.55h, cgen/cparam
8.72h each; on A6000, LoRA only ever completed ctool (l17 1.53h / l4
3.53h), cgen/cparam have no finish record.

## Ruling 3: card placement and parallel strategy for the four batches (process-level)

Projected at data x4.02: b06's cgen/cparam on H100 is about 24.4h;
b17's same cells on H200 are about 35h (H100 is slightly slower).
Layout:

- Three batches launch now: b06 -> 108 H100 idx0/1/2 (the only free
  card group that fits the 60-77G peaks); l4 -> 108 H200 idx3/4/5 (the
  biggest model paired with the fastest card); l17 -> 107 Ada idx0/1/2
  (peak <=35G, 13G headroom, zero OOM risk).
- b17 waits for b06 to finish and takes over its H100 idx0/1/2 (about
  +24h, and the driver's serial ordering happens to reach it next). b17
  does not go on Ada: 44.1G against 48G leaves only 3.4G, and a
  tens-of-hours-long run should not risk an OOM partway through. Ada idx3
  is kept in reserve.
- The driver only invokes t2 twice (launch b06, then launch b17 once
  b06 is done); l17/l4 are launched manually with `launch-probe full`
  (the same registration code path). t2 is not invoked outside of these
  two times, avoiding "a partially completed batch getting a fake
  RUNMETA reissued by the driver" (the scenario in driver.py:1260-1269's
  comment).
- No historical data exists for LoRA speed on big cards: 1-2 hours
  after launch, the measured ips is taken from train_log's step events to
  recompute and file the ETA, ruled on again if it turns out infeasible
  (see the pending item).

## Training three-batch launch record (afternoon 2026-08-22)

- t1's gate, the 12 cells' smoke criteria, all passed (the "loss is
  dropping" item can't produce a step record at smoke scale, and the
  driver, per the known convention, records "not judged" and doesn't
  block on it).
- t2's first invocation launched np821b06 -> H100 idx0/1/2, all three
  cells ALIVE; l4 -> H200 idx3/4/5 and l17 -> Ada idx0/1/2 were launched
  manually with `launch-probe full`, all six cells ALIVE. All nine
  cells' record start is at commit 1b9334f (tree clean).
- launch-probe doesn't write RUNMETA (a WARN was actually logged), and
  `runmeta --kind train` has been added to each of the nine runs one by
  one, with the command taken from the ledger's cmd field, keeping the
  traceability chain complete.
- b06_cgen's start record confirms it's training on the full data:
  n_train 186479 / total steps 17484 (batch 32, 3 epochs).
- Monitoring: the sampler plus a 30-minute heartbeat (reading ips
  directly from step events); once b06's three cells are done, wake up
  and invoke t2 to launch b17 (taking over H100 0/1/2); if any cell dies
  without a done, alert.

## Pending rulings (preview)

- ~~Rule on `max_bounds` once annotation's a1_stats cut distribution is
  out~~ (already ruled: stays at 64, see above).
- ~~Whether the four training batches run in parallel across batches for
  cards~~ (already ruled: launch three batches at once + b17 takes over,
  see ruling 3).
- ~~Ruling 4 pending~~ (already ruled, see below).

## Ruling 4: LoRA's measured ETA makes the run viable (process-level, final calculation 2026-08-22 15:02)

Method note: the ledger's record window duration is not trustworthy
(p1b06_cgen's ledger says 6.07h, train_log's real value is 5.60h); ETA is
always computed from train_log's step-event timestamps. The early-rate
severely underestimates the steady state: both p1 and np821's
full-parameter cgen only run ~5.4 gstep/min for the first 100 steps,
climbing to above 13.5 at steady state; LoRA has no such ramp-up curve,
it is steady from the start.

Measured over a two-hour steady-state window (13:01 -> 15:02):

- b06 cgen/cparam: already past 16.7 gstep/min at steady state and
  still climbing, remaining ETA ≈ 15h, expected to wrap up the morning of
  08-23 -> b17 takes over the H100.
- l17 cgen/cparam (Ada): 3.31 gstep/min, remaining ≈ 85h (3.6 days),
  expected to wrap up in the small hours of 08-26.
- l4 cgen/cparam (H200): 3.31 gstep/min, remaining ≈ 85h, same as
  above.

Ruling: **the run is viable, nothing is cut or changed**. Basis: 85h
is far below the A6000-projected 170/380h (the point of switching to a
big card is achieved); b17's takeover uses the H100 that b06 freed, zero
conflict with the two LoRA batches, and no task is waiting on these six
cards while LoRA runs to completion; cutting or scaling down would save
nothing, since evaluation and the matrix have to wait for these runs
either way. The plan's clause "an infeasible ETA overturns the premise"
was not triggered, no convention changes, not entered into TIMELINE.

Three ctool cells have already fully wrapped up and been settled run
by run (deregistered + record finish): b06 acc 0.6883 (H100, about 1.0h),
l17 acc 0.6974 (Ada, about 3.2h), l4 acc 0.7016 (H200, about 3.0h), ALIGN
all PASS.

## b06 wraps up and b17 takes over (morning 2026-08-23) + Ruling 5: cgen reroutes to Ada

- b06's whole batch wraps up: ctool acc 0.6883, cgen best_val_ce
  0.4793, cparam best_val_ce 0.396, all three runs deregistered + record
  finish one by one. Each epoch-boundary validation (val's 115211 lines
  plus 200 generations) takes about 1 hour, and both cells' wall-clock is
  about 18h.
- Complication: the 108 gpu0 that b06 freed and the gpu3 that
  l4_ctool freed were subsequently taken by other users' processes (gpu0
  user glin 51.8G, already running 7h48m; gpu3 pid 3144460 50.9G).
  Someone else's card is off-limits: it's not touched, and its release
  time is not waited on.
- Ruling 5: b17's ctool/cparam land on 108 gpu1/gpu2 (H100, launched
  normally, ALIVE); cgen reroutes to 107 Ada gpu3 (the reserve card).
  Basis: the smoke test measured cgen's peak on Ada at 44.1G, running
  stably to completion, with the same structure as the full-scale peak
  (same max_len, same batch size); how long it will take for the taken
  big cards to be released is unknown. Ada's steady-state rate is
  measured 2 hours after launch: if the ETA stretches past midday
  08-26 and a big card has been freed by then, cut losses early and
  refire (giving up 2 hours of Ada progress for 35h of big-card time).
- The driver had already stamped the `launched` marker on the first
  launch attempt (gpu3 SKIP); the relaunch went through manual
  launch-probe (ctool/cparam are alive, SKIP, only cgen was launched),
  all three ledger entries filled in, RUNMETA for the three runs pinned
  at commit 7dbd28e.

## Ruling 6: b17_cgen OOMs on Ada on the very first backward pass, switching to waiting for a safe big card (2026-08-23 05:50)

- Fact: 6 minutes after launch, the first backward OOM'd (needed
  4.64G with only 3.61G left; PyTorch actually held 34.75G plus 8.63G
  reserved as fragmentation, the full traceback is kept in the tmux log
  `new1_np821b17_gptoss_cgen_t107g3.log`). The smoke test's 500-sample
  subset never hit the sequence combination in the full data's first
  batch: ruling 5's premise, "the smoke peak of 44.1G fits," was
  empirically overturned, and 48G is recorded as "doesn't fit" for
  b17_cgen at full scale.
- Ruling: no experiment with the expandable_segments allocator is
  done (the time saved doesn't outweigh the risk of another OOM partway
  through a 30-hour-class run); cgen instead waits for a safe big card:
  it lands on gpu1 once b17_ctool wraps up there around 08:00 on H100
  gpu1; if the taken cards 108 gpu0/gpu3 are released earlier, whichever
  is free first is used. Monitoring watches both conditions, and wakes
  up to refire on whichever triggers first.
- Already cleaned up: the dead session killed clean (gpu3's VRAM at
  the 4 MiB empty-card baseline), the ledger deregistered; the failed
  attempt's record start stays in the append-only runs.jsonl, and a new
  start is recorded on refiring, with no conflict.

## b17_cgen's third placement finalized (2026-08-23 07:17-07:2x)

- b17_ctool wrapped up on H100 gpu1 at 07:17 (acc 0.6867, ALIGN PASS
  2.14e-04, wall-clock about 1.5h), deregistered + record finish done,
  gpu1 measured 0 MiB.
- cgen refired onto gpu1: launched with a temporary placement table
  containing only the cgen cell
  (`$CLAUDE_JOB_DIR/tmp/np821b17_cgen_only_placement.json`, not checked
  into git), avoiding the pitfall of launch-probe's "refire -> guard
  exits instantly -> fake registration" against the already-completed
  ctool cell; the real table `ops/np821b17_placement.json`'s cgen row is
  synchronously updated to 108 gpu1, on file.
- Registration in fact: the ledger's active list has the correct new
  session entry (launch-probe's "registration failed" WARN doesn't match
  reality, jobs.json is authoritative); record start reuses the 05:44
  entry (commit 7dbd28e, a duplicate run_id refuses to add a new one),
  and the actual launch commit is 097d81c, the difference being only the
  placement table and the worklog, the training code is the same
  version; RUNMETA's 4th entry pins 097d81c, and 097d81c is authoritative
  for tracing.
- The whole batch's 12 runs' final placement: b06=H100 x3, b17
  ctool/cparam=H100 gpu1/2, b17 cgen=H100 gpu1 (taking over from ctool),
  l17=Ada x3, l4=H200 x3.
- Whether the four training batches run cross-batch parallel for
  cards (ruled after the smoke test's measured speed, process-level,
  recorded in this file).
- If LoRA's smoke-measured ETA turns out infeasible, rule on switching
  cards / scaling down (convention-level, entered into TIMELINE).
- Each batch's evaluation risk level is set by REPLAY_REPORT's
  chosen_theta (the convention is already settled, only the execution
  result is recorded here).

## b17's two cells wrap up (2026-08-24 15:34)

- cgen best_val_ce 0.512 (H100 gpu1, taking over from ctool, including
  the rerouting hassle, wall-clock about 32.2h counting from the 097d81c
  refire); cparam best_val_ce 0.3378 (H100 gpu2, about 30.1h).
- Both runs deregistered + record finish one by one, b17's batch 3/3
  complete. Both full-parameter batches (b06/b17), six cells in total,
  have all wrapped up.

## l4_cgen wraps up (2026-08-25 04:25), 9/12 complete

- best_val_ce 0.371 (Qwen3-4B LoRA+gc, H200, wall-clock about 64.2h).
  The last epoch's val_ce 0.5716 is worse than best, best/ is taken from
  an earlier epoch, the weight files are all present.
- Deregistered + record finish done. 3 cells remain: l4_cparam is in
  its final validation segment (H200 validation about 2.5h, expected to
  wrap up the morning of 08-25); l17 cgen/cparam are at the 2nd
  epoch-boundary validation (Ada, expected to wrap up the morning of
  08-26).

## l4_cparam wraps up (2026-08-25 04:5x), 10/12 complete, l4's batch 3/3

- best_val_ce 0.3375 (Qwen3-4B LoRA+gc, H200, wall-clock about 64.4h).
  Last epoch's val_ce 0.4186, val_exact_params 0.77, best/ weights all
  present. Deregistered + record finish done.
- A real probe of 108: gpu3/4/5 at zero (l4 released clean, and the
  other user's process that had taken gpu3 is gone); gpu0/1/2 each show
  34-36G taken by other users (b17 wrapped up on 08-24, this is not our
  own leftover). The pre-written eval_tool placement table points at 108
  gpu0-3, to be re-arranged per the real probe when the time comes.
- 2 cells remain: l17 cgen/cparam (Ada, g11650/17484, expected to wrap
  up the morning of 08-26).

## Division of labor change: the evaluation line hands off to a branch session (2026-08-26 03:5x)

- The user opened a branch session, "new-exp-plan ⑂ I want to
  evaluate the fine-tuned parts done so far first," ordering evaluation
  of the 10 already-trained cells first. Division of labor between the
  two sessions: the branch handles the whole evaluation line
  (e1_tool/e2_call/matrix, advancing the driver's t2->t3->e1, Phase D
  wrap-up, Phase E writing back to the skill); this session only handles
  l17 cgen/cparam's training monitoring and wrap-up (deregister + record
  finish + record + commit), and once wrapped up, sends a message
  notifying the branch, which then launches l17's e2_call.
- From here on, this session doesn't invoke `run.py pipeline` and
  doesn't launch evaluation tasks, to avoid duplicate launches and
  state.json conflicts. Both sides write the ledger only through
  `run.py gpu-jobs`/`record` (which lock); git commits each add only the
  files they themselves touched.
- The branch's real probe at 03:5x: all six cards on 108 empty, all
  eight cards on 105 empty (the other user's process that had taken 108
  gpu0/1/2 is gone), evaluation prioritizes 108.

## Ruling 7: evaluation does no separate smoke test, launch's liveness check plus the first progress line substitute for it (branch session, 2026-08-26 03:5x)

- Fact: the driver's e1/e2/m1 completion criteria only look at output
  files (each batch's ctool REPLAY_REPORT.json, cgen/cparam's
  CALLGEN/PARAM_REPORT.json, MATRIX md), not state.json's launch marker;
  t2_full only clears once all 12 cells are complete. So evaluating the
  already-trained cells directly with `launch-eval` now means the driver,
  when it later reaches the evaluation stage, will recognize them as done
  with no conflict (skill C4 already says "dispatch evaluation cell by
  cell as each wraps up").
- Ruling: no separate evaluation smoke test. Basis: the same version
  of the evaluation code already ran through in full on p1's b06/b17
  batches (0.6B, 1.7B backbones); all three training scripts do
  merge_and_unload before saving best/, so a LoRA cell's best/ is
  structurally identical to a full-parameter cell's item for item (l4's
  model.safetensors is 16.09G, l17's is 6.88G, both merged full models);
  the evaluation script always loads back with from_pretrained(best/),
  zero changes; cgen/cparam evaluation's three-way data cross-check
  (the header's meta.data / --data / ctool's meta.data) all point at
  nyapass_aw_v1/gptoss. Doing a smoke test with `--limit` would require
  copying a 16G run directory, a cost higher than the benefit. The
  substitute verification point = launch's 30-second liveness check plus
  the first @hb progress line.

## Evaluation launch record: four batches' ctool (2026-08-26 03:58)

- `launch-eval tool` launched per batch: b06->108 gpu0 (H100),
  b17->gpu1 (H100), l17->gpu2 (H100), l4->gpu3 (H200), all four cells
  ALIVE, record start pinned to commit 1edd5ae (tree clean), run_id
  `eval_np821{b06,b17,l17,l4}_gptoss_ctool`.
- Verification point passed: within 100 seconds of finishing loading
  weights, all four cells reached @hb 100/2556 (dev split's 2556 events
  are evaluated first, then test split's 8533 events).
- **The RUNMETA WARN's wording doesn't match reality (needs to be
  written back into the skill)**: launch-eval prints "no --outdir given,
  RUNMETA not written," but it then appends an entry itself, kind=
  eval_tool, to `<run>/RUNMETA.json`'s `launches` (03:58:10, with
  session/gpu/log/placement table). Manually adding `run.py runmeta` per
  the WARN (03:59:07) becomes a duplicate. Looking back at training runs,
  the same thing: launch-probe's 12:03:50 entry plus the manually added
  12:05:20 entry. Duplicates are harmless (the traceability chain only
  gains entries, never loses them); from now on, **runmeta is no longer
  manually added** after launch-probe / launch-eval launches, instead
  RUNMETA is read to verify.
- Monitor b8phu882x: wakes up on REPLAY_REPORT landing or a log error,
  30-minute heartbeat. Once the report lands, read chosen_theta to set
  the risk level, write the eval_call placement table, and launch
  b06/b17/l4's cgen/cparam evaluation; l17's call cells wait for the
  parent session's notification that training has wrapped up.

## ctool evaluation wraps up x3 + call cells launched x2 (2026-08-26 04:37-04:45)

- Measured rate: evaluation runs by event count (dev 2556 + test 8533
  events); on H100, 0.6B/1.7B are each about 4.6-4.8 events/second, on
  H200 4B is about 3.7 events/second; one batch's ctool evaluation takes
  about 40 minutes, far faster than the 2-3 hours projected from p1's
  sample row count.
- Three batches' REPLAY_REPORT (test frozen, n=8533, the frequency
  prior baseline 0.3867):

  | Batch | θ(0.05) | θ(0.1) | 0.05-level coverage / trig_acc / earliness / wrong_spec | Temperature |
  |---|---|---|---|---|
  | b06 | 0.975 | 0.9 | 0.261 / 0.9529 / 0.565 / 0.0123 | 1.1959 |
  | b17 | 0.975 | 0.925 | 0.3288 / 0.9533 / 0.4758 / 0.0154 | 1.2359 |
  | l17 | 0.95 | 0.85 | 0.3401 / 0.9476 / 0.5042 / 0.0178 | 1.24 |

  All three batches have a solution at the 0.05 level, so the call cells
  all use the default risk level (no `--risk` added). All three cells
  deregistered + record finish one by one (run_id
  `eval_np821<batch>_gptoss_ctool`).
- b06's call cells launched at 04:38 on 108 gpu4/gpu5 (H200), b17's
  call cells launched at 04:45 on gpu0/gpu1 (H100), all four cells
  ALIVE; the placement tables
  `ops/np821{b06,b17}_eval_call_placement.json` were committed along
  with the ledger (d4ff119 / e6d1a39). b06's two cells showed their
  first progress within 40 seconds: cgen 8/2227, cparam 16/2227 (2227 =
  the count of test events fired at theta=0.975; cparam runs both
  gt_tool / pred_tool passes). RUNMETA's eval_call entry is
  self-written by launch-eval, not manually added.
- Monitor b7pufajd8 watches the call cells (reads the ledger to
  automatically pick up newly launched cells). l4's ctool report hasn't
  landed yet (4B is one notch slower on H200); once it lands, its call
  cells land on gpu2/gpu3.

## l4 ctool wraps up + call cells launched (2026-08-26 04:46-04:50), all four batches' ctool evaluation complete

- l4's REPLAY_REPORT (test frozen n=8533): θ(0.05)=0.975, θ(0.1)=0.875;
  0.05-level coverage 0.2569 / trig_acc 0.9599 / earliness 0.3886 /
  wrong_spec 0.0103; temperature 1.2704. 0.05 has a solution -> the
  default level. Deregistered + record finish (H200, about 48 minutes).
- l4's call cells launched at 04:50 on 108 gpu2 (cgen, H100) / gpu3
  (cparam, H200, since two generation passes go to the faster card),
  ALIVE, pinned at 15c90e8. At this point, 108's six cards are running
  b06/b17/l4's six call-cell evaluations; all four batches' ctool
  evaluation reports are present, and the driver's e1_tool criterion is
  already satisfied.
- All four batches have a solution at the 0.05 theta level, e2's
  `--risk 0.1` fallback clause was never triggered once.

## b06's call cells wrap up (2026-08-26 05:00-05:0x), b06's batch, three cells, evaluation complete

- Both cells are risk 0.05, θ 0.975, fired 2227 = 2227 test events
  scored, parse_fail 0, share of no-parameter events 0.467. On H200,
  cparam takes about 22 minutes, cgen about 23 minutes (generation rate
  1.1-1.4 per second).
- cgen: tool_ok 0.9057 / params_all_ok 0.8702 / full_call_ok 0.8276 /
  exact_call_ok 0.8289 / parameter-instance accuracy 0.7406 (2120
  parameter instances).
- cparam: the pred_tool convention gives tool_ok 0.9529 /
  params_all_ok 0.9026 / full_call_ok 0.8752 / exact_call_ok 0.8765 /
  parameter-instance accuracy 0.8182 (2079 instances); the gt_tool
  convention gives params_all_ok 0.9106 / parameter-instance accuracy
  0.8693 (1997 instances).
- Both cells deregistered + record finish (run_id
  `eval_np821b06_gptoss_{cgen,cparam}`).
- b06's two risk-level matrices are out:
  `pipeline/runs/MATRIX_np821b06_r0.05.md` / `_r0.1.md` (NFS output
  directory, the same command and filename as the driver's m1). Both of
  the matrix script's known display limitations show up here: the
  m-line's two cells (not trained in this batch) are marked PENDING; in
  the 0.1-level table, the cgen/cparam rows are still the numbers at the
  0.05-level firing threshold (θ 0.975), so citing the 0.1-level table
  must come with a written explanation.

## b17's call cells wrap up (2026-08-26 05:06-05:0x), b17's batch, three cells, evaluation complete

- Both cells are risk 0.05, θ 0.975, fired 2806 = 2806 test events
  scored, parse_fail 0, share of no-parameter events 0.3977. On H100,
  cgen takes about 26 minutes, cparam about 27 minutes.
- cgen: tool_ok 0.9006 / params_all_ok 0.8254 / full_call_ok 0.7887 /
  exact_call_ok 0.7876 / parameter-instance accuracy 0.6927 (3095
  instances).
- cparam: the pred_tool convention gives tool_ok 0.9533 /
  params_all_ok 0.8795 / full_call_ok 0.8525 / exact_call_ok 0.8521 /
  parameter-instance accuracy 0.8116 (2957 instances); the gt_tool
  convention gives params_all_ok 0.8902 / parameter-instance accuracy
  0.864 (2830 instances).
- Both cells deregistered + record finish; b17's two risk-level
  matrices come out afterward.

## l4's call cells wrap up (2026-08-26 05:13-05:1x), l4's batch, three cells, evaluation complete; 108's six cards back to zero

- Both cells are risk 0.05, θ 0.975, fired 2192 = 2192 test events
  scored, parse_fail 0, share of no-parameter events 0.3828. cgen (H100)
  about 23 minutes, cparam (H200) about 24 minutes.
- cgen: tool_ok 0.9056 / params_all_ok 0.8472 / full_call_ok 0.8294 /
  exact_call_ok 0.8271 / parameter-instance accuracy 0.7291 (2676
  instances).
- cparam: the pred_tool convention gives tool_ok 0.9599 /
  params_all_ok 0.8828 / full_call_ok 0.8654 / exact_call_ok 0.8645 /
  parameter-instance accuracy 0.8251 (2590 instances); the gt_tool
  convention gives params_all_ok 0.8969 / parameter-instance accuracy
  0.8794 (2488 instances).
- Both cells deregistered + record finish. A real probe of 108:
  evaluation sessions cleared to zero, all six cards' VRAM at 0 MiB (G7
  passes). The np821-related entries in the evaluation line's ledger
  active list are cleared.
- Evaluation of the 10 already-trained cells has now all wrapped up (4
  ctool + 6 call cells); l17's cgen/cparam evaluation remains, waiting
  for the parent session's notification that training has wrapped up.

## l17_cparam training wraps up (2026-08-26 14:3x, parent session), 11/12 complete

- best_val_ce 0.3146 (Qwen3-1.7B LoRA+gc, Ada, wall-clock about
  98.3h). Last epoch's val_ce 0.4518, val_exact_params 0.725, best/
  weights all present. Deregistered + record finish done.
- 1 cell remains: l17_cgen is in its final validation segment (entered
  validation around 12:05, expected to produce done around 15:00); once
  it wraps up, the branch will be notified all at once to launch l17's
  call-cell evaluation.

## l17_cgen training wraps up (2026-08-26 14:5x, parent session), 12/12 training all complete

- best_val_ce 0.3814 (Qwen3-1.7B LoRA+gc, Ada, wall-clock about
  98.7h). Last epoch's val_ce 0.643, val_exact_call 0.505, best/ weights
  all present. Deregistered + record finish done; 107's four cards
  measured at the 4 MiB baseline, released clean.
- All twelve of np821's training cells have now wrapped up. Summary
  of the four batches' best_val_ce (cgen/cparam): b06 0.4793/0.396, b17
  0.512/0.3378, l17 0.3814/0.3146, l4 0.371/0.3375; the four ctool
  best_calA_weighted_acc: b06 0.6883, b17 0.6867, l17 0.6974, l4 0.7016.
- Training monitoring wound down (the monitoring task ends itself
  after TRAIN_ALL_DONE); a message has been sent notifying the branch
  session to launch l17's call-cell evaluation and produce l17's matrix.
  This session's responsibilities are now clear.

## l17's call cells launched (2026-08-26 15:0x, branch session)

- The branch personally verified the parent session's wrap-up facts:
  both cells' train_log done events (0.3814 / 0.3146), best/ weights all
  present, runs.jsonl has finish, the ledger's active list is empty, the
  tree is clean at 7076c34, a real probe of 108's six cards found them
  all empty.
- l17 ctool's 0.05-level θ=0.95 has a solution -> the call cells use
  the default risk level. The placement table
  `ops/np821l17_eval_call_placement.json` (cgen->108 gpu0,
  cparam->gpu1) was committed as fad9abe, then `launch-eval call`
  launched, both cells ALIVE, record start pinned to fad9abe. Monitor
  b7pufajd8 picks it up automatically from the ledger.
- The driver is not invoked at this point: e2_call would see l17's two
  reports missing and no launch marker, and would launch l17's call
  cells again (the driver doesn't check the ledger for in-flight eval
  tasks). Once the reports land, t2->t3->e1->e2->m1 are invoked straight
  through, with m1 only adding l17's two risk-level matrices (skipping
  the six that already exist).

## Root-cause fix: RUNMETA's two writers become register_all's single writer (2026-08-26 15:1x)

- Root cause: `launch_common.register_all` carries its own RUNMETA
  step (writes only when given outdir, in the order ledger -> record ->
  RUNMETA); the two placement launchers, `launch_probe` / `launch_eval`,
  in order to ensure "once a launch really happens, pin the code first,
  even if registration is later refused it must not be lost," each
  called `append_runmeta` once themselves before invoking it (with
  session/gpu/log/placement table), then passed `outdir=None`, so
  register_all printed "WARN no --outdir given, RUNMETA not written,"
  the opposite of what actually happened.
- Fix (stated affirmatively, a single writer): the RUNMETA step moves
  to the very front of register_all (the order becomes RUNMETA -> ledger
  -> record), with new `runmeta_kind` / `runmeta_extra` parameters, and a
  write failure only WARNs; the two launchers drop their private write
  and instead pass outdir + kind + extra. `run.py launch`'s WARN when
  --outdir isn't given is kept (that case really doesn't write).
- Tests: `tests/test_launch_{probe,eval}.py` drop the patch on the
  private write, asserting instead that outdir/kind/extra are passed
  through to register_all; `tests/test_launch_common.py` adds two cases
  (RUNMETA has already landed when record is refused; kind/extra make it
  into the record and there's only one entry). All 57 cases across the
  four launcher test files pass, `run.py selfcheck` passes.
- Documentation: gpu-run SKILL.md's Phase 4 registration order and
  WARN semantics are rewritten; the two sentences in probe-pipeline's
  stage-commands, "launch-probe doesn't write RUNMETA / on seeing a WARN,
  add it yourself," are changed by this session once the write-back
  agent delivers (to avoid editing the same file at the same time as the
  agent).
- The duplicate RUNMETA entries already present in this batch's 12
  training run directories and 6 evaluation run directories (one from
  the launcher, one manually added) are left as is: the traceability
  chain only gains entries, never loses them, and output records are not
  deleted after the fact.
- Fix committed as 6047f83 (including a stale `max_bounds` assertion
  in test_driver: after ruling 2, the config explicitly writes 64, so the
  test now asserts == 64; the whole suite of 354 cases has only the known
  1 error from test_splice_replay's environment difference).

## Phase E write-back to the skill (2026-08-26 15:0x-15:3x)

- An opus subagent wrote back 7 documents per the task brief
  (probe-pipeline's SKILL.md / gates / invariants / stage-commands /
  extending, gpu-run's launch-methodology / monitor-methodology), +187
  -27 lines. Key points: establishing **G23** (don't invoke the driver
  while a manually launched evaluation is in flight) and **G24** (a
  matrix is only produced once that batch's reports are all present),
  added to the silent-failure table as #23/#24; adding the whole LoRA
  training-method axis (extending §3's opening, stage-commands §3.2,
  invariants' LoRA row, the run_id prefix carrying the training method);
  the measured-VRAM table, stage-commands §3.1, plus gates §3.9/§3.10's
  two OOM cases; the evaluation-duration table §4.5 (writing the counting
  unit first); the driver's two kinds of completion criteria written into
  §6; the multi-trajectory convention (seed family, trajs_per_unit, the
  preset as the single source of truth, the max_bounds field, equal
  weight w=1) added into invariants; G14's criterion rewording (a smoke
  run can't produce a step record at that scale, so "loss is dropping"
  cannot be judged).
- Main-session acceptance: read through both batches of diff in full;
  every code-behavior assertion in the documents was checked against the
  source with grep one by one (the SEED constant split, `--weight-mode`'s
  default of uniform, check_callstr gate B by K, gen_launch's
  traj_per_task/seed_family constraints, the inject line still looking up
  by `appworld_<unit>.jsonl`) and all matched. One number was corrected:
  §4.5's ctool minute count, recomputed from first-to-last heartbeat, is
  changed to 36-38 (H100) / about 45 (H200 4B), noting that ctool's @hb
  unit is events in the dev segment and cut-point rows in the test
  segment.
- Evaluation-rate correction (to earlier text in this file): the
  earlier "4.6-4.8 events/second" and "generation 1.1-1.4 per second"
  were readings from an early window in flight; computed for real from
  first-to-last heartbeat over the whole run, cgen generates at
  1.57-1.85 per second, cparam's two passes combined at 2.98-3.63 per
  second, a call cell takes 21-26 minutes; the memory file
  gpu-time-reference has been updated to the whole-run values.
- The three RUNMETA-related spots (stage-commands §3, §4.2, SKILL.md
  C3) were rewritten by the main session per the fixed single-writer
  semantics; gates' G16 line's original text is still accurate,
  untouched.

## l17 cgen evaluation wraps up (2026-08-26 15:18)

risk 0.05, θ 0.95, fired 2902 = 2902 scored, parse_fail 0; tool_ok
0.8866 / params_all_ok 0.7774 / full_call_ok 0.7326 / exact_call_ok
0.7316 / parameter-instance accuracy 0.6287 (3420 instances); share of
no-parameter events 0.387. H100, about 23 minutes. Deregistered + record
finish; gpu0 back to zero. cparam's second pass is running.

## l17 cparam evaluation wraps up (2026-08-26 15:19), 12/12 evaluation all complete

risk 0.05, θ 0.95, fired 2902 = 2902 scored, parse_fail 0; the
pred_tool convention gives tool_ok 0.9476 / params_all_ok 0.8322 /
full_call_ok 0.8094 / exact_call_ok 0.8067 / parameter-instance accuracy
0.7498 (3221 instances); the gt_tool convention gives params_all_ok
0.8467 / parameter-instance accuracy 0.808 (3083 instances). H100, about
24 minutes. Deregistered + record finish.

A real probe of 108: evaluation sessions cleared to zero, all six
cards' VRAM at 0 MiB; the ledger's active list is empty. All four
batches' ctool plus the eight call cells' evaluation have now all
wrapped up, next the driver is invoked through t2->t3->e1->e2->m1.

## The driver wraps up (2026-08-26 15:21): the nyapass_aw_v1 pipeline is fully complete

Five invocations in a row all green: t2_full "all 12 training runs
finished" -> t3_close "all 12 runs have all three ledger entries,
numbers recorded" -> e1_tool "all 4 batches' ctool reports present" ->
e2_call "all call-cell reports present, batches where both theta levels
are null and recorded N/A: none" -> m1_matrix newly producing
`MATRIX_np821l17_r0.05.md` / `_r0.1.md` (the other six already existed,
skipped per the criterion) -> done. All manually launched evaluations
were recognized as complete by the driver, matching ruling 7's
expectation.

All eight matrices are present:
`pipeline/runs/MATRIX_np821{b06,b17,l17,l4}_r{0.05,0.1}.md`.

## Phase D's six-part chain (2026-08-26 15:2x)

1. Record numbers: all 24 finish entries (12 training + 12 evaluation)
   are in `ops/runs.jsonl`, `RESULTS.md` has been rendered.
2. Add direction: not done, whether these numbers change any judgment
   in WORKPLAN is gyb's call to make (the iron rule: don't interpret
   results).
3. Add conventions: `DATA.md`'s nyapass_aw_v1 section was already
   written at the annotation stage, no new settings this round.
4. Release: a real probe of the three machines 105/107/108 found not a
   single non-FREE card, np821/nyapass-related tmux sessions are zero
   across all three machines; the call-cell monitor b7pufajd8 has
   stopped.
5. Deregister: the ledger's active list is empty.
6. Commit: the results report `plans/2026-08-26-np821-results.md`
   (states only facts) + the three ledger files + this worklog + Phase
   E's 7 skill documents, in one commit.
