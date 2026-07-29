---
name: show-knowledge-map
description: Render KNOWLEDGE_MAP.md as a published web page where colour encodes evidence tier (A = verified by me / B = agent-verified / quarantine / dead direction), so what is citable and what is not is readable at a glance. Redeploys to the same URL on every update. Invoke when the user wants to see, share, or review the knowledge map visually. 中文触发：把知识图做成网页 / 展示这个图 / 看一下 knowledge map / 渲染那张表 / 出个网页 / 更新那个网页 / 发布知识图。
version: 1.0.0
---

# show-knowledge-map

Renders `/home/y-guo/reproduce/new1/KNOWLEDGE_MAP.md` as an Artifact.

**The page has one job:** make the evidence tier of every claim visible without reading. The map exists because search summaries lie; the page exists so the user can see, in one glance, which parts survived verification and which did not.

## Procedure

1. **Load the `artifact-design` skill first** (mandatory before writing any Artifact page).
2. Read `KNOWLEDGE_MAP.md` in full. Do not summarize or re-verify — the map is already the verified layer. Rendering is a display job, not a research job. **If a claim looks wrong, do not silently fix it on the page** — report it and use `update-knowledge-map` instead. The page must never disagree with the map.
3. Write the HTML to the scratchpad directory, then publish with `Artifact`.
4. **Same file path every time** → same URL. Never mint a new URL for an update. If updating from a session that did not publish it, pass the existing URL via the `url` parameter (find it with `action: "list"`).

## Design contract

**Colour = provenance, and nothing else.** This is a page about which claims are trustworthy; the colour budget belongs entirely to that, not to decoration.

| Tier | Role |
|---|---|
| **A** — I verified the primary source | citable — the strongest state |
| **B** — agent-verified, unchecked | usable but must be re-fetched |
| **🚫 Quarantine** | never cite — includes proven confabulations |
| **☠ Dead direction** | do not write this |

Requirements:

- **Semantic colours are separate from any accent hue.** Four tiers = four distinct, legible states in both light and dark themes.
- **Verbatim quotes render as quotes**, visually distinct from commentary, in a monospace or otherwise marked face. The whole value of the map is that these are exact — the design must say so. Never render a translation as if it were the quote.
- **The quarantine section is not an appendix.** It is the most load-bearing part of the map — the record of how the map was attacked. Give it real weight on the page.
- **The dead-directions table must distinguish** "killed by evidence" (permanent) from "killed by an argument" (reopenable). This distinction was nearly lost once; the page must not lose it.
- **Every entry shows its date.** The field moves in weeks.
- Theme-aware via tokens at `:root`, redefined under `@media (prefers-color-scheme: dark)` **and** `:root[data-theme="dark"]` / `:root[data-theme="light"]`.
- Wide content (tables, long quotes) gets `overflow-x: auto` on its own container — the body never scrolls sideways.
- Self-contained: no external fonts, scripts, or images. CJK webfonts are megabytes — use a system CJK stack, never a CDN link (the CSP blocks it and the fallback is silent).

## Artifact parameters

- `favicon`: **🔗** — keep it stable across redeploys. Users find the tab by its icon; changing it reads as a different page.
- `description`: one sentence naming what the map is and that it is verified-only.
- `label`: something short and real, e.g. `added-flipflop`, not `v2`.

## Do not

- Do not add analysis, recommendations, or next steps to the page. The map is a record of what is known; interpretation belongs in conversation, where it can be argued with. A page renders claims — it should not quietly acquire opinions.
- Do not make it look finished when it is not. Open questions stay visibly open.
- Do not publish anything that is not in the map.
