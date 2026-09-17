# 05 the environment contract and AppWorld

Status: ready-for-agent
Blocked by: 01
Spec: .scratch/from-zero/spec.md (sections 2, 3, 4, 5, 7)

## What to do

Two files. Contracts Part 4 (4.1 through 4.4), 2.3 (`requested_pairs`), 2.5 (the
gates this file's methods serve), 3.3 (the literal rule), 5.3 and 6.3 are the
specification; read Part 4 in full.

```
data/environments/__init__.py   venv: any   imports: none (repo); [importlib, PyYAML]
                                reads: constants/path_datasets.yaml   VERSION = 1
data/environments/appworld.py   venv: any at import and for the call-syntax methods; appworld to hold a world
                                imports: data/environments/__init__.py; [the appworld package, inside open()]
                                used by: data/environments/__init__.py (by name)
                                reads: constants/path_datasets.yaml, the split task-id files
                                writes: the AppWorld per-task output directory, deleted by close()
                                VERSION = 1
README.md                       your two lines only
```

Build in three passes; the acceptance is grouped the same way: (A) the base
module, (B) `appworld.py`'s literals, attributes and call syntax, (C)
`appworld.py`'s five world methods.

### 1. `data/environments/__init__.py` (contracts 4.1, 4.2, 2.3)

```python
VERSION = 1                       # of the base contract itself; keyed into sample, build and inject (2.2)

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
    task_text: str | None         # set by open(), read by agent/loop.py, cleared by close()

    def tasks(self, split: str) -> list[str]
    def open(self, task_id: str, seed: int) -> None
    def step(self, reply_text: str) -> StepObservation
    def speculate(self, call: str) -> dict
    def judge(self) -> dict
    def close(self) -> None
    def split_args(self, text: str) -> tuple[str, list[tuple[str, str]], tuple[int, int]] | None
    def build_call(self, tool: str, args: list[tuple[str, str]]) -> str
    def complete_call(self, text: str) -> str | None

def open_env(name: str) -> Environment
def requested_pairs(env: Environment, splits: list[str], tasks: list[str] | None,
                    n_tasks: int | None, seeds: list[int]
                    ) -> list[tuple[str, str, int]]   # (split, task_id, seed)
```

Each of the nine methods has **one line of body**: `raise NotImplementedError`
naming the method. No logic in the base.

**Decision already made (errata E3):** the base declares the instance attribute
`task_text`, which `open` sets and `close` clears. 1.1 has `agent/loop.py`
capture the task text after `Environment.open` while 4.2's nine methods hand out
no task text; this attribute is the path.

`VERSION` is assigned at module level, column zero, exactly once, to an integer
literal (3.3); the class body writes `VERSION = VERSION`, which is indented and
therefore not a second match. Start at `1`.

**`open_env(name)` (4.1, errata E1 and E2), in this order:**

1. Read `constants/path_datasets.yaml`, resolved as
   `Path(__file__).resolve().parents[2] / "constants" / "path_datasets.yaml"` —
   **no absolute path in the source**. Refuse with `ValueError` naming `name` and
   the blocks the file does have, when it has no block for `name`. (4.1 does not
   say it reads that file while the 0.2 annotation does; it reads it first, so an
   unknown environment is refused before anything is imported.)
2. `importlib.import_module(f"data.environments.{name}")`, **inside the
   function**.
3. Find the module's classes that are a **strict subclass** of `Environment`;
   refuse with `ValueError` naming the module when there is not exactly one.
4. Instantiate it with no arguments, check the nine method names exist on the
   instance and the seven class attributes are set (`hasattr`), refuse naming
   each missing one, and return the instance.

**`requested_pairs` semantics (2.3, authoritative), in this order:** for each `s`
in `splits` **in the given order**, take `env.tasks(s)` **in the file's order**,
apply `tasks` as a filter over it (an id not in the split is dropped here; the
refusal is `jobs/launch.py`'s), keep the **first `n_tasks` of what is left of
that split** (`n_tasks` is a cap **per split**, never over the concatenation),
concatenate the per-split lists in the given split order, and cross with `seeds`
in the given order, **task-major**: every seed of one task is adjacent (errata
E4, `legacy/envs/collect/run_appworld.py:176`). `n_tasks` null means no cap,
`tasks` null means no filter. It reads nothing but `env.tasks(s)`.

Legacy sources: `legacy/envs/collect/run_appworld.py:157-160` (split list, `--n`
cap, shard slice), `:176` (the task x sample-index cross);
`legacy/pipeline/inject/live_appworld.py:708-723` (the `--task-ids` filter, the
`--n` cap, the pool rotation).

**Not ported:** the shard slice `ids[shard::num_shards]` and the pool rotation
`ids[piece:] + ids[:piece]` — rotation is the loop piece's business and lives in
`agent/loop.py`; the out-of-split refusal — it is `jobs/launch.py`'s.
`StepObservation` and `open_env` have no legacy counterpart.

### 2. `data/environments/appworld.py`, the `any` half (contracts 4.1, 4.2, 4.4)

Three module-level literals, each at column zero, exactly once, a plain literal
`ast.literal_eval` succeeds on — `experimental_settings/schema.py` reads all
three over the parsed source and never imports this file:

```python
VERSION = 1
INSTRUCTIONS = {"v1": """..."""}          # a dict literal of string literals only
SPLIT_ROLE = {"train": "train", "dev": "val", "test": "test"}
```

No f-string and no `+` inside `INSTRUCTIONS`. The class body writes
`VERSION = VERSION`, `INSTRUCTIONS = INSTRUCTIONS`, `SPLIT_ROLE = SPLIT_ROLE`
(indented, so not a second match).

Class attributes:

| name | value | source |
|---|---|---|
| `NAME` | `"appworld"` | the `data.env` axis value (5.3) |
| `VERSION` | `1` | 4.4 |
| `INSTRUCTIONS` | `{"v1": <the collection SYSTEM text>}` | `legacy/envs/collect/run_appworld.py:24-43`, mirrored at `legacy/pipeline/inject/rebuild.py:52-70`; copy character for character |
| `NO_CODE_MESSAGE` | ``"No ```python``` block found. Reply with exactly one python code block."`` | `legacy/pipeline/inject/rebuild.py:76-77` |
| `RESULT_CAP` | `4000` | `legacy/pipeline/inject/exec_calls.py:137`, applied at `run_appworld.py:215` |
| `SEED` | `100` | `legacy/pipeline/inject/exec_calls.py:142` |
| `SPLIT_ROLE` | `{"train": "train", "dev": "val", "test": "test"}` | `legacy/pipeline/configs/p1_gptoss.json:10-14` with `legacy/pipeline/annotate/build.py:309-318` |

The system text of an injection format is **not** part of `INSTRUCTIONS`: a
`FORMATS` entry's `system_text` is applied by `agent/loop.py` or by the family's
`wrap_prefetch` (7.3). `legacy/pipeline/inject/live_appworld.py:389-394`
concatenated the two; that concatenation does not come along.

**Construction.** `__init__(self)` takes no arguments. It reads
`constants/path_datasets.yaml` (same repo-relative resolution as `open_env`),
keeps `home`, `data` and `splits` from the `appworld:` block, and refuses with
`ValueError` when `data` is not `<home>/data` — AppWorld derives its data root
from its root directory and cannot be pointed elsewhere
(`appworld/common/path_store.py:14,26-28`, errata E11). No world is opened here.

**The four `any` methods:**

- `tasks(split)`: the `splits[split]` file read as text, split on `\n`, empty
  lines dropped, **never sorted**; `ValueError` naming the split and the keys it
  has when the split is unknown. Source
  `legacy/pipeline/annotate/build.py:299-306` (`read_unit_list`); the files have
  no trailing newline. **Not ported:** AppWorld's own `load_task_ids`
  (`run_appworld.py:157`) — reading the split file named in
  `constants/path_datasets.yaml` is what keeps `tasks` in the `any` venv for
  `data/build_dataset.py` and `jobs/launch.py`.
- `split_args(text) -> (tool, args, span) | None`:
  `m = AW_CALL.search(text)` with
  `AW_CALL = re.compile(r"apis\.(\w+)\.(\w+)\(")` (`rules.py:67`); `None` when
  there is no match. Walk from the opening parenthesis counting `(` and `)` to
  the matching close at index `j` (`first_call_named`, `rules.py:152-164`);
  `None` when it never closes. `tool = f"apis.{m.group(1)}.{m.group(2)}"`.
  `args = split_args_named(text[i+1:j])` (`rules.py:118-149`) — quote- and
  bracket-aware split on top-level commas, `(\w+)\s*=\s*(.+)` with `re.S` for a
  named argument, `pos0`, `pos1`, … for a positional one, each value
  `.strip().strip("\"'")`. `span = (m.start(), j + 1)`, so `text[span[0]:span[1]]`
  is the call itself. **It keeps returning `None` for text with no call**; what
  the build does with that is `data/build_dataset.py`'s (ticket 09).
- `build_call(tool, args)` is the **inverse** of `split_args` over the args
  `split_args` produces (4.2, and the build gate of 2.5). Join `", "`-separated:
  a key matching `^pos\d+$` is written as the bare value, every other key as
  `k=<value>`; wrap the value in a quote when it is empty, holds a top-level `,`
  or `=`, or ends with an unbalanced bracket or quote — `'` when the value holds
  no `'`, `"` when it holds a `'` but no `"`, and **raise `ValueError`** naming
  the tool, the key and the value when it holds both.
  **Decision already made (errata E5): never `repr()`.** 4.2 says a value is
  quoted with `repr()`; `repr` escapes newlines and backslashes that `split_args`
  never unescapes, which fails 2.5's round-trip gate on 4 of the first 476 real
  actions, while bare quoting passes 4,040 of 4,040 over all 315 p1
  trajectories. Shape from `legacy/pipeline/annotate/build.py:197-200`; the
  quoting is new.
- `complete_call(text) -> str | None`: the first `apis.<app>.<api>(...)` in
  `text` whose parentheses balance, or `None` (errata E6: "finish a call the
  probe generated but cut off" and "None when it cannot be balanced" cannot both
  hold). Ported from `legacy/pipeline/inject/parse_call.py:27-69`: inside a
  string only the closing quote counts (single, double and triple), a backslash
  escapes the next character, `#` runs to end of line, and an unterminated
  comment or an unbalanced call returns `None`. **Nothing is appended.** The
  legacy signature's `start` parameter and its `(call, end)` tuple are dropped.

### 3. `data/environments/appworld.py`, the world half (contracts 4.2, 4.3)

The `from appworld import AppWorld` statement sits **in `open` alone** (errata
E11); the other four world methods use the handle `open` stored.

- `open(task_id, seed)`: set `os.environ["APPWORLD_ROOT"] = home` (**not** a
  process `chdir`, `appworld/common/path_store.py:14`), import the package inside
  the function, build
  `AppWorld(task_id=task_id, experiment_name=f"{task_id}__s{seed}", random_seed=self.SEED)`
  — the experiment name is 1.1's `record_id`, so two seeds never share the
  benchmark's own output directory (errata E8) — store the world, set
  `self.task_text = world.task.instruction`, and read and store the frozen clock
  `world.execute("print(DateTime.now())").strip()` (None when it starts with
  `Execution failed`). Sources `legacy/envs/collect/run_appworld.py:149-150,186-190`,
  `legacy/pipeline/inject/live_appworld.py:693,759-762,776-778`.
- `step(reply_text)`: `re.compile(r"```python\s*(.*?)```", re.S).search(...)`; no
  match -> `StepObservation(None, "NO_CODE_BLOCK", None, False)` (errata E7,
  today's record mark `rebuild.py:78`); match ->
  `out = str(world.execute(m.group(1)))[:RESULT_CAP]`,
  `StepObservation(m.group(1), out, error_kind(out), world.task_completed())`.
  Sources `run_appworld.py:45,203-220`, `live_appworld.py:806-819`.
- `speculate(call)`: the three-step of 4.3, in this order.
  1. `code_x, modes = requote(call, world.shell.user_ns)` — the branch order is
     `unparsable_raw`, `forced_str`, `literal`, `shell_var`, `quoted`, ported
     character for character from
     `legacy/pipeline/inject/exec_calls.py:161-229` with its `IDENT`, `POSKEY`
     and `ALWAYS_STR = {"app_name", "api_name"}` (`:152-156`). An unparsable call
     becomes `print(<call>)` and **is run**, never skipped.
  2. `world.save_state("probe")` (`CKPT`, `exec_calls.py:145`), then
     `exec_out = str(world.execute(code_x))[:RESULT_CAP]` inside a `try`.
  3. In the `finally`: `world.load_state("probe")`, `world._set_datetime()`, then
     re-read `print(DateTime.now())` and **raise `RuntimeError` naming both
     strings when it differs from the clock `open` stored**. When `open` stored
     no clock, `speculate` raises **before** step 1 (errata E9: legacy skipped
     the guard when its first read failed, so the guard was silently off).

  Returns exactly `{"exec_code": str, "arg_modes": list[str], "exec_out": str,
  "exec_ok": bool, "error_kind": str | None, "spec_s": float}` — `error_kind`
  from the ported `error_kind(out)` (`exec_calls.py:269-306`, with `err_tail`
  **not** ported), `exec_ok = error_kind is None`, and `spec_s` the wall time of
  the whole three-step **measured with
  `time.clock_gettime(time.CLOCK_MONOTONIC)`, never `time.time()`** (errata
  E12): an open AppWorld world freezes the driver process's clock, so
  `time.time()`, `time.monotonic()`, `time.perf_counter()` and `datetime.now()`
  all return a 0.0 delta while `clock_gettime` and `os.times().elapsed` keep
  moving (measured 2026-09-17; every `gen.wall_s` in the legacy live run is
  `0.0`). Sources `live_appworld.py:305-321`, `exec_calls.py:545-570`.
- `judge()`: `ev = world.evaluate()`;
  `d = ev.to_dict() if hasattr(ev, "to_dict") else ev`; return `d` when it is a
  dict with a boolean `success`, else `{"success": False, "eval_error": <message,
  600 chars>}` on any exception or shape (errata E10). Sources
  `run_appworld.py:229-235`, `live_appworld.py:827-835`.
- `close()`: `world.close()`, then
  `shutil.rmtree(Path(home) / "experiments" / "outputs" / experiment_name,
  ignore_errors=True)`, then clear the stored world, `task_text` and clock; a
  second `close()` is a no-op. Source `live_appworld.py:754-756`.

### Not ported, stated

`legacy/pipeline/annotate/rules.py`: the value-only `split_args` (`:71-98`),
`first_call_args` (`:101-113`), `mkparams` (`:167-178`), the whole BFCL and
ALFWorld half (`:181-304`), and the probe-prompt constants `MAX_BOUNDS`,
`MIN_THINK`, `HIST_ROUNDS`, `RESULT_CAP=400`, `SENT_RE`, `boundaries`, `clip`,
`assemble` (`:17-62`) — those are `data/probe_input.py`'s and the setting's.
**Note the name clash:** `rules.RESULT_CAP` is 400 and is the *probe prompt*'s
cap (`build.probe_result_cap`), while this file's `RESULT_CAP` is 4,000 and is
the *record*'s cap.
`legacy/pipeline/inject/exec_calls.py`: the replay cache and its version
(`:354-440`) — this file's `VERSION` covers the requote rule now; the
`last_event_of_unit` skip of the restore (`:565-566`) — every speculation
restores, with no exception; `err_tail` (`:248-267`), `is_bare_print`
(`:231-246`), `prefix_sigs`, `load_steps`, `replay_unit`, `main`.
`legacy/pipeline/inject/live_appworld.py`: everything but `speculate` and the
world handling. `legacy/envs/collect/run_appworld.py`: `resolve_seeds`,
`traj_path`, `is_done`, `exp_name`, `traj_meta`, the heartbeat and the whole
`main`. `legacy/pipeline/inject/parse_call.py`: `call_at` (`:72-88`, the retired
skeleton arm) and `find_fence_close` (`:91-100`). The process `chdir`
(`run_appworld.py:149`, `live_appworld.py:692`).

## Acceptance

Run every command from the repo root and paste the real output.

```bash
PR=/home/y-guo/reproduce/new1/external/probe-env/bin/python
AW=/home/y-guo/reproduce/new1/external/appworld/venv/bin/python
VL=/home/y-guo/reproduce/new1/external/vllm-env/bin/python
```

**A0 — imports under every interpreter of the `venvs:` map.**
```bash
for P in "$PR" "$AW" "$VL"; do
  $P -c "import data.environments as E; print(E.VERSION, sorted(n for n, v in vars(E.Environment).items() if callable(v)))"
done
```
Expected: three identical lines, exit 0:
`1 ['build_call', 'close', 'complete_call', 'judge', 'open', 'speculate', 'split_args', 'step', 'tasks']`

**A0b — standard library and PyYAML only, under system `python3`.**
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
Expected: `REFUSED True True`, exit 0.

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

**A4 — the `VERSION` line shape and no absolute path.**
```bash
grep -c '^VERSION = [0-9]' data/environments/__init__.py
grep -n '/home/\|/net/' data/environments/__init__.py || echo NO_ABS_PATH
```
Expected: `1`, then `NO_ABS_PATH`.

**B0 — the seven attributes, under every interpreter of the map.**
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
`appworld 1 4000 100 ['v1'] {'train': 'train', 'dev': 'val', 'test': 'test'} AppWorld`

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
Expected: `4074 4040 4040`, exit 0, in about 4 s. The 34 actions `split_args`
returns `None` for split two ways, measured on 2026-09-17: **24 code blocks that
call no api at all** (in 13 of the 315 trajectories) plus **10 whose api call
never closes its parentheses** for the paren walk (in 9 trajectories) — 22
trajectories in all, 0.83% of the non-null actions. Ticket 09 skips and counts
both kinds as `counts.events_skipped_no_call`.

**B5 — `complete_call`, the legacy cases.**
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

**B6 — the literal rule, no absolute path, no module-level benchmark import.**
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

**C0 — the whole life cycle on one dev task** (appworld venv, CPU, about 25 s).
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
Expected, exit 0:
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
`CLOCK_SOURCE` is the check for the frozen process clock: with `time.time()` it
prints `0.0` every time.

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

**C3 — rerun B0-B6 after the world half lands, and paste them.**

### Selfcheck lines that apply later

`run.py selfcheck` (ticket 15) will check: one integer `VERSION` at column zero in
each of the two files, and one `INSTRUCTIONS` and one `SPLIT_ROLE` literal in
`appworld.py` (A4, B6); the `data.env` axis literals equal the file names under
`data/environments/`; `data.instructions` is within the union of every
environment's `INSTRUCTIONS` keys; the split axes are within the union of every
`SPLIT_ROLE`'s keys; each file imports under every interpreter of the `venvs:`
map (A0, B0); no `/home/` or `/net/` path in code outside `constants/`; and every
`README.md` annotation line agrees with the `ast`-parsed import graph.

### GPU / main session — not yours

No GPU step and no cross-host step in this folder; AppWorld is CPU. Three
whole-tree checks belong to the main session because they need other folders:
a `--debug` sample walk leaving nine record files whose `meta` rows carry
`env: appworld`, `env_seed: 100`, a non-empty `task_text` and a `split` matching
the file the task came from, with no `env.result` longer than 4,000 characters; a
`--debug` inject walk whose `spec` rows carry all six speculation fields with no
clock-drift `RuntimeError` in `log/<piece>.txt`; and `run.py selfcheck`.

## Comments
