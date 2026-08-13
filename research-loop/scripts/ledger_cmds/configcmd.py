"""`ledger.py config-check [--root PATH]` and `ledger.py init [--root PATH]
[--non-interactive] [--set key=JSON ...] [--force]` (issues/04-config.md).

config-check validates a project's research-loop.json against the plugin's
closed-list tables -- tables/config.json (key domain), tables/writes.json
(owner_values), tables/ledgers.json (ledger names/formats + _cap_rules) --
and, once the structure passes, prints one line per null/missing key naming
what that null locks (tables/config.json null_effect, copied verbatim) or
which plugin default it falls back to (roles/standing_authorization/
runtime_factor).

init writes a fresh research-loop.json skeleton: ledgers gets every
tables/ledgers.json main-table key at its default_path (optional ledgers
never go in); owners is copied from schemas/owners.default.json without
asking; every other key takes its --set value (json.loads, falling back to
the raw string on parse failure) if given, else -- unless --non-interactive
-- is asked for interactively (blank input = leave null). The skeleton is
then run back through the same structural check init itself, so a config
init produces always passes config-check by construction (spec.md §9).

Both structural failures and init's own "already wired" guard exit 1 (not
the RLError-driven exit 2 the rest of the CLI uses) -- config-check is a
gate other things read machine output from, not a "your invocation was
malformed" error, so failures are caught locally rather than left to
propagate to ledger.py's top-level RLError handler.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import _lib
from _lib import RLError, fail

# roles/standing_authorization/runtime_factor: on null, the null report shows
# the plugin default (via Config.get, which already resolves it) instead of
# the key's null_effect text -- spec: "为 null 打 -> default: <plugin默认>".
_DEFAULTED_KEYS = {"roles", "standing_authorization", "runtime_factor"}


def register(subparsers):
    check_parser = subparsers.add_parser(
        "config-check",
        help="Validate research-loop.json against tables/config.json + writes.json + ledgers.json.",
    )
    check_parser.add_argument("--root", help="Project root (default: walk up from cwd).")

    init_parser = subparsers.add_parser(
        "init",
        help="Write a research-loop.json skeleton (ledgers/owners auto-filled).",
    )
    init_parser.add_argument("--root", help="Project root (default: cwd).")
    init_parser.add_argument("--non-interactive", action="store_true")
    init_parser.add_argument(
        "--set", action="append", default=[], metavar="key=JSON",
        help="Set one config key's value; JSON-parsed, kept as a string on parse failure.",
    )
    init_parser.add_argument("--force", action="store_true")


def run(args) -> int:
    if args.command == "init":
        return _run_init(args)
    return _run_config_check(args)


# ---------------------------------------------------------------------------
# root resolution
# ---------------------------------------------------------------------------


def _root_by_walking_up(args) -> Path:
    """config-check: an explicit --root is authoritative; otherwise walk up
    from cwd like every other subcommand's implicit project resolution
    does. Falls back to cwd itself (not None) so callers always get a path
    to report "config not found" against."""
    if args.root:
        return Path(args.root).resolve()
    found = _lib.find_project_root()
    return found if found is not None else Path.cwd()


def _root_for_init(args) -> Path:
    """init: never walks up -- it creates a config exactly at --root (or
    cwd), never in some discovered ancestor project's directory."""
    return Path(args.root).resolve() if args.root else Path.cwd()


# ---------------------------------------------------------------------------
# structural checks (tables/config.json keys' domain + writes.json
# owner_values + tables/ledgers.json _cap_rules; spec.md §7, §9 config-check)
# ---------------------------------------------------------------------------


