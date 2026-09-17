# 08 the eval library and the classifier metric

Status: ready-for-agent
Blocked by: 02, 03, 04
Spec: .scratch/from-zero/spec.md (sections 2, 3, 4, 5, 6, 7)

## What to do

Two files. Contracts 1.4 (the probe report, both shapes and `fires.parquet`), 2.6
("The eval hook" table and "Who owns what, on both sides"), 2.5 (the four eval
gates) and 1.3 (the prediction columns) are the specification; read 1.4 and 2.6
in full.

```
eval/utils/probe_eval.py   venv: any    VERSION = 1
  imports: experimental_settings/schema.py, data/probe_output.py, jobs/registry.py;
           [polars, numpy]        — and NOT data/__init__.py, NOT data/environments/
  used by: eval/methods/{ctool,cgen,cparam}.py, run.py (read_report), eval/method_table.py
  reads:   prediction (parquet), its own and the referenced eval run's train meta.json,
           the referenced probe report
  writes:  probe_report.json, fires.parquet, report.md, consumed.json, heartbeat, done.json

eval/methods/ctool.py      venv: any    VERSION = 1, PROBE_KIND = "classifier"
  imports: eval/utils/probe_eval.py; [polars, numpy]   — nothing else: no schema.py,
           no registry.py, no environment
  used by: train/methods/ctool.py (its match function)
  reads/writes: nothing; everything goes through probe_eval.py

README.md                  your two lines only
```

**No `torch`, no `cuda`, no `transformers` anywhere under `eval/`** — the tree's
own line, and A2 proves it. Every model call has already happened:
`train/utils/trainer.py`'s last step writes one prediction row per example row.

### 1. `eval/utils/probe_eval.py` (contracts 1.4, 2.6)

```python
VERSION = 1

FIRES_SCHEMA = {     # the fires.parquet column list of 1.4, in this order
    "risk": pl.Float32, "theta": pl.Float32, "split": pl.Utf8,
    "event_id": pl.Utf8, "example_id": pl.Utf8, "score": pl.Float32,
    "depth": pl.Float32, "label_pred": pl.Utf8,
}
IDENTITY_FIELDS = frozenset({"version", "method", "probe_kind", "stage_key",
                             "train_key", "theta_from", "commit", "labels"})

def run(run_dir: Path, method) -> None                                    # 2.6
def write_report(run_dir: Path, fields: dict, fires: DataFrame | None) -> None   # 1.4
def read_report(run_dir: Path) -> tuple[dict, DataFrame | None]           # 1.4
def fit_temperature(logits: "np.ndarray", y: "np.ndarray") -> float       # 1.4
def bootstrap_ci(df: DataFrame, group: str, stat, *, n: int, seed: int) -> dict[str, list[float]]
def softmax(logits: "np.ndarray", temperature: float) -> "np.ndarray"
```

**`run`, in order:**

1. `cfg = schema.load_frozen(run_dir)` (2.6). No method file calls it.
2. `hb = registry.beat(run_dir, 0)` and `hb.emit(0, total, "item")` before the
   work; `unit` is `item` for eval and the piece index is 0 (8.4).
3. `train_dir = schema.run_dir_of("train", cfg._upstream["train"], debug=cfg._debug)`
   — the same-setting upstream keeps the debug overlay.
4. `pred_df = probe_output.read(train_dir / "predictions.parquet")`. Raise, naming
   the values, when the frame's `method` column holds anything but
   `cfg.probe.method`.
5. `labels = json.load(train_dir/"meta.json")["stage_extra"]["labels"]` (1.3,
   8.3). `None` for a generator.
