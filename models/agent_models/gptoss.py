"""gpt-oss's harmony conversation format: render messages to token ids, parse a streamed reply, end of turn, and the control-token wrapping of a prefetch message."""
# venv: any at import and for parse/end_of_turn/wrap_prefetch; probe or vllm for render_ids()
from __future__ import annotations

import re

NAME = "gptoss"
STOP = ["<|return|>"]                     # 5.2's default of generation.stop
EFFORTS = ("high", "medium", "low")       # 5.3 validates generation.effort against it
DEFAULT_EFFORT = "high"
DEFAULT_DATE = "2026-08-06"
END_IDS = (200002, 200012)                # <|return|>, <|call|>

_END_MARK = "<|end|>"
_ROLE = {"system", "developer", "user", "assistant"}


def _text(content: str | None) -> str | None:
    """Equivalent of vLLM's flatten_input_text_content for our message shape: str stays as-is, None maps to None."""
    if content is None or isinstance(content, str):
        return content
    raise ValueError(f"only str content is supported, got {type(content).__name__}")


def _to_harmony_messages(messages: list[dict], effort: str, date: str) -> list:
    from openai_harmony import (Conversation, DeveloperContent, Message,
                                 ReasoningEffort, Role, SystemContent, TextContent)

    effort_table = {"high": ReasoningEffort.HIGH, "medium": ReasoningEffort.MEDIUM,
                    "low": ReasoningEffort.LOW}
    role_table = {"system": Role.SYSTEM, "developer": Role.DEVELOPER,
                  "user": Role.USER, "assistant": Role.ASSISTANT}

    msgs = list(messages)
    for m in msgs:
        for bad in ("tool_calls", "reasoning", "thinking"):
            if m.get(bad):
                raise ValueError(f"message carries {bad}, render_ids does not support it")
        if m.get("role") not in _ROLE:
            raise ValueError(f"unknown role {m.get('role')!r}")

    instructions = None
    if msgs and msgs[0]["role"] in ("system", "developer"):
        instructions = _text(msgs[0].get("content"))
        msgs = msgs[1:]

    sys_content = (SystemContent.new()
                   .with_reasoning_effort(effort_table[effort])
                   .with_conversation_start_date(date))
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
            out.append(Message.from_role_and_contents(role_table[role], [TextContent(text=content)]))
    return Conversation.from_messages(out)

_encoding = None


def _harmony_encoding():
    global _encoding
    if _encoding is None:
        from openai_harmony import HarmonyEncodingName, load_harmony_encoding
        _encoding = load_harmony_encoding(HarmonyEncodingName.HARMONY_GPT_OSS)
    return _encoding


def render_ids(messages: list[dict], effort: str | None, date: str | None) -> list[int]:
    """The conversation as gpt-oss's own harmony prompt token ids, ending at `<|start|>assistant`."""
    from openai_harmony import RenderConversationConfig, Role

    if effort is None:
        raise ValueError("effort is required: render_ids refuses an unpinned reasoning effort")
    if effort not in EFFORTS:
        raise ValueError(f"effort must be one of {EFFORTS}, got {effort!r}")
    if date is None:
        raise ValueError("date is required: render_ids refuses an unpinned date")
    conv = _to_harmony_messages(messages, effort, date)
    return list(_harmony_encoding().render_conversation_for_completion(
        conv, Role.ASSISTANT, config=RenderConversationConfig(auto_drop_analysis=False)))


def parse(text_delta: str, state: dict) -> dict:
    """Split the text streamed so far into its two channels, growing `state` chunk to chunk."""
    state["raw"] = state.get("raw", "") + text_delta
    full = state["raw"].split("<|return|>", 1)[0]
    reasoning, content = [], []
    for i, seg in enumerate(full.split(_END_MARK)):
        if i == 0 and not seg.lstrip().startswith("<|channel|>"):
            channel, has_recipient, body = "analysis", False, seg
        else:
            header, sep, body = seg.partition("<|message|>")
            header = header.strip()
            if not sep or not (header.startswith("<|start|>assistant") or header.startswith("<|channel|>")):
                continue
            m = re.match(r"\s*([a-z]+)", header.partition("<|channel|>")[2])
            channel = m.group(1) if m else ""
            has_recipient = " to=" in header
        if channel == "analysis" and body:
            reasoning.append(body)
        elif (channel == "final" or (channel == "commentary" and not has_recipient)) and body:
            content.append(body)
    return {"reasoning": "\n".join(reasoning), "content": "\n".join(content)}


def end_of_turn(ids: list[int]) -> bool:
    """Whether the generated ids have closed the turn."""
    return ids[-1] in END_IDS


def wrap_prefetch(body: str, system_text: str | None) -> str:
    """Wrap an injected prefetch body in gpt-oss's control tokens, closing the open thinking segment."""
    if system_text is not None:
        body = system_text + "\n\n" + body
    return ("<|end|><|start|>prefetch to=assistant<|channel|>analysis<|message|>"
            + body + "<|end|><|start|>assistant")
