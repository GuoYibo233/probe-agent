# alf_official_v1 / q36 annotate 出厂报告

- SEED=20260729 MAX_BOUNDS=64 env=alfworld model=qwen3.6-27b
- runs=['/home/y-guo/reproduce/new1/envs/runs/c2_alfworld']
- config=pipeline/configs/alf_q36.json out=/home/y-guo/reproduce/new1/pipeline/data/alf_official_v1/q36
- 规则:全句边界前缀 / w=1/m_i 事件等权 / 三路切分(官方题单,任务实例级) / 一模型一数据集

## alfworld — q36
- 轨迹 474 / 任务实例 474 / 事件 8947 / 样本 149273(全模型事件 21830,过滤后留 8947)
- 边界数每事件: min 1 med 6 max 64(上限 64)
- 切分(官方题单,任务实例级): train 200实例·4048事件·63556样本 / val 140实例·2753事件·42912样本 / test 134实例·2146事件·42805样本
- 工具词表 12 类;top5 [('go', 4856), ('open', 2308), ('take', 612), ('move', 467), ('look', 318)]
- 长尾(出现<5次): 1 类
- 深度十桶样本数: [8572, 12133, 14120, 15038, 14534, 14812, 15264, 15604, 15818, 23378]
- 题干长度 p50=1176 p90=3516 max=18138 字符(超 4096 token 由训练脚本左截)
- 频率先验基线(test 事件级,猜 go): 0.548
- 自检: 前缀断言 200/200 ✓;实例不跨 split ✓;题单归属抽查 train 20/20 val 20/20 test 20/20 ✓
- 模板切不动而丢弃的步: 12 ({'no_template': 12});官方模板 13 条,工具词表应 ≤13 类
