# 15 run.py selfcheck

Status: claimed
Blocked by: 13, 14
Spec: .scratch/from-zero/spec.md (sections 1, 2, 3, 4, 5, 7)

## What to do

Two files, edited: `run.py` and `README.md`. Add the `selfcheck` subcommand (replacing ticket 14's
one-line stub) and the three parsers it needs beside `readme_entries`, which ticket
14 already wrote. Contracts 8.6 (the subcommand and its check list), 0.1 (the
annotation format and what `selfcheck` proves), 3.3 (the literal rule), 2.6 (the
`PROBE_KIND` pair) and Part 1 (`DEFAULTS` / `REQUIRED`) are the specification.

```
run.py       venv: probe    the only file this ticket may touch, besides README.md
README.md    the six lines named below, and no others — list them in your report
```

By this wave every one of the 31 Python files is on the branch, so **a green
`selfcheck` is the deliverable**, not an aspiration.

**Six README lines are already wrong, and correcting them is the whole of the
README licence above.** Correct these six and no others, and list them in your
report. Each correction replaces one line in place, so no line number below moves.
The import sets were measured with `ast` over the tree at this ticket's HEAD.

| README line | entry and label | what is wrong | the corrected line |
|---|---|---|---|
| 129 | `data/training_data.py` `used by:` | it names `train/methods/{ctool,cgen,cparam}.py (their target column)`, and none of the three imports this module — they reach it through `train/utils/trainer.py` | `  used by: data/build_training_dataset.py (write), train/utils/trainer.py (read)` |
| 197 | `models/probe_models/base.py` `used by:` | the same three method files, the same reason | `  used by: train/utils/trainer.py, models/probe_models/service.py (inside serve())` |
| 210 | `models/probe_models/service.py` `imports:` | it writes the qualifier bare, `models/probe_models/base.py inside serve()`, so no strip rule removes it although the `ast` edge is real (`models/probe_models/service.py:88`, `from models.probe_models import base` inside `serve()`) | the same line with `models/probe_models/base.py (inside serve())` |
| 256 | `train/methods/ctool.py` `imports:` | it names `models/probe_models/base.py` and `data/training_data.py`; this file imports only `train/utils/trainer.py` and `eval/utils/probe_eval.py` | the same line with those two entries removed |
| 263 | `train/methods/cgen.py` `imports:` | the same two entries; this file imports only `train/utils/trainer.py`, `data/environments/__init__.py` and `eval/utils/probe_eval.py` | the same line with those two entries removed |
| 270 | `train/methods/cparam.py` `imports:` | the same two entries, the same three real imports | the same line with those two entries removed |

Contracts 0.2 carries these lines as they stand today (contracts line 272 for
README.md:129, line 366 for :197, and lines 480, 487 and 495 for :256, :263 and
:270); `notes/` was not rewritten after the `eval/methods/` fold
(errata entry `0.2 / 2.1 / 2.6`), so the tree on disk decides here. The contracts-0.2
argument in rule 3 below applies only to the two `(as their package)` lines it names.

Do not "fix" check 2 by following transitive imports: `imports_of` is the file's own
`ast` imports and nothing else. These six lines are the only annotation lines in the
README that disagree with the graph. A prototype of check 2 built to the rules below
reports exactly these six problems before the edits and zero after them.

### The parsers

```python
def readme_entries(path) -> dict[str, dict[str, str]]   # ticket 14 wrote this; reuse it
def imports_of(path) -> set[str]                        # ast over the file, never an import
def literal_of(path, name)                              # the one column-zero assignment
def literal_keys_of(path, name) -> list                 # that assignment's ast.Dict keys only
```

`imports_of` parses the file with `ast` and returns the dotted module names of
every `Import` and `ImportFrom`, **including the ones inside functions** — a
heavy import moved inside `serve()` is still an import of that module and the
annotation line must carry it. `literal_of` returns
`ast.literal_eval` of the **one column-zero** assignment to `name`; more than one
match, zero matches, and a value `ast.literal_eval` refuses are all failures; each
names the file, the name and which of the three it is, and each is reported as one
problem line like every other check, never as an escaping traceback.

**`literal_of` stays strict.** The whole content of check 4 is that a value parses
as a literal, so a fallback inside `literal_of` would stop check 4 firing. Two kinds
of value in the tree are not literals, and each is read its own way:

