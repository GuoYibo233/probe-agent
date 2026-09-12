# T03 report: trainer `pipeline/train/train_causal_share.py` and the registry

Ticket: `.scratch/kvshare-train/issues/03-share-trainer.md`
Branch: `ticket/2026-08-28-wave2/T03`, base `2216c44d50838e6df6d3f8f78b31ca955998e520`,
head `f40daaa` (worktree `/home/y-guo/reproduce/new1-wt/2026-08-28-wave2-T03`, deleted).

## 1. What was done (checked against the ticket, item by item)

### 1. New file `pipeline/train/train_causal_share.py`

- Data goes through `share_data.py` (ticket 01); the tokenizer and model go through
  `train_causal_callgen.build(dev, base=, attn_impl=, path=)`. `--base` accepts
  `qwen/qwen17/qwen4` or a directory path (`args.base in train_causal_callgen.MODELS`
  decides the branch: if yes, pass `base=`; if no, pass `path=`).
- The forward pass follows spec section 4 + `design-attention.md`: one shared
  `_forward_packed` first gathers from the last-layer hidden state at the loss
  positions, then runs `model.lm_head` (not computing logits for every position);
  on cuda it wraps `sdpa_kernel([SDPBackend.EFFICIENT_ATTENTION])` (`_attn_ctx`,
  degrades to `contextlib.nullcontext()` on CPU). The mask dtype is passed in by the
  caller (the `mask_dtype` parameter); training/evaluation use bf16 (when amp is on)
  or fp32 (CPU); the alignment check uses fp32; the bf16 coarse screen uses bf16.
  The position_ids at pad positions keep being counted onward by
  `share_data.batch_mask` (already implemented by ticket 01, this ticket only
  consumes it).
- Loss and updates follow section 5: `block_row_ce` (per-row mean CE + w for one
  physical block), `backward_logical_minibatch` (a list of physical blocks that one
  logical minibatch is split into by `chunk_by_budget`, `loss_C = Σ w_r·ce_r / W`,
  `(loss_C/n_g).backward()`). Inside `main()`, each epoch shuffles events with
  `random.Random(SEED+ep)`, cuts them into logical minibatches by `--events-per-mb`,
  and groups them by `--accum`; the tail group's `n_g` is set by
  `min(accum, M-group start)`, so no gradient is dropped and the step size is not
  discounted.
- Evaluation and `best/` follow section 6: the evaluation-point set is
  `{ceil(U·k/E): k=1..E}`; the implementation uses a `dict` so that when the same
  point is hit by multiple `k` values, the `max k` is taken as `frac` (guaranteeing
  that the `k=E` point, i.e. `u=U`, always maps to `frac=E` and is never displaced by
  an earlier duplicate point; details in "self-check"). The `best/` write-out and
  the `meta.json` fields are implemented item by item per the ticket (`trainer/frac/
  gstep/tok_budget/events_per_mb/accum/attn_impl` are new, `readonly_env`/
  `lora`/`grad_ckpt`/`param_only` are written conditionally).
- Logging and the heartbeat follow section 7: six event types,
  `start/step/eval/save_best/done/mem_probe` (`mem_probe` only appears under
  `--mem-probe`); `step`'s `train_s` only accumulates time spent in the training
  segment (timed once before and once after each update; the evaluation call sits
  between the two timings and is naturally excluded). `heartbeat.emit` appears in
  three places: at startup (line 606), on every step (line 682), and at wrap-up
  (line 726).
- The command line is implemented item by item per the table in section 8; the
  combination rule for `--smoke`/`--max-events` (`--max-events` alone is random,
  given together with `--smoke` it uses `shortest` and N covers 40/16) is written
  exactly as the spec states.
- The alignment check follows section 9; details are in its own section below (the
  part with the largest changes, most worth re-checking).

### 2. `run.py` registry

- `CELLS["cgen"]`/`CELLS["cparam"]` are changed to point at
  `train_causal_share.py`, carrying `["--mode", "cgen"]`/`["--mode", "cparam"]`
  respectively; `CELL_ORDER` is untouched.
- `TASKS["train-cgen"]`/`TASKS["train-cparam"]` have the script + `args` changed to
  match, and notes add an explanation of the new convention (the cap, the update
  unit, the built-in alignment check).
- New `TASKS["train-cgen-rows"]`/`TASKS["train-cparam-rows"]` point at the two old
  row-by-row scripts, with fields filled in item by item to match `train-ctool`
  (`desc/stage/py/script/gpu/notes`); notes use the ticket's own wording: "row-by-row
  reference implementation, used only for alignment checks and comparison; its
  output does not go into the matrix, its run_id must not use the in-service
  batch's prefix."
- `python3 run.py selfcheck`, `python3 -c "import ops.launch_probe"`, and
  `python3 run.py show train-cgen` printing a command that includes
  `train_causal_share.py --mode cgen` — all three pass, details in "2. How it was
  verified".
- `EVAL_CELLS` is untouched (`git diff` shows no change in this part).

### 3. `MAP.md` copy (the ticket asks for this to be written into the report, to be
committed to disk by ticket 04)

- **cgen** row: the program column changes to `train_causal_share.py --mode cgen`;
  the key-settings column reads "one event, one forward pass, shared prefix; events
  over the 8192 cap are dropped whole; one update per 8 events; validated on
  val_ce once every quarter epoch; `--tok-budget` controls VRAM."
