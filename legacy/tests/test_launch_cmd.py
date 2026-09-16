import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops"))
import launch_cmd as LCC  # noqa: E402
import gpu_jobs  # noqa: E402


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
        # Flags after `--` (including a same-named --outdir) pass through into extra as-is, not into launch's own outdir
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
    """Piece injection (ticket 09 acceptance item): two pieces inject 0/1, multiple pieces
    on a non-shardable task are rejected, two pieces on the same machine and same card
    are rejected, --cmd mode leaves the command unchanged."""

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
        t = fake_task()  # Not marked shardable
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

    def test_overlapping_multi_gpu_pieces_rejected(self):
        # tokyo106:0,1 and tokyo106:1,2 are different strings, but both would occupy gpu1, so should be rejected
        t = fake_task(shardable=True)
        p = LCC.parse_launch_argv(
            ["faketask", "--run-id", "trun", "--track", "smoke",
             "--piece", "tokyo106:0,1", "--piece", "tokyo106:1,2"])
        with self.assertRaises(SystemExit):
            LCC.build_pieces(p, t)

    def test_disjoint_multi_gpu_pieces_same_host_allowed(self):
        # Non-overlapping cards on the same machine should be allowed
        t = fake_task(shardable=True)
        p = LCC.parse_launch_argv(
            ["faketask", "--run-id", "trun", "--track", "smoke",
             "--piece", "tokyo106:0,1", "--piece", "tokyo106:2,3"])
        pieces = LCC.build_pieces(p, t)
        self.assertEqual(len(pieces), 2)

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
    """dry-run smoke test (ticket 09 acceptance item): two pieces print two complete
    commands carrying piece numbers, and the register function is not called."""

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

    @patch("launch_cmd.gate_dirty", side_effect=lambda extra, honor_dry=True: extra)
    def test_service_without_port_rejected(self, _gd):
        """C2 (final-review): without --port, the rich piece has no port field, and the
        sampler's port-verdict chain breaks -- reject before launch outright; never let
        it go out and then silently stall."""
        with patch.dict(LCC.TASKS, {"faketask": fake_task()}):
            with self.assertRaises(SystemExit) as cm:
                LCC.cmd_launch(["faketask", "--run-id", "r", "--track", "t",
                               "--piece", "tokyo106:0", "--service",
                               "--dry-run"])
        self.assertIn("--port", str(cm.exception))


