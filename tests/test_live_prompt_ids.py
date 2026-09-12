"""Shape test for the prompt live_appworld.gen_step sends to vLLM (pure CPU, fake service).

Since 2026-08-18 the prompt is a list of token ids: a step where the probe does not
fire = the prefix_ids given by /render, unchanged; a v6 (ident3) fire-and-resend =
prefix_ids + the model's own generated id[:k] (head = the shortest id prefix covering
the sentence-ending punctuation, verified id by id via /decode) + /encode (NOTE). Fake
http_json / open_stream pin down these assertions here, and along the way pin down that
/health refuses to run if it lacks render/decode fields, and that head still finds the
right spot when the streamed text lags behind the ids.
    python3 -m unittest tests.test_live_prompt_ids -v
"""

import sys
import types
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline" / "inject"))
sys.path.insert(0, str(ROOT / "pipeline" / "annotate"))

import live_appworld as L                                       # noqa: E402

PREFIX = [200006, 17360, 200008, 3575, 200007, 200006, 173781]  # An arbitrary string
THINK = ("<|channel|>analysis<|message|>We need to inspect the profile first. "
         "Then we log in to spotify. Then we list playlists.")
FINAL = "<|end|><|start|>assistant<|channel|>final<|message|>```python\nprint(1)\n```"
HEAD2 = ("<|channel|>analysis<|message|>We need to inspect the profile first. "
         "Then we log in to spotify.")          # head text at the 2nd sentence-ending cut


def fake_encode(text):
    # Fake tokenizer: one character one id (reversible: 100000 + code point), just enough to verify the "prefix + encoding" shape
    return [100000 + ord(c) for c in text]


def words(text):
    """Fake "model tokens": tokenized on spaces before the word (a word with a leading
    space like ' Then' is one token), one stream chunk per token."""
    out, cur = [], ""
    for ch in text:
        if ch == " " and cur:
            out.append(cur)
            cur = ""
        cur += ch
    if cur:
        out.append(cur)
    return out


def word_id(w):
    # Can't use the built-in hash(): string hash gets a random salt per process, so two
    # words occasionally collide on the same id, the decoder's reverse lookup table then
    # mixes up words, and find_head reports inconsistencies at random (an old bug caught on
    # 2026-08-20: the code before the fix failed 4 out of 8 consecutive runs). crc32 is
    # deterministic; pass once, pass forever.
    return 3000 + (zlib.crc32(w.encode()) % 100000)


class FakeStream:
    """Emit (text, ids) chunk by chunk according to pieces; record the payload; count
    close calls. Elements in pieces are either str (id determined by word_id, same
    word same id) or (str, ids)."""
    calls = []

    def __init__(self, base_url, payload, timeout, script):
        self.payload = payload
        self.script = script
        FakeStream.calls.append(payload)
        self.usage = None
        self.finish = None
        self.stop_reason = None
        self.n_chunks = 0
        self.n_ids = 0
        self.closed = 0

    def __iter__(self):
        for piece in self.script:
            text, ids = piece if isinstance(piece, tuple) else (
                piece, [word_id(piece)])
            self.n_chunks += 1
            self.n_ids += len(ids)
            yield text, ids
        self.usage = dict(prompt_tokens=len(self.payload["prompt"]),
                          completion_tokens=self.n_ids)
        self.finish = "stop"

    def close(self):
        self.closed += 1


class Args(types.SimpleNamespace):
    pass


def mk_args(**kw):
    a = Args(base_url="http://vllm", probe_url="http://probe", model="m",
             timeout=5, no_probe=False, max_inject_per_step=1,
             fire_nth_cut=0, nofill=False, format="note",
             # gen-preset (2026-08-20): these three fields hang off args, expanded from --preset;
             # here they are filled with the values of the `default` preset (temperature 1.0)
             max_step_tokens=8192, temperature=1.0, stop=["<|return|>"])
    a.__dict__.update(kw)
    return a


def decoder(all_words):
    """Fake /decode: reverse-look-up the word by id (words in the test are all distinct)."""
    table = {word_id(w): w for w in all_words}
    return lambda ids: "".join(table[i] if i < 100000 else chr(i - 100000)
                               for i in ids)


