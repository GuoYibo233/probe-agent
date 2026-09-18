"""The setting schema: the dataclasses, the stage table, and the loader that reads a YAML file against them (file -> setting, diff, key)."""
from __future__ import annotations

import ast
import hashlib
import itertools
import json
from dataclasses import dataclass, field, fields as dc_fields
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]     # every repo-relative read goes through it


class SchemaError(Exception):
    """A setting file, an override or a frozen settings.yaml could not be loaded."""


# ---------------------------------------------------------------------------
# 1. Declarations: the dataclasses, the axis literals, the stage table.
# ---------------------------------------------------------------------------

THETA_GRID = [0.5, 0.525, 0.55, 0.575, 0.6, 0.625, 0.65, 0.675, 0.7, 0.725,
              0.75, 0.775, 0.8, 0.825, 0.85, 0.875, 0.9, 0.925, 0.95, 0.975]


@dataclass
class Meta:
    notes: str = ""                            # what this experiment is for
    override: list[str] = field(default_factory=list)  # dotted field names this setting may state differently from the runs it references


@dataclass
class Data:
    env: str = "appworld"                       # which benchmark environment
    instructions: str = "v1"                    # which variant of the environment's developer message


@dataclass
class Models:
    agent: str = "gpt_oss_120b"                   # the agent model, an alias string
    probe: str | None = "qwen3_0pt6b"                 # the probe backbone; likewise
    agent_row: dict | None = None                # read-only, written by the loader (5.2)
    probe_row: dict | None = None                # read-only, written by the loader (5.2)


@dataclass
class Generation:
    temperature: float = 1.0                    # sampling temperature
    top_p: float | None = None                   # only sent when set
    max_step_tokens: int = 8192                  # the per-step generation budget
    stop: list[str] | None = None                 # stop strings; null takes the family module's STOP
    effort: str | None = None                     # the family's reasoning tier; null takes DEFAULT_EFFORT
    date: str | None = None                       # the date pinned into the system message; null takes DEFAULT_DATE


@dataclass
class Sample:
    split: list[str] = field(default_factory=lambda: ["train", "dev", "test"])  # which task splits to run
    seeds: list[int] = field(default_factory=lambda: [42])  # one task run per seed
    tasks: list[str] | None = None                # restrict to these task ids
    n_tasks: int | None = None                    # cap on tasks per split
    max_steps: int = 30                          # steps before the run is cut off
    store_token_ids: bool = False                # keep the generated token ids in the record
    pieces: int = 6                              # how many loop processes
    replicas: int = 1                            # how many agent servers


@dataclass
class Build:
    max_cuts: int = 64                           # cuts kept per event, thinned evenly when there are more
    min_think: int = 40                          # characters of thinking below which a step has no cuts
    hist_rounds: int = 3                         # tool rounds kept in the probe's text
    probe_result_cap: int = 400                  # characters per environment result inside the probe's text
    weight_mode: str = "uniform"                 # uniform (weight 1 per cut) or per_event (1/n)
    split_source: str = "env"                    # env = the benchmark's official task lists; hash = a stable hash split
    split_ratio: list[float] = field(default_factory=lambda: [0.8, 0.1, 0.1])  # train/val/test shares, used only under hash
    max_examples: int | None = None               # cap on examples per split; for --debug
    max_abort_frac: float = 0.02                 # refuse to build when a larger share of records aborted


@dataclass
class Probe:
    method: str = "ctool"                        # which probe method this run trains and evaluates
    tuning: str = "full"                         # how the backbone is tuned
    lora_r: int = 16                             # LoRA rank, read under lora
    lora_alpha: int = 32                          # LoRA alpha
    lora_dropout: float = 0.05                   # LoRA dropout
    lora_targets: list[str] | None = None          # null takes the backbone file's list


@dataclass
class Predict:
    splits: list[str] = field(default_factory=lambda: ["val", "test"])  # which splits get prediction rows
    cap: int | None = None                        # rows per split; for --debug
    max_new: int = 96                            # generation budget per row for cgen and cparam


@dataclass
class Train:
    lr: float = 1.0e-5                           # learning rate
    epochs: int = 1                              # passes over the training split
    warmup_ratio: float = 0.05                   # share of steps spent warming the schedule
    seed: int = 42                               # seeds the init, the shuffle and the dropout
    max_len: int = 8192                          # tokens per event; a longer event is dropped whole
    events_per_mb: int = 4                        # events in one logical minibatch
    accum: int = 2                               # logical minibatches per optimizer step
    grad_ckpt: bool = False                       # gradient checkpointing; kept in the key because it changes kernels
    max_steps: int | None = None                  # stop early; for --debug
    align_check: bool = True                      # run the packed-versus-plain loss gate before training
    checkpoint_hours: float = 2.0                 # how often last/ is written
    predict: Predict = field(default_factory=Predict)


@dataclass
class Eval:
    risk: list[float] = field(default_factory=lambda: [0.10, 0.05])  # the wrong-fire rates theta is frozen at
    theta_grid: list[float] = field(default_factory=lambda: list(THETA_GRID))  # the thetas swept on val
    bootstrap: int = 1000                        # resamples for the interval, grouped by task
    bootstrap_seed: int = 42                      # seeds the resampling
    theta_from: str | dict | None = None           # ref; required when the method's PROBE_KIND is generator


@dataclass
class Inject:
    split: list[str] = field(default_factory=lambda: ["test"])  # which task splits to run
    seeds: list[int] = field(default_factory=lambda: [42])  # one task run per seed
    tasks: list[str] | None = None                # restrict to these task ids
    n_tasks: int | None = None                    # cap on tasks per split
    max_steps: int = 30                          # steps before the run is cut off
    probe_score: str | dict | None = None          # ref; required: the setting whose ctool probe decides when to fire
    probe_gen: str | dict | None = None            # ref; required: the setting whose probe writes the whole call
    theta: float | None = None                    # required: the confidence threshold
    arm: str = "probe"                            # which control arm
    format: str = "p1_e1"                         # how an early result is written into the stream
    fire_nth_cut: int = 0                         # fire at the n-th cut instead of by score; 0 = by score
    max_inject_per_step: int = 1                  # injections allowed per step
    max_cuts: int = 64                            # cuts scored per step
    max_new: int = 96                             # the probe's generation budget per fire
    store_token_ids: bool = True                  # keep the generated and discarded token ids in the record
    pieces: int = 6                               # how many loop processes
    replicas: int = 1                             # how many agent servers


