#!/usr/bin/env python3
"""Thin dispatcher for the research-loop plugin's ledger.py CLI.

Registers argparse subparsers for every subcommand name in plan.md §C2,
including subcommands whose ledger_cmds module hasn't been implemented yet.
Each implemented module exposes two functions:

    register(subparsers)   -- adds its own argparse parser(s)
    run(args) -> int        -- does the work, returns the process exit code

ledger.py lazily imports `ledger_cmds.<module>` for a subcommand only when
that subcommand is the one actually being invoked -- build_parser() peeks at
raw argv to work out which single module (if any) this call needs and
imports at most that one; every other subcommand's module is left untouched
for this process. That keeps subcommands fault-isolated from each other: an
import-time exception in an unrelated module (e.g. a later ticket's file
with a syntax error) can never affect a subcommand that doesn't need it. A
subcommand whose module is missing (ImportError) or incomplete (no
register/run) still gets a placeholder parser that accepts arbitrary
arguments, so argparse itself never rejects the call -- the dispatcher's own
"not implemented yet" message and exit code 3 are what the caller sees.

The one exception is when argv names no subcommand at all -- bare
`--help`/`-h`, or no args -- since there is then no single module to single
out. build_parser() imports every implemented module in that case so
top-level --help lists each subcommand's real description instead of a
blank placeholder line (a module that fails to import there still just
falls back to its placeholder, same as an unimplemented one).

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


def _peek_positional(argv):
    """First non-flag token in argv, skipping "--" and anything starting
    with "-". Used only to guess which single ledger_cmds module this
    invocation needs before the real parser exists -- never trusted for
    anything else. argparse's own parse (right after, against the fully
    registered parser) is what actually validates and extracts arguments;
    if the guess is wrong (or there's no top-level command at all, e.g.
    `--help`), the affected group just falls back to a placeholder and
    argparse reports whatever error it normally would."""
    for token in argv:
        if token == "--" or token.startswith("-"):
            continue
        return token
    return None


def _module_name_for_argv(argv):
    """Which single ledger_cmds module name (if any) this invocation
    implies, guessed from raw argv. None means "can't tell" (missing/
    unknown command, --help, ...) -- the caller then registers a
    placeholder for every group and lets the real argparse parse below
    report the proper error."""
    command = _peek_positional(argv)
    if command is None:
        return None
    if command == "render":
        target = _peek_positional(argv[argv.index(command) + 1:])
        return _RENDER_TARGET_MODULES.get(target)
    return _SUBCOMMAND_MODULES.get(command)


def build_parser(argv):
    """Build the top-level argparse parser and a {subcommand: module} dict.

    Normally imports at most the one ledger_cmds module `argv` implies is
    needed (via _module_name_for_argv) -- every other subcommand gets a
    placeholder parser with no import attempted at all, so an import-time
    exception in an unrelated module can never reach this invocation.

    Exception: when argv names no subcommand at all (bare `--help`/`-h`,
    or no args) -- the "what commands exist" exploration path -- there is
    no single module to single out, so every implemented module is
    imported and registered instead. That is what makes top-level --help
    show each subcommand's real description rather than a blank
    placeholder line; a module that fails to import still just falls back
    to its placeholder (no help text for that one entry), the same as an
    unimplemented module.

    `render`'s own module (chosen by args.target) is resolved separately, at
    dispatch time in _dispatch(), since render's parser is fixed and owned
    by ledger.py itself rather than delegated to a module's register()."""
    parser = argparse.ArgumentParser(
        prog="ledger.py", description="research-loop plugin ledger CLI"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_all = _peek_positional(argv) is None
    if import_all:
        wanted_module_name = None
        wanted_module = None
    else:
        wanted_module_name = _module_name_for_argv(argv)
        wanted_module = _import_cmd_module(wanted_module_name) if wanted_module_name else None

    names_by_module: dict[str, list[str]] = {}
    for name, module_name in _SUBCOMMAND_MODULES.items():
        names_by_module.setdefault(module_name, []).append(name)

    dispatch: dict[str, object] = {}
    for module_name, names in names_by_module.items():
        if import_all:
            module = _import_cmd_module(module_name)
        elif module_name == wanted_module_name:
            module = wanted_module
        else:
            module = None

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
    if argv is None:
        argv = sys.argv[1:]
    try:
        parser, dispatch = build_parser(argv)
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
