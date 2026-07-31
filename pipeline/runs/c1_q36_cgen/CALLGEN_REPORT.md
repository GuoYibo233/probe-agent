# 触发时刻调用生成评测 — appworld
- 分类头 c1_q36_ctool / 生成头 c1_q36_cgen;风险≤0.1 → θ=0.925(温度 T=1.4151)
- test 事件 3150,触发 917,本次计入 917
- 拼串分隔符 call_sep='\n[CALL] '(读自生成头 meta.json);greedy max_new_tokens=96,遇换行或 eos 停

| 指标 | 值 |
|---|---|
| 解析失败率 | 0.0 |
| 工具名正确率 | 0.904 |
| 参数全对率(宽松) | 0.8582 |
| 参数全对率(严格) | 0.8582 |
| 完整调用正确率 | 0.8135 |
| 整串逐字命中(对照训练侧 val_exact_call) | 0.8103 |
| 无参事件占比 | 0.5278(484/917) |
| 参数实例数 | 785 |
| 参数级正确率(宽松/严格) | 0.7312 / 0.7312 |

## 分工具明细(按事件数前 10)
| 工具 | 事件数 | 工具名正确 | 参数全对 | 完整调用正确 |
|---|---|---|---|---|
| apis.api_docs.show_app_descriptions | 217 | 1.0 | 1.0 | 1.0 |
| apis.api_docs.show_api_doc | 143 | 0.958 | 0.8322 | 0.8322 |
| apis.supervisor.show_profile | 118 | 0.7966 | 1.0 | 0.7966 |
| apis.supervisor.complete_task | 118 | 0.9915 | 0.9322 | 0.9237 |
| apis.api_docs.show_api_descriptions | 105 | 0.9524 | 0.9333 | 0.9333 |
| apis.supervisor.show_account_passwords | 48 | 0.9792 | 1.0 | 0.9792 |
| apis.simple_note.search_notes | 37 | 0.1351 | 0.4865 | 0.1081 |
| apis.venmo.login | 28 | 1.0 | 0.75 | 0.75 |
| apis.phone.login | 24 | 0.9167 | 0.1667 | 0.1667 |
| apis.spotify.login | 22 | 0.9545 | 0.3182 | 0.3182 |

## 判分口径
- 参数逐个比:宽松=归一化(strip 后去引号)后值相等;严格=原串逐字相等;键按 union 比,多参/少参/名错各记一个错实例。
- 参数全对率里,真值无参的事件恒真(单独列出占比);完整调用正确 = 工具名对 且 参数全对(宽松)。
- 触发点与 ctool 的回放完全同源,所以本表可与同模型 mext 格的EXTRACT_REPORT 并排读:两边都是触发那一刻能不能组出整条调用。
