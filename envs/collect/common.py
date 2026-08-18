"""统一轨迹落盘。每条轨迹一个 JSONL,逐步四样东西全录:
模型输入(增量)、模型原始输出(reasoning 一字不删)、动作、环境原始返回。
"""

import json
import re
import time
import urllib.request

from openai import OpenAI

# harmony 的 system 消息模板。vLLM 服务端用 openai_harmony 生成同一段文字,
# 这里手拼是因为 openai_harmony 依赖 pydantic 2,装进 envs/appworld/venv 会
# 顶掉 appworld 需要的 pydantic 1.10.26(实测直接 import 就断)。
# 手拼版已被官方渲染器逐字节验过(2026-08-06,813 字符/174 token 全等)。
HARMONY_SYSTEM = (
    "You are ChatGPT, a large language model trained by OpenAI.\n"
    "Knowledge cutoff: 2024-06\n"
    "Current date: {date}\n"
    "\n"
    "Reasoning: {effort}\n"
    "\n"
    "# Valid channels: analysis, commentary, final. "
    "Channel must be included for every message."
)

# 一条 harmony 消息的头:<|channel|>频道 [to=收件人] [<|constrain|>类型] <|message|>
HARMONY_HEAD = re.compile(
    r"<\|channel\|>(?P<channel>[^\s<]+)"
    r"(?:\s+to=(?P<recipient>[^\s<]+))?"
    r"(?:\s*<\|constrain\|>(?P<ctype>[^\s<]+))?"
    r"\s*<\|message\|>")


