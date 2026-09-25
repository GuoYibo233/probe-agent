# T15 — run.py selfcheck

## What was done

Two files touched, exactly as the ticket licenses: `run.py` and `README.md`.

**`run.py`**: added `import ast`, the three parsers (`imports_of`, `literal_of`,
`literal_keys_of`), and replaced ticket 14's `cmd_selfcheck` stub with the full
implementation of the eleven checks in contracts 8.6's order, plus the
`VERSION_HISTORY` strict-shape rule spec section 5 and the ticket's Comments
section both ask `selfcheck` to enforce. Every helper function got a one-line
docstring citing the contract or rule it implements; no docstring, comment or
identifier mentions `legacy/` anywhere (grepped, zero hits).

Requirement by requirement:

- **`selfcheck` subcommand replacing the stub** — done; `cmd_selfcheck` runs all
  eleven checks, prints one line per problem, then `selfcheck: <n> python
  files, <problems> problems`, and returns 1 on any problem, 0 otherwise.
- **The three parsers beside `readme_entries`** — done, right after it in the
  file. `readme_entries` itself is untouched (ticket 14's `D1` and ticket 16's
  skills both depend on its shape).
- **Check 1 (README's file list against the tree)** — `_tree_python_files()`
  walks `run.py` plus the eight named roots; `_check_1` tests coverage both
  ways and existence over every one of `readme_entries`'s 43 entries (not just
  the 31 `.py` ones), with `Path.exists()`, never `is_file()`, so `tests/`
  passes.
- **Check 2 (annotation lines against the real import graph)** — `_check_2`
  builds the whole 31-file import graph once (`_repo_imports`, which is
  `imports_of` restricted to repo files) and its reverse, then applies the
  five-step parse (`_parse_annotation`, `_split_top_level`,
  `_drop_parenthetical`, `_expand_braces`) to every `imports:`/`used by:`
  line, routing the three rule-3 spellings (`by name`, `none (program)`,
  `(as their package)`) to their own tests instead of the plain equality.
- **Check 3 (axis literals)** — `_check_3`: the two ordered tuple comparisons
  (`inject.format` via `literal_keys_of`, `inject.arm` via `literal_of`), the
  two set comparisons (`probe.method`, `data.env`), the three subset checks
  (`data.instructions`, `sample.split`/`inject.split`, `generation.effort`),
  and `probe.method`'s two dict-membership tests against `PROBE_KIND` and
  `MATCH_VERSION`.
- **Check 4 (one `VERSION` per stage-table module, one literal apiece)** —
  `_resolve_versions_entry`/`_stage_table_files` reproduce the ticket's own
  two-step resolution (drop `@stage`/`#TABLE.name`, then expand `{env}`,
  `{method}`, `{probe_score_method}`, `{family}`, `{backbone}` over the
  role-split family lists) without touching `schema._substitute` or
  `schema._entry_parts`. The nine named literals are read off their own
  natural file sets (train methods, agent family modules, probe backbones,
  environment files). `_check_version_and_history` additionally enforces the
  `VERSION_HISTORY` strict shape spec section 5 and the ticket's Comments
  section ask for (keys exactly `2..VERSION`, non-empty `why`, `stale` a
  tuple of `schema.STAGES` names), scoped to the 22 stage-table files — see
  "Decisions" below.
- **Check 5 (`SCHEMA`/`DEFAULTS`/`REQUIRED`)** — `_column_zero_ann_or_assign`
  matches on the target's bare `id`, never `ast.unparse`, so
  `data/trajectory_record.py:95`'s `DEFAULTS["n_inject"] = 0` (a `Subscript`
  target) is not a second match; `_check_5` reads `SCHEMA`'s keys and
  `REQUIRED`'s `frozenset({...})` argument directly off the `ast` nodes, using
  neither `literal_of` nor `literal_keys_of`, and checks `REQUIRED ⊆ SCHEMA`
  for exactly the three named files, `data/probe_input.py` excluded.
