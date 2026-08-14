"""Tests for scripts/doctor.py (issues/14-doctor.md).

Every fixture is hand-written straight to disk (helpers.write_jsonl / row
factories, launch orders as raw JSON, METHOD.md as raw text) the same way
test_trace_check.py and test_oversight.py build theirs -- doctor.py only
depends on T04/T07/T09/T11/T13, and this suite must not depend on any
other ticket's CLI write paths to build test data.
"""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
from pathlib import Path

import _lib
import helpers


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _sandbox(tmp) -> Path:
    return helpers.make_sandbox(Path(tmp))


def _write_clean_method(root: Path) -> None:
    """helpers.METHOD_MD's own criterion_cmd is a bare "python3
    stub_registry.py check-p001" -- it exercises T07's column parsing, not
    a real pass through principles-lint's registry check (see
    test_runs_principles.py's own _write_method, which always rewrites this
    same way before asserting a clean principles-lint run). Doctor's own
    "clean sandbox" test needs a principles table that actually resolves
    against the sandbox's real (absolute, sys.executable-based) registry_cmd."""
    registry_cmd = _lib.load_config(root).get("registry_cmd")
    (root / "METHOD.md").write_text(
        "# METHOD\n\n"
        "| principle_id | status | scope | applies_when | principle | rationale | "
        "criterion_cmd | last_tested |\n"
        "|---|---|---|---|---|---|---|---|\n"
        f"| P001 | 【现状】 | data | always | seeds are fixed | user said so 2026-08-13 | "
        f"{registry_cmd} check-p001 | — |\n",
        encoding="utf-8",
    )


def _dump_launch_order(root: Path, order: dict) -> None:
    directory = root / "ops" / "launch_orders"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{order['run_id']}.json").write_text(
        json.dumps(order, ensure_ascii=False), encoding="utf-8",
    )


def _snapshot(root: Path) -> dict:
    """{relative path: sha256} for every regular file under root -- used to
    prove a doctor run touched nothing on disk."""
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _run_doctor(root: Path, *extra_args):
    return helpers.run_script(root, "doctor.py", "--project-root", str(root), *extra_args)


# ---------------------------------------------------------------------------
# 1. clean sandbox
# ---------------------------------------------------------------------------


def test_doctor_clean_sandbox_all_sections_present_and_zero_findings():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        _write_clean_method(root)

        code, out, err = _run_doctor(root)

        assert code == 0
        for name in [
            "config", "trace", "evidence", "principles", "regression",
            "caps", "archives", "worktrees", "half-state", "workplan",
        ]:
            assert f"== {name} ==" in out
        assert "doctor: 0 findings across 10 sections" in out


# ---------------------------------------------------------------------------
# 2. three half-state fixtures -- each reported, sandbox left untouched
# ---------------------------------------------------------------------------


def test_doctor_orphan_decision_is_reported_and_sandbox_is_untouched():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        blocked_row = helpers.make_blocked_row(
            blocked_id="B001", kind="r5-choice", to_layer="deploy", status="open",
            where="which approach", options=["A", "B"],
        )
        decision_row = helpers.make_decision_row(
            decision_id="D001", blocked_ref="B001", status="decided",
        )
        helpers.write_jsonl(root / "ops" / "blocked.jsonl", [blocked_row])
        helpers.write_jsonl(root / "ops" / "decisions.jsonl", [decision_row])
        before = _snapshot(root)

        code, out, err = _run_doctor(root)
        after = _snapshot(root)

        assert code == 0
        assert after == before
        assert "orphan decision" in out
        assert "re-run: ledger.py blocked answer B001 ..." in out


