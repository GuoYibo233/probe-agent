# 10 the generator metrics, the run scorer and the matrix table

Status: ready-for-agent
Blocked by: 02, 03, 04, 05, 08
Spec: .scratch/from-zero/spec.md (sections 2, 3, 4, 5, 6, 7)

## What to do

Four files, the rest of `eval/`. Contracts 1.4 (the generator report shape), 2.6
(the eval hook), 2.5 (the `score` gates), 2.3 (the pair list), 1.1 (the record
columns) and 8.6 (`run.py table`) are the specification.

```
eval/methods/cgen.py     venv any   VERSION = 1, PROBE_KIND = "generator"
  imports: eval/utils/probe_eval.py, data/environments/__init__.py (open_env); [polars, numpy]
  used by: train/methods/cgen.py (its match function)
eval/methods/cparam.py   venv any   VERSION = 1, PROBE_KIND = "generator"
  imports: eval/utils/probe_eval.py, data/environments/__init__.py (open_env); [polars, numpy]
  used by: train/methods/cparam.py (its match function)
eval/score_run.py        venv any   VERSION = 1
  imports: experimental_settings/schema.py, data/trajectory_record.py,
           data/environments/__init__.py (open_env for split_args and build_call, and
           requested_pairs), jobs/registry.py; [polars]
  used by: none (program)
  writes:  run_report.json, report.md, heartbeat, done.json
eval/method_table.py     venv any   NO VERSION, no __main__, not a stage
  imports: experimental_settings/schema.py, jobs/registry.py, eval/utils/probe_eval.py
  used by: run.py (the table subcommand, 8.6)
README.md                your four lines only
```

