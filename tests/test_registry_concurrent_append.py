"""Eight processes appending to jobs/runs.jsonl at once all land, and every line parses; a beat
carries `mem_gib` only when it is given; the piece verdicts of 8.5 read a finished run as done
and a run that lost a piece as dead; the finish row of a card stage's run carries the card
record of the incarnation it closes; and a relaunch of an open run whose pieces are all dead
closes that incarnation with its finish row before its own start row."""
# venv: probe
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

import yaml

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
        "upstream": {}, "era": 1, "diff": {},
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


class HeartbeatLineTest(unittest.TestCase):
    """8.4's beat line with the optional `mem_gib` a train piece passes: the figure lands in the
    line when it is given, and a beat without it is the line it was before."""

    def test_beat_carries_mem_gib_only_when_given(self):
        registry = _load_registry()
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            with contextlib.redirect_stdout(io.StringIO()) as out:
                hb = registry.beat(run_dir, 0)
                hb.emit(0, 10, "step", mem_gib=61.2)
                hb.emit(1, 10, "step", loss=0.5)
                hb.emit(1, 10, "step")
                hb.finish()
            lines = (run_dir / "heartbeat" / "0-0.jsonl").read_text().splitlines()
        rows = [json.loads(line) for line in lines]
        self.assertEqual(rows[0]["mem_gib"], 61.2)
        self.assertEqual(set(rows[0]), {"done", "total", "unit", "ts", "mem_gib"})
        self.assertEqual(set(rows[1]), {"done", "total", "unit", "ts", "loss"})
        self.assertEqual(set(rows[2]), {"done", "total", "unit", "ts"})
        self.assertEqual(set(rows[3]), {"done", "total", "unit", "ts", "status"})
        # The stdout copy of each beat is the same line as the file's.
        self.assertEqual(out.getvalue().splitlines(), ["@hb " + line for line in lines])


