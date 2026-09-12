# T02: Sampler single round runs end to end, three files land on disk

Ticket: `.scratch/gpu-monitor-launch/issues/02-sampler-once.md`
Requirement source: `docs/plans/2026-08-08-gpu-monitor-launch.md` Task 6 (sampler core `ops/sampler.py`).
Design source: `docs/design/2026-08-08-gpu-monitor-launch.md` §3 (sampler) §4 (verdict).
The ticket does not directly cite any section of spec.md; spec.md was not read.

Worktree: `/home/y-guo/reproduce/new1-wt/20260808-par-T02`, branch `ticket/20260808-par/T02`,
base commit `5be5d0827fe959cc1c016c8f99221c4d6a4218c8`.

## What was done (against the ticket's four acceptance items)

1. **Sampler tests pass: two pieces in a fake ledger (one alive, one dead), the alive one verdicts healthy or warming up, the dead one verdicts dead, the cumulative token count reads correctly**
   - New `ops/sampler.py`: `sample_once()` reads the ledger's active list, `read_beats()` tails the log to pick up heartbeats, `live_sessions()` probes tmux liveness, `update_piece_state()` accumulates state, `build_row()` calls `ops/verdicts.py`'s `stall_line_s`/`rates`/`judge` to produce the verdict row.
   - Landed the test skeleton given in the ticket/plan as-is, `tests/test_sampler.py` (`TestSampleOnce.test_round`): two pieces, one with three heartbeats and a live session, one with only plain text and a session not in the alive set;
     asserts the alive piece's verdict is in {healthy, warming up}, the dead piece's verdict is dead, and `tok_in == 210` (the cumulative value from the last heartbeat).

2. **All three on-disk files appear and are json.load-able; sampling another round does not re-append heartbeats for an unchanged log**
   - `latest.json`/`state.json`/`history/<job>.jsonl` are written with `atomic_write` (tmp + `os.replace`, same style as `run.py:save_state`) and `append_jsonl`; the `NEW1_MONITOR_DIR` environment variable can point the directory elsewhere. Added `test_files_are_valid_json`: all three files exist, `json.load` can read them, and each line of `history/x.jsonl` is independently valid JSON.
   - Heartbeat de-duplication: `update_piece_state` takes the last `(ts, done)` in `ps["recent_beats"]` as the baseline; only a strictly greater `(ts, done)` counts as a new heartbeat and gets appended. The second part of the ticket skeleton's `test_round` (sampling the same log again, `recent_beats` length unchanged) already covers this.
   - Refire (`launched_at` changed) reopens the whole state block and increments the `refires` count: a separate `test_refire_resets_state_and_counts` was added. Sample once first to confirm `refires == 0` and `recent_beats` length 3, then change `launched_at` and sample again, asserting `refires == 1` and `first_beat` is non-empty (the state really did reopen, not a leftover from history).

3. **`python3 run.py sampler --once` runs to completion on the real ledger without crashing**
   - Ran `python3 run.py sampler --once` in the worktree (without setting `NEW1_MONITOR_DIR`, going through the real NFS path), RC=0. At the time `ops/jobs.json`'s `active` list was empty, so this round actually exercised the path "empty ledger + real `live_sessions` cross-checking sessions outside the ledger": `live_sessions` really did ssh into tokyo105-108, and `extras` showed four unregistered tmux sessions on tokyo105 (`7-29run`/`7-31run`/`flow-8-1`/
     `rc-claude`, which belong to other conversations and are not this ticket's concern). The output landed at
     `/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/monitor/` (`latest.json`/
     `state.json`, content shown in the verification output below) and was not cleaned up. This is exactly where the sampler should write once deployed, and leaving it on disk is not a mess.

