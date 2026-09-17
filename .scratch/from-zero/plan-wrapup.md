# Folder plan: wrapup (the end of construction, the smoke list, the migration)

Planner folder: **wrapup**. Written 2026-09-17 against
`notes/plans/2026-09-14-structure-from-zero.md` (Part 1 tree, fixed),
`notes/plans/2026-09-17-contracts.md` (Parts 0.2, 0.4, 1.5, 1.7, 2.1, 2.3, 2.5,
2.6, 3.4, 5.4, 5.6, 5.7, 6.3, 8.0, 8.4, 8.5, 8.6, 9(a), 9(c), 9(d)),
`notes/CONTEXT.md`, and the four files this folder rewrites.

This folder owns no Python file. The tree's 34 Python files belong to the other
folders; what is listed here is the end of construction: the acceptance walk,
the GPU smoke list handed to the main session, the migration (delete `legacy/`,
clean `.gitignore`, retire the old commands from the skills, the agents and
`CLAUDE.md`), and one `notes/TIMELINE.md` entry.

---

## 1. Files

Nothing in the fixed Python tree is added, removed or edited by this folder. The
files below are the repo's agent-facing documents and its version-control
boundary. None is a Python module, so the "venv / signatures / imports / used by"
annotations of contracts 0.1 do not apply to them; in their place each entry
names **what the file must say**, **which contract section it is copied from**,
**which old file and line range it replaces**, and **what is not carried over**.

### 1.1 `.claude/skills/gpu-run/SKILL.md` — rewritten in place

One sentence: the sole entry point for starting a GPU run in new1, rewritten so
that its whole lifecycle is `run.py`'s stage walk instead of the retired
`gpu-jobs` / `record` / sampler machinery.

What it must say, phase by phase (each phase cites the contract section the
builder copies from):

