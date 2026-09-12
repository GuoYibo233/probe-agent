# T06 report, `--mem-probe` changed to the real worst case

Ticket: `.scratch/kvshare-train/issues/06-mem-probe-worst-case.md`
Branch: `ticket/2026-08-28-wave4b/T06` (base `f1e0a1f`, head `e2c471a`)

## 1 What was done

### 1.1 `run_mem_probe` (`pipeline/train/train_causal_share.py`), ticket item 1

Changed to:

1. Build the optimizer state first: first take the "fullest block" (fall back to the "longest event" if unavailable) and do one forward-plus-backward pass that **is not counted in the measurement**, filling each trainable parameter's `.grad` with a real-shaped tensor; `opt.zero_grad(set_to_none=False)` zeros these gradients but keeps the tensors themselves; temporarily set each `param_group`'s `lr` to 0 and do one `opt.step()`, at which point AdamW allocates `exp_avg`/`exp_avg_sq` for every parameter, without changing the parameter values. `torch.cuda.reset_peak_memory_stats()` comes after this.
2. Do "forward + backward" twice in a row for the "fullest block", without `zero_grad` in between (gradient accumulation); after the second backward, read `max_memory_allocated` and record it as `fullest_block`'s `peak_mem_gb`.
3. The "longest event" block is done right after, with the condition unchanged that the state is already built and the gradients are not cleared, doing one more forward-plus-backward pass and reading the peak.
4. Both `mem_probe` event entries add the fields `n_backward` (`fullest_block` records 2, `longest_event` records 1) and `optimizer_state_prebuilt: true`; the original fields (`kind`/`n_events`/`packed_len_max`/`peak_mem_gb`/`B`/`L_pad`/`with_optimizer_state`) are kept as before.
5. Finally `opt.state.clear()`, restore `lr`, `opt.zero_grad(set_to_none=True)`.

**A technical gap in the first step (not written in the original ticket text, explained here in the report, see section 4 self-check for details)**: the original ticket text put "first build the optimizer state by doing `opt.zero_grad(set_to_none=False)` and then a `opt.step()` with lr set to 0" at the very front, before any forward-backward pass. I tested this (see section 3): under this order, `.grad` is `None` for all parameters, and AdamW's `step()` only allocates state for parameters where `.grad is not None`, so the `opt.state` built this way, in the literal order, is empty and will not be counted into the subsequent memory peak, the problem the ticket wants to solve (the probe undercounting the optimizer state's memory) would not be solved. I inserted, before this step, one forward-backward pass that is not counted in the measurement, specifically to fill `.grad` with real-shaped tensors, and then followed the original ticket text's `zero_grad(set_to_none=False)` + `opt.step(lr=0)`, so that the state is genuinely built (already verified with small-tensor testing, see section 3). Which block is used for this forward-backward pass does not affect the memory size the state occupies (AdamW's state only looks at the parameter shape and dtype, not the gradient values), so choosing the "fullest block" first and falling back to the "longest event" does not affect the result.

### 1.2 spec section 10 "worst block", ticket item 2

The "worst block" entry at line 185 of `.scratch/kvshare-train/spec.md`, the method section (from `the optimizer is built before the probe…` to `…then it samples and starts training`) is rewritten following the new process in section 1.1 above; the "fullest block" search definition (B taken from 2 to `events_per_mb`, `packed_len` scanned in descending order, etc.) is unchanged. The other three entries (smoke tier, ctool smoke, ruling) are not changed.

### 1.3 ctool `step`/`eval` events add `peak_mem_gb` (`pipeline/train/train_causal_tool.py`), ticket item 3

Added a new module-level function `_peak_mem_gb(dev)`: on cuda it reads `torch.cuda.max_memory_allocated() / 1e9` (rounded to 1e-3) and calls `reset_peak_memory_stats()`; on CPU it is always 0.0. The `log(...)` calls for the `step` event (around line 460) and the `eval` event (around line 470) both now pass in `peak_mem_gb=_peak_mem_gb(dev)`, using the same convention as the new trainer's `step` log (the peak window = from after the last read to before this read).

Added `TestPeakMemGb` in `tests/test_ctool_readpos.py`: this file has no CPU test case that can reach `main()`/the `step` event (`main()` needs a real `--base`/`--data`), so following the fallback written in ticket item 3, it only tests the function `_peak_mem_gb` itself that writes this field (the CPU branch returns 0.0, repeated calls do not accumulate and do not error).

