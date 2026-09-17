"""The entrance to models/table.yaml: agent(alias) and probe(alias) resolve a row into its family module (agent only), weights alias, weights path and serving block."""
from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
_TABLE_PATH = _ROOT / "models" / "table.yaml"
_PATH_MODELS_PATH = _ROOT / "constants" / "path_models.yaml"


@dataclass(frozen=True)
class AgentModel:
    module: object        # the family module, imported by name inside agent()
    alias: str
    role: str             # "agent"
    family: str
    weights: str          # always the alias, never the path
    weights_path: str     # always the directory (or the hub id)
    serving: dict


@dataclass(frozen=True)
class ProbeModel:         # the same shape, minus `module`
    alias: str
    role: str
    family: str
    weights: str
    weights_path: str
    serving: dict


def _load_yaml(path: Path) -> dict[str, Any]:
    import yaml

    return yaml.safe_load(path.read_text()) or {}


def _table() -> dict[str, Any]:
    return _load_yaml(_TABLE_PATH)


def _weights_path(weights: str) -> str:
    path_models = _load_yaml(_PATH_MODELS_PATH)
    if weights not in path_models:
        raise KeyError(f"models: weights alias {weights!r} is not a key of constants/path_models.yaml")
    path = path_models[weights]["path"]
    if path.startswith("/") and not Path(path).exists():
        raise FileNotFoundError(f"{weights}: {path} does not exist (NFS not mounted?)")
    return path


def _row(alias: str, role: str) -> dict[str, Any]:
    table = _table()
    if alias not in table:
        known = sorted(a for a, r in table.items() if r["role"] == role)
        raise KeyError(f"models.{role}: {alias!r} is not a known {role} alias; known {role} aliases: {known}")
    row = table[alias]
    if row["role"] != role:
        raise ValueError(f"models.{role}: {alias!r} has role {row['role']!r}, not {role!r}")
    return row


def agent(alias: str) -> AgentModel:
    row = _row(alias, "agent")
    family = row["family"]
    try:
        module = importlib.import_module(f"models.agent_models.{family}")
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            f"models.agent: family {family!r} has no module models/agent_models/{family}.py"
        ) from exc
    weights = row["result"]["weights"]
    return AgentModel(
        module=module, alias=alias, role="agent", family=family,
        weights=weights, weights_path=_weights_path(weights), serving=row.get("serving") or {},
    )


def probe(alias: str) -> ProbeModel:
    row = _row(alias, "probe")
    weights = row["result"]["weights"]
    return ProbeModel(
        alias=alias, role="probe", family=row["family"],
        weights=weights, weights_path=_weights_path(weights), serving=row.get("serving") or {},
    )
