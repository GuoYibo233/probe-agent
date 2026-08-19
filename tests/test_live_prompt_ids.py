"""live_appworld.gen_step 发给 vLLM 的 prompt 形态测试(纯 CPU,假服务)。

2026-08-18 起 prompt 是 token id 列表:不出手的步 = /render 给的 prefix_ids
原样;v6(ident3)开火重发 = prefix_ids + 模型自己生成的 id[:k](head = 盖住句尾
标点的最短 id 前缀,/decode 逐个核出来)+ /encode(NOTE)。这里用假的
http_json / open_stream 把这些断言钉死,顺带钉住 /health 缺 render/decode
字段就拒跑,以及流文本落后于 id 时 head 仍然找对。
    python3 -m unittest tests.test_live_prompt_ids -v
"""

import sys
import types
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline" / "inject"))
sys.path.insert(0, str(ROOT / "pipeline" / "annotate"))

import live_appworld as L                                       # noqa: E402

PREFIX = [200006, 17360, 200008, 3575, 200007, 200006, 173781]  # 随便一串
THINK = ("<|channel|>analysis<|message|>We need to inspect the profile first. "
         "Then we log in to spotify. Then we list playlists.")
FINAL = "<|end|><|start|>assistant<|channel|>final<|message|>```python\nprint(1)\n```"
HEAD2 = ("<|channel|>analysis<|message|>We need to inspect the profile first. "
         "Then we log in to spotify.")          # 第 2 个句尾切口处的 head 文本


def fake_encode(text):
    # 假分词:一字一 id(可逆:100000 + 码位),只要能验"前缀 + 编码"这个形态
    return [100000 + ord(c) for c in text]


def words(text):
    """假的"模型 token":按空格前分词(' Then' 这种带前导空格的词一个 token),
    每个 token 一个流块。"""
    out, cur = [], ""
    for ch in text:
        if ch == " " and cur:
            out.append(cur)
            cur = ""
        cur += ch
    if cur:
        out.append(cur)
    return out


def word_id(w):
    # 不能用内置 hash():字符串 hash 每个进程加随机盐,两个词偶尔撞出同一个
    # id,decoder 的反查表就串词,find_head 随机报不一致(2026-08-20 抓到的
    # 老毛病:改造前的代码连跑八遍挂四遍)。crc32 确定性,过一次永远过。
    return 3000 + (zlib.crc32(w.encode()) % 100000)


class FakeStream:
    """按 pieces 逐块吐 (文本, ids);记录 payload;close 计数。
    pieces 里的元素是 str(id 由 word_id 决定,同一词同一 id)或 (str, ids)。"""
    calls = []

    def __init__(self, base_url, payload, timeout, script):
        self.payload = payload
        self.script = script
        FakeStream.calls.append(payload)
        self.usage = None
        self.finish = None
        self.stop_reason = None
        self.n_chunks = 0
        self.n_ids = 0
        self.closed = 0

    def __iter__(self):
        for piece in self.script:
            text, ids = piece if isinstance(piece, tuple) else (
                piece, [word_id(piece)])
            self.n_chunks += 1
            self.n_ids += len(ids)
            yield text, ids
        self.usage = dict(prompt_tokens=len(self.payload["prompt"]),
                          completion_tokens=self.n_ids)
        self.finish = "stop"

    def close(self):
        self.closed += 1


class Args(types.SimpleNamespace):
    pass


def mk_args(**kw):
    a = Args(base_url="http://vllm", probe_url="http://probe", model="m",
             timeout=5, no_probe=False, max_inject_per_step=1,
             fire_nth_cut=0, nofill=False,
             # gen-preset(2026-08-20):这三个字段原来是模块常量/写死值,
             # 现在挂在 args 上,缺省与旧值相同
             max_step_tokens=8192, temperature=0.0, stop=["<|return|>"])
    a.__dict__.update(kw)
    return a


def decoder(all_words):
    """假 /decode:按 id 反查词(测试里的词各不相同)。"""
    table = {word_id(w): w for w in all_words}
    return lambda ids: "".join(table[i] if i < 100000 else chr(i - 100000)
                               for i in ids)


