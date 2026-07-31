# alf_official_v1 / gptoss annotate 出厂报告

- SEED=20260729 MAX_BOUNDS=64 env=alfworld model=gpt-oss-120b
- runs=['/home/y-guo/reproduce/new1/envs/runs/c2_alfworld']
- config=pipeline/configs/alf_gptoss.json out=/home/y-guo/reproduce/new1/pipeline/data/alf_official_v1/gptoss
- 规则:全句边界前缀 / w=1/m_i 事件等权 / 三路切分(官方题单,任务实例级) / 一模型一数据集

## alfworld — gptoss
- 轨迹 474 / 任务实例 474 / 事件 12883 / 样本 633392(全模型事件 21830,过滤后留 12883)
- 边界数每事件: min 7 med 56 max 64(上限 64)
- 切分(官方题单,任务实例级): train 200实例·5510事件·269259样本 / val 140实例·3876事件·190180样本 / test 134实例·3497事件·173953样本
- 工具词表 12 类;top5 [('go', 6165), ('open', 2862), ('examine', 1407), ('take', 778), ('move', 649)]
- 长尾(出现<5次): 0 类
- 深度十桶样本数: [52445, 56182, 58790, 60164, 61290, 62614, 64528, 66056, 68138, 83185]
- 题干长度 p50=2085 p90=5634 max=33559 字符(超 4096 token 由训练脚本左截)
- 频率先验基线(test 事件级,猜 go): 0.470
- 自检: 前缀断言 200/200 ✓;实例不跨 split ✓;题单归属抽查 train 20/20 val 20/20 test 20/20 ✓
- 模板切不动而丢弃的步: 12 ({'no_template': 12});官方模板 13 条,工具词表应 ≤13 类