class TestPureHelpers(unittest.TestCase):
    def test_token_boundary_backs_off(self):
        b = [(0, 0), (5, 1), (9, 2), (15, 3)]
        self.assertEqual(L.token_boundary(b, 9), (9, 2))
        self.assertEqual(L.token_boundary(b, 12), (9, 2))
        self.assertEqual(L.token_boundary(b, 4), (0, 0))
        self.assertEqual(L.token_boundary(b, 100), (15, 3))

    def test_token_boundary_held_back_text_picks_fewest_ids(self):
        b = [(0, 0), (5, 1), (5, 2), (8, 3)]
        self.assertEqual(L.token_boundary(b, 5), (5, 1))
        self.assertEqual(L.token_boundary(b, 8), (8, 3))

    def test_sep_for(self):
        self.assertEqual(L.sep_for("done."), "\n")
        self.assertEqual(L.sep_for("done.\n\n"), "")
        self.assertEqual(L.sep_for("done. "), "")

    def test_sent_starts_stable_as_whitespace_arrives(self):
        base = "x" * 30 + " We need this. "
        s1 = L.sent_starts(base)                 # ". " has arrived
        s2 = L.sent_starts(base + "\n")          # Another newline arrives
        self.assertEqual(s1, s2)                 # Same sentence end, still the same cut
        self.assertEqual(L.sent_cuts(base) != L.sent_cuts(base + "\n"), True)
        self.assertEqual(s1, [len("x" * 30 + " We need this.")])

    def test_find_head_shortest_prefix_covering_pos(self):
        toks = ["<|channel|>", "a.", " b.", "\n\n", "c.\n\n", " d"]
        dec = lambda ids: "".join(toks[i] for i in ids)
        ids = list(range(len(toks)))
        raw = "".join(toks)
        pos_a = len("<|channel|>a.")            # After 'a.'
        self.assertEqual(L.find_head(ids, raw, pos_a, 5, dec), (2, "<|channel|>a."))
        self.assertEqual(L.find_head(ids, raw, pos_a, 1, dec), (2, "<|channel|>a."))
        pos_b = len("<|channel|>a. b.")         # After 'b.', followed by a separate "\n\n" token
        self.assertEqual(L.find_head(ids, raw, pos_b, 4, dec)[0], 3)   # Without "\n\n"
        pos_c = len("<|channel|>a. b.\n\nc.")   # After 'c.', "c.\n\n" is one token
        self.assertEqual(L.find_head(ids, raw, pos_c, 2, dec),
                         (5, "<|channel|>a. b.\n\nc.\n\n"))       # With "\n\n" attached
        # It's fine if the streamed text lags behind the ids (raw only reaches 'b.'):
        self.assertEqual(L.find_head(ids, raw[:pos_b], pos_b, 6, dec)[0], 3)
        # Must raise when text and ids don't line up
        with self.assertRaises(RuntimeError):
            L.find_head(ids, "<|channel|>zz. b.", pos_b, 3, dec)


