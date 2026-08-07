# 01 — 心跳模块与判定引擎，单测全绿

**What to build:** 脚本侧有了打心跳的唯一入口（emit 打一行前缀加 JSON，parse 只认合法心跳行），监控侧有了算判定的唯一口径（六格判定按固定优先级、判定线与升级线自适应、平均与近期两种速率，全部是纯函数零 IO）。步骤照实施计划 Task 1 与 Task 2（`docs/plans/2026-08-08-gpu-monitor-launch.md`）执行，测试代码计划里现成。

**Blocked by:** None — can start immediately

**Status:** resolved

- [ ] 心跳测试通过：必填字段齐、选填不给不出现、parse 往返一致、垃圾行返回 None
- [ ] 判定测试通过：六格每格至少一个用例，判定线下限、warm-up 上限、探测失败不判已挂、服务类四格都有边界用例
- [ ] 两个模块只用标准库，常数全部收在判定引擎的 DEFAULTS 配置里
- [ ] `python3 run.py selfcheck` 通过，两个任务各自 commit

## Comments

- 2026-08-08 ticket-run：DONE。commit 范围 ae41f27..ba3cdbb（c890cec 心跳模块 ops/heartbeat.py，ba3cdbb 判定引擎 ops/verdicts.py，直接落在 main，当时还是串行波模式）。测试 15/15 绿（test_heartbeat 4 + test_verdicts 11），selfcheck 过。评审零 findings、零 cannotVerify，修复 0 轮，无遗留 minors、无实现者 concerns。报告：sdd/2026-08-08-wave1/T01-report.md。