@dataclass
class Score:
    baseline: str | dict | None = None             # ref; the run to pair against; null means report this run's own numbers
    by_seed: bool = True                          # report mean and spread across seeds


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
    _workflow: list[str] = field(default_factory=list)  # the file's workflow: line; never written to settings.yaml
    _debug: bool = False
    _name: str = ""                              # the named setting, or "<name>/<field>=<v>,..." for a sweep child
    _file: str = ""                               # the workflow file's stem, the first half of a reference
    _stage: str | None = None                     # filled by load_frozen / freeze
    _key: str | None = None
    _upstream: dict = field(default_factory=dict)
    _versions: dict = field(default_factory=dict)
    _commit: str | None = None
    _resolved: dict = field(default_factory=dict)


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
                 "eval/utils/probe_eval.py#MATCH_VERSION.{method}",
                 "data/training_data.py", "data/probe_output.py",
                 "models/probe_models/base.py", "models/probe_models/{backbone}.py"),
  },
  "eval": {
    "sections": ("probe.method", "eval"),
    "models": (),
    "upstream": ({"name": "train", "source": "same", "stage": "train", "key": "fold"},
                 {"name": "theta_from.eval", "source": "ref:eval.theta_from",
                  "stage": "eval", "key": "fold", "when": "generator"}),
    "program": "eval.utils.probe_eval",
    "venv": "any",
    "pieces": (("cpu", 1, None),),
    "cards": False,
    "done_writer": "stage",
    "projection": (),
    "projection_generator": ("data",),
    "versions": ("eval/utils/probe_eval.py", "data/probe_output.py"),
  },
  "inject": {
    "sections": ("data", "models.agent", "generation",
                 "build.min_think", "build.hist_rounds", "build.probe_result_cap",
                 "inject.split", "inject.max_steps", "inject.theta", "inject.format",
                 "inject.arm", "inject.fire_nth_cut", "inject.max_inject_per_step",
                 "inject.max_cuts", "inject.max_new", "inject.store_token_ids"),
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
                 "eval/utils/probe_eval.py",
                 "eval/utils/probe_eval.py#MATCH_VERSION.{probe_score_method}"),
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

# The section-to-stage map (errata, spec section "the section-to-stage map").
SECTION_STAGE = {
    "sample": "sample", "build": "build", "probe": "train", "train": "train",
    "eval": "eval", "inject": "inject", "score": "score",
}
ALWAYS_SECTIONS = ("meta", "data", "models", "generation")
SECTION_CLASSES = {
    "meta": Meta, "data": Data, "models": Models, "generation": Generation,
    "sample": Sample, "build": Build, "probe": Probe, "train": Train,
    "eval": Eval, "inject": Inject, "score": Score,
}
REF_FIELDS = ("eval.theta_from", "inject.probe_score", "inject.probe_gen", "score.baseline")
MODELS_READONLY = ("agent_row", "probe_row")


# ---------------------------------------------------------------------------
# Small readers: source text, YAML config files (3.3's literal rule).
# ---------------------------------------------------------------------------


def _column_zero_matches(rel_path: str, name: str) -> list:
    """Every column-zero module-level assignment of `name` in `rel_path`, read with ast.literal_eval, never by importing."""
    tree = ast.parse((ROOT / rel_path).read_text())
    matches = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and node.col_offset == 0:
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    matches.append(ast.literal_eval(node.value))
    return matches


def _column_zero_literal(rel_path: str, name: str) -> Any:
    """Read the one column-zero module-level assignment of `name` in `rel_path`, with ast.literal_eval, never by importing."""
    matches = _column_zero_matches(rel_path, name)
    if not matches:
        raise SchemaError(f"{rel_path}: no column-zero assignment to {name!r}")
    if len(matches) > 1:
        raise SchemaError(
            f"{rel_path}: {len(matches)} column-zero assignments to {name!r}, expected exactly one")
    return matches[0]


def module_version(rel_path: str) -> int:
    """The one column-zero VERSION of the module at rel_path, read as source text (3.3)."""
    return _column_zero_literal(rel_path, "VERSION")


def module_literal(rel_path: str, name: str) -> Any:
    """The one column-zero literal named `name` in the module at rel_path, read as source text (3.3)."""
    return _column_zero_literal(rel_path, name)


def _check_version_history(rel_path: str, table: Any, version: int) -> None:
    """Refuse, naming the file, a VERSION_HISTORY the key path cannot read (errata "3.3 / 8.6").

    The strict shape -- one entry with a non-empty `why` for every version from 2 to VERSION --
    is `run.py selfcheck`'s to enforce, so a missing `why` passes here.
    """
    stages = tuple(STAGES)
    if not isinstance(table, dict):
        raise SchemaError(
            f"{rel_path}: VERSION_HISTORY is a {type(table).__name__}, expected a mapping of "
            "version -> entry")
    for entry_version, entry in table.items():
        if isinstance(entry_version, bool) or not isinstance(entry_version, int):
            raise SchemaError(
                f"{rel_path}: VERSION_HISTORY key {entry_version!r} is a "
                f"{type(entry_version).__name__}, expected an int from 2 to {version}")
        if not 2 <= entry_version <= version:
            raise SchemaError(
                f"{rel_path}: VERSION_HISTORY key {entry_version} is outside 2..{version}, this "
                "file's VERSION")
        if not isinstance(entry, dict):
            raise SchemaError(
                f"{rel_path}: VERSION_HISTORY[{entry_version}] is a {type(entry).__name__}, "
                "expected a mapping")
        if "stale" in entry:
            stale = entry["stale"]
            if not isinstance(stale, (tuple, list)):
                raise SchemaError(
                    f"{rel_path}: VERSION_HISTORY[{entry_version}]['stale'] is a "
                    f"{type(stale).__name__}, expected a tuple of stage names of {stages}")
            for name in stale:
                if name not in STAGES:
                    raise SchemaError(
                        f"{rel_path}: VERSION_HISTORY[{entry_version}]['stale'] names {name!r}, "
                        f"which is not one of {stages}")


def version_history(rel_path: str) -> dict:
    """The one column-zero VERSION_HISTORY of the module at rel_path; a file with no such literal has an empty table (errata "3.3 / 8.6")."""
    matches = _column_zero_matches(rel_path, "VERSION_HISTORY")
    if not matches:
        return {}
    if len(matches) > 1:
        raise SchemaError(
            f"{rel_path}: {len(matches)} column-zero assignments to 'VERSION_HISTORY', "
            "expected exactly one")
    table = matches[0]
    _check_version_history(rel_path, table, module_version(rel_path))
    return table


def _stale_at(table: dict, entry_version: int, stage: str) -> bool:
    """Whether the bump to `entry_version` made `stage`'s existing outputs unusable (errata "3.3 / 8.6")."""
    entry = table.get(entry_version)
    if entry is None:
        return True                            # a version with no entry is stale for every stage
    if "stale" not in entry:
        return True                            # an unstated bump invalidates every stage
    return stage in entry["stale"]


