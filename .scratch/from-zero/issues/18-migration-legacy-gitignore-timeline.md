# 18 the migration: delete legacy/, clean .gitignore, write the TIMELINE entry

Status: ready-for-agent
Blocked by: 15, 16
Spec: .scratch/from-zero/spec.md (sections 1, 2, 7, 9)

## What to do

Four things, in this order. The files you may touch, and nothing else:

```
docs/                 moved whole into notes/, with git mv docs notes/docs
legacy/               deleted entirely, with git rm -r
.gitignore            edited: every rule naming a deleted directory removed
constants/path_models.yaml   two source citations stripped (C9 greps for the word `legacy`)
notes/TIMELINE.md     one entry appended at the top
```

**This is the last ticket of the build.** It removes the only copy of the
algorithms, so it runs after `run.py selfcheck` is green and after the main
session's three end-to-end `--debug` walks have passed. **The walk keys are
handed to you in the Comments section below**; the TIMELINE entry quotes them and
is written after they pass, not before.

**`notes/CONTEXT.md` is not edited.** `notes/` is gyb's, an agent appends only a
`TIMELINE.md` entry, so the obsolete glossary entries are **listed inside the
TIMELINE entry** and the rewrite is gyb's (errata).

### 0. `docs/` -> `notes/docs/`

`git mv docs notes/docs`, and nothing else: no file inside it is opened, read or
edited. The fixed tree's `notes/` line says notes holds "everything gyb writes by
hand: ... plans/ and docs/ (moved whole)", and contracts 0.2's tree lists no
root-level `docs/`. The move was missed when the rest of gyb's documents went to
`notes/` in commit `25e64ed`, and until it happens the root carries a directory
the fixed tree does not name while two documents this build writes — ticket 16's
`.claude/skills/repo-review/SKILL.md`, already on the branch, and ticket 17's
`CLAUDE.md`, in flight beside this ticket — cite `notes/docs/agents/issue-tracker.md` and
`notes/docs/agents/triage-labels.md`. **This is the one write into `notes/` this
ticket makes besides the TIMELINE entry, and it is a move, not an edit**: the
spec's rule that `notes/` is the owner's stands, and `git status` must show the
five tracked files (`docs/agents/domain.md`, `docs/agents/issue-tracker.md`,
`docs/agents/triage-labels.md`, `docs/design/2026-08-08-gpu-monitor-launch.md`,
`docs/plans/2026-08-08-gpu-monitor-launch.md`) as pure renames (`R`), with no
content change.

Check before and after:

```bash
ls -d docs docs/agents docs/adr 2>&1 | head -5        # before: what is there
git mv docs notes/docs
git status --porcelain notes/docs docs | head -20     # every line starts with R
test ! -e docs && echo ok-docs-moved
test -f notes/docs/agents/issue-tracker.md && test -f notes/docs/agents/triage-labels.md \
  && echo ok-docs-paths
```

Expected: `ok-docs-moved`, `ok-docs-paths`, and a `git status` whose every line
is a rename. If `docs/adr/` is absent on disk, say so and move what is there —
the tree names the directory, not a fixed file list inside it.

### 1. `.gitignore`

**`envs/` is not `legacy/` and does not go with it.** `envs/` is a **top-level
sibling** of `legacy/` and survives the deletion: `external/appworld` is a symlink
to `../envs/appworld`, `external/vllm-env` to `../envs/vllm-env`, and ticket 06's
`models/table.yaml` sets `LD_LIBRARY_PATH:
/home/y-guo/reproduce/new1/envs/cuda-compat-13.0`. Verified on disk 2026-09-17,
`envs/` holds `alfworld/` (whose `splits/` is **tracked**), `appworld/`, `bfcl/`,
`cuda-compat-13.0/`, `tales/`, `tau2-bench/`, `stb-server-env/`, `toolhop-env/`,
`vllm-env/` and the three NFS symlinks `runs`, `stabletoolbench`, `toolhop`.
**Every `envs/...` rule stays.** The bare names `external/appworld` and
`external/vllm-env` match only the symlinks, and `*-env/` covers `vllm-env`,
`stb-server-env`, `toolhop-env` and the top-level `cprobe-env`, `mbert-env`,
`pptx-env` — nothing else. Dropping the `envs/` rules would leave a
multi-gigabyte clone tree and the NFS symlinks untracked **and** unignored, and
`C15`'s empty `git status --porcelain` could not hold.

