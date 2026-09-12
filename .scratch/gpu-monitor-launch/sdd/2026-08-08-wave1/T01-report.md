# T01: Heartbeat module and verdict engine, all unit tests green

Ticket: `.scratch/gpu-monitor-launch/issues/01-heartbeat-verdicts.md`
Requirement source: `docs/plans/2026-08-08-gpu-monitor-launch.md` Task 1 (heartbeat module), Task 2 (verdict engine).
This ticket does not directly cite any section of spec.md (the ticket names the implementation plan, not the spec); spec.md was not read.

## What was done (against the ticket's four acceptance items)

1. **Heartbeat tests pass: required fields all present, optional fields absent when not given, parse round-trips consistently, garbage lines return None**
   - New `ops/heartbeat.py`: `emit(done, total, unit, *, tok_in=None, tok_out=None, loss=None, status=None, stream=None)` and `parse(line) -> dict | None`, constant `PREFIX = "@hb "`. The code matches the implementation given in plan Task 1 Step 3 verbatim.
   - New `tests/test_heartbeat.py`, 4 cases: all required fields present, optional fields appear/don't appear as needed, emit→parse round trip, three kinds of garbage lines (no `@hb ` prefix / invalid JSON / missing required field) all return `None`.

2. **Verdict tests pass: at least one case per each of the six verdicts, stall-line floor, warm-up ceiling, probe failure does not verdict dead, all four service-kind cells have boundary cases**
   - New `ops/verdicts.py`: `DEFAULTS` config dict, `typical_gap_s`, `stall_line_s`, `rates`, `judge` (including an internal `_judge_service` that handles the `kind="service"` branch), six verdict constants `V_DONE/V_DEAD/V_STALL/V_WARMUP/V_SLOW/V_OK`. The code matches the implementation given in plan Task 2 Step 3 verbatim.
   - New `tests/test_verdicts.py`, 11 cases, covering:
     - `test_done_beats_everything`: done outranks alive/status
     - `test_dead`: alive=False verdicts dead and immediately hits the escalate line
     - `test_stall_and_escalate`: a stall past the stall line verdicts suspected stall; only past the escalate line (stall line x3) does escalate=True
     - `test_warmup_and_warmup_timeout`: warming up, past the warm-up ceiling turns into suspected stall
     - `test_stall_line_fallback_when_few_intervals`: when `stall_s=None` (not enough interval samples), the warm-up ceiling is used as a stopgap, no false positive
     - `test_slow_needs_recent_rate`: recent rate < average x0.5 verdicts slow, missing recent rate verdicts healthy
     - `test_probe_fail_keeps_previous_alive`: `alive=None` (probe failure) does not verdict dead
     - `test_service`: the four service-kind cells (port never answered → warming up, has answered → healthy, 3 consecutive rounds no answer → suspected stall, alive=False → dead)
     - Three `TestLinesAndRates` cases: `typical_gap_s` median, `stall_line_s` floor plus override plus returning None on insufficient samples, `rates` average/recent rate and the boundary where first_beat/recent_beats are empty.

3. **Both modules use only the standard library, all constants are collected in the verdict engine's DEFAULTS config**
   - `ops/heartbeat.py` only imports `json`, `sys`, `time`.
   - `ops/verdicts.py` only imports `statistics.median`.
   - Every threshold that appears in the verdict engine (stall-line multiplier, floor sample-round count, escalate-line multiplier, warm-up ceiling, recent-rate window, typical heartbeat interval window, minimum interval count, slow-down ratio, service-port consecutive-failure round count) is collected in the `DEFAULTS` dict; there are no scattered hardcoded constants in the function bodies.

4. **`python3 run.py selfcheck` passes, each task has its own commit**
   - `python3 run.py selfcheck` prints `selfcheck: 62 tasks / 4 recipes, all present` (this ticket did not add or change any run.py registry entries. Heartbeat and verdicts are pure library modules imported by other tasks, not standalone runnable tasks, and the plan's Task 1/2 did not require registering them either).
   - Task 1 has its own commit, Task 2 has its own commit (list below).

## How it was verified

```
$ python3 -m unittest tests.test_heartbeat -v
test_emit_optional_fields (tests.test_heartbeat.TestHeartbeat) ... ok
test_emit_required_fields (tests.test_heartbeat.TestHeartbeat) ... ok
test_parse_rejects_garbage (tests.test_heartbeat.TestHeartbeat) ... ok
test_parse_roundtrip (tests.test_heartbeat.TestHeartbeat) ... ok

Ran 4 tests in 0.000s

OK
```

```
$ python3 -m unittest tests.test_verdicts -v
test_dead (tests.test_verdicts.TestJudge) ... ok
test_done_beats_everything (tests.test_verdicts.TestJudge) ... ok
test_probe_fail_keeps_previous_alive (tests.test_verdicts.TestJudge) ... ok
test_service (tests.test_verdicts.TestJudge) ... ok
test_slow_needs_recent_rate (tests.test_verdicts.TestJudge) ... ok
test_stall_and_escalate (tests.test_verdicts.TestJudge) ... ok
test_stall_line_fallback_when_few_intervals (tests.test_verdicts.TestJudge) ... ok
test_warmup_and_warmup_timeout (tests.test_verdicts.TestJudge) ... ok
test_rates (tests.test_verdicts.TestLinesAndRates) ... ok
test_stall_line_floor (tests.test_verdicts.TestLinesAndRates) ... ok
test_typical_gap_median (tests.test_verdicts.TestLinesAndRates) ... ok

Ran 11 tests in 0.000s

OK
```

```
$ python3 run.py selfcheck
selfcheck: 62 tasks / 4 recipes, all present
```

```
$ python3 -m unittest discover -s tests -v
(all 15 items ok, heartbeat 4 + verdicts 11)
Ran 15 tests in 0.001s
OK
```

## Commit list

- `c890cec`: T01: monitor: heartbeat module ops/heartbeat.py(emit/parse,stdlib-only)
  (`ops/heartbeat.py`, `tests/__init__.py`, `tests/test_heartbeat.py`)
- `ba3cdbb`: T01: monitor: verdict engine ops/verdicts.py(six-cell priority + adaptive two lines + rates, pure functions)
  (`ops/verdicts.py`, `tests/test_verdicts.py`)

## Self-check findings and open questions

- The implementation code and test code for both modules were already fixed in the plan document (Step 1/Step 3 give the full source), so this ticket copied them exactly, with no room for improvisation and no place found where the implementation differed from the plan's code in a way that needed an on-the-spot decision.
- `run.py selfcheck`'s "all tasks/recipes present" is a generic self-check; this ticket did not change the `run.py` registry, so this acceptance item is equivalent to "nothing else got broken," not a targeted check of this ticket's new content.
- No deviation from the ticket/plan was found, and there are no lingering ambiguities.
