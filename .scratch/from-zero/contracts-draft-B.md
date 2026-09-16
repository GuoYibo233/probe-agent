# new1 contracts, draft B — the interfaces between the files of the fixed tree

Written 2026-09-17 against the fourth draft's Part 1 tree
(`notes/plans/2026-09-14-structure-from-zero.md`), the four Fable reviews and
their synthesis (`notes/plans/2026-09-17-structure-review-synthesis.md`), the
third draft's Part 2 (`git show 771a6e5:plans/2026-09-14-structure-from-zero.md`)
and the legacy code under `legacy/`.

This draft is written from one standpoint: **extension first**. Every interface
below was chosen so that the seven extension scenarios (a new environment, a new
probe method, a new hyperparameter, a new record field, a new injection format, a
new probe backbone, a new agent family) touch as few of the tree's files as
possible, and so that the file list per scenario can be written down in advance.
Section 0.4 is that list; the rest of the document is what makes it true.

Three rules govern the whole document.

1. **The tree is fixed.** No file is added, removed, moved, split or renamed.
   Where a mechanism has no obvious file, it goes into the file whose tree line
   best covers it, and the choice is stated. Where a reviewer's fix needs a
   structural change, it is not applied; it is listed in Part 9(b).
2. **Interfaces, not shared code.** What is pinned here is what crosses a file
   boundary: a function signature, a column, a request body, a directory name.
   Code is shared on its third repetition, not before.
3. **Every claim about today's behaviour is grounded.** Where this document says
   what the old code does, the file and line are named. Where it says what a
   library does, it was checked in the venv on this machine.

Facts checked on this machine, 2026-09-17, in the three venvs under `external/`:

| venv | python | polars | pyyaml | numpy | torch | transformers | openai_harmony | pydantic |
|---|---|---|---|---|---|---|---|---|
| `external/appworld/venv` | 3.12.13 | 1.44.2 | 6.0.3 | **absent** | absent | absent | absent | 1.10.26 |
| `external/probe-env` | 3.11.15 | 1.44.2 | 6.0.3 | 2.4.6 | 2.11.0+cu128 | 5.14.1 | present | 2.13.4 |
| `external/vllm-env` | 3.12.13 | 1.44.2 | 6.0.3 | 2.3.5 | 2.11.0+cu130 | 5.14.1 | present | 2.13.4 |

This settles grounding F3 (which found Polars installed nowhere): Polars 1.44.2
and PyYAML 6.0.3 are now in all three venvs, and the owner's decision holds.
It also settles one thing the owner's decision did not cover: **NumPy is absent
from the AppWorld venv**, so `venv: any` means *standard library, PyYAML and
Polars only*, and no file marked `any` may import NumPy. Part 9(a) records what
that costs the eval side.

---

## Part 0. The tree, annotated

### 0.1 How to read an entry

Every code file carries five annotations. They are the contract, and they are
copied verbatim onto that file's line in `README.md`, in this order and this
punctuation, so that `run.py selfcheck` can parse them:

```
path/to/file.py — one sentence of what it does.
  imports: a.py, b.py          repo files this file imports (not third-party)
  used by: c.py, d.py          repo files that import this file
  reads: <format or file>      what it reads off disk
  writes: <format or file>     what it writes to disk
  venv: any | appworld | probe | vllm
```

`venv: any` means the file imports under all three venvs using only the standard
library, PyYAML and Polars. A file whose *runtime* needs a heavier venv than its
*import* does is written `any (serves under vllm)` and keeps the heavy import
inside the function that needs it. `used by:` lists importers only; a file that
is started as a program and read by nobody says `used by: none (program)`.
Dynamic imports (`importlib`) are written `used by: <file> (by name)`.

`run.py selfcheck` proves these lines against the code with `ast`, never by
importing: it parses every file's import statements, builds the real graph, and
fails when a README line disagrees. That is the mechanism the owner asked for —
three or four files touched per change is tolerable *because* the line says which
three or four, and the line cannot rot.

### 0.2 The tree

Reproduced entry for entry from the fourth draft's Part 1. Descriptions are the
owner's, shortened where they repeat; annotations are this draft's.

```
new1/
  README.md               for the future reader: this tree, one line per file, how to run, the extension
                          recipes. Edited whenever the tree changes; selfcheck fails on a Python file
                          missing from it, on a line whose imports/used by disagree with the code, and on
                          an axis value with no file behind it
  CLAUDE.md               the rules an agent reads on its own; the only other file at the root that is not code
  run.py                  the one command: run one or several named settings of one workflow file; ls, where,
                          find, free, kill, sync, selfcheck
      imports: experimental_settings/schema.py, jobs/launch.py, jobs/registry.py
      used by: none (program)
      reads: experimental_settings/*.yaml (through schema), run directories' meta.json / done.json /
             heartbeat/*.jsonl, jobs/runs.jsonl
      writes: nothing of its own; it starts stage programs and calls jobs/launch.py and jobs/registry.py
      venv: probe (the interpreter this repo's commands are typed with)
```

```
  constants/              where things are on this cluster. Nothing here enters a key
    path_datasets.yaml      per environment: clone home, venv interpreter, split files, data root
      read by: data/environments/appworld.py (home, split files), jobs/launch.py (venv)
    path_outputs.yaml       the outputs root on NFS, and the debug root under it
      read by: experimental_settings/schema.py (run_dir), jobs/registry.py (ls walks it)
    path_models.yaml        alias -> weights directory
      read by: models/__init__.py, models/agent_models/service.py (the weights path for vllm serve);
               models/probe_models/base.py reaches it through models/__init__.py, never directly
```

```
  experimental_settings/  everything in here changes a result. YAML written by gyb only (hook-refused for
                          agents); schema.py is code
    schema.py               the schema of a setting: every field with its default and a one-line comment, the
                            allowed values of each axis, the stage table; the loader (file -> setting, diff,
                            key); and run_dir
      imports: none (repo); stdlib + PyYAML only
      used by: run.py, jobs/launch.py, agent/loop.py, data/build_dataset.py, train/utils/trainer.py,
               eval/utils/probe_eval.py, eval/score_run.py, eval/method_table.py
      reads: experimental_settings/*.yaml, models/table.yaml, constants/path_outputs.yaml, and the
             VERSION line of every module in the stage table (read as text, never imported)
      writes: settings.yaml frozen into a run directory
      venv: any
    debug.yaml              only sizes: 3 tasks, 1 seed, 64 examples, 20 steps, 100 prediction examples
    baseline.yaml           workflow sample, score; named settings inside
    train_probe.yaml        workflow sample, build, train, eval; named settings inside
    inject.yaml             workflow inject, score; named settings inside
```

```
  data/                   the benchmark environments, and every format that lives on disk between two stages
    __init__.py             the conventions the three formats share: read returns a Polars DataFrame with the
                            format's declared columns and types; the id rule; write; the VERSION rule
      imports: none (repo); polars
      used by: data/task_record.py, data/example.py, data/prediction.py
      reads: -   writes: -   venv: any
    environments/
      __init__.py           class Environment declares the nine methods with one line each and no logic;
                            open_env(name) imports environments/<name>.py inside the function, checks the
                            methods are there, returns the instance
        imports: none (repo); importlib
        used by: data/environments/appworld.py (subclass), agent/loop.py, agent/inject.py,
                 data/build_dataset.py
        reads: -   writes: -   venv: any
      appworld.py           class AppWorld(Environment): the nine methods on the AppWorld package, its task
                            instruction variants, its no-code message, its call regex and Python call syntax;
                            carries VERSION
        imports: data/environments/__init__.py; the appworld package inside open()/step()/speculate()
        used by: data/environments/__init__.py (by name)
        reads: constants/path_datasets.yaml, the split task-id files
        writes: the AppWorld per-task output directory, deleted by close()
        venv: any at import, appworld to run a world
    task_record.py          the record one task run leaves: six row kinds, one file per (task, seed); write,
                            read, is_done, owner, to_messages
      imports: data/__init__.py
      used by: agent/loop.py (write), agent/inject.py (spec/resume rows), data/build_dataset.py (read),
               eval/score_run.py (read), jobs/launch.py (is_done, owner, refire)
      reads/writes: task record (jsonl)
      venv: any
    example.py              the row build writes per cut: the record and cut it came from, the text the probe
                            sees, and all three targets; write, read, and the normal form of a call
      imports: data/__init__.py
      used by: data/build_dataset.py (write), train/utils/trainer.py (read),
               train/methods/{ctool,cgen,cparam}.py (target column, normal form),
               eval/methods/{cgen,cparam}.py (normal form)
      reads/writes: example (parquet)
      venv: any
    prediction.py           the row train writes per example after training: the example id, its target, the
                            score and class logits (ctool) or the generated text (cgen, cparam); write, read
      imports: data/__init__.py
      used by: train/utils/trainer.py (write), eval/utils/probe_eval.py (read)
      reads/writes: prediction (parquet)
      venv: any
    probe_input.py          what the probe is asked and shown: cut positions in the reasoning, and the text
                            assembled for the probe; one rule offline and live; carries VERSION
      imports: none (repo); stdlib re only
      used by: data/build_dataset.py, agent/inject.py
      reads: -   writes: -   venv: any
    build_dataset.py        the program: records -> example rows; the train/val/test split; the report; the
                            gates; carries VERSION
      imports: experimental_settings/schema.py, data/task_record.py, data/example.py, data/probe_input.py,
               data/environments/__init__.py, jobs/registry.py
      used by: none (program)
      reads: task records (jsonl), the environment's split task-id files
      writes: example (parquet), consumed.json, report.md, done.json, heartbeat
      venv: any
```

```
  models/                 the models: the table, the agent-model side, the probe-model side
    __init__.py             the entrance: agent(name) and probe(name) read table.yaml and import the family's
                            or backbone's file inside the function
      imports: none (repo); importlib
      used by: agent/loop.py, agent/generate.py, agent/inject.py, models/agent_models/service.py,
               models/probe_models/base.py, train/utils/trainer.py
      reads: models/table.yaml, constants/path_models.yaml
      writes: -   venv: any
    table.yaml              one row per alias, in two blocks: result (keyed) and serving (never keyed)
      read by: experimental_settings/schema.py (the result block is expanded into the setting before
               keying), models/__init__.py, models/agent_models/service.py (the serving block)
    agent_models/
      __init__.py           empty, so the client half of service.py imports without the family's libraries
      gptoss.py             gpt-oss's harmony format: messages -> tokens, parse a reply, end of turn, the
                            model's own system message, and the control-token wrapping of a prefetch message
        imports: none (repo); openai_harmony inside render()
        used by: models/__init__.py (by name), agent/generate.py, agent/loop.py, agent/inject.py,
                 models/agent_models/service.py
        reads: -   writes: -   venv: any at import, probe/vllm for render()
      service.py            both ends of the served agent model: start or attach to the vLLM server for a
                            table row and check it (main); the loop's client, a raw token stream with a seed
        imports: models/__init__.py, models/agent_models/gptoss.py (server half only, inside main)
        used by: agent/generate.py (client), agent/loop.py (health), jobs/launch.py (starts the server)
        reads: models/table.yaml (serving block), constants/path_models.yaml
        writes: server log in the run directory
        venv: any at import, vllm to serve
    probe_models/
      __init__.py           empty, so the client half of service.py imports without torch
      base.py               the probe class every backbone shares: load, save, score a prefix, generate a
                            call; owns the classification head and the checkpoint layout
        imports: models/__init__.py, models/probe_models/<backbone>.py (by name, inside load())
        used by: train/utils/trainer.py, train/methods/{ctool,cgen,cparam}.py,
                 models/probe_models/service.py (inside serve())
        reads/writes: the checkpoint layout (best/, last/)
        venv: probe
      qwen.py               Qwen's tokenizer quirks, pad token, head attach point, LoRA target modules, dtype
        imports: none (repo); transformers
        used by: models/probe_models/base.py (by name)
        reads: -   writes: -   venv: probe
      service.py            both ends of the probe service: the local HTTP server that loads the probes and
                            answers score, generate, health, with --check (main); the loop's client
        imports: models/probe_models/base.py (server half only, inside serve())
        used by: agent/inject.py (client), jobs/launch.py (starts the server)
        reads: the two checkpoint directories named on its command line
        writes: server log in the run directory
        venv: any at import, probe to serve
```

```
  agent/                  the loop that runs the agent model on tasks
    loop.py                 run each task and seed: open, step, parse, act, until done; claim tasks across
                            pieces; write the record; pick the generation step by the setting; carries VERSION
      imports: experimental_settings/schema.py, data/environments/__init__.py, data/task_record.py,
               models/__init__.py, models/agent_models/service.py (client), agent/generate.py,
               agent/inject.py, jobs/registry.py
      used by: none (program)
      reads: settings.yaml of its run directory, the environment's split task-id files
      writes: task records (jsonl), heartbeat, done.json
      venv: the environment's (appworld today)
    generate.py             the plain generation step: stream tokens to end of turn; exposes the token stream
                            so inject.py iterates it instead of copying it; carries VERSION
      imports: models/agent_models/service.py (client), models/__init__.py (the family module)
      used by: agent/loop.py, agent/inject.py
      reads: -   writes: -   venv: the environment's
    inject.py               the generation step with the probe: score at each cut, on fire get the call, run
                            it early, write the result in, resume from the spliced prefix, roll back on
                            mismatch; carries VERSION
      imports: agent/generate.py, agent/inject_format.py, data/probe_input.py, data/task_record.py,
               models/probe_models/service.py (client), models/__init__.py (the family module),
               data/environments/__init__.py (type only; the object is passed in)
      used by: agent/loop.py
      reads: -   writes: spec and resume rows through data/task_record.py
      venv: the environment's
    inject_format.py        the table of the ways an early result is written into the stream; carries VERSION
      imports: none
      used by: agent/inject.py; its keys are cross-checked against schema.py's axis by run.py selfcheck
      reads: -   writes: -   venv: any
```

