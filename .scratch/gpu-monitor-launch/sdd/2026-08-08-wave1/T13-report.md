# T13: vLLM service ledger

Ticket: `.scratch/gpu-monitor-launch/issues/13-vllm-service.md`
Reference: `docs/plans/2026-08-08-gpu-monitor-launch.md` Task 15 (implementation-step source named by the ticket)

## What was done

Against the ticket's acceptance requirements one by one:

1. **Throughput-line parsing tests pass: a real sample line yields the generation rate, prompt rate, and concurrency count; no match returns None**

   `ops/sampler.py` got a new `VLLM_STATS_RE` (regex) + `parse_vllm_stats(text)` +
   `read_vllm_stats(log_path, max_bytes=8192)`:

   - `parse_vllm_stats(text)`: extracts every match of `Avg prompt throughput: X
     tokens/s, Avg generation throughput: Y tokens/s, Running: N reqs` from the text, taking
     **the last one** (text can be a multi-line tail, so take the most recent sample), returning
     `{"prompt_tok_s": X, "gen_tok_s": Y, "running": N}`; returns `None` on no match.
   - The fixture line is **not hand-crafted text**: on 2026-08-08 checked directly against
     `/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/logs/new1_diag_srv_a.log`
     line 9421, matching the implementation plan document's given sample byte-for-byte (checked with
     `grep -n "19:50:14"`, see "How it was verified" below). The tests also use another line, line 112
     from the same real log (`Running: 0 reqs`, a different concurrency count and different values), for a second assertion,
     avoiding baking the fixture's specific numbers into the implementation.
   - `read_vllm_stats(log_path)`: tails 8192 bytes, calls `parse_vllm_stats`;
     returns `None` if the file doesn't exist (`OSError`) or this round's log has no throughput line
     (the vLLM engine downgrades this line to debug and doesn't print it when idle). The caller (see below)
     decides whether to keep the previous round's displayed value; the function itself doesn't guess.

2. **Service pieces don't go through heartbeat parsing, verdict is decided only by port probing**

   - `sample_once()` now branches on `piece.get("kind")`: for `kind=="service"` pieces,
     `beats=[]` (no longer calling `heartbeat.parse`, i.e. not calling
     `read_beats`), instead calling `read_vllm_stats(piece["log"])` for
     `vllm_stats`; non-service pieces' behavior is unchanged (`read_beats` as before).
   - `update_piece_state()` got a new optional parameter `vllm_stats=None`: for a service piece,
     if there's a value this round, it's stored into `ps["vllm_stats"]`; if there's no value (the engine went idle and
     stopped emitting), the old value is kept unchanged. spec.md's "idle not emitting the throughput line doesn't
     count as a stall" is not just about not triggering the verdict, the display should also not blink back to blank just
     because of a stopped stream.
   - `build_row()`: for `kind=="service"`, the `tok_in`/`tok_out` display slots
     take from `ps["vllm_stats"]` (`prompt_tok_s`/`gen_tok_s`), no longer from
     `last_beat` (the heartbeat-protocol field); `last_beat` for a service piece was always going to be an empty dict
     anyway, because `recent_beats` is never fed any heartbeat.
   - The verdict path itself is completely untouched: `verdicts._judge_service` was already, since T02, only consuming
     the six fields `alive`/`port_ok`/`port_ever_ok`/`port_fail_rounds`/
     `since_launch_s`/`warmup_s`, not looking at `done`/`total`/the heartbeat time axis at all. This
     change confirms this (the test mixed a valid `@hb` line of text into the service piece's log,
     asserting it was never counted into `recent_beats`/`first_beat` at all, and the verdict follows only
     `probe_port`'s return value).

3. **The fixture uses text checked against the real log on 2026-08-08**: see acceptance item 1 above, and
   the `grep` record in "How it was verified."

4. **The log field must be filled with a real path when registering a service piece**: this original ticket wording is an
   operational requirement for launching/registration, not a code constraint. `piece["log"]` was already a
   free-form string field, `read_vllm_stats(piece["log"])` makes no assumptions about the path (doesn't join with
   workdir, doesn't guess a relative path), it reads whatever path is given. Nothing on the code side needed to be added;
   the temporary fixture path used in real testing was deliberately placed in a directory unrelated to `workdir`
   (`tests/test_vllm_stats.py`'s `TestServicePieceSampling.setUp`), verifying this path
   independence held.

5. **Commit**: see the commit list below.

## How it was verified

First checked whether the fixture is real original text (not copied from the plan document, checked fresh with grep):

```
$ grep -n "19:50:14" /net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/logs/new1_diag_srv_a.log
```
```
9421:(APIServer pid=263921) INFO 08-02 19:50:14 [loggers.py:310] Engine 000: Avg prompt throughput: 785.1 tokens/s, Avg generation throughput: 671.8 tokens/s, Running: 4 reqs, Waiting: 0 reqs, GPU KV cache usage: 11.2%, Prefix cache hit rate: 97.1%
```
Byte-for-byte match to the sample given in implementation plan Task 15.

Newly written tests (TDD: ran once first to confirm everything failed red on
`AttributeError`/assertion failures, screenshot omitted, this is the all-green output after the implementation was written):

```
$ python3 -m unittest tests.test_vllm_stats -v
```
```
test_extracts_real_fixture_line (tests.test_vllm_stats.TestParseVllmStats) ... ok
test_extracts_second_real_line (tests.test_vllm_stats.TestParseVllmStats) ... ok
test_multiple_lines_takes_the_last (tests.test_vllm_stats.TestParseVllmStats) ... ok
test_no_match_returns_none (tests.test_vllm_stats.TestParseVllmStats) ... ok
test_missing_file_returns_none (tests.test_vllm_stats.TestReadVllmStats) ... ok
test_no_throughput_line_returns_none (tests.test_vllm_stats.TestReadVllmStats) ... ok
test_reads_tail_of_log_file (tests.test_vllm_stats.TestReadVllmStats) ... ok
test_healthy_port_ignores_fake_heartbeat_line_and_shows_rate (tests.test_vllm_stats.TestServicePieceSampling) ... ok
test_idle_no_throughput_line_keeps_last_known_rate_for_display (tests.test_vllm_stats.TestServicePieceSampling) ... ok
test_port_down_gives_dead_verdict_regardless_of_throughput_line (tests.test_vllm_stats.TestServicePieceSampling) ... ok

----------------------------------------------------------------------
Ran 10 tests in 0.049s

OK
```

Of the 10, `TestParseVllmStats`/`TestReadVllmStats`'s seven are pure-function unit tests (ticket
acceptance item 1); `TestServicePieceSampling`'s three are integration smoke tests (ticket
acceptance item 2). Separately verifying "port healthy + a valid `@hb` line mixed into the log still
doesn't get counted as a heartbeat, the display slot picks up the throughput line," "port probe failure gives dead,
regardless of whether the throughput line is still there," and "throughput line stops (the second round's log has no
throughput line), verdict is still healthy, display slot keeps the previous round's value."

Whole-repo tests (independent of other parallel tickets' changes in their own worktrees):

```
$ python3 -m unittest discover -s tests -v
```
```
...(89 cases, including the 10 new ones)
----------------------------------------------------------------------
Ran 89 tests in 3.544s

OK
```

```
$ python3 run.py selfcheck
```
```
selfcheck: 63 tasks / 4 recipes, 16 missing
```
All 16 lines are `envs/*/venv`, `cprobe-env`, `mbert-env` and other third-party venv directories that
naturally don't exist in this newly built `git worktree` (excluded from git by `.gitignore`), consistent
with the phenomenon recorded in the T09 report, not a problem introduced by this change; also confirmed running the same command
in the main-repo worktree (`/home/y-guo/reproduce/new1`) that it's "all present." This ticket did not
create/change any `run.py` TASKS/RECIPES registry entry (only changed internal logic in
`ops/sampler.py`), so this time selfcheck wasn't separately re-checked against the main repo. The nature of it is
exactly the same as what T09's report recorded, no need to re-verify.

## Commit list

- `3540212`: `T13: monitor: vLLM service ledger (port probing goes into the verdict, throughput line is display-only)`
  Changes: `ops/sampler.py` (added `parse_vllm_stats`/`read_vllm_stats`,
  `sample_once`/`update_piece_state`/`build_row` all branch on `kind=="service"`), `tests/test_vllm_stats.py` (new,
  10 tests), `MAP.md` (a sentence added to the `ops/sampler.py` line describing the behavior).

## Self-check findings and open questions

- **No launch path currently auto-writes the `port` field (a must-check item named in the ticket's Comments)**:
  the read point `piece.get("port")` inside `ops/sampler.py` was already written by T02 (ticket 02);
  I did not add it this time, only confirmed it and relied on it. But upstream in the complete chain,
  `ops/launch_cmd.py` (ticket 09), currently **has no code that writes a `--port`
  value into a rich piece**: `--port` isn't in `launch_cmd.py`'s `_VALUE_FLAGS`/
  `_BOOL_FLAGS`, so it and its value both fall into `extra` (unrecognized flags passed through
  to the task), joining the command line sent to `vllm serve` verbatim. This is correct for "passing
  `--port` to the actual service process," but it means `register_all()`'s assembled
  `rich_pieces` dict has no `"port"` key at all. That is to say, if a service is actually launched via
  `python3 run.py launch serve-mirrorapi --service --piece host:gpu
  --run-id X --track Y -- --port 8125 ...`, the sampler's side, `piece.get("port")` will get
  `None`, and `update_piece_state`'s `port_ok = probe_port(...) if port else False` will
  short-circuit directly to `False` (see `ops/sampler.py`'s "service kind: port probing" segment); this
  piece can never verdict "healthy," it will only sit at "warming up" until the warm-up ceiling, then turn into
  "suspected stall."

  I **did not** change `ops/launch_cmd.py`. Reason: the ticket's original text says "steps follow
  implementation plan Task 15's execution," and Task 15's Files list only names
  `ops/sampler.py` (change) + `tests/test_vllm_stats.py` (new); none of its ten numbered
  steps mentions touching `launch_cmd.py` or `--service`/`--port` parsing either; and the ticket's
  Comments give two acceptable ways out ("either land port into a piece/ledger field so the sampler can read it, or
  state clearly in the report where port comes from"). Between these two, I chose "state it clearly in the
  report," without opportunistically widening this ticket's scope of change to touch `launch_cmd.py`
  (that's ticket 09's file, out of this ticket's "only touch files within this ticket's scope" boundary; changing it
  myself would mean doing ticket 09's work under ticket 13's name).

  The path actually verified (as exercised by the tests) is: the `piece` dict itself has no schema validation
  on `"port"`, whoever puts this key in, `sampler.py` reads it back. `ops/gpu_jobs.py`'s
  `cmd_register` (the old hand-registration path) currently also has **no** `--port`/`--kind`
  CLI support either (only recognizing `--name`/`--workdir`/`--note`/`--piece
  host:gpus:session:log`), similarly unable to accommodate `kind="service"` + `port` together.
  So the current state is: **no existing command-line path can correctly register a real vLLM service
  as a `kind="service"` ledger entry carrying `port`**. For this change to take effect on a
  real service, someone would have to manually call `launch_common.register_all()` (at the Python
  level) or directly hand-edit `ops/jobs.json` to stuff `"kind": "service", "port": N` into the
  corresponding piece. This is a real gap left for a follow-up ticket (or user decision), not something within this
  ticket's scope that can be filled in at the same time.

- **`probe_port`'s `/health` assumption has not been really verified**: `ops/sampler.py`'s
  `probe_port()` implementation and its comment ("vLLM's /health returns 200, ticket 13 to
  check and fix here if it differs") were both already written by T02. This ticket's protocol explicitly
  forbids launching any GPU process, so I did not start a real vLLM service to test `/health`'s
  actual return code. This assumption remains in a state of "not tested by this ticket," this open question is just
  carried forward as-is, without pretending it's been verified.

- **Reusing the heartbeat protocol's display slots for `tok_in`/`tok_out` is a design choice not verbatim mandated
  by the ticket's original text**: implementation plan Task 15's Step 3 said "grab the throughput line → the row's
  `tok_out` rate display slot," naming only the one field `tok_out`. I additionally put
  `prompt_tok_s` into `tok_in` (symmetrically reusing the same pair of "in/out" display slots,
  rather than opening a new field), which is the smallest reasonable choice I made in the absence of a more detailed spec,
  not copied from some existing precedent. If these two positions ever need to be labeled "this is a throughput
  rate, not a cumulative token count" on the web/terminal table down the line, a separate display format needs to be defined;
  I did not change `render_html()`'s header/unit annotation this time; the `tok` column for a
  service piece currently displays plain numbers (like `785.1/671.8`), which looks visually the same as a batch
  task's cumulative token count, and could easily be misread. Worth eyeballing once a real service piece is actually wired up
  and running.

- No real GPU process or tmux session was launched; all tests used temp directories + fake log
  files + monkeypatched `probe_port`/`live_sessions`, without touching the real ledger
  (`ops/jobs.json`), `ops/runs.jsonl`, any GPU machine, or connecting to any real network
  port (`probe_port`'s unit test uses port 1 to trigger `ConnectionRefused`, this test was already
  there in T02, unchanged this time).
- The `run.py` TASKS/RECIPES registry wasn't touched, `python3 run.py selfcheck` isn't a new gate for
  this change (it doesn't involve a new task/new recipe), but it was still run once per ticket discipline to
  confirm it didn't introduce any new missing item.
