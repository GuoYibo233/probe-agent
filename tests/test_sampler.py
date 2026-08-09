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
        # 事故触发链路不许在这个测试文件里真的拉子进程(final-review C1):
        # b.log 那个分片一上来就判"已挂"并达到升级线,round 1 就会命中
        # maybe_trigger_incidents -> spawn_agent。mock 成记录用的 lambda,
        # tearDown 还原,不留给下一个测试。
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
        self.assertIn(rows[0]["verdict"], ("健康", "warm-up 中"))
        self.assertEqual(rows[1]["verdict"], "已挂")
        self.assertEqual(rows[0]["tok_in"], 210)
        mon = pathlib.Path(os.environ["NEW1_MONITOR_DIR"])
        self.assertTrue((mon / "latest.json").exists())
        self.assertTrue((mon / "state.json").exists())
        self.assertTrue((mon / "history" / "x.jsonl").exists())
        n1 = len(json.loads((mon / "state.json").read_text())
                 ["x#0"]["recent_beats"])
        self.S.sample_once()                      # 日志没变,不重复计心跳
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
            json.loads(line)  # 每行独立合法 JSON

    def test_refire_resets_state_and_counts(self):
        latest1 = self.S.sample_once()
        mon = pathlib.Path(os.environ["NEW1_MONITOR_DIR"])
        state = json.loads((mon / "state.json").read_text())
        self.assertEqual(state["x#0"]["refires"], 0)
        self.assertEqual(len(state["x#0"]["recent_beats"]), 3)
        # 补射:launched_at 变了,同一分片的日志换成一份全新日志(新任务)
        reg = json.loads(self.jobs.read_text())
        reg["active"][0]["pieces"][0]["launched_at"] = time.time()
        self.jobs.write_text(json.dumps(reg))
        self.S.sample_once()
        state2 = json.loads((mon / "state.json").read_text())
        self.assertEqual(state2["x#0"]["refires"], 1)
        # 状态重开:first_beat/last_new_beat_mono 都刷新过(不是历史遗留)
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
        # 端口 1 在任何机器上都不该有 HTTP 服务在听,ConnectionRefused -> False
        self.assertFalse(sampler.probe_port("127.0.0.1", 1, timeout=1))


if __name__ == "__main__":
    unittest.main()
