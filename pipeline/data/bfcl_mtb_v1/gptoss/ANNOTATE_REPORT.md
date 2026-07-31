# bfcl_mtb_v1 / gptoss annotate 出厂报告

- SEED=20260729 MAX_BOUNDS=64 env=bfcl model=gpt-oss-120b
- runs=['/home/y-guo/reproduce/new1/envs/runs/full_v1', '/home/y-guo/reproduce/new1/envs/runs/full_v2_topup']
- config=pipeline/configs/bfcl_gptoss.json out=/home/y-guo/reproduce/new1/pipeline/data/bfcl_mtb_v1/gptoss
- 规则:全句边界前缀 / w=1/m_i 事件等权 / 三路切分(冻结 v3_1 老三堆,任务实例级;BFCL 无官方分区) / 一模型一数据集

## bfcl — gptoss
- 轨迹 199 / 任务实例 199 / 事件 1060 / 样本 32163(全模型事件 3325,过滤后留 1060)
- 边界数每事件: min 2 med 25 max 64(上限 64)
- 切分(冻结 v3_1 老三堆,任务实例级;BFCL 无官方分区): train 140实例·748事件·22738样本 / val 39实例·203事件·6335样本 / test 20实例·109事件·3090样本
- 工具词表 94 类;top5 [('get_stock_info', 53), ('pressBrakePedal', 44), ('lockDoors', 38), ('get_flight_cost', 37), ('cd', 36)]
- 长尾(出现<5次): 33 类
- 深度十桶样本数: [2104, 3068, 3209, 3219, 3319, 3245, 3276, 3173, 3239, 4311]
- 题干长度 p50=1784 p90=4571 max=28328 字符(超 4096 token 由训练脚本左截)
- 频率先验基线(test 事件级,猜 get_stock_info): 0.037
- 自检: 前缀断言 200/200 ✓;实例不跨 split ✓;题单归属抽查 train 20/20 val 20/20 test 20/20 ✓
