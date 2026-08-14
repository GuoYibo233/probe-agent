"""Tests for ledger_cmds/runscmd.py (runs-append) and ledger_cmds/
principlescmd.py (parse_principles / principles-lint / render principles)
(issues/07-runs-principles.md)."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import _lib
import helpers
from ledger_cmds.principlescmd import parse_principles

# Criterion runs read "today" from _lib.today() (run_id's <YYYYMMDD>
# segment) -- pinned via RL_FAKE_NOW so run_id/last_tested assertions don't
# depend on the day the suite happens to run.
_FAKE_NOW = "2026-08-13T09:00:00"
_ENV = {"RL_FAKE_NOW": _FAKE_NOW}

_HEADER = (
    "# METHOD\n\n"
    "| principle_id | status | scope | applies_when | principle | rationale | criterion_cmd | last_tested |\n"
    "|---|---|---|---|---|---|---|---|\n"
)


def _row(pid, status, cmd="", applies_when="always", rationale="user said so 2026-08-13",
         last_tested="—"):
    return f"| {pid} | {status} | scope | {applies_when} | principle text | {rationale} | {cmd} | {last_tested} |\n"


def _write_method(root, rows) -> None:
    (Path(root) / "METHOD.md").write_text(_HEADER + "".join(rows), encoding="utf-8")


def _extend_registry(root) -> None:
    """Overwrite the sandbox's stub registry with the tasks this test file
    needs on top of helpers.make_sandbox()'s default check-p001/record."""
    helpers.make_stub_registry(root, {
        "check-p001": [
            sys.executable, "-c",
            "import json; print(json.dumps({'value': 3, 'evidence_path': 'ops/evidence.txt'}))",
        ],
        "check-fail": [
            sys.executable, "-c",
            "import sys; print('boom', file=sys.stderr); sys.exit(1)",
        ],
        "check-bad-tail": [sys.executable, "-c", "print('not json')"],
        "record": [sys.executable, "-c", "pass"],
    })


def _sandbox(tmp, git=False):
    root = helpers.make_git_sandbox(Path(tmp)) if git else helpers.make_sandbox(Path(tmp))
    cfg = _lib.load_config(root)
    registry_cmd = cfg.get("registry_cmd")
    _extend_registry(root)
    return root, cfg, registry_cmd


# ---------------------------------------------------------------------------
# parse_principles (shared function -- T09/T11 also import it)
# ---------------------------------------------------------------------------


def test_parse_principles_reads_the_fixed_eight_columns():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_method(root, [_row("P001", "【想法待定】", "",
                                   rationale="discussed 2026-08-13")])
        rows = parse_principles(root / "METHOD.md")
        assert len(rows) == 1
        assert rows[0]["principle_id"] == "P001"
        assert rows[0]["status"] == "【想法待定】"
        assert rows[0]["rationale"] == "discussed 2026-08-13"
        assert rows[0]["criterion_cmd"] == ""
        assert rows[0]["last_tested"] == "—"


def test_parse_principles_returns_empty_for_a_table_with_no_data_rows():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "METHOD.md").write_text(_HEADER, encoding="utf-8")
        assert parse_principles(root / "METHOD.md") == []


def test_parse_principles_rejects_a_missing_file():
    with tempfile.TemporaryDirectory() as tmp:
        missing = Path(tmp) / "no-such-METHOD.md"
        try:
            parse_principles(missing)
        except _lib.RLError as e:
            assert e.message == f"principles.file: not found (got: {str(missing)!r})"
        else:
            raise AssertionError("expected RLError for a missing principles file")


# ---------------------------------------------------------------------------
# A missing/misconfigured principles ledger file is a regular exit-2
# rejection at every CLI entry point that reads it, not an uncaught
# FileNotFoundError.
# ---------------------------------------------------------------------------


def test_principles_lint_rejects_missing_principles_file():
    with tempfile.TemporaryDirectory() as tmp:
        root, cfg, registry_cmd = _sandbox(tmp)
        (root / "METHOD.md").unlink()

        code, out, err = helpers.run_ledger(root, "principles-lint")
        assert code == 2
        assert "principles.file: not found" in err


def test_runs_append_rejects_missing_principles_file():
    with tempfile.TemporaryDirectory() as tmp:
        root, cfg, registry_cmd = _sandbox(tmp)
        (root / "METHOD.md").unlink()

        code, out, err = helpers.run_ledger(
            root, "runs-append", "--layer", "deploy", "--principle", "P001", env=_ENV,
        )
        assert code == 2
        assert "principles.file: not found" in err
        assert _lib.jsonl_rows(cfg.ledger_path("runs")) == []