- **cparam** row: same as above, the program column changes to `--mode cparam`.
- New row **(reference)**: `train_causal_callgen.py`/`train_causal_param.py`,
  launched via `train-cgen-rows`/`train-cparam-rows`, the old row-by-row convention
  of 4096, left-truncation, 3 epochs, frozen as the alignment reference; its output
  does not go into the matrix.
- New row **(shared)**: `pipeline/train/share_data.py`, the pure-CPU data and
  tokenization module shared by cgen/cparam (and by ctool's `read_position`,
  ticket 02).

### 4. Alignment check (section 9, the part with the largest changes)

- Placed before `lora_util.wrap`, under `model.eval()`; `run_align_check()` is one
  function that does the whole job: `torch.set_float32_matmul_precision("highest")`
  plus turning off the two `allow_tf32` flags on cuda (restored in `finally`).
- Feed material: `_align_candidates` independently scans val once (grouped by
  event, filtered on full-text tokenization to `<= 2048` tokens, not running
  `share_data.load_events`'s row-level pipeline — this is so that sampling under
  `--smoke` does not also carry the cost of full-scale row-level tokenization;
  details and reasons in self-check item 1), sampled with `random.Random(SEED)`,
  and `_write_align_tmpfile` writes a temp file in ascending `(event, sent_idx)`
  order (`tempfile.mkstemp`, the system temp directory, `unlink` in `finally`).
- New path: the same temp file feeds `share_data.load_events(limit=0)`;
  `_new_forward` runs one separate forward pass per event (the count is small, no
  need to pack into blocks by budget).
- Reference path: `_ref_forward` uses the old `collate` (`import`ed from the old
  script, not copied), batching `bs` rows at a time, hand-computing cross-entropy
  with the same formula as `inst_ce`, but keeping the extra per-token intermediate
  values — this diverges from the literal "import inst_ce" instruction; details and
  reasoning in self-check item 2. `bs=4` "full batch" and `bs=1` "single row" are
  each run once (the latter fills in the baseline). The reference path does not
  wrap `EFFICIENT_ATTENTION` (the pitfall from design-attention.md section 7.1: a
  single-row batch has no mask, HF goes through `enable_gqa`, and mem-efficient
  does not support GQA).
- Pairing: `len(ds.rows) == the new path's total row count`, position-by-position
  `ds.rows[i][0] == the text of row i on the new path`, and equal drop counts (cgen
  only checks `dropped_rows_tgt`; cparam also checks `assembly_mismatch`; the
  short-circuit form `mode != "cparam" or ds.mismatch == ...` is required —
  `CallDS` has no `.mismatch` attribute, and the cgen branch never evaluates the
  right-hand side).
- Verdict: per-row `<= --align-tol` (default 2e-5) and per-token `<= 3e-4` (a fixed
  value `TOK_DIFF_TOL`, not exposed as a CLI argument, per the spec's literal text);
  the baseline warning `row_diff > max(3*baseline_diff, 1e-6)` only warns, it does
  not gate. The bf16 coarse screen only runs on cuda; on CPU, the three fields
  (`bf16_mean_abs_diff`/`bf16_max_abs_diff`/the implied `bf16_warn`) are written as
  null/False per the spec. `ALIGN_CHECK.json` uses the uppercase key name `PASS`,
  and per the spec's own text also adds `baseline_warn` (the spec body explicitly
  requires "set baseline_warn: true") and one extra diagnostic key, `bf16_warn`.

## 2. How it was verified

All of it was run inside the worktree
`/home/y-guo/reproduce/new1-wt/2026-08-28-wave2-T03` (cprobe-env/mbert-env are
symlinked to the main repo, and pipeline/data, pipeline/runs are likewise
symlinked to NFS — the worktree is a fresh checkout, none of these three go into
git, and the symlinks were removed before the commit).

**Unit tests** ((a)(b)(c) of `tests/test_share_trainer.py` plus the existing three
files):

```
cprobe-env/bin/python -m unittest tests.test_share_trainer tests.test_share_data \
  tests.test_cparam_assembly tests.test_lora_merge -v
```
Tail of the output: `Ran 48 tests in 165.629s` / `OK` (all 48 pass, including 6 I
wrote: `TestPackedForwardMatchesOldPath.{test_cgen,test_cparam}`,
`TestBackwardBlockSplitInvariance.test_split_into_1_vs_3_blocks`,
`TestMainSmokeCPU.{test_cgen_smoke,test_cparam_smoke}` count as 3 test methods but
each contains both a cgen and a cparam assertion chain).

When these modules are run by naming them directly with the system `python3`, all
four files (including the existing `test_share_data.py`/`test_cparam_assembly.py`/
`test_lora_merge.py`) alike have their `SkipTest` at import time thrown by
`unittest.loader.loadTestsFromName` as if it were an exception (a traceback rather
than "OK skipped") — this is the behavior of the call form
`python3 -m unittest tests.test_X` (naming a module explicitly) itself; only
`python3 -m unittest discover` treats it as a skip. The same traceback was
reproduced against `tests/test_share_data.py` on the **main repo** (unmodified),
so it is not a regression introduced by this ticket. Verified once in `discover`
form:
```
python3 -m unittest discover -s tests -p "test_share_trainer.py" -v
# test_share_trainer (unittest.loader.ModuleSkipped) ... skipped
# Ran 1 test in 0.000s / OK (skipped=1)
```

