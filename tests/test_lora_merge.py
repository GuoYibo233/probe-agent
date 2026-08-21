"""LoRA 存档契约的单测:包完适配器立刻合并,权重必须逐项等于原底座。

护的是 `pipeline/train/lora_util.py` 那条"训完先 merge_and_unload 再
save_pretrained"的路。LoRA 的 B 矩阵是零初始化的,所以刚包完还没训的时候
适配器对权重的贡献恒为零,合并出来的模型必须与原底座**逐项 allclose**。
这一条断了就说明合并那步接错了(比如把缩放乘错、或者合到了别的层),而
那种错落盘之后不报错——评测端照样装得回来,只是权重是坏的。

另外几件一起测掉:
- 七件套 target modules 确实都被换成了 LoRA 层(漏一件不报错,只是那部分
  底座根本没训到);
- 合并副本是深拷的,原件合并之后还留着适配器,能接着训(三个脚本都是
  "存完 best 接着训下一轮",原件被就地拆掉的话第二轮起训的就是别的模型);
- 落盘再读回来的权重仍与原底座逐项 allclose(存档入口 `save_merged`);
- 开梯度检查点时适配器真的收得到梯度(peft 的经典坑:checkpoint 段里没有
  一个输入 require_grad 时整段不建图,梯度全 None 而且不报错);
- 旗标默认值与学习率取舍(显式 --lr > --lora-lr > 全参默认)。

模型用随机初始化的两层 Qwen3(在内存里造,不读盘、不下载),CPU 秒级跑完。

跑法(要 torch/transformers/peft,所以走 cprobe-env):
  cprobe-env/bin/python -m unittest tests.test_lora_merge -v
系统 python3 跑全量 discover 时本模块整体 skip(没有 torch),不算失败。
"""
import argparse
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline/train"))

try:
    import torch
    import transformers
    from transformers import AutoModel, AutoModelForCausalLM
    import peft  # noqa: F401
    import lora_util
except ImportError as e:                      # 系统 python3 没有 torch/peft
    raise unittest.SkipTest(f"要 cprobe-env 解释器(torch/transformers/peft):{e}")


SEED = 20260729          # 测试假件自己的固定种子;训练脚本 np821 起换 42,本测试不跟随


def tiny_config():
    """随机初始化的两层 Qwen3:结构与三档底座同族,规模小到 CPU 秒级。"""
    return transformers.Qwen3Config(
        hidden_size=32, intermediate_size=64, num_hidden_layers=2,
        num_attention_heads=4, num_key_value_heads=2, head_dim=8,
        vocab_size=64, max_position_embeddings=64, tie_word_embeddings=False)


def lora_args(rank=16, alpha=32, dropout=0.05, lr=2e-4, lora=True):
    """伪造一份 argparse 结果:三个训练脚本传给 lora_util 的就是这几个字段。"""
    return argparse.Namespace(lora=lora, lora_rank=rank, lora_alpha=alpha,
                              lora_dropout=dropout, lora_lr=lr)


def snapshot(model):
    return {k: v.detach().clone() for k, v in model.state_dict().items()}


