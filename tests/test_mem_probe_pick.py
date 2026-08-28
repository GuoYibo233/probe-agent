"""tests/test_mem_probe_pick.py —— spec `.scratch/kvshare-train/spec.md`
16.5、16.9,对应工单 `.scratch/kvshare-train/issues/10-mem-probe-pick.md`。

跑法(要 cprobe-env,`import train_causal_share` 顶层有 transformers>=5.14
版本门):
  cprobe-env/bin/python -m unittest tests.test_mem_probe_pick -v
系统 python3 跑全量 discover 时本模块整体 skip(没有 torch),不算失败;
mbert-env(transformers 4.57.6)下同样 skip(照 tests/test_share_trainer.py
的做法)。

小模型与事件的构造复用 `tests/test_share_trainer.py` 的辅助函数
(`_tiny_config`、`_load_five_short_events`、`QWEN_PATH` 等),不在这里
另抄一份;真实 Qwen3-0.6B-Base 分词器路径、现役数据不存在时涉及它们的
用例 `skipTest`。
"""
import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline/train"))
sys.path.insert(0, str(ROOT / "tests"))

try:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
except ImportError as e:                       # 系统 python3 没有 torch
    raise unittest.SkipTest(f"要 cprobe-env 解释器:{e}")

try:
    import train_causal_share as tcs           # noqa: E402
    import share_data                          # noqa: E402
except ImportError as e:                       # 系统 python3 没有 transformers
    raise unittest.SkipTest(f"要 cprobe-env 解释器:{e}")
except SystemExit as e:                        # mbert-env 的 transformers<5.14
    raise unittest.SkipTest(f"要 cprobe-env 解释器:{e}")

import test_share_trainer as tst               # noqa: E402:复用小模型/事件辅助函数

QWEN_PATH = tst.QWEN_PATH
DATA_DIR = tst.DATA_DIR
VAL_PATH = tst.VAL_PATH
TRAIN_PATH = tst.TRAIN_PATH
SEED = tst.SEED
_tiny_config = tst._tiny_config
_load_five_short_events = tst._load_five_short_events


def _mk_block(packed_len, loss_counts):
    """单事件物理块(纯挑块逻辑测试用):`_pick_cost_blocks` 只读一个块的
    `packed_len`(经 `_l_pad` 补齐)与每行 `row[4]`(`seg_lab`)里非 -100 的
    个数,不需要真实 `full_ids`/`seg_ids`,所以 `packed_len` 直接给定,
    `seg_lab` 直接写成全 1(全部当损失位)。`loss_counts` 是这个事件每一行
    的损失位数,行数 = len(loss_counts)。返回单事件物理块(事件列表,长度 1)。
    """
    rows = [(i, f"r{i}", 0, [], [1] * n, 1.0) for i, n in enumerate(loss_counts)]
    return [dict(event=f"ev_{packed_len}_{sum(loss_counts)}",
                packed_len=packed_len, rows=rows)]


class TestPickCostBlocks(unittest.TestCase):
    """(a) 工单 10 spec 16.5/16.9:手造 6 个小事件(块),`cost` 挑块的三条
    规则——token 最多(并列时取损失位多的)、损失位最多(与前者不同)、按
    `n_tok/max_n_tok + n_loss_pos/max_n_loss_pos` 算出来的第三块。"""

    def test_tiebreak_and_third_block(self):
        blk_losspos_max = _mk_block(64, [60])          # 一行,目标长:损失位最多
        blk_tokens_tie_low = _mk_block(320, [2] * 8)    # 行多前缀长:token 并列(损失位少)
        blk_tokens_tie_high = _mk_block(320, [5] * 8)   # 同 token 数,损失位更多
        blk_cost_max = _mk_block(288, [11] * 5)         # 综合分最高
        blk_filler1 = _mk_block(48, [5])
        blk_filler2 = _mk_block(32, [3])

        blocks = [blk_losspos_max, blk_tokens_tie_low, blk_tokens_tie_high,
                 blk_cost_max, blk_filler1, blk_filler2]
        picks = dict(tcs._pick_cost_blocks(blocks))

        self.assertEqual(set(picks),
                         {"max_tokens_block", "max_losspos_block", "max_cost_block"})
        self.assertIs(picks["max_tokens_block"], blk_tokens_tie_high,
                      "token 数并列时应该取损失位多的那块")
        self.assertIs(picks["max_losspos_block"], blk_losspos_max)
        self.assertIsNot(picks["max_tokens_block"], picks["max_losspos_block"])
        self.assertIs(picks["max_cost_block"], blk_cost_max)
        self.assertNotIn(picks["max_cost_block"],
                         (picks["max_tokens_block"], picks["max_losspos_block"]))


