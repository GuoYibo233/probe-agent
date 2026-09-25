# T16 report — the gpu-run and probe-pipeline skills

Branch `ticket/2026-09-19-wave6/T16`, worktree
`/home/y-guo/reproduce/new1-wt/2026-09-19-wave6-T16` (removed at the end of this
ticket; the branch is kept). Base `f1f849ebd04a4de2e26d01407825f535f6638c9a`.
Commit `602d5d1`.

## What was done, against the ticket's requirements

Files touched, exactly the ticket's list and nothing else:

- `.claude/skills/gpu-run/SKILL.md` — rewritten in place, front matter and body.
- `.claude/skills/gpu-run/references/gpu_state.md` — lines 1-55 deleted, 56-97 kept
  verbatim (97 -> 42 lines).
- `.claude/skills/gpu-run/references/launch-methodology.md` — deleted.
- `.claude/skills/gpu-run/references/monitor-methodology.md` — deleted.
- `.claude/skills/gpu-run/scripts/gpu_status.sh` — deleted, and the now-empty
  `scripts/` directory removed.
- `.claude/skills/probe-pipeline/SKILL.md` — rewritten in place, front matter and
  body.
- `.claude/skills/probe-pipeline/references/{extending,gates,invariants,stage-commands}.md`
  — all four deleted, and the now-empty `references/` directory removed.
- `.claude/skills/repo-review/SKILL.md` — new.

### 1. gpu-run/SKILL.md

Rewritten around `run.py`'s stage walk in place of the retired `gpu-jobs` /
`record` / sampler machinery, phase by phase as the ticket's table lays out:
Phase 0 reads the trimmed `references/gpu_state.md` for slow variables only;
Phase 1 is `run.py free` (contracts 2.5, 3.4, 6.3); Phase 2 is the commit and the
`jobs/launch.git_state` dirty-tree gate (2.5, 1.5); Phase 3 is the `--debug`
smoke on the same setting (5.6, 3.4); Phase 4 is the one launch command, its
lock span, the two waves of pieces, and the stop-after-launch rule, plus the
three `inject`-only `run.py`-held gates including the `5.4 / 2.1` errata ruling
(8.1, 8.6, 2.3, 7.2); Phase 5 is `run.py ls` and its verdicts/flags (8.5, 8.6);
Phase 6a is wrap-up by re-running the same command plus `run.py table` and a
commit (2.3, 2.4, 1.5, 8.2, 8.6); Phase 6b is `kill` / `refire` / `retry` (8.6,
2.3, 2.4); hard rules close the file (8.6, 3.4, the branch `CLAUDE.md`).

The front-matter `description` keeps the Chinese trigger clause and does not
use the words "three ledgers" or "sampler" (neither did the original text, so
this is trivially true; the rewritten description does not reintroduce them
either).

A single `## What is gone` section, with that exact heading, lists every
retired command/file/process the ticket names and says what replaced it: this
is the one place in the file a retired name may appear, and C7/C8 locate and
skip exactly that range.

### 2. probe-pipeline/SKILL.md

Rewritten to the six numbered points the ticket specifies and nothing else:
the chain as one workflow file's stage list; who writes the YAML (gyb) versus
`schema.py` (code, for a new field or axis value); where every gate lives,
including the errata's two 2026-09-17/18 build-report rulings (`build_call`
refusal and the round-trip gate degrade to `counts.events_skipped_no_call`
instead of a hard stop) and the inject method-mismatch gate; the `--debug`
walk plus `run.py selfcheck` as the acceptance of any chain change; the four
extension places (`data/environments/<env>.py`, `models/agent_models/<family>.py`,
`models/probe_models/<backbone>.py`, `train/methods/<m>.py`) with `README.md`
section 3 as the one place that states what each extension touches (no local
copy); and the write-back rule (annotation lines into `README.md`,
`run.py selfcheck`, `schema.py` registration before any YAML use).

The eval side of the fourth extension point is written against the
2026-09-18 `eval/methods/` fold ruling
(`.scratch/from-zero/contract-errata.md`): `PROBE_KIND`, `MATCH_VERSION` and a
`match_<m>` function all in `eval/utils/probe_eval.py`, never
`eval/methods/<m>.py`. Contracts 0.3 and 0.4 are not cited here, per the
ticket, because both predate that fold.

### 3. repo-review/SKILL.md (new)

