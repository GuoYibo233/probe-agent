"""Live-run injection-line driver (appworld venv, pure CPU). Method spec: METHOD.md (the old design doc was removed in the 08-02 cleanup)

Question this answers: does the probe firing in real time, injecting the predicted call's real execution
result into the thinking, still get **the whole task** right, and does it save tokens? This is the
task-level score that the replay line (single-step continuation) cannot give; the user approved it
2026-08-01. The eval never judges whether the prediction was correct: firing means executing, and
whatever comes back gets injected (errors too).

Within one step (design doc §2):
  1. Message history assembled the same way as the collection script (SYSTEM comes from rebuild, checked
     against the source at startup);
  2. The harmony prefix comes from the probe service (/render produces token ids, token-for-token
     identical to the chat endpoint's rendering; the appworld venv has no transformers/openai_harmony);
  3. Segmented generation: --chunk-tokens tokens per segment, sampling keys from the preset,
     stop=<|return|>;
  4. Each new sentence-level cut sends assemble(task, hist, thinking[:cut]) to /score,
     fires on the first crossing of θ (stops once MAX_BOUNDS cuts have been checked; see design doc
     §4.2 for the difference in criteria);
  5. On fire: /gen produces the whole call -> live world save_state -> requote -> execute ->
     truncate to 4000 -> load_state to restore -> _set_datetime() to refreeze -> time-guard assertion
     ([copied from exec_calls.replay_unit], with a finally fallback) -> the --format text spliced in
     at the cut (inject_format.py, 2026-09-12: `note`/`p1_*` inside the thinking, `p2_*` close the
     thinking and append a message from the prefetch sender), overflow text after the cut discarded
     (the discarded amount is recorded) -> continue segmented generation;
  6. Probing stops once <|end|> appears; the segment length is enlarged to --tail-tokens to finish the
     step; the final channel takes the code block, executes it in the live world, feeds the output back,
     and moves to the next step. Injects at most once per step by default.

Process and environment (design doc §3):
  **This file and exec_calls.py are the only two places in the whole pipeline that import appworld**,
  and can only run with envs/appworld/venv/bin/python; one process holds one world (AppWorld's
  close_all corrupts coexisting instances), so concurrency is via --num-shards multiple processes.

On disk: one live_{task_id}.jsonl per task, record types:
  meta  the task and all settings (θ/T/service endpoint/chunk size/probe config echoed back)
  gen   per-step aggregate: thinking/content/per-segment usage accumulated/discarded overflow chars and token count
  spec  each fire: cut, confidence, predicted call, requote branch, execution result (truncated to 4000),
        error kind, full injected line; v6 adds head_tok/dropped_chars/overflow_ids
  resume each resend-continuation wrap-up: match_len/identical between the new ids and the discarded ids (v6)
  env   the real code and execution output for each step (same format as the collection side)
  final steps/completed/eval (a structured dict, not stored as a str -- scoring needs to read it)

Usage (smoke test, 2 tasks from the val split; do not use the test set for debugging):
  envs/appworld/venv/bin/python pipeline/inject/live_appworld.py \\
      --base-url http://tokyo108:8103/v1 --probe-url http://tokyo108:8790 \\
      --split dev --n 2 --outdir pipeline/inject/runs/live_smoke \\
      --exp live_smoke
  Control arm (same path with the probe unattached, the live-run version of the replay line's nofill): add --no-probe
  probe but nofill arm (ident3, 2026-08-18; probe weights deleted, fake firing):
      add --fire-nth-cut 5 --nofill (interrupt at the 5th sentence-end cut, resend the head using the
      model's own token ids unchanged, inject nothing)

v6 (2026-08-18 ident3): the stream carries return_token_ids, gen records now also carry gen_ids (the
whole step's token ids); on firing, the resend prompt = prefix_ids + gen_ids[:k] (the cut backs off to a
token boundary, checked via /decode) + /encode(NOTE), no longer re-tokenizing the whole segment; spec
records overflow_ids (the ids discarded on interruption), and resume records the match_len/identical from
comparing the resent continuation against them position by position.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "annotate"))

import rebuild as R                                            # noqa: E402
from rules import MIN_THINK, SENT_RE, assemble                 # noqa: E402
from exec_calls import (APPWORLD_SEED, TRUNC, CKPT, error_kind,  # noqa: E402
                        requote)
from replay_inject import DEFAULT_STOP                         # noqa: E402
import inject_format as F                                      # noqa: E402

APPWORLD_HOME = "/home/y-guo/reproduce/new1/envs/appworld"
END_MARK = "<|end|>"
MAX_BOUNDS = 64            # same value as rules.MAX_BOUNDS: the live run checks at most this many cuts (§4.2)
MAX_STEP_TOKENS = 8192     # max_tokens=8192 at collection time (common.py:20), aligned with the per-step cap

# Fallback defaults merged by --preset. merge_client only handles keys that appear in cli∪fallbacks;
# a sampling key not in this table means the preset can set it and it silently has no effect
# (before 2026-08-21 that is exactly how top_p/seed got dropped); coverage is pinned by tests/test_preset.py.
PRESET_FB = {"reasoning_effort": "high",
             "max_tokens": MAX_STEP_TOKENS, "stop": DEFAULT_STOP,
             "top_p": None, "seed": None}

# v4 (2026-08-02): isomorphic to w0's chat-path logic. Three points of alignment:
# (1) No prefilled channel header -- the prompt stops at <|start|>assistant, the model writes its own
#     <|channel|>analysis<|message|>, byte-identical to the chat endpoint's rendering;
#     v5 (2026-08-18): the prompt is sent directly as token ids (/render produces the ids, copying the
#     chat endpoint's rendering), no longer letting the completions endpoint tokenize -- this removes
#     both the empty-content-turn and literal-<|...|>-marker discrepancies between chat/completions
#     (see harmony_render.py file header);
# (2) Streaming single-shot decoding -- one stream=true request per step, the server decodes without
#     interruption, only close()s to abort and resend when the probe actually fires (injection itself
#     must change the prompt, the seam cannot be avoided);
# (3) Stop recognizes only <|return|>; the message the model continues writing after final is folded
#     into content the same way vLLM's HarmonyParser does (same as chat, including the 1.3% fabricated
#     tail -- under message-level parsing it is clean prose; v1's poison was bare markers leaking into
#     the text, which does not happen here).


def parse_step(full):
    """Whole-step generated text -> (thinking, content). Splits channels the same way vLLM's HarmonyParser
    does (vllm/parser/harmony.py::_SegmentType + parse): analysis->thinking,
    final and commentary with no recipient->content, each joined across segments with \n.

    2026-08-02 diagnosis lesson: v2 and earlier took only final, silently dropping the whole action
    narration the model wrote on the commentary channel (step-0 measurement: w0 content carried prose in
    152/168, the live run only 4/168). The "self" fed back into history had long carried no prose, so the
    model stuffed its narrative urge into complete_task(answer=...) -- and for tasks that don't ask a
    question, the reference answer is null, so stuffing it in kills the task. content must align with
    chat character for character.

    full is the entire generated text after <|start|>assistant: the first message carries its own
    <|channel|>analysis<|message|> header (v4 does not prefill it); backward compatible with the old
    convention (the header is in the prompt, full starts directly with the body). <|return|> is the
    engine's stop token; if it appears in the text (a theoretical branch) everything from it onward is
    truncated -- the engine had already stopped there anyway."""
    full = full.split("<|return|>", 1)[0]
    reasoning, content = [], []
    for i, seg in enumerate(full.split(END_MARK)):
        if i == 0 and not seg.lstrip().startswith("<|channel|>"):
            ch, has_rcpt, body = "analysis", False, seg   # old convention: header is in the prompt
        else:
            hdr, sep, body = seg.partition("<|message|>")
            hdr = hdr.strip()
            # valid header = [<|start|>assistant[ to=x]]<|channel|>CH[junk];
            # non-assistant messages (fake user/system turns) or fragments are always dropped -- same as vLLM.
            if not sep or not (hdr.startswith("<|start|>assistant")
                               or hdr.startswith("<|channel|>")):
                continue
            m = re.match(r"\s*([a-z]+)", hdr.partition("<|channel|>")[2])
            ch = m.group(1) if m else ""
            has_rcpt = " to=" in hdr
        if ch == "analysis" and body:
            reasoning.append(body)
        elif (ch == "final" or (ch == "commentary" and not has_rcpt)) and body:
            content.append(body)
    return "\n".join(reasoning), "\n".join(content)


def think_span(raw):
    """The (start, end) of the analysis body within raw (the generated text after <|start|>assistant).
    Returns None if the header is incomplete or the first message is not analysis; end = len(raw) when the message is unclosed."""
    m = raw.find("<|message|>")
    if m < 0:
        return None
    hdr = raw[:m]
    if END_MARK in hdr or "analysis" not in hdr:
        return None
    end = raw.find(END_MARK, m)
    start = m + len("<|message|>")
    return (start, end if end >= 0 else len(raw))


def sent_starts(text):
    """Sentence-end cuts are listed by **start** (after the punctuation, before the whitespace, `m.start()`)
    -- the live run uses this.
    Under streaming, the sentence-end whitespace arrives in pieces: `. ` arrives first, `\\n` arrives
    later; recording by `m.end()` would count the same sentence end as two cuts in sequence (p and p+1),
    so "the Nth cut" would shift with chunking; the start does not move as later whitespace arrives, so
    the same sentence end is only ever counted once. The MIN_THINK//2 filter stays as before (length
    after strip, equivalent to the end-based criterion). The replay line's sent_cuts (by end) is left
    unchanged."""
    pts = sorted({m.start() for m in SENT_RE.finditer(text)})
    return [p for p in pts if len(text[:p].strip()) >= MIN_THINK // 2]


def sent_cuts(text):
    """Real sentence-level cuts (excludes the fake cut at the end of the full text).

    Difference from rules.boundaries (design doc §4.2): does not do MAX_BOUNDS evenly-spaced sampling --
    the sampled result changes as the text grows, which under a live run would invalidate the set of
    "already-probed cuts"; the cap is instead managed by the caller counting "times already probed".
    The MIN_THINK filter is copied as-is.
    """
    pts = sorted({m.end() for m in SENT_RE.finditer(text)})
    return [p for p in pts if len(text[:p].strip()) >= MIN_THINK // 2]


class Stream:
    """Streaming /v1/completions. Yields (text delta, token id delta); calling close() partway through
    aborts server-side decoding. The request carries return_token_ids=True (vLLM 0.26: each chunk's
    token_ids and text are deltas from the same decoding step, but the text can lag behind the ids
    when UTF-8 bytes are not yet complete, so both are handed out together per chunk and the caller
    records boundaries per chunk).
    After completion, finish/usage are readable (with include_usage; usage is None when aborted,
    and the caller counts gen tokens using the number of ids received)."""

    def __init__(self, base_url, payload, timeout):
        url = base_url.rstrip("/") + "/completions"
        body = json.dumps(dict(payload, stream=True, return_token_ids=True,
                               stream_options={"include_usage": True})).encode()
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"})
        self.resp = urllib.request.urlopen(req, timeout=timeout)
        self.finish = None
        self.stop_reason = None
        self.usage = None
        self.n_chunks = 0
        self.n_ids = 0

    def __iter__(self):
        for line in self.resp:
            if not line.startswith(b"data: "):
                continue
            data = line[6:].strip()
            if data == b"[DONE]":
                break
            ck = json.loads(data)
            if ck.get("usage"):
                self.usage = ck["usage"]
            for c in ck.get("choices") or []:
                if c.get("finish_reason"):
                    self.finish = c["finish_reason"]
                    self.stop_reason = c.get("stop_reason")
                text = c.get("text") or ""
                ids = c.get("token_ids") or []
                if text or ids:
                    self.n_chunks += 1
                    self.n_ids += len(ids)
                    yield text, ids
        self.close()

    def close(self):
        try:
            self.resp.close()
        except Exception:
            pass


def open_stream(base_url, payload, timeout, retries=3):
    for att in range(retries):
        try:
            return Stream(base_url, payload, timeout)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if att == retries - 1:
                raise
            print(f"    stream retry {att + 1}: {e}", flush=True)
            time.sleep(2 ** att)


def sample_extras(a):
    """top_p/seed only go into the request body when explicitly given (same convention as
    Chat._sample_extras in envs/collect/common.py): when not given, the request body is byte-identical
    to what it was before these two keys were added."""
    d = {}
    if getattr(a, "top_p", None) is not None:
        d["top_p"] = a.top_p
    if getattr(a, "seed", None) is not None:
        d["seed"] = a.seed
    return d


def gen_payload(a, prompt, max_tokens):
    """The request body for the main generation request. All the sampling keys from the preset's client
    section (temperature/top_p/max_tokens/stop/seed) land here, pinned by tests/test_preset.py."""
    return dict(model=a.model, prompt=prompt, max_tokens=max_tokens,
                temperature=a.temperature, stop=a.stop,
                skip_special_tokens=False, **sample_extras(a))


def http_json(url, payload, timeout=600, retries=3):
    body = json.dumps(payload, ensure_ascii=False).encode()
    for att in range(retries):
        try:
            req = urllib.request.Request(
                url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                out = json.loads(r.read())
            if isinstance(out, dict) and out.get("error"):
                raise RuntimeError(f"{url}: {out['error']}")
            return out
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if att == retries - 1:
                raise
            print(f"    retry {att + 1} {url}: {e}", flush=True)
            time.sleep(2 ** att)


class W:
    """One jsonl per task, flushed record by record (a killed process does not lose the run)."""

    def __init__(self, path, meta):
        self.f = open(path, "w")
        self.w(dict(type="meta", **meta))

    def w(self, rec):
        self.f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.f.flush()

    def close(self):
        self.f.close()


def speculate(world, gen_call, t_frozen, dt_guard):
    """On the live world: "save state -> execute the predicted call -> restore state -> refreeze time ->
    assert". [Copied from exec_calls.replay_unit's three-step sequence.] Returns the spec record fields."""
    code_x, modes = requote(gen_call, world.shell.user_ns)
    world.save_state(CKPT)
    try:
        eout = str(world.execute(code_x))[:TRUNC]
    finally:
        world.load_state(CKPT)
        world._set_datetime()
        if dt_guard:
            now = world.execute("print(DateTime.now())").strip()
            if now != t_frozen:
                raise RuntimeError(f"time drifted after the restore: {now!r} != {t_frozen!r}")
    ek = error_kind(eout)
    return dict(exec_code=code_x, arg_modes=modes, exec_out=eout,
                exec_ok=(ek is None), error_kind=ek)


