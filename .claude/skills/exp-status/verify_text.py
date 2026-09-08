#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_text.py -- check that the HTML's visible text and the markdown's body text are
character-for-character identical.

Usage:
    python3 verify_text.py <input.md> <output.html>

HTML side: drop the contents and comments of <style>, <script>, <title>, strip all tags,
and unescape HTML entities.
Markdown side: strip the leading # of headings, the table's pipe characters and the
|---| separator row, the ``` fence lines themselves, the - or 1. list prefixes, the **
of bold text, the backticks of inline code, and the --- horizontal rule (leave code
fence contents untouched).
Compare the two sides character by character after removing all whitespace from both.

If they match, print "character-for-character match" and exit 0; if not, print the diff
blocks with difflib and exit 1.
"""

import difflib
import html
import re
import sys

STYLE_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.I | re.S)
SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.I | re.S)
TITLE_RE = re.compile(r"<title\b[^>]*>.*?</title>", re.I | re.S)
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
TAG_RE = re.compile(r"<[^>]*>", re.S)

FENCE_RE = re.compile(r"^\s*```")
HR_RE = re.compile(r"^-{3,}$")
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+")
UL_RE = re.compile(r"^\s*[-*+]\s+")
OL_RE = re.compile(r"^\s*\d+\.\s+")
DELIM_CELL_RE = re.compile(r"^:?-{1,}:?$")

CONTEXT = 30
MAX_BLOCKS = 20


def html_text(src):
    s = COMMENT_RE.sub(" ", src)
    s = STYLE_RE.sub(" ", s)
    s = SCRIPT_RE.sub(" ", s)
    s = TITLE_RE.sub(" ", s)
    s = TAG_RE.sub(" ", s)
    s = html.unescape(s)
    return "".join(s.split())


def md_text(src):
    out = []
    in_fence = False
    for line in src.split("\n"):
        stripped = line.strip()
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue  # the fence line itself does not count as body text
        if in_fence:
            out.append(line)  # keep code block contents as-is
            continue
        if HR_RE.match(stripped):
            continue
        if stripped.startswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if cells and all(DELIM_CELL_RE.match(c) for c in cells):
                continue  # the |---| separator row
            line = stripped.replace("|", " ")
        elif HEADING_RE.match(line):
            line = HEADING_RE.sub("", line)
        elif UL_RE.match(line):
            line = UL_RE.sub("", line)
        elif OL_RE.match(line):
            line = OL_RE.sub("", line)
        line = line.replace("**", "").replace("`", "")
        out.append(line)
    return "".join("".join(out).split())


def show(label, s, lo, hi):
    head = s[max(0, lo - CONTEXT):lo]
    body = s[lo:hi]
    tail = s[hi:hi + CONTEXT]
    print("  %s [%d:%d] %s<<%s>>%s" % (label, lo, hi, head, body, tail))


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: python3 verify_text.py <input.md> <output.html>\n")
        return 2
    with open(argv[1], "r", encoding="utf-8") as fh:
        md = md_text(fh.read())
    with open(argv[2], "r", encoding="utf-8") as fh:
        ht = html_text(fh.read())

    print("markdown body character count: %d" % len(md))
    print("HTML visible text character count: %d" % len(ht))

    if md == ht:
        print("identical character-for-character")
        return 0

    print("not identical, diff blocks below (the differing part is inside <<...>>):")
    matcher = difflib.SequenceMatcher(None, md, ht, autojunk=False)
    shown = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        shown += 1
        if shown > MAX_BLOCKS:
            print("  ... more diff blocks remain, fix the earlier ones first.")
            break
        print("diff %d: %s" % (shown, tag))
        show("markdown", md, i1, i2)
        show("HTML    ", ht, j1, j2)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
