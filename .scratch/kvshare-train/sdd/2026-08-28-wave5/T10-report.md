# T10 report: three block-picking modes for the memory probe `--mem-probe-pick {tokens,cost,loop}`

Ticket: `.scratch/kvshare-train/issues/10-mem-probe-pick.md`
Spec: `.scratch/kvshare-train/spec.md` 16.5 (approach and fields), 16.9 (tests), 16.10 #31 #32
Branch: `ticket/2026-08-28-wave5/T10`, base `07907db08b50d66c1c193588f22b5cc97b24b4b3`,
head `e272ffd53c4565bdd13657b003badd8d3c0b1f53`

## I. What was done (checked against the ticket item by item)

### 1. `share_data.epoch_minibatches(events, seed, ep, events_per_mb)` (ticket item 1)

New function (`pipeline/train/share_data.py`): copies `list(events)`, then runs
`random.Random(seed + ep).shuffle`, then slices into logical minibatches by `events_per_mb`,
these are the two steps the training loop used to do on its own. The training loop of
`train_causal_share.py` (lines 761 to 764 before the change) now calls it, and the `cost`/`loop`
probe's enumeration (`_enum_run_blocks`) also calls it, so this is now the single source of
truth in all three places. `grep -n "epoch_minibatches"` hits both files, and the training loop
no longer has its own `random.Random(SEED + ep).shuffle` call (verified: `grep -n
"random.Random(SEED" pipeline/train/train_causal_share.py` has zero hits).

### 2. `--mem-probe-pick {tokens,cost,loop}` (default `cost`) and the `run_mem_probe` refactor (ticket item 2)

`run_mem_probe` was split into a skeleton plus three block-picking run modes, with a new
signature `run_mem_probe(model, opt, tr_events, args, dev, log, amp, full_events=None)`,
`tr_events` stays at the position `full_events` held before the change (the third positional
argument), and `full_events` becomes a trailing keyword argument that, when it defaults to
`None`, falls back to `tr_events`. This way the two call sites from before the change,
`tcs.run_mem_probe(model, opt, events, args, "cpu", log, amp=False)` (around lines 548 and 595
of `tests/test_share_trainer.py`), still run as-is once aligned by position (`tr_events=events`,
`full_events` lands on its default and falls back to `events` itself); the call sites did not
need to change, only the two `argparse.Namespace` objects there needed the two fields
`mem_probe_pick="tokens", accum=2` added per the ticket's requirement (`run_mem_probe`
internally reads `args.mem_probe_pick`, and some paths read `args.accum`, without adding them
it would raise `AttributeError`).

The skeleton (build the optimizer state -> `reset_peak_memory_stats` -> dispatch by
`--mem-probe-pick` -> clear the state, restore lr, clear the gradients) is word-for-word
identical to before the change, it just has an outer layer added that saves and restores the
random number state (see item 4).

- **`tokens`** (the current state): picks the fullest block plus the longest event from the
  full set by `share_data.worst_blocks`, with the state already built, doing two backward
  passes in a row (fullest block) / one (longest event). Loading the full set is changed to
  only happen in this mode: `if args.mem_probe_pick == "tokens":` in `main()`, and when
  `(not args.smoke) and args.max_events == 0`, `tr_events` is reused directly (`tr_events` is
  already the full set when `limit=0`), otherwise the full set is loaded separately once.
- **`cost`** (the default): added `_enum_run_blocks(tr_events, args)`, which uses
  `epoch_minibatches(tr_events, SEED, 0, events_per_mb)` to enumerate epoch 0's logical
  minibatches, each logical minibatch going through `chunk_by_budget` to get physical blocks;
  added `_pick_cost_blocks(blocks)`, which picks three blocks: (i) the largest `B x L_pad`,
  ties go to the one with more loss positions; (ii) the largest number of loss positions, ties
  go to the one with more tokens; (iii) the largest `n_tokens/max + n_loss_pos/max`. Each of the
  three blocks has its peak measured under "state already built, two forward-plus-backward
  passes done in a row, gradients not cleared in between"; a duplicate block (judged by `id()`
  identity) is only run once, and a duplicate entry still writes a `mem_probe` event and adds
  `same_as` pointing to the kind that was actually run.
