# 16 — 文档回写：两个 agent 定义

**What to build:** job-monitor 瘦身：两点测速、ETA 手算、tqdm 解析的操作细节全删，改成读 gpu-jobs json 的现成判定加按需验尸；只读铁律、验尸流程、报告格式保留；补一段与事故 agent 的分工（job-monitor 是人派的检查员，事故 agent 是采样器半夜拉的处置员，别替它补射）。gpu-runner 的发射段改成一律 launch，双登记段删掉，登记回执改成贴 launch 的输出。步骤照实施计划 Task 17 执行。

**Blocked by:** 07 终端出口改读采样历史、09 launch 子命令、12 事故触发

**Status:** ready-for-agent

- [ ] job-monitor 定义里不再有两点测速的操作步骤
- [ ] gpu-runner 定义里发射只有 launch 一条路（排卡发射器照旧）
- [ ] commit
