# 13 the training loop and the three probe methods

Status: claimed
Blocked by: 02, 03, 04, 05, 06, 08, 10
Spec: .scratch/from-zero/spec.md (sections 2, 3, 4, 5, 6, 7)

## What to do

Five files, all `venv: probe`. Contracts 2.6 ("The method hook" table and "Who
owns what"), 2.4 (the continue rule), 2.5 (the alignment gate), 1.3 (the
prediction row), 1.6 (the checkpoint layout), 6.2 (the probe object) and 8.4 (the
heartbeat) are the specification; read 2.6 and 1.6 in full.

```
train/utils/trainer.py       imports: experimental_settings/schema.py, models/__init__.py,
                             models/probe_models/base.py, data/training_data.py,
                             data/probe_output.py, jobs/registry.py; [torch]
                             used by: train/methods/{ctool,cgen,cparam}.py   VERSION = 1
train/methods/ctool.py       imports: train/utils/trainer.py, models/probe_models/base.py,
                             data/training_data.py, eval/utils/probe_eval.py; [torch]  VERSION = 1
train/methods/cgen.py        + data/environments/__init__.py (open_env)       VERSION = 1
train/methods/cparam.py      + data/environments/__init__.py (open_env)       VERSION = 1
tests/test_packed_loss.py    venv probe (the header line names it)
README.md                    your four code lines only (see the merge note below)
```

**Decision already made (errata):** `trainer.py`'s third-party list is `[torch]`,
not `[torch, peft]` — LoRA lives in `models/probe_models/base.py` and the LR
schedule is a `torch.optim.lr_scheduler.LambdaLR`.

**No method file imports `schema.py` or `registry.py`** (2.6). **The three method
files do not import each other**; the shared shape is repeated on purpose, which
is what the alignment gate catches per method.

Build order: `trainer.py` -> `ctool.py` -> `cgen.py` and `cparam.py` ->
`tests/test_packed_loss.py`.

**The import aliases are part of the contract**, because the acceptance replaces
two of them: `trainer.py` writes `from experimental_settings import schema`,
`import models`, `from models.probe_models import base`,
`from data import training_data, probe_output`, `from jobs import registry` — so
`trainer.schema`, `trainer.base`, `trainer.models`, `trainer.example`,
`trainer.prediction` and `trainer.registry` all name the modules.

**One note about `README.md`, for the wave-5 merge.** Add your four annotation
blocks as every ticket does. Ticket 14 runs beside you in the same wave and
rewrites `README.md` whole from contracts 0.2 and 0.4, so it already carries all
34 entries, your four included. At the merge the main session takes **ticket
14's file wholesale and discards your four blocks** (the construction plan,
section 1) — keeping both would ship four duplicate entries that nothing would
catch, because `readme_entries` returns a dict and the count stays 34. Write your
four blocks exactly as contracts 0.2 spells them, so the diff against ticket 14's
copy is empty and the discard is provably safe.

### 1. `train/utils/trainer.py`

```python
VERSION = 1
def run(run_dir: Path, method) -> None      # 2.6, the only public entry point
```

Everything else is private (`_`-prefixed). `run` **never branches on the method
name** and reads exactly two method-supplied `Batch` keys, `mb` and `mb_weight`.

**What `run` does, in order.**

1. `cfg = schema.load_frozen(run_dir)`. Nothing else resolves a setting.
2. `hb = registry.beat(run_dir, 0)` (a one-process stage is piece 0).
3. **The continue rule of 2.4**, computed from what is on disk, in this order:

   | state | action |
   |---|---|
   | `done.json` present | return at once, run nothing |
   | `train_done.json` present and `predictions.parquet` absent | go to step 11 with `ckpt_dir = run_dir/"best"` |
   | `last/` present and `last/meta.json["commit"] == cfg._commit` | resume from `last/meta.json["step"]` |
   | `last/` present and its `commit` differs | `raise SystemExit`, printing both commits and `run.py retry` |
   | `train_log.jsonl` present and none of the above | `raise SystemExit`, naming `train_log.jsonl` **and `run.py retry`** as the way out (`legacy/pipeline/train/train_causal_share.py:1017-1020`) |
   | none of the above | start fresh |

4. `torch.manual_seed(cfg.train.seed)`; `torch.backends.cuda.matmul.allow_tf32 =
   False` while the alignment gate runs.
