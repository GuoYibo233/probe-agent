# T17: Documentation write-back for probe-pipeline and root documents

## What was done

The What-to-build section of ticket 17 points out that steps follow implementation plan
`docs/plans/2026-08-08-gpu-monitor-launch.md` Task 18's execution; that Task's Files list and Step 1 are this round's
work's concrete instruction source. Point by point:

1. **Three key new statements landed verbatim into their corresponding files** (the ticket's acceptance requirement 1):
   - "`python3 run.py gpu-jobs register` and `python3 run.py record start` done together" →
     **"launch auto-writes all three; the manual/register backfill path still exists, missing it is still a violation"**,
     landed at `SKILL.md:134` (G16, Phase C3) and `references/gates.md`'s G16 row.
   - invariants.md's dual-write-to-the-ledger row → **"the dual write is guaranteed by launch; for those who bypass
     launch and hand-launch, dual-registration responsibility falls back on the human"**, landed at
     `references/invariants.md` §5's ledger-dual-write row.
   - extending.md's new-script checklist got a hard item added → **"a new collection/training/eval script must
     wire into `ops/heartbeat.py` (emit(0,...) as it enters the main loop, emit per unit, status=done at
     the end); a script that doesn't will forever show as warming up in the outlets"**, landed at
     `references/extending.md` §3.2's "what can be copied, what can't" table, a new row added, "heartbeat
     emit," right next to that table's existing row for the `train_log.jsonl` `log()` closure (line 130, matching
     the line number given by implementation plan Task 18). This row honestly notes which scripts are already wired
     (the four training scripts, three eval scripts, `run_appworld.py`, each verified one by one via
     `grep import heartbeat`) and which aren't yet (`run_tales.py`/`run_alfworld.py`/`run_tau2.py`), not
     writing it as "all scripts already wired."

2. **MAP.md's old and new program rows are all present** (the ticket's acceptance requirement 2):
   - `ops/gpu_jobs.py`'s row updated: added that register is now mostly called automatically via
     `run.py launch` (`launch_common.register_all`), with hand-typing this command being the
     backfill path for missed registration; added that `status`/`watch` both go through
     `collect(with_extras=True)`, at the end listing out-of-ledger tmux sessions (source verified: `ops/gpu_jobs.py`'s
     `cmd_status`/`cmd_watch` both call `collect(with_extras=True)`).
   - Added three new rows: `ops/heartbeat.py` (the heartbeat emit/parse primitives), `ops/verdicts.py`
     (the six-cell verdict pure-function engine), `ops/launch_cmd.py` (`run.py launch`'s
     subcommand body, the ten-step flow + `--refire` refire). None of these three previously had an
     independent row in MAP.md at all (they were only mentioned in the descriptive text of the
     `sampler.py` row).
   - `ops/launch_probe.py` / `ops/launch_eval.py` / `ops/launch_common.py` /
     `ops/sampler.py`'s four rows were checked and confirmed **already synced in T09/T11/T14's respective
     wrap-up commits** (with `register_all` wiring, track naming, incident-trigger pure functions landing, and
     other latest states included), unchanged in this round, avoiding a meaningless rewrite.

