#!/usr/bin/env python3
"""论文体检器：结构完整性 + 数字溯源 + 投稿前物理检查。全部软告警，不拦截。

用法:
    python check_paper.py main.tex                     # 结构检查
    python check_paper.py main.tex --anon              # + 匿名化检查（审稿版）
    python check_paper.py main.tex --page-limit 8      # + 页数对照（需已编译出 PDF）

检查项:
  结构  : \\begin/\\end 配对、\\ref->\\label、\\cite->bib key、\\includegraphics 文件存在
  卫生  : TODO/FIXME/TBD/XXX 残留（注释行除外）
  溯源  : 含数字的 table 环境缺 "% source: run_id=..." 注释 -> 告警（项目铁律：数字可追 run_id）
  匿名  : \\author 真名、GitHub/机构 URL、Acknowledgments 节、self-citation 措辞
  物理  : pdfinfo 页数 vs 限制、pdffonts 字体嵌入（有 PDF 才查）

退出码: 0 无告警；1 有告警（软性，供脚本串联，不代表必须停下）。
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

WARNINGS: list[str] = []


def warn(cat: str, msg: str) -> None:
    WARNINGS.append(f"[{cat}] {msg}")


def strip_comments(text: str) -> str:
    # 去掉 % 注释（保留 \% 转义）；verbatim/lstlisting 里的示例代码不参与任何检查
    text = re.sub(r"\\begin\{(verbatim\*?|lstlisting)\}.*?\\end\{\1\}", "", text, flags=re.DOTALL)
    text = re.sub(r"\\verb(.)((?!\1).)*\1", "", text)
    return re.sub(r"(?<!\\)%.*$", "", text, flags=re.MULTILINE)


def gather_tex(main: Path) -> dict[Path, str]:
    """收集主文件及其 \\input/\\include 的所有 .tex，返回 {路径: 原文}。"""
    files: dict[Path, str] = {}
    queue = [main]
    while queue:
        p = queue.pop()
        if p in files or not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        files[p] = text
        for m in re.finditer(r"\\(?:input|include)\{([^}]+)\}", strip_comments(text)):
            child = m.group(1)
            if not child.endswith(".tex"):
                child += ".tex"
            queue.append((main.parent / child).resolve())
    return files


def check_env_pairing(files: dict[Path, str]) -> None:
    for path, text in files.items():
        body = strip_comments(text)
        begins: dict[str, int] = {}
        ends: dict[str, int] = {}
        for m in re.finditer(r"\\begin\{(\w+\*?)\}", body):
            begins[m.group(1)] = begins.get(m.group(1), 0) + 1
        for m in re.finditer(r"\\end\{(\w+\*?)\}", body):
            ends[m.group(1)] = ends.get(m.group(1), 0) + 1
        for env in sorted(set(begins) | set(ends)):
            if begins.get(env, 0) != ends.get(env, 0):
                warn("env", f"{path.name}: \\begin{{{env}}} x{begins.get(env,0)} vs \\end{{{env}}} x{ends.get(env,0)}")


def check_labels_refs(body: str) -> None:
    labels = set(re.findall(r"\\label\{([^}]+)\}", body))
    refs: set[str] = set()
    for m in re.finditer(r"\\(?:ref|eqref|pageref|autoref|cref|Cref)\{([^}]+)\}", body):
        refs.update(k.strip() for k in m.group(1).split(","))
    for k in sorted(refs - labels):
        warn("ref", f"\\ref{{{k}}} 无对应 \\label")


def bib_keys(main: Path, body: str) -> set[str] | None:
    """找 \\bibliography{...} 指向的 .bib，解析全部条目 key。找不到返回 None。"""
    keys: set[str] = set()
    found = False
    for m in re.finditer(r"\\(?:bibliography|addbibresource)\{([^}]+)\}", body):
        for name in m.group(1).split(","):
            name = name.strip()
            if not name.endswith(".bib"):
                name += ".bib"
            p = (main.parent / name).resolve()
            if p.exists():
                found = True
                bib = p.read_text(encoding="utf-8", errors="replace")
                keys.update(re.findall(r"@\w+\s*\{\s*([^,\s]+)\s*,", bib))
    return keys if found else None


def check_cites(main: Path, body: str) -> None:
    keys = bib_keys(main, body)
    if keys is None:
        warn("cite", "未找到 .bib 文件，跳过 cite 检查")
        return
    cites: set[str] = set()
    for m in re.finditer(r"\\[cC]ite[a-zA-Z]*(?:\[[^\]]*\])*\{([^}]+)\}", body):
        cites.update(k.strip() for k in m.group(1).split(","))
    for k in sorted(cites - keys):
        warn("cite", f"\\cite{{{k}}} 在 .bib 中不存在")


def check_graphics(main: Path, body: str) -> None:
    gpaths = [main.parent]
    for m in re.finditer(r"\\graphicspath\{((?:\{[^}]*\})+)\}", body):
        gpaths += [(main.parent / d).resolve() for d in re.findall(r"\{([^}]*)\}", m.group(1))]
    exts = ["", ".pdf", ".png", ".jpg", ".jpeg", ".eps"]
    for m in re.finditer(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", body):
        name = m.group(1)
        if any((d / (name + e)).exists() for d in gpaths for e in exts):
            continue
        # TEXMF 树里的图（如 mwe 的 example-image-*）用 kpsewhich 兜底
        in_texmf = any(
            subprocess.run(["kpsewhich", name + e], capture_output=True, text=True).stdout.strip()
            for e in exts if e
        )
        if not in_texmf:
            warn("figure", f"\\includegraphics{{{name}}} 文件不存在")


def check_todos(files: dict[Path, str]) -> None:
    for path, text in files.items():
        for i, line in enumerate(text.splitlines(), 1):
            code = re.sub(r"(?<!\\)%.*$", "", line)
            for mark in ("TODO", "FIXME", "TBD", "XXX"):
                if mark in code:
                    warn("todo", f"{path.name}:{i}: {line.strip()[:70]}")


def check_provenance(files: dict[Path, str]) -> None:
    """table 环境含数字但整块无 'source: run_id' 注释 -> 告警。"""
    for path, text in files.items():
        for m in re.finditer(r"\\begin\{table\*?\}.*?\\end\{table\*?\}", text, re.DOTALL):
            block = m.group(0)
            has_numbers = bool(re.search(r"\d+\.\d+", strip_comments(block)))
            has_source = bool(re.search(r"%.*source:.*run_id", block))
            if has_numbers and not has_source:
                line = text[: m.start()].count("\n") + 1
                warn("provenance", f"{path.name}:{line}: table 含数字但无 '% source: run_id=...' 注释")


ANON_PATTERNS = [
    (r"github\.com/(?!anonymous)[\w-]+", "GitHub 链接"),
    (r"our (?:previous|prior|earlier) (?:work|paper|study)", "self-citation 措辞"),
    (r"\\section\*?\{Acknowledg", "Acknowledgments 节（审稿版必须删）"),
]


def check_anon(body: str) -> None:
    m = re.search(r"\\author\{(.{0,120})", body, re.DOTALL)
    if m and not re.search(r"anonymous", m.group(1), re.IGNORECASE):
        warn("anon", f"\\author 疑似真名: {m.group(1)[:60].strip()!r}")
    for pat, desc in ANON_PATTERNS:
        hit = re.search(pat, body, re.IGNORECASE)
        if hit:
            warn("anon", f"{desc}: {hit.group(0)[:60]}")


def check_pdf(main: Path, page_limit: int | None) -> None:
    pdf = main.with_suffix(".pdf")
    if not pdf.exists():
        warn("pdf", f"{pdf.name} 不存在，先编译再做物理检查")
        return
    info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
    m = re.search(r"Pages:\s+(\d+)", info)
    if m:
        pages = int(m.group(1))
        note = f"（限制 {page_limit}，正文页数需人工确认——references/appendix 不计入）" if page_limit else ""
        print(f"  PDF 总页数: {pages} {note}")
        if page_limit and pages > page_limit:
            warn("pdf", f"总页数 {pages} 超过 {page_limit}——若正文部分也超限即 desk reject")
    fonts = subprocess.run(["pdffonts", str(pdf)], capture_output=True, text=True).stdout
    for line in fonts.splitlines()[2:]:
        cols = line.split()
        if len(cols) >= 5 and cols[-5] == "no":  # emb 列
            warn("pdf", f"字体未嵌入: {line[:60]}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("tex")
    ap.add_argument("--anon", action="store_true", help="匿名化检查（审稿版）")
    ap.add_argument("--page-limit", type=int, default=None)
    args = ap.parse_args()

    main_tex = Path(args.tex).resolve()
    files = gather_tex(main_tex)
    body = strip_comments("\n".join(files.values()))
    print(f"检查 {main_tex.name}（含 {len(files)} 个 tex 文件）")

    check_env_pairing(files)
    check_labels_refs(body)
    check_cites(main_tex, body)
    check_graphics(main_tex, body)
    check_todos(files)
    check_provenance(files)
    if args.anon:
        check_anon(body)
    check_pdf(main_tex, args.page_limit)

    if WARNINGS:
        print(f"\n告警 {len(WARNINGS)} 条（软告警，逐条人工判断）:")
        for w in WARNINGS:
            print(f"  {w}")
        sys.exit(1)
    print("全部检查通过")
    sys.exit(0)


if __name__ == "__main__":
    main()
