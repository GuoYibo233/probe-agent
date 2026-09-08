"""Render a chat message list into gpt-oss harmony prompt **token ids**,
token for token identical to the vLLM chat endpoint.

Why not go through the jinja template to text (rebuild.build_prefix) and
then let /v1/completions tokenize it: on 2026-08-18, while investigating the
difference between the chat baseline and no probe, found the jinja text path
disagrees with the chat endpoint at two edge cases -- (1) for an assistant
turn with empty content, the chat endpoint drops the whole turn, but jinja
still renders `<|start|>assistant<|channel|>final<|message|><|end|>`; (2)
literal markers like `<|end|>` `<|channel|>` inside content are encoded as
plain text by the chat endpoint, but the completions endpoint's tokenizer
turns them into real special token ids. Both cases make the no-probe prompt
permanently diverge from the chat baseline from that step onward. Emitting
token ids directly eliminates both cases at once, and along the way also
removes three patches (the regex that strips the trailing `\\n\\n` of the
developer segment, swapping placeholders back to the original text, and the
date regex substitution).

[Copied from vLLM 0.26.0] The three steps that
renderers/online_renderer.py:_make_request_with_harmony goes through:
entrypoints/openai/parser/harmony_utils.py's
extract_instructions_from_messages → build_harmony_preamble →
parse_chat_inputs_to_harmony_messages → render_for_completion. This file
only depends on openai_harmony (already installed in cprobe-env, pydantic
2), it does not import vllm. Token-for-token equality is verified by
tests/test_harmony_render.py using vLLM's own function as the judge (run
under envs/vllm-env).

Only supports our message shape: the three roles system/user/assistant,
content is str or None, no tool_calls / reasoning / multimodal. If present,
raise -- never silently fall through to another branch.
"""

from openai_harmony import (Conversation, DeveloperContent, HarmonyEncodingName,
                            Message, ReasoningEffort, RenderConversationConfig,
                            Role, SystemContent, TextContent,
                            load_harmony_encoding)

# Same table as vLLM harmony_utils.REASONING_EFFORT
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
    """Equivalent of vLLM flatten_input_text_content for our shape: str stays as-is, None maps to None."""
    if content is None or isinstance(content, str):
        return content
    raise ValueError(f"only str content is supported, got {type(content).__name__}")


def to_harmony_messages(messages, effort="high", start_date=None):
    """chat messages -> list of openai_harmony Message (does not render).

    Matches vLLM item for item:
    - The leading system/developer messages are stripped out as
      instructions and go into a developer message (the branch where
      VLLM_GPT_OSS_HARMONY_SYSTEM_INSTRUCTIONS defaults to False); if
      instructions is an empty string or None, no developer message is
      emitted (build_harmony_preamble's `if developer_instructions or
      tools`).
    - system message: model identity default, reasoning effort per table,
      date pinned to start_date.
    - assistant: only emits a final message when content is non-empty;
      empty string/None drops the whole turn (the end of
      parse_chat_input_to_harmony_message, `if role == "assistant" and
      contents and contents[0].text`).
    - user: content as-is (an empty string still emits one).
    - system/developer in the middle: emits one developer message
      (get_system_or_developer_message).
    """
    if effort not in EFFORT:
        raise ValueError(f"reasoning effort only recognizes {sorted(EFFORT)}, got {effort!r}")
    if start_date is None:
        raise ValueError("start_date is required: if the date is not pinned, rendering drifts with whatever day it runs")
    msgs = list(messages)
    for m in msgs:
        for bad in ("tool_calls", "reasoning", "thinking"):
            if m.get(bad):
                raise ValueError(f"message carries {bad}, this renderer does not support it (vLLM takes a different branch for this)")
        if m.get("role") not in ROLE:
            raise ValueError(f"unknown role {m.get('role')!r}")

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
    """chat messages -> prompt token id list, ending at <|start|>assistant.
    Same call as vLLM render_for_completion (auto_drop_analysis=False; our
    messages have no analysis, so vLLM's leading auto_drop_analysis_messages
    is a no-op)."""
    conv = Conversation.from_messages(
        to_harmony_messages(messages, effort=effort, start_date=start_date))
    return list(encoding().render_conversation_for_completion(
        conv, Role.ASSISTANT,
        config=RenderConversationConfig(auto_drop_analysis=False)))


def decode(ids):
    """token id -> text (special markers kept as-is), for logs and manual eyeball checking."""
    return encoding().decode(list(ids))
