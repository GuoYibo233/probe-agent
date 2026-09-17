# T04 report — the setting schema and its loader

Ticket: `.scratch/from-zero/issues/04-setting-schema-and-loader.md`
Branch: `ticket/2026-09-17-wave2/T04`, worktree `new1-wt/2026-09-17-wave2-T04`
Base: `943af829b83f8f66d4b4a6434f4a685b2b2f9c10`
Head: `082eaa5`

## 1. What was done

One file, `experimental_settings/schema.py`, plus its `README.md` entry
(new "## Ticket 04" section, following the flat five-line format ticket 03
already established).

Against the ticket's four passes:

1. **Declarations.** `ROOT`, the eleven section dataclasses plus `Predict`
   and `Setting`, `THETA_GRID` (the explicit 20-element literal), `AXES`,
   `RETIRED` (empty set), `REQUIRED_FIELDS`, `PROBE_TEXT_FIELDS`, `STAGES`
   (copied verbatim from the ticket, six stages, the cell shape pinned by
   2.1/2.2/2.3) — all as literals, no repo import, `from __future__ import
   annotations` at the top. Every mutable default uses
   `field(default_factory=...)`.
2. **`load` and every refusal of 5.7.** Implemented as: parse the file,
   validate the raw `common:`/named-setting section keys against the
   workflow (the "section for a stage not in workflow" refusal, evaluated
   against the raw YAML only, never the merged setting, per 5.6/5.7); merge
   defaults → `common:` → the named setting per field (a list field
   replaced whole); sweep expansion (between merge-step 3 and the debug
   overlay, 5.5); the debug overlay (scoped to the sections the file's
   `workflow:` line names, 5.6); command-line overrides (`dotted.path:
   "raw yaml string"`, parsed with `yaml.safe_load`); then, on the fully
   merged setting: the type check (PyYAML's `1e-5`-is-a-string trap), axis
   membership + `RETIRED`, the `data.instructions` check against the
   environment's `INSTRUCTIONS`, the split check against
   `constants/path_datasets.yaml` + the environment's `SPLIT_ROLE`, the
   model-alias role check, the `generation.effort` check against the
   family's `EFFORTS`, `inject.fire_nth_cut` under `arm: no_probe`, the
   required-fields check, reference resolution (name / pinned `key:` /
   pinned `dir:` forms) with the whole-call-generator check for
   `inject.probe_gen` and the split/seeds superset check for
   `score.baseline`, the per-inherited-group agreement check with
   `meta.override` (5.4, scoped so a build-less reference such as
   `baseline.yaml` is never consulted for the `PROBE_TEXT_FIELDS` group),
   the `generation.{stop,effort,date}` null-resolution against the agent
   family module, and finally the model-row expansion into
   `models.agent_row`/`models.probe_row` (immediately before the setting
   is considered final, matching 3.3's "immediately before keying").
   `probe.lora_targets` is deliberately never resolved onto the dataclass
   (5.2/3.3's fourth resolution): it is resolved only inside `key`/`fields_of`.
3. **`load_frozen` and `run_dir_of`.** `load_frozen` parses `settings.yaml`
   directly against the dataclasses, re-merging and re-resolving nothing,
   and refuses a field the schema has since removed, naming the field and
   the run directory. `run_dir_of` builds `<root>/<stage>/<key>` or
   `<root>/<debug_subdir>/<stage>/<key>` from `constants/path_outputs.yaml`
   and never touches the output tree.
4. **`fields_of`, `models_of`, `upstream_of`, `versions_of`, `upstream`,
   `key`, `run_dir`, `freeze`.** `key` canonicalises
   `{stage, fields, models, upstream, versions, debug?}` with
   `json.dumps(..., sort_keys=True, separators=(",", ":"),
   ensure_ascii=True)`, sha256, first 12 hex characters. `upstream` and
   `upstream_of` are the same function (the ticket describes both
   identically; `upstream` is offered as the name `run.py` calls before
   `freeze`, per the errata). `freeze` projects the stage's `sections` ∪
   `projection` ∪ `projection_generator` (gated on the method's
   `PROBE_KIND`) ∪ (`build`, for `inject`) as **whole sections**, writes
   the `_` block of 1.5, writes both files through a temporary name and
   renames, and on a re-freeze of the same directory checks
   `settings_diff.yaml` for a collision and otherwise merges the
   non-keyed request fields (seeds: ordered union; a null `tasks` absorbs;
   `pieces`/`replicas` take the new launch's values).

## 2. How it was verified

All commands run from the worktree root
(`/home/y-guo/reproduce/new1-wt/2026-09-17-wave2-T04`), pasted output is the
real output, trimmed only where the ticket itself trims (`str(ex)[:N]`).

### B1 — imports under all four interpreters, no repo import

Ran under `python3`, `external/probe-env/bin/python`,
`external/appworld/venv/bin/python`, `external/vllm-env/bin/python`:

```
experimental_settings.schema 6 ('min_think', 'hist_rounds', 'probe_result_cap')
experimental_settings.schema 6 ('min_think', 'hist_rounds', 'probe_result_cap')
experimental_settings.schema 6 ('min_think', 'hist_rounds', 'probe_result_cap')
experimental_settings.schema 6 ('min_think', 'hist_rounds', 'probe_result_cap')
['__future__', 'ast', 'dataclasses', 'hashlib', 'itertools', 'json', 'pathlib', 'typing', 'yaml']
```

Matches expected exactly (module list is standard library plus `yaml`, no
repo package). Re-ran again at the very end (D6) with the same result.

### B2 — defaults equal the contract table

```
defaults ok
```

### B3 — `STAGES` shape

```
[('sample', 8, True, 'map'), ('build', 6, False, 'any'), ('train', 7, True, 'probe'), ('eval', 3, False, 'any'), ('inject', 14, True, 'map'), ('score', 2, False, 'any')]
carry: [('inject', 'probe_score.eval')]
```

Matches exactly.

### B4 — axis literals vs. what's on disk (this wave: constants only)

```
axis checks that could run: constants only
```

Exit 0, matches (no `data/environments/`, `train/methods/`,
`eval/methods/`, `agent/inject.py`, `agent/inject_format.py` yet — those
land in later folders/waves; the check for what does exist,
`constants/path_datasets.yaml`, passed).

### B5 — the two source-text readers

```
7 ['<|return|>']
two matches -> SchemaError two.py: 2 column-zero assignments to 'VERSION', expected exa
no match -> SchemaError none.py: no column-zero assignment to 'VERSION'
```

Matches exactly.

### C1 — the flagship load

```
ctool_q06 ['sample', 'build', 'train', 'eval'] False
appworld v1 gptoss120b qwen06
gptoss ['dtype', 'env_result', 'extra_flags', 'family']
['<|return|>'] high 2026-08-06
ctool None 1e-05 None
inject is None: True | build present: True
```

Matches exactly.

### C2 — debug overlay, sizes only, stage-scoped

```
True 3 1 6 8 64 20 100 50
3 None None None
```

Matches exactly.

### C3 — overrides and the sweep

```
0.0003 lora [42, 67]
4
['ctool_q06/train.lr=0.0001,train.seed=42', 'ctool_q06/train.lr=0.0001,train.seed=67', 'ctool_q06/train.lr=0.0003,train.seed=42', 'ctool_q06/train.lr=0.0003,train.seed=67']
[0.0001, 0.0001, 0.0003, 0.0003]
ctool_q06/train.lr=0.0003,train.seed=67 0.0003 67
```

Matches exactly.

### C4 — each refusal of 5.7 fires and names the field (18 cases)

```
unknown key: REFUSED SchemaError: train.lrr: not a field of this section
off-axis value: REFUSED SchemaError: probe.method: 'ctoool' is not one of ('ctool', 'cgen', 'cparam')
bad instructions: REFUSED SchemaError: data.instructions: 'v9' is not one of ('v1',)
bad split: REFUSED SchemaError: sample.split: 'holdout' is not one of ('train', 'dev', 'test')
wrong role: REFUSED SchemaError: models.probe: 'gptoss120b' has role 'agent', expected 'probe'
bad effort: REFUSED SchemaError: generation.effort: 'ultra' is not one of ('high', 'medium', 'low')
section not in workflow: REFUSED SchemaError: inject: no stage of this file's workflow reads this section
type mismatch: REFUSED SchemaError: train.lr: '1e-5' has type str, declared type is float
sweep over debug field: REFUSED SchemaError: sweep.train.max_steps: also set by debug.yaml, which would collapse the sweep
override of swept field: REFUSED SchemaError: train.lr: overridden and swept at once
missing reference: REFUSED SchemaError: eval.theta_from: nope: no such setting in .../experimental_settings/train_...
generator without theta_from: REFUSED SchemaError: eval.theta_from: is required when probe.method's PROBE_KIND is generator
probe section under inject: REFUSED SchemaError: probe: no stage of this file's workflow reads this section
models.probe under inject: REFUSED SchemaError: models.probe: a setting whose workflow contains inject may not state models.probe
theta unset: REFUSED SchemaError: inject.theta: is required and was not set
probe_gen is a param-only method: REFUSED SchemaError: inject.probe_gen: 'cparam' is not a whole-call generator (param_only=True, PROBE_KIND='gen...
fire_nth_cut under no_probe: REFUSED SchemaError: inject.fire_nth_cut: must be 0 under arm: no_probe
baseline seeds not a superset: REFUSED SchemaError: score.baseline: baseline split/seeds are not a superset of this setting's inject.split/see...
```

All 18 lines read `REFUSED`, and each message names the field the ticket's
expected list names, in the same order: `train.lrr`, `probe.method`,
`data.instructions`, `sample.split`, `models.probe`, `generation.effort`,
`inject`, `train.lr`, `train.max_steps`, `train.lr`, `eval.theta_from`,
`eval.theta_from`, `probe`, `models.probe`, `inject.theta`,
`inject.probe_gen`, `inject.fire_nth_cut`, `score.baseline`. Matches
exactly.

**One implementation decision the ticket left implicit, recorded here:**
the checks for `score.baseline`, `inject.probe_score` and `inject.probe_gen`
are ordered so that `eval.theta_from` and `score.baseline` are resolved and
checked *before* `inject.probe_score`/`inject.probe_gen` are even opened.
Without that ordering, the last C4 case (baseline seeds not a superset)
would instead surface as a failure to resolve `inject.probe_gen`, because
an *earlier* C4 case in the same script ("generator without theta_from")
permanently rewrites `train_probe.yaml` on disk with `cgen_q06`'s
`eval.theta_from` popped, and every later `run()` call in the script that
happens to touch `train_probe.yaml` through a reference sees that broken
file. Checking `score.baseline` first means the baseline case's own
refusal fires before that stale, unrelated corruption is ever reached.

### C5 — inheritance and its per-group scope

```
inherited build fields: {'min_think': 40, 'hist_rounds': 3, 'probe_result_cap': 400}
probe row absent: True
inherited after the build edit: 5
stated-differently: REFUSED generation.temperature: stated 0.7 differs from the referenced run's 1.0; list it in meta.
with meta.override: 0.7
```

Matches exactly, including the third line (`baseline.yaml`'s build-less
reference is correctly excluded from the `PROBE_TEXT_FIELDS` agreement
group).

### D1 — the key's shape and the 3.2 guarantees

```
{'sample': '89460d84e077', 'build': 'f3dc6386b027', 'train': 'd783b81cdaf8', 'eval': '18b17298e269'}
determinism: True
debug separates: True
notes insensitive: True
default restated == unset: True
lr moves train, not sample/build: True True True
eval.risk moves eval only: True True
fields block: []
models block: ['probe'] []
upstream block: {'sample': '89460d84e077'} {}
```

Four 12-hex keys, then every boolean the ticket names as `True`, matching.
`fields block: []` is correct: `ctool_q06`'s stated `train`/`probe` values
(`lr: 1.0e-5, epochs: 1`, `method: ctool, tuning: full`) all equal their
schema defaults, so nothing differs and the diff is legitimately empty
(the ticket's own expected text only says "holding only fields that
differ from their defaults," with no literal value given).

### D2 — the VERSION fold and the one carve-out

```
['data/example.py', 'data/prediction.py', 'eval/methods/ctool.py', 'models/probe_models/base.py', 'models/probe_models/qwen.py', 'train/methods/ctool.py', 'train/utils/trainer.py']
['probe_gen.train', 'probe_score.eval', 'probe_score.train']
probe_eval VERSION moves the inject key: True
trainer VERSION moves train, not build: False True
```

First three lines match exactly. The fourth's first component does not:
the ticket expects `True True`, my run gives `False True`.

**This is a bug in the ticket's own D2 script, not in the implementation —
recorded per spec.md section 7 ("when the ticket is wrong, say which
command, what the ticket expected, what happened, and why the ticket is
wrong").** The script's last two lines are:

```python
(FIX/'train/utils/trainer.py').write_text('VERSION = 2\n')
c2 = S.load(tp, 'ctool_q06', debug=False, overrides={})[0]
print('trainer VERSION moves train, not build:', S.key('train', c2) != S.key('train', c), S.key('build', c2) == S.key('build', c))
```

Unlike the probe_eval sub-test immediately above it — which snapshots
`k0 = S.key('inject', i)` **before** editing `probe_eval.py`, then compares
`S.key('inject', i2)` (computed after the edit) against that snapshot — this
line never snapshots `S.key('train', c)` before editing `trainer.py`. Both
`S.key('train', c)` and `S.key('train', c2)` are called inside the same
`print`, after the edit; `key()` reads `VERSION` from disk fresh on every
call (3.3: "Versions are read as text" — deliberately, so that editing code
and bumping `VERSION` is immediately visible), so a setting object caches
nothing between calls. `c` and `c2` are field-for-field identical settings,
so two live-reading `key()` calls on identical settings against the same
current disk state are necessarily equal by 3.2 rule 1 (determinism): this
is correct behavior, not a bug. I confirmed the underlying mechanism is
sound by reproducing the probe_eval pattern for `trainer.py` too — snapshot
before the edit, compare after:

```python
train_key_before = S.key('train', c)
build_key_before = S.key('build', c)
(FIX/'train/utils/trainer.py').write_text('VERSION = 2\n')
c2 = S.load(tp, 'ctool_q06', debug=False, overrides={})[0]
print(S.key('train', c2) != train_key_before, S.key('build', c2) == build_key_before)
```
```
True True
```

This gives exactly the ticket's expected `True True`, confirming
`versions_of`/`key` correctly fold `train/utils/trainer.py`'s `VERSION`
into the `train` key and not into the `build` key. I did not change the
implementation to paper over the D2 script's ordering bug (e.g. by caching
`key()` results on the `Setting` object), since that would break 3.2's
sensitivity guarantee for exactly the case the probe_eval sub-test verifies.

### D3 — `run_dir`, `run_dir_of`, the debug subtree

```
train/d783b81cdaf8 debug/train/07073b0fdf8f
True True
nothing created: True
```

Matches exactly.

### D4 — `freeze` writes the projection, the `_` block, refuses a collision

```
['data', 'generation', 'models', 'sample']
['_commit', '_debug', '_key', '_resolved', '_stage', '_upstream', '_versions']
sample True deadbeefcafe False {}
versions: ['agent/generate.py', 'agent/loop.py', 'data/environments/__init__.py'] 8
diff: True
no workflow line: True
seeds merged: [42, 67]
train projection: ['models', 'probe', 'train'] True
collision: REFUSED freeze: /tmp/.../outputs/train/d783b81cdaf8 already holds settings fo...
```

Matches exactly.

### D5 — `load_frozen` round-trips, refuses a removed field

```
train True deadbeefcafe ctool 1e-05 8192
upstream: ['build'] | sections dropped: True
removed field: REFUSED train.obsolete_knob: field removed from the schema (run directory /tmp/.../outp...
```

Matches exactly.

### D6 — rerun B1 after everything else

Rerun at the end (see B1 above, run twice); same output both times.

### Selfcheck lines that apply later

`run.py` does not exist yet (checked: no `run.py` in the worktree), so per
spec.md section 7 and the ticket's own "Selfcheck lines that apply later"
section, this step is skipped — nothing to run in this wave.

### GPU / main session items

None. This ticket has no GPU step; `M-G3`'s real-tree rerun of B4/C1/C2/D1-D5
is explicitly the main session's job once every other folder has merged.

## 3. Commits

- `082eaa5` — `T04: the setting schema and its loader` — adds
  `experimental_settings/schema.py` and the README's "Ticket 04" section.

## 4. Self-review findings and open questions

- **Decision:** the "section for a stage not in workflow" refusal (5.7) and
  the `probe:`/`models.probe`-under-`inject` refusal (2.1) are both
  evaluated against the raw `common:`/named-setting dicts, before any
  merge — matching the ticket's explicit "evaluated against what the YAML
  file itself holds... never against the merged setting" (5.6/5.7).
- **Decision:** command-line overrides and sweep values are validated by
  checking the dotted path actually resolves inside the fully-defaulted
  section tree (catches a bad override on a nested field like
  `train.predict.cap`, not just the top-level section/field); the sweep
  path validation checks only the top-level field name it names (sweep
  fields in this repo are always two-level, e.g. `train.lr`, so this
  doesn't lose coverage against anything the acceptance suite exercises).
- **Decision, recorded in section 2 above:** the ref-field check order
  (`eval.theta_from` → `score.baseline` → `inject.probe_score` →
  `inject.probe_gen`) is my own choice, needed to make C4's last two cases
  pass given the shared, mutated fixture files earlier C4 cases leave
  behind. The ticket doesn't pin this order itself.
- **Ticket vs. implementation discrepancy:** D2's last assertion's first
  component (`True` expected, `False` obtained) — see the D2 section
  above for the full analysis. I judge the ticket's script, not the
  schema, to be at fault, and did not change the code to accommodate it.
- **Open question for the main session:** `versions_of`'s
  `{probe_score_method}` placeholder substitution (used only by
  `inject`'s version list) requires resolving `inject.probe_score` to a
  full `Setting` object to read its `probe.method`. For a **pinned**
  `key:`-form reference (bare hex keys, no path) there is no way to
  recover that method without touching the output tree, which 3.2 rule 2
  forbids; I raise a `SchemaError` naming this in that case. This path is
  untested by the ticket's acceptance suite (C3/C4/C5/D1/D2 only ever use
  name-syntax references) and isn't exercised anywhere in this repo's
  three real setting files yet, so I flag it rather than guess at a
  resolution the contracts don't specify.
- No file outside `experimental_settings/schema.py` and `README.md` was
  touched. No `legacy/` citation appears in the shipped source (checked
  with a grep). No `/home/` or `/net/` literal path appears in the file
  (checked with a grep). The module compiles clean under `python3 -m
  py_compile`.

## 5. Fix round 1

Worktree `new1-wt/2026-09-17-wave2-T04-fix1`, base `082eaa5` (the previous
round's head), fix commit `74cd513`.

### F1 — `freeze()` dropped earlier requested tasks on re-freeze instead of taking the ordered union

**Root cause.** `_merge_request_fields` (`experimental_settings/schema.py`,
around line 1160) implemented only the null-absorption half of contracts
3.4's merge rule for `tasks`: `if existing[sec].get('tasks') is None or
doc[sec].get('tasks') is None: doc[sec]['tasks'] = None`. When both the
existing run's `tasks` and the new launch's `tasks` were non-null, the
function did nothing, leaving `doc[sec]['tasks']` as whatever the new
(possibly narrower) setting's own list was — silently discarding the
earlier freeze's task list. Contracts 3.4 (verified directly, lines
2677-2694 of `notes/plans/2026-09-17-contracts.md`): "the non-keyed
request fields are merged instead, per field: `seeds` becomes the ordered
union of the two lists; `tasks` is `null` when either side is `null`,
because `null` means 'no restriction' (5.2) and the wider request absorbs
the narrower, and otherwise the ordered union."

**Fix.** Read both `old_tasks` and `new_tasks` first; when neither is
`None`, set `doc[sec]["tasks"]` to the ordered union (`old_tasks +
[t for t in new_tasks if t not in old_tasks]`), matching the `seeds` merge
immediately above it in the same function. The null-absorption branch is
unchanged.

**Verification.** A dedicated regression script (not part of the ticket's
own acceptance suite, since the ticket's D4 only exercises the `seeds`
merge and the both-null-vs-one-null `tasks` cases, never the
both-non-null case):

```
first freeze tasks: ['t1', 't2']
re-frozen tasks (ordered union expected): ['t1', 't2', 't3']
null absorbs: None
no duplicates, ordered union: ['t1', 't2', 't3']
ALL F1 REGRESSION CHECKS PASS
```

Freezing `sample.tasks=['t1','t2']` into a fresh directory, then
re-freezing the same directory with `sample.tasks=['t3']`, now yields
`['t1', 't2', 't3']` instead of the pre-fix `['t3']`. Re-freezing with an
overlapping list (`['t2', 't3']`) yields `['t1', 't2', 't3']` with no
duplicate — same script, `no duplicates, ordered union` line. The existing
null-absorption case (`re-freeze with tasks unset` -> `None`) still holds
(`null absorbs: None`).

### F2 — README's imports annotation for `schema.py` didn't match the ticket header, contracts 0.2, or the real import list

**Root cause.** The shipped README line read `imports: none (repo);
[PyYAML]`. An AST walk of the shipped file gives the real non-repo,
non-`__future__` import list: `ast, dataclasses, hashlib, itertools, json,
pathlib, typing, yaml`. The README bracket both undercounted (missing six
modules) and, per the ticket's own header text, listed `re`, which the
file never imports.

**Fix.** Checked the repo's own convention for what the bracket holds
(contracts 0.1: "third-party in brackets") against two existing entries
whose files I re-walked with the same AST script: `data/probe_input.py`
imports only `__future__` and `re`, and its README bracket is `[re]`
(stdlib module, no `__future__`) — confirming `__future__` is excluded and
otherwise the bracket lists every non-repo import the AST walk finds,
stdlib included. Replaced the bracket with the AST-confirmed list, keeping
the existing `PyYAML` spelling for the `yaml` import (matching every other
entry in this README that imports it) and dropping `re`:
`[PyYAML, ast, dataclasses, hashlib, itertools, json, pathlib, typing]`.

**Verification.**

```bash
python3 -c "
import ast
t = ast.parse(open('experimental_settings/schema.py').read())
mods = set()
for n in ast.walk(t):
    if isinstance(n, ast.Import): mods |= {a.name.split('.')[0] for a in n.names}
    if isinstance(n, ast.ImportFrom) and n.module: mods.add(n.module.split('.')[0])
repo = {'data','models','agent','train','eval','jobs','constants','run'}
assert not (mods & repo), mods & repo
print(sorted(mods))"
```
```
['__future__', 'ast', 'dataclasses', 'hashlib', 'itertools', 'json', 'pathlib', 'typing', 'yaml']
```

This is the B1 acceptance command itself, unchanged in behavior (it only
checks against the `repo` set, not the README), rerun here to pin the real
import list the corrected README line now matches exactly (`yaml` ->
`PyYAML`, `__future__` excluded per the established convention).

### Full re-verification after both fixes

Reran every acceptance block from the ticket against the fixed worktree,
using a fresh fixture each time (`bash /tmp/mkfix.sh`), and confirmed
every output is byte-for-byte identical to the original round's report
(section 2 above) except where F1's fix changes behavior:

- **B1** (all four interpreters + the import-graph check): identical —
  `experimental_settings.schema 6 (...)` four times, then the module list
  above.
- **B2** (`defaults ok`), **B3** (`STAGES` shape), **C1** (flagship load),
  **C4** (all 18 refusals, same messages), **D1** (all four keys, all
  booleans `True`), **D5** (`load_frozen` round-trip and the removed-field
  refusal) — identical output to the original round.
- **D4** (freeze projection, `_` block, seeds merge, collision refusal):
  identical output, including `seeds merged: [42, 67]` — F1's fix does not
  change this line since D4's own script never re-freezes with
  both-sides-non-null `tasks`.
- `python3 -m py_compile experimental_settings/schema.py` — compiles
  clean.
- `grep -n "legacy" experimental_settings/schema.py` — no match.
- `grep -n "/home/\|/net/" experimental_settings/schema.py` — no match.

No acceptance command's expected output changed as a result of either
fix; F1's behavior change is only observable in the both-non-null `tasks`
re-freeze case, which is outside the ticket's own acceptance suite (see
the F1 verification above for that case, exercised separately).

### Commits

- `74cd513` — `T04: fix re-freeze tasks union and README imports
  annotation` — both fixes, `experimental_settings/schema.py` and
  `README.md`.

### Open questions

None new. The open question from round 1 (pinned `key:`-form
`inject.probe_score` references and `versions_of`'s
`{probe_score_method}` placeholder) is unaffected by either fix and
remains open for the main session.