```
  train/                  train a probe
    utils/
      trainer.py            the training loop every method shares: settings -> arguments, seed, backbone,
                            tuning, checkpoints, metrics, heartbeat, resume, the alignment gate; and its last
                            step, the prediction run over val and test; carries VERSION
        imports: experimental_settings/schema.py, models/__init__.py, models/probe_models/base.py,
                 data/example.py, data/prediction.py, jobs/registry.py
        used by: train/methods/{ctool,cgen,cparam}.py
        reads: example (parquet), the checkpoint layout
        writes: the checkpoint layout, prediction (parquet), metrics.jsonl, heartbeat, done.json
        venv: probe
    methods/                one file per probe method, each complete on its own
      ctool.py              the classification probe: its batches, its head use, its loss, its validation
                            accuracy; carries VERSION
        imports: train/utils/trainer.py, models/probe_models/base.py, data/example.py
        used by: none (program)
        reads: -   writes: - (everything goes through trainer.py)
        venv: probe
      cgen.py               the call-generating probe: its packing, its instance strings and target, its loss
                            positions, its exact-match validation; carries VERSION
        imports / used by / venv: as ctool.py
      cparam.py             the argument-generating probe: its own packing and strings, the arguments as the
                            target; carries VERSION
        imports / used by / venv: as ctool.py
```

```
  eval/                   reads what is on disk and computes numbers; no GPU, no torch, no NumPy
    utils/
      probe_eval.py         shared by the three methods: read a train run's prediction rows, the bootstrap
                            interval, the probe report (write and read); carries VERSION
        imports: experimental_settings/schema.py, data/prediction.py, jobs/registry.py
        used by: eval/methods/{ctool,cgen,cparam}.py, jobs/launch.py (read_report only)
        reads: prediction (parquet), probe report (json)
        writes: probe report (json), report.md, done.json
        venv: any
    methods/
      ctool.py              fit the temperature and theta on the val rows at the risk targets, freeze, report
                            on the test rows; carries VERSION
        imports: eval/utils/probe_eval.py
        used by: none (program)
        reads: prediction (parquet)   writes: probe report (json)
        venv: any
      cgen.py               exact match of the generated call at the frozen theta; carries VERSION
        imports: eval/utils/probe_eval.py, data/example.py (the normal form of a call)
        used by: none (program)
        reads: prediction (parquet), the referenced ctool run's probe report
        writes: probe report (json, the generating-probe shape)
        venv: any
      cparam.py             exact match of the generated arguments at the frozen theta; carries VERSION
        imports / used by / reads / writes / venv: as cgen.py
    score_run.py            a sample or inject run from its records: task success, speculation outcomes,
                            tokens and time; by seed; against a baseline; carries VERSION
      imports: experimental_settings/schema.py, data/task_record.py, jobs/registry.py
      used by: none (program)
      reads: task records (jsonl) of this run and of its baseline
      writes: run report (json), report.md, done.json
      venv: any
    method_table.py         the backbone x method table from the registry; groups sweep children, reports
                            mean and spread
      imports: experimental_settings/schema.py, jobs/registry.py
      used by: none (program)
      reads: jobs/runs.jsonl, the probe reports it points at
      writes: a markdown table on stdout or into a named file
      venv: any
```

```
  jobs/                   a job is one stage run on cards: the code that starts it and records it, and the
                          record itself
    launch.py               the dirty-tree gate; pick free cards; one tmux session per piece; the start row;
                            the alive check; refire
      imports: experimental_settings/schema.py, jobs/registry.py, eval/utils/probe_eval.py (read_report,
               to hand the probe service its theta and temperature)
      used by: run.py
      reads: constants/path_datasets.yaml (the venv per environment), constants/path_outputs.yaml,
             settings.yaml of the run directory, nvidia-smi, tmux
      writes: the start row in jobs/runs.jsonl, meta.json, dirty.patch, the piece commands
      venv: probe (it runs on the login machine)
    registry.py             the registry: runs.jsonl rows under a lock, meta.json, the heartbeat, the
                            verdicts, ls/where/find/kill/free, RESULTS.md
      imports: none (repo); standard library only
      used by: run.py, jobs/launch.py, agent/loop.py, data/build_dataset.py, train/utils/trainer.py,
               eval/utils/probe_eval.py, eval/score_run.py, eval/method_table.py
      reads: constants/path_outputs.yaml, jobs/runs.jsonl, run directories' meta.json and heartbeat
      writes: jobs/runs.jsonl, RESULTS.md, meta.json, heartbeat/<piece>.jsonl, done.json
      venv: any
    runs.jsonl              one row per stage run, appended at start and at finish; never edited by hand; in git
    runs.jsonl.lock         the lock every append takes; ignored by git
    RESULTS.md              rendered from runs.jsonl by registry.py; never edited by hand
  tests/                  empty for now (gyb, 2026-09-17)
  .claude/skills/repo-review/SKILL.md
  .claude/skills/gpu-run/references/gpu_state.md
  .claude/hooks/settings_readonly.sh
  .scratch/review/issues/
  .claude/
  notes/
  notebooks/   figures/   external/
```

### 0.3 The count

Python files, by directory: root 1 (`run.py`); `experimental_settings` 1
(`schema.py`); `data` 8 (`__init__.py`, `environments/__init__.py`,
`environments/appworld.py`, `task_record.py`, `example.py`, `prediction.py`,
`probe_input.py`, `build_dataset.py`); `models` 8 (`__init__.py`,
`agent_models/__init__.py`, `agent_models/gptoss.py`, `agent_models/service.py`,
`probe_models/__init__.py`, `probe_models/base.py`, `probe_models/qwen.py`,
`probe_models/service.py`); `agent` 4; `train` 4; `eval` 6; `jobs` 2.
**1 + 1 + 8 + 8 + 4 + 4 + 6 + 2 = 34**, which equals the fourth draft's count.

`train/`, `train/utils/`, `train/methods/`, `eval/`, `eval/utils/`,
`eval/methods/`, `agent/`, `jobs/`, `constants/` and `experimental_settings/`
have no `__init__.py` and get none: they are namespace packages (PEP 420), which
Python 3.11 and 3.12 both resolve when the repo root is on `sys.path`. Every
program is started as `python -m <dotted module> --run-dir <dir>` with the repo
root as the working directory. The two empty `__init__.py` files under `models/`
are the owner's and stay, with the reason the tree gives them.

Four places, and only four, gain a *file* by extension, and each is named by the
tree's own line: `data/environments/<env>.py`, `models/agent_models/<family>.py`,
`models/probe_models/<backbone>.py`, and the pair
`train/methods/<m>.py` + `eval/methods/<m>.py`. Everywhere else, an extension is
an edited line.

### 0.4 What each extension touches

This is the table the contracts exist to make true. "new" marks a file the
extension creates in one of the four places above; everything else is an edit.
`README.md` is on every row (one line per file, plus the extension recipe) and
the setting YAML is on every row that needs one (written by gyb, not by an
agent). Neither is repeated in the counts.

| Scenario | Files touched | Why it is not more |
|---|---|---|
| A new benchmark environment | `data/environments/<env>.py` (new); `experimental_settings/schema.py` (one axis value on `data.env`, one on `data.instructions`); `constants/path_datasets.yaml` (home, venv, split files) | The loop calls nine methods and nothing else; the call syntax, the instruction text and the no-code message are the environment's; the venv that runs the loop is a column in `path_datasets.yaml` (dependencies P7). `data/build_dataset.py` parses calls through the environment object, so it is untouched. |
| A fourth probe method | `train/methods/<m>.py` (new); `eval/methods/<m>.py` (new); `experimental_settings/schema.py` (one axis value on `probe.method`, one line in the stage table's program map) | The example row is method-independent (Part 1.2): build writes one row per cut carrying every target, so `data/build_dataset.py` and `data/example.py` are untouched. The prediction row is method-independent (Part 1.3). `trainer.py` never branches on method: the method file is the program and passes its hooks down (Part 2.3). The head lives in `probe_models/base.py` (dependencies P10). Train's validation and eval's metric each call `data/example.py`'s normal form, so no train file imports an eval file. |
| A new training hyperparameter | `experimental_settings/schema.py` (field, default, comment); the one module that reads it (`train/utils/trainer.py` or one method file) | The key is over the *diff from the defaults* (Part 3.2), so a field whose default reproduces the old behaviour changes no key and reruns nothing. |
| A new field on the task record | `data/task_record.py` (column plus its default); the one writer (`agent/loop.py`, `agent/inject.py` or the environment file) | A column added with a declared default leaves `VERSION` alone, so old record files still read and no key moves (dependencies P9). `VERSION` bumps only when an existing column changes meaning. |
| A sixth injection format that reuses a placement | `agent/inject_format.py` (one entry) | The axis reads its values from a literal list in `schema.py` that `selfcheck` proves equal to `FORMATS.keys()`, so `schema.py` does not import `agent/`. A *new placement* costs one more file, `models/agent_models/<family>.py`, which owns the control-token wrapping (synthesis item 6). |
| A new probe backbone | `models/probe_models/<backbone>.py` (new); `models/table.yaml` (one row); `constants/path_models.yaml` (one row) | Model aliases are validated against `table.yaml`, not against a schema axis, so there is one source of legal model names (dependencies, backbone row). `base.py` holds everything the backbones share. |
| A new agent-model family | `models/agent_models/<family>.py` (new); `models/table.yaml` (one row); `constants/path_models.yaml` (one row) | Rendering and tokenising happen on the vLLM server through `/tokenize` and `/detokenize` (Part 7.1), so `models/probe_models/service.py` never loads the agent's tokenizer; the prefetch wrapping lives in the family file, so `agent/inject_format.py` holds only placement, body and system text (dependencies P4, grounding F4). |

Two scenarios the reviews raised that are not extensions but are worth the same
treatment:

| Scenario | Files touched | Cost |
|---|---|---|
| Change the cut rule | `data/probe_input.py` (+ `VERSION`) | Inherent full rerun downstream: build re-keys, train follows through the build key, eval through the train key, inject through `probe_input`'s own version. The cost is on the file's README line so nobody is surprised. |
| Rename an axis value | not allowed | An axis value is added and retired, never renamed (dependencies P6). `schema.py` keeps a `RETIRED` set: a retired value still loads (so an old `settings.yaml` still runs) but a new setting that uses it fails. |

---

## Part 1. On-disk formats

Four formats cross a stage boundary, plus the run directory's own files. Each
format is defined in exactly one file, which owns the column list, the types, the
id rule, the reader and the writer. No other file may construct a row of that
format by hand.

Common conventions, all in `data/__init__.py`:

- **Reading returns a Polars DataFrame** with the format's declared schema. The
  schema is passed to Polars explicitly (`pl.read_ndjson(path, schema=SCHEMA)`,
  `pl.read_parquet(path, columns=...)`), so a column missing from an older file
  arrives as null rather than as a missing key, and a column whose type changed
  fails loudly.
- **Records are jsonl, one file per task run**, written row by row with a flush
  after each row (a killed process keeps what it wrote, as
  `legacy/pipeline/inject/live_appworld.py:291-299` does today). **Examples and
  predictions are parquet**, written once in bulk.
- **Every format file declares `VERSION: int` and `DEFAULTS: dict[str, Any]`.**
  `VERSION` bumps only when an existing column changes meaning for the same
  settings; a *new* column is added with an entry in `DEFAULTS` and no bump, so
  old files stay readable and no key moves (dependencies P9). The reader fills a
  missing column from `DEFAULTS`.
- **Id rule**, one chain, so every join downstream is a string equality:

  | level | id | built from |
  |---|---|---|
  | record | `<task_id>__s<seed>` | the task id and the trajectory's seed |
  | event (one step) | `<record_id>\|s<step>` | the record id and the step index |
  | example (one cut) | `<event_id>\|c<cut_index>` | the event id and the cut index |
  | prediction | equal to the example id | — |

  `|` is the separator because no AppWorld task id contains it. Ids are built by
  one function per level in `data/__init__.py` (`record_id`, `event_id`,
  `example_id`), never by string formatting at a call site.

### 1.1 Task record — `data/task_record.py`

**Layout.** One file per task run:
`<run_dir>/records/<task_id>__s<seed>.jsonl`. One file is one task and one seed,
never appended by two processes (lifecycle A5, grounding F6; today's code already
writes one file per trajectory, `legacy/envs/collect/run_appworld.py:71-76`). The
first line is the `meta` row and carries `owner_session`; the last line of a
finished file is the `final` row.

**Claiming.** A piece claims a task by creating the file with `O_EXCL` and
writing the `meta` row into it. A piece that loses the race moves on. This
replaces today's `.claims/` directory of `mkdir` tickets
(`legacy/pipeline/inject/live_appworld.py:590-603`): the file is the ticket, so
there is no second thing to clean up.

**Done, partial, refire.** `is_done(path)` is "the last line parses and its
`type` is `final`". A file that is not done is **deleted and the task redone** —
a trajectory cannot be resumed mid-task because the world state is gone with the
process, and deleting also removes any half-written last line, which is what
would otherwise break a strict Polars read. `jobs/launch.py` deletes the
unfinished files whose `owner_session` is no longer a live tmux session, then
refires.

**Row kinds.** Six, exactly today's six
(`legacy/pipeline/inject/live_appworld.py:34-42`). A sample run writes
`meta`, `gen`, `env`, `final`; an inject run writes all six. One format serves
both, which is what makes `eval/score_run.py` able to pair an inject run with its
baseline.

| kind | column | type | meaning |
|---|---|---|---|
| all | `type` | str | `meta`, `gen`, `spec`, `resume`, `env`, `final` |
| all | `step` | i32 | step index; null on `meta` |
| all | `ts` | f64 | the writing machine's clock, only ever diffed against another `ts` in the same file |
| meta | `version` | i32 | this format's `VERSION` at write time |
| meta | `record_id` | str | `<task_id>__s<seed>` |
| meta | `env` | str | environment name (`data.env`) |
| meta | `task_id` | str | the environment's task id |
| meta | `seed` | i64 | the trajectory seed, sent in the request body and used as the world seed |
| meta | `split` | str | the split the task came from |
| meta | `arm` | str | `sample`, `probe`, `no_probe`, `probe_nofill` (CONTEXT: with probe / no probe) |
| meta | `instructions` | str | the instruction-variant name (`data.instructions`) |
| meta | `agent_model` | str | the alias from `models/table.yaml` |
| meta | `generation` | struct | the resolved `generation` section, echoed back |
| meta | `inject` | struct | the resolved `inject` section, or null on a sample run |
| meta | `env_seed` | i64 | the environment's own seed (AppWorld's `random_seed`, 100 today) |
| meta | `commit` | str | the git commit the piece ran at |
| meta | `run_key` | str | the stage key of the run directory this file sits in |
| meta | `owner_session` | str | the tmux session that claimed this file |
| gen | `reasoning` | str | the thinking text of this step |
| gen | `content` | str | the answer text of this step |
| gen | `usage` | struct{in:i64,out:i64} | prompt and completion tokens |
| gen | `wall_s` | f64 | wall time of the step's generation |
| gen | `finish_reason` | str | the server's finish reason |
| gen | `prefix_tok` | i32 | prompt length in tokens |
| gen | `prefix_sha` | str | sha1 of the prompt token ids (the whole prefix is not stored) |
| gen | `gen_ids` | list[i32] | the generated token ids; null unless `store_token_ids` |
| gen | `n_inject` | i32 | injections in this step (0 on a sample run) |
| gen | `discard` | struct{chars:i64,tokens:i64,events:i32} | text and tokens thrown away by interruptions |
| spec | `cut` | i32 | character offset in the thinking where the probe fired |
| spec | `n_checked` | i32 | how many cuts were scored before this one |
| spec | `conf` | f64 | the probe's confidence at the cut |
| spec | `pred_label` | str | the tool the score probe predicted |
| spec | `gen_call` | str | the call the generation probe wrote |
| spec | `exec_code` | str | the call as executed after requoting |
| spec | `arg_modes` | list[str] | how each argument was requoted |
| spec | `exec_out` | str | the speculated call's output, clipped to `TRUNC` |
| spec | `exec_ok` | bool | the speculation ran without an error |
| spec | `error_kind` | str | the error class, or null |
| spec | `note` | str | the exact text spliced into the stream |
| spec | `head_tok` | i32 | token length of the kept head |
| spec | `head_chars` | i32 | character length of the kept head |
| spec | `head_ends_ws` | bool | whether the head ends in whitespace (the seam rule) |
| spec | `note_tok` | i32 | token length of the spliced text |
| spec | `discarded_chars` | i32 | characters thrown away at this interruption |
| spec | `overflow_ids` | list[i32] | the ids thrown away, for the resume comparison |
| spec | `spec_s` | f64 | wall time of snapshot + execute + restore |
| resume | `overflow_tok` | i32 | how many ids were discarded last time |
| resume | `new_tok` | i32 | how many ids the resend produced |
| resume | `match_len` | i32 | how many leading ids matched |
| resume | `identical` | bool | the resend reproduced the discarded continuation exactly |
| resume | `stop_reason` | str | the server's stop reason for the resent request |
| env | `action` | str | the code the model ran, or null when it wrote no code block |
| env | `result` | str | the environment's output, clipped to `TRUNC` |
| env | `error_kind` | str | the error class, or null |
| final | `steps` | i32 | steps taken |
| final | `completed` | bool | the agent called the environment's completion API |
| final | `abort` | str | why the run stopped early, or null |
| final | `judge` | struct | the environment's own evaluation dict (a struct, never a string: scoring reads it) |
| final | `tokens_in` / `tokens_out` | i64 | totals for the run |
| final | `wall_s` | f64 | wall time of the whole task |