3. **Related alignment** (the range required by the What-to-build section's sentence "probe-pipeline and its
   references…the handoff skill, CLAUDE.md, MAP.md, gpu_state's header should all align with the new flow," carried out
   item by item against implementation plan Task 18's Files list):
   - `gates.md` G2 row: added that `launch`/`launch-probe`/`launch-eval` each also re-probe every
     piece automatically, manual `free` is not the only line of defense.
   - `gates.md` G17 row: added "this step isn't collected by launch. G16's automation only manages
     registration at launch time, deregistering still needs the manual four-step sequence run", avoiding readers
     over-generalizing G16's automation onto G17.
   - `SKILL.md`'s agent division-of-labor table (near the original :221-222): the `gpu-runner` row, "probe→
     smoke→tmux→register→verify-alive, one seamless flow," rewritten as "probe→smoke→`launch` (auto three
     registrations + verify-alive), one seamless flow," aligned with the ten-step flow.
   - `stage-commands.md` near :19: added a paragraph explaining that a task marked `[launch]` now goes through
     one command, `python3 run.py launch <task> ...`, no longer needing to manually
     "`show` the command → copy it into tmux → hand-type three registration commands."
   - `stage-commands.md` :352 (the parallel/serial explanation section after S11): the whole sentence rewritten,
     replacing the old description "post-launch dual registration ... + ..." with the wording "launch auto-writes all
     three; the manual/register backfill path still exists, missing it is still a violation."
   - `.claude/skills/handoff/SKILL.md`: Phase 1's step 1 evidence command
     `python3 ops/gpu_jobs.py json` (a bare call to a script in `ops/`, violating "everything goes through
     run.py") changed to `python3 run.py gpu-jobs json`, with an honest addition that verdict/rate/ETA
     are currently only complete on the web outlet `http://localhost:8377/json`; the terminal
     `gpu-jobs json` wiring up to read sampling history is still ticket 07 (in_progress), and before it's wired up,
     progress relies on tailing the log by hand, not written as if all three outlets are already ready. The handoff
     document's six-section template's "tasks currently running" row got a note added pointing progress sources at
     `run.py gpu-jobs json` + the sampling-history web json.
   - `CLAUDE.md`'s gpu-run section: added a sentence, "launch and registration are collapsed into
     `python3 run.py launch`, one command (probe/tmux/verify-alive/three registrations done all in one
     go)"; the "user self-service monitoring" row got the web `http://localhost:8377` added (no
     duplicate row added, folded directly into the existing "user self-service monitoring" row, avoiding repeating the
     same content in the same paragraph).
   - `ops/gpu_state.md`'s header: added a line, "the login machine's permanent sampler computes the verdict:
     `python3 run.py sampler --interval 60 --port 8377`; web
     `http://localhost:8377` (ssh port forwarding), `/json` outputs a machine-readable verdict."

## How it was verified

This ticket is a pure documentation change, with no executable test seam; the check method was reading through the changed
text again, and using the command line to check that Markdown table structures weren't broken, and that no wording contradicting other
tickets' actual current progress (like ticket 07's in_progress state) was introduced.

1. **Markdown table column-count check** (every table changed, the column count must match before and after the change):
   ```bash
   awk -F'|' 'NR==8{print NF}' .claude/skills/probe-pipeline/references/gates.md
   grep -n "^| G2 \|^| G16 \|^| G17 " .claude/skills/probe-pipeline/references/gates.md | awk -F'|' '{print NR": fields="NF}'
   ```
   Output: header 7 columns, G2/G16/G17's three rows all 7 columns after the change. Column count not broken.

   ```bash
   awk -F'|' 'NR==131{print NF}' .claude/skills/probe-pipeline/references/extending.md
   ```
   Output: `5`. The newly added heartbeat-emit row matches the column count of §3.2's other rows (3 content columns + head and tail empty = 5).

