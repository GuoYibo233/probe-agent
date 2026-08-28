"""tests/test_align_rules.py —— 对齐容差参数化 + 相对判据,对应工单
`.scratch/kvshare-train/issues/09-align-tolerance-params.md`、
spec `.scratch/kvshare-train/spec.md` 16.4(判据与键名)、16.9 第三条(测试)。

跑法(要 cprobe-env,两个训练脚本顶层都有 transformers>=5.14 版本门):
  cprobe-env/bin/python -m unittest tests.test_align_rules -v
系统 python3 跑全量 discover 时本模块整体 skip(没有 torch),不算失败;
mbert-env(transformers 4.57.6)下顶层 import 会 `SystemExit`,一并兜住照样
skip(照 `tests/test_cparam_assembly.py` 的写法)。

新训练器一段用手造的 3 个短 cgen 事件(不读 `pipeline/data/nyapass_aw_v1/
gptoss` 这种现役大目录);ctool 一段照 `tests/test_share_trainer.py` 第 59
与 625 到 632 行的做法建 `Qwen3Config` 临时模型目录,直接构造 `CausalProbe`
调 `align_check`,不走 `main()`,同样不读现役数据目录。小模型的构造复用
`tests/test_share_trainer.py` 的 `_tiny_config`/`QWEN_PATH`/`SEED`,不重复
定义一份。
"""
import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline/train"))

try:
    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer
except ImportError as e:                       # 系统 python3 没有 torch
    raise unittest.SkipTest(f"要 cprobe-env 解释器:{e}")

try:
    import train_causal_share as tcs           # noqa: E402
    import train_causal_tool as tct            # noqa: E402
except ImportError as e:                       # 系统 python3 没有 transformers
    raise unittest.SkipTest(f"要 cprobe-env 解释器:{e}")
except SystemExit as e:                        # mbert-env 的 transformers<5.14
    raise unittest.SkipTest(f"要 cprobe-env 解释器:{e}")

from tests.test_share_trainer import _tiny_config, QWEN_PATH, SEED  # noqa: E402

ALIGN_RULES = ("abs", "rel", "both")


def _write_jsonl(rows, path):
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _write_tiny_cgen_val(path):
    """3 个手造短事件(cgen 格),每事件 2 行。行 `text` 必须互为前缀
    (`share_data.load_events` 的前缀性质抽查要求)——用字符串拼接构造,
    短行的 `text` 恰是长行(事件全文)`text` 的一个前缀子串。返回事件数。"""
    bodies = [
        "Alice opens the fridge and takes out milk",
        "Bob walks to the store and buys bread",
        "Carol reads a book and writes a note",
    ]
    tails = [
        " for breakfast today.",
        " for the weekend trip.",
        " before going to sleep.",
    ]
    rows = []
    for ei, (short, tail) in enumerate(zip(bodies, tails)):
        ev = f"ev{ei}"
        full = short + tail
        rows.append(dict(event=ev, sent_idx=0, n_sents=2, text=short,
                         label="l0", label_call=f"call_{ei}_a()", w=1.0))
        rows.append(dict(event=ev, sent_idx=1, n_sents=2, text=full,
                         label="l1", label_call=f"call_{ei}_b(1)", w=1.0))
    _write_jsonl(rows, path)
    return len(bodies)


