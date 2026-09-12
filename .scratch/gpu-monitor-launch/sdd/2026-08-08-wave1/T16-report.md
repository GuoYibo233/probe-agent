# T16 report: Documentation write-back for two agent definitions

Ticket: `.scratch/gpu-monitor-launch/issues/16-docs-agents.md`
Branch: `ticket/20260808-par/T16` (worktree `/home/y-guo/reproduce/new1-wt/20260808-par-T16`, removed per protocol at wrap-up)
base: `0d2c1ac9c5ee4ff5c4fda4d04e93fa1c8d6e53a9`
head: `9ba56ae8e64724e441f2e8dcce3da6c3c80e15cc`

Requirement detail source: the ticket doesn't directly cite a section of spec.md, its text names "steps follow implementation plan
Task 17's execution," reading `docs/plans/2026-08-08-gpu-monitor-launch.md` lines 1022-1034
(Task 17: documentation write-back, two agent definitions). Also, the ticket's two Comments (transcribed by the
main session) cover the incident-agent status wording, with the second one explicitly saying "supersedes the previous one," so it was
executed per the second one.

## What was done (against the ticket point by point)

The ticket's acceptance items, three of them:

- [x] **The job-monitor definition no longer has two-point rate-measurement operational steps**
  `.claude/agents/job-monitor.md`'s body was rewritten:
  - Deleted the whole manual process of "rate needs two time points" (scan all tasks once first, come back and re-tail,
    compute Δitems/Δt, cross-check against tqdm's self-reported s/it), and deleted the checklist's operational
    details of "two snapshots with current rising," "measured ETA: real remaining amount x measured s/it (a
    sharded task uses the SKILL's correction formula)."
  - Changed to one topic sentence: "verdict, rate, and ETA are now computed by the sampler, you read the ready-made
    conclusion, no longer measuring rate yourself, hand-computing ETA, or parsing tqdm lines," collapsing data retrieval into
    a single command, `python3 run.py gpu-jobs json`, copying `verdict`/progress/rate/ETA/session
    liveness straight into the health table; only fall back to reading logs by hand when json can't be found.
  - The read-only hard rule was kept (a new "no refiring" item added, echoing the division-of-labor section below); the autopsy
    process was kept (`dead` or an escalating `suspected stall` still gets an autopsy: session liveness /
    log tail for a traceback / GPU util); the report format's table structure was kept as-is, with a sentence added, "the verdict
    column is copied directly from `gpu-jobs json`'s `verdict`."
  - Added a new "division of labor with the incident agent" section: job-monitor is the human-dispatched inspector (dispatched
    only when the user or the main conversation asks), the incident agent is the one automatically pulled up by the sampler to handle
    incidents (once the escalate line is crossed, `V_STALL` with `escalated=true`, or `V_DEAD`,
    it automatically records the incident and pulls up a headless `claude` subprocess to handle it); explicitly states "you may not
    execute a refire (`launch --refire`) on its behalf," and when seeing a dead/escalating suspected-stall
    piece, still only reads the log to locate the cause of death as before, writing the suggested action into the report for the main
    conversation or the incident agent to decide.

- [x] **The gpu-runner definition has only one launch path (the queued launchers stay as they are)**
  `.claude/agents/gpu-runner.md`'s local constraints, originally item 3 (the launch command comes from run.py)
  and item 4 (dual registration), were merged and rewritten into one: "launch is always
  `python3 run.py launch`, the working tree must be clean". Pasting in the full usage of
  `launch <task> ... --run-id --track --piece ...`, explaining clearly that it walks through card-probing
  (fail-closed) → tmux → 30-second alive check → three registrations in one go → prints the monitoring entry point, all in one
  command; a `shardable` task with multiple `--piece` gets sharding parameters auto-injected; the wording for the
  dirty-tree hard gate + ledger whitelist exemption was kept verbatim. The original item 4
  (typing the three commands `gpu-jobs register`/`record start`/`runmeta` by hand) was deleted entirely.
  Two exceptions were kept:
  - Exception 1 (queued launchers): `launch-probe`/`launch-eval` are still run directly as before, not going through
    the `launch` subcommand. They automatically do the FREE probe + three registrations internally
    (a product of ticket 11).
  - Exception 2 (refire is not a new task): added a description of `launch --refire <run_id> --idx <N>`.
    Rejected if the session is still alive, rejected if probing the target card finds it non-FREE, on success only that piece's
    four-tuple is updated, no new record opened, no re-registration.
  The report format's "registration receipt" section changed from "gpu-jobs register/record start/runmeta three
  commands + each one's output" to "paste `launch`'s full output (the receipt + two monitoring-entry-point lines);
  when going through a queued launcher, paste the registration line it prints itself; when refiring, paste the refire
  output." The other items (alias de-duplication, no hand-launching, smoke first, don't decide on its own, project isolation,
  log placement, responsibility boundary) were unchanged, only renumbered to follow (3→merged into 3,
  4-9 shifted to 4-8).

