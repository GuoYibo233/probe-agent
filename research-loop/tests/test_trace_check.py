"""Tests for scripts/trace_check.py (issues/11-trace-check.md).

Every fixture is hand-written straight to disk (jsonl rows via
helpers.write_jsonl / row factories, launch orders and RUNMETA as raw JSON,
spec/batch-report md files with hand-built '---' frontmatter) rather than
going through another ticket's CLI -- trace_check only depends on T03, and
this suite must not depend on T08's launch-order writer or T09's query/
status commands to exist.
"""
from __future__ import annotations

import builtins
import importlib
import json
import tempfile
from pathlib import Path

import _lib
import helpers
import trace_check
from ledger_cmds.principlescmd import parse_principles as _real_parse_principles


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _lines(out: str) -> list:
    return [line for line in out.strip().splitlines() if line.strip()]


def _dump_launch_order(root: Path, filename: str, order: dict) -> None:
    directory = root / "ops" / "launch_orders"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{filename}.json").write_text(json.dumps(order, ensure_ascii=False), encoding="utf-8")


def _write_launch_order(root: Path, **over) -> dict:
    """Write a launch order under its own run_id's canonical filename."""
    order = helpers.make_launch_order(**over)
    _dump_launch_order(root, order["run_id"], order)
    return order


def _write_launch_order_as(root: Path, filename: str, **over) -> dict:
    """Write a launch order under a filename that may disagree with its own
    run_id field -- for exercising the run_id-mismatch finding."""
    order = helpers.make_launch_order(**over)
    _dump_launch_order(root, filename, order)
    return order


def _write_issue(root: Path, rel_dir: str, issue_id: str) -> Path:
    path = root / rel_dir / f"{issue_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {issue_id}\n\nStatus: ready-for-agent\n", encoding="utf-8")
    return path


def _spec_render(spec_version, approved_by, approved_date, approved_digest, withdrawals, body) -> str:
    return (
        "---\n"
        f"spec_version: {json.dumps(spec_version)}\n"
        f"approved_by: {json.dumps(approved_by)}\n"
        f"approved_date: {json.dumps(approved_date)}\n"
        f"approved_digest: {json.dumps(approved_digest)}\n"
        f"withdrawals: {json.dumps(withdrawals)}\n"
        "---\n" + body
    )


def _write_spec(root: Path, rel_path: str, item_id: str, *, approved: bool = False,
                 approved_by: str = "user", spec_version: int = 1, withdrawals=None) -> Path:
    """Write a spec md file whose body contains `item_id` (forward-chain's
    own existence test: "字符串含 item_id"). approved=True fills in a
    correctly recomputed approved_digest for the body actually written."""
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    body = f"# spec\n\nItem {item_id} does something.\n"
    withdrawals = withdrawals if withdrawals is not None else []

    path.write_text(
        _spec_render(spec_version, None, None, None, withdrawals, body), encoding="utf-8",
    )
    if approved:
        digest = _lib.spec_digest(path)
        path.write_text(
            _spec_render(spec_version, approved_by, "2026-08-14", digest, withdrawals, body),
            encoding="utf-8",
        )
    return path


def _touch_spec_body(path: Path) -> None:
    """Append a byte to the spec's body -- the frontmatter header is left
    untouched, so the stored approved_digest goes stale."""
    path.write_text(path.read_text(encoding="utf-8") + ".", encoding="utf-8")


def _bump_spec_header(path: Path, *, withdrawals=None, spec_version=None) -> None:
    """Rewrite only frontmatter fields, byte-for-byte preserving the body
    (and, unless overridden, approved_digest) -- for the "only withdrawals /
    spec_version changed" not-stale case."""
    fields, body = _lib.parse_frontmatter(path.read_text(encoding="utf-8"))
    if withdrawals is not None:
        fields["withdrawals"] = withdrawals
    if spec_version is not None:
        fields["spec_version"] = spec_version
    header = "---\n" + "".join(f"{k}: {json.dumps(v)}\n" for k, v in fields.items()) + "---\n"
    path.write_text(header + body, encoding="utf-8")


def _write_runmeta(root: Path, rel_path: str, launch_order_ref) -> Path:
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"launch_order_ref": launch_order_ref}), encoding="utf-8")
    return path


def _write_jobs(root: Path, entries: dict) -> None:
    (root / "ops" / "jobs.json").write_text(json.dumps(entries), encoding="utf-8")