5. `build_dir = schema.run_dir_of("build", cfg._upstream["build"], debug=cfg._debug)`;
   `df = training_data.read(build_dir / "examples.parquet")`. Write `consumed.json` =
   `[{path, sha1, n_rows}]` for that one file.
6. `labels = method.head_labels(df, cfg)` on the **whole** frame, **before**
   `base.load`. On a resume or on the predict-only path the list is read back
   from `ckpt_dir/meta.json` and the hook is not called.
7. `probe = base.load(cfg.models.probe_row, cfg, probe_kind=method.PROBE_KIND,
   n_labels=(len(labels) if labels else None), labels=labels,
   ckpt_dir=<None | run_dir/"last" | run_dir/"best">)`. `weights_path` for the
   start log line comes from `models.probe(cfg.models.probe)`.
   `probe.grad_checkpointing(True)` when `cfg.train.grad_ckpt`.
8. **The alignment gate**, when `cfg.train.align_check` and the run is not
   resuming (2.5, 2.6): take the first
   `cfg.train.events_per_mb * cfg.train.accum` rows of the `train` split in
   `example_id` order; `packed = sum(method.loss(probe, b) for b in
   method.batches(slice_df, probe.tokenizer, cfg))`;
   `plain = method.reference_loss(probe, slice_df)`; **both divided by
   `len(slice_df)`**; stop when `abs(packed - plain) > 1e-4`. Both sides run
   under `torch.no_grad()` with `probe.set_training(False)`, restored afterwards.
   Write `align_check.json` = `{"PASS": bool, "packed": float, "plain": float,
   "diff": float, "tol": 1e-4, "n_rows": int, "method": <module name>}` either
   way, and exit non-zero on a failure.
9. **The step loop.**
   `steps = ceil(ceil(n_train_events / events_per_mb) / accum) * epochs`, capped
   by `cfg.train.max_steps` when set; `hb.emit(0, steps, "step")` before the
   first step (8.4: the signal that the model finished loading). Optimizer
   `torch.optim.AdamW(probe.trainable_parameters(), lr=cfg.train.lr,
   weight_decay=0.01)`; a `LambdaLR` rising linearly over
   `int(steps * cfg.train.warmup_ratio)` steps and decaying linearly to zero (the
   shape of `transformers.get_linear_schedule_with_warmup`, which legacy calls at
   `train_causal_share.py:1100`); gradient clip 1.0. Per logical minibatch,
   `method.batches` yields one `Batch` per physical block, consecutive blocks of
   one logical minibatch carrying the same `mb`; for each block
   `(method.loss(probe, batch) / batch["mb_weight"] / cfg.train.accum).backward()`
   (`train_causal_share.py:199-241`), then `clip_grad_norm_`, `opt.step()`,
   `sch.step()`, `opt.zero_grad()` after `accum` distinct `mb` values or at the
   end of the epoch. A `step` line into `train_log.jsonl` and
   `hb.emit(gstep, steps, "step", loss=...)` every `LOG_EVERY = 50` steps (a
   module constant; it changes no number).
10. **Validation and checkpoints.** `method.validate(probe, val_df,
    probe.tokenizer, cfg)` **at the end of every epoch, and once more at the end
    of training when `train.max_steps` cut the last epoch short** (errata: 2.6
    says nothing about cadence and 5.2 has no field). `best/` is written when the
    returned `objective` is lower than every earlier one (2.6: lower is better),
    through `probe.save(run_dir/"best", labels=labels,
    extra=method.CHECKPOINT_META, meta={"backbone": cfg.models.probe,
    "tuning": cfg.probe.tuning, "max_len": cfg.train.max_len,
    "train_key": cfg._key})`. `last/` is rewritten every
    `cfg.train.checkpoint_hours` with the same call plus
    `{"step": gstep, "epoch": ep, "commit": cfg._commit, "rng_state": {...}}` in
    `meta`, and **`torch.save({"opt": ..., "sch": ...}, run_dir/"last"/"optimizer.pt")`
    beside it** (errata: 1.6 gives the optimizer state no home; `rng_state` is
    `{"torch": hex, "cuda": hex|null}` and the epoch's event order is recomputed
    from `random.Random(cfg.train.seed + epoch)`, not stored). `hb.emit` is called
    during a long validation so the stall line is not crossed
    (`train_causal_share.py:243-270`).
