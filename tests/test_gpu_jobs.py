import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "ops"))

import gpu_jobs  # noqa: E402
import verdicts  # noqa: E402


def _fresh_latest(now):
    return {
        "sampled_at": now,
        "rows": [
            {"job": "x", "idx": 0, "host": "tokyo106", "gpus": "0",
             "session": "new1_x_t106g0", "kind": "batch",
             "verdict": verdicts.V_OK, "escalated": False,
             "done": 3, "total": 10, "unit": "task",
             "progress_pct": 30.0, "avg_rate": 0.01,
             "recent_rate": 0.02, "tok_in": 1234567, "tok_out": 340000,
             "loss": None, "eta_s": 3725, "log": "/tmp/a.log",
             "probe_failed": False, "probe_fail_rounds": 0, "refires": 0},
            {"job": "y", "idx": 0, "host": "tokyo107", "gpus": "1",
             "session": "new1_y_t107g1", "kind": "batch",
             "verdict": verdicts.V_DEAD, "escalated": True,
             "done": 4, "total": 10, "unit": "task",
             "progress_pct": 40.0, "avg_rate": None,
             "recent_rate": None, "tok_in": None, "tok_out": None,
             "loss": None, "eta_s": None, "log": "/tmp/b.log",
             "probe_failed": False, "probe_fail_rounds": 0, "refires": 0},
        ],
        "extras": {"tokyo108": ["stray_session"]},
        "incidents_tail": [],
    }


class TestReadLatest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.mon = pathlib.Path(self.td.name)
        self._orig_monitor_dir = gpu_jobs.MONITOR_DIR
        gpu_jobs.MONITOR_DIR = str(self.mon)

    def tearDown(self):
        gpu_jobs.MONITOR_DIR = self._orig_monitor_dir
        self.td.cleanup()

    def test_missing_file_returns_none_none(self):
        latest, age_s = gpu_jobs.read_latest()
        self.assertIsNone(latest)
        self.assertIsNone(age_s)

    def test_fresh_file_returns_dict_and_small_age(self):
        now = time.time()
        (self.mon / "latest.json").write_text(
            json.dumps(_fresh_latest(now)))
        latest, age_s = gpu_jobs.read_latest()
        self.assertIsNotNone(latest)
        self.assertEqual(latest["sampled_at"], now)
        self.assertLess(age_s, 5.0)

    def test_stale_file_reports_large_age(self):
        old = time.time() - 3600  # One hour ago, far past the 5-minute freshness threshold
        (self.mon / "latest.json").write_text(
            json.dumps(_fresh_latest(old)))
        latest, age_s = gpu_jobs.read_latest()
        self.assertIsNotNone(latest)
        self.assertGreater(age_s, gpu_jobs.FRESH_S)

    def test_corrupt_file_returns_none_none(self):
        (self.mon / "latest.json").write_text("{not json")
        latest, age_s = gpu_jobs.read_latest()
        self.assertIsNone(latest)
        self.assertIsNone(age_s)

    def test_sampled_at_wrong_type_returns_none_none(self):
        # Valid JSON, but sampled_at is a string -- should not raise TypeError (F1 review)
        (self.mon / "latest.json").write_text(
            json.dumps({"sampled_at": "x", "rows": []}))
        latest, age_s = gpu_jobs.read_latest()
        self.assertIsNone(latest)
        self.assertIsNone(age_s)

    def test_top_level_not_dict_returns_none_none(self):
        # Valid JSON, but the top level is an array, not a dict -- should not raise AttributeError (F1 review)
        (self.mon / "latest.json").write_text(json.dumps([]))
        latest, age_s = gpu_jobs.read_latest()
        self.assertIsNone(latest)
        self.assertIsNone(age_s)

    def test_missing_sampled_at_field_returns_latest_and_none_age(self):
        # The sampled_at field is entirely missing (not a type error, just absent) -- latest
        # passes through unchanged, age_s=None, the caller takes the stale branch
        (self.mon / "latest.json").write_text(json.dumps({"rows": []}))
        latest, age_s = gpu_jobs.read_latest()
        self.assertIsNotNone(latest)
        self.assertIsNone(age_s)


class TestFmtTableV2(unittest.TestCase):
    def test_renders_all_columns_and_header_stamp(self):
        now = time.time()
        latest = _fresh_latest(now)
        table = gpu_jobs.fmt_table_v2(latest["rows"], latest["sampled_at"])
        stamp = time.strftime("%H:%M:%S", time.localtime(now))
        self.assertIn(f"last sample {stamp}", table)
        self.assertIn("verdict", table)          # Verdict column header
        self.assertIn(verdicts.V_OK, table)    # Verdict value
        self.assertIn(verdicts.V_DEAD, table)
        self.assertIn("3/10 (30.0%) task", table)   # Progress
        self.assertIn("72/h", table)            # Rate: 0.02/s * 3600 = 72/h
        self.assertIn("1.2M/340k", table)       # token abbreviation
        self.assertIn("01:02", table)           # ETA:3725s -> 01:02

    def test_empty_rows_still_shows_header_and_placeholder(self):
        table = gpu_jobs.fmt_table_v2([], sampled_at=1234567890.0)
        self.assertIn("last sample", table)
        self.assertIn("job ledger is empty", table)

    def test_all_done_job_gets_finish_tip(self):
        rows = [
            {"job": "z", "idx": 0, "host": "h", "gpus": "0",
             "session": "s0", "verdict": verdicts.V_DONE,
             "done": 10, "total": 10, "unit": "task", "progress_pct": 100.0,
             "recent_rate": None, "tok_in": None, "tok_out": None,
             "eta_s": None, "log": "/tmp/z.log"},
        ]
        table = gpu_jobs.fmt_table_v2(rows)
        self.assertIn("time to finish", table)
        self.assertIn("python3 run.py gpu-jobs finish z", table)

    def test_dead_row_gets_look_at_log_tip(self):
        rows = [
            {"job": "w", "idx": 0, "host": "h", "gpus": "0",
             "session": "s0", "verdict": verdicts.V_DEAD,
             "done": 4, "total": 10, "unit": "task", "progress_pct": 40.0,
             "recent_rate": None, "tok_in": None, "tok_out": None,
             "eta_s": None, "log": "/tmp/w.log"},
        ]
        table = gpu_jobs.fmt_table_v2(rows)
        self.assertIn("check the log", table)
        self.assertIn("/tmp/w.log", table)


