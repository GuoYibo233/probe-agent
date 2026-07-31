# bfcl_mtb_v1 / gptoss 真值调用串回读检查(check_callstr.py)

- SEED=20260729 env=bfcl model=gpt-oss-120b
- config=pipeline/configs/bfcl_gptoss.json data=/home/y-guo/reproduce/new1/pipeline/data/bfcl_mtb_v1/gptoss
- 口径:对每个事件的 label_call 调 `eval_causal_call.parse_call`,再把 `(key, norm(value))` 与该事件的 `args_named` 逐位比;全等才算回读成功。

## 结构性门禁
- 门禁 C 2 项 traj_runs 均为 run 目录本身 ✓
- 门禁 A 全部 32163 行 model==gpt-oss-120b ✓
- 门禁 B 样本键 32163 个全唯一;199 个 unit 各对一条 traj ✓
- 门禁 D 题单归属全量核对(非抽样)✓
- 门禁 E 报告文案与 SPLIT_REPORT 一致 ✓(official_split_exists=False)

## 偏差 1:真值调用串回读
- 事件 1060;回读成功 1034(**0.9755**),失败 26(**0.0245**)
- 失败按 split: {'train': 17, 'test': 2, 'val': 7}
- 工具名切不回来的事件: 0
- 参数实例 1640;回读成功 1614(**0.9841**)
- 参数值里含逗号的实例: 76(0.0463)← 这是失败的主因
- **结论:params_all_ok / full_call_ok 的天花板是 0.9755**,生成侧写得再对也拿不到剩下那部分。不修口径的理由见文件头。

### 失败样例(前 5 条)
- `bfcl_gptoss/multi_turn_base_102|s6`
  - label_call: `create_ticket(title=Account Information Error, description=User-reported issue where updated account information, such as email and phone number, is not displaying correctly and is not syncing across services despite attempts to log out and back in.)`
  - annotate 侧真值: `[{'key': 'title', 'value': 'Account Information Error'}, {'key': 'description', 'value': 'User-reported issue where updated account information, such as email and phone number, is not displaying correctly and is not syncing across services despite attempts to log out and back in.'}]`
  - eval 侧切回来: `[{'key': 'title', 'value': 'Account Information Error'}, {'key': 'description', 'value': 'User-reported issue where updated account information'}, {'key': 'pos0', 'value': 'such as email and phone number'}, {'key': 'pos1', 'value': 'is not displaying correctly and is not syncing across services despite attempts to log out and back in.'}]`
- `bfcl_gptoss/multi_turn_base_106|s8`
  - label_call: `resolve_ticket(ticket_id=1, resolution=The issue with the trading system query, caused by a brief network delay, has been resolved, and no further action is required as the system is now functioning properly.)`
  - annotate 侧真值: `[{'key': 'ticket_id', 'value': '1'}, {'key': 'resolution', 'value': 'The issue with the trading system query, caused by a brief network delay, has been resolved, and no further action is required as the system is now functioning properly.'}]`
  - eval 侧切回来: `[{'key': 'ticket_id', 'value': '1'}, {'key': 'resolution', 'value': 'The issue with the trading system query'}, {'key': 'pos0', 'value': 'caused by a brief network delay'}, {'key': 'pos1', 'value': 'has been resolved'}, {'key': 'pos2', 'value': 'and no further action is required as the system is now functioning properly.'}]`
- `bfcl_gptoss/multi_turn_base_129|s5`
  - label_call: `resolve_ticket(ticket_id=1, resolution=The issue related to the previous transaction inquiry has been resolved by verifying the accuracy of the NVDA stock order, and the ticket has been marked as completed with no further action required.)`
  - annotate 侧真值: `[{'key': 'ticket_id', 'value': '1'}, {'key': 'resolution', 'value': 'The issue related to the previous transaction inquiry has been resolved by verifying the accuracy of the NVDA stock order, and the ticket has been marked as completed with no further action required.'}]`
  - eval 侧切回来: `[{'key': 'ticket_id', 'value': '1'}, {'key': 'resolution', 'value': 'The issue related to the previous transaction inquiry has been resolved by verifying the accuracy of the NVDA stock order'}, {'key': 'pos0', 'value': 'and the ticket has been marked as completed with no further action required.'}]`