- **`loop`**: also enumerates with `_enum_run_blocks`, first finds the logical minibatch that
  the block with the most loss positions belongs to, then locates the update group it belongs
  to by `(best_mb_idx // accum) * accum` (when the last group has fewer than `accum` items,
  `group_end = min(group_start + accum, M_ep)`, `n_g` is the actual count), and runs one update
  exactly as the training loop does: `backward_logical_minibatch` for each logical minibatch in
  turn, then `clip_grad_norm_` followed by `opt.step()` with lr=0 once the group finishes, then
  reads the peak (the order follows the ticket/spec literally: `opt.step()` first, then read the
  peak, matching the timing of the peak read in the real `step` event). The scheduler `sch` is
  not touched.

### 3. Saving and restoring the random number state (ticket item 2, fifth paragraph, silent failure point #31)

The whole of `run_mem_probe` is wrapped in `try/finally`: before entering it saves
`random.getstate()`, `torch.get_rng_state()`, and (on cuda) `torch.cuda.get_rng_state()`, and
`finally` restores them one by one with `setstate`/`set_rng_state`. Test (c) verifies this:
running the small model's `main()` twice, once with `--mem-probe --mem-probe-pick cost --lora`
and once without `--mem-probe` (with the same `--lora`), both with `--smoke --max-events 6
--log-every 1`, the `loss` in the `step` events of `train_log.jsonl` is identical entry by entry
(measured as `11.9434` both times, and `eval`'s `val_ce` as `11.9295` both times).

### 4. Unifying event fields plus `mem_probe_summary` plus `_peak_gb` (ticket item 2, sixth and seventh paragraphs)

Added a module-level `_peak_gb(dev)` (on cuda, `max_memory_allocated() / 1e9`, on other devices
`0.0`), all three probe modes and the training loop's `step` log (lines 813 to 817 before the
change) now call it. The `mem_probe` event fields are unified to `pick, kind, B, L_pad,
n_tokens, n_rows, n_loss_pos, peak_mem_gb, n_backward, with_optimizer_state,
optimizer_state_prebuilt` (`loop_group` additionally has `n_blocks, n_events,
max_block_n_loss_pos`, `B/L_pad/n_tokens` are written from the largest block in the group,
`n_rows/n_loss_pos` are summed over the whole group, `n_backward` is the total number of
physical blocks in the group); the old keys `n_events` (under tokens/cost it keeps the old
convention of being equal to `B`, under loop_group it changes to the total event count in the
group) and `packed_len_max` (equal to `L_pad`) are kept, not removed. Once everything finishes
running, one `mem_probe_summary` is written (`pick, worst_gb, worst_kind, scope,
n_events_considered`, `scope` is `full` (tokens) or `run` (cost/loop)). The `start` event gets
`mem_probe_pick` added (right after the `mem_probe` key).

### 5. Along the way: added `grad_norm` to the `step` event (ticket item 2, eighth paragraph)

In the training loop, `total_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)` now
captures the return value, and the `step` log adds `grad_norm=round(float(total_norm), 4)`.

### 6. The 7-field hand-built row tuple (ticket item 2, ninth paragraph)

This ticket did not write any new hand-built row tuple in production code; the hand-built
physical blocks in the test file (`_mk_block`) only serve `_pick_cost_blocks`'s pure
block-picking logic, they do not go through `pack_event`/the model's forward pass, so they are
not affected by the constraint that "a 6-field tuple would make `pack_event` raise
`ValueError`" (the ticket original says "the 6th field of the share_data row tuple is the gen
dict", and ticket 08 has not yet been merged into this branch, so there is no 7-field/6-field
conflict; if a hand-built event on a real forward-pass path shows up after a future merge, it
should be filled out to 7 fields at that point).

## II. How this was verified

