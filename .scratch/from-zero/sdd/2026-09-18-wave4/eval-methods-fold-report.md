# eval/methods fold — report

## eval/methods fold, round 1

Base `014f57fc7b980cade2f758e6d90ad65409beaad1`, branch
`ticket/2026-09-18-wave4/eval-methods-fold`, head `457c288`. Worktree
`/home/y-guo/reproduce/new1-wt/2026-09-18-wave4-eval-methods-fold1`, removed at
the end; the branch is kept.

### 1. What moved where

`git rm eval/methods/ctool.py eval/methods/cgen.py eval/methods/cparam.py`. No
`__pycache__` existed under `eval/methods/` in the worktree (git-ignored files
are not carried into a worktree), so nothing further was deleted there; the copy
in the main repo's working tree is the main session's to remove. The tree now
holds 31 Python files: 26 on disk today (1 schema + 8 data + 8 models + 4 agent +
3 eval + 2 jobs) plus `run.py` and the four `train/` files of wave 5.

Everything below is in `eval/utils/probe_eval.py`, added to what the file already
held. `VERSION` stays `1`: no byte of any report and no number in it changes —
the classifier and generator computations moved with their logic intact, the
identity block is unchanged, and no eval run exists yet, so nothing that was
keyed under the old `VERSION` needs to stay reproducible under it.

**(1) The two column-zero tables**, plain dict literals assigned exactly once at
column zero, each with a comment above it saying who reads it:

```python
PROBE_KIND = {"ctool": "classifier", "cgen": "generator", "cparam": "generator"}
MATCH_VERSION = {"ctool": 1, "cgen": 1, "cparam": 1}
```

`MATCH_VERSION` is why an eval-side `VERSION` bump re-keys no train run: `train`
and `inject` fold their own method's match version and nothing else of this file.

**(2) The three match functions**, moved verbatim in their logic:

| name | from | shape |
|---|---|---|
| `match_ctool(pred, target, env)` | `eval/methods/ctool.py:match` | `bool`, class-name equality, `env` ignored |
| `match_cgen(pred, target, env)` | `eval/methods/cgen.py:match` | `dict` with `tool_ok` / `params_all_ok` / `full_call_ok` |
| `match_cparam(pred, target, env)` | `eval/methods/cparam.py:match` | the same three keys, over two whole calls |

The two generator bodies were identical line for line, so the comparison is
written once as `_match_call(method, pred, target, env)`, with the shared
`_params_all_ok` helper beside it; `match_cgen` and `match_cparam` are one line
each and only the refusal text names which of the two was called
(`match_cgen: target ... does not parse via env.split_args`). The
`TODO(gyb, 2026-09-18)` note that the matching rule is open, which the two
generator files carried in their module docstrings, is carried once, in
`_match_call`'s docstring, together with the dropped-`noparam` sentence.

**(3) The report hooks.** I chose **two named functions plus the dispatcher**:

```python
def report_classifier(method, pred_df, cfg, ref, labels) -> tuple[dict, pl.DataFrame]
def report_generator(method, pred_df, cfg, ref, labels) -> tuple[dict, None]
def report(method, pred_df, cfg, ref, labels) -> tuple[dict, pl.DataFrame | None]
```

`report` dispatches on `PROBE_KIND[method]` and refuses a third kind naming it.
`method` is the first parameter of both named functions so that every refusal
still names the method the way the old per-file messages did (`cgen: ref must be
a (fields, fires) tuple`, in place of `cgen.report: ...`).

`report_classifier` is today's `ctool.report` whole: the temperature fit, the
theta choice at each risk on val, the first-crossing rule (`_first_crossing`),
the four numbers (`_agg`), the bootstrap over `_classifier_ci_stat`, and the
fired rows. `report_generator` is the shape `cgen.report` and `cparam.report`
shared: the join to the reference fires per risk target, the three exact-match
rates, the bootstrap ci, `n_events`, and `None` for the second file.

The one method-specific step is `_generator_scores(method, test, fires_risk,
env)`, which returns the joined frame and the three per-row lists. `cgen` joins
on `example_id` and takes all three numbers out of one `match_cgen` call per row;
`cparam` renames the fired `label_pred` to `fired_label` on the way in, takes
`tool_ok` as `fired_label == row["tool"]` and `params_all_ok` out of
`match_cparam` over the two calls rebuilt as `tool + "(" + <the argument
string>`. Nothing else in the generator report branches on the method. `_n_events`
is shared by both reports.

**(4) The driver.** `run(run_dir)` takes the method from the frozen setting
(`cfg.probe.method`) immediately after `load_frozen` and refuses one absent from
`PROBE_KIND`, naming it and the table's keys, before `registry.beat` is called.
`module.PROBE_KIND` became `PROBE_KIND[method]`, `module.report` became
`report(method, ...)`, and the `predictions.parquet` method-column gate reads the
same local. `main(run_dir)` calls `run(run_dir)`, and the
`if __name__ == "__main__":` block parses exactly `--run-dir`. The eval program
is `eval.utils.probe_eval` for every method.

`probe_eval.py` now imports `data/environments/__init__.py` (`open_env`), which
the generator report needs and which the two deleted generator files used to
carry. That is the one change to this file's import graph, and its README
`imports:` line says so. Ticket 08's selfcheck note "`probe_eval.py` imports
neither `data/__init__.py` nor `data/environments/__init__.py`" is overtaken by
the fold for the second half of that pair; the first half still holds.

### 2. experimental_settings/schema.py

- `STAGES["eval"]["program"]` is `"eval.utils.probe_eval"`.
- `_method_kind(method)` reads `module_literal("eval/utils/probe_eval.py",
  "PROBE_KIND")[method]` and refuses an unknown method naming it and the table.
- `AXES["probe.method"]` is untouched.

**The versions-block spelling I chose** is the one the dispatch proposed:

```
eval/utils/probe_eval.py#MATCH_VERSION.{method}
```

— the module path, `#`, the table's name, `.`, the method. The same string is
the template in the `STAGES` tuple and the key in the versions block, and its
value is the `int` `module_literal` reads out of that table. `versions_of` splits
an entry on `#`; with no `#` it is a bare module path and takes that module's
`VERSION`, exactly as before, so every existing whole-file entry is unchanged.
A method the named table has no entry for raises a `SchemaError` naming the file,
the table and the method. `versions_of`'s docstring states both spellings and why
the second exists. `freeze` writes `_versions` through `versions_of`, so the
frozen `settings.yaml` records the same keys (shown under (f) below).

The three versions cells after the fold:

| stage | before | after |
|---|---|---|
| train | `eval/methods/{method}.py` | `eval/utils/probe_eval.py#MATCH_VERSION.{method}` |
| eval | `eval/utils/probe_eval.py`, `eval/methods/{method}.py` | `eval/utils/probe_eval.py` alone |
| inject | `eval/utils/probe_eval.py`, `eval/methods/{probe_score_method}.py` | `eval/utils/probe_eval.py`, `eval/utils/probe_eval.py#MATCH_VERSION.{probe_score_method}` |

One message changed with it: `_substitute`'s refusal when a pinned
`inject.probe_score` states no method now reads "so its match version has no
source" in place of "so the version of its eval method file has no source".

### 3. README.md

The `methods/` subtree lines and the three `eval/methods` entries are gone from
the Ticket 08 and Ticket 10 sections, and `eval/utils/probe_eval.py`'s five-line
entry is rewritten to the contracts 0.1 shape:

```
      probe_eval.py         the eval program of every probe method: the PROBE_KIND and MATCH_VERSION
                            tables, the three match functions, the classifier and the generator report,
                            and the driver that reads a train run's prediction rows and writes the probe
                            report; carries VERSION
        imports: experimental_settings/schema.py, data/probe_output.py,
                 data/environments/__init__.py (open_env, for the environment the generator report
                 normalises both sides through, 2.6), jobs/registry.py; [polars, numpy]
        used by: train/methods/{ctool,cgen,cparam}.py (match_<method>, for their validation metric),
                 run.py (read_report, to freeze a temperature), eval/method_table.py
        reads:   prediction (parquet), its own and the referenced eval run's train meta.json
                 (stage_extra.labels, upstream["build"] — the second is what the 2.5 gate compares), probe
                 report (json + parquet)
        writes:  probe report (probe_report.json + fires.parquet), report.md, consumed.json (the
                 prediction parquet and any referenced report it read), heartbeat, done.json
        venv:    any
```

The file's module docstring's first line is that same sentence, word for word.
The Ticket 08 section's closing sentence "`eval/methods/cgen.py` and
`eval/methods/cparam.py` are not this ticket's; their lines are added by tickets
09 and 10" became "Ticket 10's two generator metrics land in this same file."

**One README line outside the ruling's list.** The dispatch says "touch no other
line", while acceptance (g) requires no `eval/methods` hit in `README.md`. The
two cannot both hold, because `data/environments/__init__.py`'s `used by:` line
named the two deleted files. I changed that one line, since the annotation line
is what `run.py selfcheck` proves against the real import graph and leaving it
would make it false:

- old: `                 validation metric's match takes, 2.6), eval/methods/cgen.py, eval/methods/cparam.py,`
- new: `                 validation metric's match takes, 2.6), eval/utils/probe_eval.py,`

### 4. Every ticket line rewritten

**Ticket 13** (`13-training-loop-and-probe-methods.md`)

- old: `                             data/training_data.py, eval/methods/ctool.py; [torch]  VERSION = 1`
- new: `                             data/training_data.py, eval/utils/probe_eval.py; [torch]  VERSION = 1`

- old: ``  with `eval/methods/ctool.py`'s `match(pred_label, target_tool, None)` (a``
- new: ``  with `eval/utils/probe_eval.py`'s `match_ctool(pred_label, target_tool, None)` (a``

- old: ``  `train_causal_share.py:272-295`), compared with `eval/methods/cgen.py`'s`` / ``  `match(pred, target, env)` where `env = open_env(cfg.data.env)` — the``
- new: ``  `train_causal_share.py:272-295`), compared with `eval/utils/probe_eval.py`'s`` / ``  `match_cgen(pred, target, env)` where `env = open_env(cfg.data.env)` — the``

- old: ``- `validate` calls `eval/methods/cparam.py`'s `match` on two **whole calls**:``
- new: ``- `validate` calls `eval/utils/probe_eval.py`'s `match_cparam` on two **whole calls**:``

