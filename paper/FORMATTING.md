# ACL 论文格式规则（本地对照表）

> 来源：https://acl-org.github.io/ACLPUB/formatting.html （抓取于 2026-07-29）
> 官方模板：https://github.com/acl-org/acl-style-files （强烈建议直接用官方 LaTeX style files，下面大部分规则模板已自动满足）
> 注意：具体会议/ARR 的 call for papers 可能覆盖个别条目（尤其页数与补充材料），投稿前以当期 CFP 为准。

## 1. 页数限制

| 类型 | 审稿版 | 终稿版 |
|---|---|---|
| Long paper | 正文 ≤ 8 页 | 正文 ≤ 9 页 |
| Short paper | 正文 ≤ 4 页 | 正文 ≤ 5 页 |

- References 不限页数；终稿的 acknowledgments 也不计页。
- 所有图表必须算在正文页数内。
- Limitations / Ethical Considerations 不计页数（见 §8）。

## 2. 文件与页面

- 只收 **PDF**；纸张 **A4**（21 × 29.7 cm）。
- **所有字体必须嵌入**（树图、特殊符号、亚洲文字最容易漏）。
  自查命令：`pdffonts mypaper.pdf`，"emb" 列必须全是 yes。
- 四边距 2.5 cm；双栏排版，栏宽 7.7 cm，栏高 24.7 cm，栏间距 0.6 cm。
- 审稿版必须带行号（ruler）+ 页码；终稿版两者都必须去掉。

## 3. 字号（Times Roman）

| 元素 | 字号 | 样式 |
|---|---|---|
| 标题 | 15 pt | bold |
| 作者名 | 12 pt | bold |
| 作者单位 | 12 pt | regular |
| Abstract 标题 / 一级节标题 | 12 pt | bold |
| 二级节标题 | 11 pt | bold |
| 正文 | 11 pt | regular |
| 图表 caption / 摘要正文 / 参考文献 | 10 pt | regular |
| 脚注 | 9 pt | regular |

- 图表内文字尽量用正文字号（11 pt）；**在图表里挤小字压行距是 desk reject 理由**。

## 4. 标题、作者、摘要、元数据

- 标题 title case（非全大写，缩写词除外），居中跨双栏；标题里别塞 LaTeX 命令。
- 作者用全名，不缩写 given name；单位和 email 直接写，不放脚注。
- 摘要 ≤ **200 词**，两侧各内缩 0.6 cm。
- 投稿系统元数据里的标题/摘要只能是纯 Unicode 文本：
  `S$^3$` ✗ → `S³` ✓；`$\textit{X}$` ✗ → `X` ✓；emoji 可以用。
- 标题/作者信息必须与投稿系统里填的完全一致。

## 5. 正文与引用

- 节编号用阿拉伯数字（1, 2, …；小节 6.1 式）；段落首行缩进 0.4 cm（节首段除外）。
- 引用格式：`(Gusfield, 1997)` / `Gusfield (1997)` / `Aho and Ullman (1972)` /
  三人及以上 `Chandra et al. (1981)` / 并列 `(Gusfield, 1997; Aho and Ullman, 1972)`。
- 不要把完整 citation 当句子成分（尤其别当主语）。
- 超链接颜色深蓝 `#000099`，不加下划线不加框。
- 非拉丁文字必须给英文翻译 + 拉丁转写，如：παράδειγμα *paradeigma* 'example'。

## 6. References

- 不编号的 "References" 节，放在 appendix 之前；按第一作者字母序。
- **每条引用尽量带 DOI**；没有 DOI 就给 ACL Anthology 链接。
- 作者写全名不写缩写。样式参照 Computational Linguistics 或 APA 7th。

## 7. 图表

- 放在首次提及处附近，不要堆到文末；至少一栏宽。
- 用矢量图（PDF/EPS），别用低分辨率 GIF/JPEG。
- caption 编号连续（Figure 1: … / Table 1: …）；单行居中，多行左对齐。
- 建议灰度可读——别用"只靠颜色区分"的设计。

## 8. 特殊章节（顺序：结论 → Limitations → Ethics → Acknowledgments → References → Appendix）

- **Limitations：必写**，放结论之后、references 之前；不许塞新实验/新图/新分析；不计页数。
- Ethical Considerations：可选，同样不许塞新内容，不计页数。
- Acknowledgments：紧挨 references 之前，不编号，不计页数；**审稿版必须删掉**。
- Appendix：放 references 之后，按 Appendix A/B/C 编号并给有信息量的标题；
  也要双栏（大段公式推导可例外）；审稿版同样要匿名。
- 脚注放页底，9 pt，与正文之间有分隔线。

## 9. 补充材料

- 只放"非阅读性"材料：预处理细节、超参、代码、数据、伪代码、证明。
- **论文本身不得依赖补充材料才能读懂**；审稿人不负责审它。
- 滥用补充材料（把正文塞进去）可能直接被拒。审稿版补充材料同样要匿名。

## 10. Desk reject 清单（投稿前最后一遍）

- [ ] 页数超限？
- [ ] 纸张不是 A4？
- [ ] 字体没嵌入（`pdffonts` 查）？
- [ ] 图表里字号/行距被压缩？
- [ ] 有人眼不可见的文字（白字、超小字）？
- [ ] 审稿版：行号在、页码在、acknowledgments 删了、全文匿名（含 appendix 和补充材料）？
