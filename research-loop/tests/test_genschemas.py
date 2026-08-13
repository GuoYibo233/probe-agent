"""Tests for ledger_cmds/genschemas.py and the ledger.py dispatcher
(issues/03-dispatcher-genschemas.md)."""
from __future__ import annotations

import hashlib
import json
import tempfile

import _lib
import helpers
import ledger as ledger_dispatcher
from ledger_cmds import genschemas

_SCHEMAS_DIR = _lib.plugin_root() / "schemas"

_SCHEMA_FILES = [
    "story.schema.json",
    "decisions.schema.json",
    "blocked.schema.json",
    "feedback.suggestion.schema.json",
    "feedback.review.schema.json",
    "runs.normal.schema.json",
    "runs.criterion.schema.json",
    "launch_order.schema.json",
]
_ALL_FILES = _SCHEMA_FILES + ["owners.default.json"]


# ---------------------------------------------------------------------------
# 1. two runs, byte-identical
# ---------------------------------------------------------------------------


def test_gen_schemas_two_runs_produce_byte_identical_files():
    with tempfile.TemporaryDirectory() as tmp:
        code, out, err = helpers.run_ledger(tmp, "gen-schemas")
        assert code == 0, (out, err)
        first = {
            name: hashlib.sha256((_SCHEMAS_DIR / name).read_bytes()).hexdigest()
            for name in _ALL_FILES
        }

        code, out, err = helpers.run_ledger(tmp, "gen-schemas")
        assert code == 0, (out, err)
        second = {
            name: hashlib.sha256((_SCHEMAS_DIR / name).read_bytes()).hexdigest()
            for name in _ALL_FILES
        }

        assert first == second


# ---------------------------------------------------------------------------
# 2. --check: green after generation, catches a byte-level mutation without
#    writing, green again once the file is restored
# ---------------------------------------------------------------------------


def test_check_flag_catches_mismatch_without_writing_then_clean_again():
    with tempfile.TemporaryDirectory() as tmp:
        code, out, err = helpers.run_ledger(tmp, "gen-schemas")
        assert code == 0, (out, err)

        code, out, err = helpers.run_ledger(tmp, "gen-schemas", "--check")
        assert code == 0, (out, err)

        # _SCHEMAS_DIR is the real, git-tracked research-loop/schemas/ (see
        # _lib.plugin_root()) -- not a sandbox. The mutate-assert-restore
        # sequence below must restore the original bytes even if an
        # assertion fails, or a real bug in --check would leave the
        # tracked story.schema.json corrupted on disk for whoever runs the
        # suite next.
        target = _SCHEMAS_DIR / "story.schema.json"
        original = target.read_bytes()
        mutated = original + b" "
        target.write_bytes(mutated)
        try:
            code, out, err = helpers.run_ledger(tmp, "gen-schemas", "--check")
            assert code == 1
            assert "story.schema.json" in err
            assert target.read_bytes() == mutated  # --check must not write to disk
        finally:
            target.write_bytes(original)

        code, out, err = helpers.run_ledger(tmp, "gen-schemas", "--check")
        assert code == 0, (out, err)


# ---------------------------------------------------------------------------
# 3. no doc keys, no unexpanded $enum, blocked.status enum matches the table
# ---------------------------------------------------------------------------


def test_generated_files_drop_doc_keys_and_expand_enum():
    files = genschemas.generate_schemas()
    for name in _SCHEMA_FILES:
        text = files[name].decode("utf-8")
        assert "_note" not in text, name
        assert "$enum" not in text, name

    blocked = json.loads(files["blocked.schema.json"])
    expected = _lib.load_tables()["rows"]["enums"]["blocked.status"]
    assert blocked["properties"]["status"]["enum"] == expected


# ---------------------------------------------------------------------------
# 4. owners.default.json == ledgers.json main table, excludes runs_legacy
# ---------------------------------------------------------------------------


def test_owners_default_matches_ledgers_main_table_and_excludes_runs_legacy():
    files = genschemas.generate_schemas()
    owners = json.loads(files["owners.default.json"])
    ledgers_table = _lib.load_tables()["ledgers"]["ledgers"]

    assert set(owners) == set(ledgers_table)
    for name, entry in ledgers_table.items():
        assert owners[name] == entry["owner"]
    assert "runs_legacy" not in owners


# ---------------------------------------------------------------------------
# 5. eight schema files present; required/primary_key are subsets of
#    properties (implementation-side regression for E4)
# ---------------------------------------------------------------------------