**grep checks**:
```
grep -n "heartbeat.emit" pipeline/train/train_causal_share.py
# 606:    heartbeat.emit(0, steps, "step")
# 682:                heartbeat.emit(gstep, steps, "step", loss=loss_val)
# 726:    heartbeat.emit(gstep, steps, "step", status="done")
grep -n "sdpa_kernel" pipeline/train/train_causal_share.py
# hits the import line + the _attn_ctx definition (all three forward-pass call
# sites — training, evaluation, alignment check — go through this one shared
# function, _forward_packed, so there is only one literal sdpa_kernel([...])
# occurrence, but all three call paths pass through it)
```

**Real CPU smoke test** (0.6B fp32, using the original command from the ticket's
acceptance section):
```
cprobe-env/bin/python pipeline/train/train_causal_share.py --mode cgen \
  --data pipeline/data/nyapass_aw_v1/gptoss --out pipeline/runs/smoke/share_cpu_cgen_smoke \
  --device cpu --smoke --max-events 6 --log-every 1 --align-events 2 --base qwen --force
```
`ALIGN_CHECK.json`: `PASS: true`, `max_abs_diff: 2.384e-6` (tol 2e-5),
`max_tok_diff: 2.193e-5` (tol 3e-4), `n_events: 2`, `n_rows: 75`.
All five event types appear in `train_log.jsonl`; there is only one `step` entry
(6 events, `events_per_mb=4`, `accum=2` → `M=2, U=1`, matching ticket item 5's
"6 events gives only 1 update"); `loss` goes from 3.3317 to `val_ce` 1.2026 (the
0.6B backbone already has a language prior, it is not randomly initialized, so the
order of magnitude is reasonable). The `best/` directory is 2.3G.

cparam, same command with `--mode cparam --out .../share_cpu_cparam_smoke`:
`ALIGN_CHECK.json` `PASS: true`, `max_abs_diff: 3.576e-6`,
`max_tok_diff: 1.335e-5`; `best/meta.json` contains `"param_only": true`.

Both runs' output is kept on NFS:
`pipeline/runs/smoke/share_cpu_{cgen,cparam}_smoke/`.

**Zero-change check on the old scripts**:
```
git diff --stat
#  pipeline/train/train_causal_callgen.py | 22 +++++++++----
#  run.py                                 | 57 +++++++++++++++++++++++++++++-----
git diff pipeline/train/train_causal_param.py   # empty output
```

**`run.py` registry**:
```
python3 run.py selfcheck
# on the main repo, the 74 existing tasks are "all in place"; inside this
# worktree, third-party envs (appworld/alfworld/tales/tau2/toolhop/bfcl/vllm/
# stb-server) have no symlinks, so it reports "interpreter/program missing" —
# none of these touch train-cgen/train-cparam/train-cgen-rows/train-cparam-rows
# or train_causal_share.py at all; this is the standard symptom of a brand-new
# git worktree missing third-party venvs (cprobe-env/mbert-env reported the
# same before their symlinks were added; once added, these two no longer appear
# in the missing list), not a registry defect introduced by this ticket.
python3 -c "import ops.launch_probe"   # no output, exit code 0
python3 run.py show train-cgen --allow-dirty
#   command: .../cprobe-env/bin/python .../train_causal_share.py --mode cgen '<args...>'
```

## 3. Commit list

- `b503e84` T03: train_causal_callgen.build() adds the two keyword arguments attn_impl/path
- `2e50bfb` T03: add the cache-reuse trainer train_causal_share.py, wire cgen/cparam into run.py
- `f40daaa` T03: tests/test_share_trainer.py, spec 12 (a)(b)(c)

## 4. Self-check findings and open questions

1. **The alignment check's candidate sampling bypasses `share_data.load_events`'s
   row-level pipeline** (`_align_candidates` groups by event and does full-text
   tokenization itself, it does not call `share_data.load_events(val, limit=0)`).
   The reason is that the latter's row-level tokenization happens "after taking the
   subset," but this candidate-sampling step needs precisely to **look over every
   event first** before it can take a subset (picking out events with `<=2048`
   tokens); if `load_events(limit=0)` were run first for the sake of sampling, it
   would also do row-level tokenization over the entire val set (115,211 rows),
   and under `--smoke` this cost would be completely out of proportion to the goal
   of sampling 6 events. So this logic does not directly reuse `share_data.py`; it
   is a piece I wrote myself for performance reasons (grouping by event plus
   full-text tokenization filtering). It is not on the ticket's named "do not copy"
   list (`CALL_SEP`/`MAX_TGT_TOK`/`param_prompt_tail`/`param_target`/`MODELS`/
   `SEED`), but please re-check whether this tradeoff is acceptable.

