# 09 — launch 子命令

**What to build:** `python3 run.py launch` 一条命令把发射走完：脏树门禁、逐分片验卡（任何一张非 FREE 整次拒绝）、起 tmux、验活 30 秒（session 在、日志有输出、无 traceback；失败不登记不回滚）、三处登记、打印监控入口。标了 shardable 的任务给多个分片自动注入分片编号，没标的多分片直接拒绝。session 名、台账名、record、日志名由程序从同一个 run_id 生成。注册表外的一次性命令走 --cmd 逃生口，登记照做。--dry-run 只打印命令不碰登记。步骤照实施计划 Task 11 执行。

**Blocked by:** 08 发射公共件

**Status:** ready-for-agent

- [ ] 分片注入测试通过：两个分片注入编号 0 和 1，非 shardable 多分片拒绝，同机同卡两个分片拒绝
- [ ] dry-run 冒烟：采集任务两分片打出两条带分片编号的完整命令，登记函数没被调
- [ ] `python3 run.py selfcheck` 通过（launch 挂进 run.py），commit