11. After the last step: write `train_done.json` = `{"key": cfg._key,
    "commit": cfg._commit, "steps": gstep, "best_objective": float,
    "finished_at": <clock_gettime REALTIME>}`, then **reload `best/`** into the
    probe (`base.load(..., ckpt_dir=run_dir/"best")`) so the normal path and
    2.4's predict-only path run the same code.
12. **The prediction step** (1.3). For each split named by
    `cfg.train.predict.splits`, take that split's rows in `example_id` order,
    capped at `cfg.train.predict.cap` when set, and call
    `method.predict(probe, df, probe.tokenizer, cfg)`. Join the five
    method-independent columns `event_id`, `task_id`, `depth`, `split`, `tool`
    from the example frame on `example_id`, and write with
    `probe_output.write(run_dir / "predictions.parquet", frame)`, which stamps
    `version`. **The trainer writes neither `target` nor `method` nor
    `version`.**
13. `registry.write_done(run_dir, stage="train", key=cfg._key,
    commit=cfg._commit, counts={train_rows, val_rows, predictions,
    dropped_overlong}, versions=cfg._versions,
    metrics={"objective": best, **the validation extras}, report=None,
    stage_extra={"labels": labels})`, then `hb.finish()`. **No registry row is
    appended here** (2.6).

Legacy sources: `train_causal_share.py:1164-1281` (the update loop), `:199-241`
(per-block backward and the `W`/`n_g` normalisation), `:243-270` (the heartbeat
during a long validation), `:1095-1137` (the optimizer, the schedule, the log),
`:1017-1020` (the refusal on an existing log);
`train_causal_tool.py:509-536` and `train_causal_share.py:1253-1278` (the `best/`
save); `lora_util.py:122-150` (which moves into `base.py`).

**Not ported:** the GPU-memory probe (`train_causal_share.py:296-601`,
`share_data.py:535-580`); the read-only-tool arm; `--smoke` and `--max-events`;
`--force`; `--align-only`; the hidden-state incremental alignment check
(`train_causal_tool.py:228-290`) and the reference-path machinery of
`train_causal_share.py:603-925`; `RefBaselineDriftError` and the six `--align-*`
tolerances (2.5 pins one, `1e-4`); the `--fire-head` experiment
(`train_causal_callgen.py:110-135`); `--lr` resolution (`lora_util.py:45-73`);
MLflow.

**Behaviour change worth stating in the module docstring:**
`train.warmup_ratio` defaults to `0.0` while legacy hardcoded
`int(steps * 0.05)`. A setting that wants the old schedule writes
`warmup_ratio: 0.05`.

### 2. `train/methods/ctool.py`

```python
VERSION = 1
PROBE_KIND = "classifier"
CHECKPOINT_META = {"call_sep": None, "param_only": False}

def head_labels(df, cfg) -> list[str] | None
def batches(df, tok, cfg)            # -> Iterator[Batch]
def loss(probe, batch)               # -> Tensor
def validate(probe, df, tok, cfg)    # -> dict[str, float]
def predict(probe, df, tok, cfg)     # -> Iterator[dict]
def reference_loss(probe, df)        # -> Tensor
def main(run_dir) -> None            # one line: trainer.run(run_dir, sys.modules[__name__])
```
plus `if __name__ == "__main__":` parsing `--run-dir` only.

- `head_labels`: the unique values of the `tool` column of the **whole** frame,
  sorted ascending by name (2.6, 1.3). Never computed over the training split.
