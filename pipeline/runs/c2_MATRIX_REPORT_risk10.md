# 四格矩阵汇总
- run 目录 /home/y-guo/reproduce/new1/pipeline/runs;run_id 前缀 c2;风险档 0.1;缺报告的格标 PENDING
- 模型 q35 / q36 / gptoss;格 mtool / mext / ctool / cgen

| 模型 | 格 | run_id | 状态 | θ | coverage | trig_acc | earliness | wrong_spec | params_all_ok | full_call_ok |
|---|---|---|---|---|---|---|---|---|---|---|
| q35 | mtool | c2_q35_mtool | PENDING | - | - | - | - | - | - | - |
| q35 | mext | c2_q35_mext | PENDING | - | - | - | - | - | - | - |
| q35 | ctool | c2_q35_ctool | PENDING | - | - | - | - | - | - | - |
| q35 | cgen | c2_q35_cgen | PENDING | - | - | - | - | - | - | - |
| q36 | mtool | c2_q36_mtool | OK | 0.5 | 0.9995 | 0.9413 | 0.8322 | 0.0587 | - | - |
| q36 | mext | c2_q36_mext | OK | 0.575 | - | - | - | - | 0.9641 | 0.9259 |
| q36 | ctool | c2_q36_ctool | OK | 0.5 | 1.0 | 0.9441 | 0.8359 | 0.0559 | - | - |
| q36 | cgen | c2_q36_cgen | OK | 0.5 | - | - | - | - | 0.7815 | 0.7768 |
| gptoss | mtool | c2_gptoss_mtool | OK | 0.825 | 0.8816 | 0.8638 | 0.7798 | 0.1201 | - | - |
| gptoss | mext | c2_gptoss_mext | OK | 0.95 | - | - | - | - | 0.8792 | 0.8324 |
| gptoss | ctool | c2_gptoss_ctool | OK | 0.85 | 0.9883 | 0.8848 | 0.7532 | 0.1138 | - | - |
| gptoss | cgen | c2_gptoss_cgen | PENDING | - | - | - | - | - | - | - |

## 每模型的 test 规模与先验基线(取 tool 格报告)
| 模型 | test 事件数 | 频率先验基线 |
|---|---|---|
| q35 | - | - |
| q36 | 2146 | 0.548 |
| gptoss | 3497 | 0.4704 |

口径:tool 格(mtool/ctool)四列来自 REPLAY_REPORT 的 test_frozen["0.1"];参数格(mext/cgen)两列来自 EXTRACT_REPORT.overall / CALLGEN_REPORT,都是同一风险档触发点上的数。
