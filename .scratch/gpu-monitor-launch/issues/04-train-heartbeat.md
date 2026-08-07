# 04 — 四个训练脚本接心跳

**What to build:** 四格训练脚本（mbert 工具、mbert 抽取、causal 工具、causal 调用生成）都接上心跳：start 日志之后打 done=0，每 50 步的 step 日志之后打一条带滑动 loss 的心跳，done 日志之后打 status=done。跑起来之后，训练任务在窗口里有步数进度和 loss 走势。四个文件同一个模式，锚点以 grep 现查为准。步骤照实施计划 Task 4 执行。

**Blocked by:** 01 心跳模块与判定引擎

**Status:** resolved

- [ ] 四个文件语法检查通过
- [ ] mbert-env 和 cprobe-env 两个训练 venv 都能 import 心跳模块
- [ ] loss 取的是各文件 step 日志里已有的那份滑动均值，插在复位之前
- [ ] commit

## Comments

- 2026-08-08 ticket-run：DONE。分支 ticket/20260808-par/T04（base 5be5d08，head f4b9f67，四个训练脚本各 +9 行），合并 commit 见 main。修复 0 轮，无 minors。cannotVerify 两条主会话已处理：mbert-env / cprobe-env import 心跳模块由主会话在合并后的 main 上亲自重跑，双双通过，四文件 py_compile 通过；"窗口里步数进度和 loss 走势"属跨 T02/06/07 端到端效果，留待后核。concerns 两条（worktree 无 venv 故用主仓解释器验证、三个文件锚点按 grep 现查与计划文档行号不一致）已读，均为过程说明不是缺口。报告：sdd/2026-08-08-wave1/T04-report.md。
