"""Test 3: decision sources (30 L52-56; 02-decisions.md).

Original (30 L52-54): empty source list refused; three source kinds each one case; `file`
path that does not exist refused, anchor accepted; `run` kind whose run_id is not in the
runs ledger refused; update without --source inherits the previous version's sources;
confirm bumps version without changing text; merge auto-includes the merged ids and
records the root from --root.

Added by 02-decisions.md 2026-08-18 (30 L56): `file` sources may point at `review/` and
`experiments/` paths, not only `notes/`/`analysis/`; `confirm` does not print affected
orders and is skipped by staleness (02 L60, L85, L87); `merge` leaves the retired old
decisions' own `root_id` untouched (02 L23, L66).
"""

import json
import unittest

from helpers import Sandbox, make_decision, open_work_order, open_launch_order


def _add_run_row(sb, handoff_id, attempt=1, session=None):
    """Add a `launched` runs row for an existing launch_order's attempt (05 L73: command
    and config are copied from the launch order by rl, not passed on the command line)."""
    r = sb.rl(
        "run", "add",
        "--handoff", handoff_id, "--attempt", str(attempt),
        "--commit", "abc123", "--host", "host1", "--gpus", "0",
        "--log", "/tmp/rl-test.log", "--tmux", "rl-test-tmux", "--watch-cmd", "tmux attach -t rl-test-tmux",
        session=session,
    )
    assert r.rc == 0, f"run add failed:\n{r}"
    return f"{handoff_id}-a{attempt}"


def _make_run_id(sb):
    """A minimal decision -> work_order -> launch_order -> runs row chain, all as gyb."""
    dec = make_decision(sb)
    parent = open_work_order(sb, None, dec)
    launch = open_launch_order(sb, None, parent)
    return _add_run_row(sb, launch)


