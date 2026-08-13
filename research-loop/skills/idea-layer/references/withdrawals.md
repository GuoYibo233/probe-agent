# Withdrawals and corrections (§2.5)

`<plugin-root>` means the plugin root, three levels up from this file
(`../../..`).

Any ruling the user already made can be taken back. The mechanism is fixed
by row/genre -- **jsonl ledgers go through three ledger.py commands, md
files go through two direct edits by whichever layer owns that file**. Full
field-level rules, single source: `tables/writes.json` →
`withdrawal_proxy` and `withdrawal_routes_md`; this page only walks the five
paths and the invariant that holds across all of them.

## The invariant

Withdrawal is a user-downward action. The session that transcribes it does
**not** have to be the ledger's owning layer -- any session the user is
talking to right now may write it as proxy, without a `--layer` argument.
But every proxy write is forced to carry the user's literal words as the
reason; there is no withdrawal without a quote from the user. Don't
transcribe "the user wants to walk this back" from your own summary --
capture what they actually said.

## jsonl paths (three commands)

```
python3 <plugin-root>/scripts/ledger.py decision-withdraw <DID> --reason "<user's literal words>" [--superseded-by <D00x>]
python3 <plugin-root>/scripts/ledger.py story retire <SID> --reason "<user's literal words>" [--superseded-by <S00x>]
python3 <plugin-root>/scripts/ledger.py blocked withdraw <BID> --reason "<user's literal words>"
```

A pure withdrawal leaves `superseded_by` empty. A **correction** (the user
is replacing the ruling with a new one, not just retracting it) passes
`--superseded-by` naming the new row; the script validates that row exists
before backfilling the reference -- it never accepts an unverified pointer.

Withdrawing an **answered** blocked entry does more than flip its status:
the same command mechanically reopens a fresh entry addressed back to that
entry's original `to_layer`, carrying the same question forward -- a
withdrawn answer doesn't make the underlying problem disappear. If a
decision entry had already been assembled from that answer (R5 choices,
see the deploy-layer skill's `references/r5-choices.md`), it's set to
withdrawn in the same action.

## md paths (two direct file edits)

These are not `ledger.py` calls -- the owning layer's session edits the
file directly:

- **Principles doc**: tag the row 【已撤销】 and append the user's literal
  words, with the date, into that row's rationale column (idea layer edits
  this).
- **Spec file**: clear `approved_by` / `approved_date` / `approved_digest`
  back to unapproved, bump `spec_version`, and append one entry to the
  header's `withdrawals[]` (deploy layer edits this -- see the deploy-layer
  skill's `references/spec-items.md`).

Both md-path edits are recorded with the same discipline as the jsonl
commands: the user's own words, not a paraphrase, land in the file.