class Chat:
    """默认(api='raw')走 /v1/completions,Qwen 聊天模板自己拼(显式 <think>
    开头),原始输出自己按 </think> 切 — 思考段不经服务端 parser,零丢失。
    api='chat' 走 /v1/chat/completions,思考取 message.reasoning —
    给 gpt-oss(harmony 格式,服务端 openai_gptoss 解析器)用;
    reasoning_effort 仅该模式生效。
    api='harmony' 也走 /v1/completions,但 harmony 提示词自己拼、原始输出
    自己按频道切(skip_special_tokens=False + return_token_ids=True) —
    服务端 HarmonyParser 完全不参与,落在 IGNORE 档的段落不会被静默丢掉,
    生成的 token id 原样存进轨迹。当天日期由客户端钉死,跨天重跑前缀不变。
    历史 assistant 轮只回填 content(与官方模板一致,思考不进上下文)。
    """

    def __init__(self, base_url, model, temperature=0.0, max_tokens=8192,
                 api="raw", reasoning_effort=None, start_date="2026-08-06"):
        self.client = OpenAI(base_url=base_url, api_key="EMPTY", timeout=600)
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.api = api
        self.reasoning_effort = reasoning_effort
        self.start_date = start_date

    @staticmethod
    def build_prompt(messages):
        parts = []
        for m in messages:
            parts.append(f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n")
        parts.append("<|im_start|>assistant\n<think>\n")
        return "".join(parts)

    def build_harmony_prompt(self, messages):
        """打头的 system 消息按官方口径落进 developer,其余原样搬。
        尾巴留一个光秃秃的 <|start|>assistant,频道由模型自己选。
        """
        parts = []
        rest = list(messages)
        instructions = None
        if rest and rest[0]["role"] in ("system", "developer"):
            instructions = rest[0]["content"]
            rest = rest[1:]
        parts.append("<|start|>system<|message|>" + HARMONY_SYSTEM.format(
            date=self.start_date,
            effort=self.reasoning_effort or "medium") + "<|end|>")
        if instructions is not None:
            parts.append("<|start|>developer<|message|># Instructions\n\n"
                         + instructions + "<|end|>")
        for m in rest:
            if m["role"] == "assistant":
                parts.append("<|start|>assistant<|channel|>final<|message|>"
                             + m["content"] + "<|end|>")
            else:
                parts.append(f"<|start|>{m['role']}<|message|>"
                             + m["content"] + "<|end|>")
        parts.append("<|start|>assistant")
        return "".join(parts)

    @staticmethod
    def split_harmony(raw):
        """把带特殊标记的原始输出按频道切成段。不丢任何一段 —
        频道认不出来的照样进 segments,只是不进 reasoning/content。
        """
        segs = []
        pos = 0
        # 生成从 <|start|>assistant 之后接着,所以第一段的头就是 <|channel|>
        while True:
            m = HARMONY_HEAD.search(raw, pos)
            if not m:
                break
            body_start = m.end()
            end = len(raw)
            end_tok = ""
            for tok in ("<|end|>", "<|return|>", "<|call|>"):
                i = raw.find(tok, body_start)
                if i != -1 and i < end:
                    end, end_tok = i, tok
            segs.append({"channel": m.group("channel"),
                         "recipient": m.group("recipient"),
                         "constrain": m.group("ctype"),
                         "text": raw[body_start:end],
                         "closed_by": end_tok})
            pos = end + len(end_tok) if end_tok else end
            if not end_tok:
                break
        reasoning = "\n".join(s["text"] for s in segs
                              if s["channel"] == "analysis")
        content = "\n".join(s["text"] for s in segs
                            if s["channel"] == "final"
                            or (s["channel"] == "commentary"
                                and not s["recipient"]))
        return segs, reasoning, content

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
        if self.api == "harmony":
            return self._harmony(messages)
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
        # return_token_ids(2026-08-18 ident3):vLLM 把 prompt 与生成的 token id
        # 一并交回(openai 客户端 extra=allow,字段留在 choice/response 上),
        # 只多存两个字段,行为不变——三臂逐 token 比对要它
        extra = {"return_token_ids": True}
        if self.reasoning_effort:
            extra["reasoning_effort"] = self.reasoning_effort
        r = self.client.chat.completions.create(
            model=self.model, messages=messages,
            temperature=self.temperature, max_tokens=self.max_tokens,
            extra_body=extra)
        ch = r.choices[0]
        m = ch.message
        reasoning = (getattr(m, "reasoning", None)
                     or getattr(m, "reasoning_content", None) or "")
        content = m.content or ""
        return {
            "reasoning": reasoning,
            "content": content,
            "raw": None,
            "out_token_ids": getattr(ch, "token_ids", None),
            "prompt_token_ids": getattr(r, "prompt_token_ids", None),
            "finish_reason": ch.finish_reason,
            "usage": {"in": r.usage.prompt_tokens, "out": r.usage.completion_tokens},
            "wall_s": round(time.time() - t0, 2),
        }

    def _harmony(self, messages):
        """不走 openai 客户端 — 它的响应模型不认 vLLM 加的 token_ids /
        prompt_token_ids,走 stdlib 直接收 JSON,一个字段都不丢。
        """
        t0 = time.time()
        prompt = self.build_harmony_prompt(messages)
        body = json.dumps({
            "model": self.model,
            "prompt": prompt,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "add_special_tokens": False,   # harmony 串自带 <|start|>,别再加
            "skip_special_tokens": False,  # 默认 True 会把频道标记抹掉
            "return_token_ids": True,      # 服务端把真实生成的 id 交回来
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/completions", data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer EMPTY"})
        with urllib.request.urlopen(req, timeout=600) as resp:
            r = json.loads(resp.read())
        ch = r["choices"][0]
        raw = ch["text"]
        segs, reasoning, content = self.split_harmony(raw)
        return {
            "reasoning": reasoning,
            "content": content,
            "raw": raw,
            "segments": segs,
            "prompt_text": prompt,
            "out_token_ids": ch.get("token_ids"),
            "prompt_token_ids": ch.get("prompt_token_ids"),
            "finish_reason": ch.get("finish_reason"),
            "stop_reason": ch.get("stop_reason"),
            "usage": {"in": r["usage"]["prompt_tokens"],
                      "out": r["usage"]["completion_tokens"]},
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
