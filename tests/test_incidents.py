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


if __name__ == "__main__":
    unittest.main()
