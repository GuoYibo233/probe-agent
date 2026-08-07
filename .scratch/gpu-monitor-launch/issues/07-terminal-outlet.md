# 07 — 终端出口改读采样历史

**What to build:** gpu-jobs 的状态表、watch、json 三个出口改成先读采样历史：最后采样时刻在 5 分钟内就用采样历史瞬间出表（表头带最后采样时刻），过期就打一行警告退回现有的现场实探老路。json 出口过期时附 sampler_stale 标记。free、register、finish 一行不动，挑卡和销号永远现场实探。步骤照实施计划 Task 8 执行。

**Blocked by:** 02 采样器单轮走通

**Status:** ready-for-agent

- [ ] 没有采样器在跑的时候：警告行加老表照出，json 出口输出合法 JSON
- [ ] 指一份假的最新采样文件：新表出得来，判定、进度、速率、ETA 各列都渲染
- [ ] 已完成和已挂两种判定仍有收尾与看日志的提示行
- [ ] commit
