"""tests/test_share_trainer.py —— spec `.scratch/kvshare-train/spec.md` 第 12
节的 (a)(b)(c),对应工单 `.scratch/kvshare-train/issues/03-share-trainer.md`。

模型全部用 `transformers.Qwen3Config` 随机初始化的小模型(全参,不挂 LoRA——
LoRA dropout 0.05 每次前向重新采样,梯度等式对 LoRA 不成立),`vocab_size`
取真实分词器的词表大小(`len(tok)`,含 added tokens,不然真实数据里的高位
token id 会越界),CPU fp32。

跑法(要 cprobe-env,`import train_causal_share` 顶层有 transformers>=5.14
版本门):
  cprobe-env/bin/python -m unittest tests.test_share_trainer -v
系统 python3 跑全量 discover 时本模块整体 skip(没有 torch),不算失败;
mbert-env(transformers 4.57.6)下 `import train_causal_share` 会 `SystemExit`,
一并兜住照样 skip(照 `tests/test_cparam_assembly.py` 第 21 到 29 行)。

真实 Qwen3-0.6B-Base 分词器路径、现役数据 `pipeline/data/nyapass_aw_v1/gptoss`
不存在时,涉及它们的用例 `skipTest`。
"""
import json
import random as _random
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
    import train_causal_callgen                # noqa: E402
    import train_causal_param                  # noqa: E402
    import share_data                          # noqa: E402
except ImportError as e:                       # 系统 python3 没有 transformers
    raise unittest.SkipTest(f"要 cprobe-env 解释器:{e}")
except SystemExit as e:                        # mbert-env 的 transformers<5.14
    raise unittest.SkipTest(f"要 cprobe-env 解释器:{e}")

QWEN_PATH = train_causal_callgen.MODELS["qwen"]
DATA_DIR = ROOT / "pipeline/data/nyapass_aw_v1/gptoss"
VAL_PATH = DATA_DIR / "val.jsonl"
TRAIN_PATH = DATA_DIR / "train.jsonl"

SEED = 20260729          # 测试假件自己的固定种子,同 tests/test_lora_merge.py


def _tiny_config(vocab_size):
    """随机初始化的两层 Qwen3,结构与三档底座同族,规模小到 CPU 秒级
    (照 tests/test_lora_merge.py 的 tiny_config,vocab_size 换成真实词表)。"""
    return transformers.Qwen3Config(
        hidden_size=64, intermediate_size=128, num_hidden_layers=2,
        num_attention_heads=4, num_key_value_heads=2, head_dim=16,
        vocab_size=vocab_size, max_position_embeddings=8192,
        tie_word_embeddings=False)


def _load_five_short_events():
    """从现役 val 集里挑 5 个短事件(行数 2~6,全文不超过 800 字符),种子 42
    (照 tests/test_share_data.py 的抽样方式),写成一个临时 jsonl。"""
    raw_by_event, order = {}, []
    with open(VAL_PATH) as f:
        for line in f:
            r = json.loads(line)
            ev = r["event"]
            if ev not in raw_by_event:
                raw_by_event[ev] = []
                order.append(ev)
            raw_by_event[ev].append(r)
    cands = []
    for ev in order:
        rs = sorted(raw_by_event[ev], key=lambda r: r["sent_idx"])
        if 2 <= len(rs) <= 6 and len(rs[-1]["text"]) <= 800:
            cands.append(ev)
    picked = _random.Random(42).sample(cands, min(5, len(cands)))
    rows = []
    for ev in picked:
        rows.extend(sorted(raw_by_event[ev], key=lambda r: r["sent_idx"]))
    tmpdir = tempfile.TemporaryDirectory()
    path = str(Path(tmpdir.name) / "five.jsonl")
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return tmpdir, path


