# T11: Two queued launchers wired to registration (11-board-launchers) report

Ticket: `.scratch/gpu-monitor-launch/issues/11-board-launchers.md`
Requirement detail source: the ticket points to implementation plan `docs/plans/2026-08-08-gpu-monitor-launch.md`
Task 13 (lines 896-916).
Worktree: `/home/y-guo/reproduce/new1-wt/20260808-par-T11`,
branch `ticket/20260808-par/T11`.

## What was done

Against the ticket's four requirements one by one:

1. **Local tmux helper functions deleted and replaced with imports**: `ops/launch_probe.py` (originally
   `:47-62`) and `ops/launch_eval.py` (originally `:62-77`) each had their own `has_session`/
   `launch` local functions, plus the module-level `LOCAL`/`ALIAS` computation serving them, all deleted,
   replaced with `from launch_common import has_session, tmux_launch, probe_free,
   register_all`. Both files' original call sites for `launch()` (inside `main()`'s launch
   loop) were changed to a new `launch_and_register(...)` function, which assembles the inner command
   internally before calling `tmux_launch`. The inner template is exactly the same as before
   (`cd <wd> && CUDA_VISIBLE_DEVICES=<g> <cmd> 2>&1 | tee <log>`), and the
   `has_session` existence check's `SKIP (exists)` behavior is kept as-is.

2. **FREE probe before each cell launches**: `launch_and_register` calls `probe_free(host, str(gpu))`
   after `has_session` passes and before actually calling `tmux_launch`;
   non-FREE only prints the reason and `return False`, skipping this one cell (`SKIP (non-FREE):
   <sess>  <host> gpu<g>  <why>`), not rejecting the whole batch. A half-empty
   queue table is common, differing from `run.py launch`'s single-task "reject the whole batch" convention;
   this difference is written into the `launch_and_register` docstring.

3. **Auto-registration into the ledger and record after each cell launches**: after `tmux_launch`
   succeeds and `append_runmeta` finishes writing as before, `launch_and_register` assembles a rich piece
   (nine fields: `host/gpus/session/log/cmd/launched_at/kind/stall_line/escalate_line`,
   `stall_line`/`escalate_line` both passed as `None`. The two queued launchers don't
   support overriding the verdict lines per cell, and the ticket's original text doesn't require it either), then calls
   `register_all(rid, str(WD), [piece], track, cmd_display, outdir=None)`.
   `outdir=None` because the RUNMETA step is already handled separately by `append_runmeta` earlier;
   the ticket's original text explicitly states "pass `outdir=None` for the RUNMETA step to skip it, don't write it twice."
   `track` differs between the two files: `launch_probe` uses `f"probe_{batch}"`,
   `launch_eval` uses `f"eval_{batch}"`. `launch_eval`'s `rid`, per the ticket's original text
   "session with the `eval_` prefix stripped, `{batch}_{model}_{cell}`," takes
   `sess[len("eval_"):]`. When `register_all` raises `SystemExit` (e.g. hitting a duplicate
   `run_id`, or `record.py start` internally rejecting), only `WARN registration failed(<rid>):
   <e>` is printed without re-raising. The tmux cell has really already been launched, and a registration failure must not
   hide an already-launched task from alive checks; the ticket's original text explicitly states this convention: "print WARN and keep
   going, don't abort the launch loop."

