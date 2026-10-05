"""The environment contract as the build uses it, with no AppWorld world held: every call
`build_call` writes parses back through `split_args` to the same tool and arguments (the round-trip
gate of 2.5), `requested_pairs` picks tasks in split, file and seed order, the build's split
and weight rules give the values the setting names, the contract's two defaults hold, and tau2's and
bfcl's call syntax reads and rebuilds calls the way their own harnesses do."""
# venv: probe
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from data.build_training_dataset import _split_rule, _token_length_lines, _weight_rule
from data.environments import open_env, requested_pairs

TOOL = "apis.file_system.show_directory"
VALUES = ["v", "0", "None", "a@b.com", "Joe Smith", "~/docs/My File.txt", "x, y", "k=v", "f(1, 2)",
          "[1, 2]", "{'a': 1}", "it's", 'say "hi"', " padded ", "", "(", ")", "a\\b", "tab\there",
          "line\nbreak", "access_token", "3.5", "-1", "é", "100%",
          # content that itself starts or ends with a quote: the reader takes one layer off, no more
          '"quoted"', "'q'", 'x"', '"lead', "''", '""', '"a" + "b"', "f'{x}'", "'''tri'''"]


class AppWorldCallSyntaxTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.env = open_env("appworld")

    def test_open_env_holds_the_contract(self):
        for attr in ("NAME", "INSTRUCTIONS", "NO_CODE_MESSAGE", "RESULT_CAP", "SEED", "SPLIT_ROLE"):
            self.assertTrue(hasattr(self.env, attr), attr)
        self.assertEqual(set(self.env.SPLIT_ROLE.values()), {"train", "val", "test"})
        with self.assertRaises(ValueError):
            open_env("no_such_benchmark")

    def test_split_args_reads_the_first_call(self):
        text = "x = 1\nr = apis.spotify.login(username='a@b.com', password=pw)\napis.a.b()"
        tool, args, (start, end) = self.env.split_args(text)
        self.assertEqual(tool, "apis.spotify.login")
        self.assertEqual(args, [("username", "a@b.com"), ("password", "pw")])
        self.assertEqual(text[start:end], "apis.spotify.login(username='a@b.com', password=pw)")
        self.assertEqual(self.env.split_args("apis.x.y('~/a', k=1)")[1], [("pos0", "~/a"), ("k", "1")])
        for no_call in ("no call here", "apis.a.b(x=1", ""):
            self.assertIsNone(self.env.split_args(no_call), no_call)

    def test_build_call_round_trips_what_split_args_reads(self):
        """The build's path: the agent's call -> split_args -> build_call -> split_args, which must
        give the same tool and arguments back (the build skips an event whose call does not)."""
        accepted = 0
        for positional in (True, False):
            for value in VALUES:
                agent_call = f"{TOOL}({'' if positional else 'path='}{value!r})"
                with self.subTest(agent_call=agent_call):
                    parsed = self.env.split_args(agent_call)
                    self.assertIsNotNone(parsed)
                    tool, args, _ = parsed
                    try:
                        call = self.env.build_call(tool, args)
                    except ValueError:
                        continue
                    accepted += 1
                    self.assertEqual(self.env.split_args(call)[:2], (tool, args), call)
        self.assertGreater(accepted, len(VALUES))

    def test_split_args_takes_one_layer_of_quotes_off(self):
        """One layer is the delimiters of a value that is one whole literal; the content's own
        quotes, and a value that is not one literal, stay as written. No escape is undone."""
        cases = [
            (r"""q='say "hi"'""", 'say "hi"'),
            (r"""q="'hi'" """, "'hi'"),
            (r"""q='"'""", '"'),
            (r"""q=''""", ""),
            (r'''q="""multi line"""''', "multi line"),
            (r"""q='''it's'''""", "it's"),
            ('q="a" + "b"', '"a" + "b"'),
            (r"""q=f'{x}'""", "f'{x}'"),
            (r"""q='it\'s'""", r"it\'s"),
            (r"""q=pw""", "pw"),
        ]
        for body, value in cases:
            with self.subTest(body=body):
                self.assertEqual(self.env.split_args(f"{TOOL}({body})")[1], [("q", value)])

    def test_build_call_round_trips_every_value_it_accepts(self):
        """The other direction: a value handed to build_call directly reads back as itself, so a
        value the reader would unwrap is never written bare."""
        accepted = 0
        for key in ("pos0", "path"):
            for value in VALUES:
                with self.subTest(key=key, value=value):
                    try:
                        call = self.env.build_call(TOOL, [(key, value)])
                    except ValueError:
                        continue
                    accepted += 1
                    self.assertEqual(self.env.split_args(call)[:2], (TOOL, [(key, value)]), call)
        self.assertGreater(accepted, len(VALUES))

    def test_build_call_round_trips_several_arguments(self):
        args = [("pos0", "~/docs"), ("query", "x, y"), ("access_token", "tok"), ("page", "0")]
        call = self.env.build_call(TOOL, args)
        self.assertEqual(self.env.split_args(call)[:2], (TOOL, args))

    def test_a_value_with_both_quotes_is_refused(self):
        with self.assertRaises(ValueError):
            self.env.build_call(TOOL, [("q", "it's \"both\", really")])

    def test_complete_call_cuts_the_call_out_of_text(self):
        self.assertEqual(self.env.complete_call("print(apis.a.b(x=f(1), y='z)')) # tail"), "apis.a.b(x=f(1), y='z)')")
        self.assertIsNone(self.env.complete_call("apis.a.b(x="))
        self.assertIsNone(self.env.complete_call(None))

    def test_a_long_output_is_cut_with_a_line_that_says_so(self):
        cap = self.env.RESULT_CAP
        self.assertEqual(self.env._capped("x" * cap), "x" * cap)
        cut = self.env._capped("x" * (cap + 37))
        self.assertTrue(cut.startswith("x" * cap))
        self.assertEqual(cut[cap:], "\n[output cut: 37 more characters not shown]")

    def test_the_setting_replaces_the_modules_reply_cap(self):
        """generation.result_cap, handed to open_env, is the cap the instance cuts at; None keeps
        the module's own, and the module's constant itself never moves."""
        module_cap = type(self.env).RESULT_CAP
        env = open_env("appworld", result_cap=50)
        self.assertEqual(env.RESULT_CAP, 50)
        self.assertEqual(env._capped("x" * 60)[50:], "\n[output cut: 10 more characters not shown]")
        self.assertEqual(open_env("appworld", result_cap=None).RESULT_CAP, module_cap)
        self.assertEqual(type(self.env).RESULT_CAP, module_cap)

    def test_v2_carries_the_official_rules(self):
        v2 = self.env.INSTRUCTIONS["v2"]
        for line in ("- If no answer is required, e.g., for \"Start my Spotify music player.\", omit the answer "
                     "argument (or set it to None/null).",
                     "- Keep answers minimal. Return only the entity, number, or direct value requested - not "
                     "full sentences.",
                     "- Make sure to end code blocks with ``` followed by a newline(\\n).",
                     "so wrap every call whose result you need in print(...)."):
            self.assertIn(line, v2)
        for left_out in ("{{", "Let's start with the task", "in the example above"):
            self.assertNotIn(left_out, v2)


