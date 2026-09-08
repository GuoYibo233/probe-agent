"""Test 7: session end releases in-progress orders (30 L76-86).

Original (30 L78): holder with in_progress orders gets them released automatically at
`session end` -- status todo, holder null, owner gets `orphaned`; done_pending_review and
stuck orders do not block session end.

Changed/added by 30's 2026-08-17 pass (30 L80-86), sourced from 04-handoffs-and-sessions.md
sixth section (L116-129) and the transitions.json `release_in_progress` row:
  - every in_progress order the session holds is released, none left; a run session's
    whole `--batch` is released together; every released id lands in the closed
    session's `released_handoffs` (04 L122; sessions.schema.json).
  - a dirty `experiments/` tree gets a `wip/<ho-id>` branch, named in `progress_note`
    (04 L127).
  - `--session ID` lets gyb close another session without checking liveness;
    `end_reason` is recorded as `manual`; a session already closed refuses any further
    write with exit 3 forbidden, and neither `--force` nor `--as-gyb --quote --force
    --reason` gets past that refusal (04 L152; 03 L15; ledgers.json writer_session_alive).
  - the release version's `actor` is the session's role and `via` is `session_end`
    (04 L75, L124; 05 L27-29).
  - a launch_order whose latest attempt has a launched, unfinished run is released
    without killing the process (04 L75 release.no_kill_if_launched).
"""

import unittest

from helpers import Sandbox, make_decision, open_work_order, open_launch_order


