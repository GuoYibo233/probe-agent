# Wave 6 post-merge fix: area "selfcheck"

Branch `fix/2026-09-20-wave6-selfcheck`, base `f810f9f`, head `3d199b1`.
Worktree `/home/y-guo/reproduce/new1-wt/2026-09-20-wave6-fix-selfcheck` (removed at
the end; the branch stays). Files touched: `run.py` and `README.md` only.
`$PR` is `/home/y-guo/reproduce/new1/external/probe-env/bin/python`.

All fifteen findings are fixed; none is declined. Five of them are the same three
defects seen through two lenses, so the fix count is twelve.

## The commits

| commit | what it fixes | findings |
|---|---|---|
| `15b66e5` | one `_parse` reader for every ast pass, reading through `ROOT`; `_safe_parse` for a check's per-file loop; `cmd_selfcheck` turns a raising check into one problem line | checks-blind:SC-2, checks-fire:W6-L15-02, checks-fire:W6-L15-04, runpy-regression:W6-L15-4, checks-blind:SC-9 |
| `7f8964e` | the two literal readers drop their own `selfcheck: ` prefix and the doubled quote | checks-fire:W6-L15-05 |
| `96acf01` | check 2 tests which package a by-name `import_module` names, and reports an annotation fragment that is a path token naming no repo file | checks-blind:SC-3, checks-blind:SC-6 |
| `6630b77` | check 4's set difference runs in both directions and the strict shape covers every versioned file; `_resolve_versions_entry` expands every template | checks-fire:W6-L15-01, checks-blind:SC-5, checks-blind:SC-8 |
| `8e71bf3` | check 1 requires all five annotation labels on a `.py` entry; check 10 requires the `venv:` value to name an interpreter | checks-blind:SC-4 |
| `7ee140e` | check 7 reads its literals directly, so `DEFAULT_EFFORT = None` is a value, not a refusal; EFFORTS proved a tuple first | runpy-regression:W6-L15-2 |
| `95f871f` | check 9's header comment no longer spells the two cluster path roots | runpy-regression:W6-L15-3 |
| `72228bb` | README section 3 recipes 1, 2, 6 and 7 name the bindings and the annotation lines selfcheck requires | pipeline-review-skills:W6-L15-2 |
| `3d199b1` | one parse-failure line per file per check, not one per reader | follow-up inside the parse fix |

## Two approved fixes that disagreed, and what was built

checks-fire:W6-L15-04's verifier approved aborting the run on an unparsable file;
runpy-regression:W6-L15-4's verifier approved collecting and continuing. The built
fix satisfies both goals: `_parse` refuses with the `SystemExit` shape `literal_of`
already uses, `_safe_parse` and the per-file guards keep a check going over the
rest of its files, and `cmd_selfcheck` turns a check that still raises into one
problem line, so the other ten checks run and the summary prints. Nothing aborts.

checks-fire:W6-L15-01 and checks-blind:SC-5 are the same defect; their fixes differ
on whether an unnamed versioned file also gets the strict `VERSION_HISTORY` shape.
The critical finding's fix (shape over the union) was built, because gyb's 2026-09-18
comment scopes the shape to "every file with a column-zero `VERSION`".

## Acceptance, real output

### Selfcheck from the worktree root

```
$ "$PR" run.py selfcheck; echo "rc=$?"
selfcheck: 31 python files, 0 problems
rc=0
```

### Selfcheck from another working directory

```
$ cd /tmp && "$PR" /home/y-guo/reproduce/new1-wt/2026-09-20-wave6-fix-selfcheck/run.py selfcheck; echo "rc=$?"
selfcheck: 31 python files, 0 problems
rc=0
```

### Ticket 14's D3 grep over run.py

```
$ grep -n "/home/\|/net/" run.py || echo NO_ABS_PATH
NO_ABS_PATH
```

### Ticket 15's D2