def effective_version(rel_path: str, stage: str) -> int:
    """The version of the module at rel_path that `stage`'s key folds: the highest version from 2 to VERSION that made `stage` stale, else 1 (errata "3.3 / 8.6")."""
    version = module_version(rel_path)
    table = version_history(rel_path)
    for entry_version in range(version, 1, -1):
        if _stale_at(table, entry_version, stage):
            return entry_version
    return 1


def _read_yaml(rel_path: str) -> dict:
    return yaml.safe_load((ROOT / rel_path).read_text()) or {}


def _table() -> dict:
    """models/table.yaml, alias -> row."""
    return _read_yaml("models/table.yaml")


def _datasets_config() -> dict:
    return _read_yaml("constants/path_datasets.yaml")


def _outputs_config() -> dict:
    return _read_yaml("constants/path_outputs.yaml")


def _env_module(env: str) -> str:
    return f"data/environments/{env}.py"


def _family_module(family: str) -> str:
    return f"models/agent_models/{family}.py"


def _backbone_module(family: str) -> str:
    return f"models/probe_models/{family}.py"


# ---------------------------------------------------------------------------
# 2. load and every refusal of 5.7.
# ---------------------------------------------------------------------------


def _workflow_sections(workflow: list[str]) -> set[str]:
    return {sec for sec, stage in SECTION_STAGE.items() if stage in workflow}


def _yaml_allowed_sections(workflow: list[str]) -> set[str]:
    return set(ALWAYS_SECTIONS) | _workflow_sections(workflow)


def _object_sections(workflow: list[str]) -> set[str]:
    sections = _yaml_allowed_sections(workflow)
    if "inject" in workflow:
        sections = sections | {"build"}
    return sections


def _dc_default_dict(cls: type) -> dict:
    """A dict of field name -> default value for a dataclass; a nested dataclass field stays a nested dict."""
    inst = cls()
    out = {}
    for f in dc_fields(cls):
        if f.name in MODELS_READONLY:
            continue
        value = getattr(inst, f.name)
        out[f.name] = _dc_default_dict(type(value)) if hasattr(value, "__dataclass_fields__") else value
    return out


def _section_field_names(cls: type) -> set[str]:
    return {f.name for f in dc_fields(cls) if f.name not in MODELS_READONLY}


_TYPE_WORDS = {"str": str, "int": int, "float": float, "bool": bool, "None": type(None)}


def _annot_types(annot: str) -> tuple:
    out = []
    for part in annot.split("|"):
        part = part.strip()
        if part in _TYPE_WORDS:
            out.append(_TYPE_WORDS[part])
        elif part.startswith("list"):
            out.append(list)
        elif part.startswith("dict"):
            out.append(dict)
        else:
            out.append(dict)   # a nested dataclass field (Predict) arrives from YAML as a dict
    return tuple(out)


def _field_type(cls: type, name: str) -> tuple:
    for f in dc_fields(cls):
        if f.name == name:
            return _annot_types(f.type)
    raise SchemaError(f"{cls.__name__}.{name}: not a field of this section")


def _type_ok(value: Any, types: tuple) -> bool:
    if type(value) in types:
        return True
    if float in types and type(value) is int:
        return True
    return False


def _apply_fields(dst: dict, overlay: dict, cls: type, prefix: str, authored: set[str]) -> None:
    """Merge `overlay` onto `dst` (a section dict), per field, list fields replaced whole; recurse into a nested dataclass field."""
    names = _section_field_names(cls)
    for key, value in overlay.items():
        if key not in names:
            raise SchemaError(f"{prefix}.{key}: not a field of this section")
        f = next(f for f in dc_fields(cls) if f.name == key)
        default = getattr(cls(), key)
        if hasattr(default, "__dataclass_fields__"):
            if not isinstance(value, dict):
                raise SchemaError(f"{prefix}.{key}: expected a mapping, got {type(value).__name__}")
            _apply_fields(dst[key], value, type(default), f"{prefix}.{key}", authored)
        else:
            dst[key] = value
            authored.add(f"{prefix}.{key}")


def _get_dotted(full: dict, dotted: str) -> Any:
    section, _, rest = dotted.partition(".")
    node = full[section]
    for part in rest.split("."):
        node = node[part]
    return node


def _set_dotted(full: dict, dotted: str, value: Any) -> None:
    section, _, rest = dotted.partition(".")
    parts = rest.split(".")
    node = full[section]
    for part in parts[:-1]:
        node = node[part]
    node[parts[-1]] = value


def _debug_fields() -> set[str]:
    """The dotted field names debug.yaml sets, flattened."""
    doc = _read_yaml("experimental_settings/debug.yaml")
    out = set()
    for section, fields_ in doc.items():
        for key, value in fields_.items():
            if isinstance(value, dict):
                for sub in value:
                    out.add(f"{section}.{key}.{sub}")
            else:
                out.add(f"{section}.{key}")
    return out


def _refuse_probe_under_inject(workflow: list[str], dotted: str) -> None:
    """2.1 / 5.7: a setting whose workflow contains inject states no probe field and no models.probe.

    The refusal holds for the merged setting, so it fires whichever path set the value -- the YAML
    file, a sweep or a command-line override -- and names the field it refused on.
    """
    if "inject" not in workflow:
        return
    if dotted == "models.probe" or dotted.split(".", 1)[0] == "probe":
        raise SchemaError(
            f"{dotted}: a setting whose workflow contains inject may not state {dotted}; "
            "an inject run's probe comes from the settings inject.probe_score and inject.probe_gen name")


def _check_raw_sections(workflow: list[str], common: dict, named: dict, base_name: str) -> None:
    """5.7's 'a section for a stage the workflow does not name', evaluated against the raw file content only."""
    allowed = _yaml_allowed_sections(workflow)
    for d in (common, named):
        for key in d:
            if key not in allowed:
                raise SchemaError(f"{key}: no stage of this file's workflow reads this section")
    for d in (common, named):
        if "probe" in d:
            _refuse_probe_under_inject(workflow, "probe")
        if "probe" in d.get("models", {}):
            _refuse_probe_under_inject(workflow, "models.probe")


