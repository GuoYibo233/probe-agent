# C 线交付手册：T5/T6/T7/T8 程序件与发射命令（写给 A 调度线）

> C 线（探针程序线）产出，2026-07-30 凌晨。所有脚本已过 CPU 级验证；
> GPU 发射、台账、record 登记全部归 A 线，走 gpu-run skill。
> 训练一律显式 `--out`（默认目录会覆盖废件区,脚本已加硬拦截）。

## 通用事实

- 分类头环境 `mbert-env/`；因果探针环境 `cprobe-env/`。
- 数据 `envs/bert_data/v3`；种子 20260729 已固化在各脚本内。
- `train_probe.py` 新增 `--input-mode`，**默认 full 行为逐位不变**，
  对在飞的 v3 训练和后续主线重训零影响。
- `eval_replay.py` 本线未动（T4 换算段归 A 线；消融评测经包装器自动继承）。

## T5 消融（六训练 + 六评测）

训练（no-think 每个几分钟可插空；no-hist 每个 1 卡 2–3h）：

```bash
# no-think ×3
mbert-env/bin/python envs/bert/train_probe.py --env tales    --data envs/bert_data/v3 --input-mode no-think --out envs/bert_runs/tales_v3_nothink
mbert-env/bin/python envs/bert/train_probe.py --env appworld --data envs/bert_data/v3 --input-mode no-think --out envs/bert_runs/appworld_v3_nothink
mbert-env/bin/python envs/bert/train_probe.py --env bfcl     --data envs/bert_data/v3 --input-mode no-think --out envs/bert_runs/bfcl_v3_nothink
# no-hist ×3
mbert-env/bin/python envs/bert/train_probe.py --env tales    --data envs/bert_data/v3 --input-mode no-hist --out envs/bert_runs/tales_v3_nohist
mbert-env/bin/python envs/bert/train_probe.py --env appworld --data envs/bert_data/v3 --input-mode no-hist --out envs/bert_runs/appworld_v3_nohist
mbert-env/bin/python envs/bert/train_probe.py --env bfcl     --data envs/bert_data/v3 --input-mode no-hist --out envs/bert_runs/bfcl_v3_nohist
```

评测（毕业后逐个，1 卡；包装器 monkeypatch 复用 eval_replay 全协议，
T4 换算段合入后自动继承）：

```bash
mbert-env/bin/python envs/bert/eval_replay_mode.py --mode no-hist  --env <env> --run envs/bert_runs/<env>_v3_nohist  --data envs/bert_data/v3
mbert-env/bin/python envs/bert/eval_replay_mode.py --mode no-think --env <env> --run envs/bert_runs/<env>_v3_nothink --data envs/bert_data/v3
```

- no-think 报告末尾追加 `nothink_plain_event_acc`（普通事件级准确率，
  规划书要求的退化口径），旧字段不动。
- 验收对表：三环境 × {历史单独 no-think / 思考单独 no-hist / 合流 v3 主线}。

## T6 跨模型双向矩阵（五训练 + 每环境四格评测）

数据已物化：`envs/bert_data/v3_xmodel/`（符号链接去重；计数验证见其
XMODEL_REPORT.md——规划书预期 920/1426 是 v2 口径，v3 超出系补采增量，
逐档核对无误）。bfcl 的 gptoss 列等 T3 v3.1 建库后重跑：
`python3 envs/bert/make_xmodel_splits.py --data envs/bert_data/v3_1 --out envs/bert_data/v3_1_xmodel`

训练（qwen 侧 ×3 + gptoss 侧 ×2，各 1 卡，数据量约主线一半）：

```bash
mbert-env/bin/python envs/bert/train_probe.py --env <env> --data envs/bert_data/v3_xmodel/train-qwen   --out envs/bert_runs/<env>_v3_xqwen    # tales/appworld/bfcl
mbert-env/bin/python envs/bert/train_probe.py --env <env> --data envs/bert_data/v3_xmodel/train-gptoss --out envs/bert_runs/<env>_v3_xgptoss  # tales/appworld
```

评测：eval_replay 的报告写进 `--run` 目录，**同一模型评多个数据配置必须
用符号链接分身目录，否则报告互相覆盖**：

```bash
mkdir -p envs/bert_runs/xmodel/<模型名>__<评测目录名>
ln -s ../../<训练run名>/best envs/bert_runs/xmodel/<模型名>__<评测目录名>/best
mbert-env/bin/python envs/bert/eval_replay.py --env <env> \
  --run envs/bert_runs/xmodel/<模型名>__<评测目录名> \
  --data envs/bert_data/v3_xmodel/<评测目录名>
```

每环境（有双侧数据的）跑满：

| 格 | 模型 | 评测目录 |
|---|---|---|
| qwen 主场 | <env>_v3_xqwen | eval-qwen_cal-qwen |
| qwen→gptoss 冷迁移 | <env>_v3_xqwen | eval-gptoss_cal-qwen |
| qwen→gptoss 只换校准 | <env>_v3_xqwen | eval-gptoss_cal-gptoss |
| gptoss 主场 | <env>_v3_xgptoss | eval-gptoss_cal-gptoss |
| gptoss→qwen 冷迁移 | <env>_v3_xgptoss | eval-qwen_cal-gptoss |
| gptoss→qwen 只换校准 | <env>_v3_xgptoss | eval-qwen_cal-qwen |
| 混训天花板(每侧) | <env>_v3（主线） | eval-<侧>_cal-full |

先验基线口径注意：矩阵评测目录的 tool_vocab 计数取校准侧训练频率，
报告里的 prior 读作"校准侧训练频率先验"。