```
3
['data.training_data', 'os']
two matches -> refused: True | /tmp/tmpsk6u44e0/bad.py: 2 column-zero assignments to 'VERSION', expected exactly one
```
with `from dataclasses import dataclass` in the fixture:
```
['dataclasses', 'os']
```
the two literal readers:
```
['note', 'p1_e1', 'p1_e2', 'p2_e1', 'p2_e2']
literal_of refuses FORMATS: SystemExit agent/injected_text_formats.py: 'FORMATS' has a value that is not a literal (malformed node or string on line 65: <ast.Call object at 0x7f8fde92f130>)
```
the four annotation lines (`_parse_annotation` now returns a third list, the dead
path tokens, empty on every line of today's README):
```
train/utils/trainer.py used by : ['train/methods/cgen.py', 'train/methods/cparam.py', 'train/methods/ctool.py'] | by name: [] | dead: []
models/agent_models/service.py used by : ['agent/run_tasks.py', 'agent/step_without_probe.py'] | by name: [] | dead: []
models/probe_models/base.py imports : ['models/__init__.py'] | by name: [('models/probe_models/<backbone>.py', 'by name, inside load()')] | dead: []
models/probe_models/__init__.py used by, package rule: equal to the directory
```
check 5's structural read and check 4's expansion:
```
data/trajectory_record.py {'SCHEMA': 1, 'DEFAULTS': 1, 'REQUIRED': 1} 12 []
data/training_data.py {'SCHEMA': 1, 'DEFAULTS': 1, 'REQUIRED': 1} 16 []
data/probe_output.py {'SCHEMA': 1, 'DEFAULTS': 1, 'REQUIRED': 1} 9 []
22 missing: []
run._stage_table_files(): 22
```

### D5

```
usage: run.py <workflow> <setting> [<setting> ...] [--debug] [--allow-dirty] [section.field=value ...]
...
subcommands:
  ls          [workflow] [--debug] -- one folded line per run
  where       <workflow> <setting> <stage> [--debug] -- the absolute run directory for one stage
  find        section.field=value ... -- the runs whose settings_diff matches every given field
  kill        <workflow> <setting> <stage> -- end one run's pieces, write the killed finish row
  refire      <workflow> <setting> <stage> [--piece i] [--allow-dirty] -- restart one dead piece
  retry       <workflow> <setting> <stage> [--allow-dirty] -- clear markers, then launch it fresh
  table       [workflow] [--out FILE] [--debug] -- the backbone x method x risk table
  free        -- the free cards per host
  sync        -- fold done.json and heartbeats into missing finish rows
  selfcheck   -- the tree's self-consistency checks
rc=0
```

### D6

28 paths, then `D6 ok`, exit 0. The first and last of them:
```
/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/sample/a7d8b62ee953
...
/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/debug/score/8f3279571a21
D6 ok
```

### D7

```
baseline.yaml gpt_oss_120b_appworld real sample=a7d8b62ee953 score=87858c091092
baseline.yaml gpt_oss_120b_appworld debug sample=96de225de2b4 score=20eaad1deae5
train_probe.yaml ctool_qwen3_0pt6b real sample=a7d8b62ee953 build=6d3bf5aff879 train=d54f9e0199cc eval=834b3a696768
train_probe.yaml ctool_qwen3_0pt6b debug sample=96de225de2b4 build=b565f5ab1b94 train=22a0980de899 eval=61c95c5e5d9e
train_probe.yaml cgen_qwen3_0pt6b real sample=a7d8b62ee953 build=6d3bf5aff879 train=7d2b29f8d708 eval=a5fdf2e5cb9c
train_probe.yaml cgen_qwen3_0pt6b debug sample=96de225de2b4 build=b565f5ab1b94 train=f4b98907f380 eval=40707c4b0c02
train_probe.yaml cparam_qwen3_0pt6b real sample=a7d8b62ee953 build=6d3bf5aff879 train=cfd89ab5cb10 eval=fb41fe88a470
train_probe.yaml cparam_qwen3_0pt6b debug sample=96de225de2b4 build=b565f5ab1b94 train=4f98555bfe73 eval=feb38b81056f
inject.yaml probe_p1_e1_theta_0pt80 real inject=b4c915d20196 score=db3bb3816292
inject.yaml probe_p1_e1_theta_0pt80 debug inject=d6e2ebd3d7f4 score=93f2718f6e2a
inject.yaml no_probe_p1_e1_theta_0pt80 real inject=4143d5301a39 score=7520d278f25a
inject.yaml no_probe_p1_e1_theta_0pt80 debug inject=668b1716daf1 score=8f3279571a21
D7 ok
rc=0
```

### Tests

```
$ "$PR" -m unittest
Ran 0 tests in 0.000s
OK
rc=0
```
`-m unittest` with no argument discovers nothing, because `tests/` is not an
importable package; that is how the tree stands today and this branch does not
change it. The two test files run the way README section 2 documents:
```
$ "$PR" tests/test_registry_concurrent_append.py
Ran 1 test in 0.208s
OK
rc=0
$ PYTHONPATH=. "$PR" tests/test_packed_loss.py
Ran 3 tests in 2.573s
OK
rc=0
```
`test_packed_loss.py` imports `data.training_data`, so it needs the repo root on
the path; README's sentence names the run command for the first file only.

## Each fix proved on a scratch copy

The scratch tree was built with
`git archive HEAD | tar -x -C <scratch>/base` from this branch and deleted at the
end. Baseline in it: `selfcheck: 31 python files, 0 problems`, rc=0.

**checks-fire:W6-L15-01 + checks-blind:SC-5** — `VERSION = 3` and
`VERSION_HISTORY = {7: {"stale": ("nowhere",)}}` appended to `eval/method_table.py`,
a file the stage table does not name, with no rule comment block:
```
check 4: eval/method_table.py carries a column-zero VERSION but the stage table's versions do not name it
check 4: eval/method_table.py: the lines directly above VERSION (line 163) do not match the pinned VERSION rule comment block
check 4: eval/method_table.py: VERSION_HISTORY keys [7] != expected [2, 3]
check 4: eval/method_table.py: VERSION_HISTORY[7] has no non-empty 'why'
check 4: eval/method_table.py: VERSION_HISTORY[7]['stale'] names ['nowhere'], not one of ['build', 'eval', 'inject', 'sample', 'score', 'train']
selfcheck: 31 python files, 5 problems
rc=1
```

**checks-blind:SC-8** — a `versions` entry holding two templates, on the real tree:
```
run._resolve_versions_entry('models/{family}_{backbone}.py') -> ['models/gptoss_qwen.py']
run._resolve_versions_entry('data/environments/{env}.py')    -> ['data/environments/appworld.py']
len(run._stage_table_files()) -> 22
```

**checks-blind:SC-2 + checks-fire:W6-L15-02** — the run from `/tmp` above, which
before the fix ended in `FileNotFoundError: [Errno 2] No such file or directory:
'agent/injected_text_formats.py'`.

**checks-fire:W6-L15-04 + runpy-regression:W6-L15-4** — `def broken(:` appended to
`eval/score_run.py`; no traceback, every check runs, the summary prints:
```
check 2: eval/score_run.py: does not parse (invalid syntax, line 267)
check 2: data/environments/__init__.py used by: README names [...'eval/score_run.py'...], the graph gives [...]
check 2: data/trajectory_record.py used by: README names [...], the graph gives [...]
check 2: experimental_settings/schema.py used by: README names [...], the graph gives [...]
check 2: jobs/registry.py used by: README names [...], the graph gives [...]
check 4: eval/score_run.py: does not parse (invalid syntax, line 267)
check 9: eval/score_run.py: does not parse (invalid syntax, line 267)
check 10: eval/score_run.py: import under .../external/appworld/venv/bin/python failed: SyntaxError: invalid syntax
check 10: eval/score_run.py: import under .../external/probe-env/bin/python failed: SyntaxError: invalid syntax
check 10: eval/score_run.py: import under .../external/vllm-env/bin/python failed: SyntaxError: invalid syntax
selfcheck: 31 python files, 10 problems
rc=1
```
The four graph lines are the consequence of the unreadable file: its edges are gone
from the import graph, and the files it imported say so.

**checks-fire:W6-L15-05** — a second column-zero `VERSION` in
`data/training_data.py`, and a `VERSION_HISTORY` rewritten as `dict({...})` in
`models/probe_models/base.py`, one prefix and one pair of quotes each:
```
check 4: data/training_data.py: 2 column-zero assignments to 'VERSION', expected exactly one
check 4: models/probe_models/base.py: 'VERSION_HISTORY' has a value that is not a literal (malformed node or string on line 27: <ast.Call object at 0x7fd6aa1ecdc0>)
```

**checks-blind:SC-3** — both loaders retargeted to `importlib.import_module("os")`:
```
check 2: data/environments/appworld.py used by: by-name entry data/environments/__init__.py holds no importlib.import_module call naming data.environments.<module>
check 2: models/agent_models/gptoss.py used by: by-name entry models/__init__.py holds no importlib.import_module call naming models.agent_models.<module>
selfcheck: 31 python files, 2 problems
rc=1
```
The third edge, `models/probe_models/base.py`, now fails on both its lines:
```
check 2: models/probe_models/base.py: no importlib.import_module f-string call beginning 'models.probe_models.' for its by-name import of models/probe_models/<backbone>.py
check 2: models/probe_models/qwen.py used by: by-name entry models/probe_models/base.py holds no importlib.import_module call naming models.probe_models.<module>
```

**checks-blind:SC-6** — `data/deleted_module.py` added to an `imports:` line and
`train/methods/gone.py` to a `used by:` line:
```
check 2: data/probe_output.py imports: names data/deleted_module.py, which is not a repo file
check 2: data/training_data.py imports: names data/deleted_module.py, which is not a repo file
check 2: data/training_data.py used by: names train/methods/gone.py, which is not a repo file
selfcheck: 31 python files, 3 problems
rc=1
```
(The same `imports:` text appears in two entries, so both report it.)

**checks-blind:SC-4** — `import definitely_not_a_module` added to
`data/environments/appworld.py`, then its `venv:` line deleted, then the same line
misspelled `nay at import ...`:
```
check 1: README entry 'data/environments/appworld.py' carries no venv: line (contracts 0.1's five-line format)
selfcheck: 31 python files, 1 problems
rc=1

check 10: data/environments/appworld.py: venv: 'nay at import and for the call-syntax methods; appworld to hold a world' names no interpreter: expected 'any', one of ['appworld', 'probe', 'vllm'], or "the environment's"
selfcheck: 31 python files, 1 problems
rc=1
```

**checks-blind:SC-9** — `AXES`'s `inject.format` key renamed to `inject.fmt` in
`experimental_settings/schema.py`:
```
check 3 raised: KeyError: 'inject.format'
selfcheck: 31 python files, 1 problems
```
The summary line proves checks 4 to 11 still ran.

**runpy-regression:W6-L15-2** — the three input classes of check 7:
```
EFFORTS ('high','medium','low'), DEFAULT_EFFORT None:
  check 7: models/agent_models/gptoss.py: DEFAULT_EFFORT None is not in EFFORTS ('high', 'medium', 'low')
EFFORTS (), DEFAULT_EFFORT None (the legal spelling):
  no check 7 line (the one problem printed is check 3's, that AXES['generation.effort'] is not within the family's now-empty EFFORTS)
EFFORTS None:
  check 7: models/agent_models/gptoss.py: EFFORTS None is not a tuple (contracts 6.2)
```

**runpy-regression:W6-L15-3** — the grep above prints `NO_ABS_PATH`.

**pipeline-review-skills:W6-L15-2** — recipe 2 followed literally in a scratch copy
(new `train/methods/cseq.py` with `VERSION`, `VERSION_HISTORY` under the pinned
rule block, `PROBE_KIND` and `CHECKPOINT_META`; `cseq` on `AXES['probe.method']`;
`PROBE_KIND`, `MATCH_VERSION` and `match_cseq` in `eval/utils/probe_eval.py`; the
new file's five annotation lines in README section 2; `cseq` added inside both
brace lists):
```
selfcheck: 32 python files, 0 problems
rc=0
```

## D4 regression: all eleven checks still fire

Each breakage is ticket 15's own D4 list, applied to a fresh scratch copy:

| # | breakage | the line selfcheck printed |
|---|---|---|
| 1 | `eval/score_run.py`'s README entry deleted | `check 1: eval/score_run.py is a .py file in the tree with no README entry` |
| 2 | `import jobs.registry` added to `models/probe_models/base.py` | `check 2: models/probe_models/base.py imports: README names ['models/__init__.py'], the graph gives ['jobs/registry.py', 'models/__init__.py']` |
| 3 | a sixth `FORMATS` key | `check 3: schema.AXES['inject.format'] (...) != agent/injected_text_formats.py FORMATS keys ('p3_e9', 'note', ...)` |
| 4 | a second column-zero `VERSION` in `data/training_data.py` | `check 4: data/training_data.py: 2 column-zero assignments to 'VERSION', expected exactly one` |
| 5 | a name in `data/probe_output.py`'s `REQUIRED` that `SCHEMA` lacks | `check 5: data/probe_output.py: REQUIRED names ['no_such_column'], which SCHEMA does not declare` |
| 6 | `PROBE_KIND["cgen"]` changed to `"classifier"` | `check 6: train/methods/cgen.py's PROBE_KIND 'generator' != eval/utils/probe_eval.py PROBE_KIND['cgen'] 'classifier'` |
| 7 | `DEFAULT_EFFORT = "ultra"` | `check 7: models/agent_models/gptoss.py: DEFAULT_EFFORT 'ultra' is not in EFFORTS ('high', 'medium', 'low')` |
| 8 | one alias block dropped from `constants/path_models.yaml` | `check 8: models/table.yaml['qwen3_0pt6b']: result.weights 'qwen3-0.6b-base' is not an alias of constants/path_models.yaml` |
| 9 | a literal `/net/...` path in `eval/score_run.py` | `check 9: eval/score_run.py: a string literal names an absolute path outside constants/: '/net/tokyo100-10g/data/str01_01/y-guo/x'` |
| 10 | `import torch` at module level in `eval/utils/probe_eval.py` | `check 10: eval/utils/probe_eval.py: import under .../external/appworld/venv/bin/python failed: ModuleNotFoundError: No module named 'torch'` |
| 11 | `touch experimental_settings/free.yaml` | `check 11: experimental_settings/free.yaml: stem 'free' is a reserved subcommand name` |

Every one exits 1. Each scratch copy was deleted after its run, and the whole
scratch directory at the end.

## One thing for the owner

`README.md` section 2's `tests/` sentence names the run command for
`tests/test_registry_concurrent_append.py` only, and `tests/test_packed_loss.py`
needs the repo root on `PYTHONPATH` because it imports `data.training_data`. No
finding covers it and no check reads that sentence, so nothing was changed there.

# Fix round 1

Head `a40659b`, on top of `3d199b1`. Same worktree, same two files (`run.py` and
`README.md`); `tests/` untouched. All four re-review findings are fixed, none is
declined.

| commit | what it fixes | findings |
|---|---|---|
| `647d759` | check 2's by-name test derives (importer, imported) from the label, and the check's `unreadable` set guards every reader in it | rr1-selfcheck-03, rr1-selfcheck-04 |
| `a40659b` | check 1's header comment and README section 3's preamble say what the checks actually do | rr1-selfcheck-01, rr1-selfcheck-02 |

## rr1-selfcheck-03 — the by-name direction

`_check_by_name_fragments`'s non-placeholder branch tested one direction whatever the
label: it parsed `path_text` as the importer and derived the prefix from
`current_file`. That is the `used by:` direction. On an `imports:` line the annotated
file is the importer and the fragment is the module it names, which the placeholder
branch two lines above already had right.

The branch now picks `(importer, imported)` from the label once, derives the prefix
from `imported`, parses `importer`, and words the message after the direction it
tested: the `used by:` message is the one this branch already printed, and the
`imports:` message names the annotated file as the reader and the fragment at the end.

Proved in a scratch copy of `a40659b`, with `data/environments/__init__.py`'s
`imports:` line rewritten to the truthful
`imports: data/environments/appworld.py (by name, inside open_env); [importlib, PyYAML]`.
The same annotation at `3d199b1` printed
`check 2: data/environments/__init__.py imports: by-name entry data/environments/appworld.py holds no importlib.import_module call naming data.environments.<module>`.
Now:
```
== rr1-selfcheck-03, truthful annotation, at branch head ==
selfcheck: 31 python files, 0 problems
rc=0
```
and with the loader in that file retargeted to `importlib.import_module("os")`, both
directions fire, each naming the file it read:
```
check 2: data/environments/__init__.py imports: data/environments/__init__.py holds no importlib.import_module call naming data.environments.<module> for by-name entry data/environments/appworld.py
check 2: data/environments/appworld.py used by: by-name entry data/environments/__init__.py holds no importlib.import_module call naming data.environments.<module>
selfcheck: 31 python files, 2 problems
rc=1
```
The placeholder arm still fires as well: with
`models/probe_models/base.py`'s `import_module` retargeted to `"os"`,
```
check 2: models/probe_models/base.py: no importlib.import_module f-string call beginning 'models.probe_models.' for its by-name import of models/probe_models/<backbone>.py
check 2: models/probe_models/qwen.py used by: by-name entry models/probe_models/base.py holds no importlib.import_module call naming models.probe_models.<module>
```

## rr1-selfcheck-04 — one parse-failure line per file per check

`_check_2` recorded an unparsable file in `unreadable` and skipped its own annotation
iteration, but `_check_by_name_fragments`, reached from another file's `used by:`
line, re-parsed it and appended the same message a second time. The set now travels
into `_check_by_name_fragments`, which passes over a fragment whose importer sits in
it, because that file's own line is already among the problems.

Proved in a scratch copy of `a40659b` with `def broken(:` appended to
`models/probe_models/base.py`, which `models/probe_models/qwen.py`'s `used by:` line
names by name. At `3d199b1` this printed the `check 2` parse line twice and
`5 problems`. Now:
```
check 2: models/probe_models/base.py: does not parse (invalid syntax, line 254)
check 2: models/__init__.py used by: README names [... 'models/probe_models/base.py' ...], the graph gives [...]
check 4: models/probe_models/base.py: does not parse (invalid syntax, line 254)
check 9: models/probe_models/base.py: does not parse (invalid syntax, line 254)
selfcheck: 31 python files, 4 problems
rc=1
```

## rr1-selfcheck-01 — check 1's header comment

The comment said the checks that read the five labels "lose the file silently when
its line is gone", naming check 2 among them. Check 2 reports a missing `imports:` or
`used by:` line by name itself. The comment now gives the real reason for each label:
check 10 is the silent reader, check 2 is a second source rather than the only one,
and `reads:` / `writes:`, which no check reads, are required because a line nobody
requires rots. The code is unchanged.

Both halves of the new comment, on scratch copies of `a40659b`. Deleting only
`eval/score_run.py`'s `imports:` line:
```
check 1: README entry 'eval/score_run.py' carries no imports: line (contracts 0.1's five-line format)
check 2: eval/score_run.py has no imports: line
selfcheck: 31 python files, 2 problems
rc=1
```
Deleting `data/environments/appworld.py`'s `venv:` line with
`import definitely_not_a_module` at the top of that file — check 10 says nothing:
```
check 1: README entry 'data/environments/appworld.py' carries no venv: line (contracts 0.1's five-line format)
selfcheck: 31 python files, 1 problems
rc=1
```

## rr1-selfcheck-02 — README section 3's preamble

The preamble put the brace-list spelling inside the sentence about what selfcheck
compares. `_split_top_level` splits an annotation line on its top-level commas and
`_expand_braces` runs per fragment, so a brace list and a separate fragment give the
same set. The paragraph now names the import-graph comparison as the check and the
brace list as the house spelling that selfcheck reads either way.

Proved on a scratch copy of `a40659b` by splitting `cparam` out of both brace lists
(README lines 250 and 280):
```
  used by: train/methods/{ctool,cgen}.py, train/methods/cparam.py
  used by: train/methods/{ctool,cgen}.py (match_<method>, for their validation metric), train/methods/cparam.py (match_cparam), run.py (read_report, to freeze a temperature), eval/method_table.py
== both brace-list spellings, one fragment split off ==
selfcheck: 31 python files, 0 problems
rc=0
```

## Acceptance, real output at `a40659b`

### Selfcheck, from the worktree root and from another working directory

```
$ "$PR" run.py selfcheck; echo "rc=$?"
selfcheck: 31 python files, 0 problems
rc=0
$ cd /tmp && "$PR" /home/y-guo/reproduce/new1-wt/2026-09-20-wave6-fix-selfcheck/run.py selfcheck; echo "rc=$?"
selfcheck: 31 python files, 0 problems
rc=0
```

### Ticket 14's D3 grep over run.py

```
$ grep -n "/home/\|/net/" run.py && echo FOUND || echo NO_ABS_PATH
NO_ABS_PATH
```

### Ticket 15's D2

```
3
['data.training_data', 'os']
two matches -> refused: True | /tmp/tmppjesl586/bad.py: 2 column-zero assignments to 'VERSION', expected exactly one
```
with `from dataclasses import dataclass` in the fixture:
```
['dataclasses', 'os']
```
the two literal readers:
```
['note', 'p1_e1', 'p1_e2', 'p2_e1', 'p2_e2']
literal_of refuses FORMATS: SystemExit agent/injected_text_formats.py: 'FORMATS' has a value that is not a literal (malformed node or string on line 65: <ast.Call object at 0x7fe7a5517130>)
```
the four annotation lines:
```
train/utils/trainer.py used by : ['train/methods/cgen.py', 'train/methods/cparam.py', 'train/methods/ctool.py'] | by name: [] | dead: []
models/agent_models/service.py used by : ['agent/run_tasks.py', 'agent/step_without_probe.py'] | by name: [] | dead: []
models/probe_models/base.py imports : ['models/__init__.py'] | by name: [('models/probe_models/<backbone>.py', 'by name, inside load()')] | dead: []
models/probe_models/__init__.py used by, package marker ok: True True
```
check 5's structural read and check 4's expansion:
```
data/trajectory_record.py {'SCHEMA': 1, 'DEFAULTS': 1, 'REQUIRED': 1} 12 []
data/training_data.py {'SCHEMA': 1, 'DEFAULTS': 1, 'REQUIRED': 1} 16 []
data/probe_output.py {'SCHEMA': 1, 'DEFAULTS': 1, 'REQUIRED': 1} 9 []
22 missing: []
```

### D5

```
usage: run.py <workflow> <setting> [<setting> ...] [--debug] [--allow-dirty] [section.field=value ...]
...
subcommands:
  ls          [workflow] [--debug] -- one folded line per run
  where       <workflow> <setting> <stage> [--debug] -- the absolute run directory for one stage
  find        section.field=value ... -- the runs whose settings_diff matches every given field
  kill        <workflow> <setting> <stage> -- end one run's pieces, write the killed finish row
  refire      <workflow> <setting> <stage> [--piece i] [--allow-dirty] -- restart one dead piece
  retry       <workflow> <setting> <stage> [--allow-dirty] -- clear markers, then launch it fresh
  table       [workflow] [--out FILE] [--debug] -- the backbone x method x risk table
  free        -- the free cards per host
  sync        -- fold done.json and heartbeats into missing finish rows
  selfcheck   -- the tree's self-consistency checks
rc=0
```

### D6

28 paths, then `D6 ok`, rc=0. The first and the last:
```
/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/sample/a7d8b62ee953
...
/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/debug/score/8f3279571a21
D6 ok
rc=0
```

### D7

```
baseline.yaml gpt_oss_120b_appworld real sample=a7d8b62ee953 score=87858c091092
baseline.yaml gpt_oss_120b_appworld debug sample=96de225de2b4 score=20eaad1deae5
train_probe.yaml ctool_qwen3_0pt6b real sample=a7d8b62ee953 build=6d3bf5aff879 train=d54f9e0199cc eval=834b3a696768
train_probe.yaml ctool_qwen3_0pt6b debug sample=96de225de2b4 build=b565f5ab1b94 train=22a0980de899 eval=61c95c5e5d9e
train_probe.yaml cgen_qwen3_0pt6b real sample=a7d8b62ee953 build=6d3bf5aff879 train=7d2b29f8d708 eval=a5fdf2e5cb9c
train_probe.yaml cgen_qwen3_0pt6b debug sample=96de225de2b4 build=b565f5ab1b94 train=f4b98907f380 eval=40707c4b0c02
train_probe.yaml cparam_qwen3_0pt6b real sample=a7d8b62ee953 build=6d3bf5aff879 train=cfd89ab5cb10 eval=fb41fe88a470
train_probe.yaml cparam_qwen3_0pt6b debug sample=96de225de2b4 build=b565f5ab1b94 train=4f98555bfe73 eval=feb38b81056f
inject.yaml probe_p1_e1_theta_0pt80 real inject=b4c915d20196 score=db3bb3816292
inject.yaml probe_p1_e1_theta_0pt80 debug inject=d6e2ebd3d7f4 score=93f2718f6e2a
inject.yaml no_probe_p1_e1_theta_0pt80 real inject=4143d5301a39 score=7520d278f25a
inject.yaml no_probe_p1_e1_theta_0pt80 debug inject=668b1716daf1 score=8f3279571a21
D7 ok
rc=0
```

### Tests

```
$ "$PR" -m unittest
Ran 0 tests in 0.000s
OK
rc=0
$ "$PR" tests/test_registry_concurrent_append.py
Ran 1 test in 0.204s
OK
$ PYTHONPATH=. "$PR" tests/test_packed_loss.py
Ran 3 tests in 2.680s
OK
```
`-m unittest` with no argument still discovers nothing, because `tests/` is not an
importable package; this round did not change that, and no finding covers it.

Every scratch copy was built with `git archive HEAD | tar -x` and the whole scratch
directory was deleted at the end of the round.

# Fix round 2

Head `f40d453`, on top of `a40659b`. Same worktree, same two files (`README.md` and
`run.py`); `tests/` untouched. Both re-review findings are fixed, neither is declined.

| commit | what it fixes | findings |
|---|---|---|
| `f31b269` | README section 3's preamble states check 2's package-marker obligation alongside the import-graph one | rr2-selfcheck-01 |
| `f40d453` | `_dynamic_import_prefix` gives a repo-root module the empty prefix, not `.` | rr2-selfcheck-02 |

## rr2-selfcheck-01 — the preamble named half of check 2

Confirmed as reported. The preamble stated the annotation work a new file costs as
the import-graph half of check 2 alone. `_check_package_marker` (`run.py:1025-1036`)
holds an `(as their package)` `used by:` line equal to the `.py` files of the
marker's own directory, and two such lines exist (`README.md:169` and
`README.md:190`). Recipes 6 and 7 add a file into one of those two directories and
that file imports no repo file, so the old sentence gave the extender nothing to do.