def _merge_one(workflow: list[str], common: dict, named: dict, *, debug: bool, overrides: dict,
                extra: dict) -> tuple[dict, set[str]]:
    """Steps 1-5 of 5.7's merge order, plus the sweep child's values applied between steps 3 and 4."""
    object_sections = _object_sections(workflow)
    full = {sec: _dc_default_dict(SECTION_CLASSES[sec]) for sec in object_sections}
    if "inject" in workflow:
        full["models"]["probe"] = None   # 2.1: an inject workflow names no models.probe

    authored: set[str] = set()
    for overlay in (common, named):
        for sec, section_overlay in overlay.items():
            if sec in full:
                _apply_fields(full[sec], section_overlay, SECTION_CLASSES[sec], sec, authored)

    for dotted, value in extra.items():
        _set_dotted(full, dotted, value)
        authored.add(dotted)

    if debug:
        for sec, section_overlay in _read_yaml("experimental_settings/debug.yaml").items():
            if sec in full and SECTION_STAGE.get(sec) in workflow:
                _apply_fields(full[sec], section_overlay, SECTION_CLASSES[sec], sec, set())

    for dotted, raw in overrides.items():
        _refuse_probe_under_inject(workflow, dotted)
        section, _, field_name = dotted.partition(".")
        if section not in SECTION_CLASSES or section not in full:
            raise SchemaError(f"{dotted}: not a field of the schema")
        try:
            _get_dotted(full, dotted)   # validates the whole dotted path exists, nested fields included
        except KeyError:
            raise SchemaError(f"{dotted}: not a field of the schema") from None
        _set_dotted(full, dotted, yaml.safe_load(raw))
        authored.add(dotted)

    return full, authored


def _sweep_children(sweep: dict, debug_fields: set[str], workflow: list[str]) -> list[tuple[str, dict]]:
    for dotted in sweep:
        _refuse_probe_under_inject(workflow, dotted)
        section, _, field_name = dotted.partition(".")
        if section not in SECTION_CLASSES:
            raise SchemaError(f"sweep.{dotted}: not a field of the schema")
        _field_type(SECTION_CLASSES[section], field_name.split(".")[0])
        if dotted in debug_fields:
            raise SchemaError(f"sweep.{dotted}: also set by debug.yaml, which would collapse the sweep")
    names = sorted(sweep)
    out = []
    for combo in itertools.product(*(sweep[n] for n in names)):
        extra = dict(zip(names, combo))
        suffix = ",".join(f"{n}={v!r}" for n, v in extra.items())
        out.append((suffix, extra))
    return out


def _type_check_section(section_dict: dict, cls: type, prefix: str) -> None:
    for f in dc_fields(cls):
        if f.name in MODELS_READONLY:
            continue
        value = section_dict[f.name]
        default = getattr(cls(), f.name)
        if hasattr(default, "__dataclass_fields__"):
            _type_check_section(value, type(default), f"{prefix}.{f.name}")
            continue
        types = _annot_types(f.type)
        if not _type_ok(value, types):
            raise SchemaError(
                f"{prefix}.{f.name}: {value!r} has type {type(value).__name__}, declared type is {f.type}")


def _check_role(table: dict, alias: str, expected_role: str, field_name: str) -> None:
    if alias not in table:
        raise SchemaError(f"{field_name}: {alias!r} is not a row of models/table.yaml")
    role = table[alias]["role"]
    if role != expected_role:
        raise SchemaError(f"{field_name}: {alias!r} has role {role!r}, expected {expected_role!r}")


def _model_row(table: dict, alias: str) -> dict:
    row = table[alias]
    return {"role": row["role"], "family": row["family"], **row["result"]}


def _method_kind(method: str) -> str:
    """The report shape of a probe method, read out of eval/utils/probe_eval.py's column-zero PROBE_KIND table."""
    table = module_literal("eval/utils/probe_eval.py", "PROBE_KIND")
    if method in table:
        return table[method]
    raise SchemaError(
        f"probe.method {method!r} is not a key of PROBE_KIND in eval/utils/probe_eval.py; "
        f"it holds {sorted(table)}")


def _ref_kind(value: Any) -> str:
    if isinstance(value, str):
        return "name"
    if isinstance(value, dict) and "key" in value:
        return "key"
    if isinstance(value, dict) and "dir" in value:
        return "dir"
    raise SchemaError(f"{value!r}: not a recognised reference (name, key: {{...}} or dir: {{...}})")


def _ref_entries(field_dotted: str) -> list[dict]:
    out = []
    for entry in STAGES.values():
        for u in entry["upstream"]:
            if u["source"] == f"ref:{field_dotted}":
                out.append(u)
    return out


def _ref_requirements(field_dotted: str) -> tuple[str, ...]:
    return tuple(u["stage"] for u in _ref_entries(field_dotted))


def _resolve_name_ref(value: str) -> Setting:
    stem, sep, name = value.partition("/")
    if not sep:
        raise SchemaError(f"{value!r}: a reference is <workflow>/<setting>")
    ref_file = ROOT / "experimental_settings" / f"{stem}.yaml"
    if not ref_file.exists():
        raise SchemaError(f"{value!r}: no such workflow file {ref_file}")
    results = load(ref_file, name, debug=False, overrides={})
    if len(results) != 1:
        raise SchemaError(
            f"{value!r}: names a swept setting with {len(results)} children; name a child directly")
    return results[0]


METHOD_REF_FIELDS = ("inject.probe_score", "inject.probe_gen")


def _pinned_method(field_dotted: str, value: dict, kind: str) -> str | None:
    """The probe method a pinned (key: / dir:) reference states in its `method:` sibling (owner ruling, 2026-09-17).

    `method:` sits beside `key:` or `dir:`, never inside them, so the stage set the pinned form
    carries stays exactly the stages the stage table requires. It is required on
    inject.probe_score and inject.probe_gen, whose method the loader has no other source for, and
    refused everywhere else.
    """
    stated = value.get("method")
    if field_dotted in METHOD_REF_FIELDS:
        if stated is None:
            raise SchemaError(
                f"a {kind}: reference of this field states the probe method as a sibling entry "
                f"'method: <one of {AXES['probe.method']}>'; method is required")
        if stated not in AXES["probe.method"]:
            raise SchemaError(f"method {stated!r} is not one of {AXES['probe.method']}")
        return stated
    if stated is not None:
        raise SchemaError(
            "a reference of this field states no 'method:'; only inject.probe_score and "
            "inject.probe_gen carry one")
    return None


