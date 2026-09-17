# T05 report — the environment contract and AppWorld

Branch: `ticket/2026-09-17-wave2/T05`. Base: `943af829b83f8f66d4b4a6434f4a685b2b2f9c10`.
Head: `7cc4d65` (see commit list below for the exact sha after `git worktree remove`).

## What was done

Two files, per the ticket's `## What to do`, built in the three passes the
ticket names:

- `data/environments/__init__.py` — contracts 4.1/4.2, 2.3. `VERSION = 1` at
  column zero; `StepObservation` (the four fields); `Environment` (the seven
  class attributes as bare annotations, the `task_text` instance attribute as
  a bare annotation per errata E3, the nine methods each one line raising
  `NotImplementedError` naming the method); `open_env(name)` in the ticket's
  four-step order (read `constants/path_datasets.yaml` first and refuse
  naming the environment blocks it has, `importlib.import_module` inside the
  function, refuse unless exactly one strict subclass of `Environment`,
  instantiate and refuse naming every missing method/attribute);
  `requested_pairs(env, splits, tasks, n_tasks, seeds)` — per-split filter,
  per-split `n_tasks` cap, split-order concatenation, task-major cross with
  seeds (errata E4).
- `data/environments/appworld.py` — contracts 4.1, 4.2, 4.3, 4.4.
  - Pass B (the `any` half): `VERSION`, `INSTRUCTIONS`, `SPLIT_ROLE` as the
    three module-level literals (`ast.literal_eval`-parseable, no f-string,
    no `+`); the seven class attributes, including
    `NO_CODE_MESSAGE`/`RESULT_CAP`/`SEED` copied verbatim from the ticket's
    table; `__init__` reading `constants/path_datasets.yaml`'s `appworld:`
    block and refusing when `data` is not `<home>/data`; `tasks(split)`
    (never sorted, refuses naming the split and the keys it has);
    `split_args`/`build_call`/`complete_call` as specified, `build_call`
    never using `repr()` (errata E5).
  - Pass C (the world half): `open` (env var `APPWORLD_ROOT`, `from appworld
    import AppWorld` inside `open` alone, `task_text` set from
    `world.task.instruction`, the frozen-clock read); `step` (the
    ```python``` regex, `StepObservation` construction); `speculate` (the
    3-step: requote → save/execute/restore → refreeze+assert, timed with
    `time.clock_gettime(time.CLOCK_MONOTONIC)` per errata E12, refusing
    before step 1 when `open` recorded no clock per errata E9); `judge`
    (the dict-with-boolean-`success` check, else the 600-char fallback,
    errata E10); `close` (world close, `rmtree` of
    `<home>/experiments/outputs/<experiment_name>`, no-op on a second call).
- `README.md` — the two files' five-line entries under a new "## Ticket 05"
  section, copied from contracts 0.2 with one correction (see Decisions).

## How it was verified

All commands below were run from the worktree root
(`/home/y-guo/reproduce/new1-wt/2026-09-17-wave2-T05`) exactly as the
ticket gives them, interpreters by absolute path.

**A0 — imports under every interpreter of the `venvs:` map.**
```
1 ['build_call', 'close', 'complete_call', 'judge', 'open', 'speculate', 'split_args', 'step', 'tasks']
1 ['build_call', 'close', 'complete_call', 'judge', 'open', 'speculate', 'split_args', 'step', 'tasks']
1 ['build_call', 'close', 'complete_call', 'judge', 'open', 'speculate', 'split_args', 'step', 'tasks']
```
Matches, exit 0, all three interpreters.