def test_render_principles_rejects_missing_principles_file():
    with tempfile.TemporaryDirectory() as tmp:
        root, cfg, registry_cmd = _sandbox(tmp)
        (root / "METHOD.md").unlink()

        code, out, err = helpers.run_ledger(root, "render", "principles")
        assert code == 2
        assert "principles.file: not found" in err


# ---------------------------------------------------------------------------
# 1. --layer run is rejected
# ---------------------------------------------------------------------------


def test_runs_append_rejects_non_deploy_layer():
    with tempfile.TemporaryDirectory() as tmp:
        root, cfg, registry_cmd = _sandbox(tmp)
        _write_method(root, [_row("P001", "【现状】", f"{registry_cmd} check-p001")])

        code, out, err = helpers.run_ledger(
            root, "runs-append", "--layer", "run", "--principle", "P001", env=_ENV,
        )
        assert code == 2
        assert "runs.layer: runs-append only accepts --layer deploy" in err
        assert _lib.jsonl_rows(cfg.ledger_path("runs")) == []


def test_runs_append_rejects_when_registry_cmd_is_null():
    with tempfile.TemporaryDirectory() as tmp:
        root, cfg, registry_cmd = _sandbox(tmp)
        _write_method(root, [_row("P001", "【现状】", f"{registry_cmd} check-p001")])

        cfg_path = root / "research-loop.json"
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        data["registry_cmd"] = None
        cfg_path.write_text(json.dumps(data), encoding="utf-8")

        code, out, err = helpers.run_ledger(
            root, "runs-append", "--layer", "deploy", "--principle", "P001", env=_ENV,
        )
        assert code == 2
        assert "config.registry_cmd: not wired (null); cannot run criterion" in err
        assert _lib.jsonl_rows(cfg.ledger_path("runs")) == []


def test_runs_append_rejects_unknown_principle_id():
    with tempfile.TemporaryDirectory() as tmp:
        root, cfg, registry_cmd = _sandbox(tmp)
        _write_method(root, [_row("P001", "【现状】", f"{registry_cmd} check-p001")])

        code, out, err = helpers.run_ledger(
            root, "runs-append", "--layer", "deploy", "--principle", "P999", env=_ENV,
        )
        assert code == 2
        assert "principles.principle_id: not found (got: 'P999')" in err
        assert _lib.jsonl_rows(cfg.ledger_path("runs")) == []


# ---------------------------------------------------------------------------
# 2. failed / malformed criterion runs land no row
# ---------------------------------------------------------------------------


def test_runs_append_failed_criterion_appends_no_row_and_exits_2():
    with tempfile.TemporaryDirectory() as tmp:
        root, cfg, registry_cmd = _sandbox(tmp)
        _write_method(root, [_row("P001", "【现状】", f"{registry_cmd} check-fail")])

        code, out, err = helpers.run_ledger(
            root, "runs-append", "--layer", "deploy", "--principle", "P001", env=_ENV,
        )
        assert code == 2
        assert out.strip() == ""
        assert "boom" in err
        assert _lib.jsonl_rows(cfg.ledger_path("runs")) == []


def test_runs_append_bad_json_tail_appends_no_row_and_exits_2():
    with tempfile.TemporaryDirectory() as tmp:
        root, cfg, registry_cmd = _sandbox(tmp)
        _write_method(root, [_row("P001", "【现状】", f"{registry_cmd} check-bad-tail")])

        code, out, err = helpers.run_ledger(
            root, "runs-append", "--layer", "deploy", "--principle", "P001", env=_ENV,
        )
        assert code == 2
        assert out.strip() == ""
        assert _lib.jsonl_rows(cfg.ledger_path("runs")) == []


# ---------------------------------------------------------------------------
# 3. success: row matches schema, run_id sequence increments across calls
# ---------------------------------------------------------------------------


def test_runs_append_success_appends_valid_row_and_increments_sequence():
    with tempfile.TemporaryDirectory() as tmp:
        root, cfg, registry_cmd = _sandbox(tmp)
        _write_method(root, [_row("P001", "【现状】", f"{registry_cmd} check-p001")])

        code, out, err = helpers.run_ledger(
            root, "runs-append", "--layer", "deploy", "--principle", "P001", env=_ENV,
        )
        assert code == 0, (out, err)
        row = json.loads(out.strip())

        schema = _lib.load_schema("runs.criterion")
        _lib.validate(row, schema, schema["ledger"])  # must not raise

        assert row["status"] == "ok"
        assert row["principle_id"] == "P001"
        assert row["value"] == 3
        assert row["output_dir"] == "ops/evidence.txt"
        assert row["run_id"] == "chk-P001-20260813-1"

        runs_path = cfg.ledger_path("runs")
        rows = _lib.jsonl_rows(runs_path)
        assert rows == [row]

        code2, out2, err2 = helpers.run_ledger(
            root, "runs-append", "--layer", "deploy", "--principle", "P001", env=_ENV,
        )
        assert code2 == 0, (out2, err2)
        row2 = json.loads(out2.strip())
        assert row2["run_id"] == "chk-P001-20260813-2"
        assert _lib.jsonl_rows(runs_path) == [row, row2]


