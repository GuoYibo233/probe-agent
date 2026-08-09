# 17 — 文档回写：probe-pipeline 与根文档

**What to build:** probe-pipeline skill 及其 references（gates、stage-commands、invariants、extending）、handoff skill、CLAUDE.md、MAP.md、gpu_state 页首全部对齐新流程。三句关键新表述：G16 双登记改成"launch 自动写三处，手搓补录路径仍在，漏了照旧算违规"；invariants 的记账双写改成"双写由 launch 保证，绕过 launch 手搓发射的责任回到人"；extending 的新脚本清单加硬项"新采集/训练/评测脚本必须接心跳，不接的脚本在窗口里永远是 warm-up 中"。MAP 更新三行旧程序、新增五行新模块。步骤照实施计划 Task 18 执行。

**Blocked by:** 09 launch 子命令、11 两个排卡发射器接登记、14 采样器上线

**Status:** resolved

- [ ] 上面三句新表述逐字落进对应文件
- [ ] MAP.md 新旧程序行齐全
- [ ] commit

## Comments

- 2026-08-09 ticket-run：DONE。分支 ticket/20260808-par/T17（base f8c9965，head 80b6cbf，probe-pipeline skill 及四份 references + handoff skill + CLAUDE.md + MAP.md + gpu_state 页首），合并 commit 4b2e9df（MAP gpu_jobs 行冲突：以 T07 出口事实为底并入 T17 的"register 是补录路径"句）。修复 1 轮。验收核对：三句关键新表述落位——gates.md"launch 自动写三处"逐字在、invariants.md"双写由 launch 保证"逐字在、extending.md 心跳硬项要素齐全（"接心跳"写成"接 `ops/heartbeat.py`"带模块引用，语义同）；MAP.md 新旧程序行齐全，T17 还顺手补了 T10 留的 launch_cmd.py 缺行。concerns 三条照录：SKILL.md :74-75/:172-173 两处经重读判断无需改动；CLAUDE.md 例句拆两处落地非逐字；MAP 四行沿用各工单收尾版本未重写。报告：sdd/2026-08-08-wave1/T17-report.md。
