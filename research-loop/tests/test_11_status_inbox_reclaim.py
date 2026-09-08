"""Test 11: `rl status`, `rl inbox`, `rl reclaim` (30 L120-130).

Original (30 L122): three orders of different ages, in-threshold and out-of-threshold
each listed correctly; the ten-section inbox each has one fixture that makes it show
up; inbox's four kinds each get one fixture; `--only`/`--skip` work on reclaim, a
launched launch order is not killed by default and only `--kill` kills it; `--line`
filters correctly.

Changed by 30 L124 (2026-08-17 issues 23, 28): inbox is five items, not four kinds --
the fifth is the verdict on feedback this role proposed; inbox is read-only, it never
closes an issue as a side effect; a notification-kind issue (withdrawn, orphaned, fyi)
is closed by its own recipient, not by reading the inbox.

Added by 30 L126-130:
  - `rl status`'s first line prints the number of days since the last reclaim (05 L166;
    01 L120, L147).
  - `--json` rows carry at least the twelve keys of `status_row_min_keys`;
    `holder_alive` follows the holder session's latest `sessions` version being `open`;
    `age_hours` counts from the ts of the row's CURRENT status version, not from when
    the order was first opened (05 L168, 2026-08-17 issue 29).
  - section 7 and reclaim's `last_activity` are not stored in any ledger, they are
    computed live as the max `ts` over the nine ledgers for that `session_id` (03, 04
    section 7).
  - reclaim pushes a `rejected` order idle beyond `reclaim.handoff_idle_hours` back to
    `todo` via the `rejected` -> `todo` transition row, `actor` gyb, `via=reclaim`; a
    `stuck` order only gets its linked issue reassigned to the owner, its own status is
    untouched (04 section 8; transitions.json `release_rejected`, `stuck_untouched`).
  - the minimal `--json` shapes of `rl inbox`, `rl doctor`, `rl reclaim` are defined in
    05-rl-cli.md "exit codes and --json" / exit_codes.json json_shapes.
  - run does not call inbox (05 L141, sync-inbox issue 28): no fixture in this file
    gives a `run` session an inbox item.

Sourced from: 05-rl-cli.md L131-221 (inbox L131-143, trace L145-147, status ten
sections L149-170, reclaim L172-187, doctor L189-221); 04-handoffs-and-sessions.md
L162-186 (reclaim rules), L188-194 (three notifications), and transitions.json rows
`release_in_progress`, `release_rejected`, `stuck`, `reject` (who_can_write includes
`reclaim`; `release_in_progress` needs a non-empty `progress_note`, auto-filled by
reclaim); 01-gyb.md L116-135 (status sections and --json keys, restated from 05, "the two
sides must match word for word").

`line` field container shape and whether it is stored as one value or a list is left
open by handoffs.schema.json ("PENDING(part 04 L27)"); `rl status --json`'s top-level
container (list vs an object keyed by section) is likewise not pinned by 05 L121-123 or
exit_codes.json (only the per-row twelve keys are pinned, and only `inbox`/`doctor`/
`reclaim` get an explicit top-level shape). Tests below that only need to prove a row
*appears* search the whole --json payload rather than assume its shape (matching
test_05_stale.py's `json.dumps(r.json)` substring style); only the one test that reads
individual key values off one row (`test_json_row_carries_the_twelve_keys...`) uses
`_find_row` to locate that row regardless of container shape.
"""

import json
import unittest

from helpers import Sandbox, make_decision, open_work_order, open_launch_order


def _find_row(payload, target_id):
    """Locate a dict with id == target_id inside a --json payload of unspecified
    container shape (05 L121-123 pins only the per-row keys, not the top-level shape)."""
    if isinstance(payload, dict):
        if payload.get("id") == target_id:
            return payload
        for v in payload.values():
            found = _find_row(v, target_id)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _find_row(item, target_id)
            if found is not None:
                return found
    return None


def _to_done_pending_review(sb, tag="dpr"):
    """A work_order moved through the whole to done_pending_review, same sequence as
    test_04_deliverables.py's `_new_work_order` + amend + done (04 L35-36, L68)."""
    dec = make_decision(sb)
    ho = open_work_order(sb, None, dec)
    deploy = sb.role_session("deploy")
    sb.write_file(f"experiments/{tag}-{ho}-method.md", "# method\n")
    sb.write_file(f"experiments/{tag}-{ho}-detail.md", "# detail\n")
    sb.write_file(f"experiments/{tag}-{ho}-code.py", "# code\n")
    # amend is a todo/stuck or done_pending_review row, not an in_progress one (04 L64,
    # L69, L80): fill the paths before start, as test_04 does
    sb.rl_ok("handoff", "amend", ho, "--report-method", f"experiments/{tag}-{ho}-method.md",
             "--report-detail", f"experiments/{tag}-{ho}-detail.md",
             "--code-path", f"experiments/{tag}-{ho}-code.py", session=deploy)
    sb.rl_ok("handoff", "start", ho, session=deploy)
    sb.rl_ok("handoff", "done", ho, session=deploy)
    return ho


