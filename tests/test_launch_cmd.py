import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops"))
import launch_cmd as LCC  # noqa: E402


def fake_task(**kw):
    base = dict(py="sys", script="ops/launch_cmd.py")
    base.update(kw)
    return base


class TestParseLaunchArgv(unittest.TestCase):
    def test_task_positional_and_flags(self):
        p = LCC.parse_launch_argv(
            ["collect-aw", "--run-id", "r1", "--track", "smoke",
             "--piece", "tokyo106:0", "--piece", "tokyo106:1",
             "--dry-run", "--allow-dirty",
             "--", "--base-url", "http://x/v1", "--outdir", "/tmp/x"])
        self.assertEqual(p["task"], "collect-aw")
        self.assertIsNone(p["cmd"])
        self.assertEqual(p["run_id"], "r1")
        self.assertEqual(p["track"], "smoke")
        self.assertEqual(p["pieces"], ["tokyo106:0", "tokyo106:1"])
        self.assertTrue(p["dry_run"])
        self.assertTrue(p["allow_dirty"])
        # `--` 之后的旗标(含同名 --outdir)原样进 extra,不进 launch 自己的 outdir
        self.assertIsNone(p["outdir"])
        self.assertEqual(p["extra"],
                         ["--base-url", "http://x/v1", "--outdir", "/tmp/x"])

    def test_cmd_mode_flags(self):
        p = LCC.parse_launch_argv(
            ["--cmd", "python3 foo.py --x 1", "--run-id", "r2",
             "--workdir", "/tmp/wd", "--piece", "tokyo106:0",
             "--track", "t", "--service"])
        self.assertIsNone(p["task"])
        self.assertEqual(p["cmd"], "python3 foo.py --x 1")
        self.assertEqual(p["workdir"], "/tmp/wd")
        self.assertTrue(p["service"])


class TestBuildPieces(unittest.TestCase):
    """分片注入(工单 09 验收项):两分片注 0/1、非 shardable 多分片拒绝、
    同机同卡两分片拒绝、--cmd 模式命令原样。"""

    def test_shardable_two_pieces_get_shard_flags(self):
        t = fake_task(shardable=True)
        p = LCC.parse_launch_argv(
            ["faketask", "--run-id", "trun", "--track", "smoke",
             "--piece", "tokyo106:0", "--piece", "tokyo106:1"])
        pieces = LCC.build_pieces(p, t)
        self.assertEqual(len(pieces), 2)
        self.assertIn("--shard-id 0 --num-shards 2", pieces[0]["cmd"])
        self.assertIn("--shard-id 1 --num-shards 2", pieces[1]["cmd"])

    def test_non_shardable_rejects_multi_piece(self):
        t = fake_task()  # 没标 shardable
        p = LCC.parse_launch_argv(
            ["faketask", "--run-id", "trun", "--track", "smoke",
             "--piece", "tokyo106:0", "--piece", "tokyo106:1"])
        with self.assertRaises(SystemExit):
            LCC.build_pieces(p, t)

    def test_duplicate_host_gpu_piece_rejected(self):
        t = fake_task(shardable=True)
        p = LCC.parse_launch_argv(
            ["faketask", "--run-id", "trun", "--track", "smoke",
             "--piece", "tokyo106:0", "--piece", "tokyo106:0"])
        with self.assertRaises(SystemExit):
            LCC.build_pieces(p, t)

    def test_session_name_format(self):
        t = fake_task()
        p = LCC.parse_launch_argv(
            ["faketask", "--run-id", "trun", "--track", "smoke",
             "--piece", "tokyo108:0,1"])
        pieces = LCC.build_pieces(p, t)
        self.assertEqual(pieces[0]["session"], "new1_trun_t108g0-1")

    def test_cmd_mode_command_verbatim_no_registry(self):
        p = LCC.parse_launch_argv(
            ["--cmd", "echo hi", "--run-id", "trun", "--workdir", "/tmp/wd",
             "--track", "smoke", "--piece", "tokyo106:0"])
        pieces = LCC.build_pieces(p, None)
        self.assertEqual(pieces[0]["cmd"], "echo hi")
        self.assertEqual(pieces[0]["workdir"], "/tmp/wd")

    def test_no_piece_rejected(self):
        t = fake_task()
        p = LCC.parse_launch_argv(["faketask", "--run-id", "trun", "--track", "s"])
        with self.assertRaises(SystemExit):
            LCC.build_pieces(p, t)


