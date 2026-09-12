# T05 Trainer Review Fixes — Implementation Report

Ticket: `.scratch/kvshare-train/issues/05-trainer-review-fixes.md`
Branch: `ticket/2026-08-28-wave3/T05` (base `45c881e3b24e0db68de6de001743b9d21ab1ca69`,
head `5060654fb62ff2847059963c118550ad49748201`)
Files changed: `pipeline/train/train_causal_share.py`,
`tests/test_share_trainer.py`, `.scratch/kvshare-train/spec.md` (only the one
line in the results section of section 9).

## I. What was done (against each ticket item)

**1. S1 — how the last hidden state is obtained.** `_forward_packed` used to
call `model(..., output_hidden_states=True)` and then take
`out.hidden_states[-1]`. Changed to newly add `_base_model_and_head(model)`
(`model.get_base_model()` to reach down to the backbone, falls back to
`model` itself if this method doesn't exist) to get `(backbone, lm_head)`,
then calls
`backbone(input_ids=..., attention_mask=..., position_ids=..., use_cache=False)`
to take `.last_hidden_state`, gathers the loss positions and then runs them
through `lm_head`.

`lora_util.wrap` injects in place (`get_peft_model` directly replaces the
seven kinds of `nn.Linear` in the original model, the original variable
`model` itself is still the original `Qwen3ForCausalLM` after wrapping, not
a `PeftModel`), so the `model` variable used throughout training in `main()`
never actually becomes a `PeftModel`, `model.model`/`model.lm_head` were
already directly usable; the `get_base_model()` branch inside
`_base_model_and_head` is a defensive branch added per the ticket text's
"needs to be compatible with peft's wrapped object" requirement, covering
the more general usage where "what the caller passes in is the `PeftModel`
itself". Verified with
`tests/test_share_trainer.py::TestBlockRowCeUnderLoRA::test_lora_forward_backward`:
after a small model goes through `lora_util.wrap`, directly call
`backward_logical_minibatch`, asserting that at least one adapter parameter
(`requires_grad=True`) gets a gradient and every non-adapter parameter
(`requires_grad=False`) gets none.

**2. S2 — the bf16 coarse screen does not perform a drift self-check.**
`_ref_forward` gained a `check_drift=True` parameter. When
`check_drift=False`, it skips the comparison between the locally,
token-by-token, formula-aggregated `row_ce_local` and the `inst_ce` return
value, and only returns the real output of `inst_ce`. At the three call
sites: the REF_BATCH full batch (fp32) and the bs=1 single-row baseline
(fp32) keep the default `True`; the bf16 coarse screen on cuda explicitly
passes `check_drift=False`. Added two tests:
`test_ref_forward_raises_real_exception_not_assert` (after the rework, also
asserts that the exception message carries the drift value),
newly added `test_ref_forward_check_drift_false_does_not_raise` (with the
same drift patch, does not raise when `check_drift=False`, the return value
is still non-empty).

**3. S3 — moving the backward pass out of autocast.**
`backward_logical_minibatch` gained an `amp=False` parameter, the
`with torch.autocast(...)` now only wraps this one forward pass of
`block_row_ce`, the computation of `loss_c` and `.backward()` were both
moved outside the `with` block. The `with torch.autocast(...)` in `main()`
that used to wrap the entire function call was removed, `amp` is passed in
as a parameter instead. `.backward()` in `run_mem_probe` was already outside
autocast, no change needed there.

**4. S5 — the length filter for alignment candidates.**
`_align_candidates` gained a `max_len` parameter, the filter condition
changed from `n_full <= ALIGN_LEN_FILTER` to
`n_full <= min(ALIGN_LEN_FILTER, max_len)`. The call site
`run_align_check` was updated to pass `args.max_len`.

**5. S6 — transient memory on the reference path.** In `_ref_forward`, once
`ce`/`rid` are pulled out of `out`/`lg`, immediately `del out, lg`, then call
`inst_ce_fn` (it re-runs the model's forward pass itself, producing its own
`[B, L, V]` fp32 logits). The computation of `row_ce_local` (needed only
when `check_drift=True`) was moved to after the `del`, before the call to
`inst_ce_fn`, because it only depends on the already-extracted `ce`/`rid`.

**6. F2 — the keys in `ALIGN_CHECK.json` (ticket 03 minor).** `bf16_warn=bf16_warn`
was removed from the `report` dict, the JSON written to disk and printed no
longer carries this key; the return value was changed to
`dict(report, bf16_warn=bf16_warn)`, only in the return value does it
additionally carry a copy for `main()`'s `start` event to read
(`align_bf16_warn=bool(align_rep["bf16_warn"])`, this line was not
touched). `baseline_warn` was already in `report`, no change needed. The
field list in that one line of the results section of spec section 9 gained
`baseline_warn` (the only line changed, checked that no other line was
touched).

**7. N2 — tests for the assertion branch (ticket 03 minor).** The two cases
the ticket asked for are both given in the S2 change:
`check_drift=True` raises `RefBaselineDriftError` and the error message
carries the drift value (extracted via the regex
`max diff ([0-9.eE+-]+)`, asserting it is greater than
`REF_INST_CE_DRIFT_TOL`), the same patch does not raise when
`check_drift=False`. The existing
`TestRunAlignCheckHandlesRefBaselineDriftError` class's case, "`run_align_check`
catches the exception via the unified reporting channel", is unaffected (it
monkeypatches the entire `_ref_forward` function, it does not go through the
`check_drift` branch).

