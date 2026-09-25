"""The probe's cut rules and prompt text: the offline cuts the build trains on and the live cuts the
injector scores are one rule (a live cut is always an offline cut of the finished text, and the
finished text's live cuts are its offline cuts less the terminal one), and `assemble` writes the
text shape both sides share."""
# venv: probe
from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from data.probe_input import assemble, cuts, cuts_live

WORDS = ["I", "need", "to", "call", "the", "api", "first.", "Then", "check!", "ok?", "Hmm.\n",
         "done.  ", "x", "\n\n", "apis.spotify.login()", "e.g.", "3.5"]
MIN_THINKS = (0, 1, 2, 10, 40, 100)
NO_THINNING = 10 ** 9


def _random_texts(n: int, seed: int = 0) -> list[str]:
    rng = random.Random(seed)
    return [" ".join(rng.choice(WORDS) for _ in range(rng.randint(1, 40))).strip() for _ in range(n)]


class OfflineCutsTest(unittest.TestCase):

    def test_max_cuts_below_two_is_refused(self):
        for bad in (0, 1):
            with self.assertRaises(ValueError):
                cuts("One. Two.", 0, bad)

    def test_sentence_ends_and_terminal(self):
        text = "First step. Second step!  Third?\nFourth"
        self.assertEqual(cuts(text, 0, NO_THINNING), [12, 26, 33, len(text)])
        for p in cuts(text, 0, NO_THINNING)[:-1]:
            self.assertFalse(text[p].isspace(), "a cut sits after the whole whitespace run")

    def test_min_think_drops_early_cuts(self):
        text = "Hi. " + "This is a much longer sentence of thinking. " * 3 + "End"
        every = cuts(text, 0, NO_THINNING)
        kept = cuts(text, 40, NO_THINNING)
        self.assertEqual(kept, [p for p in every if len(text[:p].strip()) >= 20])
        self.assertNotIn(every[0], kept)

    def test_no_eligible_cut_leaves_the_terminal_cut(self):
        self.assertEqual(cuts("tiny", 1000, 8), [4])

    def test_shape_on_random_texts(self):
        for text in _random_texts(500):
            for min_think in MIN_THINKS:
                for max_cuts in (2, 3, 8, NO_THINNING):
                    pts = cuts(text, min_think, max_cuts)
                    with self.subTest(text=text, min_think=min_think, max_cuts=max_cuts):
                        self.assertEqual(pts, sorted(set(pts)))
                        self.assertLessEqual(len(pts), max_cuts)
                        self.assertEqual(pts[-1], len(text))
                        full = cuts(text, min_think, NO_THINNING)
                        self.assertTrue(set(pts) <= set(full))
                        self.assertEqual(pts[0], full[0], "thinning keeps the first cut")


class LiveAgreesWithOfflineTest(unittest.TestCase):
    """Training text and live text end at the same kind of offset, or the probe scores a text
    shape it never saw in training."""

    def test_live_cuts_are_offline_cuts_at_every_prefix(self):
        for text in _random_texts(400, seed=1):
            for min_think in MIN_THINKS:
                offline = cuts(text, min_think, NO_THINNING)
                live_final = cuts_live(text, min_think)
                with self.subTest(text=text, min_think=min_think):
                    self.assertEqual(live_final, [p for p in offline if p != len(text)])
                    for n in range(len(text) + 1):
                        live = cuts_live(text[:n], min_think)
                        self.assertTrue(set(live) <= set(offline), f"prefix {n}")
                        self.assertEqual(live, live_final[:len(live)], f"prefix {n} is not monotone")

    def test_trailing_whitespace_holds_no_cut_yet(self):
        """The whitespace after a sentence may still be growing, so its cut waits for the next word."""
        self.assertEqual(cuts_live("Done. ", 0), [])
        self.assertEqual(cuts_live("Done.   ", 0), [])
        self.assertEqual(cuts_live("Done.   N", 0), [8])


class AssembleTest(unittest.TestCase):

    def test_empty_history(self):
        self.assertEqual(assemble("pay the bill", [], "I will", 3, 400),
                         "Task: pay the bill\n[HISTORY]\n(start)\n[THINKING]\nI will")

    def test_keeps_the_last_rounds_only(self):
        history = [(f"a{i}()", f"r{i}") for i in range(5)]
        text = assemble("t", history, "th", 2, 400)
        self.assertEqual(text, "Task: t\n[HISTORY]\na3() -> r3\na4() -> r4\n[THINKING]\nth")

    def test_long_results_are_clipped_head_and_tail(self):
        observation = "H" * 300 + "M" * 500 + "T" * 300
        line = assemble("t", [("a()", observation)], "", 1, 200).split("\n")[2]
        clipped = line[len("a() -> "):]
        self.assertTrue(clipped.startswith("H" * 140))
        self.assertTrue(clipped.endswith("T" * 40))
        self.assertIn(" ...[cut]... ", clipped)
        self.assertEqual(len(clipped), 200 - 60 + len(" ...[cut]... ") + 40)

    def test_short_results_are_untouched_and_small_caps_refused(self):
        self.assertIn("a() -> ok", assemble("t", [("a()", "ok")], "", 1, 100))
        with self.assertRaises(ValueError):
            assemble("t", [("a()", "ok")], "", 1, 99)

    def test_zero_rounds_keeps_no_history_and_negative_is_refused(self):
        history = [(f"a{i}()", f"r{i}") for i in range(3)]
        self.assertEqual(assemble("t", history, "th", 0, 400),
                         "Task: t\n[HISTORY]\n(start)\n[THINKING]\nth")
        with self.assertRaises(ValueError):
            assemble("t", history, "th", -1, 400)


if __name__ == "__main__":
    unittest.main()
