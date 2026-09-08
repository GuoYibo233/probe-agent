---
name: paper-write
description: new1 论文写作与 LaTeX 工程的唯一入口。覆盖起草/改稿/编译/投稿体检全流程：
  官方 acl-style-files 模板、latexmk 编译门禁（改完必编译）、结构体检（cite/ref/图文件/环境配对）、
  数字溯源铁律（每个实验数字标 run_id）、保护块约定、投稿前 desk-reject 自查。
  Invoke whenever Dungeon♂Master says "写论文"、"改论文"、"编译一下论文"、"投稿检查"、
  "写 intro/method/experiment"、"latex"、"体检论文"、or any paper-writing work starts in new1.
---

# paper-write：new1 论文写作流程

分工先说死：本 skill 只管**机械层**（模板/编译/检查/溯源）；**文风层**归
humanizer-gyb（写正文之前把 skill 全文读一遍），**格式规则本体**在
`paper/FORMATTING.md`（ACLPUB 对照表，写前先读一遍相关小节），
**章节结构**按 `references/writing-structure.md`（intro 七问、两条审稿红线、
related work 段落定式——写 intro/related work 前必过一遍）。

## 0. 定位（每次进入先做）

1. 论文源文件在 `paper/` 下；模板固定用 `paper/acl-style-files/`（官方 clone，不入 git）。
   首篇论文起步：把 `acl_latex.tex`、`acl.sty`、`acl_natbib.bst`、`custom.bib`
   拷到 `paper/<论文名>/` 作为工作目录，模板目录本身保持原样不动。
2. 找主 tex（含 `\documentclass`），扫一遍 `%%% PROTECTED BEGIN/END` 保护块清单。
3. 报告：主文件 / bib / 保护块数量，然后才动手。

## 1. 铁律（不可协商）

- **数字溯源**：论文里每一个实验数字都必须能追到 `ops/runs.jsonl` 的 run_id。
  落法：含数字的 table/figure 环境内加一行 `% source: run_id=<id>`（可多个）。
  check_paper.py 会对缺注释的数字表软告警。**手填一个查无 run_id 的数字 = 事故**。
- **保护块**：`%%% PROTECTED BEGIN <说明>` … `%%% PROTECTED END` 之间的内容
  （含空格注释）一律不改不动不重排。用户要求改其中内容时：指出位置，给建议
  代码，由用户自己解除标记。不得代删标记绕过。
- **acl.sty / .bst 等模板文件视同保护块**：格式问题在自己的 tex 里解决，不改样式文件。
- **软告警不硬拦**：所有检查只报告不阻塞，动不动手由用户/主对话判断
  （唯一例外：编译失败必须先修好才能继续改别的文件，见 §2）。

## 2. 改稿循环（每批编辑必走）

```
改 .tex → bash .claude/skills/paper-write/scripts/build.sh <main.tex>
        → 失败：先修编译错误（脚本已提取错误行+上下文），修好前不碰其他文件
        → 成功：看 Overfull/undefined 警告，顺手处理明显的
→ python3 .claude/skills/paper-write/scripts/check_paper.py <main.tex>
        → 逐条告警人工判断（结构/图文件/TODO/溯源）
```

build.sh 用 latexmk（会自动跑 bibtex 和补趟数），不手搓 pdflatex 序列。

## 3. 写作时的取数纪律

- 要写数字：先查 `RESULTS.md` / `ops/runs.jsonl` 拿 run_id 和数值，表格加 source 注释。
- 做表优先走已有产物；表格式样按 FORMATTING.md §7（booktabs、灰度可读、caption 规范）。
- 引用文献：先核实（paper-verifier / 亲自抓 abstract——记忆铁律 literature-judgment），
  bib 条目尽量带 DOI（FORMATTING.md §6）。

## 4. 投稿前体检（deadline 前必跑）

```
bash  scripts/build.sh <main.tex>                       # 干净编译
python3 scripts/check_paper.py <main.tex> --anon --page-limit 8   # 审稿版 long paper
```

再对照 `paper/FORMATTING.md` §10 desk-reject 清单逐项打勾，重点：
A4、字体全嵌入（pdffonts）、审稿版行号在/Acknowledgments 删/匿名（含 appendix）、
Limitations 节存在、正文页数（脚本只报总页数，正文/references 分界人工看）。

## 5. 收尾

- 阶段性成稿 → git commit（论文 tex 是工程资产，入库；PDF/编译中间产物不入）。
- 结构性写作决策（比如砍掉一节、换主线故事）→ 补 TIMELINE.md，与实验决策同权。
