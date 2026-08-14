"""Tests for scripts/evidence_lint.py, scripts/verify_report.py,
scripts/spotcheck.py and scripts/regression_check.py (issues/13-
oversight.md).

evidence_lint.py and spotcheck.py are pure text/file tools -- no project
config -- so their fixtures are plain files under a bare tempdir.
verify_report.py needs a project root only to resolve path:line references
and to `cwd=` its repro-command reruns (both point relative to it), so its
fixtures use a bare tempdir too, passed explicitly via --project-root.
regression_check.py reads the story and runs ledgers through Config, so its
fixtures go through helpers.make_sandbox() + helpers.write_jsonl (no CLI
write paths -- this ticket's own scripts must not depend on T06/T07's write
commands to build test data, same discipline as test_trace_check.py and
test_query_status.py).
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import _lib
import helpers


def _lines(out: str) -> list:
    return [line for line in out.strip().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# evidence_lint.py
# ---------------------------------------------------------------------------


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_evidence_lint_banned_word_in_body_is_caught():
    with tempfile.TemporaryDirectory() as tmp:
        path = _write(Path(tmp) / "report.md", "everything passed the smoke test\n")

        code, out, err = helpers.run_script(tmp, "evidence_lint.py", str(path))

        assert code == 1
        assert f"{path}:1: banned-word:" in out
        assert "passed" in out


def test_evidence_lint_word_boundary_avoids_false_positive():
    # "surpassed" contains "passed" as a bare substring but is not the word
    # "passed" -- must not fire (this is exactly why the English side of the
    # word list is matched on \b...\b, not plain substring).
    with tempfile.TemporaryDirectory() as tmp:
        path = _write(Path(tmp) / "report.md", "the candidate surpassed the baseline by a lot\n")

        code, out, err = helpers.run_script(tmp, "evidence_lint.py", str(path))

        assert code == 0
        assert out.strip() == ""


def test_evidence_lint_frontmatter_verdict_rejections_withdrawals_are_exempt():
    # rejections/withdrawals carry the user's own quoted words, which may
    # themselves contain a banned phrase ("looks good", "没问题") -- rows.json
    # evidence_lint_exempt._field_level: the exemption is field-level, so
    # these three frontmatter lines are skipped even though their raw text
    # would otherwise trip rule 1.
    text = (
        "---\n"
        'batch_id: "S001-20260813-1"\n'
        'rejections: [{"date": "2026-08-13", "by": "user", "reason": "it looks good enough"}]\n'
        'withdrawals: [{"date": "2026-08-13", "by": "user", "reason": "\\u6ca1\\u95ee\\u9898"}]\n'
        'verdict: "clean"\n'
        "---\n"
        "\n"
        "nothing else to report here\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = _write(Path(tmp) / "report.md", text)

        code, out, err = helpers.run_script(tmp, "evidence_lint.py", str(path))

        assert code == 0
        assert out.strip() == ""


def test_evidence_lint_other_frontmatter_fields_are_still_scanned():
    # only verdict/rejections/withdrawals are exempt -- a banned phrase
    # planted in any other frontmatter field must still be caught (rule 1 is
    # a field-level exemption, not a whole-block skip; contrast with rule 2
    # below, which does skip the whole frontmatter block).
    text = (
        "---\n"
        'batch_id: "everything passed setup"\n'
        "---\n"
        "\n"
        "body is clean\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = _write(Path(tmp) / "report.md", text)

        code, out, err = helpers.run_script(tmp, "evidence_lint.py", str(path))

        assert code == 1
        assert f"{path}:2: banned-word:" in out


def test_evidence_lint_number_without_repro_command_is_caught():
    with tempfile.TemporaryDirectory() as tmp:
        path = _write(Path(tmp) / "report.md", "count = 42\nnothing else nearby\n")

        code, out, err = helpers.run_script(tmp, "evidence_lint.py", str(path))

        assert code == 1
        assert f"{path}:1: no-repro-command:" in out


def test_evidence_lint_number_with_repro_command_next_line_is_clean():
    with tempfile.TemporaryDirectory() as tmp:
        path = _write(Path(tmp) / "report.md", "count = 42\n$ wc -l x\n= 42\n")

        code, out, err = helpers.run_script(tmp, "evidence_lint.py", str(path))

        assert code == 0
        assert out.strip() == ""


def test_evidence_lint_number_with_repro_command_within_three_lines_is_clean():
    text = "count = 42\nsome context line\nanother context line\n$ wc -l x\n= 42\n"
    with tempfile.TemporaryDirectory() as tmp:
        path = _write(Path(tmp) / "report.md", text)

        code, out, err = helpers.run_script(tmp, "evidence_lint.py", str(path))

        assert code == 0


def test_evidence_lint_exempt_shapes_never_need_a_repro_command():
    text = (
        "2026-08-13\n"
        "commit deadbeef1\n"
        "see ops/x.jsonl:12\n"
        "blocked entry B003\n"
        "chk-P001-20260813-1 recorded\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = _write(Path(tmp) / "report.md", text)

        code, out, err = helpers.run_script(tmp, "evidence_lint.py", str(path))

        assert code == 0
        assert out.strip() == ""


def test_evidence_lint_pure_decimal_long_number_is_not_hex_exempt():
    # A >=7-digit number with no a-f letter at all is not hash-shaped -- it
    # must not be swallowed by the git-HEAD/commit exemption, or a genuine
    # unsupported empirical claim (sample count, step count, ...) would go
    # unreported (F1, T13 wave5 fix round 1).
    text = "we processed 1234567 records total\nnothing else nearby\n"
    with tempfile.TemporaryDirectory() as tmp:
        path = _write(Path(tmp) / "report.md", text)

        code, out, err = helpers.run_script(tmp, "evidence_lint.py", str(path))

        assert code == 1
        assert f"{path}:1: no-repro-command:" in out


def test_evidence_lint_dollar_and_echo_lines_are_not_self_flagged():
    # the $ line and its = echo carry numbers themselves but are the
    # declaration this rule checks FOR, not a claim needing one of their own.
    text = "$ python3 script.py --n 100\n= 42\n"
    with tempfile.TemporaryDirectory() as tmp:
        path = _write(Path(tmp) / "report.md", text)

        code, out, err = helpers.run_script(tmp, "evidence_lint.py", str(path))

        assert code == 0
        assert out.strip() == ""


def test_evidence_lint_multiple_files_report_all_violations():
    with tempfile.TemporaryDirectory() as tmp:
        clean = _write(Path(tmp) / "clean.md", "nothing to see here\n")
        dirty = _write(Path(tmp) / "dirty.md", "no problems found anywhere\n")

        code, out, err = helpers.run_script(tmp, "evidence_lint.py", str(clean), str(dirty))

        assert code == 1
        found = _lines(out)
        assert len(found) == 1
        assert str(dirty) in found[0]
        assert str(clean) not in out


# ---------------------------------------------------------------------------
# evidence_lint.py -- rule 2 machine false-fire exemptions (v1-oversight-3 /
# v2-hop6-4/5/6, #159): five shapes that must go clean, plus two shapes that
# must keep firing (non-regression).
# ---------------------------------------------------------------------------


def test_evidence_lint_heading_number_prefix_is_stripped_not_flagged():
    # shape 2: a markdown heading/list numeral at the very start of the
    # line is not an empirical claim.
    with tempfile.TemporaryDirectory() as tmp:
        path = _write(Path(tmp) / "report.md", "## 2. Full-scope ledger read\n")

        code, out, err = helpers.run_script(tmp, "evidence_lint.py", str(path))

        assert code == 0
        assert out.strip() == ""


def test_evidence_lint_section_reference_is_stripped_not_flagged():
    # shape 3: a `§N` reference, including the parenthesised `(§1)` form,
    # is not an empirical claim.
    with tempfile.TemporaryDirectory() as tmp:
        path = _write(Path(tmp) / "report.md", "see the rule at (§1) for detail\n")

        code, out, err = helpers.run_script(tmp, "evidence_lint.py", str(path))

        assert code == 0
        assert out.strip() == ""


def test_evidence_lint_quoted_excerpt_line_is_not_flagged():
    # shape 1: a `> ` excerpt line is quoting a source, not asserting a
    # number of its own -- verify_report already checks the excerpt
    # byte-for-byte.
    with tempfile.TemporaryDirectory() as tmp:
        path = _write(Path(tmp) / "report.md", '> {"seed": 7, "elapsed_s": 0}\n')

        code, out, err = helpers.run_script(tmp, "evidence_lint.py", str(path))

        assert code == 0
        assert out.strip() == ""


def test_evidence_lint_letter_digit_token_is_stripped_not_flagged():
    # shape 4: a letter-digit token with no space between them (python3)
    # is an identifier, not an empirical claim.
    with tempfile.TemporaryDirectory() as tmp:
        path = _write(Path(tmp) / "report.md", "we ran python3 on the file\n")

        code, out, err = helpers.run_script(tmp, "evidence_lint.py", str(path))

        assert code == 0
        assert out.strip() == ""


def test_evidence_lint_dollar_line_continuation_is_protected():
    # shape 5: a `$ ` command's own backslash continuation line carries
    # the command's own arguments, not a claim.
    text = '$ python3 -c "print(1+1)" \\\n  --extra 5\n= 2\n'
    with tempfile.TemporaryDirectory() as tmp:
        path = _write(Path(tmp) / "report.md", text)

        code, out, err = helpers.run_script(tmp, "evidence_lint.py", str(path))

        assert code == 0
        assert out.strip() == ""


def test_evidence_lint_bare_row_count_still_caught():
    # non-regression: a bare decimal claim with no letter-digit fusion, no
    # heading marker, and no `$ ` follow-up must still fire.
    with tempfile.TemporaryDirectory() as tmp:
        path = _write(Path(tmp) / "report.md", "row count: 5\nnothing else nearby\n")

        code, out, err = helpers.run_script(tmp, "evidence_lint.py", str(path))

        assert code == 1
        assert f"{path}:1: no-repro-command:" in out


def test_evidence_lint_space_separated_ordinal_still_caught():
    # non-regression: "attempt 1" is not letter-digit-fused, so it stays
    # indistinguishable from a genuine count and must still fire.
    text = "between attempt 1 and attempt 2 nothing changed\n"
    with tempfile.TemporaryDirectory() as tmp:
        path = _write(Path(tmp) / "report.md", text)

        code, out, err = helpers.run_script(tmp, "evidence_lint.py", str(path))

        assert code == 1
        assert f"{path}:1: no-repro-command:" in out


# ---------------------------------------------------------------------------
# verify_report.py
# ---------------------------------------------------------------------------


def _vr_sandbox(tmp) -> Path:
    root = Path(tmp)
    (root / "ops").mkdir(parents=True, exist_ok=True)
    (root / "ops" / "target.txt").write_text(
        "alpha\nbeta line with UNIQUE_MARKER\ngamma\n", encoding="utf-8",
    )
    # verify_report.py never calls _lib.load_config(root) -- it only uses
    # root to resolve path:line references and as the cwd for repro-command
    # reruns -- but --project-root is still checked for a research-loop.json
    # marker before anything else runs (F2, sdd/final-review.md: the same
    # explicit-root guard trace_check.py/regression_check.py/doctor.py all
    # got), so every fixture that passes --project-root needs one on disk.
    (root / "research-loop.json").write_text("{}\n", encoding="utf-8")
    return root


def test_verify_report_all_true_is_exit_zero():
    with tempfile.TemporaryDirectory() as tmp:
        root = _vr_sandbox(tmp)
        report = (
            "Evidence at ops/target.txt:2\n"
            "> beta line with UNIQUE_MARKER\n"
            "\n"
            f"$ {sys.executable} -c \"print(42)\"\n"
            "= 42\n"
        )
        path = _write(root / "report.md", report)

        code, out, err = helpers.run_script(
            root, "verify_report.py", str(path), "--project-root", str(root),
        )

        assert code == 0
        assert "0 failures" in out


def test_verify_report_dead_path_is_caught():
    with tempfile.TemporaryDirectory() as tmp:
        root = _vr_sandbox(tmp)
        path = _write(root / "report.md", "see ops/missing.txt:1\n")

        code, out, err = helpers.run_script(
            root, "verify_report.py", str(path), "--project-root", str(root),
        )

        assert code == 1
        assert "path:line" in out
        assert "ops/missing.txt" in out


def test_verify_report_line_number_out_of_range_is_caught():
    with tempfile.TemporaryDirectory() as tmp:
        root = _vr_sandbox(tmp)
        path = _write(root / "report.md", "see ops/target.txt:99\n")

        code, out, err = helpers.run_script(
            root, "verify_report.py", str(path), "--project-root", str(root),
        )

        assert code == 1
        assert "path:line" in out
        assert "99" in out


def test_verify_report_excerpt_mismatch_is_caught():
    with tempfile.TemporaryDirectory() as tmp:
        root = _vr_sandbox(tmp)
        report = "Evidence at ops/target.txt:2\n> beta line with a typo marker\n"
        path = _write(root / "report.md", report)

        code, out, err = helpers.run_script(
            root, "verify_report.py", str(path), "--project-root", str(root),
        )

        assert code == 1
        assert "excerpt" in out


def test_verify_report_forged_count_is_caught():
    with tempfile.TemporaryDirectory() as tmp:
        root = _vr_sandbox(tmp)
        report = f"$ {sys.executable} -c \"print(42)\"\n= 43\n"
        path = _write(root / "report.md", report)

        code, out, err = helpers.run_script(
            root, "verify_report.py", str(path), "--project-root", str(root),
        )

        assert code == 1
        assert "repro-command" in out
        assert "'43'" in out and "'42'" in out


def test_verify_report_nonzero_exit_command_is_a_failure():
    with tempfile.TemporaryDirectory() as tmp:
        root = _vr_sandbox(tmp)
        report = f"$ {sys.executable} -c \"import sys; sys.exit(1)\"\n= anything\n"
        path = _write(root / "report.md", report)

        code, out, err = helpers.run_script(
            root, "verify_report.py", str(path), "--project-root", str(root),
        )

        assert code == 1
        assert "repro-command" in out


# F2 (sdd/final-review.md): explicit --project-root with no
# research-loop.json under it refuses outright.
def test_verify_report_project_root_explicit_wrong_path_exits_2():
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as tmp_wrong:
        root = _vr_sandbox(tmp)
        path = _write(root / "report.md", "see ops/missing.txt:1\n")
        wrong_root = Path(tmp_wrong)

        code, out, err = helpers.run_script(
            root, "verify_report.py", str(path), "--project-root", str(wrong_root),
        )

        assert code == 2, (out, err)
        assert "research-loop.json" in err
        assert out == ""


# ---------------------------------------------------------------------------
# spotcheck.py
# ---------------------------------------------------------------------------


def _numbered_lines_file(root: Path, name: str, n: int) -> Path:
    path = root / name
    path.write_text("".join(f"line {i}\n" for i in range(1, n + 1)), encoding="utf-8")
    return path


def test_spotcheck_same_seed_same_file_is_byte_identical():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        path = _numbered_lines_file(root, "data.txt", 20)

        code1, out1, _ = helpers.run_script(root, "spotcheck.py", "--file", str(path), "--seed", "7", "--k", "3")
        code2, out2, _ = helpers.run_script(root, "spotcheck.py", "--file", str(path), "--seed", "7", "--k", "3")

        assert code1 == 0 and code2 == 0
        assert out1 == out2


def test_spotcheck_file_edit_changes_fingerprint():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        path = _numbered_lines_file(root, "data.txt", 20)

        _, out1, _ = helpers.run_script(root, "spotcheck.py", "--file", str(path), "--seed", "7", "--k", "3")
        before = json.loads(out1)

        with open(path, "a", encoding="utf-8") as f:
            f.write("line 21\n")

        _, out2, _ = helpers.run_script(root, "spotcheck.py", "--file", str(path), "--seed", "7", "--k", "3")
        after = json.loads(out2)

        assert before["fingerprint"]["rows"] != after["fingerprint"]["rows"]
        assert before["fingerprint"]["sha256"] != after["fingerprint"]["sha256"]


def test_spotcheck_samples_are_self_checkable():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        path = _numbered_lines_file(root, "data.txt", 50)

        code, out, err = helpers.run_script(root, "spotcheck.py", "--file", str(path), "--seed", "3", "--k", "5")
        result = json.loads(out)

        actual_lines = path.read_text(encoding="utf-8").splitlines()
        assert len(result["samples"]) == 5
        for sample in result["samples"]:
            ref_path, _, line_no = sample["ref"].rpartition(":")
            assert ref_path == str(path)
            actual_line = actual_lines[int(line_no) - 1]
            assert actual_line[:80] == sample["excerpt"]


def test_spotcheck_k_larger_than_row_count_is_capped():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        path = _numbered_lines_file(root, "data.txt", 3)

        code, out, err = helpers.run_script(root, "spotcheck.py", "--file", str(path), "--seed", "1", "--k", "10")
        result = json.loads(out)

        assert code == 0
        assert result["fingerprint"]["rows"] == 3
        assert len(result["samples"]) == 3


# ---------------------------------------------------------------------------
# regression_check.py
# ---------------------------------------------------------------------------


def _sandbox(tmp) -> Path:
    return helpers.make_sandbox(Path(tmp))


def _rc_fixture(root: Path, batch_id: str):
    story_rows = [
        helpers.make_story_row(
            claim_id="S001",
            evidence_runs=["r1"],
            baseline_runs=[],
            candidate_runs=["r1"],
            metric_names=["acc"],
            status="active",
        ),
        helpers.make_story_row(
            claim_id="S002",
            evidence_runs=["r2"],
            baseline_runs=[],
            candidate_runs=["r2"],
            metric_names=None,
            status="active",
        ),
        helpers.make_story_row(
            claim_id="S003",
            evidence_runs=["r3"],
            baseline_runs=[],
            candidate_runs=["r3"],
            metric_names=["acc"],
            status="retired",
            retired_reason="user said so",
            retired_date=_lib.today(),
            retired_by="user",
        ),
    ]
    helpers.write_jsonl(root / "ops" / "story.jsonl", story_rows)

    runs_rows = [
        helpers.make_runs_row_normal(
            run_id="r1", metric_name="acc", value=0.9, filter=None, batch_id="S001-20260101-1",
        ),
        helpers.make_runs_row_normal(
            run_id="r2", metric_name="acc", value=0.5, filter=None, batch_id="S002-20260101-1",
        ),
        helpers.make_runs_row_normal(
            run_id="r3", metric_name="acc", value=0.4, filter=None, batch_id="S003-20260101-1",
        ),
        # new batch: matches S001's (metric_name, filter) exactly.
        helpers.make_runs_row_normal(
            run_id="r9", metric_name="acc", value=0.7, filter=None, batch_id=batch_id,
        ),
    ]
    helpers.write_jsonl(root / "ops" / "runs.jsonl", runs_rows)


def test_regression_check_comparison_carries_old_and_new_with_no_judgment_language():
    batch_id = "quick-20260814-1"
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        _rc_fixture(root, batch_id)

        code, out, err = helpers.run_script(
            root, "regression_check.py", "--batch", batch_id, "--dry-run", "--project-root", str(root),
        )

        assert code == 0
        assert "0.9" in out
        assert "0.7" in out
        assert "S001" in out
        assert "conflict" not in out.lower()


def test_regression_check_metric_names_empty_claim_is_listed_under_skipped():
    batch_id = "quick-20260814-1"
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        _rc_fixture(root, batch_id)

        code, out, err = helpers.run_script(
            root, "regression_check.py", "--batch", batch_id, "--dry-run", "--project-root", str(root),
        )

        assert code == 0
        skipped_section = out.split("## Skipped", 1)[1]
        assert "S002" in skipped_section


def test_regression_check_retired_claim_is_not_compared_or_skipped():
    batch_id = "quick-20260814-1"
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        _rc_fixture(root, batch_id)

        code, out, err = helpers.run_script(
            root, "regression_check.py", "--batch", batch_id, "--dry-run", "--project-root", str(root),
        )

        assert "S003" not in out


def test_regression_check_dry_run_writes_nothing_under_reports():
    batch_id = "quick-20260814-1"
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        _rc_fixture(root, batch_id)
        reports_dir = root / "reports"
        before = sorted(p.name for p in reports_dir.iterdir())

        code, out, err = helpers.run_script(
            root, "regression_check.py", "--batch", batch_id, "--dry-run", "--project-root", str(root),
        )

        after = sorted(p.name for p in reports_dir.iterdir())
        assert code == 0
        assert before == after


def test_regression_check_without_dry_run_writes_report_file():
    batch_id = "quick-20260814-1"
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        _rc_fixture(root, batch_id)
        report_path = root / "reports" / f"regression-{batch_id}.md"
        assert not report_path.exists()

        code, out, err = helpers.run_script(
            root, "regression_check.py", "--batch", batch_id, "--project-root", str(root),
        )

        assert code == 0
        assert report_path.exists()
        written = report_path.read_text(encoding="utf-8")
        assert written.startswith("---\n")
        assert f'batch_id: "{batch_id}"' in written
        assert written.strip() == out.strip()


def test_regression_check_no_new_data_for_filter_emits_no_comparison():
    # S001's evidence run has filter=None; the new batch carries no row at
    # all for that (metric_name, filter) pair -- no comparison entry, and no
    # crash (this batch_id matches nothing in the fixture's runs ledger).
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        _rc_fixture(root, "quick-20260814-1")

        code, out, err = helpers.run_script(
            root, "regression_check.py", "--batch", "quick-99990101-9", "--dry-run", "--project-root", str(root),
        )

        assert code == 0
        comparisons_section = out.split("## Comparisons", 1)[1].split("## Skipped", 1)[0]
        assert "S001" not in comparisons_section


# F2 (sdd/final-review.md): explicit --project-root with no
# research-loop.json under it refuses outright -- the pre-fix behavior was
# a false-clean report (story_rows_read: 0, exit 0) instead of this.
def test_regression_check_project_root_explicit_wrong_path_exits_2():
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as tmp_wrong:
        root = _sandbox(tmp)
        _rc_fixture(root, "quick-20260814-1")
        wrong_root = Path(tmp_wrong)

        code, out, err = helpers.run_script(
            root, "regression_check.py", "--batch", "quick-20260814-1", "--dry-run",
            "--project-root", str(wrong_root),
        )

        assert code == 2, (out, err)
        assert "research-loop.json" in err
        assert out == ""
