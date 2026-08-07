# 08 — 发射公共件

**What to build:** 发射的三样公共能力收进一个模块：探卡（ssh 查目标卡的计算进程，有进程或探测失败都算非 FREE，fail-closed）、tmux 发射模板（从 launch-probe 原样搬过来，先扩后收的扩这一步）、三处登记一口气（台账 rich 分片、实验记录 record start、产物目录 RUNMETA，重复 run_id 拒绝是护栏）。这一张不改任何现有发射器的行为。步骤照实施计划 Task 10 执行。

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [ ] 探卡测试通过：空卡、占用中、探测超时三种输入对应三种返回
- [ ] 登记测试通过：台账里出现 rich 分片全字段，重复 run_id 第二次调用被拒绝
- [ ] commit
