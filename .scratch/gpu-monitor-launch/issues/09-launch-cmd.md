# 09 — launch 子命令

**What to build:** `python3 run.py launch` 一条命令把发射走完：脏树门禁、逐分片验卡（任何一张非 FREE 整次拒绝）、起 tmux、验活 30 秒（session 在、日志有输出、无 traceback；失败不登记不回滚）、三处登记、打印监控入口。标了 shardable 的任务给多个分片自动注入分片编号，没标的多分片直接拒绝。session 名、台账名、record、日志名由程序从同一个 run_id 生成。注册表外的一次性命令走 --cmd 逃生口，登记照做。--dry-run 只打印命令不碰登记。步骤照实施计划 Task 11 执行。

**Blocked by:** 08 发射公共件

**Status:** resolved

- [ ] 分片注入测试通过：两个分片注入编号 0 和 1，非 shardable 多分片拒绝，同机同卡两个分片拒绝
- [ ] dry-run 冒烟：采集任务两分片打出两条带分片编号的完整命令，登记函数没被调
- [ ] `python3 run.py selfcheck` 通过（launch 挂进 run.py），commit

## Comments

- 2026-08-08 主会话转记（来自 T08 收账，实现时要对上的两条接口约定）：其一，launch_common.register_all 在 monitor=None 时不写 job 的 monitor key（消费端 job.get("monitor",{}) 才不炸），T09 传 monitor 参数要符合这个约定；其二，多分片时 register_all 调 record.py start 的 --host/--gpu/--log 是逗号拼接的展示串，T09 产出第一个真实多分片调用后，主会话要肉眼核对一次 RESULTS.md 的渲染效果。
- 2026-08-08 ticket-run：DONE。分支 ticket/20260808-par/T09（base 1d421be，head 0160809，新增 ops/launch_cmd.py + tests/test_launch_cmd.py，run.py 挂 launch），合并进 main 后 62 测试全绿、selfcheck 63 就位（评审那条"未在合并环境复现 selfcheck"由主会话就地核销）。修复 1 轮。遗留 minor 两条：_VALUE_FLAGS/_BOOL_FLAGS 死代码常量；--piece 的 gpu 段为空字符串时判重失效（session/log 名可碰撞，输入本身不合法，风险面窄）。主会话亲测 dry-run 冒烟：collect-aw 两分片打出注入 --shard-id 0/1 --num-shards 2 的完整命令，台账零写入。"多分片 record 展示串的 RESULTS.md 渲染"留到第一次真实多分片发射后肉眼核对。concerns 五条照录，其中"服务分片 port 字段整条路径未定义"已转记工单 13。报告：sdd/2026-08-08-wave1/T09-report.md。
