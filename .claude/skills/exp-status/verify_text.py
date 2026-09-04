#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_text.py — 校验 HTML 的可见文字和 markdown 的正文逐字符相同。

用法：
    python3 verify_text.py <input.md> <output.html>

HTML 这边：丢掉 <style>、<script>、<title> 的内容和注释，剥掉全部标签，还原 HTML 实体。
markdown 这边：去掉行首的 #、表格的竖线和 |---| 分隔行、代码围栏的 ``` 行本身、
列表的 - 或 1. 前缀、加粗的 **、行内代码的反引号、水平线 ---（代码围栏里面一个字不动）。
两边都删掉全部空白字符之后逐字符比对。

一致就打印「逐字符一致」并以 0 退出；不一致就用 difflib 打印差异块并以 1 退出。
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
            continue  # 围栏行本身不算正文
        if in_fence:
            out.append(line)  # 代码块内容原样保留
            continue
        if HR_RE.match(stripped):
            continue
        if stripped.startswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if cells and all(DELIM_CELL_RE.match(c) for c in cells):
                continue  # |---| 分隔行
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
    print("  %s [%d:%d] %s《%s》%s" % (label, lo, hi, head, body, tail))


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("用法：python3 verify_text.py <input.md> <output.html>\n")
        return 2
    with open(argv[1], "r", encoding="utf-8") as fh:
        md = md_text(fh.read())
    with open(argv[2], "r", encoding="utf-8") as fh:
        ht = html_text(fh.read())

    print("markdown 正文字符数：%d" % len(md))
    print("HTML 可见文字字符数：%d" % len(ht))

    if md == ht:
        print("逐字符一致")
        return 0

    print("不一致，差异块如下（《》里是差的那一段）：")
    matcher = difflib.SequenceMatcher(None, md, ht, autojunk=False)
    shown = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        shown += 1
        if shown > MAX_BLOCKS:
            print("  ……还有更多差异块，先改前面的。")
            break
        print("差异 %d：%s" % (shown, tag))
        show("markdown", md, i1, i2)
        show("HTML    ", ht, j1, j2)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
