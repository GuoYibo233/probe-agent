"""Nine-scenario fake-rails self-test (issues/16-e2e.md; spec.md §9 "plugin
自测（假铁轨）", §8 steps 3-10). Each `test_<N>_...` function below is one of
spec §9's nine numbered scenarios, in the same order, walking the real
fallback trio (scripts/fallback/{launch,record,registry}.py) plus the two
fake tasks (fake-experiment/fake-metrics) through the mechanical chain a real
project's rails.gpu/registry/record_cmd would drive -- no GPU, no external
service, everything inside a helpers.make_rails_sandbox() sandbox.

Every sandbox is fresh per test (a `with tempfile.TemporaryDirectory()`
block) -- scenarios do not share state, even where spec §9's prose describes
one scenario as built "on top of" another (③ says as much about ②); this
file instead has each scenario construct its own copy of whatever earlier
state it needs, so `run_all.py` can run these in any order and a failure in
one scenario never cascades into a false failure in another.
"""
from __future__ import annotations

import json
import shlex
import tempfile
from pathlib import Path

import _lib
import helpers


# ---------------------------------------------------------------------------
# Shared small tools (issue 16's own "共用小工具" -- implemented in this file,
# not helpers.py, since they build on the fake-rails registry/fake-experiment
# shape that only this file's scenarios need).
# ---------------------------------------------------------------------------


def _registry_prefix(root) -> list:
    cfg = _lib.load_config(root)
    return _lib.split_cmd(cfg.get("registry_cmd"), "test", "registry_cmd")


def _draft_dict(root, run_id, mode, quick, **over) -> dict:
    """Build a launch_order draft per issue 16's mk_order recipe: argv/
    metrics_cmd default to driving fake-experiment/fake-metrics via the
    sandbox's real registry_cmd, seed fixed at 7, dataset_version "d1",
    arm 实验组, batch_id named per §2.6. Any field (argv/metrics_cmd
    included, for scenario ③'s byte-for-byte promotion reuse) can be
    overridden via `over`."""
    seed = over.pop("seed", 7)
    artifact_dir = over.pop("artifact_dir", f"ops/runs/{run_id}")
    spec_ref = over.pop("spec_ref", None)
    issue_ref = over.pop("issue_ref", None)
    decision_refs = over.pop("decision_refs", None)
    promoted_from = over.pop("promoted_from", None)
    filter_ = over.pop("filter", None)
    dataset_version = over.pop("dataset_version", "d1")
    batch_id = over.pop("batch_id", None)
    expected_commit = over.pop("expected_commit", None) or _lib.git_head(root)

    prefix = _registry_prefix(root)
    argv = over.pop("argv", None)
    if argv is None:
        argv = prefix + [
            "fake-experiment", "--seed", str(seed), "--mode", mode, "--out", artifact_dir,
        ]
    metrics_cmd = over.pop("metrics_cmd", None)
    if metrics_cmd is None:
        metrics_argv = prefix + ["fake-metrics", "--dir", artifact_dir]
        metrics_cmd = " ".join(shlex.quote(a) for a in metrics_argv)

    if batch_id is None:
        date = _lib.today().replace("-", "")
        batch_id = f"quick-{date}-1" if quick else f"{spec_ref or 'IT-001'}-{date}-1"

    draft = {
        "run_id": run_id,
        "spec_ref": spec_ref,
        "issue_ref": issue_ref,
        "decision_refs": decision_refs,
        "batch_id": batch_id,
        "promoted_from": promoted_from,
        "registry_task": "fake-experiment",
        "argv": argv,
        "env_name": "default",
        "workdir": ".",
        "expected_commit": expected_commit,
        "seed": seed,
        "dataset_version": dataset_version,
        "arm": "实验组",
        "filter": filter_,
        "quick": quick,
        "resources": {"gpus": 1, "min_vram_gb": 8, "exclusive": False},
        "expected_runtime_s": 60,
        "expected_outputs": [{"path_glob": "result.jsonl", "min_bytes": 1}],
        "metrics_cmd": metrics_cmd,
        "artifact_dir": artifact_dir,
        "created_by": "deploy",
        "created_at": _lib.now_iso(),
    }
    draft.update(over)
    return draft