class TestAlignRulesShare(unittest.TestCase):
    """新训练器(`train_causal_share.py`)对齐容差参数化 + 相对判据,
    spec 16.4 第一条。"""

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"分词器路径不存在:{QWEN_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)
        vocab_size = len(cls.tok)
        cls.model_dir_ctx = tempfile.TemporaryDirectory()
        cls.model_dir = cls.model_dir_ctx.name
        torch.manual_seed(SEED)
        model = AutoModelForCausalLM.from_config(_tiny_config(vocab_size))
        model.save_pretrained(cls.model_dir)
        cls.tok.save_pretrained(cls.model_dir)

    @classmethod
    def tearDownClass(cls):
        cls.model_dir_ctx.cleanup()

    def setUp(self):
        self.data_dir_ctx = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.data_dir_ctx.name)
        self.n_events = _write_tiny_cgen_val(self.data_dir / "val.jsonl")
        self.out_root_ctx = tempfile.TemporaryDirectory()
        self.out_root = Path(self.out_root_ctx.name)

    def tearDown(self):
        self.data_dir_ctx.cleanup()
        self.out_root_ctx.cleanup()

    def _run_align_only(self, extra_argv, out_name):
        """走真实 CLI 入口 `tcs.main()`(`sys.argv` 打过补丁),照
        `tests/test_share_trainer.py` 的 `TestMainSmokeCPU._run_smoke` 同一个
        套路,只是这里 `--data` 指向手造的小数据目录、加 `--align-only`。"""
        out = self.out_root / out_name
        argv = ["train_causal_share.py", "--mode", "cgen",
               "--base", self.model_dir, "--data", str(self.data_dir),
               "--out", str(out), "--align-only", "--device", "cpu",
               "--align-events", str(self.n_events)] + extra_argv
        old_argv = sys.argv
        sys.argv = argv
        try:
            tcs.main()
        finally:
            sys.argv = old_argv
        return out

    def test_three_rules_pass_with_all_new_keys(self):
        """三种规则的 `ALIGN_CHECK.json` 都有全部新键,PASS 都为真——fp32
        CPU 上小模型的差是 1e-6 量级,三种规则的默认门槛都能过。"""
        for rule in ALIGN_RULES:
            with self.subTest(rule=rule):
                out = self._run_align_only(
                    ["--align-rule", rule], f"run_{rule}")
                report = json.loads((out / "ALIGN_CHECK.json").read_text())
                for key in ("rule", "tol", "tok_tol", "rel_tol", "ref_scale",
                           "rel_max_abs_diff", "bf16_mean_tol",
                           "bf16_max_tol", "baseline_factor"):
                    self.assertIn(key, report, f"{rule} 规则缺键 {key}")
                self.assertEqual(report["rule"], rule)
                self.assertTrue(
                    report["PASS"],
                    f"{rule} 规则应该 PASS(fp32 CPU 差在 1e-6 量级):{report}")

    def test_align_rel_tol_negative_fails(self):
        """`--align-rule rel --align-rel-tol -1` 必须判失败、退出码 2——
        用负数不用 0,差恰好是 0.0 时 `<= 0` 会偶发通过。"""
        with self.assertRaises(SystemExit) as cm:
            self._run_align_only(
                ["--align-rule", "rel", "--align-rel-tol", "-1"], "run_neg")
        self.assertEqual(cm.exception.code, 2)

    def test_baseline_factor_zero(self):
        """`--align-baseline-factor 0` 时 `max(0 x 基线, 1e-6)` 仍是 1e-6,
        差大于 1e-6 才告警;小模型上这个差如果小于 1e-6,退而断言
        `baseline_factor` 键忠实记录了传入值(工单 09 第 1 条最后一句)。"""
        out = self._run_align_only(
            ["--align-baseline-factor", "0"], "run_bf0")
        report = json.loads((out / "ALIGN_CHECK.json").read_text())
        self.assertEqual(report["baseline_factor"], 0.0)
        if report["max_abs_diff"] > 1e-6:
            self.assertTrue(
                report["baseline_warn"],
                f"baseline_factor=0 时差 {report['max_abs_diff']} 超过 "
                "1e-6 地板值,baseline_warn 应该为真")

    def test_run_align_check_drift_exit_has_rule_and_rel_tol(self):
        """`run_align_check` 第二条失败出口(`_ref_forward` 的参照基线自检
        失败,写的最小报告)也要带 `rule`/`rel_tol` 两个键——照
        `tests/test_share_trainer.py` 里
        `TestRunAlignCheckHandlesRefBaselineDriftError` 的做法,monkeypatch
        `_ref_forward` 直接抛 `RefBaselineDriftError`。"""
        torch.manual_seed(SEED)
        model = AutoModelForCausalLM.from_config(
            _tiny_config(len(self.tok)))
        model.eval()
        orig = tcs._ref_forward

        def _boom(*_a, **_kw):
            raise tcs.RefBaselineDriftError("测试注入的漂移")

        tcs._ref_forward = _boom
        try:
            with tempfile.TemporaryDirectory() as out_dir:
                args = argparse.Namespace(
                    data=str(self.data_dir), out=out_dir,
                    align_events=self.n_events, max_len=8192,
                    align_tol=2e-5, attn_impl="sdpa",
                    align_rule="rel", align_rel_tol=1e-5)
                with self.assertRaises(SystemExit) as cm:
                    tcs.run_align_check(model, self.tok, args, "cpu",
                                        "cgen", None)
                self.assertEqual(cm.exception.code, 2)
                report = json.loads(
                    (Path(out_dir) / "ALIGN_CHECK.json").read_text())
                self.assertEqual(report["stage"], "ref_forward_drift")
                self.assertEqual(report["rule"], "rel")
                self.assertEqual(report["rel_tol"], 1e-5)
        finally:
            tcs._ref_forward = orig