class PieceVerdictTest(unittest.TestCase):
    """8.5's verdicts over one run's pieces, through `_judge_pieces`, the derivation `ls()` and
    `sync()` both read. Sessions are a plain set, so no host is probed."""

    def setUp(self):
        self.registry = _load_registry()
        self._tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self._tmp.name)
        # The verdicts age every beat against the clock they read after the heartbeat file, so
        # the fixture's beats and launch minute are placed relative to the real clock: the
        # launch about ten minutes ago, beats a few seconds ago.
        self.now_ts = time.time()
        self.T = datetime.fromtimestamp(self.now_ts - 600).strftime("%Y-%m-%d %H:%M")

    def tearDown(self):
        self._tmp.cleanup()

    def _verdicts(self, pieces, sessions):
        return [(v, esc) for _pv, v, esc in self.registry._judge_pieces(
            pieces, self.run_dir, set(sessions), self.T)]

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
        # The earlier incarnation finished; the relaunch recorded beat_launch 1, stamped the
        # entry with the time its session started, and its process has not opened
        # heartbeat/0-1.jsonl yet, so the piece is warming up, or dead once its session is
        # gone, and never done on the earlier file's finish row.
        _write_beats(self.run_dir, 0, [{"done": 0, "total": 3}, {"done": 3, "total": 3},
                                       {"done": 3, "total": 3, "status": "done"}],
                     self.now_ts - 900)
        piece = {"index": 0, "kind": "train", "host": "tokyo108", "session": "t-0",
                 "beat_launch": 1, "started": self.T}
        self.assertEqual(self._verdicts([piece], {"t-0"})[0], ("warming up", False))
        self.assertEqual(self._verdicts([piece], set())[0], ("dead", True))
        _write_beats(self.run_dir, 0, [{"done": 0, "total": 3}], self.now_ts - 5, launch=1)
        self.assertEqual(self._verdicts([piece], {"t-0"})[0], ("healthy", False))

    def test_piece_whose_session_was_never_started_is_not_started(self):
        # A loop piece of a later wave: no session, no `started` stamp from the launcher and no
        # beat of its own, so it is not started and not escalated; the launcher's stamp alone,
        # or a beat of its own alone, makes the same session-less piece dead.
        piece = {"index": 0, "kind": "loop", "host": "tokyo105", "session": "s-0"}
        self.assertEqual(self._verdicts([piece], set())[0], ("not started", False))
        # Past launch_timeout_s the launcher that would have started it is gone: escalated.
        old = [(v, esc) for _pv, v, esc in self.registry._judge_pieces(
            [piece], self.run_dir, set(), "2020-01-01 00:00")]
        self.assertEqual(old[0], ("not started", True))
        self.assertEqual(self._verdicts([dict(piece, started=self.T)], set())[0], ("dead", True))
        _write_beats(self.run_dir, 0, [{"done": 0, "total": 2}], self.now_ts - 5)
        self.assertEqual(self._verdicts([piece], set())[0], ("dead", True))
        self.assertTrue(self.registry.launch_failed("2020-01-01 00:00", ["not started", "dead"]))

    def test_beat_naming_a_phase_is_never_slowed(self):
        # A train piece in its validation pass touches the heartbeat without moving the count:
        # the same done/total under `phase`, so a zero recent rate reads healthy, not slowed.
        # The touches refresh the age only: the stall line and the rates are read over the
        # counting beats, so thirty touches a few seconds apart leave the stall line where the
        # step beats put it and a beat-less minute after the pass is not a stall.
        step_gap = 300
        beats = [{"done": 5 * i, "total": 100} for i in range(11)]
        hb_dir = self.run_dir / "heartbeat"
        hb_dir.mkdir(parents=True, exist_ok=True)
        pass_start = self.now_ts - 200
        with open(hb_dir / "0-0.jsonl", "w") as f:
            for i, beat in enumerate(beats):
                ts = pass_start - (len(beats) - 1 - i) * step_gap
                f.write(json.dumps({"unit": "step", "ts": ts, **beat}) + "\n")
            for i in range(30):
                f.write(json.dumps({"unit": "step", "ts": pass_start + 3 * i, "done": 50,
                                    "total": 100, "phase": "validate"}) + "\n")
        piece = {"index": 0, "kind": "train", "host": "tokyo108", "session": "t-0",
                 "started": self.T}
        pv, verdict, escalated = self.registry._judge_pieces([piece], self.run_dir, {"t-0"}, self.T)[0]
        self.assertEqual(pv["phase"], "validate")
        self.assertEqual((pv["done"], pv["total"]), (50, 100))
        self.assertEqual(len(pv["beat_ts"]), len(beats))
        self.assertGreater(self.registry.stall_line_s(pv["beat_ts"]), 1000)
        self.assertEqual((verdict, escalated), ("healthy", False))

    def test_attached_service_is_judged_by_its_port_and_its_runs_work(self):
        # An attached agent service's own session ends once its endpoint file is written (7.4),
        # so a gone session is its normal state: the port and its run's work decide.
        (self.run_dir / "service_agent_0.json").write_text(
            json.dumps({"kind": "agent", "attached_to": "sample-000000000000"}))
        pieces = [{"index": 0, "kind": "loop", "host": "tokyo105", "session": "s-0"},
                  {"index": 1, "kind": "service", "host": "tokyo108", "session": "s-1",
                   "endpoint_file": "service_agent_0.json"}]
        judged = self.registry._judge_pieces(pieces, self.run_dir, {"s-0"}, self.T)
        self.assertTrue(judged[1][0]["attached"])
        self.assertEqual(self.registry.judge_service(dict(judged[1][0], port_ok=True)),
                         ("healthy", False))
        self.assertEqual(self.registry.judge_service(dict(judged[1][0], port_ok=False)),
                         ("dead", True))
        _write_beats(self.run_dir, 0, [{"done": 0, "total": 2},
                                       {"done": 2, "total": 2, "status": "done"}], self.now_ts - 5)
        self.assertEqual(self._verdicts(pieces, set()), [("done", False), ("done", False)])


_FIXTURE_CARDS = """\
hosts:
  - name: tokyo105
    alias: shiga
    cards:
      - {model: NVIDIA RTX A6000, memory_gib: 47}
  - name: tokyo108
    alias: saitama
    cards:
      - {model: NVIDIA H100 NVL, memory_gib: 93}
      - {model: NVIDIA H100 NVL, memory_gib: 93}
      - {model: NVIDIA H100 NVL, memory_gib: 93}
      - {model: NVIDIA H200 NVL, memory_gib: 140}
      - {model: NVIDIA H200 NVL, memory_gib: 140}
      - {model: NVIDIA H200 NVL, memory_gib: 140}
"""

_LAUNCHED_AT = "2026-10-02 20:49"

# One vLLM statistics line, repeated until an agent service's log is longer than the tail the
# failure is read from, so the memory lines near its start lie outside that tail.
_VLLM_STATS = ("(APIServer pid=7) INFO 10-02 21:00:00 [loggers.py:310] Engine 000: Avg prompt "
               "throughput: 22.2 tokens/s, Avg generation throughput: 191.8 tokens/s, Running: 1 "
               "reqs, Waiting: 0 reqs, GPU KV cache usage: 1.1%, Prefix cache hit rate: 94.5%\n")

_OOM_LINE = ("torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 2.00 GiB. GPU 0 has a "
             "total capacity of 93.00 GiB of which 1.10 GiB is free. Including non-PyTorch memory, "
             "this process has 91.89 GiB memory in use. Of the allocated memory 88.10 GiB is "
             "allocated by PyTorch, and 2.31 GiB is reserved by PyTorch but unallocated. If "
             "reserved but unallocated memory is large try setting "
             "PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True to avoid fragmentation.")


