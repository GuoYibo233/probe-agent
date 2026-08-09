# 07 — 终端出口改读采样历史

**What to build:** gpu-jobs 的状态表、watch、json 三个出口改成先读采样历史：最后采样时刻在 5 分钟内就用采样历史瞬间出表（表头带最后采样时刻），过期就打一行警告退回现有的现场实探老路。json 出口过期时附 sampler_stale 标记。free、register、finish 一行不动，挑卡和销号永远现场实探。步骤照实施计划 Task 8 执行。

**Blocked by:** 02 采样器单轮走通

**Status:** resolved

- [ ] 没有采样器在跑的时候：警告行加老表照出，json 出口输出合法 JSON
- [ ] 指一份假的最新采样文件：新表出得来，判定、进度、速率、ETA 各列都渲染
- [ ] 已完成和已挂两种判定仍有收尾与看日志的提示行
- [ ] commit

## Comments

- 2026-08-09 ticket-run：DONE。分支 ticket/20260808-par/T07（base 2ce9834，head f5a864a，gpu_jobs.py +177、tests/test_gpu_jobs.py 新增 16 用例），合并 commit 0d2c1ac。修复 1 轮，无 minors、无 cannotVerify。主会话真实冒烟：活采样器在跑的情况下 `gpu-jobs status` 瞬间出表、表头带最后采样时刻，`gpu-jobs json` 直接吐采样结果原文（rows/extras/incidents_tail），16 测试全绿。concerns 两条照录：RATE 单位切换阈值（≥1 用 /s 否则 /h）是实现者自定边界，与网页出口固定 /s 不一致，留收官核对是否统一；已完成/已挂提示行保留旧关键短语但非逐字照抄。首个 workflow 昨日静默死亡，resume 重跑实现完成。报告：sdd/2026-08-08-wave1/T07-report.md。
