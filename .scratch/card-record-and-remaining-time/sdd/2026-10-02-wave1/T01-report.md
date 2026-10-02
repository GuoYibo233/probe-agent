# T01 report: the card record on every finish row

Branch `ticket/2026-10-02-wave1/T01`, base `757d0067c7e90636d75f5bfafbdc27b6088f4f19`,
head `e4850c4`. Worktree `/home/y-guo/reproduce/new1-wt/2026-10-02-wave1-T01` (removed after
the commit; the branch is kept).

## 1. What was done, against each requirement

The ticket file was the source; the spec sections "The record" and decisions 4 and 5 were read
for the shape. Nothing in `notes/plans/2026-09-17-contracts.md` names `card_record` (8.2 lists
the finish row's fields before this ticket), so there was no contract to follow beyond the
ticket and spec.

- **Field on every card-stage finish row, one helper, no other writer changed.**
  `registry.append_finish` (`jobs/registry.py`) now adds `card_record` when the run id's
  `<stage>-` prefix is in `CARD_STAGES = ("sample", "inject", "train")`. The record is built by
  `_card_record(run_id, status)` and its private helpers, all in `jobs/registry.py`, under the
  lock `append_finish` already takes. None of the eight finish-row call sites in `run.py` and
  `jobs/registry.py` was touched. A CPU stage's row gets no field.
- **1. `hosts()` keeps the card model; `card_model(host, index)`.** Each `hosts()` entry gains
  `model`, a list by card index parallel to `memory_gib`. `card_model(host, index)` sits beside
  `card_memory_gib()`, accepts a name or an alias (through `canonical_host`) and returns None
  for an unknown host or index.
- **2. What the helper reads.** The run's open start row (from `fold`), the run directory's
  `meta.json` (the launch ordinal through `launch_ordinal`, and the pieces), the frozen
  `settings.yaml`, the incarnation's heartbeat files (through `current_beats`, which honours
  each entry's `beat_launch`) and each card-holding piece's `log/<index>.txt`. The task
  identity is one constant, `CARD_TASK_FIELDS`, keyed by stage, with the spec's lists:
  - every stage: `stage`, `debug` (`_debug` of `settings.yaml`);
  - `sample`: `models.agent`, plus `cards_per_agent_server` (the card count of the first
    card-holding agent service piece; the setting has no such field, the pieces do);
  - `inject`: `models.agent`, plus `probe_score.backbone`, `probe_score.tuning`,
    `probe_gen.backbone`, `probe_gen.tuning`, read as `models.probe` and `probe.tuning` from the
    settings.yaml of the train run each checkpoint comes from (keyed by the run's
    `_upstream["probe_score.train"]` and `["probe_gen.train"]`, looked up under both roots and
    accepted only when that file's `_key` matches, the rule `schema.referenced_run_dir` uses);
  - `train`: `models.probe`, `probe.method`, `probe.tuning`, `probe.lora_r`, `train.max_len`,
    `train.events_per_mb`, `train.grad_ckpt`.
- **3. Memory figures.** Train piece: `peak_gib`, the largest `mem_gib` among the
  incarnation's beats, null until ticket 02 lands. Agent service: `weights_gib`,
  `kv_cache_gib`, `max_concurrency` from the three vLLM lines the spec quotes. Probe service:
  `peak_gib` from `probe service memory: <x> GiB reserved after loading` (ticket 02's line),
  null when absent.
- **4. Failure.** `MEMORY_FAILURE_PATTERNS` is the one constant with the spec's four patterns.
  `failure` is `memory` (the newest matching line), `error` (any other traceback: the exception
  line of the newest one, found as the first line after its header that is not indented once
  vLLM's `(EngineCore pid=N) ` and logger prefixes are set aside), or null. `failure_line` is cut
  to `FAILURE_LINE_CHARS = 300`. Only the last `LOG_TAIL_BYTES = 16 * 1024` of the log is read
  for the failure.
- **5. Speed.** Over the incarnation's work pieces (`loop`, `train`): per piece
  `(last.done - first.done) / (last.ts - first.ts)` over its counting beats (no `phase`) in the
  stage's unit (`SPEED_UNIT`: `task` for sample and inject, `step` for train, so ticket 02's
  `prediction split` beats are not counted), summed over the pieces, given per hour; `done` is
  the summed beats moved and `span_s` the longest piece span. Null when no piece has two such
  beats.
- **6. A helper failure never blocks the row.** Every field is read through `_guarded`, which
  turns an exception into null; `append_finish` also guards the whole record, so the row is
  always appended.
- **7. README section 2.** The `jobs/registry.py` entry's description names the card record,
  and its `reads:` gains the card models, the run directory's `settings.yaml` (and, for inject,
  the two train runs' `settings.yaml`) and the pieces' `log/<piece>.txt`. The `jobs/runs.jsonl`
  line says a card stage's finish row carries the card record. The `constants/cards.yaml`
  `read by:` line names `card_model()` and `card_memory_gib()` for the card record.

### Choices made where the ticket and spec leave room

- **Pieces come from `meta.json` (`_pieces_of`), not the start row alone.** The meta entries
  carry the same host, gpus and `beat_launch` as the start row, plus the launcher's `started`
  stamp. Without that stamp `judge` reads a train piece that died while loading its model (no
  beat yet) as `not started` instead of `dead`. `_pieces_of` is the derivation `ls`, `sync` and
  `cards_busy` already use, and it falls back to the start row's pieces when `meta.json` is
  missing.
- **The verdict at finish time is read with every session gone and no host probed.**
  `_finish_verdicts` runs `judge` on the work pieces and `judge_service` on the services with
  `alive` False. A finish row is appended after the incarnation's processes have ended (or
  while they end), and probing over ssh inside the lock would cost seconds per host. In an `ok`
  run every card-holding piece then reads `done`, so the failure is read only in a non-`ok` run
  or for a `dead` piece, as the spec says.
- **A `not started` piece's log is not read for a failure**, because the log is appended to by
  every incarnation (`tee -a`) and would only hold an earlier incarnation's lines.
- **No open start row, no record.** When `append_finish` is called for a run that already has a
  finish row after its newest start row (`_finalize_pair_stage` for a request widened over pairs
  that are all on disk already), `card_record` is null: no incarnation ran since the last finish
  row, and recording the earlier one again would count it twice in ticket 04's table.
- **Agent memory lines are read from the whole log.** The 16 KB limit is item 4's (failure). The
  vLLM load lines come near the start of an incarnation, and a long run's log is megabytes of
  statistics lines after them, so the scan streams the whole file and keeps the figures of the
  newest load (a load line clears the KV-cache and concurrency figures, the lines after it fill
  them in). Measured on the largest real log (`outputs/sample/e09d7f1730d6/log/20.txt`,
  3.8 MB): 0.01 to 0.13 s.
- **A piece on several cards.** `card_gib` is the smallest of its cards' memory; `card_model` is
  the one model, or the distinct models in card order joined by ` + `.
- **The probe service's figure is named `peak_gib`**, the field name ticket 04 reads for "the
  largest peak memory (train and probe service)".

## 2. How it was verified

### Acceptance 1: the unit test

New class `CardRecordTest` in `tests/test_registry_concurrent_append.py` (CPU only, temporary
tree with a copy of `jobs/registry.py`, its own `runs.jsonl`, a fixture `constants/cards.yaml`
and a `constants/path_outputs.yaml` rooted in the temporary directory; the real ledger and NFS
are never touched). Each case compares the whole `card_record` dict:

- `test_train_piece_dead_of_memory`: train piece with an earlier incarnation's beats (ignored),
  this incarnation's step beats carrying `mem_gib`, a `validate` touch, two `prediction split`
  beats, and a log ending in a CUDA out-of-memory traceback; status `launch_failed`. Expected
  `peak_gib` 62.5, `failure` `memory`, `failure_line` the out-of-memory line cut to 300
  characters, speed 8 steps in 200 s = 144.0 per hour, launch 2, the seven train identity
  fields.
- `test_agent_service_memory_lines_and_its_log_tail`: sample run (debug) with two loop pieces,
  an agent service on card 5 whose log holds two incarnations' load lines, an out-of-memory line
  from the first incarnation outside the 16 KB tail, 27 KB of statistics lines, and a final
  `KeyboardInterrupt` traceback with vLLM's process prefix; a render-only probe service with no
  card; status `killed`. Expected the second load's 50.22 / 73.63 / 8.99, `failure` `error` with
  `(APIServer pid=7) KeyboardInterrupt` (the earlier memory line is outside the tail), no entry
  for the card-less probe service, `cards_per_agent_server` 1, speed summed over the two loop
  pieces.
- `test_inject_checkpoints_and_the_probe_service_of_a_finished_run`: inject run whose two
  checkpoints' train runs sit under the two roots, an agent service on cards 3,4 with no log
  (null figures), a probe service whose log has the memory line and a teardown traceback;
  status `ok`. Expected the four checkpoint fields, `peak_gib` 3.42, and no failure read.
- `test_unreadable_inputs_leave_fields_null_and_the_row_lands`: a train run with no run
  directory at all gives `launch` 0, `task` null, the piece with null figures and `speed` null;
  a second finish row for the closed run gives `card_record` null; a `build` finish row has no
  `card_record` key.

```
$ cd /home/y-guo/reproduce/new1-wt/2026-10-02-wave1-T01 && /home/y-guo/reproduce/new1/external/probe-env/bin/python tests/test_registry_concurrent_append.py -v
test_agent_service_memory_lines_and_its_log_tail (__main__.CardRecordTest.test_agent_service_memory_lines_and_its_log_tail) ... ok
test_inject_checkpoints_and_the_probe_service_of_a_finished_run (__main__.CardRecordTest.test_inject_checkpoints_and_the_probe_service_of_a_finished_run) ... ok
test_train_piece_dead_of_memory (__main__.CardRecordTest.test_train_piece_dead_of_memory) ... ok
test_unreadable_inputs_leave_fields_null_and_the_row_lands (__main__.CardRecordTest.test_unreadable_inputs_leave_fields_null_and_the_row_lands) ... ok
test_eight_processes_land_all_160_rows (__main__.ConcurrentAppendTest.test_eight_processes_land_all_160_rows) ... ok
test_attached_service_is_judged_by_its_port_and_its_runs_work (__main__.PieceVerdictTest.test_attached_service_is_judged_by_its_port_and_its_runs_work) ... ok
test_beat_naming_a_phase_is_never_slowed (__main__.PieceVerdictTest.test_beat_naming_a_phase_is_never_slowed) ... ok
test_piece_whose_session_was_never_started_is_not_started (__main__.PieceVerdictTest.test_piece_whose_session_was_never_started_is_not_started) ... ok
test_relaunched_piece_reads_only_its_own_incarnation (__main__.PieceVerdictTest.test_relaunched_piece_reads_only_its_own_incarnation) ... ok
test_service_ended_after_its_loop_pieces_finished_is_done (__main__.PieceVerdictTest.test_service_ended_after_its_loop_pieces_finished_is_done) ... ok
test_service_gone_while_its_loop_piece_works_is_dead (__main__.PieceVerdictTest.test_service_gone_while_its_loop_piece_works_is_dead) ... ok
test_train_piece_at_step_total_without_finish_row_is_not_done (__main__.PieceVerdictTest.test_train_piece_at_step_total_without_finish_row_is_not_done) ... ok
test_train_piece_with_finish_row_is_done (__main__.PieceVerdictTest.test_train_piece_with_finish_row_is_done) ... ok

----------------------------------------------------------------------
Ran 13 tests in 0.356s

OK
```

### Acceptance 2: selfcheck and all test modules

The worktree has no `external/` (not in git), so every command used the main repo's
interpreter with the worktree as the working directory. The tree now has eight test modules
(`tests/test_qwen3_family.py` was added after CLAUDE.md listed seven); all eight were run.

```
$ /home/y-guo/reproduce/new1/external/probe-env/bin/python run.py selfcheck
selfcheck: 32 python files, 0 problems
== tests/test_environment_and_build.py
Ran 22 tests in 0.072s
OK
== tests/test_packed_loss.py
Ran 3 tests in 2.997s
OK
== tests/test_probe_eval.py
Ran 15 tests in 2.069s
OK
== tests/test_probe_input.py
Ran 19 tests in 2.059s
OK
== tests/test_qwen3_family.py
Ran 13 tests in 32.826s
OK
== tests/test_record_formats.py
Ran 16 tests in 0.083s
OK
== tests/test_registry_concurrent_append.py
Ran 13 tests in 0.357s
OK
== tests/test_settings_keys.py
Ran 25 tests in 24.085s
OK
```

`git status` after the test runs showed only the three edited files.

### Acceptance 3: no code-era row

```
$ git diff --stat 757d006 e4850c4
 README.md                                |   8 +-
 jobs/registry.py                         | 338 ++++++++++++++++++++++++++++++-
 tests/test_registry_concurrent_append.py | 290 +++++++++++++++++++++++++-
 3 files changed, 626 insertions(+), 10 deletions(-)
```

`jobs/versions.yaml` is not touched.

### Extra check: read-only records for real runs

A scratch script loaded the branch's `jobs/registry.py`, pointed it at the real
`jobs/runs.jsonl` for reading only, and built the record pieces for four real runs without
appending anything. The debug run `sample-c32dc16e29c0` (status ok) gave exactly the spec's
example: launch 2, agent service on tokyo108 card 5, `NVIDIA H200 NVL`, 140 GiB, 50.22 / 73.63 /
8.99, speed `{"unit": "task", "done": 9, "span_s": 173.0, "per_hour": 187.3}`.
`sample-e09d7f1730d6` (22 pieces, three agent services) gave 61.43 / 20.45 / 4.04 on the H100
card and 61.43 / 63.43 / 12.52 on the two H200 cards; building it took 3.75 s on yebis over NFS,
almost all of it reading 19 loop pieces' heartbeat files. `_log_failure` over every real piece
log under `outputs/` and `outputs/debug/` flagged 16 logs: 5 `memory` (all CUDA out-of-memory
lines in debug train runs) and 11 `error` (8 `torch.AcceleratorError` probe-service logs, 3 vLLM
`RuntimeError: Engine core initialization failed`, 1 `PytorchStreamReader` error).

## 3. Commits

- `e4850c4` T01: the card record on every card-stage finish row (`jobs/registry.py`, README
  section 2, four new cases in `tests/test_registry_concurrent_append.py`).

## 4. Self-review and open questions

- Scope: only `jobs/registry.py`, README section 2 and the registry test module changed. No
  finish-row writer outside `append_finish` changed, and `render()` is untouched (ticket 04's).
- Merge overlap with ticket 02: both tickets edit `jobs/registry.py`. Ticket 02 changes
  `Heartbeat._write` (to pass `mem_gib`); this branch changes `hosts()`, adds `card_model()`,
  and changes `append_finish` and the new block after it. The hunks do not overlap, so the merge
  should be clean, but both touch the same file.
- The failure rule follows the spec: read only in a non-`ok` run or for a `dead` piece. One case
  it misses: in an `ok` sample or inject run with two agent replicas, a replica that died of
  memory while the other finished the work reads `done` under `judge_service` (its session is
  gone and the run's work is done), so its failure is not recorded. Reading every service log
  tail in an `ok` run would catch it but would also read teardown tracebacks as `error`.
- Logs are appended to by every incarnation (`tee -a`) and carry no incarnation marker. A
  service that printed no load line in this incarnation therefore reports the previous
  incarnation's vLLM figures. A launch that records each log's size at start would fix this,
  but that is a launcher change outside this ticket.
- For a vLLM engine failure, the "last exception line" is the API server's wrapper
  (`RuntimeError: Engine core initialization failed. See root cause above.`); the engine's own
  cause is in an earlier traceback. The spec asks for the last exception line, so that is what
  is quoted; a memory root cause is still found when its line is inside the 16 KB tail, because
  memory patterns are matched before tracebacks.
- The record is built inside the registry lock. Most callers already hold that lock when they
  call `append_finish`, so building it outside would not shorten the hold. The cost measured on
  the largest real run was 3.75 s, once per finish row.
- `speed` sums the per-piece rates, as the spec's "summed over the work pieces" and `ls`'s summed
  rates do; `span_s` is the longest piece's span, so `per_hour` differs from
  `done / span_s * 3600` when pieces run for different spans. For one piece (every train run)
  the two agree.

---

# Fix round 1

Branch `ticket/2026-10-02-wave1/T01`, worked in
`/home/y-guo/reproduce/new1-wt/2026-10-02-wave1-T01-fix1` (removed after the commit), head
`4dd8bc9`.

## 1. What was done, per finding

### F1 (critical): log reads ignored where this incarnation's output starts

The root cause was that the launcher measured each work piece's log size before its session
started (`incarnation_origin`) but kept the number only in memory, so the record had no way
to tell this incarnation's lines from an earlier one's. The fix records that number on the
piece entry and makes every log read in the record start from it.

- **`jobs/launch.py`, `incarnation_origin`.** It now measures every placed piece's log size,
  services included, stamps it on the piece as `log_offset`, and writes the entries to
  `meta.json` with one `registry.write_meta` call before returning. That happens after the
  launch's own lock hold and before the first `tmux new-session`. The returned map for
  `alive_check` is built from the same measurement and is otherwise unchanged. `_start_wave`
  then writes the same entries with `started` added, so `log_offset` stays on them. A new
  private helper, `_log_size(log)`, gives the size, or 0 when the log does not exist yet.
- **`jobs/launch.py`, `refire`.** The restarted piece's entry gets
  `log_offset = _log_size(log)` next to its new `beat_launch`. This happens inside the hold,
  before the `meta.json` write and the session start, so a refired train piece's record reads
  none of the dead incarnation's lines.
- **`jobs/registry.py`.** `_card_piece` reads `offset = piece.get("log_offset") or 0` and
  passes it to all three readers:
  - `_log_failure` / `_log_tail` read from `max(offset, size - LOG_TAIL_BYTES)`. They drop
    the first line only when the 16 KB limit cut inside it, which is when the start is after
    the offset.
  - `_agent_memory` and `_probe_memory` stream from `offset` through the new `_log_lines`
    helper (binary read, UTF-8 decode).
  - An entry without `log_offset` reads from byte 0, which is the behaviour before this fix.
    The "a load line clears the other two" rule in `_agent_memory` stays for those entries.
- **README section 2.** Four lines changed:
  - the `jobs/registry.py` `reads:` line says the piece logs are read from the byte the
    entry's `log_offset` names;
  - the `jobs/launch.py` description says a launch or a refire records `log_offset` before
    the session starts;
  - its `writes:` line names the piece entries' `started` and `log_offset`;
  - the `tests/` line names the card-record cases, including the relaunch case.
- **Not deferred to ticket 03.** The fix is the small launcher change the finding describes,
  so it lands here and nothing is left implicit. Ticket 03 also edits `launch()` and
  `refire()`, but at the start-row append, not in `incarnation_origin`. The one nearby hunk
  is the new `log_offset` line in `refire()`, two lines above the `append_start` call ticket
  03 changes. A merge conflict there, if any, is textual and small.

## 2. How it was verified

Two new cases were added to `CardRecordTest` in `tests/test_registry_concurrent_append.py`.
Each imports the tree's `jobs/launch.py` and points its `registry` at the case's temporary
copy for the length of the case (`_launch`), so every `meta.json` write lands in the
temporary tree. `_relaunch` runs what a launch does to the entries: `incarnation_origin`,
then the `started` stamp `_start_wave` writes.

- `test_relaunched_train_piece_records_none_of_the_earlier_incarnations_log` reproduces the
  finding's scenario.
  - Incarnation 1 runs on tokyo108 card 0 (H100) and dies with the CUDA out-of-memory
    traceback. Its record reads `failure: memory`.
  - The relaunch runs on card 4 (H200) with `beat_launch` 1. The test checks that
    `incarnation_origin` returns `{0: {"log_size": <earlier size>}}` and that the
    `meta.json` entry carries `log_offset` equal to that size, `gpus` "4" and `started`, with
    no `run_dir`.
  - The relaunch writes one log line and one beat (`mem_gib` 30.0) and is `killed`. The whole
    record is compared: launch 2, H200 / 140 GiB, `peak_gib` 30.0,
    `failure: null, failure_line: null`, `speed: null`.
- `test_relaunched_agent_service_reads_its_figures_and_failure_from_its_offset` covers the
  service half.
  - The earlier incarnation's agent-service log holds the three vLLM load lines and an
    out-of-memory line, and the loop log has one line. The endpoint file is present.
  - After `incarnation_origin`: the endpoint file is gone, the origin map holds only the loop
    piece, and both entries carry their log sizes as `log_offset`.
  - The relaunched service then dies with vLLM's `RuntimeError: Engine core initialization
    failed` before any load line. Its record entry has `weights_gib`, `kv_cache_gib` and
    `max_concurrency` null, and `failure: error` with that RuntimeError line. Before the fix
    the entry read 61.43 / 63.43 / 12.52 and `memory`.

The new cases were also run against the unfixed code:

- With both `jobs/registry.py` and `jobs/launch.py` at `e4850c4`, the two cases error on the
  missing `log_offset` key.
- With only `jobs/registry.py` at `e4850c4` (the new launcher in place), the two cases fail
  on the record itself:

```
AssertionError: {'lau[372 chars]re': 'memory', 'failure_line': 'torch.OutOfMem[300 chars]None} != {'lau[372 chars]re': None, 'failure_line': None}], 'speed': None}
```

With the fix:

```
$ cd /home/y-guo/reproduce/new1-wt/2026-10-02-wave1-T01-fix1 && /home/y-guo/reproduce/new1/external/probe-env/bin/python tests/test_registry_concurrent_append.py -v
test_agent_service_memory_lines_and_its_log_tail (__main__.CardRecordTest...) ... ok
test_inject_checkpoints_and_the_probe_service_of_a_finished_run (__main__.CardRecordTest...) ... ok
test_relaunched_agent_service_reads_its_figures_and_failure_from_its_offset (__main__.CardRecordTest...) ... ok
test_relaunched_train_piece_records_none_of_the_earlier_incarnations_log (__main__.CardRecordTest...) ... ok
test_train_piece_dead_of_memory (__main__.CardRecordTest...) ... ok
test_unreadable_inputs_leave_fields_null_and_the_row_lands (__main__.CardRecordTest...) ... ok
test_eight_processes_land_all_160_rows (__main__.ConcurrentAppendTest...) ... ok
(8 PieceVerdictTest cases) ... ok
Ran 15 tests in 0.581s
OK
```

The four earlier `CardRecordTest` cases pass unchanged. Their piece entries have no
`log_offset`, so they now also check that an entry written before this change reads from
byte 0.

Selfcheck and all eight test modules, run in the fix worktree with the main repo's
interpreter:

```
$ /home/y-guo/reproduce/new1/external/probe-env/bin/python run.py selfcheck
selfcheck: 32 python files, 0 problems
== tests/test_environment_and_build.py   Ran 22 tests in 0.073s   OK
== tests/test_packed_loss.py             Ran 3 tests in 2.539s    OK
== tests/test_probe_eval.py              Ran 15 tests in 2.000s   OK
== tests/test_probe_input.py             Ran 19 tests in 2.000s   OK
== tests/test_qwen3_family.py            Ran 13 tests in 23.580s  OK
== tests/test_record_formats.py          Ran 16 tests in 0.089s   OK
== tests/test_registry_concurrent_append.py  Ran 15 tests in 0.547s  OK
== tests/test_settings_keys.py           Ran 25 tests in 25.056s  OK
```

After the runs, `git status` showed only the four edited files. `jobs/runs.jsonl` was not
touched.

No code-era row is needed. No stage's `code` tuple in `experimental_settings/schema.py`
names a file under `jobs/` or `run.py`, and `jobs/versions.yaml` is untouched:

```
$ git diff --stat 757d006 4dd8bc9
 README.md                                |  14 +-
 jobs/launch.py                           |  26 +-
 jobs/registry.py                         | 353 +++++++++++++++++++++++++-
 tests/test_registry_concurrent_append.py | 419 ++++++++++++++++++++++++++++++-
```

## 3. Commits

- `4dd8bc9` T01: the card record reads each piece log from where its incarnation's output
  starts (`jobs/launch.py` records `log_offset`, `jobs/registry.py` reads from it, README
  section 2, two new test cases).

## 4. Self-review and open questions

- **Scope grew to `jobs/launch.py`.** The change there is two additions: the offset
  record in `incarnation_origin` and one line in `refire`. No finish-row writer changed. The
  ticket's own file list did not name `jobs/launch.py`; the finding asked for this change.
- **A short window without an offset.** Between `launch()`'s locked `meta.json` write and
  `incarnation_origin`'s write (a directory creation and a few `stat` calls), the entries do
  not carry `log_offset` yet. A finish row appended in that window reads from byte 0, which
  is the behaviour before the fix. The window opens before any session starts.
- **Runs launched before this change keep the old behaviour.** Their entries have no
  `log_offset`, so a relaunch of such a run before this change lands can still show the
  misattribution. Every launch and refire after the merge records the offset.
- **The earlier open question is resolved.** The question in section 4 of the first round
  ("a service that printed no load line in this incarnation reports the previous
  incarnation's vLLM figures") is now answered by this change.
