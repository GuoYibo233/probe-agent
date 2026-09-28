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

---

# Post-merge fix round 1

Branch: `ticket/2026-09-17-wave2/T05`, recreated from the current `from-zero`
HEAD after the wave merge deleted it.
Base: `67473dd0d6ea2a6e9e563d6cf1a6db20d8d4924a`. Head: `511e61d3912e7c11cbe4f6be045c72ff30c924b3`.
One file changed: `data/environments/appworld.py`. One commit.

Worktree: `/home/y-guo/reproduce/new1-wt/2026-09-17-wave2-T05-postfix1`, removed
at the end, branch kept. Fixture directory for the proof scripts: `mktemp -d`
gave `/tmp/tmp.azhNkY1UY3`.

## ENV-1 — the quote-blind paren walk

Confirmed and fixed at its root, per the owner's ruling of 2026-09-17 (the fix
overrides the ticket's pinned quote-blind walk).

`_first_call_named` counted `(` and `)` with no quote tracking, while
`complete_call` carried a second walk that was quote-, escape- and
triple-quote-aware. Two walks over the same grammar, and they disagreed.

The fix is one walk. The quote-aware walk is now the module-level
`_call_close(text, start) -> int | None`, which returns the index of the `)`
closing the call whose `(` is at `start`. `_first_call_named` (behind
`split_args`) and `complete_call` both call it; neither carries a walk of its
own any more. The walk is Python source rules: inside a string literal only the
closing quote counts (single, double and triple quoted), a backslash escapes the
next character, `#` runs to the end of the line, and an unterminated comment or
an unbalanced call gives `None`.

The finding's own two examples, on the fixture:

```
$ FIX=$(mktemp -d)                      # -> /tmp/tmp.azhNkY1UY3
$ PYTHONPATH=/home/y-guo/reproduce/new1-wt/2026-09-17-wave2-T05-postfix1 \
    /home/y-guo/reproduce/new1/external/probe-env/bin/python "$FIX/env1_env2.py"
=== ENV-1: a ')' inside a password value ===
tool   apis.spotify.login
args   [('username', 'matthew.blac@gmail.com'), ('password', 'TsivP)G')]
span   (0, 73)
text[span] == whole call: True

=== ENV-1: a '(' inside a password value (was one of the 10 None) ===
split_args    ('apis.phone.login', [('username', '6639773608'), ('password', 'b270(RP')], (0, 59))
span is whole: True
complete_call apis.phone.login(username="6639773608", password="b270(RP")
split_args and complete_call agree: True
```

Both the span and the argument list are now the full call, and `split_args` and
`complete_call` return the same call text for the same input.

### What this cost, and the three further root causes it exposed

Making the reader correct made the writer wrong, three times over, each time
because `_bare_safe` claimed a value could be written bare when the reader would
not read it back as itself. All three are the same defect — the writer's model
of the reader had drifted from the reader — and all three are fixed inside
`_bare_safe`, not worked around. After the walk fix alone, B4 over the real
corpus gave `4074 4050 4039`: 11 of the newly correct parses failed 2.5's
round-trip gate.

1. **Eight values holding a `#`** (`password="2a3mE#x"`, `password="#XdnUVa"`,
   `password="GB#I12c"` and so on). `build_call` wrote `password=2a3mE#x` bare;
   the now comment-aware walk read the `#` as a comment, swallowed the rest of
   the line including the call's `)`, and the re-parse returned `None`. A value
   holding a `#` outside a quote is not bare-safe.
2. **Three values that are a trailing comment**, e.g.
   `page_limit=20  # max allowed per request`, whose value `_split_args_named`
   had swallowed whole. Same cause, same fix: the `#` sends the value down the
   quoting branch, and it round-trips.
3. **Three values with a stray bracket**, `&I]qO(X` and `_u(r]7K`.
   `_bare_safe` counted `([{` and `)]}` on one interchangeable counter that was
   allowed to go negative, so `&I]qO(X` summed to zero and passed as "balanced",
   and `_u(r]7K` summed to zero across two different bracket kinds. The walk
   counts parentheses alone. Written bare, `password=&I]qO(X)` has its call `)`
   eaten by the value's own `(`, and the re-parse returned `None`.

`_bare_safe` now carries one counter per reader, because the two readers count
different things: `parens` for `_call_close`, which counts parentheses alone,
and `brackets` for `_split_args_named`, which counts every bracket kind when it
decides whether a `,` or `=` is top-level. Each counter must stay at or above
zero throughout and end at zero. The `,`/`=` test uses `brackets`, the reader
that performs the split.

## ENV-2 — a value with leading or trailing whitespace

Confirmed and fixed at its root: `_bare_safe` now returns False when
`value != value.strip()`, so the value goes down the existing quoting branch.
No wrapper, no special case at the call site.

The finding's own example and the symmetric cases it names:

```
=== ENV-2: a value with trailing whitespace ===
parsed args  [('phone_number', '+11234567890'), ('message', 'See you at 5 ')]
build_call   "apis.phone.send_message(phone_number=+11234567890, message='See you at 5 ')"
re-parsed    [('phone_number', '+11234567890'), ('message', 'See you at 5 ')]
round trips : True

=== ENV-2: the finding's own one-liner ===
build_call   "apis.a.b(message='hello world ')"
re-parsed    [('message', 'hello world ')]
round trips : True

=== ENV-2: symmetric cases ===
' hello world'     -> "apis.a.b(k=' hello world')" re-parsed [('k', ' hello world')]  round_trip=True
' hello world '    -> "apis.a.b(k=' hello world ')" re-parsed [('k', ' hello world ')] round_trip=True
' '                -> "apis.a.b(k=' ')"            re-parsed [('k', ' ')]             round_trip=True
'   '              -> "apis.a.b(k='   ')"          re-parsed [('k', '   ')]           round_trip=True
'\t'               -> "apis.a.b(k='\t')"           re-parsed [('k', '\t')]            round_trip=True
'\nx\n'            -> "apis.a.b(k='\nx\n')"        re-parsed [('k', '\nx\n')]         round_trip=True
"'hello'"          -> "apis.a.b(k='hello')"        re-parsed [('k', 'hello')]         round_trip=False
'"hello"'          -> 'apis.a.b(k="hello")'        re-parsed [('k', 'hello')]         round_trip=False
"'"                -> 'apis.a.b(k="\'")'           re-parsed [('k', '')]              round_trip=False
'a b'              -> 'apis.a.b(k=a b)'            re-parsed [('k', 'a b')]           round_trip=True
```

