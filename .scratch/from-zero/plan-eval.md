# Build plan: `eval/` (six files)

Planner: eval folder group, 2026-09-17, branch `from-zero`.
Sources: `notes/plans/2026-09-14-structure-from-zero.md` (Part 1 tree, fixed),
`notes/plans/2026-09-17-contracts.md` (Parts 0.2, 1.1-1.5, 2.1-2.6, 3.1, 3.3, 4.1,
4.2, 5.1, 5.2, 5.4, 5.5, 8.0-8.6, 9(a)#2, #12, #15), `notes/CONTEXT.md`,
`legacy/pipeline/eval/*`, `legacy/pipeline/inject/score_live.py`.

Two facts that shape everything below:

- **No GPU, no torch, every file imports as `any`** (the tree's `eval/` line;
  principle 7). Every model call the legacy eval files make has already happened:
  `train/utils/trainer.py`'s last step writes one `prediction` row per example row
  of `train.predict.splits`, generators included (1.3, 9(a)#2). `eval/` reads that
  parquet and computes numbers. Everything in the legacy files below the line
  "load the model / score / generate" is therefore **not ported**, per file.
- `venv: any` means NumPy is allowed (9(a)#15) and required for the temperature
  fit and the bootstrap. NumPy is absent from `external/appworld/venv` today; see
  section 4, prerequisite P0.

---

## 1. Files

### 1.1 `eval/utils/probe_eval.py`

One sentence: the eval-side library — drives a method file, owns the probe report
format (`probe_report.json` + `fires.parquet`), the temperature fit, the bootstrap
interval, `consumed.json`, the heartbeat and `done.json`.

- **venv:** `any` (runs under `venvs.probe` = `external/probe-env/bin/python`, 6.3).
- **imports** (0.2): `experimental_settings/schema.py`, `data/probe_output.py`,
  `jobs/registry.py`; `[polars, numpy]`. It must **not** import `data/__init__.py`
  or `data/environments/__init__.py` — `selfcheck` parses the import statements
  against this line (0.1).
- **used by** (0.2): `eval/methods/{ctool,cgen,cparam}.py`, `run.py` (`read_report`,
  to freeze `_resolved.probe_temperature`, 5.4), `eval/method_table.py`.
- **reads:** `predictions.parquet` (through `data/probe_output.py`), its own train
  run's `meta.json` (`stage_extra.labels`, `upstream["build"]`), the referenced
  eval run's `meta.json` and its train run's `meta.json` (the 2.5 gate), the
  referenced probe report (through its own `read_report`).
- **writes:** `probe_report.json`, `fires.parquet`, `report.md`, `consumed.json`,
  `heartbeat/0-<launch>.jsonl`, `done.json`.

**Module-level names.**

```python
VERSION = 1          # column zero, exactly once, integer literal (3.3)

FIRES_SCHEMA = {     # the fires.parquet column list of 1.4, in this order
    "risk": pl.Float32, "theta": pl.Float32, "split": pl.Utf8,
    "event_id": pl.Utf8, "example_id": pl.Utf8, "score": pl.Float32,
    "depth": pl.Float32, "label_pred": pl.Utf8,
}
IDENTITY_FIELDS = frozenset({"version", "method", "probe_kind", "stage_key",
                             "train_key", "theta_from", "commit", "labels"})
```

**Functions** (signatures copied from the contracts, section cited):

```python
def run(run_dir: Path, method) -> None                                    # 2.6
def write_report(run_dir: Path, fields: dict, fires: DataFrame | None) -> None   # 1.4
def read_report(run_dir: Path) -> tuple[dict, DataFrame | None]           # 1.4
def fit_temperature(logits: "np.ndarray", y: "np.ndarray") -> float       # 1.4 (see E4)
def bootstrap_ci(df: DataFrame, group: str, stat, *, n: int, seed: int) -> dict[str, list[float]]   # 1.4 (see E5)
def softmax(logits: "np.ndarray", temperature: float) -> "np.ndarray"     # helper, shared by a second classifier method
```

**What `run` does, in order.**

1. `cfg = schema.load_frozen(run_dir)` (2.6). No method file calls it (2.6).
2. `hb = registry.beat(run_dir, 0)` and `hb.emit(0, total, "item")` before the
   work; `unit` is `item` for eval and the piece index is 0 (8.4).
3. `train_dir = schema.run_dir_of("train", cfg._upstream["train"], debug=cfg._debug)`
   (3.1; the same-setting upstream keeps the debug overlay).
4. `pred_df = probe_output.read(train_dir / "predictions.parquet")`. Raise, naming
   the values, when the frame's `method` column holds anything but
   `cfg.probe.method`.
5. `labels = json.load(train_dir/"meta.json")["stage_extra"]["labels"]` (1.3, 8.3).
   `None` for a generator.
6. `kind = method.PROBE_KIND`. For `generator`:
   - `ref_eval_dir = schema.run_dir_of("eval", cfg._upstream["theta_from.eval"], debug=False)`
     (3.1: a resolved reference is located without the debug overlay).
   - Gate: `(ref_eval_dir/"done.json").exists()`, else refuse naming the directory (2.5).
   - `ref = read_report(ref_eval_dir)`.
   - Gate: `ref[0]["risk_targets"] == cfg.eval.risk`, else refuse naming both lists (2.5).
   - Build-key gate (2.5, errata E1): read `ref_eval_dir/"meta.json"` →
     `upstream["train"]` → `schema.run_dir_of("train", that, debug=False)` →
     that run's `meta.json` → `upstream["build"]`; refuse, naming both keys, when
     it differs from `json.load(train_dir/"meta.json")["upstream"]["build"]`.
   For `classifier`: `ref = None`.
7. `fields, fires = method.report(pred_df, cfg, ref, labels)` (2.6).
8. Raise, naming the key, when `set(fields) & IDENTITY_FIELDS` is non-empty (1.4).
9. Merge the identity block (1.4): `version=VERSION`, `method=cfg.probe.method`,
   `probe_kind=kind`, `stage_key=cfg._key`, `train_key=cfg._upstream["train"]`,
   `theta_from=cfg._upstream.get("theta_from.eval")` (None for a classifier),
   `commit=cfg._commit`, `labels=labels`.
10. `write_report(run_dir, fields, fires)`.
11. Write `report.md` (see below).
12. Write `consumed.json` = `[{path, sha1, n_rows}]` (1.5) for the prediction
    parquet (`n_rows` = frame height) and, for a generator, the referenced
    `probe_report.json` (`n_rows: null`) and `fires.parquet` (its height).
13. `registry.write_done(run_dir, stage="eval", key=cfg._key, commit=cfg._commit,
    counts={"rows": <pred rows>, "events": <distinct event_id>, "fires": <fires rows or 0>},
    versions=cfg._versions, metrics=<flat dict, E11>, report="report.md")` (8.0, 1.5).
14. `hb.finish()` (8.0). `run` appends **no registry row** (2.6).

`write_report` writes `probe_report.json` with `json.dumps(..., indent=1,
ensure_ascii=False)` and, when `fires` is not None, `fires.parquet` with
`fires.write_parquet`, each through a temporary name in the same directory and a
rename (errata E12). `read_report` returns `({}, None)`-free: it raises when the
json is missing, raises when its `version` is above this module's `VERSION`
(Part 1's version rule), and returns `None` for the frame when no
`fires.parquet` exists.

`report.md`: a title line with the stage key, method, probe kind and commit; for a
classifier, the fitted temperature and one line per risk target
(`theta`, `coverage (CI)`, `trig_acc (CI)`, `earliness (CI)`, `wrong_spec`, `n`);
for a generator, one line per risk target (`theta_used`, `tool_ok`,
`params_all_ok`, `full_call_ok`, `n`); then the per-split event counts. It is a
rendering of `probe_report.json` and computes nothing.

**Legacy source and what is not ported.**

| ported from | lines | into |
|---|---|---|
| `legacy/pipeline/eval/eval_tool.py` `fit_temperature` | 213-224 | `fit_temperature`, rewritten without torch (E4) |
| `legacy/pipeline/eval/eval_tool.py` `bootstrap` | 279-296 | `bootstrap_ci` (resample by task, sorted-index bounds kept, E5) |
| `legacy/pipeline/eval/eval_tool.py` report assembly and md rendering | 598-618, 634-692 | `write_report` + `report.md`, restricted to 1.4's field list |

Not ported, stated: the whole model half of `eval_tool.py` — `score` (61-76),
`load_causal` (81-91), `score_causal` (116-197), `weights_fingerprint` (94-113),
`token_cost` (200-208) and the `--cached-logits` / `--adopt-logits-fingerprint`
fingerprint machinery (312-316, 358-380, 436-498); the `--overlong`
left/skip/drop-event modes and their five counter fields (117-197, 607-611); the
readonly-tool / abstain-class mode (`readonly_map`, 318-321, 384-398, 425-431,
557-596, 668-681); `--legacy-splits` (308-309, 350-356); `--limit` (322-325,
621-623); and `--report-dir` / `--device` (310-317). The first group is gone
because the probe never runs here; the rest are settings-era switches that the
setting schema (5.2) and the key (3.3) replace.

### 1.2 `eval/methods/ctool.py`

One sentence: the classifier metric — fit the temperature and sweep theta on the
val prediction rows, freeze theta per risk target, report on test, and write the
fired rows every generator joins against.

- **venv:** `any`.
- **imports** (0.2): `eval/utils/probe_eval.py`; `[polars, numpy]`. Nothing else —
  no `schema.py`, no `registry.py` (2.6), no environment.
- **used by:** `train/methods/ctool.py` (its `match` function, for the validation
  metric).
- **reads / writes:** nothing; everything goes through `probe_eval.py`.

**Module-level names** (both at column zero, exactly once, 3.3):

```python
VERSION = 1
PROBE_KIND = "classifier"        # equal to train/methods/ctool.py's; selfcheck compares (2.6)
```

**Functions:**

```python
def match(pred: str, target: str, env) -> bool                                   # 2.6
def report(pred_df, cfg, ref, labels) -> tuple[DataFrame | None, ...]            # 2.6
# exact: report(pred_df: DataFrame, cfg: Setting,
#               ref: tuple[dict, DataFrame | None] | None,
#               labels: list[str] | None) -> tuple[dict, DataFrame | None]
def main(run_dir: Path) -> None      # one line: probe_eval.run(run_dir, sys.modules[__name__])  (2.6)
```

plus `if __name__ == "__main__":` parsing exactly `--run-dir <dir>` and nothing
else (2.6's command shape; a one-process stage carries no `--piece`, 8.4).

`match(pred, target, env)` is class-name equality, `pred == target`; `env` is
`None` and is ignored (2.6).

**`report`'s algorithm** (the port of `eval_tool.py`'s post-processing):

1. `ref` must be None and `labels` must be a list; raise otherwise.
2. `logits` → `np.asarray(pred_df["logits"].to_list(), dtype=np.float64)`;
   `y` = the index of each row's `target` in `labels`; raise, naming the value,
   on a target that is not in `labels` (1.3's class-order rule makes this a defect).
3. `T = probe_eval.fit_temperature(logits[val], y[val])` where `val` is
   `split == "val"`. Raise when the val slice is empty.
4. `probs = probe_eval.softmax(logits, T)`; per row `conf = probs.max(axis=1)`,
   `pred_idx = probs.argmax(axis=1)`, `label_pred = labels[pred_idx]`.
   (Temperature scaling does not move the argmax, so this `label_pred` equals the
   prediction row's own; the recomputed one is used so one array feeds both.)
5. **The first-crossing rule, once, here** (1.4): group the rows by `event_id`,
   order each event's cuts by `depth` ascending, tie-broken by `example_id`
   ascending (errata E2), and take the first cut with `conf >= theta`. Per event:
   `{fired, ok: label_pred == target, depth, conf, task_id, split, event_id,
   example_id, label_pred}`. Port of `eval_tool.py:227-249` minus its `nro_id`
   parameter (the readonly arm is not ported).
6. `agg(recs)` → `{n, coverage, trig_acc, earliness, wrong_spec}`, each rounded to
   4 places, verbatim from `eval_tool.py:252-260`
   (`coverage = fired/n`, `trig_acc = ok/fired`, `earliness = mean(1-depth)` over
   fired, `wrong_spec = wrong/n`).
7. `grid`: for every theta in `cfg.eval.theta_grid`, `agg` over the val events;
   each entry is `{"theta": θ, **agg}`.
8. `chosen`: per risk in `cfg.eval.risk`, the theta with the largest `coverage`
   among those whose `trig_acc >= 1 - risk` and whose `coverage > 0`, else `None`
   (`eval_tool.py:513-518`). Keys are `str(risk)` (1.4).
9. `frozen`: per risk with a theta, `agg` over the **test** events at that theta
   plus `ci = probe_eval.bootstrap_ci(...)` over the same events grouped by
   `task_id`, with `n=cfg.eval.bootstrap`, `seed=cfg.eval.bootstrap_seed`. Risks
   whose `chosen` is null are absent from `frozen`.
10. `fires`: for every risk with a theta, the fired events of **every split** at
    that theta (1.4), one row per fired event with the `FIRES_SCHEMA` columns.
11. Returns `({"temperature": round(T,4), "risk_targets": cfg.eval.risk,
    "grid": grid, "chosen": chosen, "frozen": frozen,
    "n_events": {split: distinct event_id}}, fires)` (E6, E13).

**Legacy source:** `legacy/pipeline/eval/eval_tool.py:213-224, 227-249, 252-260,
279-296, 500-532, 513-518`.
**Not ported:** `economics` (263-276) and the whole
`speculation_economics` block (612-617, 656-667); the stop-time calibration
(534-545), the depth-decile accuracy and the frequency-prior baseline (547-568),
`probe_cost_test` / `probe_backbone` (624-630). None of them is a field of 1.4's
classifier shape, and 1.4's table is the format. The readonly arm (`nro_id` in
`replay`, 227-249, and `readonly_stats`, 570-596) is not ported — `inject.arm`
(5.3) replaces the arm concept and no axis value names a readonly mode.

### 1.3 `eval/methods/cgen.py`

One sentence: exact match of the generated whole call, over the events a
referenced classifier report fired, at that report's frozen theta.

- **venv:** `any`.
- **imports** (0.2): `eval/utils/probe_eval.py`,
  `data/environments/__init__.py` (`open_env`, for the environment whose
  `split_args` and `build_call` `report` normalises with, 2.6); `[polars, numpy]`.
- **used by:** `train/methods/cgen.py` (its `match` function).
- **reads / writes:** nothing; everything goes through `probe_eval.py`.

```python
VERSION = 1
PROBE_KIND = "generator"

def match(pred: str, target: str, env) -> dict[str, bool]      # 2.6
def report(pred_df, cfg, ref, labels) -> tuple[dict, None]     # 2.6
def main(run_dir: Path) -> None
```

**`match`** returns `{"tool_ok", "params_all_ok", "full_call_ok"}` (2.6, 1.4) and
is the one comparison `train/methods/cgen.py`'s `validate` also calls:

1. `t = env.split_args(target)`; raise, naming the target, when it is None — the
   build gate of 2.5 makes a non-round-trippable `call` impossible, so a failure
   here is a defect, not data.
2. `p = env.split_args(pred)`; when None, return all three False (the port of
   `parse_call`'s `parse_fail`, `eval_causal_call.py:172-203`, now the
   environment's business per 4.2).
3. `tool_ok = p.tool == t.tool`.
4. `params_all_ok`: the union-by-key comparison of
   `eval_causal_call.py:205-226` over the two argument lists — group each side's
   `(key, value)` pairs by key in call order, walk
   `list(truth_keys) + [k for k in gen_keys if k not in truth_keys]`, add
   `max(len(tv), len(gv))` instances and count position-by-position equality;
   `params_all_ok = (n_instances == 0) or (n_ok == n_instances)`.
   **The `noparam` short-circuit of `eval_causal_call.py:401` is dropped** — see
   errata E3; a spurious argument on a no-argument call is now wrong.
5. `full_call_ok = tool_ok and params_all_ok`.

Both sides' values arrive already normalised, because `env.split_args` is the one
parser (4.2); there is no second `norm()` and no loose/strict pair (see below).

**`report`'s algorithm:**

1. `env = open_env(cfg.data.env)` (2.1: `data` is in this stage's projection).
   `ref` must be a `(fields, fires)` tuple and `labels` must be None; raise otherwise.
2. `test = pred_df.filter(split == "test")` (1.4 pins the split).
3. Per risk in `cfg.eval.risk`: `theta_used[str(risk)] = ref_fields["chosen"][str(risk)]`.
   When it is null, `exact[str(risk)] = {"tool_ok": None, "params_all_ok": None,
   "full_call_ok": None, "n": 0, "ci": None}` and the eval does **not** refuse (1.4).
4. Otherwise join `test` to `ref_fires.filter(risk == risk, split == "test")` on
   `example_id` (1.4: the first-crossing rule is executed once, by ctool, and
   everyone else joins), call `match(row.text_pred, row.target, env)` per joined
   row, and report the three rates rounded to 4 with `n` = joined rows, plus
   `ci = probe_eval.bootstrap_ci` over those rows grouped by `task_id` for the
   same three rates.
5. `n_events = {split: distinct event_id}` over `pred_df` (E6).
6. Returns `({"risk_targets": cfg.eval.risk, "theta_used": theta_used,
   "exact": exact, "n_events": n_events}, None)`.

**Legacy source:** `legacy/pipeline/eval/eval_causal_call.py:100-125`
(`replay_fire`, now ctool's and reached by the join), `129-226`
(`norm` / `split_named_raw` / `parse_call` / `match_params` → the environment's
`split_args` plus the comparison above), `379-410` (`score_points` → `match` +
the rate aggregation), `700-745` (the report fields, restricted to 1.4's list).

**Not ported:** the generation half (`generate`, 231-254) and the model load
(657-666) — the text is in `prediction.text_pred`; the self-fire block
(`load_ready` 262-299, `score_fire` 301-328, `replay_fire_head` 330-352,
`agg_fire` 354-364, `pick_theta` 366-375, `self_fire_block` 413-489) — no fire
head exists in this tree and no setting field names one; the readonly arm and its
fuses (505-518, 578-607, 644-652); the three-way `--data` cross-check (566-577),
replaced by the shared-build-key gate of 2.5; the `--overlong` filtering (672-694);
`--limit` (695-696); the `params_all_ok_strict` / `param_acc_loose` /
`param_acc_strict` tiers, `exact_call_ok`, `parse_fail_rate`, `noparam_rate`, the
`by_tool` breakdown and the `samples` list (401-410, 710-745) — 1.4's generator
shape names exactly `tool_ok`, `params_all_ok`, `full_call_ok`, `n`, `ci`.
Strictness in particular cannot be ported: the raw, un-normalised argument strings
do not survive into `prediction`, and `example.args` is never read by `eval/` (1.2).

### 1.4 `eval/methods/cparam.py`

One sentence: exact match of the generated arguments, rebuilt into a whole call
with the event's tool, over the events a referenced classifier report fired.

- **venv:** `any`.
- **imports** (0.2): `eval/utils/probe_eval.py`, `data/environments/__init__.py`
  (`open_env`); `[polars, numpy]`.
- **used by:** `train/methods/cparam.py` (its `match` function).
- **reads / writes:** nothing.

```python
VERSION = 1
PROBE_KIND = "generator"

def match(pred: str, target: str, env) -> dict[str, bool]      # 2.6, E7
def report(pred_df, cfg, ref, labels) -> tuple[dict, None]     # 2.6
def main(run_dir: Path) -> None
```

`match` is handed **two whole calls** (2.6): its two callers — this file's
`report` and `train/methods/cparam.py`'s `validate` — prepend `tool + "("` (from
the `tool` column their frame carries, 1.2, 1.3) to the predicted and the target
argument string before calling it, because an argument string alone cannot be
parsed by `env.split_args` (1.4). The body is the same comparison cgen's `match`
does, repeated here: the two files do not import each other (the tree's
`eval/methods/` line), and the returned dict carries the same three keys (E7).

**`report`'s algorithm** — steps 1-3 and 5-6 are cgen's; step 4 differs, per 1.4:

- `tool_ok` is `fires.label_pred == prediction.tool` on the joined row — the
  classifier's fired label against the true tool the prediction row carries.
- `params_all_ok` is `match(tool + "(" + text_pred, tool + "(" + target, env)
  ["params_all_ok"]`, where `tool` is the prediction row's `tool` column; the
  returned `tool_ok` of that call is ignored (both sides carry the same prefix,
  so it is always true).
- `full_call_ok = tool_ok and params_all_ok`.
- `ci` over the same three rates, grouped by `task_id`.

**Legacy source:** `legacy/pipeline/eval/eval_causal_param.py:93-119`
(`replay_fire`, now the join), `123-253` (parse and compare → `env.split_args`
plus the comparison of 1.3 above), `257-292` (`score_points`, the
`given + "(" + gen` rebuild is the rule 1.4 keeps), `296-328` (`block`, restricted
to 1.4's field list).

**Not ported:** the two-convention structure — legacy runs the same threshold
points twice, once with the ground-truth tool in the prompt (`gt_tool`) and once
with ctool's argmax (`pred_tool`), and the matrix reads only `pred_tool`
(`eval_causal_param.py:12-21`, `summarize_matrix.py:59-69`). This tree generates
once, at training time, at every cut row (1.3, 9(a)#2), so the report has one
block; the loss from the classifier naming the wrong tool enters through
`tool_ok = fires.label_pred == prediction.tool` (1.4) instead of through a second
generation pass. Also not ported: the generation half (225-249) and the model
load; the readonly arm and its fuses; `given_tool_ok`, `exact_call_ok`,
`parse_fail_rate`, `noparam_rate`, `params_all_ok_strict`, `param_acc_loose`,
`param_acc_strict`, `by_tool` and `samples` (280-292, 296-328).

### 1.5 `eval/score_run.py`

One sentence: score a `sample` or `inject` run from its task records — task
success, speculation outcomes, tokens and time, by seed, against a baseline.

- **venv:** `any`.
- **imports** (0.2): `experimental_settings/schema.py`, `data/trajectory_record.py`,
  `data/environments/__init__.py` (`open_env` for `split_args` and `build_call`,
  and `requested_pairs`, 2.3), `jobs/registry.py`; `[polars]`.
- **used by:** none (program).
- **reads:** the task records of this run and of its baseline; the environment's
  split task-id files (through `requested_pairs`); the scored run's and the
  baseline run's `settings.yaml` (the same-setup gate of 2.5).
- **writes:** `run_report.json`, `report.md`, `heartbeat/0-<launch>.jsonl`,
  `done.json`.

```python
VERSION = 1

def main(run_dir: Path) -> None     # 2.1's program column: eval.score_run, main(run_dir)
```

plus `if __name__ == "__main__":` parsing exactly `--run-dir <dir>`.

**What `main` does, in order.**

1. `cfg = schema.load_frozen(run_dir)`; `env = open_env(cfg.data.env)`.
   `scored = "inject" if "inject" in cfg._upstream else "sample"` (1.5's
   `_upstream` naming: a `score` run's map is `{inject, baseline.sample}` or
   `{sample, baseline.sample}`).
2. `sec = cfg.inject if scored == "inject" else cfg.sample`;
   `triples = requested_pairs(env, sec.split, sec.tasks, sec.n_tasks, sec.seeds)`;
   `pairs = [(t, s) for _, t, s in triples]` (2.3's projection).
3. `scored_dir = schema.run_dir_of(scored, cfg._upstream[scored], debug=cfg._debug)`;
   `base_dir = schema.run_dir_of("sample", cfg._upstream["baseline.sample"], debug=False)`
   when `cfg.score.baseline` is set (3.1: a reference is located without the
   debug overlay).
4. **Same-setup gate** (2.5): `schema.load_frozen` on both upstream run
   directories and compare their `data`, `models.agent` and `generation`
   sections field by field; refuse, naming both directories and the first field
   that differs.
5. **Baseline completeness gate** (2.5): `done_pairs(base_dir, pairs)` must cover
   every pair; refuse naming the missing pairs.
6. `hb = registry.beat(run_dir, 0)`, `hb.emit(0, len(pairs), "task")` (8.4's unit
   for score is `task`), then one beat per task read.
7. `df = trajectory_record.read_dir(scored_dir, pairs)`; `bdf = read_dir(base_dir, pairs)`
   when paired. Both gates and both reads are stated over this pair list and never
   over the directory (2.5).
8. Compute (columns from 1.1):
   - per record: `final.success`, `final.abort`, `final.steps`, `final.completed`,
     `final.tokens_in`, `final.tokens_out`, `final.wall_s`;
     `sum(gen.n_inject)`, `sum(gen.usage.out)`, `sum(gen.discard.chars)`,
     `sum(gen.discard.tokens)`.
   - per `spec` row: `exec_ok`, `error_kind`, `conf`, `discarded_chars`, and the
     after-the-fact firing account — `tool_agree`, `call_agree`, `recalled` —
     computed against the same step's `env.action` through `env.split_args` and
     `env.build_call`: parse both `spec.gen_call` and `env.action`, compare the
     tools (`tool_agree`) and the two `build_call` normalisations (`call_agree`);
     `recalled` is the predicted tool name appearing anywhere in that step's
     `env.action` text (legacy's containment test, `score_live.py:155`, kept
     because `split_args` returns only the first call).
   - per `resume` row: `identical`, `match_len`, `overflow_tok`, `new_tok`.
   - paired: the records whose `(task_id, seed)` the baseline also holds.
   - by seed, when `cfg.score.by_seed`: the same per-record rates per seed, plus
     the mean and the sample standard deviation across seeds.
9. `run_report.json`, the pinned field list:
   `{version, stage_key, scored_stage, scored_key, baseline_key|null, commit,
   n_pairs, n_tasks, n_seeds,
   run: {n_records, n_abort, success, success_no_abort, steps_mean, completed,
   tokens_in, tokens_out, n_inject_per_task, discard_chars, discard_tokens,
   wall_s_mean},
   baseline: {the same block, or null},
   paired: {n, success, base_success, delta_success, tokens_out, base_tokens_out},
   spec: {n, exec_ok, tool_agree, call_agree, recalled, conf_mean,
   discarded_chars, error_kinds: {kind: count}},
   resume: {n, identical, match_len_mean},
   by_seed: {"<seed>": {...}, "mean": {...}, "spread": {...}} | null}`
   (errata E11; every rate rounded to 4, `null` when the denominator is 0).
10. `report.md` — a rendering of the above: the summary table, then one line per
    task (`task, seed, success, base_success, steps, n_inject, tokens_out`).
11. `registry.write_done(run_dir, stage="score", key=cfg._key, commit=cfg._commit,
    counts={"records": …, "tasks": …, "seeds": …, "specs": …},
    versions=cfg._versions, metrics=<flat, E11>, report="report.md")`; `hb.finish()`.
    No `consumed.json`: 1.5 gives it three writers and `score` is not one.

**Legacy source:** `legacy/pipeline/inject/score_live.py:57-108` (the helpers:
`first_call`, `norm_call`, `success_of`, `read_live`, `read_base`) and `111-216`
(the whole summary). `success_of`'s two-shape parse (dict / truncated str /
regex fallback, 70-88) is **not ported**: 1.1 declares `final.success` as a
boolean column of its own and says `eval/score_run.py` reads it and never the
JSON. `first_call` / `norm_call` (54-67) are replaced by `env.split_args` and
`env.build_call` (4.2). Also not ported: the `live_*.jsonl` glob and the
filename-derived task id (120-123) — `read_dir(dir, pairs)` is the reader and the
id chain is 1's; the `task_error` prefix convention (162, 168-170) — 9(a)#17 makes
any non-null `abort` a finished task, counted in `n_abort`; the `format` field
fallback for pre-2026-09-12 runs (124); the per-task `base` lookup by file name
(133-141).

### 1.6 `eval/method_table.py`

One sentence: render the backbone x method table out of the registry, grouping
sweep children and reporting mean and spread.

- **venv:** `any`.
- **imports** (0.2): `experimental_settings/schema.py`, `jobs/registry.py`,
  `eval/utils/probe_eval.py` (`read_report`).
- **used by:** `run.py` (the `table` subcommand, 8.6). Not a stage: no
  `__main__`, no run directory, and **no `VERSION`** — 0.2 gives the other five
  eval files "carries VERSION" and gives this one none, and the stage table never
  names it, so `selfcheck`'s VERSION rule does not cover it.
- **reads:** `jobs/runs.jsonl` (through `registry.ls`), the probe reports the rows
  point at.
- **writes:** a markdown table on stdout or into a named file.

```python
def table(workflow: str | None = None, out: Path | None = None) -> str    # 8.6
```

returns the rendered markdown and also writes it when `out` is given (8.6).

**Algorithm:**

1. `rows = [r for r in registry.ls(workflow, debug=False) if r["stage"] == "eval"]`
   (errata E8).
2. Per row, resolve the cell without opening any `settings.yaml`: `backbone` is
   `diff["models"]["probe"]` when present and the schema default for
   `models.probe` otherwise; `method` is `diff["probe"]["method"]` when present
   and the schema default otherwise (`diff` is `settings_diff.yaml` as JSON, 8.1,
   so a default-valued field is absent from it).
3. Group the sweep children: the group key is `row["parent"]` when it is set and
   `row["setting"]` otherwise (5.5; `parent` and `swept` are the registry row's
   fields and exist for this file).
4. Per row, `read_report(Path(row["dir"]))`; a directory with no
   `probe_report.json` is `PENDING` (legacy's convention,
   `summarize_matrix.py:36-39`) and contributes no number.
5. One table row per `(backbone, method, risk target)` — every risk in the
   report's `risk_targets`, never one tier chosen silently (errata E9). Columns:
   `backbone | method | risk | n | coverage | trig_acc | earliness | wrong_spec |
   tool_ok | params_all_ok | full_call_ok | runs | status`. A classifier report
   fills the four `frozen` columns from `frozen[str(risk)]`, a generator report
   the three `exact` columns from `exact[str(risk)]`, and the other side prints
   `-` (`summarize_matrix.py:31-32`'s `fmt`).
6. Each cell shows `mean ± spread` over the group's runs, spread being the sample
   standard deviation (ddof 1), and the bare value when the group has one run
   (E9). `runs` is the group size; `status` is `OK` when every member has a
   report and `PENDING n/m` otherwise.

**Legacy source:** `legacy/pipeline/eval/summarize_matrix.py:31-73` (`fmt`,
`read_cell`, the PENDING convention) and `76-131` (the rendering).
**Not ported:** the `CELLS` / `REPORT_OF` literal cell list and the fixed
`c1_<model>_<cell>` run-id naming (24-27, 88-91) — the registry's rows are the
inventory now; the `mtool` and `mext` cells (ModernBERT), which no axis value in
5.3 names; the fixed `--models` list and `--prefix` (81-83); the single
`RISK = "0.05"` tier (28) — see E9; the per-model test-scale and prior-baseline
table (114-118), whose `prior_baseline_event_acc` is a field 1.4 does not carry.

---

## 2. Order of construction, and what must exist first

Inside the folder:

1. **`eval/utils/probe_eval.py`** — everything else in the folder except
   `score_run.py` sits on it.
2. **`eval/methods/ctool.py`** — the only producer of `fires.parquet`, which the
   two generator files join against.
3. **`eval/methods/cgen.py`** and **`eval/methods/cparam.py`** — parallel; each
   needs a finished classifier eval run to point `eval.theta_from` at.
4. **`eval/score_run.py`** — independent of 1-3.
5. **`eval/method_table.py`** — needs `read_report` (step 1) and at least one
   registry row to render.

From other folders, per file (the integrator turns these into Blocked-by):

| this file | needs to exist | which names |
|---|---|---|
| `probe_eval.py` | `experimental_settings/schema.py` | `load_frozen(run_dir) -> Setting`, `run_dir_of(stage, key, *, debug)`, the `Setting` with `eval`, `probe`, `data` sections and `_key`, `_commit`, `_debug`, `_upstream`, `_versions` |
| | `data/probe_output.py` | `read(path) -> DataFrame`, `write(path, df)`, `SCHEMA`, `VERSION` |
| | `jobs/registry.py` | `beat(run_dir, piece) -> Heartbeat`, `Heartbeat.emit`, `Heartbeat.finish`, `write_done(run_dir, *, stage, key, commit, counts, versions, metrics, report, pairs=None, stage_extra=None)` |
| `methods/ctool.py` | `eval/utils/probe_eval.py` | `run`, `fit_temperature`, `bootstrap_ci`, `softmax` |
| `methods/cgen.py`, `methods/cparam.py` | `eval/utils/probe_eval.py`; `data/environments/__init__.py` | `open_env(name)`; the environment's `split_args(text)` and `build_call(tool, args)` |
| `score_run.py` | `experimental_settings/schema.py`; `data/trajectory_record.py`; `data/environments/__init__.py`; `jobs/registry.py` | `load_frozen`, `run_dir_of`; `read_dir(dir, pairs)`, `done_pairs(dir, pairs)`; `open_env`, `requested_pairs(env, splits, tasks, n_tasks, seeds)`, `env.split_args`, `env.build_call`, `env.tasks`; `beat`, `write_done` |
| `method_table.py` | `experimental_settings/schema.py`; `jobs/registry.py`; `eval/utils/probe_eval.py` | the schema defaults for `models.probe` and `probe.method`; `ls(workflow=None, *, debug=False, edited=None, progress=None) -> list[dict]` with the start row's `stage`, `key`, `dir`, `diff`, `parent`, `swept` on each row; `read_report` |

`constants/path_outputs.yaml` and `constants/path_datasets.yaml` must exist, but
no `eval/` file opens them: the outputs root reaches `eval/` through
`schema.run_dir_of` and the split files through `data/environments/`.

---

## 3. Acceptance, CPU

Every command is run from the repo root. `A0` is the prerequisite (section 4,
P0). `$PY` below is `external/probe-env/bin/python` — `venv: any` resolves to
`venvs.probe` for a stage program (6.3).

### A1. The `any` import test (all six files, every ticket)

```bash
for P in external/probe-env/bin/python external/appworld/venv/bin/python external/vllm-env/bin/python; do
  for M in eval.utils.probe_eval eval.methods.ctool eval.methods.cgen eval.methods.cparam eval.score_run eval.method_table; do
    $P -c "import importlib,sys; importlib.import_module('$M')" || echo "FAIL $P $M";
  done; done; echo "import test done"
```

Expected: no `FAIL` line, `import test done` printed, exit 0. (This is the
per-interpreter test `run.py selfcheck` automates for `venv: any`, 8.6.)

### A2. No torch, no GPU anywhere in `eval/`

```bash
grep -rn "import torch\|from torch\|cuda\|transformers" eval/ ; echo "exit=$?"
```

Expected: no matches, `exit=1`.

### A3. The literal lines `selfcheck` reads (3.3, 2.6)

```bash
external/probe-env/bin/python - <<'PY'
import re, pathlib
for p in ["eval/utils/probe_eval.py","eval/methods/ctool.py","eval/methods/cgen.py",
          "eval/methods/cparam.py","eval/score_run.py"]:
    s = pathlib.Path(p).read_text()
    v = re.findall(r"(?m)^VERSION = (\d+)$", s)
    assert len(v) == 1, (p, v)
for p, k in [("eval/methods/ctool.py","classifier"),("eval/methods/cgen.py","generator"),
             ("eval/methods/cparam.py","generator")]:
    s = pathlib.Path(p).read_text()
    m = re.findall(r'(?m)^PROBE_KIND = "(\w+)"$', s)
    assert m == [k], (p, m)
assert not re.findall(r"(?m)^VERSION = ", pathlib.Path("eval/method_table.py").read_text())
print("literals ok")
PY
```

Expected: `literals ok`, exit 0.

### A4. The classifier path end to end, on a fixture built in the command

```bash
external/probe-env/bin/python - <<'PY'
import json, subprocess, sys, polars as pl
sys.path.insert(0, ".")
from experimental_settings import schema
from data import probe_output

TK, EK = "aaaaaaaaaaaa", "bbbbbbbbbbbb"
tdir = schema.run_dir_of("train", TK, debug=True); tdir.mkdir(parents=True, exist_ok=True)
edir = schema.run_dir_of("eval",  EK, debug=True); edir.mkdir(parents=True, exist_ok=True)
labels = ["apis.a.x", "apis.b.y"]
rows = []
for ev in range(20):                       # 20 events, 2 cuts each, 10 val / 10 test
    split = "val" if ev < 10 else "test"
    tool = labels[ev % 2]
    for c in range(2):
        rows.append(dict(
            example_id=f"t{ev}__s42|s0|c{c}", event_id=f"t{ev}__s42|s0",
            task_id=f"t{ev}", depth=0.3 + 0.4 * c, split=split, tool=tool,
            method="ctool", target=tool,
            score=0.9, label_pred=tool,
            logits=[3.0, 0.0] if tool == labels[0] else [0.0, 3.0],
            text_pred=None, gen_tokens=None))
probe_output.write(tdir / "predictions.parquet", pl.DataFrame(rows))
(tdir / "meta.json").write_text(json.dumps(
    {"stage": "train", "key": TK, "upstream": {"build": "cccccccccccc"},
     "stage_extra": {"labels": labels}}))
(edir / "settings.yaml").write_text(f"""
data: {{env: appworld, instructions: v1}}
probe: {{method: ctool, tuning: full}}
eval: {{risk: [0.10, 0.05], theta_grid: [0.5, 0.9, 0.975], bootstrap: 50,
        bootstrap_seed: 42, theta_from: null}}
_stage: eval
_key: {EK}
_upstream: {{train: {TK}}}
_versions: {{}}
_debug: true
_commit: deadbeef
_resolved: {{}}
""")
r = subprocess.run([sys.executable, "-m", "eval.methods.ctool", "--run-dir", str(edir)])
assert r.returncode == 0, r.returncode
rep = json.loads((edir / "probe_report.json").read_text())
print("fields:", sorted(rep))
assert rep["probe_kind"] == "classifier" and rep["method"] == "ctool"
assert rep["labels"] == labels and rep["train_key"] == TK and rep["stage_key"] == EK
assert rep["theta_from"] is None and rep["commit"] == "deadbeef"
assert rep["risk_targets"] == [0.10, 0.05] and set(rep["chosen"]) == {"0.1", "0.05"}
assert rep["frozen"]["0.05"]["coverage"] == 1.0 and rep["frozen"]["0.05"]["trig_acc"] == 1.0
assert rep["n_events"] == {"val": 10, "test": 10}
f = pl.read_parquet(edir / "fires.parquet")
print("fires columns:", f.columns, "rows:", f.height)
assert f.columns == ["risk","theta","split","event_id","example_id","score","depth","label_pred"]
assert set(f["split"].unique()) == {"val", "test"}          # every split, 1.4
d = json.loads((edir / "done.json").read_text())
assert d["stage"] == "eval" and d["report"] == "report.md" and d["commit"] == "deadbeef"
assert (edir / "report.md").exists() and json.loads((edir / "consumed.json").read_text())
print("A4 ok")
PY
```

Expected: `A4 ok` printed, exit 0; `fields:` lists at least `chosen`, `commit`,
`frozen`, `grid`, `labels`, `method`, `n_events`, `probe_kind`, `risk_targets`,
`stage_key`, `temperature`, `theta_from`, `train_key`, `version`;
`fires columns:` exactly the eight of 1.4 and `rows: 40` (20 events fired at each
of the two risk targets). Every file lands under the outputs root's `debug/`
subtree — `schema.run_dir_of(..., debug=True)` is what names it, nothing is
hardcoded.

### A5. The temperature fit and the bootstrap (deterministic, no torch)

```bash
external/probe-env/bin/python - <<'PY'
import sys, numpy as np, polars as pl; sys.path.insert(0, ".")
from eval.utils import probe_eval as pe
rng = np.random.default_rng(0)
y = rng.integers(0, 3, 4000)
lg = np.zeros((4000, 3)); lg[np.arange(4000), y] = 4.0     # over-confident by 2x
lg = lg * 2.0
T = pe.fit_temperature(lg, y)
print("T =", round(T, 4))
assert 1.0 < T < 20.0
assert abs(pe.fit_temperature(lg, y) - T) < 1e-9           # deterministic
df = pl.DataFrame({"task_id": [f"t{i//4}" for i in range(400)],
                   "ok": [i % 2 == 0 for i in range(400)]})
ci = pe.bootstrap_ci(df, "task_id", lambda d: {"acc": d["ok"].mean()}, n=200, seed=42)
print("ci =", ci)
assert ci == pe.bootstrap_ci(df, "task_id", lambda d: {"acc": d["ok"].mean()}, n=200, seed=42)
assert ci["acc"][0] <= 0.5 <= ci["acc"][1]
print("A5 ok")
PY
```

Expected: `A5 ok`, exit 0; `T` printed and identical across the two calls; `ci`
identical across the two calls and bracketing 0.5.

### A6. The two generator methods, against the A4 report

Run after A4 in the same shell session (it reuses `bbbbbbbbbbbb`).

```bash
external/probe-env/bin/python - <<'PY'
import json, subprocess, sys, polars as pl; sys.path.insert(0, ".")
from experimental_settings import schema
from data import probe_output
from data.environments import open_env
env = open_env("appworld")
TK2, EK2 = "dddddddddddd", "eeeeeeeeeeee"
tdir = schema.run_dir_of("train", TK2, debug=True); tdir.mkdir(parents=True, exist_ok=True)
edir = schema.run_dir_of("eval",  EK2, debug=True); edir.mkdir(parents=True, exist_ok=True)
rows = []
for ev in range(20):
    split = "val" if ev < 10 else "test"
    tool = ["apis.a.x", "apis.b.y"][ev % 2]
    call = env.build_call(tool, [("k", "1")])
    for c in range(2):
        rows.append(dict(example_id=f"t{ev}__s42|s0|c{c}", event_id=f"t{ev}__s42|s0",
                         task_id=f"t{ev}", depth=0.3 + 0.4 * c, split=split, tool=tool,
                         method="cgen", target=call,
                         score=None, label_pred=None, logits=None,
                         text_pred=call if ev % 4 else env.build_call(tool, [("k", "2")]),
                         gen_tokens=7))
probe_output.write(tdir / "predictions.parquet", pl.DataFrame(rows))
(tdir / "meta.json").write_text(json.dumps(
    {"stage": "train", "key": TK2, "upstream": {"build": "cccccccccccc"},
     "stage_extra": {"labels": None}}))
(edir / "settings.yaml").write_text(f"""
data: {{env: appworld, instructions: v1}}
probe: {{method: cgen, tuning: full}}
eval: {{risk: [0.10, 0.05], theta_grid: [0.5, 0.9, 0.975], bootstrap: 50,
        bootstrap_seed: 42, theta_from: 'train_probe/ctool_fixture'}}
_stage: eval
_key: {EK2}
_upstream: {{train: {TK2}, theta_from.eval: bbbbbbbbbbbb}}
_versions: {{}}
_debug: true
_commit: deadbeef
_resolved: {{}}
""")
r = subprocess.run([sys.executable, "-m", "eval.methods.cgen", "--run-dir", str(edir)])
assert r.returncode == 0, r.returncode
rep = json.loads((edir / "probe_report.json").read_text())
print("generator fields:", sorted(rep))
assert rep["probe_kind"] == "generator" and rep["labels"] is None
assert rep["theta_from"] == "bbbbbbbbbbbb"
assert set(rep["theta_used"]) == {"0.1", "0.05"} and set(rep["exact"]) == {"0.1", "0.05"}
e = rep["exact"]["0.05"]; print("exact@0.05 =", e)
assert e["n"] == 10 and e["tool_ok"] == 1.0 and e["params_all_ok"] == 0.75
assert not (edir / "fires.parquet").exists()          # a generator writes no second file
print("A6 ok")
PY
```

Expected: `A6 ok`, exit 0; `exact@0.05` showing `n: 10`, `tool_ok: 1.0`,
`params_all_ok: 0.75`, `full_call_ok: 0.75` (the 10 test events fire, and one in
four carries the wrong argument). The same script with `cparam` substituted (the
`target` becomes `env.build_call(...)` with the `tool + "("` prefix stripped and
`method` becomes `cparam`) must give `tool_ok == 1.0` from the fired
`label_pred`.

### A7. `match` is callable from the train side, with the environment

```bash
external/probe-env/bin/python - <<'PY'
import sys; sys.path.insert(0, ".")
from data.environments import open_env
from eval.methods import ctool, cgen, cparam
env = open_env("appworld")
assert ctool.match("apis.a.x", "apis.a.x", None) is True
assert ctool.match("apis.a.x", "apis.b.y", None) is False
good = env.build_call("apis.a.x", [("k", "1")])
bad  = env.build_call("apis.a.x", [("k", "2")])
assert cgen.match(good, good, env) == {"tool_ok": True, "params_all_ok": True, "full_call_ok": True}
assert cgen.match(bad, good, env)["params_all_ok"] is False
assert cgen.match("not a call at all", good, env) == {"tool_ok": False, "params_all_ok": False, "full_call_ok": False}
# a no-argument target with a spurious generated argument is wrong (errata E3)
none0 = env.build_call("apis.a.x", [])
assert cgen.match(good, none0, env)["params_all_ok"] is False
# cparam takes two whole calls and returns the same three keys
assert cparam.match(good, good, env)["params_all_ok"] is True
print("A7 ok")
PY
```

Expected: `A7 ok`, exit 0.

### A8. `score_run` end to end, on a fixture built in the command

```bash
external/probe-env/bin/python - <<'PY'
import json, subprocess, sys, time; sys.path.insert(0, ".")
from experimental_settings import schema
from data import trajectory_record
from data.environments import open_env, requested_pairs
env = open_env("appworld")
SK, BK, RK = "1111aaaa1111", "2222bbbb2222", "3333cccc3333"
sdir = schema.run_dir_of("sample", SK, debug=True)
bdir = schema.run_dir_of("sample", BK, debug=True)
rdir = schema.run_dir_of("score",  RK, debug=True)
for d in (sdir, bdir, rdir): (d / "records").mkdir(parents=True, exist_ok=True)
triples = requested_pairs(env, ["train"], None, 2, [42])
print("requested:", triples)
for d, ok in ((sdir, True), (bdir, False)):
    for split, tid, seed in triples:
        w = trajectory_record.open_record(d / "records", tid, seed)
        w.row("meta", step=None, ts=time.time(), record_id=f"{tid}__s{seed}", stage="sample",
              env="appworld", task_id=tid, seed=seed, env_seed=100, split=split, arm="sample",
              instructions="v1", task_text="do it", agent_model="gptoss120b",
              generation="{}", inject=None, commit="deadbeef", run_key=d.name,
              owner_session="fixture", version=1)
        w.row("gen", step=0, ts=time.time(), reasoning="think", content="answer",
              usage={"in": 10, "out": 20}, wall_s=1.0, n_inject=0,
              discard={"chars": 0, "tokens": 0, "events": 0})
        w.row("env", step=0, ts=time.time(), action=env.build_call("apis.a.x", [("k", "1")]),
              result="ok", error_kind=None)
        w.row("final", step=0, ts=time.time(), steps=1, completed=True, abort=None,
              judge='{"success": %s}' % str(ok).lower(), success=ok,
              tokens_in=10, tokens_out=20, wall_s=2.0, finished_at=time.time())
        w.close()
for d, k in ((sdir, SK), (bdir, BK)):
    (d / "settings.yaml").write_text(f"""
data: {{env: appworld, instructions: v1}}
models: {{agent: gptoss120b}}
generation: {{temperature: 1.0, top_p: null, max_step_tokens: 8192}}
sample: {{split: [train], seeds: [42], tasks: null, n_tasks: 2, max_steps: 30}}
_stage: sample
_key: {k}
_upstream: {{}}
_versions: {{}}
_debug: true
_commit: deadbeef
_resolved: {{}}
""")
(rdir / "settings.yaml").write_text(f"""
data: {{env: appworld, instructions: v1}}
sample: {{split: [train], seeds: [42], tasks: null, n_tasks: 2, max_steps: 30}}
score: {{baseline: 'baseline/plain', by_seed: true}}
_stage: score
_key: {RK}
_upstream: {{sample: {SK}, baseline.sample: {BK}}}
_versions: {{}}
_debug: true
_commit: deadbeef
_resolved: {{}}
""")
r = subprocess.run([sys.executable, "-m", "eval.score_run", "--run-dir", str(rdir)])
assert r.returncode == 0, r.returncode
rep = json.loads((rdir / "run_report.json").read_text())
print("score keys:", sorted(rep))
assert rep["scored_stage"] == "sample" and rep["n_pairs"] == 2
assert rep["run"]["success"] == 1.0 and rep["baseline"]["success"] == 0.0
assert rep["paired"]["n"] == 2 and rep["paired"]["delta_success"] == 1.0
assert rep["spec"]["n"] == 0 and rep["by_seed"]["42"]["n_records"] == 2
d = json.loads((rdir / "done.json").read_text())
assert d["stage"] == "score" and d["report"] == "report.md"
assert (rdir / "report.md").exists() and not (rdir / "consumed.json").exists()
print("A8 ok")
PY
```

Expected: `A8 ok`, exit 0. Then the two refusals, each a non-zero exit with the
named reason on stderr:

```bash
# same-setup gate: change the baseline's generation section and rerun
external/probe-env/bin/python - <<'PY'
import sys, pathlib; sys.path.insert(0, ".")
from experimental_settings import schema
p = schema.run_dir_of("sample", "2222bbbb2222", debug=True) / "settings.yaml"
p.write_text(p.read_text().replace("temperature: 1.0", "temperature: 0.7"))
PY
external/probe-env/bin/python -m eval.score_run --run-dir "$(external/probe-env/bin/python -c "import sys;sys.path.insert(0,'.');from experimental_settings import schema;print(schema.run_dir_of('score','3333cccc3333',debug=True))")" ; echo "exit=$?"
```

Expected: a message naming both run directories and `generation.temperature`,
`exit=1`.

```bash
# baseline completeness gate: delete one baseline record and rerun
external/probe-env/bin/python - <<'PY'
import sys; sys.path.insert(0, ".")
from experimental_settings import schema
d = schema.run_dir_of("sample", "2222bbbb2222", debug=True) / "records"
p = sorted(d.glob("*.jsonl"))[0]; p.unlink(); print("deleted", p.name)
PY
```

then the same `eval.score_run` command: expected a message naming the missing
`(task_id, seed)` pair, `exit=1`.

### A9. `method_table`

```bash
external/probe-env/bin/python - <<'PY'
import sys; sys.path.insert(0, ".")
from eval import method_table
md = method_table.table()
print(md)
assert md.splitlines()[0].startswith("#")
assert "| backbone | method | risk |" in md
PY
echo "exit=$?"
```

Expected: a markdown table printed (its body may be empty while the registry
holds no eval row), `exit=0`. With the A4 fixture's row present in
`jobs/runs.jsonl`, the table must carry one line per `(backbone, method, risk)`
with `runs 1` and no `±`.

### A10. `selfcheck` lines that apply to these files (8.6)

```bash
python3 run.py selfcheck 2>&1 | tail -20; echo "exit=${PIPESTATUS[0]}"
```

Expected once `run.py` exists on the branch: `exit=0`, and no line naming a file
under `eval/`. The checks that bite here are: every `eval/` file imported under
every interpreter of the `venvs:` map; one integer `VERSION` line in the five
stage files; `PROBE_KIND` in `eval/methods/<m>.py` equal to the one in
`train/methods/<m>.py`; every annotation line in `README.md` matching the real
import graph; every axis value of `probe.method` having a file under
`eval/methods/`; and no `/home/` or `/net/` path in code outside `constants/`
(the fixtures above reach the outputs root through `schema.run_dir_of`, never by
a literal, and they live in the acceptance command, not in the code).

---

## 4. Acceptance, GPU or cross-host — for the main session

No `eval/` file touches a GPU: the tree's own line forbids it and A2 proves it.
Three items still belong to the main session because an implementer may not do
them.

- **P0 (prerequisite, not GPU, but an install the implementer may not run):**
  ```bash
  uv pip install --python external/appworld/venv/bin/python numpy
  external/appworld/venv/bin/python -c "import numpy, polars; print(numpy.__version__, polars.__version__)"
  ```
  Must print a NumPy version and `1.44.2`. Without it A1 fails for every `eval/`
  file under the appworld interpreter, because `venv: any` includes NumPy
  (contracts, "One precondition on the venvs", 9(a)#15).
- **G1 (needs a GPU upstream):** the first real classifier eval, over a real
  `train` run's `predictions.parquet`:
  ```bash
  python3 run.py train_probe <ctool setting> eval --debug
  python3 run.py where train_probe <ctool setting> eval
  ```
  Must show `probe_report.json` with a `temperature` between 0.5 and 5, a
  `chosen` entry per risk target, `frozen` numbers whose `n` equals the test
  event count printed by the train run's `done.json` `counts`, and a
  `fires.parquet` whose `event_id` values are a subset of the prediction frame's.
- **G2 (needs G1):** the generator eval against it:
  ```bash
  python3 run.py train_probe <cgen setting> eval --debug
  python3 run.py table train_probe
  ```
  Must show `exact` numbers with the same `n` as the classifier's `frozen` `n` at
  that risk, and a table row per `(backbone, method, risk)`.
- **G3 (needs a GPU upstream):** the first real `score` run over an `inject` run
  and its `sample` baseline:
  ```bash
  python3 run.py inject <inject setting> score --debug
  ```
  Must show `run_report.json` with `spec.n` equal to the `spec` row count of the
  inject records and `paired.n` equal to the requested pair count.

---

## 5. Tickets

### T-EVAL-1 — the eval library and the classifier metric

- **Files:** `eval/utils/probe_eval.py`, `eval/methods/ctool.py` (new);
  `README.md` (two lines).
- **What to do:** sections 1.1 and 1.2 above, in that order. Copy the four
  signatures of 1.1 and the four of 1.2 exactly. The report format is contracts
  1.4 (both shapes' field tables and `fires.parquet`'s column table); the driver
  contract is 2.6 ("The eval hook" table and "Who owns what, on both sides"); the
  gates are 2.5's four eval bullets; the prediction columns are 1.3. Port
  `fit_temperature`, the first-crossing `replay`, `agg`, `bootstrap` and the
  `chosen` rule from the legacy lines named in 1.1 and 1.2, and drop everything
  those two entries list as not ported. `fit_temperature` is a NumPy 1-D
  minimiser (errata E4), not torch.
- **Acceptance:** A1, A2, A3, A4, A5 (and A10 when `run.py` exists).
- **Needs from other folders:** `experimental_settings/schema.py`
  (`load_frozen`, `run_dir_of`, the `Setting`); `data/probe_output.py`
  (`read`, `write`, `SCHEMA`, `VERSION`); `jobs/registry.py`
  (`beat`, `Heartbeat.emit`, `Heartbeat.finish`, `write_done`).

### T-EVAL-2 — the two generator metrics

- **Files:** `eval/methods/cgen.py`, `eval/methods/cparam.py` (new);
  `README.md` (two lines).
- **What to do:** sections 1.3 and 1.4 above. The two files do not import each
  other; the comparison body is written twice on purpose (the tree's
  `eval/methods/` line). `match`'s signature and its three-key return are 2.6 and
  errata E7; the generator report shape, the `theta_used` / `exact` null rule and
  cparam's `tool_ok` rule are 1.4. Drop the `noparam` short-circuit (errata E3)
  and state it in the module docstring.
- **Acceptance:** A1, A2, A3, A6, A7.
- **Needs from other folders:** `eval/utils/probe_eval.py` (T-EVAL-1);
  `data/environments/__init__.py` (`open_env`, and the environment's
  `split_args`, `build_call`); `data/probe_output.py`;
  `experimental_settings/schema.py`; `jobs/registry.py` (through `probe_eval`).

### T-EVAL-3 — the run scorer

- **Files:** `eval/score_run.py` (new); `README.md` (one line).
- **What to do:** section 1.5 above. The record columns are 1.1's table; the pair
  list and its projection are 2.3; the two gates are 2.5's `score` bullets; the
  heartbeat unit and piece index are 8.4; `done.json` is 1.5 and 8.0. Port the
  summary of `legacy/pipeline/inject/score_live.py:111-216`, replacing
  `success_of` with the declared `final.success` column and `first_call` /
  `norm_call` with `env.split_args` / `env.build_call`.
- **Acceptance:** A1, A2, A3, A8.
- **Needs from other folders:** `experimental_settings/schema.py`
  (`load_frozen`, `run_dir_of`); `data/trajectory_record.py` (`open_record`,
  `Writer.row`, `Writer.close`, `read_dir`, `done_pairs`);
  `data/environments/__init__.py` (`open_env`, `requested_pairs`, `env.tasks`,
  `env.split_args`, `env.build_call`); `jobs/registry.py` (`beat`, `write_done`).

### T-EVAL-4 — the matrix table

- **Files:** `eval/method_table.py` (new); `README.md` (one line).
- **What to do:** section 1.6 above. One function, `table(workflow=None,
  out=None) -> str` (8.6). No `__main__`, no `VERSION`. Resolve each cell from the
  registry row's `diff` plus the schema defaults and never from a `settings.yaml`
  (errata E8); one row per risk target (errata E9); PENDING for a row whose
  directory has no report.
- **Acceptance:** A1, A2, A3, A9.
- **Needs from other folders:** `eval/utils/probe_eval.py` (`read_report`,
  T-EVAL-1); `jobs/registry.py` (`ls`, with the start row's `stage`, `key`,
  `dir`, `diff`, `parent`, `swept` on each folded row);
  `experimental_settings/schema.py` (the defaults for `models.probe` and
  `probe.method`).

---

## 6. Contract errata settled here

Appended verbatim to `.scratch/from-zero/contract-errata.md`.

- **E1 — Part 0.2 (`eval/utils/probe_eval.py` reads) / 2.5:** the generator-eval
  build-key gate is stated over "its own and the referenced eval run's train
  `meta.json`", with no path from this run to the referenced eval's *train* key →
  the build reads the referenced eval run's own `meta.json` `upstream["train"]`
  first, then that train run's `meta.json` `upstream["build"]`, both located with
  `run_dir_of(..., debug=False)`.
- **E2 — Part 1.3:** the prediction row carries no cut index, while the
  first-crossing rule needs an order within an event → cuts are ordered by `depth`
  ascending, tie-broken by `example_id` ascending.
- **E3 — Part 1.4:** "the three exact-match tiers are today's", and today's
  `params_all_ok` is true for every event whose ground truth has no arguments,
  whatever was generated (`eval_causal_call.py:401`, `eval_causal_param.py:284`)
  → the build drops that short-circuit and scores the union count
  (`n == 0 or ok == n`), so a spurious argument on a no-argument call is wrong.
- **E4 — Part 1.4 (`temperature`):** the fit method is unstated and today's is
  torch LBFGS, which `venv: any` forbids → `probe_eval.fit_temperature` minimises
  the mean NLL over `log T` with NumPy: a grid of 81 points over `[-4, 4]` then a
  golden-section refinement inside the winning cell to a tolerance of `1e-6`.
- **E5 — Part 1.4 (`ci`):** the interval's shape is unstated → `ci` is a dict from
  statistic name to a `[lo, hi]` pair; `bootstrap_ci(df, group, stat, *, n, seed)`
  resamples the distinct `task_id` values with replacement `n` times using
  `numpy.random.default_rng(seed)` and takes today's sorted-index bounds,
  `v[int(n*0.025)]` and `v[int(n*0.975)]`, rounded to 4.
- **E6 — Part 1.4 (`n_events`):** "events per split" names no frame → distinct
  `event_id` per `split` of the prediction frame the method was handed.
- **E7 — Part 2.6 (`match`):** the return shape is `bool | dict[str, bool]` and
  cparam's is unstated → cparam's `match` returns the same three-key dict cgen's
  does, and `report` uses only its `params_all_ok`.
- **E8 — Part 0.2 (`eval/method_table.py` reads `jobs/runs.jsonl`) / 8.0:** the
  registry offers no raw-row reader → `table` calls `registry.ls(workflow)` and
  the folded row must carry the start row's `stage`, `key`, `dir`, `diff`,
  `parent` and `swept`.
- **E9 — Part 8.6 (`run.py table`):** the risk tier is unstated and today's is a
  fixed 0.05 → one table row per `(backbone, method, risk target)`, every risk in
  the report, and the cell is `mean ± sample standard deviation` over the group's
  runs, the bare value for a group of one.
- **E10 — Part 0.1 (`venv: any`) and the venvs precondition:** NumPy is absent
  from `external/appworld/venv` → the `any` import test for `eval/` runs over the
  three interpreters of `constants/path_datasets.yaml`'s `venvs:` map after NumPy
  is installed there (a main-session prerequisite); the system `python3` (3.10,
  no NumPy) is not in that map and is not part of the check.
- **E11 — Part 1.5 (`done.json.metrics`):** the key names are unstated → `eval`
  writes `<stat>@<risk>` (`coverage@0.05`, `trig_acc@0.05`, `earliness@0.05`,
  `wrong_spec@0.05` for a classifier; `tool_ok@<risk>`, `params_all_ok@<risk>`,
  `full_call_ok@<risk>` for a generator), and `score` writes `success`,
  `base_success`, `delta_success`, `tokens_out`, `spec_exec_ok`,
  `spec_tool_agree`, `spec_call_agree`, `n_records`; null-valued entries are
  omitted.
- **E12 — Part 0.2 (`eval/utils/probe_eval.py` imports):** the annotation line
  does not carry `data/__init__.py`, so `write_frame` is unreachable → `probe_eval`
  writes `probe_report.json` and `fires.parquet` itself, with `json` and
  `polars.write_parquet`, each through a temporary name in the same directory and
  a rename, mirroring `write_frame`'s rule.
- **E13 — Part 1.4 / 2.6:** `risk_targets` and `n_events` are fields of both
  report shapes but are not in the identity block `probe_eval.run` assembles →
  the method's `report` hook returns them, and only the eight names of
  `IDENTITY_FIELDS` are refused.