### 1.4 New CPU test case in `tests/test_share_trainer.py`, ticket item 4

Added `TestRunMemProbeCPU`, a small model (`_tiny_config`) plus 5 short events from the active val set, `dev="cpu"`, `amp=False`. Asserts:

- After the call, `opt.state` is empty (`len(opt.state) == 0`).
- Each `param_group`'s `lr` is restored to its original value from before the call.
- All of the model's parameters have `.grad` equal to `None`.
- Two `mem_probe` events are recorded (`kind` is `fullest_block`/`longest_event` respectively), `n_backward` is 2/1 respectively, `optimizer_state_prebuilt`/`with_optimizer_state` are true, `peak_mem_gb` is 0 (CPU), and the `B`/`L_pad`/`n_events`/`packed_len_max` fields are all present.

## 2 How this was verified

```
cd /home/y-guo/reproduce/new1-wt/2026-08-28-wave4b-T06
/home/y-guo/reproduce/new1/cprobe-env/bin/python -m unittest tests.test_share_trainer tests.test_share_data -v
```
Tail of the output:
```
Ran 34 tests in 235.151s
OK
```
(includes the newly added `TestRunMemProbeCPU.test_state_cleared_lr_restored_grad_none_after_probe`, also `ok` when run alone.)

```
/home/y-guo/reproduce/new1/cprobe-env/bin/python -m unittest tests.test_ctool_readpos -v
```
Tail of the output:
```
Ran 8 tests in 1.116s
OK
```
(includes the two newly added `TestPeakMemGb` cases.)

```
grep -n "n_backward" pipeline/train/train_causal_share.py
```
3 hits (assignment, loop-variable use, writing the log).

Scope check: `git diff --stat` only touches five files, `.scratch/kvshare-train/spec.md`, `pipeline/train/train_causal_share.py`, `pipeline/train/train_causal_tool.py`, `tests/test_ctool_readpos.py`, `tests/test_share_trainer.py`; it does not touch `share_data.py`, the `run.py` registry, or `train_causal_callgen.py`/`train_causal_param.py`.

**Environment note**: a newly created worktree by default lacks the two gitignored NFS symlinks `pipeline/data`/`pipeline/runs` (they are symlinks in the main worktree, not tracked by git), which caused the CPU test cases depending on active data to all `skip` at first. I manually recreated two symlinks pointing at the same NFS path in the worktree (`ln -s /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/{data,runs} pipeline/{data,runs}`), these two links themselves are not tracked by git (they disappear along with the directory when the worktree is removed), they only let the tests run in this worktree, they do not change any tracked file.

**The real acceptance criterion is a measured run, the ticket itself does not do this**: after the change, `--mem-probe`'s reported `fullest_block.peak_mem_gb` must be ≥ the whole-run training `step` peak at the same budget/speed tier (60.59 GB for `--tok-budget 16384`, 80.91 GB for `24576`), verifying this needs the main session to rerun the `ks828b06_gptoss_cgen_speed` smoke tier (with `--mem-probe`) on an H100, the CPU unit tests cannot verify the memory number itself.

## 3 commit list

- `e2640b7` T06: run_mem_probe changed to a real worst case (build state first + do two backward passes in a row on the fullest block), changed `train_causal_share.py`, `tests/test_share_trainer.py`, spec section 10.
- `e2c471a` T06: ctool step/eval events add peak_mem_gb (same convention as the new trainer), changed `train_causal_tool.py`, `tests/test_ctool_readpos.py`.

## 4 Self-check findings and open questions

1. **The technical gap mentioned in section 1.1, with measured evidence attached**: verified using a 2-parameter toy optimizer.

   - When `.grad` is `None` for all parameters, `opt.zero_grad(set_to_none=False)` is a no-op (`.grad` stays `None`, because it only processes grad tensors that "already exist"), then when `opt.step()` runs, AdamW entirely skips parameters where `.grad is None` and allocates no state at all, reproduced by following the ticket's literal order (`zero_grad`+`step` first, then forward-backward), `opt.state` afterward is an empty dict (`len(opt.state) == 0`).
   - First do one genuine forward-backward pass so `.grad` has real values, then `opt.zero_grad(set_to_none=False)` (at this point `.grad` becomes all-zero while keeping the tensor, not `None`) plus `opt.step()` with `lr=0`, and in `opt.state` each of the two parameters gets the three keys `step`/`exp_avg`/`exp_avg_sq`, and the parameter values themselves do not change (`lr=0` takes effect).

   This is the direct basis for what I called in section 1.1 "inserting one forward-backward pass not counted in the measurement", it is not a design decision guessed out of thin air, but it is indeed a step the original ticket text did not write out; I wrote both this measured evidence and the reason for the change into `run_mem_probe`'s new docstring, so the main session has something to check against when reviewing on H100.
