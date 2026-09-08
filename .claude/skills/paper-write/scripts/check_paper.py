#!/usr/bin/env python3
"""Paper checkup tool: structural completeness + number traceability + pre-submission
physical checks. All soft warnings, nothing blocks.

Usage:
    python check_paper.py main.tex                     # structure check
    python check_paper.py main.tex --anon              # + anonymization check (review version)
    python check_paper.py main.tex --page-limit 8      # + page count check (needs a compiled PDF)

Checks:
  structure    : \\begin/\\end pairing, \\ref->\\label, \\cite->bib key, \\includegraphics file exists
  hygiene      : TODO/FIXME/TBD/XXX left over (comment lines excluded)
  traceability : a table environment with numbers but no "% source: run_id=..." comment
                 -> warning (project hard rule: every number must trace to a run_id)
  anonymity    : \\author real name, GitHub/institution URL, Acknowledgments section,
                 self-citation wording
  physical     : pdfinfo page count vs limit, pdffonts font embedding (checked only if a PDF exists)

Exit code: 0 no warnings; 1 has warnings (soft, for chaining scripts; does not mean it
must stop).
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
    # strip % comments (keep the \% escape); example code inside verbatim/lstlisting is
    # excluded from every check
    text = re.sub(r"\\begin\{(verbatim\*?|lstlisting)\}.*?\\end\{\1\}", "", text, flags=re.DOTALL)
    text = re.sub(r"\\verb(.)((?!\1).)*\1", "", text)
    return re.sub(r"(?<!\\)%.*$", "", text, flags=re.MULTILINE)


def gather_tex(main: Path) -> dict[Path, str]:
    """Collect all .tex files reachable from the main file via \\input/\\include, return {path: source text}."""
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
        warn("ref", f"\\ref{{{k}}} has no matching \\label")


def bib_keys(main: Path, body: str) -> set[str] | None:
    """Find the .bib file that \\bibliography{...} points to and parse all entry keys. Return None if not found."""
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
        warn("cite", "no .bib file found, skipping cite check")
        return
    cites: set[str] = set()
    for m in re.finditer(r"\\[cC]ite[a-zA-Z]*(?:\[[^\]]*\])*\{([^}]+)\}", body):
        cites.update(k.strip() for k in m.group(1).split(","))
    for k in sorted(cites - keys):
        warn("cite", f"\\cite{{{k}}} not found in .bib")


def check_graphics(main: Path, body: str) -> None:
    gpaths = [main.parent]
    for m in re.finditer(r"\\graphicspath\{((?:\{[^}]*\})+)\}", body):
        gpaths += [(main.parent / d).resolve() for d in re.findall(r"\{([^}]*)\}", m.group(1))]
    exts = ["", ".pdf", ".png", ".jpg", ".jpeg", ".eps"]
    for m in re.finditer(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", body):
        name = m.group(1)
        if any((d / (name + e)).exists() for d in gpaths for e in exts):
            continue
        # for figures inside the TEXMF tree (e.g. mwe's example-image-*), fall back to kpsewhich
        in_texmf = any(
            subprocess.run(["kpsewhich", name + e], capture_output=True, text=True).stdout.strip()
            for e in exts if e
        )
        if not in_texmf:
            warn("figure", f"\\includegraphics{{{name}}} file does not exist")


def check_todos(files: dict[Path, str]) -> None:
    for path, text in files.items():
        for i, line in enumerate(text.splitlines(), 1):
            code = re.sub(r"(?<!\\)%.*$", "", line)
            for mark in ("TODO", "FIXME", "TBD", "XXX"):
                if mark in code:
                    warn("todo", f"{path.name}:{i}: {line.strip()[:70]}")


def check_provenance(files: dict[Path, str]) -> None:
    """A table environment that contains numbers but has no 'source: run_id' comment anywhere in the block -> warning."""
    for path, text in files.items():
        for m in re.finditer(r"\\begin\{table\*?\}.*?\\end\{table\*?\}", text, re.DOTALL):
            block = m.group(0)
            has_numbers = bool(re.search(r"\d+\.\d+", strip_comments(block)))
            has_source = bool(re.search(r"%.*source:.*run_id", block))
            if has_numbers and not has_source:
                line = text[: m.start()].count("\n") + 1
                warn("provenance", f"{path.name}:{line}: table has numbers but no '% source: run_id=...' comment")


ANON_PATTERNS = [
    (r"github\.com/(?!anonymous)[\w-]+", "GitHub link"),
    (r"our (?:previous|prior|earlier) (?:work|paper|study)", "self-citation wording"),
    (r"\\section\*?\{Acknowledg", "Acknowledgments section (must be removed in the review version)"),
]


def check_anon(body: str) -> None:
    m = re.search(r"\\author\{(.{0,120})", body, re.DOTALL)
    if m and not re.search(r"anonymous", m.group(1), re.IGNORECASE):
        warn("anon", f"\\author looks like a real name: {m.group(1)[:60].strip()!r}")
    for pat, desc in ANON_PATTERNS:
        hit = re.search(pat, body, re.IGNORECASE)
        if hit:
            warn("anon", f"{desc}: {hit.group(0)[:60]}")


def check_pdf(main: Path, page_limit: int | None) -> None:
    pdf = main.with_suffix(".pdf")
    if not pdf.exists():
        warn("pdf", f"{pdf.name} does not exist; compile first, then run the physical check")
        return
    info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
    m = re.search(r"Pages:\s+(\d+)", info)
    if m:
        pages = int(m.group(1))
        note = f"(limit {page_limit}, body page count needs manual confirmation -- references/appendix do not count)" if page_limit else ""
        print(f"  PDF total pages: {pages} {note}")
        if page_limit and pages > page_limit:
            warn("pdf", f"total pages {pages} exceeds {page_limit} -- if the body section also exceeds it, that is a desk reject")
    fonts = subprocess.run(["pdffonts", str(pdf)], capture_output=True, text=True).stdout
    for line in fonts.splitlines()[2:]:
        cols = line.split()
        if len(cols) >= 5 and cols[-5] == "no":  # the emb column
            warn("pdf", f"font not embedded: {line[:60]}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("tex")
    ap.add_argument("--anon", action="store_true", help="anonymization check (review version)")
    ap.add_argument("--page-limit", type=int, default=None)
    args = ap.parse_args()

    main_tex = Path(args.tex).resolve()
    files = gather_tex(main_tex)
    body = strip_comments("\n".join(files.values()))
    print(f"checking {main_tex.name} (contains {len(files)} tex files)")

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
        print(f"\n{len(WARNINGS)} warnings (soft warnings, judge each one by hand):")
        for w in WARNINGS:
            print(f"  {w}")
        sys.exit(1)
    print("all checks passed")
    sys.exit(0)


if __name__ == "__main__":
    main()
