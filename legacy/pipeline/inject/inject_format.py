"""Injection formats: the text that goes back into the token stream when the probe fires, and
where it goes (METHOD.md axis 5, decided 2026-09-12). Stdlib only, so both the live driver
(appworld venv) and the probe server (cprobe-env) can import it.

Two placements:
  think  the text is appended inside the model's open thinking segment, right after the head
         (the model's own ids up to the cut); the model keeps thinking. Zero control markers.
  after  the thinking segment is closed with <|end|>, a message from a sender named `prefetch`
         is appended on the analysis channel, then <|start|>assistant: the model picks its next
         channel itself (a second thinking block, or straight to final). This placement writes
         control markers, so the driver asks the probe server to encode it with special=True.

Two ways to explain the mechanism to the model:
  e1  every injection carries the explanation sentence inline;
  e2  the system prompt carries one paragraph (system_extra) and the injection is a marker only.

`note` is the format the driver used before this table existed (kept byte for byte, default).

The sender is named `prefetch` and not `python` on purpose: with the python sender the model
switches into calling the python tool itself, and the AppWorld harness has no server for that
channel.

Head seam (think placement only): a head ending in whitespace gets the text appended directly,
otherwise one newline first -- the model's last token is never merged or rewritten. `after`
placement appends <|end|> right after the head without trimming, for the same reason.
"""

EXPLAIN = ("The system already ran {call} for you and got:\n{result}\n"
           "You can use this result without calling it.")
MARKER = "[Prefetch] {call} = {result}"
SYSTEM_EXTRA = (
    "\n\nSometimes a prefetched result appears while you reason, either as a line starting with "
    "[Prefetch] or as a message from a sender named prefetch. It means the system already ran "
    "that call for you; use the result without calling it again.")

TAIL = ("<|end|><|start|>prefetch to=assistant<|channel|>analysis<|message|>"
        "{body}<|end|><|start|>assistant")
PREFETCH_SENDER = "<|start|>prefetch"

FORMATS = {
    "note": dict(place="think", body="[SYSTEM NOTE: prefetched {call} = {result}]\n", system=""),
    "p1_e1": dict(place="think", body="[Prefetch: " + EXPLAIN + "]\n", system=""),
    "p1_e2": dict(place="think", body=MARKER + "\n", system=SYSTEM_EXTRA),
    "p2_e1": dict(place="after", body=EXPLAIN, system=""),
    "p2_e2": dict(place="after", body="{call} = {result}", system=SYSTEM_EXTRA),
}


def sep_for(head):
    """Seam before text appended inside the thinking: nothing when head ends in whitespace,
    one newline otherwise."""
    return "" if head[-1:].isspace() else "\n"


def system_extra(name):
    """Paragraph appended to the system prompt for this format ('' for formats that explain
    inline or not at all)."""
    return FORMATS[name]["system"]


def needs_special(name):
    """True when the format's text carries control markers and must be encoded with them
    recognised (the `after` placement)."""
    return FORMATS[name]["place"] == "after"


def splice_text(name, head, call, result):
    """The exact text appended after the head (the model's own text up to the cut)."""
    f = FORMATS[name]
    body = f["body"].format(call=call, result=result)
    if f["place"] == "think":
        return sep_for(head) + body
    return TAIL.format(body=body)


def is_prefetch_header(hdr):
    """True for the header of a message written by the prefetch sender (the `after` placement)."""
    return hdr.lstrip().startswith(PREFETCH_SENDER)
