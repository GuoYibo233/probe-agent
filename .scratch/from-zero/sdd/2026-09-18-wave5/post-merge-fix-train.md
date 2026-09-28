# Wave 5 post-merge fix — train (trainer.py, the three methods, test_packed_loss.py)

Base: `9c3b963` (branch `from-zero`; the merge under review, `df3c473`, plus the
commit that recorded `post-merge-review.json`).
Head: `225d951` on branch `fix/2026-09-18-wave5-train`.
Worktree: `/home/y-guo/reproduce/new1-wt/2026-09-18-wave5-fix-train-r1`, removed
after the commits; the branch is kept.

Findings fixed: TRAINER-1 (= PACKING-02 = SEAMS-1), PACKING-01 (= SEAMS-2),
TRAINER-2, PACKING-03, TRAINER-3, TRAINER-4, TRAINER-6.

Files changed: `train/utils/trainer.py`, `train/methods/ctool.py`,
`train/methods/cgen.py`, `train/methods/cparam.py`, `tests/test_packed_loss.py`.
No import of any of the four code files changed, so no `README.md` annotation
line changes and `README.md` is untouched.

Commits:

| sha | what |
|---|---|
| `e632144` | `trainer.py`: TRAINER-1, TRAINER-2, TRAINER-3, TRAINER-4, TRAINER-6 |
| `09856de` | the three method files: PACKING-01 and PACKING-03 |
| `225d951` | `tests/test_packed_loss.py`: the three fixtures that tell the two sides apart |

The repro scripts live in `/tmp/wave5fix_train/` (`harness.py`, `repro_trainer1.py`,
`repro_trainer2.py`, `repro_trainer3.py`, `repro_trainer4.py`, `repro_packing01.py`,
`repro_packing03.py`, `a34_a35.py`), with a `git archive` export of the base at
`/tmp/wave5fix_train/base_tree` for the before-side runs. `$PR` below is
`/home/y-guo/reproduce/new1/external/probe-env/bin/python`. Every command is CPU
only; no GPU process was started.

---

## TRAINER-1 (= PACKING-02 = SEAMS-1) — critical

