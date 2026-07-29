---
name: update-knowledge-map
description: Add, promote, demote, or quarantine an entry in KNOWLEDGE_MAP.md — the verified-only research map for the agent memory / forgetting / multi-turn investigation. Enforces the three-tier evidence standard (A = I fetched the primary source and hold verbatim text; B = a subagent claims it verified; quarantine = unverified or confabulated), and maintains the dead-directions table and open-questions list. Invoke whenever a new paper is read, a claim is verified or falsified, a research direction dies, or an entry's evidence level changes. 中文触发：加到 knowledge map / 更新知识图 / 把这篇加进去 / 收录这篇 / 归档这篇论文 / 这条核实了 / 这条是假的 / 这个方向死了 / 划掉这个方向 / 进隔离区 / 升级成 A 级 / 更新那张表。
version: 1.0.0
---

# update-knowledge-map

Maintains `KNOWLEDGE_MAP.md` — a map that is worth something **only** because everything in it was verified against a primary source. One unverified entry that gets cited destroys the map's entire reason to exist.

Map location: `/home/y-guo/reproduce/new1/KNOWLEDGE_MAP.md`

## Why this skill exists (read this, it is not boilerplate)

During the 2026-07-15 investigation, the environment's **search-summary layer and subagent report layer both confabulated, at least three times**. The worst case:

> A subagent reported a verbatim quote from arXiv:2605.12087 claiming the paper discussed retraction. The paper was real. The subagent's *other* quotes from it verified exactly. But the retraction sentence **did not exist** — the words "retracted"/"retraction" appear nowhere in that paper. The fabrication was surgical: real paper, accurate framing, one invented sentence **inserted at exactly the point that carried the argument**.

Also caught: the same fabricated sentence ("dependency edges between capsules and derived artifacts") attributed to **two different papers** in two different searches; a claim that "influence provenance" was absent from MEMOREPAIR when it occurs 6 times; a paper titled *"When Should Long-Term Memories Be Forgotten by LLMs?"* that is actually a safety paper about sycophancy and leakage.

**The operational lesson: confabulation concentrates on the load-bearing sentence.** The more a quote matters to an argument, the more likely it is invented. So verification effort must scale with how much the claim carries — the opposite of the natural instinct to check the boring stuff.

## The three tiers

| Tier | Standard | Usable in a paper? |
|---|---|---|
| **A** | *I* fetched the arxiv abs / HTML / PDF / official page in this session and hold the **verbatim text** | Yes |
| **B** | A subagent claims it fetched and verified; I did not re-check | **Re-fetch before citing** |
| **🚫 Quarantine** | Unverified, source-blocked, contradicted, or proven confabulated | **Never** |

Nothing enters A on the strength of a search summary. Ever. Not even if the summary looks obviously right.

## Procedure

### 1. Determine the operation

- **New paper** → verify, then insert at A or B
- **Promote B→A** → I fetched primary myself; move it, keep the verbatim
- **Demote A→B / A→quarantine** → the quote didn't survive re-check
- **Quarantine → A/B** → previously-unverifiable claim now confirmed (this happens; check the quarantine list on every run)
- **Direction died** → add a row to *已确认死亡的方向* with cause + date
- **Open question resolved** → move the answer into the map, strike the question

### 2. Verify (the load-bearing part)

For anything entering **A**:

1. `WebFetch` the **primary** source. Prefer, in order: `arxiv.org/abs/<id>` → `arxiv.org/html/<id>v1` → the official site (e.g. `transformer-circuits.pub`) → raw GitHub. **`arxiv.org/pdf/` often returns a binary dump — use abs or html.**
2. Ask for **exact quotes, not paraphrase.** Explicitly instruct: *"Quote verbatim. Say explicitly if a claim is NOT present."*
3. **Ask whether the claim is absent**, not just whether it's present. Absence is what catches fabrication — "does the word 'retraction' appear anywhere" is the question that caught the worst one.
4. If a quote carries the argument, **verify it a second way** — different URL form, or a targeted grep prompt over the full text.
5. Record the quote **verbatim, in the original language**. Never translate into the map. Translation destroys the ability to re-verify.

Red flags that demand a second check:
- The quote is *exactly* what the argument needs
- The title promises what the argument needs (titles are rhetoric — see PersistBench)
- A subagent's other quotes verified (this is the *camouflage*, not the reassurance)
- The number is suspiciously round or suspiciously perfect

### 3. Record what the paper actually is

For each entry, capture — beyond the quote:

- **Type**: benchmark / method / system / critique / survey / position
- **What is given vs inferred** (this distinction killed several directions — MEME hand-crafts its graph, MEMOREPAIR assumes provenance)
- **What it explicitly does NOT do** — often more valuable than what it does. STALE's "only evaluates responses, not previously produced artifacts" was the load-bearing boundary.
- **Self-admitted limitations, quoted** — these are the strongest ammunition available. MEMOREPAIR's own Limitations section is worth more than any external critique.
- **Domain / model scale / N** — several "findings" turned out to be small-model or single-domain artifacts.

### 4. Maintain the dead-directions table

When a direction dies, record **cause and date**. And distinguish, explicitly:

- **Killed by evidence** — a paper exists that does it. Permanent.
- **Killed by an argument** — someone (often me) reasoned it was confounded/weak. **Mark these as reopenable.** The relevance→forgetting-resistance line was killed by my reasoning on day one, not by evidence, and that distinction was almost lost.

### 5. Maintain the open questions

Each open question needs: what would settle it, and **what it decides**. A question that decides nothing should not be on the list.

## Hard rules

1. **A search summary is never evidence.** Not for entry, not for promotion, not for quarantine release.
2. **Verbatim, original language, no translation** in the quote fields.
3. **Absence claims need a full-text check**, not an abstract read. "The paper doesn't mention X" from an abstract fetch means "the abstract doesn't mention X" — say that instead.
4. **Two independent reads failing to find something ≠ it doesn't exist.** It may be in an appendix. Record the reads, not the conclusion.
5. **Never delete a quarantine entry.** Quarantine is the record of how the map was attacked. Mark it resolved; keep the history.
6. **If a subagent supplied it, it is B — no matter how confident the subagent sounded.** Confidence correlates with nothing.
7. **Date every entry.** The field moves in weeks; a 2-month-old "nobody has done this" is not a fact.

## After updating

Report to the user:
- What moved and to which tier
- **Anything that got demoted or quarantined** — this is the most important line
- Whether any dead direction became reopenable, or any live direction died

If the user wants to see it, use the `show-knowledge-map` skill to render and publish.
