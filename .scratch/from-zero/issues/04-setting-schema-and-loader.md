# 04 the setting schema and its loader

Status: resolved
Blocked by: 01
Spec: .scratch/from-zero/spec.md (sections 1, 2, 3, 4, 5, 7)

## What to do

One Python file: `experimental_settings/schema.py`, plus its `README.md` entry.
Contracts Part 5 (5.1 through 5.7), Part 3 (3.1 through 3.4), Part 2 (2.1, 2.2,
2.3) and 1.5 are the specification; read Part 5 and Part 3 in full.

```
experimental_settings/schema.py   venv: any
  imports: none (repo); [PyYAML, dataclasses, hashlib, re, ast]
  used by: run.py, jobs/launch.py, agent/loop.py, data/build_training_dataset.py,
           train/utils/trainer.py, eval/utils/probe_eval.py, eval/score_run.py,
           eval/method_table.py, models/agent_models/service.py,
           models/probe_models/service.py  (ten; both services take load_frozen only)
  reads:   experimental_settings/*.yaml, models/table.yaml,
           constants/path_outputs.yaml, constants/path_datasets.yaml (the splits
           block of the chosen environment), a run directory's settings.yaml, and
           the VERSION / PROBE_KIND lines and module-level literals of 3.3's
           literal rule — all as source text, never by importing
  writes:  settings.yaml and settings_diff.yaml in a run directory
```

`from __future__ import annotations` at the top. No 3.11+ syntax, no NumPy, no
Polars, **no repo import at all**. The file must import under system `python3`
(3.10.12) as well as all three venv interpreters.

Write it in four passes, in this order — the acceptance is grouped the same way,
so you can run B before writing C:

1. `ROOT`, the dataclasses, `THETA_GRID`, `AXES`, `RETIRED`, `REQUIRED_FIELDS`,
   `PROBE_TEXT_FIELDS`, `STAGES`, `module_version`, `module_literal`.
2. `load` and every refusal of 5.7.
3. `load_frozen` and `run_dir_of`.
4. `fields_of`, `models_of`, `upstream_of`, `versions_of`, `upstream`, `key`,
   `run_dir`, `freeze`.

### 1. Declarations

```python
ROOT = Path(__file__).resolve().parents[1]     # every repo-relative read goes through it
```