`final.judge` is a struct because today's sample side stores the evaluation as a
string (`legacy/envs/collect/run_appworld.py:231`) and the inject side as a dict
(`legacy/pipeline/inject/live_appworld.py:834`), and the scoring side has to read
it. One shape, the dict.

**Who writes.** `agent/loop.py` writes `meta`, `gen`, `env`, `final`;
`agent/inject.py` writes `spec` and `resume` through the same writer object.
**Who reads.** `data/build_dataset.py` (events and cuts), `eval/score_run.py`
(outcomes, tokens, speculation), `jobs/launch.py` (`is_done`, `owner`).
**Offered functions.** `open_record(dir, task_id, seed, meta) -> Writer | None`
(None when another piece holds it), `Writer.row(kind, **fields)`,
`Writer.close()`, `is_done(path)`, `owner(path)`, `read(path) -> DataFrame`,
`read_dir(dir) -> DataFrame`, `to_messages(df, upto_step)`.

`to_messages` rebuilds the conversation exactly as the model saw it, and both the
loop (live) and the builder (offline) use it, so there is one convention for
what the agent's history looks like.

### 1.2 Example — `data/example.py`

**Layout.** `<run_dir>/examples.parquet`, one file, written once by
`data/build_dataset.py`. The split is a column, not three files, so a change to
the split rule rewrites one file and eval can read "the val rows" by filter.

**One row per cut, not per method.** This is the single decision that makes a
fourth probe method cheap. The row carries every target shape a method could
want, and the method picks its column at train time.

| column | type | meaning | key-relevant |
|---|---|---|---|
| `example_id` | str | `<record_id>\|s<step>\|c<cut>` | id |
| `record_id` | str | the record file this came from | |
| `event_id` | str | `<record_id>\|s<step>` | the unit that fires at most once |
| `task_id` | str | the environment's task id | the split is by task |
| `seed` | i64 | the trajectory seed | |
| `step` | i32 | step index in the trajectory | |
| `cut_index` | i32 | which cut of this step's thinking | |
| `n_cuts` | i32 | how many cuts this step has | |
| `depth` | f32 | `cut / len(thinking)`, the earliness measure | |
| `text` | str | what the probe is shown, from `data/probe_input.py` | |
| `task` | str | the task instruction | |
| `tool` | str | the tool actually called at this step: ctool's target | |
| `call` | str | the normalised whole call `tool(k=v, ...)`: cgen's target | |
| `args` | list[struct{key:str,value:str}] | the named arguments: cparam's target | |
| `weight` | f32 | 1.0 under `uniform`, `1/n_cuts` under `per_event` | |
| `split` | str | `train`, `val`, `test` | |
| `env` | str | environment name | |
| `agent_model` | str | the alias that produced the trajectory | |
| `version` | i32 | this format's `VERSION` at write time | |

`call` is built by the environment's `build_call(tool, args)` and is the same
string today's `make_call` produces (`legacy/pipeline/annotate/build.py:195-198`).
cparam's target is derived from `call` and `tool` the way
`legacy/pipeline/train/train_causal_param.py:105-113` derives it (strip
`tool + "("`, keep the closing parenthesis), and that derivation lives in
`train/methods/cparam.py` because it is that method's business.

**The normal form.** `example.py` also owns `norm_call(s) -> str` and
`norm_args(s) -> list[tuple[str,str]]`: the canonical form of a call string and
of an argument list (whitespace normalised, quotes stripped, arguments sorted by
key), which is what "exact match" means. Two places need it —
`train/methods/<m>.py` for its validation metric and `eval/methods/<m>.py` for
its reported metric — and both are allowed to import `data/`, so the upward edge
`train -> eval` that the dependency review found (its cycle C2) never exists.
The rule stated plainly: **a column's canonical form is defined where the column
is defined.**

**Who writes.** `data/build_dataset.py`. **Who reads.** `train/utils/trainer.py`
(all rows of the requested split), `train/methods/*.py` (through the frame the
trainer hands them).

### 1.3 Prediction — `data/prediction.py`

**Layout.** `<train run_dir>/predictions.parquet`, written by
`train/utils/trainer.py` as the last step of training, with the probe still on
the card (principle 7). One row per example of every split named by
`train.predict.splits` (default `[val, test]`), **uniform across methods**: the
generating probes generate at every cut row, so eval can apply any theta later
without a GPU. That is the owner's decision; the construction plan measures the
cost in the smoke and the fallback is written down in Part 9(a).

| column | type | meaning |
|---|---|---|
| `example_id` | str | joins to the example row |
| `split` | str | copied from the example |
| `method` | str | `ctool`, `cgen`, `cparam` |
| `target` | str | the example's target for this method, copied so eval joins nothing |
| `score` | f32 | ctool: max softmax probability at temperature 1; null for generators |
| `label_pred` | str | ctool: the argmax class; null for generators |
| `logits` | list[f32] | ctool: the class logits, in `label_map.json` order; null for generators |
| `text_pred` | str | cgen, cparam: the greedily generated string, cut at the first newline and stripped |
| `gen_tokens` | i32 | generators: how many tokens were generated |
| `version` | i32 | this format's `VERSION` at write time |

`logits` is stored because the temperature fit needs the whole class vector and
eval has no GPU; at about 100 tools and float32 that is 400 bytes a row, which
parquet compresses well. `label_map.json` (class name -> index) is written once
into the train run directory beside the checkpoint, by
`models/probe_models/base.py`, which owns the head.

**Who writes.** `train/utils/trainer.py`, through the method file's `predict`
hook. **Who reads.** `eval/utils/probe_eval.py`.

### 1.4 Probe report — defined in `eval/utils/probe_eval.py`

The owner's instruction places this format on `eval/utils/probe_eval.py`, whose
tree line says "write the report". It is the fourth on-disk format and the one
the reviews found had no owner (dependencies P3, grounding F1, synthesis item 5).

**Layout.** `<eval run_dir>/probe_report.json`, one file. Two shapes, tagged by
`method`: the ctool shape carries the fitted temperature and theta per risk
target; the generating shape carries exact-match numbers at a named theta.

| field | type | meaning |
|---|---|---|
| `version` | int | the format's `VERSION` |
| `method` | str | `ctool`, `cgen`, `cparam` |
| `stage_key` | str | this eval run's key |
| `train_key` | str | the train run whose predictions were read |
| `theta_from` | str | for cgen and cparam: the ctool eval key whose theta was used; null for ctool |
| `commit` | str | the commit the report was computed at |
| `label_map` | dict[str,int] | class name to index, copied from the train run |
| `temperature` | float | ctool: the fitted softmax temperature |
| `risk_targets` | list[float] | the risk targets swept, from `eval.risk` |
| `chosen` | dict[str, float \| null] | risk target (as a string) to the theta chosen on val, null when no theta meets the constraint |
| `frozen` | dict[str, struct] | risk target to the test numbers at that theta: `n`, `coverage`, `trig_acc`, `earliness`, `wrong_spec`, `ci` |
| `fire_rows` | dict[str, int] | risk target to how many rows fired on test |
| `exact` | struct | cgen, cparam: `tool_ok`, `params_all_ok`, `full_call_ok`, `n`, `ci` at the theta used |
| `theta_used` | float | cgen, cparam: the theta taken from the referenced report |
| `n_events_test` | int | events in the test split |

The names `coverage`, `trig_acc`, `earliness`, `wrong_spec` and the three
exact-match tiers are today's
(`legacy/pipeline/eval/eval_tool.py:251-258` and
`legacy/pipeline/eval/eval_causal_call.py:1-40`), so old numbers and new ones are
comparable without a translation table.

**Who writes.** `eval/methods/ctool.py` (the ctool shape),
`eval/methods/{cgen,cparam}.py` (the generating shape), both through
`probe_eval.write_report`. **Who reads.** `eval/methods/{cgen,cparam}.py` (the
referenced ctool report, through `probe_eval.read_report`), `jobs/launch.py`
(theta and temperature, to hand to the probe service on its command line),
`eval/method_table.py` (through the registry row, which carries the summary).

