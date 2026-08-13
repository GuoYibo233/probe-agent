# Criterion runs

`<plugin-root>` means the plugin root, three levels up from this file
(`../../..`).

## One action does everything

```
python3 <plugin-root>/scripts/ledger.py runs-append --layer deploy --principle <P00x>
```

This one command is both the execution and the bookkeeping -- there is no
separate "run it, then record it" pair of steps. The script reads
`criterion_cmd` off the named principle's row in the principles doc, splits
it (`shlex.split`, no shell), starts the process directly, times it, and
parses the last line of its stdout as structured JSON. This session never
sees a number pass through it and never types one in (R7).

## Criteria are lightweight, read-only, on-the-spot

A criterion must never touch a GPU or go through `rails.gpu` -- it has to
be something this session can run right here, right now. If the evidence a
principle needs actually requires heavy compute, that compute runs first as
a normal launch order, and `criterion_cmd` only checks the paths that run's
artifacts landed at -- the criterion itself stays cheap. A principle whose
criterion can't be made lightweight this way goes back to the idea layer to
be renegotiated, not force-fit into a heavy `criterion_cmd`.

## Only a clean run lands a row

A row lands (`status=ok`) only when the exit code is 0 **and** the last
stdout line parses as the structured output contract expects
(`tables/rows.json` → `structured_output_contract`). Anything else -- a
nonzero exit, or a last line that doesn't parse -- writes nothing to
runs.jsonl. That's not a bug to route around: it means the criterion didn't
actually run, so escalate it per R8 (same classification/escalation shape
as the run-layer skill's `references/failures.md`) rather than treating a
failed attempt as a measurement. The principles doc's "latest measurement" column
only ever reflects a landed `ok` row -- a failed attempt never back-fills
it.
