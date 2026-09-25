# T09 — owner ruling round 1 (RULING-9): a call the builder cannot rebuild is skipped and reported

Base: `d1a4e60ffb50436bd4a8d7e8a3df5b194e71fe54` (branch `from-zero`)
Branch: `ticket/2026-09-18-wave4/T09-builder-ruling`
Head: `dfba7dc`
Worktree: `/home/y-guo/reproduce/new1-wt/2026-09-18-wave4-T09-builder-ruling1` (removed after the commit, per protocol)

## What was done

RULING-9 (`.scratch/from-zero/issues/09-dataset-builder.md`'s Comments, and the ruling text
in this dispatch): today's event walk in `data/build_training_dataset.py` calls
`env.build_call(tool, call_args)` and then the round-trip gate of contracts 2.5, and both could
raise `ValueError` and stop the whole build. The ruling makes both cases take the same skip path
the pre-existing `env.split_args(action) is None` case already takes:

- `data/build_training_dataset.py`, the per-event loop after `tool, call_args, _span = parsed`:
  - `env.build_call(tool, call_args)` is now called inside a `try/except ValueError`.
  - The round-trip check (`env.split_args(call)` against `tool`/`call_args`) is evaluated only
    when `build_call` did not raise.
  - The affirmative condition is `call_rebuilds_and_round_trips` (build succeeded **and** the
    round trip matches); everything else — a `build_call` `ValueError`, or a mismatched round
    trip — takes the skip path: `skip_no_call` is incremented (the same counter the
    `split_args is None` case uses, `counts.events_skipped_no_call`), the event is recorded in
    a new `refused_calls` list (record id, step, reason — the `ValueError` message for a
    `build_call` refusal, or the re-parsed value for a round-trip mismatch), `(action,
    env_row["result"])` is appended to `history` exactly as every other skip does, and the walk
    continues to the next step.
  - No new count name: `counts.events_skipped_no_call` now covers three input kinds (a
    non-parsing action, a `build_call` refusal, a round-trip mismatch), matching the
    integrator's precedent for the `split_args is None` case in `contract-errata.md`.
  - `report.md` gained one new line, `- calls build_call refused or that failed the round-trip
    gate: <n>`, followed by one indented line per refused event naming its record id, step and
    reason.
- `data/environments/appworld.py` is unchanged: `build_call` still raises and still names the
  tool, key and value; the ruling explicitly keeps that.
- No file was added, moved, renamed or deleted. `README.md`'s ticket-09 entry needed no edit:
  its `writes:` and `imports:` lines are unchanged by this fix.

## How it was verified

All commands ran from the worktree above, with fixtures built by a copy of the ticket's fixture
script (`.scratch/from-zero/issues/09-dataset-builder.md`'s `mkbuildfix.sh`), written into a
`mktemp -d` scratch directory rather than directly under `/tmp`, and run through
`/home/y-guo/reproduce/new1/external/appworld/venv/bin/python` ($AW below). Every fixture
directory used in this round (14 in total, including the ones used for the ticket's F2–F7 reruns
below) was deleted at the end.

### A1 — imports under all three venvs (unaffected by this change, rerun for completeness)

```
imports ok 3.11.15
imports ok 3.12.13
imports ok 3.12.13
```

### A3 — one column-zero `VERSION`

```
$ grep -c '^VERSION = [0-9][0-9]*$' data/build_training_dataset.py
1
```

### F1 — the command shape

```
$ "$AW" -m data.build_training_dataset --help 2>&1 | head -5
usage: build_training_dataset.py [-h] --run-dir RUN_DIR

Build the probe training dataset from a sample run's task records.

options:
$ "$AW" -m data.build_training_dataset --run-dir /nonexistent; echo "exit=$?"
build: --run-dir /nonexistent does not exist
exit=1
```

### New fixture for RULING-9: three events (normal / build_call-refused / no-call)

The fixture's `build_call_refused` variant writes six records (the standard two tasks x three
splits x one seed the base fixture uses), each with exactly three events:

1. a normal call (`print(apis.supervisor.show_profile())`), long enough thinking — produces an
   example row.
2. a call `env.split_args` returns `None` for (`print(len('inspecting the namespace'))`, no api
   call) — the pre-existing no-call skip.