def _resolve_ref(field_dotted: str, value: Any) -> tuple[str, Any, str | None]:
    """Resolve one reference field's stated value to ('setting', Setting, method) or ('keys', {stage: key}, method)."""
    try:
        if isinstance(value, dict) and "method" in value and "key" not in value and "dir" not in value:
            raise SchemaError(
                "a name-form reference states no 'method:'; the loader reads the method off the "
                "named setting, and 'method:' belongs to a key: or dir: reference")
        kind = _ref_kind(value)
        required = set(_ref_requirements(field_dotted))
        if kind == "name":
            setting = _resolve_name_ref(value)
            missing = required - set(setting._workflow)
            if missing:
                raise SchemaError(
                    f"{value!r}: workflow {setting._workflow} does not provide stage(s) {sorted(missing)}")
            method = setting.probe.method if setting.probe is not None else None
            return ("setting", setting, method)
        method = _pinned_method(field_dotted, value, kind)
        extra = set(value) - {kind, "method"}
        if extra:
            raise SchemaError(f"a {kind}: reference holds no entry {sorted(extra)}")
        got = set(value[kind])
        if got != required:
            raise SchemaError(f"pinned {kind} stages {sorted(got)} != required {sorted(required)}")
        if kind == "key":
            return ("keys", dict(value["key"]), method)
        return ("keys", {stage: Path(p).name for stage, p in value["dir"].items()}, method)
    except SchemaError as ex:
        raise SchemaError(f"{field_dotted}: {ex}") from ex


def _get_dotted_setting(setting: Setting, dotted: str) -> Any:
    section, _, rest = dotted.partition(".")
    node = getattr(setting, section)
    for part in rest.split("."):
        node = getattr(node, part)
    return node


_INHERIT_GROUPS = {
    "data": ("data.env", "data.instructions"),
    "models.agent": ("models.agent",),
    "generation": ("generation.temperature", "generation.top_p", "generation.max_step_tokens",
                    "generation.stop", "generation.effort", "generation.date"),
}


def _apply_inherit_group(full: dict, authored: set[str], override_perm: set[str],
                          dotted_fields: tuple[str, ...], ref_items: list[tuple[str, Setting]]) -> None:
    for dotted in dotted_fields:
        agreed, agreed_from = None, None
        for ref_name, ref_setting in ref_items:
            ref_value = _get_dotted_setting(ref_setting, dotted)
            if agreed_from is None:
                agreed, agreed_from = ref_value, ref_name
            elif ref_value != agreed:
                raise SchemaError(
                    f"{dotted}: {agreed_from!r} and {ref_name!r} disagree ({agreed!r} vs {ref_value!r})")
        if dotted in authored:
            stated = _get_dotted(full, dotted)
            if stated != agreed and dotted not in override_perm:
                raise SchemaError(
                    f"{dotted}: stated {stated!r} differs from the referenced run's {agreed!r}; "
                    "list it in meta.override to allow this")
        else:
            _set_dotted(full, dotted, agreed)


def _apply_inheritance(full: dict, authored: set[str],
                       refs: dict[str, tuple[str, Any, str | None]]) -> None:
    override_perm = set(full["meta"].get("override", []))
    setting_refs = {name: payload for name, (kind, payload, _method) in refs.items() if kind == "setting"}
    if not setting_refs:
        return
    for dotted_fields in _INHERIT_GROUPS.values():
        _apply_inherit_group(full, authored, override_perm, dotted_fields, list(setting_refs.items()))
    if "build" in full:
        build_refs = [(name, s) for name, s in setting_refs.items()
                      if name in ("inject.probe_score", "inject.probe_gen") and "build" in s._workflow]
        if build_refs:
            dotted_fields = tuple(f"build.{f}" for f in PROBE_TEXT_FIELDS)
            _apply_inherit_group(full, authored, override_perm, dotted_fields, build_refs)


def _resolve_generation(full: dict, agent_family: str) -> None:
    gen = full["generation"]
    if gen["stop"] is None:
        gen["stop"] = list(module_literal(_family_module(agent_family), "STOP"))
    if gen["effort"] is None:
        try:
            gen["effort"] = module_literal(_family_module(agent_family), "DEFAULT_EFFORT")
        except SchemaError:
            pass
    if gen["date"] is None:
        try:
            gen["date"] = module_literal(_family_module(agent_family), "DEFAULT_DATE")
        except SchemaError:
            pass


def _dict_to_dataclass(cls: type, d: dict):
    kwargs = {}
    for f in dc_fields(cls):
        if f.name in MODELS_READONLY:
            continue
        value = d[f.name]
        default = getattr(cls(), f.name)
        kwargs[f.name] = _dict_to_dataclass(type(default), value) if hasattr(default, "__dataclass_fields__") else value
    return cls(**kwargs)


def _to_setting(full: dict, workflow: list[str], file_stem: str, name: str, debug: bool) -> Setting:
    setting = Setting()
    setting._workflow = list(workflow)
    setting._debug = debug
    setting._name = name
    setting._file = file_stem
    for sec, cls in SECTION_CLASSES.items():
        if sec not in full:
            continue
        inst = _dict_to_dataclass(cls, full[sec])
        if sec == "models":
            inst.agent_row = full["models"].get("agent_row")
            inst.probe_row = full["models"].get("probe_row")
        setattr(setting, sec, inst)
    return setting


