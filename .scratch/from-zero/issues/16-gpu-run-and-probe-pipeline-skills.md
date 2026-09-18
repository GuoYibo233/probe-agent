# 16 the gpu-run and probe-pipeline skills

Status: resolved
Blocked by: 14
Spec: .scratch/from-zero/spec.md (sections 1, 5, 7, 9)

## What to do

Two skills rewritten and six companion files deleted. No Python. The files you
may touch, and nothing else:

```
.claude/skills/gpu-run/SKILL.md                              rewrite in place
.claude/skills/gpu-run/references/gpu_state.md               delete lines 1-55, keep 56-97
.claude/skills/gpu-run/references/launch-methodology.md      delete the file
.claude/skills/gpu-run/references/monitor-methodology.md     delete the file
.claude/skills/gpu-run/scripts/gpu_status.sh                 delete the file (and the empty scripts/ dir)
.claude/skills/probe-pipeline/SKILL.md                       rewrite in place
.claude/skills/probe-pipeline/references/extending.md        delete (and the empty references/ dir
                                                             once these four files are gone)
.claude/skills/probe-pipeline/references/gates.md            delete
.claude/skills/probe-pipeline/references/invariants.md       delete
.claude/skills/probe-pipeline/references/stage-commands.md   delete
.claude/skills/repo-review/SKILL.md                          NEW: the tree's own line for it
```