**Root cause.** `_batches_with_epoch_end` computed one flag,
`is_epoch_end = nxt is None or nxt["mb"] != prev["mb"]`, from a one-item
lookahead. That expression is the end of a *logical minibatch*, not the end of
the epoch, and both consumers read it as the epoch end: the step gate
`len(seen_mbs) >= cfg.train.accum or is_epoch_end` therefore fired an optimizer
step at every minibatch boundary whatever `train.accum` said, and
`if is_epoch_end: _validate_and_maybe_save(ep)` ran a whole validation per
minibatch. Because `steps` is still planned as
`ceil(ceil(n_train_events / events_per_mb) / accum) * epochs`, `gstep` reached
that budget after `1/accum` of the epoch's minibatches and `if gstep >= steps:
break` ended the run there. A second, independent half of the same defect:
`seen_mbs.add(mb)` ran on *every* physical block, so a minibatch that spans
several blocks was counted as complete on its first block and the step fired
with the rest of its gradient missing.

**The change** (`train/utils/trainer.py`). The lookahead yields the two facts it
actually has, under their own names: `_batches_with_flags` yields
`(batch, is_mb_end, is_epoch_end)` with `is_mb_end = nxt is None or nxt["mb"] !=
prev["mb"]` and `is_epoch_end = nxt is None`. A minibatch enters `seen_mbs` when
its **last** physical block has its gradient in (`if is_mb_end:
seen_mbs.add(mb)`), in the step loop and in the resume fast-forward alike, so the
step gate `len(seen_mbs) >= cfg.train.accum or is_epoch_end` now means what it
says: after `accum` complete minibatches, or at the end of the epoch. Validation
reads `is_epoch_end`, which is true once per epoch, matching errata line 171.

**Repro rerun** — `$PR /tmp/wave5fix_train/repro_trainer1.py`, run from the base
export and from the fix worktree. Scenario A is the shape the dispatch asked for
(6 train events, `events_per_mb=1`, `accum=2`, `epochs=1`); scenario B is a
logical minibatch that spans several physical blocks (8 events,
`events_per_mb=4`, `accum=1`, `max_len=24`).

Before, at `9c3b963`:

```
[A] one epoch: 6 logical minibatches, 6 physical blocks
[A] steps the trainer planned   : 3
[A] optimizer steps taken       : 3
[A] physical blocks trained on  : 3 of 6
[A] distinct minibatches trained: 3 of 6 -> [0, 1, 2]
[A] validate() calls            : 3
[A] eval lines in train_log     : 3
[B] one epoch: 2 logical minibatches, 4 physical blocks
[B] steps the trainer planned   : 2
[B] optimizer steps taken       : 2
[B] physical blocks trained on  : 2 of 4
[B] distinct minibatches trained: 1 of 2 -> [0]
[B] validate() calls            : 1
[B] eval lines in train_log     : 1
```

After, at `225d951`:

```
[A] one epoch: 6 logical minibatches, 6 physical blocks
[A] steps the trainer planned   : 3
[A] optimizer steps taken       : 3
[A] physical blocks trained on  : 6 of 6
[A] distinct minibatches trained: 6 of 6 -> [0, 1, 2, 3, 4, 5]
[A] validate() calls            : 1
[A] eval lines in train_log     : 1
[B] one epoch: 2 logical minibatches, 4 physical blocks
[B] steps the trainer planned   : 2
[B] optimizer steps taken       : 2
[B] physical blocks trained on  : 4 of 4
[B] distinct minibatches trained: 2 of 2 -> [0, 1]
[B] validate() calls            : 1
[B] eval lines in train_log     : 1
```

3 optimizer steps cover all 6 minibatches and one epoch validates once; a
minibatch of 2 physical blocks contributes both blocks to its step. A3.4 and A3.5
are rerun in full under "Acceptance" below.

---

## PACKING-01 (= SEAMS-2) — critical

**Root cause.** `Probe.forward` (`models/probe_models/base.py:89-111`) moves the
four keys it consumes to the backbone's device and returns `Outputs.logits`
there, and `trainer.run` loads the backbone with `device="cuda"` whenever a card
is visible. The three methods pack their batches on the CPU and then combined
those CPU tensors with device-side logits: `ctool`'s class indices and
`batch["weight"]`, and `cgen`/`cparam`'s `target_ids`, `row_of` and the two
`torch.zeros(n_rows)` accumulators. `F.cross_entropy` and `index_add` refuse a
cross-device pair, so the first loss call of a launched run raised — inside
`_run_alignment_gate`, before the first optimizer step, with the schema default
`align_check: true`, for all three methods; `reference_loss` had the same split.

**The change** (`ctool.loss`, `ctool.reference_loss`, `cgen._row_mean_ce`,
`cgen.loss`, `cgen.reference_loss`, `cparam._row_mean_ce`, `cparam.loss`,
`cparam.reference_loss`). Each reads `device = out.logits.device` off the model's
own outputs and builds every tensor it makes beside them there; the two tensors
that come out of the batch (`weight`, and `target_ids`/`row_of`) are moved to
that device at the point of use. The device is never named, never read from a
setting and never guessed — it is whatever the probe's outputs came back on, so
the same code is correct on the CPU and on a card.

**Repro rerun** — `$PR /tmp/wave5fix_train/repro_packing01.py`. A stub probe
keeps `base.Probe.forward`'s contract (it moves the four backbone keys itself and
returns outputs on the probe's device) with torch's `meta` device standing in for
a card, which enforces the same same-device rule; the batches are the real ones
each method's own `batches()` yields.

Before, at `9c3b963`:

```
same-device rule on meta : RuntimeError - Tensor on device meta is not on the expected device cpu!
ctool: batch tensors on -> {'input_ids': 'cpu', 'attention_mask': 'cpu', 'position_ids': 'cpu', 'event_end': 'cpu', 'weight': 'cpu'}
  ctool.loss -> RuntimeError: Tensor on device meta is not on the expected device cpu!
  ctool.reference_loss -> RuntimeError: Tensor on device meta is not on the expected device cpu!
cgen: batch tensors on -> {'input_ids': 'cpu', ..., 'target_ids': 'cpu', 'row_of': 'cpu', 'weight': 'cpu'}
  cgen.loss -> RuntimeError: Tensor on device meta is not on the expected device cpu!
  cgen.reference_loss -> RuntimeError: Tensor on device meta is not on the expected device cpu!
cparam: batch tensors on -> {'input_ids': 'cpu', ..., 'target_ids': 'cpu', 'row_of': 'cpu', 'weight': 'cpu'}
  cparam.loss -> RuntimeError: Tensor on device meta is not on the expected device cpu!
  cparam.reference_loss -> RuntimeError: Tensor on device meta is not on the expected device cpu!
