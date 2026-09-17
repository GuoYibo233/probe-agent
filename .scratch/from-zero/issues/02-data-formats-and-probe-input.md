# 02 the three on-disk formats and the probe's input

Status: resolved
Blocked by: (none)
Spec: .scratch/from-zero/spec.md (sections 2, 3, 4, 5, 7)

## What to do

Five files, all `venv: any`, all importing nothing from the repo except
`data/__init__.py`. Contracts Part 1 (the shared conventions), 1.1 (the task
record), 1.2 (the example), 1.3 (the prediction) and 1.7 (the probe's input) are
the specification; read them in full.

```
data/__init__.py        venv any   imports: none (repo); [polars]      carries NO VERSION
data/probe_input.py     venv any   imports: none (repo); [re]          VERSION = 1
data/trajectory_record.py     venv any   imports: data/__init__.py           VERSION = 1
data/training_data.py         venv any   imports: data/__init__.py; [polars] VERSION = 1
data/probe_output.py      venv any   imports: data/__init__.py; [polars] VERSION = 1
README.md               your five lines only
```

Build order inside the ticket: `data/__init__.py` and `data/probe_input.py`
first (neither imports the other), then the three format files.

### 1. `data/__init__.py` (contracts Part 1)

```python
def record_id(task_id: str, seed: int) -> str          # f"{task_id}__s{seed}"
def event_id(record_id: str, step: int) -> str         # f"{record_id}|s{step}"
def example_id(event_id: str, cut_index: int) -> str   # f"{event_id}|c{cut_index}"

def read_frame(path: Path, *, schema: dict, defaults: dict,
               required: frozenset[str], version: int) -> DataFrame
def write_frame(path: Path, df: DataFrame, *, schema: dict) -> None
```

`schema` is `dict[str, polars.DataType]`, column name to Polars dtype, in the
order the format declares its columns; `read_frame` returns the columns in that
order (errata: "Part 1 (`schema`'s value type)").

`read_frame`, in this order:

1. Raise, naming the path, when the file is missing or empty.
2. Read **the file's own schema** without reading the data:
   `pl.read_parquet_schema(path)` for `.parquet`,
   `dict(pl.scan_ndjson(path, infer_schema_length=None).collect_schema())` for
   `.jsonl`.
3. Treat a file column whose dtype is Polars `Null` as **absent**: a jsonl column
   every line writes as JSON `null` infers as `Null`, and that is an absent
   column, not a wrong type (errata).
4. `present = {name: schema[name]}` for every declared name the file still holds
   — the **declared** dtype, never the file's inferred one. A column the file
   holds and the format does not declare is dropped here.
5. Raise, naming the column, the path and the file's recorded version, for every
   name in `required` absent from `present`.
6. The file's recorded version is the **maximum non-null value of the declared
   `version` column**, and 0 when that column is absent (errata). Raise when it
   is above `version`.
7. Read: `pl.read_ndjson(path, schema=present)` for jsonl,
   `pl.read_parquet(path, columns=list(present)).cast(present, strict=True)` for
   parquet. **That read is the wrong-type check** (errata: a dtype comparison
   cannot be the check, because a JSON integer always infers as `Int64` against a
   declared `Int32`). Both forms raise on a value the declared dtype cannot hold
   — measured 2026-09-17, a jsonl `"abc"` under a declared `Int32` gives
   `ComputeError: cannot parse 'abc' (string) as Int32`, the parquet cast gives
   `InvalidOperationError`. Catch both and re-raise naming the path. Widening is
   silent and intended: a JSON integer reads back as the declared `Int32`, a JSON
   list as `List(Int32)`, a struct missing a field as that field null.
8. Add every declared column still absent as
   `pl.lit(defaults[name], dtype=schema[name]).alias(name)` and `select` the
   declared order.

`write_frame` accepts `.parquet` **only** and raises, naming the suffix, on
anything else (errata): a task record's jsonl is written row by row by
`Writer.row` under Part 1's flush rule, so no jsonl bulk writer has a caller. It
writes `<path>.tmp-<pid>` in the same directory and `os.replace`s it onto `path`.

This file carries **no** `VERSION` line: 0.2 gives it none and no version list in
2.2 names it. Legacy source: none, the file is new (today every script
hand-parses jsonl, `legacy/pipeline/annotate/build.py:67`,
`legacy/pipeline/annotate/check_callstr.py:254`).

### 2. `data/probe_input.py` (contracts 1.7)

```python
VERSION = 1
SENT_RE = re.compile(r"(?<=[.!?])\s+|\n")      # legacy/pipeline/annotate/rules.py:26

def cuts(thinking: str, min_think: int, max_cuts: int) -> list[int]
def cuts_live(thinking_so_far: str, min_think: int) -> list[int]
def assemble(task: str, history: list[tuple[str, str]],
             thinking_prefix: str, hist_rounds: int, probe_result_cap: int) -> str
```

All three are pure: every parameter is passed in, nothing is read from a file, no
setting value is a module constant. That is what keeps the offline caller
(`data/build_training_dataset.py`) and the live caller (`agent/inject.py`) from drifting.

`cuts` is the offline enumeration, ported from
`legacy/pipeline/annotate/rules.py:29-47` (`boundaries`) with `MAX_BOUNDS` and
`MIN_THINK` turned into parameters:

```python
if max_cuts < 2: raise ValueError(...)                       # names max_cuts
pts = sorted({m.end() for m in SENT_RE.finditer(thinking)} | {len(thinking)})
pts = [p for p in pts if len(thinking[:p].strip()) >= min_think // 2]
if not pts: pts = [len(thinking)]
if len(pts) > max_cuts:
    keep = {len(pts) - 1}
    step = (len(pts) - 1) / (max_cuts - 1)
    keep.update(round(k * step) for k in range(max_cuts - 1))
    pts = [pts[j] for j in sorted(keep)]
return pts
```

`cuts_live` is the streaming enumeration, ported from
`legacy/pipeline/inject/live_appworld.py:165-175` (`sent_starts`): `m.start()`
offsets, the same `min_think // 2` per-cut filter, **no** terminal cut and **no**
thinning. Its docstring carries 1.7's three reasons, and both this file's and
`data/trajectory_record.py`'s README lines say that `example.cut` and `spec.cut` are
not the same coordinate.

`assemble` is ported from `legacy/pipeline/annotate/rules.py:50-62`
(`clip` + `assemble`) with `HIST_ROUNDS` and `RESULT_CAP` turned into parameters:

```python
def _clip(s: str, cap: int) -> str:
    if cap < 100: raise ValueError(...)                       # names probe_result_cap
    s = str(s)
    return s if len(s) <= cap else s[: cap - 60] + " ...[cut]... " + s[-40:]

lines = [f"Task: {task}", "[HISTORY]"]
lines += [f"{a} -> {_clip(r, probe_result_cap)}" for a, r in history[-hist_rounds:]] or ["(start)"]
lines += ["[THINKING]", thinking_prefix]
return "\n".join(lines)
```

Not ported from `rules.py`: every module constant (`SEED`, `MAX_BOUNDS`,
`MIN_THINK`, `HIST_ROUNDS`, `RESULT_CAP`, `MODEL_OF`, `:17-23`) — they are
setting fields now; `split_args`, `first_call_args`, `split_args_named`,
`first_call_named`, `mkparams`, `AW_CALL`, `BFCL_CALL` (`:67-178`) — call syntax
is the environment's (ticket 05); the whole ALFWorld block (`:181-305`).

### 3. `data/trajectory_record.py` (contracts 1.1)

Layout: `<run_dir>/records/<task_id>__s<seed>.jsonl`.

**Decision already made (errata):** every offered function takes the **run
directory** as `dir`, and this file appends `records/` itself. No caller anywhere
in the tree spells that subdirectory.

```python
VERSION = 1
SCHEMA: dict[str, polars.DataType]   # every column of all six row kinds, below
DEFAULTS: dict[str, Any]             # every declared column -> None, except n_inject -> 0
REQUIRED: frozenset[str]             # below

def open_record(dir: Path, task_id: str, seed: int) -> Writer | None
def record_path(dir: Path, task_id: str, seed: int) -> Path
class Writer:
    def row(self, kind: str, **fields) -> None
    def frame(self) -> DataFrame
    def close(self) -> None
def is_done(path: Path) -> bool
def owner(path: Path) -> str | None
def done_pairs(dir: Path, pairs: list[tuple[str, int]]) -> set[tuple[str, int]]
def release(dir: Path, live_sessions: set[str], unowned_age_s: float) -> list[Path]
def read(path: Path) -> DataFrame
def read_dir(dir: Path, pairs: list[tuple[str, int]]) -> DataFrame
def to_messages(df: DataFrame, upto_step: int, task_text: str, instructions: str,
                no_code: str, extra_developer: str | None) -> list[dict]
```

`SCHEMA`, in declaration order, from 1.1's column table (one column per name;
`error_kind`, `stop_reason`, `fire_index` and `wall_s` appear on two kinds each
with the same dtype and are one column):

