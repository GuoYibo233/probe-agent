"""Test 10: runs account schema (30 L108-118; 03 L98-124).

Original: a launched version missing commit or config is refused, metrics is not
required on it; a finished version with exit_status ok missing metrics is refused;
failed does not require metrics but does get actual_seconds; a metric landing on 0 or
1 at finish opens an anomaly issue to gyb; run list default omits killed rows and old
attempts, --all shows everything.

Added by 30 L112-118: a finished ok version also requires data_path (03 L120, L122);
exceeding anomaly.duration_factor times the estimate at finish also opens an anomaly
issue (08 L75; 12 "watchdog" final paragraph; 21 section 7); `rl run relink` appends a
version changing only handoff_id (03 L100, sync-inbox Q31); started_at/finished_at are
filled by rl and refused on the command line; `run list --decision`/`--line` resolve
through the launch order's decision_refs and line (05 L73).
"""

import json
import unittest

from helpers import Sandbox, make_decision, open_work_order, open_launch_order


class RunsSchema(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    # ---- helpers -----------------------------------------------------------
    def _launch(self):
        dec = make_decision(self.sb)
        wo = open_work_order(self.sb, None, dec)
        launch = open_launch_order(self.sb, None, wo)
        run_sid = self.sb.role_session("run")
        self.sb.rl_ok("handoff", "start", launch, session=run_sid)
        return dec, wo, launch, run_sid

    def _add(self, launch, run_sid, attempt="1", **kw):
        args = ["run", "add", "--handoff", launch, "--attempt", attempt,
                "--commit", kw.get("commit", "abc123"), "--host", kw.get("host", "h1"),
                "--gpus", kw.get("gpus", "0"), "--log", kw.get("log", "/tmp/l"),
                "--tmux", kw.get("tmux", "t1"), "--watch-cmd", kw.get("watch_cmd", "w1")]
        return self.sb.rl_ok(*args, session=run_sid)

    # ---- launched version ---------------------------------------------------
    def test_launched_missing_commit_refused(self):
        """30 L108; 03 L107: a launched version missing commit is refused."""
        _, _, launch, run_sid = self._launch()
        before = self.sb.count("runs")
        r = self.sb.rl("run", "add", "--handoff", launch, "--attempt", "1",
                       "--host", "h", "--gpus", "0", "--log", "/tmp/l", "--tmux", "t",
                       "--watch-cmd", "w", session=run_sid)
        self.assertEqual(r.rc, 2, str(r))
        self.assertEqual(r.kind, "validation")
        self.assertEqual(self.sb.count("runs"), before)

    def test_launched_missing_config_pending(self):
        """30 L108: a launched version missing config is refused -- left undecided.

        `rl run add` has no --config flag (05 L73: config is copied from the launch
        order's attempt, not typed); a launch_order's first attempt already requires a
        complete config at open time (04 L61 open.launch_order_first_attempt; handoffs
        schema attempt.config requires model/params/dataset/split). No documented CLI
        path produces a launched run row with a missing config, so this scenario from
        30 L108 cannot be transcribed without inventing a mechanism.
        """
        self.skipTest("PENDING(part 30 L108): the 'launched version missing config' case has no "
                      "documented CLI path, since `rl run add` copies config from an attempt that "
                      "was complete at open (05 L73; 04 L61)")

    def test_launched_version_does_not_require_metrics(self):
        """30 L108 (03 L119): metrics is required only when exit_status is ok, not on the launched version."""
        _, _, launch, run_sid = self._launch()
        run_id = f"{launch}-a1"
        self._add(launch, run_sid)
        row = self.sb.latest("runs", run_id)
        self.assertEqual(row["status"], "launched")
        self.assertFalse(row.get("metrics"))
        # 30 L114 second half: the launched version has no artifact_dir column (the
        # artifact directory follows the <artifact_root>/<run_id>/ convention instead).
        self.assertNotIn("artifact_dir", row)

    # ---- finished version -----------------------------------------------------
    def test_finished_ok_missing_metrics_refused(self):
        """30 L108 (03 L119): a finished ok version missing metrics is refused."""
        _, _, launch, run_sid = self._launch()
        run_id = f"{launch}-a1"
        self._add(launch, run_sid)
        path = self.sb.write_file(f"artifacts/{run_id}/metrics.json")
        before = self.sb.latest("runs", run_id)
        r = self.sb.rl("run", "finish", run_id, "--exit", "ok",
                       "--data-path", str(path.relative_to(self.sb.root)), session=run_sid)
        self.assertEqual(r.rc, 2, str(r))
        self.assertEqual(r.kind, "validation")
        after = self.sb.latest("runs", run_id)
        self.assertEqual(after["version"], before["version"])

    def test_finished_ok_missing_data_path_refused(self):
        """30 L114; 03 L120, L122: a finished ok version also requires data_path."""
        _, _, launch, run_sid = self._launch()
        run_id = f"{launch}-a1"
        self._add(launch, run_sid)
        before = self.sb.latest("runs", run_id)
        r = self.sb.rl("run", "finish", run_id, "--exit", "ok", "--metric", "acc=0.5", session=run_sid)
        self.assertEqual(r.rc, 2, str(r))
        self.assertEqual(r.kind, "validation")
        after = self.sb.latest("runs", run_id)
        self.assertEqual(after["version"], before["version"])

    def test_finished_failed_does_not_require_metrics(self):
        """30 L108 (03 L119): a finished failed version does not require metrics but still gets actual_seconds."""
        _, _, launch, run_sid = self._launch()
        run_id = f"{launch}-a1"
        self._add(launch, run_sid)
        path = self.sb.write_file(f"artifacts/{run_id}/metrics.json")
        self.sb.rl_ok("run", "finish", run_id, "--exit", "failed",
                      "--data-path", str(path.relative_to(self.sb.root)), session=run_sid)
        row = self.sb.latest("runs", run_id)
        self.assertEqual(row["exit_status"], "failed")
        self.assertFalse(row.get("metrics"))
        self.assertIsInstance(row["actual_seconds"], (int, float))

    def test_finished_failed_killed_data_path_requirement_pending(self):
        """PENDING(part 23 L93): whether a finished version with exit_status failed or killed needs data_path."""
        self.skipTest("PENDING(part 23 L93): whether a finished version with exit_status "
                      "failed or killed needs data_path")

    # ---- anomaly warnings -----------------------------------------------------
    def test_finish_metric_extreme_zero_opens_anomaly_issue(self):
        """08 L74; 30 L110: a metric landing on 0 (anomaly.metric_extremes) opens an anomaly issue to gyb."""
        _, _, launch, run_sid = self._launch()
        run_id = f"{launch}-a1"
        self._add(launch, run_sid)
        path = self.sb.write_file(f"artifacts/{run_id}/metrics.json")
        before = self.sb.count("issues")
        self.sb.rl_ok("run", "finish", run_id, "--exit", "ok", "--metric", "acc=0",
                      "--data-path", str(path.relative_to(self.sb.root)), session=run_sid)
        issues = self.sb.rows("issues")
        self.assertEqual(len(issues), before + 1)
        self.assertEqual(issues[-1]["kind"], "anomaly")
        self.assertEqual(issues[-1]["assignee"], "gyb")

    def test_finish_metric_extreme_one_opens_anomaly_issue(self):
        """08 L74; 30 L110: a metric landing on 1 (anomaly.metric_extremes) opens an anomaly issue to gyb."""
        _, _, launch, run_sid = self._launch()
        run_id = f"{launch}-a1"
        self._add(launch, run_sid)
        path = self.sb.write_file(f"artifacts/{run_id}/metrics.json")
        before = self.sb.count("issues")
        self.sb.rl_ok("run", "finish", run_id, "--exit", "ok", "--metric", "acc=1",
                      "--data-path", str(path.relative_to(self.sb.root)), session=run_sid)
        issues = self.sb.rows("issues")
        self.assertEqual(len(issues), before + 1)
        self.assertEqual(issues[-1]["kind"], "anomaly")
        self.assertEqual(issues[-1]["assignee"], "gyb")

    def test_finish_duration_exceeds_estimate_opens_anomaly_issue(self):
        """08 L75; 30 L115 (12 "watchdog" final paragraph; 21 section 7): actual duration
        beyond anomaly.duration_factor times the latest attempt's estimated_seconds opens
        an anomaly issue in rl run finish.
        """
        _, _, launch, run_sid = self._launch()
        run_id = f"{launch}-a1"
        self._add(launch, run_sid)
        self.sb.rl_ok("handoff", "estimate", launch, "--step", "s", "--kind", "cpu",
                      "--smoke-seconds", "1", "--scale", "1", session=run_sid)
        # push started_at far into the past so actual_seconds dwarfs the tiny estimate
        # (04 L43: estimated_seconds sums only the latest attempt's step_table).
        runs_path = self.sb.loop / "runs.jsonl"
        rows = [json.loads(l) for l in runs_path.read_text().splitlines() if l.strip()]
        for row in rows:
            if row.get("run_id") == run_id and row.get("status") == "launched":
                row["started_at"] = "2000-01-01T00:00:00+0000"
        runs_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        path = self.sb.write_file(f"artifacts/{run_id}/metrics.json")
        before = self.sb.count("issues")
        self.sb.rl_ok("run", "finish", run_id, "--exit", "ok", "--metric", "acc=0.5",
                      "--data-path", str(path.relative_to(self.sb.root)), session=run_sid)
        issues = self.sb.rows("issues")
        self.assertEqual(len(issues), before + 1)
        self.assertEqual(issues[-1]["kind"], "anomaly")
        self.assertEqual(issues[-1]["assignee"], "gyb")

    # ---- run list -------------------------------------------------------------
    def test_run_list_default_omits_non_ok_latest_attempt(self):
        """03 L124; 30 L110: run list default excludes an order whose latest attempt did not finish ok; --all shows it."""
        _, _, launch, run_sid = self._launch()
        run_id = f"{launch}-a1"
        self._add(launch, run_sid)
        # --data-path is supplied even though exit is killed, not ok, so this test does not
        # depend on the still-undecided PENDING(part 23 L93) question below.
        path = self.sb.write_file(f"artifacts/{run_id}/metrics.json")
        self.sb.rl_ok("run", "finish", run_id, "--exit", "killed",
                      "--data-path", str(path.relative_to(self.sb.root)), session=run_sid)
        default = self.sb.rl_ok("run", "list", "--handoff", launch, "--json").json
        self.assertNotIn(run_id, [r["run_id"] for r in default])
        everything = self.sb.rl_ok("run", "list", "--handoff", launch, "--all", "--json").json
        self.assertIn(run_id, [r["run_id"] for r in everything])

    def test_run_list_default_omits_old_attempt_even_if_ok(self):
        """03 L124; 30 L110: run list default shows only each order's latest attempt, not an earlier ok one; --all shows both."""
        _, _, launch, run_sid = self._launch()
        run_id_1 = f"{launch}-a1"
        self._add(launch, run_sid, attempt="1", log="/tmp/l1", tmux="t1", watch_cmd="w1")
        path1 = self.sb.write_file(f"artifacts/{run_id_1}/metrics.json")
        self.sb.rl_ok("run", "finish", run_id_1, "--exit", "ok", "--metric", "acc=0.4",
                      "--data-path", str(path1.relative_to(self.sb.root)), session=run_sid)
        self.sb.rl_ok("handoff", "release", launch, "--note", "round 1 done")
        self.sb.rl_ok("handoff", "amend", launch, "--command", "python3 t2.py", "--workdir", "experiments",
                      "--track", "probe", "--config", "model=m", "--config", "params=1",
                      "--config", "dataset=d", "--config", "split=s")
        self.sb.rl_ok("handoff", "start", launch, session=run_sid)
        run_id_2 = f"{launch}-a2"
        self._add(launch, run_sid, attempt="2", commit="def456", log="/tmp/l2", tmux="t2", watch_cmd="w2")
        path2 = self.sb.write_file(f"artifacts/{run_id_2}/metrics.json")
        self.sb.rl_ok("run", "finish", run_id_2, "--exit", "ok", "--metric", "acc=0.9",
                      "--data-path", str(path2.relative_to(self.sb.root)), session=run_sid)
        default = self.sb.rl_ok("run", "list", "--handoff", launch, "--json").json
        self.assertEqual([r["run_id"] for r in default], [run_id_2])
        everything = self.sb.rl_ok("run", "list", "--handoff", launch, "--all", "--json").json
        self.assertEqual(sorted(r["run_id"] for r in everything), sorted([run_id_1, run_id_2]))

    def test_run_list_filters_by_decision_and_line(self):
        """05 L73 (03 L124 note): run list --decision and --line resolve through the launch order's decision_refs and line."""
        dec, wo, launch, run_sid = self._launch()
        run_id = f"{launch}-a1"
        self._add(launch, run_sid)
        path = self.sb.write_file(f"artifacts/{run_id}/metrics.json")
        self.sb.rl_ok("run", "finish", run_id, "--exit", "ok", "--metric", "acc=0.5",
                      "--data-path", str(path.relative_to(self.sb.root)), session=run_sid)
        line = self.sb.latest("handoffs", launch)["line"]
        by_decision = self.sb.rl_ok("run", "list", "--decision", dec, "--json").json
        self.assertIn(run_id, [r["run_id"] for r in by_decision])
        by_line = self.sb.rl_ok("run", "list", "--line", line, "--json").json
        self.assertIn(run_id, [r["run_id"] for r in by_line])

    # ---- relink -----------------------------------------------------------
    def test_relink_appends_version_changing_only_handoff_id(self):
        """03 L100 (sync-inbox Q31); 05 L73: a relink version copies every other field from the latest version, changing only handoff_id."""
        dec = make_decision(self.sb)
        wo = open_work_order(self.sb, None, dec)
        launch1 = open_launch_order(self.sb, None, wo)
        launch2 = open_launch_order(self.sb, None, wo)
        run_sid = self.sb.role_session("run")
        self.sb.rl_ok("handoff", "start", launch1, session=run_sid)
        run_id = f"{launch1}-a1"
        self._add(launch1, run_sid)
        before = self.sb.latest("runs", run_id)
        self.sb.rl_ok("run", "relink", run_id, "--handoff", launch2)
        after = self.sb.latest("runs", run_id)
        self.assertEqual(after["version"], before["version"] + 1)
        self.assertEqual(after["handoff_id"], launch2)
        for key in ("status", "attempt", "commit", "host", "gpus", "log_path", "tmux_session", "watch_cmd", "config"):
            self.assertEqual(after[key], before[key], key)

    # ---- rl-filled timestamps ---------------------------------------------
    def test_started_at_not_accepted_on_command_line(self):
        """30 L117 (05 command table): started_at is filled by rl and refused on the command line."""
        _, _, launch, run_sid = self._launch()
        r = self.sb.rl("run", "add", "--handoff", launch, "--attempt", "1", "--commit", "abc",
                       "--host", "h", "--gpus", "0", "--log", "/tmp/l", "--tmux", "t",
                       "--watch-cmd", "w", "--started-at", "2020-01-01T00:00:00+0000", session=run_sid)
        self.assertEqual(r.rc, 5, str(r))
        self.assertEqual(r.kind, "usage")

    def test_finished_at_not_accepted_on_command_line(self):
        """30 L117 (05 command table): finished_at is filled by rl and refused on the command line."""
        _, _, launch, run_sid = self._launch()
        run_id = f"{launch}-a1"
        self._add(launch, run_sid)
        # --data-path is supplied so an unrelated PENDING(part 23 L93) refusal cannot
        # masquerade as the exit-5 refusal this test is checking for.
        path = self.sb.write_file(f"artifacts/{run_id}/metrics.json")
        r = self.sb.rl("run", "finish", run_id, "--exit", "killed",
                       "--data-path", str(path.relative_to(self.sb.root)),
                       "--finished-at", "2020-01-01T00:00:00+0000", session=run_sid)
        self.assertEqual(r.rc, 5, str(r))
        self.assertEqual(r.kind, "usage")

    # ---- actual_seconds copy into the handoff -------------------------------
    def test_actual_seconds_copied_into_launch_order_latest_attempt(self):
        """04 L43: rl copies actual_seconds from the runs finish version into the launch order's latest attempt."""
        _, _, launch, run_sid = self._launch()
        run_id = f"{launch}-a1"
        self._add(launch, run_sid)
        path = self.sb.write_file(f"artifacts/{run_id}/metrics.json")
        self.sb.rl_ok("run", "finish", run_id, "--exit", "ok", "--metric", "acc=0.5",
                      "--data-path", str(path.relative_to(self.sb.root)), session=run_sid)
        run_row = self.sb.latest("runs", run_id)
        handoff_row = self.sb.latest("handoffs", launch)
        self.assertEqual(handoff_row["attempts"][-1]["actual_seconds"], run_row["actual_seconds"])


if __name__ == "__main__":
    unittest.main()