def mk_order(root, run_id, mode, quick, **over) -> Path:
    """_draft_dict() -> write the draft under ops/_drafts/ (gitignored, so
    it never trips launch.py's dirty-tree gate) -> `ledger.py launch-order`
    -> the written launch order's own path (ops/launch_orders/<run_id>.json).
    Asserts the write succeeds; scenario ⑦'s negative case builds its draft
    directly with _draft_dict() instead of going through this helper."""
    draft = _draft_dict(root, run_id, mode, quick, **over)
    draft_path = root / "ops" / "_drafts" / f"{run_id}.json"
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
    code, out, err = helpers.run_ledger(
        root, "launch-order", "--layer", "deploy", "--file", str(draft_path)
    )
    assert code == 0, (out, err)
    return _lib.load_config(root).ledger_path("launch_orders") / f"{run_id}.json"


def _run_launch(root, order_path):
    return helpers.run_script(root, "fallback/launch.py", str(order_path))


def _run_record(root, order_path, *extra):
    return helpers.run_script(root, "fallback/record.py", "--launch-order", str(order_path), *extra)


def _run_output_check(root, order_path):
    return helpers.run_script(root, "output_check.py", "--launch-order", str(order_path))


def _run_trace_check(root, *extra):
    return helpers.run_script(root, "trace_check.py", *extra)


def _runs_rows(root, run_id=None) -> list:
    rows = _lib.jsonl_rows(_lib.load_config(root).ledger_path("runs"))
    if run_id is not None:
        rows = [r for r in rows if r["run_id"] == run_id]
    return rows


def _blocked_rows(root) -> list:
    return _lib.jsonl_rows(_lib.load_config(root).ledger_path("blocked"))


def _decisions_rows(root) -> list:
    return _lib.jsonl_rows(_lib.load_config(root).ledger_path("decisions"))


def _story_add(root, *, claim, evidence_runs, baseline_runs="", candidate_runs="",
                principle_id="P001", role="主结果", metric_names=None):
    args = [
        "story", "add", "--layer", "idea",
        "--claim", claim,
        "--evidence-runs", evidence_runs,
        "--baseline-runs", baseline_runs,
        "--candidate-runs", candidate_runs,
        "--selection-rule", "single fake run, no selection needed",
        "--derivation-command",
        "python3 research-loop/scripts/fallback/registry.py fake-metrics --dir <artifact_dir>",
        "--principle-id", principle_id,
        "--role", role,
    ]
    if metric_names is not None:
        args += ["--metric-names", metric_names]
    return helpers.run_ledger(root, *args)


def _open_r5(root, *, ref, where="which arm", options=("A", "B"), layer="run", to_layer="deploy"):
    return helpers.run_ledger(
        root, "blocked", "open", "--layer", layer, "--to-layer", to_layer,
        "--kind", "r5-choice", "--ref", ref, "--question", "which arm should we use?",
        "--evidence", "ops/evidence.txt", "--where", where, "--options", *options,
    )


def _write_batch_report(root, batch_id, *, run_ids, spec_items=None, inspection_report="") -> Path:
    fields = {
        "batch_id": batch_id,
        "spec_items": spec_items or [],
        "run_ids": run_ids,
        "date": _lib.today(),
        "how_to_read": "ledger.py query runs --batch " + batch_id,
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
    path = root / "plans" / f"{batch_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _set_inspection_report(path, inspection_report_rel) -> None:
    fields, body = _lib.parse_frontmatter(path.read_text(encoding="utf-8"))
    fields["inspection_report"] = inspection_report_rel
    lines = ["---\n"]
    for key, value in fields.items():
        lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}\n")
    lines.append("---\n")
    path.write_text("".join(lines) + body, encoding="utf-8")