# ---------------------------------------------------------------------------
# 4. commit field: no-git outside a repo, -dirty on a dirty tree
# ---------------------------------------------------------------------------


def test_runs_append_commit_field_reports_no_git_outside_a_repo():
    with tempfile.TemporaryDirectory() as tmp:
        root, cfg, registry_cmd = _sandbox(tmp, git=False)
        _write_method(root, [_row("P001", "【现状】", f"{registry_cmd} check-p001")])

        code, out, err = helpers.run_ledger(
            root, "runs-append", "--layer", "deploy", "--principle", "P001", env=_ENV,
        )
        assert code == 0, (out, err)
        assert json.loads(out.strip())["commit"] == "no-git"


def test_runs_append_commit_field_reports_dirty_suffix_on_a_dirty_git_tree():
    with tempfile.TemporaryDirectory() as tmp:
        # make_git_sandbox commits everything; _extend_registry/_write_method
        # (called after that commit, inside _sandbox/below) leave the tree dirty.
        root, cfg, registry_cmd = _sandbox(tmp, git=True)
        _write_method(root, [_row("P001", "【现状】", f"{registry_cmd} check-p001")])

        code, out, err = helpers.run_ledger(
            root, "runs-append", "--layer", "deploy", "--principle", "P001", env=_ENV,
        )
        assert code == 0, (out, err)
        assert json.loads(out.strip())["commit"].endswith("-dirty")


# ---------------------------------------------------------------------------
# 5. principles-lint
# ---------------------------------------------------------------------------


def test_principles_lint_passes_a_valid_table():
    with tempfile.TemporaryDirectory() as tmp:
        root, cfg, registry_cmd = _sandbox(tmp)
        _write_method(root, [
            _row("P001", "【现状】", f"{registry_cmd} check-p001"),
            _row("P002", "【想法待定】", ""),
        ])
        code, out, err = helpers.run_ledger(root, "principles-lint")
        assert code == 0, err


def test_principles_lint_reports_malformed_row_by_line_number():
    # F6 (sdd/final-review.md): parse_principles's own tolerant parsing
    # silently drops a row whose cell count doesn't match the header --
    # principles-lint is R1's one machine-verified gate, so a row that
    # can't even be counted must be reported, not made to look like it
    # never existed. parse_principles's parsing behavior itself is
    # unchanged (still silently dropped from the returned rows list); only
    # principles-lint's own reporting changes.
    with tempfile.TemporaryDirectory() as tmp:
        root, cfg, registry_cmd = _sandbox(tmp)
        _write_method(root, [
            _row("P001", "【想法待定】", ""),
            "| P002 | 【想法待定】 | scope | always | text | reason |\n",  # 6 cells, header wants 8
        ])
        code, out, err = helpers.run_ledger(root, "principles-lint")
        assert code == 1
        assert "principles.6.format: malformed row (expected 8 cells, got 6)" in err
        # the malformed row is absent from every other check, not
        # double-reported under some other field path.
        assert "P002" not in err


def test_principles_lint_reports_duplicate_principle_id():
    with tempfile.TemporaryDirectory() as tmp:
        root, cfg, registry_cmd = _sandbox(tmp)
        _write_method(root, [
            _row("P001", "【想法待定】", ""),
            _row("P001", "【想法待定】", ""),
        ])
        code, out, err = helpers.run_ledger(root, "principles-lint")
        assert code == 1
        assert "principles.P001.principle_id: duplicate principle_id" in err


def test_principles_lint_reports_empty_rationale():
    with tempfile.TemporaryDirectory() as tmp:
        root, cfg, registry_cmd = _sandbox(tmp)
        _write_method(root, [_row("P001", "【想法待定】", "", rationale="")])
        code, out, err = helpers.run_ledger(root, "principles-lint")
        assert code == 1
        assert "principles.P001.rationale: must not be empty" in err


def test_principles_lint_reports_empty_applies_when():
    with tempfile.TemporaryDirectory() as tmp:
        root, cfg, registry_cmd = _sandbox(tmp)
        _write_method(root, [_row("P001", "【想法待定】", "", applies_when="")])
        code, out, err = helpers.run_ledger(root, "principles-lint")
        assert code == 1
        assert "principles.P001.applies_when: must not be empty" in err


def test_principles_lint_reports_empty_criterion_cmd_for_testable_status():
    with tempfile.TemporaryDirectory() as tmp:
        root, cfg, registry_cmd = _sandbox(tmp)
        _write_method(root, [_row("P001", "【现状】", "")])
        code, out, err = helpers.run_ledger(root, "principles-lint")
        assert code == 1
        assert "principles.P001.criterion_cmd: not wired" in err


