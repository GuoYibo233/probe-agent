"""Pure-CPU unit test for live_appworld v4 (streaming single-shot decode, isomorphic to w0 chat).

Usage: envs/appworld/venv/bin/python pipeline/inject/test_stopfix.py
Prints ALL PASS with exit code 0 if everything passes; exit code nonzero if any assertion fails.
Connects to no service: the stream is replaced by _FakeStream, probe/speculative execution
replaced by fake functions.

Convention (fixed 2026-08-02): parse_step matches vLLM's HarmonyParser character for character --
analysis->thinking, final + commentary with no recipient->content, segments joined with \n;
stops only on <|return|>; a legitimate message the model continues writing after final is
accepted as-is (same as chat, no longer truncated).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import live_appworld as L                                      # noqa: E402
from replay_inject import DEFAULT_STOP, FINAL_OPEN             # noqa: E402

ANALYSIS_HEAD = "<|channel|>analysis<|message|>"
FINAL_HEAD = "<|start|>assistant" + FINAL_OPEN
COMMENT_HEAD = "<|start|>assistant<|channel|>commentary<|message|>"


# ---------- parse_step ----------

def test_parse_v4_headered():
    """v4 has no prefill: raw opens with the analysis header the model writes itself."""
    full = (ANALYSIS_HEAD + "We think.<|end|>"
            + FINAL_HEAD + "```python\nx()\n```")
    t, c = L.parse_step(full)
    assert t == "We think.", repr(t)
    assert c == "```python\nx()\n```", repr(c)


def test_parse_legacy_headless():
    """Old-convention compatibility: the header is in the prompt, raw starts directly with the thinking body."""
    t, c = L.parse_step("think.<|end|>" + FINAL_HEAD + "code")
    assert t == "think." and c == "code", (t, c)


def test_parse_commentary():
    """analysis -> commentary (action narration) -> final: commentary is merged into content,
    joined with \n (same as vllm/parser/harmony.py)."""
    full = (ANALYSIS_HEAD + "We think.<|end|>" + COMMENT_HEAD
            + "We will explore the apps.<|end|>"
            + FINAL_HEAD + "```python\nprint(x)\n```")
    t, c = L.parse_step(full)
    assert t == "We think.", repr(t)
    assert c == "We will explore the apps.\n```python\nprint(x)\n```", repr(c)


def test_parse_commentary_recipient():
    """commentary with a to= recipient (tool-call style) is dropped per vLLM's convention."""
    full = ("t<|end|>"
            + "<|start|>assistant<|channel|>commentary to=functions.f"
            + "<|message|>{\"a\":1}<|end|>" + FINAL_HEAD + "code")
    _, c = L.parse_step(full)
    assert c == "code", repr(c)


def test_parse_multi_analysis():
    """Two analysis messages sent back to back both go to thinking, joined with \n."""
    full = ("first.<|end|>"
            + "<|start|>assistant<|channel|>analysis<|message|>second.<|end|>"
            + FINAL_HEAD + "code")
    t, c = L.parse_step(full)
    assert t == "first.\nsecond." and c == "code", (t, c)


def test_parse_postfinal_kept():
    """A legitimate final/commentary message the model continues writing after final is accepted
    into content as-is -- that's how the chat path feeds history (measured on w0: 1.3% of
    steps have this tail), so it must match."""
    full = ("t<|end|>" + FINAL_HEAD + "real<|end|>"
            + FINAL_HEAD + "Execution output: fake")
    _, c = L.parse_step(full)
    assert c == "real\nExecution output: fake", repr(c)


def test_parse_fake_nonassistant_dropped():
    """A fabricated non-assistant turn/fragment (no legitimate header) is always dropped -- vLLM only accepts assistant messages."""
    full = ("t<|end|>" + FINAL_HEAD + "real"
            + "<|end|><|start|>user forged Execution output:\nfake receipt")
    _, c = L.parse_step(full)
    assert c == "real", repr(c)