- `batches`: group the rows by `event_id`; the row texts of one event are nested
  prefixes (2.5 gates it), so tokenize the longest text as the event's `full_ids`
  and each row's own text as `row_ids`, take `p = lcp(row_ids, full_ids)` and
  pack `full_ids[:p_max]` once followed by every row's divergent tail
  `row_ids[p:]` (`share_data.py:55-62, 362-393`). The decision position of a row
  is the last token of its own tail, or `p - 1` inside the shared prefix when the
  tail is empty; those positions are `Batch["event_end"]`, the `[n_positions, 2]`
  `(sequence, position)` tensor of 6.2. The attention mask is the block-diagonal
  additive mask of `share_data.py:396-480` (prefix causal, each tail sees the
  first `p` prefix positions and its own tokens, tails do not see each other), so
  every row's hidden state equals the one an independent forward of `row_ids`
  would give. **Drop every row of an event whose longest text exceeds
  `cfg.train.max_len` tokens** (errata: 5.2's "a longer event is dropped whole"
  is applied here, over the longest text of the event; those rows get no
  prediction row and the count is `done.json`'s `counts.dropped_overlong`). Split
  events into logical minibatches of `cfg.train.events_per_mb` after
  `random.Random(cfg.train.seed + epoch).shuffle` (`share_data.py:482-497`) and
  each logical minibatch into physical blocks by **`2 * cfg.train.max_len`
  tokens** (errata: no setting field gives a physical block budget; this matches
  legacy's 16384 at `max_len` 8192, and twice that for validation).
  Batch keys: `input_ids`, `attention_mask` (the 4-D additive mask),
  `position_ids`, `event_end`, `mb`, `mb_weight`, and the method's own `target`,
  `weight`, `example_id`.
- **`Batch["target"]` holds the class *name* per decision row, not an index**
  (errata). 2.6 pins `batches(df, tok, cfg)`, and neither the frame it is handed
  (a split, or the alignment gate's first `events_per_mb * accum` rows) nor `cfg`
  carries the class order — recomputing `sorted(unique(tool))` there gives a
  different order from `head_labels` over the whole frame, which is the silent
  mislabelling 1.3 exists to prevent. The one place the order is reachable is
  `probe.labels`, which `trainer.run` passed into `base.load`. So `batches` emits
  the name and **`loss` and `reference_loss` map it**:
  `y = torch.tensor([probe.labels.index(t) for t in batch["target"]])`.
  **`validate` and `predict` read the class order off `probe.labels` for the same
  reason** — `label_pred` is `probe.labels[argmax]` and `logits` are written in
  `probe.labels` order.
- `loss`: `out = probe.forward(batch)`;
  `ce = F.cross_entropy(out.logits.float(), y, reduction="none")` with `y` the
  indices above; return `(ce * batch["weight"]).sum()` — **the unnormalised
  weighted sum** (errata: 2.6's gate sums `loss` over batches, and a per-batch
  mean is not additive; `trainer.run` divides).
- `reference_loss`: the same number computed **one example row per sequence, in
  its plainest form** — tokenize each row's text alone, right-pad, and go through
  `probe.forward` (the only place a method touches the model) with a batch whose
  `attention_mask` is the plain 2-D 0/1 mask, no `position_ids`, and whose
  `event_end` names each sequence's last real token; weighted CE, weighted sum,
  with the target index taken through `probe.labels` exactly as `loss` does.
  **This is the one piece of code written twice on purpose** (2.6).
- `validate`: score the frame it is handed through the same packed path, compare
  with `eval/utils/probe_eval.py`'s `match_ctool(pred_label, target_tool, None)` (a
  classifier passes `None`), and return
  `{"objective": 1 - weighted_accuracy, "val_wacc": weighted_accuracy,
  "val_lastcut_acc": ...}` (`train_causal_tool.py:308-323`; the last-cut accuracy
  is an extra number, not the objective).
- `predict`: one row per example row, **through the same packed path, not
  `Probe.score`** (errata: 6.2 says `predict` writes what `Probe.score` returns,
  but `score` is one sequence per text and a prediction pass would cost
  `build.max_cuts` times the packed pass; the packed path is also the one the
  alignment gate covers, and `Probe.score` stays the served form):
  `{"example_id", "method": "ctool", "target": <the row's `tool`>,
  "score": <largest softmax probability at temperature 1>,
  "label_pred": <argmax class name>, "logits": <the class logits in `labels`
  order>}`.

Legacy: `train_causal_tool.py:97-150, 154-189, 308-323, 487-489`;
`share_data.py:55-62, 362-480`.
**Not ported:** `read_position` and the offset-mapping rule
(`share_data.py:583-611`) — the new packing retokenizes each row and shares by
token prefix, so the decision position is a row's own last token and matches
`Probe.score` exactly; `label_map.json`; `--readonly-env` label folding;
`Counter.most_common()` ordering (`build.py:404-406`) — 1.3 replaces it with the
sorted order, because the old tie-break was unspecified.

### 3. `train/methods/cgen.py`

```python
VERSION = 1
PROBE_KIND = "generator"
CHECKPOINT_META = {"call_sep": "\n[CALL] ", "param_only": False}
GEN_N = 200          # val rows generated per validation; legacy GEN_N
```

`call_sep` is `train_causal_callgen.py:102`; `param_only: false` is what 5.7
reads to allow this method as an `inject.probe_gen`.

The same seven hook names as ctool, with `head_labels` returning `None`.

- `batches`: per event, `full_ids = tok(longest text)`; per row,
  `old_ids = tok(row.text + CALL_SEP)`, `p = lcp(old_ids, full_ids)`,
  `tail_ids = old_ids[p:]` (assert non-empty),
  `tgt_ids = tok(row.call, add_special_tokens=False) + [eos]`,
  `seg_ids = tail_ids + tgt_ids`, `seg_lab = [-100]*len(tail_ids) + tgt_ids`.
  Drop a row whose `tgt_ids` exceeds `MAX_TGT_TOK = 160`
  (`train_causal_callgen.py:103`) and count it. Pack, mask, block and group
  exactly as in `share_data.py:362-533`. **`Batch["event_end"]` names every
  target token's *query* position `t-1`** (labels are not shifted:
  `share_data.py:455-470`), and the method's own keys carry `target_ids` (the
  token at `t`), `row_of` (which decision row each target token belongs to),
  `weight` (per row), `mb`, `mb_weight`, `example_id`.
