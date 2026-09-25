"""The numbers an eval run reports, on synthetic prediction rows and no GPU: the softmax and the
temperature fit, the first crossing per event and the aggregate over it, the bootstrap interval,
the generator match rule, and the whole classifier report (theta chosen on val under each risk
target, frozen on test, one heartbeat per pass)."""
# venv: probe
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import polars as pl

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from data.environments import open_env
from eval.utils import probe_eval as pe
from experimental_settings.schema import THETA_GRID

LABELS = ["apis.a.x", "apis.a.y", "apis.a.z"]


class _Beats:
    def __init__(self):
        self.beats: list[tuple[int, int, str]] = []

    def emit(self, done, total, kind):
        self.beats.append((done, total, kind))


def _cfg(risk=(0.10, 0.05), bootstrap=50):
    return SimpleNamespace(eval=SimpleNamespace(theta_grid=list(THETA_GRID), risk=list(risk),
                                                bootstrap=bootstrap, bootstrap_seed=42))


def _predictions(n_events: int = 120, seed: int = 0) -> pl.DataFrame:
    """Three cuts per event; the true label's logit grows with depth, so later cuts are surer."""
    rng = np.random.default_rng(seed)
    rows = []
    for e in range(n_events):
        split = ("val", "test")[e % 2]
        target = int(rng.integers(len(LABELS)))
        for c, depth in enumerate((0.25, 0.5, 1.0)):
            logits = rng.normal(0.0, 1.0, len(LABELS))
            logits[target] += 4.0 * depth
            rows.append(dict(event_id=f"t{e}__s42|s0", task_id=f"t{e // 4}", split=split,
                             example_id=f"t{e}__s42|s0|c{c}", depth=depth,
                             target=LABELS[target], logits=logits.tolist()))
    return pl.DataFrame(rows)


class SoftmaxAndTemperatureTest(unittest.TestCase):

    def test_softmax_rows_sum_to_one_and_survive_large_logits(self):
        p = pe.softmax(np.array([[1000.0, 1001.0, 999.0], [0.0, 0.0, 0.0]]), 1.0)
        np.testing.assert_allclose(p.sum(axis=1), [1.0, 1.0])
        np.testing.assert_allclose(p[1], [1 / 3] * 3)
        self.assertTrue(np.isfinite(p).all())

    def test_temperature_flattens(self):
        z = np.array([[2.0, 0.0]])
        self.assertGreater(pe.softmax(z, 0.5)[0, 0], pe.softmax(z, 1.0)[0, 0])
        self.assertLess(pe.softmax(z, 4.0)[0, 0], pe.softmax(z, 1.0)[0, 0])

    def test_fit_recovers_a_known_temperature(self):
        rng = np.random.default_rng(1)
        z = rng.normal(0.0, 3.0, (20000, 5))
        for true_t in (0.5, 2.0):
            with self.subTest(true_t=true_t):
                p = pe.softmax(z, true_t)
                y = np.array([rng.choice(5, p=row) for row in p])
                fitted = pe.fit_temperature(z, y)
                self.assertAlmostEqual(fitted, true_t, delta=0.1 * true_t)
                self.assertEqual(fitted, pe.fit_temperature(z, y), "the fit is deterministic")


class CrossingTest(unittest.TestCase):

    def _frame(self):
        return pl.DataFrame(dict(
            event_id=["e1", "e1", "e1", "e2", "e2", "e3"],
            task_id=["t1", "t1", "t1", "t1", "t1", "t2"],
            split=["val"] * 6,
            example_id=["e1c2", "e1c0", "e1c1", "e2c0", "e2c1", "e3c0"],
            depth=[1.0, 0.2, 0.6, 0.5, 1.0, 1.0],
            conf=[0.99, 0.4, 0.9, 0.95, 0.97, 0.3],
            label_pred=["x", "y", "x", "y", "x", "x"],
            target=["x", "x", "x", "x", "x", "x"],
        ))

    def test_first_crossing_takes_the_shallowest_cut_over_theta(self):
        recs = pe._first_crossing(self._frame(), 0.85).sort("event_id")
        self.assertEqual(recs["fired"].to_list(), [True, True, False])
        self.assertEqual(recs["example_id"].to_list(), ["e1c1", "e2c0", None])
        self.assertEqual(recs["ok"].to_list(), [True, False, False])

    def test_aggregate_by_hand(self):
        a = pe._agg(pe._first_crossing(self._frame(), 0.85))
        self.assertEqual(a, {"n": 3, "coverage": round(2 / 3, 4), "trig_acc": 0.5,
                             "earliness": round(1 - (0.6 + 0.5) / 2, 4), "wrong_spec": round(1 / 3, 4)})

    def test_nothing_fires_above_every_conf(self):
        a = pe._agg(pe._first_crossing(self._frame(), 0.999))
        self.assertEqual((a["coverage"], a["trig_acc"], a["earliness"], a["wrong_spec"]), (0.0, 0.0, 0.0, 0.0))


