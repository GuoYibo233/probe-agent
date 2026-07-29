"""流式生成:collect/common.Chat 的 raw 模式改造 —— 边生成边把思考喂给
回调,回调说打断就断开连接(vLLM 客户端断开即弃算,后续 token 不再生成
也不再计费)。

- 提示词拼法/停止符/思考切分与 common.Chat 逐字节一致(直接复用其
  build_prompt),保证闭环轨迹与采集轨迹同分布
- on_think(reasoning_so_far) 返回 "abort" 即中止;只在 </think> 出现前回调
- token 账:走完取服务端 usage(include_usage);被打断拿不到 usage,
  记 aborted=True + 文本,由 accounting.tokenize_count 用 /tokenize
  端点(同模型同分词器)事后补精确数
"""

import sys
import time
from pathlib import Path

from openai import OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "collect"))
from common import Chat  # noqa: E402


class StreamingChat:
    def __init__(self, base_url, model, temperature=0.0, max_tokens=8192):
        self.client = OpenAI(base_url=base_url, api_key="EMPTY", timeout=600)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def __call__(self, messages, on_think=None):
        prompt = Chat.build_prompt(messages)
        t0 = time.time()
        stream = self.client.completions.create(
            model=self.model, prompt=prompt,
            temperature=self.temperature, max_tokens=self.max_tokens,
            stop=["<|im_end|>"], stream=True,
            stream_options={"include_usage": True})
        raw, usage, aborted, in_think = "", None, False, True
        for chunk in stream:
            if getattr(chunk, "usage", None):
                usage = {"in": chunk.usage.prompt_tokens,
                         "out": chunk.usage.completion_tokens}
            if not chunk.choices:
                continue
            prev = len(raw)
            raw += chunk.choices[0].text or ""
            if in_think and "</think>" in raw[max(0, prev - 12):]:
                in_think = False
            if in_think and on_think is not None:
                if on_think(raw) == "abort":
                    aborted = True
                    stream.close()
                    break
        reasoning, sep, content = raw.partition("</think>")
        if not sep:
            reasoning, content = raw, ""
        return {"reasoning": reasoning.strip("\n"), "content": content.strip(),
                "raw": raw, "aborted": aborted,
                "usage": usage or {"in": None, "out": None},
                "wall_s": round(time.time() - t0, 2)}
