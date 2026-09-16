"""Splice-method replay: when the probe fires, **how the prefetched result gets spliced
back in** -- which method makes the model think less and just move on.
Plan: plans/archive/2026-08-18-splice-replay.md (arms, cuts, metrics, and decision
points D1-D12 are all there).

God's-eye view: take a chat baseline trajectory, cut it at four proportional
positions in the thinking for each step, splice the step's code block's real
execution output in using ten splice methods, and have gpt-oss-120b continue writing
for one step. This measures single-step behavior only -- it does not judge whether
the prediction is right, does not run to completion, and does not evaluate. The probe
weights have been deleted; this line does not need a probe.

Three stages, each writing its own output to disk (run under cprobe-env; depends only
on openai_harmony + the standard library):
  events  trajectory -> events.jsonl (per event: CALL/CODE/RESULT/four cuts/baseline tokens)
  run     event x cut x arm sends /v1/completions (prompt is token ids) -> raw.jsonl
  score   parse -> per_row.jsonl + SPLICE_REPORT.{json,md}

  cprobe-env/bin/python pipeline/inject/splice_replay.py events \\
      --traj-root <chat trajectory dir> --out <run dir>
  cprobe-env/bin/python pipeline/inject/splice_replay.py run \\
      --run-dir <run dir> --base-url http://tokyo108:8103/v1 --model gpt-oss-120b \\
      [--arms ...] [--dry-run] [--limit N]
  cprobe-env/bin/python pipeline/inject/splice_replay.py score --run-dir <run dir>

The prompt is entirely token ids: the prefix = harmony_render.render_ids (same as the
chat endpoint); text arms follow with encode(<|channel|>analysis<|message|> + head +
splice string); p3k/p4 have the whole segment rendered by openai_harmony (bytes are
never hand-assembled). encode uses harmony's own o200k_harmony, the same vocabulary as
the gpt-oss HF tokenizer (verified 2026-08-18: the same string produces identical ids
one by one).
"""

import argparse
import hashlib
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "annotate"))

import rebuild as R                                             # noqa: E402
import harmony_render as H                                      # noqa: E402
from rules import MIN_THINK, SENT_RE                            # noqa: E402
from parse_call import complete_call, CALL_START                # noqa: E402
from replay_inject import PERMIT, SWITCH, DEFAULT_STOP, CODE_RE  # noqa: E402
from live_appworld import parse_step, sent_cuts                 # noqa: E402

A_OPEN = "<|channel|>analysis<|message|>"
CALL_MARK = "<|call|>"
CALL_ID = 200012                # <|call|>'s token id: one of the model's generation_config eos ids,
                                # vLLM folds it into stop_token_ids by default; when generation stops on it,
                                # stop_reason is this int (not a string), and every arm stops here (D11)
FRACS = [0.66, 0.75, 0.80, 1.00]
MAX_STEP_TOKENS = 8192          # whole-step cap at collection time (envs/collect/common.py:48)

# Wording (axis two). n0 follows the bracket form of replay_inject.NOTE_TMPL (the
# status-quo anchor, splices in the call CALL -- for 12/52 events the code block isn't
# a bare print(CALL), RESULT is the whole stdout block, so this wording isn't fully
# accurate for them; the report breaks it down by code_is_print_call); n1/n2 splice in
# the code block's original text CODE, which is accurate for every one of them
# (D3'/D13); n2 copies the form of the user message the model sees each turn
def note_body(kind, call, code, result):
    if kind == "n0":
        return f"[SYSTEM NOTE: prefetched {call} = {result}]"
    if kind == "n1":
        return f"I already ran:\n{code}\nand got:\n{result}"
    if kind == "n2":
        return f"```python\n{code}\n```\nExecution output:\n{result}"
    if kind == "n3":
        return result
    raise ValueError(kind)


# Arm table: (position, wording, whether PERMIT is added). Positions: p1=continue
# writing inside thinking p2=splice then force-cut to the body
# p3k=fake a whole turn that keeps thinking p4=harmony's native python tool
ARMS = {
    "nofill": ("p1", None, False),
    "p1_n0": ("p1", "n0", False),
    "p1_n1": ("p1", "n1", False),
    "p1_n2": ("p1", "n2", False),
    "p1_n3": ("p1", "n3", False),
    "p1_n0p": ("p1", "n0", True),
    "p2_n0": ("p2", "n0", False),
    "p2_n1": ("p2", "n1", False),
    "p3k": ("p3k", None, False),
    "p4": ("p4", None, False),
}
ARMS_ALL = list(ARMS)


