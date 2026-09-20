# 04 assemble with hist_rounds 0 puts the whole history into the probe's text instead of none

Status: needs-triage
Severity: important
File: data/probe_input.py:63-66
Contract: 1.7 ("`assemble` keeps the last `hist_rounds` of them")
Errata: not recorded. Errata "Part 1.7 (the two guards)" adds the `max_cuts < 2` and `probe_result_cap < 100` refusals and says nothing about `hist_rounds`.

## Finding

`assemble` takes the last `hist_rounds` rounds with a negative slice:

```python
    lines += [
        f"{action} -> {_clip(observation, probe_result_cap)}"
        for action, observation in history[-hist_rounds:]
    ] or ["(start)"]
```

For `hist_rounds == 0` the expression is `history[0:]`, which is the whole
history, not the empty list. Confirmed by running the function with four rounds
and `hist_rounds=0`:

```
assemble("T", [("a1","o1"),("a2","o2"),("a3","o3"),("a4","o4")], "think", 0, 400)
-> 'Task: T\n[HISTORY]\na1 -> o1\na2 -> o2\na3 -> o3\na4 -> o4\n[THINKING]\nthink'
```

`experimental_settings/schema.py:75` types the field `hist_rounds: int = 3` with
no floor, and `run.py`'s `section.field=value` override accepts
`build.hist_rounds=0` on the command line.

## Failure scenario

An ablation that asks "does the probe need the tool history at all?" is written
as `build.hist_rounds=0`, either in a setting file or as a command-line
override. The value is a real `build` field, so it enters the build key
(`PROBE_TEXT_FIELDS`, contract 1.7), the run gets its own directory, and the
build finishes with no error. Every example row's `text` carries the *entire*
trajectory history, which is the opposite of what was asked and is also longer
than any other setting's text, since the `hist_rounds` cap is what keeps the
probe's input bounded. `train` and `eval` then report numbers for "no history"
that were produced with unbounded history, and the inject run inherits the same
field, so live and offline agree with each other and nothing anywhere
contradicts the label on the experiment.

## Proposed fix

Make the slice say "the last `hist_rounds` rounds" for every value of the field,
in `data/probe_input.py`:

```python
    kept = history[len(history) - hist_rounds:] if hist_rounds > 0 else []
```

and refuse a negative `hist_rounds` naming the field, beside the two guards
`cuts` and `_clip` already carry (errata "Part 1.7 (the two guards)"). `VERSION`
does not move: no existing setting writes 0, so no finished output changes.
