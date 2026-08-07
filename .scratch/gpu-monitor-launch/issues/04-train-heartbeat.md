# 04 — 四个训练脚本接心跳

**What to build:** 四格训练脚本（mbert 工具、mbert 抽取、causal 工具、causal 调用生成）都接上心跳：start 日志之后打 done=0，每 50 步的 step 日志之后打一条带滑动 loss 的心跳，done 日志之后打 status=done。跑起来之后，训练任务在窗口里有步数进度和 loss 走势。四个文件同一个模式，锚点以 grep 现查为准。步骤照实施计划 Task 4 执行。

**Blocked by:** 01 心跳模块与判定引擎

**Status:** ready-for-agent

- [ ] 四个文件语法检查通过
- [ ] mbert-env 和 cprobe-env 两个训练 venv 都能 import 心跳模块
- [ ] loss 取的是各文件 step 日志里已有的那份滑动均值，插在复位之前
- [ ] commit
