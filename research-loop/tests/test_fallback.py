"""Tests for scripts/fallback/*.py and ledger_cmds/freezecmd.py
(issues/10-fallback-freeze.md). All fixtures use helpers.make_git_sandbox --
the dirty-tree and expected_commit checks need a real repo, and this module
standardizes on it throughout rather than mixing fixtures per test.

`ops/` is gitignored in every sandbox this file builds (`_sandbox()`): the
fallback three (jobs.json, launch_orders/, and fake-run artifact_dirs all
live under it) are treated as living, uncommitted operational data here,
the same way the real ledgers.json.dirty_exempt_globs example treats
ops/jobs.json*/ops/runs.jsonl -- so the dirty-tree gate (test 3 below) is
exercised against a real *tracked* file instead.
"""
from __future__ import annotations

import json
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import _lib
import helpers

_RUN_LEVEL_FIELDS = (
    "status", "output_dir", "runmeta_path", "seed", "dataset_version",
    "batch_id", "arm", "quick", "commit", "elapsed_s", "gpu_count",
)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def _sandbox(tmp) -> Path:
    """make_git_sandbox() plus a committed .gitignore for ops/ -- every
    file this test file writes at runtime (launch orders, jobs.json, fake
    run artifact_dirs, runs.jsonl) lives under ops/, so the launch.py dirty
    gate never trips on this module's own scratch writes."""
    root = helpers.make_git_sandbox(tmp)
    (root / ".gitignore").write_text("ops/\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "ignore ops/"], cwd=root, check=True)
    return root


def _registry_argv() -> list:
    registry_path = _lib.plugin_root() / "scripts" / "fallback" / "registry.py"
    return [sys.executable, str(registry_path)]


def _make_order(root: Path, run_id: str, *, mode="ok", seed=7, expected_runtime_s=600,
                 expected_commit=None, workdir=".", filter_=None, quick=True) -> tuple:
    reg = _registry_argv()
    artifact_dir = f"ops/runs/{run_id}"
    argv = reg + ["fake-experiment", "--seed", str(seed), "--mode", mode, "--out", artifact_dir]
    metrics_argv = reg + ["fake-metrics", "--dir", artifact_dir]
    metrics_cmd = " ".join(shlex.quote(a) for a in metrics_argv)
    commit = expected_commit if expected_commit is not None else _lib.git_head(root)

    order = {
        "run_id": run_id,
        "batch_id": "quick-20260814-1",
        "registry_task": "fake-experiment",
        "argv": argv,
        "env_name": "default",
        "workdir": workdir,
        "expected_commit": commit,
        "seed": seed,
        "dataset_version": "v1",
        "arm": "实验组",
        "filter": filter_,
        "quick": quick,
        "resources": {"gpus": 1, "min_vram_gb": 8, "exclusive": False},
        "expected_runtime_s": expected_runtime_s,
        "expected_outputs": [],
        "metrics_cmd": metrics_cmd,
        "artifact_dir": artifact_dir,
        "created_by": "deploy",
        "created_at": _lib.now_iso(),
    }
    path = root / "ops" / "launch_orders" / f"{run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(order, ensure_ascii=False), encoding="utf-8")
    return path, order


def _patch_config(root: Path, **updates) -> None:
    path = root / "research-loop.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(updates)
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8",
    )


def _run_launch(root: Path, order_path: Path, *extra):
    return helpers.run_script(root, "fallback/launch.py", str(order_path), *extra)


def _run_record(root: Path, order_path: Path, *extra):
    return helpers.run_script(root, "fallback/record.py", "--launch-order", str(order_path), *extra)


def _bare_git_repo(tmp) -> Path:
    """A git repo with no research-loop.json at all -- exercises launch.py's
    and record.py's `_lib.find_project_root() or Path.cwd()` fallback (both
    are otherwise only ever invoked from a wired sandbox in this file)."""
    root = Path(tmp) / "bare"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "research-loop tests"], cwd=root, check=True)
    (root / ".gitignore").write_text("ops/\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init bare repo"], cwd=root, check=True)
    return root