class TestAlignRulesTool(unittest.TestCase):
    """ctool(`train_causal_tool.py`)对齐容差参数化 + 相对判据,spec 16.4
    第二条。`CausalProbe.build()` 只认 `MODELS[base]`、没有 `path=` 口子
    (`train_causal_tool.py` 第 177 到 184 行),照
    `tests/test_share_trainer.py` 第 59 与 625 到 632 行的做法建
    `Qwen3Config` 临时模型目录,直接构造 `CausalProbe(<目录>, n_labels)`
    调 `align_check`,不走 `main()`,不读现役数据目录。"""

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"分词器路径不存在:{QWEN_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)
        vocab_size = len(cls.tok)
        cls.model_dir_ctx = tempfile.TemporaryDirectory()
        cls.model_dir = cls.model_dir_ctx.name
        torch.manual_seed(SEED)
        backbone_model = AutoModelForCausalLM.from_config(
            _tiny_config(vocab_size))
        backbone_model.save_pretrained(cls.model_dir)
        cls.tok.save_pretrained(cls.model_dir)
        torch.manual_seed(SEED)
        cls.probe = tct.CausalProbe(cls.model_dir, n_labels=4)
        cls.probe.eval()
        cls.text = ("Alice opens the fridge and takes out milk for "
                   "breakfast today.")

    @classmethod
    def tearDownClass(cls):
        cls.model_dir_ctx.cleanup()

    def test_three_rules_pass_with_reldiff_and_new_keys(self):
        for rule in ALIGN_RULES:
            with self.subTest(rule=rule):
                rep = tct.align_check(
                    self.probe, self.tok, self.text, 64, "cpu", "qwen",
                    self.model_dir, tol=3e-4, rule=rule, rel_tol=1e-5)
                for key in ("rule", "rel_tol", "reldiff_hidden",
                           "reldiff_logits"):
                    self.assertIn(key, rep, f"{rule} 规则缺键 {key}")
                self.assertEqual(rep["rule"], rule)
                self.assertTrue(
                    rep["PASS"],
                    f"{rule} 规则应该 PASS(fp32 CPU 差在 1e-6 量级):{rep}")

    def test_align_rel_tol_negative_fails(self):
        """`rel_tol = -1` 判失败(用负数不用 0,道理同新训练器那边)。"""
        rep = tct.align_check(
            self.probe, self.tok, self.text, 64, "cpu", "qwen",
            self.model_dir, tol=3e-4, rule="rel", rel_tol=-1)
        self.assertFalse(rep["PASS"], f"rel_tol=-1 应该判失败,实际:{rep}")


if __name__ == "__main__":
    unittest.main()
