# 17 CLAUDE.md, exp-status, the agents and the remaining skills

Status: ready-for-agent
Blocked by: 15, 16
Spec: .scratch/from-zero/spec.md (sections 1, 5, 7, 9)

## What to do

One rewrite and eight sets of path-and-command edits. No Python. `CLAUDE.md` is
rewritten; **everything else is a path-and-command edit that leaves every method
alone** — a reviewer will read the diff for exactly that.

```
CLAUDE.md                                   rewrite in place
.claude/skills/exp-status/SKILL.md          path and source edits only
.claude/agents/gpu-runner.md                command edits only
.claude/agents/job-monitor.md               command edits only
.claude/agents/env-runner.md                one deletion
.claude/skills/handoff/SKILL.md             path edits only
.claude/skills/paper-write/SKILL.md         path edits only
.claude/skills/ticket-run/SKILL.md          hard-rule and path edits
.claude/skills/ticket-run/prompts/*.md      replaced by .scratch/from-zero/prompts/*.md
.scratch/from-zero/prompts/implementer.md   its `legacy/` lines rewritten first (section 4)
```

### 1. `CLAUDE.md` (repo root) — rewritten

The root rules file stops describing the construction layout of the `from-zero`
branch and becomes the steady-state rules of the new tree. What it must say, and
where each line comes from:

1. **The tree**, one paragraph per layer, and the pointer that `README.md` holds
   one line per file (the tree's Part 1, contracts 0.1).
2. **One command**: every stage is entered through `run.py`; the subcommands are
   `ls, where, find, kill, refire, retry, free, sync, table, selfcheck` and a walk
   is `run.py <workflow> <setting> [--debug]` (8.6). The underlying modules are
   never called by hand (2.6).
3. **GPU runs go through the gpu-run skill**, and an agent never starts a GPU
   process: it returns BLOCKED with the ready-to-run command (kept from the
   branch CLAUDE.md).
4. **Records, five layers, with the new paths**: direction `notes/TIMELINE.md`
   (a person, append-only); numbers `jobs/runs.jsonl` -> `jobs/RESULTS.md`
   (written by `jobs/registry.py`, never by hand); data settings `notes/DATA.md`;
   plan `notes/WORKPLAN.md` (overwritten); raw data on NFS. **The primary key is
   the run key**: the run directory name, the tmux session name, the registry row
   and the commit message all carry it (3.4, 8.1) — this replaces the old
   `run_id`-in-four-places rule.
   **Decision already made (errata):** the file names **five** record layers with
   `jobs/runs.jsonl` and `jobs/RESULTS.md` beside the registry, and **drops the
   claim that the ledgers live in one place** — rendering `RESULTS.md` into
   `notes/` was considered and not applied.
5. **`experimental_settings/` is gyb's**: a hook refuses an agent edit to
   `experimental_settings/*.yaml` **and to `models/table.yaml`** (contracts 6.1
   answers the owner's open question with yes); an agent proposes a setting as a
   task.
6. The iron rules that already hold on the branch, unchanged in substance: large
   outputs to `/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/`, weights to
   `.../models`, uv for environments, complete isolation from
   `/home/y-guo/ACL2026`, no guessing about data results, commit before
   launching, `notes/` is gyb's and an agent appends only a `TIMELINE.md` entry
   when asked, ancient memory (`notes/plans/archive/`) is read only on request,
   everything on disk is English.
7. **Issue tracker and ticket execution**, unchanged in substance, with two path
   moves: the prompts are at `.claude/skills/ticket-run/prompts/`, and the
   conventions are at **`notes/docs/agents/issue-tracker.md`** and
   **`notes/docs/agents/triage-labels.md`** — the fixed tree's `notes/` line says
   notes holds "plans/ and docs/ (moved whole)", and ticket 18 performs the
   `git mv docs notes/docs` in this same wave. Ticket 16's repo-review skill
   cites the same two paths.

**Not carried over:** the "Layout during construction" section (`legacy/` is
deleted in ticket 18); the sentence that the old rules "do not apply on this
branch until the new run.py, jobs/ and the skills are rewritten" (they are); the
`run.py` task registry / `TASKS` / `RECIPES` / `recipe` / `status` / `show`
rules; `MAP.md`; `ops/`; `DATA.md §7`; the four-ledger table's claim that the
ledgers live together; the presets rule; `RUNMETA.json`.

### 2. `.claude/skills/exp-status/SKILL.md` — edited, not rewritten

The "where does this project stand" skill keeps its **whole method** and only has
its ledger paths and its number sources moved to the new tree. By line:

- line 8 (`description`) and lines 145-151 (the read list): `TIMELINE` ->
  `notes/TIMELINE.md`; `RESULTS.md` -> `jobs/RESULTS.md`; `ops/runs.jsonl` ->
  `jobs/runs.jsonl`; `ops/jobs.json` -> **deleted**, replaced by "`run.py ls` for
  what is running now" (there is no separate job ledger, 8.6); `plans/` ->
  `notes/plans/`; `plans/PLAINWORDS.md` -> `notes/plans/PLAINWORDS.md`.
- lines 10, 40, 129, 135, 138, 194, 210, 445: the `plans/STATUS_*.md` path ->
  `notes/plans/STATUS_*.md`.
- line 46: `plans/archive/...` -> `notes/plans/archive/...`, and the
  ancient-memory rule restated (that directory is read only when gyb says so).
- line 508: "never touch `RESULTS.md`" -> "never touch `jobs/RESULTS.md`; it is
  rendered from `jobs/runs.jsonl` by `jobs/registry.py`" (8.6).
- line 511: unchanged in substance (`notes/WORKPLAN.md`, `notes/TIMELINE.md`).
- **The line numbers above are a map, not the rule. The rule is: every
  occurrence** of `TIMELINE.md`, `RESULTS.md`, `runs.jsonl`, `jobs.json`,
  `WORKPLAN.md`, `DATA.md` and `plans/` in the file takes its new path, and `C15`
  below proves it by grep. Two occurrences the numbered list missed are lines 235
  and 248, where `TIMELINE.md` stands bare inside a paragraph of method
  ("Taken from `TIMELINE.md`", "a decision … that `TIMELINE.md` hasn't recorded
  yet") — the method is untouched, only the path moves to `notes/TIMELINE.md`.
  `C7`'s token list has no entry for a bare `TIMELINE.md`, so nothing else would
  have caught them.
- **one new sentence** in the read list: a run's own numbers are in its
  `done.json` (`metrics` and `report`, 1.5) and reach the finish row verbatim, so
  a status pass reads `jobs/runs.jsonl` and the named report file and **never
  parses a training log**.

Not carried over: `ops/jobs.json`, the sampler's history as a source, and the
"which cells are still empty" matrix language that assumed `CELLS` (the table is
now `run.py table`).

### 3. The three agent definitions

These carry the same retired commands and would otherwise be the last place in
the repo telling an agent to type `run.py gpu-jobs` or to read a sampler that no
longer runs. They are in scope for that reason and no other.

- **`.claude/agents/gpu-runner.md`** (lines 28-29, 43-46, 72-73, 81-90, 112,
  141): the launch block becomes `run.py <workflow> <setting>`; the three-ledger
  registration paragraph becomes one sentence (the start row, `meta.json` and
  `settings.yaml` are written by the launcher inside one lock hold, 8.6);
  `--refire` becomes `run.py refire ... --piece i`; the allowlist sentence keeps
  its meaning with the new paths (`jobs/runs.jsonl`, `jobs/RESULTS.md`, `*.lock`,
  2.5).
- **`.claude/agents/job-monitor.md`** (lines 21, 32-36, 46-54, 65-66, 79): its
  whole source of truth changes from `run.py gpu-jobs json` + the sampler to
  `run.py ls`. **The incident paragraph (lines 46-54) is deleted**; there is no
  incident agent.
- **`.claude/agents/env-runner.md`** (lines 82-84): the `run.py list` registry
  sentence is deleted; a CPU stage is started by `run.py` itself (2.3) and there
  is no task registry.

### 4. The three path-only skills

Same defect, smallest possible change; **no method is touched**.

- `handoff/SKILL.md` lines 45, 51, 60: `run.py gpu-jobs json` and the sampling
  history -> `run.py ls`; `tail ops/runs.jsonl` -> `tail jobs/runs.jsonl` (rows
  with a start and no finish are `registry.open_runs()`, 8.0).
- `paper-write/SKILL.md` lines 32, 60: `ops/runs.jsonl` -> `jobs/runs.jsonl`,
  `RESULTS.md` -> `jobs/RESULTS.md`; "traceable to a run_id" keeps its meaning
  (the run_id is still the primary key of a registry row, 8.1).
- `ticket-run/SKILL.md` line 27 (`docs/agents/issue-tracker.md` and
  `docs/agents/triage-labels.md` -> `notes/docs/agents/...`, the same move
  `CLAUDE.md` takes), lines 47, 140 and `ticket-run/prompts/implementer.md`
  lines 22, 30-31, 38: the "run.py registry three-piece update" hard rule is
  replaced by the branch rule — the file's five annotation lines go into
  `README.md` and `run.py selfcheck` proves them; the `MAP.md` sentence is
  deleted (there is no `MAP.md`); the ledger sentence takes the new paths.
  **The four role prompts under `.scratch/from-zero/prompts/`**
  (`implementer.md`, `reviewer.md`, `re-reviewer.md`, `final-reviewer.md`),
  written for this branch in commit `f28474c`, **replace** the copies under
  `.claude/skills/ticket-run/prompts/`, so the branch stops having two versions
  of the same prompt. Copy them over and delete nothing else in that directory.

  **First rewrite every line of `.scratch/from-zero/prompts/implementer.md` that
  carries the token `legacy/`, then copy.** That prompt was written for the
  construction branch, where `legacy/` was the read-only source of the algorithms
  to port; ticket 18 deletes `legacy/` **in this same wave**, so the lines are
  stale, and `C7` below scans every `*.md` under `.claude/` for exactly that
  token — a straight copy makes `C7` fail on a file this ticket just installed,
  while `C12` forbids fixing it in the copy. Rewriting the source is the only
  move that satisfies both. **Find the lines with
  `grep -n 'legacy/' .scratch/from-zero/prompts/implementer.md` and rewrite every
  hit** — the list below is three worked examples, not a count to stop at. On
  2026-09-17 the hits are lines 9, 50 and 52:
  - line 9, today "The construction plan … names, per file, which legacy file
    holds the algorithm to port. `legacy/` is read-only reference: read it, port
    the logic, never import it, never run it." -> "Your ticket names, per file,
    where the algorithm it ports comes from. Read the named source, port the
    logic, and import nothing the tree's `README.md` does not list."
  - line 50, today "Never import from `legacy/`; never edit anything under
    `legacy/` or `notes/`." -> "Never edit anything under `notes/`; never add a
    file the fixed tree does not name."
  - line 52, today "**The legacy citation goes in your report, never in the
    shipped source.** No docstring, comment or variable name mentions `legacy/`:
    that directory is deleted by the last ticket of the build, and ..." ->
    "**Where the code came from goes in your report, never in the shipped
    source.** No docstring, comment or variable name cites a source the tree's
    `README.md` does not list: say what the code does, and say where it came from
    in the report."

  Verified by grep on 2026-09-17: `implementer.md` is the only one of the four
  prompts carrying a retired token, and `.claude/RESUME.md`,
  `.claude/agents/deploy-scout.md`, `.claude/agents/paper-verifier.md` and
  `.claude/skills/paper-write/references/writing-structure.md` — the four `.md`
  files under `.claude/` that this ticket does not edit — carry none, so `C7`
  over all of `.claude/` passes once tickets 16 and 17 have landed.

## Acceptance

Run from the repo root and paste the real output. `$PR` is
`/home/y-guo/reproduce/new1/external/probe-env/bin/python`. Ticket 16 has merged,
so C7 and C8 now run over **all** of `.claude/` and `CLAUDE.md` and must pass
whole.

**C7 — no retired command survives in an agent-facing document.** Scoped to
`CLAUDE.md`, `README.md` and `.claude/`, because `notes/` records history on
purpose.
```bash
"$PR" - <<'PY'
import pathlib, sys
RETIRED = ["gpu-jobs", "run.py record", "launch-probe", "launch-eval",
           "run.py runmeta", "RUNMETA", "run.py list", "run.py show",
           "run.py recipe", "run.py status", "run.py sampler", "sampler",
           "incidents.jsonl", "incident agent", "localhost:8377",
           "ops/", "MAP.md", "pipeline/", "configs/presets", "jobs.json",
           "--run-id", "--track", "CELLS", "EVAL_CELLS", "legacy/"]
def section_range(path, heading):
    """(first, last) line numbers of the section headed `heading`, 1-based."""
    lines = pathlib.Path(path).read_text().splitlines()
    lo = next(i for i, l in enumerate(lines, 1) if l.strip() == heading)
    hi = len(lines)
    for i, l in enumerate(lines[lo:], lo + 1):
        if l.startswith("## "):
            hi = i - 1
            break
    return lo, hi

GONE = ".claude/skills/gpu-run/SKILL.md"
EXEMPT = {(GONE,) + section_range(GONE, "## What is gone")}
print("exempt range:", sorted(EXEMPT))
files = [pathlib.Path("CLAUDE.md"), pathlib.Path("README.md")]
files += sorted(pathlib.Path(".claude").rglob("*.md"))
bad = []
for p in files:
    for i, line in enumerate(p.read_text().splitlines(), 1):
        if any(str(p) == f and lo <= i <= hi for f, lo, hi in EXEMPT): continue
        for t in RETIRED:
            if t in line: bad.append((str(p), t, i))
for b in bad: print("RETIRED", *b)
print("C7", "ok" if not bad else "FAIL")
sys.exit(1 if bad else 0)
PY
```
Expected: exit 0, the `exempt range:` line, and `C7 ok`. The one allowed
exception is the gpu-run skill's "what is gone" list, which ticket 16 wrote with
the heading `## What is gone` for exactly this lookup; quote the range it printed
in your report. **A hit inside `CLAUDE.md` is a real failure**, not an exemption
candidate — and so is a hit inside `.claude/skills/ticket-run/prompts/`, which is
why section 4 rewrites the source prompt **before** copying it. This script is
byte-identical to ticket 16's, paths without a `./` prefix and the tuple unpacked
as `for f, lo, hi in EXEMPT`, so the two remain interchangeable.

**C8 — every command the documents name exists.** **It takes the same
heading-located exemption `C7` takes.** Ticket 16's `## What is gone` section
names `run.py gpu-jobs ...`, `run.py record ...`, `run.py launch`,
`run.py runmeta` and `python3 run.py sampler` on purpose, and none of them is in
`run.py --help`; without the exemption this check fails on a file it is not
allowed to change. This script is ticket 16's with a wider file list — the same
`section_range`, the same `str(p) == f` comparison with no `./` prefix, the same
`for f, lo, hi in EXEMPT` unpacking — so the two stay interchangeable.
```bash
"$PR" - <<'PY'
import pathlib, re, subprocess, sys
help_txt = subprocess.run(["/home/y-guo/reproduce/new1/external/probe-env/bin/python",
                           "run.py", "--help"], capture_output=True, text=True).stdout

def section_range(path, heading):
    """(first, last) line numbers of the section headed `heading`, 1-based."""
    lines = pathlib.Path(path).read_text().splitlines()
    lo = next(i for i, l in enumerate(lines, 1) if l.strip() == heading)
    hi = len(lines)
    for i, l in enumerate(lines[lo:], lo + 1):
        if l.startswith("## "):
            hi = i - 1
            break
    return lo, hi

GONE = ".claude/skills/gpu-run/SKILL.md"
EXEMPT = {(GONE,) + section_range(GONE, "## What is gone")}
print("exempt range:", sorted(EXEMPT))
named = set()
for p in [pathlib.Path("CLAUDE.md"), pathlib.Path("README.md")] + \
         sorted(pathlib.Path(".claude").rglob("*.md")):
    for i, line in enumerate(p.read_text().splitlines(), 1):
        if any(str(p) == f and lo <= i <= hi for f, lo, hi in EXEMPT): continue
        named |= set(re.findall(r"run\.py ([a-z_][a-z0-9_-]*)", line))
sub = set(re.findall(r"^\s{2,}([a-z][a-z0-9_-]*)", help_txt, re.M))
missing = sorted(n for n in named if n not in sub and n not in
                 {"baseline", "train_probe", "inject"})
print("named:", sorted(named)); print("missing:", missing)
print("C8", "ok" if not missing else "FAIL"); sys.exit(1 if missing else 0)
PY
```
Expected: exit 0, the `exempt range:` line, `C8 ok`, and the `named:` line
containing exactly
`free, ls, where, find, kill, refire, retry, table, sync, selfcheck` plus the
three workflow-file names. `sub` is parsed out of ticket 14's pinned `--help`
layout — one subcommand per line, indented two spaces, name first.

**C11 — the diff of the six edited documents is paths and command names only.**
```bash
git diff --stat .claude/skills/exp-status .claude/skills/handoff \
    .claude/skills/paper-write .claude/skills/ticket-run .claude/agents
git diff .claude/skills/exp-status .claude/skills/handoff \
    .claude/skills/paper-write | head -120
```
Expected: a small stat, and a diff in which every removed line is a path, a
command name or the deleted incident paragraph. Paste the stat and say, for each
of the six files, what changed in one sentence.

**C12 — the prompts are one copy, not two.**
```bash
for f in implementer reviewer re-reviewer final-reviewer; do
  diff -q .scratch/from-zero/prompts/$f.md .claude/skills/ticket-run/prompts/$f.md && echo "same $f"
done
```
Expected: four `same <name>` lines.

**C13 — `CLAUDE.md` says the five things it must.**
```bash
grep -c "run.py" CLAUDE.md
grep -c "jobs/runs.jsonl" CLAUDE.md
grep -c "jobs/RESULTS.md" CLAUDE.md
grep -c "models/table.yaml" CLAUDE.md
grep -c "notes/TIMELINE.md" CLAUDE.md
grep -c "Layout during construction" CLAUDE.md
```
Expected: non-zero counts for the first five, `0` for the last.

**C15 — no old ledger path survives in the edited documents.** Every hit must
carry its new prefix.
```bash
"$PR" - <<'PY'
import pathlib, re, sys
OLD = [r"(?<![\w/])TIMELINE\.md", r"(?<![\w/])RESULTS\.md",
       r"(?<![\w/])runs\.jsonl", r"(?<![\w/])jobs\.json",
       r"(?<![\w/])WORKPLAN\.md", r"(?<![\w/])DATA\.md",
       r"(?<![\w/.])plans/"]
bad = []
for p in [pathlib.Path("CLAUDE.md")] + sorted(pathlib.Path(".claude").rglob("*.md")):
    for i, line in enumerate(p.read_text().splitlines(), 1):
        for pat in OLD:
            if re.search(pat, line): bad.append((str(p), i, pat, line.strip()[:80]))
for b in bad: print("OLD PATH", *b)
print("C15", "ok" if not bad else "FAIL"); sys.exit(1 if bad else 0)
PY
```
Expected: exit 0 and `C15 ok`. The lookbehinds make a hit only on a **bare**
spelling: `notes/TIMELINE.md`, `jobs/RESULTS.md`, `jobs/runs.jsonl` and
`notes/plans/` do not match, and `ops/jobs.json` is already `C7`'s. Any line this
prints is a path the numbered list in section 2 missed.

**C5 — `run.py selfcheck` is still green** (nothing in this ticket touches code,
so this is a regression check).
```bash
"$PR" run.py selfcheck; echo "rc=$?"
```
Expected: `selfcheck: 34 python files, 0 problems`, `rc=0`.

### GPU / main session — not yours

None in this ticket.

## Comments
