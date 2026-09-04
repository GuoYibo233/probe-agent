"""Test 15: withdraw and reissue (30 L150-154).

Original (30 L152): withdrawing an order that has a holder auto-opens a `withdrawn`
notice to the holder's role and to the owner; `--cascade` withdraws, along parent_id, the
derived orders; `reissue` withdraws the old order and opens a new one, `supersedes`
pointing at the old id.

Changed (30 L154): the `withdrawn` notice only opens when the order is withdrawn from
`in_progress`; withdrawing from any other status opens no notice (04 L194, L74).

Added (30 L154): notification-kind issues (`withdrawn`, `orphaned`, `fyi`) are not
closed automatically -- the recipient closes them themselves with `rl issue close`;
`withdrawn` and `orphaned` carry `handoff_id` (04 L194-198; 03 L92 assignee may close a
notification kind). gyb overriding the owner on accept or reject both send an `fyi` to
the owner, including for a dispatch=manual order (04 L70, L71, L114; sync-inbox Q43(e)).
"""

import unittest

from helpers import Sandbox, make_decision, open_work_order, open_launch_order


def _idea(sb):
    return sb.role_session("idea")


def _deploy(sb):
    return sb.role_session("deploy")


def _new_work_order(sb, to_role="deploy", explanation="build it", extra=()):
    """(idea_session, ho_id): a fresh work_order at todo, owner idea (04 L61)."""
    idea = _idea(sb)
    dec = make_decision(sb, session=idea)
    ho_id = open_work_order(sb, idea, dec, to_role=to_role, explanation=explanation, extra=extra)
    return idea, ho_id


def _to_done_pending_review(sb, tag, extra_open=()):
    """(idea_session, deploy_session, ho_id) with a work_order pushed to
    done_pending_review, owner idea (helper mirrors test_02/test_04's own local copy)."""
    idea, ho_id = _new_work_order(sb, extra=extra_open)
    deploy = _deploy(sb)
    sb.write_file(f"experiments/{tag}/method.md", "# method\n")
    sb.write_file(f"experiments/{tag}/detail.md", "# detail\n")
    sb.rl_ok("handoff", "amend", ho_id, "--report-method", f"experiments/{tag}/method.md",
             "--report-detail", f"experiments/{tag}/detail.md", "--code-path", f"experiments/{tag}/x.py",
             session=deploy)
    sb.rl_ok("handoff", "start", ho_id, session=deploy)
    sb.rl_ok("handoff", "done", ho_id, session=deploy)
    return idea, deploy, ho_id


def _issue_ids_matching(sb, **filters):
    """Distinct issue ids that carry the given field values in any version (kind,
    assignee and handoff_id are set at open and are not expected to change for the
    notification kinds under test here)."""
    ids = set()
    for row in sb.rows("issues"):
        if all(row.get(k) == v for k, v in filters.items()):
            ids.add(row["id"])
    return ids


class TestWithdrawNotify(unittest.TestCase):
    """withdrawing from in_progress opens a `withdrawn` notice to the holder's role and
    to the owner; other statuses open no notice (30 L152, L154; 04 L74, L194)."""

    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_withdraw_from_in_progress_opens_two_withdrawn_notices(self):
        sb = self.sb
        idea, ho_id = _new_work_order(sb)
        deploy = _deploy(sb)
        sb.rl_ok("handoff", "start", ho_id, session=deploy)  # holder = deploy
        sb.rl_ok("handoff", "withdraw", ho_id, "--reason", "no longer needed",
                 "--quote", "gyb said drop it", session=idea)
        row = sb.latest("handoffs", ho_id)
        self.assertEqual(row["status"], "withdrawn")

        ids = _issue_ids_matching(sb, kind="withdrawn", handoff_id=ho_id)
        self.assertEqual(len(ids), 2, "one notice to the holder's role, one to the owner (04 L194)")
        rows = [sb.latest("issues", i) for i in ids]
        assignees = {r["assignee"] for r in rows}
        self.assertEqual(assignees, {"deploy", "idea"})  # holder's role and owner
        for r in rows:
            self.assertEqual(r["status"], "open")  # not auto-closed (04 L198)
            self.assertEqual(r["handoff_id"], ho_id)  # required for withdrawn (04 L198)

    def test_withdraw_from_todo_opens_no_notice(self):
        """04 L194: withdrawing from any status other than in_progress does not notify;
        todo has no holder to begin with."""
        sb = self.sb
        idea, ho_id = _new_work_order(sb)  # still todo
        sb.rl_ok("handoff", "withdraw", ho_id, "--reason", "no longer needed",
                 "--quote", "gyb said drop it", session=idea)  # role session still needs --quote (04 L74)
        row = sb.latest("handoffs", ho_id)
        self.assertEqual(row["status"], "withdrawn")
        ids = _issue_ids_matching(sb, kind="withdrawn", handoff_id=ho_id)
        self.assertEqual(len(ids), 0)


