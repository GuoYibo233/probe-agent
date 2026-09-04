"""Test 9: actor and permissions (30 L94-106).

Original (30 L96): analysis calling `rl grant add` is exit 3; in an analysis session
`rl eval approve --as-gyb` without `--quote` is exit 2, with quote it passes and the row
has actor gyb and session_id the current session; bare terminal `rl eval approve` passes
directly with session_id cli; bare terminal `rl grant add` passes, a role session's
`--as-gyb` grant add is refused; non-run calling `rl run add` is exit 3, gyb passes; gyb
missing a required field is refused, with `--force --reason` it passes and the row has
force_reason.

Changed by 30 L98 (2026-08-17, sync-inbox Q27, gyb: "3 不是，可以替我写"): a role
session's `--as-gyb --quote` grant add now also passes -- but per proxy decision D-01
(issue 43c) the grants ledger is kept as a name only with no `rl grant` commands at all
(commands.json pending_commands; ledgers.json grants.pending), so every grant case here
is skipped rather than transcribed as a real assertion.

Added by 30 L100-106:
  - a role with --force is exit 3 with the "open an issue to gyb" command on stderr; a
    role session's `--as-gyb --quote --force --reason` counts as gyb and is written
    (03-ledgers.md gyb_exemption_scope; 01 L90).
  - `rl init` in a role session is exit 3 (05 L39, L119; 08 L9-13) -- stays red until
    `rl init` exists in build step 7.
  - `--force` does not get past an out-of-table transition, exit 2 (05 L119; 03 L228).
  - exit 5 for a bad argument value and an unknown id; every non-zero exit's first
    stderr line is the fixed reason kind, and with --json the same value is in
    error.kind (exit_codes.json; 03 L226; 05 L117).
  - `decisions.gyb.jsonl` only accepting session_id cli is already covered by test 3,
    not repeated here (30 L106).

Also covers, from 05-rl-cli.md / roles/*.json: a role's write command outside its
ledger_writes (run.json ledger_writes.handoffs has no "handoff accept") is exit 3.
"""

import unittest

from helpers import Sandbox, make_decision, open_work_order, open_launch_order


