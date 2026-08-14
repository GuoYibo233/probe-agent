# Failures (R8)

`<plugin-root>` means the plugin root, three levels up from this file
(`../../..`).

## Classify first

```
python3 <plugin-root>/scripts/error_classify.py --error-classes <error_classes.json> \
  [--exit-code <code>] [--log <path>] [--output-check <output_check result>]
```

This is a table lookup, not a judgment call -- three feature kinds (exit
code, `output_check` verdict, log regex) get matched against the project's
error classification table. A hit returns a self-heal action (e.g. retry,
swap cards) or an escalation instruction; do exactly what it says, nothing
more creative.

## When it doesn't hit (`unknown`)

**This layer does not classify an `unknown` result itself** -- no
guessing at what category it might be. Instead, collect and hand up:

- the verbatim error (not a summary of it),
- the log path,
- a table of what was already tried.

Then escalate:

```
python3 <plugin-root>/scripts/ledger.py blocked open --layer run \
  --to-layer deploy --kind failure --ref <run_id> \
  --question "<what's stuck>" \
  --evidence "<verbatim error>" "<log path>" "<attempted actions>"
```

Classification judgment on an `unknown` belongs to the deploy layer (or
above) -- once it's classified there, a new rule can be added to the error
classification table so the same failure self-heals next time (record it
in that table, note it when the blocked entry gets answered).

## The rerun rule

If a rerun of the exact same command still comes back empty, that always
escalates -- don't try a second silent rerun hoping it clears up on its
own, and don't downgrade "still empty after a retry" into anything other
than an escalation.

## What this layer never does

No layer-skipping (escalate to deploy, not straight to idea or the user).
No silently swallowing an error and reporting the run as done. No fixing
someone else's layer's code to make the failure go away -- that's a deploy
job, handed up through the entry above.

## Consuming the answer

Deploy answering this entry (the deploy-layer skill's
`references/failures-inbound.md`) does not close it -- closing is
`from_layer`'s job (`tables/writes.json` blocked_transitions.closed:
`writable_by: from_layer`), and `from_layer=run` for whatever this layer
raised. Once `status --layer run`'s `answered_blocked` block lists it, read
the answer and do what it says (a self-heal action, or nothing further if
it only added a rule to `ops/error_classes.json` for next time), then close
it:

```
python3 <plugin-root>/scripts/ledger.py blocked close --layer run <BID>
```

Skipping this leaves an already-answered escalation sitting in this
layer's own queue indefinitely -- an answer nobody ever consumed.