class TestPromptIds(unittest.TestCase):
    def setUp(self):
        FakeStream.calls = []
        self.logged = []
        self.log = types.SimpleNamespace(w=lambda rec: self.logged.append(rec))
        self._orig = (L.open_stream, L.http_json, L.speculate)

    def tearDown(self):
        L.open_stream, L.http_json, L.speculate = self._orig

    def _http(self, all_words, extra=None):
        dec = decoder(all_words)

        def http(url, payload, **k):
            if url.endswith("/decode"):
                return dict(text=dec(payload["ids"]))
            if url.endswith("/encode"):
                return dict(ids=fake_encode(payload["text"]))
            if extra and url.endswith(extra[0]):
                return extra[1](payload)
            self.fail(f"should not hit {url}")
        return http

    def test_no_probe_prompt_is_prefix_ids_verbatim(self):
        script = words(THINK) + [FINAL]
        L.open_stream = lambda b, p, t, retries=3: FakeStream(b, p, t, script)
        L.http_json = lambda url, payload, **k: self.fail(f"no probe should not hit {url}")
        think, content, usage, discard, n_inj, gen_ids, cons = L.gen_step(
            mk_args(no_probe=True), PREFIX, "task", [], None, "t0", False,
            self.log, 0)
        self.assertEqual(len(FakeStream.calls), 1)
        self.assertEqual(FakeStream.calls[0]["prompt"], PREFIX)
        self.assertEqual(FakeStream.calls[0]["max_tokens"], L.MAX_STEP_TOKENS)
        self.assertNotIn("add_special_tokens", FakeStream.calls[0])
        self.assertEqual(n_inj, 0)
        self.assertIsNone(cons)
        self.assertIn("print(1)", content)
        self.assertTrue(think.startswith("We need to inspect"))
        self.assertEqual(gen_ids, [word_id(w) for w in script])
        self.assertEqual(usage["gen_tok"], len(script))

    def test_probe_fire_resends_prefix_plus_own_ids_plus_note(self):
        # First shot: emit thinking word by word, the probe fires at the end of the second sentence; second shot: continue writing to final
        first = words(THINK)          # The last sentence "Then we list playlists." is overflow
        second = words(" Continue.") + [FINAL]
        scripts = iter([first, second])
        L.open_stream = lambda b, p, t, retries=3: FakeStream(b, p, t, next(scripts))
        n_score = {"n": 0}
        dec = decoder(first + second)

        def http(url, payload, **k):
            if url.endswith("/score"):
                n_score["n"] += 1
                return dict(conf=0.9 if n_score["n"] == 2 else 0.1,
                            label="x", fired=(n_score["n"] == 2))
            if url.endswith("/gen"):
                return dict(call="apis.supervisor.show_profile()")
            if url.endswith("/encode"):
                return dict(ids=fake_encode(payload["text"]))
            if url.endswith("/decode"):
                return dict(text=dec(payload["ids"]))
            self.fail(url)
        L.http_json = http
        L.speculate = lambda world, call, t, g: dict(
            exec_code=call, arg_modes={}, exec_out="{'ok': 1}", exec_ok=True,
            error_kind=None)
        think, content, usage, discard, n_inj, gen_ids, cons = L.gen_step(
            mk_args(), PREFIX, "task", [], None, "t0", False, self.log, 0)
        self.assertEqual(n_inj, 1)
        self.assertEqual(len(FakeStream.calls), 2)
        self.assertEqual(FakeStream.calls[0]["prompt"], PREFIX)
        p2 = FakeStream.calls[1]["prompt"]
        spec = next(r for r in self.logged if r["type"] == "spec")
        head_ids = [word_id(w) for w in words(HEAD2)]   # Stops at "spotify."
        self.assertEqual(spec["head_tok"], len(head_ids))
        self.assertFalse(spec["head_ends_ws"])
        self.assertTrue(spec["note"].startswith("\n[SYSTEM NOTE"))  # head has no trailing whitespace
        self.assertEqual(p2, PREFIX + head_ids + fake_encode(spec["note"]))
        # The second shot's budget is computed from the remaining ids
        self.assertEqual(FakeStream.calls[1]["max_tokens"],
                         L.MAX_STEP_TOKENS - len(p2) + len(PREFIX))
        self.assertEqual(spec["overflow_ids"],
                         [word_id(w) for w in words(" Then we list playlists.")])
        self.assertIn("SYSTEM NOTE", think)
        self.assertNotIn("Then we list playlists", think)   # Overflow after the cut is discarded
        self.assertIn("print(1)", content)
        self.assertEqual(discard["tokens"], 4)
        res = next(r for r in self.logged if r["type"] == "resume")
        self.assertEqual(res["overflow_tok"], 4)
        self.assertFalse(res["identical"])
        # gen_ids = head + note ids + the second shot's ids; the fake decode doesn't recognize
        # note's fake ids at the wrap-up check and would KeyError -- so only gen_ids's shape is
        # verified here
        self.assertEqual(gen_ids, head_ids + fake_encode(spec["note"])
                         + [word_id(w) for w in second])

    def test_nth_cut_nofill_resends_prefix_plus_own_ids_only(self):
        first = words(THINK)
        overflow = words(" Then we list playlists.")
        second = overflow + [FINAL]          # The resent continuation matches the discarded one bit for bit
        scripts = iter([first, second])
        L.open_stream = lambda b, p, t, retries=3: FakeStream(b, p, t, next(scripts))
        L.http_json = self._http(first + second)
        L.speculate = lambda *a: self.fail("nofill should not speculate")
        think, content, usage, discard, n_inj, gen_ids, cons = L.gen_step(
            mk_args(fire_nth_cut=2, nofill=True), PREFIX, "task", [], None,
            "t0", False, self.log, 0)
        self.assertEqual(n_inj, 1)
        spec = next(r for r in self.logged if r["type"] == "spec")
        self.assertTrue(spec["nofill"])
        self.assertIsNone(spec["gen_call"])
        self.assertIsNone(spec["exec_out"])       # All keys score_live needs are present, values are None
        self.assertEqual(spec["note"], "")
        head_ids = [word_id(w) for w in words(HEAD2)]
        self.assertEqual(FakeStream.calls[1]["prompt"], PREFIX + head_ids)
        self.assertNotIn("SYSTEM NOTE", think)
        self.assertIn("Then we list playlists", think)   # The continuation is written out again
        res = next(r for r in self.logged if r["type"] == "resume")
        self.assertTrue(res["identical"])
        self.assertEqual(res["match_len"], len(overflow))
        self.assertEqual(gen_ids, head_ids + [word_id(w) for w in second])
        self.assertEqual(usage["req"], 2)
        # gen_tok(billed) = all of the first shot (including overflow) + the second shot
        self.assertEqual(usage["gen_tok"], len(first) + len(second))
        self.assertTrue(cons)                     # Wrap-up check: decode(gen_ids)==raw

    def test_lagging_text_head_found_by_decode(self):
        # When vLLM has a stop string, text lags behind ids (held back by len(stop)-1
        # characters); here the text is made to lag by 2 tokens: chunk i hands over id(w_i)
        # together with w_{i-2}'s text, and the tail emits the remaining text at the end
        first = words(THINK)
        lag = 2
        script = []
        for i, w in enumerate(first):
            script.append((first[i - lag] if i >= lag else "", [word_id(w)]))
        for w in first[-lag:]:
            script.append((w, []))
        overflow = words(" Then we list playlists.")
        second = overflow + [FINAL]
        scripts = iter([script, second])
        L.open_stream = lambda b, p, t, retries=3: FakeStream(b, p, t, next(scripts))
        n_dec = {"n": 0}
        base_http = self._http(first + second)

        def http(url, payload, **k):
            if url.endswith("/decode"):
                n_dec["n"] += 1
            return base_http(url, payload, **k)
        L.http_json = http
        think, content, usage, discard, n_inj, gen_ids, cons = L.gen_step(
            mk_args(fire_nth_cut=2, nofill=True), PREFIX, "task", [], None,
            "t0", False, self.log, 0)
        self.assertEqual(n_inj, 1)
        head_ids = [word_id(w) for w in words(HEAD2)]
        self.assertEqual(FakeStream.calls[1]["prompt"], PREFIX + head_ids)
        spec = next(r for r in self.logged if r["type"] == "spec")
        self.assertEqual(spec["head_tok"], len(head_ids))
        # At fire time the ids are already 2 ahead of the text: the overflow contains " Then", " we" which haven't appeared in the text yet
        self.assertEqual(spec["overflow_ids"][:2], [word_id(" Then"), word_id(" we")])
        self.assertLessEqual(n_dec["n"], 8)
        self.assertIn("Then we list playlists", think)
        self.assertTrue(cons)

    def test_multi_token_chunk_same_head(self):
        # When the producer is faster than the consumer, several tokens merge into one chunk: head is the same as when tokens arrive one by one
        first = words(THINK)
        merged = []
        i = 0
        while i < len(first):
            grp = first[i:i + 3]
            merged.append(("".join(grp), [word_id(w) for w in grp]))
            i += 3
        second = words(" Then we list playlists.") + [FINAL]
        scripts = iter([merged, second])
        L.open_stream = lambda b, p, t, retries=3: FakeStream(b, p, t, next(scripts))
        L.http_json = self._http(first + second)
        *_, n_inj, gen_ids, cons = L.gen_step(
            mk_args(fire_nth_cut=2, nofill=True), PREFIX, "task", [], None,
            "t0", False, self.log, 0)
        self.assertEqual(n_inj, 1)
        head_ids = [word_id(w) for w in words(HEAD2)]
        self.assertEqual(FakeStream.calls[1]["prompt"], PREFIX + head_ids)

    def test_nth_cut_not_reached_never_fires(self):
        script = words(THINK) + [FINAL]
        L.open_stream = lambda b, p, t, retries=3: FakeStream(b, p, t, script)
        L.http_json = lambda url, payload, **k: self.fail(url)
        *_, n_inj, gen_ids, cons = L.gen_step(
            mk_args(fire_nth_cut=9, nofill=True), PREFIX, "task", [], None,
            "t0", False, self.log, 0)
        self.assertEqual(n_inj, 0)
        self.assertEqual(len(FakeStream.calls), 1)

    def test_decode_mismatch_raises(self):
        first = words(THINK)
        L.open_stream = lambda b, p, t, retries=3: FakeStream(b, p, t, first)
        L.http_json = lambda url, payload, **k: dict(text="something else that is long enough. yes")
        with self.assertRaises(RuntimeError):
            L.gen_step(mk_args(fire_nth_cut=1, nofill=True), PREFIX, "task",
                       [], None, "t0", False, self.log, 0)