**Removed** — only rules naming a path that no longer exists once `legacy/` is
gone, each checked on disk first: `legacy/pipeline/data`, `legacy/pipeline/runs`,
`legacy/pipeline/inject/exec_cache/`, `legacy/demo/tiny_qwen3`,
`legacy/demo/runs`, `legacy/ops/*.lock`,
`legacy/envs/serve_logs/*.preset.json`, the `legacy/pipeline/**` keep-only-md
blocks and `legacy/pipeline/inject/runs/**`. Removed as well, because their
directories are absent from this machine (`ls -d` finds none of them):
`paper/acl-style-files/`, `related_work/`, `jacobian-lens/`,
`fig1_pilot/alfworld_data/`, `traj_pipeline/data/`, `envs/bert_runs`, the
`envs/bert_runs/**` and `envs/bert_data/**` keep-only-md blocks, `*/results/**`,
`benchmark_design/*.jsonl`, the `envs/runs/**` keep-only-md block (`envs/runs` is a
symlink, so a rule under it never matches) and `*.feather` (first check that
`git ls-files '*.feather' | wc -l` prints `0`; keep the rule otherwise). **Before removing any of those, run
`ls -d <path>` and paste the result**; keep the rule if the path is there.

**Kept or added**, each with the rule it comes from:

```
# venvs and clones live under envs/, reached through external/ (bare names: symlinks)
*-env/
.venv/
**/.venv/
external/appworld
external/probe-env
external/vllm-env

# third-party benchmark clones under envs/: each has its own .git, restored by clone
envs/appworld/
envs/tau2-bench/
envs/tales/
envs/bfcl/
envs/cuda-compat-13.0/

# envs/alfworld/ is ours: only the venv, the data symlink and the logs are ignored;
# splits/ is a self-generated task list and is tracked
envs/alfworld/venv/
envs/alfworld/data
envs/alfworld/logs/

# symlinks to directories that live on NFS (bare names, since git does not follow them)
envs/runs
envs/stabletoolbench
envs/toolhop

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

The LaTeX block is **not** carried over — but check rather than assume:
`git ls-files '*.tex' | wc -l` must print `0` (C10 below).

### 1b. `constants/path_models.yaml` — two parentheticals removed

Lines 12 and 15 end `(legacy train_causal_tool.py:86)` and
`(legacy train_causal_tool.py:87)`. `legacy/` is deleted by this ticket, so the
citation dangles and C9's bare-word grep hits it. Delete the parenthetical on both
lines, leaving `note: own replica; the 1.7B tier of the three-tier backbone sweep`
and `note: own replica; the 4B tier of the same sweep`. No other line of the file
is touched. Use the Edit tool.

### 2. `legacy/` — deleted

`git rm -r legacy/` as the last construction step. The tree's own line says it:
"It is deleted by the last migration step." It holds `configs/`, `demo/`,
`envs/`, `MAP.md`, `model_registry.py`, `ops/`, `pipeline/`, `preset_loader.py`,
`RESULTS.md`, `run.py`, `serve_preset.py`, `sweep_preset.py`, `tests/`. Nothing
in the new tree imports it, which C9 **proves** rather than asserts.

**What is lost, stated** (so the deletion is a decision and not an accident):
the offline replay line (`legacy/pipeline/inject/replay_inject.py` and its six
siblings), the five non-AppWorld environments, the read-only axis and the
self-fire head, `--overlong skip` and `drop-event`, the probing-cost and
economics tables, the mbert line, the presets and the collection manifests,
`demo/prepare.py`, and the chat-endpoint collection path. All of it stays
reachable in git history at tag `checkpoint-2026-09-17-before-from-zero` and at
commit `647dc45`, which the TIMELINE entry names.

### 3. `notes/TIMELINE.md` — one entry appended at the top

Written under that file's own "new entries go on top" rule; the file's existing
entries are the format model (`## YYYY-MM-DD <sentence>`, then labelled bullets).
"On top" means above the newest entry (`## 2026-09-12 ...`, line 19 today) and
below the title and the blockquote header, never at line 1. It must state, in
this order:

- **Trigger**: gyb's seven principles (the tree's Part 1 numbered list) and the
  2026-09-13..09-17 renewal discussion.
