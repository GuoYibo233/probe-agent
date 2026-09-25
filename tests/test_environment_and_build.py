"""The environment contract as the build uses it, with no AppWorld world held: every call
`build_call` writes parses back through `split_args` to the same tool and arguments (the round-trip
gate of 2.5), `requested_pairs` picks tasks in split, file and seed order, and the build's split
and weight rules give the values the setting names."""
# venv: probe
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from data.build_training_dataset import _split_rule, _weight_rule
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


if __name__ == "__main__":
    unittest.main()