- **Check 6 (the two `PROBE_KIND` declarations)** — `_check_6`.
- **Check 7 (`DEFAULT_EFFORT` in `EFFORTS`, or both empty)** — `_check_7`,
  over `models/agent_models/<family>.py` only, per the ticket's explicit
  scoping.
- **Check 8 (`models/table.yaml` row resolution)** — `_check_8`.
- **Check 9 (no `/home/`/`/net/` literal outside `constants/`)** — `_check_9`.
  Its own forbidden-root strings are built by concatenation
  (`"/" + "home/"`) precisely so the check's own source text never contains
  the substring it is looking for — see "Self-review findings" below.
- **Check 10 (`any` files under every venv; family modules under probe+vllm)**
  — `_check_10`, the one check that starts a subprocess, exactly as the
  ticket says.
- **Check 11 (no workflow file stem is a reserved subcommand name)** —
  `_check_11`.
- **The six README corrections** — applied verbatim, each one line replaced
  in place, no line numbers shifted:
  - `:129` `data/training_data.py` `used by:` — the three `train/methods/`
    entries removed.
  - `:197` `models/probe_models/base.py` `used by:` — same removal.
  - `:210` `models/probe_models/service.py` `imports:` — `models/probe_models/base.py
    inside serve()` rewritten to `models/probe_models/base.py (inside serve())`.
  - `:256`, `:263`, `:270` `train/methods/{ctool,cgen,cparam}.py` `imports:` —
    `models/probe_models/base.py` and `data/training_data.py` removed from
    each.

## How it was verified

All commands run from the worktree root,
`/home/y-guo/reproduce/new1-wt/2026-09-19-wave6-T15`, with
`$PR=/home/y-guo/reproduce/new1/external/probe-env/bin/python`.

**D2 — selfcheck's parsers.**

```
$PR -c "... VERSION=3/import os/from data import training_data ..."
```
Output: `3`, then `['data.training_data', 'os']`, then `two matches -> refused: True`.
The `dataclasses` fixture (`from dataclasses import dataclass`) gave
`['dataclasses', 'os']`. All three match the ticket's expectation exactly.

`literal_keys_of`/`literal_of` division of labour on `FORMATS`:
```
run.literal_keys_of('agent/injected_text_formats.py', 'FORMATS')
-> ['note', 'p1_e1', 'p1_e2', 'p2_e1', 'p2_e2']
run.literal_of('agent/injected_text_formats.py', 'FORMATS')
-> SystemExit: selfcheck: agent/injected_text_formats.py: 'FORMATS''s value is
   not a literal (malformed node or string on line 65: <ast.Call object at ...>)
```
`literal_of` refuses `FORMATS` outright (no fallback), exactly as required.