- `agent/injected_text_formats.py`'s `FORMATS` is a dict of `Format(...)`
  constructor calls, which `ast.literal_eval` refuses. The errata records this
  state and leaves it unchanged (`.scratch/from-zero/contract-errata.md`, the entry
  `3.3 / 8.6 (the ruling entry above, "what a VERSION bump invalidates")`, last
  sentence, "Pre-existing, reported and unchanged"), and that file is outside this
  ticket's two editable files, so check 3 reads it with `literal_keys_of`.
  `literal_keys_of` finds the same one column-zero assignment `literal_of` finds,
  requires its value to be an `ast.Dict`, and `ast.literal_eval`s each key. It
  fails, naming the file and the name, when the assignment is missing, is matched
  more than once, is not a dict display, or carries a key that is not a literal.
  **Check 3 uses it for `FORMATS` and for nothing else**; every other name in
  checks 3 and 4 goes through `literal_of` unchanged, so check 4's "one literal
  apiece" keeps its meaning. Contracts 5.3 words the same read as "`FORMATS`' keys,
  parsed with `ast`".
- `SCHEMA`, `DEFAULTS` and `REQUIRED` in the three `data/` format files are
  annotated assignments whose values are a `polars` dtype dict, a dict
  comprehension and a `frozenset(...)` call. Check 5 reads them off the `ast` nodes
  and uses neither `literal_of` nor `literal_keys_of`. See check 5.

`literal_of` and `literal_keys_of` match `ast.Assign` only. Every name they are
asked for is a plain `ast.Assign` in this tree — `VERSION`, `VERSION_HISTORY`,
`PROBE_KIND`, `MATCH_VERSION`, `STOP`, `EFFORTS`, `DEFAULT_EFFORT`, `DEFAULT_DATE`,
`LORA_TARGETS`, `CHECKPOINT_META`, `INSTRUCTIONS`, `SPLIT_ROLE`, `ARMS`, `FORMATS`
— so `experimental_settings/schema.py`'s `_column_zero_matches` is the right shape
to copy for them. It is the wrong shape for check 5's three names, which are
`ast.AnnAssign`: a reader that tests `ast.Assign` alone reports nine spurious
"zero matches" problems there.

**Three normalisation rules the checks below depend on**, stated here because
without them check 2 can never be green:

1. **`imports_of` joins `module.name` for an `ImportFrom` only when the join is a
   repo file.** `from data import training_data` yields `data.training_data` because
   `data/training_data.py` exists; `from dataclasses import dataclass` yields
   `dataclasses`, because neither `dataclasses/dataclass.py` nor
   `dataclasses/dataclass/__init__.py` is in this repo. Without the rule a
   `from <package> import <module>` import of a repo file is invisible to the
   graph, and every `data/` and `models/` annotation line disagrees with it.
2. **Check 2 parses an annotation line in five steps, in this order.**
   `readme_entries` returns the label's raw value string unchanged — the one ticket
   14 wrote does no splitting at all — so the parsing is check 2's own. Do not
   change `readme_entries`: ticket 14's `D1` calls it as it is, and ticket 16's
   skills tell future writers to add the five annotation lines in the format it
   parses.

   1. Drop every bracketed third-party list: `[polars, numpy]`,
      `[http.server, transformers and torch inside serve()]`.
   2. Split what is left into fragments on every `,` and every `;` that is **not**
      inside brackets, parentheses or braces. Both separators carry real entries —
      `;` separates entries on README.md:196 and :210 — and both carry prose.
   3. In each fragment drop the parenthetical, everything from the first `(` on:
      `data/trajectory_record.py (done_pairs, is_done, owner, release)` becomes
      `data/trajectory_record.py`. Keep the parenthetical's first words: a fragment
      whose parenthetical starts `by name` is rule 3's by-name entry, whatever
      follows inside it (`(by name)` and `(by name, inside load())` are both it).
   4. Expand a brace alternation into one entry per alternative:
      `train/methods/{ctool,cgen,cparam}.py` is the three files
      `train/methods/ctool.py`, `train/methods/cgen.py`, `train/methods/cparam.py`.
      README.md:250 and :280 write this form, and :129 and :197 do until the six
      corrections above land; contracts 0.2 writes it the same way. The commas inside the braces never split a fragment, because
      step 2 splits at depth zero only.
   5. A fragment counts as an entry only when what is left is **exactly** a repo
      file path — after step 4, every expansion of it. Anything else is the
      reader's note and is dropped: the prose clauses on README.md:176, :183, :211,
      :241 and :295. **The whole fragment is tested, never its first word**:
      `jobs/launch.py starts it
      as a piece, which is a tmux command and not an import` begins with a real
      repo path, and keeping it as an entry makes check 2 fail on both service
      files forever, because `jobs/launch.py` names them only in a `-m` argv
      string and imports neither.

   What is compared is the set of repo file paths that survive step 5, nothing
   else. A bare `none` is not a path and is dropped here; rule 3 handles
   `none (program)`.