```

After, at `225d951`:

```
same-device rule on meta : RuntimeError - Tensor on device meta is not on the expected device cpu!
ctool: batch tensors on -> {'input_ids': 'cpu', 'attention_mask': 'cpu', 'position_ids': 'cpu', 'event_end': 'cpu', 'weight': 'cpu'}
  ctool.loss -> ok, result on meta
  ctool.reference_loss -> ok, result on meta
cgen: batch tensors on -> {'input_ids': 'cpu', ..., 'target_ids': 'cpu', 'row_of': 'cpu', 'weight': 'cpu'}
  cgen.loss -> ok, result on meta
  cgen.reference_loss -> ok, result on meta
cparam: batch tensors on -> {'input_ids': 'cpu', ..., 'target_ids': 'cpu', 'row_of': 'cpu', 'weight': 'cpu'}
  cparam.loss -> ok, result on meta
  cparam.reference_loss -> ok, result on meta
```

(The two `batch tensors on` lines are elided at `...` here exactly as the review
recorded them; the script prints every key.) The numbers are unchanged on the
CPU: A3.3 and A3.6 below.

---

## TRAINER-2 — important

**Root cause.** `trainer.run` never put the probe into training mode itself.
`base.load` returns it in eval mode (`from_pretrained` ends with `model.eval()`),
and the only two calls that turned training on were the alignment gate's
`finally` and the restore after a validation. The gate is guarded by
`if cfg.train.align_check and resume_step is None:`, so a setting with
`align_check: false` and **every** resume reached the step loop in eval mode, and
with `epochs: 1` stayed there for the whole run. Beyond dropout, transformers
checkpoints activations only for a module in training mode
(`if self.gradient_checkpointing and self.training`), so `probe.grad_checkpointing(True)`
was a silent no-op on exactly those paths.

**The change** (`train/utils/trainer.py`). `run` owns the training mode: after the
alignment gate and before the step loop it calls `probe.set_training(True)` and
then arms `probe.grad_checkpointing(True)` when `cfg.train.grad_ckpt`, on every
path that trains. The `grad_checkpointing` call moved out of the load block into
this one, so a predict-only continuation no longer arms a feature only a backward
pass uses. `_run_alignment_gate`'s `finally` no longer calls
`set_training(True)`: the gate switches to eval mode for its own comparison and
`run` is the single place that decides the mode the step loop runs in — which is
the whole point, since the paths that skip the gate have to reach it too.

**Repro rerun** — `$PR /tmp/wave5fix_train/repro_trainer2.py`. The stub probe's
backbone is put in eval mode before each `run`, which is what `base.load` hands
back. The crash case saves `last/` with `checkpoint_hours=0.0` and raises after
two backwards; the relaunch resumes from it.

Before, at `9c3b963`:

```
align_check=True : backbone.training at the first training loss = True; probe calls before it = ['grad_checkpointing(True)', 'set_training(False)', 'set_training(True)']
align_check=False: backbone.training at the first training loss = False; probe calls before it = ['grad_checkpointing(True)']
crash run        : backbone.training at the first training loss = True; probe calls before it = ['grad_checkpointing(True)', 'set_training(False)', 'set_training(True)']
last/meta.json step/epoch/commit   : 1 0 deadbee
after the resume : backbone.training at the first training loss = False; probe calls before it = ['grad_checkpointing(True)']
```

After, at `225d951`:

```
align_check=True : backbone.training at the first training loss = True; probe calls before it = ['set_training(False)', 'set_training(True)', 'grad_checkpointing(True)']
align_check=False: backbone.training at the first training loss = True; probe calls before it = ['set_training(True)', 'grad_checkpointing(True)']
crash run        : backbone.training at the first training loss = True; probe calls before it = ['set_training(False)', 'set_training(True)', 'grad_checkpointing(True)']
last/meta.json step/epoch/commit   : 1 0 deadbee
after the resume : backbone.training at the first training loss = True; probe calls before it = ['set_training(True)', 'grad_checkpointing(True)']
```

All four paths now reach the first training loss in training mode, and
`grad_checkpointing` is armed after the mode is on.

---

## PACKING-03 — important

**Root cause, and the rule taken.** The gate compares `sum(loss over batches)`
against `reference_loss`, both divided by `slice_df.height`. `batches()` decides
which rows survive; `reference_loss` decided separately, and differently:

- it tokenized every row of the frame, while `batches()` drops an event whole
  when its longest text exceeds `max_len` (errata 5.2, `counts.dropped_overlong`);
- for `cgen`/`cparam` it kept a row whose target exceeds `MAX_TGT_TOK = 160`,
  which `batches()` drops;
- for `cgen`/`cparam` it left-truncated the prompt to `max_len - len(target)`,
  while the packed path never truncates — it drops the over-long event instead.

**The rule I took: `reference_loss` scores exactly the rows `batches()` keeps and
shows each of them the same tokens.** That is the root because contracts 2.6
defines `reference_loss` as "the same loss computed one example row per sequence,
in its plainest form, over a slice of the same example-row frame `trainer.run`
hands `batches`", and 2.5 makes any difference above `1e-4` a hard stop that
names the packing. "The same loss on the same rows" is the hook's whole job; the
row set and the length policy are not the thing being tested — the packing is.
The two alternatives are both worse. Moving the drops into the packed path is
ruled out: errata line 118 pins the drop-whole rule and left-truncating inside
`batches()` would destroy the shared token prefix the packing is built on.
Filtering the gate's slice inside `trainer.run` is ruled out too: the trainer
would have to know which rows a method drops, and 2.6 forbids it branching on the
method (there is no hook that reports the kept rows). So the plain side is the
one that moves. The left-truncation the ticket pins for `cgen`/`cparam`'s
`reference_loss` ("left-truncated prompt", ported from legacy's `collate`) is the
one place where I follow the contract over the ticket's own wording: legacy's
batching truncated, this tree's drops whole, and a plain path that truncates
where the packed path does not makes the gate report a packing bug on correct
packing. Flagged here as the reviewer's case (b) already flagged it.

**The change** (`ctool.reference_loss`, `cgen.reference_loss`,
`cparam.reference_loss`). Each walks the frame by `event_id`, skips an event
whose longest text tokenizes past `probe.max_len` (which `base.load` sets from
`cfg.train.max_len`), and inside a kept event skips the rows its own `batches()`
skips — the target over `MAX_TGT_TOK` for both generators, the target that does
not assemble for `cparam`. The prompt is no longer truncated. The drop rules are
written out a second time rather than shared with `_build_events`, which is 2.6's
"the one piece of code written twice on purpose": sharing them would make the two
sides agree by construction and the gate would stop testing anything. An empty
row set returns `torch.zeros(())`, which matches the packed side's empty sum.

**Repro rerun** — `$PR /tmp/wave5fix_train/repro_packing03.py`, every case driven
through the shipped gate `trainer._run_alignment_gate` with the whole fixture
inside the slice. (The tiny model is initialised at random per process, so the
loss values differ run to run; the `diff` column is the claim.)

Before, at `9c3b963`:

```
control (A3.3 fixture, max_len=512):
  [control] ctool: packed=1.36843793 plain=1.36843793 diff=0.000e+00 n_rows=6 PASS=True -> PASS
  [control] cgen: packed=11.88723501 plain=11.88723373 diff=1.272e-06 n_rows=6 PASS=True -> PASS
  [control] cparam: packed=11.60412216 plain=11.60412216 diff=0.000e+00 n_rows=6 PASS=True -> PASS