- **Decision**: the old tree is replaced by the 31-file tree of
  `notes/plans/2026-09-14-structure-from-zero.md`, whose interfaces are
  `notes/plans/2026-09-17-contracts.md` and whose build order was
  `notes/plans/2026-09-17-construction-plan.md`; six stages, one command
  (`run.py`), one experiment is one setting, a run directory is named by its key,
  `--debug` runs any setting tiny, `eval/` reads only disk.
- **Counts**: about 60 Python files under the old code directories -> 31; the old
  four-ledger layout -> five record layers with `jobs/runs.jsonl` and
  `jobs/RESULTS.md` beside the registry.
- **What is retired, by name**: the resident sampler, its web page
  (`localhost:8377`), the sampling history, the incident agent, the autopsy, the
  escalation line's automatic consequence, the one-refire-per-piece quota, the
  `run.py` task registry (`TASKS`/`RECIPES`/`list`/`show`/`recipe`/`status`),
  `MAP.md`, `ops/jobs.json`, `RUNMETA.json`, the presets, the offline replay
  line, the chat-endpoint collection path, and the five non-AppWorld
  environments.
- **What this invalidates**: every command in the pre-rewrite gpu-run and
  probe-pipeline skills; the `notes/CONTEXT.md` entries listed below; every
  experiment number produced before the rewrite keeps its old provenance and is
  **not** re-derived (the old `RESULTS.md` goes with `legacy/`, and the tag is
  where it is read).
- **The glossary debt, listed for gyb**: `notes/CONTEXT.md`'s entries *Sampler*,
  *Window*, *Escalation line*, *Incident agent*, *Autopsy*, *Incident record*,
  *Sampling history*, the sampler's half of *Verdict*, *Ledger* (now the
  registry, `jobs/runs.jsonl`), *Refire*'s quota sentence, *shardable*,
  *Monitoring parameters* (now `registry.DEFAULTS`, 8.5) and *chat baseline*
  describe machinery that no longer exists. An agent does not edit `notes/`
  beyond this entry, so they are named here and the rewrite is gyb's.
- **Where the old tree is**: tag `checkpoint-2026-09-17-before-from-zero` on
  `main`, and commit `647dc45` on this branch.
- **Acceptance that was actually run**: the three `--debug` walks, each with its
  printed run-directory key (the keys are in the Comments below), and
  `run.py selfcheck` exit 0.

Write it in English, in the file's existing entry format, and change no other
entry.

## Acceptance

Run from the repo root and paste the real output. `$PR` is
`/home/y-guo/reproduce/new1/external/probe-env/bin/python`.

**Scope note.** Ticket 17 rewrites `CLAUDE.md` in this same wave, so in your
worktree `CLAUDE.md` still names `legacy/` and `ops/`. C9 below is therefore
**scoped to the code directories and `README.md`**; the main session re-runs it
over `CLAUDE.md` and `.claude/` after the wave merges.

**C9 — `legacy/` is gone and nothing refers to it.**
```bash
git ls-files legacy | wc -l                       # expect: 0
test ! -e legacy && echo ok-gone
grep -rn "legacy" run.py constants experimental_settings data models agent \
     train eval jobs tests README.md || echo ok-noref
grep -n "legacy\|fig1_pilot\|traj_pipeline\|benchmark_design" .gitignore \
     || echo ok-gitignore
```
Expected: `0`, `ok-gone`, `ok-noref`, `ok-gitignore`. The greps name the code
directories explicitly and **never start at the repo root**, because a recursive
grep from the root walks the multi-gigabyte `external/` clone tree.
**`envs/` is deliberately not in the `.gitignore` grep**: those rules stay
(section 1), and `C10` is what proves the boundary still holds. The `ok-noref`
grep looks for the bare word `legacy` in code because `legacy/` is deleted, so a
ported file that cites its source in a comment would leave a dangling reference;
the spec's section 5 tells every implementer to keep the citation in the ticket
and in the report and out of the shipped source, and this is where that is
checked.

**C10 — the `.gitignore` boundary still holds.**
```bash
git check-ignore -v external/probe-env external/appworld external/vllm-env \
    envs/appworld envs/cuda-compat-13.0 envs/vllm-env envs/runs envs/toolhop \
    envs/stabletoolbench envs/alfworld/venv envs/alfworld/data envs/alfworld/logs \
    jobs/runs.jsonl.lock .claude/settings.local.json
git check-ignore jobs/runs.jsonl jobs/RESULTS.md README.md envs/alfworld/splits/train.txt ; echo "exit=$?"
git ls-files '*.tex' | wc -l
git ls-files envs | wc -l
```
Expected: the first command prints a matching rule for **every one** of the
fourteen paths — the three `external/` symlinks, the six `envs/` directories and
symlinks, the three `envs/alfworld/` entries, the lock and the local settings
file; the second exits 1 with no output (**none** of those four is ignored — the
registry rows, the rendered table, `README.md` and the tracked AppWorld-side
split list are in git); the third prints `0`, which is what licenses dropping the
LaTeX block; the fourth prints `4`, the tracked `envs/alfworld/splits/` files,
unchanged from before the edit.

