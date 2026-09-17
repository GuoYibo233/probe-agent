# T02 report: the three on-disk formats and the probe's input

Ticket: `.scratch/from-zero/issues/02-data-formats-and-probe-input.md`
Branch: `ticket/2026-09-17-wave1/T02`, worktree `new1-wt/2026-09-17-wave1-T02`
Base: `cca3ca3a506cf5b2a8d990e641ec160e40e8465f`
Head: `8b48e98`

## What was done

Five files, all `venv: any`, exactly the ticket's list:

- `data/__init__.py` — `record_id`, `event_id`, `example_id`; `read_frame`
  (missing/empty raise, own-schema read, null-as-absent, `present` selection,
  required-column raise naming the column/path/recorded version, version-above
  raise, the type-check-by-reading step catching `pl.exceptions.ComputeError`
  and `pl.exceptions.InvalidOperationError` and re-raising naming the path,
  default-filling, declared-order `select`); `write_frame` (parquet-only,
  raises naming the suffix otherwise, temp-file-then-`os.replace`). No
  `VERSION` line, per the ticket.
- `data/probe_input.py` — `VERSION = 1`, `SENT_RE`, `cuts` (offline
  enumeration with even thinning, raises on `max_cuts < 2`), `cuts_live`
  (streaming enumeration, no terminal cut, no thinning), `_clip` and
  `assemble` (raises on `probe_result_cap < 100`). All three pure, no module
  constants beyond `SENT_RE`.
- `data/task_record.py` — `VERSION = 1`, the 64-column `SCHEMA` (declaration
  order taken from contracts 1.1's per-kind column table, deduplicating
  `error_kind`, `stop_reason`, `fire_index`, `wall_s`), `DEFAULTS` (`None`
  except `n_inject -> 0`), the twelve-column `REQUIRED` exactly as the ticket
  gives it, `record_path`, `open_record` (`O_EXCL` claim), `Writer` (`row`
  stamps `type`/`ts` and, on `meta`, `version`/`record_id`; raises naming the
  column and row kind on a caller-supplied stamped column or an undeclared
  field; flushes and `fsync`s every row; `frame()` builds the DataFrame from
  the in-memory row list, never re-reading the file), `is_done` (tail read,
  not a full-file read), `owner` (first-line read), `done_pairs`, `release`
  (unfinished + unowned-but-live-owner deletion, unowned-and-stale deletion by
  age, done files never touched), `read` (fills `record_id` from the `meta`
  row), `read_dir`, `to_messages` (exclusive `upto_step`, `no_code` on a null
  action, `extra_developer` appended with `"\n\n"`).
- `data/example.py` — `VERSION = 1`, the 19-column `SCHEMA` in the ticket's
  literal order, `DEFAULTS`, `REQUIRED` exactly as given, `write` (stamps
  `version`, fills any `SCHEMA` column the caller's frame does not carry from
  `DEFAULTS`, selects declared order, calls `write_frame`), `read`.
- `data/prediction.py` — `VERSION = 1`, the 14-column `SCHEMA`, `DEFAULTS`,
  `REQUIRED` exactly as given, `write` (same fill/select/stamp pattern as
  `example.py`), `read`.