| column | dtype | | column | dtype |
|---|---|---|---|---|
| `type` | `Utf8` | | `n_inject` | `Int32` |
| `step` | `Int32` | | `discard` | `Struct({"chars": Int64, "tokens": Int64, "events": Int32})` |
| `ts` | `Float64` | | `fire_index` | `Int32` |
| `version` | `Int32` | | `cut` | `Int32` |
| `record_id` | `Utf8` | | `n_checked` | `Int32` |
| `stage` | `Utf8` | | `conf` | `Float64` |
| `env` | `Utf8` | | `pred_label` | `Utf8` |
| `task_id` | `Utf8` | | `gen_call` | `Utf8` |
| `seed` | `Int64` | | `exec_code` | `Utf8` |
| `env_seed` | `Int64` | | `arg_modes` | `List(Utf8)` |
| `split` | `Utf8` | | `exec_out` | `Utf8` |
| `arm` | `Utf8` | | `exec_ok` | `Boolean` |
| `instructions` | `Utf8` | | `error_kind` | `Utf8` |
| `task_text` | `Utf8` | | `note` | `Utf8` |
| `agent_model` | `Utf8` | | `format` | `Utf8` |
| `generation` | `Utf8` | | `head_tok` | `Int32` |
| `inject` | `Utf8` | | `head_chars` | `Int32` |
| `commit` | `Utf8` | | `note_tok` | `Int32` |
| `run_key` | `Utf8` | | `discarded_chars` | `Int32` |
| `owner_session` | `Utf8` | | `overflow_ids` | `List(Int32)` |
| `reasoning` | `Utf8` | | `spec_s` | `Float64` |
| `content` | `Utf8` | | `overflow_tok` | `Int32` |
| `usage` | `Struct({"in": Int64, "out": Int64})` | | `new_tok` | `Int32` |
| `wall_s` | `Float64` | | `match_len` | `Int32` |
| `finish_reason` | `Utf8` | | `identical` | `Boolean` |
| `stop_reason` | `Utf8` | | `action` | `Utf8` |
| `prefix_tok` | `Int32` | | `result` | `Utf8` |
| `prefix_sha` | `Utf8` | | `steps` | `Int32` |
| `gen_ids` | `List(Int32)` | | `completed` | `Boolean` |
| | | | `abort` | `Utf8` |
| | | | `judge` | `Utf8` |
| | | | `success` | `Boolean` |
| | | | `tokens_in` | `Int64` |
| | | | `tokens_out` | `Int64` |
| | | | `finished_at` | `Float64` |

