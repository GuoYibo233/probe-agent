# T05 report: remaining time in run.py ls

Ticket: `.scratch/card-record-and-remaining-time/issues/05-remaining-time-in-ls.md`
Spec section: "Remaining time" of `.scratch/card-record-and-remaining-time/spec.md`
Branch: `ticket/2026-10-02-wave3/T05`, base `ae70b18f7d3c712cc2da30e488b9ca17cc2bd226`, head `afa6464`.

## 1. What was done

| requirement | done |
|---|---|
| `_format_ls_row` adds `left=<h>h<mm>` after the rate for a run without a finish row, `(total - done) / recent_rate` | New `_format_left(row)` in `run.py`, called from `_format_ls_row`; the field sits between `rate=` and `beat=`. Hours unpadded, minutes two digits, the seconds rounded to the nearest minute. The `ls` header line in `cmd_ls` gains `left` between `rate` and `heartbeat`. |
| a `train` run whose newest beats carry the unit `prediction split` prints `left=<h>h<mm> (prediction)`; during training `(training)`, which leaves out the prediction phase | For stage `train`, the label is `training` when the row's unit equals `registry.SPEED_UNIT["train"]` (`"step"`, the unit of the training beats) and `prediction` otherwise (the only other unit the trainer beats in is `PREDICTION_UNIT = "prediction split"`). The row's `unit` is the newest beat's unit (`_piece_verdict_dict` reads `last.get("unit")`), so the label follows the newest beats. The time is computed from the same `progress` pair and rate the line prints, which for a train run are the current phase's own numbers, so `(training)` leaves out the prediction pass. |
| no rate, or a finished run: `left=-` | `left=-` when `recent_rate` is `None` or not positive, or when the row's status is not `launching`. |
| `run.py --help`'s `ls` line mentions the field | `_SUBCOMMAND_ONE_LINE["ls"]`: "one folded line per run, with an open run's remaining time as left=<h>h<mm> (a train run's line names its phase, training or prediction); closes a launch whose pieces are all dead". |
| README section 2 line of `run.py` mentions the field | Clause added: "ls prints after each run's rate its remaining time, left=<h>h<mm>, the work left at the recent rate for a run without a finish row, a train run's line naming its current phase (training, which leaves out the prediction pass, or prediction), and left=- for a run with no rate or with a finish row". |
| CPU-only unit test: 300/1575 tasks at 0.03 tasks/s prints `left=11h48`; no rate prints `left=-` | `LsLineTest` in `tests/test_registry_concurrent_append.py` (the module ticket 02 extended with the beat and card-record cases), four tests: the 11h48 case, no rate, a finished run (`status="ok"`), and the two train phases (`left=0h25 (training)`, `left=0h50 (prediction)`). It loads the real `run.py` by path under its own name with the repo root on `sys.path`; `_format_ls_row` reads only the row dict it is given, so nothing is written. The module docstring and the README `tests/` line name the new cases. |

How "a run without a finish row" is read: `registry._ls_row` gives a run with no finish row its start row's status, and every start-row writer (`jobs/launch.py` twice, `run.py` once) writes `status: "launching"`; a run with a finish row carries the finish row's word (`ok`, `failed`, `killed`, `launch_failed`, ...). `run.py`'s `_close_failed_launches` already uses `status == "launching"` as its test for an open run, and it rewrites the row's status to `launch_failed` before the rows are printed, so a launch it closes prints `left=-`. No field was added to `registry.ls`'s row.

No file outside `run.py`, `README.md` and `tests/test_registry_concurrent_append.py` changed; no `jobs/versions.yaml` row is needed (`run.py` is in no stage's code set).

Where the code came from: nothing ported; the formula and labels are the ticket's, the training-unit name is the existing `jobs/registry.SPEED_UNIT`.

## 2. How it was verified

All commands run from the worktree `/home/y-guo/reproduce/new1-wt/2026-10-02-wave3-T05` with the main repo's interpreter (the worktree has no `external/` link), on yebis.

```
$ /home/y-guo/reproduce/new1/external/probe-env/bin/python tests/test_registry_concurrent_append.py
....................
----------------------------------------------------------------------
Ran 20 tests in 0.779s

OK
```

```
$ /home/y-guo/reproduce/new1/external/probe-env/bin/python run.py selfcheck
selfcheck: 32 python files, 0 problems
```

(The `venvs:` map in `constants/path_datasets.yaml` holds absolute interpreter paths, so the per-interpreter import checks ran in full from the worktree.)

All CPU test modules, each in its own process:

```
== test_registry_concurrent_append
Ran 20 tests in 0.804s
OK
== test_settings_keys
Ran 25 tests in 25.025s
OK
== test_probe_input
Ran 19 tests in 1.986s
OK
== test_record_formats
Ran 16 tests in 0.089s
OK
== test_probe_eval
Ran 15 tests in 2.081s
OK
== test_environment_and_build
Ran 22 tests in 0.073s
OK
== test_qwen3_family
Ran 13 tests in 32.557s
OK
```

`tests/test_packed_loss.py` needs torch and the Qwen3 tokenizer on NFS, is not one of the CPU-only modules, and covers nothing this ticket changed; it was not run.

The `--help` line:

```
$ /home/y-guo/reproduce/new1/external/probe-env/bin/python run.py --help | grep " ls "
  ls          [workflow] [--debug] -- one folded line per run, with an open run's remaining time as left=<h>h<mm> (a train run's line names its phase, training or prediction); closes a launch whose pieces are all dead
```

The arithmetic of the acceptance case: (1575 - 300) / 0.03 = 42500 s = 708.3 min, which rounds to 708 min = 11 h 48 min, printed `left=11h48`.

## 3. Commits

- `afa6464` T05: run.py ls prints an open run's remaining time after its rate (run.py `_format_left` and the ls header and help line, README section 2 lines of run.py and tests/, `LsLineTest` in tests/test_registry_concurrent_append.py)

## 4. Self-review findings and open questions

- A zero recent rate also prints `left=-`. The ticket says "no rate"; a rate of 0 gives no finite time and would divide by zero, so it is treated as no rate.
- At the switch from training to prediction, `registry.rates` takes its recent window over the newest counting beats regardless of unit, so for the first few prediction beats the window mixes step beats and prediction-split beats. While the prediction count is below the last step count the rate comes out `None` and the line prints `left=-`; a window whose first step beat has a `done` at or below the current prediction count would give a mixed rate. This is in `jobs/registry.rates`, outside this ticket; it lasts until the window holds prediction beats only.
- The open-run test is `status == "launching"`, the start rows' one status word and the test `_close_failed_launches` already uses. If a start row ever carries another word, this test and that one move together.
- Merge note: the README `tests/` line is one long line and the test module's docstring changed; the wave 2 branches (T03, T04) may touch the same lines, so the merge may need a hand join there.

## Fix round 1

Worktree `/home/y-guo/reproduce/new1-wt/2026-10-02-wave3-T05-fix1` on branch `ticket/2026-10-02-wave3/T05` (checked out from `afa6464`), on yebis. Head after this round: `ab0f602`.

### F1 (critical): an ordinary train run never printed `left=<h>h<mm> (prediction)`

Cause, confirmed: `registry._piece_verdict_dict` handed `rates()` the newest counting beats of every unit. A train piece's step beats end at `done = steps`, its prediction beats count from 0 to `predict_total` (2 or 8 in every setting in the tree), so the 10-beat recent window always started on a step beat with a larger `done` than the prediction count, and `rates()` returned `None` for the whole prediction phase. The previous round's self-review note (the gap "lasts until the window holds prediction beats only") was wrong for these settings, as the finding says.

Fix, in `jobs/registry.py` `_piece_verdict_dict`: the rates (the recent window and the average's first beat) are read over the counting beats whose unit equals the newest counting beat's unit. The stall line's `beat_ts` is still read over all counting beats, as before. Each phase of a train piece now has a rate of its own; the prediction phase has one from its second beat on (its first beat, `0/total`, is a single point and gives no rate, so the line prints `left=-` there). A heartbeat file in one unit (sample, inject, a predict-only relaunch) reads exactly as before. `run.py` needed no change: `_format_left` already labels the phase from the row's unit and computes the time from the row's progress and recent rate.

```diff
-    recent_slice = counting[-DEFAULTS["typical_beats"]:] if counting else []
-    avg_rate, recent_rate = rates(counting[0] if counting else None, recent_slice)
+    unit_now = counting[-1].get("unit") if counting else None
+    phase_counting = [b for b in counting if b.get("unit") == unit_now]
+    recent_slice = phase_counting[-DEFAULTS["typical_beats"]:]
+    avg_rate, recent_rate = rates(phase_counting[0] if phase_counting else None, recent_slice)
```

`jobs/registry.py` is in no stage's code set (`schema.code_files` names no `jobs/` module), so no `jobs/versions.yaml` row is needed.

Test: new case `LsLineTest.test_prediction_phase_rate_is_read_from_its_own_beats` in `tests/test_registry_concurrent_append.py`. It writes a trainer-shaped heartbeat file into a temporary run directory (21 step beats up to 1000/1000 ten seconds apart, five `validate` touches, the closing step beat, then prediction beats 0..3 of 8 a minute apart), reads it through `registry._judge_pieces` and prints the line through the real `run.py`'s `_format_ls_row`. It checks: the training rate is 5.0 steps/s at the end of the step beats; at the first prediction beat the rate is `None` and the line prints `left=-`; at 3/8 the recent and average rates are both 1/60 splits/s and the line prints `left=0h05 (prediction)`. Against the unfixed `jobs/registry.py` this case fails (the 3/8 recent rate is `None`):

```
$ git checkout jobs/registry.py   # the unfixed file, then the fix re-applied after the run
$ /home/y-guo/reproduce/new1/external/probe-env/bin/python tests/test_registry_concurrent_append.py LsLineTest
ERROR: test_prediction_phase_rate_is_read_from_its_own_beats (__main__.LsLineTest.test_prediction_phase_rate_is_read_from_its_own_beats)
...
    self.assertAlmostEqual(pv["recent_rate"], 1 / 60)
TypeError: unsupported operand type(s) for -: 'NoneType' and 'float'
Ran 5 tests in 0.351s
FAILED (errors=1)
```

README: the `jobs/registry.py` line's verdicts clause gains "a piece's rates are read over its counting beats in the newest beat's unit, so a train piece's prediction pass has a rate of its own"; the `tests/` line names the new case. The test module docstring and the `LsLineTest` docstring name it too.

Contracts note: the contracts table row for `rates(first_beat, recent_beats)` says "done per second, over the whole run and over the last 10 beats". `rates()` itself is unchanged; what `_piece_verdict_dict` passes it is now the current unit's beats, so for a train piece "the whole run" reads as "the whole current phase". The contracts are the owner's file under `notes/` and were not edited.

### Verification (fix round 1)

All from the worktree with the main repo's interpreter, on yebis.

```
$ /home/y-guo/reproduce/new1/external/probe-env/bin/python tests/test_registry_concurrent_append.py
.....................
----------------------------------------------------------------------
Ran 21 tests in 0.735s

OK
```

```
$ /home/y-guo/reproduce/new1/external/probe-env/bin/python run.py selfcheck
selfcheck: 32 python files, 0 problems
```

The other CPU test modules, each in its own process:

```
== test_settings_keys
Ran 25 tests in 23.992s
OK
== test_probe_input
Ran 19 tests in 1.968s
OK
== test_record_formats
Ran 16 tests in 0.090s
OK
== test_probe_eval
Ran 15 tests in 1.984s
OK
== test_environment_and_build
Ran 22 tests in 0.071s
OK
== test_qwen3_family
Ran 13 tests in 27.194s
OK
```

`tests/test_packed_loss.py` covers nothing this round changed and was not run.

### Commit (fix round 1)

- `ab0f602` T05: a piece's rates are read over its counting beats in the newest beat's unit, so a train run's prediction phase prints left=<h>h<mm> (prediction) (jobs/registry.py `_piece_verdict_dict`, README lines of jobs/registry.py and tests/, the new LsLineTest case)

### Self-review (fix round 1)

- The second bullet of section 4 above (the mixed window at the phase switch) is resolved by this fix: the window never mixes units now.
- `judge`'s `slowed` test now compares the recent and average rates within the current phase. Before, during the prediction phase both rates were `None` (the average's first beat was the first step beat, `done` 0, which made the average defined but the recent rate `None`), so `slowed` could not fire there; now it can, on the prediction phase's own rates.
- The first prediction beat still prints `left=-`, since one beat gives no rate. With `predict_total` of 2 the line shows a time only at 1/2.