def _finalize(full: dict, authored: set[str], workflow: list[str], *, file_stem: str, name: str,
              debug: bool) -> Setting:
    for sec, cls in SECTION_CLASSES.items():
        if sec in full:
            _type_check_section(full[sec], cls, sec)

    for dotted, axis_values in AXES.items():
        section, _, field_name = dotted.partition(".")
        if section not in full:
            continue
        value = full[section].get(field_name)
        if value is None:
            continue
        values = value if isinstance(value, list) else [value]
        for v in values:
            if (dotted, v) in RETIRED:
                raise SchemaError(f"{dotted}: {v!r} is retired")
            if v not in axis_values:
                raise SchemaError(f"{dotted}: {v!r} is not one of {axis_values}")

    if "inject" in workflow and full["models"]["probe"] is not None:
        _refuse_probe_under_inject(workflow, "models.probe")

    if "inject" in full and full["inject"]["arm"] == "no_probe" and full["inject"]["fire_nth_cut"] > 0:
        raise SchemaError("inject.fire_nth_cut: must be 0 under arm: no_probe")

    for dotted in REQUIRED_FIELDS:
        if "inject" in full and _get_dotted(full, dotted) is None:
            raise SchemaError(f"{dotted}: is required and was not set")

    # Each reference field is resolved and checked in turn -- a field's own check runs right after
    # its resolution, so an unrelated field's mutation is refused before a later reference is even
    # opened. eval.theta_from and score.baseline are self-contained checks; inject.probe_score is
    # needed only for inheritance; inject.probe_gen's method check runs right after its resolution.
    refs: dict[str, tuple[str, Any, str | None]] = {}

    def _resolve_if_set(dotted: str) -> None:
        section, _, field_name = dotted.partition(".")
        if section not in full:
            return
        value = full[section].get(field_name)
        if value is None:
            return
        refs[dotted] = _resolve_ref(dotted, value)

    _resolve_if_set("eval.theta_from")
    if "eval" in full:
        method = full["probe"]["method"] if "probe" in full else None
        if method is not None:
            kind = _method_kind(method)
            if kind == "generator" and "eval.theta_from" not in refs:
                raise SchemaError("eval.theta_from: is required when probe.method's PROBE_KIND is generator")

    _resolve_if_set("score.baseline")
    if "score.baseline" in refs:
        kind, payload, _method = refs["score.baseline"]
        if kind == "setting":
            own_section = "inject" if "inject" in full else "sample"
            own_split = set(full[own_section]["split"])
            own_seeds = set(full[own_section]["seeds"])
            base_split = set(payload.sample.split)
            base_seeds = set(payload.sample.seeds)
            if not (own_split <= base_split and own_seeds <= base_seeds):
                raise SchemaError(
                    "score.baseline: baseline split/seeds are not a superset of this setting's "
                    f"{own_section}.split/seeds ({sorted(own_split)}/{sorted(own_seeds)} vs "
                    f"{sorted(base_split)}/{sorted(base_seeds)})")

    _resolve_if_set("inject.probe_score")

    # The whole-call-generator check reads the method the reference selects, which the name form
    # takes off the named setting and the key: / dir: form states in its method: sibling, so the
    # check runs the same way in all three forms (owner ruling, 2026-09-17).
    _resolve_if_set("inject.probe_gen")
    if "inject.probe_gen" in refs:
        gen_method = refs["inject.probe_gen"][2]
        checkpoint_meta = module_literal(f"train/methods/{gen_method}.py", "CHECKPOINT_META")
        gen_kind = _method_kind(gen_method)
        whole_call_generator = gen_kind == "generator" and checkpoint_meta.get("param_only") is False
        if whole_call_generator is False:
            raise SchemaError(
                f"inject.probe_gen: {gen_method!r} is not a whole-call generator "
                f"(param_only={checkpoint_meta.get('param_only')}, PROBE_KIND={gen_kind!r})")

    _apply_inheritance(full, authored, refs)

    # 5.3 / 5.4 / 5.7: everything below reads a field 5.4 lets a reference fill in, so it runs on
    # the values inheritance chose -- the values this setting runs with.
    env = full["data"]["env"]
    instructions_keys = tuple(module_literal(_env_module(env), "INSTRUCTIONS"))
    if full["data"]["instructions"] not in instructions_keys:
        raise SchemaError(
            f"data.instructions: {full['data']['instructions']!r} is not one of {instructions_keys} "
            f"for env {env!r}")

    datasets = _datasets_config()
    dataset_splits = set(datasets.get(env, {}).get("splits", {}))
    split_role = set(module_literal(_env_module(env), "SPLIT_ROLE"))
    valid_splits = dataset_splits & split_role
    for sec in ("sample", "inject"):
        if sec in full and full[sec].get("split") is not None:
            for s in full[sec]["split"]:
                if s not in valid_splits:
                    raise SchemaError(f"{sec}.split: {s!r} is not a split of env {env!r} ({sorted(valid_splits)})")

    table = _table()
    agent_alias = full["models"]["agent"]
    _check_role(table, agent_alias, "agent", "models.agent")
    probe_alias = full["models"].get("probe")
    if probe_alias is not None:
        _check_role(table, probe_alias, "probe", "models.probe")

    agent_family = table[agent_alias]["family"]
    effort = full["generation"]["effort"]
    if effort is not None:
        efforts = tuple(module_literal(_family_module(agent_family), "EFFORTS"))
        if effort not in efforts:
            raise SchemaError(
                f"generation.effort: {effort!r} is not one of {efforts} for family {agent_family!r}")

    _resolve_generation(full, agent_family)

    full["models"]["agent_row"] = _model_row(table, agent_alias)
    if probe_alias is not None:
        full["models"]["probe_row"] = _model_row(table, probe_alias)

    return _to_setting(full, workflow, file_stem, name, debug)


def _load_all(ref_file: Path, base_name: str, *, debug: bool, overrides: dict) -> list[Setting]:
    doc = yaml.safe_load(Path(ref_file).read_text()) or {}
    workflow = list(doc.get("workflow", []))
    if base_name not in doc:
        raise SchemaError(f"{base_name}: no such setting in {ref_file}")
    common = dict(doc.get("common", {}))
    named = dict(doc[base_name])
    sweep = named.pop("sweep", None)
    _check_raw_sections(workflow, common, named, base_name)

    if sweep:
        clash = set(overrides) & set(sweep)
        if clash:
            raise SchemaError(f"{sorted(clash)[0]}: overridden and swept at once")
        children_extras = _sweep_children(sweep, _debug_fields(), workflow)
    else:
        children_extras = [(None, {})]

    file_stem = Path(ref_file).stem
    settings = []
    for suffix, extra in children_extras:
        full, authored = _merge_one(workflow, common, named, debug=debug, overrides=overrides, extra=extra)
        name = f"{base_name}/{suffix}" if suffix else base_name
        settings.append(_finalize(full, authored, workflow, file_stem=file_stem, name=name, debug=debug))
    return settings


def load(workflow_file: Path, setting_name: str, *, debug: bool, overrides: dict) -> list[Setting]:
    """The merge order of 5.7: defaults -> common -> the named setting -> sweep -> debug.yaml -> overrides (5.1)."""
    base_name, sep, _ = setting_name.partition("/")
    children = _load_all(Path(workflow_file), base_name, debug=debug, overrides=overrides)
    if not sep:
        return children
    for c in children:
        if c._name == setting_name:
            return [c]
    raise SchemaError(f"{setting_name}: no such child of {base_name}")


# ---------------------------------------------------------------------------
# 3. load_frozen and run_dir_of; 4. fields_of, models_of, upstream_of,
#    versions_of, upstream, key, run_dir, freeze.
# ---------------------------------------------------------------------------


def _all_field_names(cls: type) -> set[str]:
    return {f.name for f in dc_fields(cls)}


def _dataclass_default(section: str, rest: str) -> Any:
    node = SECTION_CLASSES[section]()
    for part in rest.split("."):
        node = getattr(node, part)
    return node


def _stage_dotted_fields(stage: str) -> list[str]:
    """The dotted field names STAGES[stage]['sections'] names, whole bare sections expanded field by field."""
    names = []
    for entry in STAGES[stage]["sections"]:
        if "." in entry:
            names.append(entry)
            continue
        cls = SECTION_CLASSES[entry]
        for f in dc_fields(cls):
            if f.name in MODELS_READONLY:
                continue
            default = getattr(cls(), f.name)
            if hasattr(default, "__dataclass_fields__"):
                for pf in dc_fields(type(default)):
                    names.append(f"{entry}.{f.name}.{pf.name}")
            else:
                names.append(f"{entry}.{f.name}")
    return names


