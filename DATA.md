# DATA — Data settings and conventions

> Only settings and conventions are recorded here, **no conclusions** — conclusions
> belong to `RESULTS.md`.
> Rebuilt after the 2026-08-02 clear-out. The old phase's data conventions are in the
> git snapshot commit `b1f5b9c`.
> When the new phase's first batch of data is produced, add sections for "how it was
> collected / how it became samples / version / scale and prior baseline."

## Checklist before starting a new experiment

General rules distilled from pitfalls hit in the old phase, go through them in order
before starting any new batch of experiments:

1. **Which data version is being used?** Numbers from different versions are not
   comparable, the version number goes into the run_id and the record.
2. **Is the prior baseline taken correctly?** The prior baseline changes with the data
   version, record it separately per version, never carry it over across versions.
3. **The tier/difficulty numbering uses only one definition.** If the numbering in the
   code and the numbering in the documents ever diverge into two sets, they will get
   swapped.
4. **Comparing wall-clock time?** First confirm the two arms being compared ran on the
   same model of GPU, otherwise the timing column is invalid.
5. **Is the seed fixed?** Data generation/training always fixes a random seed and
   writes it into the report; a rerun must match sample-for-sample.
6. **Was a rebuilt dataset compared byte-for-byte?** The dataset-building script has a
   history of unstable ordering, a byte-for-byte comparison is required after a
   rebuild.
7. **Is the same probe being evaluated across multiple data configs?** Use a symlinked
   copy, otherwise replay reports overwrite each other.
8. **Did this touch any judgment call in `WORKPLAN.md`?** Add an entry to
   `TIMELINE.md`.
9. **Did the generation settings go through a preset?** For any change to a generation
   setting like effort/temperature/budget, first open a new preset under
   `configs/presets/` (do not edit the old one), carry the preset name in the run_id;
   the trajectory meta automatically records the preset name and the expanded
   gen_settings, so it can be checked afterward.

## nyapass_aw_v1 — the np821 batch's collected data (produced 2026-08-22, temperature 1 / 4 per task / equal weight per step)

**How it was collected**: run_id `nyapass`. The model being probed is gpt-oss-120b
(four vLLM instances, tokyo108 GPUs 2 H100 + 3/4/5 H200), preset `default` (api
harmony, reasoning_effort high, temperature 1.0, top_p 1.0, max_tokens 8192,
start_date 2026-08-06), `--max-steps 30`. 4 trajectories per task, seed family
42 / 67 / 4267 / 6742 assigned per trajectory in order by sampling index r0..r3 and
recorded in the trajectory meta; filenames `appworld_<tid>_r<k>.jsonl`. The task list
is the full set of AppWorld's official three splits, 315 tasks (train 90 / dev 57 /
test_normal 168, the txt files have no trailing newline, so `wc -l` reads one less
for each). All 1260 trajectories end with a final line, written to
`envs/runs/nyapass/appworld_gptoss` (via a symlink onto NFS). 41 hit the 30-step cap
(across 35 tasks); 0 pairs of completely identical trajectories (counted, not
deduplicated).

**Seed reproduction boundary**: vLLM's seed takes effect per request, the server's
continuous batching carries numerical noise, resampling with the same seed on a later
run is not guaranteed to be byte-identical; the reproducible source of truth is the
archived raw trajectory itself, not "resample once with the same seed."

**How it became samples**: recipe `annotate-chain`, config
`pipeline/configs/np821_gptoss.json`. Rules: full-sentence-boundary prefixes, equal
weight per step w=1 (`weight_mode: uniform`), a cap of `max_bounds=64` per event's
boundaries (decided at the a1 stop point, TIMELINE 2026-08-22 entry: untruncated
p50 60 / p90 246 / max 842, events over 64 make up 47.8%, subsampling is near-evenly
spaced and always keeps the final cut), the official task list's task-instance-level
three-way split (dev used as val), `trajs_per_unit=4` (the same task's four
trajectories go into the same split, split seed 42).

**Version and scale** (numbers from `ANNOTATE_REPORT.md`): data directory
`pipeline/data/nyapass_aw_v1/gptoss` (NFS). 15216 events, 693583 samples;
train 90 instances · 4127 events · 186479 samples / val 57 · 2556 · 115211 /
test 168 · 8533 · 391893; the tool vocabulary has 150 classes (92 classes appear
fewer than 5 times, the long tail); task-text length p50=4876 / p90=13432 /
max=52351 characters (anything over 4096 tokens is left-truncated by the training
scripts). Argument annotation is in the `params/` three splits, with the same row
counts per split as the main data (874014 arguments, found_rate 0.846).