# ---------------------------------------------------------------------------
# 1. registry.py --list / unknown task
# ---------------------------------------------------------------------------


def test_registry_list_two_tasks_and_unknown_task_exits_4():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)

        code, out, err = helpers.run_script(root, "fallback/registry.py", "--list")
        assert code == 0, (out, err)
        assert set(line.strip() for line in out.splitlines() if line.strip()) == {
            "fake-experiment", "fake-metrics",
        }

        code, out, err = helpers.run_script(root, "fallback/registry.py", "no-such-task")
        assert code == 4
        assert "no-such-task" in err


# ---------------------------------------------------------------------------
# 2. launch ok: jobs done, RUNMETA complete, attempt1.log present, exit 0
# ---------------------------------------------------------------------------


def test_launch_ok_writes_runmeta_and_marks_jobs_done():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        order_path, order = _make_order(root, "fake-ok-1", mode="ok", seed=7)

        code, out, err = _run_launch(root, order_path)
        assert code == 0, (out, err)

        cfg = _lib.load_config(root)
        jobs = json.loads(Path(cfg.ledger_path("jobs")).read_text(encoding="utf-8"))
        entry = jobs[order["run_id"]]
        assert entry["state"] == "done"
        assert entry["launch_order_ref"] == str(order_path)
        assert entry["finished_at"] is not None
        assert entry["log_path"] == f"{order['artifact_dir']}/attempt1.log"

        artifact_dir = root / order["artifact_dir"]
        runmeta = json.loads((artifact_dir / "RUNMETA.json").read_text(encoding="utf-8"))
        assert runmeta["commit"] == _lib.git_head(root)
        assert runmeta["argv"] == order["argv"]
        assert runmeta["dirty_files"] == []
        assert runmeta["launch_order_ref"] == str(order_path)
        assert runmeta["env_name"] == "default"
        assert runmeta["outputs"] == []
        assert len(runmeta["attempts"]) == 1

        attempt = runmeta["attempts"][0]
        assert attempt["attempt_no"] == 1
        assert attempt["exit_code"] == 0
        assert attempt["argv"] == order["argv"]
        assert attempt["resources"] == order["resources"]
        assert attempt["started_at"] and attempt["finished_at"]

        log_file = artifact_dir / "attempt1.log"
        assert log_file.exists()
        assert (artifact_dir / "mode.txt").read_text(encoding="utf-8") == "ok"
        assert (artifact_dir / "result.jsonl").exists()


def test_launch_accepts_explicit_project_root_when_cwd_differs():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        order_path, order = _make_order(root, "fake-projroot-1", mode="ok")

        with tempfile.TemporaryDirectory() as elsewhere:
            launch_py = _lib.plugin_root() / "scripts" / "fallback" / "launch.py"
            proc = subprocess.run(
                [sys.executable, str(launch_py), str(order_path), "--project-root", str(root)],
                cwd=elsewhere, capture_output=True, text=True,
            )
        assert proc.returncode == 0, (proc.stdout, proc.stderr)
        assert (root / order["artifact_dir"] / "RUNMETA.json").exists()


def test_launch_and_record_fall_back_to_cwd_when_no_project_root_is_found():
    with tempfile.TemporaryDirectory() as tmp:
        root = _bare_git_repo(tmp)
        assert _lib.find_project_root(root) is None
        order_path, order = _make_order(root, "fake-unwired-1", mode="ok")

        code, out, err = _run_launch(root, order_path)
        assert code == 0, (out, err)
        assert (root / order["artifact_dir"] / "RUNMETA.json").exists()

        code, out, err = _run_record(root, order_path)
        assert code == 0, (out, err)
        rows = _lib.jsonl_rows(root / "ops" / "runs.jsonl")
        assert len(rows) == 2


# ---------------------------------------------------------------------------
# 3. dirty tree refused; dirty_exempt_globs hit -> allowed through
# ---------------------------------------------------------------------------


