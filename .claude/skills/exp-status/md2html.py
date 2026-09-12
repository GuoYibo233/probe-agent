#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""md2html.py -- convert a markdown file into one HTML page, purely deterministic.

Usage:
    python3 md2html.py <input.md> <output.html>

Uses only the Python standard library. The same input always produces the same output.
The script only moves characters: it does not rewrite, polish, or drop body text, and it
never adds visible text to the page that is not in the markdown.
The visible text on the page and the markdown's body text, after stripping markup, are
character-for-character identical once all whitespace is removed
(verified by verify_text.py).

Recognized blocks: heading levels 1 to 6, paragraphs, ordered lists, unordered lists, GFM
tables (header row + second-row |---|), triple-backtick code fences, horizontal rule ---.
Recognized inline: **bold**, backtick inline code, bare URLs (starting with https:// or
http://), HTML special-character escaping.
"""

import html
import re
import sys

PAGE_TITLE = "Cache-reuse trainer status"

# Collapse-block opening tags: a paragraph starting with one of these three plus an
# ASCII colon gets folded into <details>.
FOLD_LABELS = ("How it was done", "Why this design counts", "One real sample")
# Collapse-block closing tags: a paragraph starting with one of these three ends the
# collapse block.
STOP_PREFIXES = ("Experiment results", "Worth noting", "Index")

FENCE = "```"

CSS = """
:root{
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans CJK SC","Source Han Sans SC",sans-serif;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,"Liberation Mono","PingFang SC",monospace;
  --bg:#f5f7f6;
  --panel:#ffffff;
  --panel-2:#eaeeec;
  --ink:#17211f;
  --ink-2:#4d5b58;
  --ink-3:#77847f;
  --rule:#d6dcda;
  --rule-2:#bac5c1;
  --accent:#0d7268;
  --accent-2:#0a5a52;
  --accent-wash:rgba(13,114,104,.10);
  --code-bg:#eef2f0;
  --code-ink:#1d2b28;
  --judg-bg:#f1f0f7;
  --judg-panel:#faf9fd;
  --judg-rule:#c6c1dd;
  --judg-accent:#5a4e8f;
  --judg-accent-2:#8c83bd;
  --zebra:rgba(23,33,31,.035);
  color-scheme:light;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --bg:#101614;
    --panel:#161e1c;
    --panel-2:#1d2725;
    --ink:#e6ecea;
    --ink-2:#a9b6b2;
    --ink-3:#7f8c88;
    --rule:#27322f;
    --rule-2:#3a4844;
    --accent:#4fc3b1;
    --accent-2:#7ed8c8;
    --accent-wash:rgba(79,195,177,.14);
    --code-bg:#131b19;
    --code-ink:#cfe0db;
    --judg-bg:#1a1826;
    --judg-panel:#201d2e;
    --judg-rule:#3d3660;
    --judg-accent:#a89bdf;
    --judg-accent-2:#6d61a8;
    --zebra:rgba(255,255,255,.04);
    color-scheme:dark;
  }
}
:root[data-theme="dark"]{
  --bg:#101614;
  --panel:#161e1c;
  --panel-2:#1d2725;
  --ink:#e6ecea;
  --ink-2:#a9b6b2;
  --ink-3:#7f8c88;
  --rule:#27322f;
  --rule-2:#3a4844;
  --accent:#4fc3b1;
  --accent-2:#7ed8c8;
  --accent-wash:rgba(79,195,177,.14);
  --code-bg:#131b19;
  --code-ink:#cfe0db;
  --judg-bg:#1a1826;
  --judg-panel:#201d2e;
  --judg-rule:#3d3660;
  --judg-accent:#a89bdf;
  --judg-accent-2:#6d61a8;
  --zebra:rgba(255,255,255,.04);
  color-scheme:dark;
}

body{
  margin:0;
  background:var(--bg);
  color:var(--ink);
  font-family:var(--sans);
  font-size:15px;
  line-height:1.7;
  -webkit-text-size-adjust:100%;
  overflow-x:hidden;
}
.doc{max-width:860px;margin:0 auto;padding:48px 22px 110px;}