Both `description` front-matter lines **keep their Chinese trigger clause** (the
project CLAUDE.md's one exception) and drop the words "three ledgers" and
"sampler". Neither file may name a command that `run.py --help` does not list,
outside the gpu-run skill's one `## What is gone` list (section 1), which the C7
and C8 checks exempt by that heading.

### 1. `.claude/skills/gpu-run/SKILL.md`

The sole entry point for starting a GPU run in new1, rewritten so that its whole
lifecycle is `run.py`'s stage walk instead of the retired `gpu-jobs` / `record` /
sampler machinery. Phase by phase, each phase citing the contract section it is
copied from:

| phase | content | contract |
|---|---|---|
| 0 | read `.claude/skills/gpu-run/references/gpu_state.md` (slow variables only: drivers, CUDA, the alias dedupe, mixed card types) | the tree's line for that file |
| 1 | `run.py free` — free cards per host over `constants/path_outputs.yaml`'s `hosts:` list, probed now, never cached, under the busy test of 2.5 | 8.6, 2.5, 6.3 |
| 2 | commit before launching; the dirty-tree gate is `jobs/launch.git_state(run_dir, allow_dirty)` and refuses without `--allow-dirty`, which writes `dirty.patch` into the run directory; `jobs/runs.jsonl`, `jobs/RESULTS.md` and `*.lock` never count as dirty | 2.5, 1.5 |
| 3 | the smoke is `--debug` on the **same** setting, not a hand-shrunk copy: `debug.yaml` lays sizes over any setting, the model, the tuning and the code path stay the same, and `debug: true` enters the key, so a debug run can never be mistaken for or reused by a real one | 5.6, 3.4 |
| 4 | one command: `run.py <workflow> <setting> [<setting> ...] [--debug] [--allow-dirty] [section.field=value ...]` — the usage line `run.py --help` prints. It walks the stage list of each named setting, and of each child a `sweep:` expands to, one after another, each child with its own key, run directory and registry row. For each it freezes `settings.yaml` / `settings_diff.yaml`, takes `jobs/runs.jsonl.lock` across the git gate, the launch gate, the attach test, the card reservation, the port assignment and the start-row append, starts the service pieces, runs the probe service's `check` client for an `inject` run, then the loop pieces — and **stops that setting's walk**, printing the monitoring command, so one call over several settings or over a sweep parent leaves one launched run per child. A GPU stage is never waited on; a CPU stage runs inline and the walk goes on to the next stage | 8.1, 8.6, 2.3, 7.2 |
| 5 | monitoring is `run.py ls [workflow] [--debug]`: one folded line per run with the six verdicts (`done`, `dead`, `suspected stall`, `warming up`, `slowed`, `healthy`), progress as `done/total <unit>` and the recent rate, the heartbeat age, sessions and cards, the flag column (`edited`, `behind`, `consumed`, `split`, `pinned`, `dirty`, `debug`, `orphan`), and — for a run whose key has moved (`edited`) because a file's effective `VERSION` rose — a trailing `stale=<path> VERSION <n>: "<why>"` naming that file and quoting the bump's own `why`. A `behind` run is the other case: its recorded `VERSION` is below the current one but its key still matches, so it stays usable and carries no `stale=` text. A `--debug` run shows only when `--debug` is given, because `ls` drops debug rows by default, so the Phase 3 smoke is monitored with the flag. A person looks when they want to; nothing patrols | 8.5, 8.6 |
| 6a | wrap-up is re-running the same `run.py` command, and what that re-run does depends on the stage. For `sample` and `inject` the walk finds every requested pair done, writes `done.json` with the certified `pairs`, **tears the run's service pieces down** and appends the `ok` finish row, in that order. For `build` and `train` the stage program wrote `done.json` itself, so the walk only appends the finish row from it when the run still has none, and there are no service pieces to tear down. `eval` and `score` never skip (2.4): the re-run recomputes the whole stage in place and appends that run's own finish row. Then it walks on to the next stage. Numbers reach `jobs/RESULTS.md` through `done.json` -> the finish row -> the render; nothing is typed in. Then `run.py table [workflow] [--debug]`, and one commit carrying `jobs/runs.jsonl` and `jobs/RESULTS.md` with the key in the message | 2.3, 2.4, 1.5, 8.2, 8.6 |
| 6b | interruption: `run.py kill <workflow> <setting> <stage>` (writes the `killed` finish row, refuses while another live run is attached to this run's service); a dead piece is `run.py refire <workflow> <setting> <stage> --piece i` (liveness refusal first, claims released, cards re-probed, a launch entry appended, a **warning** when that piece already has more than one `launches` entry, counted as the entries whose `pieces` list contains this piece index — there is **no quota**); "start fresh" is `run.py retry <workflow> <setting> <stage>` | 8.6, 2.3, 2.4 |
| hard rules | `jobs/runs.jsonl` is append-only and `jobs/RESULTS.md` is rendered — never hand-edited; `run.py` and `jobs/launch.py` refuse to run on any host but `login_host`; an agent never starts a GPU process and returns BLOCKED with the ready-to-run command; one key is one directory and `run.py where` prints it | 8.6, 3.4, the branch CLAUDE.md |

The old file is **rewritten, not patched**, front matter included: the
`description` scalar is lines 3-11 of the current file (`version: 1.0.0` is line
12, the closing `---` line 13), and it is rewritten so that it keeps its Chinese
trigger clause and loses "three ledgers" (line 7) and "sampler" (line 8). Then
the body: lines 14-18 (the title and the one-sentence intro), 19-26 (fixed
paths), 27-40 (Phase 0-1), 41-67 (Phase 2-3),
68-151 (Phase 4 and the three registrations), 152-182 (Phase 5, the sampler and
the incident agent), 183-217 (Phase 6a), 218-225 (Phase 6b) and 226-236 (hard
rules) — that is the rest of the file, which is 236 lines long.

**One "what is gone" list**, as a single section **whose heading line is exactly
`## What is gone`** (the acceptance locates it by that text and takes everything
up to the next `## ` heading, so no line number is hand-typed anywhere), so a
reader who remembers the old command finds out why:
`run.py gpu-jobs free/register/finish/watch/json`,
`run.py record start/finish`, `run.py launch` with
`--run-id/--track/--piece host:gpus`, `launch-probe` / `launch-eval`,
`run.py runmeta` and `RUNMETA.json` (its content is `meta.json`'s `launches`),
`ops/jobs.json`, `ops/runs.jsonl`, `ops/gpu_state.md`, the resident sampler and
`python3 run.py sampler`, the web page `http://localhost:8377`, the sampling
history, `incidents.jsonl` and the incident agent, the escalation line's
automatic consequence, and the one-refire-per-piece quota. **That list is the
only place in the file where a retired name may appear**, and the acceptance
checker skips exactly that section by an explicit `(path, line-range)` exemption
— never by loosening its token list.

`references/gpu_state.md`: delete lines 1-55 (the sampler / ledger / cron /
port-8377 block **and its tail**: lines 45-48 are the "Port 8377 is already held
by this resident process" bullet and 49-54 the "restart the resident session"
note); **keep lines 56-97 verbatim** — the kept block starts at
`Surveyed on: 2026-07-29 (measured, not hearsay).`, then `## Hardware and drivers`
at line 58, the six known traps and the machines outside the pool. They are the
measured slow variables the tree asks this file to hold. Cutting at 46 instead
(that is, keeping 46-97) keeps line 46's `python3 run.py sampler --port 8377`, so
`W1`'s sampler-token count would not be zero; cutting at 47 gets the token count
to zero but still leaves eight orphaned lines (47-54) about the machinery this
wave retires.

`references/launch-methodology.md` is deleted: card picking, sharding and what
`launch` does are contract text (3.4's placement rules, 2.3's piece rule) and are
not restated in a skill. `references/monitor-methodology.md` is deleted: its
content is the sampler's verdict rules, which are now `jobs/registry.py`'s pure
functions (8.5) with `DEFAULTS` as the one home for the numbers.
`scripts/gpu_status.sh` is deleted: `run.py free` replaces it, and a second card
probe is a second copy of 2.5's busy test.

### 2. `.claude/skills/probe-pipeline/SKILL.md`

The entry point for running or extending the whole probe chain, rewritten around
the fact that the chain is now one `run.py` call over a workflow file's stage
list. Six numbered points, and nothing else:

1. **The chain is a workflow file.** `experimental_settings/train_probe.yaml` has
   `workflow: [sample, build, train, eval]`; `run.py train_probe <setting>` walks
   it. There is no per-stage command table any more: every stage program is
   called `<venv python> -m <module> --run-dir <dir> [--piece i/n]` by `run.py`
   or `jobs/launch.py`, never by a person (2.6). A batch of related experiments
   is the `sweep:` keyword inside one named setting, not a script (5.5).
2. **Who writes what.** The YAML files are gyb's; an agent reads them and never
   edits them (a hook refuses). An agent proposes a named setting as a task.
   `schema.py` is code and is edited for a new field or a new axis value, with a
   default that reproduces the old behaviour.
3. **The gates are in the programs.** The old `references/gates.md` numbering
   (G1-G24) is retired: every gate is held by the stage that can fail it and is
   listed in contracts 2.5 as `.scratch/from-zero/contract-errata.md` amends it —
   `build`'s record completeness, its abort share, its split gates (a task id in
   two splits, a record's task id in none of the environment's official lists)
   and its row gates (an empty `text`, a `depth` outside [0, 1], a text whose
   thinking part is not a prefix of the record's thinking); `train`'s alignment
   gate; the generator eval's shared-build-key gate; `inject`'s **three**
   `run.py`-held gates — contracts 2.5's shared-build-key gate and code-currency
   gate, plus the errata's `5.4 / 2.1` ruling, which compares a `key:`/`dir:`
   reference's stated `method:` against the referenced train run's frozen
   `probe.method`; `score`'s same-setup and baseline-pair gates; the launch gate
   and the card reservation. Two things that read like build gates are not gates,
   and the skill says so: an event whose call `build_call` refuses, that fails
   the round-trip gate, or whose non-null action `split_args` cannot parse is
   skipped and counted under `counts.events_skipped_no_call`; `report.md`
   carries that count for all three, and one line per event naming the record,
   the step and the reason for the `build_call`-refusal and round-trip cases
   only (the errata's two rulings on 2.5, of 2026-09-17 and 2026-09-18 —
   the build reports a rare data problem and goes on); and `build.max_examples`
   is a cap per split, applied after the split column is assigned, not a gate.
4. **The acceptance of any chain change is the `--debug` walk of its workflow
   file**, plus `run.py selfcheck` before delivery.
5. **Extending.** The four places a file is added are
   `data/environments/<env>.py`, `models/agent_models/<family>.py`,
   `models/probe_models/<backbone>.py`, and `train/methods/<m>.py`, whose eval
   side is a `PROBE_KIND` and a `MATCH_VERSION` entry plus a `match_<m>`
   function in `eval/utils/probe_eval.py` (the errata's
   `0.2 / 2.1 / 2.6 (eval/methods/)` ruling of 2026-09-18, which folded the three
   `eval/methods/` files into that one file). What each extension touches is
   **`README.md` section 3, "The extension recipes"**, and that one section is
   the only place this skill points at **for what an extension touches**. **It
   keeps no copy** — the old `references/extending.md` existed because there was
   no single table; there is one now. Do not cite contracts 0.3 or 0.4 here:
   both predate the fold and the renames of 2026-09-18 — 0.3 still names
   `eval/methods/<m>.py` and counts 34 files, 0.4 still names
   `eval/methods/<m>.py` and `agent/inject_format.py` — and `notes/` is not
   rewritten.
6. **Write-back.** Phase E's "write the new method back into the skill" is
   replaced by: the new file's five annotation lines go into `README.md` in the
   same commit, `run.py selfcheck` proves them against the real import graph, and
   a new axis value is registered in `schema.py` before any YAML may use it.

The whole file is rewritten, front matter included. The `description` scalar is
lines 3-15 of the current file (`version: 1.0.0` is line 16, the closing `---`
line 17), and it is rewritten to the new chain — `run.py <workflow> <setting>`
over a workflow file's stage list, extension through `README.md` — keeping its
Chinese trigger clause and dropping Phase E's write-back, the matrix and cell
language, and the `collect/annotate/train/eval` stage names (the stages are
`sample, build, train, eval`). The body below it, lines 18-319, is rewritten too.

### 3. `.claude/skills/repo-review/SKILL.md` — new

The fixed tree names this file and nothing else in the build writes it, so it is
this ticket's. The tree's own one line is the whole brief: **"the two-day review:
an agent reads the tree against the six principles and writes tasks"**. Keep it
short — it is a procedure, not a second copy of the contracts.

That quoted line's count is stale, and the quote stays as it is because the fixed
tree is never reworded: `notes/plans/2026-09-14-structure-from-zero.md`'s opening
list of principles (lines 11-32, above that document's
`## Part 1. The file structure` heading) numbers seven and
`README.md` line 5 opens "Seven principles hold the tree together", and item 1
below is that list. The `SKILL.md` you write says it reviews against the seven
principles `README.md` section 1 states, and never writes "six".

1. **What it reviews**: the 31-file tree against the owner's principles as
   `README.md` states them (one experiment is one setting; outputs keyed by
   setting and version; the layer boundaries `data/ models/ agent/ train/ eval/
   jobs/`; `--debug` runs any setting tiny; no near-duplicate and no framework;
   `README.md` for the next reader; everything on disk and `eval/` CPU-only).
2. **What it reads, in order**: `README.md`, then the file under review, then the
   `notes/plans/2026-09-17-contracts.md` section its annotation line cites. It
   runs `run.py selfcheck` first and stops if that is not green — a review over a
   tree that fails its own checks reports noise.
3. **What it writes**: one ticket per finding into **`.scratch/review/issues/`**,
   in the issue-tracker format of **`notes/docs/agents/issue-tracker.md`**, with
   the Status line taking one of the five labels of
   **`notes/docs/agents/triage-labels.md`**. It edits no code and no file under
   `notes/`. **Those two paths are `notes/docs/...`, not `docs/...`**: the fixed
   tree's `notes/` line says notes holds "plans/ and docs/ (moved whole)", and
   ticket 18 performs the `git mv docs notes/docs` in wave 7. Ticket 17's
   `CLAUDE.md` cites the same two paths, so the two documents agree.
4. **What it never does**: start a GPU process (it returns BLOCKED with the
   ready-to-run command), edit `experimental_settings/*.yaml` or
   `models/table.yaml`, or propose a file the tree's Part 1 does not name.
5. A `description` front-matter line in the same shape as the other skills,
   **ending with its Chinese trigger clause** (the project CLAUDE.md's one
   exception), and naming no command that `run.py --help` does not list.

**Not carried over:** the `run.py` task registry (`list` / `show` / `recipe` /
`status` and `selfcheck`'s old meaning), `CELLS` / `EVAL_CELLS`, `MAP.md`, the
`<BATCH>`/`<DATA_ROOT>` variable table, `pipeline/configs/*.json` annotate
configs, collect manifests, placement tables, the presets (`configs/presets/`,
`sweep_preset`, `serve_preset`), and the `DATA.md §7` pre-flight checklist
reference (its checks are now loader refusals in 5.7 and stage gates in 2.5). All
four `references/` files are deleted — their content is `README.md` section 3
(`extending.md`; contracts 0.4 says the same but predates the `eval/methods/`
fold), 2.5, 3.3 + 2.2 and 2.6 respectively, and a second copy in a skill is a
copy that rots.

## Acceptance

Run from the repo root and paste the real output. `$PR` is
`/home/y-guo/reproduce/new1/external/probe-env/bin/python`.

**Scope note.** `.claude/` also holds `exp-status`, the three agents, `handoff`,
`paper-write` and `ticket-run`, which ticket 17 rewrites in the next wave. C7 and
C8 below are therefore **scoped to this ticket's three skill directories**; the
main session runs them over all of `.claude/` after wave 7 merges.

**W1 — the deletions landed.**
```bash
test ! -e .claude/skills/gpu-run/references/launch-methodology.md && echo ok-launchmeth
test ! -e .claude/skills/gpu-run/references/monitor-methodology.md && echo ok-monitormeth
test ! -e .claude/skills/gpu-run/scripts && echo ok-scripts
test ! -e .claude/skills/probe-pipeline/references && echo ok-ppreferences
wc -l .claude/skills/gpu-run/references/gpu_state.md
head -1 .claude/skills/gpu-run/references/gpu_state.md
grep -c 'tokyo105 | shiga' .claude/skills/gpu-run/references/gpu_state.md
grep -c 'sampler\|8377\|crontab' .claude/skills/gpu-run/references/gpu_state.md || true
```
Expected: the four `ok-` lines; **`42`** lines (the file was 97 and lines 1-55 are
gone); a first line reading
`Surveyed on: 2026-07-29 (measured, not hearsay).`; `1` for the hardware-table
row; `0` for the sampler tokens. The last line carries `|| true` on purpose:
`grep -c` exits 1 when the count is zero, so a bare `grep -c ...` expecting `0`
would make a correct implementation look like a failed command.

**W2 — the repo-review skill exists and names its output directory.**
```bash
test -f .claude/skills/repo-review/SKILL.md && echo ok-exists
grep -c '\.scratch/review/issues/' .claude/skills/repo-review/SKILL.md
grep -c 'run.py selfcheck' .claude/skills/repo-review/SKILL.md
awk 'NR>1 && /^---$/{exit} {print}' .claude/skills/repo-review/SKILL.md
```
Expected: `ok-exists`; a count of at least `1` for each grep; and a
`description` front-matter line ending in its Chinese trigger clause. The `awk`
prints the whole front matter and stops at the closing `---`: a `head -8` cannot
show the trigger clause, because every skill in this repo has a `description: >-`
block whose closing `---` is at line 12 or later.

**C7 — no retired command survives in any of the three skills**, outside the
gpu-run skill's one "what is gone" list. The exempt range is found by its heading
text, so no line number is typed by hand.
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
files = []
for d in (".claude/skills/gpu-run", ".claude/skills/probe-pipeline",
          ".claude/skills/repo-review"):
    files += sorted(pathlib.Path(d).rglob("*.md"))
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
Expected: exit 0, the `exempt range:` line, and `C7 ok`. Quote the range in your
report. **Two details the script depends on**: the paths carry **no `./`
prefix**, because `rglob` stringifies them without one and the comparison is
`str(p) == f`; and the tuple is unpacked as `for f, lo, hi in EXEMPT`, the same
way ticket 17's copy of this script unpacks it, so the two stay interchangeable.

**C8 — every command the two skills name exists.** **It takes the same
heading-located exemption `C7` takes**, and for the same reason: section 1
requires the gpu-run skill to carry a `## What is gone` list naming
`run.py gpu-jobs ...`, `run.py record ...`, `run.py launch`, `run.py runmeta` and
`python3 run.py sampler`, none of which is in `run.py --help`. Without the
exemption this check fails on text the same ticket ordered written. The scan is
therefore line by line, skipping that range, exactly as `C7` does.
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
for d in (".claude/skills/gpu-run", ".claude/skills/probe-pipeline",
          ".claude/skills/repo-review"):
    for p in sorted(pathlib.Path(d).rglob("*.md")):
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
Expected: exit 0, the `exempt range:` line, `C8 ok`, and the `named:` line drawn
from `free, ls, where, find, kill, refire, retry, table, sync, selfcheck` plus
the three workflow-file names. `selfcheck` is in `run.py --help` from ticket 14
onward, so this passes in this wave. `sub` is parsed out of ticket 14's pinned
`--help` layout — one subcommand per line, indented two spaces, name first — so
if the `named:` line looks right and `missing:` is not empty, read
`run.py --help` before touching a skill: the defect is ticket 14's layout, not
this ticket's text. Ticket 17's `C8` is this same script with a wider file list;
keep the two interchangeable.

**W3 — the four extension places are each named once in the probe-pipeline
skill.** (Numbered `W3`, not `C9`: ticket 18 owns `C9` and the plan's section 2.9
indexes the wrapup checks by one identifier each.)
```bash
for s in "data/environments/" "models/agent_models/" "models/probe_models/" "train/methods/"; do
  printf '%s %s\n' "$s" "$(grep -c "$s" .claude/skills/probe-pipeline/SKILL.md)"
done
```
Expected: each line ending in a count of at least 1.

**W4 — the trigger clauses survived.** (Numbered `W4`, not `C10`: ticket 18 owns
`C10`.)
```bash
awk 'NR>1 && /^---$/{exit} {print}' .claude/skills/gpu-run/SKILL.md
awk 'NR>1 && /^---$/{exit} {print}' .claude/skills/probe-pipeline/SKILL.md
awk 'NR>1 && /^---$/{exit} {print}' .claude/skills/repo-review/SKILL.md
```
Expected: each `description` front-matter line still ends with its Chinese
trigger-phrase clause, and none contains the words "sampler" or "three ledgers".
Each `awk` prints that file's whole front matter and stops at the closing `---`;
`head -8` is not used, because it truncates every one of these descriptions
before the trigger clause and both halves of the Expected sentence would then be
unverifiable from the pasted output.

**W5 — no bare ledger name in the three skills.** Ticket 17's `C15` scans
`CLAUDE.md` and every `*.md` under `.claude/` in the next wave, these three
skill directories included, with no exempt section, and ticket 17 may not edit
the files this ticket writes. So every ledger and notes file is written with its
directory here: `jobs/runs.jsonl`, `jobs/runs.jsonl.lock`, `jobs/RESULTS.md`,
`notes/TIMELINE.md`, `notes/WORKPLAN.md`, `notes/DATA.md`, `notes/plans/`. The
`## What is gone` list passes as the ticket words it: `ops/jobs.json` and
`ops/runs.jsonl` carry a `/` before the name and `RUNMETA.json` is not
`jobs.json`. The pattern list is ticket 17's, copied whole; keep the two
interchangeable.
```bash
"$PR" - <<'PY'
import pathlib, re, sys
OLD = [r"(?<![\w/])TIMELINE\.md", r"(?<![\w/])RESULTS\.md",
       r"(?<![\w/])runs\.jsonl", r"(?<![\w/])jobs\.json",
       r"(?<![\w/])WORKPLAN\.md", r"(?<![\w/])DATA\.md",
       r"(?<![\w/.])plans/"]
bad = []
for d in (".claude/skills/gpu-run", ".claude/skills/probe-pipeline",
          ".claude/skills/repo-review"):
    for p in sorted(pathlib.Path(d).rglob("*.md")):
        for i, line in enumerate(p.read_text().splitlines(), 1):
            for pat in OLD:
                if re.search(pat, line): bad.append((str(p), pat, i))
for b in bad: print("BARE", *b)
print("W5", "ok" if not bad else "FAIL"); sys.exit(1 if bad else 0)
PY
```
Expected: exit 0 and `W5 ok`.

### GPU / main session — not yours

None in this ticket. The main session runs C7 and C8 over all of `.claude/` after
ticket 17 merges, and runs the three end-to-end `--debug` walks under the skill
this ticket rewrote.

## Comments

- 2026-09-19, wave 6 (fork5): resolved. Branch ticket/2026-09-19-wave6/T16, commit 602d5d1 on base f1f849e, merged as 724db73. No fix round, no open finding, no minor. Main-session checks on the merged tree: W1, W2, W3, W5, C7 (exempt range lines 175-197) and C8 (`missing: []`) pass. Could not be verified by the review, checked here: (1) C7/C8 over all of `.claude/` and the three `--debug` walks are the main session's after wave 7 and are not this ticket's; (2) the repo-review skill's Chinese trigger clause is the implementer's own wording (the ticket names no phrases) -- for the owner's eye; (3) repo-review point 1 says the tree is reviewed against `README.md`'s seven principles and does not repeat the file count; no acceptance check reads that phrase, left as it is. Implementer concerns: the skill cites `notes/docs/agents/...`, which exist only after ticket 18's move, as the ticket orders.
