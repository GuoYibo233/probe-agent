"""Test 4: deliverables (30 L58-62).

work_order missing any report path or code_paths is refused at done (04 L68, L35-36); the
quick-lane supplement needs only a method report, not a detail one (04 L62 vs L68; 07
L98-99); analysis_order gates on notebook presence and evaluation approval (04 L61, L68,
L33, L37); launch_order needs a finished-ok run for its latest attempt (04 L68); a
quick-lane work order goes straight to done_pending_review and only gyb can accept it (04
L62, L70; 07 L97); the scratch row must still be open when the supplement is opened, and
the order is open-supplement-then-close (04 L62; 07 L88, L109); the supplement carries
ql_tag, other orders leave it empty (04 L31, L44); `rl handoff done` takes no
--actual-seconds (04 L43; 30 L62).
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


def _open_quick_lane_supplement(sb, deploy, ql, tag="x"):
    """Opens a quick-lane supplement work_order for scratch tag `ql` (04 L62; 07 L109)."""
    sb.write_file(f"experiments/{ql}/method.md", "# method\n")
    return sb.rl("handoff", "open", "--type", "work_order", "--to", "deploy", "--quick-lane",
                 "--report-method", f"experiments/{ql}/method.md", "--ql", ql,
                 "--explain", "gyb said: just try it", "--code-path", f"experiments/{tag}.py",
                 "--track", "probe", "--json", session=deploy)


class TestWorkOrderDeliverables(unittest.TestCase):
    """work_order missing any report path or code_paths is refused at done
    (30 L60; 04 L68, L35-36)."""

    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_missing_method_refused(self):
        sb = self.sb
        idea, ho_id = _new_work_order(sb)
        deploy = _deploy(sb)
        sb.write_file("experiments/m1/detail.md", "# detail\n")
        sb.rl_ok("handoff", "amend", ho_id, "--report-detail", "experiments/m1/detail.md",
                 "--code-path", "experiments/m1/x.py", session=deploy)
        sb.rl_ok("handoff", "start", ho_id, session=deploy)
        before = sb.count("handoffs")
        r = sb.rl("handoff", "done", ho_id, session=deploy)
        self.assertEqual(r.rc, 2)
        self.assertEqual(sb.count("handoffs"), before)

    def test_missing_detail_refused(self):
        sb = self.sb
        idea, ho_id = _new_work_order(sb)
        deploy = _deploy(sb)
        sb.write_file("experiments/m2/method.md", "# method\n")
        sb.rl_ok("handoff", "amend", ho_id, "--report-method", "experiments/m2/method.md",
                 "--code-path", "experiments/m2/x.py", session=deploy)
        sb.rl_ok("handoff", "start", ho_id, session=deploy)
        before = sb.count("handoffs")
        r = sb.rl("handoff", "done", ho_id, session=deploy)
        self.assertEqual(r.rc, 2)
        self.assertEqual(sb.count("handoffs"), before)

    def test_missing_code_paths_refused(self):
        sb = self.sb
        idea, ho_id = _new_work_order(sb)
        deploy = _deploy(sb)
        sb.write_file("experiments/m3/method.md", "# method\n")
        sb.write_file("experiments/m3/detail.md", "# detail\n")
        sb.rl_ok("handoff", "amend", ho_id, "--report-method", "experiments/m3/method.md",
                 "--report-detail", "experiments/m3/detail.md", session=deploy)
        sb.rl_ok("handoff", "start", ho_id, session=deploy)
        before = sb.count("handoffs")
        r = sb.rl("handoff", "done", ho_id, session=deploy)
        self.assertEqual(r.rc, 2)
        self.assertEqual(sb.count("handoffs"), before)


class TestQuickLaneSupplementDeliverables(unittest.TestCase):
    """The quick-lane supplement's own precondition list has no report_paths.detail
    requirement, unlike a normal work_order (04 L62 vs L68; 07 L98-99; 30 L60)."""

    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_supplement_needs_only_method_not_detail(self):
        sb = self.sb
        deploy = _deploy(sb)
        ql = sb.rl_ok("ql", "open", "--role", "deploy", "--json", session=deploy).json["ql_tag"]
        r = _open_quick_lane_supplement(sb, deploy, ql)
        self.assertEqual(r.rc, 0, f"quick-lane supplement open failed:\n{r}")
        row = sb.latest("handoffs", r.json["id"])
        self.assertEqual(row["status"], "done_pending_review")
        self.assertNotIn("detail", row.get("report_paths", {}))  # no detail required for quick lane


class TestAnalysisOrderDeliverables(unittest.TestCase):
    """analysis_order missing notebook refused; opening with a proposed evaluation passes;
    done with a still-proposed evaluation refused (30 L60; 04 L61, L68, L33, L37).

    UNDECIDED: whether an analysis_order needs decision_refs or explanation at open is
    PENDING(part 22 L113) and PENDING(part 22 L114) in tables/transitions.json's 'open'
    row _pending list; this fixture opens one without either, which is not itself under
    test here (only the notebook/evaluation gating is).
    """

    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_open_with_proposed_evaluation_then_done_gates_on_approval_and_notebook(self):
        sb = self.sb
        analysis = _analysis(sb)
        eval_id = sb.rl_ok("eval", "propose", "--kind", "metric", "--name", "accuracy",
                           "--definition", "top-1 accuracy", "--metrics-key", "acc",
                           "--applies-to", "track probe, model m, dataset d, split s",
                           "--json", session=analysis).json["id"]
        eval_row = sb.latest("evaluations", eval_id)
        self.assertEqual(eval_row["status"], "proposed")

        idea = _idea(sb)
        ao_id = sb.rl_ok("handoff", "open", "--type", "analysis_order", "--to", "analysis",
                         "--eval", f"{eval_id}@1", "--json", session=idea).json["id"]
        # 04 L61 / open.analysis_order_has_eval_refs: opening with a still-proposed
        # evaluation is allowed.
        row = sb.latest("handoffs", ao_id)
        self.assertEqual(row["status"], "todo")

        sb.rl_ok("handoff", "start", ao_id, session=analysis)

        # missing notebook
        before = sb.count("handoffs")
        r = sb.rl("handoff", "done", ao_id, session=analysis)
        self.assertEqual(r.rc, 2)
        self.assertEqual(sb.count("handoffs"), before)

        # notebook present but the evaluation is still proposed, not approved
        sb.write_file("analysis/ao1/nb.ipynb", "{}")
        before = sb.count("handoffs")
        r = sb.rl("handoff", "done", ao_id, "--notebook", "analysis/ao1/nb.ipynb", session=analysis)
        self.assertEqual(r.rc, 2)
        self.assertEqual(sb.count("handoffs"), before)

        # gyb approves the evaluation (03 ledgers: approved/rejected/retired versions are gyb's)
        sb.rl_ok("eval", "approve", eval_id, "--quote", "gyb: looks right", session=None)
        self.assertEqual(sb.latest("evaluations", eval_id)["status"], "approved")

        sb.rl_ok("handoff", "done", ao_id, "--notebook", "analysis/ao1/nb.ipynb", session=analysis)
        row = sb.latest("handoffs", ao_id)
        self.assertEqual(row["status"], "done_pending_review")


class TestLaunchOrderDeliverables(unittest.TestCase):
    """launch_order without a finished ok run for the latest attempt is refused at done
    (30 L60; 04 L68)."""

    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_done_refused_without_a_finished_ok_run(self):
        sb = self.sb
        idea, wo_id = _new_work_order(sb)
        deploy = _deploy(sb)
        lo_id = open_launch_order(sb, deploy, wo_id)
        run = _run(sb)
        sb.rl_ok("handoff", "start", lo_id, session=run)
        before = sb.count("handoffs")
        r = sb.rl("handoff", "done", lo_id, session=run)
        self.assertEqual(r.rc, 2)
        self.assertEqual(sb.count("handoffs"), before)


class TestQuickLaneAcceptance(unittest.TestCase):
    """A quick-lane work order goes straight to done_pending_review and only gyb can
    accept it (30 L60; 04 L62, L70 who_note; 07 L97)."""

    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_only_gyb_can_accept_the_supplement(self):
        sb = self.sb
        deploy = _deploy(sb)
        ql = sb.rl_ok("ql", "open", "--role", "deploy", "--json", session=deploy).json["ql_tag"]
        r0 = _open_quick_lane_supplement(sb, deploy, ql)
        self.assertEqual(r0.rc, 0, f"quick-lane supplement open failed:\n{r0}")
        ho_id = r0.json["id"]
        before = sb.count("handoffs")
        r = sb.rl("handoff", "accept", ho_id, session=deploy)  # deploy is not gyb
        self.assertEqual(r.rc, 2)
        self.assertEqual(sb.count("handoffs"), before)
        sb.rl_ok("handoff", "accept", ho_id, session=None)  # bare terminal = gyb
        row = sb.latest("handoffs", ho_id)
        self.assertEqual(row["status"], "accepted")


class TestQuickLaneCloseOrdering(unittest.TestCase):
    """Merge-back order: open the supplement first, then rl ql close --merged --handoff
    ID; the supplement's own precondition requires the scratch row to be open, not merged
    or dropped (30 L62; 04 L62; 07 L88, L109; sync-inbox Q8 L294)."""

    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_open_then_close_updates_both_rows(self):
        sb = self.sb
        deploy = _deploy(sb)
        ql = sb.rl_ok("ql", "open", "--role", "deploy", "--json", session=deploy).json["ql_tag"]
        r0 = _open_quick_lane_supplement(sb, deploy, ql)
        self.assertEqual(r0.rc, 0, f"quick-lane supplement open failed:\n{r0}")
        ho_id = r0.json["id"]
        sb.rl_ok("ql", "close", ql, "--merged", "--handoff", ho_id, session=deploy)
        scratch_row = sb.latest("scratch", ql)
        self.assertEqual(scratch_row["status"], "merged")
        self.assertEqual(scratch_row["handoff_id"], ho_id)
        ho_row = sb.latest("handoffs", ho_id)
        self.assertEqual(ho_row["ql_tag"], ql)  # 04 L31: the two point at each other

    def test_supplement_open_refused_when_scratch_row_is_not_open(self):
        sb = self.sb
        deploy = _deploy(sb)
        ql = sb.rl_ok("ql", "open", "--role", "deploy", "--json", session=deploy).json["ql_tag"]
        sb.rl_ok("ql", "close", ql, "--dropped", "--reason", "abandoned", session=deploy)
        self.assertEqual(sb.latest("scratch", ql)["status"], "dropped")
        before_h = sb.count("handoffs")
        r = _open_quick_lane_supplement(sb, deploy, ql)
        self.assertEqual(r.rc, 2)  # ql.scratch_row_open precondition fails: status is dropped
        self.assertEqual(sb.count("handoffs"), before_h)


class TestQlTagField(unittest.TestCase):
    """ql_tag is required and non-empty on a quick-lane supplement, empty on every other
    order (30 L62; 04 L31, L44 handoffs field table)."""

    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_ql_tag_set_on_supplement_empty_elsewhere(self):
        sb = self.sb
        idea, plain_wo = _new_work_order(sb)
        plain_row = sb.latest("handoffs", plain_wo)
        self.assertFalse(plain_row.get("ql_tag"))

        deploy = _deploy(sb)
        ql = sb.rl_ok("ql", "open", "--role", "deploy", "--json", session=deploy).json["ql_tag"]
        r0 = _open_quick_lane_supplement(sb, deploy, ql)
        self.assertEqual(r0.rc, 0, f"quick-lane supplement open failed:\n{r0}")
        supp_row = sb.latest("handoffs", r0.json["id"])
        self.assertEqual(supp_row["ql_tag"], ql)


class TestHandoffDoneUsage(unittest.TestCase):
    """`rl handoff done` has no --actual-seconds flag: actual_seconds only ever comes from
    `rl run finish` (30 L62; 04 L43 'handoff done 不带 --actual-seconds'; exit 5 usage)."""

    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_actual_seconds_flag_is_usage_error(self):
        sb = self.sb
        idea, ho_id = _new_work_order(sb)
        deploy = _deploy(sb)
        sb.write_file("experiments/das1/method.md", "# method\n")
        sb.write_file("experiments/das1/detail.md", "# detail\n")
        sb.rl_ok("handoff", "amend", ho_id, "--report-method", "experiments/das1/method.md",
                 "--report-detail", "experiments/das1/detail.md", "--code-path", "experiments/das1/x.py",
                 session=deploy)
        sb.rl_ok("handoff", "start", ho_id, session=deploy)
        before = sb.count("handoffs")
        r = sb.rl("handoff", "done", ho_id, "--actual-seconds", "100", session=deploy)
        self.assertEqual(r.rc, 5)
        self.assertEqual(r.kind, "usage")
        self.assertEqual(sb.count("handoffs"), before)


if __name__ == "__main__":
    unittest.main()