class TestVerifyAlive(unittest.TestCase):
    @patch("launch_cmd.LC.has_session", return_value=True)
    def test_ok_when_alive_and_no_traceback(self, _hs):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".log") as f:
            f.write(b"hello\n")
            f.flush()
            pieces = [dict(host="tokyo106", gpus="0", session="s1", log=f.name)]
            ok, failed = LCC.verify_alive(pieces, window_s=0.1, poll_s=0.05)
        self.assertTrue(ok)
        self.assertEqual(failed, [])

    @patch("launch_cmd.LC.has_session", return_value=False)
    def test_fails_when_session_gone(self, _hs):
        pieces = [dict(host="tokyo106", gpus="0", session="s1",
                       log="/nonexistent/path.log")]
        ok, failed = LCC.verify_alive(pieces, window_s=0.1, poll_s=0.05)
        self.assertFalse(ok)
        self.assertEqual(len(failed), 1)

    @patch("launch_cmd.LC.has_session", return_value=True)
    def test_fails_on_traceback_in_tail(self, _hs):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".log") as f:
            f.write(b"Traceback (most recent call last):\n")
            f.flush()
            pieces = [dict(host="tokyo106", gpus="0", session="s1", log=f.name)]
            ok, failed = LCC.verify_alive(pieces, window_s=0.1, poll_s=0.05)
        self.assertFalse(ok)


class TestCmdLaunchDryRun(unittest.TestCase):
    """dry-run 冒烟(工单 09 验收项):两分片打出两条带分片编号的完整命令,
    登记函数没被调。"""

    @patch("launch_cmd.LC.register_all")
    @patch("launch_cmd.gate_dirty", side_effect=lambda extra, honor_dry=True: extra)
    def test_dry_run_prints_shard_commands_and_skips_register(self, _gd, mreg):
        with patch.dict(LCC.TASKS, {"faketask": fake_task(shardable=True)}):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = LCC.cmd_launch(
                    ["faketask", "--run-id", "smoke_x", "--track", "smoke",
                     "--piece", "tokyo106:0", "--piece", "tokyo106:1",
                     "--dry-run", "--allow-dirty",
                     "--", "--base-url", "http://x/v1", "--model", "m"])
        out = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("--shard-id 0 --num-shards 2", out)
        self.assertIn("--shard-id 1 --num-shards 2", out)
        mreg.assert_not_called()

    @patch("launch_cmd.LC.probe_free")
    @patch("launch_cmd.LC.tmux_launch")
    @patch("launch_cmd.gate_dirty", side_effect=lambda extra, honor_dry=True: extra)
    def test_dry_run_does_not_probe_or_launch(self, _gd, mtmux, mprobe):
        with patch.dict(LCC.TASKS, {"faketask": fake_task(shardable=True)}):
            buf = io.StringIO()
            with redirect_stdout(buf):
                LCC.cmd_launch(
                    ["faketask", "--run-id", "smoke_y", "--track", "smoke",
                     "--piece", "tokyo106:0", "--dry-run"])
        mprobe.assert_not_called()
        mtmux.assert_not_called()


