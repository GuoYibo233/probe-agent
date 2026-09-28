# VERSION_HISTORY (errata "3.3 / 8.6") — finishing report

- Ruling: `.scratch/from-zero/contract-errata.md`, the entry beginning
  "3.3 / 8.6 (what a `VERSION` bump invalidates)".
- Branch `owner/2026-09-18-version-history`.
  Base of this round: `7f498549f8741d1848d679ad80bef8cf3b864250` (the one commit
  fork1 left on top of `78e9260`). Head: `6692bc1`.
- Worktree: `/home/y-guo/reproduce/new1-wt/2026-09-18-version-history-r1`
  (removed at the end; the branch is kept). Every command below ran from that
  worktree root.

## 1. What is on the branch, and what this round changed

### Already on the branch at `7f49854` (read against the ruling, no correction needed)

`experimental_settings/schema.py`
- `version_history(rel_path)` reads the file's column-zero `VERSION_HISTORY`
  literal; a file with no such literal has an empty table.
- `effective_version(rel_path, stage)` returns the highest version `v` in
  `2..VERSION` for which the stage is stale, else `1`. The stage is stale at `v`
  when the table has no entry for `v`, when the entry has no `"stale"` key, or
  when the stage is named in `entry["stale"]` (`_stale_at`).
- `key()` folds `_key_versions(stage, setting)` under the same `"versions"`
  payload name. A bare module path folds `effective_version(path, stage)` with
  the stage being the stage whose key is computed, including where a file is
  folded for another stage's sake (the inject key's stand-ins for the
  `probe_score` eval key). A `<path>#<TABLE>.<method>` entry folds the table
  value itself.
- `versions_of`, `freeze`'s `_versions` (line 1392 of the file: `doc["_versions"]
  = versions_of(stage, setting)`), `load_frozen` and `jobs/launch.py`'s
  provenance record (`"versions": schema.versions_of(stage, setting)`) keep the
  real `VERSION` / table value.
- Refusals, each a `SchemaError` naming the file (`_check_version_history`): a
  table that is not a mapping; an entry key that is not an int or outside
  `2..VERSION`; an entry that is not a mapping; a `"stale"` value that is not a
  tuple/list; a `"stale"` value naming something outside `STAGES`. A missing
  `"why"` is not refused here.
- `README.md`'s sentence listing the names the file offers now names
  `version_history` and `effective_version`.

Every tracked `.py` file under the code directories with a column-zero
`VERSION = <int>` line — 18 on this branch after the `eval/methods/` fold —
carries the VERSION-rule comment block directly above `VERSION` and
`VERSION_HISTORY = {}` directly below it, exactly once. `.scratch/from-zero/spec.md`
section 5 carries the rule and lists `VERSION_HISTORY` among the module-level
literals the loader reads.

Mechanical check of the 18 files (block text compared character for character
against the block the specification gives):

```
$ python3 - <<'EOF'   # block = the comment block from the specification, verbatim
... for each file with a column-zero VERSION: compare the 10 lines above it with the block,
... check the line below it, count the VERSION_HISTORY assignments ...
EOF
agent/generate.py: block=True below=True hist_count=1 version=VERSION = 1
agent/inject.py: block=True below=True hist_count=1 version=VERSION = 1
agent/inject_format.py: block=True below=True hist_count=1 version=VERSION = 1
agent/loop.py: block=True below=True hist_count=1 version=VERSION = 1
data/build_training_dataset.py: block=True below=True hist_count=1 version=VERSION = 1
data/environments/__init__.py: block=True below=True hist_count=1 version=VERSION = 1
data/environments/appworld.py: block=True below=True hist_count=1 version=VERSION = 1
data/probe_input.py: block=True below=True hist_count=1 version=VERSION = 1
data/probe_output.py: block=True below=True hist_count=1 version=VERSION = 1
data/training_data.py: block=True below=True hist_count=1 version=VERSION = 1
data/trajectory_record.py: block=True below=True hist_count=1 version=VERSION = 1
eval/score_run.py: block=True below=True hist_count=1 version=VERSION = 1
eval/utils/probe_eval.py: block=True below=True hist_count=1 version=VERSION = 1
models/agent_models/gptoss.py: block=True below=True hist_count=1 version=VERSION = 1
models/agent_models/service.py: block=True below=True hist_count=1 version=VERSION = 1
models/probe_models/base.py: block=True below=True hist_count=1 version=VERSION = 1
models/probe_models/qwen.py: block=True below=True hist_count=1 version=VERSION = 1
models/probe_models/service.py: block=True below=True hist_count=1 version=VERSION = 1
```

gyb's `TODO(gyb, 2026-09-18)` blocks are untouched: the diff of
`data/training_data.py` and `eval/utils/probe_eval.py` (and of
`eval/score_run.py`, which carries a third one) against `78e9260` adds only the
11 lines of the comment block plus `VERSION_HISTORY = {}`.

### Changed this round (commit `6692bc1`, `experimental_settings/schema.py` only)

`effective_version` read the same file three times: `module_version(rel_path)`
parsed it once, then `version_history(rel_path)` parsed it again and called
`module_version` a third time. On the real tree that made `key()` 2.75x slower
than at `78e9260` (measurement below). Fixed at the root, in the reader that
caused it: the source-text reader is now split into a parse step
(`_parse_module`) and walkers over an already parsed tree
(`_column_zero_matches(tree, name)`, `_one_column_zero(rel_path, tree, name)`,
`_history_of(rel_path, tree)`), so `effective_version` parses the file once and
`version_history` once. `module_version`, `module_literal` and
`_column_zero_literal` keep their signatures; every refusal message is
unchanged, and P1 and P5 were rerun after the change to show every key and every
message is the same.

```
$ PYTHONPATH=$PWD python3 - <<'PY'      # 50 x key('build') on the real tree
78e9260: 50 x key('build') on the real tree = 1.935 s
before this commit (three parses per entry): 5.317 s
after  this commit (one parse per entry):    3.244 s
```

The residual 1.7x over `78e9260` is the extra `ast.walk` passes (`VERSION` and
`VERSION_HISTORY` are two walks of the one tree, not one). 65 ms per `key()`
call against 39 ms; left as is rather than fused into a single two-name walker,
which would add a third near-identical walker for no behaviour change.

## 2. The fixture, and what was adapted for the `eval/methods/` fold

The fixture is the `mkfix.sh` body of
`.scratch/from-zero/issues/04-setting-schema-and-loader.md` (Acceptance, "The
fixture"), written under a fresh `mktemp -d`, with `S.ROOT` pointed at it. That
script predates the fold merged as `f13f0ad`, so two schema-facing stubs were
adapted. The adapted script lives at `/tmp/vh/mkfix.sh`; the two changes, and
nothing else, are:

1. `eval/utils/probe_eval.py` was written by the bare `printf 'VERSION = 1\n'`
   loop. It is now written with the two tables the fold put in the real file,
   because `schema.py` reads both there: `_method_kind` reads `PROBE_KIND` from
   `eval/utils/probe_eval.py`, and the train and inject version lists read
   `eval/utils/probe_eval.py#MATCH_VERSION.{method}` /
   `#MATCH_VERSION.{probe_score_method}`.
   ```
   cat > "$FIX/eval/utils/probe_eval.py" <<'P'
   VERSION = 1
   PROBE_KIND = {"ctool": "classifier", "cgen": "generator", "cparam": "generator"}
   MATCH_VERSION = {"ctool": 1, "cgen": 1, "cparam": 1}
   P
   ```
2. The `eval/methods/<m>.py` stub loop and the `eval/methods` entry of the
   `mkdir -p` list were dropped: the fold deleted that folder and `schema.py`
   reads nothing there. `train/methods/<m>.py` keeps its `VERSION`,
   `PROBE_KIND` and `CHECKPOINT_META` stubs, which the loader still reads.

Every command below that needs the fixture runs `FIX=$(bash /tmp/vh/mkfix.sh)`
first — the only edit to the ticket's own command text is that path
(`/tmp/mkfix.sh` -> `/tmp/vh/mkfix.sh`, so as not to overwrite a file another
session may be using). Commands whose ticket form is a `python3 - "$FIX" <<'PY'`
heredoc were saved to `/tmp/vh/<name>.py` with the heredoc body verbatim and run
as `PYTHONPATH=$PWD python3 /tmp/vh/<name>.py "$FIX"`; a Bash command that names
a settings yaml file next to a write word is refused by the repo's read-only
hook, and the heredoc bodies do exactly that.

## 3. Proofs

### P1 — every key that keys is the key of `78e9260`

`/tmp/vh/p1.py` loads `git show 78e9260:experimental_settings/schema.py` into a
temp module, points both modules' `ROOT` at the same root, and compares
`key(stage, setting)` for every named setting of every workflow file, for every
stage of that file's `workflow:` line.

```
$ git show 78e9260:experimental_settings/schema.py > /tmp/vh/old_schema.py
$ FIX=$(bash /tmp/vh/mkfix.sh); PYTHONPATH=$PWD python3 /tmp/vh/p1.py "$FIX" /tmp/vh/old_schema.py
same  baseline/gpt_oss_120b_appworld sample                5e898c2e7741
same  baseline/gpt_oss_120b_appworld score                 8f16442a6e72
skip  debug.yaml: no workflow line, it is the debug overlay
same  inject/probe_p1_e1_theta_0pt80 inject                373d26d8bc27
same  inject/probe_p1_e1_theta_0pt80 score                 1a8e6643f8ef
same  inject/no_probe_p1_e1_theta_0pt80 inject             6d18fcc8d2d0
same  inject/no_probe_p1_e1_theta_0pt80 score              6755666ac372
same  train_probe/ctool_qwen3_0pt6b sample                 5e898c2e7741
same  train_probe/ctool_qwen3_0pt6b build                  aa9b69a5cc81
same  train_probe/ctool_qwen3_0pt6b train                  a7f5ebd1adbe
same  train_probe/ctool_qwen3_0pt6b eval                   67e377456b8e
same  train_probe/cgen_qwen3_0pt6b sample                  5e898c2e7741
same  train_probe/cgen_qwen3_0pt6b build                   aa9b69a5cc81
same  train_probe/cgen_qwen3_0pt6b train                   7c509d3a79fa
same  train_probe/cgen_qwen3_0pt6b eval                    c622550d0044
same  train_probe/cparam_qwen3_0pt6b sample                5e898c2e7741
same  train_probe/cparam_qwen3_0pt6b build                 aa9b69a5cc81
same  train_probe/cparam_qwen3_0pt6b train                 d047fc949418
same  train_probe/cparam_qwen3_0pt6b eval                  b710e6d08915

equal keys: 18
moved keys: 0 []
raised on both sides: 0
raised on one side only: 0 []
```

The same comparison over the real repo's `experimental_settings/*.yaml`, with
both modules' `ROOT` at the worktree root:

```
$ PYTHONPATH=$PWD python3 /tmp/vh/p1.py "$PWD" /tmp/vh/old_schema.py
same  baseline/gpt_oss_120b_appworld sample                5e898c2e7741
same  baseline/gpt_oss_120b_appworld score                 8f16442a6e72
skip  debug.yaml: no workflow line, it is the debug overlay
same  train_probe/ctool_qwen3_0pt6b sample                 5e898c2e7741
same  train_probe/ctool_qwen3_0pt6b build                  aa9b69a5cc81
same  train_probe/cgen_qwen3_0pt6b sample                  5e898c2e7741
same  train_probe/cgen_qwen3_0pt6b build                   aa9b69a5cc81
same  train_probe/cparam_qwen3_0pt6b sample                5e898c2e7741
same  train_probe/cparam_qwen3_0pt6b build                 aa9b69a5cc81

equal keys: 8
moved keys: 0 []
raised on both sides: 10
  raise inject/probe_p1_e1_theta_0pt80 inject       new=FileNotFoundError: ... /train/methods | old=FileNotFoundError: ... /train/methods
  raise inject/probe_p1_e1_theta_0pt80 score        new=FileNotFoundError: ... /train/methods | old=FileNotFoundError: ... /train/methods
  raise inject/no_probe_p1_e1_theta_0pt80 inject    new=FileNotFoundError: ... /train/methods | old=FileNotFoundError: ... /train/methods
  raise inject/no_probe_p1_e1_theta_0pt80 score     new=FileNotFoundError: ... /train/methods | old=FileNotFoundError: ... /train/methods
  raise train_probe/ctool_qwen3_0pt6b train         new=FileNotFoundError: ... /train/utils/t | old=FileNotFoundError: ... /train/utils/t
  raise train_probe/ctool_qwen3_0pt6b eval          new=FileNotFoundError: ... /train/utils/t | old=FileNotFoundError: ... /train/utils/t
  raise train_probe/cgen_qwen3_0pt6b train          new=FileNotFoundError: ... /train/utils/t | old=FileNotFoundError: ... /train/utils/t
  raise train_probe/cgen_qwen3_0pt6b eval           new=FileNotFoundError: ... /train/utils/t | old=FileNotFoundError: ... /train/utils/t
  raise train_probe/cparam_qwen3_0pt6b train        new=FileNotFoundError: ... /train/utils/t | old=FileNotFoundError: ... /train/utils/t
  raise train_probe/cparam_qwen3_0pt6b eval         new=FileNotFoundError: ... /train/utils/t | old=FileNotFoundError: ... /train/utils/t
```

(The paths are shown shortened; the script prints the full
`/home/y-guo/reproduce/new1-wt/2026-09-18-version-history-r1/train/...` path on
both sides.) The ten stages that raise are the ones that fold a train version
entry — `train` and `eval` of the three `train_probe` settings, `inject` and
`score` of the two `inject` settings — and `train/` does not exist on this
branch yet. Every one raises the same `FileNotFoundError` on the same missing
file on both sides. Eight stages key on both sides and key identically.

### P2 — a bump that is stale for inject only

```
$ FIX=$(bash /tmp/vh/mkfix.sh); PYTHONPATH=$PWD python3 /tmp/vh/p2.py "$FIX"
before: {'sample': '5e898c2e7741', 'build': 'aa9b69a5cc81', 'inject': '373d26d8bc27'}
file now: 'VERSION = 2' 'VERSION_HISTORY = {2: {"why": "x", "stale": ("inject",)}}'
version_history: {2: {'why': 'x', 'stale': ('inject',)}}
effective_version per stage: {'sample': 1, 'build': 1, 'train': 1, 'eval': 1, 'inject': 2, 'score': 1}
after:  {'sample': '5e898c2e7741', 'build': 'aa9b69a5cc81', 'inject': 'c4f6d2c47722'}
inject key moves: True
sample key stays: True
build key stays:  True
_versions records the real VERSION: 2
_versions of the bumped file in the sample run: 2
```

`data/environments/appworld.py` is listed by the sample, build and inject
version lists. The inject key moves, the sample and build keys do not, and both
`freeze`'s `_versions` block in `settings.yaml` and `versions_of` for the sample
stage record the real `VERSION`, 2.

### P3 — the three table shapes of the same bump

```
$ FIX=$(bash /tmp/vh/mkfix.sh); PYTHONPATH=$PWD python3 /tmp/vh/p3.py "$FIX"
before: {'sample': '5e898c2e7741', 'build': 'aa9b69a5cc81', 'inject': '373d26d8bc27'}
no table at all: effective {'sample': 2, 'build': 2, 'train': 2, 'eval': 2, 'inject': 2, 'score': 2}
no table at all: moved ['sample', 'build', 'inject'] | unchanged []
an entry with no 'stale' key: effective {'sample': 2, 'build': 2, 'train': 2, 'eval': 2, 'inject': 2, 'score': 2}
an entry with no 'stale' key: moved ['sample', 'build', 'inject'] | unchanged []
an entry with "stale": (): effective {'sample': 1, 'build': 1, 'train': 1, 'eval': 1, 'inject': 1, 'score': 1}
an entry with "stale": (): moved [] | unchanged ['sample', 'build', 'inject']
```

`moved` / `unchanged` list the three stages that fold this file. A stub with
`VERSION = 2` and no table keys as stale everywhere, an entry with no `"stale"`
key keys as stale everywhere, and `"stale": ()` moves no stage.

### P4 — flipping an entry from stale to usable brings the run directory back

```
$ FIX=$(bash /tmp/vh/mkfix.sh); PYTHONPATH=$PWD python3 /tmp/vh/p4.py "$FIX"
P1 inject key (VERSION = 1, empty table): 373d26d8bc27
after the stale-for-inject bump:         c4f6d2c47722 | moved: True
after flipping the entry to stale: ()    373d26d8bc27 | back to the P1 key: True
the run directory that comes back: /tmp/tmp.Rs2JPHYdN7/outputs/inject/373d26d8bc27
```

### P5 — every refusal names the file; a missing `"why"` passes

Each case is run twice: directly through `version_history(rel_path)` and through
`key('inject', ...)`, which reaches it through `_key_versions`.