- `loss`: `out = probe.forward(batch)`;
  `tok_ce = F.cross_entropy(out.logits.float(), batch["target_ids"], reduction="none")`;
  aggregate to a per-row mean by `index_add` over `row_of` divided by each row's
  target-token count (`train_causal_share.py:179-197`); return
  `(row_ce * weight).sum()` — the unnormalised weighted sum.
- `reference_loss`: `train_causal_callgen.py:203-237` (`collate`) plus `:268-294`
  (`inst_ce`) — one row per sequence, left-truncated prompt, right padding, labels
  masking the prompt, per-instance mean CE — weighted and summed over the slice.
  It reaches the model through `probe.forward` with a plain 2-D
  `attention_mask`, no `position_ids`, and an `event_end` naming each target
  token's query position in its own sequence.
- `validate`: the weighted val CE over the whole frame it is handed (the same
  packed path, `train_causal_callgen.py:297-337`) **and** greedy generation over a
  deterministic subsample of `GEN_N` rows
  (`random.Random(cfg.train.seed).shuffle` over the rows in `example_id` order,
  `train_causal_share.py:272-295`), compared with `eval/utils/probe_eval.py`'s
  `match_cgen(pred, target, env)` where `env = open_env(cfg.data.env)` — the
  environment is reachable because 3.4 writes `data` into a generator train run's
  projection. `max_new` is `cfg.train.predict.max_new` (errata). Returns
  `{"objective": 1 - weighted full_call_ok, "val_ce": ..., "val_tool_ok": ...,
  "val_params_all_ok": ..., "val_full_call_ok": ..., "gen_n": ...}`.
- `predict`: one row per example row. `texts = [row.text for ...]`,
  `out = probe.generate(texts, cfg.train.predict.max_new,
  CHECKPOINT_META["call_sep"])` — the method supplies its **own** separator (2.6,
  6.2). Row: `{"example_id", "method": "cgen", "target": <the row's `call`>,
  "text_pred": out, "gen_tokens": len(tok(out,
  add_special_tokens=False)["input_ids"])}` (errata: `Probe.generate` returns
  strings only, so the method computes `gen_tokens`).

Legacy: `train_causal_callgen.py:100-105, 137-200, 203-237, 268-294, 339-365`;
`share_data.py:169-357, 362-533`.
**Not ported:** the fire head; `--readonly-env` row dropping; `--overlong` /
`select_keys` (`share_data.py:113-165`); the `MAX_BOUNDS` packed-length assertion
(`share_data.py:350-357`).

### 4. `train/methods/cparam.py`

```python
VERSION = 1
PROBE_KIND = "generator"
CHECKPOINT_META = {"call_sep": "\n[CALL] ", "param_only": True}
GEN_N = 200
ASSEMBLY_MISMATCH_LIMIT = 0.05      # legacy train_causal_param.py:90
```

`param_only: True` is exactly what 5.7 refuses an `inject.probe_gen` on, which is
why this method never serves a live run.

**The target, and the one derivation this file owns** (1.2, 1.3):

