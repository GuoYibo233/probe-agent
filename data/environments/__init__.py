"""The environment contract every benchmark implements, the loader that finds and instantiates one by name, and the one rule for which (task, seed) pairs a run requests."""
from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path

import yaml



@dataclass
class StepObservation:
    """What `Environment.step` returns for one step."""

    action: str | None
    observation: str
    error_kind: str | None
    completed: bool


class Environment:
    """A benchmark that hands out tasks, steps, can try a call early and undo
    it, and judges."""

    NAME: str
    INSTRUCTIONS: dict[str, str]
    NO_CODE_MESSAGE: str
    RESULT_CAP: int
    SEED: int
    SPLIT_ROLE: dict[str, str]
    task_text: str | None

    def tasks(self, split: str) -> list[str]:
        raise NotImplementedError("tasks")

    def open(self, task_id: str, seed: int) -> None:
        raise NotImplementedError("open")

    def step(self, reply_text: str) -> StepObservation:
        raise NotImplementedError("step")

    def speculate(self, call: str) -> dict:
        raise NotImplementedError("speculate")

    def judge(self) -> dict:
        raise NotImplementedError("judge")

    def close(self) -> None:
        raise NotImplementedError("close")

    def split_args(self, text: str) -> tuple[str, list[tuple[str, str]], tuple[int, int]] | None:
        raise NotImplementedError("split_args")

    def build_call(self, tool: str, args: list[tuple[str, str]]) -> str:
        raise NotImplementedError("build_call")

    def complete_call(self, text: str) -> str | None:
        raise NotImplementedError("complete_call")


def open_env(name: str) -> Environment:
    """Load `data/environments/<name>.py`, instantiate its one strict subclass of `Environment`, and return it."""
    path = Path(__file__).resolve().parents[2] / "constants" / "path_datasets.yaml"
    with open(path) as f:
        doc = yaml.safe_load(f)
    blocks = sorted(k for k in doc if k != "venvs")
    if name not in blocks:
        raise ValueError(f"open_env: no block for environment {name!r} in {path}; blocks: {blocks}")

    module = importlib.import_module(f"data.environments.{name}")
    subclasses = [
        obj
        for obj in vars(module).values()
        if isinstance(obj, type) and issubclass(obj, Environment) and obj is not Environment
    ]
    if len(subclasses) != 1:
        raise ValueError(
            f"data.environments.{name}: expected exactly one strict subclass of Environment, "
            f"found {len(subclasses)}"
        )

    instance = subclasses[0]()
    missing_methods = sorted(
        m
        for m in ("tasks", "open", "step", "speculate", "judge", "close", "split_args", "build_call", "complete_call")
        if not hasattr(instance, m)
    )
    missing_attrs = sorted(
        a
        for a in ("NAME", "INSTRUCTIONS", "NO_CODE_MESSAGE", "RESULT_CAP", "SEED", "SPLIT_ROLE")
        if not hasattr(instance, a)
    )
    missing = missing_methods + missing_attrs
    if missing:
        raise ValueError(f"data.environments.{name}: instance missing {missing}")
    return instance


def requested_pairs(
    env: Environment,
    splits: list[str],
    tasks: list[str] | None,
    n_tasks: int | None,
    seeds: list[int],
) -> list[tuple[str, str, int]]:
    """The one definition of which (split, task_id, seed) triples a run asks for.

    For each split in the given order, take `env.tasks(split)` in the file's
    order, filter it by `tasks` when given, keep the first `n_tasks` of what
    is left of that split, concatenate the per-split lists in the given split
    order, and cross with `seeds` in the given order, task-major: every seed
    of one task is adjacent.
    """
    wanted = None if tasks is None else set(tasks)
    per_split: list[tuple[str, str]] = []
    for split in splits:
        ids = env.tasks(split)
        if wanted is not None:
            ids = [task_id for task_id in ids if task_id in wanted]
        if n_tasks is not None:
            ids = ids[:n_tasks]
        per_split.extend((split, task_id) for task_id in ids)
    return [(split, task_id, seed) for split, task_id in per_split for seed in seeds]
