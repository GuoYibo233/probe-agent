"""Test 6: cross-ledger write order (30 L70-74; 03 L23).

Original (30 L72): simulate the issue write succeeding and the handoff write failing;
`rl doctor` reports the corresponding item and gives the `issue link` fix.

Changed by 05-rl-cli.md doctor table (30 L74, 2026-08-17 ruled): the item is now numbered
(item 3, "a `stuck` order with no issue"), the fix command is `rl issue link ID --handoff
ID`, and "who it gets pushed to" is the role that set the order to `stuck`.

03 L23: "The write order across the two ledgers is fixed: write the issue first to get
its number, then write the order's row citing it. If it crashes in between, at worst
there is one extra issue nobody cites, which `rl doctor` can scan out." The two ledger
writes for marking something stuck are (1) the issue and (2) the handoff's `stuck`
transition, which cites the issue by id and is itself gated by the precondition that the
issue points back (04-handoffs-and-sessions.md L89, `stuck.issue_links_back`). Simulating
write (2) failing/never happening, without `--force`, is exactly this test's setup: an
issue exists, but the order it was meant for never actually became `stuck` because the
issue does not (yet) point back at it.
"""

import json
import unittest

from helpers import Sandbox, make_decision, open_work_order


class CrossLedgerOrder(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def _open_order_and_orphan_issue(self):
        """An in_progress order, plus an issue that does not point back at it - the state
        left behind if the second of the two cross-ledger writes (03 L23) never lands."""
        sid = self.sb.role_session("deploy")
        dec = make_decision(self.sb)
        ho = open_work_order(self.sb, None, dec, to_role="deploy")
        r_start = self.sb.rl("handoff", "start", ho, session=sid)
        assert r_start.rc == 0, f"handoff start failed:\n{r_start}"
        r_issue = self.sb.rl("issue", "open", "--to", "gyb", "--kind", "request", "--text", "blocked, need input",
                             "--json", session=sid)
        assert r_issue.rc == 0, f"issue open failed:\n{r_issue}"
        return sid, ho, r_issue.json["id"]

    def test_stuck_with_an_issue_that_does_not_point_back_is_exit_2(self):
        # 04-handoffs-and-sessions.md L89: "issue_id points to an issue that exists, and that
        # issue's handoff_id points back to this order"; the freshly-opened issue here has no
        # handoff_id at all.
        sid, ho, iss = self._open_order_and_orphan_issue()
        r = self.sb.rl("handoff", "stuck", ho, "--issue", iss, session=sid)
        self.assertEqual(r.rc, 2, str(r))
        self.assertEqual(r.kind, "validation")
        # refused write -> no new row (helpers.py convention); order is still in_progress.
        self.assertEqual(self.sb.latest("handoffs", ho)["status"], "in_progress")

    def test_issue_link_appends_a_version_that_only_adds_handoff_id(self):
        # 05-rl-cli.md L31, L197: `rl issue link ID --handoff ID` is the doctor item 3 fix.
        sid, ho, iss = self._open_order_and_orphan_issue()
        rows_before = [row for row in self.sb.rows("issues") if row["id"] == iss]
        self.assertEqual(len(rows_before), 1)
        v1 = rows_before[0]
        self.assertIn(v1.get("handoff_id"), (None, ""))
        r = self.sb.rl("issue", "link", iss, "--handoff", ho, "--json")
        self.assertEqual(r.rc, 0, str(r))
        rows_after = [row for row in self.sb.rows("issues") if row["id"] == iss]
        self.assertEqual(len(rows_after), 2)
        v2 = self.sb.latest("issues", iss)
        self.assertEqual(v2["version"], v1["version"] + 1)
        self.assertEqual(v2["handoff_id"], ho)
        # only handoff_id changed - everything else copied from v1.
        self.assertEqual(v2["kind"], v1["kind"])
        self.assertEqual(v2["text"], v1["text"])
        self.assertEqual(v2["assignee"], v1["assignee"])
        self.assertEqual(v2["status"], v1["status"])

    def test_stuck_succeeds_after_issue_link(self):
        sid, ho, iss = self._open_order_and_orphan_issue()
        r_link = self.sb.rl("issue", "link", iss, "--handoff", ho)
        self.assertEqual(r_link.rc, 0, str(r_link))
        r = self.sb.rl("handoff", "stuck", ho, "--issue", iss, session=sid)
        self.assertEqual(r.rc, 0, str(r))
        latest = self.sb.latest("handoffs", ho)
        self.assertEqual(latest["status"], "stuck")
        self.assertEqual(latest["issue_id"], iss)
        # 04-handoffs-and-sessions.md L11 holder_invariant: every exit from in_progress
        # clears holder and copies it into last_holder.
        self.assertIsNone(latest["holder"])
        self.assertEqual(latest["last_holder"], sid)


class Step4Commands(unittest.TestCase):
    """`rl doctor` is a step-4 deliverable (30 L197 step table, row '4 communication
    mechanism'); step 3 has no scripts/rl_cmds handler for it, so this stays red - by
    design - until step 4 lands."""

    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_doctor_reports_stuck_order_without_issue_pushed_to_the_role_that_set_stuck(self):
        # 05-rl-cli.md L197, doctor item 3: scan "a `stuck` order with no issue"; fix
        # `rl issue link ID --handoff ID`; pushed to "the role that turned the order into
        # stuck".
        #
        # Reaching a `stuck` order whose issue does not point back requires bypassing the
        # stuck.issue_links_back precondition; 03-ledgers.md L27 and
        # 04-handoffs-and-sessions.md header rule preconditions_bind_gyb say gyb may do
        # this with --force --reason (integrity preconditions bind gyb too, but gyb alone
        # may force past them, which is recorded in force_reason).
        sid = self.sb.role_session("deploy")
        dec = make_decision(self.sb)
        ho = open_work_order(self.sb, None, dec, to_role="deploy")
        r_start = self.sb.rl("handoff", "start", ho, session=sid)
        self.assertEqual(r_start.rc, 0, str(r_start))
        r_issue = self.sb.rl("issue", "open", "--to", "gyb", "--kind", "request", "--text", "unrelated issue",
                             "--json")
        self.assertEqual(r_issue.rc, 0, str(r_issue))
        iss = r_issue.json["id"]
        r_force = self.sb.rl("handoff", "stuck", ho, "--issue", iss, "--force", "--reason",
                             "test: force stuck without a real linking issue")
        self.assertEqual(r_force.rc, 0, str(r_force))
        self.assertEqual(self.sb.latest("handoffs", ho)["status"], "stuck")
        r_doctor = self.sb.rl("doctor", "--json")
        self.assertEqual(r_doctor.rc, 0, str(r_doctor))
        dump = json.dumps(r_doctor.json)
        self.assertIn(ho, dump)
        self.assertIn("issue link", dump)


if __name__ == "__main__":
    unittest.main()