h1,h2,h3,h4,h5,h6{text-wrap:balance;}
h1{
  font-size:clamp(1.45rem,1.05rem+1.5vw,2rem);
  line-height:1.42;
  font-weight:700;
  letter-spacing:-.005em;
  margin:0 0 1.4em;
  padding-bottom:.65em;
  border-bottom:2px solid var(--accent);
}
h2{
  position:relative;
  font-size:1.32rem;
  line-height:1.5;
  font-weight:650;
  margin:3.1em 0 1em;
  padding-top:1.1em;
  border-top:1px solid var(--rule-2);
}
h2::before{
  content:"";
  position:absolute;
  top:-1px;left:0;
  width:64px;height:3px;
  background:var(--accent);
}
h3{
  font-size:1.06rem;
  font-weight:650;
  line-height:1.6;
  margin:2.4em 0 .9em;
  padding-left:.62em;
  border-left:3px solid var(--accent);
}
p{margin:1em 0;}
h1+p{font-size:1.02rem;}

a{
  color:var(--accent-2);
  text-decoration:underline;
  text-underline-offset:2px;
  text-decoration-thickness:1px;
  word-break:break-all;
}
a:hover{text-decoration-thickness:2px;}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:3px;}

ul,ol{margin:1em 0;padding-left:1.55em;}
li{margin:.4em 0;}
li::marker{color:var(--accent);font-weight:600;}

code{
  font-family:var(--mono);
  font-size:.86em;
  background:var(--accent-wash);
  color:var(--accent-2);
  padding:.08em .34em;
  border-radius:4px;
  word-break:break-word;
}
pre.code{
  margin:1.2em 0;
  padding:.85em 1em;
  background:var(--code-bg);
  border:1px solid var(--rule);
  border-radius:8px;
  overflow-x:auto;
  font-size:.8rem;
  line-height:1.6;
}
pre.code code{
  font-family:var(--mono);
  background:none;
  color:var(--code-ink);
  padding:0;
  border-radius:0;
  white-space:pre;
  word-break:normal;
}

.table-wrap{
  margin:1.3em 0;
  overflow-x:auto;
  background:var(--panel);
  border:1px solid var(--rule);
  border-radius:8px;
}
table{border-collapse:collapse;width:100%;font-size:.84rem;font-variant-numeric:tabular-nums;}
th,td{
  padding:.5em .85em;
  text-align:left;
  white-space:nowrap;
  border-bottom:1px solid var(--rule);
}
th{background:var(--panel-2);font-weight:650;border-bottom:1px solid var(--rule-2);}
tbody tr:nth-child(even){background:var(--zebra);}
tbody tr:last-child th,tbody tr:last-child td{border-bottom:none;}

details.fold{
  margin:1.2em 0;
  background:var(--panel);
  border:1px solid var(--rule);
  border-left:3px solid var(--accent);
  border-radius:8px;
}
details.fold>summary{
  display:flex;
  align-items:center;
  gap:.6em;
  list-style:none;
  cursor:pointer;
  padding:.5em .9em;
  font-size:.92rem;
  font-weight:650;
  color:var(--accent-2);
}
details.fold>summary::-webkit-details-marker{display:none;}
details.fold>summary::before{
  content:"";
  flex:none;
  width:.42em;height:.42em;
  border-right:2px solid currentColor;
  border-bottom:2px solid currentColor;
  transform:rotate(-45deg);
  transition:transform .15s ease;
}
details.fold[open]>summary::before{transform:rotate(45deg);}
details.fold[open]>summary{border-bottom:1px solid var(--rule);}
.fold-body{padding:.15em .95em .5em;}
.fold-body>:first-child{margin-top:.85em;}
.fold-body>:last-child{margin-bottom:.6em;}
/* The first paragraph of the fold-block body starts with a full-width colon (the label moved into summary); let the colon hang into the left-hand blank space. */
.fold-body>p:first-child{text-indent:-.5em;}