Annotation-line parse table (via the internal `_parse_annotation`, called
directly for this demonstration):
```
train/utils/trainer.py            used by -> ['train/methods/cgen.py', 'train/methods/cparam.py', 'train/methods/ctool.py']
models/agent_models/service.py    used by -> ['agent/run_tasks.py', 'agent/step_without_probe.py']
models/probe_models/base.py       imports -> ['models/__init__.py']   by_name=[('models/probe_models/<backbone>.py', 'by name, inside load()')]
models/probe_models/__init__.py   used by -> ['models/probe_models/base.py', 'models/probe_models/qwen.py', 'models/probe_models/service.py']
```
All four match the ticket's expected parse exactly, including the `jobs/launch.py
starts it as a piece...` prose being dropped on the `service.py` row.

Check 5's structural read (run verbatim, unmodified):
```
data/trajectory_record.py {'SCHEMA': 1, 'DEFAULTS': 1, 'REQUIRED': 1} 12 []
data/training_data.py {'SCHEMA': 1, 'DEFAULTS': 1, 'REQUIRED': 1} 16 []
data/probe_output.py {'SCHEMA': 1, 'DEFAULTS': 1, 'REQUIRED': 1} 9 []
```

Check 4's expansion (run verbatim, unmodified):
```
22 missing: []
```

**D3 — the whole-tree selfcheck.**
```
$PR run.py selfcheck; echo "rc=$?"
```
```
selfcheck: 31 python files, 0 problems
rc=0
```
Matches exactly.

**D4 — each check fires.** All eleven breakages run in a scratch copy under
`/tmp` (never in the worktree), one at a time, each restored by discarding
that scratch copy:

| # | break | message printed |
|---|---|---|
| 1 | deleted `run.py`'s README entry line | `check 1: run.py is a .py file in the tree with no README entry` (plus the two cascading `check 2: run.py has no imports:/used by: line` — expected, since the whole entry is gone) |
| 2 | added `import jobs.registry` to `models/probe_models/base.py` | `check 2: jobs/registry.py used by: README names [...], the graph gives [..., 'models/probe_models/base.py', ...]` and the matching `imports:` line on `base.py` itself |
| 3 | added a sixth `FORMATS` key | `check 3: schema.AXES['inject.format'] (...) != agent/injected_text_formats.py FORMATS keys (..., 'p3_extra')` — fired through `literal_keys_of`, not a parse refusal |
| 4 | added a second column-zero `VERSION` to `data/training_data.py` | `check 4: selfcheck: data/training_data.py: 2 column-zero assignments to 'VERSION', expected exactly one` |
| 5 | added `"not_a_real_column"` to `data/probe_output.py`'s `REQUIRED` | `check 5: data/probe_output.py: REQUIRED names ['not_a_real_column'], which SCHEMA does not declare` — fired through the structural reader, not `literal_of` |
| 6 | changed `PROBE_KIND["cgen"]` to `"classifier"` | `check 6: train/methods/cgen.py's PROBE_KIND 'generator' != eval/utils/probe_eval.py PROBE_KIND['cgen'] 'classifier'` |
| 7 | changed `gptoss.py`'s `DEFAULT_EFFORT` to `"ultra"` | `check 7: models/agent_models/gptoss.py: DEFAULT_EFFORT 'ultra' is not in EFFORTS ('high', 'medium', 'low')` |
| 8 | deleted `qwen3-0.6b-base`'s block from `constants/path_models.yaml` | `check 8: models/table.yaml['qwen3_0pt6b']: result.weights 'qwen3-0.6b-base' is not an alias of constants/path_models.yaml` |
| 9 | added a literal `/net/tokyo100-10g/x` string to `eval/score_run.py` | `check 9: eval/score_run.py: a string literal names an absolute path outside constants/: '/net/tokyo100-10g/x'` |
| 10 | added `import torch` at module level to `eval/utils/probe_eval.py` | `check 10: eval/utils/probe_eval.py: import under .../appworld/venv/bin/python failed: ModuleNotFoundError: No module named 'torch'` (and the same for `eval/method_table.py`, which imports it — both correctly named, both exit 1) |
| 11 | `touch <scratch>/experimental_settings/free.yaml` | `check 11: experimental_settings/free.yaml: stem 'free' is a reserved subcommand name` |

Every one of the eleven fires and exits 1, and each restore was a discard of
that scratch copy (never an edit inside the worktree). Breakage 11's own
`touch` and its later `rm -rf` of the scratch directory were kept in separate
Bash calls, per the ticket's own note about the read-only hook's path-tail
matching (a single call naming `experimental_settings/free.yaml` anywhere
alongside `cp ` or `rm ` anywhere else in the same command is refused by
`.claude/hooks/settings_readonly.sh`, even when the two are unrelated parts of
the command).

**D5 — `--help`.** Unaffected by this ticket's edits (no subcommand list
change); ran anyway to confirm no silent breakage:
```
$PR run.py --help
```
Ten subcommands in the pinned order, `selfcheck   -- the tree's self-consistency
checks` among them, `rc=0`. Matches.

**D6 — `where` over all fourteen (stage, --debug) pairs.** Ran the full sweep
verbatim; all twenty-eight printed as absolute paths under
`/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs[/debug]/<stage>/<12
hex>`, `D6 ok`, exit 0. Matches; no regression from this ticket's `run.py`
edits.

