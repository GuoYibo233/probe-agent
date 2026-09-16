"""The injection format table (pipeline/inject/inject_format.py): what text goes back into the
stream when the probe fires, and where. Pure stdlib.
    python3 -m unittest tests.test_inject_format -v
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline" / "inject"))

import inject_format as F                                       # noqa: E402

CALL = "apis.supervisor.show_profile()"
RESULT = '{\n "first_name": "Claudia"\n}\n'
HEAD_WS = "<|channel|>analysis<|message|>We need the profile.\n\n"   # head ends in whitespace
HEAD_NOWS = "<|channel|>analysis<|message|>We need the profile."    # head ends at the punctuation
P2_OPEN = "<|end|><|start|>prefetch to=assistant<|channel|>analysis<|message|>"
P2_CLOSE = "<|end|><|start|>assistant"


class TestTable(unittest.TestCase):
    def test_five_formats_registered(self):
        self.assertEqual(set(F.FORMATS), {"note", "p1_e1", "p1_e2", "p2_e1", "p2_e2"})

    def test_unknown_format_is_refused(self):
        with self.assertRaises(KeyError):
            F.splice_text("p9", HEAD_WS, CALL, RESULT)


class TestNote(unittest.TestCase):
    """`note` is the behaviour before the format table existed, kept byte for byte."""

    def test_head_with_trailing_whitespace_gets_no_leading_newline(self):
        self.assertEqual(F.splice_text("note", HEAD_WS, CALL, RESULT),
                         f"[SYSTEM NOTE: prefetched {CALL} = {RESULT}]\n")

    def test_head_without_trailing_whitespace_gets_one_newline(self):
        self.assertEqual(F.splice_text("note", HEAD_NOWS, CALL, RESULT),
                         f"\n[SYSTEM NOTE: prefetched {CALL} = {RESULT}]\n")

    def test_no_system_extra(self):
        self.assertEqual(F.system_extra("note"), "")


class TestP1(unittest.TestCase):
    def test_p1_e1_explains_inline(self):
        t = F.splice_text("p1_e1", HEAD_NOWS, CALL, RESULT)
        self.assertTrue(t.startswith("\n[Prefetch: "))
        self.assertIn(CALL, t)
        self.assertIn(RESULT, t)
        self.assertIn("without calling it", t)
        self.assertTrue(t.endswith("]\n"))
        self.assertEqual(F.system_extra("p1_e1"), "")

    def test_p1_e1_seam_follows_head(self):
        self.assertTrue(F.splice_text("p1_e1", HEAD_WS, CALL, RESULT).startswith("[Prefetch: "))

    def test_p1_e2_marker_only_and_system_paragraph(self):
        t = F.splice_text("p1_e2", HEAD_WS, CALL, RESULT)
        self.assertEqual(t, f"[Prefetch] {CALL} = {RESULT}\n")
        self.assertNotIn("without calling it", t)
        self.assertIn("[Prefetch]", F.system_extra("p1_e2"))
        self.assertIn("without calling it again", F.system_extra("p1_e2"))

    def test_p1_texts_carry_no_control_markers(self):
        for name in ("note", "p1_e1", "p1_e2"):
            self.assertNotIn("<|", F.splice_text(name, HEAD_WS, CALL, RESULT), name)
            self.assertFalse(F.needs_special(name), name)


class TestP2(unittest.TestCase):
    def test_p2_e1_closes_thinking_and_speaks_as_prefetch(self):
        t = F.splice_text("p2_e1", HEAD_NOWS, CALL, RESULT)
        self.assertTrue(t.startswith(P2_OPEN))
        self.assertTrue(t.endswith(P2_CLOSE))
        body = t[len(P2_OPEN):-len(P2_CLOSE)]
        self.assertIn(CALL, body)
        self.assertIn(RESULT, body)
        self.assertIn("without calling it", body)
        self.assertNotIn("<|", body)
        self.assertEqual(F.system_extra("p2_e1"), "")

    def test_p2_ignores_head_seam(self):
        self.assertEqual(F.splice_text("p2_e1", HEAD_WS, CALL, RESULT),
                         F.splice_text("p2_e1", HEAD_NOWS, CALL, RESULT))

    def test_p2_e2_body_is_call_and_result_with_system_paragraph(self):
        t = F.splice_text("p2_e2", HEAD_NOWS, CALL, RESULT)
        self.assertEqual(t, f"{P2_OPEN}{CALL} = {RESULT}{P2_CLOSE}")
        self.assertIn("prefetch", F.system_extra("p2_e2"))

    def test_p2_needs_special_tokens(self):
        self.assertTrue(F.needs_special("p2_e1"))
        self.assertTrue(F.needs_special("p2_e2"))

    def test_p2_sender_is_recognised(self):
        self.assertTrue(F.is_prefetch_header("<|start|>prefetch to=assistant<|channel|>analysis"))
        self.assertFalse(F.is_prefetch_header("<|start|>assistant<|channel|>analysis"))
        self.assertFalse(F.is_prefetch_header("<|channel|>analysis"))


if __name__ == "__main__":
    unittest.main()
