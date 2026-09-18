# Spec: the from-zero build of new1

The tickets in `.scratch/from-zero/issues/` cite this file. It states the rules
every implementer follows; it does not restate a contract. Read it once, then
read your ticket.

## 1. The three documents, and which one wins

| document | what it fixes | a ticket may |
|---|---|---|
| `notes/plans/2026-09-14-structure-from-zero.md`, Part 1 | the file tree: 34 Python files plus the data files | never add, remove, move, split or rename a file |
| `notes/plans/2026-09-17-contracts.md` | every interface that crosses a file boundary: the four on-disk formats, the stage table, the key, the environment base class, the setting schema, the model table, the two service protocols, the registry | never edit this file; cite it by section |
| `notes/plans/2026-09-17-construction-plan.md` | who builds what, in which wave, and what proves it | read section 2 for your folder |

`.scratch/from-zero/contracts-index.md` maps every name in the contracts to the
section that defines it. `.scratch/from-zero/contract-errata.md` records every
place the contracts contradicted themselves and what the build does instead; a
ticket that depends on one names it. When a ticket and the contracts disagree,
**the ticket wins and you say so in your report** — the ticket carries the
errata. When the contracts and a folder plan disagree and the ticket is silent,
the contracts win.

`notes/CONTEXT.md` is the glossary: probe, cut, fire, inject, launch, heartbeat,
piece, refire, verdict, sampler. Two words have one meaning only: **record** is
always the task record on disk, never a line of the registry (that is a
**registry row**); **environment** is always a benchmark, never a venv (a venv is
named by its directory under `external/`).

## 2. The fixed tree

A ticket writes only the files its `## What to do` names. There is no
`utils.py`, no `helpers.py`, no new package, no new module "just for this". A
mechanism with no obvious file goes into the existing file whose tree line best
covers it, and you say where you put it in your report.

The one exception is `tests/`, which is empty by the owner's decision. A ticket
may add a file under `tests/` only for one of the four checks the tree's `tests/`
line names, and only when its own ticket says so. Two of the four are in this
build: `tests/test_registry_concurrent_append.py` (ticket 03) and
`tests/test_packed_loss.py` (ticket 13). Everything else is verified by an
acceptance command, not by a test file.

`legacy/` is read-only. It is where the algorithms to port live. **Nothing in the
new tree imports it, runs it, or is added to it.** Your ticket names the legacy
file and line range for every algorithm you port, and the "not ported" list in
your ticket is binding: a behaviour on that list is not recreated.

## 3. Every file's five annotation lines

Contracts 0.1 gives every code file five lines, in this order and this
punctuation, and `run.py selfcheck` parses them:

```
path/to/file.py — one sentence of what it does.
  imports: a.py, b.py          repo files this file imports (third-party in brackets)
  used by: c.py, d.py          repo files that import this file
  reads:   <format or file>    what it reads off disk
  writes:  <format or file>    what it writes to disk
  venv:    any | appworld | probe | vllm
```

The authoritative text of those five lines, for all 34 files, is contracts 0.2.
**Every ticket copies its own files' entries into `README.md`.** Ticket 14
assembles the whole `README.md` from contracts 0.2 and 0.4 and reconciles what
earlier tickets added. `README.md` is therefore the one file two tickets of the
same wave may both touch; merge conflicts on it are expected and are resolved by
the main session at wave merge, by keeping every ticket's lines. No other file is
shared: two tickets of one wave never edit the same file.

A file whose runtime needs a heavier venv than its import does is written
`any at import, <venv> to run` and keeps the heavy import **inside** the function
that needs it. A file started as a program and imported by nobody says
`used by: none (program)`. A dynamic import is written `used by: <file> (by name)`.

## 4. Venvs, and what `any` means

```
PY_SYS=python3                                                           # 3.10.12, stdlib + PyYAML 5.4.1, no polars, no numpy
PY_PROBE=/home/y-guo/reproduce/new1/external/probe-env/bin/python        # 3.11.15, torch 2.11, transformers 5.14, peft, polars, numpy
PY_AW=/home/y-guo/reproduce/new1/external/appworld/venv/bin/python       # 3.12.13, appworld 0.1.3, pydantic 1.10, polars
PY_VLLM=/home/y-guo/reproduce/new1/external/vllm-env/bin/python          # 3.12.13, vllm 0.26, polars, numpy
```

`venv: any` means the file imports under **every interpreter of the `venvs:` map
of `constants/path_datasets.yaml`** — today those three — using only the standard
library, PyYAML, Polars and NumPy. System `python3` is **not** in that map: it has
neither Polars nor NumPy, so `any` does not include it. A file whose whole import
list is the standard library (`data/probe_input.py`,
`data/environments/__init__.py`, `experimental_settings/schema.py`,
`jobs/registry.py`, `agent/injected_text_formats.py`) is checked under system `python3`
as well, because it costs nothing and its ticket says so.

**Always name the interpreter by absolute path.** `external/` is git-ignored and
is not materialised in a worktree, so a relative `external/probe-env/bin/python`
does not resolve where you work. Run every command from the repo root (in a
ticket, your worktree root).

## 5. What every Python file carries

- **A module docstring whose first line is the file's one sentence** — the same
  sentence as its `README.md` entry. Then, when the file is not `venv: any`, a
  `# venv: <name>` comment line.
- `from __future__ import annotations` at the top, so `str | None` loads under
  3.10 as well as 3.11 and 3.12.
