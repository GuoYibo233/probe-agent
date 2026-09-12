# T15 report: Documentation write-back for the gpu-run skill and two methodology docs

Ticket: `.scratch/gpu-monitor-launch/issues/15-docs-gpu-run.md`
Branch: `ticket/20260808-par/T15` (worktree `/home/y-guo/reproduce/new1-wt/20260808-par-T15`, removed)
base: `86f2b8e2fa5846f4060262989974237ad824d108`
head: `146a289e3b14de7318dcf719cb4290fe140ab92c`

## What was done (against the ticket point by point)

The ticket's acceptance items, three of them:

- [x] **Phase 4 down to just three steps: commit, launch, hand off the monitoring entry point**
  `.claude/skills/gpu-run/SKILL.md`'s Phase 4 was rewritten into three numbered steps:
  1. commit the code;
  2. `python3 run.py launch <task> ... --run-id --track --piece ...` (one command, full
     usage pasted in, explaining that it does probe → tmux launch → 30-second alive check → ledger/record/RUNMETA
     three registrations, all fixed down by `ops/launch_cmd.py`'s header comment's ten steps; the whole paragraph about
     typing three registration commands by hand was deleted);
  3. hand off the monitoring entry point (`gpu-jobs`/`gpu-jobs watch`/the browser
     `localhost:8377`).
  Phase 3 (smoke) got a sentence added: can also use `launch --dry-run` first to see the command, without launching or registering.

- [x] **Phase 5 no longer contains a scheduled-checking cadence clause**
  The original clause "10-minute granularity while a service is starting up, 15-30 minutes while running a batch"
  and the manual step "ETA is cross-checked from two time points' Δitems/Δt" were deleted wholesale, rewritten as
  "sampler takes over": the verdict/escalation is now the permanent responsibility of
  `ops/sampler.py`, and Claude only dispatches `job-monitor` on two occasions: ① the user asks, ② the incident
  record has new content. Per the ruling from the ticket's Comments transcribed by the main session,
  **the incident agent's automatic autopsy-and-refire is written as "not yet live (on hold)"**, with a clear explanation
  of why: the trigger-rule pure function `should_trigger` has already been merged, but the function that actually
  pulls up the agent, `maybe_trigger_incidents`, was confirmed by reading the code to currently be just a `pass`
  placeholder (2026-08-08 user ruling: held). It wasn't written as current state.

- [x] **Commit**: `146a289`, see the commit list below.

Two extra methodology rewrites required by the ticket text:

- **`references/launch-methodology.md`**:
  - Step 4's title changed from "Launch in tmux" to "What `launch` does for you," the body rewritten to
    explain clearly what `run.py launch` does for you (fail-closed probing, session/log naming
    rules, the 30-second alive check window, the three registrations); the original
    `subprocess`/`tmux new-session` template kept, but annotated as "a reference template only still
    useful for the `--cmd` escape hatch."
  - Step 3's title changed from "Shard if it pays" to "Shard via `--piece`, not by hand,"
    explaining clearly that multiple `--piece` will get `--shard-id i --num-shards N` auto-injected by
    `launch`, and that a task must be marked `shardable: True` in the registry before it may be given
    multiple pieces; the way to recover a dead piece was changed to
    `launch --refire`.
  - Step 2 (card-picking rules) kept unchanged as-is.

- **`references/monitor-methodology.md`**:
  - The original four sections "Mandatory rules / Standard procedure / Reading tqdm output /
    Sharded-job caveat" (the manual process of two-point rate measurement, tqdm parsing, sharded ETA correction) were
    merged and rewritten into one section, "Program responsibility statement: where the verdict comes from": explaining clearly that
    this work is now the permanent responsibility of `ops/heartbeat.py`+`ops/sampler.py`+`ops/verdicts.py`, with
    `ops/verdicts.py`'s six-cell verdict table attached (`V_DONE`/`V_DEAD`/`V_STALL`/`V_WARMUP`/
    `V_SLOW`/`V_OK`'s respective hit conditions, taken from `judge()`) and the two formulas for the
    stall line/escalate line (the constants come from `ops/verdicts.py` `DEFAULTS`, defaults listed item by item).
  - The "Decision tree" section was kept, with its header changed from "Condition" to "verdict," and its input
    changed from "ETA computed by hand" to the `verdict`/`escalated` value given by the sampler, with six
    branches corresponding to the six verdicts.

