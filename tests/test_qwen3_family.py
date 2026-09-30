"""The qwen3 agent-model family: render_ids equals the model's own chat template encoded the way vLLM's chat endpoint encodes it (and equals what the service's render check would get back from a server fed the family's chat_request), the date is the system message's first line, the loop's developer message becomes the system message and earlier assistant turns carry content only; parse gives the same reasoning and content however the stream is split, and keeps the reasoning a suffix of the stream while thinking; end_of_turn reads the end ids from the tokenizer; wrap_prefetch closes the thinking, puts the body in a turn parse skips, and opens a new assistant turn whose thinking parse reads. The rendering cases run once per cached Qwen tokenizer and are skipped with a message when none is on disk."""
# venv: probe
from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from models.agent_models import qwen3
from models.agent_models.service import CHECK_MESSAGES

HUB = Path("/net/tokyo100-10g/data/str01_01/y-guo/hf/hub")
MODELS = Path("/net/tokyo100-10g/data/str01_01/y-guo/models")
DATE = "2026-08-06"


def _tokenizer_dirs() -> list[Path]:
    """Every cached Qwen3-generation tokenizer directory: two hub snapshots of other sizes, and the two agent models' own directories once their tokenizer files have arrived."""
    found = []
    for repo in ("models--Qwen--Qwen3.5-9B", "models--Qwen--Qwen3-8B"):
        found += sorted((HUB / repo / "snapshots").glob("*/"))
    found += [MODELS / "Qwen3-30B-A3B-Thinking-2507", MODELS / "Qwen3.5-35B-A3B"]
    return [d for d in found if (d / "tokenizer_config.json").is_file() and (d / "tokenizer.json").is_file()]


TOKENIZER_DIRS = _tokenizer_dirs()

LOOP_MESSAGES = [
    {"role": "developer", "content": "You are an agent. Reply with one python block."},
    {"role": "user", "content": "Play my most liked song."},
    {"role": "assistant", "content": "```python\nprint(apis.spotify.login())\n```"},
    {"role": "user", "content": "{'access_token': 'x'}"},
    {"role": "assistant", "content": "```python\nprint(1)\n```"},
    {"role": "user", "content": "1"},
]


def _server_ids(tok, request: dict) -> list[int]:
    """What vLLM's chat endpoint does with a request: the chat template over its messages with its template kwargs, as text, then encoded without added special tokens."""
    text = tok.apply_chat_template(request["messages"], tokenize=False, add_generation_prompt=True,
                                   **request.get("chat_template_kwargs", {}))
    return tok.encode(text, add_special_tokens=False)


