# aw_official_v1 / q36 annotate 出厂报告

- SEED=20260729 MAX_BOUNDS=64 env=appworld model=qwen3.6-27b
- runs=['/home/y-guo/reproduce/new1/envs/runs/full_v1', '/home/y-guo/reproduce/new1/envs/runs/full_v2_topup', '/home/y-guo/reproduce/new1/envs/runs/w0_aw_official']
- config=pipeline/configs/aw_q36.json out=/home/y-guo/reproduce/new1/pipeline/data/aw_official_v1/q36
- 规则:全句边界前缀 / w=1/m_i 事件等权 / 官方题单三路切分 / 一模型一数据集

## appworld — q36
- 轨迹 315 / 任务实例 315 / 事件 5738 / 样本 52104(全模型事件 16030,过滤后留 5738)
- 边界数每事件: min 1 med 3 max 64(上限 64)
- 切分(官方题单,任务实例级): train 90实例·1639事件·13591样本 / val 57实例·949事件·9249样本 / test 168实例·3150事件·29264样本
- 工具词表 151 类;top5 [('apis.api_docs.show_api_doc', 972), ('apis.api_docs.show_api_descriptions', 779), ('apis.api_docs.show_app_descriptions', 448), ('apis.supervisor.show_profile', 315), ('apis.supervisor.complete_task', 280)]
- 长尾(出现<5次): 52 类
- 深度十桶样本数: [2840, 4362, 5168, 5326, 5325, 5417, 5210, 5036, 4799, 8621]
- 题干长度 p50=1888 p90=4356 max=34074 字符(超 4096 token 由训练脚本左截)
- 频率先验基线(test 事件级,猜 apis.api_docs.show_api_doc): 0.159
- 自检: 前缀断言 200/200 ✓;实例不跨 split ✓;题单归属抽查 train 20/20 val 20/20 test 20/20 ✓
