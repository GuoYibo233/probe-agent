# 11 — 两个排卡发射器接登记

**What to build:** launch-probe 和 launch-eval 内部改调公共件：本地的 tmux 辅助函数删掉换成 import（先扩后收的收这一步），每格发射前 FREE 实探（非 FREE 的格打印原因跳过，不整表拒绝，排卡表半空常见），每格发射后自动补台账和 record（RUNMETA 照旧自己写）。各自的守卫一个不动：launch-probe 的排卡表和 smoke 模式，launch-eval 的依赖顺序硬检查和训练产物存在检查。改完之后"程序保证登记"在所有发射路径上成立。步骤照实施计划 Task 13 执行。

**Blocked by:** 08 发射公共件

**Status:** claimed

- [ ] 两个发射器 dry-run 照常打印
- [ ] 全量单测绿（公共件的测试覆盖登记路径）
- [ ] commit
