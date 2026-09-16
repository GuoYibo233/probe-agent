import json, os, pathlib, tempfile, time, unittest
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "ops"))


class TestSampleOnce(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        d = pathlib.Path(self.td.name)
        os.environ["NEW1_MONITOR_DIR"] = str(d / "monitor")
        log0 = d / "a.log"
        now = time.time()
        log0.write_text(
            "loading...\n"
            f'@hb {{"done": 0, "total": 10, "unit": "task", "ts": {now-120:.1f}}}\n'
            f'@hb {{"done": 1, "total": 10, "unit": "task", "ts": {now-60:.1f}, "tok_in": 100, "tok_out": 20}}\n'
            f'@hb {{"done": 2, "total": 10, "unit": "task", "ts": {now-1:.1f}, "tok_in": 210, "tok_out": 41}}\n')
        log1 = d / "b.log"
        log1.write_text("Traceback (most recent call last):\n  boom\n")
        self.jobs = d / "jobs.json"
        self.jobs.write_text(json.dumps({"active": [{
            "name": "x", "workdir": str(d), "started_at": "2026-08-08 00:00",
            "monitor": {"warmup_s": 1800},
            "pieces": [
                {"host": "tokyo106", "gpus": "0", "session": "new1_x_t106g0",
                 "log": str(log0), "launched_at": now - 3600, "kind": "batch"},
                {"host": "tokyo106", "gpus": "1", "session": "new1_x_t106g1",
                 "log": str(log1), "launched_at": now - 3600, "kind": "batch"},
            ]}], "history": []}))
        import importlib
        import sampler
        importlib.reload(sampler)
        self.S = sampler
        self._old_reg_path = self.S.REG_PATH
        self._old_live_sessions = self.S.live_sessions
        self._old_spawn_agent = self.S.spawn_agent
        self.S.REG_PATH = str(self.jobs)
        self.S.live_sessions = lambda hosts: {"tokyo106": {"new1_x_t106g0"}}
        # The incident-trigger chain must not actually spawn a subprocess in this test file
        # (final-review C1): the b.log piece is judged "dead" right away and hits the
        # escalation line, so round 1 will hit maybe_trigger_incidents -> spawn_agent. Mock
        # it into a recording lambda, restore it in tearDown, and do not leak it into the
        # next test.
        self._spawned = []
        self.S.spawn_agent = lambda prompt, out: self._spawned.append(
            (prompt, str(out)))

    def tearDown(self):
        self.S.REG_PATH = self._old_reg_path
        self.S.live_sessions = self._old_live_sessions
        self.S.spawn_agent = self._old_spawn_agent
        self.td.cleanup()
        os.environ.pop("NEW1_MONITOR_DIR", None)

    def test_round(self):
        latest = self.S.sample_once()
        rows = {r["idx"]: r for r in latest["rows"]}
        self.assertIn(rows[0]["verdict"], ("healthy", "warming up"))
        self.assertEqual(rows[1]["verdict"], "dead")
        self.assertEqual(rows[0]["tok_in"], 210)
        mon = pathlib.Path(os.environ["NEW1_MONITOR_DIR"])
        self.assertTrue((mon / "latest.json").exists())
        self.assertTrue((mon / "state.json").exists())
        self.assertTrue((mon / "history" / "x.jsonl").exists())
        n1 = len(json.loads((mon / "state.json").read_text())
                 ["x#0"]["recent_beats"])
        self.S.sample_once()                      # Log unchanged, do not count the heartbeat again
        n2 = len(json.loads((mon / "state.json").read_text())
                 ["x#0"]["recent_beats"])
        self.assertEqual(n1, n2)

    def test_files_are_valid_json(self):
        self.S.sample_once()
        mon = pathlib.Path(os.environ["NEW1_MONITOR_DIR"])
        latest = json.loads((mon / "latest.json").read_text())
        state = json.loads((mon / "state.json").read_text())
        self.assertIn("sampled_at", latest)
        self.assertIn("rows", latest)
        self.assertIn("x#0", state)
        hist_lines = (mon / "history" / "x.jsonl").read_text().splitlines()
        self.assertTrue(hist_lines)
        for line in hist_lines:
            json.loads(line)  # Each line is independently valid JSON

    def test_refire_resets_state_and_counts(self):
        latest1 = self.S.sample_once()
        mon = pathlib.Path(os.environ["NEW1_MONITOR_DIR"])
        state = json.loads((mon / "state.json").read_text())
        self.assertEqual(state["x#0"]["refires"], 0)
        self.assertEqual(len(state["x#0"]["recent_beats"]), 3)
        # Refire: launched_at changed, the same piece's log is swapped for a brand-new log (a new job)
        reg = json.loads(self.jobs.read_text())
        reg["active"][0]["pieces"][0]["launched_at"] = time.time()
        self.jobs.write_text(json.dumps(reg))
        self.S.sample_once()
        state2 = json.loads((mon / "state.json").read_text())
        self.assertEqual(state2["x#0"]["refires"], 1)
        # State reopened: first_beat/last_new_beat_mono have both been refreshed (not left over from before)
        self.assertIsNotNone(state2["x#0"]["first_beat"])


class TestReadBeats(unittest.TestCase):
    def setUp(self):
        import sampler
        self.S = sampler

    def test_reads_only_valid_heartbeat_lines(self):
        with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as f:
            f.write("plain text\n")
            f.write('@hb {"done": 1, "total": 5, "unit": "x", "ts": 100.0}\n')
            f.write("garbage @hb not-json\n")
            path = f.name
        try:
            beats = self.S.read_beats(path)
            self.assertEqual(len(beats), 1)
            self.assertEqual(beats[0]["done"], 1)
        finally:
            os.unlink(path)

    def test_missing_log_returns_empty(self):
        self.assertEqual(self.S.read_beats("/no/such/file.log"), [])


class TestProbePort(unittest.TestCase):
    def test_unreachable_returns_false(self):
        import sampler
        # Port 1 should never have an HTTP service listening on any machine, ConnectionRefused -> False
        self.assertFalse(sampler.probe_port("127.0.0.1", 1, timeout=1))


if __name__ == "__main__":
    unittest.main()
