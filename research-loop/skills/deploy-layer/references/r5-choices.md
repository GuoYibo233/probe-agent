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
  --to-layer <user|idea|deploy> --kind r5-choice --ref <spec item / ticket / run_id> \
  --question "<the decision point>" --evidence <log path / prior attempt> [<more...>] \
  --where "<file path | spec item | ticket>" --options "<option A>" "<option B>" [...]
```

`--to-layer` is whichever layer can rule on this -- usually `user`, sometimes `idea`; a self-decision under a grant goes `--to-layer idea` or `--to-layer deploy` instead, never `user` (see "Which mode applies").

## Which mode applies

Check the active-grants view from this session's opening `status` call before opening a blocked entry -- don't open one reflexively:

- **Default (no override)**: stop here, open the entry above, wait.
- **Self-decide under a grant**: an active grant's scope covers this fork and hasn't expired -- decide on the spot. If a blocked entry is already open for this fork, answer it below with `--grant` pointing at that grant. If nothing was opened yet (the fork was spotted and resolved in the same breath), skip `blocked` entirely and record the ruling directly with `ledger.py decision` (below).
- **Standing authorization (GPU<1h)**: the fork is only about launching compute, total `expected_runtime_s` under `standing_authorization.max_expected_runtime_s` (default 3600s) -- proceed directly, no `blocked` entry, no grant lookup (§2.6 is the fast lane, not a `blocked answer` variant). R6 still applies: record the ruling with `ledger.py decision` (below), `--authorized-by spec-standing-gpu-1h`.

Either self-decide mode opens its `blocked` entry (if one gets opened at all) `--to-layer idea` or `--to-layer deploy`, never `--to-layer user` -- a `--to-layer user` entry is a transcript of the user's own words, and `blocked answer` rejects `--grant` on one outright (R6's machine-check anchor: see "Recording the ruling" below).

## Recording the ruling

Two mechanisms, depending on whether a `blocked` entry is already open for this fork.

**A blocked entry is open** -- the default path, or a grant self-decide answering a row someone already raised:

```
python3 <plugin-root>/scripts/ledger.py blocked answer <BID> --layer deploy \
  --answer "<the ruling, in full>" --chosen "<grep-able concrete value>" \
  [--answered-by user] [--grant <D00x>]
```

Answering mechanically assembles a decisions-ledger entry from where/options/chosen/answer -- never leave the ruling as free text in `--answer` alone (`tables/writes.json` → `r5_choice_assembly`). Self-deciding requires `--grant <D00x>` pointing at an *active* grant row's `decision_id` -- omitting it when the answering session isn't the user is rejected outright. `--grant` only ever names a live grant row: `spec-standing-gpu-1h` is not a grant and is rejected here (standing authorization never goes through `blocked answer` -- see the bullet above). And `--grant` itself is rejected outright on a `--to-layer user` entry, regardless of whether it names a real grant -- that entry is where the user's own words get transcribed (`--answered-by user`, no `--grant`), not where a self-decision gets recorded.

**No blocked entry was opened** -- grant self-decide or standing authorization, resolved in the same breath the fork was spotted:

```
python3 <plugin-root>/scripts/ledger.py decision --layer <idea|deploy|run> \
  --question "<the decision point>" --options "<option A>" "<option B>" [...] \
  --chosen "<grep-able concrete value>" --reason "<why>" \
  --where "<file path | spec item | ticket>" \
  --authorized-by "grant:<D00x>" \
  [--principle-ref <P00x>] [--affects <run_id / spec item> ...]
```

For standing authorization, pass `--authorized-by spec-standing-gpu-1h` instead of a `grant:<D00x>` value. `--decided-by` defaults to `agent` (correct for both self-decide paths); pass `--decided-by user` only from `--layer deploy` (spec approval transcription, not a self-decision at all).

## After

Every self-decided item goes on the next report back to the user (§2.5's self-decision report clause), listed by name, not folded silently into "everything ran fine."
