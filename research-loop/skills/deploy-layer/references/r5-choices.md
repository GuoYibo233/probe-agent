# R5 decision points

`<plugin-root>` means the plugin root, three levels up from this file
(`../../..`).

## Identifying one

When construction hits a fork, run the mechanical three-question test before picking either branch: (1) would either branch change what some criterion's output is? (2) would either branch introduce a new constraint with no corresponding principles-doc item? (3) is it irreversible -- large compute/time spent, or an artifact already consumed downstream? (Writing to the raw-data disk by itself does **not** count as irreversible.)

Three no's is construction freedom -- just build it, no entry needed. Any yes puts it on the table. **A ledger schema change is always a yes on question two**, unconditionally.

**Experimental settings are always in scope here.** An ambiguity about a run's model, temperature, sampling, dataset version, or anything else in that family is never resolved on this session's own judgment -- not without the user's explicit word or an active grant that covers it (§2.5's hard boundary). This isn't a separate rule from R5: it's confirmation that these ambiguities *are* R5 decision points, not construction freedom, and get the same open/self-decide/standing-authorization treatment below.

## Opening it

```
python3 <plugin-root>/scripts/ledger.py blocked open --layer deploy \
  --to-layer <user|idea> --kind r5-choice --ref <spec item / ticket / run_id> \
  --question "<the decision point>" --evidence <log path / prior attempt> [<more...>] \
  --where "<file path | spec item | ticket>" --options "<option A>" "<option B>" [...]
```

`--to-layer` is whichever layer can rule on this -- usually `user`, sometimes `idea`.

## Which mode applies

Check the active-grants view from this session's opening `status` call before opening a blocked entry -- don't open one reflexively:

- **Default (no override)**: stop here, open the entry above, wait.
- **Self-decide under a grant**: an active grant's scope covers this fork and hasn't expired -- decide on the spot, then answer/trace it below with `--grant` pointing at that grant.
- **Standing authorization (GPU<1h)**: the fork is only about launching compute, total `expected_runtime_s` under `standing_authorization.max_expected_runtime_s` (default 3600s) -- proceed directly with no grant in force.

## Recording the ruling

```
python3 <plugin-root>/scripts/ledger.py blocked answer <BID> --layer deploy \
  --answer "<the ruling, in full>" --chosen "<grep-able concrete value>" \
  [--answered-by user] [--grant <D00x>]
```

Answering mechanically assembles a decisions-ledger entry from where/options/chosen/answer -- never leave the ruling as free text in `--answer` alone (`tables/writes.json` → `r5_choice_assembly`). Self-deciding requires `--grant <D00x>` (standing authorization: literal token `spec-standing-gpu-1h`) -- omitting it when the answering session isn't the user is rejected outright: R6's machine-check anchor.

## After

Every self-decided item goes on the next report back to the user (§2.5's self-decision report clause), listed by name, not folded silently into "everything ran fine."
