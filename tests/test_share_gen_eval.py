"""tests/test_share_gen_eval.py —— spec `.scratch/kvshare-train/spec.md` 第
16.9 节工单 08 的 (a)(b)(c)(d)(e),对应工单
`.scratch/kvshare-train/issues/08-gen-eval.md`。

不往 `tests/test_share_trainer.py` 末尾加(工单 09、10 并行,三张往同一文件
末尾加用例必撞),小模型的构造照该文件现有的 `_tiny_config` 辅助函数
import 过来用。spec 16.9 前言:新用例一律用手造的小事件与随机初始化的小
模型,不读 `pipeline/data/nyapass_aw_v1/gptoss` 这种现役大目录(一个用例
读一遍 val 就是十几分钟)——本文件全部用手造 jsonl,真实分词器只用来分词。

跑法(要 cprobe-env,`import train_causal_share` 顶层有 transformers>=5.14
版本门):
  cprobe-env/bin/python -m unittest tests.test_share_gen_eval -v
系统 python3 跑全量 discover 时本模块整体 skip(没有 torch),不算失败;
mbert-env(transformers 4.57.6)下同样兜住照样 skip(照
`tests/test_cparam_assembly.py` 第 21 到 29 行、`tests/test_share_trainer.py`
的做法)。

真实 Qwen3-0.6B-Base 分词器路径不存在时,涉及它的用例 `skipTest`。
"""
import ast
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
    import train_causal_callgen                # noqa: E402
    import train_causal_param                  # noqa: E402
    import share_data                          # noqa: E402
except ImportError as e:                       # 系统 python3 没有 transformers
    raise unittest.SkipTest(f"要 cprobe-env 解释器:{e}")
except SystemExit as e:                        # mbert-env 的 transformers<5.14
    raise unittest.SkipTest(f"要 cprobe-env 解释器:{e}")

from tests.test_share_trainer import _tiny_config  # noqa: E402

QWEN_PATH = train_causal_callgen.MODELS["qwen"]
SEED = 20260729          # 测试假件自己的固定种子,同 tests/test_share_trainer.py


def _mk_row(event, i, n_sents=1, sent_idx=0):
    """一个独立小事件的单行:label/label_call 互相匹配,cgen/cparam 两种
    mode 都能干净装载(cparam 的 `param_target` 不会剥离失败)。照
    `tests/test_share_data.py` 的 `_row`/`_clean_rows` 同一种构造方式。"""
    label = f"apis.pad{i}.call"
    text = f"Please handle synthetic request number {i} right now completely."
    return dict(event=event, sent_idx=sent_idx, n_sents=n_sents, text=text,
               label=label, label_call=f"{label}(x=1)", w=1.0)


def _write_jsonl(rows, path):
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _make_data_dir(n_train, n_eval):
    """手造 `n_train` 个训练事件 + `n_eval` 个 val 事件的数据目录(各事件
    独立、各一行),写进一个临时目录的 train.jsonl / val.jsonl。"""
    tmpdir = tempfile.TemporaryDirectory()
    data_dir = Path(tmpdir.name)
    train_rows = [_mk_row(f"tr{i}", i) for i in range(n_train)]
    eval_rows = [_mk_row(f"ev{i}", 1000 + i) for i in range(n_eval)]
    _write_jsonl(train_rows, data_dir / "train.jsonl")
    _write_jsonl(eval_rows, data_dir / "val.jsonl")
    return tmpdir, data_dir


def _make_model_dir(tok):
    tmpdir = tempfile.TemporaryDirectory()
    model_dir = Path(tmpdir.name)
    torch.manual_seed(SEED)
    model = AutoModelForCausalLM.from_config(_tiny_config(len(tok)))
    model.save_pretrained(model_dir)
    tok.save_pretrained(model_dir)
    return tmpdir, model_dir


