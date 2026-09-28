# plans/archive

Archived 2026-09-08. This holds plans, reports, and review records that have
already wrapped up or been superseded by later documents; filenames are
unchanged, they were just moved from `plans/` to `plans/archive/`.

Append-only ledgers (`TIMELINE.md`, `ops/runs.jsonl`), plus collection
manifests and batch config JSON (`pipeline/collect/manifest_*.json`,
`pipeline/configs/np821_gptoss.json`, which the driver records by file-byte
sha1) still write the old path `plans/<filename>`: when you see the old path,
look in this directory for the file with the same name. Pointers in live
documents and code (run.py, MAP.md, DATA.md, METHOD.md, WORKPLAN.md, comments
in pipeline, `.scratch/kvshare-train/`) have already been changed to the new
path.

The research-loop lineage that used to sit in this directory (the six
2026-08-16/17 v1 documents, the 2026-08-21 parts-review items, and
`2026-08-21-review-findings.md`) moved to
`/home/y-guo/research-loop/plans/archive/` when research-loop split out into
its own repository on 2026-09-12.

Since 2026-09-12 this directory is named "ancient memory" (gyb's ruling): read
only when gyb explicitly says "check ancient memory" or names a specific
archived file; otherwise not read, not cited, not used to answer questions.
The rule is written in the repo root `CLAUDE.md`. On the same day the 7
entries in `TIMELINE.md` from 2026-08-02 to 2026-08-18 were moved verbatim
into `TIMELINE-2026-08-02-to-2026-08-18.md`.

| File | Which line it belongs to | Why archived |
|---|---|---|
| `TIMELINE-2026-08-02-to-2026-08-18.md` | TIMELINE ancient entries | 2026-09-12 gyb ruled that all records before 2026-08-20 be archived; 7 entries moved verbatim from `TIMELINE.md` (diff-checked byte-identical) |
| `2026-08-10-z1-plan.md`, `2026-08-10-z1-smoke-report.md` | z1 injection smoke test | smoke test complete, conclusion recorded in METHOD.md's R3 line |
| `2026-08-18-ident3.md`, `2026-08-18-splice-replay.md` | replay injection | code for both lines has landed and is wired into run.py; the plans now serve only historical purposes |
| `2026-08-21-lora-current-state.md` | np821 | a status snapshot, superseded by the 08-26 results report |
| `2026-08-21-new-probe-training.md`, `2026-08-21-p1-collection-plan.md`, `2026-08-21-np821-plan.md` | p1 / np821 | both batches of data and training have wrapped up, results are in RESULTS.md and `2026-08-26-np821-results.md` |
| `2026-08-22-np821-exec-worklog.md`, `2026-08-26-np821-results.md`, `2026-08-26-hparam-survey.md` | np821 | the execution worklog, results report, and hyperparameter survey after the np821 twelve cells wrapped up; the kvshare-train line took over starting from `plans/2026-08-28-plan.md` |
