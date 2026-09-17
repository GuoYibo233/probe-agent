# Build plan: `train/` (trainer + the three probe methods)

Planner: train folder. Written 2026-09-17 against
`notes/plans/2026-09-14-structure-from-zero.md` (Part 1 tree, fixed),
`notes/plans/2026-09-17-contracts.md` (Parts 0.2, 1.2, 1.3, 1.5, 1.6, 2.1-2.6,
3.3, 3.4, 5.2, 5.3, 6.2, 8.0, 8.4) and the old code under `legacy/`.

Four files, one venv (`probe` = `external/probe-env`, Python 3.11, torch
2.11.0+cu128, transformers 5.14.1, peft 0.20.0, polars 1.44.2). No file outside
the fixed tree is added; one file under `tests/` is added for the packed-loss
check the tree's `tests/` line names.

---

## 1. Files

### 1.1 `train/utils/trainer.py`

**One sentence.** The training loop every probe method shares: frozen setting ->
arguments, seed, probe, tuning, the alignment gate, the step loop, validation
and checkpoints, resume, the heartbeat, and as its last step the prediction rows
over `train.predict.splits` with the probe still on the card.

**venv.** `probe`. Runs on a card; a CPU run is possible and is what the
acceptance scripts of section 3 use.

**Imports (0.2, authoritative).** `experimental_settings/schema.py`,
`models/__init__.py`, `models/probe_models/base.py`, `data/training_data.py`,
`data/probe_output.py`, `jobs/registry.py`; third-party `[torch]` (erratum E11:
0.2 says `[torch, peft]`; peft lives in `base.py` and the LR schedule is a
`torch.optim.lr_scheduler.LambdaLR`).
**Used by.** `train/methods/{ctool,cgen,cparam}.py`.
**Reads.** `<build run_dir>/examples.parquet` (through `data/training_data.py`), the
checkpoint layout of 1.6.
**Writes.** `best/`, `last/` (plus `last/optimizer.pt`, erratum E6),
`train_log.jsonl`, `align_check.json`, `train_done.json`,
`predictions.parquet`, `consumed.json`, `heartbeat/0-<launch>.jsonl`,
`done.json` (whose `stage_extra` carries the class order).

**Module-level names.**

```python
VERSION = 1                      # column zero, exactly once, integer literal (3.3)

def run(run_dir: Path, method) -> None      # 2.6, the only public entry point
```

Everything else is private (`_`-prefixed). `run` never branches on the method
name and never reads a method-specific key of `Batch` other than the two the
contract-errata pin (`mb`, `mb_weight`, E4).

**The import aliases are part of the contract**, because the acceptance scripts
of section 3 replace two of them: the file writes
`from experimental_settings import schema`, `import models`,
`from models.probe_models import base`, `from data import training_data, probe_output`,
`from jobs import registry` — so `trainer.schema`, `trainer.base`,
`trainer.models`, `trainer.example`, `trainer.prediction` and
`trainer.registry` all name the modules. The three method files import
`from train.utils import trainer`, `from models.probe_models import base`,
`from data import training_data`, and `from eval.methods import <name> as ev` (plus
`from data.environments import open_env` in the two generators).

**What `run` does, in order.**

1. `cfg = schema.load_frozen(run_dir)` (2.6, 5.1). Nothing else resolves a
   setting; no setting name is on the command line.
2. `hb = registry.beat(run_dir, 0)` (8.0, 8.4: a one-process stage is piece 0).
3. The continue rule of **2.4**, computed from what is on disk, in this order:
   | state | action |
   |---|---|
   | `done.json` present | return at once, run nothing |
   | `train_done.json` present and `predictions.parquet` absent | go to step 11 with `ckpt_dir = run_dir/"best"` |
   | `last/` present and `last/meta.json["commit"] == cfg._commit` | resume from `last/meta.json["step"]` |
   | `last/` present and its `commit` differs | `raise SystemExit`, printing both commits and `run.py retry` |
   | `train_log.jsonl` present and none of the above | `raise SystemExit` (legacy `train_causal_share.py:1017-1020`) |
   | none of the above | start fresh |
4. `torch.manual_seed(cfg.train.seed)`; `torch.backends.cuda.matmul.allow_tf32 =
   False` while the alignment gate runs (legacy `train_causal_share.py:748-925`
   runs the gate with TF32 off).
5. Read the example frame:
   `build_dir = schema.run_dir_of("build", cfg._upstream["build"], debug=cfg._debug)`
   (2.1), `df = training_data.read(build_dir / "examples.parquet")`. Write
   `consumed.json` = `[{path, sha1, n_rows}]` for that one file (1.5).
6. `labels = method.head_labels(df, cfg)` on the **whole** frame, before
   `base.load` (2.6, 1.3). On a resume or on the predict-only path the list is
   read back from `ckpt_dir/meta.json` and the hook is not called.
7. `probe = base.load(cfg.models.probe_row, cfg, probe_kind=method.PROBE_KIND,
   n_labels=(len(labels) if labels else None), labels=labels,
   ckpt_dir=<None | run_dir/"last" | run_dir/"best">)` (6.2). `weights_path` for
   the start log line comes from `models.probe(cfg.models.probe)` (6.2).
   `probe.grad_checkpointing(True)` when `cfg.train.grad_ckpt` (E5).
8. The alignment gate, when `cfg.train.align_check` and the run is not resuming
   (2.5, 2.6): take the first `cfg.train.events_per_mb * cfg.train.accum` rows
   of the `train` split in `example_id` order; `packed = sum(method.loss(probe,
   b) for b in method.batches(slice_df, probe.tokenizer, cfg))`;
   `plain = method.reference_loss(probe, slice_df)`; both divided by
   `len(slice_df)`; stop when `abs(packed - plain) > 1e-4`. Both sides run under
   `torch.no_grad()` with `probe.set_training(False)`, restored afterwards.
   Write `align_check.json` = `{"PASS": bool, "packed": float, "plain": float,
   "diff": float, "tol": 1e-4, "n_rows": int, "method": <module name>}` either
   way, and exit non-zero on a failure.
9. The step loop. `steps = ceil(ceil(n_train_events / events_per_mb) / accum) *
   epochs`, capped by `cfg.train.max_steps` when it is set;
   `hb.emit(0, steps, "step")` before the first step (8.4: the signal that the
   model finished loading). Optimizer `torch.optim.AdamW(
   probe.trainable_parameters(), lr=cfg.train.lr, weight_decay=0.01)`; schedule
   a `LambdaLR` that rises linearly over `int(steps * cfg.train.warmup_ratio)`
   steps and decays linearly to zero (the shape of
   `transformers.get_linear_schedule_with_warmup`, which legacy calls at
   `train_causal_share.py:1100`); gradient clip 1.0. Per logical minibatch,
   `method.batches` yields one `Batch` per physical block, consecutive blocks of
   one logical minibatch carrying the same `mb`; for each block
   `(method.loss(probe, batch) / batch["mb_weight"] / cfg.train.accum).backward()`
   (legacy `train_causal_share.py:199-241`), then `clip_grad_norm_`, `opt.step()`,
   `sch.step()`, `opt.zero_grad()` after `accum` distinct `mb` values or at the
   end of the epoch. A `step` line into `train_log.jsonl` and
   `hb.emit(gstep, steps, "step", loss=...)` every `LOG_EVERY = 50` steps
   (module constant; it changes no number).