class TestPackedForwardMatchesOldPath(unittest.TestCase):
    """(a) 拼接前向的每行 ce 与旧路径(旧 collate + inst_ce)逐行差 <= 1e-5。"""

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

        torch.manual_seed(SEED)
        cls.model = AutoModelForCausalLM.from_config(_tiny_config(len(cls.tok)))
        cls.model.eval()

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def _check_mode(self, mode):
        events, _counts = share_data.load_events(
            self.data_path, self.tok, mode=mode, max_len=8192, limit=0)
        self.assertGreater(len(events), 0)

        OldDS = (train_causal_callgen.CallDS if mode == "cgen"
                else train_causal_param.ParamDS)
        old_collate = (train_causal_callgen.collate if mode == "cgen"
                      else train_causal_param.collate)
        old_inst_ce = (train_causal_callgen.inst_ce if mode == "cgen"
                      else train_causal_param.inst_ce)
        ds = OldDS(self.data_path, self.tok, limit=0)

        # 两条路径的行序都是文件序(load_events 保序契约 + OldDS 不打乱
        # limit=0),先核对逐位 text 相同,再比 ce 才有意义。
        new_texts = [row[1] for ev in events for row in ev["rows"]]
        self.assertEqual(len(ds.rows), len(new_texts))
        for r, t in zip(ds.rows, new_texts):
            self.assertEqual(r[0], t)

        with torch.no_grad():
            enc, labels = old_collate(ds.rows, self.tok, 8192)[:2]
            old_ce = old_inst_ce(self.model, enc, labels, "cpu")

            new_row_ce = torch.cat([
                tcs.block_row_ce(self.model, [ev], "cpu", torch.float32)[0]
                for ev in events])

        diff = (new_row_ce - old_ce).abs()
        self.assertLessEqual(diff.max().item(), 1e-5,
                             f"最大差 {diff.max().item()} (mode={mode})")

    def test_cgen(self):
        self._check_mode("cgen")

    def test_cparam(self):
        self._check_mode("cparam")


class TestRefForwardUsesInstCe(unittest.TestCase):
    """F1(评审发现):`train_causal_share._ref_forward`(对齐检查的参照路径)
    的逐行 ce 必须真的来自调用 `inst_ce`,不是另一套同公式的手写替代——
    (a) 只验新路径 `block_row_ce` 对 `inst_ce` 的差,不覆盖 `_ref_forward`
    这段代码本身,这里直接对 `_ref_forward` 断言。"""

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

        torch.manual_seed(SEED)
        cls.model = AutoModelForCausalLM.from_config(_tiny_config(len(cls.tok)))
        cls.model.eval()

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def _check_mode(self, mode):
        OldDS = (train_causal_callgen.CallDS if mode == "cgen"
                else train_causal_param.ParamDS)
        old_collate = (train_causal_callgen.collate if mode == "cgen"
                      else train_causal_param.collate)
        old_inst_ce = (train_causal_callgen.inst_ce if mode == "cgen"
                      else train_causal_param.inst_ce)
        ds = OldDS(self.data_path, self.tok, limit=0)

        with torch.no_grad():
            row_ref, _tok_ref = tcs._ref_forward(
                mode, self.model, self.tok, ds.rows, "cpu", 8192,
                tcs.REF_BATCH)

            # 不经过 `_ref_forward`,按同样的分批方式独立再走一遍旧
            # collate + 真正调用 inst_ce——两边必须逐行相同(同一个模型、
            # 同一批输入、同一次 no_grad 前向,理论上 bit 级一致),才能
            # 证明 `_ref_forward` 返回的就是 `inst_ce` 的真实输出,不是
            # 另一套同公式的独立实现。
            direct = []
            for i in range(0, len(ds.rows), tcs.REF_BATCH):
                chunk = ds.rows[i:i + tcs.REF_BATCH]
                enc, labels = old_collate(chunk, self.tok, 8192)[:2]
                direct.extend(
                    old_inst_ce(self.model, enc, labels, "cpu").tolist())

        self.assertEqual(len(row_ref), len(direct))
        diff = max(abs(a - b) for a, b in zip(row_ref, direct))
        self.assertEqual(diff, 0.0,
                         f"_ref_forward 的逐行结果与直接调用 inst_ce 不是"
                         f"同一次计算(max diff {diff},mode={mode})")

    def test_cgen(self):
        self._check_mode("cgen")

    def test_cparam(self):
        self._check_mode("cparam")


