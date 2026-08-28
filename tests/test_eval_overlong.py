"""tests/test_eval_overlong.py —— spec `.scratch/kvshare-train/spec.md`
16.9 第一条,对应工单 `.scratch/kvshare-train/issues/07-eval-overlong.md`。

跑法(share_data.py/eval_tool.py 顶层都要 torch,`train_causal_tool` 顶层有
transformers>=5.14 版本门,所以整份要 cprobe-env):
  cprobe-env/bin/python -m unittest tests.test_eval_overlong -v
系统 python3 跑全量 discover 时本模块整体 skip(没有 torch),不算失败;
mbert-env(transformers 4.57.6)下 import train_causal_tool/eval_tool 会
SystemExit(顶层的 transformers>=5.14 版本门),一并兜住照样 skip(照
tests/test_ctool_readpos.py 的写法)。

真实 Qwen3-0.6B-Base 分词器路径不存在时,涉及它的用例 skipTest。全部用例
手造小事件/小模型,不读 pipeline/data/ 下的现役数据目录。
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
    import transformers
    import share_data
    from transformers import AutoModel, AutoModelForCausalLM, AutoTokenizer
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

try:
    import eval_causal_call                     # noqa: E402
    import eval_causal_param                    # noqa: E402
except ImportError as e:
    raise unittest.SkipTest(f"要 cprobe-env 解释器:{e}")

QWEN_PATH = train_causal_tool.MODELS["qwen"]


def _row(event, sent_idx, n_sents, text, label, label_call, w=1.0):
    return dict(event=event, sent_idx=sent_idx, n_sents=n_sents, text=text,
               label=label, label_call=label_call, w=w)


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


def _tiny_causal_config(vocab_size):
    """两层 Qwen3,规模小到 CPU 秒级(照 tests/test_share_trainer.py 的
    `_tiny_config`)。"""
    return transformers.Qwen3Config(
        hidden_size=64, intermediate_size=128, num_hidden_layers=2,
        num_attention_heads=4, num_key_value_heads=2, head_dim=16,
        vocab_size=vocab_size, max_position_embeddings=8192,
        tie_word_embeddings=False)


class TestNFullTokensMatchesLoadEvents(unittest.TestCase):
    """(a) `n_full_tokens`/`full_token_ids` 与 `load_events` 的
    `dropped_events` 判据用同一个数,一致。"""

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"分词器路径不存在:{QWEN_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)

    def test_matches_load_events_drop(self):
        short_text = "Please handle this request right now quickly."
        max_len = len(self.tok(short_text,
                              add_special_tokens=False)["input_ids"]) + 5
        long_full_text = _grow_until(self.tok, "word", max_len + 20)

        rows = [
            _row("ev_normal", 0, 1, short_text,
                "apis.a.call", "apis.a.call(x=1)"),
            _row("ev_long", 0, 1, long_full_text,
                "apis.a.call", "apis.a.call(x=1)"),
        ]
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "data.jsonl")
            _write_jsonl(rows, path)
            events, counts = share_data.load_events(
                path, self.tok, mode="cgen", max_len=max_len, limit=0)

        self.assertEqual(counts["dropped_events"], 1)
        kept = {e["event"] for e in events}
        self.assertIn("ev_normal", kept)
        self.assertNotIn("ev_long", kept)

        # 同一段文本上,n_full_tokens 的丢弃判据与 load_events 的一致
        self.assertGreater(share_data.n_full_tokens(self.tok, long_full_text),
                           max_len)
        self.assertLessEqual(
            share_data.n_full_tokens(self.tok, short_text), max_len)
        # full_token_ids 与 n_full_tokens 是同一次分词的两个产物
        self.assertEqual(
            len(share_data.full_token_ids(self.tok, long_full_text)),
            share_data.n_full_tokens(self.tok, long_full_text))


class TestSelectKeys(unittest.TestCase):
    """(b) `share_data.select_keys` 三种模式的计数与留下的 key 集合,以及
    给定 `excluded_rows` 时的剔除(部分行被剔的事件留下、全部候选行被剔的
    事件去掉并计入 `n_excluded_by_ctool`)。不需要真实分词器/模型——纯手造
    的 dict 输入。
    """

    def setUp(self):
        # e1/e2/e4 的提示长度不超阈值;e3 超阈值(left/drop-event 里被左截
        # 计数,skip 里整行被剔);e2 的事件全文超 max_len(drop-event 专属);
        # e4 只有部分候选行被 ctool 剔除(留下);e5 唯一的候选行被 ctool
        # 剔光(整个 key 去掉,计 n_excluded_by_ctool)。
        self.keys = {"e1": [0, 1], "e2": [2, 3], "e3": [4],
                    "e4": [5, 6], "e5": [7]}
        self.n_full = {"e1": 100, "e2": 5000, "e3": 50, "e4": 10, "e5": 10}
        self.prompt_len = {"e1": 30, "e2": 30, "e3": 90, "e4": 10, "e5": 10}
        self.excluded_rows = {5, 7}     # e4 剔一行留一行;e5 唯一候选行被剔
        self.max_len = 100
        self.max_new = 20               # thresh = 80

    def _call(self, mode):
        return share_data.select_keys(
            mode, self.keys, self.n_full, self.prompt_len,
            self.excluded_rows, self.max_len, self.max_new)

    def test_left(self):
        kept, counts = self._call("left")
        self.assertEqual(kept, ["e1", "e2", "e3", "e4"])
        self.assertEqual(counts, dict(n_left_truncated=1, n_skipped_rows=0,
                                      n_dropped_events=0,
                                      n_excluded_by_ctool=1))

    def test_skip(self):
        kept, counts = self._call("skip")
        self.assertEqual(kept, ["e1", "e2", "e4"])
        self.assertEqual(counts, dict(n_left_truncated=0, n_skipped_rows=1,
                                      n_dropped_events=0,
                                      n_excluded_by_ctool=1))

    def test_drop_event(self):
        kept, counts = self._call("drop-event")
        self.assertEqual(kept, ["e1", "e3", "e4"])
        self.assertEqual(counts, dict(n_left_truncated=1, n_skipped_rows=0,
                                      n_dropped_events=1,
                                      n_excluded_by_ctool=1))

    def test_bad_mode(self):
        with self.assertRaises(ValueError):
            share_data.select_keys("bogus", self.keys, self.n_full,
                                   self.prompt_len, self.excluded_rows,
                                   self.max_len, self.max_new)


class TestCparamPromptLenMaxRule(unittest.TestCase):
    """(b 附加)cparam 用例:一个 key 的真值/预测工具名提示 token 数不同,
    只有 pred_tool 那套超过 `max_len - max_new`。`L(k)` 取两套的最大值
    (`eval_causal_param.py` main() 里内联的同一段算法,这里直接照抄那段
    算法验证,不跑整份需要模型 run 目录的 main())。
    """

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"分词器路径不存在:{QWEN_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)

    def test_max_of_two_tags(self):
        gt_text = "short prompt with the true tool name"
        len_gt = len(self.tok(gt_text, add_special_tokens=False,
                             truncation=False)["input_ids"])
        max_len = len_gt + 5
        max_new = 0                      # thresh = max_len,简化算术
        pred_text = _grow_until(self.tok, "word", max_len)
        len_pred = len(self.tok(pred_text, add_special_tokens=False,
                               truncation=False)["input_ids"])
        self.assertLessEqual(len_gt, max_len)
        self.assertGreater(len_pred, max_len)

        keys = {"k1": [0]}
        prompt_len = {"k1": max(len_gt, len_pred)}
        excluded_rows = set()

        # skip:两套提示的最大值超阈值,整个 key 被剔(最大值规则)
        kept, counts = share_data.select_keys(
            "skip", keys, {}, prompt_len, excluded_rows, max_len, max_new)
        self.assertEqual(kept, [])
        self.assertEqual(counts["n_skipped_rows"], 1)

        # left:key 留下,同时按 eval_causal_param.py 内联的算法逐 tag 计
        # n_left_truncated_by_tag
        kept, counts = share_data.select_keys(
            "left", keys, {}, prompt_len, excluded_rows, max_len, max_new)
        self.assertEqual(kept, ["k1"])
        self.assertEqual(counts["n_left_truncated"], 1)
        thresh = max_len - max_new
        tag_len = {"k1": {"gt_tool": len_gt, "pred_tool": len_pred}}
        n_left_truncated_by_tag = {"gt_tool": 0, "pred_tool": 0}
        for k in kept:
            for tag in ("gt_tool", "pred_tool"):
                if tag_len[k][tag] > thresh:
                    n_left_truncated_by_tag[tag] += 1
        self.assertEqual(n_left_truncated_by_tag,
                         {"gt_tool": 0, "pred_tool": 1})


class _IdentityGenerate:
    """把 `eval_causal_call.generate` / `eval_causal_param.generate` 换成
    回声:直接把喂进去的 prompt 原样当"生成结果"返回。测的是触发点/候选行
    怎么挑出来这一段接线,不是模型真会不会写调用——真模型的输出不可控,
    回声让报告里的 `gen` 字段直接暴露"喂给模型的 prompt 到底含哪一行 text",
    从而能断言挑中的是重新选出来的那一行,不是被 ctool 剔除的原触发行。
    """

    def __call__(self, model, tok, prompts, dev, bs, max_len, max_new,
                tag=None):
        return list(prompts)


class TestCgenCtoolExclusionWiring(unittest.TestCase):
    """(b 附加 2)`eval_causal_call.py` 端到端接线(F1 的回归测试):ctool
    剔除的行不许当触发点候选,候选行剔光的事件计入 `n_excluded_by_ctool`
    且不判分,部分候选行被剔的事件要在剩下的行里重新挑触发点——不是靠"零
    logits 天然过不了 θ"这个巧合。只手造一个真实分词器 + 随机初始化的两层
    模型,`generate` 换成回声,不依赖任何现役 run 目录。
    """

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"分词器路径不存在:{QWEN_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)

    def test_reselect_and_count_excluded(self):
        torch.manual_seed(20260828)
        model = AutoModelForCausalLM.from_config(
            _tiny_causal_config(len(self.tok)))
        model.eval()

        rows = [
            _row("ev_reselect", 0, 2, "ROW0 EXCLUDED CONFIDENT TEXT",
                "apis.a", "apis.a(x=1)"),
            _row("ev_reselect", 1, 2, "ROW1 SURVIVING TEXT",
                "apis.a", "apis.a(x=1)"),
            _row("ev_full_excl", 0, 2, "ROW2 FULL EXCL A",
                "apis.a", "apis.a(x=2)"),
            _row("ev_full_excl", 1, 2, "ROW3 FULL EXCL B",
                "apis.a", "apis.a(x=2)"),
            _row("ev_normal", 0, 1, "ROW4 NORMAL TEXT",
                "apis.a", "apis.a(x=3)"),
        ]
        for r in rows:
            r["args_named"] = []
        # row0(被剔除,logits 故意比 θ 高得多——「剔除的行不许当候选」这条
        # 不能靠 θ 天然挡住,得靠接线本身挡);row1(存活,conf 略过 θ,event
        # 该重新挑到这一行);row2/row3(整个事件都被剔除,logits 是 ctool
        # 真实产出的零 logits,conf=0.5<θ,老接线里这类事件本来就不会
        # "fired",既不计入已触发也不计入 n_excluded_by_ctool,静默消失——
        # 这正是 F1 指出的缺口);row4(正常触发,基线对照)。
        logits = torch.tensor([
            [10.0, -10.0],
            [3.0, -3.0],
            [0.0, 0.0],
            [0.0, 0.0],
            [5.0, -5.0],
        ])
        excluded_idx = [0, 2, 3]
        theta = 0.9

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            ctool_dir, cgen_dir, data_dir = (root / "ctool", root / "cgen",
                                             root / "data")
            (ctool_dir / "best").mkdir(parents=True)
            (cgen_dir / "best").mkdir(parents=True)
            data_dir.mkdir()

            _write_jsonl(rows, data_dir / "test.jsonl")
            (ctool_dir / "best" / "label_map.json").write_text(
                json.dumps({"apis.a": 0, "apis.b": 1}))
            (ctool_dir / "best" / "meta.json").write_text(
                json.dumps({"data": str(data_dir)}))
            (ctool_dir / "REPLAY_REPORT.json").write_text(json.dumps(
                {"temperature": 1.0, "chosen_theta": {"0.05": theta}}))
            torch.save(logits, ctool_dir / "logits_test.pt")
            (ctool_dir / "logits_test.meta.json").write_text(
                json.dumps({"excluded_idx": excluded_idx}))

            self.tok.save_pretrained(cgen_dir / "best")
            model.save_pretrained(cgen_dir / "best")
            (cgen_dir / "best" / "meta.json").write_text(json.dumps(
                {"call_sep": "\n[CALL] ", "max_len": 4096,
                 "data": str(data_dir)}))

            argv = ["eval_causal_call.py", "--env", "appworld",
                   "--ctool-run", str(ctool_dir), "--cgen-run", str(cgen_dir),
                   "--data", str(data_dir), "--risk", "0.05",
                   "--device", "cpu", "--bs", "2", "--overlong", "left"]
            old_argv = sys.argv
            old_generate = eval_causal_call.generate
            try:
                sys.argv = argv
                eval_causal_call.generate = _IdentityGenerate()
                eval_causal_call.main()
            finally:
                sys.argv = old_argv
                eval_causal_call.generate = old_generate

            out = json.loads((cgen_dir / "CALLGEN_REPORT.json").read_text())

        self.assertEqual(out["n_events_test"], 3)
        self.assertEqual(out["n_events_fired"], 2,
                         "ev_full_excl 的两行都是零 logits,不该被算作已触发")
        self.assertEqual(out["n_excluded_by_ctool"], 1)
        self.assertEqual(out["n_events_scored"], 2)

        by_event = {s["event"]: s for s in out["samples"]}
        self.assertIn("ev_reselect", by_event)
        self.assertNotIn("ev_full_excl", by_event)
        gen = by_event["ev_reselect"]["gen"]
        self.assertIn("ROW1 SURVIVING TEXT", gen,
                     "触发点该重新挑到剩下的那一行")
        self.assertNotIn("ROW0 EXCLUDED CONFIDENT TEXT", gen,
                         "被 ctool 剔除的行不许当触发点候选,不管它的 logits"
                         "多自信")


class TestCparamCtoolExclusionWiring(unittest.TestCase):
    """(b 附加 3)`eval_causal_param.py` 端到端接线(F2 的回归测试),与
    `TestCgenCtoolExclusionWiring` 同构。"""

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"分词器路径不存在:{QWEN_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)

    def test_reselect_and_count_excluded(self):
        torch.manual_seed(20260828)
        model = AutoModelForCausalLM.from_config(
            _tiny_causal_config(len(self.tok)))
        model.eval()

        rows = [
            _row("ev_reselect", 0, 2, "ROW0 EXCLUDED CONFIDENT TEXT",
                "apis.a", "apis.a(x=1)"),
            _row("ev_reselect", 1, 2, "ROW1 SURVIVING TEXT",
                "apis.a", "apis.a(x=1)"),
            _row("ev_full_excl", 0, 2, "ROW2 FULL EXCL A",
                "apis.a", "apis.a(x=2)"),
            _row("ev_full_excl", 1, 2, "ROW3 FULL EXCL B",
                "apis.a", "apis.a(x=2)"),
            _row("ev_normal", 0, 1, "ROW4 NORMAL TEXT",
                "apis.a", "apis.a(x=3)"),
        ]
        for r in rows:
            r["args_named"] = []
        logits = torch.tensor([
            [10.0, -10.0],
            [3.0, -3.0],
            [0.0, 0.0],
            [0.0, 0.0],
            [5.0, -5.0],
        ])
        excluded_idx = [0, 2, 3]
        theta = 0.9

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            ctool_dir, cparam_dir, data_dir = (root / "ctool",
                                               root / "cparam", root / "data")
            (ctool_dir / "best").mkdir(parents=True)
            (cparam_dir / "best").mkdir(parents=True)
            data_dir.mkdir()

            _write_jsonl(rows, data_dir / "test.jsonl")
            (ctool_dir / "best" / "label_map.json").write_text(
                json.dumps({"apis.a": 0, "apis.b": 1}))
            (ctool_dir / "best" / "meta.json").write_text(
                json.dumps({"data": str(data_dir)}))
            (ctool_dir / "REPLAY_REPORT.json").write_text(json.dumps(
                {"temperature": 1.0, "chosen_theta": {"0.05": theta}}))
            torch.save(logits, ctool_dir / "logits_test.pt")
            (ctool_dir / "logits_test.meta.json").write_text(
                json.dumps({"excluded_idx": excluded_idx}))

            self.tok.save_pretrained(cparam_dir / "best")
            model.save_pretrained(cparam_dir / "best")
            (cparam_dir / "best" / "meta.json").write_text(json.dumps(
                {"call_sep": "\n[CALL] ", "max_len": 4096,
                 "data": str(data_dir), "param_only": True}))

            argv = ["eval_causal_param.py", "--env", "appworld",
                   "--ctool-run", str(ctool_dir),
                   "--cparam-run", str(cparam_dir),
                   "--data", str(data_dir), "--risk", "0.05",
                   "--device", "cpu", "--bs", "2", "--overlong", "left"]
            old_argv = sys.argv
            old_generate = eval_causal_param.generate
            try:
                sys.argv = argv
                eval_causal_param.generate = _IdentityGenerate()
                eval_causal_param.main()
            finally:
                sys.argv = old_argv
                eval_causal_param.generate = old_generate

            out = json.loads((cparam_dir / "PARAM_REPORT.json").read_text())

        self.assertEqual(out["n_events_test"], 3)
        self.assertEqual(out["n_events_fired"], 2,
                         "ev_full_excl 的两行都是零 logits,不该被算作已触发")
        self.assertEqual(out["n_excluded_by_ctool"], 1)
        self.assertEqual(out["n_events_scored"], 2)

        by_event = {s["event"]: s for s in out["gt_tool"]["samples"]}
        self.assertIn("ev_reselect", by_event)
        self.assertNotIn("ev_full_excl", by_event)
        gen = by_event["ev_reselect"]["gen"]
        self.assertIn("ROW1 SURVIVING TEXT", gen,
                     "触发点该重新挑到剩下的那一行")
        self.assertNotIn("ROW0 EXCLUDED CONFIDENT TEXT", gen,
                         "被 ctool 剔除的行不许当触发点候选,不管它的 logits"
                         "多自信")


class TestCgenDropEventFullTextUsesRawRows(unittest.TestCase):
    """终审 F1 回归测试:`--overlong drop-event` 取事件全文要用 share_data
    的规则(不按 ctool 词表过滤行,取 `sent_idx` 最大那行的 `text`),不能
    套用 ctool 过滤后的 `rows`。手造一个事件:`sent_idx` 最大的那一行标签
    不在 ctool 词表里(会被 `label in label2id` 过滤掉),只有算上这一行的
    全文才会超过 `max_len`——套错口径(用过滤后的 `rows`)会漏看这一行,
    误判成没超长;改对之后(用 `raw_rows`)才会正确地把整个事件丢掉。
    """

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"分词器路径不存在:{QWEN_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)

    def test_event_with_out_of_vocab_last_row_gets_dropped(self):
        torch.manual_seed(20260829)
        model = AutoModelForCausalLM.from_config(
            _tiny_causal_config(len(self.tok)))
        model.eval()

        short_text_a = "Please handle this quick request now."
        short_text_b = "This is a different short event text."
        max_len = len(self.tok(short_text_a,
                              add_special_tokens=False)["input_ids"]) + 20
        # 只有把 sent_idx=1 这一行(标签不在词表里)的全文算进去,事件全文
        # 才会超过 max_len;词表过滤后剩下的 sent_idx=0 全文远低于 max_len。
        long_full_text = _grow_until(self.tok, "word", max_len + 20)

        rows = [
            # ev_drop 的触发点(sent_idx=0,标签在词表里,会被判为 fired):
            # 全文本身不长,套错口径时事件全文就等于这一行,判不出超长。
            _row("ev_drop", 0, 2, short_text_a, "apis.a", "apis.a(x=1)"),
            # sent_idx 最大的一行,标签不在 ctool 词表里,会被
            # `label in label2id` 整行过滤掉——但 share_data 的规则要求
            # 全文口径必须看到这一行。
            _row("ev_drop", 1, 2, long_full_text, "apis.zzz", "apis.zzz(x=1)"),
            # 基线对照:正常短事件,drop-event 下不该被丢。
            _row("ev_keep", 0, 1, short_text_b, "apis.a", "apis.a(x=2)"),
        ]
        for r in rows:
            r["args_named"] = []
        # 过滤后只剩 ev_drop 的 sent_idx=0 与 ev_keep 的 sent_idx=0 两行,
        # 顺序与 raw_rows 里的先后一致;两行都给高置信度让它们都能触发。
        logits = torch.tensor([
            [10.0, -10.0],
            [10.0, -10.0],
        ])
        theta = 0.9

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            ctool_dir, cgen_dir, data_dir = (root / "ctool", root / "cgen",
                                             root / "data")
            (ctool_dir / "best").mkdir(parents=True)
            (cgen_dir / "best").mkdir(parents=True)
            data_dir.mkdir()

            _write_jsonl(rows, data_dir / "test.jsonl")
            (ctool_dir / "best" / "label_map.json").write_text(
                json.dumps({"apis.a": 0, "apis.b": 1}))
            (ctool_dir / "best" / "meta.json").write_text(
                json.dumps({"data": str(data_dir)}))
            (ctool_dir / "REPLAY_REPORT.json").write_text(json.dumps(
                {"temperature": 1.0, "chosen_theta": {"0.05": theta}}))
            torch.save(logits, ctool_dir / "logits_test.pt")

            self.tok.save_pretrained(cgen_dir / "best")
            model.save_pretrained(cgen_dir / "best")
            (cgen_dir / "best" / "meta.json").write_text(json.dumps(
                {"call_sep": "\n[CALL] ", "max_len": max_len,
                 "data": str(data_dir)}))

            argv = ["eval_causal_call.py", "--env", "appworld",
                   "--ctool-run", str(ctool_dir), "--cgen-run", str(cgen_dir),
                   "--data", str(data_dir), "--risk", "0.05",
                   "--device", "cpu", "--bs", "2", "--overlong", "drop-event",
                   "--max-new-tokens", "0"]
            old_argv = sys.argv
            old_generate = eval_causal_call.generate
            try:
                sys.argv = argv
                eval_causal_call.generate = _IdentityGenerate()
                eval_causal_call.main()
            finally:
                sys.argv = old_argv
                eval_causal_call.generate = old_generate

            out = json.loads((cgen_dir / "CALLGEN_REPORT.json").read_text())

        self.assertEqual(out["n_dropped_events"], 1)
        self.assertEqual(out["n_events_fired"], 2,
                         "两个事件的触发行都给了高置信度,该都触发")
        self.assertEqual(out["n_events_scored"], 1,
                         "ev_drop 该被 drop-event 丢掉,只剩 ev_keep 判分")
        by_event = {s["event"]: s for s in out["samples"]}
        self.assertNotIn("ev_drop", by_event,
                         "sent_idx 最大那行(标签不在词表里)的全文超长,"
                         "事件该被丢——套错口径(过滤后的 rows)会漏看这一行")
        self.assertIn("ev_keep", by_event)


class TestScoreCausalOverlong(unittest.TestCase):
    """(c) `eval_tool.score_causal` 三种模式下 `out` 行数都等于输入行数、
    `excluded_idx` 与计数各对、被剔除行的 logits 全零。小模型:
    `Qwen3Config` 随机初始化的两层 backbone + 一个线性头(照
    `tests/test_share_trainer.py` 的做法)。
    """

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"分词器路径不存在:{QWEN_PATH}")
        cls.tok = AutoTokenizer.from_pretrained(QWEN_PATH)
        if cls.tok.pad_token_id is None:
            cls.tok.pad_token = cls.tok.eos_token
        cls.tok.truncation_side = "left"
        cls.tok.padding_side = "right"

        torch.manual_seed(20260828)
        cls.backbone = AutoModel.from_config(
            _tiny_causal_config(len(cls.tok))).eval()
        cls.head = torch.nn.Linear(64, 3)
        cls.head.weight.data.zero_()
        cls.head.bias.data = torch.tensor([1.0, 2.0, 3.0])

        # ev1:early 段被左截掉之后落在窗口外(row0 的边界在 early 里),
        # tail 段(row1 = 整段全文)保留在窗口内;full 的 token 数超过
        # max_len,drop-event 下整个事件被丢。ev2:短事件,始终在窗口内。
        # early/late/max_len/early_cut 的构造照抄
        # tests/test_ctool_readpos.py 的 TestScoreCausalOutOfWindow,已验证
        # 能稳定触发左截窗口外。
        early = "zero one two three four five six seven eight nine ten. "
        late = ("eleven twelve thirteen fourteen fifteen sixteen seventeen "
               "eighteen nineteen twenty twenty-one twenty-two twenty-three "
               "twenty-four twenty-five twenty-six twenty-seven twenty-eight.")
        cls.full = early + late
        n_late = len(cls.tok(late, add_special_tokens=False)["input_ids"])
        n_full_total = len(
            cls.tok(cls.full, add_special_tokens=False)["input_ids"])
        cls.max_len = n_late
        assert cls.max_len < n_full_total, "构造不满足会左截的前提"
        cls.early_cut = 3                       # 落在 early 里,左截后必定窗口外

        cls.short_text = "a short normal event that fits easily"
        assert share_data.n_full_tokens(cls.tok, cls.short_text) < cls.max_len

        cls.rows = [
            dict(event="ev1", sent_idx=0, text=cls.full[:cls.early_cut]),
            dict(event="ev1", sent_idx=1, text=cls.full),
            dict(event="ev2", sent_idx=0, text=cls.short_text),
        ]

    def test_left(self):
        out, excluded_idx, counts = eval_tool.score_causal(
            self.backbone, self.head, self.tok, self.rows, "cpu",
            self.max_len, bs=2, overlong="left")
        self.assertEqual(out.shape[0], len(self.rows))
        self.assertEqual(excluded_idx, [])
        self.assertGreaterEqual(counts["n_oow"], 1)
        self.assertEqual(counts["n_skipped_bounds"], 0)
        self.assertEqual(counts["n_dropped_events"], 0)
        self.assertEqual(counts["n_dropped_bounds"], 0)
        self.assertEqual(out[0].abs().sum().item(), 0.0)   # 窗口外:零 logits
        self.assertTrue(torch.equal(out[1], self.head.bias.detach()))
        self.assertTrue(torch.equal(out[2], self.head.bias.detach()))

    def test_skip(self):
        out, excluded_idx, counts = eval_tool.score_causal(
            self.backbone, self.head, self.tok, self.rows, "cpu",
            self.max_len, bs=2, overlong="skip")
        self.assertEqual(out.shape[0], len(self.rows))
        self.assertEqual(excluded_idx, [0])
        self.assertEqual(counts["n_skipped_bounds"], 1)
        self.assertGreaterEqual(counts["n_oow"], 1)
        self.assertEqual(counts["n_dropped_events"], 0)
        self.assertEqual(out[0].abs().sum().item(), 0.0)   # 剔除:零 logits
        self.assertTrue(torch.equal(out[2], self.head.bias.detach()))

    def test_drop_event(self):
        out, excluded_idx, counts = eval_tool.score_causal(
            self.backbone, self.head, self.tok, self.rows, "cpu",
            self.max_len, bs=2, overlong="drop-event")
        self.assertEqual(out.shape[0], len(self.rows))
        self.assertEqual(excluded_idx, [0, 1])
        self.assertEqual(counts["n_dropped_events"], 1)
        self.assertEqual(counts["n_dropped_bounds"], 2)
        self.assertEqual(counts["n_oow"], 0)
        self.assertEqual(counts["n_skipped_bounds"], 0)
        self.assertEqual(out[0].abs().sum().item(), 0.0)
        self.assertEqual(out[1].abs().sum().item(), 0.0)
        self.assertTrue(torch.equal(out[2], self.head.bias.detach()))

    def test_bad_overlong(self):
        with self.assertRaises(ValueError):
            eval_tool.score_causal(self.backbone, self.head, self.tok,
                                   self.rows, "cpu", self.max_len, bs=2,
                                   overlong="bogus")


class TestCachedLogitsOverlongModeGuard(unittest.TestCase):
    """(d) `--cached-logits` 路径:缓存的 `overlong_mode` 与本次 `--overlong`
    不同就 `SystemExit`。causal 头下 `--cached-logits` 不加载模型权重,只需要
    tokenizer(真实 Qwen)、`label_map.json`、`meta.json`、两堆手造 jsonl 与
    手造的 `logits_*.pt`/`.meta.json`。
    """

    @classmethod
    def setUpClass(cls):
        if not Path(QWEN_PATH).exists():
            raise unittest.SkipTest(f"分词器路径不存在:{QWEN_PATH}")

    def test_mode_mismatch_hard_stops(self):
        tok = AutoTokenizer.from_pretrained(QWEN_PATH)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            run = root / "run"
            data = root / "data"
            (run / "best").mkdir(parents=True)
            data.mkdir()
            tok.save_pretrained(run / "best")
            (run / "best" / "label_map.json").write_text(
                json.dumps({"apis.a": 0, "apis.b": 1}))
            (run / "best" / "meta.json").write_text(
                json.dumps({"max_len": 64, "base": "qwen-tiny"}))

            def _rows(n, prefix):
                return [dict(event=f"{prefix}{i}", sent_idx=0,
                           text=f"event {prefix}{i} text", label="apis.a")
                       for i in range(n)]

            val_rows, test_rows = _rows(2, "v"), _rows(2, "t")
            _write_jsonl(val_rows, data / "val.jsonl")
            _write_jsonl(test_rows, data / "test.jsonl")

            torch.save(torch.zeros(2, 2), run / "logits_val.pt")
            (run / "logits_val.meta.json").write_text(json.dumps(
                {"weights": {}, "rows": 2, "overlong_mode": "left",
                 "excluded_idx": []}))
            torch.save(torch.zeros(2, 2), run / "logits_test.pt")
            (run / "logits_test.meta.json").write_text(json.dumps(
                {"weights": {}, "rows": 2, "overlong_mode": "skip",
                 "excluded_idx": []}))

            argv = ["eval_tool.py", "--env", "appworld", "--run", str(run),
                   "--data", str(data), "--head", "causal",
                   "--cached-logits", "--overlong", "left", "--device", "cpu"]
            old_argv = sys.argv
            try:
                sys.argv = argv
                with self.assertRaises(SystemExit):
                    eval_tool.main()
            finally:
                sys.argv = old_argv


class TestMbertOverlongGuard(unittest.TestCase):
    """(e) `--head mbert` 传非 `left` 的 `--overlong` 必须 `SystemExit`——
    这条检查在参数解析之后、任何文件访问之前,--run/--data 给不存在的路径
    也能测。"""

    def test_mbert_rejects_non_left(self):
        argv = ["eval_tool.py", "--env", "appworld", "--run", "/no/such/run",
               "--data", "/no/such/data", "--head", "mbert",
               "--overlong", "skip"]
        old_argv = sys.argv
        try:
            sys.argv = argv
            with self.assertRaises(SystemExit):
                eval_tool.main()
        finally:
            sys.argv = old_argv


if __name__ == "__main__":
    unittest.main()
