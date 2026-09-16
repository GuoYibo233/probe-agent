import json
import pathlib
import sys
import tempfile
import time
import unittest
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "ops"))

import sampler  # noqa: E402
import verdicts  # noqa: E402


class TestWebServer(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.monitor_dir = pathlib.Path(self.td.name)
        self.now = time.time()
        self.latest = {
            "sampled_at": self.now,
            "rows": [
                {"job": "x", "idx": 0, "host": "tokyo106", "gpus": "0",
                 "session": "new1_x_t106g0", "kind": "batch",
                 "verdict": "healthy", "escalated": False,
                 "done": 3, "total": 10, "unit": "task",
                 "progress_pct": 30.0, "avg_rate": 0.01,
                 "recent_rate": 0.02, "tok_in": 100, "tok_out": 20,
                 "loss": None, "eta_s": 300.0, "log": "/tmp/a.log",
                 "probe_failed": False, "probe_fail_rounds": 0,
                 "refires": 0},
                {"job": "y", "idx": 0, "host": "tokyo107", "gpus": "1",
                 "session": "new1_y_t107g1", "kind": "batch",
                 "verdict": "dead", "escalated": False,
                 "done": None, "total": None, "unit": None,
                 "progress_pct": None, "avg_rate": None,
                 "recent_rate": None, "tok_in": None, "tok_out": None,
                 "loss": None, "eta_s": None, "log": "/tmp/b.log",
                 "probe_failed": False, "probe_fail_rounds": 0,
                 "refires": 0},
            ],
            "extras": {"tokyo108": ["stray_session"]},
            "incidents_tail": [
                {"t": self.now - 3600, "job": "z", "idx": 0,
                 "verdict": "dead", "note": "autopsy: process not present"},
            ],
        }
        (self.monitor_dir / "latest.json").write_text(
            json.dumps(self.latest, ensure_ascii=False))
        self.server = sampler.WebServer(
            port=0, monitor_dir=self.monitor_dir)
        self.server.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.stop()
        self.td.cleanup()

    def _get(self, path):
        with urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}{path}", timeout=5) as r:
            return r.status, r.read().decode("utf-8")

    def test_json_matches_latest_file(self):
        status, body = self._get("/json")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), self.latest)

    def test_json_content_type(self):
        with urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}/json", timeout=5) as r:
            self.assertEqual(r.headers.get("Content-Type"),
                              "application/json")

    def test_root_returns_200_with_task_table(self):
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn("x", body)          # Job name
        self.assertIn("healthy", body)        # Verdict
        self.assertIn("dead", body)
        # The text of the last sample time (a clock time in HH:MM:SS format) appears in the body
        stamp = time.strftime("%H:%M:%S", time.localtime(self.now))
        self.assertIn(stamp, body)

    def test_root_renders_incidents_and_extras(self):
        status, body = self._get("/")
        self.assertIn("autopsy: process not present", body)
        self.assertIn("stray_session", body)

    def test_stale_threshold_from_verdicts_defaults(self):
        # The stale-turns-red threshold = sample_interval_s * 3, generated from the verdict
        # engine's DEFAULTS into the page, not copied as a separate number -- the body
        # should show this computed value.
        status, body = self._get("/")
        expected = verdicts.DEFAULTS["sample_interval_s"] * 3
        self.assertIn(str(int(expected)), body)

    def test_missing_latest_file_returns_200_with_placeholder(self):
        (self.monitor_dir / "latest.json").unlink()
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn("No samples", body)


if __name__ == "__main__":
    unittest.main()