def test_principles_lint_reports_criterion_cmd_not_in_registry():
    with tempfile.TemporaryDirectory() as tmp:
        root, cfg, registry_cmd = _sandbox(tmp)
        _write_method(root, [_row("P001", "【现状】", f"{registry_cmd} not-a-real-task")])
        code, out, err = helpers.run_ledger(root, "principles-lint")
        assert code == 1
        assert "principles.P001.criterion_cmd: task is not in the registry" in err


def test_principles_lint_reports_criterion_cmd_with_pipe():
    with tempfile.TemporaryDirectory() as tmp:
        root, cfg, registry_cmd = _sandbox(tmp)
        # "\|" survives the table parser as an escaped literal '|' -- the
        # criterion_cmd cell ends up containing a real pipe character for
        # the lint check to catch (an un-escaped '|' would just corrupt the
        # row's cell count instead).
        _write_method(root, [
            _row("P001", "【现状】", f"{registry_cmd} check-p001 \\| grep x")
        ])
        code, out, err = helpers.run_ledger(root, "principles-lint")
        assert code == 1
        assert "principles.P001.criterion_cmd: must not contain pipes or newlines" in err


def test_principles_lint_reports_registry_query_not_wired():
    with tempfile.TemporaryDirectory() as tmp:
        root, cfg, registry_cmd = _sandbox(tmp)
        _write_method(root, [_row("P001", "【现状】", f"{registry_cmd} check-p001")])

        cfg_path = root / "research-loop.json"
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        data["registry_query"] = None
        cfg_path.write_text(json.dumps(data), encoding="utf-8")

        code, out, err = helpers.run_ledger(root, "principles-lint")
        assert code == 1
        assert "principles.P001.criterion_cmd:" in err
        assert "not wired" in err


def test_principles_lint_dash_style_status_allows_empty_cmd():
    with tempfile.TemporaryDirectory() as tmp:
        root, cfg, registry_cmd = _sandbox(tmp)
        _write_method(root, [_row("P001", "【想法待定】", "")])
        code, out, err = helpers.run_ledger(root, "principles-lint")
        assert code == 0, err


# ---------------------------------------------------------------------------
# 6. render principles
# ---------------------------------------------------------------------------


def test_render_principles_backfills_last_tested_and_preserves_other_bytes():
    with tempfile.TemporaryDirectory() as tmp:
        root, cfg, registry_cmd = _sandbox(tmp)
        _write_method(root, [
            _row("P001", "【现状】", f"{registry_cmd} check-p001"),
            _row("P002", "【想法待定】", ""),
        ])
        before_lines = (root / "METHOD.md").read_text(encoding="utf-8").splitlines(keepends=True)

        code, out, err = helpers.run_ledger(
            root, "runs-append", "--layer", "deploy", "--principle", "P001", env=_ENV,
        )
        assert code == 0, (out, err)

        code, out, err = helpers.run_ledger(root, "render", "principles")
        assert code == 0, (out, err)

        after_lines = (root / "METHOD.md").read_text(encoding="utf-8").splitlines(keepends=True)
        assert len(before_lines) == len(after_lines)

        i_p001 = [i for i, l in enumerate(before_lines) if "| P001 |" in l]
        i_p002 = [i for i, l in enumerate(before_lines) if "| P002 |" in l]
        assert len(i_p001) == 1 and len(i_p002) == 1
        i_p001, i_p002 = i_p001[0], i_p002[0]

        assert before_lines[i_p001] != after_lines[i_p001]
        # every cell except the trailing (last_tested) one is untouched
        assert before_lines[i_p001].rsplit("|", 2)[0] == after_lines[i_p001].rsplit("|", 2)[0]
        assert "ok (3) 2026-08-13" in after_lines[i_p001]

        # P002 never had a criterion run -- stays "—", line unchanged
        assert before_lines[i_p002] == after_lines[i_p002]

        # every other byte in the file (header, separator) is untouched
        for i in range(len(before_lines)):
            if i != i_p001:
                assert before_lines[i] == after_lines[i], i

        rendered_rows = parse_principles(root / "METHOD.md")
        p002 = next(r for r in rendered_rows if r["principle_id"] == "P002")
        assert p002["last_tested"] == "—"


def test_render_principles_no_runs_row_gives_em_dash():
    with tempfile.TemporaryDirectory() as tmp:
        root, cfg, registry_cmd = _sandbox(tmp)
        _write_method(root, [_row("P001", "【现状】", f"{registry_cmd} check-p001",
                                   last_tested="stale value")])
        code, out, err = helpers.run_ledger(root, "render", "principles")
        assert code == 0, (out, err)
        rows = parse_principles(root / "METHOD.md")
        assert rows[0]["last_tested"] == "—"
