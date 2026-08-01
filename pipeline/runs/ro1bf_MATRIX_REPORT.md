# 四格矩阵汇总
- run 目录 pipeline/runs;run_id 前缀 ro1bf;风险档 0.05;缺报告的格标 PENDING
- 模型 q35 / q36 / gptoss;格 mtool / mext / ctool / cgen

| 模型 | 格 | run_id | 状态 | θ | coverage | trig_acc | earliness | wrong_spec | params_all_ok | full_call_ok |
|---|---|---|---|---|---|---|---|---|---|---|
| q35 | mtool | ro1bf_q35_mtool | OK | 0.875 | 0.25 | 0.9333 | 0.6346 | 0.0167 | - | - |
| q35 | mext | ro1bf_q35_mext | OK | 0.875 | - | - | - | - | 0.8621 | 0.8276 |
| q35 | ctool | ro1bf_q35_ctool | OK | 0.875 | 0.3167 | 0.9211 | 0.4982 | 0.025 | - | - |
| q35 | cgen | ro1bf_q35_cgen | OK | 0.875 | - | - | - | - | 0.7778 | 0.75 |
| q36 | mtool | ro1bf_q36_mtool | OK | 0.95 | 0.3113 | 0.9697 | 0.618 | 0.0094 | - | - |
| q36 | mext | ro1bf_q36_mext | OK | 0.95 | - | - | - | - | 0.9375 | 0.9375 |
| q36 | ctool | ro1bf_q36_ctool | OK | 0.8 | 0.4245 | 0.8889 | 0.7084 | 0.0472 | - | - |
| q36 | cgen | ro1bf_q36_cgen | OK | 0.8 | - | - | - | - | 0.881 | 0.8571 |
| gptoss | mtool | ro1bf_gptoss_mtool | OK | 0.725 | 0.3303 | 0.8889 | 0.6899 | 0.0367 | - | - |
| gptoss | mext | ro1bf_gptoss_mext | OK | 0.725 | - | - | - | - | 0.9118 | 0.8529 |
| gptoss | ctool | ro1bf_gptoss_ctool | OK | 0.825 | 0.3394 | 0.8919 | 0.6211 | 0.0367 | - | - |
| gptoss | cgen | ro1bf_gptoss_cgen | OK | 0.825 | - | - | - | - | 0.9412 | 0.9412 |

## 每模型的 test 规模与先验基线(取 tool 格报告)
| 模型 | test 事件数 | 频率先验基线 |
|---|---|---|
| q35 | 120 | 0.5167 |
| q36 | 106 | 0.5094 |
| gptoss | 109 | 0.4679 |

口径:tool 格(mtool/ctool)四列来自 REPLAY_REPORT 的 test_frozen["0.05"];参数格(mext/cgen)两列来自 EXTRACT_REPORT.overall / CALLGEN_REPORT,都是同一风险档触发点上的数。
