"""The single read access point for this project's model address mapping. The table itself
lives in configs/models.json (moved there 2026-08-20, part of the gen-preset rework); only
the reader stays here, and resolve()'s signature and behavior are unchanged from before the move.

All scripts get paths through resolve(); hard-coding is not allowed.
To add a model: add an entry under models in configs/models.json (alias all lowercase).
For a local directory, prefer writing an absolute path; for one that goes through the HF
cache, write the hub ID.
CLI usage: python3 model_registry.py qwen3.6
"""

import json
from pathlib import Path

_D = json.loads((Path(__file__).resolve().parent
                 / "configs" / "models.json").read_text())
MODELS = {k: (v["path"], v["note"]) for k, v in _D["models"].items()}
ALIASES = dict(_D.get("aliases", {}))


def resolve(name: str) -> str:
    key = ALIASES.get(name.lower(), name.lower())
    if key not in MODELS:
        raise KeyError(f"unknown model '{name}'; known: {sorted(MODELS)}")
    path, _ = MODELS[key]
    if path.startswith("/") and not Path(path).exists():
        raise FileNotFoundError(f"{key}: {path} does not exist (NFS not mounted?)")
    return path


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(resolve(sys.argv[1]))
    else:
        for k, (p, note) in MODELS.items():
            print(f"{k:14s} {p}   # {note}")