def enc(text):
    return list(H.encoding().encode(text, allowed_special="all"))


def enc_plain(text):
    """Encode text that **must not contain control markers** (head / NOTE / RESULT / CODE).
    If a literal <|end|> or similar sneaks into the text, allowed_special="all" would
    turn it into a real special token and silently wreck the prompt (the kind of
    accident described at the top of harmony_render), so this rejects it outright."""
    ids = enc(text)
    e = H.encoding()
    bad = [i for i in ids if e.is_special_token(i)]
    if bad:
        raise ValueError(f"the text has literal control markers {[H.decode([i]) for i in bad]},"
                         "splicing into the prompt would turn them into real special tokens")
    return ids


def sep_for(head):
    """Seam-mending method (D5/D5'): if head ends in whitespace (true of the 66/75/80
    cuts, after the sentence-final whitespace), don't add a leading newline; splice
    NOTE directly after the whitespace -- `.\\n\\n`+`\\n[` would merge into `.\\n\\n\\n`
    and replace the model's own last token; `. `+`\\n[` keeps the `.` but adds an
    extra ` \\n` oddball token; `.\\n\\n`+`[S` and `. `+`[S` (inline) are both clean,
    `.` stays as-is. Only add `\\n` to start a new line when head has no trailing
    whitespace (the 100% cut)."""
    return "" if head[-1:].isspace() else "\n"


# ---------------------------------------------------------------- events

def cut_points(think, fracs=FRACS):
    """Fraction -> cut. For a fraction < 1, take the nearest sentence end before that
    character position (same as sent_cuts); 1.0 takes the end of the whole text.
    Fractions landing on the same cut are merged. Returns [(cut, [fracs])], sorted by
    cut ascending."""
    cuts = sent_cuts(think)
    got = {}
    for f in fracs:
        if f >= 1.0:
            c = len(think)
        else:
            pos = int(round(len(think) * f))
            cand = [c for c in cuts if c <= pos]
            if not cand:
                continue                    # no valid sentence end before this fraction: this fraction has no event
            c = cand[-1]
        got.setdefault(c, []).append(f)
    return sorted(got.items())


def cmd_events(a):
    root, out = Path(a.traj_root), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    R.check_system_verbatim()
    fracs = [float(x) for x in a.fracs.split(",")]
    seen, evs = set(), []
    stat = dict(steps=0, no_code=0, not_one_call=0, short_think=0, dup=0,
                kept=0, baseline_capped=0, code_is_print_call=0)
    for f in sorted(root.glob("appworld_*.jsonl")):
        meta, gens, envs, _ = R.load_traj(f)
        tid = meta["task_id"]
        for st in sorted(gens):
            stat["steps"] += 1
            g, e = gens[st], envs.get(st)
            if e is None or e.get("action") is None:
                stat["no_code"] += 1
                continue
            m = CODE_RE.search(g.get("content") or "")
            if not m:
                stat["no_code"] += 1
                continue
            code = m.group(1).strip()
            if len(CALL_START.findall(code)) != 1:
                stat["not_one_call"] += 1        # D1: skip both multi-call blocks and no-call blocks
                continue
            think = (g.get("reasoning") or "").strip()
            if len(think) < MIN_THINK:
                stat["short_think"] += 1
                continue
            call, _ = complete_call(code)
            if call is None:
                stat["not_one_call"] += 1      # parens don't balance, treat the call as unextractable
                continue
            msgs = R.build_messages(meta, gens, envs, st)
            key = hashlib.sha1(json.dumps([msgs, think]).encode()).hexdigest()
            if key in seen:
                stat["dup"] += 1
                continue
            seen.add(key)
            cps = cut_points(think, fracs)      # if 1.0 is in fracs it's guaranteed non-empty
            nxt = gens.get(st + 1)
            nm = CODE_RE.search((nxt or {}).get("content") or "")
            nt = CALL_START.search(nm.group(1)) if nm else None
            next_call = complete_call(nm.group(1))[0] if nm else None
            cm = CALL_START.match(call)
            base = (g.get("usage") or {}).get("out")
            # D12: for steps that hit max_tokens=8192 at collection time, the baseline out count
            # is truncated, so the token-savings accounting is unfair to them; flag them and look
            # at them separately in score
            capped = base is not None and base >= MAX_STEP_TOKENS
            stat["baseline_capped"] += int(capped)
            stat["code_is_print_call"] += int(code == f"print({call})")
            evs.append(dict(
                event=f"{tid}_s{st}", traj_path=str(f), task_id=tid, step=st,
                think_chars=len(think), call=call,
                call_tool=f"apis.{cm.group(1)}.{cm.group(2)}",
                code=code, result=e["result"],
                baseline_out_tok=base, baseline_capped=capped,
                next_tool=(f"apis.{nt.group(1)}.{nt.group(2)}" if nt else None),
                next_call=next_call,
                # n0's wording isn't fully accurate for blocks other than a bare "print(CALL)"; the report breaks this down
                code_is_print_call=(code == f"print({call})"),
                cuts=[dict(cut=c, fracs=fs) for c, fs in cps]))
            stat["kept"] += 1
    with open(out / "events.jsonl", "w") as w:
        for ev in evs:
            w.write(json.dumps(ev, ensure_ascii=False) + "\n")
    cfg = dict(traj_root=str(root), fracs=fracs, stat=stat,
               n_events=len(evs), n_cuts=sum(len(e["cuts"]) for e in evs),
               date=time.strftime("%Y-%m-%d"), arms=ARMS_ALL)
    (out / "events_config.json").write_text(json.dumps(cfg, indent=1,
                                                       ensure_ascii=False))
    print(json.dumps(cfg, ensure_ascii=False))


