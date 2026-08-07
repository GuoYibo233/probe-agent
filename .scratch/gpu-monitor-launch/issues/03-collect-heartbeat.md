# 03 — 采集脚本接心跳

**What to build:** 采集脚本 run_appworld 进主循环先打 done=0（模型加载完了的标志），每做完一题打一条心跳带累计 token（token 数从每个请求的 usage 现成拿），resume 跳过的题同样推进 done，正常收尾打 status=done。跑起来之后，采集任务在窗口里有进度、token 速率和 ETA。步骤照实施计划 Task 3 执行。

**Blocked by:** 01 心跳模块与判定引擎

**Status:** resolved

- [ ] 语法检查通过，appworld 的 venv 下 `--help` 正常打印（证明心跳模块在那个 venv 里 import 得动）
- [ ] 每题收尾和 SKIP 分支都推进 done，循环结束打 status=done
- [ ] commit

## Comments

- 2026-08-08 ticket-run：DONE。分支 ticket/20260808-par/T03（base 5be5d08，head 9838281，改 envs/collect/run_appworld.py +17 行），合并 commit 251919f。修复 0 轮，无 minors。cannotVerify 两条主会话已处理：--help 在 appworld venv 下由主会话在合并后的 main 上亲自重跑通过（exit 0）；"窗口里显示进度/速率/ETA"属跨 T02/06/07 的端到端效果，留待采样器与出口落地后核。实现者 concern 一条：tok_in/tok_out 为累计值，与协议一致，确认性记录。报告：sdd/2026-08-08-wave1/T03-report.md。
