# aw_official_v1 / gptoss annotate 出厂报告

- SEED=20260729 MAX_BOUNDS=64 env=appworld model=gpt-oss-120b
- runs=['/home/y-guo/reproduce/new1/envs/runs/full_v1', '/home/y-guo/reproduce/new1/envs/runs/full_v2_topup', '/home/y-guo/reproduce/new1/envs/runs/w0_aw_official']
- config=pipeline/configs/aw_gptoss.json out=/home/y-guo/reproduce/new1/pipeline/data/aw_official_v1/gptoss
- 规则:全句边界前缀 / w=1/m_i 事件等权 / 官方题单三路切分 / 一模型一数据集

## appworld — gptoss
- 轨迹 315 / 任务实例 315 / 事件 3952 / 样本 166103(全模型事件 16030,过滤后留 3952)
- 边界数每事件: min 1 med 51 max 64(上限 64)
- 切分(官方题单,任务实例级): train 90实例·1141事件·47296样本 / val 57实例·673事件·28893样本 / test 168实例·2138事件·89914样本
- 工具词表 85 类;top5 [('apis.api_docs.show_api_doc', 1653), ('apis.api_docs.show_api_descriptions', 637), ('apis.supervisor.show_profile', 604), ('apis.api_docs.show_app_descriptions', 319), ('apis.supervisor.show_account_passwords', 147)]
- 长尾(出现<5次): 58 类
- 深度十桶样本数: [12626, 14884, 15456, 15819, 16277, 16779, 17442, 17698, 17847, 21275]
- 题干长度 p50=4528 p90=13208 max=45052 字符(超 4096 token 由训练脚本左截)
- 频率先验基线(test 事件级,猜 apis.api_docs.show_api_doc): 0.404
- 自检: 前缀断言 200/200 ✓;实例不跨 split ✓;题单归属抽查 train 20/20 val 20/20 test 20/20 ✓