| phase | content | contract |
|---|---|---|
| 0 | read `.claude/skills/gpu-run/references/gpu_state.md` (slow variables only: drivers, CUDA, the alias dedupe, mixed card types) | tree line for that file |
| 1 | `run.py free` — free cards per host over `constants/path_outputs.yaml`'s `hosts:` list, probed now, never cached, under the busy test of 2.5 | 8.6, 2.5, 6.3 |
| 2 | commit before launching; the dirty-tree gate lives in `jobs/launch.git_state(run_dir, allow_dirty)` and refuses without `--allow-dirty`, which writes `dirty.patch` into the run directory; `jobs/runs.jsonl`, `jobs/RESULTS.md` and `*.lock` never count as dirty | 2.5, 1.5 |
| 3 | the smoke is `--debug` on the same setting, not a hand-shrunk copy: `debug.yaml` lays sizes over any setting, the model, the tuning and the code path stay the same, and `debug: true` enters the key so a debug run can never be mistaken for or reused by a real one | 5.6, 3.4, 9(c)#8 |
| 4 | one command: `run.py <workflow> <setting> [--debug]`. It walks the workflow's stage list, freezes `settings.yaml` / `settings_diff.yaml`, takes `runs.jsonl.lock` across the git gate, the launch gate, the attach test, the card reservation, the port assignment and the start-row append, releases it, starts the service pieces, runs the probe service's `check` client for an `inject` run, then the loop pieces — and **stops**, printing the monitoring command. A GPU stage is never waited on | 9(c)#1, 8.1, 8.6, 2.3, 7.2 |
| 5 | monitoring is `run.py ls [workflow]`: one folded line per run with the six verdicts (`done`, `dead`, `suspected stall`, `warming up`, `slowed`, `healthy`), the progress pair, the heartbeat age, sessions and cards, and the flag column (`edited`, `behind`, `consumed`, `split`, `pinned`, `dirty`, `debug`, `orphan`). A person looks when they want to; nothing patrols | 8.5, 8.6, 9(a)#13 |
| 6a | wrap-up is re-running the same `run.py` command: it writes `done.json` with the certified `pairs`, appends the finish row, **tears the service pieces down**, and walks on to the next stage. Numbers reach `jobs/RESULTS.md` through `done.json` -> the finish row -> the render; nothing is typed in. Then `run.py table [workflow]` for the backbone x method table, and one commit carrying `jobs/runs.jsonl` and `jobs/RESULTS.md` with the key in the message | 2.3, 1.5, 8.2, 8.6, 9(a)#37 |
| 6b | interruption: `run.py kill <workflow> <setting> <stage>` (writes the `killed` finish row, refuses while another live run is attached to this run's service); a dead piece is `run.py refire <workflow> <setting> <stage> --piece i` (liveness-refusal first, claims released, cards re-probed, a launch entry appended, a warning when that piece has been launched before — **no quota**); "start fresh" is `run.py retry <workflow> <setting> <stage>` | 8.6, 2.3, 2.4, 9(a)#39 |
| hard rules | `jobs/runs.jsonl` is append-only and `jobs/RESULTS.md` is rendered — never hand-edited; `run.py` and `jobs/launch.py` refuse to run on any host but `login_host`; an agent never starts a GPU process and returns BLOCKED with the ready-to-run command; one key is one directory and `run.py where` prints it | 8.6, 3.4, branch CLAUDE.md |

Old file and line ranges replaced: `.claude/skills/gpu-run/SKILL.md` lines 19-26
(fixed paths), 27-40 (Phase 0-1), 41-67 (Phase 2-3), 68-151 (Phase 4, the
`run.py launch` receipt and the three registrations), 152-182 (Phase 5, the
sampler and the incident agent), 183-217 (Phase 6a), 218-225 (Phase 6b), 226-236
(hard rules) — that is the whole file; it is rewritten, not patched.

**Not carried over** (each named in the new file's one-line "what is gone"
list, so a reader who remembers the old command finds out why): `run.py gpu-jobs
free/register/finish/watch/json`, `run.py record start/finish`, `run.py launch`
with `--run-id/--track/--piece host:gpus`, `launch-probe` / `launch-eval`,
`run.py runmeta` and `RUNMETA.json` (its content is `meta.json`'s `launches`,
1.5), `ops/jobs.json`, `ops/runs.jsonl`, `ops/gpu_state.md`, the resident
sampler and `python3 run.py sampler`, the web page `http://localhost:8377`, the
sampling history, `incidents.jsonl` and the incident agent, the escalation
line's automatic consequence, and the one-refire-per-piece quota
(9(a)#13, #26, #39; 8.5's closing paragraph).

Companion files in the same skill directory:

- `references/gpu_state.md` — **kept** (the tree names it). Edited: lines 1-46
  (the sampler / ledger / cron / port-8377 block and the "restart the resident
  session" notes) are deleted; lines 47-97 (the hardware and driver table, the
  six known traps, the machines outside the pool) are kept verbatim, because
  they are the measured slow variables the tree asks this file to hold.
- `references/launch-methodology.md` — **deleted**. Card picking, sharding and
  what `launch` does are now contract text (3.4's placement rules, 2.3's piece
  rule) and are not restated in a skill.
- `references/monitor-methodology.md` — **deleted**. Its content is the
  sampler's verdict rules, which are now `jobs/registry.py`'s pure functions
  (8.5) with `DEFAULTS` as the one home for the numbers.
- `scripts/gpu_status.sh` — **deleted**. `run.py free` replaces it (8.6), and a
  second card probe is a second copy of 2.5's busy test.

### 1.2 `.claude/skills/probe-pipeline/SKILL.md` — rewritten in place

One sentence: the entry point for running or extending the whole probe chain,
rewritten around the fact that the chain is now one `run.py` call over a
workflow file's stage list.

What it must say:

1. **The chain is a workflow file.** `experimental_settings/train_probe.yaml`
   has `workflow: [sample, build, train, eval]`; `run.py train_probe <setting>`
   walks it. There is no per-stage command table any more: every stage program
   is called `<venv python> -m <module> --run-dir <dir> [--piece i/n]` by
   `run.py` or `jobs/launch.py`, never by a person (2.6). A batch of related
   experiments is the `sweep:` keyword inside one named setting, not a script
   (5.5, tree line for `jobs/`).
2. **Who writes what.** The YAML files are gyb's; an agent reads them and never
   edits them (a hook refuses). An agent proposes a named setting as a task.
   `schema.py` is code and is edited for a new field or a new axis value, with a
   default that reproduces the old behaviour (tree line for
   `experimental_settings/`, 3.3).
3. **The gates are in the programs.** The old `references/gates.md` numbering
   (G1-G24) is retired: every gate is now held by the stage that can fail it and
   is listed in contracts 2.5 — `build`'s record completeness, abort share,
   call round-trip, split membership, `max_examples` per split; `train`'s
   alignment gate; the generator eval's shared-build-key gate; `inject`'s two
   `run.py`-held gates; `score`'s same-setup and baseline-pair gates; the launch
   gate and the card reservation.
4. **The acceptance of any chain change is the `--debug` walk of its workflow
   file**, plus `run.py selfcheck` before delivery (principle 4, 8.6). Section 4
   of this plan is that walk.
5. **Extending.** The four places a file is added are
   `data/environments/<env>.py`, `models/agent_models/<family>.py`,
   `models/probe_models/<backbone>.py`, and the pair
   `train/methods/<m>.py` + `eval/methods/<m>.py` (0.3). What each extension
   touches is contracts 0.4's table, and the recipe lives in `README.md`. This
   skill **points at both and keeps no copy** — the old `references/extending.md`
   existed because there was no single table; there is one now.
6. **Write-back.** Phase E's "write the new method back into the skill" is
   replaced by: the new file's five annotation lines go into `README.md` in the
   same commit, `run.py selfcheck` proves them against the real import graph, and
   a new axis value is registered in `schema.py` before any YAML may use it
   (0.1, 8.6, the tree's two recurring rules).

Old file and line ranges replaced: `.claude/skills/probe-pipeline/SKILL.md`
lines 18-47 (the five-stage/four-phase shell, the companion documents, the
`run.py` registry paragraph) and every phase below it — the whole file.

**Not carried over**: the `run.py` task registry (`list` / `show` / `recipe` /
`status` / `selfcheck`'s old meaning), `CELLS` / `EVAL_CELLS`, `MAP.md`, the
`<BATCH>`/`<DATA_ROOT>` variable table, `pipeline/configs/*.json` annotate
configs, collect manifests, placement tables, the presets
(`configs/presets/`, `sweep_preset`, `serve_preset`), and the `DATA.md §7`
pre-flight checklist reference (the checks it lists are now loader refusals in
5.7 and stage gates in 2.5).

Companion files: `references/extending.md`, `references/gates.md`,
`references/invariants.md`, `references/stage-commands.md` — **all four deleted**
(their content is 0.4, 2.5, 3.3 + 2.2, and 2.6 respectively; a second copy in a
skill is a copy that rots).

### 1.3 `.claude/skills/exp-status/SKILL.md` — edited, not rewritten

One sentence: the "where does this project stand" skill keeps its whole method
and only has its ledger paths and its number sources moved to the new tree.

Edits, by line:

- line 8 (`description`) and lines 145-151 (the read list): `TIMELINE` ->
  `notes/TIMELINE.md`; `RESULTS.md` -> `jobs/RESULTS.md`; `ops/runs.jsonl` ->
  `jobs/runs.jsonl`; `ops/jobs.json` -> deleted, replaced by
  "`run.py ls` for what is running now" (there is no separate job ledger, 8.6);
  `plans/` -> `notes/plans/`; `plans/PLAINWORDS.md` -> `notes/plans/PLAINWORDS.md`.
- lines 10, 40, 129, 135, 138, 194, 210, 445: the `plans/STATUS_*.md` path ->
  `notes/plans/STATUS_*.md`.
- line 46: `plans/archive/...` -> `notes/plans/archive/...`, and the ancient-memory
  rule is restated (that file is read only when gyb says so).
- line 508: "never touch `RESULTS.md`" -> "never touch `jobs/RESULTS.md`; it is
  rendered from `jobs/runs.jsonl` by `jobs/registry.py`" (8.6).
- line 511: unchanged in substance (`notes/WORKPLAN.md`, `notes/TIMELINE.md`).
- A new sentence in the read list: a run's own numbers are in its
  `done.json` (`metrics` and `report`, 1.5) and reach the finish row verbatim, so
  a status pass reads `jobs/runs.jsonl` and the named report file and never
  parses a training log.

**Not carried over**: `ops/jobs.json`, the sampler's history as a source, and the
"which cells are still empty" matrix language that assumed `CELLS` (the table is
now `run.py table`, 8.6).

### 1.4 `.claude/agents/gpu-runner.md`, `.claude/agents/job-monitor.md`, `.claude/agents/env-runner.md`

Beyond the three skills the folder assignment names, these three agent
definitions carry the same retired commands and would otherwise be the last
place in the repo telling an agent to type `run.py gpu-jobs` or to read a
sampler that no longer runs. They are in scope for the same reason and no other.

- `gpu-runner.md` (lines 28-29, 43-46, 72-73, 81-90, 112, 141): its launch block
  becomes `run.py <workflow> <setting>`; the three-ledger registration paragraph
  becomes one sentence (the start row, `meta.json` and `settings.yaml` are
  written by the launcher inside one lock hold, 8.6); `--refire` becomes
  `run.py refire ... --piece i`; the allowlist sentence keeps its meaning with
  the new paths (`jobs/runs.jsonl`, `jobs/RESULTS.md`, `*.lock`, 2.5).
- `job-monitor.md` (lines 21, 32-36, 46-54, 65-66, 79): its whole source of truth
  changes from `run.py gpu-jobs json` + the sampler to `run.py ls`. The incident
  paragraph (lines 46-54) is deleted; there is no incident agent (9(a)#13).
- `env-runner.md` (lines 82-84): the `run.py list` registry sentence is deleted;
  a CPU stage is started by `run.py` itself (2.3) and there is no task registry.

### 1.5 `.claude/skills/{handoff,paper-write,ticket-run}` — path-only edits

Same defect, smallest possible change; no method is touched.

- `handoff/SKILL.md` lines 45, 51, 60: `run.py gpu-jobs json` and the sampling
  history -> `run.py ls`; `tail ops/runs.jsonl` -> `tail jobs/runs.jsonl` (rows
  with a start and no finish are `registry.open_runs()`, 8.0).
- `paper-write/SKILL.md` lines 32, 60: `ops/runs.jsonl` -> `jobs/runs.jsonl`,
  `RESULTS.md` -> `jobs/RESULTS.md`; "traceable to a run_id" keeps its meaning
  (the run_id is still the primary key of a registry row, 8.1).
- `ticket-run/SKILL.md` lines 47, 140 and `ticket-run/prompts/implementer.md`
  lines 22, 30-31, 38: the "run.py registry three-piece update" hard rule is
  replaced by the branch rule already written for this rewrite — the file's five
  annotation lines go into `README.md` and `run.py selfcheck` proves them; the
  `MAP.md` sentence is deleted (there is no `MAP.md`); the ledger sentence takes
  the new paths. The four role prompts under `.scratch/from-zero/prompts/`
  (`implementer.md`, `reviewer.md`, `re-reviewer.md`, `final-reviewer.md`),
  written for this branch in commit `f28474c`, **replace** the copies under
  `.claude/skills/ticket-run/prompts/`, so the branch stops having two versions
  of the same prompt.

### 1.6 `CLAUDE.md` (repo root) — rewritten in place

One sentence: the root rules file stops describing the construction layout of
the `from-zero` branch and becomes the steady-state rules of the new tree.

What it must say, and where each line comes from:

1. **The tree**, one paragraph per layer, and the pointer that `README.md` holds
   one line per file (tree Part 1, 0.1).
2. **One command**: every stage is entered through `run.py`; the subcommands are
   `ls, where, find, kill, refire, retry, free, sync, table, selfcheck` and a
   walk is `run.py <workflow> <setting> [--debug]` (8.6). The underlying modules
   are never called by hand (2.6).
3. **GPU runs go through the gpu-run skill**, and an agent never starts a GPU
   process: it returns BLOCKED with the ready-to-run command (branch CLAUDE.md,
   kept).
4. **Records, five layers, with the new paths**: direction `notes/TIMELINE.md`
   (a person, append-only); numbers `jobs/runs.jsonl` -> `jobs/RESULTS.md`
   (written by `jobs/registry.py`, never by hand); data settings
   `notes/DATA.md`; plan `notes/WORKPLAN.md` (overwritten); raw data on NFS.
   The primary key is the run key: the run directory name, the tmux session
   name, the registry row and the commit message all carry it (3.4, 8.1) —
   this replaces the old `run_id`-in-four-places rule.
5. **`experimental_settings/` is gyb's**: a hook refuses an agent edit to
   `experimental_settings/*.yaml` and to `models/table.yaml` (0.2, 6.1,
   9(a)#10); an agent proposes a setting as a task.
6. The iron rules that already hold on the branch, unchanged in substance: large
   outputs to `/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/`, weights to
   `.../models`, uv for environments, complete isolation from
   `/home/y-guo/ACL2026`, no guessing about data results, commit before
   launching, `notes/` is gyb's and an agent appends only a `TIMELINE.md` entry
   when asked, ancient memory (`notes/plans/archive/`) is read only on request,
   everything on disk is English.
7. **Issue tracker and ticket execution**, unchanged, with the prompts now at
   `.claude/skills/ticket-run/prompts/`.

**Not carried over**: the "Layout during construction" section (legacy/ is
deleted), the sentence that the old rules "do not apply on this branch until the
new run.py, jobs/ and the skills are rewritten" (they are), the `run.py` task
registry / `TASKS` / `RECIPES` / `recipe` / `status` / `show` rules, `MAP.md`,
`ops/`, `DATA.md §7`, the four-ledger table's claim that the ledgers live
together (errata 5 below), the presets rule, and `RUNMETA.json`.

### 1.7 `.gitignore` — edited

One sentence: the version-control boundary is re-stated for the new tree, with
every rule that names a deleted directory removed.

Removed (all of them name paths that stop existing when `legacy/` goes):
`envs/cuda-compat-13.0/`, `envs/tau2-bench/`, `envs/appworld/`, `envs/tales/`,
`envs/bfcl/`, the whole `envs/alfworld/` block, `fig1_pilot/...`,
`traj_pipeline/data/`, `envs/bert_runs`, `envs/toolhop`, `envs/runs`,
`envs/stabletoolbench`, `legacy/pipeline/data`, `legacy/pipeline/runs`,
`legacy/pipeline/inject/exec_cache/`, `legacy/demo/tiny_qwen3`,
`legacy/demo/runs`, `legacy/ops/*.lock`, the three `envs/...runs/**` keep-only-md
blocks, `legacy/envs/serve_logs/*.preset.json`, `benchmark_design/*.jsonl`, the
`legacy/pipeline/**` keep-only-md blocks, and
`legacy/pipeline/inject/runs/**`.

Kept or added, each with the rule it comes from:

```
# venvs and clones live under external/ and are never in git (bare names: symlinks)
external/appworld
external/probe-env
external/vllm-env
*-env/
.venv/

# the registry's lock (8.6); the rows and the rendered table are in git (tree line for jobs/)
jobs/runs.jsonl.lock

# outputs live on NFS and nothing under them is in git (iron rule; 6.3 names the root)

# python miscellany, logs, weights
__pycache__/
*.py[cod]
*.egg-info/
.ipynb_checkpoints/
logs/
*.log
*.out
*.pt
*.pth
*.safetensors
*.bin
*.npy
*.npz

# local settings only; .claude skills and agents are engineering assets and stay in the repo
.claude/settings.local.json
```

**Not carried over**: the LaTeX block (no `.tex` source is in this repo) — kept
only if `git ls-files '*.tex'` is non-empty at migration time, which the
acceptance below checks rather than assumes.

### 1.8 `legacy/` — deleted

`git rm -r legacy/` as the last construction step. The tree's own line says it:
"It is deleted by the last migration step." It holds `configs/`, `demo/`,
`envs/`, `MAP.md`, `model_registry.py`, `ops/`, `pipeline/`, `preset_loader.py`,
`RESULTS.md`, `run.py`, `serve_preset.py`, `sweep_preset.py`, `tests/`. Nothing
in the new tree imports it, which the acceptance proves rather than asserts.

**What is lost, stated** (so the deletion is a decision and not an accident):
the offline replay line (`legacy/pipeline/inject/replay_inject.py` and its six
siblings, 9(b)#15 names what bringing it back would take), the five non-AppWorld
environments, the read-only axis and the self-fire head, `--overlong skip` and
`drop-event`, the probing-cost and economics tables, the mbert line, the presets
and the collection manifests, `demo/prepare.py`, and the chat-endpoint
collection path (9(a)#26). All of it stays reachable in git history at tag
`checkpoint-2026-09-17-before-from-zero` and at commit `647dc45`, which the
TIMELINE entry names.

### 1.9 `notes/TIMELINE.md` — one entry appended at the top

One sentence: the direction entry that records the from-zero rewrite, written
under the "new entries go on top" rule of that file's own header.

It must state, in this order (the file's existing entries are the format model):

- **Trigger**: gyb's seven principles (tree Part 1's numbered list) and the
  2026-09-13..09-17 renewal discussion.
- **Decision**: the old tree is replaced by the 34-file tree of
  `notes/plans/2026-09-14-structure-from-zero.md`, whose interfaces are
  `notes/plans/2026-09-17-contracts.md`; six stages, one command (`run.py`), one
  experiment is one setting, a run directory is named by its key, `--debug` runs
  any setting tiny, `eval/` reads only disk.
- **Counts**: about 60 Python files under the old code directories -> 34; the
  old four-ledger layout -> five record layers with `jobs/runs.jsonl` and
  `jobs/RESULTS.md` beside the registry.
- **What is retired, by name**: the resident sampler, its web page
  (`localhost:8377`), the sampling history, the incident agent, the autopsy, the
  escalation line's automatic consequence, the one-refire-per-piece quota, the
  `run.py` task registry (`TASKS`/`RECIPES`/`list`/`show`/`recipe`/`status`),
  `MAP.md`, `ops/jobs.json`, `RUNMETA.json`, the presets, the offline replay
  line, the chat-endpoint collection path, and the five non-AppWorld
  environments (9(a)#13, #26, #39).
- **What this invalidates**: every command in the pre-rewrite gpu-run and
  probe-pipeline skills; the CONTEXT.md entries listed below; every experiment
  number in `jobs/RESULTS.md` produced before the rewrite keeps its old
  provenance and is not re-derived (the old `RESULTS.md` goes with `legacy/`,
  and the tag is where it is read).
- **The glossary debt, listed for gyb**: `notes/CONTEXT.md`'s entries *Sampler*,
  *Window*, *Escalation line*, *Incident agent*, *Autopsy*, *Incident record*,
  *Sampling history*, the sampler's half of *Verdict*, *Ledger* (now the
  registry, `jobs/runs.jsonl`), *Refire*'s quota sentence, *shardable*,
  *Monitoring parameters* (now `registry.DEFAULTS`, 8.5) and *chat baseline*
  describe machinery that no longer exists. An agent does not edit `notes/`, so
  they are named here and the rewrite is gyb's (errata 4).
- **Where the old tree is**: tag `checkpoint-2026-09-17-before-from-zero` on
  `main`, and commit `647dc45` on this branch.
- **Acceptance that was actually run**: the three `--debug` walks of section 4,
  each with its printed run directory key, and `run.py selfcheck` exit 0. The
  entry is written after they pass, with the real keys pasted in, not before.

---

## 2. Order of construction inside the folder

This folder is last: every other folder's tickets must be merged, and the
`--debug` walks of section 4 must have been run by the main session, before
`legacy/` is deleted and the TIMELINE entry is written.

| step | what | needs to exist first (file + function) |
|---|---|---|
| W1 | rewrite `.claude/skills/gpu-run/SKILL.md`, trim `references/gpu_state.md`, delete the two reference files and the script | `run.py` with `free`, `ls`, `where`, `kill`, `refire`, `retry`, `table`, `sync`, `selfcheck` and the walk; `jobs/registry.py` `free`, `ls`, `judge`, `judge_service`, `DEFAULTS`; `jobs/launch.py` `git_state`, `launch`, `refire`, `teardown_services` |
| W2 | rewrite `.claude/skills/probe-pipeline/SKILL.md`, delete its four reference files | `experimental_settings/schema.py` `STAGES`, `load`, `key`, `run_dir`; `README.md`'s extension recipes (0.4) and file list; `run.py selfcheck` |
| W3 | edit `.claude/skills/exp-status/SKILL.md`, the three agent definitions, the three path-only skills, and move the branch role prompts into `ticket-run/prompts/` | `jobs/registry.py` (`jobs/runs.jsonl`, `jobs/RESULTS.md` exist as paths); `run.py ls`, `run.py table` |
| W4 | rewrite `CLAUDE.md` | W1-W3 (it points at the skills), `run.py --help` (the subcommand list it names), `.claude/hooks/settings_readonly.sh` (the hook it cites) |
| W5 | **main session**: the GPU smoke list of section 4 | everything; W1 (the skill it is run under) |
| W6 | delete `legacy/`, clean `.gitignore`, append the `notes/TIMELINE.md` entry, `run.py selfcheck`, one commit | W1-W5. The TIMELINE entry quotes W5's real keys |

W1, W2 and W3 touch disjoint files and can run in parallel. W4 follows them
because it names them. W6 is alone and last.

---

## 3. Acceptance, CPU (an implementer runs these from the repo root)

Interpreter: `external/probe-env/bin/python` (the interpreter this repo's
commands are typed with, 0.2's `run.py` venv line, 6.3's `any` resolution).
Working directory: `/home/y-guo/reproduce/new1`.

Two of the checks below (C1, C3) are the CPU half of "the `--debug` walk is the
acceptance of the whole": they prove that every named setting of all three
workflow files loads under `--debug` and resolves to a directory, without
launching anything. Everything past that needs a card and is section 4's.
Stage-level fixtures (records -> `build`, prediction rows -> `eval`, records ->
`score`) belong to the folders that own those programs and are not repeated
here.

**C1 — every named setting of all three workflow files loads, keys and freezes
under `--debug`.** No launch, no card, no output directory.

```bash
external/probe-env/bin/python - <<'PY'
import pathlib, yaml
from experimental_settings import schema
for f in ["baseline.yaml", "train_probe.yaml", "inject.yaml"]:
    p = pathlib.Path("experimental_settings") / f
    doc = yaml.safe_load(p.read_text())
    stages = doc["workflow"]
    names = [k for k in doc if k not in ("workflow", "common")]
    for name in names:
        for dbg in (False, True):
            cfgs = schema.load(p, name, debug=dbg, overrides={})
            for cfg in cfgs:
                keys = {s: schema.key(s, cfg) for s in stages}
                dirs = {s: schema.run_dir(s, cfg) for s in stages}
                assert cfg._workflow == stages, (f, name, cfg._workflow)
                for s in stages:
                    assert len(keys[s]) == 12, (f, name, s, keys[s])
                    assert dirs[s].name == keys[s], (f, name, s)
                    assert ("/debug/" in str(dirs[s])) == dbg, (f, name, s, dbg)
                print(f, name, "debug" if dbg else "real",
                      " ".join(f"{s}={keys[s]}" for s in stages))
print("C1 ok")
PY
```

Expected: exit 0, the last line `C1 ok`, and one line per (file, setting,
debug/real) naming a 12-hex key per stage of that file's workflow. Every debug
path contains `/debug/` and every real one does not (3.4). A load error here is
the check working: it names the field (5.7).

**C2 — a key is pure: it never reads the output tree, and it is stable.** Run C1
twice with the outputs root made unreadable and compare.

```bash
external/probe-env/bin/python run.py where train_probe ctool_q06 train > /tmp/k1.txt
OUT=$(external/probe-env/bin/python -c "import yaml;print(yaml.safe_load(open('constants/path_outputs.yaml'))['root'])")
test ! -e "$OUT" || mv "$OUT" "$OUT.hidden"
external/probe-env/bin/python run.py where train_probe ctool_q06 train > /tmp/k2.txt
test -e "$OUT.hidden" && mv "$OUT.hidden" "$OUT"
diff /tmp/k1.txt /tmp/k2.txt && echo "C2 ok"
```

Expected: exit 0, `C2 ok`, and both files holding the same absolute path
`<root>/train/<12 hex>` (3.1, 3.2 rule 2). *If the outputs root cannot be moved
on this machine, the weaker form is the same `where` call run twice with
`--debug` and without, and the two keys differing.*

**C3 — `where` answers for every stage of every workflow, real and debug.**

```bash
set -e
for a in "baseline gptoss120b_appworld sample" "baseline gptoss120b_appworld score" \
         "train_probe ctool_q06 sample" "train_probe ctool_q06 build" \
         "train_probe ctool_q06 train"  "train_probe ctool_q06 eval" \
         "inject ctool_q06_p1e1 inject" "inject ctool_q06_p1e1 score"; do
  external/probe-env/bin/python run.py where $a
  external/probe-env/bin/python run.py where $a --debug
done
echo "C3 ok"
```

Expected: exit 0, sixteen absolute paths, `C3 ok`. Each debug path sits under
`<root>/debug/<stage>/`, each real one under `<root>/<stage>/` (3.4). The
setting names are the ones `experimental_settings/*.yaml` actually carries; the
ticket takes them from the file with the loop in C1 rather than hard-coding
them if they differ.

**C4 — the read-only subcommands answer on the live registry.**

```bash
external/probe-env/bin/python run.py ls        && echo ok-ls
external/probe-env/bin/python run.py ls --debug && echo ok-lsdebug
external/probe-env/bin/python run.py find data.env=appworld && echo ok-find
external/probe-env/bin/python run.py free      && echo ok-free
external/probe-env/bin/python run.py table     && echo ok-table
external/probe-env/bin/python run.py sync      && echo ok-sync
```

Expected: each exits 0 and prints its table (`ls` may print a header and no rows
on an empty `jobs/runs.jsonl`; `free` prints one line per host of
`constants/path_outputs.yaml`'s `hosts:` list, and a host whose probe fails is
printed as busy, not skipped, 3.4). `run.py free` on a host that is not
`login_host` must instead refuse, naming the login host (8.6) — checked in
section 4, since it needs a second host.

**C5 — selfcheck.** The single line that covers this folder's claim that the
documents and the code agree.

```bash
external/probe-env/bin/python run.py selfcheck && echo "C5 ok"
```

Expected: exit 0, `C5 ok`. It proves the README file list against the tree,
every annotation line against the `ast`-parsed import graph, every axis literal
against the files behind it, one `VERSION` per module the stage table names, the
`PROBE_KIND` pair per method, `DEFAULTS`/`REQUIRED` per format file, no `/home/`
or `/net/` path in code outside `constants/`, each `any` file importing under
**every interpreter of the `venvs:` map** (three: appworld, probe, vllm — see
errata 3), and each family module importing under the probe and the vllm
interpreter (8.6).

**C6 — the file count and the README cover.**

```bash
find run.py constants experimental_settings data models agent train eval jobs \
     -name '*.py' | wc -l          # expect: 34
find run.py constants experimental_settings data models agent train eval jobs \
     -name '*.py' | while read -r f; do grep -qF "$f" README.md || echo "MISSING $f"; done
```

Expected: `34`, and no `MISSING` line (0.3's count; the README rule of 0.1).

**C7 — no retired command survives in an agent-facing document.** This is the
acceptance of W1-W4. It is scoped to `CLAUDE.md`, `README.md` and `.claude/`,
because `notes/` records history on purpose.

```bash
external/probe-env/bin/python - <<'PY'
import pathlib, re, sys
RETIRED = ["gpu-jobs", "run.py record", "launch-probe", "launch-eval",
           "run.py runmeta", "RUNMETA", "run.py list", "run.py show",
           "run.py recipe", "run.py status", "run.py sampler", "sampler",
           "incidents.jsonl", "incident agent", "localhost:8377",
           "ops/", "MAP.md", "pipeline/", "configs/presets", "jobs.json",
           "--run-id", "--track", "CELLS", "EVAL_CELLS", "legacy/"]
files = [pathlib.Path("CLAUDE.md"), pathlib.Path("README.md")]
files += [p for p in pathlib.Path(".claude").rglob("*.md")]
bad = [(str(p), t, i + 1) for p in files
       for i, line in enumerate(p.read_text().splitlines())
       for t in RETIRED if t in line]
for b in bad:
    print("RETIRED", *b)
print("C7", "ok" if not bad else "FAIL")
sys.exit(1 if bad else 0)
PY
```

Expected: exit 0 and `C7 ok`. The one allowed exception is a line whose purpose
is to say the thing is gone; such a line is written as a single "what is gone"
list item inside `.claude/skills/gpu-run/SKILL.md` and that file's list is the
only place the checker skips — the ticket adds it to the checker as an explicit
`(path, line-range)` exemption rather than by loosening the token list.

**C8 — every command the documents name exists.**

```bash
external/probe-env/bin/python - <<'PY'
import pathlib, re, subprocess, sys
help_txt = subprocess.run(["external/probe-env/bin/python", "run.py", "--help"],
                          capture_output=True, text=True).stdout
named = set()
for p in [pathlib.Path("CLAUDE.md"), pathlib.Path("README.md")] + \
         list(pathlib.Path(".claude").rglob("*.md")):
    named |= set(re.findall(r"run\.py ([a-z_][a-z0-9_-]*)", p.read_text()))
sub = set(re.findall(r"^\s{2,}([a-z][a-z0-9_-]*)", help_txt, re.M))
missing = sorted(n for n in named if n not in sub and n not in
                 {"baseline", "train_probe", "inject"})   # the three workflow files
print("named:", sorted(named)); print("missing:", missing)
print("C8", "ok" if not missing else "FAIL"); sys.exit(1 if missing else 0)
PY
```

Expected: exit 0, `C8 ok`, and the `named:` line containing exactly
`free, ls, where, find, kill, refire, retry, table, sync, selfcheck` plus the
three workflow-file names (8.6).

**C9 — `legacy/` is gone and nothing refers to it.** This is W6's acceptance.

```bash
git ls-files legacy | wc -l                       # expect: 0
test ! -e legacy && echo ok-gone
grep -rn "legacy" run.py constants experimental_settings data models agent \
     train eval jobs README.md CLAUDE.md || echo ok-noref
grep -n "legacy\|envs/\|fig1_pilot\|traj_pipeline\|benchmark_design" .gitignore \
     || echo ok-gitignore
git status --porcelain | grep -v '^$' || echo ok-clean
```

Expected: `0`, `ok-gone`, `ok-noref`, `ok-gitignore`, and after the commit
`ok-clean`. The greps name the code directories explicitly and never start at
the repo root, because a recursive grep from the root walks `external/`.

**C10 — the `.gitignore` boundary still holds.**

```bash
git check-ignore -v external/probe-env jobs/runs.jsonl.lock .claude/settings.local.json
git check-ignore jobs/runs.jsonl jobs/RESULTS.md README.md ; echo "exit=$?"
git ls-files '*.tex' | wc -l          # 0 -> the LaTeX block is dropped from .gitignore
```

Expected: the first command prints a matching rule for each of the three paths;
the second exits 1 with no output (none of those three is ignored — the registry
rows and the rendered table are in git, tree line for `jobs/`); the third prints
`0`, which is what licenses dropping the LaTeX block.

---

## 4. Acceptance, GPU or cross-host (the main session, not the implementer)

Every command here starts a process on a card or reaches another host, so an
implementer returns BLOCKED with it and the main session runs it under the
rewritten gpu-run skill. Cards are picked by `run.py` itself (3.4), so no card
is named by hand.

**The three walks in order.** Each is run twice: the first call launches and
stops (9(c)#1), the second call — after the pieces finish — writes `done.json`,
appends the finish row, tears the service pieces down and walks to the next
stage. In between, `run.py ls <workflow> --debug`.

**G1 — `baseline.yaml`, the `[sample, score]` walk.**

```bash
external/probe-env/bin/python run.py baseline <baseline_setting> --debug
external/probe-env/bin/python run.py ls baseline --debug
# … when the loop piece is done …
external/probe-env/bin/python run.py baseline <baseline_setting> --debug
```

Must show:
- the first call prints the sample run directory under
  `<root>/debug/sample/<key>` and starts three pieces: one vLLM service piece on
  its table row's `serving.host`, one probe service piece with `--render-only`
  **on `login_host` and holding no card**, and one loop piece on `login_host`
  (`debug.yaml` sets `pieces: 1`, `replicas: 1`) — 2.3, 3.4, 5.6;
- `ls` prints a verdict per piece from the six-value set, `warming up` at first
  and `healthy` once beats arrive; `progress` counts done records against the
  requested total, which is 9 (3 splits x `n_tasks: 3` x one seed, 2.3's
  per-split cap);
- the second call writes `done.json` with `pairs` of length 9, the finish row,
  **and kills both service pieces**; `ssh <host> nvidia-smi` then shows the vLLM
  cards free and `run.py ls` shows no `orphan` flag (2.3, 9(a)#37);
- `score` runs in place on `login_host` (no tmux) and writes `run_report.json`,
  `report.md`, `consumed.json` and `done.json`; `run.py ls baseline --debug`
  shows both stages `done`.

**G2 — `train_probe.yaml`, the `[sample, build, train, eval]` walk, ctool.**

```bash
external/probe-env/bin/python run.py train_probe <ctool_setting> --debug
```

Must show:
- `sample` is either **skipped** — if this setting's keyed `data`,
  `models.agent`, `generation` and `sample.{split,max_steps,store_token_ids}`
  match G1's, the key is the same directory, the requested pairs are a subset of
  its `done.json` `pairs`, and `run.py` adds `{train_probe, <setting>}` to that
  directory's `meta.json` `owners` (2.3's ownership event) — or collected afresh.
  Both are acceptance; the walk prints which, and `run.py ls --debug` shows the
  `owners` column with two names in the skip case;
- `build` runs in place and writes `examples.parquet`, `consumed.json` (record
  files **and** split files, with hashes), `report.md`, `done.json`. Check:
  ```bash
  external/probe-env/bin/python -c "import polars as pl,sys; d=pl.read_parquet(sys.argv[1]); print(d.height); print(d['split'].value_counts())" <build dir>/examples.parquet
  ```
  must print a non-zero height and **all three of `train`, `val`, `test` with a
  non-zero count** (2.3's per-split `n_tasks`, 2.5's per-split `max_examples`,
  9(c)#8 — an empty `val` here is the exact failure 9(a)#44/#47 were written to
  prevent, and it means the build or the loop lost the split);
- `train` launches one piece on one card and writes, in this order,
  `align_check.json` (the alignment gate, mismatch under 1e-4),
  `train_log.jsonl`, `best/` with `meta.json`, `train_done.json`,
  `predictions.parquet`, `done.json` with `stage_extra.labels`;
- `eval` runs in place and writes `probe_report.json`, `fires.parquet`,
  `report.md`, `consumed.json`, `done.json`; `probe_report.json` carries a
  `theta_used` per entry of `eval.risk` and a bootstrap interval
  (`debug.yaml` sets `bootstrap: 50`);
- `run.py table train_probe` prints a row for this run.

**G3 — the two generating methods, and the cost of predicting at every cut
(contracts 9(d), 9(a)#2).**

```bash
external/probe-env/bin/python run.py train_probe <cgen_setting>   --debug
external/probe-env/bin/python run.py train_probe <cparam_setting> --debug
```

`build` is skipped for both (one build serves all three methods, 2.2). For each,
after `done.json` appears, measure:

```bash
D=<train run dir>
python3 - "$D" <<'PY'
import json, pathlib, sys, polars as pl
d = pathlib.Path(sys.argv[1])
t0 = (d/"train_done.json").stat().st_mtime
t1 = (d/"done.json").stat().st_mtime
n  = pl.read_parquet(d/"predictions.parquet").height
print(f"predict rows={n} wall_s={t1-t0:.1f} s_per_row={(t1-t0)/max(n,1):.4f}")
print(f"extrapolated to 507104 rows: {(t1-t0)/max(n,1)*507104/3600:.1f} GPU-hours")
PY
```

Report to gyb, as facts and nothing else: seconds per generated row for cgen and
for cparam, and the extrapolation to the full example count — 507,104 rows is
the number contracts 9(a)#2 names for "every row", against 8,533 for today's
theta-filtered `eval_causal_call.py`. 9(a)#2's fallback
(`train.predict.trigger_run`) is **written down and not built**; whether it gets
built is gyb's call on these numbers. No interpretation of the numbers is
offered.

**G4 — `inject.yaml`, the `[inject, score]` walk, with pinned references.**

At the end of construction no full-scale probe exists, and contracts 3.4 keys a
resolved reference **without** the debug overlay, so a named reference would
point at a real directory that has never existed. The walk therefore pins every
reference to the keys G1-G3 just produced (errata 1 and 2):

```bash
KS=$(basename $(external/probe-env/bin/python run.py where train_probe <ctool_setting> train --debug))
KE=$(basename $(external/probe-env/bin/python run.py where train_probe <ctool_setting> eval  --debug))
KG=$(basename $(external/probe-env/bin/python run.py where train_probe <cgen_setting>  train --debug))
KB=$(basename $(external/probe-env/bin/python run.py where baseline    <baseline_setting> sample --debug))
external/probe-env/bin/python run.py inject <inject_setting> --debug \
  "inject.probe_score={key: {train: $KS, eval: $KE}}" \
  "inject.probe_gen={key: {train: $KG}}" \
  "score.baseline={key: {sample: $KB}}"
```

Must show:
- the loader accepts the three pinned references, `ls` flags the run `pinned`,
  and the inheritance check, the shared-build-key gate of 2.5 and 5.7's baseline
  split/seed superset refusal are skipped, which is 5.4's stated behaviour for a
  pinned reference;
- `settings.yaml` carries `_upstream` with `probe_score.train`,
  `probe_score.eval`, `probe_gen.train` and `baseline.sample`, and
  `_resolved.probe_temperature` read out of the ctool eval report (5.4, 9(a)#7);
- `jobs/launch.py` starts one vLLM piece and one probe service piece **holding
  one card** with `--score-ckpt`, `--gen-ckpt` and `--temperature`, then runs
  ```bash
  external/probe-env/bin/python -m models.probe_models.service check \
      --base-url <url from service_probe_0.json> --run-dir <inject run dir>
  ```
  and only then the loop piece. A non-zero exit there must produce a
  `launch_failed` finish row, **no loop piece**, and a teardown of the service
  pieces that did come up (2.3, 8.1, 7.2);
- the records carry `spec` and `resume` rows, and at least one `spec` row exists
  under `arm: probe` with `theta` as set — if none does, the run is still a pass
  for the machinery and a fact to report (a 0.6B debug probe at three tasks may
  never cross theta), and the arm is then re-run once with
  `inject.fire_nth_cut=1` to force one fire through the whole path;
- `score` writes the paired report and does not refuse: the baseline holds a
  done record for each of the inject run's requested (task, seed) pairs, which
  holds because G1 collected `test` with the same `n_tasks` and seed (2.5).

**G5 — the encode fixture, the one open question of 9(d).** Against the live
render-only service of G1:

```bash
external/probe-env/bin/python -m models.probe_models.service check \
    --base-url <url from G1's service_probe_0.json> --run-dir <G1 sample run dir>
```

Record which way it came out for the `<|end|>` fixture: `special=false` must
leave it plain text and `special=true` must produce the control token. The
result decides whether the `p2_*` injection formats are runnable at all on this
backbone; it is a measurement to report, not a decision (9(d)). Until it is run,
G4 uses the default `p1_e1` format, which needs neither direction.

**G6 — the cross-host rules.**

```bash
ssh <a host that is not login_host> "cd /home/y-guo/reproduce/new1 && external/probe-env/bin/python run.py ls"
external/probe-env/bin/python run.py free
```

Must show: the first refuses, naming `login_host` (8.6); the second lists every
host of `constants/path_outputs.yaml`'s `hosts:` list with its free-card count,
and a host whose ssh fails is reported busy rather than free (3.4, fail-closed).

**G7 — the two-session gate.** Two `run.py` calls on the same setting and stage
from `login_host`, the second while the first is launching: the second must
refuse, naming the open row's `run_id` and its age, or the live session (2.5,
9(c)#9). Cheap to run and it is the one concurrency claim nothing else exercises.

**G8 — retire the sampler's live machinery on the login machine.** Not a repo
change, so it is the main session's and is done only after G1-G4 pass:
`crontab -l` on `login_host` holds a `*/5 * * * *` line that restarts a
`new1_sampler` tmux session (recorded in the old `gpu_state.md` lines 17-26);
that line is removed and the resident `new1_sampler` session is killed, because
after the migration it would restart a process whose code is deleted. Check:
`crontab -l | grep -c new1_sampler` prints `0` and `tmux ls` on `login_host`
lists no `new1_sampler`.

---

## 5. Tickets

Four tickets. W5 (the GPU walks) and G8 are not tickets: they are the main
session's, and the integrator lists them as the gate between ticket 3 and
ticket 4.

### Ticket 1 — `gpu-run skill: the new lifecycle`

- **Files**: `.claude/skills/gpu-run/SKILL.md` (rewrite),
  `.claude/skills/gpu-run/references/gpu_state.md` (delete lines 1-46, keep
  47-97), delete `.claude/skills/gpu-run/references/launch-methodology.md`,
  `.claude/skills/gpu-run/references/monitor-methodology.md`,
  `.claude/skills/gpu-run/scripts/gpu_status.sh`.
- **What to do**: section 1.1 of this plan, phase table and all. The
  `description` front-matter keeps its Chinese trigger clause (branch CLAUDE.md)
  and drops the words "three ledgers" and "sampler". The file names no command
  that `run.py --help` does not list.
- **Acceptance**: C7, C8 (both restricted to this skill's files while the other
  documents are still being edited), plus `test ! -e
  .claude/skills/gpu-run/scripts` and a `wc -l` on `gpu_state.md` showing the
  hardware table intact.
- **Needs from other folders**: `run.py` (subcommands `free`, `ls`, `where`,
  `kill`, `refire`, `retry`, `table`, `sync`, `selfcheck`, and the walk
  `run.py <workflow> <setting> [--debug]`); `jobs/registry.py`
  (`free`, `ls`, `judge`, `judge_service`, `DEFAULTS`, `open_runs`);
  `jobs/launch.py` (`git_state`, `launch`, `refire`, `teardown_services`);
  `constants/path_outputs.yaml` (`login_host`, `hosts`).

### Ticket 2 — `probe-pipeline skill: the chain is one command`

- **Files**: `.claude/skills/probe-pipeline/SKILL.md` (rewrite), delete
  `references/extending.md`, `references/gates.md`, `references/invariants.md`,
  `references/stage-commands.md`.
- **What to do**: section 1.2 of this plan, its six numbered points. Every
  pointer is to `README.md` (the file list and the extension recipes) or to
  `notes/plans/2026-09-17-contracts.md` by Part number; the skill keeps no copy
  of either.
- **Acceptance**: C7 and C8 on this skill's file; `test ! -e
  .claude/skills/probe-pipeline/references`; and a grep proving that each of the
  four extension places of 0.3 is named once in the file.
- **Needs from other folders**: `experimental_settings/schema.py` (`STAGES`,
  `load`, `key`, `run_dir`, the axis literals); `README.md`'s file list and
  extension recipes (0.4); `run.py selfcheck`.

### Ticket 3 — `retire the old commands from CLAUDE.md, exp-status, the agents and the remaining skills`

- **Files**: `CLAUDE.md`, `.claude/skills/exp-status/SKILL.md`,
  `.claude/agents/gpu-runner.md`, `.claude/agents/job-monitor.md`,
  `.claude/agents/env-runner.md`, `.claude/skills/handoff/SKILL.md`,
  `.claude/skills/paper-write/SKILL.md`, `.claude/skills/ticket-run/SKILL.md`,
  `.claude/skills/ticket-run/prompts/*.md` (replaced by the four files under
  `.scratch/from-zero/prompts/`).
- **What to do**: sections 1.3, 1.4, 1.5 and 1.6 of this plan, each with its
  line numbers. `CLAUDE.md` is a rewrite; the rest are path-and-command edits
  that leave every method alone.
- **Acceptance**: C7 and C8 over all of `.claude/` and `CLAUDE.md` (they must
  now pass whole), plus a diff review showing that `exp-status`, `handoff`,
  `paper-write` and `ticket-run` changed only paths and command names.
- **Needs from other folders**: `run.py --help` (for C8); `jobs/runs.jsonl` and
  `jobs/RESULTS.md` existing as paths; `.claude/hooks/settings_readonly.sh`
  (CLAUDE.md cites it).

### Ticket 4 — `delete legacy/, clean .gitignore, write the TIMELINE entry`

- **Files**: delete `legacy/` entirely; `.gitignore`; `notes/TIMELINE.md`
  (append one entry at the top).
- **What to do**: sections 1.7, 1.8 and 1.9 of this plan. The TIMELINE entry is
  written **after** the main session's G1-G4 have passed and quotes their real
  keys; the ticket receives those keys in its body. `notes/CONTEXT.md` is **not**
  edited — its obsolete entries are listed inside the TIMELINE entry and the
  rewrite is gyb's (errata 4).
- **Acceptance**: C9, C10, C5 (`selfcheck` exit 0 after the deletion), and C6.
- **Needs from other folders**: every other folder merged — this ticket removes
  the only copy of the algorithms, so `run.py selfcheck` and the section 4 walks
  are its gate. Concretely: `run.py selfcheck`,
  `experimental_settings/schema.py`, `jobs/registry.py`, `jobs/launch.py`,
  `data/*`, `models/*`, `agent/*`, `train/*`, `eval/*` all present and green.

---

## 6. Contract errata settled here

Appended verbatim to `.scratch/from-zero/contract-errata.md`.

1. **3.4 / 9(c)#8** — a resolved reference is always keyed without the debug
   overlay, so a `--debug` run points at real upstream directories -> at the end
   of construction no real run exists, so the acceptance `--debug` walk of
   `inject.yaml` pins `inject.probe_score`, `inject.probe_gen` and
   `score.baseline` with the `key:` form of 5.4 to the debug keys G1-G3 produced,
   and accepts the `pinned` flag with the inheritance check, the shared-build-key
   gate of 2.5 and 5.7's baseline split/seed superset refusal skipped.
2. **5.7** — the command-line override is written `section.field=value` with no
   rule for the right-hand side -> the build parses the right-hand side with
   `yaml.safe_load`, so a reference can be pinned from the command line
   (`inject.probe_score={key: {train: <hex>, eval: <hex>}}`) and the acceptance
   walk needs no edit to gyb's YAML files.
3. **0.1** — `venv: any` is defined over every interpreter of the `venvs:` map of
   `constants/path_datasets.yaml` -> the acceptance runs the import test over
   exactly those three interpreters and not over the system `python3` (3.10, no
   NumPy), under which every `eval/` file legitimately fails to import because
   0.2 gives them NumPy.
4. **9(a)#13** — the obsolete `notes/CONTEXT.md` entries "must be rewritten in
   the same commit" -> `notes/` is gyb's and an agent appends only a
   `TIMELINE.md` entry, so the migration ticket lists the obsolete entries
   (Sampler, Window, Escalation line, Incident agent, Autopsy, Incident record,
   Sampling history, the sampler's half of Verdict, Ledger, Refire's quota
   sentence, shardable, Monitoring parameters, chat baseline) inside the TIMELINE
   entry and the CONTEXT.md rewrite goes to gyb.
5. **9(b)#16** — rendering `RESULTS.md` into `notes/` is not applied, so "the
   four-ledger rule in CLAUDE.md stays literally true" fails -> the rewritten
   `CLAUDE.md` names five record layers with `jobs/runs.jsonl` and
   `jobs/RESULTS.md` beside the registry and drops the claim that the ledgers
   live in one place.
6. **2.3 / 8.6** — no subcommand offers a dry run, and every walk launches -> the
   CPU acceptance of a workflow file's `--debug` load calls
   `schema.load(..., debug=True)`, `schema.key` and `schema.run_dir` directly
   (C1) and uses `run.py where` (C3); the walk itself is a GPU acceptance.
7. **6.3** — the `hosts:` example lists 105:4, 106:8, 107:8, 108:8 cards ->
   `constants/path_outputs.yaml` is filled from the measured table in
   `.claude/skills/gpu-run/references/gpu_state.md` (tokyo105/shiga 8x A6000,
   tokyo106 10x A6000, tokyo107 4x RTX 6000 Ada, tokyo108/saitama 3x H100 NVL +
   3x H200 NVL), since 6.3's block is an illustration and the card counts differ.