class RenderTest(unittest.TestCase):

    def setUp(self):
        if not TOKENIZER_DIRS:
            self.skipTest(f"no cached Qwen3-generation tokenizer under {HUB} or {MODELS}")

    def _each(self):
        from transformers import AutoTokenizer
        for d in TOKENIZER_DIRS:
            qwen3.bind_weights(str(d))
            yield d, AutoTokenizer.from_pretrained(str(d))

    def test_render_equals_the_template_tokenized(self):
        for d, tok in self._each():
            with self.subTest(tokenizer=d.name if d.parent.name != "snapshots" else d.parent.parent.name):
                ids = qwen3.render_ids(LOOP_MESSAGES, None, DATE)
                want = tok.apply_chat_template(qwen3.template_messages(LOOP_MESSAGES, DATE),
                                               tokenize=True, return_dict=False,
                                               add_generation_prompt=True, enable_thinking=True)
                self.assertEqual(ids, list(want))

    def test_render_equals_the_server_path_on_the_check_fixture(self):
        for d, tok in self._each():
            with self.subTest(tokenizer=str(d)):
                ids = qwen3.render_ids(CHECK_MESSAGES, None, DATE)
                self.assertEqual(ids, _server_ids(tok, qwen3.chat_request(CHECK_MESSAGES, None, DATE)))
                self.assertEqual(qwen3.render_ids(LOOP_MESSAGES, None, DATE),
                                 _server_ids(tok, qwen3.chat_request(LOOP_MESSAGES, None, DATE)))

    def test_text_shape(self):
        for d, tok in self._each():
            with self.subTest(tokenizer=str(d)):
                text = tok.decode(qwen3.render_ids(LOOP_MESSAGES, None, DATE), skip_special_tokens=False)
                self.assertTrue(text.startswith(
                    "<|im_start|>system\nCurrent date: 2026-08-06\n\n"
                    "You are an agent. Reply with one python block.<|im_end|>\n"))
                self.assertIn("<|im_start|>assistant\n```python\nprint(1)\n```<|im_end|>\n", text)
                # the earlier assistant turns carry content only: the one <think> is the
                # generation prompt's, or none at all when the template leaves it to the model
                self.assertLessEqual(text.count("<think>"), 1)
                self.assertTrue(text.endswith("<|im_start|>assistant\n")
                                or text.endswith("<|im_start|>assistant\n<think>\n"))

    def test_refusals(self):
        for d, _ in self._each():
            with self.subTest(tokenizer=str(d)):
                with self.assertRaises(ValueError):
                    qwen3.render_ids(LOOP_MESSAGES, "high", DATE)
                with self.assertRaises(ValueError):
                    qwen3.render_ids(LOOP_MESSAGES, None, None)
                with self.assertRaises(ValueError):
                    qwen3.render_ids(LOOP_MESSAGES + [{"role": "system", "content": "late"}], None, DATE)
                with self.assertRaises(ValueError):
                    qwen3.render_ids([{"role": "user", "content": "x", "reasoning": "r"}], None, DATE)

    def test_unbound_module_refuses(self):
        saved = qwen3._weights_path
        qwen3._weights_path = None
        try:
            with self.assertRaises(RuntimeError):
                qwen3.render_ids(LOOP_MESSAGES, None, DATE)
            with self.assertRaises(RuntimeError):
                qwen3.end_of_turn([1])
        finally:
            qwen3._weights_path = saved


class EndOfTurnTest(unittest.TestCase):

    def test_end_ids_come_from_the_tokenizer(self):
        if not TOKENIZER_DIRS:
            self.skipTest(f"no cached Qwen3-generation tokenizer under {HUB} or {MODELS}")
        from transformers import AutoTokenizer
        for d in TOKENIZER_DIRS:
            with self.subTest(tokenizer=str(d)):
                qwen3.bind_weights(str(d))
                tok = AutoTokenizer.from_pretrained(str(d))
                im_end, eot = tok.convert_tokens_to_ids(["<|im_end|>", "<|endoftext|>"])
                self.assertTrue(qwen3.end_of_turn([5, im_end]))
                self.assertTrue(qwen3.end_of_turn([5, eot]))
                self.assertFalse(qwen3.end_of_turn([im_end, 5]))
                self.assertFalse(qwen3.end_of_turn(tok.convert_tokens_to_ids(["</think>"])))


REPLY_BODY = ("\nThe user wants a song. First log in. Then read the liked list.\n</think>\n\n"
              "```python\nprint(apis.spotify.login())\n```")


def _stream(text: str, n_splits: int, rng: random.Random) -> list[str]:
    cuts = sorted(rng.sample(range(1, len(text)), min(n_splits, len(text) - 1)))
    return [text[a:b] for a, b in zip([0] + cuts, cuts + [len(text)])]