## II. How it was verified

**cprobe-env unit tests (inside the worktree, `pipeline/data/nyapass_aw_v1`
is a symlink to the same-named directory in the main repo, read-only, no
file in the main repo is changed):**

```
/home/y-guo/reproduce/new1/cprobe-env/bin/python -m unittest \
  tests.test_share_trainer tests.test_share_data
```
Tail of the output: `Ran 32 tests in 233.106s` / `OK` (`TestBlockRowCeUnderLoRA`
and `test_ref_forward_check_drift_false_does_not_raise` are new this time,
the rest are regressions of existing cases). Actual `ALIGN_CHECK.json`
sample (the real artifact produced by
`TestMainSmokeCPU.test_cgen_smoke`):

```
{
 "PASS": true, "n_events": 2, "n_rows": 75, "n_tgt_tokens": 1551,
 "max_abs_diff": 1.9073486328125e-06, "max_tok_diff": 9.5367431640625e-07,
 "baseline_max_abs_diff": 1.9073486328125e-06, "tol": 2e-05,
 "bf16_mean_abs_diff": null, "bf16_max_abs_diff": null,
 "attn_impl": "sdpa", "mismatch_idx": [], "baseline_warn": false
}
```
Confirmed that the JSON written to disk has no `bf16_warn` key, `baseline_warn`
is present; in the `start` event of the same run,
`'align_bf16_warn': False` is present as usual (the CPU device never
reaches the cuda branch, always False, the field itself is not lost).

**System python3 discover (run once per the acceptance requirement, expected
to skip overall):**
```
python3 -m unittest discover -s tests -p 'test_share_*.py'
```
Output: `skipped "needs the cprobe-env interpreter: No module named 'torch'"`
×2, `Ran 2 tests in 0.000s` / `OK (skipped=2)`.

**Two grep acceptance commands:**
```
grep -n "output_hidden_states" pipeline/train/train_causal_share.py   # no output, exit 1
grep -n "backward" pipeline/train/train_causal_share.py
```
The latter hits 4 lines (1 definition + 2 in the docstring mentioning
`.backward()` + 2 actual call sites): `backward_logical_minibatch`'s
`(loss_c / n_g).backward()` is outside the `with torch.autocast(...)` block
(that with block only wraps the one line
`ce_per_row, w = block_row_ce(...)`, already checked against the indentation
in the code snippet pasted in this report); `loss.backward()` in
`run_mem_probe` was already outside its autocast block, unchanged.

**`python3 run.py selfcheck` (run inside the worktree, compared against the
main repo):**
Inside the worktree, output is
`selfcheck: 76 tasks / 4 recipes / 3 presets, 16 gaps`, all 16 gaps are
local virtual-environment and third-party directories of the kind excluded
by `.gitignore`'s `*-env/` or `envs/<third-party clone>/`
(`cprobe-env`/`mbert-env`/`envs/*`) — a git worktree only checks out
version-controlled files, so these directories naturally do not appear in
the new worktree, unrelated to this ticket's changes. Running `selfcheck`
against the exact same `run.py` in the main repo (not a single line
changed) outputs
`selfcheck: 76 tasks / 4 recipes / 3 presets, all present` — the
task/recipe/preset counts fully agree with what was seen inside the
worktree, proving the registry structure was not broken, the gap list is
only because these local environment directories do not exist inside the
worktree. This ticket did not change `run.py` or any task definition.