def _write_batch_report(root: Path, batch_id: str, *, run_ids=None, inspection_report: str = "") -> Path:
    path = root / "plans" / f"{batch_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "---\n"
        f"batch_id: {json.dumps(batch_id)}\n"
        f"spec_items: {json.dumps([])}\n"
        f"run_ids: {json.dumps(run_ids or [])}\n"
        f"date: {json.dumps('2026-08-14')}\n"
        f"how_to_read: {json.dumps('read via ledger.py query runs --batch ' + batch_id)}\n"
        f"inspection_report: {json.dumps(inspection_report)}\n"
        f"rejections: {json.dumps([])}\n"
        "---\n"
    )
    path.write_text(header + "\nbody\n", encoding="utf-8")
    return path


def _set_config_key(root: Path, key: str, value) -> None:
    cfg_path = root / "research-loop.json"
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    data[key] = value
    cfg_path.write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8",
    )


def _fix_method_criterion_cmd(root: Path) -> None:
    """helpers.METHOD_MD's P001 row carries criterion_cmd "python3
    stub_registry.py check-p001", which does not start with make_sandbox()'s
    actual registry_cmd prefix (sys.executable + an absolute stub path) --
    the same pre-existing mismatch issues/08-launch-order.md's Comments
    section and T07's own tests correct for. Rewrites P001's cell to the
    sandbox's real registry_cmd so criterion-row checks can resolve it."""
    cfg = _lib.load_config(root)
    method_path = root / "METHOD.md"
    text = method_path.read_text(encoding="utf-8")
    text = text.replace(
        "python3 stub_registry.py check-p001", f"{cfg.get('registry_cmd')} check-p001",
    )
    method_path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# 0. Loading resilience (fix round 1, F2) + ImportError fallback (F3)
#
# F2: a launch order file, ops/jobs.json, or a RUNMETA file that exists but
# fails to parse as JSON used to raise json.JSONDecodeError straight out of
# _load_launch_orders / _load_jobs / check_runs_backlink, uncaught by
# main()'s `except _lib.RLError` -- one corrupted file crashed the whole
# run (unhandled traceback, exit 1 with no finding printed) instead of
# being reported like every other broken reference this script checks for.
# F3: the `except ImportError` fallback for ledger_cmds.principlescmd (used
# only in a stripped deployment where that module isn't importable) had no
# automated coverage -- ledger_cmds.principlescmd is always importable in
# this test environment, so the primary branch always won and the ~40 lines
# of duplicated fallback parser were only ever hand-checked, not tested.
# ---------------------------------------------------------------------------


def test_load_malformed_launch_order_json_reported_not_crashed():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        bad_path = root / "ops" / "launch_orders" / "run-bad.json"
        bad_path.write_text("{not valid json", encoding="utf-8")

        code, out, err = helpers.run_script(root, "trace_check.py")

        assert code == 1, (out, err)
        lines = _lines(out)
        assert any(
            line.startswith("load.launch_order_unreadable:") and "run-bad.json" in line
            for line in lines
        ), (out, err)
        # No traceback on stderr -- reported as a finding, not an uncaught
        # exception (err would carry "Traceback" if json.loads had raised
        # straight out of main()).
        assert "Traceback" not in err, err
        assert lines[-1] == "trace_check: 1 errors, 0 warnings", out


def test_load_malformed_jobs_json_reported_not_crashed():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        (root / "ops" / "jobs.json").write_text("[not valid json", encoding="utf-8")

        code, out, err = helpers.run_script(root, "trace_check.py")

        assert code == 1, (out, err)
        lines = _lines(out)
        assert any(
            line.startswith("load.jobs_unreadable:") and "jobs.json" in line for line in lines
        ), (out, err)
        assert "Traceback" not in err, err
        assert lines[-1] == "trace_check: 1 errors, 0 warnings", out


def test_runs_backlink_runmeta_unreadable_reported_not_crashed():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        runmeta_path = root / "ops" / "runs" / "run-001" / "RUNMETA.json"
        runmeta_path.parent.mkdir(parents=True, exist_ok=True)
        runmeta_path.write_text("{not valid json", encoding="utf-8")
        helpers.write_jsonl(root / "ops" / "runs.jsonl", [
            helpers.make_runs_row_normal(run_id="run-001",
                                          runmeta_path="ops/runs/run-001/RUNMETA.json"),
        ])

        code, out, err = helpers.run_script(root, "trace_check.py")

        assert code == 1, (out, err)
        assert any(
            line.startswith("runs_backlink.runmeta_unreadable:") and "run-001" in line
            for line in _lines(out)
        ), (out, err)
        assert "Traceback" not in err, err


