# 15 — 文档回写：gpu-run skill 与两份方法论

**What to build:** gpu-run skill 对齐新流程：Phase 4 发射段收成一条 launch（手打双登记、RUNMETA、record 的命令段全删），交给用户的监控命令换成 gpu-jobs、watch 和网页；Phase 5 常设巡检制度改成采样器条款（判定、升级、事故 agent 由采样器负责，Claude 只在用户问起或事故记录有内容时派 job-monitor 读 json）；Phase 6a 销号五连保留。发射方法论里 tmux 模板一节改成"launch 替你做了什么"，挑卡规则保留；监控方法论里两点测速等三节改成程序职责说明，判断树的输入改成判定值。步骤照实施计划 Task 16 执行。

**Blocked by:** 09 launch 子命令、12 事故触发、14 采样器上线

**Status:** resolved

- [ ] Phase 4 只剩 commit、launch、交监控入口三步
- [ ] Phase 5 不再含定时巡检的排程条款
- [ ] commit

## Comments

- 2026-08-08 主会话转记（写文档前必读的现状口径）：工单 12 的事故 agent 自动拉起经用户 2026-08-08 裁决暂缓——触发规则纯函数已合并但 maybe_trigger_incidents 是占位。Phase 5 的采样器条款里"判定、升级由采样器负责"照写，"事故 agent 自动验尸补射"必须写成"未上线（暂缓）"，不许写成现状。
- 2026-08-08 口径更新（覆盖上一条）：用户随后授权，事故 agent 自动拉起已由主会话接线完成（含补射许可规则），但手动演练取消——文档写"已接线、未经真实演练"，不写"未上线"。若你已按旧口径写完，主会话收账时会核对并改正。
- 2026-08-08 ticket-run：DONE。分支 ticket/20260808-par/T15（base 86f2b8e，head b0cd20d，gpu-run SKILL.md + launch/monitor 两份方法论共 +159/-130），已合并。修复 1 轮。验收两条达成：Phase 4 收成 commit→launch→交监控入口三步；Phase 5 无定时巡检排程条款，事故 agent 口径与实装状态一致（已接线、未经真实演练）。遗留 minor 一条：实现者报告自查第 4 条与 diff 不符（说"--kind 三词枚举原样保留"，实际该段已删换成通用占位）——文档本身没问题，是报告描述错误，照录。concerns 五条照录，其中"--kind 三词枚举 vs launch 写 kind=launch 两套值"与"launch-methodology Step6 旧 ETA 措辞与新 monitor-methodology 略不齐"两条转给工单 18 收官自检核对。cannotVerify 三条：T07 过渡表述等 T07 收账对照；T12 接线完整性等 T12 提交落地核（正在走用户 ! 提交）；网页渲染一致性 T14 已实测过网页可用，措辞层面收官再扫。报告：sdd/2026-08-08-wave1/T15-report.md。
