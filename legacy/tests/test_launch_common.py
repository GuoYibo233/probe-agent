import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops"))
import gpu_jobs  # noqa: E402
import launch_common as LC  # noqa: E402

# `launch_common.subprocess` is the global `subprocess` module itself (not a copy of
# it); patch("launch_common.subprocess.run") is equivalent to globally patching
# subprocess.run -- this also hits the real git-probe call inside
# runmeta.append_runmeta. Keep one unpatched real copy, and let calls other than
# record.py pass through unchanged in tests that involve RUNMETA.
_REAL_RUN = subprocess.run


def _fake_record_call(argv, *a, **kw):
    if any("record.py" in str(x) for x in argv):
        return MagicMock(returncode=0)
    return _REAL_RUN(argv, *a, **kw)


def _fake_record_fail(argv, *a, **kw):
    """record.py rejects (rc=1); other calls (the git probe inside RUNMETA) pass through unchanged."""
    if any("record.py" in str(x) for x in argv):
        return MagicMock(returncode=1)
    return _REAL_RUN(argv, *a, **kw)


def rich_piece(**kw):
    base = dict(host="tokyo106", gpus="0", session="new1_trun_t106g0",
                log="/tmp/new1_trun_t106g0.log", cmd="python3 foo.py --x 1",
                launched_at=time.time(), kind="batch",
                stall_line=None, escalate_line=None)
    base.update(kw)
    return base


class TestLocalAndSession(unittest.TestCase):
    @patch("launch_common.subprocess.run")
    def test_local_host_applies_alias(self, mrun):
        mrun.return_value = MagicMock(stdout="shiga\n")
        self.assertEqual(LC.local_host(), "tokyo105")

    @patch("launch_common.local_host", return_value="tokyo107")
    @patch("launch_common.subprocess.run")
    def test_has_session_local_uses_bash(self, mrun, _lh):
        mrun.return_value = MagicMock(returncode=0)
        self.assertTrue(LC.has_session("tokyo107", "sess1"))
        argv = mrun.call_args[0][0]
        self.assertEqual(argv[0], "bash")

    @patch("launch_common.local_host", return_value="tokyo107")
    @patch("launch_common.subprocess.run")
    def test_has_session_remote_uses_ssh(self, mrun, _lh):
        mrun.return_value = MagicMock(returncode=1)
        self.assertFalse(LC.has_session("tokyo106", "sess1"))
        argv = mrun.call_args[0][0]
        self.assertEqual(argv[0], "ssh")
        self.assertIn("tokyo106", argv)

    @patch("launch_common.local_host", return_value="tokyo107")
    @patch("launch_common.subprocess.run")
    def test_tmux_launch_builds_new_session_cmd(self, mrun, _lh):
        mrun.return_value = MagicMock(returncode=0)
        LC.tmux_launch("tokyo106", "sess1", "cd /x && python3 y.py")
        argv = mrun.call_args[0][0]
        self.assertEqual(argv[0], "ssh")
        self.assertIn("tmux new-session -d -s sess1", argv[-1])


class TestProbeFree(unittest.TestCase):
    """Probing a card: three inputs -- free / occupied / probe timeout -- map to three returns (ticket acceptance item)."""

    @patch("launch_common.subprocess.run")
    def test_free_when_stdout_empty(self, mrun):
        mrun.return_value = MagicMock(returncode=0, stdout="", stderr="")
        ok, why = LC.probe_free("tokyo106", "0")
        self.assertTrue(ok)
        self.assertEqual(why, "")

    @patch("launch_common.subprocess.run")
    def test_occupied_when_stdout_has_process(self, mrun):
        mrun.return_value = MagicMock(
            returncode=0,
            stdout="12345, 2048 MiB\n67890, 1024 MiB\n", stderr="")
        ok, why = LC.probe_free("tokyo106", "0")
        self.assertFalse(ok)
        self.assertIn("busy", why)
        self.assertIn("12345", why)

    @patch("launch_common.subprocess.run")
    def test_probe_fails_on_timeout(self, mrun):
        mrun.side_effect = subprocess.TimeoutExpired(cmd="ssh", timeout=15)
        ok, why = LC.probe_free("tokyo106", "0")
        self.assertFalse(ok)
        self.assertIn("probe failed", why)

    @patch("launch_common.subprocess.run")
    def test_probe_fails_on_nonzero_rc(self, mrun):
        mrun.return_value = MagicMock(returncode=255, stdout="",
                                       stderr="ssh: connect refused")
        ok, why = LC.probe_free("tokyo106", "0")
        self.assertFalse(ok)
        self.assertIn("probe failed", why)


