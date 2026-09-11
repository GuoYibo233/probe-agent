# plans/archive

2026-09-08 归档。这里放的是已经收官或者被后来的文档取代的计划、报告和评审记录，
文件名不改，只是从 `plans/` 挪到 `plans/archive/`。

只增不改的账本（`TIMELINE.md`、`ops/runs.jsonl`）、以及采集 manifest
和批次配置 JSON（`pipeline/collect/manifest_*.json`、`pipeline/configs/np821_gptoss.json`，
驱动器按文件字节记 sha1）里写的仍是旧路径 `plans/<文件名>`：看到旧路径就到这个目录找同名文件。
活文档和代码里的指向（run.py、MAP.md、DATA.md、METHOD.md、WORKPLAN.md、
pipeline 里的注释、`.scratch/kvshare-train/`）已经改成新路径。

The research-loop lineage that used to sit in this directory (the six
2026-08-16/17 v1 documents, the 2026-08-21 parts-review items, and
`2026-08-21-review-findings.md`) moved to
`/home/y-guo/research-loop/plans/archive/` when research-loop split out into
its own repository on 2026-09-12.

2026-09-12 起这个目录定名"远古记忆"（gyb 裁决）：gyb 明说"查远古记忆"或者
点名某份归档文件的时候才读，其余时候不读、不引用、不拿来回答问题，
规则写在仓库根 `CLAUDE.md`。同日把 `TIMELINE.md` 里 2026-08-02 到 2026-08-18
的 7 条条目逐字搬进 `TIMELINE-2026-08-02-to-2026-08-18.md`。

| 文件 | 归哪条线 | 为什么归档 |
|---|---|---|
| `TIMELINE-2026-08-02-to-2026-08-18.md` | TIMELINE 远古条目 | 2026-09-12 gyb 裁决 2026-08-20 之前的记录全部归档，7 条条目从 `TIMELINE.md` 逐字搬来（diff 校验过逐字节相同） |
| `2026-08-10-z1-plan.md`、`2026-08-10-z1-smoke-report.md` | z1 注入冒烟 | 冒烟已完成，结论录在 METHOD.md 的 R3 行 |
| `2026-08-18-ident3.md`、`2026-08-18-splice-replay.md` | 回放注入 | 两条线的代码已经落地并挂进 run.py，计划只剩历史用途 |
| `2026-08-21-lora-current-state.md` | np821 | 状态快照，被 08-26 的结果报告取代 |
| `2026-08-21-new-probe-training.md`、`2026-08-21-p1-collection-plan.md`、`2026-08-21-np821-plan.md` | p1 / np821 | 两批数据与训练都已收官，结果在 RESULTS.md 与 `2026-08-26-np821-results.md` |
| `2026-08-22-np821-exec-worklog.md`、`2026-08-26-np821-results.md`、`2026-08-26-hparam-survey.md` | np821 | np821 十二格收官后的执行日志、结果报告、超参调研；kvshare-train 这条线从 `plans/2026-08-28-plan.md` 起接手 |