3. a call whose one argument value ends in a single backslash and needs quoting:
   `print(apis.supervisor.show_profile(note="a,b\""))`. Verified directly against
   `data/environments/appworld.py` before building the fixture:
   `_first_call_named` parses it to `('supervisor', 'show_profile', [('note', 'a,b\\')], ...)`
   (the comma forces `_quote_value` to quote it, since `_stays_one_argument` refuses a bare
   top-level comma), and `AppWorld.build_call('apis.supervisor.show_profile', [('note',
   'a,b\\')])` raises `ValueError: appworld.build_call: apis.supervisor.show_profile argument
   'note' value 'a,b\\' needs quoting and ends in a backslash that escapes its closing ', so the
   call it would be written into never closes` — this is RULING-9's named scenario.

```
$ (cd "$FIX" && "$AW" -m data.build_training_dataset --run-dir "$BDIR"); echo "exit=$?"
... (heartbeat lines) ...
exit=0
$ "$AW" -c "... print(counts) ..."
counts: {'records': 6, 'events': 18, 'events_skipped_no_action': 0, 'events_skipped_no_call': 12,
'events_skipped_short_think': 0, 'examples': 6, 'examples_train': 2, 'examples_val': 2,
'examples_test': 2, 'tools': 1, 'tools_unseen_in_train': 0}
example rows: 6
event ids: ['3d9a636_1__s42|s0', '3d9a636_2__s42|s0', '50e1ac9_1__s42|s0', '50e1ac9_2__s42|s0',
'82e2fac_1__s42|s0', '82e2fac_2__s42|s0']
```

`events_skipped_no_call` is 12 = 2 skip-worthy events (the no-call one and the build_call-refused
one) x 6 records, matching the shape the ticket's own F4 already uses (its three skip counters
each come out to 6 = 1 x 6 records). Examples are written only for the `|s0` (normal) event of
each record — 6 rows total, one per record, none from `|s1` or `|s2`.

`report.md`:

```
# build report

- key=b011db011db0 env=appworld agent_model=gpt_oss_120b commit=deadbeef debug=True
- records=6 events=18 events_skipped_no_action=0 events_skipped_no_call=12 events_skipped_short_think=0 examples=6
- calls build_call refused or that failed the round-trip gate: 6
  - record=82e2fac_1__s42 step=2: appworld.build_call: apis.supervisor.show_profile argument 'note' value 'a,b\\' needs quoting and ends in a backslash that escapes its closing ', so the call it would be written into never closes
  - record=82e2fac_2__s42 step=2: appworld.build_call: apis.supervisor.show_profile argument 'note' value 'a,b\\' needs quoting and ends in a backslash that escapes its closing ', so the call it would be written into never closes
  - record=50e1ac9_1__s42 step=2: appworld.build_call: apis.supervisor.show_profile argument 'note' value 'a,b\\' needs quoting and ends in a backslash that escapes its closing ', so the call it would be written into never closes
  - record=50e1ac9_2__s42 step=2: appworld.build_call: apis.supervisor.show_profile argument 'note' value 'a,b\\' needs quoting and ends in a backslash that escapes its closing ', so the call it would be written into never closes
  - record=3d9a636_1__s42 step=2: appworld.build_call: apis.supervisor.show_profile argument 'note' value 'a,b\\' needs quoting and ends in a backslash that escapes its closing ', so the call it would be written into never closes
  - record=3d9a636_2__s42 step=2: appworld.build_call: apis.supervisor.show_profile argument 'note' value 'a,b\\' needs quoting and ends in a backslash that escapes its closing ', so the call it would be written into never closes
- cuts per event: min=1 median=1.0 max=1 (cap 64)
- per split:
- train: 2 tasks, 2 events, 2 examples
- val: 2 tasks, 2 events, 2 examples
- test: 2 tasks, 2 events, 2 examples
- tool vocabulary: 1 classes; top5 [('apis.supervisor.show_profile', 6)]
- long tail (appears fewer than 5 times): 0 classes
- tools in val or test and never in train: []
- examples per depth decile: [0, 0, 0, 0, 0, 0, 0, 0, 0, 6]
- text length p50=126 p90=126 max=126
- abort share 0.0000 against build.max_abort_frac=0.5
- per-split build.max_examples cap dropped 0 rows
```

Every refused event names its record, its step and the exact `ValueError` message (the
build-side reason, since this fixture exercises the `build_call`-refusal branch specifically;
the round-trip-mismatch branch is exercised below by the `bad_call` variant).

### F2 — the end-to-end build (`ok` variant, unaffected by this change)

```
exit=0
consumed.json  done.json  examples.parquet  heartbeat  report.md  settings.yaml
12 ['test', 'train', 'val'] ['example_id', 'event_id', 'record_id', 'task_id', 'seed', 'step',
'cut', 'cut_index', 'n_cuts', 'depth', 'text', 'tool', 'call', 'args', 'weight', 'split', 'env',
'agent_model', 'version']
```

