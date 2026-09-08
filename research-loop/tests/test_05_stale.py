"""Test 5: staleness (30 L64-68).

Original (30 L64-66): a work order citing v1, decision updated to v2, `rl decision stale`
lists it; `rl status` also lists it; `rl inbox` lists it for the related role; evaluation
references are checked for staleness too.

Changed by 05-rl-cli.md (30 L68, 2026-08-17 ruled): `rl inbox` item 3 lists only the
orders held by the CURRENT SESSION, not everything the role owns - an owned-but-not-held
stale order goes to `rl status` section 6 instead. `rl decision stale` dropped `--mine`;
its signature is `[--handoff ID] [--all]`, and with neither flag it defaults to the
current session's held orders (02 L89), the same "current session" rule `rl inbox` item 3
uses.
"""

import json
import unittest

from helpers import Sandbox, make_decision, open_work_order


class StaleDecisions(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_order_citing_v1_is_listed_stale_with_all_after_update_to_v2(self):
        # 30 L66: "a work order cites v1, and after the decision updates to v2, `rl decision
        # stale` lists it".
        dec = make_decision(self.sb)
        ho = open_work_order(self.sb, None, dec)
        r = self.sb.rl("decision", "update", dec, "--text", "revised approach")
        self.assertEqual(r.rc, 0, str(r))
        r2 = self.sb.rl("decision", "stale", "--all")
        self.assertEqual(r2.rc, 0, str(r2))
        self.assertIn(ho, r2.out)

    def test_handoff_filter_lists_only_that_orders_stale_refs(self):
        # 02 L89: "--handoff ID only checks what that order cites"; 05 signature
        # `[--handoff ID] [--all]`.
        dec1 = make_decision(self.sb, text="line one decision")
        dec2 = make_decision(self.sb, text="line two decision")
        ho1 = open_work_order(self.sb, None, dec1)
        ho2 = open_work_order(self.sb, None, dec2)
        self.sb.rl("decision", "update", dec1, "--text", "line one, revised")
        self.sb.rl("decision", "update", dec2, "--text", "line two, revised")
        r = self.sb.rl("decision", "stale", "--handoff", ho1)
        self.assertEqual(r.rc, 0, str(r))
        self.assertIn(ho1, r.out)
        self.assertNotIn(ho2, r.out)

    def test_default_lists_only_orders_held_by_the_current_session(self):
        # 30 L68 (2026-08-17 ruled): default = "list only what relates to orders the current
        # session holds".
        dec = make_decision(self.sb)
        ho = open_work_order(self.sb, None, dec)
        sid = self.sb.role_session("deploy")
        r_start = self.sb.rl("handoff", "start", ho, session=sid)
        self.assertEqual(r_start.rc, 0, str(r_start))
        self.sb.rl("decision", "update", dec, "--text", "revised approach")
        r_holder = self.sb.rl("decision", "stale", session=sid)
        self.assertEqual(r_holder.rc, 0, str(r_holder))
        self.assertIn(ho, r_holder.out)
        r_other = self.sb.rl("decision", "stale")  # bare terminal: not the holder of ho
        self.assertEqual(r_other.rc, 0, str(r_other))
        self.assertNotIn(ho, r_other.out)

    def test_confirm_does_not_make_a_citing_order_stale(self):
        # 02 L60, L85: confirm "does not count as a version change, does not trigger staleness";
        # 30 L66 backdrop (also asserted, from the decision-account side, in
        # test_03_decisions.py).
        dec = make_decision(self.sb)
        ho = open_work_order(self.sb, None, dec)
        self.sb.write_file("notes/confirm-evidence.md", "# still holds\n")
        r = self.sb.rl("decision", "confirm", dec, "--source", "file:notes/confirm-evidence.md")
        self.assertEqual(r.rc, 0, str(r))
        r2 = self.sb.rl("decision", "stale", "--all")
        self.assertEqual(r2.rc, 0, str(r2))
        self.assertNotIn(ho, r2.out)

    def test_evaluation_references_checked_for_staleness_is_undecided(self):
        # 30 L68: "scope references are checked for staleness too" carries over the original
        # sentence, but no command is named for it; 22-pair-idea-analysis.md L115 lists this as
        # one of the questions left for gyb (item 3 of "things the source doc did not spell
        # out"), still unruled.
        self.skipTest(
            "PENDING(part 22 L115): which command checks evaluation_refs for staleness "
            "is not ruled (30 L68 keeps the original sentence without a command)."
        )


class Step4Commands(unittest.TestCase):
    """`rl status` and `rl inbox` are step-4 deliverables (30 L197 step table, row '4
    communication mechanism'); step 3 has no scripts/rl_cmds handler for them, so these
    stay red - by design - until step 4 lands. 30 L66 and 30 L68 name both commands as
    part of test 5's original scope."""

    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_status_section_6_lists_the_stale_order(self):
        # 05-rl-cli.md L160: section 6 = "stale orders and live orders under a retired
        # decision's name".
        dec = make_decision(self.sb)
        ho = open_work_order(self.sb, None, dec)
        self.sb.rl("decision", "update", dec, "--text", "revised approach")
        r = self.sb.rl("status", "--json")
        self.assertEqual(r.rc, 0, str(r))
        self.assertIn(ho, json.dumps(r.json))

    def test_inbox_item_3_lists_only_orders_held_by_this_session(self):
        # 05-rl-cli.md L137, L143 (2026-08-17 ruled): item 3 = "a stale decision cited by an
        # order the current session holds".
        dec = make_decision(self.sb)
        ho = open_work_order(self.sb, None, dec)
        sid_holder = self.sb.role_session("deploy")
        r_start = self.sb.rl("handoff", "start", ho, session=sid_holder)
        self.assertEqual(r_start.rc, 0, str(r_start))
        self.sb.rl("decision", "update", dec, "--text", "revised approach")
        r_holder = self.sb.rl("inbox", "--json", session=sid_holder)
        self.assertEqual(r_holder.rc, 0, str(r_holder))
        self.assertIn(ho, json.dumps(r_holder.json))
        sid_other = self.sb.role_session("analysis")
        r_other = self.sb.rl("inbox", "--json", session=sid_other)
        self.assertEqual(r_other.rc, 0, str(r_other))
        self.assertNotIn(ho, json.dumps(r_other.json))


if __name__ == "__main__":
    unittest.main()
