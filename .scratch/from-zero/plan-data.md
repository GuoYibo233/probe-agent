# Build plan — folder `data/` (the three on-disk formats, the probe's input, the builder)

Planner: data. Written 2026-09-17 against
`notes/plans/2026-09-14-structure-from-zero.md` (Part 1, fixed),
`notes/plans/2026-09-17-contracts.md` (Parts 0.2, 1, 1.1–1.3, 1.5, 1.7, 2.1–2.6,
3.3, 4.1–4.2, 5.2, 8.0, 8.3, 8.4) and the legacy code under `legacy/`.

Files in scope, and only these:
`data/__init__.py`, `data/trajectory_record.py`, `data/training_data.py`,
`data/probe_output.py`, `data/probe_input.py`, `data/build_training_dataset.py`.

`data/environments/__init__.py` and `data/environments/appworld.py` are **not**
in this folder group; they are a cross-folder dependency named in section 5.

---

## 0. Two facts that govern every file here

**The venv.** `venv: any` is the contracts' definition (0.1): the file imports
under every interpreter in the `venvs:` map — measured today as
`external/probe-env/bin/python` (3.11.15), `external/appworld/venv/bin/python`
(3.12.13) and `external/vllm-env/bin/python` (3.12.13), all three carrying
polars 1.44.2 and PyYAML 6.0.3. The dispatch brief's reading ("plus system
python3") cannot hold for the five files that import Polars: system `python3`
is 3.10.12 with no polars and no numpy (measured 2026-09-17). Only
`data/probe_input.py`, whose whole import list is `re`, is additionally checked
under system `python3`. Errata line 13 records this.

**No file here needs NumPy.** The construction plan's `uv pip install numpy`
into `external/appworld/venv` is for `eval/`; nothing in `data/` imports it.

---

## 1. Files

### 1.1 `data/__init__.py`

One sentence: the conventions the three formats share — the id chain, the
shared reader and writer, and the `VERSION` / `DEFAULTS` / `REQUIRED` rule.

- **venv**: any. Imports `polars` and the standard library; no repo import.
- **imports** (0.2): none (repo); `[polars]`.
- **used by** (0.2): `data/trajectory_record.py`, `data/training_data.py`,
  `data/probe_output.py`, `data/build_training_dataset.py` (the id functions, which the
  builder calls rather than formatting a string).
- **reads / writes**: —
- **`VERSION`**: none. This file carries no `VERSION` line: 0.2 gives it none
  and no version list in 2.2 names it.