class TestGenEvalEndToEnd(unittest.TestCase):
    """(a) `--gen-eval 3 --gen-bs 2 --gen-eval-at all --eval-per-epoch 2`
    跑通,每条 `eval` 事件都有生成式评估的三个键、`gen_n == 3`;换
    `--gen-eval-at last` 时只有 `frac == 2` 那条有。(b) `--gen-eval 0` 时
    `eval` 事件没有这三个键。

    12 个训练事件(`--events-per-mb` 默认 4、`--accum` 默认 2)给出
    M=ceil(12/4)=3、U=ceil(3/2)=2,`--eval-per-epoch 2` 下 eval_points 是
    `{1: 1, 2: 2}`——两个评估点、两个不同的 frac,才分得出 all/last 的差别。
    6 个 val 事件(各一行)够 `--gen-eval 3` 抽样。
    """

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"分词器路径不存在:{QWEN_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)

    def _run(self, mode, extra_argv, out_name):
        data_tmp, data_dir = _make_data_dir(n_train=12, n_eval=6)
        model_tmp, model_dir = _make_model_dir(self.tok)
        try:
            with tempfile.TemporaryDirectory() as out_root:
                out = Path(out_root) / out_name
                argv = ["train_causal_share.py", "--mode", mode,
                       "--base", str(model_dir), "--data", str(data_dir),
                       "--out", str(out), "--max-events", "12",
                       "--eval-per-epoch", "2", "--log-every", "1",
                       "--device", "cpu", "--align-events", "2"] + extra_argv
                old_argv = sys.argv
                sys.argv = argv
                try:
                    tcs.main()
                finally:
                    sys.argv = old_argv
                events = []
                for line in open(out / "train_log.jsonl"):
                    events.append(json.loads(line))
                return events
        finally:
            data_tmp.cleanup()
            model_tmp.cleanup()

    def _eval_events(self, events):
        return [e for e in events if e["event"] == "eval"]

    def _check_mode_all(self, mode):
        exact_key = "val_exact_call" if mode == "cgen" else "val_exact_params"
        events = self._run(mode, ["--gen-eval", "3", "--gen-bs", "2",
                                  "--gen-eval-at", "all"], "run_all")
        evals = self._eval_events(events)
        self.assertEqual({e["frac"] for e in evals}, {1, 2},
                         f"应该有 frac=1、frac=2 两个评估点:{evals}")
        for e in evals:
            self.assertIn(exact_key, e, f"缺 {exact_key}:{e}")
            self.assertEqual(e["gen_n"], 3, f"gen_n 应该是 3:{e}")
            self.assertIn("gen_s", e, f"缺 gen_s:{e}")

    def _check_mode_last(self, mode):
        exact_key = "val_exact_call" if mode == "cgen" else "val_exact_params"
        events = self._run(mode, ["--gen-eval", "3", "--gen-bs", "2",
                                  "--gen-eval-at", "last"], "run_last")
        evals = self._eval_events(events)
        self.assertEqual({e["frac"] for e in evals}, {1, 2})
        by_frac = {e["frac"]: e for e in evals}
        self.assertNotIn(exact_key, by_frac[1],
                         f"gen-eval-at last 下 frac=1(非 epoch 末)不该有 "
                         f"{exact_key}:{by_frac[1]}")
        self.assertNotIn("gen_n", by_frac[1])
        self.assertNotIn("gen_s", by_frac[1])
        self.assertIn(exact_key, by_frac[2],
                      f"gen-eval-at last 下 frac=2(epoch 末)应该有 "
                      f"{exact_key}:{by_frac[2]}")
        self.assertEqual(by_frac[2]["gen_n"], 3)
        self.assertIn("gen_s", by_frac[2])

    def _check_mode_off(self, mode):
        exact_key = "val_exact_call" if mode == "cgen" else "val_exact_params"
        events = self._run(mode, ["--gen-eval", "0"], "run_off")
        evals = self._eval_events(events)
        self.assertTrue(evals)
        for e in evals:
            self.assertNotIn(exact_key, e, f"--gen-eval 0 时不该有 {exact_key}:{e}")
            self.assertNotIn("gen_n", e)
            self.assertNotIn("gen_s", e)

    def test_cgen_all(self):
        self._check_mode_all("cgen")

    def test_cgen_last(self):
        self._check_mode_last("cgen")

    def test_cgen_off(self):
        self._check_mode_off("cgen")

    def test_cparam_all(self):
        self._check_mode_all("cparam")

    def test_cparam_last(self):
        self._check_mode_last("cparam")

    def test_cparam_off(self):
        self._check_mode_off("cparam")


class TestSampleGenEvalRowsDeterministic(unittest.TestCase):
    """(c) 抽样函数单独测:同一批事件两次抽样结果相同。"""

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"分词器路径不存在:{QWEN_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)

    def _events(self, mode):
        data_tmp, data_dir = _make_data_dir(n_train=1, n_eval=10)
        try:
            events, _counts = share_data.load_events(
                data_dir / "val.jsonl", self.tok, mode=mode, max_len=8192,
                limit=0)
            return events
        finally:
            data_tmp.cleanup()

    def _check_mode(self, mode):
        events = self._events(mode)
        self.assertGreaterEqual(len(events), 5)
        a = tcs.sample_gen_eval_rows(events, mode, SEED, 5)
        b = tcs.sample_gen_eval_rows(events, mode, SEED, 5)
        self.assertEqual(a, b)
        self.assertEqual(len(a), 5)

    def test_cgen(self):
        self._check_mode("cgen")

    def test_cparam(self):
        self._check_mode("cparam")

    def test_n_greater_than_rows_takes_all(self):
        events = self._events("cgen")
        n_rows = sum(len(ev["rows"]) for ev in events)
        picked = tcs.sample_gen_eval_rows(events, "cgen", SEED, n_rows + 100)
        self.assertEqual(len(picked), n_rows)


