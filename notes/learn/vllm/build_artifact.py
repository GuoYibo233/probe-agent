#!/usr/bin/env python3
"""Render one lesson into a single publishable artifact file.

Why this is needed: the artifact shell itself provides `<!doctype html><head>...</head><body>`,
and CSP blocks every external request -- the lesson page's links to `../assets/lesson.css` and
`../assets/quiz.js` cannot be fetched once published. So the published version must be a
self-contained fragment with everything inlined and no document shell.

This is a **deterministic converter**: the lesson page and the shared files are the single
source of truth, and the published version is generated fresh from them every time, so the
two never diverge. Hand-editing the output means it gets overwritten on the next rerun.

It does four things, and not a fifth (it never changes a single character of the body text):
  1. Strip the doctype / html / head / body shell, keep only <title> and the body
  2. <link rel=stylesheet> -> inline <style>; <script src> -> inline <script>
  3. <a class="local"> -> <span class="local"> (local files cannot be linked to from the
     published page, so it degrades to plain text)
  4. Exit self-check: doctype / body tag / relative paths / external-linked resources --
     exit 2 if even one is found

Usage:
  python3 run.py build-lesson-artifact --lesson learn/vllm/lessons/0001-*.html
  # By default the output is written to <name>.artifact.html in the same directory; --out changes it
  # --check only verifies whether an existing output is in sync with the source (writes no file);
  # exits 3 if out of sync
"""

import argparse
import re
import sys
from pathlib import Path

LINK_RE = re.compile(r'[ \t]*<link\b[^>]*rel=["\']stylesheet["\'][^>]*>[ \t]*\n?', re.I)
HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.I)
SCRIPT_RE = re.compile(r'[ \t]*<script\b[^>]*\bsrc=["\']([^"\']+)["\'][^>]*>\s*</script>[ \t]*\n?', re.I)
TITLE_RE = re.compile(r'<title>(.*?)</title>', re.I | re.S)
BODY_RE = re.compile(r'<body[^>]*>(.*)</body>', re.I | re.S)
LOCAL_A_RE = re.compile(r'<a class="local" href="[^"]*">(.*?)</a>', re.I | re.S)

BAD_OUT = [
    ('<!doctype', 'doctype not stripped'),
    ('<html', 'html tag not stripped'),
    ('<head', 'head tag not stripped'),
    ('<body', 'body tag not stripped'),
    ('href="../', 'still has relative-path links'),
    ('src="../', 'still has relative-path resources'),
    ('rel="stylesheet"', 'still has an external stylesheet link'),
]


def die(msg, code=2):
    print(f"build_artifact: ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def render(lesson: Path) -> str:
    src = lesson.read_text(encoding="utf-8")
    base = lesson.parent

    m = TITLE_RE.search(src)
    if not m:
        die(f"{lesson} has no <title>, the artifact's name depends on it")
    title = m.group(1).strip()

    m = BODY_RE.search(src)
    if not m:
        die(f"{lesson} has no <body>...</body>")
    body = m.group(1)

    def resolve(rel, kind):
        p = (base / rel).resolve()
        if not p.exists():
            die(f"{kind} does not exist: {p}")
        return p

    head = src[: src.lower().find("<body")]
    css = [resolve(HREF_RE.search(mo.group(0)).group(1), "stylesheet")
           for mo in LINK_RE.finditer(head)]

    js = [resolve(mo.group(1), "script") for mo in SCRIPT_RE.finditer(body)]
    body = SCRIPT_RE.sub("", body)                                  # Strip the external-linked script tag
    body = LOCAL_A_RE.sub(r'<span class="local">\1</span>', body)   # Downgrade the local link

    if not css:
        die("not a single stylesheet got inlined, publishing this would ship bare HTML")

    out = [f"<title>{title}</title>", ""]
    for p in css:
        out += [f"<!-- inlined from {p.name} (single source of truth, do not edit here) -->",
                "<style>", p.read_text(encoding="utf-8").rstrip(), "</style>", ""]
    out += [body.strip(), ""]
    for p in js:
        out += [f"<!-- inlined from {p.name} -->",
                "<script>", p.read_text(encoding="utf-8").rstrip(), "</script>"]
    return "\n".join(out) + "\n"


def selfcheck(text: str):
    low = text.lower()
    bad = [why for needle, why in BAD_OUT if needle in low]
    if bad:
        die("artifact self-check failed:" + ";".join(bad))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lesson", required=True, help="lesson page html (single source of truth)")
    ap.add_argument("--out", default=None, help="artifact output path, defaults to <name>.artifact.html")
    ap.add_argument("--check", action="store_true",
                    help="only check whether the existing artifact is in sync with the source, write no files")
    a = ap.parse_args()

    lesson = Path(a.lesson).resolve()
    if not lesson.exists():
        die(f"lesson page does not exist: {lesson}")
    out = Path(a.out).resolve() if a.out else \
        lesson.parent / (lesson.stem + ".artifact.html")

    text = render(lesson)
    selfcheck(text)

    if a.check:
        if not out.exists():
            die(f"artifact does not exist yet: {out}", 3)
        if out.read_text(encoding="utf-8") != text:
            die(f"artifact out of sync with source, rerun build-lesson-artifact: {out}", 3)
        print(f"build_artifact: synced {out}")
        return

    out.write_text(text, encoding="utf-8")
    print(f"build_artifact: {lesson.name} + {len(text.splitlines())} lines inlined -> {out}")


if __name__ == "__main__":
    main()
