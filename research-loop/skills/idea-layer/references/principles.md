# Principles (R1)

`<plugin-root>` means the plugin root, three levels up from this file
(`../../..`).

Every principle is one row in the principles doc (md table). The row's full
column contract -- names, order, enum domains -- is `tables/rows.json` →
`principles_columns`; this file only explains the columns that carry a
behavioral rule, not the full column list.

## Writing a row

- **rationale must never be blank.** When the user states a principle
  without giving a reason, ask for one on the spot -- "why this, why now" --
  before recording the row. Don't write a row with an empty rationale and
  plan to fill it in later; `principles-lint` rejects it, and more to the
  point, a principle nobody can explain isn't ready to be one.
- **applies_when must never be blank** either, for the same reason
  (`principles-lint` checks both).
- **criterion_cmd is the exception**: it may be left empty only when the
  status column is the "idea-pending" tag (`tables/rows.json` enums →
  `principles.status`) -- meaning: this principle exists but nothing checks
  it yet, because the registry command it needs isn't wired up. Every other
  status value requires a non-empty `criterion_cmd` that resolves to a
  registry command; `principles-lint` enforces this too.
- Once a criterion is wired, the row moves out of the idea-pending tag into
  whichever of the other status values fits (current state vs. decided
  change) -- that transition only happens when `criterion_cmd` actually
  lands, not before.
- **Latest measurement is never hand-filled.** It's a rendering artifact --
  every time the criterion runs (`ledger.py runs-append`), that run enters
  runs.jsonl carrying this principle's id, and the render step reads it back
  in. Don't type a date or a value into that column yourself.

## Approval is a row-by-row event

There is no file-level "principles doc approved" state. Each row's status
moves when the user rules on *that row*, on the spot, in conversation --
approving one principle says nothing about any other row's status. Don't
batch approvals into one sitting and record them as if the user ruled on the
whole document at once.

## Commands

```
python3 <plugin-root>/scripts/ledger.py principles-lint [--file FILE]
python3 <plugin-root>/scripts/ledger.py render principles
```

`principles-lint` is the mechanical check (rationale/applies_when non-empty,
`principle_id` uniqueness, criterion wiring per status) -- run it after any
edit to the principles doc, before treating the edit as final.
`render principles` regenerates the doc's "latest measurement" column from
runs.jsonl; never hand-edit that column instead.
