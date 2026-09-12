# 18 — Final wrap-up self-check

**What to build:** Wrap up the whole chain: full unit tests plus
selfcheck all green; a final grep sweep confirms no leftover old-flow
narration about "hand-typing three registration commands" remains in the
repo; a review pass over the CONTEXT.md glossary against the
implementation (words that emerged during implementation, such as
shardable and the monitor-parameter field names, get collected into the
glossary with a date noted); the final report covers the change list, a
new-command quick reference, the watchdog crontab line, and the explicit
v1 not-doing list. Steps follow Task 19 of the implementation plan.

**Blocked by:** 15 Doc write-back gpu-run, 16 Doc write-back agent
definitions, 17 Doc write-back probe-pipeline and root docs (and
everything upstream of them)

**Status:** resolved

- [x] `python3 -m unittest discover -s tests -v` all green plus
  `python3 run.py selfcheck` passes
- [x] grep results for double registration, record start, and register
  are all in the new context
- [x] CONTEXT.md review done, new words collected
- [x] Final commit plus report

## Comments

- 2026-08-08 transcribed by the main conversation (two items added to
  the final self-check): first, gpu-run SKILL.md's hand-typed backfill
  path uses a generic RUNMETA `--kind` placeholder, while launch's
  automatic registration writes kind="launch"; these are two different
  value sets, and at wrap-up check whether docs and code need to be
  unified on this; second, launch-methodology.md Step6 still has the old
  wording "ETA claims need >=60s of tqdm observation," which doesn't
  line up with the rewritten monitor-methodology.md's verdict-value
  inputs, to be aligned together at wrap-up.
- 2026-08-09 transcribed by the main conversation (from T13's wrap-up):
  one more item added to the final self-check, the port field's path
  from launch to sampling breaks on the registration side (launch's
  --port only passes through and doesn't land in piece, and register
  doesn't recognize --port/--kind), so a service record with
  kind="service" has no ready-made command line for registering it; this
  must be listed as a known gap in the final report, with the user to
  decide whether to open a follow-up ticket.
- 2026-08-09 main-conversation wrap-up execution record: 117 tests all
  green + selfcheck's 63 tasks all in place; grep hits on the three key
  terms are all in the new context of "launch does it automatically /
  the backfill path"; CONTEXT.md gained two new words, shardable and
  monitor parameters (dated 2026-08-09). Rulings on the two added items:
  RUNMETA `--kind` is not unified to one value, since kind was always
  meant to be a free-form string, and the three launchers each write
  their own (launch / train / eval_<stage>); a phrasing note was added
  next to gpu-run SKILL.md's placeholder to explain this. Re-checking
  launch-methodology.md Step6 found the old "≥60s tqdm" wording had
  already been changed in T15 (the current text at line 141 reads "ETA
  claims come from the sampler's verdict, not hand-parsed tqdm"), so no
  further change is needed. The sampler was restarted onto the
  post-merge code (restarted during a window when the ledger's active
  list was empty, no monitoring interruption), and the watchdog crontab
  is in place. The port-passing gap remains pending a decision.
- 2026-08-09 Phase 4 final review and fix-loop closure (this is the
  final record): the opus whole-branch final review (f30e6cf..5963842)
  produced 3 critical + 2 important + 21 observations. All five
  merge-blocking items were fixed and judged ADDRESSED by a sonnet
  scoped re-review (commits
  f79b0d5/2136f97/3b0642c/66eb140/0d26563/8ff20e7): C1, the test suite
  really spawned a paid opus subprocess (fixed with a double defense of
  a mock plus NEW1_NO_SPAWN; after the fix, all 124 tests were verified
  to spawn zero subprocesses); C2, --service without a port would
  inevitably be misjudged as dead (launch now requires --port and lands
  it in piece, register adds --port/--kind); C3, incident-trigger
  exception isolation + shutil.which resolution + state.json's disk
  write moved to right after the trigger; I4, five spots of stale doc
  text plus a deployment-facts section added to gpu_state; I5, the
  verdict engine gets an assertion covering the two service cells and
  the verdict-line main formula. Two rulings on newly found issues from
  the re-review: --port gets cut off by launch before the -- and isn't
  passed through, an existing convention in the same category as
  --outdir being shadowed (task-side flags go after --), left as is; the
  piece's port:null versus register's default not carrying the key at
  all is a schema drift with no real harm, noted as-is. Of the final
  review's 21 observations, the unaddressed ones are kept verbatim in
  the final-review record; three key ones are passed on for the user to
  decide: eyeball RESULTS.md's rendering after the first real
  multi-piece launch; the incident chain, even after the fix, still
  hasn't been rehearsed for real, recommend rehearsing once on a fake
  piece during the day; the web page binds to all network interfaces
  with no authentication (the spec only requires ssh forwarding, this
  could be tightened to 127.0.0.1). The two leftover /tmp sampler
  processes from T06 have been cleaned up (pid 2574051/2575583). The
  sampler was killed at 22:18 and pulled back by the watchdog under the
  cron environment at 22:20, running the HEAD with all fixes included.