def test_import_error_fallback_parses_principles_same_as_primary():
    """trace_check.py's `except ImportError` fallback (its own copy of
    ledger_cmds.principlescmd.parse_principles) is reached only when `from
    ledger_cmds.principlescmd import parse_principles` fails at
    trace_check's module-load time -- which never happens through the
    normal `import trace_check` path in this test environment, since the
    real module is always importable here. Force that ImportError with a
    builtins.__import__ patch, reload trace_check under it (re-running its
    module body, which rebinds trace_check._parse_principles to the
    fallback def), and diff the fallback's parse of a real principles table
    (helpers.METHOD_MD, written by make_sandbox) against the real parser's
    output on the same file, byte for byte."""
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        method_path = root / "METHOD.md"
        expected = _real_parse_principles(method_path)
        assert expected, "fixture must produce at least one principle row"

        real_import = builtins.__import__

        def _blocking_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "ledger_cmds.principlescmd":
                raise ImportError("blocked by test_import_error_fallback_... to force the fallback")
            return real_import(name, globals, locals, fromlist, level)

        builtins.__import__ = _blocking_import
        try:
            importlib.reload(trace_check)
            fallback_rows = trace_check._parse_principles(method_path)
        finally:
            builtins.__import__ = real_import
            importlib.reload(trace_check)  # restore the primary-import binding for later tests

        assert fallback_rows == expected, (fallback_rows, expected)
        # The primary binding is back after the restoring reload above --
        # confirms the reload dance leaves no lasting state for other tests.
        assert trace_check._parse_principles is _real_parse_principles


# ---------------------------------------------------------------------------
# 1. Broken-chain findings (spec_ref / issue_ref / decision_ref / runmeta_path
#    / launch_order_ref / jobs reference)
# ---------------------------------------------------------------------------


def test_forward_chain_spec_ref_missing_reported():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        _write_issue(root, ".scratch/demo/issues", "01-example")
        _write_launch_order(root, run_id="run-001", quick=False, spec_ref="NOPE-1",
                             issue_ref="01-example", decision_refs=[])

        code, out, err = helpers.run_script(root, "trace_check.py")

        assert code == 1, (out, err)
        assert any(
            line.startswith("forward_chain.spec_ref:") and "NOPE-1" in line for line in _lines(out)
        ), out


def test_forward_chain_issue_ref_missing_reported():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        _write_spec(root, ".scratch/demo/spec.md", "IT-001", approved=True)
        _write_launch_order(root, run_id="run-001", quick=False, spec_ref="IT-001",
                             issue_ref="99-nope", decision_refs=[])

        code, out, err = helpers.run_script(root, "trace_check.py")

        assert code == 1, (out, err)
        assert any(
            line.startswith("forward_chain.issue_ref:") and "99-nope" in line for line in _lines(out)
        ), out


def test_forward_chain_decision_ref_missing_reported():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        _write_spec(root, ".scratch/demo/spec.md", "IT-001", approved=True)
        _write_issue(root, ".scratch/demo/issues", "01-example")
        _write_launch_order(root, run_id="run-001", quick=False, spec_ref="IT-001",
                             issue_ref="01-example", decision_refs=["D999"])

        code, out, err = helpers.run_script(root, "trace_check.py")

        assert code == 1, (out, err)
        assert any(
            line.startswith("forward_chain.decision_ref:") and "D999" in line for line in _lines(out)
        ), out


def test_forward_chain_decision_ref_not_decided_reported():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        _write_spec(root, ".scratch/demo/spec.md", "IT-001", approved=True)
        _write_issue(root, ".scratch/demo/issues", "01-example")
        helpers.write_jsonl(root / "ops" / "decisions.jsonl", [
            helpers.make_decision_row(decision_id="D001", status="withdrawn",
                                       withdrawn_by="user", withdrawn_reason="changed mind"),
        ])
        _write_launch_order(root, run_id="run-001", quick=False, spec_ref="IT-001",
                             issue_ref="01-example", decision_refs=["D001"])

        code, out, err = helpers.run_script(root, "trace_check.py")

        assert code == 1, (out, err)
        assert any(
            line.startswith("forward_chain.decision_ref:") and "D001" in line and "withdrawn" in line
            for line in _lines(out)
        ), out


