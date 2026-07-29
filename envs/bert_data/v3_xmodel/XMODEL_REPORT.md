# 跨模型双向矩阵数据物化报告(make_xmodel_splits.py)

- 来源 envs/bert_data/v3 -> envs/bert_data/v3_xmodel;侧=样本 model 字段前缀(qwen*/gpt-oss*)

## tales

| split | qwen 事件·样本 | gptoss 事件·样本 |
|---|---|---|
| train | 1425·64895 | 1235·77726 |
| calA | 220·9980 | 183·11549 |
| calB | 253·10605 | 183·11444 |
| test | 229·10120 | 179·11233 |

- train 分模型事件计数: gpt-oss-120b 1235 / qwen3.5-27b 499 / qwen3.6-27b 926
- qwen 训练侧事件 1425 vs 规划书预期≈920(v2 口径): 超出——v2 口径逐档核对已吻合,增量来自 full_v2_topup 补采,计数无误

## appworld

| split | qwen 事件·样本 | gptoss 事件·样本 |
|---|---|---|
| train | 2434·21748 | 1211·49254 |
| calA | 363·2881 | 181·8198 |
| calB | 386·5578 | 186·7640 |
| test | 555·5371 | 236·11097 |

- train 分模型事件计数: gpt-oss-120b 1211 / qwen3.5-27b 708 / qwen3.6-27b 1726
- qwen 训练侧事件 2434 vs 规划书预期≈1426(v2 口径): 超出——v2 口径逐档核对已吻合,增量来自 full_v2_topup 补采,计数无误

## bfcl

| split | qwen 事件·样本 | gptoss 事件·样本 |
|---|---|---|
| train | 1605·25061 | 0·0 |
| calA | 220·4120 | 0·0 |
| calB | 214·3675 | 0·0 |
| test | 226·3487 | 0·0 |

- train 分模型事件计数: qwen3.5-27b 855 / qwen3.6-27b 750
- ⚠️ gptoss 侧无数据,相关目录跳过(bfcl 等 T3 v3.1 后重跑本脚本)

## 用法(A 线发射用)

训练(每侧一模型,--out 必须显式):
```
train_probe.py --env <env> --data envs/bert_data/v3_xmodel/train-<侧> --out envs/bert_runs/<env>_v3_x<侧>
```
评测四格+天花板(eval_replay 报告写进 --run 目录,同一模型评多个数据配置必须用符号链接分身,否则互相覆盖):
```
mkdir -p envs/bert_runs/<env>_x/<模型>__<评测目录名>
ln -s ../../<训练run>/best envs/bert_runs/<env>_x/<模型>__<评测目录名>/best
eval_replay.py --env <env> --run envs/bert_runs/<env>_x/<...> --data envs/bert_data/v3_xmodel/eval-<考侧>_cal-<校准侧>
```
- 主场 = train-X 模型 × eval-X_cal-X;冷迁移客场 = train-X × eval-Y_cal-X;只换校准客场 = train-X × eval-Y_cal-Y(纯 CPU 差价在校准,但 logits 仍需打分);混训天花板 = 主线 v3 模型 × eval-<侧>_cal-full。
