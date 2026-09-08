"""Ticket 13 (vLLM service profile): throughput-line parsing + service pieces use
port-based verdicts, not heartbeat parsing. The fixture line was checked against
a real log on 2026-08-08 (see the constant comment below); it is not hand-made text.
"""
import json
import os
import pathlib
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "ops"))

# checked on 2026-08-08: byte-identical to line 9421 of
# /net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/logs/new1_diag_srv_a.log
# (vllm 0.26.0, the throughput-line format from loggers.py:263-313).
REAL_FIXTURE_LINE = (
    "(APIServer pid=263921) INFO 08-02 19:50:14 [loggers.py:310] "
    "Engine 000: Avg prompt throughput: 785.1 tokens/s, "
    "Avg generation throughput: 671.8 tokens/s, Running: 4 reqs, "
    "Waiting: 0 reqs, GPU KV cache usage: 11.2%, "
    "Prefix cache hit rate: 97.1%"
)
# an earlier line (line 112) from the same real log, with a different concurrency
# count, used to verify the fixture's specific numbers aren't hard-coded into the
# implementation.
REAL_FIXTURE_LINE_2 = (
    "(APIServer pid=263921) INFO 08-02 17:09:56 [loggers.py:310] "
    "Engine 000: Avg prompt throughput: 7.0 tokens/s, "
    "Avg generation throughput: 2.0 tokens/s, Running: 0 reqs, "
    "Waiting: 0 reqs, GPU KV cache usage: 0.0%, "
    "Prefix cache hit rate: 0.0%"
)


class TestParseVllmStats(unittest.TestCase):
    def setUp(self):
        import sampler
        self.S = sampler

    def test_extracts_real_fixture_line(self):
        got = self.S.parse_vllm_stats(REAL_FIXTURE_LINE)
        self.assertEqual(got, {"prompt_tok_s": 785.1, "gen_tok_s": 671.8,
                                "running": 4})

    def test_extracts_second_real_line(self):
        got = self.S.parse_vllm_stats(REAL_FIXTURE_LINE_2)
        self.assertEqual(got, {"prompt_tok_s": 7.0, "gen_tok_s": 2.0,
                                "running": 0})

    def test_no_match_returns_none(self):
        self.assertIsNone(self.S.parse_vllm_stats("just a banner line\n"))
        self.assertIsNone(self.S.parse_vllm_stats(""))

    def test_multiple_lines_takes_the_last(self):
        text = REAL_FIXTURE_LINE_2 + "\n" + REAL_FIXTURE_LINE
        got = self.S.parse_vllm_stats(text)
        self.assertEqual(got["gen_tok_s"], 671.8)  # the latest one, not the first


class TestReadVllmStats(unittest.TestCase):
    def setUp(self):
        import sampler
        self.S = sampler

    def test_reads_tail_of_log_file(self):
        with tempfile.NamedTemporaryFile(
                "w", suffix=".log", delete=False) as f:
            f.write("banner line, no stats here\n")
            f.write(REAL_FIXTURE_LINE_2 + "\n")
            f.write(REAL_FIXTURE_LINE + "\n")
            path = f.name
        try:
            got = self.S.read_vllm_stats(path)
            self.assertEqual(got["gen_tok_s"], 671.8)
            self.assertEqual(got["prompt_tok_s"], 785.1)
            self.assertEqual(got["running"], 4)
        finally:
            os.unlink(path)

    def test_missing_file_returns_none(self):
        self.assertIsNone(self.S.read_vllm_stats("/no/such/vllm.log"))

    def test_no_throughput_line_returns_none(self):
        with tempfile.NamedTemporaryFile(
                "w", suffix=".log", delete=False) as f:
            f.write("(APIServer pid=1) INFO 08-02 17:08:04 [api_utils.py:345] "
                     "starting up\n")
            path = f.name
        try:
            self.assertIsNone(self.S.read_vllm_stats(path))
        finally:
            os.unlink(path)