class TestCmdLaunchFullFlow(unittest.TestCase):
    """Three trunk paths: card-probe rejection / liveness-check failure not registered / successful registration."""

    @patch("launch_cmd.LC.register_all")
    @patch("launch_cmd.LC.probe_free", return_value=(False, "busy: 12345, 2048 MiB"))
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

    @patch("launch_cmd.LC.register_all", return_value="registration receipt")
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
                     "--note", "test", "--piece", "tokyo106:0"])
        self.assertEqual(rc, 0)
        mreg.assert_called_once()
        args, kwargs = mreg.call_args
        run_id, workdir, pieces, track, cmd_display = args[:5]
        self.assertEqual(run_id, "r5")
        self.assertEqual(track, "smoke")
        self.assertEqual(len(pieces), 1)
        for key in ("host", "gpus", "session", "log", "cmd", "launched_at",
                    "kind", "stall_line", "escalate_line", "task"):
            self.assertIn(key, pieces[0])
        self.assertEqual(pieces[0]["kind"], "batch")
        self.assertEqual(pieces[0]["task"], "faketask")
        self.assertEqual(kwargs.get("note"), "test")

    @patch("launch_cmd.LC.register_all", return_value="registration receipt")
    @patch("launch_cmd.LC.tmux_launch")
    @patch("launch_cmd.LC.probe_free", return_value=(True, ""))
    @patch("launch_cmd.LC.has_session", return_value=True)
    @patch("launch_cmd.gate_dirty", side_effect=lambda extra, honor_dry=True: extra)
    def test_service_with_port_registers_service_kind_and_port(
            self, _gd, _hs, _pf, mtmux, mreg):
        """C2 (final-review): --service --port goes through the full flow; the rich piece
        registered in the job ledger carries port (int) and kind=="service" -- the
        sampler's probe_port verdict chain connects, no longer stuck forever in
        warm-up."""
        with patch.dict(LCC.TASKS, {"faketask": fake_task()}):
            with patch.object(LCC, "verify_alive", return_value=(True, [])):
                rc = LCC.cmd_launch(
                    ["faketask", "--run-id", "r7", "--track", "smoke",
                     "--piece", "tokyo106:0", "--service", "--port", "8103"])
        self.assertEqual(rc, 0)
        mreg.assert_called_once()
        args, _kwargs = mreg.call_args
        pieces = args[2]
        self.assertEqual(pieces[0]["kind"], "service")
        self.assertEqual(pieces[0]["port"], 8103)

    @patch("launch_cmd.LC.register_all", return_value="registration receipt")
    @patch("launch_cmd.LC.tmux_launch")
    @patch("launch_cmd.LC.probe_free", return_value=(True, ""))
    @patch("launch_cmd.LC.has_session", return_value=True)
    @patch("launch_cmd.gate_dirty", side_effect=lambda extra, honor_dry=True: extra)
    def test_success_does_not_persist_raw_env_values(
            self, _gd, _hs, _pf, mtmux, mreg):
        """N1 regression: when a task defines a non-empty env (possibly holding secrets), the
        rich piece registered in the job ledger must not carry env's actual key-value
        pairs as-is -- only the task name may be stored; the env values stay only in
        this launch's local variables/inner command, never entering the git-tracked
        ops/jobs.json."""
        with patch.dict(LCC.TASKS, {"sekrit": fake_task(
                env={"HF_TOKEN": "shh-do-not-commit-me"})}):
            with patch.object(LCC, "verify_alive", return_value=(True, [])):
                rc = LCC.cmd_launch(
                    ["sekrit", "--run-id", "r6", "--track", "smoke",
                     "--piece", "tokyo106:0"])
        self.assertEqual(rc, 0)
        _host, _sess, inner = mtmux.call_args[0]
        self.assertIn("HF_TOKEN=shh-do-not-commit-me", inner)  # The launch itself still carries env as usual

        args, _kwargs = mreg.call_args
        pieces = args[2]
        self.assertNotIn("env", pieces[0])
        self.assertEqual(pieces[0]["task"], "sekrit")
        dumped = repr(pieces[0])
        self.assertNotIn("shh-do-not-commit-me", dumped)


