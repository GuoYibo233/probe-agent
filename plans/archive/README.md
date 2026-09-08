# plans/archive

2026-09-08 归档。这里放的是已经收官或者被后来的文档取代的计划、报告和评审记录，
文件名不改，只是从 `plans/` 挪到 `plans/archive/`。

只增不改的账本（`TIMELINE.md`、`ops/runs.jsonl`）、冻结的设计源文档
（`plans/research-loop-parts/`，其中三份有冻结 commit 校验）、以及采集 manifest
和批次配置 JSON（`pipeline/collect/manifest_*.json`、`pipeline/configs/np821_gptoss.json`，
驱动器按文件字节记 sha1）里写的仍是旧路径 `plans/<文件名>`：看到旧路径就到这个目录找同名文件。
活文档和代码里的指向（run.py、MAP.md、DATA.md、METHOD.md、WORKPLAN.md、
research-loop 的 GLOSSARY 与 reviewer skill、pipeline 里的注释、`.scratch/kvshare-train/`）
已经改成新路径。

| 文件 | 归哪条线 | 为什么归档 |
|---|---|---|
| `2026-08-10-z1-plan.md`、`2026-08-10-z1-smoke-report.md` | z1 注入冒烟 | 冒烟已完成，结论录在 METHOD.md 的 R3 行 |
| `2026-08-16-research-loop-build-plan.md`、`2026-08-16-research-loop-next-steps.md` | research-loop v1 | 两份源文档已经拆成 `plans/research-loop-parts/` 的 22 份 part，part 里的行号引用指向这两份 |
| `2026-08-16-research-loop-plan-critiques.md`、`2026-08-16-research-loop-simulation-round1.md`、`-round2.md`、`2026-08-17-research-loop-usage-scenarios.md` | research-loop v1 | 审读意见与模拟原始结果，已经裁进 part 00 |
| `2026-08-21-research-loop-parts-review.md`、`2026-08-21-research-loop-parts-review-raw/`、`2026-08-21-research-loop-parts-fix.md`、`2026-08-21-review-findings.md` | research-loop parts 评审 | 08-21 那轮评审与修法，裁决已经落进 part 和 sync-inbox |
| `2026-08-18-ident3.md`、`2026-08-18-splice-replay.md` | 回放注入 | 两条线的代码已经落地并挂进 run.py，计划只剩历史用途 |
| `2026-08-21-lora-current-state.md` | np821 | 状态快照，被 08-26 的结果报告取代 |
| `2026-08-21-new-probe-training.md`、`2026-08-21-p1-collection-plan.md`、`2026-08-21-np821-plan.md` | p1 / np821 | 两批数据与训练都已收官，结果在 RESULTS.md 与 `2026-08-26-np821-results.md` |
| `2026-08-22-np821-exec-worklog.md`、`2026-08-26-np821-results.md`、`2026-08-26-hparam-survey.md` | np821 | np821 十二格收官后的执行日志、结果报告、超参调研；kvshare-train 这条线从 `plans/2026-08-28-plan.md` 起接手 |