The preamble now names both obligations in one sentence, in the place where the
brace-list rule is already stated, rather than repeating itself in recipes 6 and 7:

> Every recipe that adds a file (1, 2, 6 and 7) also writes that file's own five
> annotation lines into section 2 above, and adds the new file's name to the
> `used by:` line of every repo file it imports. A new file that lands in a package
> directory whose `__init__.py` carries an `(as their package)` `used by:` line
> (`models/agent_models/` and `models/probe_models/` today) joins that list as well,
> because check 2 holds such a line equal to the `.py` files the directory holds.

Both recipes were then followed literally in scratch copies of the branch head
(baseline in the scratch base: `selfcheck: 31 python files, 0 problems`, rc=0).

Recipe 6, `models/probe_models/qwen2.py` (column-zero `LORA_TARGETS`) plus its five
annotation lines and nothing else — the finding's own experiment, reproduced:
```
check 2: models/probe_models/__init__.py used by: package marker names ['models/probe_models/base.py', 'models/probe_models/qwen.py', 'models/probe_models/service.py'], directory models/probe_models holds ['models/probe_models/base.py', 'models/probe_models/qwen.py', 'models/probe_models/qwen2.py', 'models/probe_models/service.py']
selfcheck: 32 python files, 1 problems
rc=1
```
The same copy with the marker line widened, which is what the new sentence tells the
extender to do:
```
selfcheck: 32 python files, 0 problems
rc=0
```