class TestCmdLaunchValidation(unittest.TestCase):
    @patch("launch_cmd.gate_dirty", side_effect=lambda extra, honor_dry=True: extra)
    def test_unknown_task_rejected(self, _gd):
        with self.assertRaises(SystemExit):
            LCC.cmd_launch(["not-a-real-task", "--run-id", "r", "--track", "t",
                            "--piece", "tokyo106:0", "--dry-run"])

    @patch("launch_cmd.gate_dirty", side_effect=lambda extra, honor_dry=True: extra)
    def test_missing_run_id_rejected(self, _gd):
        with patch.dict(LCC.TASKS, {"faketask": fake_task()}):
            with self.assertRaises(SystemExit):
                LCC.cmd_launch(["faketask", "--track", "t",
                               "--piece", "tokyo106:0", "--dry-run"])

    @patch("launch_cmd.gate_dirty", side_effect=lambda extra, honor_dry=True: extra)
    def test_missing_track_rejected(self, _gd):
        with patch.dict(LCC.TASKS, {"faketask": fake_task()}):
            with self.assertRaises(SystemExit):
                LCC.cmd_launch(["faketask", "--run-id", "r",
                               "--piece", "tokyo106:0", "--dry-run"])


class TestCmdLaunchFullFlow(unittest.TestCase):
    """探卡拒绝 / 验活失败不登记 / 成功登记三条主干路径。"""

    @patch("launch_cmd.LC.register_all")
    @patch("launch_cmd.LC.probe_free", return_value=(False, "占用中: 12345, 2048 MiB"))
    @patch("launch_cmd.gate_dirty", side_effect=lambda extra, honor_dry=True: extra)
    def test_non_free_piece_rejects_all_and_no_register(self, _gd, _pf, mreg):
        with patch.dict(LCC.TASKS, {"faketask": fake_task()}):
            with self.assertRaises(SystemExit):
                LCC.cmd_launch(["faketask", "--run-id", "r3", "--track", "t",
                               "--piece", "tokyo106:0"])
        mreg.assert_not_called()

    @patch("launch_cmd.LC.register_all")
    @patch("launch_cmd.LC.tmux_launch")
    @patch("launch_cmd.LC.probe_free", return_value=(True, ""))
    @patch("launch_cmd.LC.has_session", return_value=False)
    @patch("launch_cmd.gate_dirty", side_effect=lambda extra, honor_dry=True: extra)
    def test_verify_alive_failure_skips_register(
            self, _gd, _hs, _pf, mtmux, mreg):
        with patch.dict(LCC.TASKS, {"faketask": fake_task()}):
            with patch.object(LCC, "verify_alive",
                              return_value=(False, [(dict(host="tokyo106", gpus="0",
                                                          session="new1_r4_t106g0",
                                                          log="/nonexistent.log"), "")])):
                rc = LCC.cmd_launch(["faketask", "--run-id", "r4", "--track", "t",
                                    "--piece", "tokyo106:0"])
        self.assertEqual(rc, 1)
        mtmux.assert_called_once()
        mreg.assert_not_called()

    @patch("launch_cmd.LC.register_all", return_value="登记回执")
    @patch("launch_cmd.LC.tmux_launch")
    @patch("launch_cmd.LC.probe_free", return_value=(True, ""))
    @patch("launch_cmd.LC.has_session", return_value=True)
    @patch("launch_cmd.gate_dirty", side_effect=lambda extra, honor_dry=True: extra)
    def test_success_registers_rich_pieces(
            self, _gd, _hs, _pf, mtmux, mreg):
        with patch.dict(LCC.TASKS, {"faketask": fake_task()}):
            with patch.object(LCC, "verify_alive", return_value=(True, [])):
                rc = LCC.cmd_launch(
                    ["faketask", "--run-id", "r5", "--track", "smoke",
                     "--note", "测试", "--piece", "tokyo106:0"])
        self.assertEqual(rc, 0)
        mreg.assert_called_once()
        args, kwargs = mreg.call_args
        run_id, workdir, pieces, track, cmd_display = args[:5]
        self.assertEqual(run_id, "r5")
        self.assertEqual(track, "smoke")
        self.assertEqual(len(pieces), 1)
        for key in ("host", "gpus", "session", "log", "cmd", "launched_at",
                    "kind", "stall_line", "escalate_line"):
            self.assertIn(key, pieces[0])
        self.assertEqual(pieces[0]["kind"], "batch")
        self.assertEqual(kwargs.get("note"), "测试")


if __name__ == "__main__":
    unittest.main()