class TestRunAlignCheckHandlesRefBaselineDriftError(unittest.TestCase):
    """N1(评审发现):`_ref_forward` 的自检失败(参照基线不可信)要走
    `run_align_check` 其余所有校验一致的失败上报通道——写 ALIGN_CHECK.json、
    打印诊断、`sys.exit(2)`——不能是裸 `assert`(会被 `-O`/`PYTHONOPTIMIZE`
    整体剥除、静默放行),也不能是让异常原样冒出去变成未处理的 traceback
    (拿不到结构化产物)。"""

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

        torch.manual_seed(SEED)
        cls.model = AutoModelForCausalLM.from_config(_tiny_config(len(cls.tok)))
        cls.model.eval()

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def test_ref_forward_raises_real_exception_not_assert(self):
        """check_drift=True(默认)时,drift 超容差要抛 `RefBaselineDriftError`
        ——一个真正的异常类,不是裸 `assert`(`-O` 下不会被剥除),错误信息
        里要带漂移数值,不用复现就知道差了多少(工单 05 第 7 条 N2)。用打过
        monkeypatch、逐行都偏移 1.0(远超 1e-6 容差)的 `inst_ce` 制造一个
        必然超差的场景。"""
        ds = train_causal_callgen.CallDS(self.data_path, self.tok, limit=0)
        orig = train_causal_callgen.inst_ce

        def _perturbed(model, enc, labels, dev):
            return orig(model, enc, labels, dev) + 1.0

        train_causal_callgen.inst_ce = _perturbed
        try:
            with torch.no_grad():
                with self.assertRaises(tcs.RefBaselineDriftError) as cm:
                    tcs._ref_forward("cgen", self.model, self.tok, ds.rows,
                                     "cpu", 8192, tcs.REF_BATCH,
                                     check_drift=True)
            msg = str(cm.exception)
            m = re.search(r"max diff ([0-9.eE+-]+)", msg)
            self.assertIsNotNone(m, f"错误信息没带漂移数值:{msg}")
            self.assertGreater(float(m.group(1)), tcs.REF_INST_CE_DRIFT_TOL)
        finally:
            train_causal_callgen.inst_ce = orig

    def test_ref_forward_check_drift_false_does_not_raise(self):
        """同一个必然超差的 monkeypatch,`check_drift=False` 时不抛(工单
        05 S2:bf16 粗筛那一遍关掉这道自检,它只用 `row_ce`)。返回值仍然
        是 `inst_ce` 的真实输出(偏移过的),不是本地公式的替代值。"""
        ds = train_causal_callgen.CallDS(self.data_path, self.tok, limit=0)
        orig = train_causal_callgen.inst_ce

        def _perturbed(model, enc, labels, dev):
            return orig(model, enc, labels, dev) + 1.0

        train_causal_callgen.inst_ce = _perturbed
        try:
            with torch.no_grad():
                row_ce, tok_ce = tcs._ref_forward(
                    "cgen", self.model, self.tok, ds.rows, "cpu", 8192,
                    tcs.REF_BATCH, check_drift=False)
            self.assertTrue(row_ce)
            self.assertTrue(tok_ce)
        finally:
            train_causal_callgen.inst_ce = orig

    def test_run_align_check_reports_drift_error_instead_of_crashing(self):
        """`run_align_check` 捕获 `RefBaselineDriftError` 后按文件里其余
        所有失败分支同样的模式处理:写 ALIGN_CHECK.json(PASS=False,
        stage="ref_forward_drift"),再 `sys.exit(2)`——不是让异常原样冒出去。
        """
        import argparse
        orig = tcs._ref_forward

        def _boom(*_a, **_kw):
            raise tcs.RefBaselineDriftError("测试注入的漂移")

        tcs._ref_forward = _boom
        try:
            with tempfile.TemporaryDirectory() as out_dir:
                args = argparse.Namespace(
                    data=str(DATA_DIR), out=out_dir, align_events=2,
                    max_len=8192, align_tol=2e-5, attn_impl="sdpa",
                    # 工单 09:run_align_check 从 args 取新增的门槛参数,
                    # 这个 Namespace 是手造的,不经过 argparse 默认值,
                    # 补齐新属性(值等于 CLI 默认值)防 AttributeError。
                    align_tok_tol=3e-4, align_bf16_mean_tol=2e-2,
                    align_bf16_max_tol=1e-1, align_baseline_factor=3.0,
                    align_rule="abs", align_rel_tol=1e-5)
                with self.assertRaises(SystemExit) as cm:
                    tcs.run_align_check(self.model, self.tok, args, "cpu",
                                        "cgen", None)
                self.assertEqual(cm.exception.code, 2)

                report_path = Path(out_dir) / "ALIGN_CHECK.json"
                self.assertTrue(report_path.exists(),
                               "drift 报错没有写出 ALIGN_CHECK.json")
                report = json.loads(report_path.read_text())
                self.assertFalse(report["PASS"])
                self.assertEqual(report["stage"], "ref_forward_drift")
                self.assertIn("测试注入的漂移", report["error"])
        finally:
            tcs._ref_forward = orig


