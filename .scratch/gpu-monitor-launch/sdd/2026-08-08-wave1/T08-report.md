# T08: Launch commons (08-launch-common) report

Ticket: `.scratch/gpu-monitor-launch/issues/08-launch-common.md`
Requirement detail source: the ticket does not cite spec; per the ticket's instruction, read the implementation plan
`docs/plans/2026-08-08-gpu-monitor-launch.md` Task 10 (lines 797-818).
Worktree: `/home/y-guo/reproduce/new1-wt/20260808-par-T08`, branch `ticket/20260808-par/T08`.

## What was done

New `ops/launch_common.py`, implementing the ticket's three capabilities one by one:

1. **Probe free `probe_free(host, gpus)`**: `ssh <host> nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader -i <gpus>`.
   Non-empty stdout → `(False, "occupied: <first line>")`; ssh timeout/`OSError`/nonzero exit →
   `(False, "probe failed: ...")`; empty stdout → `(True, "")`. Fail-closed: probe
   failure and occupied both return non-FREE the same way.

2. **tmux launch template**: `ALIAS = {"shiga": "tokyo105", "saitama": "tokyo108"}`
   copied as-is; `local_host()` (changed from `launch_probe.py`'s original module-level constant `LOCAL` into a
   function computed on demand, for easier test monkeypatching, with no behavior change. Both are computed by
   folding `hostname` through ALIAS); `has_session(host, s)` and `tmux_launch(host, sess, inner_cmd)` are consistent with the
   logic at `launch_probe.py:47-62` (locally goes through `bash -c`, remotely goes through
   `ssh -n host`; `tmux_launch`'s inner template matches the caller-assembled
   `cd <wd> && CUDA_VISIBLE_DEVICES=<g> <cmd> 2>&1 | tee <log>`).
   One difference from `launch_probe.py`'s original `launch()`: `tmux_launch` does not do the
   "skip if session already exists" check. That is the caller's (launch_cmd / the queued launchers)
   business, which tickets 09/11 will each handle; this ticket does not change any existing launcher's
   behavior, `launch_probe.py`/`launch_eval.py` are left unchanged.