(a) overlong event, max_len=64 (longest text = 100 tokens):
  [overlong] ctool: packed=0.78722914 plain=1.28932031 diff=5.021e-01 n_rows=6 PASS=False -> SystemExit
  [overlong] cgen: packed=6.01132393 plain=11.91383616 diff=5.903e+00 n_rows=6 PASS=False -> SystemExit
  [overlong] cparam: packed=5.73521932 plain=11.53659948 diff=5.801e+00 n_rows=6 PASS=False -> SystemExit
(b) truncation band, max_len=32 (longest text = 30 tokens, text+sep = 35 tokens, target = 7 tokens):
  [band] cgen: packed=12.08834457 plain=12.11332957 diff=2.498e-02 n_rows=3 PASS=False -> SystemExit
  [band] cparam: packed=11.71421432 plain=11.59412511 diff=1.201e-01 n_rows=3 PASS=False -> SystemExit
(c) target over MAX_TGT_TOK, max_len=512 (target = 206 tokens):
  [maxtgt] cgen: packed=6.01132393 plain=12.25170135 diff=6.240e+00 n_rows=6 PASS=False -> SystemExit
  [maxtgt] cparam: packed=5.73521932 plain=11.96529770 diff=6.230e+00 n_rows=6 PASS=False -> SystemExit