class TestLoraMerge(unittest.TestCase):
    """合并回来的权重要与原底座逐项 allclose(两种底座各测一遍)。"""

    def _roundtrip(self, model):
        before = snapshot(model)
        wrapped = lora_util.wrap(model, lora_args())
        merged = lora_util.merged_copy(wrapped)
        after = merged.state_dict()
        self.assertEqual(set(after), set(before),
                         "合并后的 state_dict 键集合变了——落盘格式就不同构了")
        bad = [k for k in before
               if not torch.allclose(after[k], before[k], atol=1e-6, rtol=1e-5)]
        self.assertEqual(bad, [], f"这些权重合并后与原底座对不上:{bad[:5]}")
        return wrapped, merged

    def test_causal_lm_merge_equals_base(self):
        """cgen / cparam 走的底座:AutoModelForCausalLM。"""
        torch.manual_seed(SEED)
        model = AutoModelForCausalLM.from_config(tiny_config())
        model.eval()
        _wrapped, merged = self._roundtrip(model)
        self.assertIsInstance(merged, type(model))

    def test_base_model_merge_equals_base(self):
        """ctool 走的底座:AutoModel(没有语言模型头,只出隐状态)。"""
        torch.manual_seed(SEED)
        model = AutoModel.from_config(tiny_config())
        model.eval()
        _wrapped, merged = self._roundtrip(model)
        self.assertIsInstance(merged, type(model))

    def test_all_seven_target_modules_wrapped(self):
        """七件套一个都不许漏:漏了的那类线性层根本没参与训练,而且不报错。"""
        torch.manual_seed(SEED)
        model = AutoModelForCausalLM.from_config(tiny_config())
        lora_util.wrap(model, lora_args())
        hit = set()
        for name, mod in model.named_modules():
            if hasattr(mod, "lora_A"):
                hit.add(name.rsplit(".", 1)[-1])
        self.assertEqual(hit, set(lora_util.TARGET_MODULES))

    def test_only_adapters_trainable(self):
        """包完之后可训的只剩适配器,底座全冻。"""
        torch.manual_seed(SEED)
        model = AutoModelForCausalLM.from_config(tiny_config())
        lora_util.wrap(model, lora_args())
        train = [n for n, p in model.named_parameters() if p.requires_grad]
        self.assertTrue(train, "一个可训参数都没有,LoRA 没包上")
        self.assertTrue(all("lora_" in n for n in train),
                        f"这些非适配器参数还可训:{[n for n in train if 'lora_' not in n][:5]}")
        # opt_params 只收可训的那批
        picked = lora_util.opt_params(model.parameters(), True)
        self.assertEqual(len(picked), len(train))

    def test_original_keeps_adapters_after_merge(self):
        """合并走的是深拷副本:原件合并之后照样带适配器,还能接着训。"""
        torch.manual_seed(SEED)
        model = AutoModelForCausalLM.from_config(tiny_config())
        wrapped = lora_util.wrap(model, lora_args())
        lora_util.merged_copy(wrapped)
        still = [n for n, _ in model.named_parameters() if "lora_" in n]
        self.assertTrue(still, "原件的适配器被就地拆了——第二轮起训的就不是同一个模型")

    def test_save_merged_writes_base_equivalent_checkpoint(self):
        """存档入口:落盘的权重装回来必须与原底座逐项 allclose,原件还带适配器。"""
        import tempfile
        torch.manual_seed(SEED)
        model = AutoModelForCausalLM.from_config(tiny_config())
        before = snapshot(model)
        wrapped = lora_util.wrap(model, lora_args())
        with tempfile.TemporaryDirectory() as d:
            lora_util.save_merged(wrapped, Path(d) / "best", "cpu")
            back = AutoModelForCausalLM.from_pretrained(Path(d) / "best")
        after = back.state_dict()
        self.assertEqual(set(after), set(before))
        bad = [k for k in before
               if not torch.allclose(after[k], before[k], atol=1e-6, rtol=1e-5)]
        self.assertEqual(bad, [], f"落盘再读回来对不上原底座:{bad[:5]}")
        self.assertTrue([n for n, _ in model.named_parameters() if "lora_" in n],
                        "存完档原件的适配器没了")

    def test_merge_reflects_trained_adapter(self):
        """把 B 矩阵灌成非零,合并后的权重必须跟着变——证明合并真的在合。"""
        torch.manual_seed(SEED)
        model = AutoModelForCausalLM.from_config(tiny_config())
        before = snapshot(model)
        wrapped = lora_util.wrap(model, lora_args(rank=4, alpha=8))
        n_touched = 0
        with torch.no_grad():
            for _n, p in model.named_parameters():
                if "lora_B" in _n:
                    p.fill_(0.01)
                    n_touched += 1
        self.assertGreater(n_touched, 0)
        after = lora_util.merged_copy(wrapped).state_dict()
        moved = [k for k in before
                 if not torch.allclose(after[k], before[k], atol=1e-6, rtol=1e-5)]
        self.assertEqual(len(moved), n_touched,
                         "被适配器改动的权重数对不上 lora_B 的个数")