**Prior baseline**: the test event-level frequency prior is 0.387 (always guessing the
most frequent tool, `apis.api_docs.show_api_doc`). Recorded separately for this
version, not carried over across versions.

**Gates and rebuild**: `check_callstr` gate A (all 693583 rows have correct model
attribution), gate B (all sample keys unique; K=4 is the new criterion, each of the
315 units pairs with exactly 4 mutually distinct trajectories, sampling indices
r0..r3 all present), gate D (full check of task-list membership) all pass; gate C is
skipped (appworld does not go through the runs.glob path), gate E is skipped (no
SPLIT_REPORT.json). The ground-truth call string reads back 15192/15216 (0.9984),
argument instances 19095/19132 (0.9981), the main cause of failure is an argument
value containing a comma, 21 cases (the same known bias as p1, the ceiling
convention is in the header of CALLSTR_CHECK.md). Rebuild comparison (checklist item
6): `a3_gates` reran all 12 artifacts of build+param_label, byte-for-byte `cmp`
identical. The CHECK_50 manual check: 50 located / 10 not found.

**Convention note**: numbers at temperature 1 are not comparable with any historical
number at temperature 0 (the aw_p1_v1 line). Against aw_p1_v1, there are exactly
three convention differences: temperature (1.0 vs. 0.0), trajectories per task (4 vs.
1), sample weighting (w=1 per step vs. w=1/m_i within an event); the cut-point cap is
the same 64 in both.

## aw_p1_v1 — the p1 batch's collected data (produced 2026-08-21)

**How it was collected**: run_id `p1`. The model being probed is gpt-oss-120b (two
vLLM instances, tokyo108 two H200 cards), preset `gptoss_harmony_high` (api harmony,
reasoning_effort high, temperature 0.0, start_date 2026-08-06), `--max-steps 30`, seed
20260729. The task list is the full set of AppWorld's official three splits, 315
tasks: train 90 / dev 57 / test_normal 168, files at
`envs/appworld/data/datasets/{train,dev,test_normal}.txt` (⚠️ none of the three txt
files has a trailing newline, `wc -l` reads one less for each). All 315 trajectories
end with a final line, written to `envs/runs/p1/appworld_gptoss` (via a symlink onto
NFS).

**How it became samples**: recipe `annotate-chain` (ann-build → ann-params →
ann-check-callstr), config `pipeline/configs/p1_gptoss.json`. Rules:
full-sentence-boundary prefixes, equal weight within an event w=1/m_i, a cap of
MAX_BOUNDS=64 per event's boundaries, the official task list's task-instance-level
three-way split (dev used as val).

**Version and scale** (numbers from `ANNOTATE_REPORT.md`): data directory
`pipeline/data/aw_p1_v1/gptoss` (NFS). 4048 events, 175359 samples;
train 90 instances · 1098 events · 46438 samples / val 57 · 675 · 29202 /
test 168 · 2275 · 99719; the tool vocabulary has 83 classes (57 classes appear
fewer than 5 times, the long tail); task-text length p50=4645 / p90=13364 /
max=47019 characters (anything over 4096 tokens is left-truncated by the training
scripts). Argument annotation is in the `params/` three splits, with the same row
counts per split as the main data.

**Prior baseline**: the test event-level frequency prior is 0.419 (always guessing the
most frequent tool, `apis.api_docs.show_api_doc`). Recorded separately for this
version, not carried over across versions.

**Gates and rebuild**: `check_callstr` gate A (all 175359 rows have correct model
attribution), gate B (all sample keys unique, each of the 315 units pairs with one
trajectory), gate D (full check of task-list membership) all pass; gate C is skipped
(appworld does not go through the runs.glob path), gate E is skipped (no
SPLIT_REPORT.json, the official split has no such artifact). The ground-truth call
string reads back 4041/4048 (0.9983), argument instances with a comma 5/5267. Rebuild
comparison (checklist item 6): build+param_label reran once, the seven data files and
every report matched byte-for-byte `cmp`.

**Convention note**: not comparable with aw_official_v1's numbers (a different effort
tier, see the generation-settings section of
`plans/archive/2026-08-21-p1-collection-plan.md`), use only as an order-of-magnitude
reference.
