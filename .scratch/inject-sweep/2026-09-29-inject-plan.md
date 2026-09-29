# Inject sweep: confirmed action list (2026-09-29)

Discussed step by step with gyb on 2026-09-29 (detail-check), after the probe
line in `2026-09-29-probe-plan.md`. Every step is locked.

## Goal (confirmed)

Run the live injection loop (stream the agent's thinking, score each sentence
cut, fire at theta, discard the tokens past the cut, splice the prefetched
result in, resume) on a small fixed set of test tasks under many settings, to
see which settings help and which hurt. Success: one registry row per
setting, all on the same 20 tasks and seed, paired against a baseline on the
same tasks; the raw records keep every fire so scoring can be redone later.
Not doing this round: any probe training, a richer score report (gyb writes
the evaluation code later), full test-split runs.

## Action list

1. Tasks (locked): 20 test tasks drawn at random with a recorded draw seed,
   written as a fixed task list into the baseline and inject settings. Who:
   agent draws and hands over the list; gyb writes it into the setting files.
2. Seeds (locked): one seed per task. Each row is 20 task runs; one task
   flipping moves success by 5 points, accepted as the price of many settings.
3. Grid (locked), 122 runs x 20 tasks:
   - probe arm: 4 pairs x 4 formats (p1_e1, p1_e2, p2_e1, p2_e2) x 3 thetas
     (0.6, 0.75, 0.9) x 2 history lengths (last 3 rounds, every round) = 96;
   - no-fill arm (cut and resume, nothing spliced): 4 pairs x 3 thetas x 2
     history lengths = 24; it isolates the cost of the interruption;
   - no-probe arm: 2 (plain; with the e2 system paragraph); it isolates the
     system text.
   The old fifth format (the system-note line) is dropped.
4. Knobs held fixed (locked): one fire per step, at most 64 cuts scored per
   step, 96 tokens for the probe's call.
5. Scoring (locked): run first. The score report stays as it is (task success
   paired against the baseline); gyb writes the evaluation code later. The
   raw records already hold, per fire, the cut, confidence, predicted call,
   execution result, injected text and discarded token count, and per step
   the token usage.
6. GPUs and order (locked):
   - agent servers: tokyo108's 3 H200 (2 runs each) and 3 H100 (1 run each);
     tokyo106: 4 two-card A6000 servers (1 run each) if a smoke of one
     two-card server serves, else none;
   - probe services, one per run: the remaining small cards (tokyo105 7 free,
     tokyo107 4, tokyo106 2);
   - 13 runs in flight when the A6000 servers work, 9 otherwise; launches in
     waves; wall time estimated 5 to 10 hours;
   - order: one debug smoke, then the 0.6B full pair's whole grid, then the
     other three pairs;
   - launcher change needed: a run attaches only to a live agent server on
     the cards its launch names (today it attaches to any live server on the
     same host, which would pile every run onto one server);
   - monitoring: a read-only monitor agent on a 40-minute loop reads the run
     table and reports progress, rate, stalls and dead pieces; the main
     conversation acts on the report.

## Dropped during the discussion

- The fifth format (system-note line): predates the 2026-09-12 four-arm
  ruling; 24 runs saved.
- Adding four numbers to the score report now (fires per task, call
  agreement, execution success, output tokens): deferred to gyb's own
  evaluation code.
- First-20-of-the-list task selection: replaced by a seeded random draw.

## Code changes this plan needs (agent), each with a version row

1. build: abort gate removed, aborted step skipped, count reported (probe plan step 2).
2. train: `import_from` path, no prediction, imported calibration (probe plan step 3).
3. eval: an imported run's eval records imported numbers and fits nothing (probe plan step 3).
4. launch: attach only within the named card pool; two-card agent server on A6000.

## Owner edits (gyb)

- baseline setting: the 20-task list, one seed, test split only.
- train_probe file: eight imported probe settings with the August paths and
  a 16k served window.
- inject file: the sweep blocks (arm x format x theta x history length) per
  pair, the no-fill and no-probe settings, all on the same task list.

## Execution order

Code changes and the two-card server smoke first (no owner edit needed for
the smoke), owner edits in parallel, then a debug smoke of one inject child,
then the waves.