3. **An annotation entry that is not an `ast` edge is checked differently.** Spec
   section 3 gives two such spellings and contracts 0.2 a third; all three are
   legitimate, and the first of them appears on an `imports:` line as well as on a
   `used by:` line:
   - `<file> (by name)` — a dynamic import. `ast` cannot see
     `importlib.import_module(f"data.environments.{name}")`, so instead of the
     graph equality, check that the named file **exists** and that it holds the
     dynamic-import call — on a `used by:` line the named file is the importer, so
     it is the one that holds the call. The entry is asserted against the import
     target, not against the graph, and it is dropped from both sides of check 2's
     equality. The 31 Python files the README lists hold exactly three
     `importlib.import_module` calls —
     `data/environments/__init__.py:84`, `models/__init__.py:70` inside `agent()`,
     and `models/probe_models/base.py:198` inside `load()` — so the three files in
     this state today are `data/environments/appworld.py` (imported by name inside
     `data/environments/__init__.py`), `models/agent_models/gptoss.py` (imported by
     name inside `models.agent()`) and `models/probe_models/qwen.py` (imported by
     name inside `base.load()`). **`models.probe()` performs no import at all**; do
     not look for one there. `tests/test_packed_loss.py:127` holds a fourth such
     call; check 2 never walks `tests/`, so it is outside this count.

     One `imports:` entry is by name as well: `models/probe_models/base.py`'s
     `models/probe_models/<backbone>.py (by name, inside load())` (README.md:196).
     `<backbone>` is a placeholder, not a file, so rule 2 step 3 routes it here
     like every other by-name fragment, and unlike the three `used by:` by-name
     entries it names no file: the existence half does not apply to it and it is
     dropped from check 2's comparison. Its test is that
     `models/probe_models/base.py` holds an `importlib.import_module` call whose
     argument is an f-string beginning `models.probe_models.`. The existence half
     is already carried by `models/probe_models/qwen.py`'s
     `used by: models/probe_models/base.py (by name)` line (README.md:204).
   - `used by: none (program)` — a stage program nobody imports. Check that no
     repo file's `imports_of` names it, and that it has a `__main__` block.
   - `used by: <files> (as their package)` — an empty package marker. This
     parenthetical sits **once, at the end of the line**, and governs the whole
     list, so this rule is scoped to the line and not to an entry: **for such a
     line, drop check 2's equality for the whole line** and instead check that the
     set the line names **equals** the set of `.py` files in that marker's own
     directory other than `__init__.py`. Being inside a package is not an `ast`
     edge: `from models.probe_models import base` resolves under rule 1 to
     `models/probe_models/base.py`, and nothing imports `models.agent_models` at
     all, so the graph set of either marker is empty and the equality could never
     hold. The two files in this state are `models/agent_models/__init__.py`
     (README.md:169, naming `service.py` and `gptoss.py`) and
     `models/probe_models/__init__.py` (README.md:190, naming `base.py`,
     `service.py` and `qwen.py`). Contracts 0.2 carries both lines verbatim, so
     they are right and are not among the six lines this ticket corrects. Each
     marker's `imports:` half keeps the plain equality and still proves
     `imports: none` against an empty `imports_of`. A scope test rather than an
     equality would silently pass a marker that had stopped naming a new sibling.

   Every other `imports:` or `used by:` line keeps the plain equality of check 2.
   Check 2 never looks at the `reads:`, `writes:`, `read by:`, `offers:` or `venv:`
   line; only check 10 reads `venv:`.

**`selfcheck` never imports a repo module to inspect it.** The only place it
starts an interpreter is the per-interpreter import test at the end.

### The checks, in the contract's order (8.6)