.note{cursor:pointer;}
.note::before{
  content:"";
  display:inline-block;
  width:.42em;height:.42em;
  margin:0 .16em;
  vertical-align:.28em;
  border-radius:50%;
  background:var(--accent);
  transition:background .15s ease;
}
.note:hover::before,.note:focus::before,.note.is-open::before{background:var(--accent-2);}
.note-body{display:none;}
.note:hover .note-body,.note:focus .note-body,.note.is-open .note-body{
  display:inline;
  color:var(--ink-2);
  background:var(--accent-wash);
  border-radius:3px;
  padding:.05em .12em;
}
.verdict .note::before{background:var(--judg-accent);}
.verdict .note:hover .note-body,.verdict .note:focus .note-body,.verdict .note.is-open .note-body{
  background:rgba(90,78,143,.10);
}

.verdict{
  margin-top:3.6em;
  padding:0 clamp(16px,3.4vw,30px) 26px;
  background:var(--judg-bg);
  border:1px solid var(--judg-rule);
  border-radius:10px;
  overflow:hidden;
}
.band{
  height:11px;
  margin:0 calc(-1 * clamp(16px,3.4vw,30px));
  background:repeating-linear-gradient(135deg,var(--judg-accent) 0 7px,var(--judg-accent-2) 7px 14px);
}
.band+p{
  margin-top:1.5em;
  font-size:1.02rem;
  font-weight:600;
  color:var(--ink);
}
.verdict h2{border-top-color:var(--judg-rule);}
.verdict h2::before{background:var(--judg-accent);}
.verdict h3{border-left-color:var(--judg-accent);}
.verdict li::marker{color:var(--judg-accent);}
.verdict .table-wrap,.verdict details.fold{background:var(--judg-panel);}
.verdict code{
  background:rgba(90,78,143,.10);
  color:var(--judg-accent);
}
.verdict a{color:var(--judg-accent);}

@media (max-width:640px){
  .doc{padding:32px 16px 80px;}
  body{font-size:14.5px;}
}
@media (prefers-reduced-motion:reduce){
  *{transition:none !important;animation:none !important;}
}
"""

JS = """
(function(){
  function toggle(el){el.classList.toggle('is-open');}
  document.addEventListener('click',function(e){
    var t=e.target;
    if(!t||!t.closest){return;}
    var n=t.closest('.note');
    if(n){toggle(n);}
  });
  document.addEventListener('keydown',function(e){
    if(e.key!=='Enter'&&e.key!==' '){return;}
    var el=document.activeElement;
    if(el&&el.classList&&el.classList.contains('note')){e.preventDefault();toggle(el);}
  });
})();
"""


# ---------------------------------------------------------------- inline rendering

# Numbers: integers, thousands separators, decimals, scientific notation, percent signs;
# only counts as an annotation when followed (optionally after one space) by parentheses.
NUM_NOTE_RE = re.compile(
    r"(?P<num>[0-9][0-9,]*(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?%?)"
    r"(?P<sp> ?)\((?P<body>[^()]*)\)"
)
CODE_RE = re.compile(r"`([^`]+)`")
URL_RE = re.compile(r"https?://[^\s\x00<>\"'（）「」，。、；]+")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.S)
SLOT_RE = re.compile(r"\x00(\d+)\x00")


def render_inline(text, notes=True):
    """Render a chunk of inline text to HTML.

    First replace the spots that become tags with placeholders, escape the whole chunk,
    then swap the placeholders back for tags. This way < > & " in the body text are
    always escaped, and tags are never escaped.
    """
    slots = []

    def put(kind, payload=None):
        slots.append((kind, payload))
        return "\x00%d\x00" % (len(slots) - 1)

    text = CODE_RE.sub(lambda m: put("code", m.group(1)), text)
    text = URL_RE.sub(lambda m: put("url", m.group(0)), text)
    text = BOLD_RE.sub(
        lambda m: put("bopen") + m.group(1) + put("bclose"), text
    )
    if notes:
        text = NUM_NOTE_RE.sub(
            lambda m: m.group("num")
            + m.group("sp")
            + put("nopen")
            + "("
            + m.group("body")
            + ")"
            + put("nclose"),
            text,
        )

    out = html.escape(text, quote=True)

    def restore(m):
        kind, payload = slots[int(m.group(1))]
        if kind == "code":
            return "<code>%s</code>" % html.escape(payload, quote=True)
        if kind == "url":
            esc = html.escape(payload, quote=True)
            return '<a href="%s" rel="noreferrer">%s</a>' % (esc, esc)
        if kind == "bopen":
            return "<strong>"
        if kind == "bclose":
            return "</strong>"
        if kind == "nopen":
            return '<span class="note" role="button" tabindex="0"><span class="note-body">'
        if kind == "nclose":
            return "</span></span>"
        raise AssertionError("unknown placeholder type: %r" % (kind,))

    return SLOT_RE.sub(restore, out)


# ---------------------------------------------------------------- block parsing

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
HR_RE = re.compile(r"^-{3,}$")
OL_RE = re.compile(r"^(\d+)\.\s+(.*)$")
UL_RE = re.compile(r"^[-*+]\s+(.*)$")
DELIM_CELL_RE = re.compile(r"^:?-{1,}:?$")


def split_row(line):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def is_delim_row(cells):
    return bool(cells) and all(DELIM_CELL_RE.match(c) for c in cells)


def starts_block(s):
    """Whether this line is the start of a different kind of block (used to end a paragraph)."""
    if s == "":
        return True
    if s.startswith(FENCE) or s.startswith("|"):
        return True
    if HEADING_RE.match(s) or HR_RE.match(s):
        return True
    if OL_RE.match(s) or UL_RE.match(s):
        return True
    return False


def join_para(lines):
    """Join a paragraph's multiple lines: insert a space only when both sides are ASCII, not between Chinese characters."""
    out = ""
    for piece in lines:
        if out and out[-1].isascii() and piece[:1].isascii():
            out += " "
        out += piece
    return out