- **`VERSION`, when the file's tree line says it carries one**: assigned at
  module level, at **column zero, exactly once**, to an integer literal, starting
  at `1`. `experimental_settings/schema.py` reads these as source text with
  `ast`, never by importing, so a second column-zero assignment or a computed
  value breaks the key. A class body that re-exposes it writes
  `VERSION = VERSION` indented, which is not a second match. `data/__init__.py`,
  the three `models/.../__init__.py`, `models/__init__.py`,
  `eval/method_table.py`, `jobs/registry.py`, `jobs/launch.py` and `run.py` carry
  **no** `VERSION`.
- **Every module-level literal the loader reads follows the same rule**: column
  zero, exactly once, a plain literal `ast.literal_eval` succeeds on — `STOP`,
  `EFFORTS`, `DEFAULT_EFFORT`, `DEFAULT_DATE`, `NAME`, `END_IDS`, `LORA_TARGETS`,
  `HEAD_LAYER`, `DTYPE`, `INSTRUCTIONS`, `SPLIT_ROLE`, `PROBE_KIND`,
  `CHECKPOINT_META`, `FORMATS`, `ARMS`. No f-string, no `+`, no comprehension.
- **No `/home/` and no `/net/` path anywhere in code outside `constants/`.**
  Paths come from `constants/*.yaml` or from `Path(__file__).resolve().parents[n]`.
  `run.py selfcheck` fails on a literal.
- **English.** Code, comments, docstrings, error messages, argparse help, log
  lines, report titles — all English, per the project CLAUDE.md. The only Chinese
  in the repo is the trigger clause of a skill or agent `description` and the
  parenthesised original term in a `notes/CONTEXT.md` glossary entry.
- **Errors name the thing.** Every refusal names the field, the file, the value
  or the pair it refused on. "Invalid setting" is not a message; "`probe.method`:
  `ctoool` is not one of ('ctool', 'cgen', 'cparam')" is.
- **No citation of `legacy/` in the shipped source.** Your ticket names the
  legacy file and line range for every algorithm you port, and that is where the
  citation lives — in the ticket and in your report, never in a docstring, a
  comment or a variable name. `legacy/` is deleted by ticket 18 and ticket 18's
  `C9` greps the code directories for the word, so a comment reading "ported from
  `legacy/pipeline/...`" becomes a dangling reference to a directory that is
  gone. Say what the code does; say where it came from in the report.

## 6. How a stage program is called

```
<venv python> -m <module> --run-dir <dir> [--piece <i>/<n>]
```

with the repo root as the working directory and **no setting name anywhere on the
command line** (contracts 2.6). `--piece` appears only on a `sample` or `inject`
loop piece. Behind that command the program calls
`schema.load_frozen(run_dir) -> Setting` and reads nothing else: no preset file,
no environment variable, no `models/table.yaml` column that is in the key. A YAML
edit after launch cannot move a running process.

No stage program appends a registry row. The start row is appended by
`jobs/launch.py` for a tmux stage or by `run.py` for a CPU stage, before the
process starts; the finish row by `run.py` on its next walk.

## 7. Acceptance

Your ticket's `## Acceptance` section is a list of shell commands with their
expected output. **Run every one of them, and paste the real output into your
report** beside what the ticket said to expect. A command whose output differs is
a failure, not a note — fix the code or, when the ticket is wrong, say which
command, what the ticket expected, what happened, and why the ticket is wrong.

- Never edit an acceptance command to make it pass.
- Never write a new test file to stand in for a command (see section 2).
- A check the ticket marks **GPU / main session** is not yours. Return BLOCKED
  with the ready-to-run command; an implementer never starts a GPU process, never
  runs `ssh`, and never installs a package.
- `run.py selfcheck` does not exist until wave 6. A ticket in an earlier wave
  lists, under "selfcheck lines that apply later", the rules `selfcheck` will
  check over its files, and the hand-run command that stands in for each until
  then.

## 8. Reporting

Your report says, in this order: which files you wrote; every acceptance command
with its pasted output; every decision you made that the ticket did not make, and
where in the code it is; anything you could not do and why; and anything you
noticed that belongs in another ticket. Do not write a summary document, do not
edit `notes/`, and do not commit — the workflow commits.

## 9. Standing rules of this repo that bite here

- `experimental_settings/*.yaml` and `models/table.yaml` are the owner's files. A
  hook refuses an agent edit (ticket 01 ships the hook, the main session arms it
  after wave 2). **Ticket 01 writes `experimental_settings/*.yaml` and ticket 06
  writes `models/table.yaml`**, both before the hook is armed; no later ticket
  edits either. The hook matches on the path's **tail**, so a temp copy of the
  tree is protected too: an acceptance that needs to break one of them does not
  exist, and an acceptance that copies the tree copies the directory
  (`cp -a experimental_settings "$FIX/"`), never the glob.
- `notes/` is the owner's. An agent appends a `TIMELINE.md` entry only when a
  ticket says so (ticket 18), and ticket 18 also performs the one move the fixed
  tree's `notes/` line requires, `git mv docs notes/docs` — a rename, with no
  file inside it opened or edited.
- `jobs/runs.jsonl` is append-only and `jobs/RESULTS.md` is rendered. Never edit
  either by hand; never make an acceptance command write into the real ones —
  work against a throw-away copy in a temp tree.
- Large outputs go under
  `/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/`, debug runs under its
  `debug/` subtree. Nothing large is written into the repo.
- Complete isolation from `/home/y-guo/ACL2026`.
- Never grep from the repo root: `external/` is a multi-gigabyte clone tree and a
  recursive grep from the root takes over an hour. Name the code directories.