**The two method files do not import each other.** The comparison body is written
twice on purpose (the tree's `eval/methods/` line).

### 1. `eval/methods/cgen.py` (contracts 1.4, 2.6)

```python
VERSION = 1
PROBE_KIND = "generator"

def match(pred: str, target: str, env) -> dict[str, bool]      # 2.6
def report(pred_df, cfg, ref, labels) -> tuple[dict, None]     # 2.6
def main(run_dir: Path) -> None    # one line: probe_eval.run(run_dir, sys.modules[__name__])
```
plus `if __name__ == "__main__":` parsing exactly `--run-dir`.

**`match`** returns `{"tool_ok", "params_all_ok", "full_call_ok"}` and is the one
comparison `train/methods/cgen.py`'s `validate` also calls:

1. `t = env.split_args(target)`; **raise**, naming the target, when it is None —
   the build gate of 2.5 makes a non-round-trippable `call` impossible, so a
   failure here is a defect, not data.
2. `p = env.split_args(pred)`; when None, return all three False (the port of
   `parse_call`'s `parse_fail`, `eval_causal_call.py:172-203`, now the
   environment's business).
3. `tool_ok = p.tool == t.tool`.
4. `params_all_ok`: the union-by-key comparison of `eval_causal_call.py:205-226`
   over the two argument lists — group each side's `(key, value)` pairs by key in
   call order, walk `list(truth_keys) + [k for k in gen_keys if k not in
   truth_keys]`, add `max(len(tv), len(gv))` instances and count position-by-
   position equality; `params_all_ok = (n_instances == 0) or (n_ok ==
   n_instances)`.
   **Decision already made (errata): the `noparam` short-circuit of
   `eval_causal_call.py:401` is dropped.** Today `params_all_ok` is true for
   every event whose ground truth has no arguments, whatever was generated; the
   build scores the union count, so a spurious argument on a no-argument call is
   **wrong**. State this in the module docstring.
5. `full_call_ok = tool_ok and params_all_ok`.

Both sides' values arrive already normalised, because `env.split_args` is the one
parser; there is no second `norm()` and no loose/strict pair.

**`report`:**

1. `env = open_env(cfg.data.env)` (2.1 puts `data` in this stage's projection).
   `ref` must be a `(fields, fires)` tuple and `labels` must be None; raise
   otherwise.
2. `test = pred_df.filter(split == "test")` (1.4 pins the split).
3. Per risk in `cfg.eval.risk`:
   `theta_used[str(risk)] = ref_fields["chosen"][str(risk)]`. When it is null,
   `exact[str(risk)] = {"tool_ok": None, "params_all_ok": None, "full_call_ok":
   None, "n": 0, "ci": None}` and the eval does **not** refuse (1.4).
4. Otherwise join `test` to `ref_fires.filter(risk == risk, split == "test")` on
   `example_id` — the first-crossing rule is executed **once**, by ctool, and
   everyone else joins — call `match(row.text_pred, row.target, env)` per joined
   row, and report the three rates rounded to 4 with `n` = joined rows, plus
   `ci = probe_eval.bootstrap_ci` over those rows grouped by `task_id` for the
   same three rates.
5. `n_events = {split: distinct event_id}` over `pred_df`.
6. Returns `({"risk_targets": cfg.eval.risk, "theta_used": theta_used,
   "exact": exact, "n_events": n_events}, None)` — a generator writes **no**
   `fires.parquet`.

Legacy sources: `legacy/pipeline/eval/eval_causal_call.py:100-125` (`replay_fire`,
now ctool's and reached by the join), `:129-226` (`norm` / `split_named_raw` /
`parse_call` / `match_params`, replaced by `env.split_args` plus the comparison
above), `:379-410` (`score_points`), `:700-745` (the report fields, restricted to
1.4's list).
**Not ported:** the generation half (`:231-254`) and the model load (`:657-666`)
— the text is in `prediction.text_pred`; the whole self-fire block (`:262-489`);
the readonly arm and its fuses (`:505-518, 578-607, 644-652`); the three-way
`--data` cross-check (`:566-577`), replaced by the shared-build-key gate of 2.5;
`--overlong` filtering (`:672-694`); `--limit` (`:695-696`); the
`params_all_ok_strict` / `param_acc_loose` / `param_acc_strict` tiers,
`exact_call_ok`, `parse_fail_rate`, `noparam_rate`, the `by_tool` breakdown and
the `samples` list (`:401-410, 710-745`). Strictness in particular **cannot** be
ported: the raw, un-normalised argument strings do not survive into `prediction`,
and `example.args` is never read by `eval/`.

### 2. `eval/methods/cparam.py` (contracts 1.4, 2.6)

Same three names and the same `main`. **`match` is handed two whole calls**
(2.6): its two callers — this file's `report` and `train/methods/cparam.py`'s
`validate` — prepend `tool + "("` (from the `tool` column their frame carries) to
the predicted and the target argument string before calling it, because an
argument string alone cannot be parsed by `env.split_args`. **The returned dict
carries the same three keys cgen's does** (errata; 2.6 leaves cparam's return
shape unstated), and `report` uses only its `params_all_ok`.

`report`'s steps 1-3 and 5-6 are cgen's; step 4 differs, per 1.4:

- `tool_ok` is `fires.label_pred == prediction.tool` on the joined row — the
  classifier's fired label against the true tool the prediction row carries.
- `params_all_ok` is
  `match(tool + "(" + text_pred, tool + "(" + target, env)["params_all_ok"]`,
  where `tool` is the prediction row's `tool` column; the returned `tool_ok` of
  that call is ignored (both sides carry the same prefix, so it is always true).
- `full_call_ok = tool_ok and params_all_ok`.
- `ci` over the same three rates, grouped by `task_id`.

Legacy sources: `legacy/pipeline/eval/eval_causal_param.py:93-119` (`replay_fire`,
now the join), `:123-253` (parse and compare), `:257-292` (`score_points`; the
`given + "(" + gen` rebuild is the rule 1.4 keeps), `:296-328` (`block`,
restricted to 1.4's field list).
**Not ported:** the two-convention structure — legacy runs the same threshold
points twice, once with the ground-truth tool in the prompt and once with ctool's
argmax, and the matrix reads only the second (`eval_causal_param.py:12-21`,
`summarize_matrix.py:59-69`). This tree generates once, at training time, at every
cut row, so the report has one block and the loss from the classifier naming the
wrong tool enters through `tool_ok = fires.label_pred == prediction.tool`. Also
not ported: the generation half (`:225-249`) and the model load; the readonly arm;
`given_tool_ok`, `exact_call_ok`, `parse_fail_rate`, `noparam_rate`,
`params_all_ok_strict`, `param_acc_loose`, `param_acc_strict`, `by_tool`,
`samples`.

### 3. `eval/score_run.py` (contracts 2.5, 2.3, 1.1)

```python
VERSION = 1
def main(run_dir: Path) -> None     # 2.1's program column: eval.score_run, main(run_dir)
```
plus `if __name__ == "__main__":` parsing exactly `--run-dir`.

**What `main` does, in order.**

1. `cfg = schema.load_frozen(run_dir)`; `env = open_env(cfg.data.env)`;
   `scored = "inject" if "inject" in cfg._upstream else "sample"` (1.5's
   `_upstream` naming: a `score` run's map is `{inject, baseline.sample}` or
   `{sample, baseline.sample}`).
2. `sec = cfg.inject if scored == "inject" else cfg.sample`;
   `triples = requested_pairs(env, sec.split, sec.tasks, sec.n_tasks, sec.seeds)`;
   `pairs = [(t, s) for _, t, s in triples]`.
3. `scored_dir = schema.run_dir_of(scored, cfg._upstream[scored], debug=cfg._debug)`;
   `base_dir = schema.run_dir_of("sample", cfg._upstream["baseline.sample"], debug=False)`
   when `cfg.score.baseline` is set (a reference is located **without** the debug
   overlay).
4. **Same-setup gate** (2.5): `schema.load_frozen` on both upstream run
   directories and compare their `data`, `models.agent` and `generation` sections
   field by field; refuse, naming both directories and the first field that
   differs.
5. **Baseline completeness gate** (2.5): `done_pairs(base_dir, pairs)` must cover
   every pair; refuse naming the missing pairs. **`done_pairs` takes the run
   directory**, not `<run_dir>/records` (errata).
6. `hb = registry.beat(run_dir, 0)`, `hb.emit(0, len(pairs), "task")` (8.4's unit
   for `score` is `task`), then one beat per task read.
7. `df = trajectory_record.read_dir(scored_dir, pairs)`; `bdf = read_dir(base_dir,
   pairs)` when paired. **Both gates and both reads are stated over this pair
   list**, never over the directory (2.5).
8. Compute, with the columns of 1.1:
   - per record: `final.success`, `final.abort`, `final.steps`,
     `final.completed`, `final.tokens_in`, `final.tokens_out`, `final.wall_s`;
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
   — every rate rounded to 4, `null` when the denominator is 0.
10. `report.md`: a rendering of the above — the summary table, then one line per
    task (`task, seed, success, base_success, steps, n_inject, tokens_out`).
11. `registry.write_done(run_dir, stage="score", key=cfg._key,
    commit=cfg._commit, counts={"records": …, "tasks": …, "seeds": …,
    "specs": …}, versions=cfg._versions, metrics=<flat>, report="report.md")`;
    `hb.finish()`. **No `consumed.json`**: 1.5 gives it three writers and `score`
    is not one.

**`done.json`'s `metrics` (errata):** `score` writes `success`, `base_success`,
`delta_success`, `tokens_out`, `spec_exec_ok`, `spec_tool_agree`,
`spec_call_agree`, `n_records`, with null-valued entries omitted.

Legacy sources: `legacy/pipeline/inject/score_live.py:57-108` (`first_call`,
`norm_call`, `success_of`, `read_live`, `read_base`) and `:111-216` (the whole
summary).
**Not ported:** `success_of`'s two-shape parse (`:70-88`) — 1.1 declares
`final.success` as a boolean column of its own and `eval/score_run.py` reads it
and never the JSON; `first_call` / `norm_call` (`:54-67`) — replaced by
`env.split_args` and `env.build_call`; the `live_*.jsonl` glob and the
filename-derived task id (`:120-123`) — `read_dir(dir, pairs)` is the reader and
the id chain is Part 1's; the `task_error` prefix convention (`:162,168-170`) —
any non-null `abort` is a finished task, counted in `n_abort`; the `format` field
fallback for pre-2026-09-12 runs (`:124`); the per-task `base` lookup by file
name (`:133-141`).

### 4. `eval/method_table.py` (contracts 8.6)

```python
def table(workflow: str | None = None, out: Path | None = None) -> str    # 8.6
```
returns the rendered markdown and also writes it when `out` is given. **No
`__main__`, no run directory, and no `VERSION`** — 0.2 gives the other five eval
files "carries VERSION" and gives this one none, and the stage table never names
it.

1. `rows = [r for r in registry.ls(workflow, debug=False) if r["stage"] == "eval"]`.
   **Decision already made (errata):** the registry offers no raw-row reader, so
   `table` calls `registry.ls(...)` and the folded row carries the start row's
   `stage`, `key`, `dir`, `diff`, `parent` and `swept`.
2. Per row, resolve the cell **without opening any `settings.yaml`**: `backbone`
   is `diff["models"]["probe"]` when present and the schema default for
   `models.probe` otherwise; `method` is `diff["probe"]["method"]` when present
   and the schema default otherwise (`diff` is `settings_diff.yaml` as JSON, 8.1,
   so a default-valued field is absent from it).
3. Group the sweep children: the group key is `row["parent"]` when it is set and
   `row["setting"]` otherwise (5.5).
4. Per row, `read_report(Path(row["dir"]))`; a directory with no
   `probe_report.json` is `PENDING` (legacy's convention,
   `summarize_matrix.py:36-39`) and contributes no number.
5. **One table row per `(backbone, method, risk target)`** — every risk in the
   report, never one tier chosen silently (errata; 8.6 leaves the tier unstated
   and today's is a fixed 0.05). Columns:
   `backbone | method | risk | n | coverage | trig_acc | earliness | wrong_spec |
   tool_ok | params_all_ok | full_call_ok | runs | status`. A classifier report
   fills the four `frozen` columns from `frozen[str(risk)]`, a generator report
   the three `exact` columns from `exact[str(risk)]`, and the other side prints
   `-` (`summarize_matrix.py:31-32`'s `fmt`).
6. Each cell shows `mean ± spread` over the group's runs, spread being the sample
   standard deviation (ddof 1), and the **bare value when the group has one run**.
   `runs` is the group size; `status` is `OK` when every member has a report and
   `PENDING n/m` otherwise.

Legacy source: `legacy/pipeline/eval/summarize_matrix.py:31-73` (`fmt`,
`read_cell`, the PENDING convention) and `:76-131` (the rendering).
**Not ported:** the `CELLS` / `REPORT_OF` literal cell list and the fixed
`c1_<model>_<cell>` run-id naming (`:24-27, 88-91`) — the registry's rows are the
inventory now; the `mtool` and `mext` cells; the fixed `--models` list and
`--prefix` (`:81-83`); the single `RISK = "0.05"` tier (`:28`); the per-model
test-scale and prior-baseline table (`:114-118`).

## Acceptance

Run from the repo root and paste the real output. `$PY` is
`/home/y-guo/reproduce/new1/external/probe-env/bin/python`.

**A1 — the `any` import test, over all six `eval/` files.**
```bash
for P in /home/y-guo/reproduce/new1/external/probe-env/bin/python \
         /home/y-guo/reproduce/new1/external/appworld/venv/bin/python \
         /home/y-guo/reproduce/new1/external/vllm-env/bin/python; do
  for M in eval.utils.probe_eval eval.methods.ctool eval.methods.cgen eval.methods.cparam eval.score_run eval.method_table; do
    $P -c "import importlib,sys; sys.path.insert(0,'.'); importlib.import_module('$M')" || echo "FAIL $P $M";
  done; done; echo "import test done"
```
Expected: no `FAIL` line, `import test done`, exit 0.

**A2 — no torch, no GPU anywhere in `eval/`.**
```bash
grep -rn "import torch\|from torch\|cuda\|transformers" eval/ ; echo "exit=$?"
```
Expected: no matches, `exit=1`.

**A3 — the literal lines.**
```bash
"$PY" - <<'PY'
import re, pathlib
for p in ["eval/utils/probe_eval.py","eval/methods/ctool.py","eval/methods/cgen.py",
          "eval/methods/cparam.py","eval/score_run.py"]:
    s = pathlib.Path(p).read_text()
    v = re.findall(r"(?m)^VERSION = (\d+)$", s)
    assert len(v) == 1, (p, v)
for p, k in [("eval/methods/ctool.py","classifier"),("eval/methods/cgen.py","generator"),
             ("eval/methods/cparam.py","generator")]:
    s = pathlib.Path(p).read_text()
    assert re.findall(r'(?m)^PROBE_KIND = "(\w+)"$', s) == [k], p
assert not re.findall(r"(?m)^VERSION = ", pathlib.Path("eval/method_table.py").read_text())
print("literals ok")
PY
```
Expected: `literals ok`, exit 0.

**A6a — the reference classifier eval this ticket's generators need.** This
ticket builds its own, it does not reuse ticket 08's: step 6 of `probe_eval.run`
locates a resolved reference with `run_dir_of(..., debug=False)`, so **a
referenced eval run and the train run it names are non-debug directories**, and
the referenced eval directory must carry a `meta.json` — the stage program never
writes one, `run.py` and `jobs/launch.py` do, and the generator's build-key gate
reads `upstream["train"]` out of it.
```bash
"$PY" - <<'PY'
import json, subprocess, sys, polars as pl; sys.path.insert(0, ".")
from experimental_settings import schema
from data import probe_output

TK0, EK0, BK0 = "4444dddd4444", "5555eeee5555", "cccccccccccc"
tdir = schema.run_dir_of("train", TK0, debug=False); tdir.mkdir(parents=True, exist_ok=True)
edir = schema.run_dir_of("eval",  EK0, debug=False); edir.mkdir(parents=True, exist_ok=True)
labels = ["apis.a.x", "apis.b.y"]
rows = []
for ev in range(20):                       # 20 events, 2 cuts each, 10 val / 10 test
    split = "val" if ev < 10 else "test"
    tool = labels[ev % 2]
    for c in range(2):
        rows.append(dict(
            example_id=f"t{ev}__s42|s0|c{c}", event_id=f"t{ev}__s42|s0",
            task_id=f"t{ev}", depth=0.3 + 0.4 * c, split=split, tool=tool,
            method="ctool", target=tool, score=0.9, label_pred=tool,
            logits=[3.0, 0.0] if tool == labels[0] else [0.0, 3.0],
            text_pred=None, gen_tokens=None))
probe_output.write(tdir / "predictions.parquet", pl.DataFrame(rows, strict=False))
(tdir / "meta.json").write_text(json.dumps(
    {"stage": "train", "key": TK0, "upstream": {"build": BK0},
     "stage_extra": {"labels": labels}}))
(edir / "settings.yaml").write_text(f"""
data: {{env: appworld, instructions: v1}}
probe: {{method: ctool, tuning: full}}
eval: {{risk: [0.10, 0.05], theta_grid: [0.5, 0.9, 0.975], bootstrap: 50,
        bootstrap_seed: 42, theta_from: null}}
_stage: eval
_key: {EK0}
_upstream: {{train: {TK0}}}
_versions: {{}}
_debug: false
_commit: deadbeef
_resolved: {{}}
""")
r = subprocess.run([sys.executable, "-m", "eval.methods.ctool", "--run-dir", str(edir)])
assert r.returncode == 0, r.returncode
# the meta.json a real run would carry, written here because no stage program writes it
(edir / "meta.json").write_text(json.dumps(
    {"stage": "eval", "key": EK0, "upstream": {"train": TK0}}))
f = pl.read_parquet(edir / "fires.parquet")
print("reference fires:", f.height, sorted(set(f["split"].to_list())))
assert f.filter(f["split"] == "test").filter(f["risk"] == 0.05).height == 10
print("A6a ok")
PY
```
Expected: `reference fires: 40 ['test', 'val']`, then `A6a ok`, exit 0.

**A6 — the two generator methods against that report.**
```bash
for M in cgen cparam; do
"$PY" - "$M" <<'PY'
import json, subprocess, sys, polars as pl; sys.path.insert(0, ".")
from experimental_settings import schema
from data import probe_output
from data.environments import open_env
name = sys.argv[1]
env = open_env("appworld")
EK0, BK0 = "5555eeee5555", "cccccccccccc"
TK2 = {"cgen": "dddddddddddd", "cparam": "6666ffff6666"}[name]
EK2 = {"cgen": "eeeeeeeeeeee", "cparam": "7777aaaa7777"}[name]
tdir = schema.run_dir_of("train", TK2, debug=True); tdir.mkdir(parents=True, exist_ok=True)
edir = schema.run_dir_of("eval",  EK2, debug=True); edir.mkdir(parents=True, exist_ok=True)
rows = []
for ev in range(20):
    split = "val" if ev < 10 else "test"
    tool = ["apis.a.x", "apis.b.y"][ev % 2]
    good = env.build_call(tool, [("k", "1")])
    bad  = env.build_call(tool, [("k", "2")])
    if name == "cparam":                    # the arguments alone, tool + "(" stripped
        good, bad = good[len(tool) + 1:], bad[len(tool) + 1:]
    wrong = ev % 4 == 0                     # ev 12 and 16 of the ten test events
    for c in range(2):
        rows.append(dict(example_id=f"t{ev}__s42|s0|c{c}", event_id=f"t{ev}__s42|s0",
                         task_id=f"t{ev}", depth=0.3 + 0.4 * c, split=split, tool=tool,
                         method=name, target=good,
                         score=None, label_pred=None, logits=None,
                         text_pred=bad if wrong else good, gen_tokens=7))
probe_output.write(tdir / "predictions.parquet", pl.DataFrame(rows, strict=False))
(tdir / "meta.json").write_text(json.dumps(
    {"stage": "train", "key": TK2, "upstream": {"build": BK0},
     "stage_extra": {"labels": None}}))
(edir / "settings.yaml").write_text(f"""
data: {{env: appworld, instructions: v1}}
probe: {{method: {name}, tuning: full}}
eval: {{risk: [0.10, 0.05], theta_grid: [0.5, 0.9, 0.975], bootstrap: 50,
        bootstrap_seed: 42, theta_from: 'train_probe/ctool_fixture'}}
_stage: eval
_key: {EK2}
_upstream: {{train: {TK2}, theta_from.eval: {EK0}}}
_versions: {{}}
_debug: true
_commit: deadbeef
_resolved: {{}}
""")
r = subprocess.run([sys.executable, "-m", f"eval.methods.{name}", "--run-dir", str(edir)])
assert r.returncode == 0, r.returncode
rep = json.loads((edir / "probe_report.json").read_text())
print(name, "generator fields:", sorted(rep))
assert rep["probe_kind"] == "generator" and rep["labels"] is None
assert rep["theta_from"] == EK0
assert set(rep["theta_used"]) == {"0.1", "0.05"} and set(rep["exact"]) == {"0.1", "0.05"}
e = rep["exact"]["0.05"]; print(name, "exact@0.05 =", e)
assert e["n"] == 10, e["n"]
assert e["tool_ok"] == 1.0, e["tool_ok"]
assert e["params_all_ok"] == 0.8, e["params_all_ok"]
assert e["full_call_ok"] == 0.8, e["full_call_ok"]
assert not (edir / "fires.parquet").exists()          # a generator writes no second file
print(name, "A6 ok")
PY
done
```
Expected: two `<name> A6 ok` lines, exit 0 each; `exact@0.05` showing `n: 10`,
`tool_ok: 1.0`, `params_all_ok: 0.8`, `full_call_ok: 0.8`. **The arithmetic**:
`wrong = ev % 4 == 0` over the ten test events `ev = 10..19` is true for `ev = 12`
and `ev = 16`, so two of the ten joined rows carry the wrong argument and the
three rates are `8/10`. `tool_ok` is `1.0` for cgen because the parsed tool of a
wrong-argument call is still the right tool, and for cparam because it is the
fired `label_pred` against the row's own `tool` column.

**Clean up after A6a and A6**: delete the six fixture directories at the end
(`shutil.rmtree`) and list the six keys — `4444dddd4444`, `5555eeee5555`
(non-debug), `dddddddddddd`, `eeeeeeeeeeee`, `6666ffff6666`, `7777aaaa7777`
(debug) — in your report, so the main session can confirm nothing fake is left
under the outputs root.

**A7 — `match` is callable from the train side, with the environment.**
```bash
"$PY" - <<'PY'
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
none0 = env.build_call("apis.a.x", [])
assert cgen.match(good, none0, env)["params_all_ok"] is False     # the dropped noparam short-circuit
assert cparam.match(good, good, env)["params_all_ok"] is True
print("A7 ok")
PY
```
Expected: `A7 ok`, exit 0.

**A8 — `score_run` end to end, on a record fixture the command builds.**
```bash
"$PY" - <<'PY'
import json, subprocess, sys; sys.path.insert(0, ".")
from experimental_settings import schema
from data import trajectory_record
from data.environments import open_env, requested_pairs
env = open_env("appworld")
SK, BK, RK = "1111aaaa1111", "2222bbbb2222", "3333cccc3333"
sdir = schema.run_dir_of("sample", SK, debug=True)
bdir = schema.run_dir_of("sample", BK, debug=True)
rdir = schema.run_dir_of("score",  RK, debug=True)
for d in (sdir, bdir, rdir): d.mkdir(parents=True, exist_ok=True)
triples = requested_pairs(env, ["train"], None, 2, [42])
print("requested:", triples)
for d, ok in ((sdir, True), (bdir, False)):
    for split, tid, seed in triples:
        w = trajectory_record.open_record(d, tid, seed)          # d is the RUN DIRECTORY
        # no record_id=: the writer stamps it, and passing a stamped column raises
        w.row("meta", stage="sample",
              env="appworld", task_id=tid, seed=seed, env_seed=100, split=split, arm="sample",
              instructions="v1", task_text="do it", agent_model="gptoss120b",
              generation="{}", inject=None, commit="deadbeef", run_key=d.name,
              owner_session="fixture")
        w.row("gen", step=0, reasoning="think", content="answer",
              usage={"in": 10, "out": 20}, wall_s=1.0, n_inject=0,
              discard={"chars": 0, "tokens": 0, "events": 0})
        w.row("env", step=0, action=env.build_call("apis.a.x", [("k", "1")]),
              result="ok", error_kind=None)
        w.row("final", steps=1, completed=True, abort=None,
              judge='{"success": %s}' % str(ok).lower(), success=ok,
              tokens_in=10, tokens_out=20, wall_s=2.0, finished_at=0.0)
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
score: {{baseline: 'baseline/gptoss_aw', by_seed: true}}
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
"$PY" -c "
import sys; sys.path.insert(0, '.')
from experimental_settings import schema
p = schema.run_dir_of('sample', '2222bbbb2222', debug=True) / 'settings.yaml'
p.write_text(p.read_text().replace('temperature: 1.0', 'temperature: 0.7'))"
"$PY" -m eval.score_run --run-dir "$("$PY" -c "import sys;sys.path.insert(0,'.');from experimental_settings import schema;print(schema.run_dir_of('score','3333cccc3333',debug=True))")" ; echo "exit=$?"
```
Expected: a message naming both run directories and `generation.temperature`,
`exit=1`. Then delete one baseline record file and rerun the same command:
expected a message naming the missing `(task_id, seed)` pair, `exit=1`.

**Clean up after A8**: delete the three fixture directories and name the keys
(`1111aaaa1111`, `2222bbbb2222`, `3333cccc3333`, all under `debug/`) in your
report.

**A9 — `method_table`.**
```bash
"$PY" - <<'PY'
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
holds no eval row), `exit=0`. With an eval row present in `jobs/runs.jsonl`, the
table must carry one line per `(backbone, method, risk)` with `runs 1` and no
`±`.

**This command must issue no `ssh`**, and that is itself part of the check:
`table()` goes through `registry.ls(...)`, which calls `live_sessions()` — one
`ssh` per host — only when the folded row set is non-empty (ticket 03, errata).
The ledger is empty in your worktree, so the call returns without touching a
host. If `A9` hangs or prints an ssh error, that short-circuit is missing: report
it as a ticket-03 defect and do not work around it. An implementer never runs
`ssh` (spec section 7).

### Selfcheck lines that apply later

`run.py selfcheck` (ticket 15) will check: every `eval/` file imports under every
interpreter of the `venvs:` map (A1); one integer `VERSION` in the five stage
files and none in `method_table.py` (A3); `PROBE_KIND` in `eval/methods/<m>.py`
equal to `train/methods/<m>.py`'s (ticket 13's files); every `README.md`
annotation line against the real import graph; every axis value of `probe.method`
having a file under `eval/methods/`; and no `/home/` or `/net/` path in code
outside `constants/`.

### GPU / main session — not yours

`M-E2` the generator eval against a real classifier eval:
`run.py train_probe cgen_q06 --debug` then `run.py table train_probe` must show
`exact` numbers with the same `n` as the classifier's `frozen` `n` at that risk,
and a table row per `(backbone, method, risk)`. `M-E3` the first real `score`
over an inject run and its `sample` baseline: `run_report.json` with `spec.n`
equal to the `spec` row count of the inject records and `paired.n` equal to the
requested pair count.

## Comments
