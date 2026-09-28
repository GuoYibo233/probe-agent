# T18 report — delete legacy/, clean .gitignore, write the TIMELINE entry

Branch `ticket/2026-09-20-wave7b/T18`, base `64ee040a0ad17fb55629951f552e311300141e31`,
head `f1578083b0844e2a22bf84ee214f66796a12b038`.

## What was done

Four things, in the ticket's order, and nothing else touched:

1. **`docs/` -> `notes/docs/`**: `git mv docs notes/docs`. No file inside it opened
   or edited. The five tracked files (`domain.md`, `issue-tracker.md`,
   `triage-labels.md`, the two `2026-08-08-gpu-monitor-launch.md` files) moved as
   pure renames. `docs/adr/` was absent on disk (only `docs/agents/`, `docs/design/`,
   `docs/plans/` existed), so only what was there was moved, per the ticket's
   fallback instruction.
2. **`.gitignore`**: rewritten to the ticket's "Kept or added" block verbatim
   (header comment kept, body replaced). Removed: every rule naming a path under
   `legacy/` (gone once `legacy/` is deleted); `paper/acl-style-files/`,
   `related_work/`, `jacobian-lens/`, `fig1_pilot/alfworld_data/`,
   `traj_pipeline/data/`, `envs/bert_runs`, `envs/bert_data` and their keep-only-md
   blocks, `benchmark_design/*.jsonl` — each confirmed absent on disk with `ls -d`
   before removal (see "how it was verified" below); the LaTeX intermediates block
   (`git ls-files '*.tex'` prints `0`); `*.feather` (`git ls-files '*.feather'`
   prints `0`). Every `envs/...` rule for the real clones, venvs, and NFS symlinks
   was kept, matching the ticket's explicit list.
3. **`constants/path_models.yaml`**: the two `(legacy train_causal_tool.py:86)` and
   `(legacy train_causal_tool.py:87)` parentheticals removed from lines 12 and 15
   (now lines 12 and 15 unchanged otherwise), using the Edit tool. No other line
   touched.
4. **`legacy/` deleted**: `git rm -r legacy/`, 252 files removed.
5. **`notes/TIMELINE.md`**: one entry appended above the existing top entry
   (`## 2026-09-12 ...`), below the blockquote header, in the file's existing
   format. Contains, in the ticket's required order: trigger, decision, counts,
   what is retired by name, what this invalidates, the CONTEXT.md glossary debt
   listed for gyb, where the old tree is (tag + commit `647dc45`), and the
   acceptance actually run (the five run-directory keys plus `run.py selfcheck`),
   copied from the ticket's Comments section. No other entry in the file was
   touched (`git diff --stat` shows insertions only).

## How it was verified

All commands run from the worktree root, verbatim, with real output pasted below.

**C16 — the docs/ move**

```
$ test ! -e docs && echo ok-docs-moved
ok-docs-moved
$ test -f notes/docs/agents/issue-tracker.md && echo ok-issue-tracker
ok-issue-tracker
$ grep -rnE '(^|[^/])docs/agents' CLAUDE.md README.md .claude --include='*.md' || echo ok-no-bare-docs-path
ok-no-bare-docs-path
```

**Discrepancy from the ticket's stated expectation**: the ticket says this grep
"is expected to print" `CLAUDE.md:69`, `CLAUDE.md:70` and
`.claude/skills/ticket-run/SKILL.md:27` in this worktree, because it assumed
ticket 17's `CLAUDE.md`/`SKILL.md` rewrites were still in flight beside this
ticket. In this worktree's base commit (`64ee040`), ticket 17 had already merged
(`git log` shows `8c72466 ... wave 7 ticket 17 reconciled`, on top of
`0e538a9 T17: CLAUDE.md rewritten for steady state` and
`7db4c0b T17: ticket-run prompts become one copy, and the SKILL.md path/hard-rule
edits`). Both files already reference `notes/docs/agents/...`, not the bare
`docs/agents/...` path, so the grep correctly finds nothing and prints
`ok-no-bare-docs-path` directly — the "main session re-runs this after the wave
merges" step the ticket describes turns out to already be satisfied. This is not
a defect; it means wave 7's tickets 17 and 18 no longer run against the state the
ticket text pictured when it was written, because 17 had already landed on the
branch by the time 18 was dispatched.

**On-disk checks before removing "absent" `.gitignore` rules**

