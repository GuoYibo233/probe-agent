# 05 — 三个评测脚本接心跳

**What to build:** 三个评测脚本（工具评测、mbert 调用评测、causal 调用评测）接上心跳，进度单位是 item（样本条数）：批循环前打 done=0，跟着已有的进度 print 打心跳（没有进度 print 的按每 50 批一条补节奏），写完报告之后打 status=done。多段循环的脚本以最长那段为进度分母，一个脚本只打一根进度轴。步骤照实施计划 Task 5 执行。

**Blocked by:** 01 心跳模块与判定引擎

**Status:** resolved

- [ ] 三个文件语法检查通过
- [ ] 每个脚本只有一根进度轴，正常结束点打 status=done
- [ ] commit

## Comments

- 2026-08-08 ticket-run：DONE。分支 ticket/20260808-par/T05（base 5be5d08，head b8cda45，三个评测脚本共 +20 行），合并进 main 后 29 测试全绿、三文件 py_compile 过。修复 0 轮，无 minors。cannotVerify 一条（"最长段"选轴对 eval_mbert_call/eval_causal_call 是否成立取决于运行期数据）主会话裁决：进度轴必须静态可定，实现者选的主口径路径是必跑段、--self-fire 是默认关闭的可选支路，按"必跑段为轴"收下，不改。concerns 三条照录：--self-fire 的 score_fire() 不接心跳；eval_tool 跨 split 时 done 从 0 重起（verdicts.rates() 对 done 回跳有保护，速率记 None 不报错）；status=done 的 done/total 只计主口径不含 self-fire 数据量。报告：sdd/2026-08-08-wave1/T05-report.md。