6. `kind = method.PROBE_KIND`. For `generator`:
   - `ref_eval_dir = schema.run_dir_of("eval", cfg._upstream["theta_from.eval"], debug=False)`
     — **a resolved reference is located without the debug overlay** (3.1).
   - Gate: `(ref_eval_dir/"done.json").exists()`, else refuse naming the directory.
   - `ref = read_report(ref_eval_dir)`.
   - Gate: `ref[0]["risk_targets"] == cfg.eval.risk`, else refuse naming both lists.
   - **The build-key gate** (2.5, errata): read `ref_eval_dir/"meta.json"` ->
     `upstream["train"]` -> `schema.run_dir_of("train", that, debug=False)` ->
     that run's `meta.json` -> `upstream["build"]`; refuse, naming both keys, when
     it differs from `json.load(train_dir/"meta.json")["upstream"]["build"]`.
     (2.5 states the gate over "its own and the referenced eval run's train
     `meta.json`" with no path from this run to the referenced eval's train key;
     this is the path.)
   For `classifier`: `ref = None`.
7. `fields, fires = method.report(pred_df, cfg, ref, labels)` (2.6).
8. Raise, naming the key, when `set(fields) & IDENTITY_FIELDS` is non-empty (1.4).
9. Merge the identity block (1.4): `version=VERSION`, `method=cfg.probe.method`,
   `probe_kind=kind`, `stage_key=cfg._key`, `train_key=cfg._upstream["train"]`,
   `theta_from=cfg._upstream.get("theta_from.eval")` (None for a classifier),
   `commit=cfg._commit`, `labels=labels`. **`risk_targets` and `n_events` are the
   method's**, not the identity block's (errata), and only the eight names of
   `IDENTITY_FIELDS` are refused.
10. `write_report(run_dir, fields, fires)`.
11. Write `report.md` (below).
12. Write `consumed.json` = `[{path, sha1, n_rows}]` (1.5) for the prediction
    parquet (`n_rows` = frame height) and, for a generator, the referenced
    `probe_report.json` (`n_rows: null`) and `fires.parquet` (its height).
13. `registry.write_done(run_dir, stage="eval", key=cfg._key, commit=cfg._commit,
    counts={"rows": <pred rows>, "events": <distinct event_id>, "fires": <fires rows or 0>},
    versions=cfg._versions, metrics=<flat, below>, report="report.md")`.
14. `hb.finish()`. **`run` appends no registry row** (2.6).

**Decision already made (errata):** `probe_eval` writes `probe_report.json` and
`fires.parquet` **itself**, with `json` and `polars.write_parquet`, each through
a temporary name in the same directory and a rename, mirroring `write_frame`'s
rule — 0.2's import line does not carry `data/__init__.py`, so `write_frame` is
unreachable from here. `write_report` writes the json with
`json.dumps(..., indent=1, ensure_ascii=False)`. `read_report` raises when the
json is missing, raises when its `version` is above this module's `VERSION`, and
returns `None` for the frame when no `fires.parquet` exists.

**`fit_temperature` (errata):** the fit method is unstated in 1.4 and today's is
torch LBFGS, which `venv: any` forbids. Minimise the mean NLL over `log T` with
NumPy: a grid of 81 points over `[-4, 4]`, then a golden-section refinement
inside the winning cell to a tolerance of `1e-6`. Deterministic.
Legacy source: `legacy/pipeline/eval/eval_tool.py:213-224`.

**`bootstrap_ci` (errata):** `ci` is a dict from statistic name to a `[lo, hi]`
pair. `bootstrap_ci(df, group, stat, *, n, seed)` resamples the **distinct
`task_id` values** with replacement `n` times using
`numpy.random.default_rng(seed)` and takes today's sorted-index bounds
`v[int(n*0.025)]` and `v[int(n*0.975)]`, rounded to 4. `stat` is a callable
taking a frame and returning a dict of statistic name to value.
Legacy source: `eval_tool.py:279-296`.

**`report.md`**: a title line with the stage key, method, probe kind and commit;
for a classifier, the fitted temperature and one line per risk target (`theta`,
`coverage (CI)`, `trig_acc (CI)`, `earliness (CI)`, `wrong_spec`, `n`); for a
generator, one line per risk target (`theta_used`, `tool_ok`, `params_all_ok`,
`full_call_ok`, `n`); then the per-split event counts. It is a **rendering** of
`probe_report.json` and computes nothing.