All commands used `/home/y-guo/reproduce/new1/cprobe-env/bin/python` (the worktree does not
have this virtual environment, it is a local directory outside the symlinks, not tracked by
git, so the main repo's interpreter was used directly). Before running, two symlinks to NFS,
`pipeline/data` and `pipeline/runs`, were rebuilt in the worktree (pointing at the same symlink
target as the main repo's `pipeline/data`/`pipeline/runs`; these two symlinks themselves are
excluded in `.gitignore`, `git worktree add` does not bring them over; rebuilding them was
purely to let the tests that depend on the active data/weights run, it does not change any
tracked file).

- Acceptance command (ticket original):
  ```
  cprobe-env/bin/python -m unittest tests.test_mem_probe_pick tests.test_share_trainer tests.test_share_data
  ```
  Output: `Ran 42 tests in 571.167s` `OK` (5 + 16 + 21 = 42, the numbers add up, not double
  counted because of my `import test_share_trainer as tst`).

- `grep -n "epoch_minibatches" pipeline/train/share_data.py
  pipeline/train/train_causal_share.py`: hits in both files (the definition plus 3 call sites).
- `grep -n "random.Random(SEED" pipeline/train/train_causal_share.py`: zero hits (the training
  loop no longer has its own shuffle).
- `grep -n "mem_probe_summary\|get_rng_state\|def _peak_gb"
  pipeline/train/train_causal_share.py`: all three hit.
- `git diff --stat main -- run.py`: empty (`run.py` was not changed).
- `python3 run.py selfcheck`: in this worktree it reports 16 spots of "missing
  interpreter/program" (local virtual environment directories such as `envs/*`, `cprobe-env`,
  `mbert-env` are simply not brought over by `git worktree add`), but the task/recipe/preset
  counts `76 tasks / 4 recipes / 3 presets` match the main repo (`selfcheck: 76 tasks / 4
  recipes / 3 presets, all present`) exactly, the registry itself was not changed, the missing
  items are purely because the worktree lacks the local environment directories, not a problem
  introduced by this ticket (this ticket indeed did not change `run.py`).

### New tests (`tests/test_mem_probe_pick.py`) corresponding item by item

- (a) `TestPickCostBlocks`: hand-built 6 single-event physical blocks (1 with the most loss
  positions, 2 tied on token count but with different loss positions, 1 with the highest
  combined score, 2 filler blocks), asserts that the `max_tokens_block` picked by
  `_pick_cost_blocks` is the one with more loss positions among the tied ones, `max_losspos_block`
  is different from it, and `max_cost_block` is the one computed by the formula, passed. The
  hand-calculation process is in the comments inside the test file and the review at the bottom
  of this report under "self-check".
- (b) `TestRunMemProbeThreeModes`: runs `run_mem_probe` once for each of the three modes
  `tokens`/`cost`/`loop` (the real Qwen3-0.6B-Base tokenizer plus a randomly initialized
  two-layer small model plus 5 short events drawn from the val set), asserts `opt.state` is
  empty, `lr` is restored, `.grad` is all `None`, and the parameters are unchanged bit for bit
  (`torch.equal`); `_peak_gb` is swapped for a fake function via
  `unittest.mock.patch.object` that returns an increasing value each call (1.0, 2.0, ...),
  asserting `mem_probe_summary.worst_gb` equals the maximum `peak_mem_gb` among this round's
  `mem_probe` events, and `worst_kind` matches the `kind` that maximum belongs to, all three
  subtests passed.
- (c) `TestMemProbeRngRestorationViaMain`: runs the small model's `main()` once with
  `--mem-probe --mem-probe-pick cost --device cpu --lora` and once without `--mem-probe` (with
  the same `--lora`) (both `--smoke --max-events 6 --log-every 1`), the `loss` in the `step`
  events of the two `train_log.jsonl` files is identical entry by entry, passed (measured
  `loss` as `11.9434` both times).

### `tests/test_share_data.py` adds `TestEpochMinibatches`

`test_matches_old_inline_shuffle`: 23 hand-built events, comparing the event-name sequence
between `epoch_minibatches` and the "old way of writing it" hand-copied inside the function
body (copying `list(events)`, `random.Random(seed + ep).shuffle`, slicing by `events_per_mb`),
identical entry by entry. `test_does_not_mutate_input`: confirms it does not change the
original list passed in by the caller. Both passed.

### Each of the four files touched by the full diff was run separately