def test_runs_backlink_runmeta_path_missing_reported():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        helpers.write_jsonl(root / "ops" / "runs.jsonl", [
            helpers.make_runs_row_normal(run_id="run-001",
                                          runmeta_path="ops/runs/run-001/RUNMETA.json"),
        ])

        code, out, err = helpers.run_script(root, "trace_check.py")

        assert code == 1, (out, err)
        assert any(
            line.startswith("runs_backlink.runmeta_missing:") and "run-001" in line
            for line in _lines(out)
        ), out


def test_runs_backlink_launch_order_ref_missing_reported():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        _write_runmeta(root, "ops/runs/run-001/RUNMETA.json", "run-999")
        helpers.write_jsonl(root / "ops" / "runs.jsonl", [
            helpers.make_runs_row_normal(run_id="run-001",
                                          runmeta_path="ops/runs/run-001/RUNMETA.json"),
        ])

        code, out, err = helpers.run_script(root, "trace_check.py")

        assert code == 1, (out, err)
        assert any(
            line.startswith("runs_backlink.launch_order_ref_missing:") and "run-999" in line
            for line in _lines(out)
        ), out


def test_runs_backlink_run_id_mismatch_reported():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        # Filed under ops/launch_orders/run-001.json, but the JSON body's own
        # run_id field says run-999 -- a real drift, distinct from "file
        # missing" (spec §5: filename IS the canonical run_id).
        _write_launch_order_as(root, "run-001", run_id="run-999", quick=True,
                                spec_ref=None, issue_ref=None, decision_refs=None)
        _write_runmeta(root, "ops/runs/run-001/RUNMETA.json", "run-001")
        helpers.write_jsonl(root / "ops" / "runs.jsonl", [
            helpers.make_runs_row_normal(run_id="run-001",
                                          runmeta_path="ops/runs/run-001/RUNMETA.json"),
        ])

        code, out, err = helpers.run_script(root, "trace_check.py")

        assert code == 1, (out, err)
        assert any(
            line.startswith("runs_backlink.run_id_mismatch:") and "run-999" in line
            for line in _lines(out)
        ), out


def test_jobs_backlink_missing_reported():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        _write_jobs(root, {"run-001": {"launch_order_ref": "run-999", "state": "done"}})

        code, out, err = helpers.run_script(root, "trace_check.py")

        assert code == 1, (out, err)
        assert any(
            line.startswith("jobs_backlink:") and "run-999" in line for line in _lines(out)
        ), out


# ---------------------------------------------------------------------------
# 2. quick exemption + criterion (judged) row's own path
# ---------------------------------------------------------------------------


def test_quick_launch_order_exempts_forward_chain_refs():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        _write_launch_order(root, run_id="quick-20260814-1", quick=True,
                             spec_ref=None, issue_ref=None, decision_refs=None)

        code, out, err = helpers.run_script(root, "trace_check.py")

        assert code == 0, (out, err)
        assert _lines(out)[-1] == "trace_check: 0 errors, 0 warnings"


def test_criterion_row_checks_principle_and_registry_not_spec_chain():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        _fix_method_criterion_cmd(root)
        helpers.write_jsonl(root / "ops" / "runs.jsonl", [
            helpers.make_runs_row_criterion(run_id="chk-P001-20260814-1", principle_id="P001"),
        ])

        code, out, err = helpers.run_script(root, "trace_check.py")

        assert code == 0, (out, err)
        assert not any(line.startswith("runs_backlink.") for line in _lines(out)), out


def test_criterion_row_principle_id_not_in_principles_doc_reported():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        helpers.write_jsonl(root / "ops" / "runs.jsonl", [
            helpers.make_runs_row_criterion(run_id="chk-P999-20260814-1", principle_id="P999"),
        ])

        code, out, err = helpers.run_script(root, "trace_check.py")

        assert code == 1, (out, err)
        assert any(
            line.startswith("runs_backlink.principle_missing:") and "P999" in line
            for line in _lines(out)
        ), out


def test_criterion_row_registry_query_null_reports_unwired():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        _fix_method_criterion_cmd(root)
        _set_config_key(root, "registry_query", None)
        helpers.write_jsonl(root / "ops" / "runs.jsonl", [
            helpers.make_runs_row_criterion(run_id="chk-P001-20260814-1", principle_id="P001"),
        ])

        code, out, err = helpers.run_script(root, "trace_check.py")

        assert code == 1, (out, err)
        assert any(line.startswith("unwired:") for line in _lines(out)), out