class SessionEndReleasesOrders(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_holder_order_released_with_progress_note_and_orphaned_notice(self):
        """30 L78-86: a holder with in_progress orders gets them released automatically
        at session end -- status todo, holder null, last_holder = the session,
        progress_note non-empty and saying the session ended, actor = the session's
        role, via = session_end (04 L75, L122-127; transitions.json release_in_progress
        preconditions and side_effects).
        30 L83: the owner receives an orphaned issue with handoff_id set (04 L75, L126,
        L195; 04 ninth-section table: orphaned -> owner)."""
        dec = make_decision(self.sb)
        ho = open_work_order(self.sb, None, dec)  # opened bare terminal: owner = gyb (04 L13 owner_definition)
        deploy = self.sb.role_session("deploy")
        self.sb.rl_ok("handoff", "start", ho, session=deploy)

        self.sb.rl_ok("session", "end", session=deploy, caller="hook")

        row = self.sb.latest("handoffs", ho)
        self.assertEqual(row["status"], "todo")
        self.assertIsNone(row["holder"])
        self.assertEqual(row["last_holder"], deploy)
        self.assertTrue(row["progress_note"])
        # 04 L125: the note says the session ended and names the holder; check the session
        # id shows up rather than pinning the exact sentence.
        self.assertIn(deploy, row["progress_note"])
        self.assertEqual(row["actor"], "deploy")
        self.assertEqual(row.get("via"), "session_end")

        orphaned = [i for i in self.sb.rows("issues") if i["kind"] == "orphaned"]
        self.assertEqual(len(orphaned), 1)
        self.assertEqual(orphaned[0]["assignee"], "gyb")
        self.assertEqual(orphaned[0]["handoff_id"], ho)

    def test_done_pending_review_and_stuck_orders_untouched(self):
        """30 L78: done_pending_review and stuck orders do not block session end and
        are untouched (04 L78 stuck_untouched: holder is already empty in both states,
        so session end has nothing of theirs to release)."""
        dec = make_decision(self.sb)
        wo_active = open_work_order(self.sb, None, dec, explanation="active order")
        wo_stuck = open_work_order(self.sb, None, dec, explanation="stuck order")
        deploy = self.sb.role_session("deploy")
        self.sb.rl_ok("handoff", "start", wo_active, session=deploy)
        self.sb.rl_ok("handoff", "start", wo_stuck, session=deploy)
        iss = self.sb.rl_ok("issue", "open", "--to", "idea", "--kind", "cannot", "--text",
                            "blocked", "--handoff", wo_stuck, "--json", session=deploy).json["id"]
        self.sb.rl_ok("handoff", "stuck", wo_stuck, "--issue", iss, session=deploy)

        # a launch_order reaches done_pending_review under a run session, unrelated to deploy's holding
        lo = open_launch_order(self.sb, None, wo_active)
        run = self.sb.role_session("run")
        self.sb.rl_ok("handoff", "start", lo, session=run)
        self.sb.rl_ok("run", "add", "--handoff", lo, "--attempt", "1", "--commit", "c",
                      "--host", "h", "--gpus", "0", "--log", "/tmp/l", "--tmux", "t",
                      "--watch-cmd", "w", session=run)
        self.sb.rl_ok("run", "finish", f"{lo}-a1", "--exit", "ok", "--metric", "acc=0.9",
                      "--data-path", "out.json", session=run)
        self.sb.rl_ok("handoff", "done", lo, session=run)

        stuck_version_before = self.sb.latest("handoffs", wo_stuck)["version"]
        dpr_version_before = self.sb.latest("handoffs", lo)["version"]

        self.sb.rl_ok("session", "end", session=deploy, caller="hook")

        stuck_row = self.sb.latest("handoffs", wo_stuck)
        dpr_row = self.sb.latest("handoffs", lo)
        self.assertEqual(stuck_row["version"], stuck_version_before)
        self.assertEqual(stuck_row["status"], "stuck")
        self.assertEqual(dpr_row["version"], dpr_version_before)
        self.assertEqual(dpr_row["status"], "done_pending_review")

        active_row = self.sb.latest("handoffs", wo_active)
        self.assertEqual(active_row["status"], "todo")
        self.assertIsNone(active_row["holder"])

    def test_all_in_progress_orders_released_and_recorded(self):
        """30 L82 (2026-08-17 decision): a session releases every order it holds, none
        left; a run session's whole batch is released together; all released ids are
        recorded in the closed session's released_handoffs (04 L122; sessions.schema.json
        released_handoffs).

        Two launch orders without a batch are started one by one (the batch form is
        proxy decision D-22, covered by test_batch_start_takes_every_todo_launch_order_of_the_batch)."""
        dec = make_decision(self.sb)
        wo = open_work_order(self.sb, None, dec)
        lo1 = open_launch_order(self.sb, None, wo, command="python3 t1.py")
        lo2 = open_launch_order(self.sb, None, wo, command="python3 t2.py")
        run = self.sb.role_session("run")
        self.sb.rl_ok("handoff", "start", lo1, session=run)
        self.sb.rl_ok("handoff", "start", lo2, session=run)

        self.sb.rl_ok("session", "end", session=run, caller="hook")

        for lo in (lo1, lo2):
            row = self.sb.latest("handoffs", lo)
            self.assertEqual(row["status"], "todo")
            self.assertIsNone(row["holder"])
            self.assertEqual(row["last_holder"], run)

        closed = self.sb.latest("sessions", run)
        self.assertCountEqual(closed["released_handoffs"], [lo1, lo2])

    def test_session_end_with_session_flag_does_not_check_liveness(self):
        """30 L84: `--session ID` closes another session without checking whether it is
        alive, end_reason is recorded as manual (04 L152: 'rl cannot see the process, only
        the ledger; it deregisters anyway, end_reason recorded as manual'; 01 L27-29)."""
        deploy = self.sb.role_session("deploy")

        r = self.sb.rl_ok("session", "end", "--session", deploy)  # gyb, bare terminal

        row = self.sb.latest("sessions", deploy)
        self.assertEqual(row["status"], "closed")
        self.assertEqual(row["end_reason"], "manual")

    def test_closed_session_write_refused(self):
        """30 L84: a closed session writing again is refused with exit 3 forbidden, and
        the message tells it to reload the role (03 L15: 'reload a role'; 04 L152-153:
        the message: "session already deregistered, reload the role to register")."""
        deploy = self.sb.role_session("deploy")
        self.sb.rl_ok("session", "end", session=deploy, caller="hook")
        self.sb.write_file("notes/seed.md", "# seed\n")

        r = self.sb.rl("decision", "add", "--text", "x", "--source", "file:notes/seed.md", session=deploy)

        self.assertEqual(r.rc, 3)
        self.assertEqual(r.kind, "forbidden")
        self.assertIn("reload", r.err.lower())
        self.assertEqual(self.sb.count("decisions", "deploy"), 0)

    def test_closed_session_write_refused_even_with_force(self):
        """30 L84 (03 L15; 01 L90): neither `--force` nor `--as-gyb --quote --force
        --reason` gets past the closed-session refusal; the only way out is reloading
        the role."""
        deploy = self.sb.role_session("deploy")
        self.sb.rl_ok("session", "end", session=deploy, caller="hook")
        self.sb.write_file("notes/seed.md", "# seed\n")

        r1 = self.sb.rl("decision", "add", "--text", "x", "--source", "file:notes/seed.md",
                        "--force", "--reason", "y", session=deploy)
        self.assertEqual(r1.rc, 3)
        self.assertEqual(r1.kind, "forbidden")

        r2 = self.sb.rl("decision", "add", "--text", "x", "--source", "file:notes/seed.md",
                        "--as-gyb", "--quote", "q", "--force", "--reason", "y", session=deploy)
        self.assertEqual(r2.rc, 3)
        self.assertEqual(r2.kind, "forbidden")

        self.assertEqual(self.sb.count("decisions", "deploy"), 0)

    def test_dirty_experiments_get_wip_branch(self):
        """30 L83: experiments/ dirty changes go to a wip/<ho-id> branch, named in
        progress_note (04 L127: '4. dirty changes under experiments/ go into a
        wip/<ho-id> branch, the branch name recorded in progress_note')."""
        dec = make_decision(self.sb)
        ho = open_work_order(self.sb, None, dec)
        deploy = self.sb.role_session("deploy")
        self.sb.rl_ok("handoff", "start", ho, session=deploy)
        self.sb.write_file("experiments/wip.py")

        self.sb.rl_ok("session", "end", session=deploy, caller="hook")

        branches = self.sb.git("branch", "--list", "wip/*").stdout
        self.assertIn(f"wip/{ho}", branches)
        row = self.sb.latest("handoffs", ho)
        self.assertIn(f"wip/{ho}", row["progress_note"])

    def test_launch_order_with_unfinished_run_not_killed(self):
        """30 L86: a launch_order whose latest attempt has a launched, unfinished run
        is released without any kill (04 L75 release.no_kill_if_launched: 'does not get
        its process killed (the next run adopts it)')."""
        dec = make_decision(self.sb)
        wo = open_work_order(self.sb, None, dec)
        lo = open_launch_order(self.sb, None, wo)
        run = self.sb.role_session("run")
        self.sb.rl_ok("handoff", "start", lo, session=run)
        self.sb.rl_ok("run", "add", "--handoff", lo, "--attempt", "1", "--commit", "c",
                      "--host", "h", "--gpus", "0", "--log", "/tmp/l", "--tmux", "t",
                      "--watch-cmd", "w", session=run)

        self.sb.rl_ok("session", "end", session=run, caller="hook")

        row = self.sb.latest("handoffs", lo)
        self.assertEqual(row["status"], "todo")
        self.assertIsNone(row["holder"])

        run_id = f"{lo}-a1"
        killed = [r for r in self.sb.rows("runs") if r["run_id"] == run_id and r.get("exit_status") == "killed"]
        self.assertEqual(killed, [])
        latest_run = self.sb.latest("runs", run_id)
        self.assertEqual(latest_run["status"], "launched")

    def test_closed_session_row_fields(self):
        """30 L86: the closed sessions row has ended_at, end_reason hook (caller=hook),
        and released_handoffs (sessions.schema.json x-conditions; 03 L188-190)."""
        dec = make_decision(self.sb)
        wo = open_work_order(self.sb, None, dec)
        deploy = self.sb.role_session("deploy")
        self.sb.rl_ok("handoff", "start", wo, session=deploy)

        self.sb.rl_ok("session", "end", session=deploy, caller="hook")

        row = self.sb.latest("sessions", deploy)
        self.assertEqual(row["status"], "closed")
        self.assertTrue(row["ended_at"])
        self.assertEqual(row["end_reason"], "hook")
        self.assertEqual(row["released_handoffs"], [wo])

    def test_session_start_after_end_reopens_the_same_chain(self):
        """Proxy decision D-28 (03 L15: the way out of a closed session is reloading the
        role): `rl session start` for a closed session_id passes and writes the next
        open version of the same chain; later writes from that session pass again."""
        deploy = self.sb.role_session("deploy", session_id="sess-reload")
        self.sb.rl_ok("session", "end", session=deploy, caller="hook")
        self.assertEqual(self.sb.latest("sessions", deploy)["status"], "closed")
        r = self.sb.rl("session", "start", "--role", "deploy", "--model", "m", "--launched-by", "manual",
                       session=deploy, caller="hook")
        self.assertEqual(r.rc, 0, str(r))
        row = self.sb.latest("sessions", deploy)
        self.assertEqual(row["status"], "open")
        self.assertGreater(row["version"], 1)
        dec = make_decision(self.sb)
        wo = open_work_order(self.sb, None, dec)
        self.sb.rl_ok("handoff", "start", wo, session=deploy)  # a write after the reload passes

    def test_batch_start_takes_every_todo_launch_order_of_the_batch(self):
        """Proxy decision D-22 (04 L98, L122): `rl handoff start ID --batch B` starts every
        todo launch_order whose batch is B (ID only locates the batch and must belong to
        it, otherwise exit 5); each gets its own start version with holder = this
        session, and session end hands the whole batch back, all ids recorded."""
        dec = make_decision(self.sb)
        wo = open_work_order(self.sb, None, dec)
        lo1 = open_launch_order(self.sb, None, wo, extra=("--batch", "b1"))
        lo2 = open_launch_order(self.sb, None, wo, extra=("--batch", "b1"))
        lo3 = open_launch_order(self.sb, None, wo, extra=("--batch", "other"))
        run = self.sb.role_session("run")
        bad = self.sb.rl("handoff", "start", lo3, "--batch", "b1", session=run)
        self.assertEqual(bad.rc, 5, str(bad))
        self.assertEqual(bad.kind, "usage")
        self.sb.rl_ok("handoff", "start", lo1, "--batch", "b1", session=run)
        for lo in (lo1, lo2):
            row = self.sb.latest("handoffs", lo)
            self.assertEqual(row["status"], "in_progress")
            self.assertEqual(row["holder"], run)
        self.assertEqual(self.sb.latest("handoffs", lo3)["status"], "todo")
        self.sb.rl_ok("session", "end", session=run, caller="hook")
        for lo in (lo1, lo2):
            self.assertEqual(self.sb.latest("handoffs", lo)["status"], "todo")
        self.assertEqual(sorted(self.sb.latest("sessions", run)["released_handoffs"]), sorted([lo1, lo2]))

    def test_session_end_closes_a_session_that_held_nothing(self):
        """Debt map 35(c) (sync-inbox Q35(c) L194; 06 L120): a session that held no
        in_progress order is closed too; the hook then deletes its state file (test 8)."""
        deploy = self.sb.role_session("deploy")
        state = self.sb.loop / ".sessions" / f"{deploy}.json"
        self.assertTrue(state.exists())
        self.sb.rl_ok("session", "end", session=deploy, caller="hook")
        self.assertEqual(self.sb.latest("sessions", deploy)["status"], "closed")
        # the file itself is removed by the deregistration hook after `rl session end`
        # (06 L120; hooks/rl_hook.py session-end), covered by test 8; rl only closes the row.

    def test_release_rows_are_written_before_the_closed_version(self):
        """Debt map 47(b) (03 L15; sync-inbox Q47(b) L348): session end first releases
        every held order (the release row carries this session's id and is not refused,
        because the sessions ledger still says open), and writes the closed version last."""
        dec = make_decision(self.sb)
        wo = open_work_order(self.sb, None, dec)
        deploy = self.sb.role_session("deploy")
        self.sb.rl_ok("handoff", "start", wo, session=deploy)
        self.sb.rl_ok("session", "end", session=deploy, caller="hook")
        release = self.sb.latest("handoffs", wo)
        self.assertEqual(release["status"], "todo")
        self.assertEqual(release["session_id"], deploy)
        closed = self.sb.latest("sessions", deploy)
        self.assertEqual(closed["status"], "closed")
        self.assertLessEqual(release["ts"], closed["ts"])  # release row written before the closed version (03 L15; 47(b))


if __name__ == "__main__":
    unittest.main()
