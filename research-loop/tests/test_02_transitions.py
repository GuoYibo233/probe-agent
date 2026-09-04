"""Test 2: transition table (30 L39-50).

One legal case per row of tables/transitions.json (04 L59-76 full table text; 07 L105-114
the two quick-lane rows), three illegal cases (cross-state, wrong role, missing
precondition, all exit 2 with no new row, 30 L39-41), the holder invariant across every
exit from in_progress including done_pending_review (04 L51; 30 L45), the adoption case
(04 L54, L63, L98; 03 L100), the out-of-table-refused-for-gyb-with-force case (04 L55,
L57; 03 L228), and reissue's cascade/supersedes side effects (04 L74, L76).
"""

import unittest

from helpers import Sandbox, make_decision, open_work_order, open_launch_order


def _idea(sb):
    return sb.role_session("idea")


def _deploy(sb):
    return sb.role_session("deploy")


def _run(sb):
    return sb.role_session("run")


def _analysis(sb):
    return sb.role_session("analysis")


def _new_work_order(sb, to_role="deploy"):
    """(idea_session, ho_id): a fresh work_order at todo, owner idea (04 L61)."""
    idea = _idea(sb)
    dec = make_decision(sb, session=idea)
    ho_id = open_work_order(sb, idea, dec, to_role=to_role)
    return idea, ho_id


def _open_issue_against(sb, session, ho_id, to_role="idea"):
    r = sb.rl_ok("issue", "open", "--to", to_role, "--kind", "request",
                 "--text", "need clarification", "--handoff", ho_id, "--json", session=session)
    return r.json["id"]