class EvalApproveActor(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def _propose_eval(self, session):
        r = self.sb.rl_ok("eval", "propose", "--kind", "metric", "--name", "acc",
                          "--definition", "accuracy", "--metrics-key", "acc",
                          "--applies-to", "track probe", "--json", session=session)
        return r.json["id"]

    def test_as_gyb_eval_approve_requires_quote(self):
        """30 L96: in an analysis session `rl eval approve --as-gyb` without --quote is
        exit 2 (01 L70; 05 L15, L119: '--as-gyb 缺 --quote 退出码 2')."""
        analysis = self.sb.role_session("analysis")
        eval_id = self._propose_eval(analysis)
        before = self.sb.count("evaluations")

        r = self.sb.rl("eval", "approve", eval_id, "--as-gyb", session=analysis)

        self.assertEqual(r.rc, 2)
        self.assertEqual(r.kind, "validation")
        self.assertEqual(self.sb.count("evaluations"), before)

    def test_as_gyb_eval_approve_with_quote_records_gyb_and_session(self):
        """30 L96: with quote it passes and the row has actor gyb and session_id the
        current session (01 L69-70; 05 L17-19)."""
        analysis = self.sb.role_session("analysis")
        eval_id = self._propose_eval(analysis)

        r = self.sb.rl_ok("eval", "approve", eval_id, "--as-gyb", "--quote", "looks good",
                          "--json", session=analysis)

        row = self.sb.latest("evaluations", eval_id)
        self.assertEqual(row["actor"], "gyb")
        self.assertEqual(row["session_id"], analysis)

    def test_bare_terminal_eval_approve_session_id_cli(self):
        """30 L96: bare terminal `rl eval approve` passes directly, session_id is cli
        (01 L69)."""
        analysis = self.sb.role_session("analysis")
        eval_id = self._propose_eval(analysis)

        r = self.sb.rl_ok("eval", "approve", eval_id, "--quote", "fine", "--json")

        row = self.sb.latest("evaluations", eval_id)
        self.assertEqual(row["actor"], "gyb")
        self.assertEqual(row["session_id"], "cli")


class GrantCommandsPending(unittest.TestCase):
    """30 L96, L98: grants are kept as a name only, no `rl grant` commands yet
    (proxy decision D-01, PENDING(issue 43c); commands.json pending_commands;
    ledgers.json grants.pending). Every grant case from test 9's original and
    2026-08-17-updated text is skipped rather than decided here."""

    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_analysis_session_grant_add_forbidden(self):
        self.skipTest("PENDING(issue 43c): grants ledger kept as a name only, no commands (D-01)")

    def test_bare_terminal_grant_add_passes(self):
        self.skipTest("PENDING(issue 43c): grants ledger kept as a name only, no commands (D-01)")

    def test_role_session_as_gyb_quote_grant_add_passes(self):
        self.skipTest("PENDING(issue 43c): grants ledger kept as a name only, no commands (D-01)")


class RunAddActor(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_run_add_forbidden_for_non_run_role(self):
        """30 L96: non-run calling `rl run add` is exit 3 (05 L73: 'who': 'run, gyb')."""
        dec = make_decision(self.sb)
        wo = open_work_order(self.sb, None, dec)
        lo = open_launch_order(self.sb, None, wo)
        run = self.sb.role_session("run")
        self.sb.rl_ok("handoff", "start", lo, session=run)
        analysis = self.sb.role_session("analysis")

        r = self.sb.rl("run", "add", "--handoff", lo, "--attempt", "1", "--commit", "c",
                       "--host", "h", "--gpus", "0", "--log", "/tmp/l", "--tmux", "t",
                       "--watch-cmd", "w", session=analysis)

        self.assertEqual(r.rc, 3)
        self.assertEqual(r.kind, "forbidden")
        self.assertEqual(self.sb.count("runs"), 0)

    def test_run_add_gyb_passes(self):
        """30 L96: gyb calling `rl run add` passes (03 L100: 'actor 是 run 或 gyb')."""
        dec = make_decision(self.sb)
        wo = open_work_order(self.sb, None, dec)
        lo = open_launch_order(self.sb, None, wo)
        run = self.sb.role_session("run")
        self.sb.rl_ok("handoff", "start", lo, session=run)

        r = self.sb.rl_ok("run", "add", "--handoff", lo, "--attempt", "1", "--commit", "c",
                          "--host", "h", "--gpus", "0", "--log", "/tmp/l", "--tmux", "t",
                          "--watch-cmd", "w")  # bare terminal = gyb

        row = self.sb.latest("runs", f"{lo}-a1")
        self.assertEqual(row["actor"], "gyb")


class ForceAndCompleteness(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_gyb_missing_required_field_then_force_passes(self):
        """30 L96: gyb missing a required field is refused, with --force --reason it
        passes and the row has force_reason (02 L42: an empty source list is refused;
        03-ledgers.md gyb_exemption_scope: 'required fields ... still apply; --force
        --reason records force_reason')."""
        r = self.sb.rl("decision", "add", "--text", "no source")  # --source is required, none given
        self.assertEqual(r.rc, 2)
        self.assertEqual(r.kind, "validation")
        self.assertEqual(self.sb.count("decisions", "gyb"), 0)

        ok = self.sb.rl_ok("decision", "add", "--text", "no source", "--force", "--reason",
                           "testing force", "--json")

        row = self.sb.latest("decisions", ok.json["id"], book="gyb")
        self.assertEqual(row["force_reason"], "testing force")

    def test_role_force_forbidden_with_open_issue_command(self):
        """30 L102: a role with --force is exit 3 with the 'open an issue to gyb'
        command on stderr (03-ledgers.md: 'actor 是角色的命令带 --force 一律拒收，
        退出码 3，附「开 issue 给 gyb」的命令'; rl_lib.issue_command_for_gyb)."""
        deploy = self.sb.role_session("deploy")
        self.sb.write_file("notes/seed.md", "# seed\n")

        r = self.sb.rl("decision", "add", "--text", "x", "--source", "file:notes/seed.md",
                       "--force", "--reason", "y", session=deploy)

        self.assertEqual(r.rc, 3)
        self.assertEqual(r.kind, "forbidden")
        self.assertIn("issue open", r.err)
        self.assertIn("gyb", r.err)
        self.assertEqual(self.sb.count("decisions", "deploy"), 0)

    def test_as_gyb_quote_force_reason_counts_as_gyb(self):
        """30 L102: a role session's --as-gyb --quote --force --reason counts as gyb
        and is written (03-ledgers.md; 01 L90)."""
        deploy = self.sb.role_session("deploy")

        r = self.sb.rl_ok("decision", "add", "--text", "no source", "--as-gyb", "--quote",
                          "gyb said so", "--force", "--reason", "override", "--json", session=deploy)

        row = self.sb.latest("decisions", r.json["id"], book="deploy")
        self.assertEqual(row["actor"], "gyb")
        self.assertEqual(row["session_id"], deploy)
        self.assertEqual(row["force_reason"], "override")

    def test_out_of_table_transition_force_still_exit2(self):
        """30 L104: --force does not get past an out-of-table transition, exit 2
        (05 L119: 'transitions outside the table are refused with exit 2, also for
        gyb with --force')."""
        dec = make_decision(self.sb)
        wo = open_work_order(self.sb, None, dec)  # status todo; accept is only valid from done_pending_review

        r = self.sb.rl("handoff", "accept", wo, "--force", "--reason", "y")

        self.assertEqual(r.rc, 2)
        self.assertEqual(r.kind, "validation")
        self.assertEqual(self.sb.count("handoffs"), 1)  # only the open version


class InitInRoleSession(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_init_in_role_session_forbidden(self):
        """30 L103: `rl init` in a role session is exit 3 (05 L39, L119; 08 L9-13).
        Stays red until `rl init` exists (build step 7, 30 L200); this only checks the
        role-session gate."""
        deploy = self.sb.role_session("deploy")

        r = self.sb.rl("init", session=deploy)

        self.assertEqual(r.rc, 3)
        self.assertEqual(r.kind, "forbidden")


class ExitCodesAndJson(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_exit5_usage_unknown_id(self):
        """30 L104: exit 5 for an unknown id (03 L221: 'usage error ... unknown id')."""
        r = self.sb.rl("decision", "show", "dec-idea-9999")
        self.assertEqual(r.rc, 5)
        self.assertEqual(r.kind, "usage")

    def test_exit5_usage_bad_argument_value(self):
        """30 L104: exit 5 for a bad argument (03 L221: 'usage error ... 参数写错').
        --exit takes only ok|failed|killed (03 L117)."""
        r = self.sb.rl("run", "finish", "ho-0001-a1", "--exit", "bogus")
        self.assertEqual(r.rc, 5)
        self.assertEqual(r.kind, "usage")

    def test_json_error_kind_and_stderr_kind_together(self):
        """30 L104-105 (03 L226; 05 L117): on every non-zero exit the first stderr line
        is the fixed reason kind, and --json puts the same value into error.kind, at
        once -- not one or the other."""
        r = self.sb.rl("decision", "show", "dec-idea-9999", "--json")
        self.assertNotEqual(r.rc, 0)
        self.assertEqual(r.kind, "usage")
        self.assertEqual(r.json["error"]["kind"], "usage")


class WriteOutsideLedgerWrites(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_run_session_handoff_accept_forbidden(self):
        """A role's write command outside its ledger_writes is exit 3
        (roles/run.json ledger_writes.handoffs: no 'handoff accept'; 05 L100:
        'machine check only checks that a write command in the SKILL.md is in that
        role's ledger_writes')."""
        dec = make_decision(self.sb)
        wo = open_work_order(self.sb, None, dec)
        lo = open_launch_order(self.sb, None, wo)
        run = self.sb.role_session("run")
        self.sb.rl_ok("handoff", "start", lo, session=run)

        r = self.sb.rl("handoff", "accept", lo, session=run)

        self.assertEqual(r.rc, 3)
        self.assertEqual(r.kind, "forbidden")
        self.assertEqual(self.sb.latest("handoffs", lo)["status"], "in_progress")


if __name__ == "__main__":
    unittest.main()
