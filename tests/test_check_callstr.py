"""check_callstr.py 门禁 B 的 K 条判据(np821 计划 §4)+ §8b 补强判据测试。

门禁 B 的 unit->traj 判据被抽成纯函数 gate_b_unit_traj/parse_sample_idx
(check_callstr.py 顶层),不 import eval_causal_call/torch,本文件因此在
系统 python3 下就能跑;额外一个 skipUnless(cprobe-env 存在) 的冒烟用例确认
check_callstr.py 里被延后到 main() 内的 `from eval_causal_call import
norm, parse_call` 在 cprobe-env 下真的装得上(照 tests/test_splice_replay.py
的 cprobe-env 依赖处理惯例:那个文件整个只在 cprobe-env 下跑;这里不同,
纯函数部分脱离了 torch 依赖,只有这一个冒烟用例需要 cprobe-env)。

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
    """凑齐 gate_b_unit_traj 要的 {split: [row,...]} 形状;三堆缺省都给空表,
    用例只往需要的堆里塞行。"""
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
        # 老式无后缀文件名(K==1 口径)解析不出,不是 0。
        self.assertIsNone(C.parse_sample_idx("appworld_gptoss/appworld_123"))
        self.assertIsNone(
            C.parse_sample_idx("bfcl_q35/live_multiple_1-0-0"))
        # 数字出现在中间、不在 stem 结尾的不算(例如 unit id 本身带下划线数字)。
        self.assertIsNone(C.parse_sample_idx("appworld_gptoss/appworld_r0_x"))


class TestGateBK1Legacy(unittest.TestCase):
    """K==1(缺省 / 旧配置)必须逐字节复刻旧版判据与成功/失败文案——
    旧配置重跑 CALLSTR_CHECK.md 必须逐字节一致这条铁律落在这里。"""

    def test_single_traj_per_unit_passes_with_exact_old_string(self):
        rows = rows3(train=[("u1", "batch/appworld_u1")],
                     val=[("u2", "batch/appworld_u2")])
        ok, msg = C.gate_b_unit_traj(rows, 1)
        self.assertTrue(ok)
        self.assertEqual(msg, "2 个 unit 各对一条 traj ✓")

    def test_multi_traj_rejected_with_exact_old_string(self):
        rows = rows3(train=[("u1", "batch/appworld_u1"),
                            ("u1", "batch/appworld_u1_dup")])
        ok, msg = C.gate_b_unit_traj(rows, 1)
        self.assertFalse(ok)
        self.assertEqual(
            msg,
            "1 个 unit 对应多个 traj,例 "
            "[('u1', ['batch/appworld_u1', 'batch/appworld_u1_dup'])];"
            "同一模型下一个任务实例只应有一条轨迹")

    def test_default_k_is_one(self):
        # cfg.get("trajs_per_unit", 1) 的缺省值就是这里的 K=1;旧配置没有这个
        # 字段时,main() 传给 gate_b_unit_traj 的 K 恒为 1。
        rows = rows3(train=[("u1", "b/t1"), ("u1", "b/t2"), ("u1", "b/t3")])
        ok, msg = C.gate_b_unit_traj(rows, 1)
        self.assertFalse(ok)
        self.assertIn("对应多个 traj", msg)


class TestGateBKGreaterThanOne(unittest.TestCase):
    """K>1(trajs_per_unit 显式配置)的三条判据:恰好 K 条、§8b 互异补强、
    §8b 采样序号 {0..K-1} 补强。"""

    def _rows(self, unit="u1", batch="appworld_gptoss", suffixes=(0, 1, 2, 3)):
        return rows3(train=[(unit, f"{batch}/appworld_{unit}_r{k}")
                            for k in suffixes])

    def test_exact_k_passes(self):
        rows = self._rows()
        ok, msg = C.gate_b_unit_traj(rows, 4)
        self.assertTrue(ok)
        self.assertEqual(msg, "1 个 unit 各对恰好 4 条 traj ✓")

    def test_multi_unit_all_exact_k_passes(self):
        rows = rows3(train=[(u, f"appworld_gptoss/appworld_{u}_r{k}")
                            for u in ("u1", "u2", "u3") for k in range(4)])
        ok, msg = C.gate_b_unit_traj(rows, 4)
        self.assertTrue(ok)
        self.assertEqual(msg, "3 个 unit 各对恰好 4 条 traj ✓")

    def test_three_trajs_rejected(self):
        rows = self._rows(suffixes=(0, 1, 2))
        ok, msg = C.gate_b_unit_traj(rows, 4)
        self.assertFalse(ok)
        self.assertIn("条数不是 trajs_per_unit=4", msg)
        self.assertIn("u1", msg)
        self.assertIn("(3,", msg)          # 实际条数(3)显式带在错误信息里

    def test_five_trajs_rejected(self):
        rows = self._rows(suffixes=(0, 1, 2, 3, 4))
        ok, msg = C.gate_b_unit_traj(rows, 4)
        self.assertFalse(ok)
        self.assertIn("条数不是 trajs_per_unit=4", msg)
        self.assertIn("u1", msg)
        self.assertIn("(5,", msg)          # 实际条数(5)显式带在错误信息里

    def test_shifted_indices_rejected(self):
        # 条数对(4 条互异 traj),但采样序号是 {1,2,3,4} 不是 {0,1,2,3}。
        rows = self._rows(suffixes=(1, 2, 3, 4))
        ok, msg = C.gate_b_unit_traj(rows, 4)
        self.assertFalse(ok)
        self.assertIn("采样序号不是", msg)
        self.assertIn("u1", msg)

    def test_missing_suffix_rejected_with_clear_message(self):
        # 一条老式无后缀 + 三条新式 _r1.._r3:条数对但混了没有采样序号的文件名。
        rows = rows3(train=[
            ("u1", "appworld_gptoss/appworld_u1"),
            ("u1", "appworld_gptoss/appworld_u1_r1"),
            ("u1", "appworld_gptoss/appworld_u1_r2"),
            ("u1", "appworld_gptoss/appworld_u1_r3")])
        ok, msg = C.gate_b_unit_traj(rows, 4)
        self.assertFalse(ok)
        self.assertIn("不带采样序号", msg)
        self.assertIn("u1", msg)

    def test_k2_exact_passes(self):
        # K 不止 4 这一个值也要过。
        rows = self._rows(suffixes=(0, 1))
        ok, msg = C.gate_b_unit_traj(rows, 2)
        self.assertTrue(ok)
        self.assertEqual(msg, "1 个 unit 各对恰好 2 条 traj ✓")


class TestCprobeSmoke(unittest.TestCase):
    """本文件其余用例都在系统 python3 下跑;这条另外用子进程确认整个模块、
    以及 main() 里延后 import 的 eval_causal_call,在 cprobe-env 下真的装得上
    (check_callstr.py 顶层不再 import 它,只在 main() 用到的地方才 import——
    这条冒烟就是钉住那次延后 import 没有被写坏)。"""

    @unittest.skipUnless(CPROBE_PY.exists(), "cprobe-env 不在这台机器上")
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
