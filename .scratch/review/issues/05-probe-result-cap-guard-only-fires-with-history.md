# 05 the probe_result_cap floor is checked once per history entry, so a bad cap passes at step 0 and raises later

Status: needs-triage
Severity: minor
File: data/probe_input.py:46-51, data/probe_input.py:54-68
Contract: 1.7 (`assemble`'s parameters)
Errata: "Part 1.7 (the two guards)": "`assemble` raises `ValueError` naming `probe_result_cap` below 100". The entry puts the refusal on `assemble`; the code puts it on `_clip`.

## Finding

The floor lives inside the per-observation clipper:

```python
def _clip(s: str, cap: int) -> str:
    """Clip a history observation to at most cap characters, keeping the head and tail."""
    if cap < 100:
        raise ValueError(f"probe_result_cap must be at least 100, got {cap}")
```

and `_clip` is reached only from the list comprehension over `history`, so
`assemble` with an empty history never evaluates it. Confirmed:

```
assemble("T", [], "think", 3, 50)   -> 'Task: T\n[HISTORY]\n(start)\n[THINKING]\nthink'   (no raise)
assemble("T", [("a1","o1")], "think", 3, 50) -> ValueError: probe_result_cap must be at least 100, got 50
```

The value is a setting field (`experimental_settings/schema.py:76`,
`probe_result_cap: int = 400`) with no floor in the schema, and the errata entry
that created the guard states it as a property of `assemble`, which is the
function both layers call.

## Failure scenario

A setting (or a `build.probe_result_cap=50` override) is launched with a cap
below 100.

- `build`: step 0 of every trajectory has an empty history, so the first
  examples are written; the first event that has a history entry raises
  `ValueError` out of the middle of the record walk. The stage dies after
  reading records and writing nothing, with no `done.json`, and `ls` reports it
  failed on a value that was wrong before the first record was read.
- `inject`: the same setting inherits `PROBE_TEXT_FIELDS` from the build run
  (5.4), and the live injector calls `assemble` per cut. Step 0 fires normally;
  the first cut of step 1 raises inside the task loop,
  `agent/run_tasks.py:180` catches it, and the task is closed with
  `abort="task_error:ValueError"` and counted done by `is_done`. Every task of
  the run aborts the same way and the run reaches `done.json` with a full set of
  one-step records.

## Proposed fix

Put the refusal where the errata puts it. In `data/probe_input.py`, `assemble`
checks `probe_result_cap` (and, per ticket 04, `hist_rounds`) at its top, before
it builds any line, so the value is refused on the first call whatever the
history holds; `_clip` keeps clipping and stops re-deciding whether the cap is
legal.
