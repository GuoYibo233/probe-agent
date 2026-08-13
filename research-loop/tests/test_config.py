"""Tests for ledger_cmds/configcmd.py -- `config-check` and `init`
(issues/04-config.md)."""
from __future__ import annotations

import builtins
import json
import tempfile
import types
from pathlib import Path

import _lib
import helpers
from ledger_cmds import configcmd


def _read_config(root: Path) -> dict:
    return json.loads((root / "research-loop.json").read_text(encoding="utf-8"))


def _write_config(root: Path, data: dict) -> None:
    (root / "research-loop.json").write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _init(root: Path, *extra_args):
    return helpers.run_ledger(root, "init", "--non-interactive", *extra_args)


def _owner_domain() -> list:
    return _lib.load_tables()["writes"]["owner_values"]


# ---------------------------------------------------------------------------
# 1. init --non-interactive -> config-check exit 0; owners key set ==
#    ledgers key set (issues/04-config.md test 1)
# ---------------------------------------------------------------------------


def test_init_non_interactive_then_config_check_is_clean_and_key_sets_match():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        code, out, err = _init(root)
        assert code == 0, (out, err)

        code, out, err = helpers.run_ledger(root, "config-check")
        assert code == 0, (out, err)

        data = _read_config(root)
        assert set(data["ledgers"]) == set(data["owners"])
        ledgers_table = _lib.load_tables()["ledgers"]["ledgers"]
        assert set(data["ledgers"]) == set(ledgers_table)


# ---------------------------------------------------------------------------
# 2. init again without --force -> exit 1; --force lets it through
#    (issues/04-config.md test 2)
# ---------------------------------------------------------------------------


def test_init_twice_without_force_rejected_with_force_allowed():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        code, out, err = _init(root)
        assert code == 0, (out, err)

        code, out, err = _init(root)
        assert code == 1
        assert "config exists (use --force)" in err

        code, out, err = _init(root, "--force")
        assert code == 0, (out, err)


# ---------------------------------------------------------------------------
# 3. delete a key from owners -> config-check exit 1, names the key-set
#    mismatch (issues/04-config.md test 3)
# ---------------------------------------------------------------------------


def test_owners_missing_a_key_fails_config_check_naming_the_mismatch():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        code, out, err = _init(root)
        assert code == 0, (out, err)

        data = _read_config(root)
        del data["owners"]["principles"]
        _write_config(root, data)

        code, out, err = helpers.run_ledger(root, "config-check")
        assert code == 1
        assert "config.owners" in err
        assert "key set must equal config.ledgers key set" in err
        assert "principles" in err


# ---------------------------------------------------------------------------
# 4. an owners value outside the nine owner_values -> exit 1, message
#    lists the value domain (issues/04-config.md test 4)
# ---------------------------------------------------------------------------


def test_owners_bad_value_fails_config_check_and_lists_the_nine_values():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        code, out, err = _init(root)
        assert code == 0, (out, err)

        data = _read_config(root)
        data["owners"]["principles"] = "nobody"
        _write_config(root, data)

        code, out, err = helpers.run_ledger(root, "config-check")
        assert code == 1
        assert "config.owners.principles" in err
        assert "'nobody'" in err
        for value in _owner_domain():
            assert value in err, (value, err)


# ---------------------------------------------------------------------------
# 5. ledger_caps: a cap on a non-jsonl ledger rejected, a cap on
#    runs (must stay null) rejected, a cap on a jsonl ledger allowed
#    (issues/04-config.md test 5)
# ---------------------------------------------------------------------------


def test_ledger_caps_rejects_non_jsonl_and_runs_cap_allows_jsonl():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        code, out, err = _init(root)
        assert code == 0, (out, err)
        data = _read_config(root)

        data["ledger_caps"] = {"principles": 100}
        _write_config(root, data)
        code, out, err = helpers.run_ledger(root, "config-check")
        assert code == 1
        assert "config.ledger_caps.principles" in err

        data["ledger_caps"] = {"runs": 500}
        _write_config(root, data)
        code, out, err = helpers.run_ledger(root, "config-check")
        assert code == 1
        assert "config.ledger_caps.runs" in err

        data["ledger_caps"] = {"blocked": 500}
        _write_config(root, data)
        code, out, err = helpers.run_ledger(root, "config-check")
        assert code == 0, (out, err)


