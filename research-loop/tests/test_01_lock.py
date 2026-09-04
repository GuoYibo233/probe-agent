"""Test 1: lock and numbering (30 L33-37).

Original: two processes append 100 rows each to the same ledger; numbers never collide,
the row count is right; ql_tag and run_id do not collide either.
Changed by 03 (sync-inbox Q9): batch is caller free text, not assigned inside the lock,
so the collision cases are ql_tag and run_id only.
"""

import re
import unittest

from helpers import Sandbox, make_decision, open_work_order, open_launch_order


class LockAndNumbering(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox.create()

    def tearDown(self):
        self.sb.destroy()

    def test_issue_numbers_do_not_collide_across_two_processes(self):
        # 03 L19: scan, assign, append inside one lock; 03 L21: numbers from 1, four digits minimum.
        per_proc = 100
        calls = [(("issue", "open", "--to", "gyb", "--kind", "request", "--text", f"q{i}"), {})
                 for i in range(2 * per_proc)]
        results = self.sb.parallel(calls, workers=2)
        bad = [r for r in results if r.rc != 0]
        self.assertEqual(bad, [], f"{len(bad)} writes failed, first:\n{bad[0] if bad else ''}")
        rows = self.sb.rows("issues")
        self.assertEqual(len(rows), 2 * per_proc)
        ids = [r["id"] for r in rows]
        self.assertEqual(len(set(ids)), 2 * per_proc, "duplicate issue ids")
        nums = sorted(int(re.fullmatch(r"iss-(\d+)", i).group(1)) for i in ids)
        self.assertEqual(nums, list(range(1, 2 * per_proc + 1)))
        self.assertIn("iss-0001", ids)
        self.assertIn("iss-0200", ids)

    def test_ql_tags_do_not_collide(self):
        # 07 L27: ql_tag assigned inside the lock, form ql-YYYYMMDD-NN.
        n = 20
        calls = [(("ql", "open", "--role", "analysis", "--json"), {}) for _ in range(2 * n)]
        results = self.sb.parallel(calls, workers=2)
        bad = [r for r in results if r.rc != 0]
        self.assertEqual(bad, [], f"{len(bad)} ql open failed, first:\n{bad[0] if bad else ''}")
        tags = [r["ql_tag"] for r in self.sb.rows("scratch") if r["version"] == 1]
        self.assertEqual(len(tags), 2 * n)
        self.assertEqual(len(set(tags)), 2 * n, "duplicate ql_tag")
        for t in tags:
            self.assertRegex(t, r"^ql-\d{8}-\d{2,}$")

    def test_run_ids_do_not_collide(self):
        # 04 L43: run_id is <ho-id>-a<attempt>, assigned by rl at open (attempt 1).
        dec = make_decision(self.sb)
        parent = open_work_order(self.sb, None, dec)
        n = 20
        calls = [(("handoff", "open", "--type", "launch_order", "--to", "run", "--parent", parent,
                   "--command", f"python3 t.py --i {i}", "--workdir", "experiments",
                   "--config", "model=m", "--config", "params=1", "--config", "dataset=d", "--config", "split=s",
                   "--json"), {}) for i in range(2 * n)]
        results = self.sb.parallel(calls, workers=2)
        bad = [r for r in results if r.rc != 0]
        self.assertEqual(bad, [], f"{len(bad)} launch_order open failed, first:\n{bad[0] if bad else ''}")
        launch = [r for r in self.sb.rows("handoffs") if r["work_type"] == "launch_order"]
        self.assertEqual(len(launch), 2 * n)
        run_ids = [r["attempts"][0]["run_id"] for r in launch]
        self.assertEqual(len(set(run_ids)), 2 * n, "duplicate run_id")
        for r in launch:
            self.assertEqual(r["attempts"][0]["run_id"], f"{r['id']}-a1")

    def test_sequence_passes_four_digits_without_reissue(self):
        # 03 L21: four digits is the minimum width; sorting is numeric.
        from helpers import RL  # noqa: F401 - documents that only the CLI is used
        self.sb.rl_ok("issue", "open", "--to", "gyb", "--kind", "request", "--text", "a")
        # seed the ledger with a high number the way an old repo would carry it
        with open(self.sb.loop / "issues.jsonl", "a") as fh:
            fh.write('{"id": "iss-9999", "version": 1, "status": "open", "ts": "2026-01-01T00:00:00+0000", '
                     '"actor": "gyb", "session_id": "cli", "schema_version": 1, "assignee": "gyb", '
                     '"kind": "request", "text": "old"}\n')
        r = self.sb.rl_ok("issue", "open", "--to", "gyb", "--kind", "request", "--text", "b", "--json")
        self.assertEqual(r.json["id"], "iss-10000")


if __name__ == "__main__":
    unittest.main()