class TestCmdJson(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        d = pathlib.Path(self.td.name)
        self.mon = d / "monitor"
        self._orig_monitor_dir = gpu_jobs.MONITOR_DIR
        gpu_jobs.MONITOR_DIR = str(self.mon)
        self.jobs = d / "jobs.json"
        self.jobs.write_text(json.dumps({"active": [], "history": []}))
        self._orig_reg_path = gpu_jobs.REG_PATH
        gpu_jobs.REG_PATH = str(self.jobs)

    def tearDown(self):
        gpu_jobs.MONITOR_DIR = self._orig_monitor_dir
        gpu_jobs.REG_PATH = self._orig_reg_path
        self.td.cleanup()

    def _run_cmd_json(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            gpu_jobs.cmd_json()
        return json.loads(buf.getvalue())

    def test_no_sampler_running_outputs_valid_json_with_stale_flag(self):
        out = self._run_cmd_json()
        self.assertTrue(out["sampler_stale"])
        self.assertEqual(out["rows"], [])

    def test_fresh_latest_outputs_it_verbatim(self):
        now = time.time()
        latest = _fresh_latest(now)
        self.mon.mkdir(parents=True, exist_ok=True)
        (self.mon / "latest.json").write_text(json.dumps(latest))
        out = self._run_cmd_json()
        self.assertEqual(out, latest)
        self.assertNotIn("sampler_stale", out)

    def test_stale_latest_outputs_old_collect_with_stale_flag(self):
        old = time.time() - 3600
        self.mon.mkdir(parents=True, exist_ok=True)
        (self.mon / "latest.json").write_text(
            json.dumps(_fresh_latest(old)))
        out = self._run_cmd_json()
        self.assertTrue(out["sampler_stale"])
        self.assertEqual(out["rows"], [])  # collect()'s old path, empty job ledger


class TestCmdStatus(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        d = pathlib.Path(self.td.name)
        self.mon = d / "monitor"
        self._orig_monitor_dir = gpu_jobs.MONITOR_DIR
        gpu_jobs.MONITOR_DIR = str(self.mon)
        self.jobs = d / "jobs.json"
        self.jobs.write_text(json.dumps({"active": [], "history": []}))
        self._orig_reg_path = gpu_jobs.REG_PATH
        gpu_jobs.REG_PATH = str(self.jobs)

    def tearDown(self):
        gpu_jobs.MONITOR_DIR = self._orig_monitor_dir
        gpu_jobs.REG_PATH = self._orig_reg_path
        self.td.cleanup()

    def _run_cmd_status(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            gpu_jobs.cmd_status()
        return buf.getvalue()

    def test_no_sampler_running_warns_and_falls_back(self):
        out = self._run_cmd_status()
        self.assertIn("sampler is not running (last sample none), probing live once", out)
        self.assertIn("job ledger is empty", out)

    def test_fresh_latest_renders_new_table(self):
        now = time.time()
        latest = _fresh_latest(now)
        self.mon.mkdir(parents=True, exist_ok=True)
        (self.mon / "latest.json").write_text(json.dumps(latest))
        out = self._run_cmd_status()
        self.assertNotIn("do a live probe once", out)
        self.assertIn("last sample", out)
        self.assertIn("verdict", out)
        self.assertIn("stray_session", out)  # extras render as before


class TestCmdRegister(unittest.TestCase):
    """C2 (final-review, 2026-08-09): the manual backfill-registration path must also be
    able to register a service piece -- without --kind/--port, behavior is unchanged
    (defaults to batch, no port field); given, it lands in the piece, so the sampler's
    probe_port verdict chain can connect."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        d = pathlib.Path(self.td.name)
        self.jobs = d / "jobs.json"
        self.jobs.write_text(json.dumps({"active": [], "history": []}))
        self._orig_reg_path = gpu_jobs.REG_PATH
        gpu_jobs.REG_PATH = str(self.jobs)

    def tearDown(self):
        gpu_jobs.REG_PATH = self._orig_reg_path
        self.td.cleanup()

    def test_default_kind_is_batch_no_port_field(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            gpu_jobs.cmd_register([
                "--name", "reg1", "--workdir", "/tmp/wd",
                "--piece", "tokyo106:0:new1_reg1_t106g0:/tmp/a.log"])
        piece = gpu_jobs.load_reg()["active"][0]["pieces"][0]
        self.assertEqual(piece["kind"], "batch")
        self.assertNotIn("port", piece)

    def test_kind_and_port_land_on_piece(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            gpu_jobs.cmd_register([
                "--name", "reg2", "--workdir", "/tmp/wd",
                "--piece", "tokyo108:0:new1_reg2_t108g0:/tmp/b.log",
                "--kind", "service", "--port", "8103"])
        piece = gpu_jobs.load_reg()["active"][0]["pieces"][0]
        self.assertEqual(piece["kind"], "service")
        self.assertEqual(piece["port"], 8103)


if __name__ == "__main__":
    unittest.main()