class TestLegalTransitions(unittest.TestCase):
    """One legal case per transition-table row."""

    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_row_open(self):
        """(new) -> todo, who=from_role, needs decision_refs+explanation (04 L61) and track
        (sync-inbox Q45(a)(f) L329-330; proxy decision D-10)."""
        sb = self.sb
        idea, ho_id = _new_work_order(sb)
        row = sb.latest("handoffs", ho_id)
        self.assertEqual(row["status"], "todo")
        self.assertEqual(row["from_role"], "idea")
        self.assertEqual(row["to_role"], "deploy")
        self.assertTrue(row["decision_refs"])
        self.assertTrue(row["explanation"])
        self.assertTrue(row["track"])
        self.assertIsNone(row["holder"])  # 04 L51: holder empty outside in_progress

    def test_row_open_quick_lane(self):
        """(new) -> done_pending_review, who=deploy, owner recorded gyb (04 L62; 07 L94-103, L116)."""
        sb = self.sb
        deploy = _deploy(sb)
        ql = sb.rl_ok("ql", "open", "--role", "deploy", "--json", session=deploy).json["ql_tag"]
        sb.write_file(f"experiments/{ql}/method.md", "# method\n")
        r = sb.rl_ok("handoff", "open", "--type", "work_order", "--to", "deploy", "--quick-lane",
                     "--report-method", f"experiments/{ql}/method.md", "--ql", ql,
                     "--explain", "gyb said: just try it", "--code-path", "experiments/x.py",
                     "--track", "probe", "--json", session=deploy)
        row = sb.latest("handoffs", r.json["id"])
        self.assertEqual(row["status"], "done_pending_review")
        self.assertTrue(row["quick_lane"])
        self.assertEqual(row["ql_tag"], ql)
        # proxy decision D-24 (04 L19; 07 L96, L116): the supplement row is written with
        # actor deploy, from_role gyb (the owner) and to_role deploy (who did the work).
        self.assertEqual(row["actor"], "deploy")
        self.assertEqual(row["from_role"], "gyb")
        self.assertEqual(row["to_role"], "deploy")
        self.assertIsNone(row["holder"])

    def test_row_start(self):
        """todo -> in_progress, who=to_role, holder was empty (04 L63)."""
        sb = self.sb
        idea, ho_id = _new_work_order(sb)
        deploy = _deploy(sb)
        sb.rl_ok("handoff", "start", ho_id, session=deploy)
        row = sb.latest("handoffs", ho_id)
        self.assertEqual(row["status"], "in_progress")
        self.assertEqual(row["holder"], deploy)  # 04 L51: entering in_progress writes holder
        self.assertFalse(row.get("adopted"))  # plain start, not an adoption (04 L63)

    def test_row_amend_todo_stuck(self):
        """todo/stuck -> same, owner or to_role add report_paths/code_paths (04 L64)."""
        sb = self.sb
        idea, ho_id = _new_work_order(sb)
        deploy = _deploy(sb)
        sb.write_file("experiments/wo1/method.md", "# method\n")
        sb.write_file("experiments/wo1/x.py", "print(1)\n")
        sb.rl_ok("handoff", "amend", ho_id, "--report-method", "experiments/wo1/method.md",
                 "--code-path", "experiments/wo1/x.py", session=deploy)
        row = sb.latest("handoffs", ho_id)
        self.assertEqual(row["status"], "todo")  # 04 L80: content-only, status unchanged
        self.assertEqual(row["report_paths"]["method"], "experiments/wo1/method.md")
        self.assertIn("experiments/wo1/x.py", row["code_paths"])

    def test_row_estimate(self):
        """in_progress -> same, only holder (run) touches step_table/estimated_seconds (04 L65)."""
        sb = self.sb
        idea, wo_id = _new_work_order(sb)
        deploy = _deploy(sb)
        lo_id = open_launch_order(sb, deploy, wo_id)
        run = _run(sb)
        sb.rl_ok("handoff", "start", lo_id, session=run)
        sb.rl_ok("handoff", "estimate", lo_id, "--step", "train", "--kind", "gpu",
                 "--smoke-seconds", "30", "--scale", "10", session=run)
        row = sb.latest("handoffs", lo_id)
        self.assertEqual(row["status"], "in_progress")  # 04 L65: status unchanged
        self.assertEqual(row["holder"], run)
        steps = row["attempts"][-1]["step_table"]
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["step"], "train")
        self.assertGreater(row["attempts"][-1]["estimated_seconds"], 0)

    def test_row_stuck(self):
        """in_progress -> stuck, holder writes, issue must point back (04 L66)."""
        sb = self.sb
        idea, ho_id = _new_work_order(sb)
        deploy = _deploy(sb)
        sb.rl_ok("handoff", "start", ho_id, session=deploy)
        iss_id = _open_issue_against(sb, deploy, ho_id)
        sb.rl_ok("handoff", "stuck", ho_id, "--issue", iss_id, session=deploy)
        row = sb.latest("handoffs", ho_id)
        self.assertEqual(row["status"], "stuck")
        self.assertEqual(row["issue_id"], iss_id)
        self.assertIsNone(row["holder"])  # 04 L51: leaving in_progress clears holder
        self.assertEqual(row["last_holder"], deploy)

    def test_row_resume(self):
        """stuck -> todo, who=issue_answerer or owner, needs issue answered (04 L67)."""
        sb = self.sb
        idea, ho_id = _new_work_order(sb)
        deploy = _deploy(sb)
        sb.rl_ok("handoff", "start", ho_id, session=deploy)
        iss_id = _open_issue_against(sb, deploy, ho_id)
        sb.rl_ok("handoff", "stuck", ho_id, "--issue", iss_id, session=deploy)
        sb.rl_ok("issue", "reply", iss_id, "--text", "use lr 1e-4", session=idea)
        sb.rl_ok("handoff", "resume", ho_id, session=idea)  # idea is owner (04 L67)
        row = sb.latest("handoffs", ho_id)
        self.assertEqual(row["status"], "todo")
        self.assertIsNone(row["holder"])

    def test_row_done_work_order(self):
        """in_progress -> done_pending_review, needs report_paths+code_paths (04 L68)."""
        sb = self.sb
        idea, ho_id = _new_work_order(sb)
        deploy = _deploy(sb)
        sb.write_file("experiments/wo2/method.md", "# method\n")
        sb.write_file("experiments/wo2/detail.md", "# detail\n")
        sb.rl_ok("handoff", "amend", ho_id, "--report-method", "experiments/wo2/method.md",
                 "--report-detail", "experiments/wo2/detail.md", "--code-path", "experiments/wo2/x.py",
                 session=deploy)
        sb.rl_ok("handoff", "start", ho_id, session=deploy)
        sb.rl_ok("handoff", "done", ho_id, session=deploy)
        row = sb.latest("handoffs", ho_id)
        self.assertEqual(row["status"], "done_pending_review")
        self.assertIsNone(row["holder"])  # 04 L51: leaving in_progress clears holder
        self.assertEqual(row["last_holder"], deploy)

    def test_row_amend_done_pending_review(self):
        """done_pending_review -> same, owner/to_role fix a path (04 L69)."""
        sb = self.sb
        idea, ho_id = _new_work_order(sb)
        deploy = _deploy(sb)
        sb.write_file("experiments/wo3/method.md", "# method\n")
        sb.write_file("experiments/wo3/detail.md", "# detail v1\n")
        sb.rl_ok("handoff", "amend", ho_id, "--report-method", "experiments/wo3/method.md",
                 "--report-detail", "experiments/wo3/detail.md", "--code-path", "experiments/wo3/x.py",
                 session=deploy)
        sb.rl_ok("handoff", "start", ho_id, session=deploy)
        sb.rl_ok("handoff", "done", ho_id, session=deploy)
        sb.write_file("experiments/wo3/detail-v2.md", "# detail v2\n")
        sb.rl_ok("handoff", "amend", ho_id, "--report-detail", "experiments/wo3/detail-v2.md", session=deploy)
        row = sb.latest("handoffs", ho_id)
        self.assertEqual(row["status"], "done_pending_review")  # 04 L80: status unchanged
        self.assertEqual(row["report_paths"]["detail"], "experiments/wo3/detail-v2.md")

    def _to_done_pending_review(self, tag):
        sb = self.sb
        idea, ho_id = _new_work_order(sb)
        deploy = _deploy(sb)
        sb.write_file(f"experiments/{tag}/method.md", "# method\n")
        sb.write_file(f"experiments/{tag}/detail.md", "# detail\n")
        sb.rl_ok("handoff", "amend", ho_id, "--report-method", f"experiments/{tag}/method.md",
                 "--report-detail", f"experiments/{tag}/detail.md", "--code-path", f"experiments/{tag}/x.py",
                 session=deploy)
        sb.rl_ok("handoff", "start", ho_id, session=deploy)
        sb.rl_ok("handoff", "done", ho_id, session=deploy)
        return idea, deploy, ho_id

    def test_row_accept(self):
        """done_pending_review -> accepted, who=owner (04 L70)."""
        sb = self.sb
        idea, deploy, ho_id = self._to_done_pending_review("wo4")
        sb.rl_ok("handoff", "accept", ho_id, session=idea)  # idea is owner
        row = sb.latest("handoffs", ho_id)
        self.assertEqual(row["status"], "accepted")

    def test_row_reject(self):
        """done_pending_review -> rejected, who=owner, reason required (04 L71)."""
        sb = self.sb
        idea, deploy, ho_id = self._to_done_pending_review("wo5")
        sb.rl_ok("handoff", "reject", ho_id, "--reason", "not convincing", session=idea)
        row = sb.latest("handoffs", ho_id)
        self.assertEqual(row["status"], "rejected")
        self.assertEqual(row["reason"], "not convincing")

    def test_row_release_rejected(self):
        """rejected -> todo, who=owner/reclaim, no progress_note required (04 L72)."""
        sb = self.sb
        idea, deploy, ho_id = self._to_done_pending_review("wo6")
        sb.rl_ok("handoff", "reject", ho_id, "--reason", "not convincing", session=idea)
        sb.rl_ok("handoff", "release", ho_id, session=idea)  # 04 L39: no --note needed here
        row = sb.latest("handoffs", ho_id)
        self.assertEqual(row["status"], "todo")

    def test_row_restart_rejected(self):
        """rejected -> in_progress, who=to_role, original session continues (04 L73).

        This is a direct rejected->in_progress start, distinct from release_rejected
        (04 L72, rejected->todo): holder is already empty after reject, so `handoff start`
        applies straight away without going through todo.
        """
        sb = self.sb
        idea, deploy, ho_id = self._to_done_pending_review("wo7")
        sb.rl_ok("handoff", "reject", ho_id, "--reason", "not convincing", session=idea)
        sb.rl_ok("handoff", "start", ho_id, session=deploy)  # same deploy session restarts
        row = sb.latest("handoffs", ho_id)
        self.assertEqual(row["status"], "in_progress")
        self.assertEqual(row["holder"], deploy)

    def test_row_withdraw(self):
        """todo -> withdrawn, who=owner, reason (+quote from a role session) (04 L74)."""
        sb = self.sb
        idea, ho_id = _new_work_order(sb)
        sb.rl_ok("handoff", "withdraw", ho_id, "--reason", "no longer needed",
                 "--quote", "gyb said drop it", session=idea)  # role session needs --quote (04 L74)
        row = sb.latest("handoffs", ho_id)
        self.assertEqual(row["status"], "withdrawn")
        self.assertEqual(row["reason"], "no longer needed")

    def test_row_release_in_progress(self):
        """in_progress -> todo, owner/hook/reclaim, progress_note required (04 L75)."""
        sb = self.sb
        idea, ho_id = _new_work_order(sb)
        deploy = _deploy(sb)
        sb.rl_ok("handoff", "start", ho_id, session=deploy)
        sb.rl_ok("handoff", "release", ho_id, "--note", "deploy went quiet", session=idea)  # owner
        row = sb.latest("handoffs", ho_id)
        self.assertEqual(row["status"], "todo")
        self.assertIsNone(row["holder"])
        self.assertEqual(row["last_holder"], deploy)
        self.assertEqual(row["progress_note"], "deploy went quiet")

    def test_row_reissue_cascades_and_supersedes(self):
        """Any non-terminal -> old withdrawn (cascading), new todo, supersedes old (04 L76)."""
        sb = self.sb
        idea, old_wo = _new_work_order(sb)
        deploy = _deploy(sb)
        old_lo = open_launch_order(sb, deploy, old_wo)  # parent_id == old_wo
        dec2 = make_decision(sb, session=idea, text="try lr 3e-4")
        r = sb.rl_ok("handoff", "reissue", old_wo, "--decision", f"{dec2}@1", "--json", session=idea)
        new_wo = r.json["id"]
        old_row = sb.latest("handoffs", old_wo)
        self.assertEqual(old_row["status"], "withdrawn")
        new_row = sb.latest("handoffs", new_wo)
        self.assertEqual(new_row["status"], "todo")
        self.assertEqual(new_row["supersedes"], old_wo)
        # 04 L76 side effect: rl withdraws the old order cascading (04 L74's --cascade
        # behaviour, automatic here); the child launch_order goes too.
        cascaded_lo = sb.latest("handoffs", old_lo)
        self.assertEqual(cascaded_lo["status"], "withdrawn")
        self.assertEqual(cascaded_lo["actor"], "idea")  # 04 L74: downstream actor = initiator

    def test_row_ql_transfer_in(self):
        """todo -> same, marks quick_lane and leaves the todo queue (07 L31; sync-inbox Q41(c))."""
        sb = self.sb
        idea, ho_id = _new_work_order(sb)
        deploy = _deploy(sb)
        sb.rl_ok("ql", "open", "--role", "deploy", "--from", ho_id, "--json", session=deploy)
        row = sb.latest("handoffs", ho_id)
        self.assertEqual(row["status"], "todo")  # 07 L31: transfer keeps status todo
        self.assertTrue(row["quick_lane"])
        self.assertIsNone(row["holder"])  # 07 L31: takes no holder

    def test_row_ql_transfer_exit(self):
        """PENDING(issue 41f): merge-back/abandon exit of a --from-transferred quick-lane
        order has no sub-command name yet (tables/transitions.json 'ql_transfer_exit';
        07 L114; sync-inbox Q41(c)(f) L294-295)."""
        self.skipTest("PENDING(issue 41f): no sub-command name yet for the merge-back/abandon "
                      "exit of a quick-lane order transferred in with `ql open --from` (07 L114)")


