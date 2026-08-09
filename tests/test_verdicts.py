import unittest
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "ops"))
import verdicts as V


def p(**kw):
    """batch 分片的默认状态,单测里按格覆盖。"""
    base = dict(kind="batch", alive=True, done=5, total=100, status=None,
                has_beat=True, beat_age_s=10.0, since_launch_s=600.0,
                stall_s=180.0, escalate_s=None, warmup_s=1800.0,
                avg_rate=1.0, recent_rate=1.0,
                port_ok=None, port_ever_ok=False, port_fail_rounds=0)
    base.update(kw)
    return base


class TestJudge(unittest.TestCase):
    def test_done_beats_everything(self):        # 优先级 1:已完成压过活着
        self.assertEqual(V.judge(p(done=100))[0], V.V_DONE)
        self.assertEqual(V.judge(p(alive=False, status="done", done=3))[0],
                         V.V_DONE)

    def test_dead(self):                          # 优先级 2:含零心跳就死的
        v, esc = V.judge(p(alive=False))
        self.assertEqual(v, V.V_DEAD)
        self.assertTrue(esc)                      # 已挂当场达升级线
        v, _ = V.judge(p(alive=False, has_beat=False, done=None, total=None))
        self.assertEqual(v, V.V_DEAD)

    def test_stall_and_escalate(self):            # 优先级 3 + 升级线
        v, esc = V.judge(p(beat_age_s=200.0))     # 停摆 200s > 判定线 180s
        self.assertEqual(v, V.V_STALL)
        self.assertFalse(esc)                     # 未过 180×3
        v, esc = V.judge(p(beat_age_s=600.0))
        self.assertEqual(v, V.V_STALL)
        self.assertTrue(esc)

    def test_warmup_and_warmup_timeout(self):     # 优先级 4 + 上限
        self.assertEqual(V.judge(p(has_beat=False, since_launch_s=300.0))[0],
                         V.V_WARMUP)
        v, _ = V.judge(p(has_beat=False, since_launch_s=2000.0))
        self.assertEqual(v, V.V_STALL)            # 超 warm-up 上限转疑似卡死

    def test_stall_line_fallback_when_few_intervals(self):
        # 间隔样本不足:stall_s=None,长首题不误报(停摆 400s < warmup 1800s)
        self.assertEqual(V.judge(p(stall_s=None, beat_age_s=400.0))[0], V.V_OK)

    def test_slow_needs_recent_rate(self):        # 优先级 5
        self.assertEqual(V.judge(p(recent_rate=0.4))[0], V.V_SLOW)
        self.assertEqual(V.judge(p(recent_rate=None))[0], V.V_OK)

    def test_probe_fail_keeps_previous_alive(self):
        # alive=None(探测失败折算后未知)不判已挂
        self.assertNotEqual(V.judge(p(alive=None))[0], V.V_DEAD)

    def test_service(self):
        s = dict(kind="service", alive=True, done=None, total=None, status=None,
                 has_beat=False, beat_age_s=0.0, since_launch_s=120.0,
                 stall_s=None, escalate_s=None, warmup_s=1800.0,
                 avg_rate=None, recent_rate=None,
                 port_ok=False, port_ever_ok=False, port_fail_rounds=0)
        self.assertEqual(V.judge(s)[0], V.V_WARMUP)          # 端口还没应答过
        s.update(port_ok=True, port_ever_ok=True)
        self.assertEqual(V.judge(s)[0], V.V_OK)
        s.update(port_ok=False, port_fail_rounds=3)
        self.assertEqual(V.judge(s)[0], V.V_STALL)           # 连续 3 轮不应答
        s.update(alive=False)
        # 已挂当场达升级线(与 batch 一样),I5(final-review):断言整个二元组
        # 而不是只看判定值,漏了 escalated 这半这条回归会跑不出来。
        self.assertEqual(V.judge(s), (V.V_DEAD, True))

    def test_service_never_answered_past_warmup_is_stall(self):
        # 端口从未应答过(port_ever_ok=False)且超过 warm-up 上限:疑似卡死,
        # 还没过升级线(2000 < 1800×3=5400)所以 escalated=False。
        s = dict(kind="service", alive=True, done=None, total=None, status=None,
                 has_beat=False, beat_age_s=0.0, since_launch_s=2000.0,
                 stall_s=None, escalate_s=None, warmup_s=1800.0,
                 avg_rate=None, recent_rate=None,
                 port_ok=False, port_ever_ok=False, port_fail_rounds=0)
        self.assertEqual(V.judge(s), (V.V_STALL, False))

    def test_service_answered_before_recent_failures_under_threshold_ok(self):
        # 曾经应答过(port_ever_ok=True),当前这一轮失败,但连续失败轮数
        # (1 或 2)还没到 port_fail_rounds 的下限(3)——健康,不许提前报警。
        for n in (1, 2):
            s = dict(kind="service", alive=True, done=None, total=None,
                     status=None, has_beat=False, beat_age_s=0.0,
                     since_launch_s=600.0, stall_s=None, escalate_s=None,
                     warmup_s=1800.0, avg_rate=None, recent_rate=None,
                     port_ok=False, port_ever_ok=True, port_fail_rounds=n)
            self.assertEqual(V.judge(s), (V.V_OK, False))


class TestLinesAndRates(unittest.TestCase):
    def test_typical_gap_median(self):
        ts = [0, 10, 20, 30, 100]                 # 间隔 10,10,10,70 -> 中位 10
        self.assertEqual(V.typical_gap_s(ts), 10)

    def test_stall_line_floor(self):
        ts = [0, 1, 2, 3, 4]                      # 密心跳:5×1s < 3×60s 下限
        self.assertEqual(V.stall_line_s(ts), 180.0)
        self.assertEqual(V.stall_line_s(ts, override=42.0), 42.0)
        self.assertIsNone(V.stall_line_s([0, 10]))  # 只有 1 个间隔 -> None

    def test_stall_line_uses_mult_when_above_floor(self):
        # I5(final-review):判定线主公式的另一支没测过——典型间隔 60s 时
        # 5×60=300 > 3×60=180 下限,判定线该走 stall_mult 那一支,不是下限。
        ts = [0, 60, 120, 180]                    # 间隔全 60s,中位 60
        self.assertEqual(V.stall_line_s(ts), 300.0)

    def test_rates(self):
        first = {"ts": 0.0, "done": 0}
        recent = [{"ts": 100.0 + i * 10, "done": 50 + i} for i in range(5)]
        avg, rc = V.rates(first, recent)
        self.assertAlmostEqual(avg, 54 / 140.0)   # (54-0)/(140-0)
        self.assertAlmostEqual(rc, 4 / 40.0)      # 窗口内 Δdone/Δts
        self.assertEqual(V.rates(first, recent[:1]), ((50 - 0) / 100.0, None))
        self.assertEqual(V.rates(None, []), (None, None))


if __name__ == "__main__":
    unittest.main()
