# Regression checks

`<plugin-root>` means the plugin root, three levels up from this file
(`../../..`).

`regression_check.py` compares one batch's new numbers against the story
ledger's active claims, same-filter only, and reports facts -- it renders no
judgment (R2, R3): whether an old/new difference matters is the user's and
the idea layer's call, never this script's.

## Running it

```
python3 <plugin-root>/scripts/regression_check.py --batch <batch_id> [--project-root <root>]
```

For every `story` row with `status=active`: `metric_names` empty or null
puts that `claim_id` in the report's **Skipped** table -- explicitly, not
silently dropped and not treated as a comparison (`tables/rows.json`
story_row.metric_names: "metric_names 为空的 claim 列入跳过清单"). Otherwise,
for each metric name the claim carries, its `evidence_runs`' rows sharing
that `metric_name` are grouped by their own `filter`; for each distinct
filter, the named batch's rows sharing that same `(metric_name, filter)`
pair are the new values. A comparison entry only appears when the new batch
actually has at least one matching row -- no entry manufactured out of
nothing.

Every comparison entry is data only: `claim_id`, `metric_name`, `filter`,
`old` (run_id/value/filter for each old row), `new` (same shape for the new
ones) -- no adjudicating language anywhere in the rendered text.

## Output

One markdown report: a **Comparisons** table, a **Skipped** table, and an
R3 provenance block in the frontmatter (`generated_at`, `git_head`,
`story_rows_read`, `runs_rows_read`). Without `--dry-run`, the same text
lands at `reports/regression-<batch_id>.md` (this ledger's own naming
convention -- oversight owns `reports/` outright); `--dry-run` prints to
stdout and writes nothing.

`--dry-run` exists for exactly one other caller: `doctor.py`'s own
regression section feeds it the latest batch_id it finds in the runs
ledger. Doctor must never write under `reports/` -- that's this face's
exclusive territory (`tables/writes.json` → `owner_values.oversight`) -- so
doctor's call is always `--dry-run`, printed into its own combined report
and never landing a file here.

## When this runs, relative to a batch's other checks

This is not part of the three-script suite a dispatched `inspector` runs at
close-out (`references/inspection.md`, `trace_check.py` /
`evidence_lint.py` / `verify_report.py`) -- it's a separate action this
session runs directly, typically once per batch after the runs land and
before the idea layer rules on whether the result enters the story (spec §8
step 6: inspector's observation report + a spot-check + this, then the user
reads the originals, then the story ruling happens). Running it earlier than
that (before the batch's runs are all in) just produces fewer new-value
matches, not an error -- there's no ordering gate enforced by the script
itself.
