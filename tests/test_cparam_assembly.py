"""cparam 格的拼串推导单测:从 (label, label_call) 推出目标串。

只测纯字符串这一层——`param_target` 是整个 cparam 格唯一的拼串规则,拼错了
训练目标就整体偏一格,而且不报错。四类覆盖:有参、无参、值里带逗号/引号/
括号、前缀对不上。

跑法(train_causal_param 顶上 import torch/transformers,所以要 cprobe-env):
  cprobe-env/bin/python -m unittest tests.test_cparam_assembly -v
系统 python3 跑全量 discover 时本模块整体 skip(没有 torch),不算失败。
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline/train"))
try:
    from train_causal_param import (CALL_SEP, param_prompt_tail,  # noqa: E402
                                    param_target)
except ImportError as e:                      # 系统 python3 没有 torch
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

    def test_value_with_comma_quote_paren(self):
        label = "apis.gmail.send_email"
        call = ('apis.gmail.send_email(to=a@b.c, '
                'body="hi, there (really)", subject=\'x, y\')')
        self.assertEqual(
            param_target(label, call),
            'to=a@b.c, body="hi, there (really)", subject=\'x, y\')')

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


if __name__ == "__main__":
    unittest.main()
