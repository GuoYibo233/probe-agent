"""Comparison-criteria test for ident3_score (pure CPU).
    python3 -m unittest tests.test_ident3_score -v
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline" / "inject"))

import ident3_score as I                                        # noqa: E402


def run(ids):
    return dict(ids=ids)


class TestCompare(unittest.TestCase):
    def test_identical(self):
        c = I.compare(run([[1, 2, 3], [4, 5]]), run([[1, 2, 3], [4, 5]]))
        self.assertTrue(c["identical"])
        self.assertEqual(c["shared_tok"], 5)

    def test_tail_return_stripped(self):
        c = I.compare(run([[1, 2, I.RETURN_ID]]), run([[1, 2]]))
        self.assertTrue(c["identical"])

    def test_first_divergence(self):
        c = I.compare(run([[1, 2, 3], [4, 5, 6]]), run([[1, 2, 3], [4, 9, 6]]))
        self.assertFalse(c["identical"])
        self.assertEqual((c["div_step"], c["div_tok"], c["shared_tok"]), (1, 1, 4))

    def test_prefix_but_more_steps(self):
        c = I.compare(run([[1, 2]]), run([[1, 2], [3]]))
        self.assertFalse(c["identical"])
        self.assertEqual((c["div_step"], c["div_tok"], c["shared_tok"]), (1, 0, 2))

    def test_length_diff_within_step(self):
        c = I.compare(run([[1, 2, 3]]), run([[1, 2]]))
        self.assertFalse(c["identical"])
        self.assertEqual((c["div_step"], c["div_tok"]), (0, 2))

    def test_missing_ids_not_comparable(self):
        c = I.compare(run([None]), run([[1]]))
        self.assertFalse(c["comparable"])


class TestLoadRun(unittest.TestCase):
    def test_chat_and_live_shapes(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "appworld_t1.jsonl"
            p.write_text("\n".join(json.dumps(r) for r in [
                dict(type="meta"),
                dict(type="gen", step=0, out_token_ids=[1, 2], prompt_token_ids=[9] * 4,
                     usage=dict(**{"in": 4, "out": 2})),
                dict(type="env", step=0),
                dict(type="final", steps=1, completed=True, abort=None,
                     eval="{'success': True, 'x': 1}")]) + "\n")
            r = I.load_run(p, "chat")
            self.assertEqual(r["ids"], [[1, 2]])
            self.assertEqual(r["prompt_tok"], [4])
            self.assertTrue(r["success"])
            self.assertFalse(r["excluded"])
            self.assertEqual(r["prompt_sha"], [I.ids_sha([9] * 4)])
            q = Path(d) / "live_t1.jsonl"
            q.write_text("\n".join(json.dumps(r) for r in [
                dict(type="meta"),
                dict(type="gen", step=0, gen_ids=[1, 2], prefix_tok=4, n_inject=1,
                     usage=dict(prompt_tok=4, gen_tok=3, req=2),
                     discard=dict(chars=3, tokens=1, events=1)),
                dict(type="spec", step=0, head_tok=1, dropped_chars=1, overflow_ids=[7]),
                dict(type="resume", step=0, overflow_tok=1, new_tok=1, match_len=1,
                     identical=True),
                dict(type="final", steps=1, completed=True, abort=None,
                     eval=dict(success=False))]) + "\n")
            r = I.load_run(q, "nofill")
            self.assertEqual(r["ids"], [[1, 2]])
            self.assertEqual(r["prompt_tok"], [4])
            self.assertFalse(r["success"])
            self.assertEqual(r["n_inject"], 1)
            self.assertEqual(r["discard_tok"], 1)
            self.assertEqual(len(r["resumes"]), 1)


if __name__ == "__main__":
    unittest.main()
