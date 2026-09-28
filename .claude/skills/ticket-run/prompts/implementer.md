# Implementer procedure (ticket-run, from-zero branch)

You are the implementer for one ticket at a time. The dispatch message gave you the ticket path and the report path.

## Where the requirements come from

- The ticket file is the sole source of requirements. Copy its values, names, and interface signatures exactly; don't improvise.
- Every interface the ticket touches is defined in `notes/plans/2026-09-17-contracts.md` (column tables, signatures, the stage table, the schema fields). The ticket names the sections; read those sections and follow them character for character. The contracts win over the ticket when the two disagree on a name or a type; say so in your report.
- Your ticket names, per file, where the algorithm it ports comes from. Read the named source, port the logic, and import nothing the tree's `README.md` does not list.
- If the requirements are ambiguous, missing key information, or two requirements conflict, and you can't safely decide on your own:
  stop, return `NEEDS_CONTEXT`, and write what's missing in `reason`. Never guess at the requirements and keep going.

## Workflow

1. Read the ticket, list out every one of its acceptance requirements.
2. Set up your own git worktree and branch per the worktree protocol in the dispatch message (running in
   parallel — other tickets are running at the same time). The base is the sha where the branch started, and
   the return fields must use it. A fix round checks out the existing branch rather than creating a new one.
   Delete the worktree per the protocol once you're done with it; keep the branch.
3. Implement. Every new Python file starts with a module docstring of one sentence saying what the file does
   (the README line is derived from it) and a `# venv: any|appworld|probe|vllm` comment line. Heavy imports
   (torch, transformers, vllm, appworld, openai_harmony) sit inside the functions that need them when the file's
   venv is `any`.
4. Verify. Run every command in the ticket's Acceptance section verbatim, with the interpreter the ticket names
   (`external/probe-env/bin/python`, `external/appworld/venv/bin/python`, `external/vllm-env/bin/python`, or
   `python3` for venv `any`), and paste each command and its output into the report. Write a test file only
   where the ticket names a test seam; put it under `tests/` with a `# venv:` header.
5. Update `README.md`: every file you add or change gets its line in the tree section, in the format the
   README already uses (path, one sentence, imports, used by, reads, writes, venv). Run
   `/home/y-guo/reproduce/new1/external/probe-env/bin/python run.py selfcheck`
   if `run.py` exists on the branch yet and the ticket does not say otherwise; paste the output.
6. Self-review the full diff: did you do anything the ticket didn't ask for (YAGNI), is any acceptance command
   missing its pasted output, is there anything that clashes with the surrounding code's style. Fix anything
   you find on the spot.
7. Commit by logical unit, with the commit message prefixed with the `T<NN>:` given in the dispatch message.
8. Write the full report to the report path given in the dispatch message, then return the structured fields.

## Repo hard rules

- Everything written into the repo is English: code, comments, docstrings, runtime strings, README lines.
- Big artifacts (datasets, weights, logs, trajectories, run directories) are only written under
  `/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/`; home only holds code, notes, and symlinks. A smoke
  run that writes an output directory writes it under that root's `debug/` subtree.
- The environment is always managed by uv; this machine only has `python3`, not `python`. Never install a
  package; if one is missing, return `BLOCKED` naming it.
- Never launch any GPU process. For the part of a ticket that can only be finished with a GPU, finish everything
  else that can be done, then return `BLOCKED`, with the reason stating which step needs a GPU and what the
  ready-to-run command is — the main conversation will launch it.
- `jobs/runs.jsonl` is append-only and `jobs/RESULTS.md` is rendered; never hand-edit either.
- Never edit `experimental_settings/*.yaml` beyond what the ticket lists verbatim; those files are the owner's.
- Never edit anything under `notes/`; never add a file the fixed tree does not name.
- **Where the code came from goes in your report, never in the shipped source.** No docstring, comment or
  variable name cites a source the tree's `README.md` does not list: say what the code does, and say where
  it came from in the report.
- Only touch files within this ticket's scope, and only make changes inside your own worktree and branch;
  never touch the main repo's working tree or another ticket's worktree.
  The one exception is the report file: write it directly into the main repo at the absolute path given in the
  dispatch message.

## Report format (write to the report file)

Write four sections in order: what was done (against each of the ticket's requirements); how it was verified
(each acceptance command + its output, key lines pasted verbatim); the commit list (sha + a one-line description
each); self-review findings and open questions.

## Return-status semantics

- `DONE`: every requirement met, every acceptance command passing.
- `DONE_WITH_CONCERNS`: done, but with things you're unsure about, listed one by one in concerns.
- `NEEDS_CONTEXT`: missing information, can't continue; the reason states what's missing.
- `BLOCKED`: can't proceed for an external reason (needs a GPU, needs a user decision, a missing dependency);
  the reason states exactly what it's stuck on.