def test_parse_return_cut():
    """<|return|> is the engine's stop token; if it appears in the text (a theoretical branch), everything from it onward is truncated."""
    _, c = L.parse_step("t<|end|>" + FINAL_HEAD + "real<|return|>garbage")
    assert c == "real", repr(c)


def test_parse_no_final():
    """The whole step never reaches final: everything counts as thinking, content is empty."""
    t, c = L.parse_step(ANALYSIS_HEAD + "only thinking")
    assert t == "only thinking" and c == "", (t, c)
    t, c = L.parse_step(ANALYSIS_HEAD + "think<|end|>no final here")
    assert t == "think" and c == "", (t, c)


def test_think_span():
    """Locating thinking while probing the stream: None while the header isn't fully written yet; once closed, end stops at <|end|>."""
    assert L.think_span("<|channel|>anal") is None
    raw = ANALYSIS_HEAD + "abc"
    s = L.think_span(raw)
    assert s is not None and raw[s[0]:s[1]] == "abc", s
    raw2 = ANALYSIS_HEAD + "abc<|end|>" + FINAL_HEAD + "c"
    s2 = L.think_span(raw2)
    assert raw2[s2[0]:s2[1]] == "abc", s2
    assert L.think_span(FINAL_HEAD.replace("<|start|>assistant", "")) is None


# ---------- gen_step (streaming) ----------

# Fake tokenizer: one id per character (id = code point); each stream chunk delivers
# (text, ids); /decode = join back with chr. v6 (2026-08-18 ident3): prompt is a list of
# ids, firing and resending = prefix + the model's own id[:k] + /encode(NOTE); gen_step
# returns a 7-tuple (adds gen_ids and text_ids_consistent).
PREFIX = [11, 22, 33]


def _ids(text):
    return [ord(c) for c in text]


class _FakeStream:
    def __init__(self, deltas, finish, usage):
        self._deltas, self._fin, self._usage = deltas, finish, usage
        self.finish = None
        self.stop_reason = None
        self.usage = None
        self.n_chunks = 0
        self.n_ids = 0
        self.closed = False

    def __iter__(self):
        for d in self._deltas:
            self.n_chunks += 1
            self.n_ids += len(d)
            yield d, _ids(d)
        self.finish = self._fin
        self.usage = self._usage

    def close(self):
        self.closed = True


class _FakeLog:
    def __init__(self):
        self.recs = []

    def w(self, rec):
        self.recs.append(rec)


def _args(no_probe=True):
    return argparse.Namespace(
        no_probe=no_probe, chunk_tokens=64, tail_tokens=1024,
        max_inject_per_step=1, base_url="http://fake", model="m",
        probe_url="http://fake", timeout=1, fire_nth_cut=0, nofill=False)


def _run(scripted, no_probe=True, score_fire=None, gen_call="apis.x.y()"):
    """scripted: [(deltas, finish, usage), ...], one entry per request.
    score_fire: which /score call fires (counting from 1); None = never."""
    streams, prompts = [], []
    it = iter(scripted)

    def fake_open(base_url, payload, timeout, retries=3):
        prompts.append(payload["prompt"])
        assert payload["stop"] == DEFAULT_STOP, payload["stop"]
        st = _FakeStream(*next(it))
        streams.append(st)
        return st

    calls = dict(n=0)

    def fake_http(url, payload, timeout=600, retries=3):
        if url.endswith("/score"):
            calls["n"] += 1
            return dict(fired=(calls["n"] == score_fire), conf=0.99, label="x")
        if url.endswith("/gen"):
            return dict(call=gen_call)
        if url.endswith("/decode"):
            return dict(text="".join(chr(i) for i in payload["ids"]))
        if url.endswith("/encode"):
            return dict(ids=_ids(payload["text"]))
        raise AssertionError(url)

    def fake_spec(world, call, t_frozen, dt_guard):
        return dict(exec_code=call, arg_modes=[], exec_out="RESULT",
                    exec_ok=True, error_kind=None)

    orig = (L.open_stream, L.http_json, L.speculate)
    L.open_stream, L.http_json, L.speculate = fake_open, fake_http, fake_spec
    try:
        log = _FakeLog()
        out = L.gen_step(_args(no_probe), PREFIX, "task", [], None,
                         "t0", False, log, 0)
    finally:
        L.open_stream, L.http_json, L.speculate = orig
    return out, streams, prompts, log