def _write_clean_inspection_report(root, batch_id, run_ids) -> Path:
    """A clean (verdict=clean) core-check report written in the style
    evidence_lint.py's own two rules would require -- T13, not a T16
    dependency and not invoked here, so this is descriptive compliance, not
    a machine-checked one: no banned-conclusion prose in the body, and its
    one numeric claim (the runs ledger's row count) is followed within 3
    lines by a real `$ ` repro command and its echoed `= ` output."""
    runs_path = _lib.load_config(root).ledger_path("runs")
    n_rows = len(_lib.jsonl_rows(runs_path))
    fields = {"batch_id": batch_id, "verdict": "clean", "blockers": [], "date": _lib.today()}
    lines = ["---"]
    for key, value in fields.items():
        lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    lines.append("---")
    lines.append("")
    lines.append(f"# inspection report {batch_id}")
    lines.append("")
    lines.append(f"generated_at: {_lib.now_iso()}")
    lines.append(f"git_head: {_lib.git_head(root)}")
    lines.append(f"runs ledger row count: {n_rows}")
    lines.append(f"$ wc -l {runs_path.relative_to(root)}")
    lines.append(f"= {n_rows} {runs_path.relative_to(root)}")
    lines.append("")
    lines.append(f"Ran trace_check and evidence_lint over run_ids {run_ids}; no blockers found.")
    lines.append("")
    path = root / "reports" / f"inspection-{batch_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# ① 正轨闭环
# ---------------------------------------------------------------------------


def test_1_clean_loop_reaches_closeout():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_rails_sandbox(tmp)

        order_path = mk_order(
            root, "run-clean", mode="ok", quick=False,
            spec_ref="IT-001", issue_ref="01-demo", decision_refs=["D001"],
        )
        order = json.loads(order_path.read_text(encoding="utf-8"))
        batch_id = order["batch_id"]

        code, out, err = _run_launch(root, order_path)
        assert code == 0, (out, err)

        code, out, err = _run_output_check(root, order_path)
        assert code == 0, (out, err)
        assert json.loads(out)["verdict"] == "ok"

        code, out, err = _run_record(root, order_path)
        assert code == 0, (out, err)
        run_rows = _runs_rows(root, "run-clean")
        assert len(run_rows) == 2
        assert {r["metric_name"] for r in run_rows} == {"acc", "rows"}
        assert all(r["status"] == "ok" for r in run_rows)

        report_path = _write_batch_report(
            root, batch_id, run_ids=["run-clean"], spec_items=["IT-001"],
        )
        fields, _body = _lib.parse_frontmatter(report_path.read_text(encoding="utf-8"))
        assert fields["inspection_report"] == ""  # "inspection_report 先空"

        inspection_path = _write_clean_inspection_report(root, batch_id, ["run-clean"])
        insp_fields, _body = _lib.parse_frontmatter(inspection_path.read_text(encoding="utf-8"))
        assert insp_fields["verdict"] == "clean"

        inspection_rel = f"reports/inspection-{batch_id}.md"
        _set_inspection_report(report_path, inspection_rel)
        fields, _body = _lib.parse_frontmatter(report_path.read_text(encoding="utf-8"))
        assert fields["inspection_report"] == inspection_rel

        code, out, err = _story_add(
            root, claim="the fake experiment produces a stable acc metric",
            evidence_runs="run-clean", candidate_runs="run-clean",
        )
        assert code == 0, (out, err)

        code, out, err = _run_trace_check(root, "--closeout", batch_id)
        assert code == 0, (out, err)
        assert "trace_check: 0 errors" in out


# ---------------------------------------------------------------------------
# ② 快车道
# ---------------------------------------------------------------------------


def test_2_quick_lane_skips_refs_and_blocks_story():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_rails_sandbox(tmp)
        order_path = mk_order(root, "run-quick", mode="ok", quick=True)
        order = json.loads(order_path.read_text(encoding="utf-8"))
        assert order["spec_ref"] is None
        assert order["issue_ref"] is None
        assert order["decision_refs"] is None

        code, out, err = _run_launch(root, order_path)
        assert code == 0, (out, err)
        code, out, err = _run_record(root, order_path)
        assert code == 0, (out, err)

        rows = _runs_rows(root, "run-quick")
        assert len(rows) == 2
        assert all(r["quick"] is True for r in rows)

        code, out, err = _story_add(
            root, claim="quick try looks promising",
            evidence_runs="run-quick", candidate_runs="run-quick",
        )
        assert code == 2
        assert "quick runs cannot enter the story ledger" in err

        code, out, err = _run_trace_check(root)
        # never reports a broken chain for a quick order
        assert "forward_chain" not in out, (out, err)
        assert code == 0, (out, err)