class CardRecordTest(unittest.TestCase):
    """`append_finish` adds a `card_record` to the finish row of a sample, inject or train run,
    and a walk's relaunch or a refire of an open run whose pieces are all dead appends that
    incarnation's `launch_failed` row, record included, before its own start row.
    Every case runs in a temporary tree holding a copy of jobs/registry.py, its own runs.jsonl,
    a fixture constants/cards.yaml and a constants/path_outputs.yaml whose root is under the
    temporary directory, so no case touches the real ledger or NFS."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tree = Path(self._tmp.name)
        (self.tree / "jobs").mkdir()
        (self.tree / "constants").mkdir()
        shutil.copy(REPO_ROOT / "jobs" / "registry.py", self.tree / "jobs" / "registry.py")
        (self.tree / "jobs" / "runs.jsonl").write_text("")
        (self.tree / "constants" / "cards.yaml").write_text(_FIXTURE_CARDS)
        self.out = self.tree / "out"
        (self.tree / "constants" / "path_outputs.yaml").write_text(
            f"root: {self.out}\ndebug_subdir: debug\nlogin_host: saitama\n")
        spec = importlib.util.spec_from_file_location(
            "registry_card_record_under_test", self.tree / "jobs" / "registry.py")
        self.registry = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.registry)

    def tearDown(self):
        self._tmp.cleanup()

    def _run_dir(self, stage: str, key: str, debug: bool = False) -> Path:
        run_dir = self.out / ("debug" if debug else "") / stage / key
        (run_dir / "log").mkdir(parents=True)
        return run_dir

    def _start(self, stage: str, key: str, run_dir: Path, pieces: list[dict], debug: bool = False,
               launches: int = 2) -> str:
        """Append the run's start row and write its meta.json: the pieces with the launcher's
        `started` stamp, and `launches` launch entries (the incarnation's ordinal)."""
        run_id = f"{stage}-{key}"
        self.registry.append_start({
            "ev": "start", "t": _LAUNCHED_AT, "run_id": run_id, "stage": stage, "key": key,
            "dir": str(run_dir), "workflow": "train_probe", "setting": "fixture",
            "debug": debug, "pieces": pieces, "status": "launching"})
        self.registry.write_meta(run_dir, stage=stage, key=key,
                                 pieces=[dict(p, started=_LAUNCHED_AT) for p in pieces],
                                 launches=[{"t": _LAUNCHED_AT}] * launches)
        return run_id

    def _write_settings(self, run_dir: Path, doc: dict) -> None:
        (run_dir / "settings.yaml").write_text(yaml.safe_dump(doc))

    def _write_beats(self, run_dir: Path, piece: int, launch: int, beats: list[dict]) -> None:
        hb_dir = run_dir / "heartbeat"
        hb_dir.mkdir(exist_ok=True)
        with open(hb_dir / f"{piece}-{launch}.jsonl", "w") as f:
            for beat in beats:
                f.write(json.dumps(beat) + "\n")

    def _launch(self):
        """The tree's jobs/launch.py with its `registry` pointed at this case's temporary copy
        for the length of the case, so the meta.json writes it makes land in the temporary
        tree."""
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        launch = importlib.import_module("jobs.launch")
        self.addCleanup(setattr, launch, "registry", launch.registry)
        launch.registry = self.registry
        return launch

    def _relaunch(self, launch, run_dir: Path, placed: list[dict]) -> dict[int, dict]:
        """What a launch does to its pieces' entries before and as their sessions start:
        `incarnation_origin` records where each log's new output starts, then each session's
        `started` stamp is written, as `_start_wave` writes it."""
        placed = [dict(p, run_dir=str(run_dir)) for p in placed]
        origin = launch.incarnation_origin(run_dir, placed)
        for p in placed:
            p["started"] = _LAUNCHED_AT
        self.registry.write_meta(run_dir, pieces=[launch._strip_runtime(p) for p in placed])
        return origin

    def _meta_pieces(self, run_dir: Path) -> dict[int, dict]:
        meta = json.loads((run_dir / "meta.json").read_text())
        return {p["index"]: p for p in meta["pieces"]}

    def _finish(self, run_id: str, status: str) -> dict:
        self.registry.append_finish(run_id, {
            "ev": "finish", "t": "2026-10-02 22:00", "run_id": run_id, "status": status,
            "counts": {}, "metrics": {}, "report": None, "elapsed_s": 60.0})
        rows = (self.tree / "jobs" / "runs.jsonl").read_text().strip().splitlines()
        return json.loads(rows[-1])

    def test_train_piece_dead_of_memory(self):
        key = "a1a1a1a1a1a1"
        run_dir = self._run_dir("train", key)
        self._write_settings(run_dir, {
            "_stage": "train", "_key": key, "_debug": False,
            "models": {"probe": "qwen3_4b"},
            "probe": {"method": "ctool", "tuning": "lora", "lora_r": 16},
            "train": {"max_len": 8192, "events_per_mb": 4, "grad_ckpt": True, "lr": 1.0e-5}})
        piece = {"index": 0, "kind": "train", "host": "tokyo108", "gpus": "0",
                 "session": f"train-{key}-0", "log": str(run_dir / "log" / "0.txt"),
                 "endpoint_file": None, "beat_launch": 1}
        run_id = self._start("train", key, run_dir, [piece])
        # The earlier incarnation's beats: never read, though its memory is the largest.
        self._write_beats(run_dir, 0, 0, [
            {"done": 0, "total": 10, "unit": "step", "ts": 100.0, "mem_gib": 80.0},
            {"done": 6, "total": 10, "unit": "step", "ts": 900.0, "mem_gib": 90.0}])
        # This incarnation trained 8 steps in 200 s, touched the heartbeat in its validation
        # pass, started its prediction pass and died there of memory.
        self._write_beats(run_dir, 0, 1, [
            {"done": 0, "total": 8, "unit": "step", "ts": 1000.0, "mem_gib": 10.5},
            {"done": 4, "total": 8, "unit": "step", "ts": 1100.0, "mem_gib": 61.2},
            {"done": 8, "total": 8, "unit": "step", "ts": 1200.0, "mem_gib": 60.0},
            {"done": 8, "total": 8, "unit": "step", "ts": 1250.0, "mem_gib": 62.5,
             "phase": "validate"},
            {"done": 0, "total": 2, "unit": "prediction split", "ts": 1300.0, "mem_gib": 61.0},
            {"done": 1, "total": 2, "unit": "prediction split", "ts": 1400.0, "mem_gib": 61.4}])
        (run_dir / "log" / "0.txt").write_text(
            "step 8 loss 0.31\n"
            "Traceback (most recent call last):\n"
            '  File "/repo/train/utils/trainer.py", line 582, in run\n'
            "    pred_rows.extend(method.predict(probe, split_df, probe.tokenizer, cfg, hb))\n"
            "                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n"
            + _OOM_LINE + "\n")
        row = self._finish(run_id, "launch_failed")
        self.assertEqual(row["status"], "launch_failed")
        self.assertEqual(row["card_record"], {
            "launch": 2,
            "task": {"stage": "train", "debug": False, "models.probe": "qwen3_4b",
                     "probe.method": "ctool", "probe.tuning": "lora", "probe.lora_r": 16,
                     "train.max_len": 8192, "train.events_per_mb": 4, "train.grad_ckpt": True},
            "pieces": [{"index": 0, "kind": "train", "host": "tokyo108", "gpus": "0",
                        "card_model": "NVIDIA H100 NVL", "card_gib": 93, "peak_gib": 62.5,
                        "failure": "memory", "failure_line": _OOM_LINE[:300]}],
            "speed": {"unit": "step", "done": 8, "span_s": 200.0, "per_hour": 144.0},
        })
        self.assertEqual(len(row["card_record"]["pieces"][0]["failure_line"]), 300)

    def test_agent_service_memory_lines_and_its_log_tail(self):
        key = "b2b2b2b2b2b2"
        run_dir = self._run_dir("sample", key, debug=True)
        self._write_settings(run_dir, {
            "_stage": "sample", "_key": key, "_debug": True,
            "models": {"agent": "qwen3pt8_27b", "probe": "qwen3_0pt6b"},
            "sample": {"max_steps": 6, "pieces": 2}})
        pieces = [
            {"index": 0, "kind": "loop", "host": "saitama", "gpus": "", "session": f"sample-{key}-0",
             "endpoint_file": None, "beat_launch": 0},
            {"index": 1, "kind": "loop", "host": "saitama", "gpus": "", "session": f"sample-{key}-1",
             "endpoint_file": None, "beat_launch": 0},
            {"index": 2, "kind": "service", "host": "tokyo108", "gpus": "5",
             "session": f"sample-{key}-2", "endpoint_file": "service_agent_0.json"},
            # A render-only probe service holds no card, so the record has no entry for it.
            {"index": 3, "kind": "service", "host": "saitama", "gpus": "",
             "session": f"sample-{key}-3", "endpoint_file": "service_probe_0.json"},
        ]
        run_id = self._start("sample", key, run_dir, pieces, debug=True)
        self._write_beats(run_dir, 0, 0, [
            {"done": 0, "total": 9, "unit": "task", "ts": 5000.0},
            {"done": 3, "total": 9, "unit": "task", "ts": 5060.0},
            {"done": 9, "total": 9, "unit": "task", "ts": 5173.0}])
        self._write_beats(run_dir, 1, 0, [
            {"done": 0, "total": 3, "unit": "task", "ts": 5000.0},
            {"done": 3, "total": 3, "unit": "task", "ts": 5100.0}])
        # The log the service's two incarnations appended to: the first loaded a model and ran
        # out of memory; the second loaded it again, served long enough for its statistics to
        # fill more than the 16 KB tail, and was interrupted by the kill.
        engine = "(EngineCore pid=11) INFO 10-02 20:51:21 "
        (run_dir / "log" / "2.txt").write_text(
            engine + "[gpu_model_runner.py:5347] Model loading took 61.43 GiB memory and "
                     "16.769317 seconds\n"
            + engine + "[gpu_worker.py:560] Available KV cache memory: 63.43 GiB\n"
            + engine + "[kv_cache_utils.py:2178] Maximum concurrency for 131,072 tokens per "
                       "request: 12.52x\n"
            + "(EngineCore pid=11) " + _OOM_LINE + "\n"
            + engine + "[gpu_model_runner.py:5347] Model loading took 50.22 GiB memory and "
                       "13.758207 seconds\n"
            + engine + "[gpu_worker.py:560] Available KV cache memory: 73.63 GiB\n"
            + engine + "[kv_cache_utils.py:2178] Maximum concurrency for 131,072 tokens per "
                       "request: 8.99x\n"
            + _VLLM_STATS * 120
            + "(APIServer pid=7) Traceback (most recent call last):\n"
            + '(APIServer pid=7)   File "/venv/vllm/entrypoints/openai/api_server.py", line 10, '
              "in run_server\n"
            + "(APIServer pid=7)     await serve()\n"
            + "(APIServer pid=7) KeyboardInterrupt\n"
            + _VLLM_STATS)
        self.assertGreater((run_dir / "log" / "2.txt").stat().st_size, 16 * 1024 + 1000)
        row = self._finish(run_id, "killed")
        self.assertEqual(row["card_record"], {
            "launch": 2,
            "task": {"stage": "sample", "debug": True, "models.agent": "qwen3pt8_27b",
                     "cards_per_agent_server": 1},
            "pieces": [{"index": 2, "kind": "service", "service": "agent", "host": "tokyo108",
                        "gpus": "5", "card_model": "NVIDIA H200 NVL", "card_gib": 140,
                        "weights_gib": 50.22, "kv_cache_gib": 73.63, "max_concurrency": 8.99,
                        "failure": "error", "failure_line": "(APIServer pid=7) KeyboardInterrupt"}],
            # Summed over the two loop pieces: 9 tasks in 173 s and 3 tasks in 100 s.
            "speed": {"unit": "task", "done": 12, "span_s": 173.0,
                      "per_hour": round((9 / 173 + 3 / 100) * 3600, 1)},
        })

    def test_inject_checkpoints_and_the_probe_service_of_a_finished_run(self):
        key, score_key, gen_key = "c3c3c3c3c3c3", "d4d4d4d4d4d4", "e5e5e5e5e5e5"
        score_dir = self.out / "train" / score_key
        gen_dir = self.out / "debug" / "train" / gen_key
        for train_dir, train_key, backbone, tuning in ((score_dir, score_key, "qwen3_0pt6b", "full"),
                                                        (gen_dir, gen_key, "qwen3_1pt7b", "lora")):
            train_dir.mkdir(parents=True)
            self._write_settings(train_dir, {"_stage": "train", "_key": train_key,
                                             "models": {"probe": backbone},
                                             "probe": {"tuning": tuning}})
        run_dir = self._run_dir("inject", key)
        self._write_settings(run_dir, {
            "_stage": "inject", "_key": key, "_debug": False,
            "_upstream": {"probe_score.train": score_key, "probe_score.eval": "f6f6f6f6f6f6",
                          "probe_gen.train": gen_key},
            "models": {"agent": "gpt_oss_120b", "probe": None}})
        pieces = [
            {"index": 0, "kind": "loop", "host": "saitama", "gpus": "", "session": f"inject-{key}-0",
             "endpoint_file": None, "beat_launch": 0},
            {"index": 1, "kind": "service", "host": "tokyo108", "gpus": "3,4",
             "session": f"inject-{key}-1", "endpoint_file": "service_agent_0.json"},
            {"index": 2, "kind": "service", "host": "tokyo108", "gpus": "1",
             "session": f"inject-{key}-2", "endpoint_file": "service_probe_0.json"},
        ]
        run_id = self._start("inject", key, run_dir, pieces, launches=1)
        self._write_beats(run_dir, 0, 0, [
            {"done": 0, "total": 2, "unit": "task", "ts": 0.0},
            {"done": 2, "total": 2, "unit": "task", "ts": 3600.0},
            {"done": 2, "total": 2, "unit": "task", "ts": 3601.0, "status": "done"}])
        # The service ended with its run's work: the traceback its teardown printed is not read.
        (run_dir / "log" / "2.txt").write_text(
            "probe service memory: 3.42 GiB reserved after loading\n"
            "Traceback (most recent call last):\n"
            "KeyboardInterrupt\n")
        row = self._finish(run_id, "ok")
        self.assertEqual(row["card_record"], {
            "launch": 1,
            "task": {"stage": "inject", "debug": False, "models.agent": "gpt_oss_120b",
                     "probe_score.backbone": "qwen3_0pt6b", "probe_score.tuning": "full",
                     "probe_gen.backbone": "qwen3_1pt7b", "probe_gen.tuning": "lora"},
            # The agent service's log is gone: its figures are null.
            "pieces": [{"index": 1, "kind": "service", "service": "agent", "host": "tokyo108",
                        "gpus": "3,4", "card_model": "NVIDIA H200 NVL", "card_gib": 140,
                        "weights_gib": None, "kv_cache_gib": None, "max_concurrency": None,
                        "failure": None, "failure_line": None},
                       {"index": 2, "kind": "service", "service": "probe", "host": "tokyo108",
                        "gpus": "1", "card_model": "NVIDIA H100 NVL", "card_gib": 93,
                        "peak_gib": 3.42, "failure": None, "failure_line": None}],
            "speed": {"unit": "task", "done": 2, "span_s": 3601.0,
                      "per_hour": round(2 / 3601 * 3600, 1)},
        })

    def test_unreadable_inputs_leave_fields_null_and_the_row_lands(self):
        key = "f7f7f7f7f7f7"
        run_dir = self.out / "train" / key
        piece = {"index": 0, "kind": "train", "host": "tokyo108", "gpus": "2",
                 "session": f"train-{key}-0", "endpoint_file": None, "beat_launch": 0}
        run_id = f"train-{key}"
        # No run directory at all: no meta.json, settings.yaml, heartbeat or log.
        self.registry.append_start({
            "ev": "start", "t": _LAUNCHED_AT, "run_id": run_id, "stage": "train", "key": key,
            "dir": str(run_dir), "pieces": [piece], "status": "launching"})
        row = self._finish(run_id, "launch_failed")
        self.assertEqual(row["card_record"], {
            "launch": 0, "task": None,
            "pieces": [{"index": 0, "kind": "train", "host": "tokyo108", "gpus": "2",
                        "card_model": "NVIDIA H100 NVL", "card_gib": 93, "peak_gib": None,
                        "failure": None, "failure_line": None}],
            "speed": None})
        # A second finish row for the closed run has no incarnation left to record.
        self.assertIsNone(self._finish(run_id, "killed")["card_record"])
        # A CPU stage's finish row carries no card record.
        self.registry.append_start({"ev": "start", "t": _LAUNCHED_AT, "run_id": f"build-{key}",
                                    "stage": "build", "key": key, "dir": str(run_dir),
                                    "pieces": [], "status": "launching"})
        self.assertNotIn("card_record", self._finish(f"build-{key}", "ok"))

    def test_relaunched_train_piece_records_none_of_the_earlier_incarnations_log(self):
        launch = self._launch()
        key = "a8a8a8a8a8a8"
        run_dir = self._run_dir("train", key)
        self._write_settings(run_dir, {
            "_stage": "train", "_key": key, "_debug": False,
            "models": {"probe": "qwen3_4b"},
            "probe": {"method": "ctool", "tuning": "lora", "lora_r": 16},
            "train": {"max_len": 8192, "events_per_mb": 4, "grad_ckpt": True}})
        log = run_dir / "log" / "0.txt"
        first = {"index": 0, "kind": "train", "host": "tokyo108", "gpus": "0",
                 "session": f"train-{key}-0", "log": str(log), "endpoint_file": None,
                 "beat_launch": 0}
        # The first incarnation, on an H100 card, died of memory.
        run_id = self._start("train", key, run_dir, [first], launches=1)
        self._relaunch(launch, run_dir, [first])
        self.assertEqual(self._meta_pieces(run_dir)[0]["log_offset"], 0)
        self._write_beats(run_dir, 0, 0, [
            {"done": 0, "total": 8, "unit": "step", "ts": 100.0, "mem_gib": 92.0}])
        log.write_text("Traceback (most recent call last):\n"
                       '  File "/repo/train/utils/trainer.py", line 410, in run\n'
                       + _OOM_LINE + "\n")
        first_record = self._finish(run_id, "launch_failed")["card_record"]
        self.assertEqual((first_record["pieces"][0]["failure"],
                          first_record["pieces"][0]["failure_line"]), ("memory", _OOM_LINE[:300]))
        # The relaunch on an H200 card: the launcher records the log's size before the session
        # starts, then the incarnation writes one line and one beat and is killed.
        second = dict(first, gpus="4", beat_launch=1)
        run_id = self._start("train", key, run_dir, [second], launches=1)
        earlier_size = log.stat().st_size
        self.assertEqual(self._relaunch(launch, run_dir, [second]), {0: {"log_size": earlier_size}})
        entry = self._meta_pieces(run_dir)[0]
        self.assertEqual((entry["log_offset"], entry["gpus"], entry["started"]),
                         (earlier_size, "4", _LAUNCHED_AT))
        self.assertNotIn("run_dir", entry)
        with open(log, "a") as f:
            f.write("loading qwen3_4b on cuda:0\n")
        self._write_beats(run_dir, 0, 1, [
            {"done": 0, "total": 8, "unit": "step", "ts": 2000.0, "mem_gib": 30.0}])
        row = self._finish(run_id, "killed")
        self.assertEqual(row["card_record"], {
            "launch": 2,
            "task": {"stage": "train", "debug": False, "models.probe": "qwen3_4b",
                     "probe.method": "ctool", "probe.tuning": "lora", "probe.lora_r": 16,
                     "train.max_len": 8192, "train.events_per_mb": 4, "train.grad_ckpt": True},
            # The earlier incarnation's out-of-memory line lies before this one's offset.
            "pieces": [{"index": 0, "kind": "train", "host": "tokyo108", "gpus": "4",
                        "card_model": "NVIDIA H200 NVL", "card_gib": 140, "peak_gib": 30.0,
                        "failure": None, "failure_line": None}],
            "speed": None,
        })

    def test_relaunched_agent_service_reads_its_figures_and_failure_from_its_offset(self):
        launch = self._launch()
        key = "b9b9b9b9b9b9"
        run_dir = self._run_dir("sample", key)
        self._write_settings(run_dir, {
            "_stage": "sample", "_key": key, "_debug": False,
            "models": {"agent": "qwen3pt8_27b"}, "sample": {"pieces": 1}})
        pieces = [
            {"index": 0, "kind": "loop", "host": "saitama", "gpus": "",
             "session": f"sample-{key}-0", "log": str(run_dir / "log" / "0.txt"),
             "endpoint_file": None, "beat_launch": 1},
            {"index": 1, "kind": "service", "host": "tokyo108", "gpus": "5",
             "session": f"sample-{key}-1", "log": str(run_dir / "log" / "1.txt"),
             "endpoint_file": "service_agent_0.json"},
        ]
        # The first incarnation's service loaded the model, served, and ran out of memory; its
        # loop piece walked a task. Both logs and the endpoint file are still in the directory.
        engine = "(EngineCore pid=11) INFO 10-02 20:51:21 "
        (run_dir / "log" / "0.txt").write_text("task 1 of 3 done\n")
        (run_dir / "log" / "1.txt").write_text(
            engine + "[gpu_model_runner.py:5347] Model loading took 61.43 GiB memory and "
                     "16.769317 seconds\n"
            + engine + "[gpu_worker.py:560] Available KV cache memory: 63.43 GiB\n"
            + engine + "[kv_cache_utils.py:2178] Maximum concurrency for 131,072 tokens per "
                       "request: 12.52x\n"
            + "(EngineCore pid=11) " + _OOM_LINE + "\n")
        (run_dir / "service_agent_0.json").write_text(json.dumps({"kind": "agent"}))
        service_offset = (run_dir / "log" / "1.txt").stat().st_size
        run_id = self._start("sample", key, run_dir, pieces)
        origin = self._relaunch(launch, run_dir, pieces)
        self.assertEqual(origin, {0: {"log_size": len("task 1 of 3 done\n")}})
        self.assertFalse((run_dir / "service_agent_0.json").exists())
        entries = self._meta_pieces(run_dir)
        self.assertEqual((entries[0]["log_offset"], entries[1]["log_offset"]),
                         (len("task 1 of 3 done\n"), service_offset))
        # The relaunched service died before vLLM printed a load line.
        with open(run_dir / "log" / "1.txt", "a") as f:
            f.write("(APIServer pid=21) Traceback (most recent call last):\n"
                    '(APIServer pid=21)   File "/venv/vllm/v1/engine/core_client.py", line 92, '
                    "in make_async_mp_client\n"
                    "(APIServer pid=21) RuntimeError: Engine core initialization failed. See "
                    "root cause above. Failed core proc(s): {}\n")
        row = self._finish(run_id, "launch_failed")
        self.assertEqual(row["card_record"]["pieces"], [
            {"index": 1, "kind": "service", "service": "agent", "host": "tokyo108", "gpus": "5",
             "card_model": "NVIDIA H200 NVL", "card_gib": 140,
             "weights_gib": None, "kv_cache_gib": None, "max_concurrency": None,
             "failure": "error",
             "failure_line": "(APIServer pid=21) RuntimeError: Engine core initialization "
                             "failed. See root cause above. Failed core proc(s): {}"}])

    # -- A relaunch of an open run whose pieces are all dead: the dead incarnation's finish row
    # lands between the two start rows. --

    _GIT = {"commit": "deadbee", "branch": "main", "dirty": False, "dirty_count": 0,
            "dirty_files": []}

    # The record of the dead incarnation `_dead_train_run` leaves behind.
    _DEAD_TRAIN_RECORD = {
        "launch": 1,
        "task": {"stage": "train", "debug": False, "models.probe": "qwen3_4b",
                 "probe.method": "ctool", "probe.tuning": "lora", "probe.lora_r": 16,
                 "train.max_len": 8192, "train.events_per_mb": 4, "train.grad_ckpt": True},
        "pieces": [{"index": 0, "kind": "train", "host": "tokyo108", "gpus": "0",
                    "card_model": "NVIDIA H100 NVL", "card_gib": 93, "peak_gib": 91.5,
                    "failure": "memory", "failure_line": _OOM_LINE[:300]}],
        "speed": {"unit": "step", "done": 4, "span_s": 200.0, "per_hour": 72.0},
    }

    def _dead_train_run(self, launch, key: str) -> tuple[str, Path]:
        """An open train run whose one piece, on card 0 of tokyo108, trained 4 steps and died of
        memory: its session is gone, its log ends in the error, and no finish row closes it. No
        host is probed: every session reads gone, and cards 3 and 4 of tokyo108 read free."""
        run_dir = self._run_dir("train", key)
        self._write_settings(run_dir, {
            "_stage": "train", "_key": key, "_debug": False, "data": {"env": "appworld"},
            "models": {"probe": "qwen3_4b", "probe_row": {"family": "qwen"}},
            "probe": {"method": "ctool", "tuning": "lora", "lora_r": 16},
            "train": {"max_len": 8192, "events_per_mb": 4, "grad_ckpt": True}})
        log = str(run_dir / "log" / "0.txt")
        piece = {"index": 0, "kind": "train", "host": "tokyo108", "gpus": "0",
                 "session": f"train-{key}-0", "log": log, "endpoint_file": None,
                 "beat_launch": 0, "log_offset": 0, "venv": "probe",
                 "cmd": launch.piece_command("python3", "train.methods.ctool", str(run_dir),
                                             None, None, "0", log)}
        run_id = self._start("train", key, run_dir, [piece], launches=1)
        self._write_beats(run_dir, 0, 0, [
            {"done": 0, "total": 8, "unit": "step", "ts": 100.0, "mem_gib": 40.0},
            {"done": 4, "total": 8, "unit": "step", "ts": 300.0, "mem_gib": 91.5}])
        Path(log).write_text("Traceback (most recent call last):\n"
                             '  File "/repo/train/utils/trainer.py", line 410, in run\n'
                             + _OOM_LINE + "\n")
        self.registry.live_sessions = lambda: set()
        self.registry.session_alive = lambda host, session: False
        self.registry.free = lambda: {"tokyo105": [], "tokyo108": [3, 4]}
        return run_id, run_dir

    def _rows(self) -> list[dict]:
        text = (self.tree / "jobs" / "runs.jsonl").read_text()
        return [json.loads(line) for line in text.strip().splitlines()]

    def _assert_closed_then_relaunched(self, run_id: str) -> None:
        rows = self._rows()
        self.assertEqual([(r["ev"], r["status"]) for r in rows],
                         [("start", "launching"), ("finish", "launch_failed"),
                          ("start", "launching")])
        self.assertEqual(rows[1]["card_record"], self._DEAD_TRAIN_RECORD)
        # The relaunch's start row holds the card it claimed and leaves the run open.
        self.assertEqual(rows[2]["pieces"][0]["gpus"], "3")
        self.assertIsNone(self.registry.fold(rows)[run_id]["finish"])

    def test_walk_relaunch_closes_the_dead_incarnation_before_its_start_row(self):
        launch = self._launch()
        key = "c6c6c6c6c6c6"
        run_id, run_dir = self._dead_train_run(launch, key)
        # While the piece's session reads alive, the incarnation stays open and nothing is
        # appended.
        self.assertFalse(self.registry.close_dead_incarnation(run_id, {f"train-{key}-0"}))
        self.assertEqual(len(self._rows()), 1)
        setting = launch.schema.load_frozen(run_dir)
        setting._file, setting._name = "train_probe", "fixture"
        with mock.patch.object(launch, "_start_tmux", return_value=True), \
                mock.patch.object(launch, "alive_check", return_value=(True, [])):
            outcome, _pieces = launch.launch("train", setting, run_dir, {}, self._GIT)
        self.assertEqual(outcome, "up")
        self._assert_closed_then_relaunched(run_id)

    def test_refire_closes_the_dead_incarnation_before_its_start_row(self):
        launch = self._launch()
        key = "d7d7d7d7d7d7"
        run_id, run_dir = self._dead_train_run(launch, key)
        with mock.patch.object(launch, "_start_tmux", return_value=True):
            launch.refire(run_dir, self._GIT)
        self._assert_closed_then_relaunched(run_id)


if __name__ == "__main__":
    unittest.main()