class TestIllegalTransitions(unittest.TestCase):
    """Three illegal transition cases, all exit 2, no new row (30 L39-41)."""

    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_cross_state_refused(self):
        """accept on a todo order: no row in the table for from=todo (04 L55; 03 L228)."""
        sb = self.sb
        idea, ho_id = _new_work_order(sb)
        before = sb.count("handoffs")
        r = sb.rl("handoff", "accept", ho_id, session=idea)
        self.assertEqual(r.rc, 2)
        self.assertEqual(r.kind, "validation")
        self.assertEqual(sb.count("handoffs"), before)

    def test_wrong_role_refused(self):
        """analysis tries to start a work_order addressed to deploy (04 L63: session role
        must equal to_role; 30 L39-41: wrong-role is exit 2 same as the other two)."""
        sb = self.sb
        idea, ho_id = _new_work_order(sb)
        analysis = _analysis(sb)
        before = sb.count("handoffs")
        r = sb.rl("handoff", "start", ho_id, session=analysis)
        self.assertEqual(r.rc, 2)
        self.assertEqual(r.kind, "validation")
        self.assertEqual(sb.count("handoffs"), before)

    def test_missing_precondition_refused(self):
        """resume before the linked issue is answered (04 L67: precondition is issue answered)."""
        sb = self.sb
        idea, ho_id = _new_work_order(sb)
        deploy = _deploy(sb)
        sb.rl_ok("handoff", "start", ho_id, session=deploy)
        iss_id = _open_issue_against(sb, deploy, ho_id)
        sb.rl_ok("handoff", "stuck", ho_id, "--issue", iss_id, session=deploy)
        before = sb.count("handoffs")
        r = sb.rl("handoff", "resume", ho_id, session=idea)  # issue still open, not answered
        self.assertEqual(r.rc, 2)
        self.assertEqual(r.kind, "validation")
        self.assertEqual(sb.count("handoffs"), before)

    def test_out_of_table_transition_refused_for_gyb_even_with_force(self):
        """gyb --force --reason cannot cross a transition outside the table (04 L55, L57;
        03 L228; 05, the actor-resolution section: --force only bypasses integrity
        preconditions, never an out-of-table transition)."""
        sb = self.sb
        idea, ho_id = _new_work_order(sb)  # still todo
        before = sb.count("handoffs")
        r = sb.rl("handoff", "accept", ho_id, "--force", "--reason", "gyb wants it now")  # bare terminal = gyb
        self.assertEqual(r.rc, 2)
        self.assertEqual(r.kind, "validation")
        self.assertEqual(sb.count("handoffs"), before)