P2_OPEN = "<|end|><|start|>prefetch to=assistant<|channel|>analysis<|message|>"
P2_CLOSE = "<|end|><|start|>assistant"
SECOND_THINK = "<|channel|>analysis<|message|>Now act on it."
FINAL_AFTER_TOOL = "<|channel|>final<|message|>```python\nprint(1)\n```"


class TestFormatArms(unittest.TestCase):
    """--format picks the injection text and its placement (inject_format.py). The head is the
    model's own ids in every arm; only the appended text differs."""

    def setUp(self):
        FakeStream.calls = []
        self.logged = []
        self.log = types.SimpleNamespace(w=lambda rec: self.logged.append(rec))
        self._orig = (L.open_stream, L.http_json, L.speculate)
        self.encodes = []

    def tearDown(self):
        L.open_stream, L.http_json, L.speculate = self._orig

    def _fire(self, fmt, second):
        first = words(THINK)
        scripts = iter([first, second])
        L.open_stream = lambda b, p, t, retries=3: FakeStream(b, p, t, next(scripts))
        n_score = {"n": 0}
        dec = decoder(first + second)

        def http(url, payload, **k):
            if url.endswith("/score"):
                n_score["n"] += 1
                return dict(conf=0.9, label="x", fired=(n_score["n"] == 2))
            if url.endswith("/gen"):
                return dict(call="apis.supervisor.show_profile()")
            if url.endswith("/encode"):
                self.encodes.append(payload)
                return dict(ids=fake_encode(payload["text"]))
            if url.endswith("/decode"):
                return dict(text=dec(payload["ids"]))
            self.fail(url)
        L.http_json = http
        L.speculate = lambda world, call, t, g: dict(
            exec_code=call, arg_modes={}, exec_out="{'ok': 1}", exec_ok=True,
            error_kind=None)
        return L.gen_step(mk_args(format=fmt), PREFIX, "task", [], None, "t0",
                          False, self.log, 0)

    def test_p1_e1_appends_plain_text_after_head(self):
        think, content, usage, discard, n_inj, gen_ids, cons = self._fire(
            "p1_e1", words(" Continue.") + [FINAL])
        self.assertEqual(n_inj, 1)
        spec = next(r for r in self.logged if r["type"] == "spec")
        self.assertTrue(spec["note"].startswith("\n[Prefetch: "))
        self.assertIn("{'ok': 1}", spec["note"])
        head_ids = [word_id(w) for w in words(HEAD2)]
        self.assertEqual(FakeStream.calls[1]["prompt"],
                         PREFIX + head_ids + fake_encode(spec["note"]))
        self.assertEqual(self.encodes[0].get("special", False), False)
        self.assertIn("without calling it", think)
        self.assertIn("print(1)", content)

    def test_p2_e1_closes_thinking_and_resumes_at_assistant_start(self):
        think, content, usage, discard, n_inj, gen_ids, cons = self._fire(
            "p2_e1", [FINAL_AFTER_TOOL])
        self.assertEqual(n_inj, 1)
        spec = next(r for r in self.logged if r["type"] == "spec")
        self.assertTrue(spec["note"].startswith(P2_OPEN))
        self.assertTrue(spec["note"].endswith(P2_CLOSE))
        head_ids = [word_id(w) for w in words(HEAD2)]
        self.assertEqual(FakeStream.calls[1]["prompt"],
                         PREFIX + head_ids + fake_encode(spec["note"]))
        self.assertTrue(self.encodes[0]["special"])
        # the prefetch message is not the model's thinking; the model went straight to final
        self.assertNotIn("without calling it", think)
        self.assertEqual(think.strip(), "We need to inspect the profile first. Then we log in to spotify.")
        self.assertIn("print(1)", content)
        self.assertEqual(len(FakeStream.calls), 2)   # thinking is closed: no second fire

    def test_p2_second_thinking_block_joins_thinking(self):
        think, content, *_ = self._fire(
            "p2_e2", words(SECOND_THINK) + ["<|end|><|start|>assistant" + FINAL_AFTER_TOOL])
        self.assertIn("Now act on it.", think)
        self.assertNotIn("show_profile() = ", think)
        self.assertIn("print(1)", content)


