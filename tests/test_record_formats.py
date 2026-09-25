"""The three on-disk formats between stages: a task record written row by row reads back as the frame
its writer held, its claim and release rules keep one owner per task and free a dead owner's
unfinished file, and the example and prediction parquet files round-trip and refuse what they
cannot read. Everything is written under a temporary directory."""
# venv: probe
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

import polars as pl
from polars.testing import assert_frame_equal

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from data import event_id, example_id, read_frame, record_id, write_frame
from data import probe_output, trajectory_record as tr, training_data

META = dict(stage="sample", env="appworld", task_id="t1", seed=42, split="test",
            task_text="pay the bill", agent_model="gpt_oss_120b", owner_session="sample-abc-0")


def _write_record(run_dir: Path, task_id: str = "t1", seed: int = 42, *, owner: str = "sample-abc-0",
                  steps: int = 2, final: bool = True) -> tr.Writer:
    w = tr.open_record(run_dir, task_id, seed)
    w.row("meta", **{**META, "task_id": task_id, "seed": seed, "owner_session": owner})
    for step in range(steps):
        w.row("gen", step=step, reasoning=f"think {step}", content=f"```python\napis.a.b({step})\n```",
              usage={"in": 10, "out": 5})
        w.row("env", step=step, action=f"apis.a.b({step})", result=f"out {step}", exec_ok=True)
    if final:
        w.row("final", steps=steps, completed=True, success=True)
    w.close()
    return w


class IdChainTest(unittest.TestCase):

    def test_ids_nest(self):
        rid = record_id("82e2fac_1", 42)
        eid = event_id(rid, 3)
        self.assertEqual(example_id(eid, 7), "82e2fac_1__s42|s3|c7")
        self.assertEqual(tr.record_path(Path("/r"), "82e2fac_1", 42), Path(f"/r/records/{rid}.jsonl"))


class TrajectoryRecordTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_read_equals_the_writers_frame(self):
        w = _write_record(self.dir)
        on_disk = tr.read(tr.record_path(self.dir, "t1", 42))
        assert_frame_equal(on_disk.drop("ts"), w.frame().drop("ts"))
        self.assertEqual(on_disk.columns, list(tr.SCHEMA))
        self.assertEqual(on_disk["type"].to_list(), ["meta", "gen", "env", "gen", "env", "final"])
        self.assertEqual(set(on_disk["record_id"].to_list()), {"t1__s42"})
        self.assertEqual(on_disk["version"][0], tr.FORMAT_VERSION)
        self.assertEqual(on_disk["n_inject"].to_list(), [0] * 6, "an absent n_inject reads as 0")

    def test_the_claim_is_exclusive(self):
        first = tr.open_record(self.dir, "t1", 42)
        self.assertIsNotNone(first)
        self.assertIsNone(tr.open_record(self.dir, "t1", 42))
        first.close()

    def test_stamped_and_undeclared_fields_are_refused(self):
        w = tr.open_record(self.dir, "t1", 42)
        with self.assertRaises(ValueError):
            w.row("meta", ts=1.0, **META)
        with self.assertRaises(ValueError):
            w.row("gen", step=0, not_a_column=1)
        w.close()

    def test_is_done_owner_and_done_pairs(self):
        _write_record(self.dir, "t1", owner="s-live")
        _write_record(self.dir, "t2", owner="s-dead", final=False)
        p1, p2 = tr.record_path(self.dir, "t1", 42), tr.record_path(self.dir, "t2", 42)
        self.assertTrue(tr.is_done(p1))
        self.assertFalse(tr.is_done(p2))
        self.assertEqual(tr.owner(p1), "s-live")
        self.assertEqual(tr.done_pairs(self.dir, [("t1", 42), ("t2", 42), ("t3", 42)]), {("t1", 42)})

    def test_a_torn_last_line_is_not_done(self):
        _write_record(self.dir)
        path = tr.record_path(self.dir, "t1", 42)
        with open(path, "a") as f:
            f.write('{"type": "fin')
        self.assertFalse(tr.is_done(path))

    def test_release_frees_dead_owners_and_old_unowned_files(self):
        _write_record(self.dir, "done", owner="s-dead")
        _write_record(self.dir, "live", owner="s-live", final=False)
        _write_record(self.dir, "dead", owner="s-dead", final=False)
        young = tr.record_path(self.dir, "young", 42)
        old = tr.record_path(self.dir, "old", 42)
        young.write_text("")
        old.write_text("")
        past = time.time() - 3600
        os.utime(old, (past, past))

        released = tr.release(self.dir, live_sessions={"s-live"}, unowned_age_s=600)
        self.assertEqual(sorted(p.name for p in released), ["dead__s42.jsonl", "old__s42.jsonl"])
        left = sorted(p.name for p in (self.dir / "records").glob("*.jsonl"))
        self.assertEqual(left, ["done__s42.jsonl", "live__s42.jsonl", "young__s42.jsonl"])
        again = tr.open_record(self.dir, "dead", 42)
        self.assertIsNotNone(again, "a released task can be claimed again")
        again.close()

    def test_read_dir_skips_unfinished_records(self):
        _write_record(self.dir, "t1")
        _write_record(self.dir, "t2", final=False)
        df = tr.read_dir(self.dir, [("t1", 42), ("t2", 42)])
        self.assertEqual(set(df["record_id"].to_list()), {"t1__s42"})
        self.assertEqual(tr.read_dir(self.dir, [("t9", 42)]).height, 0)

    def test_to_messages_rebuilds_the_conversation(self):
        _write_record(self.dir, steps=3)
        df = tr.read(tr.record_path(self.dir, "t1", 42))
        msgs = tr.to_messages(df, 2, "pay the bill", "INSTR", "NO CODE", "EXTRA")
        self.assertEqual([m["role"] for m in msgs], ["developer", "user", "assistant", "user", "assistant", "user"])
        self.assertEqual(msgs[0]["content"], "INSTR\n\nEXTRA")
        self.assertEqual(msgs[3]["content"], "out 0")
        self.assertEqual(len(tr.to_messages(df, 0, "t", "I", "N", None)), 2)

    def test_newer_format_version_is_refused(self):
        path = tr.record_path(self.dir, "t1", 42)
        path.parent.mkdir(parents=True)
        meta = {"type": "meta", "ts": 1.0, "version": tr.FORMAT_VERSION + 1, "record_id": "t1__s42", **META}
        path.write_text(json.dumps(meta) + "\n")
        with self.assertRaisesRegex(ValueError, "newer"):
            tr.read(path)