# ---------------------------------------------------------------- prompt

def prefix_messages(ev, permit=False):
    """The chat messages before this step (assembled the way run_appworld does it). permit adds a heads-up sentence at the end of system."""
    meta, gens, envs, _ = R.load_traj(Path(ev["traj_path"]))
    msgs = R.build_messages(meta, gens, envs, ev["step"])
    if permit:
        msgs = [dict(m) for m in msgs]
        msgs[0]["content"] = msgs[0]["content"] + PERMIT
    return msgs, gens


def build_prompt(arm, ev, head, msgs, content):
    """Returns (prompt_ids, prefix_len, splice_text).
    prefix_len = the token count of the prefix (ending at <|start|>assistant); everything
    after counts as this turn's bytes;
    splice_text = the spliced-in segment that the model did not write itself (for
    accounting + eyeballing)."""
    where, kind, _ = ARMS[arm]
    prefix = H.render_ids(msgs, effort="high", start_date=R.COLLECT_DATE)
    if where == "p1":
        if kind is None:
            splice = ""
        else:
            splice = sep_for(head) + note_body(kind, ev["call"], ev["code"],
                                               ev["result"]) + "\n"
        # Control markers and body text are encoded separately (special tokens are already
        # tokenizer boundaries, so encoding separately gives identical ids to encoding the
        # whole string at once); the body text goes through enc_plain, which rejects literal
        # control markers
        return prefix + enc(A_OPEN) + enc_plain(head + splice), len(prefix), splice
    if where == "p2":
        note = sep_for(head) + note_body(kind, ev["call"], ev["code"], ev["result"])
        splice = note + SWITCH
        return (prefix + enc(A_OPEN) + enc_plain(head + note) + enc(SWITCH),
                len(prefix), splice)
    # structural arms: hand the whole segment to openai_harmony to render
    from openai_harmony import (Author, Conversation, Message,
                                RenderConversationConfig, Role, SystemContent,
                                ReasoningEffort, ToolNamespaceConfig)
    hm = H.to_harmony_messages(msgs, effort="high", start_date=R.COLLECT_DATE)
    body = head.rstrip()                    # D6: analysis ends with the model's own text, then <|end|>
    for t in (body, content, ev["code"], ev["result"]):
        enc_plain(t)                        # same gate: reject literal control markers outright
    cfg = RenderConversationConfig(auto_drop_analysis=False)

    def render(ms):
        return list(H.encoding().render_conversation_for_completion(
            Conversation.from_messages(ms), Role.ASSISTANT, config=cfg))
    if where == "p3k":
        hm += [Message.from_role_and_content(Role.ASSISTANT, body)
               .with_channel("analysis"),
               Message.from_role_and_content(Role.ASSISTANT, content)
               .with_channel("final"),
               Message.from_role_and_content(
                   Role.USER, f"Execution output:\n{ev['result']}")]
    elif where == "p4":
        # D7: declare the python tool in system (part of the training format)
        sysc = (SystemContent.new()
                .with_reasoning_effort(ReasoningEffort.HIGH)
                .with_conversation_start_date(R.COLLECT_DATE)
                .with_tools(ToolNamespaceConfig.python()))
        hm[0] = Message.from_role_and_content(Role.SYSTEM, sysc)
        hm += [Message.from_role_and_content(Role.ASSISTANT, body)
               .with_channel("analysis"),
               Message.from_role_and_content(Role.ASSISTANT, ev["code"])
               .with_channel("analysis").with_recipient("python"),
               Message.from_author_and_content(
                   Author.new(Role.TOOL, "python"), ev["result"])
               .with_channel("analysis").with_recipient("assistant")]
    else:
        raise ValueError(arm)
    n_added = 3
    # prefix = this arm's own rendering of "history up to before this step" (p4's system
    # has an extra tool declaration, so the text arm's prefix length can't stand in for
    # it); it renders out ending at <|start|>assistant, which is exactly the prefix of
    # the whole string -- pin it down with an assert
    own_prefix = render(hm[:-n_added])
    ids = render(hm)
    if ids[:len(own_prefix)] != own_prefix:
        raise RuntimeError(f"{arm}: the structure arm's prefix is not a prefix of the full string, the renderer's behavior changed")
    if where == "p3k" and own_prefix != prefix:
        raise RuntimeError("p3k's prefix should be token-for-token identical to the chat render")
    return ids, len(own_prefix), H.decode(ids[len(own_prefix):])


