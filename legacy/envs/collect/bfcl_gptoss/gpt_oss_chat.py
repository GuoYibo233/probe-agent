"""BFCL prompt-mode handler for gpt-oss-120b, going through chat.completions.

v1 does not collect gpt-oss trajectories for bfcl, because the harmony prompt template cannot
be hand-assembled at the completions endpoint (the way the qwen handler does it). Fix: switch
to the chat endpoint, let the vLLM server apply the template, and take the thinking from
message.reasoning (the same field chain as the chat mode in collect/common.py). The function
protocol is unchanged: function descriptions go in the system prompt, the model calls back in
text, and the decode side keeps the BFCL default prompt protocol -- matching the trajectory
format used for the qwen batches.

Install: install_patch.py copies this file into the venv's local_inference/ and registers
"openai/gpt-oss-120b" at the end of model_config.py.

All generation settings come from the client section of one preset file (max_tokens /
reasoning_effort / temperature / top_p / seed, taking whichever of these are non-null): the
environment variable NEW1_PRESET_JSON points to the absolute path of a
configs/presets/*.json file; when the environment variable is absent, it reads
configs/presets/default.json at the repo root, which is the setting currently active across
the board. When the preset leaves a key null, that key falls back to BFCL's built-in value
(temperature) or the hardcoded default below. This uses an environment variable instead of
--preset because this file gets copied into BFCL's venv, has no command line of its own, and
cannot reach the repo root's preset_loader; hence the repo root is written as an absolute path.
"""
import json
import os
import time
from typing import Any

# The repo root is hardcoded as an absolute path: this file runs from inside BFCL's venv, so
# __file__ cannot reach back to the repo
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
    """top_p/seed only go into the request when the preset gives them explicitly (the same rule as
    Chat._sample_extras in envs/collect/common.py): when absent, the request is byte-for-byte
    identical to before these two keys were added."""
    d = {}
    if _TOP_P is not None:
        d["top_p"] = _TOP_P
    if _SEED is not None:
        d["seed"] = _SEED
    return d


# NEW1_PRESET_PREFIX_END -- tests/test_preset.py execs only the source above this line
# (preset reading is pure stdlib); the imports below this line need the BFCL venv.
from bfcl_eval.model_handler.local_inference.base_oss_handler import OSSHandler
from overrides import override


class GptOssChatHandler(OSSHandler):

    @override
    def _format_prompt(self, messages, function):
        raise NotImplementedError("chat mode has the server apply the template, don't hand-assemble the prompt")

    def _to_chat_messages(self, messages):
        """Convert BFCL's message list into a shape the chat endpoint can accept.

        role=tool messages (rejected by the chat endpoint without a matching tool_calls) are
        folded into a <tool_response> block inside a user message; consecutive ones are merged
        into the same user turn -- aligned with how the qwen template handles tool returns.
        assistant messages pass only content, without the thinking (gpt-oss's convention is
        that past turns' thinking does not go back into context).
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