**C5 — `run.py selfcheck` is green after the deletion.**
```bash
"$PR" run.py selfcheck; echo "rc=$?"
```
Expected: `selfcheck: 31 python files, 0 problems`, `rc=0`. This is the check
that proves nothing in the new tree depended on `legacy/`.

**C6 — the file count and the README cover.**
```bash
find run.py constants experimental_settings data models agent train eval jobs \
     -name '*.py' | wc -l
find run.py constants experimental_settings data models agent train eval jobs \
     -name '*.py' | while read -r f; do grep -qF "$f" README.md || echo "MISSING $f"; done
```
Expected: `31`, and no `MISSING` line.

**C16 — the `docs/` move landed and nothing still points at the old path.**
```bash
test ! -e docs && echo ok-docs-moved
test -f notes/docs/agents/issue-tracker.md && echo ok-issue-tracker
grep -rnE '(^|[^/])docs/agents' CLAUDE.md README.md .claude --include='*.md' \
  || echo ok-no-bare-docs-path
git log --diff-filter=R --name-status -1 -- notes/docs | head -5
```
Expected: `ok-docs-moved` and `ok-issue-tracker`. The grep is **expected to print**
in your worktree, where ticket 17's rewrites are absent: on 2026-09-20 it prints
`CLAUDE.md:69`, `CLAUDE.md:70` and `.claude/skills/ticket-run/SKILL.md:27`. Those
are ticket 17's to fix, not yours: paste them in your report and do not edit
those files. The main session re-runs this grep after the wave merges and requires
`ok-no-bare-docs-path` there. The last command is informational; the rename may not be committed
yet when you run it, since the workflow commits.

**C14 — the TIMELINE entry is on top and names the real keys.**
```bash
head -40 notes/TIMELINE.md
grep -c "checkpoint-2026-09-17-before-from-zero" notes/TIMELINE.md
grep -c "647dc45" notes/TIMELINE.md
git diff --stat notes/TIMELINE.md
```
Expected: the new entry at the top of the file; `1` and `1`; and a stat showing
**only additions** to `notes/TIMELINE.md` — no existing line changed.

**C15 — the working tree is clean once the commit lands.**
```bash
git status --porcelain | grep -v '^$' || echo ok-clean
```
Expected: `ok-clean` after the workflow commits. Do not commit yourself; the
workflow commits.

### GPU / main session — not yours

None in this ticket. Its gate — the three end-to-end `--debug` walks and the GPU
list of the construction plan's section 2 — was run by the main session before
this wave was dispatched.

## Comments

The main session fills in, before dispatching this ticket, the run-directory keys
the three `--debug` walks produced, so the TIMELINE entry can quote them:

```
baseline    gpt_oss_120b_appworld   --debug   sample=<key>  score=<key>
train_probe ctool_qwen3_0pt6b   --debug   sample=<key>  build=<key>  train=<key>  eval=<key>
train_probe cgen_qwen3_0pt6b    --debug   train=<key>   eval=<key>
train_probe cparam_qwen3_0pt6b  --debug   train=<key>   eval=<key>
inject      probe_p1_e1_theta_0pt80   --debug   inject=<key>  score=<key>
run.py selfcheck: <the line it printed>
```

- 2026-09-18, from gyb (wave 2/3 review): one rename is deferred to the end of the
  build, after every wave has merged, and is the owner's change to the fixed tree, not
  this ticket's: `data/training_data.py` -> `data/training_data_format.py`,
  `data/trajectory_record.py` -> `data/trajectory_record_format.py`,
  `data/probe_output.py` -> `data/probe_output_format.py`, with the first docstring
  line of `data/training_data.py` rewritten to say what the file is for. The note that
  carries the details is the `TODO(gyb, 2026-09-18)` comment at the top of
  `data/training_data.py`. Whoever dispatches this ticket asks gyb whether the rename
  runs before it or after it; `C6` and `C9` here count and grep file names.
