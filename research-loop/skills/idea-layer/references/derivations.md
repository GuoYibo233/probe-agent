# Derived computations (R4)

Data is presented as raw values by default. Anything derived from it --
means, ratios, deltas, anything computed rather than read -- needs the
user's approval before it's computed, not after.

## Proposal format

Bring the user exactly four things, before running anything:

1. **Formula** -- what's being computed, in plain terms.
2. **Denominator** -- what it's computed over (which n, which population).
3. **Filter conditions** -- which rows are included or excluded.
4. **Files acted on** -- which run outputs or ledger rows feed it.

Present this as a proposal, not a fait accompli (§2.5 upward genre
"proposal"): the user rules on the four items before the computation runs,
the same way any R5 decision point does.

## Approved terms are standing authorization

Once the user approves a formula/denominator/filter/aggregation-level
combination and it's written into an approved spec item, every future batch
that matches those same terms computes and reports it without going back to
the table. This is the one case where "already ruled on" persists across
batches -- everywhere else in R5/R6, authorization is scoped and can expire.

A combination only counts as pre-authorized when all four terms were
actually written into the approved spec item; a rule that's only partially
specified (e.g. formula given but filter left implicit) is not
pre-authorized -- it still needs a proposal.

## Any change is a new proposal

Adding or changing the formula, the denominator, the filter, the
aggregation level, or how missing values are handled is always a fresh
proposal, even if it looks like a small tweak to something already
approved. The §2.5 experimental-settings hard boundary applies here
unchanged: don't resolve an ambiguity in any of these four terms yourself
without the user's word or an active grant that covers it.

## Bookkeeping

Once computed, the command that produced it travels with the result:
attach it beside the number when reporting, and when the result enters the
story ledger, it goes into that claim's `derivation_command` field (see
`references/story.md`) -- so anyone can re-run the exact computation later,
not just re-read the number.
