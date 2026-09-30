"""Qwen3-generation chat models' ChatML format with <think> reasoning: render messages to token ids through the model's own chat template, parse a streamed reply, end of turn, and the ChatML wrapping of a prefetch message."""
# venv: any at import and for parse/end_of_turn/wrap_prefetch; probe or vllm for render_ids()
from __future__ import annotations

import json
import threading
from pathlib import Path

NAME = "qwen3"
STOP = ["<|im_end|>"]                     # 5.2's default of generation.stop
EFFORTS = ()                              # no reasoning tiers: 5.3 refuses any generation.effort value
DEFAULT_EFFORT = None
DEFAULT_DATE = "2026-08-06"

# The two tokens that close a turn. Their ids differ between generations (Qwen3: 151645 and
# 151643; Qwen3.5: 248046 and 248044), so end_of_turn reads them from the bound weights'
# tokenizer_config.json instead of naming one generation's ids here.
_END_TOKENS = ("<|im_end|>", "<|endoftext|>")
_ROLE = {"system", "developer", "user", "assistant"}

# The weights directory models/__init__.py's agent(alias) hands over through bind_weights();
# the chat template and the end-of-turn ids are read from it.
_weights_path: str | None = None
_tokenizers: dict[str, object] = {}
_end_ids: dict[str, tuple[int, ...]] = {}
_lock = threading.Lock()


def bind_weights(weights_path: str) -> None:
    """Take the weights directory of the table row being served, whose tokenizer holds this model's chat template and end-of-turn ids."""
    global _weights_path
    _weights_path = weights_path


def _bound_path() -> str:
    if _weights_path is None:
        raise RuntimeError("models.agent_models.qwen3: no weights directory is bound; "
                           "resolve the row through models.agent(alias) first")
    return _weights_path


def _tokenizer():
    path = _bound_path()
    with _lock:
        if path not in _tokenizers:
            from transformers import AutoTokenizer
            _tokenizers[path] = AutoTokenizer.from_pretrained(path)
        return _tokenizers[path]


def _text(content: str | None) -> str:
    """A message's text: a str stays as it is and None is the empty text."""
    if content is None or isinstance(content, str):
        return content or ""
    raise ValueError(f"only str content is supported, got {type(content).__name__}")


def template_messages(messages: list[dict], date: str) -> list[dict]:
    """The messages as the model's chat template takes them: the first system or developer message becomes the one system message, its text preceded by the line `Current date: <date>` and a blank line (ChatML has no date slot); every later turn keeps its role and its content only."""
    for m in messages:
        for bad in ("tool_calls", "reasoning", "reasoning_content", "thinking"):
            if m.get(bad):
                raise ValueError(f"message carries {bad}, render_ids does not support it")
        if m.get("role") not in _ROLE:
            raise ValueError(f"unknown role {m.get('role')!r}")

    msgs = list(messages)
    system = f"Current date: {date}"
    if msgs and msgs[0]["role"] in ("system", "developer"):
        instructions = _text(msgs[0].get("content"))
        if instructions:
            system = system + "\n\n" + instructions
        msgs = msgs[1:]
    out = [{"role": "system", "content": system}]
    for m in msgs:
        if m["role"] in ("system", "developer"):
            raise ValueError("a system or developer message after the first one has no place in "
                             "the ChatML template (it accepts one system message, at the start)")
        out.append({"role": m["role"], "content": _text(m.get("content"))})
    return out


def render_ids(messages: list[dict], effort: str | None, date: str | None) -> list[int]:
    """The conversation as the model's own chat-template prompt token ids, thinking switched on, ending at the generation prompt: the template's text encoded without added special tokens, which is what vLLM's chat endpoint does."""
    if effort is not None:
        raise ValueError(f"effort must be None: family {NAME!r} has no reasoning tiers, got {effort!r}")
    if date is None:
        raise ValueError("date is required: render_ids refuses an unpinned date")
    tok = _tokenizer()
    text = tok.apply_chat_template(template_messages(messages, date), tokenize=False,
                                   add_generation_prompt=True, enable_thinking=True)
    return list(tok.encode(text, add_special_tokens=False))


def chat_request(messages: list[dict], effort: str | None, date: str | None) -> dict:
    """The fields of a /v1/chat/completions request under which the served chat template renders the ids render_ids does: the same template messages and the same thinking switch."""
    if date is None:
        raise ValueError("date is required: chat_request refuses an unpinned date")
    return {"messages": template_messages(messages, date),
            "chat_template_kwargs": {"enable_thinking": True}}


def _assistant_bodies(raw: str) -> list[str]:
    """The text of every assistant turn in the stream: the turn the prompt opened, then each turn whose finished header names the assistant (a prefetch turn, and a header still streaming, are left out)."""
    first, *later = raw.split("<|im_start|>")
    bodies = [first]
    for seg in later:
        role, sep, body = seg.partition("\n")
        if sep and role == "assistant":
            bodies.append(body)
    return bodies


def parse(text_delta: str, state: dict) -> dict:
    """Split the text streamed so far into reasoning (before `</think>`, a leading `<think>` dropped) and content (after it), growing `state` chunk to chunk; a turn a prefetch note opened is read the same way and a non-assistant turn is skipped."""
    state["raw"] = state.get("raw", "") + text_delta
    reasoning, content = [], []
    for body in _assistant_bodies(state["raw"]):
        for end in _END_TOKENS:
            body = body.split(end, 1)[0]
        if body.startswith("<think>"):
            body = body[len("<think>"):]
        think, closed, after = body.partition("</think>")
        if think:
            reasoning.append(think)
        after = after.lstrip("\n")
        if closed and after:
            content.append(after)
    return {"reasoning": "\n".join(reasoning), "content": "\n".join(content)}


def _end_ids_of(path: str) -> tuple[int, ...]:
    with _lock:
        if path not in _end_ids:
            config = json.loads((Path(path) / "tokenizer_config.json").read_text())
            decoder = config.get("added_tokens_decoder") or {}
            ids = tuple(int(i) for i, tok in decoder.items() if tok.get("content") in _END_TOKENS)
            if len(ids) != len(_END_TOKENS):
                raise RuntimeError(f"models.agent_models.qwen3: {path}/tokenizer_config.json names "
                                   f"{len(ids)} of the end tokens {_END_TOKENS}")
            _end_ids[path] = ids
        return _end_ids[path]


def end_of_turn(ids: list[int]) -> bool:
    """Whether the generated ids have closed the turn."""
    return ids[-1] in _end_ids_of(_bound_path())


def wrap_prefetch(body: str, system_text: str | None) -> str:
    """Wrap an injected prefetch body in ChatML, closing the open thinking segment: the ChatML form of gpt-oss's wrapping, `</think>` ends the thinking and `<|im_end|>` the turn, a turn from the sender `prefetch` carries the body, and a new assistant turn opens with its thinking open, as the generation prompt of Qwen3-*-Thinking-2507 and Qwen3.5 opens it."""
    if system_text is not None:
        body = system_text + "\n\n" + body
    return ("\n</think>\n\n<|im_end|>\n<|im_start|>prefetch\n"
            + body + "<|im_end|>\n<|im_start|>assistant\n<think>\n")
