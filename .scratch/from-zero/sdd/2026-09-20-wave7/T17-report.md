# T17 report — CLAUDE.md, exp-status, the agents and the remaining skills

Branch: `ticket/2026-09-20-wave7/T17`, base `8fc75af3b6c601eb48a31eff3e01865b55fbab1f`,
head `7db4c0b`.

## What was done

One rewrite and eight sets of path-and-command edits, exactly the files the ticket names.
No Python file was touched.

1. **`CLAUDE.md`** — rewritten in place. It states the six things the ticket ordered: the
   tree with `README.md`'s pointer; `run.py` as the one command with its ten reserved
   subcommands and the "underlying modules are never called by hand" rule; GPU runs go
   through the gpu-run skill, an agent never starts one; the five record layers with their
   new paths and the run key as the single primary key (`<stage>-<key>` names the run
   directory, the tmux session, the registry row and the commit message); the owner's two
   hook-protected settings files, with the Bash-heredoc trap named and `CLAUDE.md` itself
   written with the Write tool as the escape from it; the iron rules unchanged in
   substance; the ticket-execution paths moved to `notes/docs/agents/`. Dropped: the
   "Layout during construction" section, the "old rules do not apply until rewritten"
   sentence, and every retired-registry / `MAP.md` / `ops/` mention.
2. **`.claude/skills/exp-status/SKILL.md`** — path and source edits only, the method
   untouched. Every `TIMELINE.md` / `RESULTS.md` / `runs.jsonl` / `WORKPLAN.md` /
   `DATA.md` / `plans/` occurrence takes its new prefix (`notes/` or `jobs/`); `ops/jobs.json`
   is replaced by "`run.py ls` — what's running now (there is no separate job ledger)"; one
   new sentence was added to the read list, that a run's own numbers live in `done.json`
   and reach the finish row verbatim, so a status pass never parses a training log.
3. **`.claude/agents/gpu-runner.md`** — command edits. The launch block becomes
   `run.py <workflow> <setting> [--debug] [--allow-dirty] [section.field=value ...]`; the
   old three-way registration paragraph collapses into one sentence (the launcher writes
   the start row, `meta.json` and `settings.yaml` inside one lock hold); the two queueing
   launchers, `RUNMETA.json` and the `--run-id`/`--track` flags are gone (there is no
   separate queue and no `run_id` typed by hand); `--refire` becomes
   `run.py refire <workflow> <setting> <stage> --piece i`, with no quota; the ledger
   allowlist takes `jobs/runs.jsonl`, `jobs/RESULTS.md`, `*.lock`. The stale reference to
   the (now-deleted, per ticket 16) `launch-methodology.md` file was also repointed to
   `.claude/skills/gpu-run/SKILL.md` itself — not separately named by the ticket, but the
   same paragraph the ticket's lines 28-29 sit inside; see concerns below.
4. **`.claude/agents/job-monitor.md`** — command edits. Its whole source of truth becomes
   `run.py ls`, which computes verdict/rate/ETA fresh on each call from the run's own
   heartbeat files; the resident sampler, its freshness threshold and the
   "Division of labor with the incident agent" section (with its `incidents.jsonl` /
   escalation-spawns-a-process description) are gone, matching gpu-run skill's own
   "What is gone" list (there is no sampler and no incident agent). The stale
   `monitor-methodology.md` reference was repointed the same way as gpu-runner.md's.
