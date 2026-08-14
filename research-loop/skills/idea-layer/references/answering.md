# Answering a pending entry addressed to idea

`<plugin-root>` means the plugin root, three levels up from this file
(`../../..`).

The entries this covers are the ones `status --layer idea`'s `open_blocked`
block lists: `blocked` rows with `to_layer=idea`. Only `deploy` may open one
here (`tables/writes.json` blocked_transitions.open `legal_to`: `deploy`'s
legal targets are `idea` and `user`, `oversight`'s are `user` and `deploy`
only -- `oversight` can never open a row targeting `idea`) -- typically a
principle gap deploy hit while turning a principle into a spec item, a fork
that needs a ruling only this layer's user conversation can give, or a
failure escalation deploy couldn't resolve within its own write rights and
pushed one step further up the ladder (R8's "运行→部署→idea→你").

## Reading the row

```
python3 <plugin-root>/scripts/ledger.py query blocked --status open --to-layer idea
```

This is the query-only read path (§2.1) -- never `cat`/read `ops/blocked.jsonl`
directly. The row's `kind` field decides which of the three answering shapes
below applies; `where`/`options` are only populated for `kind=r5-choice`.

## Which shape the answer takes

**`kind=r5-choice`** -- a construction fork was routed here for a ruling.
Answering mechanically assembles a decisions-ledger entry from
`where`/`options`/`chosen`/`answer` (`tables/writes.json` →
`r5_choice_assembly`) -- never leave the ruling as free text in `--answer`
alone:

```
python3 <plugin-root>/scripts/ledger.py blocked answer <BID> --layer idea \
  --answer "<the ruling, in full>" --chosen "<grep-able concrete value>" \
  [--answered-by user] [--grant <D00x>]
```

Pass `--answered-by user` when the user is the one ruling on it (the common
case here, since idea is the layer talking to them) -- `authorized_by` then
becomes the user's own words, `decided_by=user`. Self-deciding this fork
under an active grant instead (no `--answered-by user`) requires `--grant
<D00x>` pointing at that grant's `decision_id`; omitting both is rejected.
Full mechanics, including which grant counts active: the deploy-layer
skill's `references/r5-choices.md` -- read it there if a case doesn't fit
what's above, this section only restates what idea-layer answering needs.

**`kind≠r5-choice`, answered under an active grant or standing GPU<1h
authorization** -- R6's two-step trail (`tables/writes.json`
blocked_transitions.answered → `_non_r5_self_decision`), not a direct
`--grant` on the answer (that path is r5-choice-only):

```
python3 <plugin-root>/scripts/ledger.py decision --blocked-ref <BID> --layer idea \
  --authorized-by grant:<D00x> \
  --question "<the decision point>" --options "<option A>" "<option B>" [...] \
  --chosen "<grep-able concrete value>" --reason "<why>" \
  --where "<file path | spec item | ticket>"
```

For standing authorization, `--authorized-by spec-standing-gpu-1h` instead
of `grant:<D00x>`. Then cite it in the answer:

```
python3 <plugin-root>/scripts/ledger.py blocked answer <BID> --layer idea \
  --answer "<the ruling, in full>" --decision-ref <D00x>
```

`--decision-ref` is checked against the row it names (exists, `kind=decision`,
its own `blocked_ref` points back at this `<BID>`, `decided_by=agent`,
`authorized_by` still an active grant or the standing-authorization literal)
before it's accepted.

**`kind≠r5-choice`, transcribing what the user said** -- the far more common
case at this layer for a principle-gap or a further-escalated failure: the
user rules on it in conversation, this session transcribes it, no
authorization reference is involved because it isn't a self-decision at all:

```
python3 <plugin-root>/scripts/ledger.py blocked answer <BID> --layer idea \
  --answer "<the user's ruling, in full>" --answered-by user
```

A plain answer with neither `--grant` nor `--decision-ref` is also legal
when nothing needs citing -- R6 only governs answers that invoke
authorization, not every answer (`tables/writes.json` →
`_non_r5_self_decision._plain_answer`).

## After answering: who closes it

Answering only moves the row to `status=answered` -- it does **not** close
it. Closing is `from_layer`'s job (`tables/writes.json`
blocked_transitions.closed: `writable_by: from_layer`): for a row this
layer received (`to_layer=idea`), `from_layer` is always `deploy` -- the
only layer whose `legal_to` includes `idea` (see above) -- so deploy
consumes the answer and runs `ledger.py blocked close --layer deploy <BID>`
in its own session. This layer's involvement with a row it merely answered
ends here.

The mirror case is entries **this layer raised** (`to_layer=user`, since
`idea`'s only legal escalation target is `user` --
`tables/writes.json` blocked_transitions.open `legal_to`). Once the user
rules on one of those and this session transcribes it the same way (`blocked
answer ... --answered-by user` above), this layer *is* `from_layer` and owns
the close step:

```
python3 <plugin-root>/scripts/ledger.py blocked close --layer idea <BID>
```

Skipping this leaves the row sitting in `status --layer idea`'s
`answered_blocked` block indefinitely -- an entry this layer itself raised,
already answered, that nobody ever consumed.
