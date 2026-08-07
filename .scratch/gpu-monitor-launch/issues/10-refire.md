# 10 — 补射模式 --refire

**What to build:** `run.py launch --refire` 把台账里死掉的分片按原命令重发：session 还活着就拒绝（补射只对死分片），目标卡是指定的或原卡、发射前照样实探，非 FREE 拒绝并给明确报错（事故 agent 拿报错去换卡重试）。成功后台账里这个分片位的四元组更新、launched_at 刷新，session 名不变、日志换新文件；不新开 record、不重复登记，补射不是新任务。采样器看到 launched_at 变了会自动重开该分片的心跳时间轴。步骤照实施计划 Task 12 执行。

**Blocked by:** 09 launch 子命令

**Status:** resolved

- [ ] 测试通过：活 session 拒绝，非 FREE 拒绝，成功路径台账分片的日志和 launched_at 更新且命令不变、没有第二个任务出现
- [ ] commit

## Comments

- 2026-08-08 ticket-run：DONE。分支 ticket/20260808-par/T10（base 8dfdec0，head 55a0d0e，launch_cmd.py +115、launch_common.py 微调、run.py +3、测试 +185），合并进 main 后 72 测试全绿、selfcheck 63 就位。修复 2 轮，无遗留 minors、无 cannotVerify。concerns 三条照录：launch_cmd.py 缺 MAP.md 行（T09 既有缺口，留给 T17 的 MAP 更新，T17 收账时核）；补射在采样器未追上的窗口内连发两次会撞同一 .r1.log 后缀（追加写不覆盖，边界未定义）；补射后不做 30 秒验活（工单与计划均未要求）。报告：sdd/2026-08-08-wave1/T10-report.md。