```

After, at `225d951`:

```
control (A3.3 fixture, max_len=512):
  [control] ctool: packed=1.21021040 plain=1.21021032 diff=7.947e-08 n_rows=6 PASS=True -> PASS
  [control] cgen: packed=12.02303441 plain=12.02303441 diff=0.000e+00 n_rows=6 PASS=True -> PASS
  [control] cparam: packed=12.09836070 plain=12.09836070 diff=0.000e+00 n_rows=6 PASS=True -> PASS
(a) overlong event, max_len=64 (longest text = 100 tokens):
  [overlong] ctool: packed=0.73696852 plain=0.73696852 diff=0.000e+00 n_rows=6 PASS=True -> PASS
  [overlong] cgen: packed=5.85683886 plain=5.85683886 diff=0.000e+00 n_rows=6 PASS=True -> PASS
  [overlong] cparam: packed=6.03128815 plain=6.03128815 diff=0.000e+00 n_rows=6 PASS=True -> PASS
(b) truncation band, max_len=32 (longest text = 30 tokens, text+sep = 35 tokens, target = 7 tokens):
  [band] cgen: packed=11.71064504 plain=11.71064504 diff=0.000e+00 n_rows=3 PASS=True -> PASS
  [band] cparam: packed=12.13173421 plain=12.13173421 diff=0.000e+00 n_rows=3 PASS=True -> PASS
(c) target over MAX_TGT_TOK, max_len=512 (target = 206 tokens):
  [maxtgt] cgen: packed=5.85683886 plain=5.85683886 diff=0.000e+00 n_rows=6 PASS=True -> PASS
  [maxtgt] cparam: packed=6.03128815 plain=6.03128815 diff=0.000e+00 n_rows=6 PASS=True -> PASS
```

The three fixtures are now permanent: `tests/test_packed_loss.py` walks them as
subtests of the same three test methods (below).

---

## TRAINER-3 — minor

**Root cause.** The step line and the loss-carrying beat sat behind
`if gstep % LOG_EVERY == 0:` with `LOG_EVERY = 50`, and nothing wrote a line when
the loop ended. `experimental_settings/debug.yaml` sets `train.max_steps: 20`, so
a `--debug` train never satisfied the condition once and GPU acceptance item 1's
"at least one `step` line" could not pass.

**The change.** `LOG_EVERY` stays 50, the ticket's pinned constant. The cadence
gains the two steps a reader always wants: `if gstep == 1 or gstep % LOG_EVERY ==
0 or gstep >= steps:`. A run whose last step is not one of those three — the
method dropped events, so the loop ends below the planned `steps` — gets its line
after the loop, guarded on there being a loss to report
(`if gstep > last_logged_step and window_loss_n > 0:`), which also keeps a resume
that trains nothing from writing a step line with a loss of 0. The line and the
beat are one function, `_log_step`, so the two can never drift apart.

**Repro rerun** — `$PR /tmp/wave5fix_train/repro_trainer3.py` (25 train events,
`accum=1`, `max_steps=20`, debug.yaml's value).

Before, at `9c3b963`:

```
LOG_EVERY                    : 50
gstep reached                : 20
train_log.jsonl event counts : {'start': 1, 'eval': 20, 'save_best': 1}
step lines at gstep          : []
beats                        : 42  with a loss field: 0
```

After, at `225d951`:

```
LOG_EVERY                    : 50
gstep reached                : 20
train_log.jsonl event counts : {'start': 1, 'step': 2, 'eval': 1, 'save_best': 1}
step lines at gstep          : [1, 20]
beats                        : 9  with a loss field: 2
```

The `eval` count falling from 20 to 1 is TRAINER-1's fix showing in the same run:
one epoch, one validation.

---

## TRAINER-4 — minor

**Root cause.** The only `hb.emit(0, total, unit)` sat inside
`if not predict_only:`, so 2.4's predict-only incarnation wrote nothing into its
heartbeat file until `finish()`; `registry.judge` on a piece with no beat
compares its age against `DEFAULTS["warmup_s"] = 1800` and returns
`suspected stall` after 30 minutes. On the trained path the last step beat
carried `done == total`, which `judge` returns `done` on, while the whole
prediction pass was still ahead.

**The change.** The prediction pass is a phase with its own beats, on both paths,
with no branch: `hb.emit(0, predict_total, "step")` before the loop and
`hb.emit(i + 1, predict_total, "step")` after each split's predictions are in
hand. **The unit I chose is `"step"`** — 8.4 gives the unit per stage, not per
phase, and `step` is the word it gives `train`; the verdict functions read the
word but never branch on it. **The total I chose is `len(splits) + 1`**: the
splits plus the one frame their rows are joined into and written to, so the last
beat before `finish()` reads `done = len(splits) < total` and the piece is called
done only by `finish()`'s own `status: "done"` — and, on the trained path, the
step loop's `done == total` beat is superseded the moment prediction starts.

**Repro rerun** — `$PR /tmp/wave5fix_train/repro_trainer4.py`. It runs a full
train, deletes `done.json` and `predictions.parquet`, relaunches into the
predict-only path, and snapshots the heartbeat directory at the first
`method.predict` call — the state a monitor sees mid-prediction — then runs
`registry.judge` over the snapshot one hour after the piece's launch.

Before, at `9c3b963`:

```
heartbeat files                    : ['0-0.jsonl', '0-1.jsonl']
trained: newest heartbeat at the first predict() call = 0-0.jsonl, beats = [(0, 2, 'step'), (1, 2, 'step'), (1, 2, 'step'), (2, 2, 'step'), (2, 2, 'step')]
  registry.judge(piece, 1 h in) -> ('done', False) (warmup_s = 1800)