def test_loop_clean_single():
    """No firing: a single request decodes without interruption, same as chat; stop is always just <|return|>."""
    deltas = [ANALYSIS_HEAD, "think. ", "more.", "<|end|>",
              FINAL_HEAD, "Done. ```python\ny()\n```"]
    (t, c, usage, discard, n_inj, gen_ids, cons), streams, prompts, _ = _run(
        [(deltas, "stop", dict(prompt_tokens=10, completion_tokens=50))])
    assert usage["req"] == 1 and usage["gen_tok"] == 50, usage
    assert t == "think. more." and c == "Done. ```python\ny()\n```", (t, c)
    assert n_inj == 0 and discard["events"] == 0
    assert prompts == [PREFIX], prompts
    assert gen_ids == _ids("".join(deltas)) and cons is None


def test_loop_noprobe_never_scores():
    """The noprobe arm never calls /score at all (fake_http throws the moment it's called)."""
    deltas = [ANALYSIS_HEAD + "s1. s2. s3.", "<|end|>", FINAL_HEAD, "c"]
    (_, c, _, _, _, _, _), _, _, _ = _run(
        [(deltas, "stop", dict(prompt_tokens=1, completion_tokens=9))])
    assert c == "c"


def test_loop_fire_restart():
    """Firing: the stream is closed, head = the model's own ids up to the sentence-ending
    punctuation, NOTE is encoded separately and appended for resend; overflow is booked;
    a second continuation wraps it up."""
    head = "We need to inspect the venmo documentation."
    deltas1 = [ANALYSIS_HEAD, head + " Overrun text arrives in the same chunk."]
    deltas2 = ["Continue think.", "<|end|>", FINAL_HEAD, "```python\nz()\n```"]
    (t, c, usage, discard, n_inj, gen_ids, cons), streams, prompts, log = _run(
        [(deltas1, None, None),
         (deltas2, "stop", dict(prompt_tokens=30, completion_tokens=20))],
        no_probe=False, score_fire=1)
    assert n_inj == 1 and discard["events"] == 1
    assert discard["chars"] > 0 and discard["tokens"] > 0
    assert streams[0].closed, "firing must abort the first stream"
    assert usage["req"] == 2, usage
    # For an aborted stream, count gen tokens by the number of ids received (including overflow)
    assert usage["gen_tok"] == streams[0].n_ids + 20, usage
    # Resend prompt = prefix + the model's own ids up to "documentation." + NOTE's ids
    head_ids = _ids(ANALYSIS_HEAD + head)
    assert prompts[1][:len(PREFIX) + len(head_ids)] == PREFIX + head_ids
    note = "".join(chr(i) for i in prompts[1][len(PREFIX) + len(head_ids):])
    assert note.startswith("\n[SYSTEM NOTE") and "RESULT" in note, note
    assert "Overrun" not in note
    assert [r["type"] for r in log.recs] == ["spec", "resume"]
    assert log.recs[0]["head_tok"] == len(head_ids)
    assert c == "```python\nz()\n```", repr(c)
    assert "Continue think." in t and "RESULT" in t, repr(t)
    assert cons is True, cons


def test_loop_budget_exhaust():
    """finish=length (budget exhausted): accept whatever came in, send no further requests."""
    deltas = [ANALYSIS_HEAD + "endless thinking"]
    (t, c, usage, _, _, _, _), _, prompts, _ = _run(
        [(deltas, "length", dict(prompt_tokens=5, completion_tokens=8192))])
    assert usage["req"] == 1 and len(prompts) == 1
    assert t == "endless thinking" and c == "", (t, c)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}", flush=True)
    print(f"ALL PASS ({len(fns)} tests)")