4. **`python3 run.py selfcheck` passes and is committed**
   - `run.py`'s `TASKS` got a `"sampler"` entry (`stage="ops", py="sys",
     script="ops/sampler.py"`, with three notes: how to start it as a daemon, where it writes to disk, and how to use `--once` for a smoke test), the wording matching the entry given in plan Task 6 Step 4 verbatim.
   - `MAP.md` got a line added for `ops/sampler.py`.
   - `selfcheck` cannot reach "all present" in this isolated worktree, see the explanation in the "Verification" section below; this is caused by the worktree itself missing venv directories, not a problem introduced by this ticket's changes (see "Self-check findings and open questions").

## How it was verified

```
$ python3 -m unittest tests.test_sampler tests.test_heartbeat tests.test_verdicts -v
test_unreachable_returns_false (tests.test_sampler.TestProbePort) ... ok
test_missing_log_returns_empty (tests.test_sampler.TestReadBeats) ... ok
test_reads_only_valid_heartbeat_lines (tests.test_sampler.TestReadBeats) ... ok
test_files_are_valid_json (tests.test_sampler.TestSampleOnce) ... ok
test_refire_resets_state_and_counts (tests.test_sampler.TestSampleOnce) ... ok
test_round (tests.test_sampler.TestSampleOnce) ... ok
(heartbeat 4 + verdicts 11 run together, all 21 ok)

Ran 21 tests in 0.043s

OK
```

Ran once before writing the tests to confirm it failed (`ModuleNotFoundError: No module named 'sampler'`); the implementation was added after all six cases were in place.

```
$ python3 run.py sampler --once
[sampler] cwd=/home/y-guo/reproduce/new1-wt/20260808-par-T02
  python3 /home/y-guo/reproduce/new1-wt/20260808-par-T02/ops/sampler.py --once
RC=0