2. The CPU unit tests (ticket item 4) can only verify "the wrap-up state is clean and the event fields are all present", they cannot verify the ticket's final criterion of "whether the probe's number actually catches up with the training peak", this criterion is itself written in the ticket as something "the main session does on H100", it is outside the scope of this ticket.
3. The order the two `mem_probe` events for `fullest_block` and `longest_event` are written to the log has changed, from the old code's "`longest_event` first, then `fullest_block`" to "`fullest_block` first, then `longest_event`", this is required by the execution order the ticket itself describes ("longest event" must be done after "fullest block" has finished its two backward passes, with the gradient not yet cleared); it has been confirmed that nowhere in the codebase parses `mem_probe` events by position (rather than by the `kind` field), so this does not affect any downstream script.
4. Did not touch `share_data.py`, the `run.py` registry, `train_causal_callgen.py`/`train_causal_param.py`, consistent with acceptance item 2.

## 5 Fix round 1 (fix1), F1

Branch: `ticket/2026-08-28-wave4b/T06` (continuing from head `e2c471a`, fix1 head `312e0e0`).

### 5.1 F1 handling

**F1 original text**: the actual order in which `run_mem_probe` builds the optimizer state deviates from the literal wording of ticket item 1, the literal order in ticket item 1 is "first build the state with `zero_grad`+a `step()` at lr=0, `reset_peak_memory_stats()` comes after that, then do two forward-backward passes in a row on the fullest block", that is, no forward-backward pass should occur before the state-building step; the implementation inserted one forward-backward pass, not counted in the measurement, before this step. The review's conclusion: even with measured evidence behind it, this deviation still needs the main session to explicitly rule on whether to accept it, the reviewer should not wave it through on their own.

**What this round did**: did not change any execution logic (the order described in section 1.1 is kept exactly as is). Did two things:

1. **Independent re-verification** (not just restating the toy example from the previous round's report, re-verifying it myself in the environment actually used by this repo): ran both the ticket's literal order and the implementation's order in `/home/y-guo/reproduce/new1/cprobe-env` (torch 2.11.0+cu128):

   ```python
   # Literal order: no forward-backward at all, go straight to zero_grad(set_to_none=False) + step(lr=0)
   p = torch.nn.Parameter(torch.randn(3))
   opt = torch.optim.AdamW([p], lr=1e-3)
   opt.zero_grad(set_to_none=False)      # grad is already None, this step is a no-op
   for g in opt.param_groups: g["lr"] = 0.0
   opt.step()
   # Result: opt.state == {} (empty dict, zero keys), p's value unchanged

   # Implementation order: first genuinely do one forward-backward to fill .grad, then zero_grad(set_to_none=False)+step(lr=0)
   p2 = torch.nn.Parameter(torch.randn(3))
   opt2 = torch.optim.AdamW([p2], lr=1e-3)
   ((p2 ** 2).sum()).backward()
   opt2.zero_grad(set_to_none=False)     # grad becomes all-zero while keeping the tensor, not None
   for g in opt2.param_groups: g["lr"] = 0.0
   opt2.step()
   # Result: opt2.state has three keys for this parameter, step/exp_avg/exp_avg_sq, p2's value unchanged (lr=0)
   ```

   This result matches the toy example from the previous round's report: on the torch version actually used in this repo, the literal order leaves `opt.state` an empty dict afterward, it is not that "the state gets smaller", it is that no state gets built at all.

2. **Ruling that the literal order is not an optional design choice requiring a pick between "literal order" and "implementation order"**: the ticket's own title says "the optimizer state **is built**", and the mechanism the background section describes is "the real training peak is where the optimizer state and the previous minibatch's gradients are both still present", the memory the ticket wants the probe to reproduce has as its precondition that the optimizer state must genuinely be built first. The literal order cannot build any state at all on the torch version used in this repo (`opt.state` is an empty dict), so it cannot reach the goal the ticket itself states; there is no reading that both copies the literal order verbatim and manages to build the state. So this is not a "both implementations are reasonable, the user needs to pick one" judgment call, the literal order itself cannot reach the result the ticket asks for, inserting one forward-backward pass not counted in the measurement is the necessary precondition for the sentence "the optimizer state is built" to hold, it is not an alternative that could be picked instead. This matches the project CLAUDE.md rule "fix any problem with a root-cause fix: find the faulty logic that produces the problem, and directly overwrite that faulty logic with correct logic": the faulty logic is ticket item 1's literal order itself (it cannot build the state, it cannot reach its own goal), and the implementation order in section 1.1 is the correct logic that directly overwrites it, it is not a patch bolted on outside the faulty logic.

   As the implementer of the fix round, I have no authority to make this kind of decision that needs a human ruling on behalf of the real user (gyb); F1's requirement that "the main session explicitly rule on this" is what I did here is not overstepping to approve on its behalf, but verifying this finding, moving it from an open "is it credible" state to an independently checkable fact, "the literal order is technically incapable of reaching the ticket's own goal in this repo's actual environment", laying out all the evidence the judgment needs, so the final review at branch merge time can check it quickly. If the final review decides to keep the literal order even so (that is, accepting the consequence that the probe cannot build the optimizer state and the ticket's goal falls through), a separate ticket needs to be opened to adjust the goal or the approach, this is not a decision this round can substitute for.

