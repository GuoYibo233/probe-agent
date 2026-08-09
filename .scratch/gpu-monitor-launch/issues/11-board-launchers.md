# 11 — 两个排卡发射器接登记

**What to build:** launch-probe 和 launch-eval 内部改调公共件：本地的 tmux 辅助函数删掉换成 import（先扩后收的收这一步），每格发射前 FREE 实探（非 FREE 的格打印原因跳过，不整表拒绝，排卡表半空常见），每格发射后自动补台账和 record（RUNMETA 照旧自己写）。各自的守卫一个不动：launch-probe 的排卡表和 smoke 模式，launch-eval 的依赖顺序硬检查和训练产物存在检查。改完之后"程序保证登记"在所有发射路径上成立。步骤照实施计划 Task 13 执行。

**Blocked by:** 08 发射公共件

**Status:** resolved

- [ ] 两个发射器 dry-run 照常打印
- [ ] 全量单测绿（公共件的测试覆盖登记路径）
- [ ] commit

## Comments

- 2026-08-09 ticket-run：DONE。分支 ticket/20260808-par/T11（base 0914ef5，head b49705b，launch_probe/launch_eval 接 launch_common + 两个新测试文件），合并 commit f8c9965（MAP.md 三方冲突手解：sampler 行取新口径、发射器两行取 T11）。修复 1 轮。主会话复核：launch_probe/launch_eval/launch_common 三组 22 测试全绿；dry-run 亲测跳过（工作树带着 T12 未提交改动过不了脏树门禁，实现者与评审均已在干净工作树跑过并贴输出）。修复轮定案：eval 登记的 run_id 保留 eval_ 前缀防与训练 job 撞车；登记失败只 WARN 不中断（tmux 已真发射）。concerns 三条照录：workdir 语义（发射器传仓库根 vs 台账历史填产物目录）不一致是既有问题，要统一需跨工单裁决；排卡发射器不支持判定线覆盖（范围内）；launch_probe 测试对 inner 命令做精确字符串匹配（模板改动会牵连）。这次 workflow 昨天曾静默死在修复轮，今晨 resume 缓存回放实现+评审后续跑完成。报告：sdd/2026-08-08-wave1/T11-report.md。
