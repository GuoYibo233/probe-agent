#!/usr/bin/env python3
"""把一节课渲染成可发布的 artifact 单文件。

为什么需要它:artifact 的外壳自己提供 `<!doctype html><head>…</head><body>`,
而且 CSP 挡掉一切外部请求——课页链的 `../assets/lesson.css` 与 `../assets/quiz.js`
在发布后取不到。所以发布版必须是内联好的、没有文档外壳的片段。

这是**确定性转换器**:课页与共用件是唯一真源,发布版每次由它现生成,
两处内容不会分叉。手改产物 = 下次重跑被覆盖。

它做四件事,不做第五件(不改任何一个字的正文):
  1. 去掉 doctype / html / head / body 外壳,只留 <title> 与正文
  2. <link rel=stylesheet> -> 内联 <style>;<script src> -> 内联 <script>
  3. <a class="local"> -> <span class="local">(本地文件在发布页里链不到,降级成纯文本)
  4. 出口自检:doctype / body 标签 / 相对路径 / 外链资源,有一个就退 2

用法:
  python3 run.py build-lesson-artifact --lesson learn/vllm/lessons/0001-*.html
  # 产物默认写到同目录的 <名>.artifact.html;--out 可改
  # --check 只校验已有产物是否与源同步(不写文件),不同步退 3
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
    ('<!doctype', 'doctype 没去掉'),
    ('<html', 'html 标签没去掉'),
    ('<head', 'head 标签没去掉'),
    ('<body', 'body 标签没去掉'),
    ('href="../', '还有相对路径链接'),
    ('src="../', '还有相对路径资源'),
    ('rel="stylesheet"', '还有外链样式表'),
]


def die(msg, code=2):
    print(f"build_artifact: ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def render(lesson: Path) -> str:
    src = lesson.read_text(encoding="utf-8")
    base = lesson.parent

    m = TITLE_RE.search(src)
    if not m:
        die(f"{lesson} 里没有 <title>,artifact 靠它取名")
    title = m.group(1).strip()

    m = BODY_RE.search(src)
    if not m:
        die(f"{lesson} 里没有 <body>…</body>")
    body = m.group(1)

    def resolve(rel, kind):
        p = (base / rel).resolve()
        if not p.exists():
            die(f"{kind}不存在:{p}")
        return p

    head = src[: src.lower().find("<body")]
    css = [resolve(HREF_RE.search(mo.group(0)).group(1), "样式表")
           for mo in LINK_RE.finditer(head)]

    js = [resolve(mo.group(1), "脚本") for mo in SCRIPT_RE.finditer(body)]
    body = SCRIPT_RE.sub("", body)                                  # 摘掉外链脚本标签
    body = LOCAL_A_RE.sub(r'<span class="local">\1</span>', body)   # 本地链接降级

    if not css:
        die("一个样式表都没内联进来,发布出去会是裸 HTML")

    out = [f"<title>{title}</title>", ""]
    for p in css:
        out += [f"<!-- 内联自 {p.name}(唯一真源,勿在此处改) -->",
                "<style>", p.read_text(encoding="utf-8").rstrip(), "</style>", ""]
    out += [body.strip(), ""]
    for p in js:
        out += [f"<!-- 内联自 {p.name} -->",
                "<script>", p.read_text(encoding="utf-8").rstrip(), "</script>"]
    return "\n".join(out) + "\n"


def selfcheck(text: str):
    low = text.lower()
    bad = [why for needle, why in BAD_OUT if needle in low]
    if bad:
        die("产物自检没过:" + ";".join(bad))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lesson", required=True, help="课页 html(唯一真源)")
    ap.add_argument("--out", default=None, help="产物路径,默认 <名>.artifact.html")
    ap.add_argument("--check", action="store_true",
                    help="只校验已有产物是否与源同步,不写文件")
    a = ap.parse_args()

    lesson = Path(a.lesson).resolve()
    if not lesson.exists():
        die(f"课页不存在:{lesson}")
    out = Path(a.out).resolve() if a.out else \
        lesson.parent / (lesson.stem + ".artifact.html")

    text = render(lesson)
    selfcheck(text)

    if a.check:
        if not out.exists():
            die(f"产物还不存在:{out}", 3)
        if out.read_text(encoding="utf-8") != text:
            die(f"产物与源不同步,重跑 build-lesson-artifact:{out}", 3)
        print(f"build_artifact: 同步 {out}")
        return

    out.write_text(text, encoding="utf-8")
    print(f"build_artifact: {lesson.name} + {len(text.splitlines())} 行内联 -> {out}")


if __name__ == "__main__":
    main()
