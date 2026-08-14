# Batch close-out (§1, three-step loop)

`<plugin-root>` means the plugin root, three levels up from this file
(`../../..`).

A batch is not closed by this session deciding the numbers look fine -- close-out runs through an independent inspection every time (config `inspection_policy=always`). **Quick-lane batches (§2.6) skip this entire flow.**

## Step 0: write the batch report

Once this batch's runs have landed (§8 step 5's sequence -- smoke, criterion
run, R3 evidence, `evidence_lint`/`verify_report` clean, the user's own
look, then the real launch), write the report itself: an md file under
`plans/`, named after the batch (`tables/rows.json` →
`batch_report_header.batch_id_pattern`: `<spec条目>-<YYYYMMDD>-<序号>`).
Its full field set -- including the two easiest to drop when copying a
sibling report as a template -- is `tables/rows.json` →
`batch_report_header`: `batch_id`, `spec_items[]`, `run_ids[]`, `date`,
`how_to_read` (the read-script +口径 explanation this layer owes the idea
layer -- §1's "how to read" deliverable, channel 2), `inspection_report`
(leave it an empty string here -- that's what marks the batch
`batches_pending_inspection` until step 3 below back-fills it),
`rejections[]` (leave empty unless this batch is itself a rewrite after a
send-back). This step's output is what Step 1 dispatches on -- the report
must exist and carry a real `run_ids[]` before there's anything to inspect.

## Step 1: drop the report, dispatch the inspector

Once the batch report lands (md, in `plans/`), dispatch the `inspector` agent. Model comes from `research-loop.json` → `roles.inspector_model` (plugin default: opus) -- name it explicitly in the dispatch, never let it default. The dispatch contract must carry the `batch_id`, the batch report's path, the project's `research-loop.json` path, and the three mechanical-check commands the inspector must run:

```
python3 <plugin-root>/scripts/trace_check.py --project-root <root>
python3 <plugin-root>/scripts/evidence_lint.py <inspection material>
python3 <plugin-root>/scripts/verify_report.py <inspection material>
```

The inspection's scope is whatever the batch report's own header points at (`run_ids`/`spec_items`) -- the batch report is itself the on-disk message, so this dispatch still satisfies "the message lives in the ledger, not in session memory."

## Step 2: the inspector reads through, verdicts

The inspector runs the three-script suite and reads through this batch's ledgers and report in full -- not a sample. Its report lands in `reports/` with a header carrying a `verdict` field (`tables/rows.json` → `inspection_report_header`). A blocker only ever names a process or evidence defect -- a broken chain, a missing repro command, a mismatched basis -- never a scientific conclusion (R2); science stays this layer's and the user's call.

## Step 3: read the verdict back

- **Any blocker**: transcribe each one into a blocked entry -- `from_layer=deploy`, evidence pointing at the inspection report, `to_layer` set to the nearest layer that can actually answer it. This batch is **not** closed yet.
  ```
  python3 <plugin-root>/scripts/ledger.py blocked open --layer deploy \
    --to-layer <idea|user> --kind <tables/rows.json enums.blocked.kind> \
    --ref <batch_id> --question "<the blocker, verbatim>" --evidence <inspection report path>
  ```
  Transcribing a blocker does **not** count as this session grading its own work -- the judgment already happened in the inspector's independent context; this step only moves it into the queue.
- **No blocker**: this is what closes the batch. Back-fill the inspection report's path into the batch report header's `inspection_report` field, then run the closing gate:
  ```
  python3 <plugin-root>/scripts/trace_check.py --closeout <batch_id>
  ```
  A non-empty `inspection_report` is exactly what this gate requires -- don't call the batch closed without it passing.