def parse_blocks(lines):
    blocks = []
    i, n = 0, len(lines)
    while i < n:
        s = lines[i].strip()
        if s.startswith(FENCE):
            i += 1
            body = []
            while i < n and not lines[i].strip().startswith(FENCE):
                body.append(lines[i])
                i += 1
            i += 1  # the closing fence line
            blocks.append({"kind": "code", "lines": body})
            continue
        if s == "":
            i += 1
            continue
        m = HEADING_RE.match(s)
        if m:
            blocks.append(
                {"kind": "heading", "level": len(m.group(1)), "text": m.group(2).strip()}
            )
            i += 1
            continue
        if HR_RE.match(s):
            blocks.append({"kind": "hr"})
            i += 1
            continue
        if s.startswith("|"):
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(split_row(lines[i]))
                i += 1
            header, body = None, rows
            if len(rows) >= 2 and is_delim_row(rows[1]):
                header, body = rows[0], rows[2:]
            blocks.append({"kind": "table", "header": header, "rows": body})
            continue
        if OL_RE.match(s) or UL_RE.match(s):
            ordered = bool(OL_RE.match(s))
            items = []
            while i < n:
                t = lines[i].strip()
                m_ol, m_ul = OL_RE.match(t), UL_RE.match(t)
                if ordered and m_ol:
                    items.append(m_ol.group(2))
                elif (not ordered) and m_ul and not HR_RE.match(t):
                    items.append(m_ul.group(1))
                else:
                    break
                i += 1
            blocks.append({"kind": "list", "ordered": ordered, "items": items})
            continue
        para = []
        while i < n and not starts_block(lines[i].strip()):
            para.append(lines[i].strip())
            i += 1
        blocks.append({"kind": "para", "text": join_para(para)})
    return blocks


# ---------------------------------------------------------------- collapse grouping


def fold_label(text):
    """If the paragraph starts with "tag:", return that tag; otherwise return an empty string."""
    for label in FOLD_LABELS:
        if text.startswith(label + ":"):
            return label
    return ""


def is_stop_para(text):
    return any(text.startswith(p) for p in STOP_PREFIXES)


