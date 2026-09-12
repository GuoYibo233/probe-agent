# new1 project rules

## Everything written into this repo is English (user order, 2026-09-12)

Every file and every new addition is written in English: code, comments,
docstrings, runtime strings (errors, exit messages, argparse help, log lines,
report titles), plan documents, and new ledger entries. Terminology follows the
English terms in the `CONTEXT.md` glossary
(probe / cut / fire / inject / launch / heartbeat / sampler / verdict / piece / refire).
The whole repo was translated to English in one pass on 2026-09-12, including
the ledgers and the archive; nothing on disk is Chinese any more, with two
allowed exceptions. First, the `description` field of each skill and agent
definition ends with one clause of Chinese trigger phrases, because those
phrases route Chinese requests to the right skill. Second, each `CONTEXT.md`
glossary entry keeps the original Chinese term once in parentheses after its
English head term, because the glossary is the map from the words the user
says in chat to the canonical English terms. The user speaks Chinese in chat;
that never changes the language of a file.

## GPU jobs: the only entry is the gpu-run skill

Any program that uses a GPU (training / inference / probe / vLLM, no matter how
small) goes through the full life-cycle pipeline in
`.claude/skills/gpu-run/SKILL.md`:
probe the cards -> pick cards -> smoke -> commit before launch -> `launch`
(tmux + registration in three places) -> hand over the monitoring command ->
the sampler takes over verdicts and escalation -> wrap-up (report / record
numbers / release / deregister / commit) or interruption.
Hand-rolled ssh/nohup launches that bypass it are forbidden.

- Launch and registration collapse into one command, `python3 run.py launch`
  (card probe / tmux / liveness check / three registrations in one go).
- Cluster slow variables (driver / CUDA / pitfalls): `ops/gpu_state.md`
- Job ledger: `ops/jobs.json`. `launch` registers automatically; wrap-up
  deregisters with `python3 run.py gpu-jobs finish`; `gpu-jobs register` is
  only for backfilling hand-rolled launches. Never edit the file body by hand.
- Self-service monitoring: `python3 run.py gpu-jobs watch`; the web page
  `http://localhost:8377` (ssh port forward) is served by the long-running
  sampler `python3 run.py sampler`. No sampler, no web page.
- Free cards right now: `python3 run.py gpu-jobs free` (never trusts cached
  occupancy).
- Outputs pinned to code: the launcher writes `RUNMETA.json` (commit + argv +
  dirty list) into the output directory automatically; a hand-rolled launch
  must backfill it with `python3 run.py runmeta <output dir> --cmd '<full command>'`.

## Probe pipeline: the whole chain goes through the probe-pipeline skill

To chain collect/annotate/train/eval into one batch (new dataset / new model /
a matrix), use `.claude/skills/probe-pipeline/SKILL.md`: define the batch ->
collect -> write code -> two acceptance lines -> build data -> smoke -> train
-> evaluate in dependency order -> matrix -> wrap-up -> **write back into the
skill**. A single GPU job still uses only gpu-run; this skill manages the whole
chain and hands each GPU step to gpu-run.

**Extending the pipeline also enters here**: adding a model / an environment /
a training method (a new cell) / a split method. The change list is in
`references/extending.md` (section 5, the table of silent failure points, is
required reading). **After extending, write the skill back per Phase E**;
without the write-back the next person gets the old map.

## Running tasks: always enter through run.py

Every task in the registry (collect / annotate / train / eval / replay
injection / execute / live run, CPU or GPU) is entered through `run.py` at the
repo root; calling the underlying scripts directly is forbidden:
- CPU tasks: `python3 run.py <task> [args...]` runs directly; the interpreter
  is set by the registry.
- GPU / launch-type tasks: `python3 run.py show <task>` prints the command; the
  launch itself still goes through the gpu-run skill. `show` applies the
  dirty-tree gate to launch-type tasks too (`--allow-dirty` bypasses it); the
  three ledger files and the locks (jobs.json / runs.jsonl / RESULTS.md /
  *.lock) do not count as dirty.
- Multi-step flows use `python3 run.py recipe <name>`; progress is in
  `run.py status`.
- A task missing from the registry is added to TASKS/RECIPES before it runs
  (one-off launchers stay out of the registry per the 2026-08-02 ruling, the
  only exception).
- Extension code and the registry update land in the same commit; run
  `python3 run.py selfcheck` before delivery.

## Records: four ledgers plus raw data, primary key run_id

Every experiment leaves a trace, in five layers (four ledgers + raw data); do
not mix them:

| Layer | File | Who writes | Which question it answers |
|---|---|---|---|
| Direction | `TIMELINE.md` | a person, append only | why it was decided this way at the time |
| Numbers | `ops/runs.jsonl` -> `RESULTS.md` | `ops/record.py` | what the data looks like |
| Data settings | `DATA.md` | a person, updated with each data version | how this batch of data was built |
| Plan | `WORKPLAN.md` | a person, overwritten | what comes next |
| Raw data | NFS, not in git | experiment scripts | where the data itself lives |

