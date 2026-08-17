"""live_appworld.gen_step 发给 vLLM 的 prompt 形态测试(纯 CPU,假服务)。

2026-08-18 起 prompt 是 token id 列表:不出手的步 = /render 给的 prefix_ids
原样;注入后重发 = prefix_ids + /encode(切口前生成文本 + NOTE)。这里用假的
http_json / open_stream 把两条断言钉死,顺带钉住 /health 缺 render 字段就拒跑。
    python3 -m unittest tests.test_live_prompt_ids -v
"""

import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline" / "inject"))
sys.path.insert(0, str(ROOT / "pipeline" / "annotate"))

import live_appworld as L                                       # noqa: E402

PREFIX = [200006, 17360, 200008, 3575, 200007, 200006, 173781]  # 随便一串
THINK = ("<|channel|>analysis<|message|>We need to inspect the profile first. "
         "Then we log in to spotify. Then we list playlists.")
FINAL = "<|end|><|start|>assistant<|channel|>final<|message|>```python\nprint(1)\n```"


class FakeStream:
    """按 pieces 逐块吐文本;记录 payload;close 计数。"""
    calls = []

    def __init__(self, base_url, payload, timeout, script):
        self.payload = payload
        self.script = script
        FakeStream.calls.append(payload)
        self.usage = None
        self.n_chunks = 0
        self.closed = 0

    def __iter__(self):
        for piece in self.script:
            self.n_chunks += 1
            yield piece
        self.usage = dict(prompt_tokens=len(self.payload["prompt"]),
                          completion_tokens=self.n_chunks)

    def close(self):
        self.closed += 1


def fake_encode(text):
    # 假分词:一字一 id,只要能验"前缀 + 编码(raw)"这个形态
    return [1000 + (ord(c) % 100) for c in text]


class Args(types.SimpleNamespace):
    pass


def mk_args(**kw):
    a = Args(base_url="http://vllm", probe_url="http://probe", model="m",
             timeout=5, no_probe=False, max_inject_per_step=1)
    a.__dict__.update(kw)
    return a


class TestPromptIds(unittest.TestCase):
    def setUp(self):
        FakeStream.calls = []
        self.logged = []
        self.log = types.SimpleNamespace(w=lambda rec: self.logged.append(rec))
        self._orig = (L.open_stream, L.http_json, L.speculate)

    def tearDown(self):
        L.open_stream, L.http_json, L.speculate = self._orig

    def test_no_probe_prompt_is_prefix_ids_verbatim(self):
        script = [THINK, FINAL]
        L.open_stream = lambda b, p, t, retries=3: FakeStream(b, p, t, script)
        L.http_json = lambda url, payload, **k: self.fail(f"no probe 不该打 {url}")
        think, content, usage, discard, n_inj = L.gen_step(
            mk_args(no_probe=True), PREFIX, "task", [], None, "t0", False,
            self.log, 0)
        self.assertEqual(len(FakeStream.calls), 1)
        self.assertEqual(FakeStream.calls[0]["prompt"], PREFIX)
        self.assertNotIn("add_special_tokens", FakeStream.calls[0])
        self.assertEqual(n_inj, 0)
        self.assertIn("print(1)", content)
        self.assertTrue(think.startswith("We need to inspect"))

    def test_probe_fire_resends_prefix_plus_encoded_raw(self):
        # 第一枪:逐块吐思考,第二句结束时探针开火;第二枪:续写到 final
        first = ["<|channel|>analysis<|message|>We need to inspect the profile first. ",
                 "Then we log in to spotify. ", "Then we list playlists."]
        second = [" Continue.", FINAL]
        scripts = iter([first, second])
        L.open_stream = lambda b, p, t, retries=3: FakeStream(b, p, t, next(scripts))
        n_score = {"n": 0}

        def http(url, payload, **k):
            if url.endswith("/score"):
                n_score["n"] += 1
                return dict(conf=0.9 if n_score["n"] == 2 else 0.1,
                            label="x", fired=(n_score["n"] == 2))
            if url.endswith("/gen"):
                return dict(call="apis.supervisor.show_profile()")
            if url.endswith("/encode"):
                return dict(ids=fake_encode(payload["text"]))
            self.fail(url)
        L.http_json = http
        L.speculate = lambda world, call, t, g: dict(
            exec_code=call, arg_modes={}, exec_out="{'ok': 1}", exec_ok=True,
            error_kind=None)
        think, content, usage, discard, n_inj = L.gen_step(
            mk_args(), PREFIX, "task", [], None, "t0", False, self.log, 0)
        self.assertEqual(n_inj, 1)
        self.assertEqual(len(FakeStream.calls), 2)
        self.assertEqual(FakeStream.calls[0]["prompt"], PREFIX)
        p2 = FakeStream.calls[1]["prompt"]
        self.assertEqual(p2[:len(PREFIX)], PREFIX)
        spec = next(r for r in self.logged if r["type"] == "spec")
        raw_resent = ("<|channel|>analysis<|message|>We need to inspect the "
                      "profile first. Then we log in to spotify. " + spec["note"])
        self.assertEqual(p2[len(PREFIX):], fake_encode(raw_resent))
        self.assertIn("SYSTEM NOTE", think)
        self.assertNotIn("Then we list playlists", think)   # 切口后溢出丢弃
        self.assertIn("print(1)", content)


class TestHealthGate(unittest.TestCase):
    def test_old_server_rejected(self):
        self.assertIn("旧版", L.probe_cfg_problem(dict(theta=0.9, temperature=1.8)))
        self.assertIn("旧版", L.probe_cfg_problem(dict(render="jinja_text")))

    def test_new_server_accepted(self):
        self.assertIsNone(L.probe_cfg_problem(dict(theta=0.9, render="harmony_ids")))


if __name__ == "__main__":
    unittest.main()