predict_only: newest heartbeat at the first predict() call = 0-1.jsonl, beats = []
  registry.judge(piece, 1 h in) -> ('suspected stall', False) (warmup_s = 1800)
0-0.jsonl: 6 beats, before finish() -> [(0, 2, 'step'), (1, 2, 'step'), (1, 2, 'step'), (2, 2, 'step'), (2, 2, 'step')]
0-1.jsonl: 1 beats, before finish() -> []
```

After, at `225d951`:

```
heartbeat files                    : ['0-0.jsonl', '0-1.jsonl']
trained: newest heartbeat at the first predict() call = 0-0.jsonl, beats = [(0, 2, 'step'), (1, 2, 'step'), (2, 2, 'step'), (2, 2, 'step'), (2, 2, 'step'), (0, 3, 'step')]
  registry.judge(piece, 1 h in) -> ('healthy', False) (warmup_s = 1800)
predict_only: newest heartbeat at the first predict() call = 0-1.jsonl, beats = [(0, 3, 'step')]
  registry.judge(piece, 1 h in) -> ('healthy', False) (warmup_s = 1800)
0-0.jsonl: 9 beats, before finish() -> [(0, 2, 'step'), (1, 2, 'step'), (2, 2, 'step'), (2, 2, 'step'), (2, 2, 'step'), (0, 3, 'step'), (1, 3, 'step'), (2, 3, 'step')]
0-1.jsonl: 4 beats, before finish() -> [(0, 3, 'step'), (1, 3, 'step'), (2, 3, 'step')]
```

Neither incarnation reads `done` or `suspected stall` while its predictions are
being written, and the last beat before `finish()` on both is `(2, 3, 'step')`.
`jobs/registry.rates` guards both of its subtractions with `>=`, so the `total`
changing between the two phases yields `None` rates rather than a wrong one, and
`judge` falls through to `healthy`.

---

## TRAINER-6 — minor

**Root cause.** The module comment stated a default the schema does not have. The
owner ruled on `train.warmup_ratio` in wave 4 (errata line 172, merged as
`2169c4e`): the default is `0.05`, the share the old trainer hard-coded.

**The change.** The comment states the real default and the real consequence.

**Repro rerun.**

```
$ sed -n '34,36p' /tmp/wave5fix_train/base_tree/train/utils/trainer.py     # before, at 9c3b963
# Behaviour change worth stating here (construction plan): train.warmup_ratio defaults to 0.0
# in experimental_settings/schema.py; the previous pipeline hardcoded a warmup of 5% of steps.
# A setting that wants that schedule writes warmup_ratio: 0.05 explicitly.

$ sed -n '34,37p' train/utils/trainer.py                                   # after, at 225d951
# The learning-rate schedule, stated here because a reader looks for it: train.warmup_ratio
# defaults to 0.05 in experimental_settings/schema.py, the share of steps the previous pipeline
# hardcoded, so a setting that says nothing warms over the first 5% of its steps and a setting
# that wants no warmup writes warmup_ratio: 0.0 explicitly.

