# new1 project rules

## The tree

The tree is fixed and is never changed by an agent (moves, splits and renames
are proposals only): `notes/plans/2026-09-14-structure-from-zero.md` (fourth
draft) with the fixes in `notes/plans/2026-09-17-structure-review-synthesis.md`
is the file list, `notes/plans/2026-09-17-contracts.md` is every interface
that crosses a file boundary, cited by section and never edited, and
`notes/plans/2026-09-17-construction-plan.md` recorded who built what.
`README.md` holds one line per file: what it does, what it imports, who
imports it, what it reads, what it writes, and its venv — read it before
touching a file, and update the file's own line whenever you change it.

The code layers are `constants/` (the fixed paths and lookups), `data/`
(formats and the probe input builder), `experimental_settings/` (the setting
schema and the setting files themselves), `models/` (the agent and probe
model modules and the two services), `agent/` (the collection loop),
`train/` and `eval/` (the method files and their shared libraries), `jobs/`
(the registry and the launcher), and `run.py` at the root, the one entry
point. The old pipeline's read-only reference code has been removed.

`notes/` holds gyb's hand-written documents: `notes/TIMELINE.md`,
`notes/DATA.md`, `notes/WORKPLAN.md`, `notes/METHOD.md`, `notes/CONTEXT.md`,
`notes/plans/`, and `notes/docs/` (moved whole from the repo root). Agents
read these and never edit them, except to append a `notes/TIMELINE.md` entry
when asked.

`external/` holds links to the venvs and clones: `external/appworld` (the
AppWorld clone with its venv at `external/appworld/venv`, Python 3.12),
`external/probe-env` (torch, transformers, peft; Python 3.11),
`external/vllm-env` (vLLM; Python 3.12); nothing under it is in git.
"Environment" in this repo means a benchmark, never a venv.

## One command

Every stage is entered through `run.py`, never by calling an underlying
module by hand. Ten subcommands are reserved: `ls`, `where`, `find`, `kill`,
`refire`, `retry`, `table`, `free`, `sync`, `selfcheck` (`run.py --help`
lists them). Any other first word names a workflow file's stem, and a walk
is:

```
external/probe-env/bin/python run.py <workflow> <setting> [<setting> ...] [--debug] [--allow-dirty] [section.field=value ...]
```

which freezes the setting, takes the launch gate, and walks that setting's
stage list, one launch per named setting or sweep child. `run.py ls` reads
progress and verdicts on demand, computed fresh from each run's heartbeat
files; there is no background process and nothing to poll for freshness.

## GPU runs go through the gpu-run skill

An agent never starts a GPU process. A step that needs a GPU is returned as
`BLOCKED` with the ready-to-run command, and the main conversation launches
it through the gpu-run skill (`.claude/skills/gpu-run/SKILL.md`).

## Records, five layers

Direction is `notes/TIMELINE.md`, a person's own words, append-only, and an
agent appends an entry only when asked. Numbers are `jobs/runs.jsonl`
(append-only, one JSON object per stage run) rendered into `jobs/RESULTS.md`
by `jobs/registry.py`; neither is ever hand-edited. Data settings are
`notes/DATA.md`. The plan is `notes/WORKPLAN.md`, overwritten in place. Raw
data lives on NFS. These five layers do not live in one place, and that is
by design: the registry is the numbers, `notes/` is the person's own record
of why.

**The primary key is the run key**: the run directory name, the tmux session
name, the registry row's `run_id` and the commit message that closes out a
result all carry the same `<stage>-<key>` string. There is no `run_id` typed
separately in four places; there is one key, computed once, that names all
four.

## `experimental_settings/` and `models/table.yaml` are gyb's

A hook refuses an agent edit to `experimental_settings/*.yaml` and to
`models/table.yaml`: both change what a setting produces, so both are the
owner's files, and an agent proposes a change to either as a task instead of
editing it. The hook also refuses any Bash command whose text carries one of
these files' names together with a write word (a redirect, `tee`, `cp`,
`mv`, `sed -i`, ...), so writing `CLAUDE.md` itself is always done with the
Write tool, never with a Bash heredoc — a heredoc into `CLAUDE.md` is refused
because its text names `experimental_settings` and `models/table.yaml`
together with redirects.

## Iron rules

- Large outputs go to the net disk:
  `/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/` (mirroring this
  directory's structure). Home keeps code, notes, and symlinks. Model
  weights live under `/net/tokyo100-10g/data/str01_01/y-guo/models`.
- Environments are managed with uv, always. This machine has `python3`,
  not `python`.
- Complete isolation from `/home/y-guo/ACL2026`: never read or write its
  data, code, or results.
- No guessing about data results: without having read the output file or
  the code that produced a number, make no judgment or interpretation
  about it; report results as facts only, no praise, no advice on which
  data is convincing.
- Subagents and implementers never start a GPU process; a step that needs
  a GPU is returned as BLOCKED with the ready-to-run command, and the main
  conversation launches it.
- Records are never edited by hand: `jobs/runs.jsonl` is append-only and
  `jobs/RESULTS.md` is rendered.
- `notes/` is gyb's; an agent reads it and never edits it, except to append
  a `notes/TIMELINE.md` entry when asked.
- Commit before launching any experiment; the recorded HEAD must lead back
  to the code that ran.
- Ancient memory: `notes/plans/archive/` is read only when the user says
  so explicitly.
- Everything written into this repo is English: code, comments, docstrings,
  runtime strings, plan documents, ledger entries. Terminology follows the
  English terms in the `notes/CONTEXT.md` glossary. The only Chinese allowed
  is the trigger-phrase clause in skill and agent descriptions and the
  parenthesised original term in glossary entries.

## Issue tracker and ticket execution

Specs and tickets are local markdown files under `.scratch/<feature>/`
(`spec.md`, `issues/NN-<name>.md`), conventions in
`notes/docs/agents/issue-tracker.md`, status labels in
`notes/docs/agents/triage-labels.md`. Batch execution goes through
`.claude/skills/ticket-run/SKILL.md`, whose role prompts are
`.claude/skills/ticket-run/prompts/`.