```python
REQUIRED = frozenset({"type", "ts", "version", "record_id", "stage", "env",
    "task_id", "seed", "split", "task_text", "agent_model", "owner_session"})
```

**The rule that fixes this set (errata, "Part 1 (`read_frame` and a null
column)"):** an all-null column reads as **absent**, so a name may be in
`REQUIRED` only when **every record file `read` must accept carries at least one
non-null value for it**. The twelve above are exactly the `meta`-row columns
`agent/loop.py` writes on every record, and the `meta` row is the first row of
every record file (ticket 11). Everything else is out, and each exclusion has a
file that would otherwise be refused:

| out | the valid file that has it all-null |
|---|---|
| `action`, `abort` | a finished record where no step produced an action, and any record that did not abort |
| `step`, `reasoning`, `content` | a record that aborts before its first `gen` row — a 400 on step 0 writes `abort="context_overflow_400"` (7.1) and any other exception writes `abort="task_error:…"` (errata), both after the `meta` row and before any `gen` row, leaving a two-row `meta`+`final` file that `is_done` calls done and `read_dir` therefore reads |
| `result` | the same two-row file, plus any record whose `env` rows all carry a null `result` |
| `steps`, `completed`, `judge`, `success`, `tokens_in`, `tokens_out`, `wall_s`, `finished_at` | a killed writer's file, which has no `final` row at all and which `read` must still return to its last flushed row (`D2`) |
| every `spec` / `resume` column | a `sample` record has no such row |

`D1`'s two-row case and `D2` are the executable form of the last two rows of that
table; a `REQUIRED` that names a column outside the twelve fails one of them.

Behaviour:

- `open_record` performs `os.open(path, O_CREAT | O_EXCL | O_WRONLY, 0o644)` of an
  **empty** file and returns the `Writer`; on `FileExistsError` it returns `None`
  (1.1, "Claiming"). It writes no `meta` row: `meta.task_text` only exists after
  `Environment.open`, so the caller's first `row("meta", ...)` is that row.
- `Writer.row(kind, **fields)` writes one JSON object and flushes
  (`legacy/pipeline/inject/live_appworld.py:291-299`). It stamps `type=kind` and
  `ts` on every row and, on a `meta` row, `version=VERSION` and
  `record_id=record_id(task_id, seed)`; every other column is the caller's, and
  an undeclared field name raises (errata). **A caller that passes one of the
  four stamped columns — `type`, `ts`, `version`, `record_id` — also raises,
  naming the column and the row kind** (errata): the stamp is their one writer,
  and silently accepting a second value for a column the writer owns is how two
  spellings of one id get into a record. **`ts` is read with
  `time.clock_gettime(time.CLOCK_REALTIME)`, never `time.time()`** — an open
  AppWorld world freezes the driver process's clock, and a loop piece writes
  these rows with a world open (errata, measured 2026-09-17: every `gen.wall_s`
  in the legacy live run is `0.0`).
- `Writer.frame()` returns the rows written so far, held in memory, in the same
  column order and dtypes `read` returns.
- `is_done(path)`: the last line parses and its `type` is `final`, **whatever
  `abort` says**. Read the tail, not the file.
- `owner(path)`: the first line parses as a `meta` row -> its `owner_session`;
  otherwise `None`.
- `done_pairs(dir, pairs)` builds each candidate path with `record_path` and
  returns the subset of `pairs` whose file `is_done`, reading one line per file.
- `release(dir, live_sessions, unowned_age_s)` deletes, and returns, (a) every
  unfinished record file whose `owner(path)` is not in `live_sessions`, and (b)
  every record file whose first line does not parse as a `meta` row and whose
  mtime is older than `unowned_age_s` seconds. Both callers pass
  `registry.live_sessions()` and `registry.DEFAULTS["launch_timeout_s"]` in, which
  is what keeps this file's imports at `data/__init__.py` alone.
- `read(path)` = `read_frame(path, schema=SCHEMA, defaults=DEFAULTS,
  required=REQUIRED, version=VERSION)`, then fills `record_id` on **every** row
  from that file's `meta` row (errata), so a concatenated frame is groupable.
- `read_dir(dir, pairs)` reads exactly the files of `pairs`, skips every file
  whose `is_done` is false, and concatenates.