class _FakeTask:
    def __init__(self, api_docs):
        self.api_docs = api_docs


class _FakeWorld:
    def __init__(self, api_docs):
        self.task = _FakeTask(api_docs)


class ChangesStateTest(unittest.TestCase):
    """Which calls the loop may try early: the ones AppWorld documents as reads."""

    @classmethod
    def setUpClass(cls):
        cls.env = open_env("appworld")
        cls.env._world = _FakeWorld({
            "spotify": {
                "show_song": {"method": "GET", "parameters": [{"name": "song_id"}]},
                "login": {"method": "POST", "parameters": [{"name": "username"}, {"name": "password"}]},
                "next_song": {"method": "POST", "parameters": [{"name": "access_token"}]},
                "remove_song": {"method": "DELETE", "parameters": [{"name": "song_id"}]},
                "download_receipt": {"method": "GET", "parameters": [{"name": "download_to_file_path"}]},
            },
            "supervisor": {"complete_task": {"method": "POST", "parameters": [{"name": "answer"}]}},
        })

    @classmethod
    def tearDownClass(cls):
        cls.env._world = None

    def test_reads_change_nothing(self):
        self.assertFalse(self.env.changes_state("apis.spotify.show_song(song_id=3)"))
        self.assertFalse(self.env.changes_state("print(apis.spotify.show_song(song_id=3))"))

    def test_writes_change_the_world(self):
        for call in ("apis.supervisor.complete_task()", "apis.supervisor.complete_task(answer=4)",
                     "apis.spotify.login(username='a@b.com', password=pw)", "apis.spotify.next_song()",
                     "apis.spotify.remove_song(song_id=3)", "apis.spotify.download_receipt()"):
            self.assertTrue(self.env.changes_state(call), call)

    def test_the_first_call_decides(self):
        self.assertTrue(self.env.changes_state("apis.spotify.next_song(); apis.spotify.show_song(song_id=3)"))
        self.assertFalse(self.env.changes_state("apis.spotify.show_song(song_id=3); apis.spotify.next_song()"))

    def test_a_text_with_no_call_and_an_unknown_api_change_nothing(self):
        for call in ("None", "", None, "apis.spotify.show_song(song_id=", "apis.nowhere.do(x=1)",
                     "apis.spotify.no_such_api()"):
            self.assertFalse(self.env.changes_state(call), call)

    def test_it_needs_an_open_task(self):
        env = open_env("appworld")
        with self.assertRaises(RuntimeError):
            env.changes_state("apis.spotify.show_song(song_id=3)")


