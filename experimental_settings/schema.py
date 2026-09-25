"""The setting schema: the dataclasses, the stage table, and the loader that reads a YAML file against them (file -> setting, diff, key)."""
from __future__ import annotations

import ast
import hashlib
import itertools
import json
import re
from collections.abc import Hashable
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
    # TODO(gyb, 2026-09-22): 6 is a placeholder, here and on Inject.pieces. One loop process runs
    # one task at a time, so this number is the most requests the agent server sees at once.
    # Set it from a measured throughput once the real cards are there; it is not in the key
    # (`sample.pieces=<n>` on the command line changes it and keeps the run directory).
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
    # TODO(gyb, 2026-09-22): before the full inject run, set theta in the inject workflow file from
    # the full ctool eval's risk thresholds. The 0.80 there was never crossed in a debug walk
    # (wave 7: no spec row); both 2026-09-22 debug walks fired through fire_nth_cut only.
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
    _era: int | None = None                       # the stage's era the run was keyed under (jobs/versions.yaml)
    _commit: str | None = None
    _resolved: dict = field(default_factory=dict)
    # The command-line overrides this load applied, dotted field -> the text typed, empty for a
    # plain load. The launcher records them in the start row and meta.json, and `run.py ls`
    # reloads the named setting under them when it asks whether the setting was edited since;
    # without the record every overridden run read `edited` forever (repo test 2026-09-25, D2).
    _overrides: dict = field(default_factory=dict)


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
    "program": "agent.run_tasks",
    "venv": {"loop": "env", "service_agent": "vllm", "service_probe": "probe"},
    "pieces": (("loop", "pieces", None), ("service_agent", "replicas", None),
               ("service_probe", 1, "render_only")),
    "cards": True,
    "done_writer": "run.py",
    "projection": ("sample.seeds", "sample.tasks", "sample.n_tasks",
                   "sample.pieces", "sample.replicas"),
    "projection_generator": (),
    "code": ("agent/run_tasks.py", "agent/step_without_probe.py", "agent/step_with_probe.py",
             "agent/injected_text_formats.py", "data/__init__.py", "data/probe_input.py",
             "data/trajectory_record.py", "data/environments/__init__.py",
             "data/environments/{env}.py", "models/__init__.py",
             "models/agent_models/__init__.py", "models/agent_models/{family}.py",
             "models/agent_models/service.py", "models/probe_models/__init__.py",
             "models/probe_models/base.py", "models/probe_models/service.py"),
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
    "code": ("data/__init__.py", "data/build_training_dataset.py", "data/probe_input.py",
             "data/training_data.py", "data/trajectory_record.py",
             "data/environments/__init__.py", "data/environments/{env}.py"),
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
    "code": ("train/utils/trainer.py", "train/methods/{method}.py", "eval/utils/probe_eval.py",
             "data/__init__.py", "data/training_data.py", "data/probe_output.py",
             "data/environments/__init__.py", "models/__init__.py",
             "models/probe_models/__init__.py", "models/probe_models/base.py",
             "models/probe_models/{backbone}.py"),
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
    "code": ("eval/utils/probe_eval.py", "data/__init__.py", "data/probe_output.py",
             "data/environments/__init__.py"),
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
    "program": "agent.run_tasks",
    "venv": {"loop": "env", "service_agent": "vllm", "service_probe": "probe"},
    "pieces": (("loop", "pieces", None), ("service_agent", "replicas", None),
               ("service_probe", 1, None)),
    "cards": True,
    "done_writer": "run.py",
    "projection": ("inject.seeds", "inject.tasks", "inject.n_tasks",
                   "inject.pieces", "inject.replicas"),
    "projection_generator": (),
    "code": ("agent/run_tasks.py", "agent/step_without_probe.py", "agent/step_with_probe.py",
             "agent/injected_text_formats.py", "data/__init__.py", "data/probe_input.py",
             "data/trajectory_record.py", "data/environments/__init__.py",
             "data/environments/{env}.py", "models/__init__.py",
             "models/agent_models/__init__.py", "models/agent_models/{family}.py",
             "models/agent_models/service.py", "models/probe_models/__init__.py",
             "models/probe_models/base.py", "models/probe_models/service.py",
             # The live run reads the carried probe_score eval run's fitted temperature, so the
             # eval driver is code this stage's output depends on as well.
             "eval/utils/probe_eval.py"),
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
    "code": ("eval/score_run.py", "data/__init__.py", "data/trajectory_record.py",
             "data/environments/__init__.py"),
  },
}

