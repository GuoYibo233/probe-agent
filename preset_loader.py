"""Reader for configs/, pure standard library (the collection venv cannot install
pydantic 2; the lesson is at the top of envs/collect/common.py).

configs/models.json is the single model-address mapping; model_registry.py reads from
here. configs/presets/*.json: one file is one set of generation settings: a model alias +
a server section (vLLM launch args, consumed by serve_preset.py) + a client section
(sampling params, consumed by each entry point). Both sections are optional; in the
client section, null = not specified, falls through to the caller's own default.
temperature comes only from the client section; when a preset writes it as null, the
generation entry point stops right there via require_temperature and names which preset
(the BFCL handler is an exception: when null, it uses BFCL's own default tier).

Usage from an entry-point script (three-tier priority: explicit CLI value > preset value >
original default):

    from preset_loader import load_preset, merge_client
    pre = load_preset(args.preset)                      # each entry point's argparse default is "default"
    eff = merge_client({"api": args.api, ...},          # None = user did not give it explicitly
                       pre.get("client"),
                       {"api": "raw", ...})             # original default
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODELS_JSON = ROOT / "configs" / "models.json"
PRESET_DIR = ROOT / "configs" / "presets"

# valid keys of the client section -> expected type (None is always valid)
CLIENT_KEYS = {
    "api": str,
    "reasoning_effort": str,
    "temperature": (int, float),
    "top_p": (int, float),
    "max_tokens": int,
    "stop": list,
    "start_date": str,
    "seed": int,
}

# valid keys of the server section -> expected type
SERVER_KEYS = {
    "host": str,
    "port": int,
    "served_model_name": str,
    "gpu_memory_utilization": (int, float),
    "max_model_len": int,
    "env": dict,
    "extra_flags": str,
}

TOP_KEYS = {"desc", "model", "server", "client"}


def load_models():
    """Returns {"models": {alias: {"path","note"}}, "aliases": {short name: alias}}."""
    d = json.loads(MODELS_JSON.read_text())
    return {"models": d["models"], "aliases": d.get("aliases", {})}


def list_presets():
    return sorted(p.stem for p in PRESET_DIR.glob("*.json"))


def _check_node(name, node, keys, errs):
    for k, v in node.items():
        if k not in keys:
            errs.append(f"{name} section has unknown key {k!r} (valid keys: {sorted(keys)})")
        elif v is not None and not isinstance(v, keys[k]):
            errs.append(f"{name}.{k} has the wrong type: {type(v).__name__}({v!r})")
    if name == "server" and node.get("env") is not None:
        for ek, ev in node["env"].items():
            if not isinstance(ek, str) or not isinstance(ev, str):
                errs.append(f"server.env keys and values must all be strings: {ek!r}={ev!r}")


def validate(preset, models=None):
    """Returns the list of problems (empty = passes). If models is not given, reads models.json fresh."""
    errs = []
    unknown = set(preset) - TOP_KEYS
    if unknown:
        errs.append(f"top level has unknown keys {sorted(unknown)} (valid keys: {sorted(TOP_KEYS)})")
    if "model" not in preset:
        errs.append("missing top-level model (an alias from models.json)")
    else:
        m = models or load_models()
        key = m["aliases"].get(preset["model"], preset["model"])
        if key not in m["models"]:
            errs.append(f"model alias {preset['model']!r} is not in models.json")
    if "client" in preset:
        _check_node("client", preset["client"], CLIENT_KEYS, errs)
    if "server" in preset:
        _check_node("server", preset["server"], SERVER_KEYS, errs)
        for need in ("host", "port", "served_model_name"):
            if preset["server"].get(need) is None:
                errs.append(f"server section is missing {need} (the launcher can't assemble the command)")
    return errs


def load_preset(name):
    """Reads and validates a preset by name; the name is the filename under configs/presets/ minus .json."""
    path = PRESET_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"preset {name!r} does not exist; existing presets: {list_presets()}")
    preset = json.loads(path.read_text())
    errs = validate(preset)
    if errs:
        raise ValueError(f"preset {name} is invalid:\n" + "\n".join(errs))
    preset["_name"] = name
    preset["_path"] = str(path)
    return preset


def merge_client(cli, client_node, fallbacks):
    """Merges key by key: explicit CLI value (non-None) > preset value (non-null) > the
    original default in fallbacks. A key absent from all three ends up None. Only
    processes keys that appear in cli and fallbacks -- an extra key present only in the
    preset (e.g. stop, which the collector has no use for) is never forced onto the
    caller.
    """
    node = client_node or {}
    out = {}
    for k in set(cli) | set(fallbacks):
        if cli.get(k) is not None:
            out[k] = cli[k]
        elif node.get(k) is not None:
            out[k] = node[k]
        else:
            out[k] = fallbacks.get(k)
    return out


def require_temperature(value, preset_name):
    """Temperature check for a generation entry point: the merged temperature must be a
    number; if it is, return it unchanged. temperature has only one source, the preset's
    client section, so when a preset writes it as null (e.g. the BFCL one, where
    temperature follows BFCL's own tier) this stops right here and reports clearly which
    preset it is.
    """
    if isinstance(value, (int, float)):
        return value
    raise SystemExit(
        f"preset {preset_name}'s client.temperature is null;"
        f"generation entry points read temperature only from the preset, use a preset that sets temperature"
        f"(existing: {list_presets()})")


def base_url_of(preset):
    """Assembles the /v1 endpoint from the server section; returns None if there is no server section."""
    srv = preset.get("server")
    if not srv:
        return None
    return f"http://{srv['host']}:{srv['port']}/v1"


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(json.dumps(load_preset(sys.argv[1]), ensure_ascii=False, indent=2))
    else:
        for n in list_presets():
            print(f"{n:24s} {json.loads((PRESET_DIR / (n + '.json')).read_text()).get('desc', '')}")