def test_doctor_interrupted_withdrawal_is_reported_and_sandbox_is_untouched():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        withdrawn_row = helpers.make_blocked_row(
            blocked_id="B001", kind="r5-choice", to_layer="deploy", status="withdrawn",
            where="which approach", options=["A", "B"], decision_ref="D001",
            answer="chose A\n[withdrawn by user: changed my mind]",
            answered_at=_lib.now_iso(), answered_by="deploy",
        )
        reopened_row = helpers.make_blocked_row(
            blocked_id="B002", kind="r5-choice", to_layer="deploy", status="open",
            where="which approach", options=["A", "B"], ref="B001",
        )
        decision_row = helpers.make_decision_row(
            decision_id="D001", blocked_ref="B001", status="decided",  # should be withdrawn
        )
        helpers.write_jsonl(root / "ops" / "blocked.jsonl", [withdrawn_row, reopened_row])
        helpers.write_jsonl(root / "ops" / "decisions.jsonl", [decision_row])
        before = _snapshot(root)

        code, out, err = _run_doctor(root)
        after = _snapshot(root)

        assert code == 0
        assert after == before
        assert "interrupted withdrawal" in out
        assert "re-run: ledger.py blocked withdraw B001 --reason ..." in out


def test_doctor_reopened_row_moving_past_open_is_not_reported_as_interrupted_again():
    # F3 (sdd/final-review.md): once B001's withdrawal mechanically reopened
    # B002, B002 living out its own ordinary lifecycle (getting answered)
    # must not make doctor think the reopen never happened and suggest
    # re-running the withdraw -- that re-run would mechanically open a
    # *third* row for a question the user already has two live threads on.
    # The old status=open-only "reopened" criterion did exactly that the
    # moment B002 stopped being open; requiring only that a ref=B001 row
    # exist (regardless of its current status) fixes it.
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        withdrawn_row = helpers.make_blocked_row(
            blocked_id="B001", kind="r5-choice", to_layer="deploy", status="withdrawn",
            where="which approach", options=["A", "B"], decision_ref="D001",
            answer="chose A\n[withdrawn by user: changed my mind]",
            answered_at=_lib.now_iso(), answered_by="deploy",
        )
        reopened_and_answered_row = helpers.make_blocked_row(
            blocked_id="B002", kind="r5-choice", to_layer="deploy", status="answered",
            where="which approach", options=["A", "B"], ref="B001",
            answer="chose B", answered_at=_lib.now_iso(), answered_by="deploy",
            decision_ref="D002",
        )
        decision_row_withdrawn = helpers.make_decision_row(
            decision_id="D001", blocked_ref="B001", status="withdrawn",
            withdrawn_by="user", withdrawn_reason="changed my mind",
        )
        decision_row_new = helpers.make_decision_row(decision_id="D002", blocked_ref="B002")
        helpers.write_jsonl(
            root / "ops" / "blocked.jsonl", [withdrawn_row, reopened_and_answered_row],
        )
        helpers.write_jsonl(
            root / "ops" / "decisions.jsonl", [decision_row_withdrawn, decision_row_new],
        )

        code, out, err = _run_doctor(root)

        assert code == 0
        assert "interrupted withdrawal" not in out


def test_doctor_affects_mismatch_is_reported_and_sandbox_is_untouched():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        decision_row = helpers.make_decision_row(decision_id="D001", affects=[])
        order = helpers.make_launch_order(run_id="run-001", decision_refs=["D001"])
        helpers.write_jsonl(root / "ops" / "decisions.jsonl", [decision_row])
        _dump_launch_order(root, order)
        before = _snapshot(root)

        code, out, err = _run_doctor(root)
        after = _snapshot(root)

        assert code == 0
        assert after == before
        assert "affects mismatch" in out
        expected_fix = (
            f"re-run: ledger.py launch-order --layer deploy "
            f"--file {root / 'ops' / 'launch_orders' / 'run-001.json'}"
        )
        assert expected_fix in out


# ---------------------------------------------------------------------------
# 3. one check goes red, doctor still finishes every other section, exit 0
# ---------------------------------------------------------------------------