class BootstrapTest(unittest.TestCase):

    def test_seeded_bounds_are_ordered_and_reproducible(self):
        df = pl.DataFrame(dict(task_id=[f"t{i % 10}" for i in range(50)], v=[float(i % 7) for i in range(50)]))
        stat = lambda d: {"mean": float(d["v"].mean()), "one": 1.0}
        a = pe.bootstrap_ci(df, "task_id", stat, n=200, seed=7)
        self.assertEqual(a, pe.bootstrap_ci(df, "task_id", stat, n=200, seed=7))
        self.assertLessEqual(a["mean"][0], a["mean"][1])
        self.assertLessEqual(a["mean"][0], float(df["v"].mean()))
        self.assertGreaterEqual(a["mean"][1], float(df["v"].mean()))
        self.assertEqual(a["one"], [1.0, 1.0])


class MatchTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.env = open_env("appworld")

    def test_ctool_is_name_equality(self):
        self.assertTrue(pe.match_ctool("apis.a.b", "apis.a.b", None))
        self.assertFalse(pe.match_ctool("apis.a.b", "apis.a.c", None))

    def test_quoting_does_not_matter(self):
        m = pe.match_cgen("apis.phone.search(query='Joe', page=0)", 'apis.phone.search(query="Joe", page=0)', self.env)
        self.assertEqual(m, {"tool_ok": True, "params_all_ok": True, "full_call_ok": True})

    def test_wrong_value_extra_argument_and_wrong_tool(self):
        target = "apis.phone.search(query='Joe')"
        self.assertEqual(pe.match_cgen("apis.phone.search(query='Ann')", target, self.env),
                         {"tool_ok": True, "params_all_ok": False, "full_call_ok": False})
        self.assertFalse(pe.match_cgen("apis.phone.search(query='Joe', page=1)", target, self.env)["params_all_ok"])
        self.assertEqual(pe.match_cgen("apis.phone.find(query='Joe')", target, self.env),
                         {"tool_ok": False, "params_all_ok": True, "full_call_ok": False})
        noarg = pe.match_cparam("apis.a.b(x=1)", "apis.a.b()", self.env)
        self.assertFalse(noarg["params_all_ok"], "a spurious argument on a no-argument target counts wrong")

    def test_unparsable_prediction_scores_zero_and_unparsable_target_raises(self):
        self.assertEqual(pe.match_cgen("I think apis.a.b(x=", "apis.a.b(x=1)", self.env),
                         {"tool_ok": False, "params_all_ok": False, "full_call_ok": False})
        with self.assertRaises(ValueError):
            pe.match_cgen("apis.a.b(x=1)", "not a call", self.env)


class ClassifierReportTest(unittest.TestCase):

    def test_report_on_synthetic_predictions(self):
        pred = _predictions()
        cfg, hb = _cfg(), _Beats()
        fields, fires = pe.report_classifier("ctool", pred, cfg, None, LABELS, hb)

        total = pe.report_passes("ctool", cfg)
        self.assertEqual(len(hb.beats), total)
        self.assertEqual([b[0] for b in hb.beats], list(range(1, total + 1)))
        self.assertTrue(all(b[1] == total for b in hb.beats))

        self.assertGreater(fields["temperature"], 0)
        self.assertEqual([g["theta"] for g in fields["grid"]], list(THETA_GRID))
        self.assertEqual(fields["n_events"], {"val": 60, "test": 60})
        for g in fields["grid"]:
            self.assertEqual(g["n"], 60)
        coverages = [g["coverage"] for g in fields["grid"]]
        self.assertEqual(coverages, sorted(coverages, reverse=True), "a higher theta never fires more")

        for risk in cfg.eval.risk:
            theta = fields["chosen"][str(risk)]
            with self.subTest(risk=risk):
                ok = [g for g in fields["grid"] if g["trig_acc"] >= 1 - risk and g["coverage"] > 0]
                if not ok:
                    self.assertIsNone(theta)
                    self.assertNotIn(str(risk), fields["frozen"])
                    continue
                self.assertEqual(theta, max(ok, key=lambda g: g["coverage"])["theta"])
                frozen = fields["frozen"][str(risk)]
                self.assertEqual(frozen["n"], 60)
                for name in ("coverage", "trig_acc", "earliness"):
                    lo, hi = frozen["ci"][name]
                    self.assertLessEqual(lo, hi)
                mine = fires.filter(pl.col("risk") == pl.lit(risk, dtype=pl.Float32))
                self.assertTrue((mine["score"] >= np.float32(theta)).all())
                self.assertEqual(mine["event_id"].n_unique(), mine.height, "one fire per event")
        self.assertEqual(fires.columns, list(pe.FIRES_SCHEMA))

    def test_refusals(self):
        pred = _predictions(8)
        with self.assertRaisesRegex(ValueError, "not in labels"):
            pe.report_classifier("ctool", pred, _cfg(), None, LABELS[:1], _Beats())
        with self.assertRaisesRegex(ValueError, "val"):
            pe.report_classifier("ctool", pred.filter(pl.col("split") == "test"), _cfg(), None, LABELS, _Beats())

    def test_generator_pass_count(self):
        self.assertEqual(pe.report_passes("cgen", _cfg(risk=(0.1, 0.05, 0.01))), 6)
        self.assertEqual(pe.report_passes("ctool", _cfg(risk=(0.1, 0.1))), len(THETA_GRID) + 3)


if __name__ == "__main__":
    unittest.main()
