"""Test 16: quick lane (30 L156-165).

Original (30 L158): `ql open` assigns a tag and builds the worktree (deploy) or the
scratch dir (analysis); `ql close --merged` requires the handoff to exist; `--dropped`
requires a reason; `rl status` only lists the quick lanes that are not closed.

Changed (30 L160-165; 07 section 7; tables/commands.json):
- The merge-back order is: `rl handoff open --quick-lane --report-method P --ql QL`
  first (getting the supplement's handoff id), then `rl ql close QL --merged --handoff
  ID`; `ql close --merged`'s precondition is that ID is a quick_lane supplement whose
  `ql_tag` equals QL.
- `ql close --merged` only works for deploy; analysis's quick lane has no supplement, only
  `--dropped`.
- `ql open --role analysis` does not build a worktree, it builds
  `analysis/scratch/<ql_tag>/`; the open version fills `dir`.
- Middle versions that append numbers to scratch keep `status` open; `open`, `merged`,
  `dropped` are checked against the field table, middle versions only against the
  skeleton and `ql_tag` (03 L211).

This file does not repeat what test_04_deliverables.py's TestQuickLaneSupplementDeliverables
and TestQuickLaneCloseOrdering already cover (the supplement's own precondition list, the
open-then-close ordering, ql_tag linkage) -- it covers ql open's own side effects
(worktree/branch vs scratch dir), ql close's negative paths, worktree/branch removal on
both close paths, scratch add's middle-version behaviour, and the status-listing clause.
"""

import json
import unittest
from pathlib import Path

from helpers import Sandbox, make_decision, open_work_order


def _idea(sb):
    return sb.role_session("idea")


def _deploy(sb):
    return sb.role_session("deploy")


def _analysis(sb):
    return sb.role_session("analysis")


def _new_work_order(sb, to_role="deploy"):
    """(idea_session, ho_id): a fresh plain work_order at todo (04 L61)."""
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


def _worktree_path(sb, ql):
    cfg = json.loads((sb.root / "research-loop.json").read_text())
    return Path(cfg["quick_lane.worktree_root"]) / ql


class TestQlOpen(unittest.TestCase):
    """`ql open` assigns a tag inside the lock and builds the worktree/branch (deploy)
    or the scratch dir (analysis); the open row's required fields differ by role (07
    L23-31; schemas/scratch.schema.json x-conditions; sync-inbox Q41(a))."""

    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_open_deploy_assigns_tag_and_creates_worktree_and_branch(self):
        sb = self.sb
        deploy = _deploy(sb)
        r = sb.rl_ok("ql", "open", "--role", "deploy", "--json", session=deploy)
        ql = r.json["ql_tag"]
        self.assertRegex(ql, r"^ql-[0-9]{8}-[0-9]{2,}$")  # scratch.schema.json ql_tag pattern

        row = sb.latest("scratch", ql)
        self.assertEqual(row["status"], "open")
        self.assertEqual(row["role"], "deploy")
        self.assertTrue(row["worktree"])
        self.assertTrue(row["base_commit"])
        self.assertTrue(row["branch"])

        wt = _worktree_path(sb, ql)
        self.assertTrue(wt.is_dir(), "ql open --role deploy must create the worktree directory")
        self.assertIn(ql, sb.git("branch", "--list", ql).stdout)
        self.assertIn(str(wt), sb.git("worktree", "list").stdout)

    def test_open_analysis_creates_scratch_dir_with_dir_field_only(self):
        sb = self.sb
        analysis = _analysis(sb)
        r = sb.rl_ok("ql", "open", "--role", "analysis", "--json", session=analysis)
        ql = r.json["ql_tag"]

        row = sb.latest("scratch", ql)
        self.assertEqual(row["status"], "open")
        self.assertEqual(row["role"], "analysis")
        self.assertTrue(row["dir"])
        self.assertFalse(row.get("base_commit"))  # not set for analysis (07 L70)
        self.assertFalse(row.get("branch"))  # not set for analysis (07 L70)

        d = sb.root / "analysis" / "scratch" / ql
        self.assertTrue(d.is_dir(), "ql open --role analysis must create analysis/scratch/<ql_tag>/")
        self.assertNotIn(ql, sb.git("branch", "--list", ql).stdout)  # no branch built for analysis