# ---------------------------------------------------------------------------
# 3. cross-archive reads
# ---------------------------------------------------------------------------


def test_cross_archive_referenced_run_only_in_archive_not_reported_broken():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        _write_spec(root, ".scratch/demo/spec.md", "IT-001", approved=True)
        _write_issue(root, ".scratch/demo/issues", "01-example")
        _write_launch_order(root, run_id="run-001", quick=False, spec_ref="IT-001",
                             issue_ref="01-example", decision_refs=[])

        runmeta_rel = "ops/runs/run-001/RUNMETA.json"
        _write_runmeta(root, runmeta_rel, "run-001")
        # This run row lives ONLY in runs.archive.jsonl -- never written to
        # the live runs.jsonl main file. Every read in trace_check.py must
        # go through include_archive=True (spec §2.1) to see it at all.
        helpers.write_jsonl(root / "ops" / "runs.archive.jsonl", [
            helpers.make_runs_row_normal(run_id="run-001", runmeta_path=runmeta_rel, quick=False),
        ])
        helpers.write_jsonl(root / "ops" / "story.jsonl", [
            helpers.make_story_row(claim_id="S001", evidence_runs=["run-001"],
                                    baseline_runs=["run-001"], candidate_runs=["run-001"],
                                    status="active"),
        ])

        code, out, err = helpers.run_script(root, "trace_check.py")

        assert code == 0, (out, err)
        assert _lines(out)[-1] == "trace_check: 0 errors, 0 warnings"


# ---------------------------------------------------------------------------
# 4. Approval face
# ---------------------------------------------------------------------------


def test_approval_stale_on_body_punctuation_change():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        spec_path = _write_spec(root, ".scratch/demo/spec.md", "IT-001", approved=True)
        _touch_spec_body(spec_path)
        _write_issue(root, ".scratch/demo/issues", "01-example")
        _write_launch_order(root, run_id="run-001", quick=False, spec_ref="IT-001",
                             issue_ref="01-example", decision_refs=[])

        code, out, err = helpers.run_script(root, "trace_check.py")

        assert code == 1, (out, err)
        assert any(
            line.startswith("approval_stale:") and "run-001" in line for line in _lines(out)
        ), out


def test_approval_not_stale_on_withdrawals_or_spec_version_bump():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        spec_a = _write_spec(root, ".scratch/demo-a/spec.md", "IT-001", approved=True)
        _bump_spec_header(spec_a, withdrawals=[{"date": "2026-08-14", "by": "user", "reason": "n/a"}])
        spec_b = _write_spec(root, ".scratch/demo-b/spec.md", "IT-002", approved=True)
        _bump_spec_header(spec_b, spec_version=2)
        _write_issue(root, ".scratch/demo/issues", "01-example")
        _write_launch_order(root, run_id="run-001", quick=False, spec_ref="IT-001",
                             issue_ref="01-example", decision_refs=[])
        _write_launch_order(root, run_id="run-002", quick=False, spec_ref="IT-002",
                             issue_ref="01-example", decision_refs=[])

        code, out, err = helpers.run_script(root, "trace_check.py")

        assert code == 0, (out, err)
        assert not any(line.startswith("approval_stale:") for line in _lines(out)), out


def test_spec_ref_without_frontmatter_reported_as_not_found():
    # F1 (sdd/final-review.md): _lib.find_spec_files requires valid
    # frontmatter as part of "found" -- a file that merely contains the
    # item_id string, with no frontmatter at all, is no longer a candidate
    # to either check. check_forward_chain now reports it exactly as if no
    # file mentioned the id at all; check_approval's old "found by check 1
    # but fails to parse" finding (approval.spec_unreadable) no longer
    # exists -- there is nothing left for it to catch that check_forward_
    # chain hasn't already reported.
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        spec_path = root / ".scratch" / "demo" / "spec.md"
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text("# spec\n\nItem IT-001 does something, no frontmatter here.\n",
                              encoding="utf-8")
        _write_issue(root, ".scratch/demo/issues", "01-example")
        _write_launch_order(root, run_id="run-001", quick=False, spec_ref="IT-001",
                             issue_ref="01-example", decision_refs=[])

        code, out, err = helpers.run_script(root, "trace_check.py")

        assert code == 1, (out, err)
        lines = _lines(out)
        assert any(
            line.startswith("forward_chain.spec_ref:") and "IT-001" in line for line in lines
        ), out
        assert not any(line.startswith("approval.spec_unreadable:") for line in lines), out
        assert not any(line.startswith("not-approved:") for line in lines), out


