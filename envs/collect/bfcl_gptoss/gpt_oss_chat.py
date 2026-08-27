"""gpt-oss-120b 的 BFCL 提示词模式 handler,走 chat.completions。

v1 不采 bfcl 的 gpt-oss 轨迹,原因是 harmony 提示词模板没法在 completions
端点手工拼(qwen handler 的做法)。解法:改走 chat 端点,模板由 vLLM 服务端套,
思考取 message.reasoning(与 collect/common.py 的 chat 模式同一字段链)。
函数协议不变:函数说明写在系统提示词里,模型以文本回调用,decode 侧沿用
BFCL 默认提示词协议——与 qwen 批次的轨迹格式保持一致。

安装:install_patch.py 把本文件拷进 venv 的 local_inference/ 并在
model_config.py 末尾注册 "openai/gpt-oss-120b"。

生成设置全部来自一份预设文件的 client 节(max_tokens / reasoning_effort /
temperature / top_p / seed,取其中非 null 的):环境变量 NEW1_PRESET_JSON 指一份
configs/presets/*.json 的绝对路径,环境变量缺席时读仓库根下的
configs/presets/default.json,也就是全线现役的那一份口径。
预设把某个键留 null 时该键落 BFCL 自带的值(temperature)或下面的写死缺省。
用环境变量不用 --preset 的原因:本文件被拷进 BFCL 的 venv,没有自己的命令行,
也够不到仓库根的 preset_loader;仓库根因此写成绝对路径。
"""
import json
import os
import time
from typing import Any

# 仓库根写死绝对路径:本文件的运行位置在 BFCL 的 venv 里,__file__ 够不回仓库
_REPO_ROOT = "/home/y-guo/reproduce/new1"
_DEFAULT_PRESET = os.path.join(_REPO_ROOT, "configs", "presets", "default.json")

_PRESET_PATH = os.environ.get("NEW1_PRESET_JSON") or _DEFAULT_PRESET
with open(_PRESET_PATH) as _f:
    _CLIENT = json.load(_f).get("client") or {}
_MAX_TOKENS = (_CLIENT.get("max_tokens")
               if _CLIENT.get("max_tokens") is not None else 16384)
_EFFORT = (_CLIENT.get("reasoning_effort")
           if _CLIENT.get("reasoning_effort") is not None else "high")
_TOP_P = _CLIENT.get("top_p")
_SEED = _CLIENT.get("seed")


def _sample_kwargs():
    """top_p/seed 只在预设显式给了的时候进请求(envs/collect/common.py 的
    Chat._sample_extras 同款口径):不给时请求与加这两个键之前逐字节一致。"""
    d = {}
    if _TOP_P is not None:
        d["top_p"] = _TOP_P
    if _SEED is not None:
        d["seed"] = _SEED
    return d


# NEW1_PRESET_PREFIX_END —— tests/test_preset.py 只 exec 这行以上的源码
# (预设读取纯标准库);这行以下的 import 需要 BFCL venv。
from bfcl_eval.model_handler.local_inference.base_oss_handler import OSSHandler
from overrides import override


class GptOssChatHandler(OSSHandler):

    @override
    def _format_prompt(self, messages, function):
        raise NotImplementedError("chat 模式由服务端套模板,不手工拼提示词")

    def _to_chat_messages(self, messages):
        """把 BFCL 的消息列表转成 chat 端点能收的形态。

        role=tool 的消息(chat 端点没有配套 tool_calls 会被拒收)折叠成
        user 消息里的 <tool_response> 块,连续多条并进同一条 user——
        与 qwen 模板处理工具返回的方式对齐。assistant 消息只传 content,
        不回传思考(gpt-oss 约定历史轮思考不进上下文)。
        """
        chat = []
        for m in messages:
            role = m["role"]
            if role == "tool":
                block = f"<tool_response>\n{m['content']}\n</tool_response>"
                if chat and chat[-1]["role"] == "user" and chat[-1].get("_tool"):
                    chat[-1]["content"] += "\n" + block
                else:
                    chat.append({"role": "user", "content": block, "_tool": True})
            elif role == "assistant":
                chat.append({"role": "assistant", "content": m["content"] or ""})
            else:
                chat.append({"role": role, "content": m["content"]})
        for m in chat:
            m.pop("_tool", None)
        return chat

    @override
    def _query_prompting(self, inference_data: dict):
        chat_messages = self._to_chat_messages(inference_data["message"])
        inference_data["inference_input_log"] = {"chat_messages": chat_messages}

        start_time = time.time()
        api_response = self.client.chat.completions.create(
            model=self.model_path_or_id,
            temperature=(_CLIENT["temperature"]
                         if _CLIENT.get("temperature") is not None
                         else self.temperature),
            messages=chat_messages,
            max_tokens=_MAX_TOKENS,
            extra_body={"reasoning_effort": _EFFORT},
            timeout=72000,
            **_sample_kwargs(),
        )
        end_time = time.time()
        return api_response, end_time - start_time

    @override
    def _parse_query_response_prompting(self, api_response: Any) -> dict:
        m = api_response.choices[0].message
        reasoning = (getattr(m, "reasoning", None)
                     or getattr(m, "reasoning_content", None) or "")
        return {
            "model_responses": m.content or "",
            "reasoning_content": reasoning,
            "input_token": api_response.usage.prompt_tokens,
            "output_token": api_response.usage.completion_tokens,
        }

    @override
    def _add_assistant_message_prompting(
        self, inference_data: dict, model_response_data: dict
    ) -> dict:
        inference_data["message"].append(
            {
                "role": "assistant",
                "content": model_response_data["model_responses"],
                "reasoning_content": model_response_data.get("reasoning_content", ""),
            }
        )
        return inference_data