class TestQlOpenFrom(unittest.TestCase):
    """`ql open --from ho-ID` transfers a todo work order into the quick lane: the order
    is marked quick_lane, takes the new ql_tag, leaves the todo queue and takes no
    holder (07 L31; sync-inbox Q41(c); tables/transitions.json ql_transfer_in)."""

    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_open_from_marks_quick_lane_ql_tag_and_no_holder(self):
        sb = self.sb
        idea, ho_id = _new_work_order(sb)
        deploy = _deploy(sb)
        r = sb.rl_ok("ql", "open", "--role", "deploy", "--from", ho_id, "--json", session=deploy)
        ql = r.json["ql_tag"]

        row = sb.latest("handoffs", ho_id)
        self.assertEqual(row["status"], "todo")  # 07 L31: transfer keeps status todo
        self.assertTrue(row["quick_lane"])
        self.assertIsNone(row["holder"])  # 07 L31: takes no holder
        # whether a transferred order carries ql_tag is PENDING(issue 41f) (04 L31 rules only the supplement); not asserted


class TestQlCloseMergedValidation(unittest.TestCase):
    """`ql close --merged` requires ID to be a quick_lane supplement whose ql_tag
    equals QL (05 L87); refused otherwise, with no change to the scratch row."""

    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_merged_refused_when_handoff_does_not_match_ql_tag(self):
        sb = self.sb
        deploy = _deploy(sb)
        ql1 = sb.rl_ok("ql", "open", "--role", "deploy", "--json", session=deploy).json["ql_tag"]
        supp1 = _open_quick_lane_supplement(sb, deploy, ql1)
        self.assertEqual(supp1.rc, 0, f"quick-lane supplement open failed:\n{supp1}")
        ho1 = supp1.json["id"]
        ql2 = sb.rl_ok("ql", "open", "--role", "deploy", "--json", session=deploy).json["ql_tag"]

        with self.subTest(case="ql_tag_mismatch"):
            before = sb.count("scratch")
            r = sb.rl("ql", "close", ql2, "--merged", "--handoff", ho1, session=deploy)
            self.assertEqual(r.rc, 2, str(r))
            self.assertEqual(r.kind, "validation")
            self.assertEqual(sb.count("scratch"), before)
            self.assertEqual(sb.latest("scratch", ql2)["status"], "open")

        with self.subTest(case="not_a_quick_lane_supplement"):
            idea, plain_wo = _new_work_order(sb)
            before = sb.count("scratch")
            r = sb.rl("ql", "close", ql1, "--merged", "--handoff", plain_wo, session=deploy)
            self.assertEqual(r.rc, 2, str(r))
            self.assertEqual(r.kind, "validation")
            self.assertEqual(sb.count("scratch"), before)
            self.assertEqual(sb.latest("scratch", ql1)["status"], "open")

    def test_analysis_cannot_merge(self):
        """--merged only works for deploy (07 L86); analysis's quick lane only has
        --dropped."""
        sb = self.sb
        analysis = _analysis(sb)
        ql = sb.rl_ok("ql", "open", "--role", "analysis", "--json", session=analysis).json["ql_tag"]
        before = sb.count("scratch")
        r = sb.rl("ql", "close", ql, "--merged", "--handoff", "ho-0001", session=analysis)
        self.assertEqual(r.rc, 3, str(r))
        self.assertEqual(r.kind, "forbidden")
        self.assertEqual(sb.count("scratch"), before)


class TestQlCloseDroppedValidation(unittest.TestCase):
    """`ql close --dropped` requires a reason (schemas/scratch.schema.json: dropped
    version requires `reason`; 30 L158)."""

    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_dropped_requires_reason(self):
        sb = self.sb
        deploy = _deploy(sb)
        ql = sb.rl_ok("ql", "open", "--role", "deploy", "--json", session=deploy).json["ql_tag"]
        before = sb.count("scratch")
        r = sb.rl("ql", "close", ql, "--dropped", session=deploy)
        self.assertEqual(r.rc, 2, str(r))
        self.assertEqual(r.kind, "validation")
        self.assertEqual(sb.count("scratch"), before)