class TestBackwardBlockSplitInvariance(unittest.TestCase):
    """(b) 一个逻辑小批拆成 1 块和拆成 3 块的参数梯度逐元素差 <= 1e-6

    (spec 第 5 节:m 个物理块的梯度之和等于整个逻辑小批一次算完的梯度,
    这条性质只依赖 W 与 n_g 不变,与具体怎么切块无关)。
    """

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
        cls.vocab_size = len(cls.tok)

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def _run(self, blocks, W):
        torch.manual_seed(SEED)
        model = AutoModelForCausalLM.from_config(_tiny_config(self.vocab_size))
        model.train()
        tcs.backward_logical_minibatch(model, blocks, W, n_g=1, dev="cpu",
                                       mask_dtype=torch.float32)
        return {n: p.grad.clone() for n, p in model.named_parameters()
                if p.grad is not None}

    def test_split_into_1_vs_3_blocks(self):
        events, _counts = share_data.load_events(
            self.data_path, self.tok, mode="cgen", max_len=8192,
            limit=3, order="shortest")
        self.assertEqual(len(events), 3)
        W = sum(row[5] for ev in events for row in ev["rows"])

        grads_1block = self._run([events], W)
        grads_3block = self._run([[events[0]], [events[1]], [events[2]]], W)

        self.assertTrue(grads_1block, "1 块跑完一个梯度都没有")
        self.assertEqual(set(grads_1block), set(grads_3block))
        bad = []
        for k in grads_1block:
            diff = (grads_1block[k] - grads_3block[k]).abs().max().item()
            if diff > 1e-6:
                bad.append((k, diff))
        self.assertEqual(bad, [], f"这些参数 1 块/3 块的梯度对不上:{bad[:5]}")