class TestPureHelpers(unittest.TestCase):
    def test_token_boundary_backs_off(self):
        b = [(0, 0), (5, 1), (9, 2), (15, 3)]
        self.assertEqual(L.token_boundary(b, 9), (9, 2))
        self.assertEqual(L.token_boundary(b, 12), (9, 2))
        self.assertEqual(L.token_boundary(b, 4), (0, 0))
        self.assertEqual(L.token_boundary(b, 100), (15, 3))

    def test_token_boundary_held_back_text_picks_fewest_ids(self):
        b = [(0, 0), (5, 1), (5, 2), (8, 3)]
        self.assertEqual(L.token_boundary(b, 5), (5, 1))
        self.assertEqual(L.token_boundary(b, 8), (8, 3))

    def test_sep_for(self):
        self.assertEqual(L.sep_for("done."), "\n")
        self.assertEqual(L.sep_for("done.\n\n"), "")
        self.assertEqual(L.sep_for("done. "), "")

    def test_sent_starts_stable_as_whitespace_arrives(self):
        base = "x" * 30 + " We need this. "
        s1 = L.sent_starts(base)                 # ". " 已到
        s2 = L.sent_starts(base + "\n")          # 又来一个换行
        self.assertEqual(s1, s2)                 # 同一个句尾还是同一个切口
        self.assertEqual(L.sent_cuts(base) != L.sent_cuts(base + "\n"), True)
        self.assertEqual(s1, [len("x" * 30 + " We need this.")])

    def test_find_head_shortest_prefix_covering_pos(self):
        toks = ["<|channel|>", "a.", " b.", "\n\n", "c.\n\n", " d"]
        dec = lambda ids: "".join(toks[i] for i in ids)
        ids = list(range(len(toks)))
        raw = "".join(toks)
        pos_a = len("<|channel|>a.")            # 'a.' 之后
        self.assertEqual(L.find_head(ids, raw, pos_a, 5, dec), (2, "<|channel|>a."))
        self.assertEqual(L.find_head(ids, raw, pos_a, 1, dec), (2, "<|channel|>a."))
        pos_b = len("<|channel|>a. b.")         # 'b.' 之后,后面是独立的 "\n\n" token
        self.assertEqual(L.find_head(ids, raw, pos_b, 4, dec)[0], 3)   # 不带 "\n\n"
        pos_c = len("<|channel|>a. b.\n\nc.")   # 'c.' 之后,"c.\n\n" 是一个 token
        self.assertEqual(L.find_head(ids, raw, pos_c, 2, dec),
                         (5, "<|channel|>a. b.\n\nc.\n\n"))       # 连着 "\n\n"
        # 流文本落后于 id 也没关系(raw 只到 'b.'):
        self.assertEqual(L.find_head(ids, raw[:pos_b], pos_b, 6, dec)[0], 3)
        # 文本与 id 对不上要抛
        with self.assertRaises(RuntimeError):
            L.find_head(ids, "<|channel|>zz. b.", pos_b, 3, dec)


