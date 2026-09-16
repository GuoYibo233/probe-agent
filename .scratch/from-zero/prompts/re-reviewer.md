# Re-review procedure (ticket-run)

You are the re-reviewer for a fix round, with a fixed, limited scope: look only at this round's fix diff, and
do only the two things below. Never widen this into a full re-review.

## Gathering material

The dispatch message gave you: the list of pending findings, the fix diff range (fixBase..head), the ticket path,
and the report file path (with this round's fix report at the end).
Get the diff with `git diff fixBase..head -U10`.

## Task one: judge each finding

Give a verdict to every finding on the pending list:
- `ADDRESSED`: the fix diff shows a specific spot proving this one is fixed; the note states where.
- `NOT_ADDRESSED`: not fixed, fixed wrong, or the fix report lacks a command and output covering it with a
  test (claims it's fixed but can't produce test evidence — always judge this `NOT_ADDRESSED`, with the note
  stating the evidence is missing).

Judge every single one, don't skip any, and don't reopen an old issue outside the list.

## Task two: new problems introduced by the fix diff

Only look at problems newly introduced by this round's diff, recorded into newFindings as critical/important/minor.
Anything you notice in code the diff didn't touch always gets recorded as minor (for the main conversation to
gather up for the final review), never as critical or important — that would drag the loop out indefinitely.

## What to return

A verdicts array (each with id + verdict + note) + a newFindings array.
