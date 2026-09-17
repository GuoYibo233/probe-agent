# Build plan — folder group `settings`

Planner: settings. Written 2026-09-17 against
`notes/plans/2026-09-14-structure-from-zero.md` (Part 1 tree, fixed),
`notes/plans/2026-09-17-contracts.md` (Parts 0.2, 2, 3, 5, 6.3 read in full;
1.5, 1.7, 4.1 read for the names this folder declares) and `notes/CONTEXT.md`.

Files owned here, all nine, and nothing else:

```
constants/path_datasets.yaml
constants/path_outputs.yaml
constants/path_models.yaml
experimental_settings/schema.py
experimental_settings/debug.yaml
experimental_settings/baseline.yaml
experimental_settings/train_probe.yaml
experimental_settings/inject.yaml
.claude/hooks/settings_readonly.sh
```

No file in this folder imports anything from the repo, and no file here starts a
GPU process. `schema.py` is the one Python file; the rest is data and one shell
script.

---

## 1. Files

### 1.1 `constants/path_datasets.yaml`

**One sentence.** Where each benchmark environment lives on this cluster — its
clone, its interpreter, its data root and its split task-id files — plus the
top-level `venvs:` map, the one place an interpreter path is written down
(contracts 6.3).

**Venv.** Data file. Parsed with `yaml.safe_load` by system `python3` (PyYAML
5.4.1) and by all three venv interpreters (PyYAML 6.0.3).

**Content (write exactly this).**

```yaml
# Where things are on this cluster. Locations only: nothing here changes a
# result or enters a key (contracts 6.3). A path changes only when the same
# bytes move; new bytes are a new alias.

venvs:                                  # every interpreter this repo starts a program with
  appworld: /home/y-guo/reproduce/new1/external/appworld/venv/bin/python
  probe:    /home/y-guo/reproduce/new1/external/probe-env/bin/python
  vllm:     /home/y-guo/reproduce/new1/external/vllm-env/bin/python

appworld:
  home:  /home/y-guo/reproduce/new1/external/appworld
  venv:  appworld                       # a key of venvs:
  data:  /home/y-guo/reproduce/new1/external/appworld/data
  splits:
    train: /home/y-guo/reproduce/new1/external/appworld/data/datasets/train.txt
    dev:   /home/y-guo/reproduce/new1/external/appworld/data/datasets/dev.txt
    test:  /home/y-guo/reproduce/new1/external/appworld/data/datasets/test_normal.txt
```

The three split files hold 90, 57 and 168 task ids, one per line, no trailing
newline (measured 2026-09-17; the reading rule is
`legacy/pipeline/annotate/build.py:303-306`). `test_challenge.txt` (417 ids) is
deliberately not a split: today's line uses `test_normal` as `test`
(`legacy/pipeline/configs/p1_gptoss.json:10-14`).

