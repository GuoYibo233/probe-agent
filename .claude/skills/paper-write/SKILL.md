---
name: paper-write
description: >-
  The sole entry point for paper writing and LaTeX engineering in new1. Covers the full
  drafting/revision/compile/submission-checkup workflow: the official acl-style-files
  template, the latexmk compile gate (compile after every edit), the structural checkup
  (cite/ref/figure-file/environment pairing), the number-provenance hard rule (every
  experiment number tags a run_id), the protected-block convention, the pre-submission
  desk-reject self-check. Invoke whenever Dungeon♂Master says "latex", or any
  paper-writing work starts in new1. Chinese triggers: "写论文" / "改论文" / "编译一下论文" / "投稿检查" /
  "写 intro/method/experiment" / "体检论文".
---

# paper-write: new1 paper-writing workflow

Division of labor settled up front: this skill only manages the **mechanical layer** (template/compile/checks/provenance); the
**writing-style layer** belongs to humanizer-gyb (read the skill in full before drafting body text), the
**formatting-rules body** lives in `paper/FORMATTING.md` (the ACLPUB cross-reference table, read the relevant section
before writing), and the **section structure** follows `references/writing-structure.md` (intro's seven questions, the
two reviewer red lines, the related-work paragraph template — go through it once before writing the intro/related work).

## 0. Orient (do this every time you enter)

1. The paper's source files live under `paper/`; the template is fixed at `paper/acl-style-files/` (the official
   clone, not checked into git). Starting the first paper: copy `acl_latex.tex`, `acl.sty`, `acl_natbib.bst`,
   `custom.bib` into `paper/<paper-name>/` as the working directory; the template directory itself stays untouched.
2. Find the main tex file (the one with `\documentclass`), scan for the list of `%%% PROTECTED BEGIN/END` protected blocks.
3. Report: the main file / bib / protected-block count, then start work.

## 1. Hard rules (non-negotiable)

- **Number provenance**: every experiment number in the paper must be traceable to a run_id in `jobs/runs.jsonl`.
  How: inside a table/figure environment that contains numbers, add a line `% source: run_id=<id>` (can be
  multiple). check_paper.py soft-warns on a numeric table missing this annotation. **Hand-filling a number with
  no traceable run_id is an incident.**
- **Protected blocks**: content between `%%% PROTECTED BEGIN <description>` … `%%% PROTECTED END` (including
  blank-line comments) is never changed, touched, or reordered. When the user asks to change what's inside:
  point out the location, give suggested code, and let the user remove the marker themselves. Never delete the
  marker on the user's behalf to work around this.
- **acl.sty / .bst and other template files count as protected blocks**: solve formatting problems in your own
  tex file, don't change the style files.
- **Soft warnings never hard-block**: every check only reports, never blocks; whether to act on it is for the
  user/main conversation to judge (the one exception: a compile failure must be fixed before touching any other
  file — see §2).

## 2. Revision loop (every batch of edits goes through this)

```
Edit .tex → bash .claude/skills/paper-write/scripts/build.sh <main.tex>
        → fails: fix the compile error first (the script already extracts the error line + context); don't touch other files until it's fixed
        → succeeds: look at the Overfull/undefined warnings, handle the obvious ones while you're there
→ python3 .claude/skills/paper-write/scripts/check_paper.py <main.tex>
        → judge each warning by hand (structure/figure files/TODOs/provenance)
```

build.sh uses latexmk (it runs bibtex and extra passes automatically); never hand-assemble a pdflatex sequence.

## 3. Sourcing discipline while writing

- Need a number: look it up in `jobs/RESULTS.md` / `jobs/runs.jsonl` first to get the run_id and the value, and add a
  source comment to the table.
- Prefer building tables from existing artifacts; table styling follows FORMATTING.md §7 (booktabs, readable in
  grayscale, caption conventions).
- Citing literature: verify first (paper-verifier / fetch the abstract yourself — per the literature-judgment
  memory hard rule), and give bib entries a DOI wherever possible (FORMATTING.md §6).

## 4. Pre-submission checkup (must run before every deadline)

```
bash  scripts/build.sh <main.tex>                       # clean compile
python3 scripts/check_paper.py <main.tex> --anon --page-limit 8   # anonymized review version, long paper
```

Then go through `paper/FORMATTING.md` §10's desk-reject checklist item by item, focusing on: A4, fonts fully
embedded (pdffonts), line numbers present / Acknowledgments removed / anonymized in the review version (appendix
included), a Limitations section exists, body page count (the script only reports the total page count; the
boundary between body and references is checked by eye).

## 5. Wrap-up

- Staged draft → git commit (the paper's tex is an engineering asset, checked in; the PDF and compile
  intermediates are not).
- Structural writing decisions (e.g. cutting a section, changing the main narrative) → add a `notes/TIMELINE.md` entry,
  with the same weight as an experiment decision.