def test_doctor_principles_violation_is_red_but_doctor_completes_and_exits_zero():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        bad_method = (
            "# METHOD\n\n"
            "| principle_id | status | scope | applies_when | principle | rationale | "
            "criterion_cmd | last_tested |\n"
            "|---|---|---|---|---|---|---|---|\n"
            "| P001 | 【想法待定】 | data | always | seeds fixed | dup one |  | — |\n"
            "| P001 | 【想法待定】 | data | always | seeds fixed again | dup two |  | — |\n"
        )
        (root / "METHOD.md").write_text(bad_method, encoding="utf-8")

        code, out, err = _run_doctor(root)

        assert code == 0
        assert "== principles ==" in out
        assert "duplicate principle_id" in out
        # every other section still ran and the summary line still appears
        assert re.search(r"doctor: \d+ findings across 10 sections", out)
        for name in ["config", "trace", "evidence", "regression", "caps",
                     "archives", "worktrees", "half-state", "workplan"]:
            assert f"== {name} ==" in out


def test_doctor_a_genuinely_crashing_section_is_caught_and_the_rest_still_runs():
    # A malformed ledger_caps value (bypassing config-check, which would
    # otherwise reject it) makes _section_caps's own dict .get() raise --
    # this is the "section failed" path (spec.md §4: single check crashing
    # must not take the rest of the run down with it), distinct from a
    # subcommand simply exiting non-zero with an ordinary finding (the
    # principles test above).
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        cfg_path = root / "research-loop.json"
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        data["ledger_caps"] = "not-a-dict"
        cfg_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        code, out, err = _run_doctor(root)

        assert code == 0
        assert "== caps ==" in out
        assert "section failed:" in out
        for name in ["config", "trace", "evidence", "principles", "regression",
                     "archives", "worktrees", "half-state", "workplan"]:
            assert f"== {name} ==" in out


# ---------------------------------------------------------------------------
# 4. caps: a ledger over its cap is a finding
# ---------------------------------------------------------------------------


def test_doctor_caps_section_flags_ledger_at_or_over_cap():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        rows = [helpers.make_blocked_row(blocked_id=f"B{i:03d}") for i in range(1, 502)]
        helpers.write_jsonl(root / "ops" / "blocked.jsonl", rows)

        code, out, err = _run_doctor(root)

        assert code == 0
        assert "== caps ==" in out
        assert "caps.blocked: 501 rows >= cap 500" in out
        assert "archive lands in v1.1; trim manually or raise the cap" in out


# ---------------------------------------------------------------------------
# 5. --out matches stdout
# ---------------------------------------------------------------------------


def test_doctor_out_file_matches_stdout():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        out_path = root / "doctor-report.txt"

        code, out, err = _run_doctor(root, "--out", str(out_path))

        assert code == 0
        assert out_path.exists()
        assert out_path.read_text(encoding="utf-8") == out


# ---------------------------------------------------------------------------
# 6. exit is unconditionally 0 when there's simply no project to find by
#    walking up from cwd -- doctor is advisory (issues/14-doctor.md: "exit
#    恒 0"). One case does exit non-zero: an explicit --project-root that
#    points at a directory with no research-loop.json at all (F2, sdd/
#    final-review.md) -- that's not "nothing to inspect", it's a caller
#    mistake that would otherwise make every section below silently read an
#    empty, falsely-clean project.
# ---------------------------------------------------------------------------


def test_doctor_unwired_project_still_exits_zero():
    with tempfile.TemporaryDirectory() as tmp:
        unwired_root = Path(tmp)  # no research-loop.json anywhere above this

        code, out, err = helpers.run_script(unwired_root, "doctor.py")

        assert code == 0
        assert "project not wired" in err
        assert out == ""


def test_doctor_project_root_explicit_wrong_path_exits_2():
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as tmp_wrong:
        root = _sandbox(tmp)
        _write_clean_method(root)
        wrong_root = Path(tmp_wrong)  # exists on disk, but no research-loop.json

        code, out, err = helpers.run_script(root, "doctor.py", "--project-root", str(wrong_root))

        assert code == 2, (out, err)
        assert "research-loop.json" in err
        assert out == ""