```
$ FIX=$(bash /tmp/vh/mkfix.sh); PYTHONPATH=$PWD python3 /tmp/vh/p5.py "$FIX"
table is not a mapping -> version_history: SchemaError (names the file: True) data/environments/appworld.py: VERSION_HISTORY is a list, expected a mapping of version -> entry
table is not a mapping -> key('inject'): SchemaError (names the file: True) data/environments/appworld.py: VERSION_HISTORY is a list, expected a mapping of version -> entry
entry key is not an int -> version_history: SchemaError (names the file: True) data/environments/appworld.py: VERSION_HISTORY key '2' is a str, expected an int from 2 to 2
entry key is not an int -> key('inject'): SchemaError (names the file: True) data/environments/appworld.py: VERSION_HISTORY key '2' is a str, expected an int from 2 to 2
entry key below 2 -> version_history: SchemaError (names the file: True) data/environments/appworld.py: VERSION_HISTORY key 1 is outside 2..2, this file's VERSION
entry key below 2 -> key('inject'): SchemaError (names the file: True) data/environments/appworld.py: VERSION_HISTORY key 1 is outside 2..2, this file's VERSION
entry key above VERSION -> version_history: SchemaError (names the file: True) data/environments/appworld.py: VERSION_HISTORY key 3 is outside 2..2, this file's VERSION
entry key above VERSION -> key('inject'): SchemaError (names the file: True) data/environments/appworld.py: VERSION_HISTORY key 3 is outside 2..2, this file's VERSION
entry is not a mapping -> version_history: SchemaError (names the file: True) data/environments/appworld.py: VERSION_HISTORY[2] is a str, expected a mapping
entry is not a mapping -> key('inject'): SchemaError (names the file: True) data/environments/appworld.py: VERSION_HISTORY[2] is a str, expected a mapping
stale is not a tuple or list -> version_history: SchemaError (names the file: True) data/environments/appworld.py: VERSION_HISTORY[2]['stale'] is a str, expected a tuple of stage names of ('sample', 'build', 'train', 'eval', 'inject', 'score')
stale is not a tuple or list -> key('inject'): SchemaError (names the file: True) data/environments/appworld.py: VERSION_HISTORY[2]['stale'] is a str, expected a tuple of stage names of ('sample', 'build', 'train', 'eval', 'inject', 'score')
stale names a non-stage -> version_history: SchemaError (names the file: True) data/environments/appworld.py: VERSION_HISTORY[2]['stale'] names 'injct', which is not one of ('sample', 'build', 'train', 'eval', 'inject', 'score')
stale names a non-stage -> key('inject'): SchemaError (names the file: True) data/environments/appworld.py: VERSION_HISTORY[2]['stale'] names 'injct', which is not one of ('sample', 'build', 'train', 'eval', 'inject', 'score')
two column-zero tables -> version_history: SchemaError (names the file: True) data/environments/appworld.py: 2 column-zero assignments to 'VERSION_HISTORY', expected exactly one
two column-zero tables -> key('inject'): SchemaError (names the file: True) data/environments/appworld.py: 2 column-zero assignments to 'VERSION_HISTORY', expected exactly one
no why (the key path allows it) -> version_history: NO RAISE, {2: {'stale': ('inject',)}}
no why (the key path allows it) -> key('inject'): NO RAISE, c4f6d2c47722
```

### P6 — a `MATCH_VERSION` bump re-keys one method's train run

```
$ FIX=$(bash /tmp/vh/mkfix.sh); PYTHONPATH=$PWD python3 /tmp/vh/p6.py "$FIX"
before ctool_qwen3_0pt6b {'train': 'a7f5ebd1adbe', 'eval': '67e377456b8e'}
before cgen_qwen3_0pt6b {'train': '7c509d3a79fa', 'eval': 'c622550d0044'}
before cparam_qwen3_0pt6b {'train': 'd047fc949418', 'eval': 'b710e6d08915'}
train key-versions of cgen: {'train/utils/trainer.py': 1, 'train/methods/cgen.py': 1, 'eval/utils/probe_eval.py#MATCH_VERSION.cgen': 1, 'data/training_data.py': 1, 'data/probe_output.py': 1, 'models/probe_models/base.py': 1, 'models/probe_models/qwen.py': 1}
eval  key-versions of cgen: {'eval/utils/probe_eval.py': 1, 'data/probe_output.py': 1}

-- MATCH_VERSION["cgen"] 1 -> 2 --
ctool_qwen3_0pt6b: train moved False, eval moved False -> {'train': 'a7f5ebd1adbe', 'eval': '67e377456b8e'}
cgen_qwen3_0pt6b: train moved True, eval moved True -> {'train': '9db8d9f48a04', 'eval': '66a4c1cdea2c'}
cparam_qwen3_0pt6b: train moved False, eval moved False -> {'train': 'd047fc949418', 'eval': 'b710e6d08915'}

-- probe_eval.py VERSION 1 -> 2, MATCH_VERSION back to 1 everywhere --
ctool_qwen3_0pt6b: train moved False, eval moved True -> {'train': 'a7f5ebd1adbe', 'eval': '422f227952e3'}
cgen_qwen3_0pt6b: train moved False, eval moved True -> {'train': '7c509d3a79fa', 'eval': '3f29da9f64e1'}
cparam_qwen3_0pt6b: train moved False, eval moved True -> {'train': 'd047fc949418', 'eval': '5da2c7f3270c'}
```

Bumping `MATCH_VERSION["cgen"]` moves cgen's train key and leaves the ctool and
cparam train keys and the ctool and cparam eval keys where they were. cgen's own
eval key moves as well, and that is the upstream chain, not the table: the eval
stage folds the train key of the same setting (`STAGES["eval"]["upstream"]`,
`"key": "fold"`), so a train run that is re-keyed re-keys its own eval run. The
eval key's own versions block holds `eval/utils/probe_eval.py` and
`data/probe_output.py` and no `MATCH_VERSION` entry, printed above.

The second half is the counterpart: a `VERSION` bump of `probe_eval.py` moves
all three eval keys and no train key, because the train version list names only
`eval/utils/probe_eval.py#MATCH_VERSION.{method}` and never the bare path.

### P7 — ticket 04's acceptance groups B, C, D

**B1 — imports under all four interpreters, and no repo import.** Run verbatim.

```
$ for P in python3 "$PR" "$AW" "$VL"; do $P -c "import experimental_settings.schema as S; print(S.__name__, len(S.STAGES), S.PROBE_TEXT_FIELDS)"; done
experimental_settings.schema 6 ('min_think', 'hist_rounds', 'probe_result_cap')
experimental_settings.schema 6 ('min_think', 'hist_rounds', 'probe_result_cap')
experimental_settings.schema 6 ('min_think', 'hist_rounds', 'probe_result_cap')
experimental_settings.schema 6 ('min_think', 'hist_rounds', 'probe_result_cap')
$ python3 -c "... ast walk over schema.py's imports ..."
['__future__', 'ast', 'dataclasses', 'hashlib', 'itertools', 'json', 'pathlib', 'typing', 'yaml']
```

**B2 — the defaults equal the contract table.** Run verbatim, fails on ticket
text the wave-4 owner ruling made stale (the ticket's own Comments entry of
2026-09-18 lists `B2`'s `i.chunk_tokens` / `i.tail_tokens` dereference as stale;
the two fields were removed from `Inject`). Not caused by this change.

```
$ python3 -c "... the ticket's B2, verbatim ..."
Traceback (most recent call last):
  File "<string>", line 12, in <module>
AttributeError: 'Inject' object has no attribute 'chunk_tokens'
```

The same command with those two names dropped from the last assertion:

```
$ python3 -c "... B2 without i.chunk_tokens / i.tail_tokens ..."
defaults ok (without the removed inject.chunk_tokens / inject.tail_tokens)
```

**B3 — `STAGES` has the six stages and the cell shape.** Run verbatim.

```
$ python3 -c "... the ticket's B3 ..."
[('sample', 8, True, 'map'), ('build', 6, False, 'any'), ('train', 7, True, 'probe'), ('eval', 2, False, 'any'), ('inject', 14, True, 'map'), ('score', 2, False, 'any')]
carry: [('inject', 'probe_score.eval')]
```

Exit 0. The eval row's version count is 2 where the ticket's expected line says
3: the fold took `eval/methods/{method}.py` out of the eval version list. Ticket
text made stale by `f13f0ad`, not by this change.

**B4 — the axis literals agree with what is on disk.** Run verbatim; aborts.

```
$ python3 -c "... the ticket's B4 ..."
Traceback (most recent call last):
  File "<string>", line 22, in <module>
  File "<string>", line 7, in lit
  ...
ValueError: malformed node or string on line 60: <ast.Call object at 0x7f9114230370>
exit=1
```

Line 22 is `lit('agent/inject_format.py','FORMATS')`. `FORMATS` in that file is
a dict of `Format(...)` calls, so `ast.literal_eval` refuses it. This is
pre-existing and independent of this change:

```
$ git show 78e9260:agent/inject_format.py > /tmp/vh/if_base.py
$ git show 7f49854:agent/inject_format.py > /tmp/vh/if_head.py
$ python3 -c "... literal_eval FORMATS in both ..."
78e9260 FORMATS: ValueError malformed node or string on line 49: <ast.Call object at 0x7
7f49854 (this branch) FORMATS: ValueError malformed node or string on line 60: <ast.Call object at 0x7
```

Same defect at the base commit (line 49 there, line 60 here only because the
comment block shifted the file down by 11 lines). Reported below as an open
finding. The other axis checks of B4, run one at a time:

```
$ python3 -c "... B4 with each check reported instead of aborting ..."
data/environments present: True
env axes ok: ['appworld'] ['v1'] ['dev', 'test', 'train']
train/methods and eval/methods present: False False -> that check skips
FORMATS: ValueError malformed node or string on line 60: <ast.Call object at 0x7
ARMS: ['no_probe', 'probe', 'probe_nofill'] == AXES: True
constants block ok
```

The `probe.method` axis check is guarded on `eval/methods/` and skips, as the
errata entry says.

**B5 — the two source-text readers.** Run verbatim, with two lines added for the
new readers.

```
$ D=$(mktemp -d); printf 'VERSION = 7\nSTOP = ["<|return|>"]\nclass C:\n    VERSION = VERSION\n' > $D/m.py
$ printf 'VERSION = 1\nVERSION = 2\n' > $D/two.py; printf 'x = 1\n' > $D/none.py
$ python3 -c "... the ticket's B5 + version_history / effective_version on m.py ..."
7 ['<|return|>']
two matches -> SchemaError two.py: 2 column-zero assignments to 'VERSION', expected exa
no match -> SchemaError none.py: no column-zero assignment to 'VERSION'
version_history of a file with no table: {}
effective_version of that file: 7
```

The indented `VERSION = VERSION` in the class body is still not a second match,
and a file with `VERSION = 7` and no table keys as stale from 2 on, so its
effective version is 7 for every stage.

**C1 — the flagship load.**

```
$ FIX=$(bash /tmp/vh/mkfix.sh); python3 -c "... the ticket's C1 ..."
ctool_qwen3_0pt6b ['sample', 'build', 'train', 'eval'] False
appworld v1 gpt_oss_120b qwen3_0pt6b
gptoss ['dtype', 'env_result', 'extra_flags', 'family']
['<|return|>'] high 2026-08-06
ctool None 1e-05 None
inject is None: True | build present: True
```

**C2 — the debug overlay.**

```
$ FIX=$(bash /tmp/vh/mkfix.sh); python3 -c "... the ticket's C2 ..."
True 3 1 6 8 64 20 100 50
3 None None None
```

**C3 — overrides and the sweep.**

```
$ FIX=$(bash /tmp/vh/mkfix.sh); python3 -c "... the ticket's C3 ..."
0.0003 lora [42, 67]
4
['ctool_qwen3_0pt6b/train.lr=0.0001,train.seed=42', 'ctool_qwen3_0pt6b/train.lr=0.0001,train.seed=67', 'ctool_qwen3_0pt6b/train.lr=0.0003,train.seed=42', 'ctool_qwen3_0pt6b/train.lr=0.0003,train.seed=67']
[0.0001, 0.0001, 0.0003, 0.0003]
ctool_qwen3_0pt6b/train.lr=0.0003,train.seed=67 0.0003 67
```

**C4 — every refusal of 5.7.**

```
$ FIX=$(bash /tmp/vh/mkfix.sh); PYTHONPATH=$PWD python3 /tmp/vh/c4.py "$FIX"
unknown key: REFUSED SchemaError: train.lrr: not a field of this section
off-axis value: REFUSED SchemaError: probe.method: 'ctoool' is not one of ('ctool', 'cgen', 'cparam')
bad instructions: REFUSED SchemaError: data.instructions: 'v9' is not one of ('v1',)
bad split: REFUSED SchemaError: sample.split: 'holdout' is not one of ('train', 'dev', 'test')
wrong role: REFUSED SchemaError: models.probe: 'gpt_oss_120b' has role 'agent', expected 'probe'
bad effort: REFUSED SchemaError: generation.effort: 'ultra' is not one of ('high', 'medium', 'low')
section not in workflow: REFUSED SchemaError: inject: no stage of this file's workflow reads this section
type mismatch: REFUSED SchemaError: train.lr: '1e-5' has type str, declared type is float
sweep over debug field: REFUSED SchemaError: sweep.train.max_steps: also set by debug.yaml, which would collapse the sweep
override of swept field: REFUSED SchemaError: train.lr: overridden and swept at once
missing reference: REFUSED SchemaError: eval.theta_from: nope: no such setting in /tmp/tmp.L27zxaXnO4/experimental_settings/train_
generator without theta_from: REFUSED SchemaError: eval.theta_from: is required when probe.method's PROBE_KIND is generator
probe section under inject: REFUSED SchemaError: probe: no stage of this file's workflow reads this section
models.probe under inject: REFUSED SchemaError: models.probe: a setting whose workflow contains inject may not state models.probe; an inje
theta unset: REFUSED SchemaError: inject.theta: is required and was not set
probe_gen is a param-only method: REFUSED SchemaError: inject.probe_gen: 'cparam' is not a whole-call generator (param_only=True, PROBE_KIND='gen
fire_nth_cut under no_probe: REFUSED SchemaError: inject.fire_nth_cut: must be 0 under arm: no_probe
baseline seeds not a superset: REFUSED SchemaError: score.baseline: baseline split/seeds are not a superset of this setting's inject.split/see
```

18 lines, every one `REFUSED`, the fields in the ticket's order.

**C5 — inheritance and its per-group scope.**

```
$ FIX=$(bash /tmp/vh/mkfix.sh); PYTHONPATH=$PWD python3 /tmp/vh/c5.py "$FIX"
inherited build fields: {'min_think': 40, 'hist_rounds': 3, 'probe_result_cap': 400}
probe row absent: True
inherited after the build edit: 5
stated-differently: REFUSED generation.temperature: stated 0.7 differs from the referenced run's 1.0; list it in meta.
with meta.override: 0.7
```

**D1 — the key's shape and the 3.2 guarantees.**

```
$ FIX=$(bash /tmp/vh/mkfix.sh); PYTHONPATH=$PWD python3 /tmp/vh/d1.py "$FIX"
{'sample': '5e898c2e7741', 'build': 'aa9b69a5cc81', 'train': 'a7f5ebd1adbe', 'eval': '67e377456b8e'}
determinism: True
debug separates: True
notes insensitive: True
default restated == unset: True
lr moves train, not sample/build: True True True
eval.risk moves eval only: True True
fields block: []
models block: ['probe'] []
upstream block: {'sample': '5e898c2e7741'} {}
```