**Names it must offer** (signatures copied from Part 1, "The id rule" and "The
shared reader and writer have names"):

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
order (errata 3).

`read_frame`, in this order (Part 1's first and third bullets):

1. Raise, naming the path, when the file is missing or empty.
2. Read **the file's own schema** without reading the data:
   `pl.read_parquet_schema(path)` for `.parquet`,
   `dict(pl.scan_ndjson(path, infer_schema_length=None).collect_schema())` for
   `.jsonl`. Both were run in `external/appworld/venv` on 2026-09-17 and return
   a `{name: dtype}` mapping.
3. Treat a file column whose dtype is Polars `Null` as **absent** (errata 12):
   a jsonl column every line writes as JSON `null` infers as `Null`, and that is
   an absent column, not a wrong type.
4. Let `present` be `{name: schema[name]}` for every declared name the file holds
   after step 3 — the **declared** dtype, never the file's inferred one
   (errata 17). A column the file holds and the format does not declare is
   dropped here.
5. Raise, naming the column, the path and the file's recorded version, for every
   name in `required` that is absent from `present`.
6. Read the file's recorded version: the maximum non-null value of the declared
   `version` column (the `meta` row's for a record, every row's for a parquet);
   0 when the column is absent (errata 2). Raise when it is above `version`.
7. Read the data: `pl.read_ndjson(path, schema=present)` for jsonl, and
   `pl.read_parquet(path, columns=list(present)).cast(present, strict=True)` for
   parquet. **That read is the wrong-type check** (Part 1's "a column that is
   present but of the wrong type still fails loudly"): both forms raise on a
   value the declared dtype cannot hold — measured 2026-09-17, a jsonl `"abc"`
   under a declared `Int32` gives
   `ComputeError: cannot parse 'abc' (string) as Int32`, and the parquet cast
   gives `InvalidOperationError`. `read_frame` catches both and re-raises naming
   the path. Widening is silent and intended: a JSON integer infers as `Int64`
   and reads back as the declared `Int32`, a JSON list as the declared
   `List(Int32)`, and a struct missing a field as that field null.
8. Add every declared column still absent as
   `pl.lit(defaults[name], dtype=schema[name]).alias(name)` and `select` the
   declared order.

`write_frame` accepts `.parquet` only and raises, naming the suffix, on anything
else (errata 1): a task record is written row by row and flushed by
`Writer.row`, per Part 1's flush rule, so no jsonl bulk writer has a caller. It
writes to `<path>.tmp-<pid>` in the same directory and `os.replace`s it onto
`path`.

**Legacy source**: none. Today's pipeline has no shared reader; every script
hand-parses jsonl (`legacy/pipeline/annotate/build.py:67`,
`legacy/pipeline/annotate/check_callstr.py:254`). **Not ported**: nothing — this
file is new.

---

### 1.2 `data/trajectory_record.py`

One sentence: the record one task run leaves — six row kinds, one file per
(task, seed), the exclusive-create claim, the readers the login machine uses,
and the conversation rebuild.

- **venv**: any.
- **imports** (0.2): `data/__init__.py` only. It imports **no** registry and
  **no** environment: `release` takes the live-session set and the age margin as
  arguments, and `to_messages` takes the two environment texts as arguments
  (1.1).
- **used by** (0.2): `agent/loop.py` (`meta`, `gen`, `env`, `final`),
  `agent/inject.py` (`spec`, `resume`), `data/build_training_dataset.py`,
  `eval/score_run.py`, `jobs/launch.py` (`done_pairs`, `is_done`, `owner`,
  `release`), `run.py` (the same four).
- **reads / writes**: task record (jsonl).
- **`VERSION = 1`** at column zero, exactly once (3.3's line shape).

**Layout** (1.1): `<run_dir>/records/<task_id>__s<seed>.jsonl`. Every offered
function takes the **run directory** as `dir` and appends `records/` itself, so
no caller spells that subdirectory (errata 4).

**Module-level names**

```python
VERSION = 1
SCHEMA: dict[str, polars.DataType]   # every column of all six row kinds, below
DEFAULTS: dict[str, Any]             # every declared column -> None, except n_inject -> 0
REQUIRED: frozenset[str]             # below
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

`REQUIRED = frozenset({"type", "step", "ts", "version", "record_id", "stage",
"env", "task_id", "seed", "split", "task_text", "agent_model", "owner_session",
"reasoning", "content", "result", "steps", "completed", "judge", "success",
"tokens_in", "tokens_out", "wall_s"})` — the columns a downstream stage reads
that a finished record always carries with a non-null value somewhere. `action`
and `abort` are deliberately **out**: both are legitimately null on every row of
some finished records (a record with no no-code step, a record that never
aborted), and under errata 12 an all-null column reads as absent, so requiring
them would refuse a valid file. 2.5 handles both null cases explicitly. Every
spec/resume column is out for the same reason: a `sample` record has no such row.

**Offered functions** (1.1, "Offered functions"):

```python
def open_record(dir: Path, task_id: str, seed: int) -> Writer | None
def record_path(dir: Path, task_id: str, seed: int) -> Path        # errata 5
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

Behaviour that the sections pin, plus the details settled here:

- `open_record` performs `os.open(path, O_CREAT | O_EXCL | O_WRONLY, 0o644)` of
  an **empty** file and returns the `Writer`; on `FileExistsError` it returns
  `None` (1.1, "Claiming"). It writes no `meta` row: the caller's first
  `row("meta", ...)` call is that row, because `meta.task_text` only exists
  after `Environment.open`.
- `Writer.row(kind, **fields)` writes one JSON object and flushes
  (`legacy/pipeline/inject/live_appworld.py:291-299`). It stamps `type=kind` and
  `ts=time.time()` on every row and, on a `meta` row, `version=VERSION` and
  `record_id=record_id(task_id, seed)`; every other column is the caller's
  (errata 6). It raises on a field name that `SCHEMA` does not declare.
- `Writer.frame()` returns the rows written so far, held in memory, in the same
  column order and dtypes `read` returns (1.1, "Where each caller's `df` comes
  from").
- `is_done(path)`: the last line parses and its `type` is `final`, whatever
  `abort` says (1.1, "Done, partial, refire"). It reads the tail, not the file.
- `owner(path)`: the first line parses as a `meta` row -> its `owner_session`;
  otherwise `None`.
- `done_pairs(dir, pairs)` builds each candidate path with `record_path` and
  returns the subset of `pairs` whose file `is_done`, reading one line per file.
- `release(dir, live_sessions, unowned_age_s)` deletes, and returns, (a) every
  unfinished record file whose `owner(path)` is not in `live_sessions`, and (b)
  every record file whose first line does not parse as a `meta` row and whose
  mtime is older than `unowned_age_s` seconds. Both callers pass
  `registry.live_sessions()` and `registry.DEFAULTS["launch_timeout_s"]` in.
- `read(path)` = `read_frame(path, schema=SCHEMA, defaults=DEFAULTS,
  required=REQUIRED, version=VERSION)`, then fills `record_id` on **every** row
  from that file's `meta` row (errata 7).
- `read_dir(dir, pairs)` reads exactly the files of `pairs`, skips every file
  whose `is_done` is false, and concatenates. Because `read` broadcasts
  `record_id`, the concatenated frame is groupable by record; every other
  meta-only column is reached by joining the meta rows on `record_id`.
- `to_messages(df, upto_step, task_text, instructions, no_code,
  extra_developer)` returns
  `[{"role": "developer", "content": instructions + ("\n\n" + extra_developer if
  extra_developer is not None else "")}, {"role": "user", "content": task_text}]`
  and then, for each step `s < upto_step` in increasing order,
  `{"role": "assistant", "content": <that step's gen.content>}` followed by
  `{"role": "user", "content": <that step's env.result> if <env.action> is not
  null else no_code}` (errata 8). An earlier step's `reasoning` is **never**
  resent, which is today's behaviour
  (`legacy/envs/collect/run_appworld.py:191-215` appends only `g["content"]`).

**Legacy sources and what is ported**

| what | where | ported as |
|---|---|---|
| one jsonl per trajectory, flushed per row | `legacy/pipeline/inject/live_appworld.py:290-299` (`class W`) | `Writer` |
| the six row kinds and their fields | `legacy/pipeline/inject/live_appworld.py:34-42` (the docstring list) and the write sites `:295, 405, 515, 798, 806, 812, 834` | `SCHEMA` |
| the sample side's four kinds | `legacy/envs/collect/run_appworld.py:189-234` | the same `SCHEMA` |
| the conversation shape | `legacy/envs/collect/run_appworld.py:191-215` | `to_messages` |
| the claim | `legacy/pipeline/inject/live_appworld.py:590-603` (`claim`, `mkdir` tickets) | `open_record`'s `O_EXCL` create (1.1 grounds the swap on the NFSv4 measurement) |
| done / resume | `legacy/envs/collect/run_appworld.py:180` (`is_done`) | `is_done`, `done_pairs` |

**Not ported (dropped functionality, stated)**

- The `.claims/` directory and the launch script's "wipe `.claims/` before every
  start" (`live_appworld.py:590-603`): the record file **is** the ticket, so
  there is no second thing to clean up, and the cleanup becomes `release`, which
  runs only on the login machine and only against a dead tmux session.
- `traj_meta`'s free-form dict (`run_appworld.py:189`): every `meta` field is now
  a declared column, and `generation` / `inject` / `judge` are canonical JSON
  **text** columns (1.1) rather than nested structs.
- `final.eval` as a `str(...)` on the sample side (`run_appworld.py:231`) and as
  a dict on the inject side (`live_appworld.py:834`): one shape now — `judge` as
  canonical JSON text plus a declared boolean `success` (1.1).
- The per-run resume-by-skip in `run_appworld.py:180-184` (skip a done file,
  otherwise **overwrite** it): a not-done file is now deleted and the task redone,
  and only on the login machine.

---

### 1.3 `data/training_data.py`

One sentence: the row `build` writes per cut — where it came from, the text the
probe sees, and all three methods' targets.

- **venv**: any. **imports**: `data/__init__.py`; `[polars]`.
- **used by** (0.2): `data/build_training_dataset.py` (write),
  `train/utils/trainer.py` (read), `train/methods/{ctool,cgen,cparam}.py` (their
  target column).
- **reads / writes**: example (parquet), `<run_dir>/examples.parquet`.
- **`VERSION = 1`** at column zero, exactly once.

**Module-level names**: `VERSION`, `SCHEMA`, `DEFAULTS`, `REQUIRED`.

`SCHEMA`, in 1.2's table order:

```
example_id Utf8 | event_id Utf8 | record_id Utf8 | task_id Utf8 | seed Int64
step Int32 | cut Int32 | cut_index Int32 | n_cuts Int32 | depth Float32
text Utf8 | tool Utf8 | call Utf8
args List(Struct({"key": Utf8, "value": Utf8}))
weight Float32 | split Utf8 | env Utf8 | agent_model Utf8 | version Int32
```

`DEFAULTS` = every declared column -> `None`.
`REQUIRED = frozenset({"example_id", "event_id", "record_id", "task_id", "seed",
"step", "cut", "cut_index", "n_cuts", "depth", "text", "tool", "call", "weight",
"split", "version"})` — `args` is out because 1.2 gives it one reader, the build
gate, inside the stage that writes it; `env` and `agent_model` are out because
1.2's "who reads" names only the trainer, which reads neither.

**Offered functions** (errata 9; 1.2 and 0.2 say only "write, read"):

```python
def write(path: Path, df: DataFrame) -> None   # stamps version, selects SCHEMA order, calls write_frame
def read(path: Path) -> DataFrame              # read_frame with this file's four literals
```

**Legacy source**: the sample dict of
`legacy/pipeline/annotate/build.py:216-227` (`make_samples`), whose keys map
one for one: `text`->`text`, `label`->`tool`, `w`->`weight`,
`depth`->`depth`, `sent_idx`->`cut_index`, `n_sents`->`n_cuts`,
`event`->`event_id`, `traj`->`record_id`, `unit`->`task_id`, `step`->`step`,
`label_call`->`call`, `args_named`->`args`.

**Not ported**: the `model` column (`build.py:224`) — one run is one agent model
by key (2.2), so the alias is `agent_model` and gate A of
`legacy/pipeline/annotate/check_callstr.py:257-265` has nothing left to catch;
the three separate `train.jsonl` / `val.jsonl` / `test.jsonl` files
(`build.py:390-393`) — one parquet with a `split` column (1.2), so a changed
split rule rewrites one file; and `tool_vocab.json` (`build.py:404-406`) — the
class order is `head_labels`' and lives in `best/meta.json` (1.3).

---

### 1.4 `data/probe_output.py`

One sentence: the row `train` writes per example after training, and the only
file `eval/` reads.

- **venv**: any. **imports**: `data/__init__.py`; `[polars]`.
- **used by** (0.2): `train/utils/trainer.py` (write),
  `eval/utils/probe_eval.py` (read).
- **reads / writes**: prediction (parquet), `<train run_dir>/predictions.parquet`.
- **`VERSION = 1`** at column zero, exactly once.

`SCHEMA`, in 1.3's table order:

```
example_id Utf8 | event_id Utf8 | task_id Utf8 | depth Float32 | split Utf8
tool Utf8 | method Utf8 | target Utf8
score Float32 | label_pred Utf8 | logits List(Float32)
text_pred Utf8 | gen_tokens Int32 | version Int32
```

`DEFAULTS` = every declared column -> `None`.
`REQUIRED = frozenset({"example_id", "event_id", "task_id", "depth", "split",
"tool", "method", "target", "version"})` — the nine columns every method writes.
The classifier trio (`score`, `label_pred`, `logits`) and the generator pair
(`text_pred`, `gen_tokens`) are out: each is null for the other `PROBE_KIND`
(1.3), and under errata 12 an all-null column reads as absent.

**Offered functions**: the same two as `data/training_data.py`
(`write(path, df)`, `read(path)`), same errata 9.

**Legacy source**: none as a file. Today the equivalent numbers are produced
inside the eval scripts and never written as a row format (grounding F1, quoted
in 1.3). **Not ported**: nothing — this file is new. In particular the class
order is **not** kept here: it is `head_labels`' output, written into
`best/meta.json` by `models/probe_models/base.py` (1.3), not a column and not a
sidecar file.

---

### 1.5 `data/probe_input.py`

One sentence: the cut positions in the reasoning and the text assembled for the
probe — the one text that `data/build_training_dataset.py` (offline) and
`agent/inject.py` (live) must build identically.

- **venv**: any, and additionally importable under system `python3` (its whole
  import list is `re`).
- **imports** (0.2): none (repo); `[re]`.
- **used by** (0.2): `data/build_training_dataset.py`, `agent/inject.py`.
- **reads / writes**: —
- **`VERSION = 1`** at column zero, exactly once. 1.7: this file's `VERSION` is
  the expensive one — it folds into the `build` and `inject` keys (2.2).

**Offered functions** (1.7, copied verbatim):

```python
def cuts(thinking: str, min_think: int, max_cuts: int) -> list[int]
def cuts_live(thinking_so_far: str, min_think: int) -> list[int]
def assemble(task: str, history: list[tuple[str, str]],
             thinking_prefix: str, hist_rounds: int, probe_result_cap: int) -> str
```

All three are pure: every parameter is passed in, nothing is read from a file,
and no setting value is a module constant. The one module-level literal is the
sentence regex, which is the rule itself, not a parameter:

```python
SENT_RE = re.compile(r"(?<=[.!?])\s+|\n")      # legacy/pipeline/annotate/rules.py:26
```

`cuts` is the offline enumeration, ported from
`legacy/pipeline/annotate/rules.py:29-47` (`boundaries`) with `MAX_BOUNDS` and
`MIN_THINK` turned into parameters:

```python
if max_cuts < 2: raise ValueError(...)                       # errata 10
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
offsets, the same `min_think // 2` per-cut filter, **no** terminal cut and
**no** thinning. Its docstring carries 1.7's three reasons, and both files'
README lines say `example.cut` and `spec.cut` are not the same coordinate.

`assemble` is ported from `legacy/pipeline/annotate/rules.py:50-62`
(`clip` + `assemble`) with `HIST_ROUNDS` and `RESULT_CAP` turned into
parameters:

```python
def _clip(s: str, cap: int) -> str:
    if cap < 100: raise ValueError(...)                       # errata 10
    s = str(s)
    return s if len(s) <= cap else s[: cap - 60] + " ...[cut]... " + s[-40:]

lines = [f"Task: {task}", "[HISTORY]"]
lines += [f"{a} -> {_clip(r, probe_result_cap)}" for a, r in history[-hist_rounds:]] or ["(start)"]
lines += ["[THINKING]", thinking_prefix]
return "\n".join(lines)
```

**Not ported from `legacy/pipeline/annotate/rules.py`**

- Every module constant — `SEED`, `MAX_BOUNDS`, `MIN_THINK`, `HIST_ROUNDS`,
  `RESULT_CAP`, `MODEL_OF` (`rules.py:17-23`): they become setting fields
  (`build.max_cuts`, `build.min_think`, `build.hist_rounds`,
  `build.probe_result_cap`, 5.2) and are passed in. That is the whole point of
  1.7's inheritance rule.
- `split_args`, `first_call_args`, `split_args_named`, `first_call_named`,
  `mkparams`, `AW_CALL`, `BFCL_CALL` (`rules.py:67-178`): call syntax is the
  environment's (4.2), so they move to `data/environments/appworld.py`, a
  different folder.
- The entire ALFWorld block (`rules.py:181-305`: `ALF_TEMPLATES`,
  `ALF_BAD_CHARS`, `ALF_VALUE_RE`, `_alf_compile`, `ALF_RULES`, `ALF_TOOLS`,
  `ALF_CALL`, `alf_split`): `alfworld` is not a value on the `data.env` axis in
  the new tree (5.3 lists `appworld` only), and a new environment adds a file
  under `data/environments/`, never a branch here.

---

### 1.6 `data/build_training_dataset.py`

One sentence: the program that turns a `sample` run's task records into example
rows for the three probe methods, assigns the train/val/test split, holds the
build gates and writes the report.

- **venv**: any (2.1's `build` row). `run.py` starts it in place with the `any`
  interpreter (2.3).
- **imports** (0.2, corrected by errata 11): `experimental_settings/schema.py`,
  `data/__init__.py` (the id functions), `data/trajectory_record.py`,
  `data/training_data.py`, `data/probe_input.py`, `data/environments/__init__.py`,
  `jobs/registry.py`; `[polars, PyYAML]`.
- **used by**: none (program).
- **reads** (errata 11): the sample run's task records,
  `constants/path_datasets.yaml` (the `splits:` block of `cfg.data.env`, for the
  split files' paths), the environment's split task-id files.
- **writes**: `examples.parquet`, `consumed.json`, `report.md`, the heartbeat,
  `done.json`.
- **`VERSION = 1`** at column zero, exactly once (2.2 folds it into the build
  key).

**Entry point** (2.6): `def main(run_dir: Path) -> None`, plus an
`if __name__ == "__main__":` block whose only flag is `--run-dir`. **No setting
name anywhere on the command line.** It calls `schema.load_frozen(run_dir)`
itself.

**The walk, in order**

1. `cfg = schema.load_frozen(run_dir)`; `hb = registry.beat(run_dir, 0)`.
2. `env = open_env(cfg.data.env)`.
3. `triples = requested_pairs(env, cfg.sample.split, cfg.sample.tasks,
   cfg.sample.n_tasks, cfg.sample.seeds)`;
   `pairs = [(t, s) for _split, t, s in triples]` (2.3's projection).
4. `sample_dir = schema.run_dir_of("sample", cfg._upstream["sample"],
   debug=cfg._debug)` — the key is read out of `_upstream`, never recomputed
   (2.1).
5. **Completeness gate** (2.5): `done = trajectory_record.done_pairs(sample_dir,
   pairs)`; raise, naming the missing pairs, when `done` does not cover `pairs`.
6. `hb.emit(0, len(pairs), "row")`, then one beat per record read (errata 14).
7. Resolve the split files: read `constants/path_datasets.yaml`, take the
   `splits:` block of `cfg.data.env` for each split's **path**; take each
   split's ids from `env.tasks(split)`. Hash each file with sha1.
8. **Split gates** (2.5): a task id that appears in two splits, and a task id of
   the records that is in none of the environment's official lists, each stop the
   build and name the ids.
9. `df = trajectory_record.read_dir(sample_dir, pairs)`.
10. **Abort gate** (2.5): the share of records whose `final.abort` is non-null
    above `cfg.build.max_abort_frac` stops the build.
11. Per record, join the `gen` and `env` rows on `step`. **A `gen` row with no
    `env` row raises, naming the record and the step** (1.1's gen-and-env
    pairing) — it does not break out of the trajectory.
12. Per event, in step order, with `history` accumulated across the trajectory:
    - `thinking = (gen.reasoning or "").strip()`,
      `action = (env.action or "").strip()`.
    - `action` empty -> **skip the event, count it, and append nothing to
      `history`** (`legacy/pipeline/annotate/build.py:81-83`; 2.5's null-action
      rule).
    - `env.split_args(action)` returns `None` on a non-empty action -> **stop the
      build**, naming the record and the step (2.5).
    - `len(thinking) < cfg.build.min_think` or `thinking == ""` -> skip the
      event, count it, **but append `(action, env.result)` to `history`**
      (`build.py:86,117`: the `hist.append` sits after the yield and outside the
      `if`, so an unparsed or too-short step still enters the history).
    - otherwise: `tool, args, _span = env.split_args(action)`;
      `call = env.build_call(tool, args)`;
      `offsets = probe_input.cuts(thinking, cfg.build.min_think,
      cfg.build.max_cuts)`; one row per offset with
      `text = probe_input.assemble(task_text, history, thinking[:cut],
      cfg.build.hist_rounds, cfg.build.probe_result_cap)`,
      `depth = round(cut / len(thinking), 4)`,
      `weight = 1.0` under `uniform` and `round(1.0 / n_cuts, 6)` under
      `per_event` (`build.py:213`), and the ids from `data/__init__.py`.
    - then append `(action, env.result)` to `history`.
13. **The `split` column.** Under `split_source: env`: the record's `meta.split`
    through `env.SPLIT_ROLE` (2.5, 4.1). Under `hash`:
    `int(sha1(task_id.encode()).hexdigest()[:8], 16) / 2**32` against the
    cumulative `cfg.build.split_ratio` (5.2) — never Python's `hash()`.
14. **Row gates** (2.5), each stopping the build and naming the rows:
    the call round trip (`env.split_args(call)` must give back this row's `tool`
    and `args`); an empty `text`; a `depth` outside [0, 1]; and the thinking-prefix
    check, spelled `row.text.endswith(thinking[:cut])` (errata 15).
15. **Per-split cap**: keep the first `cfg.build.max_examples` rows of **each**
    split in `example_id` order (2.5).
16. `training_data.write(run_dir / "examples.parquet", frame)`.
17. `consumed.json`: every record file it read, by `trajectory_record.record_path`,
    with its sha1 and row count; **and** every split file, with its path, sha1
    and task count (2.5, 1.5).
18. `report.md` (section 1.6's list below).
19. `registry.write_done(run_dir, stage="build", key=cfg._key,
    commit=cfg._commit, counts=<below>, versions=cfg._versions, metrics={},
    report="report.md")`, then `hb.finish()`.

`counts` (errata 16): `{records, events, events_skipped_no_action,
events_skipped_short_think, examples, examples_train, examples_val,
examples_test, tools, tools_unseen_in_train}`. `metrics` is `{}`: 1.5 names the
metric owners as train, eval and score, and a build's numbers are counts.

`report.md` carries, ported in content from
`legacy/pipeline/annotate/build.py:462-489`: the identity line (key, env,
agent model, commit, debug); records / events / events skipped / examples; cuts
per event (min, median, max, and the cap); per split, tasks · events · examples;
the tool vocabulary (class count, top 5, classes appearing fewer than 5 times);
**the tools that appear in val or test and never in train, listed** (2.5 demotes
that gate to a report line); examples per depth decile; `text` length p50 / p90 /
max; the abort share against `max_abort_frac`; and how many rows the per-split
`max_examples` cap dropped.

**Legacy sources**

| what | where |
|---|---|
| trajectory -> event | `legacy/pipeline/annotate/build.py:61-118` (`jsonl_events`, the `appworld` branch only) |
| event -> sample rows | `legacy/pipeline/annotate/build.py:205-228` (`make_samples`) |
| the official-task-list split | `legacy/pipeline/annotate/build.py:303-318` (`read_unit_list`, `official_split`) and the missing-unit refusal `:367-372` |
| the report | `legacy/pipeline/annotate/build.py:442-534` |
| the call round trip, today a measurement | `legacy/pipeline/annotate/check_callstr.py:20-27, 48-51, 307-320` |
| the structural gates | `legacy/pipeline/annotate/check_callstr.py:257-305` (gates A, B, D) |

**Not ported (dropped functionality, stated)**

- `bfcl_events` (`build.py:120-169`) and the `tales` / `alfworld` branches of
  `jsonl_events` (`build.py:93-116`): one environment on the axis, and a new
  environment adds a file under `data/environments/`, not a branch here.
- `collect_events`' multi-runs-directory concatenation (`build.py:172-187`) and
  `MODEL_OF` filtering (`build.py:64, 360`): one build reads one `sample` run
  directory, and the agent model is fixed by the key (2.2).
- `traj_files` and `scan_raw_trajs` (`build.py:248-298`): the duplicate-trajectory
  and step-cap scan re-read the raw files a second time. `final.steps` and the
  record frame answer both from the frame already in hand, and the report keeps
  only the lines section 1.6 lists.
- `router_stats.md` (`build.py:408-433`), `qa_sample.txt` (`build.py:436-440`)
  and `tool_vocab.json` (`build.py:404-406`): `report.md` is the one report file
  (1.5's `report` field), and the class order is `head_labels`' (1.3).
- The `random.Random(seed)` sampling behind self-checks 1 and 3
  (`build.py:337, 376-402`): both become whole-frame gates (step 14 above and the
  split gates of step 8), so the builder draws no random number at all and needs
  no seed.
- `make_call` (`build.py:197-200`) and `norm_named` (`build.py:192-194`):
  replaced by `env.build_call`, which 4.2 makes the **inverse** of
  `env.split_args`; `make_call`'s unquoted join is exactly what
  `check_callstr.py:20-27` measures as a loss.
- Gate A (`check_callstr.py:257-265`, cross-model contamination), gate C
  (`:110-120`, the `traj_runs` shape) and gate E (`:290-305`, the report wording
  against `SPLIT_REPORT.json`): the first has no failure mode left (one run, one
  model, by key), the second has no `traj_runs`, and the third has no
  `SPLIT_REPORT.json` — the split source is `build.split_source`, a keyed field.
- Deviations 2, 3 and 4 (`check_callstr.py:52-65`) as separate sections: they
  become `report.md` lines and `counts` entries.
- `legacy/pipeline/train/share_data.py:583-611` (`read_position`, the
  character-cut-to-token-index rule): **not ported anywhere in `data/`.** In the
  new tree one example row is one sequence whose `text` ends at the cut, and the
  decision is taken at that sequence's last non-pad token — `Batch["event_end"]`
  on the packed path and `Probe.score`'s "that text's last token" on the served
  path (6.2). A train method that reintroduces per-event packing writes its own
  `event_end`, which 2.6 makes that method file's business.

---

## 2. Order of construction inside the folder

```
data/__init__.py          (no repo import)
  ├── data/probe_input.py (no repo import; can be written in parallel)
  ├── data/trajectory_record.py       needs data/__init__.py
  ├── data/training_data.py           needs data/__init__.py
  └── data/probe_output.py        needs data/__init__.py
          └── data/build_training_dataset.py   needs all five, plus three other folders
```

`data/build_training_dataset.py` is last and needs these names to **exist** first:

| file (other folder) | names it must offer |
|---|---|
| `experimental_settings/schema.py` | `load_frozen(run_dir) -> Setting`; `run_dir_of(stage, key, *, debug)`; on the `Setting`: `data.env`, `build.{max_cuts, min_think, hist_rounds, probe_result_cap, weight_mode, split_source, split_ratio, max_examples, max_abort_frac}`, `sample.{split, tasks, n_tasks, seeds}`, `_key`, `_commit`, `_versions`, `_upstream`, `_debug` |
| `data/environments/__init__.py` | `open_env(name)`; `requested_pairs(env, splits, tasks, n_tasks, seeds)`; on the instance: `tasks(split)`, `split_args(text)`, `build_call(tool, args)`, `SPLIT_ROLE` |
| `data/environments/appworld.py` | the concrete environment `open_env("appworld")` returns |
| `jobs/registry.py` | `beat(run_dir, piece) -> Heartbeat`, `Heartbeat.emit`, `Heartbeat.finish`, `write_done(run_dir, *, stage, key, commit, counts, versions, metrics, report, pairs=None, stage_extra=None)` |
| `constants/path_datasets.yaml` | the `splits:` block of `appworld` (each split's task-id file path) |

Nothing else in this folder needs anything from another folder.

---

## 3. Acceptance, CPU

Every command is run from the repo root. `$P` stands for each of the three
interpreters in turn:
`external/probe-env/bin/python`, `external/appworld/venv/bin/python`,
`external/vllm-env/bin/python`.

### A. Import and annotation checks (ticket 01 writes them, every ticket reruns them)

**A1 — every file in this folder imports under all three venvs.**
```sh
for P in external/probe-env/bin/python external/appworld/venv/bin/python external/vllm-env/bin/python; do
  "$P" -c "import sys; sys.path.insert(0,'.');
import data, data.trajectory_record, data.training_data, data.probe_output, data.probe_input, data.build_training_dataset
print('imports ok', sys.version.split()[0])"
done
```
Expected: three lines, `imports ok 3.11.15`, `imports ok 3.12.13`,
`imports ok 3.12.13`; exit 0 each. (Drop the modules a ticket has not written
yet; the last ticket runs the full line.)

**A2 — `data/probe_input.py` also imports under system `python3`** (3.10, no
polars), which is what "the offline and the live caller cannot drift" costs
nothing to keep.
```sh
python3 -c "
import importlib.util as u
s = u.spec_from_file_location('pi', 'data/probe_input.py')
m = u.module_from_spec(s); s.loader.exec_module(m)
print('probe_input imports on', __import__('sys').version.split()[0])"
```
Expected: `probe_input imports on 3.10.12`; exit 0.

**A3 — the `VERSION` line shape (3.3), the selfcheck rule this folder must
satisfy.** `run.py selfcheck` does not exist yet; this is its grep stand-in.
```sh
for f in data/trajectory_record.py data/training_data.py data/probe_output.py data/probe_input.py data/build_training_dataset.py; do
  n=$(grep -c '^VERSION = [0-9][0-9]*$' "$f"); echo "$f $n"
done
grep -c '^VERSION' data/__init__.py
```
Expected: five lines each ending in ` 1`, then `0` for `data/__init__.py`
(that file carries no `VERSION`).

**A4 — `REQUIRED` names only declared columns** (the selfcheck rule of Part 1).
```sh
external/probe-env/bin/python -c "
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

### B. `data/__init__.py` (ticket 01)

**B1 — the id chain.**
```sh
external/appworld/venv/bin/python -c "
import sys; sys.path.insert(0,'.')
from data import record_id, event_id, example_id
r = record_id('50e1ac9_1', 42); e = event_id(r, 3); x = example_id(e, 2)
assert r == '50e1ac9_1__s42', r
assert e == '50e1ac9_1__s42|s3', e
assert x == '50e1ac9_1__s42|s3|c2', x
print(r, e, x)"
```
Expected: `50e1ac9_1__s42 50e1ac9_1__s42|s3 50e1ac9_1__s42|s3|c2`; exit 0.

**B2 — `write_frame` / `read_frame` round trip, DEFAULTS filling, and the three
raises.** (Run under each `$P`.)
```sh
external/appworld/venv/bin/python - <<'PY'
import sys, tempfile, pathlib; sys.path.insert(0,'.')
import polars as pl
from data import read_frame, write_frame
S = {"a": pl.Utf8, "b": pl.Int32, "c": pl.Float32, "version": pl.Int32}
D = {"a": None, "b": None, "c": None, "version": None}
R = frozenset({"a", "version"})
d = pathlib.Path(tempfile.mkdtemp())

# round trip, and a declared column the file does not hold is filled from DEFAULTS
p = d/"x.parquet"
write_frame(p, pl.DataFrame({"a": ["z"], "b": [1], "version": [1]}), schema=S)
f = read_frame(p, schema=S, defaults=D, required=R, version=1)
assert list(f.columns) == ["a","b","c","version"], f.columns
assert f["c"].to_list() == [None] and f["c"].dtype == pl.Float32
print("roundtrip+defaults ok")

# a required column absent from the file raises and names it
q = d/"y.parquet"
write_frame(q, pl.DataFrame({"b": [1], "version": [1]}), schema={"b": pl.Int32, "version": pl.Int32})
try:
    read_frame(q, schema=S, defaults=D, required=R, version=1); raise SystemExit("no raise")
except Exception as e:
    assert "a" in str(e) and str(q) in str(e), e
    print("required raise ok")

# a file version above the reader's raises
w = d/"z.parquet"
write_frame(w, pl.DataFrame({"a":["z"],"version":[9]}), schema={"a": pl.Utf8, "version": pl.Int32})
try:
    read_frame(w, schema=S, defaults=D, required=R, version=1); raise SystemExit("no raise")
except Exception as e:
    assert "9" in str(e), e
    print("version raise ok")

# a jsonl column that is null on every line counts as absent, not as a wrong type;
# a JSON integer widens silently into the declared Int32
j = d/"r.jsonl"; j.write_text('{"a":"z","version":1,"b":7,"c":null}\n')
f = read_frame(j, schema=S, defaults=D, required=R, version=1)
assert f["c"].to_list() == [None] and f["c"].dtype == pl.Float32
assert f["b"].to_list() == [7] and f["b"].dtype == pl.Int32
print("null-column-as-absent ok")

# a value the declared dtype cannot hold raises and names the path
k = d/"bad_type.jsonl"; k.write_text('{"a":"z","version":1,"b":"abc"}\n')
try:
    read_frame(k, schema=S, defaults=D, required=R, version=1); raise SystemExit("no raise")
except Exception as e:
    assert str(k) in str(e), e
    print("wrong-type raise ok")

# write_frame refuses a non-parquet suffix
try:
    write_frame(d/"bad.jsonl", pl.DataFrame({"a":["z"]}), schema={"a": pl.Utf8}); raise SystemExit("no raise")
except Exception as e:
    assert "jsonl" in str(e), e
    print("write_frame suffix raise ok")
PY
```
Expected, in order: `roundtrip+defaults ok`, `required raise ok`,
`version raise ok`, `null-column-as-absent ok`, `write_frame suffix raise ok`;
exit 0.

### C. `data/probe_input.py` (ticket 01)

**C1 — the two cut rules, against values computed from the legacy code on
2026-09-17.**
```sh
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
Expected: `cuts ok`; exit 0. The pair
`cuts(T,40,64) == [21,45,60,79]` against `cuts_live(T,40) == [20,44,59]` is the
executable form of 1.7's "not the same coordinate".

**C2 — `assemble`, byte for byte against the legacy format.**
```sh
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
Expected: `assemble ok`; exit 0. (393 = `400 - 60 + 13 + 40`, the legacy `clip`
shape of `rules.py:50-52`.)

### D. `data/trajectory_record.py` (ticket 02)

**D1 — the claim, the six kinds, the round trip, `is_done` / `owner` /
`done_pairs` / `read_dir` / `to_messages` / `release`, on a fixture built by the
real entry points.**
```sh
external/appworld/venv/bin/python - <<'PY'
import sys, json, os, time, tempfile, pathlib; sys.path.insert(0,'.')
import data.trajectory_record as tr
d = pathlib.Path(tempfile.mkdtemp())

w = tr.open_record(d, "50e1ac9_1", 42)
assert w is not None
assert tr.open_record(d, "50e1ac9_1", 42) is None          # the O_EXCL claim
p = tr.record_path(d, "50e1ac9_1", 42)
assert p == d/"records"/"50e1ac9_1__s42.jsonl", p
assert not tr.is_done(p)
w.row("meta", stage="sample", env="appworld", task_id="50e1ac9_1", seed=42,
      env_seed=100, split="train", arm="sample", instructions="v1",
      task_text="Play my playlist.", agent_model="gpt_oss_120b",
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
      wall_s=2.0, finished_at=time.time())
w.close()

assert tr.is_done(p)
assert tr.owner(p) == "sample-abc123def456-0"
df = tr.read(p)
assert df.height == 6, df.height
assert set(df["type"].to_list()) == {"meta","gen","env","final"}
assert df["record_id"].to_list() == ["50e1ac9_1__s42"]*6       # broadcast, errata 7
assert df["version"].max() == tr.VERSION
assert set(fr.columns) == set(df.columns)                      # Writer.frame matches read

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

# release: a finished file is never touched; a dead session's unfinished file is
w2 = tr.open_record(d, "abc0000_2", 7)
w2.row("meta", stage="sample", env="appworld", task_id="abc0000_2", seed=7,
       env_seed=100, split="train", arm="sample", instructions="v1",
       task_text="t", agent_model="gpt_oss_120b", generation="{}", inject=None,
       commit="deadbee", run_key="abc123def456", owner_session="gone-0")
w2.close()
fd = os.open(d/"records"/"zzz9999_3__s1.jsonl", os.O_CREAT|os.O_EXCL|os.O_WRONLY); os.close(fd)
os.utime(d/"records"/"zzz9999_3__s1.jsonl", (0, 0))            # older than the margin
gone = sorted(x.name for x in tr.release(d, {"sample-abc123def456-0"}, 1800))
assert gone == ["abc0000_2__s7.jsonl", "zzz9999_3__s1.jsonl"], gone
assert p.exists()
print("trajectory_record ok")
PY
```
Expected: `trajectory_record ok`; exit 0. Run under all three `$P`.

**D2 — a killed writer's file is readable to its last flushed row.**
```sh
external/appworld/venv/bin/python - <<'PY'
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

### E. `data/training_data.py` and `data/probe_output.py` (ticket 03)

**E1 — write with the format's writer, read it back, and get the declared
columns.**
```sh
external/appworld/venv/bin/python - <<'PY'
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
  "env": ["appworld"]*2, "agent_model": ["gpt_oss_120b"]*2,
}, strict=False)
p = d/"examples.parquet"
ex.write(p, rows)
back = ex.read(p)
assert list(back.columns) == list(ex.SCHEMA), back.columns
assert back["version"].to_list() == [ex.VERSION]*2           # the writer stamps it
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
assert pb["text_pred"].to_list() == [None, None]             # a generator column, filled from DEFAULTS
assert pb["version"].to_list() == [pr.VERSION]*2
print("example+prediction ok")
PY
```
Expected: `example+prediction ok`; exit 0. Run under all three `$P`.

**E2 — a prediction file written by a generator reads back with the classifier
columns null, and the other way round** (the executable form of 1.3's
per-`PROBE_KIND` column split).
```sh
external/appworld/venv/bin/python - <<'PY'
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

### F. `data/build_training_dataset.py` (ticket 04)

**F1 — the module is a program with the command shape of 2.6 and no setting name
on its command line.**
```sh
external/appworld/venv/bin/python -m data.build_training_dataset --help 2>&1 | head -5
external/appworld/venv/bin/python -m data.build_training_dataset --run-dir /nonexistent; echo "exit=$?"
```
Expected: the help text names `--run-dir` and **no** `--setting`, `--config`,
`--env` or `--out`; the second command exits non-zero with a message naming
`/nonexistent`.

**F2 — the end-to-end build over a fixture run directory.** The ticket's
implementer builds the fixture with the real writers: a `sample` run directory
with two record files written through `data/trajectory_record.py`, a frozen
`settings.yaml` written through `schema.freeze`, and a `build` run directory.
```sh
external/appworld/venv/bin/python -m data.build_training_dataset --run-dir <fixture build dir>; echo "exit=$?"
ls <fixture build dir>
external/appworld/venv/bin/python -c "
import sys; sys.path.insert(0,'.')
import data.training_data as ex
df = ex.read('<fixture build dir>/examples.parquet')
print(df.height, sorted(set(df['split'].to_list())), list(df.columns))"
```
Expected: `exit=0`; the directory holds `examples.parquet`, `consumed.json`,
`report.md`, `done.json` and `heartbeat/0-0.jsonl`; the read prints the row
count, the split values present, and the full declared column list of
`data/training_data.py`'s `SCHEMA` in order.

**F3 — each gate of 2.5 fires and names what it found.** One command per gate,
each against a fixture that is the F2 fixture with one thing changed; every one
must exit non-zero and print the named thing.

| what is changed in the fixture | expected message contains |
|---|---|
| one requested (task, seed) has no done record | the missing `(task_id, seed)` pairs |
| `build.max_abort_frac: 0.0` and one record has a non-null `abort` | the abort share and `max_abort_frac` |
| a `gen` row whose `step` has no `env` row | the record id and the step index |
| an `env.action` that `split_args` returns None for | the record id and the step index |
| the same task id put in two split files | the task id and both splits |
| a record whose `task_id` is in no split file | the task id |
| a `call` edited so `split_args(call)` no longer gives back `tool` and `args` | the `example_id` and both sides of the round trip |

**F4 — a null `env.action` is skipped, not raised, and is counted.**
```sh
external/appworld/venv/bin/python -c "
import json; c = json.load(open('<fixture build dir>/done.json'))
print(c['counts']['events_skipped_no_action'], c['counts']['events'], c['counts']['examples'])"
```
Expected: a non-zero `events_skipped_no_action` for a fixture whose second step
wrote no code block, and no example row carrying that step's `event_id`.

**F5 — `consumed.json` names both kinds of input.**
```sh
external/appworld/venv/bin/python -c "
import json; e = json.load(open('<fixture build dir>/consumed.json'))
paths = [x['path'] for x in e]
print(sum(1 for p in paths if p.endswith('.jsonl')), sum(1 for p in paths if not p.endswith('.jsonl')))
print(all('sha1' in x for x in e))"
```
Expected: the record-file count, then the split-file count (one per split of the
environment), then `True`.

**F6 — the per-split `max_examples` cap is a deterministic function of its
input** (2.5): run the build twice into two directories with
`build.max_examples: 1` and compare.
```sh
external/appworld/venv/bin/python -c "
import sys; sys.path.insert(0,'.')
import data.training_data as ex
a = ex.read('<dir A>/examples.parquet'); b = ex.read('<dir B>/examples.parquet')
assert a.equals(b)
print('deterministic cap ok', a.height)"
```
Expected: `deterministic cap ok <n>`; exit 0, with at most one row per split.

---

## 4. Acceptance, GPU or cross-host — for the main session

Nothing in `data/` runs on a GPU, and no file here opens an ssh connection. Two
checks still belong to the main session because they need a real GPU-produced
input or a second host:

**G1 — a real `sample` run's records build.** After the first `--debug`
`train_probe.yaml` walk produces a real `sample` run directory on
`/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/debug/sample/<key>/`,
run the build against its own run directory:
```sh
python3 run.py train_probe <setting> --debug        # the walk reaches build itself
external/appworld/venv/bin/python -c "
import sys; sys.path.insert(0,'.')
import data.training_data as ex
df = ex.read('<debug build dir>/examples.parquet')
print(df.height, df['split'].value_counts().sort('split'))"
```
Must show: a non-zero row count in **all three** splits (`train`, `val`, `test`)
— the failure 2.3's per-split `n_tasks` cap and 4.1's `SPLIT_ROLE` map exist to
prevent, and the one thing a fixture cannot prove.

**G2 — the claim is exclusive across hosts.** `open_record`'s `O_EXCL` is the
primitive the whole claiming rule rests on, and the contracts' own measurement
was made outside this code. Repeat it against this implementation:
```sh
# on each of shiga/tokyo105, tokyo106, tokyo107, released at a common wall-clock barrier
for i in $(seq 8); do external/appworld/venv/bin/python -c "
import sys; sys.path.insert(0,'.')
import data.trajectory_record as tr
n = sum(1 for k in range(150) if tr.open_record('<a fresh NFS run dir>', 'race_%d' % k, 0) is not None)
print(n)" & done; wait
```
Must show: the counts across all 24 processes sum to exactly 150.

---

## 5. Tickets

### Ticket 01 — the shared format conventions and the probe's input

- **Files**: `data/__init__.py`, `data/probe_input.py`.
- **What to do**: sections 1.1 and 1.5 above. `data/__init__.py` offers the
  three id functions and `read_frame` / `write_frame` with the eight-step
  reading rule and the parquet-only writing rule; `data/probe_input.py` ports
  `boundaries`, `sent_starts`, `clip` and `assemble` from
  `legacy/pipeline/annotate/rules.py:26-62` and
  `legacy/pipeline/inject/live_appworld.py:165-175`, turning every module
  constant into a parameter. Both carry the docstrings section 1 names,
  `data/probe_input.py` carries `VERSION = 1` and `data/__init__.py` carries
  none.
- **Acceptance**: A1 (these two modules), A2, A3, B1, B2, C1, C2.
- **Needs from other folders**: none.

### Ticket 02 — the task record

- **Files**: `data/trajectory_record.py`.
- **What to do**: section 1.2 above — `VERSION`, `SCHEMA`, `DEFAULTS`,
  `REQUIRED`, and the eleven offered names. The claim is the `O_EXCL` create of
  an empty file and nothing else; the `meta` row is the caller's first
  `row` call; `record_id` is broadcast onto every row by `read` and `read_dir`;
  `to_messages` builds the six-role conversation of errata 8 and never resends an
  earlier step's `reasoning`. This file imports `data/__init__.py` and nothing
  else — in particular no registry and no environment.
- **Acceptance**: A1, A3, A4, D1, D2.
- **Needs from other folders**: none (ticket 01 inside this folder).

### Ticket 03 — the example and prediction formats

- **Files**: `data/training_data.py`, `data/probe_output.py`.
- **What to do**: sections 1.3 and 1.4 above — the two column lists with their
  dtypes, `DEFAULTS` all null, the `REQUIRED` sets as stated, and
  `write(path, df)` / `read(path)` on each. `write` stamps `version` and selects
  the declared column order; neither file computes a target, a class order or a
  metric.
- **Acceptance**: A1, A3, A4, E1, E2.
- **Needs from other folders**: none (ticket 01 inside this folder).

### Ticket 04 — the builder

- **Files**: `data/build_training_dataset.py`.
- **What to do**: section 1.6 above — `main(run_dir)`, the nineteen-step walk,
  every gate of 2.5 with the spellings this plan fixes, the `split` assignment
  by both rules of `build.split_source`, the per-split `max_examples` cap,
  `examples.parquet` through `data/training_data.py`, `consumed.json` with both kinds
  of entry, `report.md` with the lines section 1.6 lists, the heartbeat and
  `done.json` through `jobs/registry.py`. The "not ported" list of section 1.6
  is part of the ticket: none of those legacy outputs is recreated.
- **Acceptance**: A1 (all six modules), A3, F1, F2, F3, F4, F5, F6.
- **Needs from other folders** (the integrator's Blocked-by):
  - `experimental_settings/schema.py`: `load_frozen`, `run_dir_of`, `freeze`
    (for the fixture), and the `Setting` fields listed in section 2.
  - `data/environments/__init__.py`: `open_env`, `requested_pairs`.
  - `data/environments/appworld.py`: `tasks`, `split_args`, `build_call`,
    `SPLIT_ROLE`.
  - `jobs/registry.py`: `beat`, `Heartbeat.emit`, `Heartbeat.finish`,
    `write_done`.
  - `constants/path_datasets.yaml`: the `splits:` block of `appworld`.

---

## 6. Contract errata settled here

Appended verbatim to `.scratch/from-zero/contract-errata.md`.

1. **Part 1 (`write_frame`)** — says `read_frame` picks jsonl or parquet by the
   suffix and leaves `write_frame`'s suffix handling unstated -> `write_frame`
   accepts `.parquet` only and raises on any other suffix; a task record's jsonl
   is written row by row by `Writer.row` under Part 1's flush rule, so no jsonl
   bulk writer has a caller.
2. **Part 1 (`read_frame`'s version source)** — says "a recorded version above
   `version`" without naming where the file records it -> the file's recorded
   version is the maximum non-null value of the declared `version` column, and 0
   when that column is absent.
3. **Part 1 (`schema`'s value type)** — `schema: dict` with no value type ->
   `dict[str, polars.DataType]`, in the order the format declares its columns,
   and `read_frame` returns the columns in that order.
4. **Part 1.1 (`dir`)** — `open_record`, `done_pairs`, `read_dir` and `release`
   take a `dir` whose meaning is unstated -> it is the **run directory**, and
   `data/trajectory_record.py` appends `records/` itself.
5. **Part 1.1 (offered names)** — the list gives no way for a caller to name the
   record files it read, which 2.5 requires for `build`'s `consumed.json` ->
   `record_path(dir, task_id, seed) -> Path` is added to this file's offered
   names; `done_pairs`, `read_dir` and `release` build their paths through it.
6. **Part 1.1 (who stamps a row)** — unstated -> `Writer.row(kind, **fields)`
   stamps `type` and `ts` on every row and, on a `meta` row, `version` and
   `record_id`; every other column is the caller's, and an undeclared field name
   raises.
7. **Part 1.1 (`record_id`)** — listed as a `meta` column while `read_dir`
   concatenates many files, leaving non-meta rows unattributable -> `read` and
   `read_dir` fill `record_id` on every row from that file's `meta` row;
   `Writer.row` still stamps it only on the `meta` row.
8. **Part 1.1 (`to_messages`'s shape)** — the six parameters are pinned, the
   message list is not -> `developer` (`instructions`, plus `"\n\n" +
   extra_developer` when it is not None), `user` (`task_text`), then per step
   `s < upto_step` an `assistant` message carrying that step's `gen.content` and
   a `user` message carrying `env.result`, or `no_code` when `env.action` is
   null. An earlier step's `reasoning` is never resent
   (`legacy/envs/collect/run_appworld.py:191-215`), and per-turn framing text
   belongs to the environment's `INSTRUCTIONS` and to `step`'s observation.
9. **Parts 1.2 and 1.3 (the writer's signature)** — "write, read" with no
   signature -> `write(path: Path, df: DataFrame) -> None`, which stamps
   `version`, selects the declared columns in order and calls `write_frame`, and
   `read(path: Path) -> DataFrame`.
10. **Part 1.7 (the two guards)** — `cuts` divides by `max_cuts - 1` and
    `assemble`'s clip slices `cap - 60` and `-40`, with no stated floor ->
    `cuts` raises `ValueError` naming `max_cuts` below 2 (today's hard stop,
    `legacy/pipeline/annotate/build.py:353-355`) and `assemble` raises
    `ValueError` naming `probe_result_cap` below 100.
11. **Part 0.2 (`data/build_training_dataset.py`'s annotation lines)** — its `imports:`
    names no third-party and its `reads:` no `constants/` file, while 2.5
    requires `consumed.json` to carry each split file's path and sha1, which only
    `constants/path_datasets.yaml` holds -> `imports: ...; [polars, PyYAML]` and
    `reads: the sample run's task records, constants/path_datasets.yaml (the
    splits block of cfg.data.env), the environment's split task-id files`.
12. **Part 1 (`read_frame` and a null column)** — a jsonl column every line
    writes as JSON `null` infers as Polars `Null` and would fail any type check
    -> such a column counts as **absent** and is filled from `DEFAULTS`;
    `REQUIRED` therefore names no column that a valid file may leave null
    throughout (`action` and `abort` on a task record, the per-`PROBE_KIND`
    columns on a prediction).
13. **Part 0.1 (`venv: any`)** — the dispatch brief reads it as the three venvs
    plus system `python3`, which has no Polars (3.10.12, measured 2026-09-17) ->
    the build keeps 0.1's definition, the interpreters of the `venvs:` map; only
    `data/probe_input.py`, whose import list is `re`, is additionally checked
    under system `python3`.
14. **Part 8.4 (`build`'s heartbeat unit)** — `unit` for `build` is `row`, while
    the countable unit before the example frame exists is the record file ->
    `build` emits one beat per record read, with `done` and `total` counted in
    records, and keeps 8.4's word `row`, because the verdict functions read the
    word and only diff `ts` and `done`.
15. **Part 2.5 (the thinking-prefix gate)** — "a `text` whose thinking part is
    not a prefix of the record's thinking" has no executable spelling ->
    `row.text.endswith(thinking[:cut])`, since `assemble` puts the thinking
    prefix last; splitting `text` on the `[THINKING]` marker would mis-fire on an
    observation that contains that marker.
16. **Part 1.5 (`build`'s `done.json`)** — `counts` and `metrics` are stated for
    `sample` and `inject` only -> `build` writes `counts = {records, events,
    events_skipped_no_action, events_skipped_short_think, examples,
    examples_train, examples_val, examples_test, tools, tools_unseen_in_train}`,
    `metrics = {}` (1.5 names train, eval and score as the metric owners) and
    `report = "report.md"`.
17. **Part 1 (`read_frame`'s type check)** — "a column present but of the wrong
    type still fails loudly" reads as a dtype comparison, which a jsonl file
    always fails: JSON integers infer as `Int64` against a declared `Int32`
    (measured in `external/appworld/venv` on 2026-09-17) -> the check is the read
    itself. `pl.read_ndjson(path, schema=<the declared dtypes of the present
    columns>)` and `pl.read_parquet(path, columns=...).cast(<the same>,
    strict=True)` both raise on a value the declared dtype cannot hold, while
    widening a JSON integer, list or partial struct to the declared dtype is
    silent and intended.
