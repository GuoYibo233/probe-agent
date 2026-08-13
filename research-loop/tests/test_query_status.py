"""Tests for ledger_cmds/querycmd.py (query LEDGER, render blocked) and
ledger_cmds/statuscmd.py (status --layer L) -- issues/09-query-status.md.

Fixtures write ledgers directly with helpers' row factories (no CLI write
paths -- the ticket's own instruction: this ticket must not depend on
sibling tickets' write commands to build its test data). Comment headers
below map each test back to the ticket's own numbered "测试" list; a few
extra tests beyond that list cover other literal "要求" bullets (the
json-single-file rejection, render blocked's grouping, and the
approved_specs_in_flight/open_issues derivations) that the ticket states as
requirements without giving them their own list entry.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import _lib
import helpers


def _sandbox(tmp) -> Path:
    return helpers.make_sandbox(Path(tmp))


def _write_launch_order(root, **over) -> Path:
    row = helpers.make_launch_order(**over)
    path = Path(root) / "ops" / "launch_orders" / f"{row['run_id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _write_jobs(root, data) -> Path:
    path = Path(root) / "ops" / "jobs.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _write_batch_report(root, filename, *, batch_id, run_ids, inspection_report="") -> Path:
    fields = {
        "batch_id": batch_id,
        "spec_items": [],
        "run_ids": run_ids,
        "date": _lib.today(),
        "how_to_read": "see RESULTS.md",
        "inspection_report": inspection_report,
        "rejections": [],
    }
    lines = ["---"]
    for key, value in fields.items():
        lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    lines.append("---")
    lines.append("")
    lines.append(f"# batch report {batch_id}")
    lines.append("")
    path = Path(root) / "plans" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_spec(root, feature, *, approved_by="user") -> Path:
    fields = {
        "spec_version": 1,
        "approved_by": approved_by,
        "approved_date": _lib.today(),
        "approved_digest": "deadbeef",
        "withdrawals": [],
    }
    lines = ["---"]
    for key, value in fields.items():
        lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    lines.append("---")
    lines.append("")
    lines.append(f"# spec for {feature}")
    lines.append("")
    path = Path(root) / ".scratch" / feature / "spec.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_issue(root, feature, name, *, status) -> Path:
    path = Path(root) / ".scratch" / feature / "issues" / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {name}\n\nStatus: {status}\n", encoding="utf-8")
    return path


def _snapshot(root) -> dict:
    root = Path(root)
    out = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


# ---------------------------------------------------------------------------
# 1. query story: default view = active only; --all-rows includes retired
# ---------------------------------------------------------------------------


def test_query_story_default_active_all_rows_includes_retired():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        cfg = _lib.load_config(root)
        active = helpers.make_story_row(claim_id="S001", status="active")
        retired = helpers.make_story_row(
            claim_id="S002", status="retired",
            retired_reason="superseded", retired_date="2026-08-01", retired_by="user",
        )
        helpers.write_jsonl(cfg.ledger_path("story"), [active, retired])

        code, out, err = helpers.run_ledger(root, "query", "story")
        assert code == 0, err
        assert [r["claim_id"] for r in json.loads(out)] == ["S001"]

        code, out, err = helpers.run_ledger(root, "query", "story", "--all-rows")
        assert code == 0, err
        assert sorted(r["claim_id"] for r in json.loads(out)) == ["S001", "S002"]


# ---------------------------------------------------------------------------
# 2. query runs: no filter rejected (--all-rows does not exempt this);
#    --batch/--run/--metric/--since each filter correctly
# ---------------------------------------------------------------------------


def test_query_runs_requires_filter_and_all_rows_does_not_exempt():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        cfg = _lib.load_config(root)
        row = helpers.make_runs_row_normal(run_id="run-a", batch_id="B1")
        helpers.write_jsonl(cfg.ledger_path("runs"), [row])

        code, out, err = helpers.run_ledger(root, "query", "runs")
        assert code == 2
        assert err.strip() == (
            "query.runs: refuse to return the full table; add a filter "
            "(--batch/--run/--since/--metric) or read the rendered product"
        )

        code, out, err = helpers.run_ledger(root, "query", "runs", "--all-rows")
        assert code == 2, "--all-rows must not exempt runs from the filter requirement"
        assert err.strip() == (
            "query.runs: refuse to return the full table; add a filter "
            "(--batch/--run/--since/--metric) or read the rendered product"
        )


def test_query_runs_batch_run_metric_since_filters():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        cfg = _lib.load_config(root)
        row_a = helpers.make_runs_row_normal(
            run_id="run-a", batch_id="B1", metric_name="acc", recorded_at="2026-08-10T00:00:00"
        )
        row_b = helpers.make_runs_row_normal(
            run_id="run-b", batch_id="B2", metric_name="loss", recorded_at="2026-08-12T00:00:00"
        )
        helpers.write_jsonl(cfg.ledger_path("runs"), [row_a, row_b])

        code, out, err = helpers.run_ledger(root, "query", "runs", "--run", "run-a")
        assert code == 0, err
        assert [r["run_id"] for r in json.loads(out)] == ["run-a"]

        code, out, err = helpers.run_ledger(root, "query", "runs", "--batch", "B2")
        assert code == 0, err
        assert [r["run_id"] for r in json.loads(out)] == ["run-b"]

        code, out, err = helpers.run_ledger(root, "query", "runs", "--metric", "acc")
        assert code == 0, err
        assert [r["run_id"] for r in json.loads(out)] == ["run-a"]

        code, out, err = helpers.run_ledger(root, "query", "runs", "--since", "2026-08-11T00:00:00")
        assert code == 0, err
        assert [r["run_id"] for r in json.loads(out)] == ["run-b"]


# ---------------------------------------------------------------------------
# 3. query decisions: default view = active_grants ∪ referenced rows;
#    an expired grant referenced by blocked.grant_ref is kept
# ---------------------------------------------------------------------------


def test_query_decisions_default_view_referenced_expired_grant_kept():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        cfg = _lib.load_config(root)

        grant_active = helpers.make_grant_row(
            decision_id="D001", scope={"desc": "x", "path_globs": ["ops/**"], "expires_at": None}
        )
        grant_expired = helpers.make_grant_row(
            decision_id="D002",
            scope={"desc": "y", "path_globs": ["ops/**"], "expires_at": "2000-01-01T00:00:00"},
        )
        grant_expired_referenced = helpers.make_grant_row(
            decision_id="D003",
            scope={"desc": "z", "path_globs": ["ops/**"], "expires_at": "2000-01-01T00:00:00"},
        )
        decision_unreferenced = helpers.make_decision_row(decision_id="D004")
        helpers.write_jsonl(
            cfg.ledger_path("decisions"),
            [grant_active, grant_expired, grant_expired_referenced, decision_unreferenced],
        )

        blocked_row = helpers.make_blocked_row(
            blocked_id="B001", status="answered", to_layer="deploy", kind="r5-choice",
            where="w", options=["a", "b"],
            answer="chose a", answered_at=_lib.now_iso(), answered_by="deploy",
            grant_ref="D003",
        )
        helpers.write_jsonl(cfg.ledger_path("blocked"), [blocked_row])

        code, out, err = helpers.run_ledger(root, "query", "decisions")
        assert code == 0, err
        assert sorted(r["decision_id"] for r in json.loads(out)) == ["D001", "D003"]

        code, out, err = helpers.run_ledger(root, "query", "decisions", "--all-rows")
        assert code == 0, err
        assert sorted(r["decision_id"] for r in json.loads(out)) == ["D001", "D002", "D003", "D004"]


# ---------------------------------------------------------------------------
# 4. query feedback: reviewed suggestion excluded, unreviewed kept, review
#    rows never in the default view
# ---------------------------------------------------------------------------


def test_query_feedback_pending_excludes_reviewed_and_review_rows():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        cfg = _lib.load_config(root)
        pending = helpers.make_suggestion_row(fb_id="F001")
        reviewed = helpers.make_suggestion_row(fb_id="F002", problem="another issue")
        review = {
            "fb_id": "F003", "kind": "review", "ref": "F002", "layer": "user",
            "verdict": "accepted", "note": None, "date": _lib.today(), "schema_version": 1,
        }
        helpers.write_jsonl(cfg.ledger_path("feedback"), [pending, reviewed, review])

        code, out, err = helpers.run_ledger(root, "query", "feedback")
        assert code == 0, err
        assert [r["fb_id"] for r in json.loads(out)] == ["F001"]

        code, out, err = helpers.run_ledger(root, "query", "feedback", "--all-rows")
        assert code == 0, err
        assert sorted(r["fb_id"] for r in json.loads(out)) == ["F001", "F002", "F003"]


# ---------------------------------------------------------------------------
# 5. query principles (md ledger) rejected
# ---------------------------------------------------------------------------


def test_query_principles_md_ledger_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        code, out, err = helpers.run_ledger(root, "query", "principles")
        assert code == 2
        assert err.strip() == "query.principles: md ledger, read the file directly (md-full)"


# ---------------------------------------------------------------------------
# 6. --include-archive: a row that only exists in runs.archive.jsonl is
#    invisible by default, visible with --include-archive
# ---------------------------------------------------------------------------


def test_query_runs_include_archive_reads_archive_file():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        cfg = _lib.load_config(root)
        runs_path = Path(cfg.ledger_path("runs"))
        archive_path = runs_path.with_name(f"{runs_path.stem}.archive{runs_path.suffix}")
        archived_row = helpers.make_runs_row_normal(run_id="run-archived")
        helpers.write_jsonl(archive_path, [archived_row])

        code, out, err = helpers.run_ledger(root, "query", "runs", "--run", "run-archived")
        assert code == 0, err
        assert json.loads(out) == []

        code, out, err = helpers.run_ledger(
            root, "query", "runs", "--run", "run-archived", "--include-archive"
        )
        assert code == 0, err
        assert [r["run_id"] for r in json.loads(out)] == ["run-archived"]


# ---------------------------------------------------------------------------
# 7. status: the four breakpoint fixtures each land their field
# ---------------------------------------------------------------------------


def test_status_four_breakpoints_land_correct_fields():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        cfg = _lib.load_config(root)

        # launch order written, never picked up by a job -> pending_launch_orders
        _write_launch_order(
            root, run_id="run-pending", batch_id="batch-x",
            created_at=_lib.now_iso(), expected_runtime_s=600,
        )
        # a job that finished with no matching runs.jsonl row -> unrecorded_runs
        # (plus one running job, to check running_runs while we're here)
        _write_jobs(root, {
            "run-done-no-row": {"state": "done"},
            "run-running": {"state": "running"},
        })
        # a runs row whose batch has no report yet -> batches_pending_report
        runs_row = helpers.make_runs_row_normal(run_id="run-with-report", batch_id="batch-y")
        helpers.write_jsonl(cfg.ledger_path("runs"), [runs_row])
        # a batch report with an empty inspection_report -> batches_pending_inspection
        _write_batch_report(root, "batch-z.md", batch_id="batch-z", run_ids=[], inspection_report="")

        code, out, err = helpers.run_ledger(root, "status", "--layer", "deploy")
        assert code == 0, err
        view = json.loads(out)

        assert {
            "run_id": "run-pending", "path": "ops/launch_orders/run-pending.json",
        } in view["pending_launch_orders"]
        assert view["unrecorded_runs"] == ["run-done-no-row"]
        assert view["running_runs"] == ["run-running"]
        assert "batch-y" in view["batches_pending_report"]
        assert {
            "batch_id": "batch-z", "path": "plans/batch-z.md",
        } in view["batches_pending_inspection"]
        assert view["layer"] == "deploy"
        assert view["schema_version"] == 1


# ---------------------------------------------------------------------------
# 8. status inconsistencies: a batch report referencing a missing run_id
#    only lands in inconsistencies[]; other fields are unaffected
# ---------------------------------------------------------------------------


def test_status_inconsistency_report_run_missing_other_fields_unaffected():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        _write_batch_report(
            root, "batch-report.md", batch_id="batch-q",
            run_ids=["run-ghost"], inspection_report="reports/already-done.md",
        )

        code, out, err = helpers.run_ledger(root, "status", "--layer", "deploy")
        assert code == 0, err
        view = json.loads(out)

        assert {
            "code": "report-run-missing", "ref": "run-ghost", "source": "plans/batch-report.md",
        } in view["inconsistencies"]
        # inspection_report was non-empty -- the report must not also show up
        # as pending inspection just because one of its run_ids is dangling.
        assert view["batches_pending_inspection"] == []


# ---------------------------------------------------------------------------
# 9. status is idempotent and writes nothing
# ---------------------------------------------------------------------------


def test_status_repeat_query_is_byte_identical_and_writes_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        cfg = _lib.load_config(root)
        _write_launch_order(root, run_id="run-1", batch_id="batch-1")
        _write_jobs(root, {"run-2": {"state": "running"}})
        runs_row = helpers.make_runs_row_normal(run_id="run-3", batch_id="batch-3")
        helpers.write_jsonl(cfg.ledger_path("runs"), [runs_row])
        _write_batch_report(root, "b1.md", batch_id="batch-3", run_ids=["run-3"], inspection_report="")

        before = _snapshot(root)
        code1, out1, err1 = helpers.run_ledger(root, "status", "--layer", "deploy")
        code2, out2, err2 = helpers.run_ledger(root, "status", "--layer", "deploy")
        after = _snapshot(root)

        assert code1 == 0 and code2 == 0, (err1, err2)
        view1, view2 = json.loads(out1), json.loads(out2)
        view1.pop("generated_at")
        view2.pop("generated_at")
        assert view1 == view2
        assert before == after, "status must not write anything to the project directory"


# ---------------------------------------------------------------------------
# 10. waiting_on's action strings are routes.json's own "to" column, verbatim
# ---------------------------------------------------------------------------


def test_status_waiting_on_action_matches_routes_to_column():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        cfg = _lib.load_config(root)
        blocked_row = helpers.make_blocked_row(blocked_id="B001", status="open", to_layer="user")
        helpers.write_jsonl(cfg.ledger_path("blocked"), [blocked_row])
        _write_batch_report(root, "waiting.md", batch_id="batch-w", run_ids=[], inspection_report="")

        code, out, err = helpers.run_ledger(root, "status", "--layer", "idea")
        assert code == 0, err
        view = json.loads(out)

        routes = _lib.load_tables()["routes"]["routes"]
        expected_decide = next(r["to"] for r in routes if r["say"].startswith("有什么在等我"))
        expected_inspect = next(r["to"] for r in routes if r["say"].startswith("深查这批"))

        decide_entries = [w for w in view["waiting_on"] if w["ref"] == "B001"]
        inspect_entries = [w for w in view["waiting_on"] if w["ref"] == "batch-w"]
        assert len(decide_entries) == 1
        assert decide_entries[0]["action"] == expected_decide
        assert len(inspect_entries) == 1
        assert inspect_entries[0]["action"] == expected_inspect


# ---------------------------------------------------------------------------
# extra: json single-file ledgers ("direct" read class) are rejected too
# ---------------------------------------------------------------------------


def test_query_direct_ledger_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        code, out, err = helpers.run_ledger(root, "query", "launch_orders")
        assert code == 2
        assert err.strip() == "query.launch_orders: json ledger, read the file directly (direct)"


# ---------------------------------------------------------------------------
# extra: render blocked groups open/answered rows by to_layer, excludes
# closed rows, and uses the fixed column set
# ---------------------------------------------------------------------------


def test_render_blocked_groups_by_to_layer():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        cfg = _lib.load_config(root)
        open_deploy = helpers.make_blocked_row(blocked_id="B001", status="open", to_layer="deploy")
        answered_idea = helpers.make_blocked_row(
            blocked_id="B002", status="answered", to_layer="idea",
            answer="ok", answered_at=_lib.now_iso(), answered_by="user",
        )
        closed_row = helpers.make_blocked_row(blocked_id="B003", status="closed", to_layer="deploy")
        helpers.write_jsonl(cfg.ledger_path("blocked"), [open_deploy, answered_idea, closed_row])

        code, out, err = helpers.run_ledger(root, "render", "blocked")
        assert code == 0, err
        assert "## deploy" in out
        assert "## idea" in out
        assert "| blocked_id | kind | question | from_layer | raised_at |" in out
        assert "B001" in out
        assert "B002" in out
        assert "B003" not in out


# ---------------------------------------------------------------------------
# extra: approved_specs_in_flight / open_issues derivations
# ---------------------------------------------------------------------------


def test_status_approved_specs_in_flight_and_open_issues():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        _write_spec(root, "featx", approved_by="user")
        _write_issue(root, "featx", "01-open-thing", status="claimed")
        _write_issue(root, "featx", "02-done-thing", status="resolved")

        _write_spec(root, "featy", approved_by="user")
        _write_issue(root, "featy", "01-all-done", status="wontfix")

        code, out, err = helpers.run_ledger(root, "status", "--layer", "deploy")
        assert code == 0, err
        view = json.loads(out)

        assert ".scratch/featx/spec.md" in view["approved_specs_in_flight"]
        assert ".scratch/featy/spec.md" not in view["approved_specs_in_flight"]

        issue_ids = {i["issue_id"] for i in view["open_issues"]}
        assert "01-open-thing" in issue_ids
        assert "02-done-thing" not in issue_ids
        assert "01-all-done" not in issue_ids
