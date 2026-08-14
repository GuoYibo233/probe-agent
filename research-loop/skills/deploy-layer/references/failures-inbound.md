# Inbound failure escalations (channel 4)

`<plugin-root>` means the plugin root, three levels up from this file
(`../../..`).

This covers `status --layer deploy`'s `open_blocked` rows with `kind=failure`
-- the run layer's channel-4 escalation, raised when its own
`error_classify.py` pass came back `unknown` (see the run-layer skill's
`references/failures.md`). Classification judgment on an `unknown` result
belongs here, not at the run layer (R8) -- this is where that judgment
actually happens.

## Reading the row

```
python3 <plugin-root>/scripts/ledger.py query blocked --status open --to-layer deploy --kind failure
```

`evidence` is an array carrying, in order, the verbatim error and the log
path, plus a table of what was already tried -- read the evidence itself,
not a summary of it. Open the named log at the given path; don't rule on the
failure from `question` alone.

## The error classification table

`ops/error_classes.json` is deploy-owned (`tables/ledgers.json` → owner
`deploy`, read class `direct`) and is the table `error_classify.py` reads at
the run layer *before* anything ever reaches this queue. Its real shape
(`tables/rows.json` → `error_classes`, matching `error_classify.py`'s own
`_MATCH_KEYS`/`_rule_matches` exactly -- read the table entry there before
writing a rule, not the sketch elsewhere):

```json
{
  "rule_name": {
    "match": {"exit_code": 137, "log_regex": "CUDA out of memory", "output_check": "empty-output"},
    "action": "retry"
  }
}
```

Key order is match priority (first fully-matching rule wins); a `match`
key you leave out never counts as a free pass -- only a key the caller
actually supplied to `error_classify.py` can match. `action` is one of the
values `error_classify.py`'s docstring names (`retry` / `swap-card` /
`escalate`); a rule missing `action` is a broken table, not an `unknown`.

**If the file doesn't exist yet** (`error_classify.py` treats that as zero
rules and reports `unknown`, per #155 -- it never crashes, but it also never
self-heals anything until this file exists): create it here, this layer's
write. Start with one rule per failure kind you've actually seen and
classified by hand; a table with zero rules is a legitimate starting state,
not an error.

## Classifying and deciding

Read the evidence, decide what this failure actually is, and pick one of:

- **Self-heal now, and add a rule** so the same shape self-heals at the run
  layer next time without a round trip back here. Answer naming the action
  (retry / swap card / whatever this failure actually calls for), and add
  the corresponding rule to `error_classes.json` in the same sitting
  (`tables/rows.json` error_classes → `_note`: "unknown 的新规则提议路径见
  R8").
- **This needs a decision only idea/the user can make** (a principle gap,
  an experimental-settings ambiguity §2.5 forbids self-resolving) -- open a
  new entry the normal way (the deploy-layer skill's own
  `references/r5-choices.md` "Opening it"), `--to-layer idea` or `--to-layer
  user`, and answer *this* row once that one comes back (see "After
  answering" below) -- don't leave this row open waiting on a second one
  indefinitely; close the loop through it.

Whichever action changes about how the run relaunches (different resources,
a different launch order, a retry with altered `argv`) runs through the
mechanical three-question test first (`references/r5-choices.md`
"Identifying one") -- a construction fork triggered by a failure is still a
fork. Self-deciding it (grant or standing GPU<1h authorization) follows the
same R6 two-step trail as any other non-r5-choice self-decision:

```
python3 <plugin-root>/scripts/ledger.py decision --blocked-ref <BID> --layer deploy \
  --authorized-by grant:<D00x>|spec-standing-gpu-1h \
  --question "<what changes>" --options "<option A>" "<option B>" [...] \
  --chosen "<grep-able concrete value>" --reason "<why>" --where "<file path>"

python3 <plugin-root>/scripts/ledger.py blocked answer <BID> --layer deploy \
  --answer "<the ruling, in full>" --decision-ref <D00x>
```

A plain answer (no `--grant`/`--decision-ref`) is legal when nothing needs
citing -- R6 only governs answers that invoke authorization
(`tables/writes.json` blocked_transitions.answered →
`_non_r5_self_decision._plain_answer`). `r5-choices.md`'s "Answering
mechanically assembles a decisions-ledger entry" line is scoped to
`kind=r5-choice` only -- it does not describe this row's answer shape.

## After answering: who closes it

Answering moves this row to `status=answered`; it does not close it.
Closing is `from_layer`'s job (`tables/writes.json` blocked_transitions.closed)
-- for this row, `from_layer=run`, so the run layer consumes the answer and
closes it (the run-layer skill's `references/failures.md`), not this
session.

If answering this row required opening a *second* entry upward (the branch
above, `--to-layer idea` or `--to-layer user`) -- that one has `from_layer=
deploy`, so once it comes back answered, this layer owns its close step the
same way:

```
python3 <plugin-root>/scripts/ledger.py blocked close --layer deploy <BID>
```