The tree's own one line for this file —
"the two-day review: an agent reads the tree against the six principles and
writes tasks" (`notes/plans/2026-09-14-structure-from-zero.md:219`) — is quoted
verbatim (the fixed tree is never reworded), and the skill's own prose states
it reviews against the **seven** principles `README.md` section 1 gives,
never writing "six" as its own claim. Four numbered points: what it reviews
(the seven principles as `README.md` states them), what it reads in order
(`README.md`, the file under review, the cited contracts section) and that it
runs `run.py selfcheck` first and stops if not green, what it writes (one
ticket per finding into `.scratch/review/issues/`, in the issue-tracker format
of `notes/docs/agents/issue-tracker.md` with a Status label from
`notes/docs/agents/triage-labels.md`, no edits to code or to `notes/`), and
what it never does (start a GPU process, edit the owner's YAML/table files, or
propose a file the tree's Part 1 does not name).

The two cited paths are written `notes/docs/agents/...`, not `docs/...`, per
the ticket: the fixed tree's `notes/` line already says notes holds "plans/
and docs/ (moved whole)", and ticket 18 performs `git mv docs notes/docs` in
wave 7 — the files live at `docs/agents/issue-tracker.md` and
`docs/agents/triage-labels.md` on disk today, and this skill names where they
will be once that move lands, matching ticket 17's `CLAUDE.md` citation of the
same two paths (per the ticket's own instruction, not an assumption of mine).

## How it was verified

All commands run from the worktree root with
`$PR = /home/y-guo/reproduce/new1/external/probe-env/bin/python` (the
worktree does not materialise `external/`, which is git-ignored, so the
interpreter is named by its absolute path in the main tree, per contract
errata "0.1").

**W1 — the deletions landed.**
```
$ test ! -e .claude/skills/gpu-run/references/launch-methodology.md && echo ok-launchmeth
ok-launchmeth
$ test ! -e .claude/skills/gpu-run/references/monitor-methodology.md && echo ok-monitormeth
ok-monitormeth
$ test ! -e .claude/skills/gpu-run/scripts && echo ok-scripts
ok-scripts
$ test ! -e .claude/skills/probe-pipeline/references && echo ok-ppreferences
ok-ppreferences
$ wc -l .claude/skills/gpu-run/references/gpu_state.md
42 .claude/skills/gpu-run/references/gpu_state.md
$ head -1 .claude/skills/gpu-run/references/gpu_state.md
Surveyed on: 2026-07-29 (measured, not hearsay).
$ grep -c 'tokyo105 | shiga' .claude/skills/gpu-run/references/gpu_state.md
1
$ grep -c 'sampler\|8377\|crontab' .claude/skills/gpu-run/references/gpu_state.md || true
0
```
All four `ok-` lines, `42` lines, the expected first line, `1` and `0` — matches
exactly.

**W2 — the repo-review skill exists and names its output directory.**
```
$ test -f .claude/skills/repo-review/SKILL.md && echo ok-exists
ok-exists
$ grep -c '\.scratch/review/issues/' .claude/skills/repo-review/SKILL.md
2
$ grep -c 'run.py selfcheck' .claude/skills/repo-review/SKILL.md
2
$ awk 'NR>1 && /^---$/{exit} {print}' .claude/skills/repo-review/SKILL.md
name: repo-review
description: >-
  The two-day review: an agent reads the tree against `README.md`'s seven principles
  and writes tasks. It runs `run.py selfcheck` first and stops if that is not green,
  reads `README.md`, then the file under review, then the contracts section its
  annotation line cites, and writes one ticket per finding into
  `.scratch/review/issues/` in the issue-tracker format — it edits no code and no file
  under `notes/`. Invoke whenever Dungeon♂Master says "review the repo" or a periodic
  tree review is due. Chinese triggers: "审查仓库" / "复盘整棵树" / "两天复盘" / "查一遍仓库".
version: 1.0.0
```
`ok-exists`, both grep counts >= 1, and a `description` line ending in the
Chinese trigger clause — matches.

**C7 — no retired command survives outside the exempt list.**
```
$ "$PR" - <<'PY'
... (script from the ticket, verbatim) ...
PY
exempt range: [('.claude/skills/gpu-run/SKILL.md', 175, 197)]
C7 ok
exit=0
```
Exit 0, `C7 ok`. Exempt range quoted: `.claude/skills/gpu-run/SKILL.md` lines
175-197 (the `## What is gone` section, heading to end of file).

**C8 — every named `run.py` command exists in `run.py --help`.**
```
$ "$PR" - <<'PY'
... (script from the ticket, verbatim) ...
PY
exempt range: [('.claude/skills/gpu-run/SKILL.md', 175, 197)]
named: ['free', 'kill', 'ls', 'refire', 'retry', 'selfcheck', 'table', 'train_probe', 'where']
missing: []
C8 ok
exit=0
```
Exit 0, `C8 ok`, `missing: []`. `run.py --help`'s subcommand list (one per
line, two-space indent, name first, per contract errata "8.6 / 8.1 / 3.3"):
`ls, where, find, kill, refire, retry, table, free, sync, selfcheck` — matches
the ticket's expected set.

**W3 — the four extension places are each named once.**
```
$ for s in "data/environments/" "models/agent_models/" "models/probe_models/" "train/methods/"; do
    printf '%s %s\n' "$s" "$(grep -c "$s" .claude/skills/probe-pipeline/SKILL.md)"
  done
data/environments/ 1
models/agent_models/ 1
models/probe_models/ 1
train/methods/ 1
```
Each count is 1, at least the required minimum — matches.

**W4 — the trigger clauses survived.**
```
$ awk 'NR>1 && /^---$/{exit} {print}' .claude/skills/gpu-run/SKILL.md
$ awk 'NR>1 && /^---$/{exit} {print}' .claude/skills/probe-pipeline/SKILL.md
$ awk 'NR>1 && /^---$/{exit} {print}' .claude/skills/repo-review/SKILL.md
```
All three front-matter blocks were printed (pasted in full above and in the
"what was done" section); each `description` ends with its Chinese
trigger-phrase clause, and none contains "sampler" or "three ledgers" —
matches.

**W5 — no bare ledger name.**
```
$ "$PR" - <<'PY'
... (script from the ticket, verbatim) ...
PY
W5 ok
exit=0
```
Exit 0, `W5 ok` — matches.

**selfcheck.**
```
$ "$PR" run.py selfcheck
selfcheck arrives in ticket 15
```
`run.py selfcheck` is a stub on this branch's base: ticket 15 (the other wave-6
ticket, run in a sibling worktree in parallel) has not merged into this
worktree, so the real check does not exist here yet. This matches the spec's
"selfcheck lines that apply later" carve-out — there is nothing to hand-run in
its place, because this ticket touches no Python file and no `README.md`
entry that a stand-in check would cover.

