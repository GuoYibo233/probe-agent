# p1 batch collection plan: supplying data for the new probe's three training methods x three backbone sizes

Settled 2026-08-21. The upstream design is
`plans/2026-08-21-new-probe-training.md`: the ModernBERT line stops
running, the causal line expands to three training methods (ctool / cgen /
cparam) x three backbone sizes (0.6B / 1.7B / 4B). The dataset directory on
NFS is currently empty (the 2026-08-02 clean sweep deleted the old
trajectories, and the z1 smoke batch was also deleted once tested), so
this round of comparison has to start from collection. This plan only
covers collection and dataset building; how training is launched (SFT
details, the first round's 1.7B hyperparameters) is discussed separately,
not settled in this file.

## Phase 0, five variables

| Variable | Value | Basis |
|---|---|---|
| BATCH | `p1` | a new prefix, doesn't collide with w0/c1/c2/z1/ro1 |
| ENV | `appworld` | the current active setting (METHOD.md: gpt-oss-120b with AppWorld, TIMELINE 2026-08-08) |
| MODELS | `gptoss`, a single model | user's 2026-08-21 ruling: every variable in the nine-cell comparison is on the probe side, one model being probed is enough |
| CELLS | `ctool cgen cparam` | the m-line's two cells stop running as of 2026-08-21 (the design document's first overall decision) |
| DATA_ROOT | `/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/data/aw_p1_v1/` | the big-output-goes-straight-to-NFS iron rule; the data version number follows the batch, not mixed with aw_official_v1 / aw_z1_v1 |

## Scale

- The full official task set, all three splits: train 90 tasks, dev 57
  tasks (used as val), test_normal 168 tasks, 315 tasks in total (user's
  2026-08-21 ruling).
- The task sets are used directly from
  `envs/appworld/data/datasets/{train,dev,test_normal}.txt`. The three
  task sets have no pairwise overlap, measured on 2026-08-21 (244
  scenarios, each with 3 variants, not one scenario crosses splits); as
  usual, `comm` is run again before launch to check and keep the
  evidence.
- Warning: none of the three txt files end in a newline, so `wc -l`
  under-counts each by 1 (89/56/167); count it as +1 when checking
  numbers at G9.

## Generation settings (the effort level, ruled on 2026-08-21)

