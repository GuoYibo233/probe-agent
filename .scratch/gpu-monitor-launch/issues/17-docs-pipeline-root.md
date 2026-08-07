# 17 — 文档回写：probe-pipeline 与根文档

**What to build:** probe-pipeline skill 及其 references（gates、stage-commands、invariants、extending）、handoff skill、CLAUDE.md、MAP.md、gpu_state 页首全部对齐新流程。三句关键新表述：G16 双登记改成"launch 自动写三处，手搓补录路径仍在，漏了照旧算违规"；invariants 的记账双写改成"双写由 launch 保证，绕过 launch 手搓发射的责任回到人"；extending 的新脚本清单加硬项"新采集/训练/评测脚本必须接心跳，不接的脚本在窗口里永远是 warm-up 中"。MAP 更新三行旧程序、新增五行新模块。步骤照实施计划 Task 18 执行。

**Blocked by:** 09 launch 子命令、11 两个排卡发射器接登记、14 采样器上线

**Status:** ready-for-agent

- [ ] 上面三句新表述逐字落进对应文件
- [ ] MAP.md 新旧程序行齐全
- [ ] commit
