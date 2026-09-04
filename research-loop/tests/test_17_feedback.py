"""Test 17: feedback account (30 L167-171; 03 L139-152; 09 L57-95).

Original: accept checks every applied_to path exists, rules_version is bumped by one,
the sessions ledger's open version records rules_version, inbox lists the ruling to
the proposer.

Added by 30 L171: verdict_text is required on both the accepted and rejected version
(03 L148); accept lists the still-live sessions with their rules_version and prints a
to-do (09 L59, L87; 05 command table); accept bumps rules_version and writes it back to
the first line of common/GLOBAL-RULES.md, an integer starting at 1, that line being the
single source of truth (09 L57-59); `feedback accept --text` is required (sync-inbox
fifth paragraph, restated at 09 L59 as verdict_text on accept).

`rl inbox` is a step-4 command, so the "inbox lists the verdict to the proposer" case
lives in Step4Commands below and stays red until step 4 builds it.
"""

import unittest

from helpers import Sandbox


class Feedback(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def _add_feedback(self, session=None, target="rule-06", text="use two-space indent"):
        r = self.sb.rl("feedback", "add", "--target", target, "--text", text, "--json", session=session)
        assert r.rc == 0, f"feedback add failed:\n{r}"
        return r.json["id"]

    def test_accept_checks_every_applied_to_path_exists(self):
        """03 L149, L152; 30 L171: accept checks every applied_to path exists."""
        fb = self._add_feedback()
        good = self.sb.write_file("notes/good.md")
        before = self.sb.count("feedback")
        refused = self.sb.rl("feedback", "accept", fb, "--applied-to", str(good.relative_to(self.sb.root)),
                             "--applied-to", "notes/does-not-exist.md", "--text", "partly adopted")
        self.assertEqual(refused.rc, 2, str(refused))
        self.assertEqual(refused.kind, "validation")
        self.assertEqual(self.sb.count("feedback"), before)
        self.sb.rl_ok("feedback", "accept", fb, "--applied-to", str(good.relative_to(self.sb.root)),
                      "--text", "adopted")
        self.assertEqual(self.sb.latest("feedback", fb)["status"], "accepted")

    def test_accept_bumps_rules_version_from_1_to_2(self):
        """09 L57-59; 03 L150: accept bumps rules_version by one and writes it back to
        common/GLOBAL-RULES.md's first line; the row gets rules_version_after."""
        fb = self._add_feedback()
        path = self.sb.write_file("notes/fix.md")
        rules_file = self.sb.common / "GLOBAL-RULES.md"
        self.assertEqual(rules_file.read_text().splitlines()[0], "rules_version: 1")
        self.sb.rl_ok("feedback", "accept", fb, "--applied-to", str(path.relative_to(self.sb.root)),
                      "--text", "adopted")
        self.assertEqual(rules_file.read_text().splitlines()[0], "rules_version: 2")
        row = self.sb.latest("feedback", fb)
        self.assertEqual(row["rules_version_after"], 2)

    def test_session_rules_version_reflects_bump_time(self):
        """03 L184; 09 L59, L65: a session started before the bump keeps rules_version 1
        in its open row; one started after the bump gets 2."""
        before_sid = self.sb.role_session("analysis")
        fb = self._add_feedback()
        path = self.sb.write_file("notes/fix2.md")
        self.sb.rl_ok("feedback", "accept", fb, "--applied-to", str(path.relative_to(self.sb.root)),
                      "--text", "adopted")
        after_sid = self.sb.role_session("deploy")
        self.assertEqual(self.sb.latest("sessions", before_sid)["rules_version"], 1)
        self.assertEqual(self.sb.latest("sessions", after_sid)["rules_version"], 2)

    def test_verdict_text_required_on_accept(self):
        """03 L148: verdict_text is required on the accepted version."""
        fb = self._add_feedback()
        path = self.sb.write_file("notes/fix3.md")
        before = self.sb.count("feedback")
        r = self.sb.rl("feedback", "accept", fb, "--applied-to", str(path.relative_to(self.sb.root)))
        self.assertEqual(r.rc, 2, str(r))
        self.assertEqual(r.kind, "validation")
        self.assertEqual(self.sb.count("feedback"), before)

    def test_verdict_text_required_on_reject(self):
        """03 L148: verdict_text is required on the rejected version."""
        fb = self._add_feedback()
        before = self.sb.count("feedback")
        r = self.sb.rl("feedback", "reject", fb)
        self.assertEqual(r.rc, 2, str(r))
        self.assertEqual(r.kind, "validation")
        self.assertEqual(self.sb.count("feedback"), before)

    def test_accept_lists_live_sessions_and_prints_a_todo(self):
        """09 L59, L87; 05 command table: accept lists the still-live sessions with
        their rules_version and prints a to-do."""
        live = self.sb.role_session("run")
        fb = self._add_feedback()
        path = self.sb.write_file("notes/fb-fix.md")
        r = self.sb.rl_ok("feedback", "accept", fb, "--applied-to", str(path.relative_to(self.sb.root)),
                          "--text", "adopted as written")
        self.assertIn(live, r.out)
        self.assertIn("rules_version", r.out)
        lines = [l for l in r.out.splitlines() if l.strip()]
        self.assertGreaterEqual(len(lines), 2, "expected the live-session listing plus a to-do line")


class Step4Commands(unittest.TestCase):
    """rl inbox is a step-4 command (05 L41, L131-143); this test stays red until step 4 builds it."""

    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_inbox_lists_the_verdict_to_the_proposer(self):
        """30 L169; 05 L131-143 item 5: inbox lists the verdict to the proposer."""
        proposer = self.sb.role_session("analysis")
        r = self.sb.rl("feedback", "add", "--target", "rule-06", "--text", "tighten rule-06",
                       "--json", session=proposer)
        self.assertEqual(r.rc, 0, str(r))
        fb = r.json["id"]
        path = self.sb.write_file("notes/fb-verdict.md")
        self.sb.rl_ok("feedback", "accept", fb, "--applied-to", str(path.relative_to(self.sb.root)),
                      "--text", "adopted as written")
        inbox = self.sb.rl_ok("inbox", session=proposer)
        self.assertIn(fb, inbox.out)


if __name__ == "__main__":
    unittest.main()