### F3 — the other six gates, rerun

```
=== missing_record ===
exit=1
ValueError: build: 1 requested (task_id, seed) pair(s) have no done record ... [('82e2fac_1', 42)]
=== abort ===
exit=1
ValueError: build: 1/6 records aborted (share 0.1667) exceeds build.max_abort_frac=0.0
=== orphan_gen ===
exit=1
ValueError: build: record 82e2fac_1__s42 step 9: a gen row has no matching env row
=== two_splits ===
exit=1
ValueError: build: task id(s) ['50e1ac9_1'] appear in both splits 'dev' and 'train'
=== unknown_task ===
exit=1
ValueError: build: 1 requested (task_id, seed) pair(s) have no done record ... [('82e2fac_3', 42)]
(script defect predicted by the ticket's own Comments: unknown_task trips the completeness gate
before the split gate it is meant to exercise; unchanged by this fix)
=== bad_call ===
exit=0   <-- changed by this ruling, see "self-review" below
=== bad_text ===
exit=1
ValueError: build: example 82e2fac_1__s42|s0|c0: text does not end with the thinking prefix at cut 73
```

`bad_call`'s own `report.md` and counts, for the record:

```
counts: {'records': 6, 'events': 30, 'events_skipped_no_action': 6, 'events_skipped_no_call': 12,
'events_skipped_short_think': 6, 'examples': 6, ...}
- calls build_call refused or that failed the round-trip gate: 6
  - record=82e2fac_1__s42 step=4: call 'apis.phone.search_contacts()' does not round-trip
    through split_args/build_call (built from tool='apis.phone.search_contacts'
    args=[('query', 'alice')], re-parsed to ('apis.phone.search_contacts', [], (0, 28)))
  ... (one line per record)
```

### F4 — the three skip-and-count cases (`ok` variant)

```
6 6 6 30 12
skipped events present in examples.parquet: []
```
Matches the ticket's expected `6 6 6 30 <n>` shape exactly (`events_skipped_no_call` is
unaffected here since this fixture's steps never hit `build_call` or the round-trip gate).

### F5 — `consumed.json`

```
6 3
True
```

### F6 — the per-split cap is deterministic

```
deterministic cap ok 3 ['test', 'train', 'val']
```

### F7 — the history rule

```
"Task: Play my playlist.\n[HISTORY]\nprint(apis.supervisor.show_profile()) -> {'name': 'alice'}\n
print(len('inspecting the namespace')) -> 24\nprint(apis.supervisor.show_profile()) ->
{'name': 'alice'}\n[THINKING]\nI will look at the supervisor profile first, then decide what to
do next."
no-code observation absent: True
api-less action present: True
api-less result present: True
```

## The commit

- `dfba7dc` — `T09: apply owner ruling round 1 (RULING-9): skip build_call/round-trip failures`
  (the only commit; one logical unit).

## Self-review findings and open questions

- **The ticket's F3 `bad_call` row is superseded by this ruling, not broken by an implementation
  defect.** `bad_call` patches `AppWorld.build_call` to always drop its arguments
  (`tool + '()'`), which used to make the round-trip gate raise for every event and stop the
  build (`exit != 0`). Under RULING-9 that same failure now takes the skip path like any other
  round-trip mismatch: the build finishes (`exit=0`) with zero examples and every event named in
  `report.md` and counted under `events_skipped_no_call`. This is the ruling working as
  specified — the affirmative condition is "the call rebuilds and round-trips" with no exception
  for a systemic file defect versus a rare data value — but it means `data/build_training_dataset.py`
  no longer has a gate that turns a broken `build_call` into a hard stop; a defective
  `data/environments/appworld.py` file now degrades the dataset silently instead of failing the
  build loudly. Flagging this for the record since it is a real behavior change from what
  contracts 2.5 originally specified for that row ("It becomes a stop here because `build_call`
  is now the inverse of `split_args`... so a row that fails it is a defect in the environment
  file rather than a known loss") and from the ticket's own F3 table, both of which RULING-9
  supersedes by design. No code change is proposed for this: the dispatch's ruling text is
  explicit that everything but "the call rebuilds and round-trips" takes the skip path, with no
  special case.
- The `unknown_task` fixture variant still trips the completeness gate before reaching the split
  gate it is meant to exercise — a pre-existing, already-documented script defect in the ticket's
  own Comments (wave-3 precheck), unrelated to this change and left as is.
- No open question beyond the one above; the ruling's own text answers everything else the
  ticket left open for this file.
