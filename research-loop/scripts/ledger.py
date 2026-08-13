#!/usr/bin/env python3
"""Thin dispatcher for the research-loop plugin's ledger.py CLI.

Registers argparse subparsers for every subcommand name in plan.md §C2,
including subcommands whose ledger_cmds module hasn't been implemented yet.
Each implemented module exposes two functions:

    register(subparsers)   -- adds its own argparse parser(s)
    run(args) -> int        -- does the work, returns the process exit code

ledger.py lazily imports `ledger_cmds.<module>` for each subcommand at
startup. A subcommand whose module is missing (ImportError) or incomplete
(no register/run) still gets a placeholder parser that accepts arbitrary
arguments, so argparse itself never rejects the call -- the dispatcher's own
"not implemented yet" message and exit code 3 are what the caller sees.

Every subcommand except gen-schemas/init/config-check requires a wired
project (a research-loop.json findable by walking up from cwd) before it is
dispatched at all. RLError raised by any module is caught once, here, in
main(): the message goes to stderr and the process exits 2. Every other
exception is left to propagate (no swallowed tracebacks).
"""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _lib  # noqa: E402
from _lib import RLError  # noqa: E402

# Top-level subcommand name -> ledger_cmds module that owns it (plan.md §C2
# CLI listing x plan.md's scripts/ledger_cmds/ directory tree). Multiple
# names can share one module (e.g. grant/decision/decision-withdraw are all
# decisionscmd) -- that module's single register() call adds all of them.
_SUBCOMMAND_MODULES = {
    "gen-schemas": "genschemas",
    "config-check": "configcmd",
    "init": "configcmd",
    "blocked": "blockedcmd",
    "grant": "decisionscmd",
    "decision": "decisionscmd",
    "decision-withdraw": "decisionscmd",
    "story": "storycmd",
    "feedback": "feedbackcmd",
    "runs-append": "runscmd",
    "launch-order": "launchcmd",
    "approve-spec": "launchcmd",
    "query": "querycmd",
    "status": "statuscmd",
    "principles-lint": "principlescmd",
    "freeze-legacy": "freezecmd",
}

# `render principles|blocked` is one CLI subcommand (plan.md §C2) but its two
# targets are owned by two different modules (plan.md's directory tree:
# principlescmd owns "render principles", querycmd owns "render blocked").
# Its argument surface is fixed (just the target choice) so ledger.py
# registers the "render" parser itself instead of delegating registration.
_RENDER_TARGET_MODULES = {
    "principles": "principlescmd",
    "blocked": "querycmd",
}

# Subcommands that run before -- or without needing -- a wired project.
_UNWIRED_EXEMPT = {"gen-schemas", "init", "config-check"}


def _import_cmd_module(module_name: str):
    """Import ledger_cmds.<module_name>. Returns None (never raises) if the
    module doesn't exist yet, or exists but doesn't implement the module
    protocol (register + run)."""
    try:
        module = importlib.import_module(f"ledger_cmds.{module_name}")
    except ImportError:
        return None
    if not hasattr(module, "register") or not hasattr(module, "run"):
        return None
    return module


def _add_placeholder(subparsers, name: str):
    """A parser that accepts any arguments, for a subcommand whose module
    isn't implemented yet -- guarantees argparse itself never rejects the
    call, so the "not implemented yet" / exit 3 path is always reachable."""
    parser = subparsers.add_parser(name, add_help=False)
    parser.add_argument("_placeholder_args", nargs=argparse.REMAINDER)
    return parser


def build_parser():
    """Build the top-level argparse parser and a {subcommand: module} dict
    for subcommands whose module loaded successfully (render is handled
    separately at run time, since its module depends on args.target)."""
    parser = argparse.ArgumentParser(
        prog="ledger.py", description="research-loop plugin ledger CLI"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    names_by_module: dict[str, list[str]] = {}
    for name, module_name in _SUBCOMMAND_MODULES.items():
        names_by_module.setdefault(module_name, []).append(name)

    dispatch: dict[str, object] = {}
    for module_name, names in names_by_module.items():
        module = _import_cmd_module(module_name)
        if module is not None:
            module.register(subparsers)
            for name in names:
                dispatch[name] = module
        else:
            for name in names:
                _add_placeholder(subparsers, name)

    render_parser = subparsers.add_parser(
        "render", help="Render a maintenance view (principles|blocked)."
    )
    render_parser.add_argument("target", choices=sorted(_RENDER_TARGET_MODULES))

    return parser, dispatch


def _dispatch(args, dispatch: dict) -> int:
    if args.command == "render":
        module = _import_cmd_module(_RENDER_TARGET_MODULES[args.target])
        if module is None:
            print(f"not implemented yet: render {args.target}", file=sys.stderr)
            return 3
        return module.run(args)

    module = dispatch.get(args.command)
    if module is None:
        print(f"not implemented yet: {args.command}", file=sys.stderr)
        return 3
    return module.run(args)


def main(argv=None) -> int:
    try:
        parser, dispatch = build_parser()
        args = parser.parse_args(argv)

        if args.command not in _UNWIRED_EXEMPT:
            if _lib.find_project_root() is None:
                print(
                    "project not wired: research-loop.json not found (run: ledger.py init)",
                    file=sys.stderr,
                )
                return 2

        return _dispatch(args, dispatch)
    except RLError as exc:
        print(exc.message, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
