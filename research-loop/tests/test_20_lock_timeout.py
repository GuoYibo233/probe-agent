"""Test 20: lock.timeout_seconds (30 L181-183; 03 "exit codes"; 08 L77).

Original: one process holds loop/.lock past lock.timeout_seconds (default 10 seconds);
another process writing a ledger gets exit 4, first stderr line lock_timeout, --json
error.kind lock_timeout, and no new row; changing research-loop.json's
lock.timeout_seconds to 1 makes the wait follow the new value instead of the default.
"""

import subprocess
import sys
import time
import unittest

from helpers import Sandbox

HOLD_LOCK_SCRIPT = """
import fcntl, sys, time
path = sys.argv[1]
hold = float(sys.argv[2])
fh = open(path, "a+")
fcntl.flock(fh, fcntl.LOCK_EX)
print("locked", flush=True)
time.sleep(hold)
fcntl.flock(fh, fcntl.LOCK_UN)
"""


class LockTimeout(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def _hold_lock(self, hold_seconds: float) -> subprocess.Popen:
        lock_path = self.sb.loop / ".lock"
        proc = subprocess.Popen([sys.executable, "-c", HOLD_LOCK_SCRIPT, str(lock_path), str(hold_seconds)],
                                stdout=subprocess.PIPE, text=True)
        line = proc.stdout.readline()
        assert line.strip() == "locked", f"lock holder did not report locked: {line!r}"
        return proc

    def test_default_timeout_refuses_with_exit_4_and_no_new_row(self):
        """08 L77 (default 10s); 03 "exit codes" row 4 and the non-zero-exit rule:
        exit 4, first stderr line lock_timeout, no new row."""
        holder = self._hold_lock(15)
        try:
            before = self.sb.count("issues")
            start = time.monotonic()
            r = self.sb.rl("issue", "open", "--to", "gyb", "--kind", "request", "--text", "q", timeout=30)
            elapsed = time.monotonic() - start
            self.assertEqual(r.rc, 4, str(r))
            self.assertEqual(r.kind, "lock_timeout")
            self.assertEqual(self.sb.count("issues"), before)
            self.assertGreaterEqual(elapsed, 8, "should have waited close to the default 10-second timeout")
        finally:
            holder.kill()
            holder.wait(timeout=5)

    def test_default_timeout_json_error_kind(self):
        """03 "exit codes" (non-zero-exit rule): --json error.kind is lock_timeout."""
        holder = self._hold_lock(15)
        try:
            before = self.sb.count("issues")
            r = self.sb.rl("issue", "open", "--to", "gyb", "--kind", "request", "--text", "q",
                           "--json", timeout=30)
            self.assertEqual(r.rc, 4, str(r))
            self.assertEqual(r.json["error"]["kind"], "lock_timeout")
            self.assertEqual(self.sb.count("issues"), before)
        finally:
            holder.kill()
            holder.wait(timeout=5)

    def test_configured_timeout_seconds_is_honored(self):
        """08 L77; 30 L183: lowering lock.timeout_seconds makes the wait follow it, not the default."""
        self.sb.set_config("lock.timeout_seconds", 1)
        holder = self._hold_lock(10)
        try:
            before = self.sb.count("issues")
            start = time.monotonic()
            r = self.sb.rl("issue", "open", "--to", "gyb", "--kind", "request", "--text", "q", timeout=20)
            elapsed = time.monotonic() - start
            self.assertEqual(r.rc, 4, str(r))
            self.assertEqual(r.kind, "lock_timeout")
            self.assertEqual(self.sb.count("issues"), before)
            self.assertLess(elapsed, 5, "a 1-second configured timeout should not wait ~10 seconds")
        finally:
            holder.kill()
            holder.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
