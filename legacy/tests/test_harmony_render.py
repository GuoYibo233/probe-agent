"""Judge test verifying harmony_render.render_ids renders token-for-token identical to
the vLLM chat endpoint.

Judge = vLLM 0.26.0's own three functions (build_harmony_preamble /
parse_chat_inputs_to_harmony_messages / render_for_completion), i.e. the same three
steps `renderers/online_renderer.py:_make_request_with_harmony` goes through.
So this test can only run under envs/vllm-env:
    envs/vllm-env/bin/python -m unittest tests.test_harmony_render -v
Other interpreters lacking vllm or openai_harmony skip the whole file; that does not
count as a failure.
"""

import os
import sys
import unittest
from pathlib import Path

# The judge reads VLLM_SYSTEM_START_DATE to pin the date; it must be set before import vllm
PIN = "2026-07-31"
os.environ.setdefault("VLLM_SYSTEM_START_DATE", PIN)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline" / "inject"))

try:
    from vllm.entrypoints.openai.parser.harmony_utils import (  # noqa: E402
        build_harmony_preamble, extract_instructions_from_messages,
        parse_chat_inputs_to_harmony_messages, render_for_completion)
    import harmony_render as HR                                     # noqa: E402
    HAVE = True
except Exception as e:  # vllm / openai_harmony are not in this interpreter
    HAVE = False
    WHY = repr(e)

SYSTEM = ("You are an autonomous agent operating a phone-like environment "
          "on behalf of your supervisor.\n\nRules:\n- Each turn, write exactly "
          "ONE ```python ... ``` code block.")
NO_CODE = "No ```python``` block found. Reply with exactly one python code block."


def judge_ids(messages, effort):
    instr, rest = extract_instructions_from_messages(list(messages))
    hm = build_harmony_preamble(instructions=instr, tools=None,
                                reasoning_effort=effort, with_custom_tools=False)
    hm.extend(parse_chat_inputs_to_harmony_messages(rest))
    return render_for_completion(hm)


@unittest.skipUnless(HAVE, "needs envs/vllm-env (vllm + openai_harmony)")
class TestRenderIds(unittest.TestCase):
    base = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": "Task from supervisor: Do X."}]
    two = base + [
        {"role": "assistant",
         "content": "```python\nprint(apis.api_docs.show_app_descriptions())\n```"},
        {"role": "user", "content": "Execution output:\n[...]"}]

    def same(self, msgs, effort="high"):
        want = judge_ids(msgs, effort)
        got = HR.render_ids(msgs, effort=effort, start_date=PIN)
        self.assertEqual(want, got)
        return got

    def test_step0(self):
        ids = self.same(self.base)
        self.assertGreater(len(ids), 50)

    def test_two_turn(self):
        self.same(self.two)

    def test_empty_assistant_dropped(self):
        # The chat endpoint drops assistant turns with empty content (around harmony_utils line 430)
        msgs = self.two + [{"role": "assistant", "content": ""},
                           {"role": "user", "content": NO_CODE}]
        ids = self.same(msgs)
        self.assertEqual(ids, self.same(self.two + [{"role": "user", "content": NO_CODE}]))

    def test_none_content_assistant_dropped(self):
        msgs = self.two + [{"role": "assistant", "content": None},
                           {"role": "user", "content": NO_CODE}]
        self.same(msgs)

    def test_whitespace_assistant_kept(self):
        self.same(self.two + [{"role": "assistant", "content": "   "},
                              {"role": "user", "content": NO_CODE}])

    def test_literal_harmony_marks_are_text(self):
        # The chat endpoint encodes literal <|...|> as plain text, not collapsed into a special token
        msgs = self.two + [
            {"role": "assistant",
             "content": "Some prose then <|channel|>final<|message|> literal <|end|> x"},
            {"role": "user", "content": "Execution output:\nok"}]
        ids = self.same(msgs)
        # 7 messages (system/developer/user/assistant/user/assistant/user) each contribute one
        # structural <|end|> (200007); the literal <|end|> inside content must not be counted extra
        self.assertEqual(ids.count(200007), 7)
        text = HR.decode(ids)
        self.assertIn("<|channel|>final<|message|> literal <|end|> x", text)

    def test_effort_variants(self):
        for e in ("low", "medium", "high"):
            self.same(self.two, effort=e)

    def test_no_system_message(self):
        self.same([{"role": "user", "content": "hi"}])

    def test_long_history(self):
        msgs = list(self.two)
        for i in range(6):
            msgs.append({"role": "assistant",
                         "content": f"step {i}\n```python\nprint({i})\n```"})
            msgs.append({"role": "user", "content": f"Execution output:\n{i}\n"})
        self.same(msgs)

    def test_unicode_and_newlines(self):
        msgs = self.two + [
            {"role": "assistant", "content": "Chinese → émoji 🙂\n\n\n```python\nx=1\n```"},
            {"role": "user", "content": "Execution output:\n\n\ttabbed\r\nCRLF"}]
        self.same(msgs)

    def test_ends_with_start_assistant(self):
        ids = self.same(self.two)
        self.assertTrue(HR.decode(ids).endswith("<|start|>assistant"))

    def test_rejects_tool_calls(self):
        with self.assertRaises(ValueError):
            HR.render_ids(self.two + [{"role": "assistant", "content": "",
                                       "tool_calls": [{"id": "x"}]}],
                          effort="high", start_date=PIN)

    def test_bad_effort(self):
        with self.assertRaises(ValueError):
            HR.render_ids(self.two, effort="none", start_date=PIN)


if __name__ == "__main__":
    if not HAVE:
        print("SKIP:", WHY)
    unittest.main()
