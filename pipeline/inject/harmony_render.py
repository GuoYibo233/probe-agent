"""把 chat 消息列表渲染成 gpt-oss 的 harmony prompt **token id**,与 vLLM chat 端点
逐 token 相同。

为什么不再走 jinja 模板出文本(rebuild.build_prefix)、再让 /v1/completions 分词:
2026-08-18 排查 chat baseline 与 no probe 的差异,发现 jinja 文本路在两个边角上
与 chat 端点不一致——(1) content 为空的 assistant 轮,chat 端点整条丢掉,jinja
照渲染 `<|start|>assistant<|channel|>final<|message|><|end|>`;(2) content 里
的字面 `<|end|>` `<|channel|>` 等标记,chat 端点当普通文本编码,completions
端点的分词器把它们收成真正的特殊 token id。两条都让 no probe 的 prompt 从
那一步起永久偏离 chat baseline。改成直接出 token id 就把两条一起消掉,还顺带
去掉三样补丁(剥 developer 段尾 `\\n\\n` 的正则、占位符换回原文、日期正则替换)。

【照抄 vLLM 0.26.0】renderers/online_renderer.py:_make_request_with_harmony 走的
三步:entrypoints/openai/parser/harmony_utils.py 的 extract_instructions_from_messages
→ build_harmony_preamble → parse_chat_inputs_to_harmony_messages → render_for_completion。
本文件只依赖 openai_harmony(cprobe-env 已装,pydantic 2),不 import vllm。
逐 token 相等由 tests/test_harmony_render.py 用 vLLM 自己的函数当裁判验(在
envs/vllm-env 下跑)。

只支持我们的消息形态:system/user/assistant 三种 role、content 是 str 或 None,
没有 tool_calls / reasoning / 多模态。带了就 raise,不静默走别的分支。
"""

from openai_harmony import (Conversation, DeveloperContent, HarmonyEncodingName,
                            Message, ReasoningEffort, RenderConversationConfig,
                            Role, SystemContent, TextContent,
                            load_harmony_encoding)

# 与 vLLM harmony_utils.REASONING_EFFORT 同一张表
EFFORT = {"high": ReasoningEffort.HIGH,
          "medium": ReasoningEffort.MEDIUM,
          "low": ReasoningEffort.LOW}
ROLE = {"system": Role.SYSTEM, "developer": Role.DEVELOPER,
        "user": Role.USER, "assistant": Role.ASSISTANT}

_enc = None


def encoding():
    global _enc
    if _enc is None:
        _enc = load_harmony_encoding(HarmonyEncodingName.HARMONY_GPT_OSS)
    return _enc


def _text(content):
    """vLLM flatten_input_text_content 在我们形态下的等价:str 原样,None 归 None。"""
    if content is None or isinstance(content, str):
        return content
    raise ValueError(f"只支持 str content,拿到 {type(content).__name__}")


def to_harmony_messages(messages, effort="high", start_date=None):
    """chat messages -> openai_harmony Message 列表(不渲染)。

    与 vLLM 逐条对应:
    - 打头的 system/developer 消息剥出来当 instructions,进 developer 消息
      (VLLM_GPT_OSS_HARMONY_SYSTEM_INSTRUCTIONS 缺省 False 的分支);
      instructions 为空串或 None 就不出 developer 消息(build_harmony_preamble
      的 `if developer_instructions or tools`)。
    - system 消息:model identity 默认、reasoning effort 按表、日期钉 start_date。
    - assistant:content 非空才出一条 final 消息;空串/None 整条丢
      (parse_chat_input_to_harmony_message 末尾 `if role == "assistant" and
      contents and contents[0].text`)。
    - user:content 原样(空串也出一条)。
    - 中途的 system/developer:出一条 developer 消息(get_system_or_developer_message)。
    """
    if effort not in EFFORT:
        raise ValueError(f"reasoning effort 只认 {sorted(EFFORT)},拿到 {effort!r}")
    if start_date is None:
        raise ValueError("start_date 必传:日期不钉死,渲染就随运行当天漂")
    msgs = list(messages)
    for m in msgs:
        for bad in ("tool_calls", "reasoning", "thinking"):
            if m.get(bad):
                raise ValueError(f"消息带 {bad},本渲染器不支持(vLLM 会走别的分支)")
        if m.get("role") not in ROLE:
            raise ValueError(f"未知 role {m.get('role')!r}")

    instructions = None
    if msgs and msgs[0]["role"] in ("system", "developer"):
        instructions = _text(msgs[0].get("content"))
        msgs = msgs[1:]

    sys_content = (SystemContent.new()
                   .with_reasoning_effort(EFFORT[effort])
                   .with_conversation_start_date(start_date))
    out = [Message.from_role_and_content(Role.SYSTEM, sys_content)]
    if instructions:
        out.append(Message.from_role_and_content(
            Role.DEVELOPER, DeveloperContent.new().with_instructions(instructions)))

    for m in msgs:
        role = m["role"]
        content = _text(m.get("content")) or ""
        if role == "assistant":
            if content:
                out.append(Message.from_role_and_contents(
                    Role.ASSISTANT, [TextContent(text=content)]).with_channel("final"))
        elif role in ("system", "developer"):
            instr = _text(m.get("content"))
            if instr is not None:
                out.append(Message.from_role_and_content(
                    Role.DEVELOPER, DeveloperContent.new().with_instructions(instr)))
        else:  # user
            out.append(Message.from_role_and_contents(
                ROLE[role], [TextContent(text=content)]))
    return out


def render_ids(messages, effort="high", start_date=None):
    """chat messages -> prompt token id 列表,止于 <|start|>assistant。
    与 vLLM render_for_completion 同款调用(auto_drop_analysis=False;我们的
    消息里没有 analysis,vLLM 前置的 auto_drop_analysis_messages 是空操作)。"""
    conv = Conversation.from_messages(
        to_harmony_messages(messages, effort=effort, start_date=start_date))
    return list(encoding().render_conversation_for_completion(
        conv, Role.ASSISTANT,
        config=RenderConversationConfig(auto_drop_analysis=False)))


def decode(ids):
    """token id -> 文本(特殊标记原样),给日志与人眼核对用。"""
    return encoding().decode(list(ids))
