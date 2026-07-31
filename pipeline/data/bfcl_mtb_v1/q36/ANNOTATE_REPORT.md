# bfcl_mtb_v1 / q36 annotate 出厂报告

- SEED=20260729 MAX_BOUNDS=64 env=bfcl model=qwen3.6-27b
- runs=['/home/y-guo/reproduce/new1/envs/runs/full_v1', '/home/y-guo/reproduce/new1/envs/runs/full_v2_topup']
- config=pipeline/configs/bfcl_q36.json out=/home/y-guo/reproduce/new1/pipeline/data/bfcl_mtb_v1/q36
- 规则:全句边界前缀 / w=1/m_i 事件等权 / 三路切分(冻结 v3_1 老三堆,任务实例级;BFCL 无官方分区) / 一模型一数据集

## bfcl — q36
- 轨迹 196 / 任务实例 196 / 事件 1056 / 样本 25249(全模型事件 3325,过滤后留 1056)
- 边界数每事件: min 1 med 11 max 64(上限 64)
- 切分(冻结 v3_1 老三堆,任务实例级;BFCL 无官方分区): train 139实例·750事件·17429样本 / val 38实例·200事件·5323样本 / test 19实例·106事件·2497样本
- 工具词表 94 类;top5 [('cd', 52), ('startEngine', 51), ('get_stock_info', 43), ('pressBrakePedal', 35), ('echo', 32)]
- 长尾(出现<5次): 30 类
- 深度十桶样本数: [1815, 2067, 2229, 2341, 2380, 2553, 2581, 2689, 2739, 3855]
- 题干长度 p50=1891 p90=5634 max=14676 字符(超 4096 token 由训练脚本左截)
- 频率先验基线(test 事件级,猜 cd): 0.066
- 自检: 前缀断言 200/200 ✓;实例不跨 split ✓;题单归属抽查 train 20/20 val 20/20 test 19/19 ✓