1. The README's file list against the tree: every `.py` under `run.py`,
   `constants/`, `experimental_settings/`, `data/`, `models/`, `agent/`,
   `train/`, `eval/`, `jobs/` has an entry, and every entry names a path that
   exists. The count is **31**, and it counts the `.py` entries only:
   `readme_entries` returns 43 entries today, the 31 Python files plus `CLAUDE.md`,
   the three `constants/*.yaml`, the four `experimental_settings/*.yaml`,
   `models/table.yaml`, `jobs/runs.jsonl`, `jobs/RESULTS.md` and the directory entry
   `tests/` (README.md:322). All 43 are tested, and the test is **existence, not
   `is_file()`** — `tests/` is a directory and passes.
2. Every annotation line against the real import graph, parsed with `ast`: the
   `imports:` line equals `imports_of` restricted to repo files, and the
   `used by:` line equals the set of repo files whose `imports_of` names this one
   — **under the three normalisation rules above**, so an entry whose parenthetical
   starts `by name`, the literal `none (program)` and a line ending
   `(as their package)` take their own test instead of the equality. A line that
   disagrees is a failure naming both sides.
3. Every axis literal against the files behind it (5.3):
   `schema.AXES["inject.format"]` equals
   `tuple(literal_keys_of("agent/injected_text_formats.py", "FORMATS"))`: the string
   keys of the one column-zero `FORMATS` dict display, in the dict's own order, which
   is the axis's order. Take the `tuple(...)` literally — the axis is the tuple
   `("note", "p1_e1", "p1_e2", "p2_e1", "p2_e2")` and `literal_keys_of` returns a
   list, so comparing the two raw values is always False and check 3 would print a
   problem on an untouched tree. `literal_of` refuses that same value,
   whose entries are `Format(...)` calls, and this is the one place
   `literal_keys_of` is used; `schema.AXES["inject.arm"]` equals
   `agent/step_with_probe.py`'s `ARMS`;
   every axis value of `schema.AXES["probe.method"]` is a key of
   `eval/utils/probe_eval.py`'s `PROBE_KIND` and of its `MATCH_VERSION`, and the
   axis equals the file stems under `train/methods/`; `schema.AXES["data.env"]` equals the file
   stems under `data/environments/` minus `__init__`. The two stem comparisons are
   **set** comparisons — a directory has no order — while `inject.format` and
   `inject.arm` are ordered tuple comparisons, because a dict display and a tuple
   literal both carry the axis's order. Today `schema.AXES["probe.method"]` is
   `("ctool", "cgen", "cparam")` and the stems sort to `cgen, cparam, ctool`, so an
   ordered comparison there fails on an untouched tree.
   `schema.AXES["data.instructions"]` is within the union of every environment's
   `INSTRUCTIONS` keys; `sample.split` and `inject.split` are within the union of
   every environment's `SPLIT_ROLE` keys; `generation.effort` is within the union
   of every family module's `EFFORTS`.
4. One integer `VERSION` line at column zero per module the stage table's
   `versions` tuples name, and one literal apiece for `PROBE_KIND`, `STOP`,
   `EFFORTS`, `DEFAULT_EFFORT`, `DEFAULT_DATE`, `LORA_TARGETS`, `CHECKPOINT_META`,
   `INSTRUCTIONS` and `SPLIT_ROLE`.

   A `versions` entry is not always a plain path, so resolve it before opening
   anything. Do not call `schema._substitute` or `schema._entry_parts`: both are
   private, and `_substitute` needs a loaded `Setting`, which `selfcheck` does not
   have. The resolution is two steps.
   (a) Drop an entry's `@<stage>` tail and its `#<TABLE>.<name>` tail —
   `entry.split("@")[0].split("#")[0]` is the whole of it — because those name a
   stand-in stage and a table entry, not a file.
   (b) Expand the four templates: `{env}` over `schema.AXES["data.env"]`,
   `{method}` and `{probe_score_method}` over `schema.AXES["probe.method"]`,
   `{family}` over the `family` field of every `models/table.yaml` row whose `role`
   is `agent`, and `{backbone}` over the `family` field of every row whose `role`
   is `probe`. **The role split is not optional.** `gptoss` is the only agent
   family and `qwen` the only probe family, so expanding either template over all
   rows names `models/agent_models/qwen.py` and `models/probe_models/gptoss.py`,
   neither of which exists, and check 4 prints two problems of its own making.
   Resolved this way the six stage rows name exactly **22** files, and exactly
   those 22 carry a column-zero `VERSION` today; a set difference in either
   direction is a failure naming the files.