class ContractDefaultsTest(unittest.TestCase):
    """The two contract methods with defaults: a benchmark whose developer message is one text
    sends INSTRUCTIONS[variant] as it stands, and one with no simulated party keeps no endpoint."""

    def test_appworld_sends_its_instructions_as_they_stand(self):
        env = open_env("appworld")
        for variant in env.INSTRUCTIONS:
            self.assertEqual(env.instructions(variant), env.INSTRUCTIONS[variant])
        self.assertIsNone(env.bind_agent("http://h:1/v1", "m"))

    def test_the_new_benchmarks_hold_the_contract(self):
        for name in ("tau2", "bfcl"):
            env = open_env(name)
            for attr in ("NAME", "INSTRUCTIONS", "NO_CODE_MESSAGE", "RESULT_CAP", "SEED", "SPLIT_ROLE"):
                self.assertTrue(hasattr(env, attr), (name, attr))
            self.assertEqual(env.NAME, name)
            self.assertLessEqual(set(env.SPLIT_ROLE.values()), {"train", "val", "test"})
            with self.assertRaises(RuntimeError):
                env.instructions("v1")


class Tau2CallSyntaxTest(unittest.TestCase):
    """tau2's text form of a tool call: the whole reply is one call (or a list of calls) to a bare
    name with JSON values; anything else is a message to the user."""

    @classmethod
    def setUpClass(cls):
        cls.env = open_env("tau2")

    def test_a_reply_that_is_a_call_is_read_and_a_message_is_not(self):
        tool, args, (start, end) = self.env.split_args('get_user_details(user_id="sara_doe_496")')
        self.assertEqual((tool, args), ("get_user_details", [("user_id", '"sara_doe_496"')]))
        fenced = "```json\nget_order_details(order_id='#W1')\n```"
        tool, args, (start, end) = self.env.split_args(fenced)
        self.assertEqual((tool, args), ("get_order_details", [("order_id", '"#W1"')]))
        self.assertEqual(fenced[start:end], "get_order_details(order_id='#W1')")
        self.assertEqual(self.env.split_args("[think(thought='a'), think(thought='b')]")[1], [("thought", '"a"')])
        for message in ("Sure, I can help(you) with that.", "Hello", "", None, "get_user_details(user_id='x'",
                        "Your total is calculate(1).", "[NO RESPONSE]", "[ ]", "The options are [1, 2]."):
            self.assertIsNone(self.env.split_args(message), message)

    def test_the_turn_ends_at_the_first_call_list(self):
        """Text around a call list: the first list of calls is the call, as a native function
        call ends the model's turn; what comes after it is never read."""
        mixed = ('We need to look it up.\n[NO RESPONSE]\n[ get_reservation_details(reservation_id="EHGLP3") ]\n'
                 '[NO RESPONSE]\n[cancel_reservation(reservation_id="EHGLP3")]')
        tool, args, (start, end) = self.env.split_args(mixed)
        self.assertEqual((tool, args), ("get_reservation_details", [("reservation_id", '"EHGLP3"')]))
        self.assertEqual(mixed[start:end], 'get_reservation_details(reservation_id="EHGLP3")')
        nested = "[f(x=[1, 2], y='a]b'), g()] and then more text"
        self.assertEqual(self.env.split_args(nested)[:2], ("f", [("x", "[1, 2]"), ("y", '"a]b"')]))

    def test_values_read_as_one_json_text(self):
        """The same value written two ways reads the same: quotes, JSON's true/false/null and
        Python's True/False/None, tuples and lists."""
        a = self.env.split_args("f(x='v', y=True, z=None, w=(1, 2))")[1]
        b = self.env.split_args('f(x="v", y=true, z=null, w=[1, 2])')[1]
        self.assertEqual(a, b)
        self.assertEqual(a, [("x", '"v"'), ("y", "true"), ("z", "null"), ("w", "[1, 2]")])

    def test_build_call_round_trips_what_split_args_reads(self):
        for call in ('book_reservation(user_id="a", passengers=[{"first_name": "A", "dob": null}], insurance="no")',
                     "think()", "calculate(expression='(2 + 3) * 4')", 'f(text="it\'s \\"quoted\\"")',
                     "f(x=some_name)", "f(1, k=2)"):
            with self.subTest(call=call):
                tool, args, _ = self.env.split_args(call)
                rebuilt = self.env.build_call(tool, args)
                self.assertEqual(self.env.split_args(rebuilt)[:2], (tool, args))
        with self.assertRaises(ValueError):
            self.env.build_call("f", [("x", "(")])

    def test_complete_call_and_the_open_task_rule(self):
        self.assertEqual(self.env.complete_call("get_x(a='b)') and more"), "get_x(a='b)')")
        self.assertIsNone(self.env.complete_call("get_x(a="))
        with self.assertRaises(RuntimeError):
            self.env.changes_state("cancel_reservation(reservation_id='X')")

    def test_the_text_before_a_call_list_is_the_messages_content(self):
        """What a reply says before its call list rides on the call message; a reply that is one
        call list, fenced or not, says nothing before it (the fence opener is not text)."""
        from data.environments import tau2 as tau2_module
        for raw in ("```json\nget_order_details(order_id='#W1')\n```", "get_order_details(order_id='#W1')",
                    "  [get_order_details(order_id='#W1')]  "):
            source = tau2_module._unfenced(raw)
            calls_source, _, start = tau2_module._reply_calls(raw)
            self.assertIsNone(tau2_module._message_text_before_calls(raw, source, calls_source, start), raw)
        mixed = "Let me check.\n[get_order_details(order_id='#W1')]\nand more"
        source = tau2_module._unfenced(mixed)
        calls_source, _, start = tau2_module._reply_calls(mixed)
        self.assertEqual(tau2_module._message_text_before_calls(mixed, source, calls_source, start), "Let me check.")

    def test_the_user_simulators_visible_text(self):
        """The agent reads what follows a closing think tag, nothing from an unclosed one (the
        thinking quotes the hidden scenario), and the whole text when there is no tag."""
        from data.environments import tau2 as tau2_module
        self.assertEqual(tau2_module._visible_text("<think>the scenario says X</think>\n\nHi, my phone broke."),
                         "Hi, my phone broke.")
        self.assertEqual(tau2_module._visible_text("<think>the scenario says X and"), "")
        self.assertEqual(tau2_module._visible_text("Hi, my phone broke."), "Hi, my phone broke.")