class TestCmdRefire(unittest.TestCase):
    """Refire (ticket 10 acceptance item): a live session is rejected, a non-FREE card is
    rejected, and on the success path the job ledger piece's log/launched_at are
    updated while cmd/session stay unchanged and no second job appears."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="launch_cmd_refire_")
        self._orig_reg_path = gpu_jobs.REG_PATH
        gpu_jobs.REG_PATH = os.path.join(self.tmpdir, "jobs.json")
        gpu_jobs.mutate_reg(lambda reg: reg["active"].append({
            "name": "rrun", "workdir": "/tmp/wd", "note": None,
            "started_at": "2026-08-08 00:00",
            "pieces": [{
                "host": "tokyo106", "gpus": "0", "session": "new1_rrun_t106g0",
                "log": "/tmp/wd/logs/new1_rrun_t106g0.log",
                "cmd": "python3 foo.py --x 1", "launched_at": 1000.0,
                "kind": "batch", "stall_line": None, "escalate_line": None,
            }],
        }))

    def tearDown(self):
        gpu_jobs.REG_PATH = self._orig_reg_path
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch("launch_cmd.gate_dirty", side_effect=lambda extra, honor_dry=True: extra)
    @patch("launch_cmd.LC.has_session", return_value=True)
    def test_alive_session_rejected(self, _hs, _gd):
        with self.assertRaises(SystemExit):
            LCC.cmd_launch(["--refire", "rrun", "--idx", "0"])
        reg = gpu_jobs.load_reg()
        self.assertEqual(reg["active"][0]["pieces"][0]["launched_at"], 1000.0)

    @patch("launch_cmd.gate_dirty", side_effect=lambda extra, honor_dry=True: extra)
    @patch("launch_cmd.LC.probe_free", return_value=(False, "busy: 1, 1 MiB"))
    @patch("launch_cmd.LC.has_session", return_value=False)
    def test_non_free_rejected(self, _hs, _pf, _gd):
        with self.assertRaises(SystemExit):
            LCC.cmd_launch(["--refire", "rrun", "--idx", "0"])
        reg = gpu_jobs.load_reg()
        self.assertEqual(reg["active"][0]["pieces"][0]["launched_at"], 1000.0)

    @patch("launch_cmd.LC.tmux_launch")
    @patch("launch_cmd.gate_dirty", side_effect=lambda extra, honor_dry=True: extra)
    @patch("launch_cmd.LC.probe_free", return_value=(True, ""))
    @patch("launch_cmd.LC.has_session", return_value=False)
    def test_success_updates_piece_no_new_job(self, _hs, _pf, _gd, mtmux):
        rc = LCC.cmd_launch(["--refire", "rrun", "--idx", "0"])
        self.assertEqual(rc, 0)
        mtmux.assert_called_once()
        host, sess, inner = mtmux.call_args[0]
        self.assertEqual(host, "tokyo106")
        self.assertEqual(sess, "new1_rrun_t106g0")
        self.assertIn("python3 foo.py --x 1", inner)

        reg = gpu_jobs.load_reg()
        self.assertEqual(len(reg["active"]), 1)  # A refire is not a new task; no second job appears
        job = reg["active"][0]
        self.assertEqual(job["name"], "rrun")
        piece = job["pieces"][0]
        self.assertEqual(piece["cmd"], "python3 foo.py --x 1")  # Command unchanged
        self.assertEqual(piece["session"], "new1_rrun_t106g0")  # Session name unchanged
        self.assertNotEqual(piece["log"], "/tmp/wd/logs/new1_rrun_t106g0.log")
        self.assertGreater(piece["launched_at"], 1000.0)

    @patch("launch_cmd.LC.tmux_launch")
    @patch("launch_cmd.gate_dirty", side_effect=lambda extra, honor_dry=True: extra)
    @patch("launch_cmd.LC.probe_free", return_value=(True, ""))
    @patch("launch_cmd.LC.has_session", return_value=False)
    def test_env_prefix_restored(self, _hs, _pf, _gd, mtmux):
        """F1 regression, the shape after the N1 fix: the ledger piece does not store env's
        actual key-value pairs (finding N1: writing env into the git-tracked jobs.json
        risks leaking it), only the task name; a refire must use this task name to look
        up the *current* TASKS[task]["env"], compute it fresh, pass it through, and
        restore it as-is into the tmux inner command -- it must not be silently dropped."""
        gpu_jobs.mutate_reg(lambda reg: reg["active"].append({
            "name": "erun", "workdir": "/tmp/wd", "note": None,
            "started_at": "2026-08-08 00:00",
            "pieces": [{
                "host": "tokyo106", "gpus": "0", "session": "new1_erun_t106g0",
                "log": "/tmp/wd/logs/new1_erun_t106g0.log",
                "cmd": "python3 foo.py --x 1", "launched_at": 1000.0,
                "kind": "batch", "stall_line": None, "escalate_line": None,
                "task": "envtask",
            }],
        }))
        with patch.dict(LCC.TASKS, {"envtask": fake_task(
                env={"FOO": "bar", "BAZ": "qux"})}):
            rc = LCC.cmd_launch(["--refire", "erun", "--idx", "0"])
        self.assertEqual(rc, 0)
        _host, _sess, inner = mtmux.call_args[0]
        self.assertIn("FOO=bar", inner)
        self.assertIn("BAZ=qux", inner)
        self.assertIn("python3 foo.py --x 1", inner)

    @patch("launch_cmd.LC.tmux_launch")
    @patch("launch_cmd.gate_dirty", side_effect=lambda extra, honor_dry=True: extra)
    @patch("launch_cmd.LC.probe_free", return_value=(True, ""))
    @patch("launch_cmd.LC.has_session", return_value=False)
    def test_missing_task_field_defaults_empty_env(self, _hs, _pf, _gd, mtmux):
        """A piece in an old ledger (registered before this fix) has no task field; a refire
        must not error over this -- treat a failed lookup as an empty dict."""
        rc = LCC.cmd_launch(["--refire", "rrun", "--idx", "0"])
        self.assertEqual(rc, 0)
        _host, _sess, inner = mtmux.call_args[0]
        self.assertIn("python3 foo.py --x 1", inner)

    @patch("launch_cmd.LC.tmux_launch")
    @patch("launch_cmd.gate_dirty", side_effect=lambda extra, honor_dry=True: extra)
    @patch("launch_cmd.LC.probe_free", return_value=(True, ""))
    @patch("launch_cmd.LC.has_session", return_value=False)
    def test_unknown_task_field_defaults_empty_env(self, _hs, _pf, _gd, mtmux):
        """The task name stored in the ledger is not in the current TASKS (the task was later
        retired); a refire must not error over this either -- treat a failed lookup as
        an empty dict, and cmd is still refired unchanged."""
        gpu_jobs.mutate_reg(lambda reg: reg["active"].append({
            "name": "grun", "workdir": "/tmp/wd", "note": None,
            "started_at": "2026-08-08 00:00",
            "pieces": [{
                "host": "tokyo106", "gpus": "0", "session": "new1_grun_t106g0",
                "log": "/tmp/wd/logs/new1_grun_t106g0.log",
                "cmd": "python3 foo.py --x 1", "launched_at": 1000.0,
                "kind": "batch", "stall_line": None, "escalate_line": None,
                "task": "gone-task",
            }],
        }))
        rc = LCC.cmd_launch(["--refire", "grun", "--idx", "0"])
        self.assertEqual(rc, 0)
        _host, _sess, inner = mtmux.call_args[0]
        self.assertIn("python3 foo.py --x 1", inner)

    @patch("launch_cmd.LC.tmux_launch")
    @patch("launch_cmd.gate_dirty", side_effect=lambda extra, honor_dry=True: extra)
    @patch("launch_cmd.LC.probe_free", return_value=(True, ""))
    @patch("launch_cmd.LC.has_session", return_value=False)
    def test_piece_override_changes_target_gpu(self, _hs, mprobe, _gd, mtmux):
        rc = LCC.cmd_launch(
            ["--refire", "rrun", "--idx", "0", "--piece", "tokyo107:2"])
        self.assertEqual(rc, 0)
        mprobe.assert_called_once_with("tokyo107", "2")
        piece = gpu_jobs.load_reg()["active"][0]["pieces"][0]
        self.assertEqual(piece["host"], "tokyo107")
        self.assertEqual(piece["gpus"], "2")

    @patch("launch_cmd.gate_dirty", side_effect=lambda extra, honor_dry=True: extra)
    def test_unknown_run_id_rejected(self, _gd):
        with self.assertRaises(SystemExit):
            LCC.cmd_launch(["--refire", "no-such-run", "--idx", "0"])

    @patch("launch_cmd.gate_dirty", side_effect=lambda extra, honor_dry=True: extra)
    def test_idx_out_of_range_rejected(self, _gd):
        with self.assertRaises(SystemExit):
            LCC.cmd_launch(["--refire", "rrun", "--idx", "5"])


if __name__ == "__main__":
    unittest.main()
