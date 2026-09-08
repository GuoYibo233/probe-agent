"""Test 19: `rl doctor --ack / --unack / --list-acks` (30 L177-179, named by
05-rl-cli.md's final draft).

Original (30 L179): doctor reports item 6 for a run; gyb `rl doctor --ack 6 RUN_ID`
makes that item/id pair permanently unreported and appends a row to
`loop/.doctor-acks.jsonl` recording item, id, ts, actor, session_id; `--list-acks` lists
every ack; `--unack 6 RUN_ID` appends an unack row and doctor reports it again; a role
session calling `--ack` is exit 3; `.doctor-acks.jsonl` is not one of the nine ledgers,
and `rl init` does not create it -- the first `--ack` does.

Sourced from 05-rl-cli.md L189-221 (doctor's nineteen items table L193-213, item 6 row
L200: "runs row handoff_id is empty, dangling, or not a launch_order | rl run relink
RUN_ID --handoff ID; ...use rl doctor --ack 6 RUN_ID | run; no live session then gyb";
ack rules L217); exit_codes.json
json_shapes.doctor ("an array; each element has item, ids, fix_cmd, push_to");
ledgers.json plain_files (`loop/.doctor-acks.jsonl`: "doctor ack records; created by the
first `doctor --ack`, not by `rl init`; not a ledger") and 08 L18 (same point, tables/
config_defaults.md keys section header note); commands.json (`doctor --ack`/`--unack`
who=gyb, `doctor --list-acks` who=anyone).

The fixture for item 6 needs a runs row with a missing or dangling handoff_id. `rl run
relink RUN_ID --handoff ID` refuses a non-existent target order (reference existence
still applies even under gyb's exemption -- ledgers.json gyb_exemption_scope: "required
fields, path existence and reference existence still apply"), so there is no way to
produce this row through `rl` itself. The fixture below writes a legitimate run row
first through `rl run add` (03-ledgers.md's own append-only, one-lock rules still apply
to how the fixture is built), then appends one more raw line to `loop/runs.jsonl`
directly, changing only handoff_id to a non-existent order id. This is a fixture
bypassing rl (03 L9's convention, as used for backdating timestamps elsewhere in this
test suite) -- it exists to reach a ledger state rl itself refuses to write, not to
claim rl would write it that way.

The exact field that distinguishes an "unack" row from an "ack" row in
`loop/.doctor-acks.jsonl` is not named anywhere in the parts (05 L217 only says
`--unack` "appends a line, unack" / appends an unack row); the unack test below only asserts
the observable facts the parts do state -- a new line is appended, it names the same
item/id pair, and doctor reports the finding again afterward -- without guessing the
discriminator field's name.
"""

import json
import unittest

from helpers import LEDGER_FILES, Sandbox, make_decision, open_launch_order, open_work_order


def _legit_run(sb):
    """A properly-formed launched run row through rl, same sequence as
    test_10_runs_schema.py's `_launch` + `_add` helpers. Returns the run_id."""
    dec = make_decision(sb)
    wo = open_work_order(sb, None, dec)
    lo = open_launch_order(sb, None, wo)
    run_sid = sb.role_session("run")
    sb.rl_ok("handoff", "start", lo, session=run_sid)
    sb.rl_ok("run", "add", "--handoff", lo, "--attempt", "1", "--commit", "c",
             "--host", "h", "--gpus", "0", "--log", "/tmp/l", "--tmux", "t",
             "--watch-cmd", "w", session=run_sid)
    return f"{lo}-a1"


def _make_handoff_id_dangling(sb, run_id):
    """Fixture bypassing rl (03 L9; module docstring above): `rl run relink` refuses a
    non-existent target order, so a dangling handoff_id can only be produced by writing
    loop/runs.jsonl directly. Appends one more raw version of run_id with handoff_id
    pointed at an order that does not exist."""
    base = sb.latest("runs", run_id)
    row = dict(base)
    row["version"] = base["version"] + 1
    row["handoff_id"] = "ho-9999"
    path = sb.loop / "runs.jsonl"
    with path.open("a") as f:
        f.write(json.dumps(row) + "\n")