- `to_messages(df, upto_step, task_text, instructions, no_code, extra_developer)`
  returns `[{"role": "developer", "content": instructions + ("\n\n" +
  extra_developer if extra_developer is not None else "")}, {"role": "user",
  "content": task_text}]` and then, for each step `s < upto_step` in increasing
  order (`upto_step` is **exclusive**), `{"role": "assistant", "content": <that
  step's gen.content>}` followed by `{"role": "user", "content": <that step's
  env.result> if <env.action> is not null else no_code}`. An earlier step's
  `reasoning` is **never** resent
  (`legacy/envs/collect/run_appworld.py:191-215`).

Legacy sources: `legacy/pipeline/inject/live_appworld.py:290-299` (`class W`),
`:34-42` and the write sites `:295,405,515,798,806,812,834` (the six kinds and
their fields), `:590-603` (the `.claims/` `mkdir` ticket this replaces);
`legacy/envs/collect/run_appworld.py:180` (`is_done`), `:189-234` (the sample
side's four kinds), `:191-215` (the conversation shape).

Not ported: the `.claims/` directory and its wipe-before-start; `traj_meta`'s
free-form dict (`run_appworld.py:189`); `final.eval` in its two legacy shapes
(`run_appworld.py:231`, `live_appworld.py:834`) — one shape now, `judge` as
canonical JSON text plus a declared boolean `success`; the resume-by-skip that
overwrote a not-done file (`run_appworld.py:180-184`).

### 4. `data/training_data.py` (contracts 1.2)

```python
VERSION = 1
SCHEMA = {   # in this order
  "example_id": Utf8, "event_id": Utf8, "record_id": Utf8, "task_id": Utf8,
  "seed": Int64, "step": Int32, "cut": Int32, "cut_index": Int32,
  "n_cuts": Int32, "depth": Float32, "text": Utf8, "tool": Utf8, "call": Utf8,
  "args": List(Struct({"key": Utf8, "value": Utf8})),
  "weight": Float32, "split": Utf8, "env": Utf8, "agent_model": Utf8,
  "version": Int32,
}
DEFAULTS = {every declared column: None}
REQUIRED = frozenset({"example_id","event_id","record_id","task_id","seed","step",
  "cut","cut_index","n_cuts","depth","text","tool","call","weight","split","version"})

def write(path: Path, df: DataFrame) -> None   # stamps version, selects SCHEMA order, calls write_frame
def read(path: Path) -> DataFrame              # read_frame with this file's four literals
```

`args` is out of `REQUIRED` because 1.2 gives it one reader, the build gate,
inside the stage that writes it; `env` and `agent_model` are out because no
downstream file reads them.

Legacy source: the sample dict of `legacy/pipeline/annotate/build.py:216-227`
(`make_samples`), key for key: `text`->`text`, `label`->`tool`, `w`->`weight`,
`depth`->`depth`, `sent_idx`->`cut_index`, `n_sents`->`n_cuts`,
`event`->`event_id`, `traj`->`record_id`, `unit`->`task_id`, `step`->`step`,
`label_call`->`call`, `args_named`->`args`.

Not ported: the `model` column (`build.py:224`); the three separate
`train/val/test.jsonl` files (`build.py:390-393`) — one parquet with a `split`
column; `tool_vocab.json` (`build.py:404-406`) — the class order is
`head_labels`' and lives in `best/meta.json`.

### 5. `data/probe_output.py` (contracts 1.3)

```python
VERSION = 1
SCHEMA = {   # in this order
  "example_id": Utf8, "event_id": Utf8, "task_id": Utf8, "depth": Float32,
  "split": Utf8, "tool": Utf8, "method": Utf8, "target": Utf8,
  "score": Float32, "label_pred": Utf8, "logits": List(Float32),
  "text_pred": Utf8, "gen_tokens": Int32, "version": Int32,
}
DEFAULTS = {every declared column: None}
REQUIRED = frozenset({"example_id","event_id","task_id","depth","split","tool",
                      "method","target","version"})

def write(path: Path, df: DataFrame) -> None
def read(path: Path) -> DataFrame
```

The classifier trio (`score`, `label_pred`, `logits`) and the generator pair
(`text_pred`, `gen_tokens`) are out of `REQUIRED`: each is null for the other
`PROBE_KIND`, and an all-null column reads as absent.

Legacy source: none as a file — today the equivalent numbers are produced inside
the eval scripts and never written as a row format. The class order is **not**
kept here.

## Acceptance

Run every command from the repo root and paste its real output. `$P` stands for
each of the three interpreters in turn.

```bash
PR=/home/y-guo/reproduce/new1/external/probe-env/bin/python
AW=/home/y-guo/reproduce/new1/external/appworld/venv/bin/python
VL=/home/y-guo/reproduce/new1/external/vllm-env/bin/python
```

**A1 — every file imports under all three venvs.**
```bash
for P in "$PR" "$AW" "$VL"; do
  "$P" -c "import sys; sys.path.insert(0,'.');
import data, data.trajectory_record, data.training_data, data.probe_output, data.probe_input
print('imports ok', sys.version.split()[0])"
done
```
Expected: `imports ok 3.11.15`, `imports ok 3.12.13`, `imports ok 3.12.13`;
exit 0 each. (`data.build_training_dataset` is ticket 09 and is not in this list.)

**A2 — `data/probe_input.py` also imports under system `python3`** (3.10, no polars).
```bash
python3 -c "
import importlib.util as u
s = u.spec_from_file_location('pi', 'data/probe_input.py')
m = u.module_from_spec(s); s.loader.exec_module(m)
print('probe_input imports on', __import__('sys').version.split()[0])"
```
Expected: `probe_input imports on 3.10.12`; exit 0.

**A3 — the `VERSION` line shape (3.3).**
```bash
for f in data/trajectory_record.py data/training_data.py data/probe_output.py data/probe_input.py; do
  n=$(grep -c '^VERSION = [0-9][0-9]*$' "$f"); echo "$f $n"
done
test "$(grep -c '^VERSION' data/__init__.py)" = 0 && echo NO_VERSION
```
Expected: four lines each ending in ` 1`, then `NO_VERSION`, exit 0. The last
line is wrapped in `test` on purpose: `grep -c` **exits 1 when the count is
zero**, so a bare `grep -c ... ` expecting `0` would make a correct
implementation look like a failed command.

**A4 — `REQUIRED` names only declared columns, `DEFAULTS` covers `SCHEMA`.**
```bash
"$PR" -c "
import sys; sys.path.insert(0,'.')
import data.trajectory_record as tr, data.training_data as ex, data.probe_output as pr
for m in (tr, ex, pr):
    bad = sorted(set(m.REQUIRED) - set(m.SCHEMA))
    assert not bad, (m.__name__, bad)
    miss = sorted(set(m.SCHEMA) - set(m.DEFAULTS))
    assert not miss, (m.__name__, miss)
print('REQUIRED/DEFAULTS cover SCHEMA in all three formats')"
```
Expected: `REQUIRED/DEFAULTS cover SCHEMA in all three formats`; exit 0.

**B1 — the id chain.**
```bash
"$AW" -c "
import sys; sys.path.insert(0,'.')
from data import record_id, event_id, example_id
r = record_id('50e1ac9_1', 42); e = event_id(r, 3); x = example_id(e, 2)
assert r == '50e1ac9_1__s42', r
assert e == '50e1ac9_1__s42|s3', e
assert x == '50e1ac9_1__s42|s3|c2', x
print(r, e, x)"
```
Expected: `50e1ac9_1__s42 50e1ac9_1__s42|s3 50e1ac9_1__s42|s3|c2`; exit 0.

**B2 — `write_frame` / `read_frame`: the round trip, the filling, and the five raises.**
```bash
"$AW" - <<'PY'
import sys, tempfile, pathlib; sys.path.insert(0,'.')
import polars as pl
from data import read_frame, write_frame
S = {"a": pl.Utf8, "b": pl.Int32, "c": pl.Float32, "version": pl.Int32}
D = {"a": None, "b": None, "c": None, "version": None}
R = frozenset({"a", "version"})
d = pathlib.Path(tempfile.mkdtemp())

p = d/"x.parquet"
write_frame(p, pl.DataFrame({"a": ["z"], "b": [1], "version": [1]}), schema=S)
f = read_frame(p, schema=S, defaults=D, required=R, version=1)
assert list(f.columns) == ["a","b","c","version"], f.columns
assert f["c"].to_list() == [None] and f["c"].dtype == pl.Float32
print("roundtrip+defaults ok")

q = d/"y.parquet"
write_frame(q, pl.DataFrame({"b": [1], "version": [1]}), schema={"b": pl.Int32, "version": pl.Int32})
try:
    read_frame(q, schema=S, defaults=D, required=R, version=1); raise SystemExit("no raise")
except Exception as e:
    assert "a" in str(e) and str(q) in str(e), e
    print("required raise ok")

w = d/"z.parquet"
write_frame(w, pl.DataFrame({"a":["z"],"version":[9]}), schema={"a": pl.Utf8, "version": pl.Int32})
try:
    read_frame(w, schema=S, defaults=D, required=R, version=1); raise SystemExit("no raise")
except Exception as e:
    assert "9" in str(e), e
    print("version raise ok")

j = d/"r.jsonl"; j.write_text('{"a":"z","version":1,"b":7,"c":null}\n')
f = read_frame(j, schema=S, defaults=D, required=R, version=1)
assert f["c"].to_list() == [None] and f["c"].dtype == pl.Float32
assert f["b"].to_list() == [7] and f["b"].dtype == pl.Int32
print("null-column-as-absent ok")

k = d/"bad_type.jsonl"; k.write_text('{"a":"z","version":1,"b":"abc"}\n')
try:
    read_frame(k, schema=S, defaults=D, required=R, version=1); raise SystemExit("no raise")
except Exception as e:
    assert str(k) in str(e), e
    print("wrong-type raise ok")

try:
    write_frame(d/"bad.jsonl", pl.DataFrame({"a":["z"]}), schema={"a": pl.Utf8}); raise SystemExit("no raise")
except Exception as e:
    assert "jsonl" in str(e), e
    print("write_frame suffix raise ok")
PY
```
Expected, in order: `roundtrip+defaults ok`, `required raise ok`,
`version raise ok`, `null-column-as-absent ok`, `wrong-type raise ok`,
`write_frame suffix raise ok`; exit 0.

**C1 — the two cut rules, against values computed from the legacy code.**
```bash
python3 -c "
import importlib.util as u
s = u.spec_from_file_location('pi','data/probe_input.py'); m = u.module_from_spec(s); s.loader.exec_module(m)
T = 'I need the playlist. First I check the docs. Then I log in. Finally I print it.'
assert len(T) == 79
assert m.cuts(T, 40, 64) == [21, 45, 60, 79], m.cuts(T, 40, 64)
assert m.cuts(T, 40, 3)  == [21, 60, 79],     m.cuts(T, 40, 3)
assert m.cuts(T, 40, 2)  == [21, 79],         m.cuts(T, 40, 2)
assert m.cuts_live(T, 40) == [20, 44, 59],    m.cuts_live(T, 40)
assert m.cuts('', 40, 64) == [0]
assert m.cuts_live('', 40) == []
try:
    m.cuts(T, 40, 1); raise SystemExit('no raise')
except ValueError as e:
    assert 'max_cuts' in str(e), e
print('cuts ok')"
```
Expected: `cuts ok`; exit 0. The pair `[21,45,60,79]` against `[20,44,59]` is the
executable form of 1.7's "not the same coordinate".

**C2 — `assemble`, byte for byte against the legacy format.**
```bash
python3 -c "
import importlib.util as u
s = u.spec_from_file_location('pi','data/probe_input.py'); m = u.module_from_spec(s); s.loader.exec_module(m)
h = [('a1','r1'),('a2','r2'),('a3','r3'),('a4','r4')]
got = m.assemble('Buy milk', h, 'I think.', 3, 400)
assert got == 'Task: Buy milk\n[HISTORY]\na2 -> r2\na3 -> r3\na4 -> r4\n[THINKING]\nI think.', repr(got)
got = m.assemble('Buy milk', [], '', 3, 400)
assert got == 'Task: Buy milk\n[HISTORY]\n(start)\n[THINKING]\n', repr(got)
c = m.assemble('t', [('a','x'*500)], '', 1, 400)
obs = c.split('a -> ',1)[1].split('\n[THINKING]')[0]
assert len(obs) == 393 and ' ...[cut]... ' in obs, len(obs)
print('assemble ok')"
```
Expected: `assemble ok`; exit 0. (393 = `400 - 60 + 13 + 40`.)

**D1 — the claim, the six kinds, the round trip, the readers, `to_messages`, `release`.**
Run under all three interpreters.
```bash
"$AW" - <<'PY'
import sys, json, os, time, tempfile, pathlib; sys.path.insert(0,'.')
import data.trajectory_record as tr
d = pathlib.Path(tempfile.mkdtemp())          # d is the RUN DIRECTORY; records/ is appended inside

w = tr.open_record(d, "50e1ac9_1", 42)
assert w is not None
assert tr.open_record(d, "50e1ac9_1", 42) is None          # the O_EXCL claim
p = tr.record_path(d, "50e1ac9_1", 42)
assert p == d/"records"/"50e1ac9_1__s42.jsonl", p
assert not tr.is_done(p)
w.row("meta", stage="sample", env="appworld", task_id="50e1ac9_1", seed=42,
      env_seed=100, split="train", arm="sample", instructions="v1",
      task_text="Play my playlist.", agent_model="gptoss120b",
      generation="{}", inject=None, commit="deadbee", run_key="abc123def456",
      owner_session="sample-abc123def456-0")
w.row("gen", step=0, reasoning="I think. I check.", content="```python\nx\n```",
      usage={"in": 10, "out": 20}, wall_s=1.0, finish_reason="stop",
      stop_reason=None, prefix_tok=10, prefix_sha="aa", n_inject=0)
w.row("env", step=0, action="print(apis.spotify.show_playlists())",
      result="[]", error_kind=None)
w.row("gen", step=1, reasoning="Now done.", content="no code here",
      usage={"in": 30, "out": 5}, wall_s=1.0, finish_reason="stop", n_inject=0)
w.row("env", step=1, action=None, result="NO_CODE_BLOCK", error_kind=None)
fr = w.frame()
w.row("final", steps=2, completed=True, abort=None,
      judge='{"success": true}', success=True, tokens_in=40, tokens_out=25,
      wall_s=2.0, finished_at=time.clock_gettime(time.CLOCK_REALTIME))
w.close()

assert tr.is_done(p)
assert tr.owner(p) == "sample-abc123def456-0"
df = tr.read(p)
assert df.height == 6, df.height
assert set(df["type"].to_list()) == {"meta","gen","env","final"}
assert df["record_id"].to_list() == ["50e1ac9_1__s42"]*6       # broadcast
assert df["version"].max() == tr.VERSION
assert set(fr.columns) == set(df.columns)                      # Writer.frame matches read

wbad = tr.open_record(d, "stamped_1", 42)
for bad in ("record_id", "ts", "version", "type"):
    try:
        wbad.row("meta", task_id="stamped_1", seed=42, **{bad: "x"})
        raise AssertionError("a stamped column was accepted: " + bad)
    except AssertionError: raise
    except Exception as ex: assert bad in str(ex), (bad, str(ex))
wbad.close(); tr.record_path(d, "stamped_1", 42).unlink()
print("stamped columns refused")

assert tr.done_pairs(d, [("50e1ac9_1", 42), ("nope", 1)]) == {("50e1ac9_1", 42)}
dd = tr.read_dir(d, [("50e1ac9_1", 42), ("nope", 1)])
assert dd.height == 6

msgs = tr.to_messages(df, 2, "Play my playlist.", "DEV TEXT", "NO CODE", None)
assert [m["role"] for m in msgs] == ["developer","user","assistant","user","assistant","user"], msgs
assert msgs[0]["content"] == "DEV TEXT"
assert msgs[1]["content"] == "Play my playlist."
assert msgs[3]["content"] == "[]"
assert msgs[5]["content"] == "NO CODE"                          # a null action -> no_code
m2 = tr.to_messages(df, 2, "Play my playlist.", "DEV TEXT", "NO CODE", "EXTRA")
assert m2[0]["content"] == "DEV TEXT\n\nEXTRA"
assert tr.to_messages(df, 0, "t", "DEV", "NC", None) == [
    {"role":"developer","content":"DEV"}, {"role":"user","content":"t"}]

w2 = tr.open_record(d, "abc0000_2", 7)
w2.row("meta", stage="sample", env="appworld", task_id="abc0000_2", seed=7,
       env_seed=100, split="train", arm="sample", instructions="v1",
       task_text="t", agent_model="gptoss120b", generation="{}", inject=None,
       commit="deadbee", run_key="abc123def456", owner_session="gone-0")
w2.close()
fd = os.open(d/"records"/"zzz9999_3__s1.jsonl", os.O_CREAT|os.O_EXCL|os.O_WRONLY); os.close(fd)
os.utime(d/"records"/"zzz9999_3__s1.jsonl", (0, 0))            # older than the margin
gone = sorted(x.name for x in tr.release(d, {"sample-abc123def456-0"}, 1800))
assert gone == ["abc0000_2__s7.jsonl", "zzz9999_3__s1.jsonl"], gone
assert p.exists()

w3 = tr.open_record(d, "abort01_1", 5)          # a task that aborts before its first gen row
w3.row("meta", stage="inject", env="appworld", task_id="abort01_1", seed=5,
       env_seed=100, split="test", arm="probe", instructions="v1",
       task_text="t", agent_model="gptoss120b", generation="{}", inject="{}",
       commit="deadbee", run_key="abc123def456", owner_session="inject-abc123def456-0")
w3.row("final", steps=0, completed=False, abort="context_overflow_400",
       judge='{"success": false}', success=False, tokens_in=0, tokens_out=0,
       wall_s=0.5, finished_at=time.clock_gettime(time.CLOCK_REALTIME))
w3.close()
p3 = tr.record_path(d, "abort01_1", 5)
assert tr.is_done(p3)                           # a non-null abort still counts as done
a = tr.read(p3)                                 # step/reasoning/content/result are absent here
assert a.height == 2, a.height
assert a["step"].to_list() == [None, None], a["step"].to_list()
assert a["reasoning"].to_list() == [None, None] and a["content"].to_list() == [None, None]
assert a["result"].to_list() == [None, None]
assert a["abort"].to_list()[-1] == "context_overflow_400"
assert tr.read_dir(d, [("abort01_1", 5)]).height == 2
print("abort-only record ok")
print("trajectory_record ok")
PY
```
Expected: `stamped columns refused`, then `abort-only record ok`, then
`trajectory_record ok`; exit 0, under each of the three interpreters. The
`abort-only` block is the executable form of the `REQUIRED` rule above: the
record `agent/loop.py` writes when step 0 raises holds a `meta` row and a `final`
row and nothing else, so `step`, `reasoning`, `content` and `result` are absent
from its inferred schema. `is_done` is true for it, so `read_dir` — and through
it `data/build_training_dataset.py`'s completeness gate — reads it, and a `REQUIRED` that
names any of those four raises before the builder's abort-share gate can run.

**D2 — a killed writer's file is readable to its last flushed row.**
```bash
"$AW" - <<'PY'
import sys, pathlib, tempfile; sys.path.insert(0,'.')
import data.trajectory_record as tr
d = pathlib.Path(tempfile.mkdtemp())
w = tr.open_record(d, "t_1", 1)
w.row("meta", stage="sample", env="appworld", task_id="t_1", seed=1, env_seed=100,
      split="train", arm="sample", instructions="v1", task_text="t",
      agent_model="a", generation="{}", inject=None, commit="c", run_key="k",
      owner_session="s")
w.row("gen", step=0, reasoning="r", content="c", n_inject=0)
del w                                                    # no close(): the flush rule must have landed
p = tr.record_path(d, "t_1", 1)
assert not tr.is_done(p)
assert tr.read(p).height == 2
print("flush-per-row ok")
PY
```
Expected: `flush-per-row ok`; exit 0.

**E1 — the example and prediction writers and readers.** Run under all three.
```bash
"$AW" - <<'PY'
import sys, pathlib, tempfile; sys.path.insert(0,'.')
import polars as pl, data.training_data as ex, data.probe_output as pr
d = pathlib.Path(tempfile.mkdtemp())
rows = pl.DataFrame({
  "example_id": ["t_1__s1|s0|c0", "t_1__s1|s0|c1"],
  "event_id":   ["t_1__s1|s0"]*2,
  "record_id":  ["t_1__s1"]*2,
  "task_id":    ["t_1"]*2, "seed": [1, 1], "step": [0, 0],
  "cut": [21, 79], "cut_index": [0, 1], "n_cuts": [2, 2],
  "depth": [0.2658, 1.0],
  "text": ["Task: t\n[HISTORY]\n(start)\n[THINKING]\nI think.", "Task: t\n[HISTORY]\n(start)\n[THINKING]\nI think. Done."],
  "tool": ["apis.spotify.show_playlists"]*2,
  "call": ["apis.spotify.show_playlists(access_token=tok)"]*2,
  "args": [[{"key": "access_token", "value": "tok"}]]*2,
  "weight": [1.0, 1.0], "split": ["train", "train"],
  "env": ["appworld"]*2, "agent_model": ["gptoss120b"]*2,
}, strict=False)
p = d/"examples.parquet"
ex.write(p, rows)
back = ex.read(p)
assert list(back.columns) == list(ex.SCHEMA), back.columns
assert back["version"].to_list() == [ex.VERSION]*2
assert back["args"][0].to_list() == [{"key":"access_token","value":"tok"}]
assert back["depth"].dtype == pl.Float32

q = d/"predictions.parquet"
pr.write(q, pl.DataFrame({
  "example_id": back["example_id"], "event_id": back["event_id"],
  "task_id": back["task_id"], "depth": back["depth"], "split": back["split"],
  "tool": back["tool"], "method": ["ctool"]*2,
  "target": back["tool"], "score": [0.9, 0.7],
  "label_pred": ["apis.spotify.show_playlists"]*2,
  "logits": [[0.1, 0.9], [0.3, 0.7]],
}, strict=False))
pb = pr.read(q)
assert list(pb.columns) == list(pr.SCHEMA), pb.columns
assert pb["text_pred"].to_list() == [None, None]
assert pb["version"].to_list() == [pr.VERSION]*2
print("example+prediction ok")
PY
```
Expected: `example+prediction ok`; exit 0.

**E2 — a generator's prediction row reads back with the classifier columns null.**
```bash
"$AW" - <<'PY'
import sys, pathlib, tempfile; sys.path.insert(0,'.')
import polars as pl, data.probe_output as pr
d = pathlib.Path(tempfile.mkdtemp()); q = d/"p.parquet"
pr.write(q, pl.DataFrame({
  "example_id": ["a"], "event_id": ["e"], "task_id": ["t"], "depth": [0.5],
  "split": ["val"], "tool": ["tl"], "method": ["cgen"], "target": ["tl(x=1)"],
  "text_pred": ["tl(x=1)"], "gen_tokens": [7]}, strict=False))
b = pr.read(q)
assert b["score"].to_list() == [None] and b["logits"].to_list() == [None]
assert b["text_pred"].to_list() == ["tl(x=1)"]
print("generator prediction ok")
PY
```
Expected: `generator prediction ok`; exit 0.

### Selfcheck lines that apply later

`run.py selfcheck` (ticket 15) will check, over these five files: one column-zero
integer `VERSION` in the four that carry one and none in `data/__init__.py` (A3);
a `DEFAULTS` and a `REQUIRED` literal in every format file, with every name in
`REQUIRED` a declared column (A4); each file importing under every interpreter of
the `venvs:` map (A1); every `README.md` annotation line agreeing with the
`ast`-parsed import graph; and no `/home/` or `/net/` path in code.

### GPU / main session — not yours

`M-D2` the claim is exclusive across hosts: on each of shiga/tokyo105, tokyo106
and tokyo107, eight processes released at a common wall-clock barrier race for
150 files under a fresh NFS run directory with `tr.open_record(...)`; the counts
across all 24 processes must sum to exactly 150.

## Comments

- 2026-09-17 wave 1 closeout: implementation passed review after 1 fix round (finding F1, a README import line, addressed), branch `ticket/2026-09-17-wave1/T02` (base `cca3ca3`, head `80b0d01`), merged as `025c54c` (README conflict resolved by keeping every ticket's lines). Main-session checks after the merge: `data`, `data.trajectory_record`, `data.training_data`, `data.probe_output`, `data.probe_input` import under the probe, appworld and vllm interpreters; `M-D2` the cross-host claim race: 8 processes on each of tokyo105, tokyo106, tokyo107 released at a common barrier raced for 150 record files under a fresh NFS directory with `open_record`, claims 64 + 42 + 44 = 150, 150 files on disk. System `python3` (3.10) cannot import `data/__init__.py` because it has no polars; the contracts define `venv: any` over the interpreters in the `venvs:` map, which does not include it. Left for later tickets (reviewer cannotVerify): `to_messages` raises a bare `KeyError` for a step with no gen/env row, which depends on how `agent/loop.py` (ticket 11) calls it; the contracts' 0.2 import lines for `training_data.py` and `probe_output.py` omit the `[polars]` bracket the ticket and the code carry. Implementer concerns: `write()` in `training_data.py` and `probe_output.py` fills absent SCHEMA columns from DEFAULTS; `trajectory_record.SCHEMA` order was reconstructed column-major from the ticket's table; `Writer.row` also calls `os.fsync`. Report `sdd/2026-09-17-wave1/T02-report.md`.