Recipe 7, `models/agent_models/llama.py` (column-zero `STOP`, `EFFORTS`,
`DEFAULT_EFFORT`, `DEFAULT_DATE`) plus its five annotation lines and nothing else:
```
check 2: models/agent_models/__init__.py used by: package marker names ['models/agent_models/gptoss.py', 'models/agent_models/service.py'], directory models/agent_models holds ['models/agent_models/gptoss.py', 'models/agent_models/llama.py', 'models/agent_models/service.py']
selfcheck: 32 python files, 1 problems
rc=1
```
With the marker line widened:
```
selfcheck: 32 python files, 0 problems
rc=0
```

## rr2-selfcheck-02 — the prefix of a repo-root module

Confirmed as reported. `".".join(Path("run.py").parent.parts) + "."` is `"."`, so the
f-string arm of `_has_dynamic_import_of` demanded a leading constant beginning with a
dot. The helper now reads the package part off the module's own dotted name:

```python
parts = Path(annotated_file).parent.parts
return ".".join(parts) + "." if parts else ""
```

Today's three prefixes are unchanged:
```
'' 'models.agent_models.' 'data.environments.' 'models.probe_models.'
```
(the four calls are `run.py`, `models/agent_models/gptoss.py`,
`data/environments/appworld.py`, `models/probe_models/qwen.py`).