# ---------------------------------------------------------------------------
# ③ 转正重跑
# ---------------------------------------------------------------------------


def test_3_promote_quick_to_full_reruns_byte_identical_argv():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_rails_sandbox(tmp)

        quick_path = mk_order(root, "run-quick-base", mode="ok", quick=True)
        quick_order = json.loads(quick_path.read_text(encoding="utf-8"))
        code, out, err = _run_launch(root, quick_path)
        assert code == 0, (out, err)
        code, out, err = _run_record(root, quick_path)
        assert code == 0, (out, err)

        # promoted_from=<quick run_id>; seed/dataset_version/argv/env_name/
        # filter carried over byte for byte (trace_check.check_promotion
        # compares these five as one group) -- argv (and, since it isn't one
        # of the five, metrics_cmd too, to keep reading the same bytes) keep
        # pointing at the quick run's own artifact_dir; the launch order's
        # own artifact_dir field is what distinguishes the two runs'
        # RUNMETA/job bookkeeping (issue 16's own "产物目录用 artifact_dir
        # 字段区分即可，argv 里 --out 也保持逐字").
        promoted_path = mk_order(
            root, "run-promoted", mode="ok", quick=False,
            spec_ref="IT-001", issue_ref="01-demo", decision_refs=["D001"],
            promoted_from="run-quick-base",
            seed=quick_order["seed"], dataset_version=quick_order["dataset_version"],
            argv=quick_order["argv"], metrics_cmd=quick_order["metrics_cmd"],
            filter=quick_order["filter"],
        )

        code, out, err = _run_launch(root, promoted_path)
        assert code == 0, (out, err)
        code, out, err = _run_record(root, promoted_path)
        assert code == 0, (out, err)

        code, out, err = _story_add(
            root, claim="the promoted run confirms the quick try",
            evidence_runs="run-promoted", candidate_runs="run-promoted",
        )
        assert code == 0, (out, err)  # non-quick -> story add is no longer refused

        quick_acc = next(r for r in _runs_rows(root, "run-quick-base") if r["metric_name"] == "acc")
        promoted_rows = _runs_rows(root, "run-promoted")
        promoted_acc = next(r for r in promoted_rows if r["metric_name"] == "acc")
        # byte-identical result.jsonl -> identical value
        assert promoted_acc["value"] == quick_acc["value"]


# ---------------------------------------------------------------------------
# ④ empty 模式
# ---------------------------------------------------------------------------


def _build_scenario4_sandbox(tmp):
    root = helpers.make_rails_sandbox(tmp)
    order_path = mk_order(root, "run-empty", mode="empty", quick=True)
    code, out, err = _run_launch(root, order_path)
    assert code == 0, (out, err)
    oc = _run_output_check(root, order_path)
    code, out, err = _run_record(root, order_path, "--status", "empty-output")
    assert code == 0, (out, err)
    return root, order_path, oc


def test_4_empty_mode_records_null_metrics():
    with tempfile.TemporaryDirectory() as tmp:
        root, _order_path, (oc_code, oc_out, oc_err) = _build_scenario4_sandbox(tmp)

        assert oc_code == 4, (oc_out, oc_err)
        assert json.loads(oc_out)["verdict"] == "empty-output"

        rows = _runs_rows(root, "run-empty")
        assert len(rows) == 1
        row = rows[0]
        assert row["status"] == "empty-output"
        assert row["metric_name"] is None
        assert row["value"] is None
        assert row["n"] is None


# ---------------------------------------------------------------------------
# ⑤ bad-metrics
# ---------------------------------------------------------------------------