**`done.json`'s `metrics` (errata):** `eval` writes `<stat>@<risk>` —
`coverage@0.05`, `trig_acc@0.05`, `earliness@0.05`, `wrong_spec@0.05` for a
classifier; `tool_ok@<risk>`, `params_all_ok@<risk>`, `full_call_ok@<risk>` for a
generator — with null-valued entries omitted.

**Not ported** from `eval_tool.py`: the whole model half — `score` (61-76),
`load_causal` (81-91), `score_causal` (116-197), `weights_fingerprint` (94-113),
`token_cost` (200-208) and the `--cached-logits` /
`--adopt-logits-fingerprint` machinery (312-316, 358-380, 436-498); the
`--overlong` left/skip/drop-event modes and their five counter fields; the
readonly-tool / abstain-class mode; `--legacy-splits`; `--limit`; `--report-dir`
and `--device`.

### 2. `eval/methods/ctool.py` (contracts 1.4, 2.6)

```python
VERSION = 1
PROBE_KIND = "classifier"        # equal to train/methods/ctool.py's; selfcheck compares (2.6)

def match(pred: str, target: str, env) -> bool                 # 2.6
def report(pred_df, cfg, ref, labels) -> tuple[dict, DataFrame | None]   # 2.6
def main(run_dir: Path) -> None  # one line: probe_eval.run(run_dir, sys.modules[__name__])
```

plus `if __name__ == "__main__":` parsing exactly `--run-dir <dir>` and nothing
else (2.6's command shape; a one-process stage carries no `--piece`).

`match(pred, target, env)` is class-name equality, `pred == target`; `env` is
`None` and is ignored.

**`report`'s algorithm** (the port of `eval_tool.py`'s post-processing):

