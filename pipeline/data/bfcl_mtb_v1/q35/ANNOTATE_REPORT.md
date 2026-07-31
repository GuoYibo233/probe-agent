# bfcl_mtb_v1 / q35 annotate 出厂报告

- SEED=20260729 MAX_BOUNDS=64 env=bfcl model=qwen3.5-27b
- runs=['/home/y-guo/reproduce/new1/envs/runs/full_v1', '/home/y-guo/reproduce/new1/envs/runs/full_v2_topup']
- config=pipeline/configs/bfcl_q35.json out=/home/y-guo/reproduce/new1/pipeline/data/bfcl_mtb_v1/q35
- 规则:全句边界前缀 / w=1/m_i 事件等权 / 三路切分(冻结 v3_1 老三堆,任务实例级;BFCL 无官方分区) / 一模型一数据集

## bfcl — q35
- 轨迹 200 / 任务实例 200 / 事件 1209 / 样本 11094(全模型事件 3325,过滤后留 1209)
- 边界数每事件: min 1 med 7 max 60(上限 64)
- 切分(冻结 v3_1 老三堆,任务实例级;BFCL 无官方分区): train 140实例·855事件·7632样本 / val 40实例·234事件·2472样本 / test 20实例·120事件·990样本
- 工具词表 94 类;top5 [('startEngine', 79), ('cd', 52), ('pressBrakePedal', 44), ('get_stock_info', 43), ('get_nearest_airport_by_city', 39)]
- 长尾(出现<5次): 31 类
- 深度十桶样本数: [675, 1070, 1197, 1141, 1167, 1023, 1010, 994, 1040, 1777]
- 题干长度 p50=846 p90=1475 max=3533 字符(超 4096 token 由训练脚本左截)
- 频率先验基线(test 事件级,猜 startEngine): 0.058
- 自检: 前缀断言 200/200 ✓;实例不跨 split ✓;题单归属抽查 train 20/20 val 20/20 test 20/20 ✓