def test_eight_schema_files_present_and_keys_are_subsets_of_properties():
    files = genschemas.generate_schemas()
    for name in _SCHEMA_FILES:
        schema = json.loads(files[name])
        prop_keys = set(schema["properties"])
        assert set(schema["required"]) <= prop_keys, name
        assert set(schema["primary_key"]) <= prop_keys, name


# ---------------------------------------------------------------------------
# 6. dispatcher: project-wired gate blocks query, exempts gen-schemas
# ---------------------------------------------------------------------------


def test_dispatcher_gates_unwired_project_but_exempts_gen_schemas():
    with tempfile.TemporaryDirectory() as tmp:
        code, out, err = helpers.run_ledger(tmp, "query", "blocked")
        assert code == 2
        assert "project not wired" in err

        code, out, err = helpers.run_ledger(tmp, "gen-schemas")
        assert code == 0, (out, err)


# ---------------------------------------------------------------------------
# 7. an unimplemented subcommand (status has no module yet) exits 3.
#    Once T09 lands ledger_cmds/statuscmd.py, this scenario no longer
#    applies -- skip rather than fail.
# ---------------------------------------------------------------------------


def test_unimplemented_subcommand_exits_3_with_message():
    if ledger_dispatcher._import_cmd_module("statuscmd") is not None:
        return  # status is implemented now; the "not implemented yet" case is gone

    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        code, out, err = helpers.run_ledger(root, "status")
        assert code == 3
        assert err.strip() == "not implemented yet: status"


# ---------------------------------------------------------------------------
# 8. build_parser() imports at most the one ledger_cmds module the invoked
#    subcommand needs -- not every module in _SUBCOMMAND_MODULES. Otherwise a
#    non-ImportError exception while importing an unrelated module (e.g. a
#    syntax error added by a later ticket) would crash every subcommand,
#    including ones that don't need that module at all.
# ---------------------------------------------------------------------------


def test_build_parser_imports_only_the_module_the_invoked_command_needs():
    calls = []
    real_import_cmd_module = ledger_dispatcher._import_cmd_module

    def _recording(module_name):
        calls.append(module_name)
        return real_import_cmd_module(module_name)

    ledger_dispatcher._import_cmd_module = _recording
    try:
        parser, dispatch = ledger_dispatcher.build_parser(["gen-schemas"])
    finally:
        ledger_dispatcher._import_cmd_module = real_import_cmd_module

    assert calls == ["genschemas"], calls

    args = parser.parse_args(["gen-schemas"])
    assert args.command == "gen-schemas"
    assert dispatch["gen-schemas"] is not None


# ---------------------------------------------------------------------------
# 9. N1 regression (fix-round-2): a bare `--help`/`-h`/no-args invocation
#    names no subcommand at all, so build_parser() cannot single out one
#    module to import the way it does for a real subcommand (test 8 above).
#    It must fall back to importing every implemented module instead --
#    otherwise every subcommand's real (help-bearing) parser gets replaced
#    by a placeholder with no help text, and top-level --help goes blank
#    for every already-built subcommand except `render`.
# ---------------------------------------------------------------------------


def test_build_parser_bare_help_imports_every_module_so_help_text_survives():
    calls = []
    real_import_cmd_module = ledger_dispatcher._import_cmd_module

    def _recording(module_name):
        calls.append(module_name)
        return real_import_cmd_module(module_name)

    ledger_dispatcher._import_cmd_module = _recording
    try:
        parser, _dispatch = ledger_dispatcher.build_parser(["--help"])
    finally:
        ledger_dispatcher._import_cmd_module = real_import_cmd_module

    # Every module group got a real import attempt, not just genschemas.
    assert sorted(calls) == sorted(set(ledger_dispatcher._SUBCOMMAND_MODULES.values())), calls

    # gen-schemas is implemented, so its real register() ran and its
    # top-level --help description (from genschemas.py's own parser.add_
    # parser(..., help=...)) shows up instead of a blank placeholder line.
    help_text = parser.format_help()
    assert "Generate schemas/*.schema.json" in help_text, help_text


def test_build_parser_empty_and_short_help_argv_also_import_every_module():
    # `-h` and no-args at all hit the same "no positional token" case as
    # `--help` -- _peek_positional skips every "-"-prefixed token and an
    # empty argv has no tokens to find one in either way.
    for argv in ([], ["-h"]):
        parser, _dispatch = ledger_dispatcher.build_parser(argv)
        help_text = parser.format_help()
        assert "Generate schemas/*.schema.json" in help_text, (argv, help_text)