## T7 抽取头（三训练 + 逐环境评测）

标签数据已产：`envs/bert_data/v3_params/`（定位率 appworld 0.833 / tales
0.807 / bfcl 0.917，深度单调上升；人工核对件 CHECK_50.md；重跑逐字节一致）。

训练（各 1 卡，实例量与主线同档：bfcl 3.9 万 / appworld 10.3 万 / tales
14.2 万）：

```bash
mbert-env/bin/python envs/bert/train_extractor.py --env bfcl     --out envs/bert_runs/bfcl_ext_v3
mbert-env/bin/python envs/bert/train_extractor.py --env appworld --out envs/bert_runs/appworld_ext_v3
mbert-env/bin/python envs/bert/train_extractor.py --env tales    --out envs/bert_runs/tales_ext_v3
```

评测（需对应环境分类头 run 的 REPLAY_REPORT + logits_test.pt 在位）：

```bash
mbert-env/bin/python envs/bert/eval_extract.py --env <env> \
  --run envs/bert_runs/<env>_v3 --extractor envs/bert_runs/<env>_ext_v3 --risk 0.05
```

注意事项：
- **判对主口径较规划书有一处偏离，汇报时要写明**：严格"预测区间解码==
  value"会被 BPE 前导空格/引号并 token 打成伪错（金标自身只能过 0.07–0.66），
  故主口径改为"字符区间覆盖真值且多余字符仅空白/标点"，严格列并排保留。
- 短值（≤3 字符）rfind 有撞巧合子串噪声（bfcl 已定位参数的 18.5%），训练
  评测同口径不偏袒，绝对数字含此噪声。
- `--risk` 必须命中分类头报告已有的 θ 档（0.1/0.05），否则报错退出。
- T3 出 v3_1 后重跑：`python3 envs/bert/param_label.py --data
  envs/bert_data/v3_1 --out envs/bert_data/v3_1_params`。

### 转交 A 线的一条修复建议（不归 C 线动手）

`envs/collect/build_dataset.py` 的 bfcl glob **未 sorted()**，readdir 序不稳
会使事件数在重跑间漂移（实测 2265↔2267），破坏"重跑逐字节一致"铁律。
T3 建 v3_1 前建议先修（一行 `sorted(glob.glob(...))`）。

## T8 因果探针（双底座 × 三环境，先 bfcl 探路）

脚本 `train_causal_probe.py` / `eval_replay_causal.py`（cprobe-env）。
对齐检查已过（CPU fp32，逐 token 增量 vs 整段一次前向：qwen maxdiff
9.5e-5@300tok、4.1e-5@1024tok；lfm 2.2e-5；门槛 1e-4 未放宽），开训时
脚本自动再跑一遍并落 ALIGN_CHECK.json，FAIL 即拒训。
计算量对比已可先报：**探完 test 全部轨迹，因果探针 token 量是 ModernBERT
的 1/19.8（bfcl）/ 1/26.4（appworld）/ 1/34.1（tales）**。

```bash
P=cprobe-env/bin/python
# 波次 1：bfcl 探路（各几分钟，出数与 bfcl_v3 并排看分类差距）
$P envs/bert/train_causal_probe.py --base qwen --env bfcl --out envs/bert_runs/bfcl_v3_causal_qwen
$P envs/bert/train_causal_probe.py --base lfm  --env bfcl --out envs/bert_runs/bfcl_v3_causal_lfm
$P envs/bert/eval_replay_causal.py --env bfcl --run envs/bert_runs/bfcl_v3_causal_qwen
$P envs/bert/eval_replay_causal.py --env bfcl --run envs/bert_runs/bfcl_v3_causal_lfm
# 波次 2：四条并行（一卡一条；tales 开 --grad-ckpt）
$P envs/bert/train_causal_probe.py --base qwen --env appworld --out envs/bert_runs/appworld_v3_causal_qwen
$P envs/bert/train_causal_probe.py --base lfm  --env appworld --out envs/bert_runs/appworld_v3_causal_lfm
$P envs/bert/train_causal_probe.py --base qwen --env tales --out envs/bert_runs/tales_v3_causal_qwen --grad-ckpt
$P envs/bert/train_causal_probe.py --base lfm  --env tales --out envs/bert_runs/tales_v3_causal_lfm  --grad-ckpt
# 评测同构:eval_replay_causal.py --env <env> --run <对应 out>
```

- 上卡前建议先 `--align-only --device cuda`（几十秒）确认真实窗口 PASS；
  若偶发 FAIL 先看 reldiff_hidden：1e-6 量级=fp32 噪声（量级大所致），
  1e-3 以上才是真算错。放宽门槛需用户点头。
- 显存（A6000 48G,bs4,4096）：qwen ≈20G（--grad-ckpt 降至 ~14G），lfm 减半。
  时长：六条训练合计 **2–3 GPU 小时**（每事件只读一遍,比分类头线便宜一个量级）。
- **窗口口径不对称要写进汇报**：整段前向下超 4096 token 的事件早期边界
  落窗外（tales 14.1%/appworld 2.2%/bfcl 0%），训练跳过、评测永不触发，
  机械压低 tales 的 coverage/earliness。**建议加跑一条对照**：tales qwen
  `--max-len 8192 --bs 2 --grad-ckpt`（最长事件 ≤9129 token,可全覆盖），
  是否采纳由 A 线/用户定。
- LFM2.5 许可是 LFM Open License v1.0（非 Apache），汇报如实标注。
- T9 闭环连带铁律：线上增量喂 LFM 必须严格逐 token，禁分块（7ae80b0 分块
  静默算错前科——见 check_causal_candidates.py 判定）。

