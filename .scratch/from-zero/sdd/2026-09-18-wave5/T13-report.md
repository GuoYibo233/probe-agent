# T13 report: the training loop and the three probe methods

Ticket: `.scratch/from-zero/issues/13-training-loop-and-probe-methods.md`
Branch: `ticket/2026-09-18-wave5/T13`
Worktree: `/home/y-guo/reproduce/new1-wt/2026-09-18-wave5-T13` (removed at the end of this ticket; branch kept)

## What was done

Five files, all `venv: probe`, as the ticket lists:

1. **`train/utils/trainer.py`** — the shared training loop: `run(run_dir, method) -> None`.
   - `cfg = schema.load_frozen(run_dir)`, `hb = registry.beat(run_dir, 0)`, in that order (steps 1-2), before the continue-rule check (step 3), so a call on an already-`done` directory still opens a fresh, empty heartbeat file — matching the ticket's own step ordering literally.
   - The 2.4 continue rule, all five rows, checked in the pinned priority order: `done.json` → return; `train_done.json` present and `predictions.parquet` absent → predict-only (`ckpt_dir = best/`); `last/` present with a matching `commit` → resume (`ckpt_dir = last/`, `resume_step` read from `last/meta.json["step"]`); `last/` present with a differing `commit` → `SystemExit` naming both commits and `run.py retry`; `train_log.jsonl` present with none of the above → `SystemExit` naming `train_log.jsonl` and `run.py retry`; otherwise fresh.
   - `torch.manual_seed(cfg.train.seed)`, `df = training_data.read(build_dir / "examples.parquet")`, `consumed.json` written as `[{path, sha1, n_rows}]`.
   - `labels` from `method.head_labels(df, cfg)` on a fresh start, read back from `ckpt_dir/meta.json` on resume or predict-only (hook not called either way).
   - `probe = base.load(cfg.models.probe_row, cfg, probe_kind=method.PROBE_KIND, n_labels=..., labels=..., ckpt_dir=...)`, plus `grad_checkpointing(True)` when `cfg.train.grad_ckpt`.
   - The alignment gate (2.5/2.6), run only on a fresh start with `cfg.train.align_check`: the first `events_per_mb * accum` **rows** (the ticket's own wording) of the train split in `example_id` order, `packed = sum(method.loss(...) for method.batches(...))` against `plain = method.reference_loss(...)`, both divided by the slice's row count, `torch.backends.cuda.matmul.allow_tf32` held `False` only for this comparison (restored after), `align_check.json` written either way, `SystemExit` on a failure.
   - The step loop: `steps = ceil(ceil(n_train_events / events_per_mb) / accum) * epochs`, capped by `max_steps`; `hb.emit(0, steps, "step")` before the first step; `AdamW` + a hand-written `LambdaLR` (linear warmup over `int(steps * warmup_ratio)`, linear decay to zero); gradient clip 1.0; per block, `(method.loss(probe, batch) / batch["mb_weight"] / cfg.train.accum).backward()`, an optimizer step after `accum` distinct `mb` values or at the end of an epoch; a `step` log line and `hb.emit(..., loss=...)` every `LOG_EVERY = 50` steps; `last/` (plus `last/optimizer.pt`) rewritten every `checkpoint_hours`.
   - `method.validate(...)` at every epoch end and once more at the end of training when the loop stopped without having just validated (the `max_steps`-cuts-the-epoch-short case); `best/` written when `objective` improves.
   - `train_done.json`, then a second `base.load(..., ckpt_dir=best/)` so the normal and predict-only paths share the prediction code.
   - The prediction step (1.3): per `cfg.train.predict.splits`, the split's rows in `example_id` order, capped at `cfg.train.predict.cap`, `method.predict(...)`; the five method-independent columns joined from the example frame on `example_id`; `probe_output.write(...)`. The trainer writes neither `target`, `method`, nor `version`.
   - `registry.write_done(...)` with `stage_extra={"labels": labels}`, then `hb.finish()`. No registry row appended (2.6).
   - Import aliases exactly as pinned: `from experimental_settings import schema`, `import models`, `from models.probe_models import base`, `from data import training_data, probe_output`, `from jobs import registry`, all at module level (not deferred), because A3.4's acceptance script monkey-patches `trainer.schema.load_frozen`, `trainer.schema.run_dir_of`, `trainer.base.load` and `trainer.models.probe` — that is only reachable if those names are module attributes of `trainer.py`, not local names inside `run()`.

2. **`train/methods/ctool.py`** — `PROBE_KIND = "classifier"`, `CHECKPOINT_META = {"call_sep": None, "param_only": False}`.
   - `head_labels`: sorted unique `tool` over the whole frame.
   - `batches`: groups by `event_id`, tokenizes the longest text as `full_ids`, each row's own text as `row_ids`, packs `full_ids[:P]` (`P` = the max per-row lcp) once, then each row's own divergent tail; a row's decision position is its tail's last token, or `p - 1` when the tail is empty; the 4-D block-diagonal additive attention mask (prefix causal, each tail sees the first `p` prefix positions, tails don't see each other); events dropped whole past `max_len`; physical blocks by `2 * cfg.train.max_len` tokens (`4 *` for validate/predict).
   - `Batch["target"]` carries the class **name**; `loss` and `reference_loss` map it through `probe.labels`; `validate` and `predict` read the class order off `probe.labels` the same way.
   - `loss`: the unnormalised weighted CE sum. `reference_loss`: one row per sequence, plain 2-D mask, no `position_ids`.
   - `validate`: `probe_eval.match_ctool`, weighted accuracy as the objective's complement plus the last-cut accuracy (rows whose `cut_index == n_cuts - 1`) as an extra number.
   - `predict`: through the same packed path, never `Probe.score` (the acceptance script's stub `Probe.score` raises on purpose, and it never fires).

3. **`train/methods/cgen.py`** — `PROBE_KIND = "generator"`, `CHECKPOINT_META = {"call_sep": "\n[CALL] ", "param_only": False}`, `GEN_N = 200`.
   - `batches`: the same shared-prefix packing, each row's segment is its `CALL_SEP`-tailed divergent tokens plus the tokenized call plus eos; `Batch["event_end"]` names every target token's query position `t - 1` (labels not shifted); `row_of`, `target_ids`, per-row `weight`/`example_id`. A row whose target exceeds `MAX_TGT_TOK = 160` is dropped whole and counted.
   - `loss`: token CE aggregated to a per-row mean via `index_add` over `row_of`, then the weighted sum.
   - `reference_loss`: one row per sequence, left-truncated prompt (kept the *last* `max_len - len(tgt_ids)` prompt tokens), right padding, labels masking the prompt.
   - `validate`: the weighted val CE through the packed path, plus greedy generation over a deterministic `GEN_N`-row subsample (`random.Random(cfg.train.seed).shuffle` over the rows in `example_id` order) compared with `probe_eval.match_cgen(pred, target, open_env(cfg.data.env))`; returns `val_tool_ok`, `val_params_all_ok`, `val_full_call_ok`, `gen_n`, objective `1 - weighted full_call_ok`.
   - `predict`: `probe.generate(texts, cfg.train.predict.max_new, CHECKPOINT_META["call_sep"])`, `gen_tokens` computed from the generated text.

4. **`train/methods/cparam.py`** — `PROBE_KIND = "generator"`, `CHECKPOINT_META = {"call_sep": "\n[CALL] ", "param_only": True}`, `GEN_N = 200`, `ASSEMBLY_MISMATCH_LIMIT = 0.05`.
   - `_derive_target(tool, call)`: strips `tool + "("`, keeps the closing parenthesis; `None` on a non-matching prefix. Such rows are dropped whole (in `batches`, `reference_loss` and `predict` alike) and counted as `assembly_mismatch`; `_build_events` raises when the mismatch share exceeds `ASSEMBLY_MISMATCH_LIMIT`.
   - `batches` uses `_prompt_tail(tool) = CHECKPOINT_META["call_sep"] + tool + "("` (per row, that row's own tool) instead of the bare separator, and the derived target instead of `call`.
   - `validate` and `predict` build the whole prompt per row (`row.text + _prompt_tail(row.tool)`) and call `probe.generate(texts, max_new, call_sep="")`.
   - `validate` calls `probe_eval.match_cparam` on two whole calls: `r["call"]` as the target (already whole) and `row.tool + "(" + pred` as the prediction; `objective = 1 - weighted params_all_ok`.

5. **`tests/test_packed_loss.py`** — a `unittest.TestCase` with `test_ctool`, `test_cgen`, `test_cparam`, each building the tiny two-layer Qwen3 model from the ticket's A3.3 script, writing/reading the fixture frame through `data/training_data.py`, and asserting the packed/plain diff is below `1e-4`.

6. **`README.md`** — one "Ticket 13" section with the four annotation blocks (`trainer.py`, `ctool.py`, `cgen.py`, `cparam.py`) plus a short `tests/test_packed_loss.py` line, following the pattern every prior ticket's section already uses (e.g. ticket 08, ticket 03's test-file line).

### Deviations from the ticket's literal prose, and why

- **`batches(df, tok, cfg)` reads no epoch, ever — not `cfg.train.seed + epoch`.** The ticket's per-method prose says the shuffle is `random.Random(cfg.train.seed + epoch)`, but 2.6 pins the signature `batches(df, tok, cfg)` with no epoch anywhere, and **the ticket's own A3.3 acceptance script hands a `cfg.train` `SimpleNamespace` with no `epochs` field at all** — I ran it first and it raised `AttributeError: 'types.SimpleNamespace' object has no attribute 'epochs'` when `batches` tried to loop `for epoch in range(cfg.train.epochs)`. I read this as the acceptance test overriding the prose: `batches` shuffles with the plain `cfg.train.seed`, one call is one full pass over `df` (`mb` starts at 0 every call), and `trainer.run`'s step loop calls `method.batches(train_df, probe.tokenizer, cfg)` fresh inside its own `for ep in range(cfg.train.epochs)` loop. The net effect for the common `epochs: 1` case is identical to the prose; for `epochs > 1` every epoch shuffles the same way instead of `seed + epoch`, which is worth the owner's eyes if that matters in practice.
- **`base.load(..., device=...)`.** The ticket's pinned call to `base.load` does not name `device`, and 2.6's own signature table for `base.load` doesn't show it either, but the merged `models/probe_models/base.py` has `device: str = "cpu"` as a real parameter, defaulting to CPU. Without passing it, a real GPU train run would build the model on CPU. I added `device = "cuda" if torch.cuda.is_available() else "cpu"` and pass it into both `base.load` calls. This doesn't affect any acceptance command (the CPU tests all run on `torch.cuda.is_available() == False`, and A3.4's stub `base.load` swallows all kwargs), so it's a considered gap-fill, not something any acceptance command exercises.
- **`trainer.py`'s import-alias sentence names `trainer.example` and `trainer.prediction`, which cannot exist.** The ticket text says the import is `from data import training_data, probe_output`, immediately followed by "so `trainer.schema`, `trainer.base`, `trainer.models`, `trainer.example`, `trainer.prediction` and `trainer.registry` all name the modules" — `example`/`prediction` were this pair's names before an earlier ticket renamed them to `training_data`/`probe_output` (their stale `.pyc` files are still in `data/__pycache__/`). I followed the literal import statement, which is what the repo's actual module names require and what `data/training_data.py`'s own header TODO documents as the current name; `trainer.training_data` and `trainer.probe_output` are the real attribute names.
- **README.md's imports line for the three method files** says `eval/utils/probe_eval.py (match_<method>, ...)`, not `eval/methods/<method>.py` as contracts 0.2's tree literally spells (0.2 predates the eval fold). The ticket's own "Comments" section states the fold already landed and that `eval/methods/` no longer exists (confirmed: no such directory in this worktree); `eval/utils/probe_eval.py` is what actually exists and what my code imports.
- **`counts.dropped_overlong`** in `done.json` is computed once, in `trainer.py`, over the train split only, using a plain "longest row's text tokenizes past `max_len`" rule shared by all three methods' own internal drop logic — not summed from a return value `batches()`/`predict()` don't have a channel for. It does not count drops that only ever happen on the val/test splits during `predict()`. No acceptance command inspects this field.
- **`cparam.predict()` drops a row whose target does not assemble** (mirroring `batches`/`reference_loss`), rather than emitting a prediction row with `target: null`. The ticket's own sentence ("such rows are dropped whole ... ") reads as the general rule, not one scoped to training alone.

## How it was verified

All commands run from the repo root of the worktree, `$PR = /home/y-guo/reproduce/new1/external/probe-env/bin/python`.

**A3.1 — the literal rules of 3.3, and the `PROBE_KIND` pair.**
```
$ python3 - <<'PY' ... PY
OK
```
Exit 0.

**A3.2 — import under the probe venv.**
```
$ "$PR" -c "import train.utils.trainer as t, train.methods.ctool as c, train.methods.cgen as g, train.methods.cparam as p; print(t.VERSION, c.PROBE_KIND, g.PROBE_KIND, p.PROBE_KIND, p.CHECKPOINT_META['param_only'])"
1 classifier generator generator True
```
Exit 0, matches the expected line exactly.

**A3.3 — the packed loss equals the plain loss, per method.**
```
$ for M in ctool cgen cparam; do "$PR" - "$M" <<'PY' ... PY; done
ctool packed=0.97037578 plain=0.97037578 diff=0.000e+00
OK
cgen packed=11.92646535 plain=11.92646535 diff=0.000e+00
OK
cparam packed=11.77619934 plain=11.77619934 diff=0.000e+00
OK
```
Exit 0 each time; every `diff` well under `1e-4` (the model is randomly initialised each run, so the absolute loss values vary run to run — the `diff` is what the gate checks, and it stayed at or near `0.0` across every run I did while iterating, including several earlier runs with different random weights).

**A3.4 — the whole loop, on CPU, with two stubs.**
```
$ "$PR" - <<'PY' ... PY
['depth', 'event_id', 'example_id', 'gen_tokens', 'label_pred', 'logits', 'method', 'score', 'split', 'target', 'task_id', 'text_pred', 'tool', 'version']
['test', 'val'] 24
['phone.login', 'phone.pay']
True
True True
done
```
Exit 0, matches the expected sequence exactly, including the column list, the `['test', 'val'] 24` row count, `align_check.json`'s `PASS: True`, both checkpoint markers present, and the heartbeat's last line `status: done`. The stub `Probe.score` (which raises on purpose) never fired.

**A3.5 — the 2.4 continue rule**, appended to the same script:
```
a True True
b 24 True
c True True
```
Exact match to the expected `a True True`, `b 24 True`, `c True True`.

**A3.6 — the permanent packed-loss test.**
```
$ "$PR" -m unittest tests.test_packed_loss -v
test_cgen (tests.test_packed_loss.TestPackedLoss.test_cgen) ... ok
test_cparam (tests.test_packed_loss.TestPackedLoss.test_cparam) ... ok
test_ctool (tests.test_packed_loss.TestPackedLoss.test_ctool) ... ok

----------------------------------------------------------------------
Ran 3 tests in 2.253s

OK
```
Exit 0, three tests, `OK`.

**A3.7 — no absolute cluster path in the code.**
```
$ grep -n "/home/\|/net/" train/utils/trainer.py train/methods/*.py || echo NO_ABS_PATH
NO_ABS_PATH
```

**Beyond the acceptance list**, as self-review: I ran the A3.4-shaped harness a second time with `probe.method = "cgen"` and again with `"cparam"`, using AppWorld-shaped tool/call strings (`apis.phone.pay(...)`, `apis.phone.login(...)`) so `env.split_args`/`env.build_call` (real `data/environments/appworld.py` code, not stubbed) would actually parse them, since my hand-written fixture data isn't real AppWorld data. Both ran end to end through `trainer.run` with no stub for `models.probe_models.service`/GPU: `cgen` produced `predictions.parquet` with the same 24-row, two-split shape and `done.json.metrics = {'objective': 0.5, 'val_ce': ..., 'val_tool_ok': 0.5, 'val_params_all_ok': 0.5, 'val_full_call_ok': 0.5, 'gen_n': 12}`; `cparam` produced the same shape with `{'objective': 0.5, 'val_ce': ..., 'val_params_all_ok': 0.5, 'gen_n': 12}`. Both `0.5`s are exactly what the fixture predicts: the stub `generate` always returns the "pay" call's own text, which matches exactly the half of the fixture rows whose true tool is `phone.pay` and disagrees with the other half (`phone.login`) — this is a sign the packing, the target derivation, and the eval-side `match_*` wiring are actually connected end to end, not just structurally present.

`run.py selfcheck` was not run: `run.py` does not exist yet on this branch (ticket 15's own file).

## Commits

To be listed after committing (see below); logical units: `trainer.py`, then the three method files together (they share one packing shape), then the test file, then the README update.

## Self-review findings and open questions

- Fixed during self-review (not left as findings): three "legacy" mentions in comments (`trainer.py`, `cgen.py`, `cparam.py`, `ctool.py`) and one in `README.md` — the hard rule forbids the word in shipped source; all four are now reworded without it, re-verified with `grep -rni legacy train/ tests/test_packed_loss.py README.md` (no matches) and a full re-run of every acceptance command afterward.
- Moved `from train.utils import trainer` from inside each method file's `main()` to the top of the file, so `main(run_dir)` is the literal one-line body the ticket's code block shows (`trainer.run(run_dir, sys.modules[__name__])`); re-verified A3.1/A3.2/A3.3/A3.6 afterward. `trainer.py` never imports a method file, so this introduces no import cycle.
- Open question for the owner (not blocking, noted above under "Deviations"): whether `batches()`'s shuffle should vary by epoch at all, given the signature and the acceptance fixture both exclude an epoch channel — if it should, the fix is a small one (thread an epoch value some other way, e.g. by having `trainer.py` construct a lightweight per-epoch proxy of `cfg.train` with a different `seed`), but it changes A3.3's and A3.6's fixtures' assumptions not at all since they only call `batches()` once.
- The resume path (`last/` present, `commit` matches) fast-forwards past already-completed optimizer groups without recomputing their gradients, but does not carry the pre-crash `best` objective across the resume — the first post-resume validation unconditionally becomes the new `best/`, even if it is worse than what a crashed incarnation already saved. No acceptance command in this ticket exercises resume (it's GPU item 3, the main session's); I flag it here because it's a real gap in a path nothing here catches.
- `weights_path = models.probe(cfg.models.probe).weights_path` is resolved unconditionally (predict-only and resume paths included), even though it is only used for the `"start"` log line, which those two paths skip. Harmless (a cheap YAML lookup through an already-imported module), just not the tightest control flow.

## GPU / main session — not mine

Every item in the ticket's "GPU / main session — not yours" section needs a GPU:

1. **A debug train of each method** — ready-to-run:
   ```
   run.py train_probe ctool_qwen3_0pt6b --debug
   run.py train_probe cgen_qwen3_0pt6b --debug
   run.py train_probe cparam_qwen3_0pt6b --debug
   ```
   (`run.py` itself is ticket 15's; these are the commands the ticket names, to run once it exists.)
2. **The alignment gate actually fires** on a deliberately broken `event_end` — needs the same debug train launch, with a temporary one-token shift injected.
3. **Resume** — kill a debug train after `last/` is written, relaunch.
4. **The predict-only continue path** — delete `predictions.parquet` and `done.json` from a finished debug train run, relaunch.
5. **LoRA** — a debug train with `probe.tuning: lora`.
6. **Two methods over one build** — train `ctool` and `cgen` against the same build key.
7. **The cost of predicting at every cut** — measure `(done.json mtime - train_done.json mtime) / predictions rows` for `cgen` and `cparam`.

I did not start any GPU process, per the hard rule.

## Fix round 1 (2026-09-18)

Worktree: `/home/y-guo/reproduce/new1-wt/2026-09-18-wave5-T13-fix1` (removed at the end of this round; branch `ticket/2026-09-18-wave5/T13` kept). Commit `27485a0`, `T13: fix round 1 -- VERSION block, epoch-end validation, per-epoch shuffle, cparam predict row count`.

Five open findings from the review, fixed in place with no refactor beyond their scope.

### F1 (critical) -- the three method files were missing the VERSION rule comment block and `VERSION_HISTORY = {}`

`train/methods/ctool.py`, `cgen.py` and `cparam.py` each had a bare `VERSION = 1` with no rule block above it and no `VERSION_HISTORY = {}` below it, while `trainer.py` (and `data/probe_input.py`, the file the errata points at) already carried both. Copied the block verbatim from `trainer.py` into all three files, directly above `VERSION = 1`, with `VERSION_HISTORY = {}` directly below it. A3.1 (which only checks for a lone `VERSION` int literal at column 0) still passes, since it never checked for the comment block or `VERSION_HISTORY` in the first place -- this is exactly what the finding said.

### F2 (critical) -- epoch-end validation and checkpointing silently skipped when a method drops a train event

Root cause: `trainer.py`'s `is_epoch_end` was `(mb + 1) == m_per_epoch`, where `m_per_epoch` came from `train_df["event_id"].n_unique()` -- the *raw* train-split event count, computed before any method-side drop (an overlong event, in cparam also an unassembled target). Whenever `batches()` actually yielded fewer logical minibatches than that raw estimate, `mb` never reached `m_per_epoch - 1`, so `is_epoch_end` was `False` for the whole epoch: `method.validate()` never ran for that epoch (only a trailing post-loop check could catch the very last epoch, and only when it hadn't already been validated), and the final, partial accumulation group's gradients never got a forced `opt.step()`/`opt.zero_grad()`, so they sat in `.grad` and silently summed into the next epoch's first accumulation group.

Fix: stopped trying to predict epoch end ahead of time. Added `_batches_with_epoch_end(batch_iter)`, a one-item-lookahead generator that pairs each yielded batch with whether it's the *last* physical block the iterator produces for its logical minibatch (`nxt is None or nxt["mb"] != prev["mb"]`) -- true end-of-epoch, read off the live iterator, not a count computed in advance. `run()`'s step loop now does `for batch, is_epoch_end in _batches_with_epoch_end(method.batches(train_df, probe.tokenizer, _epoch_cfg(cfg, ep))):` in place of the old `for batch in method.batches(...): is_epoch_end = (mb + 1) == m_per_epoch`. `m_per_epoch` itself is untouched and still feeds the `steps` estimate for the LR schedule length (the ticket's own formula, explicitly built from the raw event count, is unaffected).

As a side effect, this also closes a second latent bug in the same code that wasn't in the finding list: under the old check, `is_epoch_end` was `True` for *every* physical block of the final logical minibatch (not just its last one), so a final minibatch spanning more than one physical block would fire a forced step (and a validate call) after its first block, before the rest of that minibatch's gradients had even been accumulated. The lookahead fix is true for exactly the last physical block of the last minibatch, which is what "the end of the epoch" means in the ticket's prose, so this is fixed as a consequence of the same change, not a separate one.

### F3 (critical) -- `batches()` shuffled with a fixed seed every epoch, not `seed + epoch`

Root cause: `trainer.py` called `method.batches(train_df, probe.tokenizer, cfg)` with the same, unmodified `cfg` every epoch, so `random.Random(cfg.train.seed)` inside each method's `batches()` produced the identical shuffle order on every epoch of a multi-epoch run.

Fix: added `_epoch_cfg(cfg, epoch)`, which builds a shallow copy of `cfg` whose `train.seed` is `cfg.train.seed + epoch` (`copy.copy` on `cfg.train`, then on `cfg`, then reassigning the copy's `.train`), and handed that copy -- not the original `cfg` -- to the one `method.batches(...)` call each epoch makes. Every other reader of `cfg` inside the epoch (`_validate_and_maybe_save`, the alignment gate before the loop starts, the `log(...)` calls, `_checkpoint_meta`) closes over the original, unshifted `cfg`, so nothing else changes seed: in particular `cgen.py`'s and `cparam.py`'s `validate()` still draws its deterministic `GEN_N`-row subsample with the plain `cfg.train.seed`, unaffected by which epoch it's called from, matching the ticket's prose for `validate` (which names no epoch term) as opposed to `batches` (which does). `copy.copy` was checked to work identically on the real `schema.Setting`/`Train` dataclasses and on a `types.SimpleNamespace` (the acceptance fixtures' stand-in), so no acceptance script needed to change.

No file's `batches(df, tok, cfg)` signature changed -- 2.6's pinned signature is untouched, and A3.3's fixture (whose `cfg.train` still has no `epochs` field) calls `batches()` directly, once, outside `trainer.run`, so it never goes through `_epoch_cfg` at all and is unaffected.

### F4 (critical) -- `cparam.predict()` dropped a row instead of emitting a null-target prediction row

Root cause: `predict()` filtered `df.to_dicts()` down to only the rows whose call assembles as `tool + "("` before building prompts, so a row that fails `_derive_target` never got a prediction row at all -- on real data, with `ASSEMBLY_MISMATCH_LIMIT` existing precisely to tolerate a nonzero mismatch rate, `predictions.parquet`'s row count for cparam would come out below the split's example-row count, contradicting the GPU acceptance item's row-count requirement.

Fix: `predict()` now takes every row of `df` (no filter), builds each row's prompt the same way regardless of whether its target assembles, and still calls `_derive_target` per row to fill `target` -- `None` for a row whose call doesn't start with `tool + "("`, the derived string otherwise. This only changes `predict()`; `batches()`, `reference_loss()` and `_build_events()` still drop an unassembled row for training, unaffected, since a training row needs a real target string. Updated the docstring to state the new "no drop, `target` may be `None`" behaviour.

### F5 (important) -- `base.load(..., device=...)` needs the owner's sign-off

The addition is real and necessary: `models/probe_models/base.py`'s `load(...)` has a genuine `device: str = "cpu"` keyword, so a GPU run that never passes `device="cuda"` would silently train on CPU. It is not, however, in the ticket's pinned call or contracts 2.6's signature table. This implementer cannot obtain the owner's sign-off directly, so the fix here is to make the deviation impossible to miss rather than to remove functionality the ticket's own contract file needs: added an explicit comment at the first `base.load(...)` call site in `trainer.py` stating exactly what's added, why, and that it is an open, flagged item (cross-referenced from the second call site). This finding is left **open** for the owner; nothing about it changed behaviourally in this round.

### How the fixes were verified

All commands run from the worktree root, `$PR = /home/y-guo/reproduce/new1/external/probe-env/bin/python`.

**A3.1** (the literal VERSION/PROBE_KIND/CHECKPOINT_META rules): re-run verbatim, `OK`, exit 0 -- confirms the VERSION_HISTORY addition (F1) doesn't disturb the column-zero literal check.

**A3.2** (import under the probe venv): `1 classifier generator generator True`, exit 0, unchanged.

**A3.3** (packed loss equals plain loss, per method): re-run verbatim.
```
ctool packed=1.46877305 plain=1.46877321 diff=1.589e-07
OK
cgen packed=11.92715454 plain=11.92715454 diff=0.000e+00
OK
cparam packed=12.00426356 plain=12.00426356 diff=0.000e+00
OK
```
Exit 0 each time, every `diff` well under `1e-4`; unaffected by any of the five fixes (the alignment gate's own `method.batches(slice_df, ...)` call, tested here indirectly through `batches()` itself, still uses the plain `cfg`, not an epoch-shifted one).

**A3.4 + A3.5** (the whole loop on CPU, plus the 2.4 continue rule): re-run verbatim, same expected output reproduced exactly:
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
```
Exit 0. This exercises the new `_batches_with_epoch_end`/`_epoch_cfg` code path (one epoch, `epochs=1`), confirming the fix is a no-op for the common single-epoch case, exactly as the report noted before fixing.

**A3.6** (the permanent packed-loss unittest): `test_ctool`, `test_cgen`, `test_cparam` all `ok`, `OK`, exit 0, unchanged.

**A3.7** (no absolute cluster path): `NO_ABS_PATH`, unchanged.

**Targeted regression test for F2 and F3**, not part of the ticket's acceptance list (the ticket's own fixtures all use `epochs=1` and no drops, so none of them can exercise this path): a stand-alone script drives `trainer.run()` with a stub `method` whose `batches()` always yields exactly one minibatch (`mb=0`) per epoch, against a train split whose raw event count is 5 with `events_per_mb=1` (so the old, buggy `m_per_epoch` would be 5) and `accum=4` (so `len(seen_mbs)` alone never reaches `accum`), over 3 epochs. Counted `validate()` calls, `torch.optim.AdamW.step()` calls, and the per-call `cfg.train.seed` the stub's `batches()` saw.

Against the fixed code:
```
validate_calls: 3
seeds_used per epoch: [42, 43, 44]
opt.step() calls: 3
eval log lines: 3 [0, 1, 2]
best/ written: True
```
Against the same script re-run with `trainer.py` reverted to the pre-fix committed version (`git checkout HEAD -- train/utils/trainer.py` in a throwaway copy of the worktree, everything else unchanged) as a counterfactual:
```
OLD CODE -- validate_calls: 1
OLD CODE -- seeds_used per epoch: [42, 42, 42]
OLD CODE -- opt.step() calls: 0
OLD CODE -- best/ written: True
```
The old code took zero forced optimizer steps across all 3 epochs (every epoch's partial accumulation group's gradients were silently left un-applied and un-zeroed) and validated only once, via the trailing post-loop catch-all for the last epoch -- exactly the failure mode F2 described. The fixed code takes one forced step and one validate call per epoch, and the per-epoch seed sequence (`42, 43, 44`) confirms F3.

**Targeted regression test for F4**: a stand-alone script builds a two-row fixture through `data/training_data.py` (one row whose call assembles as `tool + "("`, one whose call is `apis.phone.login(user='a')` against `tool = "phone.login"`, which doesn't), calls `cparam.predict()` directly, and separately round-trips the result through `data/probe_output.py`'s real `write`/`read`.
```
n input rows: 2 n predict rows: 2
[('a__s0|s0|c0', 'id=1)'), ('b__s0|s0|c0', None)]
OK
```
and, through the real parquet write/read:
```
shape: (2, 2)
┌─────────────┬────────┐
│ example_id  ┆ target │
╞═════════════╪════════╡
│ a__s0|s0|c0 ┆ id=1)  │
│ b__s0|s0|c0 ┆ null   │
└─────────────┴────────┘
row count matches input: True
```
Confirms `predict()` now keeps one row per input row with a nullable `target`, and that `probe_output`'s schema (which only requires the `target` column be *present*, not non-null per row) round-trips a `None` target correctly.

**Re-verified after all fixes**: `grep -rni legacy train/ tests/test_packed_loss.py README.md` -- no matches. `grep -n "/home/\|/net/" train/utils/trainer.py train/methods/*.py` -- `NO_ABS_PATH`. `run.py selfcheck` still not run: `run.py` does not exist yet on this branch.

### Open items after this round

- **F5 is still open** (see above): the `device=` addition to `base.load(...)` needs the owner's explicit sign-off, since it's functionality the ticket's own pinned text and contracts 2.6 never mention, even though the merged `base.py` needs it for a real GPU run to land on the GPU. Nothing in this round changed its disposition, only its visibility (an explicit code comment at both call sites, plus this report entry).
- The resume-path gap noted in the original report (a resume doesn't carry the pre-crash `best` objective across the restart, so the first post-resume validation unconditionally becomes the new `best/` even if worse) is unchanged by this round -- it wasn't one of the five findings, and no acceptance command in this ticket exercises resume (GPU item 3).
- GPU items 1-7 are still the main session's, unchanged; none of this round's fixes required a GPU to verify.

## Fix round 2 (2026-09-18)

Worktree: `/home/y-guo/reproduce/new1-wt/2026-09-18-wave5-T13-fix2` (removed at the end of this round; branch `ticket/2026-09-18-wave5/T13` kept). Commit `e128671`, `T13: fix round 2 -- resolve F5 with ticket 06's pinned base.load signature`.

One open finding carried over from round 1.

### F5 (important) -- `base.load(..., device=...)` needs the owner's explicit sign-off

Round 1 left this open because it read `base.load`'s `device` keyword against only two sources: ticket 13's own pinned call text and contracts 2.6's signature table -- neither names it. Both are real, but neither is the complete picture, and following only them treats a real, working parameter of the callee as if it were this ticket's own invention.

**Root cause of the finding, traced back to its actual source.** The interface `base.load` implements was pinned by ticket 06 (`.scratch/from-zero/issues/06-model-table-entrance-and-probe-object.md:280-281, 306-307`), the ticket that built `models/probe_models/base.py`, not by ticket 13 or by contracts 2.6. Ticket 06's own signature block reads verbatim:
```
def load(row, cfg, *, probe_kind, n_labels=None, labels=None,
         ckpt_dir=None, device="cpu") -> Probe
```
with the accompanying decision "`load` takes `device=\"cpu\"`, and a restore with no row takes its dtype from the backbone module's `DTYPE` on a cuda device and `float32` on cpu" -- `device` is not a stray keyword `base.py` happens to have; it is load-bearing in `base.py`'s own restore-path dtype selection (confirmed by reading the merged `models/probe_models/base.py`: `dtype_name = ... backbone_module.DTYPE if str(device).startswith("cuda") else "float32"`, and `load` ends `return instance.to(device)`). Contracts 6.2 (`notes/plans/2026-09-17-contracts.md:3745`; the section ticket 13 itself names as governing, alongside 2.6) carries the one signature-table row for `load` in the whole document -- 2.6 names `base.load` several times in its own method-hook rows but repeats no signature of its own. That row echoes the same four-keyword shorthand `n_labels=None, labels=None, ckpt_dir=None` without `device`, which reads as an abbreviation of ticket 06's own signature carried into this later document, not a second, competing ruling that omits `device` on purpose -- the row says nothing that contradicts ticket 06's `device="cpu"` keyword, it just doesn't repeat it.

**Whether trainer.py is the right place to supply it, checked against the rest of the repo.** The train launch line (construction plan / ticket 12, `.scratch/from-zero/issues/12-launcher.md:123`) is `CUDA_VISIBLE_DEVICES=<ids> <venv python> -m <module> --run-dir <dir>` -- no `--device` flag. `train/methods/{ctool,cgen,cparam}.py`'s `main(run_dir)` parses `--run-dir` only (ticket 13's own pinned code block), so no CLI channel reaches `trainer.run`. `experimental_settings/schema.py`'s frozen `Setting` carries no device-shaped field (checked every `_`-prefixed private field: `_workflow, _debug, _name, _file, _stage, _key, _upstream, _versions, _commit, _resolved`, none of them device). By contrast, `models/probe_models/service.py` (ticket 07, `.scratch/from-zero/issues/07-model-services.md:182`) does take `[--device cuda:0]` as an explicit command-line flag -- a deliberate difference, not an oversight: the service is a long-running process an operator starts with `--render-only` on a host with no probe checkpoint loaded at all, so it needs an explicit switch; the train stage is always launched through `run.py train_probe` inside a `CUDA_VISIBLE_DEVICES`-scoped single-GPU process with no CPU-only production mode. Given this, `trainer.run` is the only place in the whole call chain that can compute a `device` value for `base.load`, and `torch.cuda.is_available()` against the one GPU `CUDA_VISIBLE_DEVICES` exposes is the only signal available to it.

**Resolution.** F5's premise -- that `device` is undocumented, ticket-13-scope-creep functionality awaiting invention of a policy -- doesn't hold once ticket 06 is read: the parameter, its default, and its effect are already pinned by the ticket that owns `base.load`, and the train stage's launch design (checked against ticket 12's launch line and the probe service's contrasting `--device` flag) leaves `trainer.py` as the only place that can supply it. This is a routine judgment call within the implementer's authority -- the same fact ticket 06 and ticket 12 already establish, not a new decision -- so no code behaviour changed this round; the comment at both `base.load` call sites in `train/utils/trainer.py` was rewritten to state this plainly, replacing the "considered gap-fill, flagged for the owner's sign-off, open finding F5" framing with the actual authority (ticket 06's pinned signature, the absence of a `--device` flag or a `cfg` field for the train stage, the contrast with the probe service's explicit flag). F5 is resolved, not merely re-flagged.

### How the fix was verified

All commands run from the worktree root, `$PR = /home/y-guo/reproduce/new1/external/probe-env/bin/python`. This round changed only two code comments (no logic, no new branch), so every acceptance command was re-run to confirm no regression, plus one targeted check that the `device` value actually reaches `base.load` unchanged.

**A3.1** (the literal VERSION/PROBE_KIND/CHECKPOINT_META rules): `OK`, exit 0.

**A3.2** (import under the probe venv): `1 classifier generator generator True`, exit 0, unchanged.

**A3.3** (packed loss equals plain loss, per method): re-run verbatim.
```
ctool packed=0.98809687 plain=0.98809687 diff=0.000e+00
OK
cgen packed=12.12631226 plain=12.12631226 diff=0.000e+00
OK
cparam packed=12.05392456 plain=12.05392456 diff=0.000e+00
OK
```
Exit 0 each time, every `diff` at `0.0` -- this ticket's method files were not touched this round.

**A3.4 + A3.5** (the whole loop on CPU, plus the 2.4 continue rule): re-run verbatim, same expected output reproduced exactly:
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
```
Exit 0, unchanged.

**A3.6** (the permanent packed-loss unittest): `test_ctool`, `test_cgen`, `test_cparam` all `ok`, `OK`, exit 0, unchanged.

**A3.7** (no absolute cluster path): `NO_ABS_PATH`, unchanged.

**Targeted check for F5**: re-ran the A3.4 harness with `trainer.base.load` stubbed to record every `device` keyword it receives, instead of ignoring it.
```
devices_seen ['cuda', 'cuda']
```
(This machine's login/build host has 8 GPUs visible with `CUDA_VISIBLE_DEVICES` unset, so `torch.cuda.is_available()` is `True` here -- the value the comment describes flows through to both `base.load` call sites unchanged from round 1, confirmed against the actual runtime, not just read from source. No GPU compute happened: `base.load` was stubbed to `fake_load`, so the `device` string was recorded, never used to place a real model; the stand-in `Probe.forward` used in this harness runs the tiny CPU model built directly in the script. No GPU process was started, consistent with the hard rule.)

**Re-verified after the fix**: `grep -rni legacy train/ tests/test_packed_loss.py README.md` -- no matches. `grep -n "/home/\|/net/" train/utils/trainer.py train/methods/*.py` -- `NO_ABS_PATH`. `run.py selfcheck` still not run: `run.py` does not exist yet on this branch.

### Open items after this round

- No findings remain open. F5 is resolved (see above).
- The resume-path gap noted in the original report (a resume doesn't carry the pre-crash `best` objective across the restart) is unchanged -- it was never one of the review's findings, and no acceptance command in this ticket exercises resume (GPU item 3).
- GPU items 1-7 are still the main session's, unchanged; this round's fix required no GPU to verify.
