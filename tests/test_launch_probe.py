"""launch_probe.launch_and_register 的边界测试(工单 11)：一格发射从
「已删掉的本地 has_session/launch」改成「import 公共件 + FREE 实探 + 自动
登记」之后，四种路径都要被测到——session 已存在 / 目标卡非 FREE / 正常发射
成功登记 / 登记失败(重复 run_id 等)只 WARN 不中断循环。"""
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops"))
import launch_probe as LP  # noqa: E402


class TestLaunchAndRegister(unittest.TestCase):
    @patch("launch_probe.register_all")
    @patch("launch_probe.append_runmeta")
    @patch("launch_probe.tmux_launch")
    @patch("launch_probe.probe_free")
    @patch("launch_probe.has_session", return_value=True)
    def test_skips_when_session_exists(self, mhas, mfree, mtmux, mrm, mreg):
        ok = LP.launch_and_register("tokyo106", "0", "sess1", "python3 x.py",
                                     "/tmp/sess1.log", "/tmp/out", "rid1", "c2")
        self.assertFalse(ok)
        mfree.assert_not_called()
        mtmux.assert_not_called()
        mreg.assert_not_called()

    @patch("launch_probe.register_all")
    @patch("launch_probe.append_runmeta")
    @patch("launch_probe.tmux_launch")
    @patch("launch_probe.probe_free", return_value=(False, "占用中: 12345"))
    @patch("launch_probe.has_session", return_value=False)
    def test_skips_when_gpu_not_free(self, mhas, mfree, mtmux, mrm, mreg):
        ok = LP.launch_and_register("tokyo106", "0", "sess1", "python3 x.py",
                                     "/tmp/sess1.log", "/tmp/out", "rid1", "c2")
        self.assertFalse(ok)
        mtmux.assert_not_called()
        mreg.assert_not_called()

    @patch("launch_probe.register_all", return_value="登记回执")
    @patch("launch_probe.append_runmeta")
    @patch("launch_probe.tmux_launch")
    @patch("launch_probe.probe_free", return_value=(True, ""))
    @patch("launch_probe.has_session", return_value=False)
    def test_launches_and_registers_rich_piece(self, mhas, mfree, mtmux, mrm, mreg):
        ok = LP.launch_and_register("tokyo106", "0", "sess1", "python3 x.py",
                                     "/tmp/sess1.log", "/tmp/out", "rid1", "c2")
        self.assertTrue(ok)
        mtmux.assert_called_once_with("tokyo106", "sess1",
                                      "cd " + str(LP.WD) +
                                      " && CUDA_VISIBLE_DEVICES=0 python3 x.py"
                                      " 2>&1 | tee /tmp/sess1.log")
        mrm.assert_called_once()
        mreg.assert_called_once()
        args, kwargs = mreg.call_args
        run_id, workdir, pieces, track, cmd_display = args[:5]
        self.assertEqual(run_id, "rid1")
        self.assertEqual(track, "probe_c2")
        self.assertEqual(kwargs.get("outdir"), None)
        self.assertEqual(len(pieces), 1)
        piece = pieces[0]
        for key in ("host", "gpus", "session", "log", "cmd", "launched_at",
                    "kind", "stall_line", "escalate_line"):
            self.assertIn(key, piece)
        self.assertEqual(piece["host"], "tokyo106")
        self.assertEqual(piece["gpus"], "0")
        self.assertEqual(piece["session"], "sess1")
        self.assertEqual(piece["kind"], "train")
        self.assertIsNone(piece["stall_line"])
        self.assertIsNone(piece["escalate_line"])

    @patch("launch_probe.register_all", side_effect=SystemExit("run_id 已在台账里"))
    @patch("launch_probe.append_runmeta")
    @patch("launch_probe.tmux_launch")
    @patch("launch_probe.probe_free", return_value=(True, ""))
    @patch("launch_probe.has_session", return_value=False)
    def test_register_failure_warns_but_launch_still_reported(
            self, mhas, mfree, mtmux, mrm, mreg):
        # 发射本身(tmux_launch)已经真实发生了；登记失败(比如重复 run_id)
        # 只 WARN，不能让异常往外抛炸掉调用方的循环。
        ok = LP.launch_and_register("tokyo106", "0", "sess1", "python3 x.py",
                                     "/tmp/sess1.log", "/tmp/out", "rid1", "c2")
        self.assertTrue(ok)
        mtmux.assert_called_once()


if __name__ == "__main__":
    unittest.main()
