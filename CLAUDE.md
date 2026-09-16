# new1 project rules (branch from-zero)

This branch is the from-zero rewrite of new1. The tree being built is
`notes/plans/2026-09-14-structure-from-zero.md` (fourth draft) with the
fixes in `notes/plans/2026-09-17-structure-review-synthesis.md`; the
interfaces every file must follow are `notes/plans/2026-09-17-contracts.md`
(written first, before any code); the per-folder build order and
acceptance checks are `notes/plans/2026-09-17-construction-plan.md`.
The state before the rewrite is tag `checkpoint-2026-09-17-before-from-zero`
on branch `main`.

## Layout during construction

- `legacy/` holds the old code (`legacy/pipeline`, `legacy/ops`,
  `legacy/run.py`, `legacy/tests`, `legacy/configs`, `legacy/envs/collect`,
  `legacy/envs/serve_logs`, `legacy/MAP.md`) for reading the algorithms
  only. Nothing imports it, nothing runs it, nothing is added to it. It is
  deleted by the last migration step.
- `notes/` holds gyb's hand-written documents (`TIMELINE.md`, `DATA.md`,
  `WORKPLAN.md`, `METHOD.md`, `CONTEXT.md`, `plans/`, `learn/`, `talks/`).
  Agents read them and never edit them except to append a `TIMELINE.md`
  entry when asked.
- `external/` holds links to the venvs and clones: `external/appworld`
  (the AppWorld clone with its venv at `external/appworld/venv`, Python
  3.12), `external/probe-env` (torch, transformers, peft; Python 3.11),
  `external/vllm-env` (vLLM; Python 3.12). "environment" in this repo
  means a benchmark, never a venv.
- The old rules about `run.py` task registry, `MAP.md`, `ops/`, the
  four-ledger layout and the gpu-run skill's launch command describe the
  old tree and do not apply on this branch until the new `run.py`,
  `jobs/` and the skills are rewritten.

## Everything written into this repo is English (user order, 2026-09-12)

Every file and every new addition is written in English: code, comments,
docstrings, runtime strings, plan documents, ledger entries. Terminology
follows the English terms in the `notes/CONTEXT.md` glossary. The only
Chinese allowed is the trigger-phrase clause in skill and agent
descriptions and the parenthesised original term in glossary entries.

## Iron rules that hold on this branch

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
- Commit before launching any experiment; the recorded HEAD must lead back
  to the code that ran.
- Ancient memory: `notes/plans/archive/` is read only when the user says
  so explicitly.

## Issue tracker and ticket execution

Specs and tickets are local markdown files under `.scratch/<feature>/`
(`spec.md`, `issues/NN-<name>.md`), conventions in
`docs/agents/issue-tracker.md`, status labels in
`docs/agents/triage-labels.md`. Batch execution goes through
`.claude/skills/ticket-run/SKILL.md`; on this branch the role prompts are
the ones the dispatch names (`.scratch/from-zero/prompts/`), whose
hard-rule section matches the new tree.