class TestAttnCtxOnlyInForwardPacked(unittest.TestCase):
    """(d) 守卫测试(spec 16.10 #29):`_attn_ctx(...)` 的调用点只能在
    `_forward_packed` 内——无掩码的 `generate` 走 GQA,mem-efficient 内核
    报 `No available kernel`,后来有人把生成也包进 `_attn_ctx` 就会撞上
    这条。用 `ast` 找 `_attn_ctx` 的 `Call` 节点,断言父函数只有
    `_forward_packed`(`def _attn_ctx` 那一行本身是 `FunctionDef`,不是
    `Call`,不算调用)。"""

    def test_attn_ctx_called_only_inside_forward_packed(self):
        src_path = ROOT / "pipeline/train/train_causal_share.py"
        tree = ast.parse(src_path.read_text())

        class _Visitor(ast.NodeVisitor):
            def __init__(self):
                self.stack = []
                self.offenders = []

            def visit_FunctionDef(self, node):
                self.stack.append(node.name)
                self.generic_visit(node)
                self.stack.pop()

            def visit_Call(self, node):
                func = node.func
                name = func.id if isinstance(func, ast.Name) else None
                if name == "_attn_ctx":
                    caller = self.stack[-1] if self.stack else None
                    if caller != "_forward_packed":
                        self.offenders.append((caller, node.lineno))
                self.generic_visit(node)

        v = _Visitor()
        v.visit(tree)
        self.assertEqual(
            v.offenders, [],
            "spec 16.10 #29:_attn_ctx(...) 只能在 _forward_packed 内调用——"
            "无掩码的 model.generate 走 enable_gqa,mem-efficient 内核报 "
            f"No available kernel。发现调用点在别的函数里:{v.offenders}")


class TestEvalCeBeat(unittest.TestCase):
    """(e) `eval_ce` 的 `beat` 回调在块数 >= 25 时至少被调一次。

    30 个独立的单行小事件,`tok_budget` 卡到刚好只能放下一个事件(一个
    事件的补齐长度是 16 的倍数、两个事件的补齐长度之和必然 > 该预算),
    每个事件独自成一个物理块,给出 30 个物理块。
    """

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"分词器路径不存在:{QWEN_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)

    def test_beat_called_when_at_least_25_blocks(self):
        data_tmp, data_dir = _make_data_dir(n_train=1, n_eval=30)
        model_tmp, model_dir = _make_model_dir(self.tok)
        try:
            events, _counts = share_data.load_events(
                data_dir / "val.jsonl", self.tok, mode="cgen", max_len=8192,
                limit=0)
            self.assertGreaterEqual(len(events), 25)
            torch.manual_seed(SEED)
            model = AutoModelForCausalLM.from_config(_tiny_config(len(self.tok)))
            model.eval()
            # tok_budget = 全部事件里补齐长度最小的那个:任何一对事件的
            # cand_max 都不会小于这个值,2 * pad16(cand_max) 必然 > tok_budget
            # ——不管这 30 个事件的 packed_len 具体怎么分布,两两都装不进
            # 同一块,保证每个事件独自成一个物理块(30 块)。
            pads = [((ev["packed_len"] + 15) // 16) * 16 for ev in events]
            tok_budget = min(pads)

            calls = []
            with torch.no_grad():
                tcs.eval_ce(model, events, tok_budget, "cpu", amp=False,
                           beat=lambda: calls.append(1))
            self.assertGreaterEqual(len(calls), 1,
                                    "块数 >= 25 时 beat 应该至少被调一次")
        finally:
            data_tmp.cleanup()
            model_tmp.cleanup()

    def test_beat_none_does_not_crash(self):
        """`beat=None`(默认)不影响现有调用点——不传时不出错。"""
        data_tmp, data_dir = _make_data_dir(n_train=1, n_eval=3)
        try:
            events, _counts = share_data.load_events(
                data_dir / "val.jsonl", self.tok, mode="cgen", max_len=8192,
                limit=0)
            torch.manual_seed(SEED)
            model = AutoModelForCausalLM.from_config(_tiny_config(len(self.tok)))
            model.eval()
            with torch.no_grad():
                vce = tcs.eval_ce(model, events, 100000, "cpu", amp=False)
            self.assertIsInstance(vce, float)
        finally:
            data_tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