3. **Written to disk**: `run_mem_probe`'s docstring (`pipeline/train/train_causal_share.py`) has this environment-measured evidence added, replacing the originally vague "verified on an empty model" with the specific environment (torch 2.11.0+cu128), the specific shape of the result (`opt.state` is an empty dict, zero keys), and the judgment that "this is not an optional implementation preference", so that anyone reading this code afterward can confirm this step's necessity without re-verifying it. The original text of that passage in section 10 of `.scratch/kvshare-train/spec.md` is already a plain, straightforward description of this same order, there is nothing that needs to change accordingly, it is left untouched.

### 5.2 How this was verified

```
cd /home/y-guo/reproduce/new1-wt/2026-08-28-wave4b-T06-fix1
/home/y-guo/reproduce/new1/cprobe-env/bin/python -m unittest tests.test_share_trainer tests.test_share_data -v
```
Tail of the output:
```
Ran 34 tests in 241.551s

OK
```

```
/home/y-guo/reproduce/new1/cprobe-env/bin/python -m unittest tests.test_ctool_readpos -v
```
Tail of the output:
```
Ran 8 tests in 1.122s

OK
```

Scope check: `git diff --stat` (relative to the fix1 starting point `e2c471a`) only touched one file, `pipeline/train/train_causal_share.py`, all 11 changed lines are in `run_mem_probe`'s docstring, it did not touch any execution logic, and did not touch `share_data.py`/the `run.py` registry/`train_causal_callgen.py`/`train_causal_param.py`/`train_causal_tool.py`/test files.

### 5.3 commit list (fix1)

- `312e0e0` T06: run_mem_probe docstring adds environment-measured evidence (F1 fix round), only changed `train_causal_share.py`'s docstring.

### 5.4 Open questions

F1's core demand is "this deviation needs the main session to explicitly rule on it", in this round I verified it into a factual judgment (the literal order cannot reach the ticket's own goal in this repo's environment), rather than approving this deviation myself on its behalf, whether to accept the result of "changing the probe into an order that can build the optimizer state" is still a single line the main session needs to look at and confirm at the branch's final review, it is not a decision I can substitute for.

## 6 Fix round 2 (fix2), F1

Branch: `ticket/2026-08-28-wave4b/T06` (continuing from fix1 head `312e0e0`, fix2 head `d97ed61`). Worktree: `/home/y-guo/reproduce/new1-wt/2026-08-28-wave4b-T06-fix2`.

### 6.1 F1 handling