class TestRegisterAll(unittest.TestCase):
    """Registration: the rich piece appears in the ledger with all fields; a second call with a duplicate run_id is rejected (ticket acceptance item)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="launch_common_test_")
        self._orig_reg_path = gpu_jobs.REG_PATH
        gpu_jobs.REG_PATH = os.path.join(self.tmpdir, "jobs.json")

    def tearDown(self):
        gpu_jobs.REG_PATH = self._orig_reg_path
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch("launch_common.subprocess.run")
    def test_ledger_gets_rich_piece_full_fields(self, mrun):
        mrun.return_value = MagicMock(returncode=0)
        pieces = [rich_piece()]
        receipt = LC.register_all("trun_rich", "/tmp/wd", pieces, "smoke",
                                   "python3 foo.py --x 1", note="for testing",
                                   monitor={"warmup_s": 1800})
        self.assertIsInstance(receipt, str)
        reg = gpu_jobs.load_reg()
        self.assertEqual(len(reg["active"]), 1)
        job = reg["active"][0]
        self.assertEqual(job["name"], "trun_rich")
        self.assertEqual(job["note"], "for testing")
        self.assertEqual(job["monitor"], {"warmup_s": 1800})
        p = job["pieces"][0]
        for key in ("host", "gpus", "session", "log", "cmd", "launched_at",
                    "kind", "stall_line", "escalate_line"):
            self.assertIn(key, p)

    @patch("launch_common.subprocess.run")
    def test_duplicate_run_id_rejected_on_second_call(self, mrun):
        mrun.return_value = MagicMock(returncode=0)
        pieces = [rich_piece()]
        LC.register_all("trun_dup", "/tmp/wd", pieces, "smoke", "cmd")
        with self.assertRaises(SystemExit):
            LC.register_all("trun_dup", "/tmp/wd", pieces, "smoke", "cmd")
        reg = gpu_jobs.load_reg()
        self.assertEqual(len(reg["active"]), 1)

    @patch("launch_common.subprocess.run")
    def test_no_monitor_key_when_not_given(self, mrun):
        mrun.return_value = MagicMock(returncode=0)
        pieces = [rich_piece()]
        LC.register_all("trun_nomon", "/tmp/wd", pieces, "smoke", "cmd")
        job = gpu_jobs.load_reg()["active"][0]
        self.assertNotIn("monitor", job)

    @patch("launch_common.subprocess.run")
    def test_record_failure_aborts_but_ledger_already_written(self, mrun):
        mrun.return_value = MagicMock(returncode=1)
        pieces = [rich_piece()]
        with self.assertRaises(SystemExit):
            LC.register_all("trun_recfail", "/tmp/wd", pieces, "smoke", "cmd")
        reg = gpu_jobs.load_reg()
        self.assertTrue(any(j["name"] == "trun_recfail" for j in reg["active"]))

    @patch("launch_common.subprocess.run", side_effect=_fake_record_call)
    def test_outdir_given_writes_runmeta(self, mrun):
        outdir = os.path.join(self.tmpdir, "out")
        pieces = [rich_piece()]
        receipt = LC.register_all("trun_out", "/tmp/wd", pieces, "smoke",
                                   "cmd", outdir=outdir)
        self.assertTrue(os.path.exists(os.path.join(outdir, "RUNMETA.json")))
        self.assertIn("RUNMETA", receipt)

    @patch("launch_common.subprocess.run")
    def test_no_outdir_warns_instead_of_writing(self, mrun):
        mrun.return_value = MagicMock(returncode=0)
        pieces = [rich_piece()]
        receipt = LC.register_all("trun_noout", "/tmp/wd", pieces, "smoke", "cmd")
        self.assertIn("WARN", receipt)
        self.assertIn("--outdir", receipt)

    @patch("launch_common.subprocess.run", side_effect=_fake_record_fail)
    def test_runmeta_written_even_when_record_refuses(self, mrun):
        # RUNMETA comes first among the three registrations: the launch has already really
        # happened, so pinning the outputs to the code lands first -- even if record.py later
        # rejects (e.g. a duplicate run_id), that must not drag RUNMETA down with it
        # (from the 2026-08-26 np821 b17_cgen refire incident).
        outdir = os.path.join(self.tmpdir, "out_recfail")
        pieces = [rich_piece()]
        with self.assertRaises(SystemExit):
            LC.register_all("trun_rm_first", "/tmp/wd", pieces, "smoke",
                            "cmd", outdir=outdir)
        self.assertTrue(os.path.exists(os.path.join(outdir, "RUNMETA.json")))

    @patch("launch_common.subprocess.run", side_effect=_fake_record_call)
    def test_runmeta_kind_and_extra_land_in_entry(self, mrun):
        # The card-scheduling launcher hands its own kind (train / eval_tool / eval_call) and
        # fields like session/gpu/log to register_all to write; register_all is the sole writer.
        import json
        outdir = os.path.join(self.tmpdir, "out_kind")
        pieces = [rich_piece()]
        receipt = LC.register_all("trun_kind", "/tmp/wd", pieces, "smoke",
                                   "cmd", outdir=outdir, runmeta_kind="train",
                                   runmeta_extra={"session": "s1", "gpu": 3})
        self.assertIn("RUNMETA", receipt)
        self.assertNotIn("WARN", receipt)
        doc = json.load(open(os.path.join(outdir, "RUNMETA.json")))
        ent = doc["launches"][-1]
        self.assertEqual(ent["kind"], "train")
        self.assertEqual(ent["session"], "s1")
        self.assertEqual(ent["gpu"], 3)
        self.assertEqual(len(doc["launches"]), 1)


if __name__ == "__main__":
    unittest.main()