class TestPromptIds(unittest.TestCase):
    def setUp(self):
        FakeStream.calls = []
        self.logged = []
        self.log = types.SimpleNamespace(w=lambda rec: self.logged.append(rec))
        self._orig = (L.open_stream, L.http_json, L.speculate)

    def tearDown(self):
        L.open_stream, L.http_json, L.speculate = self._orig

    def _http(self, all_words, extra=None):
        dec = decoder(all_words)

        def http(url, payload, **k):
            if url.endswith("/decode"):
                return dict(text=dec(payload["ids"]))
            if url.endswith("/encode"):
                return dict(ids=fake_encode(payload["text"]))
            if extra and url.endswith(extra[0]):
                return extra[1](payload)
            self.fail(f"不该打 {url}")
        return http

    def test_no_probe_prompt_is_prefix_ids_verbatim(self):
        script = words(THINK) + [FINAL]
        L.open_stream = lambda b, p, t, retries=3: FakeStream(b, p, t, script)
        L.http_json = lambda url, payload, **k: self.fail(f"no probe 不该打 {url}")
        think, content, usage, discard, n_inj, gen_ids, cons = L.gen_step(
            mk_args(no_probe=True), PREFIX, "task", [], None, "t0", False,
            self.log, 0)
        self.assertEqual(len(FakeStream.calls), 1)
        self.assertEqual(FakeStream.calls[0]["prompt"], PREFIX)
        self.assertEqual(FakeStream.calls[0]["max_tokens"], L.MAX_STEP_TOKENS)
        self.assertNotIn("add_special_tokens", FakeStream.calls[0])
        self.assertEqual(n_inj, 0)
        self.assertIsNone(cons)
        self.assertIn("print(1)", content)
        self.assertTrue(think.startswith("We need to inspect"))
        self.assertEqual(gen_ids, [word_id(w) for w in script])
        self.assertEqual(usage["gen_tok"], len(script))

    def test_probe_fire_resends_prefix_plus_own_ids_plus_note(self):
        # 第一枪:逐词吐思考,第二句结束时探针开火;第二枪:续写到 final
        first = words(THINK)          # 最后一句 "Then we list playlists." 是溢出
        second = words(" Continue.") + [FINAL]
        scripts = iter([first, second])
        L.open_stream = lambda b, p, t, retries=3: FakeStream(b, p, t, next(scripts))
        n_score = {"n": 0}
        dec = decoder(first + second)

        def http(url, payload, **k):
            if url.endswith("/score"):
                n_score["n"] += 1
                return dict(conf=0.9 if n_score["n"] == 2 else 0.1,
                            label="x", fired=(n_score["n"] == 2))
            if url.endswith("/gen"):
                return dict(call="apis.supervisor.show_profile()")
            if url.endswith("/encode"):
                return dict(ids=fake_encode(payload["text"]))
            if url.endswith("/decode"):
                return dict(text=dec(payload["ids"]))
            self.fail(url)
        L.http_json = http
        L.speculate = lambda world, call, t, g: dict(
            exec_code=call, arg_modes={}, exec_out="{'ok': 1}", exec_ok=True,
            error_kind=None)
        think, content, usage, discard, n_inj, gen_ids, cons = L.gen_step(
            mk_args(), PREFIX, "task", [], None, "t0", False, self.log, 0)
        self.assertEqual(n_inj, 1)
        self.assertEqual(len(FakeStream.calls), 2)
        self.assertEqual(FakeStream.calls[0]["prompt"], PREFIX)
        p2 = FakeStream.calls[1]["prompt"]
        spec = next(r for r in self.logged if r["type"] == "spec")
        head_ids = [word_id(w) for w in words(HEAD2)]   # 止于 "spotify."
        self.assertEqual(spec["head_tok"], len(head_ids))
        self.assertFalse(spec["head_ends_ws"])
        self.assertTrue(spec["note"].startswith("\n[SYSTEM NOTE"))  # head 无尾空白
        self.assertEqual(p2, PREFIX + head_ids + fake_encode(spec["note"]))
        # 第二枪的预算按留下的 id 算
        self.assertEqual(FakeStream.calls[1]["max_tokens"],
                         L.MAX_STEP_TOKENS - len(p2) + len(PREFIX))
        self.assertEqual(spec["overflow_ids"],
                         [word_id(w) for w in words(" Then we list playlists.")])
        self.assertIn("SYSTEM NOTE", think)
        self.assertNotIn("Then we list playlists", think)   # 切口后溢出丢弃
        self.assertIn("print(1)", content)
        self.assertEqual(discard["tokens"], 4)
        res = next(r for r in self.logged if r["type"] == "resume")
        self.assertEqual(res["overflow_tok"], 4)
        self.assertFalse(res["identical"])
        # gen_ids = head + note ids + 第二枪的 id;收官核对时假 decode 不认 note
        # 的假 id 会 KeyError——所以这里只验 gen_ids 形态
        self.assertEqual(gen_ids, head_ids + fake_encode(spec["note"])
                         + [word_id(w) for w in second])

    def test_nth_cut_nofill_resends_prefix_plus_own_ids_only(self):
        first = words(THINK)
        overflow = words(" Then we list playlists.")
        second = overflow + [FINAL]          # 重发续写与被丢弃的逐位相同
        scripts = iter([first, second])
        L.open_stream = lambda b, p, t, retries=3: FakeStream(b, p, t, next(scripts))
        L.http_json = self._http(first + second)
        L.speculate = lambda *a: self.fail("nofill 不该投机执行")
        think, content, usage, discard, n_inj, gen_ids, cons = L.gen_step(
            mk_args(fire_nth_cut=2, nofill=True), PREFIX, "task", [], None,
            "t0", False, self.log, 0)
        self.assertEqual(n_inj, 1)
        spec = next(r for r in self.logged if r["type"] == "spec")
        self.assertTrue(spec["nofill"])
        self.assertIsNone(spec["gen_call"])
        self.assertIsNone(spec["exec_out"])       # score_live 要的键都在,值 None
        self.assertEqual(spec["note"], "")
        head_ids = [word_id(w) for w in words(HEAD2)]
        self.assertEqual(FakeStream.calls[1]["prompt"], PREFIX + head_ids)
        self.assertNotIn("SYSTEM NOTE", think)
        self.assertIn("Then we list playlists", think)   # 续写又写出来了
        res = next(r for r in self.logged if r["type"] == "resume")
        self.assertTrue(res["identical"])
        self.assertEqual(res["match_len"], len(overflow))
        self.assertEqual(gen_ids, head_ids + [word_id(w) for w in second])
        self.assertEqual(usage["req"], 2)
        # gen_tok(billed)= 第一枪全部(含溢出)+ 第二枪
        self.assertEqual(usage["gen_tok"], len(first) + len(second))
        self.assertTrue(cons)                     # 收官核对:decode(gen_ids)==raw

    def test_lagging_text_head_found_by_decode(self):
        # vLLM 有 stop 串时文本比 id 落后(压着 len(stop)-1 字符);这里让文本
        # 落后 2 个 token:块 i 交出 id(w_i) 与 w_{i-2} 的文本,尾部再把文本吐完
        first = words(THINK)
        lag = 2
        script = []
        for i, w in enumerate(first):
            script.append((first[i - lag] if i >= lag else "", [word_id(w)]))
        for w in first[-lag:]:
            script.append((w, []))
        overflow = words(" Then we list playlists.")
        second = overflow + [FINAL]
        scripts = iter([script, second])
        L.open_stream = lambda b, p, t, retries=3: FakeStream(b, p, t, next(scripts))
        n_dec = {"n": 0}
        base_http = self._http(first + second)

        def http(url, payload, **k):
            if url.endswith("/decode"):
                n_dec["n"] += 1
            return base_http(url, payload, **k)
        L.http_json = http
        think, content, usage, discard, n_inj, gen_ids, cons = L.gen_step(
            mk_args(fire_nth_cut=2, nofill=True), PREFIX, "task", [], None,
            "t0", False, self.log, 0)
        self.assertEqual(n_inj, 1)
        head_ids = [word_id(w) for w in words(HEAD2)]
        self.assertEqual(FakeStream.calls[1]["prompt"], PREFIX + head_ids)
        spec = next(r for r in self.logged if r["type"] == "spec")
        self.assertEqual(spec["head_tok"], len(head_ids))
        # 开火时 id 已经比文本多 2 个:溢出里含文本里还没出现的 " Then"," we"
        self.assertEqual(spec["overflow_ids"][:2], [word_id(" Then"), word_id(" we")])
        self.assertLessEqual(n_dec["n"], 8)
        self.assertIn("Then we list playlists", think)
        self.assertTrue(cons)

    def test_multi_token_chunk_same_head(self):
        # 生产端快过消费端时几个 token 并成一块:head 与逐 token 到达时相同
        first = words(THINK)
        merged = []
        i = 0
        while i < len(first):
            grp = first[i:i + 3]
            merged.append(("".join(grp), [word_id(w) for w in grp]))
            i += 3
        second = words(" Then we list playlists.") + [FINAL]
        scripts = iter([merged, second])
        L.open_stream = lambda b, p, t, retries=3: FakeStream(b, p, t, next(scripts))
        L.http_json = self._http(first + second)
        *_, n_inj, gen_ids, cons = L.gen_step(
            mk_args(fire_nth_cut=2, nofill=True), PREFIX, "task", [], None,
            "t0", False, self.log, 0)
        self.assertEqual(n_inj, 1)
        head_ids = [word_id(w) for w in words(HEAD2)]
        self.assertEqual(FakeStream.calls[1]["prompt"], PREFIX + head_ids)

    def test_nth_cut_not_reached_never_fires(self):
        script = words(THINK) + [FINAL]
        L.open_stream = lambda b, p, t, retries=3: FakeStream(b, p, t, script)
        L.http_json = lambda url, payload, **k: self.fail(url)
        *_, n_inj, gen_ids, cons = L.gen_step(
            mk_args(fire_nth_cut=9, nofill=True), PREFIX, "task", [], None,
            "t0", False, self.log, 0)
        self.assertEqual(n_inj, 0)
        self.assertEqual(len(FakeStream.calls), 1)

    def test_decode_mismatch_raises(self):
        first = words(THINK)
        L.open_stream = lambda b, p, t, retries=3: FakeStream(b, p, t, first)
        L.http_json = lambda url, payload, **k: dict(text="something else that is long enough. yes")
        with self.assertRaises(RuntimeError):
            L.gen_step(mk_args(fire_nth_cut=1, nofill=True), PREFIX, "task",
                       [], None, "t0", False, self.log, 0)


class TestHealthGate(unittest.TestCase):
    def test_old_server_rejected(self):
        self.assertIn("旧版", L.probe_cfg_problem(dict(theta=0.9, temperature=1.8)))
        self.assertIn("旧版", L.probe_cfg_problem(dict(render="jinja_text")))

    def test_new_server_accepted(self):
        self.assertIsNone(L.probe_cfg_problem(dict(theta=0.9, render="harmony_ids")))

    def test_decode_required_for_firing_arms(self):
        cfg = dict(render="harmony_ids")
        self.assertIsNone(L.probe_cfg_problem(cfg, need_decode=False))
        self.assertIn("decode", L.probe_cfg_problem(cfg, need_decode=True))
        self.assertIsNone(L.probe_cfg_problem(dict(cfg, decode=True),
                                              need_decode=True))


if __name__ == "__main__":
    unittest.main()