class BFCLCallSyntaxTest(unittest.TestCase):
    """BFCL's prompting-mode call format, read the way its decoder reads a reply."""

    @classmethod
    def setUpClass(cls):
        cls.env = open_env("bfcl")

    def test_split_args_follows_the_official_decoder(self):
        """Ends stripped of backticks, newlines and spaces, a missing bracket added, keyword
        arguments only (the decoder drops a positional one, so sort('a') runs as sort())."""
        text = "[cd(folder='document'), mkdir(dir_name='temp')]"
        tool, args, (start, end) = self.env.split_args(text)
        self.assertEqual((tool, args), ("cd", [("folder", "'document'")]))
        self.assertEqual(text[start:end], "cd(folder='document')")
        fenced = "```\n[ls(a=True)]\n```"
        tool, args, (start, end) = self.env.split_args(fenced)
        self.assertEqual((tool, args, fenced[start:end]), ("ls", [("a", "True")], "ls(a=True)"))
        self.assertEqual(self.env.split_args("sort('final_report.pdf')")[:2], ("sort", []))
        self.assertEqual(self.env.split_args('cd(folder="x")')[1], self.env.split_args("cd(folder='x')")[1])
        for no_call in ("I have finished the task.", "[]", "", None, "```python\n[ls()]\n```"):
            self.assertIsNone(self.env.split_args(no_call), no_call)

    def test_build_call_round_trips_what_split_args_reads(self):
        for call in ("post_tweet(content='hi, all', tags=['#a', '#b'], mentions=[])", "pwd()",
                     "echo(content='a\\nb', file_name='x.txt')", "f(x=g(1))"):
            with self.subTest(call=call):
                tool, args, _ = self.env.split_args(call)
                self.assertEqual(self.env.split_args(self.env.build_call(tool, args))[:2], (tool, args))

    def test_the_reader_reads_what_the_decoder_resolves(self):
        """An argument value BFCL's resolve_ast_by_type turns into a value is read; one it
        raises on (an attribute, an f-string, a set, a comparison) and one it would hand to eval
        (arithmetic, a lambda) count as no call, so a step the build labels is a step that ran."""
        for call in ("f(x=-1, y=2.5)", "f(x=some_name)", "f(x=g(1))", "f(x=g(k=[1, 2]))", "f(x=d['k'])",
                     "f(x=[1, {'a': None}], y=(True, 'b'))", "[f(x=1), g(y='z')]"):
            with self.subTest(call=call):
                self.assertIsNotNone(self.env.split_args(call), call)
        for no_call in ("[mv(source=file.name, destination='b')]", "[f(x=f'{a}')]", "[f(x={1, 2})]",
                        "[f(x=a > b)]", "[f(x=1 + 2)]", "[f(x=lambda: 1)]", "[f(x=-'a')]", "[f(x=[1, a.b])]",
                        "[f(x=g(k=1 + 2))]"):
            with self.subTest(no_call=no_call):
                self.assertIsNone(self.env.split_args(no_call), no_call)

    def test_changes_state_reads_the_write_table(self):
        self.assertTrue(self.env.changes_state("cd()"))
        self.assertTrue(self.env.changes_state("[get_flight_cost(travel_from='A', travel_to='B')]"))
        self.assertFalse(self.env.changes_state("ls()"))
        self.assertFalse(self.env.changes_state("I will now stop."))
        self.assertEqual(self.env.complete_call("[cd(folder='a)b'), ls()]"), "cd(folder='a)b')")


