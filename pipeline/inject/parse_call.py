"""Cuts one complete apis call out of continuation text (standard library only). Spec:
plans/2026-08-01-splice-impl-spec.md §D1

Whether the model finished writing the call, for the splice-back experiment, can't be judged with a
regex -- calls with parentheses, quotes, and escapes in the arguments are everywhere
(`print(apis.phone.send_message(message="Hi :) (really)"))`), and a regex only stops at the first `)`.
So this hand-writes bracket matching instead: parentheses inside quotes (single, double, triple) don't
count, a backslash escape skips the next character, and everything from `#` to end of line counts as
a comment.

Imported by both replay_inject.py (score section C2) and extract_completed.py, so this file may only
depend on the standard library: cprobe-env and any future bare python must be able to import it.

Self-test: python pipeline/inject/parse_call.py
"""

import re

# call start. Character-for-character identical to AW_CALL in pipeline/annotate/rules.py -- there is
# only one convention for tool names; writing a separate regex here is only to avoid depending on that
# package, and the pattern must stay in sync
CALL_START = re.compile(r"apis\.(\w+)\.(\w+)\(")

FENCE = "```"


def complete_call(text, start=0):
    """Finds the first apis call starting from start, matching parentheses through to close.

    Returns (call_str, end_idx): call_str is the bare call string from `apis.` through the matched
    closing parenthesis, end_idx is the position **right after** the closing parenthesis (usable
    directly as the start of the next search).
    Returns (None, None) if no call start is found, or if it never balances by end of text.
    """
    s = text or ""
    m = CALL_START.search(s, start)
    if m is None:
        return None, None
    i, depth, quote = m.end() - 1, 0, None      # i stops on that opening parenthesis
    while i < len(s):
        c = s[i]
        if quote is not None:                   # inside a string: only look for the closing quote
            if c == "\\":
                i += 2                          # an escape consumes the next character
                continue
            if s.startswith(quote, i):
                i += len(quote)
                quote = None
                continue
            i += 1
            continue
        if c in "\"'":                          # entering a string, triple quotes match first
            quote = c * 3 if s.startswith(c * 3, i) else c
            i += len(quote)
            continue
        if c == "#":                            # a comment consumes to end of line
            nl = s.find("\n", i)
            if nl < 0:
                return None, None
            i = nl + 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return s[m.start():i + 1], i + 1
        i += 1
    return None, None


def call_at(text, pos):
    """The complete call that starts **exactly** at position pos in text; returns (None, None) if that
    position is not a call start.

    This is what the skeleton arm needs: the skeleton pins `apis.x.y` at a known position (the tail of
    the text spliced into the prompt is the tool name itself), and only counts as completed once the
    model goes on to write the arguments. Under the hard rule, the skeleton carries no trailing opening
    parenthesis, while CALL_START only matches `apis.x.y(` -- if the model doesn't continue with `(` but
    instead starts a new line and writes its own call, complete_call would search all the way to that
    call, reporting the skeleton as completed and extracting the model's own call instead. Anchoring to
    the position is what separates "completed the skeleton" from "threw out the skeleton and wrote its
    own".
    """
    call, end = complete_call(text, pos)
    if call is None or end - len(call) != pos:
        return None, None
    return call, end


def find_fence_close(text, start=0):
    """Finds the closing fence ``` starting from start, returns the position **right after** it; returns
    None if there isn't one.

    Only recognizes the three backticks themselves, not the opening fence -- the caller is responsible
    for placing start after the opening fence (in the splice-back experiment the opening fence
    ```python is something we insert into the prompt ourselves, it is not part of the continuation).
    """
    j = (text or "").find(FENCE, start)
    return None if j < 0 else j + len(FENCE)


if __name__ == "__main__":
    cases = [
        # (text, expected call_str)
        ("print(apis.venmo.login(username='a'))",
         "apis.venmo.login(username='a')"),
        # parentheses inside quotes don't count
        ('apis.phone.send_message(message="hi :) (really)")',
         'apis.phone.send_message(message="hi :) (really)")'),
        # a backslash-escaped quote does not close the string
        (r'apis.file_system.write(text="say \") here")',
         r'apis.file_system.write(text="say \") here")'),
        # nested call
        ("x = apis.a.b(c=apis.d.e(f=1), g=2)\nprint(x)",
         "apis.a.b(c=apis.d.e(f=1), g=2)"),
        # parentheses inside triple quotes
        ('apis.a.b(t="""a ) b""", u=1)', 'apis.a.b(t="""a ) b""", u=1)'),
        # a closing parenthesis inside a comment does not stop it
        ("apis.a.b(\n  x=1,  # )))\n  y=2)",
         "apis.a.b(\n  x=1,  # )))\n  y=2)"),
        # unclosed
        ("print(apis.venmo.login(username='a'", None),
        # skeleton truncated before the opening parenthesis (the skeleton's shape in the splice-back experiment)
        ("print(apis.venmo.login", None),
        # no call at all
        ("just some thinking text", None),
    ]
    for txt, want in cases:
        got, end = complete_call(txt)
        assert got == want, f"complete_call({txt!r}) -> {got!r} expected {want!r}"
        if want is None:
            assert end is None, (txt, end)
        else:
            assert txt[end - len(want):end] == want, (txt, end)

    # start offset: skip the first one, take the second
    two = "apis.a.b()\nprint(apis.c.d(x=1))"
    first, e1 = complete_call(two)
    assert first == "apis.a.b()", first
    second, _ = complete_call(two, e1)
    assert second == "apis.c.d(x=1)", second

    # anchor position: for the skeleton `print(apis.venmo.login`, the tool name starts at position 6
    sk = "print(apis.venmo.login"
    pos = len(sk) - len("apis.venmo.login")
    ok = sk + "(username='a'))\n```\n"
    assert call_at(ok, pos)[0] == "apis.venmo.login(username='a')"
    # the model doesn't fill in the arguments and instead starts a new line writing its own call: that
    # doesn't count as completing the skeleton
    bad = sk + "\nWait, wrong.\nprint(apis.api_docs.show_api_doc('venmo'))"
    assert complete_call(bad)[0] == "apis.api_docs.show_api_doc('venmo')"
    assert call_at(bad, pos) == (None, None)
    # not balanced at the skeleton position doesn't count as completed either
    assert call_at(sk + "(username='a'", pos) == (None, None)

    # fence
    assert find_fence_close("code```\ntail") == 7
    assert find_fence_close("no fence here") is None
    assert find_fence_close("```a```", 3) == 7

    print("parse_call selftest passed: %d complete_call cases + offset + 3 anchor-position cases + 3 fence cases"
          % len(cases))
