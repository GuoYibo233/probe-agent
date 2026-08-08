"""工单 13(vLLM 服务档):吞吐行解析 + 服务分片走端口判定不走心跳解析。
fixture 行 2026-08-08 从真实日志核实(见下方常量注释),不是手造文本。
"""
import json
import os
import pathlib
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "ops"))

# 2026-08-08 核对:与
# /net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/logs/new1_diag_srv_a.log
# 第 9421 行字节级一致(vllm 0.26.0,loggers.py:263-313 的吞吐行格式)。
REAL_FIXTURE_LINE = (
    "(APIServer pid=263921) INFO 08-02 19:50:14 [loggers.py:310] "
    "Engine 000: Avg prompt throughput: 785.1 tokens/s, "
    "Avg generation throughput: 671.8 tokens/s, Running: 4 reqs, "
    "Waiting: 0 reqs, GPU KV cache usage: 11.2%, "
    "Prefix cache hit rate: 97.1%"
)
# 同一份真实日志里的早期一行(第 112 行),并发数不同,用来验证不是把
# fixture 的具体数字焊死在实现里。
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
        self.assertEqual(got["gen_tok_s"], 671.8)  # 最新一条,不是第一条


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
    """集成冒烟(工单 13 验收项 2):服务分片不走心跳解析,判定只由端口探测
    决定;吞吐行只进显示位。仿 test_sampler.py 的 TestSampleOnce 套路。"""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        d = pathlib.Path(self.td.name)
        os.environ["NEW1_MONITOR_DIR"] = str(d / "monitor")
        # vLLM 的日志不在 workdir 下(工单 13 原话),这里刻意放到一个和
        # workdir 不相干的路径,验证 read_vllm_stats 就认 piece["log"]
        # 这个字段,不假设日志在某个固定相对位置。
        self.vllm_log = d / "vllm_cache_logs" / "new1_diag_srv_a.log"
        self.vllm_log.parent.mkdir(parents=True)
        # 混一行看起来像心跳但其实不是的文本 + 真实吞吐行 + 一行 @hb 噪声
        # (故意的:即便日志里出现合法 @hb 行,服务分片也不该把它算进心跳)
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
        self.S.REG_PATH = str(self.jobs)
        self.S.live_sessions = (
            lambda hosts: {"tokyo108": {"new1_diag_srv_a_t108g0"}})

    def tearDown(self):
        self.td.cleanup()
        os.environ.pop("NEW1_MONITOR_DIR", None)

    def test_healthy_port_ignores_fake_heartbeat_line_and_shows_rate(self):
        self.S.probe_port = lambda host, port, timeout=3: True
        latest = self.S.sample_once()
        row = latest["rows"][0]
        self.assertEqual(row["verdict"], "健康")
        # 显示位吃到了吞吐行里最新一条的生成/prompt 速率
        self.assertEqual(row["tok_out"], 671.8)
        self.assertEqual(row["tok_in"], 785.1)
        # 服务分片不走心跳解析:日志里那行合法 @hb 没有被算进心跳
        self.assertIsNone(row["done"])
        self.assertIsNone(row["total"])
        mon = pathlib.Path(os.environ["NEW1_MONITOR_DIR"])
        state = json.loads((mon / "state.json").read_text())
        self.assertEqual(state["srv#0"]["recent_beats"], [])
        self.assertIsNone(state["srv#0"]["first_beat"])

    def test_port_down_gives_dead_verdict_regardless_of_throughput_line(self):
        # 吞吐行还在(日志没断流),但端口探测判死——判定只看端口。
        self.S.probe_port = lambda host, port, timeout=3: False
        self.S.live_sessions = lambda hosts: {"tokyo108": set()}
        latest = self.S.sample_once()
        row = latest["rows"][0]
        self.assertEqual(row["verdict"], "已挂")

    def test_idle_no_throughput_line_keeps_last_known_rate_for_display(self):
        """吞吐行断流(引擎空闲降级 debug 不打印)不算停摆,判定仍看端口;
        显示位沿用上一轮已知值,不因为这一轮没吞吐行就闪回空白。"""
        self.S.probe_port = lambda host, port, timeout=3: True
        self.S.sample_once()
        # 第二轮:日志没有新吞吐行(空闲)
        self.vllm_log.write_text("engine idle, nothing printed\n")
        latest2 = self.S.sample_once()
        row2 = latest2["rows"][0]
        self.assertEqual(row2["verdict"], "健康")
        self.assertEqual(row2["tok_out"], 671.8)  # 沿用上一轮


if __name__ == "__main__":
    unittest.main()