class TestWithdrawNoticeRecipientCloses(unittest.TestCase):
    """Notification-kind issues are not closed automatically; the recipient closes them
    with `rl issue close` (04 L198; 03 L92: the assignee may close a notification
    kind)."""

    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_recipient_closes_their_own_withdrawn_notice(self):
        sb = self.sb
        idea, ho_id = _new_work_order(sb)
        deploy = _deploy(sb)
        sb.rl_ok("handoff", "start", ho_id, session=deploy)
        sb.rl_ok("handoff", "withdraw", ho_id, "--reason", "stop", "--quote", "gyb: stop", session=idea)

        ids = _issue_ids_matching(sb, kind="withdrawn", handoff_id=ho_id)
        rows = {r["assignee"]: r for r in (sb.latest("issues", i) for i in ids)}
        self.assertEqual(set(rows), {"deploy", "idea"})
        self.assertEqual(rows["deploy"]["status"], "open")  # not read-and-closed (04 L198)
        self.assertEqual(rows["idea"]["status"], "open")

        # deploy is the assignee of its own notice, not the actor that opened it (idea's
        # withdraw call did) -- 03 L92 lets the assignee close a notification kind anyway.
        sb.rl_ok("issue", "close", rows["deploy"]["id"], session=deploy)
        self.assertEqual(sb.latest("issues", rows["deploy"]["id"])["status"], "closed")

        sb.rl_ok("issue", "close", rows["idea"]["id"], session=idea)
        self.assertEqual(sb.latest("issues", rows["idea"]["id"])["status"], "closed")


class TestWithdrawnNoticeTextPending(unittest.TestCase):
    """PENDING: the withdrawn notice's own literal text is not ruled anywhere -- only
    its intended content is (the holder reports the code location and the half-finished
    artifact directory into that withdrawn issue, sync-inbox Q45(b) L329); the
    transitions table marks this side effect explicitly as 'discipline for the holder,
    not a check' rl performs, so there is no machine-checkable behaviour to assert. The
    debt map for this exact point (plans/2026-09-05-research-loop-debt-map.md L555) also
    concludes rl cannot check whether the holder replied, so no new test case is added
    for that half. The run-holder branch is separately PENDING(issue 50): run's issues
    write permission (reply/close) is undecided in the frozen role json."""

    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_withdrawn_notice_tells_holder_to_report_location_and_artifact_dir(self):
        self.skipTest(
            "PENDING(sync-inbox Q45(b) L329 / issue 50): no literal wording is ruled for "
            "the withdrawn notice's text field, only its intended content; whether rl "
            "bakes that instruction into the notice text is undecided, and the run-holder "
            "branch is additionally blocked on issue 50 (run's issues reply/close "
            "permission is undecided in 06)."
        )


class TestWithdrawCascade(unittest.TestCase):
    """`--cascade` withdraws, on the owner's behalf, the orders whose parent_id points
    at the withdrawn order; those downstream rows record the initiator as actor (04
    L74)."""

    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_cascade_withdraws_children_actor_is_initiator_unrelated_order_untouched(self):
        sb = self.sb
        idea, wo_id = _new_work_order(sb)
        deploy = _deploy(sb)
        lo1 = open_launch_order(sb, deploy, wo_id)
        lo2 = open_launch_order(sb, deploy, wo_id)

        # an unrelated launch_order under a different parent must not be touched
        idea2, wo_id2 = _new_work_order(sb)
        deploy2 = _deploy(sb)
        lo3 = open_launch_order(sb, deploy2, wo_id2)

        sb.rl_ok("handoff", "withdraw", wo_id, "--reason", "stop this line",
                 "--quote", "gyb: stop this line", "--cascade", session=idea)

        wo_row = sb.latest("handoffs", wo_id)
        self.assertEqual(wo_row["status"], "withdrawn")
        for lo_id in (lo1, lo2):
            lo_row = sb.latest("handoffs", lo_id)
            self.assertEqual(lo_row["status"], "withdrawn")
            self.assertEqual(lo_row["actor"], "idea")  # 04 L74: downstream actor = initiator

        lo3_row = sb.latest("handoffs", lo3)
        self.assertEqual(lo3_row["status"], "todo")  # untouched: different parent_id

        # none of these were in_progress, so cascading withdrawal opens no notice either
        # (04 L194 extends to the cascaded rows the same way it does to the top order)
        for hid in (wo_id, lo1, lo2):
            self.assertEqual(len(_issue_ids_matching(sb, kind="withdrawn", handoff_id=hid)), 0)