5. In each of the three format files the contracts define —
   `data/trajectory_record.py`, `data/training_data.py`, `data/probe_output.py`,
   and **not** `data/probe_input.py`, which declares none of these names, so a glob
   over `data/*.py` would fail this check on it — exactly one column-zero binding
   each of `SCHEMA`, `DEFAULTS` and `REQUIRED`, with **every name in `REQUIRED` a
   declared column of that file's `SCHEMA`** (Part 1).

   All nine bindings are **annotated** assignments (`ast.AnnAssign`), and none of
   the three values is a literal: `SCHEMA`'s values are `polars` dtype attributes
   and calls (`pl.Utf8`, `pl.List(pl.Float32)`), `DEFAULTS` is a dict comprehension
   over `SCHEMA`, `REQUIRED` is a `frozenset({...})` call. This check therefore
   reads the `ast` nodes directly and uses neither `literal_of` nor
   `literal_keys_of`:
   - a column-zero binding is an `ast.Assign` or an `ast.AnnAssign` at column zero
     whose target is the bare `ast.Name`. **Match on the target's `id`, never on
     `ast.unparse(target)`**: `data/trajectory_record.py:95` is
     `DEFAULTS["n_inject"] = 0`, a subscript target, and counting it would make
     that file fail the "exactly one" rule;
   - `SCHEMA`'s declared columns are the `ast.literal_eval` of its `ast.Dict`'s
     keys;
   - `REQUIRED`'s names are the `ast.literal_eval` of the single argument of its
     `frozenset(...)` call;
   - `DEFAULTS` is checked for its one column-zero binding only.

   Today that is 12, 16 and 9 required names, every one of them a `SCHEMA` column.
6. The two `PROBE_KIND` declarations of a method — `train/methods/<m>.py`'s
   literal and that method's entry in `eval/utils/probe_eval.py`'s `PROBE_KIND`
   table — are equal (2.6).
7. Every family module's `DEFAULT_EFFORT` is in its own `EFFORTS`, **or `EFFORTS`
   is the empty tuple and `DEFAULT_EFFORT` is `None`** — the state contracts 6.2
   gives a family with no reasoning tier, which 8.6 spells "or both empty". Do not
   write the alternative as `EFFORTS == () and DEFAULT_EFFORT == ""`: 6.2 types
   `DEFAULT_EFFORT` as `str | None` and prescribes `None` there. A family module
   here is `models/agent_models/<family>.py`; probe backbones carry `LORA_TARGETS`
   instead of this pair and are not tested. Today's one agent family,
   `models/agent_models/gptoss.py`, has `EFFORTS = ("high", "medium", "low")` and
   `DEFAULT_EFFORT = "high"`.
8. Every `models/table.yaml` row's `family` resolves to a file under
   `models/agent_models/` or `models/probe_models/` per its `role`, and its
   `result.weights` alias is present in `constants/path_models.yaml` (6.1).
9. No `/home/` or `/net/` path in code outside `constants/`.
10. Each file whose README `venv:` value **begins with** `any` — the plain `any`
    and the compound `any at import, <venv> to run` spellings alike (contracts
    0.1) — imports under **every** interpreter of
    `constants/path_datasets.yaml`'s `venvs:` map, and each family module imports
    under the probe **and** the vllm interpreter (0.4's precondition for a new
    family). A `venv == "any"` test would silently skip every compound spelling
    (today `data/environments/appworld.py`, `models/agent_models/gptoss.py`,
    `models/agent_models/service.py`, `models/probe_models/service.py`) and
    under-cover the check without failing it. 20 of the 31 files begin with `any`
    today, and all 20 import under all three interpreters. This is the one check
    that starts a subprocess.
11. A workflow file whose stem is one of the ten reserved subcommand names is
    refused, naming the file (errata).

Print **one line per problem** and exit 1 on any; on success print
`selfcheck: 31 python files, 0 problems` and exit 0. Shape ported from
`legacy/run.py:1172-1267` (count, one line per problem, exit 1 on any).

## Acceptance

Run from the repo root and paste the real output. `$PR` is
`/home/y-guo/reproduce/new1/external/probe-env/bin/python`.