2. **Heartbeat-wiring surface check** (making sure extending.md's new row's statement about "which scripts are wired/not wired" is grounded):
   ```bash
   grep -rln "import.*heartbeat\|from.*heartbeat" pipeline/ envs/collect/*.py
   ```
   Output: `pipeline/eval/eval_mbert_call.py`, `pipeline/eval/eval_causal_call.py`,
   `pipeline/eval/eval_tool.py`, `pipeline/train/train_causal_callgen.py`,
   `pipeline/train/train_mbert_extract.py`, `pipeline/train/train_causal_tool.py`,
   `pipeline/train/train_mbert_tool.py`, `envs/collect/run_appworld.py`, 8 files total,
   matching exactly what the new row says, "four training scripts + three eval scripts +
   `run_appworld.py` already wired"; separately, `grep -l "import heartbeat"
   envs/collect/*.py` confirmed `run_tales.py`/`run_alfworld.py`/`run_tau2.py` are not in the hit
   list, matching that ticket 03's scope was only ever appworld, honestly noted as unwired.

3. **Source check for the new gpu_jobs.py description**:
   ```bash
   grep -n "def cmd_status\|def cmd_watch\|with_extras" ops/gpu_jobs.py
   ```
   Confirmed `cmd_status()`/`cmd_watch()` both take data via `collect(with_extras=True)`,
   and `collect(with_extras=True)` additionally collects out-of-ledger sessions. MAP.md's new description is accurate.

4. **`python3 run.py selfcheck`** (this ticket doesn't touch the run.py registry, but per the implementer's protocol's
   boundary of "changed something related to the run.py registry," ran it once anyway to be careful):
   ```
   selfcheck: 63 tasks / 4 recipes, 16 missing
   ```
   All 16 missing items are "missing interpreter/program" (like `envs/appworld/venv/bin/python`,
   `mbert-env/bin/python`, etc.), an existing environment issue from this worktree simply not having each
   environment's venv built, unrelated to this ticket's pure documentation change. This ticket did not touch `run.py`'s TASKS/
   RECIPES/CELLS/EVAL_CELLS, this boundary rule isn't triggered here, this was just to confirm the documentation
   change didn't introduce a new registry error.

## Commit list

- `e7f31b6`: `T17: docs: probe-pipeline/handoff/CLAUDE/MAP/gpu_state aligned with launch+sampler`
  (branch `ticket/20260808-par/T17`, base `f8c9965`). One commit, 9 files changed, 27 lines
  added / 11 lines deleted:
  `.claude/skills/handoff/SKILL.md`, `.claude/skills/probe-pipeline/SKILL.md`,
  `.claude/skills/probe-pipeline/references/{extending,gates,invariants,stage-commands}.md`,
  `CLAUDE.md`, `MAP.md`, `ops/gpu_state.md`.

## Self-check findings and open questions

- **The line numbers given by implementation plan Task 18 (like extending.md:130, SKILL.md:74-75/172-173/
  221-222) are a snapshot written the same day, mostly matching this ticket's actual line numbers at execution time**
  (extending.md:130 hits precisely on the `train_log.jsonl` `log()` closure row, with the heartbeat row inserted right
  next to it). But for SKILL.md's :74-75 (the Phase A wrap-up chain: G6/G7/finish/commit) and :172-173
  (Phase D's release/deregister two steps), on re-reading I judged **the content itself is procedurally still
  accurate** (Phase D's two steps already carry the fail-closed/`--force` explanation, written by some earlier
  change, not something this ticket needs to fill in). I found no specific text that needed rewriting because of "launch
  collecting registration," so these two spots **were not changed** this round, only the parts closer to them in the same
  Phase that were genuinely outdated were touched (the G16 paragraph, Phase C3, and the agent division-of-labor table
  near the original :221-222). If the main session thinks these two spots should also get a pass (even just to
  align the wording), I can do a follow-up round; but currently I found no specific point of "content is wrong" or
  "content is out of date," and was worried about forcing wording changes into a meaningless diff, so I've treated them
  for now as "content already accurate, no need to touch," noted here for the record.
- **CLAUDE.md's "add a sentence" was not a verbatim copy of the ticket's example sentence** (the ticket's given example
  sentence was "launch and registration collapsed into `run.py launch`, user self-service monitoring =
  `gpu-jobs watch` + web 8377"). I split this sentence into two places: one added independently ("launch
  and registration collapsed into one command, launch"), the other folded into the already-existing "user
  self-service monitoring" row (avoiding writing the same `gpu-jobs watch` command twice in the same
  paragraph). The meaning is fully consistent with the ticket's description, just not stacked verbatim into one sentence. This isn't
  among the "three key new statements" (those three being G16/ledger-dual-write/heartbeat checklist, already landed
  verbatim). Here I judged that the ticket's example sentence only gives direction, allowing me to split it into sentences naturally
  given the context; if there's a discrepancy please point it out, I can change it back to a verbatim single sentence.
- **Related files not touched**: `.claude/skills/probe-pipeline/references/gates.md`'s G3–G15,
  G18–G22, and `invariants.md`'s other convention rows were not touched this round, because they are
  unrelated to these two changes (launch/heartbeat), out of this ticket's scope. Per YAGNI, not opportunistically changed.
- **Ticket 16 (write-back of two agent definitions) and ticket 18 (wrap-up self-check) were both untouched
  this round**. They are `pending` in the task ledger, not within this ticket's scope.

## Fix round 1 (2026-08-09)

Branch `ticket/20260808-par/T17`, worktree `/home/y-guo/reproduce/new1-wt/20260808-par-T17-fix1`,
base `e7f31b6` (the previous round's implementer's wrap-up commit).

### F1 (critical): gates.md G2 mis-wrote launch-probe/launch-eval's non-FREE handling as "whole-batch rejection"

**Problem**: the previous round's newly-added sentence in the G2 row described `run.py launch`, `launch-probe`,
`launch-eval`'s non-FREE handling as all the same one behavior, "any single card non-FREE, the whole batch
rejected." Checking the source:

- `ops/launch_cmd.py:271-272` (`run.py launch`, single-task/multi-piece mode): probes each piece with
  `probe_free` one by one; as soon as any single card is non-FREE, `raise SystemExit`, **genuinely not
  launching a single one of the whole batch**. This sentence is correct for `launch`.
- `ops/launch_probe.py:46-56` and `ops/launch_eval.py:62-72` (the `launch_and_register`
  function): a single cell's `probe_free` finding non-FREE only does `print(f"SKIP (non-FREE): ...")`
  and `return False`, the loop keeps going to launch the next cell, it doesn't `raise`, doesn't abort the
  whole batch's call. It's "skip this cell," not "whole-batch rejection."
- Cross-checked against MAP.md's existing description (this round of T17 did not change these two lines, cross-checkable
  within the same version): `ops/launch_probe.py`'s row says "non-FREE prints the reason and skips this cell
  (a half-empty queue table is common, **doesn't reject the whole table**)," `ops/launch_eval.py`'s row says "non-FREE
  skips this cell", directly contradicting the old G2 row's new sentence.

**How it was fixed**: split the G2 row into two sentences, each describing the two kinds of launchers' actual behavior:

```diff
-`python3 run.py launch`/`launch-probe`/`launch-eval` internally also re-probe every
-piece automatically, any single one non-FREE rejects the whole batch, manual `free` is for a human to pick
-cards with, not the only line of defense
+`python3 run.py launch` internally also re-probes every piece automatically, any single one non-FREE
+rejects the whole batch (fail-closed, none of them get launched); `launch-probe`/`launch-eval` (queued batches)
+re-probe cell by cell, non-FREE only prints the reason and skips that cell, continuing to launch the next one, not a
+whole-batch rejection, manual `free` is for a human to pick cards with, not the only line of
+defense
```

The change only lands in `.claude/skills/probe-pipeline/references/gates.md`'s G2 row, without touching
G16/G17 (those two rows are about registration behavior, all three launchers' registration logic is consistent, no similar
problem).

**Tests**: this ticket has no executable test seam throughout, verification method reused the previous round's report's table
column-count check, plus an extra whole-repo search this time to confirm there's no second spot with the same mistaken wording.

```
$ awk -F'|' 'NR==8{print "header:",NF}' .claude/skills/probe-pipeline/references/gates.md
header: 7
$ grep -n "^| G2 \|^| G16 \|^| G17 " .claude/skills/probe-pipeline/references/gates.md | awk -F'|' '{print NR": fields="NF}'
1: fields=7
2: fields=7
3: fields=7
```

Header 7 columns, the changed G2/G16/G17 rows all 7 columns after the change. Table structure not broken.

```
$ grep -rn "launch.*launch-probe.*launch-eval.*whole-batch rejection\|launch-probe.*launch-eval.*whole-batch rejection" \
    .claude/skills/probe-pipeline/ CLAUDE.md MAP.md ops/gpu_state.md
exit=1(no match)
```

Confirmed the old kind of wrong statement, "all three launchers always reject the whole batch," has no second copy
elsewhere (stage-commands.md, invariants.md, SKILL.md, CLAUDE.md, MAP.md, gpu_state.md). Where these files
have the phrase "whole-batch rejection"/"fail-closed" appear, they're talking about something else
(`ops/launch_cmd.py`'s own ten-step-flow description, `gpu-jobs finish`'s fail-closed deregistration), not
involving `launch-probe`/`launch-eval`'s probing behavior, no need to change those along with it.

### Commit list (this round)

- `80b6cbf`: `T17: fix: gates.md G2 split apart launch's and launch-probe/launch-eval's non-FREE handling`
  (branch `ticket/20260808-par/T17`). One file, 1 line changed:
  `.claude/skills/probe-pipeline/references/gates.md`.

### Self-check findings and open questions (this round)

- Only the G2 row was touched, no scope-widening rewrite of surrounding wording. The finding only names this one
  row, and everywhere else gates.md/invariants.md/stage-commands.md mentions launch/launch-probe/launch-eval was
  read through one by one, no second spot found conflating the two's behavior.
- No new GPU process launched, `run.py` registry untouched, `selfcheck` not run (this round's change is unrelated to
  TASKS/RECIPES/CELLS/EVAL_CELLS, this boundary rule isn't triggered).