class ParseTest(unittest.TestCase):

    def _parse_stream(self, deltas: list[str]) -> tuple[dict, list[tuple[str, dict]]]:
        state: dict = {}
        out = {"reasoning": "", "content": ""}
        seen = []
        for delta in deltas:
            out = qwen3.parse(delta, state)
            seen.append((state["raw"], out))
        return out, seen

    def test_split_anywhere_gives_the_same_result(self):
        rng = random.Random(0)
        for prefix in ("<think>", ""):          # the model writes <think>, or the prompt holds it
            text = prefix + REPLY_BODY + "<|im_end|>"
            whole = qwen3.parse(text, {})
            self.assertEqual(whole["reasoning"],
                             "\nThe user wants a song. First log in. Then read the liked list.\n")
            self.assertEqual(whole["content"], "```python\nprint(apis.spotify.login())\n```")
            for n in (1, 2, 5, 17, len(text) - 1):
                for _ in range(20):
                    out, _ = self._parse_stream(_stream(text, n, rng))
                    self.assertEqual(out, whole)

    def test_reasoning_is_a_suffix_of_the_stream_while_thinking(self):
        # agent/step_with_probe.py probes only while the reasoning ends the streamed text
        text = "<think>" + REPLY_BODY
        _, seen = self._parse_stream(list(text))
        for raw, out in seen:
            if "</think>" in raw:
                break
            self.assertTrue(raw.endswith(out["reasoning"]), raw)
            self.assertEqual(out["content"], "")

    def test_unclosed_thinking_is_all_reasoning(self):
        out = qwen3.parse("<think>\nstill thinking. more", {})
        self.assertEqual(out, {"reasoning": "\nstill thinking. more", "content": ""})

    def test_token_deltas_through_the_tokenizer(self):
        if not TOKENIZER_DIRS:
            self.skipTest(f"no cached Qwen3-generation tokenizer under {HUB} or {MODELS}")
        from transformers import AutoTokenizer
        text = "<think>" + REPLY_BODY + "<|im_end|>"
        for d in TOKENIZER_DIRS:
            with self.subTest(tokenizer=str(d)):
                tok = AutoTokenizer.from_pretrained(str(d))
                ids = tok.encode(text, add_special_tokens=False)
                deltas = [tok.decode([i], skip_special_tokens=False) for i in ids]
                self.assertEqual("".join(deltas), text)
                out, _ = self._parse_stream(deltas)
                self.assertEqual(out, qwen3.parse(text, {}))


class WrapPrefetchTest(unittest.TestCase):

    def test_shape(self):
        self.assertEqual(qwen3.wrap_prefetch("f() = 1", None),
                         "\n</think>\n\n<|im_end|>\n<|im_start|>prefetch\nf() = 1<|im_end|>\n"
                         "<|im_start|>assistant\n<think>\n")
        self.assertIn("<|im_start|>prefetch\nSYS\n\nf() = 1<|im_end|>",
                      qwen3.wrap_prefetch("f() = 1", "SYS"))

    def test_parse_skips_the_prefetch_turn_and_reads_the_new_one(self):
        head = "<think>\nFirst log in. "
        note = qwen3.wrap_prefetch("apis.spotify.login() = {'token': 'x'}", "SYS")
        rest = "Now use the token.\n</think>\n\n```python\nprint(2)\n```"
        state: dict = {}
        qwen3.parse(head + note, state)
        out = qwen3.parse(rest, state)
        # the two thinking segments joined by one newline, as gptoss.py joins its analysis bodies
        self.assertEqual(out["reasoning"], "\nFirst log in. \n" + "\n" + "\nNow use the token.\n")
        self.assertEqual(out["content"], "```python\nprint(2)\n```")
        self.assertNotIn("token': 'x'", out["reasoning"] + out["content"])
        self.assertNotIn("SYS", out["reasoning"] + out["content"])

    def test_control_tokens_encode_as_special_ids(self):
        if not TOKENIZER_DIRS:
            self.skipTest(f"no cached Qwen3-generation tokenizer under {HUB} or {MODELS}")
        from transformers import AutoTokenizer
        for d in TOKENIZER_DIRS:
            with self.subTest(tokenizer=str(d)):
                tok = AutoTokenizer.from_pretrained(str(d))
                note_ids = tok.encode(qwen3.wrap_prefetch("x", None), add_special_tokens=False,
                                      split_special_tokens=False)
                special = tok.convert_tokens_to_ids(["</think>", "<|im_end|>", "<|im_start|>", "<think>"])
                for token_id in special:
                    self.assertIn(token_id, note_ids)


if __name__ == "__main__":
    unittest.main()
