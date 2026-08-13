# Spec items

`<plugin-root>` means the plugin root, three levels up from this file
(`../../..`).

## File header contract

Every spec file opens with a `---`-delimited frontmatter block; its field
set is `tables/rows.json` → `spec_header` (five fields, including
`approved_by`/`approved_date`/`approved_digest` and a `withdrawals[]` log --
see that table entry for the exact set, not restated here). Approval state
lives on disk in this header, not in session memory: a new session reading
a spec file must treat a draft as a draft until the header says otherwise.

`approved_digest` is a hash of the file's body -- everything after the
second `---` line, not the header itself. Any edit to the body after
approval makes a recomputed digest disagree with the stored one; that
disagreement is `approval_stale`, and it blocks launch-order writes against
this spec until re-approved. Purely appending to `withdrawals[]` or bumping
`spec_version` in the header does not trigger staleness on its own.

## Each item

An item's field contract is `tables/rows.json` → `spec_header` → `item`
(read it there, not copied here). Every item's `principle_id` must resolve
to a real row in the principles doc -- write the spec against principles
that already exist, don't invent a principle to match a spec item you
already want to write.

## Getting to approved

1. Write or edit the spec.
2. Run:
   ```
   python3 <plugin-root>/scripts/trace_check.py [--project-root <root>]
   ```
   until it's clean -- forward chain (ticket → spec → principle) and
   backward chain (run → launch order → ticket) both have to hold before
   this spec goes in front of the user.
3. Bring it to the user for a ruling (§2.5 "拍板" -- not a fait accompli).
4. On approval, the transcription is mechanical, run it on the spot:
   ```
   python3 <plugin-root>/scripts/ledger.py approve-spec --by <user> <spec_file>
   ```
   This is the only path that writes `approved_by` / `approved_date` /
   `approved_digest` -- don't hand-fill any of the three, the digest in
   particular has to come from the script's own recomputation.

## Not approved

A "no" here is not the batch-acceptance send-back genre (§6 routing entry
"这个不行，重做"). Nothing is written to `approved_by` -- the draft simply
stays a draft -- and the open question goes into the pending ledger so it
doesn't get lost, addressed to whichever layer can actually resolve it.
Don't treat silence or a lukewarm response as approval and move on with the
spec anyway.
