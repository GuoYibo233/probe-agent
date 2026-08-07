# 08 — 发射公共件

**What to build:** 发射的三样公共能力收进一个模块：探卡（ssh 查目标卡的计算进程，有进程或探测失败都算非 FREE，fail-closed）、tmux 发射模板（从 launch-probe 原样搬过来，先扩后收的扩这一步）、三处登记一口气（台账 rich 分片、实验记录 record start、产物目录 RUNMETA，重复 run_id 拒绝是护栏）。这一张不改任何现有发射器的行为。步骤照实施计划 Task 10 执行。

**Blocked by:** None — can start immediately

**Status:** resolved

- [ ] 探卡测试通过：空卡、占用中、探测超时三种输入对应三种返回
- [ ] 登记测试通过：台账里出现 rich 分片全字段，重复 run_id 第二次调用被拒绝
- [ ] commit

## Comments

- 2026-08-08 ticket-run：DONE。分支 ticket/20260808-par/T08（base 5be5d08，head c55e47a，新增 ops/launch_common.py +126、tests/test_launch_common.py +184、MAP.md +1），合并进 main 后 29 测试全绿、selfcheck 过。修复 0 轮。遗留 minor 一条：launch_common.py 的 ROOT 变量定义后未使用（死代码，不挡合并）。cannotVerify 四条：第一条评审已自行重跑 14 用例核实；其余三条（monitor=None 不写 key 的约定与 T09 调用方吻合与否、多分片 record start 逗号拼接的显示效果、T13 反向 import 后行为一致性）属跨工单事项，已转记到工单 09 的 Comments，T13 收账时再核最后一条。报告：sdd/2026-08-08-wave1/T08-report.md。