def token_boundary(bounds, pos):
    """bounds = the (n_chars, n_ids) at the end of each stream chunk, n_chars monotonically non-decreasing;
    returns the last boundary (n_chars, n_ids) no later than character position pos. When the same
    n_chars has multiple boundaries (text lagging behind ids), takes the one with the fewest ids.
    Returns None if there is none.
    Only used as find_head's starting point: the stream text lags behind the ids (see find_head), so
    chunk boundaries are not exact."""
    best = None
    for c, k in bounds:
        if c > pos:
            break
        if best is None or c > best[0]:
            best = (c, k)
    return best


def find_head(gen_ids, raw, pos, k0, decode):
    """head = the shortest id prefix whose decoded text covers character position pos (the start of a
    sentence-end cut = right after the punctuation). Returns (k, head_text). In other words, up through
    "the token that contains the sentence-end punctuation": when `.` and ` Then` are separate tokens,
    head stops at `.`; when `.\\n\\n` is one token, head includes all of it.
    This rule only looks at the model's token sequence, not how the stream is chunked.

    Why this can't be computed from the chunk boundary (len(raw), len(gen_ids)): when vLLM has a stop
    string, it withholds the last len(stop)-1 characters (stop_buffer_length in
    v1/engine/detokenizer.py's get_next_output_text; <|return|> is 10 characters -> the text is always
    about 9 characters, roughly 2 tokens, behind the ids; smoke test measured decode(head_ids) producing
    an extra ' We have'), and it also withholds when multi-byte characters are not yet complete;
    several tokens get merged into one chunk when the producer runs faster than the consumer. So k must
    be verified with decode one at a time, and the chunk boundary k0 is only used as a starting point.
    decode is an HTTP call, usually only a few calls per fire.
    The part head_text shares with the stream text must match character for character (mismatch raises
    an error, never silently)."""
    if not gen_ids:
        raise RuntimeError("find_head: no generated ids yet")
    k = max(1, min(k0, len(gen_ids)))
    txt = decode(gen_ids[:k])
    while len(txt) < pos and k < len(gen_ids):          # advance forward until it covers pos
        k += 1
        txt = decode(gen_ids[:k])
    while k > 1:                                        # then back off to the shortest
        prev = decode(gen_ids[:k - 1])
        if len(prev) < pos:
            break
        k, txt = k - 1, prev
    if len(txt) < pos:
        raise RuntimeError(f"find_head: decoding all {len(gen_ids)} ids gives "
                           f"({len(txt)} chars), which does not cover the cut at {pos}")
    n = min(len(txt), len(raw))
    if txt[:n] != raw[:n]:
        raise RuntimeError(f"find_head: decode(ids[:{k}]) does not match the streamed text: "
                           f"{txt[max(0, n - 60):n]!r} vs {raw[max(0, n - 60):n]!r}")
    return k, txt