5. **`.claude/agents/env-runner.md`** — one deletion. Rule 8 ("A registered task goes
   through run.py", citing `run.py list` and a task registry) is deleted whole; rule 9
   renumbers to 8. Rule 7's cross-reference ("subject to rule 7") still points correctly.
6. **`.claude/skills/handoff/SKILL.md`** — path edits only, method untouched. The
   frontmatter's bare `runs.jsonl` takes the `jobs/` prefix; Phase 1 item 1
   (`run.py gpu-jobs json` + sampler + `localhost:8377`) becomes `run.py ls`, computed
   fresh with no sampler; item 3's `tail ops/runs.jsonl` becomes `tail jobs/runs.jsonl`
   (`registry.open_runs()`); item 4's bare `WORKPLAN.md`/`TIMELINE.md` take the `notes/`
   prefix; the "Running tasks" template line's source becomes `run.py ls`.
7. **`.claude/skills/paper-write/SKILL.md`** — path edits only, method untouched. The two
   `ops/runs.jsonl` mentions (provenance rule, sourcing-discipline bullet) take the
   `jobs/` prefix, the bare `RESULTS.md` mention becomes `jobs/RESULTS.md`, and the bare
   `TIMELINE.md` in the wrap-up bullet (line 83, not in the ticket's numbered list but
   caught by its general rule) takes the `notes/` prefix.
8. **`.claude/skills/ticket-run/SKILL.md`** — hard-rule and path edits. Line 27's two
   `docs/agents/*.md` paths take the `notes/docs/agents/` prefix. The precheck bullet and
   the "Hard-rule wiring" bullet both replace "bypassing the run.py registry" /
   "the run.py registry three-piece update" with the branch rule (a file's five
   annotation lines go into `README.md`, proved by `run.py selfcheck`), and both take
   `jobs/RESULTS.md`. No `MAP.md` sentence was found anywhere in this file to delete (see
   concerns).
9. **The four role prompts** — `.scratch/from-zero/prompts/implementer.md`'s three
   `legacy/`-carrying lines (9, 50, 52 — confirmed by
   `grep -n 'legacy/' .scratch/from-zero/prompts/implementer.md`, still exactly those
   three on 2026-09-20) were rewritten first, verbatim to the ticket's three worked
   examples. All four files
   (`implementer`, `reviewer`, `re-reviewer`, `final-reviewer`) were then copied into
   `.claude/skills/ticket-run/prompts/`, replacing the old copies whole; the other three
   were already byte-identical so `git diff` shows no change to them.

## How it was verified

Run from the worktree root with
`PR=/home/y-guo/reproduce/new1/external/probe-env/bin/python` (interpreter resolved
against the main repo, since `external/` is git-ignored and not materialized in the
worktree — the scripts themselves are pure stdlib and path-independent).

**C7 — no retired command survives.**
```
$ "$PR" <C7 script>
exempt range: [('.claude/skills/gpu-run/SKILL.md', 247, 269)]
C7 ok
```
Exit 0. The exempt range is ticket 16's `## What is gone` list (lines 247-269 of
`.claude/skills/gpu-run/SKILL.md` on this tree), quoted as printed.

**C8 — every named `run.py` subcommand exists.**
```
$ "$PR" <C8 script>
exempt range: [('.claude/skills/gpu-run/SKILL.md', 247, 269)]
named: ['free', 'kill', 'ls', 'refire', 'retry', 'selfcheck', 'sync', 'table', 'train_probe', 'where']
missing: []
C8 ok
```
Exit 0. `named` is a subset of `free, ls, where, find, kill, refire, retry, table, sync,
selfcheck` plus a workflow-file name (`train_probe`), matching the expected shape exactly.

**C11 — the diff of the seven edited documents is paths and command names only.**
```
$ git diff --stat 8fc75af..HEAD -- .claude/skills/exp-status .claude/skills/handoff \
    .claude/skills/paper-write .claude/skills/ticket-run .claude/agents
 .claude/agents/env-runner.md                     |   9 +-
 .claude/agents/gpu-runner.md                     | 115 +++++++++--------------
 .claude/agents/job-monitor.md                    |  65 +++++--------
 .claude/skills/exp-status/SKILL.md               |  44 +++++----
 .claude/skills/handoff/SKILL.md                  |  16 ++--
 .claude/skills/paper-write/SKILL.md              |   6 +-
 .claude/skills/ticket-run/SKILL.md               |  15 +--
 .claude/skills/ticket-run/prompts/implementer.md |  55 +++++++----
 8 files changed, 147 insertions(+), 178 deletions(-)
```
One sentence per file, as C11 asks:
- `exp-status/SKILL.md`: every ledger path moved, `ops/jobs.json` replaced by
  "`run.py ls`", one sentence added about `done.json` as the numbers' source.
- `handoff/SKILL.md`: the sampler-based probe step becomes `run.py ls`, the ledger paths
  moved.
- `paper-write/SKILL.md`: the two `ops/runs.jsonl` and one `RESULTS.md`/`TIMELINE.md`
  mention moved to their `jobs/`/`notes/` prefix.
- `ticket-run/SKILL.md`: the issue-tracker path moved, the retired registry hard rule
  replaced by the branch's README-annotation rule.
- `env-runner.md`: rule 8 (task-registry) deleted whole.
- `gpu-runner.md`: the whole launch mechanism rewritten from the task-registry `launch`
  command to `run.py <workflow> <setting>`.
- `job-monitor.md`: the whole source-of-truth rewritten from `gpu-jobs json` + sampler to
  `run.py ls`, the incident-agent section deleted.
(`gpu-runner.md`/`job-monitor.md` are ticketed as "command edits", a wider scope than the
"path edits only" skills, and the check script itself only prints the full diff for the
three skill directories, not `.claude/agents` — consistent with that wider scope.)