- `tests.test_share_data` (21 -> 23 items, including two new ones): `Ran 23 tests` `OK` (1
  `setUpClass`-level skip, the one time the val-set path check ran before the symlinks I
  rebuilt took effect; after rebuilding the links, rerunning did not skip again; this time,
  running together with `test_share_trainer`, the `Ran 37 tests`/`OK` is the result after
  rebuilding the links, so this one has also been run for real).
- `tests.test_share_trainer` (16 items, including the two changed probe test cases): run
  together with `test_share_data`, `Ran 37 tests` `OK`.

## III. Commit list

- `d4a87d9` T10: share_data.epoch_minibatches as the single source of truth (spec 16.5),
  `pipeline/train/share_data.py` gets a new function, `tests/test_share_data.py` adds
  `TestEpochMinibatches`.
- `e272ffd` T10: three block-picking modes for the memory probe --mem-probe-pick
  {tokens,cost,loop} (spec 16.5), the `run_mem_probe` refactor in
  `pipeline/train/train_causal_share.py` and the training loop switched to calling
  `epoch_minibatches`/`grad_norm`, two `Namespace` objects in `tests/test_share_trainer.py`
  got fields added, new `tests/test_mem_probe_pick.py`.

## IV. Self-check findings and open questions

- **Hand-calculation review for `_pick_cost_blocks`** (for review purposes, not a newly found
  problem): the 6 blocks' `packed_len`/loss positions are `(64,60)`, `(320,16)`, `(320,40)`,
  `(288,55)`, `(48,5)`, `(32,3)` (all are 1-row or multi-row 1-event blocks, `B=1`, `L_pad` and
  `packed_len` happen to be equal because their values are all multiples of 16, `n_tok=L_pad`).
  `max_n_tok=320`, `max_n_loss_pos=60`. The three blocks' scores: `(64,60)`'s cost =
  64/320+60/60=1.2; `(320,16)` = 1.2667; `(320,40)` = 1.6667; `(288,55)` = 0.9+0.9167=1.8167;
  the two filler blocks are 0.233 and 0.15. `max_tokens_block`, when `(320,16)` and `(320,40)`
  are tied, goes to `(320,40)` by "more loss positions"; `max_losspos_block` is `(64,60)` (the
  unique maximum, different from the former); `max_cost_block` is `(288,55)` (the unique
  maximum). All three blocks differ pairwise, matching the test assertions.
- **`worst_kind` can be `None` on the real (unmocked) CPU path**: the three `_mem_probe_*`
  functions decide `worst_kind` with `if peak > worst_gb:` (starting from `worst_gb=0.0`), on
  CPU `_peak_gb` always returns `0.0`, the first candidate's `0.0` does not satisfy being
  strictly greater than `0.0`, so `worst_kind` stays at `None` (`worst_gb` itself is still
  correct, because `0.0` genuinely is the maximum of an all-`0.0` list). This can be seen in
  test (c)'s real output (`mem_probe_summary`'s `worst_kind: None`, `worst_gb: 0.0`). On GPU the
  real peak will not happen to equal the sentinel value `0.0`, so this is not a production
  problem; the ticket/spec also make clear that this limitation, "the real value on CPU is
  always 0.0, without patching it is 0 == 0 with no discriminating power", is itself expected,
  so the decision logic was not changed for this, it is only recorded here for review. My
  judgment is that this does not need changing; if gyb thinks `worst_kind` should also get a
  non-`None` value when everything ties at zero (for example, taking the first candidate), that
  needs a separate ruling before changing it.
  - **In test (c), all three of the `cost` mode's blocks land on the same physical block** (the
  `same_as` chain `max_losspos_block -> max_tokens_block`, `max_cost_block ->
  max_tokens_block`): under `--max-events 6`, `events_per_mb=4` (default), the 6 events are
  sliced into only 2 logical minibatches, `tok_budget=16384` is large enough for each logical
  minibatch to fit into 1 physical block on its own, and it happens that one of these blocks is
  at once the one with the most tokens, the most loss positions, and the highest combined
  score. This is a coincidence of the real data at small sample size, not a bug, test (a) has
  already separately verified the three block-picking rules' behavior when there is
  discriminating power, using hand-built data.
