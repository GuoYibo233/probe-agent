# full_v1 — BERT 训练量级的思考+工具调用轨迹采集（2026-07-29 发射）

目标:够训一个"从思考前缀预测下一工具调用"的 BERT 的数据量,
预计 ~6000+ 个带完整思考段的调用事件。数据只增不删。

## 批次与端点

| 批次 | 模型 | 端点 | 规模 | 输出目录 |
|---|---|---|---|---|
| appworld_q35 | qwen3.5-27b | 8101 | dev 全 57 题,2 shard | appworld_q35/ |
| appworld_q36 | qwen3.6-27b | 8104 | 同上 | appworld_q36/ |
| appworld_gptoss | gpt-oss-120b (chat,high) | 8103 | 同上 | appworld_gptoss/ |
| tales_q35 | qwen3.5-27b | 8101 | 多房间加难版,seeds 31–50 | tales_q35/ |
| tales_q36 | qwen3.6-27b | 8104 | 同上 | tales_q36/ |
| tales_gptoss | gpt-oss-120b (chat,high) | 8103 | 同上 | tales_gptoss/ |
| bfcl_q35 | qwen3.5-27b | 8101 | multi_turn_base 全 200 | bfcl_q35/(含此前 21 条,若重复按 id 去重) |
| bfcl_q36 | qwen3.6-27b | 8104 | 同上 | bfcl_q36/ |

TALES 加难参数(经 pipecheck_hard 单 seed 验证,多房间/带门/BBQ 可达):
`numLocations=5, numIngredients=3, numDistractorItems=8, includeDoors=1, limitInventorySize=0`

## 数据格式

- TALES/AppWorld: 自研 JSONL(meta/gen/env/final),gen.reasoning 为完整思考,
  raw 模式含原始文本;格式定义见 collect/common.py
- BFCL: 官方 result.json,思考在 inference_log 内 assistant 消息的
  reasoning_content 字段(qwen.py handler 已打 <think> 开头补丁)
- 服务端口异动、进程日志: logs/ 子目录

## 最终清点（2026-07-29 采集完毕）

- **631 条轨迹 / ~8789 个带思考的调用事件 / 32.8M 字符思考文本 / 94MB**
- AppWorld 171 条:q3.5 acc 0.19(1161 调用) / q3.6 **0.61**(984) / gpt-oss 0.35(687,思考 3.9M 字符)
- BFCL 400 条:官方状态比对 q3.5 **70.5%** vs q3.6 54.5%(与 AppWorld 排序对调,
  疑为 q3.6 对括号调用格式的服从度问题,待错例验证)
- TALES 加难版 60 条:三模型胜率全 0(40 步上限内无人通关),但每轨迹跑满 40 步、
  思考极肥(gpt-oss 12.3M 字符)。**该配置作 BERT 训练数据合格,作速度-准确率
  实验需要回调难度**(建议 numLocations=3 或 max-steps 60 找可赢中间档)
- q3.6 的 TALES 分片曾因单流吞吐过低重组为 4 路并行(重组后速率 ×2),
  s34/s44 各弃过一次 36 步半成品重跑

## 已知边界

- tau2 不在本批(其日志不存思考,待补丁)
- gpt-oss 不跑 BFCL(其 harmony 工具格式与 BFCL qwen handler 不兼容,未适配)
- 8102(GPU4 上冗余的 qwen3.6)在其收尾任务完成后释放,不参与本批
