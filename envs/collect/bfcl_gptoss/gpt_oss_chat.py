"""gpt-oss-120b 的 BFCL 提示词模式 handler,走 chat.completions。

v1 不采 bfcl 的 gpt-oss 轨迹,原因是 harmony 提示词模板没法在 completions
端点手工拼(qwen handler 的做法)。解法:改走 chat 端点,模板由 vLLM 服务端套,
思考取 message.reasoning(与 collect/common.py 的 chat 模式同一字段链)。
函数协议不变:函数说明写在系统提示词里,模型以文本回调用,decode 侧沿用
BFCL 默认提示词协议——与 qwen 批次的轨迹格式保持一致。

安装:install_patch.py 把本文件拷进 venv 的 local_inference/ 并在
model_config.py 末尾注册 "openai/gpt-oss-120b"。
"""
import time
from typing import Any

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
            temperature=self.temperature,
            messages=chat_messages,
            max_tokens=16384,
            extra_body={"reasoning_effort": "high"},
            timeout=72000,
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