def test_5_bad_metrics_opens_blocked_with_evidence():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_rails_sandbox(tmp)
        order_path = mk_order(root, "run-badmetrics", mode="bad-metrics", quick=True)
        order = json.loads(order_path.read_text(encoding="utf-8"))

        code, out, err = _run_launch(root, order_path)
        assert code == 0, (out, err)

        code, out, err = _run_record(root, order_path)
        assert code == 2, (out, err)
        assert "no row recorded" in err
        assert _runs_rows(root, "run-badmetrics") == []

        log_path = root / order["artifact_dir"] / "attempt1.log"
        assert log_path.exists()

        before = len(_blocked_rows(root))
        code, out, err = helpers.run_ledger(
            root, "blocked", "open", "--layer", "run", "--to-layer", "deploy",
            "--kind", "failure", "--ref", "run-badmetrics",
            "--question",
            "record.py refused run-badmetrics's metrics output; how should this proceed?",
            "--evidence", str(log_path), "tried: reran record once",
        )
        assert code == 0, (out, err)

        rows = _blocked_rows(root)
        assert len(rows) == before + 1
        new_row = next(r for r in rows if r["ref"] == "run-badmetrics")
        assert new_row["kind"] == "failure"
        assert str(log_path) in new_row["evidence"]


# ---------------------------------------------------------------------------
# ⑥ fail 后重试 ok
# ---------------------------------------------------------------------------


def test_6_fail_then_retry_ok_preserves_first_attempt():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_rails_sandbox(tmp)
        order_path = mk_order(root, "run-fail-then-ok", mode="fail", quick=True)
        order = json.loads(order_path.read_text(encoding="utf-8"))

        code, out, err = _run_launch(root, order_path)
        assert code != 0, (out, err)

        attempt1_log = root / order["artifact_dir"] / "attempt1.log"
        attempt1_text_before_retry = attempt1_log.read_text(encoding="utf-8")
        assert "simulated failure" in attempt1_text_before_retry

        # "同 run_id 重写发射单（argv 的 --mode 改 ok；重写同路径幂等）"
        order_path_2 = mk_order(root, "run-fail-then-ok", mode="ok", quick=True)
        assert order_path_2 == order_path

        code, out, err = _run_launch(root, order_path)
        assert code == 0, (out, err)  # attempt 2

        code, out, err = _run_record(root, order_path)
        assert code == 0, (out, err)

        rows = _runs_rows(root, "run-fail-then-ok")
        assert len(rows) == 2  # acc + rows, one row-group, all status=ok
        assert all(r["status"] == "ok" for r in rows)

        runmeta_path = root / order["artifact_dir"] / "RUNMETA.json"
        runmeta = json.loads(runmeta_path.read_text(encoding="utf-8"))
        assert len(runmeta["attempts"]) == 2
        assert "fail" in runmeta["attempts"][0]["argv"]
        # not overwritten
        assert attempt1_log.read_text(encoding="utf-8") == attempt1_text_before_retry


# ---------------------------------------------------------------------------
# ⑦ 批准失效
# ---------------------------------------------------------------------------


def test_7_approval_invalidated_by_body_edit_rejects_new_order():
    with tempfile.TemporaryDirectory() as tmp:
        root = helpers.make_rails_sandbox(tmp)
        spec_path = root / ".scratch" / "demo" / "spec.md"
        spec_path.write_text(spec_path.read_text(encoding="utf-8") + "!", encoding="utf-8")

        draft = _draft_dict(
            root, "run-stale", mode="ok", quick=False,
            spec_ref="IT-001", issue_ref="01-demo", decision_refs=["D001"],
        )
        draft_path = root / "ops" / "_drafts" / "run-stale.json"
        draft_path.parent.mkdir(parents=True, exist_ok=True)
        draft_path.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")

        code, out, err = helpers.run_ledger(
            root, "launch-order", "--layer", "deploy", "--file", str(draft_path)
        )
        assert code == 2
        assert "approval_stale" in err