## One problem discovered and fixed on my own (not named by the ticket, but directly affects the documentation's accuracy)

While drafting Phase 4/5 and monitor-methodology, I initially followed the ticket's literal wording and described
`ops/verdicts.py`'s six-cell verdict as "already visible in the `gpu-jobs`/`gpu-jobs watch`/`gpu-jobs json`
tables." Reading the code to check found this to be wrong:

- `ops/gpu_jobs.py`'s `collect()` is still, to this day, the old `parse_log()` (a regex grabbing the tail
  of the log's tqdm lines); `fmt_table`'s columns are `job/host/gpus/state/progress/rate/eta/session`,
  with no `verdict`/`escalated` columns; the `json` subcommand is also just
  `print(json.dumps(collect()))`, the same old logic.
- The sampler (`ops/sampler.py`) writes its verdict into its own
  `MONITOR_DIR/latest.json`, which is a completely separate file from what `ops/gpu_jobs.py` reads and writes,
  `ops/jobs.json` (the ledger/registry); the sampler doesn't write to the ledger.
- The six-cell verdict is currently visible **only** through the sampler's own web outlet:
  `http://localhost:8377` (HTML) and `http://localhost:8377/json` (the raw
  `latest.json`), a product ticket 06 has already completed.
- Wiring the three terminal outlets `gpu-jobs`/`watch`/`json` to read this sampling history is
  what ticket 07, "terminal outlet reads sampling history," is supposed to do; confirmed its current status is
  `in_progress`, not yet wired (`.scratch/gpu-monitor-launch/issues/07-terminal-outlet.md`).

Per the CLAUDE.md hard rule "no guessing at data results/no writing something unverified into the documentation as current
state," changed all three places in the documentation to accurately distinguish "already viewable on the web/still being
wired up in the terminal":

- SKILL.md Phase 4, hand off the monitoring entry point: the terminal table description changed back to the original accurate
  "progress/measured rate/ETA/tmux alive status," with a sentence added noting that the web
  `localhost:8377` (and `/json`) already shows the six-cell verdict, and the three terminal
  outlets "wiring up to read this sampling history is still in progress."
- SKILL.md Phase 5: job-monitor reading the verdict is written as "`gpu-jobs json` (once the terminal outlet is
  wired up, this is exactly this data; before it's wired up, read the web `localhost:8377/json` first)," and
  "written into `ops/jobs.json`" was changed to the accurate "written into its own state file."
- monitor-methodology.md's "Program responsibility statement" and "Decision tree" sections were both changed to the
  same accurate wording.

This is not something the ticket required by name, it's an accuracy issue found while checking the code, and was fixed along
the way in the same change, without opening a separate scope for it.

## How it was verified

This is a pure documentation change, not touching the `run.py` registry; `selfcheck` wasn't run (none of the three changed
files are within test coverage. `grep -rl "gpu-run\|SKILL.md\|monitor-methodology\|
launch-methodology" tests/` has no match). The verification method was reading the implementation code line by line
to check the documentation's statements against it:

- `ops/launch_cmd.py` (the ten-step flow, `parse_launch_argv`, `build_pieces`,
  `build_inner`, `verify_alive`, `cmd_refire`'s refire semantics)
- `ops/launch_common.py` (`register_all`'s three-registration order and failure semantics)
- `ops/verdicts.py` (the six-cell verdict constants, `judge()`/`_judge_service()`'s hit conditions,
  `DEFAULTS`'s constant values, `stall_line_s`/`typical_gap_s`'s formulas)
- `ops/sampler.py` (where `MONITOR_DIR` is located, `maybe_trigger_incidents`'s current state being
  `pass`, `should_trigger`/`build_incident_prompt` already merged, `WebServer`'s
  `/`, `/json` paths, `read_incidents_tail`'s landing path)
- `ops/gpu_jobs.py` (`collect()`/`fmt_table()`/`cmd_status`/`cmd_watch`/
  `main()`'s `json` branch, confirming the terminal outlet has not yet been wired to sampling history)
- `.scratch/gpu-monitor-launch/issues/07-terminal-outlet.md` (checking that ticket's actual status and
  acceptance scope)
- `docs/plans/2026-08-08-gpu-monitor-launch.md` Task 16 (the original text of the execution steps specified by the ticket)

At the command level, only ran `git diff --stat` / `git diff` to read through the whole change once for self-consistency; there was no
automated test that could verify the documentation's correctness.

## Commit list

- `146a289`: `T15: gpu-run skill aligned with launch+sampler's new flow (Phase4/Phase5 folded in, two methodology docs rewritten)`
  Files changed: `.claude/skills/gpu-run/SKILL.md`,
  `.claude/skills/gpu-run/references/launch-methodology.md`,
  `.claude/skills/gpu-run/references/monitor-methodology.md`

## Self-check findings and open questions

1. **The frontmatter description and two fixed-path lines got an update along the way, not named by the ticket**:
   `SKILL.md`'s top `description:` field (originally wrote "tmux launch→register the ledger→…→scheduled
   checking") and the two reference lines in the "fixed paths" list ("tmux template," and the un-labeled
   "measurement and ETA methodology") were out of sync with the rewritten Phase 4/5 and the two methodology docs' content,
   so I updated these two spots along the way to make the whole document self-consistent. The ticket's acceptance items don't name
   these two spots; if the reviewer thinks this is out of scope, these two small sections can be reverted (in the diff, the
   description line + the two fixed-path lines).

2. **`launch-methodology.md`'s Step 5 (Verify)/Step 6 (Monitor without
   polling) were not changed**: Step 6 still has the sentence "ETA claims need ≥60s of tqdm
   observation (see `monitor-methodology.md`)," which is the wording of the old manual process, and doesn't
   quite match `monitor-methodology.md`'s rewritten content anymore. The ticket's original text only names "the tmux template
   section" and "the sharding section" as needing changes; Step 5/6 aren't on that list, so I followed the ticket's
   literal scope and didn't touch them; if this leftover residue needs sweeping out too, that needs additional authorization
   (which the ticket didn't give, and I did not expand the scope myself).

3. **`monitor-methodology.md`'s Gotchas section (tail -c/\r parsing, tqdm filtering,
   process count) was not changed**: this content is essentially still "operational details for reading logs by hand," and the
   ticket names "the two-point measurement/ETA-correction/tqdm-parsing three sections". I understood this as
   "Mandatory rules + Standard procedure + Reading tqdm output + Sharded-job caveat," those four sections,
   with Gotchas not among them, and in the newly written "Program responsibility statement," I added a sentence
   "the manual process is only a fallback for when sampling can't find the answer," positioning Gotchas as
   operational detail for that fallback, so it was left unchanged. This is my own ruling on the scope of "three sections,"
   not something the ticket named verbatim. If my understanding is off, it needs to be revisited.

4. **The three `--kind` values (train/eval_tool/eval_call) don't match what
   `launch_common.py` actually writes, `kind="launch"`**: reading `ops/launch_common.py`
   I found that `register_all` fixedly passes `kind="launch"` for RUNMETA, but
   SKILL.md's original text (which I kept as-is during this rewrite) says "when hand-registering, `--kind`
   should use one of `train`/`eval_tool`/`eval_call`". This is a tip for "hand-launched via tmux, not
   through `launch`," a different path from what `launch` itself writes, `kind="launch"`, and I judged
   this isn't a contradiction so I didn't touch it; but this is indeed a code/documentation inconsistency nobody has
   named before, noted here for a follow-up ticket (especially ticket 18, wrap-up self-check) to cross-check.

---

## Fix round 1 (2026-08-08)

Branch `ticket/20260808-par/T15` reused (not newly created); base unchanged
(`86f2b8e2fa5846f4060262989974237ad824d108`), this round's commit lands after the original head
`146a289e`. Worktree `/home/y-guo/reproduce/new1-wt/20260808-par-T15-fix1`
(removed per protocol).

Two findings delivered by the main session:

### F1 (critical): Incident-agent wording using the old convention

**Problem**: `SKILL.md` Phase 5 and `monitor-methodology.md`'s Decision tree say "the incident
agent's automatic autopsy-and-refire: not yet live (on hold)," which is the wording of ticket 15's Comments' first
entry (the old convention, transcribed from the main session). Ticket 15's Comments' second entry (same day, explicitly
marked "supersedes the previous one") says the user subsequently authorized it, and the
`spawn_agent`+`maybe_trigger_incidents` wiring has already been implemented by the main session, requiring it to be
rewritten as "wired up, not yet actually rehearsed."

**Verified**: at the time the previous round's report was written, this comment 2 had not yet been posted on the ticket
file (the report's full text never mentioned it), so writing per comment 1's wording last round was a reasonable
product of the information available at the time, not a mistake. This round first read ticket 15's current Comments to confirm
comment 2's original text and the "supersedes the previous one" annotation; then read ticket 12's Comments' latest entry
(same day, in `.scratch/gpu-monitor-launch/issues/12-incidents.md`, an uncommitted change in the
main repo per `git diff`) to get the precise wording of the implementation details' source: `spawn_agent`
(a headless `claude` subprocess, model pinned to opus, detached without wait, output going into
`monitor/incidents/<incident-id>.out`) + `maybe_trigger_incidents`
(a hit writes `incidents.jsonl` → pulls up the agent → sets `incident_open` to prevent re-triggering) +
`sample_once`'s `state.json` write moved to after triggering (fixing the timing pitfall), 4 new unit
tests, "the manual rehearsal was cancelled per another user ruling: the whole chain is backed only by unit tests,
no opus has ever really been pulled." Also read the worktree's `ops/sampler.py` (still the
`maybe_trigger_incidents` `pass` placeholder within this branch. The wiring code is an uncommitted change
in the main repo, it hadn't landed along with either the T15 or T12 branch), confirming this "wired up" is a
documentation-level authorization instruction, not the current runnable code state on this branch; per the ticket's original
instruction "if you've already written it per the old convention, the main session will check and correct it at settlement," this
round still rewrote the documentation per comment 2's given wording.

**Fix**:
- `SKILL.md` Phase 5 (originally lines 126-131): the topic sentence changed to "The incident agent's automatic
  autopsy-and-refire: wired up, not yet actually rehearsed.", the body rewritten to explain clearly the wiring details
  (who authorized what on 2026-08-08 and who implemented it, `should_trigger` hitting first writes
  `incidents.jsonl` then spawns a headless `claude` subprocess, the mechanism of `incident_open`
  preventing re-triggering), keeping a caveat sentence: "the manual rehearsal was cancelled per user ruling.
  The whole chain is backed only by unit tests, no agent has ever really been pulled, the first real incident is
  this chain's first live run," and keeping the original wrap-up sentence "read the log to locate the cause of death, refire
  with `--refire` if it can be fixed."
- `monitor-methodology.md`'s Decision tree table's `V_STALL`/`escalated=true` row:
  "automatically pulling up an incident agent to refire is currently **not live (on hold)**" changed to
  "and automatically pulls up a headless incident agent to handle it (**wired up, not yet actually
  rehearsed**)," everything else unchanged.

### F2 (important): launch-methodology.md dangling reference

**Problem**: `launch-methodology.md` Step 6's sentence "ETA claims need ≥60s of tqdm
observation (see `monitor-methodology.md` in this same directory)." is the wording of the old manual
measurement process; this rewrite has already deleted `monitor-methodology.md`'s whole "two-point
measurement/manually parse tqdm lines" process, replaced by "read the sampler's verdict"; this reference now
points at content that no longer exists, and a reader following it would find no corresponding operation.

**Verified**: the previous round's report's self-check item 2 already pointed out this inconsistency, and it was not addressed at the
time on the grounds that "the ticket's original text only names the tmux-template section and the sharding section, Step 5/6 aren't on that
list, no extra authorization to expand scope on my own." This round's finding explicitly requires handling it as "clearly at
odds with this round's rewritten content," which is a new dangling reference directly produced by this round's rewrite, not an
independent out-of-scope refactor, so it was fixed.

**Fix**: changed this sentence to point at `monitor-methodology.md`'s existing verdict-outlet wording,
"ETA claims come from the sampler's verdict, not hand-parsed tqdm: read
`python3 run.py gpu-jobs json` once the terminal outlet reads sampler
history, or `http://localhost:8377/json` in the meantime (see
`monitor-methodology.md` in this same directory).", aligned with `monitor-methodology.md`'s
"Program responsibility statement" section's wording, "read the verdict preferring `gpu-jobs json`……before
it's wired up, first read the web `/json`……don't go back to reading logs by hand and hand-computing tqdm lines."

### How it was verified

A pure documentation change (the changed files are still the same three existing files,
`SKILL.md`/`launch-methodology.md`/`monitor-methodology.md`'s existing wording, no new file added, the
`run.py` registry not touched), re-confirmed the previous round's test-coverage conclusion still holds:

```
$ grep -rl "gpu-run\|SKILL.md\|monitor-methodology\|launch-methodology" tests/
(no output, exit code 1)
```

None of the three files are within test coverage, `selfcheck` wasn't run (the registry wasn't touched). Verified by reading
the source and checking the wording: `ops/sampler.py` (`should_trigger`/`build_incident_prompt`/
`maybe_trigger_incidents`/`spawn_agent`'s actual code state on this branch, confirming it's
still the `pass` placeholder, the wiring is in an uncommitted change in the main repo), ticket 15's Comments in full, ticket 12's
Comments' latest entry in full (the source of the original wording). Also ran `git diff` to read through the change for
self-consistency, and confirmed it only touched the three spots named by the finding.

### Commit list

- `b0cd20d`: `T15: fix round 1, incident-agent wording changed to wired up not yet rehearsed, added launch-methodology's missing dangling reference`
  Files changed: `.claude/skills/gpu-run/SKILL.md`,
  `.claude/skills/gpu-run/references/launch-methodology.md`,
  `.claude/skills/gpu-run/references/monitor-methodology.md`

head: `b0cd20d`

### Self-check findings and open questions

- No new leftover issues. The original report's self-check item 1 (the opportunistic update to description/fixed-path
  lines), item 3 (the Gotchas section unchanged), and item 4 (the potential inconsistency between the three
  `--kind` values and `kind="launch"`) weren't touched this round, kept as-is, left for a follow-up
  ticket to cross-check.
- The wording "wired up, not yet actually rehearsed" itself depends on the code state described in ticket 12's Comments'
  latest entry; that code is currently an uncommitted change in the main repo (`ops/sampler.py`/
  `tests/test_incidents.py` etc. modified, not committed), and once it lands in some other way or the wording
  changes again down the line, these two documentation spots need to be re-checked accordingly. This isn't something this round can pin
  down as final.