$ grep -n 'warmup_ratio' experimental_settings/schema.py
105:    warmup_ratio: float = 0.05                   # share of steps spent warming the schedule
```

---

## The permanent test

`tests/test_packed_loss.py` keeps its three test methods, so A3.6 still reports
`ctool`, `cgen` and `cparam` and its pinned expectation ("three tests") holds.
Each now walks four fixtures as subtests: the original two events of nested
prefixes, an event whose longest text is over `max_len`, an event whose target is
over `MAX_TGT_TOK`, and an event whose prompt sits just under `max_len`. The
fixture the file shipped with passes on both trees, which is how PACKING-03
reached the merge; the three new ones tell the sides apart. Run against a
`git archive` export of `9c3b963` with only this test file copied in:

```
$ cd /tmp/wave5fix_train/base_tree && $PR -m unittest tests.test_packed_loss -v
FAIL: test_cgen (case='an event whose longest text is over max_len')
AssertionError: 6.102222442626953 not less than 0.0001 : cgen [...]: packed=6.105906168619792 plain=12.208128611246744 diff=6.102222442626953
FAIL: test_cgen (case='an event whose target is over MAX_TGT_TOK')
AssertionError: 5.817029317220052 not less than 0.0001 : cgen [...]: packed=6.105906168619792 plain=11.922935485839844 diff=5.817029317220052
FAIL: test_cgen (case='an event whose prompt sits just under max_len')
AssertionError: 0.029568990071614582 not less than 0.0001 : cgen [...]: packed=12.369956970214844 plain=12.340387980143229 diff=0.029568990071614582
FAIL: test_cparam (case='an event whose longest text is over max_len')
AssertionError: 6.082503000895183 not less than 0.0001 : cparam [...]: packed=6.159628550211589 plain=12.242131551106771 diff=6.082503000895183
FAIL: test_cparam (case='an event whose target is over MAX_TGT_TOK')
AssertionError: 5.821343739827474 not less than 0.0001 : cparam [...]: packed=6.159628550211589 plain=11.980972290039062 diff=5.821343739827474
FAIL: test_cparam (case='an event whose prompt sits just under max_len')
AssertionError: 0.09520848592122395 not less than 0.0001 : cparam [...]: packed=11.998575846354166 plain=11.903367360432943 diff=0.09520848592122395
FAIL: test_ctool (case='an event whose longest text is over max_len')
AssertionError: 0.6518583297729492 not less than 0.0001 : ctool [...]: packed=0.559240976969401 plain=1.2110993067423503 diff=0.6518583297729492
Ran 3 tests in 2.739s
```

Seven subtest failures before, twelve subtests passing after (A3.6 below).

---

## Acceptance — ticket 13, rerun in full at `225d951`

All seven of ticket 13's CPU acceptance commands were rerun verbatim from the
worktree root. A3.3, A3.4, A3.5 and A3.6 are the ones that touch the changed
files; A3.1, A3.2 and A3.7 are run because they cover the same four files.

**A3.1 — the literal rules of 3.3, and the `PROBE_KIND` pair** (`python3 - <<'PY' ... PY`):

```
OK
exit=0
```

**A3.2 — import under the probe venv:**

```
$ "$PR" -c "import train.utils.trainer as t, train.methods.ctool as c, train.methods.cgen as g, train.methods.cparam as p; print(t.VERSION, c.PROBE_KIND, g.PROBE_KIND, p.PROBE_KIND, p.CHECKPOINT_META['param_only'])"
1 classifier generator generator True
exit=0
```

**A3.3 — the packed loss equals the plain loss, per method** (the ticket's
`for M in ctool cgen cparam` loop):

```
ctool packed=1.10491896 plain=1.10491896 diff=0.000e+00
OK
exit=0
cgen packed=12.09551112 plain=12.09551112 diff=0.000e+00
OK
exit=0
cparam packed=12.11617915 plain=12.11617788 diff=1.272e-06
OK
exit=0
```

**A3.4 + A3.5 — the whole loop on CPU, and the 2.4 continue rule.** The ticket's
A3.4 script with A3.5 appended after its last print, run as
`"$PR" - < /tmp/wave5fix_train/a34_a35.py` (the same stdin form the ticket's
heredoc uses; `@hb` stdout lines filtered):

```
['depth', 'event_id', 'example_id', 'gen_tokens', 'label_pred', 'logits', 'method', 'score', 'split', 'target', 'task_id', 'text_pred', 'tool', 'version']
['test', 'val'] 24
['phone.login', 'phone.pay']
True
True True
done
a True True
b 24 True
c True True
exit=0
```

Every line matches the ticket's expected output, A3.5's `a True True`, `b 24 True`
and `c True True` included.

**A3.6 — the permanent packed-loss test:**

```
$ "$PR" -m unittest tests.test_packed_loss -v
test_cgen (tests.test_packed_loss.TestPackedLoss.test_cgen) ... ok
test_cparam (tests.test_packed_loss.TestPackedLoss.test_cparam) ... ok
test_ctool (tests.test_packed_loss.TestPackedLoss.test_ctool) ... ok

