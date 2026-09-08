"""check_callstr.py gate B's K criteria (np821 plan §4) + tests for the §8b reinforcement
criterion.

Gate B's unit->traj criterion has been pulled out into pure functions gate_b_unit_traj/
parse_sample_idx (top level of check_callstr.py), which do not import eval_causal_call/torch, so
this file can run under the system python3; one extra skipUnless(cprobe-env exists) smoke test
confirms that `from eval_causal_call import norm, parse_call`, deferred inside main() in
check_callstr.py, really does install under cprobe-env (following the cprobe-env dependency
convention of tests/test_splice_replay.py: that file runs only under cprobe-env in its entirety;
here it's different -- the pure-function part has been freed from the torch dependency, and only
this one smoke test needs cprobe-env).

    python3 -m unittest tests.test_check_callstr -v
    cprobe-env/bin/python -m unittest tests.test_check_callstr -v
"""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline" / "annotate"))

import check_callstr as C                               # noqa: E402

CPROBE_PY = ROOT / "cprobe-env" / "bin" / "python"


def mkrow(unit, traj):
    return {"unit": unit, "traj": traj}


def rows3(train=(), val=(), test=()):
    """Assemble the {split: [row,...]} shape gate_b_unit_traj needs; all three piles
    default to empty tables, the test case only puts rows into the piles it needs."""
    return {"train": [mkrow(*r) for r in train],
            "val": [mkrow(*r) for r in val],
            "test": [mkrow(*r) for r in test]}


class TestParseSampleIdx(unittest.TestCase):
    def test_parses_trailing_rk(self):
        self.assertEqual(
            C.parse_sample_idx("appworld_gptoss/appworld_123_r0"), 0)
        self.assertEqual(
            C.parse_sample_idx("appworld_gptoss/appworld_123_r3"), 3)
        self.assertEqual(
            C.parse_sample_idx("appworld_gptoss/appworld_123_r12"), 12)

    def test_none_when_no_suffix(self):
        # Old-style filenames without a suffix (K==1 convention) don't parse, not 0.
        self.assertIsNone(C.parse_sample_idx("appworld_gptoss/appworld_123"))
        self.assertIsNone(
            C.parse_sample_idx("bfcl_q35/live_multiple_1-0-0"))
        # A number that appears in the middle, not at the end of the stem, doesn't count (e.g. the unit id itself has underscore-digits).
        self.assertIsNone(C.parse_sample_idx("appworld_gptoss/appworld_r0_x"))


class TestGateBK1Legacy(unittest.TestCase):
    """K==1 (default / old config) must byte-for-byte replicate the old criteria and
    success/failure text -- this is where the hard rule that rerunning an old config
    must match CALLSTR_CHECK.md byte-for-byte lands."""

    def test_single_traj_per_unit_passes_with_exact_old_string(self):
        rows = rows3(train=[("u1", "batch/appworld_u1")],
                     val=[("u2", "batch/appworld_u2")])
        ok, msg = C.gate_b_unit_traj(rows, 1)
        self.assertTrue(ok)
        self.assertEqual(msg, "2 units each map to one traj ✓")

    def test_multi_traj_rejected_with_exact_old_string(self):
        rows = rows3(train=[("u1", "batch/appworld_u1"),
                            ("u1", "batch/appworld_u1_dup")])
        ok, msg = C.gate_b_unit_traj(rows, 1)
        self.assertFalse(ok)
        self.assertEqual(
            msg,
            "1 units map to multiple trajs, e.g. "
            "[('u1', ['batch/appworld_u1', 'batch/appworld_u1_dup'])]; "
            "under the same model, one task instance should have only one trajectory")

    def test_default_k_is_one(self):
        # The default of cfg.get("trajs_per_unit", 1) is K=1 here; when an old config
        # lacks this field, the K that main() passes to gate_b_unit_traj is always 1.
        rows = rows3(train=[("u1", "b/t1"), ("u1", "b/t2"), ("u1", "b/t3")])
        ok, msg = C.gate_b_unit_traj(rows, 1)
        self.assertFalse(ok)
        self.assertIn("map to multiple trajs", msg)