**D2 — selfcheck's parsers, on fixtures the command writes.**
```bash
"$PR" -c "
import sys, pathlib, tempfile; sys.path.insert(0,'.')
import run
d = pathlib.Path(tempfile.mkdtemp()); f = d/'m.py'
f.write_text('VERSION = 3\nimport os\nfrom data import training_data\nclass A:\n    VERSION = VERSION\n')
print(run.literal_of(f, 'VERSION'))
print(sorted(run.imports_of(f)))
g = d/'bad.py'; g.write_text('VERSION = 1\nVERSION = 2\n')
try:
    print('two matches ->', run.literal_of(g, 'VERSION'))
except SystemExit as e:
    print('two matches -> refused:', 'bad.py' in str(e))"
```
Expected: `3`; `['data.training_data', 'os']`; then a refusal naming the file for the
two-match case (or a `None` plus a printed problem, whichever the implementation
uses — more than one match **is** a failure). `data.training_data` and not
`['data', 'os']` is rule 1 above: the join is taken because `data/training_data.py` is
a repo file. Run the same command with `from dataclasses import dataclass` in the
fixture and paste that too — it must print `['dataclasses', 'os']`.

Then prove each new rule on the real files, still under D2. First the two literal
readers and their division of labour:
```bash
"$PR" -c "
import sys; sys.path.insert(0,'.')
import run
print(run.literal_keys_of('agent/injected_text_formats.py', 'FORMATS'))
try:
    print('literal_of returned:', repr(run.literal_of('agent/injected_text_formats.py', 'FORMATS')))
except BaseException as e:
    print('literal_of refuses FORMATS:', type(e).__name__, e)"
```
Expected: `['note', 'p1_e1', 'p1_e2', 'p2_e1', 'p2_e2']`, then either an exception
naming the file or `None` plus one printed problem naming
`agent/injected_text_formats.py` and `FORMATS` — whichever shape the implementation
gives a reader failure, the same shape as the two-match case above. What must not
happen is `literal_of` returning the keys, or any other value, for `FORMATS`: a
fallback there stops check 4 firing.

Next the annotation-line parse (rules 2 and 3), printed with whatever helper check 2
uses. Paste the parsed entry set of these four lines:

| entry and label | expected parse |
|---|---|
| `train/utils/trainer.py` `used by:` | the three method files `train/methods/ctool.py`, `train/methods/cgen.py`, `train/methods/cparam.py` — rule 2 step 4 |
| `models/agent_models/service.py` `used by:` | `agent/step_without_probe.py` and `agent/run_tasks.py` only; the `jobs/launch.py …` clause after the `;` is prose — rule 2 step 5 |
| `models/probe_models/base.py` `imports:` | `models/__init__.py` only; `models/probe_models/<backbone>.py` is dropped and tested by rule 3 |
| `models/probe_models/__init__.py` `used by:` | the package rule, equal to `base.py`, `service.py`, `qwen.py` in that directory |

Then check 5's structural read and check 4's expansion, which need no implementation
to run and whose output the implementation must reproduce:
```bash
"$PR" -c "
import ast, pathlib
for f in ['data/trajectory_record.py','data/training_data.py','data/probe_output.py']:
    t = ast.parse(pathlib.Path(f).read_text()); got = {}
    for n in ast.walk(t):
        if getattr(n, 'col_offset', 1) != 0: continue
        tg = n.targets if isinstance(n, ast.Assign) else ([n.target] if isinstance(n, ast.AnnAssign) else [])
        for x in tg:
            if isinstance(x, ast.Name) and x.id in ('SCHEMA','DEFAULTS','REQUIRED'):
                got.setdefault(x.id, []).append(n)
    cols = [ast.literal_eval(k) for k in got['SCHEMA'][0].value.keys]
    req = ast.literal_eval(got['REQUIRED'][0].value.args[0])
    print(f, {k: len(v) for k, v in got.items()}, len(req), sorted(set(req) - set(cols)))"
```
Expected, exactly:
```
data/trajectory_record.py {'SCHEMA': 1, 'DEFAULTS': 1, 'REQUIRED': 1} 12 []
data/training_data.py {'SCHEMA': 1, 'DEFAULTS': 1, 'REQUIRED': 1} 16 []
data/probe_output.py {'SCHEMA': 1, 'DEFAULTS': 1, 'REQUIRED': 1} 9 []
```
```bash
"$PR" -c "
import sys, pathlib, yaml; sys.path.insert(0,'.')
from experimental_settings import schema
t = yaml.safe_load(pathlib.Path('models/table.yaml').read_text())
fam = {r: sorted({v['family'] for v in t.values() if v['role'] == r}) for r in ('agent','probe')}
named = set()
for row in schema.STAGES.values():
    for e in row['versions']:
        p = e.split('@')[0].split('#')[0]
        outs = [p]
        for tok, vals in [('{env}', schema.AXES['data.env']), ('{method}', schema.AXES['probe.method']),
                          ('{probe_score_method}', schema.AXES['probe.method']),
                          ('{family}', fam['agent']), ('{backbone}', fam['probe'])]:
            if tok in p: outs = [p.replace(tok, v) for v in vals]
        named |= set(outs)
print(len(named), 'missing:', [p for p in sorted(named) if not pathlib.Path(p).exists()])"
```
Expected: `22 missing: []`.

