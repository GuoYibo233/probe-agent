# 活跑注入线报告

对照批次的服务条件与 harmony 日期行都与活跑不同(设计书 §1),
token 总量对比要带这条保留;billed 含触发后丢弃的溢出。
n_task_error 是临时故障(abort=task_error)的题数,这些题没进
live_success 的分母;重跑前删掉对应 live_*.jsonl 才会重试。

| 指标 | 值 |
|---|---|
| n_tasks | 2 |
| n_done | 2 |
| n_paired | 0 |
| n_task_error | 0 |
| live_success | 0.5 |
| base_success | None |
| live_success_paired | None |
| inject_per_task | 1.0 |
| billed_tok_sum | 26692 |
| base_out_tok_sum | 0 |
| n_spec | 2 |
| spec_exec_ok | 1.0 |
| spec_tool_agree | 0.0 |
| spec_call_agree | 0.0 |
| spec_recalled | 0.0 |
| spec_error_kinds | {} |

| task | arm | 成败 | 对照成败 | 步数 | 出手 | billed tok | 对照 out tok |
|---|---|---|---|---|---|---|---|
| 50e1ac9_1 | probe | True | None | 10 | 1 | 17556 | None |
| 50e1ac9_2 | probe | False | None | 7 | 1 | 9136 | None |
