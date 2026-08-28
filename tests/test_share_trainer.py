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