The finding is latent on today's tree, so the breakage was reproduced by making a
root-level module by-name imported. In two scratch copies, `run.py`'s `used by:` line
reads `eval/method_table.py (by name, inside the table subcommand)` and
`eval/method_table.py` gains a correct dynamic import of it,
`importlib.import_module(f"run{suffix}")` inside a function. One copy carries the
pre-fix line of the helper, the other the branch head:
```
== rr2-selfcheck-02, before the fix (prefix '.') ==
prefix for run.py -> '.'
check 2: run.py used by: by-name entry eval/method_table.py holds no importlib.import_module call naming .<module>
selfcheck: 31 python files, 1 problems
rc=1
== rr2-selfcheck-02, after the fix (prefix '') ==
prefix for run.py -> ''
selfcheck: 31 python files, 0 problems
rc=0
```
The check still bites after the fix: the same annotation with the call retargeted to
`importlib.import_module("os")` fires, and the message's tail now reads `<module>`:
```
check 2: run.py used by: by-name entry eval/method_table.py holds no importlib.import_module call naming <module>
selfcheck: 31 python files, 1 problems
rc=1
```
One property of a root-level target is worth stating plainly, because the fix does
not change it: with an empty prefix every `import_module` f-string passes the
f-string arm, since ast sees only that the call names some top-level module. The
plain-string spelling is still tested exactly, which is what the experiment above
shows. A dotted prefix is what makes the test bite, and a root-level module has none.