class _FakeEnv:
    def __init__(self, splits):
        self._splits = splits

    def tasks(self, split):
        return list(self._splits[split])


class RequestedPairsTest(unittest.TestCase):

    def test_order_filter_and_cap(self):
        env = _FakeEnv({"train": ["a", "b", "c"], "test": ["x", "y"]})
        self.assertEqual(requested_pairs(env, ["test", "train"], None, 1, [1, 2]),
                         [("test", "x", 1), ("test", "x", 2), ("train", "a", 1), ("train", "a", 2)])
        self.assertEqual(requested_pairs(env, ["train"], ["c", "a", "zz"], None, [7]),
                         [("train", "a", 7), ("train", "c", 7)])
        self.assertEqual(len(requested_pairs(env, ["train", "test"], None, None, [1, 2, 3])), 15)


class BuildRulesTest(unittest.TestCase):

    def test_env_split_follows_the_benchmark_role(self):
        env = open_env("appworld")
        split_of = _split_rule("env", env, None)
        for benchmark_split, role in env.SPLIT_ROLE.items():
            self.assertEqual(split_of("any_task", benchmark_split), role)

    def test_hash_split_is_stable_and_follows_the_ratio(self):
        split_of = _split_rule("hash", None, [0.8, 0.1, 0.1])
        tasks = [f"task_{i}" for i in range(20000)]
        first = [split_of(t, "ignored") for t in tasks]
        self.assertEqual(first, [split_of(t, "other") for t in tasks], "the benchmark split plays no part")
        for name, share in (("train", 0.8), ("val", 0.1), ("test", 0.1)):
            self.assertAlmostEqual(first.count(name) / len(tasks), share, delta=0.015)
        only_test = _split_rule("hash", None, [0.0, 0.0, 1.0])
        self.assertEqual({only_test(t, "") for t in tasks[:200]}, {"test"})

    def test_weights(self):
        self.assertEqual(_weight_rule("uniform")(7), 1.0)
        self.assertEqual(_weight_rule("per_event")(4), 0.25)
        self.assertEqual(_weight_rule("per_event")(3), round(1 / 3, 6))

    def test_unknown_axis_values_are_refused(self):
        with self.assertRaises(ValueError):
            _split_rule("random", None, None)
        with self.assertRaises(ValueError):
            _weight_rule("by_depth")

    def test_token_length_line_without_a_probe_backbone(self):
        """A build frozen with no models section (before models.probe joined the build
        projection), or a setting with no probe, gets one line saying the tokens were not
        measured, and the build goes on."""
        from types import SimpleNamespace
        import polars as pl
        frame = pl.DataFrame({"event_id": ["e"], "text": ["Task: t"]})
        for cfg in (SimpleNamespace(models=None),
                    SimpleNamespace(models=SimpleNamespace(probe=None, probe_row=None))):
            lines = _token_length_lines(cfg, frame)
            self.assertEqual(len(lines), 1)
            self.assertIn("not measured", lines[0])


if __name__ == "__main__":
    unittest.main()