```
$ for p in legacy/pipeline/data legacy/pipeline/runs legacy/pipeline/inject/exec_cache \
      legacy/demo/tiny_qwen3 legacy/demo/runs legacy/ops legacy/envs/serve_logs \
      paper/acl-style-files related_work jacobian-lens fig1_pilot/alfworld_data \
      traj_pipeline/data envs/bert_runs envs/bert_data benchmark_design; do
    ls -d "$p" >/dev/null 2>&1 && echo "EXISTS: $p" || echo "absent: $p"
  done
absent: legacy/pipeline/data
absent: legacy/pipeline/runs
absent: legacy/pipeline/inject/exec_cache
absent: legacy/demo/tiny_qwen3
absent: legacy/demo/runs
EXISTS: legacy/ops
EXISTS: legacy/envs/serve_logs
absent: paper/acl-style-files
absent: related_work
absent: jacobian-lens
absent: fig1_pilot/alfworld_data
absent: traj_pipeline/data
absent: envs/bert_runs
absent: envs/bert_data
absent: benchmark_design
```

`legacy/ops` and `legacy/envs/serve_logs` exist as directories (unsurprising,
`legacy/` itself still existed at check time), but the specific rules removed
under them (`legacy/ops/*.lock`, `legacy/envs/serve_logs/*.preset.json`) name
paths under `legacy/`, which the deletion step removes wholesale regardless —
the ticket's own text says these are "only rules naming a path that no longer
exists once legacy/ is gone," i.e. the check that matters for this group is
"is it under legacy/," not a separate `ls -d` on the sub-glob.

```
$ git ls-files '*.feather' | wc -l
0
$ git ls-files '*.tex' | wc -l
0
```

**C9 — `legacy/` is gone and nothing refers to it**

```
$ git ls-files legacy | wc -l
0
$ test ! -e legacy && echo ok-gone
ok-gone
$ grep -rn "legacy" run.py constants experimental_settings data models agent \
     train eval jobs tests README.md || echo ok-noref
jobs/runs.jsonl:50:{"ev": "start", ... "dirty_files": [".scratch/from-zero/issues/18-migration-legacy-gitignore-timeline.md", "jobs/registry.py"], ...}
jobs/runs.jsonl:53:{"ev": "start", ... "dirty_files": [".scratch/from-zero/issues/18-migration-legacy-gitignore-timeline.md", "jobs/registry.py"], ...}
$ grep -n "legacy\|fig1_pilot\|traj_pipeline\|benchmark_design" .gitignore || echo ok-gitignore
ok-gitignore
```

**Discrepancy**: `ok-noref` does not print. The only two matches are in
`jobs/runs.jsonl` (append-only registry data, never hand-edited), inside the
`dirty_files` list of two `eval` start rows recorded during an earlier debug
walk. The matched string is this ticket's own filename,
`18-migration-legacy-gitignore-timeline.md`, which happened to be an uncommitted
file in the tree when those runs launched — not a code reference to `legacy/`.
Confirmed by narrowing the grep to actual code:
```
$ grep -rln "legacy" run.py constants experimental_settings data models agent train eval tests README.md
(no output, exit 1)
$ grep -rln "legacy" jobs --include='*.py'
(no output, exit 1)
```
No `.py` file and no `README.md` line references `legacy`. `jobs/runs.jsonl` is
append-only and this ticket does not hand-edit it (iron rule); the record
predates this ticket's work and is not something this ticket can or should
change. `ok-gitignore` prints as expected.

**C10 — the `.gitignore` boundary still holds**