2. **The reference path's per-token CE does not call `inst_ce` directly, it
   hand-computes the same formula** (`_ref_forward`). The ticket/spec section 9
   literally says "import the old script's collate, inst_ce ... to get the per-row
   ce," but the same spec section also requires a per-token-granularity criterion,
   "max difference over target tokens ≤ 3e-4" — `inst_ce` itself only returns
   per-row mean CE (see lines 231-253 of `train_causal_callgen.py`), it does not
   expose the per-token intermediate values. My handling is: `_ref_forward`
   hand-writes the exact same shifted-prediction + mask + cross-entropy formula as
   `inst_ce` (just keeping one extra step, `ce` (per-token), instead of directly
   aggregating `inst_ce`'s return value), without additionally calling `inst_ce`
   for double verification. I judge this to be "the capability the ticket's
   requirement itself demands exceeds `inst_ce`'s interface," not "I wrote a
   separate one for convenience," but it is indeed the autonomous decision in this
   ticket furthest from the literal instruction; please review closely whether the
   formula is position-by-position equivalent to `inst_ce` (the `max_abs_diff`/
   `max_tok_diff` from the two real cgen/cparam smoke runs are both on the order
   of 1e-5 to 1e-6, far below the threshold, which is indirect evidence, but it is
   not a direct row-by-row assertion against `inst_ce`'s output).

3. **`--mem-probe`, the GPU-side alignment check, and the second bf16 coarse
   screen (the `dev.startswith("cuda")` branch) were not exercised at all on my
   side** — this ticket's hard rule forbids launching GPU processes; these
   segments of code are written per spec sections 10 and 9 literally, and on CPU
   only "the branch itself does not crash when `dev.startswith("cuda")` is false"
   was verified, not the actual values on the cuda branch (especially whether the
   operation in `run_mem_probe` of "zero the lr, do one `opt.step()` to allocate
   AdamW state, then clear it" behaves as expected on a real optimizer). This part,
   together with "commands to run on GPU" below, is handed to the main session to
   go through gpu-run.

4. **`--mem-probe`'s full training-set load does not go through the
   `--readonly-env` filter** (`share_data.load_events(..., ro=None, limit=0)`,
   line 611 of main()). The spec does not clearly state whether the probe should
   pass through the readonly filter; not filtering makes the event set the probe
   sees (possibly) larger than at real training time, giving a peak-memory
   estimate that leans conservative (it will not underestimate); I judge the
   direction to be safe but it is not a behavior the spec names, listing it here
   for the record.

5. **`wall_s` (the done event) includes the time spent in `--mem-probe`** —
   `training_t0` is set after `heartbeat.emit(0, steps, "step")` and before the
   `--mem-probe` block, so when `--mem-probe` is on, `wall_s` will be longer than
   pure training time. The spec does not precisely define the start/end points of
   `wall_s`; this is my choice (treating it as "total time for this invocation"
   rather than "pure training time"), noted for the record.

6. **Found a pitfall unrelated to this ticket but worth recording**: in a
   newly-created git worktree, the `.gitignore` rule for `*-env/` (with a trailing
   slash) only matches a real directory, not a symlink pointing at a real
   directory — the `cprobe-env`/`mbert-env` symlinks I temporarily created inside
   the worktree to run the tests were, for a while, treated by `git status`/
   `git add -A` as untracked plain files (unlike the two bare-name rules for
   `pipeline/data`/`pipeline/runs`, which have no trailing slash and do recognize
   symlinks). Both symlinks were `rm`'d before the commit and never entered any
   commit, but other worktree branches later on should watch for this same
   pitfall (do not use a symlink to restore a large directory other than
   `*-env/` inside a worktree, or if you do, run `git status` to confirm before
   `git add`).

## 5. Commands to run on GPU (not part of this ticket, handed to the main session
to go through gpu-run)

Smoke tier (`launch_probe` automatically appends `--smoke`):
```
run_id: ks828b06_gptoss_cgen_smoke / ks828b06_gptoss_cparam_smoke
```
Launched with `ops/launch_probe.py smoke` (or by hand directly), output lands at
`pipeline/runs/smoke/<run_id>_smoke/`; acceptance is "it runs, it saves, the logs
are complete, ALIGN_CHECK.json PASSes."

Speed/VRAM tier (spec section 10, tokyo108 H100, no `--smoke`):
```
cprobe-env/bin/python pipeline/train/train_causal_share.py --mode cgen \
  --data pipeline/data/nyapass_aw_v1/gptoss \
  --out pipeline/runs/smoke/ks828b06_gptoss_cgen_speed \
  --max-events 450 --log-every 3 --eval-per-epoch 1 --mem-probe \
  --tok-budget 16384 --base qwen --force
# also run once more with --tok-budget 24576; PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
# is measured alongside it as a switch (spec section 10)
```
When `--mem-probe` is on, it first does one pass of event-level tokenization over
the entire train set (186,479 rows), then `worst_blocks` finds the worst block;
this step is much faster on GPU than on CPU, but it is still the most
time-consuming preparatory step; when scheduling, reserving on the order of "a few
minutes" is enough (the cost of a full run of
`share_data.load_events(train, limit=0)` on CPU was not separately timed by
itself; the full command's wall clock for the smoke tier of 6 events + 2 alignment
events is 26-27 seconds, and `--mem-probe`, which includes this full
tokenization step, will take longer).

## 6. Fix round 1 (review finding F1)

Worktree: `/home/y-guo/reproduce/new1-wt/2026-08-28-wave2-T03-fix1` (deleted),
branch unchanged (`ticket/2026-08-28-wave2/T03`), base is still the `f40daaa`
recorded above (checked out from the existing branch, not a new branch), new
head `106ab63`.

### F1: the alignment check's reference path does not import and call `inst_ce`, it
hand-writes a substitute implementation of the same formula

**The core objection in the finding text**: `_ref_forward` only hand-writes a
formula that is mathematically equivalent to `inst_ce`, and never actually calls
`train_causal_callgen.inst_ce`/`train_causal_param.inst_ce`, which diverges from
spec section 9's literal text, "import the old script's `collate`, `inst_ce` ...
to get the per-row ce"; furthermore, nowhere in the code is `_ref_forward`'s
per-row result cross-checked against the result of actually calling `inst_ce` —
the only related test from the previous round, `TestPackedForwardMatchesOldPath`,
checks the new path's `block_row_ce` against `inst_ce`, which verifies a different
code path and does not cover `_ref_forward`'s hand-written formula itself.

**Root cause**: `inst_ce` only returns per-row mean CE (the local variable `ce`
at lines 231-253 of `train_causal_callgen.py` / lines 197-209 of
`train_causal_param.py` is never exposed externally), while the same spec section
also requires a per-target-token max-difference threshold (≤3e-4); `inst_ce`'s
interface cannot give this granularity. The previous round's response was to work
around it — writing an entire separate "same formula," but never actually calling
`inst_ce` for comparison, so "the two formulas are equivalent" was only an
unverified assertion.

**How it was fixed (not a patch, the interface gap is closed with a real call plus
an assertion)**:

1. `_ref_forward` now actually imports and calls
   `inst_ce_fn = train_causal_callgen.inst_ce` / `train_causal_param.inst_ce`; the
   function's returned `row_ce` is `inst_ce`'s direct return value (no further
   processing before `.tolist()`) — this step satisfies spec section 9's literal
   instruction, it is no longer "a separate implementation of the same formula."
2. The intermediate value needed for the per-token threshold cannot be obtained
   from `inst_ce`, so a local `ce` (per-token) is still computed with the exact
   same shifted-prediction + mask + cross-entropy formula as `inst_ce`, for
   `tok_ce` to use; but right after each batch is processed, it immediately
   asserts that the per-row result aggregated from this local formula
   (`row_ce_local`) matches the `row_ce_inst` obtained from actually calling
   `inst_ce` (a new constant, `REF_INST_CE_DRIFT_TOL = 1e-6`; calling the same
   data through the same `no_grad` forward pass twice should in theory be
   bit-identical, so this tolerance only guards against tiny floating-point
   summation-order noise; it is an order of magnitude below `--align-tol`'s 2e-5,
   and 1000x away from a genuine formula mismatch, which would be on the order of
   1e-2 — it will not let a structural mismatch slip through). A mismatch raises
   an `AssertionError` on the spot; an unverified hand-written formula will not be
   quietly treated as the alignment check's baseline.
3. New unit test `TestRefForwardUsesInstCe` (`tests/test_share_trainer.py`),
   asserting directly against `_ref_forward` (unlike (a), which only verified the
   new path): call `_ref_forward` to get `row_ref`, then independently, without
   going through it, run the old `collate` plus a direct call to `old_inst_ce`
   using the same batching scheme (`tcs.REF_BATCH=4`); assert the two sides'
   per-row results are exactly equal with `assertEqual(diff, 0.0)` (same model,
   same batch of input, same `no_grad` forward pass, no difference in theory) —
   this test is independent of the assertion inside `_ref_forward`, verifying the
   same property once more from the outside, one test method each for
   cgen/cparam.
4. Updated the wording describing the reference path's formula in the function
   docstring and the module-level docstring (lines 22-28); it no longer says
   "self-computed per-token CE, the formula is the same as inst_ce," it now says
   "inst_ce is actually called to get the per-row ce; the intermediate value
   needed for the per-token threshold is computed locally with the same formula,
   and every batch asserts it matches inst_ce's return value."

Only these two files were changed (`pipeline/train/train_causal_share.py`,
`tests/test_share_trainer.py`); `git diff HEAD --stat` confirms
`train_causal_callgen.py`/`train_causal_param.py` have zero changes, and no other
acceptance point of the ticket was touched.

### How it was verified

**Unit tests** (same command as the ticket's acceptance section, re-run):
```
cprobe-env/bin/python -m unittest tests.test_share_trainer tests.test_share_data \
  tests.test_cparam_assembly tests.test_lora_merge
# Ran 50 tests in 218.148s / OK
```
(48 → 50, the 2 extra are the new `TestRefForwardUsesInstCe.{test_cgen,test_cparam}`;
`tests.test_share_trainer` was also run once with `-v` on its own, all 7 tests
`ok`, including these two new cases.)

**Re-ran the real Qwen3-0.6B-Base CPU smoke test** (the ticket acceptance
section's original command, `--force` overwriting the old output), and checked the
numbers exactly match the pre-fix state (section 2 of the previous round's
report):

cgen:
```
{
 "PASS": true, "n_events": 2, "n_rows": 75, "n_tgt_tokens": 1551,
 "max_abs_diff": 2.384185791015625e-06,
 "max_tok_diff": 2.193450927734375e-05,
 "baseline_max_abs_diff": 2.1457672119140625e-06, "tol": 2e-05,
 "bf16_mean_abs_diff": null, "bf16_max_abs_diff": null,
 "attn_impl": "sdpa", "mismatch_idx": [],
 "baseline_warn": false, "bf16_warn": false
}
```
`loss` 3.3317 → `val_ce` 1.2026, matches the previous round's report's numbers
position by position.

cparam:
```
{
 "PASS": true, "n_events": 2, "n_rows": 75, "n_tgt_tokens": 1090,
 "max_abs_diff": 3.5762786865234375e-06,
 "max_tok_diff": 1.33514404296875e-05,
 "baseline_max_abs_diff": 3.5762786865234375e-06, "tol": 2e-05,
 "bf16_mean_abs_diff": null, "bf16_max_abs_diff": null,
 "attn_impl": "sdpa", "mismatch_idx": [],
 "baseline_warn": false, "bf16_warn": false
}
```
Matches the previous round's report's numbers position by position (`max_abs_diff`
3.576e-6, `max_tok_diff` 1.335e-5). Neither run triggered the
`REF_INST_CE_DRIFT_TOL` assertion (no `AssertionError`, `ALIGN_CHECK.json` written
out normally). Output overwrote
`pipeline/runs/smoke/share_cpu_{cgen,cparam}_smoke/`.

**A controlled experiment on the performance impact** (the finding did not name
this as something to test, but the change makes `_ref_forward` call `inst_ce` one
extra time per batch, i.e. doubles the number of model forward passes on the
reference path; measured the order of magnitude proactively, not by guessing):
using `--align-only` (only runs the alignment check, does not enter
training/save), ran the same command (`--mode cgen --smoke --max-events 6
--align-events 2`) once before and once after on the same machine, switching to
the pre-fix code with `git stash`, running it, then restoring with
`git stash pop` and running again:
```
before the fix (after git stash): real 3m30.945s / user 84m56.327s / sys 5m59.441s
after the fix (current code):     real 6m54.556s / user 171m0.156s / sys 15m15.537s
```
Roughly 2x, matching the theoretical expectation of "the reference path calls
`inst_ce` one extra time per batch (one extra model forward pass)." This overhead
only occurs during the one-time alignment-check stage before training starts
(its scale is controlled by `--align-events`, it does not grow with the amount of
training data); it does not affect `wall_s` (the training loop's timing field does
not include the alignment check), and it does not affect any field already
reported in `train_log.jsonl`. Both measurements were taken on the same login
machine, whose current load was medium-to-high at the time (`uptime` showed a
5/15-minute load of 13-18, 64 cores, with sessions from other wave2 tickets
running at the same time), so the two absolute numbers themselves (3m30s / 6m54s)
cannot be directly compared to the previous round's report's idle-machine baseline
of "26-27 seconds," but the before/after comparison was done back-to-back within
the same time window, so the relative factor (about 2x) is the real cost of this
change, not an artifact of machine load fluctuation.

**Zero-change check on the old scripts**:
```
git diff HEAD -- pipeline/train/train_causal_callgen.py pipeline/train/train_causal_param.py
# empty output
```

**`run.py` registry (unaffected by this change, re-checked once to confirm no
collateral damage)**:
```
python3 run.py selfcheck        # 76 tasks, 14 missing, all of them third-party
                                  # env symlinks missing (a standard worktree
                                  # symptom, unrelated to train-cgen/train-cparam,
                                  # same as the previous round)
python3 -c "import ops.launch_probe"   # no output, exit code 0
python3 run.py show train-cgen --allow-dirty
#   command: .../cprobe-env/bin/python .../train_causal_share.py --mode cgen '<args...>'
```

### Commit list (this round)

- `106ab63` T03: fix 1, F1, the alignment check's reference path now really calls inst_ce instead of a hand-written substitute formula

### Self-check findings and open questions (new in this round)

1. **A tradeoff on performance**: `_ref_forward` now takes effect uniformly across
   all three call sites — the `REF_BATCH` full batch, the `bs=1` single-row
   baseline, and the cuda-side bf16 coarse screen (they share the same function),
   but only the first one (the `REF_BATCH` call) actually gates PASS/FAIL; the
   other two are only used for warnings (`baseline_warn`/`bf16_warn`), they do not
   take part in the verdict. I judge that handling this with one unified function
   (rather than forking two `_ref_forward` implementations for "used to gate" and
   "used to warn") is simpler and less likely to create a new gap of "only
   verified on one of the paths," so the real call was not applied only to the
   `REF_BATCH` call; all three sites uniformly get this guarantee, at the cost of
   doubling the forward-pass count at all three sites. This is my tradeoff, not
   something the finding named as required, listed here for the record.
2. **The tolerance value for `REF_INST_CE_DRIFT_TOL` (1e-6) has not been
   specifically verified on a real GPU environment** — both real CPU smoke runs
   and the new unit tests pass within this tolerance (and the measured drift is
   far below the threshold; on CPU, two forward passes should in theory be
   bit-identical), but whether GPU would see noise larger than 1e-6 due to
   different kernel scheduling has not been measured (this ticket's hard rule
   forbids launching GPU processes). If this check is triggered on GPU, it
   indicates a kernel-nondeterminism issue of the kind "the same model forward
   pass on the same batch of data gives two different results," not that the
   per-row formula itself is wrong; at that point this tolerance would need to be
   separately re-checked on GPU for whether it needs loosening, which is outside
   the scope this round can verify (after fix 2, even if it is genuinely
   triggered, it will now write out `ALIGN_CHECK.json` and `sys.exit(2)`, rather
   than letting the process crash with an unhandled exception — a structured
   artifact will be available when troubleshooting).

## 7. Fix round 2 (review finding N1)

Worktree: `/home/y-guo/reproduce/new1-wt/2026-08-28-wave2-T03-fix2` (deleted),
branch unchanged (`ticket/2026-08-28-wave2/T03`), base is still the ticket's
original base `2216c44d50838e6df6d3f8f78b31ca955998e520` (checked out from the
existing branch, not a new branch), previous round's head `106ab63`, new head
`312038d`.

### N1: the `REF_INST_CE_DRIFT_TOL` check is implemented with a bare `assert`,
bypassing this file's own failure-reporting channel

**The core objection in the finding text**: fix 1's new
`assert drift <= REF_INST_CE_DRIFT_TOL` is the sole runtime check that decides
whether "the reference baseline can be trusted," but it does not follow the
pattern that every other check in `run_align_check` consistently uses — compute
the result, write it into `ALIGN_CHECK.json`, print diagnostic information,
`sys.exit(2)` — it uses a bare `assert` instead. Two consequences: (1) under
`-O`/`PYTHONOPTIMIZE`, Python strips this assert out entirely, so the gap that
the F1 fix meant to close would silently reopen; (2) when it genuinely triggers
(the report already states that the 1e-6 tolerance has not been run on real GPU),
the process would crash with a bare `AssertionError` traceback, instead of first
writing out `ALIGN_CHECK.json` the way every other failure branch in the same
function does.

**Root cause**: the F1 fix implemented this check as a Python-language-level
`assert` statement, rather than this file's own failure-reporting mechanism
(`if condition: write report + print + sys.exit(2)`) — `assert` is itself a
mechanism that can be entirely disabled by an interpreter optimization switch;
using it as the sole runtime check deciding baseline trustworthiness in
production code is inconsistent with how every other check in the file is
handled, and is a newly introduced piece of writing that fights the file's
existing convention.

**How it was fixed (not a patch, the wrong logic — the bare assert — is directly
replaced with correct logic)**:

1. New exception class `RefBaselineDriftError(RuntimeError)` (defined after the
   `REF_INST_CE_DRIFT_TOL` constant), with a docstring that spells out why a bare
   `assert` cannot be used.
2. In `_ref_forward`, `assert drift <= REF_INST_CE_DRIFT_TOL, (...)` is changed to
   `if drift > REF_INST_CE_DRIFT_TOL: raise RefBaselineDriftError(...)` —
   `if`/`raise` is unaffected by `-O`/`PYTHONOPTIMIZE`, and the message text is
   kept as is.
3. A new `except RefBaselineDriftError as e:` branch is added in the middle of
   `run_align_check`'s `try/finally`, handled with the same pattern as every other
   failure branch in the file: write
   `report = dict(PASS=False, stage="ref_forward_drift", error=str(e),
   ref_inst_ce_drift_tol=REF_INST_CE_DRIFT_TOL)`, write `ALIGN_CHECK.json` to
   disk, print diagnostics (explaining what to check: whether the two formulas
   are equivalent, or whether this environment needs a looser tolerance), then
   `sys.exit(2)`. The three call sites of `_ref_forward` (the `REF_BATCH` full
   batch, the `bs=1` single-row baseline, the cuda-side bf16 coarse screen) share
   this one `except`; whichever one triggers goes through the same reporting
   path; the `finally` block (restoring precision settings, deleting the temp
   file, `model.train()`) still executes while the `SystemExit` raised by
   `sys.exit(2)` is propagating, unaffected by this change.
4. Along the way, updated the wording in `_ref_forward` and the module-level
   docstring that mentioned "a mismatch raises an `AssertionError` on the spot,"
   changing it to accurately describe the new flow (raise
   `RefBaselineDriftError` → caught by `run_align_check` → reported in
   structured form).
5. New unit test `TestRunAlignCheckHandlesRefBaselineDriftError`
   (`tests/test_share_trainer.py`), two test methods:
   - `test_ref_forward_raises_real_exception_not_assert`: monkeypatches
     `train_causal_callgen.inst_ce` (its return value uniformly gets 1.0 added,
     far past the 1e-6 tolerance), asserts directly against `_ref_forward` that
     it raises `tcs.RefBaselineDriftError` — proving this is a real exception,
     not an `assert` that `-O` would strip.
   - `test_run_align_check_reports_drift_error_instead_of_crashing`:
     monkeypatches `tcs._ref_forward` (making it directly raise
     `RefBaselineDriftError("injected drift for testing")`), calls
     `run_align_check(...)`, asserts it raises `SystemExit` with `code == 2`, and
     that `ALIGN_CHECK.json` is written to disk, `PASS` is false,
     `stage == "ref_forward_drift"`, and the `error` field contains the injected
     message — proving that a failure goes through the structured reporting
     channel, rather than letting the exception surface as-is into an unhandled
     traceback.

Only these two files were changed (`pipeline/train/train_causal_share.py`,
`tests/test_share_trainer.py`); `git diff HEAD --stat` confirms
`train_causal_callgen.py`/`train_causal_param.py` have zero changes, no other
acceptance point of the ticket was touched, and no refactoring not named by the
finding was done under cover of this change.

### How it was verified

**Unit tests** (same command as the ticket's acceptance section, re-run):
```
cprobe-env/bin/python -m unittest tests.test_share_trainer tests.test_share_data \
  tests.test_cparam_assembly tests.test_lora_merge
# Ran 52 tests in 230.616s / OK
```
(50 → 52, the 2 extra are the new
`TestRunAlignCheckHandlesRefBaselineDriftError.{test_ref_forward_raises_real_exception_not_assert,
test_run_align_check_reports_drift_error_instead_of_crashing}`; `tests.test_share_trainer`
was also run once with `-v` on its own, all 9 tests `ok`, including these two new
cases; the new cases' printed output confirms the expected behavior:
```
{
 "PASS": false,
 "stage": "ref_forward_drift",
 "error": "injected drift for testing",
 "ref_inst_ce_drift_tol": 1e-06
}
Alignment check FAIL: reference-path self-check failed, refusing to start training.
  injected drift for testing
  Check: whether the local per-token formula in _ref_forward is equivalent to inst_ce's shift/mask/aggregation logic; ...
```

**Re-ran the real Qwen3-0.6B-Base CPU smoke test** (the ticket acceptance
section's original command, `--force` overwriting the old output), and checked the
numbers exactly match the pre-fix state (the previous two rounds' reports):

cgen: `PASS: true`, `max_abs_diff: 2.384185791015625e-06`,
`max_tok_diff: 2.193450927734375e-05`, `baseline_max_abs_diff:
2.1457672119140625e-06`; `loss` 3.3317 → `val_ce` 1.2026.
cparam: `PASS: true`, `align_maxdiff: 3.5762786865234375e-06`
(the `start` event field in `train_log.jsonl`, the same number as
`ALIGN_CHECK.json`'s `max_abs_diff`); `loss` 5.6631 → `val_ce` 1.9795.
Neither run triggered the new `except RefBaselineDriftError` branch (this path
was not taken, the `if`/`raise` inside `_ref_forward` did not fire),
`ALIGN_CHECK.json` went through the normal `PASS=true` branch, output overwrote
`pipeline/runs/smoke/share_cpu_{cgen,cparam}_smoke/`.

**grep checks** (the ticket acceptance section's original commands, re-run):
```
grep -n "heartbeat.emit" pipeline/train/train_causal_share.py
# 664/740/784, all three unchanged
grep -n "sdpa_kernel" pipeline/train/train_causal_share.py
# hits unchanged
grep -n "^\s*assert " pipeline/train/train_causal_share.py
# empty output — the whole file no longer has a bare assert
```

**Zero-change check on the old scripts**:
```
git diff HEAD -- pipeline/train/train_causal_callgen.py pipeline/train/train_causal_param.py
# empty output
```

**`run.py` registry (unaffected by this change, re-checked once to confirm no
collateral damage)**:
```
python3 run.py selfcheck        # 76 tasks, 14 missing, all of them third-party
                                  # env symlinks missing (a standard worktree
                                  # symptom, unrelated to train-cgen/train-cparam,
                                  # same as the previous two rounds)
python3 -c "import ops.launch_probe"   # no output, exit code 0
python3 run.py show train-cgen --allow-dirty
#   command: .../cprobe-env/bin/python .../train_causal_share.py --mode cgen '<args...>'
```

`git diff HEAD --stat`:
```
 pipeline/train/train_causal_share.py | 47 +++++++++++++++++----
 tests/test_share_trainer.py          | 81 ++++++++++++++++++++++++++++++++++++
 2 files changed, 121 insertions(+), 7 deletions(-)
```

### Commit list (this round)

- `312038d` T03: fix 2, N1, the alignment check's reference-baseline self-check now raises a real exception with structured reporting, no longer a bare assert

### Self-check findings and open questions (new in this round)

1. **Other than the new `except RefBaselineDriftError` added between the
   `try/finally`, no other logic in `run_align_check` was touched** — the code
   and behavior of the two existing paths, normal PASS and normal FAIL (per-row
   difference over `--align-tol` or per-token difference over `TOK_DIFF_TOL`),
   are unchanged word for word; only a third failure path (reference-baseline
   self-check failure) was added and wired into the same report/print/
   sys.exit(2) skeleton, without refactoring any other branch under cover of this
   change, matching the finding's scope limit of fixing only this one spot.
2. **The report dict fields written by the `except RefBaselineDriftError`
   branch are not fully the same as the normal path's report fields** (missing
   fields like `n_events`/`n_rows`/`max_abs_diff`, because these values are
   simply never computed when the reference-baseline self-check fails; it adds
   two extra fields, `stage`/`ref_inst_ce_drift_tol`, to distinguish which kind of
   failure this is) — so the two paths' `ALIGN_CHECK.json` schemas are not fully
   consistent (the only thing they share is that `PASS` is always present). The
   finding only requires "go through the same write-report + print + exit
   channel," it does not require the two failure types' field schemas to be
   fully unified; I judge that if downstream code consuming `ALIGN_CHECK.json`
   (currently there is none, it is read by a person) later needs to parse this
   file mechanically, it should check `PASS` first and then read the rest of the
   fields as needed, rather than assuming a fixed field set; this is my
   tradeoff, listed here for the record, not something this round needs to
   resolve.
3. **Whether `REF_INST_CE_DRIFT_TOL` needs loosening on real GPU is still
   unverified** (same as self-check item 2 in the previous round, this ticket's
   hard rule forbids launching GPU processes, unchanged) — the only difference
   is: in the previous round, if this check were genuinely triggered on GPU, the
   process would crash with an unhandled `AssertionError`; this round, once
   triggered, it will write out a structured `ALIGN_CHECK.json` and then
   `sys.exit(2)`; when troubleshooting, one can see `stage: "ref_forward_drift"`
   and the concrete drift value, no longer a bare traceback.