4. **Each script's own guardrail left untouched**: `launch_probe.py`'s queue table parsing (`build()`) and
   smoke mode (the four-cell zip of `--model`/`--host`/`--gpus`) logic wasn't changed a single character;
   `launch_eval.py`'s dependency-order hard check (checking `dep_run/
   REPLAY_REPORT.json` before launching a call-stage) and training-artifact existence check (the `run/best`
   directory) logic wasn't changed a single character.
   `git diff` shows `build()` doesn't appear in the change scope at all.

`kind` field: `launch_probe` passes `"train"`, `launch_eval` passes
`f"eval_{stage}"` (`eval_tool`/`eval_call`), matching the values the two files' original
`append_runmeta(..., kind=...)` calls already used; `verdicts.judge()` only special-cases
`kind=="service"`, everything else goes through the batch verdict path, and neither of these two values is
`"service"`, so this doesn't affect verdicts.

The same commit updated the two `MAP.md` lines for `ops/launch_probe.py`/`ops/launch_eval.py`,
noting they now go through `launch_common` and auto-register. The `run.py` registry wasn't touched.
neither file's CLI signature, the `launch-probe`/`launch-eval` task entries, nor the dry-run output
format changed at all; `run.py`'s descriptions of these two tasks are still accurate.

## How it was verified

New `tests/test_launch_probe.py` (4 cases), `tests/test_launch_eval.py`
(4 cases), covering the four boundary paths of the new `launch_and_register`: session already exists,
skip; target card non-FREE, skip; normal launch and registration with all rich piece fields; registration throws
`SystemExit`, only WARN without aborting (and the launch is still reported as successful, returning `True`).

```
python3 -m unittest tests.test_launch_probe tests.test_launch_eval -v
```

Output (tail):

```
test_launches_and_registers_rich_piece (tests.test_launch_probe.TestLaunchAndRegister) ... ok
test_register_failure_warns_but_launch_still_reported (tests.test_launch_probe.TestLaunchAndRegister) ... ok
test_skips_when_gpu_not_free (tests.test_launch_probe.TestLaunchAndRegister) ... ok
test_skips_when_session_exists (tests.test_launch_probe.TestLaunchAndRegister) ... ok
test_launches_and_registers_rich_piece_rid_strips_eval_prefix (tests.test_launch_eval.TestLaunchAndRegister) ... ok
test_register_failure_warns_but_launch_still_reported (tests.test_launch_eval.TestLaunchAndRegister) ... ok
test_skips_when_gpu_not_free (tests.test_launch_eval.TestLaunchAndRegister) ... ok
test_skips_when_session_exists (tests.test_launch_eval.TestLaunchAndRegister) ... ok

Ran 8 tests in 0.007s

OK
```

Full suite:

```
python3 -m unittest discover -s tests -v
```

37 tests all green (including `test_heartbeat.py`/`test_verdicts.py`/`test_launch_common.py`, written before T01/T02/T03/T08;
this worktree has no other parallel ticket's test files yet). `ops/jobs.json`/`RESULTS.md`
weren't touched (`git status --porcelain` shows only the 5 files I changed).

The ticket's acceptance item "both launchers dry-run as usual": `pipeline/data/` doesn't
exist in this worktree (not a regression, `pipeline/data/` was never in git, it's an NFS-hosted big
artifact; `/home/y-guo/reproduce/new1` also has no ready-made `pipeline/data/`. Checked and
genuinely couldn't find any already-collected data batch to use directly, not caused by worktree isolation), so a fake data directory
(`mkdir -p /tmp/.../q35`) + fake training-artifact directory (`mkdir -p pipeline/runs/zz_q35_mtool/best`, deleted
right after the run) were built under `/tmp` to walk through both dry-run commands, confirming CLI parsing,
`build()`, and the dry-run print path weren't broken after replacing the local `has_session`/
`launch` with imports:

```
python3 run.py launch-probe smoke --batch zz --data-root /tmp/t11_smoke_data \
    --env appworld --model q35 --dry-run --allow-dirty
```
```
[launch-probe] cwd=.../new1-wt/20260808-par-T11
  python3 .../ops/launch_probe.py smoke --batch zz --data-root /tmp/t11_smoke_data --env appworld --model q35 --dry-run
[dry-run] tokyo107 gpu0 new1_zz_q35_mtool_smoke_t107g0
    .../mbert-env/bin/python .../pipeline/train/train_mbert_tool.py --data /tmp/t11_smoke_data/q35 --out .../pipeline/runs/smoke/zz_q35_mtool_smoke --env appworld --smoke
(three more cells like this)
4 cells total (dry-run, not launched)
```

```
python3 run.py launch-eval tool --batch zz --data-root /tmp/t11_smoke_eval_data \
    --env appworld --placement /tmp/t11_eval_placement.json --dry-run --allow-dirty