class TestGateBKGreaterThanOne(unittest.TestCase):
    """The three criteria for K>1 (trajs_per_unit explicitly configured): exactly K
    entries, the section 8b distinctness reinforcement, and the section 8b
    sample-index {0..K-1} reinforcement."""

    def _rows(self, unit="u1", batch="appworld_gptoss", suffixes=(0, 1, 2, 3)):
        return rows3(train=[(unit, f"{batch}/appworld_{unit}_r{k}")
                            for k in suffixes])

    def test_exact_k_passes(self):
        rows = self._rows()
        ok, msg = C.gate_b_unit_traj(rows, 4)
        self.assertTrue(ok)
        self.assertEqual(msg, "1 units each map to exactly 4 trajs ✓")

    def test_multi_unit_all_exact_k_passes(self):
        rows = rows3(train=[(u, f"appworld_gptoss/appworld_{u}_r{k}")
                            for u in ("u1", "u2", "u3") for k in range(4)])
        ok, msg = C.gate_b_unit_traj(rows, 4)
        self.assertTrue(ok)
        self.assertEqual(msg, "3 units each map to exactly 4 trajs ✓")

    def test_three_trajs_rejected(self):
        rows = self._rows(suffixes=(0, 1, 2))
        ok, msg = C.gate_b_unit_traj(rows, 4)
        self.assertFalse(ok)
        self.assertIn("isn't trajs_per_unit=4", msg)
        self.assertIn("u1", msg)
        self.assertIn("(3,", msg)          # the actual count (3) is explicitly included in the error message

    def test_five_trajs_rejected(self):
        rows = self._rows(suffixes=(0, 1, 2, 3, 4))
        ok, msg = C.gate_b_unit_traj(rows, 4)
        self.assertFalse(ok)
        self.assertIn("isn't trajs_per_unit=4", msg)
        self.assertIn("u1", msg)
        self.assertIn("(5,", msg)          # the actual count (5) is explicitly included in the error message

    def test_shifted_indices_rejected(self):
        # Count matches (4 distinct trajs), but the sample indices are {1,2,3,4}, not {0,1,2,3}.
        rows = self._rows(suffixes=(1, 2, 3, 4))
        ok, msg = C.gate_b_unit_traj(rows, 4)
        self.assertFalse(ok)
        self.assertIn("sampling indices are not", msg)
        self.assertIn("u1", msg)

    def test_missing_suffix_rejected_with_clear_message(self):
        # One old-style suffix-less entry plus three new-style _r1..r3: count matches but mixes in a filename with no sample index.
        rows = rows3(train=[
            ("u1", "appworld_gptoss/appworld_u1"),
            ("u1", "appworld_gptoss/appworld_u1_r1"),
            ("u1", "appworld_gptoss/appworld_u1_r2"),
            ("u1", "appworld_gptoss/appworld_u1_r3")])
        ok, msg = C.gate_b_unit_traj(rows, 4)
        self.assertFalse(ok)
        self.assertIn("no sampling index", msg)
        self.assertIn("u1", msg)

    def test_k2_exact_passes(self):
        # K must also pass for values other than 4.
        rows = self._rows(suffixes=(0, 1))
        ok, msg = C.gate_b_unit_traj(rows, 2)
        self.assertTrue(ok)
        self.assertEqual(msg, "1 units each map to exactly 2 trajs ✓")


class TestCprobeSmoke(unittest.TestCase):
    """The rest of the test cases in this file run under system python3; this one
    additionally uses a subprocess to confirm that the whole module, and the
    eval_causal_call deferred-imported inside main(), really do install under
    cprobe-env (check_callstr.py no longer imports it at the top level, only where
    main() uses it -- this smoke test just pins down that the deferred import
    hasn't been broken)."""

    @unittest.skipUnless(CPROBE_PY.exists(), "cprobe-env is not on this machine")
    def test_module_and_eval_causal_call_import_under_cprobe_env(self):
        code = (
            "import sys\n"
            f"sys.path.insert(0, {str(ROOT / 'pipeline' / 'annotate')!r})\n"
            f"sys.path.insert(0, {str(ROOT / 'pipeline' / 'eval')!r})\n"
            "import check_callstr\n"
            "assert check_callstr.gate_b_unit_traj is not None\n"
            "from eval_causal_call import norm, parse_call\n"
            "assert norm and parse_call\n"
            "print('cprobe-import-ok')\n"
        )
        r = subprocess.run([str(CPROBE_PY), "-c", code],
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("cprobe-import-ok", r.stdout)


if __name__ == "__main__":
    unittest.main()