def _check_structure(cfg: _lib.Config) -> None:
    """Raises RLError on the first structural violation found, checked in
    the order the five rules are listed in issues/04-config.md. Every
    fail() call passes a value so the message always ends in the ticket's
    required "(got: ...)" suffix."""
    tables = _lib.load_tables()
    ledgers_table = tables["ledgers"]["ledgers"]
    optional_table = tables["ledgers"].get("optional_ledgers", {})
    owner_values = set(tables["writes"]["owner_values"])
    known_ledger_names = set(ledgers_table) | set(optional_table)

    config_ledgers = cfg.data.get("ledgers") or {}
    config_owners = cfg.data.get("owners") or {}

    # 1. ledgers key set == owners key set, strictly.
    ledgers_keys = set(config_ledgers)
    owners_keys = set(config_owners)
    if ledgers_keys != owners_keys:
        fail(
            "config", "owners",
            "key set must equal config.ledgers key set",
            sorted(ledgers_keys ^ owners_keys),
        )

    # 2. every config.ledgers key is known (main or optional table); every
    #    main-table key is present in config.ledgers (optional ledgers may
    #    add more, nothing else may); archive companion names rejected.
    for key, value in config_ledgers.items():
        if ".archive." in key or (isinstance(value, str) and ".archive." in value):
            fail("config", f"ledgers.{key}", "archive companion name is not a ledger", value)
        if key not in known_ledger_names:
            fail(
                "config", f"ledgers.{key}",
                "not a known ledger (not in tables/ledgers.json)", value,
            )
    missing_main = sorted(set(ledgers_table) - ledgers_keys)
    if missing_main:
        fail("config", "ledgers", "missing required ledger keys", missing_main)

    # 3. owners values must be one of writes.json's nine owner_values.
    for key, value in config_owners.items():
        if value not in owner_values:
            fail(
                "config", f"owners.{key}",
                f"owner value must be one of {sorted(owner_values)}",
                value,
            )

    # 4. ledger_caps: keys are known ledgers, jsonl-format only;
    #    runs/runs_legacy accept only null.
    caps = cfg.data.get("ledger_caps") or {}
    for key, value in caps.items():
        if key not in known_ledger_names:
            fail("config", f"ledger_caps.{key}", "key is not a known ledger", value)
        if key in ("runs", "runs_legacy"):
            if value is not None:
                fail("config", f"ledger_caps.{key}", "runs/runs_legacy caps must be null", value)
            continue
        entry = ledgers_table.get(key) or optional_table.get(key)
        fmt = entry["format"] if entry else None
        if fmt != "jsonl":
            fail("config", f"ledger_caps.{key}", "cap is only allowed for jsonl ledgers", value)

    # 5. inspection_policy v1 value domain: only "always" (null is fine --
    #    that's the null report's job, not a structural error).
    policy = cfg.data.get("inspection_policy")
    if policy is not None and policy != "always":
        fail("config", "inspection_policy", "must be 'always' (v1 value domain)", policy)


def _null_report_lines(cfg: _lib.Config) -> list[str]:
    """One line per null/missing top-level config key, in tables/config.json
    order. Not an error report -- printed on the exit-0 (structure passed)
    path only."""
    config_keys = _lib.load_tables()["config"]["keys"]
    lines = []
    for key, entry in config_keys.items():
        if not cfg.null_locked(key):
            continue
        if key in _DEFAULTED_KEYS:
            default_text = json.dumps(cfg.get(key), sort_keys=True, ensure_ascii=False)
            lines.append(f"null key {key} -> default: {default_text}")
        else:
            lines.append(f"null key {key} -> locks: {entry['null_effect']}")
    return lines


def _run_config_check(args) -> int:
    root = _root_by_walking_up(args)
    config_path = root / "research-loop.json"
    if not config_path.exists():
        print(f"config not found: {config_path} (run: ledger.py init)", file=sys.stderr)
        return 1

    cfg = _lib.load_config(root)
    try:
        _check_structure(cfg)
    except RLError as exc:
        print(exc.message, file=sys.stderr)
        return 1

    for line in _null_report_lines(cfg):
        print(line)
    return 0


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def _parse_json_or_string(raw: str):
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return raw


def _parse_set_args(pairs: list[str]) -> dict:
    overrides = {}
    for raw in pairs:
        if "=" not in raw:
            fail("config", "--set", "must be key=JSON", raw)
        key, _, raw_value = raw.partition("=")
        overrides[key] = _parse_json_or_string(raw_value)
    return overrides


def _prompt_value(key: str, entry: dict):
    example = entry.get("example", "")
    raw = input(f"{key} (example: {example}; blank = null): ").strip()
    if not raw:
        return None
    return _parse_json_or_string(raw)


def _build_skeleton(
    config_keys: dict, ledgers_table: dict, owners: dict, overrides: dict, interactive: bool,
) -> dict:
    data = {
        "ledgers": {name: entry["default_path"] for name, entry in ledgers_table.items()},
        "owners": owners,
    }
    for key, entry in config_keys.items():
        if key in ("ledgers", "owners"):
            continue
        if key in overrides:
            data[key] = overrides[key]
        elif interactive:
            data[key] = _prompt_value(key, entry)
        else:
            data[key] = None
    return data


def _run_init(args) -> int:
    root = _root_for_init(args)
    config_path = root / "research-loop.json"
    if config_path.exists() and not args.force:
        print("config exists (use --force)", file=sys.stderr)
        return 1

    tables = _lib.load_tables()
    ledgers_table = tables["ledgers"]["ledgers"]
    config_keys = tables["config"]["keys"]

    owners_path = _lib.plugin_root() / "schemas" / "owners.default.json"
    owners = json.loads(owners_path.read_text(encoding="utf-8"))

    overrides = _parse_set_args(args.set)
    data = _build_skeleton(
        config_keys, ledgers_table, owners, overrides,
        interactive=not args.non_interactive,
    )

    root.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # "init 产物直接过" (spec.md §9): the freshly written skeleton must pass
    # its own structural check by construction; run it the same way
    # config-check would and surface the same output.
    cfg = _lib.load_config(root)
    try:
        _check_structure(cfg)
    except RLError as exc:
        print(exc.message, file=sys.stderr)
        return 1

    for line in _null_report_lines(cfg):
        print(line)
    return 0