class TestBlockRowCeUnderLoRA(unittest.TestCase):
    """工单 05 验收第 3 条:`_forward_packed` 改用 `model.model(...)` 的
    backbone 输出再过 `model.lm_head`(S1)之后,LoRA 包装下一次前向加反向
    仍要能跑,且只有适配器参数拿到梯度。两个用例分别覆盖 `_base_model_and_head`
    的两条分支:`test_lora_forward_backward` 走 `lora_util.wrap` 就地注入、
    调用方原来的 `model` 变量继续用这条实际路径(落进 `else` 分支——
    `model` 本身不是 PeftModel);`test_get_base_model_branch_forward_backward`
    走『拿到手的就是 PeftModel 本身』这条更泛的路径(工单 05 复审 F1:
    `get_base_model()` 分支此前没有任何用例真正执行到)。

    peft 装了就跑,没装就 skip。"""

    @classmethod
    def setUpClass(cls):
        try:
            import peft  # noqa: F401
        except ImportError as e:
            raise unittest.SkipTest(f"peft 未安装:{e}")
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

    def test_lora_forward_backward(self):
        import argparse
        import lora_util

        torch.manual_seed(SEED)
        model = AutoModelForCausalLM.from_config(_tiny_config(len(self.tok)))
        model.train()
        lora_args = argparse.Namespace(
            lora_rank=4, lora_alpha=8, lora_dropout=0.0)
        lora_util.wrap(model, lora_args)  # 就地注入,原变量 model 继续用

        events, _counts = share_data.load_events(
            self.data_path, self.tok, mode="cgen", max_len=8192,
            limit=2, order="shortest")
        self.assertEqual(len(events), 2)
        W = sum(row[5] for ev in events for row in ev["rows"])

        tcs.backward_logical_minibatch(
            model, [events], W, n_g=1, dev="cpu", mask_dtype=torch.float32)

        trainable = [(n, p) for n, p in model.named_parameters()
                    if p.requires_grad]
        frozen = [(n, p) for n, p in model.named_parameters()
                 if not p.requires_grad]
        self.assertTrue(trainable, "LoRA 包装后没有任何可训练参数")
        self.assertTrue(
            any(p.grad is not None for _n, p in trainable),
            "LoRA 适配器参数一个都没拿到梯度——S1 的 model.model()/"
            "model.lm_head 取法在 peft 包装下没建起图")
        self.assertTrue(
            all(p.grad is None for _n, p in frozen),
            "非适配器参数不该有梯度(lora_util.wrap 已把它们 requires_grad "
            "设成 False)")

    def test_get_base_model_branch_forward_backward(self):
        """工单 05 复审 F1:`test_lora_forward_backward` 传给
        `backward_logical_minibatch` 的 `model` 是 `lora_util.wrap` 就地注入
        后的原变量,本身不是 PeftModel,所以 `_base_model_and_head` 里
        `hasattr(model, "get_base_model")` 恒假,`get_base_model()` 那半句
        代码一次都没被执行到。这里改传 `lora_util.wrap` 的**返回值**
        (真正的 `PeftModel` 对象)当 `model` 用,逼 `_base_model_and_head`
        走 `get_base_model()` 分支:先直接核对取到的 backbone/lm_head 就是
        `get_base_model()` 返回对象上的那两个属性(证明分支本身取值正确),
        再跑一次真实的前向加反向(证明这条分支下建出来的计算图真的能
        训——不是只有对象相等这一层保证)。"""
        import argparse
        import lora_util

        torch.manual_seed(SEED)
        model = AutoModelForCausalLM.from_config(_tiny_config(len(self.tok)))
        model.train()
        lora_args = argparse.Namespace(
            lora_rank=4, lora_alpha=8, lora_dropout=0.0)
        wrapped = lora_util.wrap(model, lora_args)  # 真正的 PeftModel,不丢弃

        self.assertTrue(
            hasattr(wrapped, "get_base_model"),
            "peft 版本变了,PeftModel 不再有 get_base_model()——"
            "_base_model_and_head 的分支判据要跟着改")
        backbone, lm_head = tcs._base_model_and_head(wrapped)
        base = wrapped.get_base_model()
        self.assertIs(
            backbone, base.model,
            "get_base_model() 分支取到的 backbone 应该就是 "
            "get_base_model() 返回对象上的 .model")
        self.assertIs(
            lm_head, base.lm_head,
            "get_base_model() 分支取到的 lm_head 应该就是 "
            "get_base_model() 返回对象上的 .lm_head")

        events, _counts = share_data.load_events(
            self.data_path, self.tok, mode="cgen", max_len=8192,
            limit=2, order="shortest")
        W = sum(row[5] for ev in events for row in ev["rows"])

        tcs.backward_logical_minibatch(
            wrapped, [events], W, n_g=1, dev="cpu", mask_dtype=torch.float32)

        trainable = [(n, p) for n, p in model.named_parameters()
                    if p.requires_grad]
        frozen = [(n, p) for n, p in model.named_parameters()
                 if not p.requires_grad]
        self.assertTrue(
            any(p.grad is not None for _n, p in trainable),
            "走 get_base_model() 分支时 LoRA 适配器参数一个都没拿到梯度")
        self.assertTrue(
            all(p.grad is None for _n, p in frozen),
            "走 get_base_model() 分支时非适配器参数不该有梯度")


