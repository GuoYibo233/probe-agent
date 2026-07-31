# 四格矩阵汇总
- run 目录 pipeline/runs;风险档 0.1;缺报告的格标 PENDING
- 模型 q35 / q36 / gptoss;格 mtool / mext / ctool / cgen

| 模型 | 格 | run_id | 状态 | θ | coverage | trig_acc | earliness | wrong_spec | params_all_ok | full_call_ok |
|---|---|---|---|---|---|---|---|---|---|---|
| q35 | mtool | c1_q35_mtool | OK | - | - | - | - | - | - | - |
| q35 | mext | c1_q35_mext | PENDING | - | - | - | - | - | - | - |
| q35 | ctool | c1_q35_ctool | OK | 0.925 | 0.1642 | 0.9292 | 0.3638 | 0.0116 | - | - |
| q35 | cgen | c1_q35_cgen | OK | 0.975 | - | - | - | - | 0.9041 | 0.8904 |
| q36 | mtool | c1_q36_mtool | OK | 0.925 | 0.1724 | 0.9208 | 0.5207 | 0.0137 | - | - |
| q36 | mext | c1_q36_mext | OK | 0.975 | - | - | - | - | 0.9595 | 0.9324 |
| q36 | ctool | c1_q36_ctool | OK | 0.925 | 0.2911 | 0.9368 | 0.4049 | 0.0184 | - | - |
| q36 | cgen | c1_q36_cgen | OK | 0.925 | - | - | - | - | 0.8582 | 0.8135 |
| gptoss | mtool | c1_gptoss_mtool | OK | 0.975 | 0.1239 | 0.8642 | 0.5502 | 0.0168 | - | - |
| gptoss | mext | c1_gptoss_mext | OK | 0.975 | - | - | - | - | 0.7887 | 0.6755 |
| gptoss | ctool | c1_gptoss_ctool | OK | 0.925 | 0.4963 | 0.9057 | 0.5864 | 0.0468 | - | - |
| gptoss | cgen | c1_gptoss_cgen | OK | 0.975 | - | - | - | - | 0.8262 | 0.7852 |

## 每模型的 test 规模与先验基线(取 tool 格报告)
| 模型 | test 事件数 | 频率先验基线 |
|---|---|---|
| q35 | 3356 | 0.174 |
| q36 | 3150 | 0.1587 |
| gptoss | 2138 | 0.4041 |

口径:tool 格(mtool/ctool)四列来自 REPLAY_REPORT 的 test_frozen["0.1"];参数格(mext/cgen)两列来自 EXTRACT_REPORT.overall / CALLGEN_REPORT,都是同一风险档触发点上的数。
