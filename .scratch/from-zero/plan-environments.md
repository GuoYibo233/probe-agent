# Build plan: `data/environments/` (folder group: environments)

Written 2026-09-17 against `notes/plans/2026-09-14-structure-from-zero.md`
(Part 1, fixed), `notes/plans/2026-09-17-contracts.md` (Parts 4, 2.3, 2.5, 3.3,
5.3, 6.3 and the 0.2 entries) and the legacy code under `legacy/`.

Two files, both in the fixed tree, nothing else:
`data/environments/__init__.py`, `data/environments/appworld.py`.

Everything measured below was run on this machine on 2026-09-17; the commands
and their outputs are in section 3.

---

## 1. Files

### 1.1 `data/environments/__init__.py`

**One sentence.** The environment contract and the entrance: the `Environment`
base class with its nine one-line methods and seven class attributes, the
`StepObservation` dataclass, `open_env(name)`, and `requested_pairs`, the one
definition of what a run asks for.

**Venv.** `any` — module level is `dataclasses`, `importlib`, `pathlib`, `re`
and PyYAML; no repo import, no benchmark package. (0.2, 4.4.)

**Annotations (0.2, copied):**

```
imports: none (repo); [importlib, PyYAML]
used by: data/environments/appworld.py (subclass), agent/loop.py (open_env,
         StepObservation, requested_pairs), agent/inject.py,
         data/build_training_dataset.py (open_env, requested_pairs),
         train/methods/cgen.py, train/methods/cparam.py (open_env),
         eval/methods/cgen.py, eval/methods/cparam.py, eval/score_run.py,
         jobs/launch.py (tasks and requested_pairs), run.py (open_env and
         requested_pairs)
reads:   constants/path_datasets.yaml
writes:  -
venv:    any
```

**Module-level names, exactly (4.1):**

```python
VERSION: int                      # of the base contract itself; keyed into
                                  # sample, build and inject (2.2, 4.1, 9(a)#42)

@dataclass
class StepObservation:            # what step returns; 4.2
    action: str | None
    observation: str
    error_kind: str | None
    completed: bool

class Environment:
    """A benchmark that hands out tasks, steps, can try a call early and undo
    it, and judges."""

    NAME: str                     # the value on the data.env axis
    VERSION: int                  # of this environment's file
    INSTRUCTIONS: dict[str, str]  # variant name -> the developer message
    NO_CODE_MESSAGE: str          # what the agent is told when it wrote no call
    RESULT_CAP: int               # characters an observation is clipped to
    SEED: int                     # the environment's own seed
    SPLIT_ROLE: dict[str, str]    # benchmark split name -> train | val | test

def open_env(name: str) -> Environment
def requested_pairs(env: Environment, splits: list[str], tasks: list[str] | None,
                    n_tasks: int | None, seeds: list[int]
                    ) -> list[tuple[str, str, int]]   # (split, task_id, seed)
```

The nine methods the class declares, one line of body each (`raise
NotImplementedError` naming the method), with the signatures of 4.2:

```python
def tasks(self, split: str) -> list[str]
def open(self, task_id: str, seed: int) -> None
def step(self, reply_text: str) -> StepObservation
def speculate(self, call: str) -> dict
def judge(self) -> dict
def close(self) -> None
def split_args(self, text: str) -> tuple[str, list[tuple[str, str]], tuple[int, int]] | None
def build_call(self, tool: str, args: list[tuple[str, str]]) -> str
def complete_call(self, text: str) -> str | None
```

Plus one instance attribute the base declares and `open` sets (decision E3):

```python
task_text: str | None             # the benchmark's own instruction for the
                                  # opened task; agent/loop.py reads it right
                                  # after open() returns and writes it into the
                                  # record's meta row (1.1)
```

`VERSION` is assigned at module level, at column zero, exactly once, to an
integer literal (3.3); the class body writes `VERSION = VERSION`, which is
indented and therefore not a second match. Start at `1`.

**`open_env(name)` (4.1, and decisions E1/E2):**

1. Read `constants/path_datasets.yaml` (resolved as
   `Path(__file__).resolve().parents[2] / "constants" / "path_datasets.yaml"`;
   no absolute path in the source — `selfcheck` fails on `/home/` or `/net/`
   outside `constants/`, 8.6). Refuse with `ValueError` naming `name` and the
   blocks the file does have when it has no block for `name`.
2. `importlib.import_module(f"data.environments.{name}")` **inside the
   function**.
3. Find the module's classes that are a strict subclass of `Environment`;
   refuse with `ValueError` naming the module when there is not exactly one.
4. Instantiate it with no arguments, check the nine method names exist on the
   instance and the seven class attributes are set (`hasattr`), refuse naming
   each missing one, and return the instance.

**`requested_pairs` semantics (2.3, authoritative), in this order:**