class TestRunMemProbeCPU(unittest.TestCase):
    """工单 06:`run_mem_probe` 的 CPU 收尾状态与日志字段——真正的验收判据是
    H100 实测(改后 `fullest_block.peak_mem_gb` 是否 >= 训练整程 `step` 峰值,
    工单不做),这里只验 CPU 上能跑通、收尾干净、字段齐全。"""

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

    def test_state_cleared_lr_restored_grad_none_after_probe(self):
        import argparse

        events, _counts = share_data.load_events(
            self.data_path, self.tok, mode="cgen", max_len=8192, limit=0)
        self.assertGreaterEqual(len(events), 2,
                                "要至少 2 个事件才能凑出最满块")

        torch.manual_seed(SEED)
        model = AutoModelForCausalLM.from_config(_tiny_config(len(self.tok)))
        model.train()
        orig_lr = 1e-3
        opt = torch.optim.AdamW(model.parameters(), lr=orig_lr,
                                weight_decay=0.01)
        args = argparse.Namespace(tok_budget=100000, events_per_mb=4)
        logged = []

        def log(**kw):
            logged.append(kw)

        tcs.run_mem_probe(model, opt, events, args, "cpu", log, amp=False)

        self.assertEqual(len(opt.state), 0, "探针收尾后 opt.state 应该清空")
        self.assertTrue(
            all(g["lr"] == orig_lr for g in opt.param_groups),
            "探针收尾后各 param_group 的 lr 应该恢复原值")
        self.assertTrue(
            all(p.grad is None for p in model.parameters()),
            "探针收尾后所有参数的 .grad 应该是 None")

        kinds = {e["kind"]: e for e in logged if e.get("event") == "mem_probe"}
        self.assertEqual(set(kinds), {"longest_event", "fullest_block"},
                         f"应该写两条 mem_probe 事件,实际:{logged}")
        for kind, n_backward in (("fullest_block", 2), ("longest_event", 1)):
            e = kinds[kind]
            self.assertEqual(e["n_backward"], n_backward,
                             f"{kind} 的 n_backward 应该是 {n_backward}")
            self.assertTrue(e["optimizer_state_prebuilt"])
            self.assertTrue(e["with_optimizer_state"])
            self.assertEqual(e["peak_mem_gb"], 0.0)   # CPU 上允许为 0
            for key in ("B", "L_pad", "n_events", "packed_len_max"):
                self.assertIn(key, e, f"{kind} 缺字段 {key}")

    def test_state_built_before_any_forward_backward(self):
        """F1(工单 06 修复第 2 轮):按工单字面顺序,建状态这一步(先
        `opt.zero_grad(set_to_none=False)` 接 lr=0 的 `opt.step()`)之前不
        应该发生任何前向或反向——用一个会记录『调用发生时 `opt.state` 是否
        还是空字典』的 `block_row_ce` 替身验证:第一次前向反向发生时,
        `opt.state` 必须已经非空(状态已经建好),不能有任何一次前向反向发生
        在 `opt.state` 还是空字典的时候。"""
        import argparse

        events, _counts = share_data.load_events(
            self.data_path, self.tok, mode="cgen", max_len=8192, limit=0)
        self.assertGreaterEqual(len(events), 2,
                                "要至少 2 个事件才能凑出最满块")

        torch.manual_seed(SEED)
        model = AutoModelForCausalLM.from_config(_tiny_config(len(self.tok)))
        model.train()
        opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=0.01)
        args = argparse.Namespace(tok_budget=100000, events_per_mb=4)
        logged = []

        def log(**kw):
            logged.append(kw)

        state_was_empty_at_call = []
        real_block_row_ce = tcs.block_row_ce

        def spy(*a, **kw):
            state_was_empty_at_call.append(len(opt.state) == 0)
            return real_block_row_ce(*a, **kw)

        with patch.object(tcs, "block_row_ce", side_effect=spy):
            tcs.run_mem_probe(model, opt, events, args, "cpu", log, amp=False)

        self.assertGreater(len(state_was_empty_at_call), 0,
                           "应该至少发生一次前向反向")
        self.assertFalse(any(state_was_empty_at_call),
                         "建状态这一步之前不应该发生任何前向或反向,"
                         f"实际记录:{state_was_empty_at_call}")