def _default_for_diff(dotted: str, agent_family: str | None, probe_family: str | None) -> Any:
    if dotted == "generation.stop" and agent_family:
        return list(module_literal(_family_module(agent_family), "STOP"))
    if dotted == "generation.effort" and agent_family:
        try:
            return module_literal(_family_module(agent_family), "DEFAULT_EFFORT")
        except SchemaError:
            return None
    if dotted == "generation.date" and agent_family:
        try:
            return module_literal(_family_module(agent_family), "DEFAULT_DATE")
        except SchemaError:
            return None
    if dotted == "probe.lora_targets" and probe_family:
        try:
            return list(module_literal(_backbone_module(probe_family), "LORA_TARGETS"))
        except SchemaError:
            return None
    section, _, rest = dotted.partition(".")
    return _dataclass_default(section, rest)


def _value_for_diff(dotted: str, setting: Setting, probe_family: str | None) -> Any:
    if dotted == "probe.lora_targets":
        stated = setting.probe.lora_targets
        if stated is not None:
            return stated
        if probe_family:
            try:
                return list(module_literal(_backbone_module(probe_family), "LORA_TARGETS"))
            except SchemaError:
                return None
        return None
    return _get_dotted_setting(setting, dotted)


def fields_of(stage: str, setting: Setting) -> dict:
    """The 'fields' block of 3.3, = settings_diff.yaml: dotted field -> value, only fields differing from default."""
    agent_family = setting.models.agent_row["family"] if setting.models and setting.models.agent_row else None
    probe_family = setting.models.probe_row["family"] if setting.models and setting.models.probe_row else None
    out = {}
    for dotted in _stage_dotted_fields(stage):
        if dotted in REF_FIELDS:
            continue
        section = dotted.split(".", 1)[0]
        if getattr(setting, section, None) is None:
            continue
        value = _value_for_diff(dotted, setting, probe_family)
        default = _default_for_diff(dotted, agent_family, probe_family)
        if value != default:
            out[dotted] = value
    return out


_STAGE_MODEL_ROLE = {"sample": "agent", "inject": "agent", "train": "probe"}


def models_of(stage: str, setting: Setting) -> dict:
    """The 'models' block of 3.3: {role: expanded row}, per 2.1's 'sections read' column."""
    role = _STAGE_MODEL_ROLE.get(stage)
    if role is None:
        return {}
    row = setting.models.agent_row if role == "agent" else setting.models.probe_row
    return {role: row}


def _substitute(template: str, setting: Setting) -> str:
    if "{env}" in template:
        template = template.replace("{env}", setting.data.env)
    if "{family}" in template:
        template = template.replace("{family}", setting.models.agent_row["family"])
    if "{backbone}" in template:
        template = template.replace("{backbone}", setting.models.probe_row["family"])
    if "{method}" in template:
        template = template.replace("{method}", setting.probe.method)
    if "{probe_score_method}" in template:
        method = _resolve_ref("inject.probe_score", setting.inject.probe_score)[2]
        if method is None:
            raise SchemaError(
                "inject.probe_score: the referenced setting states no probe.method, so its "
                "match version has no source")
        template = template.replace("{probe_score_method}", method)
    return template


def versions_of(stage: str, setting: Setting) -> dict:
    """The 'versions' block of 3.3: entry -> version, read as source text (entry -> int).

    An entry is spelled one of two ways. A bare repo-relative module path takes that whole
    module's `VERSION`, which is the form of every entry on the sample, build, eval and score
    rows. An entry spelled `<path>#<TABLE>.<method>` takes one probe method's own version out
    of the named column-zero table of that module, and enters the key under that same
    spelling: `train` folds `eval/utils/probe_eval.py#MATCH_VERSION.<method>` and `inject`
    folds the same entry for its scoring probe's method, so a change to the eval driver, to a
    report or to another method's match leaves an existing train run's key where it is, while
    a change to the match its validation metric is computed with re-keys it.

    This is the real version of every entry the stage lists, which is what settings.yaml's and
    meta.json's `_versions` record; the key folds `_key_versions` instead.
    """
    out = {}
    for template in STAGES[stage]["versions"]:
        entry = _substitute(template, setting)
        path, marker, table_entry = entry.partition("#")
        if marker:
            out[entry] = _table_entry_version(path, table_entry)
            continue
        out[entry] = module_version(path)
    return out


def _table_entry_version(path: str, table_entry: str) -> int:
    """One probe method's version out of a column-zero table: the value of `<TABLE>.<method>` in the module at `path`."""
    table_name, _, method = table_entry.partition(".")
    table = module_literal(path, table_name)
    if method not in table:
        raise SchemaError(
            f"{path}: {table_name} has no entry for method {method!r}; "
            f"it holds {sorted(table)}")
    return table[method]


def _key_versions(stage: str, setting: Setting) -> dict:
    """The 'versions' payload of the key: entry -> the version `stage`'s key folds (errata "3.3 / 8.6").

    A bare module path folds the file's effective version for `stage`: the stage looked up in
    the file's VERSION_HISTORY is the stage whose key is being computed, including where a file
    is folded for another stage's sake (the inject key's stand-ins for the probe_score eval key).
    A `<path>#<TABLE>.<method>` entry folds the table value itself: a per-method match version
    is already scoped to the one method that folds it, so it carries no VERSION_HISTORY.
    """
    out = {}
    for template in STAGES[stage]["versions"]:
        entry = _substitute(template, setting)
        path, marker, table_entry = entry.partition("#")
        if marker:
            out[entry] = _table_entry_version(path, table_entry)
            continue
        out[entry] = effective_version(path, stage)
    return out


def upstream(stage: str, setting: Setting) -> dict:
    """The full upstream map (1.5's naming), name -> key, for every upstream the stage table gives."""
    out = {}
    for entry in STAGES[stage]["upstream"]:
        when = entry.get("when")
        if when == "in_workflow" and entry["stage"] not in setting._workflow:
            continue
        if when == "generator":
            method = setting.probe.method if setting.probe else None
            if method is None or _method_kind(method) != "generator":
                continue
        if entry["source"] == "same":
            out[entry["name"]] = key(entry["stage"], setting)
            continue
        field_dotted = entry["source"][len("ref:"):]
        section, _, field_name = field_dotted.partition(".")
        section_obj = getattr(setting, section, None)
        value = getattr(section_obj, field_name) if section_obj is not None else None
        if value is None:
            continue
        kind, payload, _method = _resolve_ref(field_dotted, value)
        out[entry["name"]] = key(entry["stage"], payload) if kind == "setting" else payload[entry["stage"]]
    return out