class TestParseStep(unittest.TestCase):
    def test_prefetch_segment_is_not_thinking(self):
        full = ("<|channel|>analysis<|message|>Think one." + P2_OPEN
                + "the system already ran x and got 1" + P2_CLOSE
                + "<|channel|>analysis<|message|>Think two."
                + "<|end|><|start|>assistant<|channel|>final<|message|>done")
        think, content = L.parse_step(full)
        self.assertEqual(think, "Think one.\nThink two.")
        self.assertEqual(content, "done")


class TestSystemPrompt(unittest.TestCase):
    def test_note_and_e1_keep_the_collection_system_prompt(self):
        self.assertEqual(L.system_prompt("note"), L.R.SYSTEM)
        self.assertEqual(L.system_prompt("p1_e1"), L.R.SYSTEM)

    def test_e2_appends_the_prefetch_paragraph(self):
        s = L.system_prompt("p1_e2")
        self.assertTrue(s.startswith(L.R.SYSTEM))
        self.assertIn("[Prefetch]", s[len(L.R.SYSTEM):])
        self.assertEqual(L.system_prompt("p2_e2"), s)


class TestHealthGate(unittest.TestCase):
    def test_special_encode_required_for_p2_formats(self):
        cfg = dict(render="harmony_ids", decode=True)
        self.assertIsNone(L.probe_cfg_problem(cfg, need_decode=True, need_special=False))
        self.assertIn("encode_special", L.probe_cfg_problem(cfg, need_decode=True, need_special=True))
        self.assertIsNone(L.probe_cfg_problem(dict(cfg, encode_special=True),
                                              need_decode=True, need_special=True))

    def test_old_server_rejected(self):
        self.assertIn("old probe_server", L.probe_cfg_problem(dict(theta=0.9, temperature=1.8)))
        self.assertIn("old probe_server", L.probe_cfg_problem(dict(render="jinja_text")))

    def test_new_server_accepted(self):
        self.assertIsNone(L.probe_cfg_problem(dict(theta=0.9, render="harmony_ids")))

    def test_decode_required_for_firing_arms(self):
        cfg = dict(render="harmony_ids")
        self.assertIsNone(L.probe_cfg_problem(cfg, need_decode=False))
        self.assertIn("decode", L.probe_cfg_problem(cfg, need_decode=True))
        self.assertIsNone(L.probe_cfg_problem(dict(cfg, decode=True),
                                              need_decode=True))


if __name__ == "__main__":
    unittest.main()
