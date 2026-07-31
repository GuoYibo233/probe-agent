# 触发时刻调用生成评测 — appworld
- 分类头 c1_q35_ctool / 生成头 c1_q35_cgen;风险≤0.05 → θ=0.975(温度 T=1.2445)
- test 事件 3356,触发 219,本次计入 219
- 拼串分隔符 call_sep='\n[CALL] '(读自生成头 meta.json);greedy max_new_tokens=96,遇换行或 eos 停

| 指标 | 值 |
|---|---|
| 解析失败率 | 0.0 |
| 工具名正确率 | 0.968 |
| 参数全对率(宽松) | 0.9041 |
| 参数全对率(严格) | 0.9041 |
| 完整调用正确率 | 0.8904 |
| 整串逐字命中(对照训练侧 val_exact_call) | 0.8858 |
| 无参事件占比 | 0.7032(154/219) |
| 参数实例数 | 122 |
| 参数级正确率(宽松/严格) | 0.7049 / 0.7049 |

## 分工具明细(按事件数前 10)
| 工具 | 事件数 | 工具名正确 | 参数全对 | 完整调用正确 |
|---|---|---|---|---|
| apis.api_docs.show_app_descriptions | 98 | 1.0 | 1.0 | 1.0 |
| apis.supervisor.show_profile | 41 | 0.9268 | 1.0 | 0.9268 |
| apis.api_docs.show_api_descriptions | 27 | 0.8889 | 0.8889 | 0.8889 |
| apis.api_docs.show_api_doc | 19 | 0.9474 | 0.8947 | 0.8947 |
| apis.supervisor.show_account_passwords | 12 | 1.0 | 1.0 | 1.0 |
| apis.spotify.login | 9 | 1.0 | 0.1111 | 0.1111 |
| apis.venmo.show_transactions | 7 | 1.0 | 0.2857 | 0.2857 |
| apis.supervisor.complete_task | 3 | 1.0 | 0.6667 | 0.6667 |
| apis.phone.login | 1 | 1.0 | 0.0 | 0.0 |
| apis.simple_note.show_note | 1 | 1.0 | 0.0 | 0.0 |

## 判分口径
- 参数逐个比:宽松=归一化(strip 后去引号)后值相等;严格=原串逐字相等;键按 union 比,多参/少参/名错各记一个错实例。
- 参数全对率里,真值无参的事件恒真(单独列出占比);完整调用正确 = 工具名对 且 参数全对(宽松)。
- 触发点与 ctool 的回放完全同源,所以本表可与同模型 mext 格的EXTRACT_REPORT 并排读:两边都是触发那一刻能不能组出整条调用。