def test_spec_ref_resolves_past_a_non_frontmatter_issue_file_mentioning_the_same_id():
    # F1 false-red repro: a real issue ticket legitimately references its
    # spec item's id (issue_min's own "spec_item(回指 item_id)" convention),
    # lives under the same .scratch/ tree the specs ledger scans, has no
    # frontmatter, and sorts ahead of the real spec.md ("issues/01-demo.md"
    # < "spec.md"). The old substring-only search (no frontmatter check
    # during the scan itself) picked the issue file as "the" spec file and
    # then failed to parse it -- approval.spec_unreadable, even though a
    # perfectly valid, approved spec.md sat right next to it. Rerun this
    # exact fixture against the pre-fix code (git stash the trace_check.py/
    # _lib.py changes) and it reports that finding; against the fix, it's
    # clean.
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        spec_path = _write_spec(root, ".scratch/demo/spec.md", "IT-001", approved=True)
        issue_path = root / ".scratch" / "demo" / "issues" / "01-demo.md"
        issue_path.parent.mkdir(parents=True, exist_ok=True)
        issue_path.write_text(
            "# 01-demo\n\nStatus: ready-for-agent\n\nspec_item: IT-001\n", encoding="utf-8",
        )
        _write_launch_order(root, run_id="run-001", quick=False, spec_ref="IT-001",
                             issue_ref="01-demo", decision_refs=[])

        code, out, err = helpers.run_script(root, "trace_check.py")

        assert code == 0, (out, err)
        assert "trace_check: 0 errors" in out


def test_approval_empty_approved_by_reports_not_approved():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        _write_spec(root, ".scratch/demo/spec.md", "IT-001", approved=False)
        _write_issue(root, ".scratch/demo/issues", "01-example")
        _write_launch_order(root, run_id="run-001", quick=False, spec_ref="IT-001",
                             issue_ref="01-example", decision_refs=[])

        code, out, err = helpers.run_script(root, "trace_check.py")

        assert code == 1, (out, err)
        assert any(
            line.startswith("not-approved:") and "run-001" in line for line in _lines(out)
        ), out


# ---------------------------------------------------------------------------
# 5. affects consistency
# ---------------------------------------------------------------------------


def test_affects_missing_reported_with_rerun_guidance():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        helpers.write_jsonl(root / "ops" / "decisions.jsonl", [
            helpers.make_decision_row(decision_id="D001", affects=[]),
        ])
        _write_spec(root, ".scratch/demo/spec.md", "IT-001", approved=True)
        _write_issue(root, ".scratch/demo/issues", "01-example")
        _write_launch_order(root, run_id="run-001", quick=False, spec_ref="IT-001",
                             issue_ref="01-example", decision_refs=["D001"])

        code, out, err = helpers.run_script(root, "trace_check.py")

        assert code == 1, (out, err)
        matches = [line for line in _lines(out) if line.startswith("affects-missing:")]
        assert matches, out
        assert "D001" in matches[0] and "run-001" in matches[0]
        assert "re-run" in matches[0] and "launch-order" in matches[0]


def test_affects_extra_reported():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        helpers.write_jsonl(root / "ops" / "decisions.jsonl", [
            helpers.make_decision_row(decision_id="D001", affects=["run-001"]),
        ])
        _write_spec(root, ".scratch/demo/spec.md", "IT-001", approved=True)
        _write_issue(root, ".scratch/demo/issues", "01-example")
        _write_launch_order(root, run_id="run-001", quick=False, spec_ref="IT-001",
                             issue_ref="01-example", decision_refs=[])

        code, out, err = helpers.run_script(root, "trace_check.py")

        assert code == 1, (out, err)
        assert any(
            line.startswith("affects-extra:") and "D001" in line and "run-001" in line
            for line in _lines(out)
        ), out


# ---------------------------------------------------------------------------
# 6. story references
# ---------------------------------------------------------------------------


def test_story_refs_broken_run_reference_reported():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        helpers.write_jsonl(root / "ops" / "story.jsonl", [
            helpers.make_story_row(claim_id="S001", evidence_runs=["run-ghost"],
                                    baseline_runs=["run-ghost"], candidate_runs=["run-ghost"],
                                    status="active"),
        ])

        code, out, err = helpers.run_script(root, "trace_check.py")

        assert code == 1, (out, err)
        assert any(
            line.startswith("story_refs:") and "run-ghost" in line for line in _lines(out)
        ), out