1. `ref` must be None and `labels` must be a list; raise otherwise.
2. `logits` -> `np.asarray(pred_df["logits"].to_list(), dtype=np.float64)`;
   `y` = the index of each row's `target` in `labels`; raise, naming the value, on
   a target that is not in `labels` (1.3's class-order rule makes that a defect).
3. `T = probe_eval.fit_temperature(logits[val], y[val])` where `val` is
   `split == "val"`. Raise when the val slice is empty.
4. `probs = probe_eval.softmax(logits, T)`; per row `conf = probs.max(axis=1)`,
   `pred_idx = probs.argmax(axis=1)`, `label_pred = labels[pred_idx]`.
5. **The first-crossing rule, once, here** (1.4): group the rows by `event_id`,
   order each event's cuts by **`depth` ascending, tie-broken by `example_id`
   ascending** (errata — the prediction row carries no cut index), and take the
   first cut with `conf >= theta`. Per event:
   `{fired, ok: label_pred == target, depth, conf, task_id, split, event_id,
   example_id, label_pred}`. Port of `eval_tool.py:227-249` minus its `nro_id`
   parameter.
6. `agg(recs)` -> `{n, coverage, trig_acc, earliness, wrong_spec}`, each rounded
   to 4, verbatim from `eval_tool.py:252-260` (`coverage = fired/n`,
   `trig_acc = ok/fired`, `earliness = mean(1-depth)` over fired,
   `wrong_spec = wrong/n`).
7. `grid`: for every theta in `cfg.eval.theta_grid`, `agg` over the **val**
   events; each entry is `{"theta": θ, **agg}`.
8. `chosen`: per risk in `cfg.eval.risk`, the theta with the largest `coverage`
   among those whose `trig_acc >= 1 - risk` and whose `coverage > 0`, else `None`
   (`eval_tool.py:513-518`). Keys are `str(risk)`.
9. `frozen`: per risk with a theta, `agg` over the **test** events at that theta
   plus `ci = probe_eval.bootstrap_ci(...)` over the same events grouped by
   `task_id`, with `n=cfg.eval.bootstrap`, `seed=cfg.eval.bootstrap_seed`. Risks
   whose `chosen` is null are absent from `frozen`.
10. `fires`: for every risk with a theta, the fired events of **every split** at
    that theta (1.4), one row per fired event with the `FIRES_SCHEMA` columns.
11. Returns `({"temperature": round(T,4), "risk_targets": cfg.eval.risk,
    "grid": grid, "chosen": chosen, "frozen": frozen,
    "n_events": {split: distinct event_id}}, fires)`. `n_events` counts distinct
    `event_id` **per split of the prediction frame the method was handed**
    (errata).

Legacy source: `eval_tool.py:213-224, 227-249, 252-260, 279-296, 500-532,
513-518`.
**Not ported:** `economics` (263-276) and the `speculation_economics` block
(612-617, 656-667); the stop-time calibration (534-545); the depth-decile
accuracy and the frequency-prior baseline (547-568); `probe_cost_test` /
`probe_backbone` (624-630); the readonly arm (`nro_id`, `readonly_stats`
570-596). None of them is a field of 1.4's classifier shape, and 1.4's table is
the format.

## Acceptance

Run from the repo root and paste the real output. `$PY` is
`/home/y-guo/reproduce/new1/external/probe-env/bin/python` — `venv: any` resolves
to `venvs.probe` for a stage program (6.3).

**Prerequisite, already done by the main session before this wave:**
`uv pip install --python /home/y-guo/reproduce/new1/external/appworld/venv/bin/python numpy`.
If A1 fails under the appworld interpreter with `ModuleNotFoundError: numpy`,
stop and say so — an implementer does not install packages.

**A1 — the `any` import test.**
```bash
for P in /home/y-guo/reproduce/new1/external/probe-env/bin/python \
         /home/y-guo/reproduce/new1/external/appworld/venv/bin/python \
         /home/y-guo/reproduce/new1/external/vllm-env/bin/python; do
  for M in eval.utils.probe_eval eval.methods.ctool; do
    $P -c "import importlib,sys; sys.path.insert(0,'.'); importlib.import_module('$M')" || echo "FAIL $P $M";
  done; done; echo "import test done"
```
Expected: no `FAIL` line, `import test done`, exit 0.

**A2 — no torch, no GPU anywhere in `eval/`.**
```bash
grep -rn "import torch\|from torch\|cuda\|transformers" eval/ ; echo "exit=$?"
```
Expected: no matches, `exit=1`.

**A3 — the literal lines `selfcheck` reads.**
```bash
/home/y-guo/reproduce/new1/external/probe-env/bin/python - <<'PY'
import re, pathlib
for p in ["eval/utils/probe_eval.py", "eval/methods/ctool.py"]:
    s = pathlib.Path(p).read_text()
    v = re.findall(r"(?m)^VERSION = (\d+)$", s)
    assert len(v) == 1, (p, v)
s = pathlib.Path("eval/methods/ctool.py").read_text()
assert re.findall(r'(?m)^PROBE_KIND = "(\w+)"$', s) == ["classifier"]
print("literals ok")
PY
```
Expected: `literals ok`, exit 0.

**A4 — the classifier path end to end, on a fixture the command builds.**
```bash
/home/y-guo/reproduce/new1/external/probe-env/bin/python - <<'PY'
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
            method="ctool", target=tool, score=0.9, label_pred=tool,
            logits=[3.0, 0.0] if tool == labels[0] else [0.0, 3.0],
            text_pred=None, gen_tokens=None))
probe_output.write(tdir / "predictions.parquet", pl.DataFrame(rows, strict=False))
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
Expected: `A4 ok`, exit 0; `fields:` lists at least `chosen`, `commit`, `frozen`,
`grid`, `labels`, `method`, `n_events`, `probe_kind`, `risk_targets`,
`stage_key`, `temperature`, `theta_from`, `train_key`, `version`;
`fires columns:` exactly the eight of 1.4 and `rows: 40` (20 events fired at each
of the two risk targets). Every file lands under the outputs root's `debug/`
subtree, named by `schema.run_dir_of(..., debug=True)` — nothing is hardcoded.

**This fixture is a classifier with `theta_from: null`, so nothing references it
and `debug=True` is right.** A fixture that a *generator* eval will reference is
a different case and is built differently: step 6 above locates a resolved
reference with `run_dir_of(..., debug=False)`, so **a referenced eval run and the
train run it names must both be non-debug directories**, and the referenced eval
directory must also carry a `meta.json` (the stage program never writes one —
`run.py` / `jobs/launch.py` do). Ticket 10's `A6` builds exactly that, its own
copy, under its own keys; do not point ticket 10 at this fixture.

**Clean up after A4**: delete the two fixture directories at the end of the
command (`shutil.rmtree(tdir)`, `shutil.rmtree(edir)`) and name the keys you used
(`aaaaaaaaaaaa`, `bbbbbbbbbbbb`) in your report, so the main session can confirm
nothing fake is left under the outputs root's `debug/` subtree.

**A5 — the temperature fit and the bootstrap.**
```bash
/home/y-guo/reproduce/new1/external/probe-env/bin/python - <<'PY'
import sys, numpy as np, polars as pl; sys.path.insert(0, ".")
from eval.utils import probe_eval as pe
rng = np.random.default_rng(0)
y = rng.integers(0, 3, 4000)
# Over-confident, not correct: about 35% of the rows put the 8.0 logit on a wrong
# class, so the NLL-minimising temperature sits above 1 instead of at the grid
# floor. A perfectly separable fixture would make the mean NLL
# log(1 + 2*exp(-8/T)) fall monotonically with T and pin the answer at e^-4.
wrong = rng.random(4000) < 0.35
pred = np.where(wrong, (y + 1 + rng.integers(0, 2, 4000)) % 3, y)
lg = np.zeros((4000, 3)); lg[np.arange(4000), pred] = 8.0
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
Expected: `A5 ok`, exit 0; `T` identical across the two calls; `ci` identical
across the two calls and bracketing 0.5. **`T` prints about `6.0`** — the
analytic minimum for this fixture is `8 / ln(2(1-q)/q)` with `q` the wrong share,
which is `6.04` at the measured `q = 0.347`; the 81-point grid alone lands on
`e^1.8 = 6.05` and the golden-section refinement on `6.0359` (measured
2026-09-17 with the algorithm this ticket specifies). A `T` at either end of the
grid (`0.018` or `54.6`) means the minimiser ran the wrong way; report it, do not
clamp it.

**A7a — `match` is callable from the train side.**
```bash
/home/y-guo/reproduce/new1/external/probe-env/bin/python -c "
import sys; sys.path.insert(0, '.')
from eval.methods import ctool
assert ctool.match('apis.a.x', 'apis.a.x', None) is True
assert ctool.match('apis.a.x', 'apis.b.y', None) is False
print('ctool match ok')"
```
Expected: `ctool match ok`, exit 0.

### Selfcheck lines that apply later

`run.py selfcheck` (ticket 15) will check: both files import under every
interpreter of the `venvs:` map (A1); one integer `VERSION` line each (A3);
`PROBE_KIND` in `eval/methods/ctool.py` equal to the one in
`train/methods/ctool.py` (ticket 13's file, so the pair check lands then); every
`README.md` annotation line against the real import graph — in particular that
`probe_eval.py` imports **neither** `data/__init__.py` nor
`data/environments/__init__.py`; every axis value of `probe.method` having a file
under `eval/methods/`; and no `/home/` or `/net/` path in code outside
`constants/` (the fixtures above reach the outputs root through
`schema.run_dir_of`, never by a literal, and they live in the acceptance command,
not in the code).

### GPU / main session — not yours

`M-E1` the first real classifier eval over a real `train` run's
`predictions.parquet`:
`run.py train_probe ctool_q06 --debug` then `run.py where train_probe ctool_q06 eval`
must show `probe_report.json` with a `temperature` between 0.5 and 5, a `chosen`
entry per risk target, `frozen` numbers whose `n` equals the test event count in
the train run's `done.json` `counts`, and a `fires.parquet` whose `event_id`
values are a subset of the prediction frame's.

## Comments