**D3 — the whole-tree selfcheck.**
```bash
"$PR" run.py selfcheck; echo "rc=$?"
```
Expected: `selfcheck: 31 python files, 0 problems` and `rc=0`.

**D4 — each check actually fires.** For each of the eleven checks above, break one
thing in a **scratch copy of the tree** (never in the worktree's own files —
copy the tree to a temp directory, break it there, and run `selfcheck` with that
directory as the working directory), confirm `selfcheck` names it and exits 1,
then restore. Paste one line per check: the check number, what you broke, and the
message `selfcheck` printed. The eleven breakages:

| # | break |
|---|---|
| 1 | delete one `.py` line from `README.md` |
| 2 | add `import jobs.registry` to `models/probe_models/base.py` |
| 3 | add a sixth key to `agent/injected_text_formats.py`'s `FORMATS` |
| 4 | add a second column-zero `VERSION` to `data/training_data.py` |
| 5 | add a name to `data/probe_output.py`'s `REQUIRED` that its `SCHEMA` does not declare |
| 6 | change `eval/utils/probe_eval.py`'s `PROBE_KIND["cgen"]` to `"classifier"` |
| 7 | change `models/agent_models/gptoss.py`'s `DEFAULT_EFFORT` to `"ultra"` |
| 8 | delete one alias block from `constants/path_models.yaml`, so a `models/table.yaml` row's `result.weights` no longer resolves |
| 9 | put a literal `/net/tokyo100-10g/...` path in `eval/score_run.py` |
| 10 | add `import torch` at module level to `eval/utils/probe_eval.py` |
| 11 | `touch <scratch>/experimental_settings/free.yaml` — **undone by deleting the whole scratch copy** (`rm -rf "$S"`) and re-copying the tree, never by removing the single file: the hook's Bash rule blocks any command naming `experimental_settings/<anything>.yaml` together with `rm `, so the obvious undo exits 2 |

Two of the eleven fire through the readers the parser block adds, not through
`literal_of`: breakage 3 adds a literal key to the same `ast.Dict`, so
`literal_keys_of` returns six names and check 3 reports the disagreement with
`schema.AXES["inject.format"]`; breakage 5 adds a string to the `frozenset(...)`
call, so check 5's structural read reports the name that `SCHEMA` does not declare.
If either breakage produces a parse refusal instead of the check's own message, the
reader is wrong, not the breakage.