def test_story_refs_quick_run_reference_reported():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        helpers.write_jsonl(root / "ops" / "runs.jsonl", [
            helpers.make_runs_row_normal(run_id="run-quick", quick=True),
        ])
        helpers.write_jsonl(root / "ops" / "story.jsonl", [
            helpers.make_story_row(claim_id="S001", evidence_runs=["run-quick"],
                                    baseline_runs=["run-quick"], candidate_runs=["run-quick"],
                                    status="active"),
        ])

        code, out, err = helpers.run_script(root, "trace_check.py")

        assert code == 1, (out, err)
        assert any(
            line.startswith("story_refs:") and "run-quick" in line for line in _lines(out)
        ), out


# ---------------------------------------------------------------------------
# 7. promoted_from field drift
# ---------------------------------------------------------------------------


def test_promotion_field_drift_names_seed():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        _write_spec(root, ".scratch/demo/spec.md", "IT-001", approved=True)
        _write_issue(root, ".scratch/demo/issues", "01-example")
        _write_launch_order(root, run_id="quick-20260814-1", quick=True, seed=0,
                             spec_ref=None, issue_ref=None, decision_refs=None)
        _write_launch_order(root, run_id="run-001", quick=False, seed=1,
                             promoted_from="quick-20260814-1", spec_ref="IT-001",
                             issue_ref="01-example", decision_refs=[])

        code, out, err = helpers.run_script(root, "trace_check.py")

        assert code == 1, (out, err)
        matches = [line for line in _lines(out) if line.startswith("promotion-field-drift:")]
        assert matches, out
        assert "run-001" in matches[0] and "seed" in matches[0]


def test_promotion_all_fields_match_is_clean():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        _write_spec(root, ".scratch/demo/spec.md", "IT-001", approved=True)
        _write_issue(root, ".scratch/demo/issues", "01-example")
        _write_launch_order(root, run_id="quick-20260814-1", quick=True,
                             spec_ref=None, issue_ref=None, decision_refs=None)
        _write_launch_order(root, run_id="run-001", quick=False,
                             promoted_from="quick-20260814-1", spec_ref="IT-001",
                             issue_ref="01-example", decision_refs=[])

        code, out, err = helpers.run_script(root, "trace_check.py")

        assert code == 0, (out, err)
        assert not any(line.startswith("promotion-field-drift:") for line in _lines(out)), out


# ---------------------------------------------------------------------------
# 8. --closeout batch gate
# ---------------------------------------------------------------------------


def test_closeout_empty_inspection_report_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        _write_batch_report(root, "IT-001-20260814-1", run_ids=[], inspection_report="")

        code, out, err = helpers.run_script(root, "trace_check.py", "--closeout", "IT-001-20260814-1")

        assert code == 1, (out, err)
        assert any(
            line.startswith("closeout.inspection_report_empty:") for line in _lines(out)
        ), out


def test_closeout_filled_inspection_report_passes():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        _write_spec(root, ".scratch/demo/spec.md", "IT-001", approved=True)
        _write_issue(root, ".scratch/demo/issues", "01-example")
        _write_launch_order(root, run_id="run-001", quick=False, spec_ref="IT-001",
                             issue_ref="01-example", decision_refs=[])
        runmeta_rel = "ops/runs/run-001/RUNMETA.json"
        _write_runmeta(root, runmeta_rel, "run-001")
        helpers.write_jsonl(root / "ops" / "runs.jsonl", [
            helpers.make_runs_row_normal(run_id="run-001", runmeta_path=runmeta_rel, quick=False),
        ])
        (root / "reports" / "IT-001-20260814-1.md").write_text("inspection body\n", encoding="utf-8")
        _write_batch_report(root, "IT-001-20260814-1", run_ids=["run-001"],
                             inspection_report="reports/IT-001-20260814-1.md")

        code, out, err = helpers.run_script(root, "trace_check.py", "--closeout", "IT-001-20260814-1")

        assert code == 0, (out, err)
        assert _lines(out)[-1] == "trace_check: 0 errors, 0 warnings"


def test_normal_mode_empty_inspection_report_not_reported():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        _write_batch_report(root, "IT-001-20260814-1", run_ids=[], inspection_report="")

        code, out, err = helpers.run_script(root, "trace_check.py")

        assert code == 0, (out, err)
        assert not any(line.startswith("closeout.") for line in _lines(out)), out


