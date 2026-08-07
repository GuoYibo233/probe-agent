import io
import json
import unittest

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "ops"))
import heartbeat


class TestHeartbeat(unittest.TestCase):
    def test_emit_required_fields(self):
        buf = io.StringIO()
        heartbeat.emit(3, 100, "task", stream=buf)
        line = buf.getvalue()
        self.assertTrue(line.startswith("@hb "))
        rec = json.loads(line[4:])
        for k in ("done", "total", "unit", "ts"):
            self.assertIn(k, rec)
        self.assertEqual(rec["done"], 3)
        self.assertNotIn("tok_in", rec)          # 选填不给就不出现

    def test_emit_optional_fields(self):
        buf = io.StringIO()
        heartbeat.emit(0, 10, "step", tok_in=123, tok_out=45,
                       loss=0.5, status="done", stream=buf)
        rec = json.loads(buf.getvalue()[4:])
        self.assertEqual((rec["tok_in"], rec["tok_out"]), (123, 45))
        self.assertEqual(rec["status"], "done")

    def test_parse_roundtrip(self):
        buf = io.StringIO()
        heartbeat.emit(7, 9, "task", tok_out=1, stream=buf)
        rec = heartbeat.parse(buf.getvalue())
        self.assertEqual(rec["done"], 7)

    def test_parse_rejects_garbage(self):
        self.assertIsNone(heartbeat.parse("task=1 SKIP (done)"))
        self.assertIsNone(heartbeat.parse("@hb not-json"))
        self.assertIsNone(heartbeat.parse('@hb {"done": 1}'))  # 缺必填


if __name__ == "__main__":
    unittest.main()
