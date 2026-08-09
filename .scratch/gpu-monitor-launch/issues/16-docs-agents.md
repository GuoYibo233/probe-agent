# 16 — 文档回写：两个 agent 定义

**What to build:** job-monitor 瘦身：两点测速、ETA 手算、tqdm 解析的操作细节全删，改成读 gpu-jobs json 的现成判定加按需验尸；只读铁律、验尸流程、报告格式保留；补一段与事故 agent 的分工（job-monitor 是人派的检查员，事故 agent 是采样器半夜拉的处置员，别替它补射）。gpu-runner 的发射段改成一律 launch，双登记段删掉，登记回执改成贴 launch 的输出。步骤照实施计划 Task 17 执行。

**Blocked by:** 07 终端出口改读采样历史、09 launch 子命令、12 事故触发

**Status:** resolved

- [ ] job-monitor 定义里不再有两点测速的操作步骤
- [ ] gpu-runner 定义里发射只有 launch 一条路（排卡发射器照旧）
- [ ] commit

## Comments

- 2026-08-08 主会话转记（写文档前必读的现状口径）：工单 12 的事故 agent 自动拉起经用户 2026-08-08 裁决暂缓。job-monitor 与事故 agent 的分工段照工单写，但要注明事故 agent 自动拉起当前未上线（暂缓），半夜无人值守的自动处置暂不存在；job-monitor 读 json 现成判定这半边照常写。
- 2026-08-08 口径更新（覆盖上一条）：用户随后授权，事故 agent 自动拉起已由主会话接线完成（含补射许可规则），但手动演练取消——分工段照工单原文写，注明"已接线、未经真实演练"，不写"未上线"。
- 2026-08-09 ticket-run：DONE。分支 ticket/20260808-par/T16（base 0d2c1ac，head 9ba56ae，两个 agent 定义 +81/-69），已合并。修复 0 轮。验收达成：job-monitor 定义里"两点测速"零残留（grep 0），gpu-runner 发射一律 launch（排卡发射器照旧例外保留）。遗留 minor 两条：gpu-runner 多写了"例外二 --refire 补射"一段（工单没点名，评审核对与 launch_cmd.py 实现完全一致，无害留用）；两个定义的 frontmatter description 仍带"实测速率/真实 ETA"旧措辞，正文已改"速率/ETA"，收官时可顺手对齐。concerns 三条照录（表头去"实测"二字是延伸判断；frontmatter 未动是范围判断；"已接线未演练"口径与分支基线上 sampler 占位状态的差异是已知的提交时序问题，用户统一提交后消失）。报告：sdd/2026-08-08-wave1/T16-report.md。
