# Story rulings

`<plugin-root>` means the plugin root, three levels up from this file
(`../../..`).

The story ledger is a record of the user's rulings on what counts as a result worth keeping. This layer never adds a claim on its own initiative -- every `story add` follows a ruling the user just made in conversation.

## Adding a claim

```
python3 <plugin-root>/scripts/ledger.py story add --layer idea \
  --claim "<one-sentence claim>" --evidence-runs <run_id[,run_id...]> \
  [--baseline-runs <run_id[,run_id...]>] --candidate-runs <run_id[,run_id...]> \
  [--metric-names <metric_name[,metric_name...]>] \
  --selection-rule "<how the candidate was picked>" \
  --derivation-command "<R4 recompute command, or the raw read if no derivation>" \
  --principle-id <P00x> --role <see tables/rows.json enums.story.role>
```

Walk the user through each of these before writing, not just the claim sentence:

- **evidence / baseline / candidate runs**: which run_ids back the claim, which are the comparison point (if any), which are the thing being claimed about. A run must exist in runs.jsonl with `status=ok` to be citable here.
- **baseline_runs, single-arm claims**: omit `--baseline-runs` entirely when there's no comparison object -- a claim that stands on its own, not against anything. The row then lands with `baseline_runs=null` (`tables/rows.json` → `story_row`: "null=单臂绝对陈述，没有对照对象，不是漏填"). Don't paper over an actual missing baseline by citing the candidate run a second time under `--baseline-runs`: if given, the baseline set must not equal the candidate set exactly -- a claim "compared" against itself is empty, and `storycmd.py`'s own check rejects the write.
- **metric_names**: leave empty only when this claim has no fixed metric anchor; otherwise name the metrics `regression_check` should hold this claim to on future batches (`tables/rows.json` → `story_row`, and the oversight skill's `references/regression.md`).
- **selection_rule**: how the candidate got picked out of whatever else was tried -- this is what stops a claim from silently being the best of many unmentioned runs.
- **derivation_command**: the R4-approved recompute command if this claim involves a derived quantity (see `references/derivations.md`); the raw metric's own `metrics_cmd`/`criterion_cmd` if it doesn't.
- **principle_id**: which principle row this claim speaks to (`P00x`) -- required by the CLI same as every field above; don't guess one when more than one principle could plausibly fit, ask the user which.
- **role**: pick from the enum at `tables/rows.json` → `enums.story.role` -- read the table rather than guessing a value, since a rejected value fails the write outright.

## Quick rows are rejected

Any run cited in `--evidence-runs` / `--baseline-runs` / `--candidate-runs` that came out of the quick lane (§2.6, `quick=true`) makes the write fail. A quick result has to be promoted to a regular run first (see the deploy-layer skill's `references/quick-lane.md` for the promotion path) before it can back a story claim. Don't work around this by omitting the run and citing a sibling run instead -- if the evidence is quick, the claim isn't ready for the story yet.

## Retiring or correcting a claim

```
python3 <plugin-root>/scripts/ledger.py story retire <SID> --reason "<user's literal words>" [--superseded-by <SID>]
```

Retiring is a user ruling like adding is -- it needs the user's own reason in their words, not a paraphrase. This is one of the withdrawal paths; the full withdrawal contract (who may write it, what fields it forces) is in `references/withdrawals.md` -- this section only covers the story-specific call shape.