- **Go through the `DATA.md` checklist before starting a new experiment.**
  Every item there corresponds to a pitfall already hit.
- `DATA.md` records settings and definitions only, **no conclusions**;
  conclusions belong to `RESULTS.md`, otherwise it grows into a second ledger.
- The code map is `MAP.md`: what each program does and how to use it. Adding a
  program updates its line.
- `run.py launch` calls `record start` automatically (captures git HEAD); at
  wrap-up, `run.py record finish` adds the numbers by hand. Both steps are
  written into Phase 4 / 6a of the gpu-run skill; following the pipeline means
  nothing is missed.
- `RESULTS.md` is a rendered product, **never edit it by hand**; `runs.jsonl`
  is append-only. The one-time English translation of both on 2026-09-12 is the
  only historical exception and is recorded in `TIMELINE.md`.
- `WORKPLAN.md` is the current plan and gets overwritten; `TIMELINE.md` is the
  decision history and is never overwritten. The two roles never swap. When an
  experiment result changes any judgment in WORKPLAN, add a TIMELINE entry.
- run_id is identical in four places: raw data directory name / tmux session /
  ledger name / commit message.

## Ancient memory: records from before 2026-08-20 are not read by default (user order, 2026-09-12)

The whole `plans/archive/` directory is ancient memory: plans, reports, and
reviews from before 2026-08-20, plus the 2026-08-02 to 2026-08-18 entries moved
out of `TIMELINE.md` (`plans/archive/TIMELINE-2026-08-02-to-2026-08-18.md`).
Read it only when the user explicitly says "check the ancient memory" or names
an archived file; otherwise do not read it, cite it, or use it to answer
questions. When an answer needs those records, say "the evidence is in the
ancient memory" and stop until the user speaks. Number rows dated before
2026-08-20 in `ops/runs.jsonl` and `RESULTS.md` are not moved (the ledger is
append-only, the rendered product is not hand-edited). Entries with old date
stamps in `METHOD.md` and `CONTEXT.md` are active rules and do not count as
ancient memory.

## Version control

- This directory is a git repository (created 2026-07-29, no remote).
- Repository boundary: code / notes / statistics go in; virtual environments,
  third-party clones, raw trajectories, model weights, and logs stay out (see
  `.gitignore`).
- **Commit before launching an experiment**: the HEAD stored in a record leads
  back to the real code only when the working tree was clean.

## Iron rule: no guessing about data results

Without explicit user permission, none of these three things happens:

1. **Without having read the actual output file or code, make no guess,
   judgment, or interpretation about a data result.** That includes
   attribution, conclusions, and speculated mechanisms. Counterexample: w2 is
   worse than w0, and without reading any log the GPU was blamed. To explain a
   number, first read the file that produced it (log / jsonl / eval output)
   and the code that ran it; if it cannot be read, say so and stop there.
2. **Give no advice of the kind "which data is convincing" or "how the paper
   should tell the story".**
3. **Do not praise** the user's conclusions, questions, or data results.

Report experiment results as facts only, with no commentary. This is the same
discipline as "`DATA.md` records settings, not conclusions" and "facts and
interpretation are separated, facts first".

## Other iron rules

- Complete isolation from `/home/y-guo/ACL2026`: never read or write its data /
  code / results (sharing hardware is fine).
- **Large outputs go straight to the net disk** (iron rule since 2026-08-01,
  after the home quota filled up): training outputs / raw trajectories /
  datasets / checkpoints all live under
  `/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/` (mirroring this
  directory's structure); home keeps only code, notes, and symlinks.
- Environments are managed with uv, always.
- Model weights download to `/net/tokyo100-10g/data/str01_01/y-guo/models`,
  never to /home.

## Agent skills

### Issue tracker

Specs and tickets are local markdown files: one directory per feature,
`.scratch/<feature>/`, with the spec in `spec.md` and tickets in
`issues/NN-<name>.md`. Conventions are in `docs/agents/issue-tracker.md`.

### Triage labels

Ticket status uses the five default label strings (needs-triage / needs-info /
ready-for-agent / ready-for-human / wontfix), written on the ticket file's
Status line. The mapping is in `docs/agents/triage-labels.md`.

### Ticket execution

Batch execution of the tickets in `.scratch/<feature>/issues/` has one entry,
`.claude/skills/ticket-run/SKILL.md`: the main session groups tickets into
waves by Blocked by -> pre-check + commit before launch -> one workflow per
wave (`wave.js`; tickets in a wave run in parallel, each on its own worktree
and branch; the implement-review-fix loop is capped at 5 rounds in the script)
-> branch merge and accounting ruling -> final review of the whole branch.
Subagent models are fixed to sonnet/opus; implementers never start GPU
processes (they return BLOCKED and the work goes through gpu-run).

### Domain docs

Single-repo layout: the glossary is `CONTEXT.md` at the repo root, and
architecture decision records live in `docs/adr/`. Reading rules are in
`docs/agents/domain.md`.
