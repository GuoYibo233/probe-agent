# 03 — 采集脚本接心跳

**What to build:** 采集脚本 run_appworld 进主循环先打 done=0（模型加载完了的标志），每做完一题打一条心跳带累计 token（token 数从每个请求的 usage 现成拿），resume 跳过的题同样推进 done，正常收尾打 status=done。跑起来之后，采集任务在窗口里有进度、token 速率和 ETA。步骤照实施计划 Task 3 执行。

**Blocked by:** 01 心跳模块与判定引擎

**Status:** ready-for-agent

- [ ] 语法检查通过，appworld 的 venv 下 `--help` 正常打印（证明心跳模块在那个 venv 里 import 得动）
- [ ] 每题收尾和 SKIP 分支都推进 done，循环结束打 status=done
- [ ] commit