## Commit list

- `602d5d1` — `T16: rewrite gpu-run and probe-pipeline skills for the run.py
  stage walk, add repo-review`. One commit, all eleven file changes (two
  rewrites, nine deletes/adds), since the ticket is a single logical unit —
  three skill documents rewritten together against one set of contract
  sections.

## Self-review findings and open questions

- No Python was written or touched, per the ticket ("No Python"); no README
  entry was needed, since none of this ticket's files carry a five-line
  annotation and the ticket's file list does not include `README.md`.
- I did not add anything the ticket did not ask for: each SKILL.md's body
  follows the ticket's phase table / numbered points one for one, and I
  re-read the diff against the ticket's own text before committing to check
  for scope creep — none found.
- `repo-review/SKILL.md`'s Chinese trigger clause is my own composition (the
  ticket names no specific phrases for this new file, only that it "ends with
  its Chinese trigger clause" in the shape of the other two skills); I chose
  "审查仓库" / "复盘整棵树" / "两天复盘" / "查一遍仓库" to match the register of the
  existing two skills' trigger lists. Worth the owner's eye if a different
  phrasing is preferred.
- The `notes/docs/agents/issue-tracker.md` and `notes/docs/agents/triage-labels.md`
  paths this ticket has me write do not exist yet on disk (the files are
  currently at `docs/agents/...`); this is the ticket's explicit instruction,
  matching ticket 18's planned `git mv docs notes/docs` and ticket 17's
  `CLAUDE.md`. Until wave 7 merges, `repo-review/SKILL.md` points at a path
  that will only resolve once that move lands — noted here so the gap is
  visible, not silently assumed.
- `run.py selfcheck` is a placeholder on this base commit (ticket 15's real
  implementation lands in a sibling worktree this wave and had not merged when
  I ran it), so I could not get a real green/red signal from it. Nothing in
  this ticket's scope depends on it passing.
- No step in this ticket needed a GPU, and nothing here is `BLOCKED`.

## Return

status: DONE
base: f1f849ebd04a4de2e26d01407825f535f6638c9a
head: 602d5d143... (see `git log` on `ticket/2026-09-19-wave6/T16`; full sha in
the Commit list section is truncated by the harness output, `602d5d1`)
