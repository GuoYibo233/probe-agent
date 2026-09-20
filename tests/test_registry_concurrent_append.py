"""Eight processes appending to jobs/runs.jsonl at once all land, and every line parses."""
# venv: probe
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

N_PROCS = 8
N_ROWS = 20


def _start_row(proc_index: int, row_index: int, run_dir: Path) -> dict:
    return {
        "ev": "start", "t": "2026-09-17 12:00",
        "run_id": f"sample-{proc_index}-{row_index}",
        "stage": "sample", "key": f"{proc_index}{row_index}",
        "dir": str(run_dir), "workflow": "baseline", "setting": "gpt_oss_120b_appworld",
        "parent": None, "swept": None, "debug": False,
        "upstream": {}, "versions": {}, "diff": {},
        "commit": "deadbee", "branch": "main",
        "dirty": False, "dirty_count": 0, "dirty_files": [],
        "host": "shiga", "pieces": [], "status": "launching",
    }


class ConcurrentAppendTest(unittest.TestCase):
    """The fourth of the tree's four planned `tests/` checks (spec section 2)."""

    def test_eight_processes_land_all_160_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            (tree / "jobs").mkdir()
            shutil.copy(REPO_ROOT / "jobs" / "registry.py", tree / "jobs" / "registry.py")
            (tree / "jobs" / "runs.jsonl").write_text("")
            run_dir = tree / "out" / "sample" / "shared"

            pids = []
            for proc_index in range(N_PROCS):
                pid = os.fork()
                if pid == 0:
                    # The child loads the temporary tree's copy by file path, under a name of
                    # its own. `from jobs import registry` returns whatever `jobs.registry` the
                    # forked parent already holds in sys.modules -- the real one whenever another
                    # test module ran first in this process -- and that one appends to the real
                    # jobs/runs.jsonl (42 fixture rows reached it on 2026-09-20).
                    spec = importlib.util.spec_from_file_location(
                        "registry_under_test", tree / "jobs" / "registry.py")
                    registry = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(registry)
                    for row_index in range(N_ROWS):
                        registry.append_start(_start_row(proc_index, row_index, run_dir))
                    os._exit(0)
                pids.append(pid)

            for pid in pids:
                _, status = os.waitpid(pid, 0)
                self.assertTrue(
                    os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0,
                    f"child {pid} exited abnormally: status={status}")

            lines = (tree / "jobs" / "runs.jsonl").read_text().strip().splitlines()
            self.assertEqual(len(lines), N_PROCS * N_ROWS)
            for line in lines:
                json.loads(line)


if __name__ == "__main__":
    unittest.main()