for each `s` in `splits` **in the given order**, take `env.tasks(s)` **in the
file's order**, apply `tasks` as a filter over it (an id not in the split is
dropped here; the refusal is `jobs/launch.py`'s, 2.3), keep the **first
`n_tasks`** of what is left **of that split** (`n_tasks` is a cap per split,
never over the concatenation, 9(a)#47), concatenate the per-split lists in the
given split order, and cross with `seeds` in the given order, **task-major**:
every seed of one task is adjacent (decision E4). `n_tasks` null means no cap,
`tasks` null means no filter. It reads nothing but `env.tasks(s)`.

**Legacy source.** The ordering rules are today's request path:
`legacy/envs/collect/run_appworld.py:157-160` (split list, `--n` cap, shard
slice) and `:176` (the task x sample-index cross, which is the task-major
order), `legacy/pipeline/inject/live_appworld.py:708-723` (the `--task-ids`
filter, the `--n` cap, the pool rotation).

**Not ported.** The shard slice `ids[shard::num_shards]` and the pool rotation
`ids[piece:] + ids[:piece]` stay out of this function: rotation is the loop
piece's business (2.3) and lives in `agent/loop.py`. The out-of-split refusal
stays out: it is `jobs/launch.py`'s (2.3, 4.2). `StepObservation` and
`open_env` have no legacy counterpart; they are new.

---

### 1.2 `data/environments/appworld.py`

**One sentence.** `class AppWorld(Environment)`: the nine methods on the
AppWorld package, its instruction variants, its no-code message, and its call
syntax.

**Venv.** `any` at import and for the call-syntax methods (`tasks`,
`split_args`, `build_call`, `complete_call`); `appworld` to hold a world
(`open`, `step`, `speculate`, `judge`, `close`). The `from appworld import
AppWorld` statement sits inside `open` (decision E11); the other four world
methods use the handle `open` stored. (4.4, 0.2.)

**Annotations (0.2, copied):**

```
imports: data/environments/__init__.py; [the appworld package, inside open()]
used by: data/environments/__init__.py (by name)
reads:   constants/path_datasets.yaml, the split task-id files
writes:  the AppWorld per-task output directory, deleted by close()
venv:    any at import and for the call-syntax methods; appworld to hold a world
```

**Module-level literals, each at column zero, exactly once, a plain literal
(3.3, 4.1) — `experimental_settings/schema.py` reads all three with
`ast.literal_eval` over the parsed source and never imports this file:**

```python
VERSION = 1
INSTRUCTIONS = {"v1": """..."""}          # dict literal of string literals only
SPLIT_ROLE = {"train": "train", "dev": "val", "test": "test"}
```

The class body writes `VERSION = VERSION`, `INSTRUCTIONS = INSTRUCTIONS`,
`SPLIT_ROLE = SPLIT_ROLE` (indented, so not a second match). No f-string and no
`+` in `INSTRUCTIONS`: `ast.literal_eval` must succeed on the whole dict.

**Class attributes:**

| name | value | source |
|---|---|---|
| `NAME` | `"appworld"` | the `data.env` axis value (5.3) |
| `VERSION` | `1` | 4.4 |
| `INSTRUCTIONS` | `{"v1": <the collection SYSTEM text>}` | `legacy/envs/collect/run_appworld.py:24-43`, mirrored at `legacy/pipeline/inject/rebuild.py:52-70`; copy character for character |
| `NO_CODE_MESSAGE` | `"No ```python``` block found. Reply with exactly one python code block."` | `legacy/pipeline/inject/rebuild.py:76-77` |
| `RESULT_CAP` | `4000` | `legacy/pipeline/inject/exec_calls.py:137`, applied at `run_appworld.py:215` |
| `SEED` | `100` | `legacy/pipeline/inject/exec_calls.py:142` |
| `SPLIT_ROLE` | `{"train": "train", "dev": "val", "test": "test"}` | `legacy/pipeline/configs/p1_gptoss.json:10-14` with `legacy/pipeline/annotate/build.py:309-318`; AppWorld's `dev` is the role `val` and its `test_normal.txt` is the role `test` (4.1) |

The system text of an injection format is **not** part of `INSTRUCTIONS`: a
`FORMATS` entry's `system_text` is applied by `agent/loop.py` or by the
family's `wrap_prefetch` (7.3). `legacy/pipeline/inject/live_appworld.py:389-394`
concatenated the two; that concatenation does not come along.

**Construction.** `__init__(self)` takes no arguments. It reads
`constants/path_datasets.yaml` (same repo-relative resolution as `open_env`),
keeps `home`, `data` and `splits` from the `appworld:` block, and refuses with
`ValueError` when `data` is not `<home>/data` — AppWorld derives its data root
from its root directory and cannot be pointed elsewhere
(`external/appworld/venv/.../appworld/common/path_store.py:14,26-28`,
decision E11). No world is opened here.

**The nine methods.**

| method | what it does | legacy source |
|---|---|---|
| `tasks(split)` | the `splits[split]` file, read as text, split on `\n`, empty lines dropped, **never sorted**; `ValueError` naming the split and the keys it has when the split is unknown | `legacy/pipeline/annotate/build.py:299-306` (`read_unit_list`); the file has no trailing newline |
| `open(task_id, seed)` | set `os.environ["APPWORLD_ROOT"] = home`, import the package inside the function, build `AppWorld(task_id=task_id, experiment_name=f"{task_id}__s{seed}", random_seed=self.SEED)`, store the world, set `self.task_text = world.task.instruction`, and read and store the frozen clock `world.execute("print(DateTime.now())").strip()` (None when it starts with `Execution failed`) | `legacy/envs/collect/run_appworld.py:149-150,186-190`, `legacy/pipeline/inject/live_appworld.py:693,759-762,776-778` |
| `step(reply_text)` | `re.compile(r"```python\s*(.*?)```", re.S).search(reply_text)`; no match -> `StepObservation(None, "NO_CODE_BLOCK", None, False)` (decision E7); match -> `out = str(world.execute(m.group(1)))[:RESULT_CAP]`, `StepObservation(m.group(1), out, error_kind(out), world.task_completed())` | `legacy/envs/collect/run_appworld.py:45,203-220`, `legacy/pipeline/inject/live_appworld.py:806-819` |
| `speculate(call)` | the three-step of 4.3, below | `legacy/pipeline/inject/live_appworld.py:305-321`, `legacy/pipeline/inject/exec_calls.py:545-570` |
| `judge()` | `ev = world.evaluate()`; `d = ev.to_dict() if hasattr(ev, "to_dict") else ev`; return `d` when it is a dict with a boolean `success`, else `{"success": False, "eval_error": <message, 600 chars>}` on any exception or shape (decision E10) | `legacy/envs/collect/run_appworld.py:229-235`, `legacy/pipeline/inject/live_appworld.py:827-835` |
| `close()` | `world.close()`, then `shutil.rmtree(Path(home) / "experiments" / "outputs" / experiment_name, ignore_errors=True)`, then clear the stored world, `task_text` and clock; a second `close()` is a no-op | `legacy/pipeline/inject/live_appworld.py:754-756` |
| `split_args(text)` | below | `legacy/pipeline/annotate/rules.py:67,118-149,152-164` |
| `build_call(tool, args)` | below | shape from `legacy/pipeline/annotate/build.py:197-200`; the quoting is new (decision E5) |
| `complete_call(text)` | below | `legacy/pipeline/inject/parse_call.py:27-69` |

**`speculate(call)` — the three-step, in this order (4.3):**

1. `code_x, modes = requote(call, world.shell.user_ns)` — the branch order is
   `unparsable_raw`, `forced_str`, `literal`, `shell_var`, `quoted`, ported
   character for character from `legacy/pipeline/inject/exec_calls.py:161-229`
   with its `IDENT`, `POSKEY` and `ALWAYS_STR = {"app_name", "api_name"}`
   (`exec_calls.py:152-156`). An unparsable call becomes `print(<call>)` and is
   run, never skipped.
2. `world.save_state("probe")` (`CKPT`, `exec_calls.py:145`), then
   `exec_out = str(world.execute(code_x))[:RESULT_CAP]` inside a `try`.
3. In the `finally`: `world.load_state("probe")`, `world._set_datetime()`, then
   re-read `print(DateTime.now())` and **raise `RuntimeError` naming both
   strings when it differs from the clock `open` stored**. When `open` stored no
   clock, `speculate` raises before step 1 (decision E9).

Returns exactly `{"exec_code": str, "arg_modes": list[str], "exec_out": str,
"exec_ok": bool, "error_kind": str | None, "spec_s": float}` — `error_kind` from
the ported `error_kind(out)` (`exec_calls.py:269-306`, with `err_tail` **not**
ported), `exec_ok = error_kind is None`, and `spec_s` the wall time of the whole
three-step **measured with `time.clock_gettime(time.CLOCK_MONOTONIC)`, never
`time.time()`** (decision E12): AppWorld freezes the driver process's clock
while a world is open, so `time.time()`, `time.monotonic()`,
`time.perf_counter()` and `datetime.now()` all stand still, and only
`time.clock_gettime(CLOCK_MONOTONIC | CLOCK_REALTIME)` and `os.times().elapsed`
keep moving (measured 2026-09-17; the evidence is that every `gen.wall_s` in the
legacy live run
`/net/.../pipeline/inject/runs/fmt_smoke/p2_e1/live_50e1ac9_1.jsonl` is `0.0`).

**`split_args(text)`** returns `(tool, args, span)` or `None`:

- `m = AW_CALL.search(text)` with `AW_CALL = re.compile(r"apis\.(\w+)\.(\w+)\(")`
  (`rules.py:67`); `None` when there is no match.
- walk from the opening parenthesis counting `(` and `)` to the matching close
  at index `j` (`first_call_named`, `rules.py:152-164`); `None` when it never
  closes.
- `tool = f"apis.{m.group(1)}.{m.group(2)}"`.
- `args = split_args_named(text[i+1:j])` (`rules.py:118-149`) — quote- and
  bracket-aware split on top-level commas, `(\w+)\s*=\s*(.+)` with `re.S` for a
  named argument, `pos0`, `pos1`, ... for a positional one, each value
  `.strip().strip("\"'")`.
- `span = (m.start(), j + 1)`, so `text[span[0]:span[1]]` is the call itself.

**`build_call(tool, args)`** is the **inverse** of `split_args` over the args
`split_args` produces (4.2, and the build gate of 2.5). Join
`", "`-separated: a key matching `^pos\d+$` is written as the bare value, every
other key as `k=<value>`; wrap the value in a quote when it is empty, holds a
top-level `,` or `=`, or ends with an unbalanced bracket or quote — `'` when the
value holds no `'`, `"` when it holds a `'` but no `"`, and **raise
`ValueError`** naming the tool, the key and the value when it holds both
(decision E5; 0 of 4,040 real arguments, section 3). Never `repr()`: `repr`
escapes newlines and backslashes that `split_args` does not unescape.

**`complete_call(text)`** returns the first `apis.<app>.<api>(...)` in `text`
whose parentheses balance, or `None` (decision E6). Ported from
`legacy/pipeline/inject/parse_call.py:27-69`: inside a string only the closing
quote counts (single, double and triple), a backslash escapes the next
character, `#` runs to end of line, and an unterminated comment or an unbalanced
call returns `None`. Nothing is appended to the text. The legacy signature's
`start` parameter and its `(call, end)` tuple are dropped; the contract's
signature returns the call alone.

**Not ported, stated.**

- `legacy/pipeline/annotate/rules.py`: the value-only `split_args` (`:71-98`),
  `first_call_args` (`:101-113`), `mkparams` (`:167-178`), the whole BFCL and
  ALFWorld half (`:181-304`), and the probe-prompt constants `MAX_BOUNDS`,
  `MIN_THINK`, `HIST_ROUNDS`, `RESULT_CAP=400`, `SENT_RE`, `boundaries`, `clip`,
  `assemble` (`:17-62`) — those belong to `data/probe_input.py` (1.7) and to the
  setting (5.2), not to the environment. Note the name clash: `rules.RESULT_CAP`
  is 400 and is the **probe prompt**'s cap (`probe_result_cap`, 5.2), while this
  file's `RESULT_CAP` is 4,000 and is the **record**'s cap (1.7, 4.1).
- `legacy/pipeline/inject/exec_calls.py`: the replay cache and its version
  (`REQUOTE_VERSION`, `cache_key`, `load_cache`, `check_requote_version`,
  `:354-440`) — this file's `VERSION` covers the requote rule now (4.4); the
  `last_event_of_unit` skip of the restore (`:565-566`) — every speculation
  restores, with no exception; `err_tail` (`:248-267`), `is_bare_print`
  (`:231-246`), `prefix_sigs`, `load_steps`, `replay_unit`, `main` — the replay
  line's own acceptance measures, which no stage of this tree runs.
- `legacy/pipeline/inject/live_appworld.py`: everything but `speculate` and the
  world handling — the stream, the cuts, `find_head`, the formats, the claim,
  `selftest_shadow` — belongs to `agent/`, `data/probe_input.py` and
  `data/trajectory_record.py`.
- `legacy/envs/collect/run_appworld.py`: `resolve_seeds`, `traj_path`,
  `is_done`, `exp_name`, `traj_meta`, the heartbeat and the whole `main` — the
  loop's, the record's and the registry's business.
- `legacy/pipeline/inject/parse_call.py`: `call_at` (`:72-88`, the retired
  skeleton arm — `inject.arm` has three values and none is `skeleton`, 5.3) and
  `find_fence_close` (`:91-100`).
- AppWorld's own `load_task_ids` (`run_appworld.py:157`): `tasks` reads the
  split file named in `constants/path_datasets.yaml` instead, which is what
  keeps `tasks` in the `any` venv for `data/build_training_dataset.py` and
  `jobs/launch.py` (4.2).
- The process `chdir` (`run_appworld.py:149`, `live_appworld.py:692`): replaced
  by `APPWORLD_ROOT` (decision E11).

---

## 2. Order of construction, and what must exist first

1. **`constants/path_datasets.yaml`** (constants folder, not mine) must exist
   before either file can be run — both read it. The blocks these two files
   need, with the values measured on this machine:

   ```yaml
   venvs:
     appworld: /home/y-guo/reproduce/new1/external/appworld/venv/bin/python
     probe:    /home/y-guo/reproduce/new1/external/probe-env/bin/python
     vllm:     /home/y-guo/reproduce/new1/external/vllm-env/bin/python
   appworld:
     home:  /home/y-guo/reproduce/new1/external/appworld
     venv:  appworld
     data:  /home/y-guo/reproduce/new1/external/appworld/data
     splits:
       train: /home/y-guo/reproduce/new1/external/appworld/data/datasets/train.txt
       dev:   /home/y-guo/reproduce/new1/external/appworld/data/datasets/dev.txt
       test:  /home/y-guo/reproduce/new1/external/appworld/data/datasets/test_normal.txt
   ```

2. **`data/environments/__init__.py`** — imports no repo file (0.2), so nothing
   else must exist. `data/__init__.py` need not exist: `data` resolves as a
   namespace package, and when it does exist it imports Polars, which all three
   venvs have.
3. **`data/environments/appworld.py`, the `any` half** — needs 1 and 2.
4. **`data/environments/appworld.py`, the world half** — needs 3.

Nothing in this folder needs `experimental_settings/schema.py`, `models/`,
`agent/`, `train/`, `eval/` or `jobs/`. The dependency runs the other way:
`schema.py`'s loader reads this file's `INSTRUCTIONS` and `SPLIT_ROLE` literals
as source text (3.3, 5.3), `agent/loop.py` reads `env.task_text` after `open`
(decision E3), `jobs/launch.py` refuses an out-of-split `tasks` id against
`requested_pairs` (2.3), and `data/build_training_dataset.py` holds the call round-trip
gate over `build_call` (2.5).

---

## 3. Acceptance, CPU

Every command is run from the repo root — in a ticket that means the
implementer's **worktree** root, and that decides how the interpreters are
spelled. `external/` is git-ignored and absent from `HEAD`
(`git status --porcelain --ignored external` prints `!! external/`), so a
worktree has no `external/` directory and a relative `external/probe-env/bin/python`
does not resolve there. **Every command below names the interpreter by its
absolute path in the main tree**, which is also what
`constants/path_datasets.yaml`'s `venvs:` map holds:

```bash
PR=/home/y-guo/reproduce/new1/external/probe-env/bin/python      # 3.11
AW=/home/y-guo/reproduce/new1/external/appworld/venv/bin/python  # 3.12
VL=/home/y-guo/reproduce/new1/external/vllm-env/bin/python       # 3.12
```

The same reason puts the p1 trajectory corpus of B4 at its NFS path: `envs/runs`
is a symlink into `/net/...` and is untracked.

Everything here runs on CPU; AppWorld itself is a CPU package
(`legacy/pipeline/inject/live_appworld.py:1`), and a whole
open/execute/checkpoint/evaluate/close cycle took 17 s on this machine.

**Which interpreters the `any` test uses.** The three in the `venvs:` map
(0.1, 6.3, and `selfcheck`'s rule in 8.6). System `python3` (3.10) is *not* in
that map and has neither Polars nor NumPy, so once `data/__init__.py` exists,
`import data.environments` cannot work under it — the dispatch note that `any`
includes system `python3` does not survive `data/__init__.py`'s Polars import.
Both files are still written to standard library + PyYAML only, which A0b
checks by loading the module file directly under `python3`.

### A. `data/environments/__init__.py`

**A0 — imports under every interpreter of the `venvs:` map.**

```bash
for P in "$PR" "$AW" "$VL"; do
  $P -c "import data.environments as E; print(E.VERSION, sorted(n for n, v in vars(E.Environment).items() if callable(v)))"
done
```
Expected: three identical lines, exit 0:
`1 ['build_call', 'close', 'complete_call', 'judge', 'open', 'speculate', 'split_args', 'step', 'tasks']`
(the seven class attributes are annotations, so they are not in `vars`).

**A0b — standard library and PyYAML only, under system `python3` (3.10).**

```bash
python3 -c "
import importlib.util as u
s = u.spec_from_file_location('env_base', 'data/environments/__init__.py')
m = u.module_from_spec(s); s.loader.exec_module(m)
print(m.VERSION, m.StepObservation.__name__)"
```
Expected: `1 StepObservation`, exit 0.

**A1 — `StepObservation`'s four fields.**

```bash
"$PR" - <<'PY'
from data.environments import StepObservation as S
o = S(action=None, observation='NO_CODE_BLOCK', error_kind=None, completed=False)
print(o.action, o.observation, o.error_kind, o.completed)
PY
```
Expected: `None NO_CODE_BLOCK None False`, exit 0.

**A2 — `open_env` refuses an unknown environment by name.**

```bash
"$PR" - <<'PY'
from data.environments import open_env
try: open_env('nosuch')
except ValueError as e: print('REFUSED', 'nosuch' in str(e), 'appworld' in str(e))
PY
```
Expected: `REFUSED True True`, exit 0 (the message names the value asked for and
the blocks `constants/path_datasets.yaml` has).

**A3 — `requested_pairs`: per-split cap, split order, task-major cross.**

```bash
"$PR" - <<'PY'
from data.environments import requested_pairs
class E:
    def tasks(self, s): return {'train': ['a','b','c'], 'dev': ['d','e']}[s]
e = E()
print(requested_pairs(e, ['train','dev'], None, 2, [1,2]))
print(requested_pairs(e, ['dev','train'], ['b','d'], None, [7]))
print(requested_pairs(e, ['train'], ['zzz'], None, [1]))
print(requested_pairs(e, ['train'], None, None, [1]))
PY
```
Expected, exactly:
```
[('train', 'a', 1), ('train', 'a', 2), ('train', 'b', 1), ('train', 'b', 2), ('dev', 'd', 1), ('dev', 'd', 2), ('dev', 'e', 1), ('dev', 'e', 2)]
[('dev', 'd', 7), ('train', 'b', 7)]
[]
[('train', 'a', 1), ('train', 'b', 1), ('train', 'c', 1)]
```

**A4 — the `VERSION` line shape (3.3) and no absolute path (8.6).**

```bash
grep -c '^VERSION = [0-9]' data/environments/__init__.py
grep -n '/home/\|/net/' data/environments/__init__.py || echo NO_ABS_PATH
```
Expected: `1`, then `NO_ABS_PATH`.

### B. `data/environments/appworld.py`, the `any` half

**B0 — imports and the seven attributes, under every interpreter of the map.**

```bash
for P in "$PR" "$AW" "$VL"; do
  $P - <<'PY'
from data.environments import open_env
e = open_env('appworld')
print(e.NAME, e.VERSION, e.RESULT_CAP, e.SEED, sorted(e.INSTRUCTIONS), e.SPLIT_ROLE, type(e).__name__)
PY
done
```
Expected: three identical lines, exit 0:
`appworld 1 4000 100 ['v1'] {'train': 'train', 'dev': 'val', 'test': 'test'} AppWorld`.

**B1 — `tasks` reads the split files in file order.**

```bash
"$PR" - <<'PY'
from data.environments import open_env
e = open_env('appworld')
for s in ('train','dev','test'):
    ids = e.tasks(s); print(s, len(ids), ids[0], ids[-1])
try: e.tasks('val')
except ValueError as err: print('REFUSED', 'val' in str(err))
PY
```
Expected (measured):
```
train 90 82e2fac_1 aa8502b_3
dev 57 50e1ac9_1 4fab96f_3
test 168 3d9a636_1 bde252e_3
REFUSED True
```

**B2 — `split_args` on the three shapes, including the span.**

```bash
"$PR" - <<'PY'
from data.environments import open_env
e = open_env('appworld')
t = """print(apis.spotify.login(username="a@b.c", password='pw'))"""
tool, args, (s, x) = e.split_args(t)
print(tool, args, (s, x), t[s:x] == """apis.spotify.login(username="a@b.c", password='pw')""")
print(e.split_args('no call here'))
print(e.split_args("print(apis.a.b('x'))"))
print(e.split_args('print(apis.a.b('))
PY
```
Expected:
```
apis.spotify.login [('username', 'a@b.c'), ('password', 'pw')] (6, 57) True
None
('apis.a.b', [('pos0', 'x')], (6, 19))
None
```

**B3 — `build_call` is the inverse, on the four shapes that break a naive join.**

```bash
"$PR" - <<'PY'
from data.environments import open_env
e = open_env('appworld')
cases = [[('k','')], [('k','a, b'), ('pos0','x=y')],
         [('username','+1555'), ('pos0','# c\n  password="P!')],
         [('access_token','token'), ('page_index','0')]]
for args in cases:
    c = e.build_call('apis.a.b', args)
    back = e.split_args(c)
    print(back[1] == args, repr(c))
PY
```
Expected, exit 0:
```
True "apis.a.b(k='')"
True "apis.a.b(k='a, b', 'x=y')"
True 'apis.a.b(username=+1555, \'# c\n  password="P!\')'
True 'apis.a.b(access_token=token, page_index=0)'
```

**B4 — the round trip over the real corpus (the gate of 2.5, measured).**

```bash
"$PR" - <<'PY'
import glob, json
from data.environments import open_env
e = open_env('appworld')
n = p = ok = 0
for f in sorted(glob.glob('/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/envs/runs/p1/appworld_gptoss/*.jsonl')):
    for line in open(f):
        r = json.loads(line)
        if r.get('type') != 'env': continue
        a = (r.get('action') or '').strip()
        if not a: continue
        n += 1
        pr = e.split_args(a)
        if pr is None: continue
        p += 1
        tool, args, _ = pr
        b = e.split_args(e.build_call(tool, args))
        ok += 1 if (b and b[0] == tool and b[1] == args) else 0
print(n, p, ok)
PY
```
Expected: `4074 4040 4040`, exit 0, in about 4 s. (Measured with the rule of
section 1.2 on 2026-09-17 over the 315 p1 trajectories. With `repr()` quoting
instead, 4 of the first 476 parsed actions fail — that measurement is decision
E5's reason. The 34 actions `split_args` returns `None` for are steps whose code
block calls no api; see section 6's note to the build planner.)

**B5 — `complete_call`, the legacy cases (`parse_call.py:104-127`).**

```bash
"$PR" - <<'PY'
from data.environments import open_env
e = open_env('appworld')
cases = [
 ("""print(apis.venmo.login(username='a'))""", """apis.venmo.login(username='a')"""),
 ("""apis.phone.send_message(message="hi :) (really)")""", """apis.phone.send_message(message="hi :) (really)")"""),
 ("x = apis.a.b(c=apis.d.e(f=1), g=2)\nprint(x)", "apis.a.b(c=apis.d.e(f=1), g=2)"),
 ('apis.a.b(t="""a ) b""", u=1)', 'apis.a.b(t="""a ) b""", u=1)'),
 ("apis.a.b(\n  x=1,  # )))\n  y=2)", "apis.a.b(\n  x=1,  # )))\n  y=2)"),
 ("""print(apis.venmo.login(username='a'""", None),
 ("print(apis.venmo.login", None),
 ("just some thinking text", None)]
print(sum(1 for t, w in cases if e.complete_call(t) == w), 'of', len(cases))
PY
```
Expected: `8 of 8`, exit 0.

**B6 — the literal rule (3.3) and no absolute path, no module-level benchmark
import.**

```bash
grep -c '^VERSION = [0-9]' data/environments/appworld.py
grep -c '^INSTRUCTIONS = ' data/environments/appworld.py
grep -c '^SPLIT_ROLE = ' data/environments/appworld.py
grep -n '/home/\|/net/' data/environments/appworld.py || echo NO_ABS_PATH
"$PR" - <<'PY'
import ast
t = ast.parse(open('data/environments/appworld.py').read())
lit = {n.targets[0].id: ast.literal_eval(n.value) for n in t.body
       if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)}
print(sorted(lit['INSTRUCTIONS']), lit['SPLIT_ROLE'], lit['VERSION'])
top = [a.module or a.names[0].name for a in t.body if isinstance(a, (ast.Import, ast.ImportFrom))]
print('appworld_at_module_level', any('appworld' in m and 'data.environments' not in m for m in top))
PY
```
Expected: `1`, `1`, `1`, `NO_ABS_PATH`, then
`['v1'] {'train': 'train', 'dev': 'val', 'test': 'test'} 1` and
`appworld_at_module_level False`.

### C. `data/environments/appworld.py`, the world half (appworld venv, CPU)

**C0 — the whole life cycle on one dev task.**

```bash
"$AW" - <<'PY'
from pathlib import Path
from data.environments import open_env
e = open_env('appworld')
tid = e.tasks('dev')[0]
e.open(tid, 42)
print('TASK_TEXT', len(e.task_text) > 20)
o = e.step('thinking\n```python\nprint(1+1)\n```')
print('STEP', repr(o.action), repr(o.observation), o.error_kind, o.completed)
o2 = e.step('no code block here')
print('NOCODE', o2.action, o2.observation, o2.error_kind, o2.completed)
o3 = e.step('```python\nprint(apis.nosuch.thing(a=1))\n```')
print('ERRKIND', o3.error_kind, o3.observation.startswith('Execution failed'))
j = e.judge(); print('JUDGE', isinstance(j['success'], bool), sorted(j)[:3])
out = Path('/home/y-guo/reproduce/new1/external/appworld/experiments/outputs') / (tid + '__s42')
print('DIR_BEFORE', out.exists())
e.close()
print('DIR_AFTER', out.exists())
PY
```
Expected, exit 0, about 25 s:
```
TASK_TEXT True
STEP 'print(1+1)\n' '2\n' None False
NOCODE None NO_CODE_BLOCK None False
ERRKIND Exception True
JUDGE True ['difficulty', 'failures', 'num_tests']
DIR_BEFORE True
DIR_AFTER False
```

**C1 — `speculate` leaves the world and the clock unchanged.**

```bash
"$AW" - <<'PY'
from data.environments import open_env
e = open_env('appworld')
tid = e.tasks('dev')[0]
e.open(tid, 43)
before = e.step('```python\nprint(DateTime.now())\n```').observation
s = e.speculate('apis.api_docs.show_app_descriptions()')
print('KEYS', sorted(s))
print('OK', s['exec_ok'], s['error_kind'], s['exec_code'].startswith('print(apis.api_docs'), s['spec_s'] > 0)
print('CLOCK_SOURCE', s['spec_s'])
after = e.step('```python\nprint(DateTime.now())\n```').observation
print('CLOCK', before == after)
bad = e.speculate('apis.login(x=1)')
print('UNPARSABLE', bad['arg_modes'], bad['exec_ok'], bad['error_kind'])
e.close()
PY
```
Expected, exit 0:
```
KEYS ['arg_modes', 'error_kind', 'exec_code', 'exec_ok', 'exec_out', 'spec_s']
OK True None True True
CLOCK_SOURCE <a positive float; 1.519 measured on this machine>
CLOCK True
UNPARSABLE ['unparsable_raw'] False Exception
```
`CLOCK_SOURCE` is the check for decision E12: with `time.time()` it prints
`0.0` every time, because the world freezes the process clock.

**C2 — `speculate` before `open` refuses, and a second `close` is a no-op.**

```bash
"$AW" - <<'PY'
from data.environments import open_env
e = open_env('appworld')
try: e.speculate('apis.a.b()')
except RuntimeError as err: print('REFUSED', 'open' in str(err))
e.close(); e.close(); print('CLOSE_TWICE_OK')
PY
```
Expected: `REFUSED True`, then `CLOSE_TWICE_OK`, exit 0.

### D. Selfcheck lines that apply to these two files

`run.py selfcheck` does not exist yet; when it lands (8.6) these are the rules
it will run over this folder, and A4 / B6 above are the hand-run form of the
first four:

- one integer `VERSION` line at column zero in each of the two files, and one
  `INSTRUCTIONS` and one `SPLIT_ROLE` literal in `data/environments/appworld.py`
  (3.3, 4.1);
- the `data.env` axis literals in `experimental_settings/schema.py` equal the
  file names under `data/environments/` (5.3);
- the `data.instructions` axis literals are a subset of the union of every
  environment's `INSTRUCTIONS` keys (4.4, 5.3);
- the `sample.split` / `inject.split` axis literals are within the union of
  every environment's split keys, which are also its `SPLIT_ROLE` keys (5.3);
- each `any` file imports under **every** interpreter of the `venvs:` map (6.3)
  — A0 and B0;
- no `/home/` or `/net/` path in code outside `constants/` — A4 and B6;
- every `README.md` annotation line agrees with the real import graph, parsed
  with `ast` (0.1): the two annotation blocks in section 1 are those lines.

---

## 4. Acceptance, GPU or cross-host (for the main session)

**This folder has no GPU step and no cross-host step.** AppWorld runs on CPU,
and every method above is accepted on the login machine. Three checks belong to
the main session anyway, because they need files from other folders:

1. **After `agent/`, `models/` and `jobs/` land**, a debug sample run of the
   flagship workflow, which is the first time the environment is driven by the
   loop against a served agent model:
   `python3 run.py train_probe <setting> --debug --stage sample`, then, in the
   run directory under
   `/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/debug/sample/<key>/records/`:
   nine record files (3 tasks x 3 splits, one seed), each whose `meta` row has
   `env: appworld`, `env_seed: 100`, a non-empty `task_text`, and a `split` in
   `{train, dev, test}` matching the file the task came from; each whose `final`
   row has a boolean `success` and a `judge` string that parses as JSON; and no
   `env` row whose `result` is longer than 4,000 characters.
2. **After `agent/inject.py` and the probe service land**, a debug inject run:
   `python3 run.py inject <setting> --debug`, and in its records every `spec`
   row carries `exec_code`, `arg_modes`, `exec_out`, `exec_ok`, `error_kind` and
   `spec_s`, with no `RuntimeError` about a drifted clock anywhere in
   `log/<piece>.txt`. A drifted clock is a hard stop by design (4.3).
3. **After `run.py` lands**: `python3 run.py selfcheck` passes, covering
   section 3D.

---

## 5. Tickets

Three tickets, serial: T-ENV-2 needs T-ENV-1's module, T-ENV-3 edits the file
T-ENV-2 creates (so they must not run in one wave).

### T-ENV-1 — The environment contract and the entrance

- **Files:** `data/environments/__init__.py` (new).
- **What to do:** section 1.1 in full — `VERSION`, `StepObservation`, the
  `Environment` base class with its nine one-line methods, seven annotated class
  attributes and the `task_text` instance attribute, `open_env(name)` (the
  four steps, including the `constants/path_datasets.yaml` refusal and the
  single-subclass rule), and `requested_pairs` with the ordering of 2.3
  (per-split `n_tasks` cap, split order, task-major seed cross). Copy the
  signatures from 4.1 and 4.2 character for character. Read contracts 4.1, 4.2,
  2.3 and the 0.2 entry for this file.
- **Acceptance:** A0, A0b, A1, A2, A3, A4.
- **Needs from other folders:** `constants/path_datasets.yaml` with the
  `venvs:` map and the `appworld:` block of section 2 step 1 (constants folder).
  Nothing else.

### T-ENV-2 — AppWorld: the attributes and the call syntax

- **Files:** `data/environments/appworld.py` (new).
- **What to do:** section 1.2 down to and including `complete_call`, leaving
  `open`, `step`, `speculate`, `judge` and `close` inherited from the base (they
  still raise `NotImplementedError`; T-ENV-3 implements them). That is: the
  three module-level literals under the 3.3 shape, the seven class attributes
  with the legacy text copied character for character, `__init__` (the
  `path_datasets.yaml` block and the `data == <home>/data` refusal), `tasks`,
  `split_args`, `build_call` and `complete_call`. Port from
  `legacy/pipeline/annotate/rules.py:67,118-164`,
  `legacy/pipeline/annotate/build.py:197-200,299-306`,
  `legacy/pipeline/inject/parse_call.py:27-69`,
  `legacy/envs/collect/run_appworld.py:24-43`,
  `legacy/pipeline/inject/rebuild.py:76-77`,
  `legacy/pipeline/inject/exec_calls.py:137,142`. Read contracts 4.1, 4.2, 4.4,
  2.5 (the build gates), 3.3 (the literal rule), 5.3, 6.3.
- **Acceptance:** B0, B1, B2, B3, B4, B5, B6.
- **Needs from other folders:** `constants/path_datasets.yaml` (constants
  folder), and `data/environments/__init__.py` with `Environment`,
  `StepObservation` and `open_env` (T-ENV-1).

### T-ENV-3 — AppWorld: holding a world

- **Files:** `data/environments/appworld.py` (edit).
- **What to do:** the five world methods of section 1.2 — `open` (the
  `APPWORLD_ROOT` assignment, the in-function package import, the
  `<task_id>__s<seed>` experiment name, `random_seed=SEED`, `task_text`, the
  frozen clock), `step` (the ```` ```python ```` extraction, the `RESULT_CAP`
  clip, `error_kind`, `task_completed`), `speculate` (the three-step of 4.3 with
  `requote` and `error_kind` ported from
  `legacy/pipeline/inject/exec_calls.py:161-229,269-306` and the restore and
  clock assertion in a `finally`, `legacy/pipeline/inject/live_appworld.py:305-321`,
  `legacy/pipeline/inject/exec_calls.py:545-570`), `judge`
  (`legacy/envs/collect/run_appworld.py:229-235`) and `close` (the rmtree of
  `legacy/pipeline/inject/live_appworld.py:754-756`). **`spec_s` is read with
  `time.clock_gettime(time.CLOCK_MONOTONIC)`, never `time.time()`** — an open
  AppWorld world freezes the process clock (decision E12, and C1's
  `CLOCK_SOURCE` line is the check). Bump nothing: `VERSION`
  stays 1 — the file is not released until all nine methods are there. Read
  contracts 4.2, 4.3, 4.4, 1.1 (the `spec` and `env` row columns the returns
  feed).
- **Acceptance:** C0, C1, C2, and B0-B6 again (the file must still import and
  behave under the three interpreters).
- **Needs from other folders:** none beyond T-ENV-2. The AppWorld clone and its
  venv already exist at `external/appworld`; no package is installed.

---

## 6. Contract errata settled here

Each line is also appended to
`.scratch/from-zero/contract-errata.md`.

- **E1 — 4.1, `open_env`'s class discovery.** 4.1 says it "returns an instance"
  without saying which class. The build takes the module's one strict subclass
  of `Environment` and refuses, naming the module, on zero or more than one.
- **E2 — 4.1, `open_env` and `constants/path_datasets.yaml`.** 4.1 does not say
  `open_env` reads it while the 0.2 annotation does. The build reads it first,
  to refuse an environment with no block before importing anything; each
  environment file reads its own block itself.
- **E3 — 4.2 against 1.1, the task text.** 1.1 says `agent/loop.py` captures
  `task_text` after `Environment.open` and that the nine methods do not hand it
  out, which leaves no path to it. The build has `open` set the instance
  attribute `task_text` (AppWorld's `world.task.instruction`), which the loop
  reads and `close` clears. **Cross-folder: `agent/loop.py` must read
  `env.task_text`.**
- **E4 — 2.3, `requested_pairs`' cross with seeds.** The order of the cross is
  unstated. The build crosses task-major (every seed of one task adjacent), as
  `legacy/envs/collect/run_appworld.py:176` does.
- **E5 — 4.2, `build_call`'s quoting.** 4.2 says a value is quoted with
  `repr()`. The build wraps instead in a bare `'` (or `"` when the value holds a
  `'`) and raises `ValueError` when it holds both, and also quotes an empty
  value and one with an unbalanced bracket or quote: `repr()` escapes newlines
  and backslashes that `split_args` never unescapes, which fails 2.5's round-trip
  gate on 4 of the first 476 real actions, while bare quoting passes 4,040 of
  4,040 over all 315 p1 trajectories.
- **E6 — 4.2, `complete_call`.** "Finish a call the probe generated but cut off"
  and "None when it cannot be balanced" cannot both hold. The build extracts the
  first `apis.<app>.<api>(...)` whose parentheses balance
  (`legacy/pipeline/inject/parse_call.py:27-69`, quote-, escape- and
  comment-aware) and returns None when none does; nothing is appended.
- **E7 — 4.2, `step` with no code block.** The `observation` for a null `action`
  is unstated. The build writes `NO_CODE_BLOCK` with `error_kind` None and
  `completed` False, which is today's record mark
  (`legacy/pipeline/inject/rebuild.py:78`).
- **E8 — 4.2, `open`'s per-task directory.** "Named so two seeds never share the
  benchmark's own output directory" names no shape. The build uses AppWorld
  `experiment_name = f"{task_id}__s{seed}"` (the `record_id` of 1.1) and has
  `close` delete `<home>/experiments/outputs/<experiment_name>`.
- **E9 — 4.3, `speculate`'s clock baseline.** The frozen clock has no stated
  source, and legacy skipped the guard when its first read failed
  (`live_appworld.py:777-778`). The build reads and stores it in `open` and has
  `speculate` raise when there is none, so the guard is never silently off.
- **E10 — 4.2, `judge` when `evaluate()` raises.** 4.2 promises a dict with a
  boolean `success`; AppWorld's `evaluate()` can raise
  (`legacy/envs/collect/run_appworld.py:232-233` recorded `eval_error` with no
  `success`). The build returns
  `{"success": False, "eval_error": "<message>"}` on any exception or
  non-conforming shape.
- **E11 — 4.4 and 6.3, holding the world.** 4.4 says the benchmark package is
  imported inside five methods and 6.3 gives the environment a `data` column
  AppWorld cannot be pointed at. The build puts the `from appworld import
  AppWorld` statement in `open` alone (the other four use the handle it stored),
  sets `APPWORLD_ROOT` to the `home` column instead of a process `chdir`
  (`appworld/common/path_store.py:14`), and refuses at construction when `data`
  is not `<home>/data`.

- **E12 — 4.3, `spec_s` and the frozen process clock.** 4.3 lists `spec_s`
  without saying how it is read, and AppWorld freezes the driver process's
  clock while a world is open. The build reads
  `time.clock_gettime(time.CLOCK_MONOTONIC)` at both ends of the three-step.
  Measured 2026-09-17 with a world open: `time.time()`, `time.monotonic()`,
  `time.perf_counter()` and `datetime.now().timestamp()` return a **0.0** delta
  across a 0.25 s sleep, while `time.clock_gettime(CLOCK_MONOTONIC)`,
  `time.clock_gettime(CLOCK_REALTIME)` and `os.times().elapsed` return 0.25.

**Not mine to settle, flagged for the record, agent and registry planners.**
The frozen clock of E12 is not the environment's alone: every wall-clock field
a loop piece writes is read in the same process while the world is open — the
`ts` column of every record row, `gen.wall_s`, `final.wall_s` and
`final.finished_at` (1.1), and the heartbeat's timestamps (8.4). Today's code
already loses them: **every `gen.wall_s` in the legacy live run
`/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/inject/runs/fmt_smoke/p2_e1/live_50e1ac9_1.jsonl`
is `0.0`** (`legacy/pipeline/inject/live_appworld.py:790,800` reads
`time.time()`), which is a wrong number with no crash — the class every gate in
the contracts exists for. Those files must read
`time.clock_gettime(time.CLOCK_REALTIME)` for a unix timestamp and
`time.clock_gettime(time.CLOCK_MONOTONIC)` for a duration whenever the code can
run in a loop piece. The registry's verdicts rest on heartbeat timestamps (8.5),
so a frozen clock there stalls every verdict on a `sample` or `inject` run.

**Not mine to settle, flagged for the build planner and the integrator.** 2.5
makes "a non-null `action` that `env.split_args` returns None for" a hard stop
that ends the build naming the record and the step. Measured over the 315 p1
trajectories: 24 of 4,074 non-null actions (0.6%, in 13 of the 315
trajectories) contain no `apis.<app>.<api>(` at all — they are real steps whose
code block only inspects the namespace, parses text with `re`, or prints a
variable. Under 2.5 as written, every build over p1-shaped data stops. The
environment side is not the place to soften it (`split_args` must keep
returning None for text with no call); `data/build_training_dataset.py`'s planner has to
decide whether such an event is skipped and counted like a null action or
whether the stop stands.