# ---------------------------------------------------------------- run

def post_json(url, payload, timeout, retries=4):
    body = json.dumps(payload).encode()
    for att in range(retries):
        try:
            req = urllib.request.Request(
                url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError:
            raise                            # don't retry on things like 400, re-raise as-is
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if att == retries - 1:
                raise
            print(f"    retry {att + 1}: {e}", flush=True)
            time.sleep(2 ** att)


def cmd_run(a):
    d = Path(a.run_dir)
    # sampling keys come from the preset's client section (--preset defaults to default); temperature has this one source only
    root = str(HERE.parents[1])
    if root not in sys.path:
        sys.path.append(root)
    from preset_loader import load_preset, require_temperature   # noqa: E402
    pre = load_preset(a.preset)
    a.temperature = require_temperature(pre["client"]["temperature"], pre["_name"])
    R.check_system_verbatim()               # run/score also rebuild the prompt, and verify against the source the same way
    H.encoding()                            # get the encoder loaded before the thread pool starts (lazy loading isn't thread-safe)
    evs = [json.loads(l) for l in open(d / "events.jsonl")]
    if a.limit:
        evs = evs[:a.limit]
    arms = [x.strip() for x in a.arms.split(",") if x.strip()]
    bad = [x for x in arms if x not in ARMS]
    if bad:
        raise SystemExit(f"unknown arm: {bad}; options {ARMS_ALL}")
    rp = d / f"raw{a.tag}.jsonl"
    done = set()
    if rp.exists() and not a.dry_run:
        for l in open(rp):
            try:
                o = json.loads(l)
                done.add((o["event"], o["cut"], o["arm"]))
            except Exception:
                pass
    todo = [(ev, c, arm) for ev in evs for c in ev["cuts"] for arm in arms
            if (ev["event"], c["cut"], arm) not in done]
    print(f"events {len(evs)} cuts {sum(len(e['cuts']) for e in evs)} x arms {arms}"
          f"; already have {len(done)}, still to run {len(todo)}, concurrency {a.concurrency}", flush=True)
    if a.dry_run:
        todo = todo[:a.limit or 12]

    lock, cache, clock = threading.Lock(), {}, threading.Lock()
    stat = dict(n=0, fail=0, t0=time.time())

    def msgs_of(ev, permit):
        k = (ev["event"], permit)
        with clock:
            if k not in cache:
                cache[k] = prefix_messages(ev, permit)
            return cache[k]

    def one(ev, c, arm):
        _, _, permit = ARMS[arm]
        msgs, gens = msgs_of(ev, permit)
        think = (gens[ev["step"]].get("reasoning") or "").strip()
        head = think[:c["cut"]]
        content = gens[ev["step"]].get("content") or ""
        ids, plen, splice = build_prompt(arm, ev, head, msgs, content)
        head_tok = len(enc(A_OPEN + head))
        rec = dict(event=ev["event"], cut=c["cut"], fracs=c["fracs"], arm=arm,
                   prompt_tok=len(ids), prefix_tok=plen, head_tok=head_tok,
                   splice_tok=len(ids) - plen - head_tok, splice=splice)
        if a.dry_run:
            # only look at the seam: from 30 tokens before the end of head to the end of the prompt, then truncate to 1200 characters
            rec["prompt_tail"] = H.decode(ids[max(0, plen + head_tok - 30):])[:1200]
            return rec
        # D11: <|call|> is already in the model's generation_config eos list, and vLLM stops
        # every arm on it by default (stop_reason=200012); adding a string stop sequence here
        # is just a safety net
        stop = list(DEFAULT_STOP) + [CALL_MARK]
        t0 = time.time()
        r = post_json(a.base_url.rstrip("/") + "/completions", dict(
            model=a.model, prompt=ids, max_tokens=a.max_tokens,
            temperature=a.temperature, stop=stop, skip_special_tokens=False),
            a.timeout)
        ch = r["choices"][0]
        rec.update(text=ch["text"], finish_reason=ch.get("finish_reason"),
                   stop_reason=ch.get("stop_reason"),
                   prompt_tok=r["usage"]["prompt_tokens"],
                   gen_tok=r["usage"]["completion_tokens"],
                   wall_s=round(time.time() - t0, 2))
        return rec

    sink = open(rp, "a") if not a.dry_run else None
    with ThreadPoolExecutor(max_workers=a.concurrency) as ex:
        futs = {ex.submit(one, ev, c, arm): (ev["event"], c["cut"], arm)
                for ev, c, arm in todo}
        for fu in as_completed(futs):
            key = futs[fu]
            try:
                rec = fu.result()
            except Exception as e:
                stat["fail"] += 1
                print(f"  FAIL {key}: {type(e).__name__}: {e}", flush=True)
                continue
            with lock:
                if a.dry_run:
                    print(json.dumps(rec, ensure_ascii=False))
                else:
                    sink.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    sink.flush()
                stat["n"] += 1
                if stat["n"] % 50 == 0:
                    el = time.time() - stat["t0"]
                    rate = stat["n"] / el
                    left = (len(todo) - stat["n"]) / rate if rate else 0
                    print(f"  {stat['n']}/{len(todo)} {rate:.2f} req/s "
                          f"ETA {left/60:.1f} min", flush=True)
    if sink:
        sink.close()
        print(f"finished {stat['n']}/{len(todo)}; failed {stat['fail']} -> {rp}")
    else:
        print(f"dry-run printed {stat['n']} entries, wrote nothing to disk")


# ---------------------------------------------------------------- score

# discussing the injection itself. "the note" alone would false-hit on simple_note /
# "the notes app", so only recognize it paired with a verb; "already ran" is listed
# separately (n1's wording itself contains these three words, and they can also occur
# naturally in nofill, look at both sides together)
MENTION_RE = re.compile(
    r"system note|prefetch|the note says|note above|according to the note|"
    r"per the note|given the note|from the note", re.I)
ALREADY_RE = re.compile(r"already ran|already called|already executed", re.I)
STR_LIT_RE = re.compile(r"""(?:"([^"\\\n]{3,})"|'([^'\\\n]{3,})')""")


def analyze(arm, splice, text):
    """Reconstruct the splice string + continuation back into the full assistant turn text,
    split into (thinking, content).
    p1/nofill: the full turn = A_OPEN + head + splice + text (head isn't here; slicing
    just text also works -- the channel header is already written into the prompt
    before splice, and text starts inside analysis);
    p2: text starts inside final; p3k/p4: text starts after <|start|>assistant."""
    where = ARMS[arm][0]
    if where == "p1":
        return parse_step(A_OPEN + text)      # add the header back, parse_step recognizes it
    if where == "p2":
        think, content = parse_step(A_OPEN + splice + text)   # splice ends with SWITCH
        note = splice[:-len(SWITCH)].strip()
        t = think.lstrip()
        if note and t.startswith(note):       # the spliced-in NOTE doesn't count as the model "thinking more"
            think = t[len(note):]
        return think, content
    # p3k/p4: a python call segment the model initiates itself (to=python ... <|call|>)
    # doesn't count as "thinking"; strip it out before slicing.
    # it's extracted separately by python_call_code and counted as an action
    return parse_step(PY_CALL_RE.sub("", text))


# A python call segment the model writes itself. Observed (smoke test), it writes
# `<|start|>assistant<|channel|>analysis to=python code<|message|>CODE<|call|>`
# (the recipient comes after the channel, with an extra " code"), while the harmony
# library renders `<|start|>assistant to=python
# <|channel|>analysis<|message|>`; recognize both: consume from " to=python" through
# <|call|>/end of text, including the adjacent <|start|>assistant / <|channel|>analysis
# headers
PY_CALL_RE = re.compile(
    r"(?:<\|start\|>assistant)?(?:<\|channel\|>analysis)? to=python.*?<\|message\|>"
    r".*?(?:<\|call\|>|$)", re.S)


def python_call_code(text):
    """A python call the model initiates itself (analysis channel, recipient python): the
    code from the first <|message|> after `to=python` through <|call|>/end of text;
    None if there isn't one."""
    i = text.find(" to=python")
    if i < 0:
        return None
    j = text.find("<|message|>", i)
    if j < 0:
        return None
    body = text[j + len("<|message|>"):]
    return body.split(CALL_MARK, 1)[0]


def stopped_on_call(o):
    """Whether this continuation stopped on <|call|> (vLLM records the int 200012; a string stop sequence hit is recorded as a string)."""
    return o.get("stop_reason") in (CALL_ID, CALL_MARK)


def norm_call(c):
    return re.sub(r"\s+", "", c) if c else None


def first_tool(code):
    m = CALL_START.search(code or "")
    return f"apis.{m.group(1)}.{m.group(2)}" if m else None


def cmd_score(a):
    d = Path(a.run_dir)
    R.check_system_verbatim()
    evs = {}
    for l in open(d / "events.jsonl"):
        ev = json.loads(l)
        evs[ev["event"]] = ev
    raw = {}
    for l in open(d / f"raw{a.tag}.jsonl"):
        o = json.loads(l)
        raw[(o["event"], o["cut"], o["arm"])] = o        # later writes override earlier ones
    cache = {}

    def pre_text(ev, cut):
        k = (ev["event"], cut)
        if k not in cache:
            msgs, gens = prefix_messages(ev)
            think = (gens[ev["step"]].get("reasoning") or "").strip()
            cache[k] = "\n".join(m["content"] for m in msgs) + "\n" + think[:cut]
        return cache[k]

    rows = []
    for (evn, cut, arm), o in raw.items():
        ev = evs.get(evn)
        if ev is None or "text" not in o:
            continue
        think, content = analyze(arm, o["splice"], o["text"])
        m = CODE_RE.search(content)
        py_code = python_call_code(o["text"])
        # the model's "action" for this step: the body code block; if there's no body but it
        # fires off a python call on its own (this is how p4's natural continuation works,
        # harmony puts it in the analysis channel), that also counts as an action
        if m:
            code, action = m.group(1), "final_code"
        elif py_code is not None:
            code, action = py_code, "python_call"
        else:
            code, action = "", None
        tool = first_tool(code)
        call_out = complete_call(code)[0]
        pre = pre_text(ev, cut)
        lits = {x or y for x, y in STR_LIT_RE.findall(code)}
        used = sorted(s for s in lits if s in ev["result"] and s not in pre)
        # structure: opening analysis again after p2; any arm stopping on <|call|> (the model wants to call a tool)
        reopen = ("<|channel|>analysis" in o["text"]) if ARMS[arm][0] == "p2" \
            else None
        on_call = stopped_on_call(o)
        base = ev.get("baseline_out_tok")
        own_tok = o["head_tok"] + o["gen_tok"]      # written by the model itself (the splice string doesn't count)
        wire_tok = o["prompt_tok"] - o["prefix_tok"] + o["gen_tok"]
        # only events with an action enter the denominator for repeated/next_hit/advanced
        rep_tool = (tool == ev["call_tool"]) if tool else None
        rep_call = (norm_call(call_out) == norm_call(ev["call"])) if call_out else None
        nxt_tool = (tool == ev["next_tool"]) if tool and ev["next_tool"] else None
        nxt_call = ((norm_call(call_out) == norm_call(ev["next_call"]))
                    if call_out and ev.get("next_call") else None)
        rows.append(dict(
            event=evn, cut=cut, fracs=o["fracs"], arm=arm,
            head_tok=o["head_tok"], splice_tok=o["splice_tok"],
            gen_tok=o["gen_tok"], own_tok=own_tok, wire_tok=wire_tok,
            baseline_out_tok=base, baseline_capped=ev.get("baseline_capped"),
            code_is_print_call=ev.get("code_is_print_call"),
            next_distinct=(ev["next_tool"] is not None
                           and ev["next_tool"] != ev["call_tool"]),
            saved_own=(base - own_tok) if base is not None else None,
            saved_wire=(base - wire_tok) if base is not None else None,
            has_code=bool(m), action=action, has_action=action is not None,
            tool_out=tool, call_out=call_out,
            repeated=rep_tool, repeated_call=rep_call,
            next_hit=nxt_tool, next_hit_call=nxt_call,
            advanced=((tool != ev["call_tool"]) if tool else None),
            uses_result=bool(used), used_literals=used[:5],
            mentions=bool(MENTION_RE.search(o["text"])),
            mentions_already=bool(ALREADY_RE.search(o["text"])),
            reopen_analysis=reopen, stopped_on_call=on_call,
            python_call=(py_code is not None),
            think_chars_after=len(think.strip()), content_chars=len(content),
            finish_reason=o.get("finish_reason"), stop_reason=o.get("stop_reason")))
    # use nofill from the same event and same cut as the reference: the own_tok
    # difference (the splice string doesn't count) -- this is a tighter fit than
    # baseline, whose usage.out doesn't reconcile the commentary segment against the
    # message header accounting (the sanity-check line will show a constant offset of a
    # few tokens, don't treat that as a pipeline bug)
    nof = {(r["event"], r["cut"]): r["own_tok"] for r in rows if r["arm"] == "nofill"}
    for r in rows:
        n = nof.get((r["event"], r["cut"]))
        r["vs_nofill_own"] = (n - r["own_tok"]) if n is not None else None
    with open(d / f"per_row{a.tag}.jsonl", "w") as w:
        for r in rows:
            w.write(json.dumps(r, ensure_ascii=False) + "\n")

    def agg(rs):
        n = len(rs)
        if not n:
            return {}
        def rate(k):
            v = [r[k] for r in rs if r[k] is not None]
            return round(sum(bool(x) for x in v) / len(v), 3) if v else None
        def rate_where(k, cond):
            v = [r[k] for r in rs if r[k] is not None and r[cond]]
            return round(sum(bool(x) for x in v) / len(v), 3) if v else None
        def med(k):
            v = sorted(r[k] for r in rs if r[k] is not None)
            return v[len(v) // 2] if v else None
        def mean(k):
            v = [r[k] for r in rs if r[k] is not None]
            return round(sum(v) / len(v), 1) if v else None
        return dict(n=n, gen_tok_med=med("gen_tok"), own_tok_med=med("own_tok"),
                    vs_nofill_own_med=med("vs_nofill_own"),
                    saved_own_med=med("saved_own"), saved_own_mean=mean("saved_own"),
                    saved_wire_med=med("saved_wire"),
                    has_code=rate("has_code"), has_action=rate("has_action"),
                    python_call=rate("python_call"),
                    repeated=rate("repeated"), repeated_call=rate("repeated_call"),
                    next_hit=rate("next_hit"), next_hit_call=rate("next_hit_call"),
                    next_hit_distinct=rate_where("next_hit", "next_distinct"),
                    advanced=rate("advanced"),
                    uses_result=rate("uses_result"), mentions=rate("mentions"),
                    mentions_already=rate("mentions_already"),
                    reopen_analysis=rate("reopen_analysis"),
                    stopped_on_call=rate("stopped_on_call"),
                    truncated=round(sum(r["finish_reason"] == "length"
                                        for r in rs) / n, 3),
                    think_after_med=med("think_chars_after"))

    by_arm = defaultdict(list)
    by_arm_frac = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by_arm[r["arm"]].append(r)
        for f in r["fracs"]:
            by_arm_frac[f"{f:.2f}"][r["arm"]].append(r)
    rep = dict(run_dir=str(d), n_rows=len(rows),
               n_rows_baseline_capped=sum(bool(r["baseline_capped"]) for r in rows),
               by_arm={k: agg(v) for k, v in by_arm.items()},
               by_arm_uncapped={k: agg([r for r in v if not r["baseline_capped"]])
                                for k, v in by_arm.items()},
               # n0's wording is only accurate for bare print(CALL) blocks, look at it broken down
               by_arm_print_call={k: agg([r for r in v if r["code_is_print_call"]])
                                  for k, v in by_arm.items()},
               by_arm_not_print_call={k: agg([r for r in v if not r["code_is_print_call"]])
                                      for k, v in by_arm.items()},
               by_frac={f: {k: agg(v) for k, v in arms.items()}
                        for f, arms in sorted(by_arm_frac.items())})
    (d / f"SPLICE_REPORT{a.tag}.json").write_text(
        json.dumps(rep, indent=1, ensure_ascii=False))
    cols = ["n", "own_tok_med", "vs_nofill_own_med", "saved_own_med", "has_action",
            "python_call", "repeated", "repeated_call", "next_hit", "next_hit_call",
            "next_hit_distinct", "uses_result", "mentions", "mentions_already",
            "reopen_analysis", "stopped_on_call", "truncated", "think_after_med"]
    lines = [f"# SPLICE_REPORT{a.tag}", "", f"rows={len(rows)}",
             "", "## by arm", "", "| arm | " + " | ".join(cols) + " |",
             "|" + "---|" * (len(cols) + 1)]
    for k in ARMS_ALL:
        if k in rep["by_arm"]:
            v = rep["by_arm"][k]
            lines.append(f"| {k} | " + " | ".join(str(v.get(c)) for c in cols) + " |")
    for f, arms in rep["by_frac"].items():
        lines += ["", f"## frac {f}", "", "| arm | " + " | ".join(cols) + " |",
                  "|" + "---|" * (len(cols) + 1)]
        for k in ARMS_ALL:
            if k in arms:
                v = arms[k]
                lines.append(f"| {k} | " + " | ".join(str(v.get(c)) for c in cols) + " |")
    (d / f"SPLICE_REPORT{a.tag}.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


# ---------------------------------------------------------------- cli

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sp = ap.add_subparsers(dest="cmd", required=True)
    e = sp.add_parser("events")
    e.add_argument("--traj-root", required=True)
    e.add_argument("--out", required=True)
    e.add_argument("--fracs", default=",".join(str(f) for f in FRACS))
    e.set_defaults(fn=cmd_events)
    r = sp.add_parser("run")
    r.add_argument("--run-dir", required=True)
    r.add_argument("--base-url", default="http://tokyo108:8103/v1")
    r.add_argument("--model", default="gpt-oss-120b")
    r.add_argument("--preset", default="default",
                   help="a set of generation settings from configs/presets/<name>.json;"
                        "the continuation's temperature is read from this preset's client section")
    r.add_argument("--arms", default=",".join(ARMS_ALL))
    r.add_argument("--max-tokens", type=int, default=MAX_STEP_TOKENS)   # D8
    r.add_argument("--concurrency", type=int, default=16)
    r.add_argument("--timeout", type=int, default=1800)
    r.add_argument("--limit", type=int, default=0)
    r.add_argument("--tag", default="")
    r.add_argument("--dry-run", action="store_true")
    r.set_defaults(fn=cmd_run)
    s = sp.add_parser("score")
    s.add_argument("--run-dir", required=True)
    s.add_argument("--tag", default="")
    s.set_defaults(fn=cmd_score)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
