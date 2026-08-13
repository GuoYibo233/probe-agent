# Quick lane (§2.6)

`<plugin-root>` means the plugin root, three levels up from this file
(`../../..`).

The channel for a small exploratory experiment -- get it done in one pass,
plain and fast, reusing whatever infrastructure already exists. Trigger
phrase: "quick test" (`tables/routes.json`).

## What's exempted

No spec item, no ticket, no batch report, no dispatched close-out review
(`references/closeout.md` doesn't run for a quick batch at all). The launch
order itself can be reduced: `spec_ref` / `issue_ref` / `decision_refs` may
all be left empty, tag it `"quick": true`, and its `run_id` folds into a
quick batch (`batch_id` pattern: `tables/rows.json` →
`batch_report_header.batch_id_pattern`).

## What isn't exempted

This is a numbers-discipline floor, not procedural padding:

- Numbers still enter runs.jsonl only through a script (`metrics_cmd`) --
  no reading a log by eye and typing a value in, quick or not.
- The seed is still fixed in the launch order, same as any other run.
- Launch still goes through `rails.gpu` -- the plugin's one launch entry
  point doesn't get a side door.

## Standing-authorization overlap

A quick experiment expected to finish in under an hour can launch directly
even in default mode, same as the R5 standing authorization for compute
(`references/r5-choices.md`) -- report it after the fact per §2.5, same as
any other self-decided launch.

## Where the result can go

A quick row cannot be cited by the story ledger -- `story add` rejects any
`run_id` whose launch order was `quick=true` (see the idea-layer skill's
`references/story.md`). To bring a quick result into the story, promote it
through the regular route: back it with a spec item, then write a regular launch order using
the original quick order as a template. Carry these fields over verbatim,
unchanged: `seed`, `dataset_version`, `argv`, `env_name`, `filter`. Only
these may change: `run_id`, `batch_id`, `spec_ref`, `issue_ref`,
`decision_refs`, `expected_commit`, and `quick` (now `false`) --
`promoted_from` points back to the original quick `run_id`. Fixing the seed
alone is not a rerun; carrying the whole launch order over is what makes it
one. The quick lane is where an idea gets tried, not where evidence for the
paper comes from.