- old (A3.1's PROBE_KIND cross-check):
  ```python
          e = ast.parse(pathlib.Path("eval/methods/" + f.split("/")[-1]).read_text())
          ek = [n for n in e.body if isinstance(n, ast.Assign)
                and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "PROBE_KIND"
                and n.col_offset == 0]
          if len(ek) != 1 or ast.literal_eval(ek[0].value) != ast.literal_eval(k[0].value):
  ```
- new:
  ```python
          e = ast.parse(pathlib.Path("eval/utils/probe_eval.py").read_text())
          ek = [n for n in e.body if isinstance(n, ast.Assign)
                and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "PROBE_KIND"
                and n.col_offset == 0]
          method = f.split("/")[-1][:-3]
          table = ast.literal_eval(ek[0].value) if len(ek) == 1 else {}
          if table.get(method) != ast.literal_eval(k[0].value):
  ```

- old: ``under `train/methods/` and `eval/methods/`; and `PROBE_KIND` declared in both`` / `method files and equal. A3.1 stands in for all but the first.`
- new: ``under `train/methods/` and the keys of `eval/utils/probe_eval.py`'s `PROBE_KIND``` / ``and `MATCH_VERSION` tables; and `PROBE_KIND` declared in the train method file`` / `and equal to that method's entry in the eval table. A3.1 stands in for all but` / `the first.`

- old (the wave-5 Comment, which told the implementer the fold had not happened
  yet and named the deleted files):
  ```
  - 2026-09-18, from gyb (review of waves 2 and 3, session fork1): **do not dispatch
    this ticket before the `eval/methods/` fold has merged.** gyb ruled that
    `eval/methods/{ctool,cgen,cparam}.py` fold into `eval/utils/probe_eval.py`
    after wave 4 and before wave 5 (errata, the entry "0.2 / 2.1 / 2.6
    (`eval/methods/`)"; details in the `TODO(gyb, 2026-09-18)` at the top of
    `eval/methods/ctool.py`). Every place in this ticket that imports
    `eval.methods.<m>`, reads its `PROBE_KIND`, or names `eval/methods/<m>.py` in a
    versions list is rewritten by that change to the new home of `match` and to the
    per-method match version; `train/methods/` stays one file per method.
  ```
- new:
  ```
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
  ```

**Ticket 14** (`14-run-py-walk-and-readme.md`)

- old: `   All **34** Python files of 0.3 plus the non-Python entries (\`constants/*.yaml\`,`
- new: `   All **31** Python files of 0.3 plus the non-Python entries (\`constants/*.yaml\`,`

- old: ``Expected: `34 True`, exit 0. (`readme_entries` is the parser ticket 15's``
- new: ``Expected: `31 True`, exit 0. (`readme_entries` is the parser ticket 15's``

- old (D2's whole expectation paragraph):
  ```
  Expected: `30`, and no `MISSING` line. **30, not 34**: `train/` is ticket 13's and
  merges at the end of this same wave, so the four `train/*.py` files are not on
  disk in your worktree — `1 run.py + 1 schema.py + 8 data + 8 models + 4 agent +
  6 eval + 2 jobs`. `README.md` still carries all **34** entries, the four `train/`
  ones included, because it is assembled from contracts 0.2 and `D1` counts them
  (`34 True`). Do not drop a `train/` line to make this command print 34, and do
  not add `train` to the `find` list. The 34-file check is **ticket 15's `D3`** and
  **ticket 18's `C6`**, both after wave 5 merges.
  ```
- new:
  ```
  Expected: `27`, and no `MISSING` line. **27, not 31**: `train/` is ticket 13's and
  merges at the end of this same wave, so the four `train/*.py` files are not on
  disk in your worktree — `1 run.py + 1 schema.py + 8 data + 8 models + 4 agent +
  3 eval + 2 jobs`. `README.md` still carries all **31** entries, the four `train/`
  ones included, because it is assembled from contracts 0.2 and `D1` counts them
  (`31 True`). Do not drop a `train/` line to make this command print 31, and do
  not add `train` to the `find` list. The 31-file check is **ticket 15's `D3`** and
  **ticket 18's `C6`**, both after wave 5 merges.
  ```
  (27 was counted on the branch: `find constants experimental_settings data models
  agent eval jobs -name '*.py' | wc -l` gives 26, plus `run.py`, which ticket 14
  itself writes.)

**Ticket 15** (`15-run-py-selfcheck.md`)

- old: `By this wave every one of the 34 Python files is on the branch, so **a green`
- new: `By this wave every one of the 31 Python files is on the branch, so **a green`

- old: `   exists. The count is **34**.`
- new: `   exists. The count is **31**.`

- old: ``   `schema.AXES["probe.method"]` equals the intersection of the file stems under`` / ``   `train/methods/` and `eval/methods/`; `schema.AXES["data.env"]` equals the file``
- new: ``   every axis value of `schema.AXES["probe.method"]` is a key of`` / ``   `eval/utils/probe_eval.py`'s `PROBE_KIND` and of its `MATCH_VERSION`, and the`` / ``   axis equals the file stems under `train/methods/`; `schema.AXES["data.env"]` equals the file``

- old: ``6. The two `PROBE_KIND` declarations of a method — `train/methods/<m>.py` and`` / ``   `eval/methods/<m>.py` — are equal (2.6).``
- new: ``6. The two `PROBE_KIND` declarations of a method — `train/methods/<m>.py`'s`` / ``   literal and that method's entry in `eval/utils/probe_eval.py`'s `PROBE_KIND``` / `   table — are equal (2.6).`

- old: ``\`selfcheck: 34 python files, 0 problems\` and exit 0. Shape ported from``
- new: ``\`selfcheck: 31 python files, 0 problems\` and exit 0. Shape ported from``

- old: ``Expected: `selfcheck: 34 python files, 0 problems` and `rc=0`.``
- new: ``Expected: `selfcheck: 31 python files, 0 problems` and `rc=0`.``

- old: ``| 6 | change `eval/methods/cgen.py`'s `PROBE_KIND` to `"classifier"` |``
- new: ``| 6 | change `eval/utils/probe_eval.py`'s `PROBE_KIND["cgen"]` to `"classifier"` |``

**Ticket 18** (`18-migration-legacy-gitignore-timeline.md`)

- old: `- **Decision**: the old tree is replaced by the 34-file tree of`
- new: `- **Decision**: the old tree is replaced by the 31-file tree of`

- old: `- **Counts**: about 60 Python files under the old code directories -> 34; the old`
- new: `- **Counts**: about 60 Python files under the old code directories -> 31; the old`

- old: ``Expected: `selfcheck: 34 python files, 0 problems`, `rc=0`. This is the check``
- new: ``Expected: `selfcheck: 31 python files, 0 problems`, `rc=0`. This is the check``

- old: ``Expected: `34`, and no `MISSING` line.``
- new: ``Expected: `31`, and no `MISSING` line.``

### 5. Acceptance — the commands and their real output

Every fixture ran under a temp outputs root. The whole code tree was copied with
`cp -a` into `$S/repo` inside a `mktemp -d`, and that copy's
`constants/path_outputs.yaml` had its `root:` pointed at `$S/outputs`, so both
the parent process and the `python -m eval.utils.probe_eval` subprocess resolve
`schema.run_dir_of` to the temp tree: `schema.ROOT` is
`Path(__file__).resolve().parents[1]`, so it follows the copy. The real outputs
root and the real `jobs/runs.jsonl` were never written (checked at the end;
`jobs/runs.jsonl` is still 0 lines and the real root holds none of the eight
fixture keys). `$S` was `/tmp/tmp.5R2jwMFDua` and is deleted.

**(a) The import test.**

```
$ for P in .../probe-env/bin/python .../appworld/venv/bin/python .../vllm-env/bin/python; do
    for M in eval.utils.probe_eval eval.score_run eval.method_table experimental_settings.schema; do
      $P -c "import importlib,sys; sys.path.insert(0,'.'); importlib.import_module('$M')" || echo "FAIL $P $M";
    done; done; echo "import test done"
import test done

$ python3 -c "import sys; sys.path.insert(0,'.'); import experimental_settings.schema as S; print(S.__name__, len(S.STAGES), S.STAGES['eval']['program'])"
experimental_settings.schema 6 eval.utils.probe_eval
```

No `FAIL` line under any of the three venvs; `schema` also imports under system
`python3` and its eval program reads `eval.utils.probe_eval`.

**(b) Ticket 08's classifier acceptance (A4), through `python -m
eval.utils.probe_eval --run-dir`.** Fixture keys `aaaaaaaaaaaa` (train) and
`bbbbbbbbbbbb` (eval), both `debug=True`, both `shutil.rmtree`'d at the end.

```
@hb {"done": 0, "total": 20, "unit": "item", "ts": 1789709531.7567673}
@hb {"done": 0, "total": 20, "unit": "item", "ts": 1789709531.9513009, "status": "done"}
outputs root in use: /tmp/tmp.5R2jwMFDua/outputs/debug/train/aaaaaaaaaaaa
fields: ['chosen', 'commit', 'frozen', 'grid', 'labels', 'method', 'n_events', 'probe_kind', 'risk_targets', 'stage_key', 'temperature', 'theta_from', 'train_key', 'version']
temperature: 0.0202 chosen: {'0.1': 0.5, '0.05': 0.5}
fires columns: ['risk', 'theta', 'split', 'event_id', 'example_id', 'score', 'depth', 'label_pred'] rows: 40
A4 ok
```

Every assertion of ticket 08's A4 passed unchanged: `probe_kind == "classifier"`,
`method == "ctool"`, the identity block, `frozen["0.05"]` coverage and trig_acc
`1.0`, `n_events == {"val": 10, "test": 10}`, the eight fires columns, 40 fires
rows, `done.json`, `report.md`, `consumed.json`. The temperature is `0.0202`, the
grid floor, because this fixture is perfectly separable — the same number the
pre-fold `eval.methods.ctool` produced on it; ticket 08's A4 asserts no
temperature value and its A5 is the fixture that pins the fit (below).

Ticket 08's A5 (the temperature fit and the bootstrap), run on the same branch:

```
T = 6.0359
ci = {'acc': [0.5, 0.5]}
A5 ok
```

`6.0359` is the value ticket 08 names for that fixture, so `fit_temperature` and
`bootstrap_ci` came through the fold unchanged.

Ticket 08's A2, over the folded file:

```
$ grep -rn "import torch\|from torch\|cuda\|transformers" eval/ ; echo "exit=$?"
exit=1
```

**(c) Ticket 10's A6a + A6, through the same program with `probe.method` set per
run.** Keys `4444dddd4444` / `5555eeee5555` (non-debug reference) and
`dddddddddddd` / `eeeeeeeeeeee` (cgen), `6666ffff6666` / `7777aaaa7777` (cparam),
all under the temp root.

A6a:
```
@hb {"done": 0, "total": 20, "unit": "item", "ts": 1789709550.8487635}
@hb {"done": 0, "total": 20, "unit": "item", "ts": 1789709551.0492702, "status": "done"}
reference fires: 40 ['test', 'val']
A6a ok
```

A6:
```
@hb {"done": 0, "total": 20, "unit": "item", "ts": 1789709567.2050512}
@hb {"done": 0, "total": 20, "unit": "item", "ts": 1789709567.2911088, "status": "done"}
cgen generator fields: ['commit', 'exact', 'labels', 'method', 'n_events', 'probe_kind', 'risk_targets', 'stage_key', 'theta_from', 'theta_used', 'train_key', 'version']
cgen exact@0.05 = {'tool_ok': 1.0, 'params_all_ok': 0.8, 'full_call_ok': 0.8, 'n': 10, 'ci': {'tool_ok': [1.0, 1.0], 'params_all_ok': [0.6, 1.0], 'full_call_ok': [0.6, 1.0]}}
cgen A6 ok
@hb {"done": 0, "total": 20, "unit": "item", "ts": 1789709568.0134993}
@hb {"done": 0, "total": 20, "unit": "item", "ts": 1789709568.094648, "status": "done"}
cparam generator fields: ['commit', 'exact', 'labels', 'method', 'n_events', 'probe_kind', 'risk_targets', 'stage_key', 'theta_from', 'theta_used', 'train_key', 'version']
cparam exact@0.05 = {'tool_ok': 1.0, 'params_all_ok': 0.8, 'full_call_ok': 0.8, 'n': 10, 'ci': {'tool_ok': [1.0, 1.0], 'params_all_ok': [0.6, 1.0], 'full_call_ok': [0.6, 1.0]}}
cparam A6 ok
```

`n` 10, `tool_ok` 1.0, `params_all_ok` 0.8, `full_call_ok` 0.8 for both, the
numbers ticket 10 expects; `fires.parquet` is absent for both generator runs.

**(d) Ticket 10's A7 with the new names.**

```
$ .../probe-env/bin/python - <<'PY'
import sys; sys.path.insert(0, ".")
from data.environments import open_env
from eval.utils import probe_eval as pe
env = open_env("appworld")
assert pe.match_ctool("apis.a.x", "apis.a.x", None) is True
assert pe.match_ctool("apis.a.x", "apis.b.y", None) is False
good = env.build_call("apis.a.x", [("k", "1")])
bad  = env.build_call("apis.a.x", [("k", "2")])
assert pe.match_cgen(good, good, env) == {"tool_ok": True, "params_all_ok": True, "full_call_ok": True}
assert pe.match_cgen(bad, good, env)["params_all_ok"] is False
assert pe.match_cgen("not a call at all", good, env) == {"tool_ok": False, "params_all_ok": False, "full_call_ok": False}
none0 = env.build_call("apis.a.x", [])
assert pe.match_cgen(good, none0, env)["params_all_ok"] is False     # the dropped noparam short-circuit
assert pe.match_cparam(good, good, env)["params_all_ok"] is True
print("A7 ok")
PY
A7 ok
```

**(e) The ast checks.**

```
VERSION = 1
PROBE_KIND = {'ctool': 'classifier', 'cgen': 'generator', 'cparam': 'generator'}
MATCH_VERSION = {'ctool': 1, 'cgen': 1, 'cparam': 1}
no eval/methods directory: True
literals ok
```

Exactly one column-zero assignment each of `VERSION`, `PROBE_KIND` and
`MATCH_VERSION`; `ast.literal_eval` succeeds on both tables; no file under
`eval/methods/` and no such directory.

**(f) schema.** `_method_kind` for the three methods and its refusal, then
`schema.load` and `schema.key` over ticket 04's fixture tree — the whole
`experimental_settings` directory copied with `cp -a`, `constants/*.yaml` copied
and its outputs root repointed, `train/utils/trainer.py` and
`train/methods/<m>.py` stubbed as ticket 04's acceptance does, and
`eval/utils/probe_eval.py` stubbed as
`VERSION = 1` plus the two table literals (the fixture's `eval/methods/` stubs
are gone with the folder).

```
=== _method_kind ===
  _method_kind('ctool') = 'classifier'
  _method_kind('cgen') = 'generator'
  _method_kind('cparam') = 'generator'
  refusal: probe.method 'ctoool' is not a key of PROBE_KIND in eval/utils/probe_eval.py; it holds ['cgen', 'cparam', 'ctool']

=== schema.load + schema.key over the fixture tree ===
  train_probe/ctool_qwen3_0pt6b train: key=a7f5ebd1adbe
    versions={"train/utils/trainer.py": 1, "train/methods/ctool.py": 1, "eval/utils/probe_eval.py#MATCH_VERSION.ctool": 1, "data/training_data.py": 1, "data/probe_output.py": 1, "models/probe_models/base.py": 1, "models/probe_models/qwen.py": 1}
  train_probe/ctool_qwen3_0pt6b eval: key=67e377456b8e
    versions={"eval/utils/probe_eval.py": 1, "data/probe_output.py": 1}
  train_probe/cgen_qwen3_0pt6b train: key=7c509d3a79fa
    versions={"train/utils/trainer.py": 1, "train/methods/cgen.py": 1, "eval/utils/probe_eval.py#MATCH_VERSION.cgen": 1, "data/training_data.py": 1, "data/probe_output.py": 1, "models/probe_models/base.py": 1, "models/probe_models/qwen.py": 1}
  train_probe/cgen_qwen3_0pt6b eval: key=c622550d0044
    versions={"eval/utils/probe_eval.py": 1, "data/probe_output.py": 1}
  train_probe/cparam_qwen3_0pt6b train: key=d047fc949418
    versions={"train/utils/trainer.py": 1, "train/methods/cparam.py": 1, "eval/utils/probe_eval.py#MATCH_VERSION.cparam": 1, "data/training_data.py": 1, "data/probe_output.py": 1, "models/probe_models/base.py": 1, "models/probe_models/qwen.py": 1}
  train_probe/cparam_qwen3_0pt6b eval: key=b710e6d08915
    versions={"eval/utils/probe_eval.py": 1, "data/probe_output.py": 1}

inject/probe_p1_e1_theta_0pt80 inject: key=373d26d8bc27
  versions={"agent/loop.py": 1, "agent/generate.py": 1, "agent/inject.py": 1, "agent/inject_format.py": 1, "data/probe_input.py": 1, "data/trajectory_record.py": 1, "data/environments/__init__.py": 1, "data/environments/appworld.py": 1, "models/agent_models/gptoss.py": 1, "models/agent_models/service.py": 1, "models/probe_models/base.py": 1, "models/probe_models/service.py": 1, "eval/utils/probe_eval.py": 1, "eval/utils/probe_eval.py#MATCH_VERSION.ctool": 1}
inject/no_probe_p1_e1_theta_0pt80 inject: key=6d18fcc8d2d0
  versions={"agent/loop.py": 1, "agent/generate.py": 1, "agent/inject.py": 1, "agent/inject_format.py": 1, "data/probe_input.py": 1, "data/trajectory_record.py": 1, "data/environments/__init__.py": 1, "data/environments/appworld.py": 1, "models/agent_models/gptoss.py": 1, "models/agent_models/service.py": 1, "models/probe_models/base.py": 1, "models/probe_models/service.py": 1, "eval/utils/probe_eval.py": 1, "eval/utils/probe_eval.py#MATCH_VERSION.ctool": 1}
```

No `eval/methods` path in any block. `freeze` writes the same keys:

```
frozen settings.yaml _versions (train, cgen):
  data/probe_output.py: 1
  data/training_data.py: 1
  eval/utils/probe_eval.py#MATCH_VERSION.cgen: 1
  models/probe_models/base.py: 1
  models/probe_models/qwen.py: 1
  train/methods/cgen.py: 1
  train/utils/trainer.py: 1
```

And the new refusal fires when a method is missing from the table (fixture edited
to `MATCH_VERSION = {"ctool": 1}` and restored):

```
refusal: eval/utils/probe_eval.py: MATCH_VERSION has no entry for method 'cgen'; it holds ['ctool']
```

**(g) The grep over the code directories.**

```
$ grep -rn "eval/methods\|eval\.methods" experimental_settings data models eval agent jobs tests README.md .scratch/from-zero/issues | sed 's/:.*//' | sort | uniq -c
     12 .scratch/from-zero/issues/04-setting-schema-and-loader.md
     12 .scratch/from-zero/issues/08-eval-library-and-classifier-metric.md
     19 .scratch/from-zero/issues/10-eval-generators-scorer-and-table.md
      1 .scratch/from-zero/issues/16-gpu-run-and-probe-pipeline-skills.md
```

Zero hits in `experimental_settings/`, `data/`, `models/`, `eval/`, `agent/`,
`jobs/`, `tests/` and `README.md`. Tickets 08 and 10 are the history the
acceptance names. **Two files the acceptance clause did not name still hit**, and
I left both alone because the dispatch says "Change nothing else in the tickets":

- `04-setting-schema-and-loader.md`, 12 hits: the quoted `STAGES` literal
  (4 lines), the fixture script that stubs `$FIX/eval/methods/<m>.py` and the B4
  axis check over `glob.glob('eval/methods/*.py')`, the `{probe_score_method}`
  paragraph, and two wave-2 closeout Comments. Ticket 04 is merged, like 08 and
  10, so this is the same kind of history — except that its fixture script and
  its B4 check are code a re-run of ticket 04's acceptance would execute, and
  both would now be wrong. My own (f) above uses the same fixture with the
  `eval/methods/` stubs replaced by one `eval/utils/probe_eval.py` stub carrying
  the two tables; that is the edit ticket 04 needs if anyone re-runs it.
- `16-gpu-run-and-probe-pipeline-skills.md`, 1 hit, line 117: the extension
  recipe names "the pair `train/methods/<m>.py` + `eval/methods/<m>.py` (0.3)".
  Ticket 16 is **not yet built** (wave 6), so this line will instruct a future
  implementer at a path that no longer exists. It wants: `train/methods/<m>.py`
  plus an entry in `eval/utils/probe_eval.py`'s `PROBE_KIND` and `MATCH_VERSION`
  and a `match_<m>` function there. **This is the one live defect this round
  leaves open** and it needs the main session's one-line edit.

### 6. Commits

| sha | what |
|---|---|
| `ae327b0` | `fold:` the three method files fold into `eval/utils/probe_eval.py` (the two tables, the three match functions with one shared comparison body, the two reports with one method-specific step, `run`/`main`/`__main__`) |
| `da5973b` | `fold:` `schema.py` — one program, `_method_kind` off the table, the three versions cells and `versions_of`'s second spelling |
| `086c01d` | `fold:` `README.md` — one eval entry in place of the `methods/` subtree |
| `457c288` | `fold:` tickets 13, 14, 15 and 18 point at the new home |

### 7. Self-review, and what is open

- **Not done, on purpose**: no `VERSION_HISTORY` block (that change lives on
  another branch), no edit to `notes/`, to `experimental_settings/*.yaml` or to
  `models/table.yaml`, no compatibility shim and no re-export of
  `eval.methods.<m>`, no new file.
- **`VERSION` stays 1** and the report says why above: the reports' bytes and
  numbers do not change and no eval run exists yet.
- **Ticket 16's line 117** is the open item, named in (g).
- **Ticket 04's fixture and B4 check** are the second item in (g); they are
  merged history, but they are runnable history.
- **One README line outside the ruling's list** was changed, named in section 3.
- The generator report's refusal for a method that is a generator with no scoring
  step (`f"{method}: no generator scoring step; the generator methods are 'cgen'
  and 'cparam'"`) is the one place a fourth generator method would land. It is
  unreachable today, since `PROBE_KIND` holds exactly three keys and both
  generators have a branch; it exists so a fourth method fails loudly instead of
  silently taking cparam's path.
- `run.py` does not exist on this branch yet (ticket 14, wave 5), so
  `run.py selfcheck` could not be run; the checks it will make are covered by
  (a), (e), (f) and (g) above.

## eval/methods fold, round 2

Base `014f57fc7b980cade2f758e6d90ad65409beaad1`, branch
`ticket/2026-09-18-wave4/eval-methods-fold`, round-1 head `457c288`, round-2 head
`a7a2f94`. Worktree
`/home/y-guo/reproduce/new1-wt/2026-09-18-wave4-eval-methods-fold2`, removed at
the end; the branch is kept.

### 1. What moved where

No code moved this round. Round 1 finished the fold itself; round 2 fixes the two
prose lines round 1 left pointing at the deleted folder. `eval/utils/probe_eval.py`,
`experimental_settings/schema.py` and the four rewritten tickets are byte for byte
what round 1 committed, and every acceptance number below is identical to round 1's,
which is the check that this round changed no behaviour.

Two lines changed, in two files:

1. **`README.md` line 333**, the `eval/` folder description in the Ticket 08
   section. It still read "A new probe method is a file under methods/", a folder
   the fold deleted, and it slipped past round 1's acceptance (g) only because it
   spells the folder bare, as `methods/`, not `eval/methods`. It now names the new
   home.
2. **`.scratch/from-zero/issues/16-gpu-run-and-probe-pipeline-skills.md`
   line 117**, point 5 of the probe-pipeline skill's rewrite. Ticket 16 is wave 6
   and unbuilt, so this line is an instruction a future implementer follows, not
   history like tickets 04, 08 and 10; it named "the pair `train/methods/<m>.py` +
   `eval/methods/<m>.py`" as the fourth extension place.

### 2. The versions-block spelling

Unchanged from round 1 and re-verified under (f) below:

```
eval/utils/probe_eval.py#MATCH_VERSION.{method}
```

The train stage folds that per-method entry, the eval stage folds the whole file
(`eval/utils/probe_eval.py`), and the inject stage folds both — the whole file plus
`eval/utils/probe_eval.py#MATCH_VERSION.{probe_score_method}`. Every key printed
under (f) equals round 1's, character for character.

### 3. Every line rewritten (old and new)

**`README.md`** (the `eval/` folder description, Ticket 08 section)

- old:
  ```
    eval/                   reads what is on disk and computes numbers; no GPU, no torch, every file imports
                            as any. A new probe method is a file under methods/; a new metric is an edit to
                            the file that reports it
  ```
- new:
  ```
    eval/                   reads what is on disk and computes numbers; no GPU, no torch, every file imports
                            as any. A new probe method is a key in probe_eval.py's PROBE_KIND and
                            MATCH_VERSION tables plus a match_<m> function there; a new metric is an edit
                            to the file that reports it
  ```

The metric half of the sentence is unchanged; only the probe-method half moved. The
line carries no `.py` path, so it is not an entry `readme_entries` returns and
ticket 14's `D1` count of `31` is untouched.

**Ticket 16** (`16-gpu-run-and-probe-pipeline-skills.md`, point 5 of the six the
probe-pipeline skill keeps)

- old:
  ```
  5. **Extending.** The four places a file is added are
     `data/environments/<env>.py`, `models/agent_models/<family>.py`,
     `models/probe_models/<backbone>.py`, and the pair `train/methods/<m>.py` +
     `eval/methods/<m>.py` (0.3). What each extension touches is contracts 0.4's
     table, and the recipe lives in `README.md`. **This skill points at both and
     keeps no copy** — the old `references/extending.md` existed because there was
     no single table; there is one now.
  ```
- new:
  ```
  5. **Extending.** The four places a file is added are
     `data/environments/<env>.py`, `models/agent_models/<family>.py`,
     `models/probe_models/<backbone>.py`, and `train/methods/<m>.py`, whose eval
     side is a `PROBE_KIND` and a `MATCH_VERSION` entry plus a `match_<m>`
     function in `eval/utils/probe_eval.py` (0.3). What each extension touches is
     contracts 0.4's table, and the recipe lives in `README.md`. **This skill
     points at both and keeps no copy** — the old `references/extending.md`
     existed because there was no single table; there is one now.
  ```

"The four places a file is added" stays four, and the four are still the four
directory prefixes ticket 16's own `W3` greps for
(`data/environments/`, `models/agent_models/`, `models/probe_models/`,
`train/methods/`): after the fold a new probe method adds exactly one file,
`train/methods/<m>.py`, and its eval side is an edit to a file that already
exists. `W3` needed no change and got none.

### 4. Acceptance — the commands and their real output

Every fixture ran under a temp outputs root. The code directories (`constants`,
`experimental_settings`, `data`, `models`, `eval`, `agent`, `jobs`, `tests`,
`README.md`) were copied with `cp -a` into `$S/repo` inside a `mktemp -d`, and that
copy's `constants/path_outputs.yaml` had its `root:` pointed at `$S/outputs`, so
both the parent process and the `python -m eval.utils.probe_eval` subprocess resolve
`schema.run_dir_of` to the temp tree (`schema.ROOT` is
`Path(__file__).resolve().parents[1]`, so it follows the copy). `$S` was
`/tmp/tmp.JOCcd5l6Up` and is deleted. The real outputs root and the real
`jobs/runs.jsonl` were never written; the check is at the end of this section.

**(a) The import test** — the three venvs, then `schema` under system `python3`.

```
$ for P in /home/y-guo/reproduce/new1/external/probe-env/bin/python \
           /home/y-guo/reproduce/new1/external/appworld/venv/bin/python \
           /home/y-guo/reproduce/new1/external/vllm-env/bin/python; do
    for M in eval.utils.probe_eval eval.score_run eval.method_table experimental_settings.schema; do
      $P -c "import importlib,sys; sys.path.insert(0,'.'); importlib.import_module('$M')" || echo "FAIL $P $M";
    done; done; echo "import test done"
import test done

$ python3 -c "import sys; sys.path.insert(0,'.'); import experimental_settings.schema as S; print(S.__name__, len(S.STAGES), S.STAGES['eval']['program'])"
experimental_settings.schema 6 eval.utils.probe_eval
```

No `FAIL` line under any of the three venvs.

**(b) Ticket 08's classifier acceptance, through `python -m eval.utils.probe_eval
--run-dir`.** A4's fixture (keys `aaaaaaaaaaaa` train, `bbbbbbbbbbbb` eval, both
`debug=True`, both `shutil.rmtree`'d at the end):

```
@hb {"done": 0, "total": 20, "unit": "item", "ts": 1789710622.7699778}
@hb {"done": 0, "total": 20, "unit": "item", "ts": 1789710622.9262528, "status": "done"}
outputs root in use: /tmp/tmp.JOCcd5l6Up/outputs/debug/train/aaaaaaaaaaaa
fields: ['chosen', 'commit', 'frozen', 'grid', 'labels', 'method', 'n_events', 'probe_kind', 'risk_targets', 'stage_key', 'temperature', 'theta_from', 'train_key', 'version']
temperature: 0.0202 chosen: {'0.1': 0.5, '0.05': 0.5}
fires columns: ['risk', 'theta', 'split', 'event_id', 'example_id', 'score', 'depth', 'label_pred'] rows: 40
A4 ok
```

Every A4 assertion passed unchanged: `probe_kind == "classifier"`,
`method == "ctool"`, the identity block, `frozen["0.05"]` coverage and trig_acc
`1.0`, `n_events == {"val": 10, "test": 10}`, the eight fires columns, 40 fires rows,
`done.json`, `report.md`, `consumed.json`. Temperature `0.0202` and chosen theta
`0.5` at both risks are round 1's numbers.

A5, the temperature fit and the bootstrap:

```
T = 6.0359
ci = {'acc': [0.5, 0.5]}
A5 ok
```

`6.0359` is the value ticket 08 names for that fixture.

**(c) Ticket 10's A6a + A6, through the same program with `probe.method` set per
run.** Keys `4444dddd4444` / `5555eeee5555` (non-debug reference),
`dddddddddddd` / `eeeeeeeeeeee` (cgen), `6666ffff6666` / `7777aaaa7777` (cparam),
all under the temp root.

A6a:
```
@hb {"done": 0, "total": 20, "unit": "item", "ts": 1789710648.2813694}
@hb {"done": 0, "total": 20, "unit": "item", "ts": 1789710648.4377818, "status": "done"}
reference fires: 40 ['test', 'val']
A6a ok
```

A6:
```
@hb {"done": 0, "total": 20, "unit": "item", "ts": 1789710664.789486}
@hb {"done": 0, "total": 20, "unit": "item", "ts": 1789710664.8699925, "status": "done"}
cgen generator fields: ['commit', 'exact', 'labels', 'method', 'n_events', 'probe_kind', 'risk_targets', 'stage_key', 'theta_from', 'theta_used', 'train_key', 'version']
cgen exact@0.05 = {'tool_ok': 1.0, 'params_all_ok': 0.8, 'full_call_ok': 0.8, 'n': 10, 'ci': {'tool_ok': [1.0, 1.0], 'params_all_ok': [0.6, 1.0], 'full_call_ok': [0.6, 1.0]}}
cgen A6 ok
@hb {"done": 0, "total": 20, "unit": "item", "ts": 1789710665.5562036}
@hb {"done": 0, "total": 20, "unit": "item", "ts": 1789710665.6441264, "status": "done"}
cparam generator fields: ['commit', 'exact', 'labels', 'method', 'n_events', 'probe_kind', 'risk_targets', 'stage_key', 'theta_from', 'theta_used', 'train_key', 'version']
cparam exact@0.05 = {'tool_ok': 1.0, 'params_all_ok': 0.8, 'full_call_ok': 0.8, 'n': 10, 'ci': {'tool_ok': [1.0, 1.0], 'params_all_ok': [0.6, 1.0], 'full_call_ok': [0.6, 1.0]}}
cparam A6 ok
```

`n` 10, `tool_ok` 1.0, `params_all_ok` 0.8, `full_call_ok` 0.8 for both, the numbers
ticket 10 expects; `fires.parquet` is absent for both generator runs.

**(d) Ticket 10's A7 with the new names.**

```
$ /home/y-guo/reproduce/new1/external/probe-env/bin/python - <<'PY'
import sys; sys.path.insert(0, ".")
from data.environments import open_env
from eval.utils import probe_eval as pe
env = open_env("appworld")
assert pe.match_ctool("apis.a.x", "apis.a.x", None) is True
assert pe.match_ctool("apis.a.x", "apis.b.y", None) is False
good = env.build_call("apis.a.x", [("k", "1")])
bad  = env.build_call("apis.a.x", [("k", "2")])
assert pe.match_cgen(good, good, env) == {"tool_ok": True, "params_all_ok": True, "full_call_ok": True}
assert pe.match_cgen(bad, good, env)["params_all_ok"] is False
assert pe.match_cgen("not a call at all", good, env) == {"tool_ok": False, "params_all_ok": False, "full_call_ok": False}
none0 = env.build_call("apis.a.x", [])
assert pe.match_cgen(good, none0, env)["params_all_ok"] is False     # the dropped noparam short-circuit
assert pe.match_cparam(good, good, env)["params_all_ok"] is True
print("A7 ok")
PY
A7 ok
```

**(e) The ast checks.**

```
VERSION = 1
PROBE_KIND = {'ctool': 'classifier', 'cgen': 'generator', 'cparam': 'generator'}
MATCH_VERSION = {'ctool': 1, 'cgen': 1, 'cparam': 1}
no eval/methods directory: True
literals ok
```

Exactly one column-zero assignment each of `VERSION`, `PROBE_KIND` and
`MATCH_VERSION`; `ast.literal_eval` succeeds on both tables; no file under
`eval/methods/` and no such directory. In the worktree itself,
`git ls-files eval` lists exactly `eval/method_table.py`, `eval/score_run.py`,
`eval/utils/probe_eval.py`.

**(f) schema.** The fixture is ticket 04's, with `experimental_settings` and
`constants` copied whole with `cp -a`, `train/utils/trainer.py` and
`train/methods/<m>.py` stubbed as ticket 04's acceptance does, and
`eval/utils/probe_eval.py` stubbed as `VERSION = 1` plus the two table literals in
place of ticket 04's `eval/methods/<m>.py` stubs.

```
=== _method_kind ===
  _method_kind('ctool') = 'classifier'
  _method_kind('cgen') = 'generator'
  _method_kind('cparam') = 'generator'
  refusal: probe.method 'ctoool' is not a key of PROBE_KIND in eval/utils/probe_eval.py; it holds ['cgen', 'cparam', 'ctool']

=== schema.load + schema.key over the fixture tree ===
  train_probe/ctool_qwen3_0pt6b train: key=a7f5ebd1adbe
    versions={"train/utils/trainer.py": 1, "train/methods/ctool.py": 1, "eval/utils/probe_eval.py#MATCH_VERSION.ctool": 1, "data/training_data.py": 1, "data/probe_output.py": 1, "models/probe_models/base.py": 1, "models/probe_models/qwen.py": 1}
  train_probe/ctool_qwen3_0pt6b eval: key=67e377456b8e
    versions={"eval/utils/probe_eval.py": 1, "data/probe_output.py": 1}
  train_probe/cgen_qwen3_0pt6b train: key=7c509d3a79fa
    versions={"train/utils/trainer.py": 1, "train/methods/cgen.py": 1, "eval/utils/probe_eval.py#MATCH_VERSION.cgen": 1, "data/training_data.py": 1, "data/probe_output.py": 1, "models/probe_models/base.py": 1, "models/probe_models/qwen.py": 1}
  train_probe/cgen_qwen3_0pt6b eval: key=c622550d0044
    versions={"eval/utils/probe_eval.py": 1, "data/probe_output.py": 1}
  train_probe/cparam_qwen3_0pt6b train: key=d047fc949418
    versions={"train/utils/trainer.py": 1, "train/methods/cparam.py": 1, "eval/utils/probe_eval.py#MATCH_VERSION.cparam": 1, "data/training_data.py": 1, "data/probe_output.py": 1, "models/probe_models/base.py": 1, "models/probe_models/qwen.py": 1}
  train_probe/cparam_qwen3_0pt6b eval: key=b710e6d08915
    versions={"eval/utils/probe_eval.py": 1, "data/probe_output.py": 1}

inject/probe_p1_e1_theta_0pt80 inject: key=373d26d8bc27
  versions={"agent/loop.py": 1, "agent/generate.py": 1, "agent/inject.py": 1, "agent/inject_format.py": 1, "data/probe_input.py": 1, "data/trajectory_record.py": 1, "data/environments/__init__.py": 1, "data/environments/appworld.py": 1, "models/agent_models/gptoss.py": 1, "models/agent_models/service.py": 1, "models/probe_models/base.py": 1, "models/probe_models/service.py": 1, "eval/utils/probe_eval.py": 1, "eval/utils/probe_eval.py#MATCH_VERSION.ctool": 1}
inject/no_probe_p1_e1_theta_0pt80 inject: key=6d18fcc8d2d0
  versions={"agent/loop.py": 1, "agent/generate.py": 1, "agent/inject.py": 1, "agent/inject_format.py": 1, "data/probe_input.py": 1, "data/trajectory_record.py": 1, "data/environments/__init__.py": 1, "data/environments/appworld.py": 1, "models/agent_models/gptoss.py": 1, "models/agent_models/service.py": 1, "models/probe_models/base.py": 1, "models/probe_models/service.py": 1, "eval/utils/probe_eval.py": 1, "eval/utils/probe_eval.py#MATCH_VERSION.ctool": 1}
```

No `eval/methods` path in any block, and all eight keys equal round 1's, which is
the proof this round changed nothing that keys.

**(g) The grep over the code directories.**

```
$ grep -rn "eval/methods\|eval\.methods" experimental_settings data models eval agent jobs tests README.md .scratch/from-zero/issues | sed 's/:.*//' | sort | uniq -c
     12 .scratch/from-zero/issues/04-setting-schema-and-loader.md
     12 .scratch/from-zero/issues/08-eval-library-and-classifier-metric.md
     19 .scratch/from-zero/issues/10-eval-generators-scorer-and-table.md
```

Zero hits in `experimental_settings/`, `data/`, `models/`, `eval/`, `agent/`,
`jobs/`, `tests/` and `README.md`. **Ticket 16's line 117 is gone**, which is this
round's point. The bare-`methods/` spelling that hid the README defect is gone too:

```
$ grep -n "methods/" README.md
78:             train/methods/{ctool,cgen,cparam}.py (their target column)
188:                 train/methods/cgen.py, train/methods/cparam.py (open_env, for the environment their
261:        used by: train/utils/trainer.py, train/methods/{ctool,cgen,cparam}.py,
344:        used by: train/methods/{ctool,cgen,cparam}.py (match_<method>, for their validation metric),
```

All four remaining `methods/` hits in `README.md` are `train/methods/`, which the
ruling keeps as one file per method.

**Ticket 04 still hits, 12 times, and I left it.** The acceptance clause names
tickets 08 and 10, the wave-4 sdd reports and the errata as the allowed set, so
ticket 04 is formally outside it and this is the one clause of (g) that does not
hold literally. The reason I left it: ticket 04 is merged and built, exactly like
08 and 10, and the round-2 dispatch — which quotes round 1's section 5 (g), where
both ticket 04 and ticket 16 were named as open — ordered only ticket 16, on the
stated ground that ticket 16 is unbuilt and therefore an instruction rather than
history. Ticket 04 fails that test the same way 08 and 10 do. What it costs is
recorded once more so the main session can decide in one line: ticket 04's hits are
the quoted `STAGES` literal (4 lines), the fixture script that stubs
`$FIX/eval/methods/<m>.py`, the `B4` axis check over `glob.glob('eval/methods/*.py')`,
the `{probe_score_method}` paragraph and two wave-2 closeout Comments. The fixture
script and the `B4` check are runnable and would now be wrong; section (f) above is
that same fixture with the `eval/methods/` stubs replaced by one
`eval/utils/probe_eval.py` stub carrying the two tables, which is the edit ticket 04
needs if anyone re-runs it.

**Nothing under the real outputs root, nothing in the real ledger.**

```
$ R=/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs
$ for K in aaaaaaaaaaaa bbbbbbbbbbbb 4444dddd4444 5555eeee5555 dddddddddddd eeeeeeeeeeee 6666ffff6666 7777aaaa7777; do find "$R" -maxdepth 4 -name "$K" -print; done
(no output)
$ wc -l /home/y-guo/reproduce/new1/jobs/runs.jsonl
0 /home/y-guo/reproduce/new1/jobs/runs.jsonl
```

Every fixture directory was under `/tmp/tmp.JOCcd5l6Up/outputs`, which is deleted.
The main repo's working tree is untouched apart from this report file.

### 5. Commits

| sha | what |
|---|---|
| `e99d241` | `fold:` `README.md`'s eval-folder line names the new home of a probe method |
| `a7a2f94` | `fold:` ticket 16's extension recipe names the new home of a probe method |

### 6. Self-review, and what is open

- **`run.py selfcheck` could not be run**: `run.py` is ticket 14's and does not
  exist on this branch. The checks it will make over these two lines are covered by
  (a), (e), (f) and (g); the `README.md` line changed carries no `.py` path, so it is
  not an entry `readme_entries` returns and ticket 14's `D1` expectation of
  `31 True` is unaffected.
- **Ticket 04 is the one item left open**, argued in (g) above. It is a one-line
  decision for the main session: rewrite its fixture script and `B4` check the way
  (f) does, or record it as history that is not re-run.
- **Nothing else changed.** No code, no `notes/`, no `experimental_settings/*.yaml`,
  no `models/table.yaml`, no `VERSION` bump, no compatibility shim, no new file.
- **One protocol slip, with no consequence**: two marker files holding the temp
  root's path (`/tmp/fold2_s.txt`, `/tmp/fold2_fix.txt`) were written directly in
  `/tmp` rather than inside the `mktemp -d` tree, because the shell's working
  directory resets between calls and the path had to survive. Both are deleted, and
  every fixture, script and output still lived inside `/tmp/tmp.JOCcd5l6Up`.