```python
prompt_tail = CHECKPOINT_META["call_sep"] + tool + "("   # legacy param:99-102
target      = call[len(tool) + 1:]                        # strip tool + "(", keep ")"
```

`target` is `None` when `call` does not start with `tool + "("`; such rows are
dropped whole and counted as `assembly_mismatch`, and the file **raises** when
their share exceeds `ASSEMBLY_MISMATCH_LIMIT`
(`train_causal_param.py:105-123`, `share_data.py:341-349`). The derived string is
what `predict` writes into `prediction.target`, which is why the derivation lives
here and not in the trainer.

Hooks as cgen's, with three differences:

- `batches` uses `prompt_tail` (per row, it names that row's tool) instead of the
  bare separator, and the derived `target` instead of `call`.
- `validate` and `predict` build the **whole prompt per row** —
  `row.text + CHECKPOINT_META["call_sep"] + row.tool + "("` — and call
  `probe.generate(texts, max_new, call_sep="")` (errata: the pinned
  `Probe.generate(texts, max_new, call_sep)` appends one separator to every text
  while this method's tail is per row; `CHECKPOINT_META["call_sep"]` stays
  `"\n[CALL] "` and `param_only` stays `true`).
- `validate` calls `eval/utils/probe_eval.py`'s `match_cparam` on two **whole calls**:
  both the prediction and the target get `row.tool + "("` prepended, per 2.6's
  rule for cparam's two callers. `objective = 1 - weighted params_all_ok`.

Legacy: `train_causal_param.py:88-123, 125-197, 214-250, 252-277`;
`share_data.py` as for cgen. Not ported: the same list as cgen, plus
`--readonly-env`.

### 5. `tests/test_packed_loss.py`

The second of the four checks the tree's `tests/` line names: "the packed loss
equals a row-by-row loss kept in its plainest form ... on a tiny CPU model". Turn
A3.3 below into a `unittest.TestCase` with one test per method, building the tiny
two-layer model from the Qwen3-0.6B-Base config and the fixture frame through
`data/training_data.py`'s writer. The header line names the venv (`probe`). The
tolerance is 2.5's `1e-4` on the per-example-row difference. `pytest` is not
installed on this machine.

## Acceptance

Run from the repo root and paste the real output. `$PR` is
`/home/y-guo/reproduce/new1/external/probe-env/bin/python`. Every command is
CPU-only: the tokenizer fixture is read from
`/net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-0.6B-Base` (read-only) and
every model is a two-layer 64-hidden Qwen3 built from that directory's config,
about 10M parameters.

**A3.1 — the literal rules of 3.3, and the `PROBE_KIND` pair.**
```bash
python3 - <<'PY'
import ast, pathlib, sys
files = ["train/utils/trainer.py", "train/methods/ctool.py",
         "train/methods/cgen.py", "train/methods/cparam.py"]
bad = []
for f in files:
    tree = ast.parse(pathlib.Path(f).read_text())
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
        e = ast.parse(pathlib.Path("eval/utils/probe_eval.py").read_text())
        ek = [n for n in e.body if isinstance(n, ast.Assign)
              and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "PROBE_KIND"
              and n.col_offset == 0]
        method = f.split("/")[-1][:-3]
        table = ast.literal_eval(ek[0].value) if len(ek) == 1 else {}
        if table.get(method) != ast.literal_eval(k[0].value):
            bad.append((f, "PROBE_KIND disagrees with the eval side"))
print("FAIL", bad) if bad else print("OK")
sys.exit(1 if bad else 0)
PY
```
Expected: `OK`, exit 0.

**A3.2 — import under the probe venv.**
```bash
"$PR" -c "import train.utils.trainer as t, train.methods.ctool as c, train.methods.cgen as g, train.methods.cparam as p; print(t.VERSION, c.PROBE_KIND, g.PROBE_KIND, p.PROBE_KIND, p.CHECKPOINT_META['param_only'])"
```
Expected: `1 classifier generator generator True`, exit 0.

**A3.3 — the packed loss equals the plain loss, per method.** The script writes a
tiny example frame with `data/training_data.py`'s **writer**, reads it back with its
reader, builds a stub `Probe` whose `forward` is the one
`models/probe_models/base.py` has, and runs the method's own hooks.
```bash
for M in ctool cgen cparam; do
"$PR" - "$M" <<'PY'
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
            weight=1.0, split="train", env="appworld", agent_model="gpt_oss_120b"))
d = pathlib.Path(tempfile.mkdtemp())
training_data.write(d / "examples.parquet", pl.DataFrame(rows, strict=False))
df = training_data.read(d / "examples.parquet")

class Outputs:
    def __init__(self, logits, hidden): self.logits, self.hidden = logits, hidden
class Probe:
    tokenizer, max_len = tok, 512
    probe_kind = "classifier" if name == "ctool" else "generator"
    labels = ["phone.login", "phone.pay"]   # head_labels' order; ctool.loss maps names through it
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
Expected: three `<name> packed=... plain=... diff=...` lines each followed by
`OK`, every `diff` below `1e-4`, exit 0 each time. A non-zero exit or a `diff`
above the tolerance is the packing bug the gate exists for.

**A3.4 — the whole loop, on CPU, with two stubs.** `trainer.run` is exercised end
to end: only `schema.load_frozen`, `schema.run_dir_of`, `base.load` and
`models.probe` are replaced; everything else — `data/training_data.py`,
`data/probe_output.py`, `jobs/registry.py`, the method's hooks, the checkpoint
calls — is the real code.
```bash
"$PR" - <<'PY'
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
                env="appworld", agent_model="gpt_oss_120b"))
