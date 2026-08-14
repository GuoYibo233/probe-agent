"""Tests for ledger_cmds/storycmd.py and ledger_cmds/feedbackcmd.py
(issues/06-story-feedback.md)."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import _lib
import helpers


def _runs_path(root: Path) -> Path:
    return root / "ops" / "runs.jsonl"


def _story_path(root: Path) -> Path:
    return root / "ops" / "story.jsonl"


def _feedback_path(root: Path) -> Path:
    return root / "ops" / "feedback.jsonl"


def _story_row(root: Path, claim_id: str) -> dict:
    rows = _lib.jsonl_rows(_story_path(root))
    for row in rows:
        if row["claim_id"] == claim_id:
            return row
    raise AssertionError(f"{claim_id} not found in story.jsonl: {rows}")


# ---------------------------------------------------------------------------
# 1. story add: referenced-run write check (not found / not ok / quick / ok)
# ---------------------------------------------------------------------------


def test_story_add_rejects_evidence_run_not_found():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        code, out, err = helpers.run_ledger(
            root, "story", "add", "--layer", "idea", "--claim", "X beats baseline",
            # single-arm (no --baseline-runs): the referenced-run check this
            # test targets is orthogonal to #157's baseline/candidate
            # equality check, so it must not also trip that one.
            "--evidence-runs", "run-001",
            "--candidate-runs", "run-001", "--selection-rule", "best of 3",
            "--derivation-command", "python3 run.py eval run-001",
            "--principle-id", "P001", "--role", "主结果",
        )
        assert code == 2, (out, err)
        assert err.strip() == "story.evidence_runs: run not found (got: 'run-001')", err


def test_story_add_rejects_run_status_not_ok():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        helpers.write_jsonl(_runs_path(root), [
            helpers.make_runs_row_normal(run_id="run-001", status="failed", quick=False,
                                          metric_name=None, value=None, n=None),
        ])
        code, out, err = helpers.run_ledger(
            root, "story", "add", "--layer", "idea", "--claim", "X beats baseline",
            "--evidence-runs", "run-001",
            "--candidate-runs", "run-001", "--selection-rule", "best of 3",
            "--derivation-command", "python3 run.py eval run-001",
            "--principle-id", "P001", "--role", "主结果",
        )
        assert code == 2, (out, err)
        assert err.strip() == "story.evidence_runs: run status is not ok (got: 'run-001')", err


def test_story_add_rejects_quick_run():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        helpers.write_jsonl(_runs_path(root), [
            helpers.make_runs_row_normal(run_id="run-001", status="ok", quick=True),
        ])
        code, out, err = helpers.run_ledger(
            root, "story", "add", "--layer", "idea", "--claim", "X beats baseline",
            "--evidence-runs", "run-001",
            "--candidate-runs", "run-001", "--selection-rule", "best of 3",
            "--derivation-command", "python3 run.py eval run-001",
            "--principle-id", "P001", "--role", "主结果",
        )
        assert code == 2, (out, err)
        assert err.strip() == (
            "story.evidence_runs: quick runs cannot enter the story ledger (got: 'run-001')"
        ), err


def test_story_add_legit_lands_s001():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        helpers.write_jsonl(_runs_path(root), [
            helpers.make_runs_row_normal(run_id="run-000", status="ok", quick=False),
            helpers.make_runs_row_normal(run_id="run-001", status="ok", quick=False),
        ])
        code, out, err = helpers.run_ledger(
            root, "story", "add", "--layer", "idea", "--claim", "X beats baseline",
            "--evidence-runs", "run-001,run-000", "--baseline-runs", "run-000",
            "--candidate-runs", "run-001", "--selection-rule", "best of 3",
            "--derivation-command", "python3 run.py eval run-001",
            "--principle-id", "P001", "--role", "主结果",
        )
        assert code == 0, (out, err)
        row = _story_row(root, "S001")
        assert row["evidence_runs"] == ["run-001", "run-000"]
        assert row["baseline_runs"] == ["run-000"]
        assert row["candidate_runs"] == ["run-001"]
        assert row["decided_by"] == "user"
        assert row["status"] == "active"
        assert row["principle_id"] == "P001"


# ---------------------------------------------------------------------------
# 1b. #157: --baseline-runs is optional (omitted -> baseline_runs=null, a
#     single-arm claim); given, it must not equal candidate_runs' set.
# ---------------------------------------------------------------------------


def test_story_add_without_baseline_runs_lands_null():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        helpers.write_jsonl(_runs_path(root), [
            helpers.make_runs_row_normal(run_id="run-001", status="ok", quick=False),
        ])
        code, out, err = helpers.run_ledger(
            root, "story", "add", "--layer", "idea", "--claim", "single-arm absolute claim",
            "--evidence-runs", "run-001",
            "--candidate-runs", "run-001", "--selection-rule", "best of 3",
            "--derivation-command", "python3 run.py eval run-001",
            "--principle-id", "P001", "--role", "主结果",
        )
        assert code == 0, (out, err)
        row = _story_row(root, "S001")
        assert row["baseline_runs"] is None

        schema = _lib.load_schema("story")
        _lib.validate(row, schema, "story")  # raises _lib.RLError on failure


def test_story_add_baseline_equals_candidate_set_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        helpers.write_jsonl(_runs_path(root), [
            helpers.make_runs_row_normal(run_id="run-000", status="ok", quick=False),
            helpers.make_runs_row_normal(run_id="run-001", status="ok", quick=False),
        ])
        # same two run_ids on both sides, different order -- the equality
        # check is set-based, not order-based.
        code, out, err = helpers.run_ledger(
            root, "story", "add", "--layer", "idea", "--claim", "X beats baseline",
            "--evidence-runs", "run-000,run-001",
            "--baseline-runs", "run-001,run-000",
            "--candidate-runs", "run-000,run-001",
            "--selection-rule", "best of 3",
            "--derivation-command", "python3 run.py eval run-001",
            "--principle-id", "P001", "--role", "主结果",
        )
        assert code == 2, (out, err)
        assert err.strip() == (
            "story.baseline_runs: baseline set equals candidate set; a comparison "
            "against itself is empty (got: ['run-001', 'run-000'])"
        ), err
        assert not _story_path(root).exists() or _story_path(root).read_text() == ""


# ---------------------------------------------------------------------------
# 2. metric_names must exist on every referenced run
# ---------------------------------------------------------------------------


def test_story_add_rejects_unknown_metric_name():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        helpers.write_jsonl(_runs_path(root), [
            helpers.make_runs_row_normal(run_id="run-001", status="ok", quick=False,
                                          metric_name="accuracy"),
        ])
        code, out, err = helpers.run_ledger(
            root, "story", "add", "--layer", "idea", "--claim", "X beats baseline",
            "--evidence-runs", "run-001",
            "--candidate-runs", "run-001", "--metric-names", "accuracy,f1",
            "--selection-rule", "best of 3",
            "--derivation-command", "python3 run.py eval run-001",
            "--principle-id", "P001", "--role", "主结果",
        )
        assert code == 2, (out, err)
        assert err.strip() == "story.metric_names: metric not found in referenced run (got: 'f1')", err


def test_story_add_accepts_metric_name_present_on_every_referenced_run():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        helpers.write_jsonl(_runs_path(root), [
            helpers.make_runs_row_normal(run_id="run-001", status="ok", quick=False,
                                          metric_name="accuracy"),
        ])
        code, out, err = helpers.run_ledger(
            root, "story", "add", "--layer", "idea", "--claim", "X beats baseline",
            "--evidence-runs", "run-001",
            "--candidate-runs", "run-001", "--metric-names", "accuracy",
            "--selection-rule", "best of 3",
            "--derivation-command", "python3 run.py eval run-001",
            "--principle-id", "P001", "--role", "主结果",
        )
        assert code == 0, (out, err)
        row = _story_row(root, "S001")
        assert row["metric_names"] == ["accuracy"]


# ---------------------------------------------------------------------------
# 3. a criterion row (quick=null) as evidence is let through
# ---------------------------------------------------------------------------


def test_story_add_allows_criterion_row_as_evidence():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        helpers.write_jsonl(_runs_path(root), [
            helpers.make_runs_row_criterion(run_id="chk-P001-20260813-1", status="ok"),
            helpers.make_runs_row_normal(run_id="run-001", status="ok", quick=False),
        ])
        code, out, err = helpers.run_ledger(
            root, "story", "add", "--layer", "idea", "--claim", "criterion clears the bar",
            "--evidence-runs", "chk-P001-20260813-1",
            "--candidate-runs", "run-001", "--selection-rule", "best of 3",
            "--derivation-command", "python3 run.py eval run-001",
            "--principle-id", "P001", "--role", "反例",
        )
        assert code == 0, (out, err)
        row = _story_row(root, "S001")
        assert row["evidence_runs"] == ["chk-P001-20260813-1"]


# ---------------------------------------------------------------------------
# 4. story add is idea-layer exclusive
# ---------------------------------------------------------------------------


def test_story_add_rejects_non_idea_layer():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        code, out, err = helpers.run_ledger(
            root, "story", "add", "--layer", "deploy", "--claim", "X beats baseline",
            "--evidence-runs", "run-001", "--baseline-runs", "run-001",
            "--candidate-runs", "run-001", "--selection-rule", "best of 3",
            "--derivation-command", "python3 run.py eval run-001",
            "--principle-id", "P001", "--role", "主结果",
        )
        assert code == 2, (out, err)
        assert "story.layer" in err
        assert not _story_path(root).exists() or _story_path(root).read_text() == ""


# ---------------------------------------------------------------------------
# 5. story retire: all five whitelist fields land; bad --superseded-by rejected
# ---------------------------------------------------------------------------


def _add_story(root, claim="X beats baseline"):
    helpers.write_jsonl(_runs_path(root), [
        helpers.make_runs_row_normal(run_id="run-001", status="ok", quick=False),
    ])
    code, out, err = helpers.run_ledger(
        root, "story", "add", "--layer", "idea", "--claim", claim,
        "--evidence-runs", "run-001",
        "--candidate-runs", "run-001", "--selection-rule", "best of 3",
        "--derivation-command", "python3 run.py eval run-001",
        "--principle-id", "P001", "--role", "主结果",
    )
    assert code == 0, (out, err)
    return json.loads(out.strip().splitlines()[-1])["claim_id"]


def test_story_retire_sets_all_five_whitelist_fields():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        sid = _add_story(root)

        code, out, err = helpers.run_ledger(
            root, "story", "retire", sid, "--reason", "the effect did not replicate",
        )
        assert code == 0, (out, err)

        row = _story_row(root, sid)
        assert row["status"] == "retired"
        assert row["retired_reason"] == "the effect did not replicate"
        assert row["retired_date"] == _lib.today()
        assert row["retired_by"] == "user"
        assert row["superseded_by"] is None
        # unrelated fields untouched
        assert row["claim"] == "X beats baseline"


def test_story_retire_rejects_blank_reason():
    # writes.json withdrawal_proxy: "无用户原话拒" -- retire is a proxy write,
    # so the user's own words are the only thing that makes it legitimate.
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        sid = _add_story(root)

        code, out, err = helpers.run_ledger(root, "story", "retire", sid, "--reason", "   ")
        assert code == 2, (out, err)
        assert "story.retired_reason" in err
        row = _story_row(root, sid)
        assert row["status"] == "active"


def test_story_retire_rejects_superseded_by_pointing_nowhere():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        sid = _add_story(root)

        code, out, err = helpers.run_ledger(
            root, "story", "retire", sid, "--reason", "superseded by a later run",
            "--superseded-by", "S999",
        )
        assert code == 2, (out, err)
        assert err.strip() == "story.superseded_by: claim not found (got: 'S999')", err
        # the row must be untouched -- validation happens before the write
        row = _story_row(root, sid)
        assert row["status"] == "active"


# ---------------------------------------------------------------------------
# 6. feedback add: four layers pass, layer self-certifies; --layer user rejected
# ---------------------------------------------------------------------------


def test_feedback_add_accepts_each_of_four_layers_with_self_certifying_layer():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        for layer in ["idea", "deploy", "run", "oversight"]:
            code, out, err = helpers.run_ledger(
                root, "feedback", "add", "--layer", layer,
                "--context", f"batch for {layer}", "--problem", "the process was confusing",
                "--suggestion", "clarify the docs",
            )
            assert code == 0, (out, err)

        rows = _lib.jsonl_rows(_feedback_path(root))
        assert [row["layer"] for row in rows] == ["idea", "deploy", "run", "oversight"]
        assert all(row["kind"] == "suggestion" for row in rows)


def test_feedback_add_rejects_layer_user():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        code, out, err = helpers.run_ledger(
            root, "feedback", "add", "--layer", "user",
            "--context", "batch", "--problem", "p", "--suggestion", "s",
        )
        assert code == 2, (out, err)
        assert "feedback.layer" in err


# ---------------------------------------------------------------------------
# 7. feedback review: --layer deploy rejected; --ref -> review row rejected;
#    legit review lands
# ---------------------------------------------------------------------------


def _add_suggestion(root, layer="idea"):
    code, out, err = helpers.run_ledger(
        root, "feedback", "add", "--layer", layer,
        "--context", "batch", "--problem", "p", "--suggestion", "s",
    )
    assert code == 0, (out, err)
    return json.loads(out.strip().splitlines()[-1])["fb_id"]


def test_feedback_review_rejects_non_user_layer():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        fid = _add_suggestion(root)

        code, out, err = helpers.run_ledger(
            root, "feedback", "review", "--layer", "deploy", "--ref", fid,
            "--verdict", "accepted",
        )
        assert code == 2, (out, err)
        assert err.strip() == "feedback.layer: review rows only accept --layer user", err


def test_feedback_review_rejects_ref_not_found():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        _add_suggestion(root)

        code, out, err = helpers.run_ledger(
            root, "feedback", "review", "--layer", "user", "--ref", "F999",
            "--verdict", "accepted",
        )
        assert code == 2, (out, err)
        assert err.strip() == "feedback.ref: row not found (got: 'F999')", err


def test_feedback_review_rejects_ref_pointing_at_a_review_row():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        fid = _add_suggestion(root)

        code, out, err = helpers.run_ledger(
            root, "feedback", "review", "--layer", "user", "--ref", fid,
            "--verdict", "accepted",
        )
        assert code == 0, (out, err)
        review_id = json.loads(out.strip().splitlines()[-1])["fb_id"]

        code, out, err = helpers.run_ledger(
            root, "feedback", "review", "--layer", "user", "--ref", review_id,
            "--verdict", "rejected",
        )
        assert code == 2, (out, err)
        assert err.strip() == (
            f"feedback.ref: ref must point to a suggestion row (got: {review_id!r})"
        ), err


def test_feedback_review_legit_lands():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        fid = _add_suggestion(root)

        code, out, err = helpers.run_ledger(
            root, "feedback", "review", "--layer", "user", "--ref", fid,
            "--verdict", "accepted", "--note", "good idea, will do",
        )
        assert code == 0, (out, err)

        rows = _lib.jsonl_rows(_feedback_path(root))
        review_rows = [row for row in rows if row["kind"] == "review"]
        assert len(review_rows) == 1
        assert review_rows[0]["ref"] == fid
        assert review_rows[0]["layer"] == "user"
        assert review_rows[0]["verdict"] == "accepted"
        assert review_rows[0]["note"] == "good idea, will do"


# ---------------------------------------------------------------------------
# 8. rewriting an old feedback row is rejected at the shared-library level
# ---------------------------------------------------------------------------


def test_feedback_row_cannot_be_rewritten_via_inplace_update():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        path = _feedback_path(root)
        helpers.write_jsonl(path, [helpers.make_suggestion_row(fb_id="F001")])

        try:
            _lib.inplace_update(path, "fb_id", "F001", {"suggestion": "rewritten"}, whitelist=set())
        except _lib.RLError as e:
            assert "not in-place updatable" in e.message
        else:
            raise AssertionError("expected RLError: feedback rows have no in-place-update whitelist")
