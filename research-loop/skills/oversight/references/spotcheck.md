# Spot-checks

`<plugin-root>` means the plugin root, three levels up from this file
(`../../..`).

A spot-check answers "let me see some of this myself" without asking the
user to read an entire batch. It's one of the six upward genres (§2.5) and
one of oversight's routing entries ("查 X" also lands here).

## Running one

```
python3 <plugin-root>/scripts/spotcheck.py <material>
```

Sampling is fixed-seed -- rerunning the same command against the same
material picks the same sample, so a spot-check is itself reproducible,
not a fresh roll each time it's requested.

## What gets delivered

Two things, together, every time:

- **A direct-path list**: the sampled items, each as an openable
  `path:line` reference the user can jump straight to -- not a summary of
  what they contain, the actual locations.
- **A population fingerprint**: something that lets the user (or a later
  spot-check) verify the sample was actually drawn from the full
  population claimed, not a cherry-picked subset.

Deliver both in the R3 report genre (`references/report-genre.md`) -- the
direct-path list is itself the evidence, so it needs no separate repro
command; the population fingerprint is metadata and gets the provenance
treatment, not a `$ ` line of its own.

## What it's for, and isn't

A spot-check lets the user personally verify a slice of raw material --
it's not a substitute for the full read-through a routine inspection does
(`references/inspection.md`), and it carries no verdict of its own beyond
"here's what's actually there." If the user wants to check a batch's
correctness rather than look at some of it themselves, that's an
inspection, not a spot-check.