class TestReissue(unittest.TestCase):
    """`rl handoff reissue ID --decision DEC@V` by the owner: the old order is withdrawn
    (cascading), the new order starts at todo with supersedes = old id, inheriting
    explanation, parent_id and batch (04 L76; 02 L91); every holder of the withdrawn
    order is notified (04 L76), which for an in_progress holder is the same withdrawn
    notice mechanism as plain withdraw (04 L74, L194)."""

    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_reissue_inherits_explanation_parent_id_batch(self):
        sb = self.sb
        idea = _idea(sb)
        dec = make_decision(sb, session=idea)
        old_id = open_work_order(sb, idea, dec, explanation="try lr 1e-4 first",
                                  extra=("--batch", "B1"))
        old_row_before = sb.latest("handoffs", old_id)
        self.assertEqual(old_row_before["batch"], "B1")  # sanity: batch landed on the old row

        dec2 = make_decision(sb, session=idea, text="try lr 3e-4")
        r = sb.rl_ok("handoff", "reissue", old_id, "--decision", f"{dec2}@1", "--json", session=idea)
        new_id = r.json["id"]

        old_row = sb.latest("handoffs", old_id)
        self.assertEqual(old_row["status"], "withdrawn")
        new_row = sb.latest("handoffs", new_id)
        self.assertEqual(new_row["status"], "todo")
        self.assertEqual(new_row["supersedes"], old_id)
        self.assertEqual(new_row["explanation"], old_row["explanation"])
        self.assertEqual(new_row["parent_id"], old_row["parent_id"])
        self.assertEqual(new_row["batch"], "B1")

    def test_reissue_notifies_every_holder(self):
        sb = self.sb
        idea, old_id = _new_work_order(sb)
        deploy = _deploy(sb)
        sb.rl_ok("handoff", "start", old_id, session=deploy)  # holder = deploy

        dec2 = make_decision(sb, session=idea, text="try lr 3e-4")
        sb.rl_ok("handoff", "reissue", old_id, "--decision", f"{dec2}@1", session=idea)

        old_row = sb.latest("handoffs", old_id)
        self.assertEqual(old_row["status"], "withdrawn")
        ids = _issue_ids_matching(sb, kind="withdrawn", handoff_id=old_id)
        self.assertEqual(len(ids), 2)
        assignees = {sb.latest("issues", i)["assignee"] for i in ids}
        self.assertEqual(assignees, {"deploy", "idea"})  # holder's role and owner


class TestFyiOnGybOverride(unittest.TestCase):
    """gyb accepting or rejecting a done_pending_review order over the owner sends an
    `fyi` to the owner, including for a dispatch=manual order (04 L70, L71, L114; 30
    L154; sync-inbox Q43(e))."""

    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_gyb_accept_over_owner_sends_fyi(self):
        sb = self.sb
        idea, deploy, ho_id = _to_done_pending_review(sb, "fyi1")
        sb.rl_ok("handoff", "accept", ho_id, session=None)  # bare terminal = gyb, bypasses owner
        row = sb.latest("handoffs", ho_id)
        self.assertEqual(row["status"], "accepted")
        ids = _issue_ids_matching(sb, kind="fyi", assignee="idea")
        self.assertTrue(ids, "gyb accepting over the owner must open an fyi issue to the owner")

    def test_gyb_reject_over_owner_sends_fyi(self):
        sb = self.sb
        idea, deploy, ho_id = _to_done_pending_review(sb, "fyi2")
        sb.rl_ok("handoff", "reject", ho_id, "--reason", "not convincing", session=None)
        row = sb.latest("handoffs", ho_id)
        self.assertEqual(row["status"], "rejected")
        ids = _issue_ids_matching(sb, kind="fyi", assignee="idea")
        self.assertTrue(ids, "gyb rejecting over the owner must open an fyi issue to the owner")

    def test_owner_accept_sends_no_fyi(self):
        """fyi only fires when gyb overrides the owner (04 L70, L114); the owner
        accepting its own order does not trigger it."""
        sb = self.sb
        idea, deploy, ho_id = _to_done_pending_review(sb, "fyi3")
        sb.rl_ok("handoff", "accept", ho_id, session=idea)  # owner itself, not gyb
        ids = _issue_ids_matching(sb, kind="fyi", assignee="idea")
        self.assertEqual(len(ids), 0)

    def test_gyb_accept_over_owner_sends_fyi_for_manual_dispatch_order(self):
        """sync-inbox Q43(e): gyb accepting by default is expected for a dispatch=manual
        order, but rl still sends the owner an fyi -- the trigger is actor != owner, not
        whether gyb's involvement was expected."""
        sb = self.sb
        idea, deploy, ho_id = _to_done_pending_review(sb, "fyi4", extra_open=("--manual",))
        sb.rl_ok("handoff", "accept", ho_id, session=None)
        row = sb.latest("handoffs", ho_id)
        self.assertEqual(row["status"], "accepted")
        ids = _issue_ids_matching(sb, kind="fyi", assignee="idea")
        self.assertTrue(ids)


if __name__ == "__main__":
    unittest.main()
