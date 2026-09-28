# T09 report — the dataset builder

Ticket: `.scratch/from-zero/issues/09-dataset-builder.md`
Branch: `ticket/2026-09-17-wave3/T09`, base `28735bb2437f34af4f85d915b9de22f22530cfaa`, head `2be4f0688b4b93137ff1d871f74e68c840ad051e`
Contracts read: 2.5 (every gate), 1.2 (the example row), 1.7 (the probe's input), 2.3 (the requested pair list), 1.5 (`consumed.json`, `done.json`), plus 0.1/0.2 (annotation format), 1.1 (the record format and `read_dir`/`done_pairs`), 2.1/2.6 (the stage table and the call shape), 3.1 (`run_dir_of`), 4.1/4.2/4.3 (the environment contract), 5.2 (the `build` and `sample` fields).
Spec sections read: 1–9 of `.scratch/from-zero/spec.md`.

## What was done

One file, `data/build_training_dataset.py`, plus its `README.md` entry (appended under a new "Ticket 09" section — tickets 07 and 08 were not yet in this worktree's base, so their README sections are not here; the wave merge reconciles all three, per spec.md section 3).

Every numbered step of the ticket's "the walk, in order" is implemented:

1. `cfg = schema.load_frozen(run_dir)`, `hb = registry.beat(run_dir, 0)`.
2. `env = open_env(cfg.data.env)`.
3. `requested_pairs` → `triples`, projected to `pairs` (dropping the split element).
4. `sample_dir = schema.run_dir_of("sample", cfg._upstream["sample"], debug=cfg._debug)`, the key read out of `_upstream`, never recomputed.
5. Completeness gate via `trajectory_record.done_pairs`, naming the missing `(task_id, seed)` pairs.
6. `hb.emit(0, len(pairs), "row")`, then a `read_dir` call followed by `len(pairs)` sequential `hb.emit` calls, one per record — see "Decisions" below for how I resolved the ordering between this step and the literal `read_dir` call in step 9.
7. Split files resolved from `constants/path_datasets.yaml`'s `splits:` block for `cfg.data.env`, ids from `env.tasks(split)`, each file sha1-hashed.
8. Split gates: a task id in two splits; a record's task id in none of the official lists.
9. `df = trajectory_record.read_dir(sample_dir, pairs)` (folded into step 6's block, see below).
10. Abort gate against `cfg.build.max_abort_frac`.
11. Per-record gen/env join by `step`; a `gen` row with no matching `env` row raises, naming the record and the step, without breaking out of the trajectory (the raise ends the whole build, not just that trajectory).
12. Per-event walk with `history` accumulated per record: the null-action skip (no append), the no-call skip (append, counted as `events_skipped_no_call` per the wave-3-precheck-pinned errata number, the corpus counts themselves are not asserted by any code path), the short-think skip (append), and the full-processing branch (round-trip check, `probe_input.cuts`, one row per offset with `depth`, `weight`, and the `data/__init__.py` id functions — never a formatted string at the call site).
13. The `split` column: `env` rule through `env.SPLIT_ROLE`, `hash` rule through the sha1-of-task-id / cumulative `split_ratio` rule (not exercised by any acceptance command, but implemented per 5.2).
14. Row gates: the call round trip, empty `text`, `depth` outside `[0, 1]`, and `row.text.endswith(thinking[:cut])`.
15. Per-split cap: first `cfg.build.max_examples` rows of each split in `example_id` order.
16. `training_data.write(run_dir / "examples.parquet", frame)`.
17. `consumed.json`: every record file (path, sha1, row count) then every split file (path, sha1, task count), all under the uniform `{path, sha1, n_rows}` shape 1.5 gives.
18. `report.md`: identity line, records/events/skip counts/examples, cuts-per-event stats, per-split tasks·events·examples, tool vocabulary (count, top5, long tail), tools unseen in train, depth deciles, text length percentiles, abort share, and the cap-dropped count.
19. `registry.write_done(...)` with the `counts` dict the ticket's errata names, then `hb.finish()`.

Entry point: `def main(run_dir: Path) -> None`, plus an `if __name__ == "__main__":` block whose only flag is `--run-dir`. `main` calls `schema.load_frozen(run_dir)` itself; no setting name anywhere on the command line.

## Decisions I made that the ticket did not pin down

- **Step 6 vs step 9's literal ordering.** Step 6 says "`hb.emit(0, len(pairs), "row")`, then one beat per record read", placed before steps 7–8 (resolve the split files, split gates), while step 9 places `df = trajectory_record.read_dir(sample_dir, pairs)` after the split gates. `read_dir` offers no per-record callback, so "one beat per record read" cannot be interleaved with that one call. I placed the `read_dir` call immediately after the split gates (matching step 9's position) and emit `len(pairs)` sequential beats right after it — the beats are not literally synchronous with disk I/O, but they are one beat per record and follow the same relative order the walk describes. This is a CPU-only stage with records numbering in the low hundreds at most, so the distinction is not observable in practice. The code comment at that line says so.
- **The round-trip gate's `example_id`.** The gate fires once per event, before any cut offsets are computed (since `call`/`tool`/`args` are identical across every cut of one event), so I name the failure with `example_id(event_id, 0)` — a representative id at cut_index 0, even though that particular row was never built. The acceptance test (`bad_call`) only checks that an example-id-shaped string and both sides of the round trip appear in the message, which this satisfies.
- **`counts.tools` / `counts.tools_unseen_in_train`.** The ticket doesn't say whether these are computed pre-cap or post-cap. I compute them over the final, post-cap frame (the frame actually written to `examples.parquet`), since that's the frame any downstream reader sees.
- **The report's "agent model" line.** `build`'s own frozen `settings.yaml` carries no `models` section (2.1: build's sections read are `data`, `build`, `sample.{...}` only), so I read the agent model alias off each record's own `meta.agent_model` column and report the sorted distinct set, rather than off `cfg`.
- **README.md.** Only ticket 09's own entry was appended, using the ticket's own fuller `imports:`/`reads:` lines (which name `[polars, PyYAML]` and `constants/path_datasets.yaml`) rather than contracts 0.2's incomplete original — per the ticket errata note on this exact point ("0.2's own annotation lines for this file were incomplete") and per spec.md section 1 ("when a ticket and the contracts disagree, the ticket wins and you say so"). Tickets 07 and 08's README sections are not present in this worktree because their branches had not merged into this base; the wave merge keeps every ticket's lines per spec.md section 3.

## Known ticket-documented defect exercised, not fixed

F3's `unknown_task` variant only removes a task id from the split files; `requested_pairs` derives both the requested pairs and the records the builder reads from those same (now-edited) files, so the run stops at step 5's completeness gate (the substituted task has no record file in the fixture's `sample_dir`) rather than reaching the unknown-task split gate. This is called out in the ticket's Comments as "Known script defect, report it as it is and do not bend code to pass it" — I did not change the code to route around it. The completeness-gate message does still name a task id, so F3's table requirement ("must contain: the task id") is satisfied, just via a different gate than the one the row names.

## How it was verified

All commands run from `/home/y-guo/reproduce/new1-wt/2026-09-17-wave3-T09` (the worktree root), pasted output below trimmed only where noted.

**A1 — imports under all three venvs.**
```
$ for P in .../probe-env/bin/python .../appworld/venv/bin/python .../vllm-env/bin/python; do "$P" -c "..."; done
imports ok 3.11.15
imports ok 3.12.13
imports ok 3.12.13
```
Matches exactly.

**A3 — one column-zero `VERSION`.**
```
$ grep -c '^VERSION = [0-9][0-9]*$' data/build_training_dataset.py
1
```

**F1 — command shape, no setting name on the command line.**
```
$ "$AW" -m data.build_training_dataset --help 2>&1 | head -5
usage: build_training_dataset.py [-h] --run-dir RUN_DIR

Build the probe training dataset from a sample run's task records.

options:
$ "$AW" -m data.build_training_dataset --run-dir /nonexistent; echo "exit=$?"
build: --run-dir /nonexistent does not exist
exit=1
```
Help names only `--run-dir`; the second command exits non-zero naming `/nonexistent`.

**F2 — the end-to-end build.**
```
$ (cd "$FIX" && "$AW" -m data.build_training_dataset --run-dir "$BDIR"); echo "exit=$?"
... (heartbeat lines) ...
exit=0
$ ls "$BDIR"
consumed.json  done.json  examples.parquet  heartbeat  report.md  settings.yaml
$ (cd "$FIX" && "$AW" -c "... read examples.parquet ...")
12 ['test', 'train', 'val'] ['example_id', 'event_id', 'record_id', 'task_id', 'seed', 'step', 'cut', 'cut_index', 'n_cuts', 'depth', 'text', 'tool', 'call', 'args', 'weight', 'split', 'env', 'agent_model', 'version']
```
Non-zero row count, `['test', 'train', 'val']`, and the full declared `training_data.SCHEMA` column list in order — matches exactly.

**F3 — every gate of 2.5 fires and names what it found.**
```
=== missing_record ===
exit=1
ValueError: build: 1 requested (task_id, seed) pair(s) have no done record in .../records: [('82e2fac_1', 42)]
=== abort ===
exit=1
ValueError: build: 1/6 records aborted (share 0.1667) exceeds build.max_abort_frac=0.0
=== orphan_gen ===
exit=1
ValueError: build: record 82e2fac_1__s42 step 9: a gen row has no matching env row
=== two_splits ===
exit=1
ValueError: build: task id(s) ['50e1ac9_1'] appear in both splits 'dev' and 'train'
=== unknown_task ===
exit=1
ValueError: build: 1 requested (task_id, seed) pair(s) have no done record in .../records: [('82e2fac_3', 42)]
=== bad_call ===
exit=1
ValueError: build: example 82e2fac_1__s42|s4|c0: call 'apis.phone.search_contacts()' does not round-trip through split_args/build_call (built from tool='apis.phone.search_contacts' args=[('query', 'alice')], re-parsed to ('apis.phone.search_contacts', [], (0, 28)))
=== bad_text ===
exit=1
ValueError: build: example 82e2fac_1__s42|s0|c0: text does not end with the thinking prefix at cut 73
```
All seven exit non-zero and name the row's right-hand-column content. `unknown_task` fires via the completeness gate rather than the split gate, as documented above and in the ticket's Comments as an accepted, known defect of the fixture's construction — it still names a task id.

**F4 — the three skip-and-count cases are skipped, not raised, and counted.**
```
$ ... build exit=0
6 6 6 30 12
skipped events present in examples.parquet: []
```
`events_skipped_no_action=6`, `events_skipped_no_call=6`, `events_skipped_short_think=6`, `events=30`, `examples=12` (non-zero), and no skipped step's event id appears in `examples.parquet`. Matches exactly.

**F5 — `consumed.json` names both kinds of input.**
```
6 3
True
```
Six record files, three split files, every entry carries `sha1`. Matches exactly.

**F6 — the per-split cap is deterministic.**
```
$ ... A exit=0
$ ... B exit=0
deterministic cap ok 3 ['test', 'train', 'val']
```
One row per split, identical `DataFrame.equals` across two independent builds. Matches exactly.

**F7 — the history rule matches the live side.**
```
$ ... build exit=0
"Task: Play my playlist.\n[HISTORY]\nprint(apis.supervisor.show_profile()) -> {'name': 'alice'}\nprint(len('inspecting the namespace')) -> 24\nprint(apis.supervisor.show_profile()) -> {'name': 'alice'}\n[THINKING]\nI will look at the supervisor profile first, then decide what to do next."
no-code observation absent: True
api-less action present: True
api-less result present: True
```
Matches exactly — the null-action step's `NO_CODE_BLOCK` observation never entered history; the api-less step's action and result did.

**`run.py selfcheck`**: `run.py` does not exist yet on this branch (confirmed: `find . -maxdepth 1 -name run.py` finds nothing), so per the implementer protocol and spec.md section 7 I did not attempt to run it. The ticket's "Selfcheck lines that apply later" section states what a future `run.py selfcheck` will check over this file; nothing in it required action now.

**Fixture cleanup.** I made 12 fixture trees via `mktemp -d` over this session (1 for A1/F1's setup script write, then one each for `ok` (F2), the seven F3 gate variants, `ok` again (F4), two for F6's determinism comparison, and `ok` again for F7). All 12 were deleted at the end (`rm -rf`), along with the scratch `/tmp/g_*.txt` gate-output files and `/tmp/mkbuildfix.sh` itself. None of the fixtures touched the real NFS outputs root or the repo's own `constants/`; each used its own private `outputs/` subtree and its own copies of the three split files, per the fixture script's own design.

## Commits

- `2be4f0688b4b93137ff1d871f74e68c840ad051e` — T09: the dataset builder (`data/build_training_dataset.py`), plus its `README.md` entry.

## Self-review findings

- Diff is scoped to exactly what the ticket asked for: one new file plus one README section. No test file was added (the ticket names no `tests/` seam for this ticket, and spec.md section 2 reserves `tests/` for the two named checks of tickets 03 and 13).
- Every acceptance command's real output is pasted above; none were edited to pass.
- No citation of `legacy/` appears anywhere in `data/build_training_dataset.py` (checked with `grep -n legacy`); the two legacy files this ticket ports from (`legacy/pipeline/annotate/build.py`, `legacy/pipeline/annotate/check_callstr.py`) are cited only in this report and in the ticket, per spec.md section 5.
- No `/home/` or `/net/` literal path appears in the file (checked with `grep`); the one filesystem path resolution (`constants/path_datasets.yaml`) uses `Path(__file__).resolve().parents[1]`, matching the pattern `data/environments/appworld.py` already uses.
- `python3 -m py_compile` on the file succeeds (a cheap sanity check; A1 already covers real imports under the three venvs).

## Open questions

None that block this ticket. One item worth the main session's attention at wave merge: this worktree's base (`28735bb`) predates tickets 07 and 08 landing in this branch, so my README.md addition only has ticket 09's section — the merge will need to combine it with whatever ticket 07 and 08 add, per spec.md section 3's explicit allowance for that.
