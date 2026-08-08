"""launch_eval.launch_and_register 的边界测试(工单 11)：同 launch_probe 的
四条路径,外加 rid 的推导规则(rid = sess 原样,含 eval_ 前缀——F1 复核:去掉
前缀会跟同一格训练 job 的 rid 撞车)。"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops"))
import launch_eval as LE  # noqa: E402


class TestLaunchAndRegister(unittest.TestCase):
    @patch("launch_eval.register_all")
    @patch("launch_eval.append_runmeta")
    @patch("launch_eval.tmux_launch")
    @patch("launch_eval.probe_free")
    @patch("launch_eval.has_session", return_value=True)
    def test_skips_when_session_exists(self, mhas, mfree, mtmux, mrm, mreg):
        ok = LE.launch_and_register("tokyo106", "0", "eval_c2_q36_mtool",
                                     "python3 x.py", "/tmp/e.log", "/tmp/run",
                                     "tool", "c2")
        self.assertFalse(ok)
        mfree.assert_not_called()
        mtmux.assert_not_called()
        mreg.assert_not_called()

    @patch("launch_eval.register_all")
    @patch("launch_eval.append_runmeta")
    @patch("launch_eval.tmux_launch")
    @patch("launch_eval.probe_free", return_value=(False, "占用中: 999"))
    @patch("launch_eval.has_session", return_value=False)
    def test_skips_when_gpu_not_free(self, mhas, mfree, mtmux, mrm, mreg):
        ok = LE.launch_and_register("tokyo106", "0", "eval_c2_q36_mtool",
                                     "python3 x.py", "/tmp/e.log", "/tmp/run",
                                     "tool", "c2")
        self.assertFalse(ok)
        mtmux.assert_not_called()
        mreg.assert_not_called()

    @patch("launch_eval.register_all", return_value="登记回执")
    @patch("launch_eval.append_runmeta")
    @patch("launch_eval.tmux_launch")
    @patch("launch_eval.probe_free", return_value=(True, ""))
    @patch("launch_eval.has_session", return_value=False)
    def test_launches_and_registers_rich_piece_rid_keeps_eval_prefix(
            self, mhas, mfree, mtmux, mrm, mreg):
        ok = LE.launch_and_register("tokyo106", "0", "eval_c2_q36_mtool",
                                     "python3 x.py", "/tmp/e.log", "/tmp/run",
                                     "tool", "c2")
        self.assertTrue(ok)
        mtmux.assert_called_once()
        mrm.assert_called_once()
        self.assertEqual(mrm.call_args.kwargs["kind"], "eval_tool")
        reg_args, reg_kwargs = mreg.call_args
        run_id, workdir, pieces, track, cmd_display = reg_args[:5]
        # rid 不能等于同一格训练 job 的 rid(`c2_q36_mtool`,launch_probe.build()
        # 给的)——带 eval_ 前缀是不撞车的关键,不是随手的命名选择(F1)。
        self.assertEqual(run_id, "eval_c2_q36_mtool")
        self.assertNotEqual(run_id, "c2_q36_mtool")
        self.assertEqual(track, "eval_c2")
        self.assertEqual(reg_kwargs.get("outdir"), None)
        piece = pieces[0]
        self.assertEqual(piece["kind"], "eval_tool")
        self.assertEqual(piece["session"], "eval_c2_q36_mtool")
        self.assertIsNone(piece["stall_line"])
        self.assertIsNone(piece["escalate_line"])

    @patch("launch_eval.register_all", side_effect=SystemExit("run_id 已在台账里"))
    @patch("launch_eval.append_runmeta")
    @patch("launch_eval.tmux_launch")
    @patch("launch_eval.probe_free", return_value=(True, ""))
    @patch("launch_eval.has_session", return_value=False)
    def test_register_failure_warns_but_launch_still_reported(
            self, mhas, mfree, mtmux, mrm, mreg):
        ok = LE.launch_and_register("tokyo106", "0", "eval_c2_q36_mtool",
                                     "python3 x.py", "/tmp/e.log", "/tmp/run",
                                     "tool", "c2")
        self.assertTrue(ok)
        mtmux.assert_called_once()


if __name__ == "__main__":
    unittest.main()
