# 新流水线施工图 — 2026-07-31

> 配套 `2026-07-31-pipeline-plan.md` 第 1 波的**工程细节**：五段每段写清
> 干什么 / 输入输出 / 复用哪个旧件 / 新写什么 / 怎么验收；凡是碰 GPU 的段落，
> 都配一个**请示计划**——什么时候向用户请示、请示时给看什么、批准词是什么、
> 批准后怎么监控收尾。
>
> **请示铁律（2026-07-31 定，写进记忆）**：GPU 发射必须拿到明确指向发射的话
> （"发射"/"跑吧"）；回答子话题的"就这样吧/可以"一律不算发射许可。

---

## 0. 总体骨架

- 顶层目录 `pipeline/`，五个子目录一段一个：`collect/ annotate/ train/ eval/ inject/`，
  外加 `configs/`（实验配置，进 git）、`data/` 与 `runs/`（产物，不进 git，仿照
  `envs/bert_data` 的 gitignore 模式：排除一切、只留 `.md`）。
- **配置驱动**：一个实验一个 json（env / model / backbone / head / split 方案 /
  seed / 数据路径），run_id 由配置推导，四处一致（数据目录 / tmux / 台账 / commit）。
- **双环境铁律照旧**：ModernBERT 段一律 `mbert-env` 的 python（transformers 4.57.6 钉死），
  因果段一律 `cprobe-env`（≥5.14），采集段用各环境自己的 venv。pipeline 代码不跨环境
  import，段与段之间只通过落盘文件交接。
- seed 20260729 写死进配置模板，跟着每份报告走。

## 1. collect 段（采集）

**干什么**：收编三个旧采集器，新写一个"发射清单生成器"。

- **复用（一字不改）**：`envs/collect/run_appworld.py` / `run_tales.py` /
  `bfcl_gptoss/` 三个采集器本体，`common.py` 的 Chat/TrajLog，SYSTEM 提示词，
  gpt-oss 的 `--api chat --reasoning-effort high` 档位。幂等续采
  （`--resume`、分片 `--num-shards/--shard-id`）都是现成的。
- **新写**：`collect/gen_launch.py`——输入一份采集清单 json
  （模型 → 实例数 → 端口 → 卡位 → split/题单 → 分片数），输出三样：
  服务端发射脚本（照 `envs/serve_logs/launch_vllm_topup.py` 的 ssh+tmux 模板，
  含 H100 上 Qwen 要 `--max-num-seqs 512` 这类已知坑）、客户端发射脚本
  （照 `full_v2_topup/launch_clients.sh` 模板）、`MANIFEST.md` 落到 run 目录。
- **验收**：生成的脚本与旧模板逐参数 diff 核对；先发 1 题 smoke，轨迹 jsonl
  里见到思考文本和工具调用才算通。

**GPU 请示计划**：

| 项 | 内容 |
|---|---|
| 请示时机 | 发射脚本生成完 + smoke 通过后 |
| 请示给看 | 卡位表（哪台哪卡起哪个实例）、分片清单、预计墙钟 |
| 批准词 | 明确的"发射"；批准前 GPU 零动作 |
| 批准后 | gpu-run 全生命周期：探卡→发射→双登记（台账 + record.py start）→验活 |
| 用户监控 | `python ops/gpu_jobs.py watch`（发射后原样奉上） |
| Claude 巡检 | job-monitor 只读 agent，30 分钟一巡 |
| 收尾 | 汇报条数与落盘路径 → **请示是否释放 vLLM 服务**（可能还要热用）→ 销号 → commit |

## 2. annotate 段（切样本 + 标签）——纯 CPU，无请示

- **规则常量表** `annotate/rules.py`：MIN_THINK=40、MAX_BOUNDS=64、HIST_ROUNDS=3、
  RESULT_CAP=400、`Task/[HISTORY]/[THINKING]` 拼版式，从 `build_dataset.py` 原样搬，
  一个数不改。
- **两档标签同一份文件**：每条样本同时带 `label_tool`（工具名）和 `label_call`
  （完整调用；参数归一化按 `param_label.py`：strip + 去引号，kwarg 保名、
  位置参数记 pos0/pos1…）。不出两份数据。
- **切分**：appworld 按官方分区文件（train 训 / dev 当 val / test_normal 考）；
  bfcl 轮到时定种子单切三堆。切分粒度 = 任务实例。
- **产物**：`data/<版本>/<env>_<model>/{train,val,test}.jsonl` +
  `ANNOTATE_REPORT.md`（每堆的事件数 / 样本数 / 类目分布 / 先验基线——
  对应 `DATA.md` §7 检查清单）。新版本条目同步补进 `DATA.md` §3/§4。
