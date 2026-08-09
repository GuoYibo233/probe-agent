# 18 — 收官自检

**What to build:** 整条链收官：全量单测加 selfcheck 全绿；grep 扫尾确认仓库里不再有"手打三条登记命令"的旧流程叙述残留；CONTEXT.md 词汇表与实现复核一遍（shardable、监控参数字段名这批实施中出现的词收进词汇表，注明日期）；最终汇报改动清单、新命令速查、看门狗 crontab 行和 v1 明确不做的清单。步骤照实施计划 Task 19 执行。

**Blocked by:** 15 文档回写 gpu-run、16 文档回写 agent 定义、17 文档回写 probe-pipeline 与根文档（连带全部前置）

**Status:** ready-for-agent

- [ ] `python3 -m unittest discover -s tests -v` 全绿加 `python3 run.py selfcheck` 通过
- [ ] 双登记、record start、register 的 grep 结果全部是新语境
- [ ] CONTEXT.md 复核完成，新词已收
- [ ] 最终 commit 加汇报

## Comments

- 2026-08-08 主会话转记（收官自检加两项）：其一，gpu-run SKILL.md 手搓补录路径的 RUNMETA `--kind` 通用占位与 launch 自动登记写 kind="launch" 是两套值，收官时核对文档与代码口径是否需要统一；其二，launch-methodology.md Step6 仍留旧的"ETA claims need ≥60s of tqdm observation"措辞，与重写后的 monitor-methodology.md 判定值输入不齐，收官时一并对齐。
- 2026-08-09 主会话转记（来自 T13 收账）：收官自检再加一项——port 字段从发射到采样的传递链路断在登记侧（launch --port 透传不进 piece、register 不认 --port/--kind），服务档 kind="service" 无现成命令行可登记；收官汇报里必须列为已知缺口，是否开后续工单由用户裁决。