class DoctorItem6DanglingHandoff(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_doctor_reports_item6_for_dangling_handoff_id(self):
        """05 L200 (item 6): doctor reports a runs row whose handoff_id is missing or
        dangling. --json is an array of {item, ids, fix_cmd, push_to}
        (exit_codes.json json_shapes.doctor); item 6's fix_cmd mentions `rl run relink`
        and push_to is `run` (the run session that wrote the row is still alive here)."""
        run_id = _legit_run(self.sb)
        _make_handoff_id_dangling(self.sb, run_id)

        r = self.sb.rl("doctor", "--json")

        self.assertEqual(r.rc, 0, str(r))
        self.assertIsInstance(r.json, list)
        item6 = next(x for x in r.json if x["item"] == 6)
        self.assertIn(run_id, item6["ids"])
        self.assertIn("rl run relink", item6["fix_cmd"])
        self.assertEqual(item6["push_to"], "run")

    def test_ack_appends_row_and_suppresses_the_finding(self):
        """05 L217: gyb `rl doctor --ack 6 RUN_ID` appends a row to
        loop/.doctor-acks.jsonl with item, id, ts, actor, session_id; the same
        item/id pair is never reported again."""
        run_id = _legit_run(self.sb)
        _make_handoff_id_dangling(self.sb, run_id)
        acks_path = self.sb.loop / ".doctor-acks.jsonl"
        self.assertFalse(acks_path.exists())

        self.sb.rl_ok("doctor", "--ack", "6", run_id)

        self.assertTrue(acks_path.exists())
        lines = [json.loads(l) for l in acks_path.read_text().splitlines() if l.strip()]
        self.assertEqual(len(lines), 1)
        row = lines[0]
        self.assertEqual(row["item"], 6)
        self.assertEqual(row["id"], run_id)
        for key in ("ts", "actor", "session_id"):
            self.assertIn(key, row)

        after = self.sb.rl("doctor", "--json")
        self.assertEqual(after.rc, 0, str(after))
        still_reported = [x for x in after.json if x["item"] == 6 and run_id in x["ids"]]
        self.assertEqual(still_reported, [])

    def test_list_acks_lists_the_ack(self):
        """05 L217: `--list-acks` lists every ack recorded so far."""
        run_id = _legit_run(self.sb)
        _make_handoff_id_dangling(self.sb, run_id)
        self.sb.rl_ok("doctor", "--ack", "6", run_id)

        r = self.sb.rl("doctor", "--list-acks", "--json")

        self.assertEqual(r.rc, 0, str(r))
        pairs = [(x["item"], x["id"]) for x in r.json]
        self.assertIn((6, run_id), pairs)

    def test_unack_appends_a_row_and_doctor_reports_again(self):
        """05 L217: `--unack ITEM ID` appends an unack row, and doctor reports the
        finding again afterward. The exact field naming the row an "unack" (as opposed
        to an "ack") is not specified by the parts, so only the two stated observable
        facts are checked: a new line is appended for the same item/id pair, and the
        finding reappears."""
        run_id = _legit_run(self.sb)
        _make_handoff_id_dangling(self.sb, run_id)
        acks_path = self.sb.loop / ".doctor-acks.jsonl"
        self.sb.rl_ok("doctor", "--ack", "6", run_id)
        lines_after_ack = acks_path.read_text().splitlines()

        self.sb.rl_ok("doctor", "--unack", "6", run_id)

        lines_after_unack = [l for l in acks_path.read_text().splitlines() if l.strip()]
        self.assertEqual(len(lines_after_unack), len(lines_after_ack) + 1)
        appended = json.loads(lines_after_unack[-1])
        self.assertEqual(appended["item"], 6)
        self.assertEqual(appended["id"], run_id)

        after = self.sb.rl("doctor", "--json")
        self.assertEqual(after.rc, 0, str(after))
        still_reported = [x for x in after.json if x["item"] == 6 and run_id in x["ids"]]
        self.assertEqual(len(still_reported), 1)

    def test_ack_from_role_session_is_forbidden(self):
        """05 L100, L217 (commands.json doctor --ack who=gyb): a role session running
        --ack is exit 3 forbidden, and no ack row is written."""
        run_id = _legit_run(self.sb)
        _make_handoff_id_dangling(self.sb, run_id)
        deploy = self.sb.role_session("deploy")

        r = self.sb.rl("doctor", "--ack", "6", run_id, session=deploy)

        self.assertEqual(r.rc, 3)
        self.assertEqual(r.kind, "forbidden")
        acks_path = self.sb.loop / ".doctor-acks.jsonl"
        self.assertFalse(acks_path.exists())

    def test_acks_file_absent_before_first_ack_and_not_a_ledger(self):
        """08 L18; ledgers.json plain_files: loop/.doctor-acks.jsonl is created by the
        first `doctor --ack`, not by `rl init`, and is not one of the nine ledgers
        (helpers.LEDGER_FILES enumerates the nine)."""
        self.assertNotIn(".doctor-acks.jsonl", LEDGER_FILES)
        acks_path = self.sb.loop / ".doctor-acks.jsonl"
        self.assertFalse(acks_path.exists())


class DoctorItem12BackAtTodo(unittest.TestCase):
    """05 L206 (item 12) with proxy decision D-34: the notification issues rl opens on a
    release (04 L195: orphaned; 04 L190: notices, not problems) do not count as the "linked
    issue still open" of item 12."""

    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_released_order_with_only_its_orphaned_notice_is_not_reported(self):
        dec = make_decision(self.sb)
        ho = open_work_order(self.sb, None, dec)
        deploy = self.sb.role_session("deploy")
        self.sb.rl_ok("handoff", "start", ho, session=deploy)
        self.sb.rl_ok("handoff", "release", ho, "--note", "handing back")  # owner gyb, 04 L75
        self.assertEqual(self.sb.latest("handoffs", ho)["status"], "todo")
        notices = [i for i in self.sb.rows("issues")
                   if i.get("handoff_id") == ho and i["status"] == "open"]
        self.assertTrue(notices, "the release wrote no open notice issue (04 L195)")
        self.assertTrue(all(i["kind"] in ("orphaned", "withdrawn", "fyi") for i in notices))

        r = self.sb.rl("doctor", "--json")

        self.assertEqual(r.rc, 0, str(r))
        self.assertEqual([x for x in r.json if x["item"] == 12 and ho in x["ids"]], [])

    def test_released_order_with_a_real_open_issue_is_reported_to_the_opener(self):
        dec = make_decision(self.sb)
        ho = open_work_order(self.sb, None, dec)
        deploy = self.sb.role_session("deploy")
        self.sb.rl_ok("handoff", "start", ho, session=deploy)
        analysis = self.sb.role_session("analysis")
        self.sb.rl_ok("issue", "open", "--to", "deploy", "--kind", "request", "--handoff", ho,
                      "--text", "please add the plot", session=analysis)
        self.sb.rl_ok("handoff", "release", ho, "--note", "handing back")  # owner gyb, 04 L75

        r = self.sb.rl("doctor", "--json")

        self.assertEqual(r.rc, 0, str(r))
        item12 = [x for x in r.json if x["item"] == 12 and ho in x["ids"]]
        self.assertEqual(len(item12), 1, str(r))
        self.assertEqual(item12[0]["push_to"], "analysis")


if __name__ == "__main__":
    unittest.main()