**D7 — the three workflow files' twelve `(setting, debug)` loads.** Ran
verbatim; twelve lines printed, each with a 12-hex key per stage, `D7 ok`,
exit 0. Matches; no regression.

### GPU / main session

None in this ticket, per its own text.

## Commits

- `db856fb` — T15: correct the six README annotation lines the import graph disagrees with
- `bef01b1` — T15: add run.py selfcheck, its parsers, and the eleven checks

## Self-review findings and open questions

- **Check 9 almost flagged itself.** The first implementation wrote the
  literal strings `"/home/"` and `"/net/"` directly into `run.py`'s own
  source (both in the containment test and in the printed message), and
  since `run.py` is one of the 31 files check 9 scans, it failed on its own
  source text. Fixed by building the two forbidden roots from concatenated
  parts (`"/" + "home/"`, `"/" + "net/"`) and rewording the message to not
  repeat the substring; re-verified clean on `run.py`'s D3 pass and still
  correctly named the real breakage in D4's test 9.
- **The `VERSION_HISTORY` strict-shape rule is scoped to the 22 stage-table
  files, not to "every versioned file in the tree" read as a free-standing
  set.** Spec section 5 and the ticket's Comments section both word it as
  "every file with a column-zero `VERSION`"; I resolved that against the
  stage table's own resolution (check 4's own scope) rather than treating it
  as a twelfth, unscoped check, and confirmed by grep that the two sets are
  in fact identical today (22 files carry `VERSION`, and the stage table's
  `versions` tuples, resolved, name exactly those 22 — no gap either way on
  the current tree). If a future file ever carries `VERSION` without being
  named by any stage's `versions` tuple, this scoping would let it skip the
  strict-shape check; flagging this for the owner rather than deciding it
  silently.
- **Not implemented: the "comment block sits directly above it with the
  pinned text" half of the `VERSION_HISTORY` rule.** I implemented the
  structural half (keys `2..VERSION`, non-empty `why`, `stale` a valid stage
  tuple) but not a literal check that the pinned comment text sits directly
  above every `VERSION` line. No acceptance command in the ticket tests this,
  and a naive text-equality check risks false positives on legitimate
  rewording; left as an open question rather than guessed at.
- **Check 2's by-name handling for `models/probe_models/base.py`'s
  `<backbone>.py` placeholder is a single hardcoded branch**, not a general
  rule, because the ticket names exactly one such case in the whole tree. A
  second placeholder-style by-name entry appearing in a future ticket would
  need this branch generalised; noting it rather than building unused
  generality now (YAGNI, per the implementer procedure).
- No acceptance command was edited to make it pass, and no test file was
  added (the ticket names no test seam for this ticket).

## Fix round 1

Worktree `/home/y-guo/reproduce/new1-wt/2026-09-19-wave6-T15-fix1`, branch
`ticket/2026-09-19-wave6/T15` (already existed; checked out rather than
created).

### F1 (critical): VERSION_HISTORY strict-shape check omits the pinned-comment-block requirement

**Root cause.** `_check_version_and_history` implemented the structural half
of the ticket's Comments-section rule (`VERSION_HISTORY` keys exactly
`2..VERSION`, every entry's `why` non-empty, every `stale` a tuple of
`schema.STAGES` names) but never read the source lines above a file's
`VERSION` assignment and compared them against the pinned
"`VERSION rule: read this before you edit this file...`" comment text. The
first round's own self-review disclosed this as "Not implemented," which
per the review protocol is still an open spec-compliance gap, not a
resolved one.

**Fix.** Before touching code, confirmed the block is in fact word-for-word
identical, and sits with no gap, directly above `VERSION` in every one of
the 22 stage-table files (checked programmatically over all 22, not just
the five the finding sampled). Added two things to `run.py`:

- `_VERSION_RULE_COMMENT`, a 10-line tuple holding that pinned text exactly
  as it reads in the tree today.
