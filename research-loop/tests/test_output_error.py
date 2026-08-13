"""Tests for scripts/output_check.py and scripts/error_classify.py
(issues/12-output-error.md)."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import helpers


# ---------------------------------------------------------------------------
# output_check.py
# ---------------------------------------------------------------------------


def _write_launch_order(root: Path, expected_outputs, artifact_dir="artifacts") -> Path:
    order = {
        "run_id": "run-001",
        "artifact_dir": artifact_dir,
        "expected_outputs": expected_outputs,
    }
    path = root / "launch_order.json"
    path.write_text(json.dumps(order), encoding="utf-8")
    return path


def _last_json_line(stdout: str) -> dict:
    return json.loads(stdout.strip().splitlines()[-1])


def test_output_check_ok_when_products_are_all_present():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        art = root / "artifacts"
        art.mkdir()
        (art / "metrics.jsonl").write_text('{"a": 1}\n{"a": 2}\n', encoding="utf-8")
        order_path = _write_launch_order(root, [
            {"path_glob": "metrics.jsonl", "min_bytes": 1, "min_lines": 2, "required_keys": ["a"]},
        ])

        code, out, err = helpers.run_script(root, "output_check.py", "--launch-order", str(order_path))

        result = _last_json_line(out)
        assert result == {"verdict": "ok", "failures": []}
        assert code == 0


def test_output_check_zero_byte_file_is_empty_output():
    # spec §9: an experiment process exiting 0 with an empty product must
    # not be recorded ok -- exercised here by giving a 0-byte file against
    # a min_bytes gate (this script never reads the experiment's exit code).
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        art = root / "artifacts"
        art.mkdir()
        (art / "out.txt").write_text("", encoding="utf-8")
        order_path = _write_launch_order(root, [
            {"path_glob": "out.txt", "min_bytes": 1},
        ])

        code, out, err = helpers.run_script(root, "output_check.py", "--launch-order", str(order_path))

        result = _last_json_line(out)
        assert result["verdict"] == "empty-output"
        assert result["failures"] == [{
            "glob": "out.txt",
            "file": "artifacts/out.txt",
            "why": "size 0 bytes < min_bytes 1",
        }]
        assert code == 4


def test_output_check_glob_with_no_match_is_missing_output():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        art = root / "artifacts"
        art.mkdir()
        order_path = _write_launch_order(root, [
            {"path_glob": "nope-*.json"},
        ])

        code, out, err = helpers.run_script(root, "output_check.py", "--launch-order", str(order_path))

        result = _last_json_line(out)
        assert result["verdict"] == "missing-output"
        assert result["failures"] == [{"glob": "nope-*.json", "file": None, "why": "no file matched the glob"}]
        assert code == 4


def test_output_check_missing_required_key_is_empty_output():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        art = root / "artifacts"
        art.mkdir()
        (art / "metrics.jsonl").write_text('{"a": 1}\n', encoding="utf-8")
        order_path = _write_launch_order(root, [
            {"path_glob": "metrics.jsonl", "required_keys": ["a", "b"]},
        ])

        code, out, err = helpers.run_script(root, "output_check.py", "--launch-order", str(order_path))

        result = _last_json_line(out)
        assert result["verdict"] == "empty-output"
        assert "missing required_keys: ['b']" in result["failures"][0]["why"]
        assert code == 4


def test_output_check_short_file_is_empty_output():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        art = root / "artifacts"
        art.mkdir()
        (art / "log.txt").write_text("one line\n", encoding="utf-8")
        order_path = _write_launch_order(root, [
            {"path_glob": "log.txt", "min_lines": 3},
        ])

        code, out, err = helpers.run_script(root, "output_check.py", "--launch-order", str(order_path))

        result = _last_json_line(out)
        assert result["verdict"] == "empty-output"
        assert "1 lines < min_lines 3" in result["failures"][0]["why"]
        assert code == 4


def test_output_check_non_numeric_min_bytes_errors_cleanly():
    # a hand-authored launch order with min_bytes typoed as a string must not
    # crash the script with a raw TypeError traceback -- it fails cleanly
    # like any other unreadable launch order (T12/F2).
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        art = root / "artifacts"
        art.mkdir()
        (art / "out.txt").write_text("hello", encoding="utf-8")
        order_path = _write_launch_order(root, [
            {"path_glob": "out.txt", "min_bytes": "not-a-number"},
        ])

        code, out, err = helpers.run_script(root, "output_check.py", "--launch-order", str(order_path))

        assert code == 2
        assert out.strip() == ""
        assert "output_check:" in err
        assert "min_bytes" in err


def test_output_check_non_numeric_min_lines_errors_cleanly():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        art = root / "artifacts"
        art.mkdir()
        (art / "out.txt").write_text("hello\n", encoding="utf-8")
        order_path = _write_launch_order(root, [
            {"path_glob": "out.txt", "min_lines": "not-a-number"},
        ])

        code, out, err = helpers.run_script(root, "output_check.py", "--launch-order", str(order_path))

        assert code == 2
        assert out.strip() == ""
        assert "output_check:" in err
        assert "min_lines" in err


def test_output_check_missing_output_wins_priority_over_empty_output():
    # one entry misses entirely, another entry's file is present but too
    # small -- missing-output must win the overall verdict either way.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        art = root / "artifacts"
        art.mkdir()
        (art / "small.txt").write_text("x", encoding="utf-8")
        order_path = _write_launch_order(root, [
            {"path_glob": "small.txt", "min_bytes": 100},
            {"path_glob": "absent.txt"},
        ])

        code, out, err = helpers.run_script(root, "output_check.py", "--launch-order", str(order_path))

        result = _last_json_line(out)
        assert result["verdict"] == "missing-output"
        globs = {f["glob"] for f in result["failures"]}
        assert globs == {"small.txt", "absent.txt"}
        assert code == 4


# ---------------------------------------------------------------------------
# error_classify.py
# ---------------------------------------------------------------------------


ERROR_CLASSES = {
    "oom-kill": {"match": {"exit_code": 137}, "action": "swap-card"},
    "cuda-oom-log": {"match": {"log_regex": "CUDA out of memory"}, "action": "retry"},
    "empty-output-escalate": {"match": {"output_check": "empty-output"}, "action": "escalate"},
    "exit-and-log-both": {"match": {"exit_code": 1, "log_regex": "disk full"}, "action": "escalate"},
}


def _write_error_classes(root: Path, classes=None) -> Path:
    path = root / "error_classes.json"
    path.write_text(json.dumps(classes if classes is not None else ERROR_CLASSES), encoding="utf-8")
    return path


def test_error_classify_exit_code_rule_hits_oom_kill():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        classes_path = _write_error_classes(root)

        code, out, err = helpers.run_script(
            root, "error_classify.py", "--error-classes", str(classes_path), "--exit-code", "137",
        )

        assert _last_json_line(out) == {"rule": "oom-kill", "action": "swap-card"}
        assert code == 0


def test_error_classify_log_regex_rule_hits_cuda_oom():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        classes_path = _write_error_classes(root)
        log_path = root / "run.log"
        log_path.write_text("some preamble\nCUDA out of memory at step 4\n", encoding="utf-8")

        code, out, err = helpers.run_script(
            root, "error_classify.py", "--error-classes", str(classes_path), "--log", str(log_path),
        )

        assert _last_json_line(out) == {"rule": "cuda-oom-log", "action": "retry"}
        assert code == 0


def test_error_classify_output_check_rule_hits_escalate():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        classes_path = _write_error_classes(root)

        code, out, err = helpers.run_script(
            root, "error_classify.py", "--error-classes", str(classes_path),
            "--output-check", "empty-output",
        )

        assert _last_json_line(out) == {"rule": "empty-output-escalate", "action": "escalate"}
        assert code == 0


def test_error_classify_and_semantics_partial_match_does_not_count():
    # exit-and-log-both needs exit_code==1 AND log_regex "disk full". Giving
    # exit_code=1 with a log that lacks "disk full" must not fire it, and
    # nothing else in the table matches exit_code=1 alone.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        classes_path = _write_error_classes(root)
        log_path = root / "run.log"
        log_path.write_text("no relevant text here\n", encoding="utf-8")

        code, out, err = helpers.run_script(
            root, "error_classify.py", "--error-classes", str(classes_path),
            "--exit-code", "1", "--log", str(log_path),
        )

        assert _last_json_line(out) == {"rule": None, "action": "unknown"}
        assert code == 0


def test_error_classify_unknown_when_nothing_matches():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        classes_path = _write_error_classes(root)

        code, out, err = helpers.run_script(
            root, "error_classify.py", "--error-classes", str(classes_path),
            "--exit-code", "1",
        )

        assert _last_json_line(out) == {"rule": None, "action": "unknown"}
        assert code == 0


def test_error_classify_missing_action_field_errors_cleanly():
    # a rule that hand-authors forgot to give an "action" must not crash the
    # script with a raw KeyError traceback -- it fails cleanly like any other
    # malformed error-classes table (findings T12/F1).
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        classes_path = _write_error_classes(root, {
            "bad-rule": {"match": {"exit_code": 1}},
        })

        code, out, err = helpers.run_script(
            root, "error_classify.py", "--error-classes", str(classes_path),
            "--exit-code", "1",
        )

        assert code == 2
        assert out.strip() == ""
        assert "error_classify:" in err
        assert "bad-rule" in err


def test_error_classify_invalid_log_regex_errors_cleanly():
    # a log_regex that is not valid regex syntax must not crash the script
    # with a raw re.error traceback -- it fails cleanly instead (T12/F1).
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        classes_path = _write_error_classes(root, {
            "bad-regex-rule": {"match": {"log_regex": "(unclosed"}, "action": "retry"},
        })
        log_path = root / "run.log"
        log_path.write_text("anything\n", encoding="utf-8")

        code, out, err = helpers.run_script(
            root, "error_classify.py", "--error-classes", str(classes_path),
            "--log", str(log_path),
        )

        assert code == 2
        assert out.strip() == ""
        assert "error_classify:" in err


def test_error_classify_first_matching_rule_wins_key_order():
    # a broader rule placed earlier in file key order must win even though
    # a later, more specific rule would also match.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        classes = {
            "catch-all-137": {"match": {"exit_code": 137}, "action": "escalate"},
            "oom-kill": {"match": {"exit_code": 137}, "action": "swap-card"},
        }
        classes_path = _write_error_classes(root, classes)

        code, out, err = helpers.run_script(
            root, "error_classify.py", "--error-classes", str(classes_path), "--exit-code", "137",
        )

        assert _last_json_line(out) == {"rule": "catch-all-137", "action": "escalate"}
        assert code == 0
