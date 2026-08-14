"""Tests for scripts/_lib.py and tests/helpers.py (issues/02-lib.md)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import _lib
import helpers


# ---------------------------------------------------------------------------
# 1. alloc_id
# ---------------------------------------------------------------------------


def test_alloc_id_empty_table_gives_first_id():
    assert _lib.alloc_id([], "blocked_id", "B") == "B001"


def test_alloc_id_increments_from_existing_max():
    rows = [{"decision_id": "D003"}, {"decision_id": "D009"}, {"decision_id": "D005"}]
    assert _lib.alloc_id(rows, "decision_id", "D") == "D010"


def test_alloc_id_widens_past_999():
    rows = [{"decision_id": "D999"}]
    assert _lib.alloc_id(rows, "decision_id", "D") == "D1000"


# ---------------------------------------------------------------------------
# 1a. jsonl_rows / _read_jsonl_file -- malformed line handling (F4, sdd/
#     final-review.md): a bad line used to blow up as a bare
#     json.decoder.JSONDecodeError -- not the contract's exit 2, no
#     "<ledger>.<field>: <detail>" text, no file/line pointer -- crashing
#     every command that starts a session (`status` is the first thing every
#     session runs). It must now surface as an ordinary RLError naming the
#     ledger and the 1-indexed line number.
# ---------------------------------------------------------------------------


def test_jsonl_rows_bad_line_raises_rlerror_with_ledger_and_line_number():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "ops" / "blocked.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"blocked_id": "B001", "status": "open"}\n{"blocked_id": "B002"\n',
                         encoding="utf-8")
        try:
            _lib.jsonl_rows(path)
        except _lib.RLError as e:
            assert e.message.startswith("blocked.line 2: is not valid JSON")
        else:
            raise AssertionError("expected RLError for a malformed jsonl line")


def test_query_blocked_bad_jsonl_line_exits_2_with_ledger_and_line_number():
    # CLI-level companion to the unit test above: the same corruption, hit
    # through `ledger.py query` the way a real session would, lands the
    # contract's exit 2 with the same text -- not a bare traceback.
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(Path(tmp))
        cfg = _lib.load_config(root)
        blocked_path = cfg.ledger_path("blocked")
        blocked_path.parent.mkdir(parents=True, exist_ok=True)
        blocked_path.write_text('{"blocked_id": "B001"\n', encoding="utf-8")  # truncated

        code, out, err = helpers.run_ledger(root, "query", "blocked", "--all-rows")

        assert code == 2, (out, err)
        assert "blocked.line 1: is not valid JSON" in err


# ---------------------------------------------------------------------------
# 2. inplace_update
# ---------------------------------------------------------------------------


def test_inplace_update_bad_line_raises_rlerror_with_ledger_and_line_number():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "ops" / "blocked.jsonl"
        helpers.write_jsonl(path, [helpers.make_blocked_row(blocked_id="B001")])
        with open(path, "a", encoding="utf-8") as f:
            f.write('{"blocked_id": "B002", unterminated\n')
        try:
            _lib.inplace_update(path, "blocked_id", "B001", {"status": "closed"},
                                 whitelist={"status"})
        except _lib.RLError as e:
            assert e.message.startswith("blocked.line 2: is not valid JSON")
        else:
            raise AssertionError("expected RLError for a malformed jsonl line")


def test_inplace_update_rejects_non_whitelisted_field_with_exact_message():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "ops" / "blocked.jsonl"
        helpers.write_jsonl(path, [helpers.make_blocked_row(blocked_id="B001")])
        try:
            _lib.inplace_update(path, "blocked_id", "B001", {"question": "new question"},
                                 whitelist={"status", "answer"})
        except _lib.RLError as e:
            assert e.message == "blocked.question: field is not in-place updatable"
        else:
            raise AssertionError("expected RLError for a non-whitelisted field")


def test_inplace_update_rejects_missing_row():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "ops" / "blocked.jsonl"
        helpers.write_jsonl(path, [helpers.make_blocked_row(blocked_id="B001")])
        try:
            _lib.inplace_update(path, "blocked_id", "B999", {"status": "closed"},
                                 whitelist={"status"})
        except _lib.RLError as e:
            assert "row not found" in e.message
        else:
            raise AssertionError("expected RLError for a row that does not exist")


def test_inplace_update_is_atomic_and_leaves_other_rows_byte_identical():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "ops" / "blocked.jsonl"
        rows = [
            helpers.make_blocked_row(blocked_id="B001", question="first row"),
            helpers.make_blocked_row(blocked_id="B002", question="second row, must stay untouched"),
        ]
        helpers.write_jsonl(path, rows)
        original_lines = path.read_bytes().splitlines(keepends=True)

        updated = _lib.inplace_update(path, "blocked_id", "B001", {"status": "closed"},
                                       whitelist={"status"})
        assert updated["status"] == "closed"

        new_lines = path.read_bytes().splitlines(keepends=True)
        assert len(new_lines) == len(original_lines)
        assert new_lines[1] == original_lines[1]  # untouched row: identical bytes
        assert new_lines[0] != original_lines[0]  # updated row: changed


# ---------------------------------------------------------------------------
# 3. validate
# ---------------------------------------------------------------------------


def test_validate_required_field_missing():
    schema = {"required": ["a"], "additionalProperties": True,
              "properties": {"a": {"type": "string"}}, "conditional": []}
    try:
        _lib.validate({}, schema, "t")
    except _lib.RLError as e:
        assert e.message.startswith("t.a:")
    else:
        raise AssertionError("expected RLError for missing required field")


def test_validate_additional_properties_rejects_unknown_field():
    schema = {"required": [], "additionalProperties": False,
              "properties": {"a": {"type": "string"}}, "conditional": []}
    try:
        _lib.validate({"a": "x", "z": 1}, schema, "t")
    except _lib.RLError as e:
        assert e.message.startswith("t.z:")
    else:
        raise AssertionError("expected RLError for a field not in the schema")


def test_validate_type_union_accepts_any_member_and_rejects_others():
    schema = {"required": [], "additionalProperties": True,
              "properties": {"a": {"type": ["string", "null"]}}, "conditional": []}
    _lib.validate({"a": "x"}, schema, "t")
    _lib.validate({"a": None}, schema, "t")
    try:
        _lib.validate({"a": 5}, schema, "t")
    except _lib.RLError:
        pass
    else:
        raise AssertionError("expected RLError: 5 matches neither string nor null")


def test_validate_bool_is_not_treated_as_integer():
    schema = {"required": [], "additionalProperties": True,
              "properties": {"n": {"type": "integer"}}, "conditional": []}
    _lib.validate({"n": 3}, schema, "t")
    try:
        _lib.validate({"n": True}, schema, "t")
    except _lib.RLError:
        pass
    else:
        raise AssertionError("expected RLError: bool must not satisfy integer type")


def test_validate_enum():
    schema = {"required": [], "additionalProperties": True,
              "properties": {"status": {"enum": ["ok", "failed"]}}, "conditional": []}
    _lib.validate({"status": "ok"}, schema, "t")
    try:
        _lib.validate({"status": "nope"}, schema, "t")
    except _lib.RLError:
        pass
    else:
        raise AssertionError("expected RLError for a value outside the enum")


def test_validate_const():
    schema = {"required": [], "additionalProperties": True,
              "properties": {"kind": {"type": "string", "const": "suggestion"}}, "conditional": []}
    _lib.validate({"kind": "suggestion"}, schema, "t")
    try:
        _lib.validate({"kind": "review"}, schema, "t")
    except _lib.RLError:
        pass
    else:
        raise AssertionError("expected RLError for a value that does not equal const")


def test_validate_minimum():
    schema = {"required": [], "additionalProperties": True,
              "properties": {"schema_version": {"type": "integer", "minimum": 1}}, "conditional": []}
    _lib.validate({"schema_version": 1}, schema, "t")
    try:
        _lib.validate({"schema_version": 0}, schema, "t")
    except _lib.RLError:
        pass
    else:
        raise AssertionError("expected RLError for a value below minimum")


def test_validate_minitems():
    schema = {"required": [], "additionalProperties": True,
              "properties": {"expected_outputs": {"type": "array", "minItems": 1}},
              "conditional": []}
    _lib.validate({"expected_outputs": ["x"]}, schema, "t")
    try:
        _lib.validate({"expected_outputs": []}, schema, "t")
    except _lib.RLError:
        pass
    else:
        raise AssertionError("expected RLError for an array shorter than minItems")


def test_validate_array_items_checked_per_element():
    schema = {"required": [], "additionalProperties": True,
              "properties": {"evidence_runs": {"type": "array", "items": {"type": "string"}}},
              "conditional": []}
    _lib.validate({"evidence_runs": ["run-001", "run-002"]}, schema, "t")
    try:
        _lib.validate({"evidence_runs": ["run-001", 5]}, schema, "t")
    except _lib.RLError:
        pass
    else:
        raise AssertionError("expected RLError: item 5 is not a string")


def test_validate_conditional_require_single_when():
    schema = {
        "required": [], "additionalProperties": True,
        "properties": {"kind": {"type": "string"}, "scope": {"type": ["object", "null"]}},
        "conditional": [
            {"when": {"field": "kind", "op": "eq", "value": "grant"}, "require": ["scope"]}
        ],
    }
    _lib.validate({"kind": "decision"}, schema, "t")  # condition false: scope may be absent
    try:
        _lib.validate({"kind": "grant"}, schema, "t")
    except _lib.RLError:
        pass
    else:
        raise AssertionError("expected RLError: scope required when kind=grant")
    _lib.validate({"kind": "grant", "scope": {"desc": "x"}}, schema, "t")


def test_validate_conditional_require_when_is_array_of_two_conditions():
    schema = {
        "required": [], "additionalProperties": True,
        "properties": {
            "kind": {"type": "string"},
            "answered_by": {"type": ["string", "null"]},
            "grant_ref": {"type": ["string", "null"]},
        },
        "conditional": [
            {"when": [{"field": "kind", "op": "eq", "value": "r5-choice"},
                      {"field": "answered_by", "op": "neq", "value": "user"}],
             "require": ["grant_ref"]}
        ],
    }
    # Only one of the two conditions holds -> require not triggered.
    _lib.validate({"kind": "r5-choice", "answered_by": "user"}, schema, "t")
    # Both hold -> require triggered, grant_ref missing -> fail.
    try:
        _lib.validate({"kind": "r5-choice", "answered_by": "agent"}, schema, "t")
    except _lib.RLError:
        pass
    else:
        raise AssertionError("expected RLError: grant_ref required when both conditions hold")
    _lib.validate({"kind": "r5-choice", "answered_by": "agent", "grant_ref": "D001"}, schema, "t")


def test_validate_allow_null_gated_by_condition():
    schema = {
        "required": [], "additionalProperties": True,
        "properties": {
            "status": {"type": "string"},
            "metric_name": {"type": ["string", "null"]},
            "filter": {"type": ["string", "null"]},
        },
        "conditional": [
            {"when": {"field": "status", "op": "neq", "value": "ok"},
             "allow_null": ["metric_name"]}
        ],
    }
    # status=ok: the allow_null condition (status != ok) does not hold -> null rejected.
    try:
        _lib.validate({"status": "ok", "metric_name": None}, schema, "t")
    except _lib.RLError:
        pass
    else:
        raise AssertionError("expected RLError: metric_name must not be null when status=ok")
    # status=failed: the allow_null condition holds -> null permitted.
    _lib.validate({"status": "failed", "metric_name": None}, schema, "t")
    # filter is not named by any allow_null entry -> nullable unconditionally (its type says so).
    _lib.validate({"status": "ok", "metric_name": "acc", "filter": None}, schema, "t")


# ---------------------------------------------------------------------------
# 4. fail() message format
# ---------------------------------------------------------------------------


def test_fail_message_format_matches_spec():
    try:
        _lib.fail("runs", "metric_name", "must not be null when status=ok", None)
    except _lib.RLError as e:
        assert e.message == "runs.metric_name: must not be null when status=ok (got: None)"
    else:
        raise AssertionError("fail() must raise RLError")


def test_fail_without_value_omits_got_suffix():
    try:
        _lib.fail("blocked", "blocked_id", "row not found")
    except _lib.RLError as e:
        assert e.message == "blocked.blocked_id: row not found"
    else:
        raise AssertionError("fail() must raise RLError")


# ---------------------------------------------------------------------------
# 5. split_cmd / last_json_line
# ---------------------------------------------------------------------------


def test_split_cmd_rejects_pipes_and_newlines():
    for bad in ["echo a | grep a", "echo a\necho b"]:
        try:
            _lib.split_cmd(bad, "config", "registry_cmd")
        except _lib.RLError:
            pass
        else:
            raise AssertionError(f"expected RLError for: {bad!r}")
    assert _lib.split_cmd("python3 run.py show", "config", "registry_cmd") == \
        ["python3", "run.py", "show"]


def test_last_json_line_variants():
    assert _lib.last_json_line('{"a": 1}\n') == {"a": 1}
    assert _lib.last_json_line('junk line\n{"a": 1}\n\n') == {"a": 1}
    assert _lib.last_json_line("not json at all") is None
    assert _lib.last_json_line("[1, 2]") is None
    assert _lib.last_json_line("") is None


# ---------------------------------------------------------------------------
# 6. parse_frontmatter / spec_digest
# ---------------------------------------------------------------------------


def test_parse_frontmatter_splits_header_and_body():
    text = '---\nkey: 1\nname: "quoted"\n---\nbody line one.\nbody line two.\n'
    fields, body = _lib.parse_frontmatter(text)
    assert fields == {"key": 1, "name": "quoted"}
    assert body == "body line one.\nbody line two.\n"


def test_spec_digest_stable_across_header_edits_changes_with_body():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        p1 = root / "a.md"
        p2 = root / "b.md"
        p3 = root / "c.md"
        p1.write_text("---\nkey: 1\n---\nbody line one.\n", encoding="utf-8")
        p2.write_text("---\nkey: 2\n---\nbody line one.\n", encoding="utf-8")
        p3.write_text("---\nkey: 1\n---\nbody line one!\n", encoding="utf-8")

        assert _lib.spec_digest(p1) == _lib.spec_digest(p2)
        assert _lib.spec_digest(p1) != _lib.spec_digest(p3)


# ---------------------------------------------------------------------------
# 7. check_in_registry
# ---------------------------------------------------------------------------


def _write_config(root, data):
    (root / "research-loop.json").write_text(json.dumps(data), encoding="utf-8")


def test_check_in_registry():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        helpers.make_stub_registry(root, {
            "taskA": [sys.executable, "-c", "import sys; sys.exit(0)"],
        })
        registry_cmd = f"{sys.executable} {root / 'stub_registry.py'}"
        registry_query = f"{registry_cmd} --list"

        _write_config(root, {"registry_cmd": registry_cmd, "registry_query": registry_query})
        cfg = _lib.load_config(root)

        good_argv = _lib.split_cmd(registry_cmd, "t", "f") + ["taskA", "--flag"]
        task = _lib.check_in_registry(good_argv, cfg, ledger="launch_order", field="registry_task")
        assert task == "taskA"

        bad_prefix_argv = [sys.executable, "not-the-registry.py", "taskA"]
        try:
            _lib.check_in_registry(bad_prefix_argv, cfg, ledger="launch_order", field="registry_task")
        except _lib.RLError as e:
            assert e.message.startswith("launch_order.registry_task:")
        else:
            raise AssertionError("expected RLError: argv does not start with registry_cmd")

        unknown_task_argv = _lib.split_cmd(registry_cmd, "t", "f") + ["taskZ"]
        try:
            _lib.check_in_registry(unknown_task_argv, cfg, ledger="launch_order", field="registry_task")
        except _lib.RLError:
            pass
        else:
            raise AssertionError("expected RLError: taskZ is not in the registry")

        _write_config(root, {"registry_cmd": registry_cmd, "registry_query": None})
        cfg_no_query = _lib.load_config(root)
        argv = _lib.split_cmd(registry_cmd, "t", "f") + ["taskA"]
        try:
            _lib.check_in_registry(argv, cfg_no_query, ledger="launch_order", field="registry_task")
        except _lib.RLError as e:
            assert "registry_query" in e.message and "not wired" in e.message
        else:
            raise AssertionError("expected RLError: registry_query is null")

        _write_config(root, {"registry_cmd": None, "registry_query": registry_query})
        cfg_no_cmd = _lib.load_config(root)
        try:
            _lib.check_in_registry(["anything"], cfg_no_cmd, ledger="launch_order", field="registry_task")
        except _lib.RLError as e:
            assert "registry_cmd" in e.message and "not wired" in e.message
        else:
            raise AssertionError("expected RLError: registry_cmd is null")


# ---------------------------------------------------------------------------
# 8. locked
# ---------------------------------------------------------------------------

_LOCK_PROBE = (
    "import fcntl, sys\n"
    "fd = open(sys.argv[1], 'r+')\n"
    "try:\n"
    "    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
    "except BlockingIOError:\n"
    "    sys.exit(1)\n"
    "else:\n"
    "    sys.exit(0)\n"
)


def test_locked_blocks_another_process_and_releases_on_exit():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "ops" / "blocked.jsonl"
        lock_path = str(path) + ".lock"
        with _lib.locked(path):
            code = subprocess.run([sys.executable, "-c", _LOCK_PROBE, lock_path]).returncode
            assert code == 1, "another process must fail to acquire the lock while held"
        code_after = subprocess.run([sys.executable, "-c", _LOCK_PROBE, lock_path]).returncode
        assert code_after == 0, "the lock must be released once the context manager exits"


# ---------------------------------------------------------------------------
# 9. now_iso / today
# ---------------------------------------------------------------------------


def test_now_iso_reads_rl_fake_now():
    os.environ["RL_FAKE_NOW"] = "2026-08-13T12:00:00"
    try:
        assert _lib.now_iso() == "2026-08-13T12:00:00"
    finally:
        del os.environ["RL_FAKE_NOW"]


def test_today_reads_date_part_of_rl_fake_now():
    os.environ["RL_FAKE_NOW"] = "2026-08-13T09:30:00"
    try:
        assert _lib.today() == "2026-08-13"
    finally:
        del os.environ["RL_FAKE_NOW"]


# ---------------------------------------------------------------------------
# 10. make_sandbox wiring
# ---------------------------------------------------------------------------


def test_make_sandbox_wires_jsonl_rows_and_ledger_path():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(Path(tmp))
        cfg = _lib.load_config(root)

        blocked_path = cfg.ledger_path("blocked")
        assert blocked_path == root / "ops" / "blocked.jsonl"
        assert _lib.jsonl_rows(blocked_path) == []

        with _lib.locked(blocked_path):
            _lib.jsonl_append(blocked_path, helpers.make_blocked_row(blocked_id="B001"))
        rows = _lib.jsonl_rows(blocked_path)
        assert len(rows) == 1
        assert rows[0]["blocked_id"] == "B001"

        # template paths (artifact_dir / raw_data_roots) come back unresolved
        runmeta_path = cfg.ledger_path("runmeta")
        assert isinstance(runmeta_path, str) and "<artifact_dir>" in runmeta_path


# ---------------------------------------------------------------------------
# Config defaults (plan.md §C1)
# ---------------------------------------------------------------------------


def test_config_get_falls_back_to_plugin_defaults():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "research-loop.json").write_text(
            json.dumps({"registry_cmd": None}), encoding="utf-8"
        )
        cfg = _lib.load_config(root)
        assert cfg.get("runtime_factor") == 3
        assert cfg.get("roles") == {"inspector_model": "opus", "reader_model": "sonnet"}
        assert cfg.get("standing_authorization") == \
            {"max_expected_runtime_s": 3600, "resource": "compute"}
        assert cfg.get("inspection_policy") == "always"
        assert cfg.get("registry_cmd") is None  # no default for this key
        assert cfg.null_locked("registry_cmd") is True
        assert cfg.null_locked("runtime_factor") is True  # missing -> null-locked regardless of default


# ---------------------------------------------------------------------------
# plugin_root / load_tables / find_project_root / git_head
# ---------------------------------------------------------------------------


def test_plugin_root_and_load_tables():
    root = _lib.plugin_root()
    assert (root / "tables" / "rows.json").exists()
    tables = _lib.load_tables()
    assert set(tables.keys()) == {"ledgers", "rows", "writes", "config", "routes"}


def test_find_project_root_walks_up_and_returns_none_when_unwired():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "research-loop.json").write_text("{}", encoding="utf-8")
        nested = root / "a" / "b"
        nested.mkdir(parents=True)
        assert _lib.find_project_root(nested) == root

    with tempfile.TemporaryDirectory() as tmp2:
        assert _lib.find_project_root(Path(tmp2)) is None


def test_git_head_reports_no_git_and_dirty_suffix():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        assert _lib.git_head(root) == "no-git"

        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=root, check=True)
        (root / "f.txt").write_text("x", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True)

        head_clean = _lib.git_head(root)
        assert "-dirty" not in head_clean and len(head_clean) >= 7

        (root / "f.txt").write_text("y", encoding="utf-8")
        head_dirty = _lib.git_head(root)
        assert head_dirty.endswith("-dirty")