class TestServicePieceSampling(unittest.TestCase):
    """Integration smoke test (ticket 13 acceptance item 2): service pieces don't use
    heartbeat parsing, the verdict is decided by port probing alone; the throughput
    line only feeds the display field. Modeled on test_sampler.py's TestSampleOnce
    pattern."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        d = pathlib.Path(self.td.name)
        os.environ["NEW1_MONITOR_DIR"] = str(d / "monitor")
        # vLLM's log is not under workdir (ticket 13's own wording); this deliberately
        # places it at a path unrelated to workdir, to verify that read_vllm_stats only
        # trusts the piece["log"] field, not any assumption about a fixed relative
        # location for the log.
        self.vllm_log = d / "vllm_cache_logs" / "new1_diag_srv_a.log"
        self.vllm_log.parent.mkdir(parents=True)
        # mixes in a line that looks like a heartbeat but isn't + a real throughput line +
        # one line of @hb noise (deliberate: even if a valid @hb line appears in the log,
        # a service piece should not count it as a heartbeat)
        self.vllm_log.write_text(
            "starting up\n"
            + REAL_FIXTURE_LINE_2 + "\n"
            + REAL_FIXTURE_LINE + "\n"
            '@hb {"done": 999, "total": 1000, "unit": "tok", "ts": 1.0}\n'
        )
        self.jobs = d / "jobs.json"
        now = time.time()
        self.jobs.write_text(json.dumps({"active": [{
            "name": "srv", "workdir": str(d), "started_at": "2026-08-08 00:00",
            "pieces": [
                {"host": "tokyo108", "gpus": "0",
                 "session": "new1_diag_srv_a_t108g0",
                 "log": str(self.vllm_log), "launched_at": now - 300,
                 "kind": "service", "port": 8103},
            ]}], "history": []}))
        import importlib
        import sampler
        importlib.reload(sampler)
        self.S = sampler
        self._old_reg_path = self.S.REG_PATH
        self._old_live_sessions = self.S.live_sessions
        self._old_spawn_agent = self.S.spawn_agent
        self._old_probe_port = self.S.probe_port
        self.S.REG_PATH = str(self.jobs)
        self.S.live_sessions = (
            lambda hosts: {"tokyo108": {"new1_diag_srv_a_t108g0"}})
        # the test case where the port never answers (test_port_down_...) judges this
        # piece "dead" and reaches the escalation line, triggering
        # maybe_trigger_incidents -> spawn_agent -- mocked as a lambda that just records
        # calls, not allowed to actually spawn a subprocess (final-review C1); restored
        # in tearDown, not left behind for the next test file.
        self._spawned = []
        self.S.spawn_agent = lambda prompt, out: self._spawned.append(
            (prompt, str(out)))

    def tearDown(self):
        self.S.REG_PATH = self._old_reg_path
        self.S.live_sessions = self._old_live_sessions
        self.S.spawn_agent = self._old_spawn_agent
        self.S.probe_port = self._old_probe_port
        self.td.cleanup()
        os.environ.pop("NEW1_MONITOR_DIR", None)

    def test_healthy_port_ignores_fake_heartbeat_line_and_shows_rate(self):
        self.S.probe_port = lambda host, port, timeout=3: True
        latest = self.S.sample_once()
        row = latest["rows"][0]
        self.assertEqual(row["verdict"], "healthy")
        # the display field picks up the generation/prompt rate from the latest throughput line
        self.assertEqual(row["tok_out"], 671.8)
        self.assertEqual(row["tok_in"], 785.1)
        # service pieces don't use heartbeat parsing: the valid @hb line in the log is not counted as a heartbeat
        self.assertIsNone(row["done"])
        self.assertIsNone(row["total"])
        mon = pathlib.Path(os.environ["NEW1_MONITOR_DIR"])
        state = json.loads((mon / "state.json").read_text())
        self.assertEqual(state["srv#0"]["recent_beats"], [])
        self.assertIsNone(state["srv#0"]["first_beat"])

    def test_port_down_gives_dead_verdict_regardless_of_throughput_line(self):
        # the throughput line is still there (the log hasn't stopped), but the port probe judges it dead -- the verdict looks only at the port.
        self.S.probe_port = lambda host, port, timeout=3: False
        self.S.live_sessions = lambda hosts: {"tokyo108": set()}
        latest = self.S.sample_once()
        row = latest["rows"][0]
        self.assertEqual(row["verdict"], "dead")

    def test_idle_no_throughput_line_keeps_last_known_rate_for_display(self):
        """A stopped throughput line (the engine idles and drops to debug level, so it
        doesn't print) doesn't count as a stall; the verdict still looks at the port;
        the display field keeps the last known value from the previous round, and
        doesn't flash back to blank just because this round has no throughput line."""
        self.S.probe_port = lambda host, port, timeout=3: True
        self.S.sample_once()
        # second round: no new throughput line in the log (idle)
        self.vllm_log.write_text("engine idle, nothing printed\n")
        latest2 = self.S.sample_once()
        row2 = latest2["rows"][0]
        self.assertEqual(row2["verdict"], "healthy")
        self.assertEqual(row2["tok_out"], 671.8)  # carries over from the previous round


if __name__ == "__main__":
    unittest.main()