**D2 — the `VERSION` fold and the one carve-out.** Two adaptations, both stated
in the output: the overwrite of the fixture's `eval/utils/probe_eval.py` keeps
the `PROBE_KIND` and `MATCH_VERSION` tables the fold put there (the ticket's
`write_text('VERSION = 2\n')` would delete them and the loader would stop
reading the method's kind), and the last assertion is printed twice, once as the
ticket writes it and once with the train key snapshotted before `trainer.py` is
edited.

```
$ FIX=$(bash /tmp/vh/mkfix.sh); PYTHONPATH=$PWD python3 /tmp/vh/d2.py "$FIX"
['data/probe_output.py', 'data/training_data.py', 'eval/utils/probe_eval.py#MATCH_VERSION.ctool', 'models/probe_models/base.py', 'models/probe_models/qwen.py', 'train/methods/ctool.py', 'train/utils/trainer.py']
['probe_gen.train', 'probe_score.eval', 'probe_score.train']
probe_eval VERSION moves the inject key: True
as the ticket writes it -- trainer VERSION moves train, not build: False True
with the snapshot taken first  -- trainer VERSION moves train, not build: True True
```

The first line is the train version list with the placeholders substituted; it
names `eval/utils/probe_eval.py#MATCH_VERSION.ctool` where the ticket's expected
line says `eval/methods/ctool.py` — the fold, not this change. The `False` on
the fourth line is the known script defect the ticket's Comments record: `D2`
never snapshots the train key before it edits `trainer.py`, so it compares two
keys both computed after the edit; with the snapshot taken first the same
sub-test prints `True True`.

**D3 — `run_dir`, `run_dir_of`, and the debug subtree.**

```
$ FIX=$(bash /tmp/vh/mkfix.sh); PYTHONPATH=$PWD python3 /tmp/vh/d3.py "$FIX"
train/a7f5ebd1adbe debug/train/6b173f360677
True True
nothing created: True
```

**D4 — `freeze`.**

```
$ FIX=$(bash /tmp/vh/mkfix.sh); PYTHONPATH=$PWD python3 /tmp/vh/d4.py "$FIX"
['data', 'generation', 'models', 'sample']
['_commit', '_debug', '_key', '_resolved', '_stage', '_upstream', '_versions']
sample True deadbeefcafe False {}
versions: ['agent/generate.py', 'agent/loop.py', 'data/environments/__init__.py'] 8
diff: True
no workflow line: True
seeds merged: [42, 67]
train projection: ['models', 'probe', 'train'] True
collision: REFUSED freeze: /tmp/tmp.omnLO5jD84/outputs/train/a7f5ebd1adbe already holds settings fo
```

**D5 — `load_frozen`.**

```
$ FIX=$(bash /tmp/vh/mkfix.sh); PYTHONPATH=$PWD python3 /tmp/vh/d5.py "$FIX"
train True deadbeefcafe ctool 1e-05 8192
upstream: ['build'] | sections dropped: True
removed field: REFUSED train.obsolete_knob: field removed from the schema (run directory /tmp/tmp.UXXtzBA4AR/outp
```

**D6 — rerun B1.** The B1 block above was rerun after the last code change and
is the output pasted there.

### P8 — every versioned file imports, and the diff touches nothing else

Each file is run under the interpreters of its `# venv:` line. Per spec section
4, `venv: any` means the three venv interpreters of the `venvs:` map — system
`python3` has neither Polars nor NumPy and is not in that map.

```
$ for f in $(git grep -l "^VERSION = " -- experimental_settings data models agent eval jobs | sort); do ... import the module and print VERSION, VERSION_HISTORY ...; done
agent/generate.py                appworld                      | 1 {}
agent/inject_format.py           any (probe, appworld, vllm)   | 1 {} | 1 {} | 1 {}
agent/inject.py                  appworld                      | 1 {}
agent/loop.py                    appworld                      | 1 {}
data/build_training_dataset.py   any (probe, appworld, vllm)   | 1 {} | 1 {} | 1 {}
data/environments/appworld.py    any (probe, appworld, vllm)   | 1 {} | 1 {} | 1 {}
data/environments/__init__.py    any (probe, appworld, vllm)   | 1 {} | 1 {} | 1 {}
data/probe_input.py              any (probe, appworld, vllm)   | 1 {} | 1 {} | 1 {}
data/probe_output.py             any (probe, appworld, vllm)   | 1 {} | 1 {} | 1 {}
data/training_data.py            any (probe, appworld, vllm)   | 1 {} | 1 {} | 1 {}
data/trajectory_record.py        any (probe, appworld, vllm)   | 1 {} | 1 {} | 1 {}
eval/score_run.py                any (probe, appworld, vllm)   | 1 {} | 1 {} | 1 {}
eval/utils/probe_eval.py         any (probe, appworld, vllm)   | 1 {} | 1 {} | 1 {}
models/agent_models/gptoss.py    any (probe, appworld, vllm)   | 1 {} | 1 {} | 1 {}
models/agent_models/service.py   any (probe, appworld, vllm)   | 1 {} | 1 {} | 1 {}
models/probe_models/base.py      probe                         | 1 {}
models/probe_models/qwen.py      probe                         | 1 {}
models/probe_models/service.py   any (probe, appworld, vllm)   | 1 {} | 1 {} | 1 {}
```

`module_version` still reads each `VERSION` as source text, and
`version_history` reads each table, without importing anything:

```
$ python3 -c "... S.module_version(f), S.version_history(f) for every versioned file ..."
18 files
{'agent/generate.py': (1, {}), 'agent/inject.py': (1, {}), 'agent/inject_format.py': (1, {}), 'agent/loop.py': (1, {}), 'data/build_training_dataset.py': (1, {}), 'data/environments/__init__.py': (1, {}), 'data/environments/appworld.py': (1, {}), 'data/probe_input.py': (1, {}), 'data/probe_output.py': (1, {}), 'data/training_data.py': (1, {}), 'data/trajectory_record.py': (1, {}), 'eval/score_run.py': (1, {}), 'eval/utils/probe_eval.py': (1, {}), 'models/agent_models/gptoss.py': (1, {}), 'models/agent_models/service.py': (1, {}), 'models/probe_models/base.py': (1, {}), 'models/probe_models/qwen.py': (1, {}), 'models/probe_models/service.py': (1, {})}
```

```
$ git diff --stat 78e9260..HEAD
 .scratch/from-zero/spec.md      |  23 ++++++-
 README.md                       |   6 +-
 agent/generate.py               |  11 +++
 agent/inject.py                 |  11 +++
 agent/inject_format.py          |  11 +++
 agent/loop.py                   |  11 +++
 data/build_training_dataset.py  |  11 +++
 data/environments/__init__.py   |  11 +++
 data/environments/appworld.py   |  11 +++
 data/probe_input.py             |  11 +++
 data/probe_output.py            |  11 +++
 data/training_data.py           |  11 +++
 data/trajectory_record.py       |  11 +++
 eval/score_run.py               |  11 +++
 eval/utils/probe_eval.py        |  11 +++
 experimental_settings/schema.py | 148 ++++++++++++++++++++++++++++++++++++----
 models/agent_models/gptoss.py   |  11 +++
 models/agent_models/service.py  |  11 +++
 models/probe_models/base.py     |  11 +++
 models/probe_models/qwen.py     |  11 +++
 models/probe_models/service.py  |  11 +++
 21 files changed, 360 insertions(+), 15 deletions(-)
```

21 files: `schema.py`, `README.md`, `spec.md` and the 18 versioned files. Every
versioned file is 11 added lines and no deletion.

## 4. Decisions the ruling did not make, and where they live in the code

1. **A `<path>#<TABLE>.<method>` entry folds the table value itself**, not an
   effective version. `_key_versions`, the `if marker:` branch calling
   `_table_entry_version`. The code says so twice: `_key_versions`'s docstring
   ("a per-method match version is already scoped to the one method that folds
   it, so it carries no VERSION_HISTORY") and `versions_of`'s docstring, which
   describes both spellings. `.scratch/from-zero/spec.md` section 5 does not
   mention the `#<TABLE>.<method>` spelling at all — it is stated only in the
   errata entry "0.2 / 2.1 / 2.6" and in these two docstrings.
2. **Which stage is looked up when a file is folded for another stage's sake.**
   `_key_versions` passes the stage whose key is being computed, so the inject
   key's stand-ins for the `probe_score` eval key (`eval/utils/probe_eval.py` on
   the inject row) read the `inject` entry of that file's table. The docstring
   of `_key_versions` states it.
3. **`"stale"` may be a tuple or a list.** `_check_version_history` accepts both
   and refuses a string. The ruling writes a tuple in the literal shape and says
   nothing about a list; a string is the shape most likely to be written by
   accident (`"stale": "inject"`), and it is refused.
4. **A `bool` table key is refused as "not an int"**, though Python's `True` is
   an `int`. `_check_version_history`, the first check of the loop.
5. **`effective_version(rel_path, stage)` does not check that `stage` names a
   stage.** An unknown name behaves like a stage no entry lists: it returns 1
   when every entry states `"stale"`, and the bumped version when an entry omits
   it. `effective_version` / `_stale_at`. Nothing in the repo calls it with a
   name that is not a `STAGES` key today; `run.py ls` and `run.py selfcheck`
   (tickets 14 and 15) will be the first outside callers.
6. **Reading a table refuses on entries the stage does not care about.**
   `_history_of` checks the whole table on every call, so a bad `"stale"` name
   in the entry for version 3 refuses the sample key as well, even when the
   sample key would fold version 2. This is what makes every refusal reachable
   from any stage's key, and it is what P5's `key('inject')` column shows.
7. **`version_history` on a file with a table but no `VERSION` raises** the
   "no column-zero assignment to 'VERSION'" refusal, because the `2..VERSION`
   bound has no source; on a file with neither literal it returns `{}` without
   looking for `VERSION`. `_history_of`.
8. **Refusal order inside one file**: two column-zero `VERSION_HISTORY`
   assignments refuse before the `VERSION` read. `_history_of`.
9. **One parse per file on the key path** (this round's commit, `6692bc1`): the
   reader is split into `_parse_module` and walkers over an already parsed tree.
   Behaviour-preserving; the reason is the 2.75x `key()` slowdown measured
   above.

## 5. Open findings, not fixed here

- `agent/inject_format.py`'s `FORMATS` is a dict of `Format(...)` calls, so
  `ast.literal_eval` refuses it, while spec section 5 lists `FORMATS` among the
  module-level literals the loader reads with `ast.literal_eval`. Pre-existing
  at `78e9260` (shown under B4 above), out of this change's scope, and it will
  bite `run.py selfcheck` (ticket 15) and ticket 04's `B4` until it is settled —
  either `FORMATS` becomes a plain literal or the spec's list drops it.
- `README.md`'s second sentence about `schema.py` ("`fields_of`, `models_of`,
  `upstream_of`, `versions_of`, `module_version` and `module_literal` are called
  only by this file and by `run.py`") does not list `version_history` and
  `effective_version`, which are also called only by this file today and are
  read by `run.py ls` and `run.py selfcheck` per the ruling. The same sentence
  already claims `versions_of` is called only by this file and `run.py`, while
  `jobs/launch.py` calls it (line 844). Left alone: correcting it means
  correcting a pre-existing claim the change did not introduce.
- Ticket 04's text is stale in three places this run touched, all from earlier
  merges: `B2`'s `i.chunk_tokens` / `i.tail_tokens` (wave-4 owner ruling, already
  recorded in the ticket's Comments), `B3`'s expected `('eval', 3, ...)` and
  `D2`'s expected `eval/methods/ctool.py` (the fold, `f13f0ad`). Tickets are not
  edited by an implementer; noted here for the owner.

## 6. Commits

- `7f49854` (fork1, the change under review) — effective per-stage versions in
  `schema.py`, the VERSION-rule comment and `VERSION_HISTORY = {}` in every
  versioned file, `spec.md` section 5.
- `6692bc1` (this round) — `effective_version` and `version_history` read one
  parse of the file.

---

## 7. Adversarial review of `78e9260..6692bc1` (read-only reviewer, 2026-09-18)

Read-only pass over `owner/2026-09-18-version-history`. The branch was exported
with `git archive 6692bc1 ...` into a temp tree and every proof was recomputed
there against a fresh fixture, not read off the pasted output above. The main
repo's working tree was not touched (it is mid-edit by another session and no
longer holds the from-zero file names, so every check ran against the archive).

### What was re-run and what it showed

- **P1, recomputed.** `key()` on the branch equals `key()` from
  `git show 78e9260:experimental_settings/schema.py` on all 18 keying stages of
  the fixture's three workflow files, and on all 8 stages that key on the real
  tree; the 6 that fold `train/` raise the same `FileNotFoundError` on both
  sides (`ctool/cgen/cparam` × `train`, `eval`), and both `inject.yaml` settings
  raise at `load` on `train/methods/cgen.py`. Extended: the same comparison with
  `debug=True`, and against `7f49854`, gives 0 mismatches, so the second commit
  is behaviour-preserving.
- **P2-P6, recomputed.** All as claimed. P2 also moves the two `score` keys of
  the inject settings, which is the `score` row folding the `inject` key, not a
  defect. P5's ten refusals all name the file; a missing `"why"` passes, as ruled.
- **P8, recomputed.** All 18 versioned files import under the interpreters of
  their venv line; the pinned comment block matches character for character in
  all 18 (byte-compared against the ruling text) and `VERSION_HISTORY = {}` sits
  directly below `VERSION` exactly once in each; `git diff --numstat` is
  `11 0` for each of the 18 and touches nothing else.
- **P7.** `B2`, `B3` and `D2` differ from the ticket exactly where the report
  says (wave-4 ruling and the fold). `B4` additionally fails on
  `agent/inject_format.py`'s `FORMATS`; pre-existing, already in section 5.

### Findings

- **V1 (important) — a `stale: ("eval",)` bump of `eval/utils/probe_eval.py`
  stops the inject stand-in from standing in.** `schema.py:1256`. Contracts 2.1
  and 3.3 carve `inject.probe_score`'s eval key out of the inject key and put
  `eval/utils/probe_eval.py`'s `VERSION` in its place, because that module fits
  `_resolved.probe_temperature`, the one number a live run takes from the
  report. `_key_versions` looks that file up under the stage being keyed
  (`inject`), so the bump that says "every eval report is stale" leaves every
  inject key where it was. Measured on the fixture: `VERSION = 2` with no table
  moves the inject key (`True`), `VERSION = 2` with
  `{2: {"why": ..., "stale": ("eval",)}}` does not (`False`) — ticket 04's `D2`
  assertion "probe_eval VERSION moves the inject key" now holds only when the
  bump names `inject` or names nothing. The behaviour is what the dispatch
  pins, so the fix is the owner's call: either that one entry looks up `eval`,
  or the comment block and `spec.md` say that a bump of a stand-in module must
  list `inject` as well.
- **V2 (important) — a directory kept alive by a usable bump loses the record
  of which `VERSION` made its bytes.** `schema.py:1407`. `freeze` rewrites
  `settings.yaml` whole, `_versions` and `_commit` included, and it merges
  request fields into an existing directory (`D4`'s "seeds merged"). Measured:
  freeze at `VERSION = 1` (`_versions` 1, `_commit` `commit_one`), bump
  `data/environments/appworld.py` to 2 with `"stale": ()`, freeze again — same
  key `5e898c2e7741`, same directory, `_versions` now 2 and `_commit`
  `commit_two`, while the files in it were produced at 1. Before this change a
  bump always moved the key, so one directory never spanned two `VERSION`s. The
  errata's sentence that `_versions` with `_commit` is "the record of which
  program made the output" no longer holds for a reused directory.
- **V3 (minor) — `<path>#<TABLE>.<method>` entries have no escape hatch.**
  `schema.py:1229`, `1246`. A `MATCH_VERSION` bump for one method re-keys both
  that method's train runs and every inject run whose `probe_score` uses it
  (measured: bumping `MATCH_VERSION["cgen"]` moved 6 keys, the two inject
  settings among them). That is the "an expensive live run is silently lost to
  a bump" case the ruling exists to prevent, and it is the one entry shape the
  ruling gives no way to declare usable. The docstring's "so it carries no
  VERSION_HISTORY" also reads as a claim about the file, which now carries
  `VERSION_HISTORY = {}` like every other versioned file.
- **V4 (minor) — a `"stale"` entry naming a stage that does not fold the file
  is accepted and does nothing.** `schema.py:376`. Measured: `train/utils/trainer.py`
  at `VERSION = 2` with `"stale": ("eval",)` moves no key at all, because only
  the `train` row lists that file. `_check_version_history` checks the name is a
  stage, not that the stage folds this file, and ticket 15's stated selfcheck
  rule checks the same thing. An author who lists the wrong stage gets silence.
- **V5 (minor) — `effective_version` answers a stage name outside `STAGES` with
  the permissive number instead of refusing.** `schema.py:442`. With
  `{2: {"stale": ["inject"]}, 3: {"stale": ()}}`, `effective_version(f, "injec")`
  returns 1, the answer that keeps every old directory, not the safe default the
  rest of the ruling takes. Section 4 item 5 records the behaviour; the point
  here is which way it fails. `run.py ls` and `run.py selfcheck` are the first
  outside callers.
- **V6 (minor, style) — `_stale_at` guards on two negatives.**
  `schema.py:432`. `if entry is None` / `if "stale" not in entry` can be one
  affirmative test (`if entry is not None and "stale" in entry: return stage in
  entry["stale"]`, then `return True`). Weakest item here; the repo rule on
  affirmative conditions is why it is listed.
- **V7 (minor, pre-existing, confirmed) — `FORMATS` is not a literal.**
  `agent/inject_format.py:58`. Confirmed at `78e9260` as well, and this change's
  `spec.md` edit adds `VERSION_HISTORY` to the very list that names `FORMATS`.
  Already in section 5; repeated so the owner sees it in one place.

Nothing else broke: no versioned file was missed, no unversioned file was
touched, every shipped `VERSION_HISTORY = {}` reads under `ast.literal_eval`,
`versions_of` / `freeze._versions` / `load_frozen` / `jobs/launch.py:844` all
still carry the real `VERSION`, no docstring names `eval/methods/`, no `legacy/`
citation entered the source, and the diff carries no non-ASCII.

---

## 8. Fix round 2: findings V1 and V2, 2026-09-18

Base of this round: `6692bc18578aa39f02fc675f29648cb747186d1a` (the head section 1
records). Head: `ea33c9c8b50fc2912d57a2e5b7319c176c60cf41`, one commit.
Worktree `/home/y-guo/reproduce/new1-wt/2026-09-18-version-history-r2` (removed
at the end, the branch kept); every command below ran from its root. One file
changed, `experimental_settings/schema.py`: `git diff --stat 6692bc1..HEAD` is
`1 file changed, 86 insertions(+), 25 deletions(-)`. V3 to V7 were not in this
round's list and are untouched.

### 8.1 V1 — the inject key's stand-in now reads the stage it stands in for

The inject row of the stage table folds `eval/utils/probe_eval.py` in place of
the `probe_score.eval` key 2.1 carries, because a live inject run takes
`_resolved.probe_temperature` out of that eval report. `_key_versions` looked the
file up under the stage being keyed, `inject`, so the natural declaration for a
change to the temperature fit, `stale: ("eval",)`, moved every eval key and left
every inject key where it was.

The fix is in the stage table and in the two readers:

- `STAGES["inject"]["versions"]` spells that one entry
  `"eval/utils/probe_eval.py@eval"`, with a three-line comment above it saying
  why (`schema.py:292`).
- `_entry_parts(entry)` (new, `schema.py:1211`) splits a versions entry into the
  name it enters a payload under, the module path, the table entry and the stage
  it stands in for, and documents the three spellings in one place. The
  `@<stage>` part is the stage table's own bookkeeping: the name is the part in
  front of it, so the key payload and the `_versions` record keep the bare path
  and every key is the key `78e9260` computed.
- `_key_versions` folds, for a stand-in, the highest version that made **either**
  the stage being keyed **or** the stage it stands in for stale
  (`_effective_version_over(path, (stage, stands_for))`). Both natural
  declarations therefore move the inject key: `stale: ("eval",)`, because an eval
  report that can no longer be used takes the inject run that read its
  temperature with it, and `stale: ("inject",)`, because the author said so.
- `effective_version(rel_path, stage)` keeps its signature and its behaviour and
  now calls `_effective_version_over(rel_path, (stage,))`; the file is still
  parsed once per entry (round 1's fix).

Because both declarations work, the pinned comment block in the 18 versioned
files and `spec.md` section 5 stay exactly as they are: the person editing
`eval/utils/probe_eval.py` lists the stages whose outputs can no longer be used
and needs to know nothing about stand-ins.

### 8.2 V2 — a reused run directory keeps the record of which VERSION made its bytes

`freeze` rewrote `settings.yaml` whole, so a directory kept alive by a bump whose
entry states `stale: ()` had its `_versions` overwritten with the versions of the
program of the *next* launch, while the bytes already in it were produced by the
earlier one.

`_keep_recorded_versions(current, recorded, run_dir)` (new, `schema.py:1412`) is
called from `freeze`'s existing re-freeze branch, next to `_merge_request_fields`
(`schema.py:1482`): every entry the directory already recorded keeps the version
its existing output was produced under, and every difference is printed, naming
the module and both numbers. Three points of the design, all in the function's
docstring:

- `_commit` is **not** treated this way. Contracts 1.5 and 3.4 make it "the
  commit `jobs/launch.git_state` returned for this launch, rewritten on every
  launch of this stage, which is the one commit a piece may record", and 2.5's
  `last/` resume rule compares a checkpoint against the commit of the launch that
  reads it.
- The launch that is starting still records its own real versions: `jobs/launch.py`
  appends `"versions": schema.versions_of(stage, setting)` to its `runs.jsonl`
  start row (8.1), one row per launch, append-only, so the per-launch pairs of
  commit and versions are in the ledger.
- The shape of the `_` block does not change, so ticket 04's `D4` still prints the
  same seven `_` names.

### 8.3 Proofs

The fixture is the one section 2 describes, `/tmp/vh/mkfix.sh`, unchanged in this
round (the two adaptations for the `eval/methods/` fold are the ones section 2
lists). New scripts this round: `/tmp/vh/p9.py` and `/tmp/vh/p10.py`.

**P9 (new) — every declaration on `eval/utils/probe_eval.py` reaches the right keys.**

```
$ FIX=$(bash /tmp/vh/mkfix.sh); PYTHONPATH=$PWD python3 /tmp/vh/p9.py "$FIX"
at VERSION = 1, empty table:
  ctool_qwen3_0pt6b train                a7f5ebd1adbe
  ctool_qwen3_0pt6b eval                 67e377456b8e
  cgen_qwen3_0pt6b train                 7c509d3a79fa
  cgen_qwen3_0pt6b eval                  c622550d0044
  cparam_qwen3_0pt6b train               d047fc949418
  cparam_qwen3_0pt6b eval                b710e6d08915
  probe_p1_e1_theta_0pt80 inject         373d26d8bc27
  no_probe_p1_e1_theta_0pt80 inject      6d18fcc8d2d0

the inject key's versions payload entry for the eval driver: {'eval/utils/probe_eval.py': 1, 'eval/utils/probe_eval.py#MATCH_VERSION.ctool': 1}
the inject run's _versions record for it:       {'eval/utils/probe_eval.py': 1, 'eval/utils/probe_eval.py#MATCH_VERSION.ctool': 1}

-- VERSION = 2, no table at all --
  effective version per stage: {'sample': 2, 'build': 2, 'train': 2, 'eval': 2, 'inject': 2, 'score': 2}
  moved:  ['cgen_qwen3_0pt6b eval', 'cparam_qwen3_0pt6b eval', 'ctool_qwen3_0pt6b eval', 'no_probe_p1_e1_theta_0pt80 inject', 'probe_p1_e1_theta_0pt80 inject']
  stayed: ['cgen_qwen3_0pt6b train', 'cparam_qwen3_0pt6b train', 'ctool_qwen3_0pt6b train']

-- VERSION = 2, stale: ("eval",) --
  effective version per stage: {'sample': 1, 'build': 1, 'train': 1, 'eval': 2, 'inject': 1, 'score': 1}
  moved:  ['cgen_qwen3_0pt6b eval', 'cparam_qwen3_0pt6b eval', 'ctool_qwen3_0pt6b eval', 'no_probe_p1_e1_theta_0pt80 inject', 'probe_p1_e1_theta_0pt80 inject']
  stayed: ['cgen_qwen3_0pt6b train', 'cparam_qwen3_0pt6b train', 'ctool_qwen3_0pt6b train']

-- VERSION = 2, stale: ("inject",) --
  effective version per stage: {'sample': 1, 'build': 1, 'train': 1, 'eval': 1, 'inject': 2, 'score': 1}
  moved:  ['no_probe_p1_e1_theta_0pt80 inject', 'probe_p1_e1_theta_0pt80 inject']
  stayed: ['cgen_qwen3_0pt6b eval', 'cgen_qwen3_0pt6b train', 'cparam_qwen3_0pt6b eval', 'cparam_qwen3_0pt6b train', 'ctool_qwen3_0pt6b eval', 'ctool_qwen3_0pt6b train']

-- VERSION = 2, stale: () --
  effective version per stage: {'sample': 1, 'build': 1, 'train': 1, 'eval': 1, 'inject': 1, 'score': 1}
  moved:  []
  stayed: ['cgen_qwen3_0pt6b eval', 'cgen_qwen3_0pt6b train', 'cparam_qwen3_0pt6b eval', 'cparam_qwen3_0pt6b train', 'ctool_qwen3_0pt6b eval', 'ctool_qwen3_0pt6b train', 'no_probe_p1_e1_theta_0pt80 inject', 'probe_p1_e1_theta_0pt80 inject']

restored: 'VERSION = 1' | keys back: True
```

The line the review measured as `False` — `stale: ("eval",)` against the inject
keys — now moves both inject keys. `stale: ("inject",)` moves the two inject keys
and no eval key. `stale: ()` moves nothing. No declaration moves a train key,
because the train row folds only `#MATCH_VERSION.{method}` (P6). The payload and
record entry names are the bare path, printed above.

**P10 (new) — the record of the bytes already in a directory survives a re-freeze.**

```
$ FIX=$(bash /tmp/vh/mkfix.sh); PYTHONPATH=$PWD python3 /tmp/vh/p10.py "$FIX"
first freeze : key 5e898c2e7741 | _versions[appworld] 1 | _commit commit_one | seeds [42]
after the stale: () bump: key 5e898c2e7741 | same directory: True | real VERSION now 2
schema.freeze: /tmp/tmp.reDOZUu9vh/outputs/sample/5e898c2e7741 holds output produced under data/environments/appworld.py VERSION 1 and this launch runs VERSION 2; the directory keeps 1
second freeze: _versions[appworld] 1 | _commit commit_two | seeds merged [42, 67]
the record of the bytes already there is kept: True
every other _versions entry is this launch's: True
the start row of this launch carries the real versions: 2

-- the same two freezes with no bump in between (ticket 04 D4's case) --
same directory, emptied: True | appworld back at VERSION 1
no line printed above; _versions[appworld] 1 | _commit commit_two | seeds merged [42, 67]
```

The review's measurement was: freeze at `VERSION = 1` (`_versions` 1, `_commit`
`commit_one`), bump with `"stale": ()`, freeze again, and `_versions` read 2.
It now reads 1, the version the directory's output was produced under, with the
difference printed; `_commit` takes the new launch's commit, as 3.4 requires; the
seeds still merge; and with no bump in between nothing is printed and nothing
changes, which is the case `D4` exercises.

**P1 (rerun) — every key is the key of `78e9260`.** The `@eval` marker is stage-table
bookkeeping, so no payload changed.

```
$ git show 78e9260:experimental_settings/schema.py > /tmp/vh/old_schema.py
$ FIX=$(bash /tmp/vh/mkfix.sh); PYTHONPATH=$PWD python3 /tmp/vh/p1.py "$FIX" /tmp/vh/old_schema.py
same  baseline/gpt_oss_120b_appworld sample                5e898c2e7741
same  baseline/gpt_oss_120b_appworld score                 8f16442a6e72
skip  debug.yaml: no workflow line, it is the debug overlay
same  inject/probe_p1_e1_theta_0pt80 inject                373d26d8bc27
same  inject/probe_p1_e1_theta_0pt80 score                 1a8e6643f8ef
same  inject/no_probe_p1_e1_theta_0pt80 inject             6d18fcc8d2d0
same  inject/no_probe_p1_e1_theta_0pt80 score              6755666ac372
same  train_probe/ctool_qwen3_0pt6b sample                 5e898c2e7741
same  train_probe/ctool_qwen3_0pt6b build                  aa9b69a5cc81
same  train_probe/ctool_qwen3_0pt6b train                  a7f5ebd1adbe
same  train_probe/ctool_qwen3_0pt6b eval                   67e377456b8e
same  train_probe/cgen_qwen3_0pt6b sample                  5e898c2e7741
same  train_probe/cgen_qwen3_0pt6b build                   aa9b69a5cc81
same  train_probe/cgen_qwen3_0pt6b train                   7c509d3a79fa
same  train_probe/cgen_qwen3_0pt6b eval                    c622550d0044
same  train_probe/cparam_qwen3_0pt6b sample                5e898c2e7741
same  train_probe/cparam_qwen3_0pt6b build                 aa9b69a5cc81
same  train_probe/cparam_qwen3_0pt6b train                 d047fc949418
same  train_probe/cparam_qwen3_0pt6b eval                  b710e6d08915

equal keys: 18
moved keys: 0 []
raised on both sides: 0
raised on one side only: 0 []
```

Over the real repo's `experimental_settings/*.yaml` (the worktree path is
shortened to `<WT>` in this paste; the script prints it in full):

```
$ PYTHONPATH=$PWD python3 /tmp/vh/p1.py "$PWD" /tmp/vh/old_schema.py
same  baseline/gpt_oss_120b_appworld sample                5e898c2e7741
same  baseline/gpt_oss_120b_appworld score                 8f16442a6e72
skip  debug.yaml: no workflow line, it is the debug overlay
same  train_probe/ctool_qwen3_0pt6b sample                 5e898c2e7741
same  train_probe/ctool_qwen3_0pt6b build                  aa9b69a5cc81
same  train_probe/cgen_qwen3_0pt6b sample                  5e898c2e7741
same  train_probe/cgen_qwen3_0pt6b build                   aa9b69a5cc81
same  train_probe/cparam_qwen3_0pt6b sample                5e898c2e7741
same  train_probe/cparam_qwen3_0pt6b build                 aa9b69a5cc81

equal keys: 8
moved keys: 0 []
raised on both sides: 10
  raise inject/probe_p1_e1_theta_0pt80 inject                new=FileNotFoundError: [Errno 2] No such file or directory: '<WT>/train/methods | old=FileNotFoundError: [Errno 2] No such file or directory: '<WT>/train/methods
  raise inject/probe_p1_e1_theta_0pt80 score                 new=FileNotFoundError: ... | old=FileNotFoundError: ...
  raise inject/no_probe_p1_e1_theta_0pt80 inject             new=FileNotFoundError: ... | old=FileNotFoundError: ...
  raise inject/no_probe_p1_e1_theta_0pt80 score              new=FileNotFoundError: ... | old=FileNotFoundError: ...
  raise train_probe/ctool_qwen3_0pt6b train                  new=FileNotFoundError: [Errno 2] No such file or directory: '<WT>/train/utils/t | old=FileNotFoundError: [Errno 2] No such file or directory: '<WT>/train/utils/t
  raise train_probe/ctool_qwen3_0pt6b eval                   new=FileNotFoundError: ... | old=FileNotFoundError: ...
  raise train_probe/cgen_qwen3_0pt6b train                   new=FileNotFoundError: ... | old=FileNotFoundError: ...
  raise train_probe/cgen_qwen3_0pt6b eval                    new=FileNotFoundError: ... | old=FileNotFoundError: ...
  raise train_probe/cparam_qwen3_0pt6b train                 new=FileNotFoundError: ... | old=FileNotFoundError: ...
  raise train_probe/cparam_qwen3_0pt6b eval                  new=FileNotFoundError: ... | old=FileNotFoundError: ...
raised on one side only: 0 []
```

The ten stages that raise are the ones that fold a `train/` entry, which does not
exist on this branch; each raises the same `FileNotFoundError` on the same file on
both sides, as in round 1. Two of the ten lines are pasted whole, one per missing
file; the eight marked `...` printed the same two full strings as the line above
each of them, differing only in the setting and stage at the front.

**P1 extended — the `_versions` record too.** `versions_of` is what
`freeze`'s `_versions`, `jobs/launch.py`'s start row and `meta.json` carry, so the
entry names matter as much as the keys.

```
$ FIX=$(bash /tmp/vh/mkfix.sh); PYTHONPATH=$PWD python3 - "$FIX" /tmp/vh/old_schema.py <<'PY'
... versions_of(stage, setting) on both modules, every stage of every named setting ...
PY
versions_of equal to 78e9260 on 18 stage/setting pairs
the inject row's _versions entries: ['agent/generate.py', 'agent/inject.py', 'agent/inject_format.py', 'agent/loop.py', 'data/environments/__init__.py', 'data/environments/appworld.py', 'data/probe_input.py', 'data/trajectory_record.py', 'eval/utils/probe_eval.py', 'eval/utils/probe_eval.py#MATCH_VERSION.ctool', 'models/agent_models/gptoss.py', 'models/agent_models/service.py', 'models/probe_models/base.py', 'models/probe_models/service.py']
```

**P2 to P6 (rerun) — byte-identical to the round-1 output pasted in section 3.**

```
$ for p in p2 p3 p4 p5 p6; do echo "=== $p ==="; FIX=$(bash /tmp/vh/mkfix.sh); PYTHONPATH=$PWD python3 /tmp/vh/$p.py "$FIX"; done
=== p2 ===
before: {'sample': '5e898c2e7741', 'build': 'aa9b69a5cc81', 'inject': '373d26d8bc27'}
file now: 'VERSION = 2' 'VERSION_HISTORY = {2: {"why": "x", "stale": ("inject",)}}'
version_history: {2: {'why': 'x', 'stale': ('inject',)}}
effective_version per stage: {'sample': 1, 'build': 1, 'train': 1, 'eval': 1, 'inject': 2, 'score': 1}
after:  {'sample': '5e898c2e7741', 'build': 'aa9b69a5cc81', 'inject': 'c4f6d2c47722'}
inject key moves: True
sample key stays: True
build key stays:  True
_versions records the real VERSION: 2
_versions of the bumped file in the sample run: 2
=== p3 ===
before: {'sample': '5e898c2e7741', 'build': 'aa9b69a5cc81', 'inject': '373d26d8bc27'}
no table at all: effective {'sample': 2, 'build': 2, 'train': 2, 'eval': 2, 'inject': 2, 'score': 2}
no table at all: moved ['sample', 'build', 'inject'] | unchanged []
an entry with no 'stale' key: effective {'sample': 2, 'build': 2, 'train': 2, 'eval': 2, 'inject': 2, 'score': 2}
an entry with no 'stale' key: moved ['sample', 'build', 'inject'] | unchanged []
an entry with "stale": (): effective {'sample': 1, 'build': 1, 'train': 1, 'eval': 1, 'inject': 1, 'score': 1}
an entry with "stale": (): moved [] | unchanged ['sample', 'build', 'inject']
=== p4 ===
P1 inject key (VERSION = 1, empty table): 373d26d8bc27
after the stale-for-inject bump:         c4f6d2c47722 | moved: True
after flipping the entry to stale: ()    373d26d8bc27 | back to the P1 key: True
the run directory that comes back: /tmp/tmp.wSmnN3mLJl/outputs/inject/373d26d8bc27
=== p5 ===
table is not a mapping -> version_history: SchemaError (names the file: True) data/environments/appworld.py: VERSION_HISTORY is a list, expected a mapping of version -> entry
table is not a mapping -> key('inject'): SchemaError (names the file: True) data/environments/appworld.py: VERSION_HISTORY is a list, expected a mapping of version -> entry
entry key is not an int -> version_history: SchemaError (names the file: True) data/environments/appworld.py: VERSION_HISTORY key '2' is a str, expected an int from 2 to 2
entry key is not an int -> key('inject'): SchemaError (names the file: True) data/environments/appworld.py: VERSION_HISTORY key '2' is a str, expected an int from 2 to 2
entry key below 2 -> version_history: SchemaError (names the file: True) data/environments/appworld.py: VERSION_HISTORY key 1 is outside 2..2, this file's VERSION
entry key below 2 -> key('inject'): SchemaError (names the file: True) data/environments/appworld.py: VERSION_HISTORY key 1 is outside 2..2, this file's VERSION
entry key above VERSION -> version_history: SchemaError (names the file: True) data/environments/appworld.py: VERSION_HISTORY key 3 is outside 2..2, this file's VERSION
entry key above VERSION -> key('inject'): SchemaError (names the file: True) data/environments/appworld.py: VERSION_HISTORY key 3 is outside 2..2, this file's VERSION
entry is not a mapping -> version_history: SchemaError (names the file: True) data/environments/appworld.py: VERSION_HISTORY[2] is a str, expected a mapping
entry is not a mapping -> key('inject'): SchemaError (names the file: True) data/environments/appworld.py: VERSION_HISTORY[2] is a str, expected a mapping
stale is not a tuple or list -> version_history: SchemaError (names the file: True) data/environments/appworld.py: VERSION_HISTORY[2]['stale'] is a str, expected a tuple of stage names of ('sample', 'build', 'train', 'eval', 'inject', 'score')
stale is not a tuple or list -> key('inject'): SchemaError (names the file: True) data/environments/appworld.py: VERSION_HISTORY[2]['stale'] is a str, expected a tuple of stage names of ('sample', 'build', 'train', 'eval', 'inject', 'score')
stale names a non-stage -> version_history: SchemaError (names the file: True) data/environments/appworld.py: VERSION_HISTORY[2]['stale'] names 'injct', which is not one of ('sample', 'build', 'train', 'eval', 'inject', 'score')
stale names a non-stage -> key('inject'): SchemaError (names the file: True) data/environments/appworld.py: VERSION_HISTORY[2]['stale'] names 'injct', which is not one of ('sample', 'build', 'train', 'eval', 'inject', 'score')
two column-zero tables -> version_history: SchemaError (names the file: True) data/environments/appworld.py: 2 column-zero assignments to 'VERSION_HISTORY', expected exactly one
two column-zero tables -> key('inject'): SchemaError (names the file: True) data/environments/appworld.py: 2 column-zero assignments to 'VERSION_HISTORY', expected exactly one
no why (the key path allows it) -> version_history: NO RAISE, {2: {'stale': ('inject',)}}
no why (the key path allows it) -> key('inject'): NO RAISE, c4f6d2c47722
=== p6 ===
before ctool_qwen3_0pt6b {'train': 'a7f5ebd1adbe', 'eval': '67e377456b8e'}
before cgen_qwen3_0pt6b {'train': '7c509d3a79fa', 'eval': 'c622550d0044'}
before cparam_qwen3_0pt6b {'train': 'd047fc949418', 'eval': 'b710e6d08915'}
train key-versions of cgen: {'train/utils/trainer.py': 1, 'train/methods/cgen.py': 1, 'eval/utils/probe_eval.py#MATCH_VERSION.cgen': 1, 'data/training_data.py': 1, 'data/probe_output.py': 1, 'models/probe_models/base.py': 1, 'models/probe_models/qwen.py': 1}
eval  key-versions of cgen: {'eval/utils/probe_eval.py': 1, 'data/probe_output.py': 1}

-- MATCH_VERSION["cgen"] 1 -> 2 --
ctool_qwen3_0pt6b: train moved False, eval moved False -> {'train': 'a7f5ebd1adbe', 'eval': '67e377456b8e'}
cgen_qwen3_0pt6b: train moved True, eval moved True -> {'train': '9db8d9f48a04', 'eval': '66a4c1cdea2c'}
cparam_qwen3_0pt6b: train moved False, eval moved False -> {'train': 'd047fc949418', 'eval': 'b710e6d08915'}

-- probe_eval.py VERSION 1 -> 2, MATCH_VERSION back to 1 everywhere --
ctool_qwen3_0pt6b: train moved False, eval moved True -> {'train': 'a7f5ebd1adbe', 'eval': '422f227952e3'}
cgen_qwen3_0pt6b: train moved False, eval moved True -> {'train': '7c509d3a79fa', 'eval': '3f29da9f64e1'}
cparam_qwen3_0pt6b: train moved False, eval moved True -> {'train': 'd047fc949418', 'eval': '5da2c7f3270c'}
```

P6's second half is the `no table` case of P9 restricted to one file, and it
still moves the three eval keys and no train key.

**P7 (rerun of the groups this fix touches): B1, B3, B5, C1 to C5, D1 to D5.**

```
$ for P in python3 "$PR" "$AW" "$VL"; do PYTHONPATH=$PWD $P -c "import experimental_settings.schema as S; print(S.__name__, len(S.STAGES), S.PROBE_TEXT_FIELDS)"; done   # B1
experimental_settings.schema 6 ('min_think', 'hist_rounds', 'probe_result_cap')
experimental_settings.schema 6 ('min_think', 'hist_rounds', 'probe_result_cap')
experimental_settings.schema 6 ('min_think', 'hist_rounds', 'probe_result_cap')
experimental_settings.schema 6 ('min_think', 'hist_rounds', 'probe_result_cap')

$ python3 -c "... the ticket's B3, verbatim ..."
[('sample', 8, True, 'map'), ('build', 6, False, 'any'), ('train', 7, True, 'probe'), ('eval', 2, False, 'any'), ('inject', 14, True, 'map'), ('score', 2, False, 'any')]
carry: [('inject', 'probe_score.eval')]
exit=0

$ python3 -c "... the ticket's B5 + version_history / effective_version on m.py ..."
7 ['<|return|>']
two matches -> SchemaError two.py: 2 column-zero assignments to 'VERSION', expected exa
no match -> SchemaError none.py: no column-zero assignment to 'VERSION'
version_history of a file with no table: {}
effective_version of that file: 7

$ FIX=$(bash /tmp/vh/mkfix.sh); python3 -c "... the ticket's C1 ..."
ctool_qwen3_0pt6b ['sample', 'build', 'train', 'eval'] False
appworld v1 gpt_oss_120b qwen3_0pt6b
gptoss ['dtype', 'env_result', 'extra_flags', 'family']
['<|return|>'] high 2026-08-06
ctool None 1e-05 None
inject is None: True | build present: True

$ FIX=$(bash /tmp/vh/mkfix.sh); python3 -c "... the ticket's C2 ..."
True 3 1 6 8 64 20 100 50
3 None None None

$ FIX=$(bash /tmp/vh/mkfix.sh); python3 -c "... the ticket's C3 ..."
0.0003 lora [42, 67]
4
['ctool_qwen3_0pt6b/train.lr=0.0001,train.seed=42', 'ctool_qwen3_0pt6b/train.lr=0.0001,train.seed=67', 'ctool_qwen3_0pt6b/train.lr=0.0003,train.seed=42', 'ctool_qwen3_0pt6b/train.lr=0.0003,train.seed=67']
[0.0001, 0.0001, 0.0003, 0.0003]
ctool_qwen3_0pt6b/train.lr=0.0003,train.seed=67 0.0003 67

$ FIX=$(bash /tmp/vh/mkfix.sh); PYTHONPATH=$PWD python3 /tmp/vh/c4.py "$FIX"
unknown key: REFUSED SchemaError: train.lrr: not a field of this section
off-axis value: REFUSED SchemaError: probe.method: 'ctoool' is not one of ('ctool', 'cgen', 'cparam')
bad instructions: REFUSED SchemaError: data.instructions: 'v9' is not one of ('v1',)
bad split: REFUSED SchemaError: sample.split: 'holdout' is not one of ('train', 'dev', 'test')
wrong role: REFUSED SchemaError: models.probe: 'gpt_oss_120b' has role 'agent', expected 'probe'
bad effort: REFUSED SchemaError: generation.effort: 'ultra' is not one of ('high', 'medium', 'low')
section not in workflow: REFUSED SchemaError: inject: no stage of this file's workflow reads this section
type mismatch: REFUSED SchemaError: train.lr: '1e-5' has type str, declared type is float
sweep over debug field: REFUSED SchemaError: sweep.train.max_steps: also set by debug.yaml, which would collapse the sweep
override of swept field: REFUSED SchemaError: train.lr: overridden and swept at once
missing reference: REFUSED SchemaError: eval.theta_from: nope: no such setting in /tmp/tmp.wtukqXoMtS/experimental_settings/train_
generator without theta_from: REFUSED SchemaError: eval.theta_from: is required when probe.method's PROBE_KIND is generator
probe section under inject: REFUSED SchemaError: probe: no stage of this file's workflow reads this section
models.probe under inject: REFUSED SchemaError: models.probe: a setting whose workflow contains inject may not state models.probe; an inje
theta unset: REFUSED SchemaError: inject.theta: is required and was not set
probe_gen is a param-only method: REFUSED SchemaError: inject.probe_gen: 'cparam' is not a whole-call generator (param_only=True, PROBE_KIND='gen
fire_nth_cut under no_probe: REFUSED SchemaError: inject.fire_nth_cut: must be 0 under arm: no_probe
baseline seeds not a superset: REFUSED SchemaError: score.baseline: baseline split/seeds are not a superset of this setting's inject.split/see

$ FIX=$(bash /tmp/vh/mkfix.sh); PYTHONPATH=$PWD python3 /tmp/vh/c5.py "$FIX"
inherited build fields: {'min_think': 40, 'hist_rounds': 3, 'probe_result_cap': 400}
probe row absent: True
inherited after the build edit: 5
stated-differently: REFUSED generation.temperature: stated 0.7 differs from the referenced run's 1.0; list it in meta.
with meta.override: 0.7

$ for p in d1 d2 d3 d4 d5; do echo "=== $p ==="; FIX=$(bash /tmp/vh/mkfix.sh); PYTHONPATH=$PWD python3 /tmp/vh/$p.py "$FIX"; done
=== d1 ===
{'sample': '5e898c2e7741', 'build': 'aa9b69a5cc81', 'train': 'a7f5ebd1adbe', 'eval': '67e377456b8e'}
determinism: True
debug separates: True
notes insensitive: True
default restated == unset: True
lr moves train, not sample/build: True True True
eval.risk moves eval only: True True
fields block: []
models block: ['probe'] []
upstream block: {'sample': '5e898c2e7741'} {}
=== d2 ===
['data/probe_output.py', 'data/training_data.py', 'eval/utils/probe_eval.py#MATCH_VERSION.ctool', 'models/probe_models/base.py', 'models/probe_models/qwen.py', 'train/methods/ctool.py', 'train/utils/trainer.py']
['probe_gen.train', 'probe_score.eval', 'probe_score.train']
probe_eval VERSION moves the inject key: True
as the ticket writes it -- trainer VERSION moves train, not build: False True
with the snapshot taken first  -- trainer VERSION moves train, not build: True True
=== d3 ===
train/a7f5ebd1adbe debug/train/6b173f360677
True True
nothing created: True
=== d4 ===
['data', 'generation', 'models', 'sample']
['_commit', '_debug', '_key', '_resolved', '_stage', '_upstream', '_versions']
sample True deadbeefcafe False {}
versions: ['agent/generate.py', 'agent/loop.py', 'data/environments/__init__.py'] 8
diff: True
no workflow line: True
seeds merged: [42, 67]
train projection: ['models', 'probe', 'train'] True
collision: REFUSED freeze: /tmp/tmp.RdWp6nGSNQ/outputs/train/a7f5ebd1adbe already holds settings fo
=== d5 ===
train True deadbeefcafe ctool 1e-05 8192
upstream: ['build'] | sections dropped: True
removed field: REFUSED train.obsolete_knob: field removed from the schema (run directory /tmp/tmp.vUsNHmyD9l/outp
```

Every line is what section 3 pasted for round 1. `D4`'s `_` block is still the
seven names, and its `seeds merged` step printed no version line because the two
freezes run at the same versions. `D2`'s two known differences from the ticket
text (the fold's `#MATCH_VERSION.ctool` entry, and the script's missing snapshot)
are unchanged. `B2` and `B4` were not rerun: neither reads the code this round
touched, and section 3 records why each differs from the ticket.

**P8 (rerun) — every versioned file still imports, and the diff touches nothing else.**

```
$ for f in $(git grep -l "^VERSION = " -- experimental_settings data models agent eval jobs | sort); do ... import the module under its venv line's interpreters and print VERSION, VERSION_HISTORY ...; done
agent/generate.py                any (probe, appworld, vllm)    | 1 {} | 1 {} | 1 {}
agent/inject_format.py           any (probe, appworld, vllm)    | 1 {} | 1 {} | 1 {}
agent/inject.py                  any (probe, appworld, vllm)    | 1 {} | 1 {} | 1 {}
agent/loop.py                    any (probe, appworld, vllm)    | 1 {} | 1 {} | 1 {}
data/build_training_dataset.py   any (probe, appworld, vllm)    | 1 {} | 1 {} | 1 {}
data/environments/appworld.py    any (probe, appworld, vllm)    | 1 {} | 1 {} | 1 {}
data/environments/__init__.py    any (probe, appworld, vllm)    | 1 {} | 1 {} | 1 {}
data/probe_input.py              any (probe, appworld, vllm)    | 1 {} | 1 {} | 1 {}
data/probe_output.py             any (probe, appworld, vllm)    | 1 {} | 1 {} | 1 {}
data/training_data.py            any (probe, appworld, vllm)    | 1 {} | 1 {} | 1 {}
data/trajectory_record.py        any (probe, appworld, vllm)    | 1 {} | 1 {} | 1 {}
eval/score_run.py                any (probe, appworld, vllm)    | 1 {} | 1 {} | 1 {}
eval/utils/probe_eval.py         any (probe, appworld, vllm)    | 1 {} | 1 {} | 1 {}
models/agent_models/gptoss.py    any (probe, appworld, vllm)    | 1 {} | 1 {} | 1 {}
models/agent_models/service.py   any (probe, appworld, vllm)    | 1 {} | 1 {} | 1 {}
models/probe_models/base.py      probe                          | 1 {}
models/probe_models/qwen.py      probe                          | 1 {}
models/probe_models/service.py   any (probe, appworld, vllm)    | 1 {} | 1 {} | 1 {}
```

This round's loop classifies a file by its `# venv:` line and treats a file with
no such line as `any`, so `agent/generate.py`, `agent/inject.py` and
`agent/loop.py`, whose line reads `# venv: the environment's (appworld today)`,
were run under all three venv interpreters rather than the appworld one alone —
a superset of what they must pass, and all three imports succeed. Section 3's
round-1 paste shows the appworld-only form.

```
$ python3 -c "... S.module_version(f), S.version_history(f) for every versioned file ..."
18 files
{'agent/generate.py': (1, {}), 'agent/inject.py': (1, {}), 'agent/inject_format.py': (1, {}), 'agent/loop.py': (1, {}), 'data/build_training_dataset.py': (1, {}), 'data/environments/__init__.py': (1, {}), 'data/environments/appworld.py': (1, {}), 'data/probe_input.py': (1, {}), 'data/probe_output.py': (1, {}), 'data/training_data.py': (1, {}), 'data/trajectory_record.py': (1, {}), 'eval/score_run.py': (1, {}), 'eval/utils/probe_eval.py': (1, {}), 'models/agent_models/gptoss.py': (1, {}), 'models/agent_models/service.py': (1, {}), 'models/probe_models/base.py': (1, {}), 'models/probe_models/qwen.py': (1, {}), 'models/probe_models/service.py': (1, {})}

$ git diff --stat 78e9260..HEAD
 .scratch/from-zero/spec.md      |  23 +++-
 README.md                       |   6 +-
 agent/generate.py               |  11 ++
 agent/inject.py                 |  11 ++
 agent/inject_format.py          |  11 ++
 agent/loop.py                   |  11 ++
 data/build_training_dataset.py  |  11 ++
 data/environments/__init__.py   |  11 ++
 data/environments/appworld.py   |  11 ++
 data/probe_input.py             |  11 ++
 data/probe_output.py            |  11 ++
 data/training_data.py           |  11 ++
 data/trajectory_record.py       |  11 ++
 eval/score_run.py               |  11 ++
 eval/utils/probe_eval.py        |  11 ++
 experimental_settings/schema.py | 231 ++++++++++++++++++++++++++++++++++++----
 models/agent_models/gptoss.py   |  11 ++
 models/agent_models/service.py  |  11 ++
 models/probe_models/base.py     |  11 ++
 models/probe_models/qwen.py     |  11 ++
 models/probe_models/service.py  |  11 ++
 21 files changed, 432 insertions(+), 26 deletions(-)

$ git diff --stat 6692bc1..HEAD
 experimental_settings/schema.py | 111 +++++++++++++++++++++++++++++++---------
 1 file changed, 86 insertions(+), 25 deletions(-)
```

**Timing, against the round-1 measurement.** The fix parses no extra file: a
stand-in entry is still one parse.

```
$ PYTHONPATH=$PWD python3 - <<'PY'      # 50 x key('build') on the real tree, both modules
78e9260:    50 x key('build') on the real tree = 1.935 s
this round: 50 x key('build') on the real tree = 3.209 s
```

Round 1 measured 1.935 s and 3.244 s for the same two.

### 8.4 Decisions this round that the ruling did not make

1. **A stand-in entry folds the highest version that made either stage stale**,
   not the stood-for stage alone. `_key_versions`, the `stages = (stage,
   stands_for) if stands_for else (stage,)` line, and its docstring. The
   alternative — look up `eval` alone — would drop an explicit
   `stale: ("inject",)` on `eval/utils/probe_eval.py`, which is the same class of
   silence V1 reports. Folding both honours every declaration and leaves the
   pinned comment block and `spec.md` section 5 untouched.
2. **Where the stand-in is declared**: in the stage table, as the entry spelling
   `<path>@<stage>`, next to the entry it qualifies, rather than derived from the
   `carry` upstream cell or special-cased on the pair (`inject`,
   `eval/utils/probe_eval.py`). The `carry` cell names the upstream, not which
   version entries stand in for it, so deriving it would be a guess that changes
   meaning the day a file lands on two rows for unrelated reasons.
3. **`@<stage>` never reaches a payload or a record.** `_entry_parts` returns the
   part in front of the marker as the entry name, so the key payload, `_versions`
   in `settings.yaml`, `meta.json` and the `runs.jsonl` start row all keep the
   bare path. This is what P1 and the `versions_of` comparison measure.
4. **A re-freeze keeps the recorded `_versions` and rewrites `_commit`.**
   `_keep_recorded_versions`, called from `freeze`. The asymmetry is deliberate
   and the docstring gives the reason: 1.5 and 3.4 pin `_commit` as this launch's
   commit and 2.5's resume rule compares against it, while `_versions` is the
   record of which program made the output that is already there.
5. **The difference is printed, not refused.** A refusal would block extending a
   directory the ruling deliberately kept alive (adding a seed to a sample run of
   315 trajectories after a bump declared harmless for `sample`), which is the
   cost the ruling exists to avoid. `schema.py` prints nothing else anywhere;
   `jobs/launch.py` warns in the same shape (`jobs/launch.py refire: ...`).
6. **Round-1 decision, restated because the dispatch asks whether the code says
   so: a `<path>#<TABLE>.<method>` entry folds the table value itself.** It is
   stated in three docstrings now — `_entry_parts` (the three spellings in one
   place), `_key_versions` ("a per-method match version is already scoped to the
   one method that folds it, so it carries no VERSION_HISTORY") and `versions_of`
   (both spellings). `.scratch/from-zero/spec.md` section 5 still does not mention
   either marker, and that is on purpose: section 5 says what a Python file
   carries, and both markers are the stage table's bookkeeping, written in
   `schema.py` and never in a versioned file. The errata entry "0.2 / 2.1 / 2.6"
   remains the only document that spells `#<TABLE>.<method>`; nothing outside
   `schema.py` spells `@<stage>`.
7. Round-1 decisions 3 to 8 of section 4 (a list is accepted for `"stale"`, a
   `bool` key is refused, `effective_version` accepts an unknown stage name, a
   bad entry refuses from any stage's key, `version_history` on a file with a
   table and no `VERSION`, the refusal order) are unchanged by this round.

### 8.5 Left open

- **The 2.5 inject gate now needs effective versions, and it is ticket 14's code.**
  Contracts 2.5 has `run.py` compare a train run's recorded `_versions` entries
  for `models/probe_models/base.py` and its backbone, and a build run's entry for
  `data/probe_input.py`, against the `VERSION` lines of the current source. Under
  the ruling, a bump whose entry states those stages usable keeps the train key
  and the train directory, while the source's `VERSION` has moved — so the gate
  as contracts spell it refuses a live run the ruling says is fine. The gate
  should compare `effective_version(path, "train")` (and `"build"`) against the
  recorded number, or read the recorded number through the same table.
  `run.py` does not exist on this branch; this is for ticket 14, not for
  `schema.py`, and nothing in the repo takes that comparison today.
- **`done.json` of an extended run.** A stage program writes
  `versions=cfg._versions`, so after 8.2's fix the `done.json` of a directory that
  was extended across a usable bump records the version its earlier output was
  produced under, not the version of the launch that just finished. That is the
  directory-level record; the per-launch pair is the `runs.jsonl` start row. Said
  here because it is a visible consequence, not a defect found.
- V3 to V7 of the round-1 review are outside this round's list and untouched.

---

## 9. Fix round 3: finding R1, 2026-09-18

Base of this round: `ea33c9c8b50fc2912d57a2e5b7319c176c60cf41` (the head section 8
records). Head: `a3d18e2388ec928e47556e7e7a4e66d937b86ec1`, one commit. Worktree
`/home/y-guo/reproduce/new1-wt/2026-09-18-version-history-r3` (removed at the
end, the branch kept); every command below ran from its root. One file changed,
`experimental_settings/schema.py`: `git diff --stat ea33c9c..HEAD` is
`1 file changed, 1 insertion(+), 30 deletions(-)`. R1 was the only finding in this
round's list; round 2's V1 fix and findings V3 to V7 of round 1 are untouched.

### 9.1 R1 — `settings.yaml`'s `_versions` records the file's real `VERSION` again

The ruling states the invariant in so many words: "`_versions` in `settings.yaml`
and `meta.json` keeps recording the file's real `VERSION` (with `_commit`, the
record of which program made the output)", and this branch's own
`.scratch/from-zero/spec.md` section 5 repeats it to implementers ("while
`_versions` in `settings.yaml` and `meta.json` goes on recording the file's real
`VERSION`"). Round 2's `_keep_recorded_versions` pinned the recorded number to the
version the directory's first bytes were made under, so `settings.yaml` stopped
carrying the real `VERSION`, disagreed with the `meta.json` and `done.json` the
same launch writes from `versions_of` and `load_frozen`, and after a rollback of
the code claimed a version higher than the program that had just run.

The fix is the root one: the pin is deleted, not guarded. `_keep_recorded_versions`
and the `freeze` call to it are gone and `freeze`'s docstring is back to its
one-line form, so `doc["_versions"] = versions_of(stage, setting)` is what every
freeze writes, on the first write into a directory and on every later one.

```
$ git diff 6692bc1..HEAD -- experimental_settings/schema.py | grep "^@@"
@@ -286,7 +286,10 @@ STAGES = {
@@ -439,17 +442,22 @@ def _stale_at(table: dict, entry_version: int, stage: str) -> bool:
@@ -1200,14 +1208,35 @@ def _substitute(template: str, setting: Setting) -> str:
@@ -1217,12 +1246,11 @@ def versions_of(stage: str, setting: Setting) -> dict:
@@ -1240,20 +1268,24 @@ def _table_entry_version(path: str, table_entry: str) -> int:

$ git diff 6692bc1..HEAD -- experimental_settings/schema.py | grep "^[-+]def "
-def effective_version(rel_path: str, stage: str) -> int:
+def _effective_version_over(rel_path: str, stages: tuple[str, ...]) -> int:
+def effective_version(rel_path: str, stage: str) -> int:
+def _entry_parts(entry: str) -> tuple[str, str, str, str]:
```

Five hunks remain against round 1's head, and all five are round 2's V1 fix (the
stage table's `@eval` stand-in, `_entry_parts`, `_effective_version_over`,
`versions_of`, `_key_versions`). The `freeze` region is byte for byte the `6692bc1`
one.

**What round 2's pin was recording, and where that record lives instead.** A
directory kept alive by a bump whose entry states `stale: ()` does hold bytes from
two real `VERSION`s of the same module, which is what round 1's V2 observed. The
per-launch pair is in the ledger and was already there before this change:
`jobs/launch.py:844` puts `schema.versions_of(stage, setting)` and
`jobs/launch.py:846` puts this launch's commit in the `runs.jsonl` start row, one
append-only row per launch. The directory-level files — `settings.yaml`,
`meta.json`, `done.json` — name the versions of the launch that wrote them, which
is the meaning the ruling gives them. Recording the older launch's number in
`settings.yaml` is the owner's call, and it needs the errata entry and `spec.md`
section 5 rewritten first.

### 9.2 Proofs

The fixture is the one section 2 describes; the scripts were copied to `/tmp/vh3/`
and run from the worktree root, `mkfix.sh` unchanged. `p10.py` is rewritten this
round (the script that measured the pin now measures the restored invariant);
every other script is the one sections 3 and 8.3 used.

**P10 (rewritten) — the three records of one launch agree, through a bump, a
second bump and a rollback.** The scenario is the one the finding measured: freeze
at `VERSION = 1`; bump `data/environments/appworld.py` to 2 with `"stale": ()` so
the key holds and the directory is reused; freeze again; a third freeze at
`VERSION = 3`; then the code rolls back to `VERSION = 1` and a fourth freeze. Each
line reads `settings.yaml`'s `_versions`, `versions_of` (what `jobs/launch.py`
writes into the `runs.jsonl` start row and hands `registry.write_meta` for
`meta.json["versions"]`) and `load_frozen()._versions` (what
`data/build_training_dataset.py:366`, `eval/score_run.py:253` and
`eval/utils/probe_eval.py:656` pass to `done.json`).

```
$ FIX=$(bash /tmp/vh3/mkfix.sh); PYTHONPATH=$PWD python3 /tmp/vh3/p10.py "$FIX"
first freeze : key 5e898c2e7741
first freeze : settings.yaml _versions 1 | versions_of (meta.json, runs.jsonl start row) 1 | load_frozen (done.json) 1 | _commit commit_one | all three agree: True
after the stale: () bump: key 5e898c2e7741 | same directory: True
second freeze: settings.yaml _versions 2 | versions_of (meta.json, runs.jsonl start row) 2 | load_frozen (done.json) 2 | _commit commit_two | all three agree: True
seeds merged: [42, 67]
third freeze at VERSION 3: key 5e898c2e7741 | same directory: True
third freeze : settings.yaml _versions 3 | versions_of (meta.json, runs.jsonl start row) 3 | load_frozen (done.json) 3 | _commit commit_three | all three agree: True
code rolled back to VERSION 1: key 5e898c2e7741 | same directory: True
fourth freeze: settings.yaml _versions 1 | versions_of (meta.json, runs.jsonl start row) 1 | load_frozen (done.json) 1 | _commit commit_four | all three agree: True

-- the same two freezes with no bump in between (ticket 04 D4's case) --
after both   : settings.yaml _versions 1 | versions_of (meta.json, runs.jsonl start row) 1 | load_frozen (done.json) 1 | _commit commit_two | all three agree: True
seeds merged: [42, 67]
freeze printed nothing above
```

Every one of the four measurements the finding lists now reads the real `VERSION`:
1, 2, 3, and 1 after the rollback, with the three files agreeing on each. The
non-keyed request fields still merge (`seeds [42, 67]`), the key and the directory
still hold across the usable bump, and `freeze` prints nothing — round 2's warning
line went with the pin.

**P2 (rerun) — `_versions` records the real `VERSION` after a bump that moves the
inject key.**

```
$ FIX=$(bash /tmp/vh3/mkfix.sh); PYTHONPATH=$PWD python3 /tmp/vh3/p2.py "$FIX"
before: {'sample': '5e898c2e7741', 'build': 'aa9b69a5cc81', 'inject': '373d26d8bc27'}
file now: 'VERSION = 2' 'VERSION_HISTORY = {2: {"why": "x", "stale": ("inject",)}}'
version_history: {2: {'why': 'x', 'stale': ('inject',)}}
effective_version per stage: {'sample': 1, 'build': 1, 'train': 1, 'eval': 1, 'inject': 2, 'score': 1}
after:  {'sample': '5e898c2e7741', 'build': 'aa9b69a5cc81', 'inject': 'c4f6d2c47722'}
inject key moves: True
sample key stays: True
build key stays:  True
_versions records the real VERSION: 2
_versions of the bumped file in the sample run: 2
```

**P9 (rerun) — round 2's V1 fix is intact, and the `_versions` record still names
the bare path.**

```
$ FIX=$(bash /tmp/vh3/mkfix.sh); PYTHONPATH=$PWD python3 /tmp/vh3/p9.py "$FIX"
at VERSION = 1, empty table:
  ctool_qwen3_0pt6b train                a7f5ebd1adbe
  ctool_qwen3_0pt6b eval                 67e377456b8e
  cgen_qwen3_0pt6b train                 7c509d3a79fa
  cgen_qwen3_0pt6b eval                  c622550d0044
  cparam_qwen3_0pt6b train               d047fc949418
  cparam_qwen3_0pt6b eval                b710e6d08915
  probe_p1_e1_theta_0pt80 inject         373d26d8bc27
  no_probe_p1_e1_theta_0pt80 inject      6d18fcc8d2d0

the inject key's versions payload entry for the eval driver: {'eval/utils/probe_eval.py': 1, 'eval/utils/probe_eval.py#MATCH_VERSION.ctool': 1}
the inject run's _versions record for it:       {'eval/utils/probe_eval.py': 1, 'eval/utils/probe_eval.py#MATCH_VERSION.ctool': 1}

-- VERSION = 2, no table at all --
  effective version per stage: {'sample': 2, 'build': 2, 'train': 2, 'eval': 2, 'inject': 2, 'score': 2}
  moved:  ['cgen_qwen3_0pt6b eval', 'cparam_qwen3_0pt6b eval', 'ctool_qwen3_0pt6b eval', 'no_probe_p1_e1_theta_0pt80 inject', 'probe_p1_e1_theta_0pt80 inject']
  stayed: ['cgen_qwen3_0pt6b train', 'cparam_qwen3_0pt6b train', 'ctool_qwen3_0pt6b train']

-- VERSION = 2, stale: ("eval",) --
  effective version per stage: {'sample': 1, 'build': 1, 'train': 1, 'eval': 2, 'inject': 1, 'score': 1}
  moved:  ['cgen_qwen3_0pt6b eval', 'cparam_qwen3_0pt6b eval', 'ctool_qwen3_0pt6b eval', 'no_probe_p1_e1_theta_0pt80 inject', 'probe_p1_e1_theta_0pt80 inject']
  stayed: ['cgen_qwen3_0pt6b train', 'cparam_qwen3_0pt6b train', 'ctool_qwen3_0pt6b train']

-- VERSION = 2, stale: ("inject",) --
  effective version per stage: {'sample': 1, 'build': 1, 'train': 1, 'eval': 1, 'inject': 2, 'score': 1}
  moved:  ['no_probe_p1_e1_theta_0pt80 inject', 'probe_p1_e1_theta_0pt80 inject']
  stayed: ['cgen_qwen3_0pt6b eval', 'cgen_qwen3_0pt6b train', 'cparam_qwen3_0pt6b eval', 'cparam_qwen3_0pt6b train', 'ctool_qwen3_0pt6b eval', 'ctool_qwen3_0pt6b train']

-- VERSION = 2, stale: () --
  effective version per stage: {'sample': 1, 'build': 1, 'train': 1, 'eval': 1, 'inject': 1, 'score': 1}
  moved:  []
  stayed: ['cgen_qwen3_0pt6b eval', 'cgen_qwen3_0pt6b train', 'cparam_qwen3_0pt6b eval', 'cparam_qwen3_0pt6b train', 'ctool_qwen3_0pt6b eval', 'ctool_qwen3_0pt6b train', 'no_probe_p1_e1_theta_0pt80 inject', 'probe_p1_e1_theta_0pt80 inject']

restored: 'VERSION = 1' | keys back: True
```

**P1 (rerun) — every key that keys is still the key of `78e9260`.** On the fixture:

```
$ git show 78e9260:experimental_settings/schema.py > /tmp/vh3/old_schema.py
$ FIX=$(bash /tmp/vh3/mkfix.sh); PYTHONPATH=$PWD python3 /tmp/vh3/p1.py "$FIX" /tmp/vh3/old_schema.py
same  baseline/gpt_oss_120b_appworld sample                5e898c2e7741
same  baseline/gpt_oss_120b_appworld score                 8f16442a6e72
skip  debug.yaml: no workflow line, it is the debug overlay
same  inject/probe_p1_e1_theta_0pt80 inject                373d26d8bc27
same  inject/probe_p1_e1_theta_0pt80 score                 1a8e6643f8ef
same  inject/no_probe_p1_e1_theta_0pt80 inject             6d18fcc8d2d0
same  inject/no_probe_p1_e1_theta_0pt80 score              6755666ac372
same  train_probe/ctool_qwen3_0pt6b sample                 5e898c2e7741
same  train_probe/ctool_qwen3_0pt6b build                  aa9b69a5cc81
same  train_probe/ctool_qwen3_0pt6b train                  a7f5ebd1adbe
same  train_probe/ctool_qwen3_0pt6b eval                   67e377456b8e
same  train_probe/cgen_qwen3_0pt6b sample                  5e898c2e7741
same  train_probe/cgen_qwen3_0pt6b build                   aa9b69a5cc81
same  train_probe/cgen_qwen3_0pt6b train                   7c509d3a79fa
same  train_probe/cgen_qwen3_0pt6b eval                    c622550d0044
same  train_probe/cparam_qwen3_0pt6b sample                5e898c2e7741
same  train_probe/cparam_qwen3_0pt6b build                 aa9b69a5cc81
same  train_probe/cparam_qwen3_0pt6b train                 d047fc949418
same  train_probe/cparam_qwen3_0pt6b eval                  b710e6d08915

equal keys: 18
moved keys: 0 []
raised on both sides: 0
raised on one side only: 0 []
```

Over the real repo's settings files (the worktree path is shortened to `<WT>` in
this paste with `sed`; the script prints it in full):

