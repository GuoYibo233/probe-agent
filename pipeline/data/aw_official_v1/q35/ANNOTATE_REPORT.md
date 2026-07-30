# aw_official_v1 / q35 annotate 出厂报告

- SEED=20260729 MAX_BOUNDS=64 env=appworld model=qwen3.5-27b
- runs=['/home/y-guo/reproduce/new1/envs/runs/full_v1', '/home/y-guo/reproduce/new1/envs/runs/full_v2_topup', '/home/y-guo/reproduce/new1/envs/runs/w0_aw_official']
- config=pipeline/configs/aw_q35.json out=/home/y-guo/reproduce/new1/pipeline/data/aw_official_v1/q35
- 规则:全句边界前缀 / w=1/m_i 事件等权 / 官方题单三路切分 / 一模型一数据集

## appworld — q35
- 轨迹 315 / 任务实例 315 / 事件 6340 / 样本 70440(全模型事件 16030,过滤后留 6340)
- 边界数每事件: min 1 med 7 max 64(上限 64)
- 切分(官方题单,任务实例级): train 90实例·1834事件·18875样本 / val 57实例·1150事件·12738样本 / test 168实例·3356事件·38827样本
- 工具词表 143 类;top5 [('apis.api_docs.show_api_doc', 1111), ('apis.api_docs.show_api_descriptions', 858), ('apis.supervisor.show_profile', 323), ('apis.venmo.show_transactions', 307), ('apis.api_docs.show_app_descriptions', 300)]
- 长尾(出现<5次): 50 类
- 深度十桶样本数: [4143, 6407, 7407, 7505, 7361, 7553, 7492, 7119, 6274, 9179]
- 题干长度 p50=2022 p90=3306 max=20181 字符(超 4096 token 由训练脚本左截)
- 频率先验基线(test 事件级,猜 apis.api_docs.show_api_doc): 0.174
- 自检: 前缀断言 200/200 ✓;实例不跨 split ✓;题单归属抽查 train 20/20 val 20/20 test 20/20 ✓