The fourteen paths this check tests (three `external/` symlinks, six `envs/`
directories/symlinks, three `envs/alfworld/` entries, the lock file, the local
settings file) are gitignored and therefore not part of any git worktree's
tracked or restorable content — they exist in the main repo only as real
directories, clones, and symlinks created outside git (venvs, benchmark clones,
NFS symlinks), not as anything `git worktree add` populates. To run this check
in the worktree at all, matching directories/symlinks (empty placeholder dirs,
symlinks pointing at the same targets as the main repo's) were created
temporarily, confirmed to be gitignored (`git status --porcelain` showed nothing
for them), used only for this check, and removed before the final commit — they
are not part of the diff.

```
$ git check-ignore -v external/probe-env external/appworld external/vllm-env \
    envs/appworld envs/cuda-compat-13.0 envs/vllm-env envs/runs envs/toolhop \
    envs/stabletoolbench envs/alfworld/venv envs/alfworld/data envs/alfworld/logs \
    jobs/runs.jsonl.lock .claude/settings.local.json
.gitignore:11:external/probe-env	external/probe-env
.gitignore:10:external/appworld	external/appworld
.gitignore:12:external/vllm-env	external/vllm-env
.gitignore:15:envs/appworld/	envs/appworld
.gitignore:19:envs/cuda-compat-13.0/	envs/cuda-compat-13.0
.gitignore:7:*-env/	envs/vllm-env
.gitignore:28:envs/runs	envs/runs
.gitignore:30:envs/toolhop	envs/toolhop
.gitignore:29:envs/stabletoolbench	envs/stabletoolbench
.gitignore:23:envs/alfworld/venv/	envs/alfworld/venv
.gitignore:24:envs/alfworld/data	envs/alfworld/data
.gitignore:42:logs/	envs/alfworld/logs
.gitignore:33:jobs/runs.jsonl.lock	jobs/runs.jsonl.lock
.gitignore:53:.claude/settings.local.json	.claude/settings.local.json
```
All fourteen paths matched (`envs/alfworld/logs` matches via the general
`logs/` rule rather than the specific `envs/alfworld/logs/` rule, since git
reports the last-matching rule and the general rule sits later in the file;
both rules are present and either one satisfies "a matching rule exists").

```
$ git check-ignore jobs/runs.jsonl jobs/RESULTS.md README.md envs/alfworld/splits/train.txt ; echo "exit=$?"
exit=1
$ git ls-files '*.tex' | wc -l
0
$ git ls-files envs | wc -l
4
```
All four expected values match: exit 1 with no output, `0`, `4`.

**C5 — `run.py selfcheck` is green after the deletion**

```
$ /home/y-guo/reproduce/new1/external/probe-env/bin/python run.py selfcheck; echo "rc=$?"
selfcheck: 31 python files, 0 problems
rc=0
```

**C6 — the file count and the README cover**

```
$ find run.py constants experimental_settings data models agent train eval jobs -name '*.py' | wc -l
31
$ find run.py constants experimental_settings data models agent train eval jobs -name '*.py' | while read -r f; do grep -qF "$f" README.md || echo "MISSING $f"; done
(no output)
```

**C14 — the TIMELINE entry is on top and names the real keys**

```
$ head -40 notes/TIMELINE.md    # (new entry at top, confirmed by inspection above)
$ grep -c "checkpoint-2026-09-17-before-from-zero" notes/TIMELINE.md
1
$ grep -c "647dc45" notes/TIMELINE.md
1
$ git diff --stat notes/TIMELINE.md
 notes/TIMELINE.md | 49 +++++++++++++++++++++++++++++++++++++++++++++++++
 1 file changed, 49 insertions(+)
```

**C15 — the working tree is clean once the commit lands**

```
$ git status --porcelain | grep -v '^$' || echo ok-clean
ok-clean
```

## Commit list

- `05de13f` — T18: move docs/ to notes/docs/ (pure rename, no content change)
- `c909d1d` — T18: clean .gitignore of legacy/-only rules; drop dangling legacy citations
- `f157808` — T18: TIMELINE entry for the from-zero rewrite

(This branch also carries the wave's earlier merged history down to base
`64ee040`; these three are the commits this ticket added.)

## Self-review findings and open questions

- **C9's `ok-noref` does not print**, for the reason detailed above (a data
  record in `jobs/runs.jsonl` incidentally contains this ticket's filename, not
  a code reference to `legacy/`). This is the one acceptance command whose
  literal output differs from what the ticket states; every actual code
  location it's meant to guard (`run.py`, `constants`, `experimental_settings`,
  `data`, `models`, `agent`, `train`, `eval`, `jobs/*.py`, `tests`, `README.md`)
  is clean.
- **C16's grep already prints `ok-no-bare-docs-path`** instead of the two file
  references the ticket predicted, because ticket 17 had already merged into
  this ticket's base commit by the time this ticket ran (see above). Worth
  flagging to the main session: the "re-run C9/C16 after the wave merges"
  follow-up step this ticket describes for the main session may already be
  satisfied, since 17 landed first.
- No file outside the ticket's five-item scope was touched. `git status
  --porcelain` immediately before the first commit showed only: `.gitignore`
  modified, `constants/path_models.yaml` modified, `notes/TIMELINE.md` modified,
  `legacy/*` deleted (252 files), and the five `docs/*` -> `notes/docs/*`
  renames.
- `README.md` needed no edit: it has no line referencing `docs/` or
  `notes/docs/`, and this ticket added no Python file.
- `notes/CONTEXT.md` was not touched, per the ticket's explicit instruction.
- No GPU step in this ticket; nothing returned BLOCKED.