- `README.md` — created (did not exist yet on this branch's base); holds only
  this ticket's five `data/` tree lines, per spec section 3's "your own files'
  lines only" and the expectation that ticket 14 assembles the rest.

## How it was verified

All commands run from the worktree root (repo root of the branch).

**A1 — imports under all three venvs.**
```
imports ok 3.11.15
imports ok 3.12.13
imports ok 3.12.13
```

**A2 — `probe_input.py` under system `python3`.**
```
probe_input imports on 3.10.12
```

**A3 — VERSION line shape.**
```
data/task_record.py 1
data/example.py 1
data/prediction.py 1
data/probe_input.py 1
NO_VERSION
```

**A4 — REQUIRED/DEFAULTS cover SCHEMA.**
```
REQUIRED/DEFAULTS cover SCHEMA in all three formats
```

**B1 — the id chain.**
```
50e1ac9_1__s42 50e1ac9_1__s42|s3 50e1ac9_1__s42|s3|c2
```

**B2 — `write_frame`/`read_frame` round trip and the five raises.**
```
roundtrip+defaults ok
required raise ok
version raise ok
null-column-as-absent ok
wrong-type raise ok
write_frame suffix raise ok
```

**C1 — the two cut rules.**
```
cuts ok
```

**C2 — `assemble`.**
```
assemble ok
```

**D1 — the claim, six kinds, round trip, readers, `to_messages`, `release`.**
Run under all three interpreters (`$AW`, `$PR`, `$VL`); each printed:
```
stamped columns refused
abort-only record ok
task_record ok
```

**D2 — a killed writer's file reads to its last flushed row.**
```
flush-per-row ok
```

**E1 — example and prediction writers/readers.** Run under `$AW`, `$PR`, `$VL`:
```
example+prediction ok
```

**E2 — a generator's prediction row reads back with classifier columns null.**
```
generator prediction ok
```

`run.py selfcheck` does not exist yet (ticket 15, wave 6); the ticket's
"selfcheck lines that apply later" were checked by hand above (A1–A4) and by
inspection: `grep -rn "legacy" data/` and `grep -rn "/home/\|/net/" data/` both
return no matches.

## Commit list

- `8b48e98` — T02: data package conventions, task record, example, prediction,
  probe input (all five files + README.md, one commit).

## Self-review findings and open questions

- **Contracts/ticket omission on `task_record.py`'s import line (fixed in the
  README, flagged here):** both the ticket's file table and contracts 0.2 list
  `data/task_record.py`'s imports as `data/__init__.py` alone, with no
  `[polars]` bracket, unlike `example.py`/`prediction.py` which do list it.
  But `task_record.py`'s `SCHEMA` dict holds live `pl.Utf8`/`pl.Int32`/…
  instances (needed regardless of `from __future__ import annotations`, which
  only defers *annotations*, not this dict's *values*), so the file must
  `import polars as pl` to run. I import it and wrote the README line as
  `imports: data/__init__.py; [polars]` to match what the code actually does,
  since `run.py selfcheck`'s future `ast`-parsed-import-graph check (ticket 15)
  would otherwise fail this file's README line against its real imports. This
  is a correction for accuracy, not a requirements change — the contracts and
  ticket sections that matter (1.1's signatures, the column table, the
  `REQUIRED` set) are unaffected.
- **`write()` on `example.py`/`prediction.py` fills missing `SCHEMA` columns
  from `DEFAULTS` before selecting**, rather than a bare `stamp version +
  select`. The ticket's one-line gloss ("stamps version, selects SCHEMA order,
  calls write_frame") reads as a plain select, but acceptance **E2** writes a
  generator's prediction row with the classifier columns (`score`,
  `label_pred`, `logits`) entirely absent from the input frame, which a bare
  `.select(list(SCHEMA))` would raise `ColumnNotFoundError` on. Filling absent
  declared columns from `DEFAULTS` (mirroring `read_frame`'s own fill step) is
  what makes E2 pass and is, I believe, the intended reading — flagging it
  since it is a design choice beyond the ticket's one-line description of
  `write`.
- `Writer.row` calls `os.fsync` on every row in addition to `flush()`. The
  ticket only names "writes one JSON object and flushes"; I added `fsync` for
  the durability the surrounding contract prose argues for ("a killed piece
  keeps everything it wrote"). This is strictly additional durability, not a
  behavior change any acceptance command depends on, and costs one syscall per
  row.
- `data/task_record.py`'s `SCHEMA` declaration order is not spelled out as a
  literal dict in the ticket (unlike `example.py`/`prediction.py`, which give
  the dict verbatim); I derived it by reading the ticket's two-column table
  column-major (left column top-to-bottom, then right column), which
  reproduces exactly contracts 1.1's per-kind table order (`all` → `meta` →
  `gen` → `spec` → `resume`-unique → `env`-unique → `final`) once the four
  cross-kind duplicates are collapsed to one column each. No acceptance
  command checks `task_record.SCHEMA`'s column order directly, so this is a
  documentation-fidelity note rather than a test risk.
- Did not add anything beyond the ticket's five files (no `utils.py`, no test
  file — the ticket names no test seam for this ticket).
