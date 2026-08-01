# 四格矩阵汇总
- run 目录 pipeline/runs;run_id 前缀 ro1aw;风险档 0.05;缺报告的格标 PENDING
- 模型 q35 / q36 / gptoss;格 mtool / mext / ctool / cgen

| 模型 | 格 | run_id | 状态 | θ | coverage | trig_acc | earliness | wrong_spec | params_all_ok | full_call_ok |
|---|---|---|---|---|---|---|---|---|---|---|
| q35 | mtool | ro1aw_q35_mtool | OK | 0.975 | 0.0054 | 0.8889 | 0.3562 | 0.0006 | - | - |
| q35 | mext | ro1aw_q35_mext | OK | 0.975 | - | - | - | - | 0.7647 | 0.7647 |
| q35 | ctool | ro1aw_q35_ctool | OK | 0.95 | 0.0882 | 0.9831 | 0.2311 | 0.0015 | - | - |
| q35 | cgen | ro1aw_q35_cgen | OK | 0.95 | - | - | - | - | 0.8912 | 0.8741 |
| q36 | mtool | ro1aw_q36_mtool | OK | - | - | - | - | - | - | - |
| q36 | mext | ro1aw_q36_mext | OK | 0.925 | - | - | - | - | 0.924 | 0.8687 |
| q36 | ctool | ro1aw_q36_ctool | OK | 0.975 | 0.0905 | 0.986 | 0.3604 | 0.0013 | - | - |
| q36 | cgen | ro1aw_q36_cgen | OK | 0.975 | - | - | - | - | 0.961 | 0.9433 |
| gptoss | mtool | ro1aw_gptoss_mtool | OK | - | - | - | - | - | - | - |
| gptoss | mext | ro1aw_gptoss_mext | OK | 0.975 | - | - | - | - | 0.7312 | 0.625 |
| gptoss | ctool | ro1aw_gptoss_ctool | OK | 0.95 | 0.3606 | 0.9481 | 0.6105 | 0.0187 | - | - |
| gptoss | cgen | ro1aw_gptoss_cgen | OK | 0.95 | - | - | - | - | 0.7927 | 0.7562 |

## 每模型的 test 规模与先验基线(取 tool 格报告)
| 模型 | test 事件数 | 频率先验基线 |
|---|---|---|
| q35 | 3356 | 0.2333 |
| q36 | 3150 | 0.2584 |
| gptoss | 2138 | 0.4041 |

口径:tool 格(mtool/ctool)四列来自 REPLAY_REPORT 的 test_frozen["0.05"];参数格(mext/cgen)两列来自 EXTRACT_REPORT.overall / CALLGEN_REPORT,都是同一风险档触发点上的数。