- [x] **Commit**: `9ba56ae`, see the commit list below.

## Cross-check with the ticket's Comments (incident-agent wording convention)

Ticket Comments' second entry (superseding the first) required: "the division-of-labor section follows the ticket's
original wording, noting 'wired up, not yet actually rehearsed,' don't write 'not yet live.'" job-monitor.md's
division-of-labor section is written per this wording ("wired up, not yet actually rehearsed, details in
monitor-methodology.md's decision tree section").

Verified: read this branch's `ops/sampler.py` (`maybe_trigger_incidents` lines 170-172),
currently still a `pass` placeholder, with a comment reading "incident triggering is implemented at Task
14 (ticket 12), placeholder for now". That is, ticket 12's (incident triggering) implementation code hasn't yet
landed in this branch's commit history (ticket 12 is `in_progress` in the task ledger, and the main repo worktree at the time had
uncommitted changes to `ops/sampler.py`/`tests/test_incidents.py`). "Wired up, not yet actually
rehearsed" is the exact documentation wording specified by the ticket's Comments (superseding the earlier wording, and it's a user ruling
transcribed by the main session; T15's report, handling the same wording, also confirmed this and wrote per the Comments'
original text). Both documentation spots have the same relationship to the code's commit state, this isn't a new
inconsistency introduced by this ticket.

## How it was verified

A pure documentation change, only touching `.claude/agents/job-monitor.md` and
`.claude/agents/gpu-runner.md`, not touching the `run.py` registry:

```
$ grep -rl "job-monitor\|gpu-runner" tests/
(no output, exit code 1)
```

Neither file is within test coverage, no unit test was run. Still ran `python3 run.py
selfcheck` once as a low-cost check-up (not required by the ticket, but the cost is low):

```
$ python3 run.py selfcheck
...
selfcheck: 63 tasks / 4 recipes, 16 missing
```

All 16 missing items are third-party venv/script paths that don't exist in the worktree (`envs/appworld/venv`
etc.), unrelated to this change's two agent documentation files. A worktree is a working tree rebuilt from git objects,
which doesn't carry over venv directories excluded by `.gitignore`, a known limitation of the worktree environment itself,
not a problem introduced by this change.

At the command level, also ran `git diff --stat` / `git diff` to read through the change for self-consistency, checking each item's
wording against implementation plan `docs/plans/2026-08-08-gpu-monitor-launch.md` Task 17's Step 1/Step 2 original text one
by one to confirm it was carried out.

## Commit list

- `9ba56ae`: `T16: job-monitor slimmed down to read ready-made verdicts; gpu-runner's launch section changed to launch`
  Files changed: `.claude/agents/job-monitor.md`, `.claude/agents/gpu-runner.md`

## Self-check findings and open questions

1. **`gpu-runner.md`'s frontmatter `description` was not changed**: its wording, "measured rate, real ETA,"
   describes what the user can ask job-monitor, not gpu-runner's own behavior; the ticket's Comments don't name the
   frontmatter, and Task 17's Step 1/2 only mention two spots in the body (the launch section merged, the
   registration-receipt part of the report format), leaving frontmatter untouched. Judged as not needing a change.
2. **The six-cell verdict table and decision tree in `monitor-methodology.md` are already the version T15 changed**:
   this ticket references it directly ("what the six-cell verdict means and the decision tree are written
   in……") rather than repeating the table again; whether this needs to also be inlined and repeated in
   job-monitor.md isn't named by the ticket. I judged that "referencing one single source of truth" is less prone to
   drift than repeating it in two places, and handled it by reference.
3. **In the report-format table, "measured rate" was changed to "rate"**: the original header said "measured
   rate," "real ETA," with "measured" emphasizing the old manual measurement process; now that it's changed to
   directly copying the json field, the modifier "measured" is no longer accurate (it's computed by the sampler, not
   measured by job-monitor itself), so I changed the header to "rate," "ETA." The ticket does not fix this header
   wording verbatim, this is my extended judgment on the requirement "delete all the two-point-measurement operational
   details". If the reviewer thinks "measured" should be kept, these two words can be reverted.

No gap requiring `BLOCKED`/`NEEDS_CONTEXT` was found. Both acceptance items, the Comments' wording convention, and Task 17's
Step 1/2 have all been checked off and carried out, the worktree is already clean and ready to commit.