**The probe service does not read this file.** `jobs/launch.py` resolves
`inject.probe_score` to an eval(ctool) run, reads the report, freezes the numbers
into the inject run's `settings.yaml`, and passes `--theta` and `--temperature`
on the service's command line. That removes the only edge that would have made
`models/` depend on an `eval/` output (the dependency review's cycle C3) and
makes a live run's theta visible in the run directory instead of hidden in
another run's report.

### 1.5 The run directory's own files

Every stage run writes into one directory, named in Part 3. The files are the
same for every stage, which is what lets `run.py ls` treat them uniformly.

| file | written by | content |
|---|---|---|
| `settings.yaml` | `jobs/launch.py` (GPU stages) or `run.py` (CPU stages), before the first piece starts | the fully resolved setting: defaults merged, debug applied, overrides applied, references resolved to keys, model-table result columns expanded. This is the truth the stage runs from; a piece is never told a setting name (lifecycle A2) |
| `settings_diff.yaml` | the same writer | only the fields that differ from the schema defaults: the human summary, and exactly what the key is computed over |
| `meta.json` | `jobs/registry.py` | see Part 8.2 |
| `heartbeat/<piece>.jsonl` | `jobs/registry.py`, called by the stage | one line per beat, one file per piece, one writer per file |
| `log/<piece>.txt` | the piece's tmux session | stdout and stderr |
| `dirty.patch` | `jobs/launch.py` | `git diff HEAD` when `--allow-dirty` was used; absent otherwise |
| `done.json` | whoever observes completeness (Part 2.2) | `{stage, key, commit, finished_at, n_outputs, versions}` |
| `consumed.json` | the stage, when it consumes another stage's files | `[{path, sha1, n_rows}]`; `run.py ls` flags a directory whose consumed hashes no longer match the upstream |
| the stage's outputs | the stage | records, examples, predictions, checkpoints, reports |

There is no `failed.json`. Failure is not a file: it is the verdict `ls` computes
from a run directory with no `done.json`, no live session and a stale heartbeat
(Part 8.4). One less thing to write, and no way for a stale marker to lie.

---

## Part 2. The stage table

Six stages, the owner's six. No stage is added. The retired offline replay line
would have been a seventh and is listed as a proposal in Part 9(b).

The table lives in `experimental_settings/schema.py` as a literal dictionary,
`STAGES`, with no imports: every entry is strings and tuples. `run.py` walks it,
`jobs/launch.py` reads the piece rule and the venv from it, and `run_dir` reads
the "sections read" and "versions" rows to compute a key. Because it is literal
data, editing a stage's inputs is an edit to one dictionary entry, and nothing
imports upward to make it work (dependencies P1).

### 2.1 The table

| stage | sections read (keyed part) | upstream | program (module, entry) | venv | cards | pieces | versions folded into its key |
|---|---|---|---|---|---|---|---|
| `sample` | `data`, `models.agent`, `generation`, `sample.{split,max_steps,store_token_ids}` | none | `agent.loop`, `main(run_dir, piece)` | the environment's (from `constants/path_datasets.yaml`) | yes (the agent server) | `sample.replicas` agent-service pieces + `sample.pieces` loop pieces | `agent/loop.py`, `agent/generate.py`, `data/task_record.py`, `data/environments/<env>.py`, `models/agent_models/<family>.py` |
| `build` | `data`, `build`, `sample.{split,seeds,tasks}` | `sample` (its key) | `data.build_dataset`, `main(run_dir)` | any | no | 1, in place | `data/build_dataset.py`, `data/probe_input.py`, `data/example.py`, `data/task_record.py`, `data/environments/<env>.py` |
| `train` | `models.probe`, `probe`, `train` | `build` (its key) | `train.methods.<probe.method>`, `main(run_dir)` | probe | yes | 1 | `train/utils/trainer.py`, `train/methods/<m>.py`, `data/example.py`, `data/prediction.py`, `models/probe_models/base.py`, `models/probe_models/<backbone>.py` |
| `eval` | `probe.method`, `eval` | `train` (its key); for `cgen` and `cparam` also the run named by `eval.theta_from`, resolved to its **eval(ctool)** key | `eval.methods.<probe.method>`, `main(run_dir)` | any | no | 1, in place | `eval/methods/<m>.py`, `eval/utils/probe_eval.py`, `data/prediction.py`, and `data/example.py` for `cgen` and `cparam` only (they use its normal form; `ctool` compares class names) |
| `inject` | `data`, `models`, `generation`, `probe`, `inject.{split,max_steps,theta,format,max_inject_per_step,chunk_tokens,tail_tokens,no_probe,nofill,fire_nth_cut,store_token_ids}` | the run named by `inject.probe_score`, resolved to its **eval(ctool)** key; the run named by `inject.probe_gen`, resolved to its **train(cgen)** key | `agent.loop`, `main(run_dir, piece)` | the environment's | yes (agent server + probe service) | `inject.replicas` agent-service pieces + 1 probe-service piece + `inject.pieces` loop pieces | `agent/loop.py`, `agent/generate.py`, `agent/inject.py`, `agent/inject_format.py`, `data/probe_input.py`, `data/task_record.py`, `data/environments/<env>.py`, `models/agent_models/<family>.py` |
| `score` | `score`, and the `sample` or `inject` section's `{split, seeds, tasks}` | the run being scored (its key) and, when `score.baseline` is set, the baseline run's key | `eval.score_run`, `main(run_dir)` | any | no | 1, in place | `eval/score_run.py`, `data/task_record.py` |

Notes that the table's shape hides:

- **`build`'s key does not contain `probe.method`.** One build serves all three
  methods, because the example row carries all three targets (Part 1.2). A
  fourth method therefore reuses an existing dataset rather than rebuilding it.
- **`eval`'s key does not contain anything `train` reads,** and `train`'s key
  does not contain anything under `eval.`. The prediction run's sizing lives in
  `train.predict` (lifecycle B2), so editing `eval.risk` never reruns a training.
- **`inject` names two probe runs and resolves them to two different stages** of
  those settings: the scoring probe is resolved to its *eval* run (that is where
  theta and the temperature are) and the generating probe to its *train* run
  (the loop only needs the weights). Both resolved keys enter the inject key, so
  a refit of theta gives the live run a new directory.
- **`sample`'s key does not contain `seeds`, `tasks`, `pieces` or `replicas`.**
  Those choose how much of a pool to fill, not what the pool is, so asking for
  more seeds adds files to the same directory (the third draft's rule, kept).
  `split` and `max_steps` are in the key: they change what a trajectory is.
  `build` puts `sample.{split,seeds,tasks}` in *its* key, so a dataset built from
  three seeds and one built from four are different directories.

### 2.2 Per stage: what it writes, what "done" means, how it continues

**`sample` and `inject`** (the two stages that are collections of task files).

- Writes: `records/<task_id>__s<seed>.jsonl` per task run; `heartbeat/<piece>.jsonl`;
  `done.json` at the end.
- Piece rule: the requested (task, seed) pairs are the full product of the
  split's task list (restricted by `sample.tasks` when set) with `sample.seeds`.
  There is no static sharding. Each piece walks the list starting at its own
  offset (`ids[piece:] + ids[:piece]`, today's pool mode,
  `legacy/pipeline/inject/live_appworld.py:718-723`) and claims by `O_EXCL`
  create. A slow task therefore blocks nobody.
- Done: every requested pair has a done file. The first process to observe that
  writes `done.json` with `O_EXCL`; `run.py` writes it too on its next walk, and
  the first writer wins.
- Continue: rerunning the stage skips done files, deletes unfinished files whose
  owner session is dead, and claims what is left. Nothing else is needed; this is
  the same rule as a first run.
- Dead piece: no heartbeat for longer than the stall line and no live tmux
  session (Part 8.4). `jobs/launch.py --refire` releases that piece's unfinished
  files and starts one replacement piece. One automatic refire per piece, as
  CONTEXT's refire entry says; a second death stops and waits.

**`build`.**

- Writes: `examples.parquet`, `consumed.json`, `report.md`, `done.json`.
- Refuses to start unless every requested (task, seed) has a done record
  (lifecycle B9). A partial sample silently yielding a smaller dataset is the
  failure this refusal exists to prevent.
- Gates (from `legacy/pipeline/annotate/check_callstr.py`): a row whose `call`
  does not re-parse to its `tool` and `args`; a split that puts one task id in
  two splits; a tool that appears in val or test and never in train; an empty
  `text`; a `depth` outside [0, 1]. A gate failure stops the build and names the
  rows. The gates live in `build_dataset.py` with the example construction; a
  separate `data/check_dataset.py` would be a new file, so it is a Part 9(b)
  proposal.
- Continue: build is minutes of CPU, so a partial directory is started over. The
  stage writes into a temporary file beside the target and renames, so a killed
  build never leaves a half parquet.

**`train`.**

- Writes: `best/`, `last/`, `label_map.json`, `metrics.jsonl`,
  `heartbeat/train.jsonl`, `predictions.parquet`, `train_done.json`,
  `done.json`.
- Piece rule: exactly one piece on one card. Two cards are two sweep children,
  not two pieces; there is no multi-card training in this repo today and none is
  contracted.
- Continue (lifecycle A6, which found today's rule undecidable): three markers,
  three answers.

  | state on disk | action |
  |---|---|
  | `done.json` present | reuse; run nothing |
  | `train_done.json` present, `predictions.parquet` absent | load `best/`, run the prediction step only, write predictions and `done.json` |
  | `last/` present, its `commit` equals the current commit | resume from `last/step`, continue training |
  | `last/` present, its `commit` differs | refuse unless `--retry`; with `--retry`, start fresh |
  | none of the above | start fresh |

  `last/` is written every `train.checkpoint_hours` and carries
  `{step, epoch, commit, rng_state}`. `best/` is written on validation
  improvement and carries the weights, the tokenizer, `head.pt` for ctool and
  `meta.json` (backbone alias, tuning, `call_sep`, `param_only`), which is
  today's layout (`legacy/pipeline/train/train_causal_tool.py:518-536`) with the
  addition of `last/`.

**`eval` and `score`.**

- Write: `probe_report.json` or `run_report.json`, `report.md`, `done.json`.
- These are seconds of CPU, so they **always recompute**: a rerun overwrites its
  own directory, and the report carries the commit (lifecycle A7). They are still
  keyed, and their key folds their own file's `VERSION` plus
  `eval/utils/probe_eval.py`'s, so a change to *how* a number is computed lands
  in a new directory and the old number stays retrievable.
- `eval(cgen)` and `eval(cparam)` refuse to start when the referenced ctool eval
  is not done, and refuse when its `label_map` differs from the one in their own
  train run.
- `score` refuses a baseline whose `data`, `models.agent` and `generation`
  sections differ from the run being scored — CONTEXT's same-setup rule, enforced
  by a program instead of by memory.

### 2.3 How a stage program is called, and how the method hook works

Every stage program has the same shape:

```
python -m <module> --run-dir <dir> [--piece <i>/<n>]
```

with the repo root as the working directory and no setting name anywhere on the
command line (lifecycle A2). The program calls
`schema.load_frozen(run_dir) -> Setting`, which parses `settings.yaml` against
the dataclasses and neither re-merges nor re-resolves references. A YAML edit
after launch, or days later before a refire, therefore cannot move a running
process to a different directory.

Upstream directories are found with `schema.run_dir(stage, setting)` using the
frozen setting, so a stage never has to be told where its input is.

**The method hook.** `train/methods/<m>.py` is the program; `train/utils/trainer.py`
is the library. The method module defines exactly these names, and `trainer.py`
calls them and never branches on the method:

| name | signature | what it must do |
|---|---|---|
| `VERSION` | `int` | bumped when this file's output changes meaning |
| `PROBE_KIND` | `"classifier"` or `"generator"` | tells `base.py` which head to attach |
| `batches(df, tok, cfg)` | `DataFrame, Tokenizer, Setting -> Iterator[Batch]` | the method's own packing; `cgen` and `cparam` each carry their own, per the tree's "no shared packing" |
| `loss(probe, batch)` | `Probe, Batch -> Tensor` | the training loss |
| `validate(probe, df, tok, cfg)` | `... -> dict[str, float]` | the validation metric; the key `objective` is the number `best/` is chosen on, lower is better |
| `predict(probe, df, tok, cfg)` | `... -> Iterator[dict]` | one prediction row per example row, in `data/prediction.py`'s columns |
| `reference_loss(probe, rows)` | `... -> Tensor` | the same loss computed one example per sequence, in its plainest form; the alignment gate compares it against `loss` on a few real batches before training starts |

`reference_loss` is the answer to the gap the structure review found (its item 1):
the tree keeps the alignment gate and drops `train/utils/reference.py`, so the
gate has nothing to compare against. Putting the plain loss in the method file,
beside the packed loss it checks, keeps the gate working without adding a file,
and it is the one piece of code a method's author must write twice on purpose.
`train.align_check` (default on) runs it; a mismatch above `1e-4` stops before
the first optimizer step.

`eval/methods/<m>.py` is a program in the same way and calls
`eval/utils/probe_eval.py` for the parts every method shares: read the prediction
rows, join them to the example rows, the bootstrap interval, write the report.

---

## Part 3. `run_dir` and keys

### 3.1 The signature and where it lives

```python
def run_dir(stage: str, setting: Setting) -> Path
```

in **`experimental_settings/schema.py`**, whose tree line already says it holds
the loader and the key.

Why there and not in `jobs/registry.py`: every stage below `jobs/` has to find
its own directory and its upstream's (build finds sample, train finds build, eval
finds train, inject finds two). If `run_dir` lived in `jobs/`, then `data/`,
`train/` and `eval/` would all import the top layer to resolve a path, which is
exactly the inversion the dependency review objects to (its P8). In `schema.py`
the function sits beside the stage table and the key it needs, and `schema.py`
imports nothing from the repo, so the graph stays pointing down. `jobs/` imports
`schema.py`, not the other way round.

### 3.2 The guarantees

1. **Determinism.** The same stage and the same setting give the same path, on
   any machine, in any venv.
2. **Purity.** `run_dir` reads the setting, the stage table, `models/table.yaml`,
   `constants/path_outputs.yaml` and the `VERSION` lines of the modules in the
   stage's version list. It **never touches the output tree**, so `run.py where`
   and a whole sweep's paths can be printed before anything has been run, and a
   missing NFS mount cannot change a key.
3. **Sensitivity.** The path changes when, and only when: a field the stage reads
   changes value; an upstream key changes; one of the folded `VERSION`s changes;
   the model-table result columns of a named model change; `debug` is on.
4. **Insensitivity.** The path does not change when a field the stage does not
   read changes, when `notes` changes, when a serving-only column changes, when
   a field is *added* to the schema with a default (Part 3.3), or when the code
   changes without a `VERSION` bump.
5. **Debug separation.** A debug run never shares a directory with a real one.
6. **Sweep children** each get their own path, because each child is a full
   setting whose swept field has a different value.

### 3.3 What the key is computed over

```
key(stage, setting) = sha1(canonical_json({
    "stage":    stage,
    "fields":   {dotted field name: value, for every field the stage reads
                 whose value differs from the schema default},
    "upstream": {name: key, for each upstream the stage table gives},
    "versions": {module: VERSION, for each module in the stage's version list},
    "debug":    true | absent,
}))[:12]
```

- **Diff from the defaults, not the resolved values.** This is what makes "add a
  hyperparameter" free: a field added with a default that reproduces the old
  behaviour is equal to its default in every existing setting, so it is absent
  from every key and nothing reruns. The price is the rule the fourth draft
  already states: *changing an existing default* must come with a `VERSION` bump
  on the module that reads it, and until `tests/` exists that rule is kept by
  hand. `settings_diff.yaml` in every run directory is the same dictionary, so
  what a key was computed over is always visible.
- **`notes` never enters.** Nor does anything under `constants/`.
- **Model table.** The named model's `result:` block is expanded into the setting
  before keying (the tree's own rule), so an edited context length or dtype gives
  a new key; the `serving:` block is not.
- **Versions.** `schema.py` gets a module's `VERSION` by reading the literal
  `VERSION = <int>` line out of the module's source file with a regex. It does
  not import the module. This is deliberate: it keeps the number in the file a
  person edits (synthesis item 8), it costs no import, and it works from every
  venv — which matters because `eval/` must compute a train key to find its
  upstream and must not import `train/utils/trainer.py`, which needs torch. An
  importlib-based version lookup would break principle 7 the first time eval ran.
  `run.py selfcheck` fails when a module in the stage table has no `VERSION`
  line or has one that is not an integer literal. The alternative (all version
  numbers listed in `schema.py`) is in Part 9(a).
- **Retired values.** `schema.py` keeps `RETIRED: set[tuple[str, str]]` of
  (axis, value). A retired value loads from a frozen `settings.yaml` so old runs
  still reproduce, and is refused in a new setting. Values are never renamed
  (dependencies P6).

### 3.4 The directory name

```
<root>/<stage>/<key>/                 normal
<root>/debug/<stage>/<key>/           debug
```

`<root>` is the single value in `constants/path_outputs.yaml`
(`/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs`). There is no
`outputs` symlink at the repo root; `run.py where` prints the path.

The directory is named by the key alone, with no setting name in it, because the
same key can be reached from several settings — that is the whole point of
sharing a sample or a build — and two names for one directory would be two
directories. Who owns a directory is in `meta.json`'s `owners` list, which
carries every (workflow, setting) that has run into it, and `run.py ls` prints
name and path together. Part 9(a) records the alternative.

`--debug` is applied **before** keying and adds `debug: true` to the key
(lifecycle B4), so a debug run can never be mistaken for a real one, can never
collide with a real run's tmux session name, and is never considered for reuse
by a non-debug walk. Its rows in `runs.jsonl` carry `debug: true` and `ls` hides
them unless asked.

A sweep expands at load into children named `<setting>/<field>=<value>,...`
(sorted by field name), each a full setting with its own keys. A child is
addressable on the command line by that name, so `run.py where train_probe
'ctool_q06/train.lr=3e-05' train` works and a single child can be refired.

### 3.5 What a piece command looks like

`jobs/launch.py` freezes the setting first, then starts pieces that name only the
directory:

```
tmux new-session -d -s <stage>-<key12>-<piece>
  cd <repo root> && <venv python> -m <module> --run-dir <dir> --piece <i>/<n>
```

The tmux session name is the piece's identity everywhere: in the start row, in
`ls`, in the record's `owner_session`, and in `kill`. It contains the key, so two
sessions for one piece cannot coexist on one host, and `launch.py` refuses to
start a key whose last row is `running` with a fresh heartbeat on any host
(lifecycle A4).

---

## Part 4. The environment base class — `data/environments/__init__.py`

### 4.1 The class and the entrance

```python
VERSION: int                      # of the base contract itself

class Environment:
    """A benchmark that hands out tasks, steps, can try a call early and undo
    it, and judges."""

    NAME: str                     # the value on the data.env axis
    VERSION: int                  # of this environment file
    INSTRUCTIONS: dict[str, str]  # variant name -> the developer message
    NO_CODE_MESSAGE: str          # what the agent is told when it writes no call
    RESULT_CAP: int               # characters an observation is clipped to (4000 today)
    SEED: int                     # the environment's own seed (100 for AppWorld)

def open_env(name: str) -> Environment
```

`open_env` imports `data/environments/<name>.py` inside the function with
`importlib`, checks that the nine methods below exist and that the four class
attributes are set, and returns an instance. Nothing else in the repo imports an
environment module by name, so adding one adds no import anywhere.

The fourth draft's line says "eight methods" and then lists nine. Nine is right
(dependencies P11); the count on the line is a slip and the class declares nine.

### 4.2 The nine methods

| method | signature | returns | one line |
|---|---|---|---|
| `tasks` | `tasks(split: str) -> list[str]` | task ids, in the file's order | the split's task list, read from the file named in `constants/path_datasets.yaml`; never shuffled |
| `open` | `open(task_id: str, seed: int) -> None` | — | enter a fresh world for this task and seed, named so two seeds never share the benchmark's own output directory; **the benchmark package is imported inside this method** |
| `step` | `step(action: str) -> tuple[str, str \| None]` | observation, error kind | run the agent's action, clip the observation to `RESULT_CAP`, classify the error |
| `speculate` | `speculate(call: str) -> dict` | see 4.3 | run a predicted call early and leave the world untouched |
| `judge` | `judge() -> dict` | the benchmark's evaluation dict | did the task succeed; the dict always has a boolean `success` |
| `close` | `close() -> None` | — | leave the world and delete the per-task outputs (AppWorld leaves about 90 KB per task) |
| `split_args` | `split_args(text: str) -> tuple[str, list[tuple[str, str]]] \| None` | tool name and named arguments, or None | parse the environment's action text into a call; the call regex is the environment's |
| `build_call` | `build_call(tool: str, args: list[tuple[str, str]]) -> str` | the normalised call string | the inverse of `split_args`, and the definition of `example.call` |
| `complete_call` | `complete_call(text: str) -> str \| None` | a complete call, or None | finish a call the probe generated but cut off (an unbalanced parenthesis, a missing quote) |

`split_args` keeps the tree's name and does the whole parse — today's
`first_call_named(code, AW_CALL)` plus `split_args_named`
(`legacy/pipeline/annotate/rules.py:118-164`). A rename to `parse_call` would be
a tree change and is a Part 9(b) proposal.

**Who calls what.** `agent/loop.py`: `tasks`, `open`, `step`, `judge`, `close`,
and `INSTRUCTIONS[cfg.data.instructions]`, `NO_CODE_MESSAGE`. `agent/inject.py`:
`speculate`, `complete_call`, `build_call` (on the object the loop passes it; it
never opens a world of its own). `data/build_dataset.py`: `split_args` and
`build_call` only — which is why the package import must sit inside `open`, or
build would run in the AppWorld venv alone (dependencies P11).

### 4.3 What `speculate` must guarantee

The three-step is today's, from
`legacy/pipeline/inject/exec_calls.py:16-17,564-570` and its copy in
`legacy/pipeline/inject/live_appworld.py:305-321`:

1. **Snapshot** the world under a fixed checkpoint name.
2. **Make the call executable** (AppWorld: requote the generated arguments
   against the live shell's namespace) and **run it**, clipping the output to
   `RESULT_CAP`.
3. **Restore** the snapshot, **refreeze the clock**, and **assert** that the
   frozen moment equals the one taken at `open`. The restore and the assertion
   run in a `finally`, so a call that raises still leaves the world unchanged.

Returns
`{"exec_code": str, "arg_modes": list[str], "exec_out": str, "exec_ok": bool, "error_kind": str | None, "spec_s": float}`
— exactly the fields the record's `spec` row needs, so `agent/inject.py` copies
the dict in rather than reassembling it.

The guarantee is "the genuine world is unchanged": the deferred test named in the
tree (a speculated call leaves the world unchanged, per environment, in that
environment's venv) is the check. Until it exists, `speculate`'s assertion is the
check, and it is a hard stop, not a warning.

### 4.4 Instruction text, variants, venv, version

The instruction text lives in the environment file, in `INSTRUCTIONS`, keyed by
variant name. The variant is chosen by the setting axis `data.instructions`
(default `v1`), whose allowed values are listed in `schema.py` and cross-checked
by `selfcheck` against the keys of every environment's `INSTRUCTIONS`. So a
prompt variant is a YAML line that enters the key by name, not a code edit with a
hand-kept version (structure item 8, applied without moving the folder).

`VERSION` on an environment file therefore guards only what is left: the
benchmark package's interface, the observation clipping, the error classes, the
call regex, the speculate three-step. It is folded into the keys of `sample`,
`build` and `inject`.

Venv: the file imports under `any` (only `re`, `pathlib`, PyYAML at module
level); the benchmark package is imported inside `open`. The interpreter that
runs a loop piece comes from the `venv:` column of that environment's row in
`constants/path_datasets.yaml`, read by `jobs/launch.py` (dependencies P7). That
column is a location, so it enters no key.

---

## Part 5. The setting schema — `experimental_settings/schema.py`

### 5.1 What the file holds

Four things, in this order, and nothing else: the dataclasses (fields, defaults,
one-line comments), the axis literals, the stage table (`STAGES`), and the loader
(`load`, `load_frozen`, `diff`, `key`, `run_dir`, `save`). It imports nothing
from the repo. The reviews want it split three ways (synthesis item 1); the tree
forbids that, so the mitigations are: axis values are literals (no upward
import), versions are read as text (no cycle), and the README line names all
eight importers so "who breaks" is answerable from the line.

Config loading is PyYAML plus dataclasses, per the owner's decision. No
OmegaConf: it is not installed, it needs `antlr4-python3-runtime`, and the only
feature this repo used it for is `${a.b}` interpolation, which the reference
syntax below replaces.

### 5.2 The sections and their fields

"key" marks whether the field enters the key of the stage that reads it.
Reference fields are marked `ref` and explained in 5.4.

**`data`** — which benchmark, and which prompt.

| field | type | default | key | one line |
|---|---|---|---|---|
| `env` | axis | `appworld` | yes | which benchmark environment |
| `instructions` | axis | `v1` | yes | which variant of the environment's developer message |

**`models`** — which models, by alias in `models/table.yaml`.

| field | type | default | key | one line |
|---|---|---|---|---|
| `agent` | str | `gptoss120b` | yes | the agent model alias; its `result:` block is expanded before keying |
| `probe` | str | `qwen06` | yes | the probe backbone alias; likewise |

**`generation`** — how the agent model generates. One path for sample and inject
(CONTEXT's same-setup rule).

| field | type | default | key | one line |
|---|---|---|---|---|
| `temperature` | float | `1.0` | yes | sampling temperature |
| `top_p` | float | `1.0` | yes | nucleus cutoff |
| `max_tokens` | int | `8192` | yes | per-step generation cap |
| `stop` | list[str] | `["<|return|>"]` | yes | stop strings |
| `reasoning_effort` | str | `high` | yes | the family's effort tier; written into the model's own system message |
| `date` | str | `2026-08-06` | yes | the date pinned into the model's own system message, so a rerun on another day has the same prefix |

**`sample`** — running the agent alone.

| field | type | default | key | one line |
|---|---|---|---|---|
| `split` | axis | `train` | yes | which task split to run |
| `seeds` | list[int] | `[42]` | no | one trajectory per seed per task; the seed goes into the request body and the record |
| `tasks` | list[str] \| null | `null` | no | restrict to these task ids |
| `max_steps` | int | `30` | yes | steps before the run is cut off |
| `store_token_ids` | bool | `false` | yes | keep the generated token ids in the record |
| `pieces` | int | `6` | no | how many loop processes |
| `replicas` | int | `1` | no | how many agent servers |

**`build`** — records to examples.

| field | type | default | key | one line |
|---|---|---|---|---|
| `max_cuts` | int | `64` | yes | cut points kept per step, thinned evenly when there are more |
| `min_think` | int | `40` | yes | characters of thinking below which a step has no cuts |
| `hist_rounds` | int | `3` | yes | tool rounds kept in the probe's text |
| `result_cap` | int | `400` | yes | characters per environment result inside the probe's text |
| `weight_mode` | axis | `uniform` | yes | `uniform` (weight 1 per cut) or `per_event` (1/n, the old convention) |
| `split_source` | axis | `env` | yes | `env` = the benchmark's official task lists; `hash` = a stable hash of the task id |
| `split_ratio` | list[float] | `[0.8, 0.1, 0.1]` | yes | train/val/test shares, used only under `hash` |

**`probe`** — what the probe is.

| field | type | default | key | one line |
|---|---|---|---|---|
| `method` | axis | `ctool` | yes | `ctool`, `cgen`, `cparam` |
| `tuning` | axis | `full` | yes | `full` or `lora` |
| `lora_r` | int | `16` | yes | LoRA rank, used under `lora` |
| `lora_alpha` | int | `32` | yes | LoRA alpha |
| `lora_dropout` | float | `0.0` | yes | LoRA dropout |
| `max_len` | int | `2048` | yes | tokens of probe input kept, left-truncated |

**`train`**

| field | type | default | key | one line |
|---|---|---|---|---|
| `epochs` | int | `1` | yes | passes over the training split |
| `lr` | float | `1.0e-5` | yes | learning rate |
| `warmup_ratio` | float | `0.0` | yes | share of steps spent warming the schedule |
| `batch_tokens` | int | `8192` | yes | token budget per batch |
| `seed` | int | `42` | yes | seeds the shuffle, the init and the dropout |
| `grad_ckpt` | bool | `false` | yes | gradient checkpointing (memory, not results — kept in the key because it changes kernels) |
| `align_check` | bool | `true` | yes | run the packed-versus-plain loss gate before training |
| `checkpoint_hours` | float | `2.0` | no | how often `last/` is written |
| `predict.splits` | list[str] | `["val", "test"]` | yes | which splits the prediction step covers |
| `predict.cap` | int | `0` | yes | rows per split, 0 = all (debug sets 100) |

**`eval`**

| field | type | default | key | one line |
|---|---|---|---|---|
| `risk` | list[float] | `[0.10, 0.05]` | yes | risk targets theta is chosen at |
| `theta_grid` | list[float] | `[0.5 … 0.99]` | yes | the thetas swept on val |
| `bootstrap` | int | `1000` | yes | resamples for the confidence interval |
| `bootstrap_seed` | int | `42` | yes | seeds the resampling |
| `theta_from` | ref | `null` | yes | for `cgen` and `cparam`: the ctool setting whose frozen theta selects the rows |

**`inject`** — the live run.

| field | type | default | key | one line |
|---|---|---|---|---|
| `split` | axis | `test` | yes | which split to run |
| `seeds` | list[int] | `[42]` | no | one trajectory per seed per task |
| `tasks` | list[str] \| null | `null` | no | restrict to these task ids |
| `max_steps` | int | `30` | yes | steps before the run is cut off |
| `probe_score` | ref | required | yes | the setting whose ctool eval says when to fire |
| `probe_gen` | ref | required | yes | the setting whose cgen training writes the call |
| `theta` | float | required | yes | the confidence threshold; CONTEXT: theta is always given by a person, and startup is refused without it |
| `format` | axis | `p1_e1` | yes | how an early result is written into the stream |
| `max_inject_per_step` | int | `1` | yes | injections allowed per step |
| `chunk_tokens` | int | `64` | yes | tokens per streaming segment between probe calls |
| `tail_tokens` | int | `1024` | yes | segment size once probing has stopped |
| `max_cuts` | int | `64` | yes | cuts scored per step |
| `no_probe` | bool | `false` | yes | the control arm: the whole machinery is wired and never fires |
| `nofill` | bool | `false` | yes | the ident3 arm: interrupt and resend the head unchanged, inject nothing |
| `fire_nth_cut` | int | `0` | yes | fire at the n-th cut instead of by score (0 = by score) |
| `store_token_ids` | bool | `true` | yes | keep the generated token ids in the record |
| `pieces` | int | `6` | no | how many loop processes |
| `replicas` | int | `1` | no | how many agent servers |

The no-probe control is `no_probe: true` in an inject setting, not a flag on
`agent/loop.py` (structure item 13). That keeps one generation path and makes the
control arm an experiment with its own directory, as the same-setup rule wants.

**`score`**

| field | type | default | key | one line |
|---|---|---|---|---|
| `baseline` | ref | `null` | yes | the run to pair against, task by task and seed by seed |
| `by_seed` | bool | `true` | yes | report mean and spread across seeds |

There is no `logging` section: the MLflow tracker of the third draft is dropped
with the sampler (Part 9(a)). `notes` is a free string on any named setting and
never enters a key.

### 5.3 The axes and where each value's code lives

| axis | values today | the code behind a value | checked by selfcheck against |
|---|---|---|---|
| `data.env` | `appworld` | `data/environments/<value>.py` | the file names under `data/environments/` |
| `data.instructions` | `v1` | a key of that environment's `INSTRUCTIONS` | every environment's `INSTRUCTIONS` keys |
| `sample.split`, `inject.split` | `train`, `dev`, `test` | a key of the environment's row in `constants/path_datasets.yaml` | that file's split keys |
| `probe.method` | `ctool`, `cgen`, `cparam` | `train/methods/<value>.py` and `eval/methods/<value>.py` | the intersection of those two directories |
| `probe.tuning` | `full`, `lora` | a branch in `models/probe_models/base.py` | — |
| `inject.format` | `note`, `p1_e1`, `p1_e2`, `p2_e1`, `p2_e2` | an entry in `agent/inject_format.py`'s `FORMATS` | `FORMATS`' keys, parsed with `ast` |
| `build.weight_mode` | `uniform`, `per_event` | a branch in `data/build_dataset.py` | — |
| `build.split_source` | `env`, `hash` | a branch in `data/build_dataset.py` | — |

Model aliases are **not** an axis: they are validated against the rows of
`models/table.yaml`, which is the one registry of legal model names. The fourth
draft has two sources for them (the "register every value" rule and the model
table); this closes it in the table's favour, which is what makes a new backbone
a row and not a row plus an axis line.

Axis values are literals in `schema.py`, never imported from the layer that
implements them. `run.py selfcheck` proves the literals equal what is on disk,
by parsing, not importing. That is the whole of the settings layer's independence
(dependencies P1): a misspelled value still fails at load, and `schema.py` still
imports nothing.

### 5.4 References to another setting

Three fields point at another run: `eval.theta_from`, `inject.probe_score`,
`inject.probe_gen`, and `score.baseline`. One syntax:

```
<workflow>/<setting>        a name, resolved by loading that file and computing its key chain
key:<12 hex>                a key, pinned; survives an edit to the named setting
dir:<absolute path>         a directory, for a run made before this scheme
```

The loader resolves a reference at load time. The stage table says which stage of
the referenced setting each field wants (Part 2.1), so a name resolves to exactly
one key, and **that key enters the referencing stage's key** and is written into
`meta.json`. A name that no longer exists in its file is a load error. `run.py`
refuses to start a stage whose referenced run has no `done.json`.

A referencing setting **inherits** the referenced run's `data`, `models.agent`
and `generation` sections. Stating one of them differently is a load error unless
the setting carries an explicit `override:` block naming the field. This is the
same-setup rule turned into a loader refusal: an inject arm cannot silently
differ from the data its probe was trained on, or from its baseline.

### 5.5 The sweep keyword

```yaml
ctool_q17_lr:
  models: {probe: qwen17}
  probe: {method: ctool, tuning: lora}
  sweep: {train.lr: [1.0e-4, 3.0e-4, 5.0e-4], train.seed: [42, 67]}
```

expands at load into the cartesian product, six children named
`ctool_q17_lr/train.lr=0.0001,train.seed=42` and so on (fields sorted by name,
values formatted by `repr` of the parsed YAML value). Each child is a full
setting with its own keys; children share the sample and build keys and
therefore the sample and build directories. `run.py` accepts a child name
anywhere a setting name is accepted. `eval/method_table.py` groups children by
everything except the swept fields and reports mean and spread; it finds them by
the `parent` and `swept` fields the registry row carries.

One `sweep:` block per named setting. Sweeping a field that `debug.yaml` also
sets is refused at load (otherwise the children collapse onto one key).

### 5.6 `debug.yaml`

Sizes only, never a model and never a tuning, so a debug run exercises the real
code path:

```yaml
sample:  {tasks_n: 3, seeds: [42], pieces: 1, replicas: 1, max_steps: 6}
build:   {max_cuts: 8}
train:   {epochs: 1, max_steps: 20, predict: {cap: 100}}
inject:  {tasks_n: 3, seeds: [42], pieces: 1}
eval:    {bootstrap: 50}
```

`tasks_n` is the one field that exists for debug alone: take the first n task
ids of the split. `train.max_steps` likewise caps the optimizer steps. Both are
in the schema with defaults (`null`, meaning no cap) so debug adds no special
case to the loader.

### 5.7 The merge order, and what the loader refuses

Merge, in order, each beating the one before:

1. the dataclass defaults;
2. the file's `common:` block;
3. the named setting;
4. `debug.yaml`, when `--debug` was given;
5. the command-line overrides `section.field=value`.

A list field is **replaced, never appended**: `seeds: [42]` in a setting over
`seeds: [42, 67, 4267]` in `common` gives `[42]`. Overrides beat debug, so
`--debug train.lr=1e-4` works. Sweep expansion happens after the merge and before
keying; references are resolved after the merge; the model table's `result:`
block is expanded last, immediately before keying.

The loader refuses, with the field named in the message:

- a key that is not in the schema;
- a value outside an axis, or a retired value in a new setting;
- a stage section for a stage the file's `pipeline:` line does not name;
- a reference that does not resolve, or that resolves to a run whose stage the
  table does not provide;
- a referencing setting whose `data`, `models.agent` or `generation` differs from
  the referenced run's without an `override:` block;
- a `sweep:` field that `debug.yaml` also sets, or a `sweep:` over a field that
  is not in the schema;
- a required field left unset (`inject.theta`, `inject.probe_score`,
  `inject.probe_gen`, `eval.theta_from` for `cgen` and `cparam`);
- a `settings.yaml` frozen at a version of the schema that has since removed a
  field it uses (`load_frozen` says which field and which run directory).

---

## Part 6. The model table and constants

### 6.1 `models/table.yaml`

One row per alias, in two blocks. The rule for which block a column goes in is
one question: **does changing it change the bytes the model produces?** Yes goes
in `result:` and enters the key; no goes in `serving:` and never does. That is
the shape the structure review asked for (its item 7) without moving the file.

```yaml
gptoss120b:
  role: agent
  family: gptoss
  result:
    weights: gpt-oss-120b        # alias into constants/path_models.yaml
    dtype: bfloat16
    quantization: null
    max_model_len: 131072
    served_model_name: gpt-oss-120b
  serving:
    host: tokyo108
    port: 8103
    gpu_memory_utilization: 0.92
    tensor_parallel_size: 1
    env: {LD_LIBRARY_PATH: /home/y-guo/reproduce/new1/envs/cuda-compat-13.0,
          VLLM_USE_FLASHINFER_SAMPLER: "0"}
    extra_flags: ""

qwen06:
  role: probe
  family: qwen                   # the backbone file, models/probe_models/qwen.py
  result:
    weights: qwen3-0.6b-base
    dtype: bfloat16
  serving: {}
```

| column | block | why |
|---|---|---|
| `role` | row | `agent` or `probe`; decides which side of `models/` the family name resolves against |
| `family` | row | the file name under `agent_models/` or `probe_models/`; changing it changes everything, so it is keyed as part of the row identity |
| `weights` | result | different weights, different outputs |
| `dtype`, `quantization` | result | change the arithmetic |
| `max_model_len` | result | changes where a long prompt is refused, and thus which tasks abort (grounding F8, dependencies P5) |
| `served_model_name` | result | the string the client sends; a mismatch is a different server |
| `host`, `port` | serving | where the same server runs |
| `gpu_memory_utilization`, `tensor_parallel_size` | serving | how much card it takes |
| `env`, `extra_flags` | serving | launch environment; anything here that turns out to change results moves to `result:` and the move is a key change on purpose |

`experimental_settings/schema.py` expands the `result:` block of the named agent
and probe into the setting before keying; the `serving:` block is read only by
`models/agent_models/service.py` at start. A new model of a known family or
backbone is one row here and one row in `constants/path_models.yaml`.

The owner's open question — whether the read-only hook covers `table.yaml` — is
answered yes in this draft: the `result:` block changes results exactly as a
setting does, so the hook that refuses agent edits to
`experimental_settings/*.yaml` covers `models/table.yaml` too. Part 9(a).

### 6.2 `constants/`

Locations only. Nothing here enters a key; a path changes only when the same
bytes move, and new bytes are a new alias.

**`path_datasets.yaml`** — one block per environment:

| column | meaning |
|---|---|
| `home` | the clone's directory (the benchmark is `cd`-ed into it before its package is imported) |
| `venv` | the interpreter that runs a loop piece for this environment — the file `jobs/launch.py` reads to answer "which python" (dependencies P7) |
| `data` | the benchmark's data root |
| `splits` | split name -> the task-id file for that split |

**`path_outputs.yaml`** — `root:` (the NFS outputs root) and `debug_subdir:`
(`debug`). Two lines, one home for the outputs root; there is no symlink.

**`path_models.yaml`** — alias -> `{path, note}`, exactly today's
`legacy/configs/models.json` shape, in YAML. `path` is an absolute directory or
a hub id; `note` is where the copy came from and when it was verified.

**Which side does a new column go to?** Ask what happens if it changes and
nothing else does. If a finished run's numbers would have been different, it is a
setting field or a `result:` column. If only the machine or the speed changes, it
is `constants/` or a `serving:` column. The benchmark's split *lists* are the
awkward case the review raised (dependencies P5): they live behind
`path_datasets.yaml` but their contents decide which tasks are sampled. The rule
here: the environment file owns reading them, its `VERSION` covers the reading
rule, the sample directory's `meta.json` records the sha1 of every split file it
read, and `run.py ls` flags a directory whose recorded hash no longer matches.
Downstream is safe without that flag anyway, because `build` refuses to run
unless every requested (task, seed) is present and records what it consumed.

---

## Part 7. Service protocols

Two services, one file each, both ends in the file, as the tree says. The client
half is standard library and imports under `any`; the server half is a `main`
whose heavy imports sit inside it. `jobs/launch.py` starts both as pieces of a
stage and writes their rows with `kind: service`.

### 7.1 The agent service — `models/agent_models/service.py` (vLLM)

**Server half** (`venv: vllm`):

```
python -m models.agent_models.service serve --run-dir <dir> --model <alias> \
    --port <n> --gpus <ids> [--attach-only]
```

reads the alias's `result:` and `serving:` blocks from `models/table.yaml` and
the weights path from `constants/path_models.yaml`, and either starts
`vllm serve` with those flags or attaches to a live server on the same host and
port. **Attach is verified, not assumed**: the service asks `GET /v1/models` for
the served model name, and refuses to attach unless that name and every
`result:` column match the row it was asked for. A mismatched live server is an
error, never a silent reuse (lifecycle B8).

Then it runs the check table before reporting healthy:

| check | how |
|---|---|
| health | `GET /health` answers within the wait |
| render equals server | for one fixture conversation, `gptoss.render(messages, generation)` computed locally in this venv equals `POST /tokenize {"messages": …}` from the server, id for id |
| special-token round trip | for one fixture string containing harmony control markers, `decode(encode(s, special=True)) == s` |

The second check is the reason the family file's `render` exists at all: at run
time nobody calls it, because the loop cannot import `openai_harmony` (its venv
holds pydantic 1.10.26, `legacy/envs/collect/common.py:15-20`). It exists so that
the server's own rendering can be proved equal to the format this repo believes
in, once per launch, in a venv that can compute both.

**Client half** (standard library, imported by `agent/generate.py` and
`agent/loop.py`). Five calls, all against the vLLM server's own endpoints, which
were checked in `external/vllm-env` (vLLM 0.26.0):

| call | request | response | endpoint |
|---|---|---|---|
| `stream(prompt_ids, generation, seed)` | `POST /v1/completions` with `prompt: [ids]`, `stream: true`, `return_token_ids: true`, `add_special_tokens: false`, `skip_special_tokens: false`, plus temperature, top_p, max_tokens, stop, seed | an iterator of `(text_chunk, token_ids)` until a stop string or `max_tokens`; the connection is closed to abort when the probe fires | `/v1/completions` |
| `render(messages, generation)` | `POST /tokenize` with `messages`, `add_generation_prompt: true`, `chat_template_kwargs: {reasoning_effort: …}` | `{count, max_model_len, tokens: [ids]}` | `/tokenize` |
| `encode(text, special)` | `POST /tokenize` with `prompt: text`, `add_special_tokens: special` | `{tokens: [ids]}` | `/tokenize` |
| `decode(ids)` | `POST /detokenize` with `tokens: [ids]` | `{prompt: text}` | `/detokenize` |
| `health()` | `GET /health` and `GET /v1/models` | the served model name and the row it claims | — |

`render`, `encode` and `decode` on the *agent* service is the change that makes a
second agent family one file plus a row (dependencies P4, grounding F4,
synthesis item 6). Today all three live on the probe server
(`legacy/pipeline/inject/probe_server.py:14-32`), which is why the probe service
loads the agent's tokenizer today and why adding Qwen as an agent would touch
three files that have nothing to do with Qwen.

The startup checks are what make the move safe: if vLLM's `/tokenize` disagrees
with the family's own render, or if `/detokenize` loses control markers, the
service refuses to start and says so, rather than producing a subtly different
prompt at three in the morning. Part 9(a) names the fallback.

**Who starts it.** `jobs/launch.py`, as `sample.replicas` (or
`inject.replicas`) service pieces, each with its own row, port and card list. A
service piece's verdict is the service branch of Part 8.4.

### 7.2 The probe service — `models/probe_models/service.py`

**Server half** (`venv: probe`):

```
python -m models.probe_models.service serve --run-dir <dir> \
    --score-ckpt <dir> --gen-ckpt <dir> --theta <f> --temperature <f> \
    --port <n> --device cuda:0 [--check]
```

It loads the two checkpoints through `models/probe_models/base.py` (imported
inside `serve`), and answers three calls. It reads no report and resolves no
reference: `jobs/launch.py` resolved `inject.probe_score` and `inject.probe_gen`,
read the probe report, and passed the numbers here (Part 1.4). `--check` loads
both probes, runs one scoring and one generation, prints the echo and exits; it
is what a launch runs before it starts pieces.

| call | request | response |
|---|---|---|
| `POST /score` | `{"text": <probe input>}` | `{"conf": float, "label": str}` — `conf` is `max softmax(logits / temperature)`, `label` is the argmax class name |
| `POST /gen` | `{"text": <probe input at the cut>}` | `{"call": str}` — greedy continuation after the method's separator, cut at the first newline and stripped |
| `GET /health` | — | the startup echo: theta, temperature, both checkpoint paths, both train keys, the device, the format version |

The threshold itself is not applied here: `/score` returns the confidence and
`agent/inject.py` compares it against `inject.theta`. One place decides to fire,
and it is the place that also knows `fire_nth_cut` and `max_inject_per_step`.
(Today the server also returns `fired`, `legacy/pipeline/inject/probe_server.py:14-16`;
dropping it removes a second copy of the rule.)

**Client half** (standard library, imported by `agent/inject.py`): `score(text)`,
`generate(text)`, `health()`. Nothing else — no `render`, no `encode`, no
`decode`. That is the whole of the P4 fix.

**Who renders harmony, given that the loop's venv cannot.** The vLLM server,
through `/tokenize`, called by the agent service's client. The loop assembles
messages as plain dicts, the family file says how a *reply* is parsed (which is
pure string work and imports nothing), and the only step that needs the harmony
library is turning messages into ids — which now happens where the model is.

### 7.3 What the loop does per step, in terms of these calls

So that the two services' contracts can be checked against one another:

1. `agent_client.render(messages, generation)` -> `prefix_ids`.
2. `agent_client.stream(prefix_ids, generation, seed)` -> token chunks;
   `agent/generate.py` accumulates text and ids and parses channels as they
   arrive.
3. On a sample run, that is all: at end of turn the step's `gen` row is written.
4. On an inject run, `agent/inject.py` iterates the same stream. At each new cut
   from `data/probe_input.py`, it calls `probe_client.score(assemble(...))`; on
   the first confidence at or above `inject.theta` it closes the stream, calls
   `probe_client.generate(...)`, completes the call through the environment,
   `speculate`s it, builds the splice text through `agent/inject_format.py` (and
   the family's `wrap_prefetch` for an `after` placement), turns that text into
   ids with `agent_client.encode(note, special=needs_special(format))`, backs the
   head off to a token boundary (checked with `agent_client.decode`), and starts
   a new request from `prefix_ids + head_ids + note_ids`.
5. The discarded ids go into the `spec` row; when the next fire or the end of the
   step arrives, the `resume` row records how much of the resent continuation
   matched them.

---

## Part 8. The registry — `jobs/registry.py`

Standard library only, imported by every stage, and importing nothing from the
repo. That is what makes its position in the tree harmless: the layer order is a
reading order, and this file is a leaf.

The reviews want it split (synthesis item 2, structure item 5); the tree forbids
that, so the mitigations are: the writer functions and the reader functions are
in two clearly marked halves of the file, the README line names all eight
importers, and **only login-machine processes append to `runs.jsonl`** (below),
which is the part of the split that was about correctness rather than tidiness.

Terminology, settled here: the thing in `runs.jsonl` is a **row**. "Record" means
the task record and nothing else (lifecycle C2).

### 8.1 `jobs/runs.jsonl`

Append-only, one JSON object per line, never rewritten. Two kinds.

**Start row**, written once per stage run by `jobs/launch.py` after the alive
check (GPU stages) or by `run.py` before it starts a CPU stage:

| field | type | meaning |
|---|---|---|
| `ev` | str | `start` |
| `t` | str | local time, `YYYY-MM-DD HH:MM` |
| `run_id` | str | `<stage>-<key>`; the primary key, equal to the directory name's tail and to the tmux session prefix |
| `stage` | str | one of the six |
| `key` | str | the 12-character key |
| `dir` | str | the absolute run directory |
| `workflow` / `setting` | str | the file and the named setting that asked for it; the child name for a sweep child |
| `parent` / `swept` | str / dict | the sweep parent and the swept field values, for `method_table.py`'s grouping; null otherwise |
| `debug` | bool | a debug run |
| `upstream` | dict | upstream name -> key |
| `versions` | dict | module -> `VERSION`, as folded into the key |
| `diff` | dict | `settings_diff.yaml` as JSON: what the key was computed over |
| `commit`, `branch`, `dirty`, `dirty_count`, `dirty_files` | str/bool/int/list | the git state at launch, fail-closed (a failed git probe counts as dirty), copied from `legacy/ops/record.py:58-83` |
| `host` | str | where the launch happened |
| `pieces` | list | one entry per piece: `{kind: batch\|service, host, gpus, session, log, port}` |
| `cmd` | str | the command a piece runs, for a person to read and to refire |

**Finish row**, written by `run.py` or `jobs/launch.py` when a walk finds
`done.json`, or by `run.py kill`:

| field | type | meaning |
|---|---|---|
| `ev` | str | `finish` |
| `t` | str | local time |
| `run_id` | str | the same key |
| `status` | str | `ok`, `failed`, `killed` |
| `metrics` | dict | the stage's headline numbers, lifted from its own report (train: best validation; eval: coverage and accuracy at each risk; score: task success and tokens) |
| `report` | str | the report file inside the run directory |
| `elapsed_s` | float | from the start row's time |

A later finish row for the same `run_id` wins. `RESULTS.md` is rendered from the
whole file by `registry.py` on every append and is never edited by hand.

There is no `--conclusion` field: a conclusion is a sentence about a direction
and belongs in `notes/TIMELINE.md`, which is a person's file (lifecycle C3).

### 8.2 `meta.json`

One per run directory, rewritten (not appended) by `registry.py`:

| field | meaning |
|---|---|
| `stage`, `key`, `dir` | identity |
| `versions`, `upstream`, `diff` | as in the start row |
| `owners` | every `{workflow, setting}` that has run into this directory |
| `launches` | one entry per start: `{t, commit, dirty_count, host, pieces, cmd}` |
| `inputs` | for a stage that consumes files: the sha1 of each split file or upstream file it read |
| `status_hint` | the last thing the stage itself said: `running`, `finished`, or the exception class it died on |

`status_hint` is how a compute node reports without touching `runs.jsonl`
(lifecycle B11): the stage writes into its own directory on NFS, and `ls` folds
it in. `meta.json` also absorbs today's `RUNMETA.json` (`legacy/ops/runmeta.py`),
which is why that file has no successor of its own.

### 8.3 The heartbeat

Today's line format, kept exactly (`legacy/ops/heartbeat.py:15-33`), because the
verdict rules are written against it and it already survives being read from a
log tail:

```
@hb {"done": 12, "total": 400, "unit": "task", "ts": 1758000000.0,
     "tok_in": 1234, "tok_out": 567, "loss": 0.42, "status": "done"}
```

`done`, `total`, `unit`, `ts` are required; `tok_in`, `tok_out`, `loss`,
`status` are optional. `ts` is the writing machine's clock and is only ever
diffed against another `ts` from the same machine. `unit` is the stage's own word
(`task` for sample and inject, `step` for train, `row` for build).

Two changes from today: the line is written to `<run_dir>/heartbeat/<piece>.jsonl`
as well as to stdout, so the monitor does not have to parse a log tail; and one
file has exactly one writer, so no lock is needed on NFS. Every stage emits
`emit(0, total, unit)` before its main loop — the signal that the model has
finished loading — and a final beat with `status: "done"`.

### 8.4 Verdicts

Pure functions over (heartbeat history, liveness, kind), in `registry.py`, ported
from `legacy/ops/verdicts.py` unchanged in behaviour. Six values in a fixed
priority order — `done`, `dead`, `suspected stall`, `warming up`, `slowed`,
`healthy` — computed by the program and never guessed by an agent, which is
CONTEXT's definition of a verdict.

| function | signature | rule |
|---|---|---|
| `typical_gap_s(beat_ts)` | list[float] -> float\|None | median of the last 20 intervals; None below 3 intervals |
| `stall_line_s(beat_ts, override)` | -> float\|None | `max(5 x typical gap, 3 x 60 s)`; None while there are too few beats, and the caller falls back to the 1800 s warm-up cap |
| `rates(first_beat, recent_beats)` | -> (avg, recent) | done per second, over the whole run and over the last 10 beats |
| `judge(piece)` | dict -> (verdict, escalated) | `done` if `status == done` or `done >= total`; else `dead` if the session is gone; else `suspected stall` if the age is past the line; else `warming up` before the first beat; else `slowed` if the recent rate is below half the average; else `healthy` |
| `judge_service(piece)` | dict -> (verdict, escalated) | `dead` if the session is gone; `healthy` if the port answers; `warming up` before the first answer and within the warm-up cap; `suspected stall` after three consecutive rounds of no answer |

`DEFAULTS` keeps the constants in one dictionary, as today, so a per-job
override (`stall_line`, `escalate_line`, `warmup_s` in the start row's piece
entry) is the only way a number changes.

What is gone: the resident sampler, the sampling history, the web page, the
incident agent, the autopsy, the escalation line's automatic consequence, the
incident record. `run.py ls` computes the verdicts on demand from the heartbeat
files and one `tmux ls` per host. `escalated` survives as a flag `ls` prints, not
as something that spawns a process. Part 9(a) states this as a decision the owner
can veto, and it is the one change in this document that makes several CONTEXT.md
entries obsolete in the same commit.

### 8.5 What the subcommands print

| subcommand | prints |
|---|---|
| `run.py ls [workflow]` | one line per run: `run_id`, stage, the names that own it, verdict, progress (`done/total` and a rate), the heartbeat's age, the tmux session, and a flag column for: the setting has been edited since (its key no longer matches the name), a folded `VERSION` is behind the code, `consumed.json` no longer matches the upstream, and a tmux session of this repo that matches no row |
| `run.py where <workflow> <setting> <stage>` | the absolute run directory, whether or not it exists |
| `run.py find section.field=value …` | the rows whose `diff` matches every given field, newest first |
| `run.py kill <workflow> <setting> <stage>` | the pieces it ended, and writes the `killed` finish row; refuses while a piece is a service another live run is attached to |
| `run.py free` | free cards per host, probed now, never cached: a card with any compute process, or whose probe failed, is busy |

`ls` is the only place a verdict is produced, and `find` is the only way to ask
"which runs used this value" — which works because the start row carries `diff`.

### 8.6 The lock, and who may append

`runs.jsonl` is appended only by processes on the login machine: `run.py` and
`jobs/launch.py`. They take `runs.jsonl.lock` (an `O_EXCL` lock file with the pid
and a stale timeout) for the duration of one append plus the `RESULTS.md`
re-render. Stage processes on compute nodes write **only** into their own run
directory: `meta.json`'s `status_hint`, their heartbeat file and `done.json`.
That removes cross-host `fcntl` locking on NFS from the design (lifecycle B11)
without splitting the file.

The dirty-tree gate lives in `jobs/launch.py` as one function (structure item 10;
the project CLAUDE.md's hard rule). It refuses a launch from a dirty tree,
`--allow-dirty` records `dirty.patch` and the file list into `meta.json` and the
start row, and the three ledger paths (`jobs/runs.jsonl`, `jobs/RESULTS.md`,
`jobs/runs.jsonl.lock`) never count as dirty — today's `LEDGER_PATHS` exemption,
which existed in three copies (`legacy/ops/record.py:52-55`) and now exists in
one.

---

## Part 9. Decisions, proposals and their alternatives

### 9(a). Choices the owner could reasonably veto

Each line: the choice, the alternative it beat, why this one.

1. **The example row is method-independent** (one row per cut carrying `tool`,
   `call` and `args`); alternative: one example file per method, as today's
   build writes. Chosen because it takes `data/build_dataset.py` and
   `data/example.py` off the "fourth probe method" list and lets one build serve
   three methods; it costs unused columns and one parquet about 15% larger.
2. **The prediction row is method-independent** and generators predict at every
   cut row; alternative (today's): generate only at the rows a ctool run's theta
   selects. The owner already decided this; the cost is the one number the
   construction plan must measure, since today's `eval_causal_call.py` generates
   at most 8,533 rows where every row would be 507,104. The fallback stays
   written down: an `eval.theta_from`-style field on `train` instead of `eval`.
3. **The key is over the diff from the defaults**, not the resolved values;
   alternative: hash the resolved setting. Chosen because it makes "add a
   hyperparameter" free, which is the most frequent extension; it costs the
   hand-kept rule that changing an existing default needs a `VERSION` bump.
4. **`run_dir` lives in `experimental_settings/schema.py`**; alternative:
   `jobs/registry.py`. Chosen so that `data/`, `train/` and `eval/` resolve
   paths without importing the top layer.
5. **`run_dir` never reads the output tree**, so `build`'s key folds the sample
   *key* and the requested subset rather than the consumed files' hashes;
   alternative: hash the input files into the key. Chosen so a key is computable
   before anything has run (sweeps, `where`, dry runs); the hashes are recorded
   in `consumed.json` and checked by `ls` instead.
6. **`VERSION` is read out of a module's source text** by `schema.py`;
   alternatives: import the module (breaks principle 7 the first time `eval/`
   computes a train key, because `trainer.py` needs torch), or list every number
   in `schema.py` (moves the number away from the file a person edits).
7. **The probe service is handed theta and the temperature on its command line**
   by `jobs/launch.py`; alternative: the service reads the eval report itself,
   as today. Chosen to keep `models/` from depending on an `eval/` output, and
   to make a live run's theta visible in its own `settings.yaml`.
8. **Rendering and tokenising happen on the vLLM server** through `/tokenize`
   and `/detokenize` (both confirmed present in vLLM 0.26.0 in
   `external/vllm-env`); alternative: keep them on the probe service, as today.
   Chosen because it is what makes a second agent family one file plus a row.
   The fallback, if the startup equality check ever fails: the probe service
   regains `/render`, `/encode`, `/decode` and the tree pays the P4 coupling.
9. **Model aliases are validated against `models/table.yaml`, not an axis in
   `schema.py`**; alternative: an axis, per the "register every value" rule.
   Chosen so there is one list of legal model names; the table is hook-protected
   like a setting file, which is also the answer to the owner's open question.
10. **The run directory is named by the key alone**; alternative: include the
    setting name. Chosen because one key can be reached from several settings and
    two names would mean two directories; `ls` and `where` carry the names.
11. **`eval` and `score` always recompute inside their key**; alternative: skip
    when done, like the GPU stages. Chosen because they take seconds and because
    a silently reused stale number is the failure principle 7 exists to prevent.
12. **A partial task record is deleted and the task redone**; alternative: resume
    a trajectory mid-task. Chosen because the world state dies with the process,
    and because deleting also removes the half-written last line that would
    otherwise break a strict Polars read.
13. **The sampler, the incident agent, the escalation consequence, the sampling
    history and the web page are retired**; `run.py ls` computes verdicts on
    demand. The owner named this; it is repeated here because it makes nine
    CONTEXT.md entries obsolete, and those entries must be rewritten in the same
    commit or the glossary will describe a process that does not exist.
14. **`venv: any` means standard library, PyYAML and Polars — not NumPy**,
    because NumPy is absent from the AppWorld venv (checked). Consequence: the
    temperature fit in `eval/methods/ctool.py` is a golden-section search over
    `log T` with the cross-entropy computed in Polars list expressions, replacing
    today's torch LBFGS (`legacy/pipeline/eval/eval_tool.py:213-224`), and the
    bootstrap is plain Python over per-event records. The alternative is to
    install NumPy into the AppWorld venv, which touches a venv this repo has
    deliberately frozen around pydantic 1.10.26.
15. **The instruction text is an axis value (`data.instructions`)**, not a code
    edit guarded by a `VERSION`; alternative: the fourth draft's wording. Chosen
    because a prompt variant is the value the owner is most likely to vary, and
    it should enter the key by name like every other varied value.
16. **There is no `logging` section and no MLflow**; the third draft's optional
    tracker is dropped with the sampler. `metrics.jsonl` plus `ls` is the whole
    of monitoring.
17. **The no-probe control is `inject.no_probe: true`**, an experiment with its
    own directory, not a flag on the loop. Chosen so the control arm obeys the
    same-setup rule by construction.
18. **`data/example.py` owns the normal form of a call**, so train's validation
    and eval's metric share a definition without `train/` importing `eval/`;
    alternative: the dependency review's `data/methods/<m>.py`, which is a new
    file and therefore a Part 9(b) proposal.
19. **The method file is the program and `trainer.py` is the library** (hooks
    listed in Part 2.3); alternative: `trainer.py` as the program dispatching on
    `probe.method`. Chosen so `trainer.py` never branches on a method and a
    fourth method adds no line to it.
20. **`reference_loss` is a hook on each method file**, not a shared
    `train/reference.py`; the tree drops that file, and the alignment gate the
    tree keeps needs something to compare against. This is the one place where
    the contract asks for code to be written twice on purpose.

### 9(b). Reviewer fixes that need a structural change — not applied

Each line: the fix, the file it would add, split or move, what it would buy.

1. **Split `experimental_settings/schema.py`** into `schema.py` (fields, axes,
   stage table), `loader.py` (merge, debug, overrides, sweep, references) and
   `key.py` (the hash). Buys: the file everyone edits stops being the file
   everyone imports. (synthesis 1, dependencies P1, structure 4)
2. **Split `jobs/registry.py`** into `ledger.py` (append, meta, heartbeat;
   imported by every stage) and `status.py` (ls, where, find, kill, render;
   imported by `run.py` only). Buys: a change to an `ls` column stops touching
   the file eight stages import. (synthesis 2, structure 5)
3. **Bring back `train/packing.py` and `train/reference.py`.** Buys: cgen and
   cparam stop being two 600-line near-copies of
   `legacy/pipeline/train/share_data.py`, and the alignment gate gets one
   reference instead of one per method. (synthesis 3, structure 1 and 2)
4. **Split `train/utils/trainer.py`** into `trainer.py`, `tuning.py` and
   `predict.py`. Buys: the prediction step becomes its own program with its own
   resume point, and the LoRA merge stops living inside the loop.
   (synthesis 4, structure 1)
5. **`data/probe_report.py`** as the probe report's home, instead of defining it
   in `eval/utils/probe_eval.py`. Buys: the rule "every format between two
   stages is defined in `data/`" holds without an exception, and `jobs/launch.py`
   reads the report from `data/` rather than from `eval/`. (synthesis 5,
   dependencies P3)
6. **Split each `service.py` into `server.py` and `client.py`.** Buys: the venv
   boundary becomes a file boundary that `selfcheck` can import-test, instead of
   a convention that one stray top-level `import vllm` breaks at night.
   (synthesis 6, structure 9)
7. **Move the model table to `experimental_settings/models.yaml` and serving
   location to `constants/models.yaml`.** Buys: `models/` holds only code, and
   "everything in `experimental_settings/` changes a result" becomes true
   without the two-block convention of Part 6.1. (synthesis 7, structure 7)
8. **`environments/` as a top-level layer.** Buys: the folder sits beside its
   three callers instead of inside `data/`, whose own line already says a new
   environment goes elsewhere. (synthesis 11, structure 8)
9. **Flatten `train/` and `eval/`, name the eval files by the metric**
   (`fire_threshold.py`, `exact_match.py`), and add `data/methods/<m>.py` for the
   per-method example construction and match function. Buys: the
   `train/methods/ctool.py` / `eval/methods/ctool.py` basename collision goes
   away, and the cgen/cparam eval copy collapses into one file.
   (synthesis 12, structure 12, dependencies P2)
10. **`data/check_dataset.py`** for the build gates. Buys: the gates, which are
    edited when a new silent failure is found, stop sharing a file with example
    construction, which is edited for a new method or cut rule. (structure 11)
11. **`jobs/walk.py`** for the stage walk, leaving `run.py` a CLI. Buys: the walk
    stops growing inside the command that parses arguments; today's
    `legacy/pipeline/driver.py` is 1,615 lines of exactly that. (structure 4)
12. **`jobs/watch.py`** if the sampler is kept rather than retired. Buys: the
    verdict engine and the web page keep a home, and the nine CONTEXT.md entries
    stay true. (structure 6, lifecycle B7)
13. **A seventh stage, `replay`, with its own file.** Buys: the offline
    injection line (`legacy/pipeline/inject/replay_inject.py`, 1,521 lines) has
    somewhere to come back to; it is injection over recorded records and fits
    none of the six stages. Retired in this draft. (structure 13)
14. **Rename `Environment.split_args` to `parse_call`.** Buys: the method's name
    would say what Part 4.2 has to explain in a sentence.
15. **Render `RESULTS.md` into `notes/`** with the other three ledgers, instead
    of into `jobs/`. Buys: the four-ledger rule in CLAUDE.md stays literally
    true. (structure 13)
16. **`tests/` files**, deferred by the owner: the four checks the tree names
    (a changed default without a `VERSION` bump, packed loss equals the plain
    loss and a LoRA merge equals full weights on a tiny CPU model, a speculated
    call leaves the world unchanged, two pieces appending at once both land).
    Until they exist, three rules in this document are kept by hand: the default
    rule (Part 3.3), the alignment gate (Part 2.3) and the speculate guarantee
    (Part 4.3).

### 9(c). What this document does not decide

- The hash function's implementation and the exact canonical JSON form: the
  owner's instruction is that keying is implemented last. Only the signature,
  the inputs and the guarantees are fixed here (Part 3).
- The cost of predicting at every cut row for cgen and cparam: the construction
  plan measures it in the smoke, and the fallback is written down but not built.
- Whether `/detokenize` preserves harmony control markers: the contract requires
  the startup check to prove it and refuses to start otherwise (Part 7.1); which
  way the check comes out is a fact to be measured, not a decision.
- The exact instruction-variant texts: `v1` is today's AppWorld system prompt
  (`legacy/envs/collect/run_appworld.py:24-43`); further variants are the owner's
  to write.