**C12 — the prompts are one copy, not two.**
```
$ for f in implementer reviewer re-reviewer final-reviewer; do
  diff -q .scratch/from-zero/prompts/$f.md .claude/skills/ticket-run/prompts/$f.md && echo "same $f"
done
same implementer
same reviewer
same re-reviewer
same final-reviewer
```

**C13 — `CLAUDE.md` says the five things.**
```
$ grep -c "run.py" CLAUDE.md            -> 5
$ grep -c "jobs/runs.jsonl" CLAUDE.md   -> 2
$ grep -c "jobs/RESULTS.md" CLAUDE.md   -> 2
$ grep -c "models/table.yaml" CLAUDE.md -> 3
$ grep -c "notes/TIMELINE.md" CLAUDE.md -> 4
$ grep -c "Layout during construction" CLAUDE.md -> 0
```
All five non-zero, the last zero, as expected.

**C15 — no old ledger path survives.**
```
$ "$PR" <C15 script>
C15 ok
```
Exit 0. (Two rounds: the first run flagged three bare mentions inside `CLAUDE.md`'s own
`notes/` bullet — `TIMELINE.md`, `WORKPLAN.md`, `DATA.md`, `plans/` written bare while
describing what lives inside `notes/`; these were reworded to their full `notes/...`
paths, matching the pattern the ticket already used for `exp-status`'s bare mentions.)

**C5 — `run.py selfcheck` regression check.**
```
$ "$PR" run.py selfcheck; echo "rc=$?"
selfcheck: 31 python files, 0 problems
rc=0
```
Matches expected exactly.

## Commit list

- `0e538a9` — CLAUDE.md rewritten for steady state, construction layout dropped.
- `5c4a1cb` — exp-status skill moves its ledger paths to the new tree.
- `7ca2cfc` — the three GPU agents drop the retired task registry and sampler.
- `ac5b6fe` — handoff and paper-write skills move their ledger paths, no method change.
- `7db4c0b` — ticket-run prompts become one copy, and the SKILL.md path/hard-rule edits.

## Self-review findings and open questions

1. **The ticket's "the `MAP.md` sentence is deleted (there is no `MAP.md`)" instruction
   for `ticket-run/SKILL.md` has no target.** `grep -ni "map" .claude/skills/ticket-run/SKILL.md`
   returns nothing on this tree — the file carries no `MAP.md` sentence to delete. The
   only place a `MAP.md` line existed on this tree was the *old* copy at
   `.claude/skills/ticket-run/prompts/implementer.md` (line 31, "the corresponding line
   in the code map `MAP.md` updated in sync"), which is superseded, not edited, by the
   wholesale copy from `.scratch/from-zero/prompts/implementer.md` in section 4 — that
   copy carries no `MAP.md` line either, so the net effect the ticket describes ("there is
   no `MAP.md`") holds; nothing further needed changing.
2. **Two dangling file references, not named by the ticket's line list, were fixed as
   part of the same paragraphs the ticket did ask me to edit.** `gpu-runner.md` (lines
   20-32) and `job-monitor.md` (lines 20-29) each pointed at
   `.claude/skills/gpu-run/references/{launch,monitor}-methodology.md`, both deleted by
   ticket 16 (confirmed: `.claude/skills/gpu-run/` on this tree holds only `SKILL.md` and
   `references/gpu_state.md`). Both now point at `.claude/skills/gpu-run/SKILL.md`
   itself, since that ticket folded both methodology files into the one skill document.
   This is a small addition beyond the ticket's literal line numbers, done because it sits
   inside the same paragraph those line numbers name and because leaving a broken file
   reference in an agent-facing document seemed worse than the small addition; flagging
   it here rather than treating it as silently in-scope.
3. **`gpu-runner.md`'s smoke-test item (point 4, "fire a smoke run with a few dozen data
   points") was left as prose**, not rewritten to the formal `--debug` mechanism the rest
   of the tree now uses for smoking a setting. It carries no retired token and sits
   outside the ticket's line list, so I left it — but it now describes an ad-hoc procedure
   next to a codebase that has a named, contracted one. Worth a line item in a future
   ticket, not done here as it would be scope beyond what T17 asked for.
4. **`notes/docs/agents/issue-tracker.md` and `notes/docs/agents/triage-labels.md` do not
   exist yet** on this tree (`notes/docs/` is not created until ticket 18's
   `git mv docs notes/docs`, later in this same wave). `CLAUDE.md` and
   `ticket-run/SKILL.md` now cite paths that don't resolve until ticket 18 lands — the
   same forward-reference pattern ticket 16's own report recorded for the repo-review
   skill's citation of the same two paths.
5. No GPU work and no ambiguity blocked any part of this ticket; nothing was needed from
   the main session.
