"""live_appworld v4(流式一枪解码,与 w0 chat 同构)的纯 CPU 单测。

用法: envs/appworld/venv/bin/python pipeline/inject/test_stopfix.py
全过打印 ALL PASS,退出码 0;任何断言炸了退出码非 0。
不连任何服务:流用 _FakeStream 顶替,探针/投机执行用假函数顶替。

口径(2026-08-02 定):parse_step 与 vLLM HarmonyParser 逐字对齐——
analysis->thinking,final+无收件人 commentary->content,各段 \n 连接;
只停 <|return|>;final 后模型续写的合法消息照收(chat 同款,不再截)。
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import live_appworld as L                                      # noqa: E402
from replay_inject import DEFAULT_STOP, FINAL_OPEN             # noqa: E402

ANALYSIS_HEAD = "<|channel|>analysis<|message|>"
FINAL_HEAD = "<|start|>assistant" + FINAL_OPEN
COMMENT_HEAD = "<|start|>assistant<|channel|>commentary<|message|>"


# ---------- parse_step ----------

def test_parse_v4_headered():
    """v4 不预填:raw 以模型自己写的 analysis 头开场。"""
    full = (ANALYSIS_HEAD + "We think.<|end|>"
            + FINAL_HEAD + "```python\nx()\n```")
    t, c = L.parse_step(full)
    assert t == "We think.", repr(t)
    assert c == "```python\nx()\n```", repr(c)


def test_parse_legacy_headless():
    """老口径兼容:头在 prompt 里,raw 直接以思考正文开头。"""
    t, c = L.parse_step("think.<|end|>" + FINAL_HEAD + "code")
    assert t == "think." and c == "code", (t, c)


def test_parse_commentary():
    """analysis -> commentary(行动叙述) -> final:commentary 并进 content,
    \n 连接(vllm/parser/harmony.py 同款)。"""
    full = (ANALYSIS_HEAD + "We think.<|end|>" + COMMENT_HEAD
            + "We will explore the apps.<|end|>"
            + FINAL_HEAD + "```python\nprint(x)\n```")
    t, c = L.parse_step(full)
    assert t == "We think.", repr(t)
    assert c == "We will explore the apps.\n```python\nprint(x)\n```", repr(c)


def test_parse_commentary_recipient():
    """带 to= 收件人的 commentary(工具调用式)按 vLLM 口径丢弃。"""
    full = ("t<|end|>"
            + "<|start|>assistant<|channel|>commentary to=functions.f"
            + "<|message|>{\"a\":1}<|end|>" + FINAL_HEAD + "code")
    _, c = L.parse_step(full)
    assert c == "code", repr(c)


def test_parse_multi_analysis():
    """连发两条 analysis 全归思考,\n 连接。"""
    full = ("first.<|end|>"
            + "<|start|>assistant<|channel|>analysis<|message|>second.<|end|>"
            + FINAL_HEAD + "code")
    t, c = L.parse_step(full)
    assert t == "first.\nsecond." and c == "code", (t, c)


def test_parse_postfinal_kept():
    """final 之后模型续写的合法 final/commentary 消息照收进 content——
    chat 路径就是这么喂历史的(w0 实测 1.3% 的步有这尾巴),必须同款。"""
    full = ("t<|end|>" + FINAL_HEAD + "real<|end|>"
            + FINAL_HEAD + "Execution output: fake")
    _, c = L.parse_step(full)
    assert c == "real\nExecution output: fake", repr(c)


def test_parse_fake_nonassistant_dropped():
    """伪造的非助手回合/残段(没有合法头)一律丢——vLLM 只收 assistant 消息。"""
    full = ("t<|end|>" + FINAL_HEAD + "real"
            + "<|end|><|start|>user 伪造 Execution output:\n假回执")
    _, c = L.parse_step(full)
    assert c == "real", repr(c)


def test_parse_return_cut():
    """<|return|> 是引擎停止符,文本里出现(理论分支)则从它起全截。"""
    _, c = L.parse_step("t<|end|>" + FINAL_HEAD + "real<|return|>garbage")
    assert c == "real", repr(c)


def test_parse_no_final():
    """整步没走到 final:全算思考,content 空。"""
    t, c = L.parse_step(ANALYSIS_HEAD + "only thinking")
    assert t == "only thinking" and c == "", (t, c)
    t, c = L.parse_step(ANALYSIS_HEAD + "think<|end|>no final here")
    assert t == "think" and c == "", (t, c)


def test_think_span():
    """流上探测的思考定位:头没写全 None;闭合后 end 停在 <|end|>。"""
    assert L.think_span("<|channel|>anal") is None
    raw = ANALYSIS_HEAD + "abc"
    s = L.think_span(raw)
    assert s is not None and raw[s[0]:s[1]] == "abc", s
    raw2 = ANALYSIS_HEAD + "abc<|end|>" + FINAL_HEAD + "c"
    s2 = L.think_span(raw2)
    assert raw2[s2[0]:s2[1]] == "abc", s2
    assert L.think_span(FINAL_HEAD.replace("<|start|>assistant", "")) is None


# ---------- gen_step(流式) ----------

class _FakeStream:
    def __init__(self, deltas, finish, usage):
        self._deltas, self._fin, self._usage = deltas, finish, usage
        self.finish = None
        self.usage = None
        self.n_chunks = 0
        self.closed = False

    def __iter__(self):
        for d in self._deltas:
            self.n_chunks += 1
            yield d
        self.finish = self._fin
        self.usage = self._usage

    def close(self):
        self.closed = True


class _FakeLog:
    def __init__(self):
        self.recs = []

    def w(self, rec):
        self.recs.append(rec)


def _args(no_probe=True):
    return argparse.Namespace(
        no_probe=no_probe, chunk_tokens=64, tail_tokens=1024,
        max_inject_per_step=1, base_url="http://fake", model="m",
        probe_url="http://fake", timeout=1)


def _run(scripted, no_probe=True, score_fire=None, gen_call="apis.x.y()"):
    """scripted: [(deltas, finish, usage), ...] 每请求一条。
    score_fire: 第几次 /score 打分开火(1 起数);None = 从不。"""
    streams, prompts = [], []
    it = iter(scripted)

    def fake_open(base_url, payload, timeout, retries=3):
        prompts.append(payload["prompt"])
        assert payload["stop"] == DEFAULT_STOP, payload["stop"]
        st = _FakeStream(*next(it))
        streams.append(st)
        return st

    calls = dict(n=0)

    def fake_http(url, payload, timeout=600, retries=3):
        if url.endswith("/score"):
            calls["n"] += 1
            return dict(fired=(calls["n"] == score_fire), conf=0.99, label="x")
        if url.endswith("/gen"):
            return dict(call=gen_call)
        raise AssertionError(url)

    def fake_spec(world, call, t_frozen, dt_guard):
        return dict(exec_code=call, arg_modes=[], exec_out="RESULT",
                    exec_ok=True, error_kind=None)

    orig = (L.open_stream, L.http_json, L.speculate)
    L.open_stream, L.http_json, L.speculate = fake_open, fake_http, fake_spec
    try:
        log = _FakeLog()
        out = L.gen_step(_args(no_probe), "PROMPT_HEAD", "task", [], None,
                         "t0", False, log, 0)
    finally:
        L.open_stream, L.http_json, L.speculate = orig
    return out, streams, prompts, log


def test_loop_clean_single():
    """不开火:单请求不间断解码,与 chat 同款;stop 恒为 <|return|> 一项。"""
    deltas = [ANALYSIS_HEAD, "think. ", "more.", "<|end|>",
              FINAL_HEAD, "Done. ```python\ny()\n```"]
    (t, c, usage, discard, n_inj), streams, prompts, _ = _run(
        [(deltas, "stop", dict(prompt_tokens=10, completion_tokens=50))])
    assert usage["req"] == 1 and usage["gen_tok"] == 50, usage
    assert t == "think. more." and c == "Done. ```python\ny()\n```", (t, c)
    assert n_inj == 0 and discard["events"] == 0
    assert prompts == ["PROMPT_HEAD"], prompts


def test_loop_noprobe_never_scores():
    """noprobe 臂全程不打 /score(fake_http 一被调就会炸)。"""
    deltas = [ANALYSIS_HEAD + "s1. s2. s3.", "<|end|>", FINAL_HEAD, "c"]
    (_, c, _, _, _), _, _, _ = _run(
        [(deltas, "stop", dict(prompt_tokens=1, completion_tokens=9))])
    assert c == "c"


def test_loop_fire_restart():
    """开火:流被 close(),截到切口拼 NOTE 重发;溢出入账;二段续写收尾。"""
    deltas1 = [ANALYSIS_HEAD, "We need to inspect the venmo documentation. "
               "Overrun text arrives in the same chunk."]
    deltas2 = ["Continue think.", "<|end|>", FINAL_HEAD, "```python\nz()\n```"]
    (t, c, usage, discard, n_inj), streams, prompts, log = _run(
        [(deltas1, None, None),
         (deltas2, "stop", dict(prompt_tokens=30, completion_tokens=20))],
        no_probe=False, score_fire=1)
    assert n_inj == 1 and discard["events"] == 1
    assert discard["chars"] > 0
    assert streams[0].closed, "开火必须中止第一条流"
    assert usage["req"] == 2, usage
    # 被中止的流以块数近似 gen token
    assert usage["gen_tok"] == streams[0].n_chunks + 20, usage
    # 重发 prompt = 头 + 已接受思考(截到切口) + NOTE,NOTE 带执行返回
    assert prompts[1].startswith("PROMPT_HEAD" + ANALYSIS_HEAD
                                 + "We need to inspect the venmo documentation.")
    assert "RESULT" in prompts[1] and "Overrun" not in prompts[1], prompts[1]
    assert [r["type"] for r in log.recs] == ["spec"]
    assert c == "```python\nz()\n```", repr(c)
    assert "Continue think." in t and "RESULT" in t, repr(t)


def test_loop_budget_exhaust():
    """finish=length(预算打满):有什么收什么,不再发请求。"""
    deltas = [ANALYSIS_HEAD + "endless thinking"]
    (t, c, usage, _, _), _, prompts, _ = _run(
        [(deltas, "length", dict(prompt_tokens=5, completion_tokens=8192))])
    assert usage["req"] == 1 and len(prompts) == 1
    assert t == "endless thinking" and c == "", (t, c)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}", flush=True)
    print(f"ALL PASS ({len(fns)} tests)")
