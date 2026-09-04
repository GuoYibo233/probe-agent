"""Test 14: evaluations account (30 L144-148; 03 L154-172).

Original: propose with a code_path that does not exist passes, approve refuses until
the file exists; reject then update then approve passes; an approved row that is
updated goes back to proposed; a figure row missing uses, or a group_by/x/y value
outside the allowed domain, is refused; one approve call can take several ids and one
quote.

Added by 30 L148: `rl eval retire` is gyb only (05 command table); applies_to is free
text, not parsed by rl, but required (03 L164).
"""

import unittest

from helpers import Sandbox


class Evaluations(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox.create()
        self.analysis = self.sb.role_session("analysis")

    def tearDown(self):
        self.sb.destroy()

    def _propose_metric(self, name, key, applies_to="track probe, model m"):
        r = self.sb.rl_ok("eval", "propose", "--kind", "metric", "--name", name,
                          "--definition", f"definition of {name}", "--metrics-key", key,
                          "--applies-to", applies_to, "--json", session=self.analysis)
        return r.json["id"]

    def test_propose_with_nonexistent_code_path_passes(self):
        """30 L144-148 (03 L166): propose with a code_path that does not exist passes."""
        r = self.sb.rl_ok("eval", "propose", "--kind", "metric", "--name", "acc",
                          "--definition", "accuracy over the eval set",
                          "--code-path", "analysis/common/metrics.py:accuracy",
                          "--applies-to", "track probe, model m", "--json", session=self.analysis)
        row = self.sb.latest("evaluations", r.json["id"])
        self.assertEqual(row["status"], "proposed")

    def test_approve_refused_until_code_path_exists(self):
        """30 L144-148 (03 L166): approve is refused while code_path does not exist, passes once it does."""
        r = self.sb.rl_ok("eval", "propose", "--kind", "metric", "--name", "acc",
                          "--definition", "accuracy over the eval set",
                          "--code-path", "analysis/common/metrics.py:accuracy",
                          "--applies-to", "track probe, model m", "--json", session=self.analysis)
        eval_id = r.json["id"]
        before = self.sb.count("evaluations")
        refused = self.sb.rl("eval", "approve", eval_id, "--quote", "gyb said so")
        self.assertEqual(refused.rc, 2, str(refused))
        self.assertEqual(refused.kind, "validation")
        self.assertEqual(self.sb.count("evaluations"), before)
        self.sb.write_file("analysis/common/metrics.py", "def accuracy():\n    pass\n")
        self.sb.rl_ok("eval", "approve", eval_id, "--quote", "gyb said so")
        self.assertEqual(self.sb.latest("evaluations", eval_id)["status"], "approved")

    def test_reject_then_update_then_approve_passes(self):
        """30 L146: reject then update then approve passes."""
        eval_id = self._propose_metric("acc2", "acc")
        self.sb.rl_ok("eval", "reject", eval_id, "--reason", "not specific enough")
        self.sb.rl_ok("eval", "update", eval_id, "--definition", "accuracy, tightened", session=self.analysis)
        self.sb.rl_ok("eval", "approve", eval_id, "--quote", "gyb said so")
        self.assertEqual(self.sb.latest("evaluations", eval_id)["status"], "approved")

    def test_approved_then_update_goes_back_to_proposed(self):
        """03 L156: an approved evaluation that is updated goes back to proposed."""
        eval_id = self._propose_metric("acc3", "acc3key")
        self.sb.rl_ok("eval", "approve", eval_id, "--quote", "gyb said so")
        self.sb.rl_ok("eval", "update", eval_id, "--definition", "accuracy, v2", session=self.analysis)
        self.assertEqual(self.sb.latest("evaluations", eval_id)["status"], "proposed")

    def test_figure_missing_uses_refused(self):
        """03 L167-170: a figure row missing uses is refused."""
        before = self.sb.count("evaluations")
        r = self.sb.rl("eval", "propose", "--kind", "figure", "--name", "fig1",
                       "--definition", "accuracy by model", "--group-by", "config.model",
                       "--x", "config.params", "--y", "config.dataset",
                       "--applies-to", "track probe", session=self.analysis)
        self.assertEqual(r.rc, 2, str(r))
        self.assertEqual(r.kind, "validation")
        self.assertEqual(self.sb.count("evaluations"), before)

    def test_figure_group_by_outside_domain_refused(self):
        """03 L167-169: group_by outside {runs top-level field, config.<key>, approved metric id} is refused."""
        metric_id = self._propose_metric("acc4", "acc4key")
        self.sb.rl_ok("eval", "approve", metric_id, "--quote", "gyb said so")
        before = self.sb.count("evaluations")
        r = self.sb.rl("eval", "propose", "--kind", "figure", "--name", "fig2",
                       "--definition", "accuracy by nonsense", "--group-by", "not.a.real.domain",
                       "--x", "config.params", "--y", metric_id, "--uses", metric_id,
                       "--applies-to", "track probe", session=self.analysis)
        self.assertEqual(r.rc, 2, str(r))
        self.assertEqual(r.kind, "validation")
        self.assertEqual(self.sb.count("evaluations"), before)

    def test_approve_multiple_ids_one_quote(self):
        """03 L172; 05 command table: one approve call takes several ids and one quote."""
        id1 = self._propose_metric("m1", "k1")
        id2 = self._propose_metric("m2", "k2")
        self.sb.rl_ok("eval", "approve", id1, id2, "--quote", "both good")
        row1 = self.sb.latest("evaluations", id1)
        row2 = self.sb.latest("evaluations", id2)
        self.assertEqual(row1["status"], "approved")
        self.assertEqual(row2["status"], "approved")
        self.assertEqual(row1["quote"], "both good")
        self.assertEqual(row2["quote"], "both good")

    def test_retire_is_gyb_only(self):
        """05 command table (2026-08-17 definite): rl eval retire is gyb only, analysis gets exit 3."""
        eval_id = self._propose_metric("m3", "k3")
        self.sb.rl_ok("eval", "approve", eval_id, "--quote", "ok")
        denied = self.sb.rl("eval", "retire", eval_id, session=self.analysis)
        self.assertEqual(denied.rc, 3, str(denied))
        self.assertEqual(denied.kind, "forbidden")
        self.assertEqual(self.sb.latest("evaluations", eval_id)["status"], "approved")
        self.sb.rl_ok("eval", "retire", eval_id)
        self.assertEqual(self.sb.latest("evaluations", eval_id)["status"], "retired")

    def test_applies_to_is_required(self):
        """03 L164; 30 L148: applies_to is free text, not parsed, but required."""
        before = self.sb.count("evaluations")
        r = self.sb.rl("eval", "propose", "--kind", "metric", "--name", "m4",
                       "--definition", "d4", "--metrics-key", "k4", session=self.analysis)
        self.assertEqual(r.rc, 2, str(r))
        self.assertEqual(r.kind, "validation")
        self.assertEqual(self.sb.count("evaluations"), before)


if __name__ == "__main__":
    unittest.main()
