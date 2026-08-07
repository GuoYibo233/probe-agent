# 15 — 文档回写：gpu-run skill 与两份方法论

**What to build:** gpu-run skill 对齐新流程：Phase 4 发射段收成一条 launch（手打双登记、RUNMETA、record 的命令段全删），交给用户的监控命令换成 gpu-jobs、watch 和网页；Phase 5 常设巡检制度改成采样器条款（判定、升级、事故 agent 由采样器负责，Claude 只在用户问起或事故记录有内容时派 job-monitor 读 json）；Phase 6a 销号五连保留。发射方法论里 tmux 模板一节改成"launch 替你做了什么"，挑卡规则保留；监控方法论里两点测速等三节改成程序职责说明，判断树的输入改成判定值。步骤照实施计划 Task 16 执行。

**Blocked by:** 09 launch 子命令、12 事故触发、14 采样器上线

**Status:** ready-for-agent

- [ ] Phase 4 只剩 commit、launch、交监控入口三步
- [ ] Phase 5 不再含定时巡检的排程条款
- [ ] commit

## Comments

- 2026-08-08 主会话转记（写文档前必读的现状口径）：工单 12 的事故 agent 自动拉起经用户 2026-08-08 裁决暂缓——触发规则纯函数已合并但 maybe_trigger_incidents 是占位。Phase 5 的采样器条款里"判定、升级由采样器负责"照写，"事故 agent 自动验尸补射"必须写成"未上线（暂缓）"，不许写成现状。