def ids_sha(ids):
    """sha1 of the token id list (comma-joined string); the chat arm stores the whole prompt_token_ids,
    the live-run arm only stores this -- if both sides compute the same sha on the scoring side, that
    is an id-for-id comparison."""
    return hashlib.sha1(",".join(map(str, ids)).encode()).hexdigest()


sep_for = F.sep_for        # the head seam rule lives in inject_format (single source since 2026-09-12)


def system_prompt(fmt):
    """The system message for a task: the collection SYSTEM, plus the format's paragraph when the
    format explains the prefetch mechanism there (e2 formats). Present from step 0 and re-rendered
    every step, so the no-probe control run with the same --format carries the same prompt."""
    return R.SYSTEM + F.system_extra(fmt)


def log_resume(log, step, pending, gen_ids, st):
    """Compares, position by position, the new ids from the resent continuation against the ids discarded
    at the last interruption (under nofill this is "can an id-identical resend reproduce the model's own
    continuation")."""
    new = gen_ids[pending["head_tok"] + pending["note_tok"]:]
    ov = pending["overflow_ids"]
    m = 0
    while m < min(len(new), len(ov)) and new[m] == ov[m]:
        m += 1
    log.w(dict(type="resume", step=step, overflow_tok=len(ov),
               new_tok=len(new), match_len=m,
               identical=(m == len(ov) and len(new) >= len(ov)),
               finish=st.finish, stop_reason=st.stop_reason))


