"""Test 2, additions from the debt map (plans/2026-09-05-research-loop-debt-map.md):
43(e) a dispatch=manual order is accepted by gyb himself by default (fyi to the owner
still sent), 45(a) a work_order opened without track is refused, 45(c) a launch_order
opened without --track copies the parent's top-level track into attempts[0].track.
Kept in a separate file so the per-row cases of test_02_transitions.py stay as written.
"""

import unittest

from helpers import Sandbox, make_decision, open_work_order, open_launch_order


class TestDebtMapAdditions(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def _manual_order_at_done_pending_review(self):
        sb = self.sb
        idea = sb.role_session("idea")
        dec = make_decision(sb, session=idea)
        ho = open_work_order(sb, idea, dec, extra=("--manual",))
        self.assertEqual(sb.latest("handoffs", ho)["dispatch"], "manual")  # 04 L88
        deploy = sb.role_session("deploy")
        sb.write_file("experiments/m/method.md")
        sb.write_file("experiments/m/detail.md")
        sb.write_file("experiments/m/x.py")
        sb.rl_ok("handoff", "amend", ho, "--report-method", "experiments/m/method.md",
                 "--report-detail", "experiments/m/detail.md", "--code-path", "experiments/m/x.py",
                 session=deploy)
        sb.rl_ok("handoff", "start", ho, session=deploy)
        sb.rl_ok("handoff", "done", ho, session=deploy)
        return idea, ho

    def test_manual_order_is_accepted_by_gyb_with_fyi_to_owner(self):
        """Debt map 43(e) (sync-inbox Q43(e) L311; 04 L70, L114): a dispatch=manual order
        is accepted by gyb himself by default; the fyi to the owner is still sent."""
        idea, ho = self._manual_order_at_done_pending_review()
        self.sb.rl_ok("handoff", "accept", ho)  # bare terminal = gyb
        row = self.sb.latest("handoffs", ho)
        self.assertEqual(row["status"], "accepted")
        self.assertEqual(row["actor"], "gyb")
        fyi = [i for i in self.sb.rows("issues") if i["kind"] == "fyi"]
        self.assertEqual(len(fyi), 1)
        self.assertEqual(fyi[0]["assignee"], "idea")

    def test_manual_order_owner_accept_still_passes(self):
        """Debt map 43(e): the owner accepting a manual order still passes (04 L70)."""
        idea, ho = self._manual_order_at_done_pending_review()
        self.sb.rl_ok("handoff", "accept", ho, session=idea)
        self.assertEqual(self.sb.latest("handoffs", ho)["status"], "accepted")
        self.assertEqual([i for i in self.sb.rows("issues") if i["kind"] == "fyi"], [])

    def test_work_order_open_without_track_refused(self):
        """Debt map 45(a) (sync-inbox Q45(a)(f) L329-330; proxy decision D-10): a
        work_order opened without --track is refused with exit 2 and no row."""
        sb = self.sb
        idea = sb.role_session("idea")
        dec = make_decision(sb, session=idea)
        before = sb.count("handoffs")
        r = sb.rl("handoff", "open", "--type", "work_order", "--to", "deploy",
                  "--decision", f"{dec}@1", "--explain", "build it", session=idea)
        self.assertEqual(r.rc, 2, str(r))
        self.assertEqual(r.kind, "validation")
        self.assertEqual(sb.count("handoffs"), before)

    def test_launch_order_without_track_copies_the_parent_track(self):
        """Debt map 45(c) (sync-inbox Q45(c)(f) L329-330; 04 L43): a launch_order opened
        without --track passes and attempts[0].track equals the parent's top-level track."""
        sb = self.sb
        idea = sb.role_session("idea")
        dec = make_decision(sb, session=idea)
        parent = open_work_order(sb, idea, dec, track="probe-line")
        deploy = sb.role_session("deploy")
        lo = open_launch_order(sb, deploy, parent)  # helper passes no --track
        row = sb.latest("handoffs", lo)
        self.assertEqual(row["attempts"][0]["track"], "probe-line")
        self.assertNotIn("track", {k for k, v in row.items() if k == "track" and v})  # no top-level track on a launch_order (45(f))


if __name__ == "__main__":
    unittest.main()