**The read-only hook is armed by this wave, and it matches on the path's tail.**
`.claude/hooks/settings_readonly.sh` refuses a `Write`/`Edit` whose path ends in
`experimental_settings/<anything>.yaml` or `models/table.yaml`, and a `Bash`
command that names such a path together with `>`, `>>`, `tee`, `sed -i`, `cp `,
`mv `, `rm `, `truncate`, `dd `, `patch`, `chmod` or `install`. **Copying the tree
to a temp directory does not escape it**, because only the tail is matched. That
is why breakage 8 works on `constants/path_models.yaml` — the other side of the
same check 8, and `constants/` is not protected — and why breakage 11 uses
`touch`, which is not one of the blocked verbs and is all check 11 needs (it
reads the file's **stem**, not its contents). Do not look for a way around the
hook for the two protected files: there is no breakage in this list that needs
one.

**D5 — `--help` lists ten subcommands, `selfcheck` among them.**
```bash
"$PR" run.py --help
```
Expected: the usage block listing the ten subcommands in the order run.py prints
them today — `ls, where, find, kill, refire, retry, table, free, sync, selfcheck` —
with `selfcheck   -- the tree's self-consistency checks` among them, and the walk
form on the first line. Run at this ticket's HEAD this already passes, `rc=0`; it is
here so an edit to `run.py` cannot break it silently.

**D6 — `where` answers for every stage of every workflow, real and debug.**
Ticket 14 could run this only over `baseline` and over `train_probe`'s `sample`
and `build`, because `train/` had not merged in wave 5 and a `train`, `eval` or
`inject` key reads `train/utils/trainer.py`'s and `train/methods/<m>.py`'s
`VERSION` lines. Wave 6 has them, so the full sweep lands here.
```bash
set -e
for a in "baseline gpt_oss_120b_appworld sample" "baseline gpt_oss_120b_appworld score" \
         "train_probe ctool_qwen3_0pt6b sample" "train_probe ctool_qwen3_0pt6b build" \
         "train_probe ctool_qwen3_0pt6b train"  "train_probe ctool_qwen3_0pt6b eval" \
         "train_probe cgen_qwen3_0pt6b train"   "train_probe cgen_qwen3_0pt6b eval" \
         "train_probe cparam_qwen3_0pt6b train" "train_probe cparam_qwen3_0pt6b eval" \
         "inject probe_p1_e1_theta_0pt80 inject"      "inject probe_p1_e1_theta_0pt80 score" \
         "inject no_probe_p1_e1_theta_0pt80 inject"  "inject no_probe_p1_e1_theta_0pt80 score"; do
  "$PR" run.py where $a
  "$PR" run.py where $a --debug
done
echo "D6 ok"
```
Expected: twenty-eight absolute paths of the shape `<root>/<stage>/<12 hex>` and
`<root>/debug/<stage>/<12 hex>`, printed whether or not the directories exist;
`D6 ok`, exit 0. No command here launches anything or creates a directory. Run at
this ticket's HEAD the sweep already passes, so a failure here is a regression your
`run.py` edit introduced, not a missing piece of the tree.

**D7 — every named setting of all three workflow files loads, keys and freezes
under `--debug` and without it.** Ticket 14's `C6`, unrestricted.
```bash
"$PR" - <<'PY'
import pathlib, yaml
from experimental_settings import schema
for f in ["baseline.yaml", "train_probe.yaml", "inject.yaml"]:
    p = pathlib.Path("experimental_settings") / f
    doc = yaml.safe_load(p.read_text())
    stages = doc["workflow"]
    names = [k for k in doc if k not in ("workflow", "common")]
    for name in names:
        for dbg in (False, True):
            for cfg in schema.load(p, name, debug=dbg, overrides={}):
                keys = {s: schema.key(s, cfg) for s in stages}
                dirs = {s: schema.run_dir(s, cfg) for s in stages}
                assert cfg._workflow == stages, (f, name, cfg._workflow)
                for s in stages:
                    assert len(keys[s]) == 12, (f, name, s, keys[s])
                    assert dirs[s].name == keys[s], (f, name, s)
                    assert ("/debug/" in str(dirs[s])) == dbg, (f, name, s, dbg)
                print(f, name, "debug" if dbg else "real",
                      " ".join(f"{s}={keys[s]}" for s in stages))
print("D7 ok")
PY
```
Expected: twelve lines, one per (file, setting, debug/real), each naming a 12-hex
key per stage, then `D7 ok`, exit 0. The `inject` settings need their references to
resolve; a reference resolves to a **key**, not to a directory, so the loader must
key them whether or not any upstream run exists — report it if it does not. Run at
this ticket's HEAD this already passes; a failure here is a regression.

### GPU / main session — not yours

None in this ticket. After this wave merges, the main session runs the GPU list
of the construction plan's section 2 and the three end-to-end `--debug` walks of
its section 4, whose run keys ticket 18's TIMELINE entry quotes.

## Comments

- 2026-09-18, from gyb (errata "3.3 / 8.6 (what a `VERSION` bump invalidates)"): selfcheck enforces the strict shape the key path leaves lenient. For every file with a column-zero `VERSION`: the VERSION rule comment block sits directly above it with the pinned text; `VERSION_HISTORY` exists at column zero exactly once and is a plain literal; its keys are exactly 2..`VERSION`; every entry has a non-empty `why`; every `stale` value is a tuple of stage names of `schema.STAGES`. A file at `VERSION = 1` has `VERSION_HISTORY = {}`.