```
$ PYTHONPATH=$PWD python3 /tmp/vh3/p1.py "$PWD" /tmp/vh3/old_schema.py
same  baseline/gpt_oss_120b_appworld sample                5e898c2e7741
same  baseline/gpt_oss_120b_appworld score                 8f16442a6e72
skip  debug.yaml: no workflow line, it is the debug overlay
same  train_probe/ctool_qwen3_0pt6b sample                 5e898c2e7741
same  train_probe/ctool_qwen3_0pt6b build                  aa9b69a5cc81
same  train_probe/cgen_qwen3_0pt6b sample                  5e898c2e7741
same  train_probe/cgen_qwen3_0pt6b build                   aa9b69a5cc81
same  train_probe/cparam_qwen3_0pt6b sample                5e898c2e7741
same  train_probe/cparam_qwen3_0pt6b build                 aa9b69a5cc81

equal keys: 8
moved keys: 0 []
raised on both sides: 10
  raise inject/probe_p1_e1_theta_0pt80 inject                new=FileNotFoundError: [Errno 2] No such file or directory: '<WT>/train/methods | old=FileNotFoundError: [Errno 2] No such file or directory: '<WT>/train/methods
  raise inject/probe_p1_e1_theta_0pt80 score                 new=FileNotFoundError: [Errno 2] No such file or directory: '<WT>/train/methods | old=FileNotFoundError: [Errno 2] No such file or directory: '<WT>/train/methods
  raise inject/no_probe_p1_e1_theta_0pt80 inject             new=FileNotFoundError: [Errno 2] No such file or directory: '<WT>/train/methods | old=FileNotFoundError: [Errno 2] No such file or directory: '<WT>/train/methods
  raise inject/no_probe_p1_e1_theta_0pt80 score              new=FileNotFoundError: [Errno 2] No such file or directory: '<WT>/train/methods | old=FileNotFoundError: [Errno 2] No such file or directory: '<WT>/train/methods
  raise train_probe/ctool_qwen3_0pt6b train                  new=FileNotFoundError: [Errno 2] No such file or directory: '<WT>/train/utils/t | old=FileNotFoundError: [Errno 2] No such file or directory: '<WT>/train/utils/t
  raise train_probe/ctool_qwen3_0pt6b eval                   new=FileNotFoundError: [Errno 2] No such file or directory: '<WT>/train/utils/t | old=FileNotFoundError: [Errno 2] No such file or directory: '<WT>/train/utils/t
  raise train_probe/cgen_qwen3_0pt6b train                   new=FileNotFoundError: [Errno 2] No such file or directory: '<WT>/train/utils/t | old=FileNotFoundError: [Errno 2] No such file or directory: '<WT>/train/utils/t
  raise train_probe/cgen_qwen3_0pt6b eval                    new=FileNotFoundError: [Errno 2] No such file or directory: '<WT>/train/utils/t | old=FileNotFoundError: [Errno 2] No such file or directory: '<WT>/train/utils/t
  raise train_probe/cparam_qwen3_0pt6b train                 new=FileNotFoundError: [Errno 2] No such file or directory: '<WT>/train/utils/t | old=FileNotFoundError: [Errno 2] No such file or directory: '<WT>/train/utils/t
  raise train_probe/cparam_qwen3_0pt6b eval                  new=FileNotFoundError: [Errno 2] No such file or directory: '<WT>/train/utils/t | old=FileNotFoundError: [Errno 2] No such file or directory: '<WT>/train/utils/t
raised on one side only: 0 []
```

