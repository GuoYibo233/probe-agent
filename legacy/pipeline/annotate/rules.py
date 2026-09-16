"""Split-rule constants and functions ([COPIED] from old code, the single source of
truth for the new pipeline).

- The first seven constants + SENT_RE + boundaries/clip/assemble/split_args/
  first_call_args + AW_CALL/BFCL_CALL: copied as-is from
  envs/collect/build_dataset.py
- split_args_named/first_call_named/mkparams: copied as-is from
  envs/bert/param_label.py

Input/output: this file holds only pure functions and constants, it reads and
writes no files.
Usage example: from rules import boundaries, assemble, AW_CALL
"""

import re

SEED = 42             # starting at np821, switch to the first entry of the seed family (42/67/4267/6742); the old value 20260729 only
                      # takes effect when an old config explicitly writes the seed field (cfg.get("seed", SEED) overrides this value)
MAX_BOUNDS = 64       # per-event boundary cap (guards against gpt-oss's excessively long thinking blowing up)
MIN_THINK = 40        # characters; thinking shorter than this has no cuttable points
HIST_ROUNDS = 3       # number of recent tool-history rounds kept in the prompt
RESULT_CAP = 400      # character cap per environment return within the prompt
MODEL_OF = {"q35": "qwen3.5-27b", "q36": "qwen3.6-27b", "gptoss": "gpt-oss-120b"}

# sentence boundary: a newline, or .!? followed by whitespace (a decimal point or the dot in apis.x.y has no following whitespace, so it is naturally excluded)
SENT_RE = re.compile(r"(?<=[.!?])\s+|\n")