class TestQlCloseRemovesWorktreeAndBranch(unittest.TestCase):
    """Both `--merged` and `--dropped` delete the worktree and the branch of the same
    name (07 L92; tables/commands.json ql close notes)."""

    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_merged_close_removes_worktree_and_branch(self):
        sb = self.sb
        deploy = _deploy(sb)
        ql = sb.rl_ok("ql", "open", "--role", "deploy", "--json", session=deploy).json["ql_tag"]
        wt = _worktree_path(sb, ql)
        self.assertTrue(wt.exists())
        self.assertIn(ql, sb.git("branch", "--list", ql).stdout)

        supp = _open_quick_lane_supplement(sb, deploy, ql)
        self.assertEqual(supp.rc, 0, f"quick-lane supplement open failed:\n{supp}")
        sb.rl_ok("ql", "close", ql, "--merged", "--handoff", supp.json["id"], session=deploy)

        self.assertFalse(wt.exists(), "ql close --merged must remove the worktree")
        self.assertNotIn(ql, sb.git("branch", "--list", ql).stdout)

    def test_dropped_close_removes_worktree_and_branch(self):
        sb = self.sb
        deploy = _deploy(sb)
        ql = sb.rl_ok("ql", "open", "--role", "deploy", "--json", session=deploy).json["ql_tag"]
        wt = _worktree_path(sb, ql)
        self.assertTrue(wt.exists())

        sb.rl_ok("ql", "close", ql, "--dropped", "--reason", "abandoned", session=deploy)

        self.assertFalse(wt.exists(), "ql close --dropped must remove the worktree")
        self.assertNotIn(ql, sb.git("branch", "--list", ql).stdout)


class TestScratchAddMiddleVersions(unittest.TestCase):
    """`rl scratch add QL [--note ...] [--metric k=v]` appends an open version; middle
    versions keep status open (no fourth state) across repeated additions, and are
    validated only against the skeleton and ql_tag, not the open/merged/dropped field
    table (03 L211; 07 L39, L64)."""

    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_scratch_add_keeps_status_open_across_multiple_versions(self):
        sb = self.sb
        deploy = _deploy(sb)
        ql = sb.rl_ok("ql", "open", "--role", "deploy", "--json", session=deploy).json["ql_tag"]

        sb.rl_ok("scratch", "add", ql, "--note", "first measurement", "--metric", "acc=0.5", session=deploy)
        row1 = sb.latest("scratch", ql)
        self.assertEqual(row1["status"], "open")
        self.assertEqual(row1["ql_tag"], ql)
        self.assertEqual(row1["metrics"]["acc"], 0.5)

        sb.rl_ok("scratch", "add", ql, "--note", "second measurement", "--metric", "acc=0.6", session=deploy)
        row2 = sb.latest("scratch", ql)
        self.assertEqual(row2["status"], "open")  # still open, no fourth state (03 L211)
        self.assertGreater(row2["version"], row1["version"])
        self.assertEqual(row2["metrics"]["acc"], 0.6)


class TestQlTransferExitPending(unittest.TestCase):
    """PENDING(issue 41f): the exit sub-command for a work order transferred into the
    quick lane by `ql open --from` (merge-back to done_pending_review, or abandonment
    back to todo) has no name yet (07 L114; tables/commands.json pending_commands;
    tables/transitions.json ql_transfer_exit)."""

    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_transfer_exit_subcommand_not_named_yet(self):
        self.skipTest(
            "PENDING(issue 41f): no sub-command name yet for the merge-back or "
            "abandonment exit of a quick-lane order transferred in with `ql open "
            "--from` (07 L114)."
        )


class Step4Commands(unittest.TestCase):
    """Step-4 status assertion: `rl status` only lists quick lanes that are not closed
    (07 L126; 30 L158)."""

    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_status_lists_only_unclosed_quick_lanes(self):
        sb = self.sb
        deploy = _deploy(sb)
        open_ql = sb.rl_ok("ql", "open", "--role", "deploy", "--json", session=deploy).json["ql_tag"]

        merged_ql = sb.rl_ok("ql", "open", "--role", "deploy", "--json", session=deploy).json["ql_tag"]
        supp = _open_quick_lane_supplement(sb, deploy, merged_ql, tag="m")
        self.assertEqual(supp.rc, 0, f"quick-lane supplement open failed:\n{supp}")
        sb.rl_ok("ql", "close", merged_ql, "--merged", "--handoff", supp.json["id"], session=deploy)

        dropped_ql = sb.rl_ok("ql", "open", "--role", "deploy", "--json", session=deploy).json["ql_tag"]
        sb.rl_ok("ql", "close", dropped_ql, "--dropped", "--reason", "abandoned", session=deploy)

        r = sb.rl_ok("status", "--json")
        text = json.dumps(r.json)
        self.assertIn(open_ql, text)
        self.assertNotIn(merged_ql, text)
        self.assertNotIn(dropped_ql, text)


if __name__ == "__main__":
    unittest.main()