def test_launch_rejects_dirty_tree_but_honors_dirty_exempt_globs():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        order_path, _order = _make_order(root, "fake-dirty-1", mode="ok")

        method_path = root / "METHOD.md"
        method_path.write_text(method_path.read_text(encoding="utf-8") + "\n<!-- dirty -->\n",
                                encoding="utf-8")

        code, out, err = _run_launch(root, order_path)
        assert code == 3
        assert err.strip() == "refuse to launch: dirty tree; escalate to deploy layer"
        cfg = _lib.load_config(root)
        assert not Path(cfg.ledger_path("jobs")).exists()

        # _patch_config itself dirties research-loop.json too -- exempt both
        # patterns so this proves fnmatch handles more than one glob.
        _patch_config(root, dirty_exempt_globs=["*.md", "research-loop.json"])
        code, out, err = _run_launch(root, order_path)
        assert code == 0, (out, err)


# ---------------------------------------------------------------------------
# 4. expected_commit mismatch -> exit 3
# ---------------------------------------------------------------------------


def test_launch_rejects_expected_commit_mismatch():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        order_path, _order = _make_order(root, "fake-commit-1", mode="ok", expected_commit="deadbeef")

        code, out, err = _run_launch(root, order_path)
        assert code == 3
        assert "expected_commit mismatch" in err


# ---------------------------------------------------------------------------
# 5. rerun the same launch order twice: attempts length 2, attempt1 unchanged
# ---------------------------------------------------------------------------


def test_launch_rerun_appends_attempt_and_leaves_the_first_untouched():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        order_path, order = _make_order(root, "fake-rerun-1", mode="ok")
        runmeta_path = root / order["artifact_dir"] / "RUNMETA.json"

        code, out, err = _run_launch(root, order_path)
        assert code == 0, (out, err)
        first = json.loads(runmeta_path.read_text(encoding="utf-8"))
        assert len(first["attempts"]) == 1
        first_attempt = first["attempts"][0]

        code, out, err = _run_launch(root, order_path)
        assert code == 0, (out, err)
        second = json.loads(runmeta_path.read_text(encoding="utf-8"))
        assert len(second["attempts"]) == 2
        assert second["attempts"][0] == first_attempt
        assert second["attempts"][1]["attempt_no"] == 2
        assert (root / order["artifact_dir"] / "attempt2.log").exists()


# ---------------------------------------------------------------------------
# 6. timeout mode + expected_runtime_s=1 -> state=timeout, exit != 0, ~3s
# ---------------------------------------------------------------------------


def test_launch_timeout_kills_the_process_and_marks_jobs_timeout():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        order_path, order = _make_order(root, "fake-timeout-1", mode="timeout", expected_runtime_s=1)

        start = time.monotonic()
        code, out, err = _run_launch(root, order_path)
        elapsed = time.monotonic() - start
        assert code != 0, (out, err)
        assert elapsed < 15, "runtime_factor=3 x 1s should time out around 3s, not sleep the full 30s"

        cfg = _lib.load_config(root)
        jobs = json.loads(Path(cfg.ledger_path("jobs")).read_text(encoding="utf-8"))
        assert jobs[order["run_id"]]["state"] == "timeout"


# ---------------------------------------------------------------------------
# 7. record ok: two metric rows, matching run-level fields, schema-valid;
#    repeat record -> same primary key refused; --status override -> one
#    row with the three metric fields null
# ---------------------------------------------------------------------------


