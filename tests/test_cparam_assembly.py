"""cparam 格的拼串单测:训练侧的目标串推导 + 评测侧的重组与解析。

训练侧:`param_target` 是 cparam 格唯一的拼串规则,拼错了训练目标就整体偏一格,
而且不报错。评测侧:eval_causal_param 拿 given + "(" + 生成串 重组后判分,
重组必须是 param_target 的逆运算,解析(parse_call/split_named_raw)的口径
在这里钉死——包括"括号配平不认引号"这条既有判分口径(记录现状,不改判分)。

跑法(train_causal_param 顶上 import torch/transformers,所以要 cprobe-env):
  cprobe-env/bin/python -m unittest tests.test_cparam_assembly -v
系统 python3 跑全量 discover 时本模块整体 skip(没有 torch),不算失败;
mbert-env(transformers 4.57.6)下 train_causal_param 抛 SystemExit 不是
ImportError,一并兜住照样 skip。
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline/train"))
sys.path.insert(0, str(ROOT / "pipeline/eval"))
try:
    from train_causal_param import (CALL_SEP, param_prompt_tail,  # noqa: E402
                                    param_target)
    from train_causal_callgen import CALL_SEP as CGEN_CALL_SEP    # noqa: E402
    import eval_causal_param as ecp                               # noqa: E402
except ImportError as e:                      # 系统 python3 没有 torch
    raise unittest.SkipTest(f"要 cprobe-env 解释器:{e}")
except SystemExit as e:                       # mbert-env 的 transformers<5.14
    raise unittest.SkipTest(f"要 cprobe-env 解释器:{e}")

sys.path.insert(0, str(ROOT / "pipeline/annotate"))
from build import make_call  # noqa: E402


class TestParamTarget(unittest.TestCase):
    def test_named_args(self):
        label = "apis.spotify.login"
        call = "apis.spotify.login(username=x, password=y)"
        self.assertEqual(param_target(label, call), "username=x, password=y)")

    def test_no_args(self):
        label = "apis.phone.logout"
        self.assertEqual(param_target(label, "apis.phone.logout()"), ")")

    def test_prefix_mismatch_returns_none(self):
        # 工具名对不上(数据串味 / 上游改了拼串规则)
        self.assertIsNone(param_target("apis.spotify.login",
                                       "apis.spotify.logout(a=1)"))
        # 少了左括号
        self.assertIsNone(param_target("apis.spotify.login",
                                       "apis.spotify.login"))
        # 工具名是真值的前缀但不是同一个名字(startswith 的经典陷阱)
        self.assertIsNone(param_target("send", "send_email(to=a)"))

    def test_roundtrip_against_make_call(self):
        """唯一拼串真源是 build.make_call:工具名 + "(" + 目标 == label_call。"""
        cases = [
            ("apis.spotify.login",
             [dict(key="username", value="x"), dict(key="password", value="y")]),
            ("apis.phone.logout", []),
            ("apis.gmail.send_email",
             [dict(key="body", value='hi, there (really)')]),
        ]
        for tool, named in cases:
            call = make_call(tool, named)
            tgt = param_target(tool, call)
            self.assertIsNotNone(tgt, call)
            self.assertEqual(tool + "(" + tgt, call)
            self.assertTrue(tgt.endswith(")"), tgt)

    def test_prompt_tail(self):
        self.assertEqual(param_prompt_tail("apis.spotify.login"),
                         CALL_SEP + "apis.spotify.login(")
        self.assertEqual(CALL_SEP, "\n[CALL] ")


class TestEvalSideReassembly(unittest.TestCase):
    """评测侧重组与训练侧剥离的两文件契约,加评测侧解析的真打用例。"""

    def test_reassembly_contract(self):
        """契约:given + "(" + gen == label_call 当且仅当
        gen == param_target(label, label_call)。评测侧 score_points 的重组串
        (eval_causal_param.py)与训练侧的目标剥离必须互为逆运算。"""
        cases = [
            ("apis.spotify.login",
             [dict(key="username", value="x"), dict(key="password", value="y")]),
            ("apis.phone.logout", []),
            ("apis.gmail.send_email",
             [dict(key="body", value="hi, there (really)")]),
        ]
        for tool, named in cases:
            call = make_call(tool, named)
            tgt = param_target(tool, call)
            # 正向:gen 恰是 param_target 时,重组串逐字回到 label_call
            self.assertEqual(tool + "(" + tgt, call)
            # 反向:gen 偏离 param_target 一个字,重组串就不再等于 label_call
            for wrong in (tgt + " ", "x" + tgt, tgt[:-1]):
                self.assertNotEqual(tool + "(" + wrong, call)

    def test_value_with_comma_quote_paren(self):
        """真打评测侧解析:值里带逗号/引号/嵌套括号,引号保护逗号与括号,
        切出的键值对必须一个不错(值保留未归一化原串)。"""
        full = ('apis.gmail.send_email(to=a@b.c, '
                'body="hi, there (really)", subject=\'x, y\')')
        tool, raw = ecp.parse_call(full, "appworld")
        self.assertEqual(tool, "apis.gmail.send_email")
        self.assertEqual(raw, [("to", "a@b.c"),
                               ("body", '"hi, there (really)"'),
                               ("subject", "'x, y'")])

    def test_quote_blind_paren_balance_is_existing_convention(self):
        """记录现状,不改判分:parse_call 找整调用右边界的括号配平不认引号
        (cgen 既有判分口径)。值里出现裸右括号时,截断发生在引号内那个
        右括号上,后半段整个丢掉。"""
        tool, raw = ecp.parse_call('apis.gmail.send(body="a ) b")', "appworld")
        self.assertEqual(tool, "apis.gmail.send")
        self.assertEqual(raw, [("body", '"a')])


class TestSeparatorConstants(unittest.TestCase):
    def test_three_separator_constants_agree(self):
        """三个分隔符常量互相对拍:任何一份单独改动都会静默改拼串口径。"""
        self.assertEqual(CALL_SEP, CGEN_CALL_SEP)
        self.assertEqual(CALL_SEP, ecp.FALLBACK_SEP)


if __name__ == "__main__":
    unittest.main()