- `_version_assign_lineno(path)`, which parses the file with `ast` and
  returns the 1-indexed line number of the one column-zero `VERSION`
  assignment, or `None` when there is not exactly one (that mismatch is
  already `_safe_literal`'s own problem elsewhere in the same function, so
  this avoids a duplicate report).
- `_check_version_comment(path)`, called from `_check_version_and_history`
  right after establishing the `VERSION` literal exists: it takes the lines
  directly above that assignment line and compares them, as a tuple, against
  `_VERSION_RULE_COMMENT`. A short block (not enough lines above it to hold
  the pinned text) reports "missing directly above"; a same-length block that
  differs anywhere reports "does not match the pinned VERSION rule comment
  block." Both name the file and the check-4 prefix, matching every other
  check-4 message's shape.

This is a root-cause fix, not a patch: it builds the missing check the
finding names, rather than adding a special case or a bypass around the
existing gap.

### How it was verified

All commands run from the fix worktree,
`/home/y-guo/reproduce/new1-wt/2026-09-19-wave6-T15-fix1`, with
`$PR=/home/y-guo/reproduce/new1/external/probe-env/bin/python` (the
worktree has no `external/`, since those are gitignored symlinks that live
only in the main repo; the interpreter is invoked by its absolute path in
the main repo with the worktree as the working directory).

**New breakage for F1, on the untouched tree first:**
```
$PR run.py selfcheck; echo "rc=$?"
```
```
selfcheck: 31 python files, 0 problems
rc=0
```

**Breakage A — corrupt one word inside the pinned block** (scratch copy,
`data/trajectory_record.py`, "Bump VERSION" -> "Bump the VERSION"):
```
check 4: data/trajectory_record.py: the lines directly above VERSION (line 24) do not match the pinned VERSION rule comment block
selfcheck: 31 python files, 1 problems
rc=1
```

**Breakage B — delete the whole pinned block** (scratch copy,
`models/agent_models/gptoss.py`):
```
check 4: models/agent_models/gptoss.py: the VERSION rule comment block is missing directly above VERSION (line 7)
selfcheck: 31 python files, 1 problems
rc=1
```

Both scratch copies were discarded (`rm -rf`) after use, never edited back
in place.

**Full D2-D7 acceptance suite, rerun to confirm no regression:**

- D2 (all parts: the `VERSION`/`imports_of` fixture, the `dataclasses`
  fixture, `literal_keys_of`/`literal_of` on `FORMATS`, check 5's structural
  read, check 4's 22-file expansion) — every output byte-identical to the
  first round's report.
- D3 — `selfcheck: 31 python files, 0 problems`, `rc=0`. Unchanged.
- D4 — all eleven original breakages re-run in fresh scratch copies (each
  its own `/tmp` copy, discarded whole after use, per the ticket's own
  rule for breakage 11's undo): every one of the eleven printed the exact
  same message as the first round's report, including breakage 4 (the
  double-`VERSION` case), which returns from `_check_version_and_history`
  before reaching the new `_check_version_comment` call and so is
  unaffected by this fix.
- D5 — `--help`'s ten-subcommand block, unchanged, `rc=0`.
- D6 — the fourteen `where` pairs (28 paths), all identical to the first
  round's report.
- D7 — the twelve `(file, setting, debug)` loads, all identical keys,
  `D7 ok`, `rc=0`.

### Commits

- `c21c566` — T15: check 4 also enforces the pinned VERSION rule comment block

### Self-review

- Only `run.py` touched, matching the ticket's two-file license (`README.md`
  needed no further change: the six corrections from round 1 are untouched
  and this fix adds no new annotation lines).
- No docstring, comment or identifier mentions `legacy/` (the fix adds no
  such reference).
- The fix is scoped to F1 alone; no other line from the first round's report
  was touched or re-litigated.
- `_VERSION_RULE_COMMENT`'s ten lines were typed by copying `repr()` output
  of the actual file content, not retyped by hand, so there is no
  transcription risk in the pinned text itself.
