"""Tests for ledger_cmds/blockedcmd.py and ledger_cmds/decisionscmd.py
(issues/05-blocked-decisions.md). Numbered comment blocks below correspond
to the ticket's "测试" list 1-12."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import _lib
import helpers
from ledger_cmds import decisionscmd


def _sandbox(tmp):
    return helpers.make_sandbox(Path(tmp))


def _blocked_rows(root):
    return _lib.jsonl_rows(_lib.load_config(root).ledger_path("blocked"))


def _decisions_rows(root):
    return _lib.jsonl_rows(_lib.load_config(root).ledger_path("decisions"))


def _open_blocked(root, layer="run", to_layer="deploy", kind="other", ref="S001",
                   question="what now?", evidence=("ops/evidence.txt",),
                   where=None, options=None):
    args = ["blocked", "open", "--layer", layer, "--to-layer", to_layer,
            "--kind", kind, "--ref", ref, "--question", question,
            "--evidence", *evidence]
    if where is not None:
        args += ["--where", where]
    if options is not None:
        args += ["--options", *options]
    return helpers.run_ledger(root, *args)


def _grant(root, layer="deploy", question="may we?", reason="user said so",
           scope_desc="gpu jobs", scope_globs=("ops/**",), expires=None):
    args = ["grant", "--layer", layer, "--question", question, "--reason", reason,
            "--scope-desc", scope_desc, "--scope-globs", *scope_globs]
    if expires is not None:
        args += ["--expires", expires]
    return helpers.run_ledger(root, *args)


def _decision(root, layer="deploy", question="which?", options=("A", "B"), chosen="A",
              reason="because", where="S1", authorized_by="spec-standing-gpu-1h",
              decided_by=None, principle_ref=None, affects=None):
    args = ["decision", "--layer", layer, "--question", question, "--options", *options,
            "--chosen", chosen, "--reason", reason, "--where", where,
            "--authorized-by", authorized_by]
    if decided_by is not None:
        args += ["--decided-by", decided_by]
    if principle_ref is not None:
        args += ["--principle-ref", principle_ref]
    if affects is not None:
        args += ["--affects", *affects]
    return helpers.run_ledger(root, *args)


# ---------------------------------------------------------------------------
# 1. open: r5-choice missing --where/--options rejected; valid open -> B001.
# ---------------------------------------------------------------------------


def test_open_r5_choice_missing_where_options_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        code, out, err = _open_blocked(root, kind="r5-choice")
        assert code == 2
        assert "blocked.where" in err


def test_open_creates_b001():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        code, out, err = _open_blocked(root)
        assert code == 0, (out, err)
        row = json.loads(out.strip())
        assert row["blocked_id"] == "B001"
        assert row["status"] == "open"
        rows = _blocked_rows(root)
        assert len(rows) == 1 and rows[0]["blocked_id"] == "B001"


# ---------------------------------------------------------------------------
# 2. answer write rights: to_layer must match --layer (unless to_layer=user).
# ---------------------------------------------------------------------------


def test_answer_write_rights_to_layer_must_match():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        _open_blocked(root, layer="run", to_layer="deploy")

        code, out, err = helpers.run_ledger(
            root, "blocked", "answer", "--layer", "run", "B001", "--answer", "go ahead"
        )
        assert code == 2
        assert "blocked.to_layer" in err

        code, out, err = helpers.run_ledger(
            root, "blocked", "answer", "--layer", "deploy", "B001", "--answer", "go ahead"
        )
        assert code == 0, (out, err)
        row = json.loads(out.strip())
        assert row["status"] == "answered"
        assert row["answered_by"] == "deploy"


# ---------------------------------------------------------------------------
# 3. illegal transitions: answered->answered rejected; withdrawn->closed rejected.
# ---------------------------------------------------------------------------


def test_illegal_transitions():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)

        _open_blocked(root, layer="run", to_layer="deploy")  # B001
        helpers.run_ledger(root, "blocked", "close", "--layer", "run", "B001")
        code, out, err = helpers.run_ledger(
            root, "blocked", "answer", "--layer", "deploy", "B001", "--answer", "too late"
        )
        assert code == 2
        assert "illegal transition to answered" in err

        _open_blocked(root, layer="run", to_layer="deploy")  # B002
        helpers.run_ledger(root, "blocked", "answer", "--layer", "deploy", "B002", "--answer", "ok")
        code, out, err = helpers.run_ledger(root, "blocked", "withdraw", "B002", "--reason", "changed mind")
        assert code == 0, (out, err)
        code, out, err = helpers.run_ledger(root, "blocked", "close", "--layer", "run", "B002")
        assert code == 2


# ---------------------------------------------------------------------------
# 4. r5: missing --chosen; missing --grant (answered_by defaults to layer,
#    which != user); expired grant rejected; valid grant assembles a decision.
# ---------------------------------------------------------------------------


def test_r5_answer_requires_chosen_then_grant_then_active_grant():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        _open_blocked(root, layer="run", to_layer="deploy", kind="r5-choice",
                      where="which env", options=["A", "B"])

        code, out, err = helpers.run_ledger(
            root, "blocked", "answer", "--layer", "deploy", "B001", "--answer", "go with A"
        )
        assert code == 2
        assert "blocked.chosen" in err

        code, out, err = helpers.run_ledger(
            root, "blocked", "answer", "--layer", "deploy", "B001",
            "--answer", "go with A", "--chosen", "A",
        )
        assert code == 2
        assert "blocked.grant_ref" in err

        gcode, gout, gerr = _grant(root, expires="2000-01-01T00:00:00")
        assert gcode == 0, (gout, gerr)
        expired_id = json.loads(gout.strip())["decision_id"]
        code, out, err = helpers.run_ledger(
            root, "blocked", "answer", "--layer", "deploy", "B001",
            "--answer", "go with A", "--chosen", "A", "--grant", expired_id,
        )
        assert code == 2
        assert "blocked.grant_ref" in err

        gcode, gout, gerr = _grant(root, expires="2099-01-01T00:00:00")
        assert gcode == 0, (gout, gerr)
        good_id = json.loads(gout.strip())["decision_id"]
        code, out, err = helpers.run_ledger(
            root, "blocked", "answer", "--layer", "deploy", "B001",
            "--answer", "go with A", "--chosen", "A", "--grant", good_id,
        )
        assert code == 0, (out, err)
        answered = json.loads(out.strip())
        assert answered["decision_ref"] is not None

        decision = next(d for d in _decisions_rows(root) if d["decision_id"] == answered["decision_ref"])
        assert decision["authorized_by"] == f"grant:{good_id}"
        assert decision["decided_by"] == "agent"
        assert decision["chosen"] == "A"
        assert decision["blocked_ref"] == "B001"
        assert decision["where"] == "which env"
        assert decision["reason"] == "go with A"


# ---------------------------------------------------------------------------
# 5. answered_by=user path: no --grant required, decision.decided_by=user,
#    authorized_by = the answer's own words.
# ---------------------------------------------------------------------------


def test_answer_r5_with_answered_by_user_does_not_require_grant():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        _open_blocked(root, layer="run", to_layer="deploy", kind="r5-choice",
                      where="which env", options=["A", "B"])
        code, out, err = helpers.run_ledger(
            root, "blocked", "answer", "--layer", "deploy", "B001",
            "--answer", "user said A, verbatim", "--chosen", "A", "--answered-by", "user",
        )
        assert code == 0, (out, err)
        row = json.loads(out.strip())
        assert row["answered_by"] == "user"

        decision = next(d for d in _decisions_rows(root) if d["decision_id"] == row["decision_ref"])
        assert decision["decided_by"] == "user"
        assert decision["authorized_by"] == "user said A, verbatim"


# ---------------------------------------------------------------------------
# 6. to_layer=user special case: any --layer may answer, answered_by is
#    forced to "user"; an explicit --answered-by other than user is rejected.
# ---------------------------------------------------------------------------


def test_to_layer_user_any_layer_can_answer_but_answered_by_locked_to_user():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        _open_blocked(root, layer="deploy", to_layer="user")  # B001
        code, out, err = helpers.run_ledger(
            root, "blocked", "answer", "--layer", "run", "B001", "--answer", "user's own words"
        )
        assert code == 0, (out, err)
        row = json.loads(out.strip())
        assert row["answered_by"] == "user"

        _open_blocked(root, layer="deploy", to_layer="user")  # B002
        code, out, err = helpers.run_ledger(
            root, "blocked", "answer", "--layer", "run", "B002",
            "--answer", "x", "--answered-by", "run",
        )
        assert code == 2


# ---------------------------------------------------------------------------
# 7. same answer-r5 command run twice: second run is rejected (row is no
#    longer open) and decisions stays at exactly one row / decision_ref
#    unchanged -- repeat invocation never corrupts state.
# ---------------------------------------------------------------------------


def test_answer_r5_second_identical_run_rejected_no_double_decision():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        _open_blocked(root, layer="run", to_layer="deploy", kind="r5-choice",
                      where="w", options=["A", "B"])
        gcode, gout, _ = _grant(root, expires="2099-01-01T00:00:00")
        grant_id = json.loads(gout.strip())["decision_id"]
        answer_args = ("blocked", "answer", "--layer", "deploy", "B001", "--answer", "go A",
                       "--chosen", "A", "--grant", grant_id)

        code1, out1, err1 = helpers.run_ledger(root, *answer_args)
        assert code1 == 0, (out1, err1)
        row1 = json.loads(out1.strip())

        code2, out2, err2 = helpers.run_ledger(root, *answer_args)
        assert code2 == 2
        assert "illegal transition to answered" in err2

        matching = [d for d in _decisions_rows(root) if d.get("blocked_ref") == "B001"]
        assert len(matching) == 1
        assert matching[0]["decision_id"] == row1["decision_ref"]


# ---------------------------------------------------------------------------
# 8. withdraw: open row rejected; answered row -> old row withdrawn with the
#    original-words annotation, new open row mechanically reopened with the
#    old row's fields carried over and ref=old id; rerunning the whole
#    command is idempotent (no extra rows).
# ---------------------------------------------------------------------------


def test_withdraw_open_row_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        _open_blocked(root, layer="run", to_layer="deploy")
        code, out, err = helpers.run_ledger(root, "blocked", "withdraw", "B001", "--reason", "x")
        assert code == 2
        assert "withdraw applies to answered rows" in err


def test_withdraw_answered_row_reopens_then_idempotent_rerun():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        _open_blocked(root, layer="run", to_layer="deploy", kind="other", ref="S1")
        helpers.run_ledger(root, "blocked", "answer", "--layer", "deploy", "B001", "--answer", "go with A")

        code, out, err = helpers.run_ledger(root, "blocked", "withdraw", "B001", "--reason", "changed my mind")
        assert code == 0, (out, err)

        rows = _blocked_rows(root)
        old = next(r for r in rows if r["blocked_id"] == "B001")
        assert old["status"] == "withdrawn"
        assert old["answer"].endswith("\n[withdrawn by user: changed my mind]")

        reopened = [r for r in rows if r["ref"] == "B001" and r["status"] == "open"]
        assert len(reopened) == 1
        new = reopened[0]
        assert new["blocked_id"] != "B001"
        assert new["from_layer"] == old["from_layer"] == "run"
        assert new["to_layer"] == old["to_layer"] == "deploy"
        assert new["kind"] == old["kind"]

        code, out, err = helpers.run_ledger(root, "blocked", "withdraw", "B001", "--reason", "again")
        assert code == 0, (out, err)
        assert len(_blocked_rows(root)) == len(rows)  # idempotent: no new rows


def test_withdraw_syncs_decision_to_withdrawn():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        _open_blocked(root, layer="run", to_layer="deploy", kind="r5-choice", where="w", options=["A", "B"])
        code, out, err = helpers.run_ledger(
            root, "blocked", "answer", "--layer", "deploy", "B001",
            "--answer", "user chose A", "--chosen", "A", "--answered-by", "user",
        )
        assert code == 0, (out, err)
        decision_id = json.loads(out.strip())["decision_ref"]

        code, out, err = helpers.run_ledger(root, "blocked", "withdraw", "B001", "--reason", "reconsidered")
        assert code == 0, (out, err)

        decision = next(d for d in _decisions_rows(root) if d["decision_id"] == decision_id)
        assert decision["status"] == "withdrawn"
        assert decision["withdrawn_by"] == "user"
        assert decision["withdrawn_reason"] == "reconsidered"


# ---------------------------------------------------------------------------
# 9. orphan reverse lookup: blocked.decision_ref manually cleared (fixture)
#    -- withdraw still finds the synced decision via decisions.blocked_ref.
# ---------------------------------------------------------------------------


def test_withdraw_orphan_reverse_lookup_via_blocked_ref():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        _open_blocked(root, layer="run", to_layer="deploy", kind="r5-choice", where="w", options=["A", "B"])
        code, out, err = helpers.run_ledger(
            root, "blocked", "answer", "--layer", "deploy", "B001",
            "--answer", "user chose A", "--chosen", "A", "--answered-by", "user",
        )
        assert code == 0, (out, err)
        decision_id = json.loads(out.strip())["decision_ref"]

        blocked_path = _lib.load_config(root).ledger_path("blocked")
        rows = _lib.jsonl_rows(blocked_path)
        for row in rows:
            if row["blocked_id"] == "B001":
                row["decision_ref"] = None  # fixture: simulate an orphaned back-reference
        helpers.write_jsonl(blocked_path, rows)

        code, out, err = helpers.run_ledger(root, "blocked", "withdraw", "B001", "--reason", "orphan test")
        assert code == 0, (out, err)

        decision = next(d for d in _decisions_rows(root) if d["decision_id"] == decision_id)
        assert decision["status"] == "withdrawn"


# ---------------------------------------------------------------------------
# 10. grant: missing --scope-globs rejected; oversight rejected;
#     active_grants excludes expired/withdrawn/superseded/wrong-kind rows.
# ---------------------------------------------------------------------------


def test_grant_missing_scope_globs_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        code, out, err = helpers.run_ledger(
            root, "grant", "--layer", "deploy", "--question", "q", "--reason", "r",
            "--scope-desc", "d",
        )
        assert code == 2
        assert "decisions.scope" in err


def test_grant_oversight_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        code, out, err = helpers.run_ledger(
            root, "grant", "--layer", "oversight", "--question", "q", "--reason", "r",
            "--scope-desc", "d", "--scope-globs", "ops/**",
        )
        assert code == 2


def test_grant_valid_lands_in_active_grants():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        code, out, err = _grant(root)
        assert code == 0, (out, err)
        grant_id = json.loads(out.strip())["decision_id"]
        active = decisionscmd.active_grants(_decisions_rows(root), _lib.now_iso())
        assert grant_id in {g["decision_id"] for g in active}


def test_active_grants_excludes_expired_wrong_status_superseded_and_wrong_kind():
    now = "2026-08-14T00:00:00"
    active = decisionscmd.active_grants([
        {"kind": "grant", "status": "decided", "superseded_by": None,
         "scope": {"expires_at": None}, "decision_id": "D001"},
        {"kind": "grant", "status": "decided", "superseded_by": None,
         "scope": {"expires_at": "2099-01-01T00:00:00"}, "decision_id": "D002"},
        {"kind": "grant", "status": "decided", "superseded_by": None,
         "scope": {"expires_at": "2000-01-01T00:00:00"}, "decision_id": "D003"},
        {"kind": "grant", "status": "withdrawn", "superseded_by": None,
         "scope": {"expires_at": None}, "decision_id": "D004"},
        {"kind": "grant", "status": "decided", "superseded_by": "D002",
         "scope": {"expires_at": None}, "decision_id": "D005"},
        {"kind": "decision", "status": "decided", "superseded_by": None,
         "scope": None, "decision_id": "D006"},
    ], now)
    assert {g["decision_id"] for g in active} == {"D001", "D002"}


# ---------------------------------------------------------------------------
# 11. decision: decided_by=agent without a valid authorized_by rejected;
#     spec-standing-gpu-1h passes; an inactive grant reference rejected;
#     decided_by=user only accepted from --layer deploy.
# ---------------------------------------------------------------------------


def test_decision_agent_without_valid_authorized_by_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        code, out, err = _decision(root, authorized_by="just because")
        assert code == 2
        assert "decisions.authorized_by" in err


def test_decision_spec_standing_gpu_1h_passes():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        code, out, err = _decision(root, authorized_by="spec-standing-gpu-1h")
        assert code == 0, (out, err)
        row = json.loads(out.strip())
        assert row["decided_by"] == "agent"
        assert row["authorized_by"] == "spec-standing-gpu-1h"


def test_decision_agent_with_grant_authorized_by_requires_active_grant():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        gcode, gout, _ = _grant(root, expires="2000-01-01T00:00:00")
        expired_id = json.loads(gout.strip())["decision_id"]
        code, out, err = _decision(root, authorized_by=f"grant:{expired_id}")
        assert code == 2
        assert "decisions.authorized_by" in err

        gcode2, gout2, _ = _grant(root, expires="2099-01-01T00:00:00")
        good_id = json.loads(gout2.strip())["decision_id"]
        code, out, err = _decision(root, authorized_by=f"grant:{good_id}")
        assert code == 0, (out, err)


def test_decision_decided_by_user_only_accepted_from_layer_deploy():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        code, out, err = _decision(root, layer="idea", decided_by="user", authorized_by="user said so")
        assert code == 2
        assert "decisions.decided_by" in err

        code, out, err = _decision(root, layer="deploy", decided_by="user", authorized_by="user said so")
        assert code == 0, (out, err)
        row = json.loads(out.strip())
        assert row["decided_by"] == "user"


# ---------------------------------------------------------------------------
# 12. crash surface: step 1 (decision append) done, step 2 (blocked update)
#     not -- rerunning `answer` converges without a second decision row.
# ---------------------------------------------------------------------------


def test_answer_r5_converges_after_simulated_partial_write():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        code, out, err = _open_blocked(root, layer="run", to_layer="deploy", kind="r5-choice",
                                        where="w", options=["A", "B"])
        assert code == 0, (out, err)
        blocked_row = json.loads(out.strip())

        decisions_path = _lib.load_config(root).ledger_path("decisions")
        orphan_decision = {
            "decision_id": "D001", "kind": "decision", "where": "w",
            "question": blocked_row["question"], "options": ["A", "B"], "chosen": "A",
            "reason": "user chose A", "authorized_by": "user chose A", "scope": None,
            "principle_ref": None, "affects": ["S001"], "blocked_ref": "B001",
            "decided_by": "user", "raised_at": blocked_row["raised_at"],
            "decided_at": _lib.now_iso(), "status": "decided", "superseded_by": None,
            "withdrawn_by": None, "withdrawn_reason": None, "schema_version": 1,
        }
        helpers.write_jsonl(decisions_path, [orphan_decision])

        code, out, err = helpers.run_ledger(
            root, "blocked", "answer", "--layer", "deploy", "B001",
            "--answer", "user chose A", "--chosen", "A", "--answered-by", "user",
        )
        assert code == 0, (out, err)
        answered = json.loads(out.strip())
        assert answered["decision_ref"] == "D001"
        assert answered["status"] == "answered"

        assert len(_decisions_rows(root)) == 1  # no second decision row created


# ---------------------------------------------------------------------------
# Additional coverage at the boundaries this ticket touches, not individually
# numbered in the ticket's test list.
# ---------------------------------------------------------------------------


def test_close_write_right_and_status_gate():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        _open_blocked(root, layer="run", to_layer="deploy")
        code, out, err = helpers.run_ledger(root, "blocked", "close", "--layer", "deploy", "B001")
        assert code == 2
        assert "blocked.from_layer" in err

        code, out, err = helpers.run_ledger(root, "blocked", "close", "--layer", "run", "B001")
        assert code == 0, (out, err)
        row = json.loads(out.strip())
        assert row["status"] == "closed"


def test_decision_withdraw_sets_fields_and_validates_superseded_by():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        _, out1, _ = _decision(root, authorized_by="spec-standing-gpu-1h")
        d1 = json.loads(out1.strip())["decision_id"]
        _, out2, _ = _decision(root, authorized_by="spec-standing-gpu-1h")
        d2 = json.loads(out2.strip())["decision_id"]

        code, out, err = helpers.run_ledger(
            root, "decision-withdraw", d1, "--reason", "superseded", "--superseded-by", "D999"
        )
        assert code == 2
        assert "decisions.superseded_by" in err

        code, out, err = helpers.run_ledger(
            root, "decision-withdraw", d1, "--reason", "superseded", "--superseded-by", d2
        )
        assert code == 0, (out, err)
        row = json.loads(out.strip())
        assert row["status"] == "withdrawn"
        assert row["withdrawn_by"] == "user"
        assert row["withdrawn_reason"] == "superseded"
        assert row["superseded_by"] == d2


def test_row_not_found_errors():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        code, _, _ = helpers.run_ledger(root, "blocked", "answer", "--layer", "deploy", "B999", "--answer", "x")
        assert code == 2
        code, _, _ = helpers.run_ledger(root, "blocked", "close", "--layer", "deploy", "B999")
        assert code == 2
        code, _, _ = helpers.run_ledger(root, "blocked", "withdraw", "B999", "--reason", "x")
        assert code == 2
        code, _, _ = helpers.run_ledger(root, "decision-withdraw", "D999", "--reason", "x")
        assert code == 2
