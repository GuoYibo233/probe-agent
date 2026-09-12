# T07 report: Terminal outlet switched to reading sampling history

Ticket: `.scratch/gpu-monitor-launch/issues/07-terminal-outlet.md`
Reference: `docs/plans/2026-08-08-gpu-monitor-launch.md` Task 8 (named directly in the ticket text)
Branch: `ticket/20260808-par/T07`, worktree `new1-wt/20260808-par-T07` (cleaned up)
commit: `873f478`

## What was done

Against the ticket's four requirements one by one:

1. **When the sampler isn't running: the warning line falls back to the old table, and the json outlet outputs valid JSON.**
   `ops/gpu_jobs.py` got a new `read_latest()` (reads `MONITOR_DIR/latest.json`,
   returns `(latest_dict|None, age_s|None)`; missing file/unreadable/corrupt JSON all
   return `(None, None)`). All three of `cmd_status`/`cmd_watch`/`cmd_json` call
   `read_latest()` first; `latest is None or age_s > FRESH_S` (`FRESH_S=300.0`)
   goes to the stale branch: the two terminal outlets print the original wording given by `_stale_warning()`,
   `Sampler isn't running (last sampled <time|none>), probing live now`,
   then fall back to the original `collect()` + `fmt_table()` path; the json outlet's stale case outputs
   `{"rows": collect(), "sampler_stale": True}` (a bare list can't carry an extra field,
   so it's wrapped in a `rows` key, whose name matches the key `latest.json` already uses).

2. **Point at a fake latest-sample file: the new table can be produced, and the verdict/progress/rate/ETA columns all render.**
   The fresh branch calls the newly written `fmt_table_v2(rows, sampled_at)`: the header's first line reads
   `Last sampled HH:MM:SS`; columns are `JOB/HOST/GPU/verdict/PROGRESS/RATE/TOK/ETA/SESSION`
   (the ticket's original list). PROGRESS uses the `progress_pct` the sampler already computed,
   assembled into `done/total (pct%) unit`; RATE picks a unit by order of magnitude.
   `recent_rate >= 1` keeps `/s`, otherwise multiplies by 3600 to show `/h` (the ticket's original wording,
   "multiply by 3600 to show /h, or keep /s depending on order of magnitude," did not give a precise threshold.
   This boundary was set by me on the grounds that "batch tasks commonly have rates <1/s, vLLM-style throughput commonly has >=1/s," written into
   `_fmt_rate_v2`'s docstring for review); TOK is assembled using a thousands-abbreviated format
   (`_fmt_tok_short`: `>=1e6` uses `X.YM`, `>=1e3` uses `Xk`) into
   `tok_in/tok_out`; ETA converts `eta_s` into `HH:MM`.

3. **The two verdicts done and dead still get a wrap-up/check-the-log tip line.**
   `fmt_table_v2` groups by job: only when every piece under a job verdicts
   `verdicts.V_DONE` (done) does it output
   `Done = all pieces verdict done, time to wrap up: python3 run.py gpu-jobs finish <job>`;
   whenever any row verdicts
   `verdicts.V_DEAD` (dead), it outputs
   `Dead = session is gone, progress not at 100%, check the log: <log path of the first dead row>`.
   Both tips' wording were rewritten from the original DONE/EXIT two lines already in `fmt_table()`. That original text
   depended on old `state` fields ("session has exited" / "progress 100%"), while now it directly reads the
   `verdict` field the sampler already computed; the meaning lines up but the wording isn't a verbatim copy. This is a small,
   non-functional judgment call I made regarding the ticket's "reuse the wording" instruction, noted in the open questions below.

4. **Commit.** `873f478`, see above.

`free`/`register`/`finish` were left entirely untouched, still only probing on the spot via
`collect()`/`live_sessions()` (confirmed against the diff: changes only touched `cmd_status`/
`cmd_watch`/the newly added `cmd_json`, `cmd_free`/`cmd_register`/`cmd_finish`/
`cmd_finish_force` unchanged as-is).

## How it was verified

### Automated tests

New `tests/test_gpu_jobs.py` (this pipeline currently has no existing precedent of a
`gpu_jobs.py` test, styled the same way as `test_sampler.py`/`test_sampler_web.py`: using
`NEW1_MONITOR_DIR`/monkeypatching `gpu_jobs.REG_PATH` to point the on-disk directory and the ledger
to tmp). Four test classes:

- `TestReadLatest`: file missing → `(None, None)`; fresh file → `age_s < 5`;
  a file from an hour ago → `age_s > FRESH_S`; corrupt JSON → `(None, None)`.
- `TestFmtTableV2`: fake rows render all columns (verdict value, the progress format `3/10 (30.0%) task`,
  the rate conversion `72/h`, the token abbreviation `1.2M/340k`, the
  ETA conversion `01:02`); empty rows still gives a header placeholder; a job whose pieces are all
  `done` gets a wrap-up tip; a `dead` row gets a check-the-log tip.
- `TestCmdJson`: no sampler → `sampler_stale: True` with `rows == []` (ledger
  empty); fresh latest.json → output verbatim, without a `sampler_stale` field; stale
  → `sampler_stale: True` plus the old `collect()` result.
- `TestCmdStatus`: no sampler → the warning line verbatim plus the old table; fresh latest.json →
  the new table (without "probing live now," with "Last sampled"/"verdict"/extras'
  `stray_session`).

```
$ python3 -m unittest tests.test_gpu_jobs -v
...
Ran 13 tests in 4.043s
OK
```

Every unit test touched by this change (including the sampler/verdicts/launch series) was run together as a whole:

```
$ python3 -m unittest discover -s tests -v 2>&1 | tail -5
...
Ran 92 tests in 6.890s
OK
```

`python3 run.py selfcheck`: the worktree reports 16 "missing interpreter/program" items, but these
are all venvs of various envs (`envs/appworld/venv` etc.). venvs are not in git, and the newly built
worktree has none of them, caused by the worktree's own product isolation, not a problem introduced by this
change. The same selfcheck run in the main-repo worktree (with real venvs) gives
"63 tasks / 4 recipes, all present." This ticket did not touch the `run.py` registry (the `gpu-jobs`
task entry is unchanged, only the internal script implementation changed); the selfcheck gate isn't a hard requirement per the protocol, but it was
still run once to confirm nothing about the ledger-related task definitions was broken.

### Manual verification specified in ticket Step 2

The worktree did not set `NEW1_MONITOR_DIR` (going through the default NFS path); the login machine really
had the sampler from T14 running, so `python3 run.py gpu-jobs` went straight through the
fresh branch (header `Last sampled 07:23:52`), not the "sampler isn't running" scenario described
in ticket Step 2. To verify against the ticket's original wording faithfully, two extra groups were done:

**Scenario A (`NEW1_MONITOR_DIR` pointed at an empty tmp dir, simulating "sampler isn't running"):**

```
$ NEW1_MONITOR_DIR=/tmp/t07-empty-mon python3 run.py gpu-jobs
Sampler isn't running (last sampled none), probing live now
Ledger is empty, no jobs currently registered. Launching via the gpu-run skill auto-registers.
...
$ NEW1_MONITOR_DIR=/tmp/t07-empty-mon python3 run.py gpu-jobs json \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print('json ok', d.get('sampler_stale'))"
json ok True
```

**Scenario B (a fake latest-sample file):**

```
$ NEW1_MONITOR_DIR=/tmp/t07-fake-mon python3 run.py gpu-jobs
Last sampled 07:24:35
JOB      HOST      GPU  verdict  PROGRESS           RATE   TOK       ETA    SESSION
-------  --------  ---  -------  -----------------  -----  --------  -----  -------------------
fakejob  tokyo106  0    healthy  5/20 (25.0%) task  180/h  500k/12k  00:05  new1_fakejob_t106g0
```

The verdict, progress, rate, ETA, and token columns all render, with the header carrying the last-sampled time, satisfying
acceptance item 2.

**Scenario C (tip lines for the two done/dead verdicts):**

```
JOB      HOST  GPU  verdict   PROGRESS             RATE  TOK  ETA  SESSION
-------  ----  ---  --------  -------------------  ----  ---  ---  -------
donejob  h     0    done      10/10 (100.0%) task  -     -    -    s0
deadjob  h     1    dead      3/10 (30.0%) task    -     -    -    s1

Done = all pieces verdict done, time to wrap up: python3 run.py gpu-jobs finish donejob
Dead = session is gone, progress not at 100%, check the log: /tmp/deadjob.log
```

Satisfies acceptance item 3. All three temporary `NEW1_MONITOR_DIR` directories
(`/tmp/t07-empty-mon`, `/tmp/t07-fake-mon`, `/tmp/t07-tips-mon`) were deleted after verification.

## Commit list

- `873f478`: T07: gpu-jobs's three outlets switched to reading sampling history (fresh uses latest.json, stale prints a warning and falls back to live probing)
  (changed `ops/gpu_jobs.py`, added `tests/test_gpu_jobs.py`, synced the corresponding
  `MAP.md` line)

## Self-check findings and open questions

- **A bug found and fixed on the spot**: the first version of the `dead` tip line was written as an f-string with
  `100%%`, that was copied directly from the old `fmt_table()`'s `%`-format string, but
  f-strings don't do `%`-escaping, so it would literally print two percent signs. Self-check caught this and
  changed it to `100%` (a single percent sign), already in the commit.
- **Open question 1 (RATE unit-switch threshold)**: the ticket's original wording, "multiply by 3600 to show
  `/h`, or keep `/s` depending on order of magnitude," did not give a precise switch point.
  I set it at `recent_rate >= 1` uses `/s`,
  otherwise multiply by 3600 for `/h`. This threshold is my own estimate based on common rate
  magnitudes, with no more authoritative basis. If it's inconsistent with how other outlets display it
  (the web `render_html` always uses `/s`, no unit switching), it needs user confirmation on whether to change it.
- **Open question 2 (tip line wording)**: the ticket asks to "reuse the existing `fmt_table` wording," but the
  old wording was baked with old field semantics ("session exited"/"progress 100%"), which is not the same
  basis of judgment as the new `verdict` field. I kept the skeleton of the old wording (the two key phrases
  "time to wrap up"/"check the log" kept verbatim), but the sentence as a whole isn't a verbatim copy. If the user wants
  the old sentence reused verbatim, the wording needs adjusting here; this does not affect functionality.
- **Untouched**: `ops/jobs.json`, the `run.py` registry, the `free`/`register`/
  `finish` commands, `ops/sampler.py`, `ops/verdicts.py`, all left as-is.

## Fix round 1 (review findings F1/F2)

Branch: `ticket/20260808-par/T07` (same branch), worktree
`new1-wt/20260808-par-T07-fix1` (cleaned up), commit `f5a864a`.

### F1 (critical): read_latest() needs shape/type guards

**Problem**: `read_latest()` only caught `(OSError, ValueError)`, which blocks
"file missing" and "JSON syntax is broken," but if latest.json is valid JSON
that isn't the expected shape (the top level isn't a dict, or `sampled_at` isn't the right type), it will throw an
uncaught exception inside `read_latest()` or at the call site, causing `status`/`watch`/
`json` to all traceback straight out instead of the ticket's required "stale means print a warning and fall back to
live probing."

**How it was fixed**: after `json.load()` succeeds, `read_latest()` now adds two layers of validation:

1. If `latest` isn't a `dict` (e.g. the top level is an array), return
   `(None, None)` directly, without going on to call `latest.get(...)`.
2. If the `sampled_at` field exists but its type isn't `int`/`float` (excluding
   `bool`, because `bool` is a subclass of `int` but shouldn't be treated as a timestamp semantically), also return
   `(None, None)`, not passing the malformed `latest` through to the caller (the caller's
   `_stale_warning()` would similarly crash on `datetime.fromtimestamp()` given a string-typed
   `sampled_at`, so this swallows `latest` along with it rather than
   only swallowing `age_s`).
3. If the `sampled_at` field is entirely missing (original behavior, not new this round), keep the original behavior:
   return `(latest, None)`, passing `latest` through as-is; the caller falls back to the stale branch by way of
   `age_s is None`.
4. An additional `try/except (TypeError, OverflowError, OSError)` was wrapped around the arithmetic
   `time.time() - sampled_at` itself, defensively covering extreme values (e.g. an overly
   large float overflowing).

The docstring was rewritten to reflect the two newly-covered malformed shapes in the "all return (None, None)" list.

**How it was verified**:

Added 3 `TestReadLatest` cases (`tests/test_gpu_jobs.py`):

- `test_sampled_at_wrong_type_returns_none_none`: `sampled_at` is a string
  → `(None, None)`.
- `test_top_level_not_dict_returns_none_none`: top level is `[]` → `(None, None)`.
- `test_missing_sampled_at_field_returns_latest_and_none_age`:
  `sampled_at` entirely missing (distinct from a type error) → `(latest, None)`, confirming the original
  behavior was not broken by the new validation.

Re-ran the finding's original reproduction commands, and both scenarios changed from "traceback out directly"
to "warning line + old table, exit 0":

```
$ mkdir -p /tmp/t07f1-strtype /tmp/t07f1-toplist
$ echo '{"sampled_at":"x"}' > /tmp/t07f1-strtype/latest.json
$ echo '[]' > /tmp/t07f1-toplist/latest.json

$ NEW1_MONITOR_DIR=/tmp/t07f1-strtype python3 ops/gpu_jobs.py; echo "exit=$?"
Sampler isn't running (last sampled none), probing live now
Ledger is empty, no jobs currently registered. Launching via the gpu-run skill auto-registers.
...
exit=0

$ NEW1_MONITOR_DIR=/tmp/t07f1-toplist python3 ops/gpu_jobs.py; echo "exit=$?"
Sampler isn't running (last sampled none), probing live now
Ledger is empty, no jobs currently registered. Launching via the gpu-run skill auto-registers.
...
exit=0

$ NEW1_MONITOR_DIR=/tmp/t07f1-strtype python3 ops/gpu_jobs.py json; echo "exit=$?"
{
  "rows": [],
  "sampler_stale": true
}
exit=0

$ NEW1_MONITOR_DIR=/tmp/t07f1-toplist python3 ops/gpu_jobs.py json; echo "exit=$?"
{
  "rows": [],
  "sampler_stale": true
}
exit=0
```

`cmd_watch`'s call to the same `read_latest()` (now the shared
`_print_table_from_latest_or_fallback()`) is covered by the same guard at the same time across all three outlets, and
was not re-tested separately.

### F2 (important): de-duplicate the freshness branch in cmd_status/cmd_watch

**Problem**: `cmd_status()` and `cmd_watch()` each had an inline copy of the exact same
5-line "read latest → render fresh/fall back to stale" logic. Changing the
`FRESH_S` condition or the rendering choice would need both places updated in sync, making it easy to miss one.

**How it was fixed**: extracted this logic into a new function
`_print_table_from_latest_or_fallback()`: internally calls `read_latest()`; if fresh, prints
`fmt_table_v2()` and returns `latest.get("extras") or {}`; otherwise prints
`_stale_warning()`, falls back to `collect(with_extras=True)` + `fmt_table()`,
returning `extras`. `cmd_status()`/`cmd_watch()` are each reduced to one line calling
`extras = _print_table_from_latest_or_fallback()`, with the part that prints the extras tip line
afterward (the two tip texts were already different, status says "missed a
register? another conversation using it?", watch is a condensed version) kept in their own functions, not
force-merged into something that shouldn't be merged.

`cmd_json()`'s branching logic was not covered by this extraction. It goes through a different
rendering path from status/watch (JSON serialization vs. table printing), and the finding also only pointed at
status/watch, not json, so the ticket's original scope was kept, not expanded.

**How it was verified**: the extraction is a pure refactor (the same logic moved into a function); behavior is backed by
existing tests. Both `TestCmdStatus` cases (no sampler/fresh latest.json) passed both before and after the
change; no separate test was added for `cmd_watch` (the original report already had no dedicated
automated test for `cmd_watch`. The `while True` loop isn't convenient to unit test, and the ticket's acceptance criteria
did not name a dedicated watch test either, keeping the original test-coverage boundary unexpanded).

### Test results summary

```
$ python3 -m unittest tests.test_gpu_jobs -v 2>&1 | tail -20
...
Ran 16 tests in 3.372s
OK
```

```
$ python3 -m unittest discover -s tests 2>&1 | grep -E "Ran |OK|FAILED"
Ran 95 tests in 6.615s
OK
```

(92 → 95: this round added 3 new `TestReadLatest` boundary cases.)

`python3 run.py selfcheck`: the worktree reports the same 16 "missing interpreter/program" items,
consistent with what the original report recorded. All caused by each env's missing venv, caused by worktree
product isolation, not introduced by this change. The `gpu-jobs` task entry is unchanged.

### Commit list (this round)

- `f5a864a`: T07: fix round 1, read_latest() gets shape/type guards (F1),
  status/watch freshness branch de-duplicated (F2)
  (changed `ops/gpu_jobs.py`: `read_latest()` got shape/type validation,
  `cmd_status`/`cmd_watch` extracted into `_print_table_from_latest_or_fallback()`; changed
  `tests/test_gpu_jobs.py`: 3 new `TestReadLatest` boundary cases)

### Self-check findings and open questions (this round)

- No new bugs found.
- Thought through one extra step while fixing F1: when `sampled_at`'s type is wrong, should `latest` be kept,
  only setting `age_s` to `None`? Chose to swallow `latest` too. The reason being that `_stale_warning()`
  likewise reads `latest.get("sampled_at")` directly and passes it to
  `datetime.fromtimestamp()`; if only `age_s` were swallowed and not `latest`, the malformed
  `sampled_at` string would crash somewhere else inside `_stale_warning()`, not actually plugging the
  hole the finding described. This judgment doesn't affect the acceptance criteria, noted here for review.
- When extracting F2, confirmed that `cmd_json()` is out of the finding's scope, and didn't opportunistically pull it in
  too. The finding's original text only names `cmd_status`/`cmd_watch`, keeping the
  scope unexpanded.