$ cat /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/monitor/latest.json
{
 "sampled_at": 1786139885.1503584,
 "rows": [],
 "extras": {
  "tokyo105": [
   "7-29run",
   "7-31run",
   "flow-8-1",
   "rc-claude"
  ]
 },
 "incidents_tail": []
}
```

```
$ python3 run.py selfcheck
(last three lines)
missing cwd dir: .../envs/stabletoolbench/server  (task stb-virtual-server)
missing interpreter/program: .../envs/vllm-env/bin/python  (task build-token-walk)
selfcheck: 63 tasks / 4 recipes, 16 issues
```

For comparison, ran the same `run.py` in the main-repo worktree (`/home/y-guo/reproduce/new1`, read-only, no files changed):
`selfcheck: 62 tasks / 4 recipes, all present`. The only differences between the two are the task count 62→63 (this ticket's new
`sampler` entry) and the 16 "missing interpreter/missing script/missing cwd" lines. The 16 lines are all pointing at other tasks
(`collect-aw`/`collect-alf`/`toolhop-official`/`stb-virtual-server`/`build-token-walk` etc.), at their venv directories and
third-party scripts. Those directories are excluded from git per `.gitignore`, and an isolated worktree built with
`git worktree add` naturally does not have them. None of the 16 lines mentions `sampler`.

## Commit list

- `d7f3435`: T02: monitor: sampler core (collect heartbeats/probe liveness/verdict/write latest+state+history)+register the sampler task
  (`ops/sampler.py`, `tests/test_sampler.py`, `run.py`, `MAP.md`)

## Self-check findings and open questions

- **`selfcheck` reports 16 missing items in the isolated worktree; this is structural to the worktree, not introduced by this ticket**: these
  missing items all point at venv directories excluded by `.gitignore` (`envs/*/venv`, `cprobe-env`, `mbert-env`, etc.)
  and third-party scripts, which `git worktree add` does not carry over from the main repo's untracked directories. Confirmed
  by comparison (above): the same code run in the main-repo worktree gives selfcheck "all present", just with the task count 1 lower (not
  yet carrying `sampler`). The ticket requires "run selfcheck, pass, and commit"; this ticket cannot literally "pass" (rc=1) in its own
  isolated worktree, but that is an environment limitation of the ticket-run parallel execution protocol itself, unrelated to this
  ticket's code changes. After merging back to the main branch, selfcheck will return to "all present". This point is left for
  the main session to confirm at merge/settlement time.
- **Two necessary deviations from the `sample_once()`/`build_row()` skeleton given in the plan**, both noted in the
  commit message, expanded here again:
  1. In the plan skeleton, `sample_once()` directly calls `from gpu_jobs import load_reg`, but
     `gpu_jobs.load_reg()`'s function body reads `gpu_jobs`'s own module-level global `REG_PATH`, not the caller's. In the
     test skeleton given by the ticket/plan, the line `self.S.REG_PATH = str(self.jobs)` monkeypatches
     `sampler.REG_PATH` (an attribute of the sampler module itself), so this patch never touches `gpu_jobs.REG_PATH` at all;
     copying the skeleton as-is would make the test read the real `ops/jobs.json` instead of the fake ledger in the tmp
     directory. Changed `ops/sampler.py` to define its own `load_reg()` (4 lines, reading this module's own
     `REG_PATH`, defaulting to `gpu_jobs.REG_PATH`), so the monkeypatch works the way the test skeleton wrote it. `live_sessions` doesn't have
     this problem, it's a function name called directly, late-bound in `sampler.py`'s global namespace,
     so monkeypatching `sampler.live_sessions` naturally works without any change.
  2. In the plan skeleton, `build_row(job["name"], idx, piece, ps, now_mono)` only passes the job's name as a string, but
     the "key implementation constraints" section explicitly states that `warmup_s` should be taken from `job.get("monitor", {}).get("warmup_s")`
     The name alone cannot get at the `monitor` field. Changed `build_row` to receive the full job dict, taking
     `job["name"]` internally to fill the row's `"job"` field. This change does not affect any externally observable behavior (the tests only look at
     `latest["rows"]` and the on-disk file contents, not the function call signature).
   Both were judged to be cases where "the skeleton sample code itself conflicts with the prose description in the same plan document,
   requiring an on-the-spot pick", not "the ticket's requirement itself is ambiguous", so I did not stop to raise NEEDS_CONTEXT,
   and ruled on it myself following the prose description (the more detailed and explicit one).
- **Two implementation points fixed during self-check (not skeleton deviations, but two doubts I had while writing my own code)**:
  1. The `eta_s` calculation's "fall back to average rate when recent rate has no value" was originally written as `recent_rate if recent_rate else
     avg_rate`. When `recent_rate` happens to equal `0.0` (a genuine stall, but not yet past the stall line), the truthy check would
     mistake it for "no value" and quietly swap in the average rate, erasing the information that "the current rate is 0". Changed to an
     explicit `is not None` check.
  2. "10 consecutive rounds of probe failure" was originally an inline magic number `10`, changed to a module-level named constant
     `_PROBE_FAIL_ROUNDS_RED` (this threshold comes from the fixed text in design doc §4, "10 consecutive rounds", and does not belong
     in `ops/verdicts.py`'s `DEFAULTS`. That is the config surface for the pure-function verdict engine itself; the sampler's own constants
     should not be mixed into it, so it was not put into `verdicts.DEFAULTS`, and stays at module level in `sampler.py` instead).
- The persisted fields in `state.json` have three more keys than the schema listed in plan doc §3
  (`first_beat`/`recent_beats`/`last_new_beat_mono`/`last_done`/`launched_at`/`alive_last`/
  `probe_fail_rounds`/`port_ever_ok`/`port_fail_rounds`/`verdict`/`escalated_since_mono`/
  `incident_open`/`refires`): `last_total`/`last_unit`/`last_status`. These three
  are the resting place for the `total`/`unit` that the row output must have, and for `status` that `judge()` needs. The design doc's
  schema doesn't say where these should live, and each heartbeat's field list under `recent_beats` explicitly has no `total` (it lists
  `ts/done/tok_in/tok_out/loss/status`), so the only option was to open three more keys to store the most recent heartbeat's total/unit/
  status. The two keys `escalated_since_mono`/`incident_open` were created per the schema but only get default values (`None`/`False`) written
  when the state is created/reopened. This ticket left the logic of "when these two fields should be refreshed" unimplemented, per plan requirements: the design doc states
  these two fields are for Task 14 (ticket 12, incident triggering), and this ticket's sampler `maybe_trigger_incidents(rows,
  st)` was left as an empty function (`pass`) as planned, without touching any of the incident-verdict logic ahead of time.
- Service-kind pieces (`kind == "service"`) have port probing `probe_port()` implemented per the interface list in plan Task 6
  (HTTP GET `/health`, both exceptions and timeouts count as False), but ticket 02's acceptance criteria all target the
  `kind="batch"` two-piece scenario, and do not cover the service-kind end-to-end flow (that is ticket 13's vLLM service-ledger work). Only
  a unit test for `probe_port` itself was added (probing a local port that is bound to refuse connections, asserting it returns False), without another
  `kind="service"` integration test for `sample_once()`. The full service-kind scenario is left for ticket 13 to verify.
- `ops/jobs.json` was not touched (when this ticket ran `sampler --once`, the ledger's `active` was already an empty list, so
  this file was never written to, only read), nor were files owned by other tickets.