class TestRunMemProbeThreeModes(unittest.TestCase):
    """(b) 三种模式各跑一次 `run_mem_probe`:`opt.state` 为空、lr 恢复、
    `.grad` 全 None、参数逐位不变(`loop` 模式也是)、都写了
    `mem_probe_summary`。`worst_gb`/`worst_kind` 用 monkeypatch 的
    `_peak_gb`(每次调用返回递增假值)来验证有区分度(CPU 上真值恒 0)。"""

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"分词器路径不存在:{QWEN_PATH}")
        if not VAL_PATH.exists():
            raise unittest.SkipTest(f"val 集不存在:{VAL_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)
        if cls.tok.pad_token_id is None:
            cls.tok.pad_token = cls.tok.eos_token
        cls.tok.truncation_side = "left"
        cls.tok.padding_side = "right"
        cls.tmpdir, cls.data_path = _load_five_short_events()

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def _run_mode(self, pick):
        events, _counts = share_data.load_events(
            self.data_path, self.tok, mode="cgen", max_len=8192, limit=0)
        self.assertGreaterEqual(len(events), 2,
                                "要至少 2 个事件才能凑出多个物理块")

        torch.manual_seed(SEED)
        model = AutoModelForCausalLM.from_config(_tiny_config(len(self.tok)))
        model.train()
        orig_lr = 1e-3
        opt = torch.optim.AdamW(model.parameters(), lr=orig_lr,
                                weight_decay=0.01)
        params_before = [p.detach().clone() for p in model.parameters()]

        args = argparse.Namespace(tok_budget=100000, events_per_mb=2,
                                  accum=2, mem_probe_pick=pick)
        logged = []

        def log(**kw):
            logged.append(kw)

        counter = {"n": 0}

        def fake_peak(_dev):
            counter["n"] += 1
            return float(counter["n"])

        with patch.object(tcs, "_peak_gb", side_effect=fake_peak):
            tcs.run_mem_probe(model, opt, events, args, "cpu", log, amp=False)

        self.assertEqual(len(opt.state), 0,
                         f"{pick}:探针收尾后 opt.state 应该清空")
        self.assertTrue(
            all(g["lr"] == orig_lr for g in opt.param_groups),
            f"{pick}:探针收尾后各 param_group 的 lr 应该恢复原值")
        self.assertTrue(
            all(p.grad is None for p in model.parameters()),
            f"{pick}:探针收尾后所有参数的 .grad 应该是 None")
        for p0, p1 in zip(params_before, model.parameters()):
            self.assertTrue(torch.equal(p0, p1),
                            f"{pick}:参数在探针前后逐位不变")

        mem_events = [e for e in logged if e.get("event") == "mem_probe"]
        summaries = [e for e in logged if e.get("event") == "mem_probe_summary"]
        self.assertTrue(mem_events, f"{pick}:应该至少写一条 mem_probe 事件")
        self.assertEqual(len(summaries), 1,
                         f"{pick}:应该恰好写一条 mem_probe_summary")
        summary = summaries[0]
        self.assertEqual(summary["pick"], pick)

        max_peak = max(e["peak_mem_gb"] for e in mem_events)
        max_kind = next(e["kind"] for e in mem_events
                        if e["peak_mem_gb"] == max_peak)
        self.assertEqual(summary["worst_gb"], max_peak,
                         f"{pick}:worst_gb 应该等于各块 peak_mem_gb 的最大值")
        self.assertEqual(summary["worst_kind"], max_kind,
                         f"{pick}:worst_kind 应该对上 peak 最大的那个 kind")

    def test_tokens(self):
        self._run_mode("tokens")

    def test_cost(self):
        self._run_mode("cost")

    def test_loop(self):
        self._run_mode("loop")


class TestMemProbeRngRestorationViaMain(unittest.TestCase):
    """(c) 小模型 `main()` 带 `--mem-probe --mem-probe-pick cost --device
    cpu --lora` 与不带 `--mem-probe`(同样 `--lora`)各跑一次(同 `--smoke
    --max-events 6 --log-every 1`),两份 `train_log.jsonl` 的 `step` 事件
    `loss` 逐条相同——随机数状态在探针前后被恢复(spec 16.5,静默失败点
    #31),LoRA dropout 的随机流不受影响(小模型不挂 LoRA 时 dropout 为 0,
    没有区分度)。"""

    def test_loss_identical_with_and_without_mem_probe(self):
        try:
            import peft  # noqa: F401
        except ImportError as e:
            self.skipTest(f"peft 未安装:{e}")
        if not Path(QWEN_PATH).exists():
            self.skipTest(f"分词器路径不存在:{QWEN_PATH}")
        if not TRAIN_PATH.exists() or not VAL_PATH.exists():
            self.skipTest(f"现役数据不存在:{DATA_DIR}")

        tok = AutoTokenizer.from_pretrained(QWEN_PATH)
        vocab_size = len(tok)
        with tempfile.TemporaryDirectory() as model_dir, \
                tempfile.TemporaryDirectory() as out_root:
            torch.manual_seed(SEED)
            model = AutoModelForCausalLM.from_config(_tiny_config(vocab_size))
            model.save_pretrained(model_dir)
            tok.save_pretrained(model_dir)

            def _run(name, extra_args):
                out = Path(out_root) / name
                argv = ["train_causal_share.py", "--mode", "cgen",
                       "--base", model_dir, "--data", str(DATA_DIR),
                       "--out", str(out), "--smoke", "--max-events", "6",
                       "--log-every", "1", "--device", "cpu",
                       "--align-events", "2", "--lora"] + extra_args
                old_argv = sys.argv
                sys.argv = argv
                try:
                    tcs.main()
                finally:
                    sys.argv = old_argv
                losses = []
                for line in open(out / "train_log.jsonl"):
                    r = json.loads(line)
                    if r["event"] == "step":
                        losses.append(r["loss"])
                return losses

            loss_with_probe = _run(
                "with_probe", ["--mem-probe", "--mem-probe-pick", "cost"])
            loss_without_probe = _run("without_probe", [])

            self.assertTrue(loss_with_probe, "没有任何 step 事件")
            self.assertEqual(loss_with_probe, loss_without_probe,
                             "带探针与不带探针的 run 训练部分应该逐位相同"
                             "(随机数状态在探针前后被恢复)")


if __name__ == "__main__":
    unittest.main()
