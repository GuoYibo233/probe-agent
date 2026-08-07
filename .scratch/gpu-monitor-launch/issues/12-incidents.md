# 12 — 事故触发

**What to build:** 采样器在判定变坏的时候自动拉事故 agent：已挂当场触发，疑似卡死停摆超过升级线触发；触发规则收在纯函数里（同一次事故只拉一次，事故编号防重复；允许补射的条件是已挂并且这个分片位没补射过）。事故 agent 是无头 claude、模型钉 opus，提示词带上判定、分片、日志路径和原始发射命令，权限线写死：已挂验尸后补射一次（走 --refire），疑似卡死只验尸不许杀，不写人读的报告。事故记录和 agent 输出都落盘。实施前先核对无头模式旗标的当前拼写。步骤照实施计划 Task 14 执行。

**Blocked by:** 02 采样器单轮走通、10 补射模式 --refire

**Status:** ready-for-human

- [ ] 触发规则测试通过：首次已挂允许补射、补射过的不允许、事故已开不重复触发、疑似卡死未达升级线不触发
- [ ] 提示词测试通过：含日志路径、台账 json 命令、补射命令或不许补射的字样
- [ ] 手动演练：假任务采一轮后事故记录出一条、agent 输出文件里有 DONE 行，演练后清场
- [ ] commit

## Comments

- 2026-08-08 主会话转记（来自 T09 收账）：服务分片的 port 传递路径未定义（见工单 13 的 Comments），与本单无直接冲突，仅备忘。
- 2026-08-08 ticket-run：BLOCKED → ready-for-human。已完成并合并进 main（分支 ticket/20260808-par/T12，commit 5527eb9，合并后 79 测试全绿、selfcheck 63 就位）：should_trigger 触发规则纯函数（5 用例）、build_incident_prompt 提示词构造（2 用例）、无头旗标拼写已核对（-p/--print、--model、--dangerously-skip-permissions 均存在）。未完成：spawn_agent 实装与手动演练——写入/执行"拉起无头 claude 子进程且带权限绕过旗标"的动作被 Claude Code 权限分类器多次拦截（完整实现、删占位、mock 单测均被拦），且拉 opus 子进程属付费模型调用，按铁律需用户本人授权。关联发现（实装时必修）：sample_once() 里 atomic_write(state.json) 目前排在 maybe_trigger_incidents 之前，不调顺序则"同一次事故只拉一次"跨轮不成立，同一事故会每轮 60 秒重复拉一个 opus 子进程。需用户决策：明确授权后由拿到授权的会话实装 + 演练。报告：sdd/2026-08-08-wave1/T12-report.md。
- 2026-08-08 用户裁决：事故 agent 的 spawn_agent 实装与手动演练**暂缓**，本单停在"触发规则纯函数 + 提示词构造已合并、maybe_trigger_incidents 占位 pass"的状态。对下游文档工单（15/16）的影响：文档必须照实写"事故 agent 自动拉起未上线，判定与采样照常"，不许把未上线的自动化写成现状。复活本单时从 spawn_agent 实装 + state.json 写入顺序修复 + 演练三件事进。