def _examples(n: int = 4) -> pl.DataFrame:
    rows = []
    for i in range(n):
        eid = event_id(record_id(f"t{i}", 42), 0)
        rows.append(dict(example_id=example_id(eid, 0), event_id=eid, record_id=f"t{i}__s42", task_id=f"t{i}",
                         seed=42, step=0, cut=10, cut_index=0, n_cuts=1, depth=1.0, text="Task: x",
                         tool="apis.a.b", call="apis.a.b(k=v)", args=[{"key": "k", "value": "v"}],
                         weight=1.0, split="train"))
    return pl.DataFrame(rows, strict=False)


class ParquetFormatsTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_training_data_round_trip(self):
        path = self.dir / "examples.parquet"
        training_data.write(path, _examples())
        df = training_data.read(path)
        self.assertEqual(df.columns, list(training_data.SCHEMA))
        self.assertEqual(df.height, 4)
        self.assertEqual(df["version"].unique().to_list(), [training_data.FORMAT_VERSION])
        self.assertIsNone(df["env"][0], "an absent optional column reads as its default")
        self.assertEqual(df["args"][0].to_list(), [{"key": "k", "value": "v"}])
        self.assertEqual([p.name for p in self.dir.iterdir()], ["examples.parquet"], "no temporary file left")

    def test_probe_output_round_trip(self):
        path = self.dir / "pred.parquet"
        frame = pl.DataFrame(dict(example_id=["e0", "e1"], event_id=["v0", "v1"], task_id=["t0", "t1"],
                                  depth=[0.5, 1.0], split=["val", "test"], tool=["a", "b"], method=["ctool"] * 2,
                                  target=["a", "b"], logits=[[2.0, 0.0], [0.0, 1.0]]))
        probe_output.write(path, frame)
        df = probe_output.read(path)
        self.assertEqual(df.columns, list(probe_output.SCHEMA))
        self.assertEqual(df["logits"].to_list(), [[2.0, 0.0], [0.0, 1.0]])
        self.assertEqual(df["text_pred"].to_list(), [None, None])

    def test_missing_required_column_is_refused(self):
        path = self.dir / "examples.parquet"
        write_frame(path, _examples().drop("text").with_columns(pl.lit(1, dtype=pl.Int32).alias("version")),
                    schema=training_data.SCHEMA)
        with self.assertRaisesRegex(ValueError, "text"):
            training_data.read(path)

    def test_newer_version_and_missing_file_are_refused(self):
        path = self.dir / "examples.parquet"
        newer = _examples().with_columns(pl.lit(training_data.FORMAT_VERSION + 1, dtype=pl.Int32).alias("version"))
        write_frame(path, newer, schema=training_data.SCHEMA)
        with self.assertRaisesRegex(ValueError, "newer"):
            training_data.read(path)
        with self.assertRaisesRegex(ValueError, "missing or empty"):
            read_frame(self.dir / "absent.parquet", schema=training_data.SCHEMA, defaults=training_data.DEFAULTS,
                       required=training_data.REQUIRED, version=1)

    def test_write_frame_takes_parquet_only(self):
        with self.assertRaisesRegex(ValueError, "parquet"):
            write_frame(self.dir / "x.jsonl", _examples(), schema=training_data.SCHEMA)


if __name__ == "__main__":
    unittest.main()