class DecisionSources(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    # ---- source list must be non-empty (02 L42) --------------------------------------

    def test_empty_source_list_refused(self):
        # 02 L42: "空列表入账脚本拒收"; 30 L52.
        r = self.sb.rl("decision", "add", "--text", "no sources at all")
        self.assertEqual(r.rc, 2, str(r))
        self.assertEqual(r.kind, "validation")
        self.assertEqual(self.sb.count("decisions", book="gyb"), 0)

    # ---- one case per source kind (02 L36-40; 30 L52) ---------------------------------

    def test_add_with_file_source(self):
        self.sb.write_file("notes/x.md", "# x\n")
        r = self.sb.rl("decision", "add", "--text", "t", "--source", "file:notes/x.md", "--json")
        self.assertEqual(r.rc, 0, str(r))
        row = self.sb.latest("decisions", r.json["id"])
        self.assertEqual(row["sources"], [{"kind": "file", "path": "notes/x.md"}])

    def test_add_with_decision_source(self):
        # 02 L38: {"kind":"decision","id":...,"version":...}.
        base = make_decision(self.sb)
        r = self.sb.rl("decision", "add", "--text", "derived", "--source", f"decision:{base}@1", "--json")
        self.assertEqual(r.rc, 0, str(r))
        row = self.sb.latest("decisions", r.json["id"])
        self.assertEqual(row["sources"], [{"kind": "decision", "id": base, "version": 1}])

    def test_add_with_run_source(self):
        # 02 L40: {"kind":"run","run_id":...}; "must exist in the runs ledger" (02 L42).
        run_id = _make_run_id(self.sb)
        r = self.sb.rl("decision", "add", "--text", "from a run", "--source", f"run:{run_id}", "--json")
        self.assertEqual(r.rc, 0, str(r))
        row = self.sb.latest("decisions", r.json["id"])
        self.assertEqual(row["sources"], [{"kind": "run", "run_id": run_id}])

    # ---- file kind: existence checked, anchor is not (02 L42) -------------------------

    def test_file_source_nonexistent_path_refused(self):
        r = self.sb.rl("decision", "add", "--text", "t", "--source", "file:notes/does-not-exist.md")
        self.assertEqual(r.rc, 2, str(r))
        self.assertEqual(r.kind, "validation")
        self.assertEqual(self.sb.count("decisions", book="gyb"), 0)

    def test_file_source_with_anchor_is_accepted_anchor_not_checked(self):
        # 02 L42: "锚点本身不校验" - any anchor text passes as long as the path exists.
        self.sb.write_file("notes/anchored.md", "# heading\ntext\n")
        r = self.sb.rl("decision", "add", "--text", "t", "--source", "file:notes/anchored.md#heading-that-does-not-exist",
                       "--json")
        self.assertEqual(r.rc, 0, str(r))
        row = self.sb.latest("decisions", r.json["id"])
        self.assertEqual(row["sources"], [{"kind": "file", "path": "notes/anchored.md", "anchor": "heading-that-does-not-exist"}])

    def test_file_source_may_point_at_review_dir(self):
        # 02 L42 (2026-08-18 gyb 裁): "review/ 里的清单... 都算"; 30 L57.
        self.sb.write_file("review/checklist.md", "# checklist\n")
        r = self.sb.rl("decision", "add", "--text", "t", "--source", "file:review/checklist.md", "--json")
        self.assertEqual(r.rc, 0, str(r))

    def test_file_source_may_point_at_experiments_dir(self):
        # 02 L42: "experiments/ 里的部署报告... 都算"; 30 L57.
        self.sb.write_file("experiments/deploy-report.md", "# report\n")
        r = self.sb.rl("decision", "add", "--text", "t", "--source", "file:experiments/deploy-report.md", "--json")
        self.assertEqual(r.rc, 0, str(r))

    def test_run_source_unknown_run_id_refused(self):
        # 02 L42: "run 类的 run_id 不在 runs 账里拒收".
        r = self.sb.rl("decision", "add", "--text", "t", "--source", "run:ho-9999-a1")
        self.assertEqual(r.rc, 2, str(r))
        self.assertEqual(r.kind, "validation")
        self.assertEqual(self.sb.count("decisions", book="gyb"), 0)

    # ---- update (02 L48, L74, L87, L110) -----------------------------------------------

    def test_update_without_source_inherits_previous_version_sources(self):
        dec = make_decision(self.sb)
        v1 = self.sb.latest("decisions", dec)
        r = self.sb.rl("decision", "update", dec, "--text", "revised text")
        self.assertEqual(r.rc, 0, str(r))
        v2 = self.sb.latest("decisions", dec)
        self.assertEqual(v2["version"], v1["version"] + 1)
        self.assertEqual(v2["sources"], v1["sources"])

    def test_update_prints_open_orders_citing_old_version(self):
        # 02 L87, L110: "写完那一刻，rl 当场列出引着旧版而没到终态的单子和它们的 holder".
        # Structured shape from the task conventions: --json carries the ids under "affected".
        dec = make_decision(self.sb)
        ho = open_work_order(self.sb, None, dec)
        r = self.sb.rl("decision", "update", dec, "--text", "revised", "--json")
        self.assertEqual(r.rc, 0, str(r))
        self.assertIn("affected", r.json)
        ids = [item if isinstance(item, str) else item.get("id") for item in r.json["affected"]]
        self.assertIn(ho, ids)

    # ---- confirm (02 L60, L75, L85, L87, L111) -----------------------------------------

    def test_confirm_bumps_version_keeps_text_op_is_confirm(self):
        dec = make_decision(self.sb, text="keep doing this")
        v1 = self.sb.latest("decisions", dec)
        self.sb.write_file("notes/confirm-evidence.md", "# still holds\n")
        r = self.sb.rl("decision", "confirm", dec, "--source", "file:notes/confirm-evidence.md", "--json")
        self.assertEqual(r.rc, 0, str(r))
        v2 = self.sb.latest("decisions", dec)
        self.assertEqual(v2["version"], v1["version"] + 1)
        self.assertEqual(v2["text"], v1["text"])
        self.assertEqual(v2["op"], "confirm")
        self.assertIn({"kind": "file", "path": "notes/confirm-evidence.md"}, v2["sources"])

    def test_confirm_does_not_print_affected_orders(self):
        # 02 L87: "rl decision confirm 不打印：确认继续没有东西要复核".
        dec = make_decision(self.sb)
        open_work_order(self.sb, None, dec)  # an open order citing v1, to make sure there WOULD be something to print
        self.sb.write_file("notes/confirm-evidence.md", "# still holds\n")
        r = self.sb.rl("decision", "confirm", dec, "--source", "file:notes/confirm-evidence.md", "--json")
        self.assertEqual(r.rc, 0, str(r))
        self.assertNotIn("affected", r.json)

    def test_confirm_does_not_make_a_citing_order_stale(self):
        # 02 L60, L85: confirm "不算改版，不触发过版"; 30 L56.
        dec = make_decision(self.sb)
        ho = open_work_order(self.sb, None, dec)
        self.sb.write_file("notes/confirm-evidence.md", "# still holds\n")
        r = self.sb.rl("decision", "confirm", dec, "--source", "file:notes/confirm-evidence.md")
        self.assertEqual(r.rc, 0, str(r))
        r2 = self.sb.rl("decision", "stale", "--all")
        self.assertEqual(r2.rc, 0, str(r2))
        self.assertNotIn(ho, r2.out)

    # ---- retire (02 L76, L79, L112) ----------------------------------------------------

    def test_retire_without_text_is_refused_even_for_gyb_with_force(self):
        """Proxy decision D-27 (02 L79 over 03 L27): the reason is owed by everyone, gyb
        too; --force --reason does not get past it; exit 5 usage (03 L224)."""
        dec = make_decision(self.sb)
        before = self.sb.count("decisions", book="gyb")
        r = self.sb.rl("decision", "retire", dec, "--force", "--reason", "forcing")
        self.assertEqual(r.rc, 5, str(r))
        self.assertEqual(r.kind, "usage")
        self.assertEqual(self.sb.count("decisions", book="gyb"), before)

    def test_retire_requires_text(self):
        # 02 L76: "必须带理由（谁废都要，gyb 也要）"; the reason is the version's `text`
        # (decisions.schema.json requires "text", minLength 1 - same content-validation
        # class as the empty-sources refusal above).
        # PENDING(issue 37a) (see the commands.json "decision retire" pending note): the exact flag
        # name for the reason is still open for review at the final merge; this test uses
        # --text, the name currently on record in tables/commands.json.
        dec = make_decision(self.sb)
        r = self.sb.rl("decision", "retire", dec)
        self.assertEqual(r.rc, 5, str(r))  # proxy decision D-27: a missing reason is a usage error (03 L224)
        self.assertEqual(r.kind, "usage")
        self.assertEqual(self.sb.latest("decisions", dec)["version"], 1)

    def test_retire_text_is_the_reason_and_bumps_status(self):
        dec = make_decision(self.sb)
        r = self.sb.rl("decision", "retire", dec, "--text", "no longer needed", "--json")
        self.assertEqual(r.rc, 0, str(r))
        v2 = self.sb.latest("decisions", dec)
        self.assertEqual(v2["status"], "retired")
        self.assertEqual(v2["text"], "no longer needed")
        self.assertEqual(v2["op"], "retire")

    def test_retire_prints_affected_orders(self):
        # 02 L87 also applies to retire (only confirm is the exception).
        dec = make_decision(self.sb)
        ho = open_work_order(self.sb, None, dec)
        r = self.sb.rl("decision", "retire", dec, "--text", "stopping this line", "--json")
        self.assertEqual(r.rc, 0, str(r))
        self.assertIn("affected", r.json)
        ids = [item if isinstance(item, str) else item.get("id") for item in r.json["affected"]]
        self.assertIn(ho, ids)

    # ---- merge (02 L23, L66, L77) -------------------------------------------------------

    def _two_decisions(self):
        self.sb.write_file("notes/a.md", "# approach A\n")
        self.sb.write_file("notes/b.md", "# approach B\n")
        r_a = self.sb.rl("decision", "add", "--text", "approach A", "--source", "file:notes/a.md", "--json")
        self.assertEqual(r_a.rc, 0, str(r_a))
        r_b = self.sb.rl("decision", "add", "--text", "approach B", "--source", "file:notes/b.md", "--json")
        self.assertEqual(r_b.rc, 0, str(r_b))
        return r_a.json["id"], r_b.json["id"]

    def test_merge_sources_merged_from_and_root_from_flag(self):
        dec_a, dec_b = self._two_decisions()
        r = self.sb.rl("decision", "merge", dec_a, dec_b, "--text", "unified approach", "--root", dec_a, "--json")
        self.assertEqual(r.rc, 0, str(r))
        new = self.sb.latest("decisions", r.json["id"])
        self.assertEqual(new["op"], "merge")
        self.assertEqual(set(new["merged_from"]), {dec_a, dec_b})
        self.assertEqual(new["root_id"], dec_a)
        # 02 L77: "sources 自动含全部被合并的旧决定".
        self.assertIn({"kind": "decision", "id": dec_a, "version": 1}, new["sources"])
        self.assertIn({"kind": "decision", "id": dec_b, "version": 1}, new["sources"])

    def test_merge_retires_old_decisions_keeping_their_own_root_id(self):
        # 02 L23, L66: "被合并的旧决定的废除版根照旧不动"; root taken by --root is only
        # for the NEW merged decision, not for the retired old ones.
        dec_a, dec_b = self._two_decisions()
        r = self.sb.rl("decision", "merge", dec_a, dec_b, "--text", "unified approach", "--root", dec_a, "--json")
        self.assertEqual(r.rc, 0, str(r))
        a_latest = self.sb.latest("decisions", dec_a)
        b_latest = self.sb.latest("decisions", dec_b)
        self.assertEqual(a_latest["status"], "retired")
        self.assertEqual(b_latest["status"], "retired")
        self.assertEqual(a_latest["root_id"], dec_a)  # its own root, unchanged
        self.assertEqual(b_latest["root_id"], dec_b)  # its own root, NOT dec_a

    # ---- decisions.gyb.jsonl only takes rows from a bare terminal (02 L11) -------------

    def test_decisions_gyb_book_add_version_is_cli_but_later_versions_may_come_from_a_role_session(self):
        # 02 L11: decisions.gyb.jsonl holds only decisions opened from a bare terminal and
        # their later versions; sync-inbox Q34(e) L171 struck the old "only session_id cli
        # rows" sentence: a later version may come from a role session with --as-gyb
        # --quote and keeps that session's id (decisions.schema.json x-conditions, book gyb
        # with op add -> session_id cli).
        dec = make_decision(self.sb, session=None)  # bare terminal -> decisions.gyb.jsonl
        self.assertTrue(dec.startswith("dec-gyb-"))
        self.assertEqual(self.sb.latest("decisions", dec, book="gyb")["session_id"], "cli")
        sid = self.sb.role_session("idea")
        r = self.sb.rl("decision", "update", dec, "--as-gyb", "--quote", "gyb said keep going",
                       "--text", "still valid", session=sid)
        self.assertEqual(r.rc, 0, str(r))
        row = self.sb.latest("decisions", dec, book="gyb")
        self.assertEqual(row["version"], 2)
        self.assertEqual(row["actor"], "gyb")
        self.assertEqual(row["session_id"], sid)
        self.assertEqual(row["quote"], "gyb said keep going")
        # the idea book got nothing: the file is chosen by the id prefix (02 L13)
        self.assertIsNone(self.sb.latest("decisions", dec, book="idea"))

    def test_as_gyb_add_from_role_session_lands_in_the_role_book_not_gyb(self):
        # 02 L11-13: prefix at open time is decided by which session made the call, even
        # for --as-gyb; the row's actor is gyb but the file is the role's book.
        self.sb.write_file("notes/idea-seed.md", "# note\n")
        sid = self.sb.role_session("idea")
        r = self.sb.rl("decision", "add", "--as-gyb", "--quote", "gyb said do X", "--text", "do X",
                       "--source", "file:notes/idea-seed.md", "--json", session=sid)
        self.assertEqual(r.rc, 0, str(r))
        new_id = r.json["id"]
        self.assertTrue(new_id.startswith("dec-idea-"))
        row = self.sb.latest("decisions", new_id, book="idea")
        self.assertIsNotNone(row)
        self.assertEqual(row["actor"], "gyb")
        self.assertEqual(row["quote"], "gyb said do X")
        self.assertIsNone(self.sb.latest("decisions", new_id, book="gyb"))


if __name__ == "__main__":
    unittest.main()
