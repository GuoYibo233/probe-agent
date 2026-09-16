"""score_live carries the injection format of each live run into the report (rows and table),
so arms that differ only in --format stay apart. Pure CPU, fake live dir.
    python3 -m unittest tests.test_score_live -v
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline" / "inject"))
sys.path.insert(0, str(ROOT / "pipeline" / "annotate"))

import score_live as S                                          # noqa: E402


def write_live(d, tid, fmt):
    recs = [
        dict(type="meta", task_id=tid, arm="probe", format=fmt),
        dict(type="gen", step=0, usage=dict(gen_tok=10, req=1),
             discard=dict(chars=0, tokens=0, events=0), n_inject=1),
        dict(type="final", steps=1, completed=True, abort=None,
             eval=dict(success=True)),
    ]
    (d / f"live_{tid}.jsonl").write_text("\n".join(json.dumps(r) for r in recs) + "\n")


class TestFormatColumn(unittest.TestCase):
    def test_format_in_rows_and_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            live = Path(tmp) / "live"
            live.mkdir()
            base = Path(tmp) / "base"
            base.mkdir()
            write_live(live, "t1", "p2_e1")
            sys.argv = ["score_live", "--live-dir", str(live), "--base-root", str(base)]
            S.main()
            rep = json.loads((live / "LIVE_REPORT.json").read_text())
            self.assertEqual(rep["tasks"][0]["format"], "p2_e1")
            self.assertEqual(rep["summary"]["formats"], ["p2_e1"])
            md = (live / "LIVE_REPORT.md").read_text()
            self.assertIn("| task | arm | format |", md)
            self.assertIn("| t1 | probe | p2_e1 |", md)


if __name__ == "__main__":
    unittest.main()