# ---------------------------------------------------------------------------
# ⑧ 三类半状态收敛 (fixtures per issues/14-doctor.md's own "half-state 三类
# 扫描" wording; doctor.py itself isn't a T16 dependency -- these tests
# directly build the fixture and re-run the suggested recovery command,
# comparing against a same-sandbox-style clean one-shot execution).
# ---------------------------------------------------------------------------


def test_8a_orphan_decision_converges_on_reanswer():
    with tempfile.TemporaryDirectory() as tmp_golden, tempfile.TemporaryDirectory() as tmp_broken:
        # golden: a clean one-shot r5-choice open + answer.
        golden_root = helpers.make_rails_sandbox(tmp_golden)
        code, out, err = _open_r5(golden_root, ref="S-golden")
        assert code == 0, (out, err)
        golden_blocked = json.loads(out.strip())
        code, out, err = helpers.run_ledger(
            golden_root, "blocked", "answer", "--layer", "deploy", golden_blocked["blocked_id"],
            "--answer", "user chose A", "--chosen", "A", "--answered-by", "user",
        )
        assert code == 0, (out, err)
        golden_answered = json.loads(out.strip())
        golden_blocked_rows = _blocked_rows(golden_root)
        golden_decisions_rows = _decisions_rows(golden_root)

        # broken: an orphan decision -- decisions row already decided (with
        # blocked_ref pointing back), but the blocked row is still open, as
        # if the r5-choice assembly's decision append landed and its
        # in-place update to the blocked row never did (writes.json
        # r5_choice_assembly's own crash surface -- same shape as
        # test_blocked_decisions.py's test_answer_r5_converges_after_
        # simulated_partial_write, reused here as T14's "孤儿 decision").
        broken_root = helpers.make_rails_sandbox(tmp_broken)
        code, out, err = _open_r5(broken_root, ref="S-broken")
        assert code == 0, (out, err)
        broken_blocked = json.loads(out.strip())

        decisions_path = _lib.load_config(broken_root).ledger_path("decisions")
        existing = _lib.jsonl_rows(decisions_path)
        orphan_decision = {
            "decision_id": "D002", "kind": "decision", "where": broken_blocked["where"],
            "question": broken_blocked["question"], "options": list(broken_blocked["options"]),
            "chosen": "A", "reason": "user chose A", "authorized_by": "user chose A",
            "scope": None, "principle_ref": None, "affects": ["S-broken"],
            "blocked_ref": broken_blocked["blocked_id"], "decided_by": "user",
            "raised_at": broken_blocked["raised_at"], "decided_at": _lib.now_iso(),
            "status": "decided", "superseded_by": None, "withdrawn_by": None,
            "withdrawn_reason": None, "schema_version": 1,
        }
        helpers.write_jsonl(decisions_path, existing + [orphan_decision])

        # doctor's own suggested fix text: "re-run: ledger.py blocked answer <BID> ..."
        code, out, err = helpers.run_ledger(
            broken_root, "blocked", "answer", "--layer", "deploy", broken_blocked["blocked_id"],
            "--answer", "user chose A", "--chosen", "A", "--answered-by", "user",
        )
        assert code == 0, (out, err)
        recovered_answered = json.loads(out.strip())
        recovered_blocked_rows = _blocked_rows(broken_root)
        recovered_decisions_rows = _decisions_rows(broken_root)

        assert len(recovered_blocked_rows) == len(golden_blocked_rows) == 1
        # Both sandboxes start with the fixture's own D001 already on the
        # decisions ledger (helpers.make_rails_sandbox) -- compare counts
        # against each other, not a hardcoded literal, and separately pin
        # down that exactly one *new* (non-D001) decision row exists in
        # each, i.e. no duplicate got created by the recovery.
        assert len(recovered_decisions_rows) == len(golden_decisions_rows)
        recovered_new = [r for r in recovered_decisions_rows if r["decision_id"] != "D001"]
        golden_new = [r for r in golden_decisions_rows if r["decision_id"] != "D001"]
        assert len(recovered_new) == 1
        assert len(golden_new) == 1
        assert recovered_answered["status"] == golden_answered["status"] == "answered"
        assert recovered_answered["decision_ref"] == "D002"  # reused the orphan, no second decision
        assert recovered_new[0]["status"] == golden_new[0]["status"] == "decided"
        assert recovered_new[0]["blocked_ref"] == recovered_blocked_rows[0]["blocked_id"]
        assert golden_new[0]["blocked_ref"] == golden_blocked_rows[0]["blocked_id"]
        assert recovered_new[0]["chosen"] == golden_new[0]["chosen"] == "A"