## Acceptance, real output at `f40d453`

### Selfcheck, from the worktree root and from another working directory

```
$ "$PR" run.py selfcheck; echo "rc=$?"
selfcheck: 31 python files, 0 problems
rc=0
$ cd /tmp && "$PR" /home/y-guo/reproduce/new1-wt/2026-09-20-wave6-fix-selfcheck/run.py selfcheck; echo "rc=$?"
selfcheck: 31 python files, 0 problems
rc=0
```

### Ticket 14's D3 grep over run.py

```
$ grep -n "/home/\|/net/" run.py && echo FOUND || echo NO_ABS_PATH
NO_ABS_PATH
```

### Ticket 15's D2

```
3
['data.training_data', 'os']
two matches -> refused: True | /tmp/tmp8blq49ai/bad.py: 2 column-zero assignments to 'VERSION', expected exactly one
```
with `from dataclasses import dataclass` in the fixture:
```
['dataclasses', 'os']
```
the two literal readers:
```
['note', 'p1_e1', 'p1_e2', 'p2_e1', 'p2_e2']
literal_of refuses FORMATS: SystemExit agent/injected_text_formats.py: 'FORMATS' has a value that is not a literal (malformed node or string on line 65: <ast.Call object at 0x7f0fa601b130>)
```
the four annotation lines:
```
train/utils/trainer.py used by : ['train/methods/cgen.py', 'train/methods/cparam.py', 'train/methods/ctool.py'] | by name: [] | dead: []
models/agent_models/service.py used by : ['agent/run_tasks.py', 'agent/step_without_probe.py'] | by name: [] | dead: []
models/probe_models/base.py imports : ['models/__init__.py'] | by name: [('models/probe_models/<backbone>.py', 'by name, inside load()')] | dead: []
models/probe_models/__init__.py used by, package marker ok: True True
```
check 5's structural read and check 4's expansion:
```
data/trajectory_record.py {'SCHEMA': 1, 'DEFAULTS': 1, 'REQUIRED': 1} 12 []
data/training_data.py {'SCHEMA': 1, 'DEFAULTS': 1, 'REQUIRED': 1} 16 []
data/probe_output.py {'SCHEMA': 1, 'DEFAULTS': 1, 'REQUIRED': 1} 9 []
22 missing: []
run._stage_table_files(): 22
```