**F1 original text (issued a second time, worded the same as round 1's review)**: the actual order in which `run_mem_probe` builds the optimizer state deviates from the literal wording of ticket item 1, the literal order is "no forward-backward pass occurs before the state-building step (`zero_grad(set_to_none=False)` + `opt.step()` at lr=0), `reset_peak_memory_stats()` comes after that, then two forward-backward passes are done in a row on the fullest block"; the implementation before fix1 inserted one forward-backward pass, not counted in the measurement, before building the state. The fix1 round only did "independent re-verification + verifying the deviation into a factual judgment", it did not change any execution logic, the deviation was still left in place, so F1 was rated "critical" again unchanged after fix1, it was not treated as resolved.

**What this round did**: this time the execution logic was genuinely changed, no longer just re-verification or adding comments.

1. **Removed the inserted forward-backward pass, replaced with directly assigning `.grad`**: around lines 262 to 280 of `pipeline/train/train_causal_share.py`, removed the step `prime_grp = fullest or longest; if prime_grp: _fwd_bwd(prime_grp)`, replaced with:

   ```python
   for g in opt.param_groups:
       for p in g["params"]:
           p.grad = torch.zeros_like(p)       # for building state, not from any forward-backward pass
   opt.zero_grad(set_to_none=False)
   for g in opt.param_groups:
       g["lr"] = 0.0
   opt.step()                                 # optimizer state is allocated here, parameters unchanged
   if dev.startswith("cuda"):
       torch.cuda.reset_peak_memory_stats()
   ```

   The root cause is the very sentence the fix1 report itself pointed out: AdamW allocating state only looks at whether `.grad is not None` and the parameter's shape/dtype, it does not look at the gradient values. Fix1 used "genuinely doing one forward-backward pass" to satisfy this condition, and this itself is the deviation F1 picked out (a forward-backward pass happened before building the state); since state allocation does not care about the gradient values at all, there is no need to run a genuine forward-backward pass to produce this value, directly assigning `torch.zeros_like(p)` (a zero tensor with the same shape, dtype, and device) to each trainable parameter's `.grad` is enough, this step is a pure tensor assignment, it does not call the model, does not build a computation graph, and is neither a forward nor a backward pass. This way, no forward or backward pass occurs before the state-building step (`zero_grad` + `step(lr=0)`) any more, `reset_peak_memory_stats()` still comes after that, fully aligned with ticket item 1's literal order, no longer a choice between "literal order vs. implementation order", so the main session no longer needs to pick between the two, the deviation F1 wants eliminated is itself eliminated, not explained away in a different way.
   - Uses `params` inside `opt.param_groups` (rather than `model.parameters()`) to locate the "trainable parameters", strictly matching ticket item 1's original meaning of "trainable parameters" = the parameters the optimizer actually updates (in the LoRA case, `opt` only holds the subset picked out by `lora_util.opt_params`, `model.parameters()` would include more frozen parameters).
   - The step `zero_grad(set_to_none=False)` is a no-op after the assignment (`.grad` is already a zero tensor, zeroing it again leaves the value unchanged), but it is still called following the ticket's literal wording, this line is not removed just because it becomes a no-op, ticket item 1 explicitly wrote this step.

2. **A new test directly verifying the property F1 wants**: `tests/test_share_trainer.py`'s `TestRunMemProbeCPU` added `test_state_built_before_any_forward_backward`, using a spy wrapping `tcs.block_row_ce` to record "whether `opt.state` is still an empty dict each time it is called", asserting that none of the entries in this list is `True` (that is, no forward-backward pass ever happens while the optimizer state is not yet built), and that at least one forward-backward pass has occurred (to rule out a false positive misjudged as "it never ran at all"). This test is not re-checking fix1's measurement (that was done on bare tensors in a toy example), it directly verifies the ordering property F1 cares about on `run_mem_probe`'s real execution path.

3. **spec synced**: the method paragraph of the "worst block" entry in section 10 of `.scratch/kvshare-train/spec.md` is rewritten from "first take the fullest block (fall back to the longest event if unavailable) and do one forward-plus-backward pass not counted in the measurement, filling each trainable parameter's `.grad` with a real-shaped tensor" to "no forward or backward pass occurs before the state-building step, directly assign `torch.zeros_like(p)` to each trainable parameter's `.grad`", synced with the code change, nothing else is changed (the fullest block's search definition, smoke tier, ctool smoke, and ruling, all four are untouched).

4. **docstring synced**: the sentence in `run_mem_probe`'s docstring, "the root cause is not whether a forward-backward pass is inserted, but that `.grad` needs a real-shaped tensor first", is kept (fix1 already got the root-cause judgment right, it is just that the way fix1 chose to land it still depended on one genuine forward-backward pass); the description is changed to the new assignment approach, and explicitly states "no forward or backward pass occurs before this state-building step".

### 6.2 How this was verified

```
cd /home/y-guo/reproduce/new1-wt/2026-08-28-wave4b-T06-fix2
/home/y-guo/reproduce/new1/cprobe-env/bin/python -m unittest tests.test_share_trainer.TestRunMemProbeCPU -v
```
Tail of the output:
```
Ran 2 tests in 5.532s

OK
```
(includes the newly added `test_state_built_before_any_forward_backward`, passes when run alone.)

```
/home/y-guo/reproduce/new1/cprobe-env/bin/python -m unittest tests.test_share_trainer tests.test_share_data -v
```
Tail of the output:
```
Ran 35 tests in 234.261s

OK
```
(34 existing from fix1 + 1 newly added this round, all green.)

```
/home/y-guo/reproduce/new1/cprobe-env/bin/python -m unittest tests.test_ctool_readpos -v
```
Tail of the output:
```
Ran 8 tests in 1.150s

OK
```
(this round did not change `train_causal_tool.py`, running this confirms there is no collateral regression.)

```
grep -n "n_backward" pipeline/train/train_causal_share.py
```
3 hits (assignment, loop-variable use, writing the log), consistent with ticket acceptance item 2.

Scope check: `git diff --stat 312e0e0` (relative to the fix1 head) only touched three files, `.scratch/kvshare-train/spec.md` (2 lines), `pipeline/train/train_causal_share.py` (29 lines, including the docstring and `run_mem_probe`'s execution body), `tests/test_share_trainer.py` (41 newly added lines, one test method), it did not touch `share_data.py`, the `run.py` registry, `train_causal_callgen.py`/`train_causal_param.py`/`train_causal_tool.py`/`tests/test_ctool_readpos.py`.

**Environment note (the same pitfall as fix1)**: a new worktree by default lacks the two gitignored NFS symlinks `pipeline/data`/`pipeline/runs`, manually recreated (`ln -s /net/.../pipeline/{data,runs} pipeline/{data,runs}`), not tracked by git, disappears along with the worktree when it is removed.

**The real acceptance criterion is still a measured run, this round does not do it**: after the change, `--mem-probe`'s reported `fullest_block.peak_mem_gb` must be ≥ the whole-run training `step` peak at the same budget/speed tier (60.59 GB for `--tok-budget 16384`, 80.91 GB for `24576`), this round's change does not alter the memory-reproduction mechanism itself of "build the state first, then do two backward passes in a row on the fullest block" (it is equivalent to fix1's execution body in terms of memory usage, it is just that the state-building step is now an implementation that does not depend on a forward-backward pass), so the conclusion in the fix1 report that "this criterion needs the main session to verify on H100" is unchanged, and does not need to change or need the mechanism re-argued because of this round's change.

### 6.3 commit list (fix2)

- `d97ed61` T06: run_mem_probe's state-building changed to follow the literal order (F1 fix round 2), changed `train_causal_share.py` (execution logic + docstring), `tests/test_share_trainer.py` (added test), `.scratch/kvshare-train/spec.md` (section 10 synced).

### 6.4 Self-check findings and open questions

1. **Whether F1 is fully resolved**: what this round eliminated is the specific deviation F1 named (inserting one forward-backward pass before building the state), the means used (directly assigning `.grad`) does not appear verbatim in ticket item 1's literal text, but it is neither a "forward" nor a "backward" pass, it does not fall within the range of deviation F1 pointed out, it is instead the necessary preceding assignment that lets the literally written two steps "`zero_grad`+`step(lr=0)`" actually take effect. This point is written clearly in the report, if the final review thinks even this one line of assignment needs extra confirmation, it can look directly at the code block and reasoning in section 6.1 item 1.
2. **Did not touch** `share_data.py`, the `run.py` registry, `train_causal_callgen.py`/`train_causal_param.py`/`train_causal_tool.py`/`tests/test_ctool_readpos.py`, consistent with acceptance item 2 and the YAGNI self-check, only changed the piece of execution logic F1 named plus one targeted test, did not incidentally refactor any code outside `run_mem_probe`.
3. **The F1 open-questions passage left over from fix1 (section 5.4) is not deleted**: kept as the decision record from before this round, history is not rewritten, this round's handling result is recorded separately in section 6.
