"""splice_replay 的 prompt 形态测试(纯 CPU,真分词器 = openai_harmony 自带)。
钉四件事:切口落点(66/75/80/100 与合并)、缝修法 sep、每臂 prompt 尾部的字节、
score 的解析/指标在边界样本上不翻车。
    cprobe-env/bin/python -m unittest tests.test_splice_replay -v
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline" / "inject"))
sys.path.insert(0, str(ROOT / "pipeline" / "annotate"))

import splice_replay as S                                       # noqa: E402
import harmony_render as H                                      # noqa: E402
import rebuild as R                                             # noqa: E402

MSGS = [{"role": "system", "content": R.SYSTEM},
        {"role": "user", "content": "Task from supervisor: do x"},
        {"role": "assistant", "content": "```python\nprint(1)\n```"},
        {"role": "user", "content": "Execution output:\n1"}]
EV = dict(event="t_s1", step=1, call="apis.spotify.login(username=\"a\", password=\"b\")",
          call_tool="apis.spotify.login", code="print(apis.spotify.login(username=\"a\", password=\"b\"))",
          result="{'access_token': 'TOK123'}", next_tool="apis.spotify.show_playlists")
CONTENT = "```python\nprint(apis.spotify.login(username=\"a\", password=\"b\"))\n```"


class TestCuts(unittest.TestCase):
    def test_fracs_land_on_sentence_ends_and_merge(self):
        # 10 句,每句 "Sentence k. " 12 字符 -> 120 字符;66%=79 -> 之前最近句尾 72(第 6 句尾)
        think = " ".join(f"Sentence {k}." for k in range(10))
        cps = S.cut_points(think, [0.66, 0.75, 0.80, 1.0])
        cuts = dict(cps)
        self.assertEqual(cps[-1], (len(think), [1.0]))       # 100% = 全文末尾
        for c, fs in cps[:-1]:
            self.assertTrue(think[c - 1].isspace())          # 句尾在空白之后
            self.assertTrue(think[:c].rstrip().endswith("."))
        self.assertEqual(sum(len(fs) for fs in cuts.values()), 4)   # 四个比例都落了

    def test_short_think_merges_all_into_end(self):
        think = "Only one sentence here that is long enough to pass the filter."
        cps = S.cut_points(think, [0.66, 0.75, 0.80, 1.0])
        self.assertEqual(cps, [(len(think), [1.0])])          # 没有句尾:66/75/80 没事件

    def test_sep(self):
        self.assertEqual(S.sep_for("docs.\n\n"), "")
        self.assertEqual(S.sep_for("docs. "), "")
        self.assertEqual(S.sep_for("docs."), "\n")


class TestPromptBytes(unittest.TestCase):
    def setUp(self):
        self.prefix = H.render_ids(MSGS, effort="high", start_date=R.COLLECT_DATE)

    def tail(self, arm, head, msgs=MSGS):
        ids, plen, sp = S.build_prompt(arm, EV, head, msgs, CONTENT)
        return ids, plen, sp, H.decode(ids)

    def test_prefix_is_chat_render(self):
        for arm in S.ARMS_ALL:
            if arm in ("p1_n0p", "p4"):
                continue
            ids, plen, _, _ = self.tail(arm, "We think.\n\n")
            self.assertEqual(ids[:plen], self.prefix, arm)

    def test_nofill_is_prefix_plus_head(self):
        ids, plen, sp, txt = self.tail("nofill", "We think.\n\n")
        self.assertEqual(sp, "")
        self.assertTrue(txt.endswith("<|start|>assistant<|channel|>analysis<|message|>We think.\n\n"))

    def test_p1_notes_and_seam(self):
        ids, _, _, txt = self.tail("p1_n0", "We think.\n\n")
        self.assertTrue(txt.endswith("We think.\n\n[SYSTEM NOTE: prefetched apis.spotify.login("
                                     "username=\"a\", password=\"b\") = {'access_token': 'TOK123'}]\n"))
        toks = [H.decode([i]) for i in ids[-40:]]
        self.assertIn(".\n\n", toks)                          # 模型自己的 .\n\n 保住
        self.assertEqual(toks[toks.index(".\n\n") + 1], "[S")  # 后面直接接 NOTE
        self.assertNotIn(".\n\n\n", toks)
        ids, _, _, txt = self.tail("p1_n0", "We think. ")
        self.assertTrue(txt.endswith("We think. [SYSTEM NOTE: prefetched"
                                     " apis.spotify.login(username=\"a\", password=\"b\") = {'access_token': 'TOK123'}]\n"))
        toks = [H.decode([i]) for i in ids[-40:]]
        self.assertEqual(toks[toks.index(".") + 1], " [")   # `.` 原样,NOTE inline 接上
        ids, _, _, txt = self.tail("p1_n1", "We think.")
        self.assertTrue(txt.endswith("We think.\nI already ran:\nprint(apis.spotify.login(username=\"a\", "
                                     "password=\"b\"))\nand got:\n{'access_token': 'TOK123'}\n"))
        ids, _, _, txt = self.tail("p1_n2", "We think.\n")
        self.assertTrue(txt.endswith("We think.\n```python\nprint(apis.spotify.login(username=\"a\", "
                                     "password=\"b\"))\n```\nExecution output:\n{'access_token': 'TOK123'}\n"))
        ids, _, _, txt = self.tail("p1_n3", "We think.\n")
        self.assertTrue(txt.endswith("We think.\n{'access_token': 'TOK123'}\n"))

    def test_p1_n0p_has_permit_in_developer(self):
        msgs = [dict(MSGS[0], content=MSGS[0]["content"] + S.PERMIT)] + MSGS[1:]
        ids, plen, _, txt = self.tail("p1_n0p", "We think.\n\n", msgs)
        self.assertIn("A line marked [SYSTEM NOTE: prefetched ...] may appear", txt)
        self.assertNotEqual(ids[:plen], self.prefix)

    def test_p2_ends_in_final_channel_without_trailing_newline(self):
        ids, _, sp, txt = self.tail("p2_n0", "We think.\n\n")
        self.assertTrue(txt.endswith("TOK123'}]<|end|><|start|>assistant<|channel|>final<|message|>"))
        ids, _, sp, txt = self.tail("p2_n1", "We think.\n\n")
        self.assertTrue(txt.endswith("TOK123'}<|end|><|start|>assistant<|channel|>final<|message|>"))

    def test_p3k_fake_turn_keeps_analysis(self):
        ids, _, _, txt = self.tail("p3k", "We think.\n\n")
        self.assertTrue(txt.endswith(
            "<|start|>assistant<|channel|>analysis<|message|>We think.<|end|>"
            "<|start|>assistant<|channel|>final<|message|>" + CONTENT + "<|end|>"
            "<|start|>user<|message|>Execution output:\n{'access_token': 'TOK123'}<|end|>"
            "<|start|>assistant"))
        self.assertNotIn("# Tools", txt)

    def test_p4_python_tool_roundtrip(self):
        ids, _, _, txt = self.tail("p4", "We think.\n\n")
        self.assertIn("# Tools\n\n## python\n\n", txt)
        self.assertTrue(txt.endswith(
            "<|start|>assistant<|channel|>analysis<|message|>We think.<|end|>"
            "<|start|>assistant to=python<|channel|>analysis<|message|>" + EV["code"] + "<|call|>"
            "<|start|>python to=assistant<|channel|>analysis<|message|>{'access_token': 'TOK123'}<|end|>"
            "<|start|>assistant"))
        # developer 段与 chat 前缀一致(只有 system 段变了)
        dev = "<|start|>developer<|message|># Instructions\n\n" + R.SYSTEM
        self.assertIn(dev, txt)

    def test_p4_prefix_is_own_render(self):
        ids, plen, sp, txt = self.tail("p4", "We think.\n\n")
        self.assertTrue(H.decode(ids[:plen]).endswith("<|end|><|start|>assistant"))
        self.assertTrue(sp.startswith("<|channel|>analysis<|message|>We think.<|end|>"))
        ids3, plen3, sp3, _ = self.tail("p3k", "We think.\n\n")
        self.assertEqual(ids3[:plen3], self.prefix)
        self.assertTrue(sp3.startswith("<|channel|>analysis<|message|>We think.<|end|>"))

    def test_encode_matches_render_for_analysis_head(self):
        # 文本臂用 encode(A_OPEN+head) 接前缀;与 harmony 渲染 analysis 消息的字节一致
        from openai_harmony import Conversation, Message, RenderConversationConfig, Role
        hm = H.to_harmony_messages(MSGS, effort="high", start_date=R.COLLECT_DATE)
        hm.append(Message.from_role_and_content(Role.ASSISTANT, "We think.").with_channel("analysis"))
        rendered = list(H.encoding().render_conversation_for_completion(
            Conversation.from_messages(hm), Role.ASSISTANT,
            config=RenderConversationConfig(auto_drop_analysis=False)))
        # 渲染会补 <|end|><|start|>assistant;去掉那截应等于 prefix + enc(A_OPEN+head)
        mine = self.prefix + S.enc(S.A_OPEN + "We think.")
        self.assertEqual(rendered[:len(mine)], mine)
        self.assertEqual(H.decode(rendered[len(mine):]), "<|end|><|start|>assistant")


class TestScoreParse(unittest.TestCase):
    def test_analyze_p1_p2_p3k(self):
        t = ("Continue thinking.<|end|><|start|>assistant<|channel|>final<|message|>"
             "```python\nprint(apis.spotify.show_playlists(access_token=\"TOK123\"))\n```")
        think, content = S.analyze("p1_n0", "\n[SYSTEM NOTE: x]\n", t)
        self.assertEqual(think, "Continue thinking.")
        self.assertIn("show_playlists", content)
        think, content = S.analyze("p2_n0", "\n[SYSTEM NOTE: x]" + S.SWITCH,
                                   "```python\nprint(2)\n```")
        self.assertIn("print(2)", content)
        think, content = S.analyze("p3k", "", "<|channel|>analysis<|message|>Hmm.<|end|>"
                                   "<|start|>assistant<|channel|>final<|message|>```python\nprint(3)\n```")
        self.assertEqual(think, "Hmm.")
        self.assertIn("print(3)", content)

    def test_p4_python_call_is_an_action(self):
        # p4 的自然续写:再叫一次 python(analysis 通道、to=python),停在 <|call|>
        t = " to=python<|channel|>analysis<|message|>print(apis.spotify.show_playlists(access_token=\"TOK\"))"
        think, content = S.analyze("p4", "", t)
        self.assertEqual(content, "")                       # 正文没有
        self.assertIn("show_playlists", S.python_call_code(t))
        self.assertEqual(S.first_tool(S.python_call_code(t)), "apis.spotify.show_playlists")
        self.assertIsNone(S.python_call_code("no tool here"))
        # 模型实际写法(smoke 实测):收件人在通道后、带 " code"
        t2 = ("<|channel|>analysis<|message|>We need phone APIs.\n\n<|end|><|start|>assistant"
              "<|channel|>analysis to=python code<|message|>print(apis.api_docs.show_api_descriptions(app_name=\"phone\"))")
        think, content = S.analyze("p4", "", t2)
        self.assertEqual(think.strip(), "We need phone APIs.")
        self.assertEqual(S.first_tool(S.python_call_code(t2)), "apis.api_docs.show_api_descriptions")
        self.assertTrue(S.stopped_on_call(dict(stop_reason=200012)))
        self.assertTrue(S.stopped_on_call(dict(stop_reason="<|call|>")))
        self.assertFalse(S.stopped_on_call(dict(stop_reason=None)))

    def test_enc_plain_rejects_literal_markers(self):
        with self.assertRaises(ValueError):
            S.enc_plain("text with <|end|> inside")
        self.assertEqual(S.enc_plain("plain. text"), S.enc("plain. text"))
        # 分开编 == 整串编
        self.assertEqual(S.enc(S.A_OPEN) + S.enc_plain("We think.\n\n[NOTE]") + S.enc(S.SWITCH),
                         S.enc(S.A_OPEN + "We think.\n\n[NOTE]" + S.SWITCH))

    def test_first_tool_and_mentions(self):
        self.assertEqual(S.first_tool("x = apis.venmo.list_friends(access_token=t)"),
                         "apis.venmo.list_friends")
        self.assertIsNone(S.first_tool("print(1)"))
        self.assertTrue(S.MENTION_RE.search("The system note says we already have it"))
        self.assertFalse(S.MENTION_RE.search("We need to log in first."))
        self.assertFalse(S.MENTION_RE.search("open the note-taking app simple_note"))
        self.assertTrue(S.ALREADY_RE.search("We already ran that call."))


if __name__ == "__main__":
    unittest.main()