def test_8b_withdraw_interrupted_converges_on_rewithdraw():
    with tempfile.TemporaryDirectory() as tmp_golden, tempfile.TemporaryDirectory() as tmp_broken:
        # golden: a clean one-shot open + answer + withdraw.
        golden_root = helpers.make_rails_sandbox(tmp_golden)
        code, out, err = _open_r5(golden_root, ref="S-golden")
        assert code == 0, (out, err)
        golden_blocked = json.loads(out.strip())
        code, out, err = helpers.run_ledger(
            golden_root, "blocked", "answer", "--layer", "deploy", golden_blocked["blocked_id"],
            "--answer", "user chose A", "--chosen", "A", "--answered-by", "user",
        )
        assert code == 0, (out, err)
        code, out, err = helpers.run_ledger(
            golden_root, "blocked", "withdraw", golden_blocked["blocked_id"],
            "--reason", "changed mind",
        )
        assert code == 0, (out, err)
        golden_blocked_rows = _blocked_rows(golden_root)
        golden_decisions_rows = _decisions_rows(golden_root)

        # broken: withdraw interrupted -- the old row was already flipped to
        # withdrawn (as if writes.json blocked_transitions.withdrawn's step
        # ③ had run), but neither the synced-decision flip (step ①) nor the
        # mechanical reopen (step ②) happened yet -- T14's own OR'd
        # detection ("blocked status=withdrawn 但同步 decision 仍 decided，
        # 或缺 (ref=BID, status=open) 重开条") is satisfied on both counts at
        # once by this one fixture.
        broken_root = helpers.make_rails_sandbox(tmp_broken)
        code, out, err = _open_r5(broken_root, ref="S-broken")
        assert code == 0, (out, err)
        broken_blocked = json.loads(out.strip())
        code, out, err = helpers.run_ledger(
            broken_root, "blocked", "answer", "--layer", "deploy", broken_blocked["blocked_id"],
            "--answer", "user chose A", "--chosen", "A", "--answered-by", "user",
        )
        assert code == 0, (out, err)

        blocked_path = _lib.load_config(broken_root).ledger_path("blocked")
        rows = _lib.jsonl_rows(blocked_path)
        for row in rows:
            if row["blocked_id"] == broken_blocked["blocked_id"]:
                row["status"] = "withdrawn"
                row["answer"] = (row["answer"] or "") + "\n[withdrawn by user: changed mind]"
        helpers.write_jsonl(blocked_path, rows)

        # doctor's own suggested fix text: "re-run: ledger.py blocked withdraw <BID> --reason ..."
        code, out, err = helpers.run_ledger(
            broken_root, "blocked", "withdraw", broken_blocked["blocked_id"],
            "--reason", "changed mind",
        )
        assert code == 0, (out, err)
        recovered_blocked_rows = _blocked_rows(broken_root)
        recovered_decisions_rows = _decisions_rows(broken_root)

        assert len(recovered_blocked_rows) == len(golden_blocked_rows) == 2
        # Both sandboxes start with the fixture's own D001 already on the
        # decisions ledger (helpers.make_rails_sandbox) -- compare counts
        # against each other, not a hardcoded literal, and separately pin
        # down that exactly one *new* (non-D001) decision row exists in
        # each, i.e. no duplicate got created by the recovery.
        assert len(recovered_decisions_rows) == len(golden_decisions_rows)
        recovered_new = [r for r in recovered_decisions_rows if r["decision_id"] != "D001"]
        golden_new = [r for r in golden_decisions_rows if r["decision_id"] != "D001"]
        assert len(recovered_new) == 1
        assert len(golden_new) == 1
        assert recovered_new[0]["status"] == golden_new[0]["status"] == "withdrawn"

        broken_bid = broken_blocked["blocked_id"]
        golden_bid = golden_blocked["blocked_id"]
        old_recovered = next(r for r in recovered_blocked_rows if r["blocked_id"] == broken_bid)
        old_golden = next(r for r in golden_blocked_rows if r["blocked_id"] == golden_bid)
        assert old_recovered["status"] == old_golden["status"] == "withdrawn"

        reopened_recovered = [r for r in recovered_blocked_rows if r["ref"] == broken_bid]
        reopened_golden = [r for r in golden_blocked_rows if r["ref"] == golden_bid]
        assert len(reopened_recovered) == len(reopened_golden) == 1
        assert reopened_recovered[0]["status"] == reopened_golden[0]["status"] == "open"