def test_record_ok_writes_two_metric_rows_with_matching_run_level_fields():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        order_path, order = _make_order(root, "fake-record-ok-1", mode="ok", seed=11)
        code, out, err = _run_launch(root, order_path)
        assert code == 0, (out, err)

        code, out, err = _run_record(root, order_path)
        assert code == 0, (out, err)

        cfg = _lib.load_config(root)
        runs_path = cfg.ledger_path("runs")
        rows = _lib.jsonl_rows(runs_path)
        assert len(rows) == 2
        assert {r["metric_name"] for r in rows} == {"acc", "rows"}

        acc_row = next(r for r in rows if r["metric_name"] == "acc")
        rows_row = next(r for r in rows if r["metric_name"] == "rows")
        assert rows_row["value"] == 5
        assert rows_row["n"] == 5
        assert acc_row["n"] == 5
        assert isinstance(acc_row["value"], float) and 0 <= acc_row["value"] < 1
        assert acc_row["gpu_count"] == 1
        assert acc_row["commit"] is None
        assert acc_row["principle_id"] is None

        for field in _RUN_LEVEL_FIELDS:
            assert acc_row[field] == rows_row[field], field

        schema = _lib.load_schema("runs.normal")
        for row in rows:
            _lib.validate(row, schema, "runs")  # raises _lib.RLError on failure

        # repeat record -> same (run_id, metric_name, filter) primary key
        # refused, no new rows land
        code, out, err = _run_record(root, order_path)
        assert code == 2, (out, err)
        assert _lib.jsonl_rows(runs_path) == rows


def test_record_status_override_writes_a_single_row_with_null_metric_fields():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        order_path, order = _make_order(root, "fake-record-empty-1", mode="empty")
        code, out, err = _run_launch(root, order_path)
        assert code == 0, (out, err)

        code, out, err = _run_record(root, order_path, "--status", "empty-output")
        assert code == 0, (out, err)

        cfg = _lib.load_config(root)
        rows = _lib.jsonl_rows(cfg.ledger_path("runs"))
        assert len(rows) == 1
        row = rows[0]
        assert row["status"] == "empty-output"
        assert row["metric_name"] is None
        assert row["value"] is None
        assert row["n"] is None

        schema = _lib.load_schema("runs.normal")
        _lib.validate(row, schema, "runs")


# ---------------------------------------------------------------------------
# 8. bad-metrics: record exit 2, no new rows
# ---------------------------------------------------------------------------


def test_record_bad_metrics_output_is_refused_with_no_new_rows():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        order_path, order = _make_order(root, "fake-badmetrics-1", mode="bad-metrics")
        code, out, err = _run_launch(root, order_path)
        assert code == 0, (out, err)

        code, out, err = _run_record(root, order_path)
        assert code == 2, (out, err)
        assert "no row recorded" in err

        cfg = _lib.load_config(root)
        runs_path = Path(cfg.ledger_path("runs"))
        rows = _lib.jsonl_rows(runs_path) if runs_path.exists() else []
        assert rows == []


# ---------------------------------------------------------------------------
# 9. freeze-legacy: both mechanical checks pass, repeat refused, --layer
#    rejected by argparse
# ---------------------------------------------------------------------------


def test_freeze_legacy_checks_pass_repeat_refused_and_layer_flag_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        cfg = _lib.load_config(root)
        runs_path = Path(cfg.ledger_path("runs"))
        runs_path.parent.mkdir(parents=True, exist_ok=True)
        original = (json.dumps({"run_id": "x", "status": "ok"}) + "\n").encode("utf-8")
        runs_path.write_bytes(original)
        legacy_path = runs_path.parent / "runs.legacy.jsonl"

        # no --confirm -> exit 1, nothing written
        code, out, err = helpers.run_ledger(root, "freeze-legacy")
        assert code == 1, (out, err)
        assert not legacy_path.exists()
        assert runs_path.read_bytes() == original

        # --confirm -> both mechanical checks hold
        code, out, err = helpers.run_ledger(root, "freeze-legacy", "--confirm")
        assert code == 0, (out, err)
        assert legacy_path.read_bytes() == original  # check (1)
        assert runs_path.stat().st_size == 0          # check (2)

        # repeat -> refused
        code, out, err = helpers.run_ledger(root, "freeze-legacy", "--confirm")
        assert code == 1
        assert "repeat refused" in err
        assert legacy_path.read_bytes() == original  # untouched by the refused repeat

        # freeze-legacy takes no --layer
        code, out, err = helpers.run_ledger(root, "freeze-legacy", "--layer", "deploy", "--confirm")
        assert code == 2
        assert "unrecognized" in err.lower()
