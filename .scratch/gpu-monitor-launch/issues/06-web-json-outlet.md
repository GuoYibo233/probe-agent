# 06 — 网页与 json 出口

**What to build:** 采样器同一个进程开 HTTP 端口（默认 8377，可覆盖）：根路径出任务表网页（判定、进度、速率、token、ETA、事故记录块、台账外 session，30 秒自动刷新，最后采样时刻过期亮红），/json 出最新采样结果原文。网页线程只读落盘的最新结果文件，不碰采样线程的内存，采样那边 ssh 卡住不影响出页。用户经 VS Code 端口转发在本地浏览器看。步骤照实施计划 Task 7 执行。

**Blocked by:** 02 采样器单轮走通

**Status:** resolved

- [ ] 网页测试通过：/json 与落盘文件一致，根路径 200 且正文含任务名、判定和最后采样时刻
- [ ] 过期亮红的阈值从判定引擎的 DEFAULTS 生成进页面，不另抄一个数
- [ ] commit

## Comments

- 2026-08-08 ticket-run：DONE。分支 ticket/20260808-par/T06（base 1d421be，head 5897417，ops/sampler.py +204 行网页段、tests/test_sampler_web.py 新增），合并进 main 后 41 测试全绿、selfcheck 63 就位。修复 0 轮。遗留 minor 一条：/json 是 latest.json 解析后重序列化（语义一致、字节不同，缩进丢失），验收条目"与落盘文件一致"按语义过；若未来有消费方按字节哈希比新鲜度会踩，先记录不改。concern 一条照录：latest.json 缺失时 /json 返回 503 + error json，是实现者自裁的接口，后续消费方如有别的期望要回来对齐。报告：sdd/2026-08-08-wave1/T06-report.md。