def boundaries(text, max_bounds=MAX_BOUNDS):
    """All legal cut points (character offset, prefix=text[:i]), including the end of
    the full text, capped at max_bounds.

    The cap defaults to MAX_BOUNDS(64); leaving it unpassed matches the pre-change
    behavior byte for byte. A caller that wants a different cap (a batch config's
    max_bounds, or 10**9 when counting untruncated cut points) must pass it
    explicitly.
    """
    pts = sorted({m.end() for m in SENT_RE.finditer(text)} | {len(text)})
    pts = [p for p in pts if len(text[:p].strip()) >= MIN_THINK // 2]
    if not pts:
        pts = [len(text)]
    if len(pts) > max_bounds:
        keep = {len(pts) - 1}
        step = (len(pts) - 1) / (max_bounds - 1)
        keep.update(round(k * step) for k in range(max_bounds - 1))
        pts = [pts[j] for j in sorted(keep)]
    return pts


def clip(s, cap=RESULT_CAP):
    s = str(s)
    return s if len(s) <= cap else s[: cap - 60] + " ...[cut]... " + s[-40:]


def assemble(task, history, think_prefix):
    lines = [f"Task: {task}", "[HISTORY]"]
    if history:
        lines += [f"{a} -> {clip(r)}" for a, r in history[-HIST_ROUNDS:]]
    else:
        lines.append("(start)")
    lines += ["[THINKING]", think_prefix]
    return "\n".join(lines)


# ---------- parameter extraction (for routing statistics) ----------

AW_CALL = re.compile(r"apis\.(\w+)\.(\w+)\(")
BFCL_CALL = re.compile(r"(\w+)\(")


def split_args(argstr):
    vals, buf, depth, q = [], "", 0, None
    for ch in argstr:
        if q:
            buf += ch
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch
            buf += ch
        elif ch in "([{":
            depth += 1
            buf += ch
        elif ch in ")]}":
            depth -= 1
            buf += ch
        elif ch == "," and depth == 0:
            vals.append(buf.strip())
            buf = ""
        else:
            buf += ch
    if buf.strip():
        vals.append(buf.strip())
    out = []
    for v in vals:
        m = re.match(r"\w+\s*=\s*(.+)", v, re.S)
        out.append((m.group(1) if m else v).strip().strip("\"'"))
    return out


def first_call_args(code, name_re):
    m = name_re.search(code)
    if not m:
        return None
    i, depth = m.end() - 1, 0
    for j in range(i, len(code)):
        if code[j] == "(":
            depth += 1
        elif code[j] == ")":
            depth -= 1
            if depth == 0:
                return split_args(code[i + 1: j])
    return []


# ---------- name-preserving parameter parsing (same splitting method as split_args) ----------

def split_args_named(argstr):
    vals, buf, depth, q = [], "", 0, None
    for ch in argstr:
        if q:
            buf += ch
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch
            buf += ch
        elif ch in "([{":
            depth += 1
            buf += ch
        elif ch in ")]}":
            depth -= 1
            buf += ch
        elif ch == "," and depth == 0:
            vals.append(buf.strip())
            buf = ""
        else:
            buf += ch
    if buf.strip():
        vals.append(buf.strip())
    out, pos = [], 0
    for v in vals:
        m = re.match(r"(\w+)\s*=\s*(.+)", v, re.S)
        if m:
            out.append((m.group(1), m.group(2).strip().strip("\"'")))
        else:
            out.append((f"pos{pos}", v.strip().strip("\"'")))
            pos += 1
    return out


def first_call_named(code, name_re):
    m = name_re.search(code)
    if not m:
        return None
    i, depth = m.end() - 1, 0
    for j in range(i, len(code)):
        if code[j] == "(":
            depth += 1
        elif code[j] == ")":
            depth -= 1
            if depth == 0:
                return split_args_named(code[i + 1: j])
    return []


def mkparams(tool, named):
    """(name, value) -> [(key,value)], empty values skipped, the first occurrence is kept for a repeated key."""
    out, seen = [], set()
    for name, val in named:
        if not val:
            continue
        k = f"{tool}.{name}"
        if k in seen:
            continue
        seen.add(k)
        out.append((k, val))
    return out


# ---------- ALFWorld: natural-language action -> tool name + named parameters (c2 batch, template-level convention) ----------
#
# Single source of truth = the action-grammar file installed locally by
#   alfworld==0.4.2:
#   fig1_pilot/fig1-env/lib/python3.12/site-packages/alfworld/data/alfred.twl2
# The table below corresponds line by line to that file's `template :: "..."` lines
# (line numbers noted in the comments), 13 entries in all.
# The file has 8 more template lines that do not go into this table, for three
# kinds of reasons:
#   - duplicates: 191/196/201/206 are all `take {o} from {r}`, 211/221 are both
#           `move {o} to {r}`, 236/241 are both `examine {x}` -- multiple action
#           definitions for the same surface template
#   - movable-receptacle variants: 216 `put {o} into {outero}`, 226
#           `put {outero} in {r}` -- ALFWorld itself excludes this class of task,
#           so they are excluded here too
#   - meta-command: 425 `help` -- not an environment action; its feedback text, as
#           it happens, lists exactly these 13 entries one by one
#
# Parameter key-naming convention: a prepositional slot takes the preposition
# itself (to/from/with), a fronted-object slot takes obj; all match `\w+`, which
# satisfies rules.split_args_named's requirement on keys.

ALF_TEMPLATES = (
    ("go to {to}", 176),                    # action GotoLocation
    ("take {obj} from {from}", 191),        # action PickupObject(+196/201/206)
    ("move {obj} to {to}", 211),            # action PutObject(+221)
    ("heat {obj} with {with}", 269),        # action HeatObject
    ("clean {obj} with {with}", 284),       # action CleanObject
    ("cool {obj} with {with}", 299),        # action CoolObject
    ("slice {obj} with {with}", 314),       # action SliceObject
    ("examine {obj}", 236),                 # action examineReceptacle(+241)
    ("inventory", 231),                     # action inventory
    ("open {obj}", 181),                    # action OpenObject
    ("close {obj}", 186),                   # action CloseObject
    ("use {obj}", 246),                     # action ToggleObject
    ("look", 329),                          # action look
)

# Characters never allowed to appear in a parameter value. The comma is a hard
# requirement: eval_causal_call.split_named_raw splits arguments on top-level
# commas, while the annotate side does not split when hand-assembling label_call,
# so a comma in a value means a silent point loss.
# Parentheses/quotes are the same: they throw off parse_call's paren balancing and
# split_args_named's quote stripping.
ALF_BAD_CHARS = ",()[]{}\"'"

# Value-shape gate for parameters: an ALFWorld entity name is always "a single
# pure-letter type name + space + index" (mug 1 / countertop 3 / sinkbasin 1 /
# bathtubbasin 1) -- ALFRED's object types are CamelCase words, which textworld
# lowercases and appends an index to. Measured: all 146 distinct entity values
# across fig1_pilot's full 17510 actions are 100% this shape.
# What this catches is **the class of contamination the comma gate cannot catch**:
# a template's tail slot is the greedy `(.+)`, so
# `go to countertop 1 and take mug 1` matches `go to {to}` and the value becomes
# "countertop 1 and take mug 1" -- an action the environment would never accept,
# turned silently into a legal ground truth. A trailing period as in
# `go to countertop 1.` has the same problem. All of this falls through to the
# fallback and gets counted.
ALF_VALUE_RE = re.compile(r"[A-Za-z]+ \d+")


def _alf_compile(tpl):
    """`"take {obj} from {from}"` -> (tool name, [key...], leading literal, compiled regex)."""
    parts = re.split(r"\{(\w+)\}", tpl)     # even index = literal, odd index = parameter name
    keys = parts[1::2]
    pat = ""
    for i, p in enumerate(parts):
        if i % 2 == 0:
            pat += re.escape(p)
        else:                               # the last slot is greedy, the rest are non-greedy (shortest match first)
            pat += "(.+)" if i == len(parts) - 2 else "(.+?)"
    return (parts[0].split()[0], keys, parts[0],
            re.compile("^" + pat + "$", re.IGNORECASE))


# Longest-prefix-first: sorted by leading-literal length descending (`go to ` must
# come before any `go `).
# sorted is stable, so entries of the same length keep the table's declaration order above.
ALF_RULES = sorted((_alf_compile(t) for t, _ln in ALF_TEMPLATES),
                   key=lambda r: -len(r[2]))
ALF_TOOLS = tuple(dict.fromkeys(r[0] for r in ALF_RULES))

# For parsing on the generation side: only recognizes calls that start with one of these 13 tool names, drawn from the same source as the table above (no separate second list).
ALF_CALL = re.compile(
    r"\b(" + "|".join(sorted(ALF_TOOLS, key=len, reverse=True)) + r")\s*\(")


def alf_split(action):
    """ALFWorld action text -> (tool, [(key,value)], reason for failure).

    reason=None when it parses; when it does not parse, returns (None, [], reason),
    and the **caller must count this** -- it must never be silently swapped for a
    different convention (otherwise this regresses to the rejected "first word =
    tool name" catch-all parsing).

    Three kinds of reason:
      no_template  no official template matched at all (the model sent a string
                   not among the 13 templates)
      empty_value  matched, but some slot is blank
      bad_char     the value contains ALF_BAD_CHARS (comma/parenthesis/quote) --
                   leaving it in would silently cost points
      odd_shape    the value is not "type name + space + index" (see
                   ALF_VALUE_RE), most often the greedy tail slot swallowing a
                   sentence fragment or punctuation
    """
    act = " ".join(str(action).split())      # only normalizes whitespace, does not change case and does not strip punctuation
    if not act:
        return None, [], "no_template"
    for tool, keys, _lead, rx in ALF_RULES:
        m = rx.match(act)
        if not m:
            continue
        named = []
        for k, v in zip(keys, m.groups()):
            v = v.strip()
            if not v:
                return None, [], "empty_value"
            if any(c in v for c in ALF_BAD_CHARS):
                return None, [], "bad_char"
            if not ALF_VALUE_RE.fullmatch(v):
                return None, [], "odd_shape"
            named.append((k, v))
        return tool, named, None
    return None, [], "no_template"
