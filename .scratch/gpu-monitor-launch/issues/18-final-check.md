# 18 — 收官自检

**What to build:** 整条链收官：全量单测加 selfcheck 全绿；grep 扫尾确认仓库里不再有"手打三条登记命令"的旧流程叙述残留；CONTEXT.md 词汇表与实现复核一遍（shardable、监控参数字段名这批实施中出现的词收进词汇表，注明日期）；最终汇报改动清单、新命令速查、看门狗 crontab 行和 v1 明确不做的清单。步骤照实施计划 Task 19 执行。

**Blocked by:** 15 文档回写 gpu-run、16 文档回写 agent 定义、17 文档回写 probe-pipeline 与根文档（连带全部前置）

**Status:** ready-for-agent

- [ ] `python3 -m unittest discover -s tests -v` 全绿加 `python3 run.py selfcheck` 通过
- [ ] 双登记、record start、register 的 grep 结果全部是新语境
- [ ] CONTEXT.md 复核完成，新词已收
- [ ] 最终 commit 加汇报