def gen_step(a, prefix_ids, task, hist, world, t_frozen, dt_guard, log, step):
    """v4: one-shot streaming generation per step, isomorphic to w0's chat decoding.
    prefix_ids = the harmony prefix token ids, stopping at <|start|>assistant (no prefill);
    raw = all the generated text after that (the model writes its own channel header), gen_ids = the
    corresponding token ids (the stream carries return_token_ids, accumulated chunk by chunk; v6
    2026-08-18 ident3).
    When sending the request, prompt = prefix_ids + gen_ids: on a step that does not fire, prompt is
    exactly the id string the chat endpoint would feed the engine; after firing, the resent head is also
    the model's own generated ids unchanged (the cut backs off to a token boundary no later than it,
    checked via /decode before resending), with NOTE appended via its own /encode -- the text is no
    longer re-tokenized as a whole, so the only re-tokenization seam left is NOTE itself.
    Probing rides on the stream: scoring happens as soon as a new sentence cut appears (the real probe's
    /score; or fake firing via --fire-nth-cut: fires at the Nth cut), and only firing triggers close() to
    interrupt (with --nofill, nothing gets injected) and a resend continuation -- a step that does not
    fire is a single request decoded without interruption, exactly the same as chat.
    Each interruption stores the ids generated after the cut and then discarded into the spec record
    (overflow_ids); the new ids from the resend continuation are compared to them position by position,
    writing a resume record (match_len/identical).
    Returns (thinking, content, aggregated usage, overflow account, fire count, gen_ids)."""
    raw = ""
    gen_ids = []
    bounds = [(0, 0)]          # (len(raw), len(gen_ids)) at the end of each chunk
    usage = dict(prompt_tok=0, gen_tok=0, req=0)
    discard = dict(chars=0, tokens=0, events=0)
    checked = set()            # already-probed cuts (thinking coordinates)
    n_checked = 0
    n_inject = 0
    probing = not a.no_probe
    accepted = 0               # thinking length before the injection point (do not re-probe after restart)
    pending = None             # ids discarded at the last interruption, compared position by position once the resend continuation comes back

    while True:
        # prompt is always token ids: the prefix comes from /render (same rendering as chat); gen_ids are
        # the ids the model generated itself (after firing = head_ids + NOTE's ids)
        prompt = list(prefix_ids) + list(gen_ids)
        # the step budget is counted by the ids **kept** (in chat, all 8192 of a step's ids are kept; the
        # overflow discarded on interruption only counts against usage, not the budget -- otherwise nofill
        # steps would hit the length cap earlier than the other arms)
        st = open_stream(a.base_url, gen_payload(
            a, prompt, max(1, a.max_step_tokens - len(gen_ids))), a.timeout)
        usage["req"] += 1
        fired = False
        for delta, ids in st:
            raw += delta
            gen_ids += ids
            bounds.append((len(raw), len(gen_ids)))
            if not probing or n_inject >= a.max_inject_per_step:
                continue
            if not any(c in delta for c in ".!?\n"):
                continue           # no need to rescan without a new sentence end (tokens arrive one by one in the stream)
            span = think_span(raw)
            if span is None:
                continue           # the channel header is not fully written yet
            ts, te = span
            if te < len(raw):
                probing = False    # analysis has closed, moving into commentary/final
                continue
            t_all = raw[ts:]
            for cut in sent_starts(t_all):
                if cut in checked or cut <= accepted:
                    continue
                if n_checked >= MAX_BOUNDS:
                    probing = False
                    break
                checked.add(cut)
                n_checked += 1
                if a.fire_nth_cut:
                    # fake firing (probe weights deleted): fires at the Nth cut, does not call /score /gen
                    s = dict(conf=None, label=None,
                             fired=(n_checked == a.fire_nth_cut))
                else:
                    s = http_json(a.probe_url + "/score",
                                  dict(text=assemble(task, hist, t_all[:cut])))
                if not s["fired"]:
                    continue
                # ---- fire: head = the shortest id prefix covering the sentence-end punctuation (the model's own ids)----
                pos = ts + cut                          # raw coordinates (after the punctuation)
                _, k0 = token_boundary(bounds, pos)
                k, head_txt = find_head(
                    gen_ids, raw, pos, k0,
                    lambda ids: http_json(a.probe_url + "/decode",
                                          dict(ids=ids))["text"])
                head_ids = gen_ids[:k]
                overflow_ids = gen_ids[k:]
                if a.nofill:
                    g, note = None, ""
                    spec = dict(exec_code=None, arg_modes=None, exec_out=None,
                                exec_ok=None, error_kind=None)
                else:
                    g = http_json(a.probe_url + "/gen",
                                  dict(text=assemble(task, hist, t_all[:cut])))
                    spec = speculate(world, g["call"], t_frozen, dt_guard)
                    note = F.splice_text(a.format, head_txt, g["call"],
                                         spec["exec_out"])
                # `after` formats close the thinking and append a prefetch message: their text
                # carries control markers and is encoded with special=True; `think` formats are
                # encoded as plain text, so a marker inside a result stays text (R2)
                note_ids = (http_json(a.probe_url + "/encode",
                                      dict(text=note,
                                           special=F.needs_special(a.format)))["ids"]
                            if note else [])
                discard["chars"] += max(0, len(raw) - len(head_txt))
                discard["tokens"] += len(overflow_ids)
                discard["events"] += 1
                log.w(dict(type="spec", step=step, cut=cut,
                           n_checked=n_checked, conf=s["conf"],
                           pred_label=s["label"],
                           gen_call=g["call"] if g else None,
                           note=note, nofill=bool(a.nofill),
                           discarded_chars=max(0, len(raw) - len(head_txt)),
                           head_chars=len(head_txt) - ts,
                           head_ends_ws=head_txt[-1:].isspace(),
                           head_tok=k, note_tok=len(note_ids),
                           head_tail=head_txt[-40:],
                           n_chunks=st.n_chunks,
                           overflow_ids=overflow_ids, **spec))
                if pending is not None:     # synchronize a second fire: settle last time's account first
                    log_resume(log, step, pending, gen_ids, st)
                raw = head_txt + note        # text is taken from decode(head), overflow discarded
                gen_ids = head_ids + note_ids
                bounds = [(len(raw), len(gen_ids))]
                pending = dict(head_tok=k, note_tok=len(note_ids),
                               overflow_ids=overflow_ids)
                accepted = (len(head_txt) - ts) + len(note)
                checked = set()                # offsets shift as a whole, the old set is invalidated
                n_inject += 1
                fired = True
                break
            if fired:
                break
        # accounting: usage is available on a clean finish; when aborted, use the id count received on this
        # request (including the discarded overflow)
        if st.usage:
            usage["prompt_tok"] += st.usage.get("prompt_tokens", 0)
            usage["gen_tok"] += st.usage.get("completion_tokens", 0)
        else:
            usage["gen_tok"] += st.n_ids
        if pending is not None and not fired:
            log_resume(log, step, pending, gen_ids, st)
            pending = None
        if fired:
            st.close()
            continue               # continuation after firing (head is the model's own ids)
        break                      # stop=<|return|> or the budget is exhausted, the step wraps up

    # wrap-up check: text and ids must line up (decode(gen_ids) = raw + the stop token's text, or = raw).
    # If not, print a warning and record text_ids_consistent=False in the gen record so the scoring side
    # can see it; do not raise here -- the whole task's score must not be voided by a record-consistency
    # check failing.
    consistent = None
    if n_inject:
        full = http_json(a.probe_url + "/decode", dict(ids=gen_ids))["text"]
        consistent = full.startswith(raw) and \
            full[len(raw):] in ("", "<|return|>", "<|call|>")
        if not consistent:
            print(f"    WARN step {step}: decode(gen_ids) does not match raw "
                  f"(len {len(full)} vs {len(raw)})", flush=True)
    t_final, content = parse_step(raw)
    return (t_final, content, usage, discard, n_inject, gen_ids, consistent)