def test_closeout_missing_report_reported():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)

        code, out, err = helpers.run_script(root, "trace_check.py", "--closeout", "no-such-batch")

        assert code == 1, (out, err)
        assert any(line.startswith("closeout.report_missing:") for line in _lines(out)), out


def test_closeout_run_id_not_recorded_reported():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        (root / "reports" / "r.md").write_text("body\n", encoding="utf-8")
        _write_batch_report(root, "IT-001-20260814-1", run_ids=["run-ghost"],
                             inspection_report="reports/r.md")

        code, out, err = helpers.run_script(root, "trace_check.py", "--closeout", "IT-001-20260814-1")

        assert code == 1, (out, err)
        assert any(
            line.startswith("closeout.run_id_unrecorded:") and "run-ghost" in line
            for line in _lines(out)
        ), out


# ---------------------------------------------------------------------------
# All-green fixture: exit 0, summary line reads exactly "0 errors"
# ---------------------------------------------------------------------------


def test_all_green_fixture_exits_zero_with_zero_errors():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        _fix_method_criterion_cmd(root)

        _write_spec(root, ".scratch/demo/spec.md", "IT-001", approved=True)
        _write_issue(root, ".scratch/demo/issues", "01-example")
        helpers.write_jsonl(root / "ops" / "decisions.jsonl", [
            helpers.make_decision_row(decision_id="D001", affects=["run-001"]),
        ])

        _write_launch_order(root, run_id="quick-20260814-1", quick=True,
                             spec_ref=None, issue_ref=None, decision_refs=None)
        _write_launch_order(root, run_id="run-001", quick=False, spec_ref="IT-001",
                             issue_ref="01-example", decision_refs=["D001"],
                             promoted_from="quick-20260814-1")

        runmeta_rel = "ops/runs/run-001/RUNMETA.json"
        _write_runmeta(root, runmeta_rel, "run-001")
        helpers.write_jsonl(root / "ops" / "runs.jsonl", [
            helpers.make_runs_row_normal(run_id="run-001", runmeta_path=runmeta_rel, quick=False),
            helpers.make_runs_row_criterion(run_id="chk-P001-20260814-1", principle_id="P001"),
        ])

        _write_jobs(root, {"run-001": {"launch_order_ref": "run-001", "state": "done"}})

        helpers.write_jsonl(root / "ops" / "story.jsonl", [
            helpers.make_story_row(claim_id="S001", evidence_runs=["run-001"],
                                    baseline_runs=["run-001"], candidate_runs=["run-001"],
                                    principle_id="P001", status="active"),
        ])

        code, out, err = helpers.run_script(root, "trace_check.py")

        assert code == 0, (out, err)
        assert _lines(out) == ["trace_check: 0 errors, 0 warnings"], out


# ---------------------------------------------------------------------------
# F2 (sdd/final-review.md): an explicit --project-root with no
# research-loop.json under it must refuse outright, not silently read as an
# empty (so falsely "clean") project.
# ---------------------------------------------------------------------------


def test_project_root_explicit_wrong_path_exits_2_not_false_clean():
    with tempfile.TemporaryDirectory() as tmp_wrong, tempfile.TemporaryDirectory() as tmp_real:
        # a genuine broken chain in the real project -- normally 1 error.
        root = helpers.make_sandbox(tmp_real)
        _write_launch_order(root, run_id="run-001", quick=False, spec_ref="NOPE-1",
                             issue_ref=None, decision_refs=None)

        wrong_root = Path(tmp_wrong)  # exists on disk, but no research-loop.json

        code, out, err = helpers.run_script(root, "trace_check.py", "--project-root", str(wrong_root))

        assert code == 2, (out, err)
        assert "research-loop.json" in err
        assert out == ""  # never got far enough to print a false "0 errors"


def test_spec_ref_ambiguous_across_two_frontmatter_specs_reported():
    # trace_check's own side of the find_spec_files ambiguity contract
    # (launchcmd's side already has a test): two parseable specs both
    # containing the item id must be reported, never silently first-picked.
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_sandbox(tmp)
        _write_spec(root, ".scratch/demo/spec.md", "IT-001", approved=True)
        _write_spec(root, ".scratch/other/spec.md", "IT-001", approved=True)
        _write_launch_order(root, run_id="run-001", quick=False, spec_ref="IT-001",
                            decision_refs=[])

        code, out, err = helpers.run_script(root, "trace_check.py")

        assert code == 1, (out, err)
        assert "forward_chain.spec_ref" in out
        assert "ambiguous across 2 files" in out
