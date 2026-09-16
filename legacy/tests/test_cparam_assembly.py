"""String-assembly unit tests for the cparam cell: target-string derivation on the
training side + reassembly and parsing on the eval side.

Training side: `param_target` is the cparam cell's only string-assembly rule; get
it wrong and the training target shifts by a whole slot, with no error raised.
Eval side: eval_causal_param scores by reassembling given + "(" + the generated
string; the reassembly must be the inverse of param_target, and the convention
for parsing (parse_call/split_named_raw) is pinned down here -- including the
existing scoring convention that "bracket balancing doesn't recognize quotes"
(recorded as-is, scoring unchanged).

How to run (train_causal_param imports torch/transformers at the top, so it
needs cprobe-env):
  cprobe-env/bin/python -m unittest tests.test_cparam_assembly -v
When system python3 runs the full discover, this module is skipped entirely (no
torch), which doesn't count as a failure; under mbert-env (transformers 4.57.6)
train_causal_param raises SystemExit rather than ImportError, which is also
caught and skipped the same way.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline/train"))
sys.path.insert(0, str(ROOT / "pipeline/eval"))
try:
    from train_causal_param import (CALL_SEP, param_prompt_tail,  # noqa: E402
                                    param_target)
    from train_causal_callgen import CALL_SEP as CGEN_CALL_SEP    # noqa: E402
    import eval_causal_param as ecp                               # noqa: E402
except ImportError as e:                      # system python3 doesn't have torch
    raise unittest.SkipTest(f"needs the cprobe-env interpreter: {e}")
except SystemExit as e:                       # mbert-env's transformers<5.14
    raise unittest.SkipTest(f"needs the cprobe-env interpreter: {e}")

sys.path.insert(0, str(ROOT / "pipeline/annotate"))
from build import make_call  # noqa: E402


class TestParamTarget(unittest.TestCase):
    def test_named_args(self):
        label = "apis.spotify.login"
        call = "apis.spotify.login(username=x, password=y)"
        self.assertEqual(param_target(label, call), "username=x, password=y)")

    def test_no_args(self):
        label = "apis.phone.logout"
        self.assertEqual(param_target(label, "apis.phone.logout()"), ")")

    def test_prefix_mismatch_returns_none(self):
        # Tool name doesn't match (data contamination / upstream changed the assembly rule)
        self.assertIsNone(param_target("apis.spotify.login",
                                       "apis.spotify.logout(a=1)"))
        # missing the left parenthesis
        self.assertIsNone(param_target("apis.spotify.login",
                                       "apis.spotify.login"))
        # The tool name is a prefix of the true value but not the same name (the classic startswith trap)
        self.assertIsNone(param_target("send", "send_email(to=a)"))

    def test_roundtrip_against_make_call(self):
        """The single source of truth for string assembly is build.make_call: tool name + "(" + target == label_call."""
        cases = [
            ("apis.spotify.login",
             [dict(key="username", value="x"), dict(key="password", value="y")]),
            ("apis.phone.logout", []),
            ("apis.gmail.send_email",
             [dict(key="body", value='hi, there (really)')]),
        ]
        for tool, named in cases:
            call = make_call(tool, named)
            tgt = param_target(tool, call)
            self.assertIsNotNone(tgt, call)
            self.assertEqual(tool + "(" + tgt, call)
            self.assertTrue(tgt.endswith(")"), tgt)

    def test_prompt_tail(self):
        self.assertEqual(param_prompt_tail("apis.spotify.login"),
                         CALL_SEP + "apis.spotify.login(")
        self.assertEqual(CALL_SEP, "\n[CALL] ")


class TestEvalSideReassembly(unittest.TestCase):
    """The two-file contract between eval-side reassembly and training-side stripping, plus real-world eval-side parsing test cases."""

    def test_reassembly_contract(self):
        """Contract: given + "(" + gen == label_call if and only if
        gen == param_target(label, label_call). The eval-side score_points
        reassembly string (eval_causal_param.py) and the training-side target
        stripping must be inverse operations of each other."""
        cases = [
            ("apis.spotify.login",
             [dict(key="username", value="x"), dict(key="password", value="y")]),
            ("apis.phone.logout", []),
            ("apis.gmail.send_email",
             [dict(key="body", value="hi, there (really)")]),
        ]
        for tool, named in cases:
            call = make_call(tool, named)
            tgt = param_target(tool, call)
            # Forward: when gen is exactly param_target, the reassembled string returns to label_call byte-for-byte
            self.assertEqual(tool + "(" + tgt, call)
            # Reverse: when gen deviates from param_target by one character, the reassembled string no longer equals label_call
            for wrong in (tgt + " ", "x" + tgt, tgt[:-1]):
                self.assertNotEqual(tool + "(" + wrong, call)

    def test_value_with_comma_quote_paren(self):
        """Real-world eval-side parsing: values contain commas/quotes/nested parentheses,
        quotes protect commas and parentheses, the key-value pairs cut out must be
        exactly right, not one wrong (values keep the un-normalized original string)."""
        full = ('apis.gmail.send_email(to=a@b.c, '
                'body="hi, there (really)", subject=\'x, y\')')
        tool, raw = ecp.parse_call(full, "appworld")
        self.assertEqual(tool, "apis.gmail.send_email")
        self.assertEqual(raw, [("to", "a@b.c"),
                               ("body", '"hi, there (really)"'),
                               ("subject", "'x, y'")])

    def test_quote_blind_paren_balance_is_existing_convention(self):
        """Recorded as-is, scoring unchanged: parse_call's bracket balancing when finding
        the whole call's right boundary doesn't recognize quotes (cgen's existing
        scoring convention). When a bare right parenthesis appears inside a value,
        truncation happens at that in-quote right parenthesis, and the whole back half
        is dropped."""
        tool, raw = ecp.parse_call('apis.gmail.send(body="a ) b")', "appworld")
        self.assertEqual(tool, "apis.gmail.send")
        self.assertEqual(raw, [("body", '"a')])


class TestSeparatorConstants(unittest.TestCase):
    def test_three_separator_constants_agree(self):
        """The three delimiter constants cross-check each other: changing any one alone silently changes the string-assembly convention."""
        self.assertEqual(CALL_SEP, CGEN_CALL_SEP)
        self.assertEqual(CALL_SEP, ecp.FALLBACK_SEP)


if __name__ == "__main__":
    unittest.main()