def probe_cfg_problem(cfg, need_decode=False, need_special=False):
    """If the /health echo doesn't match expectations, gives one reason to refuse the run; returns None if
    it matches. An old service's /render produces jinja text, which diverges from the chat endpoint in
    two places (see harmony_render.py file header); lesson: an old 8790 once silently dropped the effort
    field and rendered at high -- pointing at the wrong service doesn't error, it just produces wrong
    numbers."""
    if cfg.get("render") != "harmony_ids":
        return (f"probe service /health did not return render=harmony_ids (got "
                f"{cfg.get('render')!r}), this is an old probe_server, refuse to run")
    if need_decode and not cfg.get("decode"):
        return ("probe service /health did not return decode=true: firing and resending needs /decode to check "
                "head_ids (2026-08-18 ident3), this is an old probe_server, refuse to run")
    if need_special and not cfg.get("encode_special"):
        return ("probe service /health did not return encode_special=true: an `after` format (p2_*) needs "
                "/encode to recognise control markers (2026-09-12), this is an old probe_server, refuse to run")
    return None


def claim(outdir, tid):
    """Claim a ticket via mkdir (atomic on NFS). Whoever creates it runs it, losers skip silently.

    A ticket stub only lingers when a worker dies hard (without even writing a task_error final), so
    the launch script wipes .claims/ entirely before every start -- any task without a final gets
    reclaimed.
    """
    d = outdir / ".claims"
    d.mkdir(exist_ok=True)
    try:
        (d / tid).mkdir()
        return True
    except FileExistsError:
        return False


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base-url", required=True, help="vLLM /v1 endpoint")
    ap.add_argument("--probe-url", required=True, help="probe_server endpoint")
    ap.add_argument("--model", default=None,
                    help="default gpt-oss-120b (when the preset gives none either)")
    ap.add_argument("--split", default="test_normal")
    ap.add_argument("--n", type=int, default=0, help="0 = the whole split")
    ap.add_argument("--task-ids", default="",
                    help="comma-separated, name only these tasks to run (for smoke test verification); "
                         "takes effect before --n and piece/task-claiming")
    ap.add_argument("--max-steps", type=int, default=20)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--exp", required=True, help="appworld experiment_name prefix")
    ap.add_argument("--chunk-tokens", type=int, default=64)
    ap.add_argument("--tail-tokens", type=int, default=1024,
                    help="segment length after <|end|> (or when no probe is attached)")
    ap.add_argument("--max-inject-per-step", type=int, default=1)
    ap.add_argument("--preset", default="default",
                    help="a set of generation settings from configs/presets/<name>.json"
                         "(effort/temperature/top_p/step budget/stop/seed);"
                         "default is default; parameters given explicitly on the command line override the preset")
    ap.add_argument("--effort", default=None,
                    choices=["high", "medium", "low"],
                    help="the harmony template's Reasoning level; default high (when the preset gives none either). "
                         "collection settings = high, the effort control arm passes low/medium")
    ap.add_argument("--no-probe", action="store_true",
                    help="control arm: the same segmented generation path, no probe attached, no injection")
    ap.add_argument("--fire-nth-cut", type=int, default=0,
                    help="fake trigger (used when probe weights have been deleted): fire once at the Nth sentence-end cut "
                         "of each step, do not call /score; 0 = use the real probe's /score")
    ap.add_argument("--nofill", action="store_true",
                    help="when firing, insert nothing at all (no /gen, no speculative execution, no NOTE written), "
                         "only interrupt and refire the continuation using the model's own token ids")
    ap.add_argument("--format", default="note", choices=sorted(F.FORMATS),
                    help="injection format (inject_format.py; METHOD.md axis 5): note = the text used "
                         "before 2026-09-12; p1_* append inside the thinking, p2_* close the thinking and "
                         "append a message from the prefetch sender; *_e1 explain inline, *_e2 explain once "
                         "in the system prompt. --no-probe with an *_e2 format carries the same system "
                         "paragraph and injects nothing (the control for that format)")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--shard-id", type=int, default=0)
    ap.add_argument("--num-shards", type=int, default=1)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--pool", action="store_true",
                    help="dynamic task claiming: once a worker finishes a task, it claims the next one from the full "
                         "task list (mkdir as an atomic ticket); slow tasks no longer block a static piece; --shard-id degrades to a worker number")
    ap.add_argument("--keep-outputs", action="store_true",
                    help="keep each task's appworld output dir (deleted right after finishing by default, a lesson from quota limits)")
    ap.add_argument("--selftest-shadow", metavar="TRAJ",
                    help="connect to no service: replay the first several steps of this already-collected trajectory, do a"
                         "save/execute/restore three-step combo once, then keep replaying and check character by"
                         "character -- to prove speculative execution does not pollute the live world.")
    a = ap.parse_args()
    if a.no_probe and (a.fire_nth_cut or a.nofill):
        ap.error("--no-probe is mutually exclusive with --fire-nth-cut/--nofill (the no-probe arm does not fire)")

    # --preset merge (explicit CLI value > preset's client section > original default), the expanded
    # values are hung back onto a; downstream only reads a.*; --preset defaults to default, and the
    # temperature key comes only from the preset file
    root = str(Path(__file__).resolve().parents[2])
    if root not in sys.path:
        sys.path.append(root)
    from preset_loader import load_preset, merge_client, require_temperature
    pre = load_preset(a.preset)
    eff = merge_client(
        {"reasoning_effort": a.effort,
         "temperature": getattr(a, "temperature", None)},
        pre.get("client"),
        PRESET_FB)
    a.effort = eff["reasoning_effort"]
    a.temperature = require_temperature(eff["temperature"], pre["_name"])
    a.max_step_tokens = eff["max_tokens"]
    a.stop = eff["stop"]
    a.top_p = eff["top_p"]
    a.seed = eff["seed"]
    a.model = (a.model
               or (pre.get("server") or {}).get("served_model_name")
               or "gpt-oss-120b")

    # always resolve paths before chdir [same lesson as exec_calls.py]
    outdir = Path(a.outdir).resolve()
    shadow_traj = Path(a.selftest_shadow).resolve() if a.selftest_shadow \
        else None
    outdir.mkdir(parents=True, exist_ok=True)
    R.check_system_verbatim()
    os.chdir(APPWORLD_HOME)
    from appworld import AppWorld, load_task_ids

    if shadow_traj:
        return selftest_shadow(AppWorld, shadow_traj, a)

    # both arms need /render (the appworld venv has no transformers), the service must be up
    with urllib.request.urlopen(a.probe_url + "/health", timeout=30) as r:
        probe_cfg = json.loads(r.read())
    print(f"probe: {probe_cfg}", flush=True)
    bad = probe_cfg_problem(probe_cfg, need_decode=not a.no_probe,
                            need_special=(not a.no_probe and not a.nofill
                                          and F.needs_special(a.format)))
    if bad:
        sys.exit(bad)

    ids = load_task_ids(a.split)
    if a.task_ids:
        want = [t.strip() for t in a.task_ids.split(",") if t.strip()]
        missing = sorted(set(want) - set(ids))
        if missing:
            sys.exit(f"--task-ids has {len(missing)} tasks not in split "
                     f"{a.split}: {missing}")
        ids = want
    if a.n:
        ids = ids[: a.n]
    if a.pool:
        # dynamic task claiming: no slicing, all workers contend for the same full list; workers start
        # staggered by worker number, so lock contention only happens near the tail. Lesson from static
        # sharding: one slow task blocks its whole shard, and finishing the other shards can't help --
        # the whole tail is stuck waiting on it.
        ids = ids[a.shard_id:] + ids[: a.shard_id]
    else:
        ids = ids[a.shard_id:: a.num_shards]
    exp = a.exp if a.num_shards == 1 else f"{a.exp}_s{a.shard_id}"
    print(f"shard {a.shard_id}/{a.num_shards}: {len(ids)} tasks exp={exp} "
          f"pool={a.pool}", flush=True)

    for tid in ids:
        out_path = outdir / f"live_{tid}.jsonl"
        if a.resume and out_path.exists() and \
                '"type": "final"' in out_path.read_text():
            if not a.pool:              # pool mode has all 12 workers each sweep through once, too noisy
                print(f"task={tid} SKIP (done)", flush=True)
            continue
        if a.pool and not claim(outdir, tid):
            continue
        try:
            run_task(AppWorld, tid, exp, out_path, a, probe_cfg)
        except Exception as e:
            # one task crashing must not take the whole shard down with it: write a failed final (resume won't
            # collide with it again), print and move on to the next task. Lesson: on the first run a 400 went
            # unhandled and wiped out 5 of 24 shards.
            with open(out_path, "a") as f:
                f.write(json.dumps(dict(
                    type="final", steps=-1, completed=False,
                    abort=f"task_error:{type(e).__name__}",
                    eval=dict(success=False,
                              task_error=str(e)[:300])), ensure_ascii=False)
                    + "\n")
            print(f"task={tid} TASK_ERROR {type(e).__name__}: {str(e)[:200]}",
                  flush=True)
        if not a.keep_outputs:             # appworld is ~90KB per task, a quota lesson
            shutil.rmtree(Path("experiments/outputs") / exp / "tasks" / tid,
                          ignore_errors=True)