class TestLoraGradCkpt(unittest.TestCase):
    """LoRA + 梯度检查点:适配器必须真的收到梯度。

    这是 peft 的经典坑——checkpoint 段里一个输入都不 require_grad 时整段不建图,
    适配器的梯度全是 None,而且**不报错**,只表现为损失不动。
    """

    def _grads(self, use_grad_ckpt):
        torch.manual_seed(SEED)
        model = AutoModelForCausalLM.from_config(tiny_config())
        lora_util.wrap(model, lora_args())
        if use_grad_ckpt:
            model.gradient_checkpointing_enable()
            model.config.use_cache = False
            lora_util.prepare_grad_ckpt(model)
        model.train()
        ids = torch.randint(0, 64, (2, 16))
        model(input_ids=ids, labels=ids).loss.backward()
        return {n: p.grad for n, p in model.named_parameters()
                if "lora_A" in n or "lora_B" in n}

    def test_adapters_get_gradients_with_grad_ckpt(self):
        g = self._grads(True)
        self.assertTrue(g, "一个适配器参数都没有")
        none = [n for n, v in g.items() if v is None]
        self.assertEqual(none, [], f"这些适配器在梯度检查点下没拿到梯度:{none[:5]}")
        # 第一步只看 lora_B:B 是零初始化的,所以 dL/dA 第一步天然全零,
        # 而 dL/dB 非零才说明梯度真的流进了适配器。
        zero = [n for n, v in g.items() if "lora_B" in n and not v.any()]
        self.assertEqual(zero, [], f"这些 lora_B 的梯度全零:{zero[:5]}")

    def test_adapters_get_gradients_without_grad_ckpt(self):
        g = self._grads(False)
        none = [n for n, v in g.items() if v is None]
        self.assertEqual(none, [], f"这些适配器没拿到梯度:{none[:5]}")


class TestLoraFlags(unittest.TestCase):
    """旗标与 meta 块:三个脚本共用这一份,默认值写死在这里。"""

    def _parser(self):
        ap = argparse.ArgumentParser()
        ap.add_argument("--lr", type=float, default=None)
        lora_util.add_args(ap)
        return ap

    def test_defaults(self):
        a = self._parser().parse_args([])
        self.assertFalse(a.lora)
        self.assertEqual(a.lora_rank, 16)
        self.assertEqual(a.lora_alpha, 32)
        self.assertEqual(a.lora_dropout, 0.05)
        self.assertEqual(a.lora_lr, 2e-4)

    def test_lr_resolution(self):
        p = self._parser()
        # 不开 LoRA、不给 --lr:全参默认
        self.assertEqual(lora_util.resolve_lr(p.parse_args([]), 1e-5), 1e-5)
        # 开 LoRA、不给 --lr:换成 --lora-lr
        self.assertEqual(
            lora_util.resolve_lr(p.parse_args(["--lora"]), 1e-5), 2e-4)
        # 开 LoRA 但显式给了 --lr:以显式值为准
        self.assertEqual(
            lora_util.resolve_lr(p.parse_args(["--lora", "--lr", "3e-5"]),
                                 1e-5), 3e-5)
        # 开 LoRA 且改了 --lora-lr
        self.assertEqual(
            lora_util.resolve_lr(p.parse_args(["--lora", "--lora-lr", "1e-3"]),
                                 1e-5), 1e-3)

    def test_meta_block(self):
        a = self._parser().parse_args(
            ["--lora", "--lora-rank", "8", "--lora-alpha", "64",
             "--lora-dropout", "0.1"])
        m = lora_util.meta_block(a, 2e-4)
        self.assertEqual(m, dict(rank=8, alpha=64, dropout=0.1, lr=2e-4,
                                 target_modules=lora_util.TARGET_MODULES))
        # meta 里的表是拷贝:改它不许污染模块常量
        m["target_modules"].append("mlp")
        self.assertEqual(len(lora_util.TARGET_MODULES), 7)

    def test_opt_params_passthrough_without_lora(self):
        """不开 LoRA 时参数表原样透传,顺序不变(AdamW 的状态按顺序建)。"""
        ps = [torch.nn.Parameter(torch.zeros(2)) for _ in range(3)]
        ps[1].requires_grad_(False)
        self.assertEqual(lora_util.opt_params(ps, False), ps)


if __name__ == "__main__":
    unittest.main()
