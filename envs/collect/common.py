"""统一轨迹落盘。每条轨迹一个 JSONL,逐步四样东西全录:
模型输入(增量)、模型原始输出(reasoning 一字不删)、动作、环境原始返回。
"""

import json
import time

from openai import OpenAI


class Chat:
    """默认(api='raw')走 /v1/completions,Qwen 聊天模板自己拼(显式 <think>
    开头),原始输出自己按 </think> 切 — 思考段不经服务端 parser,零丢失。
    api='chat' 走 /v1/chat/completions,思考取 message.reasoning —
    给 gpt-oss(harmony 格式,服务端 openai_gptoss 解析器)用;
    reasoning_effort 仅该模式生效。
    历史 assistant 轮只回填 content(与官方模板一致,思考不进上下文)。
    """

    def __init__(self, base_url, model, temperature=0.0, max_tokens=8192,
                 api="raw", reasoning_effort=None):
        self.client = OpenAI(base_url=base_url, api_key="EMPTY", timeout=600)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.api = api
        self.reasoning_effort = reasoning_effort

    @staticmethod
    def build_prompt(messages):
        parts = []
        for m in messages:
            parts.append(f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n")
        parts.append("<|im_start|>assistant\n<think>\n")
        return "".join(parts)

    def __call__(self, messages, tries=4):
        """服务端 500 会整条分片带走 — gpt-oss 的 harmony parser 在思考特别长时
        会吐 'unexpected tokens remaining in message header'。退避重试,
        重试完仍失败才抛,让调用方决定弃轨迹还是弃整批。
        """
        last = None
        for i in range(tries):
            try:
                return self._once(messages)
            except Exception as e:  # 连接错误 / 5xx / 解析失败一律重试
                last = e
                if i < tries - 1:
                    time.sleep(2 ** i)
        raise last

    def _once(self, messages):
        if self.api == "chat":
            return self._chat(messages)
        t0 = time.time()
        r = self.client.completions.create(
            model=self.model, prompt=self.build_prompt(messages),
            temperature=self.temperature, max_tokens=self.max_tokens,
            stop=["<|im_end|>"])
        raw = r.choices[0].text
        reasoning, sep, content = raw.partition("</think>")
        if not sep:  # 思考超长被截断:全部算思考,内容为空
            reasoning, content = raw, ""
        return {
            "reasoning": reasoning.strip("\n"),
            "content": content.strip(),
            "raw": raw,
            "usage": {"in": r.usage.prompt_tokens, "out": r.usage.completion_tokens},
            "wall_s": round(time.time() - t0, 2),
        }

    def _chat(self, messages):
        t0 = time.time()
        extra = {}
        if self.reasoning_effort:
            extra["reasoning_effort"] = self.reasoning_effort
        r = self.client.chat.completions.create(
            model=self.model, messages=messages,
            temperature=self.temperature, max_tokens=self.max_tokens,
            extra_body=extra)
        m = r.choices[0].message
        reasoning = (getattr(m, "reasoning", None)
                     or getattr(m, "reasoning_content", None) or "")
        content = m.content or ""
        return {
            "reasoning": reasoning,
            "content": content,
            "raw": None,
            "usage": {"in": r.usage.prompt_tokens, "out": r.usage.completion_tokens},
            "wall_s": round(time.time() - t0, 2),
        }


class TrajLog:
    def __init__(self, path, meta):
        self.f = open(path, "w")
        self.w({"type": "meta", **meta})

    def w(self, rec):
        self.f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.f.flush()

    def close(self):
        self.f.close()