- No `legacy/` citation appears in any shipped file; the legacy line ranges
  used while porting `cuts`/`cuts_live`/`assemble`/the `Writer` design are
  cited above and in the ticket only.
- `M-D2` (the cross-host claim race) is explicitly marked "GPU / main
  session — not yours" in the ticket; not attempted here.

## Fix round 1

Worktree `new1-wt/2026-09-17-wave1-T02-fix1`, branch `ticket/2026-09-17-wave1/T02`
(existing branch, checked out fresh). Base for this round: `8b48e98` (the
round-0 commit). Head after this round: `80b0d01`.

Two open findings, both against `data/task_record.py`.

**F1 (critical) — README's `task_record.py` imports line did not match the
ticket/contracts text.** The round-0 report already named this as a deliberate
self-correction (`imports: data/__init__.py; [polars]`, since the file does
`import polars as pl` for its `SCHEMA` dict's live dtype values). The finding
holds regardless of that rationale: both the ticket's file table and contracts
0.2 give this line as exactly `imports: data/__init__.py`, with no `[polars]`
bracket, so the shipped line was a literal deviation from the specified text.
Fixed by changing the README line back to the ticket's/contracts' exact text,
removing the `; [polars]` bracket. No code changed — `data/task_record.py`
still does `import polars as pl`, since the file's own correctness was never
in question, only the README line's wording.

**F2 (important) — `Writer.row` called `os.fsync` on every row, beyond what
the ticket/contracts specify.** The ticket's gloss ("writes one JSON object
and flushes") and contracts' Part 1 prose ("flushed after each row, so a
killed piece keeps everything it wrote") both name `flush()` only. Removed the
`os.fsync(self._file.fileno())` call from `Writer.row`, keeping `flush()`
alone. `flush()` already gives the property the spec asks for (visibility to
any other reader via the OS page cache on a killed process); `fsync` only adds
protection against a hardware/power failure, which neither the ticket nor its
D2 acceptance test (kills the writer with `del w`, not the OS) exercises, and
this file's row-writing path is the live agent loop's hot path once
`agent/loop.py` (a later ticket) calls it at full step frequency, commonly
against an NFS run directory.

### How it was verified

All commands run from the fix-round-1 worktree root, same interpreters as
round 0.

**A1 — every file imports under all three venvs (unaffected by the fix, rerun
to confirm nothing broke).**
```
imports ok 3.11.15
imports ok 3.12.13
imports ok 3.12.13
```

**A3 — the `VERSION` line shape (unaffected, rerun to confirm).**
```
data/task_record.py 1
data/example.py 1
data/prediction.py 1
data/probe_input.py 1
NO_VERSION
```

**A4 — `REQUIRED`/`DEFAULTS` cover `SCHEMA` (unaffected, rerun to confirm).**
```
REQUIRED/DEFAULTS cover SCHEMA in all three formats
```

**D1 — the claim, six kinds, round trip, readers, `to_messages`, `release`.**
Run under all three interpreters (`$PR`, `$AW`, `$VL`), the test directly
exercising `Writer.row` after the fsync removal; each printed:
```
stamped columns refused
abort-only record ok
task_record ok
```

**D2 — a killed writer's file reads to its last flushed row.** This is the
acceptance command most directly targeted by F2's fix (it kills the writer
mid-record with `del w`, no `close()`, and checks the file still reads back
its flushed rows):
```
flush-per-row ok
```
`flush()` alone is sufficient for this command to pass, confirming F2's
reasoning that `fsync` added nothing the acceptance suite checks.

**Self-review of the diff:** `git diff` against the round-0 commit shows
exactly two lines changed (the README import line, the removed `fsync` call)
and one line removed with it; no other file touched, no `legacy/` citation or
`/home/`/`/net/` path introduced (`grep -rn "legacy" data/` and
`grep -rn "/home/\|/net/" data/` both empty).

### Commit list

- `80b0d01` — T02: fix round 1 - match ticket's task_record.py imports line,
  drop per-row fsync.