training_data.write(build_dir / "examples.parquet", pl.DataFrame(rows, strict=False))

cfg = types.SimpleNamespace(
    _key="t0", _commit="deadbee", _debug=True, _upstream={"build": "b0"},
    _versions={"train/utils/trainer.py": 1}, _stage="train",
    data=types.SimpleNamespace(env="appworld"),
    models=types.SimpleNamespace(probe="qwen3_0pt6b", probe_row={"role": "probe", "family": "qwen"}),
    probe=types.SimpleNamespace(method="ctool", tuning="full"),
    train=types.SimpleNamespace(
        lr=1e-4, epochs=1, warmup_ratio=0.0, seed=42, max_len=256, events_per_mb=2,
        accum=1, grad_ckpt=False, max_steps=None, align_check=True, checkpoint_hours=2.0,
        predict=types.SimpleNamespace(splits=["val", "test"], cap=None, max_new=8)))

class Outputs:
    def __init__(self, logits, hidden): self.logits, self.hidden = logits, hidden
class Probe:
    tokenizer, max_len = tok, 256
    probe_kind = "classifier"
    labels = ["phone.login", "phone.pay"]   # what head_labels returns over this frame;
                                            # ctool's loss, validate and predict read it
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
Expected, in order: the column list exactly
`['depth', 'event_id', 'example_id', 'gen_tokens', 'label_pred', 'logits',
'method', 'score', 'split', 'target', 'task_id', 'text_pred', 'tool', 'version']`;
`['test', 'val'] 24`; `['phone.login', 'phone.pay']`; `True`; `True True`;
`done`; exit 0. The stub's `score` raises on purpose: a `predict` that calls it
instead of the packed path fails here.

