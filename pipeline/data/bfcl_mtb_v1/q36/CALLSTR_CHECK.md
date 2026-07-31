# bfcl_mtb_v1 / q36 真值调用串回读检查(check_callstr.py)

- SEED=20260729 env=bfcl model=qwen3.6-27b
- config=pipeline/configs/bfcl_q36.json data=/home/y-guo/reproduce/new1/pipeline/data/bfcl_mtb_v1/q36
- 口径:对每个事件的 label_call 调 `eval_causal_call.parse_call`,再把 `(key, norm(value))` 与该事件的 `args_named` 逐位比;全等才算回读成功。

## 结构性门禁
- 门禁 C 2 项 traj_runs 均为 run 目录本身 ✓
- 门禁 A 全部 25249 行 model==qwen3.6-27b ✓
- 门禁 B 样本键 25249 个全唯一;196 个 unit 各对一条 traj ✓
- 门禁 D 题单归属全量核对(非抽样)✓
- 门禁 E 报告文案与 SPLIT_REPORT 一致 ✓(official_split_exists=False)

## 偏差 1:真值调用串回读
- 事件 1056;回读成功 1031(**0.9763**),失败 25(**0.0237**)
- 失败按 split: {'test': 5, 'train': 15, 'val': 5}
- 工具名切不回来的事件: 0
- 参数实例 1580;回读成功 1555(**0.9842**)
- 参数值里含逗号的实例: 74(0.0468)← 这是失败的主因
- **结论:params_all_ok / full_call_ok 的天花板是 0.9763**,生成侧写得再对也拿不到剩下那部分。不修口径的理由见文件头。

### 失败样例(前 5 条)
- `bfcl_q36/multi_turn_base_103|s12`
  - label_call: `send_message(receiver_id=USR002, message=Dear Customer Service, please confirm the successful execution of my order for 150 shares of Omega Industries at the current market price, and verify the order details under reference ID USR002. Thank you.)`
  - annotate 侧真值: `[{'key': 'receiver_id', 'value': 'USR002'}, {'key': 'message', 'value': 'Dear Customer Service, please confirm the successful execution of my order for 150 shares of Omega Industries at the current market price, and verify the order details under reference ID USR002. Thank you.'}]`
  - eval 侧切回来: `[{'key': 'receiver_id', 'value': 'USR002'}, {'key': 'message', 'value': 'Dear Customer Service'}, {'key': 'pos0', 'value': 'please confirm the successful execution of my order for 150 shares of Omega Industries at the current market price'}, {'key': 'pos1', 'value': 'and verify the order details under reference ID USR002. Thank you.'}]`
- `bfcl_q36/multi_turn_base_106|s9`
  - label_call: `resolve_ticket(ticket_id=1, resolution=The issue with the trading system query, caused by a brief network delay, has been resolved, and no further action is required as the system is now functioning properly.)`
  - annotate 侧真值: `[{'key': 'ticket_id', 'value': '1'}, {'key': 'resolution', 'value': 'The issue with the trading system query, caused by a brief network delay, has been resolved, and no further action is required as the system is now functioning properly.'}]`
  - eval 侧切回来: `[{'key': 'ticket_id', 'value': '1'}, {'key': 'resolution', 'value': 'The issue with the trading system query'}, {'key': 'pos0', 'value': 'caused by a brief network delay'}, {'key': 'pos1', 'value': 'has been resolved'}, {'key': 'pos2', 'value': 'and no further action is required as the system is now functioning properly.'}]`
- `bfcl_q36/multi_turn_base_11|s4`
  - label_call: `post_tweet(content=file1.txt, file2.txt #fileshowcase, tags=["#fileshowcase"])`
  - annotate 侧真值: `[{'key': 'content', 'value': 'file1.txt, file2.txt #fileshowcase'}, {'key': 'tags', 'value': '["#fileshowcase"]'}]`
  - eval 侧切回来: `[{'key': 'content', 'value': 'file1.txt'}, {'key': 'pos0', 'value': 'file2.txt #fileshowcase'}, {'key': 'tags', 'value': '["#fileshowcase"]'}]`
- `bfcl_q36/multi_turn_base_141|s11`
  - label_call: `send_message(receiver_id=USR005, message=100 shares of GOOG purchased, thoughts?)`
  - annotate 侧真值: `[{'key': 'receiver_id', 'value': 'USR005'}, {'key': 'message', 'value': '100 shares of GOOG purchased, thoughts?'}]`
  - eval 侧切回来: `[{'key': 'receiver_id', 'value': 'USR005'}, {'key': 'message', 'value': '100 shares of GOOG purchased'}, {'key': 'pos0', 'value': 'thoughts?'}]`
- `bfcl_q36/multi_turn_base_186|s8`
  - label_call: `contact_customer_support(booking_id=3426812, message=There has been a problem with my booking and I previously reached out to support without any feedback yet. Kindly contact customer support on my behalf, emphasizing the smooth facilitation of my travel arrangements.)`
  - annotate 侧真值: `[{'key': 'booking_id', 'value': '3426812'}, {'key': 'message', 'value': 'There has been a problem with my booking and I previously reached out to support without any feedback yet. Kindly contact customer support on my behalf, emphasizing the smooth facilitation of my travel arrangements.'}]`
  - eval 侧切回来: `[{'key': 'booking_id', 'value': '3426812'}, {'key': 'message', 'value': 'There has been a problem with my booking and I previously reached out to support without any feedback yet. Kindly contact customer support on my behalf'}, {'key': 'pos0', 'value': 'emphasizing the smooth facilitation of my travel arrangements.'}]`

## 偏差 2:题单一致但实现实例有缺口
三个模型共用同一份题单;某个 unit 的轨迹若一个可用事件都没出(思考 <40 字符 或 调用正则解析不出),该 unit 就不进本模型的数据集。所以现行门禁 G10「三模型 unit 集合完全相同」在 bfcl 上不成立,跨模型只是**近似**同题。
- train: 题单 140 题 -> 实现 139 题;缺 1 题: multi_turn_base_63
- val: 题单 40 题 -> 实现 38 题;缺 2 题: multi_turn_base_187, multi_turn_base_84
- test: 题单 20 题 -> 实现 19 题;缺 1 题: multi_turn_base_176

## 偏差 3:test 出现而 train 未出现的工具
这类工具在 label2id 里(tool_vocab.json 按全堆统计),不会被 eval_tool.py 丢掉,而是**必然判错** = 不可达的精度上限。
- 1 类: {'get_user_tickets': 1}
- 词表规模: train 89 / val 70 / test 47 类

## 偏差 4:test 堆厚度
- test 事件 106 / 实例 19 / 样本 2497
- ⚠ test 事件数 106 < 200:bootstrap 置信区间会很宽,且低 risk 档(0.05)很可能没有触发点、θ 全 null 导致 eval_causal_call 直接 SystemExit 退 1(先例 c1_q35_mext)。交接时必须点明。

## 题单真源
- 唯一真源 = 入库的 txt:/home/y-guo/reproduce/new1/pipeline/splits/bfcl_mtb_v1
- 入库的 {train,val,test}.txt 是唯一真源;上面的 md5 只是审计线索,推导源不在版本控制里
- 推导源 md5: {'train:train': '05b4a46d5ad9b4971df5c7403905524d', 'val:calA': '7ef720e4c36a5b7a3c6dbc3622efceb2', 'val:calB': 'f16f1e04587f4cfea8e8c096fd54ca30', 'test:test': 'f62473454e5bd8423b91ee0c5e7313c5', 'universe': '9af187d0363923e7b0f406a08887026c'}
