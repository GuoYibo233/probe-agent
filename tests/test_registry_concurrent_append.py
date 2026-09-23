"""Eight processes appending to jobs/runs.jsonl at once all land, and every line parses; and the
piece verdicts of 8.5 read a finished run as done and a run that lost a piece as dead."""
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


def _load_registry():
    """The real jobs/registry.py under a name of its own. The verdict functions read heartbeat
    files and a session set and write nothing, so this never touches jobs/runs.jsonl."""
    spec = importlib.util.spec_from_file_location(
        "registry_verdicts_under_test", REPO_ROOT / "jobs" / "registry.py")
    registry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(registry)
    return registry


def _write_beats(run_dir: Path, piece: int, beats: list[dict], last_ts: float,
                 launch: int = 0) -> None:
    """One heartbeat file, `heartbeat/<piece>-<launch>.jsonl`, one second between beats, the last
    one at `last_ts`."""
    hb_dir = run_dir / "heartbeat"
    hb_dir.mkdir(parents=True, exist_ok=True)
    first_ts = last_ts - (len(beats) - 1)
    with open(hb_dir / f"{piece}-{launch}.jsonl", "w") as f:
        for i, beat in enumerate(beats):
            f.write(json.dumps({"unit": "task", "ts": first_ts + i, **beat}) + "\n")


class PieceVerdictTest(unittest.TestCase):
    """8.5's verdicts over one run's pieces, through `_judge_pieces`, the derivation `ls()` and
    `sync()` both read. Sessions are a plain set, so no host is probed."""

    T = "2026-09-17 12:00"

    def setUp(self):
        self.registry = _load_registry()
        self._tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self._tmp.name)
        self.now_ts = self.registry._parse_t(self.T) + 600

    def tearDown(self):
        self._tmp.cleanup()

    def _verdicts(self, pieces, sessions):
        return [(v, esc) for _pv, v, esc in self.registry._judge_pieces(
            pieces, self.run_dir, set(sessions), self.T, self.now_ts)]

    def _sample_pieces(self):
        return [
            {"index": 0, "kind": "loop", "host": "tokyo105", "session": "s-0"},
            {"index": 1, "kind": "service", "host": "tokyo108", "session": "s-1"},
        ]

    def test_train_piece_at_step_total_without_finish_row_is_not_done(self):
        _write_beats(self.run_dir, 0, [{"done": 0, "total": 3}, {"done": 3, "total": 3}],
                     self.now_ts - 5)
        piece = {"index": 0, "kind": "train", "host": "tokyo108", "session": "t-0"}
        self.assertEqual(self._verdicts([piece], {"t-0"})[0][0], "healthy")
        self.assertEqual(self._verdicts([piece], set())[0], ("dead", True))

    def test_train_piece_with_finish_row_is_done(self):
        _write_beats(self.run_dir, 0, [{"done": 0, "total": 3}, {"done": 2, "total": 3},
                                       {"done": 2, "total": 3, "status": "done"}], self.now_ts - 5)
        piece = {"index": 0, "kind": "train", "host": "tokyo108", "session": "t-0"}
        self.assertEqual(self._verdicts([piece], set())[0], ("done", False))

    def test_service_ended_after_its_loop_pieces_finished_is_done(self):
        _write_beats(self.run_dir, 0, [{"done": 0, "total": 2}, {"done": 2, "total": 2},
                                       {"done": 2, "total": 2, "status": "done"}], self.now_ts - 5)
        self.assertEqual(self._verdicts(self._sample_pieces(), set()),
                         [("done", False), ("done", False)])

    def test_service_gone_while_its_loop_piece_works_is_dead(self):
        _write_beats(self.run_dir, 0, [{"done": 0, "total": 2}, {"done": 1, "total": 2}],
                     self.now_ts - 5)
        self.assertEqual(self._verdicts(self._sample_pieces(), {"s-0"}),
                         [("healthy", False), ("dead", True)])

    def test_relaunched_piece_reads_only_its_own_incarnation(self):
        # The earlier incarnation finished; the relaunch recorded beat_launch 1 and its process
        # has not opened heartbeat/0-1.jsonl yet, so the piece is warming up, or dead once its
        # session is gone, and never done on the earlier file's finish row.
        _write_beats(self.run_dir, 0, [{"done": 0, "total": 3}, {"done": 3, "total": 3},
                                       {"done": 3, "total": 3, "status": "done"}],
                     self.now_ts - 900)
        piece = {"index": 0, "kind": "train", "host": "tokyo108", "session": "t-0",
                 "beat_launch": 1}
        self.assertEqual(self._verdicts([piece], {"t-0"})[0], ("warming up", False))
        self.assertEqual(self._verdicts([piece], set())[0], ("dead", True))
        _write_beats(self.run_dir, 0, [{"done": 0, "total": 3}], self.now_ts - 5, launch=1)
        self.assertEqual(self._verdicts([piece], {"t-0"})[0], ("healthy", False))

    def test_attached_service_is_judged_by_its_port_and_its_runs_work(self):
        # An attached agent service's own session ends once its endpoint file is written (7.4),
        # so a gone session is its normal state: the port and its run's work decide.
        (self.run_dir / "service_agent_0.json").write_text(
            json.dumps({"kind": "agent", "attached_to": "sample-000000000000"}))
        pieces = [{"index": 0, "kind": "loop", "host": "tokyo105", "session": "s-0"},
                  {"index": 1, "kind": "service", "host": "tokyo108", "session": "s-1",
                   "endpoint_file": "service_agent_0.json"}]
        judged = self.registry._judge_pieces(pieces, self.run_dir, {"s-0"}, self.T, self.now_ts)
        self.assertTrue(judged[1][0]["attached"])
        self.assertEqual(self.registry.judge_service(dict(judged[1][0], port_ok=True)),
                         ("healthy", False))
        self.assertEqual(self.registry.judge_service(dict(judged[1][0], port_ok=False)),
                         ("dead", True))
        _write_beats(self.run_dir, 0, [{"done": 0, "total": 2},
                                       {"done": 2, "total": 2, "status": "done"}], self.now_ts - 5)
        self.assertEqual(self._verdicts(pieces, set()), [("done", False), ("done", False)])


if __name__ == "__main__":
    unittest.main()