## III. Commit list

- `5060654` T05: trainer review fixes S1/S2/S3/S5/S6 + F2/N2 (ticket 05) —
  `pipeline/train/train_causal_share.py`, `tests/test_share_trainer.py`,
  `.scratch/kvshare-train/spec.md`, three files, one commit (the seven
  requirements are coupled together within the same batch of function
  changes, splitting into separate commits does not give a clearer
  boundary).

## IV. Self-check findings and open questions

- In order to run cases that need real data/tokenizers inside the worktree,
  a symlink was created inside the worktree,
  `pipeline/data/nyapass_aw_v1 -> /home/y-guo/reproduce/new1/pipeline/data/nyapass_aw_v1`
  (that whole directory is in `.gitignore`, `git status` confirms git does
  not see it, a read-only reference, does not affect any file in the main
  repo). This symlink disappears along with the worktree when it is deleted
  per protocol, no extra cleanup needed.
- An existing comment in `run_align_check` used to say "the three
  `_ref_forward` calls ... share this one except", this statement is no
  longer accurate after S2 (the bf16 one already has `check_drift=False`,
  it will no longer raise `RefBaselineDriftError`), it has been rewritten
  to an accurate description in passing (only the two fp32 calls will
  trigger this except). This is a documentation-accuracy fix made in
  passing, not one of the ticket's items, called out separately here.