**A3.5 — the 2.4 continue rule.** Append to the A3.4 script, after its last print:
```python
import importlib
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
Expected: `a True True`, `b 24 True`, `c True True`.

**A3.6 — the permanent packed-loss test.**
```bash
"$PR" -m unittest tests.test_packed_loss -v
```
Expected: three tests (`ctool`, `cgen`, `cparam`), `OK`, exit 0.

**A3.7 — no absolute cluster path in the code.**
```bash
grep -n "/home/\|/net/" train/utils/trainer.py train/methods/*.py || echo NO_ABS_PATH
```
Expected: `NO_ABS_PATH`. (The tokenizer path above lives in the acceptance
command, never in the code.)

### Selfcheck lines that apply later

`run.py selfcheck` (ticket 15) will check: the four files' `README.md` annotation
lines against their real imports; one `VERSION` line per file, at column zero,
exactly once; the `probe.method` axis against the intersection of the file names
under `train/methods/` and the keys of `eval/utils/probe_eval.py`'s `PROBE_KIND`
and `MATCH_VERSION` tables; and `PROBE_KIND` declared in the train method file
and equal to that method's entry in the eval table. A3.1 stands in for all but
the first.

### GPU / main session — not yours

Every one of these starts a GPU process. An implementer returns BLOCKED with the
command.

1. **A debug train of each method**: `run.py train_probe ctool_qwen3_0pt6b --debug`, then
   the same for `cgen_qwen3_0pt6b` and `cparam_qwen3_0pt6b`. Must show `align_check.json` with
   `"PASS": true` and `diff` below `1e-4`; `train_log.jsonl` holding `start`, at
   least one `step`, one `eval` and one `save_best` line; `best/meta.json`
   carrying `backbone`, `tuning`, `labels` (ctool only), `call_sep`,
   `param_only`, `max_len`, `train_key`; `predictions.parquet` whose `split`
   column holds exactly `val` and `test` and whose row count equals the example
   rows of those two splits (or `train.predict.cap` per split); `done.json` with
   `metrics.objective` and `stage_extra.labels`; `heartbeat/0-0.jsonl` ending in
   `"status": "done"`.
2. **The alignment gate actually fires**: one debug train with a deliberately
   broken packing (a one-token shift in `event_end`) must exit non-zero **before
   the first optimizer step** and write `align_check.json` with `"PASS": false`.
3. **Resume**: kill a debug train after `last/` has been written and relaunch —
   the new process prints that it resumed from `last/meta.json["step"]`, does not
   rewrite `train_log.jsonl` from the top, and reaches the same `done.json`
   counts as an uninterrupted run.
4. **The predict-only continue path**: delete `predictions.parquet` and
   `done.json` from a finished debug train run and relaunch — it loads `best/`,
   takes no optimizer step, and rewrites `predictions.parquet` with the same row
   count.
5. **LoRA**: one debug train with `probe.tuning: lora` — `best/` holds merged
   full weights (a `safetensors` of the backbone's own size, no `adapter_*`
   file) and its `meta.json` `tuning` reads `lora`.
6. **Two methods over one build**: train ctool and cgen against the same build
   key; the two train directories differ, both `consumed.json` files name the
   same `examples.parquet` with the same sha1, and the cgen eval accepts the
   ctool eval as its `theta_from`.
7. **The cost of predicting at every cut** (contracts 9(d)): for cgen and for
   cparam, measure `(done.json mtime - train_done.json mtime) / predictions rows`
   and extrapolate to the full example count. Report as facts only.

## Comments

- 2026-09-18, from gyb (review of waves 2 and 3, session fork1): the eval fold
  gyb ruled on (errata, the entry "0.2 / 2.1 / 2.6") has landed before this
  ticket is dispatched, and this ticket's text is already rewritten to it. The
  eval side is now one file, `eval/utils/probe_eval.py`: it holds the column-zero
  tables `PROBE_KIND` (method -> report shape) and `MATCH_VERSION` (method ->
  match version), and the three match functions under the names `match_ctool`,
  `match_cgen` and `match_cparam`. A train method file imports that one file for
  its validation metric, and `STAGES["train"]["versions"]` folds
  `eval/utils/probe_eval.py#MATCH_VERSION.<method>` in place of a per-method
  file's `VERSION`. `train/methods/` stays one file per method.
- 2026-09-18, from gyb (errata "3.3 / 8.6 (what a `VERSION` bump invalidates)"): every file of this ticket that carries `VERSION` also carries, directly above it, the VERSION rule comment block and, directly below it, the column-zero literal `VERSION_HISTORY = {}`. Copy both verbatim from a merged file (`data/probe_input.py` has them once the change `owner/2026-09-18-version-history` has merged); `.scratch/from-zero/spec.md` section 5 states the rule. Wherever this ticket says a `VERSION` enters a key, the number folded is the file's effective version for the stage being keyed, and `_versions` still records the real `VERSION`.
- 2026-09-18, wave 5 precheck (main session of wave 5, session new1-97; record in `.scratch/from-zero/sdd/2026-09-18-wave5/precheck.json`). The change `owner/2026-09-18-version-history` is merged (39b3d60): `data/probe_input.py` carries the rule block and `VERSION_HISTORY = {}`, and the train row of the stage table folds `train/utils/trainer.py`, `train/methods/{method}.py` and `eval/utils/probe_eval.py#MATCH_VERSION.{method}`. Every function this ticket imports exists on the merge base with the signature the ticket names. The read-only hook refuses any Bash command line that names `experimental_settings` or a settings yaml together with a write word; none of this ticket's acceptance commands does.