def test_8c_affects_missing_converges_on_launch_order_rewrite():
    with tempfile.TemporaryDirectory() as tmp_golden, tempfile.TemporaryDirectory() as tmp_broken:
        # golden: a clean mk_order() call backfills decisions.affects normally.
        golden_root = helpers.make_rails_sandbox(tmp_golden)
        mk_order(golden_root, "run-golden-affects", mode="ok", quick=True, decision_refs=["D001"])
        golden_d001 = next(r for r in _decisions_rows(golden_root) if r["decision_id"] == "D001")

        # broken: the launch order is already written directly at its
        # canonical path (裸写, bypassing `ledger.py launch-order`) with
        # decision_refs=["D001"], but D001.affects was never backfilled --
        # a crash between launchcmd.py's two write steps (spec §5's
        # documented ordering: launch order file first, affects backfill
        # second).
        broken_root = helpers.make_rails_sandbox(tmp_broken)
        draft = _draft_dict(
            broken_root, "run-broken-affects", mode="ok", quick=True, decision_refs=["D001"],
        )
        lo_dir = _lib.load_config(broken_root).ledger_path("launch_orders")
        lo_dir.mkdir(parents=True, exist_ok=True)
        lo_path = lo_dir / "run-broken-affects.json"
        lo_path.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")

        broken_before = next(r for r in _decisions_rows(broken_root) if r["decision_id"] == "D001")
        assert broken_before["affects"] == []

        # doctor's own suggested fix text:
        # "re-run: ledger.py launch-order --layer deploy --file <单路径>"
        code, out, err = helpers.run_ledger(
            broken_root, "launch-order", "--layer", "deploy", "--file", str(lo_path),
        )
        assert code == 0, (out, err)
        recovered_d001 = next(r for r in _decisions_rows(broken_root) if r["decision_id"] == "D001")

        assert recovered_d001["affects"] == ["run-broken-affects"]
        assert golden_d001["affects"] == ["run-golden-affects"]
        assert len(recovered_d001["affects"]) == len(golden_d001["affects"]) == 1


# ---------------------------------------------------------------------------
# ⑨ 新会话接手
# ---------------------------------------------------------------------------


def test_9_new_session_status_reflects_disk_truth_alone():
    with tempfile.TemporaryDirectory() as tmp:
        # Reuses scenario ④'s own sandbox recipe (issue 16's own instruction:
        # "拿场景 4 的沙盒断言 unrecorded_runs 或 batches_pending_report 非空
        # 即可") -- a fresh sandbox, no session/conversation state carried
        # over, `status` is the only thing consulted.
        root, order_path, _oc = _build_scenario4_sandbox(tmp)
        batch_id = json.loads(order_path.read_text(encoding="utf-8"))["batch_id"]

        code, out, err = helpers.run_ledger(root, "status", "--layer", "deploy")
        assert code == 0, (out, err)
        view = json.loads(out)  # "输出 JSON 能解析"

        for field in (
            "schema_version", "generated_at", "layer",
            "pending_launch_orders", "running_runs", "unrecorded_runs",
            "batches_pending_report", "batches_pending_inspection",
            "open_blocked", "pending_user_decisions", "active_grants",
            "waiting_on", "inconsistencies",
        ):
            assert field in view

        assert batch_id in view["batches_pending_report"] or view["unrecorded_runs"] != []
