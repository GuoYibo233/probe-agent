# bert_data v1 出厂报告

- SEED = 20260729(切点选择+轨迹切分+QA抽样共用;重跑逐样本一致)
- 事件 7076 个 -> 样本 25005 道
- 切分(按轨迹,环境×模型分层): train 20044 / val 2495 / test 2466
- 深度桶(0-25/25-50/50-75/75-100%): [5478, 6326, 6113, 7088]
- 工具词表 193 类;top5 [('TALES:open', 5184), ('APPWORLD:apis.api_docs.show_api_doc', 2354), ('APPWORLD:apis.api_docs.show_api_descriptions', 1386), ('TALES:move', 1330), ('APPWORLD:apis.supervisor.show_profile', 793)]
- 只出现<5次的长尾类: 23 类
- 题干长度(字符) p50=1460 p90=5882 max=33945
- 分环境×模型样本数: {('APPWORLD', 'gpt-oss-120b'): 2610, ('APPWORLD', 'qwen3.5-27b'): 3702, ('APPWORLD', 'qwen3.6-27b'): 2815, ('TALES', 'gpt-oss-120b'): 2880, ('TALES', 'qwen3.5-27b'): 3071, ('TALES', 'qwen3.6-27b'): 2189, ('BFCL', 'qwen3.5-27b'): 3946, ('BFCL', 'qwen3.6-27b'): 3792}
- 泄漏自检: 前缀=原文切片(逐题 assert 通过);train/val/test 轨迹零交集 = True
- 训练时注意: 超 4096 token 由训练脚本左截(truncation_side=left),本数据不截