def run_task(AppWorld, tid, exp, out_path, a, probe_cfg):
    with AppWorld(task_id=tid, experiment_name=exp,
                  random_seed=APPWORLD_SEED) as world:
        instr = world.task.instruction
        log = W(out_path, dict(
            env="appworld", task_id=tid, model=a.model, instruction=instr,
            arm=("no_probe" if a.no_probe else
                 "probe_nofill" if a.nofill else "probe"),
            fire=(f"nth_cut:{a.fire_nth_cut}" if a.fire_nth_cut else "probe"),
            nofill=bool(a.nofill), token_exact_resend=True, format=a.format,
            effort=a.effort, probe=probe_cfg, preset=a.preset,
            gen_settings=dict(temperature=a.temperature,
                              max_step_tokens=a.max_step_tokens,
                              stop=a.stop, top_p=a.top_p, seed=a.seed),
            chunk_tokens=a.chunk_tokens, tail_tokens=a.tail_tokens,
            max_inject_per_step=a.max_inject_per_step,
            appworld_seed=APPWORLD_SEED, date=time.strftime("%Y-%m-%d")))
        # time-guard baseline [copied from exec_calls]: the moment frozen at the start
        t_frozen = world.execute("print(DateTime.now())").strip()
        dt_guard = not t_frozen.startswith("Execution failed")

        msgs = [{"role": "system", "content": system_prompt(a.format)},
                {"role": "user",
                 "content": f"Task from supervisor: {instr}"}]
        hist = []                          # the (action, result) history fed to the probe
        completed, step, abort = False, -1, None
        try:
            for step in range(a.max_steps):
                prefix_ids = http_json(a.probe_url + "/render",
                                       dict(messages=msgs,
                                            effort=a.effort))["prefix_ids"]
                t0 = time.time()
                # v4: does not prefill the channel header, prompt stops at <|start|>assistant (same as chat)
                (think, content, usage, discard, n_inj, gen_ids,
                 consistent) = gen_step(a, prefix_ids, instr, hist, world,
                                        t_frozen, dt_guard, log, step)
                # the prefix is not stored whole (tens of thousands of ids per step); store sha1 + length instead;
                # the chat arm stores the whole prompt_token_ids, so comparing sha on the scoring side is an
                # id-for-id comparison
                log.w(dict(type="gen", step=step, reasoning=think,
                           content=content, usage=usage, discard=discard,
                           n_inject=n_inj, wall_s=round(time.time() - t0, 2),
                           prefix_tok=len(prefix_ids), prefix_sha=ids_sha(prefix_ids),
                           text_ids_consistent=consistent, gen_ids=gen_ids))
                msgs.append({"role": "assistant", "content": content})
                m = re.search(r"```python\s*(.*?)```", content, re.S)
                if not m:
                    log.w(dict(type="env", step=step, action=None,
                               result="NO_CODE_BLOCK"))
                    msgs.append({"role": "user", "content": R.NO_CODE_MSG})
                    continue
                code = m.group(1)
                out = str(world.execute(code))
                log.w(dict(type="env", step=step, action=code,
                           result=out[:TRUNC]))
                msgs.append({"role": "user",
                             "content": f"Execution output:\n{out[:TRUNC]}"})
                hist.append((code.strip(), out[:TRUNC]))
                if world.task_completed():
                    completed = True
                    break
        except urllib.error.HTTPError as e:
            # vLLM 400 = the prompt has hit the 65536 context limit, not even one chunk fits,
            # this task cannot continue. The world is still open: evaluate as usual, record the failure honestly.
            # Both arms abort under the same rule, so the criteria stay symmetric; a non-400 is still re-raised
            if e.code != 400:
                raise
            abort = "context_overflow_400"
        try:
            ev = world.evaluate()
            ev = ev.to_dict() if hasattr(ev, "to_dict") else ev
            if not isinstance(ev, dict):
                ev = dict(repr=str(ev)[:600])
        except Exception as e:
            ev = dict(eval_error=str(e)[:600])
        log.w(dict(type="final", steps=step + 1, completed=completed,
                   abort=abort, eval=ev))
        log.close()
        print(f"task={tid} steps={step + 1} completed={completed} "
              f"eval={json.dumps(ev, ensure_ascii=False)[:120]}", flush=True)