### D5

```
usage: run.py <workflow> <setting> [<setting> ...] [--debug] [--allow-dirty] [section.field=value ...]

The first word is one of the ten reserved subcommands below, or else the stem of a
workflow file under experimental_settings/.

subcommands:
  ls          [workflow] [--debug] -- one folded line per run
  where       <workflow> <setting> <stage> [--debug] -- the absolute run directory for one stage
  find        section.field=value ... -- the runs whose settings_diff matches every given field
  kill        <workflow> <setting> <stage> -- end one run's pieces, write the killed finish row
  refire      <workflow> <setting> <stage> [--piece i] [--allow-dirty] -- restart one dead piece
  retry       <workflow> <setting> <stage> [--allow-dirty] -- clear markers, then launch it fresh
  table       [workflow] [--out FILE] [--debug] -- the backbone x method x risk table
  free        -- the free cards per host
  sync        -- fold done.json and heartbeats into missing finish rows
  selfcheck   -- the tree's self-consistency checks
rc=0
```

### D6

28 paths, then `D6 ok`, exit 0. The first and the last:
```
/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/sample/a7d8b62ee953
...
/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/debug/score/8f3279571a21
D6 ok
```

### D7

```
baseline.yaml gpt_oss_120b_appworld real sample=a7d8b62ee953 score=87858c091092
baseline.yaml gpt_oss_120b_appworld debug sample=96de225de2b4 score=20eaad1deae5
train_probe.yaml ctool_qwen3_0pt6b real sample=a7d8b62ee953 build=6d3bf5aff879 train=d54f9e0199cc eval=834b3a696768
train_probe.yaml ctool_qwen3_0pt6b debug sample=96de225de2b4 build=b565f5ab1b94 train=22a0980de899 eval=61c95c5e5d9e
train_probe.yaml cgen_qwen3_0pt6b real sample=a7d8b62ee953 build=6d3bf5aff879 train=7d2b29f8d708 eval=a5fdf2e5cb9c
train_probe.yaml cgen_qwen3_0pt6b debug sample=96de225de2b4 build=b565f5ab1b94 train=f4b98907f380 eval=40707c4b0c02
train_probe.yaml cparam_qwen3_0pt6b real sample=a7d8b62ee953 build=6d3bf5aff879 train=cfd89ab5cb10 eval=fb41fe88a470
train_probe.yaml cparam_qwen3_0pt6b debug sample=96de225de2b4 build=b565f5ab1b94 train=4f98555bfe73 eval=feb38b81056f
inject.yaml probe_p1_e1_theta_0pt80 real inject=b4c915d20196 score=db3bb3816292
inject.yaml probe_p1_e1_theta_0pt80 debug inject=d6e2ebd3d7f4 score=93f2718f6e2a
inject.yaml no_probe_p1_e1_theta_0pt80 real inject=4143d5301a39 score=7520d278f25a
inject.yaml no_probe_p1_e1_theta_0pt80 debug inject=668b1716daf1 score=8f3279571a21
D7 ok
rc=0
```

### Tests

```
$ "$PR" -m unittest
Ran 0 tests in 0.000s
OK
rc=0
$ "$PR" tests/test_registry_concurrent_append.py
Ran 1 test in 0.203s
OK
rc=0
$ PYTHONPATH=. "$PR" tests/test_packed_loss.py
Ran 3 tests in 2.744s
OK
rc=0
```
`-m unittest` with no argument still discovers nothing, because `tests/` is not an
importable package; this round did not change that, and no finding covers it.

Every scratch copy of this round was built with `git archive HEAD | tar -x` plus the
round's two edited files, under
`/home/y-guo/.claude/jobs/46e92203/tmp/fix-selfcheck-scratch`, and the whole scratch
directory was deleted at the end of the round.

# Fix round 3

Head `5f455eb`, on top of `81df864`, on branch `fix/2026-09-20-wave6-r3` in the
worktree `/home/y-guo/reproduce/new1-wt/2026-09-20-wave6-fix-r3`. One file changed,
`run.py`; `README.md` and `tests/` untouched. The round's one selfcheck finding is
fixed, none is declined.

| commit | what it fixes | finding |
|---|---|---|
| `5f455eb` | a repo-root by-name target's f-string test takes the module's own dotted name as its required leading text | rr-selfcheck-03-empty-prefix-passes-any-fstring |

## rr-selfcheck-03 — the empty prefix passed any f-string