10. Validation and checkpoints. `method.validate(probe, val_df, probe.tokenizer,
    cfg)` at the end of every epoch, and once more at the end of training when
    `train.max_steps` cut the last epoch short (erratum E7). `best/` is written
    when the returned `objective` is lower than every earlier one (2.6: lower is
    better), through
    `probe.save(run_dir/"best", labels=labels, extra=method.CHECKPOINT_META,
    meta={"backbone": cfg.models.probe, "tuning": cfg.probe.tuning,
    "max_len": cfg.train.max_len, "train_key": cfg._key})` (1.6, 6.2).
    `last/` is rewritten every `cfg.train.checkpoint_hours` with the same call
    plus `{"step": gstep, "epoch": ep, "commit": cfg._commit, "rng_state":
    {...}}` in `meta`, and `torch.save({"opt": ..., "sch": ...},
    run_dir/"last"/"optimizer.pt")` beside it (E6). `hb.emit` is called during a
    long validation so the stall line is not crossed (legacy
    `train_causal_share.py:243-270`, the `beat` callback).
11. After the last step: write `train_done.json` =
    `{"key": cfg._key, "commit": cfg._commit, "steps": gstep,
    "best_objective": float, "finished_at": time.time()}`, then **reload
    `best/`** into the probe (`base.load(..., ckpt_dir=run_dir/"best")`) so the
    normal path and 2.4's predict-only path run the same code.
12. The prediction step (1.3). For each split named by `cfg.train.predict.splits`,
    take that split's rows in `example_id` order, capped at
    `cfg.train.predict.cap` when it is set, and call `method.predict(probe, df,
    probe.tokenizer, cfg)`. Join the five method-independent columns
    `event_id`, `task_id`, `depth`, `split`, `tool` from the example frame on
    `example_id`, and write with `probe_output.write(run_dir /
    "predictions.parquet", frame)`, which stamps `version`. The trainer writes
    neither `target` nor `method` nor `version`.
13. `registry.write_done(run_dir, stage="train", key=cfg._key,
    commit=cfg._commit, counts={...}, versions=cfg._versions,
    metrics={"objective": best, **the validation extras}, report=None,
    stage_extra={"labels": labels})` (8.0, 1.5, 1.3), then `hb.finish()`.
    `counts` carries `train_rows`, `val_rows`, `predictions`,
    `dropped_overlong`. **No registry row is appended here** (2.6).

**Legacy source, and what is not ported.**

| what | legacy file:lines |
|---|---|
| the update loop, accumulation, clipping, logging, the eval point | `legacy/pipeline/train/train_causal_share.py:1164-1281` |
| per-block backward and the `W` / `n_g` normalisation | `train_causal_share.py:199-241` |
| the heartbeat during a long validation | `train_causal_share.py:243-270` |
| the optimizer, the schedule, the log file, the start line | `train_causal_share.py:1095-1137` |
| refusing a directory that already holds `train_log.jsonl` | `train_causal_share.py:1017-1020` |
| best-checkpoint saving and `best/meta.json` | `train_causal_share.py:1253-1278`, `train_causal_tool.py:509-536` |
| the LoRA-vs-full optimizer parameter list, grad-checkpoint preparation | `lora_util.py:122-150` (moves into `base.py`; the trainer calls `probe.trainable_parameters()` and `probe.grad_checkpointing()`) |