class TestHolderInvariant(unittest.TestCase):
    """holder non-empty iff in_progress; written on entry, cleared with last_holder kept
    on every exit, including done_pending_review (04 L51; 30 L45)."""

    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_start_refused_when_holder_nonempty(self):
        """04 L63: start requires holder empty; a second start is exit 2, holder unaffected."""
        sb = self.sb
        idea, ho_id = _new_work_order(sb)
        deploy1 = _deploy(sb)
        sb.rl_ok("handoff", "start", ho_id, session=deploy1)
        deploy2 = sb.role_session("deploy")
        before = sb.count("handoffs")
        r = sb.rl("handoff", "start", ho_id, session=deploy2)
        self.assertEqual(r.rc, 2)
        self.assertEqual(r.kind, "validation")
        self.assertEqual(sb.count("handoffs"), before)
        row = sb.latest("handoffs", ho_id)
        self.assertEqual(row["holder"], deploy1)  # unaffected by the refused second start

    def test_holder_cleared_on_every_exit_from_in_progress(self):
        """04 L51: every exit from in_progress clears holder into last_holder; 30 L45 flags
        done_pending_review as the case earlier drafts missed. Each of the four exits is
        wrapped in its own subTest so one failure does not hide the other three."""
        sb = self.sb

        with self.subTest(exit="done"):
            # exit via done (-> done_pending_review)
            idea, ho_id = _new_work_order(sb)
            deploy = _deploy(sb)
            sb.write_file("experiments/hi1/method.md", "# method\n")
            sb.write_file("experiments/hi1/detail.md", "# detail\n")
            sb.rl_ok("handoff", "amend", ho_id, "--report-method", "experiments/hi1/method.md",
                     "--report-detail", "experiments/hi1/detail.md", "--code-path", "experiments/hi1/x.py",
                     session=deploy)
            sb.rl_ok("handoff", "start", ho_id, session=deploy)
            sb.rl_ok("handoff", "done", ho_id, session=deploy)
            row = sb.latest("handoffs", ho_id)
            self.assertIsNone(row["holder"], "done_pending_review must have an empty holder (30 L45)")
            self.assertEqual(row["last_holder"], deploy)

        with self.subTest(exit="stuck"):
            # exit via stuck (-> stuck)
            idea2, ho_id2 = _new_work_order(sb)
            deploy2 = _deploy(sb)
            sb.rl_ok("handoff", "start", ho_id2, session=deploy2)
            iss = _open_issue_against(sb, deploy2, ho_id2)
            sb.rl_ok("handoff", "stuck", ho_id2, "--issue", iss, session=deploy2)
            row2 = sb.latest("handoffs", ho_id2)
            self.assertIsNone(row2["holder"])
            self.assertEqual(row2["last_holder"], deploy2)

        with self.subTest(exit="withdraw"):
            # exit via withdraw (-> withdrawn)
            idea3, ho_id3 = _new_work_order(sb)
            deploy3 = _deploy(sb)
            sb.rl_ok("handoff", "start", ho_id3, session=deploy3)
            sb.rl_ok("handoff", "withdraw", ho_id3, "--reason", "stop", "--quote", "gyb: stop", session=idea3)
            row3 = sb.latest("handoffs", ho_id3)
            self.assertIsNone(row3["holder"])
            self.assertEqual(row3["last_holder"], deploy3)

        with self.subTest(exit="release"):
            # exit via release (-> todo)
            idea4, ho_id4 = _new_work_order(sb)
            deploy4 = _deploy(sb)
            sb.rl_ok("handoff", "start", ho_id4, session=deploy4)
            sb.rl_ok("handoff", "release", ho_id4, "--note", "quiet", session=idea4)
            row4 = sb.latest("handoffs", ho_id4)
            self.assertIsNone(row4["holder"])
            self.assertEqual(row4["last_holder"], deploy4)


