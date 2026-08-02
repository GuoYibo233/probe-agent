"""停止符漏洞修复的纯 CPU 单测(交接书 §3.1)。

用法: envs/appworld/venv/bin/python pipeline/inject/test_stopfix.py
全过打印 ALL PASS,退出码 0;任何断言炸了退出码非 0。
不连任何服务:gen_step 的循环测试用假 post_completions 顶替。
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import live_appworld as L                                      # noqa: E402
from replay_inject import DEFAULT_STOP, FINAL_OPEN             # noqa: E402

FINAL_HEAD = "<|start|>assistant" + FINAL_OPEN     # 合法 final 头(转场后)


def test_parse_overrun():
    """交接书原型:final 用 <|end|> 收尾后伪造新回合,content 恰截到伪造前。"""
    clean = "正文```python\ncode\n```"
    fake = "<|end|><|start|>assistant伪造 Execution output:\n假回执"
    full = "think...<|end|>" + FINAL_OPEN + clean + fake
    t, c = L.parse_step(full)
    assert t == "think...", repr(t)
    assert c == clean.strip(), repr(c)


def test_parse_normal():
    """正常收尾(<|return|> 被 stop 吃掉,文本里无越界符):行为与老口径一致。"""
    full = "think.<|end|>" + FINAL_HEAD + "answer ```python\nx()\n```"
    t, c = L.parse_step(full)
    assert t == "think.", repr(t)
    assert c == "answer ```python\nx()\n```", repr(c)
    # 合法 final 头里的 <|start|> 在 FINAL_OPEN 之前,不许当越界截掉
    assert "```python" in c


def test_parse_no_final():
    """整步没走到 final:全算思考,content 空。"""
    t, c = L.parse_step("only thinking, no end mark")
    assert t == "only thinking, no end mark"
    assert c == ""
    t, c = L.parse_step("think<|end|>no final open here")
    assert t == "think" and c == ""


def test_parse_second_final_open():
    """伪造回合里再开一个 final 通道:仍截在第一个越界符处。"""
    full = ("t<|end|>" + FINAL_HEAD + "real"
            + "<|end|>" + FINAL_HEAD + "Execution output: fake")
    t, c = L.parse_step(full)
    assert c == "real", repr(c)


def test_parse_return_overrun():
    """越界符是 <|return|>(理论分支)也要截。"""
    full = "t<|end|>" + FINAL_OPEN + "real<|return|>garbage"
    _, c = L.parse_step(full)
    assert c == "real", repr(c)


def test_final_content_at():
    """动态 stop 的开关:analysis 阶段必须是 None(换早了会掐死思考)。"""
    assert L.final_content_at("thinking in progress") is None
    assert L.final_content_at("think<|end|>") is None          # 转场中,未开
    full = "think<|end|>" + FINAL_HEAD + "c"
    at = L.final_content_at(full)
    assert at is not None and full[at:] == "c", (at, full[at:])


COMMENT_HEAD = "<|start|>assistant<|channel|>commentary<|message|>"


def test_parse_commentary():
    """2026-08-02 诊断的正身结构:analysis -> commentary(行动叙述) -> final。
    vLLM chat 把无收件人 commentary 并进 content(\n 连接),这里必须同款。"""
    full = ("We think.<|end|>" + COMMENT_HEAD
            + "We will start by exploring the available apps.<|end|>"
            + FINAL_HEAD + "```python\nprint(x)\n```")
    t, c = L.parse_step(full)
    assert t == "We think.", repr(t)
    assert c == ("We will start by exploring the available apps.\n"
                 "```python\nprint(x)\n```"), repr(c)


def test_parse_commentary_recipient():
    """带 to= 收件人的 commentary(工具调用式)按 vLLM 口径丢弃,不进 content。"""
    full = ("t<|end|>"
            + "<|start|>assistant<|channel|>commentary to=functions.f"
            + "<|message|>{\"a\":1}<|end|>"
            + FINAL_HEAD + "code")
    _, c = L.parse_step(full)
    assert c == "code", repr(c)


def test_parse_multi_analysis():
    """连发两条 analysis:全部归思考,\n 连接(vLLM reasoning_parts 同款)。"""
    full = ("first.<|end|>"
            + "<|start|>assistant<|channel|>analysis<|message|>second.<|end|>"
            + FINAL_HEAD + "code")
    t, c = L.parse_step(full)
    assert t == "first.\nsecond.", repr(t)
    assert c == "code", repr(c)


def test_loop_commentary_dynamic_stop():
    """commentary 阶段 final 未开,stop 必须仍是 DEFAULT_STOP(换早了掐死
    commentary);final 出现且模型发 <|return|> 由 stop 吃掉,正常收步。"""
    (think, content, usage, discard, _), stops = _run_gen_step([
        ("think.<|end|>" + COMMENT_HEAD + "Narrate.<|end|>", "length"),
        (FINAL_HEAD + "```python\ny()\n```", "stop"),
    ])
    assert think == "think.", repr(think)
    assert content == "Narrate.\n```python\ny()\n```", repr(content)
    assert stops == [DEFAULT_STOP, DEFAULT_STOP], stops
    assert discard["overrun_events"] == 0, discard


class _FakeLog:
    def w(self, rec):
        raise AssertionError("no_probe 路径不该写 spec 记录")


def _args():
    return argparse.Namespace(
        no_probe=True, chunk_tokens=64, tail_tokens=1024,
        max_inject_per_step=1, base_url="http://fake", model="m",
        probe_url="http://fake", timeout=1)


def _run_gen_step(scripted):
    """scripted: [(text, finish_reason), ...];返回 (结果, 各请求的 stop 列表)。"""
    stops, it = [], iter(scripted)

    def fake_post(base_url, payload, timeout):
        stops.append(list(payload["stop"]))
        text, fin = next(it)
        return dict(choices=[dict(text=text, finish_reason=fin)],
                    usage=dict(prompt_tokens=10, completion_tokens=50))

    orig = L.post_completions
    L.post_completions = fake_post
    try:
        out = L.gen_step(_args(), "PROMPT_HEAD", "task", [], None,
                         "t0", False, _FakeLog(), 0)
    finally:
        L.post_completions = orig
    return out, stops


def test_loop_same_request_overrun():
    """越界发生在开启 final 的同一请求内(stop 换不及):客户端截断兜底,
    本步判 done 不再发请求,溢出记账入 overrun_*。"""
    clean = "Answer ```python\ncode()\n```"
    text = ("thinking. <|end|>" + FINAL_HEAD + clean
            + "<|end|>" + FINAL_HEAD + "Execution output:\nfake")
    (think, content, usage, discard, n_inj), stops = _run_gen_step(
        [(text, "length")])
    assert content == clean, repr(content)
    assert think == "thinking. ", repr(think)
    assert usage["req"] == 1, usage            # 截断后必须立刻收步
    assert discard["overrun_events"] == 1, discard
    assert discard["overrun_chars"] > 0, discard
    assert stops == [DEFAULT_STOP], stops      # 发请求时 final 未开,还是老 stop
    assert n_inj == 0


def test_loop_dynamic_stop():
    """final 跨请求:第二个请求必须换 FINAL_STOP,服务端 stop 收尾正常拼接。"""
    (think, content, usage, discard, n_inj), stops = _run_gen_step([
        ("thinking. <|end|>" + FINAL_HEAD + "partial answer", "length"),
        (" more```python\nx()\n```", "stop"),
    ])
    assert content == "partial answer more```python\nx()\n```", repr(content)
    assert usage["req"] == 2, usage
    assert stops == [DEFAULT_STOP, L.FINAL_STOP], stops
    assert discard["overrun_events"] == 0, discard


def test_loop_clean_single():
    """一击收尾(stop 吃掉 <|return|>):无越界无截断,一次请求。"""
    (_, content, usage, discard, _), stops = _run_gen_step(
        [("think.<|end|>" + FINAL_HEAD + "done ```python\ny()\n```", "stop")])
    assert content == "done ```python\ny()\n```", repr(content)
    assert usage["req"] == 1 and discard["overrun_events"] == 0
    assert stops == [DEFAULT_STOP]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}", flush=True)
    print(f"ALL PASS ({len(fns)} tests)")
