"""Test 18: `rl session amend` (30 L173-175, named by 05-rl-cli.md's final draft).

Original (30 L175): amend an open session's model appends a version with only model
changed, status and other fields copied from the latest version; amend also works on a
closed session, without tripping the "closed session writing again" refusal; amend of
any field other than model is refused; who can call it is gyb or that role's own live
session, another role's session is exit 3; doctor item 19 no longer reports a session
after amend fixes its model (04 L153; 05 L153, L213: doctor item 19 is 'sessions row
model is unknown', fix `rl session amend ID --model M').

Sourced from 03-ledgers.md L176 (sessions section) and 04-handoffs-and-sessions.md L153,
L158 (rl session sub-commands and who can call them); both copies are meant to read
one-for-one (04's interface section: "the two sides must match word for word").
"""

import unittest

from helpers import Sandbox


class SessionAmend(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_amend_open_session_model_only(self):
        """30 L175: amend an open session's model appends a version with only model
        changed; status and other fields copied from the latest version
        (03 L176: 'the amend version copies status and the other fields from the
        latest version, only model changes')."""
        deploy = self.sb.role_session("deploy", model="model-a")
        before = self.sb.latest("sessions", deploy)

        self.sb.rl_ok("session", "amend", deploy, "--model", "model-b", session=deploy)

        after = self.sb.latest("sessions", deploy)
        self.assertEqual(after["version"], before["version"] + 1)
        self.assertEqual(after["model"], "model-b")
        self.assertEqual(after["status"], before["status"])
        self.assertEqual(after["role"], before["role"])
        self.assertEqual(after["launched_by"], before["launched_by"])
        self.assertEqual(after["rules_version"], before["rules_version"])
        self.assertEqual(after.get("started_at"), before.get("started_at"))

    def test_amend_closed_session_does_not_trip_liveness_refusal(self):
        """30 L175: amend also works on a closed session, without tripping the
        'closed session writing again' refusal (03 L176, sync-inbox Q18, Q30: 'a closed
        session can also amend, without tripping the "a closed session writing again is
        refused" clause')."""
        deploy = self.sb.role_session("deploy", model="model-a")
        self.sb.rl_ok("session", "end", session=deploy, caller="hook")

        r = self.sb.rl_ok("session", "amend", deploy, "--model", "model-c")  # gyb, bare terminal

        row = self.sb.latest("sessions", deploy)
        self.assertEqual(row["model"], "model-c")
        self.assertEqual(row["status"], "closed")

    def test_amend_other_field_refused(self):
        """30 L175: amend of any field other than model is refused (05 L40: amend
        changes model only). PENDING(part 30 L175): whether the refusal is exit 5 usage
        (unknown flag) or exit 2 validation is not ruled; either counts as refused."""
        deploy = self.sb.role_session("deploy")

        r = self.sb.rl("session", "amend", deploy, "--role", "run", session=deploy)

        self.assertIn(r.rc, (2, 5))
        self.assertIn(r.kind, ("validation", "usage"))
        self.assertEqual(self.sb.latest("sessions", deploy)["role"], "deploy")

    def test_amend_who_gyb_bare_terminal_passes(self):
        """30 L175: who can call amend is gyb ... (03 L176; 04 L158)."""
        deploy = self.sb.role_session("deploy")

        self.sb.rl_ok("session", "amend", deploy, "--model", "model-x")

        self.assertEqual(self.sb.latest("sessions", deploy)["model"], "model-x")

    def test_amend_who_own_live_session_passes(self):
        """30 L175: ... or that role's own live session (03 L176; 04 L158)."""
        deploy = self.sb.role_session("deploy")

        self.sb.rl_ok("session", "amend", deploy, "--model", "model-y", session=deploy)

        self.assertEqual(self.sb.latest("sessions", deploy)["model"], "model-y")

    def test_amend_who_other_role_session_forbidden(self):
        """30 L175: another role's session calling amend is exit 3 (04 L158: 'amend:
        gyb or that role's own live session')."""
        deploy = self.sb.role_session("deploy")
        run = self.sb.role_session("run")

        r = self.sb.rl("session", "amend", deploy, "--model", "model-z", session=run)

        self.assertEqual(r.rc, 3)
        self.assertEqual(r.kind, "forbidden")
        self.assertEqual(self.sb.latest("sessions", deploy)["model"], "test-model")


class Step4Commands(unittest.TestCase):
    """`rl doctor` is a build-step-4 deliverable (30 L197: step 3 delivers only
    tables/schemas/rl_lib/bin-rl-skeleton plus tests 1-7, 9, 10, 14, 17, 18, 20; doctor
    is listed under step 4 with tests 8, 11, 15, 16, 19). This class stays red until
    step 4 ships `scripts/rl_cmds/doctor.py`, not just until step 3b's ledger writers
    land."""

    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_doctor_item_19_clears_after_amend(self):
        """30 L175: doctor item 19 no longer reports after amend
        (05 L191-213: item 19 is 'sessions row model is unknown', fix `rl session amend
        ID --model M`; --json shape is an array of {item, ids, fix_cmd, push_to},
        05 L123)."""
        deploy = self.sb.role_session("deploy", model="unknown")

        before = self.sb.rl("doctor", "--json")
        self.assertEqual(before.rc, 0)
        items_before = [i for i in (before.json or []) if i["item"] == 19 and deploy in i["ids"]]
        self.assertEqual(len(items_before), 1)

        self.sb.rl_ok("session", "amend", deploy, "--model", "real-model")

        after = self.sb.rl("doctor", "--json")
        self.assertEqual(after.rc, 0)
        items_after = [i for i in (after.json or []) if i["item"] == 19 and deploy in i["ids"]]
        self.assertEqual(items_after, [])


if __name__ == "__main__":
    unittest.main()