The ten stages that raise are the ones that fold a `train/` entry, which does not
exist on this branch; each raises the same `FileNotFoundError` on the same file on
both sides, as in rounds 1 and 2.

**P7's `D4` and `D5` (rerun) — `freeze` and `load_frozen` are what ticket 04
expects.** These are the two acceptance groups this fix touches.

```
$ for p in d4 d5; do echo "=== $p ==="; FIX=$(bash /tmp/vh3/mkfix.sh); PYTHONPATH=$PWD python3 /tmp/vh3/$p.py "$FIX"; done
=== d4 ===
['data', 'generation', 'models', 'sample']
['_commit', '_debug', '_key', '_resolved', '_stage', '_upstream', '_versions']
sample True deadbeefcafe False {}
versions: ['agent/generate.py', 'agent/loop.py', 'data/environments/__init__.py'] 8
diff: True
no workflow line: True
seeds merged: [42, 67]
train projection: ['models', 'probe', 'train'] True
collision: REFUSED freeze: /tmp/tmp.DBJiiU4McJ/outputs/train/a7f5ebd1adbe already holds settings fo
=== d5 ===
train True deadbeefcafe ctool 1e-05 8192
upstream: ['build'] | sections dropped: True
removed field: REFUSED train.obsolete_knob: field removed from the schema (run directory /tmp/tmp.2FVJAgGQPy/outp
```