- The docstrings of `_forward_packed`/`_ref_forward` used to contain the
  literal string `output_hidden_states` (used to explain "no longer doing
  this"), the first draft was found to make the acceptance's
  `grep "output_hidden_states"` hit, it has been rewritten into an
  equivalent description that does not contain this literal substring, and
  the grep was rechecked to pass.
- `share_data.py`, the old scripts (`train_causal_callgen.py`/
  `train_causal_param.py`), and the `run.py` registry were not touched,
  `.scratch/kvshare-train/spec.md` only had the one line in the results
  section of section 9 changed (already checked with `git diff` that the
  whole diff has only this one spot).

## V. Fix round 1 — re-review finding F1

Same branch (`ticket/2026-08-28-wave3/T05`), this round's base is the
previous round's head,
`5060654fb62ff2847059963c118550ad49748201`, head is given below in the
commit list.

**F1 (important) — the `get_base_model()` defensive branch has no test
coverage at all under a peft-wrapped model.** The re-review pointed out:
the `model` variable that `test_lora_forward_backward` passes to
`backward_logical_minibatch`/`_forward_packed`/`_base_model_and_head` is
**the original variable** after `lora_util.wrap(model, lora_args)` injects
in place — although `lora_util.wrap`'s internal `get_peft_model` does
return a `PeftModel`, the call sites (this test and `main()`) both discard
the return value and keep using the original variable, so
`hasattr(model, "get_base_model")` is always false along this path in
`_base_model_and_head`, the code always takes the `else: base = model`
branch. The `get_base_model()` half (ticket 05 item 1 explicitly required
compatibility with the more general calling convention of "what is received
is the `PeftModel` itself") was never actually executed by any test added
in this diff.

Checked and confirmed: re-read `wrap()` in
`pipeline/train/lora_util.py` (lines 64-77) — its docstring itself states
"injects **in place** ... the wrapper it returns has no use beyond
merging", `main()` (in `train_causal_share.py`) and the old tests both only
use the original variable, confirming the re-review's judgment.

**How it was fixed:** added
`test_get_base_model_branch_forward_backward` inside
`TestBlockRowCeUnderLoRA` in `tests/test_share_trainer.py`, without
changing `_base_model_and_head` itself (F1 is a pure test-coverage gap, not
a logic defect; the behavior ticket item 1 required was already implemented
correctly in the previous round, this does not amount to widening the scope
into a refactor):

1. Use `wrapped = lora_util.wrap(model, lora_args)` to get the **return
   value** of `wrap()` (a genuine `PeftModel` object) and use it as the
   `model` argument, instead of discarding the return value like the old
   test and continuing to pass the original variable — this way
   `hasattr(wrapped, "get_base_model")` is true, and
   `_base_model_and_head(wrapped)` is guaranteed to take the `if` branch.
2. First directly check that the branch's chosen values are themselves
   correct: assert that the `backbone`/`lm_head` returned by
   `_base_model_and_head(wrapped)` are exactly
   `wrapped.get_base_model().model`/`wrapped.get_base_model().lm_head`
   (`assertIs`, object identity, not structural comparison).
3. Then run `backward_logical_minibatch(wrapped, ...)` through a real
   forward and backward pass, asserting that at least one adapter parameter
   gets a gradient and every non-adapter parameter gets none — proving that
   the computation graph built under this branch is not backed only by
   object-identity equality, it can genuinely be trained.
4. Added `assertTrue(hasattr(wrapped, "get_base_model"), ...)`, to
   separately report the two different failure causes "the peft version
   changed and this attribute disappeared" versus "the branch itself is
   wrong".

At the same time, the class docstring (around lines 388-395) was updated to
explain which branch of `_base_model_and_head` each of the two cases
covers, to keep the next reader from thinking the two cases are
duplicates.

**How it was verified:**

```
/home/y-guo/reproduce/new1/cprobe-env/bin/python -m unittest \
  tests.test_share_trainer.TestBlockRowCeUnderLoRA -v
```
Tail of the output: `Ran 2 tests in 5.100s` / `OK`
(`test_get_base_model_branch_forward_backward` is new,
`test_lora_forward_backward` is a regression, both marked `ok`).

```
/home/y-guo/reproduce/new1/cprobe-env/bin/python -m unittest \
  tests.test_share_trainer tests.test_share_data
```
Tail of the output: `Ran 33 tests in 228.300s` / `OK` (the previous round
had 32 cases, this round adds 1, everything else is a full regression pass;
the line printed midway, "alignment check FAIL: reference-path self-check
failed", is the expected output of the existing
`TestRunAlignCheckHandlesRefBaselineDriftError` case deliberately injecting
drift to trigger it, not a test failure).

The two grep commands and `python3 run.py selfcheck` from the acceptance
criteria were also rerun this round (this round only changed
`tests/test_share_trainer.py`, which should not and does not affect these
two, rerun only to confirm no side-effect breakage):
`grep -n "output_hidden_states" pipeline/train/train_causal_share.py` has
no output; `grep -n "backward" pipeline/train/train_causal_share.py` hits
the same `.backward()` calls (lines 206, 248) with the same indentation
checked against the previous round's report, still outside the
`torch.autocast` block; `python3 -m unittest discover -s tests -p
'test_share_*.py'` gives `OK (skipped=2)` under system python3;
`python3 run.py selfcheck` outputs
`selfcheck: 76 tasks / 4 recipes / 3 presets, 16 gaps`, the 16 gaps are
identical to the ones listed in the previous round's report (all are
`*-env`/`envs/*` type local virtual-environment directories that naturally
do not exist in a new worktree, unrelated to this ticket's changes), the
task/recipe/preset counts are unchanged, the registry structure was not
broken.

**Commit list:**

- `6c507cc` T05: added actual execution coverage for the get_base_model()
  branch (re-review F1) — changed only `tests/test_share_trainer.py`, added
  one test method `test_get_base_model_branch_forward_backward` and updated
  the class docstring, `train_causal_share.py` was not touched.

**Self-check findings and open questions:**

- F1 is a pure test-coverage gap, not a single line of `_base_model_and_head`'s
  implementation code was changed this round; confirmed that the logic of
  the `get_base_model()` branch (`base.model`/`base.lm_head`) is semantically
  fully symmetric with the `else` branch, the new case only connects the
  half of the code that had never been executed before to a real
  forward-plus-backward path, no new behavior was introduced.
- `pipeline/train/train_causal_share.py`, `pipeline/train/lora_util.py`,
  `share_data.py`, the old scripts, the `run.py` registry, and
  `.scratch/kvshare-train/spec.md` were not touched (this round's
  `git diff --stat` shows only one file, `tests/test_share_trainer.py`,
  62 lines added, 3 lines removed).
- The worktree reuses the same symlink as the previous round,
  `pipeline/data/nyapass_aw_v1 ->
  /home/y-guo/reproduce/new1/pipeline/data/nyapass_aw_v1` (a read-only
  reference, that directory is entirely in `.gitignore`, `git status`
  confirms git does not see it), disappearing together with the worktree
  when it is deleted per protocol.
