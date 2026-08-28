"""tests/test_ctool_readpos.py —— 工单 `.scratch/kvshare-train/issues/
02-ctool-drop-readpos.md` 第 5 条 (a) 到 (d),对应 spec 第 11、12 节。

跑法(train_causal_tool.py/eval_tool.py 顶层都要 transformers>=5.14,只有
train_causal_tool.py 顶层显式做版本门,eval_tool.py 本身两个环境都能 import,
但本文件要用到 train_causal_tool.collate,所以整份要 cprobe-env):
  cprobe-env/bin/python -m unittest tests.test_ctool_readpos -v
系统 python3 跑全量 discover 时本模块整体 skip(没有 torch),不算失败;
mbert-env(transformers 4.57.6)下 import train_causal_tool 会 SystemExit
(顶层的 transformers>=5.14 版本门),一并兜住照样 skip,照
tests/test_cparam_assembly.py 第 21 到 29 行的写法。

真实 Qwen3-0.6B-Base 分词器路径不存在时,涉及它的用例 skipTest。
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline/train"))
sys.path.insert(0, str(ROOT / "pipeline/eval"))

try:
    import torch
    import share_data
    from transformers import AutoTokenizer
except ImportError as e:                       # 系统 python3 没有 torch
    raise unittest.SkipTest(f"要 cprobe-env 解释器:{e}")

try:
    import train_causal_tool                    # noqa: E402
except ImportError as e:                        # 系统 python3 没有 transformers
    raise unittest.SkipTest(f"要 cprobe-env 解释器:{e}")
except SystemExit as e:                         # mbert-env 的 transformers<5.14
    raise unittest.SkipTest(f"要 cprobe-env 解释器:{e}")

try:
    import eval_tool                            # noqa: E402
except ImportError as e:
    raise unittest.SkipTest(f"要 cprobe-env 解释器:{e}")
except SystemExit as e:
    raise unittest.SkipTest(f"要 cprobe-env 解释器:{e}")

QWEN_PATH = train_causal_tool.MODELS["qwen"]


def _write_jsonl(rows, path):
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _grow_until(tok, base, min_tokens):
    """把 `base` 重复拼接,直到 token 数 > `min_tokens`(照 test_share_data.py)。"""
    s = base
    while len(tok(s, add_special_tokens=False)["input_ids"]) <= min_tokens:
        s = s + " " + base
    return s


class TestReadPositionManual(unittest.TestCase):
    """(a) 手造 offsets 验证读取位置规则(直接测 share_data.read_position)。"""

    def test_read_across_cut(self):
        # full[0:2]='Sp' offset(0,2); [2:7]='otify' offset(2,7);
        # [7:11]='."\n\n' offset(7,11); [11:13]='We' offset(11,13)。
        # 切点 10 落在第三个 token 内部(覆盖 '\n' 之后到下一个 token 之前),
        # end_j=11>10 且 full_text[10:11]='\n' 是空白 -> 读 j。
        offsets = [(0, 2), (2, 7), (7, 11), (11, 13)]
        full_text = 'Spotify."\n\nWe'
        j = share_data.read_position(offsets, full_text, 10, 4)
        self.assertEqual(j, 2)
        self.assertEqual(offsets[j], (7, 11))

    def test_backoff_to_prior_token(self):
        offsets = [(0, 4), (4, 5), (5, 10)]
        full_text = "done. Next"
        j = share_data.read_position(offsets, full_text, 6, 3)
        self.assertEqual(j, 1)
        self.assertEqual(offsets[j], (4, 5))


class TestCollateReadPosition(unittest.TestCase):
    """(a) 续:collate 走新规则(share_data.read_position)在真实分词器一个
    事件上读出的列下标,与直接调用 read_position 的结果一致。"""

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"分词器路径不存在:{QWEN_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)
        if cls.tok.pad_token_id is None:
            cls.tok.pad_token = cls.tok.eos_token
        cls.tok.truncation_side = "left"
        cls.tok.padding_side = "right"

    def test_collate_matches_read_position(self):
        full = 'Spotify."\n\nWe are done here now.'
        enc = self.tok(full, add_special_tokens=False,
                       return_offsets_mapping=True)
        offsets = enc["offset_mapping"]
        cut = 10
        expected_j = share_data.read_position(offsets, full, cut, len(offsets))
        self.assertGreaterEqual(expected_j, 0)
        self.assertEqual(offsets[expected_j], (7, 11))   # 覆盖 '."\n\n' 的 token

        event = dict(event="ev_a", full=full, y=0, bounds=[(cut, 1.0, True)])
        enc2, rows, cols, ys, ws, lasts, dropped = train_causal_tool.collate(
            [event], self.tok, max_len=4096)
        self.assertEqual(dropped, 0)
        self.assertEqual(cols.tolist(), [expected_j])


class TestLoadEventsDropCount(unittest.TestCase):
    """(b) train_causal_tool.load_events 的事件级丢弃计数。"""

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"分词器路径不存在:{QWEN_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)

    def test_event_over_max_len_dropped_and_counted(self):
        short_text = "Please handle this short request right now."
        max_len = len(self.tok(short_text,
                               add_special_tokens=False)["input_ids"]) + 3
        long_text = _grow_until(self.tok, "word", max_len + 20)
        rows = [
            dict(event="ev_short", sent_idx=0, n_sents=1, text=short_text,
                label="apis.a", label_call="apis.a(x=1)", w=1.0),
            dict(event="ev_long", sent_idx=0, n_sents=1, text=long_text,
                label="apis.a", label_call="apis.a(x=1)", w=1.0),
        ]
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "data.jsonl")
            _write_jsonl(rows, path)
            label2id = {"apis.a": 0}
            events, dropped = train_causal_tool.load_events(
                path, label2id, self.tok, max_len)
            self.assertEqual(dropped, 1)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event"], "ev_short")


class _StubBackbone:
    """只为 score_causal 提供形状正确的 last_hidden_state,数值不参与判读——
    (c)/(d) 只关心读取位置选中的列下标,不关心 gather 出来的数值本身。"""

    def __init__(self, hidden=4):
        self.hidden = hidden

    def __call__(self, input_ids, attention_mask, use_cache=False):
        class _Out:
            pass
        o = _Out()
        b, l = input_ids.shape
        o.last_hidden_state = torch.zeros(b, l, self.hidden)
        return o


class TestTrainEvalReadPositionAgree(unittest.TestCase):
    """(c) collate 与 score_causal 对同一全文、同一批切点读出相同下标
    (上限以内的事件;超上限训练侧丢弃、评测侧左截,不进这条)。"""

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"分词器路径不存在:{QWEN_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)
        if cls.tok.pad_token_id is None:
            cls.tok.pad_token = cls.tok.eos_token
        cls.tok.truncation_side = "left"
        cls.tok.padding_side = "right"

    def _spy(self, target_list):
        orig = share_data.read_position

        def _f(offsets, full_text, cut, keep):
            r = orig(offsets, full_text, cut, keep)
            target_list.append((cut, r))
            return r
        return _f

    def test_agree_within_max_len(self):
        full = ("Alpha beta gamma delta epsilon. " * 4
                + "Zeta eta theta iota kappa, done here now.")
        max_len = 4096
        self.assertLess(
            len(self.tok(full, add_special_tokens=False)["input_ids"]),
            max_len)                            # 防呆:确认在上限以内
        cut_points = [20, 45, 90, len(full)]

        train_event = dict(event="ev1", full=full, y=0,
                           bounds=[(c, 1.0, i == len(cut_points) - 1)
                                   for i, c in enumerate(cut_points)])
        eval_rows = [dict(event="ev1", sent_idx=i, text=full[:c])
                    for i, c in enumerate(cut_points)]

        orig = share_data.read_position
        calls_train, calls_eval = [], []
        try:
            share_data.read_position = self._spy(calls_train)
            train_causal_tool.collate([train_event], self.tok, max_len)
        finally:
            share_data.read_position = orig

        head = torch.nn.Linear(4, 1)
        try:
            share_data.read_position = self._spy(calls_eval)
            eval_tool.score_causal(_StubBackbone(), head, self.tok,
                                   eval_rows, "cpu", max_len, bs=1)
        finally:
            share_data.read_position = orig

        self.assertEqual(len(calls_train), len(cut_points))
        self.assertEqual(calls_train, calls_eval)
        self.assertTrue(all(j >= 0 for _c, j in calls_train))  # 全在上限以内


class TestScoreCausalOutOfWindow(unittest.TestCase):
    """(d) score_causal 在左截事件上,窗口外的切点计入 n_oow 而不落进 cols。"""

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"分词器路径不存在:{QWEN_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)
        if cls.tok.pad_token_id is None:
            cls.tok.pad_token = cls.tok.eos_token
        cls.tok.truncation_side = "left"
        cls.tok.padding_side = "right"

    def test_out_of_window_cut_not_in_cols(self):
        early = "zero one two three four five six seven eight nine ten. "
        late = ("eleven twelve thirteen fourteen fifteen sixteen seventeen "
               "eighteen nineteen twenty twenty-one twenty-two twenty-three "
               "twenty-four twenty-five twenty-six twenty-seven twenty-eight.")
        full = early + late
        n_full = len(self.tok(full, add_special_tokens=False)["input_ids"])
        n_late = len(self.tok(late, add_special_tokens=False)["input_ids"])
        max_len = n_late                        # 保证会左截,丢掉 early 那部分
        self.assertLess(max_len, n_full)

        # 权重清零、偏置定值:凡是被 gather 过的行 = bias,没被 gather 过的行
        # 保持初始化的 0(与 out = torch.zeros(...) 一致),用输出本身分辨
        # 该切点有没有落进 cols。
        head = torch.nn.Linear(4, 1)
        head.weight.data.zero_()
        head.bias.data.fill_(1.0)

        early_cut = 3                          # 落在 early 里,左截后必定窗口外
        eval_rows = [
            dict(event="ev1", sent_idx=0, text=full[:early_cut]),
            dict(event="ev1", sent_idx=1, text=full),   # 最后一行 = 全文,靠尾部保留
        ]
        out, excluded_idx, counts = eval_tool.score_causal(
            _StubBackbone(), head, self.tok, eval_rows, "cpu", max_len, bs=1)
        self.assertEqual(excluded_idx, [])               # left:不剔除任何行
        self.assertEqual(counts["n_oow"], 1)
        self.assertEqual(out[0, 0].item(), 0.0)          # 窗口外:未被 gather
        self.assertEqual(out[1, 0].item(), 1.0)          # 窗口内:gather 到 bias


class TestPeakMemGb(unittest.TestCase):
    """工单 06 第 3 条:`step`/`eval` 事件加 `peak_mem_gb`,和新训练器
    `train_causal_share.py` 同口径(cuda 上读 `max_memory_allocated` 并清空
    峰值统计,CPU 上恒 0.0)。本文件没有能跑到 `step` 事件的 CPU 用例
    (`main()` 需要 `--base`/`--data` 的真实分词器与数据集,本文件其余用例
    都是直接调 `collate`/`score_causal` 这一层),按工单第 3 条的退路,只测
    写这个字段的函数 `_peak_mem_gb` 本身。"""

    def test_cpu_returns_zero(self):
        self.assertEqual(train_causal_tool._peak_mem_gb("cpu"), 0.0)

    def test_cpu_repeated_calls_stay_zero(self):
        # CPU 分支不摸 torch.cuda,重复调用不该因为"没 reset"而累积或报错。
        for _ in range(3):
            self.assertEqual(train_causal_tool._peak_mem_gb("cpu"), 0.0)


if __name__ == "__main__":
    unittest.main()