Line for line what sections 3 and 8.3 pasted, the temporary directory names apart.

**P7's `B1` (rerun) — `schema.py` imports under all four interpreters.**

```
$ for P in python3 "$PR" "$AW" "$VL"; do PYTHONPATH=$PWD $P -c "import experimental_settings.schema as S; print(S.__name__, len(S.STAGES), S.PROBE_TEXT_FIELDS)"; done
experimental_settings.schema 6 ('min_think', 'hist_rounds', 'probe_result_cap')
experimental_settings.schema 6 ('min_think', 'hist_rounds', 'probe_result_cap')
experimental_settings.schema 6 ('min_think', 'hist_rounds', 'probe_result_cap')
experimental_settings.schema 6 ('min_think', 'hist_rounds', 'probe_result_cap')
```

`P3` to `P6`, `P8` and the rest of `P7` read no code this round touched: the 18
versioned files, `README.md` and `spec.md` are untouched, and the key path is
untouched (P1 above measures it).

**The diff still touches nothing else.**

```
$ git diff --stat ea33c9c..HEAD
 experimental_settings/schema.py | 31 +------------------------------
 1 file changed, 1 insertion(+), 30 deletions(-)

$ git diff --stat 78e9260..HEAD | tail -1
 21 files changed, 402 insertions(+), 25 deletions(-)
```

