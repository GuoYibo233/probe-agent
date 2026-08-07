# 05 — 三个评测脚本接心跳

**What to build:** 三个评测脚本（工具评测、mbert 调用评测、causal 调用评测）接上心跳，进度单位是 item（样本条数）：批循环前打 done=0，跟着已有的进度 print 打心跳（没有进度 print 的按每 50 批一条补节奏），写完报告之后打 status=done。多段循环的脚本以最长那段为进度分母，一个脚本只打一根进度轴。步骤照实施计划 Task 5 执行。

**Blocked by:** 01 心跳模块与判定引擎

**Status:** claimed

- [ ] 三个文件语法检查通过
- [ ] 每个脚本只有一根进度轴，正常结束点打 status=done
- [ ] commit