class TestMainSmokeCPU(unittest.TestCase):
    """(c) main() 跑 --smoke --max-events 6 --log-every 1 --align-events 2
    --device cpu(--base 一个临时目录,走 build(path=...)),产出
    best/meta.json、ALIGN_CHECK.json(PASS 真)、train_log.jsonl 的五种事件。
    """

    def _run_smoke(self, mode):
        tok = AutoTokenizer.from_pretrained(QWEN_PATH)
        vocab_size = len(tok)
        with tempfile.TemporaryDirectory() as model_dir, \
                tempfile.TemporaryDirectory() as out_root:
            torch.manual_seed(SEED)
            model = AutoModelForCausalLM.from_config(_tiny_config(vocab_size))
            model.save_pretrained(model_dir)
            tok.save_pretrained(model_dir)

            out = Path(out_root) / "run"
            argv = ["train_causal_share.py", "--mode", mode,
                   "--base", model_dir, "--data", str(DATA_DIR),
                   "--out", str(out), "--smoke", "--max-events", "6",
                   "--log-every", "1", "--device", "cpu",
                   "--align-events", "2"]
            old_argv = sys.argv
            sys.argv = argv
            try:
                tcs.main()
            finally:
                sys.argv = old_argv

            self.assertTrue((out / "ALIGN_CHECK.json").exists())
            align = json.loads((out / "ALIGN_CHECK.json").read_text())
            self.assertTrue(align["PASS"], align)

            self.assertTrue((out / "best" / "meta.json").exists())
            meta = json.loads((out / "best" / "meta.json").read_text())
            self.assertEqual(meta["trainer"], "share")
            self.assertIn("call_sep", meta)
            self.assertIn("max_len", meta)
            self.assertIn("data", meta)
            if mode == "cparam":
                self.assertTrue(meta["param_only"])

            events_seen = []
            for line in open(out / "train_log.jsonl"):
                events_seen.append(json.loads(line)["event"])
            # 6 个事件只有 1 次更新(--log-every 1 才写得出 step,工单第 5 条)。
            self.assertEqual(set(events_seen),
                             {"start", "step", "eval", "save_best", "done"})

    def test_cgen_smoke(self):
        if not Path(QWEN_PATH).exists():
            self.skipTest(f"分词器路径不存在:{QWEN_PATH}")
        if not TRAIN_PATH.exists() or not VAL_PATH.exists():
            self.skipTest(f"现役数据不存在:{DATA_DIR}")
        self._run_smoke("cgen")

    def test_cparam_smoke(self):
        if not Path(QWEN_PATH).exists():
            self.skipTest(f"分词器路径不存在:{QWEN_PATH}")
        if not TRAIN_PATH.exists() or not VAL_PATH.exists():
            self.skipTest(f"现役数据不存在:{DATA_DIR}")
        self._run_smoke("cparam")


if __name__ == "__main__":
    unittest.main()