User's ruling: open a new preset, `gptoss_harmony_high` (copying
harmony_medium, only changing reasoning_effort to high; DATA.md §7 item 9:
switching effort opens a new preset without changing the old one).
Reason: the live-run line's `gptoss_live_high` preset is effort high, and
when the probe is deployed it reads thinking generated at the high level,
so the training data is taken at the same level, and the distributions
line up. The cost is recorded as is: the high level's thinking is longer,
and both collection wall-clock and per-event cut counts will rise
compared to the medium convention; this differs from z1's small-sample
convention (z1's numbers had no reference value to begin with).

| Preset | api | effort | temperature | start_date | Status |
|---|---|---|---|---|---|
| `gptoss_harmony_high` | harmony | high | 0.0 | carried over from 2026-08-06 | used by this batch, needs to be newly created |
| `gptoss_harmony_medium` | harmony | not passed (the prompt lands at medium) | 0.0 | 2026-08-06 | the old convention kept on file, untouched |

The rest of the convention is fixed: `--api harmony` (the live-run line
goes through /render's harmony token ids, collection uses the same api
convention), temperature 0.0, seed 20260729 across the whole chain,
`--max-steps 30` (gen_launch's current CLIENT_COMMON value).

## Preparation before collection (five items, all CPU, all completed on 2026-08-21 itself)

1. **`envs/runs` symlink** done: home's `envs/runs` no longer exists after
   the clean sweep, and in the client sh that gen_launch generates, the
   interpreter path and the output path share the same `envs_root`, so
   envs_root cannot be pointed straight at NFS. A symlink has been made
   per existing convention: `envs/runs ->
   /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/envs/runs`
   (measured to see the NFS-side hcap directory through the link), and a
   bare-name entry `envs/runs` has been added to the "symlinks for
   directories already moved to NFS" section of `.gitignore` (a trailing
   slash wouldn't match the symlink itself, a mistake hit on 2026-08-02).
2. **gen_launch's gptoss client preset made configurable** done:
   previously `GPTOSS_CLIENT_EXTRA = "--preset gptoss_chat_high"` was
   hardcoded. An optional top-level manifest field,
   `gptoss_client_preset`, has been added: the default `gptoss_chat_high`
   leaves old manifests' behavior byte-for-byte unchanged, and once a
   name is given it checks that `configs/presets/<name>.json` exists
   (exits 2 if the file is missing). Along the way, the MANIFEST.md
   template's hardcoded "all six instances up" wording was changed to
   print by the actual instance count. The stage-commands §7 interface
   write-back is done together with this round's Phase E.
3. **Preset** done: `configs/presets/gptoss_harmony_high.json` has been
   created (copying harmony_medium, only changing reasoning_effort to
   high), and preset_loader was measured to load it: api=harmony /
   effort=high / temperature 0.0 / start_date 2026-08-06.
4. **Annotation config** done: `pipeline/configs/p1_gptoss.json` has been
   created, copying `aw_gptoss.json` with four changes: `run_family:
   "aw_p1_v1"`, `traj_runs: ["/home/y-guo/reproduce/new1/envs/runs/p1"]`
   (via the symlink onto NFS, the directory itself is the run directory,
   not nested, silent-failure point #20), `data_out: <DATA_ROOT>/gptoss`,
   and the three task-set paths unchanged.
5. **manifest** done: `pipeline/collect/manifest_p1.json` has been
   created, structured after manifest_w0:
   - servers: tokyo108 GPU 4/5 (H200) start 2 gpt-oss-120b instances (63G
     weights, doesn't fit on a 48G A6000, only a big card works; this is
     a pre-placement, a real G2 probe for free cards happens before
     launch, and if the card numbers change the manifest is regenerated,
     with the placement result landing in `ops/p1_placement.json`).
   - clients: a single model, three splits, 7 shards, train 2, dev 1,
     test_normal 4, all with `--resume`, outdir's standard name
     `appworld_gptoss` (forced by gen_launch, downstream silently skips
     any other name).
   - dry-run verified with `--dry-run --out-override`: 2 server
     instances / 7 shards, the client's `GPTOSS_EXTRA="--preset
     gptoss_harmony_high"`, outdir `$F/appworld_gptoss` lands behind the
     symlink.
   - The generated launch_servers.py / launch_clients.sh are not entered
     into the run.py registry, per the 2026-08-02 ruling.
- The three task sets' `comm` cross-check has been run: dev∩train = 0,
  dev∩test_normal = 0, test_normal∩train = 0.

## Launch and acceptance (the whole process goes through the gpu-run skill, this plan only lists the corresponding gates)

1. G1's pre-launch commit (the dirty-tree hard gate) -> G2's real probe
   for free cards -> `run.py gen-launch --config manifest_p1.json`, first
   `--dry-run` to look at the generated sh, then generate for real.
2. Start the service -> G3 service health all green -> G4 first runs a
   1-task smoke test (verifying the trajectory's first line has meta with
   task_id, the last line has final, and preset and gen_settings land
   correctly in meta) -> scale up.
3. Wall-clock reference (a projection, not a measurement): the w0 batch's
   six services, three models, took 3-5 hours; p1's gptoss task count is
   about 1.9 times w0's gptoss side (168 tasks), with the same number of
   service instances, roughly projecting 6-10 hours. c1 measured gptoss's
   thinking to be far longer than q36's (a median of 51 cuts per event
   versus 3), so client concurrency is set one notch higher.
4. Wrap-up: G6 completeness, 315 `appworld_<task_id>.jsonl` files under
   `appworld_gptoss/`, every file's last line `type:"final"`; G7 VRAM back
   to zero -> `gpu-jobs finish` -> `record finish` -> commit.

## Building the dataset (CPU, after collection wraps up)

1. `build.py` + `param_label.py`, one pass each, using the config
   `p1_gptoss.json`.
2. Gates: G9's three-split row-count check (89+1 / 56+1 / 167+1); G10 not
   applicable for a single-model batch; G11's label_call spot check;
   `check_callstr`'s full gate runs as usual.
3. `ANNOTATE_REPORT.md`'s tool vocabulary and frequency prior baseline are
   accepted by eye, the numbers go into DATA.md (writing only the setup
   and convention, conclusions belong to RESULTS.md).
4. Reference frame: aw_official_v1's gptoss side produced 2138
   sample-level instances back then, with a 0.404 prior
   (`talks/20260809/data/01-settings.md`); the convention differs (both
   api and effort may have changed), the numbers are not comparable, they
   serve only as an order-of-magnitude reference.

## One convention for the training batches (set here first, followed at launch time)

The run_id is assembled as `<batch>_<model>_<cell>`, with no segment for
backbone size; training the same cell twice with two different backbone
sizes would collide on run_id. So **one training batch only runs one
backbone size**: `p1b06` for 0.6B, `p1b17` for 1.7B, `p1b4` for 4B as the
batch prefix. The SFT discussion wrapped up on 2026-08-21 (the ruling is
recorded in TIMELINE that day under "first-round training ruling"): the
first round runs 0.6B and 1.7B together, full-parameter, with
hyperparameters locked to 0.6B's current values, two sizes x three cells =
6 single-card tasks scheduled on tokyo108's 6 big cards; a separate LoRA
experiment line is opened on tokyo106's A6000, covering all three backbone
sizes (batch prefixes `p1l06` / `p1l17` / `p1l4`, gyb added 4B on
2026-08-21; three sizes x three cells = 9 single-card tasks, tokyo106's
ten cards can hold them; different training methods also each occupy
their own batch prefix), not part of the locked-hyperparameter comparison.
Whether 4B's LoRA fits on 48G has not been measured, the pre-launch smoke
test decides, and if it doesn't fit, the gradient-checkpointing flag is
used.

**Pre-launch smoke conclusions (measured 2026-08-21, see each smoke log
`logs/new1_p1*_smoke*` for detail)**:

- 1.7B full-parameter OOMs on backward for all three cells on the H100
  95G (the process used 90-93 GiB and then failed asking for another 4.64
  GiB; ctool's alignment check itself PASSes, maxdiff_hidden 2.02e-4).
  Handling: p1b17's three full-parameter cells get `--grad-ckpt` added
  (this only saves activation memory, not a single locked hyperparameter
  is touched); a round of gc smoke was run and passed before launch,
  scheduled for real on H200.
- 8 of LoRA's nine cells OOM on the first pass at 48G; with `--grad-ckpt`
  added, all eight exit 0; the only one that passed on the first try,
  p1l06_ctool, peaked at 46114 MiB, leaving only about 2.5G of headroom
  under 48G. Handling: all nine cells uniformly carry `--grad-ckpt` (the
  0.6B+gc+lora+ctool combination was not smoke-tested separately, but it
  is strictly lighter than the already-measured 1.7B equivalent). 4B's
  cgen/cparam with gc peak at 46426 MiB, a narrow margin; the real run
  relies on the sampler to watch it, and a refire if it dies.
- All five card-placement tables have been settled accordingly:
  `ops/p1{b06,b17,l06,l17,l4}_placement.json`.

## Autonomous execution authorization (gyb's verbal authorization before leaving on 2026-08-21)

While gyb is away, Claude runs the whole chain autonomously, without
checking in step by step:

1. Watch collection through to wrap-up once scaled up (G6's 315 files
   ending in final / G7 VRAM back to zero / finish / record finish /
   ledger committed).
2. Annotation and dataset building (build + param_label, G9/G11/
   check_callstr/byte-for-byte reconstruction comparison,
   ANNOTATE_REPORT's numbers going into DATA.md).
3. LoRA implementation acceptance + the three batches of fixes already
   approved (three safety fuses / three convention completions / four
   test items) + the skill write-back debt, all landed in a commit before
   training is launched.
4. Training smoke test (1.7B full-parameter memory, LoRA's three sizes,
   4B LoRA turning on gradient checkpointing if it doesn't fit) ->
   pre-launch commit -> parallel launch: full-parameter p1b06+p1b17, 6
   single-card tasks in total on tokyo108, LoRA p1l06/p1l17/p1l4, 9 in
   total on tokyo106.
5. If, before training launch, the research-loop session's two documents
   (CLAUDE.md/plans/research-loop-parts) are still dirty, a separate
   commit noting their origin takes them past the dirty-tree gate, not
   mixed into the same commit as the code changes.
6. Evaluation is also authorized (gyb's supplementary authorization on
   2026-08-21): after training wraps up, launch in EVAL_CELLS dependency
   order (eval-ctool first, then eval-cgen / eval-cparam, with cparam
   depending on the same batch and same model's ctool REPLAY_REPORT),
   each of the five training batches produces its own report,
   `summarize_matrix --prefix <batch>` produces a matrix per batch,
   record finish records the numbers; once the whole chain finishes, a
   summary report is written. Review findings and the list of already
   approved fixes are in `plans/2026-08-21-review-findings.md`.

## DATA.md §7 checklist walkthrough

1. Data version aw_p1_v1, written into the config and the run_id.
2. Prior baseline: ANNOTATE_REPORT carries its own, recorded separately
per this version. 3. Size numbering: single model, single environment,
not applicable. 4. Time comparison: not done. 5. Seed 20260729 across the
whole chain. 6. Rebuild comparison: this pays off aw_official_v1's debt,
rebuilding once after build to do a byte-for-byte cmp (the bfcl_mtb_v1
batch already has a precedent process for this). 7. Probe multi-config
forks: this batch has one set of data feeding nine cells, and each
evaluation report writes to its own run directory, sharing no files, not
applicable. 8. WORKPLAN judgment changes: checked at wrap-up, add a
TIMELINE entry if anything changed.