def group_folds(blocks):
    """Fold a paragraph in a ### section that starts with one of the three tags, along with the block right after it, into details."""
    out = []
    i, n = 0, len(blocks)
    in_h3 = False
    while i < n:
        b = blocks[i]
        if b["kind"] == "heading":
            in_h3 = b["level"] == 3
            out.append(b)
            i += 1
            continue
        label = fold_label(b["text"]) if b["kind"] == "para" else ""
        if in_h3 and label:
            head = dict(b)
            head["text"] = b["text"][len(label):]  # the tag stays only in summary
            group = [head]
            i += 1
            while i < n:
                nb = blocks[i]
                if nb["kind"] in ("heading", "table", "hr"):
                    break
                if nb["kind"] == "para" and (
                    is_stop_para(nb["text"]) or fold_label(nb["text"])
                ):
                    break
                group.append(nb)
                i += 1
            out.append({"kind": "fold", "summary": label, "blocks": group})
            continue
        out.append(b)
        i += 1
    return out


# ---------------------------------------------------------------- block rendering


def render_block(b, indent=""):
    k = b["kind"]
    if k == "heading":
        lv = b["level"]
        return "%s<h%d>%s</h%d>" % (indent, lv, render_inline(b["text"], notes=False), lv)
    if k == "para":
        return "%s<p>%s</p>" % (indent, render_inline(b["text"]))
    if k == "code":
        body = "\n".join(html.escape(x, quote=True) for x in b["lines"])
        return '%s<pre class="code"><code>%s</code></pre>' % (indent, body)
    if k == "list":
        tag = "ol" if b["ordered"] else "ul"
        items = "\n".join(
            "%s  <li>%s</li>" % (indent, render_inline(x)) for x in b["items"]
        )
        return "%s<%s>\n%s\n%s</%s>" % (indent, tag, items, indent, tag)
    if k == "table":
        parts = ['%s<div class="table-wrap">' % indent, "%s  <table>" % indent]
        if b["header"] is not None:
            cells = "".join(
                "<th>%s</th>" % render_inline(c, notes=False) for c in b["header"]
            )
            parts.append("%s    <thead><tr>%s</tr></thead>" % (indent, cells))
        parts.append("%s    <tbody>" % indent)
        for row in b["rows"]:
            cells = "".join(
                "<td>%s</td>" % render_inline(c, notes=False) for c in row
            )
            parts.append("%s      <tr>%s</tr>" % (indent, cells))
        parts.append("%s    </tbody>" % indent)
        parts.append("%s  </table>" % indent)
        parts.append("%s</div>" % indent)
        return "\n".join(parts)
    if k == "fold":
        inner = "\n".join(render_block(x, indent + "    ") for x in b["blocks"])
        return (
            '%s<details class="fold">\n'
            "%s  <summary>%s</summary>\n"
            '%s  <div class="fold-body">\n%s\n%s  </div>\n'
            "%s</details>"
        ) % (
            indent,
            indent,
            html.escape(b["summary"], quote=True),
            indent,
            inner,
            indent,
            indent,
        )
    if k == "hr":
        return '%s<div class="band"></div>' % indent
    raise AssertionError("unknown block type: %r" % (k,))


def render_document(blocks):
    """Everything before the first horizontal rule is the top half; from the rule to the end of the text is the bottom half, and the bottom half is wrapped in one container."""
    split = None
    for idx, b in enumerate(blocks):
        if b["kind"] == "hr":
            split = idx
            break
    if split is None:
        upper, lower = blocks, []
    else:
        upper, lower = blocks[:split], blocks[split:]

    out = []
    out.append("<title>%s</title>" % html.escape(PAGE_TITLE, quote=True))
    out.append("<style>%s</style>" % CSS)
    out.append('<div class="doc">')
    for b in upper:
        out.append(render_block(b, "  "))
    if lower:
        out.append('  <section class="verdict">')
        for b in lower:
            out.append(render_block(b, "    "))
        out.append("  </section>")
    out.append("</div>")
    out.append("<script>%s</script>" % JS)
    return "\n".join(out) + "\n"


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: python3 md2html.py <input.md> <output.html>\n")
        return 2
    with open(argv[1], "r", encoding="utf-8") as fh:
        src = fh.read()
    blocks = group_folds(parse_blocks(src.split("\n")))
    with open(argv[2], "w", encoding="utf-8") as fh:
        fh.write(render_document(blocks))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