- `bfcl_gptoss/multi_turn_base_140|s7`
  - label_call: `resolve_ticket(ticket_id=2, resolution=Self-resolved, no longer requiring assistance.)`
  - annotate 侧真值: `[{'key': 'ticket_id', 'value': '2'}, {'key': 'resolution', 'value': 'Self-resolved, no longer requiring assistance.'}]`
  - eval 侧切回来: `[{'key': 'ticket_id', 'value': '2'}, {'key': 'resolution', 'value': 'Self-resolved'}, {'key': 'pos0', 'value': 'no longer requiring assistance.'}]`
- `bfcl_gptoss/multi_turn_base_165|s12`
  - label_call: `contact_customer_support(booking_id=3426812, message=Urgent: I have encountered a discrepancy with my booking. Booking ID: 3426812, Transaction ID: 45451592, Travel Date: 2026-12-15, From: CRH, To: HKG, Class: economy, Cost: $290.00. Please review the details and resolve the issue as soon as possible.)`
  - annotate 侧真值: `[{'key': 'booking_id', 'value': '3426812'}, {'key': 'message', 'value': 'Urgent: I have encountered a discrepancy with my booking. Booking ID: 3426812, Transaction ID: 45451592, Travel Date: 2026-12-15, From: CRH, To: HKG, Class: economy, Cost: $290.00. Please review the details and resolve the issue as soon as possible.'}]`
  - eval 侧切回来: `[{'key': 'booking_id', 'value': '3426812'}, {'key': 'message', 'value': 'Urgent: I have encountered a discrepancy with my booking. Booking ID: 3426812'}, {'key': 'pos0', 'value': 'Transaction ID: 45451592'}, {'key': 'pos1', 'value': 'Travel Date: 2026-12-15'}, {'key': 'pos2', 'value': 'From: CRH'}, {'key': 'pos3', 'value': 'To: HKG'}, {'key': 'pos4', 'value': 'Class: economy'}, {'key': 'pos5', 'value': 'Cost: $290.00. Please review the details and resolve the issue as soon as possible.'}]`

## 偏差 2:题单一致但实现实例有缺口
三个模型共用同一份题单;某个 unit 的轨迹若一个可用事件都没出(思考 <40 字符 或 调用正则解析不出),该 unit 就不进本模型的数据集。所以现行门禁 G10「三模型 unit 集合完全相同」在 bfcl 上不成立,跨模型只是**近似**同题。
- train: 题单 140 题 -> 实现 140 题;缺 0 题
- val: 题单 40 题 -> 实现 39 题;缺 1 题: multi_turn_base_30
- test: 题单 20 题 -> 实现 20 题;缺 0 题

## 偏差 3:test 出现而 train 未出现的工具
这类工具在 label2id 里(tool_vocab.json 按全堆统计),不会被 eval_tool.py 丢掉,而是**必然判错** = 不可达的精度上限。
- 1 类: {'get_user_tickets': 1}
- 词表规模: train 89 / val 65 / test 51 类

## 偏差 4:test 堆厚度
- test 事件 109 / 实例 20 / 样本 3090
- ⚠ test 事件数 109 < 200:bootstrap 置信区间会很宽,且低 risk 档(0.05)很可能没有触发点、θ 全 null 导致 eval_causal_call 直接 SystemExit 退 1(先例 c1_q35_mext)。交接时必须点明。

## 题单真源
- 唯一真源 = 入库的 txt:/home/y-guo/reproduce/new1/pipeline/splits/bfcl_mtb_v1
- 入库的 {train,val,test}.txt 是唯一真源;上面的 md5 只是审计线索,推导源不在版本控制里
- 推导源 md5: {'train:train': '05b4a46d5ad9b4971df5c7403905524d', 'val:calA': '7ef720e4c36a5b7a3c6dbc3622efceb2', 'val:calB': 'f16f1e04587f4cfea8e8c096fd54ca30', 'test:test': 'f62473454e5bd8423b91ee0c5e7313c5', 'universe': '9af187d0363923e7b0f406a08887026c'}
