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

from data.probe_input import assemble, cuts, cuts_live, rounds_cut

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


class TextBudgetTest(unittest.TestCase):
    """build.probe_prefix_max_chars cuts the oldest kept rounds until the lines before the
    thinking fit; the task and the thinking are never cut, the rounds a step keeps do not depend
    on the thinking prefix, and no budget (None) leaves every text as it was."""

    HISTORY = [(f"a{i}()", f"r{i}") for i in range(5)]

    @staticmethod
    def _prefix_len(text: str) -> int:
        """The characters before the [THINKING] line, each line with its newline."""
        return text.index("[THINKING]")

    def test_no_budget_changes_nothing(self):
        for hist_rounds in (0, 2, 5, 9):
            with self.subTest(hist_rounds=hist_rounds):
                self.assertEqual(assemble("t", self.HISTORY, "th", hist_rounds, 400, None),
                                 assemble("t", self.HISTORY, "th", hist_rounds, 400))
                self.assertEqual(rounds_cut("t", self.HISTORY, "th", hist_rounds, 400, None), 0)

    def test_a_wide_budget_cuts_nothing(self):
        full = assemble("t", self.HISTORY, "th", 5, 400)
        budget = self._prefix_len(full)
        self.assertEqual(assemble("t", self.HISTORY, "th", 5, 400, budget), full)
        self.assertEqual(rounds_cut("t", self.HISTORY, "th", 5, 400, budget), 0)

    def test_the_oldest_rounds_go_first_until_the_prefix_fits(self):
        full = assemble("t", self.HISTORY, "th", 5, 400)
        prefix = self._prefix_len(full)
        one_round = len("a0() -> r0\n")
        text = assemble("t", self.HISTORY, "th", 5, 400, prefix - 1)
        self.assertEqual(text, "Task: t\n[HISTORY]\na1() -> r1\na2() -> r2\na3() -> r3\na4() -> r4\n[THINKING]\nth")
        self.assertLessEqual(self._prefix_len(text), prefix - 1)
        self.assertEqual(rounds_cut("t", self.HISTORY, "th", 5, 400, prefix - 1), 1)
        text = assemble("t", self.HISTORY, "th", 5, 400, prefix - 3 * one_round)
        self.assertEqual(text, "Task: t\n[HISTORY]\na3() -> r3\na4() -> r4\n[THINKING]\nth")
        self.assertEqual(rounds_cut("t", self.HISTORY, "th", 5, 400, prefix - 3 * one_round), 3)

    def test_the_thinking_does_not_count(self):
        """Every cut of one step keeps the same rounds, whatever the thinking prefix's length:
        the trainer packs a step's cuts behind one shared prefix."""
        prefix = self._prefix_len(assemble("t", self.HISTORY, "", 5, 400))
        budget = prefix - 1
        kept_lines = None
        for thinking in ("", "th", "a much longer thinking prefix " * 50):
            text = assemble("t", self.HISTORY, thinking, 5, 400, budget)
            lines = text.split("\n")[: text.split("\n").index("[THINKING]")]
            if kept_lines is None:
                kept_lines = lines
            self.assertEqual(lines, kept_lines)
            self.assertEqual(rounds_cut("t", self.HISTORY, thinking, 5, 400, budget), 1)
            self.assertTrue(text.endswith(thinking))

    def test_the_budget_counts_only_the_kept_rounds(self):
        """hist_rounds keeps the last two; the budget then cuts from those two, never from the
        three it never kept."""
        two = assemble("t", self.HISTORY, "th", 2, 400)
        budget = self._prefix_len(two) - 1
        text = assemble("t", self.HISTORY, "th", 2, 400, budget)
        self.assertEqual(text, "Task: t\n[HISTORY]\na4() -> r4\n[THINKING]\nth")
        self.assertEqual(rounds_cut("t", self.HISTORY, "th", 2, 400, budget), 1)

    def test_task_and_thinking_survive_a_budget_below_them(self):
        """Every round is cut, and the history line says so instead of reading like a first step."""
        text = assemble("a long task line", self.HISTORY, "a long thinking prefix", 5, 400, 1)
        self.assertEqual(text, "Task: a long task line\n[HISTORY]\n(earlier rounds cut)\n[THINKING]\na long thinking prefix")
        self.assertEqual(assemble("a long task line", [], "a long thinking prefix", 5, 400, 1),
                         "Task: a long task line\n[HISTORY]\n(start)\n[THINKING]\na long thinking prefix")
        self.assertEqual(rounds_cut("a long task line", self.HISTORY, "a long thinking prefix", 5, 400, 1), 5)
        self.assertTrue(text.endswith("a long thinking prefix"), "the build's prefix gate still holds")

    def test_the_prefix_fits_the_budget_whenever_a_round_is_left(self):
        for text in _random_texts(200, seed=2):
            history = [(f"call{i}()", text[: (i * 7) % max(len(text), 1)]) for i in range(6)]
            full = assemble(text[:20], history, text, 6, 400)
            for budget in (1, 50, 100, 200, 400, 800, self._prefix_len(full)):
                out = assemble(text[:20], history, text, 6, 400, budget)
                n_cut = rounds_cut(text[:20], history, text, 6, 400, budget)
                with self.subTest(text=text, budget=budget):
                    self.assertTrue(out.endswith(text))
                    if n_cut < 6:
                        self.assertLessEqual(self._prefix_len(out), budget)
                        # what is left is exactly the newest rounds, written as without a budget
                        self.assertEqual(out, assemble(text[:20], history[n_cut:], text, 6, 400))
                    else:
                        self.assertIn("\n(earlier rounds cut)\n", out)
                    # the same rounds for every thinking prefix of the step
                    self.assertEqual(rounds_cut(text[:20], history, "", 6, 400, budget), n_cut)

    def test_a_budget_below_one_is_refused(self):
        with self.assertRaises(ValueError):
            assemble("t", self.HISTORY, "th", 5, 400, 0)


if __name__ == "__main__":
    unittest.main()