```
```
[launch-eval] cwd=.../new1-wt/20260808-par-T11
  python3 .../ops/launch_eval.py tool --batch zz --data-root /tmp/t11_smoke_eval_data --env appworld --placement /tmp/t11_eval_placement.json --dry-run
[dry-run] tokyo106 gpu0 eval_zz_q35_mtool
    .../mbert-env/bin/python .../pipeline/eval/eval_tool.py --env appworld --run .../pipeline/runs/zz_q35_mtool --data /tmp/t11_smoke_eval_data/q35 --head mbert
1 cell total (dry-run, not launched)
```

Both commands return directly in the dry-run branch, without touching `probe_free`/`tmux_launch`/
`register_all`, consistent with the ticket's "dry-run as usual" requirement (the dry-run logic itself wasn't touched at all this time).

`run.py selfcheck` in this worktree reports `16 missing`, all
`envs/*/venv`, `mbert-env`, `cprobe-env` and similar interpreter paths missing.
Running the same command in the main repo `/home/y-guo/reproduce/new1` (same HEAD before, without my changes)
gives `63 tasks / 4 recipes, all present`; the comparison confirms these 16 missing items are a worktree-isolation
limitation caused by `git worktree add` not bringing over untracked files (venv directories are entirely excluded from git),
unrelated to this ticket's code changes; `launch-probe`/`launch-eval`
themselves are not in the missing list.

## Commit list

- `1d1d84b`: `T11: queued launchers wired to launch_common(FREE probe + auto ledger/record, RUNMETA unchanged)`
  (`ops/launch_probe.py`, `ops/launch_eval.py`, `MAP.md` changes,
  `tests/test_launch_probe.py`, `tests/test_launch_eval.py` new)

## Self-check findings and open questions

1. **`register_all`'s `workdir` argument was passed `str(WD)` (the repo root)**: the ticket's original
   text doesn't name what this argument should be. Both launchers' inner commands are
   `cd {WD} && ...`, so the process's real cwd is the repo root; I judged passing `str(WD)` to be
   the choice that honestly reflects reality; comparing against the ledger's historical record
   (`ops/jobs.json`'s `history`'s `hcap` job has its own `workdir` set to its own artifact
   directory, not the repo root), the "workdir" field's semantics aren't fully consistent across different
   launch paths already (some fill in the artifact directory, some fill in the process cwd), this ticket does not require
   unifying this, and I did not touch this existing inconsistency, just picked "the process's real
   cwd" as the interpretation for these two newly-wired launch paths. Judged to be a safe call, not affecting any
   test assertion or acceptance item.

2. **`stall_line`/`escalate_line` are fixed to `None`**: neither the ticket's original text nor implementation plan
   Task 13 mention that these two queued launchers should support per-cell overrides of the verdict/escalate
   line (that is `run.py launch`'s capability, ticket 09, whose signature has
   `--stall-line`/`--escalate-line`). I fixed them at `None`, letting the sampler fall back to
   `verdicts.DEFAULTS`'s adaptive verdict lines. If these two launchers need override capability added
   later, that needs a separate ticket, not within this one's scope.

3. For the two test files added to cover the boundary, `test_launches_and_registers_rich_piece`
   (launch_probe) uses an exact string match to assert the inner command received by `tmux_launch`,
   binding it to the specific format `f"cd {WD} && CUDA_VISIBLE_DEVICES={gpu} {cmd}
   2>&1 | tee {log}"`; if this template is ever changed, this test would break with it. This is
   deliberate (the template is the direct embodiment of the acceptance requirement "inner template unchanged, behavior unchanged," worth
   pinning down).

No stylistic inconsistency needing a fix was found; `launch_and_register`'s
docstring style and the `WARN`-prefix printing convention both copy `launch_common.register_all` and
both files' original `append_runmeta` failure-handling style. `shlex` is still used in
`build()`/`cell_cmd_parts()` in both files; `subprocess` is no longer needed
(probing/tmux all handed off to `launch_common`), and `import subprocess` was removed.

---

## Fix round 1 (F1)

Worktree: `/home/y-guo/reproduce/new1-wt/20260808-par-T11-fix1`,
same branch `ticket/20260808-par/T11` (checked out the existing branch, not newly created).

### F1 (critical): launch-eval's run_id is exactly the same name as launch-probe's, so under the standard flow register_all is bound to collide

**Problem pointed out by review**: `ops/launch_eval.py:86` originally had `rid = sess[len("eval_"):]`,
with `sess = f"eval_{batch}_{model}_{cell}"`. Stripping the `eval_` prefix leaves it equal to
`f"{batch}_{model}_{cell}"`, character-for-character the same as the `rid` `ops/launch_probe.py`'s
`build()` uses for the same training-job cell (`f"{batch}_{model}_{cell}"`). `register_all`'s
de-dup check (`ops/launch_common.py`'s `if any(j["name"]==run_id for j in
reg["active"])`) only looks at `jobs.json`'s `active` list; a training job only leaves
`active` when `gpu_jobs finish` deregisters it. Per `probe-pipeline/SKILL.md`,
deregistration comes at Phase D (wrap-up), explicitly after C4's evaluation (C4's section
says explicitly: "no need to wait for the whole training batch to wrap up, wrap up each cell as it finishes and dispatch its eval").
Under the standard flow, when `launch-eval` calls
`register_all`, the same-named training job is almost always still in `active`, and `register_all` will
`sys.exit(f"run_id {run_id} already in ledger…")`, which gets swallowed by `launch_and_register`'s
`except SystemExit` into one WARN line. The tmux eval task still gets launched as usual, but from start to finish it
has no ledger entry, and no `record.py` record either.

**A layer deepened by further review**: after tracing into `ops/record.py`, the problem turns out to be even
more serious than the review's description. `record.py start` (step 2 of `register_all`) itself has its own
independent duplicate check (`record.py:237-238` `if ev["run_id"] in load(): sys.exit(...)`).
`load()` folds `runs.jsonl`'s entire history of events by `run_id`; `finish` just
appends another `finish` event into the event stream, it does not remove the `run_id` from
`load()`'s return value. In other words, even if the training job has already been
`finish`-deregistered in `jobs.json` (avoiding the review's described first-layer collision), as long as
this `run_id` was ever `start`-ed in `record.py`, `record.py start` itself will collide again,
independently of `jobs.json`'s `active`-list state. The `rid = sess[len("eval_"):]`
pattern collides under **any** train/eval timing, not just "almost always collides under the standard flow."

**Fix**: changed `rid = sess[len("eval_"):]` to `rid = sess` (not stripping the
`eval_` prefix). The reasons for choosing this fix over inventing a whole new encoding scheme:
1. Structurally can no longer collide with the training rid. The training rid is `x = f"{batch}_{model}_{cell}"`,
   the eval rid is now `f"eval_{x}"`, and `"eval_" + x == x` has no solution for any non-empty
   `x`; this doesn't depend on the specific values of `batch`/`model`/`cell`, it's a
   structural guarantee, not a "usually won't happen."
2. There's historical precedent: `ops/gpu_jobs.py`'s `cmd_finish` has an audit comment,
   "guard against premature deregistration (audit instance eval_c2_q36_mtool 16:52 deregistered,
   actually ran until 18:17)", showing that historically, the real eval job name genuinely registered in the ledger in this
   project was the full session name with the `eval_` prefix, not the prefix-stripped version. Changing to
   `rid = sess` returns to this already-verified precedent, it doesn't invent a new rule.
3. No downstream code depends on the convention "the eval rid equals the training rid with the prefix stripped". Searched
   all `eval_`-related strings across `ops/*.py`, `run.py`, `tests/*.py`, and
   found nowhere assuming this kind of correspondence between the two.

`docs/plans/2026-08-08-gpu-monitor-launch.md` Task 13 Step 2's original text is exactly
"rid takes session with the eval_ prefix stripped, `{batch}_{model}_{cell}`". This collision is a flaw
carried by the plan text itself; the previous round's implementer followed it faithfully, it isn't an implementation deviating from the
plan. This fix did not revise that plan document (out of this ticket's scope, and this part of Task 13
has already finished executing, with no follow-up ticket needing to read this step to re-execute it).

**Files changed**:
- `ops/launch_eval.py`: `rid = sess[len("eval_"):]` → `rid = sess`, with a comment added
  explaining why the prefix must not be stripped (three points: the collision mechanism + structural guarantee + historical precedent).
- `tests/test_launch_eval.py`: test name changed from
  `test_launches_and_registers_rich_piece_rid_strips_eval_prefix` to
  `test_launches_and_registers_rich_piece_rid_keeps_eval_prefix`; assertion changed from
  `self.assertEqual(run_id, "c2_q36_mtool")` to
  `self.assertEqual(run_id, "eval_c2_q36_mtool")` with a line added,
  `self.assertNotEqual(run_id, "c2_q36_mtool")`, pinning down "must not equal the training rid" as an
  explicit assertion; the file header docstring's wording was updated to match.
- `MAP.md`: `ops/launch_eval.py`'s line, "run_id takes the session with the `eval_`
  prefix stripped," changed to "run_id = session as-is, prefix not stripped," with a sentence added on the collision reason.

### Verification

```
python3 -m unittest tests.test_launch_probe tests.test_launch_eval -v
```

Tail output:

```
test_launches_and_registers_rich_piece (tests.test_launch_probe.TestLaunchAndRegister) ... ok
test_register_failure_warns_but_launch_still_reported (tests.test_launch_probe.TestLaunchAndRegister) ... ok
test_skips_when_gpu_not_free (tests.test_launch_probe.TestLaunchAndRegister) ... ok
test_skips_when_session_exists (tests.test_launch_probe.TestLaunchAndRegister) ... ok
test_launches_and_registers_rich_piece_rid_keeps_eval_prefix (tests.test_launch_eval.TestLaunchAndRegister) ... ok
test_register_failure_warns_but_launch_still_reported (tests.test_launch_eval.TestLaunchAndRegister) ... ok
test_skips_when_gpu_not_free (tests.test_launch_eval.TestLaunchAndRegister) ... ok
test_skips_when_session_exists (tests.test_launch_eval.TestLaunchAndRegister) ... ok

Ran 8 tests in 0.007s

OK
```

The launch-simulation print now shows the fix in effect. The WARN line now carries the full prefixed name:

```
WARN registration failed(eval_c2_q36_mtool): run_id already in ledger
```

(before the fix, this line would print `WARN registration failed(c2_q36_mtool): ...`, which is
exactly the string that collided with the training rid.)

Full suite:

```
python3 -m unittest discover -s tests -v
```

37 tests all green, same count as before the change (this round added no new test file, only changed one
existing assertion + a test name).

```
python3 run.py selfcheck
```

`62 tasks / 4 recipes, 16 missing`. The 16 missing items are all `envs/*/venv`,
`mbert-env`, `cprobe-env` and similar interpreter paths, consistent with what the previous round's report recorded
(`git worktree add` doesn't bring over untracked venv directories, caused by worktree isolation, unrelated to
this round's code change); `launch-probe`/`launch-eval` themselves are not in the missing list.

The dry-run path wasn't re-run this round: F1's change only touches the single `rid` assignment line inside
`launch_and_register`; `build()`/`main()`'s dry-run branch (returns directly when
`args.dry_run` is true, without entering `launch_and_register`) was never touched by this line of code at all,
so the previous round's report's two dry-run command outputs still faithfully reflect the current code's dry-run behavior;
`launch_and_register` itself's four paths are covered directly by the unit tests above (including the newly
changed `rid` assertion), judged unnecessary to re-run a real CLI dry-run to confirm.

### Commit list (this round)

- `b49705b`: `T11: fix eval rid colliding with training rid (F1), eval rid keeps the eval_ prefix, doesn't strip it`
  (`ops/launch_eval.py`, `tests/test_launch_eval.py`, `MAP.md`)

### Self-check findings and open questions (this round)

No new problems found. This round's change only involves one assignment statement + the corresponding
test assertion + two lines of documentation wording, without touching the other two open questions recorded in the previous
round's report (`workdir` passed `str(WD)`, `stall_line`/`escalate_line` fixed to
`None`). They're not in this finding's scope, kept as-is per the instruction "fix items one by one, no
scope-widening refactor."