# ---------------------------------------------------------------------------
# 6. registry_cmd null -> config-check exit 0, output names the null key
#    and its null_effect text verbatim (issues/04-config.md test 6)
# ---------------------------------------------------------------------------


def test_null_registry_cmd_reported_with_verbatim_null_effect():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        code, out, err = _init(root)
        assert code == 0, (out, err)
        assert _read_config(root)["registry_cmd"] is None

        code, out, err = helpers.run_ledger(root, "config-check")
        assert code == 0, (out, err)
        assert "null key registry_cmd" in out
        null_effect = _lib.load_tables()["config"]["keys"]["registry_cmd"]["null_effect"]
        assert null_effect in out


# ---------------------------------------------------------------------------
# 7. --set registry_cmd='"python3 x.py"' takes effect as a plain string
#    (issues/04-config.md test 7)
# ---------------------------------------------------------------------------


def test_set_flag_with_quoted_json_string_becomes_a_plain_string():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        code, out, err = _init(root, "--set", 'registry_cmd="python3 x.py"')
        assert code == 0, (out, err)

        data = _read_config(root)
        assert data["registry_cmd"] == "python3 x.py"


# ---------------------------------------------------------------------------
# 8. config.ledgers gets a name the table doesn't know -> exit 1
#    (issues/04-config.md test 8). owners gets the same key with a valid
#    value so check 1 (ledgers/owners key-set parity) passes and it is
#    specifically check 2 (unknown ledger name) that fires.
# ---------------------------------------------------------------------------


def test_unknown_ledger_name_in_config_ledgers_fails_config_check():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        code, out, err = _init(root)
        assert code == 0, (out, err)

        data = _read_config(root)
        data["ledgers"]["foo"] = "x.jsonl"
        data["owners"]["foo"] = "idea"
        _write_config(root, data)

        code, out, err = helpers.run_ledger(root, "config-check")
        assert code == 1
        assert "config.ledgers.foo" in err
        assert "not a known ledger" in err


# ---------------------------------------------------------------------------
# 9. boundary: an archive-companion name (".archive." in the key or the
#    path value) is rejected even though it would also fail the
#    "unknown ledger" check -- the archive-specific message must be the
#    one that actually fires (issues/04-config.md §要求 point 2).
# ---------------------------------------------------------------------------


def test_archive_companion_name_in_config_ledgers_rejected_specifically():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        code, out, err = _init(root)
        assert code == 0, (out, err)

        data = _read_config(root)
        data["ledgers"]["decisions.archive"] = "ops/decisions.archive.jsonl"
        data["owners"]["decisions.archive"] = "deploy"
        _write_config(root, data)

        code, out, err = helpers.run_ledger(root, "config-check")
        assert code == 1
        assert "archive companion name is not a ledger" in err


# ---------------------------------------------------------------------------
# 10. boundary: interactive prompting only asks for keys not already
#     answered by --set; blank input leaves the key null, a non-blank
#     answer is parsed the same way --set values are.
# ---------------------------------------------------------------------------


def test_interactive_init_skips_set_keys_blank_is_null_non_blank_is_parsed():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        prompted_keys = []
        answers = {"registry_cmd": '"python3 y.py"'}
        real_input = builtins.input

        def fake_input(prompt):
            key = prompt.split(" (", 1)[0]
            prompted_keys.append(key)
            return answers.get(key, "")

        builtins.input = fake_input
        try:
            args = types.SimpleNamespace(
                root=str(root), non_interactive=False,
                set=['record_cmd="echo hi"'], force=False,
            )
            code = configcmd._run_init(args)
        finally:
            builtins.input = real_input

        assert code == 0
        assert "record_cmd" not in prompted_keys  # answered via --set, not prompted
        assert "registry_cmd" in prompted_keys

        data = _read_config(root)
        assert data["record_cmd"] == "echo hi"
        assert data["registry_cmd"] == "python3 y.py"
        assert data["runtime_factor"] is None  # prompted, left blank


# ---------------------------------------------------------------------------
# 11. config-check on a project with no research-loop.json at all: exit 1,
#     no traceback.
# ---------------------------------------------------------------------------


def test_config_check_with_no_config_file_exits_1():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        code, out, err = helpers.run_ledger(root, "config-check")
        assert code == 1
        assert "config not found" in err