Confirmed as reported, and confirmed as the blind spot round 2 opened. Round 2 gave a
repo-root module the empty package prefix (`_dynamic_import_prefix`, `run.py:941-949`),
which is right for what that helper answers. The f-string arm of
`_has_dynamic_import_of` then tested `first.value.startswith(prefix)` (`run.py:972` at
`81df864`), and every string starts with the empty string, so for a root-level
`used by: ... (by name)` claim that arm passed any `importlib.import_module(f"...")`
call whose first piece is a string constant, whatever module it named. The plain-string
arm was never reached, because an f-string argument is an `ast.JoinedStr` and not an
`ast.Constant` (`run.py:978`).

The fix names the required leading text once, at the top of the helper, and the arm
tests against it (`run.py:963`, `run.py:976`):

```python
    lead = prefix or exact
```

A target inside a package keeps its non-empty package prefix, so nothing changes there.
A repo-root target takes `exact`, which the by-name call site already passes as
`_module_name(imported)` (`run.py:1030`) and which is `run` for `run.py`. The
placeholder call site (`run.py:1009`) passes no `exact` and a non-empty prefix, so it is
untouched. The helper's docstring now states which of the two the test uses and why.

### The defect reproduced, and the fix proved, on scratch copies

The copies were built with `git archive | tar -x` under
`/home/y-guo/.claude/jobs/46e92203/tmp/r3-scratch`, one from `81df864` and one from this
round's head, each carrying the same two fixture edits: `README.md:60` holds
`used by: eval/method_table.py (by name, inside the table subcommand)` in place of
`none (program)`, and `eval/method_table.py` holds a function returning
`importlib.import_module(f"<module>{suffix}")`.

The correct spelling, `f"run{suffix}"`, on this round's head — green, so the fix does not
cost a true by-name claim its pass:
```
$ "$PR" run.py selfcheck
selfcheck: 31 python files, 0 problems
rc=0
```

The wrong module named, `f"data.training_data{suffix}"`, while the annotation still
claims `run.py` is imported by name. At `81df864` this is the blind spot:
```
$ "$PR" run.py selfcheck
selfcheck: 31 python files, 0 problems
rc=0
```
On this round's head the same copy fires:
```
$ "$PR" run.py selfcheck
check 2: run.py used by: by-name entry eval/method_table.py holds no importlib.import_module call naming <module>
selfcheck: 31 python files, 1 problems
rc=1
```
The message's `{prefix}<module>` tail (`run.py:1033`) reads bare `<module>` for a
repo-root target. It was left as it is: the line already names `run.py` as the annotated
file, and this round's scope is the test, not the wording.

The whole scratch directory was deleted at the end of the round.

## Acceptance, real output at `5f455eb`

### Selfcheck, from the worktree root and from another working directory

```
$ cd /home/y-guo/reproduce/new1-wt/2026-09-20-wave6-fix-r3
$ "$PR" run.py selfcheck
selfcheck: 31 python files, 0 problems
rc=0
$ cd /tmp
$ "$PR" /home/y-guo/reproduce/new1-wt/2026-09-20-wave6-fix-r3/run.py selfcheck
selfcheck: 31 python files, 0 problems
rc=0
```

### Ticket 15's D2

The fixture parsers:
```
3
['data.training_data', 'os']
two matches -> refused: True
```
with `from dataclasses import dataclass` in the fixture:
```
['dataclasses', 'os']
```

The two literal readers:
```
['note', 'p1_e1', 'p1_e2', 'p2_e1', 'p2_e2']
literal_of refuses FORMATS: SystemExit agent/injected_text_formats.py: 'FORMATS' has a value that is not a literal (malformed node or string on line 65: <ast.Call object at 0x7f8e54143130>)
```

The annotation-line parse, printed with check 2's own helper, `run._parse_annotation`,
as `(normal, by_name, dead)`:
```
train/utils/trainer.py | used by
   normal:    ['train/methods/cgen.py', 'train/methods/cparam.py', 'train/methods/ctool.py']
   by_name:   []
   dead:      []
models/agent_models/service.py | used by
   normal:    ['agent/run_tasks.py', 'agent/step_without_probe.py']
   by_name:   []
   dead:      []
models/probe_models/base.py | imports
   normal:    ['models/__init__.py']
   by_name:   [('models/probe_models/<backbone>.py', 'by name, inside load()')]
   dead:      []
models/probe_models/__init__.py | used by
   normal:    ['models/probe_models/base.py', 'models/probe_models/qwen.py', 'models/probe_models/service.py']
   by_name:   []
   dead:      []
```

Check 5's structural read:
```
data/trajectory_record.py {'SCHEMA': 1, 'DEFAULTS': 1, 'REQUIRED': 1} 12 []
data/training_data.py {'SCHEMA': 1, 'DEFAULTS': 1, 'REQUIRED': 1} 16 []
data/probe_output.py {'SCHEMA': 1, 'DEFAULTS': 1, 'REQUIRED': 1} 9 []
```

Check 4's expansion:
```
22 missing: []
```

### D5

```
$ "$PR" run.py --help
usage: run.py <workflow> <setting> [<setting> ...] [--debug] [--allow-dirty] [section.field=value ...]

The first word is one of the ten reserved subcommands below, or else the stem of a
workflow file under experimental_settings/.

subcommands:
  ls          [workflow] [--debug] -- one folded line per run
  where       <workflow> <setting> <stage> [--debug] -- the absolute run directory for one stage
  find        section.field=value ... -- the runs whose settings_diff matches every given field
  kill        <workflow> <setting> <stage> -- end one run's pieces, write the killed finish row
  refire      <workflow> <setting> <stage> [--piece i] [--allow-dirty] -- restart one dead piece
  retry       <workflow> <setting> <stage> [--allow-dirty] -- clear markers, then launch it fresh
  table       [workflow] [--out FILE] [--debug] -- the backbone x method x risk table
  free        -- the free cards per host
  sync        -- fold done.json and heartbeats into missing finish rows
  selfcheck   -- the tree's self-consistency checks
rc=0
```

### Tests

Each test module in its own process, never both in one:
```
$ "$PR" tests/test_registry_concurrent_append.py
Ran 1 test in 0.211s
OK
rc=0
$ PYTHONPATH=. "$PR" tests/test_packed_loss.py
Ran 3 tests in 2.666s
OK
rc=0
```