def upstream_of(stage: str, setting: Setting) -> dict:
    """name -> key, per the stage table's upstream cell; the same map as upstream()."""
    return upstream(stage, setting)


def key(stage: str, setting: Setting) -> str:
    """The payload of 3.3, canonical JSON, sha256, first 12 lowercase hex characters.

    The 'versions' block of the payload holds effective versions, not the files' real VERSION
    (errata "3.3 / 8.6"): a bump that leaves this stage usable keeps this stage's key.
    """
    fields = fields_of(stage, setting)
    models = models_of(stage, setting)
    full_upstream = upstream(stage, setting)
    fold_names = {e["name"] for e in STAGES[stage]["upstream"] if e["key"] == "fold"}
    upstream_payload = {name: k for name, k in full_upstream.items() if name in fold_names}
    versions = _key_versions(stage, setting)
    payload = {"stage": stage, "fields": fields, "models": models,
               "upstream": upstream_payload, "versions": versions}
    if setting._debug:
        payload["debug"] = True
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def run_dir_of(stage: str, key: str, *, debug: bool) -> Path:
    """<root>/<stage>/<key> or <root>/<debug_subdir>/<stage>/<key>, both roots from constants/path_outputs.yaml."""
    cfg = _outputs_config()
    root = Path(cfg["root"])
    if debug:
        return root / cfg["debug_subdir"] / stage / key
    return root / stage / key


def run_dir(stage: str, setting: Setting) -> Path:
    return run_dir_of(stage, key(stage, setting), debug=setting._debug)


def _dataclass_to_dict(obj: Any) -> Any:
    if obj is None:
        return None
    if hasattr(obj, "__dataclass_fields__"):
        return {f.name: _dataclass_to_dict(getattr(obj, f.name)) for f in dc_fields(obj)}
    return obj


def _frozen_dict_to_dataclass(cls: type, d: dict):
    kwargs = {}
    for f in dc_fields(cls):
        if f.name not in d:
            continue
        default = getattr(cls(), f.name)
        value = d[f.name]
        if hasattr(default, "__dataclass_fields__") and isinstance(value, dict):
            kwargs[f.name] = _frozen_dict_to_dataclass(type(default), value)
        else:
            kwargs[f.name] = value
    return cls(**kwargs)


def _refuse_unknown_frozen_fields(cls: type, d: dict, prefix: str, run_dir: Path) -> None:
    names = _all_field_names(cls)
    for k in d:
        if k not in names:
            raise SchemaError(f"{prefix}.{k}: field removed from the schema (run directory {run_dir})")
    for f in dc_fields(cls):
        if f.name in d and isinstance(d[f.name], dict):
            default = getattr(cls(), f.name)
            if hasattr(default, "__dataclass_fields__"):
                _refuse_unknown_frozen_fields(type(default), d[f.name], f"{prefix}.{f.name}", run_dir)


def _atomic_write_yaml(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(yaml.safe_dump(doc, sort_keys=True))
    tmp.replace(path)


def _merge_request_fields(doc: dict, existing: dict, sections: set[str]) -> None:
    """3.4: the non-keyed request fields merge per field on a re-freeze of the same directory."""
    for sec in ("sample", "inject"):
        if sec not in sections or sec not in doc or sec not in existing:
            continue
        old_seeds = existing[sec].get("seeds") or []
        new_seeds = doc[sec].get("seeds") or []
        doc[sec]["seeds"] = old_seeds + [s for s in new_seeds if s not in old_seeds]
        old_tasks = existing[sec].get("tasks")
        new_tasks = doc[sec].get("tasks")
        if old_tasks is None or new_tasks is None:
            doc[sec]["tasks"] = None
        else:
            doc[sec]["tasks"] = old_tasks + [t for t in new_tasks if t not in old_tasks]


def _projection_sections(stage: str, setting: Setting) -> set[str]:
    entry = STAGES[stage]
    sections = {t.split(".", 1)[0] for t in entry["sections"]}
    sections |= {t.split(".", 1)[0] for t in entry["projection"]}
    if entry["projection_generator"]:
        method = setting.probe.method if setting.probe else None
        if method is not None and _method_kind(method) == "generator":
            sections |= {t.split(".", 1)[0] for t in entry["projection_generator"]}
    if stage == "inject":
        sections |= {"build"}
    return sections


def freeze(setting: Setting, stage: str, run_dir: Path, resolved: dict, commit: str) -> None:
    """The stage projection of 3.4, plus the _ block of 1.5; writes both files through a temporary name."""
    run_dir = Path(run_dir)
    sections = _projection_sections(stage, setting)

    doc: dict = {}
    for sec in sections:
        obj = getattr(setting, sec, None)
        if obj is not None:
            doc[sec] = _dataclass_to_dict(obj)

    doc["_stage"] = stage
    doc["_key"] = key(stage, setting)
    doc["_upstream"] = upstream(stage, setting)
    doc["_versions"] = versions_of(stage, setting)
    doc["_debug"] = setting._debug
    doc["_commit"] = commit
    doc["_resolved"] = resolved

    diff = fields_of(stage, setting)

    settings_path = run_dir / "settings.yaml"
    diff_path = run_dir / "settings_diff.yaml"
    if diff_path.exists():
        existing_diff = yaml.safe_load(diff_path.read_text()) or {}
        if existing_diff != diff:
            raise SchemaError(
                f"freeze: {run_dir} already holds settings for a different key under stage {stage!r}")
        existing_settings = yaml.safe_load(settings_path.read_text()) or {}
        _merge_request_fields(doc, existing_settings, sections)

    _atomic_write_yaml(settings_path, doc)
    _atomic_write_yaml(diff_path, diff)


def load_frozen(run_dir: Path) -> Setting:
    """Parse settings.yaml against the dataclasses, fill the _ block; re-merges nothing, re-resolves nothing (2.6)."""
    run_dir = Path(run_dir)
    doc = yaml.safe_load((run_dir / "settings.yaml").read_text()) or {}
    setting = Setting()
    for sec, cls in SECTION_CLASSES.items():
        if sec not in doc:
            continue
        section_doc = doc[sec]
        _refuse_unknown_frozen_fields(cls, section_doc, sec, run_dir)
        setattr(setting, sec, _frozen_dict_to_dataclass(cls, section_doc))
    setting._stage = doc.get("_stage")
    setting._key = doc.get("_key")
    setting._upstream = doc.get("_upstream", {})
    setting._versions = doc.get("_versions", {})
    setting._debug = doc.get("_debug", False)
    setting._commit = doc.get("_commit")
    setting._resolved = doc.get("_resolved", {})
    return setting