class StatusFirstLine(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_first_line_reports_days_since_last_reclaim(self):
        """05 L166; 01 L120, L147: the first line of `rl status` prints how many days
        have passed since the last reclaim. No reclaim has ever run in this fresh
        sandbox; only the semantic content (mentions reclaim, carries a number) is
        pinned by the parts -- the exact wording is not, so this does not pin a literal
        sentence."""
        r = self.sb.rl("status")
        self.assertEqual(r.rc, 0, str(r))
        first_line = r.out.splitlines()[0] if r.out.strip() else ""
        self.assertIn("reclaim", first_line.lower())
        self.assertRegex(first_line, r"\d")


class StatusSections(unittest.TestCase):
    """One fixture per section of the ten (30 L122, updated by 30 L126; 05 L153-165;
    01 L122-133). Each test builds only the fixture for its own section in a fresh
    sandbox and checks the fixture's id shows up somewhere in `rl status`'s output."""

    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_section1_non_terminal_order(self):
        """05 L155 section 1: orders not in a terminal state; a fresh todo work_order
        qualifies (transitions.json terminal_states = accepted, withdrawn only)."""
        dec = make_decision(self.sb)
        ho = open_work_order(self.sb, None, dec)
        r = self.sb.rl("status")
        self.assertEqual(r.rc, 0, str(r))
        self.assertIn(ho, r.out)
        # 05 L156: the "marked" form for stale rows is not ruled by the parts, so only
        # the presence is asserted.

    def test_section2_issue_assigned_to_gyb_marked_stale(self):
        """05 L156: open issues assigned to gyb, those beyond `issues.gyb_stale_hours`
        marked (08 threshold table default 24h; threshold set to 0 here so the issue is
        immediately over it, per the sandbox's zero-threshold idle convention)."""
        self.sb.set_config("issues.gyb_stale_hours", 0)
        iss = self.sb.rl_ok("issue", "open", "--to", "gyb", "--kind", "request",
                            "--text", "need a call", "--json").json["id"]
        r = self.sb.rl("status")
        self.assertEqual(r.rc, 0, str(r))
        self.assertIn(iss, r.out)

    def test_section3_evaluation_proposed(self):
        """05 L157 section 3: evaluations waiting for approval."""
        analysis = self.sb.role_session("analysis")
        eval_id = self.sb.rl_ok("eval", "propose", "--kind", "metric", "--name", "acc",
                                "--definition", "accuracy", "--metrics-key", "acc",
                                "--applies-to", "track probe", "--json",
                                session=analysis).json["id"]
        r = self.sb.rl("status")
        self.assertEqual(r.rc, 0, str(r))
        self.assertIn(eval_id, r.out)

    def test_section4_order_waiting_for_acceptance(self):
        """05 L158 section 4: orders waiting for acceptance, i.e. at
        done_pending_review (04 L35-36, L68)."""
        ho = _to_done_pending_review(self.sb)
        r = self.sb.rl("status")
        self.assertEqual(r.rc, 0, str(r))
        self.assertIn(ho, r.out)

    def test_section5_todo_order_whose_owner_has_no_live_session(self):
        """05 L159 section 5: waiting for gyb to start -- a todo order whose owner has
        no live session. Owner idea opens it, then idea's session ends."""
        idea = self.sb.role_session("idea")
        dec = make_decision(self.sb, session=idea)
        ho = open_work_order(self.sb, idea, dec)
        self.sb.rl_ok("session", "end", session=idea, caller="hook")
        r = self.sb.rl("status")
        self.assertEqual(r.rc, 0, str(r))
        self.assertIn(ho, r.out)

    def test_section5_dispatch_manual_order(self):
        """05 L159 section 5: a dispatch=manual order, opened with --manual
        (04 L28, L84-88; commands.json handoff open [--manual|--no-dispatch])."""
        dec = make_decision(self.sb)
        ho = open_work_order(self.sb, None, dec, extra=("--manual",))
        r = self.sb.rl("status")
        self.assertEqual(r.rc, 0, str(r))
        self.assertIn(ho, r.out)

    def test_section5_manual_order_in_progress_is_not_listed(self):
        """Proxy decision D-35 (05 L159; 01 L108): section 5 is the waiting-for-gyb list,
        so a dispatch=manual order someone has already started is not in it."""
        dec = make_decision(self.sb)
        ho = open_work_order(self.sb, None, dec, extra=("--manual",))
        deploy = self.sb.role_session("deploy")
        self.sb.rl_ok("handoff", "start", ho, session=deploy)
        r = self.sb.rl("status", "--json")
        self.assertEqual(r.rc, 0, str(r))
        row = _find_row(r.json, ho)
        self.assertIsNotNone(row, f"no row with id {ho} in {r.json!r}")
        self.assertEqual(row["dispatch"], "manual")
        self.assertNotIn(5, row["sections"])

    def test_section6_stale_order(self):
        """05 L160 section 6: a stale order -- a work order citing v1, decision
        updated to v2 (same fixture used for `rl decision stale` in test_05_stale.py;
        repeated here to demonstrate this specific status section)."""
        dec = make_decision(self.sb)
        ho = open_work_order(self.sb, None, dec)
        self.sb.rl("decision", "update", dec, "--text", "revised approach")
        r = self.sb.rl("status")
        self.assertEqual(r.rc, 0, str(r))
        self.assertIn(ho, r.out)

    def test_section6_live_order_under_retired_decision(self):
        """05 L160 section 6: a live order under a retired decision."""
        dec = make_decision(self.sb)
        ho = open_work_order(self.sb, None, dec)
        self.sb.rl_ok("decision", "retire", dec, "--text", "no longer needed")
        r = self.sb.rl("status")
        self.assertEqual(r.rc, 0, str(r))
        self.assertIn(ho, r.out)

    def test_section7_holder_silent_beyond_stale_holder_minutes(self):
        """05 L161 section 7: an in_progress order whose holder session has not
        written for longer than `status.stale_holder_minutes` (08 threshold table
        default 30 minutes; set to 0 here, zero-threshold idle convention)."""
        self.sb.set_config("status.stale_holder_minutes", 0)
        dec = make_decision(self.sb)
        ho = open_work_order(self.sb, None, dec)
        deploy = self.sb.role_session("deploy")
        self.sb.rl_ok("handoff", "start", ho, session=deploy)
        r = self.sb.rl("status")
        self.assertEqual(r.rc, 0, str(r))
        self.assertIn(ho, r.out)

    def test_section8_feedback_proposed(self):
        """05 L162 section 8: feedback waiting for a verdict."""
        fb = self.sb.rl_ok("feedback", "add", "--target", "principle-06",
                           "--text", "improve wording", "--json").json["id"]
        r = self.sb.rl("status")
        self.assertEqual(r.rc, 0, str(r))
        self.assertIn(fb, r.out)

    def test_section9_live_session_with_focus(self):
        """05 L163 section 9: live sessions, including focus (`rl session focus
        --decision ID`, reviewer only, 04 L154, L158)."""
        reviewer = self.sb.role_session("reviewer")
        dec = make_decision(self.sb)
        self.sb.rl_ok("session", "focus", "--decision", dec, session=reviewer)
        r = self.sb.rl("status")
        self.assertEqual(r.rc, 0, str(r))
        self.assertIn(reviewer, r.out)

    def test_section9_open_quick_lane(self):
        """05 L163 section 9: quick lanes not closed."""
        deploy = self.sb.role_session("deploy")
        ql_tag = self.sb.rl_ok("ql", "open", "--role", "deploy", "--json",
                               session=deploy).json["ql_tag"]
        r = self.sb.rl("status")
        self.assertEqual(r.rc, 0, str(r))
        self.assertIn(ql_tag, r.out)

    def test_section10_doctor_findings_not_fixed(self):
        """05 L164 section 10: what the last doctor run found and nobody fixed. Uses
        doctor item 19 (sessions row model is unknown, same fixture as
        test_18_session_amend.py's Step4Commands test)."""
        sess = self.sb.role_session("deploy", model="unknown")
        r = self.sb.rl("status")
        self.assertEqual(r.rc, 0, str(r))
        self.assertIn(sess, r.out)


class StatusJsonAndFiltering(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_json_row_carries_the_twelve_keys_holder_alive_and_age_hours(self):
        """05 L121, L126, L168 (2026-08-17 issue 29): --json rows carry at least the
        twelve keys; holder_alive is true because the holder session's latest sessions
        version is open; age_hours is computed from the ts of the row's current status
        version, so a just-opened, just-started order has age_hours close to zero."""
        dec = make_decision(self.sb)
        ho = open_work_order(self.sb, None, dec)
        deploy = self.sb.role_session("deploy")
        self.sb.rl_ok("handoff", "start", ho, session=deploy)

        r = self.sb.rl("status", "--json")
        self.assertEqual(r.rc, 0, str(r))
        row = _find_row(r.json, ho)
        self.assertIsNotNone(row, f"no row with id {ho} in {r.json!r}")
        for key in ("id", "work_type", "owner", "holder", "holder_alive", "status",
                    "age_hours", "line", "decision_refs", "batch", "log_path", "watch_cmd"):
            self.assertIn(key, row)
        self.assertEqual(row["status"], "in_progress")
        self.assertEqual(row["holder"], deploy)
        self.assertTrue(row["holder_alive"])
        self.assertLess(row["age_hours"], 1)

    def test_line_filter_shows_only_that_lines_own_order(self):
        """05 L166: `--line` filters by root decision id; an order under a different
        root decision does not appear under a `--line` it is not part of."""
        dec1 = make_decision(self.sb, text="line one decision")
        dec2 = make_decision(self.sb, text="line two decision")
        ho1 = open_work_order(self.sb, None, dec1)
        ho2 = open_work_order(self.sb, None, dec2)

        r1 = self.sb.rl("status", "--line", dec1)
        self.assertEqual(r1.rc, 0, str(r1))
        self.assertIn(ho1, r1.out)
        self.assertNotIn(ho2, r1.out)

    def test_cross_root_order_appears_under_every_related_line(self):
        """sync-inbox Q43(b)(d) L311-313; handoffs.schema.json `line` description: an
        order whose decision_refs span more than one root decision appears under every
        related line's `--line` view, not only under one of them."""
        dec1 = make_decision(self.sb, text="root one")
        dec2 = make_decision(self.sb, text="root two")
        ho_cross = open_work_order(self.sb, None, dec1, extra=("--decision", f"{dec2}@1"))

        r1 = self.sb.rl("status", "--line", dec1)
        r2 = self.sb.rl("status", "--line", dec2)
        self.assertEqual(r1.rc, 0, str(r1))
        self.assertEqual(r2.rc, 0, str(r2))
        self.assertIn(ho_cross, r1.out)
        self.assertIn(ho_cross, r2.out)

    def test_group_by_line_and_batch_do_not_error(self):
        """05 L166: the whole listing can be grouped by --group-by line|batch; this is
        a light structural check (rc 0) since the exact rendering of the groups is not
        pinned by the parts beyond 'line is the root decision id'."""
        dec = make_decision(self.sb)
        open_work_order(self.sb, None, dec, extra=("--batch", "b1"))
        r_line = self.sb.rl("status", "--group-by", "line")
        r_batch = self.sb.rl("status", "--group-by", "batch")
        self.assertEqual(r_line.rc, 0, str(r_line))
        self.assertEqual(r_batch.rc, 0, str(r_batch))

    def test_group_by_line_lists_open_quick_lane_as_a_separate_heap(self):
        """01 L132; 07 L126: quick lanes not closed do not belong to any line; under
        --group-by line they are listed as their own separate heap. This test checks
        the quick lane still shows up under --group-by line (the exact layout that
        proves it is a *separate* heap rather than folded into a line is not pinned by
        the parts, so only presence is checked here)."""
        deploy = self.sb.role_session("deploy")
        ql_tag = self.sb.rl_ok("ql", "open", "--role", "deploy", "--json",
                               session=deploy).json["ql_tag"]
        r = self.sb.rl("status", "--group-by", "line")
        self.assertEqual(r.rc, 0, str(r))
        self.assertIn(ql_tag, r.out)


class Inbox(unittest.TestCase):
    """`rl inbox` as a role session: five items (05 L133-139, 2026-08-17 issue 23),
    read-only (05 L138), --json is an object with five keys each an array of raw rows
    (05 L123). No test in this class gives a `run` session an inbox item: run does not
    use inbox (05 L141, sync-inbox issue 28), so there is deliberately no run fixture
    here."""

    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_item1_own_open_issues(self):
        """05 L135: item 1 -- open issues assigned to this role."""
        idea = self.sb.role_session("idea")
        iss = self.sb.rl_ok("issue", "open", "--to", "idea", "--kind", "request",
                            "--text", "please decide", "--json").json["id"]
        r = self.sb.rl("inbox", "--json", session=idea)
        self.assertEqual(r.rc, 0, str(r))
        self.assertIn(iss, json.dumps(r.json))

    def test_item2_owned_orders_with_no_holder(self):
        """05 L136: item 2 -- orders owned by this role with an empty holder."""
        idea = self.sb.role_session("idea")
        dec = make_decision(self.sb, session=idea)
        ho = open_work_order(self.sb, idea, dec)
        r = self.sb.rl("inbox", "--json", session=idea)
        self.assertEqual(r.rc, 0, str(r))
        self.assertIn(ho, json.dumps(r.json))

    def test_item2_lists_a_done_pending_review_order_the_role_owns(self):
        """Proxy decision D-33 (05 L136; 04 L47, L51): item 2 covers the four non-terminal
        states with no holder, so an order the role owns that came back done_pending_review
        is listed, and an accepted one is not."""
        idea = self.sb.role_session("idea")
        dec = make_decision(self.sb, session=idea)
        ho = open_work_order(self.sb, idea, dec)
        deploy = self.sb.role_session("deploy")
        self.sb.write_file("experiments/d33/method.md")
        self.sb.write_file("experiments/d33/detail.md")
        self.sb.write_file("experiments/d33/x.py")
        self.sb.rl_ok("handoff", "amend", ho, "--report-method", "experiments/d33/method.md",
                      "--report-detail", "experiments/d33/detail.md",
                      "--code-path", "experiments/d33/x.py", session=deploy)
        self.sb.rl_ok("handoff", "start", ho, session=deploy)
        self.sb.rl_ok("handoff", "done", ho, session=deploy)
        r = self.sb.rl("inbox", "--json", session=idea)
        self.assertEqual(r.rc, 0, str(r))
        self.assertIn(ho, [o["id"] for o in r.json["orders_without_holder"]])
        self.sb.rl_ok("handoff", "accept", ho, session=idea)
        r = self.sb.rl("inbox", "--json", session=idea)
        self.assertEqual(r.rc, 0, str(r))
        self.assertNotIn(ho, [o["id"] for o in r.json["orders_without_holder"]])

    def test_item3_stale_decisions_only_for_orders_this_session_holds(self):
        """05 L137, L143 (2026-08-17 gyb ruling): item 3 lists only past-version
        decisions cited by orders THIS SESSION holds, not everything the role owns.
        Positive: this session holds an order citing a decision that gets updated.
        Negative: another order the role owns but a different session holds does not
        show up (same distinction as test_05_stale.py's inbox item 3 test, restated
        here for inbox's five-item enumeration)."""
        deploy_a = self.sb.role_session("deploy")
        dec_held = make_decision(self.sb, text="held by session a")
        ho_held = open_work_order(self.sb, None, dec_held, to_role="deploy")
        self.sb.rl_ok("handoff", "start", ho_held, session=deploy_a)
        self.sb.rl("decision", "update", dec_held, "--text", "revised, session a's order")

        deploy_b = self.sb.role_session("deploy")
        dec_other = make_decision(self.sb, text="held by session b")
        ho_other = open_work_order(self.sb, None, dec_other, to_role="deploy")
        self.sb.rl_ok("handoff", "start", ho_other, session=deploy_b)
        self.sb.rl("decision", "update", dec_other, "--text", "revised, session b's order")

        r = self.sb.rl("inbox", "--json", session=deploy_a)
        self.assertEqual(r.rc, 0, str(r))
        blob = json.dumps(r.json)
        self.assertIn(dec_held, blob)
        self.assertNotIn(ho_other, blob)

    def test_item4_notification_addressed_to_this_role(self):
        """05 L138: item 4 -- notifications (withdrawn, orphaned, fyi) addressed to
        this role. Reuses the session-end orphaned notice already verified in
        test_07_session_end.py: owner idea gets an orphaned issue when deploy's
        session ends while holding idea's order."""
        idea = self.sb.role_session("idea")
        dec = make_decision(self.sb, session=idea)
        ho = open_work_order(self.sb, idea, dec)
        deploy = self.sb.role_session("deploy")
        self.sb.rl_ok("handoff", "start", ho, session=deploy)
        self.sb.rl_ok("session", "end", session=deploy, caller="hook")

        r = self.sb.rl("inbox", "--json", session=idea)
        self.assertEqual(r.rc, 0, str(r))
        blob = json.dumps(r.json)
        self.assertIn(ho, blob)
        self.assertIn("orphaned", blob)

    def test_item5_verdict_on_feedback_this_role_proposed(self):
        """05 L139: item 5 -- verdicts on feedback this role proposed."""
        deploy = self.sb.role_session("deploy")
        fb = self.sb.rl_ok("feedback", "add", "--target", "principle-06",
                           "--text", "tweak wording", "--json", session=deploy).json["id"]
        self.sb.rl_ok("feedback", "reject", fb, "--text", "not needed for now")

        r = self.sb.rl("inbox", "--json", session=deploy)
        self.assertEqual(r.rc, 0, str(r))
        self.assertIn(fb, json.dumps(r.json))

    def test_inbox_is_read_only_does_not_close_the_issue(self):
        """05 L138: inbox is read-only -- reading it never closes an issue as a side
        effect; a notification-kind issue is closed only when its recipient explicitly
        calls `rl issue close`."""
        idea = self.sb.role_session("idea")
        iss = self.sb.rl_ok("issue", "open", "--to", "idea", "--kind", "request",
                            "--text", "please decide", "--json").json["id"]
        r = self.sb.rl("inbox", "--json", session=idea)
        self.assertEqual(r.rc, 0, str(r))
        row = self.sb.latest("issues", iss)
        self.assertEqual(row["status"], "open")

    def test_inbox_json_is_an_object_of_five_arrays(self):
        """05 L123 (exit_codes.json json_shapes.inbox): an object with five keys
        matching the five inbox items, each an array of raw ledger rows. Key names
        themselves are not fixed by the parts, only the shape (five keys, each a
        list), so this checks the shape without guessing the key names."""
        idea = self.sb.role_session("idea")
        r = self.sb.rl("inbox", "--json", session=idea)
        self.assertEqual(r.rc, 0, str(r))
        self.assertIsInstance(r.json, dict)
        self.assertEqual(len(r.json), 5)
        for v in r.json.values():
            self.assertIsInstance(v, list)


class Reclaim(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_without_apply_only_lists(self):
        """04 L176: without --apply reclaim only lists, no ledger changes."""
        self.sb.set_config("reclaim.session_idle_hours", 0)
        deploy = self.sb.role_session("deploy")
        sessions_before = self.sb.count("sessions")

        r = self.sb.rl("reclaim")

        self.assertEqual(r.rc, 0, str(r))
        self.assertEqual(self.sb.count("sessions"), sessions_before)
        self.assertEqual(self.sb.latest("sessions", deploy)["status"], "open")

    def test_within_threshold_is_not_listed(self):
        """30 L122: orders and sessions inside the thresholds are not listed. A session
        opened just now and an order just moved are below the default 48 h / 72 h
        (08 L71-72) and below status.stale_holder_minutes 30 (08 L70), so neither
        `reclaim` nor status section 7 lists them (04 L172-173; 05 L161)."""
        dec = make_decision(self.sb)
        ho = open_work_order(self.sb, None, dec)
        deploy = self.sb.role_session("deploy")
        self.sb.rl_ok("handoff", "start", ho, session=deploy)
        r = self.sb.rl("reclaim", "--json")
        self.assertEqual(r.rc, 0, str(r))
        listed = {row["id"] for row in (r.json or [])}
        self.assertNotIn(deploy, listed)
        self.assertNotIn(ho, listed)
        st = self.sb.rl("status", "--json")
        self.assertEqual(st.rc, 0, str(st))
        rows = st.json if isinstance(st.json, list) else (st.json or {}).get("rows", [])
        for row in rows:
            if isinstance(row, dict) and row.get("id") == ho:
                self.assertFalse(row.get("stale_holder", False), row)

    def test_json_shape_kind_id_idle_hours_action(self):
        """05 L123 (exit_codes.json json_shapes.reclaim): an array of {kind, id,
        idle_hours, action}."""
        self.sb.set_config("reclaim.session_idle_hours", 0)
        deploy = self.sb.role_session("deploy")

        r = self.sb.rl("reclaim", "--json")

        self.assertEqual(r.rc, 0, str(r))
        self.assertIsInstance(r.json, list)
        row = next(x for x in r.json if x["id"] == deploy)
        for key in ("kind", "id", "idle_hours", "action"):
            self.assertIn(key, row)
        self.assertEqual(row["kind"], "session")

    def test_only_and_skip_filter(self):
        """05 L94; 04 L166: --only and --skip filter which idle things are listed."""
        self.sb.set_config("reclaim.session_idle_hours", 0)
        d1 = self.sb.role_session("deploy")
        d2 = self.sb.role_session("analysis")

        r_only = self.sb.rl("reclaim", "--only", d1, "--json")
        self.assertEqual(r_only.rc, 0, str(r_only))
        ids_only = {x["id"] for x in r_only.json}
        self.assertIn(d1, ids_only)
        self.assertNotIn(d2, ids_only)

        r_skip = self.sb.rl("reclaim", "--skip", d1, "--json")
        self.assertEqual(r_skip.rc, 0, str(r_skip))
        ids_skip = {x["id"] for x in r_skip.json}
        self.assertNotIn(d1, ids_skip)
        self.assertIn(d2, ids_skip)

    def test_skip_order_leaves_its_idle_holder_session_alone(self):
        """PENDING(part 04 L166) reading: --skip ORDER on an idle session that holds that
        order keeps the session out of the run too, because closing it while it still holds
        the order would break 04 L51. Session open, order in_progress, nothing written."""
        self.sb.set_config("reclaim.session_idle_hours", 0)
        dec = make_decision(self.sb)
        ho = open_work_order(self.sb, None, dec)
        deploy = self.sb.role_session("deploy")
        self.sb.rl_ok("handoff", "start", ho, session=deploy)
        before = (self.sb.count("handoffs"), self.sb.count("sessions"))

        self.sb.rl_ok("reclaim", "--skip", ho, "--apply")

        self.assertEqual(self.sb.latest("sessions", deploy)["status"], "open")
        self.assertEqual(self.sb.latest("handoffs", ho)["status"], "in_progress")
        self.assertEqual((self.sb.count("handoffs"), self.sb.count("sessions")), before)

    def test_apply_closes_idle_session_and_releases_its_orders(self):
        """04 L178: an idle session is closed with end_reason reclaim, and its
        in_progress orders released with actor gyb and via=reclaim
        (transitions.json release_in_progress.side_effects.release.actor_via;
        release.progress_note_nonempty: reclaim fills progress_note automatically)."""
        self.sb.set_config("reclaim.session_idle_hours", 0)
        dec = make_decision(self.sb)
        ho = open_work_order(self.sb, None, dec)
        deploy = self.sb.role_session("deploy")
        self.sb.rl_ok("handoff", "start", ho, session=deploy)

        self.sb.rl_ok("reclaim", "--apply")

        session_row = self.sb.latest("sessions", deploy)
        self.assertEqual(session_row["status"], "closed")
        self.assertEqual(session_row["end_reason"], "reclaim")
        self.assertEqual(session_row["released_handoffs"], [ho])

        ho_row = self.sb.latest("handoffs", ho)
        self.assertEqual(ho_row["status"], "todo")
        self.assertIsNone(ho_row["holder"])
        self.assertEqual(ho_row["actor"], "gyb")
        self.assertEqual(ho_row.get("via"), "reclaim")
        self.assertTrue(ho_row["progress_note"])

    def test_launched_unfinished_run_not_killed_by_default(self):
        """04 L179; transitions.json release_in_progress.side_effects.no_kill_if_launched:
        an in_progress launch_order whose latest attempt has a launched, unfinished run
        is released without killing anything, by default. The launch order becomes idle
        by its own handoff_idle_hours here, independently of the holding run session
        (which is left alive, not ended)."""
        self.sb.set_config("reclaim.handoff_idle_hours", 0)
        dec = make_decision(self.sb)
        wo = open_work_order(self.sb, None, dec)
        lo = open_launch_order(self.sb, None, wo)
        run = self.sb.role_session("run")
        self.sb.rl_ok("handoff", "start", lo, session=run)
        self.sb.rl_ok("run", "add", "--handoff", lo, "--attempt", "1", "--commit", "c",
                      "--host", "h", "--gpus", "0", "--log", "/tmp/l", "--tmux", "t",
                      "--watch-cmd", "w", session=run)

        self.sb.rl_ok("reclaim", "--apply")

        run_id = f"{lo}-a1"
        self.assertEqual(self.sb.latest("runs", run_id)["status"], "launched")
        ho_row = self.sb.latest("handoffs", lo)
        self.assertEqual(ho_row["status"], "todo")
        self.assertIsNone(ho_row["holder"])
        self.assertTrue(ho_row["progress_note"])

    def test_idle_session_release_with_kill_aborts_its_launched_run(self):
        """04 L178 through the in_progress -> todo row (04 L75): a launch order handed
        back because its holder session went idle keeps its process by default and is
        aborted (runs finished version exit_status killed) when reclaim carries --kill."""
        dec = make_decision(self.sb)
        wo = open_work_order(self.sb, None, dec)
        lo = open_launch_order(self.sb, None, wo)
        run = self.sb.role_session("run")
        self.sb.rl_ok("handoff", "start", lo, session=run)
        self.sb.rl_ok("run", "add", "--handoff", lo, "--attempt", "1", "--commit", "c", "--host", "h",
                      "--gpus", "0", "--log", "/tmp/l", "--tmux", "t", "--watch-cmd", "w", session=run)
        self.sb.set_config("reclaim.session_idle_hours", 0)
        # the order itself is not past reclaim.handoff_idle_hours (default 72 h)
        r = self.sb.rl("reclaim", "--apply", "--kill")
        self.assertEqual(r.rc, 0, str(r))
        self.assertEqual(self.sb.latest("handoffs", lo)["status"], "todo")
        run_row = self.sb.latest("runs", f"{lo}-a1")
        self.assertEqual(run_row["status"], "finished")
        self.assertEqual(run_row["exit_status"], "killed")

    def test_kill_flag_finishes_the_run_as_killed(self):
        """04 L179: --kill triggers the abort path -- process kill, GPU free, host
        deregister, runs falls to a finished version with exit_status killed."""
        self.sb.set_config("reclaim.handoff_idle_hours", 0)
        dec = make_decision(self.sb)
        wo = open_work_order(self.sb, None, dec)
        lo = open_launch_order(self.sb, None, wo)
        run = self.sb.role_session("run")
        self.sb.rl_ok("handoff", "start", lo, session=run)
        self.sb.rl_ok("run", "add", "--handoff", lo, "--attempt", "1", "--commit", "c",
                      "--host", "h", "--gpus", "0", "--log", "/tmp/l", "--tmux", "t",
                      "--watch-cmd", "w", session=run)

        self.sb.rl_ok("reclaim", "--apply", "--kill")

        run_id = f"{lo}-a1"
        run_row = self.sb.latest("runs", run_id)
        self.assertEqual(run_row["status"], "finished")
        self.assertEqual(run_row["exit_status"], "killed")
        self.assertEqual(self.sb.latest("handoffs", lo)["status"], "todo")

    def test_stuck_order_only_reassigns_issue_to_owner(self):
        """04 L180; transitions.json stuck_untouched: a stuck order's linked issue is
        reassigned to the owner; the handoff's own status is untouched (stays stuck)."""
        self.sb.set_config("reclaim.handoff_idle_hours", 0)
        dec = make_decision(self.sb)
        wo = open_work_order(self.sb, None, dec)  # owner gyb, opened bare terminal
        deploy = self.sb.role_session("deploy")
        self.sb.rl_ok("handoff", "start", wo, session=deploy)
        iss = self.sb.rl_ok("issue", "open", "--to", "idea", "--kind", "cannot", "--text",
                            "blocked", "--handoff", wo, "--json", session=deploy).json["id"]
        self.sb.rl_ok("handoff", "stuck", wo, "--issue", iss, session=deploy)

        self.sb.rl_ok("reclaim", "--apply")

        ho_row = self.sb.latest("handoffs", wo)
        self.assertEqual(ho_row["status"], "stuck")
        iss_row = self.sb.latest("issues", iss)
        self.assertEqual(iss_row["assignee"], "gyb")

    def test_rejected_order_past_threshold_goes_back_to_todo(self):
        """04 L181; transitions.json release_rejected: a rejected order idle beyond
        reclaim.handoff_idle_hours goes back to todo, actor gyb, via=reclaim."""
        self.sb.set_config("reclaim.handoff_idle_hours", 0)
        ho = _to_done_pending_review(self.sb, tag="rej")
        self.sb.rl_ok("handoff", "reject", ho, "--reason", "needs rework")

        self.sb.rl_ok("reclaim", "--apply")

        row = self.sb.latest("handoffs", ho)
        self.assertEqual(row["status"], "todo")
        self.assertEqual(row["actor"], "gyb")
        self.assertEqual(row.get("via"), "reclaim")

    def test_done_pending_review_and_todo_orders_are_only_listed(self):
        """04 L182: done_pending_review and todo orders are only listed by reclaim,
        never acted on."""
        self.sb.set_config("reclaim.handoff_idle_hours", 0)
        ho_dpr = _to_done_pending_review(self.sb, tag="list")
        dec2 = make_decision(self.sb)
        ho_todo = open_work_order(self.sb, None, dec2)

        r = self.sb.rl("reclaim", "--json")
        self.assertEqual(r.rc, 0, str(r))
        ids = {x["id"] for x in r.json}
        self.assertIn(ho_dpr, ids)
        self.assertIn(ho_todo, ids)

        self.sb.rl_ok("reclaim", "--apply")
        self.assertEqual(self.sb.latest("handoffs", ho_dpr)["status"], "done_pending_review")
        row_todo = self.sb.latest("handoffs", ho_todo)
        self.assertEqual(row_todo["status"], "todo")
        self.assertIsNone(row_todo["holder"])

    def test_apply_runs_doctor_at_the_end(self):
        """04 L184: reclaim --apply runs doctor at the end; check the output mentions
        doctor (exact wording of the announcement is not pinned by the parts)."""
        self.sb.set_config("reclaim.session_idle_hours", 0)
        self.sb.role_session("deploy")

        r = self.sb.rl_ok("reclaim", "--apply")

        self.assertIn("doctor", r.out.lower())

    def test_reclaim_from_role_session_is_forbidden(self):
        """05 L94 (commands.json reclaim who=gyb): a role session calling reclaim is
        exit 3 forbidden."""
        deploy = self.sb.role_session("deploy")

        r = self.sb.rl("reclaim", session=deploy)

        self.assertEqual(r.rc, 3)
        self.assertEqual(r.kind, "forbidden")


if __name__ == "__main__":
    unittest.main()
