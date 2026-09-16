import unittest
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "ops"))
import verdicts as V


def p(**kw):
    """Default state for a batch piece; overridden per cell in the unit tests."""
    base = dict(kind="batch", alive=True, done=5, total=100, status=None,
                has_beat=True, beat_age_s=10.0, since_launch_s=600.0,
                stall_s=180.0, escalate_s=None, warmup_s=1800.0,
                avg_rate=1.0, recent_rate=1.0,
                port_ok=None, port_ever_ok=False, port_fail_rounds=0)
    base.update(kw)
    return base


class TestJudge(unittest.TestCase):
    def test_done_beats_everything(self):        # priority 1: done overrides alive
        self.assertEqual(V.judge(p(done=100))[0], V.V_DONE)
        self.assertEqual(V.judge(p(alive=False, status="done", done=3))[0],
                         V.V_DONE)

    def test_dead(self):                          # priority 2: zero heartbeats means dead
        v, esc = V.judge(p(alive=False))
        self.assertEqual(v, V.V_DEAD)
        self.assertTrue(esc)                      # dead immediately hits the escalation line
        v, _ = V.judge(p(alive=False, has_beat=False, done=None, total=None))
        self.assertEqual(v, V.V_DEAD)

    def test_stall_and_escalate(self):            # priority 3 + escalation line
        v, esc = V.judge(p(beat_age_s=200.0))     # stalled 200s > verdict line 180s
        self.assertEqual(v, V.V_STALL)
        self.assertFalse(esc)                     # has not passed 180×3
        v, esc = V.judge(p(beat_age_s=600.0))
        self.assertEqual(v, V.V_STALL)
        self.assertTrue(esc)

    def test_warmup_and_warmup_timeout(self):     # priority 4 + cap
        self.assertEqual(V.judge(p(has_beat=False, since_launch_s=300.0))[0],
                         V.V_WARMUP)
        v, _ = V.judge(p(has_beat=False, since_launch_s=2000.0))
        self.assertEqual(v, V.V_STALL)            # past the warm-up cap, turns into suspected stall

    def test_stall_line_fallback_when_few_intervals(self):
        # not enough interval samples: stall_s=None, a long first question doesn't false-alarm (stalled 400s < warmup 1800s)
        self.assertEqual(V.judge(p(stall_s=None, beat_age_s=400.0))[0], V.V_OK)

    def test_slow_needs_recent_rate(self):        # priority 5
        self.assertEqual(V.judge(p(recent_rate=0.4))[0], V.V_SLOW)
        self.assertEqual(V.judge(p(recent_rate=None))[0], V.V_OK)

    def test_probe_fail_keeps_previous_alive(self):
        # alive=None (unknown after probe-failure conversion) is not judged dead
        self.assertNotEqual(V.judge(p(alive=None))[0], V.V_DEAD)

    def test_service(self):
        s = dict(kind="service", alive=True, done=None, total=None, status=None,
                 has_beat=False, beat_age_s=0.0, since_launch_s=120.0,
                 stall_s=None, escalate_s=None, warmup_s=1800.0,
                 avg_rate=None, recent_rate=None,
                 port_ok=False, port_ever_ok=False, port_fail_rounds=0)
        self.assertEqual(V.judge(s)[0], V.V_WARMUP)          # port has never answered
        s.update(port_ok=True, port_ever_ok=True)
        self.assertEqual(V.judge(s)[0], V.V_OK)
        s.update(port_ok=False, port_fail_rounds=3)
        self.assertEqual(V.judge(s)[0], V.V_STALL)           # 3 consecutive rounds without a response
        s.update(alive=False)
        # dead immediately hits the escalation line (same as batch); I5 (final-review):
        # assert the whole pair, not just the verdict value -- missing the escalated
        # half, this regression would not catch it.
        self.assertEqual(V.judge(s), (V.V_DEAD, True))

    def test_service_never_answered_past_warmup_is_stall(self):
        # port has never answered (port_ever_ok=False) and past the warm-up cap: suspected
        # stall, has not passed the escalation line (2000 < 1800×3=5400) so escalated=False.
        s = dict(kind="service", alive=True, done=None, total=None, status=None,
                 has_beat=False, beat_age_s=0.0, since_launch_s=2000.0,
                 stall_s=None, escalate_s=None, warmup_s=1800.0,
                 avg_rate=None, recent_rate=None,
                 port_ok=False, port_ever_ok=False, port_fail_rounds=0)
        self.assertEqual(V.judge(s), (V.V_STALL, False))

    def test_service_answered_before_recent_failures_under_threshold_ok(self):
        # has answered before (port_ever_ok=True), this round fails, but the count of
        # consecutive failed rounds (1 or 2) has not reached port_fail_rounds' floor (3) --
        # healthy, must not alarm early.
        for n in (1, 2):
            s = dict(kind="service", alive=True, done=None, total=None,
                     status=None, has_beat=False, beat_age_s=0.0,
                     since_launch_s=600.0, stall_s=None, escalate_s=None,
                     warmup_s=1800.0, avg_rate=None, recent_rate=None,
                     port_ok=False, port_ever_ok=True, port_fail_rounds=n)
            self.assertEqual(V.judge(s), (V.V_OK, False))


class TestLinesAndRates(unittest.TestCase):
    def test_typical_gap_median(self):
        ts = [0, 10, 20, 30, 100]                 # intervals 10,10,10,70 -> median 10
        self.assertEqual(V.typical_gap_s(ts), 10)

    def test_stall_line_floor(self):
        ts = [0, 1, 2, 3, 4]                      # dense heartbeats: 5×1s < 3×60s floor
        self.assertEqual(V.stall_line_s(ts), 180.0)
        self.assertEqual(V.stall_line_s(ts, override=42.0), 42.0)
        self.assertIsNone(V.stall_line_s([0, 10]))  # only 1 interval -> None

    def test_stall_line_uses_mult_when_above_floor(self):
        # I5 (final-review): the other branch of the verdict line's main formula was untested --
        # with a typical interval of 60s, 5×60=300 > 3×60=180 floor, the verdict line should
        # take the stall_mult branch, not the floor.
        ts = [0, 60, 120, 180]                    # all intervals 60s, median 60
        self.assertEqual(V.stall_line_s(ts), 300.0)

    def test_rates(self):
        first = {"ts": 0.0, "done": 0}
        recent = [{"ts": 100.0 + i * 10, "done": 50 + i} for i in range(5)]
        avg, rc = V.rates(first, recent)
        self.assertAlmostEqual(avg, 54 / 140.0)   # (54-0)/(140-0)
        self.assertAlmostEqual(rc, 4 / 40.0)      # Δdone/Δts within the view
        self.assertEqual(V.rates(first, recent[:1]), ((50 - 0) / 100.0, None))
        self.assertEqual(V.rates(None, []), (None, None))


if __name__ == "__main__":
    unittest.main()
