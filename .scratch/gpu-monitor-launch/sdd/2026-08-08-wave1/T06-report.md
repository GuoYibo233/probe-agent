# T06 report: Web outlet and json outlet

Ticket: `.scratch/gpu-monitor-launch/issues/06-web-json-outlet.md`
spec section: `docs/plans/2026-08-08-gpu-monitor-launch.md` Task 7 (the ticket text directly names "steps follow implementation plan Task 7").
Branch: `ticket/20260808-par/T06`, worktree `/home/y-guo/reproduce/new1-wt/20260808-par-T06` (removed per protocol, branch kept).

## What was done

Against the ticket's three acceptance items:

1. **Web tests pass: /json matches the on-disk file, the root path returns 200 and its body contains the job name, verdict, and last sample time.**
   `ops/sampler.py` got a new `WebServer` class (internally starts an `http.server.ThreadingHTTPServer`);
   `_WebHandler.do_GET` branches on path:
   - `/json`: reads `monitor_dir/latest.json` fresh each time, sends it verbatim with
     `Content-Type: application/json`; if the file is missing/unreadable it returns 503 (this convention isn't named by the ticket for this branch. I picked 503 over pretending to return 200, on the principle of "say so when you can't read it").
   - `/` (and any other path): calls the pure function `render_html(latest)` to assemble the HTML, returns 200. The table columns are JOB/piece/HOST/GPU/verdict/progress/rate/token/ETA/SESSION; the banner at the top reads `Last sampled HH:MM:SS`; the incident-record block renders `latest["incidents_tail"]`; the out-of-ledger-session block renders `latest["extras"]`; `<meta http-equiv="refresh" content="30">` auto-refreshes every 30 seconds.
   - The web thread only reads the on-disk file (`_load_latest_from(monitor_dir)` does a fresh `Path.read_text()` on every request), never referencing any in-memory variable belonging to the sampler thread. Manually verified, see "Manual verification: two real process runs" below.

2. **The staleness threshold generates from the verdict engine's DEFAULTS into the page, not another copy of the number.**
   In `render_html`, `stale_after_s = verdicts.DEFAULTS["sample_interval_s"] * 3`; this computed value is embedded directly into the page's inline `<script>` as the `staleAfterS` variable, and client-side JS compares `Date.now()/1000 - sampledAt` every 5 seconds, adding a `stale` class to `#banner` when it exceeds the threshold (CSS turns it red). No other place repeats a literal like `60*3` or `180`.

3. **Commit.** See the commit list below.

Done incidentally (within ticket scope, not extra work added for its own sake):
- `main()` got a `--port` flag (default 8377, the ticket's specified default); when not `--once`, a `WebServer` daemon thread is started before entering the sampling loop, and `web.stop()` is called if the sampling loop ends (in theory this never happens, unless an exit path is added later).
- Synced the `ops/sampler.py` line in `MAP.md` with the web-outlet description. This line was already supposed to reflect what this file can now do, not a separately added task.

## How it was verified

### Automated tests

New `tests/test_sampler_web.py` (Step 1 wrote failing tests first, confirmed `AttributeError: module 'sampler' has no attribute 'WebServer'`, then implemented):
- `test_json_matches_latest_file`: starts `WebServer(port=0, ...)`, fetches `/json` with `urllib.request`, asserts it equals the dict written into the fixture's latest.json.
- `test_json_content_type`: asserts `Content-Type: application/json`.
- `test_root_returns_200_with_task_table`: fetches `/`, asserts 200, and the body contains the job name (`x`), verdict (healthy/dead), and the `HH:MM:SS` timestamp text corresponding to `sampled_at`.
- `test_root_renders_incidents_and_extras`: asserts the incident record's note text and out-of-ledger session names both appear in the body.
- `test_stale_threshold_from_verdicts_defaults`: asserts that the number computed from `verdicts.DEFAULTS["sample_interval_s"] * 3` appears verbatim in the body (i.e. the number embedded in the page really is generated from DEFAULTS, not another separately-copied literal).
- `test_missing_latest_file_returns_200_with_placeholder`: when latest.json does not exist, `/` still returns 200, with the body containing a "no sample yet" placeholder.

Run and output:

```
$ python3 -m unittest tests.test_sampler tests.test_sampler_web -v
...
test_unreachable_returns_false (tests.test_sampler.TestProbePort) ... ok
test_missing_log_returns_empty (tests.test_sampler.TestReadBeats) ... ok
test_reads_only_valid_heartbeat_lines (tests.test_sampler.TestReadBeats) ... ok
test_files_are_valid_json (tests.test_sampler.TestSampleOnce) ... ok
test_refire_resets_state_and_counts (tests.test_sampler.TestSampleOnce) ... ok
test_round (tests.test_sampler.TestSampleOnce) ... ok
test_json_content_type (tests.test_sampler_web.TestWebServer) ... ok
test_json_matches_latest_file (tests.test_sampler_web.TestWebServer) ... ok
test_missing_latest_file_returns_200_with_placeholder (tests.test_sampler_web.TestWebServer) ... ok
test_root_renders_incidents_and_extras (tests.test_sampler_web.TestWebServer) ... ok
test_root_returns_200_with_task_table (tests.test_sampler_web.TestWebServer) ... ok
test_stale_threshold_from_verdicts_defaults (tests.test_sampler_web.TestWebServer) ... ok

----------------------------------------------------------------------
Ran 12 tests in 3.237s

OK
```
(the old `tests.test_sampler` six cases were run together as well, confirming no regression.)

`python3 -m py_compile ops/sampler.py tests/test_sampler_web.py` → `compile ok`.

### Manual verification: two real process runs

First run, `--interval 300 --port 18377`, `curl /json` right after starting (about 2 seconds later): got `{"error": "not sampled yet"}`, because that round's `sample_once()` was still running (a real ledger triggers cross-host ssh probing, which is not that fast). This confirms the web thread and the sampling thread don't block each other: the web service is already responding, it's just that `latest.json` hadn't been written to disk yet.

Second run, started the same way, `curl` again after 15 seconds:

```
$ curl -s http://127.0.0.1:18378/json | python3 -m json.tool | head -6
{
    "sampled_at": 1786140913.6448956,
    "rows": [],
    ...
$ curl -s http://127.0.0.1:18378/ | grep -o "Last sampled[^<]*" | head -1
Last sampled 07:15:13
```
Once disk writing completes, the web page immediately can read the new result, with the timestamp format correct. Killed the process and `rm -rf`'d the temporary `NEW1_MONITOR_DIR` after use.

Also smoke-tested the `--once` path (without starting the web thread) with `NEW1_MONITOR_DIR=/tmp/... python3 run.py sampler --once`, confirming the original single-round flow was not broken, and `latest.json` was written normally.

`python3 run.py selfcheck`: in this worktree it reports 16 "missing" items, all `envs/`, `cprobe-env`, `mbert-env` third-party/virtual environments excluded by `.gitignore` and only ever built in the main repo (home) directory; a worktree checkout does not carry over untracked directories. Running the same command in the main worktree gives "63 tasks / 4 recipes, all present." This is not a problem introduced by this change, it is a known limitation of the worktree protocol itself with respect to untracked directories, unrelated to the `ops/sampler.py`/`MAP.md` changes. This ticket did not touch `run.py`'s TASKS/RECIPES registry itself (the `sampler` task entry already existed; ticket 02 had already written "starts a web server" into its desc), so strictly speaking this doesn't fall within the trigger range of "changed something related to the run.py registry," but it was still run once for a cross-check.

## Commit list

- `5897417`: `T06: monitor: sampler web outlet (/ task table + /json, read-only latest.json)`
  - `ops/sampler.py`: added the `html`/`http.server`/`threading` imports; new `_load_latest_from`, `render_html`, `_WebHandler`, `WebServer`; `main()` got `--port` (default 8377), starting/stopping the web thread when not `--once`.
  - `tests/test_sampler_web.py`: new, 6 tests.
  - `MAP.md`: the `ops/sampler.py` line got the web-outlet description and `--port` usage added.

## Self-check findings and open questions

- What status code `/json` should return when `latest.json` is missing is not named by either the ticket or spec Task 7 (Task 7 only wrote "the latest.json content verbatim," with the implicit premise that the file already exists). I chose 503 + `{"error": "not sampled yet"}`, the reasoning being that "say so when you can't read it" fits the repository's fail-closed baseline better than pretending 200 and returning an empty/placeholder JSON, but this is my own ruling, not something the ticket fixed in the interface. If the main session/downstream tickets (e.g. ticket 08's terminal outlet, or a future agent consumer) have different expectations about this status code, this needs to be revisited. This counts as one open question, and does not affect the DONE status, because the ticket's acceptance criteria do not cover "what happens to /json when the file doesn't exist."
- `probe_free`/`register_all` (ticket 10's refire, ticket 09's launch commons) and other tickets are out of scope for this one, and were not touched.
- `ops/gpu_jobs.py` (that is ticket 07's scope) was not touched, nor was the sampler task entry itself in `run.py` (the description already says "starts a web server," no need to change it again).