def selftest_shadow(AppWorld, traj_path, a):
    """A no-service self-check of the speculative-execution three-step: replay the first K steps of an
    already-collected trajectory -> run the three-step once -> continue replaying, comparing each step's
    output against the result recorded in the trajectory character for character. If state restore isn't
    clean, later steps drift immediately."""
    from exec_calls import load_steps
    steps = load_steps(traj_path)
    if len(steps) < 3:
        print(f"the trajectory has only {len(steps)} steps, switch to a longer one")
        return 1
    k = min(2, len(steps) - 1)
    tid = json.loads(open(traj_path).readline())["task_id"]
    probe_call = "apis.api_docs.show_app_descriptions()"
    with AppWorld(task_id=tid, experiment_name=f"{a.exp}_shadowtest",
                  random_seed=APPWORLD_SEED) as world:
        t_frozen = world.execute("print(DateTime.now())").strip()
        dt_guard = not t_frozen.startswith("Execution failed")
        bad = 0
        for i, (st, code, recorded) in enumerate(steps):
            if i == k:
                spec = speculate(world, probe_call, t_frozen, dt_guard)
                print(f"[combo@step{st}] exec_ok={spec['exec_ok']} "
                      f"out={spec['exec_out'][:80]!r}", flush=True)
            got = str(world.execute(code))[:TRUNC]
            same = got == recorded
            bad += 0 if same else 1
            print(f"step{st} {'OK' if same else 'DRIFT'}", flush=True)
            if not same:
                print(f"  want={recorded[:100]!r}\n  got ={got[:100]!r}")
    print(f"selftest-shadow: {'PASS' if bad == 0 else f'FAIL({bad} steps drifted)'}",
          flush=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main() or 0)
