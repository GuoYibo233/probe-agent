"""Boundary tests for launch_eval.launch_and_register (ticket 11): the same four paths
as launch_probe, plus the rid derivation rule (rid = sess unchanged, including the
eval_ prefix -- F1 review: dropping the prefix would collide with the training job's
rid for the same cell)."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops"))
import launch_eval as LE  # noqa: E402


class TestLaunchAndRegister(unittest.TestCase):
    @patch("launch_eval.register_all")
    @patch("launch_eval.tmux_launch")
    @patch("launch_eval.probe_free")
    @patch("launch_eval.has_session", return_value=True)
    def test_skips_when_session_exists(self, mhas, mfree, mtmux, mreg):
        ok = LE.launch_and_register("tokyo106", "0", "eval_c2_q36_mtool",
                                     "python3 x.py", "/tmp/e.log", "/tmp/run",
                                     "tool", "c2")
        self.assertFalse(ok)
        mfree.assert_not_called()
        mtmux.assert_not_called()
        mreg.assert_not_called()

    @patch("launch_eval.register_all")
    @patch("launch_eval.tmux_launch")
    @patch("launch_eval.probe_free", return_value=(False, "busy: 999"))
    @patch("launch_eval.has_session", return_value=False)
    def test_skips_when_gpu_not_free(self, mhas, mfree, mtmux, mreg):
        ok = LE.launch_and_register("tokyo106", "0", "eval_c2_q36_mtool",
                                     "python3 x.py", "/tmp/e.log", "/tmp/run",
                                     "tool", "c2")
        self.assertFalse(ok)
        mtmux.assert_not_called()
        mreg.assert_not_called()

    @patch("launch_eval.register_all", return_value="registration receipt")
    @patch("launch_eval.tmux_launch")
    @patch("launch_eval.probe_free", return_value=(True, ""))
    @patch("launch_eval.has_session", return_value=False)
    def test_launches_and_registers_rich_piece_rid_keeps_eval_prefix(
            self, mhas, mfree, mtmux, mreg):
        ok = LE.launch_and_register("tokyo106", "0", "eval_c2_q36_mtool",
                                     "python3 x.py", "/tmp/e.log", "/tmp/run",
                                     "tool", "c2", placement="ops/x_eval.json")
        self.assertTrue(ok)
        mtmux.assert_called_once()
        reg_args, reg_kwargs = mreg.call_args
        run_id, workdir, pieces, track, cmd_display = reg_args[:5]
        # rid must not equal the same cell's training job's rid (`c2_q36_mtool`, given by
        # launch_probe.build()) -- carrying the eval_ prefix is the key to avoiding a collision,
        # not an arbitrary naming choice (F1).
        self.assertEqual(run_id, "eval_c2_q36_mtool")
        self.assertNotEqual(run_id, "c2_q36_mtool")
        self.assertEqual(track, "eval_c2")
        # RUNMETA is written by register_all (the sole writer): it lands in the head run's own
        # directory, kind is recorded as eval_tool / eval_call as appropriate, and
        # session/gpu/log/the card-scheduling table are merged into the record.
        self.assertEqual(reg_kwargs.get("outdir"), "/tmp/run")
        self.assertEqual(reg_kwargs.get("runmeta_kind"), "eval_tool")
        extra = reg_kwargs.get("runmeta_extra")
        self.assertEqual(extra["session"], "eval_c2_q36_mtool")
        self.assertEqual(extra["launch_host"], "tokyo106")
        self.assertEqual(extra["gpu"], "0")
        self.assertEqual(extra["log"], "/tmp/e.log")
        self.assertEqual(extra["placement"], "ops/x_eval.json")
        piece = pieces[0]
        self.assertEqual(piece["kind"], "eval_tool")
        self.assertEqual(piece["session"], "eval_c2_q36_mtool")
        self.assertIsNone(piece["stall_line"])
        self.assertIsNone(piece["escalate_line"])

    @patch("launch_eval.register_all", side_effect=SystemExit("run_id already in the job ledger"))
    @patch("launch_eval.tmux_launch")
    @patch("launch_eval.probe_free", return_value=(True, ""))
    @patch("launch_eval.has_session", return_value=False)
    def test_register_failure_warns_but_launch_still_reported(
            self, mhas, mfree, mtmux, mreg):
        ok = LE.launch_and_register("tokyo106", "0", "eval_c2_q36_mtool",
                                     "python3 x.py", "/tmp/e.log", "/tmp/run",
                                     "tool", "c2")
        self.assertTrue(ok)
        mtmux.assert_called_once()


if __name__ == "__main__":
    unittest.main()