**Read by** (contracts 0.2): `data/environments/__init__.py` (the `splits:`
block), `data/environments/appworld.py` (home, data root, split files),
`experimental_settings/schema.py` (the `splits:` block, to validate a split
value at load, 5.3), `jobs/launch.py` (the `venv:` column and the `venvs:` map),
`run.py` (the `venvs:` map, for selfcheck's per-interpreter import test).

**Legacy source.** `legacy/run.py:63-75` (the `PY` interpreter map);
`legacy/envs/collect/run_appworld.py:149` (the hardcoded AppWorld home, the only
place it exists today); `legacy/pipeline/configs/p1_gptoss.json:10-14` and
`legacy/pipeline/configs/np821_gptoss.json:12-16` (`official_split_files`);
`legacy/pipeline/annotate/build.py:303-306` (`read_unit_list`, the one-id-per-line
rule).

**Not ported.** The other seven interpreters of the `PY` map (`mbert`,
`alfworld`, `tales`, `tau2`, `toolhop`, `stbserver`, `bash`) and every
non-AppWorld environment block — the new tree has one environment and three
venvs. The per-batch keys of the old pipeline configs (`traj_runs`, `data_out`,
`run_family`, `model_short`, `split_mode`, `seed`, `trajs_per_unit`,
`max_bounds`) are not locations: outputs are keyed directories (contracts 3.4)
and the rest are setting fields (5.2).

### 1.2 `constants/path_outputs.yaml`

**One sentence.** The NFS outputs root, the debug subdirectory under it, the one
machine this repo's commands may run on, and the cluster inventory
(contracts 6.3).

**Venv.** Data file, read as above.

**Content (write exactly this).**

```yaml
# The outputs root, the debug subdirectory, the login machine and the cluster
# inventory. Locations only; nothing here enters a key (contracts 6.3).

root: /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs
debug_subdir: debug
login_host: shiga          # what `hostname` answers on the machine this repo is typed on
hosts:
  - {name: tokyo105, alias: shiga,   cards: 4}
  - {name: tokyo106, cards: 8}
  - {name: tokyo107, cards: 8}
  - {name: tokyo108, alias: saitama, cards: 8}
```

`root/` and `root/debug/` are created by the acceptance command below; they do
not exist yet (checked 2026-09-17).

**Read by** (0.2): `experimental_settings/schema.py` (`run_dir`),
`jobs/registry.py` (`ls` walks the root; the hosts list for tmux and card
probes), `jobs/launch.py` (the `login_host` and the hosts list), `run.py` (the
`login_host` refusal, 8.6).

**Legacy source.** `legacy/ops/gpu_jobs.py:124` (`DEFAULT_HOSTS`, the same four
machines); `legacy/ops/launch_common.py:41` (`ALIAS = {"shiga": "tokyo105",
"saitama": "tokyo108"}`); the NFS root in `legacy/pipeline/configs/*.json`'s
`data_out` values.

**Not ported.** The `outputs` symlink at the repo root (dropped by the fourth
draft's walk); the per-batch `data_out` paths; `legacy/ops/launch_common.py`'s
`local_host()` normalisation, which becomes `jobs/`'s business — this file only
states the name and the alias.

### 1.3 `constants/path_models.yaml`

**One sentence.** Weights alias -> the directory or hub id the weights live in
(contracts 6.3: `alias -> {path, note}`).

**Venv.** Data file, read as above.

**Content.** One block per alias; `path` is an absolute directory or a hub id,
`note` says where the copy came from and when it was checked. Port every row of
`legacy/configs/models.json`'s `models:` block whose `path` is either a hub id
(no leading `/`) or an existing directory, keeping its `note` text, and add the
two backbones the old training scripts hardcoded:

```yaml
# Weights alias -> where the weights are. A new set of weights is a new alias
# here plus a row in models/table.yaml (contracts 6.1, 6.3).

gpt-oss-120b:
  path: /net/tokyo100-10g/data/str01_01/y-guo/models/gpt-oss-120b
  note: own replica, accepted 2026-07-28 (15 shards + tokenizer, ~61G); MoE, fits one H200
qwen3-0.6b-base:
  path: /net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-0.6B-Base
  note: own replica, 1.2G; the probe backbone of the cgen/ctool line since 2026-08-20
qwen3-1.7b-base:
  path: /net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-1.7B-Base
  note: own replica; the 1.7B tier of the three-tier backbone sweep (legacy train_causal_tool.py:86)
qwen3-4b-base:
  path: /net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-4B-Base
  note: own replica; the 4B tier of the same sweep (legacy train_causal_tool.py:87)
lfm2.5-350m-base:
  path: /net/tokyo100-10g/data/str01_01/y-guo/models/LFM2.5-350M-Base
  note: own replica, 681M; used by the cgen cell, registered 2026-08-20
```

The implementer checks each `path` with `os.path.isdir` and **drops any row whose
directory is gone**, listing what it dropped in the report; the five above all
existed on 2026-09-17.

**Read by** (0.2): `models/__init__.py`, `models/agent_models/service.py` (the
weights path of the row it serves).

**Legacy source.** `legacy/configs/models.json` (the whole `models:` block, with
its notes); `legacy/pipeline/train/train_causal_tool.py:84-88` (the
`qwen`/`qwen17`/`qwen4` path map, repeated at
`train_causal_callgen.py:95-99` and `train_causal_param.py:83-87`);
`legacy/model_registry.py:15-31` (the reader).

**Not ported.** `models.json`'s `aliases:` block (`models/table.yaml`'s rows are
the alias layer now, contracts 6.1, 9(a)#10); `model_registry.resolve()`'s
existence check and its `__main__` (both move to `models/__init__.py`, 6.2);
`modernbert-base` and `mirrorapi-cache` (retired lines — no row in the new tree
can name them; they return as one line each the day a setting needs them).

### 1.4 `experimental_settings/schema.py`

**One sentence.** The schema of a setting — every field with its default, the
allowed values of each axis, the stage table — and the loader that reads a YAML
file against it (file -> setting, diff, key, run_dir, freeze).

**Venv.** `any`: standard library + PyYAML only, and it must import under system
`python3` (3.10.12), `external/appworld/venv/bin/python` (3.12),
`external/probe-env/bin/python` (3.11) and `external/vllm-env/bin/python` (3.12).
That fixes the dialect: `from __future__ import annotations` at the top, no
3.11+ syntax, no NumPy, no Polars, **no repo import at all** (contracts 0.2:
`imports: none (repo); [PyYAML, dataclasses, hashlib, re, ast]`).

**Imports / used by** (contracts 0.2). Imports nothing from the repo. Used by
ten files: `run.py`, `jobs/launch.py`, `agent/loop.py`, `data/build_dataset.py`,
`train/utils/trainer.py`, `eval/utils/probe_eval.py`, `eval/score_run.py`,
`eval/method_table.py`, `models/agent_models/service.py`,
`models/probe_models/service.py` (the last two take `load_frozen` only).
**Reads:** `experimental_settings/*.yaml`, `models/table.yaml`,
`constants/path_outputs.yaml`, `constants/path_datasets.yaml` (the `splits:`
block), a run directory's `settings.yaml`, and the `VERSION` / `PROBE_KIND` lines
and module-level literals of 3.3's literal rule — **all as source text, never by
importing**. **Writes:** `settings.yaml` and `settings_diff.yaml` in a run
directory.

#### 1.4.1 The names the file must offer

Module-level, in the order contracts 5.1 fixes (dataclasses, axis literals, the
stage table with `PROBE_TEXT_FIELDS` beside it, the loader):

```python
ROOT = Path(__file__).resolve().parents[1]     # every repo-relative read goes through it
```

**Dataclasses** (fields, types and defaults verbatim from contracts 5.2; one
`#` comment per field, the "one line" column of that table):

```python
@dataclass
class Meta:        notes: str = ""; override: list[str] = []
@dataclass
class Data:        env: str = "appworld"; instructions: str = "v1"
@dataclass
class Models:      agent: str = "gptoss120b"; probe: str | None = "qwen06"
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

Every mutable default is a `field(default_factory=...)`. `THETA_GRID` is the
explicit 20-element literal (errata 10):

```python
THETA_GRID = [0.5, 0.525, 0.55, 0.575, 0.6, 0.625, 0.65, 0.675, 0.7, 0.725,
              0.75, 0.775, 0.8, 0.825, 0.85, 0.875, 0.9, 0.925, 0.95, 0.975]
```

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

Which sections a merged setting holds is errata 6: `meta`, `data`, `models`,
`generation` always; a stage section when the file's `workflow:` names its stage;
`build` additionally on an inject setting (the inherited `PROBE_TEXT_FIELDS`);
everything else `None`, so `cfg.inject is None` is the presence test 5.1 promises.

**Axis literals** (contracts 5.3, one literal per axis, never imported from the
layer that implements them):

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

**The stage table** (contracts 2.1, 2.2, 2.3; cell shape by errata 3 and 4).
Copy this dictionary as written:

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
    "versions": ("agent/loop.py", "agent/generate.py", "data/task_record.py",
                 "data/environments/__init__.py", "data/environments/{env}.py",
                 "models/agent_models/{family}.py", "models/agent_models/service.py",
                 "models/probe_models/service.py"),
  },
  "build": {
    "sections": ("data", "build",
                 "sample.split", "sample.tasks", "sample.n_tasks", "sample.seeds"),
    "models": (),
    "upstream": ({"name": "sample", "source": "same", "stage": "sample", "key": "fold"},),
    "program": "data.build_dataset",
    "venv": "any",
    "pieces": (("cpu", 1, None),),
    "cards": False,
    "done_writer": "stage",
    "projection": (),
    "projection_generator": (),
    "versions": ("data/build_dataset.py", "data/probe_input.py", "data/example.py",
                 "data/task_record.py", "data/environments/__init__.py",
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
                 "eval/methods/{method}.py", "data/example.py", "data/prediction.py",
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
                 "data/prediction.py"),
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
                 "agent/inject_format.py", "data/probe_input.py", "data/task_record.py",
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
    "versions": ("eval/score_run.py", "data/task_record.py"),
  },
}
```

Placeholders in `versions` and `program` are substituted from the setting:
`{env}` = `data.env`, `{family}` = `models.agent_row["family"]`, `{backbone}` =
`models.probe_row["family"]`, `{method}` = `probe.method`,
`{probe_score_method}` = the `probe.method` of the setting
`inject.probe_score` resolves to. A field of a section that is `None` contributes
nothing — that is how `score`'s one entry covers both workflows.

**The loader** — the five signatures contracts 5.1 and 3.1 pin, copied exactly:

```python
def load(workflow_file: Path, setting_name: str, *,
         debug: bool, overrides: dict) -> list[Setting]          # 5.1
def load_frozen(run_dir: Path) -> Setting                         # 5.1
def freeze(setting: Setting, stage: str, run_dir: Path, resolved: dict,
           commit: str) -> None                                   # 5.1
def key(stage: str, setting: Setting) -> str                      # 3.1, 12 lowercase hex
def run_dir(stage: str, setting: Setting) -> Path                 # 3.1
def run_dir_of(stage: str, key: str, *, debug: bool) -> Path      # 3.1
```

Four helpers of this file, named so the acceptance commands can address them
(internal, nothing outside `schema.py` calls them):

```python
def fields_of(stage: str, setting: Setting) -> dict      # the "fields" block of 3.3, = settings_diff.yaml
def models_of(stage: str, setting: Setting) -> dict      # the "models" block of 3.3
def upstream_of(stage: str, setting: Setting) -> dict    # name -> key, per the stage table's upstream cell
def versions_of(stage: str, setting: Setting) -> dict    # module path -> VERSION, read as source text
def module_version(rel_path: str) -> int                 # the one column-zero `VERSION = <int>` line (3.3)
def module_literal(rel_path: str, name: str)             # ast.literal_eval of a column-zero literal (3.3)
```

**Behaviour, by contracts section.**

- `load`: merge order 5.7 (defaults -> `common:` -> the named setting -> sweep
  expansion -> `debug.yaml` -> command-line overrides), sections merged per field
  and lists replaced (errata 15); sweep expansion 5.5 with the `repr()` child
  naming; the debug overlay 5.6 applied only to the sections this file's
  `workflow:` names; references resolved after the overrides (5.4) with the
  inheritance rule and its per-group agreement; `meta.override` checked after
  step 5; the model table's `result:` block expanded last, immediately before
  keying (5.7, 6.1). Returns a list: one element, or the sweep children in name
  order.
- Every refusal of 5.7, each naming the field in the message, plus the type
  check of errata 8 and the required-field check of errata 11.
- `load_frozen`: parse `settings.yaml` against the dataclasses, fill the `_`
  block, re-merge nothing and re-resolve nothing (2.6); refuse a field the schema
  has since removed, naming the field and the run directory (5.7).
- `key`: the payload of 3.3 — `{"stage", "fields", "models", "upstream",
  "versions", "debug"}` — canonicalised by errata 2 and hashed; the four
  pre-diff resolutions of 3.3 in the order given; the `inject.probe_score` eval
  carve-out (`"key": "carry"` in the table); the four reference fields never
  entering `fields`; versions read as text.
- `run_dir` / `run_dir_of`: `<root>/<stage>/<key>` or
  `<root>/<debug_subdir>/<stage>/<key>`, roots from
  `constants/path_outputs.yaml` (3.4). `key` and `run_dir` never touch the output
  tree (3.2 rule 2).
- `freeze`: the stage projection of 3.4 (the stage table's `sections` +
  `projection` + `projection_generator` when the method's `PROBE_KIND` is
  `generator` + an inject run's inherited `PROBE_TEXT_FIELDS`), the `_` block of
  1.5, both files written through a temporary name in the same directory and
  renamed, and the collision check on `settings_diff.yaml` with the per-field
  merge of the non-keyed request fields (`seeds` ordered union, `tasks` null
  absorbs, `pieces`/`replicas` take the new launch's values).

**Legacy source.** There is no key, no run-directory naming and no stage table in
the old tree; what ports is the merge discipline and the numbers:

| what | legacy file and lines |
|---|---|
| merge order, "explicit beats preset beats default", and the refusal on a missing required value | `legacy/preset_loader.py:116-148` (`merge_client`, `require_temperature`), `:66-100` (`_check_node`, `validate`) |
| the generation defaults (temperature 1.0, top_p 1.0, max_tokens 8192, effort high, date 2026-08-06, stop null) | `legacy/configs/presets/default.json` (`client` block) |
| the `train` defaults (max_len 8192, events_per_mb 4, accum 2, epochs 1, grad_ckpt) | `legacy/pipeline/train/train_causal_share.py:931-1005` |
| `train.lr` 1.0e-5 and `train.seed` 42 | `legacy/pipeline/train/train_causal_tool.py:89-91` |
| the `build` defaults (min_think 40, hist_rounds 3, probe_result_cap 400, max_cuts 64, weight_mode) | `legacy/pipeline/annotate/rules.py:20-22`, `legacy/pipeline/annotate/build.py:18,205`, `legacy/pipeline/configs/np821_gptoss.json` (`max_bounds: 64`, `weight_mode: uniform`) |
| the `eval` defaults (theta grid 0.5..0.975 step 0.025, risk 0.05) | `legacy/pipeline/eval/eval_tool.py:51` (`THETAS`), `:279` (`bootstrap`), `legacy/pipeline/eval/eval_causal_call.py:500` (`--risk` default 0.05) |
| the `inject` defaults (chunk_tokens 64, tail_tokens 1024, max_inject_per_step 1, fire_nth_cut 0) | `legacy/pipeline/inject/live_appworld.py:617-634` |
| the stage/registry idea that `STAGES` replaces | `legacy/run.py:76-110` (`CELLS`, `EVAL_CELLS`) and the `TASKS` registry below it |

**Not ported.** Presets as a concept (`legacy/preset_loader.py`,
`legacy/serve_preset.py`, `legacy/sweep_preset.py`): generation is a setting
section, the server block is `models/table.yaml`, and preset sweeping is the
`sweep:` keyword (5.5). `CLIENT_KEYS`/`SERVER_KEYS` and the `NEW1_PRESET_JSON`
environment channel. `legacy/run.py`'s `TASKS`/`RECIPES` registry and its
`handoff` flag (`run.py`'s stage walk replaces them). OmegaConf and `${a.b}`
interpolation (5.1: replaced by the reference syntax of 5.4). The old
`--align-tol` family of flags (`train_causal_share.py:989-1005`): the contract has
one gate at `1e-4` (2.5) under one boolean, `train.align_check`.

### 1.5 `experimental_settings/debug.yaml`

**One sentence.** Sizes only, laid over any setting by `--debug` (contracts 5.6).

**Venv.** Data file. Owner's file: an agent writes it once here and never again.

**Content (contracts 5.6, verbatim).**

```yaml
# Sizes only -- never a model and never a tuning, so a --debug run exercises the
# real code path (contracts 5.6). Every field here exists in the schema, and the
# overlay applies only the sections this setting's workflow: line names.
sample:  {n_tasks: 3, seeds: [42], pieces: 1, replicas: 1, max_steps: 6}
build:   {max_cuts: 8, max_examples: 64}
train:   {epochs: 1, max_steps: 20, predict: {cap: 100}}
inject:  {n_tasks: 3, seeds: [42], pieces: 1, max_steps: 6}
eval:    {bootstrap: 50}
```

It has no `workflow:` line and no named settings: it is an overlay, not a
workflow file. **Read by** `experimental_settings/schema.py` only (0.2).

### 1.6 `experimental_settings/baseline.yaml`

**One sentence.** Workflow `sample, score`; the trajectories every inject run is
scored against.

**Content.**

```yaml
# Workflow: collect trajectories with the agent model alone, then score them.
# A new experiment is a new named setting in this file (contracts 5.1).
workflow: [sample, score]

common:
  data:   {env: appworld, instructions: v1}
  models: {agent: gptoss120b}

gptoss_aw:
  meta:   {notes: "AppWorld trajectories from gpt-oss-120b with no probe; the baseline an inject run is scored against"}
  sample: {split: [train, dev, test], seeds: [42], pieces: 6, replicas: 1}
  score:  {by_seed: true}
```

`score.baseline` is left unset on purpose: `null` means "report this run's own
numbers only", which is what a baseline file needs (5.2).

### 1.7 `experimental_settings/train_probe.yaml`

**One sentence.** Workflow `sample, build, train, eval`; the probe-training line.

**Content.**

```yaml
# Workflow: collect, build the dataset, train a probe, evaluate it.
workflow: [sample, build, train, eval]

common:
  data:   {env: appworld, instructions: v1}
  models: {agent: gptoss120b}
  sample: {split: [train, dev, test], seeds: [42], pieces: 6, replicas: 1}

ctool_q06:
  meta:   {notes: "classification probe, Qwen3-0.6B-Base, full tuning; the theta source for the generating probes"}
  models: {probe: qwen06}
  probe:  {method: ctool, tuning: full}
  train:  {lr: 1.0e-5, epochs: 1}
  eval:   {risk: [0.10, 0.05]}

cgen_q06:
  meta:   {notes: "whole-call generating probe on the same dataset; theta is frozen by ctool_q06"}
  models: {probe: qwen06}
  probe:  {method: cgen, tuning: full}
  train:  {lr: 1.0e-5, epochs: 1}
  eval:   {theta_from: train_probe/ctool_q06}
```

Both settings take the same `sample` and `build` fields, so their two train runs
share a `_upstream["build"]` key — the gate of 2.5 that `eval.theta_from` and an
inject run's two references both depend on. Floats carry a decimal point
(`1.0e-5`, never `1e-5`): PyYAML parses the second as a **string** (measured
2026-09-17 on 5.4.1 and 6.0.3), and errata 8's type check is what catches it.

### 1.8 `experimental_settings/inject.yaml`

**One sentence.** Workflow `inject, score`; the live runs and their control arm.

**Content.**

```yaml
# Workflow: run the agent live with the probe, then score against a baseline.
workflow: [inject, score]

common:
  data:   {env: appworld, instructions: v1}
  models: {agent: gptoss120b}

p1e1_t080:
  meta:  {notes: "live run: fire at theta 0.80, injection format p1_e1, probe arm"}
  inject:
    split: [test]
    seeds: [42]
    theta: 0.80
    arm: probe
    format: p1_e1
    probe_score: train_probe/ctool_q06
    probe_gen: train_probe/cgen_q06
    pieces: 6
    replicas: 1
  score: {baseline: baseline/gptoss_aw}

no_probe_t080:
  meta:  {notes: "control arm: the machinery wired and never firing"}
  inject:
    split: [test]
    seeds: [42]
    theta: 0.80
    arm: no_probe
    format: p1_e1
    probe_score: train_probe/ctool_q06
    probe_gen: train_probe/cgen_q06
    pieces: 6
    replicas: 1
  score: {baseline: baseline/gptoss_aw}
```

Neither setting states a `probe:` section or a `models.probe` field — the loader
refuses both for a workflow containing `inject` (2.1, 5.7) — and neither states
the inherited `build` fields, which `freeze` writes (5.7). The baseline's
`sample.split` `[train, dev, test]` is a superset of `inject.split` `[test]` and
its seeds are a superset, which is 5.7's baseline refusal.

### 1.9 `.claude/hooks/settings_readonly.sh`

**One sentence.** The PreToolUse hook that refuses any agent edit to
`experimental_settings/*.yaml` and to `models/table.yaml` (tree line; contracts
6.1 answers the owner's open question with **yes, the table is covered**).

**Venv.** None — a shell script the Claude Code harness runs; its inline check
uses system `python3` (3.10, standard library only).

**Behaviour.**

- Reads the PreToolUse JSON payload on stdin (`tool_name`, `tool_input`).
- Protected paths, matched on the path's tail so that an absolute, a relative and
  a worktree path all match: `experimental_settings/<anything>.yaml` (and
  `.yml`), and `models/table.yaml`.
- `Write`, `Edit`, `MultiEdit`, `NotebookEdit`: block when `tool_input.file_path`
  (or any `edits[].file_path`, or `notebook_path`) is protected.
- `Bash`: block when the command mentions a protected path **and** contains any
  of `>`, `>>`, `tee`, `sed -i`, `cp `, `mv `, `rm `, `truncate`, `dd `, `patch`,
  `chmod`, `install`. A read (`cat`, `head`, `grep`, `git show`) passes.
- Block = exit code **2** with the message on stderr; everything else exits 0.
  Message: `experimental_settings/*.yaml and models/table.yaml are the owner's
  files: an agent never edits them (contracts 5.1, 6.1). Propose the change as a
  task instead.`
- The script itself never writes a file and never calls the network.

**Registration.** The hook does nothing until `.claude/settings.json` arms it.
The implementer does **not** edit `.claude/settings.json` — an agent does not
change its own harness configuration — it ships the script plus this snippet in
the ticket report, and the main session installs it (errata 12, section 4 step
G4):

```json
{"hooks": {"PreToolUse": [{"matcher": "Write|Edit|MultiEdit|NotebookEdit|Bash",
  "hooks": [{"type": "command",
             "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/settings_readonly.sh"}]}]}}
```

**Legacy source.** None: the old tree has no hook. The rule it enforces is the
fourth draft's `experimental_settings/` line plus contracts 6.1.

---

## 2. Order of construction, and what must exist first

Inside the folder, four steps, each the next ticket:

1. **T01 — the data files** (`constants/*.yaml`, `experimental_settings/*.yaml`,
   the hook). Nothing else in the repo is needed. The hook is written **after**
   the four setting YAMLs in the same ticket and stays unarmed, so it cannot
   block its own ticket.
2. **T02 — `schema.py` declarations**: `ROOT`, the dataclasses, `THETA_GRID`,
   `AXES`, `RETIRED`, `REQUIRED_FIELDS`, `PROBE_TEXT_FIELDS`, `STAGES`, and the
   two source-text readers `module_version` / `module_literal`. Needs T01 for
   nothing but coherence; no other folder.
3. **T03 — the loader**: `load` with the whole of 5.4, 5.5, 5.6, 5.7. Needs T02.
4. **T04 — keys and the run directory**: `fields_of`, `models_of`,
   `upstream_of`, `versions_of`, `key`, `run_dir`, `run_dir_of`, `freeze`,
   `load_frozen`. Needs T03.

**What from other folders must exist, and when.** `schema.py` imports nothing
from the repo, so no ticket here is blocked on another folder's *function*. What
the loader and `key` **read as source text** must exist for the real-tree checks
of section 4, and the acceptance commands of section 3 stand in for them with a
fixture tree the command builds itself (that is what `ROOT` is for):

| needed by | file | what is read out of it |
|---|---|---|
| T03 `load` | `models/table.yaml` | the rows `gptoss120b` (role agent, family gptoss) and `qwen06` (role probe, family qwen), their `result:` blocks (6.1) |
| T03 `load` | `models/agent_models/gptoss.py` | column-zero `NAME`, `STOP`, `EFFORTS`, `DEFAULT_EFFORT`, `DEFAULT_DATE`, `VERSION` (6.2, 3.3) |
| T03 `load` | `models/probe_models/qwen.py` | column-zero `LORA_TARGETS`, `VERSION` (6.2) |
| T03 `load` | `data/environments/appworld.py` | column-zero `INSTRUCTIONS` (key `v1`), `SPLIT_ROLE`, `VERSION` (4.1) |
| T03 `load` | `data/environments/__init__.py` | column-zero `VERSION` (4.1) |
| T04 `key` | every module named in a `versions` cell above | its one column-zero `VERSION = <int>` line: `agent/{loop,generate,inject,inject_format}.py`, `data/{task_record,example,prediction,probe_input,build_dataset}.py`, `data/environments/{__init__,appworld}.py`, `models/agent_models/{gptoss,service}.py`, `models/probe_models/{base,qwen,service}.py`, `train/utils/trainer.py`, `train/methods/{ctool,cgen,cparam}.py`, `eval/utils/probe_eval.py`, `eval/methods/{ctool,cgen,cparam}.py`, `eval/score_run.py` |
| T04 `key` | `train/methods/{ctool,cgen,cparam}.py` | column-zero `PROBE_KIND` and `CHECKPOINT_META` (2.6, 5.7) |

Consumers of this folder, for the integrator's sequencing: `run.py` and
`jobs/launch.py` read `STAGES` (the `venv`, `pieces`, `cards`, `done_writer`,
`program` cells) and call `load`, `freeze`, `key`, `run_dir`, `run_dir_of`; the
eight other importers call `load_frozen` only. Nothing outside this folder calls
`fields_of`, `models_of`, `upstream_of`, `versions_of`, `module_version` or
`module_literal`.

---

## 3. Acceptance, CPU

Every command is run from the repo root. `PY3=python3` (3.10.12, PyYAML 5.4.1)
for the data files; `PY=external/probe-env/bin/python` where a second
interpreter is wanted. Nothing here needs a GPU, a card probe or another host.

### 3.0 The fixture (used by T03 and T04)

One script, written once into the scratch directory and reused. It builds a
complete fake repo root so the loader and `key` can be exercised end to end
before the other folders land; `schema.ROOT` is repointed at it, which is exactly
what `ROOT` exists for.

```bash
cat > /tmp/mkfix.sh <<'SH'
set -eu
FIX=$(mktemp -d); export FIX
mkdir -p "$FIX"/{constants,experimental_settings,models/agent_models,models/probe_models,data/environments,agent,train/utils,train/methods,eval/utils,eval/methods,outputs}
cp constants/*.yaml "$FIX/constants/"
cp experimental_settings/*.yaml "$FIX/experimental_settings/"
sed -i "s|^root:.*|root: $FIX/outputs|" "$FIX/constants/path_outputs.yaml"
cat > "$FIX/models/table.yaml" <<'Y'
gptoss120b:
  role: agent
  family: gptoss
  result: {weights: gpt-oss-120b, dtype: bfloat16, quantization: null,
           max_model_len: 131072, served_model_name: gpt-oss-120b,
           env_result: {VLLM_USE_FLASHINFER_SAMPLER: "0"}, extra_flags: ""}
  serving: {host: tokyo108, port: 8103, gpu_memory_utilization: 0.92,
            tensor_parallel_size: 1, env: {}}
qwen06:
  role: probe
  family: qwen
  result: {weights: qwen3-0.6b-base, dtype: bfloat16}
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
HEAD_LAYER = "model.norm"
P
cat > "$FIX/data/environments/appworld.py" <<'P'
VERSION = 1
INSTRUCTIONS = {"v1": "developer message v1"}
SPLIT_ROLE = {"train": "train", "dev": "val", "test": "test"}
P
for f in data/environments/__init__.py data/task_record.py data/example.py \
         data/prediction.py data/probe_input.py data/build_dataset.py \
         agent/loop.py agent/generate.py agent/inject.py agent/inject_format.py \
         models/agent_models/service.py models/probe_models/base.py \
         models/probe_models/service.py train/utils/trainer.py \
         eval/utils/probe_eval.py eval/score_run.py; do
  printf 'VERSION = 1\n' > "$FIX/$f"
done
for m in ctool cgen cparam; do
  kind=classifier; sep=null; po=false
  [ "$m" = ctool ] || kind=generator
  [ "$m" = cparam ] && po=true || true
  printf 'VERSION = 1\nPROBE_KIND = "%s"\nCHECKPOINT_META = {"call_sep": " ->", "param_only": %s}\n' \
         "$kind" "$(echo $po | sed 's/true/True/;s/false/False/')" > "$FIX/train/methods/$m.py"
  printf 'VERSION = 1\nPROBE_KIND = "%s"\n' "$kind" > "$FIX/eval/methods/$m.py"
done
echo "$FIX"
SH
bash /tmp/mkfix.sh
```

Expected: one line, the fixture directory path. Every later command does
`FIX=$(bash /tmp/mkfix.sh)` and then, inside python, `import
experimental_settings.schema as S; S.ROOT = Path(FIX)`.

### 3.1 T01 — the data files

**A1. All seven YAML files parse, under all four interpreters.**

```bash
for P in python3 external/probe-env/bin/python external/appworld/venv/bin/python external/vllm-env/bin/python; do
  $P -c "
import glob, yaml
fs = sorted(glob.glob('constants/*.yaml') + glob.glob('experimental_settings/*.yaml'))
for f in fs: yaml.safe_load(open(f))
print(len(fs), 'parsed')"
done
```
Expected: `7 parsed` four times, exit 0 each.

**A2. `path_datasets.yaml` is complete and every path it names exists.**

```bash
python3 -c "
import os, yaml
d = yaml.safe_load(open('constants/path_datasets.yaml'))
assert set(d['venvs']) == {'appworld','probe','vllm'}, d['venvs']
for k, p in d['venvs'].items(): assert os.access(p, os.X_OK), (k, p)
aw = d['appworld']
assert set(aw) == {'home','venv','data','splits'}, sorted(aw)
assert aw['venv'] in d['venvs']
assert os.path.isdir(aw['home']) and os.path.isdir(aw['data'])
n = {}
for s, f in aw['splits'].items():
    n[s] = len([l for l in open(f).read().split(chr(10)) if l.strip()])
print(sorted(aw['splits']), n)"
```
Expected: `['dev', 'test', 'train'] {'train': 90, 'dev': 57, 'test': 168}` (order
of the dict as written), exit 0.

**A3. `path_outputs.yaml` keys, the login host, the inventory, and the root.**

```bash
python3 -c "
import os, socket, yaml
d = yaml.safe_load(open('constants/path_outputs.yaml'))
assert set(d) == {'root','debug_subdir','login_host','hosts'}, sorted(d)
assert d['debug_subdir'] == 'debug'
assert d['login_host'] == socket.gethostname(), (d['login_host'], socket.gethostname())
assert [h['name'] for h in d['hosts']] == ['tokyo105','tokyo106','tokyo107','tokyo108']
assert sum(h['cards'] for h in d['hosts']) == 28
os.makedirs(os.path.join(d['root'], d['debug_subdir']), exist_ok=True)
print('root', os.path.isdir(d['root']), 'debug', os.path.isdir(os.path.join(d['root'], d['debug_subdir'])))"
```
Expected: `root True debug True`, exit 0. (This is also the command that creates
the outputs root on NFS; it did not exist on 2026-09-17.)

**A4. `path_models.yaml`: every alias resolves to something that is there.**

```bash
python3 -c "
import os, yaml
d = yaml.safe_load(open('constants/path_models.yaml'))
for a, r in d.items():
    assert set(r) == {'path','note'}, (a, sorted(r))
    ok = os.path.isdir(r['path']) if r['path'].startswith('/') else True
    print(f'{a:20s} {ok} {r[\"path\"]}')
    assert ok, a"
```
Expected: one line per alias, every one `True`; at least `gpt-oss-120b` and
`qwen3-0.6b-base` present.

**A5. The setting files are shaped the way the schema will read them.**

```bash
python3 -c "
import yaml
STAGE_OF = {'sample':'sample','build':'build','probe':'train','train':'train',
            'eval':'eval','inject':'inject','score':'score'}
FREE = {'meta','data','models','generation'}
for f, wf in [('baseline',['sample','score']),
              ('train_probe',['sample','build','train','eval']),
              ('inject',['inject','score'])]:
    d = yaml.safe_load(open(f'experimental_settings/{f}.yaml'))
    assert d['workflow'] == wf, (f, d['workflow'])
    names = [k for k in d if k not in ('workflow','common')]
    for n in names + (['common'] if 'common' in d else []):
        for sec in d[n]:
            assert sec in FREE or STAGE_OF[sec] in wf, (f, n, sec)
    print(f, wf, names)
dbg = yaml.safe_load(open('experimental_settings/debug.yaml'))
assert set(dbg) == {'sample','build','train','eval','inject'}, sorted(dbg)
assert 'workflow' not in dbg
print('debug', dbg['sample'], dbg['train'])"
```
Expected:
```
baseline ['sample', 'score'] ['gptoss_aw']
train_probe ['sample', 'build', 'train', 'eval'] ['ctool_q06', 'cgen_q06']
inject ['inject', 'score'] ['p1e1_t080', 'no_probe_t080']
debug {'n_tasks': 3, 'seeds': [42], 'pieces': 1, 'replicas': 1, 'max_steps': 6} {'epochs': 1, 'max_steps': 20, 'predict': {'cap': 100}}
```

**A6. Every number that must be a number is one, and every reference resolves.**

```bash
python3 -c "
import yaml
tp = yaml.safe_load(open('experimental_settings/train_probe.yaml'))
assert isinstance(tp['ctool_q06']['train']['lr'], float), type(tp['ctool_q06']['train']['lr'])
inj = yaml.safe_load(open('experimental_settings/inject.yaml'))
for n, s in inj.items():
    if n in ('workflow','common'): continue
    assert isinstance(s['inject']['theta'], float), (n, s['inject']['theta'])
    for fld in ('probe_score','probe_gen'):
        f, name = s['inject'][fld].split('/')
        assert name in yaml.safe_load(open(f'experimental_settings/{f}.yaml')), (n, fld)
    f, name = s['score']['baseline'].split('/')
    assert name in yaml.safe_load(open(f'experimental_settings/{f}.yaml'))
    assert 'probe' not in s and 'probe' not in (s.get('models') or {})
print('references resolve, floats are floats')"
```
Expected: `references resolve, floats are floats`, exit 0.

**A7. The hook blocks what it must and passes what it must.**

```bash
h=.claude/hooks/settings_readonly.sh
t(){ printf '%s' "$2" | $h >/dev/null 2>/tmp/hookerr; echo "$1 -> $?"; }
t protected-write  '{"tool_name":"Write","tool_input":{"file_path":"/home/y-guo/reproduce/new1/experimental_settings/inject.yaml","content":"x"}}'
t protected-edit   '{"tool_name":"Edit","tool_input":{"file_path":"experimental_settings/debug.yaml","old_string":"a","new_string":"b"}}'
t table-yaml       '{"tool_name":"Write","tool_input":{"file_path":"models/table.yaml","content":"x"}}'
t constants-ok     '{"tool_name":"Write","tool_input":{"file_path":"constants/path_models.yaml","content":"x"}}'
t schema-ok        '{"tool_name":"Write","tool_input":{"file_path":"experimental_settings/schema.py","content":"x"}}'
t bash-read-ok     '{"tool_name":"Bash","tool_input":{"command":"cat experimental_settings/debug.yaml"}}'
t bash-write       '{"tool_name":"Bash","tool_input":{"command":"sed -i s/a/b/ experimental_settings/debug.yaml"}}'
t bash-redirect    '{"tool_name":"Bash","tool_input":{"command":"echo x > models/table.yaml"}}'
cat /tmp/hookerr
```
Expected exactly:
```
protected-write -> 2
protected-edit -> 2
table-yaml -> 2
constants-ok -> 0
schema-ok -> 0
bash-read-ok -> 0
bash-write -> 2
bash-redirect -> 2
```
and the last `cat` printing the refusal message naming the two protected paths.

### 3.2 T02 — the declarations

**B1. `schema.py` imports under all four interpreters and imports no repo module.**

```bash
for P in python3 external/probe-env/bin/python external/appworld/venv/bin/python external/vllm-env/bin/python; do
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
Expected: four lines `experimental_settings.schema 6 ('min_think', 'hist_rounds', 'probe_result_cap')`,
then a module list drawn only from the standard library plus `yaml`
(`__future__, ast, dataclasses, hashlib, json, os, pathlib, re, typing, yaml` or a
subset), and no repo package.

**B2. Defaults equal the contract table.**

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
assert S.Sample().seeds is not S.Sample().seeds   # default_factory, not a shared list
print('defaults ok')"
```
Expected: `defaults ok`.

**B3. `STAGES` has the six stages and the cell shape.**

```bash
python3 -c "
import experimental_settings.schema as S
assert list(S.STAGES) == ['sample','build','train','eval','inject','score']
CELLS = {'sections','models','upstream','program','venv','pieces','cards','done_writer','projection','projection_generator','versions'}
for st, e in S.STAGES.items():
    assert set(e) == CELLS, (st, set(e) ^ CELLS)
    for u in e['upstream']:
        assert u['key'] in ('fold','carry') and (u['source'] == 'same' or u['source'].startswith('ref:')), (st, u)
print([ (st, len(e['versions']), e['cards'], e['venv'] if isinstance(e['venv'],str) else 'map') for st, e in S.STAGES.items() ])
print('carry:', [(st,u['name']) for st,e in S.STAGES.items() for u in e['upstream'] if u['key']=='carry'])"
```
Expected: the tuple list showing `('sample', 8, True, 'map')`, `('build', 6,
False, 'any')`, `('train', 7, True, 'probe')`, `('eval', 3, False, 'any')`,
`('inject', 14, True, 'map')`, `('score', 2, False, 'any')`, and
`carry: [('inject', 'probe_score.eval')]` — the one carve-out of 2.1.

**B4. The axis literals agree with what is on disk** (the part of `run.py
selfcheck` that concerns this folder, 5.3; run it again after every other folder
lands, and skip a row whose directory does not exist yet, saying so):

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
Expected before the other folders land: `axis checks that could run: constants
only`, exit 0. After they land: `all`, exit 0.

**B5. The two source-text readers.**

```bash
D=$(mktemp -d); printf 'VERSION = 7\nSTOP = ["<|return|>"]\nclass C:\n    VERSION = VERSION\n' > $D/m.py
printf 'VERSION = 1\nVERSION = 2\n' > $D/two.py; printf 'x = 1\n' > $D/none.py
python3 -c "
import sys; from pathlib import Path
import experimental_settings.schema as S
S.ROOT = Path('$D')
print(S.module_version('m.py'), S.module_literal('m.py','STOP'))
for f, why in [('two.py','two matches'), ('none.py','no match')]:
    try: S.module_version(f); print('NO RAISE', f)
    except Exception as ex: print(why, '->', type(ex).__name__, str(ex)[:60])"
```
Expected: `7 ['<|return|>']` — the indented `VERSION = VERSION` inside the class
is not a second match (3.3) — then two lines showing a raise whose message names
the file for both the two-match and the zero-match case.

### 3.3 T03 — the loader

Every command starts with `FIX=$(bash /tmp/mkfix.sh)`.

**C1. The flagship load, with the model row expanded and the nulls resolved.**

```bash
FIX=$(bash /tmp/mkfix.sh); python3 -c "
from pathlib import Path
import experimental_settings.schema as S
S.ROOT = Path('$FIX')
cs = S.load(Path('$FIX/experimental_settings/train_probe.yaml'), 'ctool_q06', debug=False, overrides={})
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
ctool_q06 ['sample', 'build', 'train', 'eval'] False
appworld v1 gptoss120b qwen06
gptoss ['dtype', 'env_result', 'extra_flags', 'family']
['<|return|>'] high 2026-08-06
ctool None 1e-05 None
inject is None: True | build present: True
```
(the `agent_row` key list may differ in spelling of the `result:` columns, but
must contain `role`, `family` and every `result:` column and **no** `serving:`
column; `probe.lora_targets` stays `None` on the Setting — 3.3's fourth
resolution happens inside `key`, not on the dataclass.)

**C2. The debug overlay is sizes only and stage-scoped.**

```bash
FIX=$(bash /tmp/mkfix.sh); python3 -c "
from pathlib import Path
import experimental_settings.schema as S
S.ROOT = Path('$FIX')
c = S.load(Path('$FIX/experimental_settings/train_probe.yaml'), 'ctool_q06', debug=True, overrides={})[0]
print(c._debug, c.sample.n_tasks, c.sample.pieces, c.sample.max_steps, c.build.max_cuts, c.build.max_examples, c.train.max_steps, c.train.predict.cap, c.eval.bootstrap)
b = S.load(Path('$FIX/experimental_settings/baseline.yaml'), 'gptoss_aw', debug=True, overrides={})[0]
print(b.sample.n_tasks, b.build, b.train, b.inject)"
```
Expected: `True 3 1 6 8 64 20 100 50` then `3 None None None` — the overlay
touches no section the workflow does not name (5.6).

**C3. Overrides and the sweep.**

```bash
FIX=$(bash /tmp/mkfix.sh); python3 -c "
from pathlib import Path
import experimental_settings.schema as S
S.ROOT = Path('$FIX')
c = S.load(Path('$FIX/experimental_settings/train_probe.yaml'), 'ctool_q06', debug=False,
           overrides={'train.lr': '3.0e-4', 'probe.tuning': 'lora', 'sample.seeds': '[42, 67]'})[0]
print(c.train.lr, c.probe.tuning, c.sample.seeds)
import yaml, pathlib
p = pathlib.Path('$FIX/experimental_settings/train_probe.yaml')
d = yaml.safe_load(p.read_text()); d['ctool_q06']['sweep'] = {'train.lr': [1.0e-4, 3.0e-4], 'train.seed': [42, 67]}
p.write_text(yaml.safe_dump(d))
cs = S.load(p, 'ctool_q06', debug=False, overrides={})
print(len(cs)); print([x._name for x in cs]); print([x.train.lr for x in cs])
one = S.load(p, 'ctool_q06/train.lr=0.0003,train.seed=67', debug=False, overrides={})[0]
print(one._name, one.train.lr, one.train.seed)"
```
Expected:
```
0.0003 lora [42, 67]
4
['ctool_q06/train.lr=0.0001,train.seed=42', 'ctool_q06/train.lr=0.0001,train.seed=67', 'ctool_q06/train.lr=0.0003,train.seed=42', 'ctool_q06/train.lr=0.0003,train.seed=67']
[0.0001, 0.0001, 0.0003, 0.0003]
ctool_q06/train.lr=0.0003,train.seed=67 0.0003 67
```
(the child name is `repr()` of the parsed value, 5.5, and a child name is
accepted anywhere a setting name is, 3.4.)

**C4. Each refusal of 5.7 fires, and names the field.** One command, one line per
case; every line must read `REFUSED` and the message must contain the quoted
field name:

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
run('unknown key',      d(lambda x: x['ctool_q06']['train'].__setitem__('lrr', 1.0)), tp, 'ctool_q06')
run('off-axis value',   d(lambda x: x['ctool_q06']['probe'].__setitem__('method', 'ctoool')), tp, 'ctool_q06')
run('bad instructions', d(lambda x: x['common']['data'].__setitem__('instructions', 'v9')), tp, 'ctool_q06')
run('bad split',        d(lambda x: x['common']['sample'].__setitem__('split', ['holdout'])), tp, 'ctool_q06')
run('wrong role',       d(lambda x: x['ctool_q06']['models'].__setitem__('probe', 'gptoss120b')), tp, 'ctool_q06')
run('bad effort',       d(lambda x: x['common'].__setitem__('generation', {'effort': 'ultra'})), tp, 'ctool_q06')
run('section not in workflow', d(lambda x: x['ctool_q06'].__setitem__('inject', {'theta': 0.5})), tp, 'ctool_q06')
run('type mismatch',    d(lambda x: x['ctool_q06']['train'].__setitem__('lr', '1e-5')), tp, 'ctool_q06')
run('sweep over debug field', d(lambda x: x['ctool_q06'].__setitem__('sweep', {'train.max_steps': [10, 20]})), tp, 'ctool_q06', debug=True)
run('override of swept field', d(lambda x: x['ctool_q06'].__setitem__('sweep', {'train.lr': [1.0e-4, 3.0e-4]})), tp, 'ctool_q06', overrides={'train.lr': '2.0e-4'})
run('missing reference', d(lambda x: x['cgen_q06']['eval'].__setitem__('theta_from', 'train_probe/nope')), tp, 'cgen_q06')
run('generator without theta_from', d(lambda x: x['cgen_q06']['eval'].pop('theta_from')), tp, 'cgen_q06')
run('probe section under inject', j(lambda x: x['p1e1_t080'].__setitem__('probe', {'tuning': 'lora'})), inj, 'p1e1_t080')
run('models.probe under inject',   j(lambda x: x['common']['models'].__setitem__('probe', 'qwen06')), inj, 'p1e1_t080')
run('theta unset',      j(lambda x: x['p1e1_t080']['inject'].pop('theta')), inj, 'p1e1_t080')
run('probe_gen is a param-only method', j(lambda x: x['p1e1_t080']['inject'].__setitem__('probe_gen', 'train_probe/cparam_q06')), inj, 'p1e1_t080')
run('fire_nth_cut under no_probe', j(lambda x: x['no_probe_t080']['inject'].__setitem__('fire_nth_cut', 3)), inj, 'no_probe_t080')
run('baseline split not a superset', j(lambda x: x['p1e1_t080']['inject'].__setitem__('split', ['train', 'dev', 'test'])) if False else j(lambda x: x['p1e1_t080']['inject'].__setitem__('seeds', [42, 67])), inj, 'p1e1_t080')
PY
```
Expected: 18 lines, every one `REFUSED`, each message naming the offending field
(`train.lrr`, `probe.method`, `data.instructions`, `sample.split`,
`models.probe`, `generation.effort`, `inject`, `train.lr`, `train.max_steps`,
`train.lr`, `eval.theta_from`, `eval.theta_from`, `probe`, `models.probe`,
`inject.theta`, `inject.probe_gen`, `inject.fire_nth_cut`, `score.baseline`).
The `probe_gen is a param-only method` case needs a `cparam_q06` setting in the
fixture's `train_probe.yaml`; the command adds it, or the implementer adds two
lines to the fixture and says so.

**C5. Inheritance and its per-group scope (5.4).**

```bash
FIX=$(bash /tmp/mkfix.sh); python3 - "$FIX" <<'PY'
import sys, yaml, copy
from pathlib import Path
import experimental_settings.schema as S
FIX = Path(sys.argv[1]); S.ROOT = FIX
inj = FIX / 'experimental_settings/inject.yaml'
tp = FIX / 'experimental_settings/train_probe.yaml'
c = S.load(inj, 'p1e1_t080', debug=False, overrides={})[0]
print('inherited build fields:', {f: getattr(c.build, f) for f in S.PROBE_TEXT_FIELDS})
print('probe row absent:', c.models.probe is None and c.models.probe_row is None)
d = yaml.safe_load(tp.read_text()); d['common']['build'] = {'hist_rounds': 5}
tp.write_text(yaml.safe_dump(d))
c2 = S.load(inj, 'p1e1_t080', debug=False, overrides={})[0]
print('inherited after the build edit:', c2.build.hist_rounds)
d2 = yaml.safe_load(inj.read_text()); d2['p1e1_t080']['data'] = {'instructions': 'v1', 'env': 'appworld'}
d2['p1e1_t080']['generation'] = {'temperature': 0.7}
inj.write_text(yaml.safe_dump(d2))
try:
    S.load(inj, 'p1e1_t080', debug=False, overrides={}); print('stated-differently: NOT REFUSED')
except Exception as ex: print('stated-differently: REFUSED', str(ex)[:90])
d2['p1e1_t080']['meta'] = {'override': ['generation.temperature']}
inj.write_text(yaml.safe_dump(d2))
c3 = S.load(inj, 'p1e1_t080', debug=False, overrides={})[0]
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
`build` stage) must not be consulted for the `build` group — that is what makes
the third line possible at all (5.4's scoping).

### 3.4 T04 — keys, run_dir, freeze

**D1. The key's shape and the 3.2 guarantees, over the fixture.**

```bash
FIX=$(bash /tmp/mkfix.sh); python3 - "$FIX" <<'PY'
import sys, re, copy
from pathlib import Path
import experimental_settings.schema as S
FIX = Path(sys.argv[1]); S.ROOT = FIX
tp = FIX / 'experimental_settings/train_probe.yaml'
c = S.load(tp, 'ctool_q06', debug=False, overrides={})[0]
k = {st: S.key(st, c) for st in ('sample', 'build', 'train', 'eval')}
for st, v in k.items():
    assert re.fullmatch(r'[0-9a-f]{12}', v), (st, v)
print(k)
print('determinism:', all(S.key(st, S.load(tp, 'ctool_q06', debug=False, overrides={})[0]) == v for st, v in k.items()))
d = S.load(tp, 'ctool_q06', debug=True, overrides={})[0]
print('debug separates:', S.key('train', d) != k['train'])
n = S.load(tp, 'ctool_q06', debug=False, overrides={'meta.notes': 'anything at all'})[0]
print('notes insensitive:', S.key('train', n) == k['train'])
lr = S.load(tp, 'ctool_q06', debug=False, overrides={'train.lr': '1.0e-5'})[0]
print('default restated == unset:', S.key('train', lr) == k['train'])
lr2 = S.load(tp, 'ctool_q06', debug=False, overrides={'train.lr': '3.0e-4'})[0]
print('lr moves train, not sample/build:', S.key('train', lr2) != k['train'],
      S.key('sample', lr2) == k['sample'], S.key('build', lr2) == k['build'])
ev = S.load(tp, 'ctool_q06', debug=False, overrides={'eval.risk': '[0.2]'})[0]
print('eval.risk moves eval only:', S.key('eval', ev) != k['eval'], S.key('train', ev) == k['train'])
pr = S.load(tp, 'ctool_q06', debug=False, overrides={'models.probe': 'qwen06'})[0]
print('fields block:', sorted(S.fields_of('train', c)))
print('models block:', sorted(S.models_of('train', c)), sorted(S.models_of('build', c)))
print('upstream block:', S.upstream_of('build', c), S.upstream_of('sample', c))
PY
```
Expected: four 12-hex keys; then `determinism: True`, `debug separates: True`,
`notes insensitive: True`, `default restated == unset: True`,
`lr moves train, not sample/build: True True True`,
`eval.risk moves eval only: True True`; `fields block: ['probe.method', ...]`
holding only fields that differ from their defaults; `models block: ['probe'] []`;
`upstream block: {'sample': '<12 hex>'} {}`.

**D2. The `VERSION` fold and the one carve-out.**

```bash
FIX=$(bash /tmp/mkfix.sh); python3 - "$FIX" <<'PY'
import sys
from pathlib import Path
import experimental_settings.schema as S
FIX = Path(sys.argv[1]); S.ROOT = FIX
tp, inj = FIX/'experimental_settings/train_probe.yaml', FIX/'experimental_settings/inject.yaml'
c = S.load(tp, 'ctool_q06', debug=False, overrides={})[0]
print(sorted(S.versions_of('train', c)))
i = S.load(inj, 'p1e1_t080', debug=False, overrides={})[0]
u = S.upstream_of('inject', i); print(sorted(u))
k0 = S.key('inject', i)
p = FIX/'eval/utils/probe_eval.py'; p.write_text('VERSION = 2\n')
i2 = S.load(inj, 'p1e1_t080', debug=False, overrides={})[0]
print('probe_eval VERSION moves the inject key:', S.key('inject', i2) != k0)
q = FIX/'train/utils/trainer.py'; q.write_text('VERSION = 2\n')
c2 = S.load(tp, 'ctool_q06', debug=False, overrides={})[0]
print('trainer VERSION moves train, not build:', S.key('train', c2) != S.key('train', c), S.key('build', c2) == S.key('build', c))
PY
```
Expected: the seven module paths of the train version list with the placeholders
substituted (`train/methods/ctool.py`, `eval/methods/ctool.py`,
`models/probe_models/qwen.py`, …); then
`['probe_gen.train', 'probe_score.eval', 'probe_score.train']`;
`probe_eval VERSION moves the inject key: True` (the eval key is carried, its two
stand-in VERSIONs are folded — 2.1, 2.2);
`trainer VERSION moves train, not build: True True`.

**D3. `run_dir`, `run_dir_of`, and the debug subtree.**

```bash
FIX=$(bash /tmp/mkfix.sh); python3 - "$FIX" <<'PY'
import sys
from pathlib import Path
import experimental_settings.schema as S
FIX = Path(sys.argv[1]); S.ROOT = FIX
tp = FIX/'experimental_settings/train_probe.yaml'
c = S.load(tp, 'ctool_q06', debug=False, overrides={})[0]
d = S.load(tp, 'ctool_q06', debug=True, overrides={})[0]
rd, dd = S.run_dir('train', c), S.run_dir('train', d)
print(rd.relative_to('%s/outputs' % FIX), dd.relative_to('%s/outputs' % FIX))
print(S.run_dir_of('train', S.key('train', c), debug=False) == rd,
      S.run_dir_of('train', S.key('train', d), debug=True) == dd)
print('nothing created:', not rd.exists() and not dd.exists())
PY
```
Expected: `train/<12 hex> debug/train/<12 hex>`, then `True True`, then
`nothing created: True` (3.2 rule 2).

**D4. `freeze` writes the projection, the `_` block, and refuses a collision.**

```bash
FIX=$(bash /tmp/mkfix.sh); python3 - "$FIX" <<'PY'
import sys, yaml
from pathlib import Path
import experimental_settings.schema as S
FIX = Path(sys.argv[1]); S.ROOT = FIX
tp = FIX/'experimental_settings/train_probe.yaml'
c = S.load(tp, 'ctool_q06', debug=False, overrides={})[0]
rd = S.run_dir('sample', c); rd.mkdir(parents=True)
S.freeze(c, 'sample', rd, {}, 'deadbeefcafe')
y = yaml.safe_load((rd/'settings.yaml').read_text())
print(sorted(k for k in y if not k.startswith('_')))
print(sorted(k for k in y if k.startswith('_')))
print(y['_stage'], y['_key'] == S.key('sample', c), y['_commit'], y['_debug'], y['_upstream'])
print('versions:', sorted(y['_versions'])[:3], len(y['_versions']))
print('diff:', yaml.safe_load((rd/'settings_diff.yaml').read_text()) == S.fields_of('sample', c))
print('no workflow line:', '_workflow' not in y)
c2 = S.load(tp, 'ctool_q06', debug=False, overrides={'sample.seeds': '[42, 67]'})[0]
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
(`sample`'s projection carries no `probe` and no `train` section — 3.4's whole
point — and the train projection carries `train.checkpoint_hours`, errata 5.)

**D5. `load_frozen` round-trips and refuses a removed field.**

```bash
FIX=$(bash /tmp/mkfix.sh); python3 - "$FIX" <<'PY'
import sys, yaml
from pathlib import Path
import experimental_settings.schema as S
FIX = Path(sys.argv[1]); S.ROOT = FIX
tp = FIX/'experimental_settings/train_probe.yaml'
c = S.load(tp, 'ctool_q06', debug=False, overrides={})[0]
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

**D6. `schema.py` still imports under all four interpreters** — rerun B1 after
T04, and paste it.

### 3.5 Selfcheck lines that apply to these files

`run.py selfcheck` does not exist yet; these are the duties it will take over,
and B1/B4 above are their stand-ins until it does:

1. `schema.py` imports under every interpreter in `constants/path_datasets.yaml`'s
   `venvs:` map (0.1, 6.3) — B1.
2. `schema.py`'s README annotation line reads `imports: none (repo)` and the
   `ast` graph agrees — B1's second half.
3. Every axis literal equals what is on disk: `data.env` vs the files under
   `data/environments/`, `data.instructions` vs the union of every environment's
   `INSTRUCTIONS` keys, the split axes vs the union of every `SPLIT_ROLE`,
   `probe.method` vs the intersection of `train/methods/` and `eval/methods/`,
   `inject.format` vs `FORMATS`, `inject.arm` vs `ARMS`, `generation.effort` vs
   the union of every family's `EFFORTS` (5.3) — B4.
4. Every module a `versions` cell names has exactly one column-zero
   `VERSION = <int>` line, and every `train/methods/<m>.py` and
   `eval/methods/<m>.py` pair declares the same `PROBE_KIND` (3.3, 2.6) — D2
   exercises the reader; the repo-wide sweep is `run.py`'s.
5. Every alias in `models/table.yaml` has a row in `constants/path_models.yaml`
   (6.1) — A4 plus the models folder's own check.

---

## 4. Acceptance needing a GPU, another host, or the whole tree

No file in this folder touches a GPU, so **there is no GPU acceptance**. Four
checks are for the main session:

**G1. The hosts inventory is true** (cross-host, read-only):

```bash
for h in tokyo105 tokyo106 tokyo107 tokyo108; do
  printf '%s ' $h; ssh -o BatchMode=yes $h 'hostname; nvidia-smi -L | wc -l' | tr '\n' ' '; echo
done
```
Must show, per line, the host answering and a card count equal to the `cards:`
value in `constants/path_outputs.yaml` (tokyo105 → 4, the other three → 8), and
tokyo105 must answer `shiga`, tokyo108 `saitama` — the two aliases the file
records.

**G2. The outputs root is reachable and writable from a compute host** (the
records of a `sample` run are written there by pieces on other machines):

```bash
ssh -o BatchMode=yes tokyo106 'd=/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/debug; \
  touch $d/.probe_from_tokyo106 && ls -l $d/.probe_from_tokyo106 && rm $d/.probe_from_tokyo106 && echo WRITABLE'
```
Must print `WRITABLE`.

**G3. The real-tree run of section 3's fixture checks.** After every other folder
has merged, rerun B4, C1–C5 and D1–D5 **without** the fixture — with
`S.ROOT` left at the repo root and the real `models/table.yaml`,
`data/environments/appworld.py`, `models/agent_models/gptoss.py`,
`models/probe_models/qwen.py` and the real `VERSION` lines. Every expected
outcome above holds unchanged except the key values themselves, which are the
real ones. This is the run that proves the fixture was not lying; it is listed
here because no single ticket can run it.

**G4. Arm the hook.** The main session merges the snippet of 1.9 into
`.claude/settings.json`, then re-runs A7 through the harness by attempting a real
edit to `experimental_settings/debug.yaml` in a scratch session and confirming
the refusal. An implementer must not do this: it changes the harness
configuration.

---

## 5. Tickets

### T01 — constants, the setting files, and the read-only hook

**Files.** `constants/path_datasets.yaml`, `constants/path_outputs.yaml`,
`constants/path_models.yaml`, `experimental_settings/debug.yaml`,
`experimental_settings/baseline.yaml`, `experimental_settings/train_probe.yaml`,
`experimental_settings/inject.yaml`, `.claude/hooks/settings_readonly.sh`.

**What to do.** Write the eight files exactly as sections 1.1, 1.2, 1.3, 1.5,
1.6, 1.7, 1.8 and 1.9 give them: the three constants files with the paths and
the inventory as written (dropping any `path_models.yaml` row whose directory is
gone, and saying which), the four setting files verbatim, then the hook script
last. Do not edit `.claude/settings.json`; put the registration snippet in the
report. Add the seven data files and the hook to `README.md`'s tree section (a
data file's line is path + one sentence + `read by:`, no venv line).

**Acceptance.** A1–A7 of section 3.1, each command with its output pasted.

**Needs from other folders.** None.

### T02 — `schema.py`: dataclasses, axes, and the stage table

**Files.** `experimental_settings/schema.py` (new).

**What to do.** Section 1.4.1 down to and including `STAGES`: the module
docstring and `# venv: any` header, `from __future__ import annotations`, `ROOT`,
the eleven section dataclasses plus `Predict` and `Setting` with the defaults and
one-line comments of contracts 5.2, `THETA_GRID`, `AXES`, `RETIRED`,
`REQUIRED_FIELDS`, `PROBE_TEXT_FIELDS` (1.7), `STAGES` copied from this plan, and
the two source-text readers `module_version` and `module_literal` (3.3's literal
rule: column zero, exactly once, `ast.literal_eval`, never an import; raise
naming the file on zero matches and on more than one). No loader yet: `load`,
`key`, `run_dir`, `run_dir_of`, `freeze` and `load_frozen` are T03 and T04.

**Acceptance.** B1–B5 of section 3.2.

**Needs from other folders.** None. `STAGES` names module paths as strings and
never opens them.

### T03 — `schema.py`: the loader

**Files.** `experimental_settings/schema.py` (edit).

**What to do.** `load(workflow_file, setting_name, *, debug, overrides)` per
section 1.4.1's behaviour list: the merge order of 5.7 with sweep expansion
between steps 3 and 4 (5.5), the stage-scoped debug overlay (5.6), the
command-line overrides (errata 9), the axis and `RETIRED` validation (5.3), the
model-row expansion (6.1, 5.2), the null resolutions against the family and
backbone modules (5.2, 3.3's literal rule), reference resolution with the
per-group inheritance and agreement rule (5.4), and every refusal of 5.7 plus
errata 8 and 11. Materialise sections by errata 6; map sections to stages by
errata 7.

**Acceptance.** C1–C5 of section 3.3, on the fixture of 3.0. If a real
`models/table.yaml` and `data/environments/appworld.py` are already on the
branch, run C1 once more against the repo root and paste both.

**Needs from other folders** (as source text, satisfied by the fixture during
implementation and for real at G3): `models/table.yaml` (rows `gptoss120b`,
`qwen06`); `models/agent_models/gptoss.py` (`NAME`, `STOP`, `EFFORTS`,
`DEFAULT_EFFORT`, `DEFAULT_DATE`); `models/probe_models/qwen.py`
(`LORA_TARGETS`); `data/environments/appworld.py` (`INSTRUCTIONS` with key `v1`,
`SPLIT_ROLE`); `train/methods/{ctool,cgen,cparam}.py` (`PROBE_KIND`,
`CHECKPOINT_META`, for the generator and `probe_gen` refusals).

### T04 — `schema.py`: keys, the run directory, freeze

**Files.** `experimental_settings/schema.py` (edit).

**What to do.** `fields_of`, `models_of`, `upstream_of`, `versions_of`, then
`key` (3.3's payload, errata 2's canonical form, the four pre-diff resolutions,
the `probe_score.eval` carve-out, the four reference fields excluded from
`fields`), `run_dir` and `run_dir_of` (3.4, reading only
`constants/path_outputs.yaml`), `freeze` (3.4: the stage projection, the `_`
block of 1.5, temp-name-and-rename, the `settings_diff.yaml` collision check and
the per-field merge of the non-keyed request fields) and `load_frozen` (5.1,
2.6). `key` returns 12 lowercase hex characters and never touches the output
tree.

**Acceptance.** D1–D6 of section 3.4, on the fixture of 3.0.

**Needs from other folders** (source text only, one `VERSION = <int>` line each;
the fixture stands in during implementation, G3 is the real run):
`agent/{loop,generate,inject,inject_format}.py`,
`data/{task_record,example,prediction,probe_input,build_dataset}.py`,
`data/environments/{__init__,appworld}.py`,
`models/agent_models/{gptoss,service}.py`,
`models/probe_models/{base,qwen,service}.py`, `train/utils/trainer.py`,
`train/methods/{ctool,cgen,cparam}.py`, `eval/utils/probe_eval.py`,
`eval/methods/{ctool,cgen,cparam}.py`, `eval/score_run.py`.

---

## 6. Contract errata settled here

Appended verbatim to `.scratch/from-zero/contract-errata.md`.

1. **3.1**: `key` raises `NotImplementedError` until the hash is implemented last
   -> the settings build implements `key` in full in its last ticket (T04), after
   the loader; nothing ships raising `NotImplementedError`, because `run.py`,
   every skip test and every acceptance command need a path.
2. **3.3**: `canonical_json` is named but not defined -> it is
   `json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)`
   encoded UTF-8, hashed with `sha256`, first 12 hex characters.
3. **Part 2 opening**: `STAGES` values are "strings, tuples and flat mappings of
   strings" -> the literal also holds ints, bools and `None` (the piece rule's
   counts and modes, the `cards` column), and its cell set is fixed as
   `sections`, `models`, `upstream`, `program`, `venv`, `pieces`, `cards`,
   `done_writer`, `projection`, `projection_generator`, `versions`.
4. **2.1 / 2.2**: the upstream and version cells are prose -> `upstream` is a
   tuple of flat mappings `{name, source, stage, key, when?}` with `source`
   `"same"` or `"ref:<dotted field>"`, `key` `"fold"` or `"carry"` (the one
   `carry` is `inject.probe_score`'s eval key), and `when` one of `generator`,
   `in_workflow`, `set`; `versions` and `program` entries carry the placeholders
   `{env}`, `{family}`, `{backbone}`, `{method}`, `{probe_score_method}`,
   substituted from the setting.
5. **3.4**: the projection names five non-keyed request fields -> a `train` run's
   projection also carries `train.checkpoint_hours`, the only other non-keyed
   field a stage program reads.
6. **5.1**: "a section the merged setting does not hold is `None`" without saying
   which sections it holds -> `meta`, `data`, `models` and `generation` are always
   materialised; a stage section is materialised when the file's `workflow:` names
   its stage; `build` is additionally materialised on an inject setting, carrying
   the inherited `PROBE_TEXT_FIELDS`; everything else is `None`, and on a workflow
   containing `inject` both `models.probe` and `models.probe_row` are `None`.
7. **5.7**: "a section for a stage the file's `workflow:` line does not name"
   without a section-to-stage map -> the map is `sample`->sample, `build`->build,
   `probe`->train, `train`->train, `eval`->eval, `inject`->inject,
   `score`->score; `meta`, `data`, `models` and `generation` are never stage
   sections.
8. **5.7**: the refusal list holds no type check -> the loader also refuses a
   value whose type does not match its field's declared type, naming the field,
   the declared type and the value; PyYAML (5.4.1 and 6.0.3, measured
   2026-09-17) parses `1e-5` as a **string** and `1.0e-5` as a float, so every
   setting YAML writes floats with a decimal point.
9. **5.1 / 5.7**: `load`'s `overrides: dict` is untyped -> it is
   `dict[str, str]`, dotted field name to the raw command-line string, each
   parsed with `yaml.safe_load`; and a `<workflow>/<setting>` reference resolves
   against `workflow_file.parent`.
10. **5.2**: `eval.theta_grid`'s default is written `0.500..0.975 step 0.025` ->
    it is the explicit 20-element literal `[0.5, 0.525, ..., 0.975]`
    (`legacy/pipeline/eval/eval_tool.py:51`), so the default cannot drift.
11. **5.2**: four fields are marked `required` with no mechanism -> they default
    to `None`, `REQUIRED_FIELDS = ("inject.theta", "inject.probe_score",
    "inject.probe_gen")` lists them (`eval.theta_from` is required only for a
    generator method), and the loader refuses a `None` at the end of the merge,
    naming the field.
12. **0.2 tree line for `.claude/hooks/settings_readonly.sh`**: the script is
    named and nothing arms it -> the implementer ships the script only, and the
    main session installs the `.claude/settings.json` PreToolUse entry (an agent
    does not edit its own harness configuration); until it is installed the hook
    refuses nothing.
13. **6.3**: `path_outputs.yaml`'s `login_host` is "gyb sets it once" -> the
    build writes `shiga`, the value `hostname` returns on this machine, which is
    `tokyo105`'s alias in the same file's `hosts:` list.
14. **experimental_settings/*.yaml**: the contracts fix the schema but not the
    owner's settings -> the build ships one workflow file per tree line with the
    named settings `baseline/gptoss_aw`, `train_probe/ctool_q06`,
    `train_probe/cgen_q06`, `inject/p1e1_t080` and `inject/no_probe_t080`, whose
    values are schema defaults except where a required field or a reference
    forces one; the owner overwrites them.
15. **5.7**: the merge of one section between `common:` and a named setting is
    undefined -> sections merge per field; a list field is replaced, never
    appended.
16. **3.2 / 3.3**: the repo-relative reads have no stated base -> `schema.ROOT =
    Path(__file__).resolve().parents[1]`, and every repo-relative read
    (`models/table.yaml`, `constants/*.yaml`, a module's source text) goes
    through it, which is also what lets an acceptance command point the loader at
    a fixture tree.