3. **`register_all(run_id, workdir, pieces, track, cmd_display, note=None, outdir=None, monitor=None)`**:
   the three registrations, in fixed order (ledger→record→RUNMETA), without swallowing exceptions:
   - Ledger: in `gpu_jobs.mutate_reg`, if `reg["active"]` already has a job with the same name (`name==run_id`)
     it calls `sys.exit` (duplicate run_id rejected, checked inside the lock, a guard rail); otherwise appends
     `{"name","workdir","note","started_at","pieces"}`, with `pieces` being the caller's own rich piece list passed in
     as-is (not reconstructed with new fields); `monitor` is only written into the job when
     it is not `None` (avoiding a downstream `job.get("monitor",{}).get("warmup_s")`
     erroring when `monitor` is explicitly `None` (the key exists but its value isn't a dict). This is a safety
     boundary I added myself; the ticket's original text does not say this, see "Self-check findings" below).
   - Record: `subprocess.run([sys.executable, OPS/"record.py", "start", "--run-id", run_id, "--track", track, "--cmd", cmd_display, "--host", ..., "--gpu", ..., "--log", ...])`,
     with the host/gpus/log for multiple pieces each comma-joined into one display string passed to these three arguments (the ticket's original
     text only wrote "..." without saying how to join them for multiple pieces. This is a ruling I made, see "Self-check
     findings" below); does not `capture_output`, letting `record.py`'s own error print directly to the terminal;
     `rc != 0` → `sys.exit(rc)` passed through as-is and aborts.
   - RUNMETA: only when `outdir` is given does it call `runmeta.append_runmeta(outdir, cmd_display, kind="launch")`;
     if not given, prints and includes a line in the receipt, `WARN --outdir not given, RUNMETA was not written`.
   - Returns three lines of receipt text (ledger/record/RUNMETA each one line).

The same commit also updated `MAP.md`: adding a line for `ops/launch_common.py` in the
"ledger and launch tools" table (placed between `ops/jobs.json` and `ops/launch_probe.py`). Did not touch
`run.py`'s registry. `launch_common.py` itself is not a runnable task, it's a library for
ticket 09 (`run.py launch`) and ticket 11 (the two queued launchers); the ticket's original text explicitly stated
"this one does not change any existing launcher's behavior."

## How it was verified

Wrote `tests/test_launch_common.py`, 14 cases, covering the ticket's two acceptance requirements plus
the basic behavior of `local_host`/`has_session`/`tmux_launch`:

- `TestProbeFree`: empty stdout / has a process line / `subprocess.TimeoutExpired` /
  nonzero rc, four kinds of input (the three named by the ticket plus one I added for nonzero rc, reason
  in "Self-check findings" below) each mapping to a corresponding return value.
- `TestRegisterAll`: `test_ledger_gets_rich_piece_full_fields` asserts the ledger's
  `pieces[0]` has all nine fields `host/gpus/session/log/cmd/launched_at/kind/stall_line/escalate_line`;
  `test_duplicate_run_id_rejected_on_second_call` asserts that calling `register_all` a second time with the same
  `run_id` raises `SystemExit`, and the ledger still has only one entry;
  also added `test_no_monitor_key_when_not_given` (when `monitor` isn't given, the ledger has no such
  key), `test_record_failure_aborts_but_ledger_already_written`
  (when `record.py` is mocked to rc=1, `register_all` raises, but the ledger step has already landed),
  and `test_outdir_given_writes_runmeta` / `test_no_outdir_warns_instead_of_writing`.
  `monkeypatch gpu_jobs.REG_PATH` points the ledger at a tmp file to isolate it (the ticket's original written pattern).
- `TestLocalAndSession`: `local_host` folded through ALIAS, and one case each for
  `has_session`/`tmux_launch` going through `bash` locally / `ssh` remotely.

Run:

```
python3 -m unittest tests.test_launch_common -v
```

Output (tail):

```
test_has_session_local_uses_bash (tests.test_launch_common.TestLocalAndSession) ... ok
test_has_session_remote_uses_ssh (tests.test_launch_common.TestLocalAndSession) ... ok
test_local_host_applies_alias (tests.test_launch_common.TestLocalAndSession) ... ok
test_tmux_launch_builds_new_session_cmd (tests.test_launch_common.TestLocalAndSession) ... ok
test_free_when_stdout_empty (tests.test_launch_common.TestProbeFree) ... ok
test_occupied_when_stdout_has_process (tests.test_launch_common.TestProbeFree) ... ok
test_probe_fails_on_nonzero_rc (tests.test_launch_common.TestProbeFree) ... ok
test_probe_fails_on_timeout (tests.test_launch_common.TestProbeFree) ... ok
test_duplicate_run_id_rejected_on_second_call (tests.test_launch_common.TestRegisterAll) ... ok
test_ledger_gets_rich_piece_full_fields (tests.test_launch_common.TestRegisterAll) ... ok
test_no_monitor_key_when_not_given (tests.test_launch_common.TestRegisterAll) ... ok
test_no_outdir_warns_instead_of_writing (tests.test_launch_common.TestRegisterAll) ... ok
test_outdir_given_writes_runmeta (tests.test_launch_common.TestRegisterAll) ... ok
test_record_failure_aborts_but_ledger_already_written (tests.test_launch_common.TestRegisterAll) ... ok

Ran 14 tests in 0.157s

OK
```

Then ran the whole suite:

```
python3 -m unittest discover -s tests -v
```

29 tests (including `test_heartbeat.py`/`test_verdicts.py` written before T01) all green,
`ops/jobs.json`/`RESULTS.md` untouched (confirmed with `git status --porcelain`).

Ran `run.py selfcheck` once (no registry change, not a hard requirement, just confirming no new problem introduced):
output `62 tasks / 4 recipes, 16 missing`, the 16 lines all being missing envs/
venv/interpreters in this worktree (things like `envs/appworld/venv/bin/python`), which is a gap in this
worktree's own environment, unrelated to this ticket's changes. `launch_common.py`/anything related to it
is not in the missing list (because it never went into the registry at all).

## Commit list

- `c55e47a`: `T08: launch commons ops/launch_common.py(fail-closed probe/tmux template/three registrations in one go)`
  (`ops/launch_common.py` new, `tests/test_launch_common.py` new,
  `MAP.md` one line added)

## Self-check findings and open questions

The ticket's original description of `register_all` left two details unspecified, ruled on myself under the
"safe to decide" standard, noted here for reviewer cross-check:

1. **Whether the ledger job should write a `monitor` key when `monitor` is `None`**: the ticket writes
   "job-level `monitor={"warmup_s":...}`," without saying what to do when `monitor` isn't given.
   Another part of the implementation plan (Task 6, sampler, line 698) writes the consuming side's logic:
   `warmup_s` is taken from `job.get("monitor", {}).get("warmup_s")`, falling back to
   `verdicts.DEFAULTS` when absent. If `register_all` still writes
   `job["monitor"] = None` when `monitor=None`, the consuming side's `job.get("monitor", {})` would return
   `None` because the key exists (it would not fall back to `{}`), and then calling `.get("warmup_s")`
   on it would report `AttributeError`. I judged this to be a pitfall that was safe to rule on myself, choosing
   "don't write this key when `monitor` is `None`," pinned down with
   `test_no_monitor_key_when_not_given`. **This is not on the ticket's acceptance checklist and is worth confirming
   when ticket 09 (`run.py launch`) lands, to check whether it will pass a non-empty `monitor` dict.**

2. **How to fill `record.py start`'s `--host`/`--gpu`/`--log` when there are multiple pieces**:
   `record.py`'s `cmd_start` takes only a single string value per argument, but
   `register_all`'s `pieces` is a list (ticket 09's sharding scenario can be multiple
   host:gpu per launch). The ticket's original text only wrote "`--host`, ..., `--gpu`, ..., `--log`, ...," without
   giving the join format for multiple pieces. I chose to join each piece's
   `host`/`gpus`/`log` with commas into one string (something like `"tokyo106,tokyo107"`). This field is
   only for display in `RESULTS.md`, doesn't affect any other field in the record system, and is low
   risk, so I judged it safe to decide on my own; but the join format itself has no test asserting the exact value
   (only that `subprocess.run` was called and the `rc==0` path was normal), **when ticket 09 lands
   and actually produces a multi-piece call, it's worth eyeballing what this line looks like in `RESULTS.md`,
   to see whether a more readable format is needed.**

3. `probe_free` covers one input not named by the ticket (the ssh command itself has a nonzero rc but no timeout,
   and stdout is also empty, e.g. a remote `nvidia-smi` error or the host key being refused): under
   fail-closed principles, this is also judged "probe failed." The ticket's acceptance checklist wrote "empty card,
   occupied, probe timeout, three kinds of input"; I tested one extra kind, without touching the three original
   assertions, and I consider this necessary added coverage, not YAGNI (it's another branch of the same
   function, not extra functionality).

No stylistic inconsistency was found needing fixing; `has_session`/`tmux_launch`/`local_host`'s
ssh/bash branching matches `ops/launch_probe.py:47-62` (local
`bash -c`, remote `ssh -n host`).