class TestAdoption(unittest.TestCase):
    """start.adopt_if_launched_unfinished: a launch_order whose latest attempt already has
    a launched-but-unfinished run row is adopted, not restarted (04 L54, L63, L98; 03 L100)."""

    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_start_adopts_a_launched_unfinished_run(self):
        sb = self.sb
        idea, wo_id = _new_work_order(sb)
        deploy = _deploy(sb)
        lo_id = open_launch_order(sb, deploy, wo_id)
        run_a = _run(sb)
        sb.rl_ok("handoff", "start", lo_id, session=run_a)
        run_id = sb.latest("handoffs", lo_id)["attempts"][0]["run_id"]
        sb.rl_ok("run", "add", "--handoff", lo_id, "--attempt", "1", "--commit", "deadbeef",
                 "--host", "h1", "--gpus", "0", "--log", "/tmp/l.log", "--tmux", "t1",
                 "--watch-cmd", "tail -f /tmp/l.log", session=run_a)
        # run_a crashes without finishing; the owner releases it back to todo (04 L75: a
        # launch_order with a launched-unfinished run is not killed, the next run adopts it)
        sb.rl_ok("handoff", "release", lo_id, "--note", "run session died", session=deploy)
        run_b = sb.role_session("run")
        sb.rl_ok("handoff", "start", lo_id, session=run_b)
        row = sb.latest("handoffs", lo_id)
        self.assertEqual(row["status"], "in_progress")
        self.assertEqual(row["holder"], run_b)
        self.assertTrue(row["adopted"])  # 04 L63: this version writes adopted: true
        run_row = sb.latest("runs", run_id)
        self.assertEqual(run_row["status"], "adopted")  # 03 L100: rl appends an adopted version


if __name__ == "__main__":
    unittest.main()
