"""事故触发(工单 12,实施计划 Task 14)——纯函数部分。

测试缝(spec `Testing Decisions`):"事故触发的规则收在纯函数里单测"——
should_trigger 压满四种情形,build_incident_prompt 检查内容字样。

`spawn_agent`/`maybe_trigger_incidents` 的实装与这两个函数的集成测试
本轮未完成(见工单报告"自查发现与存疑"一节)——不在本文件范围内。
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "ops"))

import sampler  # noqa: E402
import verdicts  # noqa: E402


def _row(job="x", idx=0, verdict=verdicts.V_DEAD, escalated=True, **kw):
    r = {"job": job, "idx": idx, "host": "tokyo106", "gpus": "0",
         "session": "new1_x_t106g0", "verdict": verdict,
         "escalated": escalated, "log": "/tmp/x.log"}
    r.update(kw)
    return r


def _ps(incident_open=False, refires=0):
    return {"incident_open": incident_open, "refires": refires}


class TestShouldTrigger(unittest.TestCase):
    def test_first_dead_allows_refire(self):
        trig, allow = sampler.should_trigger(
            _row(verdict=verdicts.V_DEAD, escalated=True), _ps(refires=0))
        self.assertEqual((trig, allow), (True, True))

    def test_dead_already_refired_denies_refire(self):
        trig, allow = sampler.should_trigger(
            _row(verdict=verdicts.V_DEAD, escalated=True), _ps(refires=1))
        self.assertEqual((trig, allow), (True, False))

    def test_incident_already_open_does_not_retrigger(self):
        trig, allow = sampler.should_trigger(
            _row(verdict=verdicts.V_DEAD, escalated=True),
            _ps(incident_open="x#0@123", refires=0))
        self.assertFalse(trig)

    def test_stall_below_escalate_line_does_not_trigger(self):
        trig, allow = sampler.should_trigger(
            _row(verdict=verdicts.V_STALL, escalated=False), _ps())
        self.assertFalse(trig)

    def test_stall_past_escalate_line_triggers_without_refire(self):
        trig, allow = sampler.should_trigger(
            _row(verdict=verdicts.V_STALL, escalated=True), _ps(refires=0))
        self.assertEqual((trig, allow), (True, False))


class TestBuildIncidentPrompt(unittest.TestCase):
    def test_allow_refire_contains_refire_command(self):
        row = _row(verdict=verdicts.V_DEAD, log="/tmp/x.log")
        prompt = sampler.build_incident_prompt(row, allow_refire=True)
        self.assertIn("/tmp/x.log", prompt)
        self.assertIn("python3 run.py gpu-jobs json", prompt)
        self.assertIn("python3 run.py launch --refire x --idx 0", prompt)

    def test_deny_refire_contains_no_refire_wording(self):
        row = _row(verdict=verdicts.V_DEAD, log="/tmp/x.log")
        prompt = sampler.build_incident_prompt(row, allow_refire=False)
        self.assertIn("/tmp/x.log", prompt)
        self.assertIn("python3 run.py gpu-jobs json", prompt)
        self.assertIn("只验尸,不许再发射任何东西", prompt)
        self.assertNotIn("--refire x --idx 0", prompt)


class TestMaybeTriggerIncidents(unittest.TestCase):
    """触发闭环:mock 掉 spawn_agent(不拉真进程),查事故记录、
    incident_open 置位、二次调用不重触发。落盘用临时 MONITOR_DIR。"""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self._old_dir = sampler.MONITOR_DIR
        sampler.MONITOR_DIR = pathlib.Path(self._tmp.name)
        self._spawned = []
        self._old_spawn = sampler.spawn_agent
        sampler.spawn_agent = lambda prompt, out: self._spawned.append(
            (prompt, str(out)))

    def tearDown(self):
        sampler.MONITOR_DIR = self._old_dir
        sampler.spawn_agent = self._old_spawn
        self._tmp.cleanup()

    def test_trigger_writes_record_and_sets_open(self):
        row = _row()
        st = {sampler.piece_key("x", 0): sampler._new_piece_state(0.0)}
        sampler.maybe_trigger_incidents([row], st)
        self.assertEqual(len(self._spawned), 1)
        prompt, out = self._spawned[0]
        self.assertIn("/tmp/x.log", prompt)
        self.assertIn("--refire", prompt)
        recs = sampler.read_incidents_tail()
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["job"], "x")
        self.assertTrue(recs[0]["allow_refire"])
        self.assertEqual(recs[0]["out"], out)
        self.assertTrue(st[sampler.piece_key("x", 0)]["incident_open"])

    def test_second_round_does_not_retrigger(self):
        row = _row()
        st = {sampler.piece_key("x", 0): sampler._new_piece_state(0.0)}
        sampler.maybe_trigger_incidents([row], st)
        sampler.maybe_trigger_incidents([row], st)
        self.assertEqual(len(self._spawned), 1)
        self.assertEqual(len(sampler.read_incidents_tail()), 1)

    def test_healthy_row_never_triggers(self):
        row = _row(verdict=verdicts.V_OK, escalated=False)
        st = {sampler.piece_key("x", 0): sampler._new_piece_state(0.0)}
        sampler.maybe_trigger_incidents([row], st)
        self.assertEqual(self._spawned, [])


class TestSpawnAgentArgs(unittest.TestCase):
    """spawn_agent 的子进程参数:mock Popen,断言无头旗标组合与重定向。"""

    def test_popen_args(self):
        import os
        import tempfile
        calls = []

        class FakePopen:
            def __init__(self, argv, **kw):
                calls.append((argv, kw))

        old = sampler.subprocess.Popen
        sampler.subprocess.Popen = FakePopen
        # tests/__init__ 全局设了 NEW1_NO_SPAWN(C1 兜底开关),这里要测的
        # 正是"真发射时的参数",临时摘掉,测完还原
        saved_env = os.environ.pop("NEW1_NO_SPAWN", None)
        try:
            with tempfile.TemporaryDirectory() as d:
                sampler.spawn_agent("PROMPT", pathlib.Path(d) / "a.out")
        finally:
            sampler.subprocess.Popen = old
            if saved_env is not None:
                os.environ["NEW1_NO_SPAWN"] = saved_env
        argv, kw = calls[0]
        # C3 起 argv[0] 是 shutil.which 解析出的绝对路径,不再是裸字符串
        self.assertTrue(argv[0].endswith("claude"), argv[0])
        self.assertEqual(argv[1:3], ["-p", "PROMPT"])
        model_i = argv.index("--model")
        self.assertEqual(argv[model_i + 1], "opus")
        self.assertIn("--dangerously-skip-permissions", argv)
        self.assertTrue(kw["start_new_session"])
        self.assertEqual(kw["stdin"], sampler.subprocess.DEVNULL)


if __name__ == "__main__":
    unittest.main()