**A0b — standard library and PyYAML only, under system `python3`. FAILS, ticket's command is wrong.**
```
Traceback (most recent call last):
  ...
  File "/usr/lib/python3.10/dataclasses.py", line 711, in _is_type
    ns = sys.modules.get(cls.__module__).__dict__
AttributeError: 'NoneType' object has no attribute '__dict__'
```
This is a CPython stdlib defect, not a defect in this ticket's files. The
ticket's own `A0b` command loads the module with
`importlib.util.spec_from_file_location` + `module_from_spec` +
`exec_module`, **without** registering the module in `sys.modules` first
(the pattern importlib's own docs use — `sys.modules[name] = module` —
before `exec_module`). Under `from __future__ import annotations` (mandated
by spec.md section 5 for every file), every dataclass field annotation is a
plain string at class-body-execution time, and CPython's
`dataclasses._process_class` calls `_is_type(...)` for every such field,
which unconditionally does `sys.modules.get(cls.__module__).__dict__` with
no null check. When the module was never registered, this raises
`AttributeError` — for *any* dataclass with postponed annotations, not
specifically `StepObservation`. Verified independent of this ticket's code
with a two-line reproduction (`@dataclass` + `from __future__ import
annotations` + a single `x: str` field), which fails identically under
system `python3` (3.10.12) and, checked for completeness, also under the
`probe-env` (3.11.15) and `appworld` (3.12.13) interpreters — this CPython
issue is not fixed on any Python version installed on this machine.
`StepObservation` is `@dataclass`-decorated because contracts 4.1 requires
it verbatim (`@dataclass\nclass StepObservation:`), and
`from __future__ import annotations` is mandated for every file by spec.md
section 5, so there is no way to satisfy both mandatory rules and also
satisfy this specific loading pattern. A corrected version of the same idea
(registering the module in `sys.modules` before `exec_module`, matching
importlib's documented usage) does succeed and prints `1 StepObservation`,
confirming the file itself is correct; I did not substitute this for the
literal acceptance command's output above, per the instruction to paste the
real output.

**A1 — `StepObservation`'s four fields.**
```
None NO_CODE_BLOCK None False
```
Matches, exit 0.

**A2 — `open_env` refuses an unknown environment by name.**
```
REFUSED True True
```
Matches, exit 0.

**A3 — `requested_pairs`: per-split cap, split order, task-major cross.**
```
[('train', 'a', 1), ('train', 'a', 2), ('train', 'b', 1), ('train', 'b', 2), ('dev', 'd', 1), ('dev', 'd', 2), ('dev', 'e', 1), ('dev', 'e', 2)]
[('dev', 'd', 7), ('train', 'b', 7)]
[]
[('train', 'a', 1), ('train', 'b', 1), ('train', 'c', 1)]
```
Matches exactly.

**A4 — the `VERSION` line shape and no absolute path.**
```
1
NO_ABS_PATH
```
Matches.

**B0 — the seven attributes, under every interpreter of the map.**
```
appworld 1 4000 100 ['v1'] {'train': 'train', 'dev': 'val', 'test': 'test'} AppWorld
appworld 1 4000 100 ['v1'] {'train': 'train', 'dev': 'val', 'test': 'test'} AppWorld
appworld 1 4000 100 ['v1'] {'train': 'train', 'dev': 'val', 'test': 'test'} AppWorld
```
Matches, all three interpreters, exit 0.

**B1 — `tasks` reads the split files in file order.**
```
train 90 82e2fac_1 aa8502b_3
dev 57 50e1ac9_1 4fab96f_3
test 168 3d9a636_1 bde252e_3
REFUSED True
```
Matches the ticket's measured values exactly.

**B2 — `split_args` on the three shapes, including the span.**
```
apis.spotify.login [('username', 'a@b.c'), ('password', 'pw')] (6, 57) True
None
('apis.a.b', [('pos0', 'x')], (6, 19))
None
```
Matches exactly.

**B3 — `build_call` is the inverse, on the four shapes that break a naive join.**
```
True "apis.a.b(k='')"
True "apis.a.b(k='a, b', 'x=y')"
True 'apis.a.b(username=+1555, \'# c\n  password="P!\')'
True 'apis.a.b(access_token=token, page_index=0)'
```
Matches exactly, exit 0.

**B4 — the round trip over the real corpus.**
```
4074 4040 4040
```
Matches the ticket's expected counts exactly, exit 0. Measured wall time was
about 23 s, not "about 4 s" as the ticket estimates — the corpus glob and
per-line JSON parse simply take that long on this run; the counts (the part
that is actually gated) match exactly.

**B5 — `complete_call`, the legacy cases.**
```
8 of 8
```
Matches, exit 0.

**B6 — the literal rule, no absolute path, no module-level benchmark import.**
```
1
1
1
NO_ABS_PATH
['v1'] {'train': 'train', 'dev': 'val', 'test': 'test'} 1
```
The first five lines (the `grep` counts, `NO_ABS_PATH`, and the `ast.literal_eval`
dict comprehension's printed line) match exactly. The script's **second**
`python` block — the one computing `appworld_at_module_level` — fails with
`AttributeError: 'Import' object has no attribute 'module'`, again a defect
in the acceptance script rather than in the file: its list comprehension
`[a.module or a.names[0].name for a in t.body if isinstance(a, (ast.Import,
ast.ImportFrom))]` accesses `.module` unconditionally, but that attribute
exists only on `ast.ImportFrom` nodes, not on plain `ast.Import` nodes
(`import os`, `import re`, etc.) — the `or` never gets a chance to fall back,
since attribute access on the wrong node type raises before the `or` is
evaluated. This is not specific to `data/environments/appworld.py`: every
already-merged file that uses a plain `import os`/`import re`/`import time`
(e.g. `data/task_record.py`, `jobs/registry.py`) would hit the same
`AttributeError` if fed through this exact line, so restyling this file's
imports into `from os import environ`-style to dodge it would be
inconsistent with the rest of the repo for no real gain. I did not do that.
A corrected version of the same check (branching on `ast.ImportFrom` vs.
`ast.Import` instead of relying on the broken `or`) does run cleanly and
prints:
```
module_level_imports ['__future__', 'ast', 'os', 're', 'shutil', 'time', 'pathlib', 'yaml', 'data.environments']
appworld_at_module_level False
```
confirming the actual property the check exists for — no module-level
`appworld` import — holds. I did not substitute this for the literal
acceptance command's output above.

**C0 — the whole life cycle on one dev task** (appworld venv, CPU, ~20 s).
```
TASK_TEXT True
STEP 'print(1+1)\n' '2\n' None False
NOCODE None NO_CODE_BLOCK None False
ERRKIND Exception True
JUDGE True ['difficulty', 'failures', 'num_tests']
DIR_BEFORE True
DIR_AFTER False
```
Matches exactly, exit 0.

**C1 — `speculate` leaves the world and the clock unchanged.**
```
KEYS ['arg_modes', 'error_kind', 'exec_code', 'exec_ok', 'exec_out', 'spec_s']
OK True None True True
CLOCK_SOURCE 1.5235241036862135
CLOCK True
UNPARSABLE ['unparsable_raw'] False Exception
```
Matches: `spec_s` is a positive float (the ticket's own machine measured
1.519; this run measured 1.524), confirming `CLOCK_MONOTONIC` is in use
rather than the frozen `time.time()`, which would print `0.0`.

**C2 — `speculate` before `open` refuses, and a second `close` is a no-op.**
```
REFUSED True
CLOSE_TWICE_OK
```
Matches, exit 0.

**C3 — B0-B6 rerun after the world half landed.** Rerun above (same commands
as B0-B6, all outputs unchanged); pasted inline above rather than twice.

### Selfcheck lines that apply later

`run.py` does not exist on this branch yet (wave 6), so `python3 run.py
selfcheck` was not run, per spec.md section 7 and the implementer protocol.
The ticket's own "Selfcheck lines that apply later" section already states
what `run.py selfcheck` will check over these two files; nothing further to
add here.

### GPU / main session

None — AppWorld is CPU-only and this ticket's folder has no GPU or
cross-host check (the ticket's own "GPU / main session — not yours" section
names the three whole-tree checks that belong to a later ticket / the main
session: the `--debug` sample walk, the `--debug` inject walk, and `run.py
selfcheck`).

## Commit list

- `7cc4d65` — `T05: environment base contract and AppWorld` (both files,
  the README section). This is the only commit; the whole ticket landed as
  one logical unit since the two files are inseparable (the base contract
  has no independent behavior without a concrete environment, and
  `appworld.py` cannot exist without the base).

## Decisions made that the ticket did not make, and where

1. **`open_env`'s "blocks the file does have" excludes the top-level
   `venvs:` map.** Contracts 6.3 describes `path_datasets.yaml` as "one
   top-level `venvs:` map, then one block **per environment**" — so `venvs`
   itself is not an environment block. `open_env` in
   `data/environments/__init__.py` computes `blocks = sorted(k for k in doc
   if k != "venvs")` and refuses naming that list. Confirmed by A2's
   acceptance (only checks the message contains `'appworld'`, not the
   absence of `'venvs'`, so either reading would have passed A2 — this is a
   judgment call for message clarity, not something the acceptance forces).

2. **Regex patterns are stored as plain strings, not compiled `Pattern`
   objects, at module level in `appworld.py`.** A first version compiled
   them (`AW_CALL = re.compile(...)`, etc.), which is idiomatic Python but
   broke B6's `ast.literal_eval` dict comprehension (that comprehension
   evaluates *every* module-level bare-`Name` assignment as a literal, and
   a compiled-regex `Call` node is not one). Since the ticket's own literal
   rule (section "the `any` half") only requires that `VERSION`,
   `INSTRUCTIONS` and `SPLIT_ROLE` be literals — it says nothing that
   forbids other module-level names, but B6's script assumes there are no
   others — I changed the four helper patterns (`CALL_START`, `CODE_BLOCK`,
   `IDENT`, `POSKEY`) to plain regex strings, used with `re.search`/
   `re.match` at each call site instead of a precompiled `Pattern`. This
   keeps them as named, single-source constants while satisfying the
   acceptance script; `re`'s own internal pattern cache means this costs
   nothing at runtime. `ALWAYS_STR` (a set literal) and `CKPT` (a string
   literal) needed no change, since a set/string literal is already
   `ast.literal_eval`-safe.

3. **The `appworld.py` `imports:` README line says "inside open() alone"**,
   not contracts 0.2's "inside open()/step()/speculate()". The ticket's own
   build section states, in bold, "The `from appworld import AppWorld`
   statement sits **in `open` alone** (errata E11); the other four world
   methods use the handle `open` stored" — so `step`, `speculate`, `judge`
   and `close` all use `self._world` (the handle `open` already built) and
   import nothing. Per spec.md section 1, the ticket (which carries the
   errata) wins over contracts 0.2 on this point; I used the corrected text
   in `README.md` and noted the discrepancy there too, rather than copying
   a line I know to be stale.

4. **`open_env`'s combined refusal.** The ticket says "check the nine
   method names exist on the instance and the seven class attributes are
   set (`hasattr`), refuse naming each missing one" without specifying
   whether the method check and the attribute check are one combined
   refusal or two separate ones. I implemented one combined `ValueError`
   listing every missing method and attribute name together (methods first,
   then attributes, both alphabetically sorted within their group). No
   acceptance command exercises a case with any of the nine methods or
   seven attributes actually missing, so this is untested by the given
   suite; it is a reasonable reading of "refuse naming each missing one."

5. **`_bare_safe`'s exact trigger conditions for `build_call`'s quoting.**
   The ticket's prose ("wrap the value in a quote when it is empty, holds a
   top-level `,` or `=`, or ends with an unbalanced bracket or quote") is
   somewhat compressed. I implemented it as: scan the value once with the
   same quote/bracket-depth tracking `_split_args_named` uses; the value is
   safe to leave bare only if it is non-empty, never hits a `,` or `=` at
   depth 0 outside a quote, and ends the scan at depth 0 with no quote left
   open. This passed all of B3 (the four hand-picked shapes) and B4 (4040
   of 4040 real actions round-trip), which is the strongest evidence
   available that the reading is right.

## Open questions

None that block this ticket. The two acceptance-script defects (A0b, and
B6's `appworld_at_module_level` check) are worth fixing in the ticket file
itself before another ticket or `run.py selfcheck` (wave 6) relies on
either pattern, since both are general Python/AST gotchas that would bite
any file with a dataclass + postponed annotations, or any file with a plain
`import x` statement, respectively — not just this one.