**Decision already made (errata):** `ROOT` is the base of every repo-relative
read (`models/table.yaml`, `constants/*.yaml`, a module's source text). That is
also what lets an acceptance command point the loader at a fixture tree.

Dataclasses — fields, types and defaults verbatim from contracts 5.2, with one
`#` comment per field (the "one line" column of 5.2's table). Every mutable
default is a `field(default_factory=...)`.

```python
@dataclass
class Meta:        notes: str = ""; override: list[str] = []
@dataclass
class Data:        env: str = "appworld"; instructions: str = "v1"
@dataclass
class Models:      agent: str = "gpt_oss_120b"; probe: str | None = "qwen3_0pt6b"
                   agent_row: dict | None = None   # read-only, written by the loader (5.2)
                   probe_row: dict | None = None
@dataclass
class Generation:  temperature: float = 1.0; top_p: float | None = None
                   max_step_tokens: int = 8192; stop: list[str] | None = None
                   effort: str | None = None; date: str | None = None
@dataclass
class Sample:      split: list[str] = ["train", "dev", "test"]; seeds: list[int] = [42]
                   tasks: list[str] | None = None; n_tasks: int | None = None
                   max_steps: int = 30; store_token_ids: bool = False
                   pieces: int = 6; replicas: int = 1
@dataclass
class Build:       max_cuts: int = 64; min_think: int = 40; hist_rounds: int = 3
                   probe_result_cap: int = 400; weight_mode: str = "uniform"
                   split_source: str = "env"; split_ratio: list[float] = [0.8, 0.1, 0.1]
                   max_examples: int | None = None; max_abort_frac: float = 0.02
@dataclass
class Probe:       method: str = "ctool"; tuning: str = "full"; lora_r: int = 16
                   lora_alpha: int = 32; lora_dropout: float = 0.05
                   lora_targets: list[str] | None = None
@dataclass
class Predict:     splits: list[str] = ["val", "test"]; cap: int | None = None; max_new: int = 96
@dataclass
class Train:       lr: float = 1.0e-5; epochs: int = 1; warmup_ratio: float = 0.0
                   seed: int = 42; max_len: int = 8192; events_per_mb: int = 4
                   accum: int = 2; grad_ckpt: bool = False; max_steps: int | None = None
                   align_check: bool = True; checkpoint_hours: float = 2.0
                   predict: Predict = Predict()
@dataclass
class Eval:        risk: list[float] = [0.10, 0.05]; theta_grid: list[float] = THETA_GRID
                   bootstrap: int = 1000; bootstrap_seed: int = 42
                   theta_from: str | dict | None = None
@dataclass
class Inject:      split: list[str] = ["test"]; seeds: list[int] = [42]
                   tasks: list[str] | None = None; n_tasks: int | None = None
                   max_steps: int = 30
                   probe_score: str | dict | None = None      # required, REQUIRED_FIELDS
                   probe_gen: str | dict | None = None        # required
                   theta: float | None = None                 # required
                   arm: str = "probe"; format: str = "p1_e1"; fire_nth_cut: int = 0
                   max_inject_per_step: int = 1; max_cuts: int = 64; max_new: int = 96
                   chunk_tokens: int = 64; tail_tokens: int = 1024
                   store_token_ids: bool = True; pieces: int = 6; replicas: int = 1
@dataclass
class Score:       baseline: str | dict | None = None; by_seed: bool = True
```

`THETA_GRID` is the explicit 20-element literal (errata; the default must not be
able to drift): `[0.5, 0.525, 0.55, 0.575, 0.6, 0.625, 0.65, 0.675, 0.7, 0.725,
0.75, 0.775, 0.8, 0.825, 0.85, 0.875, 0.9, 0.925, 0.95, 0.975]`
(`legacy/pipeline/eval/eval_tool.py:51`).

```python
@dataclass
class Setting:
    meta: Meta | None = None
    data: Data | None = None
    models: Models | None = None
    generation: Generation | None = None
    sample: Sample | None = None
    build: Build | None = None
    probe: Probe | None = None
    train: Train | None = None
    eval: Eval | None = None
    inject: Inject | None = None
    score: Score | None = None
    _workflow: list[str] = []      # the file's workflow: line (5.1); never written to settings.yaml
    _debug: bool = False
    _name: str = ""                # the named setting, or "<name>/<field>=<v>,..." for a sweep child
    _file: str = ""                # the workflow file's stem, the first half of a reference
    _stage: str | None = None      # the five below are filled by load_frozen / freeze (1.5)
    _key: str | None = None
    _upstream: dict[str, str] = {}
    _versions: dict[str, int] = {}
    _commit: str | None = None
    _resolved: dict = {}
```

**Which sections a merged setting holds (errata):** `meta`, `data`, `models` and
`generation` always; a stage section when the file's `workflow:` names its stage;
`build` **additionally** on an inject setting (carrying the inherited
`PROBE_TEXT_FIELDS`); everything else `None`, so `cfg.inject is None` is the
presence test 5.1 promises. On a workflow containing `inject`, both
`models.probe` and `models.probe_row` are `None`.

```python
AXES = {
    "data.env":            ("appworld",),
    "data.instructions":   ("v1",),
    "sample.split":        ("train", "dev", "test"),
    "inject.split":        ("train", "dev", "test"),
    "generation.effort":   ("high", "medium", "low"),
    "probe.method":        ("ctool", "cgen", "cparam"),
    "probe.tuning":        ("full", "lora"),
    "inject.format":       ("note", "p1_e1", "p1_e2", "p2_e1", "p2_e2"),
    "inject.arm":          ("probe", "no_probe", "probe_nofill"),
    "build.weight_mode":   ("uniform", "per_event"),
    "build.split_source":  ("env", "hash"),
}
RETIRED: set[tuple[str, str]] = set()          # (axis, value); empty today (3.3)
REQUIRED_FIELDS = ("inject.theta", "inject.probe_score", "inject.probe_gen")
PROBE_TEXT_FIELDS = ("min_think", "hist_rounds", "probe_result_cap")   # 1.7
```

**`STAGES`** — contracts 2.1, 2.2, 2.3, with the cell shape pinned by errata
("Part 2 opening" and "2.1 / 2.2"). Copy this dictionary as written:

```python
STAGES = {
  "sample": {
    "sections": ("data", "models.agent", "generation",
                 "sample.split", "sample.max_steps", "sample.store_token_ids"),
    "models": ("agent",),
    "upstream": (),
    "program": "agent.loop",
    "venv": {"loop": "env", "service_agent": "vllm", "service_probe": "probe"},
    "pieces": (("loop", "pieces", None), ("service_agent", "replicas", None),
               ("service_probe", 1, "render_only")),
    "cards": True,
    "done_writer": "run.py",
    "projection": ("sample.seeds", "sample.tasks", "sample.n_tasks",
                   "sample.pieces", "sample.replicas"),
    "projection_generator": (),
    "versions": ("agent/loop.py", "agent/generate.py", "data/trajectory_record.py",
                 "data/environments/__init__.py", "data/environments/{env}.py",
                 "models/agent_models/{family}.py", "models/agent_models/service.py",
                 "models/probe_models/service.py"),
  },
  "build": {
    "sections": ("data", "build",
                 "sample.split", "sample.tasks", "sample.n_tasks", "sample.seeds"),
    "models": (),
    "upstream": ({"name": "sample", "source": "same", "stage": "sample", "key": "fold"},),
    "program": "data.build_training_dataset",
    "venv": "any",
    "pieces": (("cpu", 1, None),),
    "cards": False,
    "done_writer": "stage",
    "projection": (),
    "projection_generator": (),
    "versions": ("data/build_training_dataset.py", "data/probe_input.py", "data/training_data.py",
                 "data/trajectory_record.py", "data/environments/__init__.py",
                 "data/environments/{env}.py"),
  },
  "train": {
    "sections": ("models.probe", "probe", "train"),
    "models": ("probe",),
    "upstream": ({"name": "build", "source": "same", "stage": "build", "key": "fold"},),
    "program": "train.methods.{method}",
    "venv": "probe",
    "pieces": (("train", 1, None),),
    "cards": True,
    "done_writer": "stage",
    "projection": ("train.checkpoint_hours",),
    "projection_generator": ("data",),
    "versions": ("train/utils/trainer.py", "train/methods/{method}.py",
                 "eval/methods/{method}.py", "data/training_data.py", "data/probe_output.py",
                 "models/probe_models/base.py", "models/probe_models/{backbone}.py"),
  },
  "eval": {
    "sections": ("probe.method", "eval"),
    "models": (),
    "upstream": ({"name": "train", "source": "same", "stage": "train", "key": "fold"},
                 {"name": "theta_from.eval", "source": "ref:eval.theta_from",
                  "stage": "eval", "key": "fold", "when": "generator"}),
    "program": "eval.methods.{method}",
    "venv": "any",
    "pieces": (("cpu", 1, None),),
    "cards": False,
    "done_writer": "stage",
    "projection": (),
    "projection_generator": ("data",),
    "versions": ("eval/utils/probe_eval.py", "eval/methods/{method}.py",
                 "data/probe_output.py"),
  },
  "inject": {
    "sections": ("data", "models.agent", "generation",
                 "build.min_think", "build.hist_rounds", "build.probe_result_cap",
                 "inject.split", "inject.max_steps", "inject.theta", "inject.format",
                 "inject.arm", "inject.fire_nth_cut", "inject.max_inject_per_step",
                 "inject.max_cuts", "inject.max_new", "inject.chunk_tokens",
                 "inject.tail_tokens", "inject.store_token_ids"),
    "models": ("agent",),
    "upstream": ({"name": "probe_score.train", "source": "ref:inject.probe_score",
                  "stage": "train", "key": "fold"},
                 {"name": "probe_score.eval", "source": "ref:inject.probe_score",
                  "stage": "eval", "key": "carry"},
                 {"name": "probe_gen.train", "source": "ref:inject.probe_gen",
                  "stage": "train", "key": "fold"}),
    "program": "agent.loop",
    "venv": {"loop": "env", "service_agent": "vllm", "service_probe": "probe"},
    "pieces": (("loop", "pieces", None), ("service_agent", "replicas", None),
               ("service_probe", 1, None)),
    "cards": True,
    "done_writer": "run.py",
    "projection": ("inject.seeds", "inject.tasks", "inject.n_tasks",
                   "inject.pieces", "inject.replicas"),
    "projection_generator": (),
    "versions": ("agent/loop.py", "agent/generate.py", "agent/inject.py",
                 "agent/inject_format.py", "data/probe_input.py", "data/trajectory_record.py",
                 "data/environments/__init__.py", "data/environments/{env}.py",
                 "models/agent_models/{family}.py", "models/agent_models/service.py",
                 "models/probe_models/base.py", "models/probe_models/service.py",
                 "eval/utils/probe_eval.py", "eval/methods/{probe_score_method}.py"),
  },
  "score": {
    "sections": ("score",
                 "sample.split", "sample.tasks", "sample.n_tasks", "sample.seeds",
                 "inject.split", "inject.tasks", "inject.n_tasks", "inject.seeds"),
    "models": (),
    "upstream": ({"name": "inject", "source": "same", "stage": "inject",
                  "key": "fold", "when": "in_workflow"},
                 {"name": "sample", "source": "same", "stage": "sample",
                  "key": "fold", "when": "in_workflow"},
                 {"name": "baseline.sample", "source": "ref:score.baseline",
                  "stage": "sample", "key": "fold", "when": "set"}),
    "program": "eval.score_run",
    "venv": "any",
    "pieces": (("cpu", 1, None),),
    "cards": False,
    "done_writer": "stage",
    "projection": ("data",),
    "projection_generator": (),
    "versions": ("eval/score_run.py", "data/trajectory_record.py"),
  },
}
```

Placeholders in `versions` and `program` are substituted from the setting:
`{env}` = `data.env`, `{family}` = `models.agent_row["family"]`, `{backbone}` =
`models.probe_row["family"]`, `{method}` = `probe.method`,
`{probe_score_method}` = the `probe.method` of the setting `inject.probe_score`
resolves to. A field of a section that is `None` contributes nothing — that is
how `score`'s one entry covers both workflows.

### 2. The names the file offers

```python
def load(workflow_file: Path, setting_name: str, *,
         debug: bool, overrides: dict) -> list[Setting]          # 5.1
def load_frozen(run_dir: Path) -> Setting                         # 5.1
def freeze(setting: Setting, stage: str, run_dir: Path, resolved: dict,
           commit: str) -> None                                   # 5.1
def key(stage: str, setting: Setting) -> str                      # 3.1, 12 lowercase hex
def run_dir(stage: str, setting: Setting) -> Path                 # 3.1
def run_dir_of(stage: str, key: str, *, debug: bool) -> Path      # 3.1
def upstream(stage: str, setting: Setting) -> dict[str, str]      # errata: run.py needs the map before freeze
def module_version(rel_path: str) -> int                          # 3.3's text reader
def module_literal(rel_path: str, name: str)                      # ast.literal_eval of a column-zero literal
def fields_of(stage: str, setting: Setting) -> dict               # the "fields" block of 3.3, = settings_diff.yaml
def models_of(stage: str, setting: Setting) -> dict               # the "models" block of 3.3
def upstream_of(stage: str, setting: Setting) -> dict             # name -> key, per the stage table's upstream cell
def versions_of(stage: str, setting: Setting) -> dict             # module path -> VERSION, read as source text
```

`upstream(stage, setting)` is the map `freeze` writes into `_upstream`, offered
separately because `run.py` needs it **before** `freeze` for 2.5's two inject
gates and 5.4's temperature read (errata). `freeze` calls it itself. Nothing
outside this file calls `fields_of`, `models_of`, `upstream_of`, `versions_of`,
`module_version` or `module_literal` except `run.py`, which calls
`module_version` for 2.5's inject version gate.

### 3. Behaviour, by contract section

- **`load`**: the merge order of 5.7 — defaults -> `common:` -> the named setting
  -> sweep expansion (5.5) -> `debug.yaml` (5.6) -> command-line overrides —
  with sections merged **per field** and a list field **replaced**, never
  appended (errata). The debug overlay applies only to the sections this file's
  `workflow:` line names. References are resolved after the overrides (5.4) with
  the per-group inheritance and agreement rule. `meta.override` is checked after
  step 5. The model table's `result:` block is expanded last, immediately before
  keying (5.7, 6.1). Returns a **list**: one element, or the sweep children in
  name order. A sweep child's `_name` is `"<name>/<field>=<repr(value)>,..."`
  (5.5) and a child name is accepted anywhere a setting name is.
- **Where `generation.{stop, effort, date}` are resolved** (errata, and `C1` pins
  it): `load` resolves all three onto the `Setting`, right after the model-row
  expansion, reading `STOP`, `DEFAULT_EFFORT` and `DEFAULT_DATE` out of
  `models/agent_models/<the agent row's family>.py` with `module_literal` — never
  by importing. `key` then diffs the **resolved** value against what the same
  family would give, per 3.3's second pre-diff resolution, so a setting that
  states the family's own value keys identically to one that leaves it null.
  **`probe.lora_targets` is the deliberate exception**: it is resolved inside
  `key` only and stays `None` on the dataclass. The reason for the asymmetry is
  who reads the frozen file: `freeze` projects the whole `generation` section and
  `models/agent_models/service.py`, `agent/generate.py` and `agent/loop.py` read
  `cfg.generation.date`, `.effort` and `.stop` off `settings.yaml` at run time, so
  a null there would reach a server; **no stage program ever reads
  `probe.lora_targets` off the frozen file** — `models/probe_models/base.py` takes
  the backbone module's `LORA_TARGETS` itself when the field is null.
- **`overrides`** is `dict[str, str]`, dotted field name to the raw command-line
  string, each parsed with `yaml.safe_load` (errata), so a reference can be
  pinned from the command line:
  `inject.probe_score={key: {train: <hex>, eval: <hex>}}`. A
  `<workflow>/<setting>` reference resolves against `workflow_file.parent`.
- **Every refusal of 5.7**, each naming the offending field in its message, plus
  two the errata add: a **type check** (a value whose type does not match its
  field's declared type is refused, naming the field, the declared type and the
  value — PyYAML parses `1e-5` as a *string* and `1.0e-5` as a float), and the
  **required-field check** (`REQUIRED_FIELDS` default to `None` and a `None` at
  the end of the merge is refused, naming the field).
- **The section-to-stage map** (errata): `sample`->sample, `build`->build,
  `probe`->train, `train`->train, `eval`->eval, `inject`->inject,
  `score`->score. `meta`, `data`, `models` and `generation` are never stage
  sections.
- **`load_frozen`**: parse `settings.yaml` against the dataclasses, fill the `_`
  block, **re-merge nothing and re-resolve nothing** (2.6); refuse a field the
  schema has since removed, naming the field and the run directory (5.7).
- **`key`**: the payload of 3.3 — `{"stage", "fields", "models", "upstream",
  "versions", "debug"}` — canonicalised as
  `json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)`,
  encoded UTF-8, hashed with `sha256`, first **12 lowercase hex** characters
  (errata; 3.3 names `canonical_json` without defining it). The four pre-diff
  resolutions of 3.3 apply in the order given; the `inject.probe_score` **eval**
  key is carried, not folded (`"key": "carry"` in the table), and in its place
  the `VERSION`s of `eval/utils/probe_eval.py` and the referenced setting's
  `eval/methods/<m>.py` are folded (2.1, 2.2). The four reference fields never
  enter `fields`. Versions are read as source text.
- **`run_dir` / `run_dir_of`**: `<root>/<stage>/<key>` or
  `<root>/<debug_subdir>/<stage>/<key>`, both roots from
  `constants/path_outputs.yaml` (3.4). **`key` and `run_dir` never touch the
  output tree** (3.2 rule 2) and never create a directory.
- **`freeze`**: the stage projection of 3.4 — the stage table's `sections` plus
  `projection` plus `projection_generator` when the method's `PROBE_KIND` is
  `generator` plus an inject run's inherited `PROBE_TEXT_FIELDS` — then the `_`
  block of 1.5 (`_stage`, `_key`, `_upstream`, `_versions`, `_debug`, `_commit`,
  `_resolved`; **never `_workflow`**). Both files are written through a temporary
  name in the same directory and renamed. The collision check runs over
  `settings_diff.yaml`, and the non-keyed request fields merge per field:
  `seeds` is the ordered union, a null `tasks` absorbs, `pieces` and `replicas`
  take the new launch's values.
- **`module_version` / `module_literal`** (3.3's literal rule): the one
  **column-zero** assignment, exactly once, read with `ast` over the parsed
  source and `ast.literal_eval`d — **never by importing**. Raise, naming the
  file, on zero matches and on more than one. An indented `VERSION = VERSION`
  inside a class body is not a match.

### Legacy sources

There is no key, no run-directory naming and no stage table in the old tree; what
ports is the merge discipline and the numbers.

| what | where |
|---|---|
| merge order, "explicit beats preset beats default", the refusal on a missing required value | `legacy/preset_loader.py:116-148`, `:66-100` |
| the generation defaults (temperature 1.0, max_tokens 8192, effort high, date 2026-08-06) | `legacy/configs/presets/default.json` (`client` block) |
| the `train` defaults (max_len 8192, events_per_mb 4, accum 2, epochs 1, grad_ckpt) | `legacy/pipeline/train/train_causal_share.py:931-1005` |
| `train.lr` 1.0e-5 and `train.seed` 42 | `legacy/pipeline/train/train_causal_tool.py:89-91` |
| the `build` defaults (min_think 40, hist_rounds 3, probe_result_cap 400, max_cuts 64, weight_mode) | `legacy/pipeline/annotate/rules.py:20-22`, `legacy/pipeline/annotate/build.py:18,205`, `legacy/pipeline/configs/np821_gptoss.json` |
| the `eval` defaults (the theta grid, risk 0.05) | `legacy/pipeline/eval/eval_tool.py:51,279`, `eval_causal_call.py:500` |
| the `inject` defaults (chunk_tokens 64, tail_tokens 1024, max_inject_per_step 1, fire_nth_cut 0) | `legacy/pipeline/inject/live_appworld.py:617-634` |
| the stage/registry idea `STAGES` replaces | `legacy/run.py:76-110` (`CELLS`, `EVAL_CELLS`) |

**Not ported:** presets as a concept (`legacy/preset_loader.py`,
`legacy/serve_preset.py`, `legacy/sweep_preset.py`); `CLIENT_KEYS`/`SERVER_KEYS`
and the `NEW1_PRESET_JSON` environment channel; `legacy/run.py`'s
`TASKS`/`RECIPES` registry and its `handoff` flag; OmegaConf and `${a.b}`
interpolation; the `--align-tol` family of flags
(`train_causal_share.py:989-1005`) — the contract has one gate at `1e-4` under
one boolean, `train.align_check`.

## Acceptance

Run from the repo root and paste the real output.

```bash
PR=/home/y-guo/reproduce/new1/external/probe-env/bin/python
AW=/home/y-guo/reproduce/new1/external/appworld/venv/bin/python
VL=/home/y-guo/reproduce/new1/external/vllm-env/bin/python
```

### The fixture (used by every C and D command)

One script, written once and reused. It builds a complete fake repo root so the
loader and `key` can be exercised before the other folders land; `schema.ROOT` is
repointed at it, which is exactly what `ROOT` exists for.

```bash
cat > /tmp/mkfix.sh <<'SH'
set -eu
FIX=$(mktemp -d); export FIX
mkdir -p "$FIX"/{constants,experimental_settings,models/agent_models,models/probe_models,data/environments,agent,train/utils,train/methods,eval/utils,eval/methods,outputs}
cp constants/*.yaml "$FIX/constants/"
cp experimental_settings/*.yaml "$FIX/experimental_settings/"
sed -i "s|^root:.*|root: $FIX/outputs|" "$FIX/constants/path_outputs.yaml"
cat > "$FIX/models/table.yaml" <<'Y'
gpt_oss_120b:
  role: agent
  family: gptoss
  result: {weights: gpt-oss-120b, dtype: auto, quantization: null,
           max_model_len: 131072, served_model_name: gpt-oss-120b,
           env_result: {VLLM_USE_FLASHINFER_SAMPLER: "0"}, extra_flags: ""}
  serving: {host: tokyo108, port: 8103, gpu_memory_utilization: 0.92,
            tensor_parallel_size: 1, env: {}}
qwen3_0pt6b:
  role: probe
  family: qwen
  result: {weights: qwen3-0.6b-base, dtype: float32}
  serving: {}
Y
cat > "$FIX/models/agent_models/gptoss.py" <<'P'
VERSION = 1
NAME = "gptoss"
STOP = ["<|return|>"]
EFFORTS = ("high", "medium", "low")
DEFAULT_EFFORT = "high"
DEFAULT_DATE = "2026-08-06"
P
cat > "$FIX/models/probe_models/qwen.py" <<'P'
VERSION = 1
DTYPE = "bfloat16"
LORA_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj"]
HEAD_LAYER = "last_hidden_state"
P
cat > "$FIX/data/environments/appworld.py" <<'P'
VERSION = 1
INSTRUCTIONS = {"v1": "developer message v1"}
SPLIT_ROLE = {"train": "train", "dev": "val", "test": "test"}
P
for f in data/environments/__init__.py data/trajectory_record.py data/training_data.py \
         data/probe_output.py data/probe_input.py data/build_training_dataset.py \
         agent/loop.py agent/generate.py agent/inject.py agent/inject_format.py \
         models/agent_models/service.py models/probe_models/base.py \
         models/probe_models/service.py train/utils/trainer.py \
         eval/utils/probe_eval.py eval/score_run.py; do
  printf 'VERSION = 1\n' > "$FIX/$f"
done
for m in ctool cgen cparam; do
  kind=classifier; po=False
  [ "$m" = ctool ] || kind=generator
  [ "$m" = cparam ] && po=True || true
  printf 'VERSION = 1\nPROBE_KIND = "%s"\nCHECKPOINT_META = {"call_sep": "\\n[CALL] ", "param_only": %s}\n' \
         "$kind" "$po" > "$FIX/train/methods/$m.py"
  printf 'VERSION = 1\nPROBE_KIND = "%s"\n' "$kind" > "$FIX/eval/methods/$m.py"
done
echo "$FIX"
SH
bash /tmp/mkfix.sh
```
Expected: one line, the fixture directory path. Every later command does
`FIX=$(bash /tmp/mkfix.sh)` and then, inside python,
`import experimental_settings.schema as S; S.ROOT = Path(FIX)`.

### B — the declarations

**B1 — imports under all four interpreters, and no repo import.**
```bash
for P in python3 "$PR" "$AW" "$VL"; do
  $P -c "import experimental_settings.schema as S; print(S.__name__, len(S.STAGES), S.PROBE_TEXT_FIELDS)"
done
python3 -c "
import ast
t = ast.parse(open('experimental_settings/schema.py').read())
mods = set()
for n in ast.walk(t):
    if isinstance(n, ast.Import): mods |= {a.name.split('.')[0] for a in n.names}
    if isinstance(n, ast.ImportFrom) and n.module: mods.add(n.module.split('.')[0])
repo = {'data','models','agent','train','eval','jobs','constants','run'}
assert not (mods & repo), mods & repo
print(sorted(mods))"
```
Expected: four lines
`experimental_settings.schema 6 ('min_think', 'hist_rounds', 'probe_result_cap')`,
then a module list drawn only from the standard library plus `yaml`, with no repo
package.

**B2 — the defaults equal the contract table.**
```bash
python3 -c "
import experimental_settings.schema as S
g, s, b, p, t, e, i = S.Generation(), S.Sample(), S.Build(), S.Probe(), S.Train(), S.Eval(), S.Inject()
assert (g.temperature, g.max_step_tokens, g.top_p, g.stop, g.effort, g.date) == (1.0, 8192, None, None, None, None)
assert (s.split, s.seeds, s.max_steps, s.pieces, s.replicas) == (['train','dev','test'], [42], 30, 6, 1)
assert (b.max_cuts, b.min_think, b.hist_rounds, b.probe_result_cap, b.weight_mode, b.split_source) == (64, 40, 3, 400, 'uniform', 'env')
assert (p.method, p.tuning, p.lora_r, p.lora_alpha, p.lora_dropout) == ('ctool','full',16,32,0.05)
assert (t.lr, t.epochs, t.max_len, t.events_per_mb, t.accum, t.seed, t.align_check, t.checkpoint_hours) == (1e-5,1,8192,4,2,42,True,2.0)
assert t.predict.splits == ['val','test'] and t.predict.max_new == 96
assert (e.risk, e.bootstrap, e.bootstrap_seed) == ([0.10,0.05], 1000, 42)
assert len(e.theta_grid) == 20 and e.theta_grid[0] == 0.5 and e.theta_grid[-1] == 0.975
assert (i.split, i.arm, i.format, i.max_cuts, i.max_new, i.chunk_tokens, i.tail_tokens, i.store_token_ids) == (['test'],'probe','p1_e1',64,96,64,1024,True)
assert S.Sample().seeds is not S.Sample().seeds
print('defaults ok')"
```
Expected: `defaults ok`.

**B3 — `STAGES` has the six stages and the cell shape.**
```bash
python3 -c "
import experimental_settings.schema as S
assert list(S.STAGES) == ['sample','build','train','eval','inject','score']
CELLS = {'sections','models','upstream','program','venv','pieces','cards','done_writer','projection','projection_generator','versions'}
for st, e in S.STAGES.items():
    assert set(e) == CELLS, (st, set(e) ^ CELLS)
    for u in e['upstream']:
        assert u['key'] in ('fold','carry') and (u['source'] == 'same' or u['source'].startswith('ref:')), (st, u)
print([(st, len(e['versions']), e['cards'], e['venv'] if isinstance(e['venv'],str) else 'map') for st, e in S.STAGES.items()])
print('carry:', [(st,u['name']) for st,e in S.STAGES.items() for u in e['upstream'] if u['key']=='carry'])"
```
Expected: the tuple list showing `('sample', 8, True, 'map')`,
`('build', 6, False, 'any')`, `('train', 7, True, 'probe')`,
`('eval', 3, False, 'any')`, `('inject', 14, True, 'map')`,
`('score', 2, False, 'any')`, then
`carry: [('inject', 'probe_score.eval')]`.

**B4 — the axis literals agree with what is on disk.** Rows whose directory does
not exist yet are skipped and the command says so.
```bash
python3 -c "
import ast, glob, os, yaml
import experimental_settings.schema as S
def lit(path, name):
    for n in ast.parse(open(path).read()).body:
        if isinstance(n, ast.Assign) and getattr(n.targets[0],'id',None) == name:
            return ast.literal_eval(n.value)
    raise SystemExit(f'{path}: no column-zero {name}')
if os.path.isdir('data/environments'):
    envs = {os.path.basename(f)[:-3] for f in glob.glob('data/environments/*.py')} - {'__init__'}
    assert set(S.AXES['data.env']) == envs, (S.AXES['data.env'], envs)
    ins, spl = set(), set()
    for e in envs:
        ins |= set(lit(f'data/environments/{e}.py','INSTRUCTIONS'))
        spl |= set(lit(f'data/environments/{e}.py','SPLIT_ROLE'))
    assert set(S.AXES['data.instructions']) == ins and set(S.AXES['sample.split']) == spl
if os.path.isdir('train/methods') and os.path.isdir('eval/methods'):
    tr = {os.path.basename(f)[:-3] for f in glob.glob('train/methods/*.py')}
    ev = {os.path.basename(f)[:-3] for f in glob.glob('eval/methods/*.py')}
    assert set(S.AXES['probe.method']) == tr & ev, (tr, ev)
if os.path.exists('agent/inject_format.py'):
    assert set(S.AXES['inject.format']) == set(lit('agent/inject_format.py','FORMATS'))
if os.path.exists('agent/inject.py'):
    assert set(S.AXES['inject.arm']) == set(lit('agent/inject.py','ARMS'))
d = yaml.safe_load(open('constants/path_datasets.yaml'))
blocks = {k: v for k, v in d.items() if k != 'venvs'}
assert set(S.AXES['data.env']) <= set(blocks)
u = set().union(*[set(v['splits']) for v in blocks.values()])
assert set(S.AXES['sample.split']) == u == set(S.AXES['inject.split'])
print('axis checks that could run:', 'all' if os.path.isdir('data/environments') else 'constants only')"
```
Expected in this wave: `axis checks that could run: constants only`, exit 0.

**B5 — the two source-text readers.**
```bash
D=$(mktemp -d); printf 'VERSION = 7\nSTOP = ["<|return|>"]\nclass C:\n    VERSION = VERSION\n' > $D/m.py
printf 'VERSION = 1\nVERSION = 2\n' > $D/two.py; printf 'x = 1\n' > $D/none.py
python3 -c "
from pathlib import Path
import experimental_settings.schema as S
S.ROOT = Path('$D')
print(S.module_version('m.py'), S.module_literal('m.py','STOP'))
for f, why in [('two.py','two matches'), ('none.py','no match')]:
    try: S.module_version(f); print('NO RAISE', f)
    except Exception as ex: print(why, '->', type(ex).__name__, str(ex)[:60])"
```
Expected: `7 ['<|return|>']`, then two lines showing a raise whose message names
the file, for both the two-match and the zero-match case.

### C — the loader

**C1 — the flagship load, with the model row expanded and the nulls resolved.**
```bash
FIX=$(bash /tmp/mkfix.sh); python3 -c "
from pathlib import Path
import experimental_settings.schema as S
S.ROOT = Path('$FIX')
cs = S.load(Path('$FIX/experimental_settings/train_probe.yaml'), 'ctool_qwen3_0pt6b', debug=False, overrides={})
assert len(cs) == 1
c = cs[0]
print(c._name, c._workflow, c._debug)
print(c.data.env, c.data.instructions, c.models.agent, c.models.probe)
print(c.models.agent_row['family'], sorted(c.models.agent_row)[:4])
print(c.generation.stop, c.generation.effort, c.generation.date)
print(c.probe.method, c.probe.lora_targets, c.train.lr, c.train.predict.cap)
print('inject is None:', c.inject is None, '| build present:', c.build is not None)"
```
Expected:
```
ctool_qwen3_0pt6b ['sample', 'build', 'train', 'eval'] False
appworld v1 gpt_oss_120b qwen3_0pt6b
gptoss ['dtype', 'env_result', 'extra_flags', 'family']
['<|return|>'] high 2026-08-06
ctool None 1e-05 None
inject is None: True | build present: True
```
`agent_row` must contain `role`, `family` and every `result:` column and **no**
`serving:` column. `probe.lora_targets` stays `None` on the Setting — 3.3's
fourth resolution happens inside `key`, not on the dataclass.

**C2 — the debug overlay is sizes only and stage-scoped.**
```bash
FIX=$(bash /tmp/mkfix.sh); python3 -c "
from pathlib import Path
import experimental_settings.schema as S
S.ROOT = Path('$FIX')
c = S.load(Path('$FIX/experimental_settings/train_probe.yaml'), 'ctool_qwen3_0pt6b', debug=True, overrides={})[0]
print(c._debug, c.sample.n_tasks, c.sample.pieces, c.sample.max_steps, c.build.max_cuts, c.build.max_examples, c.train.max_steps, c.train.predict.cap, c.eval.bootstrap)
b = S.load(Path('$FIX/experimental_settings/baseline.yaml'), 'gpt_oss_120b_appworld', debug=True, overrides={})[0]
print(b.sample.n_tasks, b.build, b.train, b.inject)"
```
Expected: `True 3 1 6 8 64 20 100 50`, then `3 None None None`.

**C3 — overrides and the sweep.**
```bash
FIX=$(bash /tmp/mkfix.sh); python3 -c "
from pathlib import Path
import experimental_settings.schema as S
S.ROOT = Path('$FIX')
c = S.load(Path('$FIX/experimental_settings/train_probe.yaml'), 'ctool_qwen3_0pt6b', debug=False,
           overrides={'train.lr': '3.0e-4', 'probe.tuning': 'lora', 'sample.seeds': '[42, 67]'})[0]
print(c.train.lr, c.probe.tuning, c.sample.seeds)
import yaml, pathlib
p = pathlib.Path('$FIX/experimental_settings/train_probe.yaml')
d = yaml.safe_load(p.read_text()); d['ctool_qwen3_0pt6b']['sweep'] = {'train.lr': [1.0e-4, 3.0e-4], 'train.seed': [42, 67]}
p.write_text(yaml.safe_dump(d))
cs = S.load(p, 'ctool_qwen3_0pt6b', debug=False, overrides={})
print(len(cs)); print([x._name for x in cs]); print([x.train.lr for x in cs])
one = S.load(p, 'ctool_qwen3_0pt6b/train.lr=0.0003,train.seed=67', debug=False, overrides={})[0]
print(one._name, one.train.lr, one.train.seed)"
```
Expected:
```
0.0003 lora [42, 67]
4
['ctool_qwen3_0pt6b/train.lr=0.0001,train.seed=42', 'ctool_qwen3_0pt6b/train.lr=0.0001,train.seed=67', 'ctool_qwen3_0pt6b/train.lr=0.0003,train.seed=42', 'ctool_qwen3_0pt6b/train.lr=0.0003,train.seed=67']
[0.0001, 0.0001, 0.0003, 0.0003]
ctool_qwen3_0pt6b/train.lr=0.0003,train.seed=67 0.0003 67
```

**C4 — each refusal of 5.7 fires and names the field.** Every line must read
`REFUSED` and every message must name the field in the list below it.
```bash
FIX=$(bash /tmp/mkfix.sh); python3 - "$FIX" <<'PY'
import sys, yaml
from pathlib import Path
import experimental_settings.schema as S
FIX = Path(sys.argv[1]); S.ROOT = FIX
tp = FIX / 'experimental_settings/train_probe.yaml'
inj = FIX / 'experimental_settings/inject.yaml'
base = yaml.safe_load(tp.read_text()); binj = yaml.safe_load(inj.read_text())
def run(label, doc, path, name, **kw):
    path.write_text(yaml.safe_dump(doc))
    try:
        S.load(path, name, debug=kw.get('debug', False), overrides=kw.get('overrides', {}))
        print(f'{label}: NOT REFUSED')
    except Exception as ex:
        print(f'{label}: REFUSED {type(ex).__name__}: {str(ex)[:90]}')
def d(mut):
    import copy; x = copy.deepcopy(base); mut(x); return x
def j(mut):
    import copy; x = copy.deepcopy(binj); mut(x); return x
run('unknown key',      d(lambda x: x['ctool_qwen3_0pt6b']['train'].__setitem__('lrr', 1.0)), tp, 'ctool_qwen3_0pt6b')
run('off-axis value',   d(lambda x: x['ctool_qwen3_0pt6b']['probe'].__setitem__('method', 'ctoool')), tp, 'ctool_qwen3_0pt6b')
run('bad instructions', d(lambda x: x['common']['data'].__setitem__('instructions', 'v9')), tp, 'ctool_qwen3_0pt6b')
run('bad split',        d(lambda x: x['common']['sample'].__setitem__('split', ['holdout'])), tp, 'ctool_qwen3_0pt6b')
run('wrong role',       d(lambda x: x['ctool_qwen3_0pt6b']['models'].__setitem__('probe', 'gpt_oss_120b')), tp, 'ctool_qwen3_0pt6b')
run('bad effort',       d(lambda x: x['common'].__setitem__('generation', {'effort': 'ultra'})), tp, 'ctool_qwen3_0pt6b')
run('section not in workflow', d(lambda x: x['ctool_qwen3_0pt6b'].__setitem__('inject', {'theta': 0.5})), tp, 'ctool_qwen3_0pt6b')
run('type mismatch',    d(lambda x: x['ctool_qwen3_0pt6b']['train'].__setitem__('lr', '1e-5')), tp, 'ctool_qwen3_0pt6b')
run('sweep over debug field', d(lambda x: x['ctool_qwen3_0pt6b'].__setitem__('sweep', {'train.max_steps': [10, 20]})), tp, 'ctool_qwen3_0pt6b', debug=True)
run('override of swept field', d(lambda x: x['ctool_qwen3_0pt6b'].__setitem__('sweep', {'train.lr': [1.0e-4, 3.0e-4]})), tp, 'ctool_qwen3_0pt6b', overrides={'train.lr': '2.0e-4'})
run('missing reference', d(lambda x: x['cgen_qwen3_0pt6b']['eval'].__setitem__('theta_from', 'train_probe/nope')), tp, 'cgen_qwen3_0pt6b')
run('generator without theta_from', d(lambda x: x['cgen_qwen3_0pt6b']['eval'].pop('theta_from')), tp, 'cgen_qwen3_0pt6b')
run('probe section under inject', j(lambda x: x['probe_p1_e1_theta_0pt80'].__setitem__('probe', {'tuning': 'lora'})), inj, 'probe_p1_e1_theta_0pt80')
run('models.probe under inject',   j(lambda x: x['common']['models'].__setitem__('probe', 'qwen3_0pt6b')), inj, 'probe_p1_e1_theta_0pt80')
run('theta unset',      j(lambda x: x['probe_p1_e1_theta_0pt80']['inject'].pop('theta')), inj, 'probe_p1_e1_theta_0pt80')
run('probe_gen is a param-only method', j(lambda x: x['probe_p1_e1_theta_0pt80']['inject'].__setitem__('probe_gen', 'train_probe/cparam_qwen3_0pt6b')), inj, 'probe_p1_e1_theta_0pt80')
run('fire_nth_cut under no_probe', j(lambda x: x['no_probe_p1_e1_theta_0pt80']['inject'].__setitem__('fire_nth_cut', 3)), inj, 'no_probe_p1_e1_theta_0pt80')
run('baseline seeds not a superset', j(lambda x: x['probe_p1_e1_theta_0pt80']['inject'].__setitem__('seeds', [42, 67])), inj, 'probe_p1_e1_theta_0pt80')
PY
```
Expected: 18 lines, every one `REFUSED`, each message naming, in order:
`train.lrr`, `probe.method`, `data.instructions`, `sample.split`, `models.probe`,
`generation.effort`, `inject`, `train.lr`, `train.max_steps`, `train.lr`,
`eval.theta_from`, `eval.theta_from`, `probe`, `models.probe`, `inject.theta`,
`inject.probe_gen`, `inject.fire_nth_cut`, `score.baseline`.

**C5 — inheritance and its per-group scope (5.4).**
```bash
FIX=$(bash /tmp/mkfix.sh); python3 - "$FIX" <<'PY'
import sys, yaml
from pathlib import Path
import experimental_settings.schema as S
FIX = Path(sys.argv[1]); S.ROOT = FIX
inj = FIX / 'experimental_settings/inject.yaml'
tp = FIX / 'experimental_settings/train_probe.yaml'
c = S.load(inj, 'probe_p1_e1_theta_0pt80', debug=False, overrides={})[0]
print('inherited build fields:', {f: getattr(c.build, f) for f in S.PROBE_TEXT_FIELDS})
print('probe row absent:', c.models.probe is None and c.models.probe_row is None)
d = yaml.safe_load(tp.read_text()); d['common']['build'] = {'hist_rounds': 5}
tp.write_text(yaml.safe_dump(d))
c2 = S.load(inj, 'probe_p1_e1_theta_0pt80', debug=False, overrides={})[0]
print('inherited after the build edit:', c2.build.hist_rounds)
d2 = yaml.safe_load(inj.read_text()); d2['probe_p1_e1_theta_0pt80']['data'] = {'instructions': 'v1', 'env': 'appworld'}
d2['probe_p1_e1_theta_0pt80']['generation'] = {'temperature': 0.7}
inj.write_text(yaml.safe_dump(d2))
try:
    S.load(inj, 'probe_p1_e1_theta_0pt80', debug=False, overrides={}); print('stated-differently: NOT REFUSED')
except Exception as ex: print('stated-differently: REFUSED', str(ex)[:90])
d2['probe_p1_e1_theta_0pt80']['meta'] = {'override': ['generation.temperature']}
inj.write_text(yaml.safe_dump(d2))
c3 = S.load(inj, 'probe_p1_e1_theta_0pt80', debug=False, overrides={})[0]
print('with meta.override:', c3.generation.temperature)
PY
```
Expected:
```
inherited build fields: {'min_think': 40, 'hist_rounds': 3, 'probe_result_cap': 400}
probe row absent: True
inherited after the build edit: 5
stated-differently: REFUSED ... generation.temperature ...
with meta.override: 0.7
```
The `score.baseline` reference into `baseline.yaml` (whose workflow has no
`build` stage) must **not** be consulted for the `build` group — that is 5.4's
scoping and it is what makes the third line possible at all.

### D — keys, the run directory, freeze

**D1 — the key's shape and the 3.2 guarantees.**
```bash
FIX=$(bash /tmp/mkfix.sh); python3 - "$FIX" <<'PY'
import sys, re
from pathlib import Path
import experimental_settings.schema as S
FIX = Path(sys.argv[1]); S.ROOT = FIX
tp = FIX / 'experimental_settings/train_probe.yaml'
c = S.load(tp, 'ctool_qwen3_0pt6b', debug=False, overrides={})[0]
k = {st: S.key(st, c) for st in ('sample', 'build', 'train', 'eval')}
for st, v in k.items():
    assert re.fullmatch(r'[0-9a-f]{12}', v), (st, v)
print(k)
print('determinism:', all(S.key(st, S.load(tp, 'ctool_qwen3_0pt6b', debug=False, overrides={})[0]) == v for st, v in k.items()))
d = S.load(tp, 'ctool_qwen3_0pt6b', debug=True, overrides={})[0]
print('debug separates:', S.key('train', d) != k['train'])
n = S.load(tp, 'ctool_qwen3_0pt6b', debug=False, overrides={'meta.notes': 'anything at all'})[0]
print('notes insensitive:', S.key('train', n) == k['train'])
lr = S.load(tp, 'ctool_qwen3_0pt6b', debug=False, overrides={'train.lr': '1.0e-5'})[0]
print('default restated == unset:', S.key('train', lr) == k['train'])
lr2 = S.load(tp, 'ctool_qwen3_0pt6b', debug=False, overrides={'train.lr': '3.0e-4'})[0]
print('lr moves train, not sample/build:', S.key('train', lr2) != k['train'],
      S.key('sample', lr2) == k['sample'], S.key('build', lr2) == k['build'])
ev = S.load(tp, 'ctool_qwen3_0pt6b', debug=False, overrides={'eval.risk': '[0.2]'})[0]
print('eval.risk moves eval only:', S.key('eval', ev) != k['eval'], S.key('train', ev) == k['train'])
print('fields block:', sorted(S.fields_of('train', c)))
print('models block:', sorted(S.models_of('train', c)), sorted(S.models_of('build', c)))
print('upstream block:', S.upstream_of('build', c), S.upstream_of('sample', c))
PY
```
Expected: four 12-hex keys; then `determinism: True`, `debug separates: True`,
`notes insensitive: True`, `default restated == unset: True`,
`lr moves train, not sample/build: True True True`,
`eval.risk moves eval only: True True`; a `fields block` holding only fields that
differ from their defaults; `models block: ['probe'] []`;
`upstream block: {'sample': '<12 hex>'} {}`.

**D2 — the `VERSION` fold and the one carve-out.**
```bash
FIX=$(bash /tmp/mkfix.sh); python3 - "$FIX" <<'PY'
import sys
from pathlib import Path
import experimental_settings.schema as S
FIX = Path(sys.argv[1]); S.ROOT = FIX
tp, inj = FIX/'experimental_settings/train_probe.yaml', FIX/'experimental_settings/inject.yaml'
c = S.load(tp, 'ctool_qwen3_0pt6b', debug=False, overrides={})[0]
print(sorted(S.versions_of('train', c)))
i = S.load(inj, 'probe_p1_e1_theta_0pt80', debug=False, overrides={})[0]
print(sorted(S.upstream_of('inject', i)))
k0 = S.key('inject', i)
(FIX/'eval/utils/probe_eval.py').write_text('VERSION = 2\n')
i2 = S.load(inj, 'probe_p1_e1_theta_0pt80', debug=False, overrides={})[0]
print('probe_eval VERSION moves the inject key:', S.key('inject', i2) != k0)
(FIX/'train/utils/trainer.py').write_text('VERSION = 2\n')
c2 = S.load(tp, 'ctool_qwen3_0pt6b', debug=False, overrides={})[0]
print('trainer VERSION moves train, not build:', S.key('train', c2) != S.key('train', c), S.key('build', c2) == S.key('build', c))
PY
```
Expected: the seven module paths of the train version list with the placeholders
substituted (`train/methods/ctool.py`, `eval/methods/ctool.py`,
`models/probe_models/qwen.py`, …); then
`['probe_gen.train', 'probe_score.eval', 'probe_score.train']`;
`probe_eval VERSION moves the inject key: True`;
`trainer VERSION moves train, not build: True True`.

**D3 — `run_dir`, `run_dir_of`, and the debug subtree.**
```bash
FIX=$(bash /tmp/mkfix.sh); python3 - "$FIX" <<'PY'
import sys
from pathlib import Path
import experimental_settings.schema as S
FIX = Path(sys.argv[1]); S.ROOT = FIX
tp = FIX/'experimental_settings/train_probe.yaml'
c = S.load(tp, 'ctool_qwen3_0pt6b', debug=False, overrides={})[0]
d = S.load(tp, 'ctool_qwen3_0pt6b', debug=True, overrides={})[0]
rd, dd = S.run_dir('train', c), S.run_dir('train', d)
print(rd.relative_to('%s/outputs' % FIX), dd.relative_to('%s/outputs' % FIX))
print(S.run_dir_of('train', S.key('train', c), debug=False) == rd,
      S.run_dir_of('train', S.key('train', d), debug=True) == dd)
print('nothing created:', not rd.exists() and not dd.exists())
PY
```
Expected: `train/<12 hex> debug/train/<12 hex>`, then `True True`, then
`nothing created: True`.

**D4 — `freeze` writes the projection, the `_` block, and refuses a collision.**
```bash
FIX=$(bash /tmp/mkfix.sh); python3 - "$FIX" <<'PY'
import sys, yaml
from pathlib import Path
import experimental_settings.schema as S
FIX = Path(sys.argv[1]); S.ROOT = FIX
tp = FIX/'experimental_settings/train_probe.yaml'
c = S.load(tp, 'ctool_qwen3_0pt6b', debug=False, overrides={})[0]
rd = S.run_dir('sample', c); rd.mkdir(parents=True)
S.freeze(c, 'sample', rd, {}, 'deadbeefcafe')
y = yaml.safe_load((rd/'settings.yaml').read_text())
print(sorted(k for k in y if not k.startswith('_')))
print(sorted(k for k in y if k.startswith('_')))
print(y['_stage'], y['_key'] == S.key('sample', c), y['_commit'], y['_debug'], y['_upstream'])
print('versions:', sorted(y['_versions'])[:3], len(y['_versions']))
print('diff:', yaml.safe_load((rd/'settings_diff.yaml').read_text()) == S.fields_of('sample', c))
print('no workflow line:', '_workflow' not in y)
c2 = S.load(tp, 'ctool_qwen3_0pt6b', debug=False, overrides={'sample.seeds': '[42, 67]'})[0]
S.freeze(c2, 'sample', rd, {}, 'deadbeefcafe')
print('seeds merged:', yaml.safe_load((rd/'settings.yaml').read_text())['sample']['seeds'])
tr = S.run_dir('train', c); tr.mkdir(parents=True)
S.freeze(c, 'train', tr, {}, 'deadbeefcafe')
t = yaml.safe_load((tr/'settings.yaml').read_text())
print('train projection:', sorted(k for k in t if not k.startswith('_')), 'checkpoint_hours' in t['train'])
(tr/'settings_diff.yaml').write_text('probe.method: cgen\n')
try: S.freeze(c, 'train', tr, {}, 'deadbeefcafe'); print('collision: NOT REFUSED')
except Exception as ex: print('collision: REFUSED', str(ex)[:80])
PY
```
Expected:
```
['data', 'generation', 'models', 'sample']
['_commit', '_debug', '_key', '_resolved', '_stage', '_upstream', '_versions']
sample True deadbeefcafe False {}
versions: ['agent/generate.py', 'agent/loop.py', 'data/environments/__init__.py'] 8
diff: True
no workflow line: True
seeds merged: [42, 67]
train projection: ['models', 'probe', 'train'] True
collision: REFUSED ...
```

**D5 — `load_frozen` round-trips and refuses a removed field.**
```bash
FIX=$(bash /tmp/mkfix.sh); python3 - "$FIX" <<'PY'
import sys, yaml
from pathlib import Path
import experimental_settings.schema as S
FIX = Path(sys.argv[1]); S.ROOT = FIX
tp = FIX/'experimental_settings/train_probe.yaml'
c = S.load(tp, 'ctool_qwen3_0pt6b', debug=False, overrides={})[0]
rd = S.run_dir('train', c); rd.mkdir(parents=True)
S.freeze(c, 'train', rd, {}, 'deadbeefcafe')
f = S.load_frozen(rd)
print(f._stage, f._key == S.key('train', c), f._commit, f.probe.method, f.train.lr, f.train.max_len)
print('upstream:', sorted(f._upstream), '| sections dropped:', f.sample is None and f.eval is None)
y = yaml.safe_load((rd/'settings.yaml').read_text()); y['train']['obsolete_knob'] = 3
(rd/'settings.yaml').write_text(yaml.safe_dump(y))
try: S.load_frozen(rd); print('removed field: NOT REFUSED')
except Exception as ex: print('removed field: REFUSED', str(ex)[:90])
PY
```
Expected: `train True deadbeefcafe ctool 1e-05 8192`, then
`upstream: ['build'] | sections dropped: True`, then `removed field: REFUSED`
with a message naming `train.obsolete_knob` and the run directory.

**D6 — rerun B1 after everything else, and paste it.**

### Selfcheck lines that apply later

`run.py selfcheck` (ticket 15) will check: `schema.py` imports under every
interpreter of the `venvs:` map (B1); its README annotation line reads
`imports: none (repo)` and the `ast` graph agrees (B1); every axis literal equals
what is on disk (B4); every module a `versions` cell names has exactly one
column-zero `VERSION` line and every method pair declares the same `PROBE_KIND`
(B5 exercises the reader, the repo-wide sweep is `run.py`'s); every alias in
`models/table.yaml` has a row in `constants/path_models.yaml`.

### GPU / main session — not yours

`M-G3`: once every other folder has merged, rerun the **read-only** commands —
`B4`, `C1`, `C2` and `D1`-`D5` — **without** the fixture: `S.ROOT` left at the
repo root, against the real `models/table.yaml`,
`data/environments/appworld.py`, `models/agent_models/gptoss.py`,
`models/probe_models/qwen.py` and the real `VERSION` lines. Every expected
outcome above holds unchanged except the key values themselves, which are then
the real ones.

**`C3`, `C4` and `C5` are never run this way, in this ticket or anywhere else.**
All three *write* into `$FIX/experimental_settings/*.yaml` —
`p.write_text(yaml.safe_dump(d))` with a `sweep:` block, eighteen bad fields and
a stated-differently `generation` section — so with `S.ROOT` at the repo root
they would overwrite the owner's setting files with mutated, re-dumped content.
They run against a `$FIX` copy, always. (The armed read-only hook refuses such a
write through the harness, but the hook is a backstop, not the rule: an
acceptance command never edits an owner file.)

## Comments

- 2026-09-17 wave 2 closeout: implementation passed review after 1 fix round (F1 `freeze` dropped earlier requested tasks on a re-freeze; F2 the README `imports:` line), branch `ticket/2026-09-17-wave2/T04` (base `943af82`, head `74cd513`), merged as `8a56964`. Main-session checks after the merge: `experimental_settings.schema` imports under system `python3` and the probe, appworld and vllm interpreters; `schema.load` on the real tree loads `baseline.yaml`'s setting with debug off and on, and fails on every `train_probe.yaml` and `inject.yaml` setting with `FileNotFoundError` on `eval/methods/ctool.py`, a wave 3 file (ticket 08); `module_literal` reads every literal of the real `models/agent_models/gptoss.py`, `models/probe_models/qwen.py` and `data/environments/appworld.py`. Acceptance-script defect confirmed by reading the script: `D2`'s last assertion never snapshots the train key before it edits `trainer.py`, so it prints `False True`; with the snapshot taken first the same sub-test prints `True True`. Not run: `M-G3` (needs every folder) and the repo-wide half of `B4`. Remaining minors for the final review: F3 (the inject-only refusal of a bare `probe:` section is unreachable behind the allowed-sections loop), F4 (two unused locals). Report `sdd/2026-09-17-wave2/T04-report.md`, workflow result `sdd/2026-09-17-wave2/wave-result.json`.
- 2026-09-17 wave 2 closeout, post-merge fix round: a post-merge review (four opus reviewers, every important finding re-run by a second reviewer; `sdd/2026-09-17-wave2/post-merge-review.json`) confirmed four findings in `schema.py`. SEAMS-1 (critical): the stage table still named the four `data/` files the owner's rename commit `2c97db5` had renamed, so every `key()` raised; fixed by the owner's commit `67473dd`. SCHEMA-2 and SCHEMA-3 (important): `_finalize` read `models.agent` and `data.env` before `_apply_inheritance` replaced them, so an inherited agent alias got another alias's `agent_row`, family literals and `VERSION`, and an inherited environment's splits and instructions were checked against `appworld`. SCHEMA-4 (important): the `models.probe`-under-inject refusal ran on raw YAML only, so a command-line override or a `sweep:` set it and two sweep children shared one run directory. The same round implements gyb's ruling of 2026-09-17 (errata, the `5.4 / 2.1` entry): a `key:` or `dir:` reference in `inject.probe_score` and `inject.probe_gen` carries `method: <probe.method value>`. Fixed on the recreated branch `ticket/2026-09-17-wave2/T04` (base `67473dd`, head `87a7975`, `experimental_settings/schema.py` only), re-review: all four items addressed in 1 round; merged as `e8a68b5`. Main-session checks after the merge, on the ticket's fixture: the name form and the `key:` form with `method: ctool` / `method: cgen` both key `probe_p1_e1_theta_0pt80`'s inject stage as `72e517ad368b`; a missing `method`, `method: ctoool`, `inject.probe_gen` with `method: cparam`, and the override `models.probe=qwen3_1pt7b` each raise a `SchemaError` naming the field; `inject.probe_score` with `method: cgen` loads and keys differently (`5f16f24b00a1`). SCHEMA-1 was refuted as a code defect and is an open errata entry (5.2 marks `train.checkpoint_hours` `key = no`, 2.1/2.2/3.3 and this ticket's `STAGES` put it in the train key). Ticket text the fix makes outdated: section 1's `{probe_score_method}` sentence (now also the `method:` sibling in the `key:`/`dir:` forms); `C4`'s `models.probe`-under-inject message text (the field named is unchanged); `B4`'s "constants only" expectation (more axis checks can run after the wave merge). New minors for the final review: RAW-PROBE-DEAD (F3 again, still unreachable), GEN-IS-FALSE (`if whole_call_generator is False:` and `param_only ... is False`, to be written in the affirmative), and the review's SCHEMA-5 (freeze widens a dotted `sections` entry to the whole section), SCHEMA-6 (sweep children in product order, not name order), SCHEMA-7 (malformed override, sweep or section input raises `TypeError`/`KeyError` instead of a `SchemaError` naming the field), SEAMS-2 (`_method_kind` reads `PROBE_KIND` from `eval/methods/<m>.py`, the contracts name `train/methods/<m>.py`), SEAMS-3 (tickets 04 and 05/06 resolved "docstring first line equals the README sentence" in opposite directions). Fix result `sdd/2026-09-17-wave2/post-merge-fix.json`.
