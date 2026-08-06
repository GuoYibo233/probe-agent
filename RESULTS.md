# RESULTS — 实验统计数字总表

> 本文件由 `python3 run.py record render` 自动生成，**不要手改**。
> 数据源是 append-only 的 `ops/runs.jsonl`；改数字请补一条 finish 事件。
> 方向决策的来龙去脉看 [TIMELINE.md](TIMELINE.md)，原始数据不在 git 里。

| run_id | 日期 | 方向 | commit | 模型 | 状态 | 关键数字 | 结论 |
|---|---|---|---|---|---|---|---|
| `hcap` | 2026-08-06 19:29 | learn/vllm | `364242b` | gpt-oss-120b | ok | steps=13 completed=1 out_tokens_total=39088 steps_hit_max_tokens=3 toolcall_out_tokens=484 harmony_vs_chat_out_tokens=136 | 客户端自拼 harmony 走 /v1/completions 与 chat 路端到端等价(同一组消息 prompt/输出 token 数与 reasoning/content 逐字相同);抓到 13 步真实逐 token 流,其中 3 步撞 8192 上限 |

## 逐条详情

### `hcap`

- **想验证什么**：验客户端自拼 harmony 走 /v1/completions 能不能跑通,并抓一条 AppWorld 轨迹的逐 token 原始流(return_token_ids)做教学页
- **结论**：客户端自拼 harmony 走 /v1/completions 与 chat 路端到端等价(同一组消息 prompt/输出 token 数与 reasoning/content 逐字相同);抓到 13 步真实逐 token 流,其中 3 步撞 8192 上限
- **方向**：learn/vllm ｜ **状态**：ok ｜ **起止**：2026-08-06 19:29 → 2026-08-06 19:42
- **代码**：`364242b` (分支 main)
- **机器**：tokyo108 GPU 2
- **模型 / 种子**：gpt-oss-120b / 0
- **参数**：api=harmony temperature=0.0 start_date=2026-08-06 reasoning_effort=high
- **数字**：steps=13 completed=1 out_tokens_total=39088 steps_hit_max_tokens=3 toolcall_out_tokens=484 harmony_vs_chat_out_tokens=136
- **原始数据**：`/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/envs/runs/hcap`（不在 git 里）
- **日志**：`/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/logs/new1_hcap_srv.log`
- **命令**：`envs/appworld/venv/bin/python envs/collect/run_appworld.py --api harmony --base-url http://tokyo108:8113/v1 --model gpt-oss-120b`