# The `.py` files under data/, models/, agent/, train/ and eval/ that no stage's output depends
# on, each with its reason; every other file under those five layers is named by some stage's
# `code` tuple, and `run.py selfcheck` check 4 holds both statements.
CODE_UNLISTED = {
    "eval/method_table.py": "renders the run.py table subcommand's table out of the ledger; writes no run output",
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


def _parse_module(rel_path: str) -> ast.Module:
    """The module at rel_path parsed as source text, never imported (3.3); a caller that wants two literals of one file parses it once."""
    return ast.parse((ROOT / rel_path).read_text())


def _column_zero_matches(tree: ast.Module, name: str) -> list:
    """Every column-zero module-level assignment of `name` in an already parsed module, read with ast.literal_eval."""
    matches = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and node.col_offset == 0:
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    matches.append(ast.literal_eval(node.value))
    return matches


def _one_column_zero(rel_path: str, tree: ast.Module, name: str) -> Any:
    """The one column-zero assignment of `name` in an already parsed module; refuses zero matches and two, naming the file."""
    matches = _column_zero_matches(tree, name)
    if not matches:
        raise SchemaError(f"{rel_path}: no column-zero assignment to {name!r}")
    if len(matches) > 1:
        raise SchemaError(
            f"{rel_path}: {len(matches)} column-zero assignments to {name!r}, expected exactly one")
    return matches[0]


def module_literal(rel_path: str, name: str) -> Any:
    """The one column-zero literal named `name` in the module at rel_path, read as source text (3.3)."""
    return _one_column_zero(rel_path, _parse_module(rel_path), name)


# ---------------------------------------------------------------------------
# The code-era table, jobs/versions.yaml (3.3): how a code change enters a key.
# ---------------------------------------------------------------------------
#
# A stage's key folds one integer, the stage's era, and nothing about the code itself. The era
# is the highest `era` an era row of jobs/versions.yaml states for the stage, 1 while the table
# has none. Writing an era row (`run.py version <stage> --why ...`) is the one way a code change
# moves a key: every later run of that stage, and of every stage downstream of it through the
# folded upstream keys, lands in a new directory. A same row (`run.py version <stage> --same
# --why ...`) states that the stage's code files at the named commit still produce that era's
# output; run.py's launch gate reads it to reuse a directory whose launch commit the code has
# moved past. The table's strict shape is `run.py selfcheck` check 4's; this reader refuses
# only what the key path cannot use.

VERSIONS_TABLE = ROOT / "jobs" / "versions.yaml"


def versions_table() -> list[dict]:
    """The rows of jobs/versions.yaml in file order: a list of mappings, each with a stage of STAGES, an int `era` and a `why`; a same row also carries `same`, a commit id."""
    if not VERSIONS_TABLE.exists():
        raise SchemaError(f"{VERSIONS_TABLE}: the code-era table is missing")
    rows = _parse_yaml(VERSIONS_TABLE.read_text(), str(VERSIONS_TABLE))
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise SchemaError(f"{VERSIONS_TABLE}: expected a list of rows, got {type(rows).__name__}")
    for i, row in enumerate(rows):
        where = f"{VERSIONS_TABLE}: row {i + 1}"
        if not isinstance(row, dict):
            raise SchemaError(f"{where}: expected a mapping, got {type(row).__name__}")
        if row.get("stage") not in STAGES:
            raise SchemaError(f"{where}: stage {row.get('stage')!r} is not one of {tuple(STAGES)}")
        era = row.get("era")
        if isinstance(era, bool) or not isinstance(era, int) or era < 1:
            raise SchemaError(f"{where}: era {era!r} is not a positive int")
        if not isinstance(row.get("why"), str) or not row["why"].strip():
            raise SchemaError(f"{where}: why is missing or empty")
        if "same" in row and not isinstance(row["same"], str):
            raise SchemaError(f"{where}: same {row['same']!r} is not a commit id string")
    return rows


def era_of(stage: str) -> int:
    """The current era of `stage`: the highest era an era row states for it, 1 when the table has none."""
    eras = [row["era"] for row in versions_table() if row["stage"] == stage and "same" not in row]
    return max(eras, default=1)


def era_rows(stage: str) -> list[dict]:
    """The era rows of `stage`, in file order (run.py ls quotes their `why` for a run whose era moved)."""
    return [row for row in versions_table() if row["stage"] == stage and "same" not in row]


def same_rows(stage: str, era: int) -> list[dict]:
    """The same rows of `stage` at `era`, in file order: each names a commit whose code files of the stage still produce era `era`'s output."""
    return [row for row in versions_table()
            if row["stage"] == stage and "same" in row and row["era"] == era]


class _UniqueKeyLoader(yaml.SafeLoader):
    """yaml.SafeLoader that refuses a mapping key stated twice, naming the key and the lines of both occurrences.

    PyYAML's own SafeLoader keeps the last of two equal keys, so a setting pasted twice under one
    name, or a field stated twice in one section, would load as whichever came last.
    """

    def construct_mapping(self, node, deep=False):
        seen: dict = {}
        for key_node, _value_node in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                continue                        # a `<<` merge key; its entries are flattened by the base class
            key_obj = self.construct_object(key_node, deep=deep)
            if isinstance(key_obj, Hashable):   # an unhashable key is refused by the base class
                mark = key_node.start_mark
                where = f"line {mark.line + 1} column {mark.column + 1}"
                if key_obj in seen:
                    raise SchemaError(
                        f"{mark.name}: key {key_obj!r} is stated twice, at {seen[key_obj]} and at {where}")
                seen[key_obj] = where
        return super().construct_mapping(node, deep=deep)


def _parse_yaml(text: str, source: str) -> Any:
    """Parse one YAML document with _UniqueKeyLoader; `source` names the text in a refusal (a path, or an override)."""
    loader = _UniqueKeyLoader(text)
    loader.name = source
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()


def _read_yaml(rel_path: str) -> dict:
    return _parse_yaml((ROOT / rel_path).read_text(), str(ROOT / rel_path)) or {}


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
ANNOTATION_SPELLINGS = ("str", "int", "float", "bool", "None", "list[<spelling>]", "dict", "dict[...]",
                        "the name of a dataclass defined in schema.py")


def _annotation_alternatives(annot: str) -> list[str]:
    """The `|`-separated alternatives of an annotation string, split at bracket depth zero only."""
    parts, depth, start = [], 0, 0
    for index, char in enumerate(annot):
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
        elif char == "|" and depth == 0:
            parts.append(annot[start:index].strip())
            start = index + 1
    parts.append(annot[start:].strip())
    return parts


def _is_schema_dataclass(word: str) -> bool:
    """Whether `word` names a dataclass defined in this module (Predict, a section class)."""
    obj = globals().get(word)
    return isinstance(obj, type) and hasattr(obj, "__dataclass_fields__")


def _annot_types(annot: str, label: str) -> tuple:
    """The declared type of the field `label` as (types, element, annot): the Python types a YAML value may take, and the same triple for a list's elements (None when no alternative is a list[...]).

    A word names a type only in the spellings of ANNOTATION_SPELLINGS; a nested dataclass field
    (Predict) arrives from YAML as a dict. Any other spelling is refused, naming the field.
    """
    types, element = [], None
    for part in _annotation_alternatives(annot):
        if part in _TYPE_WORDS:
            types.append(_TYPE_WORDS[part])
        elif part.startswith("list[") and part.endswith("]") and element is None:
            types.append(list)
            element = _annot_types(part[len("list["):-1], label)
        elif part == "dict" or (part.startswith("dict[") and part.endswith("]")):
            types.append(dict)
        elif _is_schema_dataclass(part):
            types.append(dict)
        else:
            raise SchemaError(
                f"{label}: annotation {annot!r} uses {part!r}, which the loader does not type; the "
                f"accepted spellings are {', '.join(ANNOTATION_SPELLINGS)}, joined with |")
    return tuple(types), element, annot


def _type_ok(value: Any, types: tuple) -> bool:
    if type(value) in types:
        return True
    if float in types and type(value) is int:
        return True
    return False


def _check_value(value: Any, declared: tuple, label: str) -> None:
    """Refuse `value` unless its type is one `declared` (an _annot_types triple) allows, and, for a list, unless every element's is one the element annotation allows, naming the index."""
    types, element, annot = declared
    if not _type_ok(value, types):
        raise SchemaError(
            f"{label}: {value!r} has type {type(value).__name__}, declared type is {annot}")
    if type(value) is list and element is not None:
        for index, item in enumerate(value):
            _check_value(item, element, f"{label}[{index}]")


def _apply_fields(dst: dict, overlay: dict, cls: type, prefix: str, authored: set[str]) -> None:
    """Merge `overlay` onto `dst` (a section dict), per field, list fields replaced whole; recurse into a nested dataclass field.

    `overlay` is a mapping of field name -> value: a section, or a nested dataclass field, is
    always written as one, so any other shape is refused here, naming `prefix`.
    """
    if not isinstance(overlay, dict):
        raise SchemaError(f"{prefix}: expected a mapping, got {type(overlay).__name__}")
    names = _section_field_names(cls)
    for key, value in overlay.items():
        if key not in names:
            raise SchemaError(f"{prefix}.{key}: not a field of this section")
        default = getattr(cls(), key)
        if hasattr(default, "__dataclass_fields__"):
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


def _is_declared_field(dotted: Any) -> bool:
    """Whether `dotted` names a field of the dataclass declarations: a section, then each inner part a field whose default is a dataclass, then the last part a field (MODELS_READONLY excluded).

    The command-line override and the sweep name are both checked here, against the
    declarations, never against the values a merged setting happens to hold.
    """
    if not isinstance(dotted, str):
        return False
    section, *rest = dotted.split(".")
    if section not in SECTION_CLASSES or not rest:
        return False
    cls = SECTION_CLASSES[section]
    for part in rest[:-1]:
        if part not in _section_field_names(cls):
            return False
        default = getattr(cls(), part)
        if not hasattr(default, "__dataclass_fields__"):
            return False
        cls = type(default)
    return rest[-1] in _section_field_names(cls)


def _set_field(full: dict, dotted: str, value: Any, authored: set[str]) -> None:
    """Set one declared field (see _is_declared_field) of the merged setting from a sweep child or an override.

    A leaf takes `value` whole, a list replaced and never appended (5.7); a nested dataclass
    field merges `value` per field, exactly as the file's own mapping for it merges.
    """
    section, *rest = dotted.split(".")
    cls, node = SECTION_CLASSES[section], full[section]
    for part in rest[:-1]:
        cls, node = type(getattr(cls(), part)), node[part]
    last = rest[-1]
    default = getattr(cls(), last)
    if hasattr(default, "__dataclass_fields__"):
        _apply_fields(node[last], value, type(default), dotted, authored)
    else:
        node[last] = value
        authored.add(dotted)


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


def _require_workflow_reads(workflow: list[str], section: str, label: str) -> None:
    """5.7's 'a section for a stage the file's workflow does not name': `section` is one a stage of `workflow` reads; `label` is the name the refusal starts with."""
    if section in _yaml_allowed_sections(workflow):
        return
    raise SchemaError(f"{label}: no stage of this file's workflow reads this section")


def _check_raw_sections(workflow: list[str], common: dict, named: dict, base_name: str) -> None:
    """5.7's 'a section for a stage the workflow does not name', evaluated against the raw file content only."""
    for d in (common, named):
        for key in d:
            _require_workflow_reads(workflow, key, key)
    for d in (common, named):
        if "probe" in d:
            _refuse_probe_under_inject(workflow, "probe")
        models = d.get("models", {})
        if isinstance(models, dict) and "probe" in models:   # a models: that is no mapping is refused by _apply_fields
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
        _set_field(full, dotted, value, authored)

    if debug:
        for sec, section_overlay in _read_yaml("experimental_settings/debug.yaml").items():
            if sec in full and SECTION_STAGE.get(sec) in workflow:
                _apply_fields(full[sec], section_overlay, SECTION_CLASSES[sec], sec, set())

    for dotted, raw in overrides.items():
        if not _is_declared_field(dotted):
            raise SchemaError(f"{dotted}: not a field of the schema")
        _refuse_probe_under_inject(workflow, dotted)
        # An override states what the file itself may state (5.7): the inherited build section
        # of an inject workflow is in the merged setting and is still not the file's to state.
        _require_workflow_reads(workflow, dotted.partition(".")[0], dotted)
        _set_field(full, dotted, _parse_yaml(raw, f"the override {dotted}"), authored)

    return full, authored


def _sweep_children(sweep: Any, debug_fields: set[str], workflow: list[str]) -> list[tuple[str, dict]]:
    """The children of a `sweep:` block, one (name suffix, {dotted: value}) per combination of the listed values.

    The block is refused unless it is a mapping from a declared field (see _is_declared_field)
    of a section the file's workflow reads to a non-empty list of values, and unless no swept
    field is one debug.yaml sets (5.5 / 5.7): a nested dataclass field swept as mappings counts
    each field those mappings state.
    """
    if not isinstance(sweep, dict):
        raise SchemaError(
            f"sweep: expected a mapping of dotted field -> list of values, got {type(sweep).__name__}")
    for dotted, values in sweep.items():
        label = f"sweep.{dotted}"
        if not _is_declared_field(dotted):
            raise SchemaError(f"{label}: not a field of the schema")
        _refuse_probe_under_inject(workflow, dotted)
        _require_workflow_reads(workflow, dotted.partition(".")[0], label)
        if not isinstance(values, list):
            raise SchemaError(f"{label}: expected a list of values, got {type(values).__name__}")
        if not values:
            raise SchemaError(f"{label}: expected a list of values, got an empty list")
        stated = {dotted}
        for value in values:
            if isinstance(value, dict):
                stated |= {f"{dotted}.{key}" for key in value}
        if stated & debug_fields:
            raise SchemaError(f"{label}: also set by debug.yaml, which would collapse the sweep")
    names = sorted(sweep)
    out = []
    for combo in itertools.product(*(sweep[n] for n in names)):
        extra = dict(zip(names, combo))
        suffix = ",".join(f"{n}={v!r}" for n, v in extra.items())
        out.append((suffix, extra))
    return out


def _type_check_section(section_dict: dict, cls: type, prefix: str) -> None:
    """Check every field of a merged section against its annotation, then descend into a nested dataclass field, whose annotation has already required a mapping."""
    for f in dc_fields(cls):
        if f.name in MODELS_READONLY:
            continue
        label = f"{prefix}.{f.name}"
        value = section_dict[f.name]
        _check_value(value, _annot_types(f.type, label), label)
        default = getattr(cls(), f.name)
        if hasattr(default, "__dataclass_fields__"):
            _type_check_section(value, type(default), label)


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


# The (workflow file stem, setting name) pairs whose name-form references are being resolved
# right now, outermost first; a pair met again while it is on this chain is a reference cycle.
_RESOLVING: list[tuple[str, str]] = []


def _resolve_name_ref(value: str, *, debug: bool) -> Setting:
    """Load the setting a name-form reference names, under the referring setting's debug flag.

    A `--debug` walk loads the referenced setting with the debug overlay too, so the reference
    keys to the referenced setting's debug key: the run a `--debug` walk of that setting
    produces, under the debug outputs root (owner ruling 9, 2026-09-24). A walk without
    `--debug` keys to the real run.
    """
    stem, sep, name = value.partition("/")
    if not sep:
        raise SchemaError(f"{value!r}: a reference is <workflow>/<setting>")
    ref_file = ROOT / "experimental_settings" / f"{stem}.yaml"
    if not ref_file.exists():
        raise SchemaError(f"{value!r}: no such workflow file {ref_file}")
    pair = (stem, name)
    if pair in _RESOLVING:
        cycle = _RESOLVING[_RESOLVING.index(pair):] + [pair]
        raise SchemaError(f"{' -> '.join(f'{s}/{n}' for s, n in cycle)}: a reference cycle")
    _RESOLVING.append(pair)
    try:
        results = load(ref_file, name, debug=debug, overrides={})
    finally:
        _RESOLVING.pop()
    if len(results) != 1:
        raise SchemaError(
            f"{value!r}: names a swept setting with {len(results)} children; name a child directly")
    return results[0]


METHOD_REF_FIELDS = ("inject.probe_score", "inject.probe_gen")
_RUN_KEY = re.compile(r"[0-9a-f]{12}")             # a run key, the form `key` returns (3.3)


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


def _resolve_ref(field_dotted: str, value: Any, *, debug: bool) -> tuple[str, Any, str | None]:
    """Resolve one reference field's stated value to ('setting', Setting, method) or ('keys', {stage: key}, method).

    `debug` is the referring setting's flag; a name-form reference loads the named setting under
    it. A pinned key:/dir: reference carries its keys as stated and ignores it.
    """
    try:
        if isinstance(value, dict) and "method" in value and "key" not in value and "dir" not in value:
            raise SchemaError(
                "a name-form reference states no 'method:'; the loader reads the method off the "
                "named setting, and 'method:' belongs to a key: or dir: reference")
        kind = _ref_kind(value)
        required = set(_ref_requirements(field_dotted))
        if kind == "name":
            setting = _resolve_name_ref(value, debug=debug)
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
        if not isinstance(value[kind], dict):
            raise SchemaError(
                f"a {kind}: reference is a mapping of stage -> value, got {type(value[kind]).__name__}")
        got = set(value[kind])
        if got != required:
            raise SchemaError(f"pinned {kind} stages {sorted(got)} != required {sorted(required)}")
        if kind == "key":
            for stage, stage_key in value["key"].items():
                if isinstance(stage_key, str) and _RUN_KEY.fullmatch(stage_key):
                    continue
                raise SchemaError(
                    f"pinned key stage {stage}: {stage_key!r} is not a 12-hex key (quote it in YAML "
                    "when it is all digits)")
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

    # 5.2: split_ratio is the train/val/test shares of the hash split, so it holds three shares,
    # each >= 0, that add up to 1 (within float rounding of the default [0.8, 0.1, 0.1]).
    if "build" in full:
        ratio = full["build"]["split_ratio"]
        if not (len(ratio) == 3 and min(ratio) >= 0 and abs(sum(ratio) - 1.0) <= 1e-9):
            raise SchemaError(
                f"build.split_ratio: {ratio!r} is not three train/val/test shares, each >= 0, "
                "summing to 1")

    if "inject" in workflow and full["models"]["probe"] is not None:
        _refuse_probe_under_inject(workflow, "models.probe")

    if "inject" in full and full["inject"]["arm"] == "no_probe" and full["inject"]["fire_nth_cut"] > 0:
        raise SchemaError("inject.fire_nth_cut: must be 0 under arm: no_probe")

    for dotted in REQUIRED_FIELDS:
        if "inject" in full and _get_dotted(full, dotted) is None:
            raise SchemaError(f"{dotted}: is required and was not set")

    # theta is compared with the probe's softmax confidence, a value in [0, 1]; a value off
    # THETA_GRID is by design (theta is a person's field, 2.1), a value outside [0, 1] never fires
    # or always fires.
    if "inject" in full:
        theta = full["inject"]["theta"]
        if not 0.0 <= theta <= 1.0:
            raise SchemaError(
                f"inject.theta: {theta} is outside [0, 1], the range of the probe confidence it is "
                "compared with")

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
        refs[dotted] = _resolve_ref(dotted, value, debug=debug)

    # 2.1 / 5.2: eval.theta_from is resolved to its classifier eval key (the frozen theta) and
    # inject.probe_score to its classifier train and eval keys (the weights that decide when to
    # fire, and the temperature), so the method each reference selects is a classifier. The name
    # form takes the method off the named setting and a pinned inject.probe_score states it; a
    # pinned eval.theta_from carries no method, and eval checks the report it reads.
    def _require_classifier(dotted: str) -> None:
        method = refs[dotted][2]
        if method is None:
            return
        kind = _method_kind(method)
        if kind == "classifier":
            return
        raise SchemaError(f"{dotted}: {method!r} is not a classifier (PROBE_KIND={kind!r})")

    _resolve_if_set("eval.theta_from")
    if "eval.theta_from" in refs:
        _require_classifier("eval.theta_from")
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
    if "inject.probe_score" in refs:
        _require_classifier("inject.probe_score")

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


RESERVED_TOP_LEVEL = ("workflow", "common")    # the top-level keys of a workflow file that name no setting (5.1)


def _check_workflow(workflow: Any) -> list[str]:
    """The file's `workflow:` line, refused unless it is a non-empty list of stage names in which every stage comes after the same-setting stages it reads.

    The same-setting upstream entries of the stage table (source `same`) are the runs a stage
    reads from its own setting; one marked `when: in_workflow` is read only when its stage is in
    the list, so it is ordered only then.
    """
    if not (isinstance(workflow, list) and workflow):
        raise SchemaError(f"workflow: expected a non-empty list of stages {sorted(STAGES)}, got {workflow!r}")
    for position, stage in enumerate(workflow):
        if not (isinstance(stage, str) and stage in STAGES):
            raise SchemaError(f"workflow: {stage!r} is not a stage ({sorted(STAGES)})")
        earlier = workflow[:position]
        for entry in STAGES[stage]["upstream"]:
            if entry["source"] == "same":
                if entry.get("when") == "in_workflow":
                    ordered = entry["stage"] in workflow
                else:
                    ordered = True
                if ordered and entry["stage"] not in earlier:
                    raise SchemaError(
                        f"workflow: {stage!r} reads the {entry['stage']!r} run of the same setting, "
                        f"so {entry['stage']!r} comes before it in the list {workflow}")
    return list(workflow)


def _load_all(ref_file: Path, base_name: str, *, debug: bool, overrides: dict) -> list[Setting]:
    doc = _parse_yaml(Path(ref_file).read_text(), str(ref_file)) or {}
    if not isinstance(doc, dict):
        raise SchemaError(
            f"{ref_file}: expected a mapping of workflow, common and named settings, got "
            f"{type(doc).__name__}")
    workflow = _check_workflow(doc.get("workflow"))
    if base_name in RESERVED_TOP_LEVEL:
        raise SchemaError(
            f"{base_name}: a reserved top-level key of a workflow file {RESERVED_TOP_LEVEL}, "
            "not a setting name")
    if base_name not in doc:
        raise SchemaError(f"{base_name}: no such setting in {ref_file}")
    common = doc.get("common", {})
    if not isinstance(common, dict):
        raise SchemaError(f"common: expected a mapping of sections, got {type(common).__name__}")
    named = doc[base_name]
    if not isinstance(named, dict):
        raise SchemaError(f"{base_name}: expected a mapping of sections, got {type(named).__name__}")
    named = dict(named)
    swept = "sweep" in named
    sweep = named.pop("sweep", None)
    _check_raw_sections(workflow, common, named, base_name)

    if swept:
        children_extras = _sweep_children(sweep, _debug_fields(), workflow)
        clash = set(overrides) & set(sweep)
        if clash:
            raise SchemaError(f"{sorted(clash)[0]}: overridden and swept at once")
    else:
        children_extras = [(None, {})]

    file_stem = Path(ref_file).stem
    settings = []
    for suffix, extra in children_extras:
        full, authored = _merge_one(workflow, common, named, debug=debug, overrides=overrides, extra=extra)
        name = f"{base_name}/{suffix}" if suffix else base_name
        setting = _finalize(full, authored, workflow, file_stem=file_stem, name=name, debug=debug)
        setting._overrides = dict(overrides)
        settings.append(setting)
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
#    code_files, upstream, key, run_dir, freeze.
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
    return template


def code_files(stage: str, setting: Setting) -> list[str]:
    """The repo-relative files whose content `stage`'s output depends on for this setting: the stage table's `code` templates with the setting's chosen modules substituted (5.2), in table order.

    run.py's launch gate compares these files, as they are in the working tree, with the
    same files at the commits a directory it is about to read was launched from; nothing here
    enters a key (the era does, `era_of`).
    """
    return [_substitute(template, setting) for template in STAGES[stage]["code"]]


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
        kind, payload, _method = _resolve_ref(field_dotted, value, debug=setting._debug)
        out[entry["name"]] = key(entry["stage"], payload) if kind == "setting" else payload[entry["stage"]]
    return out


def upstream_of(stage: str, setting: Setting) -> dict:
    """name -> key, per the stage table's upstream cell; the same map as upstream()."""
    return upstream(stage, setting)


def key(stage: str, setting: Setting) -> str:
    """The payload of 3.3, canonical JSON, sha256, first 12 lowercase hex characters.

    The code enters the payload as the stage's era alone (`era_of`, the code-era table
    jobs/versions.yaml); an upstream stage's code reaches it through that stage's folded key.
    """
    fields = fields_of(stage, setting)
    models = models_of(stage, setting)
    full_upstream = upstream(stage, setting)
    fold_names = {e["name"] for e in STAGES[stage]["upstream"] if e["key"] == "fold"}
    upstream_payload = {name: k for name, k in full_upstream.items() if name in fold_names}
    payload = {"stage": stage, "fields": fields, "models": models,
               "upstream": upstream_payload, "era": era_of(stage)}
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


def referenced_run_dir(stage: str, key: str) -> Path | None:
    """The directory of a run reached through a reference (5.4), or None when neither root holds it.

    A run's `--debug` flag is part of its own key payload (3.3), so a referenced key names a
    directory under whichever of the two roots that run was written in. A name-form reference is
    loaded under the referring setting's own flag (owner ruling 9, 2026-09-24), so its run lives
    under the referring run's root; a key pinned as `key:`/`dir:` may name a run under either
    root, whatever the referring run's flag. The one that answers is the directory whose frozen
    `settings.yaml` records this very key; a directory made before this scheme carries no
    `settings.yaml` (5.4's reason for the `dir:` form), so the one that exists stands in for it.
    The launcher (`jobs/launch.py`, the two probe checkpoints) and `eval/score_run.py` (the
    baseline) locate every referenced run through this one function, name form included;
    `run.py._upstream_dirs` alone locates a name-form reference's run with `run_dir_of` under
    the referring run's flag, which names the same directory.
    """
    candidates = [run_dir_of(stage, key, debug=flag) for flag in (False, True)]
    for candidate in candidates:
        if (candidate / "settings.yaml").exists() and load_frozen(candidate)._key == key:
            return candidate
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


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
    doc["_era"] = era_of(stage)
    doc["_debug"] = setting._debug
    doc["_commit"] = commit
    doc["_resolved"] = resolved

    diff = fields_of(stage, setting)

    settings_path = run_dir / "settings.yaml"
    diff_path = run_dir / "settings_diff.yaml"
    if diff_path.exists():
        existing_diff = _parse_yaml(diff_path.read_text(), str(diff_path)) or {}
        if existing_diff != diff:
            raise SchemaError(
                f"freeze: {run_dir} already holds settings for a different key under stage {stage!r}")
        existing_settings = _parse_yaml(settings_path.read_text(), str(settings_path)) or {}
        _merge_request_fields(doc, existing_settings, sections)

    _atomic_write_yaml(settings_path, doc)
    _atomic_write_yaml(diff_path, diff)


def load_frozen(run_dir: Path) -> Setting:
    """Parse settings.yaml against the dataclasses, fill the _ block; re-merges nothing, re-resolves nothing (2.6)."""
    run_dir = Path(run_dir)
    doc = _parse_yaml((run_dir / "settings.yaml").read_text(), str(run_dir / "settings.yaml")) or {}
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
    setting._era = doc.get("_era")
    setting._debug = doc.get("_debug", False)
    setting._commit = doc.get("_commit")
    setting._resolved = doc.get("_resolved", {})
    return setting