----------------------------------------------------------------------
Ran 3 tests in 2.528s

OK
exit=0
```

**A3.7 — no absolute cluster path in the code:**

```
$ grep -n "/home/\|/net/" train/utils/trainer.py train/methods/*.py || echo NO_ABS_PATH
NO_ABS_PATH
```

**The other test in `tests/`**, run because the trainer's heartbeat use changed:

```
$ "$PR" -m unittest tests.test_registry_concurrent_append -v
test_eight_processes_land_all_160_rows ... ok
Ran 1 test in 0.201s
OK
```

**`run.py selfcheck`** is not runnable on this branch yet:

```
$ "$PR" run.py selfcheck
selfcheck arrives in ticket 15
exit=1
```

The seven GPU acceptance items of ticket 13 remain BLOCKED for the main session;
no GPU process was started here. Items 1, 2, 3, 4 and 7 are the ones these fixes
change the outcome of.

---

## Decisions the requirements did not make

1. **PACKING-03: the plain side moves, not the packed side, and not the gate's
   slice.** Stated in full above. The consequence worth the owner's eye: ticket
   13's sentence "left-truncated prompt" for `cgen`/`cparam`'s `reference_loss`
   is no longer followed — it was ported from legacy's `collate`, whose batching
   truncated too, while this tree's `batches()` drops an over-long event whole
   (errata line 118). Keeping both would make the gate fail a correct run for
   every row whose prompt lands within `len(target) + len(call_sep)` tokens of
   `max_len`.
2. **PACKING-03: the drop rules are written out twice, not shared.**
   `reference_loss` re-derives which rows survive instead of calling
   `_build_events`. Sharing the code would make both sides agree by construction
   and the gate would stop catching anything — 2.6 calls this "the one piece of
   code written twice on purpose".
3. **TRAINER-2: the alignment gate no longer restores training mode.** Ticket 13
   step 8 says the gate runs with `set_training(False)` "restored afterwards";
   that restore is now `run`'s, immediately after the gate returns, because the
   paths that skip the gate need the same call and two owners of one flag is what
   hid this defect. The observable order on the `align_check: true` path is
   unchanged.
4. **TRAINER-2: `grad_checkpointing` moved into the training branch.** It used to
   be armed right after `base.load`, which also armed it for a predict-only
   continuation that never runs a backward. It is now armed after
   `set_training(True)`, inside `if not predict_only:`.
5. **TRAINER-4: the unit is `"step"` and the total is `len(splits) + 1`.** 8.4
   assigns the unit per stage, so the prediction phase keeps `train`'s word; the
   total counts the splits plus the frame write, which is the reason the last
   beat before `finish()` reads `2/3` rather than `3/3`. A monitor therefore
   shows a train piece switching from `N/steps step` to `0/3 step` when its
   prediction pass starts. If the owner would rather see a distinct word there
   (`split`), it is a one-word change in one call.
6. **TRAINER-3: three logging points, not a smaller `LOG_EVERY`.** The constant
   is the ticket's, and lowering it would change what a long run writes. The
   first and last step are added instead, and the post-loop line is guarded on
   there being a loss in the window so a resume that trains nothing writes no
   step line.
7. **The test file keeps exactly three test methods.** The new fixtures are
   subtests, so A3.6's pinned "three tests" expectation still reads true while
   the regression coverage lands.
8. **`README.md` untouched.** No import, venv, reads or writes line of the four
   files changed.
9. **The report file is not committed.** It is written into the main repo's
   working tree at the path the dispatch gave; other sessions are working in that
   tree, so the commit is left to the main session.

## Open, not fixed here (outside this area or outside these findings)

- The minors wave 5 already recorded and left open (F6 cparam's `target = None`
  row, N1 the stale contracts attribution at `trainer.py:167`, the resume that
  does not carry the pre-crash best objective, `counts.dropped_overlong` counting
  the train split only) are untouched: none is in the list I was given.
- `counts.dropped_overlong` is computed in `trainer._dropped_overlong_events`
  with the same rule the methods and now `reference_loss` apply, so the three
  still agree.