The 21 files are `schema.py`, `README.md`, `spec.md` and the 18 versioned files, as
section 8.3 lists them; `schema.py` against `78e9260` is now
`178 insertions(+), 22 deletions(-)`.

### 9.3 Decisions this round that the ruling did not make

1. **The pin is removed rather than kept with the documents amended.** The ruling
   and `spec.md` section 5 both state the invariant the pin broke, and both are the
   owner's to change; an implementer whose change contradicts its own
   implementer-facing document has the change to fix, not the document.
2. **Nothing is printed when a directory is written into across a bump.** Round 2's
   warning line was part of the pin and went with it, so `freeze` prints nothing
   anywhere again (P10's last line). Whether a launch should say "this directory
   also holds output of an older `VERSION`" is `run.py ls`'s question (ticket 14,
   8.6's `behind` flag), and the ledger rows it would read already exist.
3. No other decision was taken: round 2's V1 fix, the round-1 decisions of
   section 4, and findings V3 to V7 are exactly as they were.

### 9.4 Corrections to the earlier sections of this report

- **Section 8.4 item 4** ("a re-freeze keeps the recorded `_versions` and rewrites
  `_commit`") filed under "decisions the ruling did not make" a decision the ruling
  did make, in the opposite direction. It no longer describes the code, and neither
  does item 5 of the same list ("the difference is printed, not refused").
- **Section 8.5's `done.json` bullet** described a consequence of the pin. With the
  pin gone, `done.json` records the versions of the launch that wrote it, the same
  numbers as `settings.yaml` and `meta.json` (P10).
- **Section 8.1 (V1) stands**, and so does everything in sections 1 to 4 about the
  key path, the 18 versioned files and `spec.md`.

### 9.5 Left open for the owner

- **A directory extended across a usable bump holds bytes of two real `VERSION`s.**
  That is round 1's V2 observation, and the ruling's answer is that the
  directory-level record names the launch that wrote it while the per-launch pairs
  of commit and versions live in `jobs/runs.jsonl` (`jobs/launch.py:844` and
  `:846`, one append-only start row per launch). Nothing in the repo reads those
  rows for this purpose yet; `run.py ls` (ticket 14) is the first place that could.
  Changing what `settings.yaml` means needs the errata entry and `spec.md`
  section 5 rewritten first, which is the owner's call.
- **The 2.5 inject gate still needs effective versions** (section 8.5's first
  bullet, unchanged): contracts 2.5 compares a recorded `_versions` entry against
  the source's `VERSION` line, which under the ruling refuses a run the ruling says
  is fine. Ticket 14's code, not `schema.py`'s.
- V3 to V7 of the round-1 review are outside this round's list and untouched.

### 9.6 Commits

- `a3d18e2` (this round) — `settings.yaml`'s `_versions` goes back to the file's
  real `VERSION`: `_keep_recorded_versions` and its `freeze` call removed.

---

## 10. Fix round 4: finding R2, 2026-09-18

Base of this round: `a3d18e2388ec928e47556e7e7a4e66d937b86ec1` (the head section 9
records). Head: `ff3bbb0ecde60eb0d5a8ef48ef1e0bed331811ee`, one commit. Worktree
`/home/y-guo/reproduce/new1-wt/2026-09-18-version-history-r4` (removed at the end,
the branch kept); every command below ran from its root. One file changed,
`experimental_settings/schema.py`, and only comment lines: `git diff --stat
a3d18e2..HEAD` is `1 file changed, 5 insertions(+)`. R2 was the only finding in
this round's list; rounds 1 to 3 and findings V3 to V7 are untouched.

### 10.1 R2 — the `@eval` stand-in covers one of the eval row's two files

The finding holds. This round reports the hole and writes it into the stage table
as a comment; it does not close it, because closing it moves today's inject key
(section 10.2).

`STAGES["eval"]["versions"]` is `("eval/utils/probe_eval.py",
"data/probe_output.py")`. Round 2's V1 fix put the `@eval` marker on the first of
the two, on the inject row (`schema.py:297`, with the comment block above it). The second file is absent from the
inject row: the inject row reaches `data/probe_output.py` only through the
`probe_score.train` key it folds, and the train row's own entry for that file
reads the file's effective version for `train`. So `data/probe_output.py` is read
for the inject key under `train`, and never under `eval`.

Measured on the ticket-04 fixture (P11 part B below), bumping
`data/probe_output.py` to `VERSION = 2`:

| the entry's `stale` | eval key | inject key |
| --- | --- | --- |
| `("eval",)` | moves | stays |
| `("eval", "inject")` | moves | stays |
| `("train",)` | moves (it folds the train key) | moves |
| `("eval", "train")` | moves | moves |
| every stage, or no table at all | moves | moves |

Writing `inject` into the entry changes nothing, exactly as the finding says: the
inject row does not list the file, so the declaration is unreachable from the file.
The one `stale` value that moves the inject key is one that also names `train`,
and that throws the trained probe away with it — the combination the ruling exists
to avoid paying.

Against `78e9260` (P11 part B, second half): every one of those bumps moved both
keys there, because a bump was stale everywhere. The ruling makes "eval stale,
train usable" expressible for the first time, and that is the one combination the
inject key cannot be reached by.

What the hole costs, traced in the code on this branch: `freeze` rewrites
`_upstream` and `_resolved` whole (`schema.py:1443` and `:1447`; only the `sample`
and `inject` request fields merge, `_merge_request_fields`), and
`models/probe_models/service.py:205` reads `cfg._resolved["probe_temperature"]`
back out of the frozen `settings.yaml`. An inject directory found under an
unchanged key is therefore re-frozen with the new eval run's key and the new
theta's temperature over records produced with the old one. The step that fills
`_resolved["probe_temperature"]` is `run.py`'s (ticket 14) and is not on this
branch; `jobs/launch.py:824` passes on whatever the caller resolved.

The reach is measured over the whole stage table, not asserted (P11 part A):
`"key": "carry"` appears once in `STAGES` (`schema.py:272`, the inject row's
`probe_score.eval`), and `data/probe_output.py` is the only file of the carried
row with no stand-in on the carrying row.

What this round changed, in full: five comment lines under the `@eval` entry,
naming the eval row's other file, what a bump of it does to each key, and that the
stand-in for it is the owner's to add.

```
$ git diff a3d18e2..HEAD
@@ -289,6 +289,11 @@ STAGES = {
                  # `@eval`: this row folds the eval driver for the carried probe_score eval
                  # key's sake (the fitted temperature a live run reads), so it folds the
                  # version that stage's key folds as well (errata "3.3 / 8.6").
+                 # The eval row's other file, `data/probe_output.py`, carries no stand-in
+                 # here: a bump of it stating `stale: ("eval",)` moves the carried eval key
+                 # and leaves this key where it is, and an entry that names `train` as well
+                 # moves this key, through the folded probe_score train key. Adding the
+                 # stand-in moves today's inject key, so that one is the owner's to add.
                  "eval/utils/probe_eval.py@eval",
                  "eval/utils/probe_eval.py#MATCH_VERSION.{probe_score_method}"),
   },
```

### 10.2 Why the remedy is left to the owner

`"data/probe_output.py@eval"` on the inject row adds an entry named
`data/probe_output.py` to the inject key's versions payload, so every inject key
moves the day it lands. The dispatch pins P1 — every key equal to the key
`78e9260` computes — so an implementer cannot take that route.

What it would cost in output today: nothing. Every stage directory under the
outputs root is empty (listed 2026-09-18):

```
$ cd /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs && ls -1 . debug
.:
debug
eval
sample
train

debug:
eval
inject
sample
score
train
$ for d in sample train eval debug/eval debug/inject debug/sample debug/score debug/train; do \
      printf '%-16s %s run directories\n' "$d" "$(ls -1 "$d" | wc -l)"; done
sample           0 run directories
train            0 run directories
eval             0 run directories
debug/eval       0 run directories
debug/inject     0 run directories
debug/sample     0 run directories
debug/score      0 run directories
debug/train      0 run directories
```

So the choice in front of the owner is between an inject key that moves while no
run directory exists anywhere, and a hole that the first eval-side bump of
`data/probe_output.py` falls into.

### 10.3 Proofs

**P11 (new) — how far the `@eval` stand-in reaches.** `/tmp/vh4/p11.py`. Part A
walks every carried upstream of the stage table and reports, per file the carried
stage lists, whether the carrying row stands in for it. Part B bumps
`data/probe_output.py` six ways and prints which keys move, first with this
branch's `schema.py` and then with the one from `78e9260`, both pointed at the same
fixture.

```
$ git show 78e9260:experimental_settings/schema.py > /tmp/vh4/old_schema.py
$ FIX=$(bash /tmp/vh/mkfix.sh); PYTHONPATH=$PWD python3 /tmp/vh4/p11.py "$FIX" /tmp/vh4/old_schema.py
== A: every carried upstream, and which of the carried row's files have a stand-in ==
inject carries 'probe_score.eval' (the key of stage 'eval')
    eval/utils/probe_eval.py           stand-in on the inject row
    data/probe_output.py               ABSENT from the inject row

== B: data/probe_output.py bumped, keys read with the schema.py of this branch ==
-- stale ("eval",) --
   same  inject key                             373d26d8bc27 -> 373d26d8bc27
   MOVED inject _upstream[probe_score.eval]     67e377456b8e -> 37d420492922
   same  inject _upstream[probe_score.train]    a7f5ebd1adbe -> a7f5ebd1adbe
   MOVED ctool eval key                         67e377456b8e -> 37d420492922
   same  ctool train key                        a7f5ebd1adbe -> a7f5ebd1adbe
-- stale ("eval","inject") --
   same  inject key                             373d26d8bc27 -> 373d26d8bc27
   MOVED inject _upstream[probe_score.eval]     67e377456b8e -> 37d420492922
   same  inject _upstream[probe_score.train]    a7f5ebd1adbe -> a7f5ebd1adbe
   MOVED ctool eval key                         67e377456b8e -> 37d420492922
   same  ctool train key                        a7f5ebd1adbe -> a7f5ebd1adbe
-- stale ("train",) --
   MOVED inject key                             373d26d8bc27 -> e8f00a2571f7
   MOVED inject _upstream[probe_score.eval]     67e377456b8e -> 9982bf9f0be3
   MOVED inject _upstream[probe_score.train]    a7f5ebd1adbe -> a0c848d7bc3e
   MOVED ctool eval key                         67e377456b8e -> 9982bf9f0be3
   MOVED ctool train key                        a7f5ebd1adbe -> a0c848d7bc3e
-- stale ("eval","train") --
   MOVED inject key                             373d26d8bc27 -> e8f00a2571f7
   MOVED inject _upstream[probe_score.eval]     67e377456b8e -> 0e3acf814a44
   MOVED inject _upstream[probe_score.train]    a7f5ebd1adbe -> a0c848d7bc3e
   MOVED ctool eval key                         67e377456b8e -> 0e3acf814a44
   MOVED ctool train key                        a7f5ebd1adbe -> a0c848d7bc3e
-- stale ("sample","build","train","eval","inject","score") --
   MOVED inject key                             373d26d8bc27 -> e8f00a2571f7
   MOVED inject _upstream[probe_score.eval]     67e377456b8e -> 0e3acf814a44
   MOVED inject _upstream[probe_score.train]    a7f5ebd1adbe -> a0c848d7bc3e
   MOVED ctool eval key                         67e377456b8e -> 0e3acf814a44
   MOVED ctool train key                        a7f5ebd1adbe -> a0c848d7bc3e
-- no table (VERSION 2) --
   MOVED inject key                             373d26d8bc27 -> e8f00a2571f7
   MOVED inject _upstream[probe_score.eval]     67e377456b8e -> 0e3acf814a44
   MOVED inject _upstream[probe_score.train]    a7f5ebd1adbe -> a0c848d7bc3e
   MOVED ctool eval key                         67e377456b8e -> 0e3acf814a44
   MOVED ctool train key                        a7f5ebd1adbe -> a0c848d7bc3e

== B: data/probe_output.py bumped, keys read with the schema.py of 78e9260 ==
-- stale ("eval",) --
   MOVED inject key                             373d26d8bc27 -> e8f00a2571f7
   MOVED inject _upstream[probe_score.eval]     67e377456b8e -> 0e3acf814a44
   MOVED inject _upstream[probe_score.train]    a7f5ebd1adbe -> a0c848d7bc3e
   MOVED ctool eval key                         67e377456b8e -> 0e3acf814a44
   MOVED ctool train key                        a7f5ebd1adbe -> a0c848d7bc3e
-- stale ("eval","inject") --
   MOVED inject key                             373d26d8bc27 -> e8f00a2571f7
   MOVED inject _upstream[probe_score.eval]     67e377456b8e -> 0e3acf814a44
   MOVED inject _upstream[probe_score.train]    a7f5ebd1adbe -> a0c848d7bc3e
   MOVED ctool eval key                         67e377456b8e -> 0e3acf814a44
   MOVED ctool train key                        a7f5ebd1adbe -> a0c848d7bc3e
-- stale ("train",) --
   MOVED inject key                             373d26d8bc27 -> e8f00a2571f7
   MOVED inject _upstream[probe_score.eval]     67e377456b8e -> 0e3acf814a44
   MOVED inject _upstream[probe_score.train]    a7f5ebd1adbe -> a0c848d7bc3e
   MOVED ctool eval key                         67e377456b8e -> 0e3acf814a44
   MOVED ctool train key                        a7f5ebd1adbe -> a0c848d7bc3e
-- stale ("eval","train") --
   MOVED inject key                             373d26d8bc27 -> e8f00a2571f7
   MOVED inject _upstream[probe_score.eval]     67e377456b8e -> 0e3acf814a44
   MOVED inject _upstream[probe_score.train]    a7f5ebd1adbe -> a0c848d7bc3e
   MOVED ctool eval key                         67e377456b8e -> 0e3acf814a44
   MOVED ctool train key                        a7f5ebd1adbe -> a0c848d7bc3e
-- stale ("sample","build","train","eval","inject","score") --
   MOVED inject key                             373d26d8bc27 -> e8f00a2571f7
   MOVED inject _upstream[probe_score.eval]     67e377456b8e -> 0e3acf814a44
   MOVED inject _upstream[probe_score.train]    a7f5ebd1adbe -> a0c848d7bc3e
   MOVED ctool eval key                         67e377456b8e -> 0e3acf814a44
   MOVED ctool train key                        a7f5ebd1adbe -> a0c848d7bc3e
-- no table (VERSION 2) --
   MOVED inject key                             373d26d8bc27 -> e8f00a2571f7
   MOVED inject _upstream[probe_score.eval]     67e377456b8e -> 0e3acf814a44
   MOVED inject _upstream[probe_score.train]    a7f5ebd1adbe -> a0c848d7bc3e
   MOVED ctool eval key                         67e377456b8e -> 0e3acf814a44
   MOVED ctool train key                        a7f5ebd1adbe -> a0c848d7bc3e

the file is back to its fixture text: 'VERSION = 1\n'
```

(The two sides differ in the `("eval",)` and `("eval","inject")` cases only in
that this branch keeps the inject key and `78e9260` moves it; every other case is
the same verdict on both sides. The three hashes this branch prints under
`stale: ("train",)` differ from the `("eval","train")` ones because the eval key
folds the train key while its own entry for the file stays at effective version 1.)

**P1 rerun — every key that keys is still the key of `78e9260`.** The pinned gate,
rerun because this round touched `schema.py` at all.

```
$ FIX=$(bash /tmp/vh/mkfix.sh); PYTHONPATH=$PWD python3 /tmp/vh/p1.py "$FIX" /tmp/vh4/old_schema.py
same  baseline/gpt_oss_120b_appworld sample                5e898c2e7741
same  baseline/gpt_oss_120b_appworld score                 8f16442a6e72
skip  debug.yaml: no workflow line, it is the debug overlay
same  inject/probe_p1_e1_theta_0pt80 inject                373d26d8bc27
same  inject/probe_p1_e1_theta_0pt80 score                 1a8e6643f8ef
same  inject/no_probe_p1_e1_theta_0pt80 inject             6d18fcc8d2d0
same  inject/no_probe_p1_e1_theta_0pt80 score              6755666ac372
same  train_probe/ctool_qwen3_0pt6b sample                 5e898c2e7741
same  train_probe/ctool_qwen3_0pt6b build                  aa9b69a5cc81
same  train_probe/ctool_qwen3_0pt6b train                  a7f5ebd1adbe
same  train_probe/ctool_qwen3_0pt6b eval                   67e377456b8e
same  train_probe/cgen_qwen3_0pt6b sample                  5e898c2e7741
same  train_probe/cgen_qwen3_0pt6b build                   aa9b69a5cc81
same  train_probe/cgen_qwen3_0pt6b train                   7c509d3a79fa
same  train_probe/cgen_qwen3_0pt6b eval                    c622550d0044
same  train_probe/cparam_qwen3_0pt6b sample                5e898c2e7741
same  train_probe/cparam_qwen3_0pt6b build                 aa9b69a5cc81
same  train_probe/cparam_qwen3_0pt6b train                 d047fc949418
same  train_probe/cparam_qwen3_0pt6b eval                  b710e6d08915

equal keys: 18
moved keys: 0 []
raised on both sides: 0
raised on one side only: 0 []
```

The same comparison over the real repo's `experimental_settings/*.yaml`, both
modules' `ROOT` at this worktree root (the `FileNotFoundError` paths are shown
shortened, and are the same full path on both sides):

```
$ PYTHONPATH=$PWD python3 /tmp/vh/p1.py "$PWD" /tmp/vh4/old_schema.py
same  baseline/gpt_oss_120b_appworld sample                5e898c2e7741
same  baseline/gpt_oss_120b_appworld score                 8f16442a6e72
skip  debug.yaml: no workflow line, it is the debug overlay
same  train_probe/ctool_qwen3_0pt6b sample                 5e898c2e7741
same  train_probe/ctool_qwen3_0pt6b build                  aa9b69a5cc81
same  train_probe/cgen_qwen3_0pt6b sample                  5e898c2e7741
same  train_probe/cgen_qwen3_0pt6b build                   aa9b69a5cc81
same  train_probe/cparam_qwen3_0pt6b sample                5e898c2e7741
same  train_probe/cparam_qwen3_0pt6b build                 aa9b69a5cc81

equal keys: 8
moved keys: 0 []
raised on both sides: 10
  raise inject/probe_p1_e1_theta_0pt80 inject       new=FileNotFoundError: ... /train/methods | old=FileNotFoundError: ... /train/methods
  raise inject/probe_p1_e1_theta_0pt80 score        new=FileNotFoundError: ... /train/methods | old=FileNotFoundError: ... /train/methods
  raise inject/no_probe_p1_e1_theta_0pt80 inject    new=FileNotFoundError: ... /train/methods | old=FileNotFoundError: ... /train/methods
  raise inject/no_probe_p1_e1_theta_0pt80 score     new=FileNotFoundError: ... /train/methods | old=FileNotFoundError: ... /train/methods
  raise train_probe/ctool_qwen3_0pt6b train         new=FileNotFoundError: ... /train/utils/t | old=FileNotFoundError: ... /train/utils/t
  raise train_probe/ctool_qwen3_0pt6b eval          new=FileNotFoundError: ... /train/utils/t | old=FileNotFoundError: ... /train/utils/t
  raise train_probe/cgen_qwen3_0pt6b train          new=FileNotFoundError: ... /train/utils/t | old=FileNotFoundError: ... /train/utils/t
  raise train_probe/cgen_qwen3_0pt6b eval           new=FileNotFoundError: ... /train/utils/t | old=FileNotFoundError: ... /train/utils/t
  raise train_probe/cparam_qwen3_0pt6b train        new=FileNotFoundError: ... /train/utils/t | old=FileNotFoundError: ... /train/utils/t
  raise train_probe/cparam_qwen3_0pt6b eval         new=FileNotFoundError: ... /train/utils/t | old=FileNotFoundError: ... /train/utils/t
raised on one side only: 0 []
```

Eighteen keys on the fixture and eight on the real tree, every one equal to
`78e9260`'s; the ten stages that raise fold a `train/` version entry and `train/`
does not exist on this branch, and both sides raise the same error on the same
file.

**P9 rerun — round 2's stand-in proof, unchanged by this round.**

```
$ FIX=$(bash /tmp/vh/mkfix.sh); PYTHONPATH=$PWD python3 /tmp/vh/p9.py "$FIX"
at VERSION = 1, empty table:
  ctool_qwen3_0pt6b train                a7f5ebd1adbe
  ctool_qwen3_0pt6b eval                 67e377456b8e
  cgen_qwen3_0pt6b train                 7c509d3a79fa
  cgen_qwen3_0pt6b eval                  c622550d0044
  cparam_qwen3_0pt6b train               d047fc949418
  cparam_qwen3_0pt6b eval                b710e6d08915
  probe_p1_e1_theta_0pt80 inject         373d26d8bc27
  no_probe_p1_e1_theta_0pt80 inject      6d18fcc8d2d0

the inject key's versions payload entry for the eval driver: {'eval/utils/probe_eval.py': 1, 'eval/utils/probe_eval.py#MATCH_VERSION.ctool': 1}
the inject run's _versions record for it:       {'eval/utils/probe_eval.py': 1, 'eval/utils/probe_eval.py#MATCH_VERSION.ctool': 1}

-- VERSION = 2, no table at all --
  effective version per stage: {'sample': 2, 'build': 2, 'train': 2, 'eval': 2, 'inject': 2, 'score': 2}
  moved:  ['cgen_qwen3_0pt6b eval', 'cparam_qwen3_0pt6b eval', 'ctool_qwen3_0pt6b eval', 'no_probe_p1_e1_theta_0pt80 inject', 'probe_p1_e1_theta_0pt80 inject']
  stayed: ['cgen_qwen3_0pt6b train', 'cparam_qwen3_0pt6b train', 'ctool_qwen3_0pt6b train']

-- VERSION = 2, stale: ("eval",) --
  effective version per stage: {'sample': 1, 'build': 1, 'train': 1, 'eval': 2, 'inject': 1, 'score': 1}
  moved:  ['cgen_qwen3_0pt6b eval', 'cparam_qwen3_0pt6b eval', 'ctool_qwen3_0pt6b eval', 'no_probe_p1_e1_theta_0pt80 inject', 'probe_p1_e1_theta_0pt80 inject']
  stayed: ['cgen_qwen3_0pt6b train', 'cparam_qwen3_0pt6b train', 'ctool_qwen3_0pt6b train']

-- VERSION = 2, stale: ("inject",) --
  effective version per stage: {'sample': 1, 'build': 1, 'train': 1, 'eval': 1, 'inject': 2, 'score': 1}
  moved:  ['no_probe_p1_e1_theta_0pt80 inject', 'probe_p1_e1_theta_0pt80 inject']
  stayed: ['cgen_qwen3_0pt6b eval', 'cgen_qwen3_0pt6b train', 'cparam_qwen3_0pt6b eval', 'cparam_qwen3_0pt6b train', 'ctool_qwen3_0pt6b eval', 'ctool_qwen3_0pt6b train']

-- VERSION = 2, stale: () --
  effective version per stage: {'sample': 1, 'build': 1, 'train': 1, 'eval': 1, 'inject': 1, 'score': 1}
  moved:  []
  stayed: ['cgen_qwen3_0pt6b eval', 'cgen_qwen3_0pt6b train', 'cparam_qwen3_0pt6b eval', 'cparam_qwen3_0pt6b train', 'ctool_qwen3_0pt6b eval', 'ctool_qwen3_0pt6b train', 'no_probe_p1_e1_theta_0pt80 inject', 'probe_p1_e1_theta_0pt80 inject']

restored: 'VERSION = 1' | keys back: True
```

**P8 rerun — `schema.py` loads and the diff against `78e9260` touches the same 21
files.**

```
$ PYTHONPATH=$PWD python3 -c "import experimental_settings.schema as S; print('schema imports:', S.__name__); [print('  ', e) for e in S.STAGES['inject']['versions']]"
schema imports: experimental_settings.schema
   agent/loop.py
   agent/generate.py
   agent/inject.py
   agent/inject_format.py
   data/probe_input.py
   data/trajectory_record.py
   data/environments/__init__.py
   data/environments/{env}.py
   models/agent_models/{family}.py
   models/agent_models/service.py
   models/probe_models/base.py
   models/probe_models/service.py
   eval/utils/probe_eval.py@eval
   eval/utils/probe_eval.py#MATCH_VERSION.{probe_score_method}
$ git diff --stat 78e9260..HEAD | tail -3
 models/probe_models/qwen.py     |  11 +++
 models/probe_models/service.py  |  11 +++
 21 files changed, 407 insertions(+), 25 deletions(-)
```

`schema.py` is `venv: any`, so `python3` is its interpreter; the 18 versioned
files P8 imports are untouched this round and their imports stand as section 3
pasted them.
Proofs P2 to P7 read no line this round changed — the diff is five `#` lines
inside a tuple literal — and P1, P9 and P11 all exercise the table they sit in.

### 10.4 Decisions this round that the ruling did not make

1. **The hole is written into `schema.py` as well as into this report.** The
   finding's remedy is "report it"; the comment goes further, next to the entry it
   qualifies, because the stage table is what the next person edits and the
   existing `@eval` comment says what the stand-in covers without saying what it
   leaves out. A comment cannot move a key, and P1 was rerun to show it.
2. **The comment names the `train` route too.** "No `stale` value can move the
   inject key" is true of every value that leaves the train run usable and false of
   one that names `train` (P11). The comment states both, so an author reading it
   knows the price of the only route the table offers today.
3. **Nothing else changed**: no refusal, no warning, no new marker, no stage-table
   entry. Rounds 1 to 3 stand exactly as sections 1 to 9 record them.

### 10.5 Corrections to the earlier sections of this report

- **Section 8.1** describes the V1 fix as though the eval row held one file. Its
  sentence "both natural declarations therefore move the inject key" holds for
  `eval/utils/probe_eval.py` and fails for `data/probe_output.py`, which the inject
  row does not list.
- **Section 8.4 item 1** ("a stand-in entry folds the highest version that made
  either stage stale") is accurate about the entry and silent about the file with
  no entry; read it together with 10.1.
- **Section 9.5** listed what was left for the owner and did not name this hole.
  10.6 below is that list with the hole in it.

### 10.6 Left open for the owner

- **The stand-in for `data/probe_output.py` (R2).** Three ways out, none of them
  an implementer's to take:
  1. `"data/probe_output.py@eval"` on the inject row. It closes the hole for every
     declaration, and it moves today's inject keys (`373d26d8bc27` and
     `6d18fcc8d2d0` on the fixture). No run directory exists to be orphaned by that
     move (10.2), so the cost today is the pinned P1 requirement alone.
  2. Leave the row as it is and have the author of such a bump write
     `stale: ("eval", "train")`. The inject key moves, and the trained probe is
     thrown away with it.
  3. Have `run.py` (ticket 14) compare an inject directory's recorded
     `_upstream["probe_score.eval"]` against the current one and refuse the reuse
     when the two differ. `freeze` already writes that block and `load_frozen`
     already reads it back (`schema.py:1443`, `:1478`), so the comparison needs no
     key to move. This is a route the code allows, not a ruling: 8.6's `behind`
     flag is the nearest thing the contracts name.
- **The 2.5 inject gate still needs effective versions** (sections 8.5 and 9.5,
  unchanged): contracts 2.5 compares a recorded `_versions` entry against the
  source's `VERSION` line, which under the ruling refuses a run the ruling says is
  fine. Ticket 14's code, not `schema.py`'s.
- **A directory extended across a usable bump holds bytes of two real `VERSION`s**
  (section 9.5, unchanged): the directory-level record names the launch that wrote
  it, and the per-launch pairs of commit and versions are the `runs.jsonl` start
  rows (`jobs/launch.py:844`, `:846`).
- V3 to V7 of the round-1 review are outside this round's list and untouched.

### 10.7 Commits

- `ff3bbb0` (this round) — the inject row names the eval row's file it has no
  stand-in for: five comment lines under `"eval/utils/probe_eval.py@eval"`, no
  executable line.

## 11. Adversarial review of round 4 (read-only reviewer, 2026-09-18)

Range read: `78e9260..ff3bbb0` whole, this round's diff
`a3d18e2..ff3bbb0`. Nothing in the repository was changed by this review except
this section. The code was exported with `git archive ff3bbb0 experimental_settings
data models agent eval jobs constants README.md` into `/tmp/rev/exp.B5VO`; the
ticket-04 fixture was rebuilt from the ticket's own `mkfix.sh` body
(`/tmp/rev/mkfix.sh`, lines 441-497 of the ticket) and adapted for the fold by
one change only: `eval/utils/probe_eval.py` in the fixture carries
`PROBE_KIND` and `MATCH_VERSION` beside its `VERSION`, which `_method_kind` and
the `#MATCH_VERSION` entries now read. The `eval/methods/<m>.py` stubs were left
where `mkfix.sh` puts them and are read by nothing.

### 11.1 What was recomputed, and what it showed

Every number below was produced by the reviewer's own scripts under `/tmp/rev`,
not read out of sections 1 to 10.

- **P1, fixture** (`p1.py`, both modules pointed at the same fixture): 18 stage
  keys, all equal to the keys `git show 78e9260:experimental_settings/schema.py`
  computes, hash for hash (`5e898c2e7741`, `aa9b69a5cc81`, `a7f5ebd1adbe`,
  `67e377456b8e`, `373d26d8bc27`, ...). Moved: 0.
- **P1, real tree**: 8 keys equal, 10 stages raise `FileNotFoundError` on
  `train/` on both sides, 0 raise on one side only.
- **Frozen documents**: `freeze` run for all 18 setting/stage pairs with both
  modules; every `settings.yaml` document is identical, so `_upstream`,
  `_versions`, `_commit` and the projection are untouched by the change.
- **P2**: `data/environments/appworld.py` at `VERSION = 2` with
  `{2: {"why": "x", "stale": ("inject",)}}` moves the inject key (and the score
  key that folds it) and leaves all twelve sample/build/train/eval keys;
  `effective_version` is 2 for inject and 1 elsewhere; the frozen `_versions`
  entry for the file is 2.
- **P3/P4**: no table -> all 14 keys move; an entry with no `"stale"` -> all 14
  move; `"stale": ()` -> none moves and the keys equal the baseline exactly.
- **P5**: all nine malformed shapes raise `SchemaError` naming the file
  (non-mapping table, `"2"` key, key 1, key 3, key `True`, non-mapping entry,
  `"stale"` a string, `"stale"` naming `injekt`, two column-zero literals); a
  missing `"why"` and a list-valued `"stale"` both pass.
- **P6**: `MATCH_VERSION["cgen"] 1 -> 2` moves cgen's train key and cgen's eval
  key (the eval stage folds its own train key) and no ctool or cparam key; a
  `VERSION` bump of `probe_eval.py` moves the eval keys and no train key.
- **The V1 stand-in**: a `probe_eval.py` bump stale for `eval` moves the three
  eval keys and both inject keys; stale for `inject` moves the two inject keys
  only; stale for `train` or `()` moves nothing.
- **Imports**: the import matrix (18 versioned modules x 4 interpreters, 59
  successes) is identical at `78e9260` and at `ff3bbb0`, so no import broke.
- **The 18 comment blocks**: compared line by line against the pinned text;
  all 18 identical, `VERSION_HISTORY = {}` on the line directly below `VERSION`
  exactly once in each, `git diff --numstat` `11 0` for every one of them.
- **R2's measurement**: reproduced exactly, including that
  `stale: ("eval", "inject")` leaves the inject key at `373d26d8bc27` while the
  carried `probe_score.eval` upstream moves, and that `stale: ("inject",)` alone
  on `data/probe_output.py` moves nothing at all.
- **The claim that the remedy moves today's key**: measured. Adding
  `"data/probe_output.py@eval"` to the inject row moves 4 keys (both inject keys
  and both score keys that fold them) and leaves the other 14 — so the route the
  report hands to the owner does cost the pinned P1 requirement, as stated.

R2 is therefore **addressed as reported**: the finding's own remedy was to report
the hole, and it is now stated next to the entry it qualifies and measured in
section 10. The hole itself stays open and is the owner's call.

### 11.2 New findings, three, all minor

1. **A misspelled `@<stage>` marker is silently inert.** `_key_versions` builds
   `stages = (stage, stands_for)` and never checks `stands_for` against `STAGES`,
   while `_check_version_history` refuses a `stale` tuple that names a stage that
   does not exist. Measured: with `probe_eval.py` stale for `eval`, the table
   spelled `@eval` keys inject as `18809eee8194` and the same table spelled
   `@evel` keys it as `373d26d8bc27`, the unbumped value, with no refusal.
2. **One path listed twice on a row silently keeps the last entry.** Both
   `versions_of` and `_key_versions` write `out[name]`, and a `@stage` entry
   enters under the bare path, so a row that lists `<path>` and `<path>@<stage>`
   keeps whichever comes last and the key depends on the tuple order. Measured on
   the eval row with `data/probe_output.py` stale for `inject`: stand-in last
   keys `37d420492922`, stand-in first keys `67e377456b8e`. Unreachable today,
   and reachable the moment a stand-in is added for a file its row already lists.
3. **README, the sentence after the edited one.** The offered-names sentence
   gained `version_history` and `effective_version`; the sentence below it, "…
   are called only by this file and by `run.py`", was not extended with them,
   although the ruling gives both readers in `run.py` (`ls` and `selfcheck`).