- **验收（验收线的前半）**：拿 v3 bfcl 原始轨迹重跑本段，与
  `envs/bert_data/v3/bfcl` 逐字节 diff（新增的 label_call 字段除外，只比旧字段）。

## 3. train 段（四格训练）

四格各一个入口脚本，共用配置：

| 格 | 做法 | 环境 |
|---|---|---|
| ModernBERT + 工具名 | 复刻 `train_probe.py` 全套超参：fp32 权重 + bf16 autocast、lr 2e-5、bs 8×累积4、3 epoch、maxlen 4096、左截断、损失权重 w=1/m、val 加权准确率选 best | mbert-env |
| ModernBERT + 参数 | 复刻 `train_extractor.py` 抽取头 | mbert-env |
| 因果 + 工具名 | 复刻 `train_causal_probe.py`（Qwen3-0.6B-Base + 线性头）；开训前必过混合架构对齐检查（老坑：旧版分块增量喂会静默算错） | cprobe-env |
| 因果 + 参数 | **唯一全新的训练代码**：生成式目标，输入 = 样本题干、目标 = 归一化后的完整调用串，teacher forcing，loss 只压调用串的 token | cprobe-env |

- **验收**：每格 50 步微训 smoke——loss 在降、检查点能存能读、显存不超卡。
- 精度铁律继承：权重 fp32，只在前向 autocast bf16（v2 全作废的教训）。

**GPU 请示计划**：12 次训练 + 回放评测**打成一个包一次请示**。
请示给看：12 行卡位分配表（A6000 池 19 张里挑 12）、单次时长、总墙钟、
四格 smoke 结果。批准词"发射"。发射时逐 run `record.py start`；
job-monitor 30 分钟一巡；全部收敛后统一汇报 → 释放 → 销号 → `record.py finish` → commit。

## 4. eval 段（回放评测）

- 复刻 `eval_replay.py` 的三步，校准堆合并成单 val：val 拟温度 → val 扫门槛
  （THETAS、风险档 0.05/0.1 全继承）→ test 冻结只跑一次。
- **参数档判分**：ModernBERT 侧用 `eval_extract.py` 的宽松/严格/整调用三档；
  因果侧**新写判分器**——生成 → 解析出工具名和参数 → 按 `param_label.py`
  同一套归一化 → 同三档口径。这是本段唯一的新零件。
- **产物**：每 run 一份 `REPLAY_REPORT.json`（字段兼容 `probe_server.py`，
  温度它直接能读）+ 全矩阵汇总 md（12 行 × trig_acc / coverage / earliness /
  wrong_spec / 参数三档）。
- **验收（验收线的后半，零 GPU）**：复用 `envs/bert_runs/bfcl_v3/logits_*.pt`
  现成 logits 跑本段，数字对上 `RESULTS.md` 的 v3 bfcl 行才放行。
- GPU 口径：回放要的前向已归入训练包的请示；纯复用 logits 的分析零卡、不请示。

## 5. inject 段（只定格式，无实验）

- 实测过 `probe_server.py` 的加载路径：`<run>/best/`（HF 检查点 + tokenizer +
  `label_map.json`）+ `REPLAY_REPORT.json`（读 temperature）。
  train/eval 两段的产物**天然就是这个布局**，所以本段不需要格式转换器。
- 只写一个 `inject/check_bundle.py` 校验器：加载一个训练产物、喂一条样本、
  吐出预测和触发判定——CPU 可跑，作为"接口留好了"的凭证。
- 无实验、无请示；注入实验将来另立项（请示点③）。

## 6. GPU 请示点总表

| 请示点 | 是什么 | 规模 | 请示前必须完成 |
|---|---|---|---|
| ① 第 0 波采集 | tokyo108 六卡 6 个 vLLM 实例 + appworld 594 题-模型 | 6 卡约一晚 | 发射脚本生成、1 题 smoke |
| ② 训练 + 回放包 | 12 次训练 + 回放评测 | A6000 池 12 卡约 2 小时 | 数据集造好、四格 smoke、验收线双通过 |
| ③ 注入实验 | 将来另立项 | 待定 | 探针矩阵结果出炉 |

每个请示点的流程固定：我出清单 → 你说"发射" → gpu-run 全生命周期 →
监控命令交你 → job-monitor 巡检 → 完成汇报 → 释放（服务类先问）→ 销号 → commit。

## 7. 写码顺序与工作量（全程不占 GPU，直到请示点②）

annotate（0.5 天，含逐字节 diff 验收）→ eval（0.5 天，含零 GPU 验收线）→
train 四格（1 天，新代码只有因果+参数一格）→ collect 生成器（0.25 天）→
inject 校验器（0.25 天）。合计约 2.5 天。顺序这么排的理由：annotate 和 eval
先立起验收线，train 的每一格写完立刻有东西可对，不攒债。