Leading whitespace, trailing whitespace, both, a whitespace-only value and a
tab- or newline-only value all round-trip exactly.

**The three `round_trip=False` lines are a property of the ticket's stated parse
rule, not of `build_call`**, and I left them alone deliberately. `split_args`
ends every value with `.strip().strip("\"'")` (the ticket's own wording), which
removes every quote character from both ends of whatever is written. So a value
that itself begins or ends with `'` or `"` cannot survive, whichever of the
three writings `build_call` picks:

```
$ PYTHONPATH=/home/y-guo/reproduce/new1-wt/2026-09-17-wave2-T05-postfix1 \
    /home/y-guo/reproduce/new1/external/probe-env/bin/python "$FIX/quote_edge.py"
=== 1. no quoting choice can preserve a value that begins or ends with a quote char ===
  value "'hello'"  written bare            as k="'hello'"      -> re-parsed 'hello'    equal=False
  value "'hello'"  written single-wrapped  as k="''hello''"    -> re-parsed 'hello'    equal=False
  value "'hello'"  written double-wrapped  as k='"\'hello\'"'  -> re-parsed 'hello'    equal=False
  value '"hello"'  written bare            as k='"hello"'      -> re-parsed 'hello'    equal=False
  value '"hello"'  written single-wrapped  as k='\'"hello"\''  -> re-parsed 'hello'    equal=False
  value '"hello"'  written double-wrapped  as k='""hello""'    -> re-parsed 'hello'    equal=False
  value "'"        written bare            as k="'"            -> re-parsed ''         equal=False
  value "'"        written single-wrapped  as k="'''"          -> re-parsed ''         equal=False
  value "'"        written double-wrapped  as k='"\'"'         -> re-parsed ''         equal=False

=== 2. split_args never produces such a value: every value of the whole p1 corpus ===
  values parsed 5297 beginning or ending with a quote character 0
```

Adding a `_bare_safe` condition for it would swap one wrong answer for another,
so it would not be a fix. The case is also outside `build_call`'s contract:
4.2 makes `build_call` the inverse of `split_args` **over the args `split_args`
produces**, and `split_args` produces no such value — 0 of the 5,297 argument
values of the whole p1 corpus begin or end with a quote character, by
construction of the `.strip("\"'")` rule. If the owner wants such a value to be
representable, the change belongs in the parse rule in the ticket (stop
stripping quotes, or unescape), not in `build_call`.

## The round trip over the real corpus, re-measured

**B4, the ticket's command verbatim.**
```
$ cd /home/y-guo/reproduce/new1-wt/2026-09-17-wave2-T05-postfix1
$ time "$PR" - <<'PY'   # the ticket's B4 script, unchanged
...
PY
4074 4050 4050

real	0m4.123s
user	0m3.812s
sys	0m0.216s
exit=0
```

The ticket says `4074 4040 4040`. **The new numbers are `4074 4050 4050`.** The
non-null action count is unchanged at 4,074; 10 more actions parse; every one of
the 4,050 parsed actions round-trips. The ticket's "about 4 s" estimate is right
on this run (4.1 s).

**The before/after breakdown**, measured with the pre-fix walk reimplemented
alongside the new one in the same pass:
```
$ PYTHONPATH=/home/y-guo/reproduce/new1-wt/2026-09-17-wave2-T05-postfix1 \
    /home/y-guo/reproduce/new1/external/probe-env/bin/python "$FIX/corpus.py"
B4 4074 4050 4050
none_total 24 no_api_call_at_all 24 other_call_never_closes 0
was_none_now_parsed 10 was_parsed_now_none 0 span_was_truncated_now_full 13
seconds 3.9
('truncated_before', 'apis.spotify.login(username="matthew.blac@gmail.com", password="TsivP)', 'apis.spotify.login(username="matthew.blac@gmail.com", password="TsivP)G")')
('truncated_before', 'apis.simple_note.login(\n    username="gl.moore@gmail.com",\n    password="aVfy)', 'apis.simple_note.login(\n    username="gl.moore@gmail.com",\n    password="aVfy)Rr"\n)')
('truncated_before', 'apis.file_system.login(username="paul_mill@gmail.com", password="t@-)', 'apis.file_system.login(username="paul_mill@gmail.com", password="t@-)]&Q")')
('truncated_before', 'apis.simple_note.login(username="caiburc@gmail.com", password="-Bw+D)', 'apis.simple_note.login(username="caiburc@gmail.com", password="-Bw+D)w")')
('truncated_before', 'apis.spotify.login(username="aa_burt@gmail.com", password=")', 'apis.spotify.login(username="aa_burt@gmail.com", password=")FLGE$6")')
('truncated_before', 'apis.venmo.login(username="morgan-harrison@gmail.com", password="O*3)', 'apis.venmo.login(username="morgan-harrison@gmail.com", password="O*3)aho")')
('truncated_before', 'apis.venmo.login(username="kat_simp@gmail.com", password="B)', 'apis.venmo.login(username="kat_simp@gmail.com", password="B)]&d{u}")')
('truncated_before', 'apis.phone.login(username="connorbrow@gmail.com", password=")', 'apis.phone.login(username="connorbrow@gmail.com", password=")SWADm2")')
```

The finding's counts are confirmed exactly: **13 actions whose span and argument
list were truncated inside a password string now carry the full call**, and
**10 actions the walk had refused now parse**. No action that parsed before
stops parsing.

**The split of the `None` actions, re-measured.**
```
$ PYTHONPATH=/home/y-guo/reproduce/new1-wt/2026-09-17-wave2-T05-postfix1 \
    /home/y-guo/reproduce/new1/external/probe-env/bin/python "$FIX/split_none.py"
trajectory files 315
non-null actions 4074 parsed 4050 None 24
None: no api call at all 24 in 13 trajectories
None: other 0 in 0 trajectories
None trajectories in all 13
None share of non-null actions 0.59%
```

The ticket's and errata entry 2's split of 24 + 10 becomes **24 + 0**: all 24
remaining `None` actions are code blocks that call no api at all, in 13 of the
315 trajectories, 0.59% of the non-null actions. The "api call that never closes
its parentheses" class is empty over this corpus — every one of those 10 was a
well-formed call with a `(` or `)` inside a string, which the quote-aware walk
balances. Ticket 09 still skips and counts that one remaining kind as
`counts.events_skipped_no_call`.

## The acceptance groups, rerun

Every command below was run from the worktree root, interpreters by absolute
path, exactly as the ticket gives them.

**A0 — imports under every interpreter of the `venvs:` map.**
```
1 ['build_call', 'close', 'complete_call', 'judge', 'open', 'speculate', 'split_args', 'step', 'tasks']
1 ['build_call', 'close', 'complete_call', 'judge', 'open', 'speculate', 'split_args', 'step', 'tasks']
1 ['build_call', 'close', 'complete_call', 'judge', 'open', 'speculate', 'split_args', 'step', 'tasks']
exit=0
```
Matches.

**A0b — FAILS, and the defect is the ticket's script, as reported in round 0.**
```
    and _is_type(type, cls, dataclasses, dataclasses.KW_ONLY,
  File "/usr/lib/python3.10/dataclasses.py", line 711, in _is_type
    ns = sys.modules.get(cls.__module__).__dict__
AttributeError: 'NoneType' object has no attribute '__dict__'. Did you mean: '__dir__'?
exit=1
```
The script loads the module with `spec_from_file_location` + `module_from_spec`
+ `exec_module` and never registers it in `sys.modules`, which importlib's own
documented pattern does before `exec_module`. Under
`from __future__ import annotations` every dataclass field annotation is a
string, and CPython's `dataclasses._is_type` then does
`sys.modules.get(cls.__module__).__dict__` with no null check. This is the
script's defect, not the file's, it hits any dataclass with postponed
annotations, and `data/environments/__init__.py` is untouched by this fix round.
I did not bend the code to it. The corrected form of the same check, with the
one missing `sys.modules` line, passes:
```
$ python3 -c "
import sys, importlib.util as u
s = u.spec_from_file_location('env_base', 'data/environments/__init__.py')
m = u.module_from_spec(s); sys.modules['env_base'] = m; s.loader.exec_module(m)
print(m.VERSION, m.StepObservation.__name__)"
1 StepObservation
exit=0
```

**A1.** `None NO_CODE_BLOCK None False`, exit 0. Matches.

**A2.** `REFUSED True True`, exit 0. Matches.

**A3.**
```
[('train', 'a', 1), ('train', 'a', 2), ('train', 'b', 1), ('train', 'b', 2), ('dev', 'd', 1), ('dev', 'd', 2), ('dev', 'e', 1), ('dev', 'e', 2)]
[('dev', 'd', 7), ('train', 'b', 7)]
[]
[('train', 'a', 1), ('train', 'b', 1), ('train', 'c', 1)]
exit=0
```
Matches exactly.

**A4.**
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
exit=0
```
Matches.

**B1 — `tasks` reads the split files in file order.**
```
train 90 82e2fac_1 aa8502b_3
dev 57 50e1ac9_1 4fab96f_3
test 168 3d9a636_1 bde252e_3
REFUSED True
exit=0
```
Matches the ticket's measured values exactly.

**B2 — `split_args` on the three shapes, including the span.**
```
apis.spotify.login [('username', 'a@b.c'), ('password', 'pw')] (6, 57) True
None
('apis.a.b', [('pos0', 'x')], (6, 19))
None
exit=0
```
Matches exactly. The shared walk changes none of these four: the fourth case,
`print(apis.a.b(`, still never closes and still gives `None`.

**B3 — `build_call` is the inverse, on the four shapes that break a naive join.**
```
True "apis.a.b(k='')"
True "apis.a.b(k='a, b', 'x=y')"
True 'apis.a.b(username=+1555, \'# c\n  password="P!\')'
True 'apis.a.b(access_token=token, page_index=0)'
exit=0
```
Matches exactly, including the third case, whose value now takes the quoting
branch on two counts (the unbalanced `"` it always had, and the new `#` rule)
and comes out the same text.

**B4 — the round trip over the real corpus.**
```
4074 4050 4050
exit=0   (4.1 s)
```
**Differs from the ticket's `4074 4040 4040`, which is exactly what this fix
round was asked to change.** See the section above for the breakdown.

**B5 — `complete_call`, the legacy cases.**
```
8 of 8
exit=0
```
Matches. `complete_call` now runs on the shared walk and its eight legacy cases
are unchanged, which is the check that the shared walk is complete_call's old
walk and not something weaker.

**B6 — the literal rule, no absolute path, no module-level benchmark import.**
```
1
1
1
NO_ABS_PATH
['v1'] {'train': 'train', 'dev': 'val', 'test': 'test'} 1
Traceback (most recent call last):
  File "<stdin>", line 6, in <module>
  File "<stdin>", line 6, in <listcomp>
AttributeError: 'Import' object has no attribute 'module'
exit=1
```
The first five lines match. The last block fails on the same known defect of the
ticket's own script reported in round 0: `a.module` exists on `ast.ImportFrom`
alone, not on plain `ast.Import`, and attribute access raises before the `or`
can fall back. The file's imports are unchanged by this fix round. The corrected
form of the same check, branching on the node type, runs and confirms the
property the check exists for:
```
module_level_imports ['__future__', 'ast', 'os', 're', 'shutil', 'time', 'pathlib', 'yaml', 'data.environments']
appworld_at_module_level False
exit=0
```

**C2 — `speculate` before `open` refuses, and a second `close` is a no-op.**
```
REFUSED True
CLOSE_TWICE_OK
exit=0
```
Matches.

**C0 — the whole life cycle on one dev task** (appworld venv, CPU, run once at
the end).
```
TASK_TEXT True
STEP 'print(1+1)\n' '2\n' None False
NOCODE None NO_CODE_BLOCK None False
ERRKIND Exception True
JUDGE True ['difficulty', 'failures', 'num_tests']
DIR_BEFORE True
DIR_AFTER False
exit=0
```
Matches exactly.

**C1 — `speculate` leaves the world and the clock unchanged.**
```
KEYS ['arg_modes', 'error_kind', 'exec_code', 'exec_ok', 'exec_out', 'spec_s']
OK True None True True
CLOCK_SOURCE 1.519733591005206
CLOCK True
UNPARSABLE ['unparsable_raw'] False Exception
exit=0
```
Matches, `spec_s` a positive float (1.5197 this run, the ticket measured 1.519),
so `CLOCK_MONOTONIC` is still in use.

**C3 — B0 to B6 rerun after C0/C1.** Same outputs as pasted above; not repeated.

## Decisions this round that the findings did not make

1. **`#` outside a quote makes a value not bare-safe.** The findings did not
   name it; the corpus did, as 11 round-trip failures once the reader became
   comment-aware. It is ENV-1's own consequence: sharing `complete_call`'s walk
   gives `split_args` comment awareness, and a writer that emits a bare `#`
   then writes a call the reader cannot close. Fixed inside `_bare_safe`, the
   single place that decides bare versus quoted.
2. **`_bare_safe` carries one bracket counter per reader, and neither may go
   negative.** The old single counter let `&I]qO(X` and `_u(r]7K` pass as
   balanced. The `,`/`=` top-level test keeps using the all-bracket counter,
   because `_split_args_named` is the reader that performs that split; the call
   close uses the parenthesis-only counter, because `_call_close` is the reader
   that performs that. Stating the two separately is what stops them drifting
   again.
3. **A value that begins or ends with a quote character is left as is.**
   Reasoned and measured above: no quoting choice preserves it under the
   ticket's `.strip("\"'")` rule, and `split_args` produces no such value (0 of
   5,297 corpus values), so it is outside `build_call`'s contract. Changing it
   means changing the parse rule, which is the owner's call, not this round's.
4. **`_call_close` takes the index of the `(` and returns the index of the `)`**,
   rather than returning a slice or a `(call, end)` pair. `split_args` needs the
   inner text `text[i+1:j]` and the span end `j+1`; `complete_call` needs
   `text[m.start():j+1]`. An index serves both with no second shape, and keeps
   the ticket's dropped `(call, end)` tuple dropped.
5. **`README.md` is untouched.** The one file this round may edit is
   `data/environments/appworld.py`, and its five annotation lines (one sentence,
   imports, used by, reads, writes, venv) are unchanged by the fix: no import
   added, no file read or written, same venv.

## Things noticed, for another ticket or for the owner

- Ticket 09's `counts.events_skipped_no_call` now has one kind of input, not
  two: only "no api call at all". Its expected count over p1 drops from 34 to 24.
- The ticket's own A0b and B6 scripts have the two defects reported in round 0
  (module loaded by path with no `sys.modules` registration; `.module` read on
  `ast.Import`). Both are still there, both still fail, and both are worth
  fixing in the ticket file before `run.py selfcheck` in wave 6 borrows either
  pattern. I did not touch the ticket file.

---

# Post-merge fix round 2

Branch: `ticket/2026-09-17-wave2/T05`.
Base: `511e61d3912e7c11cbe4f6be045c72ff30c924b3`. Head: `a1e61c673cf79eae0c71b60894286d72aee749e5`.
One file changed: `data/environments/appworld.py`. One commit.

Worktree: `/home/y-guo/reproduce/new1-wt/2026-09-17-wave2-T05-postfix2`, removed at the
end, branch kept. Fixture directory for the proof scripts: `mktemp -d` gave
`/tmp/tmp.C6ujDrkBu8`. Three versions of the file are compared throughout:
**r0** = `67473dd` (as merged), **r1** = `511e61d` (post-merge fix round 1, this round's
base), **r2** = this round's head.

## ENV-3 — the writer's copy of the reader's rules had no backslash escape

Confirmed and fixed at its root.

Round 1 gave the reader one quote-, escape- and triple-quote-aware walk,
`_call_close`, and `split_args` and `complete_call` both run on it. The writer kept a
hand-written copy of that walk's rules inside `_bare_safe`, and the copy had no
backslash escape and counted parentheses on its own. Two models of one grammar, and
they drifted — exactly the defect round 1 fixed on the reader side, left standing on
the writer side.

The fix removes the copy. `_bare_safe` now puts the candidate through the reader
itself:

```python
def _closes_the_call(written: str) -> bool:
    return _call_close(f"({written})", 0) == len(written) + 1
```

`written` goes in as the whole argument body of a one-argument call, and the answer is
yes when the reader closes that call at the parenthesis the writer appended. That one
question replaces the copied `#` rule, the copied parenthesis counter and the missing
escape rule at once, and it cannot drift, because it is the reader. What is left of the
writer's own model is `_stays_one_argument`, which models the one reader that has no
walk to call: `_split_args_named`'s bracket counter and its `,`/`=` cut. `_quote_value`
asks the same question of the wrapped value before returning it.

A value that needs quoting and ends in an odd number of backslashes is representable in
no writing at all under the ticket's parse rule, so `build_call` refuses it by name
rather than writing a call the reader cannot close. Proof, every writing of the
finding's own two values plus a three-backslash case:

```
$ FIX=$(mktemp -d)                      # -> /tmp/tmp.C6ujDrkBu8
$ cd /home/y-guo/reproduce/new1-wt/2026-09-17-wave2-T05-postfix2
$ PYTHONPATH=$PWD /home/y-guo/reproduce/new1/external/probe-env/bin/python "$FIX/env3_proof.py"
=== every writing of a value that needs quoting and ends in a backslash ===
  value 'a,b\\'    bare                   as 'apis.a.b(k=a,b\\)'      -> re-parsed [('k', 'a'), ('pos0', 'b\\')] equal=False
  value 'a,b\\'    single-wrapped         as "apis.a.b(k='a,b\\')"    -> re-parsed None                   equal=False
  value 'a,b\\'    double-wrapped         as 'apis.a.b(k="a,b\\")'    -> re-parsed None                   equal=False
  value 'a,b\\'    triple-single-wrapped  as "apis.a.b(k='''a,b\\''')" -> re-parsed None                   equal=False
  value 'a,b\\'    triple-double-wrapped  as 'apis.a.b(k="""a,b\\""")' -> re-parsed None                   equal=False
  value 'a=b\\'    bare                   as 'apis.a.b(k=a=b\\)'      -> re-parsed [('k', 'a=b\\')]       equal=True
  value 'a=b\\'    single-wrapped         as "apis.a.b(k='a=b\\')"    -> re-parsed None                   equal=False
  value 'a=b\\'    double-wrapped         as 'apis.a.b(k="a=b\\")'    -> re-parsed None                   equal=False
  value 'a=b\\'    triple-single-wrapped  as "apis.a.b(k='''a=b\\''')" -> re-parsed None                   equal=False
  value 'a=b\\'    triple-double-wrapped  as 'apis.a.b(k="""a=b\\""")' -> re-parsed None                   equal=False
  value 'a,b\\\\\\' bare                   as 'apis.a.b(k=a,b\\\\\\)'  -> re-parsed [('k', 'a'), ('pos0', 'b\\\\\\')] equal=False
  value 'a,b\\\\\\' single-wrapped         as "apis.a.b(k='a,b\\\\\\')" -> re-parsed None                   equal=False
  value 'a,b\\\\\\' double-wrapped         as 'apis.a.b(k="a,b\\\\\\")' -> re-parsed None                   equal=False
  value 'a,b\\\\\\' triple-single-wrapped  as "apis.a.b(k='''a,b\\\\\\''')" -> re-parsed None                   equal=False
  value 'a,b\\\\\\' triple-double-wrapped  as 'apis.a.b(k="""a,b\\\\\\""")' -> re-parsed None                   equal=False

=== the same value with an even number of trailing backslashes is writable ===
  value 'a,b\\\\'      -> "apis.a.b(k='a,b\\\\')" re-parsed [('k', 'a,b\\\\')]   round_trip=True
  value 'a=b\\\\\\\\'  -> "apis.a.b(k='a=b\\\\\\\\')" re-parsed [('k', 'a=b\\\\\\\\')] round_trip=True

=== a value ending in a backslash that needs no quoting stays bare and round-trips ===
  value 'a\\'    -> 'apis.a.b(k=a\\)'        re-parsed [('k', 'a\\')]     round_trip=True
  value 'ab\\'   -> 'apis.a.b(k=ab\\)'       re-parsed [('k', 'ab\\')]    round_trip=True
  value 'a[b]\\' -> 'apis.a.b(k=a[b]\\)'     re-parsed [('k', 'a[b]\\')]  round_trip=True
exit=0
```

The one `equal=True` line is `a=b\` written bare, and it is the single writable case the
refusal covers as well; the reason is in "Decisions", item 2.

The finding's three values through `build_call` as it now stands:

```
$ PYTHONPATH=$PWD /home/y-guo/reproduce/new1/external/probe-env/bin/python "$FIX/env3.py"
=== ENV-3: the finding's three values ===
'a,b\\' -> REFUSED appworld.build_call: apis.a.b argument 'k' value 'a,b\\' needs quoting and ends in a backslash that escapes its closing ', so the call it would be written into never closes
'a=b\\' -> REFUSED appworld.build_call: apis.a.b argument 'k' value 'a=b\\' needs quoting and ends in a backslash that escapes its closing ', so the call it would be written into never closes
"a{'\\']" -> 'apis.a.b(k="a{\'\\\']")' reparsed [('k', "a{'\\']")] round_trip True
```

The bare class the finding names — value `a{'\']`, which r1 wrote bare because its copy
of the quote scanner closed the escaped `'` — now takes the quoting branch and
round-trips.

### The seeded fuzz, the three versions side by side

Same alphabet as the finding (`a b , = # ( ) [ ] { } ' " space backslash newline tab`),
seed 7, every value the fuzz generates put through `value.strip().strip("\"'")` so that
it is a value `split_args` could have produced, deduplicated: 109,999 distinct values.
Each is written with `build_call` under a named key and under a positional key and read
back with `split_args` of the same version. `ok` = round-trips, `broken` = written and
read back as something else or not read back at all, `refused` = `ValueError`.

```
$ PYTHONPATH=$PWD /home/y-guo/reproduce/new1/external/probe-env/bin/python "$FIX/fuzz.py"
distinct values 109999

=== key k ===
  r0 ok  52955 broken 54095 refused  2949
  r1 ok  99167 broken  7869 refused  2963
  r2 ok  99192 broken     0 refused 10807
  r0 -> r1: fixed  50536 lost  4324 (broken  4317, refused     7)
  r1 -> r2: fixed     25 lost     0 (broken     0, refused     0)
  r0 -> r2: fixed  50536 lost  4299 (broken     0, refused  4299)

=== key pos0 ===
  r0 ok  52955 broken 54095 refused  2949
  r1 ok  99167 broken  7869 refused  2963
  r2 ok  99192 broken     0 refused 10807
  r0 -> r1: fixed  50536 lost  4324 (broken  4317, refused     7)
  r1 -> r2: fixed     25 lost     0 (broken     0, refused     0)
  r0 -> r2: fixed  50536 lost  4299 (broken     0, refused  4299)
exit=0   (4.0 s)
```

The line that matters is **`r2 broken 0`**: over 109,999 values the writer now writes no
call the reader reads back as something else. Every value is either written and
round-tripped (99,192) or refused by name (10,807). `r1 -> r2` loses nothing.

The 10,807 refusals split by kind, and how many of them r0 round-tripped:

```
$ PYTHONPATH=$PWD /home/y-guo/reproduce/new1/external/probe-env/bin/python "$FIX/refusals.py"
round-2 refusals             10807
  holds both quote kinds     2963 (the ticket's own rule)
  escaped closing quote      7844
of those, r0 round-tripped   4299
  holds both quote kinds     7
  escaped closing quote      4292
exit=0
```

The 2,963 both-quote refusals are the ticket's own rule ("raise `ValueError` naming the
tool, the key and the value when it holds both"); 7 of them are the class the finding
counted as 15 over its own value set. The 7,844 escaped-closing-quote refusals are the
class proved unrepresentable above; 4,292 of them round-tripped under r0, which read
them back only because r0's reader was quote- and escape-blind — the reading the owner
ruled must be fixed.

The 25 values r1 got wrong and r2 gets right, in full:

```
$ PYTHONPATH=$PWD /home/y-guo/reproduce/new1/external/probe-env/bin/python "$FIX/fixed25.py"
value '#\t\\\t\n\\'  round1 broken   "apis.a.b(k='#\t\\\t\n\\')" round2 ok 'apis.a.b(k=#\t\\\t\n\\)'
value '#\n\t\n\\'    round1 broken   "apis.a.b(k='#\n\t\n\\')" round2 ok 'apis.a.b(k=#\n\t\n\\)'
value '#\n\n\\'      round1 broken   "apis.a.b(k='#\n\n\\')"  round2 ok 'apis.a.b(k=#\n\n\\)'
value '#\n \\'       round1 broken   "apis.a.b(k='#\n \\')"   round2 ok 'apis.a.b(k=#\n \\)'
value '#\n\\'        round1 broken   "apis.a.b(k='#\n\\')"    round2 ok 'apis.a.b(k=#\n\\)'
value '#\naa\\'      round1 broken   "apis.a.b(k='#\naa\\')"  round2 ok 'apis.a.b(k=#\naa\\)'
value '# a\na\\'     round1 broken   "apis.a.b(k='# a\na\\')" round2 ok 'apis.a.b(k=# a\na\\)'
value '##\n\\'       round1 broken   "apis.a.b(k='##\n\\')"   round2 ok 'apis.a.b(k=##\n\\)'
value '##[\n]\\'     round1 broken   "apis.a.b(k='##[\n]\\')" round2 ok 'apis.a.b(k=##[\n]\\)'
value '#a\n\n\\'     round1 broken   "apis.a.b(k='#a\n\n\\')" round2 ok 'apis.a.b(k=#a\n\n\\)'
value '#a\n\\'       round1 broken   "apis.a.b(k='#a\n\\')"   round2 ok 'apis.a.b(k=#a\n\\)'
value '#b\n\\'       round1 broken   "apis.a.b(k='#b\n\\')"   round2 ok 'apis.a.b(k=#b\n\\)'
value '#b\\\n\\'     round1 broken   "apis.a.b(k='#b\\\n\\')" round2 ok 'apis.a.b(k=#b\\\n\\)'
value '#bbba\n\\'    round1 broken   "apis.a.b(k='#bbba\n\\')" round2 ok 'apis.a.b(k=#bbba\n\\)'
value '#{\n}\\'      round1 broken   "apis.a.b(k='#{\n}\\')"  round2 ok 'apis.a.b(k=#{\n}\\)'
value '["\\"\n]'     round1 broken   'apis.a.b(k=["\\"\n])'   round2 ok 'apis.a.b(k=\'["\\"\n]\')'
value '[]#\n\\'      round1 broken   "apis.a.b(k='[]#\n\\')"  round2 ok 'apis.a.b(k=[]#\n\\)'
value "\\\n'\\'b"    round1 broken   "apis.a.b(k=\\\n'\\'b)"  round2 ok 'apis.a.b(k="\\\n\'\\\'b")'
value '\\#\n\\'      round1 broken   "apis.a.b(k='\\#\n\\')"  round2 ok 'apis.a.b(k=\\#\n\\)'
value 'a""#\nb\\'    round1 broken   'apis.a.b(k=\'a""#\nb\\\')' round2 ok 'apis.a.b(k=a""#\nb\\)'
value 'aa#\n\\'      round1 broken   "apis.a.b(k='aa#\n\\')"  round2 ok 'apis.a.b(k=aa#\n\\)'
value 'b\n#\n\\'     round1 broken   "apis.a.b(k='b\n#\n\\')" round2 ok 'apis.a.b(k=b\n#\n\\)'
value 'b#\n\\'       round1 broken   "apis.a.b(k='b#\n\\')"   round2 ok 'apis.a.b(k=b#\n\\)'
value "b'#\\'b"      round1 broken   "apis.a.b(k=b'#\\'b)"    round2 ok 'apis.a.b(k="b\'#\\\'b")'
value 'b\\##\n \\'   round1 broken   "apis.a.b(k='b\\##\n \\')" round2 ok 'apis.a.b(k=b\\##\n \\)'
values round 1 got wrong and round 2 gets right: 25
exit=0
```

Two shapes, one cause. Three of them (`["\"\n]`, `\\\n'\'b`, `b'#\'b`) are the finding's
bare class: r1's copy of the quote scanner closed a backslash-escaped quote, wrote the
value bare, and the reader's walk then ran past the call's `)`. The other 22 are the
mirror image: r1's blanket "a `#` makes a value not bare" rule sent a value with a `#`
and a newline after it into the quoting branch, where its trailing backslash ate the
closing quote — the reader closes that call perfectly well with the value bare, because
the comment ends at the newline, and r2 leaves it bare because it asks the reader
instead of guessing.

## ENV-1 and ENV-2, re-verified on the findings' own examples

```
$ PYTHONPATH=$PWD /home/y-guo/reproduce/new1/external/probe-env/bin/python "$FIX/env1_env2.py"
=== ENV-1: a ')' inside a password value ===
tool   apis.spotify.login
args   [('username', 'matthew.blac@gmail.com'), ('password', 'TsivP)G')]
span   (0, 73)
text[span] == the whole call: True
complete_call                : True

=== ENV-1: a '(' inside a password value ===
tool   apis.phone.login
args   [('username', '6639773608'), ('password', 'b270(RP')]
span   (0, 59)
text[span] == the whole call: True
complete_call                : True

=== ENV-1: both values survive build_call and come back ===
  "apis.a.b(username=matthew.blac@gmail.com, password='TsivP)G')" round_trip True
  "apis.a.b(username=6639773608, password='b270(RP')" round_trip True

=== ENV-2: a value with leading or trailing whitespace ===
  'See you at 5 '    -> "apis.a.b(message='See you at 5 ')" re-parsed [('message', 'See you at 5 ')] round_trip=True
  ' hello world'     -> "apis.a.b(message=' hello world')" re-parsed [('message', ' hello world')] round_trip=True
  ' hello world '    -> "apis.a.b(message=' hello world ')" re-parsed [('message', ' hello world ')] round_trip=True
  ' '                -> "apis.a.b(message=' ')"            re-parsed [('message', ' ')]     round_trip=True
  '\t'               -> "apis.a.b(message='\t')"           re-parsed [('message', '\t')]    round_trip=True
  '\nx\n'            -> "apis.a.b(message='\nx\n')"        re-parsed [('message', '\nx\n')] round_trip=True
  'a b'              -> 'apis.a.b(message=a b)'            re-parsed [('message', 'a b')]   round_trip=True
exit=0
```

For both ENV-1 values the span and the argument list are the full call, and
`split_args` and `complete_call` return the same call text. Leading whitespace, trailing
whitespace, both, a whitespace-only value and a tab- or newline-only value all
round-trip (ENV-2).

## The corpus, re-measured

```
$ PYTHONPATH=$PWD /home/y-guo/reproduce/new1/external/probe-env/bin/python "$FIX/corpus.py"
B4 4074 4050 4050
trajectory files 315
None: no api call at all 24 in 13 trajectories
None: other 0 in 0 trajectories
None share of non-null actions 0.59%
argument values 5297 holding a backslash 0
parsed actions whose span is the whole call 4050 of 4050
actions round 2 writes differently from round 1 0
seconds 3.9
exit=0
```

- **B4 is `4074 4050 4050`**, the same three numbers round 1 measured and not the
  ticket's `4074 4040 4040`. `build_call(split_args(x))` round-trips over **every one of
  the 4,050 parsed actions of the corpus**, and every one of those 4,050 spans is the
  whole call (`text[span]` starts with the tool and ends with the call's own `)`).
- **The split of the actions `split_args` returns `None` for is 24 + 0**, not the
  ticket's and errata entry 2's 24 + 10: 24 code blocks that call no api at all, in 13
  of the 315 trajectories, 0.59% of the non-null actions; 0 whose api call never closes
  its parentheses.
- **0 of the 5,297 argument values of the corpus hold a backslash**, so ENV-3's class
  touches no real trajectory today, as the finding said.
- **Round 2 writes every one of the 4,050 calls byte for byte as round 1 did.** The
  change moves no real action; it moves only values the corpus does not contain.

## The acceptance groups, rerun

Every command below was run from the worktree root, interpreters by absolute path,
exactly as the ticket gives them.

**A0 — imports under every interpreter of the `venvs:` map.**
```
1 ['build_call', 'close', 'complete_call', 'judge', 'open', 'speculate', 'split_args', 'step', 'tasks']
1 ['build_call', 'close', 'complete_call', 'judge', 'open', 'speculate', 'split_args', 'step', 'tasks']
1 ['build_call', 'close', 'complete_call', 'judge', 'open', 'speculate', 'split_args', 'step', 'tasks']
exit=0
```
Matches.

**A0b — FAILS on the known defect of the ticket's own script (reported in rounds 0 and 1).**
```
    and _is_type(type, cls, dataclasses, dataclasses.KW_ONLY,
  File "/usr/lib/python3.10/dataclasses.py", line 711, in _is_type
    ns = sys.modules.get(cls.__module__).__dict__
AttributeError: 'NoneType' object has no attribute '__dict__'. Did you mean: '__dir__'?
exit=1
```
The script loads the module with `spec_from_file_location` + `module_from_spec` +
`exec_module` and never registers it in `sys.modules`, which importlib's documented
pattern does before `exec_module`; CPython's `dataclasses._is_type` then dereferences
`sys.modules.get(cls.__module__)` with no null check. The defect is the script's, it
hits any dataclass with postponed annotations, and
`data/environments/__init__.py` is untouched by this fix round. I did not bend the code
to it. The corrected form of the same check, with the one missing line, passes:
```
$ python3 -c "
import sys, importlib.util as u
s = u.spec_from_file_location('env_base', 'data/environments/__init__.py')
m = u.module_from_spec(s); sys.modules['env_base'] = m; s.loader.exec_module(m)
print(m.VERSION, m.StepObservation.__name__)"
1 StepObservation
exit=0
```

**A1.** `None NO_CODE_BLOCK None False`, exit 0. Matches.

**A2.** `REFUSED True True`, exit 0. Matches.

**A3.**
```
[('train', 'a', 1), ('train', 'a', 2), ('train', 'b', 1), ('train', 'b', 2), ('dev', 'd', 1), ('dev', 'd', 2), ('dev', 'e', 1), ('dev', 'e', 2)]
[('dev', 'd', 7), ('train', 'b', 7)]
[]
[('train', 'a', 1), ('train', 'b', 1), ('train', 'c', 1)]
exit=0
```
Matches exactly.

**A4.**
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
exit=0
```
Matches.

**B1 — `tasks` reads the split files in file order.**
```
train 90 82e2fac_1 aa8502b_3
dev 57 50e1ac9_1 4fab96f_3
test 168 3d9a636_1 bde252e_3
REFUSED True
exit=0
```
Matches the ticket's measured values exactly.

**B2 — `split_args` on the three shapes, including the span.**
```
apis.spotify.login [('username', 'a@b.c'), ('password', 'pw')] (6, 57) True
None
('apis.a.b', [('pos0', 'x')], (6, 19))
None
exit=0
```
Matches exactly.

**B3 — `build_call` is the inverse, on the four shapes that break a naive join.**
```
True "apis.a.b(k='')"
True "apis.a.b(k='a, b', 'x=y')"
True 'apis.a.b(username=+1555, \'# c\n  password="P!\')'
True 'apis.a.b(access_token=token, page_index=0)'
exit=0
```
Matches exactly. The third case keeps its quoting branch: its value is a `#` comment
that runs to the end of the text, so the reader never reaches the call's `)` with it
written bare, and `_closes_the_call` says so.

**B4 — the round trip over the real corpus.**
```
4074 4050 4050

real	0m4.114s
exit=0
```
**Differs from the ticket's `4074 4040 4040`** — the change round 1 was asked to make,
unmoved by round 2. Breakdown in the section above.

**B5 — `complete_call`, the legacy cases.**
```
8 of 8
exit=0
```
Matches.

**B6 — the literal rule, no absolute path, no module-level benchmark import.**
```
1
1
1
NO_ABS_PATH
['v1'] {'train': 'train', 'dev': 'val', 'test': 'test'} 1
Traceback (most recent call last):
  File "<stdin>", line 6, in <module>
  File "<stdin>", line 6, in <listcomp>
AttributeError: 'Import' object has no attribute 'module'
exit=1
```
The first five lines match, so the three module-level literals and the
`ast.literal_eval` scan are unaffected by this round's two new module-level functions.
The last block fails on the known defect of the ticket's own script: `a.module` exists
on `ast.ImportFrom` alone, not on plain `ast.Import`, and the attribute access raises
before the `or` can fall back. The file's imports are unchanged by this round. The
corrected form, branching on the node type, runs and confirms the property the check
exists for:
```
module_level_imports ['__future__', 'ast', 'os', 're', 'shutil', 'time', 'pathlib', 'yaml', 'data.environments']
appworld_at_module_level False
exit=0
```

**C2 — `speculate` before `open` refuses, and a second `close` is a no-op.**
```
REFUSED True
CLOSE_TWICE_OK
exit=0
```
Matches.

**C0 — the whole life cycle on one dev task** (appworld venv, CPU, run once at the end).
```
TASK_TEXT True
STEP 'print(1+1)\n' '2\n' None False
NOCODE None NO_CODE_BLOCK None False
ERRKIND Exception True
JUDGE True ['difficulty', 'failures', 'num_tests']
DIR_BEFORE True
DIR_AFTER False
exit=0
```
Matches exactly.

**C1 — `speculate` leaves the world and the clock unchanged.**
```
KEYS ['arg_modes', 'error_kind', 'exec_code', 'exec_ok', 'exec_out', 'spec_s']
OK True None True True
CLOCK_SOURCE 1.633218951523304
CLOCK True
UNPARSABLE ['unparsable_raw'] False Exception
exit=0
```
Matches: `spec_s` is a positive float (1.633 this run, 1.519 measured in the ticket), so
`CLOCK_MONOTONIC` is still in use where `time.time()` would print `0.0`.

**C3 — B0 to B6 rerun after C0/C1.** Same outputs as pasted above; not repeated.

## Decisions this round that the findings did not make

1. **The writer asks the reader instead of carrying a second copy of its rules.** The
   finding asked for `_bare_safe` to gain `_call_close`'s backslash escape. Copying one
   more rule across would have left the copy that produced this finding in the first
   place, so `_bare_safe` and `_quote_value` both put the candidate through
   `_call_close` itself, wrapped in a one-argument call. That one call subsumes the
   copied `#` rule, the copied parenthesis counter and the missing escape rule, and it
   is the reason the fuzz's `broken` column is 0. `_split_args_named` has no walk to
   call, so the writer keeps a model of that reader alone, in `_stays_one_argument`.
2. **A value that needs quoting and ends in an odd number of backslashes is refused by
   name.** No writing represents it (proved exhaustively above), so the choice was
   between a `ValueError` naming the tool, the key and the value, and writing a call
   whose re-parse returns `None`. The ticket already makes the same choice for a value
   that holds both quote kinds, so the refusal follows the rule the ticket set rather
   than inventing one. One case inside this class is writable — `a=b\`, which
   round-trips bare — and it is refused with the rest, because the ticket's quoting rule
   quotes a value that "holds a top-level `,` or `=`" without regard to the key, while
   the reader reads a key off the *first* `=` alone and would give a named value's
   further `=` back untouched. I built the key-aware version, measured it, and reverted
   it: it rescues that class but contradicts the ticket's stated quoting rule and
   rewrites 7 real corpus actions (`password='ZEgU=ep'` becomes `password=ZEgU=ep`).
   Relaxing the `=` rule for a named key is the owner's call, not this round's.
3. **A value that begins or ends with a quote character is still left as is**, for the
   reason measured in round 1: the ticket's `.strip().strip("\"'")` parse rule preserves
   no such value under any writing, and `split_args` produces none (0 of the 5,297
   corpus values). Round 2 does not change that case.
4. **`README.md` is untouched.** The one file this round may edit is
   `data/environments/appworld.py`, and its five annotation lines are unchanged by the
   fix: no import added, no file read or written, same venv.

## Things noticed, for another ticket or for the owner

- The ticket's B4 line and errata entry 2 still carry the pre-round-1 numbers. They are
  listed in this round's return field `ticketTextNowWrong` with the measured
  replacements; the numbers are unchanged from round 1's measurement, re-measured here.
- Ticket 09's `counts.events_skipped_no_call` has one kind of input, not two: only "no
  api call at all", 24 over p1 instead of 34.
- The ticket's own A0b and B6 scripts have the two defects reported in round 0: a module
  loaded by path with no `sys.modules` registration, and `.module` read on an
  `ast.Import` node. Both still fail, both are the scripts' defects, and both are worth
  fixing in the ticket file before `run.py selfcheck` in wave 6 borrows either pattern.
  I did not touch the ticket file.