**Not ported, stated:** the GPU-memory probe (`train_causal_share.py:296-601`,
`worst_blocks` in `share_data.py:535-580`) — no `--mem-probe` and no setting
field for it; the read-only-tool arm (`--readonly-env`, `readonly_map.py`,
`READONLY.json`); `--smoke` and `--max-events` (replaced by `--debug`, 5.6);
`--force` (replaced by 2.4's continue rule); `--align-only`; the
hidden-state incremental alignment check (`train_causal_tool.py:228-290`) and
the reference-path machinery of `train_causal_share.py:603-925` (replaced by the
`loss` / `reference_loss` pair of 2.6); `RefBaselineDriftError` and the six
`--align-*` tolerances (2.5 pins one, `1e-4`); the `--fire-head` experiment
(`train_causal_callgen.py:110-135`); `--lr` resolution (`lora_util.py:45-73`,
now `probe.tuning` plus `train.lr` in the YAML); MLflow (9(a)#13).

**Behaviour change worth stating:** `train.warmup_ratio` defaults to `0.0`
(5.2) while legacy hardcodes `int(steps * 0.05)`
(`train_causal_share.py:1100`). A setting that wants the old schedule writes
`warmup_ratio: 0.05`. The schema owns the default; this plan does not change it.

---

### 1.2 `train/methods/ctool.py`

**One sentence.** The classification probe: its prefix-shared packing, its head
labels, its weighted cross-entropy, its validation accuracy and its prediction
rows.

**venv.** `probe`.
**Imports (0.2).** `train/utils/trainer.py`, `models/probe_models/base.py`,
`data/training_data.py`, `eval/methods/ctool.py`; `[torch]`.
**Used by.** none (program). **Reads/writes.** nothing directly; everything goes
through `trainer.py`.

**Module-level names** — all three literals at column zero, exactly once, per
3.3's text rule, because `schema.py` and `selfcheck` read them with `ast`:

```python
VERSION = 1
PROBE_KIND = "classifier"
CHECKPOINT_META = {"call_sep": None, "param_only": False}
```

**Hooks (signatures copied from 2.6).**

```python
def head_labels(df, cfg) -> list[str] | None
def batches(df, tok, cfg)            # -> Iterator[Batch]
def loss(probe, batch)               # -> Tensor
def validate(probe, df, tok, cfg)    # -> dict[str, float]
def predict(probe, df, tok, cfg)     # -> Iterator[dict]
def reference_loss(probe, df)        # -> Tensor
def main(run_dir) -> None            # one line: trainer.run(run_dir, sys.modules[__name__])
```

plus a `if __name__ == "__main__":` block parsing `--run-dir` only (2.6, 3.4:
the piece command is `-m train.methods.ctool --run-dir <dir>` and nothing else).

- `head_labels`: the unique values of the `tool` column of the **whole** frame,
  sorted ascending by name (2.6, 1.3). Never computed over the training split.
- `batches`: group the rows by `event_id`; the row texts of one event are nested
  prefixes (2.5 gates it), so tokenize the longest text as the event's
  `full_ids` and each row's own text as `row_ids`, take `p = lcp(row_ids,
  full_ids)` and pack `full_ids[:p_max]` once followed by every row's divergent
  tail `row_ids[p:]` (legacy `share_data.py:55-62, 362-393`). The decision
  position of a row is the last token of its own tail, or `p - 1` inside the
  shared prefix when the tail is empty; those positions are `Batch["event_end"]`
  (E2). The attention mask is the block-diagonal additive mask of
  `share_data.py:396-480` (prefix causal, each tail sees the first `p` prefix
  positions and its own tokens, tails do not see each other), so every row's
  hidden state equals the one an independent forward of `row_ids` would give.
  Drop every row of an event whose longest text exceeds `cfg.train.max_len`
  tokens (5.2, "a longer event is dropped whole") and count them. Split events
  into logical minibatches of `cfg.train.events_per_mb` after
  `random.Random(cfg.train.seed + epoch).shuffle` (legacy
  `share_data.py:482-497`) and each logical minibatch into physical blocks by
  `2 * cfg.train.max_len` tokens (legacy `share_data.py:499-533`, E12).
  Batch keys: `input_ids`, `attention_mask` (the 4-D additive mask),
  `position_ids`, `event_end`, `mb`, `mb_weight`, and the method's own
  `target` (class indices in `labels` order), `weight`, `example_id`.
- `loss`: `out = probe.forward(batch)`; `ce = F.cross_entropy(out.logits.float(),
  batch["target"], reduction="none")`; return `(ce * batch["weight"]).sum()` —
  the **unnormalised weighted sum** (E1). Legacy
  `train_causal_tool.py:487-489` is the same expression before its per-batch
  division.
- `reference_loss`: the same number computed one example row per sequence, in
  its plainest form — tokenize each row's text alone, right-pad, and go through
  `probe.forward` (the only place a method touches the model, 6.2) with a batch
  whose `attention_mask` is the plain 2-D 0/1 mask, no `position_ids`, and whose
  `event_end` names each sequence's last real token; weighted CE, weighted sum.
  This is the one piece written twice on purpose (2.6).
- `validate`: score the frame it is handed through the same packed path,
  compare with `eval/methods/ctool.py`'s `match(pred_label, target_tool, None)`
  (2.6: a classifier passes `None`), and return
  `{"objective": 1 - weighted_accuracy, "val_wacc": weighted_accuracy,
  "val_lastcut_acc": ...}`. Legacy `train_causal_tool.py:308-323`
  (`calA_weighted_acc` / `calA_lastbound_acc`); the last-cut accuracy is kept as
  an extra number, not as the objective.
- `predict`: one row per example row, through the same packed path (E13, not
  `Probe.score`, which is one sequence per text): `{"example_id", "method":
  "ctool", "target": <the row's `tool`>, "score": <largest softmax probability
  at temperature 1>, "label_pred": <argmax class name>, "logits": <the class
  logits in `labels` order>}` (1.3, 2.6).

**Legacy source.** `train_causal_tool.py:97-150` (event grouping and the label
vocabulary), `154-189` (the batch and the supervision positions — replaced by
the prefix-shared packing above), `308-323` (validation),
`487-489` (the weighted loss); `share_data.py:55-62, 362-480` (the packing and
the mask).
**Not ported:** `read_position` and the offset-mapping rule
(`share_data.py:583-611`) — the new packing retokenizes each row and shares by
token prefix, so the decision position is a row's own last token and matches
`Probe.score` exactly; `label_map.json` (1.3: the class order lives in
`best/meta.json`); `--readonly-env` label folding
(`train_causal_tool.py:107-121`); `Counter.most_common()` ordering
(`legacy/pipeline/annotate/build.py:404-406`) — 1.3 replaces it with the sorted
order because the old tie-break was unspecified.

---

### 1.3 `train/methods/cgen.py`

**One sentence.** The call-generating probe: its prefix-shared packing with one
target segment per cut, its loss positions, its exact-match validation and its
generated prediction rows.

**venv.** `probe`.
**Imports (0.2).** `train/utils/trainer.py`, `models/probe_models/base.py`,
`data/training_data.py`, `eval/methods/cgen.py`, `data/environments/__init__.py`
(`open_env`, for the environment `match` takes); `[torch]`.
**Used by.** none (program).

**Module-level names.**

```python
VERSION = 1
PROBE_KIND = "generator"
CHECKPOINT_META = {"call_sep": "\n[CALL] ", "param_only": False}
GEN_N = 200          # val rows generated per validation (E8); legacy GEN_N
```

`call_sep` is legacy `train_causal_callgen.py:102`; `param_only: false` is what
5.7 reads to allow this method as an `inject.probe_gen` (2.6).

**Hooks.** The same seven names as ctool, with `head_labels` returning `None`
(a generator has no head).

- `batches`: per event, `full_ids = tok(longest text)`; per row,
  `old_ids = tok(row.text + CALL_SEP)`, `p = lcp(old_ids, full_ids)`,
  `tail_ids = old_ids[p:]` (assert non-empty),
  `tgt_ids = tok(row.call, add_special_tokens=False) + [eos]`,
  `seg_ids = tail_ids + tgt_ids`, `seg_lab = [-100]*len(tail_ids) + tgt_ids`.
  Drop a row whose `tgt_ids` exceeds `MAX_TGT_TOK = 160` (legacy
  `train_causal_callgen.py:103`) and count it. Pack, mask, block and group
  exactly as in `share_data.py:362-533`. `Batch["event_end"]` names every target
  token's **query** position `t-1` (labels are not shifted:
  `share_data.py:455-470`), and the method's own keys carry `target_ids` (the
  token at `t`), `row_of` (which decision row each target token belongs to),
  `weight` (per row), `mb`, `mb_weight`, `example_id`.
- `loss`: `out = probe.forward(batch)`; `tok_ce = F.cross_entropy(
  out.logits.float(), batch["target_ids"], reduction="none")`; aggregate to a
  per-row mean by `index_add` over `row_of` divided by each row's target-token
  count (legacy `share_data`-side aggregation,
  `train_causal_share.py:179-197`); return `(row_ce * weight).sum()` (E1).
- `reference_loss`: legacy `train_causal_callgen.py:203-237` (`collate`) plus
  `268-294` (`inst_ce`) — one row per sequence, left-truncated prompt, right
  padding, labels masking the prompt, per-instance mean CE — weighted and
  summed over the slice. It reaches the model through `probe.forward` with a
  plain 2-D `attention_mask`, no `position_ids`, and an `event_end` naming each
  target token's query position in its own sequence.
- `validate`: the weighted val CE over the whole frame it is handed (the same
  packed path, legacy `train_causal_callgen.py:297-337`) **and** greedy
  generation over a deterministic subsample of `GEN_N` rows
  (`random.Random(cfg.train.seed).shuffle` over the rows in `example_id` order,
  legacy `train_causal_share.py:272-295`), compared with
  `eval/methods/cgen.py`'s `match(pred, target, env)` where
  `env = open_env(cfg.data.env)` (2.6, 2.1). Returns
  `{"objective": 1 - weighted full_call_ok, "val_ce": ..., "val_tool_ok": ...,
  "val_params_all_ok": ..., "val_full_call_ok": ..., "gen_n": ...}`.
- `predict`: one row per example row.
  `texts = [row.text for ...]`,
  `out = probe.generate(texts, cfg.train.predict.max_new,
  CHECKPOINT_META["call_sep"])` (6.2, 1.6, 2.6: the method supplies its own
  separator). Row: `{"example_id", "method": "cgen", "target": <the row's
  `call`>, "text_pred": out, "gen_tokens": len(tok(out,
  add_special_tokens=False)["input_ids"])}` (E9).

**Legacy source.** `train_causal_callgen.py:100-105` (constants), `137-200`
(target tokenization and the length drop), `203-237` (the plain form),
`268-294` (per-instance CE), `339-365` (greedy generation and exact match);
`share_data.py:169-357` (row construction, the `lcp` tail, the two hard stops),
`362-533` (packing, mask, blocks).
**Not ported:** the fire head (`train_causal_callgen.py:110-135, 268-294`'s
`fire` branch); `--readonly-env` row dropping (`share_data.py:272-280`);
`--overlong` / `select_keys` (`share_data.py:113-165`) — the new rule is one
event-level `max_len` drop plus the `MAX_TGT_TOK` drop; the
`ASSEMBLY_MISMATCH_LIMIT` hard stop (cparam's, below); `MAX_BOUNDS` packed-length
assertion (`share_data.py:350-357`) — the build's own gates cover it.

---

### 1.4 `train/methods/cparam.py`

**One sentence.** The argument-generating probe: the same packing as `cgen` with
a per-row prompt tail that names the tool and a target derived from `call` and
`tool`.

**venv.** `probe`.
**Imports (0.2).** `train/utils/trainer.py`, `models/probe_models/base.py`,
`data/training_data.py`, `eval/methods/cparam.py`, `data/environments/__init__.py`;
`[torch]`.

**Module-level names.**

```python
VERSION = 1
PROBE_KIND = "generator"
CHECKPOINT_META = {"call_sep": "\n[CALL] ", "param_only": True}
GEN_N = 200
ASSEMBLY_MISMATCH_LIMIT = 0.05      # legacy train_causal_param.py:90
```

`param_only: True` is exactly what 5.7 refuses an `inject.probe_gen` on (2.6),
which is why this method never serves a live run.

**The target, and the one derivation this file owns** (1.2, 1.3):

```python
prompt_tail = CHECKPOINT_META["call_sep"] + tool + "("   # legacy param:99-102
target      = call[len(tool) + 1:]                        # strip tool + "(", keep ")"
```
`target` is `None` when `call` does not start with `tool + "("`; such rows are
dropped whole and counted as `assembly_mismatch`, and the file raises when their
share exceeds `ASSEMBLY_MISMATCH_LIMIT` (legacy `train_causal_param.py:105-123`,
`share_data.py:341-349`). The derived string is what `predict` writes into
`prediction.target` (1.3), which is why the derivation lives here and not in the
trainer.

**Hooks.** As `cgen`, with three differences:
- `batches` uses `prompt_tail` (per row, it names that row's tool) instead of the
  bare separator, and the derived `target` instead of `call`.
- `validate` and `predict` build the **whole** prompt per row —
  `row.text + CHECKPOINT_META["call_sep"] + row.tool + "("` — and call
  `probe.generate(texts, max_new, call_sep="")`, because the pinned
  `Probe.generate(texts, max_new, call_sep)` appends one separator to every text
  and this method's tail is per row (erratum E10).
- `validate` calls `eval/methods/cparam.py`'s `match` on two **whole calls**:
  both the prediction and the target get `row.tool + "("` prepended, per 2.6's
  rule for `cparam`'s two callers. `objective = 1 - weighted params_all_ok`.

**Legacy source.** `train_causal_param.py:88-123` (constants, the tail and the
target), `125-197` (rows and the plain form), `214-250` (per-instance CE and val
CE), `252-277` (greedy generation and exact match); `share_data.py` as for cgen.
**Not ported:** the same list as cgen, plus `--readonly-env`.

---

## 2. Order of construction, and what must exist first

```
1. train/utils/trainer.py
2. train/methods/ctool.py          (needs 1)
3. train/methods/cgen.py           (needs 1)   \ built together, they are twins
4. train/methods/cparam.py         (needs 1)   /
5. tests/test_packed_loss.py       (needs 2, 3, 4)
```

From other folders, before `trainer.py` can be imported and run:

| file | names |
|---|---|
| `experimental_settings/schema.py` | `load_frozen(run_dir) -> Setting`, `run_dir_of(stage, key, *, debug)`, the `Setting` fields `_key`, `_commit`, `_debug`, `_upstream`, `_versions`, `models.probe`, `models.probe_row`, `probe.tuning`, `train.*` |
| `data/training_data.py` | `read(path) -> DataFrame`, `SCHEMA`, `VERSION` (E15) |
| `data/probe_output.py` | `write(path, df) -> None`, `SCHEMA`, `VERSION` (E15) |
| `jobs/registry.py` | `beat(run_dir, piece) -> Heartbeat`, `Heartbeat.emit`, `Heartbeat.finish`, `write_done(run_dir, *, stage, key, commit, counts, versions, metrics, report, pairs=None, stage_extra=None)` |
| `models/__init__.py` | `probe(alias) -> ProbeModel` (`weights`, `weights_path`, `family`) |
| `models/probe_models/base.py` | `load(row, cfg, *, probe_kind, n_labels=None, labels=None, ckpt_dir=None) -> Probe`, `Probe.save(dir, *, labels=None, extra=None, meta=None)`, `Probe.forward(batch) -> Outputs`, `Probe.generate(texts, max_new, call_sep)`, `Probe.score(texts)`, `Probe.tokenizer`, `Probe.max_len`, `Batch`, `Outputs`, and the three names errata E5 adds: `trainable_parameters()`, `set_training(flag)`, `grad_checkpointing(enabled)` |

Before the method files:

| file | names |
|---|---|
| `eval/methods/ctool.py` | `match(pred, target, None) -> bool`, `PROBE_KIND = "classifier"` |
| `eval/methods/cgen.py` | `match(pred, target, env) -> dict[str, bool]` with `tool_ok`, `params_all_ok`, `full_call_ok`, `PROBE_KIND = "generator"` |
| `eval/methods/cparam.py` | `match(pred, target, env)` over two whole calls, `PROBE_KIND = "generator"` |
| `data/environments/__init__.py` | `open_env(name) -> Environment` (cgen, cparam only) |

---

## 3. Acceptance, CPU (the implementer runs these from the repo root)

Interpreters: `python3` is system Python 3.10 (standard library only);
`external/probe-env/bin/python` is the probe venv. Every command below runs on
the login machine, uses no card and starts no GPU process. The tokenizer fixture
is read from `/net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-0.6B-Base`
(read-only) and every model is a two-layer 64-hidden Qwen3 built from that
directory's config, about 10M parameters on CPU.

### A3.1 The literal rules of 3.3 (any interpreter, no deps)

```bash
python3 - <<'PY'
import ast, pathlib, sys
files = ["train/utils/trainer.py", "train/methods/ctool.py",
         "train/methods/cgen.py", "train/methods/cparam.py"]
bad = []
for f in files:
    src = pathlib.Path(f).read_text()
    tree = ast.parse(src)
    def literals(name):
        return [n for n in tree.body
                if isinstance(n, ast.Assign) and len(n.targets) == 1
                and isinstance(n.targets[0], ast.Name) and n.targets[0].id == name
                and n.col_offset == 0]
    v = literals("VERSION")
    if len(v) != 1 or not isinstance(ast.literal_eval(v[0].value), int):
        bad.append((f, "VERSION"))
    if f.startswith("train/methods/"):
        k = literals("PROBE_KIND"); m = literals("CHECKPOINT_META")
        if len(k) != 1 or ast.literal_eval(k[0].value) not in ("classifier", "generator"):
            bad.append((f, "PROBE_KIND"))
        if len(m) != 1 or not isinstance(ast.literal_eval(m[0].value), dict):
            bad.append((f, "CHECKPOINT_META"))
        mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        mods |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        for forbidden in ("experimental_settings.schema", "jobs.registry"):
            if any(m0 == forbidden or m0.startswith(forbidden + ".") for m0 in mods):
                bad.append((f, forbidden))
        e = ast.parse(pathlib.Path("eval/methods/" + f.split("/")[-1]).read_text())
        ek = [n for n in e.body if isinstance(n, ast.Assign)
              and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "PROBE_KIND"
              and n.col_offset == 0]
        if len(ek) != 1 or ast.literal_eval(ek[0].value) != ast.literal_eval(k[0].value):
            bad.append((f, "PROBE_KIND disagrees with the eval side"))
print("FAIL", bad) if bad else print("OK")
sys.exit(1 if bad else 0)
PY
```
Expected: prints `OK`, exit 0.

### A3.2 Import (probe venv)

```bash
external/probe-env/bin/python -c "import train.utils.trainer as t, train.methods.ctool as c, train.methods.cgen as g, train.methods.cparam as p; print(t.VERSION, c.PROBE_KIND, g.PROBE_KIND, p.PROBE_KIND, p.CHECKPOINT_META['param_only'])"
```
Expected: prints `1 classifier generator generator True`, exit 0.

### A3.3 The packed loss equals the plain loss, per method (probe venv, CPU)

The script writes a tiny example frame with `data/training_data.py`'s **writer**,
reads it back with its reader, builds a stub `Probe` whose `forward` is the one
`models/probe_models/base.py` will have, and runs the method's own hooks. Run it
once with `M=ctool`, once with `M=cgen`, once with `M=cparam`.

```bash
for M in ctool cgen cparam; do
external/probe-env/bin/python - "$M" <<'PY'
import sys, importlib, torch, polars as pl, tempfile, pathlib, types
from transformers import AutoTokenizer, AutoConfig, AutoModel
name = sys.argv[1]
TOKDIR = "/net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-0.6B-Base"
tok = AutoTokenizer.from_pretrained(TOKDIR)
cfgm = AutoConfig.from_pretrained(TOKDIR)
cfgm.hidden_size, cfgm.intermediate_size = 64, 128
cfgm.num_hidden_layers, cfgm.num_attention_heads, cfgm.num_key_value_heads = 2, 4, 2
cfgm.head_dim = 16
backbone = AutoModel.from_config(cfgm, dtype=torch.float32).eval()
head = torch.nn.Linear(64, 3)
lm = torch.nn.Linear(64, cfgm.vocab_size, bias=False)

from data import training_data
rows = []
for ev in range(2):                       # two events, three cuts each
    base = "The task is to pay a bill. I will look at the phone app. "
    for c in range(3):
        text = base + "Thinking step " * (c + 1)
        rows.append(dict(
            example_id=f"t{ev}__s42|s0|c{c}", event_id=f"t{ev}__s42|s0",
            record_id=f"t{ev}__s42", task_id=f"t{ev}", seed=42, step=0,
            cut=len(text), cut_index=c, n_cuts=3, depth=0.3 * (c + 1),
            text=text, tool="phone.pay" if ev else "phone.login",
            call=("phone.pay(id=1)" if ev else "phone.login(user='a')"),
            args=[{"key": "id", "value": "1"}] if ev else [{"key": "user", "value": "a"}],
            weight=1.0, split="train", env="appworld", agent_model="gptoss120b"))
d = pathlib.Path(tempfile.mkdtemp())
training_data.write(d / "examples.parquet", pl.DataFrame(rows))
df = training_data.read(d / "examples.parquet")

class Outputs:
    def __init__(self, logits, hidden): self.logits, self.hidden = logits, hidden
class Probe:
    tokenizer, max_len = tok, 512
    def forward(self, batch):
        out = backbone(input_ids=batch["input_ids"],
                       attention_mask=batch["attention_mask"],
                       position_ids=batch.get("position_ids"), use_cache=False)
        h = out.last_hidden_state
        ee = batch["event_end"]
        hp = h[ee[:, 0], ee[:, 1]].float()
        return Outputs((head if name == "ctool" else lm)(hp), h)
    def set_training(self, flag): pass
probe = Probe()

cfg = types.SimpleNamespace(
    train=types.SimpleNamespace(seed=42, max_len=512, events_per_mb=2, accum=1,
                                predict=types.SimpleNamespace(splits=["train"], cap=None, max_new=8)),
    probe=types.SimpleNamespace(method=name), data=types.SimpleNamespace(env="appworld"))
m = importlib.import_module(f"train.methods.{name}")
if name == "ctool":
    labels = m.head_labels(df, cfg)
    assert labels == sorted(df["tool"].unique().to_list()), labels
with torch.no_grad():
    packed = sum(float(m.loss(probe, b)) for b in m.batches(df, tok, cfg))
    plain = float(m.reference_loss(probe, df))
n = len(df)
print(f"{name} packed={packed/n:.8f} plain={plain/n:.8f} diff={abs(packed-plain)/n:.3e}")
assert abs(packed - plain) / n < 1e-4, "alignment gate would fail"
print("OK")
PY
done
```
Expected: three lines `ctool packed=... plain=... diff=...` each followed by
`OK`, every `diff` below `1e-4`, exit 0 each time. A non-zero exit or a `diff`
above the tolerance is the packing bug the gate exists for.

### A3.4 The whole loop, on CPU, with two stubs (probe venv)

`trainer.run` is exercised end to end: only `schema.load_frozen` and `base.load`
are replaced, everything else — `data/training_data.py`, `data/probe_output.py`,
`jobs/registry.py`, the method's hooks, the checkpoint calls — is the real code.

```bash
external/probe-env/bin/python - <<'PY'
import json, pathlib, tempfile, types, importlib, torch, polars as pl
from transformers import AutoTokenizer, AutoConfig, AutoModel
import train.utils.trainer as trainer
from data import training_data, probe_output

TOKDIR = "/net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-0.6B-Base"
tok = AutoTokenizer.from_pretrained(TOKDIR)
c = AutoConfig.from_pretrained(TOKDIR)
c.hidden_size, c.intermediate_size = 64, 128
c.num_hidden_layers, c.num_attention_heads, c.num_key_value_heads = 2, 4, 2
c.head_dim = 16
backbone = AutoModel.from_config(c, dtype=torch.float32)
head = torch.nn.Linear(64, 2)

root = pathlib.Path(tempfile.mkdtemp())
build_dir, run_dir = root / "build" / "b0", root / "train" / "t0"
build_dir.mkdir(parents=True); run_dir.mkdir(parents=True)
rows = []
for ev in range(4):                                   # 4 events x 3 cuts x 3 splits
    for split in ("train", "val", "test"):
        for cut in range(3):
            text = "Pay the bill. " + "thinking " * (cut + 1)
            rows.append(dict(
                example_id=f"{split}{ev}__s42|s0|c{cut}", event_id=f"{split}{ev}__s42|s0",
                record_id=f"{split}{ev}__s42", task_id=f"{split}{ev}", seed=42, step=0,
                cut=len(text), cut_index=cut, n_cuts=3, depth=0.3 * (cut + 1), text=text,
                tool="phone.pay" if ev % 2 else "phone.login",
                call=("phone.pay(id=1)" if ev % 2 else "phone.login(user='a')"),
                args=[{"key": "id", "value": "1"}], weight=1.0, split=split,
                env="appworld", agent_model="gptoss120b"))
training_data.write(build_dir / "examples.parquet", pl.DataFrame(rows))

cfg = types.SimpleNamespace(
    _key="t0", _commit="deadbee", _debug=True, _upstream={"build": "b0"},
    _versions={"train/utils/trainer.py": 1}, _stage="train",
    data=types.SimpleNamespace(env="appworld"),
    models=types.SimpleNamespace(probe="qwen06", probe_row={"role": "probe", "family": "qwen"}),
    probe=types.SimpleNamespace(method="ctool", tuning="full"),
    train=types.SimpleNamespace(
        lr=1e-4, epochs=1, warmup_ratio=0.0, seed=42, max_len=256, events_per_mb=2,
        accum=1, grad_ckpt=False, max_steps=None, align_check=True, checkpoint_hours=2.0,
        predict=types.SimpleNamespace(splits=["val", "test"], cap=None, max_new=8)))

class Outputs:
    def __init__(self, logits, hidden): self.logits, self.hidden = logits, hidden
class Probe:
    tokenizer, max_len = tok, 256
    def forward(self, b):
        h = backbone(input_ids=b["input_ids"], attention_mask=b["attention_mask"],
                     position_ids=b.get("position_ids"), use_cache=False).last_hidden_state
        ee = b["event_end"]
        return Outputs(head(h[ee[:, 0], ee[:, 1]].float()), h)
    def score(self, texts): raise AssertionError("ctool.predict must use the packed path")
    def generate(self, texts, max_new, call_sep): return ["phone.pay(id=1)"] * len(texts)
    def trainable_parameters(self): return list(backbone.parameters()) + list(head.parameters())
    def set_training(self, flag): backbone.train(flag); head.train(flag)
    def grad_checkpointing(self, on): pass
    def save(self, d, *, labels=None, extra=None, meta=None):
        d = pathlib.Path(d); d.mkdir(parents=True, exist_ok=True)
        (d / "meta.json").write_text(json.dumps({"labels": labels, **(extra or {}), **(meta or {})}))
        torch.save(head.state_dict(), d / "head.pt")

trainer.schema.load_frozen = lambda rd: cfg
trainer.schema.run_dir_of = lambda stage, key, *, debug: build_dir
trainer.base.load = lambda *a, **k: Probe()
trainer.models.probe = lambda alias: types.SimpleNamespace(
    alias=alias, weights=alias, weights_path=TOKDIR, family="qwen", role="probe", serving={})

trainer.run(run_dir, importlib.import_module("train.methods.ctool"))
p = probe_output.read(run_dir / "predictions.parquet")
print(sorted(p.columns))
print(sorted(p["split"].unique().to_list()), p.height)
print(json.loads((run_dir / "done.json").read_text())["stage_extra"]["labels"])
print(json.loads((run_dir / "align_check.json").read_text())["PASS"])
print((run_dir / "best" / "meta.json").exists(), (run_dir / "train_done.json").exists())
print(json.loads(sorted((run_dir / "heartbeat").iterdir())[0].read_text().splitlines()[-1])["status"])
PY
```
Expected, in order: the column list is exactly
`['depth', 'event_id', 'example_id', 'gen_tokens', 'label_pred', 'logits',
'method', 'score', 'split', 'target', 'task_id', 'text_pred', 'tool',
'version']`; the second line is `['test', 'val'] 24` (the val and test rows of
the fixture); the labels line is `['phone.login', 'phone.pay']`; the
`align_check.json` line is `True`; the next line is `True True`; the last line
is `done`; exit 0. The stub's `score` raises on purpose: a `predict` that calls
it instead of the packed path fails here (E13).

### A3.5 The 2.4 continue rule (probe venv, CPU, after A3.4)

Append to the A3.4 script, after its last `print`:

```python
import shutil, subprocess, sys
ctool = importlib.import_module("train.methods.ctool")
log_before = (run_dir / "train_log.jsonl").read_text()
pred_before = (run_dir / "predictions.parquet").stat().st_mtime_ns

trainer.run(run_dir, ctool)                                   # (a) done.json present
print("a", (run_dir / "predictions.parquet").stat().st_mtime_ns == pred_before,
      (run_dir / "train_log.jsonl").read_text() == log_before)

(run_dir / "done.json").unlink(); (run_dir / "predictions.parquet").unlink()
trainer.run(run_dir, ctool)                                   # (b) predict only
print("b", probe_output.read(run_dir / "predictions.parquet").height,
      (run_dir / "train_log.jsonl").read_text() == log_before)

(run_dir / "done.json").unlink(); (run_dir / "train_done.json").unlink()
(run_dir / "predictions.parquet").unlink()
try:
    trainer.run(run_dir, ctool)                               # (c) refuse
    print("c FAIL: no refusal")
except SystemExit as e:
    print("c", "train_log.jsonl" in str(e), "retry" in str(e))
```
Expected: `a True True` (nothing was rewritten), `b 24 True` (the predictions
came back with the same row count and no optimizer step was logged), and
`c True True` (the refusal names `train_log.jsonl` and `run.py retry`).

### A3.6 The permanent packed-loss test

```bash
external/probe-env/bin/python -m unittest tests.test_packed_loss -v
```
Expected: three tests (`ctool`, `cgen`, `cparam`), `OK`, exit 0. The file's
header names its venv (`probe`), per the tree's `tests/` line. `pytest` is not
installed on this machine; the file is a `unittest.TestCase`.

### A3.7 The `selfcheck` lines that cover these files

```bash
python3 run.py selfcheck
```
Expected: exit 0, and in particular no finding for (i) the four files' README
annotation lines against their real imports (0.1); (ii) a `VERSION` line missing
or duplicated in any of the four; (iii) the `probe.method` axis against the
intersection of the file names under `train/methods/` and `eval/methods/` (5.3);
(iv) `PROBE_KIND` declared in both method files and disagreeing (2.6). Until
`run.py` exists, A3.1 stands in for (ii), (iv) and part of (iii).

---

## 4. Acceptance, GPU or cross-host (main session only, never an implementer)

All six commands go through the gpu-run skill; every one of them starts a GPU
process, which is why they are not in section 3.

1. **A debug train of each method.**
   `python3 run.py run train_probe <a ctool setting> --debug`, then the same for
   a cgen and a cparam setting. Must show: `align_check.json` with
   `"PASS": true` and `diff` below `1e-4`; `train_log.jsonl` holding `start`,
   at least one `step`, one `eval` and one `save_best` line;
   `best/meta.json` carrying `backbone`, `tuning`, `labels` (ctool only),
   `call_sep`, `param_only`, `max_len`, `train_key`; `predictions.parquet` whose
   `split` column holds exactly `val` and `test` and whose row count equals the
   example rows of those two splits (or `train.predict.cap` per split);
   `done.json` with `metrics.objective` and `stage_extra.labels`;
   `heartbeat/0-0.jsonl` ending in `"status": "done"`.
2. **The alignment gate actually fires.** Launch one debug train with
   `train.align_check: true` on a deliberately broken packing (a one-token shift
   in `event_end`) and confirm the process exits non-zero before the first
   optimizer step and writes `align_check.json` with `"PASS": false`.
3. **Resume.** Kill a debug train after `last/` has been written, relaunch the
   same setting: the new process must print that it resumed from
   `last/meta.json["step"]`, must not rewrite `train_log.jsonl` from the top,
   and must reach the same `done.json` counts as an uninterrupted run.
4. **The predict-only continue path.** Delete `predictions.parquet` and
   `done.json` from a finished debug train run, relaunch: the run must load
   `best/`, take no optimizer step (no new `step` line), and rewrite
   `predictions.parquet` with the same row count.
5. **LoRA.** One debug train with `probe.tuning: lora`: `best/` must hold merged
   full weights (`safetensors` of the backbone's own size, no `adapter_*`
   file), and its `meta.json` `tuning` must read `lora`.
6. **Two methods over one build.** Train ctool and cgen against the same build
   key and confirm the two train directories differ, that both
   `consumed.json` files name the same `examples.parquet` with the same sha1,
   and that `eval` of the cgen run accepts the ctool run's eval as its
   `theta_from` (the shared-build gate of 2.5 passes).

---

## 5. Tickets

### T1 — The shared training loop (`train/utils/trainer.py`)

**Files.** `train/utils/trainer.py` (new).
**What to do.** Section 1.1, in full: the twelve-step `run`, the 2.4 continue
table, the alignment gate of 2.5/2.6, the step loop and the normalisation of E1
and E4, the checkpoint calls of 1.6, the prediction step and the column join of
1.3, `consumed.json`, `done.json` through `registry.write_done`, the heartbeat
of 8.4. `run` never branches on a method name; it reads exactly two
method-supplied `Batch` keys, `mb` and `mb_weight`. It appends no registry row.
**Acceptance.** A3.1 (the `VERSION` part), A3.2 (the trainer import), A3.4, A3.5.
**Needs from other folders.** `experimental_settings/schema.py`
(`load_frozen`, `run_dir_of`); `data/training_data.py` (`read`, `SCHEMA`);
`data/probe_output.py` (`write`, `SCHEMA`); `jobs/registry.py` (`beat`,
`Heartbeat.emit`, `Heartbeat.finish`, `write_done`); `models/__init__.py`
(`probe`); `models/probe_models/base.py` (`load`, `Probe.save`, `Probe.forward`,
`Probe.tokenizer`, `Probe.max_len`, `Probe.trainable_parameters`,
`Probe.set_training`, `Probe.grad_checkpointing`, `Batch`, `Outputs`).

### T2 — The classification probe (`train/methods/ctool.py`)

**Files.** `train/methods/ctool.py` (new).
**What to do.** Section 1.2: the three column-zero literals, `head_labels`, the
prefix-shared packing and its block-diagonal mask, `loss`, `reference_loss`,
`validate` through `eval/methods/ctool.py`'s `match`, `predict` through the
packed path (E13), `main` and the `--run-dir` block.
**Acceptance.** A3.1, A3.2, A3.3 with `M=ctool`, A3.4.
**Needs from other folders.** `eval/methods/ctool.py` (`match`, `PROBE_KIND`);
`data/training_data.py` (`SCHEMA`, the column names); `models/probe_models/base.py`
(`Batch`, `Outputs`, `Probe.forward`); and T1.

### T3 — The two generating probes (`train/methods/cgen.py`, `train/methods/cparam.py`)

**Files.** `train/methods/cgen.py`, `train/methods/cparam.py` (both new).
**What to do.** Sections 1.3 and 1.4. The two files are written separately and
**do not import each other** (the tree's `methods/` line); the shared shape is
repeated on purpose, which is what the alignment gate catches per method. cgen's
target is the `call` column and its tail is the bare separator; cparam's target
is derived from `call` and `tool` in this file (1.2) and its tail names the tool,
so its `validate` and `predict` build the whole prompt and pass
`call_sep=""` (E10). Both carry `param_only` in `CHECKPOINT_META` with the
values 5.7 reads.
**Acceptance.** A3.1, A3.2, A3.3 with `M=cgen` and `M=cparam`.
**Needs from other folders.** `eval/methods/cgen.py` and `eval/methods/cparam.py`
(`match`, `PROBE_KIND`); `data/environments/__init__.py` (`open_env`);
`data/training_data.py`; `models/probe_models/base.py` (`Probe.generate`,
`Probe.forward`, `Batch`, `Outputs`); and T1.

### T4 — The permanent packed-loss check (`tests/test_packed_loss.py`)

**Files.** `tests/test_packed_loss.py` (new; one of the four checks the tree's
`tests/` line names — "the packed loss equals a row-by-row loss kept in its
plainest form ... on a tiny CPU model").
**What to do.** Turn A3.3 into a `unittest.TestCase` with one test per method,
building the tiny two-layer model from the Qwen3-0.6B-Base config and the
fixture frame through `data/training_data.py`'s writer. The header line names the venv
(`probe`). The tolerance is 2.5's `1e-4` on the per-example-row difference.
**Acceptance.** A3.6.
**Needs from other folders.** `data/training_data.py`; and T2, T3.

---

## 6. Contract errata settled here

Each line is also appended to `.scratch/from-zero/contract-errata.md`.

- **E1 — 2.6, `loss` and `reference_loss`.** The gate is stated as "sums `loss`
  over the batches it yields ... both normalised per example row", but nothing
  says what one `loss` call returns; a per-batch mean is not additive.
  The build makes both hooks return the **unnormalised weighted sum** over their
  rows, and `trainer.run` divides.
- **E2 — 6.2, `Batch["event_end"]`.** Stated as one position per event; a
  classifier decides at every cut and a generator at every target token.
  `event_end` is an `int64` tensor of shape `[n_positions, 2]` holding
  `(sequence index, token position)` pairs — every position the head is applied
  at — and `Outputs.logits` has one row per entry in that order.
- **E3 — 6.2, `Outputs.logits` for a generator.** "The LM head's" over every
  position is never computed (it is the memory blow-up
  `legacy/pipeline/train/train_causal_share.py:140-175` exists to avoid); the LM
  head is applied at `event_end` only.
- **E4 — 6.2, `Batch`.** Two further keys are required and are read by
  `train/utils/trainer.py`, never by `base.py`: `mb` (int, the logical
  minibatch this physical block belongs to; blocks of one minibatch are yielded
  consecutively) and `mb_weight` (float, that minibatch's total row weight), so
  the trainer reproduces legacy's `W` / `n_g` normalisation without reading a
  method-specific key.
- **E5 — 6.2, the probe object.** `base.load` reads no `cfg.train.grad_ckpt` and
  the `Probe` table offers no handle on the module, while every `probe.tuning`
  branch must stay in `base.py`. Three names are added:
  `Probe.trainable_parameters()`, `Probe.set_training(flag)`,
  `Probe.grad_checkpointing(enabled)` (the last also does peft's
  `enable_input_require_grads`, `legacy/pipeline/train/lora_util.py:122-139`).
- **E6 — 1.6, `last/`.** The optimizer and scheduler state have no home;
  `trainer.run` writes `<run_dir>/last/optimizer.pt` itself beside what
  `Probe.save` writes. `rng_state` in `last/meta.json` is
  `{"torch": <hex>, "cuda": <hex|null>}`; the epoch's event order is recomputed
  from `random.Random(cfg.train.seed + epoch)` and is not stored.
- **E7 — 2.6, validation cadence.** Nothing says how often `validate` runs and
  5.2 has no field for it. Validation runs at the end of every epoch, and once
  more at the end of training when `train.max_steps` cut the last epoch short;
  `best/` is chosen over those points. (Legacy's `--eval-per-epoch 4` has no
  schema field; adding `train.evals_per_epoch` with a default of 1 would be free
  under 3.3 and is the owner's call.)
- **E8 — 2.6, a generator's `validate`.** The generation budget and the number of
  rows have no source. `max_new` is `cfg.train.predict.max_new`; the rows are a
  deterministic subsample of the val frame of size `GEN_N = 200`, a module-level
  constant of each generator method file covered by that file's `VERSION`
  (legacy `train_causal_share.py:272-295`).
- **E9 — 1.3, `gen_tokens`.** `Probe.generate` returns strings only, so the
  column has no producer; the method computes it as
  `len(tok(text_pred, add_special_tokens=False)["input_ids"])`.
- **E10 — 2.6/1.6, cparam's separator.** `Probe.generate(texts, max_new,
  call_sep)` appends one separator to every text, while cparam's tail is per row
  (`call_sep + tool + "("`, `legacy/pipeline/train/train_causal_param.py:99-102`).
  `train/methods/cparam.py` builds the whole prompt per row and passes
  `call_sep=""`; its `CHECKPOINT_META["call_sep"]` stays `"\n[CALL] "` and
  `param_only` stays `true`.
- **E11 — 0.2, `train/utils/trainer.py`.** Its third-party list is `[torch]`,
  not `[torch, peft]`: LoRA lives in `models/probe_models/base.py` (whose own
  line carries peft) and the LR schedule is a
  `torch.optim.lr_scheduler.LambdaLR`.
- **E12 — 5.2, the physical block budget.** No setting field gives one. Each
  method file uses `2 * cfg.train.max_len` for training and twice that for
  validation (legacy's 16384 / 32768 at `max_len` 8192); the split changes no
  number (`train_causal_share.py:199-241`).
- **E13 — 6.2, `Probe.score` and `predict`.** 6.2 says `predict` writes what
  `Probe.score` returns; `score` is one sequence per text, and a prediction pass
  over val and test costs `build.max_cuts` times the packed pass.
  `train/methods/ctool.py`'s `predict` computes the class logits through its own
  packed batches and `Probe.forward` — the path the alignment gate covers —
  while `Probe.score` stays the served form.
- **E14 — 5.2, `train.max_len`.** "Tokens per event; a longer event is dropped
  whole" is applied in each method's `batches`, over the longest text of the
  event; the dropped rows get no prediction row either, and the count is
  `done.json`'s `counts.dropped_overlong`.
- **E15 — 1.2/1.3, the reader and writer names.** Neither section names the
  functions `data/training_data.py` and `data/probe_output.py` offer. The build calls
  `training_data.read(path) -> DataFrame`, `training_data.write(path, df) -> None`,
  `probe_output.read`, `probe_output.write`, and the module-level `SCHEMA` dict each
  format file already passes to `read_frame` (Part 1).
